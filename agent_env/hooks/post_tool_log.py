#!/usr/bin/env python3
"""Post-tool hook: post_tool_log.py — appends every sandbox tool execution to logs/sandbox_agent.jsonl."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    tc = data.get("tool_call") or {}
    rec = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event_type": "tool_call",
        "tool": tc.get("name") or data.get("tool_name") or "unknown",
        "environment_id": data.get("environment_id"),
    }
    log_path = Path("/tmp/listener_agent_log.jsonl")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "logged"}))


if __name__ == "__main__":
    main()
