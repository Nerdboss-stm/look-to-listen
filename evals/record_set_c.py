"""Fast E16 Set C clip recorder & truth intake (< 2 min per consenting pair).

Privacy & integrity rules (AGENTS.md / SPEC.md):
  - All audio, hops, real names, and truth transcripts stay in clips/set_c/ (gitignored).
  - Tracked clips.csv receives ONLY anonymous IDs (P01, P02, ...) and numeric scores —
    never real names, never truth text, never audio.
  - Consent prompt states verbatim:
    "Audio stays on this laptop and is deleted after the event, and only the numbers are shown."
  - An ASR draft is ONLY a draft: it is shown to a human who must explicitly confirm or
    correct it (truth_verified=True) before the clip can count in clips.csv.

Workflow (< 2 minutes per pair):
  1) Record 15 s consented clip:
     /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/record_set_c.py \\
       --p1 "Alice" --p2 "Bob" --target center --distance 1 --angle front --noise 65 --network wifi
  2) Attach close-talk phone recordings, review/correct draft ASR, and confirm:
     /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/record_set_c.py \\
       --fill-truth c01 --close-talk-target ~/Downloads/p1.m4a --close-talk-other ~/Downloads/p2.m4a --draft-asr
  3) Run all 3 arms (B0, Engine A, Engine B-GPU) on the verified clip:
     /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --clip c01
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "evals") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "evals"))

import clip_io

# Stored under gitignored clips/ so names, truth text, and audio never enter tracked files.
SETS_C_ROOT = REPO_ROOT / "clips" / "set_c"

CONSENT_DISCLOSURE = (
    "Audio stays on this laptop and is deleted after the event, and only the numbers are shown."
)

_ANON_ID_RE = re.compile(r"^P\d{2,}$")


def next_clip_id(sets_root: Path = SETS_C_ROOT) -> str:
    """Return next sequential clip id (c01, c02, ...)."""
    sets_root.mkdir(parents=True, exist_ok=True)
    nums: list[int] = []
    for p in sets_root.iterdir():
        if p.is_dir() and p.name.startswith("c") and p.name[1:].isdigit():
            nums.append(int(p.name[1:]))
    nxt = (max(nums) + 1) if nums else 1
    return f"c{nxt:02d}"


def assign_anonymous_ids(
    names: list[str],
    *,
    registry_path: Path | None = None,
) -> list[tuple[str, str]]:
    """Map participant names to anonymous IDs (P01, P02, ...) stored ONLY in gitignored clips/.

    Returns list of (anon_id, real_name). Reuses existing ID if the same name already registered.
    If caller already passes 'P01', keeps it as-is.
    """
    reg_path = registry_path or (SETS_C_ROOT / "participants.json")
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    if reg_path.exists():
        reg: dict[str, str] = json.loads(reg_path.read_text(encoding="utf-8"))
    else:
        reg = {}

    # Reverse lookup by normalized name -> Pxx
    by_name = {v.strip().lower(): k for k, v in reg.items() if v.strip()}
    existing_nums = [int(k[1:]) for k in reg if _ANON_ID_RE.match(k)]
    next_num = (max(existing_nums) + 1) if existing_nums else 1

    assigned: list[tuple[str, str]] = []
    for raw in names:
        clean = raw.strip()
        if not clean:
            continue
        if _ANON_ID_RE.match(clean):
            pid = clean
            reg.setdefault(pid, pid)
        elif clean.lower() in by_name:
            pid = by_name[clean.lower()]
        else:
            pid = f"P{next_num:02d}"
            next_num += 1
            reg[pid] = clean
            by_name[clean.lower()] = pid
        assigned.append((pid, clean))

    reg_path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    return assigned


def write_consent_record(
    clip_dir: Path,
    *,
    participants: list[str],
    confirmed_yes: bool,
    recorded_by: str = "Saran",
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Enforce verbal consent with required disclosure before recording; write gitignored consent.json."""
    clean_names = [p.strip() for p in participants if p and p.strip()]
    if not clean_names:
        raise ValueError("At least one participant name/ID is required for consent.")
    if not confirmed_yes:
        raise PermissionError(
            "Consent NOT confirmed. Refusing to record or save any audio/video (SPEC Privacy Rule)."
        )

    assigned = assign_anonymous_ids(clean_names, registry_path=registry_path or (clip_dir.parent / "participants.json"))
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "clip_id": clip_dir.name,
        "all_consented": True,
        "disclosure": CONSENT_DISCLOSURE,
        "recorded_by": recorded_by,
        "recorded_at": now,
        "participants": [
            {
                "face_id": f"face_{idx}",
                "participant_id": pid,
                "name": name,
                "given": True,
                "by": name,
                "time": now,
            }
            for idx, (pid, name) in enumerate(assigned)
        ],
    }
    clip_dir.mkdir(parents=True, exist_ok=True)
    (clip_dir / "consent.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def capture_live_clip(
    clip_dir: Path,
    *,
    clip_id: str,
    duration_s: float = 15.0,
    target_hint: str = "center",
    camera_index: int = 0,
    preview: bool = True,
) -> tuple[list[clip_io.ClipHop], bytes]:
    """Simultaneously capture 16 kHz mono mic + 25 fps webcam -> exact 0.5 s hops & raw.wav in clips/."""
    import sounddevice as sd

    audio_q: queue.Queue[bytes] = queue.Queue()
    stop_evt = threading.Event()

    def audio_cb(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if not stop_evt.is_set():
            audio_q.put(indata.copy().tobytes())

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam index {camera_index}")

    for _ in range(8):
        cap.read()
        time.sleep(0.04)

    print(f"\n[E16] Recording {clip_id} for {duration_s:.0f} s — BOTH talkers start talking now (with close-talk phones)!")
    if preview:
        print("      Green box = target face. Press 'q' in preview window to stop early.")

    pcm_chunks: list[bytes] = []
    frames: list[tuple[float, np.ndarray]] = []
    t0 = time.perf_counter()

    with sd.InputStream(
        samplerate=clip_io.SR,
        channels=1,
        dtype="int16",
        blocksize=1600,
        callback=audio_cb,
    ):
        last_box: dict[str, float] | None = None
        frame_idx = 0
        while True:
            elapsed = time.perf_counter() - t0
            if elapsed >= duration_s:
                break
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            frames.append((elapsed, frame))
            if preview:
                disp = frame.copy()
                if frame_idx % 5 == 0:
                    faces = clip_io.detect_faces_bgr(frame)
                    _, last_box = clip_io.select_target_face(
                        faces, target_hint=target_hint, fallback_box=last_box
                    )
                if last_box:
                    fh, fw = disp.shape[:2]
                    x0 = int(last_box["x"] * fw)
                    y0 = int(last_box["y"] * fh)
                    x1 = int((last_box["x"] + last_box["w"]) * fw)
                    y1 = int((last_box["y"] + last_box["h"]) * fh)
                    cv2.rectangle(disp, (x0, y0), (x1, y1), (0, 255, 0), 3)
                rem = max(0.0, duration_s - elapsed)
                cv2.putText(
                    disp,
                    f"REC {clip_id}  {rem:4.1f}s left  target={target_hint}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("E16 Set C Recorder", disp)
                if (cv2.waitKey(1) & 0xFF) == ord("q"):
                    break
            else:
                time.sleep(0.025)
            frame_idx += 1

        stop_evt.set()
        while not audio_q.empty():
            pcm_chunks.append(audio_q.get_nowait())

    cap.release()
    if preview:
        cv2.destroyAllWindows()

    pcm_all = b"".join(pcm_chunks)
    if len(pcm_all) < clip_io.HOP_BYTES:
        raise RuntimeError(f"Captured less than 0.5 s of audio ({len(pcm_all)} bytes)")
    if not frames:
        raise RuntimeError("Captured 0 video frames")

    clip_io.write_wav16(clip_dir / "raw.wav", pcm_all)

    n_hops = len(pcm_all) // clip_io.HOP_BYTES
    hops: list[clip_io.ClipHop] = []
    last_box = None
    frames_done = 0
    frame_times = np.array([t for t, _ in frames], dtype=np.float64)

    for seq in range(n_hops):
        pcm_hop = pcm_all[seq * clip_io.HOP_BYTES : (seq + 1) * clip_io.HOP_BYTES]
        need = (seq + 1) * 8000 // 640 - frames_done
        crops: list[bytes] = []
        mid_frame: np.ndarray | None = None
        mid_faces: list[dict[str, Any]] = []
        target_fid = "face_0"

        for i in range(need):
            t_sec = (frames_done + i) / 25.0
            nearest = int(np.argmin(np.abs(frame_times - t_sec)))
            fr = frames[nearest][1]
            if i % 3 == 0 or last_box is None:
                faces = clip_io.detect_faces_bgr(fr)
                target_fid, det_box = clip_io.select_target_face(
                    faces, target_hint=target_hint, fallback_box=last_box
                )
                if last_box is not None:
                    box = {
                        k: round(0.7 * float(last_box[k]) + 0.3 * float(det_box[k]), 4)
                        for k in ("x", "y", "w", "h")
                    }
                else:
                    box = det_box
                last_box = box
            else:
                box = last_box
                faces = [{"id": target_fid, "box": box, "mouth_open": 0.15}]
            crops.append(clip_io.extract_clearvoice_crop_jpeg(fr, box))
            if i == need // 2:
                mid_frame = fr
                mid_faces = faces if faces else [{"id": target_fid, "box": box, "mouth_open": 0.15}]

        frames_done += need
        hops.append(
            clip_io.ClipHop(
                seq=seq,
                session_id=f"eval-{clip_id}",
                target_face_id=target_fid,
                reset=(seq == 0),
                pcm_bytes=pcm_hop,
                crops_jpegs=crops,
                frame_jpeg=clip_io.encode_frame_jpeg(mid_frame) if mid_frame is not None else None,
                faces=mid_faces,
                t_capture=seq * 500.0,
            )
        )

    clip_io.save_hops_jsonl(clip_dir / "hops.jsonl", hops)
    print(f"[E16] Saved {len(hops)} hops ({len(hops)*0.5:.1f} s) + raw.wav -> {clip_dir} (gitignored)")
    return hops, pcm_all


def draft_close_talk_transcript(media_path: Path) -> str:
    """Convert a close-talk phone recording via ffmpeg and generate an UNVERIFIED ASR draft."""
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    from backend.gemini.live_captioner import transcribe_chunk_sync

    pcm = clip_io.convert_audio_to_pcm16(media_path)
    text, ms = transcribe_chunk_sync(pcm, purpose="set_c_close_talk_draft")
    print(f"  [ASR DRAFT ONLY — {ms:.0f} ms] {media_path.name}: {text!r}")
    return text


def fill_truth_flow(
    clip_dir: Path,
    *,
    truth_target: str = "",
    truth_others: str = "",
    close_talk_target: str = "",
    close_talk_other: str = "",
    draft_asr: bool = False,
    human_confirmed: bool = False,
    interactive: bool = True,
    clips_csv_path: Path | None = None,
) -> dict[str, Any]:
    """Attach close-talk truth inside gitignored clips/set_c/<clip_id>/meta.json.

    An ASR draft is NEVER treated as final truth: a human must explicitly review,
    correct/confirm it so truth_verified=True before the clip counts in clips.csv.
    Tracked clips.csv receives ONLY anonymous IDs (P01;P02) and metadata — NEVER truth text.
    """
    meta_path = clip_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No meta.json found in {clip_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    draft_t = ""
    draft_o = ""
    used_draft = False

    if close_talk_target:
        src = Path(close_talk_target).expanduser()
        pcm = clip_io.convert_audio_to_pcm16(src)
        clip_io.write_wav16(clip_dir / "close_talk_target.wav", pcm)
        if draft_asr:
            draft_t = draft_close_talk_transcript(src)
            used_draft = True

    if close_talk_other:
        src = Path(close_talk_other).expanduser()
        pcm = clip_io.convert_audio_to_pcm16(src)
        clip_io.write_wav16(clip_dir / "close_talk_other.wav", pcm)
        if draft_asr:
            draft_o = draft_close_talk_transcript(src)
            used_draft = True

    if draft_t:
        meta["draft_truth_target"] = draft_t
    if draft_o:
        meta["draft_truth_others"] = draft_o

    verified = False
    final_t = truth_target or ""
    final_o = truth_others or ""

    if interactive:
        shown_t = final_t or draft_t or meta.get("truth_target", "") or meta.get("draft_truth_target", "")
        shown_o = final_o or draft_o or meta.get("truth_others", "") or meta.get("draft_truth_others", "")
        print(f"\n--- Human Truth Verification for {meta['clip_id']} ---")
        if used_draft or (meta.get("draft_truth_target") and not meta.get("truth_verified")):
            print("  NOTE: The ASR output below is ONLY A DRAFT. You must verify or correct it before this clip counts.")
        print(f"  Current/Draft truth_target: {shown_t!r}")
        inp_t = input("  Enter corrected truth_target (or press Enter to accept draft): ").strip()
        final_t = inp_t or shown_t

        print(f"  Current/Draft truth_others: {shown_o!r}")
        inp_o = input("  Enter corrected truth_others (or press Enter to accept draft): ").strip()
        final_o = inp_o or shown_o

        if final_t.strip():
            ans = input(
                "  Confirm a human has checked & verified these transcripts against the close-talk audio? [y/N]: "
            ).strip().lower()
            verified = ans in ("y", "yes")
        else:
            verified = False
    else:
        # Non-interactive mode: an ASR draft is NEVER auto-verified.
        if used_draft:
            verified = False
        elif human_confirmed and final_t.strip():
            verified = True

    meta["truth_target"] = final_t if verified else meta.get("truth_target", "")
    meta["truth_others"] = final_o if verified else meta.get("truth_others", "")
    meta["truth_verified"] = bool(verified)
    if verified:
        meta["truth_verified_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    if not verified:
        print(
            f"[E16] Saved draft/meta in {meta_path} (truth_verified=False). "
            f"Clip {meta['clip_id']} does NOT count yet. Re-run interactively with --fill-truth {meta['clip_id']} to confirm."
        )
        return meta

    # Write ONLY anonymous participant IDs (P01;P02) and metadata to tracked clips.csv.
    # Truth text & real names stay strictly inside gitignored clips/set_c/<clip_id>/.
    target_csv = clips_csv_path or (REPO_ROOT / "clips.csv")
    clip_io.upsert_clips_csv(
        target_csv,
        {
            "clip_id": meta["clip_id"],
            "time_et": meta.get("time_et", ""),
            "talkers": meta.get("talkers", 2),
            "target_face": meta.get("target_face", "center"),
            "distance_m": meta.get("distance_m", ""),
            "angle": meta.get("angle", ""),
            "noise_db": meta.get("noise_db", ""),
            "occlusion": meta.get("occlusion", "none"),
            "consent_ids": meta.get("consent_ids", ""),
            "truth_target": "",
            "truth_others": "",
            "notes": meta.get("notes", ""),
        },
    )
    print(
        f"[E16] Human-verified truth saved in gitignored {meta_path}; "
        f"registered anonymous row ({meta.get('consent_ids')}) in {target_csv}."
    )
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="E16 fast Set C consented clip recorder (< 2 min/pair).")
    ap.add_argument("--clip-id", default="", help="Clip ID (default: auto next c01, c02, ...)")
    ap.add_argument("--p1", default="", help="Participant 1 name/initials (stored ONLY in gitignored clips/)")
    ap.add_argument("--p2", default="", help="Participant 2 name/initials (stored ONLY in gitignored clips/)")
    ap.add_argument("--p3", default="", help="Optional Participant 3 (3-talker clip)")
    ap.add_argument("--target", default="center", help="Target face hint: center, left, right, or face_N")
    ap.add_argument("--duration", type=float, default=15.0, help="Recording length in seconds (10-20 s)")
    ap.add_argument("--distance", default="1", help="Distance in meters (1, 2, 3)")
    ap.add_argument("--angle", default="front", help="Angle: front, 45deg, profile")
    ap.add_argument("--noise", default="65", help="Measured ambient noise dB")
    ap.add_argument("--occlusion", default="none", help="Occlusion: none, hand, cup")
    ap.add_argument("--network", default="wifi", help="Network tag: wifi or hotspot")
    ap.add_argument("--notes", default="", help="Extra notes (do NOT put real names here)")
    ap.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    ap.add_argument("--no-preview", action="store_true", help="Disable OpenCV preview window")
    ap.add_argument("--yes-consented", action="store_true", help="Assert verbal consent + disclosure already given")
    ap.add_argument("--fill-truth", default="", help="Skip recording; verify/attach close-talk truth for existing clip_id")
    ap.add_argument("--close-talk-target", default="", help="Path to target close-talk phone audio")
    ap.add_argument("--close-talk-other", default="", help="Path to other talker close-talk phone audio")
    ap.add_argument("--truth-target", default="", help="Human-typed ground truth target text")
    ap.add_argument("--truth-others", default="", help="Human-typed ground truth other talker(s) text")
    ap.add_argument("--truth-verified", action="store_true", help="Assert human verified typed truth (ignored if --draft-asr)")
    ap.add_argument("--draft-asr", action="store_true", help="Generate ASR draft from close-talk audio (requires human confirm)")
    ap.add_argument("--non-interactive", action="store_true", help="Skip interactive prompts")
    ap.add_argument("--run-arms", action="store_true", help="Run evals/run_arms.py after human truth verification")
    args = ap.parse_args()

    if args.fill_truth:
        clip_dir = SETS_C_ROOT / args.fill_truth
        meta = fill_truth_flow(
            clip_dir,
            truth_target=args.truth_target,
            truth_others=args.truth_others,
            close_talk_target=args.close_talk_target,
            close_talk_other=args.close_talk_other,
            draft_asr=args.draft_asr,
            human_confirmed=args.truth_verified,
            interactive=not args.non_interactive,
        )
        if args.run_arms and meta.get("truth_verified"):
            import asyncio
            import run_arms

            asyncio.run(run_arms.evaluate_clip(clip_dir, arms={"b0", "a", "b"}))
        return

    clip_id = args.clip_id or next_clip_id()
    clip_dir = SETS_C_ROOT / clip_id
    participants = [p for p in (args.p1, args.p2, args.p3) if p.strip()]
    if not participants and not args.non_interactive:
        p1 = input("Participant 1 name/initials (kept only in gitignored clips/): ").strip()
        p2 = input("Participant 2 name/initials (kept only in gitignored clips/): ").strip()
        p3 = input("Participant 3 (blank for 2-talker): ").strip()
        participants = [p for p in (p1, p2, p3) if p]

    confirmed = args.yes_consented
    if not confirmed:
        if args.non_interactive:
            raise PermissionError("Refusing to record without --yes-consented in non-interactive mode.")
        print("\n=== CONSENT DISCLOSURE (read aloud to participants) ===")
        print(f'  "{CONSENT_DISCLOSURE}"')
        ans = input(
            f"Did ALL participants ({', '.join(participants)}) hear this disclosure and verbally say YES? [y/N]: "
        ).strip().lower()
        confirmed = ans in ("y", "yes")

    consent_rec = write_consent_record(clip_dir, participants=participants, confirmed_yes=confirmed)
    anon_ids = ";".join(p["participant_id"] for p in consent_rec["participants"])
    print(f"[E16] Assigned anonymous IDs for clips.csv: {anon_ids}")

    capture_live_clip(
        clip_dir,
        clip_id=clip_id,
        duration_s=args.duration,
        target_hint=args.target,
        camera_index=args.camera,
        preview=not args.no_preview,
    )

    notes_combined = "; ".join(x for x in (args.network, args.notes) if x.strip())
    meta = {
        "clip_id": clip_id,
        "time_et": datetime.now().strftime("%H:%M"),
        "talkers": len(participants),
        "target_face": args.target,
        "distance_m": args.distance,
        "angle": args.angle,
        "noise_db": args.noise,
        "occlusion": args.occlusion,
        "consent_ids": anon_ids,
        "network": args.network,
        "truth_target": "",
        "truth_others": "",
        "truth_verified": False,
        "notes": notes_combined,
    }
    (clip_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    meta = fill_truth_flow(
        clip_dir,
        truth_target=args.truth_target,
        truth_others=args.truth_others,
        close_talk_target=args.close_talk_target,
        close_talk_other=args.close_talk_other,
        draft_asr=args.draft_asr,
        human_confirmed=args.truth_verified,
        interactive=not args.non_interactive,
    )

    if meta.get("truth_verified"):
        print(f"\n[E16] Verified & ready! Run all 3 arms next:")
        print(f"  /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --clip {clip_id}")
        if args.run_arms:
            import asyncio
            import run_arms

            asyncio.run(run_arms.evaluate_clip(clip_dir, arms={"b0", "a", "b"}))
    else:
        print(f"\n[E16] Next step: attach close-talk audio and human-verify truth:")
        print(
            f"  /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/record_set_c.py "
            f"--fill-truth {clip_id} --close-talk-target <p1.m4a> --close-talk-other <p2.m4a> --draft-asr"
        )


if __name__ == "__main__":
    main()
