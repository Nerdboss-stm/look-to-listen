# DEMO.md: the 3:00 run

Everything below happens live. Nothing is planted.

## Roles
- Hands: a teammate, blindfolded, seated at the bottom edge of the frame. Speaks the goal. Says "yes" to approve.
- Presenter: Saran, beside the screen. Says only what the screen shows.
- Operator (optional): a third person at the laptop. Hands off unless a fallback is needed.

## Run of show
| Time | What happens (live) | Presenter |
| --- | --- | --- |
| 0:00 | Hands, blindfolded: "I fly to Vegas on Sunday. Get me ready." The AGENT stream starts. | Silent for 3 seconds. Let the stream run. |
| 0:03 | AGENT reads the flight email, fetches the TSA and FAA pages and the forecast, writes the checks, tests them on this camera's scan. | Opening (below). |
| 0:30 | The hook decision appears. If a check fails, its reason shows and the agent fixes it. The plan is released. PLAN fills. | "It can't release a plan until its own tests pass. The hook enforces that." |
| 1:00 | The tone guides the hand to each item. On grasp, Hydrogen names the item. Bottles: "hold it up", Hydrogen reads the size. A wrong item or bag: STOP before it lands, with the reason. Counters move. | Short lines that match the screen: "Six point seven ounces. Checked bag." |
| 2:15 | AGENT asks to add "Leave for the airport" to the calendar. Hands: "yes". The real calendar shows the event. | "The last step is back on a screen, after she says yes." |
| 2:30 | COUNTERS: steps verified, stops before landing. The trials bar: raw vs Offscreen, event-day counts. If G-fresh finished, one line about it. | "Same model, same camera, same email. Raw: [n] of [n]. Ours: [n] of [n]." |
| 2:50 | Close. | Close (below). |

## Opening (say it aloud 10 times; under 27 s)
"On Tuesday, Google gave hundreds of millions of people an agent that pays their bills. Meta, OpenAI and Anthropic have one too. Every one of them stops at the screen. This one just read her flight email, pulled the TSA rules, and is writing the checks it will hold her hands to. She can't see. Gemini can."

## Close (under 10 s)
"Every agent this fall stops at the screen. Ours finished the job on the table, and proved every step."

## Rules for the run
- No staged mistakes. If none happens, the counter shows zero. That is fine.
- If the compile passes 90 s, switch to the latest released plan (SPEC FB2) and say: "This plan compiled at [time]. Here it is running."
- Never say a number that is not on screen.

## What is live, and what is complex
- Live: the camera, the hands, every Hydrogen call, the agent writing and testing code, the hook decision, the real email, the real calendar, every counter.
- Complex, where judges can see it: four systems on one table at once. A 30 fps hand tracker, Hydrogen perception, a check runner, and a Managed Agent writing code in the background.
- Simple underneath: no model call in the 30 fps loop, checks are pure functions, every dependency has a fallback flag.

## Screen at 1:40 (what judges see)
- Left, big: the camera. Her right hand holds the lotion bottle over the blue carry-on zone. Red border. One line: "STOP: 6.7 fl oz. Checked bag, not carry-on."
- Right top: PLAN. 5 of 9 verified. Lotion: "read 6.7 fl oz, checked bag".
- Right middle: AGENT. The last line: "check_liquids: allowed(lotion, carry_on) = false".
- Right bottom: COUNTERS. Steps verified 5. Stops before landing 1. Hydrogen p50 1.6 s. Loop 30 fps. Trials raw vs ours.
(The numbers here are placeholders. On the day, only logged numbers show.)

## Reset between runs (60 s)
Items back on their taped spots. Bags empty. Delete the calendar event. New trial id.

## Q&A (one breath each)
- How is this different from Tasks in Gemini? Tasks finishes errands in apps. Offscreen finishes the physical part and proves each step. Same Hydrogen model; we use its embodied half.
- Astra's bike demo did this. That 2025 video found the manual and called a shop while the person did the work and checked it himself. Offscreen owns the plan, watches every step at 30 fps, stops mistakes before they land, and is measured against raw Gemini today.
- Why the blindfold? So every success belongs to the model. No human eyes in the loop.
- What does the Managed Agent do that a script can't? It reads rules it has never seen, writes the checks as code, tests them on this camera, and cannot release until its tests pass. Every 30 minutes it learns from new runs, and a second hook stops it from breaking old cases.
- How fast? The loop fps, Hydrogen p50 and compile time are on screen.
- What if Gemini is wrong? It asks to hold the item up and reads it. Checks stop rule breaks before they land. The trials show what still slips through.
- Does it generalize? A goal nobody rehearsed compiled during this run. Four goals share one kit.
- Can a robot use it? The plan and checks talk about items, zones and verification, not hands. Every run is logged with frames, tracks and checks.
- Privacy? A demo account. The screen shows parsed fields only.

## Insurance
A 60 s recording of a clean run at T minus 60, saved as demo/insurance.mp4.
