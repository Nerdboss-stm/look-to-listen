"""Consent-enforced clip store for clips/.

Enforces AGENTS.md rule:
Never save, send or log audio or text of a person without a consent record.
The backend enforces it for clips/.
"""

from __future__ import annotations

import json
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.store.consent import ConsentStore

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIPS_DIR = REPO_ROOT / "clips"
AGENT_LOG_PATH = REPO_ROOT / "logs" / "agent.jsonl"
SR = 16000


class ConsentDeniedError(PermissionError):
    """Raised whenever saving or recording audio is attempted without consent."""

    def __init__(self, missing_faces: list[str], message: str | None = None) -> None:
        self.missing_faces = missing_faces
        msg = message or f"Consent required before saving clip; missing consent for: {', '.join(missing_faces)}"
        super().__init__(msg)


def _append_privacy_event(decision: str, reason: str, details: dict[str, Any]) -> None:
    AGENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event_type": "hook",
        "hook": "gate_privacy",
        "tool": "clip_store",
        "decision": decision,
        "reason": reason,
        "summary": reason,
        "details": details,
    }
    try:
        with AGENT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _write_wav16(path: Path, pcm_bytes: bytes, sample_rate: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


class ClipStore:
    """Manages consent-gated live clip recording and clip metadata under clips/."""

    def __init__(self, consent_store: ConsentStore, clips_dir: Path | None = None) -> None:
        self.consent = consent_store
        self.clips_dir = clips_dir or CLIPS_DIR
        self._lock = threading.Lock()
        self._active_clip_id: str | None = None
        self._active_faces: list[str] = []
        self._active_meta: dict[str, Any] = {}
        self._raw_pcm = bytearray()
        self._clean_pcm = bytearray()
        self._started_at: float = 0.0

    def _require_consent(self, face_ids: list[str], context: str) -> None:
        unique_faces = [f for f in dict.fromkeys(face_ids) if f]
        if not unique_faces:
            reason = f"Refused to {context}: no consenting faces identified."
            _append_privacy_event("DENY", reason, {"context": context, "missing_faces": []})
            raise ConsentDeniedError([], reason)
        missing = self.consent.missing_consent(unique_faces)
        if missing:
            reason = f"Refused to {context}: missing consent for {', '.join(missing)}."
            _append_privacy_event("DENY", reason, {"context": context, "missing_faces": missing})
            raise ConsentDeniedError(missing, reason)

    def start_recording(
        self,
        *,
        clip_id: str | None = None,
        face_ids: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Begin recording a live clip only if all listed faces have consent."""
        self._require_consent(face_ids, "start clip recording")
        cid = clip_id or f"clip-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        with self._lock:
            self._active_clip_id = cid
            self._active_faces = list(dict.fromkeys(face_ids))
            self._active_meta = dict(metadata or {})
            self._raw_pcm = bytearray()
            self._clean_pcm = bytearray()
            self._started_at = time.time()
        return {"clip_id": cid, "recording": True, "face_ids": list(self._active_faces)}

    def append_live_audio(
        self,
        *,
        raw_pcm: bytes | None = None,
        clean_pcm: bytes | None = None,
        visible_face_ids: list[str] | None = None,
    ) -> None:
        """Append audio while recording. Immediately aborts and discards if a non-consenting face appears."""
        with self._lock:
            if not self._active_clip_id:
                return
            if visible_face_ids:
                missing = self.consent.missing_consent(visible_face_ids)
                if missing:
                    cid = self._active_clip_id
                    self._active_clip_id = None
                    self._raw_pcm.clear()
                    self._clean_pcm.clear()
                    _append_privacy_event(
                        "DENY",
                        f"Aborted clip {cid}: non-consenting face entered frame ({', '.join(missing)}).",
                        {"clip_id": cid, "missing_faces": missing},
                    )
                    return
                for fid in visible_face_ids:
                    if fid not in self._active_faces:
                        self._active_faces.append(fid)
            if raw_pcm:
                self._raw_pcm.extend(raw_pcm)
            if clean_pcm:
                self._clean_pcm.extend(clean_pcm)

    def stop_recording(self) -> dict[str, Any]:
        """Finalize and persist the clip WAVs + metadata JSON if consent still holds."""
        with self._lock:
            cid = self._active_clip_id
            faces = list(self._active_faces)
            meta = dict(self._active_meta)
            raw_bytes = bytes(self._raw_pcm)
            clean_bytes = bytes(self._clean_pcm)
            started = self._started_at
            self._active_clip_id = None
            self._active_faces = []
            self._active_meta = {}
            self._raw_pcm.clear()
            self._clean_pcm.clear()

        if not cid:
            return {"saved": False, "reason": "no_active_recording"}

        return self.save_clip(
            clip_id=cid,
            face_ids=faces,
            raw_pcm=raw_bytes,
            clean_pcm=clean_bytes,
            metadata={**meta, "started_at": started},
        )

    def save_clip(
        self,
        *,
        clip_id: str,
        face_ids: list[str],
        raw_pcm: bytes,
        clean_pcm: bytes = b"",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a consenting clip to clips/."""
        self._require_consent(face_ids, f"save clip {clip_id}")
        safe_id = "".join(c for c in clip_id if c.isalnum() or c in ("-", "_"))
        if not safe_id:
            raise ValueError("Invalid clip_id")

        self.clips_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.clips_dir / f"{safe_id}_raw.wav"
        _write_wav16(raw_path, raw_pcm, SR)

        clean_rel: str | None = None
        if clean_pcm:
            clean_path = self.clips_dir / f"{safe_id}_clean.wav"
            _write_wav16(clean_path, clean_pcm, SR)
            clean_rel = clean_path.name

        duration_s = round(len(raw_pcm) / (2 * SR), 2)
        consent_snapshot = {fid: self.consent.get(fid) for fid in face_ids}
        record = {
            "clip_id": safe_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": duration_s,
            "face_ids": list(dict.fromkeys(face_ids)),
            "consent": consent_snapshot,
            "raw_wav": raw_path.name,
            "clean_wav": clean_rel,
            "metadata": metadata or {},
        }
        meta_path = self.clips_dir / f"{safe_id}.json"
        meta_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"saved": True, **record}

    def list_clips(self) -> list[dict[str, Any]]:
        if not self.clips_dir.exists():
            return []
        out: list[dict[str, Any]] = []
        for p in sorted(self.clips_dir.glob("*.json")):
            if p.name == "consent.json":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("clip_id"):
                    out.append(data)
            except Exception:
                continue
        return out

    def resolve_clip_file(self, filename: str) -> Path | None:
        """Return a safe path inside clips/ only for files belonging to consenting clips."""
        if "/" in filename or "\\" in filename or filename in ("consent.json", ".", ".."):
            return None
        path = (self.clips_dir / filename).resolve()
        try:
            path.relative_to(self.clips_dir.resolve())
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path

    @property
    def is_recording(self) -> bool:
        return self._active_clip_id is not None
