---
version: 1
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: ["web/workbench.html"]
---

# Surface brief: Keystone product page and workbench (web/index.html, web/workbench.html)

## Scope and mode
Persuade for the landing page (web/index.html), Operate for the workbench (web/workbench.html): one world, two surfaces. The landing page is what a judge sees first in the video and the live link; the workbench is the working agent. The approved comp for the landing hero is `.impeccable/mocks/comp-a.png`; the workbench screen the user chose is `.impeccable/mocks/comp-b.png`.

## Audience, task, proof, constraints
Engineering leader planning succession (primary); hackathon judges with a few minutes (secondary). Landing task: understand the question and the answer in five seconds, then open the workbench. Workbench task: pick a person, see which modules break, read the numbers, optionally ask in plain English. Proof on screen: real FalkorDB public PR data from the live API, measured milliseconds. Constraints: **text discipline is binding (the user said the first comps felt like slop): one headline, one primary button, big numbers, names only where a number needs one; no sub-paragraph, no captions, no log blocks in the hero or the workbench default view.** Also: zero em-dashes, no decorative dots, no eyebrow labels, one corner scale (none), reduced motion respected, phone width restacks.

## Chosen direction and memorable moment
Stand By (broadcast emergency alert), a dealt challenger from the third roll chosen by the user. Memorable moment: the four cells under the headline are live. The module cells the removed person held show a red spoke tearing away with a horizontal tracking glitch and a red percentage; the cells they did not hold stay locked green at 100 percent. In the workbench, choosing another person in the sources list re-tears the affected cells with damped number motion.

## Unresolved decisions
- Where the agent's tool calls live now that the hero has no log: a single reveal in the workbench (a crawl that opens on demand), not in the default view.
- How the CODEOWNERS diff and issue drafts open (a sheet over the wall, closed with Escape).
- Comp placeholders to replace with real data: the invented sign-off names and any tool name not in the MCP set.

## Direction contract
THESIS: A broadcast has been interrupted to ask one question. The page is a "please stand by" alert that shows, live, what breaks when one person is removed, and nothing that a picture already says. It refuses the dark KPI dashboard, the chat-first layout, and any paragraph that explains what the cells show.
OWN-WORLD: Near-black ground, muted SMPTE color bars as the only decorative color (a tall strip on the landing, a thin strip under the workbench wordmark), signal red for removed and fragile, one green for locked and healthy. Condensed grotesque caps for headlines and names, monospace for numbers and timecode. Flat 1px frames, no radii, no shadows, no gradients except tape noise. Recognizable with all copy removed as color bars beside a wall of hub-and-spoke cells.
STORY: A visitor reads one question, sees four cells answer it, understands that one departure leaves modules at 35 to 45 percent, and opens the workbench to try it on real data.
FIRST VIEWPORT: Top bar 64px: wordmark, GitHub link, Open workbench button, a running timecode. Left 30 percent: a tall color-bar strip with a small PLEASE STAND BY label at its foot. Right 70 percent: a three-line condensed-caps headline, one white button, then a row of four live module cells (module name, very large percentage, hub-and-spoke diagram, the first cell's red spoke tearing away). Primary action: Open the workbench.
FORM: Stand By, a dealt challenger (broadcast signal degradation), chosen over the assigned Explorable Page; third roll, seed 09dcf0cb.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
