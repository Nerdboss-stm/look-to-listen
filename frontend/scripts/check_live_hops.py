#!/usr/bin/env python3
"""Check n_crops == 12 or 13 share in logs/hops.jsonl for a 60 s run."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HOPS_PATH = Path(__file__).resolve().parents[2] / "logs" / "hops.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="", help="Specific session_id (defaults to newest browser session)")
    ap.add_argument("--min-hops", type=int, default=100, help="Minimum hop records expected for ~60 s")
    args = ap.parse_args()

    if not HOPS_PATH.exists():
        print("logs/hops.jsonl does not exist", file=sys.stderr)
        return 1

    by_session: dict[str, list[dict]] = {}
    for line in HOPS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = str(rec.get("session_id") or "")
        if not sid or rec.get("status") not in ("ok", "dropped_stale"):
            continue
        by_session.setdefault(sid, []).append(rec)

    target_sid = args.session
    if not target_sid:
        sess_ids = [s for s in by_session.keys() if s.startswith("sess-")]
        if not sess_ids:
            print("No sess-* sessions found in logs/hops.jsonl", file=sys.stderr)
            return 1
        target_sid = sess_ids[-1]

    rows = by_session.get(target_sid, [])
    if not rows:
        print(f"No hop records found for session {target_sid}", file=sys.stderr)
        return 1

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    crop_hist = Counter(r.get("n_crops") for r in ok_rows)
    face_ids = Counter(r.get("target_face_id") for r in ok_rows)
    good = sum(1 for r in ok_rows if r.get("n_crops") in (12, 13))
    total = len(ok_rows)
    pct = (100.0 * good / total) if total else 0.0

    print(f"Session:        {target_sid}")
    print(f"OK hops:        {total} (all records: {len(rows)})")
    print(f"n_crops 12|13:  {good}/{total} ({pct:.1f}%)")
    print(f"n_crops hist:   {dict(sorted((k if k is not None else -1, v) for k, v in crop_hist.items()))}")
    print(f"target_face_id: {dict(face_ids)}")

    if total < args.min_hops:
        print(f"FAIL: expected >= {args.min_hops} hops for a 60 s run, got {total}")
        return 1
    if pct < 95.0:
        print(f"FAIL: {pct:.1f}% < 95.0% gate")
        return 1
    print("VERDICT: PASS (>= 95% of hops have n_crops 12 or 13)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
