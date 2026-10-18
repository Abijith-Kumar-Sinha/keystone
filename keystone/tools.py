"""Keystone's tool catalog. The model picks a tool and fills arguments; it never writes Cypher.

Every tool returns the same envelope:
  outcome  answered | from_memory | not_in_graph | unknown_entity   (never a guess)
  data     structured rows (the single source of truth for the answer)
  path     {nodes, edges} built from those SAME rows, so the explanation is the query result, not a story about it
  sources  public GitHub URLs (PRs) behind the numbers
  queries  names of the Cypher in Q that produced the rows (see docs/QUERIES.md, generated from Q)
Definitions (also in README):
  knowledge(p, m)  = sum over PRs p authored (weight 1) or reviewed (weight 0.4) touching m, x share of PR in m, x time decay
  share(p, m)      = knowledge(p, m) / sum over everyone
  bus factor       = fewest people whose combined share reaches 50%   (truck-factor style)
  active           = authored/reviewed a PR within 180 days of the snapshot
  orphaned         = active people hold < 25% of a module's accumulated knowledge
"""
import difflib
import re
import time

from . import db

MIN_PRS = 6        # modules with fewer merged PRs are noise
ORPHAN_AT = 0.25   # active people hold less than this share => orphaned
COVER = 0.5        # truck-factor coverage target
KINDS = "['code','ci']"

Q: dict[str, str] = {}

# One row per code/ci module: who holds the knowledge, the bus factor over everyone and over *active* people only.
Q["module_stats"] = f"""
MATCH (m:Module) WHERE m.kind IN {KINDS} AND m.n_prs >= $min_prs
MATCH (m)<-[k:KNOWS]-(p:Person)
WITH m, p, k ORDER BY m.id, k.score DESC
WITH m, collect({{p: p.id, s: k.score, act: p.active, au: k.authored, rv: k.reviewed, last: k.last}}) AS hs, sum(k.score) AS tot
WITH m, hs, tot, reduce(a = 0.0, h IN hs | a + CASE WHEN h.act THEN h.s ELSE 0.0 END) AS act_tot
RETURN m.id AS id, m.n_prs AS n_prs, m.importance AS imp, tot, act_tot, hs[0].p AS top, hs[0].s / tot AS top_share,
  reduce(a = {{c: 0.0, k: 0}}, h IN hs | CASE WHEN a.c < {COVER} * tot THEN {{c: a.c + h.s, k: a.k + 1}} ELSE a END).k AS bus,
  reduce(a = {{c: 0.0, k: 0}}, h IN [x IN hs WHERE x.act] | CASE WHEN a.c < {COVER} * act_tot THEN {{c: a.c + h.s, k: a.k + 1}} ELSE a END).k AS bus_active
"""

Q["module_holders"] = """
MATCH (m:Module {id: $m})<-[k:KNOWS]-(p:Person)
RETURN p.id AS person, k.share AS share, k.authored AS authored, k.reviewed AS reviewed, k.last AS last, p.active AS active
ORDER BY k.score DESC LIMIT 8
"""

Q["module_evidence"] = """
MATCH (m:Module {id: $m})<-[:TOUCHES]-(pr:PR)
RETURN pr.url AS url, pr.title AS title, pr.ts AS ts ORDER BY pr.ts DESC LIMIT 3
"""

# People ranked by what leaves with them, in one pass over the graph (no fork):
#   orphaned = modules whose active knowledge would drop below the orphan line
#   sole     = modules where they alone hold >= half the knowledge (a single point of failure)
Q["keystones"] = f"""
MATCH (m:Module) WHERE m.kind IN {KINDS} AND m.n_prs >= $min_prs
MATCH (m)<-[k:KNOWS]-(q:Person)
WITH m, sum(k.score) AS tot, sum(CASE WHEN q.active THEN k.score ELSE 0.0 END) AS act
WHERE act / tot >= {ORPHAN_AT}
MATCH (m)<-[kp:KNOWS]-(p:Person {{active: true}})
WITH p, m, (act - kp.score) / tot AS left_cover, kp.share AS share
WHERE left_cover < {ORPHAN_AT} OR share >= {COVER}
WITH p, m, share, left_cover, (left_cover < {ORPHAN_AT}) AS orphan
RETURN p.id AS person, sum(CASE WHEN orphan THEN 1 ELSE 0 END) AS orphaned, sum(CASE WHEN orphan THEN 0 ELSE 1 END) AS sole,
       sum((CASE WHEN orphan THEN 1.0 ELSE 0.5 END) * (0.2 + m.importance)) AS weighted, p.broker AS broker,
       collect({{m: m.id, share: share, orphan: orphan, imp: m.importance}}) AS mods
ORDER BY weighted DESC LIMIT $limit
"""

Q["isolated_after"] = f"""
MATCH (m:Module) WHERE m.kind IN {KINDS} AND m.n_prs >= $min_prs AND NOT (m)<-[:KNOWS]-()
RETURN m.id AS id
"""

Q["successor_direct"] = """
UNWIND $targets AS tid
MATCH (t:Module {id: tid})
MATCH (c:Person {active: true}) WHERE c.id <> $p
OPTIONAL MATCH (c)-[kc:KNOWS]->(t)
RETURN c.id AS cand, sum(coalesce(kc.share, 0.0)) AS direct
"""

Q["successor_adjacent"] = """
UNWIND $targets AS tid
MATCH (t:Module {id: tid})<-[cc:CO_CHANGES]-(m2:Module)<-[ka:KNOWS]-(c:Person {active: true})
WHERE c.id <> $p AND m2.kind <> 'root'
RETURN c.id AS cand, sum(ka.share * log(1 + cc.n)) AS adjacent, collect(m2.id)[0] AS via
"""

Q["successor_reviewed"] = """
MATCH (c:Person {active: true})-[:REVIEWED]->(pr:PR)<-[:AUTHORED]-(p:Person {id: $p})
MATCH (pr)-[:TOUCHES]->(t:Module) WHERE t.id IN $targets
RETURN c.id AS cand, count(DISTINCT pr) AS n, collect(DISTINCT pr.url)[0] AS url
"""

Q["person_modules"] = f"""
MATCH (p:Person {{id: $p}})-[k:KNOWS]->(m:Module) WHERE m.kind IN {KINDS} AND m.n_prs >= $min_prs
RETURN m.id AS id, k.share AS share, m.importance AS imp ORDER BY k.share * (0.2 + m.importance) DESC LIMIT $limit
"""

Q["who_knows"] = """
MATCH (m:Module {id: $m})<-[k:KNOWS]-(p:Person)
RETURN p.id AS person, k.share AS share, k.authored AS authored, k.reviewed AS reviewed, k.last AS last, p.active AS active
ORDER BY k.score DESC LIMIT $limit
"""

# Territories: modules that change together (label propagation on CO_CHANGES), and who holds each one.
Q["clusters"] = f"""
MATCH (m:Module) WHERE m.kind IN {KINDS} AND m.n_prs >= $min_prs AND m.cluster >= 0
MATCH (m)<-[k:KNOWS]-(p:Person)
WITH m.cluster AS c, p, sum(k.score) AS s, collect(DISTINCT m.id) AS mods
ORDER BY s DESC
WITH c, collect({{p: p.id, s: s, act: p.active}}) AS ps, sum(s) AS tot, count(DISTINCT p) AS ppl
RETURN c, tot, ps[0..5] AS top,
  reduce(a = {{c: 0.0, k: 0}}, h IN ps | CASE WHEN a.c < {COVER} * tot THEN {{c: a.c + h.s, k: a.k + 1}} ELSE a END).k AS bus
"""

Q["cluster_modules"] = f"""
MATCH (m:Module) WHERE m.kind IN {KINDS} AND m.n_prs >= $min_prs AND m.cluster >= 0
RETURN m.cluster AS c, collect(m.id) AS mods, sum(m.n_prs) AS prs
"""

Q["brokers"] = """
MATCH (p:Person {active: true}) WHERE p.broker > 0 RETURN p.id AS person, p.broker AS broker ORDER BY p.broker DESC LIMIT 5
"""

Q["shortest_knowledge_path"] = """
MATCH (a:%s {id: $a}), (b:%s {id: $b})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['KNOWS'], relDirection: 'both', weightProp: 'cost', pathCount: 1})
YIELD path, pathWeight
RETURN [n IN nodes(path) | {id: n.id, kind: labels(n)[0]}] AS nodes, [r IN relationships(path) | r.share] AS shares, pathWeight
"""

Q["overview"] = """
MATCH (x:Meta {id: 'meta'})
OPTIONAL MATCH (p:Person) WITH x, count(p) AS people, sum(CASE WHEN p.active THEN 1 ELSE 0 END) AS active
OPTIONAL MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= %d
RETURN x.snapshot_ts AS snapshot_ts, x.n_prs AS n_prs, x.half_life_days AS half_life, people, active, count(m) AS modules
""" % MIN_PRS

Q["names"] = "MATCH (p:Person) RETURN p.id"
Q["module_names"] = "MATCH (m:Module) WHERE m.n_prs >= $min_prs RETURN m.id, m.kind, m.n_prs ORDER BY m.n_prs DESC"


# ----------------------------------------------------------------------------- envelope + helpers

def short(mid: str) -> str:
    """FalkorDB/FalkorDB:src/graph -> FalkorDB:src/graph (owner is noise in the UI)."""
    repo, _, path = mid.partition(":")
    return f"{repo.split('/')[-1]}:{path}"


def result(tool: str, outcome: str, data=None, path=None, sources=None, queries=None, note: str | None = None, t0: float | None = None) -> dict:
    return {"tool": tool, "outcome": outcome, "data": data if data is not None else {}, "note": note,
            "path": path or {"nodes": [], "edges": []}, "sources": sources or [], "queries": queries or [],
            "ms": round((time.time() - t0) * 1000, 1) if t0 else None}


def pnode(pid: str, **kw) -> dict:
    return {"id": f"person:{pid}", "kind": "person", "label": pid, **kw}


def mnode(mid: str, **kw) -> dict:
    return {"id": f"module:{mid}", "kind": "module", "label": short(mid), **kw}


def edge(a: str, b: str, typ: str, **kw) -> dict:
    return {"source": a, "target": b, "type": typ, **kw}


def _norm(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def resolve_person(g, name: str) -> tuple[str | None, list[str]]:
    names = [r[0] for r in db.q(g, Q["names"])]
    low = {n.lower(): n for n in names}
    key = name.strip().lstrip("@").lower()
    if key in low:
        return low[key], []
    near = difflib.get_close_matches(key, list(low), n=4, cutoff=0.6)
    return (low[near[0]] if near and difflib.SequenceMatcher(None, key, near[0]).ratio() >= 0.88 else None), [low[n] for n in near]


def resolve_module(g, text: str, limit: int = 5) -> list[dict]:
    """Candidates for a module reference, best first. Exact id/path beats token overlap beats fuzzy."""
    rows = db.q(g, Q["module_names"], {"min_prs": 1})
    key, toks = text.strip().lower(), _norm(text)
    scored = []
    for mid, kind, n in rows:
        path = mid.partition(":")[2].lower()
        mtoks = set(_norm(mid))
        if key in (mid.lower(), path, short(mid).lower()):
            s = 3.0
        elif toks and all(any(t in mt for mt in mtoks) for t in toks):
            s = 2.0 + len(toks) / (len(mtoks) + 1)
        else:
            s = difflib.SequenceMatcher(None, key, path).ratio()
            s = s if s >= 0.75 else 0.0
        if s:
            scored.append((s + (0.01 if kind in ("code", "ci") else -0.5), mid, kind, n))
    scored.sort(key=lambda r: (-r[0], -r[3]))
    return [{"id": m, "short": short(m), "kind": k, "n_prs": n} for _, m, k, n in scored[:limit]]


def _unknown(tool: str, what: str, name: str, suggestions: list[str], t0: float) -> dict:
    return result(tool, "unknown_entity", {"asked": name, "kind": what, "did_you_mean": suggestions},
                  note=f"No {what} called '{name}' in this graph." + (f" Closest: {', '.join(suggestions)}." if suggestions else ""), t0=t0)


def _days(now: int, ts: int | None) -> int | None:
    return None if ts is None else max(0, int((now - ts) / 86400))


def _meta(g) -> dict:
    r = db.q(g, Q["overview"])[0]
    return {"snapshot_ts": r[0], "n_prs": r[1], "half_life_days": r[2], "people": r[3], "active": r[4], "modules": r[5]}


def module_stats(g) -> dict[str, dict]:
    keys = ["id", "n_prs", "imp", "tot", "act_tot", "top", "top_share", "bus", "bus_active"]
    return {r[0]: dict(zip(keys, r)) for r in db.q(g, Q["module_stats"], {"min_prs": MIN_PRS})}


def tier(s: dict) -> str:
    cover = s["act_tot"] / s["tot"] if s["tot"] else 0.0
    if cover < ORPHAN_AT or (s["bus_active"] == 1 and (s["imp"] or 0) >= 0.5):
        return "critical"
    return {1: "high", 2: "medium"}.get(s["bus_active"], "low")


# ----------------------------------------------------------------------------- tools

def overview(tenant: str) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    m = _meta(g)
    return result("overview", "answered", m, queries=["overview"], t0=t0)


def find_modules(tenant: str, query: str, limit: int = 8) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    c = resolve_module(g, query, limit)
    if not c:
        return result("find_modules", "not_in_graph", {"query": query}, note=f"Nothing in the graph matches '{query}'.", queries=["module_names"], t0=t0)
    return result("find_modules", "answered", {"matches": c}, queries=["module_names"], t0=t0)


def module_risk(tenant: str, module: str) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    cands = resolve_module(g, module, 3)
    if not cands:
        return _unknown("module_risk", "module", module, [], t0)
    mid = cands[0]["id"]
    stats = module_stats(g).get(mid)
    if not stats:
        return result("module_risk", "not_in_graph", {"module": mid, "n_prs": cands[0]["n_prs"]},
                      note=f"{short(mid)} has too little history (fewer than {MIN_PRS} merged PRs) or is not a code/CI module.", t0=t0)
    now = _meta(g)["snapshot_ts"]
    holders = [{"person": p, "share": round(s, 3), "authored": a, "reviewed": rv, "last_active_days": _days(now, last), "active": bool(act)}
               for p, s, a, rv, last, act in db.q(g, Q["module_holders"], {"m": mid})]
    ev = [{"label": f"{t[:80]}", "url": u} for u, t, _ in db.q(g, Q["module_evidence"], {"m": mid})]
    cover = stats["act_tot"] / stats["tot"]
    d = {"module": mid, "short": short(mid), "tier": tier(stats), "bus_factor": stats["bus"], "bus_factor_active": stats["bus_active"],
         "active_cover": round(cover, 3), "importance": round(stats["imp"] or 0, 3), "merged_prs": stats["n_prs"], "holders": holders}
    nodes = [mnode(mid, tier=d["tier"])] + [pnode(h["person"], active=h["active"]) for h in holders[:5]]
    edges = [edge(f"person:{h['person']}", f"module:{mid}", "KNOWS", share=h["share"]) for h in holders[:5]]
    return result("module_risk", "answered", d, {"nodes": nodes, "edges": edges}, ev, ["module_stats", "module_holders", "module_evidence"], t0=t0)


def risk_scan(tenant: str, limit: int = 10) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    now = _meta(g)["snapshot_ts"]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows = []
    for mid, s in module_stats(g).items():
        rows.append({"module": mid, "short": short(mid), "tier": tier(s), "bus_factor_active": s["bus_active"], "top": s["top"],
                     "top_share": round(s["top_share"], 3), "active_cover": round(s["act_tot"] / s["tot"], 3), "importance": round(s["imp"] or 0, 3)})
    rows.sort(key=lambda r: (order[r["tier"]], -r["importance"]))
    counts = {t: sum(1 for r in rows if r["tier"] == t) for t in order}
    top = rows[:max(1, min(int(limit), 25))]
    nodes = [mnode(r["module"], tier=r["tier"]) for r in top] + [pnode(p) for p in dict.fromkeys(r["top"] for r in top)]
    edges = [edge(f"person:{r['top']}", f"module:{r['module']}", "KNOWS", share=r["top_share"]) for r in top]
    return result("risk_scan", "answered", {"counts": counts, "modules": top, "total_modules": len(rows)}, {"nodes": nodes, "edges": edges}, queries=["module_stats"], t0=t0)


def keystones(tenant: str, limit: int = 8) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    rows = db.q(g, Q["keystones"], {"min_prs": MIN_PRS, "limit": max(1, min(int(limit), 25))})
    if not rows:
        return result("keystones", "not_in_graph", note="No active person's departure would orphan a module.", queries=["keystones"], t0=t0)
    out, nodes, edges = [], [], []
    for p, n, sole, w, broker, mods in rows:
        mods = sorted(mods, key=lambda x: (not x["orphan"], -(x["imp"] or 0)))
        out.append({"person": p, "would_orphan": int(n), "sole_holder_of": int(sole), "risk_weight": round(w, 2), "broker_score": round(broker or 0, 1),
                    "examples": [{"module": short(x["m"]), "share": round(x["share"], 3), "orphan": x["orphan"]} for x in mods[:4]]})
        nodes.append(pnode(p, keystone=True))
        for x in mods[:3]:
            nodes.append(mnode(x["m"]))
            edges.append(edge(f"person:{p}", f"module:{x['m']}", "KNOWS", share=round(x["share"], 3)))
    return result("keystones", "answered", {"people": out}, {"nodes": nodes, "edges": edges}, queries=["keystones"], t0=t0)


def what_if_leaves(tenant: str, person: str) -> dict:
    """Counterfactual: fork the graph, delete the person, recompute the same stats, diff. The live graph is never touched."""
    t0 = time.time()
    g = db.graph(tenant)
    pid, near = resolve_person(g, person)
    if not pid:
        return _unknown("what_if_leaves", "person", person, near, t0)
    before = module_stats(g)
    with db.fork(tenant) as f:
        db.q(f, "MATCH (p:Person {id: $p}) DETACH DELETE p", {"p": pid}, write=True)
        after = module_stats(f)
        isolated = {r[0] for r in db.q(f, Q["isolated_after"], {"min_prs": MIN_PRS})}
    mine = {r[0]: r for r in db.q(g, Q["person_modules"], {"p": pid, "min_prs": MIN_PRS, "limit": 400})}
    impact = []
    for mid, (_, share, imp) in mine.items():
        b, a = before.get(mid), after.get(mid)
        if not b or share < 0.05:
            continue
        retained = (a["act_tot"] / b["tot"]) if a else 0.0
        status = "orphaned" if retained < ORPHAN_AT else ("fragile" if (a and a["bus_active"] == 1 and b["bus_active"] >= 2) or retained < COVER else "ok")
        if status == "ok":
            continue
        impact.append({"module": mid, "short": short(mid), "status": status, "their_share": round(share, 3), "retained_active": round(retained, 3),
                       "bus_before": b["bus_active"], "bus_after": a["bus_active"] if a else 0, "importance": round(imp or 0, 3),
                       "next_holder": a["top"] if a else None, "isolated": mid in isolated})
    impact.sort(key=lambda r: (r["status"] != "orphaned", -r["importance"], -r["their_share"]))
    summary = {"person": pid, "orphaned": sum(r["status"] == "orphaned" for r in impact), "fragile": sum(r["status"] == "fragile" for r in impact),
               "modules_touched": len(mine), "isolated": len(isolated & set(mine))}
    if not impact:
        return result("what_if_leaves", "answered", {**summary, "impact": []}, {"nodes": [pnode(pid)], "edges": []},
                      note=f"If {pid} left, no module would be orphaned or newly fragile.", queries=["module_stats"], t0=t0)
    top = impact[:8]
    nodes = [pnode(pid, leaving=True)] + [mnode(r["module"], status=r["status"]) for r in top]
    edges = [edge(f"person:{pid}", f"module:{r['module']}", "KNOWS", share=r["their_share"]) for r in top]
    return result("what_if_leaves", "answered", {**summary, "impact": impact[:12]}, {"nodes": nodes, "edges": edges},
                  queries=["module_stats", "person_modules", "isolated_after"], note="Computed on a GRAPH.COPY fork; live graph untouched.", t0=t0)


def successors(tenant: str, person: str, module: str | None = None, limit: int = 5) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    pid, near = resolve_person(g, person)
    if not pid:
        return _unknown("successors", "person", person, near, t0)
    if module:
        c = resolve_module(g, module, 1)
        if not c:
            return _unknown("successors", "module", module, [], t0)
        targets = [c[0]["id"]]
    else:
        targets = [r[0] for r in db.q(g, Q["person_modules"], {"p": pid, "min_prs": MIN_PRS, "limit": 6})]
    if not targets:
        return result("successors", "not_in_graph", note=f"{pid} holds no meaningful knowledge in any tracked module.", t0=t0)
    args = {"p": pid, "targets": targets}
    direct = {c: d for c, d in db.q(g, Q["successor_direct"], args)}
    adj = {c: (a, via) for c, a, via in db.q(g, Q["successor_adjacent"], args)}
    rev = {c: (n, url) for c, n, url in db.q(g, Q["successor_reviewed"], args)}
    amax = max([a for a, _ in adj.values()] or [1.0]) or 1.0
    rows = []
    for cand in set(direct) | set(adj) | set(rev):
        d = direct.get(cand, 0.0) / len(targets)
        a = adj.get(cand, (0.0, None))
        r = rev.get(cand, (0, None))
        score = d + 0.5 * min(1.0, r[0] / 10) + 0.25 * (a[0] / amax)
        if score > 0:
            rows.append({"person": cand, "score": round(score, 3), "already_knows": round(d, 3), "reviewed_their_prs": r[0],
                         "adjacent_via": short(a[1]) if a[1] else None, "evidence_pr": r[1]})
    rows.sort(key=lambda r: -r["score"])
    rows = rows[:max(1, min(int(limit), 10))]
    if not rows:
        return result("successors", "not_in_graph", {"targets": targets}, note="No active candidate shares any history with those modules.", t0=t0)
    nodes = [pnode(pid, leaving=True)] + [pnode(r["person"], candidate=True) for r in rows] + [mnode(t) for t in targets[:4]]
    edges = [edge(f"person:{pid}", f"module:{t}", "KNOWS") for t in targets[:4]]
    edges += [edge(f"person:{r['person']}", f"person:{pid}", "REVIEWED_FOR", n=r["reviewed_their_prs"]) for r in rows if r["reviewed_their_prs"]]
    return result("successors", "answered", {"person": pid, "targets": [short(t) for t in targets], "candidates": rows}, {"nodes": nodes, "edges": edges},
                  [{"label": "a PR they reviewed", "url": r["evidence_pr"]} for r in rows[:3] if r["evidence_pr"]],
                  ["person_modules", "successor_direct", "successor_adjacent", "successor_reviewed"], t0=t0)


def who_knows(tenant: str, topic: str, limit: int = 6) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    c = resolve_module(g, topic, 3)
    if not c:
        return result("who_knows", "not_in_graph", {"topic": topic}, note=f"Nothing in this graph is about '{topic}'. The graph only knows code and CI areas of the indexed repos.", queries=["module_names"], t0=t0)
    mid = c[0]["id"]
    now = _meta(g)["snapshot_ts"]
    rows = [{"person": p, "share": round(s, 3), "authored": a, "reviewed": rv, "last_active_days": _days(now, last), "active": bool(act)}
            for p, s, a, rv, last, act in db.q(g, Q["who_knows"], {"m": mid, "limit": max(1, min(int(limit), 12))})]
    nodes = [mnode(mid)] + [pnode(r["person"], active=r["active"]) for r in rows]
    edges = [edge(f"person:{r['person']}", f"module:{mid}", "KNOWS", share=r["share"]) for r in rows]
    ev = [{"label": t[:80], "url": u} for u, t, _ in db.q(g, Q["module_evidence"], {"m": mid})]
    return result("who_knows", "answered", {"module": mid, "short": short(mid), "other_matches": [x["short"] for x in c[1:]], "people": rows},
                  {"nodes": nodes, "edges": edges}, ev, ["who_knows", "module_evidence"], t0=t0)


def knowledge_map(tenant: str) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    mods = {c: (ms, prs) for c, ms, prs in db.q(g, Q["cluster_modules"], {"min_prs": MIN_PRS})}
    terr = []
    for c, tot, top, bus in db.q(g, Q["clusters"], {"min_prs": MIN_PRS}):
        ms, prs = mods.get(c, ([], 0))
        if len(ms) < 3:
            continue
        repos = [m.partition(":")[0].split("/")[-1] for m in ms]
        terr.append({"territory": max(set(repos), key=repos.count), "modules": len(ms), "merged_prs": prs, "bus_factor": bus,
                     "holders": [{"person": h["p"], "share": round(h["s"] / tot, 3), "active": bool(h["act"])} for h in top[:4]],
                     "solo_held": top[0]["s"] / tot >= COVER, "sample_modules": [short(m) for m in ms[:3]]})
    brokers = [{"person": p, "broker_score": round(b, 1)} for p, b in db.q(g, Q["brokers"], {"limit": 5})]
    if not terr:
        return result("knowledge_map", "not_in_graph", note="No module clusters found.", queries=["clusters"], t0=t0)
    terr.sort(key=lambda t: -t["merged_prs"])
    nodes = [pnode(t["holders"][0]["person"]) for t in terr[:6]] + [pnode(b["person"], broker=True) for b in brokers]
    return result("knowledge_map", "answered", {"territories": terr[:8], "brokers": brokers}, {"nodes": nodes, "edges": []},
                  queries=["cluster_modules", "clusters", "brokers"], t0=t0)


def path_between(tenant: str, a: str, b: str) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    ends = []
    for raw in (a, b):
        pid, near = resolve_person(g, raw)
        if pid:
            ends.append(("Person", pid))
            continue
        c = resolve_module(g, raw, 1)
        if c:
            ends.append(("Module", c[0]["id"]))
        else:
            return _unknown("path_between", "person or module", raw, near, t0)
    (la, ia), (lb, ib) = ends
    rows = db.q(g, Q["shortest_knowledge_path"] % (la, lb), {"a": ia, "b": ib})
    if not rows:
        return result("path_between", "not_in_graph", {"from": ia, "to": ib}, note="No chain of shared knowledge connects them.", queries=["shortest_knowledge_path"], t0=t0)
    nodes_raw, shares, w = rows[0]
    nodes = [pnode(n["id"]) if n["kind"] == "Person" else mnode(n["id"]) for n in nodes_raw]
    edges = [edge(nodes[i]["id"], nodes[i + 1]["id"], "KNOWS", share=round(s or 0, 3)) for i, s in enumerate(shares)]
    return result("path_between", "answered", {"from": ia, "to": ib, "hops": len(shares), "chain": [n["label"] for n in nodes]},
                  {"nodes": nodes, "edges": edges}, queries=["shortest_knowledge_path"], note="Weighted shortest path (algo.SPpaths); strong knowledge is cheap to walk.", t0=t0)


CATALOG = {f.__name__: f for f in (overview, find_modules, module_risk, risk_scan, keystones, what_if_leaves, successors, who_knows, knowledge_map, path_between)}
