#!/usr/bin/env python3
"""Pre-tool hook: gate_command.py (SPEC C6 / AT12).

Denies robot_act (or writing out/robot_command.json) if the command's face_id
is not the current target_face_id. The reason always names the face.
Works both inside the Managed Agent sandbox (stdin JSON) and via direct import.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _load_target_face(override: str | None = None) -> str | None:
    if override is not None and str(override).strip():
        return str(override).strip()
    for cand in (
        Path("state/target_face.json"),
        Path("/workspace/state/target_face.json"),
        Path("/state/target_face.json"),
    ):
        if cand.exists():
            try:
                raw = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("target_face_id"):
                    return str(raw["target_face_id"]).strip()
            except Exception:
                return None
    return None


def check_command_payload(
    payload: dict[str, Any],
    *,
    current_target_face_id: str | None = None,
) -> dict[str, Any]:
    """Allow robot_act ONLY when command face_id == current target_face_id."""
    face_id = payload.get("face_id")
    face_s = str(face_id).strip() if face_id is not None else ""
    target_s = _load_target_face(
        current_target_face_id
        if current_target_face_id is not None
        else payload.get("target_face_id")
    )

    if not face_s:
        return {
            "decision": "deny",
            "reason": "COMMAND_DENY: Missing face_id; robot acts only for the current target face.",
        }
    if not target_s:
        return {
            "decision": "deny",
            "reason": f"COMMAND_DENY: Face '{face_s}' denied because no target face is currently selected.",
        }
    if face_s != target_s:
        return {
            "decision": "deny",
            "reason": (
                f"COMMAND_DENY: Face '{face_s}' is not the current target face '{target_s}'. "
                "Robot obeys only the person being looked at."
            ),
        }
    return {
        "decision": "allow",
        "reason": f"COMMAND_ALLOW: Face '{face_s}' matches current target '{target_s}'.",
    }


def _extract_json_content(args: dict[str, Any]) -> Any:
    for k in ("content", "contents", "code_content", "CodeContent", "Content", "file_content", "text", "data", "body"):
        v = args.get(k)
        if v is not None:
            return v
    for k, v in args.items():
        if k.lower() in ("path", "file_path", "target_file", "targetfile", "filename", "description", "overwrite"):
            continue
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip().startswith(("{", "[")):
            return v
    return None


def _load_staged_command(target_path: str) -> dict[str, Any] | None:
    p = Path(target_path)
    for cand in (
        p.parent / "candidate_command.json",
        Path("out/candidate_command.json"),
        Path("/out/candidate_command.json"),
        Path("/workspace/out/candidate_command.json"),
    ):
        if cand.exists():
            try:
                raw = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
            except Exception:
                return None
    return None


def evaluate_hook(data: dict[str, Any]) -> dict[str, Any]:
    tc = data.get("tool_call") or {}
    tname = str(tc.get("name") or data.get("tool_name") or "")
    args = tc.get("args") or data.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    if tname == "robot_act":
        return check_command_payload(args)

    if tname in ("write_file", "write_to_file"):
        raw_target = str(
            args.get("path")
            or args.get("file_path")
            or args.get("target_file")
            or args.get("TargetFile")
            or args.get("Path")
            or args.get("filename")
            or ""
        )
        target = raw_target.lower()
        if "candidate_" in target:
            return {"decision": "allow"}
        if "robot_command" in target:
            content = _extract_json_content(args)
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    return {
                        "decision": "deny",
                        "reason": "COMMAND_DENY: robot_command file must be valid JSON with face_id and target_face_id.",
                    }
            elif isinstance(content, dict):
                parsed = content
            else:
                staged = _load_staged_command(raw_target)
                if staged is None:
                    return {
                        "decision": "deny",
                        "reason": (
                            "COMMAND_DENY: Stage candidate JSON at /out/candidate_command.json first, "
                            "then write /out/robot_command.json."
                        ),
                    }
                parsed = staged
            authoritative_target = _load_target_face(None)
            return check_command_payload(parsed, current_target_face_id=authoritative_target)

    return {"decision": "allow"}


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    res = evaluate_hook(data)
    out: dict[str, Any] = {"decision": res["decision"]}
    if res.get("reason"):
        out["reason"] = res["reason"]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
