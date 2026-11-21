/**
 * MediaPipe Tasks Vision Face Landmarker + stable multi-face tracking,
 * speaker color assignment, mouth-open ratio, target selection (center or tap),
 * 2-second re-identification of lost faces (preserving ID & consent),
 * 1-second target hold through brief losses, and consent records.
 *
 * Runs strictly in the 30 fps browser loop with zero model API calls (AGENTS.md).
 * Model file: /models/face_landmarker.task (copied from ../gemini4-prep/models/).
 */

import {
  FaceLandmarker,
  FilesetResolver,
  type NormalizedLandmark,
} from "@mediapipe/tasks-vision";
import type { Face, FaceBox, FaceConsent } from "../types/contracts";

// DESIGN.md speaker tokens (Dark default; Bright mode maps A/B/C via speakerLetterForFaceId)
export const SPEAKER_PALETTE = [
  "#FFB000", // speaker A
  "#4CC3FF", // speaker B
  "#FF7AB6", // speaker C
  "#34D399", // speaker D (4th face slot)
] as const;

export const SPEAKER_PALETTE_BRIGHT = [
  "#B25E00", // speaker A (bright room)
  "#0060A8", // speaker B (bright room)
  "#B0245F", // speaker C (bright room)
  "#067647", // speaker D (bright room)
] as const;

export const SPEAKER_LETTERS = ["A", "B", "C", "D"] as const;

export function speakerIndexForFaceId(faceId: string | null | undefined): number {
  if (!faceId) return 0;
  const m = /(\d+)$/.exec(faceId);
  if (!m) return 0;
  const n = Math.max(1, parseInt(m[1], 10));
  return (n - 1) % 4;
}

export function speakerLetterForFaceId(faceId: string | null | undefined): string {
  return SPEAKER_LETTERS[speakerIndexForFaceId(faceId)];
}

export function speakerColorForFaceId(
  faceId: string | null | undefined,
  brightMode = false
): string {
  const idx = speakerIndexForFaceId(faceId);
  return brightMode ? SPEAKER_PALETTE_BRIGHT[idx] : SPEAKER_PALETTE[idx];
}

// MediaPipe 468-landmark outer + inner lip indices
const LIP_INDICES = [
  61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
  308, 324, 318, 402, 317, 14, 87, 178, 88, 95,
  78, 191, 80, 81, 82, 13, 312, 311, 310, 415,
];

const UPPER_INNER_LIP = 13;
const LOWER_INNER_LIP = 14;
const LEFT_MOUTH_CORNER = 61;
const RIGHT_MOUTH_CORNER = 291;

export interface RawFaceDetection {
  box: FaceBox;
  lips: [number, number][];
  mouth_open: number;
}

interface TrackEntry {
  id: string;
  color: string;
  box: FaceBox;
  lips: [number, number][];
  mouth_open: number;
  consent: FaceConsent;
  label: string | null;
  lastSeenMs: number;
}

export type TargetMode = "auto" | "pinned";

export interface TrackerStepResult {
  faces: Face[];
  targetFaceId: string | null;
  targetChanged: boolean;
  targetMode: TargetMode;
}

export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/**
 * Extracts normalized bounding box, lip contour points, and mouth-open ratio
 * from one MediaPipe FaceLandmarker face landmark list.
 */
export function extractRawFace(landmarks: NormalizedLandmark[]): RawFaceDetection {
  let minX = 1;
  let minY = 1;
  let maxX = 0;
  let maxY = 0;
  for (let i = 0; i < landmarks.length; i++) {
    const lm = landmarks[i];
    if (lm.x < minX) minX = lm.x;
    if (lm.y < minY) minY = lm.y;
    if (lm.x > maxX) maxX = lm.x;
    if (lm.y > maxY) maxY = lm.y;
  }

  minX = clamp01(minX);
  minY = clamp01(minY);
  maxX = clamp01(maxX);
  maxY = clamp01(maxY);

  const box: FaceBox = {
    x: minX,
    y: minY,
    w: clamp01(maxX - minX),
    h: clamp01(maxY - minY),
  };

  const lips: [number, number][] = [];
  for (const idx of LIP_INDICES) {
    const lm = landmarks[idx];
    if (lm) {
      lips.push([clamp01(lm.x), clamp01(lm.y)]);
    }
  }

  const up = landmarks[UPPER_INNER_LIP];
  const lo = landmarks[LOWER_INNER_LIP];
  const lc = landmarks[LEFT_MOUTH_CORNER];
  const rc = landmarks[RIGHT_MOUTH_CORNER];
  let mouthOpen = 0;
  if (up && lo && lc && rc) {
    const vert = Math.hypot(lo.x - up.x, lo.y - up.y);
    const horiz = Math.hypot(rc.x - lc.x, rc.y - lc.y);
    mouthOpen = horiz > 1e-4 ? Number((vert / horiz).toFixed(4)) : 0;
  }

  return { box, lips, mouth_open: mouthOpen };
}

function boxCenter(b: FaceBox): [number, number] {
  return [b.x + b.w / 2, b.y + b.h / 2];
}

function centerDistSq(b: FaceBox): number {
  const [cx, cy] = boxCenter(b);
  const dx = cx - 0.5;
  const dy = cy - 0.5;
  return dx * dx + dy * dy;
}

function boxIoU(a: FaceBox, b: FaceBox): number {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.w, b.x + b.w);
  const y2 = Math.min(a.y + a.h, b.y + b.h);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  if (inter <= 0) return 0;
  const union = a.w * a.h + b.w * b.h - inter;
  return union > 0 ? inter / union : 0;
}

/**
 * Pure multi-face tracker + target selector:
 * - Re-identifies a face reappearing within `reappearMs` (2000 ms) near where one was lost,
 *   restoring its old ID, color, and consent record.
 * - Keeps the current target held for up to `targetHoldMs` (1000 ms) when briefly lost.
 */
export class MultiFaceTracker {
  private readonly tracks = new Map<string, TrackEntry>();
  private nextTrackNum = 1;
  private targetFaceId: string | null = null;
  private targetMode: TargetMode = "auto";
  private candidateTargetId: string | null = null;
  private candidateSinceMs = 0;

  private readonly switchHysteresisMs: number;
  private readonly switchMargin: number;
  private readonly targetHoldMs: number;
  private readonly reappearMs: number;
  private readonly reappearDist: number;

  constructor(opts?: {
    switchHysteresisMs?: number;
    switchMargin?: number;
    targetHoldMs?: number;
    reappearMs?: number;
    reappearDist?: number;
    trackTimeoutMs?: number;
  }) {
    this.switchHysteresisMs = opts?.switchHysteresisMs ?? 120;
    this.switchMargin = opts?.switchMargin ?? 0.03;
    this.targetHoldMs = opts?.targetHoldMs ?? 1000; // 1 s target hold when briefly lost
    this.reappearMs = opts?.reappearMs ?? opts?.trackTimeoutMs ?? 2000; // 2 s re-ID with consent
    this.reappearDist = opts?.reappearDist ?? 0.38;
  }

  update(detections: RawFaceDetection[], nowMs: number): TrackerStepResult {
    // 0. Prune tracks lost for strictly more than reappearMs (2 s)
    for (const [id, t] of this.tracks.entries()) {
      if (nowMs - t.lastSeenMs > this.reappearMs) {
        this.tracks.delete(id);
      }
    }

    const unmatchedTracks = new Set(this.tracks.keys());
    const matchedDet = new Set<number>();

    // 1. Pass 1: associate live tracks (seen within the last 250 ms) by IoU + centroid proximity
    const livePairs: { trackId: string; detIdx: number; score: number }[] = [];
    for (const trackId of unmatchedTracks) {
      const t = this.tracks.get(trackId)!;
      if (nowMs - t.lastSeenMs > 250) continue;
      const [tcx, tcy] = boxCenter(t.box);
      for (let i = 0; i < detections.length; i++) {
        const d = detections[i];
        const [dcx, dcy] = boxCenter(d.box);
        const dist = Math.hypot(tcx - dcx, tcy - dcy);
        const iou = boxIoU(t.box, d.box);
        if (iou > 0.05 || dist < 0.32) {
          livePairs.push({ trackId, detIdx: i, score: iou * 2 - dist });
        }
      }
    }

    livePairs.sort((a, b) => b.score - a.score);
    for (const p of livePairs) {
      if (!unmatchedTracks.has(p.trackId) || matchedDet.has(p.detIdx)) continue;
      const t = this.tracks.get(p.trackId)!;
      const d = detections[p.detIdx];
      t.box = d.box;
      t.lips = d.lips;
      t.mouth_open = d.mouth_open;
      t.lastSeenMs = nowMs;
      unmatchedTracks.delete(p.trackId);
      matchedDet.add(p.detIdx);
    }

    // 2. Pass 2: re-identify recently lost tracks (within reappearMs = 2 s) near where lost.
    // Restores the old face ID, speaker color, and consent record!
    const reidPairs: { trackId: string; detIdx: number; score: number }[] = [];
    for (const trackId of unmatchedTracks) {
      const t = this.tracks.get(trackId)!;
      const ageMs = nowMs - t.lastSeenMs;
      if (ageMs > this.reappearMs) continue;
      const [tcx, tcy] = boxCenter(t.box);
      const maxDist = Math.max(this.reappearDist, Math.max(t.box.w, t.box.h) * 1.5);
      for (let i = 0; i < detections.length; i++) {
        if (matchedDet.has(i)) continue;
        const d = detections[i];
        const [dcx, dcy] = boxCenter(d.box);
        const dist = Math.hypot(tcx - dcx, tcy - dcy);
        const iou = boxIoU(t.box, d.box);
        if (dist <= maxDist || iou > 0.02) {
          // Prefer closer spatial match, with slight preference for consented tracks
          const consentBonus = t.consent.given ? 0.05 : 0;
          reidPairs.push({
            trackId,
            detIdx: i,
            score: iou * 2 - dist + consentBonus,
          });
        }
      }
    }

    reidPairs.sort((a, b) => b.score - a.score);
    for (const p of reidPairs) {
      if (!unmatchedTracks.has(p.trackId) || matchedDet.has(p.detIdx)) continue;
      const t = this.tracks.get(p.trackId)!;
      const d = detections[p.detIdx];
      t.box = d.box;
      t.lips = d.lips;
      t.mouth_open = d.mouth_open;
      t.lastSeenMs = nowMs;
      unmatchedTracks.delete(p.trackId);
      matchedDet.add(p.detIdx);
    }

    // 3. Pass 3: spawn new tracks only for genuinely new faces (up to 4 active/dormant slots)
    for (let i = 0; i < detections.length; i++) {
      if (matchedDet.has(i)) continue;
      if (this.tracks.size >= 4) {
        // Evict the oldest unmatched non-target track (prefer evicting unconsented first)
        let evictId: string | null = null;
        let evictScore = Infinity;
        for (const id of unmatchedTracks) {
          if (id === this.targetFaceId) continue;
          const t = this.tracks.get(id)!;
          const score = t.lastSeenMs + (t.consent.given ? 10000 : 0);
          if (score < evictScore) {
            evictScore = score;
            evictId = id;
          }
        }
        if (evictId) {
          this.tracks.delete(evictId);
          unmatchedTracks.delete(evictId);
        } else {
          continue;
        }
      }
      const id = `face-${this.nextTrackNum}`;
      const color =
        SPEAKER_PALETTE[(this.nextTrackNum - 1) % SPEAKER_PALETTE.length];
      this.nextTrackNum++;
      const d = detections[i];
      this.tracks.set(id, {
        id,
        color,
        box: d.box,
        lips: d.lips,
        mouth_open: d.mouth_open,
        consent: { given: false, by: null, time: null },
        label: null,
        lastSeenMs: nowMs,
      });
    }

    // 4. Visible tracks (seen in this frame or within 300 ms anti-flicker window)
    const activeTracks = Array.from(this.tracks.values()).filter(
      (t) => nowMs - t.lastSeenMs <= 300
    );

    // 5. Target selection with 1-second target hold when briefly lost
    const prevTarget = this.targetFaceId;
    const curTargetTrack = this.targetFaceId
      ? this.tracks.get(this.targetFaceId) ?? null
      : null;
    const targetLostMs = curTargetTrack ? nowMs - curTargetTrack.lastSeenMs : Infinity;
    const targetHeldBriefly =
      curTargetTrack !== null && targetLostMs > 0 && targetLostMs <= this.targetHoldMs;

    if (targetHeldBriefly) {
      // Target was briefly lost (<= 1 s): keep it as target without switching away!
      this.candidateTargetId = null;
    } else if (activeTracks.length === 0) {
      // Target lost for > 1 s (or never had a target) and no active faces
      this.targetFaceId = null;
      this.candidateTargetId = null;
      if (this.targetMode === "pinned") {
        this.targetMode = "auto";
      }
    } else if (this.targetMode === "pinned") {
      // Pinned target either visible right now, or lost > 1 s -> fall back to auto center
      if (!curTargetTrack || targetLostMs > this.targetHoldMs) {
        this.targetMode = "auto";
        this.targetFaceId = this.pickCenterFace(activeTracks);
      }
    } else {
      // Auto-center mode (with current target either visible now, or lost > 1 s)
      const bestCenterId = this.pickCenterFace(activeTracks);
      if (!curTargetTrack || targetLostMs > this.targetHoldMs) {
        this.targetFaceId = bestCenterId;
        this.candidateTargetId = null;
      } else if (bestCenterId === this.targetFaceId) {
        this.candidateTargetId = null;
      } else {
        const bestTrack = this.tracks.get(bestCenterId)!;
        const curDist = Math.sqrt(centerDistSq(curTargetTrack.box));
        const bestDist = Math.sqrt(centerDistSq(bestTrack.box));
        if (curDist - bestDist >= this.switchMargin) {
          if (this.candidateTargetId !== bestCenterId) {
            this.candidateTargetId = bestCenterId;
            this.candidateSinceMs = nowMs;
          } else if (nowMs - this.candidateSinceMs >= this.switchHysteresisMs) {
            this.targetFaceId = bestCenterId;
            this.candidateTargetId = null;
          }
        } else {
          this.candidateTargetId = null;
        }
      }
    }

    // Build output faces: active tracks plus the held target track if briefly lost (<= 1 s)
    const outputTracks = [...activeTracks];
    if (
      targetHeldBriefly &&
      curTargetTrack &&
      !outputTracks.some((t) => t.id === curTargetTrack.id)
    ) {
      outputTracks.push(curTargetTrack);
    }

    const faces: Face[] = outputTracks.map((t) => ({
      id: t.id,
      box: t.box,
      lips: t.lips,
      mouth_open: t.lastSeenMs === nowMs ? t.mouth_open : 0,
      color: t.color,
      consent: { ...t.consent },
      is_target: t.id === this.targetFaceId,
      label: t.label,
    }));

    return {
      faces,
      targetFaceId: this.targetFaceId,
      targetChanged: this.targetFaceId !== prevTarget,
      targetMode: this.targetMode,
    };
  }

  private pickCenterFace(tracks: TrackEntry[]): string {
    let bestId = tracks[0].id;
    let bestDist = centerDistSq(tracks[0].box);
    for (let i = 1; i < tracks.length; i++) {
      const d = centerDistSq(tracks[i].box);
      if (d < bestDist) {
        bestDist = d;
        bestId = tracks[i].id;
      }
    }
    return bestId;
  }

  /**
   * Tap/click on normalized frame coordinate (nx, ny) in [0, 1] to pin a face.
   * Tapping the already-pinned target returns to auto-center mode.
   */
  tapAt(nx: number, ny: number): { targetFaceId: string | null; targetChanged: boolean; targetMode: TargetMode } {
    const prevTarget = this.targetFaceId;
    for (const t of this.tracks.values()) {
      const b = t.box;
      if (nx >= b.x && nx <= b.x + b.w && ny >= b.y && ny <= b.y + b.h) {
        if (this.targetMode === "pinned" && this.targetFaceId === t.id) {
          this.targetMode = "auto";
          return { targetFaceId: this.targetFaceId, targetChanged: false, targetMode: "auto" };
        }
        this.targetMode = "pinned";
        this.targetFaceId = t.id;
        this.candidateTargetId = null;
        return {
          targetFaceId: this.targetFaceId,
          targetChanged: this.targetFaceId !== prevTarget,
          targetMode: "pinned",
        };
      }
    }
    return { targetFaceId: this.targetFaceId, targetChanged: false, targetMode: this.targetMode };
  }

  setTargetModeAuto(): void {
    this.targetMode = "auto";
    this.candidateTargetId = null;
  }

  pinFace(faceId: string): boolean {
    if (!this.tracks.has(faceId)) return false;
    const changed = this.targetFaceId !== faceId;
    this.targetFaceId = faceId;
    this.targetMode = "pinned";
    this.candidateTargetId = null;
    return changed;
  }

  setConsent(faceId: string, given: boolean, by = "operator", label?: string | null): Face | null {
    const t = this.tracks.get(faceId);
    if (!t) return null;
    t.consent = given
      ? { given: true, by, time: new Date().toISOString() }
      : { given: false, by: null, time: null };
    if (label !== undefined) {
      t.label = label;
    }
    return {
      id: t.id,
      box: t.box,
      lips: t.lips,
      mouth_open: t.mouth_open,
      color: t.color,
      consent: { ...t.consent },
      is_target: t.id === this.targetFaceId,
      label: t.label,
    };
  }

  getTargetFaceId(): string | null {
    return this.targetFaceId;
  }

  getTargetMode(): TargetMode {
    return this.targetMode;
  }

  getFace(faceId: string): Face | null {
    const t = this.tracks.get(faceId);
    if (!t) return null;
    return {
      id: t.id,
      box: t.box,
      lips: t.lips,
      mouth_open: t.mouth_open,
      color: t.color,
      consent: { ...t.consent },
      is_target: t.id === this.targetFaceId,
      label: t.label,
    };
  }
}

/**
 * Loads MediaPipe FaceLandmarker using the local WASM runtime and pre-downloaded
 * face_landmarker.task model (zero network fetches at the venue).
 * Uses forgiving detection/tracking thresholds (0.35 / 0.35 / 0.30) so dim venue
 * lighting, glasses, and 45-degree head turns stay continuously tracked.
 */
export async function createFaceLandmarker(opts?: {
  wasmPath?: string;
  modelAssetPath?: string;
  numFaces?: number;
}): Promise<FaceLandmarker> {
  const wasmPath = opts?.wasmPath ?? "/wasm";
  const modelAssetPath = opts?.modelAssetPath ?? "/models/face_landmarker.task";
  const numFaces = opts?.numFaces ?? 4;

  const vision = await FilesetResolver.forVisionTasks(wasmPath);
  const sharedOpts = {
    runningMode: "VIDEO" as const,
    numFaces,
    minFaceDetectionConfidence: 0.35,
    minFacePresenceConfidence: 0.35,
    minTrackingConfidence: 0.3,
    outputFaceBlendshapes: false,
    outputFacialTransformationMatrixes: false,
  };
  try {
    return await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath,
        delegate: "GPU",
      },
      ...sharedOpts,
    });
  } catch {
    return await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath,
        delegate: "CPU",
      },
      ...sharedOpts,
    });
  }
}
