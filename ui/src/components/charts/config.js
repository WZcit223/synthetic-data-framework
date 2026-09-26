// The Chart.js configuration of each chart component, built from its props and
// the theme's colours. Pure (no DOM, no Chart.js import), so every chart's
// datasets are tested without a canvas. Every array handed to Chart.js is a fresh
// copy: Chart.js defines properties on its data arrays, which a page's reactive
// state (a Svelte $state proxy) does not allow. Contract: docs/refactor/frontend/interfaces.md §2.2.

/**
 * The colours a chart draws with, read from the theme at render time.
 * @typedef {{series: string[], other: string, heat: string[], ink: string, muted: string,
 *   rule: string, surface: string, raised: string, bad: string}} Look
 */

// Colours for the series names: a series keeps the colour its name got first
// (lib/palette.js colorBook), unless the caller gave one.
function colored(series, book) {
  const colors = book.assign(series.map(s => s.name));
  return series.map(s => ({ ...s, color: s.color ?? colors.get(s.name) }));
}

function base(look, format, { legend = true } = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: legend, labels: { color: look.ink, boxWidth: 12 } },
      tooltip: {
        backgroundColor: look.raised,
        titleColor: look.ink,
        bodyColor: look.ink,
        borderColor: look.rule,
        borderWidth: 1,
        callbacks: { label: ctx => `${ctx.dataset.label}: ${format(ctx.parsed.y ?? ctx.parsed.x)}` },
      },
    },
  };
}

const axis = (look, extra = {}) => ({ ticks: { color: look.muted }, grid: { color: look.rule }, border: { color: look.rule }, ...extra });

/**
 * Lines over shared labels; a null value is a gap. An optional band fills
 * between its low and high, and not where either is null.
 */
export function lineConfig({ series, labels, yLabel, format, tickFormat = format, band }, look, book) {
  const lines = colored(series, book).map(s => ({
    type: "line",
    label: s.name,
    data: [...s.values],
    borderColor: s.color,
    backgroundColor: s.color,
    borderWidth: 2,
    pointRadius: 0,
    spanGaps: false,
  }));
  const datasets = [...lines];
  if (band) {
    const color = lines[0]?.borderColor ?? look.series[0];
    const edge = { type: "line", borderWidth: 0, pointRadius: 0, spanGaps: false };
    datasets.unshift(
      { ...edge, label: `${band.name} (low)`, data: [...band.low], fill: false, borderColor: color },
      { ...edge, label: band.name, data: [...band.high], fill: "-1", borderColor: color, backgroundColor: color + "4d" }, // 30 %: visible on the dark surface too
    );
  }
  const options = base(look, format);
  options.plugins.legend.labels.filter = item => !item.text.endsWith(" (low)");
  options.scales = {
    x: axis(look, { ticks: { color: look.muted, maxTicksLimit: 8, autoSkip: true } }),
    y: axis(look, {
      beginAtZero: true,
      title: { display: !!yLabel, text: yLabel ?? "", color: look.muted },
      ticks: { color: look.muted, callback: v => tickFormat(v) },
    }),
  };
  return { type: "line", data: { labels: [...labels], datasets }, options };
}

/** Bars, grouped or stacked, vertical or horizontal; a null value draws no bar. */
export function barConfig({ series, labels, format, tickFormat = format, stacked = false, horizontal = false }, look, book) {
  const datasets = colored(series, book).map(s => ({
    label: s.name,
    data: [...s.values],
    backgroundColor: s.color,
    borderRadius: 4,
    borderSkipped: "start",
  }));
  const value = { stacked, beginAtZero: true, ...axis(look), ticks: { color: look.muted, callback: v => tickFormat(v) } };
  const category = { stacked, ...axis(look), grid: { display: false } };
  const options = base(look, format, { legend: series.length > 1 });
  options.indexAxis = horizontal ? "y" : "x";
  options.plugins.tooltip.callbacks.label = ctx => `${ctx.dataset.label}: ${format(horizontal ? ctx.parsed.x : ctx.parsed.y)}`;
  options.scales = horizontal ? { x: value, y: category } : { x: category, y: value };
  return { type: "bar", data: { labels: [...labels], datasets }, options };
}

/**
 * One point with its interval per row, top to bottom in the given order (a
 * scatter with x error bars); a null low or high draws the point alone. A row's
 * colour is its own `color`, else its `group`'s by name. The optional reference
 * is a dashed vertical line (0 for effects, the true effect for estimators).
 */
export function intervalConfig({ rows, format, reference, range = null }, look, book) {
  const colors = book.assign([...new Set(rows.filter(r => !r.color).map(r => r.group ?? ""))]);
  /** @type {any[]} */
  const datasets = rows.map((r, i) => {
    const color = r.color ?? colors.get(r.group ?? "");
    return {
      type: "scatterWithErrorBars",
      label: r.label,
      data: [{ x: r.estimate, y: i, xMin: r.low ?? r.estimate, xMax: r.high ?? r.estimate, label: r.label }],
      backgroundColor: color,
      borderColor: look.surface,
      borderWidth: 2,
      errorBarColor: color,
      errorBarWhiskerColor: color,
      errorBarLineWidth: 2,
      errorBarWhiskerSize: 10,
      pointRadius: 5,
      radius: 5, // the error-bar point element reads `radius`
      hoverRadius: 6,
    };
  });
  if (reference != null) {
    datasets.push({
      type: "line",
      label: "reference",
      data: [{ x: reference, y: -0.5 }, { x: reference, y: rows.length - 0.5 }],
      borderColor: look.ink,
      borderDash: [4, 3],
      borderWidth: 1.5,
      pointRadius: 0,
    });
  }
  const options = base(look, format, { legend: false });
  options.plugins.tooltip.filter = item => item.dataset.label !== "reference";
  options.plugins.tooltip.callbacks.label = ctx => {
    const p = ctx.raw;
    return p.xMin === p.xMax && p.xMin === p.x ? `${p.label}: ${format(p.x)}` : `${p.label}: ${format(p.x)} [${format(p.xMin)}, ${format(p.xMax)}]`;
  };
  options.scales = {
    x: axis(look, { ticks: { color: look.muted, callback: v => format(v) }, ...(range ? { min: range[0], max: range[1] } : {}) }),
    y: axis(look, {
      type: "linear",
      reverse: true,
      min: -0.5,
      max: rows.length - 0.5,
      grid: { display: false },
      afterBuildTicks: scale => { scale.ticks = rows.map((_, i) => ({ value: i })); },
      ticks: { color: look.muted, autoSkip: false, callback: v => rows[v]?.label ?? "" },
    }),
  };
  return { type: "scatterWithErrorBars", data: { datasets }, options };
}

// A stable jitter in [-0.25, 0.25] for the i-th point of a group, from the group's
// name: a redraw puts every point where it was.
export function jitter(name, i) {
  let h = 2166136261;
  for (const ch of `${name}:${i}`) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return ((h >>> 0) / 4294967295 - 0.5) / 2;
}

/**
 * Points per group, one row each, jittered vertically, with the group's mean as
 * given (never computed here) drawn as a tick.
 */
export function stripConfig({ groups, format }, look, book) {
  const colors = book.assign(groups.map(g => g.name));
  const datasets = groups.map((g, gi) => ({
    type: "scatter",
    label: g.name,
    data: g.values.map((v, i) => ({ x: v, y: gi + jitter(g.name, i) })),
    backgroundColor: colors.get(g.name) + "99",
    borderColor: colors.get(g.name),
    pointRadius: 3,
  }));
  datasets.push({
    type: "scatter",
    label: "mean",
    data: groups.map((g, gi) => ({ x: g.mean, y: gi })),
    pointStyle: "line",
    rotation: 90,
    pointRadius: 12,
    borderWidth: 3,
    borderColor: look.ink,
    backgroundColor: look.ink,
  });
  const options = base(look, format, { legend: false });
  options.plugins.tooltip.callbacks.label = ctx =>
    ctx.dataset.label === "mean" ? `mean: ${format(ctx.parsed.x)}` : `${ctx.dataset.label}: ${format(ctx.parsed.x)}`;
  options.scales = {
    x: axis(look, { ticks: { color: look.muted, callback: v => format(v) } }),
    y: axis(look, {
      type: "linear",
      reverse: true,
      min: -0.5,
      max: groups.length - 0.5,
      grid: { display: false },
      afterBuildTicks: scale => { scale.ticks = groups.map((_, i) => ({ value: i })); },
      ticks: { color: look.muted, autoSkip: false, callback: v => groups[v]?.name ?? "" },
    }),
  };
  return { type: "scatter", data: { datasets }, options };
}

/** The heat ramp step for t in [0, 1]. */
export const rampStep = (ramp, t) => ramp[Math.min(ramp.length - 1, Math.max(0, Math.floor(t * ramp.length)))];

/**
 * A value per cell on the sequential ramp, scaled over `domain` ([low, high]) or,
 * without one, from the smallest to the largest value shown; a missing or null
 * cell is drawn empty. A flagged cell gets a ring in the "bad" colour; a cell's
 * label is its tooltip.
 */
export function heatConfig({ cells, columns, rows, format, domain }, look) {
  const known = cells.filter(c => c.value != null);
  const [lo, hi] = domain ?? [Math.min(...known.map(c => c.value)), Math.max(...known.map(c => c.value))];
  const t = v => (hi > lo ? (v - lo) / (hi - lo) : 0.5); // all equal: the middle of the ramp, neither end
  const data = known.map(c => ({ x: c.column, y: c.row, v: c.value, label: c.label, flag: !!c.flag }));
  const options = base(look, format, { legend: false });
  options.plugins.tooltip.callbacks = {
    title: () => "",
    label: ctx => ctx.raw.label ?? `${ctx.raw.y} · ${ctx.raw.x}: ${format(ctx.raw.v)}`,
  };
  options.scales = {
    x: { type: "category", labels: columns, offset: true, ticks: { color: look.muted }, grid: { display: false }, border: { display: false } },
    // a category y axis draws its first label at the bottom; the first row belongs on top
    y: { type: "category", labels: [...rows].reverse(), offset: true, ticks: { color: look.muted }, grid: { display: false }, border: { display: false } },
  };
  return {
    type: "matrix",
    data: {
      datasets: [{
        label: "value",
        data,
        backgroundColor: ctx => rampStep(look.heat, t(ctx.raw?.v ?? lo)),
        borderColor: ctx => (ctx.raw?.flag ? look.bad : look.surface),
        borderWidth: ctx => (ctx.raw?.flag ? 2 : 1),
        width: ({ chart }) => (chart.chartArea ? chart.chartArea.width / columns.length - 2 : 0),
        height: ({ chart }) => (chart.chartArea ? chart.chartArea.height / rows.length - 2 : 0),
      }],
    },
    options,
  };
}
