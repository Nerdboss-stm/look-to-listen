"""End-to-end verification tests for S3 tasks (E10, E11, E12, E15, E18, E19, E20, E21, E22).

Run unit + live API acceptance checks:
  ~/.venvs/g4-backend/bin/python -m pytest backend/gemini/test_s3_suite.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent_env.hooks.gate_command import check_command_payload, evaluate_hook as eval_cmd_hook
from agent_env.hooks.gate_privacy import check_privacy_payload, evaluate_hook as eval_priv_hook
from agent_env.hooks.gate_release import check_release_payload, evaluate_hook as eval_rel_hook
from backend.gemini import logger as gemini_logger
from backend.gemini.argon import ConversationMemory
from backend.gemini.decisions import LeakageGuard, SpeakingDecisionClient
from backend.gemini.managed_agent import ListenerAgentService
from backend.gemini.vocab import get_vocab_terms, register_consenting_speaker, remove_speaker_vocab
from backend.robot.pointing import parse_pointing_json


@pytest.fixture(autouse=True)
def _isolate_logs_to_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Guarantee S3 tests NEVER write to repo logs/agent.jsonl, logs/calls.jsonl, or logs/hops.jsonl."""
    tmp_logs = tmp_path / "logs"
    tmp_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOOK_TO_LISTEN_LOGS_DIR", str(tmp_logs))
    monkeypatch.setattr(gemini_logger, "LOGS_DIR", tmp_logs)
    monkeypatch.setattr(gemini_logger, "CALLS_LOG", tmp_logs / "calls.jsonl")
    monkeypatch.setattr(gemini_logger, "AGENT_LOG", tmp_logs / "agent.jsonl")
    return tmp_logs


def test_leakage_guard_drops_when_target_silent_and_passes_when_speaking():
    guard = LeakageGuard(decision_threshold=0.9, guard_ms=500)
    guard.record(
        {
            "face_id": "face-1",
            "window_t0": 1000.0,
            "window_t1": 2000.0,
            "p_speaking": 0.96,
            "latency_ms": 180.0,
            "calibrated": True,
            "source": "decision-1",
        }
    )
    guard.record(
        {
            "face_id": "face-2",
            "window_t0": 1000.0,
            "window_t1": 2000.0,
            "p_speaking": 0.08,
            "latency_ms": 185.0,
            "calibrated": True,
            "source": "decision-1",
        }
    )
    allow_1, p1 = guard.allow_target_segment("face-1", 1200.0, 1800.0)
    allow_2, p2 = guard.allow_target_segment("face-2", 1200.0, 1800.0)
    assert allow_1 is True and p1 == pytest.approx(0.96)
    assert allow_2 is False and p2 == pytest.approx(0.08)

    best_fid, best_p = guard.best_speaking_face(1200.0, 1800.0)
    assert best_fid == "face-1" and best_p == pytest.approx(0.96)


def test_fb6_mediapipe_fallback_marks_uncalibrated():
    client = SpeakingDecisionClient(use_fallback_fb6=True)
    dec = client._fb6_mediapipe("face-1", 0.0, 1000.0, mouth_open=0.28)
    assert dec["calibrated"] is False
    assert dec["source"] == "mediapipe-uncalibrated"
    assert dec["p_speaking"] >= 0.9


def test_privacy_hook_3_of_3_deny_then_redact_allow():
    svc = ListenerAgentService()
    for trial in range(3):
        consent = {"face-1": True, "face-2": False}
        lines = [
            {"face_id": "face-1", "text": f"Consented speaker note {trial}."},
            {"face_id": "face-2", "text": f"Unconsented bystander line {trial}."},
        ]
        # First verify strict deny when auto_redact_retry=False
        denied = svc.save_transcript_with_privacy_hook(
            conversation_id=f"test-deny-{trial}",
            lines=lines,
            consent_map=consent,
            auto_redact_retry=False,
        )
        assert denied["ok"] is False
        assert "face-2" in denied["reason"]

        # Verify deny -> redact -> allow flow
        res = svc.save_transcript_with_privacy_hook(
            conversation_id=f"test-redact-{trial}",
            lines=lines,
            consent_map=consent,
            auto_redact_retry=True,
        )
        assert res["ok"] is True
        assert res["denied_initially"] is True
        assert res["redacted"] is True
        assert res["saved_lines"] == 1
        assert res["removed_lines"] == 1


def test_command_hook_10_of_10_denies_non_target_and_allows_target():
    svc = ListenerAgentService()
    for i in range(10):
        target = "face-1" if i % 2 == 0 else "face-2"
        other = "face-2" if i % 2 == 0 else "face-1"
        ok_res = svc.check_robot_command(
            command_id=f"cmd-ok-{i}", face_id=target, target_face_id=target, text="Hand me the bottle"
        )
        bad_res = svc.check_robot_command(
            command_id=f"cmd-bad-{i}", face_id=other, target_face_id=target, text="Hand me the phone"
        )
        assert ok_res["allowed"] is True
        assert bad_res["allowed"] is False
        assert other in bad_res["reason"]


def test_release_hook_2_of_2_allows_better_denies_worse():
    svc = ListenerAgentService()
    base = {"leakage": 0.14, "wer": 0.18, "delay_p50_ms": 1450.0}

    # Better config: allowed
    better_cfg = {**svc.active_config, "config_id": "cfg-better", "guard_ms": 600}
    better_res = svc.release_config_with_regression_hook(
        candidate_config=better_cfg,
        before_metrics=base,
        after_metrics={"leakage": 0.10, "wer": 0.17, "delay_p50_ms": 1400.0},
    )
    assert better_res["ok"] is True
    assert better_res["decision"] == "allow"
    assert svc.active_config["config_id"] == "cfg-better"

    # Worse config (higher leakage & delay): denied
    worse_cfg = {**svc.active_config, "config_id": "cfg-worse", "guard_ms": 1200}
    worse_res = svc.release_config_with_regression_hook(
        candidate_config=worse_cfg,
        before_metrics=base,
        after_metrics={"leakage": 0.19, "wer": 0.17, "delay_p50_ms": 1600.0},
    )
    assert worse_res["ok"] is False
    assert worse_res["decision"] == "deny"
    assert "leakage" in worse_res["reason"]
    assert "delay_p50_ms" in worse_res["reason"]
    assert svc.active_config["config_id"] == "cfg-better"


def test_hook_scripts_stdin_protocol():
    """Verify hook scripts work identically via Managed Agent stdin JSON protocol."""
    hook_cmd = REPO_ROOT / "agent_env/hooks/gate_command.py"
    stdin_payload = json.dumps(
        {
            "tool_call": {
                "name": "write_file",
                "args": {
                    "path": "out/robot_command.json",
                    "content": json.dumps({"face_id": "face-2", "target_face_id": "face-1", "text": "Grab cup"}),
                },
            }
        }
    )
    proc = subprocess.run(
        [sys.executable, str(hook_cmd)],
        input=stdin_payload,
        text=True,
        capture_output=True,
        check=True,
    )
    out = json.loads(proc.stdout)
    assert out["decision"] == "deny"
    assert "face-2" in out["reason"]


def test_vocab_consent_enforcement(tmp_path):
    vp = tmp_path / "vocab.json"
    assert register_consenting_speaker("face-1", "Alex", consent_given=False, path=vp) is False
    assert get_vocab_terms(vp) == []
    assert register_consenting_speaker("face-1", "Alex", consent_given=True, path=vp) is True
    assert "Alex" in get_vocab_terms(vp)
    remove_speaker_vocab("face-1", path=vp)
    assert "Alex" not in get_vocab_terms(vp)


def test_pointing_json_parser():
    label, pt = parse_pointing_json('```json\n[{"label": "red mug", "point": [712, 667]}]\n```')
    assert label == "red mug"
    assert pt == [712.0, 667.0]
    assert parse_pointing_json("[]") == (None, None)


def test_fastapi_backend_mounts_s3_routes():
    from backend.main import app

    paths = set(app.openapi()["paths"].keys())
    assert "/api/gemini/status" in paths
    assert "/api/memory/ask" in paths
    assert "/api/robot/command" in paths
    assert "/api/agent/save_transcript" in paths
    assert "/api/agent/release_config" in paths


def test_live_captioner_constants_and_argon_thinking_level():
    from backend.gemini import live_captioner

    assert live_captioner.LIVE_RETRY_INTERVAL_S == 10.0
    assert live_captioner.IDLE_KEEPALIVE_S <= 5.0
    assert live_captioner.WS_PONG_TIMEOUT_S == 10.0
    assert live_captioner.ROTATE_AFTER_S >= 180.0
    assert live_captioner.FB5_HTTP_TIMEOUT_MS == 10000

    lc_src = (REPO_ROOT / "backend/gemini/live_captioner.py").read_text(encoding="utf-8")
    assert "WatchdogTimeout" not in lc_src
    assert "PongTimeout" in lc_src

    argon_src = (REPO_ROOT / "backend/gemini/argon.py").read_text(encoding="utf-8")
    assert "ThinkingLevel.MINIMAL" not in argon_src
    assert "ThinkingLevel.LOW" in argon_src

    neon_src = (REPO_ROOT / "backend/gemini/neon.py").read_text(encoding="utf-8")
    assert "timeout_ms=25000" in neon_src


def test_hooks_write_only_to_temp_log_dir(_isolate_logs_to_tmp: Path):
    """Verify running all 3 hooks writes to temp logs, leaving repo logs/ untouched."""
    repo_logs = REPO_ROOT / "logs"
    before = {
        name: (repo_logs / name).stat().st_size if (repo_logs / name).exists() else 0
        for name in ("agent.jsonl", "hops.jsonl")
    }
    svc = ListenerAgentService()
    svc.save_transcript_with_privacy_hook(
        conversation_id="tmp-check",
        lines=[{"face_id": "face-2", "text": "No consent"}],
        consent_map={"face-2": False},
        auto_redact_retry=False,
    )
    svc.check_robot_command(command_id="c1", face_id="face-2", target_face_id="face-1", text="Grab cup")
    svc.release_config_with_regression_hook(
        candidate_config={**svc.active_config, "config_id": "cfg-tmp"},
        before_metrics={"leakage": 0.10, "wer": 0.15, "delay_p50_ms": 1200.0},
        after_metrics={"leakage": 0.20, "wer": 0.15, "delay_p50_ms": 1200.0},
    )
    after = {
        name: (repo_logs / name).stat().st_size if (repo_logs / name).exists() else 0
        for name in ("agent.jsonl", "hops.jsonl")
    }
    assert after == before
    tmp_agent_log = _isolate_logs_to_tmp / "agent.jsonl"
    assert tmp_agent_log.exists() and tmp_agent_log.stat().st_size > 0
