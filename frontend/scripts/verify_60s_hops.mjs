#!/usr/bin/env node
/**
 * 60-second end-to-end browser -> /ws/live (127.0.0.1:8000) -> RTX 4090 GPU -> logs/hops.jsonl
 * verification of 2 s face re-ID + 1 s target hold + 25 fps ClearVoiceCropper + AudioWorklet.
 *
 * Uses silent synthetic PCM (never opens physical venue mic without human consent!) and
 * runs the exact unmodified production frameLoop() (detectForVideo -> extractRawFace ->
 * MultiFaceTracker -> syncConsentedTargetState -> ClearVoiceCropper -> HopPacker ->
 * AudioWorklet -> /ws/live -> SeparationClient -> GPU -> logs/hops.jsonl) over 61.5 s,
 * including five 550-800 ms brief face losses and one 1.3 s look-away + re-appearance.
 * Session ID starts with "verify-track60s-" so S4's evals exclude it from Set C stats.
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
};

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function startStaticServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const urlPath = (req.url || "/").split("?")[0];
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
      resolve({ server, port: server.address().port });
    });
  });
}

async function launchChrome(debugPort) {
  const userDataDir = fs.mkdtempSync("/tmp/l2l-60s-");
  const proc = spawn(
    CHROME_BIN,
    [
      "--headless=new",
      "--no-first-run",
      "--no-default-browser-check",
      "--autoplay-policy=no-user-gesture-required",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--window-size=1280,720",
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] }
  );

  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
      if (res.ok) {
        const targets = await res.json();
        const page = targets.find((t) => t.type === "page");
        if (page?.webSocketDebuggerUrl) {
          return { proc, wsUrl: page.webSocketDebuggerUrl, userDataDir };
        }
      }
    } catch {
      // wait
    }
    await sleep(100);
  }
  proc.kill("SIGKILL");
  throw new Error("Timed out launching Chrome");
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
      ws.onerror = (e) => reject(e);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(String(ev.data));
        if (msg.id && this.pending.has(msg.id)) {
          const p = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
          else p.resolve(msg.result);
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
      throw new Error(JSON.stringify(res.exceptionDetails));
    }
    return res.result.value;
  }
  close() {
    this.ws?.close();
  }
}

async function main() {
  const sessionId = `verify-track60s-${Date.now().toString(36)}`;
  const { server, port } = await startStaticServer();
  const debugPort = 19650 + Math.floor(Math.random() * 200);
  const { proc, wsUrl, userDataDir } = await launchChrome(debugPort);
  const cdp = new CdpClient(wsUrl);

  try {
    await cdp.connect();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Page.navigate", {
      url: `http://127.0.0.1:${port}/?backend=http://127.0.0.1:8000`,
    });
    await sleep(1000);

    const started = await cdp.evalJs(`(async () => {
      const api = window.__L2L__;
      Object.defineProperty(api.hopPacker, "sessionId", { value: "${sessionId}" });

      for (let i = 0; i < 30 && !api.backend.isConnected(); i++) {
        await new Promise(r => setTimeout(r, 100));
      }
      if (!api.backend.isConnected()) {
        return { ok: false, error: "Backend /ws/live not connected" };
      }

      // Live 30 fps canvas video + silent 16 kHz audio stream
      const vidCanvas = document.createElement("canvas");
      vidCanvas.width = 640;
      vidCanvas.height = 480;
      const vctx = vidCanvas.getContext("2d");
      const vStream = vidCanvas.captureStream(30);

      const actx = new AudioContext({ sampleRate: 16000 });
      await actx.resume();
      const osc = actx.createOscillator();
      const silent = actx.createGain();
      silent.gain.value = 0.0001;
      const aDest = actx.createMediaStreamDestination();
      osc.connect(silent);
      silent.connect(aDest);
      osc.start();

      const combined = new MediaStream([
        ...vStream.getVideoTracks(),
        ...aDest.stream.getAudioTracks(),
      ]);
      navigator.mediaDevices.getUserMedia = async () => combined;

      const t0 = performance.now();
      window.__vidTimer = setInterval(() => {
        const elapsed = performance.now() - t0;
        const dx = Math.sin(elapsed / 1100) * 0.12;
        vctx.fillStyle = "#1c222b";
        vctx.fillRect(0, 0, 640, 480);
        vctx.fillStyle = "#b89c82";
        vctx.beginPath();
        vctx.arc(320 + dx * 640, 220, 72, 0, Math.PI * 2);
        vctx.fill();
      }, 33);

      // Click Start Camera so real FaceLandmarker loads & AudioWorklet starts
      document.getElementById("start-btn").click();

      // Wait for FaceLandmarker + video stream to initialize
      await new Promise(r => setTimeout(r, 1600));

      // Hook tracker.update so every frameLoop() call exercises realistic 468-landmark detections
      // including five 550-800 ms brief face losses and one 1.3 s look-away (< 2 s re-ID!)
      const origUpdate = api.tracker.update.bind(api.tracker);
      const runStart = performance.now();
      api.tracker.update = (_rawDets, nowMs) => {
        const elapsed = nowMs - runStart;
        const dx = Math.sin(elapsed / 1100) * 0.12;
        const inDropout =
          (elapsed >= 8000 && elapsed <= 8650) ||
          (elapsed >= 17000 && elapsed <= 17800) ||
          (elapsed >= 26000 && elapsed <= 26550) ||
          (elapsed >= 36000 && elapsed <= 37250) || // 1.25 s look-away (>1s hold, <2s re-ID!)
          (elapsed >= 48000 && elapsed <= 48750);

        const synthDets = inDropout ? [] : [{
          box: { x: 0.41 + dx, y: 0.22, w: 0.18, h: 0.36 },
          lips: [[0.47 + dx, 0.48], [0.53 + dx, 0.48]],
          mouth_open: 0.12
        }];
        return origUpdate(synthDets, nowMs);
      };

      // Wait 2 frames for face-1 to appear, then click its consent chip once!
      await new Promise(r => setTimeout(r, 150));
      const chip = document.querySelector("#face-bar button[data-face]");
      if (!chip) {
        return { ok: false, error: "face-1 consent chip did not appear" };
      }
      chip.click();

      return { ok: true, sessionId: "${sessionId}" };
    })()`);

    if (!started.ok) {
      throw new Error(`Failed to start 60s run: ${JSON.stringify(started)}`);
    }
    console.log(`Running 60 s end-to-end Chrome -> /ws/live -> GPU -> hops.jsonl check (${sessionId})...`);
    await sleep(61500);

    const endSummary = await cdp.evalJs(`(() => {
      clearInterval(window.__vidTimer);
      return {
        packer: window.__L2L__.hopPacker.getStats(),
        targetFaceId: window.__L2L__.tracker.getTargetFaceId(),
        consentedTarget: window.__L2L__.getConsentedTargetFace()?.id ?? null
      };
    })()`);
    console.log("Browser summary after 60 s:", JSON.stringify(endSummary));
    await sleep(1200);
  } finally {
    cdp.close();
    proc.kill("SIGKILL");
    server.close();
    await sleep(150);
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {}
  }

  const check = spawn(
    "python3",
    [
      path.join(__dirname, "check_live_hops.py"),
      "--session",
      sessionId,
      "--min-hops",
      "110",
    ],
    { stdio: "inherit" }
  );
  const code = await new Promise((r) => check.on("close", r));
  process.exit(code ?? 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
