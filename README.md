# Keystone

**An MCP-native agent that answers "if this person leaves, what breaks, and who steps in?" from an organisation's real merged-PR history, held as a graph in FalkorDB.**

Built for **Graph Hacks: Context for AI Agents** (WeMakeDevs x FalkorDB). **Track entered: Track 01, Agents That Act on Connected Data.**

| | |
|---|---|
| Live demo | https://keystone-2d8k.onrender.com (a free instance sleeps when idle: the first visit after a quiet spell takes about a minute) |
| Demo video | _to be added_ |
| Blog post | _to be added_ |
| MCP endpoint | https://keystone-2d8k.onrender.com/mcp (streamable HTTP) |

![Keystone landing page](docs/img/landing.jpg)

![The workbench: pick who leaves, the wall of modules re-solves](docs/img/workbench.png)

The workbench: choose a person (left) and the nine modules show how much knowledge stays if they leave, with the totals on the right. **Make the plan** runs the three-role review and heals the wall; the command line at the bottom talks to the same agent that serves `/mcp`; **PROOF** draws the path behind the last answer.

![Make the plan: the wall heals and the Reviewer approves](docs/img/plan.png)

![PROOF: who could step in, and the modules they would cover](docs/img/proof.png)

New to the project? Read [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## What it does

1. **Finds where knowledge is concentrated.** Every merged pull request is a fact: who authored it, who reviewed it, which module it touched. Keystone turns those facts into a `KNOWS` graph with time decay and computes bus factor, how load-bearing each module is (PageRank), and who bridges teams (betweenness).
2. **Runs the counterfactual.** "What if @Anchel123 leaves?" forks the live graph with `GRAPH.COPY`, deletes the person on the fork, recomputes the same statistics and diffs them. The live graph is never touched, and the fork is deleted afterwards.
3. **Finds who can really step in, with the path.** Successors are ranked by multi-hop evidence: who already reviewed the leaver's PRs, and who knows modules that change together with the target module (`CO_CHANGES`). Every answer carries the nodes, edges and public PR links that produced it.
4. **Acts.** Three roles hand off through graph state: the *Analyst* runs the what-if, the *Planner* simulates a pairing plan on a fork and writes a Decision with Tasks, the *Reviewer* reads those Tasks back from the graph and re-verifies on a fresh fork. An approved plan becomes reviewable artifacts: a CODEOWNERS patch diffed against the repository's real file, and an issue per pairing. All of it is a dry run unless the operator opts in.
5. **Remembers and checks itself.** Decisions and tasks are ordinary nodes. A later session asks `changes_since`: did the plan happen, judged from real PR activity rather than from a checkbox.

Ask it in plain English, or drive the same tools from Claude Desktop, Claude Code or any MCP client.

## Why this needs a graph

"Who steps in for her?" is a path question: `Person -AUTHORED-> PR -TOUCHES-> Module <-TOUCHES- PR <-REVIEWED- Person`, plus `Module -CO_CHANGES- Module`. A table of commit counts cannot show the chain. A vector index cannot compute a counterfactual. FalkorDB is the primary and central store, and the product stops working without it:

- `algo.pageRank`, `algo.labelPropagation` and `algo.betweenness` run in the database at load and write their results back as properties.
- `algo.SPpaths` finds the weighted shortest chain of shared knowledge between two people or a person and a module.
- `GRAPH.COPY` is the counterfactual engine for `what_if_leaves`, the Planner and the Reviewer.
- One graph per organisation, plus a private `GRAPH.COPY` sandbox per visitor, so writes never leak between users.
- Read tools run through `GRAPH.RO_QUERY`, so a read tool cannot mutate the graph.

## Track 01, criterion by criterion

What Keystone does for each Track 01 focus, and how to see it in under a minute on the [live demo](https://keystone-2d8k.onrender.com) (open the workbench; the command line at the bottom talks to the agent, **PROOF** and **TRACE** show what it did).

| Track 01 focus | What Keystone does | See it |
|---|---|---|
| Multi-hop reasoning | `successors` walks `reviewer -REVIEWED-> PR <-AUTHORED- leaver` and `PR -TOUCHES-> Module`, and `Module <-CO_CHANGES- Module <-KNOWS- person`. `path_between` runs `algo.SPpaths` over the knowledge graph. `what_if_leaves` re-solves the whole graph on a `GRAPH.COPY` fork. | Ask **Who steps in for Anchel123?**: barakb ranks first (reviewed 269 of his PRs) and PROOF draws the chain. Ask **How is Anchel123 connected to barakb?**: two hops, through `falkordb-browser:app/lib`. |
| Graph queries and algorithms as agent tools | 15 human-written tools, each running named Cypher (all of it in [docs/QUERIES.md](docs/QUERIES.md)). `path_between` runs `algo.SPpaths` when asked. PageRank, label propagation and betweenness run once at load, and `module_risk`, `keystones`, `risk_scan` and `knowledge_map` read what they stored. | TRACE lists each tool, its milliseconds and the named queries behind the answer. |
| Tool selection through MCP | The model chooses among the 15 tools and never writes Cypher. The in-app agent lists and calls the tools through the MCP protocol on every request, and the same tools are served at `/mcp` to Claude Desktop, Claude Code or any MCP client. | `claude mcp add --transport http keystone https://keystone-2d8k.onrender.com/mcp`, then ask for `keystones`. |
| Actions based on what the graph shows | Three roles hand off only through graph state: the Analyst runs the what-if, the Planner simulates a pairing plan on a fork and writes a Decision and Tasks, the Reviewer re-verifies them from the graph on a fresh fork. An approved plan becomes a CODEOWNERS patch and an issue per pairing. These are dry runs unless an operator opts in, and the model is shown the three tools that write only when the question asks for a plan, drafts or a note. | Click **Make the plan** (verdict **Approved**, the wall heals), then **Draft the patch**. |
| Explainable results | Every result carries a `path` and `sources` built from the same rows as the answer, the names of the queries, and one of four outcomes: `answered`, `from_memory`, `not_in_graph`, `unknown_entity`. A person named in the model's prose who is not in the tool rows throws the prose away. | PROOF, then TRACE. Ask **Who knows about Kubernetes operators?**: it says that is not in the graph. |

## Architecture

```
 browser UI ──► FastAPI ──► agent loop ──► MCP client ══(MCP protocol)══► MCP server ──► tools ──► FalkorDB
                  │             │                                              ▲                     │  GRAPH.RO_QUERY
                  │             └── LLM (optional) picks tools; never writes Cypher                  │  GRAPH.COPY forks
                  └──── /mcp (streamable HTTP) ───────────────────────────────┘                     └─ algo.* procedures
 Claude Desktop / Claude Code / any MCP client ──► stdio or /mcp
```

The model only chooses tools and phrases the answer. Names are validated: a person mentioned in the prose must appear in the tool rows, otherwise the prose is discarded and the rows are rendered instead. Without an LLM key a deterministic router makes the same MCP calls and the UI labels the mode. With keys you can set a primary and a backup model (`LLM_*` and `LLM2_*`): if the primary is slow, rate-limited or down the backup answers, and if both fail the router does, so a provider outage never breaks the demo.

## Graph data model

Nodes (one graph per tenant, `ks_<tenant>`):

| Node | Key properties |
|---|---|
| `Person` | `id` (GitHub login), `active`, `first_ts`, `last_ts`, `broker` (betweenness) |
| `PR` | `id` (`owner/repo#n`), `title`, `url`, `ts`, `nmods` |
| `Module` | `id` (`owner/repo:path`), `kind` (code, ci, tests, docs, root), `n_prs`, `importance` (PageRank), `cluster`, `total` |
| `Repo`, `Issue` | `id`, `url` |
| `Meta` | snapshot date, half-life, counts |

Edges from the data: `(Person)-[:AUTHORED]->(PR)`, `(Person)-[:REVIEWED {state}]->(PR)`, `(PR)-[:TOUCHES {share, files}]->(Module)`, `(PR)-[:CLOSES]->(Issue)`, `(Module)-[:IN]->(Repo)`.

Edges derived inside FalkorDB: `(Person)-[:KNOWS {score, share, authored, reviewed, last, cost}]->(Module)`, `(Person)-[:CO_KNOWS {w, shared}]->(Person)` (both directions), `(Module)-[:CO_CHANGES {n}]->(Module)` (both directions).

Agent memory, as ordinary nodes in the same graph: `Session`, `Finding`, `Decision`, `Task`, `Snapshot`, `Run`, `Step`, `Action`, linked by `ABOUT`, `PRODUCED`, `IMPLEMENTS`, `OBSERVED`, `HAS_STEP`, `NEXT {handoff}`, `FOR`.

Every statement is listed in [docs/QUERIES.md](docs/QUERIES.md), generated from the code that runs.

## How "knowledge" is defined

- `knowledge(p, m)` = the sum over PRs that `p` authored (weight 1.0) or reviewed (weight 0.4), times the share of that PR's files landing in module `m`, times a time decay with a 365-day half-life.
- `share(p, m)` = `knowledge(p, m)` divided by everyone's knowledge of `m`.
- **Bus factor** = the fewest people whose combined share reaches 50%.
- **Active** = authored or reviewed a PR within 180 days of the snapshot. **Orphaned** = active people hold under 25% of a module's accumulated knowledge.
- Bots are excluded. Mass changes (over 300 files) and lockfiles, vendored and generated paths are ignored.

These are structural facts about contribution patterns. They describe a team; they do not evaluate anyone.

## The tools (MCP)

`overview`, `find_modules`, `module_risk`, `risk_scan`, `keystones`, `what_if_leaves`, `successors`, `who_knows`, `knowledge_map`, `path_between`, `recall`, `changes_since`, `succession_review`, `draft_actions`, `note_finding`. Each docstring is the description the model sees, so it says when to use the tool.

## Run it

Needs Docker, Python 3.11+ and [uv](https://docs.astral.sh/uv/). The repository carries the data snapshots (about 700 KB), so no GitHub access is needed.

```bash
docker compose up --build            # app on http://localhost:8000, FalkorDB Browser on http://localhost:3000
```

or without compose:

```bash
docker run -d --name keystone-db -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
uv sync
uv run python -m keystone.bootstrap  # builds both graphs and the demo memory in about 6 seconds
uv run uvicorn keystone.api:app --port 8000
uv run pytest                        # tests need the database running
```

Optional but recommended: copy `.env.example` to `.env` and add a key (`ANTHROPIC_API_KEY`, or `LLM_API_KEY` plus `LLM_BASE_URL` for any OpenAI-compatible endpoint, or a local model through Ollama, see the file). With a model, the model chooses the tools; without one the app still answers through its deterministic router and the button at the bottom right says ROUTER.

### Use it from Claude Desktop or Claude Code

stdio (local):

```json
{ "mcpServers": { "keystone": { "command": "uv", "args": ["--directory", "/path/to/keystone", "run", "python", "-m", "keystone.mcp_server"],
                                "env": { "KEYSTONE_TENANT": "falkordb" } } } }
```

HTTP, against a local run: `claude mcp add --transport http keystone http://localhost:8000/mcp`. Against the live demo: `claude mcp add --transport http keystone https://keystone-2d8k.onrender.com/mcp` (the shared graphs there are read-only, so the three write tools answer that they need a sandbox).

### Refresh the data

```bash
uv run python -m keystone.fetch OWNER/REPO ...     # needs `gh auth login` or GITHUB_TOKEN; reads public merged PRs only
uv run python -m keystone.snapshot                 # compress into data/snapshot
uv run python -m keystone.bootstrap --force
```

## Evaluation (honest)

`bench/backtest.py` runs the successor ranking **as of 2026-04-15** and compares it with who actually took over each module's knowledge by 2026-10-15. Cases are modules where one active person held at least 40% (bus factor 1).

| Organisation | Cases | Keystone hit@3 | Next-largest holders | Busiest contributors | Random |
|---|---|---|---|---|---|
| FalkorDB (21 active people at T0) | 19 | 0.95 | 0.95 | 0.95 | 0.39 |
| Pallets (T0 2026-01-15, 49 active) | 2 | 1.00 | 1.00 | 1.00 | 0.18 |

Pallets has only two qualifying cases, so its row is listed for completeness and proves nothing on its own (`bench/backtest_pallets.json`).

What this shows and what it does not: Keystone's recommendations come true far more often than chance. In teams this small, though, simple heuristics tie the graph ranking, because the plausible successors are the same handful of people. The graph earns its place through the explanation (the path), the counterfactual (`what_if_leaves` on a fork) and the verified plan, not by out-guessing a "second-largest holder" rule.

Latency on the real FalkorDB snapshot (3,664 PRs, 62 people, 114 tracked modules), local Docker, 30 runs each (`python -m bench.latency`): single-query tools take 1 to 17 ms at p50 (`successors`, three queries, 50 ms); `what_if_leaves`, which forks the whole graph with `GRAPH.COPY`, deletes the person and recomputes, takes 113 ms at p50 and 221 ms at p95; the full three-role review takes about 0.9 s. Traversals are fast enough to run on every step of an agent loop.

### Evaluating the agent itself

`bench/agent_eval.py` asks the agent real questions about the FalkorDB graph and scores three things per question: **tools** (every tool we expect was called; with no expected tool, none may be called), **outcome** (`answered`, `from_memory`, `not_in_graph` or `unknown_entity` is the right one) and **grounded** (every person named in the answer is in the tool rows). Each question runs in its own `GRAPH.COPY` sandbox, and a model is scored on its own answer, not on the router's rescue. The question sets:

- `dev` (27): the questions the router was built against, so a regression test and not a result.
- `heldout` (26): the router first scored **62%** on tools; fixing the gaps it exposed lifted it, so it is no longer unseen.
- `fresh` (20): written after those fixes and never used to change the router or the prompt at the time it was run. This is the one to read.

| Agent | Set | Scored | Tools | Outcome | Grounded | Median per question |
|---|---|---|---|---|---|---|
| Keyword router (no key) | dev | 27 | 100% | 100% | 100% | 30 ms |
| Keyword router (no key) | heldout | 26 | 100% | 100% | 100% | 33 ms |
| Keyword router (no key) | **fresh** | 20 | **65%** | **85%** | 100% | 34 ms |
| Gemini 3.5 Flash-Lite | dev | 27 | 96% | 100% | 100% | 4.0 s |
| Gemini 3.5 Flash-Lite | **fresh** | 20 | **85%** | **95%** | 100% | 3.4 s |
| Groq gpt-oss-120b | dev | 26 of 27 (one provider error left out) | 100% | 100% | 100% | 2.5 s |
| Groq gpt-oss-120b | **fresh** | 20 | **85%** | **95%** | 100% | 2.6 s |
| Qwen3-VL 8B on a laptop GPU (Ollama) | dev | 27 | 93% | 100% | 100% | 94 s |

What this says. A model picks the right tool for about 85 of 100 unseen questions where the keyword router manages 65, and nobody's answer ever named a person the tools did not return. The misses are the interesting kind: both models read "what did the last review say" as `recall` rather than `changes_since`, one asked `overview` for "who is the CEO" where it should have declined, and Gemini answered "keep in mind that barakb is moving" by running the planning and drafting tools instead of noting it. That last one made us add a rule to the system prompt (write tools only when the user asks for a plan, drafts or a note), so the `fresh` set is no longer unseen for the prompt; the numbers above are from before that change. Checking the live site afterwards, Gemini still answered "if X leaves, what breaks and who could step in?" with `succession_review`, a tool that writes a plan to the graph, and its prose then said 5 modules were fragile when the what-if had found 21 (5 was the number the plan covers). A rule in a prompt is not a guarantee, so the code now enforces it: the model is not shown `succession_review`, `draft_actions` or `note_finding` unless the question (or the one before it) asks for a plan, drafts or a note, and the Analyst step reports the real count and how many the plan covers. Results per run are in `bench/agent_eval_*.json`; rerun with `python -m bench.agent_eval --llm --set fresh` (add `--which backup` for the second model).

The real model path is also covered by tests that need no key (`FakeModel` in `tests/test_keystone.py`): tool calls go through MCP, the model can never choose a tenant, ungrounded prose is discarded, and an empty, slow, failing or tool-less model falls back to the backup model and then the router without leaking a key.
## Safety, privacy and limits

- Public data only: merged pull requests of public repositories. GitHub logins appear (they are public); email addresses are never requested or stored.
- The public deployment serves read-only base graphs; every visitor works in a private `GRAPH.COPY` sandbox that is deleted after a few hours. A sandbox name is 96 random bits and is never listed (not by the API, not by the MCP resource, not in error messages), so the name is the visitor's capability. One address can hold at most six sandboxes and is told to retry rather than having an active one cut off (an address can be several visitors); the same refusal applies when the whole server is full. An idle sandbox is replaced first. A sandbox is deleted after three idle hours.
- Every endpoint, including `/mcp`, is rate-limited per client and across everyone, and the client address comes from the proxy's own `X-Forwarded-For` entry, believed only when the connection arrives from a private address (`KEYSTONE_TRUSTED_PROXIES`), so a forged header cannot lift the global cap or grow the limiter's table.
- A visitor's own LLM key is used for that single request, is never stored or logged, and may only target an allowlist of provider hosts.
- Actions are dry runs. Posting is off unless the operator sets `KEYSTONE_GH_REPO` (one repository they own), `GITHUB_TOKEN` and `KEYSTONE_ADMIN_TOKEN`, and the request carries `confirm=true` and the admin token in an `x-admin-token` header. A visitor can never open an issue.
- Limits: PR history is a proxy for knowledge (it misses design discussions, on-call work and direct pushes); module boundaries are directory heuristics; the successor ranking was only backtested on two organisations.

## AI assistance disclosure

Required by the hackathon rules, so stated plainly:

- The code in this repository was written with an AI coding assistant, **Claude Code (Anthropic)**, working under the direction of the team during the event window (Oct 17 to 18, 2026).
- Interface comps were generated with Figma AI (image model `gpt-image-2.5-sunburst`, through the Figma MCP) and used as visual targets; the interface itself is hand-built HTML, CSS and JavaScript.
- The team is responsible for the architecture, security, correctness and every claim above and can explain the graph model, the queries and the decisions.

_Team: who did what_ (to be completed by the team before submission):

- _name_: _role and contribution_

## Repository layout

```
keystone/   load.py (ingest + derived graph), tools.py (the tool catalog), memory.py, workflow.py (3 roles), actions.py,
            mcp_server.py, agent.py (LLM or router, via MCP), llm.py, api.py (FastAPI + /mcp), bootstrap.py, fetch.py
web/        hand-built UI (landing + workbench, no framework)   data/snapshot/  real public PR history, gzip
bench/      backtest and latency     tests/   pytest against FalkorDB      deploy/ + Dockerfile  one-container deploy
docs/       QUERIES.md (generated), HOW_IT_WORKS.md, DEMO_SCRIPT.md, DEPLOY.md, BLOG.md, design/ (the Figma AI comps the UI was built to)
scripts/    capture.ps1 (screenshots), deploy-hf.ps1 (push to a Hugging Face Space)      PRODUCT.md, DESIGN.md  design context
```

## License

MIT. Data comes from the public GitHub API; repository names and logins belong to their owners.
