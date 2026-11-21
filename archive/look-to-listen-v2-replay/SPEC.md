# SPEC.md: Look to Listen

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM.
Track: Element 119. Judging: round 1 in one of 6 rooms, then a final in front of everyone.
Chosen Nov 21, 2 AM, from 12 ideas scored on 56 criteria (sheet: "Gemini 4 NYC: every idea scored").
Revised Nov 21, 3:30 AM: RAVEN replaced by ClearVoice (RAVEN publishes no trained weights), replay mode made the default, robot layer added.
Older versions are in archive/. Do not use them.

## One line
Hear only who you look at.

## What it is
In any noisy room, point a phone or laptop camera at a person.
- Look to Listen shows captions of only that person's words.
- It plays only their voice, pulled out of the mix.
- It labels everyone else's lines by face, in their own color.
- It remembers the conversation and answers "what did she say about X?" with the moment.
- Robot layer: when two people give a robot different commands at once, it acts only for the person it is looking at.

Friend version: "Two people talked at once. They pointed a phone at one of them, and it played back only her voice and her words."

## The problem (numbers we can say out loud)
- WHO, Mar 2026: 430 million people need rehabilitation for disabling hearing loss. Unaddressed hearing loss costs almost US$1 trillion a year.
- Action on Hearing Loss survey (2017): 96% of people with hearing loss struggle in noisy places. Only 12% of hearing aid users are satisfied with the technology that helps them there.
- Google Research's SpeechCompass survey (n=263, CHI 2025 Best Paper): captions fail in group conversations because they can't tell speakers apart.
- Today's captions (Live Transcribe, Live Caption) write everyone into one stream. Meta's Conversation Focus amplifies the person you face, but Meta says it is not for extremely loud places, and it gives no captions.
- Robots: a robot in a home or a factory hears everyone. It has to know whose command to follow.

## Why DeepMind and Google people will care
- Google Research's Looking to Listen (SIGGRAPH 2018) isolated one voice by pointing at a face, on recorded video.
- SpeechCompass needed a 4-microphone phone case to separate speakers.
- Google demoed real-world subtitles on Android XR glasses, and display glasses are on its roadmap.
- Hydrogen carries Gemini Robotics ER skills. The robot layer uses them for the "whose command?" problem.
- Gemini does the parts only a frontier model can: captions in noise, a calibrated speaking decision for every face, names and context, pointing for the robot, memory, and an agent that improves the system behind gates.

## What we measured tonight (Nov 21, 3 AM)
- RAVEN (Bose) publishes training code only. It needs training on VoxCeleb2. No trained weights. Dropped.
- ClearVoice (Alibaba, Apache-2.0, `pip install clearvoice`) has a pretrained audio-visual target speaker model, AV_MossFormer2_TSE_16K (734 MB). It worked on its own two-speaker demo video and wrote one clean voice per face.
- It has a CUDA-only line that crashes on a Mac. setup_mac.sh patches it.
- Speed on a 2-core cloud machine: 14.7 to 16.4 s to process a 3 s window (about 5 times slower than real time). The full pipeline with its own face detector took 188 s for an 8 s video. A MacBook Air is faster; setup_mac.sh prints the real number (gate G1).
- So the default demo is REPLAY: record the 10 s moment, then separate it. LIVE rolling windows are a stretch if G1 allows.

## Element 119 compliance
| The brief asks | Look to Listen |
| --- | --- |
| Messier audio | Overlapping talkers and venue noise are the input |
| More streams at once | Camera, microphone, a face stream per person, the raw lane and the target lane side by side |
| Faster real-time loops | Face tracking at 30 fps, a speaking decision per face every 0.5 s, raw captions live |
| Longer footage | The whole conversation is kept for memory questions and the summary |
| The Decisions API | "Is this person speaking?" for every visible face, every 0.5 s |
| Show where it breaks | Leakage and WER by noise level, number of talkers, angle, distance and occlusion, on the END CARD |
| No scripted demos | Whoever is in the room talks, about anything |
| No team-written eval | Set C clips come from people at the venue, with consent |

## Models and their jobs
| Job | Model | What it does |
| --- | --- | --- |
| Ears | gemini-4-hydrogen-live (confirm id in AI Studio), else gemini-4-hydrogen in 1 s chunks | Live raw-lane captions; target-lane captions |
| Target listener (Engine A) | gemini-4-hydrogen | Given the AV clip with a box on the target face, transcribes only that person |
| Reflexes | gemini-decision-1 (Decisions API) | Calibrated "is this face speaking?" per face per 0.5 s |
| Robot eyes | gemini-4-hydrogen (Robotics ER skills) | Points at the object the target person asked for |
| Brain | gemini-4-neon | Merges segments, attributes lines to faces, names from vocab.json, optional translation |
| Memory | gemini-4-argon | Answers questions about the whole conversation with a time and clip; writes the summary |
| Tuner and guard | Gemini Managed Agent | Tunes the pipeline behind a regression hook; privacy and command hooks |

On stage, one line: "Hydrogen listens and points, the Decisions API watches every mouth, Neon keeps names right, Argon remembers, and a Managed Agent improves it behind gates."

Open-source building blocks, declared in the README: MediaPipe Face Landmarker, ClearVoice AV_MossFormer2_TSE_16K (Engine B), MuJoCo and MuJoCo Menagerie (robot stretch only).

## Two engines, picked by measurement
- Engine A, Gemini only: the mixed audio plus the video chunk with a box on the target face goes to Hydrogen with "transcribe only the person in the box". The Decision 1 speaking guard drops words while the target's mouth is still.
- Engine B, ClearVoice then Gemini: ClearVoice pulls the target's voice out of the mix using their face crops. Hydrogen transcribes the clean voice. The clean voice is also played to the room.
- 10:00 decision: run both on the same 5 two-talker clips. Keep the engine with lower leakage. If Engine B wins but G1 says it is slow, use it in REPLAY mode only.
- ClearVoice face input, copied from its own code: smoothed face box, half-size s, crop rows y-s to y+s(1+2c) and columns x-s(1+c) to x+s(1+c) with c=0.4 (pad the frame first), resize to 224x224, gray, center crop 112x112, then (x/255 - 0.4161)/0.1688, 25 fps, audio 16 kHz.

## Modes
- REPLAY (default): two people talk for about 10 s. The raw lane captions live. Then the system separates that clip for the face the camera points at: target captions appear and the clean voice plays. Tap the other face to hear the other person.
- LIVE (stretch): rolling 3 s windows while people talk. Only if G1 shows a 3 s window in 2.4 s or less.

## Robot layer
- R1 (build after the core, 45 minutes): two people give different commands at once ("hand me the bottle", "hand me the phone"). The target lane's command plus a camera frame goes to Hydrogen, which points at the object that person asked for. The screen draws the robot's reach point and shows the other command as ignored. A Managed Agent command hook denies any robot action whose command came from a face that is not the target.
- R2 (stretch, only with a teammate and after everything else): a MuJoCo Menagerie Franka Panda in a simulated table scene reaches for the block the target asked for.
- World models: not claimed. The event lists them as examples; the tracks are what is judged.

## Organic rules (these beat every other section)
- We never choose what anyone says.
- We never use a pre-recorded clip as the live demo. Any recording on screen shows its time.
- Interference is real: a second person talking, or any video a judge picks on their own phone.
- No paper, no tape, no kit, no food.
- Consent first: we caption a person only after they say yes. Nobody else's speech is saved. The privacy hook enforces this.
- Zero leakage is not required. Show the real number.

## Opening shot (one sentence)
Two people talk at once; the left lane on the big screen is a jumble of both, and a moment later the right lane shows only the person the phone points at while her voice plays alone.

## Idea gate (Sep 13 system)
- Person: someone with hearing loss at a loud dinner or work event. WHO: 430 million; almost US$1 trillion a year.
- Sponsor products said out loud: Gemini 4 Hydrogen, Neon, Argon, the Decisions API, Managed Agents.
- Mechanism in one picture: Architecture below.
- Number that moves on screen: leakage (share of caption words that came from someone else), raw lane against target lane.
- Opening shot: above.

## Claims (all live)
- C1 Target captions: with two people talking at once, the target lane shows the target's words, and leakage is lower than the raw lane.
- C2 Switch: tapping or pointing at the other face gives that person's words and voice.
- C3 Hear: the clean target voice plays to the room (Engine B).
- C4 Who said what: every visible face gets its own color and lines, from Decision 1 speaking decisions.
- C5 Memory: "what did she say about X?" is answered with a time and the clip in 8 s or less.
- C6 Robot: with two conflicting commands, the robot points at the object the target asked for; the command hook blocks the other.
- C7 Tuner: the Managed Agent proposes a better config from new clips; the regression hook releases it only if no metric gets worse.
- C8 Privacy: saving or sending a line from a face without consent is denied by the privacy hook, with the reason on screen.
- C9 Where it breaks: numbers by noise, talkers, angle, distance and occlusion.

## Do not claim
- Medical device, hearing aid replacement, "first ever".
- "Real time" for Engine B unless G1 shows it.
- "Better than Meta" or any product we did not test.
- "Beats the baseline" unless the gate rules in Evaluation pass.
- World models.
- Anything not on screen.

## Hardware
- Laptop, phone, headphones, HDMI adapter, a small phone stand, phone hotspot, charger, extension cord.
- Camera: the laptop camera, or the phone as the laptop's webcam. Microphone: the same device.
- Nothing on the table, the floor or the walls.

## Architecture
```
Browser (laptop, 30 fps, no model calls)
  getUserMedia video + audio; ring buffer of the last 20 s
  MediaPipe Face Landmarker -> faces {id, box, lips, mouth-open ratio}
  target = face nearest the center, or the one tapped
  overlay: face boxes in speaker colors, target ring, two caption lanes, counters, wall clock
Backend (FastAPI, ~/.venvs/g4-backend)
  raw lane: mixed audio -> Hydrogen (Live or 1 s chunks) -> raw segments, live
  speaking: every 0.5 s per face, a 1 s face crop + audio clip -> Decision 1 -> speaking timeline
  Engine A: clip + target box -> Hydrogen "only the person in the box" -> target segments
  leakage guard: drop target-lane words in windows where the target is not speaking
  Neon: merge, attribute, vocab.json, translation (flag)
  Argon: conversation store -> memory answers and summary
  robot R1: target command + frame -> Hydrogen pointing -> reach point; robot_act tool
  logs/calls.jsonl, logs/agent.jsonl, clips/, CSVs
Audio worker (~/.venvs/g4-audio, separate process)
  Engine B: ClearVoice AV_MossFormer2_TSE_16K on the clip + target face crops -> clean voice
  -> backend for captions, and -> speaker for playback
Managed Agent (Google sandbox, never inside the live loop)
  tools: get_new_clips, run_eval(config), propose_config, release_config, save_transcript, send_summary, robot_act
  hooks: gate_release (regression), gate_privacy (consent), gate_command (target-only robot commands), post-tool log
  trigger: every 30 minutes, tune on new labeled clips
```

## Managed Agent design
- Environment: one persistent environment named listener. Files persist: clips index, labels, configs, eval history.
- Model: gemini-4-neon if the agent accepts it (G5). If not, the default model runs and calls Neon through the Gemini API, with the key injected by the egress proxy.
- Skill: skills/listener/SKILL.md: the config contract, how to run the eval, the release rule, the consent rule, the command rule.
- AGENTS.md: never release without the regression suite; never save or send a line without consent; never act for a face that is not the target; report numbers, not adjectives.
- Tools (client-side, executed by the backend): get_new_clips(since), run_eval(config_id), propose_config(diff), release_config(config_id), save_transcript(conversation_id), send_summary(conversation_id), robot_act(command_id).
- Hooks (.agents/hooks.json):
  - pre_tool_execution on release_config: hooks/gate_release.py runs the regression suite on Set C. Deny if leakage, WER or p50 latency gets worse. The reason lists each metric, before and after.
  - pre_tool_execution on save_transcript and send_summary: hooks/gate_privacy.py denies if any line belongs to a face without consent. The agent redacts and retries.
  - pre_tool_execution on robot_act: hooks/gate_command.py denies if the command's face is not the current target. The reason names the face.
  - post_tool_execution on all tools: append to the agent log.
- Trigger: every 30 minutes the tuner reads new labeled clips, tries config changes (engine, window length, decision threshold, guard window, vocabulary), and proposes the best one.
- Fallback: if client-side tools are not supported, the backend calls the same functions on the agent's request through files in the sandbox (RELEASED file pattern), with command hooks on file writes.

## Contracts (E5 creates these first)
- contracts/face.schema.json: id, box, lips, mouth_open, color, consent {given, by, time}.
- contracts/segment.schema.json: t0, t1, lane (target | raw | other), face_id, text, confidence, engine (A | B).
- contracts/decision.schema.json: face_id, window_t0, window_t1, p_speaking, latency_ms.
- contracts/config.schema.json: config_id, engine, mode, window_s, decision_threshold, guard_ms, vocab, translate_to.
- contracts/command.schema.json: command_id, face_id, text, target_face_id, point [y, x], object_label.
- contracts/memory_answer.schema.json: question, answer, time, clip, confidence.
- contracts/eval.md: how WER, leakage, attribution and latency are computed (fixed now, before any data).

## Evaluation
Metric definitions are fixed now, before any data.
- Set C, clips: at least 40 two-talker clips and 10 three-talker clips of 10 to 20 s, recorded at the venue with consent. Vary distance (1, 2, 3 m), angle (front, 45 degrees, profile), noise (quiet room, hall), occlusion (hand or cup near the mouth). Truth: each talker holds a phone near their own mouth as a close-talk reference; S4 types the truth from those recordings.
- Arms: B0 raw captions of the mixed audio (same captioner, no targeting). A: Engine A. B: Engine B.
- Metrics: target WER; leakage = share of target-lane words that belong to another talker; attribution accuracy of lines to faces; time from end of speech to target caption.
- Set D, decisions: every 0.5 s window of Set C labeled speaking or not per face. Score: accuracy at 0.9, calibration chart.
- Set R, robot: at least 10 conflicting-command pairs from different people. Score: the reach point lands on the object the target asked for.
- Where it breaks: leakage and WER by noise level (measured dB), 2 against 3 talkers, angle, distance, occlusion.
- Gate: say "beats raw captions" only if leakage drops by at least 20 points with WER no more than 5 points worse, on at least 30 clips. Report counts.

## UI (readable from the back of a room)
- Top 60 percent: the live camera with face boxes, speaker colors, target ring, wall clock.
- Bottom: two caption lanes. Left "What the microphone hears" (raw, B0). Right "Look to Listen" (target). Other speakers' lines in their colors.
- Side strip: LEAKAGE counters, ENGINE and MODE labels, AGENT stream (tool calls and hook decisions), MEMORY box, ROBOT panel (whose command, reach point).
- END CARD: "Look to Listen. Hear only who you look at." Set C, D and R numbers, where it breaks, repo link and QR.
- Caption text at least 32 px, counters at least 40 px, high contrast.

## Acceptance tests
- AT1 Faces: 3 faces tracked at 25 fps or more; target ring follows the center face.
- AT2 Engine B: ClearVoice runs on a 10 s two-talker clip recorded on this laptop; the other voice is clearly lower in 4 of 5 tries; time logged.
- AT3 Captions: one talker in a quiet room, WER at or under 10% on 5 sentences, raw lane p50 latency at or under 1.5 s.
- AT4 Target lane: 10 two-talker clips with the chosen engine, leakage at or under 15% on average, WER at or under 25%.
- AT5 Switch: tapping the other face gives that person's lane, 9 of 10.
- AT6 Decisions: p50 at or under 300 ms; at least 18 of 20 labeled windows right at 0.9.
- AT7 Who said what: lines attributed to the right face in at least 85% of lines on 5 three-talker clips.
- AT8 Memory: 5 questions on a 10 minute conversation, at least 4 right with a time within 15 s, each in 8 s or less.
- AT9 Tuner: one scheduled run proposes a config; the release hook allows a better one and denies a worse one, 2 of 2.
- AT10 Privacy: save_transcript with a non-consenting face is denied with the reason; after redaction it passes, 3 of 3.
- AT11 Robot R1: 10 conflicting-command pairs, the reach point is on the target's object in at least 8; the command hook denies the other command 10 of 10.
- AT12 Replay timing: from "now only you" to target captions on screen in 15 s or less, 5 of 5.
- AT13 Evaluation: Sets C, D and R filled as defined; END CARD renders from the files.
- AT14 Room: setup in 60 s or less, 3 of 3. 10 full rehearsals with different second talkers, 8 clean.

## WOW test (checkable)
In the judging room, live, under 3:00: two people talk at once. The left lane shows both. Within 15 s the right lane shows the target's words with lower leakage, and her voice plays alone. Tapping the other face gives his. Two conflicting commands make the robot point at the target's object, and the command hook blocks the other. A save of a non-consenting person's lines is denied on screen. The END CARD shows the Set C numbers.
Evidence: clips.csv and robot.csv rows, and the recording if the room allows it.

## Out of scope
Hearing aid hardware, glasses, an app store build, accounts, sign language, more than 4 faces at once, a physical robot, world models.

## Fallbacks (each behind a flag)
- FB1 Engine B too slow or broken: Engine A only; no voice playback; captions still shown.
- FB2 Engine A leakage too high: Engine B in REPLAY mode.
- FB3 Both engines weak: show "who said what" with speaker colors from Decision 1, and say where it breaks.
- FB4 Hydrogen Live not available: 1 s chunks to gemini-4-hydrogen at low thinking.
- FB5 Decisions API down: mouth-open ratio from MediaPipe decides speaking, marked "uncalibrated".
- FB6 Argon slow: Neon answers memory questions from the transcript, marked "transcript only".
- FB7 No client-side tools in the agent: file pattern (see Managed Agent design).
- FB8 Robot pointing misses: show the command attribution and the hook decision without the point.
- FB9 Room too quiet for a second talker: the judge picks any video on their phone as the interference.
- FB10 No projector: the laptop turns to the judges. Venue Wi-Fi: phone hotspot.
- FB11 Everything else: the 60 s recording of the best run, labeled with its time.

## Rules
- All project code is written on event day. Open-source libraries and models are declared in the README. Third-party models are downloaded at home before the event; no project code is written before it.
- Consent before captioning a person. No audio of anyone without consent is kept. Faces of non-consenting people are blurred in any recording.

## Go deeper (Oct 15 rule)
1. What a top professional would do: measure the engines against each other on the same clips before choosing; record close-talk truth for every talker; measure the raw baseline on the same audio; show leakage, not just WER; measure where it breaks; keep the agent out of the live loop.
2. Rawest material: the raw mixed audio, per-talker close-talk recordings, the face crops, raw model JSON and Decision 1 probabilities.
3. Methods and tools: MediaPipe Face Landmarker; ClearVoice; Gemini Live API (16 kHz PCM in); the Decisions API; Hydrogen pointing; Neon and Argon; jiwer; Managed Agents tools, hooks and triggers; pytest.
4. Proof that is not us: judges' own voices, the close-talk truth, the raw lane on the same audio, the hook decisions in the agent log.

## After the event
- Release the code, Set C (consenting people only, with their written OK) and the eval scripts.
- Paper: audio-visual target-speaker captioning with frontier multimodal models in a real venue, comparing a Gemini-only engine with a separation-first engine, by leakage and WER against audio-only captioning, with calibrated per-face speaking decisions.
- Post the pitch clip and the numbers on X, tagging Google DeepMind and Google AI Studio. Send the repo to the judges you met.

## Open questions (answer at the event start)
- Slot length, Q&A length, projector input, which judges sit in which room, how many advance, Managed Agents prize criteria.
- Exact Live model id for Gemini 4 Hydrogen, and whether it returns input transcription.
- G1 numbers on this laptop (setup.log line "G1 ...").
- Decisions API: video and audio input format, latency on venue Wi-Fi.
- Managed Agent: accepts gemini-4-neon? Client-side tools? Tool names for hook matchers?
