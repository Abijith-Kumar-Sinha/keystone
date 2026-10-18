"""Generate docs/QUERIES.md from the Cypher the product actually runs.  python -m keystone.docs_queries > docs/QUERIES.md"""
import textwrap

from . import actions, load, memory, tools, workflow  # noqa: F401  (importing registers their queries in tools.Q)


def block(cypher: str) -> str:
    return "```cypher\n" + textwrap.fill(" ".join(cypher.split()), 118, break_long_words=False, break_on_hyphens=False) + "\n```\n"


def main() -> None:
    out = ["# Cypher and graph algorithms Keystone depends on\n",
           "Generated from the code by `python -m keystone.docs_queries`; nothing here is hand-written, so it cannot drift.\n",
           "Parameters are always passed as Cypher parameters. The language model never writes or edits any of this.\n",
           "## 1. Base facts (loaded from public merged-PR history)\n"]
    out += [f"### {t}\n{block(q)}" for t, q, _ in load.BASE]
    out.append("## 2. Derived knowledge (computed inside FalkorDB)\n")
    out += [f"### {t}\n{block(q)}" for t, q in load.DERIVE]
    out.append("## 3. Graph algorithms (run once at load, stored as properties)\n")
    for needs, title, stmts in load.ALGOS:
        out.append(f"### {title}\nRuns only when `{needs}` edges exist.\n" + "".join(block(s) for s in stmts))
    out.append("## 4. Agent tools: the human-written queries behind each MCP tool\n")
    out += [f"### `{name}`\n{block(q)}" for name, q in sorted(tools.Q.items())]
    out.append("## 5. Counterfactuals and writes\n"
               "- `GRAPH.COPY ks_<tenant> ks_<tenant>__wi_<id>` forks the graph; `what_if_leaves` and the Planner/Reviewer simulate on the fork "
               "(`MATCH (p:Person {id: $p}) DETACH DELETE p`, or add planned `KNOWS` score), then `GRAPH.DELETE` removes it.\n"
               "- Memory (`Finding`, `Decision`, `Task`, `Snapshot`, `Run`, `Step`, `Action`) is written with parameterised `CREATE`/`MERGE` in `memory.py`, "
               "`workflow.py` and `actions.py`; reads use `GRAPH.RO_QUERY` so a read tool can never mutate the graph.\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
