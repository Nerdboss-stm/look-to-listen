# PLAN.md

Every task takes under 30 minutes and ends in a check.

## Friday Nov 20 (today): learning and testing only, no submitted code
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| F1 | Ask in the CV Discord: demo length and format, submission deadline, video required, Managed Agents prize criteria | 10 min | Posted |
| F2 | Post the team-up message and DM Julian, if not done | 10 min | Posted |
| F3 | AI Studio: confirm the gemini-4-hydrogen, gemini-4-argon and gemini-3.8-live ids; check which models a Managed Agent accepts | 20 min | Ids written in SPEC.md |
| F4 | Gate test: 6 raw trials and 6 harness trials (prompts below); build each; log in gate_log.csv | 90 min | 12 rows logged |
| F5 | Save the prompts that worked in prompts.md | 15 min | File saved |
| F6 | Gather the kit, write the 5 goal cards, find a coin and a towel | 20 min | Bag packed |
| F7 | Say the opening line aloud 10 times, timed | 15 min | Under 30 s |
| F8 | Charge laptop, phone, earbuds, power bank. Pack charger, extension cord, something to prop the phone on | 15 min | Packed |
| F9 | Sleep by 11 PM | | |

### Gate test prompts (AI Studio)
Setup: lay 5 kit items on the towel, add a coin, take one top-down phone photo.

Raw (gemini-4-hydrogen):
"Using only the objects in this photo, design one build that achieves: [goal]. Pass test: [test]. Give numbered steps a person can follow, and your probability from 0 to 100 that it passes."

Harness step 1 (gemini-4-hydrogen):
"Using only the objects in this photo, propose 5 different builds that achieve: [goal]. Pass test: [test]. For each: numbered steps, the main failure risk, and your probability from 0 to 100 that it passes."

Harness step 2 (gemini-4-argon), with the photo and the 5 designs pasted:
"You are a strict physical engineer. Rank these 5 designs by how likely they are to pass [test] with these exact objects. Pick one and give a calibrated probability from 0 to 100."

Build raw's design and the harness pick. Log both in gate_log.csv.

### Gate decision
- Harness passes at least 2 more than raw, and at least 4 of 6: lead with "the harness beats raw".
- Otherwise: keep the build, drop the "beats raw" claim, lead with the live build and bet accuracy, and narrow to the goals that passed.
- No idea changes after the lock.

## Saturday Nov 21 at the event (T = submission deadline)
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | 9:00 setup: mat, camera on books, light, Wi-Fi test, read the rules, write T on paper | Camera feed live |
| E1 | S1 | contracts/ files from SPEC.md | Schemas validate a sample |
| E2 | S1 | FastAPI skeleton, .env, call logger | logs/calls.jsonl gets a row |
| E3 | S2 | Camera, MediaPipe hands, overlay | AT2 |
| E4 | S1 | Measure prompt: sizes from the photo using the coin | Sizes within 2 cm on 3 items |
| E5 | S1 | 5 designs in parallel, schema validation, retries | 5 valid designs |
| E6 | S1 | Argon critic, pick and bet; raw baseline call | AT1 |
| E7 | S1 and S2 | Live check loop at 1 to 3 per second | Steps advance on their own |
| E8 | S2 | Targets and arrows from the points | Arrow lands on the right object |
| E9 | S2 | Hover warning and spoken "stop" | AT3 |
| E10 | S2 | Live voice with ephemeral token; fallback speech | AT4 |
| E11 | S2 | PASS/FAIL tap, timer, trial record, scoreboard | AT5 |
| E12 | S3 | agents/learner/AGENTS.md and SKILL.md; register the agent; save ids in .env | Agent answers one test |
| E13 | S3 | Regression script and command hook | Hook denies a bad lesson |
| E14 | S3 | Lesson after each trial; agent panel streams events | AT6 |
| E15 | S3 | Hugging Face export with credential and consent hook | AT7 |
| E16 | S3 | Trigger every 30 min | One scheduled run logged |
| E17 | S4 | 8 raw and 8 harness trials, event-day data | Scoreboard shows 16 trials |
| E18 | S4 | README: what, how to run, numbers, a Managed Agents section | README done |
| E19 | All | Feature freeze at T minus 90 | Only fixes after this |
| E20 | S4 | Rehearse the full demo 10 times | 8 of 10 clean |
| E21 | S4 | Insurance recording at T minus 60 | Video saved |
| E22 | All | Submit; push repo and dataset public | Confirmation |

If solo: cut E16, simplify the agent panel, export only at the end. Never cut the bet, the physics test or the scoreboard.
