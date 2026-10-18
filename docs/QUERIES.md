# Cypher and graph algorithms Keystone depends on

Generated from the code by `python -m keystone.docs_queries`; nothing here is hand-written, so it cannot drift.

Parameters are always passed as Cypher parameters. The language model never writes or edits any of this.

## 1. Base facts (loaded from public merged-PR history)

### Repositories
```cypher
UNWIND $rows AS row MERGE (n:Repo {id:row.id}) SET n.url = 'https://github.com/' + row.id
```

### Modules (top-level directory, or two levels under src/app/lib/...)
```cypher
UNWIND $rows AS row MERGE (n:Module {id:row.id}) SET n.repo = row.repo, n.path = row.path, n.kind = row.kind
```

### Module -[:IN]-> Repo
```cypher
UNWIND $rows AS row MATCH (m:Module {id:row.id}), (x:Repo {id:row.repo}) MERGE (m)-[:IN]->(x)
```

### People (GitHub logins; bots excluded; no emails)
```cypher
UNWIND $rows AS row MERGE (n:Person {id:row.id}) SET n.url = row.url
```

### Merged pull requests
```cypher
UNWIND $rows AS row MERGE (n:PR {id:row.id}) SET n.number = row.number, n.title = row.title, n.url = row.url, n.ts =
row.ts, n.repo = row.repo, n.nmods = row.nmods, n.nfiles = row.nfiles
```

### Issues closed by PRs
```cypher
UNWIND $rows AS row MERGE (n:Issue {id:row.id}) SET n.title = row.title, n.url = row.url
```

### Person -[:AUTHORED]-> PR
```cypher
UNWIND $rows AS row MATCH (p:Person {id:row.p}), (x:PR {id:row.pr}) MERGE (p)-[:AUTHORED]->(x)
```

### Person -[:REVIEWED]-> PR
```cypher
UNWIND $rows AS row MATCH (p:Person {id:row.p}), (x:PR {id:row.pr}) MERGE (p)-[e:REVIEWED]->(x) SET e.state =
row.state
```

### PR -[:TOUCHES {share}]-> Module (share = fraction of the PR's files that land in the module)
```cypher
UNWIND $rows AS row MATCH (x:PR {id:row.pr}), (m:Module {id:row.m}) MERGE (x)-[e:TOUCHES]->(m) SET e.files =
row.files, e.share = row.share, e.ex = row.ex
```

### PR -[:CLOSES]-> Issue
```cypher
UNWIND $rows AS row MATCH (x:PR {id:row.pr}), (i:Issue {id:row.i}) MERGE (x)-[:CLOSES]->(i)
```

## 2. Derived knowledge (computed inside FalkorDB)

### Reset derived edges
```cypher
MATCH ()-[r:KNOWS|CO_KNOWS|CO_CHANGES]->() DELETE r
```

### Person activity window: first/last PR, and `active` (a PR within 180 days of the snapshot)
```cypher
MATCH (p:Person)-[:AUTHORED|REVIEWED]->(pr:PR) WITH p, min(pr.ts) AS f, max(pr.ts) AS l SET p.first_ts = f, p.last_ts
= l, p.active = (l >= $cut)
```

### Module size: merged PRs touching it
```cypher
MATCH (m:Module)<-[:TOUCHES]-(pr:PR) WITH m, count(pr) AS n SET m.n_prs = n
```

### Knowledge from authoring: share of each PR that lands in the module, decayed by age (half-life 365 days)
```cypher
MATCH (p:Person)-[:AUTHORED]->(pr:PR)-[t:TOUCHES]->(m:Module) WITH p, m, count(pr) AS n, sum(t.share * exp(-1.0 *
($now - pr.ts) / $tau)) AS s, max(pr.ts) AS last MERGE (p)-[k:KNOWS]->(m) SET k.authored = n, k.a_score = s, k.last =
last
```

### Knowledge from reviewing: weaker (0.4) but real; this is how knowledge spreads
```cypher
MATCH (p:Person)-[:REVIEWED]->(pr:PR)-[t:TOUCHES]->(m:Module) WITH p, m, count(pr) AS n, sum(0.4 * t.share * exp(-1.0
* ($now - pr.ts) / $tau)) AS s, max(pr.ts) AS last MERGE (p)-[k:KNOWS]->(m) SET k.reviewed = n, k.r_score = s, k.last
= CASE WHEN k.last IS NULL OR last > k.last THEN last ELSE k.last END
```

### Total knowledge score per KNOWS edge
```cypher
MATCH ()-[k:KNOWS]->() SET k.score = coalesce(k.a_score, 0.0) + coalesce(k.r_score, 0.0), k.authored =
coalesce(k.authored, 0), k.reviewed = coalesce(k.reviewed, 0)
```

### Module total knowledge
```cypher
MATCH (m:Module)<-[k:KNOWS]-() WITH m, sum(k.score) AS t SET m.total = t
```

### Share of the module each person holds, and an edge cost (strong knowledge is cheap to walk, so weighted shortest paths prefer real expertise)
```cypher
MATCH (p:Person)-[k:KNOWS]->(m:Module) SET k.share = k.score / m.total, k.cost = 1.01 - k.score / m.total
```

### CO_KNOWS: who overlaps with whom, both directions so graph algorithms can walk it
```cypher
MATCH (a:Person)-[x:KNOWS]->(m:Module)<-[y:KNOWS]-(b:Person) WHERE a.id < b.id AND x.share >= 0.05 AND y.share >= 0.05
WITH a, b, sum(CASE WHEN x.score < y.score THEN x.score ELSE y.score END) AS w, count(m) AS shared MERGE
(a)-[c:CO_KNOWS]->(b) SET c.w = w, c.shared = shared MERGE (b)-[c2:CO_KNOWS]->(a) SET c2.w = w, c2.shared = shared
```

### CO_CHANGES: logical coupling, modules that change together in the same PR
```cypher
MATCH (a:Module)<-[:TOUCHES]-(pr:PR)-[:TOUCHES]->(b:Module) WHERE a.id < b.id AND pr.nmods <= 12 WITH a, b, count(pr)
AS n WHERE n >= 2 MERGE (a)-[c:CO_CHANGES]->(b) SET c.n = n MERGE (b)-[c2:CO_CHANGES]->(a) SET c2.n = n
```

### Reset algorithm outputs (modules)
```cypher
MATCH (m:Module) SET m.importance = 0.0, m.cluster = -1
```

### Reset algorithm outputs (people)
```cypher
MATCH (p:Person) SET p.broker = 0.0
```

## 3. Graph algorithms (run once at load, stored as properties)

### algo.pageRank over co-change coupling -> Module.importance (how load-bearing is a module)
Runs only when `CO_CHANGES` edges exist.
```cypher
CALL algo.pageRank('Module', 'CO_CHANGES') YIELD node, score SET node.importance = score
```
```cypher
MATCH (m:Module) WITH max(m.importance) AS mx WHERE mx > 0 MATCH (m:Module) SET m.importance = m.importance / mx
```

### algo.labelPropagation over co-change coupling -> Module.cluster (which modules form one subsystem)
Runs only when `CO_CHANGES` edges exist.
```cypher
CALL algo.labelPropagation({nodeLabels:['Module'], relationshipTypes:['CO_CHANGES']}) YIELD node, communityId SET
node.cluster = communityId
```

### algo.betweenness over knowledge overlap -> Person.broker (who bridges otherwise separate people)
Runs only when `CO_KNOWS` edges exist.
```cypher
CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['CO_KNOWS'], samplingSize: 300, samplingSeed: 7})
YIELD node, score SET node.broker = score
```

## 4. Agent tools: the human-written queries behind each MCP tool

### `brokers`
```cypher
MATCH (p:Person {active: true}) WHERE p.broker > 0 RETURN p.id AS person, p.broker AS broker ORDER BY p.broker DESC
LIMIT 5
```

### `cluster_modules`
```cypher
MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= $min_prs AND m.cluster >= 0 RETURN m.cluster AS c,
collect(m.id) AS mods, sum(m.n_prs) AS prs
```

### `clusters`
```cypher
MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= $min_prs AND m.cluster >= 0 MATCH
(m)<-[k:KNOWS]-(p:Person) WITH m.cluster AS c, p, sum(k.score) AS s, collect(DISTINCT m.id) AS mods ORDER BY s DESC
WITH c, collect({p: p.id, s: s, act: p.active}) AS ps, sum(s) AS tot, count(DISTINCT p) AS ppl RETURN c, tot, ps[0..5]
AS top, reduce(a = {c: 0.0, k: 0}, h IN ps | CASE WHEN a.c < 0.5 * tot THEN {c: a.c + h.s, k: a.k + 1} ELSE a END).k
AS bus
```

### `current_share`
```cypher
MATCH (p:Person {id: $c})-[k:KNOWS]->(m:Module {id: $m}) RETURN k.share
```

### `isolated_after`
```cypher
MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= $min_prs AND NOT (m)<-[:KNOWS]-() RETURN m.id AS id
```

### `keystones`
```cypher
MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= $min_prs MATCH (m)<-[k:KNOWS]-(q:Person) WITH m,
sum(k.score) AS tot, sum(CASE WHEN q.active THEN k.score ELSE 0.0 END) AS act WHERE act / tot >= 0.25 MATCH
(m)<-[kp:KNOWS]-(p:Person {active: true}) WITH p, m, (act - kp.score) / tot AS left_cover, kp.share AS share WHERE
left_cover < 0.25 OR share >= 0.5 WITH p, m, share, left_cover, (left_cover < 0.25) AS orphan RETURN p.id AS person,
sum(CASE WHEN orphan THEN 1 ELSE 0 END) AS orphaned, sum(CASE WHEN orphan THEN 0 ELSE 1 END) AS sole, sum((CASE WHEN
orphan THEN 1.0 ELSE 0.5 END) * (0.2 + m.importance)) AS weighted, p.broker AS broker, collect({m: m.id, share: share,
orphan: orphan, imp: m.importance}) AS mods ORDER BY weighted DESC LIMIT $limit
```

### `last_snapshot`
```cypher
MATCH (s:Snapshot) WITH s ORDER BY s.ts DESC LIMIT 1 MATCH (s)-[o:OBSERVED]->(m:Module) RETURN s.id, s.as_of, m.id,
o.bus, o.top, o.share, o.cover
```

### `module_evidence`
```cypher
MATCH (m:Module {id: $m})<-[:TOUCHES]-(pr:PR) RETURN pr.url AS url, pr.title AS title, pr.ts AS ts ORDER BY pr.ts DESC
LIMIT 3
```

### `module_holders`
```cypher
MATCH (m:Module {id: $m})<-[k:KNOWS]-(p:Person) RETURN p.id AS person, k.share AS share, k.authored AS authored,
k.reviewed AS reviewed, k.last AS last, p.active AS active ORDER BY k.score DESC LIMIT 8
```

### `module_names`
```cypher
MATCH (m:Module) WHERE m.n_prs >= $min_prs RETURN m.id, m.kind, m.n_prs ORDER BY m.n_prs DESC
```

### `module_stats`
```cypher
MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= $min_prs MATCH (m)<-[k:KNOWS]-(p:Person) WITH m, p, k
ORDER BY m.id, k.score DESC WITH m, collect({p: p.id, s: k.score, act: p.active, au: k.authored, rv: k.reviewed, last:
k.last}) AS hs, sum(k.score) AS tot WITH m, hs, tot, reduce(a = 0.0, h IN hs | a + CASE WHEN h.act THEN h.s ELSE 0.0
END) AS act_tot RETURN m.id AS id, m.n_prs AS n_prs, m.importance AS imp, tot, act_tot, hs[0].p AS top, hs[0].s / tot
AS top_share, reduce(a = {c: 0.0, k: 0}, h IN hs | CASE WHEN a.c < 0.5 * tot THEN {c: a.c + h.s, k: a.k + 1} ELSE a
END).k AS bus, reduce(a = {c: 0.0, k: 0}, h IN [x IN hs WHERE x.act] | CASE WHEN a.c < 0.5 * act_tot THEN {c: a.c +
h.s, k: a.k + 1} ELSE a END).k AS bus_active
```

### `names`
```cypher
MATCH (p:Person) RETURN p.id
```

### `open_tasks`
```cypher
MATCH (t:Task) WHERE t.status = 'open' RETURN t.id, t.text, t.cand, t.module, t.baseline_share, t.target_share,
t.as_of
```

### `overview`
```cypher
MATCH (x:Meta {id: 'meta'}) OPTIONAL MATCH (p:Person) WITH x, count(p) AS people, sum(CASE WHEN p.active THEN 1 ELSE 0
END) AS active OPTIONAL MATCH (m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= 6 RETURN x.snapshot_ts AS
snapshot_ts, x.n_prs AS n_prs, x.half_life_days AS half_life, people, active, count(m) AS modules
```

### `pace`
```cypher
MATCH (m:Module {id: $m})<-[:TOUCHES]-(pr:PR) WHERE pr.ts >= $since RETURN count(pr)
```

### `person_modules`
```cypher
MATCH (p:Person {id: $p})-[k:KNOWS]->(m:Module) WHERE m.kind IN ['code','ci'] AND m.n_prs >= $min_prs RETURN m.id AS
id, k.share AS share, m.importance AS imp ORDER BY k.share * (0.2 + m.importance) DESC LIMIT $limit
```

### `pick_decision`
```cypher
MATCH (d:Decision) WHERE d.status = 'approved' AND ($d = '' OR d.id = $d) RETURN d.id, d.leaver, d.plan_json, d.as_of
ORDER BY d.ts DESC LIMIT 1
```

### `plan_tasks`
```cypher
MATCH (t:Task)-[:IMPLEMENTS]->(d:Decision {id: $d}) RETURN t.cand, t.module, t.target_share, t.id
```

### `pr_exists`
```cypher
MATCH (pr:PR {url: $u}) RETURN count(pr)
```

### `share_of`
```cypher
MATCH (p:Person {id: $c})-[k:KNOWS]->(m:Module {id: $m}) RETURN k.share
```

### `shortest_knowledge_path`
```cypher
MATCH (a:%s {id: $a}), (b:%s {id: $b}) CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['KNOWS'],
relDirection: 'both', weightProp: 'cost', pathCount: 1}) YIELD path, pathWeight RETURN [n IN nodes(path) | {id: n.id,
kind: labels(n)[0]}] AS nodes, [r IN relationships(path) | r.share] AS shares, pathWeight
```

### `successor_adjacent`
```cypher
UNWIND $targets AS tid MATCH (t:Module {id: tid})<-[cc:CO_CHANGES]-(m2:Module)<-[ka:KNOWS]-(c:Person {active: true})
WHERE c.id <> $p AND m2.kind <> 'root' RETURN c.id AS cand, sum(ka.share * log(1 + cc.n)) AS adjacent,
collect(m2.id)[0] AS via
```

### `successor_direct`
```cypher
UNWIND $targets AS tid MATCH (t:Module {id: tid}) MATCH (c:Person {active: true}) WHERE c.id <> $p OPTIONAL MATCH
(c)-[kc:KNOWS]->(t) RETURN c.id AS cand, sum(coalesce(kc.share, 0.0)) AS direct
```

### `successor_reviewed`
```cypher
MATCH (c:Person {active: true})-[:REVIEWED]->(pr:PR)<-[:AUTHORED]-(p:Person {id: $p}) MATCH
(pr)-[:TOUCHES]->(t:Module) WHERE t.id IN $targets RETURN c.id AS cand, count(DISTINCT pr) AS n, collect(DISTINCT
pr.url)[0] AS url
```

### `task_activity`
```cypher
MATCH (c:Person {id: $c})-[:AUTHORED|REVIEWED]->(pr:PR)-[:TOUCHES]->(m:Module {id: $m}) WHERE pr.ts > $since RETURN
count(DISTINCT pr), collect(DISTINCT pr.url)[0]
```

### `task_load`
```cypher
MATCH (t:Task) WHERE t.status = 'open' AND t.cand IS NOT NULL RETURN t.cand, count(t)
```

### `who_knows`
```cypher
MATCH (m:Module {id: $m})<-[k:KNOWS]-(p:Person) RETURN p.id AS person, k.share AS share, k.authored AS authored,
k.reviewed AS reviewed, k.last AS last, p.active AS active ORDER BY k.score DESC LIMIT $limit
```

## 5. Counterfactuals and writes
- `GRAPH.COPY ks_<tenant> ks_<tenant>__wi_<id>` forks the graph; `what_if_leaves` and the Planner/Reviewer simulate on the fork (`MATCH (p:Person {id: $p}) DETACH DELETE p`, or add planned `KNOWS` score), then `GRAPH.DELETE` removes it.
- Memory (`Finding`, `Decision`, `Task`, `Snapshot`, `Run`, `Step`, `Action`) is written with parameterised `CREATE`/`MERGE` in `memory.py`, `workflow.py` and `actions.py`; reads use `GRAPH.RO_QUERY` so a read tool can never mutate the graph.

