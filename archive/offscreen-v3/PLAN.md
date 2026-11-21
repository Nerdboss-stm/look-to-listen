# PLAN.md: Offscreen (v3, room format)

Every task takes under 30 minutes and ends in a check. Evidence goes in PROGRESS.md.

## Friday Nov 20 (today): gate tests, the demo board, pitch practice. No project code.
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| F1 | CV Discord: slot length and Q&A length in the rooms, projector and HDMI, which judges sit in which room, how many advance from each room, Managed Agents prize criteria, open-source libraries OK | 10 min | Posted |
| F2 | Post the team-up message. You need one person for the blindfolded hands and one builder | 10 min | Posted |
| F3 | Build the demo board: a tray or stiff board with a rim, a cardboard mast taped to it, the phone 60 to 80 cm above the center, tape marks for "bag" and "stays home" | 30 min | Carry it across the room; the phone does not move |
| F4 | Dump your real backpack onto the board as it is. Normal room light. Photo from the mast | 5 min | Photo saved |
| F5 | Gate G1 open scan, 3 runs on that photo (prompts.md). Score against your own list | 20 min | 3 rows in gate_log.csv |
| F6 | Gate G2 holding: 10 photos of your hand holding things from the pile | 20 min | 10 rows logged |
| F7 | Gate G3 label read: 4 containers held up, 10 reads | 15 min | 10 rows logged |
| F8 | Gate G6 triage: the same pile, 10 errands (trip, gym, coffee meeting, recycling, and 3 impossible ones) | 20 min | 10 rows logged |
| F9 | Gate G4 Managed Agent hook loop, in a throwaway folder outside this repo | 30 min | Row logged with wall time and tool names |
| F10 | Gate G5: model accepted, client-side tools, Files API inputs | 15 min | Answers in SPEC Open questions |
| F11 | Time the room setup 3 times: HDMI in, board down, phone feed on the big screen (QuickTime is fine tonight) | 15 min | 3 times under 60 s |
| F12 | Pitch: say the 2 s silence, the first line, the engineer hook and the close aloud 10 times. Record one full talk-through on your phone and watch it once | 30 min | Under 3:00, nothing said that would not be on screen |
| F13 | Pack: laptop, USB-C to HDMI adapter, chargers, phone, hotspot, the board, tape, extension cord, sleep mask, one earbud. Pack your backpack the way you normally would for the day | 15 min | Packed |
| F14 | Sleep by 11 PM | | |

## Gate decision (by 9 PM tonight)
- G1 at least 90 percent found and at most 10 percent wrong, and G2 at least 9 of 10: go as specced.
- G1 between 75 and 90 percent: brighter light on the board, rerun once. Do not remove objects.
- G1 under 75 percent: the scan ignores objects under 3 cm and says so on screen.
- G3 under 8 of 10: drop label reads; label rules show as "can't check".
- G6 under 9 of 10: tighten the "can't do" list and rerun once.
- G4 fails: the fast path carries every run; checks land when they land.
- F11 over 60 s: simplify the board until it is under 60 s.
- No idea changes after this.

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: foundations
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Check-in: our room, which judges, slot length, projector input. Set up the board, Wi-Fi and hotspot test, write T on paper | Answers in SPEC Open questions; camera feed live |
| E1 | S1 | contracts/ from SPEC | Sample errand, state and plan validate |
| E2 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E3 | S2 | Camera, MediaPipe hands, overlay, fps counter, wall clock | AT2 fps part passes |
| E4 | S1 | Open scan endpoint | AT1 |
| E5 | S3 | Agent environment, AGENTS.md, skills/offscreen-compiler/SKILL.md; ids in .env | The agent answers a test call |

### Block B, 11:00 to 14:00: the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E6 | S1 | Verify on grasp, read on hold-up | AT4 |
| E7 | S1 | State builder at 10 Hz and change detector | A new object on the board triggers a rescan |
| E8 | S2 | Guidance: target ring, tone on the speaker, words in one earbud, "not that one" before a wrong grasp | A blindfolded teammate reaches 5 named objects, each under 15 s |
| E9 | S1 | Check runner: subprocess, AST allowlist, 50 ms timeout, allowed() before zone entry, STOP | AT3 |
| E10 | S3 | Compile job for the real trip errand; release hook with pytest | AT5 |
| E11 | S2 | UI sized for a projector: PLAN, AGENT stream, COUNTERS | A photo of the projected screen reads from 5 m |

### Block C, 14:00 to T minus 3h: the moments
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E12 | S3 and S1 | Calendar close with approval | AT8 |
| E13 | S1 | Borrowed object: rescan, judge against the plan's rules, assign a zone | AT6 |
| E14 | S1 and S3 | Second errand: fast path plan in seconds, checks land after | AT7 |
| E15 | S3 | Learner: lessons.md, regression cases, regression hook, 30 min trigger | One scheduled run logged; the hook denies a regressing change |
| E16 | S2 | END CARD: name, line, today's counts, repo link and QR | Renders from runs.csv |
| E17 | All | First full room run, setup timed | AT11 and a WOW attempt in runs.csv |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E18 | S4 | Runs: at least 6 raw and 6 Offscreen, different errands and piles, alternating, blindfolded | AT9 |
| E19 | All | Feature freeze at T minus 90 | Only fixes after this |
| E20 | S4 | Rehearse: 10 full runs on different bags and errands | AT10 |
| E21 | S4 | 3 mock-room runs: setup timed, the full pitch, a teammate asking the Q&A cold | 3 under 3:00 |
| E22 | S4 | Insurance recording at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E23 | S4 | README: what, how to run, numbers, a Managed Agents section, libraries | README done |
| E24 | S4 | Submit, video within the stated length | Submitted |

## If the team is small
Cut in this order: E15, E16 (a plain text card), voice (type the second errand), the fast path (say "checks compiling" and wait).
Never cut: E3, E4, E6 to E11, E13, E17, E18, E20, E21, E22.
