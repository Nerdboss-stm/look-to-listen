"""Engine A: Gemini-only live target captioner (2 s AV chunks with green target box).

Used as:
- Live fallback when GPU separation fails or disconnects (AT14 failover within 3 s).
- Comparison arm on Set C clips (G4 & E27).
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections import deque
from typing import Any

import cv2
import numpy as np
from google.genai import types

from backend.gemini.client import MODELS, extract_usage, get_client
from backend.gemini.decisions import build_av_mp4_bytes
from backend.gemini.logger import log_model_call

ENGINE_A_PROMPT = (
    "Two or more people may be talking at the same time. "
    "Transcribe only the words spoken by the person inside the green box. "
    "Use their lip movements to decide which words are theirs. "
    "Return only those words. If the person in the box is silent, return an empty string."
)


def draw_green_target_box(frame_jpeg: bytes, box: dict[str, float] | None) -> bytes:
    """Draw a high-contrast green bounding box on the target face (normalized [0,1] box)."""
    arr = np.frombuffer(frame_jpeg, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return frame_jpeg
    if box:
        h, w = img.shape[:2]
        x0 = max(0, min(w - 1, int(float(box.get("x", 0.0)) * w)))
        y0 = max(0, min(h - 1, int(float(box.get("y", 0.0)) * h)))
        bw = max(4, int(float(box.get("w", 0.2)) * w))
        bh = max(4, int(float(box.get("h", 0.2)) * h))
        x1 = min(w - 1, x0 + bw)
        y1 = min(h - 1, y0 + bh)
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 0), 4)
    ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return enc.tobytes() if ok else frame_jpeg


def transcribe_engine_a_mp4_sync(
    mp4_bytes: bytes,
    *,
    model: str | None = None,
    purpose: str = "engine_a_chunk",
) -> tuple[str, float]:
    """Send a 2 s AV MP4 chunk (with green box on target face) to gemini-4-hydrogen (thinking LOW)."""
    model_id = model or MODELS.hydrogen
    client = get_client()
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=model_id,
            contents=[
                types.Part.from_bytes(data=mp4_bytes, mime_type="video/mp4"),
                ENGINE_A_PROMPT,
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


class EngineALiveBuffer:
    """Accumulates 4 x 0.5 s hops (= 2 s AV chunk) and transcribes target when Engine A is active."""

    def __init__(self, *, chunk_hops: int = 4) -> None:
        self.chunk_hops = chunk_hops
        self._pcm_hops: deque[bytes] = deque(maxlen=chunk_hops)
        self._frames: deque[bytes] = deque(maxlen=chunk_hops * 4)
        self._t0_ms: float | None = None
        self._target_face_id: str | None = None
        self._in_flight = False

    def reset(self) -> None:
        self._pcm_hops.clear()
        self._frames.clear()
        self._t0_ms = None

    def push_hop(
        self,
        *,
        pcm_bytes: bytes,
        frame_jpeg_b64: str | None,
        faces: list[dict[str, Any]],
        target_face_id: str | None,
        t_capture_ms: float,
        reset: bool = False,
    ) -> dict[str, Any] | None:
        """Buffer a 0.5 s hop; returns a ready 2 s chunk payload when full (drops if busy)."""
        if reset or (target_face_id and target_face_id != self._target_face_id):
            self.reset()
            self._target_face_id = target_face_id

        if self._t0_ms is None:
            self._t0_ms = t_capture_ms
        self._pcm_hops.append(pcm_bytes)

        target_box = None
        if target_face_id:
            for f in faces:
                if str(f.get("id")) == str(target_face_id):
                    target_box = f.get("box")
                    break

        if frame_jpeg_b64:
            try:
                raw_jpg = base64.b64decode(frame_jpeg_b64)
                boxed = draw_green_target_box(raw_jpg, target_box)
                self._frames.append(boxed)
            except Exception:
                pass

        if len(self._pcm_hops) < self.chunk_hops:
            return None

        if self._in_flight:
            # Never queue stale chunks
            self.reset()
            return None

        pcm_2s = b"".join(self._pcm_hops)
        frames = list(self._frames)
        t0 = self._t0_ms or t_capture_ms
        t1 = t_capture_ms + 500.0
        fid = self._target_face_id
        self.reset()
        return {
            "pcm": pcm_2s,
            "frames": frames,
            "t0": t0,
            "t1": t1,
            "target_face_id": fid,
        }

    async def process_chunk(self, chunk: dict[str, Any]) -> dict[str, Any] | None:
        if not chunk.get("frames") or not chunk.get("pcm"):
            return None
        self._in_flight = True
        try:
            fps = max(1.0, len(chunk["frames"]) / 2.0)
            mp4 = await asyncio.to_thread(
                build_av_mp4_bytes, chunk["frames"], chunk["pcm"], fps=fps
            )
            text, lat_ms = await asyncio.to_thread(
                transcribe_engine_a_mp4_sync, mp4, purpose="engine_a_live"
            )
            if not text:
                return None
            return {
                "t0": round(float(chunk["t0"]), 1),
                "t1": round(float(chunk["t1"]), 1),
                "lane": "target",
                "face_id": chunk.get("target_face_id"),
                "text": text,
                "confidence": 0.80,
                "engine": "A",
                "is_final": True,
                "latency_ms": round(lat_ms, 1),
            }
        finally:
            self._in_flight = False
