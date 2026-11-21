# Make Do: SPEC

Working name. Gemini 4 NYC Hackathon (Cerebral Valley), Sat Nov 21, 2026, The Malin, 220 W 26th St.

## One line
Pick any 5 everyday objects and a goal. Gemini 4 designs a build, bets on whether it will hold, and talks your hands through it live. Physics decides. A harness and a Managed Agent make every next design better.

## Opening line (under 30 s, rehearsed aloud)
"In 1970, Apollo 13's crew built a CO2 filter from whatever was on board. Today Gemini does that live, with whatever is on this table. Pick any five things. Pick a goal."

## Closing line
"Gemini designs it, bets on it, and learns when physics proves it wrong."

## What we prove on screen
1. Capability: Gemini 4 designs and directs a real build from objects it has never seen, live.
2. Finding: how well Gemini's bet matches the physical result.
3. Contribution: the harness beats raw Hydrogen on pass rate and bet accuracy, and improves during the day.

Never claim the harness makes a better model. Claim: "Hydrogen with this harness beats Hydrogen alone on this task."

## Kit (fixed, from home)
Hardcover book, notebook, mug, paper cup, 4 pens or pencils, 5 rubber bands, masking tape, 4 binder clips or clothespins, 5 sheets of paper, charging cable, coins (scale and weight), one sock, plain towel as the mat.
No glass, nothing sharp, no liquids.

## Goal cards (each has a physical test)
| ID | Goal | Pass test |
| --- | --- | --- |
| G1 | Phone stand | Holds the judge's phone upright for 10 s |
| G2 | Bridge | Spans 20 cm between two books and holds the mug for 5 s |
| G3 | Lift | Holds the mug 15 cm above the table for 10 s |
| G4 | Tower | 30 cm tall, survives one tap on the table |
| G5 | Judge's own | Judge states the goal and the pass test out loud before design starts |

## Demo flow (3:00)
| Time | What happens |
| --- | --- |
| 0:00 to 0:20 | Opening line |
| 0:20 to 0:40 | Judge picks 5 items and a goal card. Sizes appear on the objects in the live feed |
| 0:40 to 1:00 | Five design cards appear. Argon picks one. The bet shows ("83% this holds") beside raw Hydrogen's pick and bet |
| 1:00 to 2:20 | Live build: voice, arrow follows the hand, "stop" before a wrong placement |
| 2:20 to 2:40 | Physics test. Pass or fail. Scoreboard updates |
| 2:40 to 3:00 | Agent panel: the lesson it just wrote, the hook verdict, today's numbers. Closing line |

If the build fails: the agent writes a lesson, the harness redesigns, and the second try is the story.

## Architecture
Three live loops, a design harness and a learner.
- L0, laptop, 30 fps, no model: camera, MediaPipe Hand Landmarker, overlay, hover warning, recorder.
- L1, Hydrogen live checks, 1 to 3 per second: newest frame and current step in; step_done, target_point, risk and what to say out. Thinking low. Switch to xhigh only after a failed check.
- L2, Gemini Live: continuous voice both ways, video about 1 fps for context. Speaks instructions and corrections. Listens for "wait", "repeat", "done".
- Design harness, once per trial, target under 20 s: measure objects (coin for scale), then 5 designs in parallel (Hydrogen), then Argon critiques and ranks, then the bet. Also log raw Hydrogen's single design and bet for the comparison.
- Physical test: operator taps PASS or FAIL, timer runs.
- Learner, Managed Agent, never in the live loop: after each trial it reads the trial record and key frames, writes a lesson into skills/make-do/SKILL.md, and runs regression on archived trials in its sandbox. A pre_tool_execution command hook denies a lesson that breaks a past pass. A scheduled trigger re-analyzes every 30 min. It publishes the dataset with a managed credential. Network allowlist: Hugging Face and our endpoint.

## Models (confirm exact ids in AI Studio before building)
| Job | Model | Notes |
| --- | --- | --- |
| Designs, live checks, points | gemini-4-hydrogen | Thinking low in the loop; xhigh on failure |
| Critic and ranker | gemini-4-argon | Different model from the designer; paid key |
| Voice | gemini-3.8-live | Live API; video is about 1 fps |
| Learner | Managed Agent (Antigravity agent) | Test which models agent_config accepts |
| Hands | MediaPipe Hand Landmarker | In the browser, 30 fps |

## Contracts (create first on Saturday; everything reads and writes these)
- contracts/kit.json: items with id, name, approximate size in cm, approximate weight in g
- contracts/goals.json: G1 to G5 with pass tests
- contracts/design.schema.json: design_id, goal_id, items_used, steps (id, instruction, object, placement, success_check), pass_probability, failure_modes, rationale
- contracts/trial.schema.json: trial_id, time, goal_id, items, designs, chosen_design_id, raw_design, raw_bet, harness_bet, outcome, test_seconds, corrections, steps_log, consent, video_path
- skills/make-do/SKILL.md: lessons, each tied to the trial that produced it

## Acceptance tests (the build is done only when each passes)
- AT1 Design: a photo of 5 kit items plus a goal returns 5 schema-valid designs, Argon's pick and a bet in under 20 s, in 9 of 10 runs.
- AT2 Overlay: the arrow follows the hand at 24 fps or better with no visible lag.
- AT3 Stop: a hand hovering over a wrong spot triggers a spoken "stop" within 1.5 s, in 8 of 10 tries.
- AT4 Voice: each instruction is spoken within 1 s of its step starting; "wait" and "repeat" work.
- AT5 Trial record: PASS or FAIL saves a schema-valid trial and updates the scoreboard.
- AT6 Learner: a lesson appears within 90 s of a failed trial; the hook denies at least one lesson that breaks a past pass, shown on screen.
- AT7 Export: episodes publish to Hugging Face; the hook blocks any episode without consent.
- AT8 Cost: every model call logs model, latency, tokens and cost to logs/calls.jsonl.
- WOW: a first-time person picks any 5 kit items and G1, and a passing phone stand is built in under 3 minutes, with the bet shown before building and the result on screen. Run 10 times on Saturday; at least 8 pass.

## Numbers on screen
- Pass rate: raw Hydrogen vs harness (event-day trials only)
- Bet accuracy: bet vs actual result
- Errors caught before placement
- Build time
- Agent stats: analyses run, lessons written, lessons blocked

## Out of scope
Physics simulator, robots, blindfold, a second task type, more models.

## Fallbacks
- Argon slow or missing: Hydrogen at xhigh as the critic
- Live voice drops: browser speech synthesis with on-screen captions
- Wi-Fi fails: phone hotspot
- Anything stalls more than 5 s on stage: play the insurance recording and narrate

## Rules
All submitted code and data are created on Saturday. Work before that is learning and testing only.

## Open questions
- Demo length, judging format, submission deadline, video requirement
- Managed Agents prize criteria
- Which models the Managed Agent accepts
- Teammate

## Go deeper
1. What a top professional does: measures the raw baseline before claiming any gain, fixes the metric before collecting data, and logs every trial.
2. Rawest material: the Gemini API reference, the Managed Agents docs (overview, quickstart, hooks, environments, credentials), the Live API docs, the MediaPipe Hand Landmarker docs.
3. Tools: google-genai SDK, Live API with ephemeral tokens, MediaPipe Tasks Vision, a JSONL call log.
4. What proves it right besides Claude or Saran: physics (pass or fail), judges' own trials, raw vs harness numbers, API logs.
