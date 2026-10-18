# Submission answers (copy and paste)

Everything the WeMakeDevs form is likely to ask, in the order the rules list it. Fill the three marked links, then paste.

| Field | Answer |
|---|---|
| Project name | Keystone |
| Track entered | **Track 01: Agents That Act on Connected Data** (only this one) |
| Public repository | https://github.com/Abijith-Kumar-Sinha/keystone |
| Live deployment | https://keystone-2d8k.onrender.com (free instance: open it a minute before judging starts) |
| Demo video | **FILL IN: your YouTube (unlisted) link** |
| Blog post (side prize, optional) | **FILL IN if you publish it** (draft in `docs/BLOG.md`) |

## One line

An MCP-native agent that answers "if this person leaves, what breaks, and who steps in?" from real pull-request history held as a graph in FalkorDB.

## Short description

Keystone reads the merged pull requests of FalkorDB's own public repositories (and Pallets') as a graph: who authored and reviewed what, in which module. An agent with 15 human-written graph tools over MCP then finds the people a codebase cannot lose, simulates a departure on a `GRAPH.COPY` fork of the live graph, finds who can really step in, and turns an approved plan into a CODEOWNERS patch and issue drafts, with the path behind every answer.

## Long description

**The problem.** Every engineering leader has asked what breaks if a key engineer leaves. The usual answers are a gut feeling or a "bus factor" number with nothing behind it.

**What it does.** Every merged pull request is a fact: who wrote it, who reviewed it, which module it touched. Keystone turns those facts into `KNOWS` edges (authored 1.0, reviewed 0.4, weighted by the share of files in the module, decayed with a 365-day half-life) and computes bus factor, how load-bearing each module is, and who bridges teams. The agent then:

1. **Finds** where knowledge is concentrated (`risk_scan`, `keystones`, `module_risk`).
2. **Runs the counterfactual.** `what_if_leaves` forks the graph with `GRAPH.COPY`, deletes the person on the fork, recomputes the same statistics and diffs them. The live graph is never touched (113 ms median on the real data).
3. **Finds who can step in**, by multi-hop evidence: who already reviewed the leaver's PRs, and who knows modules that change together with the target (`successors`, `path_between`).
4. **Acts.** Three roles hand off only through graph state: an Analyst runs the what-if, a Planner simulates a pairing plan on a fork and writes a Decision with Tasks, and a Reviewer reads the tasks back from the graph and re-verifies them on a fresh fork. An approved plan becomes a CODEOWNERS patch diffed against the repository's real file, and an issue per pairing. All of it is a dry run.
5. **Remembers and checks itself.** Decisions and tasks are ordinary nodes; a later session asks `changes_since` to see which recommendations really happened.

**Why FalkorDB is central.** The product stops working without it. `algo.pageRank`, `algo.labelPropagation` and `algo.betweenness` run in the database at load and are written back as properties; `algo.SPpaths` finds the chain of shared knowledge between two people; `GRAPH.COPY` is the counterfactual engine; read tools run through `GRAPH.RO_QUERY`; one graph per organisation plus a private fork per visitor.

**Explainable and honest.** Every answer carries the nodes and edges it was built from (the PROOF button), the named Cypher statements and the public PR links (TRACE). Four explicit outcomes: `answered`, `from_memory`, `not_in_graph`, `unknown_entity`. The model only chooses tools and never writes Cypher, and a person named in its prose must appear in the tool rows or the prose is thrown away. On 20 never-tuned questions a model chose the right tool 85% of the time (the keyword fallback 65%) with 100% grounded answers. A backtest of an April plan against October reality found its picks came true 95% of the time against 39% for random, and says plainly that a simple "most active" rule ties it in teams this small.

## How to run it

`docker compose up --build`, then open http://localhost:8000 (FalkorDB Browser on :3000). Or use the live deployment above. The MCP endpoint is `<live address>/mcp`. Full setup, the graph data model and every query are in the README and `docs/QUERIES.md`.

## Data

Merged pull requests of public GitHub repositories (FalkorDB's organisation and Pallets), read through the public API. Only public GitHub logins appear; no email addresses are requested or stored. The snapshots are committed in `data/snapshot/`.

## AI assistance disclosure (required)

The code in this repository was written with an AI coding assistant, Claude Code (Anthropic), working under the direction of the team during the event window (Oct 17 to 18, 2026). Interface comps were generated with Figma AI and used as visual targets; the interface itself is hand-built HTML, CSS and JavaScript. The product's own agent uses a language model (Gemini, with Groq as a backup) only to choose tools and phrase answers from tool results. The team is responsible for the architecture, security, correctness and every claim, and can explain the graph model, the queries and the decisions.

## Team and who did what

**FILL IN, one line per person, in your own words.** Example: "Abijith Kumar Sinha: product idea, review and direction of every decision, data choice, demo video, can explain the graph model, queries and architecture."

## Anticipated questions

- *Is the graph decoration?* No: the counterfactual, the algorithms, the plan verification and the memory all run in FalkorDB.
- *Does it work without an API key?* Yes, a deterministic router answers and the UI says so; a model is much better (see the evaluation in the README).
- *Can it write to a real repository?* Not by default. Posting an issue needs an operator token on top of an explicit confirmation.
