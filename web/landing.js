import { reduced, timecode, colorBars, grain, settle, tear, cellArt } from "/static/fx.js";

const LEAVER = "Anchel123";
const $ = (s, r = document) => r.querySelector(s);
const wall = $("#cells");

timecode($("#tc"));
colorBars($("#bars"));
grain($(".frame"));

const NS = "http://www.w3.org/2000/svg";
const mk = (tag, attrs = {}, text) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); if (text) n.textContent = text; return n; };
const html = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
function lockIcon() {
  const s = mk("svg", { class: "lock", viewBox: "0 0 24 24", "aria-hidden": "true" });
  s.append(mk("rect", { x: 5, y: 11, width: 14, height: 10 }), mk("path", { d: "M8 11V7a4 4 0 0 1 8 0v4" }));
  return s;
}

async function load() {
  try {
    const r = await fetch(`/api/cells?tenant=falkordb&leaver=${LEAVER}&n=12&affected=8`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch {
    return await (await fetch("/static/snapshot.json")).json();   // static copy of the same payload, for hosts without the API
  }
}

/* four cells with a spread: the biggest cut, a middling one, a mild one, and one that holds */
function choose(all) {
  const hits = all.filter((c) => c.affected), rest = all.filter((c) => !c.affected);
  const out = hits.slice(0, 1);
  for (const target of [0.45, 0.62]) {
    const next = hits.filter((c) => !out.includes(c)).sort((a, b) => Math.abs(a.retained - target) - Math.abs(b.retained - target))[0];
    if (next) out.push(next);
  }
  return [...out, ...rest.slice(0, 1)];
}

function build(data) {
  wall.textContent = "";
  return choose(data.cells).map((c, i) => {
    const pct = Math.round(c.retained * 100);
    const cell = document.createElement("article");
    cell.className = "cell";
    cell.dataset.state = "locked";
    const gone = c.holders.find((h) => h.removed);
    cell.setAttribute("aria-label", `${c.name}: ${pct} percent of its knowledge stays if ${data.leaver} leaves`);
    const pctEl = html("p", "cell-pct", "100%");
    pctEl.setAttribute("aria-hidden", "true");
    cell.append(html("h2", "cell-name", c.name.replace(/([:/])/g, "$1\u200b")), pctEl, lockIcon(), mk("svg", { class: "cell-art", viewBox: "0 0 256 214", role: "presentation" }));
    wall.appendChild(cell);
    const art = cellArt($(".cell-art", cell), c.holders, { cut: false, label: !!gone && c.affected && i === 0 });   // the leaver is named once
    return { c, cell, art, pct, affected: c.affected && !!gone };
  });
}

function cutCell({ cell, art, c, pct }, i) {
  return new Promise((res) => setTimeout(async () => {
    cell.dataset.state = "cut";
    if (art.removed) {
      art.removed.line.setAttribute("stroke-dasharray", "3 5");
      art.removed.line.setAttribute("opacity", "0.55");
      tear(art.tear, 760);
    }
    await settle($(".cell-pct", cell), 100, pct);
    res();
  }, i * 140));
}

async function run() {
  const data = await load();
  const cells = build(data);
  if (!cells.length) return;
  const hit = cells.filter((x) => x.affected);
  if (reduced) {          // the settled state, no motion
    hit.forEach((x) => { x.cell.dataset.state = "cut"; $(".cell-pct", x.cell).textContent = `${x.pct}%`; if (x.art.removed) { x.art.removed.line.setAttribute("stroke-dasharray", "3 5"); x.art.removed.line.setAttribute("opacity", "0.55"); } });
    cells.filter((x) => !x.affected).forEach((x) => { $(".cell-pct", x.cell).textContent = `${x.pct}%`; });
    return;
  }
  const headline = $("#headline");
  let playing = false;                                  // a click mid-run must not start a second run
  const play = async () => {
    if (playing) return;
    playing = true;
    cells.forEach((x) => { x.cell.dataset.state = "locked"; $(".cell-pct", x.cell).textContent = "100%"; });
    await new Promise((r) => setTimeout(r, 900));
    headline.classList.add("is-glitch");
    setTimeout(() => headline.classList.remove("is-glitch"), 160);
    await Promise.all(hit.map((x, i) => cutCell(x, i)));
    await Promise.all(cells.filter((x) => !x.affected).map((x) => settle($(".cell-pct", x.cell), 100, x.pct)));
    playing = false;
  };
  await play();
  wall.addEventListener("click", async (e) => { if (e.target.closest(".cell")) { cells.forEach((x) => { if (x.art.removed) { x.art.removed.line.removeAttribute("stroke-dasharray"); x.art.removed.line.setAttribute("opacity", "1"); } }); await play(); } });
  setInterval(() => { if (!document.hidden) { const t = hit[0]; if (t?.art.removed) tear(t.art.tear, 520); } }, 6500);
}
run();

/* below the fold: three illustrations with the same diagram, and the tool crawl */
const steps = {
  read: [{ person: "a", share: 0.4 }, { person: "b", share: 0.25 }, { person: "c", share: 0.2 }, { person: "d", share: 0.1 }, { person: "e", share: 0.05 }],
  remove: [{ person: "a", share: 0.4, removed: true }, { person: "b", share: 0.25 }, { person: "c", share: 0.2 }, { person: "d", share: 0.1 }, { person: "e", share: 0.05 }],
  plan: [{ person: "a", share: 0.4, removed: true }, { person: "b", share: 0.25 }, { person: "c", share: 0.2 }, { person: "d", share: 0.1 }, { person: "e", share: 0.05 }],
};
const demo = {};
document.querySelectorAll("[data-demo]").forEach((svg) => {
  const k = svg.dataset.demo;
  const art = demo[k] = cellArt(svg, steps[k], { cut: k !== "read", label: false });
  if (k === "plan") { const d = art.removed.dot; d.setAttribute("fill", "var(--green)"); art.removed.line.setAttribute("stroke", "var(--green)"); art.removed.line.removeAttribute("stroke-dasharray"); art.removed.line.setAttribute("opacity", "1"); }
});

/* reveals: each evidence number settles in once when it scrolls into view; step 2 tears once */
const counted = [...document.querySelectorAll(".nums b")].map((b) => {
  const m = b.textContent.match(/^([\d.]+)(.*)$/);
  if (m && !reduced) b.textContent = `0${m[2]}`;
  return { b, to: m ? +m[1] : 0, tail: m ? m[2] : "" };
});
const seen = new IntersectionObserver((list) => list.forEach((e) => {
  if (!e.isIntersecting) return;
  seen.unobserve(e.target);
  const c = counted.find((x) => x.b === e.target);
  if (c) settle(c.b, 0, c.to, { fmt: (v) => `${Math.round(v)}${c.tail}`, w: 5 });
  else if (e.target.dataset.demo === "remove" && demo.remove.tear) tear(demo.remove.tear, 900);
}), { threshold: 0.6 });
if (!reduced) { counted.forEach((c) => seen.observe(c.b)); seen.observe($('[data-demo="remove"]')); }
const tools = ["overview", "find_modules", "module_risk", "risk_scan", "keystones", "what_if_leaves", "successors", "who_knows", "knowledge_map", "path_between", "recall", "changes_since", "succession_review", "draft_actions", "note_finding"];
const writes = new Set(["succession_review", "draft_actions", "note_finding"]);   // the tools that write to the graph
tools.forEach((t) => $("#tools-list").append(html("li", writes.has(t) ? "w" : "", t)));
