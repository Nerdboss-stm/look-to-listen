"""Argon memory store & QA/summary (gemini-4-argon) with FB7 Neon fallback (E22 / AT10).

Enforces privacy: only lines from consenting faces carry speaker names or clip paths.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from google.genai import types

from backend.gemini.client import MODELS, extract_usage, get_client
from backend.gemini.logger import log_model_call
from backend.gemini.neon import neon_memory_fallback_sync

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_json_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    s = raw.strip()
    m = _JSON_BLOCK_RE.search(s)
    if m:
        s = m.group(1)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


class ConversationMemory:
    """In-memory conversation log for Argon Q&A, summary, and consent-checked transcript export."""

    def __init__(self, *, max_entries: int = 2000) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._max_entries = max_entries
        self._started_ms = time.time() * 1000.0
        self.conversation_id = f"conv-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._started_ms = time.time() * 1000.0
            self.conversation_id = f"conv-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    def append_segment(
        self,
        *,
        t0: float,
        t1: float,
        lane: str,
        face_id: str | None,
        text: str,
        consent_given: bool = False,
        speaker_label: str | None = None,
        clip: str | None = None,
    ) -> dict[str, Any]:
        clean = (text or "").strip()
        if not clean:
            return {}
        rel_s = max(0.0, (t0 - self._started_ms) / 1000.0) if t0 > 1e11 else max(0.0, t0)
        mm, ss = divmod(int(rel_s), 60)
        hh, mm = divmod(mm, 60)
        rel_str = f"{hh:02d}:{mm:02d}:{ss:02d}"
        entry = {
            "t0": round(float(t0), 1),
            "t1": round(float(t1), 1),
            "rel_s": round(rel_s, 1),
            "time": rel_str,
            "lane": lane,
            "face_id": face_id,
            "speaker": speaker_label if consent_given else (face_id or "unknown"),
            "consent_given": bool(consent_given),
            "text": clean,
            "clip": clip if consent_given else None,
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                del self._entries[: len(self._entries) - self._max_entries]
        return entry

    def snapshot(self, *, consenting_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            if consenting_only:
                return [dict(e) for e in self._entries if e.get("consent_given")]
            return [dict(e) for e in self._entries]

    def ask_sync(
        self,
        question: str,
        *,
        use_fb7: bool | None = None,
        purpose: str = "argon_memory_qa",
    ) -> dict[str, Any]:
        """Answer a memory question over the conversation using gemini-4-argon (FB7 Neon fallback)."""
        force_fb7 = (
            bool(use_fb7)
            if use_fb7 is not None
            else os.getenv("FALLBACK_FB7_NEON", "0") == "1"
        )
        # Only expose consenting lines to Argon/Neon memory answers
        entries = self.snapshot(consenting_only=True)
        if not entries:
            # If no faces have been marked consented yet, explain clearly instead of leaking unconsented speech
            all_n = len(self.snapshot(consenting_only=False))
            msg = (
                "No consented speech is stored yet. Grant consent for a speaker to enable memory answers."
                if all_n > 0
                else "No conversation recorded yet."
            )
            return {
                "question": question,
                "answer": msg,
                "time": None,
                "clip": None,
                "confidence": 0.0,
                "source": "neon-transcript-only" if force_fb7 else "argon",
                "latency_ms": 0.0,
                "face_id": None,
            }

        if force_fb7:
            return neon_memory_fallback_sync(question, entries, purpose=f"{purpose}_fb7")

        client = get_client(timeout_ms=10000)
        payload = {
            "question": question,
            "instructions": (
                "You are the conversation memory for Look to Listen. "
                "Answer the question strictly using the timestamped conversation entries below. "
                "Return JSON only with keys: "
                "answer (concise, grounded string), "
                "time (the exact 'time' string like '00:02:14' of the matching moment, or null), "
                "clip (the exact 'clip' string from that entry, or null), "
                "face_id (the matching 'face_id', or null), "
                "confidence (float 0.0 to 1.0). "
                "Never fabricate facts or timestamps."
            ),
            "conversation": entries,
        }
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=MODELS.argon,
                contents=json.dumps(payload, ensure_ascii=False),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                ),
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            in_tok, out_tok = extract_usage(resp)
            parsed = _parse_json_obj(resp.text)
            log_model_call(
                model=MODELS.argon,
                thinking_level="LOW",
                latency_ms=latency_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                purpose=purpose,
                ok=True,
                extra={"entries": len(entries)},
            )
            return {
                "question": question,
                "answer": str(parsed.get("answer") or "No matching moment found."),
                "time": parsed.get("time"),
                "clip": parsed.get("clip"),
                "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
                "source": "argon",
                "latency_ms": round(latency_ms, 1),
                "face_id": parsed.get("face_id"),
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            log_model_call(
                model=MODELS.argon,
                thinking_level="LOW",
                latency_ms=latency_ms,
                purpose=purpose,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            # FB7 automatic fallback to Neon
            return neon_memory_fallback_sync(question, entries, purpose=f"{purpose}_fb7_auto")

    async def ask(self, question: str, *, timeout_s: float = 6.5) -> dict[str, Any]:
        """Async memory QA with timeout fallback to Neon (AT10 target <= 8 s)."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.ask_sync, question),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            entries = self.snapshot(consenting_only=True)
            return await asyncio.to_thread(
                neon_memory_fallback_sync, question, entries, purpose="argon_timeout_fb7"
            )

    def summarize_sync(self) -> dict[str, Any]:
        """Generate a concise summary of consenting speakers' lines via Argon."""
        return self.ask_sync(
            "Summarize the key points discussed in this conversation by speaker, with timestamps.",
            purpose="argon_summary",
        )
