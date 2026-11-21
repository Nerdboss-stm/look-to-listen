"""Look to Listen separation server (Engine B-GPU). Runs on the GPU pod.

ClearVoice AV_MossFormer2_TSE_16K, loaded once. Contract: SPEC.md, "Separation server contract".
Listens on 127.0.0.1 only. The laptop reaches it through an SSH tunnel (pod/tunnel.sh).
Never stores audio: each connection keeps its last 3 s in memory and drops it on disconnect.
Never logs the token, audio, crops or text.

Two hop formats, same behavior:
  Binary (fast path), little-endian:
    hop    = u32 n | n bytes JSON {session_id, seq, target_face_id, reset, pcm_bytes, jpeg_sizes, sent_ms} | int16 PCM | JPEGs
    result = u32 n | n bytes JSON {seq, covers, samples, gpu_ms, queue_ms, sent_ms} | int16 PCM
  JSON text (contracts/hop.schema.json):
    hop    = {session_id, seq, target_face_id, reset, pcm: base64 int16, crops: [base64 JPEG], t_capture}
    result = {seq, pcm: base64 int16, gpu_ms, queue_ms, t_return, covers, samples, t_capture}
Auth: header "Authorization: Bearer <token>", or a first text frame {"token": "..."}. Bad token: close 4401.
If hops pile up, the server separates once and returns all their audio in one result (covers names them).
"""
import asyncio
import base64
import collections
import hmac
import json
import os
import struct
import sys
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

SR = 16000
FPS = 25
SAMPLES_PER_FRAME = SR // FPS      # 640
WIN = 3 * SR                       # 3 s of audio
FRAMES = 3 * FPS                   # 75 face crops
XF = 640                           # 40 ms held back and crossfaded into the next result
MAX_OUT = WIN - XF
MEAN, STD = 0.4161, 0.1688         # ClearVoice's own face normalization
MODEL_NAME = "AV_MossFormer2_TSE_16K"
TOKEN = os.environ.get("SEPARATOR_TOKEN", "").strip()

FADE_IN = (0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, XF))).astype(np.float32)
FADE_OUT = (1.0 - FADE_IN).astype(np.float32)
STATE = {"model": None, "dev": None, "gpu": "", "lock": None, "sessions": 0,
         "gpu_ms": collections.deque(maxlen=20), "started": time.time()}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def token_ok(candidate):
    try:
        return bool(TOKEN) and hmac.compare_digest(str(candidate).encode(), TOKEN.encode())
    except Exception:
        return False


def load_model():
    from clearvoice import ClearVoice
    saved = sys.argv
    sys.argv = sys.argv[:1]  # ClearVoice parses sys.argv
    try:
        cv = ClearVoice(task="target_speaker_extraction", model_names=[MODEL_NAME])
    finally:
        sys.argv = saved
    model = cv.models[0].model
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(dev).eval()
    return model, dev


def infer(audio, faces):
    """audio: (WIN,) float32 in [-1, 1]. faces: (FRAMES, 112, 112) float32, normalized. Returns (WIN,) float32."""
    peak = float(np.max(np.abs(audio)))
    scale = 1.0 / max(peak, 1e-4)  # ClearVoice peak-normalizes its input; the gain is undone below
    with torch.inference_mode():
        a = torch.from_numpy(np.ascontiguousarray(audio * scale, dtype=np.float32)).to(STATE["dev"])[None]
        v = torch.from_numpy(np.ascontiguousarray(faces, dtype=np.float32)).to(STATE["dev"])[None]
        y = STATE["model"](a, v).squeeze().float().cpu().numpy()
    y = np.nan_to_num(y.astype(np.float32)) / scale
    if y.shape[0] < WIN:
        y = np.pad(y, (WIN - y.shape[0], 0))
    return y[-WIN:]


def decode_jpeg(b):
    img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    if img.shape != (112, 112):
        img = cv2.resize(img, (112, 112), interpolation=cv2.INTER_AREA)
    return (img.astype(np.float32) / 255.0 - MEAN) / STD


def parse_binary(data):
    n = struct.unpack_from("<I", data, 0)[0]
    header = json.loads(data[4:4 + n])
    off = 4 + n
    pb = int(header.get("pcm_bytes", 0))
    if pb % 2:
        raise ValueError("pcm_bytes must be even")
    pcm = data[off:off + pb]
    off += pb
    jpegs = []
    for size in header.get("jpeg_sizes", []):
        jpegs.append(data[off:off + int(size)])
        off += int(size)
    if off > len(data):
        raise ValueError("frame is shorter than its header says")
    return header, pcm, jpegs


def parse_json(text):
    header = json.loads(text)
    pcm = base64.b64decode(header.pop("pcm", "") or b"")
    jpegs = [base64.b64decode(c) for c in header.pop("crops", []) or []]
    if len(pcm) % 2:
        raise ValueError("pcm must be whole int16 samples")
    return header, pcm, jpegs


class Session:
    def __init__(self):
        self.audio = np.zeros(WIN, np.float32)
        self.faces = np.zeros((FRAMES, 112, 112), np.float32)  # zeros = neutral gray after normalization
        self.got_face = False
        self.n_samples = 0
        self.n_frames = 0
        self.tail = None
        self.pending = []
        self.pending_samples = 0
        self.last_rx = 0.0
        self.last_header = {}
        self.results = 0
        self.wake = asyncio.Event()

    def add_hop(self, header, pcm, jpegs):
        if header.get("reset"):
            self.faces[:] = 0.0
            self.got_face = False
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        k = len(x)
        if k >= WIN:
            self.audio[:] = x[-WIN:]
        elif k:
            self.audio[:-k] = self.audio[k:]
            self.audio[-k:] = x
        self.n_samples += k
        frames = [f for f in (decode_jpeg(b) for b in jpegs) if f is not None]
        need = self.n_samples // SAMPLES_PER_FRAME - self.n_frames  # keeps video locked to audio at 25 fps
        if need > 0:
            if frames:
                idx = np.minimum((np.arange(need) * len(frames)) // need, len(frames) - 1)
                new = np.stack([frames[i] for i in idx])
                if not self.got_face:
                    self.faces[:] = new[0]
                    self.got_face = True
            elif self.got_face:
                new = np.repeat(self.faces[-1:], need, axis=0)  # face lost for a moment: hold the last crop
            else:
                new = np.zeros((need, 112, 112), np.float32)
            m = min(need, FRAMES)
            self.faces[:FRAMES - m] = self.faces[m:]
            self.faces[FRAMES - m:] = new[-m:]
            self.n_frames += need
        self.pending.append(int(header.get("seq", -1)))
        self.pending_samples += k
        self.last_rx = time.perf_counter()
        self.last_header = header
        self.wake.set()


async def worker(ws, s, binary):
    try:
        await _work(ws, s, binary)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log(f"worker stopped: {type(e).__name__}")


async def _work(ws, s, binary):
    while True:
        await s.wake.wait()
        s.wake.clear()
        if not s.pending or s.pending_samples == 0:
            s.pending, s.pending_samples = [], 0
            continue
        seqs, length = s.pending, s.pending_samples
        s.pending, s.pending_samples = [], 0
        audio, faces, rx, h = s.audio.copy(), s.faces.copy(), s.last_rx, s.last_header
        async with STATE["lock"]:
            t0 = time.perf_counter()
            queue_ms = (t0 - rx) * 1000.0
            y = await asyncio.to_thread(infer, audio, faces)
            gpu_ms = (time.perf_counter() - t0) * 1000.0
        STATE["gpu_ms"].append(round(gpu_ms, 1))
        capped = length > MAX_OUT
        length = min(length, MAX_OUT)
        seg = y[WIN - length - XF:WIN - XF].copy()
        if s.tail is not None and not capped and length >= XF:
            seg[:XF] = s.tail * FADE_OUT + seg[:XF] * FADE_IN
        s.tail = y[WIN - XF:].copy()
        pcm = (np.clip(seg, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        meta = {"seq": seqs[-1], "covers": [seqs[0], seqs[-1]], "samples": int(length),
                "gpu_ms": round(gpu_ms, 1), "queue_ms": round(queue_ms, 1)}
        if binary:
            meta["sent_ms"] = h.get("sent_ms")
            head = json.dumps(meta).encode()
            await ws.send_bytes(struct.pack("<I", len(head)) + head + pcm)
        else:
            meta.update(pcm=base64.b64encode(pcm).decode(), t_capture=h.get("t_capture"),
                        t_return=round(time.time() * 1000))
            await ws.send_text(json.dumps(meta))
        s.results += 1
        if s.results % 120 == 0:
            recent = sorted(STATE["gpu_ms"])
            log(f"session: {s.results} results, gpu p50 {recent[len(recent) // 2]:.0f} ms")


@asynccontextmanager
async def lifespan(app):
    if not TOKEN:
        raise RuntimeError("SEPARATOR_TOKEN is not set. Refusing to start.")
    model, dev = load_model()
    STATE.update(model=model, dev=dev, lock=asyncio.Lock(),
                 gpu=torch.cuda.get_device_name(0) if dev.type == "cuda" else "cpu")
    infer(np.zeros(WIN, np.float32), np.zeros((FRAMES, 112, 112), np.float32))  # warm up
    log(f"ready: {MODEL_NAME} on {STATE['gpu']}")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": STATE["model"] is not None, "model": MODEL_NAME, "gpu": STATE["gpu"],
            "gpu_ms_last20": list(STATE["gpu_ms"]), "sessions": STATE["sessions"],
            "uptime_s": round(time.time() - STATE["started"])}


@app.websocket("/separate")
async def separate(ws: WebSocket):
    await ws.accept()
    auth = ws.headers.get("authorization", "")
    ok = auth.lower().startswith("bearer ") and token_ok(auth[7:].strip())
    if not ok:
        try:
            first = await asyncio.wait_for(ws.receive_text(), timeout=5)
            ok = token_ok(json.loads(first).get("token", ""))
        except Exception:
            ok = False
    if not ok:
        await ws.close(code=4401)
        return
    s = Session()
    task = None
    STATE["sessions"] += 1
    log(f"session open, {STATE['sessions']} active")
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            binary = msg.get("bytes") is not None
            try:
                header, pcm, jpegs = parse_binary(msg["bytes"]) if binary else parse_json(msg.get("text") or "")
            except Exception as e:
                await ws.send_text(json.dumps({"error": f"bad hop: {type(e).__name__}"}))
                continue
            if task is None:
                task = asyncio.create_task(worker(ws, s, binary))
            s.add_hop(header, pcm, jpegs)
            if task.done():
                break
    except WebSocketDisconnect:
        pass
    finally:
        if task is not None:
            task.cancel()
        STATE["sessions"] -= 1
        log(f"session closed after {s.results} results, {STATE['sessions']} active")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SEPARATOR_PORT", "8000")),
                access_log=False, log_level="warning")
