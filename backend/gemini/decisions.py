"""Decision 1 per-face speaking classifier (gemini-decision-1) + LeakageGuard (E12).

Primary: Gemini Decisions API (`models/gemini-decision-1`) on a 1 s face-crop video + audio clip.
Fallback FB6: MediaPipe `mouth_open` ratio (marked calibrated=False, source='mediapipe-uncalibrated').
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import subprocess
import tempfile
import time
import wave
from collections import deque
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.gemini.client import MODELS, get_client
from backend.gemini.logger import log_model_call

SPEAKING_INSTRUCTIONS = "Is the person in this video speaking right now?"
SPEAKING_CRITERIA = {
    "yes": "The person's mouth and lips are actively moving in sync with spoken audio.",
    "no": "The person is silent, listening, or their lips are not moving with the spoken audio.",
}


def build_av_mp4_bytes(
    jpegs: list[bytes],
    pcm16: bytes,
    *,
    fps: float = 12.0,
    sample_rate: int = 16000,
) -> bytes:
    """Encode a list of JPEG face crops + 16 kHz mono int16 PCM into a compact MP4 clip."""
    if not jpegs:
        raise ValueError("No JPEG frames provided")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        wav_path = td_path / "audio.wav"
        raw_vid = td_path / "video.mp4"
        out_mp4 = td_path / "av.mp4"

        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm16)

        first = cv2.imdecode(np.frombuffer(jpegs[0], dtype=np.uint8), cv2.IMREAD_COLOR)
        if first is None:
            raise ValueError("Invalid JPEG frame")
        h, w_px = first.shape[:2]
        # Ensure even dimensions for H.264 yuv420p
        eh, ew = max(2, h - (h % 2)), max(2, w_px - (w_px % 2))
        writer = cv2.VideoWriter(str(raw_vid), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ew, eh))
        for jb in jpegs:
            fr = cv2.imdecode(np.frombuffer(jb, dtype=np.uint8), cv2.IMREAD_COLOR)
            if fr is None:
                continue
            if fr.shape[0] != eh or fr.shape[1] != ew:
                fr = cv2.resize(fr, (ew, eh))
            writer.write(fr)
        writer.release()

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw_vid),
                "-i",
                str(wav_path),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "zerolatency",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "32k",
                "-shortest",
                str(out_mp4),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return out_mp4.read_bytes()


def pcm_to_wav_bytes(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16)
    return buf.getvalue()


class SpeakingDecisionClient:
    """Reuses a keep-alive v1alpha genai.Client for fast Decisions API calls with FB6 fallback."""

    def __init__(self, *, use_fallback_fb6: bool | None = None) -> None:
        self.force_fb6 = (
            bool(use_fallback_fb6)
            if use_fallback_fb6 is not None
            else os.getenv("FALLBACK_FB6_MEDIAPIPE", "0") == "1"
        )
        self._client = get_client(api_version="v1alpha")
        self._consecutive_errors = 0

    def decide_from_mp4_sync(
        self,
        mp4_bytes: bytes,
        *,
        face_id: str,
        window_t0: float,
        window_t1: float,
        mouth_open: float | None = None,
        purpose: str = "decision_speaking",
    ) -> dict[str, Any]:
        """Call gemini-decision-1 on an AV MP4 clip; returns contract-valid SpeakingDecision."""
        if self.force_fb6 or self._consecutive_errors >= 5:
            return self._fb6_mediapipe(face_id, window_t0, window_t1, mouth_open)

        mp4_b64 = base64.b64encode(mp4_bytes).decode("ascii")
        model_ref = f"models/{MODELS.decision}" if not MODELS.decision.startswith("models/") else MODELS.decision
        t0 = time.perf_counter()
        try:
            resp = self._client.decisions.create(
                model=model_ref,
                input=[
                    {
                        "type": "video",
                        "data": mp4_b64,
                        "mime_type": "video/mp4",
                        "resolution": "low",
                        "processing": "static",
                    }
                ],
                questions={
                    "speaking": {
                        "type": "choice",
                        "instructions": SPEAKING_INSTRUCTIONS,
                        "criteria": SPEAKING_CRITERIA,
                    }
                },
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._consecutive_errors = 0
            ans = (resp.answers or {}).get("speaking")
            probs = getattr(ans, "probabilities", None) or {}
            p_yes = float(probs.get("yes", 0.0))
            p_yes = max(0.0, min(1.0, p_yes))

            usage = getattr(resp, "usage", None)
            in_tok = getattr(usage, "total_input_tokens", None) if usage else None
            out_tok = getattr(usage, "total_output_tokens", None) if usage else None
            log_model_call(
                model=MODELS.decision,
                thinking_level=None,
                latency_ms=latency_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                probability=round(p_yes, 6),
                purpose=purpose,
                ok=True,
                extra={"face_id": face_id, "format": "video/mp4"},
            )
            return {
                "face_id": str(face_id),
                "window_t0": round(float(window_t0), 1),
                "window_t1": round(float(window_t1), 1),
                "p_speaking": round(p_yes, 4),
                "latency_ms": round(latency_ms, 2),
                "calibrated": True,
                "source": "decision-1",
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._consecutive_errors += 1
            log_model_call(
                model=MODELS.decision,
                thinking_level=None,
                latency_ms=latency_ms,
                purpose=purpose,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                extra={"face_id": face_id},
            )
            return self._fb6_mediapipe(face_id, window_t0, window_t1, mouth_open)

    def decide_from_frames_wav_sync(
        self,
        jpegs: list[bytes],
        pcm16: bytes,
        *,
        face_id: str,
        window_t0: float,
        window_t1: float,
        mouth_open: float | None = None,
        max_frames: int = 4,
        purpose: str = "decision_speaking_frames",
    ) -> dict[str, Any]:
        """Alternate zero-ffmpeg format: sampled low-res JPEG frames + 16 kHz WAV audio."""
        if self.force_fb6 or self._consecutive_errors >= 5 or not jpegs:
            return self._fb6_mediapipe(face_id, window_t0, window_t1, mouth_open)

        # Evenly sample up to max_frames across the 1 s window
        if len(jpegs) > max_frames:
            idxs = np.linspace(0, len(jpegs) - 1, max_frames, dtype=int)
            picked = [jpegs[int(i)] for i in idxs]
        else:
            picked = list(jpegs)

        inp: list[dict[str, Any]] = [
            {
                "type": "image",
                "data": base64.b64encode(jb).decode("ascii"),
                "mime_type": "image/jpeg",
                "resolution": "low",
            }
            for jb in picked
        ]
        inp.append(
            {
                "type": "audio",
                "data": base64.b64encode(pcm_to_wav_bytes(pcm16)).decode("ascii"),
                "mime_type": "audio/wav",
            }
        )
        model_ref = f"models/{MODELS.decision}" if not MODELS.decision.startswith("models/") else MODELS.decision
        t0 = time.perf_counter()
        try:
            resp = self._client.decisions.create(
                model=model_ref,
                input=inp,
                questions={
                    "speaking": {
                        "type": "choice",
                        "instructions": SPEAKING_INSTRUCTIONS,
                        "criteria": SPEAKING_CRITERIA,
                    }
                },
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._consecutive_errors = 0
            ans = (resp.answers or {}).get("speaking")
            probs = getattr(ans, "probabilities", None) or {}
            p_yes = max(0.0, min(1.0, float(probs.get("yes", 0.0))))
            usage = getattr(resp, "usage", None)
            log_model_call(
                model=MODELS.decision,
                thinking_level=None,
                latency_ms=latency_ms,
                input_tokens=getattr(usage, "total_input_tokens", None) if usage else None,
                output_tokens=getattr(usage, "total_output_tokens", None) if usage else None,
                probability=round(p_yes, 6),
                purpose=purpose,
                ok=True,
                extra={"face_id": face_id, "format": f"{len(picked)}xjpeg+wav"},
            )
            return {
                "face_id": str(face_id),
                "window_t0": round(float(window_t0), 1),
                "window_t1": round(float(window_t1), 1),
                "p_speaking": round(p_yes, 4),
                "latency_ms": round(latency_ms, 2),
                "calibrated": True,
                "source": "decision-1",
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._consecutive_errors += 1
            log_model_call(
                model=MODELS.decision,
                thinking_level=None,
                latency_ms=latency_ms,
                purpose=purpose,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                extra={"face_id": face_id},
            )
            return self._fb6_mediapipe(face_id, window_t0, window_t1, mouth_open)

    async def decide_window(
        self,
        jpegs: list[bytes],
        pcm16: bytes,
        *,
        face_id: str,
        window_t0: float,
        window_t1: float,
        mouth_open: float | None = None,
        prefer_frames: bool = True,
    ) -> dict[str, Any]:
        """Async wrapper used in the live 0.5 s loop."""
        if not jpegs:
            return self._fb6_mediapipe(face_id, window_t0, window_t1, mouth_open)
        if prefer_frames:
            return await asyncio.to_thread(
                self.decide_from_frames_wav_sync,
                jpegs,
                pcm16,
                face_id=face_id,
                window_t0=window_t0,
                window_t1=window_t1,
                mouth_open=mouth_open,
            )
        mp4 = await asyncio.to_thread(build_av_mp4_bytes, jpegs, pcm16)
        return await asyncio.to_thread(
            self.decide_from_mp4_sync,
            mp4,
            face_id=face_id,
            window_t0=window_t0,
            window_t1=window_t1,
            mouth_open=mouth_open,
        )

    @staticmethod
    def _fb6_mediapipe(
        face_id: str,
        window_t0: float,
        window_t1: float,
        mouth_open: float | None,
    ) -> dict[str, Any]:
        """FB6 fallback: map MediaPipe mouth-open ratio [0..1] to an uncalibrated score."""
        ratio = float(mouth_open or 0.0)
        # Typical closed mouth ~0.02-0.06, talking ~0.12-0.45
        p = max(0.0, min(1.0, (ratio - 0.04) / 0.20))
        return {
            "face_id": str(face_id),
            "window_t0": round(float(window_t0), 1),
            "window_t1": round(float(window_t1), 1),
            "p_speaking": round(p, 4),
            "latency_ms": 0.5,
            "calibrated": False,
            "source": "mediapipe-uncalibrated",
        }


class LeakageGuard:
    """Tracks per-face speaking timeline and gates target-lane captions (E12)."""

    def __init__(self, *, decision_threshold: float = 0.9, guard_ms: int = 750) -> None:
        self.decision_threshold = float(decision_threshold)
        self.guard_ms = int(guard_ms)
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self.dropped_count = 0
        self.passed_count = 0

    def configure(self, *, decision_threshold: float | None = None, guard_ms: int | None = None) -> None:
        if decision_threshold is not None:
            self.decision_threshold = float(decision_threshold)
        if guard_ms is not None:
            self.guard_ms = int(guard_ms)

    def record(self, decision: dict[str, Any]) -> None:
        fid = str(decision["face_id"])
        q = self._history.setdefault(fid, deque(maxlen=60))
        q.append(decision)

    def max_p_in_window(self, face_id: str, t0: float, t1: float) -> float | None:
        """Return max p_speaking for face_id overlapping [t0 - guard_ms, t1 + guard_ms]."""
        q = self._history.get(str(face_id))
        if not q:
            return None
        lo = t0 - self.guard_ms
        hi = t1 + self.guard_ms
        vals = [
            float(d["p_speaking"])
            for d in q
            if float(d["window_t1"]) >= lo and float(d["window_t0"]) <= hi
        ]
        if not vals:
            # Fall back to most recent decision if within 2 s
            latest = q[-1]
            if abs(t1 - float(latest["window_t1"])) <= 2500.0:
                return float(latest["p_speaking"])
            return None
        return max(vals)

    def allow_target_segment(self, target_face_id: str | None, t0: float, t1: float) -> tuple[bool, float | None]:
        """Return (allow, max_p_speaking). Drops target-lane words when target is not speaking."""
        if not target_face_id:
            self.passed_count += 1
            return True, None
        max_p = self.max_p_in_window(target_face_id, t0, t1)
        if max_p is None:
            # No decision yet for this face (cold start): do not drop live captions
            self.passed_count += 1
            return True, None
        if max_p >= self.decision_threshold:
            self.passed_count += 1
            return True, max_p
        self.dropped_count += 1
        return False, max_p

    def best_speaking_face(self, t0: float, t1: float) -> tuple[str | None, float]:
        """Return (face_id, p_speaking) with highest speaking probability in [t0, t1]."""
        best_fid: str | None = None
        best_p = -1.0
        for fid in list(self._history.keys()):
            p = self.max_p_in_window(fid, t0, t1)
            if p is not None and p > best_p:
                best_p = p
                best_fid = fid
        return best_fid, max(0.0, best_p)

    def timeline_snapshot(self, since_ms: float | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for q in self._history.values():
            for d in q:
                if since_ms is None or float(d["window_t1"]) >= since_ms:
                    out.append(d)
        out.sort(key=lambda x: float(x["window_t0"]))
        return out
