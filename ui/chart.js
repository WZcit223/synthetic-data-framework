// Charts for the Explore page, drawn as SVG strings (labels escaped) with a
// hover and keyboard layer bound afterwards. One y-axis per chart: several
// values become small multiples, never a second scale.
import { esc } from "./common.js";
import { SURFACE } from "./palette.js";

// Round tick values covering [lo, hi]: 0 / 1,000 / 2,000, never 0 / 1,137 / 2,274.
export function niceTicks(lo, hi, count = 5) {
  if (!(hi > lo)) {
    const v = Number.isFinite(hi) ? hi : 0;
    [lo, hi] = v === 0 ? [0, 1] : v > 0 ? [0, v] : [v, 0];
  }
  const raw = (hi - lo) / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) ?? 10 * mag;
  const start = Math.floor(lo / step + 1e-9) * step;
  const end = Math.ceil(hi / step - 1e-9) * step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Math.abs(v) < step / 1e6 ? 0 : +v.toPrecision(12));
  return { lo: start, hi: end, ticks };
}

// A label cut to about ``max`` characters, with an ellipsis.
export const clip = (s, max) => (s.length > max ? s.slice(0, Math.max(1, max - 1)) + "…" : s);

// A horizontal bar from x0 to x1 with a 4px rounded data end and a square baseline end.
function hbar(x0, x1, y, h, round = true) {
  const w = Math.abs(x1 - x0);
  const r = round ? Math.min(4, h / 2, w) : 0;
  if (x1 >= x0) {
    return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`;
  }
  return `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 + r},${y + h}H${x0}Z`;
}

const CHAR = 6.6; // average glyph width at 11px, for sizing label columns

/**
 * Horizontal bars: one band per category, one bar per series (or one stacked bar).
 * ``model``: {categories: [{label, values: [per series]}], series: [{name, color}],
 *   stacked, format, compact, width}. Returns {svg, tips}.
 */
export function barChart({ categories, series, stacked = false, format, compact, width }) {
  const n = series.length;
  const labelW = Math.min(220, Math.max(64, Math.max(...categories.map(c => c.label.length)) * CHAR + 12));
  const barH = stacked || n === 1 ? 18 : n <= 3 ? 14 : n <= 5 ? 10 : 8;
  const bandH = (stacked ? barH : n * barH + (n - 1) * 2) + 14;
  const top = 8, axisH = 24, right = 64;
  const plotW = Math.max(120, width - labelW - right);
  const height = top + categories.length * bandH + axisH;

  let lo = 0, hi = 0;
  for (const c of categories) {
    if (stacked) {
      const pos = c.values.reduce((s, v) => s + (v > 0 ? v : 0), 0);
      const neg = c.values.reduce((s, v) => s + (v < 0 ? v : 0), 0);
      hi = Math.max(hi, pos); lo = Math.min(lo, neg);
    } else {
      for (const v of c.values) if (v != null) { hi = Math.max(hi, v); lo = Math.min(lo, v); }
    }
  }
  const scale = niceTicks(lo, hi, Math.max(2, Math.round(plotW / 110)));
  const X = v => labelW + ((v - scale.lo) / (scale.hi - scale.lo)) * plotW;
  const x0 = X(0);

  let s = `<svg class="chart" role="img" aria-label="Bar chart" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  s += `<g class="grid">`;
  for (const t of scale.ticks) s += `<line x1="${X(t)}" x2="${X(t)}" y1="${top}" y2="${height - axisH}"/>`;
  s += `</g><g class="axis"><line x1="${x0}" x2="${x0}" y1="${top}" y2="${height - axisH}"/></g>`;
  for (const t of scale.ticks) s += `<text x="${X(t)}" y="${height - 8}" text-anchor="middle">${esc(compact(t))}</text>`;

  const tips = [];
  categories.forEach((c, i) => {
    const y = top + i * bandH + 7;
    s += `<g class="band" tabindex="0" data-tip="${i}" aria-label="${esc(c.label)}">`;
    s += `<rect class="hit" x="0" y="${y - 7}" width="${width}" height="${bandH}"/>`;
    s += `<text x="${labelW - 10}" y="${y + (bandH - 14) / 2 + 4}" text-anchor="end">${esc(clip(c.label, Math.floor((labelW - 12) / CHAR)))}</text>`;
    if (stacked) {
      let pos = 0, neg = 0;
      // the outermost segment on each side of zero carries the rounded end and reaches the tip
      const lastPos = c.values.reduce((l, v, k) => (v > 0 ? k : l), -1);
      const lastNeg = c.values.reduce((l, v, k) => (v < 0 ? k : l), -1);
      c.values.forEach((v, k) => {
        if (v == null || v === 0) return;
        const from = v > 0 ? pos : neg;
        const to = from + v;
        v > 0 ? (pos = to) : (neg = to);
        const outer = k === (v > 0 ? lastPos : lastNeg);
        // a 2px surface gap separates touching segments
        const a = X(from) + (from === 0 ? 0 : v > 0 ? 1 : -1), b = X(to) - (outer ? 0 : v > 0 ? 1 : -1);
        s += `<path class="bar" d="${hbar(a, b, y, barH, outer)}" fill="${series[k].color}"/>`;
      });
      const total = c.values.reduce((t, v) => t + (v ?? 0), 0);
      if (c.values.some(v => v != null)) {
        // the total sits beside the tip on its own side: a net-negative stack is labelled at its negative end
        const [tx, anchor] = total < 0 ? [X(neg) - 6, "end"] : [X(pos) + 6, "start"];
        s += `<text class="value" x="${tx}" y="${y + barH / 2 + 4}" text-anchor="${anchor}">${esc(format(total))}</text>`;
      }
    } else {
      c.values.forEach((v, k) => {
        if (v == null) return;
        const by = y + k * (barH + 2);
        s += `<path class="bar" d="${hbar(x0, X(v), by, barH)}" fill="${series[k].color}"/>`;
        if (n === 1) {
          const tx = v >= 0 ? X(v) + 6 : X(v) - 6;
          s += `<text class="value" x="${tx}" y="${by + barH / 2 + 4}" text-anchor="${v >= 0 ? "start" : "end"}">${esc(format(v))}</text>`;
        }
      });
    }
    s += `</g>`;
    // a band lists the series that have a value there; a sparse cross-tab would otherwise list mostly blanks
    const lines = series.map((sr, k) => ({ color: sr.color, label: sr.name, v: c.values[k] })).filter(l => n === 1 || l.v != null);
    tips.push({
      head: c.label,
      lines: lines.length ? lines.map(l => ({ color: l.color, label: l.label, value: format(l.v) })) : [{ color: "transparent", label: "no value", value: "–" }],
    });
  });
  return { svg: s + `</svg>`, tips };
}

/**
 * A line per series over ordered x positions (time keys).
 * ``model``: {points: [labels], series: [{name, color, values}], format, compact, width}.
 * Returns {svg, geometry} for the crosshair.
 */
export function lineChart({ points, series, format, compact, width }) {
  const endLabels = series.length > 1 && series.length <= 4;
  const left = 56, right = endLabels ? 118 : 24, top = 14, bottom = 28, height = 300;
  const plotW = Math.max(120, width - left - right), plotH = height - top - bottom;
  let lo = 0, hi = 0;
  for (const sr of series) for (const v of sr.values) if (v != null) { hi = Math.max(hi, v); lo = Math.min(lo, v); }
  const scale = niceTicks(lo, hi, 5);
  const X = i => left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const Y = v => top + plotH - ((v - scale.lo) / (scale.hi - scale.lo)) * plotH;

  let s = `<svg class="chart" role="img" aria-label="Line chart" tabindex="0" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  s += `<rect class="plotframe" x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="none" stroke="none"/>`;
  s += `<g class="grid">`;
  for (const t of scale.ticks) s += `<line x1="${left}" x2="${left + plotW}" y1="${Y(t)}" y2="${Y(t)}"/>`;
  s += `</g><g class="axis"><line x1="${left}" x2="${left + plotW}" y1="${Y(Math.max(scale.lo, Math.min(0, scale.hi)))}" y2="${Y(Math.max(scale.lo, Math.min(0, scale.hi)))}"/></g>`;
  for (const t of scale.ticks) s += `<text x="${left - 8}" y="${Y(t) + 4}" text-anchor="end">${esc(compact(t))}</text>`;
  const every = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(plotW / 84))));
  points.forEach((p, i) => {
    if (i % every === 0 || i === points.length - 1 && (points.length - 1) % every > every / 2) {
      s += `<text x="${X(i)}" y="${height - 8}" text-anchor="middle">${esc(p)}</text>`;
    }
  });
  for (const sr of series) {
    let d = "", pen = false;
    const lone = [];
    sr.values.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      const prevNull = i === 0 || sr.values[i - 1] == null, nextNull = i === sr.values.length - 1 || sr.values[i + 1] == null;
      if (prevNull && nextNull) lone.push(i);
      d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
      pen = true;
    });
    s += `<path d="${d}" fill="none" stroke="${sr.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    for (const i of lone) s += `<circle cx="${X(i)}" cy="${Y(sr.values[i])}" r="4" fill="${sr.color}" stroke="${SURFACE}" stroke-width="2"/>`;
  }
  if (endLabels) {
    const ends = series
      .map(sr => {
        const i = sr.values.findLastIndex(v => v != null);
        return i < 0 ? null : { sr, i, y: Y(sr.values[i]) };
      })
      .filter(Boolean)
      .sort((a, b) => a.y - b.y);
    const collide = ends.some((e, k) => k && e.y - ends[k - 1].y < 14);
    if (!collide) { // converging ends fall back to the legend and the tooltip
      for (const e of ends) {
        s += `<circle cx="${X(e.i)}" cy="${e.y}" r="4" fill="${e.sr.color}" stroke="${SURFACE}" stroke-width="2"/>`;
        s += `<text x="${X(e.i) + 10}" y="${e.y + 4}" style="fill:var(--ink)">${esc(clip(e.sr.name, 16))}</text>`;
      }
    }
  }
  s += `<line class="cross" x1="0" x2="0" y1="${top}" y2="${top + plotH}" visibility="hidden"/><g class="dots"></g>`;
  s += `<rect class="hit" x="${left}" y="${top}" width="${plotW}" height="${plotH}"/>`;
  return { svg: s + `</svg>`, geometry: { X, Y, left, plotW, n: points.length } };
}

// The tooltip: values lead, labels follow; built with textContent (labels are data).
export function showTip(el, { head, lines }, x, y) {
  el.replaceChildren();
  const h = document.createElement("div");
  h.className = "head";
  h.textContent = head;
  el.append(h);
  for (const l of lines) {
    const row = document.createElement("div");
    row.className = "line";
    const key = document.createElement("span");
    key.className = "key";
    key.style.background = l.color;
    const v = document.createElement("span");
    v.className = "tv";
    v.textContent = l.value;
    const t = document.createElement("span");
    t.className = "tl";
    t.textContent = l.label;
    row.append(key, v, t);
    el.append(row);
  }
  el.hidden = false;
  const r = el.getBoundingClientRect();
  const left = x + 14 + r.width > innerWidth ? x - r.width - 14 : x + 14;
  const top = Math.min(innerHeight - r.height - 8, Math.max(8, y - r.height / 2));
  el.style.left = `${Math.max(8, left)}px`;
  el.style.top = `${top}px`;
}

export function bindBars(root, tips, tipEl) {
  for (const band of root.querySelectorAll(".band")) {
    const tip = tips[+band.dataset.tip];
    band.addEventListener("pointermove", e => showTip(tipEl, tip, e.clientX, e.clientY));
    band.addEventListener("pointerleave", () => (tipEl.hidden = true));
    band.addEventListener("focus", () => {
      const r = band.getBoundingClientRect();
      showTip(tipEl, tip, r.left + Math.min(r.width / 2, 320), r.top + r.height / 2);
    });
    band.addEventListener("blur", () => (tipEl.hidden = true));
  }
}

// The x position a key moves the crosshair to: arrows step, Home and End jump; null for any other key.
export function stepIndex(key, at, n) {
  if (key === "Home") return 0;
  if (key === "End") return n - 1;
  if (key !== "ArrowLeft" && key !== "ArrowRight") return null;
  if (at == null) return key === "ArrowRight" ? 0 : n - 1;
  return Math.max(0, Math.min(n - 1, at + (key === "ArrowRight" ? 1 : -1)));
}

// Crosshair: a hairline snaps to the nearest x; the tooltip lists every series there.
export function bindLine(svg, { geometry, points, series, format }, tipEl) {
  const { X, Y, left, plotW, n } = geometry;
  const cross = svg.querySelector(".cross"), dots = svg.querySelector(".dots");
  let at = null;
  const show = (i, cx, cy) => {
    at = i;
    cross.setAttribute("x1", X(i));
    cross.setAttribute("x2", X(i));
    cross.setAttribute("visibility", "visible");
    dots.innerHTML = series
      .filter(sr => sr.values[i] != null)
      .map(sr => `<circle cx="${X(i)}" cy="${Y(sr.values[i])}" r="4" fill="${sr.color}" stroke="${SURFACE}" stroke-width="2"/>`)
      .join("");
    const lines = series
      .map(sr => ({ color: sr.color, label: sr.name, v: sr.values[i] }))
      .sort((a, b) => (b.v ?? -Infinity) - (a.v ?? -Infinity))
      .map(l => ({ color: l.color, label: l.label, value: format(l.v) }));
    showTip(tipEl, { head: points[i], lines }, cx, cy);
  };
  const hide = () => { cross.setAttribute("visibility", "hidden"); dots.innerHTML = ""; tipEl.hidden = true; };
  const nearest = clientX => {
    const r = svg.getBoundingClientRect();
    const x = (clientX - r.left) * (svg.viewBox.baseVal.width / r.width);
    return n === 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round(((x - left) / plotW) * (n - 1))));
  };
  const hit = svg.querySelector(".hit");
  hit.addEventListener("pointermove", e => show(nearest(e.clientX), e.clientX, e.clientY));
  hit.addEventListener("pointerleave", hide);
  svg.addEventListener("keydown", e => {
    const i = stepIndex(e.key, at, n);
    if (i == null) return;
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    const scaleX = r.width / svg.viewBox.baseVal.width;
    show(i, r.left + X(i) * scaleX, r.top + r.height / 2);
  });
  svg.addEventListener("blur", hide);
}
