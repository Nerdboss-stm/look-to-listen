# PLAN.md: Offscreen (v2, organic)

Every task takes under 30 minutes and ends in a check. Evidence goes in PROGRESS.md.

## Friday Nov 20 (today): learning and gate tests only, no project code
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| F1 | CV Discord: ask demo length and format (table or stage), deadline T, video required, Managed Agents prize criteria, open-source libraries OK, posting a form link OK | 10 min | Posted |
| F2 | Post the team-up message. You need one person for the blindfolded hands and one builder | 10 min | Posted |
| F3 | Make the Google Form (errand, handle) and its Sheet. Submit one test errand | 15 min | The row appears in the Sheet |
| F4 | Photograph your desk exactly as it is now. Do not tidy. Phone 70 to 90 cm above, lamp on | 10 min | Photo saved |
| F5 | Gate G1 open scan, 3 runs on the photo. Score against your own list of what is there | 20 min | 3 rows in gate_log.csv |
| F6 | Gate G2 holding: 10 photos of your hand holding random things from the desk | 20 min | 10 rows logged |
| F7 | Gate G3 label read: hold 4 containers up to the camera, 10 reads | 15 min | 10 rows logged |
| F8 | Gate G6 triage: text 3 friends "give me an errand you'd do with your hands". Add 3 impossible ones. Run all on the desk photo | 25 min | 10 rows logged |
| F9 | Gate G4 Managed Agent hook loop, in a throwaway folder outside this repo | 30 min | Row logged with wall time and tool names |
| F10 | Gate G5: model accepted, client-side tools, Files API inputs | 15 min | Answers in SPEC Open questions |
| F11 | Say the opening (DEMO.md) aloud 10 times, timed | 15 min | Under 25 s |
| F12 | Pack: laptop, chargers, phone, hotspot, lamp, tape, phone mount material, extension cord, blindfold, one mixed box of everyday things, two bags, three boxes | 15 min | Bag packed |
| F13 | Sleep by 11 PM | | |

## Gate decision (by 9 PM tonight)
- G1 at least 90 percent found and at most 10 percent wrong, and G2 at least 9 of 10: go as specced.
- G1 between 75 and 90 percent: use more light and a plain cloth under the table mess; rerun once. Do not remove objects.
- G1 under 75 percent: errands narrow to the bigger objects; the scan ignores anything under 3 cm.
- G3 under 8 of 10: drop label reads; rules that need labels become "can't check" on screen.
- G6 under 9 of 10: tighten the "can't do" list in the triage prompt and rerun once.
- G4 fails: the fast path (SPEC FB2) carries the run; checks arrive when they arrive.
- G5 no client-side tools: the RELEASED file pattern (SPEC FB3).
- No idea changes after this.

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: foundations
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Setup: camera rig, lamp, Wi-Fi and hotspot test, read the rules, write T on paper. Do not arrange the table | Camera feed live in the browser |
| E1 | S1 | contracts/ from SPEC | Sample errand, state and plan validate |
| E2 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E3 | S2 | Camera, MediaPipe hands, overlay, fps counter, wall clock | AT2 fps part passes |
| E4 | S1 | Open scan endpoint | AT1 |
| E5 | S3 | Agent environment, AGENTS.md, skills/offscreen-compiler/SKILL.md; ids in .env | The agent answers a test call |
| E6 | S4 | Post the form link in the event Discord (10 AM) | Posted |
| E7 | S1 | Queue poller: Sheet to errand.json every 15 s | A new form row shows in the queue data |

### Block B, 11:00 to 14:00: the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E8 | S1 | Verify on grasp, read on hold-up | AT4 |
| E9 | S1 | State builder at 10 Hz and change detector (rescan on change) | AT8 rescan part |
| E10 | S2 | Guidance: target ring, distance tone, words, "not that one" before a wrong grasp | A blindfolded teammate reaches 5 named objects, each under 15 s |
| E11 | S1 | Check runner: subprocess, AST allowlist, 50 ms timeout, allowed() before zone entry, STOP | AT3 |
| E12 | S3 | Triage job on every new errand | AT6 |
| E13 | S3 | Compile job against the live scan; release hook with pytest | AT5 |
| E14 | S2 | UI: QUEUE, PLAN, AGENT stream, COUNTERS, big type | A screen photo is readable at 2 m |

### Block C, 14:00 to T minus 3h: close the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E15 | S3 and S1 | post_result to the sender (Discord webhook or email); calendar with approval for Saran's errands | AT7 |
| E16 | S1 and S2 | Replan on change mid-run | AT8 |
| E17 | S2 | Voice: errand by voice (Live API or browser speech) | A spoken errand enters the queue |
| E18 | S3 | Learner: lessons.md, regression cases, regression hook, 30 min trigger | One scheduled run logged; the hook denies a regressing change |
| E19 | S1 | Fast path labeled "unverified" until checks arrive | FB2 works on one run |
| E20 | S4 | Repost the form link (1 PM, 4 PM) | Posted |
| E21 | All | First full run on a queue errand | WOW test attempt on the wall |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E22 | S4 | Runs: at least 6 raw and 6 Offscreen on queue errands, alternating, blindfolded | AT9 |
| E23 | S2 | WALL view from runs.csv, videos linked | Renders all runs |
| E24 | S2 | Stretch, only if AT1 to AT9 pass: blink to approve | Behind a flag |
| E25 | All | Feature freeze at T minus 90 | Only fixes after this |
| E26 | S4 | Rehearse: 10 full runs on 10 different errands | AT10 |
| E27 | S4 | Insurance recording at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E28 | S4 | README: what, how to run, numbers, a Managed Agents section, libraries | README done |
| E29 | S4 | Submit, video within the stated length | Submitted |

## If the team is small
Cut in this order: E24, E19, E18, E17 (type the errand), the Discord half of E15 (show the reply on screen only).
Never cut: E3, E4, E7 to E14, E22, E23, E26, E27.
