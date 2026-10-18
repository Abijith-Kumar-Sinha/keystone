/* Workbench: pick who leaves, watch the wall re-solve. Every number is read from the live API.
   The command line talks to the same agent that serves /mcp; questions run in a private GRAPH.COPY sandbox. */
import { reduced, timecode, settle, tear, cellArt } from "/static/fx.js";

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
const enc = encodeURIComponent;
const NS = "http://www.w3.org/2000/svg";
const COVER = 0.5;                                     // tools.py COVER: below this share of knowledge left, a module is fragile
const FOCUS = new Set(["what_if_leaves", "successors", "succession_review"]);
const PROVIDERS = {
  anthropic: { label: "Anthropic", model: "claude-haiku-5-5", cfg: { provider: "anthropic" } },
  openai: { label: "OpenAI", model: "gpt-4o-mini", cfg: { provider: "openai" } },
  gemini: { label: "Gemini", model: "gemini-3.8-flash", cfg: { provider: "openai", base_url: "https://generativelanguage.googleapis.com/v1beta/openai" } },
  groq: { label: "Groq", model: "openai/gpt-oss-120b", cfg: { provider: "openai", base_url: "https://api.groq.com/openai/v1" } },
  openrouter: { label: "OpenRouter", model: "openai/gpt-4o-mini", cfg: { provider: "openai", base_url: "https://openrouter.ai/api/v1" } },
};

const qs = new URLSearchParams(location.search);
let deep = null;                                        // set by a ?q=...&open=path deep link until the answer arrives
const S = { tenant: qs.get("g") === "pallets" ? "pallets" : "falkordb", person: null, people: [], boxes: {}, tok: 0, boot: 0, hist: [], focus: null, ask: null, plan: null, path: null, cells: [], nums: [0, 0], llm: null, tab: "path" };
try { S.llm = JSON.parse(sessionStorage.getItem("ks-llm") || "null"); } catch { /* storage can be blocked; the key then lives for this page only */ }

/* ---------------------------------------------------------------- api */
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : { cache: "no-store" });
  if (!r.ok) {
    let m = `Request failed (${r.status})`;
    try { const j = await r.json(); if (typeof j.detail === "string") m = j.detail; } catch { /* keep the status text */ }
    throw Object.assign(new Error(m), { status: r.status });
  }
  return r.json();
}
const tool = (tenant, name, args = {}) => api("/api/tool", { tenant, name, args });

async function sandbox() {
  if (!S.boxes[S.tenant]) S.boxes[S.tenant] = (await api("/api/sandbox", { base: S.tenant })).tenant;
  return S.boxes[S.tenant];
}
async function inSandbox(fn) {                          // a sandbox expires after a few hours: make a fresh fork once, then retry
  try { return await fn(await sandbox()); } catch (e) {
    if (e.status !== 404) throw e;
    delete S.boxes[S.tenant];
    return fn(await sandbox());
  }
}

/* ---------------------------------------------------------------- small ui helpers */
const sayEl = $("#say"), live = $("#live"), planBtn = $("#plan");
const bullets = (t) => String(t || "").replace(/`/g, "").replace(/^\s*[*-]\s+/gm, "• ");   // models answer in markdown; keep the bullets, drop the backticks
function say(text, kind = "") {
  sayEl.className = `say ${kind}`.trim();
  sayEl.textContent = "";
  bullets(text).replace(/\s*\n+\s*/g, " ").split("**").forEach((part, i) => { if (part) sayEl.append(i % 2 ? el("b", "", part) : part); });
}
const mark = (b, on) => (on ? b.setAttribute("aria-current", "true") : b.removeAttribute("aria-current"));
const dash = (line) => { line.setAttribute("stroke-dasharray", "3 5"); line.setAttribute("opacity", "0.55"); };
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const empty = (msg) => el("p", "empty", msg);

/* ---------------------------------------------------------------- sources: who leaves */
function renderSources() {
  const nav = $("#sources");
  nav.textContent = "";
  S.people.forEach((p) => {
    const b = el("button", "src", p);
    b.type = "button";
    b.dataset.p = p;
    mark(b, p === S.person);
    nav.append(b);
  });
}
$("#sources").addEventListener("click", (e) => { const b = e.target.closest(".src"); if (b) pick(b.dataset.p); });

async function loadSources() {
  const r = await tool(S.tenant, "keystones", { limit: 10 });
  const ids = (r.data?.people || []).map((p) => p.person);
  if (ids.length < 8) {                                // a small org has few keystones: fill with the most knowledgeable active people
    const g = await api(`/api/graph?tenant=${enc(S.tenant)}&k=40`);
    g.nodes.filter((n) => n.kind === "person" && n.active && !ids.includes(n.label))
      .sort((a, b) => b.weight - a.weight).slice(0, 9 - ids.length).forEach((n) => ids.push(n.label));
  }
  S.people = ids;
}

/* ---------------------------------------------------------------- the wall */
function setNums(o, f) {
  [["#n-orphaned", o, 0], ["#n-fragile", f, 1]].forEach(([sel, v, i]) => {
    const n = $(sel);
    n.dataset.bad = v > 0 ? "1" : "0";
    settle(n, S.nums[i], v, { fmt: (x) => String(Math.round(x)) });
  });
  S.nums = [o, f];
}

function drawWall(data) {
  const wall = $("#wall");
  wall.textContent = "";
  if (!data.cells.length) { wall.append(empty("No modules tracked.")); S.cells = []; return; }
  const done = [];
  S.cells = data.cells.slice(0, 9).map((c, i) => {
    const p = Math.round(c.retained * 100);
    const state = !c.affected ? "locked" : c.retained < COVER ? "cut" : "soft";
    const cell = el("article", "wcell");
    cell.dataset.state = state;
    cell.setAttribute("aria-label", `${c.name}: ${p} percent of its knowledge stays`);
    const pc = el("p", "pc", reduced ? `${p}%` : "100%");
    pc.setAttribute("aria-hidden", "true");
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "-14 0 270 214");     // room for a holder dot on the far left spoke
    svg.setAttribute("role", "presentation");
    cell.append(el("h2", "nm", c.name.replace(/([:/])/g, "$1\u200b")), pc, svg);   // break after : and / on a narrow cell
    if (!reduced) { cell.classList.add("enter"); cell.style.animationDelay = `${i * 55}ms`; }
    wall.append(cell);
    const holders = state === "cut" ? c.holders : c.holders.map((h) => ({ ...h, removed: false }));   // only a real cut is drawn as one
    const art = cellArt(svg, holders, { cut: false, label: false, cx: 90 });
    if (reduced) { if (art.removed) dash(art.removed.line); }
    else done.push(new Promise((res) => setTimeout(async () => {
      if (art.removed) { dash(art.removed.line); tear(art.tear, 700); }
      await settle(pc, 100, p);
      res();
    }, i * 55 + 280)));
    return { c, cell, pc, art, p, state, holders };
  });
  S.ready = Promise.all(done);
}

/* a plan heals the wall: the successor joins the cell as a green spoke and the number climbs */
async function healWall(plan) {
  const tok = S.tok, cells = S.cells;
  await S.ready;                                       // let the cut finish before it heals
  if (tok !== S.tok) return;                           // another leaver was picked meanwhile: this plan is not for this wall
  const moves = (plan.data?.plans || []).map((row) => {
    const x = cells.find((k) => k.c.name === row.module);
    if (!x) return null;
    const to = Math.round(row.retained_after * 100), from = x.p;
    x.p = to;
    x.holders = [...x.holders, { person: row.candidate, share: 0.3, active: true, planned: true, removed: false }];
    x.art = cellArt($("svg", x.cell), x.holders, { cut: true, label: false, cx: 90 });
    if (x.art.removed) { dash(x.art.removed.line); tear(x.art.tear, 600); }
    x.cell.dataset.state = "healed";
    return settle(x.pc, from, to);
  });
  await Promise.all(moves);
}

async function pick(id) {
  if (!id) return;
  const tok = ++S.tok, prev = S.person;
  S.person = id;
  $("#q").placeholder = `What if ${id} leaves?`;
  S.plan = S.patch = null;
  if (S.tab === "plan" || S.tab === "patch") closeSheet();   // those tabs belong to the previous leaver
  if (!S.people.includes(id)) { S.people.unshift(id); renderSources(); }
  else document.querySelectorAll(".src").forEach((b) => mark(b, b.dataset.p === id));
  $(".src[aria-current]")?.scrollIntoView({ block: "nearest", inline: "center" });   // the chip row scrolls on a phone
  planBtn.disabled = true;
  planBtn.textContent = "Make the plan";
  let cells, wi;
  try {
    [cells, wi] = await Promise.all([
      api(`/api/cells?tenant=${enc(S.tenant)}&leaver=${enc(id)}&n=9&affected=5`),   // five that break, four that hold: the wall needs both to read
      tool(S.tenant, "what_if_leaves", { person: id }),
    ]);
  } catch (e) {
    if (tok !== S.tok) return;
    S.person = prev;                                    // the wall still shows the previous leaver: keep the chips honest
    document.querySelectorAll(".src").forEach((b) => mark(b, b.dataset.p === prev));
    say(e.message, "err");
    return;
  }
  if (tok !== S.tok) return;                           // a newer pick won
  drawWall(cells);
  const d = wi.data || {};
  setNums(d.orphaned || 0, d.fragile || 0);
  S.path = wi.path?.nodes?.length ? wi.path : null;       // the proof for this leaver: who holds which module
  $("#proof").disabled = !S.path;
  if (S.tab === "path" && sheetOpen()) showTab("path");
  planBtn.disabled = !((d.orphaned || 0) + (d.fragile || 0));
  live.textContent = `${id} leaves: ${d.orphaned || 0} modules orphaned, ${d.fragile || 0} fragile.`;
  try { history.replaceState(null, "", `?g=${S.tenant}&p=${enc(id)}`); } catch { /* file:// */ }
}

/* ---------------------------------------------------------------- graph channel */
async function boot() {
  const bt = ++S.boot;                                 // two quick channel switches: only the last one may draw
  say("");
  $("#wall").replaceChildren(el("p", "wait", "Stand by"));
  S.person = null; S.plan = S.patch = null; S.ask = null; S.hist = []; S.focus = null;
  S.path = null;
  $("#proof").disabled = true;
  document.querySelectorAll(".chan").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tenant === S.tenant)));
  try {
    await loadSources();
    if (bt !== S.boot) return;
    renderSources();
    const want = qs.get("p");
    await pick((want && !qs.has("done") ? want : null) || (S.people.includes("Anchel123") && S.tenant === "falkordb" ? "Anchel123" : S.people[0]));
    if (!qs.has("done")) {                             // deep links (screenshots, demos): ?q=question asks it, ?open=path shows the proof, ?open=plan runs the plan
      if (qs.get("q")) { deep = ["path", "trace"].includes(qs.get("open")) ? qs.get("open") : null; $("#q").value = qs.get("q"); $("#cmd").requestSubmit(); }
      else if (qs.get("open") === "path" && S.path) openSheet("path");
      if (qs.get("open") === "plan") planBtn.click();
    }
    qs.set("done", "1");                               // the deep link applies once
  } catch (e) {
    if (bt !== S.boot) return;
    $("#wall").replaceChildren(el("p", "wait", "No signal"));
    say(e.message, "err");
  }
}
document.querySelectorAll(".chan").forEach((b) => b.addEventListener("click", () => {
  if (b.dataset.tenant === S.tenant) return;
  S.tenant = b.dataset.tenant;
  qs.set("done", "1");
  closeSheet();
  boot();
}));

/* ---------------------------------------------------------------- plan */
planBtn.addEventListener("click", async () => {
  if (!S.person) return;
  if (S.plan) { openSheet("plan"); return; }
  planBtn.disabled = true;
  planBtn.textContent = "Planning";
  const who = S.person;
  try {
    const r = await inSandbox((t) => tool(t, "succession_review", { person: who }));
    if (who !== S.person) return;
    if (r.outcome !== "answered" || !r.data?.plans?.length) { say(r.note || "No plan was needed.", ""); planBtn.textContent = "Make the plan"; planBtn.disabled = false; return; }
    S.plan = r;
    S.patch = null;
    planBtn.textContent = "Show the plan";
    await healWall(r);
    if (who === S.person) openSheet("plan");
  } catch (e) { say(e.message, "err"); planBtn.textContent = "Make the plan"; }
  planBtn.disabled = false;
});

/* ---------------------------------------------------------------- command line */
$("#cmd").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#q"), q = input.value.trim();
  if (!q) return;
  input.value = "";
  input.disabled = true;
  say("Reading the graph", "busy");
  try {
    const r = await inSandbox((t) => api("/api/ask", { tenant: t, question: q, history: S.hist, focus: S.focus, llm: S.llm }));
    S.hist = [...S.hist, { role: "user", content: q }, { role: "assistant", content: r.answer }].slice(-6);
    S.focus = r.focus;
    S.ask = r;
    say(r.answer);
    paintMode(r.mode);
    if (r.path?.nodes?.length) S.path = r.path;
    $("#proof").disabled = !S.path;
    if (deep && (deep === "trace" || S.path)) { const tab = deep; deep = null; openSheet(tab); }
    const who = r.results.find((x) => FOCUS.has(x.tool) && x.outcome === "answered" && typeof x.data?.person === "string")?.data.person;
    if (who && who !== S.person) await pick(who);       // the wall follows the question
    const plan = r.results.find((x) => x.tool === "succession_review" && x.outcome === "answered" && x.data?.plans?.length);
    if (plan) { S.plan = plan; S.patch = null; planBtn.textContent = "Show the plan"; planBtn.disabled = false; await healWall(plan); openSheet("plan"); }
    else if (sheetOpen() && (S.tab === "trace" || S.tab === "path")) showTab(S.tab);
  } catch (err) { say(err.message, "err"); }
  input.disabled = false;
  input.focus();
});
addEventListener("keydown", (e) => {
  if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) { e.preventDefault(); $("#q").focus(); }
  if (e.key === "Escape" && sheetOpen()) closeSheet();
});

/* ---------------------------------------------------------------- the sheet: trace, plan, patch, model */
const sheet = $("#sheet"), body = $("#sheet-body");
const sheetOpen = () => sheet.hasAttribute("open");

function openSheet(t) {
  if (!sheetOpen()) sheet.show();
  showTab(t);
  $("#sheet-x").focus({ preventScroll: true });
}
function closeSheet() { if (sheetOpen()) sheet.close(); }
function showTab(t) {
  S.tab = t;
  sheet.querySelectorAll("[role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === t)));
  body.textContent = "";
  body.append({ path: pathTab, trace: traceTab, plan: planTab, patch: patchTab, key: keyTab }[t]());
  body.scrollTop = 0;
}
sheet.querySelector(".tabs").addEventListener("click", (e) => { const b = e.target.closest("[role=tab]"); if (b) showTab(b.dataset.tab); });
$("#sheet-x").addEventListener("click", closeSheet);
$("#proof").addEventListener("click", () => openSheet("path"));
$("#mode").addEventListener("click", () => openSheet("key"));

/* the proof: the nodes and edges the answer was built from. People on the left, the leaver in the middle, modules on the right;
   a column that has no node is skipped. Edge width is the person's share of the module. */
function pathTab() {
  const p = S.path;
  if (!p?.nodes?.length) return empty("Pick someone or ask a question first.");
  const kind = (n) => (n.kind === "person" ? (n.leaving ? "leaver" : "person") : "module");
  const order = ["person", "leaver", "module"].filter((k) => p.nodes.some((n) => kind(n) === k));
  const XS = { 1: [210], 2: [120, 290], 3: [105, 215, 315] }[order.length];
  const colX = Object.fromEntries(order.map((k, i) => [k, XS[i]]));
  const W = 560, ROW = 38, PAD = 28;
  const groups = Object.fromEntries(order.map((k) => [k, p.nodes.filter((n) => kind(n) === k)]));
  const rows = Math.max(...order.map((k) => groups[k].length));
  const H = PAD * 2 + (rows - 1) * ROW;
  const at = {};
  order.forEach((k) => groups[k].forEach((n, i) => { at[n.id] = { x: colX[k], y: H / 2 + (i - (groups[k].length - 1) / 2) * ROW, k }; }));
  const share = {};                                     // the biggest share on any edge touching a module, shown next to its name
  (p.edges || []).forEach((e) => { if (typeof e.share === "number") for (const id of [e.source, e.target]) share[id] = Math.max(share[id] || 0, e.share); });
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "pathsvg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "The people and modules this answer was built from");
  const mk = (tag, attrs, parent = svg) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.append(e); return e; };
  (p.edges || []).forEach((e) => {
    const a = at[e.source], b = at[e.target];
    if (!a || !b) return;
    const planned = e.type === "PLANNED", rev = e.type === "REVIEWED_FOR", mx = (a.x + b.x) / 2;
    mk("path", { d: `M${a.x} ${a.y} C${mx} ${a.y} ${mx} ${b.y} ${b.x} ${b.y}`, fill: "none", stroke: planned || rev ? "var(--green)" : "#8a8f96",
      "stroke-width": String(1 + Math.min(4, (typeof e.share === "number" ? e.share : 0) * 6)), "stroke-dasharray": rev ? "4 4" : "0", opacity: "0.85" });
  });
  p.nodes.forEach((n) => {
    const q = at[n.id], isMod = q.k === "module";
    const fill = n.leaving ? "var(--red)" : n.candidate ? "var(--green)" : isMod ? "#5d6167" : n.active === false ? "#6b7078" : "#b9bdc3";
    const c = mk("circle", { cx: q.x, cy: q.y, r: isMod ? 9 : 7, fill });
    if (n.status === "orphaned" || n.status === "fragile" || n.tier === "critical") { c.setAttribute("stroke", "var(--red)"); c.setAttribute("stroke-width", "2"); }
    mk("title", {}, c).textContent = n.label;
    const label = n.label.length > 36 ? `…${n.label.slice(-35)}` : n.label;
    const t = mk("text", q.k === "leaver" ? { x: q.x, y: q.y + 25, "text-anchor": "middle" } : q.k === "person" ? { x: q.x - 14, y: q.y + 4, "text-anchor": "end" } : { x: q.x + 15, y: q.y + 4 });
    t.textContent = label;
    if (isMod && share[n.id] >= 0.05) mk("tspan", { class: "dim", dx: "8" }, t).textContent = `${Math.round(share[n.id] * 100)}%`;
  });
  const wrap = document.createDocumentFragment();
  wrap.append(svg);
  return wrap;
}

function traceTab() {
  const r = S.ask, f = document.createDocumentFragment();
  if (!r) return empty("Ask something first.");
  f.append(el("p", "ans", bullets(r.answer).replaceAll("**", "")));
  f.append(el("p", "empty", r.model ? `Answered by ${r.model}` : "Answered by the router"));
  r.trace.forEach((t) => {
    const row = el("div", "row");
    row.append(el("b", "", t.tool), el("span", "ms", t.ms == null ? "" : `${t.ms} ms`));
    const res = el("div", "res");
    res.append(el("span", t.outcome === "answered" ? "ok" : "no", t.outcome));
    const a = Object.entries(t.args || {}).map(([k, v]) => `${k}=${v}`).join(" ");
    if (a) res.append(` ${a}`);
    if (t.queries?.length) res.append(el("div", "", `cypher: ${t.queries.join(", ")}`));
    row.append(res);
    f.append(row);
  });
  (r.notes || []).forEach((n) => f.append(el("p", "empty", n)));
  (r.sources || []).filter((s) => /^https:\/\//.test(s.url || "")).forEach((s) => {
    const row = el("div", "row"), a = el("a", "", s.label || s.url);
    a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer";
    row.append(a);
    f.append(row);
  });
  return f;
}

function planTab() {
  const p = S.plan?.data, f = document.createDocumentFragment();
  if (!p?.plans?.length) return empty("No plan yet.");
  const ok = p.decision.status === "approved";
  f.append(el("p", `verdict ${ok ? "ok" : "no"}`, ok ? "Approved" : "Needs changes"));
  p.plans.forEach((x) => {
    const row = el("div", "row");
    row.append(el("b", "", x.module), el("span", "big", `${pct(x.retained_before)} to ${pct(x.retained_after)}`));
    const res = el("div", "res");
    res.append(`${p.person} to ${x.candidate}, about ${x.est_months} months, ${x.prs_needed} PRs `);
    if (/^https:\/\//.test(x.evidence || "")) {
      const a = el("a", "", "PR");
      a.href = x.evidence; a.target = "_blank"; a.rel = "noopener noreferrer";
      res.append(a);
    }
    row.append(res);
    f.append(row);
  });
  (p.failures || []).forEach((x) => f.append(el("p", "row no", `${x.module}: ${x.problems.join(", ")}`)));
  const go = el("button", "btn draft", S.patch ? "Show the patch" : "Draft the patch");
  go.type = "button";
  go.addEventListener("click", () => draftPatch(go));
  f.append(go);
  return f;
}

async function draftPatch(btn) {
  if (S.patch) { showTab("patch"); return; }
  btn.disabled = true;
  btn.textContent = "Drafting";
  try {
    const r = await inSandbox((t) => tool(t, "draft_actions", { decision_id: S.plan.data.decision.id }));
    if (r.outcome !== "answered") { btn.textContent = "Draft the patch"; btn.disabled = false; say(r.note || "Nothing to draft.", "err"); return; }
    S.patch = r;
    showTab("patch");
  } catch (e) { btn.textContent = "Draft the patch"; btn.disabled = false; say(e.message, "err"); }
}

function patchTab() {
  const p = S.patch?.data, f = document.createDocumentFragment();
  if (!p?.actions?.length) return empty("Make a plan first.");
  p.actions.forEach((a) => {
    if (a.kind === "codeowners_patch") {
      const row = el("div", "row");
      row.append(el("b", "", a.file || "CODEOWNERS"), el("span", "ms", a.repo));
      f.append(row);
      const pre = el("pre", "diff");
      a.body.split("\n").forEach((ln) => pre.append(el("span", ln.startsWith("+") && !ln.startsWith("+++") ? "add" : ln.startsWith("-") && !ln.startsWith("---") ? "del" : "", ln || " ")));
      f.append(pre);
    } else {
      const d = el("details", "issue");
      d.append(el("summary", "", a.title), el("pre", "", a.body));
      f.append(d);
    }
  });
  f.append(empty("Dry run. Nothing is posted."));
  return f;
}

function keyTab() {
  const f = document.createDocumentFragment();
  const form = el("form", "keyform");
  const sel = el("select");
  Object.entries(PROVIDERS).forEach(([k, v]) => { const o = el("option", "", v.label); o.value = k; sel.append(o); });
  const model = el("input"); model.type = "text"; model.autocomplete = "off";
  const key = el("input"); key.type = "password"; key.autocomplete = "off"; key.placeholder = "API key";
  const sync = () => { model.placeholder = PROVIDERS[sel.value].model; };
  sel.addEventListener("change", sync);
  if (S.llm && PROVIDERS[S.llm.id]) { sel.value = S.llm.id; model.value = S.llm.model || ""; }
  sync();
  const l1 = el("label", "", "Provider"), l2 = el("label", "", "Model"), l3 = el("label", "", "Key");
  l1.append(sel); l2.append(model); l3.append(key);
  const use = el("button", "btn", S.llm ? "Update" : "Use my model"); use.type = "submit";
  form.append(l1, l2, l3, use);
  if (S.llm) {
    const off = el("button", "btn", "Use the router"); off.type = "button";
    off.addEventListener("click", () => { S.llm = null; try { sessionStorage.removeItem("ks-llm"); } catch { /* ignore */ } paintMode(); showTab("key"); });
    form.append(off);
  }
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!key.value.trim() && !S.llm) { key.focus(); return; }
    const p = PROVIDERS[sel.value];
    S.llm = { ...p.cfg, id: sel.value, model: model.value.trim() || p.model, key: key.value.trim() || S.llm?.key };
    try { sessionStorage.setItem("ks-llm", JSON.stringify(S.llm)); } catch { /* ignore */ }
    paintMode();
    closeSheet();
    $("#q").focus();
  });
  f.append(form, empty("The key stays in this tab and travels only with your question. The model picks tools; it never writes Cypher."));
  return f;
}
/* what answered the last question: a model (yours, or the server's) or the deterministic router */
function paintMode(mode) {
  const b = $("#mode");
  const model = S.llm ? PROVIDERS[S.llm.id]?.label.toUpperCase() || "MODEL" : S.server ? "MODEL" : "ROUTER";
  const router = mode === "scripted" || mode === "llm->scripted";
  b.textContent = router ? "ROUTER" : model;
  b.title = mode === "llm->scripted" ? "The model failed or named someone the graph did not return, so the router answered" : "How the agent answers";
}

/* ---------------------------------------------------------------- start */
timecode($("#tc"));
paintMode();
api("/api/health").then((h) => { S.server = !!h.server_llm; paintMode(); }).catch(() => { /* the label stays ROUTER */ });
new ResizeObserver(() => document.documentElement.style.setProperty("--bh", `${Math.round($(".bottom").getBoundingClientRect().height)}px`)).observe($(".bottom"));
boot();
