"""Reads clips.csv, decisions.csv, robot.csv, and logs/hops.jsonl to produce EndCardData.

Strictly obeys AGENTS.md:
Never show a number on screen that does not come from the CSV files or the live logs.
Never claim "beats the baseline" unless the gate rules in SPEC pass.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.separation.hop_logger import read_hops_stats_from_disk

REPO_ROOT = Path(__file__).resolve().parents[2]


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "nan", "na"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _mean_pct(vals: list[float]) -> float | None:
    if not vals:
        return None
    avg = sum(vals) / len(vals)
    # Normalize ratio [0..1] vs percentage [0..100] cleanly: CSV eval stores 0..1 or 0..100
    # SPEC/eval.md defines WER and leakage in [0.0, 1.0]; convert to 0..100% if max <= 1.0
    if max(vals) <= 1.0 and min(vals) >= 0.0:
        avg *= 100.0
    return round(avg, 1)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    xs = sorted(vals)
    return round(float(xs[len(xs) // 2]), 1)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return [row for row in csv.DictReader(f) if any(v.strip() for v in row.values() if v)]
    except OSError:
        return []


_LEAKAGE_CACHE: dict[Path, tuple[tuple[int, int], tuple[float | None, float | None, int]]] = {}


def read_live_leakage_from_csv(repo_root: Path | None = None) -> tuple[float | None, float | None, int]:
    """Returns (raw_leakage_pct, target_leakage_pct, n_clips) from clips.csv (cached by mtime+size)."""
    root = repo_root or REPO_ROOT
    csv_path = root / "clips.csv"
    try:
        st = csv_path.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None, None, 0
    cached = _LEAKAGE_CACHE.get(csv_path)
    if cached is not None and cached[0] == key:
        return cached[1]
    rows = _read_csv_rows(csv_path)
    b0_leaks = [v for r in rows if (v := _to_float(r.get("b0_leak"))) is not None]
    b_leaks = [v for r in rows if (v := _to_float(r.get("b_leak"))) is not None]
    if not b_leaks:
        b_leaks = [v for r in rows if (v := _to_float(r.get("a_leak"))) is not None]
    result = (_mean_pct(b0_leaks), _mean_pct(b_leaks), len(rows))
    _LEAKAGE_CACHE[csv_path] = (key, result)
    return result


def build_end_card_data(repo_root: Path | None = None) -> dict[str, Any]:
    """Compute EndCardData strictly matching frontend/src/types/contracts.ts."""
    root = repo_root or REPO_ROOT
    clip_rows = _read_csv_rows(root / "clips.csv")
    dec_rows = _read_csv_rows(root / "decisions.csv")
    rob_rows = _read_csv_rows(root / "robot.csv")
    hops_stats = read_hops_stats_from_disk(root / "logs" / "hops.jsonl")

    # Set C
    b0_leaks = [v for r in clip_rows if (v := _to_float(r.get("b0_leak"))) is not None]
    b0_wers = [v for r in clip_rows if (v := _to_float(r.get("b0_wer"))) is not None]
    a_leaks = [v for r in clip_rows if (v := _to_float(r.get("a_leak"))) is not None]
    a_wers = [v for r in clip_rows if (v := _to_float(r.get("a_wer"))) is not None]
    b_leaks = [v for r in clip_rows if (v := _to_float(r.get("b_leak"))) is not None]
    b_wers = [v for r in clip_rows if (v := _to_float(r.get("b_wer"))) is not None]
    b_times_ms = [v * 1000.0 for r in clip_rows if (v := _to_float(r.get("b_time_s"))) is not None]

    b0_leak_pct = _mean_pct(b0_leaks)
    b0_wer_pct = _mean_pct(b0_wers)
    a_leak_pct = _mean_pct(a_leaks)
    a_wer_pct = _mean_pct(a_wers)
    b_leak_pct = _mean_pct(b_leaks)
    b_wer_pct = _mean_pct(b_wers)

    # Gate rule (SPEC & eval.md):
    # n >= 30 AND leakage drops >= 20 percentage points AND WER <= 5 points worse
    beats_raw_gate_passed = False
    if (
        len(clip_rows) >= 30
        and b0_leak_pct is not None
        and b_leak_pct is not None
        and b0_wer_pct is not None
        and b_wer_pct is not None
    ):
        beats_raw_gate_passed = (
            (b0_leak_pct - b_leak_pct) >= 20.0 and (b_wer_pct - b0_wer_pct) <= 5.0
        )

    # Set D
    d_correct = 0
    d_total = 0
    d_lats: list[float] = []
    for r in dec_rows:
        truth = _to_float(r.get("truth_speaking"))
        prob = _to_float(r.get("p_decision"))
        lat = _to_float(r.get("latency_ms"))
        if lat is not None:
            d_lats.append(lat)
        if truth is not None and prob is not None:
            d_total += 1
            if (prob >= 0.9) == bool(int(round(truth))):
                d_correct += 1

    # Set R
    r_correct = sum(1 for r in rob_rows if (_to_float(r.get("correct")) or 0) >= 1)
    r_denied = sum(1 for r in rob_rows if (_to_float(r.get("hook_denied_other")) or 0) >= 1)

    # Where it breaks slices
    slices: list[dict[str, Any]] = []
    slice_dims = [
        ("talkers", "talkers"),
        ("angle", "angle"),
        ("distance_m", "distance"),
        ("occlusion", "occlusion"),
    ]
    for col, label in slice_dims:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in clip_rows:
            val = (r.get(col) or "").strip()
            if val:
                grouped[val].append(r)
        for cond, grp in sorted(grouped.items()):
            g_b0 = [v for r in grp if (v := _to_float(r.get("b0_leak"))) is not None]
            g_bl = [v for r in grp if (v := _to_float(r.get("b_leak"))) is not None]
            g_bw = [v for r in grp if (v := _to_float(r.get("b_wer"))) is not None]
            g_bt = [v * 1000.0 for r in grp if (v := _to_float(r.get("b_time_s"))) is not None]
            slices.append(
                {
                    "slice": label,
                    "condition": cond,
                    "n": len(grp),
                    "raw_leak_pct": _mean_pct(g_b0),
                    "target_leak_pct": _mean_pct(g_bl),
                    "target_wer_pct": _mean_pct(g_bw),
                    "delay_p50_ms": _median(g_bt),
                }
            )

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "set_c": {
            "n_clips": len(clip_rows),
            "b0_leak_pct": b0_leak_pct,
            "b0_wer_pct": b0_wer_pct,
            "engine_a_leak_pct": a_leak_pct,
            "engine_a_wer_pct": a_wer_pct,
            "engine_b_leak_pct": b_leak_pct,
            "engine_b_wer_pct": b_wer_pct,
            "beats_raw_gate_passed": beats_raw_gate_passed,
        },
        "set_d": {
            "n_windows": len(dec_rows),
            "accuracy_at_0_9_pct": round((d_correct / d_total) * 100.0, 1) if d_total else None,
            "latency_p50_ms": _median(d_lats),
        },
        "set_r": {
            "n_pairs": len(rob_rows),
            "point_correct": r_correct,
            "hook_denied_other": r_denied,
        },
        "delay": {
            "voice_p50_ms": hops_stats["voice_p50_ms"],
            "voice_p95_ms": hops_stats["voice_p95_ms"],
            "caption_p50_ms": _median(b_times_ms),
            "hops_logged": hops_stats["hops_logged"],
        },
        "where_it_breaks": slices,
        "repo_url": os.environ.get("REPO_URL", "https://github.com/saran/look-to-listen"),
    }
