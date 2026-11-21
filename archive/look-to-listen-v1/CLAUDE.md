# CLAUDE.md: rules for every session in this repo

Read SPEC.md, PLAN.md and DEMO.md completely before any task. SPEC.md is the source of truth.
The project is Look to Listen. Ignore archive/. It holds old versions.

## How each session works
- Take the next task for your session in PLAN.md. Build it, run its check, fix, run again. Loop until the check passes.
- Write the evidence (command, output, number) in PROGRESS.md before taking the next task.
- If a check cannot pass after 3 loops, write why in PROGRESS.md and tell Saran. Do not move the goalposts.

## Never
- Never run git commit. Saran makes every commit. Never add Co-Authored-By trailers.
- Never print, log or commit API keys or OAuth tokens. Secrets come only from .env, or the egress proxy inside the Managed Agent.
- Never put a model call inside the 30 fps browser loop or the audio worker loop.
- Never put the Managed Agent inside the live loop.
- Never save, send or log audio or text of a person without a consent record. gate_privacy.py enforces it for the agent; the backend enforces it for clips/.
- Never release a config without the regression suite. gate_release.py enforces it.
- Never play a recording as if it were live. Any recording on screen shows its time.
- Never put fixed phrases, names or expected words in code or prompts, except vocab.json learned from consenting people.
- Never add code that assumes who will talk or what they will say.
- Never show a number on screen that does not come from the CSV files or the live logs.
- Never add a feature that is not in SPEC.md. Write the idea in NOTES.md instead.
- Never fake a result. Pass or fail comes only from a live run or a logged test.
- Never claim "beats the baseline" unless the gate rules in SPEC pass.
- Never claim medical use.

## Always
- Change files in contracts/ only when a task says so. Everything else reads and writes them.
- Log every model call to logs/calls.jsonl: time, model, thinking level, latency_ms, input and output tokens, estimated cost, and the probability for Decisions API calls.
- Log every agent event (tool call, file written, eval result, hook decision) to logs/agent.jsonl. The UI streams from it.
- Log every Set C clip to clips.csv and every labeled window to decisions.csv, failures included.
- Put every external dependency behind a fallback flag (SPEC Fallbacks). Failures degrade; they never crash the demo.
- Keep the raw lane and the target lane on the same audio and the same captioner, so the comparison is fair.
- Keep the UI readable from the back of a room on a projector: captions at least 32 px, counters at least 40 px, high contrast.

## Stack
- Frontend: Vite and TypeScript, getUserMedia, MediaPipe Tasks Vision Face Landmarker, canvas overlay, WebSocket to the backend.
- Audio worker: Python 3.12, RAVEN (declared in the README), sounddevice, numpy.
- Backend: Python 3.12, FastAPI, google-genai SDK (Hydrogen, Hydrogen Live, Neon, Argon, Decisions API), websockets, jiwer, pytest.
- Agent: one Gemini Managed Agent environment. agents/listener/AGENTS.md, skills/listener/SKILL.md, .agents/hooks.json, hooks/gate_release.py, hooks/gate_privacy.py.
- Models: see SPEC.md. Use the exact ids confirmed in AI Studio.

## Sessions (run in parallel)
- S1: audio worker and RAVEN, backend skeleton, contracts, clip store, consent records
- S2: frontend, face tracking, overlay, the two lanes, counters, AGENT stream, MEMORY box, END CARD
- S3: captioner, raw lane, Decision 1 speaking, leakage guard, Neon, Argon, Managed Agent, hooks, tuner
- S4: demo owner from hour one: gate tests, Set C and Set D, scoring, where it breaks, mentor feedback, the X clip, rehearsals, mock-room pitches, recordings, README
