# SPEC.md: Look to Listen (live base)

Source of truth for the Gemini 4 NYC build. Sat Nov 21, 2026, The Malin, 9 AM to 10 PM.
Track: Element 119. Judging: round 1 in one of 6 rooms, then a final in front of everyone.
Chosen Nov 21, 2 AM, from 12 ideas scored on 56 criteria (sheet: "Gemini 4 NYC: every idea scored").
Revised Nov 21, 8:45 AM: LIVE is the base version. Voice separation runs on a cloud GPU on rolling windows. Replay is a fallback only.
Older versions are in archive/. Do not use them.

## One line
Hear only who you look at.

## What it is (base version, all live)
Point a laptop or phone camera at people in a noisy room. While they talk:
- The left lane captions what the microphone hears: everyone, mixed.
- The right lane captions only the person the camera points at, about 2 s behind them.
- Their voice, pulled out of the mix, plays live in headphones or on the speaker.
- Every face gets its own color, and every line is attributed to the face that said it.
- Point at someone else, and the right lane and the voice switch to them within about 2 s.
- It remembers the conversation and answers "what did she say about X?" with the moment.
- Robot layer: when two people give a robot different commands at once, it acts only for the person it is looking at.

Friend version: "Everyone was talking at once. They pointed a laptop at one person, and the captions and the voice followed only her, live."

## The problem (numbers we can say out loud)
- WHO, Mar 2026: 430 million people need rehabilitation for disabling hearing loss. Unaddressed hearing loss costs almost US$1 trillion a year.
- Action on Hearing Loss survey (2017): 96% of people with hearing loss struggle in noisy places. Only 12% of hearing aid users are satisfied with the technology that helps them there.
- Google Research's SpeechCompass survey (n=263, CHI 2025 Best Paper): captions fail in group conversations because they can't tell speakers apart.
- Today's captions (Live Transcribe, Live Caption) write everyone into one stream. Meta's Conversation Focus amplifies the person you face, but Meta says it is not for extremely loud places, and it gives no captions.
- Robots: a robot in a home or a factory hears everyone. It has to know whose command to follow.

## Why DeepMind and Google people will care
- Google Research's Looking to Listen (SIGGRAPH 2018) isolated one voice by pointing at a face, on recorded video. This does it live.
- SpeechCompass needed a 4-microphone phone case to separate speakers. This uses the camera.
- Google demoed real-world subtitles on Android XR glasses, and display glasses are on its roadmap.
- Hydrogen carries Gemini Robotics ER skills. The robot layer uses them for the "whose command?" problem.

## What we know (measured Nov 21, 3 AM)
- RAVEN (Bose) publishes training code only, no trained weights. Dropped.
- ClearVoice (Alibaba, Apache-2.0, `pip install clearvoice`) has a pretrained audio-visual target speaker model, AV_MossFormer2_TSE_16K (734 MB). It worked on its own two-speaker demo video.
- On a 2-core CPU, a 3 s window took 14.7 to 16.4 s. Too slow for live on a CPU.
- Its code was written for Nvidia GPUs (it calls CUDA directly). On a cloud GPU it runs as written. On a Mac it needs the patch setup_mac.sh applies.
- The model looks at a whole window at once. Live works by running it on the last 3 s every 0.5 s and playing only the newest part of each result.

## Element 119 compliance
| The brief asks | Look to Listen |
| --- | --- |
| Faster real-time loops | Face tracking at 30 fps, separation every 0.5 s, speaking decisions every 0.5 s, live captions on two lanes |
| More streams at once | Camera, microphone, a face stream per person, a GPU separation stream, two caption streams |
| Messier audio | Overlapping talkers and venue noise are the input |
| Longer footage | The whole conversation is kept for memory questions and the summary |
| The Decisions API | "Is this person speaking?" for every visible face, every 0.5 s |
| Show where it breaks | Leakage, WER and delay by noise, number of talkers, angle, distance and occlusion, on the END CARD |
| No scripted demos | Whoever is in the room talks, about anything, live |
| No team-written eval | Set C clips come from people at the venue, with consent |

## Models and their jobs
| Job | Model or service | What it does |
| --- | --- | --- |
| Ears | gemini-3.5-transcribe-live (dedicated live speech-to-text; Vertex lists gemini-3.5-transcribe-live-preview), else gemini-4-hydrogen-live, else gemini-4-hydrogen in 1 s chunks. G2 picks by WER. Confirm ids in AI Studio | Two live caption streams: the raw mix and the clean target voice |
| Separation | ClearVoice AV_MossFormer2_TSE_16K on a cloud GPU (RunPod, Modal as backup) | Pulls the target's voice out of the mix from their face crops, every 0.5 s |
| Reflexes | gemini-decision-1 (Decisions API) | Calibrated "is this face speaking?" per face per 0.5 s |
| Target listener (Engine A) | gemini-4-hydrogen | Gemini-only target captions from AV chunks with a box on the target face (fallback and comparison arm) |
| Robot eyes | gemini-robotics-er-2-preview (DeepMind's pointing and spatial model), else gemini-4-hydrogen | Points at the object the target person asked for |
| Brain | gemini-4-neon | Merges segments, attributes lines to faces, names from vocab.json, optional translation |
| Memory | gemini-4-argon | Answers questions about the whole conversation with a time and clip; writes the summary |
| Tuner and guard | Gemini Managed Agent | Tunes the pipeline behind a regression hook; privacy and command hooks |

On stage, one line: "Gemini listens live on two streams, a GPU pulls out the voice you're looking at, the Decisions API watches every mouth, Neon keeps names right, Argon remembers, and a Managed Agent improves it behind gates."

Open-source building blocks, declared in the README: MediaPipe Face Landmarker, ClearVoice, MuJoCo and MuJoCo Menagerie (robot stretch only).

## Engines, in order of preference (all live)
1. Engine B-GPU (base): ClearVoice on a cloud GPU. Gate G1-GPU.
2. Engine B-Mac: the same model on the Mac's GPU (MPS), only if setup_mac.sh's G1 line shows a 3 s window in 0.7 s or less.
3. Engine A: Gemini only, live 2 s chunks with the target box and the Decision 1 guard. No clean voice.
4. REPLAY (last resort): separate the last 10 s on tap.

## Live loop and latency budget
- Window 3 s, hop 0.5 s. Each hop the server runs the model on the last 3 s of audio and the target's last 75 face crops, and returns the newest 0.5 s of clean voice, crossfaded with the previous hop.
- Target budget from speech to sound and text:
| Step | Budget |
| --- | --- |
| Collect one hop | 500 ms |
| Crop and encode faces (browser) | 20 ms |
| Upload hop to GPU (about 60 KB) | 80 ms |
| GPU separation of a 3 s window | 300 ms or less (gate G1-GPU) |
| Download 0.5 s clean audio | 30 ms |
| Playback buffer | 150 ms |
| Clean voice behind the speaker | about 1.1 s |
| Live captions of the clean voice | plus about 1 s |
| Target caption behind the speaker | about 2 s |
- If GPU separation takes longer than the hop, the hop grows to match (UI shows the measured delay). Never queue: drop stale hops.

## Separation server contract (written at the event, runs on the GPU)
- FastAPI with one WebSocket, /separate. Loads the model once at start. Keeps a rolling 3 s buffer per session.
- Client sends per hop: session_id, seq, target_face_id, 0.5 s of 16 kHz mono int16 PCM, and 12 or 13 face crops of the target as 112x112 grayscale JPEG (25 fps).
- Face crops follow ClearVoice's own recipe: smoothed face box, half-size s, crop rows y-s to y+s(1+2c) and columns x-s(1+c) to x+s(1+c) with c=0.4 (pad the frame first), resize to 224x224, gray, center crop 112x112; the server normalizes (x/255 - 0.4161)/0.1688.
- On a target switch the client sends reset=true; the server clears the face buffer and refills it.
- Server returns per hop: seq, 0.5 s clean int16 PCM, gpu_ms, queue_ms.
- Health endpoint /health returns the model name, GPU name and the last 20 gpu_ms values.
- Auth: a shared token in a header. The laptop reads SEPARATOR_URL and SEPARATOR_TOKEN from .env; the pod reads SEPARATOR_TOKEN from its environment. Never logged.
- Wire format, little-endian binary WebSocket frames:
  - Hop, client to server: a 4-byte header length n, n bytes of JSON {session_id, seq, target_face_id, reset, pcm_bytes, jpeg_sizes, sent_ms}, then the PCM, then the JPEGs back to back in jpeg_sizes order.
  - Result, server to client: a 4-byte header length n, n bytes of JSON {seq, covers: [first_seq, last_seq], samples, gpu_ms, queue_ms, sent_ms}, then `samples` of int16 PCM. sent_ms is echoed from the newest hop, so the client measures the round trip on its own clock.
  - If hops pile up, the server separates once and returns all their audio in one result; covers names them. Playback stays gapless. The delay meter shows the growth.
  - The server holds back the last 40 ms of each output and crossfades it into the next one. The client plays results back to back.
  - Token: header "Authorization: Bearer <token>", or a first text frame {"token": "..."} from clients that cannot set headers. A bad token closes with code 4401.
- Network: the server listens on 127.0.0.1:8000 on the pod. The laptop reaches it through an SSH tunnel, so SEPARATOR_URL is ws://localhost:18000/separate (local port 18000, so the backend can keep 8000). Server code: ../gemini4-prep/pod/.
- Pod setup steps: gemini4-prep/GPU_POD.md.

## Organic rules (these beat every other section)
- We never choose what anyone says.
- Everything on screen in the room is live. Any recording on screen shows its time.
- Interference is real: a second person talking, or any video a judge picks on their own phone.
- No paper, no tape, no kit, no food.
- Consent first: we caption a person only after they say yes. Nobody else's speech is saved. The privacy hook enforces this.
- Zero leakage is not required. Show the real number and the real delay.

## Opening shot (one sentence)
Two people talk at once; the left lane on the big screen is a jumble of both, and the right lane, live, shows only the person the laptop points at while her voice plays alone.

## Idea gate (Sep 13 system)
- Person: someone with hearing loss at a loud dinner or work event. WHO: 430 million; almost US$1 trillion a year.
- Sponsor products said out loud: Gemini 4 Hydrogen (Live), Neon, Argon, the Decisions API, Managed Agents.
- Mechanism in one picture: the live loop above.
- Numbers that move on screen: leakage (share of target-lane words that came from someone else), raw lane against target lane, and the measured delay.
- Opening shot: above.

## Claims (all live)
- C1 Live target captions: with two people talking at once, the target lane captions the target while they talk, with leakage lower than the raw lane.
- C2 Live voice: the target's clean voice plays about 1 s behind them.
- C3 Switch: pointing at another face switches the target lane and the voice within 2 s.
- C4 Who said what: every visible face gets its own color and lines, from Decision 1.
- C5 Memory: "what did she say about X?" is answered with a time and the clip in 8 s or less.
- C6 Robot: with two conflicting commands, the robot points at the object the target asked for; the command hook blocks the other.
- C7 Tuner: the Managed Agent proposes a better config from new clips; the regression hook releases it only if no metric gets worse.
- C8 Privacy: saving or sending a line from a face without consent is denied by the privacy hook, with the reason on screen.
- C9 Where it breaks: numbers by noise, talkers, angle, distance, occlusion and delay.

## Do not claim
- Medical device, hearing aid replacement, "first ever".
- "Zero latency". Say the measured delay.
- "Better than Meta" or any product we did not test.
- "Beats the baseline" unless the gate rules in Evaluation pass.
- World models.
- Anything not on screen.

## Hardware and services
- Laptop, phone, headphones, HDMI adapter, a small phone stand, phone hotspot, charger, extension cord.
- One cloud GPU (RunPod pod, 24 GB class such as RTX 4090, L4 or A5000; Modal L4 as backup), kept warm all day. Cost about $0.40 to $0.80 an hour. Stop it after the event.

## Architecture
```
Browser (laptop, 30 fps, no model calls)
  getUserMedia video + audio (16 kHz mono)
  MediaPipe Face Landmarker -> faces {id, box, lips, mouth-open ratio}
  target = face nearest the center, or the one tapped
  every 0.5 s: hop = 0.5 s audio + target face crops -> backend
  overlay: face boxes in speaker colors, target ring, two caption lanes, counters, delay meter, wall clock
Backend (FastAPI on the laptop, ~/.venvs/g4-backend)
  raw lane: mixed audio stream -> live caption session 1 (model from G2) -> raw captions
  separation client: hop -> GPU /separate (WebSocket) -> clean 0.5 s -> playback + live caption session 2 (model from G2) -> target captions
  speaking: every 0.5 s per face, a 1 s face crop + audio clip -> Decision 1 -> speaking timeline
  leakage guard: drop target-lane words in windows where the target is not speaking
  Engine A (fallback): 2 s AV chunk + target box -> Hydrogen -> target captions
  Neon: merge, attribute, vocab.json, translation (flag)
  Argon: conversation store -> memory answers and summary
  robot R1: target command + frame -> Hydrogen pointing -> reach point; robot_act tool
  logs/calls.jsonl, logs/agent.jsonl, logs/hops.jsonl, clips/, CSVs
GPU separation server (RunPod pod, CUDA)
  /separate WebSocket, /health; ClearVoice model loaded once; rolling 3 s buffer per session
Managed Agent (Google sandbox, never inside the live loop)
  tools: get_new_clips, run_eval(config), propose_config, release_config, save_transcript, send_summary, robot_act
  hooks: gate_release (regression), gate_privacy (consent), gate_command (target-only robot commands), post-tool log
  trigger: every 30 minutes, tune on new labeled clips
```

## Managed Agent design
- Environment: one persistent environment named listener. Files persist: clips index, labels, configs, eval history.
- Model: gemini-4-neon if the agent accepts it (G5). If not, the default model runs and calls Neon through the Gemini API, with the key injected by the egress proxy.
- Skill: agent_env/skills/listener/SKILL.md: the config contract, how to run the eval, the release rule, the consent rule, the command rule.
- agent_env/AGENTS.md: never release without the regression suite; never save or send a line without consent; never act for a face that is not the target; report numbers, not adjectives.
- Tools (client-side, executed by the backend): get_new_clips(since), run_eval(config_id), propose_config(diff), release_config(config_id), save_transcript(conversation_id), send_summary(conversation_id), robot_act(command_id).
- The Managed Agent environment is the agent_env/ folder. Never put an AGENTS.md or a .agents/ folder for it at the repo root: Antigravity, the IDE we build in, would load them as its own rules and hooks.
- Hooks (agent_env/.agents/hooks.json):
  - pre_tool_execution on release_config: agent_env/hooks/gate_release.py runs the regression suite on Set C. Deny if leakage, WER or delay gets worse. The reason lists each metric, before and after.
  - pre_tool_execution on save_transcript and send_summary: agent_env/hooks/gate_privacy.py denies if any line belongs to a face without consent. The agent redacts and retries.
  - pre_tool_execution on robot_act: agent_env/hooks/gate_command.py denies if the command's face is not the current target. The reason names the face.
  - post_tool_execution on all tools: append to the agent log.
- Trigger: every 30 minutes the tuner reads new labeled clips, tries config changes (window, hop, decision threshold, guard window, vocabulary), and proposes the best one.
- Fallback: if client-side tools are not supported, the backend calls the same functions on the agent's request through files in the sandbox (RELEASED file pattern), with command hooks on file writes.

## Contracts (E5 creates these first)
- contracts/face.schema.json: id, box, lips, mouth_open, color, consent {given, by, time}.
- contracts/hop.schema.json: session_id, seq, target_face_id, reset, pcm (base64 int16, 8000 samples), crops (12 or 13 base64 JPEG), t_capture.
- contracts/hop_result.schema.json: seq, pcm (base64 int16, 8000 samples), gpu_ms, queue_ms, t_return.
- contracts/segment.schema.json: t0, t1, lane (target | raw | other), face_id, text, confidence, engine (B-GPU | B-Mac | A | replay).
- contracts/decision.schema.json: face_id, window_t0, window_t1, p_speaking, latency_ms.
- contracts/config.schema.json: config_id, engine, window_s, hop_s, decision_threshold, guard_ms, vocab, translate_to.
- contracts/command.schema.json: command_id, face_id, text, target_face_id, point [y, x], object_label.
- contracts/memory_answer.schema.json: question, answer, time, clip, confidence.
- contracts/eval.md: how WER, leakage, attribution and delay are computed (fixed now, before any data).

## Evaluation
Metric definitions are fixed now, before any data.
- Set C, clips: at least 40 two-talker clips and 10 three-talker clips of 10 to 20 s, recorded live at the venue with consent. Vary distance (1, 2, 3 m), angle (front, 45 degrees, profile), noise (quiet room, hall), occlusion (hand or cup near the mouth). Truth: each talker holds a phone near their own mouth as a close-talk reference; S4 types the truth from those recordings.
- Arms, run on the same recorded clips through the live code path: B0 raw captions of the mix; Engine A; Engine B-GPU.
- Metrics: target WER; leakage = share of target-lane words that belong to another talker; attribution accuracy; delay = time from a word's end in the close-talk track to its caption on screen; voice delay from logs/hops.jsonl.
- Set D, decisions: every 0.5 s window of Set C labeled speaking or not per face. Score: accuracy at 0.9, calibration chart.
- Set R, robot: at least 10 conflicting-command pairs from different people. Score: the reach point lands on the object the target asked for.
- Where it breaks: leakage, WER and delay by noise level (measured dB), 2 against 3 talkers, angle, distance, occlusion, network (venue Wi-Fi against hotspot).
- Gate: say "beats raw captions" only if leakage drops by at least 20 points with WER no more than 5 points worse, on at least 30 clips. Report counts.

## UI (readable from the back of a room)
- Top 60 percent: the live camera with face boxes, speaker colors, target ring, wall clock.
- Bottom: two live caption lanes. Left "What the microphone hears" (raw). Right "Look to Listen" (target). Other speakers' lines in their colors.
- Side strip: DELAY meter (voice and captions, live), ENGINE label, AGENT stream, MEMORY box, ROBOT panel. LEAKAGE counters sit in each lane's header.
- Visual details: DESIGN.md.
- END CARD: "Look to Listen. Hear only who you look at." Set C, D and R numbers, delay, where it breaks, repo link and QR.
- Caption text at least 32 px, counters at least 40 px, high contrast.

## Acceptance tests
- AT1 Faces: 3 faces tracked at 25 fps or more; target ring follows the center face.
- AT2 GPU: /health answers; separation of a 3 s window p50 at or under 300 ms over 50 hops.
- AT3 Round trip: laptop to GPU and back p50 at or under 500 ms on venue Wi-Fi and on the hotspot.
- AT4 Live voice: with two people talking, the clean voice plays continuously for 30 s with no gap over 300 ms; the other voice clearly lower in 4 of 5 tries; voice delay p50 at or under 1.5 s.
- AT5 Live target captions: 10 two-talker clips, leakage at or under 15% on average, WER at or under 25%, caption delay p50 at or under 3 s.
- AT6 Switch: pointing at the other face switches the lane and the voice within 2 s, 9 of 10.
- AT7 Raw lane: one talker in a quiet room, WER at or under 10%, caption delay p50 at or under 1.5 s.
- AT8 Decisions: p50 at or under 300 ms; at least 18 of 20 labeled windows right at 0.9.
- AT9 Who said what: lines attributed to the right face in at least 85% of lines on 5 three-talker clips.
- AT10 Memory: 5 questions on a 10 minute conversation, at least 4 right with a time within 15 s, each in 8 s or less.
- AT11 Privacy: save_transcript with a non-consenting face is denied with the reason; after redaction it passes, 3 of 3.
- AT12 Robot R1: 10 conflicting-command pairs, the reach point is on the target's object in at least 8; the command hook denies the other command 10 of 10.
- AT13 Tuner: one scheduled run proposes a config; the release hook allows a better one and denies a worse one, 2 of 2.
- AT14 Failover: kill the GPU server mid-run; the system switches to Engine A within 3 s and labels it, 3 of 3.
- AT15 Evaluation: Sets C, D and R filled as defined; END CARD renders from the files.
- AT16 Room: setup in 60 s or less, 3 of 3. 10 full live rehearsals with different second talkers, 8 clean.

## WOW test (checkable)
In the judging room, live, under 3:00: two people talk at once. The left lane shows both. The right lane captions only the target while they talk, and her voice plays alone about a second behind her. Pointing at the other person switches both within 2 s. Two conflicting commands make the robot point at the target's object, and the command hook blocks the other. A save of a non-consenting person's lines is denied on screen. The END CARD shows the Set C numbers and the measured delay.
Evidence: clips.csv, robot.csv and logs/hops.jsonl rows, and the recording if the room allows it.

## Out of scope
Hearing aid hardware, glasses, an app store build, accounts, sign language, more than 4 faces at once, a physical robot, world models.

## Fallbacks (each behind a flag)
- FB1 GPU slow or down: Engine B-Mac if G1 allows, else Engine A live. The ENGINE label changes on screen.
- FB2 Network slow: switch to the hotspot; raise the hop to 1 s.
- FB3 Engine A leakage too high: show "who said what" with speaker colors from Decision 1 and say where it breaks.
- FB4 Everything live fails: REPLAY of the last 10 s on tap.
- FB5 Hydrogen Live not available: 1 s chunks to gemini-4-hydrogen at low thinking.
- FB6 Decisions API down: mouth-open ratio from MediaPipe decides speaking, marked "uncalibrated".
- FB7 Argon slow: Neon answers memory questions from the transcript, marked "transcript only".
- FB8 No client-side tools in the agent: file pattern (see Managed Agent design).
- FB9 Robot pointing misses: show the command attribution and the hook decision without the point.
- FB10 Room too quiet for a second talker: the judge picks any video on their phone as the interference.
- FB11 No projector: the laptop turns to the judges.
- FB12 Everything else: the 60 s recording of the best live run, labeled with its time.

## Rules
- All project code, including the GPU server, is written on event day. Open-source libraries and models are declared in the README. Third-party models are downloaded before use; no project code is written before the event.
- Consent before captioning a person. No audio of anyone without consent is kept. Faces of non-consenting people are blurred in any recording.
- The GPU server never stores audio. It keeps 3 s in memory per session and drops it on disconnect.

## Go deeper (Oct 15 rule)
1. What a top professional would do: set a latency budget per step and log every hop; drop stale hops instead of queueing; measure the engines against each other on the same clips; record close-talk truth for every talker; show leakage and delay, not just WER; keep the agent out of the live loop.
2. Rawest material: the raw mixed audio, per-talker close-talk recordings, the face crops, raw model JSON, Decision 1 probabilities, per-hop timings.
3. Methods and tools: MediaPipe Face Landmarker; ClearVoice on CUDA; WebSockets; Gemini Live API (16 kHz PCM in); the Decisions API; Hydrogen pointing; Neon and Argon; jiwer; Managed Agents tools, hooks and triggers; pytest.
4. Proof that is not us: judges' own voices, the close-talk truth, the raw lane on the same audio, the delay meter from logged timestamps, the hook decisions in the agent log.

## After the event
- Stop the GPU pod.
- Release the code, Set C (consenting people only, with their written OK) and the eval scripts.
- Paper: live audio-visual target-speaker captioning in a real venue, comparing a Gemini-only engine with a GPU separation engine, by leakage, WER and delay against audio-only captioning, with calibrated per-face speaking decisions.
- Post the pitch clip and the numbers on X, tagging Google DeepMind and Google AI Studio. Send the repo to the judges you met.

## Open questions (answer at the event start)
- Slot length, Q&A length, projector input, which judges sit in which room, how many advance, Managed Agents prize criteria.
- GPU: which pod type is available now; gpu_ms per 3 s window; round trip from the venue.
- Exact Live model id for Gemini 4 Hydrogen, whether it returns input transcription, and how many Live sessions run at once.
- Decisions API: video and audio input format, latency on venue Wi-Fi.
- Managed Agent: accepts gemini-4-neon? Client-side tools? Tool names for hook matchers?
