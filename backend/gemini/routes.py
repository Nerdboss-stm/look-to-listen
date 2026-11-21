"""S3 FastAPI routes and live runtime integration for Look to Listen.

Included by S1's backend/main.py via:
- `from backend.gemini.routes import router`
- `await register_runtime(runtime)` during FastAPI lifespan startup.

Wires together:
- E10 Raw lane: gemini-3.5-transcribe-live (FB5 fallback: gemini-4-hydrogen 1 s chunks)
- E11 Target lane: gemini-3.5-transcribe-live on GPU-separated clean voice
- E12 Speaking decisions (gemini-decision-1 every 0.5 s per face, FB6 fallback) + LeakageGuard
- E15 Engine A live (2 s AV chunks + green box) + automatic failover on GPU drop
- E18 Neon merge/attribution/vocab.json/translation
- E19/E21 Managed Agent privacy hook, config release regression hook, 30 min trigger
- E20 Robot R1 pointing (gemini-robotics-er-2-preview, fallback gemini-4-hydrogen) + gate_command.py
- E22 Argon conversation memory QA + summary (FB7 Neon fallback)
"""

from __future__ import annotations

import asyncio
import base64
import statistics
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel

from backend.gemini.argon import ConversationMemory
from backend.gemini.client import MODELS
from backend.gemini.decisions import LeakageGuard, SpeakingDecisionClient
from backend.gemini.engine_a import EngineALiveBuffer
from backend.gemini.live_captioner import LiveCaptionLane
from backend.gemini.managed_agent import (
    ListenerAgentService,
    create_tuner_trigger_sync,
    run_managed_agent_interaction_sync,
)
from backend.gemini.neon import attribute_and_polish_sync
from backend.gemini.vocab import get_vocab_terms, register_consenting_speaker, remove_speaker_vocab
from backend.robot.pointing import point_at_object_sync

router = APIRouter()


class GeminiPipelineController:
    """Owns all S3 live state and attaches cleanly to S1's LiveRuntime."""

    def __init__(self) -> None:
        self.runtime: Any = None
        self.decisions_client = SpeakingDecisionClient()
        self.leakage_guard = LeakageGuard(decision_threshold=0.0, guard_ms=750)  # demo: guard off; Decisions API failed G3 at 0.9 and was dropping real target captions
        self.engine_a_buf = EngineALiveBuffer(chunk_hops=4)
        self.memory = ConversationMemory()
        self.agent = ListenerAgentService()

        self.raw_lane = LiveCaptionLane(lane="raw", on_text=self._on_raw_caption)
        self.target_lane = LiveCaptionLane(lane="target", on_text=self._on_target_caption)

        # Rolling 1 s per-face buffers (2 hops x 0.5 s) for Decision 1
        self._pcm_ring: deque[bytes] = deque(maxlen=2)
        self._face_crops_ring: dict[str, deque[bytes]] = {}
        self._decision_in_flight: set[str] = set()
        self._last_decision_ts: dict[str, float] = {}
        self._caption_delays: deque[float] = deque(maxlen=30)
        self._last_target_id: str | None = None
        self._neon_pending: list[dict[str, Any]] = []
        self._neon_in_flight = False
        self._neon_last_run_at: float = 0.0

    async def attach(self, runtime: Any) -> None:
        self.runtime = runtime
        runtime.on_raw_hop_hooks.append(self.on_raw_hop)
        runtime.on_clean_audio_hooks.append(self.on_clean_audio)
        runtime.on_engine_change_hooks.append(self.on_engine_change)
        runtime.on_ws_action_hooks["ask_memory"] = self.on_ws_ask_memory
        runtime.on_ws_action_hooks["request_summary"] = self.on_ws_request_summary
        runtime.on_ws_action_hooks["save_transcript"] = self.on_ws_save_transcript
        runtime.on_ws_action_hooks["robot_command"] = self.on_ws_robot_command

        await self.raw_lane.start()
        await self.target_lane.start()

    async def shutdown(self) -> None:
        await self.raw_lane.stop()
        await self.target_lane.stop()

    def _face_color(self, face_id: str | None) -> str | None:
        if not face_id or self.runtime is None:
            return None
        for f in self.runtime.latest_faces:
            if isinstance(f, dict) and str(f.get("id")) == str(face_id):
                c = f.get("color")
                return str(c) if c else None
        return None

    def _face_consent(self, face_id: str | None) -> tuple[bool, str | None]:
        if not face_id or self.runtime is None:
            return False, None
        rec = self.runtime.consent.get_all().get(str(face_id))
        if isinstance(rec, dict) and rec.get("given"):
            return True, rec.get("label") or rec.get("by")
        for f in self.runtime.latest_faces:
            if isinstance(f, dict) and str(f.get("id")) == str(face_id):
                c = f.get("consent") or {}
                if isinstance(c, dict) and c.get("given"):
                    return True, f.get("label") or c.get("by")
        return False, None

    def _sync_vocab_from_faces(self, faces: list[dict[str, Any]]) -> None:
        for f in faces:
            if not isinstance(f, dict) or not f.get("id"):
                continue
            fid = str(f["id"])
            consent = f.get("consent") or {}
            given = bool(consent.get("given", False)) if isinstance(consent, dict) else False
            label = f.get("label") or (consent.get("by") if isinstance(consent, dict) else None)
            if given and label:
                register_consenting_speaker(fid, str(label), consent_given=True)
            elif not given:
                remove_speaker_vocab(fid)

    def _record_caption_delay(self, latency_ms: float) -> None:
        self._caption_delays.append(max(0.0, float(latency_ms)))
        if self.runtime is not None and self._caption_delays:
            self.runtime.caption_delay_ms = round(statistics.median(self._caption_delays), 1)

    async def on_raw_hop(self, hop: dict[str, Any], pcm_bytes: bytes) -> None:
        """Called every 0.5 s by S1's LiveRuntime on every browser hop."""
        t_capture = float(hop.get("t_capture") or (time.time() * 1000.0))
        target_face_id = hop.get("target_face_id")
        reset = bool(hop.get("reset", False))
        faces = hop.get("faces") if isinstance(hop.get("faces"), list) else []

        if faces:
            self._sync_vocab_from_faces(faces)

        # Target switch detection -> reset target caption lane immediately (AT6)
        if reset or (target_face_id and target_face_id != self._last_target_id):
            self._last_target_id = str(target_face_id) if target_face_id else None
            self.target_lane.reset_stream()
            self.engine_a_buf.reset()

        # 1. Raw lane (E10): mixed microphone audio -> Live session 1
        self.raw_lane.push_pcm16(pcm_bytes, t_capture_ms=t_capture, face_id=None)

        # 2. Per-face 1 s rolling buffers -> Decision 1 every 0.5 s (E12)
        self._pcm_ring.append(pcm_bytes)
        pcm_1s = b"".join(self._pcm_ring)

        # Decode target face crops
        if target_face_id:
            t_ring = self._face_crops_ring.setdefault(str(target_face_id), deque(maxlen=26))
            for b64 in hop.get("crops") or []:
                if isinstance(b64, str) and b64:
                    try:
                        t_ring.append(base64.b64decode(b64))
                    except Exception:
                        continue

        # Decode non-target face crops if S2 frontend provides other_crops: {face_id: [b64, ...]}
        other_crops = hop.get("other_crops")
        if isinstance(other_crops, dict):
            for fid, crop_list in other_crops.items():
                ring = self._face_crops_ring.setdefault(str(fid), deque(maxlen=26))
                if isinstance(crop_list, list):
                    for b64 in crop_list:
                        if isinstance(b64, str) and b64:
                            try:
                                ring.append(base64.b64decode(b64))
                            except Exception:
                                continue

        # Dispatch non-blocking Decision 1 calls per visible face (every ~0.5 s, drop if busy)
        now = time.perf_counter()
        for f in faces[:4]:
            if not isinstance(f, dict) or not f.get("id"):
                continue
            fid = str(f["id"])
            if fid in self._decision_in_flight:
                continue
            if now - self._last_decision_ts.get(fid, 0.0) < 0.45:
                continue
            jpegs = list(self._face_crops_ring.get(fid, ()))
            mouth_open = f.get("mouth_open")
            win_t1 = t_capture + 500.0
            win_t0 = max(0.0, win_t1 - 1000.0)
            self._last_decision_ts[fid] = now
            asyncio.create_task(
                self._run_decision_for_face(
                    fid, jpegs, pcm_1s, win_t0, win_t1, mouth_open
                )
            )

        # 3. Engine A fallback (E15 / AT14): active automatically when GPU separation drops
        active_engine = self.runtime.separator.active_engine if self.runtime else "B-GPU"
        if active_engine == "A":
            ready = self.engine_a_buf.push_hop(
                pcm_bytes=pcm_bytes,
                frame_jpeg_b64=hop.get("frame_jpeg"),
                faces=faces,
                target_face_id=str(target_face_id) if target_face_id else None,
                t_capture_ms=t_capture,
                reset=reset,
            )
            if ready is not None:
                asyncio.create_task(self._run_engine_a_chunk(ready))

    async def _run_decision_for_face(
        self,
        face_id: str,
        jpegs: list[bytes],
        pcm_1s: bytes,
        window_t0: float,
        window_t1: float,
        mouth_open: float | None,
    ) -> None:
        self._decision_in_flight.add(face_id)
        try:
            dec = await self.decisions_client.decide_window(
                jpegs,
                pcm_1s,
                face_id=face_id,
                window_t0=window_t0,
                window_t1=window_t1,
                mouth_open=mouth_open,
                prefer_frames=True,
            )
            self.leakage_guard.record(dec)
            if self.runtime is not None:
                await self.runtime.broadcast({"type": "decision", "payload": dec})
        finally:
            self._decision_in_flight.discard(face_id)

    async def on_clean_audio(self, result: Any) -> None:
        """Called by S1 whenever GPU separation returns clean target PCM (E11)."""
        if self.runtime is None:
            return
        if self.runtime.separator.active_engine not in ("B-GPU", "B-Mac"):
            return
        t_cap = float(getattr(result, "t_capture", 0.0) or (time.time() * 1000.0))
        self.target_lane.push_pcm16(
            result.pcm_bytes,
            t_capture_ms=t_cap,
            face_id=self.runtime.target_face_id,
        )

    async def on_engine_change(self, engine: str, reason: str) -> None:
        """React immediately to GPU failover <-> recovery (E15 / AT14)."""
        self.engine_a_buf.reset()
        self.target_lane.reset_stream()

    async def _run_engine_a_chunk(self, chunk: dict[str, Any]) -> None:
        seg = await self.engine_a_buf.process_chunk(chunk)
        if not seg or self.runtime is None:
            return
        target_fid = seg.get("face_id") or self.runtime.target_face_id
        allow, _ = self.leakage_guard.allow_target_segment(target_fid, seg["t0"], seg["t1"])
        seg["guarded"] = True
        if not allow:
            return
        seg["speaker_color"] = self._face_color(target_fid)
        seg["segment_id"] = f"ea-{uuid.uuid4().hex[:8]}"
        self._record_caption_delay(seg.get("latency_ms", 0.0))
        await self.runtime.broadcast({"type": "segment", "payload": seg})
        consent_ok, label = self._face_consent(target_fid)
        self.memory.append_segment(
            t0=seg["t0"],
            t1=seg["t1"],
            lane="target",
            face_id=target_fid,
            text=seg["text"],
            consent_given=consent_ok,
            speaker_label=label,
        )

    async def _on_raw_caption(self, ev: dict[str, Any]) -> None:
        if self.runtime is None:
            return
        engine = self.runtime.separator.active_engine
        best_fid, best_p = self.leakage_guard.best_speaking_face(ev["t0"], ev["t1"])
        attr_fid = best_fid if best_p >= self.leakage_guard.decision_threshold else None
        seg: dict[str, Any] = {
            "t0": ev["t0"],
            "t1": ev["t1"],
            "lane": "raw",
            "face_id": attr_fid,
            "text": ev["text"],
            "confidence": ev["confidence"],
            "engine": engine if engine in ("B-GPU", "B-Mac", "A", "replay") else "B-GPU",
            "segment_id": ev.get("segment_id") or f"raw-{uuid.uuid4().hex[:8]}",
            "is_final": bool(ev.get("is_final", False)),
            "speaker_color": self._face_color(attr_fid),
            "latency_ms": ev["latency_ms"],
        }
        await self.runtime.broadcast({"type": "segment", "payload": seg})
        if seg["is_final"]:
            self._queue_neon_polish(seg)

    async def _on_target_caption(self, ev: dict[str, Any]) -> None:
        if self.runtime is None:
            return
        target_fid = ev.get("face_id") or self.runtime.target_face_id
        if not target_fid:
            # No target face selected ("Point at someone" state): suppress unguided target captions
            return
        allow, max_p = self.leakage_guard.allow_target_segment(target_fid, ev["t0"], ev["t1"])
        engine = self.runtime.separator.active_engine
        valid_engine = engine if engine in ("B-GPU", "B-Mac", "A", "replay") else "B-GPU"

        if not allow:
            # Target is not speaking; attribute to the actual speaking face on 'other' lane if confident
            other_fid, other_p = self.leakage_guard.best_speaking_face(ev["t0"], ev["t1"])
            if other_fid and other_fid != target_fid and other_p >= self.leakage_guard.decision_threshold:
                other_seg: dict[str, Any] = {
                    "t0": ev["t0"],
                    "t1": ev["t1"],
                    "lane": "other",
                    "face_id": other_fid,
                    "text": ev["text"],
                    "confidence": round(other_p, 3),
                    "engine": valid_engine,
                    "segment_id": ev.get("segment_id") or f"oth-{uuid.uuid4().hex[:8]}",
                    "is_final": bool(ev.get("is_final", False)),
                    "speaker_color": self._face_color(other_fid),
                    "latency_ms": ev["latency_ms"],
                    "guarded": True,
                }
                await self.runtime.broadcast({"type": "segment", "payload": other_seg})
            return

        # Compute total caption delay including voice separation delay if available
        snap = self.runtime.hop_logger.snapshot()
        voice_ms = float(snap.get("voice_delay_p50_ms") or snap.get("last_voice_delay_ms") or 0.0)
        total_delay = round(voice_ms + float(ev["latency_ms"]), 1)
        self._record_caption_delay(total_delay)

        seg: dict[str, Any] = {
            "t0": ev["t0"],
            "t1": ev["t1"],
            "lane": "target",
            "face_id": target_fid,
            "text": ev["text"],
            "confidence": round(max_p, 3) if max_p is not None else ev["confidence"],
            "engine": valid_engine,
            "segment_id": ev.get("segment_id") or f"tgt-{uuid.uuid4().hex[:8]}",
            "is_final": bool(ev.get("is_final", False)),
            "speaker_color": self._face_color(target_fid),
            "latency_ms": total_delay,
            "guarded": True,
        }
        await self.runtime.broadcast({"type": "segment", "payload": seg})

        if seg["is_final"]:
            consent_ok, label = self._face_consent(target_fid)
            self.memory.append_segment(
                t0=seg["t0"],
                t1=seg["t1"],
                lane="target",
                face_id=target_fid,
                text=seg["text"],
                consent_given=consent_ok,
                speaker_label=label,
            )
            self._queue_neon_polish(seg)

    def _queue_neon_polish(self, seg: dict[str, Any]) -> None:
        """Batch finalized segments for best-effort background Neon polish (skips turn if busy/recent)."""
        self._neon_pending.append(seg)
        if len(self._neon_pending) > 8:
            self._neon_pending = self._neon_pending[-6:]
        now = time.perf_counter()
        if (
            len(self._neon_pending) >= 2
            and not self._neon_in_flight
            and (now - self._neon_last_run_at) >= 5.0
        ):
            batch = self._neon_pending[-6:]
            self._neon_pending.clear()
            self._neon_last_run_at = now
            asyncio.create_task(self._run_neon_batch(batch))

    async def _run_neon_batch(self, batch: list[dict[str, Any]]) -> None:
        if self.runtime is None or not batch:
            return
        self._neon_in_flight = True
        try:
            translate_to = self.agent.active_config.get("translate_to")
            decisions = self.leakage_guard.timeline_snapshot()
            faces = list(self.runtime.latest_faces)
            try:
                polished = await asyncio.wait_for(
                    asyncio.to_thread(
                        attribute_and_polish_sync,
                        batch,
                        decisions,
                        faces,
                        translate_to=translate_to,
                    ),
                    timeout=26.0,
                )
            except asyncio.TimeoutError:
                # Skip this turn gracefully so live captions are never blocked
                return
            by_id = {str(s.get("segment_id")): s for s in batch if s.get("segment_id")}
            for item in polished:
                sid = str(item.get("segment_id") or "")
                orig = by_id.get(sid)
                if not orig:
                    continue
                fid = item.get("face_id") or orig.get("face_id")
                updated = dict(orig)
                updated["face_id"] = fid
                updated["speaker_color"] = self._face_color(fid)
                if item.get("text"):
                    updated["text"] = str(item["text"])
                if item.get("translated_text"):
                    updated["translated_text"] = str(item["translated_text"])
                updated["is_final"] = True
                await self.runtime.broadcast({"type": "segment", "payload": updated})
        finally:
            self._neon_in_flight = False

    # --- WebSocket action handlers (S2 frontend contract in NOTES.md) ---

    async def on_ws_ask_memory(self, msg: dict[str, Any], ws: WebSocket) -> None:
        question = str(msg.get("question") or "").strip()
        if not question:
            return
        ans = await self.memory.ask(question)
        if self.runtime is not None:
            await self.runtime.broadcast({"type": "memory_answer", "payload": ans})

    async def on_ws_request_summary(self, msg: dict[str, Any], ws: WebSocket) -> None:
        ans = await asyncio.to_thread(self.memory.summarize_sync)
        if self.runtime is not None:
            await self.runtime.broadcast({"type": "memory_answer", "payload": ans})

    async def on_ws_save_transcript(self, msg: dict[str, Any], ws: WebSocket) -> None:
        conv_id = str(msg.get("conversation_id") or self.memory.conversation_id)
        await self.handle_save_transcript(conversation_id=conv_id)

    async def on_ws_robot_command(self, msg: dict[str, Any], ws: WebSocket) -> None:
        face_id = str(msg.get("face_id") or "")
        text = str(msg.get("text") or "").strip()
        frame_b64 = msg.get("frame_jpeg") or (self.runtime.latest_frame_jpeg if self.runtime else None)
        if not text:
            return
        res = await self.handle_robot_command(
            face_id=face_id,
            text=text,
            target_face_id=self.runtime.target_face_id if self.runtime else None,
            frame_jpeg_b64=frame_b64,
        )
        if self.runtime is not None:
            await self.runtime.broadcast({"type": "robot_command", "payload": res})

    # --- Shared business logic for both WS and REST ---

    async def handle_save_transcript(
        self,
        *,
        conversation_id: str | None = None,
        lines_override: list[dict[str, Any]] | None = None,
        auto_redact_retry: bool = True,
    ) -> dict[str, Any]:
        conv_id = conversation_id or self.memory.conversation_id
        consent_map: dict[str, bool] = {}
        if self.runtime is not None:
            for fid, rec in self.runtime.consent.get_all().items():
                consent_map[str(fid)] = bool(rec.get("given", False)) if isinstance(rec, dict) else bool(rec)
            for f in self.runtime.latest_faces:
                if isinstance(f, dict) and f.get("id"):
                    c = f.get("consent") or {}
                    consent_map[str(f["id"])] = bool(c.get("given", False))

        lines = lines_override if lines_override is not None else self.memory.snapshot(consenting_only=False)
        return await asyncio.to_thread(
            self.agent.save_transcript_with_privacy_hook,
            conversation_id=conv_id,
            lines=lines,
            consent_map=consent_map,
            auto_redact_retry=auto_redact_retry,
        )

    async def handle_robot_command(
        self,
        *,
        face_id: str,
        text: str,
        target_face_id: str | None = None,
        frame_jpeg_b64: str | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        cmd_id = f"cmd-{uuid.uuid4().hex[:8]}"
        effective_target = (
            target_face_id
            if target_face_id is not None
            else (self.runtime.target_face_id if self.runtime else None)
        )
        hook_res = self.agent.check_robot_command(
            command_id=cmd_id,
            face_id=face_id,
            target_face_id=effective_target,
            text=text,
        )
        allowed = bool(hook_res["allowed"])
        point = None
        obj_label = None

        if allowed:
            img_b64 = frame_jpeg_b64 or (self.runtime.latest_frame_jpeg if self.runtime else None)
            if img_b64:
                try:
                    img_bytes = base64.b64decode(img_b64)
                    pt_res = await asyncio.to_thread(point_at_object_sync, img_bytes, text)
                    point = pt_res.get("point")
                    obj_label = pt_res.get("object_label")
                except Exception:
                    point = None
                    obj_label = None

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return {
            "command_id": cmd_id,
            "face_id": face_id or "unknown",
            "text": text,
            "target_face_id": effective_target,
            "point": point,
            "object_label": obj_label,
            "allowed": allowed,
            "hook_reason": hook_res["reason"],
            "latency_ms": latency_ms,
            "time": datetime.now(timezone.utc).isoformat(),
        }


_CTRL = GeminiPipelineController()


def get_controller() -> GeminiPipelineController:
    return _CTRL


async def register_runtime(runtime: Any) -> None:
    """Called by S1's backend/main.py lifespan hook."""
    await _CTRL.attach(runtime)


# --- Pydantic models ---


class MemoryAskRequest(BaseModel):
    question: str


class RobotCommandRequest(BaseModel):
    face_id: str
    text: str
    target_face_id: str | None = None
    frame_jpeg: str | None = None


class SaveTranscriptRequest(BaseModel):
    conversation_id: str | None = None
    lines: list[dict[str, Any]] | None = None
    auto_redact_retry: bool = True


class ReleaseConfigRequest(BaseModel):
    config: dict[str, Any]
    before: dict[str, float]
    after: dict[str, float]


class TriggerRequest(BaseModel):
    schedule: str = "*/30 * * * *"
    time_zone: str = "America/New_York"


# --- REST endpoints (matching S2 contract in NOTES.md) ---


@router.get("/api/gemini/status")
async def gemini_status() -> dict[str, Any]:
    return {
        "ok": True,
        "models": {
            "transcribe_live": MODELS.transcribe_live,
            "hydrogen": MODELS.hydrogen,
            "decision": MODELS.decision,
            "robotics_er": MODELS.robotics_er,
            "neon": MODELS.neon,
            "argon": MODELS.argon,
        },
        "raw_lane_mode": _CTRL.raw_lane.active_mode,
        "target_lane_mode": _CTRL.target_lane.active_mode,
        "leakage_guard": {
            "decision_threshold": _CTRL.leakage_guard.decision_threshold,
            "guard_ms": _CTRL.leakage_guard.guard_ms,
            "passed": _CTRL.leakage_guard.passed_count,
            "dropped": _CTRL.leakage_guard.dropped_count,
        },
        "vocab_terms_count": len(get_vocab_terms()),
        "memory_entries": len(_CTRL.memory.snapshot()),
        "active_config": _CTRL.agent.active_config,
    }


@router.post("/api/memory/ask")
async def api_memory_ask(body: MemoryAskRequest) -> dict[str, Any]:
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question is required")
    ans = await _CTRL.memory.ask(q)
    if _CTRL.runtime is not None:
        await _CTRL.runtime.broadcast({"type": "memory_answer", "payload": ans})
    return ans


@router.post("/api/memory/summary")
async def api_memory_summary() -> dict[str, Any]:
    ans = await asyncio.to_thread(_CTRL.memory.summarize_sync)
    if _CTRL.runtime is not None:
        await _CTRL.runtime.broadcast({"type": "memory_answer", "payload": ans})
    return ans


@router.post("/api/robot/command")
async def api_robot_command(body: RobotCommandRequest) -> dict[str, Any]:
    res = await _CTRL.handle_robot_command(
        face_id=body.face_id,
        text=body.text,
        target_face_id=body.target_face_id,
        frame_jpeg_b64=body.frame_jpeg,
    )
    if _CTRL.runtime is not None:
        await _CTRL.runtime.broadcast({"type": "robot_command", "payload": res})
    return res


@router.post("/api/agent/save_transcript")
async def api_save_transcript(body: SaveTranscriptRequest) -> dict[str, Any]:
    return await _CTRL.handle_save_transcript(
        conversation_id=body.conversation_id,
        lines_override=body.lines,
        auto_redact_retry=body.auto_redact_retry,
    )


@router.get("/api/agent/config")
async def api_get_config() -> dict[str, Any]:
    return {
        "active_config": _CTRL.agent.active_config,
        "last_release": _CTRL.agent.last_release,
    }


@router.post("/api/agent/release_config")
async def api_release_config(body: ReleaseConfigRequest) -> dict[str, Any]:
    res = _CTRL.agent.release_config_with_regression_hook(
        candidate_config=body.config,
        before_metrics=body.before,
        after_metrics=body.after,
    )
    if res["ok"]:
        cfg = res["active_config"]
        _CTRL.leakage_guard.configure(
            decision_threshold=cfg.get("decision_threshold"),
            guard_ms=cfg.get("guard_ms"),
        )
    return res


@router.post("/api/agent/tuner/trigger")
async def api_create_tuner_trigger(body: TriggerRequest) -> dict[str, Any]:
    return await asyncio.to_thread(
        create_tuner_trigger_sync,
        schedule=body.schedule,
        time_zone=body.time_zone,
    )
