"""Automated S1 tests: separation client, stale-hop drop, failover (AT14),
playback continuity/crossfade (AT4), consent-enforced clip store, and end_card CSVs.
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
from pathlib import Path

import numpy as np
import pytest
import websockets

from backend.playback.player import LiveAudioPlayer, SR
from backend.separation.client import (
    PendingHop,
    SeparationClient,
    _pack_binary_hop,
    _unpack_binary_result,
)
from backend.separation.hop_logger import HopLogger, read_hops_stats_from_disk
from backend.store.clips import ClipStore, ConsentDeniedError
from backend.store.consent import ConsentStore
from backend.store.end_card import build_end_card_data


def test_binary_hop_packing_roundtrip():
    pcm = (np.arange(8000, dtype=np.int16) % 1000).tobytes()
    jpegs = [b"\xff\xd8crop1\xff\xd9", b"\xff\xd8crop2\xff\xd9"]
    hop = PendingHop(
        session_id="sess-1",
        seq=7,
        target_face_id="face-1",
        reset=True,
        pcm_bytes=pcm,
        jpegs=jpegs,
        t_capture=1700000000000.0,
        hop_ms=500,
    )
    frame = _pack_binary_hop(hop, 1700000000010.0)
    n = struct.unpack_from("<I", frame, 0)[0]
    header = json.loads(frame[4 : 4 + n].decode("utf-8"))
    assert header["session_id"] == "sess-1"
    assert header["seq"] == 7
    assert header["target_face_id"] == "face-1"
    assert header["reset"] is True
    assert header["pcm_bytes"] == len(pcm)
    assert header["jpeg_sizes"] == [len(jpegs[0]), len(jpegs[1])]
    off = 4 + n
    assert frame[off : off + len(pcm)] == pcm
    off += len(pcm)
    assert frame[off : off + len(jpegs[0])] == jpegs[0]
    assert frame[off + len(jpegs[0]) :] == jpegs[1]


def test_binary_result_unpack():
    meta = {"seq": 3, "covers": [2, 3], "samples": 4, "gpu_ms": 128.4, "queue_ms": 0.5, "sent_ms": 12345}
    pcm = np.array([100, -100, 200, -200], dtype="<i2").tobytes()
    hb = json.dumps(meta).encode("utf-8")
    frame = struct.pack("<I", len(hb)) + hb + pcm
    parsed_meta, parsed_pcm = _unpack_binary_result(frame)
    assert parsed_meta["seq"] == 3
    assert parsed_meta["covers"] == [2, 3]
    assert parsed_pcm == pcm


def test_stale_hop_dropped_and_not_queued(tmp_path: Path):
    logger = HopLogger(path=tmp_path / "hops.jsonl")
    client = SeparationClient(hop_logger=logger, url="ws://127.0.0.1:19999/separate", token="tok")
    client._connected = True  # simulate active connection without sender running
    client._active_engine = "B-GPU"

    pcm = np.zeros(8000, dtype="<i2").tobytes()

    # 1. Stale hop (800 ms old > 500 * 1.15) must be dropped immediately
    ok_stale = client.submit_hop(
        session_id="s1",
        seq=0,
        target_face_id="face-1",
        reset=False,
        pcm_bytes=pcm,
        jpegs=[],
        t_capture=(time.time() * 1000.0) - 800.0,
        hop_ms=500,
    )
    assert ok_stale is False
    assert logger.hops_dropped == 1

    # 2. Fresh hop followed immediately by newer fresh hop overwrites mailbox (no queue)
    now_ms = time.time() * 1000.0
    assert client.submit_hop(
        session_id="s1",
        seq=1,
        target_face_id="face-1",
        reset=True,
        pcm_bytes=pcm,
        jpegs=[],
        t_capture=now_ms,
        hop_ms=500,
    )
    assert client.submit_hop(
        session_id="s1",
        seq=2,
        target_face_id="face-1",
        reset=False,
        pcm_bytes=pcm,
        jpegs=[],
        t_capture=now_ms,
        hop_ms=500,
    )
    assert client._latest_hop is not None
    assert client._latest_hop.seq == 2
    assert client._latest_hop.reset is True  # preserved from superseded hop!
    assert logger.hops_dropped == 2

    # Verify n_crops is logged in hops.jsonl for dropped hops and result hops
    logger.log_result(
        session_id="s1",
        seq=3,
        covers=[3, 3],
        target_face_id="face-1",
        reset=False,
        engine="B-GPU",
        hop_ms=500,
        t_capture=now_ms,
        t_send_ms=now_ms + 2.0,
        t_return_ms=now_ms + 240.0,
        gpu_ms=129.0,
        queue_ms=0.4,
        gpu_rtt_ms=238.0,
        rtt_ms=240.0,
        playback_buf_ms=150.0,
        samples=8000,
        n_crops=12,
    )
    lines = [json.loads(line) for line in (tmp_path / "hops.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["status"] == "dropped_stale"
    assert lines[0]["n_crops"] == 0
    assert lines[-1]["status"] == "ok"
    assert lines[-1]["n_crops"] == 12
    assert logger.snapshot()["last_n_crops"] == 12


def test_player_30s_continuity_and_crossfade():
    player = LiveAudioPlayer(prefill_ms=150, max_buffer_ms=700, enabled=True)
    # Feed 60 hops of 0.5 s (30 s total) of 440 Hz sine while draining 20 ms blocks
    t_idx = 0
    block_frames = 320  # 20 ms
    # Pre-feed first hop to prime
    hop_samples = 8000
    for hop in range(60):
        t = (np.arange(hop_samples) + t_idx) / float(SR)
        t_idx += hop_samples
        wave = (0.4 * np.sin(2.0 * np.pi * 440.0 * t) * 32767.0).astype("<i2").tobytes()
        # Simulate discontinuity on hop 20 (target switch)
        player.enqueue_pcm16(wave, discontinuous=(hop == 20))
        # Drain 25 blocks (500 ms) per hop
        for _ in range(25):
            block = player.render_block(block_frames)
            assert block.shape == (block_frames,)
            assert np.all(np.isfinite(block))

    st = player.stats()
    assert st["gaps_over_300ms"] == 0
    assert st["max_gap_ms"] == 0.0
    assert st["total_played_s"] >= 29.5


def test_player_detects_gap_over_300ms_and_caps_drift():
    player = LiveAudioPlayer(prefill_ms=150, max_buffer_ms=600, enabled=True)
    pcm = (np.ones(8000, dtype="<i2") * 1000).tobytes()

    # Overfeed 2 s of audio -> must cap buffer near trim target, never grow unbounded
    for _ in range(4):
        player.enqueue_pcm16(pcm)
    assert player.buffer_ms() <= 600.0
    assert player.stats()["trimmed_ms"] > 0.0

    # Drain everything plus 400 ms (20 blocks of 20 ms) to force an underrun > 300 ms
    while player.buffer_ms() > 0:
        player.render_block(320)
    for _ in range(20):
        player.render_block(320)
    # Resume with new audio to close the underrun event
    player.enqueue_pcm16(pcm)
    player.render_block(320)
    st = player.stats()
    assert st["gaps_over_300ms"] >= 1
    assert st["max_gap_ms"] >= 380.0


def test_consent_and_clip_store_privacy_enforcement(tmp_path: Path):
    consent = ConsentStore(path=tmp_path / "consent.json")
    clips = ClipStore(consent, clips_dir=tmp_path / "clips")
    pcm = np.zeros(8000, dtype="<i2").tobytes()

    # Without consent -> MUST deny
    with pytest.raises(ConsentDeniedError) as exc:
        clips.start_recording(clip_id="c1", face_ids=["face-1", "face-2"])
    assert "face-1" in exc.value.missing_faces

    with pytest.raises(ConsentDeniedError):
        clips.save_clip(clip_id="c1", face_ids=["face-1"], raw_pcm=pcm)

    # Give consent to face-1 only -> still denies when face-2 is present
    consent.set_consent("face-1", given=True, by="Saran", label="Alice")
    with pytest.raises(ConsentDeniedError) as exc2:
        clips.start_recording(clip_id="c1", face_ids=["face-1", "face-2"])
    assert exc2.value.missing_faces == ["face-2"]

    # Start recording with consenting face-1, then face-2 (no consent) enters -> aborts!
    clips.start_recording(clip_id="c2", face_ids=["face-1"])
    assert clips.is_recording is True
    clips.append_live_audio(raw_pcm=pcm, visible_face_ids=["face-1"])
    clips.append_live_audio(raw_pcm=pcm, visible_face_ids=["face-1", "face-2"])
    assert clips.is_recording is False

    # Consent both faces -> saves cleanly
    consent.set_consent("face-2", given=True, by="Saran", label="Bob")
    clips.start_recording(clip_id="c3", face_ids=["face-1", "face-2"])
    clips.append_live_audio(raw_pcm=pcm, clean_pcm=pcm, visible_face_ids=["face-1", "face-2"])
    res = clips.stop_recording()
    assert res["saved"] is True
    assert (tmp_path / "clips" / "c3_raw.wav").exists()
    assert (tmp_path / "clips" / "c3_clean.wav").exists()
    assert (tmp_path / "clips" / "c3.json").exists()


def test_end_card_empty_and_gate_rule(tmp_path: Path):
    # Empty CSVs -> null metrics, gate False
    (tmp_path / "clips.csv").write_text(
        "clip_id,time_et,talkers,target_face,distance_m,angle,noise_db,occlusion,consent_ids,truth_target,truth_others,b0_text,b0_wer,b0_leak,a_text,a_wer,a_leak,a_time_s,b_text,b_wer,b_leak,b_time_s,notes\n",
        encoding="utf-8",
    )
    (tmp_path / "decisions.csv").write_text(
        "clip_id,face_id,window_t0,window_t1,truth_speaking,p_decision,latency_ms,notes\n",
        encoding="utf-8",
    )
    (tmp_path / "robot.csv").write_text(
        "pair_id,time_et,target_face,target_command,other_command,object_truth,point_object,correct,hook_denied_other,latency_ms,notes\n",
        encoding="utf-8",
    )
    empty_card = build_end_card_data(repo_root=tmp_path)
    assert empty_card["set_c"]["n_clips"] == 0
    assert empty_card["set_c"]["b0_leak_pct"] is None
    assert empty_card["set_c"]["beats_raw_gate_passed"] is False

    # 30 clips with 40% -> 10% leakage drop (30 pts >= 20) and WER 15% -> 18% (+3 pts <= 5)
    rows = [
        f"c{i},12:00,2,face-1,1,front,60,none,face-1|face-2,hi,yo,hi yo,0.15,0.40,hi,0.22,0.20,1.5,hi,0.18,0.10,1.1,"
        for i in range(30)
    ]
    (tmp_path / "clips.csv").write_text(
        "clip_id,time_et,talkers,target_face,distance_m,angle,noise_db,occlusion,consent_ids,truth_target,truth_others,b0_text,b0_wer,b0_leak,a_text,a_wer,a_leak,a_time_s,b_text,b_wer,b_leak,b_time_s,notes\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    card = build_end_card_data(repo_root=tmp_path)
    assert card["set_c"]["n_clips"] == 30
    assert card["set_c"]["b0_leak_pct"] == 40.0
    assert card["set_c"]["engine_b_leak_pct"] == 10.0
    assert card["set_c"]["beats_raw_gate_passed"] is True


def test_at14_failover_within_3s_three_of_three(tmp_path: Path):
    """AT14: Kill the GPU server mid-run -> switches to Engine A within 3 s, 3 of 3."""
    asyncio.run(_run_at14_trials(tmp_path))


async def _run_at14_trials(tmp_path: Path):
    for trial in range(3):
        received = []
        engine_events: list[tuple[str, str, float]] = []

        async def on_res(res):
            received.append(res)

        async def on_eng(eng, reason):
            engine_events.append((eng, reason, time.perf_counter()))

        async def mock_gpu(ws):
            async for msg in ws:
                n = struct.unpack_from("<I", msg, 0)[0]
                h = json.loads(msg[4 : 4 + n].decode("utf-8"))
                pcm = np.zeros(8000, dtype="<i2").tobytes()
                meta = json.dumps(
                    {
                        "seq": h["seq"],
                        "covers": [h["seq"], h["seq"]],
                        "samples": 8000,
                        "gpu_ms": 20.0,
                        "queue_ms": 0.5,
                        "sent_ms": h["sent_ms"],
                    }
                ).encode("utf-8")
                await ws.send(struct.pack("<I", len(meta)) + meta + pcm)

        server = await websockets.serve(mock_gpu, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        logger = HopLogger(path=tmp_path / f"hops_{trial}.jsonl")
        client = SeparationClient(
            hop_logger=logger,
            on_result=on_res,
            on_engine_change=on_eng,
            url=f"ws://127.0.0.1:{port}/separate",
            token="test-token",
            failover_timeout_s=1.5,
        )
        await client.start()
        # Wait briefly for WS connect
        for _ in range(30):
            if client.is_gpu_connected:
                break
            await asyncio.sleep(0.05)
        assert client.active_engine == "B-GPU"

        # Send 1 hop with 12 crops and confirm result + n_crops logged in hops.jsonl
        pcm = np.zeros(8000, dtype="<i2").tobytes()
        jpegs = [b"\xff\xd8crop\xff\xd9"] * 12
        client.submit_hop(
            session_id="at14",
            seq=0,
            target_face_id="face-1",
            reset=True,
            pcm_bytes=pcm,
            jpegs=jpegs,
            t_capture=time.time() * 1000.0,
            hop_ms=500,
        )
        for _ in range(40):
            if received:
                break
            await asyncio.sleep(0.05)
        assert len(received) == 1

        # Kill the mock GPU server mid-run!
        t_kill = time.perf_counter()
        server.close()
        await server.wait_closed()

        # Wait up to 3.0 s for automatic failover to Engine A
        failover_s = None
        for _ in range(60):
            if client.active_engine == "A":
                failover_s = time.perf_counter() - t_kill
                break
            await asyncio.sleep(0.05)

        await client.stop()
        assert failover_s is not None, f"Trial {trial}: did not fail over to Engine A"
        assert failover_s <= 3.0, f"Trial {trial}: failover took {failover_s:.2f}s (> 3.0s)"
        disk_stats = read_hops_stats_from_disk(tmp_path / f"hops_{trial}.jsonl")
        assert disk_stats["hops_logged"] == 1
        ok_lines = [
            json.loads(line)
            for line in (tmp_path / f"hops_{trial}.jsonl").read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("status") == "ok"
        ]
        assert ok_lines[0]["n_crops"] == 12


def test_fastapi_endpoints_and_consent_gate(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    import backend.main as main_mod

    # Isolate consent/clip stores in tmp_path and disable live hardware during unit test
    rt = main_mod.get_runtime()
    orig_consent = rt.consent
    orig_clips = rt.clips
    rt.consent = ConsentStore(path=tmp_path / "consent.json")
    rt.clips = ClipStore(rt.consent, clips_dir=tmp_path / "clips")
    monkeypatch.setattr(rt.player, "start", lambda: False)
    monkeypatch.setattr(rt.separator, "start", lambda: asyncio.sleep(0))
    monkeypatch.setattr(rt.separator, "stop", lambda: asyncio.sleep(0))

    try:
        with TestClient(main_mod.app) as tc:
            r_health = tc.get("/api/health")
            assert r_health.status_code == 200
            assert r_health.json()["ok"] is True

            r_card = tc.get("/api/end_card")
            assert r_card.status_code == 200
            assert "set_c" in r_card.json()

            # Recording without consent -> HTTP 403
            r_deny = tc.post("/api/clips/start", json={"clip_id": "test-deny", "face_ids": ["face-9"]})
            assert r_deny.status_code == 403

            # Grant consent -> HTTP 200
            r_c = tc.post("/api/consent", json={"face_id": "face-9", "given": True, "by": "Saran"})
            assert r_c.status_code == 200
            r_ok = tc.post("/api/clips/start", json={"clip_id": "test-ok", "face_ids": ["face-9"]})
            assert r_ok.status_code == 200
            r_stop = tc.post("/api/clips/stop")
            assert r_stop.status_code == 200
            assert r_stop.json()["ok"] is True
    finally:
        rt.consent = orig_consent
        rt.clips = orig_clips


def test_playback_disabled_by_default_and_ws_live_sends_clean_pcm(tmp_path: Path, monkeypatch):
    """Browser VoicePlayer is the only voice player by default (PLAYBACK_ENABLED=0)
    so Chrome's AEC cancels its own audio. Verify /ws/live delivers clean int16 PCM.
    """
    from fastapi.testclient import TestClient
    import backend.main as main_mod
    from backend.separation.client import SeparationResult

    monkeypatch.delenv("PLAYBACK_ENABLED", raising=False)
    default_player = LiveAudioPlayer()
    assert default_player.enabled is False
    assert default_player.start() is False
    assert default_player.device_ok is False
    assert default_player.effective_playback_buf_ms() == 150.0

    # Verify /ws/live streams clean PCM in hop_result matching S2's VoicePlayer contract
    rt = main_mod.get_runtime()
    monkeypatch.setattr(rt.player, "start", lambda: False)
    monkeypatch.setattr(rt.separator, "start", lambda: asyncio.sleep(0))
    monkeypatch.setattr(rt.separator, "stop", lambda: asyncio.sleep(0))
    rt.player.set_enabled(False)

    expected_samples = (np.sin(np.linspace(0, 20, 8000)) * 12000).astype("<i2")
    expected_pcm = expected_samples.tobytes()

    with TestClient(main_mod.app) as tc:
        r_health = tc.get("/health").json()
        assert r_health["playback"]["enabled"] is False

        with tc.websocket_connect("/ws/live") as ws:
            # Consume initial engine_status + metrics handshake
            m1 = ws.receive_json()
            assert m1["type"] == "engine_status"
            m2 = ws.receive_json()
            assert m2["type"] == "metrics"

            # Emit a separation result through runtime (as GPU client does)
            res = SeparationResult(
                session_id="test-browser-voice",
                seq=5,
                covers=[5, 5],
                samples=8000,
                pcm_bytes=expected_pcm,
                gpu_ms=128.5,
                queue_ms=0.4,
                gpu_rtt_ms=235.0,
                rtt_ms=240.0,
                t_capture=1795280000000.0,
                t_return=1795280000240.0,
                sent_ms=1795280000005.0,
                engine="B-GPU",
                voice_delay_ms=890.0,
            )
            # Trigger broadcast from the portal loop used by TestClient
            tc.portal.call(rt._on_separation_result, res)

            # Find hop_result frame on /ws/live
            hop_msg = None
            for _ in range(15):
                msg = ws.receive_json()
                if msg.get("type") == "hop_result":
                    hop_msg = msg
                    break

            assert hop_msg is not None
            payload = hop_msg["payload"]
            assert payload["seq"] == 5
            assert payload["samples"] == 8000
            assert payload["engine"] == "B-GPU"
            decoded = base64.b64decode(payload["pcm"])
            assert decoded == expected_pcm
            # Backend player stayed muted (enqueued 0)
            assert rt.player.stats()["enabled"] is False


def test_jitter_no_flap_and_failover_after_3_timeouts_or_no_reply(tmp_path: Path):
    """Single slow reply drops hop as stale without flipping to Engine A.
    3 consecutive timeouts OR sustained no-reply (>= failover_timeout_s) fails over cleanly.
    """
    asyncio.run(_run_jitter_failover_tests(tmp_path))


async def _run_jitter_failover_tests(tmp_path: Path):
    pcm = np.zeros(8000, dtype="<i2").tobytes()

    # --- Case 1: One slow hop (Wi-Fi jitter) -> drop as stale, stay on B-GPU (0 flips to A) ---
    engine_flips_1: list[tuple[str, str]] = []
    results_1 = []

    async def mock_jitter(ws):
        async for msg in ws:
            n = struct.unpack_from("<I", msg, 0)[0]
            h = json.loads(msg[4 : 4 + n].decode("utf-8"))
            if h["seq"] == 1:
                await asyncio.sleep(0.55)  # slower than hop_timeout_s=0.35, faster than failover=1.4
            meta = json.dumps(
                {"seq": h["seq"], "covers": [h["seq"], h["seq"]], "samples": 8000, "gpu_ms": 15.0, "queue_ms": 0.2, "sent_ms": h["sent_ms"]}
            ).encode("utf-8")
            await ws.send(struct.pack("<I", len(meta)) + meta + pcm)

    srv1 = await websockets.serve(mock_jitter, "127.0.0.1", 0)
    port1 = srv1.sockets[0].getsockname()[1]
    logger1 = HopLogger(path=tmp_path / "jitter.jsonl")
    c1 = SeparationClient(
        hop_logger=logger1,
        on_result=lambda r: _append_async(results_1, r),
        on_engine_change=lambda e, r: _append_async(engine_flips_1, (e, r)),
        url=f"ws://127.0.0.1:{port1}/separate",
        token="tok",
        hop_timeout_s=0.35,
        max_consecutive_timeouts=3,
        failover_timeout_s=1.4,
    )
    await c1.start()
    for _ in range(30):
        if c1.is_gpu_connected:
            break
        await asyncio.sleep(0.05)

    # Hop 0 (fast), Hop 1 (slow -> dropped stale), wait for late reply, Hop 2 (fast)
    c1.submit_hop(session_id="j1", seq=0, target_face_id="f1", reset=True, pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
    await asyncio.sleep(0.15)
    c1.submit_hop(session_id="j1", seq=1, target_face_id="f1", reset=False, pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
    await asyncio.sleep(0.75)
    c1.submit_hop(session_id="j1", seq=2, target_face_id="f1", reset=False, pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
    await asyncio.sleep(0.25)

    assert c1.active_engine == "B-GPU"
    assert all(e != "A" for e, _ in engine_flips_1 if "startup" not in _), f"Unexpected flap to A: {engine_flips_1}"
    assert [r.seq for r in results_1] == [0, 2]  # Hop 1 was dropped as stale, 0 and 2 delivered
    assert logger1.hops_dropped >= 1
    await c1.stop()
    srv1.close()
    await srv1.wait_closed()

    # --- Case 2: 3 consecutive slow hops -> fails over to Engine A ---
    async def mock_3slow(ws):
        async for msg in ws:
            n = struct.unpack_from("<I", msg, 0)[0]
            h = json.loads(msg[4 : 4 + n].decode("utf-8"))
            await asyncio.sleep(0.45)  # every hop exceeds hop_timeout_s=0.25
            meta = json.dumps(
                {"seq": h["seq"], "covers": [h["seq"], h["seq"]], "samples": 8000, "gpu_ms": 15.0, "queue_ms": 0.2, "sent_ms": h["sent_ms"]}
            ).encode("utf-8")
            try:
                await ws.send(struct.pack("<I", len(meta)) + meta + pcm)
            except Exception:
                break

    srv2 = await websockets.serve(mock_3slow, "127.0.0.1", 0)
    port2 = srv2.sockets[0].getsockname()[1]
    c2 = SeparationClient(
        hop_logger=HopLogger(path=tmp_path / "3slow.jsonl"),
        url=f"ws://127.0.0.1:{port2}/separate",
        token="tok",
        hop_timeout_s=0.25,
        max_consecutive_timeouts=3,
        failover_timeout_s=5.0,  # isolate consecutive-timeout trigger
    )
    await c2.start()
    for _ in range(30):
        if c2.is_gpu_connected:
            break
        await asyncio.sleep(0.05)

    for seq in range(4):
        c2.submit_hop(session_id="j2", seq=seq, target_face_id="f1", reset=(seq == 0), pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
        await asyncio.sleep(0.45)
        if c2.active_engine == "A":
            break
    assert c2.active_engine == "A"
    assert "gpu_consecutive_timeouts:3" in c2.engine_reason
    await c2.stop()
    srv2.close()
    await srv2.wait_closed()

    # --- Case 3: No reply at all (server hang/blackhole) -> fails over after failover_timeout_s ---
    async def mock_blackhole(ws):
        async for _ in ws:
            await asyncio.sleep(10.0)

    srv3 = await websockets.serve(mock_blackhole, "127.0.0.1", 0)
    port3 = srv3.sockets[0].getsockname()[1]
    c3 = SeparationClient(
        hop_logger=HopLogger(path=tmp_path / "blackhole.jsonl"),
        url=f"ws://127.0.0.1:{port3}/separate",
        token="tok",
        hop_timeout_s=0.5,
        max_consecutive_timeouts=5,  # isolate no-reply timer
        failover_timeout_s=0.9,
    )
    await c3.start()
    for _ in range(30):
        if c3.is_gpu_connected:
            break
        await asyncio.sleep(0.05)

    t0 = time.perf_counter()
    c3.submit_hop(session_id="j3", seq=0, target_face_id="f1", reset=True, pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
    for _ in range(40):
        if c3.active_engine == "A":
            break
        await asyncio.sleep(0.05)
    elapsed = time.perf_counter() - t0
    assert c3.active_engine == "A"
    assert c3.engine_reason == "gpu_no_reply_timeout"
    assert 0.85 <= elapsed <= 1.8
    await c3.stop()
    srv3.close()
    await srv3.wait_closed()


async def _append_async(lst, item):
    lst.append(item)


def test_recovery_from_engine_a_after_2_good_probes(tmp_path: Path):
    """After failover to Engine A, client probes periodically and switches back to B-GPU
    only after 2 consecutive good replies, then resumes processing hops.
    """
    asyncio.run(_run_recovery_test(tmp_path))


async def _run_recovery_test(tmp_path: Path):
    pcm = np.zeros(8000, dtype="<i2").tobytes()
    mode = {"slow": True}
    results = []
    engine_events: list[tuple[str, str]] = []

    async def mock_recoverable(ws):
        async for msg in ws:
            n = struct.unpack_from("<I", msg, 0)[0]
            h = json.loads(msg[4 : 4 + n].decode("utf-8"))
            if mode["slow"]:
                await asyncio.sleep(0.5)
            meta = json.dumps(
                {"seq": h["seq"], "covers": [h["seq"], h["seq"]], "samples": 8000, "gpu_ms": 15.0, "queue_ms": 0.2, "sent_ms": h["sent_ms"]}
            ).encode("utf-8")
            try:
                await ws.send(struct.pack("<I", len(meta)) + meta + pcm)
            except Exception:
                break

    srv = await websockets.serve(mock_recoverable, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    logger = HopLogger(path=tmp_path / "recovery.jsonl")
    c = SeparationClient(
        hop_logger=logger,
        on_result=lambda r: _append_async(results, r),
        on_engine_change=lambda e, r: _append_async(engine_events, (e, r)),
        url=f"ws://127.0.0.1:{port}/separate",
        token="tok",
        hop_timeout_s=0.25,
        max_consecutive_timeouts=3,
        failover_timeout_s=5.0,
        probe_interval_s=0.25,
        recovery_probes_required=2,
    )
    await c.start()
    for _ in range(30):
        if c.is_gpu_connected:
            break
        await asyncio.sleep(0.05)

    # Trigger 3 consecutive timeouts -> failover to Engine A
    for seq in range(5):
        c.submit_hop(session_id="rec", seq=seq, target_face_id="f1", reset=(seq == 0), pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
        await asyncio.sleep(0.42)
        if c.active_engine == "A":
            break
    assert c.active_engine == "A"
    assert c._in_failover is True

    # GPU becomes healthy again; wait for reconnect + 2 good probes -> returns to B-GPU
    mode["slow"] = False
    for _ in range(60):
        if c.active_engine == "B-GPU":
            break
        await asyncio.sleep(0.05)
    assert c.active_engine == "B-GPU"
    assert c.engine_reason == "gpu_recovered"

    # Confirm hops flow again on B-GPU after recovery
    results.clear()
    c.submit_hop(session_id="rec", seq=99, target_face_id="f1", reset=False, pcm_bytes=pcm, jpegs=[], t_capture=time.time() * 1000.0, hop_ms=500)
    for _ in range(30):
        if results:
            break
        await asyncio.sleep(0.05)
    assert len(results) == 1
    assert results[0].seq == 99

    # Verify probe_ok events were logged
    events = [json.loads(l) for l in (tmp_path / "recovery.jsonl").read_text(encoding="utf-8").splitlines()]
    probe_oks = [e for e in events if e.get("status") == "probe_ok"]
    assert len(probe_oks) >= 2

    await c.stop()
    srv.close()
    await srv.wait_closed()


