"""Backtest: does the graph's successor ranking predict who ACTUALLY picks up a module's knowledge?

  python -m bench.backtest --tenant falkordb --glob "data/raw/FalkorDB__*.json" --t0 2026-04-15

Protocol (no peeking):
  1. Load a scratch graph containing only PRs merged up to T0 (the world as the agent saw it then).
  2. Cases = modules where ONE active person holds >= MIN_SHARE of the knowledge (a bus-factor-1 module) with enough later activity.
  3. Prediction = top-K from tools.successors() computed on the T0 graph.
  4. Truth = the K people (other than the holder) who contributed the most to that module AFTER T0, from the full PR history.
  5. Baselines, all using only T0 information: DEPUTY (next-largest holders), PROLIFIC (busiest recent contributors in the repo), RANDOM (analytic).
Reported: hit@K (at least one predicted person is a true taker) and precision@K.
"""
import argparse, glob, json, math, random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from keystone import db, load, tools

MIN_SHARE, MIN_PRS, MIN_LATER_WEIGHT = 0.40, 12, 3.0


def ts(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())


def truth_table(files: list[Path], t0: int, t1: int) -> dict[str, dict[str, float]]:
    """module -> person -> knowledge gained in (t0, t1], authored 1.0 and reviewed 0.4 weighted by the PR's share in the module."""
    d = load.parse(files, None)
    when = {p["id"]: p["ts"] for p in d["prs"]}
    share = defaultdict(list)
    for t in d["touches"]:
        share[t["pr"]].append((t["m"], t["share"]))
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for rows, w in ((d["authored"], 1.0), (d["reviewed"], 0.4)):
        for r in rows:
            if t0 < when.get(r["pr"], 0) <= t1:
                for m, s in share[r["pr"]]:
                    out[m][r["p"]] += w * s
    return out


def prolific(g, repo: str, exclude: str, cut: int, k: int) -> list[str]:
    rows = db.q(g, "MATCH (p:Person {active: true})-[:AUTHORED|REVIEWED]->(pr:PR {repo: $r}) WHERE pr.ts >= $c AND p.id <> $x "
                   "RETURN p.id, count(DISTINCT pr) AS n ORDER BY n DESC LIMIT %d" % k, {"r": repo, "c": cut, "x": exclude})
    return [r[0] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="falkordb")
    ap.add_argument("--glob", default="data/raw/FalkorDB__*.json")
    ap.add_argument("--t0", default="2026-04-15")
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args()
    files = [Path(p) for p in sorted(glob.glob(a.glob))]
    t0 = ts(a.t0)
    t1 = max(p["ts"] for p in load.parse(files, None)["prs"])
    scratch = f"bt-{a.tenant}"
    load.load(scratch, files, as_of=a.t0)
    g = db.graph(scratch)
    truth = truth_table(files, t0, t1)
    active = [r[0] for r in db.q(g, "MATCH (p:Person {active: true}) RETURN p.id")]
    cases, rows = [], []
    for mid, s in tools.module_stats(g).items():
        if s["top_share"] < MIN_SHARE or s["bus_active"] != 1 or s["n_prs"] < MIN_PRS:
            continue
        holder = s["top"]
        later = {p: w for p, w in truth.get(mid, {}).items() if p != holder}
        if sum(later.values()) < MIN_LATER_WEIGHT:
            continue
        true_k = [p for p, _ in sorted(later.items(), key=lambda kv: -kv[1])[:a.k]]
        pred = [c["person"] for c in tools.successors(scratch, holder, mid, a.k)["data"].get("candidates", [])][:a.k]
        deputy = [r[0] for r in db.q(g, "MATCH (p:Person)-[k:KNOWS]->(m:Module {id: $m}) WHERE p.id <> $x AND p.active = true "
                                          "RETURN p.id ORDER BY k.score DESC LIMIT %d" % a.k, {"m": mid, "x": holder})]
        busy = prolific(g, mid.partition(":")[0], holder, t0 - 180 * 86400, a.k)
        rows.append({"module": tools.short(mid), "holder": holder, "truth": true_k, "graph": pred, "deputy": deputy, "prolific": busy})
        cases.append(mid)
    n = len(rows)
    if not n:
        raise SystemExit("no eligible cases; widen T0 or loosen thresholds")

    def score(key):
        hit = sum(bool(set(r[key]) & set(r["truth"])) for r in rows) / n
        prec = sum(len(set(r[key]) & set(r["truth"])) / a.k for r in rows) / n
        return round(hit, 3), round(prec, 3)

    A, k = max(len(active), a.k + 1), a.k
    rand_hit = 1 - math.comb(A - k, k) / math.comb(A, k)
    res = {"tenant": a.tenant, "t0": a.t0, "t1": datetime.fromtimestamp(t1, timezone.utc).date().isoformat(), "k": k, "cases": n, "active_at_t0": len(active),
           "graph": score("graph"), "deputy": score("deputy"), "prolific": score("prolific"), "random_hit": round(rand_hit, 3)}
    Path("bench").mkdir(exist_ok=True)
    Path(f"bench/backtest_{a.tenant}.json").write_text(json.dumps({"summary": res, "cases": rows}, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    print(f"\n{'method':10s} hit@{k}   precision@{k}\n" + "\n".join(f"{m:10s} {score(m)[0]:.3f}    {score(m)[1]:.3f}" for m in ("graph", "deputy", "prolific")) + f"\n{'random':10s} {rand_hit:.3f}    -")
    db.graph(scratch).delete()


if __name__ == "__main__":
    main()
