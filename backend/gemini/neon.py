"""Neon brain (gemini-4-neon): segment merging, speaker attribution, vocab.json, translation (E18).

Also provides FB7 transcript-only memory fallback if Argon is slow or unavailable.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from google.genai import types

from backend.gemini.client import MODELS, extract_usage, get_client
from backend.gemini.logger import log_model_call
from backend.gemini.vocab import get_vocab_terms

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", re.DOTALL)


def _extract_json(raw: str | None) -> Any:
    if not raw:
        return None
    s = raw.strip()
    m = _JSON_BLOCK_RE.search(s)
    if m:
        s = m.group(1)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def attribute_and_polish_sync(
    segments: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    faces: list[dict[str, Any]],
    *,
    translate_to: str | None = None,
    vocab: list[str] | None = None,
    purpose: str = "neon_attribute",
) -> list[dict[str, Any]]:
    """Use gemini-4-neon to merge, fix consenting names from vocab.json, attribute to face_id, and optionally translate."""
    if not segments:
        return []

    terms = vocab if vocab is not None else get_vocab_terms()
    # Only include consenting speaker labels
    face_summary = [
        {
            "face_id": f.get("id"),
            "color": f.get("color"),
            "consent_given": bool((f.get("consent") or {}).get("given", False)),
            "label": (
                (f.get("consent") or {}).get("by") or f.get("label")
                if bool((f.get("consent") or {}).get("given", False))
                else None
            ),
        }
        for f in faces
        if isinstance(f, dict) and f.get("id")
    ]

    prompt_obj = {
        "task": "Merge fragmented caption segments, fix spelling of known consenting vocabulary terms if clearly spoken, and attribute each segment to the face_id that spoke it using the calibrated speaking_decisions timeline.",
        "rules": [
            "Only attribute to face_ids present in faces.",
            "Use speaking_decisions (p_speaking in [window_t0, window_t1]) as primary evidence for who spoke.",
            "Never invent words that were not spoken.",
            "Return ONLY a JSON array of objects with keys: segment_id, face_id, text, confidence, translated_text (null if translate_to is null).",
        ],
        "translate_to": translate_to,
        "vocab_terms": terms[:200],
        "faces": face_summary,
        "speaking_decisions": decisions[-40:],
        "segments": [
            {
                "segment_id": s.get("segment_id"),
                "t0": s.get("t0"),
                "t1": s.get("t1"),
                "lane": s.get("lane"),
                "face_id": s.get("face_id"),
                "text": s.get("text"),
            }
            for s in segments
        ],
    }

    client = get_client(timeout_ms=25000)
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=MODELS.neon,
            contents=json.dumps(prompt_obj, ensure_ascii=False),
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        in_tok, out_tok = extract_usage(resp)
        parsed = _extract_json(resp.text)
        log_model_call(
            model=MODELS.neon,
            thinking_level="LOW",
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            purpose=purpose,
            ok=isinstance(parsed, list),
            extra={"segments_in": len(segments), "translate_to": translate_to},
        )
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        err_s = f"{type(exc).__name__}: {exc}"
        is_deadline = "504" in err_s or "DEADLINE_EXCEEDED" in err_s or "Timeout" in err_s
        log_model_call(
            model=MODELS.neon,
            thinking_level="LOW",
            latency_ms=latency_ms,
            purpose=f"{purpose}_skipped" if is_deadline else purpose,
            ok=False,
            error=err_s,
            extra={"skipped_turn": is_deadline},
        )
    return []


def neon_memory_fallback_sync(
    question: str,
    transcript_entries: list[dict[str, Any]],
    *,
    purpose: str = "fb7_neon_memory",
) -> dict[str, Any]:
    """FB7 fallback: answer memory question from transcript using gemini-4-neon (source='neon-transcript-only')."""
    client = get_client(timeout_ms=10000)
    payload = {
        "question": question,
        "instructions": (
            "Answer the question strictly from the provided conversation transcript. "
            "Return JSON only with keys: answer (string), time (string timestamp or null), "
            "clip (string clip id or null), face_id (string or null), confidence (float 0..1). "
            "If the answer is not in the transcript, say so and set confidence <= 0.2."
        ),
        "transcript": transcript_entries[-300:],
    }
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=MODELS.neon,
            contents=json.dumps(payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            ),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        in_tok, out_tok = extract_usage(resp)
        parsed = _extract_json(resp.text) or {}
        log_model_call(
            model=MODELS.neon,
            thinking_level="LOW",
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            purpose=purpose,
            ok=True,
        )
        return {
            "question": question,
            "answer": str(parsed.get("answer") or "No matching moment found in transcript."),
            "time": parsed.get("time"),
            "clip": parsed.get("clip"),
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            "source": "neon-transcript-only",
            "latency_ms": round(latency_ms, 1),
            "face_id": parsed.get("face_id"),
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        log_model_call(
            model=MODELS.neon,
            thinking_level="LOW",
            latency_ms=latency_ms,
            purpose=purpose,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        return {
            "question": question,
            "answer": "Memory lookup unavailable right now.",
            "time": None,
            "clip": None,
            "confidence": 0.0,
            "source": "neon-transcript-only",
            "latency_ms": round(latency_ms, 1),
            "face_id": None,
        }
