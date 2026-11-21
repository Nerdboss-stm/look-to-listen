"""Tests for evals/clip_io.py, evals/run_arms.py, and evals/record_set_c.py."""
from __future__ import annotations

import asyncio
import csv
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "evals"))

import clip_io
import record_set_c
import run_arms
import score_all


def _make_dummy_frame(h: int = 240, w: int = 320) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(img, (w // 2, h // 2), 45, (180, 160, 140), -1)
    return img


def test_clearvoice_crop_geometry_and_edge_padding():
    frame = _make_dummy_frame(240, 320)
    jpg = clip_io.extract_clearvoice_crop_jpeg(frame, {"x": 0.01, "y": 0.01, "w": 0.25, "h": 0.30})
    dec = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert dec is not None
    assert dec.shape == (112, 112), f"Expected 112x112 grayscale crop, got {dec.shape}"


def test_hops_jsonl_roundtrip_and_upsert_csv(tmp_path: Path):
    frame = _make_dummy_frame()
    crop = clip_io.extract_clearvoice_crop_jpeg(frame, {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.4})
    fjpg = clip_io.encode_frame_jpeg(frame)
    pcm = (np.zeros(clip_io.HOP_SAMPLES, dtype="<i2")).tobytes()

    hops = [
        clip_io.ClipHop(
            seq=i,
            session_id="eval-c01",
            target_face_id="face_0",
            reset=(i == 0),
            pcm_bytes=pcm,
            crops_jpegs=[crop] * (12 if i % 2 == 0 else 13),
            frame_jpeg=fjpg,
            faces=[{"id": "face_0", "box": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.4}, "mouth_open": 0.2}],
            t_capture=i * 500.0,
        )
        for i in range(4)
    ]
    hp = tmp_path / "hops.jsonl"
    clip_io.save_hops_jsonl(hp, hops)
    loaded = clip_io.load_hops_jsonl(hp)
    assert len(loaded) == 4
    assert len(loaded[0].pcm_bytes) == clip_io.HOP_BYTES
    assert len(loaded[0].crops_jpegs) == 12
    assert len(loaded[1].crops_jpegs) == 13
    assert loaded[0].reset is True and loaded[1].reset is False

    csv_p = tmp_path / "clips.csv"
    clip_io.upsert_clips_csv(csv_p, {"clip_id": "c01", "talkers": 2, "consent_ids": "P01;P02"})
    clip_io.upsert_clips_csv(csv_p, {"clip_id": "c02", "talkers": 3, "consent_ids": "P01;P02;P03"})
    clip_io.upsert_clips_csv(csv_p, {"clip_id": "c01", "b_wer": "0.0000", "b_leak": "0.0000"})
    rows = list(csv.DictReader(csv_p.open()))
    assert len(rows) == 2
    assert rows[0]["clip_id"] == "c01"
    assert rows[0]["consent_ids"] == "P01;P02"
    assert rows[0]["b_wer"] == "0.0000"
    assert rows[1]["clip_id"] == "c02"


def test_consent_disclosure_and_anonymous_ids(tmp_path: Path):
    assert "audio stays on this laptop" in record_set_c.CONSENT_DISCLOSURE.lower()
    assert "deleted after the event" in record_set_c.CONSENT_DISCLOSURE.lower()
    assert "only the numbers are shown" in record_set_c.CONSENT_DISCLOSURE.lower()

    cdir = tmp_path / "clips/set_c/c01"
    with pytest.raises(PermissionError):
        record_set_c.write_consent_record(cdir, participants=["Alice", "Bob"], confirmed_yes=False)
    assert not (cdir / "consent.json").exists()

    rec = record_set_c.write_consent_record(cdir, participants=["Alice", "Bob"], confirmed_yes=True)
    assert rec["disclosure"] == record_set_c.CONSENT_DISCLOSURE
    assert [p["participant_id"] for p in rec["participants"]] == ["P01", "P02"]

    # Reusing a known name keeps P01; new person gets P03
    cdir2 = tmp_path / "clips/set_c/c02"
    rec2 = record_set_c.write_consent_record(cdir2, participants=["Alice", "Charlie"], confirmed_yes=True)
    assert [p["participant_id"] for p in rec2["participants"]] == ["P01", "P03"]

    # run_arms rejects real names in consent_ids
    with pytest.raises(ValueError):
        run_arms._validate_anonymous_consent_ids("Alice;Bob")
    assert run_arms._validate_anonymous_consent_ids("P01;P02") == "P01;P02"


def test_unverified_asr_draft_never_counts(tmp_path: Path):
    cdir = tmp_path / "clips/set_c/c01"
    record_set_c.write_consent_record(cdir, participants=["Alice", "Bob"], confirmed_yes=True)

    frame = _make_dummy_frame()
    crop = clip_io.extract_clearvoice_crop_jpeg(frame, {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.4})
    pcm = (np.zeros(clip_io.HOP_SAMPLES, dtype="<i2")).tobytes()
    clip_io.save_hops_jsonl(
        cdir / "hops.jsonl",
        [
            clip_io.ClipHop(
                seq=0,
                session_id="eval-c01",
                target_face_id="face_0",
                reset=True,
                pcm_bytes=pcm,
                crops_jpegs=[crop] * 12,
                frame_jpeg=clip_io.encode_frame_jpeg(frame),
                faces=[{"id": "face_0", "box": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.4}, "mouth_open": 0.2}],
                t_capture=0.0,
            )
        ],
    )
    (cdir / "meta.json").write_text(
        json.dumps(
            {
                "clip_id": "c01",
                "consent_ids": "P01;P02",
                "draft_truth_target": "asr draft only",
                "truth_target": "",
                "truth_others": "",
                "truth_verified": False,
            }
        )
    )

    out_csv = tmp_path / "clips.csv"
    # Non-interactive draft cannot auto-verify or write clips.csv
    meta = record_set_c.fill_truth_flow(
        cdir,
        truth_target="asr draft only",
        truth_others="other draft",
        human_confirmed=False,
        interactive=False,
        clips_csv_path=out_csv,
    )
    assert meta["truth_verified"] is False
    assert not out_csv.exists()

    # run_arms refuses unverified clip
    with pytest.raises(ValueError, match="unverified truth"):
        asyncio.run(run_arms.evaluate_clip(cdir, arms={"b0", "a", "b"}, clips_csv=out_csv, dry_run=True))
    assert not out_csv.exists()


def test_run_arms_privacy_redacted_csv_and_scoring(tmp_path: Path):
    cdir = tmp_path / "clips/set_c/c01"
    rec = record_set_c.write_consent_record(cdir, participants=["Alice Secret", "Bob Secret"], confirmed_yes=True)
    anon_ids = ";".join(p["participant_id"] for p in rec["participants"])
    assert anon_ids == "P01;P02"

    frame = _make_dummy_frame()
    crop = clip_io.extract_clearvoice_crop_jpeg(frame, {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.4})
    fjpg = clip_io.encode_frame_jpeg(frame)
    pcm = (np.zeros(clip_io.HOP_SAMPLES, dtype="<i2")).tobytes()
    hops = [
        clip_io.ClipHop(
            seq=i,
            session_id="eval-c01",
            target_face_id="face_0",
            reset=(i == 0),
            pcm_bytes=pcm,
            crops_jpegs=[crop] * 12,
            frame_jpeg=fjpg,
            faces=[{"id": "face_0", "box": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.4}, "mouth_open": 0.25}],
            t_capture=i * 500.0,
        )
        for i in range(4)
    ]
    clip_io.save_hops_jsonl(cdir / "hops.jsonl", hops)
    (cdir / "meta.json").write_text(
        json.dumps(
            {
                "clip_id": "c01",
                "talkers": 2,
                "target_face": "face_0",
                "distance_m": 1,
                "angle": "front",
                "noise_db": 65,
                "occlusion": "none",
                "consent_ids": anon_ids,
                "truth_target": "the coffee is ready now",
                "truth_others": "please check the train schedule",
                "truth_verified": True,
                "network": "wifi",
            }
        )
    )

    out_csv = tmp_path / "clips.csv"
    report = asyncio.run(
        run_arms.evaluate_clip(
            cdir,
            arms={"b0", "a", "b"},
            use_guard=True,
            clips_csv=out_csv,
            dry_run=True,
        )
    )

    assert report["arms"]["b0"]["leak"] > 0.4
    assert report["arms"]["b"]["leak"] == 0.0
    assert report["arms"]["b"]["wer"] == 0.0

    # Verify tracked clips.csv has ONLY P01;P02 and numeric scores — NO real names, NO truth/arm text!
    csv_raw = out_csv.read_text(encoding="utf-8")
    assert "Alice" not in csv_raw
    assert "Bob" not in csv_raw
    assert "coffee" not in csv_raw
    assert "schedule" not in csv_raw
    assert "P01;P02" in csv_raw

    rows = list(csv.DictReader(out_csv.open()))
    assert len(rows) == 1
    assert rows[0]["truth_target"] == ""
    assert rows[0]["truth_others"] == ""
    assert rows[0]["b0_text"] == ""
    assert rows[0]["a_text"] == ""
    assert rows[0]["b_text"] == ""
    assert rows[0]["b_wer"] == "0.0000"
    assert rows[0]["b_leak"] == "0.0000"

    # Confirm score_all accurately aggregates numeric-only privacy-redacted clips.csv
    summary = score_all.build_summary(tmp_path)
    assert summary["set_c"]["n_total"] == 1
    assert math.isclose(summary["set_c"]["arms"]["b0_raw"]["leak_clip_mean"], 0.5)
    assert math.isclose(summary["set_c"]["arms"]["engine_b_gpu"]["leak_clip_mean"], 0.0)
    assert math.isclose(summary["set_c"]["arms"]["engine_b_gpu"]["wer_clip_mean"], 0.0)

    # Confirm default sets root and eval hops live inside gitignored clips/
    assert "clips" in record_set_c.SETS_C_ROOT.parts
    assert "clips" in run_arms.DEFAULT_SETS_ROOT.parts
    assert "clips" in run_arms.EVAL_HOPS_PATH.parts


def test_next_clip_id(tmp_path: Path):
    assert record_set_c.next_clip_id(tmp_path) == "c01"
    (tmp_path / "c01").mkdir()
    (tmp_path / "c04").mkdir()
    assert record_set_c.next_clip_id(tmp_path) == "c05"


def test_live_backend_symbols_and_signatures():
    import inspect
    from backend.gemini.decisions import LeakageGuard, SpeakingDecisionClient
    from backend.gemini.engine_a import EngineALiveBuffer
    from backend.gemini.live_captioner import LiveCaptionLane
    from backend.separation.client import SeparationClient
    from backend.separation.hop_logger import HopLogger

    assert not inspect.iscoroutinefunction(SeparationClient.submit_hop)
    assert inspect.iscoroutinefunction(SeparationClient.start)
    assert inspect.iscoroutinefunction(LiveCaptionLane.start)
    assert inspect.iscoroutinefunction(EngineALiveBuffer.process_chunk)
    assert inspect.iscoroutinefunction(SpeakingDecisionClient.decide_window)
    assert hasattr(LeakageGuard, "allow_target_segment")
    assert hasattr(HopLogger, "log_result")
