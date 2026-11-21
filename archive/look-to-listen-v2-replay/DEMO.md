# DEMO.md: Look to Listen, the pitch

Round 1: one of 6 rooms, about 15 teams back to back. Then the final, in front of everyone.
The pitch is built from live moments. No slides.

## Roles
- Saran: presents and holds the phone or points the laptop camera.
- Second talker: a teammate if there is one. Otherwise a judge who agrees, or any video a judge picks on their own phone.
- Operator (teammate, if any): plugs in the projector, then hands off. Takes over only for a fallback.

## Setup in the room (60 s)
1. HDMI in, mirror the display. Volume up.
2. Camera pointed at the talkers, app running, both lanes and the counters visible.
3. caffeinate is running, Do Not Disturb is on.
4. First caption on the projector. Go.

## The room run (3:00), REPLAY mode
| Time | What happens (live) | Saran says |
| --- | --- | --- |
| 0:00 | Camera on Saran. Both lanes caption him. | "430 million people need help to hear. The hardest place is a room where two people talk at once." |
| 0:10 | Ask for a second talker. | "Could you talk with me at the same time for ten seconds? Anything at all." If nobody can: "Pick any video on your phone and play it." |
| 0:15 | Both talk for about 10 s. The left lane fills with both voices jumbled. | Keep talking. |
| 0:28 | Tap the judge's face. The engine runs on those 10 s. | "Left is what a microphone hears. Now only you." While it runs: "It found your face, watched your lips, and is pulling your voice out of the mix." |
| 0:40 | Right lane shows only the judge's words. Her voice plays alone (Engine B). Leakage counters update. | Stop talking. Let the room hear it. |
| 0:55 | Tap Saran's face. His words and voice. | "And now only me." |
| 1:10 | Point at the face colors. | "Every face gets its own color. The Decisions API checks every half second whose lips are moving." |
| 1:20 | Robot moment (R1). | "Robots have the same problem. Both of us, give it a command at once." Saran: "Hand me the bottle." Judge: "Hand me the phone." The robot panel points at the object the target asked for and shows the other command as blocked by the hook. |
| 1:45 | AGENT stream: tap Save transcript. The privacy hook denies the face without consent; the agent redacts and saves. | "The agent can't save anyone who didn't say yes. That's a hook, not a promise." |
| 2:00 | AGENT stream: the tuner's last release with before and after numbers. | "Every 30 minutes it retunes on new clips. A hook blocks any change that makes a number worse." |
| 2:15 | END CARD: Set C numbers, where it breaks. | "On [n] clips from people here today: leakage [x]% for raw captions, [y]% for ours. It starts to break at [condition]." |
| 2:45 | | Close (below). |

If the processing takes longer than 15 s: keep talking about the mechanism, never stand silent. If it fails: say so, tap the other engine, and move on.

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
- New moment: "Everyone, talk to your neighbor for ten seconds." Point the camera at one judge. Then play back only their voice.
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
- Is ClearVoice doing the work? ClearVoice pulls the voice out for playback. Gemini does the captions, the speaking decisions, names, pointing, memory and the agent. Engine A is Gemini alone, and both engines are on the END CARD.
- Is it real time? The room run is replay: it separates the last ten seconds. [Say the G1 number.] Live mode is on when the laptop is fast enough.
- What breaks it? Three talkers at once, profile faces, more than 3 m, the loudest noise. Numbers on the END CARD.
- Privacy? Consent first. The privacy hook blocks saving or sending anyone without it.
- Why a Managed Agent? It tunes the system on new clips in its sandbox, and three hooks keep it honest: no regressions, no saving without consent, no robot command from the wrong person.
- Is it a hearing aid? No. It's captions and an audio assist. We don't claim medical use.
- World models? No. We use Gemini's robotics skills for pointing, and we don't claim world models.

## Practice
- 10 full runs with different second talkers, 8 clean. 3 of them in a mock room with a timer and Q&A asked cold.

## Insurance
A 60 s recording of the best run at T minus 60, labeled with its time. Play it only if the live run cannot start.
