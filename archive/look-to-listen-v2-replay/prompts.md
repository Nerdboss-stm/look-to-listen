# prompts.md: gate tests, the 10:00 decision and baselines (Look to Listen)

Run these at the start of the event (E1 to E3). Time every call. Log every run in gate_log.csv.

## G1 ClearVoice on this laptop (Engine B)
- At home, setup_mac.sh already ran the speed check. Copy its "G1" lines from gemini4-prep/setup.log into gate_log.csv.
- At the venue, record a 10 s clip on this laptop with two people talking at once, both in frame, about 1 m away. Run Engine B for each face.
- Record: time to separate the 10 s clip, and whether a listener hears the other voice clearly lower in 4 of 5 tries.
- Full third-party check if anything looks wrong: `cd ~/Hackathons/gemini4-prep/clearvoice_home && ~/.venvs/g4-audio/bin/python ../gate_g1_clearvoice.py --full`

## G2 Captions (gemini-4-hydrogen-live, else gemini-4-hydrogen at thinking low)
- Live: stream 16 kHz mono PCM of one person reading 5 sentences. Turn on input transcription if the model offers it.
- Chunked: the same audio in 1 s chunks with this prompt:
Transcribe the speech in this audio exactly, word for word. Return only the words. If there is no speech, return an empty string.
- Record WER against the read text and latency from end of speech to text. Pass: WER at or under 10%, p50 at or under 1.5 s. Write down the exact model id that worked.

## G3 Decisions API speaking (gemini-decision-1)
- 20 clips of 1 s, each a face crop video plus its audio, 10 speaking and 10 silent (the other person talks).
- Question: "Is the person in this video speaking right now?" Closed set: yes, no.
- Record p(yes), truth, latency. Pass: p50 at or under 300 ms, at least 18 of 20 right at 0.9. Write down the input format that worked.

## G4 Engine A, Gemini only (gemini-4-hydrogen, thinking low)
- 5 two-talker clips of 10 s, with a box drawn on the target face in every frame.
- Prompt:
Two or more people may be talking at the same time. Transcribe only the words spoken by the person inside the green box. Use their lip movements to decide which words are theirs. Return only those words. If the person in the box is silent, return an empty string.
- Score leakage (share of returned words that the other person said) and WER against close-talk truth.

## G5 Managed Agent
- Does it accept gemini-4-neon as its model? If not, can the sandbox call the Gemini API with a key injected by the egress proxy?
- Are client-side function tools supported? Exact tool names in the run log, for hook matchers.
- One run with a pre_tool_execution command hook that denies once with a reason: does the agent see the reason and retry on its own?
- Can a scheduled trigger start a run every 30 minutes?

## G6 Robot pointing (gemini-4-hydrogen)
- 5 photos of a table with 4 or more everyday objects, each with a spoken command typed as text.
- Prompt:
A person asked: "<command>". Point to the one object they want. Return JSON only: [{"label": "<object>", "point": [y, x]}] with y and x normalized to 0 to 1000. If no object fits, return [].
- Pass: the point lands on the right object in 4 of 5. Write down the output format.

## The 10:00 decision
| G1 (3 s window on this laptop) | G4 leakage, Engine A | Use |
| --- | --- | --- |
| 2.4 s or less | any | Engine B, LIVE mode allowed |
| 4.5 s or less | above Engine B's | Engine B, REPLAY mode |
| 4.5 s or less | at or below Engine B's | Engine A for captions, Engine B for voice playback in REPLAY |
| over 4.5 s | 25% or less | Engine A only (FB1) |
| over 4.5 s | over 25% | Engine A plus speaker colors; lead with "who said what" (FB3) |

## Baselines (event day, same audio as ours)
- B0, raw captions: the mixed microphone audio through the same captioner as G2, no targeting.
- Engine A and Engine B as defined in SPEC.

## Scoring (fixed now)
- WER with jiwer after lowercasing and removing punctuation.
- Leakage: words in the target lane that match the other talker's close-talk truth and not the target's, divided by all target-lane words.
- Time: end of the spoken clip to the target caption on screen (from logs).
