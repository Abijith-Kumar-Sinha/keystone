---
name: Keystone
description: A broadcast has been interrupted to ask what breaks when one engineer leaves; Stand By, a test-card world of color bars, big numbers and hub-and-spoke cells.
colors:
  ink: "#0b0b0f"
  ink-2: "#131318"
  paper: "#f4f4f2"
  dim: "#9aa0a6"
  mid: "#858a92"
  line: "#2b3037"
  signal-red: "#ff4b4b"
  signal-green: "#3ddc6c"
  bar-white: "#d9d9d8"
  bar-yellow: "#e3d20f"
  bar-cyan: "#14b4e3"
  bar-green: "#1fc13b"
  bar-magenta: "#e024d7"
  bar-red: "#ee2b2b"
  bar-blue: "#0b1ae5"
typography:
  display:
    fontFamily: "Bebas Neue, Oswald, Arial Narrow, sans-serif"
    fontSize: "calc(100cqw / 1536 * 104)"
    fontWeight: 400
    lineHeight: 0.85
    letterSpacing: "-0.014em"
  band-heading:
    fontFamily: "Bebas Neue, Oswald, Arial Narrow, sans-serif"
    fontSize: "clamp(44px, 6vw, 96px)"
    fontWeight: 400
    lineHeight: 0.9
    letterSpacing: "0.01em"
  evidence-number:
    fontFamily: "Bebas Neue, Oswald, Arial Narrow, sans-serif"
    fontSize: "clamp(72px, 9vw, 150px)"
    fontWeight: 400
    lineHeight: 0.8
  readout-number:
    fontFamily: "Bebas Neue, Oswald, Arial Narrow, sans-serif"
    fontSize: "clamp(88px, 11vw, 190px)"
    fontWeight: 400
    lineHeight: 0.82
  cell-number:
    fontFamily: "Bebas Neue, Oswald, Arial Narrow, sans-serif"
    fontSize: "clamp(34px, 3.7vw, 58px)"
    fontWeight: 400
    lineHeight: 1
  body:
    fontFamily: "Martian Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: "tabular-nums"
  label:
    fontFamily: "Martian Mono, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0.1em"
  button:
    fontFamily: "Martian Mono, ui-monospace, monospace"
    fontSize: "14px"
    fontWeight: 700
    letterSpacing: "0.03em"
rounded:
  none: "0"
spacing:
  xs: "6px"
  sm: "12px"
  md: "18px"
  lg: "22px"
  xl: "clamp(20px, 4vw, 60px)"
  band: "112px"
components:
  button-primary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  cell:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
  source-chip:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    padding: "24px 22px"
  source-chip-current:
    backgroundColor: "#1b0f13"
    textColor: "{colors.signal-red}"
  sheet:
    backgroundColor: "{colors.ink-2}"
    textColor: "{colors.paper}"
    width: "560px"
  command-line:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    padding: "16px 22px 18px"
  mode-button:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.dim}"
    padding: "7px 10px"
---

# Design System: Keystone

## Overview

**Creative North Star: "Stand By"**

A broadcast has been interrupted to ask one question. The system is a test card: near-black ink, paper white, one signal red for what breaks, one green for what holds, and SMPTE color bars as the single decorative signature. Display type is condensed Bebas Neue caps; everything else is Martian Mono at condensed width (font-stretch 75%). It is recognizable with all copy removed: a tall strip of color bars beside a wall of hub-and-spoke cells.

Text is minimal by rule: one headline, one primary button, big numbers, names only where a number needs one. Numbers are the content. Frames are flat 1px lines, with no radii and no shadows. The only gradients are tape noise on the bars and the hard-stop bar strip under the workbench wordmark. The landing first viewport is a 1536x864 frame that scales with width; the workbench is a fluid tool.

**Key Characteristics:**
- Color bars are the only decorative color; red and green are the only semantic colors.
- Big Bebas numbers carry state; mono carries names, timecode and tools.
- Flat, square, 1px `line` frames. No radius, no shadow.
- Motion is signal degradation (tape noise, tracking tear, damped needle) and is a still frame under reduced motion.

## Colors

Muted ink ground, paper type, two signals, seven bars.

### Primary
- **Signal Red** (`signal-red`): removed, cut, fragile, errors, the current source, selection background. Always paired with a number, a label or a dashed spoke, never alone.
- **Signal Green** (`signal-green`): locked, healed, covered, writes to the graph (tool names, `>` prompt, diff additions, the headline evidence number, the orphaned/fragile readout when good).

### Neutral
- **Ink** (`ink`): page ground, cell ground, input ground.
- **Ink Raised** (`ink-2`): the sheet only.
- **Paper** (`paper`): text, primary button fill, focus ring, soft-state numbers.
- **Dim** (`dim`): secondary text, inactive tabs, mode buttons, evidence captions.
- **Mid** (`mid`): placeholder and notes; chosen and checked for AA contrast on ink.
- **Line** (`line`): every 1px frame and divider.

### Bars (signature, never used for UI state)
`bar-white`, `bar-yellow`, `bar-cyan`, `bar-green`, `bar-magenta`, `bar-red`, `bar-blue` appear only as the landing strip (canvas, with tape noise) and the 148x4px strip under the workbench wordmark. The cyan also appears in the hero's one-frame chromatic split.

### Named Rules
**The One Accent Rule.** Red means broken or removed; green means held or written. Nothing else is saturated outside the bars.
**The Bars Stay Decorative Rule.** The seven bar colors never encode state and never appear on controls.

## Typography

**Display Font:** Bebas Neue (Oswald, Arial Narrow, sans-serif), self-hosted woff2.
**Body/Label/Mono Font:** Martian Mono variable (ui-monospace fallback), `font-stretch: 75%`, tabular numerals.

**Character:** Condensed broadcast caps shouting numbers over a quiet, narrow technical mono.

### Hierarchy
- **Display** (400, 104 comp-px scaled by `--u`, 0.85, -0.014em, uppercase): the one landing headline, three lines; 70px on phone.
- **Band heading** (400, clamp 44-96px, 0.9, uppercase): "Three steps", "15 tools over MCP", "It checks itself".
- **Readout number** (400, clamp 88-190px, 0.82): workbench totals, green, red when `data-bad`.
- **Evidence number** (400, clamp 72-150px, 0.8): three proof numbers; step numerals use clamp 64-128px.
- **Cell number** (400, 73 comp-px landing; clamp 34-58px workbench, 38px phone): module percentage, colored by state.
- **Body** (400, 16px, 1.4): note text, max 62ch, `mid`.
- **Label** (500, 12-15px, 0.08-0.1em, uppercase): channel and tab buttons, timecode, mode buttons.
- **Source** (400, clamp 18-27px mono, condensed): names in the sources list.
- **Command** (400, clamp 20-28px mono): the command line input.

### Named Rules
**The Number Is The Headline Rule.** If a thing can be said as a big number, do not say it as a sentence.

## Layout

Landing: a position-absolute frame whose every size is a multiple of `--u` (1 comp pixel = 100cqw/1536); left 29% color strip, right a headline, one button, four cells in a 4-column grid with a 13u gap. Below it, bands with `padding 64px clamp(20px,4vw,60px)` (112px block at 1100px+), 1px top rules, a 3-column steps grid and a 3-column evidence grid (gap clamp 20-48px), and an auto-fill tools grid (min clamp 150-260px) with 1px row rules.

Workbench: `100dvh` grid of top bar (56px), main, bottom (command line). Main is three columns: sources `clamp(150px,15vw,232px)`, a 3x3 wall of cells with 1px dividers, readout `clamp(170px,17vw,260px)`.

Responsive:
- At 900px and below the workbench becomes a document flow: sources become a horizontal scroll row of tabs (the only intended horizontal scroll, inside the row), readout a 2-column block with the plan button full width, the wall 2 columns of 220px rows, the command line sticky at the bottom and wrapping, the sheet full-screen.
- At 800px and below the landing frame becomes a flex stack (bars 96px, "please stand by" tag overlapping the strip, headline 70px, full-width button 52px, cells a 2x2 wall of min 260px, steps and evidence one column). The tear label inside cells is hidden; the red dot and torn spoke still say it. No horizontal page scroll.

## Elevation & Depth

Flat. No box-shadows anywhere. Depth is conveyed by 1px `line` frames, the raised `ink-2` sheet with a left border, a static film grain tile over the landing frame (alpha up to 26/255), and the single `text-shadow` red/cyan split on the headline during a glitch frame.

### Named Rules
**The Flat Frame Rule.** Surfaces are separated by a 1px line or by a tone step (`ink` to `ink-2`), never by a shadow or radius.

## Shapes

Square everywhere (radius 0). Borders are 1px `line`. Selection and state are shown with a 4px rule (source chip left border; bottom border on phone), a 2px underline (tabs, channels), or color. The only round forms are the diagram's dots. Focus is a 2px paper outline offset 3px.

## Components

### Buttons
- **Primary:** paper fill, ink text, 1px paper border, mono 700 at 0.03em, no radius, heights 46 to 52px, landing CTA 5.4% of frame.
- **Hover:** inverts to ink fill and paper text over 160ms. **Active:** 1px down. **Disabled:** 0.4 opacity, not-allowed.
- **Mode button (ROUTER, TRACE):** transparent, 1px line border, dim text, 12px mono 500, hover to paper border and text; 0.35 opacity disabled.

### Cell
Square 1px-framed ink tile: module name (mono 12.5 comp-px, top left), big Bebas percentage colored by state, the hub diagram filling the lower 62% (landing) or 72% (workbench). States: locked (green number, small padlock beside it), cut (red number, padlock hidden), soft (paper number), healed (green). Workbench cells enter with a 360ms top-down clip-path roll.

### Hub diagram (signature)
One diagram everywhere: a grey hub (r 26) with one spoke per holder (max 9), dot radius from share (6.5 to 13). The removed holder sits at the right just above horizontal as a red dot with a red spoke, dashed `3 5` at 0.55 opacity when cut, name beside it and tear bars above and below. Planned successors are green. Titles on dots carry name and share.

### Source chip
Full-width mono row in the sources list. Hover `#15151b`. Current (`aria-current`): red text, `#1b0f13` fill, 4px red left border (red bottom border on phone).

### Readout
Two stacked Bebas numbers (orphaned, fragile) with a Bebas label, green by default and red when bad, then the primary "Make the plan" button.

### Command line
Bottom bar: green `>` prompt, borderless transparent input with block caret and `mid` placeholder, then mode buttons. A two-line clamped status line above it: paper, `dim` when busy, red on error.

### Sheet
A right-hand `dialog` (560px, full-screen on phone) on `ink-2` with a 52px header of tab buttons (13px mono, 2px paper underline when selected) and Close. Body is 14px mono: rows with 1px dividers, a 40px Bebas verdict (green or red), 30px Bebas green figures, diffs (green add, red delete), keyform inputs with 1px line borders. Opens with a 260ms 24px slide and fade; Escape closes.

### Tools grid and evidence number
Tools: auto-fill mono names with 1px row rules; green entries write to the graph, with one footnote line. Evidence: a 1px top rule, a big Bebas number (green for the headline result), a `dim` caption.

### Motion
Timecode ticks every 40ms. Bars repaint at 12fps with scanline wobble, chroma smear, streaks, a roll band and a tracking tear. Numbers settle with a critically damped needle (w 7, up to 2s). The tear jitters thin red bars for 700ms. Color transitions 240ms, controls 160ms, easing `cubic-bezier(0.16,1,0.3,1)`. Under `prefers-reduced-motion` every effect is a settled still frame.

## Do's and Don'ts

### Do:
- **Do** let a big Bebas number carry each state and color it red or green.
- **Do** keep one headline and one primary button per screen; names only beside a number.
- **Do** keep every frame 1px `line`, radius 0, no shadows.
- **Do** keep `mid` (#858a92) as the lightest text on ink that is decorative or secondary; it was contrast-checked.
- **Do** show a settled state under reduced motion and restack phone layouts without page-level horizontal scroll.
- **Do** keep focus visible: 2px paper outline, 3px offset.

### Don't:
- **Don't** use a color bar color for state, controls or text.
- **Don't** add a third saturated accent, gradients, glow or decorative dots.
- **Don't** add paragraphs, captions or log blocks to the hero or the workbench default view.
- **Don't** use em-dashes in copy.
- **Don't** encode risk by color alone; keep the number, the dashed spoke or the label.
