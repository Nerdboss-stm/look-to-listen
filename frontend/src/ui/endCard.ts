/**
 * END CARD renderer matching DESIGN.md:
 * - Full screen on bg.
 * - "Look to Listen. Hear only who you look at." at 64 px.
 * - Three numbers at 120 px, each with a 24 px label: leakage (raw against ours), delay, clips.
 * - One line: where it breaks.
 * - Repo link and QR at the bottom right, read strictly from REPO_URL in .env (never guessed).
 * - Never shows a number or URL that does not come from CSV files, live logs, or .env.
 */

import type { EndCardData } from "../types/contracts";
import { renderQrSvg } from "./qrSvg";

const GUESSED_FALLBACK_URL = "https://github.com/saran/look-to-listen";

function escapeHtml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtPctInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  return `${Math.round(v)}%`;
}

function fmtDelayHero(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "";
  return `${(ms / 1000).toFixed(2)}s`;
}

export function resolveConfiguredRepoUrl(
  data: EndCardData | null,
  envOverride?: string
): string {
  const fromEnv = (envOverride !== undefined ? envOverride : import.meta.env.REPO_URL || "").trim();
  if (fromEnv) return fromEnv;
  const fromApi = (data?.repo_url || "").trim();
  if (fromApi && fromApi !== GUESSED_FALLBACK_URL) {
    return fromApi;
  }
  return "";
}

function buildWhereItBreaksLine(data: EndCardData | null): string {
  if (!data || data.where_it_breaks.length === 0) {
    return "Where it breaks: awaiting Set C clips in clips.csv.";
  }
  const ranked = [...data.where_it_breaks].filter(
    (r) => r.target_leak_pct !== null || r.target_wer_pct !== null
  );
  if (ranked.length === 0) {
    return "Where it breaks: awaiting scored Set C slices.";
  }
  ranked.sort(
    (a, b) =>
      (b.target_leak_pct ?? -1) - (a.target_leak_pct ?? -1) ||
      (b.target_wer_pct ?? -1) - (a.target_wer_pct ?? -1)
  );
  const worst = ranked[0];
  const parts: string[] = [`${worst.slice} = ${worst.condition} (n=${worst.n})`];
  if (worst.target_leak_pct !== null) {
    parts.push(`leakage ${worst.target_leak_pct.toFixed(1)}%`);
  }
  if (worst.target_wer_pct !== null) {
    parts.push(`WER ${worst.target_wer_pct.toFixed(1)}%`);
  }
  if (worst.delay_p50_ms !== null) {
    parts.push(`delay ${(worst.delay_p50_ms / 1000).toFixed(2)}s`);
  }
  return `Where it breaks: ${parts.join(", ")}.`;
}

export function renderEndCardHtml(
  data: EndCardData | null,
  envRepoOverride?: string
): string {
  const rawLeak = data?.set_c.b0_leak_pct ?? null;
  const ourLeak =
    data?.set_c.engine_b_leak_pct ?? data?.set_c.engine_a_leak_pct ?? null;
  const leakHero =
    rawLeak !== null && ourLeak !== null
      ? `${fmtPctInt(rawLeak)}/${fmtPctInt(ourLeak)}`
      : ourLeak !== null
        ? fmtPctInt(ourLeak)
        : "";

  const delayMs =
    data?.delay.voice_p50_ms ?? data?.delay.caption_p50_ms ?? null;
  const delayHero = fmtDelayHero(delayMs);

  const clipsHero = data ? String(data.set_c.n_clips) : "";
  const repoUrl = resolveConfiguredRepoUrl(data, envRepoOverride);
  const repoDisplay = repoUrl.replace(/^https?:\/\//, "");
  const breaksLine = buildWhereItBreaksLine(data);
  const qrBlockHtml = repoUrl
    ? `<div class="end-card-qr-block">
        <div class="end-card-repo">${escapeHtml(repoDisplay)}</div>
        <div class="end-card-qr">${renderQrSvg(repoUrl, 132)}</div>
      </div>`
    : "";

  const subMetaParts: string[] = [];
  if (data) {
    if (data.set_d.accuracy_at_0_9_pct !== null) {
      subMetaParts.push(
        `Set D @0.9: ${data.set_d.accuracy_at_0_9_pct.toFixed(1)}% (n=${data.set_d.n_windows})`
      );
    }
    if (data.set_r.n_pairs > 0) {
      subMetaParts.push(
        `Set R: ${data.set_r.point_correct}/${data.set_r.n_pairs} point, ${data.set_r.hook_denied_other}/${data.set_r.n_pairs} hook blocked`
      );
    }
    if (data.delay.caption_p50_ms !== null) {
      subMetaParts.push(
        `Caption p50: ${(data.delay.caption_p50_ms / 1000).toFixed(2)}s`
      );
    }
  }

  return `
    <div class="end-card-top">
      <h1 class="end-card-headline">Look to Listen. Hear only who you look at.</h1>
      <button type="button" class="stage-btn" id="end-card-close">Close [Esc]</button>
    </div>

    <div class="end-card-metrics">
      <div class="end-metric-block">
        <div class="end-metric-num">${escapeHtml(leakHero)}</div>
        <div class="end-metric-label">LEAKAGE (RAW / OURS)</div>
      </div>
      <div class="end-metric-block">
        <div class="end-metric-num">${escapeHtml(delayHero)}</div>
        <div class="end-metric-label">MEASURED VOICE DELAY</div>
      </div>
      <div class="end-metric-block">
        <div class="end-metric-num">${escapeHtml(clipsHero)}</div>
        <div class="end-metric-label">VENUE EVAL CLIPS (SET C)</div>
      </div>
    </div>

    <div class="end-card-bottom">
      <div class="end-card-breaks-wrap">
        <div class="end-card-breaks">${escapeHtml(breaksLine)}</div>
        ${
          subMetaParts.length > 0
            ? `<div class="end-card-submeta">${escapeHtml(subMetaParts.join(" · "))}</div>`
            : ""
        }
      </div>
      ${qrBlockHtml}
    </div>
  `;
}
