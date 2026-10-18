---
version: 1
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: []
---

# Surface brief: Keystone workbench (web/index.html)

## Scope and mode
Operate. One screen, the Keystone workbench: ask the agent, watch the counterfactual re-solve, read the evidence, act. It is the first thing a judge sees in the demo video and in the live link.

## Audience, task, proof, constraints
Engineering leader planning succession. Task: pick a person, see what breaks if they leave, see who steps in, get a verified plan and ready-to-review artifacts. Proof on screen: real FalkorDB public PR data (62 people, 114 modules, snapshot 2026-10-15), live MCP tool calls with measured milliseconds, public PR links as sources. Constraints: no invented numbers or names, actions are dry runs, zero em-dashes and no decorative dots (design-taste rules), one accent, one corner scale (none), readable at 1080p in a screen-share, phone width restacks.

## Chosen direction and memorable moment
Contingency Console (a power-system N-1 single-line diagram), approved comp C at `.impeccable/mocks/comp-c.png`: case tabs, a dense diagram, a results table, an agent log. Memorable moment: switch BASE to N-1 and the removed person's feeders trip (hollow breakers, dashed red-orange), every busbar they held turns amber with its retained percentage, and the log streams the MCP calls that computed it.

## Unresolved decisions
- How a person is chosen: click a source symbol, a row in the results table, or type in the command line (all three, same state).
- How the CODEOWNERS diff and issue drafts open from the log without adding chrome to the first viewport (an in-place sheet over the diagram, closed with Escape).
- The comp's log timestamps and sign-off captions are placeholders: use real call times and real step summaries.

## Direction contract
THESIS: The organisation is a power system. People are sources, modules are busbars, and a departure is an N-1 study you run, not a risk you feel. It refuses the dark KPI-tile dashboard and the chat-first layout.
OWN-WORLD: Off-black blue-grey ground, pale-grey single-line linework, one amber for stress and selection, red-orange only for tripped or orphaned. Condensed technical sans for labels, tabular mono for every number. No radii, gradients, glow or shadows; 1px rules. Recognizable with all content removed as an empty one-line-diagram frame.
STORY: The leader sees that knowledge is concentrated, believes the counterfactual because the log shows the tool calls and each row links a public source, and acts by approving a verified plan.
FIRST VIEWPORT: Top bar (wordmark, graph selector, Sandbox) over case tabs BASE, N-1 person, N-1 + PLAN. Left 68 percent: one single-line diagram, eight sources across the top, seven busbars below, results table beneath. Right 32 percent: AGENT LOG of MCP calls with the Analyst, Planner, Reviewer trail. Full-width command line at the foot. Primary actions: the case tabs and the command line.
FORM: Single-line-diagram workbench (Contingency Console), candidate 1 of my ordered list (the pick), seed c02b9f78.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
