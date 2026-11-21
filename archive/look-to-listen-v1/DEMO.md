# DEMO.md: Look to Listen, the pitch

Round 1: one of 6 rooms, about 15 teams back to back. Then the final, in front of everyone.
The pitch is built from live moments. No slides.

## Roles
- Saran: presents and holds the phone.
- Second talker: a teammate if there is one. Otherwise a judge who agrees, or any video a judge picks on their own phone.
- Operator (teammate, if any): plugs in the projector, then hands off. Takes over only for a fallback.

## Setup in the room (60 s)
1. HDMI in, mirror the display.
2. Phone on its stand or in hand, app running, both lanes and the counters visible.
3. Headphones on the table, unplugged from your ears.
4. First caption on the projector. Go.

## The room run (3:00)
| Time | What happens (live) | Saran says |
| --- | --- | --- |
| 0:00 | Camera on Saran. Both lanes caption him. | "430 million people need help to hear. The hardest place is a room where two people talk at once." |
| 0:10 | Ask for a second talker. | "Could you talk with me at the same time for ten seconds? Anything at all." If nobody can: "Pick any video on your phone and play it." |
| 0:15 | Both talk. Left lane: both voices jumbled. Right lane: only the person the camera points at. Leakage counters move. | Keep talking. Then stop and point at the screen: "Left is what a microphone hears. Right is only the person I'm looking at." |
| 0:35 | Swing the camera to the other person. The right lane switches. | "Now I look at you." |
| 0:45 | Offer the headphones. | "Put these on. You'll hear only who the camera looks at." Optional. Skip if they decline. |
| 1:00 | Point at the face colors. | "Every face gets its own color. The Decisions API checks every half second whose lips are moving." |
| 1:15 | MEMORY box. | "What did she say about [something said a minute ago]?" Argon answers with the time and the clip. |
| 1:35 | AGENT stream: tap Save transcript. The privacy hook denies it for the face without consent, then the agent redacts and saves. | "The Managed Agent can't save anyone who didn't say yes. That's a hook, not a promise." |
| 1:50 | AGENT stream: the tuner's last release with before and after numbers. | "Every 30 minutes it retunes on new clips. A second hook blocks any change that makes a number worse." |
| 2:10 | END CARD: Set C numbers, where it breaks. | "On [n] clips from people here today: leakage [x]% for raw captions, [y]% for ours. It starts to break at [condition]." |
| 2:40 | | Close (below). |

## Hook lines (pick by who is in the room)
- DeepMind or Google engineers: "Google Research did this offline in 2018 with Looking to Listen. SpeechCompass needed a four-mic phone case. This runs live on a phone camera, on Gemini 4."
- Real-time voice and video people (Agora): "Five streams at once: camera, mic, a mouth stream per face, the raw lane and the target lane. Captions in about a second."
- Investors and founders: "430 million people need help to hear, and unaddressed hearing loss costs almost a trillion dollars a year. Display glasses are coming. This is the app they need."
- Unknown room: the DeepMind line.

## Close (under 15 s)
"In a room full of voices, you hear only who you look at. Look to Listen."

## The final showdown
- Same run, bigger room. The hall's noise is the input.
- New moment: "Everyone, talk to your neighbor for ten seconds." Point the camera at one judge. Their words appear alone.
- Open with the investor line. Put the DeepMind line in the close.

## Rules for the run
- Never script what the second talker says.
- Ask before you caption anyone. Wait for yes.
- Never play a recording as the live demo. If a fallback recording plays, say its time.
- If a number is bad, show it and say what you changed. The brief asks for where it breaks.
- Never say a number that is not on screen.

## Q&A (one breath each)
- Isn't this just Live Caption? Live Caption writes everyone into one stream. The left lane is that. The right lane is only your target.
- What about Meta's Conversation Focus? It amplifies the person you face and has no captions. Meta says it's not for extremely loud places. We caption, split overlapping talkers, and run on any phone.
- Is RAVEN doing the work? RAVEN cleans the audio for the headphones. Gemini does the captions, the speaking decisions, names, memory and the agent. With RAVEN off, the right lane still works: that's our B1 arm on the END CARD.
- How fast? Captions about 1 s after speech. Decisions about 0.2 s. On the END CARD as p50 and p95.
- What breaks it? Three talkers at once, profile faces, more than 3 m, and the loudest noise. Numbers on the END CARD.
- Privacy? Consent first. The privacy hook blocks saving or sending anyone without it.
- Why a Managed Agent? It tunes the system on new clips in its sandbox, and two hooks keep it honest: no regressions, no saving without consent.
- Is it a hearing aid? No. It's captions and an audio assist. We don't claim medical use.
- Languages? Neon can translate the target lane. Off by default.

## Practice
- 10 full runs with different second talkers, 8 clean (AT14). 3 of them in a mock room with a timer and Q&A asked cold.

## Insurance
A 60 s recording of the best run at T minus 60, labeled with its time. Play it only if the live run cannot start.
