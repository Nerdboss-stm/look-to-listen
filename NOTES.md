# NOTES.md

## To S3 (from S4, 11:39) — Gate G5 Managed Agent findings for E19/E20/E21
Full sanitized JSON from the live run is in `evals/g5_result.json`. Key facts to build directly against:
1. **Model**: `antigravity-preview-09-2026` accepts `agent_config: {"type": "antigravity", "model": "gemini-4-neon"}` directly (6.1 s).
2. **Client-side function tools**: Supported via `tools: [{"type": "function", ...}]`. On `status == "requires_action"`, continuation `POST /v1beta/interactions` **must** include both `"previous_interaction_id": body["id"]` AND `"environment": body["environment_id"]` (omitting `environment` returns HTTP 400 `Missing required field 'environment'`). Send `{"type": "function_result", "name": ..., "call_id": call["id"], "result": "<json string>"}`.
3. **CRITICAL — Hook tool names & matchers (`.agents/hooks.json`)**:
   - Hook `stdin` JSON schema: `{"tool_call": {"name": "<tool>", "args": {...}}, "environment_id": "..."}`.
   - Exact `tool_call.name` values observed inside `pre_tool_execution`: **`execute_code`**, **`write_file`**, **`read_file`**, **`stat_file`** (even though the API response `steps` call them `write_to_file` and `view_file`!).
   - **Client-side function tools do NOT trigger sandbox `pre_tool_execution` hooks** (they pause the runtime with `requires_action` for the client backend).
   - Therefore, to make `gate_release.py`, `gate_privacy.py`, and `gate_command.py` run as genuine `.agents/hooks.json` `pre_tool_execution` command hooks inside the Managed Agent sandbox (SPEC FB8 pattern), match `"write_file|execute_code"` and have the agent write target action files (e.g., `out/release_config.json`, `out/saved_transcript.json`, `out/robot_command.json`) which the hooks validate and allow/deny with a reason (agent self-correction on deny is confirmed working in G5.3!).
   - Inline sources in `environment.sources` place `.agents/hooks.json` cleanly; check relative + `/workspace/` + `/` paths in hook commands just in case.
4. **Scheduled triggers**: `POST /v1beta/triggers` with `schedule: "*/30 * * * *"`, `time_zone: "America/New_York"`, and `interaction: {agent, input, environment, agent_config}` works (475 ms) and can be cleaned up with `DELETE /v1beta/triggers/{id}`.

## To Saran (from S4, 11:39) — SPEC.md Open questions answers (Managed Agent) + G7 hotspot
- **Managed Agent answers for SPEC.md**:
  - Accepts `gemini-4-neon`? **Yes** (`agent_config: {"type": "antigravity", "model": "gemini-4-neon"}`, 6.1 s).
  - Client-side tools? **Yes** (`requires_action` -> `function_result`, requires `environment: environment_id` on continuation).
  - Tool names for hook matchers? Sandbox `pre_tool_execution` hooks receive `execute_code`, `write_file`, `read_file`, `stat_file` (not client-side function tools); deny + agent retry confirmed working; 30-min cron triggers (`/v1beta/triggers`) confirmed working.
- **G7 hotspot (AT3 remaining half)**: Whenever you switch the laptop to your phone hotspot and restart `tunnel.sh`, tell S4 and I will immediately run `gate_g7_roundtrip.py --hops 50 --label hotspot` and log it.

## S2 -> S1 & S3: Frontend WebSocket & REST integration contract (11:41)
Frontend (`frontend/`) connects to `/ws/live` (proxied by Vite from `:5173` -> `127.0.0.1:8000`, or override via `?backend=http://...`).

### Client -> Backend JSON messages on `/ws/live`
- `{"type": "hop", "payload": <contracts/hop.schema.json>}` — emitted at 2 hops/s (`500 ms`, `8000` int16 samples @ 16 kHz, `12-13` base64 112x112 grayscale JPEG target crops following ClearVoice's `c=0.4` padded crop recipe, `reset: true` on first hop and target switch, plus `faces`, `other_crops`, and `frame_jpeg` for Decision 1 / Engine A / Robot R1).
- `{"type": "set_target", "face_id": "face-1" | null, "mode": "auto" | "pinned"}`
- `{"type": "set_consent", "face_id": "face-1", "consent": {"given": bool, "by": str|null, "time": str|null}, "label": str|null}`
- `{"type": "ask_memory", "question": str}` / `{"type": "request_summary"}`
- `{"type": "save_transcript", "conversation_id"?: str}`
- `{"type": "robot_command", "face_id": str, "text": str, "frame_jpeg"?: str|null}`
- `{"type": "replay_last_10s"}`

### Backend -> Client JSON messages on `/ws/live`
- `{"type": "hop_result", "payload": <contracts/hop_result.schema.json>}` (matches `SeparationResult.to_contract_dict()`; browser voice playback defaults to OFF to avoid echoing `backend/playback/player.py`, toggleable via `Voice: ON/OFF`)
- `{"type": "segment", "payload": <contracts/segment.schema.json>}` (`lane`: `"raw"` | `"target"` | `"other"`)
- `{"type": "decision", "payload": <contracts/decision.schema.json>}`
- `{"type": "engine_status", "engine": "B-GPU"|"B-Mac"|"A"|"replay", "reason"?: str, "hop_ms"?: int}`
- `{"type": "metrics", "payload": {"engine", "engine_reason"?, "voice_delay_ms", "caption_delay_ms", "gpu_ms", "rtt_ms", "raw_leakage_pct", "target_leakage_pct", "leakage_source"?, "clips_count"?, "hop_ms"?}}`
- `{"type": "agent_event", "payload": {"time", "event_type", "tool"?, "hook"?, "decision"?: "ALLOW"|"DENY", "reason"?, "summary"}}`
- `{"type": "memory_answer", "payload": <contracts/memory_answer.schema.json>}`
- `{"type": "robot_command", "payload": <contracts/command.schema.json>}` (when `allowed !== false` and `point: [y, x]` is present, the live camera canvas draws the Robot R1 pointing reticle directly on the object)
- `{"type": "end_card", "payload": EndCardData}` (also fetched via `GET /api/end_card` when opening the END CARD modal)

### REST endpoints used as fallback / direct triggers
- `GET /api/end_card` -> `EndCardData` (computed strictly from `clips.csv`, `decisions.csv`, `robot.csv`, `logs/hops.jsonl`)
- `POST /api/memory/ask` (`{"question": str}`) -> `MemoryAnswer`
- `POST /api/robot/command` (`{"face_id", "text", "target_face_id", "frame_jpeg"}`) -> `RobotCommand`
- `POST /api/agent/save_transcript` (`{"conversation_id": str}`)

## To S2 & S3 (from S4, 11:42) — Eval harness & END CARD summary ready
- `evals/metrics.py` implements `contracts/eval.md` verbatim (`norm_text`, `compute_wer`, `compute_leakage`, `score_clips_csv`, `score_decisions_csv`, `score_robot_csv`, `summarize_voice_delay`, `regression_check`). Verified with `pytest evals/test_metrics.py -v` (6/6 passed).
- `python3 evals/score_all.py` writes `evals/summary.json` (real CSV/log numbers only, `n=0` until clips arrive) and SVG charts in `evals/charts/` (`calibration.svg`, `arms_comparison.svg`, `where_it_breaks.svg`). S2 can bind the END CARD directly to `evals/summary.json` (served by backend), and S3 can call `evals.metrics.regression_check` in `gate_release.py`.
- 11:50, to S3, from the Claude chat: G2 now tests gemini-3.5-transcribe-live against gemini-4-hydrogen-live (prompts.md). The robot uses gemini-robotics-er-2-preview (SPEC Models). If a Gemini call returns 403, the API key is unrestricted: Google's Robotics ER docs say the Gemini API refuses unrestricted keys. Add restrictions to the key in AI Studio.
- 11:50, to S2, from the Claude chat: DESIGN.md is the visual spec. Run checks D1 to D6.

## S1 -> S2, S3 & S4: Backend live runtime & mount hooks ready (11:50)
- Run backend: `~/.venvs/g4-backend/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000`
- **For S3 (`backend/gemini/routes.py`)**:
  - `backend/main.py` automatically includes `backend.gemini.routes.router` if present and calls `await register_runtime(runtime)` on FastAPI startup if defined.
  - `runtime` (`from backend.main import get_runtime`) provides:
    - `runtime.on_raw_hop_hooks.append(async_fn)` — called with `(hop_dict, raw_pcm_bytes)` on every browser hop (for Raw lane Hydrogen Live, Decision 1, Engine A fallback).
    - `runtime.on_clean_audio_hooks.append(async_fn)` — called with `(result: SeparationResult)` whenever B-GPU returns clean voice (`result.pcm_bytes`, `result.seq`, `result.t_capture`, `result.t_return`, `result.voice_delay_ms`).
    - `runtime.on_engine_change_hooks.append(async_fn)` — called with `(engine: str, reason: str)` on automatic GPU failover (`B-GPU` <-> `A`).
    - `runtime.on_ws_action_hooks["ask_memory" | "request_summary" | "save_transcript" | "robot_command"] = async_fn` — receives `(msg_dict, ws)`.
    - `await runtime.broadcast(msg_dict)` — broadcasts any `ServerWsMessage` (`segment`, `decision`, `memory_answer`, `robot_command`, `agent_event`, `config`) to all connected `/ws/live` browser clients.
    - Live state: `runtime.target_face_id`, `runtime.latest_faces`, `runtime.latest_frame_jpeg`, `runtime.consent`, `runtime.separator.active_engine`, `runtime.caption_delay_ms` (set this float in ms so `/api/metrics` updates the live DELAY meter).
  - Note: `backend/main.py` already tails `logs/agent.jsonl` and streams new lines to `/ws/live` as `agent_event` messages automatically.
- **For S4 (Set C clip recording & END CARD)**:
  - Consent-enforced clip recording API: `POST /api/consent`, `POST /api/clips/start` (returns HTTP 403 if any face lacks consent), `POST /api/clips/stop` (writes `clips/<id>_raw.wav`, `_clean.wav`, `.json`), `GET /api/clips`, `GET /clips/<filename>`.
  - `GET /api/end_card` reads `clips.csv`, `decisions.csv`, `robot.csv`, `logs/hops.jsonl` directly.

## S1 -> S2: Browser VoicePlayer is now the sole voice player (12:00)
- `PLAYBACK_ENABLED` now defaults to `0` in `backend/playback/player.py` (backend does not open CoreAudio / `sounddevice` by default), so Chrome's AEC (`echoCancellation: true`) cancels the clean voice Chrome plays itself.
- Confirmed `/ws/live` broadcasts `{"type": "hop_result", "payload": {"seq", "pcm": "<base64 int16 LE 16 kHz mono>", "samples": 8000, ...}}` immediately on every GPU result (exact format expected by `VoicePlayer.enqueuePcmBase64(res.pcm)`).
- Request for S2: please default `VoicePlayer` ON when the user clicks Start (so clean voice plays automatically in Chrome without needing a separate toggle).

## To S1 (from S4, 12:02) — Tag `mode` (`live` | `test`) in `logs/hops.jsonl` & `read_hops_stats_from_disk`
Per Saran's instruction (12:01):
1. All 199 existing records in `logs/hops.jsonl` (S1 verify runs `verify-e7-e9-*` + system events) have been tagged `"mode": "test"` via `evals/tag_hops.py`, and `evals/score_all.py` now counts only `"mode": "live"` sessions.
2. Please add `"mode": "test" if session_id.startswith(("verify", "test", "g7", "eval", "offline")) or session_id == "system" else "live"` to `HopLogger.log_result` / `log_drop` / `log_event` in `backend/separation/hop_logger.py`, and filter `read_hops_stats_from_disk` to `mode == "live"` so `/api/end_card` also reports only real live sessions.
3. Optional E16 quality-of-life request: if `ClipStore` can also save per-hop video frames/crops (`<clip_id>_hops.jsonl`) during `/api/clips/start`..`stop`, `evals/run_arms.py` can replay backend-recorded clips directly too (we also support webcam/MP4 capture directly in `evals/record_set_c.py`).

## S2 -> S1 (12:18) — Browser VoicePlayer auto-enabled on Start
- Updated `startLiveCapture()` in `frontend/src/main.ts` so `VoicePlayer` automatically enables (`Voice: On`) when the user clicks `Start Camera`, matching `PLAYBACK_ENABLED=0` in `backend/playback/player.py` for clean Chrome AEC echo cancellation.

## S1 -> S2: No consented target gating + `n_crops` logging (12:42)
- S1 now logs `n_crops` per hop in `logs/hops.jsonl` (and exposes `hops.last_n_crops` on `/health` and `/api/metrics`) so we can immediately verify whether the GPU received `12-13` face crops or `0`.
- Per Saran: when there is no consented target, S2 should mute `VoicePlayer` and show `"Point at someone"` in the `LOOK TO LISTEN` lane instead of playing unguided separation.

## S2 -> S1 (12:58) — `REPO_URL` in `backend/store/end_card.py`
- Please change line 190 of `backend/store/end_card.py` from `os.environ.get("REPO_URL", "https://github.com/saran/look-to-listen")` to `os.environ.get("REPO_URL", "").strip()` so `/api/end_card` never returns a guessed repository URL when `REPO_URL` is unset in `.env`. (`frontend/src/ui/endCard.ts` already reads `REPO_URL` from `.env` via Vite and ignores the old guessed string.)

## S3 -> S1, S2 & S4: All Gemini 4, Robot R1, and Managed Agent modules online (13:12)
- Confirmed model IDs (`backend/gemini/client.py`):
  - Live captions (both lanes): `gemini-3.5-transcribe-live` (`v1alpha`, `interim_input_transcription` + `input_transcription`, custom vocabulary from `vocab.json`, auto-recovery from FB5 `gemini-4-hydrogen` chunked fallback every 15 s). Note: `gemini-4-hydrogen-live` returns 1008 NOT FOUND on `v1alpha`.
  - Speaking decisions: `gemini-decision-1` (`v1alpha`, `4xJPEG+WAV` + `video/mp4`, non-blocking per-face loop + FB6 MediaPipe fallback).
  - Engine A fallback: `gemini-4-hydrogen` (`ThinkingLevel.LOW`, 2 s AV chunks with green target box, automatic activation on GPU failover).
  - Robot R1 pointing: `gemini-robotics-er-2-preview` (`v1beta`, `thinking_budget=0`), automatic fallback to `gemini-4-hydrogen` (`ThinkingLevel.LOW`).
  - Brain / attribution / vocab / translation: `gemini-4-neon` (`ThinkingLevel.LOW`).
  - Memory QA & summary: `gemini-4-argon` (`ThinkingLevel.LOW`), automatic FB7 fallback to `gemini-4-neon` (`source="neon-transcript-only"`).
  - Managed Agent: `antigravity-preview-09-2026` + `gemini-4-neon`, environment in `agent_env/` with `gate_privacy.py`, `gate_command.py`, `gate_release.py`, `post_tool_log.py`.
- Note for S1/S2: If `backend/main.py` was started before 13:10, restart `uvicorn` once to pick up the `live_captioner.py` idle keep-alive + 15 s FB5->Live auto-recovery and `argon.py` `LOW` thinking fix.

## S2 -> S1 & S3 (13:16) — Unguided separation muted & gated on consented target
- Whenever no face is tracked OR the centered/pinned face has `consent.given === false`, the browser now:
  1. Mutes and flushes `VoicePlayer` (and drops any incoming `hop_result` PCM / `lane: "target"` segments),
  2. Displays `"Point at someone"` in `LOOK TO LISTEN`,
  3. Sends `target_face_id: null, crops: []` in hops so unconsented faces are never cropped or separated.
- Tip for live runs: clicking directly on a `?` face ring on the camera feed now grants consent and focuses them in one click (and track grace window is now `2.5 s` so brief head turns keep consent).
