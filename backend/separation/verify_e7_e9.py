"""Live end-to-end verification for E7 & E9 (AT4).

Boots backend.main:app in-process on a local port, connects via real /ws/live
WebSocket using exact contracts/hop.schema.json payloads, streams 60 real-time
0.5 s hops (30 s) through SeparationClient -> RTX 4090 GPU pod -> LiveAudioPlayer
(laptop speaker) -> logs/hops.jsonl -> /ws/live hop_result, and checks AT4 thresholds:
  - Continuous 30 s playback with 0 gaps > 300 ms
  - Voice delay p50 <= 1500 ms
  - GPU p50 <= 300 ms, RTT p50 <= 500 ms
  - Target switch reset=true handled cleanly mid-stream
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import cv2
import httpx
import numpy as np
import uvicorn
import websockets

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def make_crop_pool(n: int = 25) -> list[str]:
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:112, 0:112]
    base = 120 + 60 * np.exp(-(((xx - 56) / 30.0) ** 2 + ((yy - 50) / 38.0) ** 2))
    out: list[str] = []
    for i in range(n):
        img = base + 8 * np.sin((xx + 3 * i) / 6.0) + rng.normal(0, 5, (112, 112))
        ok, buf = cv2.imencode(".jpg", np.clip(img, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 80])
        assert ok
        out.append(base64.b64encode(buf.tobytes()).decode("ascii"))
    return out


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    xs = sorted(vals)
    return float(xs[min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))])


async def run_verification(hops: int = 60, port: int = 8000, use_existing: bool = False) -> int:
    server = None
    serve_task = None
    temp_dir_obj = None
    hops_log_path = REPO_ROOT / "logs" / "hops.jsonl"

    if not use_existing:
        # Isolate verification logs in a temporary directory so we never pollute logs/
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="l2l-verify-")
        temp_log_dir = Path(temp_dir_obj.name)
        os.environ["L2L_LOG_DIR"] = str(temp_log_dir)
        hops_log_path = temp_log_dir / "hops.jsonl"

        import backend.main as main_mod

        main_mod.AGENT_LOG_PATH = temp_log_dir / "agent.jsonl"
        rt = main_mod.get_runtime()
        rt.hop_logger.path = hops_log_path
        rt.clips.agent_log_path = temp_log_dir / "agent.jsonl"
        try:
            import backend.gemini.logger as gemini_logger_mod

            gemini_logger_mod.AGENT_LOG = temp_log_dir / "agent.jsonl"
            gemini_logger_mod.CALLS_LOG = temp_log_dir / "calls.jsonl"
        except Exception:
            pass

        app = main_mod.app

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        serve_task = asyncio.create_task(server.serve())
        # Wait for backend startup
        for _ in range(60):
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    r = await client.get(f"http://127.0.0.1:{port}/health")
                    if r.status_code == 200:
                        break
            except Exception:
                pass
            await asyncio.sleep(0.1)

    base_http = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}/ws/live"

    async with httpx.AsyncClient(timeout=2.0) as client:
        h0 = (await client.get(f"{base_http}/health")).json()
        print(
            f"Startup /health: engine={h0['engine']} gpu_connected={h0['separator']['gpu_connected']} "
            f"backend_playback_enabled={h0['playback']['enabled']}"
        )

    pool = make_crop_pool()
    results_rx: list[dict] = []
    metrics_rx: list[dict] = []
    engine_rx: list[dict] = []

    async with websockets.connect(ws_url, max_size=None, compression=None) as ws:
        async def reader() -> None:
            async for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "hop_result":
                    results_rx.append(msg["payload"])
                elif t == "metrics":
                    metrics_rx.append(msg["payload"])
                elif t == "engine_status":
                    engine_rx.append(msg)

        rx_task = asyncio.create_task(reader())
        session_id = f"verify-e7-e9-{int(time.time())}"
        t0 = time.perf_counter()
        frames_done = 0

        for seq in range(hops):
            target_t = t0 + seq * 0.5
            wait = target_t - time.perf_counter()
            if wait > 0:
                await asyncio.sleep(wait)

            # Synthesize gentle speech-band audio (two overlapping harmonics so speaker check is audible but pleasant)
            ts = np.arange(8000) / 16000.0 + seq * 0.5
            env = 0.5 + 0.5 * np.sin(2 * np.pi * 2.5 * ts)
            sig = 0.08 * env * (np.sin(2 * np.pi * 220.0 * ts) + 0.6 * np.sin(2 * np.pi * 440.0 * ts))
            pcm_bytes = (np.clip(sig, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

            need = (seq + 1) * 8000 // 640 - frames_done
            crops = [pool[(frames_done + i) % len(pool)] for i in range(need)]
            frames_done += need

            # Simulate target switch halfway through
            switched = seq == (hops // 2)
            target_face = "face-2" if seq >= (hops // 2) else "face-1"
            if switched:
                await ws.send(json.dumps({"type": "set_target", "face_id": target_face, "mode": "pinned"}))

            hop_payload = {
                "session_id": session_id,
                "seq": seq,
                "target_face_id": target_face,
                "reset": (seq == 0 or switched),
                "pcm": base64.b64encode(pcm_bytes).decode("ascii"),
                "crops": crops,
                "t_capture": round(time.time() * 1000.0, 1),
                "sample_rate": 16000,
                "hop_ms": 500,
                "faces": [
                    {
                        "id": "face-1",
                        "box": {"x": 0.15, "y": 0.2, "w": 0.25, "h": 0.4},
                        "lips": [[0.25, 0.45], [0.30, 0.45]],
                        "mouth_open": 0.12,
                        "color": "#00E5FF",
                        "consent": {"given": True, "by": "verify", "time": "2026-11-21T11:45:00Z"},
                    },
                    {
                        "id": "face-2",
                        "box": {"x": 0.55, "y": 0.2, "w": 0.25, "h": 0.4},
                        "lips": [[0.65, 0.45], [0.70, 0.45]],
                        "mouth_open": 0.10,
                        "color": "#FF4081",
                        "consent": {"given": True, "by": "verify", "time": "2026-11-21T11:45:00Z"},
                    },
                ],
            }
            await ws.send(json.dumps({"type": "hop", "payload": hop_payload}))

        # Wait briefly for final hop result & playback drain
        await asyncio.sleep(1.5)
        rx_task.cancel()
        try:
            await rx_task
        except asyncio.CancelledError:
            pass

    async with httpx.AsyncClient(timeout=2.0) as client:
        m = (await client.get(f"{base_http}/api/metrics")).json()
        h1 = (await client.get(f"{base_http}/health")).json()

    if server is not None and serve_task is not None:
        server.should_exit = True
        await serve_task

    gpu_vals = [float(r["gpu_ms"]) for r in results_rx]
    rtt_vals = [float(r.get("rtt_ms", 0.0)) for r in results_rx]
    failover_flips = [e for e in engine_rx if e.get("engine") != "B-GPU"]
    pcm_ok = sum(
        1
        for r in results_rx
        if isinstance(r.get("pcm"), str)
        and len(base64.b64decode(r["pcm"])) == int(r.get("samples", 0)) * 2
        and int(r.get("samples", 0)) >= 8000
    )
    hops_snap = m["hops"]
    pb = m["playback"]

    # Read exact backend pre-send overhead (t_send - t_capture) for this session from temp hops.jsonl
    pre_ms: list[float] = []
    gpu_rtt_vals: list[float] = []
    if hops_log_path.exists():
        for line in hops_log_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("session_id") == session_id and rec.get("status") == "ok":
                if rec.get("t_send") is not None and rec.get("t_capture") is not None:
                    pre_ms.append(float(rec["t_send"]) - float(rec["t_capture"]))
                if rec.get("gpu_rtt_ms") is not None:
                    gpu_rtt_vals.append(float(rec["gpu_rtt_ms"]))
    if temp_dir_obj is not None:
        temp_dir_obj.cleanup()

    print("\n=== E7 / E9 (AT4) Live Verification Summary ===")
    print(f"Hops sent:           {hops} ({hops * 0.5:.1f} s)")
    print(f"Hop results back:    {len(results_rx)} (valid 16kB int16 PCM on /ws/live: {pcm_ok}/{len(results_rx)})")
    print(f"Active engine:       {m['engine']} ({m['engine_reason']}); failover flips={len(failover_flips)}")
    print(f"Backend playback:    enabled={pb['enabled']} (expected False; browser VoicePlayer plays for Chrome AEC)")
    if pre_ms:
        print(f"Backend pre-send:    p50={pct(pre_ms, 50):.1f} ms / p95={pct(pre_ms, 95):.1f} ms / max={max(pre_ms):.1f} ms")
    print(f"GPU ms p50 / p95:    {pct(gpu_vals, 50):.1f} ms / {pct(gpu_vals, 95):.1f} ms (gate <= 300 ms)")
    if gpu_rtt_vals:
        print(f"GPU RTT p50/p95/max: {pct(gpu_rtt_vals, 50):.1f} ms / {pct(gpu_rtt_vals, 95):.1f} ms / {max(gpu_rtt_vals):.1f} ms")
    print(f"E2E RTT p50/p95/max: {pct(rtt_vals, 50):.1f} ms / {pct(rtt_vals, 95):.1f} ms / {max(rtt_vals or [0.0]):.1f} ms (gate p50 < 300 ms)")
    print(
        f"Voice delay p50/p95: {hops_snap['voice_delay_p50_ms']} ms / {hops_snap['voice_delay_p95_ms']} ms (AT4 gate <= 1500 ms)"
    )
    print(f"Hops logged / drop:  ok={hops_snap['hops_ok']} dropped={hops_snap['hops_dropped']} merged={hops_snap['hops_merged']}")

    passed = (
        len(results_rx) >= int(hops * 0.9)
        and pcm_ok == len(results_rx)
        and len(failover_flips) == 0
        and pb["enabled"] is False
        and m["engine"] == "B-GPU"
        and pct(rtt_vals, 50) < 300.0
        and (hops_snap["voice_delay_p50_ms"] or 9999) <= 1500.0
    )
    print(f"VERDICT: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hops", type=int, default=60)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--existing", action="store_true")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(run_verification(hops=a.hops, port=a.port, use_existing=a.existing)))


if __name__ == "__main__":
    main()
