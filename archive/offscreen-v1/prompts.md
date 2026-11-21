# prompts.md: Friday gate tests

Run G1 to G3 in AI Studio with gemini-4-hydrogen. Thinking low unless a test says otherwise.
Time every call. Log every run in gate_log.csv.

## G1 Pointing
Input: the top-down kit photo.
Prompt:
Point to each of these items if you can see it: laptop, laptop USB-C charger, phone cable, power bank, earbuds case, travel bottle, full-size bottle, toothpaste, wallet, keys, sunglasses, umbrella, socks, T-shirt, HDMI adapter, mouse or clicker, TV remote, notebook, snack bar, mug.
Return JSON only: [{"label": "<item>", "point": [y, x]}] with y and x normalized to 0 to 1000. Leave out items you cannot see.
Score: correct if the point lands on the item. Pass: at least 18 of 20, p50 at or under 2.5 s.
Also write down the exact output format Hydrogen returns.

## G2 Holding
Input: a photo of a hand holding one kit item.
Prompt:
Which one of these items is in the person's hand: [the same list], or none? Return JSON only: {"holding": "<item or none>", "confidence": <0 to 1>}.
Pass: at least 9 of 10. Include the USB-C charger, the phone cable, the clicker and the TV remote.

## G3 Label read (thinking medium)
Input: a photo of a container held up toward the camera at about 40 cm.
Prompt:
Read the size printed on the container in the hand. Return JSON only: {"printed": "<text as printed>", "fl_oz": <number or null>, "ml": <number or null>}. Use null if you cannot read it.
Pass: at least 8 of 10.

## G4 Managed Agent hook loop (throwaway folder, not this repo)
1. Make a minimal agent whose only job is: write plan.json containing {"ok": true}, then call the release step.
2. Add a pre_tool_execution command hook on the release step. It denies the first call with the reason "check_power_bank: a power bank cannot go in the checked bag" and allows the second.
3. Confirm the agent sees the reason and retries on its own.
Record: wall time, cold start time, the exact tool names in the run log (you need them for matchers).
Pass: the retry happens without help, total under 120 s.

## G5 Questions
- Does the agent accept gemini-4-hydrogen as its model?
- Are client-side function tools supported (our backend executes them and returns results)?
- Can the Files API pass scan.json and emails.json into a run?

## Raw arm (event day, AI Studio live stream, gemini-4-hydrogen)
Paste the flight email, then say:
"I am blindfolded. Guide my hands to pack everything I need for this trip into the carry-on on my left or the checked bag on my right. Follow current TSA rules."
Give no other help. The observer logs the outcome in trials.csv.
