# Look to Listen

Point your phone at a person in a noisy room. Hear only their voice, with live captions.

Built in one day at the Gemini 4 NYC Hackathon (Element 119 track).

## Why

Over 430 million people live with disabling hearing loss (WHO). Hearing aids make the whole room louder. In a crowd, the one voice you want is buried.

## How it works

1. An iPhone camera (Continuity Camera) feeds Chrome. MediaPipe Face Landmarker tracks faces in the browser.
2. You click a face and that person consents. Nobody is captioned without consent.
3. Every 0.5 s the browser sends 0.5 s of 16 kHz audio plus that person's lip crops (25 fps) to the backend.
4. The backend forwards each hop over an SSH tunnel to an RTX 4090. The open AV_MossFormer2_TSE_16K model (ClearVoice, Alibaba) uses the lips to pull that one voice out of a rolling 3 s window. 130 ms per hop. The result is crossfaded into a stream you hear in AirPods.
5. A lip gate: when the target's lips are still, their channel goes quiet and their captions get silence, so other people's words never land in their lane.
6. Two caption lanes, side by side:
   - Left: everything the microphone hears (Gemini 3.5 Transcribe Live on the raw mix).
   - Right: only the person you are looking at (Gemini 3.5 Transcribe Live on the separated voice).

## Models and their jobs

| Model | Job |
|---|---|
| gemini-3.5-transcribe-live | Live captions for both lanes |
| Gemini 4 Hydrogen | Engine A: audio-visual captions on 2 s chunks when the GPU is unreachable; chunked caption fallback |
| Gemini 4 Argon (thinking LOW) | Conversation memory and "Ask" |
| Gemini 4 Neon | Runs the Managed Agent |
| Managed Agent (antigravity-preview-09-2026) | Hooks in `agent_env/`: `gate_privacy` (nothing kept for faces without consent), `gate_command` (only the consented target can command the robot), `gate_release` (config changes that regress are blocked). 30-minute trigger. |
| Gemini Robotics ER 2 preview | Turns a command from the consented target into a robot action |
| Decisions API (gemini-decision-1) | Speaking or not speaking per face from 4 frames plus audio. Advisory only (see below) |
| Gemini 4 Carbon (in Antigravity) | Built the frontend |
| MediaPipe Face Landmarker | Face tracking and lip motion in the browser |
| AV_MossFormer2_TSE_16K (ClearVoice, open, not Google) | Lip-guided voice separation on the GPU |

## Measured today

| What | Result |
|---|---|
| GPU separation | 130 ms per 0.5 s hop (RTX 4090) |
| Voice delay on a phone hotspot | 0.99 s median, 1.33 s p95 (594 hops, 0 failovers) |
| Gemini-only engine (Hydrogen, 2 s AV chunks) | 0% leakage, but 46% word error and 8.5 s behind |
| Decisions API | 1.6 s per call; 11/20 correct at 0.9, 17/20 at 0.5 |
| Robotics ER 2 | 5/5 correct, about 2.1 s |
| Lip gate | mouth-open swing 0.00 to 0.04 per hop when silent, typically 0.1 to 0.5 when talking; threshold 0.05 |
| Crowd lab test, 7 faces | about +6 dB SI-SDR gain when the crowd is as loud as the speaker |

## Where it breaks

- Crowd 10 dB louder than the speaker: separation gain drops to about +2.4 dB. Broken.
- Faces beyond about 2 m: the face detector misses them.
- Target goes quiet: the separator leaks the room. Fixed with the lip gate.
- Venue Wi-Fi: stalls every 1 to 2 minutes. The app fails over to Engine A and returns to the GPU on its own after 2 good probes.
- Decisions API: too slow for a 0.5 s loop, and at 0.9 it dropped real words. Kept as an advisory signal; the lips decide.

## What is real and what is not

- Real: live separation on a GPU, live captions, the lip gate, automatic failover and recovery, Managed Agent hooks, Robotics ER 2 calls.
- Not yet: a labeled evaluation set (`clips.csv` is empty), on-device separation, a real robot (the robot panel shows the plan only).

## Run it

GPU pod (`gpu_pod/`): `pod_setup.sh`, then `run_separator.sh`. The server binds 127.0.0.1 only and needs `SEPARATOR_TOKEN`. Reach it with an SSH tunnel to local port 18000.

Laptop:

```
# .env: GEMINI_API_KEY, SEPARATOR_URL=ws://localhost:18000/separate, SEPARATOR_TOKEN
uvicorn backend.main:app --port 8000
npm --prefix frontend install && npm --prefix frontend run dev   # http://localhost:5173
```

The face model and MediaPipe wasm live in `frontend/public/models` and `frontend/public/wasm`.

## Privacy

Consent before captioning anyone. The GPU server never stores audio. Keys live in `.env` only.
