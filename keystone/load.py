"""Raw merged-PR JSON -> tenant graph.

Base facts (Person/PR/Module/Issue + AUTHORED/REVIEWED/TOUCHES/CLOSES) are loaded from the files;
everything *derived* (KNOWS, CO_KNOWS, CO_CHANGES, active flags) is computed inside FalkorDB with Cypher (see derive()).

CLI: python -m keystone.load TENANT data/raw/A.json [B.json ...] [--as-of 2026-04-15] [--half-life 365]
"""
import argparse, gzip, json, math, re, time
from datetime import datetime, timezone
from pathlib import Path

from . import db

BOTS = {"dependabot", "renovate", "github-actions", "copilot-swe-agent", "copilot", "codecov", "snyk-bot",
        "pre-commit-ci", "allcontributors", "imgbot", "mergify", "coderabbitai", "sonarcloud", "greenkeeper"}
GENERIC_ROOTS = {"src", "lib", "app", "apps", "packages", "pkg", "internal", "cmd", "components", "source",
                 "server", "client", "crates", "modules", "libs"}
NOISE = re.compile(r"(^|/)(node_modules|vendor|dist|build|target|__pycache__)/|"
                   r"(\.lock|package-lock\.json|pnpm-lock\.yaml|go\.sum|\.min\.js|\.map|\.svg|\.png|\.jpg|\.ico)$")
MAX_FILES = 300  # mass renames / formatter runs say nothing about who knows what
BATCH = 1000
ACTIVE_DAYS = 180


def to_ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def is_bot(a: dict | None) -> bool:
    if not a or not a.get("login"):
        return True
    low = a["login"].lower()
    return a.get("__typename") == "Bot" or low.endswith("[bot]") or low in BOTS


def module_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)"
    return "/".join(parts[:2]) if parts[0] in GENERIC_ROOTS and len(parts) > 2 else parts[0]


def kind_of(module: str) -> str:
    """code | ci | tests | docs | root. Risk tools look at code+ci only; tests/docs/root are noise for succession."""
    low = module.lower()
    if module == "(root)":
        return "root"
    if low.startswith((".github", ".circleci", ".gitlab", "ci", "scripts")):
        return "ci"
    if low.startswith(("test", "e2e", "__tests__", "spec", "tests")) or "/tests" in low:
        return "tests"
    if low.startswith(("doc", "website", "blog", "examples")):
        return "docs"
    return "code"


def parse(raw_files: list[Path], as_of: int | None):
    people, prs, touches, authored, reviewed, issues, closes = {}, [], [], [], [], {}, []
    repos, modules, skipped = set(), set(), 0

    def person(login: str, t: int):
        p = people.setdefault(login, {"id": login, "url": f"https://github.com/{login}"})
        return p

    for f in raw_files:
        slug = f.name.removesuffix(".gz").removesuffix(".json").replace("__", "/", 1)
        repos.add(slug)
        text = gzip.open(f, "rt", encoding="utf-8").read() if f.suffix == ".gz" else f.read_text(encoding="utf-8")
        for pr in json.loads(text):
            t = to_ts(pr["mergedAt"])
            if as_of and t > as_of:
                continue
            paths = [x["path"] for x in pr["files"]["nodes"] if not NOISE.search(x["path"])]
            if pr["changedFiles"] > MAX_FILES or not paths:
                skipped += 1
                continue
            pid = f"{slug}#{pr['number']}"
            per_mod: dict[str, int] = {}
            for p in paths:
                per_mod[module_of(p)] = per_mod.get(module_of(p), 0) + 1
            prs.append({"id": pid, "number": pr["number"], "title": pr["title"][:160], "url": pr["url"], "ts": t,
                        "repo": slug, "nmods": len(per_mod), "nfiles": len(paths)})
            for m, n in per_mod.items():
                mid = f"{slug}:{m}"
                modules.add((mid, slug, m))
                touches.append({"pr": pid, "m": mid, "files": n, "share": n / len(paths), "ex": [p for p in paths if module_of(p) == m][:3]})
            a = pr.get("author")
            if not is_bot(a):
                person(a["login"], t)
                authored.append({"p": a["login"], "pr": pid})
            seen = {a["login"]} if a and a.get("login") else set()
            for rv in pr["reviews"]["nodes"]:
                ra = rv.get("author")
                if is_bot(ra) or ra["login"] in seen:
                    continue
                seen.add(ra["login"])
                person(ra["login"], t)
                reviewed.append({"p": ra["login"], "pr": pid, "state": rv["state"]})
            for iss in pr["closingIssuesReferences"]["nodes"]:
                iid = f"{slug}#{iss['number']}"
                issues[iid] = {"id": iid, "title": iss["title"][:160], "url": iss["url"]}
                closes.append({"pr": pid, "i": iid})
    return {"people": list(people.values()), "prs": prs, "touches": touches, "authored": authored, "reviewed": reviewed,
            "issues": list(issues.values()), "closes": closes, "repos": sorted(repos),
            "modules": [{"id": i, "repo": r, "path": m, "kind": kind_of(m)} for i, r, m in sorted(modules)], "skipped": skipped}


def batched(g, cypher: str, rows: list[dict]):
    for i in range(0, len(rows), BATCH):
        g.query(cypher, {"rows": rows[i:i + BATCH]})


# Base facts, MERGE everywhere so a refresh can add newer PRs while agent memory in the same graph stays untouched:
# (title, Cypher, key into parse()'s result).
BASE: list[tuple[str, str, str]] = [
    ("Repositories", "UNWIND $rows AS row MERGE (n:Repo {id:row.id}) SET n.url = 'https://github.com/' + row.id", "repos"),
    ("Modules (top-level directory, or two levels under src/app/lib/...)",
     "UNWIND $rows AS row MERGE (n:Module {id:row.id}) SET n.repo = row.repo, n.path = row.path, n.kind = row.kind", "modules"),
    ("Module -[:IN]-> Repo", "UNWIND $rows AS row MATCH (m:Module {id:row.id}), (x:Repo {id:row.repo}) MERGE (m)-[:IN]->(x)", "modules"),
    ("People (GitHub logins; bots excluded; no emails)", "UNWIND $rows AS row MERGE (n:Person {id:row.id}) SET n.url = row.url", "people"),
    ("Merged pull requests",
     "UNWIND $rows AS row MERGE (n:PR {id:row.id}) SET n.number = row.number, n.title = row.title, n.url = row.url, n.ts = row.ts, "
     "n.repo = row.repo, n.nmods = row.nmods, n.nfiles = row.nfiles", "prs"),
    ("Issues closed by PRs", "UNWIND $rows AS row MERGE (n:Issue {id:row.id}) SET n.title = row.title, n.url = row.url", "issues"),
    ("Person -[:AUTHORED]-> PR", "UNWIND $rows AS row MATCH (p:Person {id:row.p}), (x:PR {id:row.pr}) MERGE (p)-[:AUTHORED]->(x)", "authored"),
    ("Person -[:REVIEWED]-> PR",
     "UNWIND $rows AS row MATCH (p:Person {id:row.p}), (x:PR {id:row.pr}) MERGE (p)-[e:REVIEWED]->(x) SET e.state = row.state", "reviewed"),
    ("PR -[:TOUCHES {share}]-> Module (share = fraction of the PR's files that land in the module)",
     "UNWIND $rows AS row MATCH (x:PR {id:row.pr}), (m:Module {id:row.m}) MERGE (x)-[e:TOUCHES]->(m) "
     "SET e.files = row.files, e.share = row.share, e.ex = row.ex", "touches"),
    ("PR -[:CLOSES]-> Issue", "UNWIND $rows AS row MATCH (x:PR {id:row.pr}), (i:Issue {id:row.i}) MERGE (x)-[:CLOSES]->(i)", "closes"),
]

# Everything derived from the base facts, in execution order: (title, Cypher). Parameters: $now $tau $cut.
# docs/QUERIES.md is generated from this list, so the documentation is the code that runs.
DERIVE: list[tuple[str, str]] = [
    ("Reset derived edges", "MATCH ()-[r:KNOWS|CO_KNOWS|CO_CHANGES]->() DELETE r"),
    ("Person activity window: first/last PR, and `active` (a PR within 180 days of the snapshot)",
     "MATCH (p:Person)-[:AUTHORED|REVIEWED]->(pr:PR) WITH p, min(pr.ts) AS f, max(pr.ts) AS l "
     "SET p.first_ts = f, p.last_ts = l, p.active = (l >= $cut)"),
    ("Module size: merged PRs touching it",
     "MATCH (m:Module)<-[:TOUCHES]-(pr:PR) WITH m, count(pr) AS n SET m.n_prs = n"),
    ("Knowledge from authoring: share of each PR that lands in the module, decayed by age (half-life 365 days)",
     "MATCH (p:Person)-[:AUTHORED]->(pr:PR)-[t:TOUCHES]->(m:Module) "
     "WITH p, m, count(pr) AS n, sum(t.share * exp(-1.0 * ($now - pr.ts) / $tau)) AS s, max(pr.ts) AS last "
     "MERGE (p)-[k:KNOWS]->(m) SET k.authored = n, k.a_score = s, k.last = last"),
    ("Knowledge from reviewing: weaker (0.4) but real; this is how knowledge spreads",
     "MATCH (p:Person)-[:REVIEWED]->(pr:PR)-[t:TOUCHES]->(m:Module) "
     "WITH p, m, count(pr) AS n, sum(0.4 * t.share * exp(-1.0 * ($now - pr.ts) / $tau)) AS s, max(pr.ts) AS last "
     "MERGE (p)-[k:KNOWS]->(m) "
     "SET k.reviewed = n, k.r_score = s, k.last = CASE WHEN k.last IS NULL OR last > k.last THEN last ELSE k.last END"),
    ("Total knowledge score per KNOWS edge",
     "MATCH ()-[k:KNOWS]->() SET k.score = coalesce(k.a_score, 0.0) + coalesce(k.r_score, 0.0), "
     "k.authored = coalesce(k.authored, 0), k.reviewed = coalesce(k.reviewed, 0)"),
    ("Module total knowledge", "MATCH (m:Module)<-[k:KNOWS]-() WITH m, sum(k.score) AS t SET m.total = t"),
    ("Share of the module each person holds, and an edge cost (strong knowledge is cheap to walk, so weighted shortest paths prefer real expertise)",
     "MATCH (p:Person)-[k:KNOWS]->(m:Module) SET k.share = k.score / m.total, k.cost = 1.01 - k.score / m.total"),
    ("CO_KNOWS: who overlaps with whom, both directions so graph algorithms can walk it",
     "MATCH (a:Person)-[x:KNOWS]->(m:Module)<-[y:KNOWS]-(b:Person) WHERE a.id < b.id AND x.share >= 0.05 AND y.share >= 0.05 "
     "WITH a, b, sum(CASE WHEN x.score < y.score THEN x.score ELSE y.score END) AS w, count(m) AS shared "
     "MERGE (a)-[c:CO_KNOWS]->(b) SET c.w = w, c.shared = shared "
     "MERGE (b)-[c2:CO_KNOWS]->(a) SET c2.w = w, c2.shared = shared"),
    ("CO_CHANGES: logical coupling, modules that change together in the same PR",
     "MATCH (a:Module)<-[:TOUCHES]-(pr:PR)-[:TOUCHES]->(b:Module) WHERE a.id < b.id AND pr.nmods <= 12 "
     "WITH a, b, count(pr) AS n WHERE n >= 2 "
     "MERGE (a)-[c:CO_CHANGES]->(b) SET c.n = n "
     "MERGE (b)-[c2:CO_CHANGES]->(a) SET c2.n = n"),
    ("Reset algorithm outputs (modules)", "MATCH (m:Module) SET m.importance = 0.0, m.cluster = -1"),
    ("Reset algorithm outputs (people)", "MATCH (p:Person) SET p.broker = 0.0"),
]

# Graph algorithms, run once at load and stored as properties. (required relationship type, title, statements)
# A tiny org may have no co-changed modules and the algorithms reject an unknown type, hence the guard.
ALGOS: list[tuple[str, str, list[str]]] = [
    ("CO_CHANGES", "algo.pageRank over co-change coupling -> Module.importance (how load-bearing is a module)",
     ["CALL algo.pageRank('Module', 'CO_CHANGES') YIELD node, score SET node.importance = score",
      "MATCH (m:Module) WITH max(m.importance) AS mx WHERE mx > 0 MATCH (m:Module) SET m.importance = m.importance / mx"]),
    ("CO_CHANGES", "algo.labelPropagation over co-change coupling -> Module.cluster (which modules form one subsystem)",
     ["CALL algo.labelPropagation({nodeLabels:['Module'], relationshipTypes:['CO_CHANGES']}) YIELD node, communityId SET node.cluster = communityId"]),
    ("CO_KNOWS", "algo.betweenness over knowledge overlap -> Person.broker (who bridges otherwise separate people)",
     ["CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['CO_KNOWS'], samplingSize: 300, samplingSeed: 7}) YIELD node, score SET node.broker = score"]),
]


def derive(g, now: int, half_life_days: int, tenant: str, n_prs: int):
    """All derived knowledge, computed in-graph. Idempotent: wipes and rebuilds derived edges only."""
    p = {"now": now, "tau": half_life_days * 86400 / math.log(2), "cut": now - ACTIVE_DAYS * 86400}
    for _, cypher in DERIVE:
        g.query(cypher, p)
    have = {r[0] for r in g.ro_query("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType").result_set}
    for needs, _, statements in ALGOS:
        if needs in have:
            for cypher in statements:
                g.query(cypher)
    g.query("MATCH (x:Meta {id:'meta'}) DETACH DELETE x")
    g.query("CREATE (:Meta {id:'meta', tenant:$t, snapshot_ts:$now, half_life_days:$h, active_days:$a, n_prs:$n, loaded_at:$l})",
            {"t": tenant, "now": now, "h": half_life_days, "a": ACTIVE_DAYS, "n": n_prs, "l": int(time.time())})


def load(tenant: str, raw_files: list[Path], as_of: str | None = None, half_life_days: int = 365, reset: bool = True) -> dict:
    t0 = time.time()
    as_of_ts = int(datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc).timestamp()) if as_of else None
    d = parse(raw_files, as_of_ts)
    if not d["prs"]:
        raise SystemExit("no PRs after filtering")
    now = as_of_ts or max(p["ts"] for p in d["prs"])
    db.set_timeout_ms(60000)
    if reset and db.exists(tenant):
        db.graph(tenant).delete()
    g = db.graph(tenant)
    for label in ("Person", "Module", "PR", "Repo", "Issue", "Finding", "Decision", "Task", "Session", "Snapshot", "Run", "Step"):
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except Exception:
            pass  # index exists (refresh path)
    d["repos"] = [{"id": r} for r in d["repos"]]
    for _, cypher, key in BASE:
        batched(g, cypher, d[key])
    derive(g, now, half_life_days, tenant, len(d["prs"]))
    stats = {k: len(d[k]) for k in ("people", "prs", "modules", "issues", "touches", "authored", "reviewed")}
    stats.update(skipped_bulk=d["skipped"], seconds=round(time.time() - t0, 1), snapshot=datetime.fromtimestamp(now, timezone.utc).date().isoformat())
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--as-of")
    ap.add_argument("--half-life", type=int, default=365)
    ap.add_argument("--refresh", action="store_true", help="upsert newer PRs into the existing graph; agent memory is kept")
    a = ap.parse_args()
    print(load(a.tenant, [Path(f) for f in a.files], a.as_of, a.half_life, reset=not a.refresh))
