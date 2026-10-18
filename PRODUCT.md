# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Backend: Python 3.12, FastAPI, an MCP server (FastMCP, `mcp` 1.x), FalkorDB. Front end: hand-built HTML/CSS/JS with no framework (delegated: the user's standing preference from TrustPass). Deploy target: one public container (FalkorDB + app) plus `docker compose` for local setup.

## Users

Primary: an engineering leader (CTO, engineering manager, tech lead) planning for attrition, leave or reorganisation. Situation: reviewing team health before a quarter, or reacting to news that someone is leaving. Job: find single points of failure, understand what breaks if a person leaves, who can realistically step in, and walk away with a plan they can act on today.

Secondary (hackathon context, Graph Hacks Track 01): judges from FalkorDB / WeMakeDevs who have a few minutes with a demo video and a live link. They must see the graph doing the reasoning, not decorating it.

## Product Purpose

Keystone is an agent that answers "if this person leaves, what breaks, and who steps in?" It reads an organisation's real merged-PR history as a FalkorDB graph (people, reviews, files, modules), finds where knowledge is concentrated, simulates departures on a forked copy of the graph, plans pairings, re-verifies the plan with a separate reviewer role, and drafts the artifacts to act on it (a CODEOWNERS patch and issues). Success: a leader goes from a worry to a verified, evidence-backed plan in minutes, and can see exactly why at every step.

## Positioning

Not a dashboard of bus-factor numbers. The agent reasons over relationships (who authored, who reviewed, which modules change together) as multi-hop paths; it tests its own plan on a counterfactual graph fork (`GRAPH.COPY`); it says "not in the graph" instead of guessing; and its tools are open over MCP so any MCP client (Claude Desktop, Claude Code) can drive it. A tool that stores flat contributor counts can show neither the path nor the counterfactual.

## Operating Context

Used at a desk by a technical leader, often screen-shared in a meeting or recorded for a demo video. Data is real and public: merged pull requests of two organisations (FalkorDB's repositories and Pallets), snapshot dated in the UI. Two durable agent roles hand off through graph state (Analyst, Planner, Reviewer). Agent actions are dry-run drafts; nothing is posted to GitHub unless the operator configures a target repository and confirms.

## Capabilities and Constraints

- 15 MCP tools: overview, find_modules, module_risk, risk_scan, keystones, what_if_leaves, successors, who_knows, knowledge_map, path_between, recall, changes_since, succession_review, draft_actions, note_finding. The model never writes Cypher.
- Every answer carries one of four outcomes: answered, from_memory, not_in_graph, unknown_entity. The path shown is built from the same rows as the answer.
- Definitions the UI must use consistently: knowledge share, bus factor (fewest people covering 50%), active (a PR within 180 days of the snapshot), orphaned (active people hold under 25%).
- Public data only; no emails stored; the tool is descriptive of contribution patterns, never an evaluation of people.
- Each visitor works in a private `GRAPH.COPY` sandbox of the base graph; base graphs are read-only in the public deployment.
- Agent works with or without an LLM key: without one a deterministic router answers and the UI says so; visitors may paste their own key (kept only for the request).
- Undecided: the exact public host for the live demo.

## Brand Commitments

Name: Keystone (the stone that holds the arch up). Voice: plain, precise, honest about uncertainty; descriptive, not evaluative. Sponsor attribution: "Built on FalkorDB" and "Graph Hacks (FalkorDB x WeMakeDevs)" appear where appropriate.

## Evidence on Hand

Real data: FalkorDB organisation snapshot 2026-10-15 (3,664 merged PRs, 62 contributors, 114 tracked modules across 12 repositories) and the Pallets organisation (4,925 merged PRs, 1,735 contributors). A true backtest exists as a story: a review run as of 2026-04-15 versus actual PR activity by 2026-10-15. No customers, testimonials, benchmarks or commercial claims exist; none may be invented. Evaluation numbers (backtest vs naive baselines) are not computed yet and must not be shown until they are.

## Product Principles

1. Show the path: every claim is one click from the nodes, edges and public PRs that produced it.
2. Counterfactual before recommendation: test a plan on a graph fork before proposing it.
3. Honest edges: say "not in the graph" or "unknown person" out loud; never smooth over a gap.
4. The graph does the work: tools are human-written queries and graph algorithms; the model chooses, it does not compute.
5. Descriptive, not evaluative: knowledge concentration is a structural fact about a team, not a verdict on a person.

## Accessibility & Inclusion

Risk is never encoded by colour alone (tier labels and shapes accompany it). WCAG AA text contrast. Fully keyboard-operable; reduced-motion respected for path animations. Works on a phone-width viewport.
