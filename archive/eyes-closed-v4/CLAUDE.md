# CLAUDE.md: rules for every session in this repo

Read SPEC.md, PLAN.md and DEMO.md completely before any task. SPEC.md is the source of truth.
The project is Eyes Closed. Ignore archive/. It holds old versions.

## Never
- Never run git commit. Saran makes every commit. Never add Co-Authored-By trailers.
- Never print, log or commit API keys or OAuth tokens. Secrets come only from .env, or the egress proxy inside the Managed Agent.
- Never put a model call inside the 30 fps loop.
- Never put the Managed Agent in the live loop.
- Never mark a step PROVEN unless its check passes and Decision 1 is above the threshold in contracts/decision.md.
- Never run agent-written checks outside the check runner (subprocess, AST allowlist, 50 ms timeout).
- Never put a kit list or a fixed object list in code or prompts. Scans are open vocabulary.
- Never add code that assumes what is in the bag, what the mystery object is, or which second errand comes next.
- Never stage a mistake, and never show a cached plan or a recording without its time on screen.
- Never show a number on screen that does not come from runs.csv, steps.csv, cases.csv or the live logs.
- Never add a feature that is not in SPEC.md. Write the idea in NOTES.md instead.
- Never fake a result. Pass or fail comes only from a live run or a logged test.
- Never show a full private email on screen. Parsed fields only.
- Never claim "beats the baseline" unless the gate rule in SPEC passes.

## Always
- Change files in contracts/ only when a task says so. Everything else reads and writes them.
- Log every model call to logs/calls.jsonl: time, model, thinking level, latency_ms, input and output tokens, estimated cost, and the probability for Decisions API calls.
- Log every agent event (tool call, file written, test result, hook decision) to logs/agent.jsonl. The UI streams from it.
- Log every run to runs.csv and every step to steps.csv, failures included.
- Put every external dependency behind a fallback flag (SPEC Fallbacks). Failures degrade; they never crash the demo.
- Everything Saran needs on stage must work by voice. He is blindfolded.
- Mark a task done only when its check in PLAN.md passes. Write the evidence (command, output, number) in PROGRESS.md.
- Keep the UI readable from the back of a room on a projector: counters at least 40 px, text at least 28 px, high contrast.

## Stack
- Frontend: Vite and TypeScript, MediaPipe Tasks Vision Hand Landmarker, canvas overlay, WebAudio tone, speechSynthesis for guidance words, browser speech recognition or the Live API for voice commands (check the Live API docs; ephemeral token from the backend).
- Backend: Python 3.12, FastAPI, google-genai SDK (Hydrogen, Neon, Decisions API), websockets, pytest, a check runner subprocess, Google Calendar for the close.
- Agent: one Gemini Managed Agent environment. agents/eyes-closed/AGENTS.md, skills/eyes-closed-compiler/SKILL.md, .agents/hooks.json, hooks/gate_release.py, hooks/gate_regression.py.
- Models: see SPEC.md. Use the exact ids confirmed in AI Studio.

## Sessions (run in parallel)
- S1: backend, Hydrogen perception (scan, holding, reads, fast plan), Decisions client, state builder, change detector, check runner, mystery object
- S2: frontend, guidance tuned for a talking presenter, voice commands, UI panels sized for a projector, the END CARD
- S3: Managed Agent: Neon compile, hooks, tools, learner, trigger, calendar close
- S4: demo owner from hour one: the board, room setup timing, Sets A, B and C, the failure card, mentor feedback, the X clip, blindfolded rehearsals, mock-room pitches, recordings, README
