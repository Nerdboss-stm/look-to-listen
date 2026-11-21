# SPEC.md: Offscreen (complex base)

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM.
Track: Element 119. Judging: round 1 in one of 6 rooms, then a final in front of everyone.
Older versions are in archive/. Do not use them.

## One line
Your agent, off the screen.

## What it is (the whole base version)
Every agent this year stops at the screen. Offscreen is a personal agent with eyes, memory, hands and a wallet.
- Eyes: it watches a real space live through two cameras and a microphone.
- Memory: it remembers everything that happened there all day, and answers any question with the clip that proves it.
- Hands: it gets physical jobs done through any pair of hands, step by step, and stops mistakes before they land.
- Wallet: when something you need is nowhere in the day's footage, it finds it on Shopify and takes you to checkout after you say yes.
- A Gemini Managed Agent runs every job through these tools. Hooks gate plans and spending. It learns every 30 minutes.

Friend version: "It watched their table all day, found his adapter from a clip at 2 PM, guided his hands to pack for his flight, and ordered the charger he didn't have."

## Why Element 119: it pushes every axis the brief names
| The brief asks | Offscreen |
| --- | --- |
| Longer footage | The whole day of our table, from about 10 AM to the pitch |
| Messier audio | Voice commands in a loud hackathon room |
| More streams at once | Overhead table camera, laptop camera, microphone |
| Faster real-time loops | 30 fps hand loop on the laptop, step decisions in about 0.2 s |
| The Decisions API | Every step check and every "is it still there?" check |
| Show where it breaks | Recall against hours of footage, occlusion, noise, on the END CARD |
| No scripted demos | Judges ask any question about the day; the bag is dumped as it is |
| No team-written eval | Memory questions from outside people and from judges; real bags |

## Models and their jobs
| Job | Model | What it does |
| --- | --- | --- |
| Eyes | gemini-4-hydrogen | Open scan, labels for every event in the memory log, what the hand holds, label reads, fast plans |
| Memory | gemini-4-argon | Checks candidate clips and searches raw footage to answer questions about the day |
| Brain | gemini-4-neon | Finds candidate events in the log, plans goals from memory, the live scene, email and rule pages, writes the checks |
| Reflexes | gemini-decision-1 (Decisions API) | Calibrated yes or no for each step and each "still there?" check, about 0.2 s |
| Orchestrator | Gemini Managed Agent | Runs each job through tools, hooks gate plans and spending, learns every 30 min |
| Voice (optional) | gemini-3.8-live | Conversation with the presenter |

On stage, one line: "Hydrogen sees, Argon remembers, Neon plans, the Decisions API checks every step, and a Managed Agent runs the job."

## Organic rules (these beat every other section)
- The memory is real: our own work table from about 10 AM. Nothing is staged for the camera.
- Memory questions come from judges live and from outside people. We never pick them.
- The trip is real (Saran's email and calendar). The bag is dumped as it is.
- Whatever is missing is really missing. Nothing is hidden to make the wallet moment happen.
- No object list anywhere in code or prompts. Everything is open vocabulary.
- No staged mistakes. Zero stops is a fine outcome.
- Only our table and our team on camera. Crop or blur anyone else. Never transcribe other people.

## Opening shot (one sentence)
The big screen shows nine hours of our table as a timeline; a judge asks where something went, and Offscreen plays the clip from that afternoon.

## Idea gate (Sep 13 system)
- Person: Saran, a real flight. Market: Instinct raised $1B (Sep 2026); RentAHuman reports 500,000 users; Shopify's checkout already sits behind Muse and Instinct.
- Sponsor products said out loud: Hydrogen, Argon, Neon, the Decisions API, Managed Agents, and Shopify for the bonus.
- Mechanism in one picture: the models table and Architecture.
- Number that moves on screen: memory recall against raw Argon on the same footage; mistakes landed against raw Gemini.
- Opening shot: above.

## Claims (all live)
- C1 Memory: any question about the day, answered with a time and a clip in 8 s or less.
- C2 Live scene: open scan of the board in 5 s or less; every change is logged as it happens.
- C3 Plan with memory: a goal is planned from memory (things out of view, "your power bank went into the black bag at 11:02"), the live scene, email and live rule pages.
- C4 Hands: guidance at 30 fps; a step is proven only when its check passes and Decision 1 is confident; STOP before a mistake lands.
- C5 Wallet: a missing item is found through Shop MCP; checkout happens only after a spoken "yes", enforced by a hook.
- C6 Agent: the Managed Agent runs the goal end to end through tools; the release and spending hook decisions show on screen.
- C7 Learn: every 30 minutes the learner updates lessons and regression cases.
- C8 Close: a calendar event after "yes".
- C9 Where it breaks: recall by footage age, occlusion and noise, with numbers.

## Do not claim
- "First ever", robot control, medical use.
- "Beats the baseline" unless the gate rules in Evaluation pass.
- Anything not on screen.

## Hardware
- The demo board (tray or stiff board with a rim, cardboard mast, phone 60 to 80 cm above the center) sits on our work table all day. It is the overhead camera for memory and for the live loop.
- The laptop camera points at the presenter only.
- The laptop microphone takes voice commands.
- In the judging room we carry the board and the backpack. Memory questions are about the day's footage; the live scene is the room.

## Architecture
```
Recorder (laptop, starts about 10 AM)
  overhead 2 fps + laptop camera 1 fps -> 5 min segments, timestamped
  change detector (frame diff held over 1 s) -> event clip (3 s before to 3 s after)
Event labeler
  Hydrogen labels each clip -> events.jsonl {t, type added|removed|moved|picked|placed, object, where, clip}
Memory query
  Neon reads events.jsonl -> candidate events -> Argon checks the clips (and raw segments when needed)
  -> answer {time, clip, confidence}
Live loop (browser, 30 fps, no model calls)
  MediaPipe hands -> guidance (tone on speaker, words in one earbud) -> overlay, STOP
Backend (FastAPI)
  Hydrogen scan, holding, reads; Decision 1 checks; check runner; state builder
  Shop MCP client; Google Calendar; logs/calls.jsonl, logs/agent.jsonl, CSVs
Managed Agent (Google sandbox, never inside the 30 fps loop)
  tools: recall, look, plan, execute, verify, shop_search, shop_checkout, calendar_add
  hooks: gate_release, gate_spend, gate_regression; learner trigger every 30 min
```

Layer rules:
- L0 Browser at 30 fps, no model calls.
- L1 Recorder and change detector on the laptop, no model calls.
- L2 Hydrogen, Argon, Neon and Decision 1 in the backend.
- L3 Check runner: released checks only, subprocess, AST allowlist (math, json), 50 ms timeout.
- L4 Managed Agent: orchestration and learning. execute(plan_id) runs the live loop locally and returns when the plan is done.

## Managed Agent design
- Environment: one persistent environment named offscreen. Files persist across runs.
- Model: gemini-4-neon if the agent accepts it (G5). If not, the default model runs the job and calls Neon through the Gemini API, with the key injected by the egress proxy.
- Skill: skills/offscreen/SKILL.md: how to run a goal with the tools, the plan and check contracts, the "can't do" list, the spending rules.
- AGENTS.md: cite a source URL for every rule; use only objects in the scan or the event log; say "can't do" plainly; never spend without a spoken approval id.
- Client-side tools executed by the backend: recall(question), look(), plan(goal), execute(plan_id), verify(step_id), shop_search(item), shop_checkout(cart_id), calendar_add(event).
- Hooks (.agents/hooks.json):
  - pre_tool_execution on execute: hooks/gate_release.py runs pytest on the plan's checks. Deny returns failing check ids and reasons.
  - pre_tool_execution on shop_checkout: hooks/gate_spend.py denies unless a spoken approval id is present and the total is under the $50 cap.
  - pre_tool_execution on writes under skills/: hooks/gate_regression.py runs every stored regression case.
  - post_tool_execution on all tools: append to the agent log.
- Trigger: every 30 minutes the learner reads new runs, steps and memory answers, writes lessons.md, adds regression cases, updates the skill through the regression hook.
- Fallback: if client-side tools are not supported, the backend orchestrates with Neon directly and the Managed Agent runs the compile, test and learn jobs only (RELEASED file pattern).

## Contracts (E2 creates these first)
- contracts/event.schema.json: t, type, object, where, clip, segment, confidence.
- contracts/state.schema.json: t; hands; objects {id: {label, pos [y, x] 0 to 1000, box, status, zone, attrs, last_seen}}; zones; holding.
- contracts/memory_answer.schema.json: question, answer, time, clip, confidence, events_used, segments_used, mode (log+clip | raw | log only).
- contracts/plan.schema.json: goal; sources; objects [{id, dest_zone, why, rule_ids, needs_read, from_memory}]; rules; steps [{id, object, action, zone, decision_question}]; shop [{item, why}]; close [{kind, payload, needs_approval}].
- contracts/check_api.md: CHECK_ID, RULE_ID, SOURCE_URL, allowed(object_id, zone_id, state, plan), satisfied(state, plan). Standard library math and json only, no I/O, 50 ms max, tests with one pass and one fail case.
- contracts/decision.md: one closed question per step; PROVEN at 0.9 or more; "hold it up" between 0.4 and 0.9.
- contracts/qa.schema.json, run.schema.json, step.schema.json: the CSV columns.

## Evaluation
Metric definitions are fixed now, before any data.
- Set M, memory: at least 50 questions about the day. At least 25 come from outside people: at about 4 PM, send friends a 60 s timelapse of the day and ask each for 3 questions. Judges' live questions are added as they come. S4 labels the true answer and time from the footage. Correct means the right answer and a time within 2 minutes. Baseline M0: raw Argon given the raw footage (as much as one call takes) and the question.
- Set L, live jobs: at least 6 baseline and 6 Offscreen runs on different bags and goals, alternating. Baseline L0: raw Hydrogen live stream guiding the same person. Score: mistakes landed, task success.
- Set S, steps: every step from Set L labeled true or false from video. Score: false "done" rate, calibration of Decision 1.
- Where it breaks: Set M accuracy by footage age (0 to 2 h, 2 to 5 h, over 5 h), by occlusion, and by object size; voice command accuracy against room noise.
- Gate: say "beats the baseline" only where the margin holds: Set M by at least 10 questions out of 50, Set L by at least 2 runs out of 6 each. Report counts.

## UI (readable from the back of a room)
- Left 60 percent: the live camera with labels, hand skeleton, zones, target ring, red STOP border, green PROVEN flash, wall clock.
- Right: TIMELINE (the whole day, events as ticks, scrubbable), ANSWER (clip player, time, confidence), PLAN, AGENT stream (tool calls and hook decisions), COUNTERS.
- END CARD: "Offscreen. Your agent, off the screen." Set M, L and S numbers, where it breaks, repo link and QR.
- Counters at least 40 px, text at least 28 px, high contrast.

## Acceptance tests
- AT1 Recorder: segments saved with no gap over 2 minutes from start to pitch.
- AT2 Event log: a 10 minute test with 20 changes made by a teammate. At least 18 logged with the right object and a time within 5 s.
- AT3 Memory: 10 questions on one hour of footage. At least 9 right, p50 at or under 8 s, each with a clip.
- AT4 Open scan: a dumped bag, ordinary light, 20 or more objects. At least 90 percent found, at most 10 percent wrong, p50 at or under 3 s.
- AT5 Hands: at least 25 fps with overlay; tone within 100 ms.
- AT6 Stop: 10 deliberate wrong moves. STOP before contact in at least 9.
- AT7 Holding and reads: holding at least 9 of 10; label reads at least 8 of 10.
- AT8 Decisions: p50 at or under 300 ms; at least 18 of 20 labeled frames right at 0.9.
- AT9 Plan with memory: a goal whose object is out of view gets its location from memory, 3 of 3.
- AT10 Wallet: search finds a matching item; checkout is blocked without "yes"; with "yes" it reaches the checkout confirmation, 3 of 3.
- AT11 Agent: the Managed Agent runs one full goal through the tools with the release and spending hooks firing, 3 of 3.
- AT12 Voice: commands right 9 of 10 in room noise.
- AT13 Evaluation: Sets M, L and S filled as defined; the END CARD renders from the files.
- AT14 Room: setup in 60 s or less, 3 of 3. 10 full rehearsals, 8 clean.

## WOW test (checkable)
In the judging room, live, under 3:00: a judge's question about the day is answered with the right clip. The trip goal is planned using memory and done with zero mistakes landed. One missing item reaches checkout after "yes", with the spending hook on screen. A change made in the room shows up in the timeline.
Evidence: memory_qa.csv and runs.csv rows, and the recording if the room allows it.

## Out of scope
Robot arms, simulation, a phone app, accounts, multi-user, gaze control, folding or assembly jobs.

## Fallbacks (each behind a flag)
- FB1 Argon slow or over its video limit: Neon answers from the event log, marked "log only".
- FB2 Recorder gap: the timeline shows the gap. Never fill it.
- FB3 Shop checkout fails: show the cart and the product page.
- FB4 No client-side tools in the agent: the backend orchestrates (see Managed Agent design).
- FB5 Decisions API down: Hydrogen answers step questions, marked "uncalibrated".
- FB6 Hydrogen slow: scan on change only.
- FB7 No projector: the laptop turns to the judges.
- FB8 Room Wi-Fi: phone hotspot.
- FB9 Everything else: the 60 s recording of the best run, labeled with its time.

## Rules
- All project code is written on event day. The recorder is the first thing built, so memory covers as much of the day as possible.
- Declare open-source libraries in the README.
- Privacy: only our table and team on camera; parsed email fields only; no audio of other people kept.

## Go deeper (Oct 15 rule)
1. What a top professional would do: start recording before anything else works, fix metric definitions before data, take questions from people who did not build it, show where it breaks with a chart, and rehearse room setup as hard as the pitch.
2. Rawest material: the full day's raw footage, the bag as it falls, the live rule pages, raw model JSON and probabilities.
3. Methods and tools: frame-diff event cutting; Hydrogen event labels; Neon retrieval over the log; Argon clip checks; the Decisions API; Shop MCP; Managed Agents tools, hooks, triggers and streaming; MediaPipe; pytest; an AST allowlist.
4. Proof that is not us: judges' own questions, outside questions, the clips themselves, the baselines, source URLs on every rule, the real calendar and checkout.

## After the event
- Release the code, the day's labeled event log, Set M with answers, and the run dataset on Hugging Face, with faces of anyone else removed.
- Paper: a day-long, queryable, actionable memory of a real space from commodity cameras, with calibrated step checks and a hands-in-the-loop executor, against raw long-video baselines.
- Post the pitch clip and the numbers on X, tagging Google DeepMind and Google AI Studio. Send the repo to the judges you met.

## Open questions (answer at the event start)
- Slot length, Q&A length, projector input, which judges sit in which room, how many advance, Managed Agents prize criteria.
- Managed Agent: accepts gemini-4-neon? Client-side tools? MCP? Tool names for hook matchers?
- Argon: video length per call and latency.
- Shop MCP: sign-in with Shop for the demo account; does checkout need a real card; a cheap real item if so.
- Decisions API image format and latency on venue Wi-Fi. Does Hydrogen stream over the Live API?
