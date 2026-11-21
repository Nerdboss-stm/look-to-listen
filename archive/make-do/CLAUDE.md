# CLAUDE.md: rules for every session in this repo

Read SPEC.md and PLAN.md completely before starting any task. SPEC.md is the source of truth.

## Never
- Never run git commit. Saran makes every commit. Never add Co-Authored-By trailers.
- Never print, log or commit API keys. Secrets come only from .env.
- Never put a model call inside the 30 fps loop.
- Never put the Managed Agent in the live loop.
- Never add a feature that is not in SPEC.md. Write the idea in NOTES.md instead.
- Never fake a result. Pass or fail comes only from the physical test.

## Always
- Change files in contracts/ only when a task says so. Everything else reads and writes them.
- Log every model call to logs/calls.jsonl: time, model, latency_ms, input and output tokens, estimated cost.
- Put every external dependency behind a fallback flag. Failures degrade; they never crash the demo.
- Mark a task done only when its check in PLAN.md passes. Write the evidence (command, output, number) in PROGRESS.md.
- Keep the UI readable from 2 meters: counters at least 32 px, instructions at least 24 px, high contrast.

## Stack
- Frontend: Vite and TypeScript, MediaPipe Tasks Vision Hand Landmarker, canvas overlay, Live API from the browser with an ephemeral token minted by the backend (check the Live API docs).
- Backend: Python 3.12, FastAPI, google-genai SDK, websockets to the frontend.
- Learner: a Gemini Managed Agent defined in agents/learner/AGENTS.md, hooks in .agents/hooks.json, hook scripts in hooks/.
- Models: see SPEC.md. Use the exact ids confirmed in AI Studio.

## Sessions (run in parallel)
- S1: backend and design harness
- S2: frontend, live loop and UI
- S3: Managed Agent learner, hooks, export
- S4: demo owner from hour one: script, kit, trials, rehearsal, recordings
