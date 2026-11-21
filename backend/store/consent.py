"""Consent record store.

Enforces AGENTS.md privacy rule:
Never save, send or log audio or text of a person without a consent record.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONSENT_PATH = REPO_ROOT / "clips" / "consent.json"


class ConsentStore:
    """Thread-safe face consent registry persisted to clips/consent.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CONSENT_PATH
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._records = data
        except Exception:
            self._records = {}

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._records, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def set_consent(
        self,
        face_id: str,
        *,
        given: bool,
        by: str | None = None,
        consent_time: str | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        if not face_id:
            raise ValueError("face_id is required")
        ts = consent_time or (datetime.now(timezone.utc).isoformat() if given else None)
        rec = {
            "face_id": face_id,
            "given": bool(given),
            "by": by if given else None,
            "time": ts if given else None,
            "label": label,
        }
        with self._lock:
            self._records[face_id] = rec
            self._save_locked()
        return dict(rec)

    def sync_from_faces(self, faces: list[dict[str, Any]]) -> None:
        """Merge face consent flags reported by the browser (never downgrading a saved consent silently)."""
        if not faces:
            return
        changed = False
        with self._lock:
            for f in faces:
                fid = f.get("id")
                consent = f.get("consent")
                if not fid or not isinstance(consent, dict):
                    continue
                given = bool(consent.get("given", False))
                existing = self._records.get(fid)
                if existing is None or existing.get("given") != given or f.get("label") != existing.get("label"):
                    self._records[fid] = {
                        "face_id": fid,
                        "given": given,
                        "by": consent.get("by") if given else None,
                        "time": consent.get("time") if given else None,
                        "label": f.get("label"),
                    }
                    changed = True
            if changed:
                self._save_locked()

    def has_consent(self, face_id: str | None) -> bool:
        if not face_id:
            return False
        with self._lock:
            rec = self._records.get(face_id)
            return bool(rec and rec.get("given") is True)

    def missing_consent(self, face_ids: list[str]) -> list[str]:
        with self._lock:
            return [fid for fid in face_ids if not (self._records.get(fid, {}).get("given") is True)]

    def get(self, face_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._records.get(face_id)
            return dict(rec) if rec else None

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._records.items()}
