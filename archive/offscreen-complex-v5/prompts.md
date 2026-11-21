# prompts.md: gate tests and baselines (Offscreen)

Run these at the start of the event (E6). Time every call. Log every run in gate_log.csv.
G1, G9 and G10 run in AI Studio. G5, G8 and G11 run in a throwaway folder outside this repo.

## G1 Open scan (gemini-4-hydrogen, thinking low)
Input: one photo from the mast of your backpack dumped on the board.
Prompt:
List every distinct object you can see and point to each one. Use specific names, for example "USB-C charger" rather than "cable". Return JSON only: [{"label": "<short name>", "point": [y, x]}] with y and x normalized to 0 to 1000.
Pass: at least 90 percent found, at most 10 percent wrong, p50 at or under 3 s. Write down the exact output format.

## G8 Decisions API (gemini-decision-1)
Follow the Decisions API quickstart. 20 photos, one yes or no question each ("Is the person holding the <object>?", "Is the <object> on the board?"), 10 true and 10 false.
Record p(yes), truth, latency. Pass: p50 at or under 300 ms, at least 18 of 20 right at 0.9.

## G9 Argon memory (gemini-4-argon)
Input: a 10 minute phone video of your table from above, during which you move, add and remove 10 things. Write down what you did and when, before asking anything.
Ask 5 questions, one per call: "Where is the <object> now?", "When was the <object> moved, and where did it go?", "What was added between minute 3 and minute 6?"
Record answers, times, latency. Pass: at least 4 of 5 right with a time within 30 s. Also note the longest video one call accepts.

## G10 Event labels (gemini-4-hydrogen)
Input: 10 clips of about 6 s cut from the G9 video around each change.
Prompt:
What changed on the table in this clip? Return JSON only: {"type": "added" | "removed" | "moved" | "picked" | "placed", "object": "<short name>", "where": "<short place>"}.
Pass: at least 9 of 10 right.

## G11 Shop MCP
Connect any MCP client to https://mcp.shop.com (read https://mcp.shop.com/skill.md first). Run search_catalog for "65W USB-C laptop charger".
Record: results, whether sign-in with Shop is needed for checkout, and whether checkout needs a real card. Do not complete a purchase.

## G5 Managed Agent
- Does it accept gemini-4-neon as its model? If not, can the sandbox call the Gemini API with a key injected by the egress proxy?
- Are client-side function tools supported? Can it connect to an MCP server?
- Exact tool names in the run log, for hook matchers.
- One run with a pre_tool_execution command hook that denies once with a reason: does the agent see the reason and retry on its own?

## Baselines (event day, same inputs as Offscreen)
- M0, memory: raw gemini-4-argon with as much raw footage as one call accepts, plus the question as asked.
- L0, live jobs: raw gemini-4-hydrogen in AI Studio's live streaming mode (or Gemini Live if Hydrogen does not stream): "Here is the goal: '<goal, word for word>'. Guide my hands to do it with what is on this table." No other help. The observer logs the outcome in runs.csv and steps.csv.
