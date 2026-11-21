# CLAUDE.md: rules for every session in this repo

Read SPEC.md, PLAN.md, PROGRESS.md, DEMO.md and DESIGN.md completely before any task. AGENTS.md holds the same rules for Antigravity; keep them identical. SPEC.md is the source of truth.
The project is Look to Listen. Ignore archive/. It holds old versions.

## How each session works
- Take the next task for your session in PLAN.md. Build it, run its check, fix, run again. Loop until the check passes.
- Write the evidence (command, output, number) in PROGRESS.md before taking the next task.
- If a check cannot pass after 3 loops, write why in PROGRESS.md and tell Saran. Do not move the goalposts.

## Never
- Never run git commit. Saran makes every commit. Never add Co-Authored-By trailers.
- Never print, log or commit API keys or OAuth tokens. Secrets come only from .env, or the egress proxy inside the Managed Agent.
- Never put a model call inside the 30 fps browser loop.
- Never put the Managed Agent inside the live loop.
- Never save, send or log audio or text of a person without a consent record. gate_privacy.py enforces it for the agent; the backend enforces it for clips/.
- Never let robot_act run for a face that is not the current target. gate_command.py enforces it.
- Never queue hops. If a hop is stale (older than one hop length), drop it. Live beats complete.
- Never store audio on the GPU server. It keeps 3 s in memory per session and drops it on disconnect.
- Never put the RunPod API key, SEPARATOR_TOKEN or SEPARATOR_URL in code or logs. They live in .env and the pod's environment.
- Never release a config without the regression suite. gate_release.py enforces it.
- Never download models at the venue. They are in ../gemini4-prep (models/, clearvoice_home/, third_party/).
- Never edit installed packages, except the ClearVoice CUDA patch that setup_mac.sh already applied.
- Never play a pre-recorded clip as if it were live. Any recording on screen shows its time.
- Never put fixed phrases, names or expected words in code or prompts, except vocab.json learned from consenting people.
- Never add code that assumes who will talk or what they will say.
- Never show a number on screen that does not come from the CSV files or the live logs.
- Never add a feature that is not in SPEC.md. Write the idea in NOTES.md instead.
- Never fake a result. Pass or fail comes only from a live run or a logged test.
- Never claim "beats the baseline" unless the gate rules in SPEC pass. Never claim zero delay; show the measured delay. Never claim world models or medical use.

## Always
- Change files in contracts/ only when a task says so. Everything else reads and writes them.
- Log every model call to logs/calls.jsonl: time, model, thinking level, latency_ms, input and output tokens, estimated cost, and the probability for Decisions API calls.
- Log every agent event (tool call, file written, eval result, hook decision) to logs/agent.jsonl. The UI streams from it.
- Log every Set C clip to clips.csv, every labeled window to decisions.csv, every robot command pair to robot.csv, failures included.
- Put every external dependency behind a fallback flag (SPEC Fallbacks). Failures degrade; they never crash the demo.
- Run both engines on the same clips when comparing them.
- Keep the UI readable from the back of a room on a projector: captions at least 32 px, counters at least 40 px, high contrast.

## Stack
- Frontend: Vite and TypeScript, getUserMedia, MediaPipe Tasks Vision Face Landmarker (model file ../gemini4-prep/models/face_landmarker.task), canvas overlay, WebSocket to the backend.
- Backend: Python 3.12 in ~/.venvs/g4-backend. FastAPI, google-genai SDK (Hydrogen, Hydrogen Live, Neon, Argon, Decisions API), websockets, opencv-python-headless, jiwer, pytest, mujoco (stretch only).
- Separation server (Engine B-GPU, the base): a RunPod pod with CUDA (setup in ../gemini4-prep/GPU_POD.md). Python, FastAPI, one WebSocket /separate and /health, ClearVoice AV_MossFormer2_TSE_16K loaded once, working directory /workspace/clearvoice_home. Contract in SPEC.
- Engine B-Mac (backup): the same model in ~/.venvs/g4-audio with the working directory ../gemini4-prep/clearvoice_home, only if G1-Mac allows.
- ffmpeg: on PATH from ~/.local/bin (linked by setup_mac.sh).
- Agent: one Gemini Managed Agent environment in agent_env/: agent_env/AGENTS.md, agent_env/skills/listener/SKILL.md, agent_env/.agents/hooks.json, agent_env/hooks/gate_release.py, gate_privacy.py, gate_command.py. Never put AGENTS.md or .agents/ for it at the repo root (Antigravity would load them as its own).
- Models: see SPEC.md. Use the exact ids confirmed in AI Studio.

## Sessions (run in parallel)
- S1: GPU pod, separation server, separation client in the backend, playback, delay logging, failover, clip store, consent records
- S2: contracts, frontend, face tracking, face crops and hop packing, overlay, the two live lanes, target switching, counters, DELAY meter, AGENT stream, MEMORY box, ROBOT panel, END CARD
- S3: Hydrogen Live sessions for both lanes, Decision 1 speaking, leakage guard, Engine A, Neon, Argon, robot R1, Managed Agent, hooks, tuner
- S4: demo owner from hour one: gate tests, Sets C, D and R, scoring, where it breaks, mentor feedback, the X clip, rehearsals, mock-room pitches, recordings, README

## Sessions in parallel (Antigravity or Claude Code)
- A conversation that starts with "You are S1" (S2, S3, S4) is that session. Take its next unfinished task in PLAN.md. PROGRESS.md says what is done.
- Parallel agents overwrite each other's files without warning. Write only in the paths your session owns:
  - S1: backend/main.py, backend/separation/, backend/playback/, backend/store/, logs/hops.jsonl
  - S2: contracts/, frontend/
  - S3: backend/gemini/, backend/robot/, agent_env/, vocab.json
  - S4: evals/, sets/, README.md, clips.csv, decisions.csv, robot.csv
  - Shared, append only: PROGRESS.md, NOTES.md, gate_log.csv, logs/calls.jsonl, logs/agent.jsonl
  - Only Saran edits SPEC.md, PLAN.md, DEMO.md, DESIGN.md, AGENTS.md and CLAUDE.md.
- Need a change in a file you do not own? Write the request in NOTES.md, addressed to the owning session.
- S3 puts its API routes in backend/gemini/routes.py. S1's backend/main.py includes that router.

## GPU pod (E1 and E2 are done)
- The separation server runs on the pod and restarts itself. Do not rewrite it. Its code is in ../gemini4-prep/pod/.
- The laptop reaches it at SEPARATOR_URL (ws://localhost:18000/separate) through ../gemini4-prep/pod/tunnel.sh. Saran runs the tunnel in his own Terminal tab. Agents never read ~/.ssh.
- Check: curl -s localhost:18000/health. Round trip test: python ../gemini4-prep/gate_g7_roundtrip.py --env .env --hops 50 --label wifi
