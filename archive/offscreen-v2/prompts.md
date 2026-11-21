# prompts.md: Friday gate tests (v2, organic)

Run in AI Studio with gemini-4-hydrogen. Thinking low unless a test says otherwise.
Time every call. Log every run in gate_log.csv. Use your desk exactly as it is.

## G1 Open scan
Input: the top-down photo of your untidied desk.
Prompt:
List every distinct object you can see and point to each one. Use specific names, for example "USB-C charger" rather than "cable". Return JSON only: [{"label": "<short name>", "point": [y, x]}] with y and x normalized to 0 to 1000.
Score: make your own list first. Found = on your list and pointed at correctly. Wrong = a label that does not match the object.
Pass: at least 90 percent found, at most 10 percent wrong, p50 at or under 3 s.
Also write down the exact output format Hydrogen returns.

## G2 Holding
Input: a photo of your hand holding one random thing from the desk.
Prompt:
What is the person holding? Return JSON only: {"holding": "<short name or none>", "confidence": <0 to 1>}.
Pass: at least 9 of 10.

## G3 Label read (thinking medium)
Input: a photo of a container held up toward the camera at about 40 cm.
Prompt:
Read the size printed on the container in the hand. Return JSON only: {"printed": "<text as printed>", "fl_oz": <number or null>, "ml": <number or null>}. Use null if you cannot read it.
Pass: at least 8 of 10.

## G6 Triage
Input: the desk photo plus one errand (3 from friends, 3 impossible ones you write, the rest from friends or yourself).
Prompt:
Errand: "<errand>". Using only objects visible in this photo, can one person do this by moving objects to places? Moving only: no folding, tying, assembling, cooking or tools. Return JSON only: {"status": "doable" | "needs" | "cannot", "missing": ["<object>"], "zones": ["<where things go>"], "reason": "<one sentence>"}.
Pass: at least 9 of 10 match your own judgment.

## G4 Managed Agent hook loop (throwaway folder, not this repo)
1. Make a minimal agent whose only job is: write plan.json containing {"ok": true}, then call the release step.
2. Add a pre_tool_execution command hook on the release step. It denies the first call with the reason "check_x: this object cannot go in that zone" and allows the second.
3. Confirm the agent sees the reason and retries on its own.
Record: wall time, cold start, the exact tool names in the run log.
Pass: the retry happens without help, total under 120 s.

## G5 Questions
- Does the agent accept gemini-4-hydrogen as its model?
- Are client-side function tools supported?
- Can the Files API pass errand.json and scan.json into a run?

## Raw arm (event day, AI Studio live stream, gemini-4-hydrogen)
Say: "I am blindfolded. Here is the errand: '<errand as the sender typed it>'. Guide my hands to do it with what is on this table."
Give no other help. The observer logs the outcome in runs.csv.
