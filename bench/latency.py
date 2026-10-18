"""Per-tool latency on the real snapshot.  python -m bench.latency [tenant] [runs]
Measures the tool function directly (query + algorithms + Python shaping), warm cache, one connection."""
import json
import statistics
import sys
import time
from pathlib import Path

from keystone import tools, workflow

tenant = sys.argv[1] if len(sys.argv) > 1 else "falkordb"
runs = int(sys.argv[2]) if len(sys.argv) > 2 else 30

CASES = [
    ("overview", lambda: tools.overview(tenant)),
    ("find_modules", lambda: tools.find_modules(tenant, "execution plan")),
    ("module_risk", lambda: tools.module_risk(tenant, "falkordb-browser app")),
    ("who_knows", lambda: tools.who_knows(tenant, "execution plan")),
    ("risk_scan", lambda: tools.risk_scan(tenant, 10)),
    ("keystones", lambda: tools.keystones(tenant, 8)),
    ("knowledge_map", lambda: tools.knowledge_map(tenant)),
    ("path_between", lambda: tools.path_between(tenant, "gkorland", "Anchel123")),
    ("successors", lambda: tools.successors(tenant, "Anchel123")),
    ("what_if_leaves (GRAPH.COPY fork)", lambda: tools.what_if_leaves(tenant, "Anchel123")),
]

rows = []
for name, fn in CASES:
    fn()  # warm
    ts = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    rows.append({"tool": name, "p50_ms": round(statistics.median(ts), 1), "p95_ms": round(ts[int(0.95 * (len(ts) - 1))], 1)})

print(f"{'tool':36s} {'p50 ms':>8s} {'p95 ms':>8s}   ({runs} runs, tenant {tenant})")
for r in rows:
    print(f"{r['tool']:36s} {r['p50_ms']:8.1f} {r['p95_ms']:8.1f}")
Path("bench").mkdir(exist_ok=True)
Path(f"bench/latency_{tenant}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
