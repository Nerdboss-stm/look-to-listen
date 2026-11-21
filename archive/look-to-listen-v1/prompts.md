# prompts.md: gate tests and baselines (Look to Listen)

Run these at the start of the event (E1 to E3). Time every call. Log every run in gate_log.csv.
G1 runs on the laptop. G2, G3 and G4 run in AI Studio or a throwaway script. G5 runs in a throwaway folder outside this repo.

## G1 RAVEN on this laptop (the deciding gate)
- Clone github.com/Bose/RAVEN. Follow its README for the real-time demo with the laptop webcam and microphone.
- Two people talk at once, both in frame, about 1 m away. Point the target at one, then the other.
- Record: install time, whether the pretrained checkpoints download, real-time factor (processing time divided by audio time), CPU and memory use, and whether a listener hears the other voice clearly lower in 4 of 5 tries.
- Pass: real-time factor under 1.0 and 4 of 5 tries clearly lower. If it fails, the 10:00 decision is FB1.

## G2 Captions (gemini-4-hydrogen-live, else gemini-4-hydrogen at thinking low)
- Live: stream 16 kHz mono PCM of one person reading 5 sentences. Turn on input transcription if the model offers it.
- Chunked: the same audio in 1 s chunks with this prompt:
Transcribe the speech in this audio exactly, word for word. Return only the words. If there is no speech, return an empty string.
- Record WER against the read text and latency from end of speech to text. Pass: WER at or under 10%, p50 at or under 1.5 s. Write down the exact model id that worked.

## G3 Decisions API speaking (gemini-decision-1)
- 20 clips of 1 s, each a mouth crop video plus its audio, 10 speaking and 10 silent (the other person talks).
- Question: "Is the person in this video speaking right now?" Closed set: yes, no.
- Record p(yes), truth, latency. Pass: p50 at or under 300 ms, at least 18 of 20 right at 0.9. Write down the input format that worked.

## G4 Gemini-only targeting (gemini-4-hydrogen, thinking low)
- 5 two-talker clips of 5 s, with a box drawn on the target face in every frame.
- Prompt:
Two or more people may be talking at the same time. Transcribe only the words spoken by the person inside the green box. Use their lip movements to decide which words are theirs. Return only those words. If the person in the box is silent, return an empty string.
- Score leakage (share of returned words that the other person said) and WER against close-talk truth. Pass for FB1: average leakage at or under 25%.

## G5 Managed Agent
- Does it accept gemini-4-neon as its model? If not, can the sandbox call the Gemini API with a key injected by the egress proxy?
- Are client-side function tools supported? Exact tool names in the run log, for hook matchers.
- One run with a pre_tool_execution command hook that denies once with a reason: does the agent see the reason and retry on its own?
- Can a scheduled trigger start a run every 30 minutes?

## Baselines (event day, same audio as ours)
- B0, raw captions: the mixed microphone audio through the same captioner as G2, no targeting.
- B1, Gemini only: the G4 prompt on 1 s AV chunks with the target box, no enhancer, no leakage guard.
- B2, ours: the full pipeline in SPEC.

## Scoring (fixed now)
- WER with jiwer after lowercasing and removing punctuation.
- Leakage: words in the target lane that match the other talker's close-talk truth and not the target's, divided by all target-lane words.
- Latency: end of a spoken word (from the close-talk track) to its caption on screen (from logs).
