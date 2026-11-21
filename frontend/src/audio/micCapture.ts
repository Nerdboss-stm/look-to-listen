/**
 * Microphone capture at 16 kHz mono int16 PCM in exact hop-sized chunks
 * (default 500 ms = 8000 samples). Uses AudioWorkletNode with automatic
 * ScriptProcessorNode fallback.
 */

export interface HopPcmChunk {
  pcm: Int16Array;
  tCapture: number;
  rms: number;
  db: number;
}

export class MicCapture {
  private audioCtx: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private fallbackNode: ScriptProcessorNode | null = null;
  private silentGain: GainNode | null = null;
  private hopSamples = 8000;
  private onChunk: ((chunk: HopPcmChunk) => void) | null = null;

  async start(
    stream: MediaStream,
    onChunk: (chunk: HopPcmChunk) => void,
    hopMs = 500
  ): Promise<void> {
    this.stop();
    this.onChunk = onChunk;
    this.hopSamples = Math.round((16000 * hopMs) / 1000);

    // Request 16 kHz AudioContext when supported; worklet resamples cleanly if OS forces 48 kHz.
    const AudioCtxCtor =
      window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.audioCtx = new AudioCtxCtor({ sampleRate: 16000 });
    if (this.audioCtx.state === "suspended") {
      await this.audioCtx.resume();
    }

    this.sourceNode = this.audioCtx.createMediaStreamSource(stream);
    this.silentGain = this.audioCtx.createGain();
    this.silentGain.gain.value = 0;

    if (this.audioCtx.audioWorklet) {
      try {
        await this.audioCtx.audioWorklet.addModule("/audio/pcm-worklet.js");
        this.workletNode = new AudioWorkletNode(
          this.audioCtx,
          "pcm-16k-hop-processor",
          {
            numberOfInputs: 1,
            numberOfOutputs: 1,
            channelCount: 1,
            processorOptions: { hopSamples: this.hopSamples },
          }
        );
        this.workletNode.port.onmessage = (ev) => {
          if (ev.data?.type === "hop_pcm") {
            const pcm = new Int16Array(ev.data.pcm);
            const rms = Number(ev.data.rms) || 0;
            const db = rms > 1e-6 ? 20 * Math.log10(rms) : -120;
            this.onChunk?.({ pcm, tCapture: Date.now(), rms, db });
          }
        };
        this.sourceNode.connect(this.workletNode);
        this.workletNode.connect(this.silentGain);
        this.silentGain.connect(this.audioCtx.destination);
        return;
      } catch (err) {
        console.warn("AudioWorklet failed, falling back to ScriptProcessor:", err);
      }
    }

    // Fallback: ScriptProcessorNode resampler
    const ratio = this.audioCtx.sampleRate / 16000;
    let phase = 0;
    let outBuf = new Int16Array(this.hopSamples);
    let outIdx = 0;
    let sumSq = 0;

    this.fallbackNode = this.audioCtx.createScriptProcessor(4096, 1, 1);
    this.fallbackNode.onaudioprocess = (ev) => {
      const ch = ev.inputBuffer.getChannelData(0);
      const len = ch.length;
      while (phase < len) {
        const i0 = Math.floor(phase);
        const frac = phase - i0;
        const s0 = ch[i0];
        const s1 = i0 + 1 < len ? ch[i0 + 1] : s0;
        const sample = Math.max(-1, Math.min(1, s0 + frac * (s1 - s0)));
        outBuf[outIdx++] =
          sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
        sumSq += sample * sample;

        if (outIdx >= this.hopSamples) {
          const rms = Math.sqrt(sumSq / this.hopSamples);
          const db = rms > 1e-6 ? 20 * Math.log10(rms) : -120;
          this.onChunk?.({ pcm: outBuf, tCapture: Date.now(), rms, db });
          outBuf = new Int16Array(this.hopSamples);
          outIdx = 0;
          sumSq = 0;
        }
        phase += ratio;
      }
      phase -= len;
    };
    this.sourceNode.connect(this.fallbackNode);
    this.fallbackNode.connect(this.silentGain);
    this.silentGain.connect(this.audioCtx.destination);
  }

  setHopMs(hopMs: number): void {
    this.hopSamples = Math.round((16000 * hopMs) / 1000);
    if (this.workletNode) {
      this.workletNode.port.postMessage({
        type: "set_hop_samples",
        hopSamples: this.hopSamples,
      });
    }
  }

  stop(): void {
    this.workletNode?.disconnect();
    this.fallbackNode?.disconnect();
    this.sourceNode?.disconnect();
    this.silentGain?.disconnect();
    this.workletNode = null;
    this.fallbackNode = null;
    this.sourceNode = null;
    this.silentGain = null;
    if (this.audioCtx) {
      void this.audioCtx.close();
      this.audioCtx = null;
    }
    this.onChunk = null;
  }
}
