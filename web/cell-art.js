/* The one diagram used everywhere: a hub (the module) with a spoke per holder, dot size = share.
   The removed holder sits on the right just above the horizontal, with its name beside it and a tracking tear above and below the name. */
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); if (parent) parent.appendChild(n); return n; };

export function cellArt(svg, holders, { cut = false, label = true, cx: hubX } = {}) {
  svg.textContent = "";
  const list = holders.slice(0, 9);
  const gone = list.findIndex((h) => h.removed);
  const cx = hubX ?? (gone >= 0 ? 90 : 128), cy = 98, R = 84, n = Math.max(list.length, 1);
  const a0 = gone >= 0 ? -4 : -90;
  const nodes = [];
  if (gone >= 0) nodes.push({ h: list[gone], a: a0 });
  let k = gone >= 0 ? 1 : 0;
  list.forEach((h, i) => { if (i !== gone) { nodes.push({ h, a: a0 + (k * 360) / n }); k++; } });

  const lines = el("g", { stroke: "#8a8f96", "stroke-width": "1.2" }, svg);
  const dots = el("g", {}, svg);
  const out = { removed: null, label: null, tear: null };
  nodes.forEach(({ h, a }) => {
    const rad = (a * Math.PI) / 180;
    const x = cx + R * Math.cos(rad), y = cy + R * Math.sin(rad);
    const r = h.removed ? 11 : Math.max(6.5, Math.min(13, 5.5 + 11 * Math.sqrt(h.share)));
    const ln = el("line", { x1: cx, y1: cy, x2: x, y2: y, "data-who": h.person }, lines);
    const dot = el("circle", { cx: x, cy: y, r, fill: h.removed ? "var(--red)" : h.planned ? "var(--green)" : "#b9bdc3", "data-who": h.person }, dots);
    el("title", {}, dot).textContent = h.planned ? `${h.person} (planned)` : `${h.person} ${Math.round(h.share * 100)}%`;
    if (h.removed) {
      out.removed = { x, y, r, line: ln, dot };
      ln.setAttribute("stroke", "var(--red)");
      if (cut) { ln.setAttribute("stroke-dasharray", "3 5"); ln.setAttribute("opacity", "0.55"); }
    }
  });
  el("circle", { cx, cy, r: 26, fill: "#5d6167" }, svg);
  if (out.removed) {
    const { x, y, r } = out.removed;
    const tg = el("g", { class: "tear", transform: `translate(${x + r + 4}, ${y})` }, svg);
    [-17, -13, -9, 9, 13, 17].forEach((dy) => el("rect", { x: 0, y: dy, width: 24, height: 1.6, fill: "var(--red)", opacity: "0" }, tg));
    out.tear = tg;
    if (label) {
      const t = el("text", { x: x + r + 7, y: y + 4, fill: "var(--paper)", "font-family": "var(--mono)", "font-size": "12", style: "font-stretch:75%;font-weight:500" }, svg);
      t.textContent = list[gone].person;
      out.label = t;
    }
  }
  return out;
}
