"""Unit tests for evals/metrics.py and evals/score_all.py against contracts/eval.md."""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics
import score_all


def test_normalization():
    assert metrics.norm_text("Hello, World!  It's_a-test...") == "hello world itsatest"
    assert metrics.norm_words("  One,   two! THREE? ") == ["one", "two", "three"]
    assert metrics.norm_words("") == []
    assert metrics.norm_words(None) == []


def test_wer_standard_and_empty_edge_cases():
    assert metrics.compute_wer("hello world", "hello world") == 0.0
    assert metrics.compute_wer("Hello, world!", "hello world") == 0.0
    assert math.isclose(metrics.compute_wer("one two three four", "one two X four"), 0.25)
    # Empty reference edge cases per contracts/eval.md §2
    assert metrics.compute_wer("", "") == 0.0
    assert metrics.compute_wer("   ", "...") == 0.0
    assert metrics.compute_wer("", "leaked words") is None


def test_multiset_leakage_target_priority():
    # "the" appears once in target and once in other -> credited to target, NOT leaked
    rate, leaked, total = metrics.compute_leakage(
        truth_target="the cat sat",
        truth_others="the dog ran",
        hyp_text="the cat dog",
    )
    assert (leaked, total) == (1, 3)
    assert math.isclose(rate, 1 / 3)

    # Second "the" exceeds target count (1) and matches other count (1) -> leaked
    rate2, leaked2, total2 = metrics.compute_leakage(
        truth_target="the cat",
        truth_others="the dog",
        hyp_text="the the cat",
    )
    assert (leaked2, total2) == (1, 3)
    assert math.isclose(rate2, 1 / 3)

    # Empty hypothesis -> 0.0 leakage
    assert metrics.compute_leakage("hello", "world", "") == (0.0, 0, 0)


def test_beats_raw_gate_boundaries():
    b0 = {"n_clips": 30, "leak_clip_mean": 0.45, "wer_clip_mean": 0.20}
    # Passes exact boundary: leak drop 0.20, wer delta +0.05, n=30
    eng_ok = {"n_clips": 30, "leak_clip_mean": 0.25, "wer_clip_mean": 0.25}
    assert metrics.check_beats_raw_gate(b0, eng_ok)["passes"] is True

    # Fails if n < 30
    eng_n29 = {"n_clips": 29, "leak_clip_mean": 0.05, "wer_clip_mean": 0.10}
    assert metrics.check_beats_raw_gate(b0, eng_n29)["passes"] is False

    # Fails if leak drop < 20pp
    eng_leak = {"n_clips": 35, "leak_clip_mean": 0.26, "wer_clip_mean": 0.15}
    assert metrics.check_beats_raw_gate(b0, eng_leak)["passes"] is False

    # Fails if WER > 5pp worse
    eng_wer = {"n_clips": 35, "leak_clip_mean": 0.05, "wer_clip_mean": 0.26}
    assert metrics.check_beats_raw_gate(b0, eng_wer)["passes"] is False


def test_regression_gate():
    before = {"leakage": 0.12, "wer": 0.20, "delay_p50_ms": 1800.0}
    ok, _ = metrics.regression_check(before, {"leakage": 0.10, "wer": 0.20, "delay_p50_ms": 1750.0})
    assert ok is True
    bad, msg = metrics.regression_check(before, {"leakage": 0.10, "wer": 0.22, "delay_p50_ms": 1700.0})
    assert bad is False
    assert "wer" in msg


def test_end_to_end_scoring_and_charts(tmp_path: Path):
    # Create synthetic Set C, D, R, hops.jsonl, gate_log.csv in tmp_path
    with (tmp_path / "clips.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "clip_id", "time_et", "talkers", "target_face", "distance_m", "angle", "noise_db",
            "occlusion", "consent_ids", "truth_target", "truth_others",
            "b0_text", "b0_wer", "b0_leak",
            "a_text", "a_wer", "a_leak", "a_time_s",
            "b_text", "b_wer", "b_leak", "b_time_s", "notes",
        ])
        w.writerow([
            "c01", "12:00", "2", "0", "1", "front", "62", "none", "p1;p2",
            "hello world today", "goodbye moon tomorrow",
            "hello world today goodbye moon tomorrow", "", "",
            "hello world today moon", "", "", "2.4",
            "hello world today", "", "", "1.8", "wifi",
        ])

    with (tmp_path / "decisions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "face_id", "window_t0", "window_t1", "truth_speaking", "p_decision", "latency_ms", "notes"])
        for i in range(20):
            speaking = 1 if i < 10 else 0
            p = 0.95 if speaking else 0.05
            w.writerow(["c01", "0", i * 0.5, (i + 1) * 0.5, speaking, p, 180, ""])

    with (tmp_path / "robot.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pair_id", "time_et", "target_face", "target_command", "other_command", "object_truth", "point_object", "correct", "hook_denied_other", "latency_ms", "notes"])
        for i in range(10):
            w.writerow([f"r{i}", "14:00", "0", "hand me bottle", "hand me phone", "bottle", "bottle" if i < 9 else "cup", 1 if i < 9 else 0, 1, 420, ""])

    (tmp_path / "logs").mkdir()
    with (tmp_path / "logs/hops.jsonl").open("w") as f:
        # Test/verify hops must be excluded from live voice delay stats
        for seq in range(3):
            f.write(json.dumps({
                "session_id": "verify-e7-e9-123",
                "mode": "test",
                "status": "ok",
                "seq": seq,
                "rtt_ms": 9999,
                "gpu_ms": 999,
                "hop_ms": 500,
                "playback_buf_ms": 150,
            }) + "\n")
        for seq in range(5):
            f.write(json.dumps({
                "session_id": "live-room-1",
                "mode": "live",
                "status": "ok",
                "seq": seq,
                "rtt_ms": 220 + seq * 10,
                "gpu_ms": 130,
                "hop_collect_ms": 500,
                "playback_buf_ms": 150,
            }) + "\n")

    summary = score_all.build_summary(tmp_path, recompute_clips=True)
    assert summary["set_c"]["n_total"] == 1
    assert math.isclose(summary["set_c"]["arms"]["b0_raw"]["leak_clip_mean"], 0.5)
    assert math.isclose(summary["set_c"]["arms"]["engine_b_gpu"]["leak_clip_mean"], 0.0)
    assert math.isclose(summary["set_c"]["arms"]["engine_b_gpu"]["wer_clip_mean"], 0.0)
    assert summary["set_d"]["at8_pass"] is True
    assert summary["set_r"]["at12_pass"] is True
    assert summary["voice_delay"]["n_hops"] == 5
    assert summary["voice_delay"]["n_hops_test"] == 3
    assert math.isclose(summary["voice_delay"]["voice_delay_p50_ms"], 890.0)

    charts = tmp_path / "evals/charts"
    score_all.render_calibration_svg(summary["set_d"], charts / "calibration.svg")
    score_all.render_arms_svg(summary["set_c"], charts / "arms_comparison.svg")
    score_all.render_where_it_breaks_svg(summary["set_c"], charts / "where_it_breaks.svg")
    assert (charts / "calibration.svg").read_text().startswith("<svg")
    assert (charts / "arms_comparison.svg").read_text().startswith("<svg")
    assert (charts / "where_it_breaks.svg").read_text().startswith("<svg")
