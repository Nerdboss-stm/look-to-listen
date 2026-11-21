#!/usr/bin/env node
/**
 * Verifies 1080p 30 fps camera request, full-resolution 1920x1080 ClearVoice lip cropping,
 * and >= 25 fps real MediaPipe FaceLandmarker 3-face tracking over 10 seconds in Chrome.
 */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const DIST_DIR = path.resolve(REPO_ROOT, "frontend/dist");
const TEST_MP4 = "/tmp/test_3faces_1080p.mp4";
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
  ".mp4": "video/mp4",
};

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function startServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const urlPath = (req.url || "/").split("?")[0];
      if (urlPath === "/__test_3faces_1080p.mp4") {
        const stat = fs.statSync(TEST_MP4);
        res.writeHead(200, {
          "Content-Type": "video/mp4",
          "Content-Length": stat.size,
        });
        fs.createReadStream(TEST_MP4).pipe(res);
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
      resolve({ server, port: server.address().port });
    });
  });
}

async function launchChrome(debugPort) {
  const userDataDir = fs.mkdtempSync("/tmp/l2l-1080p-");
  const proc = spawn(
    CHROME_BIN,
    [
      "--headless=new",
      "--no-first-run",
      "--no-default-browser-check",
      "--autoplay-policy=no-user-gesture-required",
      "--enable-webgl",
      "--ignore-gpu-blocklist",
      "--use-gl=angle",
      "--use-angle=metal",
      "--enable-gpu-rasterization",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--window-size=1920,1080",
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] }
  );

  for (let i = 0; i < 100; i++) {
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
      // retry
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
  if (!fs.existsSync(TEST_MP4)) {
    throw new Error(`Missing ${TEST_MP4}`);
  }
  const { server, port } = await startServer();
  const debugPort = 19850 + Math.floor(Math.random() * 200);
  const { proc, wsUrl, userDataDir } = await launchChrome(debugPort);
  const cdp = new CdpClient(wsUrl);

  try {
    await cdp.connect();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    // Stay disconnected from backend so zero test hops are written to logs/hops.jsonl
    await cdp.send("Page.navigate", {
      url: `http://127.0.0.1:${port}/?backend=http://127.0.0.1:19999`,
    });
    await sleep(800);

    // Set up single-decode 1920x1080 30 fps real 3-face video on camera-video (matching real webcam decode load)
    const setup = await cdp.evalJs(`(async () => {
      const dummyCanvas = document.createElement("canvas");
      dummyCanvas.width = 16;
      dummyCanvas.height = 16;
      const vStream = dummyCanvas.captureStream(1);

      const actx = new AudioContext({ sampleRate: 16000 });
      await actx.resume();
      const aDest = actx.createMediaStreamDestination();

      window.__requestedConstraints = null;
      navigator.mediaDevices.getUserMedia = async (constraints) => {
        window.__requestedConstraints = constraints;
        return new MediaStream([
          ...vStream.getVideoTracks(),
          ...aDest.stream.getAudioTracks(),
        ]);
      };

      document.getElementById("start-btn").click();

      // Wait for startLiveCapture() to attach stream, then swap videoEl directly to the 1920x1080@30fps MP4
      // so Chrome decodes ONE 1920x1080 stream (not two simultaneous 1080p streams + captureStream re-encode)
      const videoEl = document.getElementById("camera-video");
      while (!window.__requestedConstraints) {
        await new Promise(r => setTimeout(r, 50));
      }
      await new Promise(r => setTimeout(r, 300));
      videoEl.srcObject = null;
      videoEl.src = "/__test_3faces_1080p.mp4";
      videoEl.loop = true;
      await videoEl.play();

      // Wait for real FaceLandmarker to detect all 3 real faces on the 1920x1080 stream
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 100));
        const chips = document.querySelectorAll("#face-bar button[data-face]");
        if (chips.length >= 3 && videoEl.videoWidth === 1920) break;
      }

      // Click consent on the center target face so ClearVoiceCropper cuts 25 fps lip crops from 1920x1080!
      const api = window.__L2L__;
      const tid = api.tracker.getTargetFaceId();
      if (tid) {
        const chip = document.querySelector('#face-bar button[data-face="' + tid + '"]');
        if (chip) chip.click();
      }

      const gl = document.createElement("canvas").getContext("webgl2");
      const dbg = gl ? gl.getExtension("WEBGL_debug_renderer_info") : null;
      const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "unknown";

      return {
        webglRenderer: renderer,
        constraints: window.__requestedConstraints,
        videoDims: [videoEl.videoWidth, videoEl.videoHeight],
        initialFaces: document.querySelectorAll("#face-bar button[data-face]").length,
        targetId: tid
      };
    })()`);

    console.log("1080p setup:", JSON.stringify(setup));

    // Sample real trackingFps, overlayFps, face count, and cropper source dimensions every 1 s over 10 s
    const samples = [];
    for (let s = 1; s <= 10; s++) {
      await sleep(1000);
      const snap = await cdp.evalJs(`(() => {
        const api = window.__L2L__;
        const videoEl = document.getElementById("camera-video");
        return {
          sec: ${s},
          trackingFps: api.getTrackingFps(),
          overlayFps: api.getFps(),
          facesTracked: document.querySelectorAll("#face-bar button[data-face]").length,
          videoDims: [videoEl.videoWidth, videoEl.videoHeight],
          cropSourceDims: api.cropper.lastSourceDims,
          cropSourceSquarePx: api.cropper.lastSourceCropPx,
          packer: api.hopPacker.getStats()
        };
      })()`);
      samples.push(snap);
      console.log(
        `  t=${s}s: faces=${snap.facesTracked}, trackingFps=${snap.trackingFps}, overlayFps=${snap.overlayFps}, cropFrom=${snap.cropSourceDims.join("x")} (${snap.cropSourceSquarePx}px sq), lastCrops=${snap.packer.lastCropCount}`
      );
    }

    // Ignore second 1 warmup if needed; compute mean & median over seconds 2..10
    const steady = samples.slice(1);
    const meanTrackFps =
      steady.reduce((a, b) => a + b.trackingFps, 0) / steady.length;
    const sortedFaces = steady.map((x) => x.facesTracked).sort((a, b) => a - b);
    const medianFaces = sortedFaces[Math.floor(sortedFaces.length / 2)];
    const minFaces = sortedFaces[0];
    const reqV = setup.constraints?.video || {};

    console.log(
      `\nSummary (1080p 3-face real MediaPipe FaceLandmarker): requested=${reqV.width?.ideal}x${reqV.height?.ideal}@${reqV.frameRate?.ideal}fps, actual_video=${setup.videoDims.join("x")}, crop_source=${steady[steady.length - 1].cropSourceDims.join("x")}, median_faces=${medianFaces} (min=${minFaces}), mean_tracking_fps=${meanTrackFps.toFixed(1)} fps`
    );

    if (
      reqV.width?.ideal !== 1920 ||
      reqV.height?.ideal !== 1080 ||
      setup.videoDims[0] !== 1920 ||
      setup.videoDims[1] !== 1080 ||
      steady[steady.length - 1].cropSourceDims[0] !== 1920 ||
      steady[steady.length - 1].cropSourceDims[1] !== 1080 ||
      medianFaces < 3 ||
      meanTrackFps < 25.0
    ) {
      throw new Error("1080p 3-face >=25 fps check FAILED");
    }
    console.log("VERDICT: PASS (3 faces tracked at >= 25 fps at 1920x1080 with full-res lip crops)");
  } finally {
    cdp.close();
    proc.kill("SIGKILL");
    server.close();
    await sleep(150);
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {}
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
