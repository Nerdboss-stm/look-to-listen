---
name: listener
description: Config tuning, regression gating, privacy redaction, and target-only robot command governance for Look to Listen.
---

# Listener Skill

## 1. Pipeline Config Contract (`contracts/config.schema.json`)
Every config JSON contains:
- `config_id` (string, e.g. `"cfg-002"`)
- `engine` (`"B-GPU" | "B-Mac" | "A" | "replay"`)
- `window_s` (number, default `3.0`, range `(0, 10]`)
- `hop_s` (number, default `0.5`, range `(0, 2]`)
- `decision_threshold` (number, default `0.9`, range `[0, 1]`)
- `guard_ms` (integer ms, default `750`, range `[0, 5000]`)
- `vocab` (array of consenting terms/names from `vocab.json`)
- `translate_to` (string BCP-47/language or `null`)

## 2. How to Tune and Release a Config
1. Read `state/baseline_eval.json` and `state/clips_index.json` (or call `get_new_clips`).
2. Evaluate candidate parameter adjustments (`decision_threshold`, `guard_ms`, `window_s`, `hop_s`, `vocab`) using `python3 state/run_eval.py <candidate_config.json>`.
3. Stage the proposed config plus before/after eval results at `/out/candidate_config.json` (format: `{"config": {...}, "before": {"leakage": ..., "wer": ..., "delay_p50_ms": ...}, "after": {"leakage": ..., "wer": ..., "delay_p50_ms": ...}, "clips_n": ...}`), then write `/out/released_config.json`.
4. `gate_release.py` runs automatically on `write_file` to `out/released_config.json`. Release passes ONLY if:
   - `after.leakage <= before.leakage`
   - `after.wer <= before.wer`
   - `after.delay_p50_ms <= before.delay_p50_ms`
5. If denied, read the exact before/after metric reason and either propose a strictly non-regressing config or keep the baseline config.

## 3. Privacy Rule (`save_transcript` and `send_summary`)
- Before writing `/out/saved_transcript.json` or `/out/summary.json`, stage the JSON (`{"conversation_id": ..., "lines": [...]}`) at `/out/candidate_transcript.json` and verify every line's `face_id` has `consent.given == true` in `state/consent.json`.
- If `gate_privacy.py` denies with non-consenting face IDs, remove/redact all lines from those faces in `/out/candidate_transcript.json` and retry writing `/out/saved_transcript.json`.

## 4. Robot Command Rule (`robot_act`)
- Stage candidate command JSON at `/out/candidate_command.json` (`face_id`, `target_face_id`, `text`) before writing `/out/robot_command.json`, checking `face_id == target_face_id` against `state/target_face.json`.
- `gate_command.py` denies any command where `face_id != target_face_id` and names the blocked face.
