# PLAN.md: Offscreen

Every task takes under 30 minutes and ends in a check. Evidence goes in PROGRESS.md.

## Friday Nov 20 (today): learning and gate tests only, no project code
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| F1 | CV Discord: ask demo length and format, submission deadline T, video required, Managed Agents prize criteria, declared open-source libraries OK | 10 min | Posted |
| F2 | Post the team-up message. You need one person for the blindfolded hands and one builder | 10 min | Posted |
| F3 | Lay out the kit (SPEC Kit), lamp on. One top-down phone photo from 70 to 90 cm | 20 min | Photo saved |
| F4 | Gate G1 pointing (prompts.md), 3 runs on the photo | 20 min | 3 rows in gate_log.csv |
| F5 | Gate G2 holding: 10 photos of a hand holding kit items; include items 2, 3, 16, 17 | 20 min | 10 rows logged |
| F6 | Gate G3 label read: hold 4 containers up to the camera, 10 reads | 15 min | 10 rows logged |
| F7 | Gate G4 Managed Agent hook loop, in a throwaway folder outside this repo | 30 min | Row logged with wall time and tool names |
| F8 | Gate G5: does the agent accept gemini-4-hydrogen; are client-side function tools supported; can the Files API pass inputs | 15 min | Answers in SPEC Open questions |
| F9 | Demo Gmail: forward the real flight email; open the demo calendar | 10 min | Email visible in the demo inbox |
| F10 | Say the opening (DEMO.md) aloud 10 times, timed | 15 min | Under 27 s |
| F11 | Pack: laptop, chargers, phone, hotspot, lamp, tape, phone mount material, extension cord, blindfold, kit, two bags | 15 min | Bag packed |
| F12 | Sleep by 11 PM | | |

## Gate decision (by 9 PM tonight)
- G1 at least 18 of 20 and G2 at least 9 of 10: go as specced.
- G1 at 15 to 17: swap the missed items for more distinct ones, rerun once.
- G1 under 15 or G2 under 8: keep the concept, cut the kit to 10 distinct items, drop the look-alike pairs.
- G3 under 8 of 10: drop label reads. Liquids use "travel size or full size" by look.
- G4 fails: compile before the demo and show the recorded stream with its time (SPEC FB2). The live loop stays.
- G5 says no client-side tools: use the RELEASED file pattern (SPEC FB3).
- No idea changes after this.

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: foundations
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Setup: table, taped zones and item spots, camera rig, lamp, Wi-Fi and hotspot test, read the rules, write T on paper | Camera feed live in the browser |
| E1 | S1 | contracts/ from SPEC | A sample state and a sample plan validate |
| E2 | S1 | FastAPI skeleton, .env, call logger, websocket | calls.jsonl gets a row; ws echo works |
| E3 | S2 | Camera, MediaPipe hands, overlay, fps counter | AT2 fps part passes |
| E4 | S1 | Hydrogen scan endpoint and item map from kit.json | AT1 |
| E5 | S3 | Agent environment, AGENTS.md, skills/offscreen-compiler/SKILL.md, allowlist; ids in .env | The agent answers a test call |
| E6 | S4 | goals.json G1 to G4 with real sources; demo email and calendar ready | Files validate |

### Block B, 11:00 to 14:00: the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E7 | S1 | Verify-on-grasp and read-on-hold-up endpoints | AT4 |
| E8 | S1 | State builder at 10 Hz: hands from ws, items from scan, events | Status flips when an item is picked and placed |
| E9 | S2 | Guidance: target ring, distance tone, words, "not that one" before a wrong grasp | A blindfolded teammate reaches 5 named items, each under 15 s |
| E10 | S1 | Check runner: subprocess, AST allowlist, 50 ms timeout, allowed() before zone entry, STOP events | AT3 |
| E11 | S3 | Compile job: goal, emails.json, scan.json and live rule pages into plan.json, checks/, tests/ | The G1 plan validates |
| E12 | S3 | Release hook: gate_release.py runs pytest, denies with the failing ids | AT5 first part |
| E13 | S2 | UI panels: PLAN, AGENT stream, COUNTERS, big type | A photo of the screen is readable at 2 m |

### Block C, 14:00 to T minus 3h: close the loop
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E14 | S3 and S1 | get_trip_emails and create_calendar_event tools; approval on screen | AT6 |
| E15 | S2 | Voice: the goal by voice (Live API or browser speech); approval by "yes" | A spoken goal starts a compile |
| E16 | S3 | Learner: lessons.md, regression cases, regression hook, 30 min trigger | One scheduled run logged; the hook denies a regressing change |
| E17 | S3 | Background compile of G-fresh during a live run | AT8 |
| E18 | All | First full G1 run end to end | WOW test attempt logged |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E19 | S4 | Trials: at least 6 raw and 6 Offscreen, alternating, blindfolded | AT7 |
| E20 | S2 | Stretch, only if AT1 to AT8 pass: raw panel on the same feed; blink to approve | Behind flags |
| E21 | All | Feature freeze at T minus 90 | Only fixes after this |
| E22 | S4 | Rehearse the 3:00 run 10 times | AT9 |
| E23 | S4 | Insurance recording at T minus 60 | demo/insurance.mp4 saved |
| E24 | S4 | README: what, how to run, numbers, a Managed Agents section, libraries | README done |
| E25 | S4 | Submit, video within the stated length | Submitted |

## If the team is small
Cut in this order: E20, E17, E16, E15 (type the goal instead), the Gmail half of E14 (use the exported .eml).
Never cut: E3, E4, E7 to E12, E19, E22, E23.
