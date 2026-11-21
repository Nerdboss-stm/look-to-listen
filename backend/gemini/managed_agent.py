"""Managed Agent runtime & tuner (E19, E20, E21 — AT11, AT12, AT13).

Uses the verified Gemini Managed Agent API (antigravity-preview-09-2026 + gemini-4-neon,
per G5 findings in NOTES.md):
- Uploads agent_env/ (AGENTS.md, skills/listener/SKILL.md, .agents/hooks.json, hooks/*.py)
  into the Managed Agent sandbox environment so pre_tool_execution hooks genuinely fire on
  write_file / execute_code.
- Provides fast local hook execution + live remote Managed Agent invocation for:
  1. Privacy-gated save_transcript / send_summary (AT11)
  2. Target-only robot_act command gate (AT12)
  3. Set C config tuner + regression-gated release_config + 30 min cron trigger (AT13)
- Logs every tool call, hook decision (ALLOW/DENY + reason + before/after metrics), and
  config release to logs/agent.jsonl so the browser AGENT stream updates live.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agent_env.hooks.gate_command import check_command_payload
from agent_env.hooks.gate_privacy import check_privacy_payload
from agent_env.hooks.gate_release import check_release_payload
from backend.gemini.client import MODELS, get_api_key
from backend.gemini.logger import get_agent_log_path, log_agent_event, log_model_call

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ENV_DIR = REPO_ROOT / "agent_env"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
AGENT_ID = "antigravity-preview-09-2026"

DEFAULT_CONFIG: dict[str, Any] = {
    "config_id": "cfg-001",
    "engine": "B-GPU",
    "window_s": 3.0,
    "hop_s": 0.5,
    "decision_threshold": 0.9,
    "guard_ms": 750,
    "vocab": [],
    "translate_to": None,
}


def _scrub(text: str, secret: str) -> str:
    return text.replace(secret, "[REDACTED]") if secret else text


def _append_rich_agent_event(event: dict[str, Any]) -> dict[str, Any]:
    """Append an event matching S1/S2's AGENT stream schema to logs/agent.jsonl."""
    path = get_agent_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"time": datetime.now(timezone.utc).isoformat(), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def build_agent_env_sources(extra_state_files: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Package agent_env/ files + dynamic state files as inline sources for the Managed Agent."""
    sources: list[dict[str, Any]] = []
    file_map = {
        "AGENTS.md": AGENT_ENV_DIR / "AGENTS.md",
        "skills/listener/SKILL.md": AGENT_ENV_DIR / "skills/listener/SKILL.md",
        ".agents/hooks.json": AGENT_ENV_DIR / ".agents/hooks.json",
        "hooks/gate_privacy.py": AGENT_ENV_DIR / "hooks/gate_privacy.py",
        "hooks/gate_command.py": AGENT_ENV_DIR / "hooks/gate_command.py",
        "hooks/gate_release.py": AGENT_ENV_DIR / "hooks/gate_release.py",
        "hooks/post_tool_log.py": AGENT_ENV_DIR / "hooks/post_tool_log.py",
    }
    for target, src_path in file_map.items():
        if src_path.exists():
            sources.append(
                {
                    "type": "inline",
                    "target": target,
                    "content": src_path.read_text(encoding="utf-8"),
                }
            )
    if extra_state_files:
        for target, content in extra_state_files.items():
            sources.append({"type": "inline", "target": target, "content": content})
    return sources


def _extract_agent_text(resp: dict[str, Any]) -> str:
    if isinstance(resp.get("output_text"), str) and resp["output_text"]:
        return resp["output_text"]
    parts: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("type") == "text" and isinstance(obj.get("text"), str):
                parts.append(obj["text"])
            elif isinstance(obj.get("text"), str) and obj.get("type") != "thought":
                parts.append(obj["text"])
            for k, v in obj.items():
                if k in ("outputs", "steps", "output", "content", "parts", "result"):
                    walk(v)
        elif isinstance(obj, list):
            for it in obj:
                walk(it)

    walk(resp)
    return "\n".join(parts)


def run_managed_agent_interaction_sync(
    *,
    prompt: str,
    state_files: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_total_tokens: int = 60000,
    timeout_s: float = 120.0,
    purpose: str = "managed_agent_run",
) -> dict[str, Any]:
    """Run one Managed Agent interaction with agent_env/ hooks active in the remote sandbox."""
    api_key = get_api_key()
    payload: dict[str, Any] = {
        "agent": AGENT_ID,
        "input": prompt,
        "agent_config": {
            "type": "antigravity",
            "model": MODELS.neon,
            "max_total_tokens": max_total_tokens,
        },
        "environment": {
            "type": "remote",
            "sources": build_agent_env_sources(state_files),
        },
    }
    if tools:
        payload["tools"] = tools

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(
                f"{BASE_URL}/interactions",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            try:
                body = r.json()
            except Exception:
                body = {"raw": _scrub(r.text[:1000], api_key)}

            # Poll if still running
            deadline = time.perf_counter() + timeout_s
            while (
                r.status_code == 200
                and isinstance(body, dict)
                and body.get("status") in ("in_progress", "running", "pending")
                and body.get("id")
                and time.perf_counter() < deadline
            ):
                time.sleep(1.5)
                pr = client.get(
                    f"{BASE_URL}/interactions/{body['id']}",
                    headers={"x-goog-api-key": api_key},
                )
                if pr.status_code == 200:
                    body = pr.json()
                else:
                    break
    except Exception as exc:
        total_ms = (time.perf_counter() - t0) * 1000.0
        err_msg = _scrub(f"{type(exc).__name__}: {exc}", api_key)
        log_model_call(
            model=f"{AGENT_ID}/{MODELS.neon}",
            thinking_level=None,
            latency_ms=total_ms,
            purpose=purpose,
            ok=False,
            error=err_msg,
        )
        return {
            "ok": False,
            "http_status": 0,
            "status": "error",
            "interaction_id": None,
            "environment_id": None,
            "latency_ms": round(total_ms, 1),
            "text": "",
            "error": err_msg,
        }

    total_ms = (time.perf_counter() - t0) * 1000.0
    usage = body.get("usage") if isinstance(body, dict) else {}
    in_tok = (usage or {}).get("total_input_tokens")
    out_tok = (usage or {}).get("total_output_tokens")
    ok = r.status_code == 200 and isinstance(body, dict) and body.get("status") == "completed"
    text = _extract_agent_text(body) if isinstance(body, dict) else ""

    log_model_call(
        model=f"{AGENT_ID}/{MODELS.neon}",
        thinking_level=None,
        latency_ms=total_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        purpose=purpose,
        ok=ok,
        error=None if ok else _scrub(str(body)[:400], api_key),
    )
    return {
        "ok": ok,
        "http_status": r.status_code,
        "status": body.get("status") if isinstance(body, dict) else None,
        "interaction_id": body.get("id") if isinstance(body, dict) else None,
        "environment_id": body.get("environment_id") if isinstance(body, dict) else None,
        "latency_ms": round(total_ms, 1),
        "text": text,
        "raw_status_keys": sorted(body.keys()) if isinstance(body, dict) else [],
    }


def create_tuner_trigger_sync(
    *,
    schedule: str = "*/30 * * * *",
    time_zone: str = "America/New_York",
    state_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Register the 30-minute Managed Agent tuner schedule via POST /v1beta/triggers (E21)."""
    api_key = get_api_key()
    payload = {
        "schedule": schedule,
        "time_zone": time_zone,
        "interaction": {
            "agent": AGENT_ID,
            "agent_config": {
                "type": "antigravity",
                "model": MODELS.neon,
                "max_total_tokens": 20000,
            },
            "input": (
                "Scheduled 30-minute tuning run: read state/baseline_eval.json and state/clips_index.json, "
                "evaluate candidate configs, and write the best non-regressing config to out/released_config.json. "
                "Report exact before/after leakage, WER, and delay_p50_ms."
            ),
            "environment": {
                "type": "remote",
                "sources": build_agent_env_sources(state_files),
            },
        },
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{BASE_URL}/triggers",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            ms = (time.perf_counter() - t0) * 1000.0
            try:
                body = r.json()
            except Exception:
                body = {"raw": _scrub(r.text[:500], api_key)}
            status_code = r.status_code
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        body = {"error": _scrub(f"{type(exc).__name__}: {exc}", api_key)}
        status_code = 0

    ok = status_code == 200
    _append_rich_agent_event(
        {
            "event_type": "tool_call",
            "tool": "create_trigger",
            "decision": "ALLOW" if ok else "DENY",
            "reason": f"30-min tuner schedule ({schedule} {time_zone})" if ok else str(body)[:200],
            "summary": f"Tuner cron trigger {'registered' if ok else 'failed'} ({schedule})",
        }
    )
    return {
        "ok": ok,
        "http_status": status_code,
        "trigger_id": body.get("id") or body.get("name") if isinstance(body, dict) else None,
        "next_run_time": body.get("next_run_time") if isinstance(body, dict) else None,
        "latency_ms": round(ms, 1),
        "body": body if ok else _scrub(str(body)[:400], api_key),
    }


def delete_tuner_trigger_sync(trigger_id: str) -> bool:
    api_key = get_api_key()
    tid = trigger_id.split("/")[-1]
    with httpx.Client(timeout=20.0) as client:
        r = client.delete(
            f"{BASE_URL}/triggers/{tid}",
            headers={"x-goog-api-key": api_key},
        )
        return r.status_code in (200, 204)


class ListenerAgentService:
    """Backend service coordinating privacy saves, robot command hooks, and config releases."""

    def __init__(self) -> None:
        self.active_config: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.saved_transcripts: dict[str, dict[str, Any]] = {}
        self.last_release: dict[str, Any] | None = None

    def save_transcript_with_privacy_hook(
        self,
        *,
        conversation_id: str,
        lines: list[dict[str, Any]],
        consent_map: dict[str, bool],
        auto_redact_retry: bool = True,
        run_remote_sandbox: bool = False,
    ) -> dict[str, Any]:
        """Run gate_privacy.py on save_transcript; if denied, log DENY, redact, retry, log ALLOW (AT11)."""
        payload = {"conversation_id": conversation_id, "lines": lines}
        first = check_privacy_payload(payload, consent_map=consent_map)

        if first["decision"] == "deny":
            _append_rich_agent_event(
                {
                    "event_type": "hook",
                    "tool": "save_transcript",
                    "hook": "gate_privacy.py",
                    "decision": "DENY",
                    "reason": first["reason"],
                    "summary": f"gate_privacy DENIED save_transcript: {first['reason']}",
                }
            )
            if not auto_redact_retry:
                return {
                    "ok": False,
                    "denied": True,
                    "hook": "gate_privacy.py",
                    "reason": first["reason"],
                    "redacted": False,
                }

            # Redact non-consenting faces and retry (same contract as Managed Agent retry)
            redacted_lines = [
                line
                for line in lines
                if line.get("face_id") is not None and bool(consent_map.get(str(line["face_id"]), False))
            ]
            retry_payload = {"conversation_id": conversation_id, "lines": redacted_lines}
            second = check_privacy_payload(retry_payload, consent_map=consent_map)
            if second["decision"] == "allow":
                self.saved_transcripts[conversation_id] = retry_payload
                _append_rich_agent_event(
                    {
                        "event_type": "hook",
                        "tool": "save_transcript",
                        "hook": "gate_privacy.py",
                        "decision": "ALLOW",
                        "reason": f"Redacted non-consenting faces; saved {len(redacted_lines)} consented line(s).",
                        "summary": f"gate_privacy ALLOWED redacted save ({len(redacted_lines)} consented lines)",
                    }
                )
                return {
                    "ok": True,
                    "denied_initially": True,
                    "deny_reason": first["reason"],
                    "redacted": True,
                    "saved_lines": len(redacted_lines),
                    "removed_lines": len(lines) - len(redacted_lines),
                    "conversation_id": conversation_id,
                }
            return {"ok": False, "denied": True, "reason": second.get("reason")}

        # Already clean — allowed on first attempt
        self.saved_transcripts[conversation_id] = payload
        _append_rich_agent_event(
            {
                "event_type": "hook",
                "tool": "save_transcript",
                "hook": "gate_privacy.py",
                "decision": "ALLOW",
                "reason": first["reason"],
                "summary": f"gate_privacy ALLOWED save_transcript ({len(lines)} consented lines)",
            }
        )
        return {
            "ok": True,
            "denied_initially": False,
            "redacted": False,
            "saved_lines": len(lines),
            "removed_lines": 0,
            "conversation_id": conversation_id,
        }

    def check_robot_command(
        self, *, command_id: str, face_id: str, target_face_id: str | None, text: str
    ) -> dict[str, Any]:
        """Run gate_command.py and log ALLOW/DENY to logs/agent.jsonl (AT12)."""
        res = check_command_payload(
            {"command_id": command_id, "face_id": face_id, "text": text},
            current_target_face_id=target_face_id,
        )
        allowed = res["decision"] == "allow"
        _append_rich_agent_event(
            {
                "event_type": "hook",
                "tool": "robot_act",
                "hook": "gate_command.py",
                "decision": "ALLOW" if allowed else "DENY",
                "reason": res["reason"],
                "summary": f"gate_command {'ALLOWED' if allowed else 'DENIED'} {face_id}: {text}",
            }
        )
        return {"allowed": allowed, "reason": res["reason"]}

    def release_config_with_regression_hook(
        self,
        *,
        candidate_config: dict[str, Any],
        before_metrics: dict[str, float],
        after_metrics: dict[str, float],
    ) -> dict[str, Any]:
        """Run gate_release.py; apply candidate_config ONLY if zero metrics regress (AT13)."""
        res = check_release_payload(
            {"config": candidate_config, "before": before_metrics, "after": after_metrics}
        )
        allowed = res["decision"] == "allow"
        _append_rich_agent_event(
            {
                "event_type": "config_release" if allowed else "hook",
                "tool": "release_config",
                "hook": "gate_release.py",
                "decision": "ALLOW" if allowed else "DENY",
                "reason": res["reason"],
                "summary": f"gate_release {'RELEASED' if allowed else 'BLOCKED'} {candidate_config.get('config_id', 'cfg')}",
                "metrics_before": res.get("metrics_before", before_metrics),
                "metrics_after": res.get("metrics_after", after_metrics),
            }
        )
        if allowed:
            self.active_config = dict(candidate_config)
            self.last_release = {
                "config": self.active_config,
                "before": res.get("metrics_before", before_metrics),
                "after": res.get("metrics_after", after_metrics),
                "time": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "ok": allowed,
            "decision": res["decision"],
            "reason": res["reason"],
            "active_config": self.active_config,
            "metrics_before": res.get("metrics_before", before_metrics),
            "metrics_after": res.get("metrics_after", after_metrics),
        }
