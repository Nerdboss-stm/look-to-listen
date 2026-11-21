# DESIGN.md: how Look to Listen looks

The screen has one job. It shows who we listen to, what they said, what the room said and how far behind we are. Polish only what makes that faster to read from 5 m.
SPEC.md decides what exists. DESIGN.md decides how it looks.

## Concept: the spotlight
- The room is dim. The person you look at is lit.
- The target face gets a bright ring, and the camera image darkens around it. Other faces keep a thin ring in their own color.
- A thin line joins the target ring to the right lane, so the room sees which face owns those words. Build it after D1 to D4 pass.

## Stage and grid
- Design a fixed 1920x1080 stage and scale it to fit the window. Letterbox. Never reflow.
- Outer margin 24 px. Gutter 16 px.
- Main column 1440 px. Side strip 416 px.
- Camera: main column, top, 1440x640, object-fit cover. The overlay canvas uses the same transform as the video.
- Lanes: main column, bottom, two columns of 712x376. Left "WHAT THE MICROPHONE HEARS". Right "LOOK TO LISTEN".
- Side strip, top to bottom: DELAY, ENGINE, AGENT, MEMORY, ROBOT.
- Wall clock: top right of the camera, 28 px mono, seconds shown. It proves the feed is live.
- LEAKAGE sits in each lane's header, next to the words it measures.

## Tokens
| Token | Dark (default) | Bright room (press B) |
| --- | --- | --- |
| bg | #07090C | #FFFFFF |
| panel | #10141A | #F2F4F7 |
| hairline | #232A33 | #D0D5DD |
| text | #FFFFFF | #0A0C10 |
| label | #A9B4C2 | #475467 |
| raw words before attribution | #D0D7E0 | #344054 |
| speaker A | #FFB000 | #B25E00 |
| speaker B | #4CC3FF | #0060A8 |
| speaker C | #FF7AB6 | #B0245F |
| warn | #FFD60A | #8A6D00 |
| bad | #FF453A | #C4140A |
- Color is never the only signal. Each face and each of its lines carries a letter badge: A, B or C.
- A face without consent: dashed gray ring, badge "?", and no captions for it.

## Type
- Words: Atkinson Hyperlegible Next. Numbers: Atkinson Hyperlegible Mono, tabular. Both self-hosted from fontsource packages, no CDN. If a package is missing, use Inter and JetBrains Mono.
- Sizes at 1920x1080: target lane 44 px, raw lane 38 px, lane headers 22 px caps with 0.08em tracking, counters 56 px, side labels 20 px.
- Nothing on the stage under 18 px.
- Captions: line height 1.25, left aligned, at most 2 lines of interim words.

## Camera overlay
- Target ring: 6 px in the target's color, a 2 px white inner stroke, a 24 px soft glow. Badge above it: "A · LISTENING".
- Other faces: a 2 px ring at 60% opacity in their color, with their badge.
- Dim: a radial 35% black layer over everything outside the target's face box. No dim when there is no target.
- One canvas, drawn with requestAnimationFrame. No model calls in the draw loop.

## Lanes
- Newest line at the bottom. Older lines move up and fade to 80%, 60% and 40%.
- Interim words at 70% opacity, final words at 100%. Words fade in over 120 ms. No per-letter typing effect.
- Raw lane: words in their speaker's color once attributed, the "raw words" color before. That is the jumble.
- Target lane: white words. The header shows the target's badge and color chip.
- Each lane header shows its LEAKAGE at the right, 56 px, from the live logs.
- Empty state: "Waiting for speech" in the label color, 22 px.

## Side strip
- DELAY: two bars, VOICE and CAPTIONS, with the budget marked at 1.5 s and 3 s. Value at 56 px. Text color within budget, warn over budget, bad over twice the budget. Updates twice a second.
- ENGINE: "B-GPU · RTX 4090 · 129 ms", with the live gpu_ms. On failover it reads "ENGINE A · GEMINI ONLY" and its outline flashes once for 1 s. That is the only flash on the screen.
- AGENT: the last 4 events at 20 px. Hook denials in the bad color, with the reason.
- MEMORY: the last question, its answer and its time.
- ROBOT: a small live frame with the reach point as a crosshair, and the command text. A denied command is struck through in the bad color.

## Motion
- Target switch: the ring and the dim move to the new face over 300 ms, ease-out. The lane badge crossfades over 150 ms.
- A LIVE dot blinks at 1 Hz. Nothing else moves on its own.
- prefers-reduced-motion: every transition is instant.

## Never
- Gradient or glassy backgrounds, blur behind text, purple-blue "AI" glows, emoji.
- Drop shadows on panels, corner radius over 8 px, icons without a label, a third typeface.
- Centered caption text, placeholder text in the demo state.
- Any number that does not come from the live logs or the CSV files.

## END CARD
- Full screen on bg. "Look to Listen. Hear only who you look at." at 64 px.
- Three numbers at 120 px, each with a 24 px label: leakage (raw against ours), delay, clips.
- One line: where it breaks. Repo link and QR at the bottom right.

## Checks (S2 runs them and writes the evidence in PROGRESS.md)
- D1 Sizes: at 1920x1080, a DOM script finds no visible text under 18 px, target captions at 44 px or more, counters at 56 px or more.
- D2 Contrast: computed from the tokens, captions 7:1 or more and labels 4.5:1 or more, in both palettes.
- D3 No shift: counters and DELAY keep their width while values change. Layout shift 0 over 30 s.
- D4 Overlay: 30 fps or more with 3 faces, over 10 s.
- D5 Screenshots at 1920x1080 and 1280x720, saved in evals/ui/. The 1280x720 one still reads.
- D6 Projector: a photo of the projected screen from 5 m. The target lane reads (E14).
