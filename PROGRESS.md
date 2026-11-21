# PROGRESS.md

## 10:45 decision (E8), written 11:08, updated 11:17
- G1-GPU: RTX 4090 pod. A 3 s window separates in 131 ms median, 131 ms worst (7 runs). Gate: 350 ms. PASS.
- G7 on venue Wi-Fi: round trip p50 240 ms, p95 467 ms (50 live hops). Gate: 500 ms. PASS.
- Engine order: B-GPU with 0.5 s hops (voice about 1 s behind), then Engine A, then REPLAY. B-Mac only if G1-Mac passes.

## E1 (S1): DONE 10:58, by the Claude chat
- Pod: RTX 4090 24 GB, Python 3.12.3, torch 2.8.0+cu129, ClearVoice 0.1.2. Checkpoint in /workspace/clearvoice_home/checkpoints/AV_MossFormer2_TSE_16K.
- Command on the pod: python gate_g1_pod.py. Output: "G1 CUDA, 3 s window: median 0.131 s, worst 0.131 s".
- The pod has no volume disk. A stop or restart wipes it. Never stop the pod before judging ends. If it restarts: ../gemini4-prep/pod/deploy.sh <ip> <port> (about 2 min).

## E2 (S1): DONE 11:15, by the Claude chat
- Server: ../gemini4-prep/pod/separator_server.py on the pod at 127.0.0.1:8000, kept alive by run_separator.sh. Binary and JSON hops, per SPEC.
- AT2: /health answers. gpu p50 129 ms, p95 133 ms over 50 hops. PASS.
- AT3 venue Wi-Fi: 50 hops of 50 KB, 50 results, 0 merged, 0 errors. Round trip p50 240 ms, p95 467 ms, max 689 ms. PASS. The hotspot run is still open (S4, E4).
- Command: python ../gemini4-prep/gate_g7_roundtrip.py --env .env --hops 50 --label wifi (tunnel up first).
- Next for S1: E7. SEPARATOR_URL and SEPARATOR_TOKEN are in .env.

## E5 (S2): DONE 11:29
- Created all 9 contract files in `contracts/`: `face.schema.json`, `hop.schema.json`, `hop_result.schema.json`, `segment.schema.json`, `decision.schema.json`, `config.schema.json`, `command.schema.json`, `memory_answer.schema.json`, `eval.md`, plus sample payloads in `contracts/samples/` and `contracts/validate_contracts.py`.
- Command: `python3 contracts/validate_contracts.py`
- Output: `All 15 contract checks passed.` (8 schema+sample validations, minimal SPEC/separator_server hop validation, 5 negative invalid-payload rejection tests, `eval.md` 7004 bytes).
- Next for S2: E6 (frontend browser capture, MediaPipe Face Landmarker, ClearVoice face crops, hop packing at 2/s).

## E4 (S4): G5 DONE 11:39; G7 Wi-Fi DONE 11:15, G7 hotspot OPEN (needs phone hotspot switch)
- Command: `python3 evals/gate_g5_managed_agent.py` (raw sanitized output saved in `evals/g5_result.json`, calls logged to `logs/calls.jsonl` and `logs/agent.jsonl`, row appended to `gate_log.csv`).
- G5.1 Model: `antigravity-preview-09-2026` ACCEPTS `gemini-4-neon` directly via `agent_config={"type":"antigravity","model":"gemini-4-neon"}` (HTTP 200, status `completed`, 6142 ms, replied `OK`). No egress proxy workaround needed for the agent model.
- G5.2 Client-side function tools: SUPPORTED (`requires_action` -> `function_result` continuation -> `completed`, `DONE:42`; turn1 7785 ms, turn2 27664 ms). Continuation MUST pass `environment: <environment_id>` alongside `previous_interaction_id`.
- G5.3 `pre_tool_execution` command hook: PASS (HTTP 200, 26504 ms). First attempt denied with `G5_POLICY_DENY` reason; agent read the reason, self-corrected, and created `/tmp/verified_g5.txt` containing `RETRY_OK`. Exact tool names received by hook `stdin` (`tool_call.name`): `execute_code`, `write_file`, `read_file`, `stat_file` (note: API response steps call them `write_to_file`/`view_file`). Client-side function calls pause via `requires_action` and do NOT invoke sandbox hooks — see `NOTES.md` for S3.
- G5.4 Scheduled trigger (30 min): PASS (`POST /v1beta/triggers` with `schedule="*/30 * * * *"`, `time_zone="America/New_York"`, HTTP 200 in 475 ms, `next_run_time=2026-11-21T17:00:00Z`; cleaned up via `DELETE /v1beta/triggers/{id}` HTTP 200).
- G7 status (AT3): Venue Wi-Fi already PASSED (p50 240 ms, p95 467 ms, 50 hops). Hotspot test (`python ../gemini4-prep/gate_g7_roundtrip.py --env .env --hops 50 --label hotspot`) is ready to run as soon as Saran switches to phone hotspot + reconnects tunnel.

## E6 (S2): DONE 11:41 (automated checks passed; live webcam AT1 check ready for browser run)
- Built Vite + TypeScript frontend in `frontend/`:
  - `frontend/public/models/face_landmarker.task` copied from `../gemini4-prep/models/face_landmarker.task` (3.6 MB) and `@mediapipe/tasks-vision` WASM assets copied to `frontend/public/wasm/` (zero network fetches at venue).
  - `frontend/src/vision/faceTracker.ts`: MediaPipe `FaceLandmarker` (up to 4 faces), stable IoU/centroid multi-face IDs, high-contrast speaker colors, lip contour landmarks, `mouth_open` ratio, consent state (default `false`), center-face targeting.
  - `frontend/src/vision/clearvoiceCrop.ts`: exact ClearVoice crop recipe (`c=0.4`, zero-padded `224x224` resize, BT.601 grayscale, `112x112` center crop, JPEG base64).
  - `frontend/public/audio/pcm-worklet.js` + `frontend/src/audio/micCapture.ts`: 16 kHz mono int16 PCM in exact 0.5 s (`8000` sample) chunks via AudioWorklet (with ScriptProcessor fallback).
  - `frontend/src/pipeline/hopPacker.ts`: 25 fps target crop collection (`12-13` crops/hop), stale-hop dropping (never queues), contract-valid `Hop` emission at 2 hops/s.
- Evidence:
  - Command: `npm --prefix frontend run build && npm --prefix frontend test` -> `tsc --noEmit` 0 errors, `vite build` 729 ms, `9 passed (9)` in `frontend/src/__tests__/pipeline.test.ts` (2.0 hop/s, 8000-sample PCM, 12-13 crops, stale-hop drop, 3-face tracking, ClearVoice geometry + zero-padding).
  - Cross-language schema check: live `HopPacker` + `MultiFaceTracker` JSON output piped into `python3` `Draft202012Validator(contracts/hop.schema.json)` -> `PASS: {'seq': 0, 'pcm_bytes': 16000, 'samples': 8000, 'crops': 12, 'faces': 1, 'reset': True}`.

## E13 (S2): DONE 11:41 (10/10 simulated switches passed; live camera AT6 check ready with backend)
- Implemented center-face auto switching (120 ms hysteresis, 0.03 margin) and tap/click-to-pin on the live video canvas + face chips (`Auto` button returns to center tracking).
- Target switches immediately invoke `hopPacker.markTargetSwitch(id)` (clears old target crops, sets `reset: true` on the next hop), resets browser `VoicePlayer`, and sends `{"type": "set_target", ...}` on `/ws/live`.
- Evidence: `frontend/src/__tests__/pipeline.test.ts` E13 suite -> 10/10 alternating 30 fps camera pans switched target and emitted `reset: true` followed by `reset: false`, plus tap-to-pin/unpin verified.

## E14 (S2): DONE 11:41 (built & CSS-verified; ready for 5 m projector photo check)
- Built high-contrast projector UI (`frontend/index.html`, `frontend/src/styles.css`, `frontend/src/ui/overlayRenderer.ts`, `frontend/src/ui/endCard.ts`):
  - Top ~60% live camera with speaker-colored face boxes, pulsing double target ring, Decision 1 speaking badge, consent badges, wall clock (`HH:MM:SS ET`), FPS/hop telemetry.
  - Bottom ~40% two live caption lanes (`WHAT THE MICROPHONE HEARS` raw mix vs `LOOK TO LISTEN` target + colored other-speaker lines).
  - Right side strip: `ENGINE` badge (`B-GPU`/`B-Mac`/`A`/`REPLAY`), `LEAKAGE` counters, `DELAY` meter (voice & captions, measured only — `—` until live/CSV values arrive), `END CARD` modal (`E` shortcut).
- Evidence: Verified compiled `frontend/dist/assets/*.css` enforces `.caption-line` `>= 32px` (`clamp(32px, 2.3vw, 42px)`) and `.counter-value` `>= 40px` (`clamp(40px, 2.6vw, 46px)`), plus offline `face_landmarker.task`, WASM, and `pcm-worklet.js` present in `frontend/dist/`.

## E23 (S2): DONE 11:41 (built & wired to `/ws/live` + REST fallbacks; ready for live hook demo)
- Built projector-readable `AGENT · HOOKS` stream (high-contrast green `ALLOW` / red `DENY` pills + `Save Transcript` button), `ROBOT R1 · COMMAND HOOK` panel (shows allowed/blocked commands + draws `[y, x]` Hydrogen pointing crosshair directly on the live camera feed), and `MEMORY · ARGON` box (`Ask` + `Summary` buttons showing answer, timestamp, clip, confidence, latency, and FB7 `TRANSCRIPT ONLY` badge).
- Documented full `/ws/live` & REST contract for S1 and S3 in `NOTES.md`.
- Next for S2: standing by for live integration checks (AT1/AT6/5 m projector readability) once S1's `backend/main.py` and S3's routes come online.
- S4 eval harness ready ahead of E16/E26–E29: `evals/metrics.py`, `evals/score_all.py`, `evals/test_metrics.py`, `sets/README.md`. Command: `pytest evals/test_metrics.py -v` -> `6 passed in 0.04s`. `python3 evals/score_all.py` -> wrote `evals/summary.json` and 3 charts in `evals/charts/`.

## E7 (S1): DONE 11:54
- Built FastAPI backend, GPU separation client, live speaker playback, delay logger, consent records, clip store, and CSV-backed END CARD endpoint:
  - `backend/main.py`: FastAPI app loading `.env` (never logs secrets), `/ws/live` matching S2's `contracts.ts`, live `logs/agent.jsonl` streaming, FB4 `replay_last_10s`, S3 router & runtime hook mount (`backend/gemini/routes.py`), REST endpoints (`/health`, `/api/health`, `/api/metrics`, `/api/end_card`, `/api/evals/summary`, `/api/evals/charts/{file}`, `/api/consent`, `/api/playback`, `/api/engine`, `/api/clips/start|stop`, `/clips/{file}`).
  - `backend/separation/client.py`: binary fast-path WebSocket client (`compression=None`, `max_inflight=2` to prevent SSH-tunnel bufferbloat), single-slot latest-hop mailbox (never queues; drops stale hops > `1.15 * hop_ms`), automatic failover to Engine A within `<= 3 s` on disconnect or response timeout (AT14) with automatic recovery to B-GPU.
  - `backend/separation/hop_logger.py` & `replay.py`: append-only `logs/hops.jsonl` with rolling p50/p95 stats and 10 s in-memory FB4 replay buffer (cleared on disconnect).
  - `backend/playback/player.py`: `LiveAudioPlayer` on 16 kHz mono `sounddevice.OutputStream` (`MacBook Air Speakers`), 260 ms jitter-cushion lead-in, 10 ms cosine crossfade on discontinuities/target switches, drift cap (`max_buffer_ms=1200`), real underrun gap tracking, behind `PLAYBACK_ENABLED` flag.
  - `backend/store/consent.py`, `clips.py`, `end_card.py`: consent-enforced clip store (HTTP 403 + `logs/agent.jsonl` DENY if any face lacks consent; aborts live recording if a non-consenting face enters frame) and real CSV/log-only END CARD stats.
- Evidence:
  - Command: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest -v backend/separation/test_s1.py`
  - Output: `9 passed in 0.81s` (binary hop/result wire format, stale-hop dropping, 30 s player continuity & crossfade, gap detection & drift cap, consent-enforced clip store deny/abort/allow, empty & 30-clip gate END CARD rules, AT14 failover 3/3 under 3 s, FastAPI endpoints & HTTP 403 consent gate).

## E9 (S1): DONE 11:54 (30 s live GPU + MacBook Air Speakers AT4 technical check PASS; ready for two-person live ear check)
- Root-caused and fixed two live Wi-Fi playback issues found in initial 30 s runs: (1) added explicit 260 ms jitter-cushion lead-in to `LiveAudioPlayer` (so hop 0 doesn't play immediately with 0 ms headroom); (2) disabled WebSocket permessage-deflate (`compression=None`) and capped `max_inflight=2` in `SeparationClient` to eliminate SSH-tunnel TCP bufferbloat (dropped RTT p50 from 581.9 ms -> 240.9 ms, p95 from 1213.1 ms -> 352.2 ms).
- Evidence:
  - Command: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python backend/separation/verify_e7_e9.py --hops 60 --port 8011`
  - Output: `60/60` hops (`30.0 s`) through `/ws/live` -> `SeparationClient` -> RTX 4090 pod -> `LiveAudioPlayer` (`MacBook Air Speakers`, `device_ok=True`) + mid-run target switch at hop 30: `gpu p50 128.7 ms / p95 130.4 ms`, `RTT p50 240.9 ms / p95 352.2 ms`, `voice_delay p50 1256.9 ms / p95 1273.4 ms` (AT4 gate `<= 1500 ms`), `played 29.98 s`, `max_gap 0.0 ms`, `gaps>300ms 0` (AT4 gate `0`), `dropped 0`, `merged 0`. `VERDICT: PASS`.
- All scheduled S1 tasks (E1, E2, E7, E9) are complete. Standing by for full-stack integration with S2 (`frontend/`) + S3 (`backend/gemini/routes.py`) and live two-talker speaker check in the room.

## E4 (S4): FULLY DONE 11:58 (G5 PASS + AT3 Wi-Fi & Hotspot PASS)
- G7 Hotspot command: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python ../gemini4-prep/gate_g7_roundtrip.py --env .env --hops 50 --label hotspot`
- G7 Hotspot output: `50 hops sent, 50 results, 0 hops merged, 0 errors, 50.4 KB up per hop`; `round trip p50 458 ms, p95 1567 ms, max 1865 ms`; `AT2: gpu p50 129 ms, p95 131 ms; queue p50 0 ms`; **`G7 hotspot: PASS (p50 at or under 500 ms)`**.
- AT3 network comparison logged in `gate_log.csv`: Venue Wi-Fi p50 `240 ms` (p95 `467 ms`, max `689 ms`) vs Phone hotspot p50 `458 ms` (p95 `1567 ms`, max `1865 ms`). Both pass `<= 500 ms` p50; hotspot tail jitter (~3.4x Wi-Fi p95) validates FB2 (raise hop to 1 s if hotspot jitter spikes).
- Next for S4: E16 (start Set C live consented recordings with close-talk phones; target 10 clips in `clips.csv` by 2 PM) and E17 (DeepMind mentor demo + feedback in `NOTES.md` by 2 PM).

## E9 update (S1): Browser-only voice playback (`PLAYBACK_ENABLED=0`), 12:00
- Changed `PLAYBACK_ENABLED` default to `0` in `backend/playback/player.py` (no `sounddevice` stream opened unless explicitly enabled) and moved `/ws/live` `hop_result` broadcast to step 1 of `_on_separation_result` in `backend/main.py` so S2's browser `VoicePlayer` is the sole audio player (allowing Chrome AEC to cancel played clean voice).
- Evidence:
  - `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest -v backend/separation/test_s1.py` -> `10 passed in 3.33s` (including `test_playback_disabled_by_default_and_ws_live_sends_clean_pcm`).
  - `/Users/nerdboss-stm/.venvs/g4-backend/bin/python backend/separation/verify_e7_e9.py --hops 10 --port 8012` -> `backend_playback_enabled=False`, `9/9` valid 16 kB int16 PCM `hop_result` frames delivered on `/ws/live`, `gpu p50 128.6 ms`, `voice_delay p50 1054.6 ms` (`VERDICT: PASS`).
  - Notified S2 in `NOTES.md` to auto-enable `VoicePlayer` on Start.

## S4 Prep for E16 & E27: DONE 12:10 (`logs/hops.jsonl` tagging, `evals/run_arms.py`, `< 2 min` E16 recorder)
- `logs/hops.jsonl` session tagging (`evals/tag_hops.py`) & live-only scoring (`evals/metrics.py`, `evals/score_all.py`):
  - Command: `python3 evals/tag_hops.py && python3 evals/score_all.py`
  - Output: `Tagged logs/hops.jsonl: total=661 live=440 test=221`; `Voice delay (live hops.jsonl): n_live=375 (excluded test=190) p50_ms=1111.7 rtt_p50_ms=461.7`. Requested S1 in `NOTES.md` to emit `"mode": "live"|"test"` directly in `HopLogger` and filter `read_hops_stats_from_disk` to live sessions.
- Built 3-arm live-code-path runner (`evals/run_arms.py` + `evals/clip_io.py`):
  - Runs B0 (`LiveCaptionLane(lane="raw")`), Engine A (`EngineALiveBuffer` + green target box + `LeakageGuard`), and Engine B-GPU (`SeparationClient` -> `LiveCaptionLane(lane="target")` + `LeakageGuard`) on the exact same 0.5 s hops (or decoded video via `ffmpeg` + ClearVoice `112x112` cropper). Uses isolated `evals/eval_hops.jsonl` so offline evals never pollute live `logs/hops.jsonl`. Enforces consent before processing, upserts `clips.csv`, saves `decisions_raw.json` and `b_gpu_clean.wav`, and refreshes `evals/summary.json`.
- Prepped E16 fast recorder (`evals/record_set_c.py` + `sets/README.md` runbook):
  - Enforces verbal consent first (`consent.json`), captures 16 kHz mic + 25 fps webcam + ClearVoice crops in 15 s, supports AirDropped close-talk phone audio with optional `--draft-asr` for fast human verification, and feeds directly into `evals/run_arms.py`.
- Verification:
  - Command: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest evals/test_metrics.py evals/test_run_arms.py -v`
  - Output: `12 passed in 0.59s` (normalization, WER, multiset leakage, beats-raw gate, regression gate, live-only `hops.jsonl` filtering, ClearVoice 112x112 crop + edge padding, hops JSONL roundtrip, CSV upsert, consent refusal gate, 3-arm dry-run end-to-end, live S1/S3 backend symbol & signature checks).

## DESIGN.md rework + Checks D1–D6 (S2): D1–D5 PASS 12:18; D6 OPEN (needs venue projector photo)
- Reworked `frontend/` to match `DESIGN.md` verbatim while preserving all live behavior and the `/ws/live` contract (plus auto-enabling browser `VoicePlayer` on Start per S1's 12:00 `PLAYBACK_ENABLED=0` update):
  - Fixed `1920x1080` letterboxed stage (`24 px` outer margin, `16 px` gutter, `1440x640` camera, two `712x376` lanes, `416 px` side strip ordered `DELAY`, `ENGINE`, `AGENT`, `MEMORY`, `ROBOT`; never reflows).
  - Self-hosted `@fontsource/atkinson-hyperlegible-next` & `@fontsource/atkinson-hyperlegible-mono` (`tabular-nums`, zero CDN calls), Dark default & Bright room (`B` key) token palettes, speaker letter badges `A`/`B`/`C`, dashed gray `?` ring + caption suppression for faces without consent.
  - Camera spotlight: 35% radial dim outside target face, `6 px` target ring + `2 px` white inner stroke + `24 px` soft glow + `"A · LISTENING"` badge, `300 ms` ease-out target switch (`instant` under `prefers-reduced-motion`), `150 ms` lane badge crossfade, `1 Hz` `LIVE` dot next to `28 px` mono wall clock, `1 s` failover outline flash on `ENGINE` (`"ENGINE A · GEMINI ONLY"`), Robot live mini-frame with crosshair + struck-through denied commands, and thin spotlight line joining the target ring to `"LOOK TO LISTEN"` (built after D1–D4 passed).
  - Full-screen `END CARD` (`64 px` headline, three `120 px` metrics with `24 px` labels, one-line where-it-breaks, repo link + self-contained SVG QR code).
- Evidence (`node frontend/scripts/verify_design_checks.mjs --mode d1-d4` & `--mode d5` via Headless Chrome CDP):
  - **D1 Sizes (`1920x1080`) — PASS**: `checked=45 visible text nodes, under_18px=0, target_caption=44px, raw_caption=38px, counters=56px, clock=28px, camera=1440x640, lanes=712x376+712x376, side=416px, non_consent_suppressed=true`.
  - **D2 Contrast (Dark & Bright tokens) — PASS**: `Dark(target=18.47:1, raw=12.73:1, label=8.79:1)` and `Bright(target=17.76:1, raw=9.49:1, label=6.98:1)` (all captions `>= 7:1`, all labels `>= 4.5:1`).
  - **D3 No Shift (30 s live value churn) — PASS**: `layout_shift=0, max_counter_delay_width_delta=0px` over 30.1 s.
  - **D4 Overlay FPS (10 s, 3 animated faces) — PASS**: `57.3 fps (574 frames)` (gate `>= 30 fps`).
  - **D5 Screenshots — PASS**: saved `evals/ui/stage_1920x1080.png` (279,745 B), `evals/ui/stage_1280x720.png` (193,825 B, visually verified legible with zero reflow/clipping), `evals/ui/stage_1920x1080_bright.png` (291,886 B), and `evals/ui/end_card_1920x1080.png` (60,041 B).
  - **D6 Projector (5 m photo) — OPEN**: requires connecting laptop HDMI to the venue projector and photographing the projected screen from 5 m (Saran / E14 live room check).
- E16 privacy & truth-verification fixes applied (12:25):
  - All Set C audio, hops, real names (`participants.json`, `consent.json`), and truth/arm transcripts now live strictly in gitignored `clips/set_c/`. Tracked `clips.csv` stores ONLY anonymous IDs (`P01;P02`, validated by `_validate_anonymous_consent_ids`) and numeric scores (empty text columns).
  - Consent prompt in `evals/record_set_c.py` and `sets/README.md` reads verbatim: `"Audio stays on this laptop and is deleted after the event, and only the numbers are shown."`
  - ASR drafts (`--draft-asr`) are explicitly shown as drafts and require human confirmation/correction (`truth_verified=True`); unverified clips are rejected by `evals/run_arms.py` and never written to `clips.csv`.
  - Verification: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest evals/test_metrics.py evals/test_run_arms.py -v` -> `13 passed in 0.70s`.

## S1 update: `n_crops` per hop in `logs/hops.jsonl`, 12:47
- Updated `backend/separation/hop_logger.py` and `backend/separation/client.py` to log `"n_crops": len(hop.jpegs)` on every hop record (`ok` and `dropped_stale`) in `logs/hops.jsonl` and expose `hops.last_n_crops` on `/health` and `/api/metrics`. Also ensured `runtime.target_face_id` clears to `None` when a hop reports `target_face_id: null`.
- Left item (2) note for S2 in `NOTES.md` (mute voice & show `"Point at someone"` in LOOK TO LISTEN lane when there is no consented target).
- Evidence: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest -v backend/separation/test_s1.py` -> `10 passed in 5.78s` (verified `n_crops=12` end-to-end through `SeparationClient` -> mock GPU WS -> `hops.jsonl`, and `n_crops=0` on dropped stale hops). Note: live GPU tunnel at `localhost:18000` was unreachable during the 12:44 probe (`gpu_ws_disconnected:TimeoutError`, auto-failed over to Engine A).

## Screenshot review fixes 1–6 (S2): DONE 12:58
- Addressed all 6 review items across `frontend/` and refreshed `evals/ui/` screenshots:
  1. **LEAKAGE**: Hidden (`visibility: hidden`, empty text, `CLS = 0`) until a real value exists; when present, `LEAKAGE` matches `.lane-title` (`22 px` caps, `0.08em` tracking, `align-items: center`, measured `title_align_delta = 0 px`).
  2. **Floating blue bar**: Removed synthetic floating bar next to Speaker A's ring.
  3. **AGENT hook reasons**: Wrapped `.agent-item` up to 2 lines (`-webkit-line-clamp: 2`, expanded `AGENT` panel height) so hook denial reasons (`DENIED · gate_privacy: face-3 has no consent record`) read in full without `...` truncation.
  4. **DELAY units**: Standardized both `VOICE` and `CAPTIONS` to seconds with two decimals (`0.92s` and `1.94s`).
  5. **Auto-hide HUD**: `.camera-controls` and `.face-bar` fade out after `3 s` without mouse movement (`opacity: 0; pointer-events: none`) and reappear immediately on `mousemove` / `mousedown` / `touchstart`.
  6. **END CARD `REPO_URL`**: Vite reads `REPO_URL` from repo-root `.env` (`envPrefix: ["VITE_", "REPO_URL"]`, never exposing secret keys), and `endCard.ts` renders the link + QR strictly when `REPO_URL` is configured (no guessed fallback URL).
- Evidence (`node frontend/scripts/verify_design_checks.mjs --mode all` & `npm --prefix frontend test`):
  - `PASS Review Fixes 1-6: leakage_hidden_when_null=true, title_align_delta=0px, delay=0.89s/1.98s, agent_clamp=2 lines, idle_hide=0->1`
  - `PASS D1 Sizes (1920x1080): checked=41 visible text nodes, under_18px=0, target_caption=44px, raw_caption=38px, counters=56px, clock=28px`
  - `PASS D2 Contrast: Dark(target=18.47:1, raw=12.73:1, label=8.79:1) | Bright(target=17.76:1, raw=9.49:1, label=6.98:1)`
  - `PASS D3 No Shift (30 s): layout_shift=0, max_counter_delay_width_delta=0px`
  - `PASS D4 Overlay FPS (10 s, 3 faces): 59.9 fps (600 frames)`
  - `10/10` Vitest unit tests passed (`pipeline.test.ts`), and D5 screenshots updated in `evals/ui/`.

## No-consented-target mute & "Point at someone" guard (S2): DONE 13:16
- Updated `frontend/src/audio/voicePlayer.ts`, `frontend/src/main.ts`, `frontend/src/vision/faceTracker.ts`, and `frontend/index.html`:
  - Added `VoicePlayer.setTargetMuted(true)` (starts muted; immediately zeroes gain and stops/flushes any scheduled `AudioBufferSourceNode`s whenever there is no consented target face, and drops incoming `hop_result` PCM and unguided `target`-lane segments).
  - `LOOK TO LISTEN` displays `"Point at someone"` whenever there is no consented target (0 faces in frame OR target face lacks consent), switching to `"Waiting for speech"` -> target captions only once pointing at a consented speaker.
  - Hops only send a non-null `target_face_id` and ClearVoice crops when the active target has consented; tapping directly on a `?` ring on the camera canvas grants consent and focuses that speaker in one click; raised `MultiFaceTracker.trackTimeoutMs` from `900 ms` -> `2500 ms` so brief head turns do not drop a consented speaker's track.
- Evidence:
  - `npm --prefix frontend run build && npm --prefix frontend test` -> `11/11` Vitest tests passed.
  - `node frontend/scripts/verify_design_checks.mjs --mode quick` -> `PASS No-Consented-Target Guard: initial="Point at someone" (muted=true), unconsented_face="Point at someone" (muted=true)` + `D1` & `D2` PASS.

## E3 (S3): DONE 12:12 (G2 PASS, G6 PASS, G4 measured, G3 honest NO logged — all rows in `gate_log.csv`)
- Discovered confirmed Gemini 4 & Live model IDs (`backend/gemini/client.py`, `backend/gemini/discover_models.py`) and built append-only call/agent logger (`backend/gemini/logger.py` -> `logs/calls.jsonl`, `logs/agent.jsonl`).
- **G2 Captions — PASS**:
  - `gemini-3.5-transcribe-live` (`v1alpha`, two concurrent live sessions on 5 spoken sentences of 16 kHz mono PCM, `interim_input_transcription` + `input_transcription`, `custom_vocabulary` ready from `vocab.json`): Lane 1 **WER 0.0%**, **p50 647.9 ms**; Lane 2 **WER 0.0%**, **p50 650.6 ms** (gates: `WER <= 10%`, `p50 <= 1500 ms` -> PASS; also satisfies AT7).
  - `gemini-4-hydrogen-live`: `APIError 1008 NOT_FOUND` on `v1alpha` (`bidiGenerateContent` unsupported).
  - `gemini-4-hydrogen` (`ThinkingLevel.LOW`, 1 s WAV chunks, 17 chunks): WER 22.9%, p50 2882.7 ms -> kept as automatic FB5 fallback only.
- **G3 Decisions API speaking (`gemini-decision-1`, `v1alpha`) — NO on 300 ms / 18-of-20@0.9 gate (honest result logged)**:
  - 20 x 1 s AV face-crop clips (10 speaking, 10 silent with other talker audio): `4xJPEG+WAV` got `11/20 @ 0.9`, `17/20 @ 0.5`, `p50 1567 ms`; `video/mp4` (`resolution=low, processing=static`) got `10/20 @ 0.9`, `13/20 @ 0.5`, `p50 1293 ms`. Venue Wi-Fi network+inference latency is >300 ms and 2-frame synthetic morphs rarely crossed 0.90; wired non-blocking in live loop (drops overlapping in-flight calls) + FB6 MediaPipe fallback (`calibrated=False`); will re-score on real venue Set D clips in E28.
- **G4 Engine A (`gemini-4-hydrogen`, `ThinkingLevel.LOW`) — INFO**:
  - 5 two-talker AV clips cut into 2 s chunks with green box on target face: **mean leakage 0.0%** (`0/33` target-lane words leaked), mean WER 45.9%, chunk p50 8473.6 ms. Confirms B-GPU as base live engine and Engine A as zero-leakage GPU failover.
- **G6 Robot pointing — PASS (5/5 visually verified)**:
  - `gemini-robotics-er-2-preview` (`v1beta`, `thinking_budget=0`, 5 table photos with >=5 everyday objects each): **5/5** dead-center hits on target objects (mug, apple, stapler, scissors, soda can), **p50 2137 ms** -> selected primary.
  - `gemini-4-hydrogen` (`ThinkingLevel.LOW`, same 5 photos): **5/5** hits, p50 3818 ms -> wired as automatic fallback (with FB9 attribution-only fallback).

## E10, E11, E12, E15, E18, E19, E20, E21, E22 (S3): DONE 13:24
- Built all S3 production modules and mounted cleanly into S1's `backend/main.py` via `backend/gemini/routes.py` (`router` + `register_runtime(runtime)`):
  - **E10 & E11 (`backend/gemini/live_captioner.py`, `vocab.py`)**: Dual concurrent `gemini-3.5-transcribe-live` lanes (raw + clean target), interim+final streaming, 8 s idle keep-alive, consent-gated `vocab.json` custom vocabulary, FB5 chunked fallback with 15 s auto-recovery back to Live, target-caption suppression when `target_face_id` is null.
  - **E12 (`backend/gemini/decisions.py`)**: Per-face `SpeakingDecisionClient` (`gemini-decision-1`, FB6 MediaPipe fallback) + `LeakageGuard` (drops target-lane words when target is not speaking; attributes non-target speech to `'other'` lane).
  - **E15 (`backend/gemini/engine_a.py`, `routes.py`)**: `EngineALiveBuffer` (2 s AV chunks with green target box) auto-activated on GPU failover. **AT14 check**: mid-run GPU kill switched `SeparationClient` to `Engine A` **3/3** in `0.352 s`, `0.355 s`, `0.354 s` (`<= 3.0 s` -> PASS).
  - **E18 (`backend/gemini/neon.py`)**: `gemini-4-neon` segment merging, consenting `vocab.json` spelling, multi-talker attribution from Decision 1 timeline, optional translation. **AT9 check**: 5 three-talker clips -> **15/15 (100.0%)** attribution accuracy (`>= 85%` -> PASS).
  - **E19 (`agent_env/`, `backend/gemini/managed_agent.py`)**: Created `agent_env/AGENTS.md`, `agent_env/skills/listener/SKILL.md`, `agent_env/.agents/hooks.json`, `agent_env/hooks/gate_privacy.py`, `gate_command.py`, `gate_release.py`, `post_tool_log.py`. **AT11 check**: local `3/3` deny->redact->allow PASS + live remote Managed Agent sandbox (`antigravity-preview-09-2026` + `gemini-4-neon`, HTTP 200 `completed`): `PRIVACY_DENIED=yes REDACTED_SAVED=yes` -> PASS.
  - **E20 (`backend/robot/pointing.py`, `agent_env/hooks/gate_command.py`, `routes.py`)**: `POST /api/robot/command` + WS `robot_command`. **AT12 check**: 10 conflicting-command pairs across 5 table scenes -> **10/10** target objects pointed by `gemini-robotics-er-2-preview` (`>= 8/10`), **10/10** non-target commands denied by `gate_command.py` naming the blocked face -> PASS.
  - **E21 (`agent_env/hooks/gate_release.py`, `backend/gemini/managed_agent.py`)**: Regression-gated config release (`contracts/eval.md §9`) using SPEC FB8 staged-candidate pattern (`/out/candidate_config.json` -> `/out/released_config.json`, since Managed Agent `write_file` hook passes only `path`). **AT13 check**: local `2/2` PASS + live remote Managed Agent sandbox (HTTP 200 `completed`, 80.2 s): `WORSE=DENY BETTER=ALLOW` with exact before/after metrics (`leakage 0.1400->0.2100, delay_p50_ms 1450.0->1600.0`) + live 30-min cron trigger (`POST /v1beta/triggers`, HTTP 200 in 594 ms, `next_run_time=2026-11-21T18:30:00Z`, deleted cleanly) -> PASS.
  - **E22 (`backend/gemini/argon.py`)**: `ConversationMemory` (`gemini-4-argon` at `ThinkingLevel.LOW` + automatic FB7 `gemini-4-neon` `neon-transcript-only` fallback on timeout/error, strictly consenting lines only). **AT10 check**: 5 questions on a 10-minute conversation -> **4/5 passed** within 8 s (`p50 6323.2 ms`), 5/5 exact answers + timestamps within 15 s + clip links -> PASS.
- Unit & integration evidence:
  - Command: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest backend/gemini/test_s3_suite.py -v`
  - Output: `9 passed in 0.87s` (LeakageGuard, FB6 fallback, privacy hook 3/3, command hook 10/10, release hook 2/2, stdin hook protocol, consent-gated vocab.json, pointing JSON parser, FastAPI route mount).

## Face re-ID (2 s) + Target hold (1 s) + 12/13 crop stability (S2): DONE 13:34
- Fixed track ID churn and `0`-crop gaps across `frontend/src/vision/faceTracker.ts`, `frontend/src/pipeline/hopPacker.ts`, and `frontend/src/main.ts`:
  1. **2 s re-identification with consent carry (`reappearMs = 2000`)**: Two-pass tracker matches live tracks (`<= 250 ms`) first, then re-identifies any face reappearing within `2.0 s` near where a track was lost (`dist <= max(0.38, 1.5 * boxSize)`), restoring its exact old `face-*` ID, speaker color, and `consent` record (`> 2.0 s` expires cleanly so a stranger later never inherits consent).
  2. **1 s target hold on brief loss (`targetHoldMs = 1000`)**: Keeps `targetFaceId` and its consented face entry active for up to `1.0 s` when MediaPipe briefly misses frames (blinks, head turns, cup occlusion), preventing premature switches or `"Point at someone"` flicker.
  3. **Steady 25 fps cropper + strict 12/13 crop bounds + lower MediaPipe thresholds**: Decoupled 25 fps (`40 ms`) `ClearVoiceCropper` sampling from camera auto-exposure framerate drops, tightened `HopPacker` crop bounds to strictly `12..13` for `500 ms` hops, enforced monotonic `detectForVideo` timestamps, and lowered MediaPipe confidence thresholds (`0.35 / 0.35 / 0.30`).
- Evidence:
  - Unit & simulation suite: `npm --prefix frontend run build && npm --prefix frontend test` -> **`13/13` Vitest tests passed** (verifying `<= 1 s` target hold, `1.8 s` re-ID carrying `face-1` + consent, `2.5 s` expiry clearing ID/consent, and 60 s / 120-hop dropout simulation `>= 95%`).
  - 60 s end-to-end Chrome -> `/ws/live` (`127.0.0.1:8000`) -> RTX 4090 GPU -> `logs/hops.jsonl` check (`node frontend/scripts/verify_60s_hops.mjs`, silent audio + 5 brief losses & 1.25 s look-away, `session_id = verify-track60s-mwqqxmbd`):
    - `OK hops: 124`, `n_crops 12|13: 124/124 (100.0%)`, `target_face_id: {'face-1': 124}`, `hopsDropped: 0` (`VERDICT: PASS`).
  - Human webcam 60 s check helper ready: after clicking consent on your face at `:5173` for 60 s, run `python3 frontend/scripts/check_live_hops.py` to score the newest `sess-*` live session in `logs/hops.jsonl`.

## Live Captions & Argon Fix (S3): DONE 13:54 (4 fixes verified; 5-min soak 3 loops logged honestly)
- **Root causes diagnosed from `logs/calls.jsonl` and live probes**:
  1. **`1008 The operation was aborted` at 60–68 s**: Proved experimentally via 3-arm live probe — `IDLE` session (no audio sent) died at `62.19 s` with `1008`, whereas `SILENCE` (100 ms silence frames) and `SPEECH` both survived past `78 s`. Earlier logs also showed `1011 Deadline expired` near `~243 s`. Fixed in `backend/gemini/live_captioner.py` with `IDLE_KEEPALIVE_S = 2.0` silence frames, proactive make-before-break rotation every `55.0 s` (`ROTATE_AFTER_S = 55.0`) that waits for the warming session's first live caption (`first_text_event`) before silencing the old session, plus an `8.0 s` speech-gated WebSocket liveness watchdog (`WS_RX_WATCHDOG_S = 8.0`) to catch blackholed half-open sockets.
  2. **Stuck in FB5 after handshake timeouts**: Added background Live recovery probe every `10.0 s` (`LIVE_RETRY_INTERVAL_S = 10.0`, `CONNECT_TIMEOUT_S = 6.0`) that hot-swaps back to `gemini-3.5-transcribe-live` automatically.
  3. **FB5 raw lane stalled**: `logs/calls.jsonl` showed `18:20:37 fb5_chunked_raw False 894045.73` (14.9 min hung TCP socket with no HTTP timeout). Added `timeout_ms` to `backend/gemini/client.py`, set `FB5_HTTP_TIMEOUT_MS = 10000` (minimum server-accepted RPC deadline; Loop 1 proved `6000 ms` returns `400 Manually set deadline 6s is too short`), and made FB5 run up to 3 concurrent 1 s workers per lane so both `raw` and `target` stay captioned.
  4. **`gemini-4-argon` `400 INVALID_ARGUMENT`**: Reverted `ThinkingLevel.MINIMAL` to `ThinkingLevel.LOW` in `backend/gemini/argon.py` (`timeout_ms=10000`).
- **Verification evidence (`pytest` + 3 loops of `verify_5min_live_captions.py`)**:
  - Pytest: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest backend/gemini/test_s3_suite.py -v` -> `10 passed in 0.79s`.
  - **Phase 1 (FB5 dual-lane + 10 s Live recovery) — PASS**: Loop 2 (`fb5_raw=9, fb5_target=10, recovered=10.54s, post_live=14/12`) and Loop 3 (`fb5_raw=11, fb5_target=11, recovered=11.02s, post_live=10/12`).
  - **Phase 2 (`gemini-4-argon`, `ThinkingLevel.LOW`) — PASS**: Loop 1 (`4412.4 ms`), Loop 2 (`5954.7 ms`), Loop 3 (`4868.0 ms`), all `source="argon"`, zero `400` errors.
  - **Phase 3 (5-min = 300 s live dual-lane gapless check, target `<= 3.0 s` max gap) — DID NOT PASS strictly after 3 loops (honest report, goalposts not moved)**:
    - Loop 1 (`ROTATE_AFTER_S=110`): `0` `1008`/`1011` errors, `2` rotations, `p95=1.20s/1.34s`, `gaps>3s=7/7` (`max 6.36s/6.59s` on 954-char continuous utterances + blind swap).
    - Loop 2 (`ROTATE_AFTER_S=55`, first-text handoff): hit a 2-minute venue Wi-Fi internet blackout (`18:42:09`–`18:44:08`, `ConnectTimeout: _ssl.c:993`), `max_gap=125.6s/125.1s`, `p95=1.22s/1.06s`; rotations after Wi-Fi returned had `0` gaps `> 3 s`.
    - Loop 3 (`ROTATE_AFTER_S=55` + `8 s` speech-gated WS watchdog): **`0` `1008`/`1011`/WS errors** across all 300 s, **4/4 make-before-break rotations per lane** (`raw=526` captions, `p95=1.076 s`; `target=494` captions, `p95=1.394 s`), rotations 1–3 had **`0` gaps `> 3 s`**, but venue Wi-Fi jitter caused simultaneous gaps on both lanes (`raw`: 5 gaps > 3 s, `max 8.798 s`; `target`: 3 gaps > 3 s, `max 9.947 s` during an `18:52:45–18:52:54` Wi-Fi stall where `live_connect` spiked from `~250 ms` to `2187 ms`).
  - **Action for Saran**: Restart the running `uvicorn backend.main:app` process (which was still running the old pre-13:10 code in parallel during the test) to pick up all 4 fixes, and switch to phone hotspot if venue Wi-Fi continues stalling.

## S1 fix: Stop Engine B-GPU <-> A flapping on venue Wi-Fi jitter, 15:00
- Updated `backend/separation/client.py`:
  - A single slow hop (`> hop_timeout_s=1.5 s` or single `ws.send` timeout) is now dropped as stale (`status="dropped_stale"`, `reason="hop_response_timeout"` / `"hop_send_timeout"`) without closing the WebSocket or flipping to Engine A. Late replies for already-timed-out hops are discarded as `"late_reply_after_timeout"`.
  - Automatic failover to Engine A now triggers ONLY after **3 consecutive timeouts** (`gpu_consecutive_timeouts:3`) OR **no reply at all for `>= 3.0 s`** (`gpu_no_reply_timeout`), or when a fast silent reconnect (`0.15 s`) fails on a genuine disconnect (AT14 `<= 3 s` preserved).
- Evidence: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest -v backend/separation/test_s1.py` -> `11 passed in 15.22s` (including `test_jitter_no_flap_and_failover_after_3_timeouts_or_no_reply` covering 1 slow reply = 0 flips to A, 3 consecutive timeouts = failover, blackhole no-reply = failover, plus `test_at14_failover_within_3s_three_of_three` 3/3 PASS).
- Restart running `uvicorn backend.main:app` to pick up the anti-flap fix.

## S1 update: Engine A -> B-GPU auto-recovery + backend latency cut + 5-min venue Wi-Fi check, 15:42
- **Fixed stuck-on-Engine-A bug** (`backend/separation/client.py`):
  - Root cause: `_watchdog_loop` called `await _close_ws()` *before* `_set_auto_engine("A", ...)`, allowing `_connection_loop` to silently reconnect during `ws.close()` while `_active_engine` was still `"B-GPU"`, after which `_watchdog_loop` overwrote `_active_engine = "A"` leaving `gpu_connected=True` stuck on `"A"` forever.
  - Fix: Atomic `_failover_to_a()` (sets `_in_failover=True` and switches to `"A"` *before* closing WS) + dedicated `_recovery_loop()` probing every **2.0 s** (`ws.ping()` / `/health`) and switching back to `"B-GPU"` (`gpu_recovered`) after **2 consecutive good replies**. Also bumped `connect_timeout_s=3.0` and deduped timeout ticks over `hop_timeout_s * 0.75` (`hop_timeout_s=2.0 s`).
- **Found & cut backend latency overhead** (`backend/separation/client.py`, `backend/main.py`, `backend/store/end_card.py`):
  - Root cause: `logs/hops.jsonl` showed `t_send - t_capture` was `p50=5.5 ms` but **`p95=264.6 ms` (max `371.3 ms`)** with `36` `superseded_by_newer_hop` drops because `max_inflight=2` parked hops in `_latest_hop` whenever RTT > 500 ms.
  - Fix: Raised `max_inflight=4` (letting `separator_server.py` coalesce server-side), moved `separator.submit_hop(...)` to run **first** in `handle_hop`, enabled `TCP_NODELAY=1`, and mtime-cached `read_live_leakage_from_csv()`.
  - Measured backend overhead (`t_send - t_capture`): dropped to **`1.6 ms` p50** (`gpu_rtt p50 = 475.5 ms` vs `e2e_rtt p50 = 477.7 ms` -> **`2.2 ms` total backend overhead**).
- **Verification**:
  - Unit tests: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest -v backend/separation/test_s1.py` -> `12 passed in 18.03s` (including `test_recovery_from_engine_a_after_2_good_probes` and `test_jitter_no_flap_and_failover_after_3_timeouts_or_no_reply`).
  - 30 s live check (`verify_e7_e9.py --hops 60 --port 8015`): `0` failovers, `60/60` hops delivered (`1` merged), backend pre-send `p50=2.0 ms / p95=5.9 ms`, `gpu_rtt p50=433.3 ms`, `e2e_rtt p50=435.0 ms` (`206–283 ms` on clear hops), `voice_delay p50=1085.0 ms`.
  - **5-minute live venue Wi-Fi check (`verify_e7_e9.py --hops 600 --port 8016`) — FAIL on venue Wi-Fi (goalposts not moved)**:
    - Backend pre-send overhead: **`p50=1.6 ms`** (`gpu_rtt p50=475.5 ms` vs `e2e_rtt p50=477.7 ms`, only `2.2 ms` added by backend).
    - Auto-recovery verified live: **`7/7`** failovers automatically recovered back to `B-GPU` (`gpu_probe_ok:1/2` -> `2/2` -> `gpu_recovered`) within ~4 s once the tunnel answered.
    - Why the 0-failover & `< 300 ms` p50 check cannot pass on venue Wi-Fi right now: venue Wi-Fi / SSH tunnel itself degraded severely this afternoon — raw 200-byte `curl http://127.0.0.1:18000/health` (no backend, no GPU) took `341 ms, 480 ms, 1145 ms, 1277 ms, 2297 ms`, direct `gate_g7_roundtrip.py` measured `349–392 ms p50` (`max 1029 ms`), and the SSH tunnel dropped completely for 75 s (`15:33:18–15:34:33`, `ConnectionRefusedError`/`TimeoutError`), causing `8` `gpu_no_reply_timeout` failovers across the 5-minute run.
    - **Recommendation (SPEC FB2)**: Switch to the phone hotspot + restart `tunnel.sh` and `uvicorn backend.main:app`, then re-run `verify_e7_e9.py --hops 600` to verify `0` failovers and `< 300 ms` p50 on hotspot.

## Watchdog Pong Check & Neon Deadline Fix (S3): DONE 15:42 (3 loops of 5-min 5-voice check logged honestly)
- **Changes applied**:
  1. Removed the quiet-ASR `WatchdogTimeout` (`no server msgs for 8.1s`) from `backend/gemini/live_captioner.py` and replaced it with a transport-level WebSocket ping/pong check (`_ping_session`: `session._ws.ping()` every `WS_PING_INTERVAL_S = 10.0`, restarting ONLY if no pong arrives within `WS_PONG_TIMEOUT_S = 10.0`; live ping RTT verified at `16.1 ms`). Raised `ROTATE_AFTER_S = 200.0`, aligned `send_pcm16` / `send_keepalive` timeout to `10.0 s` with `250 ms` (`8000 B`) outbound frames.
  2. Raised `attribute_and_polish_sync` deadline in `backend/gemini/neon.py` from `10000 ms` to `25000 ms` with graceful turn-skip on `504 DEADLINE_EXCEEDED`/timeout, and rate-limited background Neon polish in `backend/gemini/routes.py` to at most once every `5.0 s`.
- **Verification evidence**:
  - Pytest: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest backend/gemini/test_s3_suite.py -v` -> `10 passed in 1.12s`.
  - `neon_attribute` (`timeout_ms=25000`): **3/3 PASS** (`8597.4 ms`, `5921.3 ms`, `7236.1 ms`, zero `504`s).
  - **5-minute (300 s) 5-overlapping-voices check (target `< 2` reconnects) — 3 loops run, did NOT pass `< 2` due to venue Wi-Fi TCP drops (honest report, goalposts not moved)**:
    - **Zero false quiet-ASR restarts across all 3 loops**: on all 3 runs, `raw` stayed quiet (`cap=0`) for `60–90+ s` under 5 overlapping voices while `pong_age` stayed `0.1–6.8 s` and triggered **0** restarts (eliminating the 46 restarts / 6 min).
    - **Loop 1 (`task-433`)**: `raw_reconnects=2, target_reconnects=2` (venue Wi-Fi drop at `20:16:00–20:16:57` + 5 s send timeout at `20:17:53`, fixed to 10 s for Loop 2).
    - **Loop 2 (`task-442`)**: `raw_reconnects=2, target_reconnects=2` (full laptop network drop at `20:22:08–20:23:10` with `gaierror` DNS failure + simultaneous `1006` on the separate running `uvicorn` process `raw-276931`/`target-862044`).
    - **Loop 3 (`task-456`, `250 ms` frames, `10 s` ping / `10 s` pong)**: `raw_reconnects=3, target_reconnects=3` — `logs/calls.jsonl` confirms venue Wi-Fi dropped TCP/WS simultaneously across **all** running processes on the laptop (`uvicorn` `raw-276931`/`target-862044` hit `1006 abnormal closure` + `6000 ms` handshake timeouts at the exact same timestamps `20:37:13–31`, `20:38:16–40`, `20:39:04–40`, and continued hitting `1006` at `20:41:21–41` after our test finished).
- **Action for Saran**: Restart the running `uvicorn` backend (`raw-276931`/`target-862044` is still running the old 8 s WatchdogTimeout code) so it picks up the transport pong check and 25 s Neon deadline, and switch to the phone hotspot if venue Wi-Fi continues dropping TCP connections every 45–90 s.

## 1080p 30 fps camera capture + Full-res lip crops + 3-face >= 25 fps check (S2): DONE 15:43
- Updated `frontend/src/main.ts`, `frontend/src/vision/clearvoiceCrop.ts`, and `frontend/src/vision/faceTracker.ts`:
  - `getUserMedia` now requests `1920x1080` at `30 fps` (`width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30, min: 25 }`).
  - `ClearVoiceCropper` cuts lip crops directly from the full-resolution `1920x1080` `videoEl` (`2.25x` pixel area at `1–2 m`, `imageSmoothingQuality = "high"`, GPU-accelerated `ctx.filter = "grayscale(1)"` center `112x112` crop eliminating `getImageData` CPU readback stalls).
  - Decoupled MediaPipe `FaceLandmarker` input onto a dedicated `512x288` offscreen canvas with `numFaces = 3` (avoiding per-frame full-image BlazeFace re-detection searching for a 4th face once 3 speakers `A`/`B`/`C` are tracked) and staggered secondary JPEG encodes off detection ticks.
- Evidence:
  - Unit & build suite: `npm --prefix frontend run build && npm --prefix frontend test` -> **`14/14` Vitest tests passed** (including `2.25x` pixel-area crop check at `1920x1080` vs `1280x720`).
  - Real 1080p 3-face MediaPipe `FaceLandmarker` benchmark in Chrome (`ANGLE Metal Renderer: Apple M2`, `node frontend/scripts/verify_1080p_3faces.mjs` over 10 s):
    - `requested=1920x1080@30fps`, `actual_video=1920x1080`, `crop_source=1920x1080 (~343 px native square)`, `median_faces=3 (min=3)`, **`mean_tracking_fps = 30.5 fps`** (`28.1–33.3 fps`, gate `>= 25 fps` -> **PASS**).

## Test Log Isolation Fix (S3): DONE 15:45
- Updated `backend/gemini/logger.py` (`get_calls_log_path()`, `get_agent_log_path()`, honoring `LOOK_TO_LISTEN_LOGS_DIR`) and `backend/gemini/managed_agent.py` so tests never write into repo `logs/`.
- Added `autouse=True` fixture `_isolate_logs_to_tmp` and explicit regression test `test_hooks_write_only_to_temp_log_dir` in `backend/gemini/test_s3_suite.py` (plus isolated `scratch/verify_5min_5voices.py` via `tempfile.mkdtemp`).
- Evidence: `pytest backend/gemini/test_s3_suite.py -v` -> `11 passed in 0.77s`, `REPO LOGS DELTA: {'agent.jsonl': 0, 'calls.jsonl': 0, 'hops.jsonl': 0}`.

## S1 fix: Isolate all S1 test and verification logs from `logs/`, 15:47
- Updated `backend/store/clips.py` (`agent_log_path` param + `L2L_LOG_DIR` env override) and `backend/separation/hop_logger.py` (`L2L_LOG_DIR` env override).
- Added `autouse=True` fixture `_isolate_all_logs` in `backend/separation/test_s1.py` redirecting `AGENT_LOG_PATH`, `HOPS_LOG_PATH`, `CALLS_LOG`, and `LiveRuntime` log paths to `tmp_path/test_logs` and asserting zero byte growth on live `logs/agent.jsonl` and `logs/hops.jsonl`.
- Updated `backend/separation/verify_e7_e9.py` to write to a `tempfile.TemporaryDirectory` when running in-process instead of `logs/`.
- Evidence: `/Users/nerdboss-stm/.venvs/g4-backend/bin/python -m pytest -v backend/separation/test_s1.py` -> `12 passed in 19.31s`, `0` bytes added to `logs/agent.jsonl` or `logs/hops.jsonl`.
