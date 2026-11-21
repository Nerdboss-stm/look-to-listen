# SPEC.md: Offscreen

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM. Locked Fri Nov 20.
The old Make Do files are in archive/make-do/. Do not use them.

## One line
Your agent, off the screen.

## What it is
A personal agent that finishes tasks that cross your apps and the physical world.
It reads what the task needs (email, calendar, the web), compiles a plan and the checks for it, guides any pair of hands through the physical steps live, stops mistakes before they land, and closes the task back in your apps.

Friend version: "Gemini's agent pays your bills. This one also packs your bag."

## Opening shot (one sentence)
A blindfolded teammate packs for a real flight while Gemini reads the bottle she holds up, says "checked bag", and stops her hand before it lands in the wrong one.

## Why now (say it out loud)
- Tue Nov 17: Tasks in Gemini, running on Gemini 4 Hydrogen, went free to hundreds of millions of people. It calls businesses, analyzes bills and checks out with Google Pay. Muse, Dots, Duet and Instinct do the same kind of work. Every one ends in an app or a phone call.
- Hydrogen (GA Nov 12) folds Robotics ER 2 skills into core Gemini 4. None of those agents uses that half. Offscreen does.
- Closest prior: Project Astra's I/O 2025 bike video. Astra found the manual and a video and called a shop. The person did the physical work and checked it himself. Offscreen owns the plan, watches every step, verifies it with checks it wrote, and is measured against raw Gemini on the day.

## Idea gate (Sep 13 system)
- Person: Saran, a real upcoming trip. Use the re:Invent flight email if it is in Gmail; otherwise any real flight email.
- Dollar figure: personal agents are the hottest consumer AI race (Instinct raised $1B in Sep 2026). All of them stop at the screen.
- Sponsor product load-bearing and said out loud: Gemini 4 Hydrogen embodied reasoning (perception) and Gemini Managed Agents (compile, gate, learn).
- Mechanism in one picture: Architecture below.
- Number that moves on screen: steps verified, stops before landing, raw vs Offscreen on event-day trials.
- Opening shot: above.

## Claims (all live on stage)
- C1 Compile. A spoken goal, a real email and live web rules become a plan and executable checks. The agent tests the checks against this camera's scan. A hook releases the plan only when the tests pass.
- C2 Guide. Local hand tracking at 30 fps plus Hydrogen item locations guide a blindfolded person to each item with a distance tone and short words.
- C3 Verify. Hydrogen confirms what the hand holds and reads labels when an item is held up.
- C4 Stop before landing. A held item that breaks a rule triggers STOP before it enters the wrong bag.
- C5 Close. The digital step (a calendar event) happens only after the person approves.
- C6 Better than raw. Event-day trials: Offscreen vs the same model with the same camera, email and goal, and no harness. Shown as counts.
- C7 General. A goal nobody rehearsed compiles in the background during a live run.

## Do not claim
- "First ever", "nobody has done this", robot control, or any medical use.
- "Beats raw Gemini" unless the gate rule in Trials passes.
- Anything that is not on screen.

## Kit (household items, buy nothing)
- Table area about 80 x 60 cm. Light cloth or paper on it. Two bag zones taped at the edges. A lamp.
- Camera: phone 70 to 90 cm above the table (Continuity Camera or USB), fixed with tape to a shelf, a lamp arm or a stack of books. The person sits at the bottom edge of the frame.
- Items (about 20, keep the look-alike pairs on purpose):
  1. laptop (closed)
  2. laptop USB-C charger (brick and cable)
  3. phone cable (Lightning or USB-A), look-alike of 2
  4. power bank
  5. earbuds case
  6. travel bottle, 3.4 oz or less
  7. full-size bottle (shampoo or lotion), over 3.4 oz
  8. toothpaste tube (check its printed size)
  9. wallet
  10. keys
  11. sunglasses
  12. compact umbrella
  13. socks
  14. folded T-shirt
  15. USB-C to HDMI adapter (only if you own one)
  16. mouse or presentation clicker
  17. TV remote, look-alike of 16
  18. notebook and pen
  19. snack bar
  20. distractors: mug, coins, a book
- Bags: carry-on (backpack) and checked (tote or small suitcase). For G3: three boxes marked recycle, trash, drop-off.
- Blindfold: sleep mask or scarf.
- Kit file: contracts/kit.json (id, name, visual description, look_alike_of).

## Goals
Each goal has a real source, a physical part, a digital close and an end-state test.
- G1 Flight (the demo goal). "I fly to Vegas on Sunday. Get me ready." Use the real city and date from the email. Sources: the real flight email (demo Gmail account), tsa.gov and faa.gov rules fetched live, the destination forecast. Physical: pack items into carry-on or checked. Digital close: a calendar event "Leave for the airport" at a time the agent computes. End state: every planned item in an allowed bag, no violation landed, the event exists.
- G2 Pitch. "Get me ready for my 4 PM pitch." Sources: the calendar event and its email ("the room has HDMI only"). Physical: laptop, USB-C charger, HDMI adapter and the clicker (not the remote) into the backpack. Digital close: a draft reply to the organizer, sent only after approval. Needs item 15.
- G3 Recycling. "Sort these for recycling." Source: the Jersey City recycling rules page fetched live. Physical: items into recycle, trash or drop-off. Digital close: a calendar reminder for the next collection day the page states.
- G4 Rainy commute. "Pack for tomorrow." Sources: the forecast and tomorrow's calendar. Physical: the bag the day needs. Digital close: a "leave by" event.
- G-fresh. Any goal typed on the day by a teammate (or a judge who wants to). Compiled in the background (AT8).
- Goals file: contracts/goals.json.

## Architecture
```
Browser, 30 fps, no model calls
  camera -> MediaPipe hands -> guidance (tone + words) -> overlay, STOP
      | websocket 30 Hz: hands, grasp, open/closed
      v
Backend (FastAPI)
  Hydrogen perception: scan (start + after each pick), verify on grasp, read on hold-up
  state builder, 10 Hz: hands + items + zones + events
  check runner, 10 Hz: released checks only -> STOP / OK -> browser
  logs/calls.jsonl, logs/agent.jsonl, trials.csv
      ^ plan.json + checks/ (only after the release hook passes)
      | scan.json + emails.json + goal.txt (Files API)
Managed Agent (Google sandbox, never in the live loop)
  compile: email + live rule pages -> plan + checks + tests -> release hook
  close: create_calendar_event, after approval on screen
  learn: trigger every 30 min -> lessons + regression cases (regression hook)
Gemini Live (optional): voice in and out for the goal and explanations
```

Layer rules:
- L0 Browser at 30 fps, no model calls: camera, MediaPipe Hand Landmarker, WebAudio distance tone, speechSynthesis words, overlay, STOP.
- L1 Hydrogen perception: scan every kit item at the start and after each pick; verify on grasp; read the label on hold-up. Thinking low. Medium only for label reads.
- L2 Check runner (backend, 10 Hz): runs only released checks, in a subprocess, with an AST allowlist (math, json) and a 50 ms timeout. Sends STOP and OK events.
- L3 Managed Agent (never in the live loop): compile, close, learn.
- Voice (optional): Gemini Live for the goal and explanations. Fallback: browser speech recognition.

## Managed Agent design
- Environment: one persistent environment named offscreen. Files persist across runs.
- Skill: skills/offscreen-compiler/SKILL.md. How to turn a goal into plan.json and checks/, the check API, test patterns.
- AGENTS.md: role, the plan and check contracts, rules. Cite a source URL for every rule. Never invent an item that is not in scan.json. Ask for a hold-up read when a rule depends on a label.
- Inputs per compile (Files API): goal.txt, scan.json (this camera's items and positions), emails.json (fetched by our backend with local OAuth from the demo account), kit.json.
- Tools: the built-in shell and files in the sandbox; web fetch for rule pages (allowlist: tsa.gov, faa.gov, the weather source, the city site); client-side function tools that our backend executes: get_trip_emails, release_plan, create_calendar_event.
- Hooks (.agents/hooks.json):
  - pre_tool_execution, matcher on release_plan: command hooks/gate_release.py runs pytest on checks/ against scan.json and synthetic traces. Deny returns the failing check ids and reasons. The agent fixes them and calls again.
  - pre_tool_execution, matcher on writes under skills/: command hooks/gate_regression.py runs every stored regression case. Deny if an old case breaks.
  - post_tool_execution, all tools: append to the agent log.
- Close: create_calendar_event is a client-side tool. The backend shows the request on screen and waits for approval (voice "yes" or a tap; blink is a stretch). Without approval it returns an error the agent sees.
- Trigger: a scheduled trigger every 30 minutes on the event day. The learner reads new trials and run logs, writes lessons.md, adds regression cases and updates the skill through the regression hook.
- Background: the G-fresh compile runs while a live run is on screen.
- Streaming: the UI shows agent events as they happen (tool calls, files written, test results, hook decisions).
- Model: the environment's default unless it accepts Gemini 4 (confirm Friday, G5).
- Fallback: if client-side tools are not supported, the agent writes plan.json and RELEASED in the sandbox, and the backend downloads them. The release hook gates the write of RELEASED instead.

## Contracts (E1 creates these first; everything else reads them)
- contracts/state.schema.json: t (ms); hands [{side, landmarks 21 x [x, y], open, pos [x, y]}]; items {id: {label, pos [y, x] 0 to 1000, status on_table|in_hand|in_zone, zone, attrs {fl_oz, ml, ...}}}; zones {id: polygon}; holding (item id or null); events [{t, type, item, zone}].
- contracts/plan.schema.json: goal_id, goal_text; sources [{id, kind email|web|calendar, ref, fetched_at}]; items [{id, dest_zones, why, rule_ids, needs_read}]; rules [{id, text, source_id}]; steps [{id, item, action pick|read|place, zone}]; digital [{id, kind calendar|email_draft, payload, needs_approval: true}].
- contracts/check_api.md: one file per rule in checks/. Each defines CHECK_ID, RULE_ID, SOURCE_URL and two pure functions:
  - allowed(item_id, zone_id, state, plan) -> (bool, reason). Called before a held item enters a zone.
  - satisfied(state, plan) -> (bool, reason). Called at the end.
  - Standard library math and json only. No I/O. 50 ms max.
  - tests/test_<check>.py: at least one pass case and one fail case, built from scan.json.
- contracts/trial.schema.json: the trials.csv columns.
- contracts/kit.json and contracts/goals.json.

## Models
| Role | Model | Notes |
| --- | --- | --- |
| Perception (scan, verify) | gemini-4-hydrogen, thinking low | Confirm the id and pointing format Friday (G1) |
| Label reads | gemini-4-hydrogen, thinking medium | Argon only if Hydrogen fails G3 |
| Voice | gemini-3.8-live | Optional |
| Agent | Managed Agent default (3.8 Flash) | Gemini 4 if accepted |
| Raw arm | gemini-4-hydrogen live stream in AI Studio | Same camera, email and goal, no harness |

## UI (readable from 2 m)
- Left 60 percent: live camera. Hand skeleton, target ring, item labels, zone outlines (blue carry-on, orange checked), a "holding" chip, a full-frame red border on STOP.
- Right top: PLAN checklist. Item, destination, rule, status (waiting, guiding, verified, stopped then fixed).
- Right middle: AGENT stream, one line per event.
- Right bottom: COUNTERS. Steps verified, stops before landing, Hydrogen p50 latency, loop fps, raw vs Offscreen counts from trials.csv.
- Counters at least 32 px, instructions at least 24 px.

## Acceptance tests
- AT1 Scan: Hydrogen points to at least 18 of 20 kit items within 3 cm, on 3 scans of the demo table. p50 at or under 2.5 s.
- AT2 Hands: at least 25 fps with the overlay on, on the demo laptop. The tone reacts within 100 ms of the frame.
- AT3 Stop: 10 deliberate wrong moves (wrong item reach, wrong bag). STOP fires before contact in at least 9.
- AT4 Verify and read: holding label correct in at least 9 of 10 (include items 2, 3, 16, 17). Volume read correct in at least 8 of 10 hold-ups.
- AT5 Compile and gate: G1 compiles to a valid plan with at least 5 checks. A planted broken check is denied with its reason; the agent fixes it and releases with no human help, 3 of 3. Compile p50 at or under 90 s over 5 runs.
- AT6 Close: the calendar event is created only after approval, 3 of 3. Without approval it is not created.
- AT7 Trials: at least 6 raw and 6 Offscreen G1 trials, blindfolded, alternating order, in trials.csv. The bar renders from the file.
- AT8 Fresh: an unseen goal compiles to passing checks in at or under 3 minutes while a live run is on screen.
- AT9 Rehearsal: the full 3:00 run, 8 of 10 clean (no hands on the laptop, under 3:00).

## WOW test (checkable)
On the event floor, live: a blindfolded teammate completes G1. The agent compiled and released the plan live and its hook decision is in the log. Every planned item is in an allowed zone. Zero violations landed. The calendar event exists after approval. Total at or under 3:00.
Evidence: one trials.csv row (arm offscreen, demo true) and its video.

## Trials and the "beats raw" gate
- Metric definitions are fixed now, before any trial. Success: all planned items in allowed zones and zero violations landed. stops_before_land: STOP events that prevented a violation.
- Same person, same kit, same email, blindfolded. Alternate the arms: raw, Offscreen, raw, Offscreen.
- Say "beats raw" only if Offscreen succeeds in at least 2 more trials than raw, out of at least 6 each. Otherwise show the live counters and drop the claim.
- Report counts ("7 of 8 vs 3 of 8"), never percentages from small samples.

## Numbers on screen (all from logs)
Steps verified. Stops before landing. Compile time. Hook decisions. Hydrogen calls and p50 latency. Loop fps. Raw vs Offscreen counts.

## Out of scope
Robot arms, simulation, MuJoCo, gaze control (blink approve is a stretch only), a phone app, accounts, multi-user.

## Fallbacks (each behind a flag)
- FB1 Hydrogen slow (over 3 s): scan once, rescan only after a pick, verify only on grasp.
- FB2 Live compile slow (over 90 s): run the latest released plan from a rehearsal, labeled with its time, and say so out loud.
- FB3 Client-side tools unsupported: the RELEASED file pattern above.
- FB4 Gmail OAuth fails: export the real email as a .eml file into emails.json. Still real.
- FB5 Live voice fails: browser speech recognition and speechSynthesis.
- FB6 Venue Wi-Fi fails: phone hotspot.
- FB7 Everything else: the 60 s insurance recording.

## Rules
- All project code is written on event day. Friday is learning and gate tests only, in AI Studio or a throwaway folder outside this repo.
- Declare open-source libraries in the README (MediaPipe, FastAPI, google-genai, pytest).
- Demo Gmail and calendar only. The screen shows parsed fields, never a full private email.

## Go deeper (Oct 15 rule)
1. What a top professional would do: design the judge's screen first and run one continuous take (DeepMind demo practice). Measure latency per layer and show it (robotics practice). Alternate raw and Offscreen trials, and fix metric definitions before any data (HCI and eval practice).
2. Rawest material: raw frames, per-frame hand landmarks, raw model JSON, the live tsa.gov page, the real email. Event-day trials only.
3. Methods and tools: MediaPipe Hand Landmarker; Hydrogen pointing JSON; a WebAudio distance tone; Managed Agents skills, hooks, triggers, Files API, background runs and streaming; pytest; an AST allowlist; alternating trial order; counts, not percentages.
4. Proof that is not us: the blindfold (no human eyes in the loop), the raw arm on the same camera, the real email and calendar on screen, a source URL on every rule, trials.csv and the videos.

## After the event
- Release the code, trials and run dataset (frames, landmarks, model I/O, outcomes) on Hugging Face.
- Paper: the real-world counterpart to Embodied Web Agents (NeurIPS 2025 Datasets and Benchmarks), which tested mixed physical and web tasks in simulation. Contributions: a kit protocol anyone can reproduce, the compile-to-checks harness with hook gates, raw vs harness results.
- Send the repo and the video to the judges you met.

## Open questions (answer Friday, write answers here)
- Submission deadline T, demo format and length.
- Managed Agents prize criteria.
- Does a Managed Agent accept gemini-4-hydrogen?
- Are client-side function tools supported? Exact built-in tool names for hook matchers.
- Hydrogen pointing output format.
