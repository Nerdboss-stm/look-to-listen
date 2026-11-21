/**
 * Spotlight camera overlay & Robot mini-frame renderer (DESIGN.md):
 * - Dim: radial 35% black layer over everything outside the target's face box.
 *   No dim when there is no target.
 * - Target ring (when consented): 6 px in target's color, 2 px white inner stroke,
 *   24 px soft glow. Badge above it: "A · LISTENING".
 * - Other consented faces: 2 px ring at 60% opacity in their color, with letter badge ("B", "C").
 * - Face without consent: dashed gray ring, badge "?", and no captions for it.
 * - Target switch motion: ring and dim move to the new face over 300 ms, ease-out
 *   (instant when prefers-reduced-motion is active).
 * - One canvas, drawn with requestAnimationFrame. Zero model calls in the draw loop.
 */

import type { Face, RobotCommand } from "../types/contracts";
import {
  speakerColorForFaceId,
  speakerLetterForFaceId,
} from "../vision/faceTracker";

export interface OverlayState {
  faces: Face[];
  targetFaceId: string | null;
  brightMode: boolean;
  reducedMotion: boolean;
  nowMs: number;
}

export interface TargetAnchor {
  cx: number;
  cy: number;
  radius: number;
  color: string;
}

export function computeCoverTransform(
  videoW: number,
  videoH: number,
  canvasW: number,
  canvasH: number
): { scale: number; offsetX: number; offsetY: number } {
  if (videoW <= 0 || videoH <= 0 || canvasW <= 0 || canvasH <= 0) {
    return { scale: 1, offsetX: 0, offsetY: 0 };
  }
  const scale = Math.max(canvasW / videoW, canvasH / videoH);
  const drawnW = videoW * scale;
  const drawnH = videoH * scale;
  return {
    scale,
    offsetX: (canvasW - drawnW) / 2,
    offsetY: (canvasH - drawnH) / 2,
  };
}

export function canvasClickToNormalizedVideo(
  clientX: number,
  clientY: number,
  canvas: HTMLCanvasElement,
  videoW: number,
  videoH: number
): [number, number] | null {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0 || videoW <= 0 || videoH <= 0) {
    return null;
  }
  const px = (clientX - rect.left) * (canvas.width / rect.width);
  const py = (clientY - rect.top) * (canvas.height / rect.height);
  const { scale, offsetX, offsetY } = computeCoverTransform(
    videoW,
    videoH,
    canvas.width,
    canvas.height
  );
  const vx = (px - offsetX) / (videoW * scale);
  const vy = (py - offsetY) / (videoH * scale);
  if (vx < 0 || vx > 1 || vy < 0 || vy > 1) return null;
  return [vx, vy];
}

function easeOutCubic(t: number): number {
  const clamped = t < 0 ? 0 : t > 1 ? 1 : t;
  return 1 - Math.pow(1 - clamped, 3);
}

/**
 * Stateful 300 ms ease-out interpolator for the spotlight ring and radial dim.
 */
export class SpotlightAnimator {
  private lastTargetId: string | null = null;
  private fromX = 0;
  private fromY = 0;
  private fromR = 0;
  private curX = 0;
  private curY = 0;
  private curR = 0;
  private switchStartMs = 0;
  private initialized = false;

  step(
    goalX: number,
    goalY: number,
    goalR: number,
    targetId: string,
    nowMs: number,
    reducedMotion: boolean
  ): { x: number; y: number; r: number } {
    if (!this.initialized || reducedMotion) {
      this.initialized = true;
      this.lastTargetId = targetId;
      this.fromX = this.curX = goalX;
      this.fromY = this.curY = goalY;
      this.fromR = this.curR = goalR;
      this.switchStartMs = nowMs;
      return { x: goalX, y: goalY, r: goalR };
    }

    if (targetId !== this.lastTargetId) {
      this.lastTargetId = targetId;
      this.fromX = this.curX;
      this.fromY = this.curY;
      this.fromR = this.curR;
      this.switchStartMs = nowMs;
    }

    const elapsed = nowMs - this.switchStartMs;
    if (elapsed < 300) {
      const k = easeOutCubic(elapsed / 300);
      this.curX = this.fromX + (goalX - this.fromX) * k;
      this.curY = this.fromY + (goalY - this.fromY) * k;
      this.curR = this.fromR + (goalR - this.fromR) * k;
    } else {
      this.curX = goalX;
      this.curY = goalY;
      this.curR = goalR;
    }
    return { x: this.curX, y: this.curY, r: this.curR };
  }

  reset(): void {
    this.initialized = false;
    this.lastTargetId = null;
  }
}

function drawBadge(
  ctx: CanvasRenderingContext2D,
  text: string,
  cx: number,
  ringTopY: number,
  bgColor: string,
  textColor: string,
  borderColor: string,
  canvasW: number
): void {
  ctx.save();
  ctx.font = '700 20px "Atkinson Hyperlegible Next", Inter, sans-serif';
  const padX = 12;
  const h = 32;
  const tw = ctx.measureText(text).width;
  const w = Math.ceil(tw + padX * 2);
  const x = Math.max(8, Math.min(canvasW - w - 8, Math.round(cx - w / 2)));
  const y = Math.max(8, Math.round(ringTopY - h - 10));

  ctx.beginPath();
  ctx.roundRect(x, y, w, h, 6);
  ctx.fillStyle = bgColor;
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = borderColor;
  ctx.stroke();

  ctx.fillStyle = textColor;
  ctx.textBaseline = "middle";
  ctx.fillText(text, x + padX, y + h / 2 + 1);
  ctx.restore();
}

export function renderOverlay(
  ctx: CanvasRenderingContext2D,
  videoW: number,
  videoH: number,
  state: OverlayState,
  animator: SpotlightAnimator
): TargetAnchor | null {
  const W = ctx.canvas.width;
  const H = ctx.canvas.height;
  ctx.clearRect(0, 0, W, H);

  if (videoW <= 0 || videoH <= 0 || state.faces.length === 0) {
    if (!state.targetFaceId) animator.reset();
    return null;
  }

  const { scale, offsetX, offsetY } = computeCoverTransform(videoW, videoH, W, H);
  const toX = (nx: number) => offsetX + nx * videoW * scale;
  const toY = (ny: number) => offsetY + ny * videoH * scale;

  const targetFace = state.targetFaceId
    ? state.faces.find((f) => f.id === state.targetFaceId) ?? null
    : null;

  let anchor: TargetAnchor | null = null;

  // 1. Radial 35% black dim outside the target's face box (only when target exists)
  if (targetFace) {
    const tx = toX(targetFace.box.x);
    const ty = toY(targetFace.box.y);
    const tw = targetFace.box.w * videoW * scale;
    const th = targetFace.box.h * videoH * scale;
    const goalCx = tx + tw / 2;
    const goalCy = ty + th / 2;
    const goalR = Math.max(tw, th) * 0.58;

    const anim = animator.step(
      goalCx,
      goalCy,
      goalR,
      targetFace.id,
      state.nowMs,
      state.reducedMotion
    );

    const grad = ctx.createRadialGradient(
      anim.x,
      anim.y,
      anim.r * 0.88,
      anim.x,
      anim.y,
      anim.r * 1.45
    );
    grad.addColorStop(0, "rgba(0, 0, 0, 0)");
    grad.addColorStop(1, "rgba(0, 0, 0, 0.35)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    const tColor = targetFace.consent.given
      ? speakerColorForFaceId(targetFace.id, state.brightMode)
      : "#A9B4C2";
    anchor = { cx: anim.x, cy: anim.y, radius: anim.r, color: tColor };
  } else {
    animator.reset();
  }

  // 2. Non-target faces first (thin 2px ring at 60% opacity, or dashed gray "?" if no consent)
  for (const face of state.faces) {
    if (targetFace && face.id === targetFace.id) continue;

    const x = toX(face.box.x);
    const y = toY(face.box.y);
    const w = face.box.w * videoW * scale;
    const h = face.box.h * videoH * scale;
    const cx = x + w / 2;
    const cy = y + h / 2;
    const r = Math.max(w, h) * 0.56;

    ctx.save();
    if (!face.consent.given) {
      // Face without consent: dashed gray ring, badge "?"
      ctx.strokeStyle = "#A9B4C2";
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 6]);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      drawBadge(
        ctx,
        "?",
        cx,
        cy - r,
        state.brightMode ? "#F2F4F7" : "#10141A",
        state.brightMode ? "#475467" : "#A9B4C2",
        "#A9B4C2",
        W
      );
    } else {
      const color = speakerColorForFaceId(face.id, state.brightMode);
      const letter = speakerLetterForFaceId(face.id);
      ctx.globalAlpha = 0.6;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
      drawBadge(
        ctx,
        letter,
        cx,
        cy - r,
        state.brightMode ? "#F2F4F7" : "#10141A",
        state.brightMode ? "#0A0C10" : "#FFFFFF",
        color,
        W
      );
    }
    ctx.restore();
  }

  // 3. Target face ring on top
  if (targetFace && anchor) {
    ctx.save();
    if (!targetFace.consent.given) {
      // Non-consenting face even when centered: dashed gray ring, badge "?", no captions
      ctx.strokeStyle = "#A9B4C2";
      ctx.lineWidth = 3;
      ctx.setLineDash([10, 7]);
      ctx.beginPath();
      ctx.arc(anchor.cx, anchor.cy, anchor.radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      drawBadge(
        ctx,
        "?",
        anchor.cx,
        anchor.cy - anchor.radius,
        state.brightMode ? "#F2F4F7" : "#10141A",
        state.brightMode ? "#0A0C10" : "#FFFFFF",
        "#A9B4C2",
        W
      );
    } else {
      const color = speakerColorForFaceId(targetFace.id, state.brightMode);
      const letter = speakerLetterForFaceId(targetFace.id);

      // 6 px stroke in target's color + 24 px soft glow
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = 24;
      ctx.strokeStyle = color;
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.arc(anchor.cx, anchor.cy, anchor.radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // 2 px white inner stroke
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(anchor.cx, anchor.cy, Math.max(4, anchor.radius - 4), 0, Math.PI * 2);
      ctx.stroke();

      // Badge above ring: "A · LISTENING"
      drawBadge(
        ctx,
        `${letter} · LISTENING`,
        anchor.cx,
        anchor.cy - anchor.radius,
        color,
        state.brightMode ? "#FFFFFF" : "#07090C",
        "#FFFFFF",
        W
      );
    }
    ctx.restore();
  }

  return anchor;
}

/**
 * Renders the small live video frame + crosshair inside the ROBOT side-strip panel (DESIGN.md).
 */
export function renderRobotMiniFrame(
  ctx: CanvasRenderingContext2D,
  source: HTMLVideoElement | HTMLCanvasElement | null,
  sourceReady: boolean,
  cmd: RobotCommand | null,
  brightMode: boolean
): void {
  const W = ctx.canvas.width;
  const H = ctx.canvas.height;
  ctx.fillStyle = brightMode ? "#D0D5DD" : "#07090C";
  ctx.fillRect(0, 0, W, H);

  if (source && sourceReady) {
    const sw = source instanceof HTMLVideoElement ? source.videoWidth : source.width;
    const sh = source instanceof HTMLVideoElement ? source.videoHeight : source.height;
    if (sw > 0 && sh > 0) {
      const { scale, offsetX, offsetY } = computeCoverTransform(sw, sh, W, H);
      ctx.drawImage(source, offsetX, offsetY, sw * scale, sh * scale);
    }
  }

  if (cmd && cmd.allowed !== false && cmd.point) {
    const [py, px] = cmd.point;
    const cx = (px / 1000) * W;
    const cy = (py / 1000) * H;
    const color = brightMode ? "#0060A8" : "#FFB000";

    ctx.save();
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(cx, cy, 12, 0, Math.PI * 2);
    ctx.moveTo(cx - 18, cy);
    ctx.lineTo(cx + 18, cy);
    ctx.moveTo(cx, cy - 18);
    ctx.lineTo(cx, cy + 18);
    ctx.stroke();

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, 12, 0, Math.PI * 2);
    ctx.moveTo(cx - 18, cy);
    ctx.lineTo(cx + 18, cy);
    ctx.moveTo(cx, cy - 18);
    ctx.lineTo(cx, cy + 18);
    ctx.stroke();
    ctx.restore();
  }
}
