# PLAN.md: Look to Listen

Every task takes under 30 minutes and ends in a check. Each Claude Code session loops on its task until the check passes, writes the evidence in PROGRESS.md, then takes the next task. No skipping a failed check.

## Tonight
Sleep. A rested presenter is worth more than any feature.

## Before 9 AM (no project code)
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| P1 | Send the builder post and the DM to Julian (texts below) | 5 min | Sent |
| P2 | Charge laptop, phone, headphones, hotspot. Pack over-ear headphones, a spare wired pair, HDMI adapter, phone stand, extension cord | 15 min | Packed |
| P3 | Say the opening and the close aloud 5 times | 10 min | Under 15 s each |

### Texts to send
- Discord builder post: "looking for 1 builder for gemini 4 nyc today. look to listen: point a phone at someone in a loud room and you get live captions and audio of only them. gemini 4 hydrogen + decisions api + managed agents. element 119. need someone strong in python audio or realtime web (mediapipe a plus). spec and plan are ready. dm me"
- DM to Julian: "hey julian, building this today at gemini 4 nyc: look to listen. in a loud room you point a phone at one person and get captions and audio of only them. live, on gemini 4. want to team up? spec's ready"

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: gates first, then the skeleton
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Check-in: our room, its judges, slot length, projector input, how many advance, Managed Agents criteria. Wi-Fi and hotspot test. Write T on paper | Answers in SPEC Open questions |
| E1 | S1 | G1: RAVEN cloned, installed, live demo running on this laptop (prompts.md) | Row in gate_log.csv with real-time factor |
| E2 | S3 | G2, G3, G4: Hydrogen captions, Decision 1 speaking, Gemini-only targeting (prompts.md) | Rows in gate_log.csv |
| E3 | S4 | G5: Managed Agent capabilities (prompts.md) | Answers in SPEC Open questions |
| E4 | All | 10:00 decision: G1 pass means the full build. G1 fail means FB1 (Gemini-only target lane, no headphones) | Written at the top of PROGRESS.md |
| E5 | S1 | contracts/ from SPEC | Sample face, segment, decision and config validate |
| E6 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E7 | S2 | Camera and mic capture, MediaPipe Face Landmarker, face boxes, target ring, fps counter, wall clock | AT1 |

### Block B, 11:00 to 14:00: the live loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E8 | S1 | Audio worker: RAVEN fed by target mouth crops, clean audio out to headphones and to the backend | AT2 |
| E9 | S3 | Captioner: Hydrogen Live (or 1 s chunks) on the target stream | AT3 |
| E10 | S3 | Raw lane B0 on the mixed audio, same captioner | AT11 |
| E11 | S3 | Speaking decisions: Decision 1 per face per 0.5 s, timeline | AT6 |
| E12 | S3 | Leakage guard and target switching | AT4, AT5 |
| E13 | S2 | UI: two lanes, speaker colors, LEAKAGE counters, sized for a projector | A photo of the projected screen reads from 5 m |
| E14 | S3 | Neon: merge, attribute lines to faces, vocab.json | AT7 |
| E15 | S4 | Start Set C: record consenting pairs around the venue, with close-talk phones for truth | 10 clips in clips.csv by 2 PM |
| E16 | S4 | Show it to a DeepMind mentor by 2 PM; feedback in NOTES.md | Feedback written |

### Block C, 14:00 to T minus 3h: memory, the agent, the hooks
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E17 | S3 | Argon memory answers and summary | AT8 |
| E18 | S3 | Managed Agent: tools, AGENTS.md, SKILL.md, privacy hook | AT10 |
| E19 | S3 | Tuner: run_eval in the sandbox, release hook with the regression suite, 30 min trigger | AT9 |
| E20 | S2 | AGENT stream and MEMORY box in the UI | Hook decisions visible from 5 m |
| E21 | All | First full room run | WOW attempt logged |
| E22 | S4 | After the first clean run (target 3 PM): post a clip of 30 s or less on X, tagging Google DeepMind and Google AI Studio | Posted |
| E23 | S4 | Set C to 40 two-talker and 10 three-talker clips | clips.csv filled |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E24 | S4 | Run B0, B1 and B2 on every Set C clip; compute WER, leakage, attribution, latency | clips.csv scored |
| E25 | S4 | Set D: label speaking windows; Decision 1 calibration chart | decisions.csv filled, chart saved |
| E26 | S4 | Where it breaks: leakage and WER by noise, talkers, angle, distance, occlusion | Charts on the END CARD |
| E27 | All | Feature freeze at T minus 90 | Only fixes after this |
| E28 | S4 | 10 full rehearsals with different second talkers; 3 mock-room pitches with Q&A asked cold | AT13, AT14 |
| E29 | S4 | Insurance recording at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E30 | S4 | README: what, how to run, eval tables, where it breaks, a Managed Agents section with the hook diagram, declared libraries and models | README done |
| E31 | S4 | Submit, video within the stated length | Submitted |

## Build order if time runs short
Each layer must work on its own before the next starts.
1. Faces, captions, raw lane, speaking decisions, leakage guard (E7, E9 to E13). Two lanes side by side is a demo.
2. RAVEN and headphones (E8). The listening moment.
3. Managed Agent with the privacy hook (E18). Needed for the Managed Agents prize.
4. Tuner with the release hook (E19).
5. Memory and Neon polish (E14, E17).

## If the team is small
Cut in this order: E22, translation, E17 memory (keep the summary), E8 headphones (FB1), three-talker clips.
Never cut: E7, E9 to E13, E18, E23, E24, E28, E29.
