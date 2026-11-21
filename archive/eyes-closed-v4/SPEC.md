# SPEC.md: Eyes Closed

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM. Locked Fri Nov 20, 4:15 PM.
Track: 5 Sigma. Judging: round 1 in one of 6 rooms, then a final in front of everyone.
Older versions are in archive/. Do not use them.

## One line
Do it eyes closed.

## What it is
They say you've mastered something when you can do it with your eyes closed. Eyes Closed is an agent reliable enough to make that literal.
It scans whatever is in front of you, reads what the errand needs (your email, your calendar, the rule pages), writes a plan and a check for every step, guides your hands live, stops a mistake before it lands, and only marks a step done when it can prove it.
Saran gives the whole pitch blindfolded, and does a real errand with his own hands while Gemini sees for him.

Friend version: "A guy pitched blindfolded while Gemini packed his bag through his hands."

## The problem it solves (DeepMind's own words)
- Google DeepMind, Gemini Robotics ER 2 launch (Jul 30, 2026): "One of robotics' hardest challenges is knowing when a task is done."
- DeepMind's 2023 paper "Vision-Language Models as Success Detectors" found success detection on unseen real human videos the hardest case, and left it as future work.
- Eyes Closed is that future work: knowing a real step is done, live, on objects it has never seen, with no human eyes checking.
- ER 2 is already evaluated with a human in the loop ("human tele-op" is one of its control modes). Eyes Closed is the measured, in-the-wild version of that loop.

## 5 Sigma compliance
| Rule from the guide | How Eyes Closed meets it |
| --- | --- |
| A real task today's agents struggle with | Physical errands. Today's agents stop at the screen, and raw Hydrogen guiding a person makes mistakes it can't see |
| Does it reliably | A check for every step, a release hook, calibrated step decisions, STOP before a mistake lands |
| Evaluation on inputs you didn't prepare | Bag photos and errands from 10 or more other people, plus objects handed over by judges, plus live runs on real bags |
| Compare to a simple baseline | B1: one Hydrogen call (photo plus errand gives a plan). B2: raw Hydrogen live stream guiding the same person |
| Where it still fails, what you changed | Failure card on screen and in the README: top failure types and the fix for each |
| At least two Gemini 4 models, each with a clear job | Hydrogen sees. Neon thinks. (Decision 1 and the Managed Agent are on top) |
| Media central | The live camera is the product |
| No scripted demo, no team-written eval | Real bag, judge's object, outside photos and errands. Nothing in the eval is written to pass |

## Models and their jobs
| Job | Model | What it does |
| --- | --- | --- |
| Eyes | gemini-4-hydrogen | Open scan of the pile, pointing, what the hand holds, label reads, a first plan in seconds |
| Brain | gemini-4-neon | Reads the email and the rule pages, writes the plan and the checks as code |
| Reflexes | gemini-decision-1 (Decisions API) | Yes or no on each step with a calibrated probability, about 0.2 s. Low confidence means "hold it up" |
| Job runner | Gemini Managed Agent | Runs the compile job in its sandbox, tests the checks, a hook blocks release until they pass, learns every 30 min |
| Voice (optional) | gemini-3.8-live | Conversation with the blindfolded presenter |

Say it in one line on stage: "Hydrogen is its eyes, Neon its brain, the Decisions API its reflexes, and a Managed Agent writes and tests its rules."

## Live feed, by layer
- Laptop hand tracker: every frame, 30 per second. No model call here.
- Decisions API: each step check, about 0.2 s.
- Hydrogen: about once a second and at every grab. If Hydrogen streams over the Live API (test G7 tonight; ER 2 does), it watches continuously instead.
- Managed Agent: background only, never in the live loop.
- Nothing is recorded. One continuous take, wall clock on screen.

## Organic rules (these beat every other section)
- The errand is real: Saran's actual upcoming trip, from his real email and calendar.
- The objects are real: Saran's backpack, dumped as it is. Never packed for the demo.
- The mystery object comes from a judge's hand. Nobody knows what it will be.
- The second errand comes from the room, or Saran picks one live.
- No object list anywhere in code or prompts. The scan is open vocabulary.
- No staged mistakes. Zero stops is a fine outcome.
- Any recording or cached plan shows its time.

## Opening shot (one sentence)
Saran pulls on a sleep mask before saying a word, tips his backpack onto the board, and Gemini labels every object on the big screen.

## Idea gate (Sep 13 system)
- Person: Saran, real trip. Market: Instinct raised $1B (Sep 2026); RentAHuman, a marketplace for agents to hire humans, reports 500,000 users. Its agents wait for proof after the work. Nothing watches the work.
- Sponsor products load-bearing and said out loud: Hydrogen, Neon, the Decisions API, Managed Agents.
- Mechanism in one picture: the models table and Architecture.
- Number that moves on screen: steps proven, mistakes stopped, and the false "done" rate, raw vs Eyes Closed.
- Opening shot: above.

## What it can do, said plainly
- Yes: errands that come down to the right things in the right places under real rules. Pack, sort, recycle, set up, gather, return.
- No: folding, tying, assembling, cooking, tools, heat. It says so.

## Claims (all live)
- C1 Scan: open-vocabulary labels on a dumped bag within 5 s.
- C2 Compile: Neon reads the real email and the live rule pages and writes the plan and checks. The Managed Agent tests them against the live scan. A hook releases the plan only when the tests pass.
- C3 Guide: 30 fps hand tracking plus Hydrogen locations guide the blindfolded presenter by tone and short words in one earbud.
- C4 Prove: a step is marked done only when the check passes and Decision 1 is confident. Otherwise: "hold it up".
- C5 Stop: a held item that breaks a rule triggers STOP before it lands.
- C6 Mystery object: a judge's object is guided up to the camera, named, judged against the rules and placed or handed back.
- C7 Second errand: a new errand on the same pile shows a plan within 10 s, marked "unverified" until its checks land.
- C8 Close: a calendar event in Saran's real calendar after he says yes.
- C9 Better than baseline: the false "done" rate and mistakes landed, raw vs Eyes Closed, on inputs we didn't prepare.

## Do not claim
- "First ever", "five sigma achieved", robot control, medical use.
- "Beats the baseline" unless the gate rule in Evaluation passes.
- Anything not on screen.

## The demo board (built Friday night)
- A tray or stiff board about 60 x 40 cm with a rim. A cardboard mast taped to it, phone 60 to 80 cm above the center. Carried as one piece.
- Tape marks: "bag" (the open backpack sits there) and "stays home".
- One sleep mask, one earbud for guidance, the laptop off to the side facing the room.
- Room setup: 60 s or less (AT12).

## Architecture
```
Browser, 30 fps, no model calls
  camera -> MediaPipe hands -> guidance (tone on speaker, words in one earbud) -> overlay, STOP
  voice commands for a blindfolded presenter ("get me ready", "next errand", "yes")
      | websocket 30 Hz
      v
Backend (FastAPI)
  Hydrogen: open scan (start, after each pick, on change), holding, label reads, fast plan
  Decision 1: per-step yes/no with probability; batch questions per frame
  change detector, state builder 10 Hz, check runner 10 Hz -> STOP / OK / PROVEN
  calendar write after "yes"; logs/calls.jsonl, logs/agent.jsonl, runs.csv, steps.csv
      ^ plan.json + checks/ (only after the release hook passes)
      | errand.json + scan.json + emails.json (Files API)
Managed Agent (Google sandbox, never in the live loop)
  compile: calls Neon (as the agent model, or through the API with an injected key) -> plan + checks + tests
  release hook runs the tests; learner trigger every 30 min with a regression hook
```

Layer rules:
- L0 Browser at 30 fps, no model calls.
- L1 Hydrogen and Decision 1 in the backend. Hydrogen thinking low; medium only for label reads.
- L2 Check runner: released checks only, subprocess, AST allowlist (math, json), 50 ms timeout.
- L3 Managed Agent: compile and learn. Never in the live loop.

## Managed Agent design
- Environment: one persistent environment named eyes-closed. Files persist across runs.
- Model: gemini-4-neon if the agent accepts it (G5). If not, the default model runs the job and calls Neon through the Gemini API, with the key injected by the egress proxy so it never sits in the sandbox.
- Skill: skills/eyes-closed-compiler/SKILL.md: errand to plan.json and checks/, the check API, the decision questions per step, test patterns, the "can't do" list.
- AGENTS.md: cite a source URL for every rule; use only objects in scan.json; ask for a hold-up read when a rule depends on a label; say "can't do" plainly.
- Tools: built-in shell and files; web fetch for rule pages (allowlist: tsa.gov, faa.gov, nyc.gov, manufacturer pages); client-side tools the backend executes: release_plan, create_calendar_event.
- Hooks (.agents/hooks.json):
  - pre_tool_execution on release_plan: hooks/gate_release.py runs pytest on checks/ against scan.json and synthetic traces. Deny returns failing check ids and reasons.
  - pre_tool_execution on writes under skills/: hooks/gate_regression.py runs every stored regression case. Deny if one breaks.
  - post_tool_execution on all tools: append to the agent log.
- Trigger: every 30 minutes, the learner reads new runs and steps, writes lessons.md, adds regression cases, updates the skill through the regression hook.
- Streaming: the UI shows agent events as they happen. The release decision is shown on stage.
- Fallback: no client-side tools means the RELEASED file pattern.

## Contracts (E1 creates these first)
- contracts/errand.schema.json: id, text, source (email|calendar|spoken), time.
- contracts/state.schema.json: t; hands; objects {id: {label, pos [y, x] 0 to 1000, box, status on_board|in_hand|in_zone, zone, attrs, source scan|handed}}; zones; holding; events.
- contracts/plan.schema.json: errand_id; sources [{id, kind, ref, fetched_at}]; objects [{id, dest_zone, why, rule_ids, needs_read}]; rules [{id, text, source_id}]; steps [{id, object, action pick|read|place, zone, decision_question}]; close [{kind calendar, payload, needs_approval}]; verified (bool).
- contracts/check_api.md: CHECK_ID, RULE_ID, SOURCE_URL, allowed(object_id, zone_id, state, plan) -> (bool, reason), satisfied(state, plan) -> (bool, reason). Standard library math and json only, no I/O, 50 ms max. tests/test_<check>.py with one pass and one fail case.
- contracts/decision.md: one closed question per step ("Is the hand holding the white USB-C charger?"), the probability threshold for PROVEN (start at 0.9), and the abstain rule (between 0.4 and 0.9: "hold it up").
- contracts/run.schema.json, contracts/step.schema.json, contracts/case.schema.json: the CSV columns.

## Evaluation (the 5 Sigma core)
Metric definitions are fixed now, before any data.
- Set A, outside piles: bag photos and one errand each from 10 or more other people, 30 or more cases. Saran labels the correct plan before running anything. Score: plan accuracy (objects in the right destination). Baseline B1: one Hydrogen call with the photo and the errand.
- Set B, live runs: at least 6 baseline and 6 Eyes Closed, alternating, blindfolded, on different bags and errands. Baseline B2: raw Hydrogen live stream guiding the same person. Score: mistakes landed, task success.
- Set C, step proofs: every step from Set B, labeled true or false from the video. Score: false "done" rate (marked done but wrong), abstain rate, calibration of Decision 1 (reliability chart).
- Failure analysis: the top 2 failure types with one example each, and what we changed.
- Gate: say "beats the baseline" only if Eyes Closed wins Set B by at least 2 runs out of 6 or more each, and its false "done" rate on Set C is lower. Report counts, not percentages from small samples.

## UI (readable from the back of a room)
- Left 60 percent: live camera with object labels, hand skeleton, zones, target ring, "holding" chip, red border on STOP, green flash on PROVEN, wall clock and run timer.
- Right: PLAN (steps, PROVEN or waiting, "unverified" tag), AGENT stream (one line per event, URLs, the release decision), COUNTERS (steps proven, mistakes stopped, Decision 1 p50, Hydrogen p50).
- END CARD (after the mask comes off): "Eyes Closed. Do it eyes closed." Set A, B and C numbers, the failure line, repo link and QR.
- Counters at least 40 px, text at least 28 px, high contrast for projectors.

## Acceptance tests
- AT1 Open scan: a dumped bag, ordinary room light, 20 or more objects. At least 90 percent found, at most 10 percent wrong, p50 at or under 3 s.
- AT2 Hands: at least 25 fps with overlay; tone within 100 ms.
- AT3 Stop: 10 deliberate wrong moves. STOP before contact in at least 9.
- AT4 Holding and reads: Hydrogen holding correct at least 9 of 10; label reads at least 8 of 10.
- AT5 Decisions: p50 at or under 300 ms per step check; on 20 labeled frames, at least 18 correct at the 0.9 threshold, abstains counted separately.
- AT6 Compile and gate: the real trip errand compiles to a valid plan with checks; a planted broken check is denied and fixed, 3 of 3; compile p50 at or under 45 s.
- AT7 Mystery object: an object handed over mid-run is guided to the camera, named, judged and placed or handed back within 10 s, 5 of 5, objects not seen before that day.
- AT8 Second errand: a new plan within 10 s, checks land within 60 s, 3 of 3.
- AT9 Close: the calendar event appears only after "yes", 3 of 3.
- AT10 Voice: "get me ready", "next errand" and "yes" work blindfolded with no hands on the laptop, 10 of 10.
- AT11 Evaluation: Sets A, B and C filled as defined; the END CARD renders from the files.
- AT12 Room setup: walking in to the first label on the projector, 60 s or less, 3 of 3.
- AT13 Rehearsal: Saran gives the full pitch blindfolded 10 times on different bags and errands, 8 clean.

## WOW test (checkable)
In the judging room, live: setup in 60 s or less. Saran puts on the mask and keeps it on for the whole run. He dumps his real bag. The trip errand compiles with its release decision on screen. He packs it with zero mistakes landed. A judge's object is handled. A second errand gets a new plan. The calendar event appears after "yes". He takes off the mask, and the END CARD shows today's numbers. Under 3:00.
Evidence: the runs.csv row and the recording if the room allows it.

## Out of scope
Robot arms, simulation, gaze control, a phone app, accounts, folding or assembly errands, an errand queue, the Shopify bonus.

## Fallbacks (each behind a flag)
- FB1 Hydrogen slow (over 3 s): scan on change only.
- FB2 Compile slow (over 45 s): the fast plan runs labeled "unverified" until checks land. Say so.
- FB3 Decisions API down: Hydrogen answers the step question; the screen marks it "uncalibrated".
- FB4 Neon not accepted in the agent: the agent calls Neon through the API (see Managed Agent design).
- FB5 No client-side tools: the RELEASED file pattern.
- FB6 No projector: laptop turned to the judges.
- FB7 Tracking lost mid-pitch: lift the mask, say where it broke and what we changed. The brief asks for that.
- FB8 Room Wi-Fi: phone hotspot.
- FB9 Everything else: the 60 s recording of the best run, labeled with its time.

## Rules
- All project code is written on event day. Friday is gate tests, the board, the outside photos, recruiting and pitch practice.
- Declare open-source libraries in the README.
- The screen never shows a full private email. Parsed fields only.

## Go deeper (Oct 15 rule)
1. What a top professional would do: fix metric definitions before data, use outside inputs and alternate arms, report a calibration chart rather than a single accuracy, open with an action not a slide, use a borrowed object as proof, and rehearse setup as hard as the pitch.
2. Rawest material: the bag as it falls, other people's photos as sent, the live rule pages, raw frames, raw model JSON and probabilities.
3. Methods and tools: Hydrogen open-vocabulary pointing; the Decisions API for calibrated yes/no; Neon for plans and checks; Managed Agents skills, hooks, triggers, injected credentials and streaming; MediaPipe; pytest; an AST allowlist; reliability charts.
4. Proof that is not us: the blindfold, the judge's object, other people's photos, the baselines, source URLs on every rule, the real calendar.

## After the event
- Release code, Set A, B and C, and the run dataset (frames, hand tracks, model I/O, probabilities, outcomes) on Hugging Face.
- Paper: reliable success detection for real-world tasks done by human hands, with calibrated step decisions and agent-written checks, against raw baselines. It picks up where DeepMind's 2023 success-detection paper stopped, and it is the real-world counterpart to Embodied Web Agents (NeurIPS 2025 Datasets and Benchmarks), which used simulation.
- Post the pitch clip and the numbers on X, tagging Google DeepMind and Google AI Studio. Send the repo to the judges you met.

## Open questions (answer Friday or at check-in)
- Slot length, Q&A length, projector input, which judges sit in which room, how many advance.
- Managed Agents prize criteria.
- Does the Managed Agent accept gemini-4-neon? Client-side tools? Tool names for hook matchers?
- Does gemini-4-hydrogen stream over the Live API?
- Decisions API: image input format, batch size, latency on venue Wi-Fi.
