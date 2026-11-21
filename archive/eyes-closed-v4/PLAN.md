# PLAN.md: Eyes Closed

Every task takes under 30 minutes and ends in a check. Evidence goes in PROGRESS.md.

## Friday Nov 20 (from 4:15 PM): recruit, collect, test, rehearse. No project code.
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| F1 | Send the builder post in the event Discord and the DM to Julian (texts below) | 10 min | Both sent |
| F2 | Text 10 friends for bag photos (text below) | 5 min | Sent |
| F3 | Event Discord: slot length, Q&A length, projector input, which judges sit in which room, how many advance, Managed Agents prize criteria, open-source libraries OK | 10 min | Posted |
| F4 | Build the demo board: tray or stiff board with a rim, cardboard mast, phone 60 to 80 cm above the center, tape marks for "bag" and "stays home" | 30 min | Carry it across the room; the phone does not move |
| F5 | Dump your real backpack onto the board as it falls. Normal room light. Photo from the mast | 5 min | Photo saved |
| F6 | Gate G1 open scan, 3 runs (prompts.md) | 20 min | 3 rows in gate_log.csv |
| F7 | Gate G2 holding: 10 photos of your hand holding things from the pile | 20 min | 10 rows logged |
| F8 | Gate G8 Decisions API: 20 hand photos, one yes or no question each, in a throwaway folder outside this repo | 25 min | 20 rows and p50 latency logged |
| F9 | Gate G3 label read: 4 containers held up, 10 reads | 15 min | 10 rows logged |
| F10 | Gate G6 Neon plan: the pile photo and 10 errands, 3 of them impossible | 20 min | 10 rows logged |
| F11 | Gate G7: does Hydrogen stream live in AI Studio | 10 min | Answer in SPEC Open questions |
| F12 | Gate G4 Managed Agent hook loop, throwaway folder | 30 min | Row logged with wall time and tool names |
| F13 | Gate G5: does the agent accept gemini-4-neon, client-side tools, Files API inputs | 15 min | Answers in SPEC Open questions |
| F14 | As friends' photos arrive: save each, write the correct plan for it in cases.csv before running anything on it | 20 min | One row per photo |
| F15 | Time the room setup 3 times: HDMI in, board down, phone feed on the big screen | 15 min | 3 times under 60 s |
| F16 | Blind practice: mask on, opener and close 10 times; one masked repack while saying the pitch, recorded | 30 min | Under 3:00 |
| F17 | Pack: laptop, USB-C to HDMI adapter, chargers, phone, hotspot, the board, tape, extension cord, sleep mask, one earbud. Pack your backpack the way you normally would | 15 min | Packed |
| F18 | Sleep by 11 PM | | |

### Texts to send
- Discord builder post: "looking for 1 builder for gemini 4 nyc tmrw. eyes closed: i pitch blindfolded while gemini 4 sees for me, guides my hands through a real errand, and proves every step is done. 5 sigma track. need someone strong in typescript and realtime camera (mediapipe a plus). spec, eval plan and agent design are ready. dm me"
- DM to Julian: "hey julian, saw your post in the gemini 4 nyc discord. building this for tmrw: i pitch blindfolded while gemini 4 guides my hands through a real errand and proves each step is done. your rl and hci background fits it really well. want to team up? spec's ready"
- Friends: "hey quick favor for my hackathon tmrw. dump your bag on a table, send me one photo from above, and tell me one errand you'd give an AI. takes 30 sec"

## Gate decision (by 9 PM tonight)
- G1 at least 90 percent found and at most 10 percent wrong, and G2 at least 9 of 10: go as specced.
- G1 between 75 and 90 percent: brighter light, rerun once. Do not remove objects.
- G1 under 75 percent: the scan ignores objects under 3 cm and says so on screen.
- G8 p50 over 500 ms or fewer than 16 of 20 correct: Hydrogen answers step questions, marked "uncalibrated" (SPEC FB3).
- G3 under 8 of 10: drop label reads; label rules show as "can't check".
- G6 under 8 of 10 against your judgment: tighten the "can't do" list and the prompt, rerun once.
- G7 no: Hydrogen uses snapshots, about once a second.
- G4 fails: the fast plan carries every run, labeled "unverified" until checks land.
- G5 no Neon in the agent: the agent calls Neon through the API (SPEC FB4).
- F15 over 60 s: simplify the board until it is under 60 s.
- No idea changes after this.

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: foundations
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Check-in: our room, its judges, slot length, projector input. Set up the board, Wi-Fi and hotspot test, write T on paper | Answers in SPEC; camera feed live |
| E1 | S1 | contracts/ from SPEC | Sample errand, state, plan and step validate |
| E2 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E3 | S2 | Camera, MediaPipe hands, overlay, fps counter, wall clock | AT2 fps part passes |
| E4 | S1 | Hydrogen open scan endpoint | AT1 |
| E5 | S3 | Agent environment, AGENTS.md, skills/eyes-closed-compiler/SKILL.md, Neon wiring; ids in .env | The agent answers a test call |
| E6 | S1 | Decisions client: one question per step, threshold and abstain rule from contracts/decision.md | AT5 |

### Block B, 11:00 to 14:00: the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E7 | S1 | Holding and label reads | AT4 |
| E8 | S1 | State builder at 10 Hz and change detector | A new object on the board triggers a rescan |
| E9 | S2 | Guidance: target ring, tone on the speaker, words in one earbud, "not that one" before a wrong grasp, tuned for a presenter who is talking | Saran, blindfolded, reaches 5 named objects, each under 15 s |
| E10 | S1 | Check runner: subprocess, AST allowlist, 50 ms timeout, allowed() before zone entry, STOP, PROVEN only with check and decision | AT3 |
| E11 | S3 | Compile: Neon writes plan and checks, the agent tests them, release hook with pytest | AT6 |
| E12 | S2 | UI sized for a projector: PLAN, AGENT stream, COUNTERS, green PROVEN flash | A photo of the projected screen reads from 5 m |
| E13 | S4 | Show it to a DeepMind mentor by 2 PM. Write their feedback in NOTES.md | Feedback written |

### Block C, 14:00 to T minus 3h: the moments
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E14 | S2 | Voice commands for a blindfolded presenter: "get me ready", "next errand", "yes" | AT10 |
| E15 | S3 and S1 | Calendar close after "yes" | AT9 |
| E16 | S1 | Mystery object: guide it up to the camera, name it, judge it, place it or hand it back | AT7 |
| E17 | S1 and S3 | Second errand: fast plan in seconds, checks land after | AT8 |
| E18 | S3 | Learner: lessons.md, regression cases, regression hook, 30 min trigger | One scheduled run logged; the hook denies a regressing change |
| E19 | S2 | END CARD: name, line, Set A, B and C numbers, failure line, repo link and QR | Renders from the CSV files |
| E20 | All | First full blindfolded run | WOW attempt in runs.csv |
| E21 | S4 | After the first clean run (target 3 PM): post a clip of 30 s or less on X, tagging Google DeepMind and Google AI Studio | Posted |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E22 | S4 | Set A: run Eyes Closed and baseline B1 on every friend case | cases.csv filled |
| E23 | S4 | Set B: at least 6 B2 and 6 Eyes Closed live runs, alternating, blindfolded, different bags and errands | runs.csv filled |
| E24 | S4 | Set C: label every Set B step true or false from the video; reliability chart for Decision 1 | steps.csv filled, chart saved |
| E25 | S4 | Failure card: the top 2 failure types, one example each, what we changed | On the END CARD and in the README |
| E26 | All | Feature freeze at T minus 90 | Only fixes after this |
| E27 | S4 | 10 full blindfolded rehearsals by Saran on different bags and errands | AT13 |
| E28 | S4 | 3 mock-room pitches: setup timed, the full pitch, Q&A asked cold | 3 under 3:00 |
| E29 | S4 | Insurance recording at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E30 | S4 | README: what, how to run, eval tables, failure card, a Managed Agents section with the hook diagram, libraries | README done |
| E31 | S4 | Submit, video within the stated length | Submitted |

## If the team is small
Cut in this order: E21, E18, E17, the reliability chart in E24 (keep the counts), E14 (an operator uses the keyboard instead, if you have one).
Never cut: E3, E4, E6, E7, E9 to E12, E16, E19, E22, E23, E25, E27, E29.
