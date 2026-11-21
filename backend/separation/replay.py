"""FB4 replay fallback: rolling 10 s in-memory ring of hops (cleared on disconnect).

Never writes audio to disk. Used only when the user explicitly triggers REPLAY.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass


@dataclass
class ReplayHop:
    pcm_bytes: bytes
    jpegs: list[bytes]
    target_face_id: str | None
    reset: bool
    t_capture: float


class ReplayRingBuffer:
    """Keeps the last 10 s (~20 hops at 0.5 s) in memory only."""

    def __init__(self, max_hops: int = 20) -> None:
        self._buf: collections.deque[ReplayHop] = collections.deque(maxlen=max_hops)

    def push(
        self,
        *,
        pcm_bytes: bytes,
        jpegs: list[bytes],
        target_face_id: str | None,
        reset: bool,
        t_capture: float,
    ) -> None:
        self._buf.append(
            ReplayHop(
                pcm_bytes=pcm_bytes,
                jpegs=jpegs,
                target_face_id=target_face_id,
                reset=reset,
                t_capture=t_capture,
            )
        )

    def snapshot(self) -> list[ReplayHop]:
        return list(self._buf)

    def clear(self) -> None:
        self._buf.clear()
