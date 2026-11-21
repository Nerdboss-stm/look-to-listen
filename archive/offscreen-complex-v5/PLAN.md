# PLAN.md: Offscreen (complex base)

Every task takes under 30 minutes and ends in a check. Each Claude Code session loops on its task until the check passes, writes the evidence in PROGRESS.md, then takes the next task. No skipping a failed check.

## Tonight
Sleep. A rested presenter is worth more than any feature.

## Before 9 AM (no project code)
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| P1 | Send the builder post and the DM to Julian (texts below) | 5 min | Sent |
| P2 | Charge laptop, phone, earbuds, hotspot. Pack the board, tape, HDMI adapter, extension cord, backpack as you normally would | 15 min | Packed |
| P3 | Say the opening and the close aloud 5 times | 10 min | Under 15 s each |

### Texts to send
- Discord builder post: "looking for 1 builder for gemini 4 nyc today. offscreen: an agent that watches a real table all day, answers anything about it with the clip, guides your hands through physical jobs, and orders what's missing on shopify. element 119. need someone strong in typescript and realtime video (mediapipe a plus). spec and plan are ready. dm me"
- DM to Julian: "hey julian, building this today at gemini 4 nyc: an agent that remembers a whole day of a real table, guides your hands through jobs, and buys what's missing. your rl and hci background fits it really well. want to team up? spec's ready"
- Friends, at about 4 PM, with a 60 s timelapse of the day: "quick favor: this is my hackathon table today sped up. text me 3 questions you'd ask a camera that watched it all day (where did X go, when did Y happen, anything)"

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: start remembering first
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Check-in: our room, its judges, slot length, projector input, how many advance. Board on our work table, mast up, Wi-Fi and hotspot test, write T on paper | Answers in SPEC Open questions; overhead feed live |
| E1 | S1 | Recorder: overhead 2 fps and laptop camera 1 fps into timestamped 5 min segments; change detector cuts event clips | Recording by 10:00; a moved object makes a clip |
| E2 | S1 | contracts/ from SPEC | Sample event, state, plan and answer validate |
| E3 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E4 | S3 | Event labeler: Hydrogen labels each clip into events.jsonl | AT2 |
| E5 | S2 | Camera, MediaPipe hands, overlay, fps counter, wall clock | AT5 fps part |
| E6 | S4 | Gate tests G1, G8, G9, G10, G11, G5 (prompts.md) | Rows in gate_log.csv; answers in SPEC |

### Block B, 11:00 to 14:00: memory and the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E7 | S3 | Memory query: Neon over events.jsonl finds candidates, Argon checks the clips, answer with time and clip | AT3 |
| E8 | S1 | Open scan, holding, label reads | AT4, AT7 |
| E9 | S1 | Decisions client: step questions and "still there?" | AT8 |
| E10 | S2 | Guidance: target ring, tone, words in one earbud, "not that one" before a wrong grasp | Saran reaches 5 named objects, each under 15 s |
| E11 | S1 | Check runner: subprocess, AST allowlist, 50 ms timeout, STOP, PROVEN only with check and decision | AT6 |
| E12 | S3 | Plan with memory: Neon plans from memory, live scan, email and rule pages, writes checks; release hook with pytest | AT9 |
| E13 | S2 | UI: TIMELINE, ANSWER clip player, PLAN, AGENT stream, COUNTERS, sized for a projector | A photo of the projected screen reads from 5 m |
| E14 | S4 | Show it to a DeepMind mentor by 2 PM; feedback in NOTES.md | Feedback written |

### Block C, 14:00 to T minus 3h: the agent and the wallet
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E15 | S3 | Managed Agent orchestration: recall, look, plan, execute, verify, calendar_add as client-side tools | AT11 without the wallet |
| E16 | S3 and S1 | Wallet: Shop MCP search and checkout behind gate_spend.py | AT10 |
| E17 | S2 | Voice commands in room noise | AT12 |
| E18 | S3 | Learner: lessons.md, regression cases, regression hook, 30 min trigger | One scheduled run logged; the hook denies a regressing change |
| E19 | All | First full room run | WOW attempt logged |
| E20 | S4 | After the first clean run (target 3 PM): post a clip of 30 s or less on X, tagging Google DeepMind and Google AI Studio | Posted |
| E21 | S4 | About 4 PM: send friends the timelapse text | Sent |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E22 | S4 | Set M: outside and judge questions labeled from footage; Offscreen and raw Argon on each | memory_qa.csv filled |
| E23 | S4 | Set L: at least 6 raw and 6 Offscreen live jobs, alternating, different bags and goals | runs.csv filled |
| E24 | S4 | Set S: every step labeled from video; Decision 1 calibration chart | steps.csv filled, chart saved |
| E25 | S4 | Where it breaks: Set M by footage age, occlusion and size; voice by noise | Charts on the END CARD |
| E26 | All | Feature freeze at T minus 90 | Only fixes after this |
| E27 | S4 | 10 full rehearsals on different bags and goals; 3 mock-room pitches with Q&A asked cold | AT14 |
| E28 | S4 | Insurance recording at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E29 | S4 | README: what, how to run, eval tables, where it breaks, a Managed Agents section with the hook diagram, libraries | README done |
| E30 | S4 | Submit, video within the stated length | Submitted |

## Build order if time runs short
Each layer must work on its own before the next starts.
1. Recorder, event log, memory query (E1, E4, E7). Memory alone is a demo.
2. Open scan, guidance, check runner, plan with memory (E8 to E13). Memory plus hands is a strong demo.
3. Managed Agent orchestration (E15). Needed for the Managed Agents prize.
4. Wallet (E16). Needed for the Shopify bonus.
5. Learner and voice (E17, E18).

## If the team is small
Cut in this order: E20, E18, E17 (an operator types), E16 checkout (stop at the cart), the laptop camera stream.
Never cut: E1, E4, E7, E8 to E13, E15, E22, E23, E27, E28.
