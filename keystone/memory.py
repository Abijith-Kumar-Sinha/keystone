"""Agent memory = ordinary nodes in the tenant graph, so a decision is one hop from the people and modules it concerns.

  (:Session)-[:PRODUCED]->(:Finding | :Decision | :Task)-[:ABOUT]->(:Person | :Module)
  (:Task)-[:IMPLEMENTS]->(:Decision)
  (:Snapshot)-[:OBSERVED {bus, top, share, cover}]->(:Module)         what the graph looked like at review time
Every memory node carries `as_of`: the data snapshot it was written against (not the wall clock), so "what changed since
last time" compares like with like even when the data is refreshed.
"""
import time
import uuid
from datetime import datetime, timezone

from . import db
from .tools import MIN_PRS, Q, _meta, _unknown, module_stats, resolve_module, resolve_person, result, short, pnode, mnode, edge

KINDS = {"finding": "Finding", "decision": "Decision", "task": "Task"}


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else None


def start_session(tenant: str, agent: str = "analyst", user: str = "anon") -> str:
    g = db.graph(tenant)
    sid = _id("s")
    db.q(g, "CREATE (:Session {id: $id, agent: $a, user: $u, ts: $ts, as_of: $as_of})",
         {"id": sid, "a": agent, "u": user, "ts": int(time.time()), "as_of": _meta(g)["snapshot_ts"]}, write=True)
    return sid


def link(g, node_id: str, label: str, about: list[str]) -> list[str]:
    """ABOUT edges to people and modules. Ids that match nothing are dropped and reported, never invented."""
    linked = []
    for a in about:
        for lab in ("Person", "Module"):
            if db.q(g, f"MATCH (x:{lab} {{id: $a}}) RETURN count(x)", {"a": a})[0][0]:
                db.q(g, f"MATCH (n:{label} {{id: $n}}), (x:{lab} {{id: $a}}) MERGE (n)-[:ABOUT]->(x)", {"n": node_id, "a": a}, write=True)
                linked.append(a)
    return linked


def remember(tenant: str, kind: str, text: str, about: list[str] | None = None, session: str | None = None, **props) -> dict:
    """Write a Finding, Decision or Task. `props` are extra scalar properties (status, expect_*, ...)."""
    t0 = time.time()
    label = KINDS.get(kind.lower())
    if not label:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    g = db.graph(tenant)
    nid = _id(kind[0])
    props = {k: v for k, v in props.items() if isinstance(v, (str, int, float, bool))}
    sets = "".join(f", {k}: ${k}" for k in props)
    db.q(g, f"CREATE (:{label} {{id: $id, text: $text, ts: $ts, as_of: $as_of{sets}}})",
         {"id": nid, "text": text[:600], "ts": int(time.time()), "as_of": _meta(g)["snapshot_ts"], **props}, write=True)
    linked = link(g, nid, label, list(about or []))
    if session:
        db.q(g, f"MATCH (s:Session {{id: $s}}), (n:{label} {{id: $n}}) MERGE (s)-[:PRODUCED]->(n)", {"s": session, "n": nid}, write=True)
    return result("remember", "answered", {"id": nid, "kind": label, "text": text[:600], "about": linked}, queries=["remember"], t0=t0)


def recall(tenant: str, subject: str | None = None, limit: int = 8) -> dict:
    """Memory about a person/module, plus memory about the people who hold that module / the modules that person holds."""
    t0 = time.time()
    g = db.graph(tenant)
    limit = max(1, min(int(limit), 20))
    if not subject:
        rows = db.q(g, "MATCH (n) WHERE n:Finding OR n:Decision OR n:Task RETURN labels(n)[0], n.text, n.ts, n.as_of, n.status, n.id ORDER BY n.ts DESC LIMIT %d" % limit)
        via = ["session"] * len(rows)
        about = [[] for _ in rows]
    else:
        pid, near = resolve_person(g, subject)
        ent = [("Person", pid)] if pid else []
        if not ent:
            c = resolve_module(g, subject, 1)
            ent = [("Module", c[0]["id"])] if c else []
        if not ent:
            return _unknown("recall", "person or module", subject, near, t0)
        lab, eid = ent[0]
        rows, via, about = [], [], []
        related = {  # one hop of context: who holds this module / what this person holds
            "Module": "MATCH (x:Module {id: $e})<-[k:KNOWS]-(p:Person) WHERE k.share >= 0.2 RETURN p.id",
            "Person": "MATCH (x:Person {id: $e})-[k:KNOWS]->(m:Module) WHERE k.share >= 0.3 RETURN m.id",
        }[lab]
        ids = [(lab, eid, "direct")] + [("Person" if lab == "Module" else "Module", r[0], "related") for r in db.q(g, related, {"e": eid})]
        seen = set()
        for l, i, how in ids:
            for r in db.q(g, f"MATCH (n)-[:ABOUT]->(x:{l} {{id: $i}}) WHERE n:Finding OR n:Decision OR n:Task "
                             "RETURN labels(n)[0], n.text, n.ts, n.as_of, n.status, n.id", {"i": i}):
                if r[5] not in seen:
                    seen.add(r[5])
                    rows.append(r)
                    via.append(how if how == "direct" else f"via {i if l == 'Person' else short(i)}")
                    about.append([i])
        order = sorted(range(len(rows)), key=lambda k: (via[k] != "direct", -rows[k][2]))[:limit]
        rows, via, about = [rows[k] for k in order], [via[k] for k in order], [about[k] for k in order]
    if not rows:
        return result("recall", "not_in_graph", {"subject": subject}, note=f"No earlier session recorded anything about {subject or 'this graph'}.", queries=["recall"], t0=t0)
    items = [{"kind": r[0], "text": r[1], "written": _iso(r[2]), "data_as_of": _iso(r[3]), "status": r[4], "id": r[5], "how": v}
             for r, v in zip(rows, via)]
    nodes = [{"id": f"memory:{i['id']}", "kind": "memory", "label": f"{i['kind']}: {i['text'][:40]}"} for i in items]
    return result("recall", "from_memory", {"subject": subject, "items": items}, {"nodes": nodes, "edges": []}, queries=["recall"], t0=t0)


def snapshot(tenant: str, session: str | None = None) -> dict:
    """Freeze the current per-module risk picture as OBSERVED edges so a later session can diff against it."""
    t0 = time.time()
    g = db.graph(tenant)
    meta = _meta(g)
    sid = _id("snap")
    rows = [{"id": mid, "bus": s["bus_active"], "top": s["top"], "share": round(s["top_share"], 4), "cover": round(s["act_tot"] / s["tot"], 4)}
            for mid, s in module_stats(g).items()]
    db.q(g, "CREATE (:Snapshot {id: $id, ts: $ts, as_of: $as_of, modules: $n})", {"id": sid, "ts": int(time.time()), "as_of": meta["snapshot_ts"], "n": len(rows)}, write=True)
    for i in range(0, len(rows), 500):
        db.q(g, "MATCH (s:Snapshot {id: $s}) UNWIND $rows AS r MATCH (m:Module {id: r.id}) "
                "CREATE (s)-[:OBSERVED {bus: r.bus, top: r.top, share: r.share, cover: r.cover}]->(m)", {"s": sid, "rows": rows[i:i + 500]}, write=True)
    if session:
        db.q(g, "MATCH (s:Session {id: $s}), (n:Snapshot {id: $n}) MERGE (s)-[:PRODUCED]->(n)", {"s": session, "n": sid}, write=True)
    return result("snapshot", "answered", {"id": sid, "modules": len(rows), "as_of": _iso(meta["snapshot_ts"])}, queries=["snapshot"], t0=t0)


Q["last_snapshot"] = """
MATCH (s:Snapshot) WITH s ORDER BY s.ts DESC LIMIT 1
MATCH (s)-[o:OBSERVED]->(m:Module)
RETURN s.id, s.as_of, m.id, o.bus, o.top, o.share, o.cover
"""

Q["open_tasks"] = """
MATCH (t:Task) WHERE t.status = 'open'
RETURN t.id, t.text, t.cand, t.module, t.baseline_share, t.target_share, t.as_of
"""

Q["task_activity"] = """
MATCH (c:Person {id: $c})-[:AUTHORED|REVIEWED]->(pr:PR)-[:TOUCHES]->(m:Module {id: $m}) WHERE pr.ts > $since
RETURN count(DISTINCT pr), collect(DISTINCT pr.url)[0]
"""

Q["current_share"] = "MATCH (p:Person {id: $c})-[k:KNOWS]->(m:Module {id: $m}) RETURN k.share"


def task_progress(tenant: str) -> list[dict]:
    """Did the plan happen? Judged from the graph (new PRs authored/reviewed + share change), not from the task's own status."""
    g = db.graph(tenant)
    now = _meta(g)["snapshot_ts"]
    out = []
    for tid, text, cand, module, base, target, as_of in db.q(g, Q["open_tasks"]):
        if not cand or not module:
            continue
        n, url = db.q(g, Q["task_activity"], {"c": cand, "m": module, "since": as_of})[0]
        cur = (db.q(g, Q["current_share"], {"c": cand, "m": module}) or [[0.0]])[0][0] or 0.0
        pct = 0 if target <= base else max(0, min(100, round(100 * (cur - base) / (target - base))))
        out.append({"task": tid, "text": text, "candidate": cand, "module": short(module), "prs_since": n, "evidence": url,
                    "share_then": round(base, 3), "share_now": round(cur, 3), "share_target": round(target, 3), "progress_pct": pct,
                    "state": "done" if pct >= 100 else ("in progress" if n else "not started")})
    return out


def changes_since(tenant: str) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    rows = db.q(g, Q["last_snapshot"])
    if not rows:
        return result("changes_since", "not_in_graph", note="No earlier review snapshot exists for this graph.", queries=["last_snapshot"], t0=t0)
    sid, then_ts = rows[0][0], rows[0][1]
    old = {r[2]: {"bus": r[3], "top": r[4], "share": r[5], "cover": r[6]} for r in rows}
    cur = module_stats(g)
    better, worse, handed = [], [], []
    for mid, s in cur.items():
        o = old.get(mid)
        if not o:
            continue
        row = {"id": mid, "module": short(mid), "bus_then": o["bus"], "bus_now": s["bus_active"], "top_then": o["top"], "top_now": s["top"],
               "share_then": o["share"], "share_now": round(s["top_share"], 3), "cover_then": o["cover"], "cover_now": round(s["act_tot"] / s["tot"], 3)}
        if o["top"] != s["top"]:
            handed.append(row)
        elif s["bus_active"] > o["bus"] or s["act_tot"] / s["tot"] - o["cover"] >= 0.1:
            better.append(row)
        elif s["bus_active"] < o["bus"] or o["cover"] - s["act_tot"] / s["tot"] >= 0.1:
            worse.append(row)
    tasks = task_progress(tenant)
    now = _meta(g)["snapshot_ts"]
    data = {"previous_review_as_of": _iso(then_ts), "now_as_of": _iso(now), "improved": better[:8], "worsened": worse[:8],
            "top_holder_changed": handed[:8], "tasks": tasks, "modules_compared": len(old)}
    nodes = [mnode(r["id"]) for r in (worse + better + handed)[:6]]
    for lst in (better, worse, handed):
        for r in lst:
            r.pop("id", None)
    return result("changes_since", "from_memory", data, {"nodes": nodes, "edges": []}, queries=["last_snapshot", "module_stats", "open_tasks", "task_activity"], t0=t0)
