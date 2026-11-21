# DEMO.md: Look to Listen, the pitch

Round 1: one of 6 rooms, about 15 teams back to back. Then the final, in front of everyone.
The pitch is built from live moments. No slides.

## Roles
- Saran: presents and holds the phone or points the laptop camera.
- Second talker: a teammate if there is one. Otherwise a judge who agrees, or any video a judge picks on their own phone.
- Operator (teammate, if any): plugs in the projector, then hands off. Takes over only for a fallback.

## Setup in the room (60 s)
1. HDMI in, mirror the display. Volume up.
2. Camera pointed at the talkers, app running, ENGINE label says B-GPU, both lanes, the counters and the DELAY meter visible.
3. caffeinate is running, Do Not Disturb is on.
4. First caption on the projector. Go.

## The room run (3:00), LIVE
| Time | What happens (live) | Saran says |
| --- | --- | --- |
| 0:00 | Camera on Saran. Both lanes caption him live. DELAY meter visible. | "430 million people need help to hear. The hardest place is a room where two people talk at once." |
| 0:10 | Ask for a second talker. | "Could you talk with me at the same time? Anything at all, just keep going." If nobody can: "Pick any video on your phone and play it." |
| 0:15 | Both talk. Left lane: both voices jumbled. Right lane: only the judge the laptop points at, live, about 2 s behind. Her clean voice plays on the speaker. Leakage counters move. | Keep talking for about 10 s, then stop and point at the screen: "Left is what a microphone hears. Right is only the person I'm looking at, live." |
| 0:35 | Point the laptop at yourself while you both talk again. The right lane and the voice switch to you within 2 s. | "Now I look at me." |
| 0:50 | Point at the face colors and the DELAY meter. | "Every face gets its own color. The Decisions API checks every half second whose lips are moving. The voice runs about a second behind." |
| 1:05 | Optional: hand over the headphones. | "Put these on. You'll hear only who the laptop looks at." Skip if they decline. |
| 1:15 | Robot moment (R1). | "Robots have the same problem. Both of us, give it a command at once." Saran: "Hand me the bottle." Judge: "Hand me the phone." The robot panel points at the object the target asked for and shows the other command blocked by the hook. |
| 1:40 | AGENT stream: tap Save transcript. The privacy hook denies the face without consent; the agent redacts and saves. | "The agent can't save anyone who didn't say yes. That's a hook, not a promise." |
| 1:55 | AGENT stream: the tuner's last release with before and after numbers. | "Every 30 minutes it retunes on new clips. A hook blocks any change that makes a number worse." |
| 2:10 | END CARD: Set C numbers, delay, where it breaks. | "On [n] clips from people here today: leakage [x]% for raw captions, [y]% for ours, [d] seconds behind. It starts to break at [condition]." |
| 2:45 | | Close (below). |

If the ENGINE label flips to Engine A mid-run, say it: "The GPU dropped, so Gemini alone is listening now." That is the failover working, live.

## Hook lines (pick by who is in the room)
- DeepMind or Google engineers: "Google Research separated one voice by pointing at a face in 2018, on recorded video. SpeechCompass needed a four-mic phone case. This is a phone camera and Gemini 4, in this room."
- Robotics people: "A robot hears everyone in the room. This tells it whose command to follow, and a hook enforces it."
- Real-time voice and video people (Agora): "Camera, mic, a face stream per person, the raw lane and the target lane, all at once."
- Investors and founders: "430 million people need help to hear, and unaddressed hearing loss costs almost a trillion dollars a year. Display glasses are coming. This is the app they need."
- Unknown room: the DeepMind line.

## Close (under 15 s)
"In a room full of voices, you hear only who you look at. Look to Listen."

## The final showdown
- Same run, bigger room. The hall's noise is the input.
- New moment: "Everyone, talk to your neighbor." Point the laptop at one judge while the hall talks. Their words appear alone, live, and their voice plays.
- Open with the investor line. Put the DeepMind line in the close.

## Rules for the run
- Never script what the second talker says.
- Ask before you caption anyone. Wait for yes.
- Never play a pre-recorded clip as the live demo. If a fallback recording plays, say its time.
- If a number is bad, show it and say what you changed. The brief asks for where it breaks.
- Never say a number that is not on screen.

## Q&A (one breath each)
- Isn't this just Live Caption? Live Caption writes everyone into one stream. The left lane is that. The right lane is only your target.
- What about Meta's Conversation Focus? It amplifies the person you face and has no captions. Meta says it's not for extremely loud places. We caption, split people talking over each other, and run on any phone.
- Is ClearVoice doing the work? ClearVoice, on a cloud GPU, pulls the voice out of the mix. Gemini does both live caption streams, the speaking decisions, names, pointing, memory and the agent. Engine A is Gemini alone, and both engines are on the END CARD.
- Is it real time? It is live: the voice runs about [n] s behind and the captions about [m] s. The meter on screen is measured, not estimated.
- What breaks it? Three talkers at once, profile faces, more than 3 m, the loudest noise. Numbers on the END CARD.
- Privacy? Consent first. The privacy hook blocks saving or sending anyone without it.
- Why a Managed Agent? It tunes the system on new clips in its sandbox, and three hooks keep it honest: no regressions, no saving without consent, no robot command from the wrong person.
- Is it a hearing aid? No. It's captions and an audio assist. We don't claim medical use.
- World models? No. We use Gemini's robotics skills for pointing, and we don't claim world models.

## Practice
- 10 full runs with different second talkers, 8 clean. 3 of them in a mock room with a timer and Q&A asked cold.

## Insurance
A 60 s recording of the best run at T minus 60, labeled with its time. Play it only if the live run cannot start.
