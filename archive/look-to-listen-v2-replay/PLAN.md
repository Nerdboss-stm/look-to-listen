# PLAN.md: Look to Listen

Every task takes under 30 minutes and ends in a check. Each Claude Code session loops on its task until the check passes, writes the evidence in PROGRESS.md, then takes the next task. No skipping a failed check.

## Before you leave home (about 45 minutes, no project code)
Follow gemini4-prep/PREFLIGHT.md. It cleans disk space, installs everything, downloads the models and checks mic and camera. Then:
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| P1 | Send the builder post and the DM to Julian (texts below) | 5 min | Sent |
| P2 | Pack: charger, HDMI adapter, headphones, phone stand, extension cord, hotspot tested | 10 min | Packed |
| P3 | Say the opening and the close aloud 5 times | 10 min | Under 15 s each |

### Texts to send
- Discord builder post: "looking for 1 builder for gemini 4 nyc today. look to listen: two people talk at once, you point a phone at one, and you get only their words and their voice. gemini 4 hydrogen + decisions api + managed agents, plus a robot that only obeys who it's looking at. element 119. need someone strong in python audio or realtime web (mediapipe a plus). spec and plan are ready. dm me"
- DM to Julian: "hey julian, building this today at gemini 4 nyc: look to listen. two people talk over each other, you point a phone at one, and it gives you only their words and voice. robot layer too. want to team up? spec's ready"

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: gates first, then the skeleton
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Check-in: our room, its judges, slot length, projector input, how many advance, Managed Agents criteria. Wi-Fi and hotspot test. Write T on paper | Answers in SPEC Open questions |
| E1 | S1 | G1: copy the "G1" lines from gemini4-prep/setup.log into gate_log.csv. Record a 10 s two-talker clip on this laptop and run Engine B on it | Rows in gate_log.csv; clean voice audible |
| E2 | S3 | G2, G3, G4, G6 (prompts.md) | Rows in gate_log.csv |
| E3 | S4 | G5: Managed Agent capabilities (prompts.md) | Answers in SPEC Open questions |
| E4 | All | 10:00 decision (prompts.md table): engine and mode | Written at the top of PROGRESS.md |
| E5 | S1 | contracts/ from SPEC | Sample face, segment, decision, config and command validate |
| E6 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E7 | S2 | Camera and mic capture, 20 s ring buffer, MediaPipe Face Landmarker (model from gemini4-prep/models), face boxes, target ring, fps counter, wall clock | AT1 |

### Block B, 11:00 to 14:00: the core
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E8 | S3 | Raw lane: Hydrogen Live (or 1 s chunks) on the mixed audio | AT3 |
| E9 | S3 | Speaking decisions: Decision 1 per face per 0.5 s, timeline | AT6 |
| E10 | S3 | Engine A: clip + target box to Hydrogen, leakage guard | AT4 for Engine A |
| E11 | S1 | Engine B: audio worker with ClearVoice on the clip and the target's face crops (recipe in SPEC); captions from the clean voice; playback | AT2 |
| E12 | S2 | REPLAY flow: "now only you" on tap; target lane; play voice; switch face | AT5, AT12 |
| E13 | S2 | UI: two lanes, speaker colors, LEAKAGE counters, ENGINE and MODE labels, sized for a projector | A photo of the projected screen reads from 5 m |
| E14 | S3 | Neon: merge, attribute lines to faces, vocab.json | AT7 |
| E15 | S4 | Start Set C: record consenting pairs around the venue, with close-talk phones for truth | 10 clips in clips.csv by 2 PM |
| E16 | S4 | Show it to a DeepMind mentor by 2 PM; feedback in NOTES.md | Feedback written |

### Block C, 14:00 to T minus 3h: agent, hooks, robot, memory
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E17 | S3 | Managed Agent: tools, AGENTS.md, SKILL.md, privacy hook | AT10 |
| E18 | S3 | Tuner: run_eval in the sandbox, release hook with the regression suite, 30 min trigger | AT9 |
| E19 | S3 | Robot R1: target command + frame to Hydrogen pointing; ROBOT panel; command hook | AT11 |
| E20 | S3 | Argon memory answers and summary | AT8 |
| E21 | S2 | AGENT stream, MEMORY box, ROBOT panel in the UI | Hook decisions visible from 5 m |
| E22 | All | First full room run | WOW attempt logged |
| E23 | S4 | After the first clean run (target 3 PM): post a clip of 30 s or less on X, tagging Google DeepMind and Google AI Studio | Posted |
| E24 | S4 | Set C to 40 two-talker and 10 three-talker clips; Set R to 10 command pairs | clips.csv and robot.csv filled |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E25 | S4 | Run B0, Engine A and Engine B on every Set C clip; compute WER, leakage, attribution, time | clips.csv scored |
| E26 | S4 | Set D: label speaking windows; Decision 1 calibration chart | decisions.csv filled, chart saved |
| E27 | S4 | Where it breaks: leakage and WER by noise, talkers, angle, distance, occlusion | Charts on the END CARD |
| E28 | All | Feature freeze at T minus 90 | Only fixes after this |
| E29 | S4 | 10 full rehearsals with different second talkers; 3 mock-room pitches with Q&A asked cold | AT14 |
| E30 | S4 | Insurance recording at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E31 | S4 | README: what, how to run, eval tables, where it breaks, a Managed Agents section with the hook diagram, declared libraries and models | README done |
| E32 | S4 | Submit, video within the stated length | Submitted |

### Stretch, only after E22 is clean
- S1 LIVE mode: rolling 3 s windows for Engine B, only if G1 showed 2.4 s or less.
- S2 Robot R2: MuJoCo Menagerie Panda (gemini4-prep/third_party) reaches for the asked block in sim. Only with a teammate.

## Build order if time runs short
Each layer must work on its own before the next starts.
1. Faces, raw lane, speaking decisions, the chosen engine, REPLAY flow (E7 to E13). Two lanes and a clean replay is a demo.
2. Managed Agent with the privacy hook (E17). Needed for the Managed Agents prize.
3. Robot R1 with the command hook (E19). The robotics answer.
4. Tuner with the release hook (E18).
5. Memory and Neon polish (E14, E20).

## If the team is small
Cut in this order: E23, translation, E20 memory (keep the summary), the second engine (keep the 10:00 winner), three-talker clips.
Never cut: E7 to E13, E17, E19, E24, E25, E29, E30.
