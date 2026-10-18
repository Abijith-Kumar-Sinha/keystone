"""Web app: JSON API for the UI, the MCP endpoint at /mcp, and the static front end.

  uv run uvicorn keystone.api:app --port 8000

Public-deployment safety: base graphs are read-only (KEYSTONE_WRITABLE=sandbox); every visitor works in a private GRAPH.COPY fork
(`try-<id>`, deleted after SANDBOX_TTL); bring-your-own LLM keys live only for the request and may only target an allowlist of hosts.
"""
import asyncio
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import actions as A
from . import agent, db, llm
from . import tools as T
from .mcp_server import mcp, writable

WEB = Path(__file__).resolve().parent.parent / "web"
SANDBOX_TTL = int(os.environ.get("SANDBOX_TTL", 3 * 3600))
MAX_SANDBOXES = int(os.environ.get("MAX_SANDBOXES", 40))
LLM_HOSTS = {"api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com", "api.groq.com", "openrouter.ai", "api.mistral.ai"}
_sandboxes: dict[str, float] = {}               # name -> when it was last used (it is deleted after SANDBOX_TTL idle seconds)
_owner: dict[str, str] = {}                      # name -> the client that started it
_hits: dict[tuple, deque] = {}                   # (client or "*", bucket) -> recent request times
MAX_PER_CLIENT = int(os.environ.get("MAX_SANDBOXES_PER_CLIENT", 6))


TRUSTED_PROXIES = int(os.environ.get("KEYSTONE_TRUSTED_PROXIES", 1))   # reverse proxies in front of the app (Render, Hugging Face: 1; none: 0)


def _internal(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is believed only when the socket peer is our own proxy (a private or loopback address): someone
    connecting directly could write anything in it. Each trusted proxy appends the peer it saw, so the entry that many hops from the right is
    the one our own infrastructure recorded; entries to its left are whatever the client chose to send, and are ignored."""
    peer = request.client.host if request.client else "?"
    if TRUSTED_PROXIES and _internal(peer):
        hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
        if len(hops) >= TRUSTED_PROXIES:
            return hops[-TRUSTED_PROXIES]
    return peer


def _recent(key: tuple, now: float, per: int):
    q = _hits.get(key)
    while q and q[0] < now - per:
        q.popleft()
    return q


def limited(request: Request, bucket: str, n: int, per: int = 60, total: int | None = None) -> None:
    """At most n requests per client and `total` across everyone in `per` seconds. The global cap is checked first and a refused request leaves
    no trace, so a flood of forged addresses can neither lift the cap nor grow this table."""
    now, me = time.time(), client_ip(request)
    for key, cap in (("*", total), (me, n)):
        if cap is None:
            continue
        q = _recent((key, bucket), now, per)
        if q is not None and len(q) >= cap:
            raise HTTPException(429, f"Slow down: max {cap} {bucket} requests per {per}s{' for everyone' if key == '*' else ''}.")
    if len(_hits) > 4096:                              # forget clients whose window has emptied
        for k in [k for k in list(_hits) if not _recent(k, now, per)]:
            _hits.pop(k, None)
    for key in (me, "*"):
        _hits.setdefault((key, bucket), deque()).append(now)

class Limit:
    """Pure ASGI wrapper (it must not buffer the streamed MCP responses) that rate-limits everything under a mount."""

    def __init__(self, app, bucket: str, n: int, total: int):
        self.app, self.bucket, self.n, self.total = app, bucket, n, total

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            try:
                limited(Request(scope), self.bucket, self.n, total=self.total)
            except HTTPException as e:
                await JSONResponse({"detail": e.detail}, status_code=e.status_code)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def drop_sandbox(name: str) -> None:
    try:
        db.client().connection.execute_command("GRAPH.DELETE", db.PREFIX + name)
    except Exception:
        pass
    _sandboxes.pop(name, None)
    _owner.pop(name, None)


def sweep() -> None:
    for name, ts in list(_sandboxes.items()):
        if time.time() - ts > SANDBOX_TTL:
            drop_sandbox(name)


async def _janitor():
    while True:
        await asyncio.sleep(300)
        sweep()


mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    for t in db.tenants():  # forks from a previous process are orphans
        if t.startswith("try-"):
            drop_sandbox(t)
    db.set_timeout_ms(30000)
    task = asyncio.create_task(_janitor())
    async with mcp.session_manager.run():
        yield
    task.cancel()


app = FastAPI(title="Keystone", lifespan=lifespan)
app.mount("/mcp", Limit(mcp_app, "mcp", 60, 240))


def tenant_or_404(t: str) -> str:
    if not db.TENANT_RE.match(t or "") or not db.exists(t):
        raise HTTPException(404, f"unknown graph '{t}'")
    if t in _sandboxes:
        _sandboxes[t] = time.time()                     # in use: it is the last to be evicted and its idle clock restarts
    return t


class Sandbox(BaseModel):
    base: str = "falkordb"


class Ask(BaseModel):
    tenant: str
    question: str = Field(max_length=500)
    history: list[dict] = []
    focus: dict | None = None
    llm: dict | None = None


class Tool(BaseModel):
    tenant: str
    name: str
    args: dict = {}


def provider_for(cfg: dict | None) -> list:
    """BYO key: used for this request only, never stored or logged. base_url is allowlisted (no SSRF).
    Otherwise the server's models in order (primary, then backup); an empty list means the router answers."""
    if cfg and cfg.get("key"):
        kind = cfg.get("provider") if cfg.get("provider") in ("anthropic", "openai") else "openai"
        base = cfg.get("base_url") or None
        if base and (urlparse(base).scheme != "https" or urlparse(base).hostname not in LLM_HOSTS):
            raise HTTPException(400, f"base_url host must be one of: {', '.join(sorted(LLM_HOSTS))}")
        return [llm.Provider(kind, cfg["key"], cfg.get("model") or None, base)]
    chain = llm.chain_from_env() if os.environ.get("KEYSTONE_SERVER_LLM", "1") == "1" else []
    return [llm.Provider(c["kind"], c["key"], c.get("model"), c.get("base_url")) for c in chain]


@app.get("/api/health")
def health():
    models = [p.model for p in provider_for(None)]               # model names only, never keys
    return {"ok": True, "tenants": db.public_tenants(), "sandboxes": len(_sandboxes),
            "server_llm": bool(models), "models": models, "writable": os.environ.get("KEYSTONE_WRITABLE", "all")}


@app.get("/api/tenants")
def tenants():
    out = []
    for t in db.tenants():
        if t.startswith("try-"):
            continue
        m = T._meta(db.graph(t))
        out.append({"name": t, "people": m["people"], "active": int(m["active"]), "modules": m["modules"], "prs": m["n_prs"], "as_of": m["snapshot_ts"]})
    return out


@app.post("/api/sandbox")
def sandbox(body: Sandbox, request: Request):
    limited(request, "sandbox", 6, total=30)
    base = tenant_or_404(body.base)
    if base.startswith("try-"):
        raise HTTPException(400, "fork a base graph, not a sandbox")
    sweep()
    me = client_ip(request)
    mine = [n for n in _sandboxes if _owner.get(n) == me]
    if len(mine) >= MAX_PER_CLIENT:
        idlest = min(mine, key=_sandboxes.get)
        if time.time() - _sandboxes[idlest] < 120:       # one address can be several visitors (a campus, a proxy): never cut off a sandbox that is in use
            raise HTTPException(429, f"This address already has {MAX_PER_CLIENT} active sandboxes. Use one of them, or retry in a minute.")
        drop_sandbox(idlest)                             # an idle one of its own is fair game
    while len(_sandboxes) >= MAX_SANDBOXES:
        idlest = min(_sandboxes, key=_sandboxes.get)
        if time.time() - _sandboxes[idlest] < 120:       # every sandbox was used in the last two minutes: refuse rather than cut anyone off
            raise HTTPException(503, "All sandboxes are in use. Try again in a minute.")
        drop_sandbox(idlest)
    name = f"try-{secrets.token_hex(12)}"                # 96 random bits: the name is the capability, and it is never listed anywhere
    try:
        db.client().connection.execute_command("GRAPH.COPY", db.PREFIX + base, db.PREFIX + name)
    except Exception as e:                               # FalkorDB forks to copy a graph: under memory pressure that can fail, and the visitor should just retry
        raise HTTPException(503, "The server is busy copying graphs. Try again in a few seconds.") from e
    _sandboxes[name], _owner[name] = time.time(), me
    return {"tenant": name, "base": base, "ttl_seconds": SANDBOX_TTL}


@app.get("/api/graph")
def graph_view(tenant: str, k: int = 36):
    g = db.graph(tenant_or_404(tenant))
    k = max(8, min(k, 60))
    stats = T.module_stats(g)
    rows = db.q(g, f"MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= {T.MIN_PRS} "
                   f"WITH m ORDER BY m.importance DESC, m.n_prs DESC LIMIT {k} "
                   "MATCH (m)<-[x:KNOWS]-(p:Person) WHERE x.share >= 0.15 RETURN m.id, m.importance, m.n_prs, p.id, p.active, x.share")
    nodes, edges, weight = {}, [], defaultdict(float)
    for mid, imp, n, pid, act, share in rows:
        s = stats.get(mid)
        nodes[f"module:{mid}"] = {"id": f"module:{mid}", "kind": "module", "label": T.short(mid), "tier": T.tier(s) if s else "low",
                                  "importance": round(imp or 0, 3), "prs": n,
                                  "cover": round(s["act_tot"] / s["tot"], 3) if s else None, "bus": s["bus_active"] if s else None,
                                  "top": s["top"] if s else None, "top_share": round(s["top_share"], 3) if s else None}
        nodes.setdefault(f"person:{pid}", {"id": f"person:{pid}", "kind": "person", "label": pid, "active": bool(act)})
        weight[pid] += share
        edges.append({"source": f"person:{pid}", "target": f"module:{mid}", "type": "KNOWS", "share": round(share, 3)})
    for pid, w in weight.items():
        nodes[f"person:{pid}"]["weight"] = round(w, 2)
    return {"nodes": list(nodes.values()), "edges": edges, "meta": T._meta(g)}


@app.get("/api/cells")
def cells(tenant: str, leaver: str = "", n: int = 9, affected: int = -1):
    """The wall of module cells: for each module its holders (spokes) and what remains if `leaver` goes.
    Same definitions as the tools (retained = active share left), computed without a fork so the UI feels instant.
    `affected` caps how many of the n cells are modules the leaver holds (the rest are untouched, locked ones)."""
    t = tenant_or_404(tenant)
    g = db.graph(t)
    n = max(1, min(n, 12))
    affected = (n + 1) // 2 if affected < 0 else max(0, min(affected, n))
    stats = T.module_stats(g)
    pid = T.resolve_person(g, leaver)[0] if leaver else None
    if leaver and not pid:
        raise HTTPException(404, f"no person '{leaver}' in this graph")
    mine = {r[0]: r[1] for r in db.q(g, T.Q["person_modules"], {"p": pid, "min_prs": T.MIN_PRS, "limit": 400})} if pid else {}
    active = bool(db.q(g, "MATCH (p:Person {id: $p}) RETURN p.active", {"p": pid})[0][0]) if pid else False
    hit = sorted((m for m in stats if mine.get(m, 0) >= 0.2), key=lambda m: -(stats[m]["imp"] or 0) * (1 + mine[m]))
    rest = sorted((m for m in stats if m not in set(hit[:affected])), key=lambda m: -(stats[m]["imp"] or 0))
    ranked = hit[:affected] + [m for m in rest if mine.get(m, 0) < 0.05][:n - len(hit[:affected])]
    out = []
    for mid in ranked:
        s = stats[mid]
        share = mine.get(mid, 0.0)
        cover = s["act_tot"] / s["tot"]
        retained = max(0.0, cover - (share if active else 0.0))
        holders = [{"person": p, "share": round(sh, 3), "active": bool(act), "removed": p == pid}
                   for p, sh, _, _, _, act in db.q(g, T.Q["module_holders"], {"m": mid})]
        out.append({"id": mid, "name": T.short(mid), "retained": round(retained if pid else cover, 3), "tier": T.tier(s),
                    "affected": bool(pid and share >= 0.05), "holders": holders[:8]})
    return {"tenant": t, "leaver": pid, "cells": out, "as_of": T._meta(g)["snapshot_ts"]}


@app.post("/api/ask")
async def ask(body: Ask, request: Request):
    limited(request, "ask", 20, total=90)
    t = tenant_or_404(body.tenant)
    history = [{"role": "assistant" if h.get("role") == "assistant" else "user", "content": str(h.get("content", ""))[:2000]} for h in body.history[-6:]]
    return await agent.ask(t, body.question.strip(), history, provider_for(body.llm), body.focus)


@app.post("/api/tool")
async def tool(body: Tool, request: Request):
    """The UI's buttons call tools through the same MCP path the agent uses."""
    limited(request, "tool", 40, total=150)
    from mcp.shared.memory import create_connected_server_and_client_session
    t = tenant_or_404(body.tenant)
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        res = await client.call_tool(body.name, {**body.args, "tenant": t})
    return agent._unwrap(res)


@app.get("/api/memory")
def memory(tenant: str):
    g = db.graph(tenant_or_404(tenant))
    items = [{"kind": r[0], "id": r[1], "text": r[2], "status": r[3], "ts": r[4], "as_of": r[5], "detail": r[6]} for r in db.q(
        g, "MATCH (n) WHERE n:Decision OR n:Task OR n:Finding OR n:Action RETURN labels(n)[0], n.id, coalesce(n.text, n.title), n.status, n.ts, n.as_of, "
           "coalesce(n.kind, n.module) ORDER BY n.ts DESC LIMIT 40")]
    runs: dict[str, dict] = {}
    for rid, goal, status, ts, n, by, action, summary in db.q(
            g, "MATCH (r:Run)-[:HAS_STEP]->(s:Step) RETURN r.id, r.goal, r.status, r.ts, s.n, s.by, s.action, s.summary ORDER BY r.ts DESC, s.n LIMIT 40"):
        runs.setdefault(rid, {"id": rid, "goal": goal, "status": status, "ts": ts, "steps": []})["steps"].append({"n": n, "by": by, "action": action, "summary": summary})
    return {"items": items, "runs": list(runs.values())[:5]}


@app.post("/api/actions/{action_id}/execute")
def execute(action_id: str, tenant: str, confirm: bool = False, request: Request = None):
    limited(request, "execute", 3, total=6)
    if os.environ.get("KEYSTONE_GH_REPO"):                # posting a real issue is the operator's decision: it needs the admin token as well as confirm=true
        want = os.environ.get("KEYSTONE_ADMIN_TOKEN", "")
        if not want or not hmac.compare_digest(request.headers.get("x-admin-token", ""), want):
            raise HTTPException(403, "Posting needs the operator's admin token (header x-admin-token).")
    t = tenant_or_404(tenant)
    if not writable(t):
        raise HTTPException(403, "read-only graph")
    return A.execute(t, action_id, confirm)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/workbench")
def workbench():
    return FileResponse(WEB / "workbench.html")


if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")
