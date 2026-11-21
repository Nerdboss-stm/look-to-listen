/**
 * ClearVoice AV_MossFormer2_TSE_16K face crop recipe (SPEC.md):
 * - Smoothed face box, center (cx, cy), half-size s = max(w, h) / 2
 * - Crop rows: [cy - s, cy + s * (1 + 2c)]
 * - Crop cols: [cx - s * (1 + c), cx + s * (1 + c)] with c = 0.4
 * - Pad frame first so out-of-bounds areas stay zero-padded without distortion
 * - Resize crop to 224x224
 * - Convert to grayscale (BT.601 luma matching cv2.COLOR_BGR2GRAY)
 * - Center crop 112x112 (pixels [56..168) x [56..168))
 * - Encode as JPEG (server decodes grayscale and normalizes (x/255 - 0.4161) / 0.1688)
 */

import type { FaceBox } from "../types/contracts";

export const CLEARVOICE_C = 0.4;
export const RESIZE_DIM = 224;
export const CROP_DIM = 112;
export const CENTER_OFFSET = (RESIZE_DIM - CROP_DIM) / 2; // 56

export interface SmoothedBoxState {
  cx: number;
  cy: number;
  s: number;
}

export interface CropRect {
  left: number;
  top: number;
  size: number;
  // Clipped source region within [0, frameW] x [0, frameH]
  srcX: number;
  srcY: number;
  srcW: number;
  srcH: number;
  // Destination region inside the 224x224 padded canvas
  dstX: number;
  dstY: number;
  dstW: number;
  dstH: number;
}

/**
 * Exponential moving average smoother for ClearVoice face boxes.
 * Smooths cx, cy, and half-size s independently per face track.
 */
export function updateSmoothedBox(
  prev: SmoothedBoxState | undefined,
  box: FaceBox,
  frameW: number,
  frameH: number,
  alpha = 0.35
): SmoothedBoxState {
  const x1 = box.x * frameW;
  const y1 = box.y * frameH;
  const bw = box.w * frameW;
  const bh = box.h * frameH;
  const cx = x1 + bw / 2;
  const cy = y1 + bh / 2;
  const s = Math.max(bw, bh) / 2;

  if (!prev) {
    return { cx, cy, s };
  }
  return {
    cx: prev.cx + alpha * (cx - prev.cx),
    cy: prev.cy + alpha * (cy - prev.cy),
    s: prev.s + alpha * (s - prev.s),
  };
}

/**
 * Computes exact padded ClearVoice source and destination rectangles
 * so out-of-frame bounds are zero-padded rather than stretched by Canvas2D.
 */
export function computeClearVoiceCropRect(
  state: SmoothedBoxState,
  frameW: number,
  frameH: number,
  c = CLEARVOICE_C,
  targetDim = RESIZE_DIM
): CropRect {
  const s = Math.max(state.s, 4);
  const left = state.cx - s * (1 + c);
  const top = state.cy - s;
  const right = state.cx + s * (1 + c);
  const bottom = state.cy + s * (1 + 2 * c);
  // Both width and height equal 2 * s * (1 + c) = 2.8 * s
  const size = Math.max(right - left, bottom - top);

  const srcLeft = Math.max(0, left);
  const srcTop = Math.max(0, top);
  const srcRight = Math.min(frameW, left + size);
  const srcBottom = Math.min(frameH, top + size);

  const srcW = Math.max(0, srcRight - srcLeft);
  const srcH = Math.max(0, srcBottom - srcTop);

  const scale = targetDim / size;
  const dstX = (srcLeft - left) * scale;
  const dstY = (srcTop - top) * scale;
  const dstW = srcW * scale;
  const dstH = srcH * scale;

  return {
    left,
    top,
    size,
    srcX: srcLeft,
    srcY: srcTop,
    srcW,
    srcH,
    dstX,
    dstY,
    dstW,
    dstH,
  };
}

/**
 * Reusable offscreen canvas pipeline for zero-allocation ClearVoice crops at 25 fps.
 */
export class ClearVoiceCropper {
  private readonly resizeCanvas: HTMLCanvasElement;
  private readonly resizeCtx: CanvasRenderingContext2D;
  private readonly cropCanvas: HTMLCanvasElement;
  private readonly cropCtx: CanvasRenderingContext2D;
  private readonly smoothByFace = new Map<string, SmoothedBoxState>();
  private readonly jpegQuality: number;
  public lastSourceDims: [number, number] = [0, 0];
  public lastSourceCropPx = 0;

  constructor(jpegQuality = 0.8) {
    this.jpegQuality = jpegQuality;
    this.resizeCanvas = document.createElement("canvas");
    this.resizeCanvas.width = RESIZE_DIM;
    this.resizeCanvas.height = RESIZE_DIM;
    const rCtx = this.resizeCanvas.getContext("2d", { alpha: false });
    if (!rCtx) throw new Error("Failed to create 224x224 2D context");
    rCtx.imageSmoothingEnabled = true;
    rCtx.imageSmoothingQuality = "high";
    this.resizeCtx = rCtx;

    this.cropCanvas = document.createElement("canvas");
    this.cropCanvas.width = CROP_DIM;
    this.cropCanvas.height = CROP_DIM;
    const cCtx = this.cropCanvas.getContext("2d", { alpha: false });
    if (!cCtx) throw new Error("Failed to create 112x112 2D context");
    cCtx.imageSmoothingEnabled = true;
    cCtx.imageSmoothingQuality = "high";
    this.cropCtx = cCtx;
  }

  resetFace(faceId: string): void {
    this.smoothByFace.delete(faceId);
  }

  resetAll(): void {
    this.smoothByFace.clear();
  }

  /**
   * Produces a base64-encoded 112x112 grayscale JPEG (without data URI prefix)
   * ready for Hop.crops and ClearVoice AV_MossFormer2_TSE_16K.
   */
  extractBase64Jpeg(
    source: HTMLVideoElement | HTMLCanvasElement,
    faceId: string,
    box: FaceBox
  ): string | null {
    const frameW =
      source instanceof HTMLVideoElement ? source.videoWidth : source.width;
    const frameH =
      source instanceof HTMLVideoElement ? source.videoHeight : source.height;
    if (frameW <= 0 || frameH <= 0) return null;

    const smoothed = updateSmoothedBox(
      this.smoothByFace.get(faceId),
      box,
      frameW,
      frameH
    );
    this.smoothByFace.set(faceId, smoothed);

    const rect = computeClearVoiceCropRect(smoothed, frameW, frameH);
    if (rect.srcW < 2 || rect.srcH < 2) return null;
    this.lastSourceDims = [frameW, frameH];
    this.lastSourceCropPx = Math.round(rect.size);

    // 1. Zero-padded 224x224 crop from full-resolution source (e.g. 1920x1080) on GPU
    this.resizeCtx.fillStyle = "#000000";
    this.resizeCtx.fillRect(0, 0, RESIZE_DIM, RESIZE_DIM);
    this.resizeCtx.drawImage(
      source,
      rect.srcX,
      rect.srcY,
      rect.srcW,
      rect.srcH,
      rect.dstX,
      rect.dstY,
      rect.dstW,
      rect.dstH
    );

    // 2. GPU-accelerated center crop 112x112 ([56..168) x [56..168)) + grayscale conversion
    // (avoids synchronous getImageData GPU->CPU readback stall at 1080p)
    this.cropCtx.filter = "grayscale(1)";
    this.cropCtx.drawImage(
      this.resizeCanvas,
      CENTER_OFFSET,
      CENTER_OFFSET,
      CROP_DIM,
      CROP_DIM,
      0,
      0,
      CROP_DIM,
      CROP_DIM
    );
    this.cropCtx.filter = "none";

    // 3. Encode as JPEG and strip "data:image/jpeg;base64,"
    const dataUrl = this.cropCanvas.toDataURL("image/jpeg", this.jpegQuality);
    const commaIdx = dataUrl.indexOf(",");
    return commaIdx >= 0 ? dataUrl.slice(commaIdx + 1) : dataUrl;
  }
}
