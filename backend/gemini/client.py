"""Gemini API client factory, env loader, and confirmed model ID registry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_LOADED = False


def ensure_env_loaded() -> None:
    """Load .env from repo root without ever printing secret values."""
    global _ENV_LOADED
    if not _ENV_LOADED:
        load_dotenv(REPO_ROOT / ".env", override=False)
        _ENV_LOADED = True


def get_api_key(use_backup: bool = False) -> str:
    """Return GEMINI_API_KEY (or GEMINI_API_KEY_BACKUP) from env/.env."""
    ensure_env_loaded()
    key = os.getenv("GEMINI_API_KEY_BACKUP") if use_backup else os.getenv("GEMINI_API_KEY")
    if not key and use_backup:
        key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env or environment")
    return key


def get_client(
    *,
    api_version: str | None = None,
    use_backup: bool = False,
    timeout_ms: int | None = None,
) -> genai.Client:
    """Build a google.genai.Client using the configured API key."""
    key = get_api_key(use_backup=use_backup)
    http_options: dict[str, Any] = {}
    if api_version:
        http_options["api_version"] = api_version
    if timeout_ms is not None:
        http_options["timeout"] = int(timeout_ms)
    if http_options:
        return genai.Client(api_key=key, http_options=http_options)
    return genai.Client(api_key=key)


@dataclass
class ModelIds:
    """Confirmed model IDs discovered at event start (E3 discovery)."""

    transcribe_live: str = os.getenv("MODEL_TRANSCRIBE_LIVE", "gemini-3.5-transcribe-live")
    hydrogen_live: str = os.getenv("MODEL_HYDROGEN_LIVE", "gemini-4-hydrogen-live")
    hydrogen: str = os.getenv("MODEL_HYDROGEN", "gemini-4-hydrogen")
    decision: str = os.getenv("MODEL_DECISION", "gemini-decision-1")
    robotics_er: str = os.getenv("MODEL_ROBOTICS_ER", "gemini-robotics-er-2-preview")
    neon: str = os.getenv("MODEL_NEON", "gemini-4-neon")
    argon: str = os.getenv("MODEL_ARGON", "gemini-4-argon")


MODELS = ModelIds()


def extract_usage(response: Any) -> tuple[int | None, int | None]:
    """Safely extract (input_tokens, output_tokens) from a google-genai response."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None
    in_tok = getattr(usage, "prompt_token_count", None)
    out_tok = getattr(usage, "candidates_token_count", None)
    if out_tok is None:
        total = getattr(usage, "total_token_count", None)
        if total is not None and in_tok is not None:
            out_tok = max(0, total - in_tok)
    return in_tok, out_tok
