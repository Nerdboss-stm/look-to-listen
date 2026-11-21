# prompts.md: Friday gate tests and event-day baselines (Eyes Closed)

Time every call. Log every run in gate_log.csv. Use your backpack dumped on the board exactly as it falls.
G1 to G3 and G6 run in AI Studio. G4, G5 and G8 run in a throwaway folder outside this repo.

## G1 Open scan (gemini-4-hydrogen, thinking low)
Input: the photo from the mast.
Prompt:
List every distinct object you can see and point to each one. Use specific names, for example "USB-C charger" rather than "cable". Return JSON only: [{"label": "<short name>", "point": [y, x]}] with y and x normalized to 0 to 1000.
Score: write your own list first. Found = on your list and pointed at correctly. Wrong = a label that does not match.
Pass: at least 90 percent found, at most 10 percent wrong, p50 at or under 3 s. Write down the exact output format.

## G2 Holding (gemini-4-hydrogen, thinking low)
Input: a photo of your hand holding one thing from the pile.
Prompt:
What is the person holding? Return JSON only: {"holding": "<short name or none>", "confidence": <0 to 1>}.
Pass: at least 9 of 10.

## G3 Label read (gemini-4-hydrogen, thinking medium)
Input: a container held up toward the camera at about 40 cm.
Prompt:
Read the size printed on the container in the hand. Return JSON only: {"printed": "<text as printed>", "fl_oz": <number or null>, "ml": <number or null>}. Use null if you cannot read it.
Pass: at least 8 of 10.

## G6 Plan (gemini-4-neon, Google Search grounding on)
Input: the pile photo plus one errand. Use 10: your real trip, gym tonight, a coffee meeting, recycling, a day at the office, others you think of, and 3 impossible ones ("fold my shirts", "assemble this", "cook dinner").
Prompt:
Errand: "<errand>". Using only objects visible in this photo, decide what goes in the bag and what stays home. Moving objects only: no folding, tying, assembling, cooking or tools. If the errand needs those, answer "cannot" and say why. Cite a source URL for any rule you apply. Return JSON only: {"status": "doable" | "needs" | "cannot", "plan": [{"object": "<name>", "zone": "bag" | "stays", "why": "<one line>", "rule_url": "<url or null>"}], "missing": ["<object>"], "reason": "<one sentence>"}.
Pass: at least 8 of 10 match your own judgment.

## G7 Hydrogen live stream
In AI Studio's live streaming mode, check whether gemini-4-hydrogen is offered. If it is, point the phone camera at the pile, pick up 5 things one at a time, and ask it to name each. Note the delay and how many it gets right.

## G8 Decisions API (gemini-decision-1)
Follow the Decisions API quickstart. For each of 20 hand photos, ask one yes or no question: "Is the person holding the <object>?" Use 10 where the true answer is yes and 10 where it is no.
Record: p(yes), the truth, latency.
Pass: p50 at or under 300 ms, at least 18 of 20 correct at the 0.9 threshold. Count abstains (between 0.4 and 0.9) separately.

## G4 Managed Agent hook loop
1. Make a minimal agent whose only job is: write plan.json containing {"ok": true}, then call the release step.
2. Add a pre_tool_execution command hook on the release step. It denies the first call with the reason "check_x: this object cannot go in that zone" and allows the second.
3. Confirm the agent sees the reason and retries on its own.
Record: wall time, cold start, the exact tool names in the run log.
Pass: the retry happens without help, total under 120 s.

## G5 Questions
- Does the agent accept gemini-4-neon as its model? If not, can the sandbox call the Gemini API with a key injected by the egress proxy?
- Are client-side function tools supported?
- Can the Files API pass errand.json and scan.json into a run?

## Baselines (event day, same inputs as Eyes Closed)
- B1, one call (gemini-4-hydrogen): the pile photo plus: "Errand: '<errand>'. Which objects go in the bag and which stay home? Return JSON only: [{"object": "<name>", "zone": "bag" | "stays"}]."
- B2, live guiding (gemini-4-hydrogen in AI Studio's live streaming mode, or Gemini Live if Hydrogen does not stream): "I am blindfolded. Here is the errand: '<the errand, word for word>'. Guide my hands to do it with what is on this table." Give no other help. The observer logs the outcome in runs.csv and steps.csv.
