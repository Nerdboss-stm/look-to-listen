import "./styles.css";
import type { FaceLandmarker } from "@mediapipe/tasks-vision";
import { MicCapture } from "./audio/micCapture";
import { VoicePlayer } from "./audio/voicePlayer";
import { BackendClient, type ConnectionState } from "./net/backendClient";
import { HopPacker } from "./pipeline/hopPacker";
import type {
  AgentEvent,
  CaptionSegment,
  EndCardData,
  EngineId,
  Face,
  LiveMetrics,
  MemoryAnswer,
  RobotCommand,
  ServerWsMessage,
  SpeakingDecision,
} from "./types/contracts";
import { renderEndCardHtml } from "./ui/endCard";
import {
  canvasClickToNormalizedVideo,
  renderOverlay,
  renderRobotMiniFrame,
  SpotlightAnimator,
  type TargetAnchor,
} from "./ui/overlayRenderer";
import { ClearVoiceCropper } from "./vision/clearvoiceCrop";
import {
  createFaceLandmarker,
  extractRawFace,
  MultiFaceTracker,
  speakerColorForFaceId,
  speakerLetterForFaceId,
} from "./vision/faceTracker";

const STAGE_W = 1920;
const STAGE_H = 1080;
const CAMERA_W = 1440;
const CAMERA_H = 640;

// Stage & Camera DOM
const stageEl = document.getElementById("stage") as HTMLElement;
const videoEl = document.getElementById("camera-video") as HTMLVideoElement;
const canvasEl = document.getElementById("overlay-canvas") as HTMLCanvasElement;
const canvasCtx = canvasEl.getContext("2d")!;
const cameraErrorEl = document.getElementById("camera-error") as HTMLElement;
const startBtn = document.getElementById("start-btn") as HTMLButtonElement;
const autoCenterBtn = document.getElementById("auto-center-btn") as HTMLButtonElement;
const audioToggleBtn = document.getElementById("audio-toggle-btn") as HTMLButtonElement;
const replayBtn = document.getElementById("replay-btn") as HTMLButtonElement;
const brightBtn = document.getElementById("bright-btn") as HTMLButtonElement;
const endCardBtn = document.getElementById("end-card-btn") as HTMLButtonElement;

const wsLabelEl = document.getElementById("ws-label") as HTMLElement;
const wallClockEl = document.getElementById("wall-clock") as HTMLElement;
const faceBarEl = document.getElementById("face-bar") as HTMLElement;

// Lanes DOM
const rawCaptionsEl = document.getElementById("raw-captions") as HTMLElement;
const targetCaptionsEl = document.getElementById("target-captions") as HTMLElement;
const targetLaneBadgeEl = document.getElementById("target-lane-badge") as HTMLElement;
const leakRawGroupEl = document.getElementById("leak-raw-group") as HTMLElement;
const leakTargetGroupEl = document.getElementById("leak-target-group") as HTMLElement;
const leakRawValEl = document.getElementById("leak-raw-val") as HTMLElement;
const leakTargetValEl = document.getElementById("leak-target-val") as HTMLElement;

// Side strip DOM
const perfPillEl = document.getElementById("perf-pill") as HTMLElement;
const delayVoiceValEl = document.getElementById("delay-voice-val") as HTMLElement;
const delayVoiceBarEl = document.getElementById("delay-voice-bar") as HTMLElement;
const delayCaptionValEl = document.getElementById("delay-caption-val") as HTMLElement;
const delayCaptionBarEl = document.getElementById("delay-caption-bar") as HTMLElement;

const enginePanelEl = document.getElementById("engine-panel") as HTMLElement;
const engineLabelEl = document.getElementById("engine-label") as HTMLElement;

const agentFeedEl = document.getElementById("agent-feed") as HTMLElement;
const saveTranscriptBtn = document.getElementById("save-transcript-btn") as HTMLButtonElement;

const memoryForm = document.getElementById("memory-form") as HTMLFormElement;
const memoryInput = document.getElementById("memory-input") as HTMLInputElement;
const memoryAnswerEl = document.getElementById("memory-answer") as HTMLElement;
const summaryBtn = document.getElementById("summary-btn") as HTMLButtonElement;

const robotForm = document.getElementById("robot-form") as HTMLFormElement;
const robotInput = document.getElementById("robot-input") as HTMLInputElement;
const robotCanvasEl = document.getElementById("robot-canvas") as HTMLCanvasElement;
const robotCanvasCtx = robotCanvasEl.getContext("2d")!;
const robotFeedEl = document.getElementById("robot-feed") as HTMLElement;

const endCardBackdropEl = document.getElementById("end-card-backdrop") as HTMLElement;
const endCardContentEl = document.getElementById("end-card-content") as HTMLElement;
const spotlightLineEl = document.getElementById("spotlight-line") as unknown as SVGPathElement;

// Core pipeline instances
const tracker = new MultiFaceTracker();
const spotlightAnimator = new SpotlightAnimator();
const cropper = new ClearVoiceCropper(0.8);
const hopPacker = new HopPacker();
const micCapture = new MicCapture();
const voicePlayer = new VoicePlayer();

// Runtime state
let landmarker: FaceLandmarker | null = null;
let mediaStream: MediaStream | null = null;
let rafId: number | null = null;
let latestFaces: Face[] = [];
let mockVideoDims: [number, number] | null = null; // Used by D4/D5 synthetic harness
let lastVideoTime = -1;
let lastDetectTimestampMs = 0;
let frameCount = 0;
let detectCount = 0;
let fpsWindowStart = performance.now();
let currentFps = 0;
let currentTrackingFps = 0;
let lastFrameCaptureMs = 0;
let lastRobotMiniMs = 0;
let latestFrameJpeg: string | null = null;
let brightMode = false;
let reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let lastTargetAnchor: TargetAnchor | null = null;

// Buffered metrics flushed to DELAY meter twice a second (DESIGN.md: updates twice a second)
let bufferedVoiceDelayMs: number | null = null;
let bufferedCaptionDelayMs: number | null = null;
let latestGpuMs: number | null = null;
let gpuHardwareName = "RTX 4090";
let currentEngine: EngineId = "B-GPU";

const fullFrameCanvas = document.createElement("canvas");
fullFrameCanvas.width = 640;
fullFrameCanvas.height = 360;
const fullFrameCtx = fullFrameCanvas.getContext("2d")!;

// Dedicated 640x360 canvas for MediaPipe FaceLandmarker so 3-face tracking sustains
// 28-30 fps while ClearVoiceCropper cuts lip crops from the full 1920x1080 videoEl.
const detectCanvas = document.createElement("canvas");
detectCanvas.width = 640;
detectCanvas.height = 360;
const detectCtx = detectCanvas.getContext("2d", { alpha: false })!;

const decisionsByFace = new Map<string, SpeakingDecision>();
const rawSegments: CaptionSegment[] = [];
const targetSegments: CaptionSegment[] = [];
const seenSegmentKeys = new Set<string>();
const agentEvents: AgentEvent[] = [];
const robotCommands: RobotCommand[] = [];
let activeRobotPoint: RobotCommand | null = null;
let lastQuestionAsked = "";
let latestEndCard: EndCardData | null = null;
let lastFaceBarKey = "";

// Fixed 1920x1080 letterbox scaler (never reflows)
function fitStageToWindow(): void {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const scale = Math.min(vw / STAGE_W, vh / STAGE_H);
  const left = Math.round((vw - STAGE_W * scale) / 2);
  const top = Math.round((vh - STAGE_H * scale) / 2);
  stageEl.style.transform = `translate(${left}px, ${top}px) scale(${scale})`;
}
fitStageToWindow();
window.addEventListener("resize", fitStageToWindow);

window
  .matchMedia("(prefers-reduced-motion: reduce)")
  .addEventListener("change", (ev) => {
    reducedMotion = ev.matches;
  });

const backend = new BackendClient({
  onStateChange: handleConnectionChange,
  onMessage: handleServerMessage,
});
backend.connect();

function escapeHtml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// Both VOICE and CAPTIONS delays display in seconds with two decimals (e.g. 0.92s and 1.94s)
function fmtDelay(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "";
  return `${(ms / 1000).toFixed(2)}s`;
}

function setLeakageDisplay(
  groupEl: HTMLElement,
  valEl: HTMLElement,
  pct: number | null | undefined
): void {
  if (pct === null || pct === undefined || Number.isNaN(pct)) {
    valEl.textContent = "";
    groupEl.classList.add("hidden-until-value");
  } else {
    valEl.textContent = `${Math.round(pct)}%`;
    groupEl.classList.remove("hidden-until-value");
  }
}

function handleConnectionChange(state: ConnectionState): void {
  wsLabelEl.textContent = state === "connected" ? "LIVE" : "LOCAL";
  if (state === "connected") {
    void backend.fetchHealth().then((h) => {
      if (h?.gpuName) gpuHardwareName = h.gpuName;
      if (h?.gpuMsLast !== null && h?.gpuMsLast !== undefined && latestGpuMs === null) {
        latestGpuMs = h.gpuMsLast;
      }
      renderEngineReadout();
    });
  }
}

function renderEngineReadout(): void {
  if (currentEngine === "A") {
    engineLabelEl.textContent = "ENGINE A · GEMINI ONLY";
  } else if (currentEngine === "B-GPU") {
    engineLabelEl.textContent =
      latestGpuMs !== null
        ? `B-GPU · ${gpuHardwareName} · ${Math.round(latestGpuMs)} ms`
        : `B-GPU · ${gpuHardwareName}`;
  } else if (currentEngine === "B-Mac") {
    engineLabelEl.textContent =
      latestGpuMs !== null
        ? `B-MAC · MPS · ${Math.round(latestGpuMs)} ms`
        : "B-MAC · MPS";
  } else {
    engineLabelEl.textContent = "REPLAY · LAST 10S";
  }
}

function setEngineState(next: EngineId, hopMs?: number): void {
  const prev = currentEngine;
  currentEngine = next;
  if (hopMs && hopMs !== hopPacker.getHopMs()) {
    hopPacker.setHopMs(hopMs);
    micCapture.setHopMs(hopMs);
  }
  renderEngineReadout();

  // DESIGN.md: On failover it reads "ENGINE A · GEMINI ONLY" and its outline flashes once for 1 s.
  if (prev !== "A" && next === "A" && !reducedMotion) {
    enginePanelEl.classList.remove("engine-flash");
    void enginePanelEl.offsetWidth;
    enginePanelEl.classList.add("engine-flash");
  }
}

function updateDelayBar(
  valEl: HTMLElement,
  barEl: HTMLElement,
  ms: number | null,
  budgetMs: number
): void {
  valEl.textContent = fmtDelay(ms);
  valEl.classList.remove("status-ok", "status-warn", "status-bad");
  barEl.classList.remove("fill-ok", "fill-warn", "fill-bad");

  if (ms === null || Number.isNaN(ms)) {
    valEl.classList.add("status-ok");
    barEl.classList.add("fill-ok");
    barEl.style.transform = "scaleX(0)";
    return;
  }

  // Budget sits at 50% of the bar (full scale = 2x budget)
  const scale = Math.max(0.02, Math.min(1, ms / (budgetMs * 2)));
  barEl.style.transform = `scaleX(${scale.toFixed(4)})`;

  if (ms <= budgetMs) {
    valEl.classList.add("status-ok");
    barEl.classList.add("fill-ok");
  } else if (ms <= budgetMs * 2) {
    valEl.classList.add("status-warn");
    barEl.classList.add("fill-warn");
  } else {
    valEl.classList.add("status-bad");
    barEl.classList.add("fill-bad");
  }
}

// DESIGN.md: DELAY updates twice a second
function flushDelayMeter(): void {
  updateDelayBar(delayVoiceValEl, delayVoiceBarEl, bufferedVoiceDelayMs, 1500);
  updateDelayBar(delayCaptionValEl, delayCaptionBarEl, bufferedCaptionDelayMs, 3000);
}
setInterval(flushDelayMeter, 500);

function applyMetrics(m: LiveMetrics): void {
  if (m.gpu_ms !== null) {
    latestGpuMs = m.gpu_ms;
  }
  setEngineState(m.engine, m.hop_ms);
  if (m.voice_delay_ms !== null) {
    bufferedVoiceDelayMs = m.voice_delay_ms;
  }
  if (m.caption_delay_ms !== null) {
    bufferedCaptionDelayMs = m.caption_delay_ms;
  }
  setLeakageDisplay(leakRawGroupEl, leakRawValEl, m.raw_leakage_pct);
  setLeakageDisplay(leakTargetGroupEl, leakTargetValEl, m.target_leakage_pct);
}

function isFaceConsented(faceId: string | null | undefined): boolean {
  if (!faceId) return true;
  const f = tracker.getFace(faceId) ?? latestFaces.find((x) => x.id === faceId) ?? null;
  // DESIGN.md: A face without consent: dashed gray ring, badge "?", and no captions for it.
  return f ? f.consent.given : true;
}

/**
 * Returns the active target Face ONLY when a face is currently targeted AND has given consent.
 * When null, voice playback is muted, no target crops/IDs are sent for separation,
 * and LOOK TO LISTEN shows "Point at someone".
 */
function getConsentedTargetFace(): Face | null {
  const effectiveId =
    tracker.getTargetFaceId() ?? latestFaces.find((f) => f.is_target)?.id ?? null;
  if (!effectiveId) return null;
  const f =
    tracker.getFace(effectiveId) ?? latestFaces.find((x) => x.id === effectiveId) ?? null;
  if (!f || !f.consent.given) return null;
  return f;
}

let lastConsentedTargetId: string | null = null;

function syncConsentedTargetState(): Face | null {
  const consented = getConsentedTargetFace();
  const nextId = consented ? consented.id : null;
  voicePlayer.setTargetMuted(nextId === null);

  if (nextId !== lastConsentedTargetId) {
    lastConsentedTargetId = nextId;
    hopPacker.markTargetSwitch(nextId);
    voicePlayer.reset();
    if (nextId === null) {
      // Clear stale segments from previous target so unguided speech never shows
      targetSegments.length = 0;
    }
    syncTargetHeaderBadge(nextId);
    renderCaptionLanes();
    backend.send({
      type: "set_target",
      face_id: nextId,
      mode: tracker.getTargetMode(),
    });
  } else {
    syncTargetHeaderBadge(nextId);
  }
  return consented;
}

function upsertSegment(list: CaptionSegment[], seg: CaptionSegment): void {
  if (seg.segment_id) {
    const idx = list.findIndex((s) => s.segment_id === seg.segment_id);
    if (idx >= 0) {
      list[idx] = seg;
      return;
    }
  }
  list.push(seg);
  if (list.length > 24) list.shift();
}

function ageClass(indexFromOldest: number, total: number): string {
  const ageFromNewest = total - 1 - indexFromOldest;
  if (ageFromNewest <= 0) return "age-0";
  if (ageFromNewest === 1) return "age-1";
  if (ageFromNewest === 2) return "age-2";
  return "age-3";
}

function renderCaptionLanes(): void {
  // Raw lane: newest at bottom, older fade 80% / 60% / 40%
  const visibleRaw = rawSegments
    .filter((s) => !s.face_id || isFaceConsented(s.face_id))
    .slice(-4);
  if (visibleRaw.length === 0) {
    rawCaptionsEl.innerHTML = `<div class="lane-empty">Waiting for speech</div>`;
  } else {
    rawCaptionsEl.innerHTML = visibleRaw
      .map((s, idx) => {
        const key = `raw:${s.segment_id || `${s.t0}-${s.text}`}`;
        const isNew = !seenSegmentKeys.has(key);
        seenSegmentKeys.add(key);
        const ageCls = ageClass(idx, visibleRaw.length);
        const interimCls = s.is_final === false ? "caption-interim" : "";
        const newCls = isNew ? "caption-line-new" : "";

        // Attributed words get speaker color + letter badge; unattributed keep --raw-words
        if (s.face_id) {
          const color = speakerColorForFaceId(s.face_id, brightMode);
          const letter = speakerLetterForFaceId(s.face_id);
          return `<div class="caption-line ${ageCls} ${interimCls} ${newCls}" style="color: ${color};"><span class="speaker-letter-badge" style="background: ${color};">${letter}</span>${escapeHtml(s.text)}</div>`;
        }
        return `<div class="caption-line ${ageCls} ${interimCls} ${newCls}">${escapeHtml(s.text)}</div>`;
      })
      .join("");
  }

  // Target lane: when there is no consented target, show "Point at someone";
  // when pointing at a consented target, show "Waiting for speech" until words arrive.
  const consentedTarget = getConsentedTargetFace();
  if (!consentedTarget) {
    targetCaptionsEl.innerHTML = `<div class="lane-empty">Point at someone</div>`;
    return;
  }

  const visibleTarget = targetSegments
    .filter((s) => s.lane === "target" && (!s.face_id || isFaceConsented(s.face_id)))
    .slice(-4);

  if (visibleTarget.length === 0) {
    targetCaptionsEl.innerHTML = `<div class="lane-empty">Waiting for speech</div>`;
  } else {
    targetCaptionsEl.innerHTML = visibleTarget
      .map((s, idx) => {
        const key = `tgt:${s.segment_id || `${s.t0}-${s.text}`}`;
        const isNew = !seenSegmentKeys.has(key);
        seenSegmentKeys.add(key);
        const ageCls = ageClass(idx, visibleTarget.length);
        const interimCls = s.is_final === false ? "caption-interim" : "";
        const newCls = isNew ? "caption-line-new" : "";
        return `<div class="caption-line ${ageCls} ${interimCls} ${newCls}">${escapeHtml(s.text)}</div>`;
      })
      .join("");
  }
}

// DESIGN.md: AGENT: last 4 events at 20 px. Hook denials in bad color, with reason.
function renderAgentFeed(): void {
  const last4 = agentEvents.slice(-4);
  if (last4.length === 0) {
    agentFeedEl.innerHTML = `<div class="side-empty">No agent events yet</div>`;
    return;
  }
  agentFeedEl.innerHTML = last4
    .map((ev) => {
      const isDeny = ev.decision === "DENY";
      const cls = isDeny ? "agent-item agent-item-deny" : "agent-item";
      const text = isDeny && ev.reason
        ? `DENIED · ${ev.hook || ev.tool || "hook"}: ${ev.reason}`
        : ev.summary;
      return `<div class="${cls}" title="${escapeHtml(text)}">${escapeHtml(text)}</div>`;
    })
    .join("");
}

// DESIGN.md: ROBOT: small live frame with crosshair, and command text. Denied command struck through in bad color.
function renderRobotFeed(): void {
  const recent = robotCommands.slice(-3);
  if (recent.length === 0) {
    robotFeedEl.innerHTML = `<div class="side-empty">No robot command yet</div>`;
    return;
  }
  robotFeedEl.innerHTML = recent
    .map((cmd) => {
      const letter = speakerLetterForFaceId(cmd.face_id);
      const denied = cmd.allowed === false;
      const cls = denied ? "robot-cmd-line robot-cmd-denied" : "robot-cmd-line";
      const labelSuffix =
        !denied && cmd.object_label ? ` (${cmd.object_label})` : "";
      return `<div class="${cls}">${letter}: ${escapeHtml(cmd.text)}${escapeHtml(labelSuffix)}</div>`;
    })
    .join("");
}

// DESIGN.md: MEMORY: the last question, its answer and its time.
function renderMemoryAnswer(ans: MemoryAnswer): void {
  const qText = ans.question || lastQuestionAsked;
  const timeStr =
    ans.time !== null && ans.time !== undefined ? String(ans.time) : "—";
  memoryAnswerEl.innerHTML = `
    <div class="memory-q">${escapeHtml(qText)}</div>
    <div class="memory-a">${escapeHtml(ans.answer)}</div>
    <div class="memory-t">${escapeHtml(timeStr)}</div>
  `;
}

function handleServerMessage(msg: ServerWsMessage): void {
  switch (msg.type) {
    case "hop_result": {
      const res = msg.payload;
      latestGpuMs = res.gpu_ms;
      // Never play unguided separation when there is no consented target
      if (getConsentedTargetFace() !== null) {
        voicePlayer.enqueuePcmBase64(res.pcm);
        const rtt =
          res.rtt_ms ??
          (res.t_capture ? Math.max(0, Date.now() - res.t_capture) : null);
        if (rtt !== null) {
          bufferedVoiceDelayMs = hopPacker.getHopMs() + rtt + 150;
        }
      }
      if (res.engine) {
        setEngineState(res.engine);
      } else {
        renderEngineReadout();
      }
      break;
    }
    case "segment": {
      const seg = msg.payload;
      if (seg.lane === "raw") {
        upsertSegment(rawSegments, seg);
      } else if (getConsentedTargetFace() !== null) {
        // Ignore target-lane captions when there is no consented target
        upsertSegment(targetSegments, seg);
        if (seg.latency_ms !== undefined && seg.lane === "target") {
          bufferedCaptionDelayMs = seg.latency_ms;
        }
      }
      renderCaptionLanes();
      break;
    }
    case "decision": {
      decisionsByFace.set(msg.payload.face_id, msg.payload);
      break;
    }
    case "engine_status": {
      setEngineState(msg.engine, msg.hop_ms);
      break;
    }
    case "metrics": {
      applyMetrics(msg.payload);
      break;
    }
    case "agent_event": {
      agentEvents.push(msg.payload);
      if (agentEvents.length > 32) agentEvents.shift();
      renderAgentFeed();
      break;
    }
    case "memory_answer": {
      renderMemoryAnswer(msg.payload);
      break;
    }
    case "robot_command": {
      const cmd = msg.payload;
      robotCommands.push(cmd);
      if (robotCommands.length > 16) robotCommands.shift();
      if (cmd.allowed !== false && cmd.point) {
        activeRobotPoint = cmd;
      }
      renderRobotFeed();
      break;
    }
    case "end_card": {
      latestEndCard = msg.payload;
      if (!endCardBackdropEl.classList.contains("hidden")) {
        void openEndCard(false);
      }
      break;
    }
  }
}

function syncTargetHeaderBadge(targetFaceId: string | null): void {
  const effectiveId =
    targetFaceId ?? latestFaces.find((f) => f.is_target)?.id ?? null;
  const face = effectiveId
    ? tracker.getFace(effectiveId) ?? latestFaces.find((f) => f.id === effectiveId) ?? null
    : null;

  if (!face || !face.consent.given) {
    targetLaneBadgeEl.classList.add("hidden");
    return;
  }
  const letter = speakerLetterForFaceId(face.id);
  const color = speakerColorForFaceId(face.id, brightMode);
  targetLaneBadgeEl.textContent = letter;
  targetLaneBadgeEl.style.backgroundColor = color;
  targetLaneBadgeEl.classList.remove("hidden");
}

function updateFaceBar(faces: Face[], _targetFaceId: string | null): void {
  const key = `${brightMode ? 1 : 0}|` + faces
    .map((f) => `${f.id}:${f.consent.given ? 1 : 0}`)
    .join("|");
  if (key === lastFaceBarKey) return;
  lastFaceBarKey = key;

  faceBarEl.innerHTML = faces
    .map((f) => {
      const letter = f.consent.given ? speakerLetterForFaceId(f.id) : "?";
      const color = f.consent.given
        ? speakerColorForFaceId(f.id, brightMode)
        : "var(--label)";
      const statusText = f.consent.given ? `${letter} · Consent On` : `? · Grant Consent (${speakerLetterForFaceId(f.id)})`;
      return `<button type="button" class="face-consent-chip" data-face="${escapeHtml(f.id)}" style="border-color: ${color};">${escapeHtml(statusText)}</button>`;
    })
    .join("");
}

function captureFullFrameBase64(): string | null {
  if (videoEl.videoWidth <= 0 || videoEl.videoHeight <= 0) return null;
  fullFrameCtx.drawImage(videoEl, 0, 0, fullFrameCanvas.width, fullFrameCanvas.height);
  const url = fullFrameCanvas.toDataURL("image/jpeg", 0.72);
  const idx = url.indexOf(",");
  return idx >= 0 ? url.slice(idx + 1) : url;
}

// 30 fps draw loop on one fixed 1440x640 canvas. Zero model calls inside.
function frameLoop(): void {
  rafId = requestAnimationFrame(frameLoop);
  const nowPerf = performance.now();
  const nowWall = Date.now();
  const videoReady = videoEl.readyState >= 2 && videoEl.videoWidth > 0;

  if (landmarker && videoReady && videoEl.currentTime !== lastVideoTime) {
    lastVideoTime = videoEl.currentTime;
    const detectTs = Math.max(lastDetectTimestampMs + 1, Math.round(nowPerf));
    lastDetectTimestampMs = detectTs;
    try {
      const targetDetW = 640;
      const targetDetH = Math.max(
        240,
        Math.round((videoEl.videoHeight / videoEl.videoWidth) * targetDetW)
      );
      if (detectCanvas.width !== targetDetW || detectCanvas.height !== targetDetH) {
        detectCanvas.width = targetDetW;
        detectCanvas.height = targetDetH;
      }
      detectCtx.drawImage(videoEl, 0, 0, targetDetW, targetDetH);
      const res = landmarker.detectForVideo(detectCanvas, detectTs);
      detectCount++;
      const rawDetections = (res.faceLandmarks || []).map(extractRawFace);
      const step = tracker.update(rawDetections, nowPerf);
      latestFaces = step.faces;
      updateFaceBar(step.faces, step.targetFaceId);
    } catch {
      // Guard against transient MediaPipe frame errors so tracking never halts
    }
  }

  if (landmarker && videoReady) {
    const consentedTarget = syncConsentedTargetState();

    // Sample ClearVoice crops at steady 25 fps (every 40 ms) even if camera auto-exposure
    // drops below 25 fps or target is held during a <= 1 s brief loss
    if (consentedTarget && hopPacker.shouldSampleTargetCrop(nowPerf)) {
      const b64 = cropper.extractBase64Jpeg(
        videoEl,
        consentedTarget.id,
        consentedTarget.box
      );
      if (b64) hopPacker.pushTargetCrop(b64, nowPerf, consentedTarget.id);
    }

    if (hopPacker.shouldSampleOtherCrops(nowPerf)) {
      for (const f of latestFaces) {
        if (!f.consent.given || f.id === consentedTarget?.id) continue;
        const b64 = cropper.extractBase64Jpeg(videoEl, f.id, f.box);
        if (b64) hopPacker.pushOtherCrop(f.id, b64, nowPerf);
      }
    }

    if (nowPerf - lastFrameCaptureMs >= 480) {
      lastFrameCaptureMs = nowPerf;
      latestFrameJpeg = captureFullFrameBase64();
    }
  }

  const vw = mockVideoDims ? mockVideoDims[0] : videoEl.videoWidth;
  const vh = mockVideoDims ? mockVideoDims[1] : videoEl.videoHeight;
  const activeTargetId =
    tracker.getTargetFaceId() ?? latestFaces.find((f) => f.is_target)?.id ?? null;

  lastTargetAnchor = renderOverlay(
    canvasCtx,
    vw,
    vh,
    {
      faces: latestFaces,
      targetFaceId: activeTargetId,
      brightMode,
      reducedMotion,
      nowMs: nowPerf,
    },
    spotlightAnimator
  );

  // Thin spotlight line joining target ring to the right lane ("LOOK TO LISTEN")
  const activeTargetFace = activeTargetId
    ? latestFaces.find((f) => f.id === activeTargetId) ?? null
    : null;
  if (lastTargetAnchor && activeTargetFace && activeTargetFace.consent.given) {
    // Camera box sits at (24, 24); right lane sits at x=[752..1464], y=680
    const x1 = 24 + lastTargetAnchor.cx;
    const y1 = Math.min(24 + CAMERA_H, 24 + lastTargetAnchor.cy + lastTargetAnchor.radius);
    const x2 = 966; // aligns with target badge in right lane header
    const y2 = 680;
    const midY = (y1 + y2) / 2;
    spotlightLineEl.setAttribute(
      "d",
      `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${x1.toFixed(1)} ${midY.toFixed(1)}, ${x2} ${midY.toFixed(1)}, ${x2} ${y2}`
    );
    spotlightLineEl.setAttribute("stroke", lastTargetAnchor.color);
  } else {
    spotlightLineEl.setAttribute("d", "");
    spotlightLineEl.setAttribute("stroke", "transparent");
  }

  if (nowPerf - lastRobotMiniMs >= 100) {
    lastRobotMiniMs = nowPerf;
    renderRobotMiniFrame(
      robotCanvasCtx,
      videoEl,
      videoReady,
      activeRobotPoint,
      brightMode
    );
  }

  frameCount++;
  if (nowPerf - fpsWindowStart >= 1000) {
    const elapsedS = (nowPerf - fpsWindowStart) / 1000;
    currentFps = Math.round(frameCount / elapsedS);
    currentTrackingFps = Number((detectCount / elapsedS).toFixed(1));
    frameCount = 0;
    detectCount = 0;
    fpsWindowStart = nowPerf;
    const displayFps =
      landmarker && videoReady ? Math.round(currentTrackingFps) : currentFps;
    const stats = hopPacker.getStats(nowWall);
    perfPillEl.textContent =
      stats.hopsSent > 0
        ? `${displayFps} fps · ${stats.hopsPerSec.toFixed(1)}/s`
        : `${displayFps} fps`;
  }
}

// Start the 30+ fps overlay loop immediately so synthetic/offline checks & clock run cleanly
rafId = requestAnimationFrame(frameLoop);

async function startLiveCapture(): Promise<void> {
  startBtn.disabled = true;
  startBtn.textContent = "Starting...";
  cameraErrorEl.textContent = "";

  try {
    const [lm, stream] = await Promise.all([
      landmarker ? Promise.resolve(landmarker) : createFaceLandmarker(),
      navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30, min: 25 },
          facingMode: "user",
        },
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: false,
          autoGainControl: false,
        },
      }),
    ]);

    landmarker = lm;
    mediaStream = stream;
    mockVideoDims = null;
    videoEl.srcObject = stream;
    await videoEl.play();

    // S1->S2 (12:00): Browser VoicePlayer is the sole player so Chrome AEC cancels speaker output
    await voicePlayer.setEnabled(true);
    audioToggleBtn.textContent = "Voice: On";

    await micCapture.start(
      stream,
      (chunk) => {
        const consentedTarget = getConsentedTargetFace();
        const hop = hopPacker.packHop({
          pcm: chunk.pcm,
          tCapture: chunk.tCapture,
          targetFaceId: consentedTarget ? consentedTarget.id : null,
          faces: latestFaces,
          frameJpeg: latestFrameJpeg,
        });
        if (!hop) return;
        const sent = backend.sendHop(hop);
        if (!sent && backend.isConnected()) {
          hopPacker.recordDrop();
        }
      },
      hopPacker.getHopMs()
    );

    startBtn.textContent = "Camera On";
  } catch (err) {
    cameraErrorEl.textContent =
      err instanceof Error ? err.message : "Camera/mic unavailable";
    startBtn.disabled = false;
    startBtn.textContent = "Start Camera";
  }
}

// Wall clock: 28 px mono, seconds shown
function updateWallClock(): void {
  wallClockEl.textContent = new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "America/New_York",
  });
}
updateWallClock();
setInterval(updateWallClock, 500);
renderEngineReadout();

// Hide operator buttons (.camera-controls) and consent chips (.face-bar) after 3 s without mouse movement;
// show immediately when the mouse moves again.
let controlsIdleTimer: number | null = null;
function resetControlsIdleTimer(): void {
  stageEl.classList.remove("controls-idle");
  if (controlsIdleTimer !== null) {
    clearTimeout(controlsIdleTimer);
  }
  controlsIdleTimer = window.setTimeout(() => {
    stageEl.classList.add("controls-idle");
  }, 3000);
}
window.addEventListener("mousemove", resetControlsIdleTimer, { passive: true });
window.addEventListener("mousedown", resetControlsIdleTimer, { passive: true });
window.addEventListener("touchstart", resetControlsIdleTimer, { passive: true });
resetControlsIdleTimer();

function toggleBrightRoom(force?: boolean): void {
  brightMode = force !== undefined ? force : !brightMode;
  document.body.classList.toggle("bright-room", brightMode);
  brightBtn.textContent = brightMode ? "Dark [B]" : "Bright [B]";
  syncTargetHeaderBadge(tracker.getTargetFaceId());
  updateFaceBar(latestFaces, tracker.getTargetFaceId());
  renderCaptionLanes();
}

// Controls
startBtn.addEventListener("click", () => {
  void startLiveCapture();
});

canvasEl.addEventListener("click", (ev) => {
  const vw = mockVideoDims ? mockVideoDims[0] : videoEl.videoWidth;
  const vh = mockVideoDims ? mockVideoDims[1] : videoEl.videoHeight;
  const coords = canvasClickToNormalizedVideo(
    ev.clientX,
    ev.clientY,
    canvasEl,
    vw || CAMERA_W,
    vh || CAMERA_H
  );
  if (!coords) return;
  const res = tracker.tapAt(coords[0], coords[1]);
  // Tapping directly on an unconsented ("?") face grants consent and focuses them in one click
  if (res.targetFaceId) {
    const tapped = tracker.getFace(res.targetFaceId);
    if (tapped && !tapped.consent.given) {
      const updated = tracker.setConsent(res.targetFaceId, true, "operator");
      if (updated) {
        latestFaces = latestFaces.map((f) => (f.id === updated.id ? updated : f));
        backend.send({
          type: "set_consent",
          face_id: updated.id,
          consent: updated.consent,
          label: updated.label,
        });
        updateFaceBar(latestFaces, res.targetFaceId);
      }
    }
  }
  syncConsentedTargetState();
});

faceBarEl.addEventListener("click", (ev) => {
  const btn = (ev.target as HTMLElement).closest("button[data-face]") as HTMLButtonElement | null;
  if (!btn) return;
  const faceId = btn.dataset.face;
  if (!faceId) return;
  const current = tracker.getFace(faceId) ?? latestFaces.find((f) => f.id === faceId);
  if (!current) return;
  const nextConsent = !current.consent.given;
  const updated = tracker.setConsent(faceId, nextConsent, "operator");
  const nextFace = updated ?? {
    ...current,
    consent: nextConsent
      ? { given: true, by: "operator", time: new Date().toISOString() }
      : { given: false, by: null, time: null },
  };
  latestFaces = latestFaces.map((f) => (f.id === faceId ? nextFace : f));
  backend.send({
    type: "set_consent",
    face_id: nextFace.id,
    consent: nextFace.consent,
    label: nextFace.label,
  });
  updateFaceBar(latestFaces, tracker.getTargetFaceId());
  syncConsentedTargetState();
});

autoCenterBtn.addEventListener("click", () => {
  tracker.setTargetModeAuto();
  syncConsentedTargetState();
});

audioToggleBtn.addEventListener("click", async () => {
  const next = !voicePlayer.isEnabled();
  await voicePlayer.setEnabled(next);
  audioToggleBtn.textContent = next ? "Voice: On" : "Voice: Off";
});

replayBtn.addEventListener("click", () => {
  backend.send({ type: "replay_last_10s" });
});

brightBtn.addEventListener("click", () => {
  toggleBrightRoom();
});

saveTranscriptBtn.addEventListener("click", async () => {
  const sent = backend.send({ type: "save_transcript" });
  if (!sent) {
    await backend.saveTranscriptRest();
  }
});

memoryForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = memoryInput.value.trim();
  if (!q) return;
  lastQuestionAsked = q;
  memoryInput.value = "";
  memoryAnswerEl.innerHTML = `<div class="memory-q">${escapeHtml(q)}</div><div class="side-empty">Searching conversation...</div>`;
  const sent = backend.send({ type: "ask_memory", question: q });
  if (!sent) {
    const ans = await backend.askMemoryRest(q);
    if (ans) renderMemoryAnswer(ans);
  }
});

summaryBtn.addEventListener("click", () => {
  lastQuestionAsked = "Conversation summary";
  backend.send({ type: "request_summary" });
});

robotForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = robotInput.value.trim();
  if (!text) return;
  const targetId = tracker.getTargetFaceId() || "face-1";
  const frame = captureFullFrameBase64();
  robotInput.value = "";
  const sent = backend.send({
    type: "robot_command",
    face_id: targetId,
    text,
    frame_jpeg: frame,
  });
  if (!sent) {
    const res = await backend.triggerRobotCommandRest({
      face_id: targetId,
      text,
      target_face_id: targetId,
      frame_jpeg: frame,
    });
    if (res) {
      handleServerMessage({ type: "robot_command", payload: res });
    }
  }
});

async function openEndCard(refresh = true): Promise<void> {
  if (refresh) {
    const fetched = await backend.fetchEndCard();
    if (fetched) latestEndCard = fetched;
  }
  endCardContentEl.innerHTML = renderEndCardHtml(latestEndCard);
  endCardBackdropEl.classList.remove("hidden");
  document.getElementById("end-card-close")?.addEventListener("click", closeEndCard);
}

function closeEndCard(): void {
  endCardBackdropEl.classList.add("hidden");
}

endCardBtn.addEventListener("click", () => {
  void openEndCard(true);
});

window.addEventListener("keydown", (ev) => {
  if (
    document.activeElement instanceof HTMLInputElement ||
    document.activeElement instanceof HTMLTextAreaElement
  ) {
    return;
  }
  if (ev.key === "b" || ev.key === "B") {
    toggleBrightRoom();
  } else if (ev.key === "e" || ev.key === "E") {
    if (endCardBackdropEl.classList.contains("hidden")) {
      void openEndCard(true);
    } else {
      closeEndCard();
    }
  } else if (ev.key === "Escape") {
    closeEndCard();
  }
});

window.addEventListener("beforeunload", () => {
  if (rafId !== null) cancelAnimationFrame(rafId);
  micCapture.stop();
  voicePlayer.stop();
  backend.disconnect();
  mediaStream?.getTracks().forEach((t) => t.stop());
});

// Diagnostic & verification harness API for D1-D5 (no secrets)
(window as unknown as { __L2L__: unknown }).__L2L__ = {
  tracker,
  cropper,
  hopPacker,
  voicePlayer,
  backend,
  injectServerMessage: handleServerMessage,
  flushDelayMeter,
  toggleBrightRoom,
  openEndCard,
  closeEndCard,
  getFps: () => currentFps,
  getTrackingFps: () => currentTrackingFps,
  getLastTargetAnchor: () => lastTargetAnchor,
  getConsentedTargetFace,
  setSyntheticScene: (faces: Face[], targetId: string | null, dims: [number, number] = [1440, 640]) => {
    mockVideoDims = dims;
    latestFaces = faces.map((f) => ({
      ...f,
      is_target: targetId !== null && f.id === targetId,
    }));
    updateFaceBar(latestFaces, targetId);
    syncConsentedTargetState();
  },
};
