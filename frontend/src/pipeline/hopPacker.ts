/**
 * Packs 0.5 s audio hops + 25 fps ClearVoice target face crops into
 * contracts/hop.schema.json payloads.
 *
 * Enforces SPEC & AGENTS.md rules:
 * - 12 or 13 face crops per 0.5 s hop (25 fps = 40 ms crop cadence)
 * - reset=true on first hop or whenever target_face_id switches
 * - Never queues stale hops: drops hops older than one hop length
 */

import type { Face, Hop } from "../types/contracts";

export function encodeInt16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

export interface HopPackerStats {
  seq: number;
  hopsSent: number;
  hopsDropped: number;
  lastCropCount: number;
  lastPayloadBytes: number;
  hopsPerSec: number;
}

export class HopPacker {
  public readonly sessionId: string;
  private seq = 0;
  private hopsSent = 0;
  private hopsDropped = 0;
  private lastCropCount = 0;
  private lastPayloadBytes = 0;
  private hopMs: number;

  private pendingReset = true;
  private lastTargetFaceId: string | null = null;
  private targetCrops: string[] = [];
  private lastTargetCropFallback: { faceId: string; crop: string } | null = null;
  private otherCrops = new Map<string, string[]>();
  private lastCropTimeMs = 0;
  private lastOtherCropTimeMs = 0;
  private readonly cropIntervalMs = 40; // 25 fps -> 12 or 13 crops per 500 ms hop
  private readonly otherCropIntervalMs = 200; // 5 fps for Decision 1 on non-target faces
  private readonly recentHopTimes: number[] = [];

  constructor(sessionId?: string, hopMs = 500) {
    this.sessionId =
      sessionId ?? `sess-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    this.hopMs = hopMs;
  }

  setHopMs(hopMs: number): void {
    this.hopMs = hopMs;
  }

  getHopMs(): number {
    return this.hopMs;
  }

  /**
   * Call on target switch so the next emitted hop sends reset=true
   * and discards any stale face crops from the previous target.
   */
  markTargetSwitch(newTargetFaceId: string | null): void {
    if (newTargetFaceId !== this.lastTargetFaceId) {
      this.lastTargetFaceId = newTargetFaceId;
      this.pendingReset = true;
      this.targetCrops = [];
      this.lastTargetCropFallback = null;
    }
  }

  /**
   * Returns true if >= 40 ms has elapsed since the last 25 fps target crop.
   */
  shouldSampleTargetCrop(nowMs: number): boolean {
    return nowMs - this.lastCropTimeMs >= this.cropIntervalMs - 2;
  }

  shouldSampleOtherCrops(nowMs: number): boolean {
    return nowMs - this.lastOtherCropTimeMs >= this.otherCropIntervalMs - 2;
  }

  pushTargetCrop(base64Jpeg: string, nowMs: number, faceId?: string): void {
    this.lastCropTimeMs = nowMs;
    const maxCrops = Math.ceil((this.hopMs / 1000) * 25); // 13 for 500ms, 25 for 1000ms
    if (this.targetCrops.length >= maxCrops) {
      this.targetCrops.shift();
    }
    this.targetCrops.push(base64Jpeg);
    const effId = faceId ?? this.lastTargetFaceId;
    if (effId) {
      this.lastTargetCropFallback = { faceId: effId, crop: base64Jpeg };
    }
  }

  pushOtherCrop(faceId: string, base64Jpeg: string, nowMs: number): void {
    this.lastOtherCropTimeMs = nowMs;
    let arr = this.otherCrops.get(faceId);
    if (!arr) {
      arr = [];
      this.otherCrops.set(faceId, arr);
    }
    if (arr.length >= 6) arr.shift();
    arr.push(base64Jpeg);
  }

  /**
   * Packs a Hop payload when a 500 ms PCM chunk arrives.
   * Returns null and increments hopsDropped if the hop is already stale (> hopMs old).
   */
  packHop(params: {
    pcm: Int16Array;
    tCapture: number;
    targetFaceId: string | null;
    faces: Face[];
    frameJpeg?: string | null;
    nowMs?: number;
  }): Hop | null {
    const now = params.nowMs ?? Date.now();
    // Stale hop check: live beats complete (AGENTS.md)
    if (now - params.tCapture > this.hopMs) {
      this.hopsDropped++;
      this.targetCrops = [];
      this.otherCrops.clear();
      return null;
    }

    if (params.targetFaceId !== this.lastTargetFaceId) {
      this.lastTargetFaceId = params.targetFaceId;
      this.pendingReset = true;
      if (this.lastTargetCropFallback?.faceId !== params.targetFaceId) {
        this.lastTargetCropFallback = null;
      }
    }

    // Strictly 12 or 13 crops for a 500 ms hop when a consented target is active
    const expectedMin = Math.floor((this.hopMs / 1000) * 25); // 12 for 500ms
    const expectedMax = Math.ceil((this.hopMs / 1000) * 25); // 13 for 500ms
    let crops =
      params.targetFaceId !== null ? this.targetCrops.slice(-expectedMax) : [];
    if (
      params.targetFaceId !== null &&
      crops.length === 0 &&
      this.lastTargetCropFallback?.faceId === params.targetFaceId
    ) {
      crops = [this.lastTargetCropFallback.crop];
    }
    if (crops.length > 0 && crops.length < expectedMin) {
      const last = crops[crops.length - 1];
      while (crops.length < expectedMin) {
        crops.push(last);
      }
    }

    const otherCropsObj: Record<string, string[]> = {};
    for (const [fid, arr] of this.otherCrops.entries()) {
      if (fid !== params.targetFaceId && arr.length > 0) {
        otherCropsObj[fid] = arr;
      }
    }

    const hop: Hop = {
      session_id: this.sessionId,
      seq: this.seq++,
      target_face_id: params.targetFaceId,
      reset: this.pendingReset,
      pcm: encodeInt16ToBase64(params.pcm),
      crops,
      t_capture: params.tCapture,
      sample_rate: 16000,
      hop_ms: this.hopMs,
      faces: params.faces,
      ...(Object.keys(otherCropsObj).length > 0 ? { other_crops: otherCropsObj } : {}),
      ...(params.frameJpeg ? { frame_jpeg: params.frameJpeg } : {}),
    };

    this.pendingReset = false;
    this.targetCrops = [];
    this.otherCrops.clear();
    this.lastCropCount = crops.length;
    this.hopsSent++;
    this.recentHopTimes.push(now);
    const cutoff = now - 5000;
    while (this.recentHopTimes.length > 0 && this.recentHopTimes[0] < cutoff) {
      this.recentHopTimes.shift();
    }

    // Approximate serialized size for telemetry
    this.lastPayloadBytes =
      hop.pcm.length + crops.reduce((acc, c) => acc + c.length, 0) + 256;

    return hop;
  }

  recordDrop(): void {
    this.hopsDropped++;
  }

  getStats(nowMs = Date.now()): HopPackerStats {
    const cutoff = nowMs - 5000;
    while (this.recentHopTimes.length > 0 && this.recentHopTimes[0] < cutoff) {
      this.recentHopTimes.shift();
    }
    let hopsPerSec = 0;
    if (this.recentHopTimes.length >= 2) {
      const spanS =
        (this.recentHopTimes[this.recentHopTimes.length - 1] -
          this.recentHopTimes[0]) /
        1000;
      hopsPerSec = spanS > 0.2 ? (this.recentHopTimes.length - 1) / spanS : 0;
    }
    return {
      seq: this.seq,
      hopsSent: this.hopsSent,
      hopsDropped: this.hopsDropped,
      lastCropCount: this.lastCropCount,
      lastPayloadBytes: this.lastPayloadBytes,
      hopsPerSec: Number(hopsPerSec.toFixed(2)),
    };
  }
}
