/**
 * AudioWorkletProcessor: downsamples native mic input (e.g. 48 kHz) to exact
 * 16,000 Hz mono little-endian Int16 PCM and emits exact hop-sized chunks
 * (default 8000 samples = 500 ms).
 */
class Pcm16kHopProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = 16000;
    this.hopSamples = opts.hopSamples || 8000; // 0.5 s @ 16 kHz
    this.ratio = sampleRate / this.targetRate;
    this.phase = 0;
    this.outBuf = new Int16Array(this.hopSamples);
    this.outIdx = 0;
    this.sumSq = 0;

    this.port.onmessage = (ev) => {
      if (ev.data && ev.data.type === "set_hop_samples") {
        const next = Number(ev.data.hopSamples);
        if (next >= 1600 && next <= 32000) {
          this.hopSamples = next;
          this.outBuf = new Int16Array(this.hopSamples);
          this.outIdx = 0;
          this.sumSq = 0;
        }
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) {
      return true;
    }
    const ch = input[0];
    const len = ch.length;

    // Linear interpolation resampler from native sampleRate -> 16000 Hz
    while (this.phase < len) {
      const i0 = Math.floor(this.phase);
      const frac = this.phase - i0;
      const s0 = ch[i0];
      const s1 = i0 + 1 < len ? ch[i0 + 1] : s0;
      const sample = s0 + frac * (s1 - s0);
      const clamped = sample < -1 ? -1 : sample > 1 ? 1 : sample;
      const i16 = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
      this.outBuf[this.outIdx++] = i16;
      this.sumSq += clamped * clamped;

      if (this.outIdx >= this.hopSamples) {
        const rms = Math.sqrt(this.sumSq / this.hopSamples);
        const chunk = this.outBuf;
        this.port.postMessage(
          { type: "hop_pcm", pcm: chunk.buffer, samples: this.hopSamples, rms },
          [chunk.buffer]
        );
        this.outBuf = new Int16Array(this.hopSamples);
        this.outIdx = 0;
        this.sumSq = 0;
      }

      this.phase += this.ratio;
    }
    this.phase -= len;
    return true;
  }
}

registerProcessor("pcm-16k-hop-processor", Pcm16kHopProcessor);
