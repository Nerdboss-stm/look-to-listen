# sets/ — E16 & E26 Fast Capture Runbook (< 2 min per consenting pair)

Every recording obeys `SPEC.md` Organic & Privacy rules:
- **Consent first (read aloud verbatim)**:
  > *"Audio stays on this laptop and is deleted after the event, and only the numbers are shown."*
  `evals/record_set_c.py` prints this disclosure, refuses to start without verbal YES, and writes `clips/set_c/<clip_id>/consent.json`.
- **No real names or spoken text in tracked files**:
  - Real names, audio (`raw.wav`, `close_talk_*.wav`, `b_gpu_clean.wav`), `hops.jsonl`, `consent.json`, `participants.json`, and truth/arm transcripts stay strictly inside **`clips/set_c/`**, which is **gitignored**.
  - Tracked **`clips.csv`** stores **only** anonymous IDs (`P01;P02`), condition tags, and numeric scores (`*_wer`, `*_leak`, `*_time_s`).
- **ASR draft is only a draft**:
  - `--draft-asr` prints the draft and **requires a human to confirm or correct it** (`truth_verified=True`) before the clip is written to `clips.csv` or scored by `evals/run_arms.py`.
- **Unscripted**: talkers speak naturally about anything they want (no fixed phrases).

---

## 90-Second Recording Flow (One Consented Pair)

1. **Read consent disclosure aloud + start phone Voice Memos (15 s)**:
   - Say: *"Audio stays on this laptop and is deleted after the event, and only the numbers are shown. Is it okay if we record 15 seconds of you talking?"* Wait for YES.
   - Both people hold their phone near their mouth and tap Record in Voice Memos.
2. **Capture 15 s live clip (20 s)**:
   ```bash
   /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/record_set_c.py \
     --p1 "Name1" --p2 "Name2" --target center \
     --distance 1 --angle front --noise 65 --occlusion none --network wifi
   ```
   - Confirm `[y]` on consent (assigns `P01;P02` automatically; real names stay in gitignored `clips/set_c/participants.json`).
   - Point the green box at the target face; both talk continuously for 15 s.
   - Saves everything inside gitignored `clips/set_c/cXX/`.
3. **Human-verify close-talk truth (45 s)**:
   - Either type/verify `truth_target` and `truth_others` immediately at the prompt, **or** AirDrop the two Voice Memos and run:
   ```bash
   /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/record_set_c.py \
     --fill-truth c01 \
     --close-talk-target ~/Downloads/p1.m4a \
     --close-talk-other ~/Downloads/p2.m4a --draft-asr
   ```
   - Review the `[ASR DRAFT ONLY]` text, correct any word, and explicitly confirm `[y]` so `truth_verified=True`. (Unconfirmed clips do not count.)
4. **Run B0, Engine A, and Engine B-GPU on verified clips**:
   ```bash
   /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --clip c01
   # or batch every verified clip in clips/set_c/:
   /Users/nerdboss-stm/.venvs/g4-backend/bin/python evals/run_arms.py --all
   ```

---

## E16 Target Matrix (First 10 Clips by 2:00 PM)

| Clip | Talkers | Distance | Angle | Noise | Occlusion | Network |
| --- | :---: | :---: | --- | --- | --- | --- |
| `c01`–`c02` | 2 | 1 m | `front` | quiet / room | `none` | `wifi` |
| `c03`–`c04` | 2 | 1 m | `front` | venue hall | `none` | `wifi` |
| `c05`–`c06` | 2 | 2 m | `front` | venue hall | `none` | `wifi` |
| `c07` | 2 | 3 m | `front` | venue hall | `none` | `wifi` |
| `c08` | 2 | 1 m | `45deg` | venue hall | `none` | `wifi` |
| `c09` | 2 | 1 m | `profile` | venue hall | `none` | `wifi` |
| `c10` | 2 | 1 m | `front` | venue hall | `hand` or `cup` | `hotspot` |

## E26 Full Target Matrix (40 Two-Talker + 10 Three-Talker + 10 Robot Pairs)
- **Set C (`clips.csv`)**: >= 40 two-talker + 10 three-talker clips (10–20 s each) spanning distances `1 / 2 / 3 m`, angles `front / 45deg / profile`, noise `quiet / hall` (logged dB), occlusion `none / hand / cup`, and networks `wifi / hotspot`.
- **Set D (`decisions.csv`)**: every 0.5 s window from `clips/set_c/<clip_id>/decisions_raw.json` labeled `truth_speaking` (`0`/`1`) against close-talk tracks.
- **Set R (`robot.csv`)**: >= 10 conflicting-command pairs with >= 4 everyday objects on the table; log `object_truth`, `point_object`, `correct`, `hook_denied_other`, `latency_ms`.
