"""Tag every session in logs/hops.jsonl as 'test' or 'live'.

S1's verify runs (verify-*, test-*, g7-*, eval-*, offline-*, bench-*, and system events
occurring during test runs) are tagged mode='test'. Real live runs are tagged mode='live'.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_PREFIXES = ("verify", "test", "g7", "eval", "offline", "bench", "sim", "dry")


def infer_session_mode(session_id: str | None) -> str:
    sid = (session_id or "").strip().lower()
    if not sid or sid == "system":
        return "test"
    if any(sid.startswith(p) for p in TEST_PREFIXES):
        return "test"
    return "live"


def tag_hops_file(path: Path, *, force: bool = False) -> dict[str, int]:
    if not path.exists():
        return {"total": 0, "live": 0, "test": 0}
    lines = path.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    counts: Counter[str] = Counter()

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        rec = json.loads(s)
        if force or rec.get("mode") not in ("live", "test"):
            rec["mode"] = infer_session_mode(rec.get("session_id"))
        counts[rec["mode"]] += 1
        out_lines.append(json.dumps(rec, ensure_ascii=False))

    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    tmp.replace(path)
    return {"total": len(out_lines), "live": counts["live"], "test": counts["test"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(REPO_ROOT / "logs/hops.jsonl"))
    ap.add_argument("--force", action="store_true", help="Re-infer mode even if already tagged")
    args = ap.parse_args()
    stats = tag_hops_file(Path(args.path), force=args.force)
    print(f"Tagged {args.path}: total={stats['total']} live={stats['live']} test={stats['test']}")


if __name__ == "__main__":
    main()
