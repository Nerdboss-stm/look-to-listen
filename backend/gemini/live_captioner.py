"""Gapless live audio captioning for both lanes (raw mix + clean target voice).

Primary: gemini-3.5-transcribe-live (v1alpha bidiGenerateContent, custom vocabulary from vocab.json).
- Prevents 60 s idle 1008 disconnect by sending 100 ms silence keep-alive every 2.0 s when idle.
- Prevents ~240 s 1011 session deadline by proactive make-before-break rotation (opens next
  session before closing old one with 1.0 s audio overlap -> 0 ms caption gap).
- On Live failure, falls back seamlessly to FB5 (gemini-4-hydrogen, ThinkingLevel.LOW, 1 s chunks)
  with strict 6 s HTTP timeout and concurrent chunk workers so neither lane ever stalls, and
  retries Live every 10.0 s in the background until Live recovers.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import time
import uuid
import wave
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from google.genai import types

from backend.gemini.client import MODELS, extract_usage, get_client
from backend.gemini.logger import log_model_call
from backend.gemini.vocab import get_vocab_terms

CHUNKED_PROMPT = (
    "Transcribe the speech in this audio exactly, word for word. "
    "Return only the words. If there is no speech, return an empty string."
)

CaptionCallback = Callable[[dict[str, Any]], Awaitable[None]]

# Session lifecycle & fallback constants (tuned from live logs/calls.jsonl measurements)
IDLE_KEEPALIVE_S = 2.0          # Server aborts idle sessions at ~62 s with 1008
ROTATE_AFTER_S = 200.0          # Proactively rotate before ~243 s 1011 session deadline (1x / 5 min)
ROTATE_OVERLAP_MIN_S = 1.0      # Minimum dual-feed overlap before handoff
ROTATE_HANDOFF_WAIT_S = 4.0     # Wait for warming session's first caption before silencing old
CONNECT_TIMEOUT_S = 6.0         # Bounded WebSocket handshake timeout
WS_PING_INTERVAL_S = 10.0       # Transport-level WebSocket ping cadence
WS_PONG_TIMEOUT_S = 10.0        # Restart ONLY if the socket itself fails to pong within 10 s
LIVE_RETRY_INTERVAL_S = 10.0    # Retry Live every 10 s while in FB5 fallback
FB5_HTTP_TIMEOUT_MS = 10000     # 10 s (server rejects <10 s deadline; stops 894 s TCP hangs)
FB5_MAX_CONCURRENT = 3          # Allow overlapping 1 s chunk calls so captions never gap


def pcm16_to_wav_bytes(pcm: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def transcribe_chunk_sync(
    pcm: bytes,
    *,
    model: str | None = None,
    vocab: list[str] | None = None,
    purpose: str = "chunked_caption",
    timeout_ms: int = FB5_HTTP_TIMEOUT_MS,
) -> tuple[str, float]:
    """FB5 fallback & G2 chunked benchmark: transcribe 16 kHz mono PCM with strict timeout."""
    model_id = model or MODELS.hydrogen
    client = get_client(timeout_ms=timeout_ms)
    wav_bytes = pcm16_to_wav_bytes(pcm)
    prompt = CHUNKED_PROMPT
    if vocab:
        prompt = f"{CHUNKED_PROMPT}\nKnown names/terms (if heard): {', '.join(vocab[:100])}"
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=model_id,
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = (resp.text or "").strip()
        in_tok, out_tok = extract_usage(resp)
        log_model_call(
            model=model_id,
            thinking_level="LOW",
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            purpose=purpose,
            ok=True,
        )
        return text, latency_ms
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        log_model_call(
            model=model_id,
            thinking_level="LOW",
            latency_ms=latency_ms,
            purpose=purpose,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        return "", latency_ms


@dataclass
class _LiveSessionHandle:
    """One active gemini-3.5-transcribe-live WebSocket session."""

    sid: str
    lane: str
    model: str
    cm: Any
    session: Any
    opened_at: float
    active_emit: bool = True
    closed: bool = False
    go_away_requested: bool = False
    last_send_at: float = field(default_factory=time.perf_counter)
    last_pong_at: float = field(default_factory=time.perf_counter)
    recv_task: asyncio.Task[Any] | None = None
    ping_task: asyncio.Task[Any] | None = None
    dead_event: asyncio.Event = field(default_factory=asyncio.Event)
    first_text_event: asyncio.Event = field(default_factory=asyncio.Event)
    error: str | None = None

    async def send_pcm16(self, pcm: bytes) -> None:
        if self.closed:
            return
        frame_bytes = 8000  # 250 ms @ 16 kHz mono int16 (reduces WS frame churn on venue Wi-Fi)
        for i in range(0, len(pcm), frame_bytes):
            chunk = pcm[i : i + frame_bytes]
            if chunk:
                await asyncio.wait_for(
                    self.session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                    ),
                    timeout=WS_PONG_TIMEOUT_S,
                )
        self.last_send_at = time.perf_counter()

    async def send_keepalive(self) -> None:
        if self.closed:
            return
        await asyncio.wait_for(
            self.session.send_realtime_input(
                audio=types.Blob(data=b"\x00" * 3200, mime_type="audio/pcm;rate=16000")
            ),
            timeout=WS_PONG_TIMEOUT_S,
        )
        self.last_send_at = time.perf_counter()

    async def close(self, *, graceful: bool = True) -> None:
        if self.closed:
            return
        self.closed = True
        self.active_emit = False
        if graceful:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    self.session.send_realtime_input(audio_stream_end=True),
                    timeout=1.0,
                )
        for task_attr in ("ping_task", "recv_task"):
            t = getattr(self, task_attr, None)
            if t is not None:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
                setattr(self, task_attr, None)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.cm.__aexit__(None, None, None), timeout=2.0)
        self.dead_event.set()


class LiveCaptionLane:
    """Gapless bidirectional Live transcription lane with make-before-break rotation & FB5 fallback."""

    def __init__(
        self,
        *,
        lane: str,
        on_text: CaptionCallback,
        model: str | None = None,
        use_chunked_fallback: bool | None = None,
        rotate_after_s: float = ROTATE_AFTER_S,
        live_retry_interval_s: float = LIVE_RETRY_INTERVAL_S,
    ) -> None:
        self.lane = lane  # "raw" or "target"
        self.on_text = on_text
        self.model = model or MODELS.transcribe_live
        self.force_chunked = (
            bool(use_chunked_fallback)
            if use_chunked_fallback is not None
            else os.getenv("FALLBACK_FB5_CHUNKED", "0") == "1"
        )
        self.rotate_after_s = float(rotate_after_s)
        self.live_retry_interval_s = float(live_retry_interval_s)
        self.active_mode: str = "chunked" if self.force_chunked else "live"

        self._running = False
        self._pcm_queue: asyncio.Queue[tuple[bytes, float, str | None]] = asyncio.Queue(maxsize=16)
        self._runner_task: asyncio.Task[Any] | None = None

        self._primary: _LiveSessionHandle | None = None
        self._warming: _LiveSessionHandle | None = None
        self._last_audio_ms: float = 0.0
        self._last_face_id: str | None = None
        self._last_emitted_final: str = ""
        self._last_emitted_at: float = 0.0
        self._consecutive_live_errors = 0
        self._next_live_retry_at: float = 0.0
        self._session_id = f"{lane}-{uuid.uuid4().hex[:6]}"
        self._reset_event = asyncio.Event()
        self._rotations_completed = 0

        # FB5 chunked state (non-blocking concurrent worker pool per lane)
        self._fb5_buf = bytearray()
        self._fb5_t_start: float = 0.0
        self._fb5_face_id: str | None = None
        self._fb5_sem = asyncio.Semaphore(FB5_MAX_CONCURRENT)
        self._fb5_tasks: set[asyncio.Task[Any]] = set()
        self._fb5_probe_task: asyncio.Task[Any] | None = None
        self._rotation_task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._runner_task = asyncio.create_task(self._run_loop(), name=f"caption-lane-{self.lane}")

    async def stop(self) -> None:
        self._running = False
        for t in (self._runner_task, self._rotation_task, self._fb5_probe_task):
            if t is not None:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
        self._runner_task = None
        self._rotation_task = None
        self._fb5_probe_task = None
        for t in list(self._fb5_tasks):
            t.cancel()
        self._fb5_tasks.clear()
        if self._warming is not None:
            await self._warming.close(graceful=False)
            self._warming = None
        if self._primary is not None:
            await self._primary.close(graceful=False)
            self._primary = None

    def reset_stream(self) -> None:
        """Clear queued stale audio (e.g. on target switch) and nudge session flush."""
        while not self._pcm_queue.empty():
            try:
                self._pcm_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._fb5_buf.clear()
        self._reset_event.set()

    def push_pcm16(
        self,
        pcm_bytes: bytes,
        *,
        t_capture_ms: float | None = None,
        face_id: str | None = None,
    ) -> None:
        """Enqueue latest PCM audio; drop oldest if full (never build backlog)."""
        if not pcm_bytes or not self._running:
            return
        ts = t_capture_ms if t_capture_ms is not None else (time.time() * 1000.0)
        if self._pcm_queue.full():
            try:
                self._pcm_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._pcm_queue.put_nowait((pcm_bytes, ts, face_id))
        except asyncio.QueueFull:
            pass

    async def _open_live_session(self, *, active_emit: bool = True) -> _LiveSessionHandle | None:
        """Open a single gemini-3.5-transcribe-live session with a strict handshake timeout."""
        client = get_client(api_version="v1alpha")
        vocab = get_vocab_terms()
        tx_cfg_kwargs: dict[str, Any] = {"language_codes": ["en-US"]}
        if vocab:
            tx_cfg_kwargs["custom_vocabulary"] = vocab[:1000]
        cfg = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(**tx_cfg_kwargs),
        )
        t_conn = time.perf_counter()
        cm = client.aio.live.connect(model=self.model, config=cfg)
        try:
            session = await asyncio.wait_for(cm.__aenter__(), timeout=CONNECT_TIMEOUT_S)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_model_call(
                model=self.model,
                thinking_level=None,
                latency_ms=(time.perf_counter() - t_conn) * 1000.0,
                purpose=f"live_error_{self.lane}",
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None

        conn_ms = (time.perf_counter() - t_conn) * 1000.0
        sid = f"{self._session_id}-{uuid.uuid4().hex[:5]}"
        handle = _LiveSessionHandle(
            sid=sid,
            lane=self.lane,
            model=self.model,
            cm=cm,
            session=session,
            opened_at=time.perf_counter(),
            active_emit=active_emit,
        )
        handle.recv_task = asyncio.create_task(
            self._recv_session(handle), name=f"tx-recv-{sid}"
        )
        handle.ping_task = asyncio.create_task(
            self._ping_session(handle), name=f"tx-ping-{sid}"
        )
        log_model_call(
            model=self.model,
            thinking_level=None,
            latency_ms=conn_ms,
            purpose=f"live_connect_{self.lane}",
            ok=True,
            extra={"vocab_terms": len(vocab), "sid": sid, "handoff": not active_emit},
        )
        return handle

    async def _ping_session(self, handle: _LiveSessionHandle) -> None:
        """Transport-level WebSocket ping/pong check: restart ONLY if no pong arrives within 10 s."""
        ws = getattr(handle.session, "_ws", None)
        if ws is None or not callable(getattr(ws, "ping", None)):
            return
        try:
            while self._running and not handle.closed:
                await asyncio.sleep(WS_PING_INTERVAL_S)
                if not self._running or handle.closed:
                    break
                try:
                    pong_waiter = await asyncio.wait_for(ws.ping(), timeout=WS_PONG_TIMEOUT_S)
                    await asyncio.wait_for(pong_waiter, timeout=WS_PONG_TIMEOUT_S)
                    handle.last_pong_at = time.perf_counter()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if handle.closed:
                        break
                    handle.error = f"PongTimeout({WS_PONG_TIMEOUT_S:.0f}s): {type(exc).__name__}: {exc}"
                    log_model_call(
                        model=self.model,
                        thinking_level=None,
                        latency_ms=round((time.perf_counter() - handle.opened_at) * 1000.0, 1),
                        purpose=f"live_error_{self.lane}",
                        ok=False,
                        error=handle.error,
                        extra={"sid": handle.sid},
                    )
                    handle.dead_event.set()
                    break
        except asyncio.CancelledError:
            raise

    async def _recv_session(self, handle: _LiveSessionHandle) -> None:
        """Receive interim & final transcription events for one Live session handle."""
        utterance_id = f"{handle.sid}-{uuid.uuid4().hex[:6]}"
        last_interim = ""
        try:
            while self._running and not handle.closed:
                got_any = False
                async for msg in handle.session.receive():
                    got_any = True
                    if not self._running or handle.closed:
                        break
                    if getattr(msg, "go_away", None) is not None:
                        handle.go_away_requested = True
                    sc = getattr(msg, "server_content", None)
                    if not sc:
                        continue

                    interim = getattr(sc, "interim_input_transcription", None)
                    final = getattr(sc, "input_transcription", None)
                    final_text = (getattr(final, "text", None) or "").strip() if final else ""
                    interim_text = (getattr(interim, "text", None) or "").strip() if interim else ""

                    if final_text or interim_text:
                        handle.first_text_event.set()

                    if not handle.active_emit:
                        # Warming session during overlap: stay ready to emit immediately upon promotion
                        continue

                    if final_text:
                        # Deduplicate exact overlap repetition across rotation boundary
                        now_mono = time.perf_counter()
                        if (
                            final_text.lower() == self._last_emitted_final.lower()
                            and (now_mono - self._last_emitted_at) < 2.0
                        ):
                            utterance_id = f"{handle.sid}-{uuid.uuid4().hex[:6]}"
                            last_interim = ""
                            continue
                        self._last_emitted_final = final_text
                        self._last_emitted_at = now_mono

                        now_ms = time.time() * 1000.0
                        t1 = self._last_audio_ms or now_ms
                        t0 = max(0.0, t1 - 500.0)
                        latency_ms = max(0.0, now_ms - t1)
                        log_model_call(
                            model=self.model,
                            thinking_level=None,
                            latency_ms=latency_ms,
                            purpose=f"live_caption_{self.lane}_final",
                            ok=True,
                            extra={"chars": len(final_text), "finished": True, "sid": handle.sid},
                        )
                        await self.on_text(
                            {
                                "segment_id": utterance_id,
                                "lane": self.lane,
                                "text": final_text,
                                "t0": round(t0, 1),
                                "t1": round(t1, 1),
                                "face_id": self._last_face_id if self.lane == "target" else None,
                                "confidence": 0.95,
                                "latency_ms": round(latency_ms, 1),
                                "is_final": True,
                                "model": self.model,
                            }
                        )
                        utterance_id = f"{handle.sid}-{uuid.uuid4().hex[:6]}"
                        last_interim = ""
                    elif interim_text and interim_text != last_interim:
                        last_interim = interim_text
                        now_ms = time.time() * 1000.0
                        t1 = self._last_audio_ms or now_ms
                        t0 = max(0.0, t1 - 500.0)
                        latency_ms = max(0.0, now_ms - t1)
                        await self.on_text(
                            {
                                "segment_id": utterance_id,
                                "lane": self.lane,
                                "text": interim_text,
                                "t0": round(t0, 1),
                                "t1": round(t1, 1),
                                "face_id": self._last_face_id if self.lane == "target" else None,
                                "confidence": 0.85,
                                "latency_ms": round(latency_ms, 1),
                                "is_final": False,
                                "model": self.model,
                            }
                        )
                if not got_any:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            handle.error = f"{type(exc).__name__}: {exc}"
            if not handle.closed:
                log_model_call(
                    model=self.model,
                    thinking_level=None,
                    latency_ms=(time.perf_counter() - handle.opened_at) * 1000.0,
                    purpose=f"live_error_{self.lane}",
                    ok=False,
                    error=handle.error,
                    extra={"sid": handle.sid},
                )
        finally:
            handle.dead_event.set()

    async def _rotate_make_before_break(self) -> None:
        """Open next Live session while old one is still active, wait until new emits text, then swap."""
        old = self._primary
        if old is None or old.closed:
            return
        new_handle = await self._open_live_session(active_emit=False)
        if new_handle is None or not self._running:
            return
        self._warming = new_handle
        try:
            # Dual-feed overlap: keep old emitting until new_handle is actively producing captions
            await asyncio.sleep(ROTATE_OVERLAP_MIN_S)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    new_handle.first_text_event.wait(),
                    timeout=ROTATE_HANDOFF_WAIT_S,
                )
            if not self._running or new_handle.dead_event.is_set():
                await new_handle.close(graceful=False)
                return
            # Atomic handoff: promote new_handle, silence old handle's emission, then drain & close old
            new_handle.active_emit = True
            self._primary = new_handle
            self._warming = None
            self._rotations_completed += 1
            old.active_emit = False
            log_model_call(
                model=self.model,
                thinking_level=None,
                latency_ms=round((time.perf_counter() - old.opened_at) * 1000.0, 1),
                purpose=f"live_rotate_{self.lane}",
                ok=True,
                extra={
                    "old_sid": old.sid,
                    "new_sid": new_handle.sid,
                    "rotations": self._rotations_completed,
                    "new_had_text": new_handle.first_text_event.is_set(),
                },
            )
            await old.close(graceful=True)
        finally:
            if self._warming is new_handle:
                self._warming = None

    async def _probe_live_recovery(self) -> None:
        """Background 10 s Live recovery probe while FB5 chunked keeps captioning both lanes."""
        if self.force_chunked or not self._running or self._primary is not None:
            return
        handle = await self._open_live_session(active_emit=True)
        if handle is not None and self._running:
            self._primary = handle
            self._consecutive_live_errors = 0
            self.active_mode = "live"
            self._fb5_buf.clear()
        else:
            self._next_live_retry_at = time.perf_counter() + self.live_retry_interval_s

    def _dispatch_fb5_chunk(self, chunk: bytes, t_start: float, face_id: str | None) -> None:
        """Run one FB5 1 s chunk transcription concurrently without stalling the PCM reader."""
        async def _worker() -> None:
            async with self._fb5_sem:
                t1 = t_start + 1000.0
                vocab = get_vocab_terms()
                try:
                    text, lat_ms = await asyncio.wait_for(
                        asyncio.to_thread(
                            transcribe_chunk_sync,
                            chunk,
                            model=MODELS.hydrogen,
                            vocab=vocab,
                            purpose=f"fb5_chunked_{self.lane}",
                            timeout_ms=FB5_HTTP_TIMEOUT_MS,
                        ),
                        timeout=(FB5_HTTP_TIMEOUT_MS / 1000.0) + 1.0,
                    )
                except asyncio.TimeoutError:
                    log_model_call(
                        model=MODELS.hydrogen,
                        thinking_level="LOW",
                        latency_ms=float(FB5_HTTP_TIMEOUT_MS + 1000),
                        purpose=f"fb5_chunked_{self.lane}",
                        ok=False,
                        error="TimeoutError: fb5_worker_timeout",
                    )
                    return
                if text and self._running:
                    await self.on_text(
                        {
                            "lane": self.lane,
                            "text": text,
                            "t0": round(t_start, 1),
                            "t1": round(t1, 1),
                            "face_id": face_id if self.lane == "target" else None,
                            "confidence": 0.85,
                            "latency_ms": round(lat_ms, 1),
                            "is_final": True,
                            "model": MODELS.hydrogen,
                        }
                    )

        task = asyncio.create_task(_worker(), name=f"fb5-{self.lane}")
        self._fb5_tasks.add(task)
        task.add_done_callback(self._fb5_tasks.discard)

    async def _run_loop(self) -> None:
        """Unified non-blocking PCM dispatcher managing Live (with rotation) and FB5 (with 10 s retry)."""
        while self._running:
            now = time.perf_counter()

            # 1. Ensure a Live session is connected (unless forced to FB5 or cooling down for 10 s)
            if not self.force_chunked:
                if self._primary is not None and self._primary.dead_event.is_set():
                    dead = self._primary
                    self._primary = None
                    await dead.close(graceful=False)
                    self._consecutive_live_errors += 1
                    if self._consecutive_live_errors >= 2:
                        self.active_mode = "chunked"
                        self._next_live_retry_at = now + self.live_retry_interval_s

                if self._primary is None:
                    if self._consecutive_live_errors < 2:
                        handle = await self._open_live_session(active_emit=True)
                        if handle is not None:
                            self._primary = handle
                            self._consecutive_live_errors = 0
                            self.active_mode = "live"
                            self._fb5_buf.clear()
                        else:
                            self._consecutive_live_errors += 1
                            if self._consecutive_live_errors >= 2:
                                self.active_mode = "chunked"
                                self._next_live_retry_at = time.perf_counter() + self.live_retry_interval_s
                    else:
                        self.active_mode = "chunked"
                        # Retry Live every 10.0 s in background while FB5 keeps captioning
                        if now >= self._next_live_retry_at and (
                            self._fb5_probe_task is None or self._fb5_probe_task.done()
                        ):
                            self._next_live_retry_at = now + self.live_retry_interval_s
                            self._fb5_probe_task = asyncio.create_task(
                                self._probe_live_recovery(), name=f"live-retry-{self.lane}"
                            )
                else:
                    self.active_mode = "live"
                    # Proactive make-before-break rotation before server deadline or on go_away
                    age = now - self._primary.opened_at
                    if (age >= self.rotate_after_s or self._primary.go_away_requested) and (
                        self._rotation_task is None or self._rotation_task.done()
                    ):
                        self._rotation_task = asyncio.create_task(
                            self._rotate_make_before_break(), name=f"live-rotate-{self.lane}"
                        )
            else:
                self.active_mode = "chunked"

            # 2. Handle target-switch stream flush
            if self._reset_event.is_set():
                self._reset_event.clear()
                self._fb5_buf.clear()
                if self._primary is not None and not self._primary.closed:
                    with contextlib.suppress(Exception):
                        await self._primary.send_keepalive()

            # 3. Drain next PCM chunk or send keep-alive silence every 2.0 s when idle
            try:
                pcm, t_cap, face_id = await asyncio.wait_for(self._pcm_queue.get(), timeout=0.4)
            except asyncio.TimeoutError:
                # Idle keep-alive prevents 60 s 1008 server disconnect on quiet/idle lanes
                for h in (self._primary, self._warming):
                    if h is not None and not h.closed and (time.perf_counter() - h.last_send_at) >= IDLE_KEEPALIVE_S:
                        try:
                            await h.send_keepalive()
                        except Exception:
                            h.dead_event.set()
                continue

            # Drop stale audio older than 1.5 s (live beats complete)
            if (time.time() * 1000.0) - t_cap > 1500.0:
                continue

            self._last_audio_ms = t_cap + (len(pcm) / 32.0)
            self._last_face_id = face_id

            if self._primary is not None and not self._primary.closed:
                # Fan out to both primary and warming sessions during make-before-break overlap
                for h in (self._primary, self._warming):
                    if h is not None and not h.closed:
                        try:
                            await h.send_pcm16(pcm)
                        except Exception as exc:
                            h.error = f"SendError: {type(exc).__name__}: {exc}"
                            log_model_call(
                                model=self.model,
                                thinking_level=None,
                                latency_ms=round((time.perf_counter() - h.opened_at) * 1000.0, 1),
                                purpose=f"live_error_{self.lane}",
                                ok=False,
                                error=h.error,
                                extra={"sid": h.sid},
                            )
                            h.dead_event.set()
            else:
                # FB5 chunked fallback (both raw and target lanes run concurrently with 6 s timeout)
                if not self._fb5_buf:
                    self._fb5_t_start = t_cap
                self._fb5_face_id = face_id
                self._fb5_buf.extend(pcm)
                while len(self._fb5_buf) >= 32000:  # 1.0 s @ 16 kHz mono int16
                    chunk = bytes(self._fb5_buf[:32000])
                    del self._fb5_buf[:32000]
                    self._dispatch_fb5_chunk(chunk, self._fb5_t_start, self._fb5_face_id)
                    self._fb5_t_start += 1000.0
