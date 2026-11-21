"""Shared Set C clip I/O, ClearVoice cropper, video-to-hops converter, and CSV upsert.

Matches SPEC.md face crop recipe and contracts/hop.schema.json.
"""
from __future__ import annotations

import base64
import csv
import json
import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SR = 16000
HOP_SAMPLES = 8000  # 0.5 s @ 16 kHz
HOP_BYTES = HOP_SAMPLES * 2  # int16 mono
CLIPS_CSV_COLUMNS = [
    "clip_id",
    "time_et",
    "talkers",
    "target_face",
    "distance_m",
    "angle",
    "noise_db",
    "occlusion",
    "consent_ids",
    "truth_target",
    "truth_others",
    "b0_text",
    "b0_wer",
    "b0_leak",
    "a_text",
    "a_wer",
    "a_leak",
    "a_time_s",
    "b_text",
    "b_wer",
    "b_leak",
    "b_time_s",
    "notes",
]

_FACE_CASCADE: cv2.CascadeClassifier | None = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        xml_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        _FACE_CASCADE = cv2.CascadeClassifier(xml_path)
    return _FACE_CASCADE


def detect_faces_bgr(frame_bgr: np.ndarray) -> list[dict[str, Any]]:
    """Detect faces in a BGR frame and return normalized [0,1] boxes sorted left-to-right."""
    h, w = frame_bgr.shape[:2]
    if h == 0 or w == 0:
        return []
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    cascade = _get_face_cascade()
    rects = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(40, 40))
    boxes: list[tuple[float, float, float, float]] = []
    for x, y, bw, bh in rects:
        boxes.append((x / w, y / h, bw / w, bh / h))
    boxes.sort(key=lambda b: b[0] + b[2] / 2.0)
    return [
        {
            "id": f"face_{idx}",
            "box": {"x": round(b[0], 4), "y": round(b[1], 4), "w": round(b[2], 4), "h": round(b[3], 4)},
            "mouth_open": 0.15,
        }
        for idx, b in enumerate(boxes)
    ]


def select_target_face(
    faces: list[dict[str, Any]],
    *,
    target_hint: str = "center",
    fallback_box: dict[str, float] | None = None,
) -> tuple[str, dict[str, float]]:
    """Select target face by hint ('center', 'left', 'right', or explicit 'face_N')."""
    if not faces:
        box = fallback_box or {"x": 0.35, "y": 0.2, "w": 0.3, "h": 0.45}
        return "face_0", box

    hint = (target_hint or "center").strip().lower()
    for f in faces:
        if str(f.get("id", "")).lower() == hint:
            return str(f["id"]), f["box"]

    def cx(f: dict[str, Any]) -> float:
        b = f["box"]
        return float(b["x"]) + float(b["w"]) * 0.5

    if hint == "left":
        chosen = min(faces, key=cx)
    elif hint == "right":
        chosen = max(faces, key=cx)
    else:
        chosen = min(faces, key=lambda f: abs(cx(f) - 0.5))
    return str(chosen["id"]), chosen["box"]


def extract_clearvoice_crop_jpeg(
    frame_bgr: np.ndarray,
    norm_box: dict[str, float],
    *,
    c: float = 0.4,
    jpeg_quality: int = 85,
) -> bytes:
    """Exact SPEC.md ClearVoice face crop recipe:
    smoothed face box -> half-size s -> pad frame -> crop y-s..y+s(1+2c), x-s(1+c)..x+s(1+c)
    -> resize 224x224 -> grayscale -> center crop 112x112 -> JPEG.
    """
    h, w = frame_bgr.shape[:2]
    bx = float(norm_box.get("x", 0.35)) * w
    by = float(norm_box.get("y", 0.20)) * h
    bw = max(8.0, float(norm_box.get("w", 0.30)) * w)
    bh = max(8.0, float(norm_box.get("h", 0.45)) * h)

    cx = bx + bw * 0.5
    cy = by + bh * 0.5
    s = max(bw, bh) * 0.5

    pad = int(math.ceil(s * (1.0 + 2.0 * c))) + 4
    padded = cv2.copyMakeBorder(frame_bgr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0))

    cx_p = cx + pad
    cy_p = cy + pad
    y0 = max(0, int(round(cy_p - s)))
    y1 = min(padded.shape[0], int(round(cy_p + s * (1.0 + 2.0 * c))))
    x0 = max(0, int(round(cx_p - s * (1.0 + c))))
    x1 = min(padded.shape[1], int(round(cx_p + s * (1.0 + c))))

    crop = padded[y0:y1, x0:x1]
    if crop.size == 0:
        crop = frame_bgr
    resized = cv2.resize(crop, (224, 224), interpolation=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    center = gray[56:168, 56:168]  # 112x112
    ok, enc = cv2.imencode(".jpg", center, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError("Failed to JPEG-encode ClearVoice 112x112 crop")
    return enc.tobytes()


def encode_frame_jpeg(frame_bgr: np.ndarray, *, max_width: int = 640, quality: int = 75) -> bytes:
    h, w = frame_bgr.shape[:2]
    if w > max_width:
        scale = max_width / float(w)
        frame_bgr = cv2.resize(frame_bgr, (max_width, max(2, int(round(h * scale)))))
    ok, enc = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("Failed to JPEG-encode full frame")
    return enc.tobytes()


def write_wav16(path: Path, pcm_bytes: bytes, sample_rate: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def read_wav16(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() == 1 and wf.getsampwidth() == 2 and wf.getframerate() == SR:
            return wf.readframes(wf.getnframes())
    return convert_audio_to_pcm16(path)


def convert_audio_to_pcm16(media_path: Path) -> bytes:
    """Use ffmpeg to decode any audio/video file to 16 kHz mono int16 PCM bytes."""
    with tempfile.TemporaryDirectory() as td:
        out_wav = Path(td) / "out.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(media_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SR),
                "-c:a",
                "pcm_s16le",
                str(out_wav),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with wave.open(str(out_wav), "rb") as wf:
            return wf.readframes(wf.getnframes())


@dataclass
class ClipHop:
    seq: int
    session_id: str
    target_face_id: str
    reset: bool
    pcm_bytes: bytes
    crops_jpegs: list[bytes]
    frame_jpeg: bytes | None
    faces: list[dict[str, Any]]
    t_capture: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "seq": self.seq,
            "target_face_id": self.target_face_id,
            "reset": self.reset,
            "pcm": base64.b64encode(self.pcm_bytes).decode("ascii"),
            "crops": [base64.b64encode(c).decode("ascii") for c in self.crops_jpegs],
            "frame_jpeg": base64.b64encode(self.frame_jpeg).decode("ascii") if self.frame_jpeg else None,
            "faces": self.faces,
            "t_capture": round(self.t_capture, 1),
        }

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> "ClipHop":
        frame_b64 = d.get("frame_jpeg")
        return cls(
            seq=int(d.get("seq", 0)),
            session_id=str(d.get("session_id", "eval-clip")),
            target_face_id=str(d.get("target_face_id") or "face_0"),
            reset=bool(d.get("reset", False)),
            pcm_bytes=base64.b64decode(d["pcm"]),
            crops_jpegs=[base64.b64decode(c) for c in (d.get("crops") or [])],
            frame_jpeg=base64.b64decode(frame_b64) if frame_b64 else None,
            faces=list(d.get("faces") or []),
            t_capture=float(d.get("t_capture", int(d.get("seq", 0)) * 500.0)),
        )


def save_hops_jsonl(path: Path, hops: list[ClipHop]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for h in hops:
            f.write(json.dumps(h.to_json_dict(), separators=(",", ":")) + "\n")


def load_hops_jsonl(path: Path) -> list[ClipHop]:
    hops: list[ClipHop] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s:
            continue
        hops.append(ClipHop.from_json_dict(json.loads(s)))
    return hops


def build_hops_from_video(
    video_path: Path,
    *,
    clip_id: str,
    target_hint: str = "center",
    explicit_box: dict[str, float] | None = None,
) -> list[ClipHop]:
    """Decode a recorded video file into exact 0.5 s hops (16 kHz PCM + 25 fps ClearVoice crops)."""
    pcm_all = convert_audio_to_pcm16(video_path)
    n_hops = len(pcm_all) // HOP_BYTES
    if n_hops == 0:
        raise ValueError(f"Video {video_path} has less than 0.5 s of audio")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    raw_frames: list[np.ndarray] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        raw_frames.append(frame)
    cap.release()
    if not raw_frames:
        raise RuntimeError(f"No video frames decoded from {video_path}")

    hops: list[ClipHop] = []
    last_box: dict[str, float] | None = explicit_box
    frames_done = 0

    for seq in range(n_hops):
        pcm_hop = pcm_all[seq * HOP_BYTES : (seq + 1) * HOP_BYTES]
        # Exact ClearVoice 25 fps frame cadence (12 or 13 crops per 0.5 s hop)
        need = (seq + 1) * 8000 // 640 - frames_done
        crops: list[bytes] = []
        mid_frame: np.ndarray | None = None
        mid_faces: list[dict[str, Any]] = []
        target_fid = "face_0"

        for i in range(need):
            t_sec = (frames_done + i) / 25.0
            src_idx = min(len(raw_frames) - 1, max(0, int(round(t_sec * src_fps))))
            fr = raw_frames[src_idx]
            if explicit_box is not None:
                box = explicit_box
                faces = [{"id": "face_0", "box": box, "mouth_open": 0.15}]
                target_fid = "face_0"
            else:
                # Detect on every 3rd crop for speed, smoothing box across frames
                if i % 3 == 0 or last_box is None:
                    faces = detect_faces_bgr(fr)
                    target_fid, detected_box = select_target_face(
                        faces, target_hint=target_hint, fallback_box=last_box
                    )
                    if last_box is not None:
                        box = {
                            k: round(0.7 * float(last_box[k]) + 0.3 * float(detected_box[k]), 4)
                            for k in ("x", "y", "w", "h")
                        }
                    else:
                        box = detected_box
                    last_box = box
                else:
                    box = last_box
                    faces = [{"id": target_fid, "box": box, "mouth_open": 0.15}]
            crops.append(extract_clearvoice_crop_jpeg(fr, box))
            if i == need // 2:
                mid_frame = fr
                mid_faces = faces if faces else [{"id": target_fid, "box": box, "mouth_open": 0.15}]

        frames_done += need
        frame_jpg = encode_frame_jpeg(mid_frame) if mid_frame is not None else None
        hops.append(
            ClipHop(
                seq=seq,
                session_id=f"eval-{clip_id}",
                target_face_id=target_fid,
                reset=(seq == 0),
                pcm_bytes=pcm_hop,
                crops_jpegs=crops,
                frame_jpeg=frame_jpg,
                faces=mid_faces,
                t_capture=seq * 500.0,
            )
        )
    return hops


def upsert_clips_csv(csv_path: Path, row_update: dict[str, Any]) -> None:
    """Insert or update a row in clips.csv by clip_id without dropping existing data."""
    clip_id = str(row_update.get("clip_id") or "").strip()
    if not clip_id:
        raise ValueError("row_update must include non-empty clip_id")

    rows: list[dict[str, str]] = []
    fieldnames = list(CLIPS_CSV_COLUMNS)
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
            rows = list(reader)

    updated = False
    for row in rows:
        if (row.get("clip_id") or "").strip() == clip_id:
            for k, v in row_update.items():
                if k in fieldnames and v is not None:
                    row[k] = str(v)
            updated = True
            break

    if not updated:
        new_row = {k: "" for k in fieldnames}
        for k, v in row_update.items():
            if k in fieldnames and v is not None:
                new_row[k] = str(v)
        rows.append(new_row)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(csv_path)
