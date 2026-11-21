/**
 * Gapless Web Audio API playback for clean 16 kHz int16 PCM returned from
 * the separation server. Automatically mutes and flushes any queued audio
 * whenever there is no consented target face (preventing unguided separation playback).
 */

export function decodeBase64ToInt16(b64: string): Int16Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) {
    bytes[i] = bin.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
}

export class VoicePlayer {
  private ctx: AudioContext | null = null;
  private gainNode: GainNode | null = null;
  private readonly activeSources = new Set<AudioBufferSourceNode>();
  private nextStartTime = 0;
  private enabled = false;
  private targetMuted = true; // Muted until a consented target face is active
  private readonly bufferLeadS = 0.15; // 150 ms playback buffer per SPEC
  public gapCountOver300ms = 0;

  isEnabled(): boolean {
    return this.enabled;
  }

  isTargetMuted(): boolean {
    return this.targetMuted;
  }

  isOutputActive(): boolean {
    return this.enabled && !this.targetMuted;
  }

  private applyGain(): void {
    if (this.gainNode && this.ctx) {
      const g = this.enabled && !this.targetMuted ? 1.0 : 0.0;
      this.gainNode.gain.setValueAtTime(g, this.ctx.currentTime);
    }
  }

  private flushScheduledSources(): void {
    for (const src of this.activeSources) {
      try {
        src.stop();
        src.disconnect();
      } catch {
        // Ignore already-stopped source
      }
    }
    this.activeSources.clear();
    this.nextStartTime = 0;
  }

  /**
   * Mutes or unmutes playback based on whether a consented target face is active.
   * Immediately flushes any in-flight audio buffers when muting.
   */
  setTargetMuted(muted: boolean): void {
    if (this.targetMuted === muted) return;
    this.targetMuted = muted;
    if (muted) {
      this.flushScheduledSources();
    } else if (this.ctx) {
      this.nextStartTime = this.ctx.currentTime + this.bufferLeadS;
    }
    this.applyGain();
  }

  async setEnabled(on: boolean): Promise<void> {
    this.enabled = on;
    if (on) {
      if (!this.ctx) {
        const AudioCtxCtor =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        this.ctx = new AudioCtxCtor({ sampleRate: 16000 });
        this.gainNode = this.ctx.createGain();
        this.gainNode.gain.value = this.targetMuted ? 0.0 : 1.0;
        this.gainNode.connect(this.ctx.destination);
      }
      if (this.ctx.state === "suspended") {
        await this.ctx.resume();
      }
      this.nextStartTime = this.ctx.currentTime + this.bufferLeadS;
    } else {
      this.flushScheduledSources();
    }
    this.applyGain();
  }

  enqueuePcmBase64(b64: string, chunkGain = 1.0): void {
    if (!this.enabled || this.targetMuted || !this.ctx || !this.gainNode || !b64) {
      return;
    }
    const pcm = decodeBase64ToInt16(b64);
    if (pcm.length === 0) return;

    const audioBuf = this.ctx.createBuffer(1, pcm.length, 16000);
    const ch = audioBuf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) {
      ch[i] = (pcm[i] / 32768) * chunkGain;
    }

    const now = this.ctx.currentTime;
    if (this.nextStartTime < now) {
      const gapMs = (now - this.nextStartTime) * 1000;
      if (this.nextStartTime > 0 && gapMs > 300) {
        this.gapCountOver300ms++;
      }
      this.nextStartTime = now + this.bufferLeadS;
    }

    const src = this.ctx.createBufferSource();
    src.buffer = audioBuf;
    src.connect(this.gainNode);
    this.activeSources.add(src);
    src.onended = () => {
      this.activeSources.delete(src);
    };
    src.start(this.nextStartTime);
    this.nextStartTime += audioBuf.duration;
  }

  reset(): void {
    this.flushScheduledSources();
    if (this.ctx && !this.targetMuted) {
      this.nextStartTime = this.ctx.currentTime + this.bufferLeadS;
    }
  }

  stop(): void {
    this.enabled = false;
    this.flushScheduledSources();
    if (this.ctx) {
      void this.ctx.close();
      this.ctx = null;
      this.gainNode = null;
    }
  }
}
