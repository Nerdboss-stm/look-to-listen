"""Run B0 (raw), Engine A (Gemini AV), and Engine B-GPU (ClearVoice GPU + Live)
on the exact same recorded Set C clips through S1/S3's live code path (SPEC E27).

Never pollutes live logs/hops.jsonl (uses isolated evals/eval_hops.jsonl tagged mode='test').
Scores WER, leakage, and delay per contracts/eval.md, upserts clips.csv, and refreshes
evals/summary.json + SVG charts.

Usage:
  /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --clip c01
  /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --all
  /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --clip clips/set_c/c01 --arms b0,a,b
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "evals") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "evals"))

from dotenv import load_dotenv

import clip_io
import metrics
import score_all

EVAL_HOPS_PATH = REPO_ROOT / "clips" / "set_c" / "eval_hops.jsonl"
DEFAULT_SETS_ROOT = REPO_ROOT / "clips" / "set_c"
_ANON_ID_RE = None


def _validate_anonymous_consent_ids(consent_ids: str) -> str:
    """Ensure tracked clips.csv only ever gets anonymous IDs like P01;P02 (never real names)."""
    import re

    parts = [p.strip() for p in (consent_ids or "").split(";") if p.strip()]
    if not parts:
        raise ValueError("consent_ids is empty; expected anonymous IDs like P01;P02")
    bad = [p for p in parts if not re.match(r"^P\d{2,}$", p)]
    if bad:
        raise ValueError(
            f"Privacy rule: clips.csv must use anonymous IDs (P01, P02), never real names. Got: {bad}"
        )
    return ";".join(parts)


def merge_caption_segments(segments: list[dict[str, Any]]) -> str:
    """Join incremental or chunked caption texts cleanly without duplicating overlapping prefixes."""
    out: list[str] = []
    for seg in segments:
        t = (seg.get("text") or "").strip()
        if not t:
            continue
        if out and t.lower().startswith(out[-1].lower()):
            out[-1] = t
        elif out and out[-1].lower().endswith(t.lower()):
            continue
        else:
            out.append(t)
    return " ".join(out).strip()


def resolve_clip_dir(clip_arg: str, sets_root: Path) -> Path:
    p = Path(clip_arg)
    if p.exists():
        return p
    candidate = sets_root / clip_arg
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Clip not found: {clip_arg} (also checked {candidate})")


def load_clip_bundle(clip_dir: Path) -> tuple[dict[str, Any], list[clip_io.ClipHop]]:
    """Load clip metadata and exact 0.5 s hops (from hops.jsonl or decoded from video)."""
    meta_path = clip_dir / "meta.json"
    meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    clip_id = str(meta.get("clip_id") or clip_dir.name)
    meta["clip_id"] = clip_id

    consent_path = clip_dir / "consent.json"
    if not consent_path.exists() and not meta.get("consent_ids"):
        raise PermissionError(
            f"Privacy rule: clip {clip_id} has no consent.json or consent_ids. Refusing to process."
        )

    hops_path = clip_dir / "hops.jsonl"
    if hops_path.exists():
        hops = clip_io.load_hops_jsonl(hops_path)
    else:
        video = next(
            (p for name in ("mix.mp4", "mix.webm", "mix.mov", f"{clip_id}.mp4") if (p := clip_dir / name).exists()),
            None,
        )
        if video is None:
            raise FileNotFoundError(f"No hops.jsonl or video (mix.mp4) in {clip_dir}")
        hops = clip_io.build_hops_from_video(
            video,
            clip_id=clip_id,
            target_hint=str(meta.get("target_face") or "center"),
            explicit_box=meta.get("target_box_hint"),
        )
        clip_io.save_hops_jsonl(hops_path, hops)

    if not hops:
        raise ValueError(f"Clip {clip_id} has 0 hops")
    return meta, hops


async def run_decision_pass(
    hops: list[clip_io.ClipHop],
    *,
    decision_threshold: float = 0.9,
    guard_ms: int = 750,
    dry_run: bool = False,
) -> tuple[Any, list[dict[str, Any]]]:
    """Run S3's live SpeakingDecisionClient every 0.5 s on 1 s rolling windows -> LeakageGuard."""
    from backend.gemini.decisions import LeakageGuard, SpeakingDecisionClient

    guard = LeakageGuard(decision_threshold=decision_threshold, guard_ms=guard_ms)
    records: list[dict[str, Any]] = []
    client = None if dry_run else SpeakingDecisionClient()

    prev_pcm = b""
    prev_crops: list[bytes] = []
    for hop in hops:
        win_pcm = (prev_pcm + hop.pcm_bytes) if prev_pcm else hop.pcm_bytes
        win_crops = (prev_crops + hop.crops_jpegs) if prev_crops else hop.crops_jpegs
        t0 = max(0.0, hop.t_capture - (500.0 if prev_pcm else 0.0))
        t1 = hop.t_capture + 500.0
        mouth_open = None
        for f in hop.faces:
            if str(f.get("id")) == str(hop.target_face_id):
                mouth_open = f.get("mouth_open")
                break

        if dry_run:
            # Deterministic synthetic probability: speaking on hops 0..N-1 except silent test hops
            p = 0.95 if (hop.seq % 4 != 3) else 0.10
            dec = {
                "face_id": str(hop.target_face_id),
                "window_t0": round(t0, 1),
                "window_t1": round(t1, 1),
                "p_speaking": p,
                "latency_ms": 120.0,
                "calibrated": True,
                "source": "dry-run",
            }
        else:
            assert client is not None
            dec = await client.decide_window(
                win_crops,
                win_pcm,
                face_id=str(hop.target_face_id),
                window_t0=t0,
                window_t1=t1,
                mouth_open=mouth_open,
                prefer_frames=True,
            )

        guard.record(dec)
        records.append(dec)
        prev_pcm = hop.pcm_bytes
        prev_crops = hop.crops_jpegs

    return guard, records


async def run_arm_b0(
    hops: list[clip_io.ClipHop],
    *,
    use_chunked_asr: bool = False,
    dry_run: bool = False,
    dry_run_text: str = "",
) -> dict[str, Any]:
    """Arm B0: Raw captions of the mixed microphone audio via S3's LiveCaptionLane."""
    if dry_run:
        return {
            "arm": "b0",
            "text": dry_run_text,
            "segments": [{"text": dry_run_text, "latency_ms": 650.0}] if dry_run_text else [],
            "delay_p50_s": 0.65,
        }

    from backend.gemini.live_captioner import LiveCaptionLane

    collected: list[dict[str, Any]] = []

    async def on_text(seg: dict[str, Any]) -> None:
        collected.append(seg)

    lane = LiveCaptionLane(lane="raw", on_text=on_text, use_chunked_fallback=use_chunked_asr)
    await lane.start()
    await asyncio.sleep(0.6)  # let Live WS handshake settle
    try:
        t_start = time.perf_counter()
        for idx, hop in enumerate(hops):
            target_t = t_start + idx * 0.5
            sleep_s = target_t - time.perf_counter()
            if sleep_s > 0:
                await asyncio.sleep(sleep_s)
            lane.push_pcm16(hop.pcm_bytes, t_capture_ms=time.time() * 1000.0)
        # Trailing silence to flush final transcription words
        lane.push_pcm16(b"\x00" * 16000, t_capture_ms=time.time() * 1000.0)
        await asyncio.sleep(2.5)
    finally:
        await lane.stop()

    text = merge_caption_segments(collected)
    lats = [float(s["latency_ms"]) / 1000.0 for s in collected if s.get("latency_ms") is not None]
    return {
        "arm": "b0",
        "text": text,
        "segments": collected,
        "delay_p50_s": round(statistics.median(lats), 3) if lats else None,
        "asr_mode": lane.active_mode,
    }


async def run_arm_engine_a(
    hops: list[clip_io.ClipHop],
    *,
    guard: Any | None = None,
    dry_run: bool = False,
    dry_run_text: str = "",
) -> dict[str, Any]:
    """Arm Engine A: S3's EngineALiveBuffer (2 s AV chunks + green target box) + LeakageGuard."""
    if dry_run:
        kept_segs: list[dict[str, Any]] = []
        dropped = 0
        words = dry_run_text.split()
        chunk_words = max(1, (len(words) + max(1, len(hops) // 4) - 1) // max(1, len(hops) // 4)) if words else 0
        for idx in range(0, len(hops), 4):
            t0 = hops[idx].t_capture
            t1 = hops[min(len(hops) - 1, idx + 3)].t_capture + 500.0
            part = " ".join(words[(idx // 4) * chunk_words : (idx // 4 + 1) * chunk_words]) if chunk_words else ""
            if not part:
                continue
            allow = True
            if guard is not None:
                allow, _ = guard.allow_target_segment(hops[idx].target_face_id, t0, t1)
            if allow:
                kept_segs.append({"t0": t0, "t1": t1, "text": part, "latency_ms": 1400.0})
            else:
                dropped += 1
        return {
            "arm": "a",
            "text": merge_caption_segments(kept_segs),
            "segments": kept_segs,
            "dropped_by_guard": dropped,
            "delay_p50_s": 2.4,
        }

    from backend.gemini.engine_a import EngineALiveBuffer

    buf = EngineALiveBuffer(chunk_hops=4)
    kept: list[dict[str, Any]] = []
    dropped = 0
    delays_s: list[float] = []

    for hop in hops:
        frame_b64 = base64.b64encode(hop.frame_jpeg).decode("ascii") if hop.frame_jpeg else None
        if frame_b64 is None and hop.crops_jpegs:
            frame_b64 = base64.b64encode(hop.crops_jpegs[len(hop.crops_jpegs) // 2]).decode("ascii")

        chunk = buf.push_hop(
            pcm_bytes=hop.pcm_bytes,
            frame_jpeg_b64=frame_b64,
            faces=hop.faces,
            target_face_id=hop.target_face_id,
            t_capture_ms=hop.t_capture,
            reset=hop.reset,
        )
        if chunk is not None:
            seg = await buf.process_chunk(chunk)
            if seg and seg.get("text"):
                allow = True
                max_p = None
                if guard is not None:
                    allow, max_p = guard.allow_target_segment(
                        seg.get("face_id"), float(seg["t0"]), float(seg["t1"])
                    )
                seg["guard_p"] = max_p
                if allow:
                    kept.append(seg)
                    # End-to-end caption delay: half chunk collect (1.0 s) + model latency
                    delays_s.append(1.0 + float(seg.get("latency_ms", 0.0)) / 1000.0)
                else:
                    dropped += 1

    return {
        "arm": "a",
        "text": merge_caption_segments(kept),
        "segments": kept,
        "dropped_by_guard": dropped,
        "delay_p50_s": round(statistics.median(delays_s), 3) if delays_s else None,
    }


async def run_arm_b_gpu(
    hops: list[clip_io.ClipHop],
    *,
    clip_dir: Path,
    guard: Any | None = None,
    use_chunked_asr: bool = False,
    dry_run: bool = False,
    dry_run_text: str = "",
) -> dict[str, Any]:
    """Arm Engine B-GPU: S1's SeparationClient -> S3's LiveCaptionLane -> LeakageGuard."""
    if dry_run:
        kept_segs: list[dict[str, Any]] = []
        dropped = 0
        if dry_run_text:
            t0, t1 = hops[0].t_capture, hops[-1].t_capture + 500.0
            allow = True
            if guard is not None:
                allow, _ = guard.allow_target_segment(hops[0].target_face_id, t0, t1)
            if allow:
                kept_segs.append({"t0": t0, "t1": t1, "text": dry_run_text, "latency_ms": 950.0})
            else:
                dropped += 1
        return {
            "arm": "b",
            "text": merge_caption_segments(kept_segs),
            "segments": kept_segs,
            "dropped_by_guard": dropped,
            "delay_p50_s": 1.85,
            "voice_delay_p50_ms": 880.0,
            "gpu_p50_ms": 130.0,
            "hops_returned": len(hops),
        }

    from backend.gemini.live_captioner import LiveCaptionLane
    from backend.separation.client import SeparationClient, SeparationResult
    from backend.separation.hop_logger import HopLogger

    eval_hop_logger = HopLogger(path=EVAL_HOPS_PATH)
    clean_pcm = bytearray()
    voice_delays_ms: list[float] = []
    gpu_ms_vals: list[float] = []
    hops_returned = 0

    kept: list[dict[str, Any]] = []
    dropped = 0
    caption_delays_s: list[float] = []

    # Map wall-clock t_capture back to clip-relative timeline for LeakageGuard lookup
    t0_wall_ms: list[float] = []

    async def on_text(seg: dict[str, Any]) -> None:
        nonlocal dropped
        clip_offset_ms = (float(seg["t1"]) - t0_wall_ms[0]) if t0_wall_ms else 0.0
        seg_t0 = max(0.0, clip_offset_ms - 500.0)
        seg_t1 = max(seg_t0, clip_offset_ms)
        allow = True
        max_p = None
        if guard is not None:
            allow, max_p = guard.allow_target_segment(seg.get("face_id"), seg_t0, seg_t1)
        seg["guard_p"] = max_p
        if allow:
            kept.append(seg)
            v_ms = statistics.median(voice_delays_ms) if voice_delays_ms else 1000.0
            asr_ms = float(seg.get("latency_ms", 0.0))
            caption_delays_s.append((v_ms + asr_ms) / 1000.0)
        else:
            dropped += 1

    target_lane = LiveCaptionLane(
        lane="target", on_text=on_text, use_chunked_fallback=use_chunked_asr
    )

    async def on_sep_result(res: SeparationResult) -> None:
        nonlocal hops_returned
        hops_returned += 1
        clean_pcm.extend(res.pcm_bytes)
        voice_delays_ms.append(res.voice_delay_ms)
        gpu_ms_vals.append(res.gpu_ms)
        target_lane.push_pcm16(
            res.pcm_bytes,
            t_capture_ms=res.t_capture if res.t_capture is not None else time.time() * 1000.0,
            face_id=hops[0].target_face_id,
        )

    sep_client = SeparationClient(
        hop_logger=eval_hop_logger,
        on_result=on_sep_result,
        playback_buf_ms_provider=lambda: 150.0,
    )

    await target_lane.start()
    await sep_client.start()
    # Wait up to 3 s for GPU WebSocket to connect
    for _ in range(30):
        if sep_client.is_gpu_connected:
            break
        await asyncio.sleep(0.1)
    if not sep_client.is_gpu_connected:
        await sep_client.stop()
        await target_lane.stop()
        raise RuntimeError(
            "Engine B-GPU separation client could not connect. Is tunnel.sh running on localhost:18000?"
        )

    try:
        t_start = time.perf_counter()
        t0_wall_ms.append(time.time() * 1000.0)
        eval_sid = f"eval-b-gpu-{clip_dir.name}-{int(time.time())}"
        for idx, hop in enumerate(hops):
            target_t = t_start + idx * 0.5
            sleep_s = target_t - time.perf_counter()
            if sleep_s > 0:
                await asyncio.sleep(sleep_s)
            sep_client.submit_hop(
                session_id=eval_sid,
                seq=hop.seq,
                target_face_id=hop.target_face_id,
                reset=hop.reset,
                pcm_bytes=hop.pcm_bytes,
                jpegs=hop.crops_jpegs,
                t_capture=time.time() * 1000.0,
                hop_ms=500,
            )
        # Allow last hop to return from GPU + flush final target captions
        await asyncio.sleep(1.5)
        target_lane.push_pcm16(b"\x00" * 16000, t_capture_ms=time.time() * 1000.0, face_id=hops[0].target_face_id)
        await asyncio.sleep(2.5)
    finally:
        await sep_client.stop()
        await target_lane.stop()

    if clean_pcm:
        clip_io.write_wav16(clip_dir / "b_gpu_clean.wav", bytes(clean_pcm))

    return {
        "arm": "b",
        "text": merge_caption_segments(kept),
        "segments": kept,
        "dropped_by_guard": dropped,
        "delay_p50_s": round(statistics.median(caption_delays_s), 3) if caption_delays_s else None,
        "voice_delay_p50_ms": round(statistics.median(voice_delays_ms), 1) if voice_delays_ms else None,
        "gpu_p50_ms": round(statistics.median(gpu_ms_vals), 1) if gpu_ms_vals else None,
        "hops_returned": hops_returned,
        "asr_mode": target_lane.active_mode,
    }


async def evaluate_clip(
    clip_dir: Path,
    *,
    arms: set[str],
    use_guard: bool = True,
    use_chunked_asr: bool = False,
    clips_csv: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    meta, hops = load_clip_bundle(clip_dir)
    clip_id = meta["clip_id"]
    if not meta.get("truth_verified"):
        raise ValueError(
            f"Clip {clip_id} has unverified truth (truth_verified={meta.get('truth_verified')}). "
            f"An ASR draft is only a draft — a human must confirm or correct it via "
            f"'evals/record_set_c.py --fill-truth {clip_id}' before the clip counts."
        )
    anon_consent_ids = _validate_anonymous_consent_ids(str(meta.get("consent_ids") or ""))
    truth_t = str(meta.get("truth_target") or "")
    truth_o = str(meta.get("truth_others") or "")

    print(f"\n=== Evaluating clip {clip_id} ({len(hops)} hops = {len(hops)*0.5:.1f} s, arms={sorted(arms)}) ===")

    guard = None
    decisions_raw: list[dict[str, Any]] = []
    if use_guard and (("a" in arms) or ("b" in arms)):
        guard, decisions_raw = await run_decision_pass(hops, dry_run=dry_run)
        (clip_dir / "decisions_raw.json").write_text(
            json.dumps(decisions_raw, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  Decision 1 pass: {len(decisions_raw)} windows logged -> {clip_dir / 'decisions_raw.json'}")

    arm_outputs: dict[str, Any] = {}
    # Privacy rule: tracked clips.csv receives ONLY anonymous P01;P02 IDs and numeric metrics.
    # Real names, truth text, and arm transcripts stay ONLY in gitignored clips/set_c/<clip_id>/.
    csv_row: dict[str, Any] = {
        "clip_id": clip_id,
        "time_et": meta.get("time_et") or datetime.now().strftime("%H:%M"),
        "talkers": meta.get("talkers", 2),
        "target_face": meta.get("target_face", hops[0].target_face_id),
        "distance_m": meta.get("distance_m", ""),
        "angle": meta.get("angle", ""),
        "noise_db": meta.get("noise_db", ""),
        "occlusion": meta.get("occlusion", "none"),
        "consent_ids": anon_consent_ids,
        "truth_target": "",
        "truth_others": "",
        "notes": meta.get("notes") or meta.get("network", ""),
    }

    if "b0" in arms:
        res = await run_arm_b0(
            hops,
            use_chunked_asr=use_chunked_asr,
            dry_run=dry_run,
            dry_run_text=f"{truth_t} {truth_o}".strip(),
        )
        w = metrics.compute_wer(truth_t, res["text"]) if truth_t.strip() else None
        lk, _, _ = metrics.compute_leakage(truth_t, truth_o, res["text"]) if truth_t.strip() else (None, 0, 0)
        res["wer"] = w
        res["leak"] = lk
        arm_outputs["b0"] = res
        csv_row["b0_text"] = ""
        csv_row["b0_wer"] = "" if w is None else f"{w:.4f}"
        csv_row["b0_leak"] = "" if lk is None else f"{lk:.4f}"
        print(f"  [B0 raw]   wer={w} leak={lk} delay={res['delay_p50_s']}s")

    if "a" in arms:
        res = await run_arm_engine_a(
            hops,
            guard=guard,
            dry_run=dry_run,
            dry_run_text=(f"{truth_t} {(truth_o.split()[:1] or [''])[0]}").strip(),
        )
        w = metrics.compute_wer(truth_t, res["text"]) if truth_t.strip() else None
        lk, _, _ = metrics.compute_leakage(truth_t, truth_o, res["text"]) if truth_t.strip() else (None, 0, 0)
        res["wer"] = w
        res["leak"] = lk
        arm_outputs["a"] = res
        csv_row["a_text"] = ""
        csv_row["a_wer"] = "" if w is None else f"{w:.4f}"
        csv_row["a_leak"] = "" if lk is None else f"{lk:.4f}"
        if res["delay_p50_s"] is not None:
            csv_row["a_time_s"] = f"{res['delay_p50_s']:.3f}"
        print(f"  [Engine A] wer={w} leak={lk} delay={res['delay_p50_s']}s")

    if "b" in arms:
        res = await run_arm_b_gpu(
            hops,
            clip_dir=clip_dir,
            guard=guard,
            use_chunked_asr=use_chunked_asr,
            dry_run=dry_run,
            dry_run_text=truth_t,
        )
        w = metrics.compute_wer(truth_t, res["text"]) if truth_t.strip() else None
        lk, _, _ = metrics.compute_leakage(truth_t, truth_o, res["text"]) if truth_t.strip() else (None, 0, 0)
        res["wer"] = w
        res["leak"] = lk
        arm_outputs["b"] = res
        csv_row["b_text"] = ""
        csv_row["b_wer"] = "" if w is None else f"{w:.4f}"
        csv_row["b_leak"] = "" if lk is None else f"{lk:.4f}"
        if res["delay_p50_s"] is not None:
            csv_row["b_time_s"] = f"{res['delay_p50_s']:.3f}"
        print(
            f"  [B-GPU]    wer={w} leak={lk} delay={res['delay_p50_s']}s "
            f"voice_p50={res.get('voice_delay_p50_ms')}ms"
        )

    out_report = {
        "clip_id": clip_id,
        "evaluated_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "n_hops": len(hops),
        "arms": arm_outputs,
        "csv_row": csv_row,
    }
    (clip_dir / "arms_result.json").write_text(
        json.dumps(out_report, indent=2, default=str) + "\n", encoding="utf-8"
    )

    target_csv = clips_csv or (REPO_ROOT / "clips.csv")
    clip_io.upsert_clips_csv(target_csv, csv_row)
    return out_report


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    ap = argparse.ArgumentParser(description="Run B0, Engine A, and B-GPU on Set C clips through the live path.")
    ap.add_argument("--clip", default="", help="Clip ID (under clips/set_c/) or path to clip directory")
    ap.add_argument("--all", action="store_true", help="Evaluate all verified clip directories in clips/set_c/")
    ap.add_argument("--sets-root", default=str(DEFAULT_SETS_ROOT))
    ap.add_argument("--arms", default="b0,a,b", help="Comma-separated arms: b0,a,b")
    ap.add_argument("--no-guard", action="store_true", help="Disable Decision 1 LeakageGuard on target arms")
    ap.add_argument("--chunked-asr", action="store_true", help="Use FB5 chunked ASR instead of Live WS")
    ap.add_argument("--clips-csv", default=str(REPO_ROOT / "clips.csv"))
    ap.add_argument("--dry-run", action="store_true", help="Run full orchestration with mocked APIs (no cost)")
    args = ap.parse_args()

    sets_root = Path(args.sets_root)
    arms = {a.strip().lower() for a in args.arms.split(",") if a.strip()}
    unknown = arms - {"b0", "a", "b"}
    if unknown:
        raise SystemExit(f"Unknown arms: {sorted(unknown)} (allowed: b0, a, b)")

    clip_dirs: list[Path] = []
    if args.all:
        if sets_root.exists():
            clip_dirs = sorted(p for p in sets_root.iterdir() if p.is_dir() and not p.name.startswith("."))
    elif args.clip:
        clip_dirs = [resolve_clip_dir(args.clip, sets_root)]
    else:
        raise SystemExit("Pass --clip <id_or_dir> or --all")

    if not clip_dirs:
        print(f"No clips found in {sets_root}")
        return

    async def _run_all() -> None:
        for cdir in clip_dirs:
            await evaluate_clip(
                cdir,
                arms=arms,
                use_guard=not args.no_guard,
                use_chunked_asr=args.chunked_asr,
                clips_csv=Path(args.clips_csv),
                dry_run=args.dry_run,
            )

    asyncio.run(_run_all())
    if not args.dry_run and Path(args.clips_csv).resolve() == (REPO_ROOT / "clips.csv").resolve():
        summary = score_all.build_summary(REPO_ROOT)
        (REPO_ROOT / "evals/summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nRefreshed evals/summary.json (Set C n={summary['set_c']['n_total']})")


if __name__ == "__main__":
    main()
