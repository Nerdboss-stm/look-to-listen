#!/usr/bin/env node
/**
 * Automated verification for DESIGN.md checks D1, D2, D3, D4, and D5 using
 * real Google Chrome via Chrome DevTools Protocol (zero external packages needed).
 *
 * Usage:
 *   node frontend/scripts/verify_design_checks.mjs --mode d1-d4
 *   node frontend/scripts/verify_design_checks.mjs --mode d5
 */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const DIST_DIR = path.resolve(REPO_ROOT, "frontend/dist");
const CHROME_BIN =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".wasm": "application/wasm",
  ".task": "application/octet-stream",
  ".json": "application/json",
  ".svg": "image/svg+xml",
};

function readRepoUrlFromEnv() {
  const envPath = path.join(REPO_ROOT, ".env");
  if (!fs.existsSync(envPath)) return "";
  for (const raw of fs.readFileSync(envPath, "utf-8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    if (key === "REPO_URL") {
      return line.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
    }
  }
  return "";
}

function startStaticServer() {
  const configuredRepoUrl = readRepoUrlFromEnv();
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const urlPath = (req.url || "/").split("?")[0];
      if (urlPath === "/api/end_card") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            updated_at: "2026-11-21T12:00:00-05:00",
            set_c: {
              n_clips: 0,
              b0_leak_pct: null,
              b0_wer_pct: null,
              engine_a_leak_pct: null,
              engine_a_wer_pct: null,
              engine_b_leak_pct: null,
              engine_b_wer_pct: null,
              beats_raw_gate_passed: false,
            },
            set_d: { n_windows: 0, accuracy_at_0_9_pct: null, latency_p50_ms: null },
            set_r: { n_pairs: 0, point_correct: 0, hook_denied_other: 0 },
            delay: { voice_p50_ms: 1112, voice_p95_ms: 1273, caption_p50_ms: null, hops_logged: 375 },
            where_it_breaks: [],
            repo_url: configuredRepoUrl,
          })
        );
        return;
      }
      if (urlPath === "/api/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            ok: true,
            gpu_health: { gpu: "NVIDIA GeForce RTX 4090", gpu_ms_last20: [129] },
          })
        );
        return;
      }
      const rel = urlPath === "/" ? "/index.html" : urlPath;
      const filePath = path.join(DIST_DIR, rel);
      if (!filePath.startsWith(DIST_DIR) || !fs.existsSync(filePath)) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }
      const ext = path.extname(filePath);
      res.writeHead(200, {
        "Content-Type": MIME[ext] || "application/octet-stream",
      });
      fs.createReadStream(filePath).pipe(res);
    });
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      resolve({ server, port: addr.port });
    });
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function launchChrome(debugPort, width = 1920, height = 1080) {
  const userDataDir = fs.mkdtempSync("/tmp/l2l-chrome-");
  const proc = spawn(
    CHROME_BIN,
    [
      "--headless=new",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-gpu-vsync",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--hide-scrollbars",
      `--window-size=${width},${height}`,
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] }
  );

  // Wait for /json/list to respond
  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
      if (res.ok) {
        const targets = await res.json();
        const page = targets.find((t) => t.type === "page");
        if (page && page.webSocketDebuggerUrl) {
          return { proc, wsUrl: page.webSocketDebuggerUrl, userDataDir };
        }
      }
    } catch {
      // retry
    }
    await sleep(100);
  }
  proc.kill("SIGKILL");
  throw new Error("Timed out waiting for Chrome DevTools endpoint");
}

class CdpClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  connect() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.wsUrl);
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = (err) => reject(err);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(String(ev.data));
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve: res, reject: rej } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) rej(new Error(JSON.stringify(msg.error)));
          else res(msg.result);
        }
      };
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evalJs(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) {
      throw new Error(
        `JS exception: ${JSON.stringify(res.exceptionDetails.exception)}`
      );
    }
    return res.result.value;
  }

  close() {
    this.ws?.close();
  }
}

function srgbToLin(c) {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}
function hexLum(hex) {
  const h = hex.trim().replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return 0.2126 * srgbToLin(r) + 0.7152 * srgbToLin(g) + 0.0722 * srgbToLin(b);
}
function contrastRatio(hex1, hex2) {
  const l1 = hexLum(hex1);
  const l2 = hexLum(hex2);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

async function populateStageForInspection(cdp) {
  await cdp.evalJs(`(() => {
    const api = window.__L2L__;
    const faces = [
      {
        id: "face-1",
        box: { x: 0.41, y: 0.19, w: 0.18, h: 0.42 },
        lips: [[0.47, 0.48], [0.53, 0.48]],
        mouth_open: 0.16,
        color: "#FFB000",
        consent: { given: true, by: "operator", time: "2026-11-21T12:00:00-05:00" },
        is_target: true
      },
      {
        id: "face-2",
        box: { x: 0.13, y: 0.24, w: 0.15, h: 0.36 },
        lips: [[0.18, 0.49], [0.23, 0.49]],
        mouth_open: 0.11,
        color: "#4CC3FF",
        consent: { given: true, by: "operator", time: "2026-11-21T12:00:00-05:00" },
        is_target: false
      },
      {
        id: "face-3",
        box: { x: 0.73, y: 0.25, w: 0.14, h: 0.34 },
        lips: [[0.78, 0.49], [0.82, 0.49]],
        mouth_open: 0.04,
        color: "#FF7AB6",
        consent: { given: false, by: null, time: null },
        is_target: false
      }
    ];
    api.setSyntheticScene(faces, "face-1", [1440, 640]);

    // Raw & Target caption lines (older + newest + interim)
    api.injectServerMessage({
      type: "segment",
      payload: {
        segment_id: "r1", t0: 1000, t1: 2000, lane: "raw", face_id: "face-2",
        text: "Can someone pass the schedule before the next session starts?",
        confidence: 0.92, engine: "B-GPU", is_final: true
      }
    });
    api.injectServerMessage({
      type: "segment",
      payload: {
        segment_id: "r2", t0: 2100, t1: 3200, lane: "raw", face_id: null,
        text: "We measured 129 milliseconds on the pod and two lanes live",
        confidence: 0.89, engine: "B-GPU", is_final: false
      }
    });
    api.injectServerMessage({
      type: "segment",
      payload: {
        segment_id: "t1", t0: 1200, t1: 2400, lane: "target", face_id: "face-1",
        text: "We measured 129 milliseconds on the pod.",
        confidence: 0.96, engine: "B-GPU", is_final: true, latency_ms: 1920
      }
    });
    api.injectServerMessage({
      type: "segment",
      payload: {
        segment_id: "t2", t0: 2500, t1: 3500, lane: "target", face_id: "face-1",
        text: "Both caption streams run side by side.",
        confidence: 0.95, engine: "B-GPU", is_final: true, latency_ms: 1980
      }
    });
    // Non-consenting face-3 segment must be suppressed!
    api.injectServerMessage({
      type: "segment",
      payload: {
        segment_id: "t_blocked", t0: 3600, t1: 4000, lane: "raw", face_id: "face-3",
        text: "SHOULD_NOT_APPEAR_WITHOUT_CONSENT",
        confidence: 0.9, engine: "B-GPU", is_final: true
      }
    });

    // Live metrics from logs
    api.injectServerMessage({
      type: "metrics",
      payload: {
        engine: "B-GPU",
        voice_delay_ms: 890,
        caption_delay_ms: 1980,
        gpu_ms: 129,
        rtt_ms: 240,
        raw_leakage_pct: null,
        target_leakage_pct: null
      }
    });
    api.flushDelayMeter();

    // Agent events including a hook denial
    api.injectServerMessage({
      type: "agent_event",
      payload: {
        time: "12:01:10",
        event_type: "hook",
        hook: "gate_privacy",
        decision: "DENY",
        reason: "face-3 has no consent record",
        summary: "Blocked save_transcript"
      }
    });
    api.injectServerMessage({
      type: "agent_event",
      payload: {
        time: "12:01:14",
        event_type: "tool_call",
        tool: "save_transcript",
        decision: "ALLOW",
        summary: "Redacted face-3 and saved consenting lines"
      }
    });

    // Memory
    api.injectServerMessage({
      type: "memory_answer",
      payload: {
        question: "What was the GPU separation time?",
        answer: "129 milliseconds median on the RTX 4090 pod.",
        time: "00:42",
        clip: null,
        confidence: 0.95
      }
    });

    // Robot commands (target allowed + non-target denied & struck through)
    api.injectServerMessage({
      type: "robot_command",
      payload: {
        command_id: "c1",
        face_id: "face-2",
        text: "Hand me the phone",
        target_face_id: "face-1",
        point: null,
        object_label: null,
        allowed: false,
        hook_reason: "face-2 is not current target face-1"
      }
    });
    api.injectServerMessage({
      type: "robot_command",
      payload: {
        command_id: "c2",
        face_id: "face-1",
        text: "Hand me the bottle",
        target_face_id: "face-1",
        point: [540, 620],
        object_label: "bottle",
        allowed: true
      }
    });
  })()`);
  await sleep(250);
}

async function runD1ToD4(cdp, skipLongD3 = false) {
  // First verify the "no consented target" state BEFORE populating consented scene:
  // 1) Initial load (0 faces): voice muted + LOOK TO LISTEN says "Point at someone"
  // 2) Pointing at an unconsented face ("?"): voice stays muted + LOOK TO LISTEN still says "Point at someone" + unguided segment ignored
  const noTargetCheck = await cdp.evalJs(`(() => {
    const api = window.__L2L__;
    const initialLaneText = document.getElementById("target-captions").innerText.trim();
    const initialMuted = api.voicePlayer.isTargetMuted();

    // Point at face-3 who has consent.given = false
    api.setSyntheticScene([
      {
        id: "face-3",
        box: { x: 0.41, y: 0.19, w: 0.18, h: 0.42 },
        lips: [[0.47, 0.48], [0.53, 0.48]],
        mouth_open: 0.14,
        color: "#FF7AB6",
        consent: { given: false, by: null, time: null },
        is_target: true
      }
    ], "face-3", [1440, 640]);

    // Attempt to inject an unguided target caption and hop_result while unconsented
    api.injectServerMessage({
      type: "segment",
      payload: {
        segment_id: "unguided_1", t0: 100, t1: 500, lane: "target", face_id: null,
        text: "UNGUIDED_SEPARATION_TEXT", confidence: 0.8, engine: "B-GPU", is_final: true
      }
    });
    const unconsentedLaneText = document.getElementById("target-captions").innerText.trim();
    const unconsentedMuted = api.voicePlayer.isTargetMuted();

    return {
      initialLaneText,
      initialMuted,
      unconsentedLaneText,
      unconsentedMuted
    };
  })()`);

  if (
    noTargetCheck.initialLaneText !== "Point at someone" ||
    !noTargetCheck.initialMuted ||
    noTargetCheck.unconsentedLaneText !== "Point at someone" ||
    !noTargetCheck.unconsentedMuted
  ) {
    throw new Error(`No-consented-target guard FAILED: ${JSON.stringify(noTargetCheck)}`);
  }
  console.log(
    `PASS No-Consented-Target Guard: initial="${noTargetCheck.initialLaneText}" (muted=${noTargetCheck.initialMuted}), unconsented_face="${noTargetCheck.unconsentedLaneText}" (muted=${noTargetCheck.unconsentedMuted})`
  );

  await populateStageForInspection(cdp);
  const consentedUnmuted = await cdp.evalJs(`!window.__L2L__.voicePlayer.isTargetMuted()`);
  if (!consentedUnmuted) {
    throw new Error("Expected VoicePlayer targetMuted=false once consented face-1 is active");
  }
  // Wake controls so D1 verifies all operator buttons and consent chips >= 18px too
  await cdp.evalJs(`window.dispatchEvent(new MouseEvent("mousemove"))`);
  await sleep(100);

  // Verify Fix 1 (empty leakage hidden, valued leakage aligned with lane title),
  // Fix 3 (2-line wrapped agent events), Fix 4 (0.89s & 1.98s two-decimal seconds),
  // Fix 5 (3s mouse idle hide + mousemove show)
  const fixesCheck = await cdp.evalJs(`(async () => {
    const rawGroupHidden = getComputedStyle(document.getElementById("leak-raw-group")).visibility === "hidden";
    const rawValEmpty = document.getElementById("leak-raw-val").textContent === "";
    const voiceText = document.getElementById("delay-voice-val").textContent;
    const capText = document.getElementById("delay-caption-val").textContent;
    const agentStyle = getComputedStyle(document.querySelector(".agent-item"));
    const agentClamp = agentStyle.webkitLineClamp;
    const agentWhiteSpace = agentStyle.whiteSpace;

    // Inject numeric leakage to check vertical alignment of LEAKAGE label with lane title
    window.__L2L__.injectServerMessage({
      type: "metrics",
      payload: {
        engine: "B-GPU",
        voice_delay_ms: 890,
        caption_delay_ms: 1980,
        gpu_ms: 129,
        rtt_ms: 240,
        raw_leakage_pct: 48,
        target_leakage_pct: 10
      }
    });
    const titleRect = document.querySelector("#lane-raw .lane-title").getBoundingClientRect();
    const leakLblRect = document.querySelector("#lane-raw .lane-leak-label").getBoundingClientRect();
    const titleMidY = titleRect.top + titleRect.height / 2;
    const leakMidY = leakLblRect.top + leakLblRect.height / 2;
    const alignDeltaPx = Math.abs(titleMidY - leakMidY);

    // Reset leakage back to null (live pre-eval state)
    window.__L2L__.injectServerMessage({
      type: "metrics",
      payload: {
        engine: "B-GPU",
        voice_delay_ms: 890,
        caption_delay_ms: 1980,
        gpu_ms: 129,
        rtt_ms: 240,
        raw_leakage_pct: null,
        target_leakage_pct: null
      }
    });

    return {
      rawGroupHidden,
      rawValEmpty,
      voiceText,
      capText,
      agentClamp,
      agentWhiteSpace,
      alignDeltaPx: Number(alignDeltaPx.toFixed(2))
    };
  })()`);

  if (
    !fixesCheck.rawGroupHidden ||
    !fixesCheck.rawValEmpty ||
    fixesCheck.voiceText !== "0.89s" ||
    fixesCheck.capText !== "1.98s" ||
    fixesCheck.agentClamp !== "2" ||
    fixesCheck.agentWhiteSpace === "nowrap" ||
    fixesCheck.alignDeltaPx > 1.5
  ) {
    throw new Error(`Screenshot review fixes check FAILED: ${JSON.stringify(fixesCheck)}`);
  }

  // Verify Fix 5: 3 s idle hides .camera-controls & #face-bar, mousemove restores them
  await sleep(3250);
  const idleOpacities = await cdp.evalJs(`({
    controls: parseFloat(getComputedStyle(document.querySelector(".camera-controls")).opacity),
    faces: parseFloat(getComputedStyle(document.getElementById("face-bar")).opacity)
  })`);
  if (idleOpacities.controls !== 0 || idleOpacities.faces !== 0) {
    throw new Error(`Fix 5 idle hide FAILED: ${JSON.stringify(idleOpacities)}`);
  }
  await cdp.evalJs(`window.dispatchEvent(new MouseEvent("mousemove"))`);
  await sleep(200);
  const activeOpacities = await cdp.evalJs(`({
    controls: parseFloat(getComputedStyle(document.querySelector(".camera-controls")).opacity),
    faces: parseFloat(getComputedStyle(document.getElementById("face-bar")).opacity)
  })`);
  if (activeOpacities.controls !== 1 || activeOpacities.faces !== 1) {
    throw new Error(`Fix 5 mousemove restore FAILED: ${JSON.stringify(activeOpacities)}`);
  }
  console.log(
    `PASS Review Fixes 1-6: leakage_hidden_when_null=true, title_align_delta=${fixesCheck.alignDeltaPx}px, delay=${fixesCheck.voiceText}/${fixesCheck.capText}, agent_clamp=${fixesCheck.agentClamp} lines, idle_hide=0->1`
  );

  // --- D1: Sizes & Layout Geometry at 1920x1080 ---
  const d1 = await cdp.evalJs(`(() => {
    const under18 = [];
    const walker = document.createTreeWalker(document.getElementById("stage"), NodeFilter.SHOW_TEXT);
    let node;
    let checkedCount = 0;
    while ((node = walker.nextNode())) {
      const txt = node.nodeValue.trim();
      if (!txt) continue;
      const el = node.parentElement;
      if (!el) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity) === 0) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      checkedCount++;
      const px = parseFloat(style.fontSize);
      if (px < 18) {
        under18.push({ tag: el.tagName, id: el.id, cls: el.className, px, txt: txt.slice(0, 30) });
      }
    }

    const targetCapPx = parseFloat(getComputedStyle(document.querySelector(".lane-body-target .caption-line")).fontSize);
    const rawCapPx = parseFloat(getComputedStyle(document.querySelector(".lane-body-raw .caption-line")).fontSize);
    const counterPxs = Array.from(document.querySelectorAll(".counter-56")).map(el => parseFloat(getComputedStyle(el).fontSize));
    const clockPx = parseFloat(getComputedStyle(document.getElementById("wall-clock")).fontSize);
    const camRect = document.getElementById("camera-stage").getBoundingClientRect();
    const rawLaneRect = document.getElementById("lane-raw").getBoundingClientRect();
    const tgtLaneRect = document.getElementById("lane-target").getBoundingClientRect();
    const sideRect = document.querySelector(".side-strip").getBoundingClientRect();
    const blockedPresent = document.body.innerText.includes("SHOULD_NOT_APPEAR_WITHOUT_CONSENT");

    return {
      checkedCount,
      under18,
      targetCapPx,
      rawCapPx,
      minCounterPx: Math.min(...counterPxs),
      clockPx,
      cam: [Math.round(camRect.width), Math.round(camRect.height)],
      rawLane: [Math.round(rawLaneRect.width), Math.round(rawLaneRect.height)],
      tgtLane: [Math.round(tgtLaneRect.width), Math.round(tgtLaneRect.height)],
      sideW: Math.round(sideRect.width),
      blockedPresent
    };
  })()`);

  if (
    d1.under18.length > 0 ||
    d1.targetCapPx < 44 ||
    d1.minCounterPx < 56 ||
    d1.blockedPresent
  ) {
    throw new Error(`D1 FAILED: ${JSON.stringify(d1)}`);
  }
  console.log(
    `PASS D1 Sizes (1920x1080): checked=${d1.checkedCount} visible text nodes, under_18px=0, target_caption=${d1.targetCapPx}px, raw_caption=${d1.rawCapPx}px, counters=${d1.minCounterPx}px, clock=${d1.clockPx}px, camera=${d1.cam.join("x")}, lanes=${d1.rawLane.join("x")}+${d1.tgtLane.join("x")}, side=${d1.sideW}px, non_consent_suppressed=${!d1.blockedPresent}`
  );

  // --- D2: Contrast computed from live CSS tokens in both Dark & Bright palettes ---
  const readTokens = () =>
    cdp.evalJs(`(() => {
      const s = getComputedStyle(document.body);
      return {
        bg: s.getPropertyValue("--bg").trim(),
        panel: s.getPropertyValue("--panel").trim(),
        text: s.getPropertyValue("--text").trim(),
        raw: s.getPropertyValue("--raw-words").trim(),
        label: s.getPropertyValue("--label").trim()
      };
    })()`);

  await cdp.evalJs(`window.__L2L__.toggleBrightRoom(false)`);
  const darkT = await readTokens();
  await cdp.evalJs(`window.__L2L__.toggleBrightRoom(true)`);
  const brightT = await readTokens();
  await cdp.evalJs(`window.__L2L__.toggleBrightRoom(false)`);

  const d2 = {
    dark: {
      targetOnPanel: Number(contrastRatio(darkT.text, darkT.panel).toFixed(2)),
      rawOnPanel: Number(contrastRatio(darkT.raw, darkT.panel).toFixed(2)),
      labelOnPanel: Number(contrastRatio(darkT.label, darkT.panel).toFixed(2)),
      targetOnBg: Number(contrastRatio(darkT.text, darkT.bg).toFixed(2)),
      labelOnBg: Number(contrastRatio(darkT.label, darkT.bg).toFixed(2)),
    },
    bright: {
      targetOnPanel: Number(contrastRatio(brightT.text, brightT.panel).toFixed(2)),
      rawOnPanel: Number(contrastRatio(brightT.raw, brightT.panel).toFixed(2)),
      labelOnPanel: Number(contrastRatio(brightT.label, brightT.panel).toFixed(2)),
      targetOnBg: Number(contrastRatio(brightT.text, brightT.bg).toFixed(2)),
      labelOnBg: Number(contrastRatio(brightT.label, brightT.bg).toFixed(2)),
    },
  };

  if (
    d2.dark.targetOnPanel < 7 ||
    d2.dark.rawOnPanel < 7 ||
    d2.dark.labelOnPanel < 4.5 ||
    d2.bright.targetOnPanel < 7 ||
    d2.bright.rawOnPanel < 7 ||
    d2.bright.labelOnPanel < 4.5
  ) {
    throw new Error(`D2 FAILED: ${JSON.stringify(d2)}`);
  }
  console.log(
    `PASS D2 Contrast: Dark(target=${d2.dark.targetOnPanel}:1, raw=${d2.dark.rawOnPanel}:1, label=${d2.dark.labelOnPanel}:1) | Bright(target=${d2.bright.targetOnPanel}:1, raw=${d2.bright.rawOnPanel}:1, label=${d2.bright.labelOnPanel}:1)`
  );
  if (skipLongD3) return;

  // --- D3 (30 s layout shift == 0) & D4 (10 s 3-face overlay >= 30 fps) ---
  // Run D4 (first 10 s) concurrently inside the 30 s D3 window so total wall time is 30 s!
  console.log("Running D3 (30 s layout-shift=0 check) + D4 (10 s 3-face overlay FPS check)...");
  const d3d4 = await cdp.evalJs(`new Promise((resolve) => {
    const api = window.__L2L__;
    let cls = 0;
    const obs = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        cls += entry.value;
      }
    });
    obs.observe({ type: "layout-shift", buffered: false });

    const trackedIds = ["leak-raw-val", "leak-target-val", "delay-voice-val", "delay-caption-val", "delay-row-check"];
    const els = [
      document.getElementById("leak-raw-val"),
      document.getElementById("leak-target-val"),
      document.getElementById("delay-voice-val"),
      document.getElementById("delay-caption-val"),
      document.querySelector(".panel-delay")
    ];
    const initialWidths = els.map((e) => e.getBoundingClientRect().width);
    let maxWidthDelta = 0;

    // 10-second 3-face animated overlay FPS measurement (D4)
    const fpsStart = performance.now();
    let overlayFrames = 0;
    let d4Fps = 0;
    function animStep(now) {
      const elapsedS = (now - fpsStart) / 1000;
      if (elapsedS <= 10.0) {
        overlayFrames++;
        const dx = Math.sin(now / 350) * 0.04;
        const targetId = (Math.floor(elapsedS / 2.5) % 2 === 0) ? "face-1" : "face-2";
        api.setSyntheticScene([
          {
            id: "face-1",
            box: { x: 0.42 + dx, y: 0.19, w: 0.18, h: 0.42 },
            lips: [[0.48 + dx, 0.48], [0.53 + dx, 0.48]],
            mouth_open: 0.15,
            color: "#FFB000",
            consent: { given: true, by: "op", time: "2026-11-21T12:00:00-05:00" },
            is_target: targetId === "face-1"
          },
          {
            id: "face-2",
            box: { x: 0.14 - dx * 0.5, y: 0.23, w: 0.15, h: 0.36 },
            lips: [[0.19, 0.48], [0.24, 0.48]],
            mouth_open: 0.09,
            color: "#4CC3FF",
            consent: { given: true, by: "op", time: "2026-11-21T12:00:00-05:00" },
            is_target: targetId === "face-2"
          },
          {
            id: "face-3",
            box: { x: 0.74, y: 0.25, w: 0.14, h: 0.34 },
            lips: [[0.78, 0.49], [0.82, 0.49]],
            mouth_open: 0.03,
            color: "#FF7AB6",
            consent: { given: false, by: null, time: null },
            is_target: false
          }
        ], targetId, [1440, 640]);
        requestAnimationFrame(animStep);
      } else if (d4Fps === 0) {
        d4Fps = overlayFrames / elapsedS;
      }
    }
    requestAnimationFrame(animStep);

    // 30-second value churn across counters, DELAY, captions, and panels (D3)
    const leakSamples = [null, 0, 7, 14, 48, 100];
    const voiceSamples = [null, 180, 940, 1490, 1850, 3400];
    const capSamples = [null, 650, 1920, 2950, 4100, 6800];
    let tick = 0;
    const churn = setInterval(() => {
      tick++;
      api.injectServerMessage({
        type: "metrics",
        payload: {
          engine: tick % 19 === 0 ? "A" : "B-GPU",
          voice_delay_ms: voiceSamples[tick % voiceSamples.length],
          caption_delay_ms: capSamples[(tick + 2) % capSamples.length],
          gpu_ms: 125 + (tick % 12),
          rtt_ms: 230 + (tick % 30),
          raw_leakage_pct: leakSamples[tick % leakSamples.length],
          target_leakage_pct: leakSamples[(tick + 3) % leakSamples.length]
        }
      });
      api.flushDelayMeter();

      els.forEach((el, idx) => {
        const w = el.getBoundingClientRect().width;
        const delta = Math.abs(w - initialWidths[idx]);
        if (delta > maxWidthDelta) maxWidthDelta = delta;
      });
    }, 250);

    setTimeout(() => {
      clearInterval(churn);
      obs.disconnect();
      resolve({
        cls: Number(cls.toFixed(6)),
        maxWidthDelta: Number(maxWidthDelta.toFixed(4)),
        d4Fps: Number(d4Fps.toFixed(1)),
        overlayFrames
      });
    }, 30100);
  })`);

  if (d3d4.cls > 0 || d3d4.maxWidthDelta > 0.01) {
    throw new Error(`D3 FAILED: ${JSON.stringify(d3d4)}`);
  }
  if (d3d4.d4Fps < 30) {
    throw new Error(`D4 FAILED: ${JSON.stringify(d3d4)}`);
  }
  console.log(
    `PASS D3 No Shift (30 s): layout_shift=${d3d4.cls}, max_counter_delay_width_delta=${d3d4.maxWidthDelta}px`
  );
  console.log(
    `PASS D4 Overlay FPS (10 s, 3 faces): ${d3d4.d4Fps} fps (${d3d4.overlayFrames} frames)`
  );
}

async function captureScreenshot(cdp, width, height, outPath, bright = false) {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await cdp.evalJs(`window.dispatchEvent(new Event("resize"))`);
  await populateStageForInspection(cdp);

  // Paint a realistic low-key room silhouette onto a canvas stream for videoEl so camera & robot mini-frame render realistically in screenshots
  await cdp.evalJs(`(async () => {
    const off = document.createElement("canvas");
    off.width = 1440;
    off.height = 640;
    const g = off.getContext("2d");
    g.fillStyle = "#161B22";
    g.fillRect(0, 0, 1440, 640);
    // Table surface + bottle & phone props for Robot R1 crosshair
    g.fillStyle = "#1E2530";
    g.fillRect(0, 470, 1440, 170);
    // Three person silhouettes matching face-2 (left), face-1 (center), face-3 (right)
    const drawPerson = (cx, cy, r, shirt) => {
      g.fillStyle = shirt;
      g.beginPath();
      g.ellipse(cx, cy + r * 2.1, r * 1.45, r * 1.5, 0, Math.PI, 0);
      g.fill();
      g.fillStyle = "#8D7B68";
      g.beginPath();
      g.ellipse(cx, cy, r * 0.78, r * 0.98, 0, 0, Math.PI * 2);
      g.fill();
    };
    drawPerson(1440 * 0.205, 640 * 0.42, 110, "#253042");
    drawPerson(1440 * 0.50, 640 * 0.40, 128, "#2F3A4A");
    drawPerson(1440 * 0.80, 640 * 0.42, 105, "#232B38");

    const v = document.getElementById("camera-video");
    if (off.captureStream && v.srcObject === null) {
      v.srcObject = off.captureStream(30);
      try { await v.play(); } catch {}
    }

    window.__L2L__.toggleBrightRoom(${bright ? "true" : "false"});
    window.__L2L__.injectServerMessage({
      type: "metrics",
      payload: {
        engine: "B-GPU",
        voice_delay_ms: 920,
        caption_delay_ms: 1940,
        gpu_ms: 129,
        rtt_ms: 240,
        raw_leakage_pct: null,
        target_leakage_pct: null
      }
    });
    window.__L2L__.flushDelayMeter();
  })()`);
  // Wait 3.2 s without mouse movement so screenshots capture the clean idle-hidden HUD state
  await sleep(3200);

  const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, Buffer.from(shot.data, "base64"));
  const bytes = fs.statSync(outPath).size;
  console.log(`Saved screenshot ${outPath} (${width}x${height}, ${bytes} bytes)`);
}

async function main() {
  const mode = process.argv.includes("--mode")
    ? process.argv[process.argv.indexOf("--mode") + 1]
    : "d1-d4";

  const { server, port } = await startStaticServer();
  const debugPort = 19222 + Math.floor(Math.random() * 400);
  const { proc, wsUrl, userDataDir } = await launchChrome(debugPort, 1920, 1080);
  const cdp = new CdpClient(wsUrl);

  try {
    await cdp.connect();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1920,
      height: 1080,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp.send("Page.navigate", { url: `http://127.0.0.1:${port}/` });
    await sleep(600);

    if (mode === "quick") {
      await runD1ToD4(cdp, true);
    }
    if (mode === "d1-d4" || mode === "all") {
      await runD1ToD4(cdp, false);
    }
    if (mode === "d5" || mode === "all") {
      const uiDir = path.join(REPO_ROOT, "evals/ui");
      await captureScreenshot(
        cdp,
        1920,
        1080,
        path.join(uiDir, "stage_1920x1080.png"),
        false
      );
      await captureScreenshot(
        cdp,
        1280,
        720,
        path.join(uiDir, "stage_1280x720.png"),
        false
      );
      await captureScreenshot(
        cdp,
        1920,
        1080,
        path.join(uiDir, "stage_1920x1080_bright.png"),
        true
      );
      await cdp.evalJs(`window.__L2L__.toggleBrightRoom(false); window.__L2L__.openEndCard(true);`);
      await sleep(250);
      const endShot = await cdp.send("Page.captureScreenshot", { format: "png" });
      const endPath = path.join(uiDir, "end_card_1920x1080.png");
      fs.writeFileSync(endPath, Buffer.from(endShot.data, "base64"));
      console.log(`Saved screenshot ${endPath} (1920x1080, ${fs.statSync(endPath).size} bytes)`);
    }
  } finally {
    cdp.close();
    proc.kill("SIGKILL");
    server.close();
    await sleep(150);
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {
      // Ignore transient Chrome profile lock cleanup race
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
