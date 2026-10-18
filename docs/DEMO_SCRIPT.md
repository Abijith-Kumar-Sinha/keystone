# Demo video script (about 2:45)

Record in your own voices. The rules ask for a video that shows the working project; nothing here is written for a text-to-speech voice. Record at 1080p. The workbench creates a private sandbox on your first question or plan, so nothing touches the base graph. Start from a fresh page load.

The moment the UI is built around: **remove a person, watch the wall re-solve, then watch the plan heal it.**

| Time | On screen | Say (rough, put it in your own words) |
|---|---|---|
| 0:00 | Landing page. The cells fall from 100% to 37, 45 and 60 and the red spokes tear; one cell stays a green 99. | "If your best engineer quits tomorrow, what breaks, and who steps in? Most teams guess. Keystone computes it from real pull-request history, in FalkorDB." |
| 0:12 | Click **Open the workbench**. | "This is FalkorDB's own public repositories: every merged PR, who wrote it, who reviewed it, which module it touched. It is a graph, and the graph does the thinking." |
| 0:22 | Workbench on Anchel123: five red cells, four green, **Orphaned 0, Fragile 21**. | "I take Anchel123 out. The browser app keeps 37 percent of its knowledge; 21 modules turn fragile." |
| 0:38 | Click **gkorland**. The wall re-solves; Orphaned jumps to 12. | "A different person, different damage. This is computed on a copy of the graph, `GRAPH.COPY`; the live graph is never touched." |
| 0:52 | Back to Anchel123. Type **Who steps in for Anchel123?** and press Enter. | "I ask in plain English. The agent picks a tool through MCP." |
| 1:05 | Read the answer line, then click **PROOF**: the path diagram (five candidates, dashed green into Anchel123, then his modules). Click the **TRACE** tab. | "barakb, who has reviewed 269 of his PRs, found by walking author, PR, module, reviewer. This is the path the answer was built from, and the trace shows the tool, the milliseconds and the named Cypher statements. The model never writes Cypher." |
| 1:22 | Close the sheet, click **Make the plan**. The green spokes appear, the numbers climb. The plan sheet opens: **Approved**. | "Three roles hand off only through graph state. The Planner simulates the pairing on a fork; the Reviewer reads the tasks back from the graph and re-verifies on a fresh fork. The browser app goes from 37 to 67 percent." |
| 1:58 | Click **Draft the patch**: the CODEOWNERS diff, then an issue. | "Then it acts: a CODEOWNERS patch against the repository's real file, and an issue with the evidence. A dry run; nothing is posted." |
| 2:12 | Type **who knows about kubernetes operators?** | "And when the answer is not in the graph, it says so instead of guessing." |
| 2:22 | A terminal (or Claude Code) running `claude mcp add --transport http keystone <url>/mcp`, then calling `keystones`. | "The same 15 tools are an MCP server, so Claude Desktop or Claude Code can drive it too." |
| 2:35 | Landing page, scroll to **It checks itself**. | "We replayed April's picks against what really happened by October: 95 percent came true, against 39 for a random pick. Honest note: a simple most-active rule also scores 95 in teams this small. The graph earns its place with the proof, the what-if and the checked plan." |
| 2:45 | Title card: repo URL, Graph Hacks, Track 01. | "Keystone, built on FalkorDB. Thanks for watching." |

## What the video must make visible (Track 01)

Say each focus area once, out loud, while its moment is on screen. The judges score these five.

| Focus | Where in the script |
|---|---|
| Multi-hop reasoning | 1:05: PROOF draws author, PR, module, reviewer. Optional 10 seconds: ask **How is Anchel123 connected to barakb?** for the two-hop `algo.SPpaths` chain |
| Graph queries and algorithms as agent tools | 1:05: TRACE shows the tool and the named Cypher; say that PageRank, label propagation and betweenness ran inside FalkorDB at load |
| Tool selection through MCP | 0:52 (the agent picks a tool, never writes Cypher) and 2:22 (an outside client lists the 15 tools) |
| Actions based on what the graph shows | 1:22 and 1:58: the three-role plan, the Reviewer's verdict, the CODEOWNERS patch and the issue |
| Explainable results | 1:05 PROOF and TRACE, 2:12 "not in the graph" |

## Before you record

- Fresh page load, so the sandbox is clean. Hide bookmarks and notifications.
- For the 2:22 shot use the live address, `https://keystone-2d8k.onrender.com/mcp`, and run the `claude mcp add` line once beforehand. Before the Host-header fix was deployed that address answered outside clients with HTTP 421, so confirm it lists 15 tools first.
- Run `scripts\preflight.ps1` first: it checks the graphs, the model, a question and a plan in about ten seconds.
- With the keys in `.env` the button at the bottom right says **MODEL** and the answers are written by the model (the TRACE tab says which one). Ask one free-form question (for example "which module is riskiest for the browser team?") to show the model choosing a tool. Without keys it says ROUTER, which also works on camera.
- Free model tiers limit requests per minute (Gemini allowed about seven questions a minute when we tested). Leave a few seconds between questions while recording. If the first model is limited, the backup model answers and then the router, so nothing breaks; TRACE shows who answered.
- Every number you speak must be on screen. The figures above come from the 2026-10-15 snapshot; read them off the screen if they differ.
- Mention the AI-assistance disclosure in a sentence if you like; it is also in the README.
