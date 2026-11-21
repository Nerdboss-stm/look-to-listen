# prompts.md: gate tests, the 10:45 decision and baselines (Look to Listen, live base)

Run these at the start of the event (E1 to E4). Time every call. Log every run in gate_log.csv.

## G1-GPU ClearVoice on the cloud GPU (the base engine)
- Follow gemini4-prep/GPU_POD.md. On the pod: `cd /workspace/clearvoice_home && python gate_g1_clearvoice.py --bench`
- Record the median and worst time for a 3 s window, and the GPU name.
- Pass: median at or under 0.35 s (0.5 s hops) or at or under 0.7 s (1 s hops).

## G1-Mac ClearVoice on the laptop
- setup_mac.sh already ran it. Copy its "G1" lines from gemini4-prep/setup.log.
- It decides only whether Engine B-Mac is a backup. The base is the GPU.

## G7 Round trip from the venue
- With the separation server running (E2), send 50 recorded hops from the laptop on venue Wi-Fi, then 50 on the hotspot.
- Record p50 and p95 of round trip (send to clean audio back). Pass: p50 at or under 500 ms on at least one network.

## G2 Captions (gemini-3.5-transcribe-live and gemini-4-hydrogen-live on the same audio; else gemini-4-hydrogen at thinking low)
- Live: stream 16 kHz mono PCM of one person reading 5 sentences. Turn on input transcription if the model offers it. Open two sessions at once to confirm both lanes can run together.
- Chunked: the same audio in 1 s chunks with this prompt:
Transcribe the speech in this audio exactly, word for word. Return only the words. If there is no speech, return an empty string.
- Record WER and latency from end of speech to text. Pass: WER at or under 10%, p50 at or under 1.5 s. Write down the exact model id that worked.
- Pick the model with the lower WER among those that pass. Give gemini-3.5-transcribe-live the names in vocab.json as its custom vocabulary (up to 1,000 terms).

## G3 Decisions API speaking (gemini-decision-1)
- 20 clips of 1 s, each a face crop video plus its audio, 10 speaking and 10 silent (the other person talks).
- Question: "Is the person in this video speaking right now?" Closed set: yes, no.
- Record p(yes), truth, latency. Pass: p50 at or under 300 ms, at least 18 of 20 right at 0.9. Write down the input format that worked.

## G4 Engine A, Gemini only (gemini-4-hydrogen, thinking low)
- 5 two-talker clips cut into 2 s chunks, with a box drawn on the target face in every frame.
- Prompt:
Two or more people may be talking at the same time. Transcribe only the words spoken by the person inside the green box. Use their lip movements to decide which words are theirs. Return only those words. If the person in the box is silent, return an empty string.
- Score leakage and WER against close-talk truth, and time per chunk.

## G5 Managed Agent
- Does it accept gemini-4-neon as its model? If not, can the sandbox call the Gemini API with a key injected by the egress proxy?
- Are client-side function tools supported? Exact tool names in the run log, for hook matchers.
- One run with a pre_tool_execution command hook that denies once with a reason: does the agent see the reason and retry on its own?
- Can a scheduled trigger start a run every 30 minutes?

## G6 Robot pointing (gemini-robotics-er-2-preview, else gemini-4-hydrogen; run both on the same 5 photos)
- 5 photos of a table with 4 or more everyday objects, each with a command typed as text.
- Prompt:
A person asked: "<command>". Point to the one object they want. Return JSON only: [{"label": "<object>", "point": [y, x]}] with y and x normalized to 0 to 1000. If no object fits, return [].
- Pass: the point lands on the right object in 4 of 5.

## The 10:45 decision (all rows are live)
| G1-GPU median | G7 round trip p50 | Use |
| --- | --- | --- |
| 0.35 s or less | 500 ms or less | Engine B-GPU, 0.5 s hops (voice about 1 s behind) |
| 0.7 s or less | 500 ms or less | Engine B-GPU, 1 s hops (voice about 2 s behind) |
| 0.7 s or less | over 500 ms | Engine B-GPU on the hotspot with 1 s hops; if still slow, Engine B-Mac if G1-Mac passes |
| over 0.7 s | any | Try a faster GPU (RTX 4090 or better). If none: Engine B-Mac if G1-Mac passes, else Engine A live |
| Engine A leakage over 25% and no GPU | any | Live "who said what" with speaker colors, and say where it breaks (FB3) |

## Baselines (event day, same audio as ours)
- B0, raw captions: the mixed microphone audio through the same captioner as G2, no targeting.
- Engine A and Engine B-GPU as defined in SPEC.

## Scoring (fixed now)
- WER with jiwer after lowercasing and removing punctuation.
- Leakage: words in the target lane that match the other talker's close-talk truth and not the target's, divided by all target-lane words.
- Delay: end of a spoken word (close-talk track) to its caption on screen; voice delay from logs/hops.jsonl.
