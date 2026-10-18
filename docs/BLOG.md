<!-- DRAFT for the blog side prize. Rewrite it in your own voice, add the screenshots, and publish it yourselves (dev.to, Hashnode, Medium or the WeMakeDevs blog). Every number below is from the repository; re-check them against the final build. -->

# If your best engineer quits tomorrow, what breaks? An agent that answers with a graph

Every engineering leader has asked it. The usual answers are a gut feeling or a "bus factor" number on a dashboard. We wanted an agent that answers with evidence: who holds the knowledge of each part of the codebase, what happens if they leave, who can realistically step in, and what to do about it, with the path behind every claim.

We built it for Graph Hacks on FalkorDB, and we pointed it at FalkorDB's own public repositories.

## The data is already a graph

A merged pull request is a small fact about people and code: someone authored it, others reviewed it, it touched some files. For FalkorDB's twelve public repos that is 3,664 merged PRs, 62 contributors and 114 modules (top-level directories, two levels under `src/` or `app/`). Load them and the relationships are the product:

```
(Person)-[:AUTHORED]->(PR)-[:TOUCHES {share}]->(Module)<-[:TOUCHES]-(PR)<-[:REVIEWED]-(Person)
```

"Who steps in for her?" is a path question over that shape. A table of commit counts cannot show the chain, and a vector index cannot compute a counterfactual.

## Knowledge becomes an edge, computed in the database

We never compute knowledge in Python. One Cypher statement turns authoring into a `KNOWS` edge, weighted by how much of each PR landed in the module and decayed by age:

```cypher
MATCH (p:Person)-[:AUTHORED]->(pr:PR)-[t:TOUCHES]->(m:Module)
WITH p, m, count(pr) AS n, sum(t.share * exp(-1.0 * ($now - pr.ts) / $tau)) AS s
MERGE (p)-[k:KNOWS]->(m) SET k.authored = n, k.a_score = s
```

Reviews count too, at 0.4, because reviewing is how knowledge spreads. From the shares we get a bus factor (the fewest people covering half the knowledge) in a single `reduce` expression. Then FalkorDB's own algorithms add the structure: `algo.pageRank` over modules that change together says how load-bearing each one is, `algo.labelPropagation` finds subsystems, and `algo.betweenness` finds the people who bridge teams.

The real data had real surprises. `falkordb-rs` is 69 percent one person. The core engine is spread across four people (29, 26, 18 and 11 percent). The docs lean on one maintainer (44 percent).

## The counterfactual is a graph fork

The heart of the product is `what_if_leaves`. FalkorDB can copy a whole graph in one command, so a counterfactual is cheap and safe:

```python
@contextmanager
def fork(tenant):
    name = f"ks_{tenant}__wi_{uuid.uuid4().hex[:8]}"
    client().connection.execute_command("GRAPH.COPY", f"ks_{tenant}", name)
    try:
        yield client().select_graph(name)
    finally:
        client().connection.execute_command("GRAPH.DELETE", name)
```

Fork, delete the person, recompute the same statistics, diff. On the real data this takes 113 ms at the median (221 ms at p95), and the live graph is never touched. A module is called *orphaned* when active people would hold under 25 percent of what was ever learned about it; *fragile* when it drops to a single holder.

## The model chooses tools; it never writes Cypher

Keystone exposes fifteen human-written tools over MCP (`module_risk`, `what_if_leaves`, `successors`, `path_between`, and so on). The in-app agent lists and calls them through the MCP protocol on every request, which means the same tools work from Claude Desktop or Claude Code with no extra code. Three habits keep it honest:

- Every result carries the nodes and edges built from the same rows as the answer, plus public PR links.
- Four explicit outcomes: `answered`, `from_memory`, `not_in_graph`, `unknown_entity`. Ask who knows about Kubernetes operators and it says the graph has nothing about that.
- If the model's prose names a person that no tool returned, the prose is thrown away and the rows are rendered instead. We tested this with a fabricated handle.

## Acting, with checks

An agent that only reports is half useful. For a succession plan three roles work through graph state alone. The Analyst runs the what-if and ranks successors by multi-hop evidence (who already reviewed the leaver's PRs, who knows modules that change together with the target). The Planner simulates the plan on a fork and writes a `Decision` with `Task` nodes. The Reviewer then reads those tasks back from the graph and re-verifies them on a fresh fork; it never sees the Planner's variables. Role changes are `NEXT {handoff: true}` edges, so the coordination is itself queryable.

An approved plan turns into artifacts a human can review: a CODEOWNERS patch diffed against the repository's real file, and an issue per pairing with the evidence. All of it is a dry run unless the operator opts in.

## Does it work? An honest backtest

We ran the successor ranking as of 2026-04-15 and compared it with who actually picked up each at-risk module's knowledge by 2026-10-15 (19 cases, FalkorDB).

| Method | hit@3 |
|---|---|
| Keystone | 0.95 |
| Next-largest holders | 0.95 |
| Busiest recent contributors | 0.95 |
| Random | 0.39 |

The recommendations come true far more often than chance. But in a team this small the plausible successors are the same handful of people, so simple heuristics tie the graph. We would rather say that than hide it: the graph earns its place through the explanation, the counterfactual and the verified plan, not by out-guessing a "second-largest holder" rule.

## Limits

PR history is a proxy for knowledge; it misses design discussions, on-call work and direct pushes. Module boundaries are directory heuristics. The tool describes contribution patterns and is not an evaluation of anyone.

## Try it

Code and setup: the repository README. It runs with `docker compose up --build`, builds both graphs in about six seconds, and needs no API key (a deterministic router answers if you have none; paste your own key in the app for a real model). The MCP endpoint is at `/mcp`.

*Built with an AI coding assistant (Claude Code), as disclosed in the README, for Graph Hacks by WeMakeDevs and FalkorDB.*
