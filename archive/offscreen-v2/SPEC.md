# SPEC.md: Offscreen (v2, organic)

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM.
v1 (a curated kit and one planned flight demo) is in archive/offscreen-v1/. It read as staged. Do not use it.

## One line
Your agent, off the screen. We don't pick its jobs.

## What it is
A personal agent for errands that cross your apps and the physical world.
Anyone in the room gives it an errand. It scans whatever is on the table, reads what the errand needs (the web, and for Saran's own errands his email and calendar), plans, writes checks for every step, guides any pair of hands through it live, stops mistakes before they land, and reports the result back on a screen.

Friend version: "Gemini's agent pays your bills. This one does your errands with someone's hands, and you pick the errand."

## Organic rules (these beat every other section)
- We never choose the errand on stage. It comes from the room queue or from a judge.
- We never curate objects for an errand. The table is what it is: our real hackathon table plus anything people leave on it.
- We never plant a mistake.
- Every input on screen shows where it came from and when (sender, time, URL).
- One continuous take with a wall clock on screen.
- Every run of the day goes on the wall, failures included.
- If a plan is not the live one, the screen labels it with its time.

## Opening shot (one sentence)
A stranger's errand arrives on screen with their name and time, Gemini scans a messy hackathon table it has never seen, and a blindfolded teammate does the errand right while Gemini stops her hand before a mistake lands.

## Why now (say it out loud)
- Tue Nov 17: Tasks in Gemini, on Gemini 4 Hydrogen, went free to hundreds of millions of people. Muse, Dots, Duet and Instinct do the same kind of work. Every one ends in an app or a phone call.
- Hydrogen (GA Nov 12) folds Robotics ER 2 skills into core Gemini 4. None of those agents uses that half. Offscreen does.
- Closest prior: Project Astra's I/O 2025 bike video. Astra found the manual and a video and called a shop. The person did the physical work and checked it himself.
- Staging risk is real for these judges: Google's own Dec 2023 "Hands-on with Gemini" video was not real time. Live audience requests are the known cure (OpenAI ran requests from X live at the GPT-4o launch). Offscreen runs the room's errands.

## Idea gate (Sep 13 system)
- Person: whoever sent the errand, named on screen. For Saran's own errands: his real calendar and email.
- Dollar figure: personal agents are the hottest consumer AI race (Instinct raised $1B in Sep 2026). All of them stop at the screen.
- Sponsor product load-bearing and said out loud: Gemini 4 Hydrogen embodied reasoning, Gemini Managed Agents.
- Mechanism in one picture: Architecture below.
- Number that moves on screen: steps verified, stops before landing, the wall's raw vs Offscreen counts.
- Opening shot: above.

## What it can do, said plainly
- Yes: errands that come down to the right things in the right places under real rules. Pack, sort, recycle, set up, gather, return, split mine from yours.
- No: folding, tying, assembling, cooking, tools, heat. The agent says so when an errand needs them.
- Saying the limit out loud is part of the credibility.

## Claims (all live)
- C1 Intake. Errands arrive from the room all day, each with sender and time.
- C2 Triage. For each errand the agent decides doable or not with this table, and says what is missing.
- C3 Compile. The agent researches the errand's rules live, writes a plan and executable checks, tests them against the live scan, and a hook releases the plan only when the tests pass.
- C4 Guide. Local hand tracking at 30 fps plus Hydrogen locations guide a blindfolded person with a distance tone and short words.
- C5 Verify. Hydrogen confirms what the hand holds and reads labels on hold-up.
- C6 Stop before landing. A held item that breaks a rule triggers STOP before it reaches the wrong place.
- C7 Adapt. Anyone can move or add an object mid-run. It rescans and replans.
- C8 Close. The result goes back to the sender on screen (Discord or email), or to Saran's calendar after approval.
- C9 Better than raw. Errands from the queue, alternating raw (same model, same table, no harness) and Offscreen. Counts on the wall.

## Do not claim
- "First ever", robot control, medical use.
- "Beats raw" unless the gate rule in Trials passes.
- Anything not on screen.

## Errand intake
- A short link and QR code on the screen and in the event Discord: "Give our agent an errand you would do with your hands." Fields: errand, handle (optional).
- Build: a Google Form feeding a Sheet. The backend polls it every 15 s. No custom web form.
- Each errand: id, text, from, time. Shown in the QUEUE panel with its triage status: doable, needs X, can't do (reason).
- On stage: run the oldest doable errand. A judge's errand, if given, goes to the front.
- Empty queue: the agent proposes one errand from the scene and the time of day, and the screen says so.
- Post the link in Discord at 10 AM, 1 PM and 4 PM. Teammates may share it. Nobody on the team writes errands.

## The table
- Our real working table at demo time, plus whatever people leave, plus one mixed box of everyday things from home (cables, chargers, toiletries, clothes, snacks, cans, paper, stationery). The box widens what is doable. It is not built for any errand.
- Open-vocabulary scan. No kit list anywhere in the code.
- Zones come from the scan: bags, boxes, bins, or named areas ("left half of the table"). The agent picks them per errand.
- Camera: phone 70 to 90 cm above the table, fixed. A lamp. The person sits at the bottom edge of the frame.

## Architecture
```
Room: Google Form -> Sheet -> backend poll (15 s) -> QUEUE
Browser, 30 fps, no model calls
  camera -> MediaPipe hands -> guidance (tone + words) -> overlay, STOP
      | websocket 30 Hz: hands, grasp, open/closed
      v
Backend (FastAPI)
  Hydrogen perception: open scan (start, after each pick, on change), verify on grasp, read on hold-up
  change detector: frame diff over 3 s -> rescan
  state builder, 10 Hz; check runner, 10 Hz (released checks only) -> STOP / OK
  reply: Discord webhook or email to the sender; calendar for Saran's errands
  logs/calls.jsonl, logs/agent.jsonl, runs.csv (the wall)
      ^ plan.json + checks/ (only after the release hook passes)
      | errand.json + scan.json (+ emails.json for Saran's errands), Files API
Managed Agent (Google sandbox, never in the live loop)
  triage every new errand in the background
  compile at run time against the live scan -> release hook
  learn: trigger every 30 min -> lessons + regression cases (regression hook)
```

Layer rules:
- L0 Browser at 30 fps, no model calls.
- L1 Hydrogen: open scan, verify, read. Thinking low; medium for reads.
- L2 Check runner: released checks only, subprocess, AST allowlist (math, json), 50 ms timeout.
- L3 Managed Agent: triage, compile, learn. Never in the live loop.
- Fast path: while the agent compiles, Hydrogen may propose a first step labeled "unverified". When the checks arrive they are enforced, and any earlier step that breaks a rule is flagged and fixed on screen.

## Managed Agent design
- Environment: one persistent environment named offscreen. Files persist across runs.
- Skill: skills/offscreen-compiler/SKILL.md: errand to plan.json and checks/, the check API, test patterns, the "can't do" list.
- AGENTS.md: role, contracts, rules. Cite a source URL for every rule. Use only objects in scan.json. Ask for a hold-up read when a rule depends on a label. Say "can't do" plainly.
- Triage job: starts when an errand lands in the queue. Output: doable, needs [objects], or can't do [reason].
- Compile job: starts on stage against the live scan. Output: plan.json, checks/, tests/.
- Tools: built-in shell and files; web fetch for rule pages (allowlist set per errand domain: tsa.gov, faa.gov, nyc.gov, city and manufacturer pages); client-side tools our backend executes: release_plan, post_result, create_calendar_event.
- Hooks (.agents/hooks.json):
  - pre_tool_execution on release_plan: hooks/gate_release.py runs pytest on checks/ against scan.json and synthetic traces. Deny returns failing check ids and reasons.
  - pre_tool_execution on writes under skills/: hooks/gate_regression.py runs every stored regression case. Deny if one breaks.
  - post_tool_execution on all tools: append to the agent log.
- Close: post_result and create_calendar_event are client-side tools. Calendar writes wait for approval on screen.
- Trigger: every 30 minutes, the learner reads new runs, writes lessons.md, adds regression cases, updates the skill through the regression hook.
- Streaming: the UI shows agent events as they happen.
- Fallback: no client-side tools means the RELEASED file pattern (agent writes plan.json and RELEASED; the hook gates RELEASED; the backend downloads).

## Contracts (E1 creates these first)
- contracts/errand.schema.json: id, text, from, time, triage {status doable|needs|cannot, missing [..], reason}.
- contracts/state.schema.json: t; hands [{side, landmarks 21 x [x, y], open, pos}]; objects {id: {label, pos [y, x] 0 to 1000, box, status on_table|in_hand|in_zone, zone, attrs}}; zones {id: polygon or box}; holding; events [{t, type, object, zone}].
- contracts/plan.schema.json: errand_id; sources [{id, kind web|email|calendar, ref, fetched_at}]; objects [{id, dest_zones, why, rule_ids, needs_read}]; rules [{id, text, source_id}]; steps [{id, object, action pick|read|place, zone}]; close [{kind post_result|calendar|email_draft, payload, needs_approval}].
- contracts/check_api.md: one file per rule in checks/. CHECK_ID, RULE_ID, SOURCE_URL, allowed(object_id, zone_id, state, plan) -> (bool, reason), satisfied(state, plan) -> (bool, reason). Standard library math and json only, no I/O, 50 ms max. tests/test_<check>.py with one pass and one fail case built from scan.json.
- contracts/run.schema.json: the runs.csv columns.

## Models
| Role | Model | Notes |
| --- | --- | --- |
| Open scan, verify | gemini-4-hydrogen, thinking low | Confirm id and output format Friday |
| Label reads | gemini-4-hydrogen, thinking medium | Argon only if Hydrogen fails G3 |
| Voice | gemini-3.8-live | Optional |
| Agent | Managed Agent default (3.8 Flash) | Gemini 4 if accepted |
| Raw arm | gemini-4-hydrogen live stream in AI Studio | Same errand, same table, no harness |

## UI (readable from 2 m)
- Left 60 percent: the live camera with hand skeleton, object labels, zones, target ring, "holding" chip, red border on STOP, wall clock and run timer.
- Right: QUEUE (errand, sender, time, triage), PLAN (steps and status), AGENT stream (one line per event, with URLs), COUNTERS (steps verified, stops before landing, Hydrogen p50, loop fps).
- A second view, the WALL: every run today. Errand, sender, time, outcome, video link. Raw and Offscreen counts on top.
- Counters at least 32 px, text at least 24 px.

## Acceptance tests
- AT1 Open scan: on our untidied table with 25 or more objects, Hydrogen labels and points to at least 90 percent of what a person lists, with no more than 10 percent wrong labels. p50 at or under 3 s.
- AT2 Hands: at least 25 fps with overlay; tone within 100 ms of the frame.
- AT3 Stop: 10 deliberate wrong moves on a queue errand's plan. STOP before contact in at least 9.
- AT4 Verify and read: holding correct in at least 9 of 10 on objects from the table; label reads at least 8 of 10.
- AT5 Compile and gate: 5 errands from the queue (not chosen by us) compile to valid plans with checks. A planted broken check is denied and fixed, 3 of 3. Compile p50 at or under 60 s.
- AT6 Triage: 10 queue errands including impossible ones. Correct doable, needs or cannot, with a reason, at least 9 of 10.
- AT7 Close: the result reaches the sender, 3 of 3. Calendar only after approval, 3 of 3.
- AT8 Adapt: an object added or moved mid-run triggers rescan and replan within 5 s, 3 of 3.
- AT9 Trials: at least 6 raw and 6 Offscreen runs on queue errands, alternating, blindfolded, on the wall.
- AT10 Rehearsal: 10 full runs on 10 different errands (never one path), 8 clean.

## WOW test (checkable)
On the event floor, live: an errand we did not write (queue or judge), on the table as it is. The agent compiles it live and the hook decision is in the log. A blindfolded teammate completes it with zero violations landed. The result reaches the sender. Under 3:00.
Evidence: the wall row and its video.

## Trials and the "beats raw" gate
- Fixed now, before data: success means every planned object in an allowed zone and zero violations landed.
- Errands come from the queue in arrival order. Alternate arms: raw, Offscreen, raw, Offscreen. Same person, blindfolded.
- Say "beats raw" only if Offscreen succeeds in at least 2 more runs than raw, out of at least 6 each. Report counts.

## Out of scope
Robot arms, simulation, MuJoCo, gaze control (blink approve is a stretch only), a phone app, accounts, folding or assembly errands.

## Fallbacks (each behind a flag)
- FB1 Hydrogen slow (over 3 s): scan on change only, verify only on grasp.
- FB2 Compile slow (over 60 s): the fast path runs labeled "unverified" until checks arrive.
- FB3 No client-side tools: the RELEASED file pattern.
- FB4 Queue empty: the agent proposes an errand from the scene, labeled as its own.
- FB5 Form or Discord down: a judge says the errand out loud; we type it as said.
- FB6 Live voice fails: browser speech recognition.
- FB7 Venue Wi-Fi: phone hotspot.
- FB8 Everything else: the 60 s insurance recording, labeled with its time.

## Rules
- All project code is written on event day. Friday is learning and gate tests only, in AI Studio or a throwaway folder outside this repo.
- Declare open-source libraries in the README.
- The screen never shows a full private email. Parsed fields only.

## Go deeper (Oct 15 rule)
1. What a top professional would do: take requests from the audience live (the GPT-4o launch), run one continuous take with a clock, show the raw trace, let skeptics perturb the scene, and publish every run including failures.
2. Rawest material: errands as people typed them, the table as it is, raw frames, per-frame landmarks, raw model JSON, live rule pages.
3. Methods and tools: open-vocabulary scan with Hydrogen; MediaPipe; WebAudio tone; Managed Agents skills, hooks, triggers, background runs and streaming; pytest; an AST allowlist; alternating trials in arrival order.
4. Proof that is not us: sender names and times, the judge's own errand, the blindfold, the raw arm, source URLs on every rule, the wall with videos.

## After the event
- Release code, the errand set, and the run dataset (frames, landmarks, model I/O, outcomes) on Hugging Face.
- Paper: real errands from real people, done by human hands guided by a model, raw vs harness. The real-world counterpart to Embodied Web Agents (NeurIPS 2025 Datasets and Benchmarks), which used simulation.
- Send the repo and video to the judges you met.

## Open questions (answer Friday, write answers here)
- Submission deadline T, demo format and length. Is judging at our table or on a stage?
- Managed Agents prize criteria.
- Does a Managed Agent accept gemini-4-hydrogen? Client-side function tools? Tool names for hook matchers?
- Hydrogen open-scan output format.
- Is posting a form link in the event Discord allowed?
