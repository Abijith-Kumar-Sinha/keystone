/* Effects for the Stand By world: running timecode, tape-noise color bars, a damped number, a tracking tear.
   Every effect is a still frame under prefers-reduced-motion. */
export const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const pad = (n, w = 2) => String(n).padStart(w, "0");

export function timecode(el) {
  const draw = () => {
    const d = new Date();
    el.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}:${pad(Math.floor(d.getMilliseconds() / 40))}`;
  };
  draw();
  if (reduced) return;
  let last = 0;
  const loop = (t) => { if (t - last >= 40) { draw(); last = t; } requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}

const BARS = ["#d9d9d8", "#e3d20f", "#14b4e3", "#1fc13b", "#e024d7", "#ee2b2b", "#0b1ae5"];

/* Seven flat SMPTE bars with tape noise. `vertical` bars for the landing strip, horizontal strip for a thin accent. */
export function colorBars(canvas, { vertical = true, fps = 12 } = {}) {
  const ctx = canvas.getContext("2d");
  let roll = 0;
  const fit = () => {
    const r = canvas.getBoundingClientRect();
    const s = Math.max(0.5, Math.min(1, (window.devicePixelRatio || 1) / 2));   // half-res: it is noise anyway
    canvas.width = Math.max(8, Math.round(r.width * s));
    canvas.height = Math.max(8, Math.round(r.height * s));
    if (reduced) paint(false);                                                    // resizing clears a canvas
  };
  const paint = (animated) => {
    const { width: w, height: h } = canvas;
    const n = BARS.length;
    if (vertical) {
      // tape wobble: every pair of scanlines is drawn a pixel or two off, so the bar edges shimmer like a real tube
      for (let y = 0; y < h; y += 2) {
        const dx = Math.round(Math.sin(y * 0.05 + roll * 9) * 1.4 + (Math.random() < 0.03 ? (Math.random() - 0.5) * 7 : 0));
        BARS.forEach((c, i) => {
          ctx.fillStyle = c;
          const x0 = i === 0 ? 0 : Math.round((i * w) / n) + dx;
          const x1 = i === n - 1 ? w : Math.round(((i + 1) * w) / n) + dx;
          ctx.fillRect(x0, y, Math.max(1, x1 - x0) + 1, 2);
        });
      }
      // the last bar bleeds softly into the dark ground
      const g = ctx.createLinearGradient(w - 12, 0, w, 0);
      g.addColorStop(0, "rgba(11,11,15,0)");
      g.addColorStop(1, "rgba(11,11,15,0.6)");
      ctx.fillStyle = g;
      ctx.fillRect(w - 12, 0, 12, h);
    } else {
      BARS.forEach((c, i) => { ctx.fillStyle = c; ctx.fillRect(0, Math.round((i * h) / n), w, Math.ceil(h / n) + 1); });
    }
    // chroma smear: each bar bleeds a little into its right neighbour
    if (vertical) for (let i = 1; i < n; i++) { const x = Math.round((i * w) / n); const g = ctx.createLinearGradient(x - 3, 0, x + 6, 0); g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(255,255,255,0.10)"); ctx.fillStyle = g; ctx.fillRect(x - 3, 0, 9, h); }
    // tape noise: short horizontal streaks, brighter or darker than the bar under them
    const streaks = Math.round((w * h) / 2600);
    for (let k = 0; k < streaks; k++) {
      const y = Math.random() * h, len = (0.15 + Math.random() * 0.6) * w;
      ctx.fillStyle = Math.random() < 0.5 ? "rgba(255,255,255,0.20)" : "rgba(0,0,0,0.22)";
      ctx.fillRect(Math.random() * (w - len), y, len, Math.random() < 0.15 ? 2 : 1);
    }
    // a slow dark roll band, and a tracking tear lower down
    const by = (roll % 1) * (h + 120) - 60;
    ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.fillRect(0, by, w, 14);
    if (animated) { const ty = h * 0.42 + (Math.random() - 0.5) * 4; ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.fillRect(0, ty, w, 2); }
  };
  fit();
  new ResizeObserver(fit).observe(canvas);
  if (reduced) return;
  let last = 0;
  const loop = (t) => {
    if (t - last >= 1000 / fps) { roll += 0.012; paint(true); last = t; }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

/* Film grain: one small noise tile, drawn once, laid over the frame by CSS (--grain). Static, so it costs nothing per frame. */
export function grain(el, size = 160) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const img = g.createImageData(size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.random() < 0.5 ? 255 : 0;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = Math.random() * 26;
  }
  g.putImageData(img, 0, 0);
  el.style.setProperty("--grain", `url(${c.toDataURL()})`);
}

/* A critically damped number: settles like a needle, never snaps. */
export function settle(el, from, to, { fmt = (v) => `${Math.round(v)}%`, w = 7 } = {}) {
  if (reduced || from === to) { el.textContent = fmt(to); return Promise.resolve(); }
  return new Promise((res) => {
    const t0 = performance.now();
    const step = () => {
      const s = Math.max(0, (performance.now() - t0) / 1000);   // not the rAF stamp: it can precede t0, and exp(-w * s) explodes for s < 0
      const v = to + (from - to) * (1 + w * s) * Math.exp(-w * s);
      el.textContent = fmt(v);
      if (Math.abs(v - to) > 0.4 && s < 2) requestAnimationFrame(step); else { el.textContent = fmt(to); res(); }
    };
    requestAnimationFrame(step);
  });
}

/* Horizontal tracking tear: jitters a set of thin red bars to the right of a point, for `ms`. */
export function tear(group, ms = 700) {
  if (reduced) return;
  const bars = [...group.querySelectorAll("rect")];
  const t0 = performance.now();
  const frame = () => {
    const k = Math.min(1, Math.max(0, 1 - (performance.now() - t0) / ms));
    bars.forEach((b, i) => {
      b.setAttribute("x", String(8 + Math.random() * 26 * k));
      b.setAttribute("width", String(10 + Math.random() * 54 * k + i * 3));
      b.setAttribute("opacity", String(Math.random() < 0.7 ? k * 0.9 : 0));
    });
    if (k > 0) requestAnimationFrame(frame); else bars.forEach((b) => b.setAttribute("opacity", "0"));
  };
  requestAnimationFrame(frame);
}

export { cellArt } from "/static/cell-art.js";
