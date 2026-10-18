"""Succession review: three roles coordinate ONLY through graph state.

  Analyst  -> reads the graph (what-if on a fork, successor ranking), writes a Finding
  Planner  -> reads open tasks (earlier sessions!) to respect capacity, simulates the plan on a fork, writes a Decision + Tasks
  Reviewer -> reads the Decision/Tasks back FROM THE GRAPH, re-verifies on a fresh fork, approves or sends back

Each step is a (:Step) node chained by NEXT; NEXT.handoff is true when the role changes. A later session can replay who
decided what, and `changes_since` checks the plan against real PR activity.
"""
import json
import math
import time

from . import db
from . import tools as T
from .memory import _id, _iso, remember, snapshot, start_session
from .tools import COVER, MIN_PRS, ORPHAN_AT, Q, _meta, _unknown, edge, mnode, pnode, resolve_person, result, short

CAPACITY = 3          # open pairing tasks one person may carry, counting tasks from earlier sessions
TARGET_SHARE = 0.30   # a successor should hold ~30% of the module's accumulated knowledge
AUTHOR_WEIGHT = 0.8   # one authored PR adds ~0.8 knowledge to its module (share of the PR that lands there, decay ~1)

Q["task_load"] = "MATCH (t:Task) WHERE t.status = 'open' AND t.cand IS NOT NULL RETURN t.cand, count(t)"
Q["pace"] = "MATCH (m:Module {id: $m})<-[:TOUCHES]-(pr:PR) WHERE pr.ts >= $since RETURN count(pr)"
Q["plan_tasks"] = "MATCH (t:Task)-[:IMPLEMENTS]->(d:Decision {id: $d}) RETURN t.cand, t.module, t.target_share, t.id"
Q["pr_exists"] = "MATCH (pr:PR {url: $u}) RETURN count(pr)"
Q["share_of"] = "MATCH (p:Person {id: $c})-[k:KNOWS]->(m:Module {id: $m}) RETURN k.share"


class _Run:
    """Writes the Run/Step chain as the roles work, so the coordination itself is graph state."""

    def __init__(self, g, goal: str, session: str):
        self.g, self.n, self.prev = g, 0, None
        self.id = _id("run")
        db.q(g, "CREATE (:Run {id: $id, goal: $goal, ts: $ts, as_of: $as_of, status: 'running'})",
             {"id": self.id, "goal": goal, "ts": int(time.time()), "as_of": _meta(g)["snapshot_ts"]}, write=True)
        db.q(g, "MATCH (s:Session {id: $s}), (r:Run {id: $r}) MERGE (s)-[:STARTED]->(r)", {"s": session, "r": self.id}, write=True)
        self.steps: list[dict] = []

    def step(self, by: str, action: str, summary: str, produced: list[tuple[str, str]] = ()):
        self.n += 1
        sid = f"{self.id}-{self.n}"
        db.q(self.g, "MATCH (r:Run {id: $r}) CREATE (r)-[:HAS_STEP]->(:Step {id: $id, n: $n, by: $by, action: $a, summary: $s, ts: $ts})",
             {"r": self.id, "id": sid, "n": self.n, "by": by, "a": action, "s": summary[:300], "ts": int(time.time())}, write=True)
        handoff = bool(self.prev and self.prev["by"] != by)
        if self.prev:
            db.q(self.g, "MATCH (a:Step {id: $a}), (b:Step {id: $b}) CREATE (a)-[:NEXT {handoff: $h}]->(b)", {"a": self.prev["id"], "b": sid, "h": handoff}, write=True)
        for label, nid in produced:
            db.q(self.g, f"MATCH (s:Step {{id: $s}}), (n:{label} {{id: $n}}) MERGE (s)-[:PRODUCED]->(n)", {"s": sid, "n": nid}, write=True)
        self.prev = {"id": sid, "by": by}
        self.steps.append({"n": self.n, "by": by, "action": action, "summary": summary, "handoff": handoff})

    def finish(self, status: str):
        db.q(self.g, "MATCH (r:Run {id: $r}) SET r.status = $s", {"r": self.id, "s": status}, write=True)


def _apply_plan(f, plans: list[dict], leaver: str, totals: dict[str, float]) -> dict:
    """On a fork: add the planned knowledge for each successor, remove the leaver, return the resulting module stats."""
    for p in plans:
        boost = TARGET_SHARE * totals[p["module"]]
        db.q(f, "MATCH (c:Person {id: $c}), (m:Module {id: $m}) MERGE (c)-[k:KNOWS]->(m) "
                "SET k.score = coalesce(k.score, 0.0) + $b", {"c": p["candidate"], "m": p["module"], "b": boost}, write=True)
    db.q(f, "MATCH (p:Person {id: $p}) DETACH DELETE p", {"p": leaver}, write=True)
    return T.module_stats(f)


def succession_review(tenant: str, person: str, user: str = "anon") -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    pid, near = resolve_person(g, person)
    if not pid:
        return _unknown("succession_review", "person", person, near, t0)
    meta = _meta(g)
    session = start_session(tenant, "workflow", user)
    run = _Run(g, f"succession review for {pid}", session)

    # ---- Analyst
    wi = T.what_if_leaves(tenant, pid)
    risky = [r for r in wi["data"].get("impact", []) if r["status"] in ("orphaned", "fragile")][:5]
    if not risky:
        run.step("analyst", "what_if_leaves", f"{pid} leaving orphans or weakens nothing.")
        run.finish("done")
        return result("succession_review", "answered", {"person": pid, "plans": [], "steps": run.steps, "run": run.id},
                      note=f"No succession plan needed: if {pid} left, no tracked module would be orphaned or newly fragile.", t0=t0)
    finding = remember(tenant, "finding", f"If {pid} leaves: {wi['data']['orphaned']} modules orphaned, {wi['data']['fragile']} fragile. "
                       f"Worst: {', '.join(r['short'] for r in risky[:3])}.", [pid] + [r["module"] for r in risky], session, status="note")
    load = dict(db.q(g, Q["task_load"]))
    plans = []
    for r in risky:
        sc = T.successors(tenant, pid, module=r["module"], limit=6)
        for c in sc["data"].get("candidates", []):
            if load.get(c["person"], 0) < CAPACITY:
                load[c["person"]] = load.get(c["person"], 0) + 1
                plans.append({"module": r["module"], "short": r["short"], "candidate": c["person"], "why": c, "status_before": r["status"],
                              "retained_before": r["retained_active"], "their_share": r["their_share"]})
                break
    n_risk = wi["data"]["orphaned"] + wi["data"]["fragile"]          # the plan covers the 5 most load-bearing; say how many the what-if found
    scope = f"{len(risky)} at-risk modules" if n_risk <= len(risky) else f"{n_risk} modules orphaned or fragile, planning for the {len(risky)} most load-bearing"
    run.step("analyst", "what_if_leaves + successors",
             f"{scope}; matched {len(plans)} successors within capacity ({CAPACITY} open pairings each, earlier sessions included).",
             [("Finding", finding["data"]["id"])])
    if not plans:
        run.finish("done")
        return result("succession_review", "answered", {"person": pid, "plans": [], "steps": run.steps, "run": run.id},
                      note="Everyone qualified is already at pairing capacity.", t0=t0)

    # ---- Planner: simulate the whole plan on a fork, then write the Decision and Tasks
    before = T.module_stats(g)
    totals = {m: s["tot"] for m, s in before.items()}
    since = meta["snapshot_ts"] - 180 * 86400
    for p in plans:
        tot = totals[p["module"]]
        prs = math.ceil(TARGET_SHARE * tot / AUTHOR_WEIGHT)
        pace = db.q(g, Q["pace"], {"m": p["module"], "since": since})[0][0] / 6.0
        base = (db.q(g, Q["share_of"], {"c": p["candidate"], "m": p["module"]}) or [[0.0]])[0][0] or 0.0
        p.update(prs_needed=prs, pace_per_month=round(pace, 1), est_months=round(prs / max(pace, 0.5), 1), baseline_share=round(base, 4))
    with db.fork(tenant) as f:
        after = _apply_plan(f, plans, pid, totals)
    for p in plans:
        a = after.get(p["module"])
        p.update(retained_after=round(a["act_tot"] / totals[p["module"]], 3) if a else 0.0, bus_after=a["bus_active"] if a else 0)
    decision = remember(tenant, "decision", f"Succession plan for {pid}: pair {len(plans)} successors on the modules only {pid} really holds.",
                        [pid] + [p["module"] for p in plans] + [p["candidate"] for p in plans], session, status="proposed", leaver=pid, author="planner")
    did = decision["data"]["id"]
    task_ids = []
    for p in plans:
        t = remember(tenant, "task", f"{p['candidate']} authors ~{p['prs_needed']} PRs in {p['short']} with {pid} reviewing "
                     f"(~{p['est_months']} months at {p['pace_per_month']} PRs/month).", [p["candidate"], p["module"], pid], session,
                     status="open", cand=p["candidate"], module=p["module"], baseline_share=p["baseline_share"],
                     target_share=round(p["baseline_share"] + TARGET_SHARE * (1 - p["baseline_share"]), 4), prs_needed=p["prs_needed"], author="planner")
        db.q(g, "MATCH (t:Task {id: $t}), (d:Decision {id: $d}) MERGE (t)-[:IMPLEMENTS]->(d)", {"t": t["data"]["id"], "d": did}, write=True)
        task_ids.append(("Task", t["data"]["id"]))
    run.step("planner", "simulate_plan + propose",
             f"Simulated on a fork: {sum(p['retained_after'] >= ORPHAN_AT for p in plans)}/{len(plans)} modules stop being orphaned. Wrote 1 decision, {len(plans)} tasks.",
             [("Decision", did)] + task_ids)

    # ---- Reviewer: trusts nothing the planner computed. Reads the tasks back from the graph and recomputes.
    rows = db.q(g, Q["plan_tasks"], {"d": did})
    check = [{"candidate": c, "module": m, "task": t} for c, m, _, t in rows]
    fresh_totals = {m: s["tot"] for m, s in T.module_stats(g).items()}
    with db.fork(tenant) as f2:
        verify = _apply_plan(f2, check, pid, fresh_totals)
    load_now = dict(db.q(g, Q["task_load"]))
    failures, ok = [], 0
    for c in check:
        a = verify.get(c["module"])
        retained = (a["act_tot"] / fresh_totals[c["module"]]) if a else 0.0
        ev = next((p["why"].get("evidence_pr") for p in plans if p["module"] == c["module"]), None)
        problems = []
        if retained < ORPHAN_AT:
            problems.append(f"still orphaned after plan ({retained:.0%} retained)")
        if load_now.get(c["candidate"], 0) > CAPACITY:
            problems.append(f"{c['candidate']} over capacity")
        if ev and not db.q(g, Q["pr_exists"], {"u": ev})[0][0]:
            problems.append("cited PR not found in graph")
        if problems:
            failures.append({"module": short(c["module"]), "candidate": c["candidate"], "problems": problems})
        else:
            ok += 1
    verdict = "approved" if not failures else "needs_changes"
    db.q(g, "MATCH (d:Decision {id: $d}) SET d.status = $s, d.reviewed_by = 'reviewer', d.verified = $ok, d.checked = $n",
         {"d": did, "s": verdict, "ok": ok, "n": len(check)}, write=True)
    run.step("reviewer", "verify_on_fresh_fork", f"Re-verified {len(check)} pairings from graph state: {ok} pass. Verdict: {verdict}.", [("Decision", did)])
    run.finish(verdict)
    snap = snapshot(tenant, session)

    nodes = [pnode(pid, leaving=True)] + [mnode(p["module"]) for p in plans] + [pnode(p["candidate"], candidate=True) for p in plans]
    edges = [edge(f"person:{pid}", f"module:{p['module']}", "KNOWS", share=p["their_share"]) for p in plans]
    edges += [edge(f"person:{p['candidate']}", f"module:{p['module']}", "PLANNED", months=p["est_months"]) for p in plans]
    plan_out = [{"module": p["short"], "candidate": p["candidate"], "prs_needed": p["prs_needed"], "est_months": p["est_months"],
                 "pace_per_month": p["pace_per_month"], "status_before": p["status_before"], "retained_before": p["retained_before"],
                 "retained_after": p["retained_after"], "bus_after": p["bus_after"], "their_share": p["their_share"],
                 "evidence": p["why"].get("evidence_pr"), "evidence_reviews": p["why"].get("reviewed_their_prs", 0)} for p in plans]
    db.q(g, "MATCH (d:Decision {id: $d}) SET d.plan_json = $p", {"d": did, "p": json.dumps(plan_out)}, write=True)
    data = {"person": pid, "run": run.id, "decision": {"id": did, "status": verdict}, "steps": run.steps, "failures": failures,
            "plans": plan_out, "snapshot": snap["data"]["id"], "as_of": _iso(meta["snapshot_ts"])}
    return result("succession_review", "answered", data, {"nodes": nodes, "edges": edges},
                  [{"label": f"{p['candidate']} reviewed {pid}'s PRs", "url": p["why"]["evidence_pr"]} for p in plans if p["why"].get("evidence_pr")][:4],
                  ["what_if_leaves", "successors", "task_load", "pace", "plan_tasks"], note="Planned and verified on GRAPH.COPY forks; live graph untouched except the memory nodes.", t0=t0)
