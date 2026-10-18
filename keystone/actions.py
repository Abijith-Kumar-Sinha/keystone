"""Actions: the agent turns an approved Decision into artifacts a human can review and merge.

For each pairing it drafts (1) a CODEOWNERS patch diffed against the repo's REAL file and (2) an issue with the graph evidence.
Everything is a dry run stored as (:Action)-[:FOR]->(:Decision): nothing is posted. execute() can open the issue, but only in
the one repo named by KEYSTONE_GH_REPO and only with confirm=True.
"""
import difflib
import json
import os
import time
from functools import lru_cache
from pathlib import Path

import httpx

from . import db
from .memory import _id, _iso
from .tools import Q, _meta, result, short

Q["pick_decision"] = "MATCH (d:Decision) WHERE d.status = 'approved' AND ($d = '' OR d.id = $d) RETURN d.id, d.leaver, d.plan_json, d.as_of ORDER BY d.ts DESC LIMIT 1"
CACHE = Path(__file__).resolve().parent.parent / "data" / "codeowners.json"


@lru_cache(maxsize=1)
def _cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def codeowners(repo: str) -> tuple[str, str] | None:
    """(path, text) of the repo's real CODEOWNERS, or None. Read from the ingest-time cache (fetch.py); no network at runtime."""
    hit = _cache().get(repo)
    return (hit[0], hit[1]) if hit else None


def patch_for(repo: str, rules: list[tuple[str, list[str]]], note: str) -> dict:
    """Add owners to the rule for each path (or add the rule). Returns the unified diff against the real file."""
    cur = codeowners(repo)
    path, old = cur if cur else (".github/CODEOWNERS", "")
    lines = old.splitlines()
    new = list(lines)
    for pat, owners in rules:
        want = [f"@{o}" for o in owners]
        for i, ln in enumerate(new):
            tok = ln.split()
            if tok and not ln.lstrip().startswith("#") and tok[0].strip("/") == pat.strip("/"):
                new[i] = ln.rstrip() + "".join(f" {w}" for w in want if w not in tok)
                break
        else:
            new += ([""] if new and new[-1] else []) + [f"# {note}", f"{pat} {' '.join(want)}"]
    diff = "".join(difflib.unified_diff([l + "\n" for l in lines], [l + "\n" for l in new], f"a/{path}", f"b/{path}"))
    return {"file": path, "existing_file": cur is not None, "diff": diff}


def _issue(plan: dict, leaver: str, decision: str) -> tuple[str, str]:
    m, c = plan["module"], plan["candidate"]
    ev = f"\n- @{c} already reviewed {plan['evidence_reviews']} of @{leaver}'s PRs here: {plan['evidence']}" if plan.get("evidence") else ""
    return (f"[succession] Pair @{c} with @{leaver} on {m}",
            f"**Why now** - if @{leaver} became unavailable, `{m}` would be **{plan['status_before']}**: only {plan['retained_before']:.0%} of its accumulated "
            f"knowledge would remain with active contributors.\n\n"
            f"**Proposal** - @{c} authors about {plan['prs_needed']} of the next PRs touching `{m}`, with @{leaver} reviewing. "
            f"At the module's pace ({plan['pace_per_month']} PRs/month) that is roughly {plan['est_months']} months.\n\n"
            f"**Evidence from the knowledge graph**\n- @{leaver} holds {plan['their_share']:.0%} of the module's knowledge{ev}\n"
            f"- Simulated on a graph fork: retained knowledge goes {plan['retained_before']:.0%} -> {plan['retained_after']:.0%}\n\n"
            f"**Checklist**\n- [ ] @{c} takes the next PR in this area\n- [ ] @{leaver} reviews it and records any undocumented context\n"
            f"- [ ] Re-run the Keystone review in a month and compare\n\n"
            f"_Drafted by Keystone (decision `{decision}`, verified by the reviewer role on a fresh graph fork). Dry run: not posted._")


def draft_actions(tenant: str, decision_id: str | None = None) -> dict:
    t0 = time.time()
    g = db.graph(tenant)
    rows = db.q(g, Q["pick_decision"], {"d": decision_id or ""})
    if not rows:
        return result("draft_actions", "not_in_graph", note="No approved succession decision to act on. Run succession_review first.", t0=t0)
    did, leaver, plan_json, as_of = rows[0]
    plans = json.loads(plan_json or "[]")
    if not plans:
        return result("draft_actions", "not_in_graph", note="The decision has no stored plan.", t0=t0)
    mod_id = {short(r[0]): r[0] for r in db.q(g, "MATCH (m:Module) RETURN m.id")}
    by_repo: dict[str, list[dict]] = {}
    for p in plans:
        full = mod_id.get(p["module"])
        if full:
            by_repo.setdefault(full.partition(":")[0], []).append({**p, "full": full})
    actions = []
    for repo, ps in by_repo.items():
        rules = [("/" + p["full"].partition(":")[2].strip("/") + "/", [leaver, p["candidate"]]) for p in ps]
        patch = patch_for(repo, rules, f"Keystone succession pairing ({did})")
        actions.append({"id": _id("a"), "kind": "codeowners_patch", "repo": repo, "title": f"CODEOWNERS: add successors to {len(ps)} path(s)", "body": patch["diff"],
                        "file": patch["file"], "about": [leaver] + [p["candidate"] for p in ps] + [p["full"] for p in ps]})
        for p in ps:
            title, body = _issue(p, leaver, did)
            actions.append({"id": _id("a"), "kind": "issue_draft", "repo": repo, "title": title, "body": body, "file": None,
                            "about": [leaver, p["candidate"], p["full"]]})
    for a in actions:
        db.q(g, "CREATE (:Action {id: $id, kind: $k, status: 'drafted', repo: $r, title: $t, body: $b, ts: $ts, as_of: $as_of})",
             {"id": a["id"], "k": a["kind"], "r": a["repo"], "t": a["title"], "b": a["body"][:6000], "ts": int(time.time()), "as_of": as_of}, write=True)
        db.q(g, "MATCH (a:Action {id: $a}), (d:Decision {id: $d}) MERGE (a)-[:FOR]->(d)", {"a": a["id"], "d": did}, write=True)
        for ent in a.pop("about"):
            for lab in ("Person", "Module"):
                db.q(g, f"MATCH (a:Action {{id: $a}}), (x:{lab} {{id: $x}}) MERGE (a)-[:ABOUT]->(x)", {"a": a["id"], "x": ent}, write=True)
    nodes = [{"id": f"action:{a['id']}", "kind": "memory", "label": a["title"][:48]} for a in actions]
    return result("draft_actions", "answered", {"decision": did, "leaver": leaver, "actions": actions, "dry_run": True,
                  "real_codeowners_fetched": all(codeowners(r) is not None for r in by_repo)},
                  {"nodes": nodes, "edges": []}, queries=["pick_decision"], note="Dry run: drafts are stored in the graph; nothing was posted.", t0=t0)


def execute(tenant: str, action_id: str, confirm: bool = False) -> dict:
    """Open an issue draft as a real GitHub issue. Guarded: only the repo in KEYSTONE_GH_REPO, only with confirm=True."""
    t0 = time.time()
    target, token = os.environ.get("KEYSTONE_GH_REPO"), os.environ.get("GITHUB_TOKEN")
    if not (target and token):
        return result("execute", "not_in_graph", note="Posting is disabled: set KEYSTONE_GH_REPO (a repo you own) and GITHUB_TOKEN.", t0=t0)
    if not confirm:
        return result("execute", "not_in_graph", note="Refusing without confirm=true.", t0=t0)
    g = db.graph(tenant)
    rows = db.q(g, "MATCH (a:Action {id: $a}) WHERE a.kind = 'issue_draft' AND a.status = 'drafted' RETURN a.title, a.body", {"a": action_id})
    if not rows:
        return result("execute", "unknown_entity", {"asked": action_id}, note="No drafted issue with that id.", t0=t0)
    r = httpx.post(f"https://api.github.com/repos/{target}/issues", timeout=20, headers={"Authorization": f"bearer {token}"},
                   json={"title": rows[0][0], "body": rows[0][1].replace("Dry run: not posted.", f"Posted by Keystone on request ({_iso(int(time.time()))}).")})
    r.raise_for_status()
    url = r.json()["html_url"]
    db.q(g, "MATCH (a:Action {id: $a}) SET a.status = 'executed', a.url = $u", {"a": action_id, "u": url}, write=True)
    return result("execute", "answered", {"action": action_id, "issue": url}, None, [{"label": "GitHub issue", "url": url}], t0=t0)
