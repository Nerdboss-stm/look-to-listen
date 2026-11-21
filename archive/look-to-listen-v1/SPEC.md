# SPEC.md: Look to Listen

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM.
Track: Element 119. Judging: round 1 in one of 6 rooms, then a final in front of everyone.
Chosen Nov 21, 2 AM, from 12 ideas scored on 56 criteria (sheet: "Gemini 4 NYC: every idea scored").
Older versions are in archive/. Do not use them.

## One line
Hear only who you look at.

## What it is
In any noisy room, point a phone or laptop camera at a person.
- Look to Listen shows live captions of only that person's words.
- It plays only their voice in your headphones.
- It labels everyone else's lines by face, in their own color.
- It remembers the conversation and answers "what did she say about X?" with the moment.
- Swing the camera to someone else, and it switches within about a second.

Friend version: "Everyone in the room was talking. They pointed a phone at one person, and the captions showed only her words."

## The problem (numbers we can say out loud)
- WHO, Mar 2026: 430 million people need rehabilitation for disabling hearing loss. Unaddressed hearing loss costs almost US$1 trillion a year.
- Action on Hearing Loss survey (2017): 96% of people with hearing loss struggle in noisy places. Only 12% of hearing aid users are satisfied with the technology that helps them there.
- Google Research's SpeechCompass survey (n=263, CHI 2025 Best Paper): captions fail in group conversations because they can't tell speakers apart.
- Today's captions (Live Transcribe, Live Caption) write everyone into one stream. Meta's Conversation Focus amplifies the person you face, but Meta says it is not for extremely loud places, and it gives no captions.

## Why DeepMind and Google people will care
- Google Research's Looking to Listen (SIGGRAPH 2018) isolated one voice by pointing at a face. It ran offline on recorded video.
- SpeechCompass needed a 4-microphone phone case to separate speakers.
- Google demoed real-world subtitles on Android XR glasses, and display glasses are on its roadmap.
- Look to Listen runs live, from an ordinary camera, on Gemini 4. Gemini does the parts only a frontier model can: captions in noise, a calibrated speaking decision for every face, names and context, memory, and an agent that improves the system behind a gate.

## Element 119 compliance
| The brief asks | Look to Listen |
| --- | --- |
| Messier audio | Overlapping talkers and venue noise are the input |
| More streams at once | Camera, microphone, a mouth stream per face, the raw lane and the target lane side by side |
| Faster real-time loops | Face tracking at 30 fps, a speaking decision per face every 0.5 s, captions in about 1 s |
| Longer footage | The whole conversation is kept for memory questions and the summary |
| The Decisions API | "Is this person speaking?" for every visible face, every 0.5 s |
| Show where it breaks | Leakage and WER by noise level, number of talkers, angle, distance and occlusion, on the END CARD |
| No scripted demos | Whoever is in the room talks, about anything |
| No team-written eval | Set C clips come from people at the venue, with consent |

## Models and their jobs
| Job | Model | What it does |
| --- | --- | --- |
| Ears | gemini-4-hydrogen-live (confirm id in AI Studio), else gemini-4-hydrogen in 1 s chunks | Live captions of the target stream and of the raw lane |
| Reflexes | gemini-decision-1 (Decisions API) | Calibrated "is this face speaking?" per face per 0.5 s, about 0.2 s |
| Brain | gemini-4-neon | Merges caption segments, attributes lines to faces, fixes names from the learned vocabulary, optional translation |
| Memory | gemini-4-argon | Answers questions about the whole conversation with a time and clip; writes the summary |
| Tuner and guard | Gemini Managed Agent | Tunes the pipeline on new labeled clips behind a regression hook; a privacy hook blocks saving or sending anyone who has not consented |

On stage, one line: "Hydrogen listens, the Decisions API watches every mouth, Neon keeps names right, Argon remembers, and a Managed Agent improves it behind two gates."

Open-source building blocks, declared in the README: MediaPipe Face Landmarker (faces and lips) and RAVEN (Bose, Interspeech 2025), a real-time audio-visual target speech model that runs on a laptop CPU from a webcam.

## Organic rules (these beat every other section)
- We never choose what anyone says.
- We never use a recording as the live demo. Any recording on screen shows its time.
- Interference is real: a second person talking, or any video a judge picks on their own phone.
- No paper, no tape, no kit, no food.
- Consent first: we caption a person only after they say yes. Nobody else's speech is saved. The privacy hook enforces this.
- Zero leakage is not required. Show the real number.

## Opening shot (one sentence)
Two people talk at once; the left lane on the big screen is a jumble of both, and the right lane shows only the person the phone points at.

## Idea gate (Sep 13 system)
- Person: someone with hearing loss at a loud dinner or work event. WHO: 430 million; almost US$1 trillion a year.
- Sponsor products said out loud: Gemini 4 Hydrogen, Neon, Argon, the Decisions API, Managed Agents.
- Mechanism in one picture: Architecture below.
- Number that moves on screen: leakage (share of caption words that came from someone else), raw lane against target lane.
- Opening shot: above.

## Claims (all live)
- C1 Target captions: with two people talking at once, the target lane shows the target's words, and leakage is lower than the raw lane.
- C2 Switch: pointing at another face switches the target lane in 1.5 s or less.
- C3 Hear: the headphones play the target voice with the other voice clearly lower (RAVEN layer).
- C4 Who said what: every visible face gets its own color and lane, from Decision 1 speaking decisions.
- C5 Memory: "what did she say about X?" is answered with a time and the clip in 8 s or less.
- C6 Tuner: the Managed Agent proposes a better config from new clips; the regression hook releases it only if no metric gets worse.
- C7 Privacy: saving or sending a line from a face without consent is denied by the privacy hook, with the reason on screen.
- C8 Where it breaks: numbers by noise, talkers, angle, distance and occlusion.

## Do not claim
- Medical device, hearing aid replacement, "first ever".
- "Better than Meta" or any product we did not test.
- "Beats the baseline" unless the gate rules in Evaluation pass.
- Anything not on screen.

## Hardware
- Laptop, phone, over-ear headphones (plus a spare wired pair), HDMI adapter, a small phone stand, phone hotspot.
- Camera: the laptop camera, or the phone as the laptop's webcam. Microphone: the same device.
- Nothing on the table, the floor or the walls.

## Architecture
```
Browser (laptop, 30 fps, no model calls)
  getUserMedia video + audio
  MediaPipe Face Landmarker -> faces {id, box, lip landmarks, mouth-open ratio}
  target = face nearest the center, or the one tapped
  overlay: face boxes in speaker colors, target ring, two caption lanes, counters, wall clock
Audio worker (Python, local)
  RAVEN: target mouth crops + mixed audio -> clean target audio (flag ENHANCER)
  -> headphones, and -> captioner
Backend (FastAPI)
  captioner: clean target audio -> Hydrogen (Live, or 1 s chunks) -> target segments
  raw lane: mixed audio -> same captioner, no targeting -> raw segments (baseline B0 on screen)
  speaking: every 0.5 s per face, a 1 s mouth crop + audio clip -> Decision 1 -> speaking timeline
  leakage guard: drop target-lane words in windows where the target is not speaking
  Neon: merge segments, attribute lines to faces, names from vocab.json, translation (flag)
  Argon: conversation store -> memory answers with time and clip; summary
  logs/calls.jsonl, logs/agent.jsonl, clips/, CSVs
Managed Agent (Google sandbox, never inside the live loop)
  tools: get_new_clips, run_eval(config), propose_config, release_config, save_transcript, send_summary
  hooks: gate_release (regression suite), gate_privacy (consent), post-tool log
  trigger: every 30 minutes, tune on new labeled clips
```

Layer rules:
- L0 Browser at 30 fps, no model calls.
- L1 Audio worker, local, no model calls.
- L2 Hydrogen, Decision 1, Neon and Argon in the backend.
- L3 Managed Agent: tuning, privacy and summaries only. Never in the live loop.

## Managed Agent design
- Environment: one persistent environment named listener. Files persist: clips index, labels, configs, eval history.
- Model: gemini-4-neon if the agent accepts it (G5). If not, the default model runs and calls Neon through the Gemini API, with the key injected by the egress proxy.
- Skill: skills/listener/SKILL.md: the config contract, how to run the eval, the release rule, the consent rule.
- AGENTS.md: never release without the regression suite; never save or send a line without consent; report numbers, not adjectives.
- Tools (client-side, executed by the backend): get_new_clips(since), run_eval(config_id), propose_config(diff), release_config(config_id), save_transcript(conversation_id), send_summary(conversation_id).
- Hooks (.agents/hooks.json):
  - pre_tool_execution on release_config: hooks/gate_release.py runs the regression suite on Set C. Deny if leakage, WER or p50 latency gets worse than the live config. The reason lists each metric, before and after.
  - pre_tool_execution on save_transcript and send_summary: hooks/gate_privacy.py denies if any line belongs to a face without a consent record. The reason lists the lines. The agent redacts and retries.
  - post_tool_execution on all tools: append to the agent log.
- Trigger: every 30 minutes the tuner reads new labeled clips, tries config changes (chunk length, decision threshold, guard window, vocabulary), and proposes the best one.
- Fallback: if client-side tools are not supported, the backend calls the same functions on the agent's request through files in the sandbox (RELEASED file pattern), and the hooks run as command hooks on file writes.

## Contracts (E2 creates these first)
- contracts/face.schema.json: id, box, lips, mouth_open, color, consent {given, by, time}.
- contracts/segment.schema.json: t0, t1, lane (target | raw | other), face_id, text, confidence, source (live | chunk | gemini_only).
- contracts/decision.schema.json: face_id, window_t0, window_t1, p_speaking, latency_ms.
- contracts/config.schema.json: config_id, enhancer, chunk_ms, decision_threshold, guard_ms, vocab, translate_to.
- contracts/memory_answer.schema.json: question, answer, time, clip, confidence.
- contracts/eval.md: how WER, leakage, attribution and latency are computed (fixed now, before any data).

## Evaluation
Metric definitions are fixed now, before any data.
- Set C, clips: at least 40 two-talker clips and 10 three-talker clips of 10 to 20 s, recorded at the venue with consent. Vary distance (1, 2, 3 m), angle (front, 45 degrees, profile), noise (quiet room, hall), occlusion (hand or cup near the mouth). Truth: each talker holds a phone near their own mouth as a close-talk reference; S4 types the truth from those recordings.
- Arms: B0 raw captions of the mixed audio (same captioner, no targeting). B1 Gemini only: Hydrogen given the 1 s AV chunk and "transcribe only the person in the box". B2 ours, full pipeline.
- Metrics: target WER; leakage = share of target-lane words that belong to another talker; attribution accuracy of lines to faces; latency p50 and p95 from speech to caption.
- Set D, decisions: every 0.5 s window of Set C labeled speaking or not per face. Score: accuracy at 0.9, calibration chart.
- Where it breaks: leakage and WER by noise level (measured dB), 2 against 3 talkers, angle, distance, occlusion.
- Gate: say "beats raw captions" only if leakage drops by at least 20 points with WER no more than 5 points worse, on at least 30 clips. Report counts.

## UI (readable from the back of a room)
- Top 60 percent: the live camera with face boxes, speaker colors, target ring, wall clock.
- Bottom: two caption lanes. Left "What the microphone hears" (raw, B0). Right "Look to Listen" (target). Other speakers' lines in their colors under the target lane.
- Side strip: LEAKAGE counters (raw against ours on this conversation), AGENT stream (tool calls and hook decisions), MEMORY answer box.
- END CARD: "Look to Listen. Hear only who you look at." Set C numbers, where it breaks, repo link and QR.
- Caption text at least 32 px, counters at least 40 px, high contrast.

## Acceptance tests
- AT1 Faces: 3 faces tracked at 25 fps or more with lips; target ring follows the center face.
- AT2 Enhancer: RAVEN runs live with real-time factor under 1.0 on the laptop; a listener rates the other voice clearly lower in 4 of 5 two-talker tries.
- AT3 Captions: one talker in a quiet room, WER at or under 10% on 5 sentences, p50 latency at or under 1.5 s.
- AT4 Target lane: 10 two-talker clips, leakage at or under 15% on average, WER at or under 25%.
- AT5 Switch: target lane switches in 1.5 s or less, 9 of 10.
- AT6 Decisions: p50 at or under 300 ms; at least 18 of 20 labeled windows right at 0.9.
- AT7 Who said what: lines attributed to the right face in at least 85% of lines on 5 three-talker clips.
- AT8 Memory: 5 questions on a 10 minute conversation, at least 4 right with a time within 15 s, each in 8 s or less.
- AT9 Tuner: one scheduled run proposes a config; the release hook allows a better one and denies a worse one, 2 of 2.
- AT10 Privacy: save_transcript with a non-consenting face is denied with the reason; after redaction it passes, 3 of 3.
- AT11 Raw lane: B0 runs beside the target lane on the same audio with no extra delay over 300 ms.
- AT12 Evaluation: Sets C and D filled as defined; END CARD renders from the files.
- AT13 Room: setup in 60 s or less, 3 of 3.
- AT14 Rehearsal: 10 full runs with different second talkers, 8 clean.

## WOW test (checkable)
In the judging room, live, under 3:00: two people talk at once. The right lane shows the target's words while the left lane shows both. The leakage counter is lower on the right. Pointing at the other person switches the lane in 1.5 s or less. The headphones play the target voice. A save of a non-consenting person's lines is denied by the privacy hook on screen. The END CARD shows the Set C numbers.
Evidence: clips.csv rows and the recording if the room allows it.

## Out of scope
Hearing aid hardware, glasses, an app store build, accounts, sign language, more than 4 faces at once.

## Fallbacks (each behind a flag)
- FB1 RAVEN fails or runs slower than real time: ENHANCER off. Target lane comes from B1 (Gemini only) plus the leakage guard. Headphones dropped from the demo.
- FB2 Hydrogen Live not available: 1 s chunks to gemini-4-hydrogen at low thinking.
- FB3 Decisions API down: mouth-open ratio from MediaPipe decides speaking, marked "uncalibrated".
- FB4 Argon slow: Neon answers memory questions from the transcript, marked "transcript only".
- FB5 No client-side tools in the agent: file pattern (see Managed Agent design).
- FB6 Room too quiet for a second talker: the judge picks any video on their phone as the interference.
- FB7 No projector: the laptop turns to the judges.
- FB8 Venue Wi-Fi: phone hotspot.
- FB9 Everything else: the 60 s recording of the best run, labeled with its time.

## Rules
- All project code is written on event day. Open-source libraries and models are declared in the README.
- Consent before captioning a person. No audio of anyone without consent is kept. Faces of non-consenting people are blurred in any recording.
- Never store raw audio outside clips/ and only for consenting people.

## Go deeper (Oct 15 rule)
1. What a top professional would do: fix the metrics before data; record a close-talk reference for every talker so truth is real, not guessed; measure the raw baseline on the same audio; show leakage, not just WER; measure where it breaks by condition; keep the agent out of the live loop.
2. Rawest material: the raw mixed audio, per-talker close-talk recordings, the lip landmarks, raw model JSON and Decision 1 probabilities.
3. Methods and tools: MediaPipe Face Landmarker; RAVEN; Gemini Live API (16 kHz PCM in); the Decisions API; Neon and Argon; jiwer for WER; Managed Agents tools, hooks and triggers; pytest for the regression suite.
4. Proof that is not us: judges' own voices, the close-talk truth, the raw lane on the same audio, the hook decisions in the agent log.

## After the event
- Release the code, Set C (consenting people only, with their written OK) and the eval scripts.
- Paper: live audio-visual target-speaker captioning with frontier multimodal models in a real venue, measured by leakage and WER against audio-only captioning, with calibrated per-face speaking decisions.
- Post the pitch clip and the numbers on X, tagging Google DeepMind and Google AI Studio. Send the repo to the judges you met.

## Open questions (answer at the event start)
- Slot length, Q&A length, projector input, which judges sit in which room, how many advance, Managed Agents prize criteria.
- Exact Live model id for Gemini 4 Hydrogen, and whether it returns input transcription.
- RAVEN: checkpoint availability, install time and real-time factor on this laptop.
- Decisions API: video and audio input format, latency on venue Wi-Fi.
- Managed Agent: accepts gemini-4-neon? Client-side tools? Tool names for hook matchers?
