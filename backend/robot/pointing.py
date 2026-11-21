"""Robot R1 pointing using gemini-robotics-er-2-preview (v1beta) with gemini-4-hydrogen fallback.

Implements SPEC Robot R1, prompts.md G6, and FB9 fallback.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from google.genai import types

from backend.gemini.client import MODELS, extract_usage, get_client
from backend.gemini.logger import log_model_call

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def build_pointing_prompt(command: str) -> str:
    return (
        f'A person asked: "{command}". Point to the one object they want. '
        'Return JSON only: [{"label": "<object>", "point": [y, x]}] '
        "with y and x normalized to 0 to 1000. If no object fits, return []."
    )


def parse_pointing_json(raw_text: str | None) -> tuple[str | None, list[float] | None]:
    """Parse [{"label": "...", "point": [y, x]}] into (label, [y, x]) clamped to [0, 1000]."""
    if not raw_text:
        return None, None
    s = raw_text.strip()
    m = _JSON_BLOCK_RE.search(s)
    candidate = m.group(1) if m else s
    if not candidate.startswith("["):
        m2 = _JSON_ARRAY_RE.search(candidate)
        if m2:
            candidate = m2.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None, None
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed:
        return None, None
    first = parsed[0]
    if not isinstance(first, dict):
        return None, None
    pt = first.get("point")
    label = first.get("label")
    if isinstance(pt, (list, tuple)) and len(pt) == 2:
        try:
            y = max(0.0, min(1000.0, float(pt[0])))
            x = max(0.0, min(1000.0, float(pt[1])))
            return (str(label).strip() if label else None), [round(y, 1), round(x, 1)]
        except (TypeError, ValueError):
            pass
    return (str(label).strip() if label else None), None


def point_at_object_sync(
    image_bytes: bytes,
    command: str,
    *,
    model: str | None = None,
    mime_type: str = "image/jpeg",
    allow_fallback: bool = True,
    purpose: str = "robot_pointing",
) -> dict[str, Any]:
    """Call gemini-robotics-er-2-preview (v1beta), falling back to gemini-4-hydrogen on error."""
    primary_model = model or MODELS.robotics_er
    candidates: list[tuple[str, str | None]] = [
        (primary_model, "v1beta" if "robotics" in primary_model else None)
    ]
    if allow_fallback and primary_model != MODELS.hydrogen:
        candidates.append((MODELS.hydrogen, None))

    prompt = build_pointing_prompt(command)
    last_error: str | None = None

    # Downscale very large images to <= 960px wide for fast, reliable pointing latency
    send_bytes = image_bytes
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        im = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if im is not None and max(im.shape[:2]) > 960:
            scale = 960.0 / float(max(im.shape[:2]))
            resized = cv2.resize(im, (int(im.shape[1] * scale), int(im.shape[0] * scale)))
            ok_enc, enc = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok_enc:
                send_bytes = enc.tobytes()
                mime_type = "image/jpeg"
    except Exception:
        pass

    for m_id, api_ver in candidates:
        client = get_client(api_version=api_ver)
        cfg_kwargs: dict[str, Any] = {"temperature": 0.0}
        thinking_label: str | None = None
        if "hydrogen" in m_id:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW
            )
            thinking_label = "LOW"
        elif "robotics" in m_id:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            thinking_label = "budget=0"
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=m_id,
                contents=[
                    types.Part.from_bytes(data=send_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            in_tok, out_tok = extract_usage(resp)
            label, point = parse_pointing_json(resp.text)
            log_model_call(
                model=m_id,
                thinking_level=thinking_label,
                latency_ms=latency_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                purpose=purpose,
                ok=True,
                extra={"label": label, "point": point},
            )
            return {
                "ok": True,
                "model": m_id,
                "object_label": label,
                "point": point,
                "latency_ms": round(latency_ms, 2),
                "raw_text": (resp.text or "").strip(),
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            err_str = f"{type(exc).__name__}: {exc}"
            last_error = err_str
            # Surface helpful hint if Robotics ER returns 403 (unrestricted key)
            hint = " (API key may need restrictions in AI Studio)" if "403" in err_str else ""
            log_model_call(
                model=m_id,
                thinking_level="LOW",
                latency_ms=latency_ms,
                purpose=purpose,
                ok=False,
                error=err_str + hint,
            )
            if not allow_fallback:
                break

    # FB9 fallback: return attribution without pointing coordinates
    return {
        "ok": False,
        "model": primary_model,
        "object_label": None,
        "point": None,
        "latency_ms": 0.0,
        "error": last_error or "pointing_failed",
    }
