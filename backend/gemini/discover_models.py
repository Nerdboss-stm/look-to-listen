"""Discover exact Gemini 4 model IDs and inspect google-genai 3.x API surfaces."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from google import genai
from google.genai import types

from backend.gemini.client import get_client


def main() -> None:
    print("google-genai version:", genai.__version__)
    client = get_client()
    print("\n--- Client public attributes ---")
    print([a for a in dir(client) if not a.startswith("_")])
    print("\n--- Async client public attributes ---")
    print([a for a in dir(client.aio) if not a.startswith("_")])

    # Inspect Decisions / Live / Agents / Interactions types
    interesting = [
        name
        for name in dir(types)
        if any(
            k in name.lower()
            for k in ("decision", "live", "think", "transcri", "agent", "interact", "audio")
        )
    ]
    print("\n--- Interesting types ---")
    print(interesting[:120])

    # Check if client has decisions / interactions / agents
    for attr in ("decisions", "interactions", "agents", "live", "models"):
        obj = getattr(client, attr, None)
        if obj is not None:
            print(f"\nclient.{attr}: {[m for m in dir(obj) if not m.startswith('_')]}")
        aobj = getattr(client.aio, attr, None)
        if aobj is not None:
            print(f"client.aio.{attr}: {[m for m in dir(aobj) if not m.startswith('_')]}")

    for ver in (None, "v1alpha"):
        print(f"\n=== Models (api_version={ver or 'default'}) ===")
        try:
            c = get_client(api_version=ver)
            for m in c.models.list():
                name = getattr(m, "name", "")
                if any(
                    k in name.lower()
                    for k in ("gemini-4", "hydrogen", "neon", "argon", "decision", "live", "2.5", "3.")
                ):
                    actions = getattr(m, "supported_actions", None)
                    print(f"  {name} | display={getattr(m, 'display_name', '')} | actions={actions}")
        except Exception as exc:
            print(f"  Error listing models ({ver}): {exc}")


if __name__ == "__main__":
    main()
