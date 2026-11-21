"""Compute all Look to Listen evaluation metrics, END CARD summary JSON, and SVG charts.

Reads only real logged files: clips.csv, decisions.csv, robot.csv, logs/hops.jsonl, gate_log.csv.
Writes:
  - evals/summary.json (for the END CARD UI and gate_release.py)
  - evals/charts/calibration.svg (Set D reliability diagram)
  - evals/charts/arms_comparison.svg (B0 vs Engine A vs Engine B-GPU)
  - evals/charts/where_it_breaks.svg (Set C slices by condition)
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics import (
    score_clips_csv,
    score_decisions_csv,
    score_robot_csv,
    summarize_voice_delay,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def read_gate_log(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def render_calibration_svg(set_d: dict[str, Any], out_path: Path) -> None:
    w, h = 560, 420
    pad_l, pad_r, pad_t, pad_b = 70, 30, 55, 65
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

    def sx(v: float) -> float:
        return pad_l + v * pw

    def sy(v: float) -> float:
        return pad_t + (1.0 - v) * ph

    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#0f172a" rx="12"/>',
        f'<text x="{w/2}" y="30" fill="#f8fafc" font-family="system-ui,sans-serif" font-size="18" font-weight="700" text-anchor="middle">Decision 1 Calibration (Set D, n={set_d["n"]})</text>',
    ]
    # Grid & axes
    for i in range(6):
        v = i * 0.2
        x, y = sx(v), sy(v)
        elems.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="#1e293b" stroke-width="1"/>')
        elems.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{h-pad_b}" stroke="#1e293b" stroke-width="1"/>')
        elems.append(f'<text x="{pad_l-10}" y="{y+4:.1f}" fill="#94a3b8" font-family="system-ui,sans-serif" font-size="12" text-anchor="end">{v:.1f}</text>')
        elems.append(f'<text x="{x:.1f}" y="{h-pad_b+20}" fill="#94a3b8" font-family="system-ui,sans-serif" font-size="12" text-anchor="middle">{v:.1f}</text>')

    # Perfect calibration diagonal
    elems.append(f'<line x1="{sx(0):.1f}" y1="{sy(0):.1f}" x2="{sx(1):.1f}" y2="{sy(1):.1f}" stroke="#64748b" stroke-dasharray="6,4" stroke-width="2"/>')

    pts: list[tuple[float, float, int]] = []
    for b in set_d.get("bins", []):
        if b["count"] > 0 and b["mean_p"] is not None and b["empirical_rate"] is not None:
            pts.append((sx(b["mean_p"]), sy(b["empirical_rate"]), b["count"]))

    if pts:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        elems.append(f'<polyline points="{poly}" fill="none" stroke="#38bdf8" stroke-width="3"/>')
        for x, y, cnt in pts:
            r = min(10, 4 + cnt * 0.15)
            elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#38bdf8" stroke="#0f172a" stroke-width="2"/>')
    else:
        elems.append(f'<text x="{w/2}" y="{h/2}" fill="#94a3b8" font-family="system-ui,sans-serif" font-size="15" text-anchor="middle">No Set D labeled windows yet</text>')

    ece_str = f"ECE={set_d['ece']:.3f}" if set_d.get("ece") is not None else "ECE=n/a"
    acc_str = f"Acc@0.9={set_d['accuracy']*100:.1f}%" if set_d.get("accuracy") is not None else "Acc@0.9=n/a"
    lat_str = f"p50={set_d['latency_p50_ms']:.0f}ms" if set_d.get("latency_p50_ms") is not None else "p50=n/a"
    elems.append(f'<text x="{w/2}" y="{h-16}" fill="#e2e8f0" font-family="system-ui,sans-serif" font-size="13" text-anchor="middle">{html.escape(f"{acc_str}  |  {ece_str}  |  {lat_str}")}</text>')
    elems.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(elems) + "\n", encoding="utf-8")


def render_arms_svg(set_c: dict[str, Any], out_path: Path) -> None:
    w, h = 620, 360
    pad_l, pad_r, pad_t, pad_b = 70, 30, 60, 70
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

    arms = set_c.get("arms") or {}
    groups = [
        ("Raw (B0)", arms.get("b0_raw", {})),
        ("Engine A", arms.get("engine_a", {})),
        ("Engine B-GPU", arms.get("engine_b_gpu", {})),
    ]
    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#0f172a" rx="12"/>',
        f'<text x="{w/2}" y="30" fill="#f8fafc" font-family="system-ui,sans-serif" font-size="18" font-weight="700" text-anchor="middle">Set C: Leakage &amp; WER by Arm (n={set_c.get("n_total", 0)})</text>',
        '<rect x="200" y="40" width="12" height="12" fill="#f97316"/><text x="218" y="51" fill="#e2e8f0" font-family="system-ui,sans-serif" font-size="12">Leakage %</text>',
        '<rect x="315" y="40" width="12" height="12" fill="#38bdf8"/><text x="333" y="51" fill="#e2e8f0" font-family="system-ui,sans-serif" font-size="12">Target WER %</text>',
    ]
    for pct in (0, 25, 50, 75, 100):
        y = pad_t + (1.0 - pct / 100.0) * ph
        elems.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="#1e293b" stroke-width="1"/>')
        elems.append(f'<text x="{pad_l-10}" y="{y+4:.1f}" fill="#94a3b8" font-family="system-ui,sans-serif" font-size="12" text-anchor="end">{pct}%</text>')

    gw = pw / len(groups)
    bw = 42
    for idx, (label, data) in enumerate(groups):
        cx = pad_l + (idx + 0.5) * gw
        leak = data.get("leak_clip_mean")
        wer = data.get("wer_clip_mean")
        for off, val, color in ((-bw - 4, leak, "#f97316"), (4, wer, "#38bdf8")):
            if val is not None:
                v_clamped = min(1.0, max(0.0, val))
                bh = v_clamped * ph
                y = pad_t + ph - bh
                elems.append(f'<rect x="{cx+off:.1f}" y="{y:.1f}" width="{bw}" height="{bh:.1f}" fill="{color}" rx="4"/>')
                elems.append(f'<text x="{cx+off+bw/2:.1f}" y="{y-6:.1f}" fill="#f8fafc" font-family="system-ui,sans-serif" font-size="12" font-weight="700" text-anchor="middle">{val*100:.1f}%</text>')
        elems.append(f'<text x="{cx:.1f}" y="{h-pad_b+24}" fill="#e2e8f0" font-family="system-ui,sans-serif" font-size="13" font-weight="600" text-anchor="middle">{html.escape(label)} (n={data.get("n_clips", 0)})</text>')

    gate = (set_c.get("gates") or {}).get("engine_b_beats_raw") or {}
    gate_msg = f"Beats-raw gate (B-GPU): {gate.get('reason', 'n/a')}"
    elems.append(f'<text x="{w/2}" y="{h-14}" fill="#94a3b8" font-family="system-ui,sans-serif" font-size="12" text-anchor="middle">{html.escape(gate_msg)}</text>')
    elems.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(elems) + "\n", encoding="utf-8")


def render_where_it_breaks_svg(set_c: dict[str, Any], out_path: Path) -> None:
    slices = set_c.get("where_it_breaks") or {}
    rows_out: list[tuple[str, int, float | None, float | None]] = []
    for dim in ("talkers", "angle", "distance_m", "noise_level", "occlusion", "network"):
        for bucket, vals in (slices.get(dim) or {}).items():
            b = vals.get("b", {})
            rows_out.append((f"{dim}: {bucket}", vals.get("n", 0), b.get("leak_clip_mean"), b.get("wer_clip_mean")))

    row_h = 28
    h = max(220, 90 + len(rows_out) * row_h)
    w = 680
    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#0f172a" rx="12"/>',
        f'<text x="{w/2}" y="30" fill="#f8fafc" font-family="system-ui,sans-serif" font-size="18" font-weight="700" text-anchor="middle">Where It Breaks — Engine B-GPU Leakage &amp; WER by Slice</text>',
        '<text x="230" y="56" fill="#f97316" font-family="system-ui,sans-serif" font-size="12" font-weight="700">Leakage %</text>',
        '<text x="455" y="56" fill="#38bdf8" font-family="system-ui,sans-serif" font-size="12" font-weight="700">WER %</text>',
    ]
    if not rows_out:
        elems.append(f'<text x="{w/2}" y="{h/2}" fill="#94a3b8" font-family="system-ui,sans-serif" font-size="15" text-anchor="middle">No Set C slices recorded yet</text>')
    else:
        for i, (label, n, leak, wer) in enumerate(rows_out):
            y = 76 + i * row_h
            elems.append(f'<text x="20" y="{y}" fill="#e2e8f0" font-family="system-ui,sans-serif" font-size="12">{html.escape(label)} (n={n})</text>')
            if leak is not None:
                bw = min(1.0, max(0.0, leak)) * 160
                elems.append(f'<rect x="230" y="{y-12}" width="{bw:.1f}" height="14" fill="#f97316" rx="3"/>')
                elems.append(f'<text x="{236+bw:.1f}" y="{y}" fill="#f8fafc" font-family="system-ui,sans-serif" font-size="11">{leak*100:.1f}%</text>')
            if wer is not None:
                bw = min(1.0, max(0.0, wer)) * 160
                elems.append(f'<rect x="455" y="{y-12}" width="{bw:.1f}" height="14" fill="#38bdf8" rx="3"/>')
                elems.append(f'<text x="{461+bw:.1f}" y="{y}" fill="#f8fafc" font-family="system-ui,sans-serif" font-size="11">{wer*100:.1f}%</text>')
    elems.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(elems) + "\n", encoding="utf-8")


def build_summary(root: Path, recompute_clips: bool = False) -> dict[str, Any]:
    set_c = score_clips_csv(root / "clips.csv", recompute_in_place=recompute_clips)
    set_d = score_decisions_csv(root / "decisions.csv")
    set_r = score_robot_csv(root / "robot.csv")
    voice_delay = summarize_voice_delay(root / "logs/hops.jsonl")
    gates = read_gate_log(root / "gate_log.csv")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "set_c": set_c,
        "set_d": set_d,
        "set_r": set_r,
        "voice_delay": voice_delay,
        "gate_log_count": len(gates),
        "gate_log": gates,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--recompute-clips", action="store_true", help="Recompute *_wer and *_leak in clips.csv from *_text")
    ap.add_argument("--out", default="", help="Summary JSON path (default: <root>/evals/summary.json)")
    args = ap.parse_args()

    root = Path(args.root)
    summary = build_summary(root, recompute_clips=args.recompute_clips)

    out_json = Path(args.out) if args.out else (root / "evals/summary.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    charts_dir = root / "evals/charts"
    render_calibration_svg(summary["set_d"], charts_dir / "calibration.svg")
    render_arms_svg(summary["set_c"], charts_dir / "arms_comparison.svg")
    render_where_it_breaks_svg(summary["set_c"], charts_dir / "where_it_breaks.svg")

    sc = summary["set_c"]
    sd = summary["set_d"]
    sr = summary["set_r"]
    vd = summary["voice_delay"]
    print(f"Set C: n={sc['n_total']} (2-talker={sc['n_two_talker']}, 3-talker={sc['n_three_talker']})")
    for arm_name, arm in (sc.get("arms") or {}).items():
        lk = f"{arm['leak_clip_mean']*100:.1f}%" if arm["leak_clip_mean"] is not None else "n/a"
        wr = f"{arm['wer_clip_mean']*100:.1f}%" if arm["wer_clip_mean"] is not None else "n/a"
        print(f"  {arm_name:12s}: n={arm['n_clips']:2d}  leak={lk:6s}  wer={wr:6s}  delay_p50={arm['delay_p50_s']}")
    print(f"  Beats-raw gate (B-GPU): {sc['gates']['engine_b_beats_raw']['reason']}")
    print(f"Set D: n={sd['n']}  acc@0.9={sd['accuracy']}  ece={sd['ece']}  p50_ms={sd['latency_p50_ms']}")
    print(f"Set R: n={sr['n']}  point_acc={sr['point_accuracy']}  hook_block={sr['hook_block_rate']}")
    print(
        f"Voice delay (live hops.jsonl): n_live={vd['n_hops']} "
        f"(excluded test={vd.get('n_hops_test', 0)})  "
        f"p50_ms={vd['voice_delay_p50_ms']}  rtt_p50_ms={vd['rtt_p50_ms']}"
    )
    print(f"Wrote {out_json} and SVGs in {charts_dir}")


if __name__ == "__main__":
    main()
