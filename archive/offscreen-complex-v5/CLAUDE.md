# CLAUDE.md: rules for every session in this repo

Read SPEC.md, PLAN.md and DEMO.md completely before any task. SPEC.md is the source of truth.
The project is Offscreen (complex base). Ignore archive/. It holds old versions.

## How each session works
- Take the next task for your session in PLAN.md. Build it, run its check, fix, run again. Loop until the check passes.
- Write the evidence (command, output, number) in PROGRESS.md before taking the next task.
- If a check cannot pass after 3 loops, write why in PROGRESS.md and tell Saran. Do not move the goalposts.

## Never
- Never run git commit. Saran makes every commit. Never add Co-Authored-By trailers.
- Never print, log or commit API keys or OAuth tokens. Secrets come only from .env, or the egress proxy inside the Managed Agent.
- Never put a model call inside the 30 fps loop or the recorder loop.
- Never put the Managed Agent inside the 30 fps loop. execute(plan_id) runs the loop locally.
- Never stop or pause the recorder for a code change. Restart it only through its own command, and log every gap.
- Never mark a step PROVEN unless its check passes and Decision 1 is above the threshold in contracts/decision.md.
- Never complete a checkout without a spoken approval id. gate_spend.py enforces it.
- Never run agent-written checks outside the check runner (subprocess, AST allowlist, 50 ms timeout).
- Never put a kit list or a fixed object list in code or prompts. Everything is open vocabulary.
- Never add code that assumes what is in the bag, what a judge will ask, or what is missing.
- Never stage a mistake, and never show a cached plan, answer or recording without its time on screen.
- Never show a number on screen that does not come from the CSV files or the live logs.
- Never record or transcribe anyone outside our team. Crop or blur.
- Never add a feature that is not in SPEC.md. Write the idea in NOTES.md instead.
- Never fake a result. Pass or fail comes only from a live run or a logged test.
- Never claim "beats the baseline" unless the gate rules in SPEC pass.

## Always
- Change files in contracts/ only when a task says so. Everything else reads and writes them.
- Log every model call to logs/calls.jsonl: time, model, thinking level, latency_ms, input and output tokens, estimated cost, and the probability for Decisions API calls.
- Log every agent event (tool call, file written, test result, hook decision) to logs/agent.jsonl. The UI streams from it.
- Log every memory answer to memory_qa.csv, every run to runs.csv, every step to steps.csv, failures included.
- Put every external dependency behind a fallback flag (SPEC Fallbacks). Failures degrade; they never crash the demo.
- Everything Saran needs on stage must work by voice.
- Keep the UI readable from the back of a room on a projector: counters at least 40 px, text at least 28 px, high contrast.

## Stack
- Recorder: Python 3.12, OpenCV, ffmpeg for segments.
- Frontend: Vite and TypeScript, MediaPipe Tasks Vision Hand Landmarker, canvas overlay, WebAudio tone, speechSynthesis, browser speech recognition or the Live API for commands (ephemeral token from the backend).
- Backend: Python 3.12, FastAPI, google-genai SDK (Hydrogen, Argon, Neon, Decisions API), websockets, pytest, a check runner subprocess, an MCP client for Shop MCP, Google Calendar.
- Agent: one Gemini Managed Agent environment. agents/offscreen/AGENTS.md, skills/offscreen/SKILL.md, .agents/hooks.json, hooks/gate_release.py, hooks/gate_spend.py, hooks/gate_regression.py.
- Models: see SPEC.md. Use the exact ids confirmed in AI Studio.

## Sessions (run in parallel)
- S1: recorder, change detector, backend, open scan, holding, reads, Decisions client, state builder, check runner
- S2: frontend, guidance, voice, UI (TIMELINE, ANSWER, PLAN, AGENT, COUNTERS, END CARD)
- S3: event labeler, memory query, plan with memory, Managed Agent orchestration, hooks, wallet, learner
- S4: demo owner from hour one: gate tests, board, room setup, Sets M, L and S, where it breaks, mentor feedback, the X clip, rehearsals, mock-room pitches, recordings, README
