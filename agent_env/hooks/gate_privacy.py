#!/usr/bin/env python3
"""Pre-tool hook: gate_privacy.py (SPEC C8 / AT11).

Denies saving a transcript or sending a summary if ANY line belongs to a face
without an explicit consent record (consent.given == true).
Works both inside the Managed Agent sandbox (stdin JSON) and via direct import.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _load_consent_map(consent_override: dict[str, Any] | None = None) -> dict[str, bool]:
    if isinstance(consent_override, dict):
        out: dict[str, bool] = {}
        for fid, rec in consent_override.items():
            if isinstance(rec, dict):
                out[str(fid)] = bool(rec.get("given", False))
            else:
                out[str(fid)] = bool(rec)
        return out

    for cand in (
        Path("state/consent.json"),
        Path("/workspace/state/consent.json"),
        Path("/state/consent.json"),
    ):
        if cand.exists():
            try:
                raw = json.loads(cand.read_text(encoding="utf-8"))
                return _load_consent_map(raw if isinstance(raw, dict) else {})
            except Exception:
                return {}
    return {}


def check_privacy_payload(
    payload: dict[str, Any],
    consent_map: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Validate transcript/summary payload against consent records."""
    cmap = consent_map if consent_map is not None else _load_consent_map(payload.get("consent"))
    lines = payload.get("lines") or payload.get("segments") or payload.get("transcript") or []
    if not isinstance(lines, list):
        return {
            "decision": "deny",
            "reason": "PRIVACY_DENY: Transcript payload must contain a 'lines' list with face_id attribution.",
        }

    unconsented_faces: list[str] = []
    for idx, line in enumerate(lines):
        if not isinstance(line, dict):
            continue
        fid = line.get("face_id")
        if fid is None or str(fid).strip() == "":
            tag = f"unattributed_line_{idx}"
            if tag not in unconsented_faces:
                unconsented_faces.append(tag)
            continue
        fid_s = str(fid)
        if cmap:
            allowed = bool(cmap.get(fid_s, False))
        else:
            allowed = bool(line.get("consent_given", False))
        if not allowed and fid_s not in unconsented_faces:
            unconsented_faces.append(fid_s)

    if unconsented_faces:
        faces_str = ", ".join(unconsented_faces)
        return {
            "decision": "deny",
            "reason": (
                f"PRIVACY_DENY: Blocked saving/sending lines from non-consenting face(s): {faces_str}. "
                "Redact all lines belonging to non-consenting faces and retry."
            ),
            "unconsented_faces": unconsented_faces,
        }

    return {"decision": "allow", "reason": f"All {len(lines)} line(s) verified with consent."}


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


def _load_staged_transcript(target_path: str) -> dict[str, Any] | None:
    p = Path(target_path)
    for cand in (
        p.parent / "candidate_transcript.json",
        Path("out/candidate_transcript.json"),
        Path("/out/candidate_transcript.json"),
        Path("/workspace/out/candidate_transcript.json"),
        Path("state/raw_transcript.json"),
        Path("/state/raw_transcript.json"),
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

    if tname in ("save_transcript", "send_summary"):
        return check_privacy_payload(args)

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
        content = _extract_json_content(args)
        if any(k in target for k in ("saved_transcript", "summary")):
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    return {
                        "decision": "deny",
                        "reason": (
                            "PRIVACY_DENY: Transcript/summary files must be valid JSON with a "
                            "'lines' array of {face_id, text} objects so consent can be verified."
                        ),
                    }
            elif isinstance(content, dict):
                parsed = content
            else:
                staged = _load_staged_transcript(raw_target)
                if staged is None:
                    return {
                        "decision": "deny",
                        "reason": (
                            "PRIVACY_DENY: Stage candidate JSON with 'lines' at "
                            "/out/candidate_transcript.json first, then save /out/saved_transcript.json."
                        ),
                    }
                parsed = staged
            return check_privacy_payload(parsed)

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
