#!/usr/bin/env python3
"""Validate all JSON schemas and sample payloads in contracts/."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

CONTRACTS_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = CONTRACTS_DIR / "samples"

SCHEMA_NAMES = [
    "face",
    "hop",
    "hop_result",
    "segment",
    "decision",
    "config",
    "command",
    "memory_answer",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    schemas = {}
    resources = []
    for name in SCHEMA_NAMES:
        schema_path = CONTRACTS_DIR / f"{name}.schema.json"
        schema = load_json(schema_path)
        Draft202012Validator.check_schema(schema)
        schemas[name] = schema
        res = Resource.from_contents(schema)
        resources.append((schema["$id"], res))
        resources.append((f"{name}.schema.json", res))

    registry = Registry().with_resources(resources)

    passed = 0
    for name in SCHEMA_NAMES:
        validator = Draft202012Validator(schemas[name], registry=registry)
        sample_path = SAMPLES_DIR / f"{name}.sample.json"
        sample = load_json(sample_path)
        validator.validate(sample)
        print(f"PASS  {name}.schema.json <- samples/{name}.sample.json")
        passed += 1

    # Verify minimal hop (exact SPEC/separator_server.py JSON shape) validates too
    minimal_hop = {
        "session_id": "s1",
        "seq": 0,
        "target_face_id": "face-1",
        "reset": True,
        "pcm": "AAAAAA==",
        "crops": [],
        "t_capture": 1795192200000,
    }
    Draft202012Validator(schemas["hop"], registry=registry).validate(minimal_hop)
    print("PASS  hop.schema.json <- minimal SPEC hop")
    passed += 1

    # Negative checks: ensure invalid payloads fail
    negatives = [
        ("face", {"id": "face-1"}),
        ("hop", {"session_id": "s1", "seq": -1, "target_face_id": None, "reset": False, "pcm": "", "crops": [], "t_capture": 0}),
        ("segment", {"t0": 0, "t1": 1, "lane": "bad_lane", "face_id": None, "text": "hi", "confidence": 0.5, "engine": "B-GPU"}),
        ("decision", {"face_id": "face-1", "window_t0": 0, "window_t1": 1, "p_speaking": 1.5, "latency_ms": 10}),
        ("command", {"command_id": "c1", "face_id": "f1", "text": "go", "target_face_id": "f1", "point": [1200, 10], "object_label": "cup"}),
    ]
    for name, bad in negatives:
        validator = Draft202012Validator(schemas[name], registry=registry)
        try:
            validator.validate(bad)
            print(f"FAIL  negative test for {name} unexpectedly passed!", file=sys.stderr)
            return 1
        except ValidationError:
            print(f"PASS  {name}.schema.json rejected invalid payload")
            passed += 1

    # Verify eval.md exists and is non-empty
    eval_md = CONTRACTS_DIR / "eval.md"
    assert eval_md.exists() and eval_md.stat().st_size > 500, "contracts/eval.md missing or too short"
    print(f"PASS  eval.md present ({eval_md.stat().st_size} bytes)")
    passed += 1

    print(f"\nAll {passed} contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
