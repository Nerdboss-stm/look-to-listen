"""Async WebSocket client to the GPU ClearVoice separation server (Engine B-GPU).

Implements the SPEC binary wire format, stale-hop dropping (never queues hops),
automatic failover to Engine A within <= 3 s if the GPU server dies (AT14 / FB1),
and automatic recovery when the GPU server comes back.

Never logs SEPARATOR_URL credentials or SEPARATOR_TOKEN.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx
import websockets

from backend.separation.hop_logger import HopLogger


@dataclass
class PendingHop:
    session_id: str
    seq: int
    target_face_id: str | None
    reset: bool
    pcm_bytes: bytes
    jpegs: list[bytes]
    t_capture: float
    hop_ms: int


@dataclass
class SeparationResult:
    session_id: str
    seq: int
    covers: list[int]
    samples: int
    pcm_bytes: bytes
    gpu_ms: float
    queue_ms: float
    gpu_rtt_ms: float
    rtt_ms: float
    t_capture: float | None
    t_return: float
    sent_ms: float | None
    engine: str
    voice_delay_ms: float

    def to_contract_dict(self) -> dict[str, Any]:
        """Serialize to contracts/hop_result.schema.json."""
        return {
            "seq": self.seq,
            "pcm": base64.b64encode(self.pcm_bytes).decode("ascii"),
            "gpu_ms": round(self.gpu_ms, 1),
            "queue_ms": round(self.queue_ms, 1),
            "t_return": round(self.t_return, 1),
            "covers": self.covers,
            "samples": self.samples,
            "t_capture": round(self.t_capture, 1) if self.t_capture is not None else None,
            "sent_ms": round(self.sent_ms, 1) if self.sent_ms is not None else None,
            "rtt_ms": round(self.rtt_ms, 1),
            "engine": self.engine,
        }


ResultCallback = Callable[[SeparationResult], Awaitable[None]]
EngineCallback = Callable[[str, str], Awaitable[None]]


def _derive_health_url(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    return f"{scheme}://{parsed.netloc}/health"


def _pack_binary_hop(hop: PendingHop, sent_ms: float) -> bytes:
    header = {
        "session_id": hop.session_id,
        "seq": hop.seq,
        "target_face_id": hop.target_face_id if hop.target_face_id is not None else "",
        "reset": bool(hop.reset),
        "pcm_bytes": len(hop.pcm_bytes),
        "jpeg_sizes": [len(j) for j in hop.jpegs],
        "sent_ms": round(sent_ms),
    }
    head_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(head_bytes)) + head_bytes + hop.pcm_bytes + b"".join(hop.jpegs)


def _unpack_binary_result(frame: bytes) -> tuple[dict[str, Any], bytes]:
    if len(frame) < 4:
        raise ValueError("binary result frame too short")
    n = struct.unpack_from("<I", frame, 0)[0]
    if 4 + n > len(frame):
        raise ValueError("binary result header truncated")
    meta = json.loads(frame[4 : 4 + n].decode("utf-8"))
    pcm = frame[4 + n :]
    return meta, pcm


class SeparationClient:
    """Manages the persistent WebSocket connection to Engine B-GPU with failover."""

    def __init__(
        self,
        *,
        hop_logger: HopLogger,
        on_result: ResultCallback | None = None,
        on_engine_change: EngineCallback | None = None,
        playback_buf_ms_provider: Callable[[], float] | None = None,
        url: str | None = None,
        token: str | None = None,
        hop_timeout_s: float = 2.0,
        max_consecutive_timeouts: int = 3,
        failover_timeout_s: float = 3.0,
        connect_timeout_s: float = 1.5,
        probe_interval_s: float = 2.0,
        recovery_probes_required: int = 2,
        max_inflight: int = 4,
    ) -> None:
        self._url = (url if url is not None else os.environ.get("SEPARATOR_URL", "")).strip()
        self._token = (token if token is not None else os.environ.get("SEPARATOR_TOKEN", "")).strip()
        self._health_url = _derive_health_url(self._url) if self._url else ""
        self._hop_logger = hop_logger
        self._on_result = on_result
        self._on_engine_change = on_engine_change
        self._playback_buf_ms_provider = playback_buf_ms_provider or (lambda: 150.0)

        self._hop_timeout_s = hop_timeout_s
        self._max_consecutive_timeouts = max(1, int(max_consecutive_timeouts))
        self._failover_timeout_s = failover_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._probe_interval_s = probe_interval_s
        self._recovery_probes_required = max(1, int(recovery_probes_required))

        self._ws: Any = None
        self._connected = False
        self._disconnected_since_perf: float | None = None
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []

        # Single-slot latest-hop mailbox (NEVER queues hops!)
        self._latest_hop: PendingHop | None = None
        self._hop_event = asyncio.Event()

        # In-flight hop timestamps for RTT & jitter-tolerant timeout tracking
        self._inflight: dict[int, tuple[PendingHop, float, float]] = {}
        self._timed_out_seqs: set[int] = set()
        self._consecutive_timeouts: int = 0
        self._last_timeout_tick_perf: float = 0.0
        self._max_inflight: int = max(1, int(max_inflight))
        self._last_sent_perf: float | None = None
        self._last_recv_perf: float | None = None
        self._awaiting_since_perf: float | None = None
        self._started_perf: float = 0.0

        # Engine / failover / recovery state
        self._override_engine: str | None = None  # None = auto
        self._in_failover: bool = not bool(self._url and self._token)
        self._recovery_good_replies: int = 0
        self._active_engine: str = "B-GPU" if (self._url and self._token) else "A"
        self._engine_reason: str = (
            "gpu_configured" if (self._url and self._token) else "separator_env_missing"
        )
        self._last_health: dict[str, Any] | None = None
        self._hop_ms: int = 500
        self._need_reset_on_reconnect = True

    @property
    def active_engine(self) -> str:
        return self._override_engine or self._active_engine

    @property
    def engine_reason(self) -> str:
        return f"override:{self._override_engine}" if self._override_engine else self._engine_reason

    @property
    def is_gpu_connected(self) -> bool:
        return self._connected and self._ws is not None

    @property
    def hop_ms(self) -> int:
        return self._hop_ms

    def set_hop_ms(self, hop_ms: int) -> None:
        self._hop_ms = max(250, min(2000, int(hop_ms)))

    async def set_override(self, engine: str | None) -> None:
        if engine in (None, "", "auto"):
            self._override_engine = None
            await self._emit_engine(self._active_engine, self._engine_reason, force=True)
        else:
            self._override_engine = engine
            await self._emit_engine(engine, f"manual_override:{engine}", force=True)

    async def _set_auto_engine(self, engine: str, reason: str) -> None:
        changed = (engine != self._active_engine) or (reason != self._engine_reason)
        self._active_engine = engine
        self._engine_reason = reason
        if changed and self._override_engine is None:
            await self._emit_engine(engine, reason, force=False)

    async def _emit_engine(self, engine: str, reason: str, force: bool = False) -> None:
        self._hop_logger.log_event(
            session_id="system",
            engine=engine,
            status="failover" if engine != "B-GPU" else "engine_ready",
            reason=reason,
        )
        if self._on_engine_change is not None:
            try:
                await self._on_engine_change(engine, reason)
            except Exception:
                pass

    async def check_health(self) -> dict[str, Any]:
        """Probe the GPU server's /health endpoint without logging secrets."""
        if not self._health_url:
            return {"ok": False, "error": "separator_url_not_configured"}
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.get(self._health_url)
                if r.status_code == 200:
                    data = r.json()
                    self._last_health = data
                    return data
                return {"ok": False, "status_code": r.status_code}
        except Exception as e:
            return {"ok": False, "error": type(e).__name__}

    async def _failover_to_a(self, reason: str, *, close_ws: bool = True) -> None:
        """Atomically transition to Engine A BEFORE closing WS (prevents reconnect race)."""
        self._in_failover = True
        self._recovery_good_replies = 0
        self._consecutive_timeouts = 0
        self._awaiting_since_perf = None
        self._inflight.clear()
        await self._set_auto_engine("A", reason)
        if close_ws:
            await self._close_ws()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._started_perf = time.perf_counter()
        if not self._url or not self._token:
            self._in_failover = True
            await self._set_auto_engine("A", "separator_not_configured")
            return
        # Probe health immediately at startup
        health = await self.check_health()
        if health.get("ok"):
            self._in_failover = False
            await self._set_auto_engine("B-GPU", "gpu_healthy")
        else:
            self._in_failover = True
            await self._set_auto_engine("A", "gpu_unreachable_at_startup")

        self._tasks = [
            asyncio.create_task(self._connection_loop(), name="sep-conn"),
            asyncio.create_task(self._sender_loop(), name="sep-send"),
            asyncio.create_task(self._watchdog_loop(), name="sep-watchdog"),
            asyncio.create_task(self._recovery_loop(), name="sep-recovery"),
        ]

    async def stop(self) -> None:
        self._running = False
        self._hop_event.set()
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self._close_ws()

    async def _close_ws(self) -> None:
        ws = self._ws
        self._ws = None
        if self._connected and self._disconnected_since_perf is None:
            self._disconnected_since_perf = time.perf_counter()
        self._connected = False
        self._awaiting_since_perf = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def _connect_ws(self) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    self._url,
                    additional_headers=headers,
                    max_size=None,
                    compression=None,
                    ping_interval=10,
                    ping_timeout=5,
                    open_timeout=self._connect_timeout_s,
                    close_timeout=1.0,
                ),
                timeout=self._connect_timeout_s + 0.5,
            )
        except TypeError:
            ws = await asyncio.wait_for(
                websockets.connect(
                    self._url,
                    extra_headers=headers,
                    max_size=None,
                    compression=None,
                    ping_interval=10,
                    ping_timeout=5,
                    open_timeout=self._connect_timeout_s,
                    close_timeout=1.0,
                ),
                timeout=self._connect_timeout_s + 0.5,
            )
        # Disable Nagle's algorithm for minimal upload latency
        try:
            transport = getattr(ws, "transport", None)
            sock = transport.get_extra_info("socket") if transport is not None else None
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        return ws

    async def _connection_loop(self) -> None:
        backoff = 0.5
        ever_connected = False
        while self._running:
            try:
                ws = await self._connect_ws()
                self._ws = ws
                self._connected = True
                self._disconnected_since_perf = None
                self._need_reset_on_reconnect = True
                self._inflight.clear()
                self._timed_out_seqs.clear()
                self._consecutive_timeouts = 0
                self._awaiting_since_perf = None
                backoff = 0.5
                ever_connected = True
                # Only enter B-GPU directly if we are NOT in failover recovery;
                # after a failover, _recovery_loop requires 2 good probes (every 2 s) before switching back.
                if not self._in_failover:
                    await self._set_auto_engine("B-GPU", "gpu_connected")
                    self._hop_event.set()
                elif self._engine_reason == "gpu_unreachable_at_startup":
                    # Initial connect succeeded (e.g. WS-only mock server without HTTP /health)
                    self._in_failover = False
                    await self._set_auto_engine("B-GPU", "gpu_connected")
                    self._hop_event.set()

                async for msg in ws:
                    await self._handle_server_message(msg)
                # Server closed socket cleanly without exception -> treat as disconnect
                raise ConnectionError("gpu_ws_closed")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                reason = f"gpu_ws_disconnected:{type(e).__name__}"
                await self._close_ws()
                # If we were actively on B-GPU (not already failed over by watchdog),
                # attempt one fast silent reconnect to absorb brief SSH/Wi-Fi blips.
                if ever_connected and not self._in_failover and self._active_engine == "B-GPU" and self._running:
                    await asyncio.sleep(0.15)
                    try:
                        ws = await self._connect_ws()
                        self._ws = ws
                        self._connected = True
                        self._disconnected_since_perf = None
                        self._need_reset_on_reconnect = True
                        self._inflight.clear()
                        self._timed_out_seqs.clear()
                        self._consecutive_timeouts = 0
                        self._awaiting_since_perf = None
                        self._hop_event.set()
                        async for msg in ws:
                            await self._handle_server_message(msg)
                        raise ConnectionError("gpu_ws_closed")
                    except asyncio.CancelledError:
                        raise
                    except Exception as e2:
                        reason = f"gpu_ws_disconnected:{type(e2).__name__}"
                        await self._close_ws()
                if not self._in_failover:
                    await self._failover_to_a(reason, close_ws=False)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 2.0)

    async def _probe_gpu_once(self) -> bool:
        """Probe GPU responsiveness: prefers WS ping on the live /separate socket, falls back to /health."""
        ws = self._ws
        if self._connected and ws is not None:
            try:
                pong = await ws.ping()
                await asyncio.wait_for(pong, timeout=2.5)
                return True
            except asyncio.TimeoutError:
                return False
            except Exception:
                await self._close_ws()
                return False
        health = await self.check_health()
        return bool(health.get("ok"))

    async def _recovery_loop(self) -> None:
        """When failed over to Engine A, probe GPU every 2 s and switch back after 2 good replies."""
        while self._running:
            await asyncio.sleep(self._probe_interval_s)
            if not self._in_failover or self._override_engine is not None:
                self._recovery_good_replies = 0
                continue
            ok = await self._probe_gpu_once()
            if ok and self._connected:
                self._recovery_good_replies += 1
                self._hop_logger.log_event(
                    session_id="system",
                    engine="A",
                    status="probe_ok",
                    reason=f"gpu_probe_ok:{self._recovery_good_replies}/{self._recovery_probes_required}",
                )
                if self._recovery_good_replies >= self._recovery_probes_required:
                    self._in_failover = False
                    self._recovery_good_replies = 0
                    self._consecutive_timeouts = 0
                    self._awaiting_since_perf = None
                    self._need_reset_on_reconnect = True
                    await self._set_auto_engine("B-GPU", "gpu_recovered")
                    self._hop_event.set()
            else:
                self._recovery_good_replies = 0

    async def _watchdog_loop(self) -> None:
        while self._running:
            await asyncio.sleep(0.15)
            now = time.perf_counter()

            if self._in_failover:
                continue

            if self._connected:
                # 1. Expire individual slow hops as stale without failing over on a single slow reply
                expired: list[int] = [
                    seq
                    for seq, (_, t_send_perf, _) in list(self._inflight.items())
                    if (now - t_send_perf) > self._hop_timeout_s
                ]
                if expired:
                    for seq in expired:
                        entry = self._inflight.pop(seq, None)
                        if entry is None:
                            continue
                        hop, t_send_perf, _ = entry
                        self._timed_out_seqs.add(seq)
                        if len(self._timed_out_seqs) > 256:
                            self._timed_out_seqs.clear()
                        self._hop_logger.log_drop(
                            session_id=hop.session_id,
                            seq=hop.seq,
                            target_face_id=hop.target_face_id,
                            engine="B-GPU",
                            hop_ms=hop.hop_ms,
                            t_capture=hop.t_capture,
                            age_ms=(now - t_send_perf) * 1000.0,
                            reason="hop_response_timeout",
                            n_crops=len(hop.jpegs),
                        )
                    # Count at most 1 consecutive timeout per hop_timeout_s*0.75 window so multiple
                    # concurrent inflight hops caught in ONE Wi-Fi stall don't triple-count.
                    if (now - self._last_timeout_tick_perf) >= (self._hop_timeout_s * 0.75):
                        self._consecutive_timeouts += 1
                        self._last_timeout_tick_perf = now
                    if self._latest_hop is not None and len(self._inflight) < self._max_inflight:
                        self._hop_event.set()

                # 2. Fail over ONLY after 3 consecutive timeouts OR no reply at all for >= 3.0 s
                no_reply_s = (
                    (now - self._awaiting_since_perf)
                    if self._awaiting_since_perf is not None
                    else 0.0
                )
                if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                    count = self._consecutive_timeouts
                    await self._failover_to_a(f"gpu_consecutive_timeouts:{count}")
                elif no_reply_s >= self._failover_timeout_s:
                    await self._failover_to_a("gpu_no_reply_timeout")
            elif (
                (now - self._started_perf) >= 2.0
                and self._active_engine == "B-GPU"
                and self._disconnected_since_perf is not None
                and (now - self._disconnected_since_perf) >= 1.5
            ):
                await self._failover_to_a("gpu_disconnected", close_ws=False)

    def submit_hop(
        self,
        *,
        session_id: str,
        seq: int,
        target_face_id: str | None,
        reset: bool,
        pcm_bytes: bytes,
        jpegs: list[bytes],
        t_capture: float,
        hop_ms: int | None = None,
    ) -> bool:
        """Submit a hop to be sent to B-GPU. Drops stale hops; never queues."""
        eff_hop_ms = int(hop_ms or self._hop_ms)
        now_ms = time.time() * 1000.0
        # Drop if already stale (older than one hop length, AGENTS.md rule)
        if t_capture > 0:
            age_ms = now_ms - t_capture
            if age_ms > max(eff_hop_ms, 500) * 1.15:
                self._hop_logger.log_drop(
                    session_id=session_id,
                    seq=seq,
                    target_face_id=target_face_id,
                    engine=self.active_engine,
                    hop_ms=eff_hop_ms,
                    t_capture=t_capture,
                    age_ms=age_ms,
                    reason="stale_on_arrival",
                    n_crops=len(jpegs),
                )
                return False

        if self.active_engine != "B-GPU" or not self._connected:
            return False

        hop = PendingHop(
            session_id=session_id,
            seq=seq,
            target_face_id=target_face_id,
            reset=reset,
            pcm_bytes=pcm_bytes,
            jpegs=jpegs,
            t_capture=t_capture,
            hop_ms=eff_hop_ms,
        )

        # Single-slot mailbox: overwrite stale unsent hop instead of queueing
        prev = self._latest_hop
        if prev is not None:
            # Preserve reset flag if the superseded hop had reset=True
            if prev.reset and not hop.reset:
                hop.reset = True
            self._hop_logger.log_drop(
                session_id=prev.session_id,
                seq=prev.seq,
                target_face_id=prev.target_face_id,
                engine="B-GPU",
                hop_ms=prev.hop_ms,
                t_capture=prev.t_capture,
                age_ms=max(0.0, now_ms - prev.t_capture),
                reason="superseded_by_newer_hop",
                n_crops=len(prev.jpegs),
            )

        self._latest_hop = hop
        self._hop_event.set()
        return True

    async def _sender_loop(self) -> None:
        while self._running:
            await self._hop_event.wait()
            self._hop_event.clear()

            # Prevent TCP/SSH tunnel bufferbloat: wait until < max_inflight hops are in flight
            if len(self._inflight) >= self._max_inflight:
                continue

            hop = self._latest_hop
            self._latest_hop = None
            if hop is None:
                continue

            ws = self._ws
            if ws is None or not self._connected or self.active_engine != "B-GPU":
                continue

            now_ms = time.time() * 1000.0
            if hop.t_capture > 0:
                age_ms = now_ms - hop.t_capture
                if age_ms > max(hop.hop_ms, 500) * 1.15:
                    self._hop_logger.log_drop(
                        session_id=hop.session_id,
                        seq=hop.seq,
                        target_face_id=hop.target_face_id,
                        engine="B-GPU",
                        hop_ms=hop.hop_ms,
                        t_capture=hop.t_capture,
                        age_ms=age_ms,
                        reason="stale_before_send",
                        n_crops=len(hop.jpegs),
                    )
                    continue

            if self._need_reset_on_reconnect:
                hop.reset = True
                self._need_reset_on_reconnect = False

            t_send_perf = time.perf_counter()
            t_send_ms = time.time() * 1000.0
            payload = _pack_binary_hop(hop, t_send_ms)

            # Prune inflight table to avoid unbounded growth
            if len(self._inflight) > 128:
                oldest_keys = sorted(self._inflight.keys())[:-64]
                for k in oldest_keys:
                    self._inflight.pop(k, None)
            self._inflight[hop.seq] = (hop, t_send_perf, t_send_ms)
            self._last_sent_perf = t_send_perf
            if self._awaiting_since_perf is None:
                self._awaiting_since_perf = t_send_perf

            try:
                await asyncio.wait_for(ws.send(payload), timeout=self._hop_timeout_s)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                # Single slow send: drop this hop as stale instead of flapping immediately
                self._inflight.pop(hop.seq, None)
                self._timed_out_seqs.add(hop.seq)
                self._consecutive_timeouts += 1
                self._hop_logger.log_drop(
                    session_id=hop.session_id,
                    seq=hop.seq,
                    target_face_id=hop.target_face_id,
                    engine="B-GPU",
                    hop_ms=hop.hop_ms,
                    t_capture=hop.t_capture,
                    age_ms=(time.perf_counter() - t_send_perf) * 1000.0,
                    reason="hop_send_timeout",
                    n_crops=len(hop.jpegs),
                )
                if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                    count = self._consecutive_timeouts
                    await self._failover_to_a(f"gpu_consecutive_timeouts:{count}")
            except Exception as e:
                if not self._in_failover:
                    await self._failover_to_a(f"gpu_send_failed:{type(e).__name__}")

    async def _handle_server_message(self, msg: Any) -> None:
        now_perf = time.perf_counter()
        t_return_ms = time.time() * 1000.0
        self._last_recv_perf = now_perf

        if isinstance(msg, str):
            # Server sends text only for errors like {"error": "bad hop: ..."}
            self._hop_logger.log_event(
                session_id="system",
                engine="B-GPU",
                status="error",
                reason=f"server_text:{msg[:160]}",
            )
            return

        meta, clean_pcm = _unpack_binary_result(msg)
        seq = int(meta.get("seq", 0))
        covers = meta.get("covers") or [seq, seq]
        gpu_ms = float(meta.get("gpu_ms", 0.0))
        queue_ms = float(meta.get("queue_ms", 0.0))
        samples = int(meta.get("samples", len(clean_pcm) // 2))
        sent_ms = meta.get("sent_ms")

        inflight = self._inflight.pop(seq, None)
        # Also clear any earlier seqs covered by a merged result
        if isinstance(covers, list) and len(covers) == 2:
            for s in range(int(covers[0]), int(covers[1])):
                self._inflight.pop(s, None)

        # Update no-reply timer: reset to oldest remaining inflight hop, or None if caught up
        if self._inflight:
            self._awaiting_since_perf = min(t_s for _, t_s, _ in self._inflight.values())
        else:
            self._awaiting_since_perf = None

        # Wake sender immediately if a pending latest hop was waiting for inflight headroom
        if self._latest_hop is not None and len(self._inflight) < self._max_inflight:
            self._hop_event.set()

        # If this hop already timed out and was dropped as stale, discard its late audio
        # (do NOT reset _consecutive_timeouts so 3 consecutive slow hops still fail over)
        if inflight is None and seq in self._timed_out_seqs:
            self._timed_out_seqs.discard(seq)
            self._hop_logger.log_drop(
                session_id="late",
                seq=seq,
                target_face_id=None,
                engine="B-GPU",
                hop_ms=self._hop_ms,
                t_capture=float(sent_ms) if sent_ms else None,
                age_ms=max(0.0, t_return_ms - float(sent_ms)) if sent_ms else 0.0,
                reason="late_reply_after_timeout",
                n_crops=0,
            )
            return

        # Healthy on-time reply resets consecutive timeout counter
        self._consecutive_timeouts = 0

        if inflight is not None:
            hop, t_send_perf, t_send_ms = inflight
            gpu_rtt_ms = max(0.0, (now_perf - t_send_perf) * 1000.0)
            t_capture = hop.t_capture if hop.t_capture > 0 else t_send_ms
            rtt_ms = max(gpu_rtt_ms, t_return_ms - t_capture)
            session_id = hop.session_id
            target_face_id = hop.target_face_id
            reset = hop.reset
            hop_ms = hop.hop_ms
            n_crops = len(hop.jpegs)
        else:
            gpu_rtt_ms = max(0.0, t_return_ms - float(sent_ms)) if sent_ms else gpu_ms
            t_capture = float(sent_ms) if sent_ms else None
            t_send_ms = float(sent_ms) if sent_ms else None
            rtt_ms = gpu_rtt_ms
            session_id = "unknown"
            target_face_id = None
            reset = False
            hop_ms = self._hop_ms
            n_crops = 0

        playback_buf_ms = float(self._playback_buf_ms_provider())
        rec = self._hop_logger.log_result(
            session_id=session_id,
            seq=seq,
            covers=[int(covers[0]), int(covers[1])],
            target_face_id=target_face_id,
            reset=reset,
            engine="B-GPU",
            hop_ms=hop_ms,
            t_capture=t_capture,
            t_send_ms=t_send_ms,
            t_return_ms=t_return_ms,
            gpu_ms=gpu_ms,
            queue_ms=queue_ms,
            gpu_rtt_ms=gpu_rtt_ms,
            rtt_ms=rtt_ms,
            playback_buf_ms=playback_buf_ms,
            samples=samples,
            n_crops=n_crops,
        )

        result = SeparationResult(
            session_id=session_id,
            seq=seq,
            covers=[int(covers[0]), int(covers[1])],
            samples=samples,
            pcm_bytes=clean_pcm,
            gpu_ms=gpu_ms,
            queue_ms=queue_ms,
            gpu_rtt_ms=gpu_rtt_ms,
            rtt_ms=rtt_ms,
            t_capture=t_capture,
            t_return=t_return_ms,
            sent_ms=float(sent_ms) if sent_ms is not None else None,
            engine="B-GPU",
            voice_delay_ms=rec["voice_delay_ms"],
        )

        if self._on_result is not None:
            await self._on_result(result)

    async def separate_batch_offline(
        self,
        hops: list[tuple[bytes, list[bytes], bool]],
        session_id: str = "replay",
        target_face_id: str | None = None,
    ) -> bytes:
        """Separate a short sequence of recorded hops (used by FB4 replay_last_10s)."""
        if not self._url or not self._token or not hops:
            return b""
        ws = await self._connect_ws()
        out = bytearray()
        try:
            for idx, (pcm_bytes, jpegs, reset) in enumerate(hops):
                hop = PendingHop(
                    session_id=session_id,
                    seq=idx,
                    target_face_id=target_face_id,
                    reset=(idx == 0 or reset),
                    pcm_bytes=pcm_bytes,
                    jpegs=jpegs,
                    t_capture=time.time() * 1000.0,
                    hop_ms=500,
                )
                await ws.send(_pack_binary_hop(hop, time.time() * 1000.0))
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                if isinstance(msg, bytes):
                    _, clean_pcm = _unpack_binary_result(msg)
                    out.extend(clean_pcm)
        finally:
            try:
                await ws.close()
            except Exception:
                pass
        return bytes(out)

    def status_dict(self) -> dict[str, Any]:
        return {
            "engine": self.active_engine,
            "reason": self.engine_reason,
            "gpu_connected": self._connected,
            "gpu_configured": bool(self._url and self._token),
            "hop_ms": self._hop_ms,
            "override": self._override_engine,
            "last_health": self._last_health,
        }
