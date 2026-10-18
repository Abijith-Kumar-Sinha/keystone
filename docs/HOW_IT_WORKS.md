# How Keystone works (team cheat sheet)

**One sentence.** Keystone reads a team's merged pull requests as a graph in FalkorDB, then an agent answers "if this person leaves, what breaks, and who steps in?" by calling hand-written graph tools over MCP, and turns the answer into a checked plan and reviewable patches.

## The agent, in five moves

1. **Ask.** The visitor types a question in the command line, or clicks a person.
2. **Pick tools.** The agent (`keystone/agent.py`) lists the 15 MCP tools and chooses. With no LLM key a deterministic router makes the same calls. The model never writes Cypher.
3. **Query FalkorDB.** Each tool runs fixed Cypher (`keystone/tools.py`, all listed in `docs/QUERIES.md`). Read tools use `GRAPH.RO_QUERY`.
4. **Counterfactual.** `what_if_leaves` forks the graph with `GRAPH.COPY`, deletes the person on the fork, recomputes, diffs, deletes the fork.
5. **Act.** `succession_review` (Analyst, Planner, Reviewer roles that talk only through graph nodes) writes a Decision and Tasks; `draft_actions` turns an approved plan into a CODEOWNERS patch and issue drafts. Dry run: nothing is posted.

Every answer returns its own proof (the **PROOF** button draws it): the nodes and edges, the public PR links, the names of the Cypher statements, and one of four outcomes (`answered`, `from_memory`, `not_in_graph`, `unknown_entity`). If the model names someone no tool returned, the prose is thrown away and the rows are shown instead.

## The graph in one picture

`(Person)-[:AUTHORED|REVIEWED]->(PR)-[:TOUCHES]->(Module)`. From that, inside FalkorDB: `KNOWS` (a person's decayed share of a module), `CO_KNOWS` (people who share modules), `CO_CHANGES` (modules that change together). Algorithms run in the database: PageRank (how load-bearing a module is), label propagation (territories), betweenness (brokers), `algo.SPpaths` (the chain between two nodes). Agent memory (Decision, Task, Finding, Run, Step, Action) lives in the same graph.

Definitions to say out loud: knowledge = authored 1.0 or reviewed 0.4, times the share of files in the module, times a 365-day half-life. Bus factor = fewest people reaching 50%. Orphaned = active people hold under 25%. Fragile = under 50%, or the bus factor drops to one.

## What each file does

| File | Job |
|---|---|
| `keystone/load.py` | ingest the PR snapshot, build the graph, run the algorithms |
| `keystone/tools.py` | the read tools and every Cypher statement |
| `keystone/memory.py`, `workflow.py`, `actions.py` | memory, the three-role review, the patch drafts |
| `keystone/mcp_server.py` | the 15 tools as an MCP server (`/mcp`, or stdio) |
| `keystone/agent.py`, `llm.py` | the loop: model or router, calling tools through MCP |
| `keystone/api.py` | FastAPI: the UI's JSON, `/mcp`, per-visitor sandboxes |
| `web/` | hand-built UI: `index.html` (landing) and `workbench.html` |
| `bench/backtest.py` | replays April's picks against what happened by October |

## Questions judges will ask

- **Why a graph?** The question is a path: author, PR, module, reviewer. A counterfactual needs a copy you can edit; `GRAPH.COPY` makes that cheap (113 ms median here).
- **What if there is no LLM?** The router answers; the UI says so. A visitor can paste their own key (kept in the tab, sent only with the request, host allowlist on the server).
- **Is it really an agent, or keyword matching?** With a model, the model reads the 15 tool descriptions and chooses (up to six rounds), and we score it with `bench/agent_eval.py`. On 20 questions nobody had tuned anything for, Gemini and Groq each chose the right tool 85% of the time, the keyword router 65%, and every row was 100% grounded (no name the tools did not return). Say that plainly: the model path is the agent, the router is the safety net.
- **Does it hallucinate?** The model only chooses tools. Names in its prose must appear in the tool rows or the prose is discarded.
- **Is it better than a simple rule?** On picks, no: "most active" also scores 95% in these small teams, and the README says so. The graph adds the proof, the what-if and the checked plan.
- **Is the data real?** Yes: merged PRs of public repos (FalkorDB, Pallets). Only public GitHub logins; no emails.
- **Can it write to our repo?** Not by default. Posting an issue needs `KEYSTONE_GH_REPO`, a token and `confirm=true`.
- **What did the AI write?** Claude Code wrote the code under our direction; Figma AI made the comps; the README discloses it. Be ready to explain any file above.
