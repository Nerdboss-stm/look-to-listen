"""Append-only logger for logs/hops.jsonl and live rolling delay metrics."""

from __future__ import annotations

import collections
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HOPS_LOG_PATH = REPO_ROOT / "logs" / "hops.jsonl"


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    idx = min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))
    return round(float(xs[idx]), 1)


class HopLogger:
    """Thread-safe append-only writer for logs/hops.jsonl plus rolling p50/p95 stats."""

    def __init__(self, path: Path | None = None, window: int = 120) -> None:
        self.path = path or HOPS_LOG_PATH
        self._lock = threading.Lock()
        self._gpu_ms: collections.deque[float] = collections.deque(maxlen=window)
        self._queue_ms: collections.deque[float] = collections.deque(maxlen=window)
        self._rtt_ms: collections.deque[float] = collections.deque(maxlen=window)
        self._gpu_rtt_ms: collections.deque[float] = collections.deque(maxlen=window)
        self._voice_delay_ms: collections.deque[float] = collections.deque(maxlen=window)
        self.hops_ok = 0
        self.hops_dropped = 0
        self.hops_error = 0
        self.hops_merged = 0
        self._last_gpu_ms: float | None = None
        self._last_rtt_ms: float | None = None
        self._last_voice_delay_ms: float | None = None
        self._last_n_crops: int | None = None

    def _write_record(self, rec: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def log_result(
        self,
        *,
        session_id: str,
        seq: int,
        covers: list[int] | None,
        target_face_id: str | None,
        reset: bool,
        engine: str,
        hop_ms: int,
        t_capture: float | None,
        t_send_ms: float | None,
        t_return_ms: float,
        gpu_ms: float,
        queue_ms: float,
        gpu_rtt_ms: float,
        rtt_ms: float,
        playback_buf_ms: float,
        samples: int,
        n_crops: int = 0,
    ) -> dict[str, Any]:
        voice_delay_ms = round(float(hop_ms) + float(rtt_ms) + float(playback_buf_ms), 1)
        merged = 0
        if covers and len(covers) == 2:
            merged = max(0, int(covers[1]) - int(covers[0]))

        rec: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "seq": int(seq),
            "covers": covers or [int(seq), int(seq)],
            "target_face_id": target_face_id,
            "n_crops": int(n_crops),
            "reset": bool(reset),
            "engine": engine,
            "status": "ok",
            "hop_ms": int(hop_ms),
            "t_capture": round(float(t_capture), 1) if t_capture is not None else None,
            "t_send": round(float(t_send_ms), 1) if t_send_ms is not None else None,
            "t_return": round(float(t_return_ms), 1),
            "gpu_ms": round(float(gpu_ms), 1),
            "queue_ms": round(float(queue_ms), 1),
            "gpu_rtt_ms": round(float(gpu_rtt_ms), 1),
            "rtt_ms": round(float(rtt_ms), 1),
            "playback_buf_ms": round(float(playback_buf_ms), 1),
            "voice_delay_ms": voice_delay_ms,
            "samples": int(samples),
            "merged": merged,
        }
        with self._lock:
            self.hops_ok += 1
            self.hops_merged += merged
            self._gpu_ms.append(rec["gpu_ms"])
            self._queue_ms.append(rec["queue_ms"])
            self._rtt_ms.append(rec["rtt_ms"])
            self._gpu_rtt_ms.append(rec["gpu_rtt_ms"])
            self._voice_delay_ms.append(voice_delay_ms)
            self._last_gpu_ms = rec["gpu_ms"]
            self._last_rtt_ms = rec["rtt_ms"]
            self._last_voice_delay_ms = voice_delay_ms
            self._last_n_crops = int(n_crops)
        self._write_record(rec)
        return rec

    def log_drop(
        self,
        *,
        session_id: str,
        seq: int,
        target_face_id: str | None,
        engine: str,
        hop_ms: int,
        t_capture: float | None,
        age_ms: float,
        reason: str = "stale_hop",
        n_crops: int = 0,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "seq": int(seq),
            "target_face_id": target_face_id,
            "n_crops": int(n_crops),
            "engine": engine,
            "status": "dropped_stale",
            "hop_ms": int(hop_ms),
            "t_capture": round(float(t_capture), 1) if t_capture is not None else None,
            "t_return": round(time.time() * 1000.0, 1),
            "age_ms": round(float(age_ms), 1),
            "reason": reason,
        }
        with self._lock:
            self.hops_dropped += 1
        self._write_record(rec)
        return rec

    def log_event(
        self,
        *,
        session_id: str,
        engine: str,
        status: str,
        reason: str,
        seq: int | None = None,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "seq": seq,
            "engine": engine,
            "status": status,
            "reason": reason,
        }
        if status == "error":
            with self._lock:
                self.hops_error += 1
        self._write_record(rec)
        return rec

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            gpu = list(self._gpu_ms)
            queue = list(self._queue_ms)
            rtt = list(self._rtt_ms)
            gpu_rtt = list(self._gpu_rtt_ms)
            vd = list(self._voice_delay_ms)
            return {
                "hops_ok": self.hops_ok,
                "hops_dropped": self.hops_dropped,
                "hops_error": self.hops_error,
                "hops_merged": self.hops_merged,
                "last_gpu_ms": self._last_gpu_ms,
                "last_rtt_ms": self._last_rtt_ms,
                "last_voice_delay_ms": self._last_voice_delay_ms,
                "last_n_crops": self._last_n_crops,
                "gpu_p50_ms": _percentile(gpu, 50),
                "gpu_p95_ms": _percentile(gpu, 95),
                "queue_p50_ms": _percentile(queue, 50),
                "rtt_p50_ms": _percentile(rtt, 50),
                "rtt_p95_ms": _percentile(rtt, 95),
                "gpu_rtt_p50_ms": _percentile(gpu_rtt, 50),
                "voice_delay_p50_ms": _percentile(vd, 50),
                "voice_delay_p95_ms": _percentile(vd, 95),
            }


def read_hops_stats_from_disk(path: Path | None = None) -> dict[str, Any]:
    """Compute aggregate voice delay p50/p95 and count directly from logs/hops.jsonl."""
    p = path or HOPS_LOG_PATH
    if not p.exists():
        return {
            "voice_p50_ms": None,
            "voice_p95_ms": None,
            "gpu_p50_ms": None,
            "rtt_p50_ms": None,
            "hops_logged": 0,
        }
    voice_delays: list[float] = []
    gpu_vals: list[float] = []
    rtt_vals: list[float] = []
    hops_logged = 0
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("status") != "ok":
                    continue
                hops_logged += 1
                vd = rec.get("voice_delay_ms")
                if isinstance(vd, (int, float)):
                    voice_delays.append(float(vd))
                gm = rec.get("gpu_ms")
                if isinstance(gm, (int, float)):
                    gpu_vals.append(float(gm))
                rm = rec.get("rtt_ms")
                if isinstance(rm, (int, float)):
                    rtt_vals.append(float(rm))
    except OSError:
        pass
    return {
        "voice_p50_ms": _percentile(voice_delays, 50),
        "voice_p95_ms": _percentile(voice_delays, 95),
        "gpu_p50_ms": _percentile(gpu_vals, 50),
        "rtt_p50_ms": _percentile(rtt_vals, 50),
        "hops_logged": hops_logged,
    }
