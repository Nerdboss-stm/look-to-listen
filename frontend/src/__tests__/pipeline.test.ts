import { describe, expect, it } from "vitest";
import {
  CLEARVOICE_C,
  computeClearVoiceCropRect,
  RESIZE_DIM,
  updateSmoothedBox,
} from "../vision/clearvoiceCrop";
import {
  extractRawFace,
  MultiFaceTracker,
  type RawFaceDetection,
} from "../vision/faceTracker";
import { encodeInt16ToBase64, HopPacker } from "../pipeline/hopPacker";
import { VoicePlayer } from "../audio/voicePlayer";
import { renderEndCardHtml } from "../ui/endCard";
import { renderQrSvg } from "../ui/qrSvg";
import { SPEAKER_PALETTE, speakerLetterForFaceId } from "../vision/faceTracker";
import type { EndCardData } from "../types/contracts";

function makeDet(cx: number, cy: number, w = 0.18, h = 0.28, mouthOpen = 0.05): RawFaceDetection {
  return {
    box: { x: cx - w / 2, y: cy - h / 2, w, h },
    lips: [
      [cx - 0.03, cy + 0.05],
      [cx + 0.03, cy + 0.05],
    ],
    mouth_open: mouthOpen,
  };
}

describe("E6: ClearVoice crop recipe", () => {
  it("computes exact ClearVoice square rows [y-s, y+s(1+2c)] and cols [x-s(1+c), x+s(1+c)]", () => {
    const state = updateSmoothedBox(
      undefined,
      { x: 0.4, y: 0.3, w: 0.2, h: 0.2 },
      1000,
      1000
    );
    expect(state.cx).toBeCloseTo(500, 4);
    expect(state.cy).toBeCloseTo(400, 4);
    expect(state.s).toBeCloseTo(100, 4);

    const rect = computeClearVoiceCropRect(state, 1000, 1000);
    // c = 0.4 => left = 500 - 140 = 360, top = 400 - 100 = 300, size = 280
    expect(rect.left).toBeCloseTo(500 - 100 * (1 + CLEARVOICE_C), 4);
    expect(rect.top).toBeCloseTo(400 - 100, 4);
    expect(rect.size).toBeCloseTo(280, 4);
    expect(rect.dstX).toBeCloseTo(0, 4);
    expect(rect.dstY).toBeCloseTo(0, 4);
    expect(rect.dstW).toBeCloseTo(RESIZE_DIM, 4);
    expect(rect.dstH).toBeCloseTo(RESIZE_DIM, 4);
  });

  it("zero-pads out-of-frame crops without distorting aspect ratio", () => {
    // Face right near the top-left corner
    const state = { cx: 60, cy: 50, s: 100 };
    const rect = computeClearVoiceCropRect(state, 1280, 720);
    expect(rect.left).toBeLessThan(0);
    expect(rect.top).toBeLessThan(0);
    expect(rect.srcX).toBe(0);
    expect(rect.srcY).toBe(0);
    expect(rect.dstX).toBeGreaterThan(0);
    expect(rect.dstY).toBeGreaterThan(0);
    expect(rect.dstW / rect.srcW).toBeCloseTo(RESIZE_DIM / rect.size, 4);
    expect(rect.dstH / rect.srcH).toBeCloseTo(RESIZE_DIM / rect.size, 4);
  });

  it("cuts 2.25x higher pixel-area crops at 1920x1080 than 1280x720 for a face at 1-2 m", () => {
    // Typical face at ~1.5 m: normalized box w=0.11, h=0.25
    const box = { x: 0.445, y: 0.25, w: 0.11, h: 0.25 };
    const s720 = updateSmoothedBox(undefined, box, 1280, 720);
    const s1080 = updateSmoothedBox(undefined, box, 1920, 1080);
    const r720 = computeClearVoiceCropRect(s720, 1280, 720);
    const r1080 = computeClearVoiceCropRect(s1080, 1920, 1080);
    // 1080 / 720 = 1.5x linear resolution -> 2.25x pixel area on lips!
    expect(r1080.size / r720.size).toBeCloseTo(1.5, 4);
    expect((r1080.size * r1080.size) / (r720.size * r720.size)).toBeCloseTo(2.25, 3);
  });
});

describe("E6: MultiFaceTracker (AT1)", () => {
  it("tracks 3 faces with stable IDs, distinct colors, default consent=false, and selects center face", () => {
    const tracker = new MultiFaceTracker();
    const frame1 = tracker.update(
      [makeDet(0.2, 0.5), makeDet(0.51, 0.49), makeDet(0.82, 0.52)],
      100
    );

    expect(frame1.faces).toHaveLength(3);
    const colors = new Set(frame1.faces.map((f) => f.color));
    expect(colors.size).toBe(3);
    expect(frame1.faces.every((f) => f.consent.given === false)).toBe(true);

    // Center face is the second detection (cx=0.51)
    const centerFace = frame1.faces.find((f) => Math.abs(f.box.x + f.box.w / 2 - 0.51) < 0.01)!;
    expect(frame1.targetFaceId).toBe(centerFace.id);

    // Next frame with slight motion keeps identical IDs
    const frame2 = tracker.update(
      [makeDet(0.21, 0.5), makeDet(0.50, 0.50), makeDet(0.81, 0.52)],
      133
    );
    expect(frame2.faces.map((f) => f.id).sort()).toEqual(
      frame1.faces.map((f) => f.id).sort()
    );
    expect(frame2.targetFaceId).toBe(centerFace.id);
    expect(frame2.targetChanged).toBe(false);
  });

  it("extracts lip landmarks and mouth_open ratio from MediaPipe landmarks", () => {
    const lms = Array.from({ length: 468 }, () => ({ x: 0.5, y: 0.5, z: 0, visibility: 1 }));
    lms[13] = { x: 0.5, y: 0.50, z: 0, visibility: 1 };
    lms[14] = { x: 0.5, y: 0.53, z: 0, visibility: 1 };
    lms[61] = { x: 0.45, y: 0.515, z: 0, visibility: 1 };
    lms[291] = { x: 0.55, y: 0.515, z: 0, visibility: 1 };
    const raw = extractRawFace(lms);
    expect(raw.mouth_open).toBeCloseTo(0.3, 2);
    expect(raw.lips.length).toBeGreaterThan(20);
  });
});

describe("E6: HopPacker (2 hops/sec, 12-13 crops, drop stale hops)", () => {
  it("packs 8000-sample int16 PCM and 12-13 crops at 2 hops/sec", () => {
    const packer = new HopPacker("sess-test", 500);
    const pcm = new Int16Array(8000);
    for (let i = 0; i < 8000; i++) pcm[i] = Math.round(Math.sin(i * 0.1) * 10000);

    let lastHop = null;
    for (let h = 0; h < 6; h++) {
      const baseT = 10000 + h * 500;
      for (let f = 0; f < 13; f++) {
        packer.pushTargetCrop("/9j/4AAQSkZJRgABAQAAAQABAAD/", baseT + f * 40);
      }
      lastHop = packer.packHop({
        pcm,
        tCapture: baseT + 500,
        targetFaceId: "face-1",
        faces: [],
        nowMs: baseT + 510,
      });
      expect(lastHop).not.toBeNull();
      expect(lastHop!.seq).toBe(h);
      expect(lastHop!.reset).toBe(h === 0);
      expect(lastHop!.crops.length).toBeGreaterThanOrEqual(12);
      expect(lastHop!.crops.length).toBeLessThanOrEqual(14);
      // 8000 int16 samples = 16000 bytes -> ceil(16000/3)*4 = 21336 base64 chars
      expect(lastHop!.pcm.length).toBe(21336);
    }

    const stats = packer.getStats(10000 + 6 * 500 + 10);
    expect(stats.hopsSent).toBe(6);
    expect(stats.hopsDropped).toBe(0);
    // Strict 12 or 13 crops check per 500ms hop
    for (let f = 0; f < 20; f++) {
      packer.pushTargetCrop("/9j/4AAQSkZJRgABAQAAAQABAAD/", 20000 + f * 25, "face-1");
    }
    const cappedHop = packer.packHop({
      pcm,
      tCapture: 20500,
      targetFaceId: "face-1",
      faces: [],
      nowMs: 20510,
    })!;
    expect(cappedHop.crops.length).toBeGreaterThanOrEqual(12);
    expect(cappedHop.crops.length).toBeLessThanOrEqual(13);
  });

  it("re-identifies a face within 2 s near where lost (carrying ID & consent) and holds target up to 1 s", () => {
    const tracker = new MultiFaceTracker();
    let t = 1000;

    // 1. Track face-1 at center and grant consent
    const s1 = tracker.update([makeDet(0.5, 0.5)], t);
    expect(s1.targetFaceId).toBe("face-1");
    tracker.setConsent("face-1", true, "operator");
    expect(tracker.getFace("face-1")!.consent.given).toBe(true);

    // 2. Also add unconsented face-2 on the left
    t += 40;
    tracker.update([makeDet(0.5, 0.5), makeDet(0.18, 0.5)], t);

    // 3. Briefly lose face-1 for 800 ms (<= 1 s): face-1 MUST remain target and stay in step.faces!
    t += 800;
    const held = tracker.update([makeDet(0.18, 0.5)], t);
    expect(held.targetFaceId).toBe("face-1");
    const heldFace1 = held.faces.find((f) => f.id === "face-1");
    expect(heldFace1).toBeDefined();
    expect(heldFace1!.consent.given).toBe(true);

    // 4. Lose face-1 past 1.0 s (at 1.5 s total loss, no faces in frame): target releases to null,
    //    but track stays in memory up to 2.0 s
    t += 700; // 1500 ms since face-1 was last seen
    const released = tracker.update([], t);
    expect(released.targetFaceId).toBeNull();

    // 5. Face reappears at 1.8 s (< 2.0 s) shifted by +0.24 horizontally:
    //    MUST get old ID "face-1" and carry consent.given === true!
    t += 300; // 1800 ms since face-1 was last seen (<= 2000 ms)
    const reappeared = tracker.update([makeDet(0.74, 0.46)], t);
    expect(reappeared.faces).toHaveLength(1);
    expect(reappeared.faces[0].id).toBe("face-1");
    expect(reappeared.faces[0].consent.given).toBe(true);
    expect(reappeared.targetFaceId).toBe("face-1");

    // 6. Disappear for > 2.0 s (2500 ms): must NOT carry old ID/consent to a stranger later
    t += 2500;
    const afterExpiry = tracker.update([makeDet(0.5, 0.5)], t);
    expect(afterExpiry.faces[0].id).not.toBe("face-1");
    expect(afterExpiry.faces[0].consent.given).toBe(false);
  });

  it("achieves >= 95% hops with 12 or 13 crops over a 60 s run with intermittent brief dropouts", () => {
    const tracker = new MultiFaceTracker();
    const packer = new HopPacker("test-sim-60s", 500);
    const pcm = new Int16Array(8000);

    // Initial detection + consent at t = 0
    tracker.update([makeDet(0.5, 0.5)], 0);
    tracker.setConsent("face-1", true, "operator");

    const seenIds = new Set<string>();
    let totalHops = 0;
    let valid12Or13Hops = 0;
    let nextHopMs = 500;

    // 60 seconds at 30 fps (33.33 ms per frame) with realistic 400-800ms blinks/occlusions every 8s
    // plus one 1.4s look-away at t=32s
    for (let now = 33; now <= 60030; now += 33) {
      const inBriefDropout =
        (now >= 8000 && now <= 8650) ||
        (now >= 17000 && now <= 17800) ||
        (now >= 25000 && now <= 25500) ||
        (now >= 43000 && now <= 43750) ||
        (now >= 52000 && now <= 52600);
      const inMediumLookAway = now >= 32000 && now <= 33300; // 1.3 s (>1s target hold, <2s re-ID!)

      const dx = Math.sin(now / 1200) * 0.12;
      const dets =
        inBriefDropout || inMediumLookAway ? [] : [makeDet(0.5 + dx, 0.5)];
      const step = tracker.update(dets, now);
      for (const f of step.faces) seenIds.add(f.id);

      const consentedTarget = step.targetFaceId
        ? step.faces.find((f) => f.id === step.targetFaceId && f.consent.given) ?? null
        : null;

      if (consentedTarget && packer.shouldSampleTargetCrop(now)) {
        packer.pushTargetCrop("/9j/4AAQSkZJRgABAQAAAQABAAD/", now, consentedTarget.id);
      }

      if (now >= nextHopMs) {
        const hop = packer.packHop({
          pcm,
          tCapture: nextHopMs,
          targetFaceId: consentedTarget ? consentedTarget.id : null,
          faces: step.faces,
          nowMs: nextHopMs + 5,
        })!;
        totalHops++;
        if (hop.crops.length === 12 || hop.crops.length === 13) {
          valid12Or13Hops++;
        }
        nextHopMs += 500;
      }
    }

    expect(seenIds.size).toBe(1);
    expect(seenIds.has("face-1")).toBe(true);
    expect(totalHops).toBe(120);
    const ratio = valid12Or13Hops / totalHops;
    expect(ratio).toBeGreaterThanOrEqual(0.95);
  });

  it("drops stale hops older than one hop length instead of queueing", () => {
    const packer = new HopPacker("sess-stale", 500);
    const pcm = new Int16Array(8000);
    const dropped = packer.packHop({
      pcm,
      tCapture: 1000,
      targetFaceId: "face-1",
      faces: [],
      nowMs: 1650, // 650 ms old > 500 ms hopMs
    });
    expect(dropped).toBeNull();
    expect(packer.getStats(1650).hopsDropped).toBe(1);
    expect(encodeInt16ToBase64(new Int16Array([0, 0]))).toBe("AAAAAA==");
  });
});

describe("E13: Target switching (center face & tap-to-pin -> reset hop)", () => {
  it("switches via center face within 200 ms and triggers reset=true on the next hop (10/10 switches)", () => {
    const tracker = new MultiFaceTracker({ switchHysteresisMs: 120 });
    const packer = new HopPacker("sess-switch", 500);
    const pcm = new Int16Array(8000);

    // Initial frame: face-1 at center, face-2 on the right
    let t = 1000;
    const init = tracker.update([makeDet(0.5, 0.5), makeDet(0.82, 0.5)], t);
    const f1 = init.faces[0].id;
    const f2 = init.faces[1].id;
    expect(init.targetFaceId).toBe(f1);

    // Emit initial hop (reset=true)
    const hop0 = packer.packHop({ pcm, tCapture: t, targetFaceId: f1, faces: init.faces, nowMs: t + 5 })!;
    expect(hop0.reset).toBe(true);

    // Perform 10 alternating switches between face-1 and face-2 via realistic 30 fps camera pans
    let switches = 0;
    let panPos = 0; // 0 = face-1 centered (0.50, 0.82), 1 = face-2 centered (0.18, 0.50)
    for (let i = 0; i < 10; i++) {
      const wantF2 = i % 2 === 0;
      const targetPan = wantF2 ? 1 : 0;
      let switchedStep = null;

      // Smooth 4-frame pan (~133 ms) plus 5 frames holding on new target (~166 ms)
      for (let f = 1; f <= 9; f++) {
        t += 33;
        const frac = Math.min(1, f / 4);
        const cur = panPos + (targetPan - panPos) * frac;
        const x1 = 0.5 - 0.32 * cur;
        const x2 = 0.82 - 0.32 * cur;
        const step = tracker.update([makeDet(x1, 0.5), makeDet(x2, 0.5)], t);
        if (step.targetChanged) {
          switchedStep = step;
        }
      }
      panPos = targetPan;

      expect(switchedStep).not.toBeNull();
      expect(switchedStep!.targetFaceId).toBe(wantF2 ? f2 : f1);

      packer.markTargetSwitch(switchedStep!.targetFaceId);
      packer.pushTargetCrop("/9j/4AAQSkZJRgABAQAAAQABAAD/", t);
      const resetHop = packer.packHop({
        pcm,
        tCapture: t,
        targetFaceId: switchedStep!.targetFaceId,
        faces: switchedStep!.faces,
        nowMs: t + 10,
      })!;
      expect(resetHop.reset).toBe(true);
      expect(resetHop.target_face_id).toBe(wantF2 ? f2 : f1);

      // Next hop on the same target must have reset=false
      t += 500;
      const followHop = packer.packHop({
        pcm,
        tCapture: t,
        targetFaceId: switchedStep!.targetFaceId,
        faces: switchedStep!.faces,
        nowMs: t + 10,
      })!;
      expect(followHop.reset).toBe(false);
      switches++;
    }
    expect(switches).toBe(10);
  });

  it("pins target immediately on tap and unpins back to auto on second tap", () => {
    const tracker = new MultiFaceTracker();
    const step = tracker.update([makeDet(0.5, 0.5), makeDet(0.8, 0.5)], 100);
    const f2 = step.faces[1];

    const tap1 = tracker.tapAt(0.8, 0.5);
    expect(tap1.targetChanged).toBe(true);
    expect(tap1.targetFaceId).toBe(f2.id);
    expect(tap1.targetMode).toBe("pinned");

    const tap2 = tracker.tapAt(0.8, 0.5);
    expect(tap2.targetMode).toBe("auto");
  });
});

describe("E14 & E23: DESIGN.md tokens, speaker letters, QR & END CARD truthfulness", () => {
  it("maps faces to DESIGN.md speaker tokens and letter badges A, B, C", () => {
    expect(SPEAKER_PALETTE[0]).toBe("#FFB000");
    expect(SPEAKER_PALETTE[1]).toBe("#4CC3FF");
    expect(SPEAKER_PALETTE[2]).toBe("#FF7AB6");
    expect(speakerLetterForFaceId("face-1")).toBe("A");
    expect(speakerLetterForFaceId("face-2")).toBe("B");
    expect(speakerLetterForFaceId("face-3")).toBe("C");
    const svg = renderQrSvg("https://github.com/saran/look-to-listen", 132);
    expect(svg).toContain("<svg");
    expect(svg).toContain('width="132"');
  });

  it("mutes VoicePlayer when there is no consented target and unmutes when target is consented", () => {
    const vp = new VoicePlayer();
    expect(vp.isTargetMuted()).toBe(true);
    expect(vp.isOutputActive()).toBe(false);
    vp.setTargetMuted(false);
    expect(vp.isTargetMuted()).toBe(false);
    vp.setTargetMuted(true);
    expect(vp.isTargetMuted()).toBe(true);
    expect(vp.isOutputActive()).toBe(false);
  });

  it("renders END CARD honestly from CSVs and .env REPO_URL without guessing", () => {
    const emptyHtml = renderEndCardHtml(null, "");
    expect(emptyHtml).toContain("Look to Listen. Hear only who you look at.");
    expect(emptyHtml).toContain("Where it breaks: awaiting Set C clips in clips.csv.");
    expect(emptyHtml).not.toContain("github.com/saran/look-to-listen");
    expect(emptyHtml).not.toContain("<svg");
    expect(emptyHtml).not.toContain("--");

    const sample: EndCardData = {
      updated_at: "2026-11-21T16:00:00-05:00",
      set_c: {
        n_clips: 40,
        b0_leak_pct: 48.2,
        b0_wer_pct: 31.0,
        engine_a_leak_pct: 22.4,
        engine_a_wer_pct: 26.5,
        engine_b_leak_pct: 9.8,
        engine_b_wer_pct: 18.2,
        beats_raw_gate_passed: true,
      },
      set_d: { n_windows: 240, accuracy_at_0_9_pct: 93.5, latency_p50_ms: 195 },
      set_r: { n_pairs: 10, point_correct: 9, hook_denied_other: 10 },
      delay: { voice_p50_ms: 1080, voice_p95_ms: 1410, caption_p50_ms: 2150, hops_logged: 640 },
      where_it_breaks: [
        {
          slice: "Talkers",
          condition: "3 talkers",
          n: 10,
          raw_leak_pct: 64.0,
          target_leak_pct: 21.5,
          target_wer_pct: 28.0,
          delay_p50_ms: 1120,
        },
      ],
      repo_url: "https://github.com/saran/look-to-listen", // old guessed fallback must be ignored when .env REPO_URL is unset
    };
    const htmlNoEnv = renderEndCardHtml(sample, "");
    expect(htmlNoEnv).toContain("48%/10%");
    expect(htmlNoEnv).toContain("1.08s");
    expect(htmlNoEnv).toContain("40");
    expect(htmlNoEnv).toContain("3 talkers");
    expect(htmlNoEnv).not.toContain("github.com/saran/look-to-listen");

    const htmlWithEnv = renderEndCardHtml(sample, "https://github.com/real-org/look-to-listen");
    expect(htmlWithEnv).toContain("github.com/real-org/look-to-listen");
    expect(htmlWithEnv).toContain("<svg");
  });
});
