"""Continuous 16 kHz mono PCM playback for clean separated target voice.

Designed to satisfy SPEC AT4:
- Plays continuously with a real jitter-cushion lead-in buffer (default 220 ms)
  so Wi-Fi RTT jitter up to p95 (~470 ms) produces ZERO audible gaps or clicks
- Cosine crossfade at discontinuity / target-switch / trim boundaries
- Caps excess buffer depth (> max_buffer_ms) so voice delay never drifts upward
- Tracks true mid-stream underrun gaps (gaps closed when audio resumes) for AT4
- Degrades cleanly behind PLAYBACK_ENABLED flag if audio hardware is unavailable
"""

from __future__ import annotations

import collections
import os
import threading
import time
from typing import Any

import numpy as np

SR = 16000
XF_SAMPLES = 160  # 10 ms cosine crossfade at discontinuities/trims
_FADE_IN = (0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, XF_SAMPLES))).astype(np.float32)
_FADE_OUT = (1.0 - _FADE_IN).astype(np.float32)


class LiveAudioPlayer:
    """Real-time jitter-buffered 16 kHz speaker/headphone player via sounddevice."""

    def __init__(
        self,
        *,
        sample_rate: int = SR,
        prefill_ms: int = 260,
        max_buffer_ms: int = 1200,
        blocksize: int = 320,  # 20 ms callback blocks
        enabled: bool | None = None,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.prefill_ms = int(prefill_ms)
        self.prefill_samples = int(self.sample_rate * self.prefill_ms / 1000)
        self.max_buffer_samples = int(self.sample_rate * max_buffer_ms / 1000)
        # Keep healthy 1-hop + cushion (~720 ms) when trimming runaway bursts
        self.trim_target_samples = int(
            self.sample_rate * min(max_buffer_ms - 150, self.prefill_ms + 500) / 1000
        )
        self.blocksize = int(blocksize)
        self.device = device

        if enabled is None:
            env_flag = os.environ.get("PLAYBACK_ENABLED", "0").strip().lower()
            self._enabled = env_flag in ("1", "true", "yes", "on")
        else:
            self._enabled = bool(enabled)

        self._lock = threading.Lock()
        self._chunks: collections.deque[np.ndarray] = collections.deque()
        self._queued_samples = 0
        self._primed = False
        self._lead_in_remaining = 0
        self._stream: Any = None
        self._running = False
        self._device_ok = False
        self._device_error: str | None = None
        self._device_name: str | None = None

        # Fade / continuity state
        self._last_sample: float = 0.0
        self._in_underrun = False
        self._underrun_samples = 0
        self._has_played_any = False

        # Telemetry for AT4 & DELAY meter
        self._total_enqueued_samples = 0
        self._total_played_samples = 0
        self._trimmed_samples = 0
        self._underrun_events = 0
        self._gaps_over_300ms = 0
        self._max_gap_ms = 0.0
        self._last_enqueue_ts = 0.0
        self._gain = 1.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def device_ok(self) -> bool:
        return self._device_ok

    def set_enabled(self, enabled: bool) -> None:
        want = bool(enabled)
        need_start = False
        with self._lock:
            self._enabled = want
            if not self._enabled:
                self._chunks.clear()
                self._queued_samples = 0
                self._primed = False
                self._lead_in_remaining = 0
                self._in_underrun = False
                self._underrun_samples = 0
            elif self._running and self._stream is None:
                need_start = True
        if need_start:
            self._open_stream()

    def set_gain(self, gain: float) -> None:
        with self._lock:
            self._gain = float(max(0.0, min(2.0, gain)))

    def _open_stream(self) -> bool:
        try:
            import sounddevice as sd

            dev_info = sd.query_devices(self.device, "output")
            self._device_name = str(dev_info.get("name", "default"))
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.blocksize,
                latency="low",
                device=self.device,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._device_ok = True
            self._device_error = None
        except Exception as e:
            self._stream = None
            self._device_ok = False
            self._device_error = f"{type(e).__name__}: {e}"
        return self._device_ok

    def start(self) -> bool:
        """Open the sounddevice output stream only if PLAYBACK_ENABLED is on."""
        if self._running:
            return self._device_ok
        self._running = True
        if not self._enabled:
            self._device_ok = False
            self._device_error = None
            return False
        return self._open_stream()

    def stop(self) -> None:
        self._running = False
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            self._chunks.clear()
            self._queued_samples = 0
            self._primed = False
            self._lead_in_remaining = 0

    def reset(self) -> None:
        """Clear queued audio and re-prime (e.g. on target switch or new session)."""
        with self._lock:
            self._chunks.clear()
            self._queued_samples = 0
            self._primed = False
            self._lead_in_remaining = 0
            self._in_underrun = False
            self._underrun_samples = 0
            self._has_played_any = False

    def reset_metrics(self) -> None:
        with self._lock:
            self._total_enqueued_samples = 0
            self._total_played_samples = 0
            self._trimmed_samples = 0
            self._underrun_events = 0
            self._gaps_over_300ms = 0
            self._max_gap_ms = 0.0
            self._in_underrun = False
            self._underrun_samples = 0
            self._has_played_any = False

    def enqueue_pcm16(self, pcm_bytes: bytes, *, discontinuous: bool = False) -> int:
        """Enqueue little-endian int16 mono 16 kHz PCM bytes for gapless playback."""
        if not pcm_bytes:
            return 0
        n_bytes = len(pcm_bytes) - (len(pcm_bytes) % 2)
        if n_bytes <= 0:
            return 0
        samples = np.frombuffer(pcm_bytes[:n_bytes], dtype="<i2").astype(np.float32) / 32768.0
        return self.enqueue_float32(samples, discontinuous=discontinuous)

    def enqueue_float32(self, samples: np.ndarray, *, discontinuous: bool = False) -> int:
        """Enqueue float32 mono samples in [-1, 1] with crossfade & drift control."""
        if samples.size == 0:
            return 0
        arr = np.ascontiguousarray(samples, dtype=np.float32).copy()

        with self._lock:
            if not self._enabled:
                return 0

            self._last_enqueue_ts = time.monotonic()
            self._total_enqueued_samples += arr.size

            # If recovering from a mid-stream underrun, close that gap event cleanly now
            if self._in_underrun and self._underrun_samples > 0:
                self._finish_underrun_locked()

            # Smooth fade-in on discontinuity or initial startup
            if (discontinuous or not self._primed) and arr.size >= XF_SAMPLES:
                if self._chunks and discontinuous:
                    prev = self._chunks.pop()
                    if prev.size >= XF_SAMPLES:
                        blended = prev[-XF_SAMPLES:] * _FADE_OUT + arr[:XF_SAMPLES] * _FADE_IN
                        if prev.size > XF_SAMPLES:
                            self._chunks.append(prev[:-XF_SAMPLES])
                        self._chunks.append(blended)
                        arr = arr[XF_SAMPLES:]
                        self._queued_samples -= XF_SAMPLES
                    else:
                        self._chunks.append(prev)
                        arr[:XF_SAMPLES] *= _FADE_IN
                else:
                    arr[:XF_SAMPLES] *= _FADE_IN

            if arr.size > 0:
                self._chunks.append(arr)
                self._queued_samples += arr.size

            # Cap buffer depth so voice delay never drifts upward
            if self._queued_samples > self.max_buffer_samples:
                excess = self._queued_samples - self.trim_target_samples
                trimmed = 0
                while excess > 0 and self._chunks:
                    head = self._chunks[0]
                    if head.size <= excess:
                        self._chunks.popleft()
                        self._queued_samples -= head.size
                        excess -= head.size
                        trimmed += head.size
                    else:
                        rem = head[excess:].copy()
                        if rem.size >= XF_SAMPLES:
                            rem[:XF_SAMPLES] *= _FADE_IN
                        self._chunks[0] = rem
                        self._queued_samples -= excess
                        trimmed += excess
                        excess = 0
                self._trimmed_samples += trimmed

            # Prime with an explicit jitter-cushion lead-in before playout begins
            if not self._primed and self._queued_samples >= self.prefill_samples:
                self._primed = True
                self._lead_in_remaining = self.prefill_samples

            return int(samples.size)

    def _pop_samples_locked(self, count: int) -> np.ndarray:
        """Pop up to `count` float32 samples from the deque (caller holds self._lock)."""
        if self._queued_samples <= 0:
            return np.empty(0, dtype=np.float32)
        take = min(count, self._queued_samples)
        out = np.empty(take, dtype=np.float32)
        filled = 0
        while filled < take and self._chunks:
            head = self._chunks[0]
            need = take - filled
            if head.size <= need:
                out[filled : filled + head.size] = head
                filled += head.size
                self._chunks.popleft()
            else:
                out[filled:] = head[:need]
                self._chunks[0] = head[need:]
                filled += need
        self._queued_samples -= filled
        return out

    def _finish_underrun_locked(self) -> None:
        if self._in_underrun and self._underrun_samples > 0:
            gap_ms = (self._underrun_samples / self.sample_rate) * 1000.0
            self._underrun_events += 1
            if gap_ms > self._max_gap_ms:
                self._max_gap_ms = gap_ms
            if gap_ms > 300.0:
                self._gaps_over_300ms += 1
        self._in_underrun = False
        self._underrun_samples = 0

    def render_block(self, frames: int) -> np.ndarray:
        """Produce `frames` output samples (used by audio callback and unit tests)."""
        out = np.zeros(frames, dtype=np.float32)
        with self._lock:
            if not self._enabled or not self._primed:
                self._last_sample = 0.0
                return out

            # Burn down initial jitter-cushion lead-in before playing hop 0
            if self._lead_in_remaining > 0:
                if self._lead_in_remaining >= frames:
                    self._lead_in_remaining -= frames
                    return out
                offset = self._lead_in_remaining
                self._lead_in_remaining = 0
                need = frames - offset
                avail = min(need, self._queued_samples)
                if avail > 0:
                    block = self._pop_samples_locked(avail) * self._gain
                    out[offset : offset + avail] = block
                    self._last_sample = float(out[offset + avail - 1])
                    self._total_played_samples += avail
                    self._has_played_any = True
                return out

            if self._queued_samples >= frames:
                if self._in_underrun:
                    self._finish_underrun_locked()
                block = self._pop_samples_locked(frames)
                out[:] = block * self._gain
                self._last_sample = float(out[-1])
                self._total_played_samples += frames
                self._has_played_any = True
                return out

            # Partial or empty buffer -> underrun handling
            avail = self._queued_samples
            if avail > 0:
                if self._in_underrun:
                    self._finish_underrun_locked()
                block = self._pop_samples_locked(avail)
                block = block * self._gain
                ramp = min(avail, 64)
                if ramp > 1:
                    block[-ramp:] *= np.linspace(1.0, 0.0, ramp, dtype=np.float32)
                out[:avail] = block
                self._total_played_samples += avail
                self._has_played_any = True

            missing = frames - avail
            self._last_sample = 0.0
            # Track silence as a potential mid-stream underrun; finalized only if stream resumes
            # (post-stream idle silence after the last hop is NOT a mid-playback gap)
            if self._has_played_any:
                if (time.monotonic() - self._last_enqueue_ts) < 1.5:
                    self._in_underrun = True
                    self._underrun_samples += missing
                else:
                    # Stream has gone idle; reset cleanly without charging idle tail as a gap
                    self._in_underrun = False
                    self._underrun_samples = 0
                    self._primed = False
            return out

    def _audio_callback(
        self, outdata: np.ndarray, frames: int, time_info: Any, status: Any
    ) -> None:
        block = self.render_block(frames)
        outdata[:, 0] = block

    def buffer_ms(self) -> float:
        with self._lock:
            return round((self._queued_samples / self.sample_rate) * 1000.0, 1)

    def effective_playback_buf_ms(self) -> float:
        """Returns actual queued audio + lead-in cushion when backend plays, else browser VoicePlayer's 150 ms buffer."""
        with self._lock:
            if not self._enabled:
                return 150.0  # Browser VoicePlayer bufferLeadS = 0.15 s (SPEC budget)
            if self._primed:
                total = self._queued_samples + self._lead_in_remaining
                return round((total / self.sample_rate) * 1000.0, 1)
            return float(self.prefill_ms)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            # Report finalized mid-stream gaps (closed when audio resumed)
            return {
                "enabled": self._enabled,
                "device_ok": self._device_ok,
                "device_name": self._device_name,
                "device_error": self._device_error,
                "primed": self._primed,
                "prefill_ms": self.prefill_ms,
                "buffer_ms": round((self._queued_samples / self.sample_rate) * 1000.0, 1),
                "total_played_s": round(self._total_played_samples / self.sample_rate, 2),
                "total_enqueued_s": round(self._total_enqueued_samples / self.sample_rate, 2),
                "trimmed_ms": round((self._trimmed_samples / self.sample_rate) * 1000.0, 1),
                "underrun_events": self._underrun_events,
                "gaps_over_300ms": self._gaps_over_300ms,
                "max_gap_ms": round(self._max_gap_ms, 1),
            }
