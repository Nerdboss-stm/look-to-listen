# Evaluation Specification (`contracts/eval.md`)

Fixed before any evaluation data is collected. Source of truth: `SPEC.md` (Evaluation, Acceptance tests) and `prompts.md` (Scoring).

## 1. Text Normalization
Before computing WER or leakage, normalize every reference and hypothesis string identically:
1. Convert to lowercase (`str.lower()`).
2. Remove all punctuation (keep Unicode letters, digits, and whitespace; e.g. `re.sub(r"[^\w\s]", "", text)` and remove underscores).
3. Collapse consecutive whitespace to a single space and strip leading/trailing whitespace.

Let `norm_words(s)` return the whitespace-split token list of the normalized string `s`.

## 2. Target Word Error Rate (WER)
Computed per clip against the target speaker's close-talk ground-truth transcript (`truth_target`):

- Uses `jiwer.wer(norm(truth_target), norm(hyp_text))` (standard Levenshtein word edit distance `(S + D + I) / N_ref`).
- If `norm_words(truth_target)` is empty:
  - WER is `0.0` if `norm_words(hyp_text)` is also empty; otherwise log `null` (excluded from mean WER, counted separately as hallucination/leakage words).
- Aggregate WER across a set of clips is reported both as corpus WER (`sum(edits) / sum(N_ref)`) and clip-mean WER; the primary gate metric is clip-mean WER over clips with non-empty `truth_target` (with corpus WER reported alongside).

## 3. Leakage
Share of target-lane words that belong to another talker (`truth_others`) and NOT to the target (`truth_target`).

Given a clip with normalized word lists:
- `H = norm_words(hyp_text)` (words emitted in the target lane)
- `T = Counter(norm_words(truth_target))`
- `O = Counter(norm_words(truth_others))`

Compute multiset leakage count as follows:
1. Remove target-matched tokens first so words genuinely spoken by the target are never penalized even if another talker also used the same word:
   - For each word `w` in `H`: if `T[w] > 0`, decrement `T[w]` (matched target); else append `w` to `R` (residual non-target words).
2. Match residual words against `truth_others`:
   - Initialize `leaked = 0`.
   - For each word `w` in `R`: if `O[w] > 0`, decrement `O[w]` and increment `leaked`.
3. Leakage rate for the clip:
   - If `len(H) == 0`: `leakage = 0.0` (no leaked words emitted; silence/miss is captured by WER deletions).
   - Otherwise: `leakage = leaked / len(H)` (in `[0.0, 1.0]`, displayed as `0%`–`100%`).

This definition ensures:
- Shared stop words spoken by the target are credited to the target first.
- Repeated leaked words from `truth_others` are counted accurately up to their occurrences in `truth_others`.
- Aggregate leakage is reported as mean over clips (and total `sum(leaked) / sum(len(H))` alongside).

## 4. Attribution Accuracy (Who Said What)
Evaluated on multi-talker clips (including 3-talker clips for AT9):
- For each finalized attributed segment with a non-null `face_id` and non-empty normalized text, match the segment against the ground-truth talker whose close-talk transcript aligns best in `[t0, t1]`.
- `attribution_accuracy = correct_segments / total_attributed_segments`.
- Acceptance target (AT9): `>= 85%` on 5 three-talker clips.

## 5. Delay (Voice Delay and Caption Delay)
All delays are measured from real timestamps, never estimated.

### 5.1 Voice Delay (from `logs/hops.jsonl`)
For each hop processed by the separation pipeline:
- `hop_collect_ms`: hop duration (`500` ms default, or `1000` ms under FB2).
- `rtt_ms = t_return - t_capture` (measured on the same client clock).
- `playback_buf_ms`: configured audio playback buffer ahead of output (typically `150` ms).
- `voice_delay_ms = hop_collect_ms + rtt_ms + playback_buf_ms` (or direct `t_playout - t_capture` when logged).
- Report `p50` and `p95` across hops. Acceptance target (AT4): `p50 <= 1500 ms`, no playback gap `> 300 ms` over 30 s.

### 5.2 Caption Delay
- Evaluated on Set C clips (and live runs): time from the end of a spoken word/phrase in the close-talk reference track (`t_word_end`) to the timestamp when that caption text first appears on screen (`t_caption_display`):
  - `caption_delay_ms = t_caption_display - t_word_end`.
- Live approximation displayed in the UI DELAY meter between offline evals: `t_caption_rx - segment.t1` (or `voice_delay_ms + asr_latency_ms` logged per segment).
- Report `p50` and `p95`. Acceptance targets: raw lane `p50 <= 1500 ms` (AT7), target lane `p50 <= 3000 ms` (AT5).

## 6. Set D: Speaking Decisions (`decisions.csv`)
- Every 0.5 s window of Set C is labeled per visible face (`truth_speaking` in `{0, 1}`).
- Decision threshold: `p_decision >= 0.9` (or `config.decision_threshold`).
- Metrics:
  - `accuracy_at_0_9`: fraction of windows where `(p_decision >= 0.9) == bool(truth_speaking)`.
  - `latency_p50_ms`: median `latency_ms`.
  - Calibration chart: bin `p_decision` into 10 uniform bins `[0.0, 0.1), ..., [0.9, 1.0]`; plot empirical positive rate vs mean predicted probability and compute Expected Calibration Error (ECE).
- Acceptance target (AT8): `p50 <= 300 ms`, at least 18 of 20 labeled windows correct at `0.9`.

## 7. Set R: Robot Commands (`robot.csv`)
- At least 10 conflicting-command pairs from different people (one is the current target, one is not).
- Metrics:
  - `point_accuracy`: fraction of pairs where the Hydrogen reach point `[y, x]` lands on `object_truth` (`correct == 1`).
  - `hook_block_rate`: fraction of non-target commands denied by `gate_command.py` (`hook_denied_other == 1`).
- Acceptance target (AT12): `point_accuracy >= 8/10` and `hook_block_rate == 10/10`.

## 8. Arms & Comparison Gate ("Beats Raw Captions")
All three arms are run on the exact same Set C clips through the live code path:
- **B0**: Raw captions of the mixed microphone audio (no targeting).
- **Engine A**: Gemini-only live 2 s AV chunks with target box + Decision 1 leakage guard.
- **Engine B-GPU**: ClearVoice cloud GPU live separation + Hydrogen Live target lane + Decision 1 leakage guard.

**Gate rule (SPEC):**
Claim "beats raw captions" **only if**:
1. Evaluated on **at least 30** Set C clips (`n >= 30`), AND
2. Target-lane leakage drops by **at least 20 percentage points** compared to B0 (`mean_leak_b0 - mean_leak_engine >= 0.20`), AND
3. Target-lane WER is **no more than 5 percentage points worse** than B0 (`mean_wer_engine - mean_wer_b0 <= 0.05`).

Always report clip counts (`n`) alongside every metric.

## 9. Regression Gate (`gate_release.py`)
A proposed config passes `gate_release.py` only if, on the Set C regression suite:
- `leakage_after <= leakage_before`
- `wer_after <= wer_before`
- `delay_p50_after <= delay_p50_before`
If any metric gets worse, the hook denies release and reports each metric before and after.

## 10. Where It Breaks
Slice Set C leakage, WER, and delay by:
- Noise level (measured dB: quiet room vs venue hall)
- Number of talkers (2 vs 3)
- Face angle (`front`, `45deg`, `profile`)
- Distance (`1 m`, `2 m`, `3 m`)
- Occlusion (`none` vs hand/cup near mouth)
- Network (venue Wi-Fi vs phone hotspot)
