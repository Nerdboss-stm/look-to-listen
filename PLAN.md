# PLAN.md: Look to Listen (live base)

Every task takes under 30 minutes and ends in a check. Each Claude Code session loops on its task until the check passes, writes the evidence in PROGRESS.md, then takes the next task. No skipping a failed check.
The base version is LIVE. Replay exists only as fallback FB4.

## Before 9:30 (no project code)
| ID | Task | Time | Done when |
| --- | --- | --- | --- |
| P1 | Run gemini4-prep/setup_mac.sh (home or venue Wi-Fi) | 15 min | Prints "Failures: 0" and the G1 lines |
| P2 | RunPod: add $10 credit if needed; add your SSH public key in Settings | 3 min | Done |
| P3 | Send the builder post and the DM to Julian (texts below) | 3 min | Sent |

### Texts to send
- Discord builder post: "looking for 1 builder for gemini 4 nyc today. look to listen: two people talk at once, you point a laptop at one, and you get only their words and their voice, live. gemini 4 hydrogen live + decisions api + managed agents, a cloud gpu doing the separation, and a robot that only obeys who it's looking at. element 119. need someone strong in python audio, websockets or realtime web (mediapipe a plus). spec and plan are ready. dm me"
- DM to Julian: "hey julian, building this today at gemini 4 nyc: look to listen. two people talk over each other, you point a laptop at one, and it gives you only their words and voice, live. robot layer too. want to team up? spec's ready"

## Saturday Nov 21 (T = submission deadline; block times are targets)

### Block A, 9:00 to 11:00: the live path end to end, crude
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E0 | All | Check-in: our room, its judges, slot length, projector input, how many advance, Managed Agents criteria. Wi-Fi and hotspot test. Write T on paper | Answers in SPEC Open questions |
| E1 | S1 | GPU pod per gemini4-prep/GPU_POD.md; G1-GPU bench on the pod | DONE 10:58 by the Claude chat: 131 ms median (PROGRESS.md). S1 skips it |
| E2 | S1 | Separation server per SPEC contract: /separate WebSocket, /health, token check, rolling 3 s buffer, drop stale hops. Test client sends recorded hops | AT2. Owned by the Claude chat in ../gemini4-prep/pod/. S1 skips E1 and E2 and starts at E7 |
| E3 | S3 | Gates G2, G3, G4, G6 (prompts.md) | Rows in gate_log.csv |
| E4 | S4 | Gate G5 Managed Agent; gate G7 round trip from the venue | Answers in SPEC Open questions; AT3 numbers |
| E5 | S2 | contracts/ from SPEC (face, hop, hop_result, segment, decision, config, command, memory_answer, eval.md) | Samples validate |
| E6 | S2 | Browser: camera and mic at 16 kHz, MediaPipe Face Landmarker (model from gemini4-prep/models), target ring, ClearVoice face crops, hop packing every 0.5 s | AT1; hops validate at 2 per second |
| E7 | S1 | Backend skeleton: FastAPI, .env, call logger, websocket to the browser, separation client to the pod, playback with crossfade, logs/hops.jsonl | Clean voice heard from the laptop speaker with two people talking |
| E8 | All | 10:45 decision (prompts.md table): engine order confirmed | Written at the top of PROGRESS.md |

### Block B, 11:00 to 14:00: the live core, solid
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E9 | S1 | Live voice quality and continuity: crossfade, no gaps, drop stale hops, delay meter | AT4 |
| E10 | S3 | Raw lane: Hydrogen Live session 1 on the mixed audio | AT7 |
| E11 | S3 | Target lane: Hydrogen Live session 2 on the clean voice | AT5 caption delay part |
| E12 | S3 | Decision 1 speaking per face every 0.5 s; leakage guard on the target lane | AT8; AT5 leakage part |
| E13 | S2 | Target switching: center face or tap; reset hop to the server | AT6 |
| E14 | S2 | UI: two live lanes, speaker colors, LEAKAGE counters, DELAY meter, ENGINE label, sized for a projector | A photo of the projected screen reads from 5 m |
| E15 | S3 | Engine A live (2 s AV chunks with the target box) and automatic failover from the GPU | AT14 |
| E16 | S4 | Start Set C: record consenting pairs live through the app, with close-talk phones for truth | 10 clips in clips.csv by 2 PM |
| E17 | S4 | Show it to a DeepMind mentor by 2 PM; feedback in NOTES.md | Feedback written |

### Block C, 14:00 to T minus 3h: who said what, agent, robot, memory
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E18 | S3 | Neon: merge, attribute lines to faces, vocab.json | AT9 |
| E19 | S3 | Managed Agent: tools, AGENTS.md, SKILL.md, privacy hook | AT11 |
| E20 | S3 | Robot R1: target command + live frame to Hydrogen pointing; ROBOT panel; command hook | AT12 |
| E21 | S3 | Tuner: run_eval in the sandbox, release hook, 30 min trigger | AT13 |
| E22 | S3 | Argon memory answers and summary | AT10 |
| E23 | S2 | AGENT stream, MEMORY box, ROBOT panel | Hook decisions visible from 5 m |
| E24 | All | First full live room run | WOW attempt logged |
| E25 | S4 | After the first clean live run (target 3 PM): post a clip of 30 s or less on X, tagging Google DeepMind and Google AI Studio | Posted |
| E26 | S4 | Set C to 40 two-talker and 10 three-talker clips; Set R to 10 command pairs | clips.csv and robot.csv filled |

### Block D, T minus 3h to T: prove and polish
| ID | Session | Task | Done when |
| --- | --- | --- | --- |
| E27 | S4 | Run B0, Engine A and Engine B-GPU on every Set C clip through the live code path; compute WER, leakage, attribution, delay | clips.csv scored |
| E28 | S4 | Set D: label speaking windows; Decision 1 calibration chart | decisions.csv filled, chart saved |
| E29 | S4 | Where it breaks: by noise, talkers, angle, distance, occlusion, network | Charts on the END CARD |
| E30 | All | Feature freeze at T minus 90 | Only fixes after this |
| E31 | S4 | 10 full live rehearsals with different second talkers, one on the hotspot; 3 mock-room pitches with Q&A asked cold | AT16 |
| E32 | S4 | Insurance recording of the best live run at T minus 60, labeled with its time | demo/insurance.mp4 saved |
| E33 | S4 | README: what, how to run, eval tables, delay, where it breaks, a Managed Agents section with the hook diagram, declared libraries and models | README done |
| E34 | S4 | Submit, video within the stated length. Stop the GPU pod after judging | Submitted; pod stopped |

### Stretch, only after E24 is clean
- Robot R2: MuJoCo Menagerie Panda (gemini4-prep/third_party) reaches for the asked block in sim. Only with a teammate.
- Engine B-Mac: run the separation on the laptop's GPU if G1-Mac allows, so the demo survives with no network.

## Build order if time runs short
Each layer must work on its own before the next starts.
1. Live voice from the GPU plus the two live caption lanes (E1, E2, E6, E7, E9 to E14). That alone is the live demo.
2. Failover to Engine A (E15). Live keeps working if the GPU or network fails.
3. Managed Agent with the privacy hook (E19). Needed for the Managed Agents prize.
4. Robot R1 with the command hook (E20). The robotics answer.
5. Tuner, Neon polish, memory (E18, E21, E22).

## If the team is small
Cut in this order: E25, translation, E22 memory (keep the summary), E21 tuner, three-talker clips.
Never cut: E1, E2, E6, E7, E9 to E15, E19, E20, E26, E27, E31, E32.
