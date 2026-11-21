#!/usr/bin/env python3
"""Pre-tool hook: gate_release.py (SPEC C7 / AT13 / contracts/eval.md §9).

Denies releasing a pipeline config if ANY metric (leakage, WER, or delay_p50_ms)
gets worse compared to the baseline on Set C. The reason lists each metric before and after.
Works both inside the Managed Agent sandbox (stdin JSON) and via direct import.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _load_baseline_eval() -> dict[str, Any] | None:
    for cand in (
        Path("state/baseline_eval.json"),
        Path("/workspace/state/baseline_eval.json"),
        Path("/state/baseline_eval.json"),
    ):
        if cand.exists():
            try:
                raw = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
            except Exception:
                return None
    return None


def _f(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                return None
    return None


def check_release_payload(
    payload: dict[str, Any],
    *,
    baseline_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enforce contracts/eval.md §9: leakage_after <= before, wer_after <= before, delay_p50_after <= before."""
    before = baseline_override or payload.get("before") or _load_baseline_eval()
    after = payload.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {
            "decision": "deny",
            "reason": (
                "RELEASE_DENY: Missing Set C regression suite results ('before' and 'after' metrics). "
                "Run eval_before and eval_after before releasing a config."
            ),
        }

    b_leak = _f(before, "leakage", "mean_leakage")
    a_leak = _f(after, "leakage", "mean_leakage")
    b_wer = _f(before, "wer", "mean_wer")
    a_wer = _f(after, "wer", "mean_wer")
    b_delay = _f(before, "delay_p50_ms", "delay_p50", "delay_ms")
    a_delay = _f(after, "delay_p50_ms", "delay_p50", "delay_ms")

    if None in (b_leak, a_leak, b_wer, a_wer, b_delay, a_delay):
        return {
            "decision": "deny",
            "reason": (
                "RELEASE_DENY: Incomplete regression metrics (need leakage, wer, and delay_p50_ms for both before and after)."
            ),
        }

    assert b_leak is not None and a_leak is not None
    assert b_wer is not None and a_wer is not None
    assert b_delay is not None and a_delay is not None

    eps = 1e-9
    regressions: list[str] = []
    if a_leak > b_leak + eps:
        regressions.append(f"leakage got worse ({b_leak:.4f} -> {a_leak:.4f})")
    if a_wer > b_wer + eps:
        regressions.append(f"WER got worse ({b_wer:.4f} -> {a_wer:.4f})")
    if a_delay > b_delay + eps:
        regressions.append(f"delay_p50_ms got worse ({b_delay:.1f} -> {a_delay:.1f})")

    metrics_str = (
        f"leakage {b_leak:.4f}->{a_leak:.4f}, "
        f"wer {b_wer:.4f}->{a_wer:.4f}, "
        f"delay_p50_ms {b_delay:.1f}->{a_delay:.1f}"
    )

    if regressions:
        return {
            "decision": "deny",
            "reason": f"RELEASE_DENY: Regression blocked ({'; '.join(regressions)}). Metrics: {metrics_str}.",
            "metrics_before": {"leakage": b_leak, "wer": b_wer, "delay_p50_ms": b_delay},
            "metrics_after": {"leakage": a_leak, "wer": a_wer, "delay_p50_ms": a_delay},
        }

    return {
        "decision": "allow",
        "reason": f"RELEASE_ALLOW: No regressions on Set C. Metrics: {metrics_str}.",
        "metrics_before": {"leakage": b_leak, "wer": b_wer, "delay_p50_ms": b_delay},
        "metrics_after": {"leakage": a_leak, "wer": a_wer, "delay_p50_ms": a_delay},
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


def _load_staged_candidate(target_path: str) -> dict[str, Any] | None:
    """When Managed Agent write_file hook only receives {'path': ...}, read staged candidate JSON from disk."""
    p = Path(target_path)
    cands = [
        p.parent / "candidate_config.json",
        Path("out/candidate_config.json"),
        Path("/out/candidate_config.json"),
        Path("/workspace/out/candidate_config.json"),
    ]
    for cand in cands:
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

    if tname == "release_config":
        return check_release_payload(args)

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
        if "released_config" in target or "release_config" in target:
            content = _extract_json_content(args)
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    return {
                        "decision": "deny",
                        "reason": "RELEASE_DENY: released_config file must be valid JSON containing config, before, and after metrics.",
                    }
            elif isinstance(content, dict):
                parsed = content
            else:
                staged = _load_staged_candidate(raw_target)
                if staged is None:
                    return {
                        "decision": "deny",
                        "reason": (
                            "RELEASE_DENY: Stage candidate JSON (with config, before, after metrics) "
                            "at /out/candidate_config.json first, then write /out/released_config.json."
                        ),
                    }
                parsed = staged
            # Always compare against authoritative state/baseline_eval.json if present
            baseline = _load_baseline_eval()
            return check_release_payload(parsed, baseline_override=baseline)

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
