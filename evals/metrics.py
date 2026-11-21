"""Evaluation metrics and CSV scorers implementing contracts/eval.md.

Source of truth: SPEC.md, prompts.md, and contracts/eval.md.
Never fabricates numbers: empty datasets return n=0 and None metrics.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import jiwer as _jiwer
except ImportError:  # pragma: no cover
    _jiwer = None


_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def norm_text(text: str | None) -> str:
    """Lowercase, strip punctuation & underscores, collapse whitespace (eval.md §1)."""
    if not text:
        return ""
    s = text.lower()
    s = _PUNCT_RE.sub("", s).replace("_", "")
    return _WS_RE.sub(" ", s).strip()


def norm_words(text: str | None) -> list[str]:
    s = norm_text(text)
    return s.split(" ") if s else []


def _word_edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Exact Levenshtein edit distance on token lists (matches jiwer.wer)."""
    m, n = len(ref), len(hyp)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        ri = ref[i - 1]
        for j in range(1, n + 1):
            cost = 0 if ri == hyp[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[n]


def compute_wer_parts(truth_target: str | None, hyp_text: str | None) -> tuple[float | None, int, int]:
    """Return (wer_or_none, edits, ref_len) per contracts/eval.md §2."""
    ref_s = norm_text(truth_target)
    hyp_s = norm_text(hyp_text)
    ref_w = ref_s.split(" ") if ref_s else []
    hyp_w = hyp_s.split(" ") if hyp_s else []

    if not ref_w:
        if not hyp_w:
            return 0.0, 0, 0
        return None, len(hyp_w), 0

    edits = _word_edit_distance(ref_w, hyp_w)
    if _jiwer is not None:
        wer_val = float(_jiwer.wer(ref_s, hyp_s))
    else:
        wer_val = edits / len(ref_w)
    return wer_val, edits, len(ref_w)


def compute_wer(truth_target: str | None, hyp_text: str | None) -> float | None:
    wer_val, _, _ = compute_wer_parts(truth_target, hyp_text)
    return wer_val


def compute_leakage(
    truth_target: str | None,
    truth_others: str | None,
    hyp_text: str | None,
) -> tuple[float, int, int]:
    """Multiset leakage per contracts/eval.md §3.

    Returns (leakage_rate, leaked_word_count, total_hyp_words).
    Target-matched words are removed before counting residual matches in truth_others.
    """
    hyp_w = norm_words(hyp_text)
    if not hyp_w:
        return 0.0, 0, 0

    target_counts = Counter(norm_words(truth_target))
    other_counts = Counter(norm_words(truth_others))

    residual: list[str] = []
    for w in hyp_w:
        if target_counts[w] > 0:
            target_counts[w] -= 1
        else:
            residual.append(w)

    leaked = 0
    for w in residual:
        if other_counts[w] > 0:
            other_counts[w] -= 1
            leaked += 1

    return leaked / len(hyp_w), leaked, len(hyp_w)


def compute_attribution_accuracy(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Attribution accuracy per contracts/eval.md §4.

    Expects items with {'face_id', 'truth_face_id', 'text'}.
    """
    eligible = [
        s for s in segments
        if s.get("face_id") is not None and norm_text(s.get("text"))
    ]
    if not eligible:
        return {"n": 0, "correct": 0, "accuracy": None}
    correct = sum(1 for s in eligible if str(s.get("face_id")) == str(s.get("truth_face_id")))
    return {"n": len(eligible), "correct": correct, "accuracy": correct / len(eligible)}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    idx = min(len(xs) - 1, max(0, int(round((p / 100.0) * (len(xs) - 1)))))
    return float(xs[idx])


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan"):
        return None
    try:
        v = float(s)
        return None if math.isnan(v) else v
    except ValueError:
        return None


def _to_int(val: Any) -> int | None:
    f = _to_float(val)
    return int(round(f)) if f is not None else None


def _mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def summarize_arm(rows: list[dict[str, str]], prefix: str) -> dict[str, Any]:
    """Compute clip-mean & corpus WER, leakage, and delay for arm prefix ('b0', 'a', 'b')."""
    text_col = f"{prefix}_text"
    wer_col = f"{prefix}_wer"
    leak_col = f"{prefix}_leak"
    time_col = f"{prefix}_time_s"

    clip_wers: list[float] = []
    clip_leaks: list[float] = []
    delays_s: list[float] = []
    total_edits = 0
    total_ref_words = 0
    total_leaked = 0
    total_hyp_words = 0
    scored_clips = 0

    for row in rows:
        truth_t = row.get("truth_target", "")
        truth_o = row.get("truth_others", "")
        hyp = row.get(text_col, "")

        has_text = bool(hyp.strip() or _to_float(row.get(wer_col)) is not None or _to_float(row.get(leak_col)) is not None)
        if not has_text:
            continue
        scored_clips += 1

        if truth_t.strip() or hyp.strip():
            w, edits, rlen = compute_wer_parts(truth_t, hyp)
            lk, lk_n, h_n = compute_leakage(truth_t, truth_o, hyp)
            if w is not None:
                clip_wers.append(w)
            if rlen > 0:
                total_edits += edits
                total_ref_words += rlen
            clip_leaks.append(lk)
            total_leaked += lk_n
            total_hyp_words += h_n
        else:
            w_csv = _to_float(row.get(wer_col))
            lk_csv = _to_float(row.get(leak_col))
            if w_csv is not None:
                clip_wers.append(w_csv)
            if lk_csv is not None:
                clip_leaks.append(lk_csv)

        dt = _to_float(row.get(time_col))
        if dt is not None:
            delays_s.append(dt)

    return {
        "n_clips": scored_clips,
        "n_wer": len(clip_wers),
        "wer_clip_mean": _mean(clip_wers),
        "wer_corpus": (total_edits / total_ref_words) if total_ref_words > 0 else None,
        "leak_clip_mean": _mean(clip_leaks),
        "leak_corpus": (total_leaked / total_hyp_words) if total_hyp_words > 0 else None,
        "delay_p50_s": percentile(delays_s, 50),
        "delay_p95_s": percentile(delays_s, 95),
        "delay_n": len(delays_s),
    }


def check_beats_raw_gate(b0: dict[str, Any], engine: dict[str, Any]) -> dict[str, Any]:
    """SPEC & eval.md §8 gate for claiming 'beats raw captions'."""
    n = min(b0["n_clips"], engine["n_clips"])
    b0_leak = b0["leak_clip_mean"]
    eng_leak = engine["leak_clip_mean"]
    b0_wer = b0["wer_clip_mean"]
    eng_wer = engine["wer_clip_mean"]

    if n < 30 or None in (b0_leak, eng_leak, b0_wer, eng_wer):
        return {
            "passes": False,
            "n_paired": n,
            "leak_drop": (b0_leak - eng_leak) if (b0_leak is not None and eng_leak is not None) else None,
            "wer_delta": (eng_wer - b0_wer) if (b0_wer is not None and eng_wer is not None) else None,
            "reason": f"insufficient clips ({n} < 30)" if n < 30 else "missing metrics",
        }

    leak_drop = b0_leak - eng_leak
    wer_delta = eng_wer - b0_wer
    passes = (leak_drop >= 0.20) and (wer_delta <= 0.05)
    reasons = []
    if leak_drop < 0.20:
        reasons.append(f"leakage drop {leak_drop*100:.1f}pp < 20.0pp")
    if wer_delta > 0.05:
        reasons.append(f"WER regression +{wer_delta*100:.1f}pp > +5.0pp")
    return {
        "passes": passes,
        "n_paired": n,
        "leak_drop": leak_drop,
        "wer_delta": wer_delta,
        "reason": "PASS" if passes else "; ".join(reasons),
    }


def _noise_bucket(val: str) -> str:
    db = _to_float(val)
    if db is None:
        return "unknown"
    if db < 55:
        return "quiet (<55 dB)"
    if db < 70:
        return "moderate (55-70 dB)"
    return "loud hall (>=70 dB)"


def _network_bucket(row: dict[str, str]) -> str:
    notes = (row.get("notes") or "").lower()
    if "hotspot" in notes:
        return "hotspot"
    if "wifi" in notes or "wi-fi" in notes:
        return "wifi"
    return "unspecified"


def slice_where_it_breaks(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Slice Set C by SPEC & eval.md §10 dimensions."""
    dimensions = {
        "talkers": lambda r: (r.get("talkers") or "unknown").strip() or "unknown",
        "angle": lambda r: (r.get("angle") or "unknown").strip().lower() or "unknown",
        "distance_m": lambda r: (r.get("distance_m") or "unknown").strip() or "unknown",
        "noise_level": lambda r: _noise_bucket(r.get("noise_db", "")),
        "occlusion": lambda r: (r.get("occlusion") or "none").strip().lower() or "none",
        "network": _network_bucket,
    }
    out: dict[str, dict[str, Any]] = {}
    for dim, key_fn in dimensions.items():
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            buckets[key_fn(row)].append(row)
        out[dim] = {
            k: {
                "n": len(b_rows),
                "b0": summarize_arm(b_rows, "b0"),
                "a": summarize_arm(b_rows, "a"),
                "b": summarize_arm(b_rows, "b"),
            }
            for k, b_rows in sorted(buckets.items())
        }
    return out


def score_clips_csv(path: Path, recompute_in_place: bool = False) -> dict[str, Any]:
    if not path.exists():
        return {"n_total": 0, "arms": {}, "gates": {}, "where_it_breaks": {}}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if recompute_in_place and rows:
        for row in rows:
            tt = row.get("truth_target", "")
            to = row.get("truth_others", "")
            for prefix in ("b0", "a", "b"):
                hyp = row.get(f"{prefix}_text", "")
                if hyp.strip() or (tt.strip() and row.get(f"{prefix}_text") is not None and row.get(f"{prefix}_wer", "") == ""):
                    if hyp.strip():
                        w = compute_wer(tt, hyp)
                        lk, _, _ = compute_leakage(tt, to, hyp)
                        row[f"{prefix}_wer"] = "" if w is None else f"{w:.4f}"
                        row[f"{prefix}_leak"] = f"{lk:.4f}"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    b0 = summarize_arm(rows, "b0")
    arm_a = summarize_arm(rows, "a")
    arm_b = summarize_arm(rows, "b")

    two_talker = sum(1 for r in rows if _to_int(r.get("talkers")) == 2)
    three_talker = sum(1 for r in rows if _to_int(r.get("talkers")) == 3)

    return {
        "n_total": len(rows),
        "n_two_talker": two_talker,
        "n_three_talker": three_talker,
        "arms": {"b0_raw": b0, "engine_a": arm_a, "engine_b_gpu": arm_b},
        "gates": {
            "engine_b_beats_raw": check_beats_raw_gate(b0, arm_b),
            "engine_a_beats_raw": check_beats_raw_gate(b0, arm_a),
        },
        "where_it_breaks": slice_where_it_breaks(rows),
    }


def score_decisions_csv(path: Path, threshold: float = 0.9) -> dict[str, Any]:
    """Score Set D speaking decisions per contracts/eval.md §6."""
    if not path.exists():
        return {"n": 0, "accuracy": None, "latency_p50_ms": None, "ece": None, "bins": []}
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    correct = 0
    total = 0
    latencies: list[float] = []
    bin_preds: list[list[float]] = [[] for _ in range(10)]
    bin_truths: list[list[int]] = [[] for _ in range(10)]

    for row in rows:
        truth_raw = str(row.get("truth_speaking", "")).strip().lower()
        if truth_raw in ("1", "true", "yes"):
            truth = 1
        elif truth_raw in ("0", "false", "no"):
            truth = 0
        else:
            continue
        p = _to_float(row.get("p_decision"))
        if p is None:
            continue
        p = min(1.0, max(0.0, p))
        total += 1
        pred = 1 if p >= threshold else 0
        if pred == truth:
            correct += 1

        lat = _to_float(row.get("latency_ms"))
        if lat is not None:
            latencies.append(lat)

        b_idx = min(9, int(p * 10))
        bin_preds[b_idx].append(p)
        bin_truths[b_idx].append(truth)

    bins: list[dict[str, Any]] = []
    ece = 0.0
    for i in range(10):
        cnt = len(bin_preds[i])
        mean_p = _mean(bin_preds[i])
        emp_rate = (sum(bin_truths[i]) / cnt) if cnt else None
        if cnt and total and mean_p is not None and emp_rate is not None:
            ece += (cnt / total) * abs(emp_rate - mean_p)
        bins.append({
            "bin_start": round(i * 0.1, 1),
            "bin_end": round((i + 1) * 0.1, 1),
            "count": cnt,
            "mean_p": mean_p,
            "empirical_rate": emp_rate,
        })

    p50 = percentile(latencies, 50)
    acc = (correct / total) if total else None
    at8_pass = bool(total >= 20 and acc is not None and acc >= 0.9 and p50 is not None and p50 <= 300.0)
    return {
        "n": total,
        "correct": correct,
        "threshold": threshold,
        "accuracy": acc,
        "latency_p50_ms": p50,
        "latency_p95_ms": percentile(latencies, 95),
        "ece": ece if total else None,
        "at8_pass": at8_pass,
        "bins": bins,
    }


def score_robot_csv(path: Path) -> dict[str, Any]:
    """Score Set R conflicting robot commands per contracts/eval.md §7."""
    if not path.exists():
        return {"n": 0, "point_correct": 0, "point_accuracy": None, "hook_denied": 0, "hook_block_rate": None, "at12_pass": False}
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    total = 0
    point_ok = 0
    hook_ok = 0
    latencies: list[float] = []
    for row in rows:
        if not (row.get("pair_id") or "").strip():
            continue
        total += 1
        if str(row.get("correct", "")).strip().lower() in ("1", "true", "yes"):
            point_ok += 1
        if str(row.get("hook_denied_other", "")).strip().lower() in ("1", "true", "yes"):
            hook_ok += 1
        lat = _to_float(row.get("latency_ms"))
        if lat is not None:
            latencies.append(lat)

    point_acc = (point_ok / total) if total else None
    hook_rate = (hook_ok / total) if total else None
    at12_pass = bool(total >= 10 and point_ok / total >= 0.8 and hook_ok == total)
    return {
        "n": total,
        "point_correct": point_ok,
        "point_accuracy": point_acc,
        "hook_denied": hook_ok,
        "hook_block_rate": hook_rate,
        "latency_p50_ms": percentile(latencies, 50),
        "at12_pass": at12_pass,
    }


_TEST_SESSION_PREFIXES = ("verify", "test", "g7", "eval", "offline", "bench", "sim", "dry")


def classify_hop_mode(rec: dict[str, Any]) -> str:
    """Return 'live' or 'test' for a logs/hops.jsonl record."""
    mode = str(rec.get("mode") or "").strip().lower()
    if mode in ("live", "test"):
        return mode
    sid = str(rec.get("session_id") or "").strip().lower()
    if not sid or sid == "system" or any(sid.startswith(p) for p in _TEST_SESSION_PREFIXES):
        return "test"
    return "live"


def summarize_voice_delay(hops_path: Path, *, live_only: bool = True) -> dict[str, Any]:
    """Summarize live voice delay from logs/hops.jsonl per contracts/eval.md §5.1.

    Counts only mode=='live' sessions by default (excludes S1 verify/test runs).
    """
    if not hops_path.exists():
        return {
            "n_hops": 0,
            "n_hops_live": 0,
            "n_hops_test": 0,
            "voice_delay_p50_ms": None,
            "voice_delay_p95_ms": None,
            "rtt_p50_ms": None,
            "rtt_p95_ms": None,
            "gpu_p50_ms": None,
            "max_gap_ms": None,
            "at4_delay_pass": False,
        }

    voice_delays: list[float] = []
    rtts: list[float] = []
    gpus: list[float] = []
    gaps: list[float] = []
    n_test = 0
    n_live = 0

    for line in hops_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Skip non-hop system/event status rows (e.g. engine_ready, failover, dropped_stale)
        status = rec.get("status")
        if status is not None and status != "ok":
            continue

        mode = classify_hop_mode(rec)
        if mode == "test":
            n_test += 1
            if live_only:
                continue
        else:
            n_live += 1

        rtt = _to_float(rec.get("rtt_ms"))
        if rtt is None and rec.get("t_return") is not None and rec.get("t_capture") is not None:
            t_ret = _to_float(rec.get("t_return"))
            t_cap = _to_float(rec.get("t_capture"))
            if t_ret is not None and t_cap is not None:
                diff = t_ret - t_cap
                rtt = diff * 1000.0 if diff < 100 else diff
        if rtt is not None:
            rtts.append(rtt)

        vd = _to_float(rec.get("voice_delay_ms"))
        if vd is None and rtt is not None:
            hop_ms = _to_float(rec.get("hop_collect_ms") or rec.get("hop_ms")) or 500.0
            buf_ms = _to_float(rec.get("playback_buf_ms")) or 150.0
            vd = hop_ms + rtt + buf_ms
        if vd is not None:
            voice_delays.append(vd)

        gpu = _to_float(rec.get("gpu_ms"))
        if gpu is not None:
            gpus.append(gpu)

        gap = _to_float(rec.get("gap_ms"))
        if gap is not None:
            gaps.append(gap)

    p50_vd = percentile(voice_delays, 50)
    max_gap = max(gaps) if gaps else None
    return {
        "n_hops": len(voice_delays) or len(rtts),
        "n_hops_live": n_live,
        "n_hops_test": n_test,
        "voice_delay_p50_ms": p50_vd,
        "voice_delay_p95_ms": percentile(voice_delays, 95),
        "rtt_p50_ms": percentile(rtts, 50),
        "rtt_p95_ms": percentile(rtts, 95),
        "gpu_p50_ms": percentile(gpus, 50),
        "max_gap_ms": max_gap,
        "at4_delay_pass": bool(p50_vd is not None and p50_vd <= 1500.0 and (max_gap is None or max_gap <= 300.0)),
    }


def regression_check(before: dict[str, float], after: dict[str, float]) -> tuple[bool, str]:
    """contracts/eval.md §9 regression gate rule for gate_release.py."""
    checks = [
        ("leakage", before["leakage"], after["leakage"]),
        ("wer", before["wer"], after["wer"]),
        ("delay_p50_ms", before["delay_p50_ms"], after["delay_p50_ms"]),
    ]
    worse = [
        f"{name}: {b:.4f} -> {a:.4f}"
        for name, b, a in checks
        if a > b + 1e-9
    ]
    summary = ", ".join(f"{name} {b:.4f}->{a:.4f}" for name, b, a in checks)
    if worse:
        return False, f"REGRESSION DENIED ({'; '.join(worse)}). All metrics: {summary}"
    return True, f"ALLOW ({summary})"
