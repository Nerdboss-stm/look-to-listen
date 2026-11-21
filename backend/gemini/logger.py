"""Append-only JSONL logging for model calls (logs/calls.jsonl) and agent events (logs/agent.jsonl)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"
CALLS_LOG = LOGS_DIR / "calls.jsonl"
AGENT_LOG = LOGS_DIR / "agent.jsonl"


def get_logs_dir() -> Path:
    override = os.getenv("LOOK_TO_LISTEN_LOGS_DIR")
    return Path(override) if override else LOGS_DIR


def get_calls_log_path() -> Path:
    override = os.getenv("LOOK_TO_LISTEN_LOGS_DIR")
    return (Path(override) / "calls.jsonl") if override else CALLS_LOG


def get_agent_log_path() -> Path:
    override = os.getenv("LOOK_TO_LISTEN_LOGS_DIR")
    return (Path(override) / "agent.jsonl") if override else AGENT_LOG

_LOCK = threading.Lock()

# Rough per-1M-token USD estimates for logging (input_per_1m, output_per_1m)
_COST_TABLE: dict[str, tuple[float, float]] = {
    "hydrogen": (0.25, 1.50),
    "neon": (1.25, 10.00),
    "argon": (2.50, 15.00),
    "decision": (0.10, 0.40),
    "flash": (0.15, 0.60),
    "pro": (1.25, 10.00),
}


def estimate_cost_usd(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float:
    """Estimate call cost in USD from token counts."""
    in_tok = max(0, int(input_tokens or 0))
    out_tok = max(0, int(output_tokens or 0))
    low = (model or "").lower()
    in_rate, out_rate = 0.50, 2.00
    for key, rates in _COST_TABLE.items():
        if key in low:
            in_rate, out_rate = rates
            break
    return round((in_tok * in_rate + out_tok * out_rate) / 1_000_000.0, 8)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def log_model_call(
    *,
    model: str,
    latency_ms: float,
    thinking_level: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost: float | None = None,
    probability: float | None = None,
    purpose: str | None = None,
    ok: bool = True,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a model call record to logs/calls.jsonl."""
    if estimated_cost is None:
        estimated_cost = estimate_cost_usd(model, input_tokens, output_tokens)
    rec: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "thinking_level": thinking_level,
        "latency_ms": round(float(latency_ms), 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimated_cost,
        "probability": probability,
        "purpose": purpose,
        "ok": ok,
    }
    if error:
        rec["error"] = error
    if extra:
        rec["extra"] = extra
    _append_jsonl(get_calls_log_path(), rec)
    return rec


def log_agent_event(
    *,
    event_type: str,
    tool: str | None = None,
    decision: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append an agent event record to logs/agent.jsonl."""
    rec: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "tool": tool,
        "decision": decision,
        "reason": reason,
        "details": details or {},
    }
    _append_jsonl(get_agent_log_path(), rec)
    return rec
