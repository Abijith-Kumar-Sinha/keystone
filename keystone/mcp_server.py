"""Keystone as an MCP server. Every capability the agent has is an MCP tool; the in-app agent calls them through the MCP protocol
(see agent.py), and so can Claude Desktop / Claude Code / any MCP client:

  stdio :  python -m keystone.mcp_server                (env KEYSTONE_TENANT picks the default graph)
  http  :  served by the web app at /mcp  (streamable HTTP)

The docstrings are the tool descriptions the model sees, so they say WHEN to use each tool. The model never writes Cypher.
"""
import os

import functools

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import actions as A
from . import db, memory as M, tools as T, workflow as W

INSTRUCTIONS = (
    "Keystone answers questions about knowledge concentration and succession risk in a software organisation, using a FalkorDB graph "
    "built from real merged-PR history (authors, reviewers, files touched). Pick the tool that matches the question, then answer ONLY from "
    "the returned rows. If a tool says not_in_graph or unknown_entity, say so; never guess a person or module. "
    "Use find_modules to turn a fuzzy phrase into an exact module before calling module tools. Typical flow: risk_scan or keystones -> "
    "what_if_leaves -> successors -> succession_review -> draft_actions."
)


def _security() -> TransportSecuritySettings:
    """The SDK's DNS-rebinding guard answers 421 to every Host but localhost. That protects a server on someone's own machine; a public
    deployment (KEYSTONE_WRITABLE=sandbox) is reached by its own host name, so the guard stays on for local runs only."""
    return TransportSecuritySettings(enable_dns_rebinding_protection=os.environ.get("KEYSTONE_WRITABLE", "all") != "sandbox",
                                     allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
                                     allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"])


mcp = FastMCP("keystone", instructions=INSTRUCTIONS, streamable_http_path="/", transport_security=_security())
DEFAULT = os.environ.get("KEYSTONE_TENANT", "falkordb")


def tool(fn):
    """Register as an MCP tool, run off the event loop: FalkorDB calls are blocking and a what-if takes ~200 ms."""

    @functools.wraps(fn)
    async def run(*a, **kw):
        return await anyio.to_thread.run_sync(functools.partial(fn, *a, **kw))

    return mcp.tool()(run)


def _tenant(t: str) -> str:
    t = (t or DEFAULT).strip()
    if not db.exists(t):
        raise ValueError(f"unknown tenant '{t}'. Available: {', '.join(db.public_tenants())}")
    return t


def writable(t: str) -> bool:
    """Public deployments set KEYSTONE_WRITABLE=sandbox: only per-visitor `try-*` forks accept memory writes."""
    return os.environ.get("KEYSTONE_WRITABLE", "all") == "all" or t.startswith("try-")


def _refuse(tool: str, t: str) -> dict:
    return T.result(tool, "not_in_graph", note=f"'{t}' is a read-only demo graph. Writes are allowed on your sandbox (a private GRAPH.COPY fork) - start one in the app.")


@tool
def overview(tenant: str = "") -> dict:
    """Size and freshness of the graph: people, active people, tracked modules, merged PRs, and the as-of date of the data. Call first when unsure what is in the graph."""
    return T.overview(_tenant(tenant))


@tool
def find_modules(query: str, tenant: str = "") -> dict:
    """Turn a fuzzy phrase ('execution plan', 'browser api') into exact module ids. Use before any module-specific tool when the user did not give an exact id."""
    return T.find_modules(_tenant(tenant), query)


@tool
def module_risk(module: str, tenant: str = "") -> dict:
    """Bus factor and risk tier of ONE module: who holds its knowledge (authored vs reviewed share), whether they are still active, how load-bearing the module is (PageRank). Use for 'how risky is X', 'bus factor of X'."""
    return T.module_risk(_tenant(tenant), module)


@tool
def risk_scan(limit: int = 10, tenant: str = "") -> dict:
    """Rank every tracked module by succession risk (critical/high/medium/low) and count the tiers. Use for 'what is most at risk', 'where are we fragile', 'orphaned code'."""
    return T.risk_scan(_tenant(tenant), limit)


@tool
def keystones(limit: int = 8, tenant: str = "") -> dict:
    """People ranked by what leaves with them: modules that would be orphaned and modules where they are the sole holder. Use for 'who can we not afford to lose', 'single points of failure'."""
    return T.keystones(_tenant(tenant), limit)


@tool
def what_if_leaves(person: str, tenant: str = "") -> dict:
    """Counterfactual: if this person left, which modules become orphaned or fragile? Runs on a GRAPH.COPY fork and diffs before/after; the live graph is untouched. Use for 'what if X leaves/quits/goes on leave'."""
    return T.what_if_leaves(_tenant(tenant), person)


@tool
def successors(person: str, module: str = "", limit: int = 5, tenant: str = "") -> dict:
    """Who could realistically take over a person's modules (or one module)? Multi-hop: who already reviewed their PRs, who knows adjacent modules that change together with the target. Use for 'who can step in for X', 'who should we pair with X'."""
    return T.successors(_tenant(tenant), person, module or None, limit)


@tool
def who_knows(topic: str, limit: int = 6, tenant: str = "") -> dict:
    """Who holds the knowledge for a module or area, with authored/reviewed counts and recency. Use for 'who knows about X', 'who owns X'. Returns not_in_graph if nothing matches."""
    return T.who_knows(_tenant(tenant), topic, limit)


@tool
def knowledge_map(tenant: str = "") -> dict:
    """Territories (module clusters that change together, found by label propagation), who holds each, and the brokers that connect people (betweenness). Use for 'how is knowledge organised', 'silos', 'who bridges teams'."""
    return T.knowledge_map(_tenant(tenant))


@tool
def path_between(a: str, b: str, tenant: str = "") -> dict:
    """Weighted shortest chain of shared knowledge between two people, or a person and a module (algo.SPpaths). Use for 'how is X connected to Y'."""
    return T.path_between(_tenant(tenant), a, b)


@tool
def recall(subject: str = "", limit: int = 8, tenant: str = "") -> dict:
    """What earlier sessions concluded or decided about a person or module (findings, decisions, open tasks), including notes about the people who hold a module. Call BEFORE planning so you do not repeat or contradict earlier work."""
    return M.recall(_tenant(tenant), subject or None, limit)


@tool
def changes_since(tenant: str = "") -> dict:
    """Compare the graph now with the last saved review: which modules got safer or riskier, who became top holder, and whether open pairing tasks actually progressed according to real PR activity. Use for 'what changed since last time', 'did the plan work'."""
    return M.changes_since(_tenant(tenant))


@tool
def succession_review(person: str, tenant: str = "") -> dict:
    """Full succession review for one person, run by three roles that coordinate only through graph state: Analyst (what-if + successors), Planner (simulates a pairing plan on a fork, writes a Decision and Tasks), Reviewer (re-verifies from the graph on a fresh fork). Writes memory. Use for 'make a plan for X', 'succession plan'."""
    t = _tenant(tenant)
    return W.succession_review(t, person) if writable(t) else _refuse("succession_review", t)


@tool
def draft_actions(decision_id: str = "", tenant: str = "") -> dict:
    """Turn an approved succession Decision into concrete, reviewable artifacts: a CODEOWNERS patch per repo and an issue draft per pairing, each with the graph evidence. Dry-run: nothing is posted anywhere. Omit decision_id to use the latest approved one."""
    t = _tenant(tenant)
    return A.draft_actions(t, decision_id or None) if writable(t) else _refuse("draft_actions", t)


@tool
def note_finding(text: str, about: list[str], tenant: str = "") -> dict:
    """Save a short finding to memory, linked to the people/modules (exact ids) it is about. Only write what the graph showed."""
    t = _tenant(tenant)
    return M.remember(t, "finding", text, about) if writable(t) else _refuse("note_finding", t)


@mcp.resource("keystone://tenants")
def tenants_resource() -> str:
    """Graphs (organisations) available on this server."""
    return "\n".join(db.public_tenants())


@mcp.prompt()
def succession_briefing(person: str) -> str:
    """A ready-made briefing request for one person."""
    return (f"Run a succession briefing for {person}: what_if_leaves, the top successors for their riskiest modules, recall earlier decisions, "
            f"then summarise the plan with evidence. Cite only tool results.")


if __name__ == "__main__":
    mcp.run()  # stdio

