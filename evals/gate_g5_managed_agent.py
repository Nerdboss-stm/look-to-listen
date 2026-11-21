"""Gate G5: Managed Agent capability checks (SPEC.md & prompts.md).

Tests:
  1. Model check: does antigravity-preview-09-2026 accept gemini-4-neon?
     If not, test default model + egress proxy injecting x-goog-api-key for Gemini API.
  2. Client-side function tools: requires_action -> function_result loop, plus exact tool names.
  3. pre_tool_execution command hook: denies once with a reason; verifies agent sees reason and retries.
  4. Scheduled trigger: creates a */30 * * * * trigger, verifies response, and deletes it cleanly.

Never prints or logs GEMINI_API_KEY. Logs calls to logs/calls.jsonl and events to logs/agent.jsonl.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
AGENT_ID = "antigravity-preview-09-2026"


def load_env(env_path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    if env_path.exists():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def scrub(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "[REDACTED]")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, obj: dict[str, Any], secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = scrub(json.dumps(obj, ensure_ascii=False), secret)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def extract_usage(resp: dict[str, Any]) -> tuple[int | None, int | None]:
    usage = resp.get("usage") or {}
    in_tok = usage.get("total_input_tokens") or usage.get("input_tokens") or usage.get("prompt_token_count")
    out_tok = usage.get("total_output_tokens") or usage.get("output_tokens") or usage.get("candidates_token_count")
    return in_tok, out_tok


def extract_text(resp: dict[str, Any]) -> str:
    if isinstance(resp.get("output_text"), str) and resp["output_text"]:
        return resp["output_text"]
    parts: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("type") == "text" and isinstance(obj.get("text"), str):
                parts.append(obj["text"])
            elif isinstance(obj.get("text"), str) and obj.get("type") not in ("thought",):
                parts.append(obj["text"])
            for k, v in obj.items():
                if k in ("outputs", "steps", "output", "content", "parts", "result"):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(resp)
    return "\n".join(parts)


def collect_tool_names(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        t = obj.get("type")
        if t in ("function_call", "tool_call", "code_execution_call") or "tool_name" in obj:
            if isinstance(obj.get("name"), str):
                out.add(f"{t}:{obj['name']}")
            elif isinstance(obj.get("tool_name"), str):
                out.add(f"{t}:{obj['tool_name']}")
            elif isinstance(t, str):
                out.add(t)
        elif isinstance(t, str) and ("call" in t or "execution" in t or "tool" in t):
            out.add(t)
        for v in obj.values():
            collect_tool_names(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_tool_names(v, out)


def find_function_calls(resp: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("type") == "function_call":
                calls.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(resp)
    return calls


def post_json(
    client: httpx.Client,
    url: str,
    payload: dict[str, Any],
    api_key: str,
    model_label: str,
    event_label: str,
) -> tuple[int, dict[str, Any], float]:
    t0 = time.perf_counter()
    r = client.post(
        url,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json=payload,
    )
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    try:
        body = r.json()
    except Exception:
        body = {"raw_text": scrub(r.text[:1000], api_key)}

    in_tok, out_tok = extract_usage(body if isinstance(body, dict) else {})
    append_jsonl(
        REPO_ROOT / "logs/calls.jsonl",
        {
            "time": now_iso(),
            "model": model_label,
            "thinking": None,
            "latency_ms": latency_ms,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "estimated_cost": None,
            "probability": None,
            "endpoint": url.replace(BASE_URL, ""),
            "http_status": r.status_code,
            "tag": event_label,
        },
        api_key,
    )
    append_jsonl(
        REPO_ROOT / "logs/agent.jsonl",
        {
            "time": now_iso(),
            "event": event_label,
            "http_status": r.status_code,
            "status": body.get("status") if isinstance(body, dict) else None,
            "latency_ms": latency_ms,
        },
        api_key,
    )
    return r.status_code, body, latency_ms


def poll_if_running(
    client: httpx.Client,
    resp: dict[str, Any],
    api_key: str,
    max_wait_s: float = 120.0,
) -> dict[str, Any]:
    inter_id = resp.get("id")
    status = resp.get("status")
    deadline = time.perf_counter() + max_wait_s
    while inter_id and status in ("in_progress", "running", "queued", "pending") and time.perf_counter() < deadline:
        time.sleep(2.0)
        r = client.get(
            f"{BASE_URL}/interactions/{inter_id}",
            headers={"x-goog-api-key": api_key},
        )
        if r.status_code != 200:
            break
        resp = r.json()
        status = resp.get("status")
    return resp


def test_1_model_and_egress(client: httpx.Client, api_key: str) -> dict[str, Any]:
    print("\n=== G5.1: Model gemini-4-neon check (+ egress proxy check if needed) ===")
    payload = {
        "agent": AGENT_ID,
        "input": "Reply with the single word OK.",
        "agent_config": {
            "type": "antigravity",
            "model": "gemini-4-neon",
            "max_total_tokens": 8000,
        },
        "environment": {"type": "remote"},
    }
    code, body, ms = post_json(client, f"{BASE_URL}/interactions", payload, api_key, f"{AGENT_ID}:gemini-4-neon", "g5_1_model_neon")
    if code == 200:
        body = poll_if_running(client, body, api_key)
    accepted = code == 200 and body.get("status") in ("completed", "requires_action")
    text = extract_text(body) if isinstance(body, dict) else ""
    print(f"  gemini-4-neon HTTP={code} status={body.get('status')} latency={ms} ms text={text[:120]!r}")
    if not accepted:
        print(f"  error/body: {scrub(json.dumps(body)[:500], api_key)}")

    result: dict[str, Any] = {
        "neon_accepted": accepted,
        "neon_http": code,
        "neon_status": body.get("status"),
        "neon_latency_ms": ms,
        "neon_text": text[:200],
        "neon_top_keys": sorted(body.keys()) if isinstance(body, dict) else [],
        "neon_error": None if accepted else scrub(json.dumps(body)[:400], api_key),
    }

    if not accepted:
        print("  Testing fallback: default model + egress proxy injecting x-goog-api-key to generativelanguage.googleapis.com")
        egress_payload = {
            "agent": AGENT_ID,
            "input": (
                "Run a single bash or python snippet that sends a POST request to "
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-neon:generateContent "
                "with JSON body {\"contents\":[{\"parts\":[{\"text\":\"Say EGRESS_OK\"}]}]} "
                "(do NOT supply any API key; the egress proxy injects it). "
                "Print the HTTP status code and response text."
            ),
            "environment": {
                "type": "remote",
                "network": {
                    "allowlist": [
                        {
                            "domain": "generativelanguage.googleapis.com",
                            "transform": {"x-goog-api-key": api_key},
                        }
                    ]
                },
            },
        }
        e_code, e_body, e_ms = post_json(
            client, f"{BASE_URL}/interactions", egress_payload, api_key, AGENT_ID, "g5_1b_egress_proxy"
        )
        if e_code == 200:
            e_body = poll_if_running(client, e_body, api_key)
        e_text = extract_text(e_body) if isinstance(e_body, dict) else ""
        egress_ok = e_code == 200 and ("EGRESS_OK" in e_text or "200" in e_text)
        print(f"  egress proxy HTTP={e_code} status={e_body.get('status')} latency={e_ms} ms ok={egress_ok}")
        print(f"  egress text: {scrub(e_text[:300], api_key)!r}")
        result.update(
            {
                "egress_proxy_ok": egress_ok,
                "egress_http": e_code,
                "egress_status": e_body.get("status"),
                "egress_latency_ms": e_ms,
                "egress_text": scrub(e_text[:400], api_key),
                "egress_error": None if e_code == 200 else scrub(json.dumps(e_body)[:400], api_key),
            }
        )
    return result


def test_2_client_tools(client: httpx.Client, api_key: str, use_neon: bool) -> dict[str, Any]:
    print("\n=== G5.2: Client-side function tools, continuation, & hook tool names ===")
    log_script = """#!/usr/bin/env python3
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {"raw": raw}
tc = data.get("tool_call") or {}
tname = tc.get("name") or data.get("tool_name") or "unknown"
with open("/tmp/g5_2_hook_tools.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"tool_name": tname, "args_keys": sorted((tc.get("args") or {}).keys())}) + "\\n")
print(json.dumps({"decision": "allow"}))
"""
    runner_cmd = (
        "python3 -c \""
        "import os,runpy; "
        "p=next(x for x in ['.agents/hooks-scripts/log_tools.py','/workspace/.agents/hooks-scripts/log_tools.py','/.agents/hooks-scripts/log_tools.py'] if os.path.exists(x)); "
        "runpy.run_path(p, run_name='__main__')\""
    )
    hooks_json = {
        "g5-2-logger": {
            "pre_tool_execution": [
                {
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": runner_cmd, "timeout": 10}],
                }
            ]
        }
    }
    payload: dict[str, Any] = {
        "agent": AGENT_ID,
        "input": (
            "Step 1: Call the get_clip_count tool with since='2026-11-21'. "
            "Step 2: After you receive the result, run a shell command to echo the count into /tmp/g5_count.txt, "
            "then read /tmp/g5_2_hook_tools.jsonl and print its exact contents along with DONE:<count>."
        ),
        "environment": {
            "type": "remote",
            "sources": [
                {
                    "type": "inline",
                    "target": ".agents/hooks.json",
                    "content": json.dumps(hooks_json, indent=2),
                },
                {
                    "type": "inline",
                    "target": ".agents/hooks-scripts/log_tools.py",
                    "content": log_script,
                },
            ],
        },
        "tools": [
            {"type": "code_execution"},
            {
                "type": "function",
                "name": "get_clip_count",
                "description": "Returns the number of clips recorded since a date.",
                "parameters": {
                    "type": "object",
                    "properties": {"since": {"type": "string"}},
                    "required": ["since"],
                },
            },
        ],
    }
    if use_neon:
        payload["agent_config"] = {"type": "antigravity", "model": "gemini-4-neon", "max_total_tokens": 12000}

    code, body, ms = post_json(client, f"{BASE_URL}/interactions", payload, api_key, AGENT_ID, "g5_2_client_tools_turn1")
    if code == 200:
        body = poll_if_running(client, body, api_key)

    tool_names: set[str] = set()
    collect_tool_names(body, tool_names)
    calls = find_function_calls(body)
    env_id = body.get("environment_id")
    print(f"  turn1 HTTP={code} status={body.get('status')} env_id={env_id} latency={ms} ms calls={len(calls)} tools={sorted(tool_names)}")

    res: dict[str, Any] = {
        "turn1_http": code,
        "turn1_status": body.get("status"),
        "turn1_env_id": env_id,
        "turn1_latency_ms": ms,
        "function_calls_seen": calls,
        "client_tools_supported": False,
        "tool_names_observed": sorted(tool_names),
    }

    if code == 200 and body.get("status") == "requires_action" and calls:
        call = calls[0]
        call_id = call.get("id") or call.get("call_id")
        call_name = call.get("name", "get_clip_count")
        cont_payload: dict[str, Any] = {
            "agent": AGENT_ID,
            "previous_interaction_id": body["id"],
            "environment": env_id or body.get("environment") or {"type": "remote"},
            "tools": payload["tools"],
            "input": [
                {
                    "type": "function_result",
                    "name": call_name,
                    "call_id": call_id,
                    "result": json.dumps({"count": 42}),
                }
            ],
        }
        if use_neon:
            cont_payload["agent_config"] = {"type": "antigravity", "model": "gemini-4-neon", "max_total_tokens": 12000}

        c2, b2, ms2 = post_json(client, f"{BASE_URL}/interactions", cont_payload, api_key, AGENT_ID, "g5_2_client_tools_turn2")
        if c2 == 400:
            print(f"  turn2 attempt1 400: {scrub(json.dumps(b2)[:500], api_key)}")
            cont_payload["input"][0]["result"] = {"count": 42}
            c2, b2, ms2 = post_json(client, f"{BASE_URL}/interactions", cont_payload, api_key, AGENT_ID, "g5_2_client_tools_turn2_dict")
        if c2 == 200:
            b2 = poll_if_running(client, b2, api_key)
        collect_tool_names(b2, tool_names)
        t2 = extract_text(b2) if isinstance(b2, dict) else ""
        ok = c2 == 200 and b2.get("status") == "completed" and "42" in t2
        print(f"  turn2 HTTP={c2} status={b2.get('status')} latency={ms2} ms ok={ok}")
        print(f"  turn2 text: {t2[:600]!r}")
        if c2 != 200:
            print(f"  turn2 error: {scrub(json.dumps(b2)[:500], api_key)}")
        print(f"  observed tool names: {sorted(tool_names)}")
        res.update(
            {
                "turn1_top_keys": sorted(body.keys()),
                "turn2_http": c2,
                "turn2_status": b2.get("status"),
                "turn2_latency_ms": ms2,
                "turn2_text": t2[:1200],
                "turn2_error": None if c2 == 200 else scrub(json.dumps(b2)[:500], api_key),
                "client_tools_supported": ok,
                "hook_saw_client_tool": "get_clip_count" in t2 and '"tool_name": "get_clip_count"' in t2,
                "tool_names_observed": sorted(tool_names),
            }
        )
    else:
        res["turn1_body_sample"] = scrub(json.dumps(body)[:600], api_key)
    return res


def test_3_pre_tool_hook(client: httpx.Client, api_key: str, use_neon: bool) -> dict[str, Any]:
    print("\n=== G5.3: pre_tool_execution command hook (deny once with reason, verify retry) ===")
    gate_script = """#!/usr/bin/env python3
import json, os, sys

raw = sys.stdin.read()
try:
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {"raw": raw}

tc = data.get("tool_call") or {}
tname = tc.get("name") or data.get("tool_name") or "unknown"
log_path = "/tmp/g5_hook_log.jsonl"
with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps({"tool_name": tname, "keys": list(data.keys()), "tc_keys": list(tc.keys())}) + "\\n")

flag = "/tmp/g5_denied_once.flag"
if not os.path.exists(flag):
    with open(flag, "w", encoding="utf-8") as f:
        f.write(tname)
    print(json.dumps({
        "decision": "deny",
        "reason": "G5_POLICY_DENY: First attempt blocked by gate_once. You MUST create /tmp/verified_g5.txt containing 'RETRY_OK' instead."
    }))
else:
    print(json.dumps({"decision": "allow"}))
"""
    runner_cmd = (
        "python3 -c \""
        "import os,runpy; "
        "p=next(x for x in ['.agents/hooks-scripts/gate_once.py','/workspace/.agents/hooks-scripts/gate_once.py','/.agents/hooks-scripts/gate_once.py'] if os.path.exists(x)); "
        "runpy.run_path(p, run_name='__main__')\""
    )
    hooks_json = {
        "g5-gate-test": {
            "pre_tool_execution": [
                {
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": runner_cmd,
                            "timeout": 10,
                        }
                    ],
                }
            ]
        }
    }

    payload: dict[str, Any] = {
        "agent": AGENT_ID,
        "input": (
            "Write 'HELLO' to /tmp/first_g5.txt. "
            "If a hook denies your tool call, read its reason carefully and follow its instruction instead. "
            "Finally, read and print the full contents of /tmp/g5_hook_log.jsonl and the file you created."
        ),
        "environment": {
            "type": "remote",
            "sources": [
                {
                    "type": "inline",
                    "target": ".agents/hooks.json",
                    "content": json.dumps(hooks_json, indent=2),
                },
                {
                    "type": "inline",
                    "target": ".agents/hooks-scripts/gate_once.py",
                    "content": gate_script,
                },
            ],
        },
    }
    if use_neon:
        payload["agent_config"] = {"type": "antigravity", "model": "gemini-4-neon", "max_total_tokens": 15000}

    code, body, ms = post_json(client, f"{BASE_URL}/interactions", payload, api_key, AGENT_ID, "g5_3_pre_tool_hook")
    if code == 200:
        body = poll_if_running(client, body, api_key)
    text = extract_text(body) if isinstance(body, dict) else ""
    tool_names: set[str] = set()
    collect_tool_names(body, tool_names)

    hook_fired = "tool_name" in text or "RETRY_OK" in text or "verified_g5" in text or "G5_POLICY_DENY" in text
    retried_ok = ("RETRY_OK" in text) and ("verified_g5" in text)
    print(f"  HTTP={code} status={body.get('status')} latency={ms} ms hook_fired={hook_fired} retried_ok={retried_ok}")
    print(f"  reply excerpt: {text[:450]!r}")
    if code != 200:
        print(f"  error: {scrub(json.dumps(body)[:500], api_key)}")

    return {
        "http": code,
        "status": body.get("status"),
        "latency_ms": ms,
        "hook_fired": hook_fired,
        "agent_retried_after_deny": retried_ok,
        "tool_names_in_response": sorted(tool_names),
        "top_keys": sorted(body.keys()) if isinstance(body, dict) else [],
        "outputs_summary": [
            {k: v for k, v in item.items() if k != "signature"}
            for item in (body.get("outputs") or [])
            if isinstance(item, dict)
        ] if isinstance(body, dict) else [],
        "text": text[:1500],
        "error": None if code == 200 else scrub(json.dumps(body)[:500], api_key),
    }


def test_4_scheduled_trigger(client: httpx.Client, api_key: str, use_neon: bool) -> dict[str, Any]:
    print("\n=== G5.4: Scheduled trigger (every 30 minutes) ===")
    interaction_cfg: dict[str, Any] = {
        "agent": AGENT_ID,
        "input": [{"type": "text", "text": "Reply OK."}],
        "environment": {"type": "remote"},
    }
    if use_neon:
        interaction_cfg["agent_config"] = {"type": "antigravity", "model": "gemini-4-neon", "max_total_tokens": 4000}

    payload = {
        "schedule": "*/30 * * * *",
        "time_zone": "America/New_York",
        "display_name": "g5-tuner-gate-test",
        "interaction": interaction_cfg,
    }
    code, body, ms = post_json(client, f"{BASE_URL}/triggers", payload, api_key, AGENT_ID, "g5_4_trigger_create")
    trig_id = body.get("id") or body.get("name")
    next_run = body.get("next_run_time") or body.get("nextRunTime")
    print(f"  create HTTP={code} latency={ms} ms id={trig_id} next_run={next_run}")
    if code not in (200, 201):
        print(f"  error: {scrub(json.dumps(body)[:500], api_key)}")

    deleted = False
    del_code = None
    if trig_id:
        del_path = trig_id if str(trig_id).startswith("triggers/") else f"triggers/{trig_id}"
        dr = client.delete(f"{BASE_URL}/{del_path}", headers={"x-goog-api-key": api_key})
        del_code = dr.status_code
        deleted = del_code in (200, 204)
        print(f"  cleanup DELETE /{del_path} HTTP={del_code} deleted={deleted}")

    return {
        "create_http": code,
        "latency_ms": ms,
        "trigger_supported": code in (200, 201) and bool(trig_id),
        "trigger_id": trig_id,
        "next_run_time": next_run,
        "cleanup_http": del_code,
        "cleanup_deleted": deleted,
        "response_sample": scrub(json.dumps(body)[:500], api_key),
    }


def append_gate_log(passed: bool, latency_ms: float, notes: str) -> None:
    gate_path = REPO_ROOT / "gate_log.csv"
    t_et = datetime.now().strftime("%H:%M")
    with gate_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "G5",
            "1",
            t_et,
            AGENT_ID,
            "",
            "4 Managed Agent checks (model/egress, client tools, pre_tool_execution hook, 30-min trigger)",
            "",
            "4",
            f"{latency_ms:.0f}",
            "yes" if passed else "no",
            notes,
        ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(REPO_ROOT / ".env"))
    ap.add_argument("--only", default="1,2,3,4", help="Comma-separated check numbers to run")
    ap.add_argument("--write-gate-log", action="store_true")
    args = ap.parse_args()

    env = load_env(Path(args.env))
    api_key = os.environ.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not found in environment or .env")

    checks = {s.strip() for s in args.only.split(",") if s.strip()}
    results: dict[str, Any] = {"time": now_iso(), "agent": AGENT_ID}

    with httpx.Client(timeout=180.0) as client:
        use_neon = False
        if "1" in checks:
            results["check1_model"] = test_1_model_and_egress(client, api_key)
            use_neon = bool(results["check1_model"].get("neon_accepted"))
        if "2" in checks:
            results["check2_tools"] = test_2_client_tools(client, api_key, use_neon=use_neon)
        if "3" in checks:
            results["check3_hook"] = test_3_pre_tool_hook(client, api_key, use_neon=use_neon)
        if "4" in checks:
            results["check4_trigger"] = test_4_scheduled_trigger(client, api_key, use_neon=use_neon)

    out_path = REPO_ROOT / "evals/g5_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(scrub(json.dumps(results, indent=2), api_key) + "\n", encoding="utf-8")
    print(f"\nSaved full G5 result to {out_path}")

    c1_ok = bool(results.get("check1_model", {}).get("neon_accepted") or results.get("check1_model", {}).get("egress_proxy_ok"))
    c2_ok = bool(results.get("check2_tools", {}).get("client_tools_supported"))
    c3_ok = bool(results.get("check3_hook", {}).get("agent_retried_after_deny"))
    c4_ok = bool(results.get("check4_trigger", {}).get("trigger_supported"))
    print(f"Summary: 1(model/egress)={c1_ok} 2(client_tools)={c2_ok} 3(hook_retry)={c3_ok} 4(trigger_30m)={c4_ok}")

    if args.write_gate_log:
        lat = results.get("check1_model", {}).get("neon_latency_ms") or 0.0
        note = (
            f"neon={results.get('check1_model', {}).get('neon_accepted')}; "
            f"egress={results.get('check1_model', {}).get('egress_proxy_ok')}; "
            f"client_tools={c2_ok}; hook_retry={c3_ok}; trigger_30m={c4_ok}"
        )
        append_gate_log(all([c1_ok, c2_ok, c3_ok, c4_ok]), float(lat), note)
        print("Appended row to gate_log.csv")


if __name__ == "__main__":
    main()
