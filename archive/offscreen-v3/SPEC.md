# SPEC.md: Offscreen (v3, room format)

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM.
Judging: round 1 in 6 separate rooms, then a final showdown in front of everyone.
Old versions are in archive/. v1 read as staged. v2 depended on strangers scanning a QR code. Do not use either.

## One line
Your agent, off the screen.

## What it is
A personal agent for errands that cross your apps and the physical world.
It scans whatever is in front of it, reads what the errand needs (email, calendar, the web), plans, writes a check for every step, guides any pair of hands live, stops mistakes before they land, and closes the errand back on a screen.

Friend version: "Gemini's agent pays your bills. This one packs your bag, through someone else's hands."

## Organic rules (these beat every other section)
- The errand is real: Saran's actual upcoming trip, from his real email and calendar. Nothing is invented for the demo.
- The objects are real: Saran's backpack, dumped as it is at that moment. Nobody packs it for the demo.
- One object comes from the room: borrowed from a judge or picked up in the room. We never know what it will be.
- The same pile gets a second errand on stage, so the judges see a different plan from the same objects.
- No object list anywhere in the code. The scan is open vocabulary.
- No staged mistakes. Zero stops is a fine outcome.
- One continuous take with a wall clock on screen. Any recording or cached plan shows its time.

## Why now (said out loud)
- Tue Nov 17: Tasks in Gemini, on Gemini 4 Hydrogen, went free to hundreds of millions of people. Muse, Dots, Duet and Instinct do the same kind of work. Every one ends in an app or a phone call.
- Agents already hire people for physical work. RentAHuman (YC) says it reached 500,000 users in two weeks. Its agents send instructions and wait for proof of completion. Nothing watches the work.
- Hydrogen (GA Nov 12) folds Robotics ER 2 skills into core Gemini 4. None of those agents uses that half. Offscreen does.
- Closest prior: Project Astra's I/O 2025 bike video. The person did the physical work and checked it himself.

## Idea gate (Sep 13 system)
- Person: Saran, real trip. Market figures: Instinct raised $1B (Sep 2026); RentAHuman's 500,000 users.
- Sponsor product load-bearing and said out loud: Gemini 4 Hydrogen, Gemini Managed Agents.
- Mechanism in one picture: Architecture below.
- Number that moves on screen: steps verified, stops before landing, raw vs Offscreen counts from today's runs.
- Opening shot: Saran tips his backpack onto the board, his teammate pulls on a sleep mask, and Gemini labels every object on the big screen.

## What it can do, said plainly
- Yes: errands that come down to the right things in the right places under real rules. Pack, sort, recycle, set up, gather, return.
- No: folding, tying, assembling, cooking, tools, heat. It says so.

## Claims (all live)
- C1 Scan. Open-vocabulary scan of a dumped bag, labels on screen within 5 s.
- C2 Compile. The Managed Agent reads the real email, fetches the rule pages, writes a plan and executable checks, tests them against the live scan. A hook releases the plan only when the tests pass.
- C3 Guide. Local hand tracking at 30 fps plus Hydrogen locations guide a blindfolded person with a distance tone and short words.
- C4 Verify. Hydrogen confirms what the hand holds and reads labels on hold-up.
- C5 Stop before landing. A held item that breaks a rule triggers STOP before it reaches the wrong place.
- C6 Adapt. A borrowed object enters the pile mid-run. It is scanned, judged against the rules and placed.
- C7 Second errand. A new errand on the same pile gets a new plan on screen within 10 s (marked "unverified" until its checks land).
- C8 Close. A calendar event in Saran's real calendar after he says yes.
- C9 Better than raw. Today's runs on different errands, alternating raw (same model, same camera, no harness) and Offscreen.

## Do not claim
- "First ever", robot control, medical use.
- "Beats raw" unless the gate rule in Runs passes.
- Anything not on screen.

## The demo board (built Friday night, carried into every room)
- A tray or a stiff board about 60 x 40 cm with a rim, so a dumped bag stays in frame.
- A camera mast fixed to the board (cardboard or a stack taped together), phone 60 to 80 cm above the center. The camera never moves relative to the board, so nothing needs recalibrating between rooms.
- Zones are areas on the board marked with tape: "bag" (the open backpack sits there) and "stays home". Other zones come from the scan per errand.
- One bag: Saran's real backpack. One sleep mask. One earbud for the hands teammate.
- Setup in the room: 60 s or less (AT11).

## Architecture
```
Browser, 30 fps, no model calls
  camera -> MediaPipe hands -> guidance (tone on speaker, words in one earbud) -> overlay, STOP
      | websocket 30 Hz
      v
Backend (FastAPI)
  Hydrogen: open scan (start, after each pick, on change), verify on grasp, read on hold-up
  change detector (new object -> rescan), state builder 10 Hz, check runner 10 Hz -> STOP / OK
  fast path: Hydrogen picks a first plan in seconds, labeled "unverified" until checks land
  calendar write after approval; logs/calls.jsonl, logs/agent.jsonl, runs.csv
      ^ plan.json + checks/ (only after the release hook passes)
      | errand.json + scan.json + emails.json (Files API)
Managed Agent (Google sandbox, never in the live loop)
  compile: email + rule pages -> plan + checks + tests -> release hook
  learn: trigger every 30 min -> lessons + regression cases (regression hook)
```

Layer rules:
- L0 Browser at 30 fps, no model calls.
- L1 Hydrogen: open scan, verify, read. Thinking low; medium for reads.
- L2 Check runner: released checks only, subprocess, AST allowlist (math, json), 50 ms timeout.
- L3 Managed Agent: compile and learn. Never in the live loop.

## Managed Agent design
- Environment: one persistent environment named offscreen. Files persist across runs.
- Skill: skills/offscreen-compiler/SKILL.md: errand to plan.json and checks/, the check API, test patterns, the "can't do" list.
- AGENTS.md: cite a source URL for every rule; use only objects in scan.json; ask for a hold-up read when a rule depends on a label; say "can't do" plainly.
- Tools: built-in shell and files; web fetch for rule pages (allowlist per errand: tsa.gov, faa.gov, nyc.gov, manufacturer pages); client-side tools our backend executes: release_plan, create_calendar_event.
- Hooks (.agents/hooks.json):
  - pre_tool_execution on release_plan: hooks/gate_release.py runs pytest on checks/ against scan.json and synthetic traces. Deny returns failing check ids and reasons.
  - pre_tool_execution on writes under skills/: hooks/gate_regression.py runs every stored regression case. Deny if one breaks.
  - post_tool_execution on all tools: append to the agent log.
- Trigger: every 30 minutes, the learner reads new runs, writes lessons.md, adds regression cases, updates the skill through the regression hook.
- Streaming: the UI shows agent events as they happen.
- Fallback: no client-side tools means the RELEASED file pattern.

## Contracts (E1 creates these first)
- contracts/errand.schema.json: id, text, source (email|calendar|spoken), time.
- contracts/state.schema.json: t; hands [{side, landmarks 21 x [x, y], open, pos}]; objects {id: {label, pos [y, x] 0 to 1000, box, status on_board|in_hand|in_zone, zone, attrs, source scan|borrowed}}; zones {id: polygon}; holding; events.
- contracts/plan.schema.json: errand_id; sources [{id, kind, ref, fetched_at}]; objects [{id, dest_zone, why, rule_ids, needs_read}]; rules [{id, text, source_id}]; steps; close [{kind calendar, payload, needs_approval}]; verified (bool).
- contracts/check_api.md: CHECK_ID, RULE_ID, SOURCE_URL, allowed(object_id, zone_id, state, plan) -> (bool, reason), satisfied(state, plan) -> (bool, reason). Standard library math and json only, no I/O, 50 ms max. tests/test_<check>.py with one pass and one fail case.
- contracts/run.schema.json: the runs.csv columns.

## Models
| Role | Model | Notes |
| --- | --- | --- |
| Open scan, verify, fast path | gemini-4-hydrogen, thinking low | Confirm id and output format Friday |
| Label reads | gemini-4-hydrogen, thinking medium | Argon only if Hydrogen fails G3 |
| Agent | Managed Agent default (3.8 Flash) | Gemini 4 if accepted |
| Raw arm | gemini-4-hydrogen live stream in AI Studio | Same errand, same pile, no harness |

## UI (readable from the back of a room)
- Left 60 percent: live camera with object labels, hand skeleton, zones, target ring, "holding" chip, red border on STOP, wall clock and run timer.
- Right: PLAN (steps and status, "unverified" tag when it applies), AGENT stream (one line per event, with URLs), COUNTERS (steps verified, stops before landing, Hydrogen p50).
- END CARD: "Offscreen. Your agent, off the screen." Today's runs, raw vs Offscreen counts, repo link and QR. Shown in the last 10 s.
- Counters at least 40 px, text at least 28 px. Projectors wash out color, so use high contrast.

## Acceptance tests
- AT1 Open scan: Saran's dumped bag, ordinary room light, 20 or more objects. At least 90 percent found, at most 10 percent wrong labels, p50 at or under 3 s.
- AT2 Hands: at least 25 fps with overlay; tone within 100 ms of the frame.
- AT3 Stop: 10 deliberate wrong moves. STOP before contact in at least 9.
- AT4 Verify and read: holding correct at least 9 of 10; label reads at least 8 of 10.
- AT5 Compile and gate: the real trip errand compiles to a valid plan with checks; a planted broken check is denied and fixed, 3 of 3; compile p50 at or under 45 s.
- AT6 Borrowed object: an object added mid-run is labeled, judged and given a zone within 5 s, 5 of 5, using objects not seen before that day.
- AT7 Second errand: a new errand on the same pile shows a plan within 10 s, and its checks land within 60 s, 3 of 3.
- AT8 Close: the calendar event appears only after approval, 3 of 3.
- AT9 Runs: at least 6 raw and 6 Offscreen on different errands, alternating, blindfolded.
- AT10 Rehearsal: 10 full runs on different bags and errands, 8 clean.
- AT11 Room setup: from walking in to the first label on the projector, 60 s or less, 3 of 3 timed.

## WOW test (checkable)
In the judging room, live: setup in 60 s or less. Saran dumps his real bag. The agent compiles the real trip errand with its hook decision in the log. A blindfolded teammate packs it with zero violations landed. One borrowed object is handled. A second errand gets a new plan from the same pile. The calendar event appears after "yes". Under 3:00.
Evidence: the runs.csv row and the room recording if allowed.

## Runs and the "beats raw" gate
- Fixed now, before data: success means every planned object in its zone and zero violations landed.
- Different errands and different piles across the day. Alternate arms: raw, Offscreen, raw, Offscreen. Same person, blindfolded.
- Say "beats raw" only if Offscreen succeeds in at least 2 more runs than raw, out of at least 6 each. Report counts.

## Out of scope
Robot arms, simulation, gaze control, a phone app, accounts, folding or assembly errands, an errand queue.

## Fallbacks (each behind a flag)
- FB1 Hydrogen slow (over 3 s): scan on change only, verify only on grasp.
- FB2 Compile slow (over 45 s): the fast path runs labeled "unverified" until checks land.
- FB3 No client-side tools: the RELEASED file pattern.
- FB4 No projector or a bad cable: turn the laptop to the judges. The UI is sized for that.
- FB5 Room Wi-Fi: phone hotspot.
- FB6 Live voice fails: type the second errand.
- FB7 Everything else: the 60 s recording of the best run of the day, labeled with its time.

## Rules
- All project code is written on event day. Friday is learning, gate tests, the demo board and pitch practice.
- Declare open-source libraries in the README.
- The screen never shows a full private email. Parsed fields only.

## Go deeper (Oct 15 rule)
1. What a top professional would do: open with an action instead of a slide, use one borrowed object to prove nothing is set up (a stage magician's proof), keep one continuous take with a clock, prepare two openings for two kinds of judges, and rehearse setup as hard as the pitch.
2. Rawest material: the bag as it is, the real email, live rule pages, raw frames and model JSON.
3. Methods and tools: open-vocabulary scan with Hydrogen; MediaPipe; a WebAudio tone; Managed Agents skills, hooks, triggers and streaming; pytest; an AST allowlist; timed mock-room rehearsals.
4. Proof that is not us: the borrowed object, the blindfold, the raw arm, source URLs on every rule, the real calendar.

## After the event
- Release code and the run dataset (frames, landmarks, model I/O, outcomes) on Hugging Face.
- Paper: real errands done by human hands guided by a model, raw vs harness. The real-world counterpart to Embodied Web Agents (NeurIPS 2025 Datasets and Benchmarks), which used simulation.
- Send the repo and video to the judges you met.

## Open questions (answer Friday or at check-in)
- Slot length in the room, Q&A length, projector and HDMI, and which judges sit in which room.
- How many teams go from each room to the final.
- Managed Agents prize criteria.
- Does a Managed Agent accept gemini-4-hydrogen? Client-side function tools? Tool names for hook matchers?
