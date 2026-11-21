"""Look to Listen FastAPI backend (S1).

Owns:
- .env loading (never logs secrets)
- Browser WebSocket (/ws/live) matching frontend/src/types/contracts.ts
- GPU separation client (backend/separation/client.py) with stale-hop drop & failover
- Continuous live speaker/headphone playback (backend/playback/player.py)
- Hop delay logging (logs/hops.jsonl) and live DELAY meter / END CARD endpoints
- Consent records & consent-enforced clip store (backend/store/)
- Router & live-hook mount point for S3 (backend/gemini/routes.py)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=False)

from backend.playback.player import LiveAudioPlayer  # noqa: E402
from backend.separation.client import SeparationClient, SeparationResult  # noqa: E402
from backend.separation.hop_logger import HopLogger  # noqa: E402
from backend.separation.replay import ReplayRingBuffer  # noqa: E402
from backend.store.clips import ClipStore, ConsentDeniedError  # noqa: E402
from backend.store.consent import ConsentStore  # noqa: E402
from backend.store.end_card import build_end_card_data, read_live_leakage_from_csv  # noqa: E402

AGENT_LOG_PATH = REPO_ROOT / "logs" / "agent.jsonl"

RawHopHook = Callable[[dict[str, Any], bytes], Awaitable[None]]
CleanAudioHook = Callable[[SeparationResult], Awaitable[None]]
EngineChangeHook = Callable[[str, str], Awaitable[None]]
WsActionHook = Callable[[dict[str, Any], WebSocket], Awaitable[None]]


class LiveRuntime:
    """Shared live runtime connecting S1's separation/playback/store with S2 UI and S3 Gemini."""

    def __init__(self) -> None:
        self.hop_logger = HopLogger()
        self.player = LiveAudioPlayer()
        self.consent = ConsentStore()
        self.clips = ClipStore(self.consent)
        self.replay_buf = ReplayRingBuffer(max_hops=20)
        self.separator = SeparationClient(
            hop_logger=self.hop_logger,
            on_result=self._on_separation_result,
            on_engine_change=self._on_engine_change,
            playback_buf_ms_provider=self.player.effective_playback_buf_ms,
        )

        self.clients: set[WebSocket] = set()
        self.target_face_id: str | None = None
        self.target_mode: str = "auto"
        self.latest_faces: list[dict[str, Any]] = []
        self.latest_frame_jpeg: str | None = None
        self.caption_delay_ms: float | None = None
        self._mark_next_discontinuous = False
        self._last_result_seq: int | None = None
        self._agent_tail_task: asyncio.Task[Any] | None = None

        # Extension hooks for S3 (backend/gemini/)
        self.on_raw_hop_hooks: list[RawHopHook] = []
        self.on_clean_audio_hooks: list[CleanAudioHook] = []
        self.on_engine_change_hooks: list[EngineChangeHook] = []
        self.on_ws_action_hooks: dict[str, WsActionHook] = {}

    async def start(self) -> None:
        self.player.start()
        await self.separator.start()
        self._agent_tail_task = asyncio.create_task(self._tail_agent_log(), name="agent-log-tail")

    async def stop(self) -> None:
        if self._agent_tail_task is not None:
            self._agent_tail_task.cancel()
            try:
                await self._agent_tail_task
            except asyncio.CancelledError:
                pass
            self._agent_tail_task = None
        await self.separator.stop()
        self.player.stop()
        self.replay_buf.clear()

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.clients:
            return
        text = json.dumps(message, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def build_live_metrics(self) -> dict[str, Any]:
        snap = self.hop_logger.snapshot()
        raw_leak, target_leak, clips_count = read_live_leakage_from_csv()
        return {
            "engine": self.separator.active_engine,
            "engine_reason": self.separator.engine_reason,
            "voice_delay_ms": snap["voice_delay_p50_ms"] or snap["last_voice_delay_ms"],
            "caption_delay_ms": self.caption_delay_ms,
            "gpu_ms": snap["last_gpu_ms"],
            "rtt_ms": snap["last_rtt_ms"],
            "raw_leakage_pct": raw_leak,
            "target_leakage_pct": target_leak,
            "leakage_source": "csv" if clips_count > 0 else "live",
            "clips_count": clips_count,
            "hop_ms": self.separator.hop_ms,
        }

    async def _on_engine_change(self, engine: str, reason: str) -> None:
        await self.broadcast(
            {
                "type": "engine_status",
                "engine": engine,
                "reason": reason,
                "hop_ms": self.separator.hop_ms,
            }
        )
        await self.broadcast({"type": "metrics", "payload": self.build_live_metrics()})
        for hook in list(self.on_engine_change_hooks):
            asyncio.create_task(self._safe_call(hook, engine, reason))

    async def _on_separation_result(self, result: SeparationResult) -> None:
        discontinuous = self._mark_next_discontinuous
        if (
            self._last_result_seq is not None
            and result.covers
            and result.covers[0] > self._last_result_seq + 1
        ):
            discontinuous = True
        self._mark_next_discontinuous = False
        self._last_result_seq = result.seq

        # 1. Forward clean PCM immediately to browser VoicePlayer (/ws/live)
        #    Chrome's AEC only cancels audio played by Chrome itself.
        await self.broadcast({"type": "hop_result", "payload": result.to_contract_dict()})

        # 2. Optional backend speaker playback (disabled by default: PLAYBACK_ENABLED=0)
        if self.player.enabled:
            self.player.enqueue_pcm16(result.pcm_bytes, discontinuous=discontinuous)

        # 3. Record clean track if consenting clip recording is active
        if self.clips.is_recording:
            self.clips.append_live_audio(clean_pcm=result.pcm_bytes)

        # 4. Notify S3 target-lane hooks (Hydrogen Live session 2)
        for hook in list(self.on_clean_audio_hooks):
            asyncio.create_task(self._safe_call(hook, result))

        # 5. Update live DELAY / GPU metrics on browser UI
        await self.broadcast({"type": "metrics", "payload": self.build_live_metrics()})

    async def _safe_call(self, fn: Callable[..., Awaitable[Any]], *args: Any) -> None:
        try:
            await fn(*args)
        except Exception:
            pass

    async def _tail_agent_log(self) -> None:
        """Stream new lines from logs/agent.jsonl to connected browser AGENT stream."""
        offset = AGENT_LOG_PATH.stat().st_size if AGENT_LOG_PATH.exists() else 0
        while True:
            await asyncio.sleep(0.4)
            if not AGENT_LOG_PATH.exists():
                offset = 0
                continue
            try:
                size = AGENT_LOG_PATH.stat().st_size
                if size < offset:
                    offset = 0
                if size == offset:
                    continue
                with AGENT_LOG_PATH.open("r", encoding="utf-8") as f:
                    f.seek(offset)
                    lines = f.readlines()
                    offset = f.tell()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = _normalize_agent_event(raw)
                    await self.broadcast({"type": "agent_event", "payload": payload})
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    def recent_agent_events(self, limit: int = 12) -> list[dict[str, Any]]:
        if not AGENT_LOG_PATH.exists():
            return []
        try:
            lines = AGENT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(_normalize_agent_event(json.loads(line)))
            except Exception:
                continue
        return out

    async def handle_hop(self, hop: dict[str, Any]) -> None:
        session_id = str(hop.get("session_id") or "live")
        seq = int(hop.get("seq", 0))
        target_face_id = hop.get("target_face_id")
        reset = bool(hop.get("reset", False))
        t_capture = float(hop.get("t_capture") or (time.time() * 1000.0))
        hop_ms = int(hop.get("hop_ms") or self.separator.hop_ms)

        pcm_b64 = hop.get("pcm") or ""
        try:
            pcm_bytes = base64.b64decode(pcm_b64) if pcm_b64 else b""
        except Exception:
            return
        if len(pcm_bytes) % 2:
            pcm_bytes = pcm_bytes[:-1]

        crops_b64 = hop.get("crops") or []
        jpegs: list[bytes] = []
        for c in crops_b64:
            if isinstance(c, str) and c:
                try:
                    jpegs.append(base64.b64decode(c))
                except Exception:
                    continue

        if target_face_id is None:
            self.target_face_id = None
        elif target_face_id != self.target_face_id:
            self.target_face_id = str(target_face_id)
            reset = True

        if reset:
            self._mark_next_discontinuous = True

        # Dispatch to GPU separation FIRST for minimum hop latency (never queues; drops stale)
        self.separator.submit_hop(
            session_id=session_id,
            seq=seq,
            target_face_id=target_face_id,
            reset=reset,
            pcm_bytes=pcm_bytes,
            jpegs=jpegs,
            t_capture=t_capture,
            hop_ms=hop_ms,
        )

        faces = hop.get("faces") or []
        if isinstance(faces, list):
            self.latest_faces = faces
            self.consent.sync_from_faces(faces)

        if hop.get("frame_jpeg"):
            self.latest_frame_jpeg = str(hop["frame_jpeg"])

        # Keep rolling 10 s in-memory replay buffer (FB4, never written to disk)
        self.replay_buf.push(
            pcm_bytes=pcm_bytes,
            jpegs=jpegs,
            target_face_id=target_face_id,
            reset=reset,
            t_capture=t_capture,
        )

        # Consent-enforced live recording if active
        if self.clips.is_recording:
            visible_ids = [str(f["id"]) for f in faces if isinstance(f, dict) and f.get("id")]
            self.clips.append_live_audio(raw_pcm=pcm_bytes, visible_face_ids=visible_ids)

        # Notify S3 raw-lane / Decision 1 / Engine A hooks asynchronously
        for hook in list(self.on_raw_hop_hooks):
            asyncio.create_task(self._safe_call(hook, hop, pcm_bytes))

    async def handle_replay_last_10s(self) -> dict[str, Any]:
        """FB4: separate the last 10 s on tap and play it back."""
        snap = self.replay_buf.snapshot()
        if not snap:
            return {"ok": False, "reason": "replay_buffer_empty"}
        batch = [(h.pcm_bytes, h.jpegs, h.reset) for h in snap]
        t0 = time.perf_counter()
        clean_pcm = await self.separator.separate_batch_offline(
            batch, session_id="replay-10s", target_face_id=self.target_face_id
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        if not clean_pcm:
            return {"ok": False, "reason": "separator_unavailable"}

        if self.player.enabled:
            self.player.enqueue_pcm16(clean_pcm, discontinuous=True)
        payload = {
            "seq": 0,
            "pcm": base64.b64encode(clean_pcm).decode("ascii"),
            "gpu_ms": elapsed_ms,
            "queue_ms": 0.0,
            "t_return": round(time.time() * 1000.0, 1),
            "samples": len(clean_pcm) // 2,
            "engine": "replay",
        }
        await self.broadcast({"type": "hop_result", "payload": payload})
        return {"ok": True, "samples": len(clean_pcm) // 2, "elapsed_ms": elapsed_ms}


def _normalize_agent_event(raw: dict[str, Any]) -> dict[str, Any]:
    event_type = raw.get("event_type", "info")
    if event_type not in ("tool_call", "hook", "eval", "file_written", "config_release", "info"):
        event_type = "info"
    decision = raw.get("decision")
    if isinstance(decision, str):
        up = decision.upper()
        decision = up if up in ("ALLOW", "DENY") else None
    summary = (
        raw.get("summary")
        or raw.get("reason")
        or f"{raw.get('tool') or event_type}: {decision or 'ok'}"
    )
    out: dict[str, Any] = {
        "time": str(raw.get("time") or ""),
        "event_type": event_type,
        "summary": str(summary),
    }
    if raw.get("tool"):
        out["tool"] = str(raw["tool"])
    if raw.get("hook"):
        out["hook"] = str(raw["hook"])
    if decision:
        out["decision"] = decision
    if raw.get("reason"):
        out["reason"] = str(raw["reason"])
    if isinstance(raw.get("metrics_before"), dict):
        out["metrics_before"] = raw["metrics_before"]
    if isinstance(raw.get("metrics_after"), dict):
        out["metrics_after"] = raw["metrics_after"]
    return out


_RUNTIME = LiveRuntime()


def get_runtime() -> LiveRuntime:
    return _RUNTIME


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = _RUNTIME
    await _RUNTIME.start()
    # Allow S3's backend/gemini/routes.py to register live hooks if present
    try:
        from backend.gemini import routes as gemini_routes  # type: ignore

        reg = getattr(gemini_routes, "register_runtime", None)
        if callable(reg):
            maybe_coro = reg(_RUNTIME)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    except ImportError:
        pass
    except Exception:
        pass
    try:
        yield
    finally:
        await _RUNTIME.stop()


app = FastAPI(title="Look to Listen Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount S3's API router when available (AGENTS.md rule)
try:
    from backend.gemini.routes import router as _gemini_router  # type: ignore

    app.include_router(_gemini_router)
except ImportError:
    pass


# --- Pydantic request bodies ---


class ConsentRequest(BaseModel):
    face_id: str
    given: bool
    by: str | None = None
    time: str | None = None
    label: str | None = None


class PlaybackRequest(BaseModel):
    enabled: bool | None = None
    gain: float | None = None
    reset: bool = False
    reset_metrics: bool = False


class EngineControlRequest(BaseModel):
    engine: str | None = None  # "auto" | "B-GPU" | "A" | "replay"
    hop_ms: int | None = None


class ClipStartRequest(BaseModel):
    clip_id: str | None = None
    face_ids: list[str]
    metadata: dict[str, Any] = {}


# --- REST endpoints ---


@app.get("/health")
@app.get("/api/health")
async def health() -> dict[str, Any]:
    gpu_health = await _RUNTIME.separator.check_health()
    return {
        "ok": True,
        "engine": _RUNTIME.separator.active_engine,
        "engine_reason": _RUNTIME.separator.engine_reason,
        "separator": _RUNTIME.separator.status_dict(),
        "gpu_health": gpu_health,
        "playback": _RUNTIME.player.stats(),
        "hops": _RUNTIME.hop_logger.snapshot(),
        "ws_clients": len(_RUNTIME.clients),
        "recording_clip": _RUNTIME.clips.is_recording,
    }


@app.get("/api/metrics")
async def get_metrics() -> dict[str, Any]:
    return {
        **_RUNTIME.build_live_metrics(),
        "hops": _RUNTIME.hop_logger.snapshot(),
        "playback": _RUNTIME.player.stats(),
    }


@app.get("/api/end_card")
async def get_end_card() -> dict[str, Any]:
    return build_end_card_data()


@app.get("/api/evals/summary")
async def get_evals_summary() -> dict[str, Any]:
    summary_path = REPO_ROOT / "evals" / "summary.json"
    if not summary_path.exists():
        return {"exists": False, "end_card": build_end_card_data()}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {"exists": False, "end_card": build_end_card_data()}


@app.get("/api/evals/charts/{filename}")
async def serve_eval_chart(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=404, detail="Chart not found")
    charts_dir = (REPO_ROOT / "evals" / "charts").resolve()
    path = (charts_dir / filename).resolve()
    try:
        path.relative_to(charts_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="Chart not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(path)


@app.get("/api/consent")
async def list_consent() -> dict[str, Any]:
    return {"records": _RUNTIME.consent.get_all()}


@app.post("/api/consent")
async def update_consent(body: ConsentRequest) -> dict[str, Any]:
    rec = _RUNTIME.consent.set_consent(
        body.face_id,
        given=body.given,
        by=body.by,
        consent_time=body.time,
        label=body.label,
    )
    return {"ok": True, "record": rec}


@app.post("/api/playback")
async def control_playback(body: PlaybackRequest) -> dict[str, Any]:
    if body.enabled is not None:
        _RUNTIME.player.set_enabled(body.enabled)
    if body.gain is not None:
        _RUNTIME.player.set_gain(body.gain)
    if body.reset:
        _RUNTIME.player.reset()
    if body.reset_metrics:
        _RUNTIME.player.reset_metrics()
    return {"ok": True, "playback": _RUNTIME.player.stats()}


@app.post("/api/engine")
async def control_engine(body: EngineControlRequest) -> dict[str, Any]:
    if body.hop_ms is not None:
        _RUNTIME.separator.set_hop_ms(body.hop_ms)
    if body.engine is not None:
        await _RUNTIME.separator.set_override(body.engine)
    return {"ok": True, "separator": _RUNTIME.separator.status_dict()}


@app.post("/api/clips/start")
async def start_clip_recording(body: ClipStartRequest) -> dict[str, Any]:
    try:
        res = _RUNTIME.clips.start_recording(
            clip_id=body.clip_id,
            face_ids=body.face_ids,
            metadata=body.metadata,
        )
        return {"ok": True, **res}
    except ConsentDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/api/clips/stop")
async def stop_clip_recording() -> dict[str, Any]:
    try:
        res = _RUNTIME.clips.stop_recording()
        return {"ok": bool(res.get("saved")), **res}
    except ConsentDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/api/clips")
async def list_clips() -> dict[str, Any]:
    return {"clips": _RUNTIME.clips.list_clips(), "recording": _RUNTIME.clips.is_recording}


@app.get("/clips/{filename}")
async def serve_clip(filename: str) -> FileResponse:
    path = _RUNTIME.clips.resolve_clip_file(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path)


# --- Browser live WebSocket (/ws/live) ---


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    _RUNTIME.clients.add(ws)
    try:
        # Initial handshake state so UI lights up immediately
        await ws.send_text(
            json.dumps(
                {
                    "type": "engine_status",
                    "engine": _RUNTIME.separator.active_engine,
                    "reason": _RUNTIME.separator.engine_reason,
                    "hop_ms": _RUNTIME.separator.hop_ms,
                }
            )
        )
        await ws.send_text(json.dumps({"type": "metrics", "payload": _RUNTIME.build_live_metrics()}))
        for ev in _RUNTIME.recent_agent_events(limit=10):
            await ws.send_text(json.dumps({"type": "agent_event", "payload": ev}))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype == "hop" and isinstance(msg.get("payload"), dict):
                await _RUNTIME.handle_hop(msg["payload"])
            elif mtype == "set_target":
                _RUNTIME.target_face_id = msg.get("face_id")
                _RUNTIME.target_mode = str(msg.get("mode") or "auto")
                _RUNTIME._mark_next_discontinuous = True
            elif mtype == "set_consent":
                consent = msg.get("consent") or {}
                fid = msg.get("face_id")
                if fid and isinstance(consent, dict):
                    _RUNTIME.consent.set_consent(
                        str(fid),
                        given=bool(consent.get("given", False)),
                        by=consent.get("by"),
                        consent_time=consent.get("time"),
                        label=msg.get("label"),
                    )
            elif mtype == "replay_last_10s":
                await _RUNTIME.handle_replay_last_10s()
            elif mtype in _RUNTIME.on_ws_action_hooks:
                asyncio.create_task(_RUNTIME._safe_call(_RUNTIME.on_ws_action_hooks[mtype], msg, ws))
    except WebSocketDisconnect:
        pass
    finally:
        _RUNTIME.clients.discard(ws)
        if not _RUNTIME.clients:
            _RUNTIME.replay_buf.clear()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, reload=False, log_level="info")
