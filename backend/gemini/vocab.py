"""Consent-gated custom vocabulary store (vocab.json) for Transcribe Live & Neon."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
VOCAB_PATH = REPO_ROOT / "vocab.json"
MAX_CUSTOM_VOCAB = 1000
_LOCK = threading.Lock()


def load_vocab(path: Path = VOCAB_PATH) -> dict[str, Any]:
    with _LOCK:
        if not path.exists():
            return {"terms": [], "consenting_speakers": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"terms": [], "consenting_speakers": {}}
            data.setdefault("terms", [])
            data.setdefault("consenting_speakers", {})
            return data
        except Exception:
            return {"terms": [], "consenting_speakers": {}}


def save_vocab(data: dict[str, Any], path: Path = VOCAB_PATH) -> None:
    with _LOCK:
        terms = [str(t).strip() for t in data.get("terms", []) if str(t).strip()]
        deduped = list(dict.fromkeys(terms))[:MAX_CUSTOM_VOCAB]
        payload = {
            "terms": deduped,
            "consenting_speakers": data.get("consenting_speakers", {}),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_vocab_terms(path: Path = VOCAB_PATH) -> list[str]:
    """Return deduplicated vocabulary terms (max 1,000 for gemini-3.5-transcribe-live)."""
    data = load_vocab(path)
    terms: list[str] = []
    for t in data.get("terms", []):
        s = str(t).strip()
        if s:
            terms.append(s)
    for name in (data.get("consenting_speakers") or {}).values():
        s = str(name).strip()
        if s:
            terms.append(s)
    return list(dict.fromkeys(terms))[:MAX_CUSTOM_VOCAB]


def register_consenting_speaker(
    face_id: str, name: str | None, *, consent_given: bool, path: Path = VOCAB_PATH
) -> bool:
    """Record a speaker's name in vocab.json ONLY if they have explicit consent."""
    if not consent_given or not name or not name.strip():
        return False
    clean_name = name.strip()
    data = load_vocab(path)
    speakers = dict(data.get("consenting_speakers") or {})
    speakers[str(face_id)] = clean_name
    terms = list(data.get("terms") or [])
    if clean_name not in terms:
        terms.append(clean_name)
    data["consenting_speakers"] = speakers
    data["terms"] = terms
    save_vocab(data, path)
    return True


def remove_speaker_vocab(face_id: str, path: Path = VOCAB_PATH) -> None:
    """Remove a speaker's name from vocab.json if consent is revoked."""
    data = load_vocab(path)
    speakers = dict(data.get("consenting_speakers") or {})
    removed = speakers.pop(str(face_id), None)
    if removed is not None:
        data["consenting_speakers"] = speakers
        remaining_names = set(speakers.values())
        if removed not in remaining_names:
            data["terms"] = [t for t in data.get("terms", []) if t != removed]
        save_vocab(data, path)
