// The Explore page: pick a dataset or run an experiment, then cross-tabulate it
// by dragging fields onto Rows, Columns, Values and Filters. The whole view lives
// in the address (#view=…), so a copied link rebuilds it.
// UI rule: reshape what the API returned; never compute a business number here.
import { $, api, compactFormatter, esc, valueFormatter } from "./common.js";
import { barChart, bindBars, bindLine, lineChart } from "./chart.js";
import { HEAT, colorBook, heat, inkOn } from "./palette.js";
import { AGGREGATIONS, GRAINS, OTHER, distinctValues, keptCount, keyId, partLabel, pivot, toCsv, toTable, viewError } from "./pivot.js";

const AGG_LABEL = { sum: "Sum", count: "Count", count_distinct: "Distinct", mean: "Mean", median: "Median", min: "Min", max: "Max" };
const GRAIN_LABEL = { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year", weekday: "Weekday" };
const KIND_BADGE = { dimension: "Abc", time: "Date", measure: "123" };
const KIND_GROUP = [["dimension", "Dimensions"], ["time", "Time"], ["measure", "Measures"]];
const SHELVES = ["rows", "columns", "values", "filters"];
const MAX_TABLE_ROWS = 1000; // rows drawn before "Show all"
const MAX_TABLE_CELLS = 30_000; // and fewer rows when they are wide, so a wide cross-tab draws quickly
const MAX_TABLE_COLUMNS = 400; // value cells across; wider results are cut, and the CSV export has them all
const MAX_BARS = 50; // categories a bar chart draws; the table view has the rest
const MAX_SERIES = 8; // series a chart colours; the rest fold into "Other"
const DEFAULT_DISPLAY = { as: "table", heatmap: false, totals: true, stacked: false };

// One-click starting views. A preset is a saved view: it goes through the same code as one a user builds.
const PRESETS = {
  "order-lines": [
    { label: "Line value by category and month", view: { rows: [{ field: "category" }], columns: [{ field: "date", grain: "month" }], values: [{ field: "line_value", agg: "sum" }], filters: { status: { exclude: ["cancelled"] } }, sort: { by: "value", dir: "desc" } } },
    { label: "Daily units by ABC class", view: { rows: [{ field: "date", grain: "day" }], columns: [{ field: "abc_class" }], values: [{ field: "quantity", agg: "sum" }] }, display: { as: "chart" } },
    { label: "Order lines by weekday and channel", view: { rows: [{ field: "date", grain: "weekday" }], columns: [{ field: "channel" }], values: [{ field: "sku_id", agg: "count" }] }, display: { as: "chart", stacked: true } },
    { label: "Status mix by channel", view: { rows: [{ field: "channel" }], columns: [{ field: "status" }], values: [{ field: "sku_id", agg: "count" }], showAs: "share_of_row" }, display: { heatmap: true } },
  ],
  inventory: [
    { label: "Stock value by zone and ABC class", view: { rows: [{ field: "zone" }], columns: [{ field: "abc_class" }], values: [{ field: "stock_value", agg: "sum" }], sort: { by: "value", dir: "desc" } }, display: { heatmap: true } },
    { label: "Stock by category", view: { rows: [{ field: "category" }], values: [{ field: "on_hand", agg: "sum" }, { field: "available", agg: "sum" }, { field: "stock_value", agg: "sum" }], sort: { by: "value", dir: "desc" } } },
  ],
  "replenishment-plan": [
    { label: "SKUs needing an order by category", view: { rows: [{ field: "category" }], columns: [{ field: "needs_order" }], values: [{ field: "sku_id", agg: "count" }], sort: { by: "column", key: ["yes"], dir: "desc" } } },
    { label: "Order quantity by ABC class and demand pattern", view: { rows: [{ field: "abc_class" }, { field: "demand_pattern" }], values: [{ field: "order_qty", agg: "sum" }, { field: "safety_stock", agg: "sum" }], subtotals: true } },
  ],
  skus: [
    { label: "Mean unit price by category and ABC class", view: { rows: [{ field: "category" }], columns: [{ field: "abc_class" }], values: [{ field: "unit_price", agg: "mean" }] }, display: { heatmap: true } },
  ],
  experiment: [
    { label: "Outcomes by metric, intervention and policy", view: { rows: [{ field: "metric" }, { field: "intervention" }], columns: [{ field: "policy" }], values: [{ field: "value", agg: "mean" }] } },
  ],
};

const state = {
  datasets: [], // GET /datasets entries
  catalog: null, // GET /experiments/catalog, fetched when first needed
  source: null, // {dataset} | {experiment: body} | {synthesis: body}
  table: null, // toTable(payload)
  meta: null, // {title, description, world, total, truncated}
  view: emptyView(),
  display: { ...DEFAULT_DISPLAY },
  collapsed: new Set(), // keys of collapsed group rows
  showAll: false,
  result: null, // the last table pivot, for export and re-render
  seq: 0, // the latest source request; an older answer is dropped
  seriesKey: null, // the column fields the chart's colours were assigned for
  written: "", // the last #view= this page wrote
};
const colors = colorBook();

// The last pivots of the loaded table, keyed by view and options: a display change
// (heatmap, totals, table or chart) redraws without aggregating the rows again.
const pivots = new Map();
function cachedPivot(view, options = {}) {
  const key = JSON.stringify([view, options]);
  if (!pivots.has(key)) {
    if (pivots.size >= 4) pivots.delete(pivots.keys().next().value);
    pivots.set(key, pivot(state.table, view, options));
  }
  return pivots.get(key);
}

function emptyView() {
  return { rows: [], columns: [], values: [], filters: {}, showAs: "value", sort: { by: "label", dir: "asc" }, subtotals: false };
}

// -- fields ---------------------------------------------------------------------------------------

const fields = () => new Map((state.table?.fields ?? []).map(f => [f.name, f]));
const field = name => fields().get(name);
const onAxis = name => [...state.view.rows, ...state.view.columns].some(a => a.field === name);
const used = name => onAxis(name) || state.view.values.some(v => v.field === name) || name in state.view.filters;

function axisLabel(a) {
  const f = field(a.field);
  return f?.kind === "time" ? `${f.label} · ${GRAIN_LABEL[a.grain ?? "day"]}` : f?.label ?? a.field;
}

function valueLabel(v) {
  const f = field(v.field);
  if (v.agg === "count") return "Count of rows";
  if (v.agg === "count_distinct") return `Distinct ${f?.label ?? v.field}`;
  return `${AGG_LABEL[v.agg]} of ${f?.label ?? v.field}`;
}

function filterSummary(name, f) {
  const values = distinctValues(state.table, name);
  const kept = keptCount(values, f);
  if (kept === values.length) return "all";
  const held = new Set(values.map(x => x.value));
  if (f.include) {
    const shown = f.include.filter(x => held.has(x));
    return shown.length && shown.length <= 2 ? shown.map(partLabel).join(", ") : `${kept} of ${values.length}`;
  }
  const dropped = f.exclude.filter(x => held.has(x));
  return dropped.length <= 2 ? `all but ${dropped.map(partLabel).join(", ")}` : `${kept} of ${values.length}`;
}

// A time field's first grain: days for a month of data, weeks up to about half a year, then months.
function defaultGrain(name) {
  const days = distinctValues(state.table, name).length;
  return days <= 31 ? "day" : days <= 200 ? "week" : "month";
}

const defaultAgg = f => (f.kind === "measure" ? f.aggregate ?? "sum" : "count");
const aggsFor = f => (f.kind === "measure" ? AGGREGATIONS : ["count", "count_distinct"]);

// -- sources --------------------------------------------------------------------------------------

function sourceError(source) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return "the link names no source";
  const keys = Object.keys(source);
  if (keys.length !== 1) return `a source names exactly one of dataset, experiment or synthesis; got ${JSON.stringify(keys)}`;
  const [k] = keys;
  if (k === "dataset") return typeof source.dataset === "string" ? null : "dataset must be a name";
  if (k === "experiment" || k === "synthesis") return source[k] && typeof source[k] === "object" ? null : `${k} must be a request body`;
  return `unknown source ${JSON.stringify(k)}`;
}

async function fetchSource(source) {
  if (source.dataset != null) {
    const d = await api(`/datasets/${encodeURIComponent(source.dataset)}`);
    const entry = state.datasets.find(e => e.name === d.name);
    return { payload: d, meta: { title: d.label, description: entry?.description ?? "", world: d.world, total: d.total_rows, truncated: d.truncated } };
  }
  if (source.experiment != null) {
    const d = await api("/experiments", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(source.experiment),
    });
    return {
      payload: d,
      meta: { title: "Policy experiment", description: "Each intervention replayed under each policy; one row per outcome metric.", world: null, total: d.rows.length, truncated: false },
    };
  }
  // interfaces.md §3: the synthesis source shape is read here; its endpoint arrives with the synthesizer catalogue.
  throw new Error("this server does not run synthesizers yet, so a synthesis link cannot be opened here");
}

// Why a link's display settings cannot be used, or null.
function displayError(display) {
  if (display == null) return null;
  if (typeof display !== "object" || Array.isArray(display)) return "the display must be an object";
  for (const [k, v] of Object.entries(display)) {
    if (k === "as") { if (v !== "table" && v !== "chart") return "display.as must be table or chart"; }
    else if (["heatmap", "totals", "stacked"].includes(k)) { if (typeof v !== "boolean") return `display.${k} must be true or false`; }
    else return `the display has an unknown key ${JSON.stringify(k)}`;
  }
  return null;
}

// Forget the loaded source, so a failure shows an empty view and not the previous table's fields.
function clearSource() {
  state.source = null;
  state.table = null;
  state.meta = null;
  state.result = null;
  pivots.clear();
}

async function loadSource(source, { view = null, display = null } = {}) {
  const seq = ++state.seq;
  const problem = sourceError(source) ?? (view == null ? null : viewError(view)) ?? displayError(display);
  if (problem) {
    clearSource();
    return fail("This link cannot be opened", problem);
  }
  setBusy(true);
  try {
    const { payload, meta } = await fetchSource(source);
    if (seq !== state.seq) return;
    state.source = source;
    state.table = toTable(payload);
    pivots.clear();
    state.meta = meta;
    colors.reset();
    state.collapsed.clear();
    state.showAll = false;
    const preset = (PRESETS[presetKey()] ?? [])[0];
    // copies: editing the view must never edit the preset or the parsed link it came from
    state.view = { ...emptyView(), ...structuredClone(view ?? preset?.view ?? fallbackView()) };
    state.display = { ...DEFAULT_DISPLAY, ...structuredClone(view ? display : preset?.display) };
    if (view) {
      // a link's view must also fit this table (every field it names, grains on time fields): refuse it whole if
      // not. With no values the pivot still resolves the rows, columns and filters, so an empty view is checked too.
      try {
        cachedPivot(state.view);
      } catch (err) {
        clearSource();
        return fail("This link cannot be opened", err.message);
      }
    }
    syncSourceSelect();
    render();
  } catch (err) {
    if (seq !== state.seq) return;
    clearSource();
    fail(`Could not load ${describeSource(source)}`, err.detail ?? err.message);
  } finally {
    if (seq === state.seq) setBusy(false);
  }
}

const presetKey = () => (state.source?.dataset != null ? state.source.dataset : state.source?.experiment ? "experiment" : null);

function fallbackView() {
  const fs = state.table.fields;
  const dim = fs.find(f => f.kind === "dimension");
  const m = fs.find(f => f.kind === "measure");
  return {
    rows: dim ? [{ field: dim.name }] : [],
    values: m ? [{ field: m.name, agg: defaultAgg(m) }] : fs.length ? [{ field: fs[0].name, agg: "count" }] : [],
  };
}

function describeSource(source) {
  if (source?.dataset != null) return `dataset "${source.dataset}"`;
  if (source?.experiment) return "the experiment";
  if (source?.synthesis) return "the synthesizer run";
  return "this source";
}

// -- the address ----------------------------------------------------------------------------------

function readLink() {
  const m = location.hash.match(/^#view=(.+)$/);
  if (!m) return null;
  let link;
  try {
    link = JSON.parse(decodeURIComponent(m[1]));
  } catch {
    return { error: "the view in this link is not valid JSON" };
  }
  // any JSON parses, null and arrays included: only an object can hold a source and a view
  return link && typeof link === "object" && !Array.isArray(link) ? link : { error: "the link holds no source and view" };
}

function writeLink() {
  if (!state.source) return;
  const hash = "#view=" + encodeURIComponent(JSON.stringify({ source: state.source, view: state.view, display: state.display }));
  state.written = hash;
  if (location.hash !== hash) history.replaceState(null, "", hash);
}

function openLink() {
  const link = readLink();
  if (!link) return false;
  if (link.error) {
    state.seq++;
    clearSource();
    fail("This link cannot be opened", link.error);
  }
  else loadSource(link.source, { view: link.view ?? null, display: link.display ?? null });
  return true;
}

// -- rendering ------------------------------------------------------------------------------------

// The result area is about to change: a tooltip of a chart that is going away must not stay behind.
const hideTip = () => ($("#tooltip").hidden = true);

function setBusy(on) {
  $("#result").classList.toggle("busy", on); // the previous frame stays, dimmed: no skeleton, no jump
  $("#result").setAttribute("aria-busy", on ? "true" : "false");
}

function fail(title, detail) {
  state.result = null;
  hideTip();
  $("#result").innerHTML = `<div class="failure"><b>${esc(title)}</b><div>${esc(detail)}</div></div>`;
  $("#statusline").textContent = "";
  renderSourceInfo();
  renderPresets();
  renderFields();
  renderShelves();
  renderToolbar();
}

function render() {
  renderSourceInfo();
  renderPresets();
  renderFields();
  renderShelves();
  renderToolbar();
  renderResult();
  writeLink();
}

function renderSourceInfo() {
  const m = state.meta;
  const isExp = $("#source").value === "experiment";
  $("#expForm").hidden = !isExp;
  if (!m || (isExp && !state.source?.experiment)) {
    $("#sourceTitle").textContent = isExp ? "Policy experiment" : "";
    $("#sourceInfo").textContent = isExp ? "Choose interventions, policies and outcomes, then run the experiment." : "";
    return;
  }
  $("#sourceTitle").textContent = m.title;
  const bits = [m.description, `${m.total.toLocaleString()} rows`];
  if (m.world) bits.push(`world ${m.world}`);
  $("#sourceInfo").textContent = bits.filter(Boolean).join(" · ");
}

function renderPresets() {
  const list = state.table ? PRESETS[presetKey()] ?? [] : [];
  $("#presets").innerHTML = list.length
    ? `<span class="lead">Presets</span>` + list.map((p, i) => `<button type="button" class="preset" data-preset="${i}" aria-pressed="${isPreset(p)}">${esc(p.label)}</button>`).join("")
    : "";
}

// Whether the current view is this preset, unchanged.
function isPreset(p) {
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  return same(state.view, { ...emptyView(), ...p.view }) && same(state.display, { ...DEFAULT_DISPLAY, ...p.display });
}

function renderFields() {
  const q = $("#fieldSearch").value.trim().toLowerCase();
  const all = state.table?.fields ?? [];
  $("#fields").innerHTML = KIND_GROUP.map(([kind, title]) => {
    const list = all.filter(f => f.kind === kind && (!q || f.label.toLowerCase().includes(q) || f.name.includes(q)));
    if (!list.length) return "";
    return `<div class="fgroup"><h3>${title}</h3>${list
      .map(f => `<button type="button" class="field${used(f.name) ? " used" : ""}" draggable="true" data-field="${esc(f.name)}"
          title="${esc(f.name)}"><span class="kind ${kind}">${KIND_BADGE[kind]}</span><span class="name">${esc(f.label)}</span>${f.unit ? `<span class="unit">${esc(f.unit)}</span>` : ""}</button>`)
      .join("")}</div>`;
  }).join("") || `<p class="muted">${all.length ? "No field matches." : "No data loaded."}</p>`;
}

function chipsFor(shelf) {
  const v = state.view;
  if (shelf === "filters") return Object.entries(v.filters).map(([name, f]) => ({ name, label: `${field(name)?.label ?? name}: ${filterSummary(name, f)}` }));
  if (shelf === "values") return v.values.map(x => ({ name: x.field, label: valueLabel(x) }));
  return v[shelf].map(a => ({ name: a.field, label: axisLabel(a) }));
}

function renderShelves() {
  for (const shelf of SHELVES) {
    const el = document.querySelector(`.shelf[data-shelf="${shelf}"] .chips`);
    el.innerHTML = state.table
      ? chipsFor(shelf).map((c, i) => {
          const kind = field(c.name)?.kind ?? "dimension";
          return `<span class="pchip ${kind}" draggable="true" data-shelf="${shelf}" data-index="${i}">`
            + `<button type="button" class="main" aria-haspopup="menu" title="${esc(c.label)}">${esc(c.label)}<span class="caret">▾</span></button>`
            + `<button type="button" class="x" aria-label="Remove ${esc(c.label)}">×</button></span>`;
        }).join("")
      : "";
  }
}

const additive = () => state.view.values.every(v => v.agg === "sum" || v.agg === "count") && state.view.showAs !== "share_of_column";

function renderToolbar() {
  const d = state.display, v = state.view;
  $("#asTable").setAttribute("aria-pressed", String(d.as === "table"));
  $("#asChart").setAttribute("aria-pressed", String(d.as === "chart"));
  $("#showAs").value = v.showAs;
  $("#subtotals").checked = !!v.subtotals;
  $("#subtotals").disabled = v.rows.length < 2;
  $("#subtotals").parentElement.title = v.rows.length < 2 ? "Subtotals need two or more row fields" : "";
  $("#totals").checked = d.totals;
  $("#heatmap").checked = d.heatmap;
  $("#stacked").checked = d.stacked && additive();
  $("#stacked").disabled = !additive();
  $("#stacked").parentElement.title = additive() ? "" : "Stacking needs values that add up: sums or counts, not averages or column shares";
  for (const el of document.querySelectorAll(".toolbar [data-for]")) el.hidden = el.dataset.for !== d.as;
  const ready = !!state.table;
  for (const id of ["#swap", "#exportCsv", "#copyLink", "#reset"]) $(id).disabled = !ready;
}

function renderResult() {
  hideTip();
  const v = state.view;
  if (!state.table) return;
  if (!v.values.length) {
    state.result = null;
    $("#result").innerHTML = `<div class="empty"><b>Add a value</b>Drag a measure onto Values, or pick a preset above.</div>`;
    renderStatus(null);
    return;
  }
  try {
    state.result = cachedPivot(v);
  } catch (err) {
    fail("This view does not fit the data", err.message);
    return;
  }
  if (state.display.as === "chart") renderChart();
  else renderTable(state.result);
  renderStatus(state.result);
}

function renderStatus(result) {
  const m = state.meta;
  const parts = [];
  if (result) {
    const s = result.stats;
    parts.push(`${s.rowsIn.toLocaleString()} rows read`, `${s.rowsUsed.toLocaleString()} after filters`, `${s.groups.toLocaleString()} groups`, `${s.ms} ms`);
  }
  let html = parts.map(p => `<span>${esc(p)}</span>`).join("");
  if (m?.truncated) html += `<span class="warn">⚠ the server sent the first ${state.table.rows.length.toLocaleString()} of ${m.total.toLocaleString()} rows; totals cover those rows only</span>`;
  $("#statusline").innerHTML = html;
}

// -- the table ------------------------------------------------------------------------------------

const LABEL_CHAR = 7.2;

function renderTable(full) {
  const v = state.view, d = state.display;
  // A very wide result draws its first columns only, so the cell budget below holds for any shape.
  const colLimit = Math.max(1, Math.floor(MAX_TABLE_COLUMNS / Math.max(1, v.values.length)));
  const cut = full.columns.length > colLimit;
  const result = cut
    ? {
        ...full,
        columns: full.columns.slice(0, colLimit),
        rows: full.rows.map(r => ({ ...r, cells: r.cells.slice(0, colLimit) })),
        totals: { ...full.totals, columns: full.totals.columns.slice(0, colLimit) },
      }
    : full;
  const rowFields = v.rows.map(a => ({ a, f: field(a.field) }));
  const nR = Math.max(1, rowFields.length);
  const nV = v.values.length;
  const L = v.columns.length;
  const valueRow = nV > 1 || L === 0;
  const headRows = L + (valueRow ? 1 : 0);
  const fmts = v.values.map(x => valueFormatter({ unit: field(x.field)?.unit, agg: x.agg, showAs: v.showAs }));
  const totals = d.totals && L > 0;

  // label column widths, so sticky offsets line up
  const widths = Array.from({ length: nR }, (_, i) => {
    const head = rowFields[i] ? axisLabel(rowFields[i].a).length : 5;
    let longest = head;
    for (const r of result.rows.slice(0, 2000)) if (r.key[i] != null || i < r.key.length) longest = Math.max(longest, partLabel(r.key[i]).length);
    return Math.round(Math.min(260, Math.max(96, longest * LABEL_CHAR + (i === 0 ? 44 : 30))));
  });
  const lefts = widths.map((_, i) => widths.slice(0, i).reduce((a, b) => a + b, 0));
  const rlStyle = i => `left:${lefts[i]}px;min-width:${widths[i]}px;max-width:${widths[i]}px`;
  const rl = (i, extra = "") => `class="rl ${extra}" style="${rlStyle(i)}"`;
  const top = i => `top:${i * 30}px`;
  const sort = v.sort ?? { by: "label" };
  const dirMark = sort.dir === "desc" ? "▼" : "▲";
  const ariaSort = sort.dir === "desc" ? "descending" : "ascending";

  let h = `<div class="scroller"><table class="pivot"><thead>`;
  for (let row = 0; row < headRows; row++) {
    h += `<tr>`;
    if (row === 0) {
      for (let i = 0; i < nR; i++) {
        const rf = rowFields[i];
        const sorted = rf && sort.by === "label";
        h += `<th class="rl${rf ? " sortable" : ""}" rowspan="${headRows}" style="${top(0)};${rlStyle(i)}"`
          + (rf ? ` data-sort="label" tabindex="0"${sorted && i === 0 ? ` aria-sort="${ariaSort}"` : ""}` : "")
          + `>${rf ? esc(axisLabel(rf.a)) : ""}${sorted && i === 0 ? `<span class="dir">${dirMark}</span>` : ""}</th>`;
      }
    }
    if (row < L) {
      // one header row per column field; equal neighbouring prefixes merge
      const leaf = row === L - 1;
      let j = 0;
      while (j < result.columns.length) {
        const prefix = keyId(result.columns[j].key.slice(0, row + 1));
        let k = j + 1;
        while (k < result.columns.length && keyId(result.columns[k].key.slice(0, row + 1)) === prefix) k++;
        const key = result.columns[j].key;
        const sorted = leaf && sort.by === "column" && keyId(sort.key ?? []) === keyId(key);
        const attrs = leaf ? ` data-sort="column" data-key="${esc(JSON.stringify(key))}" tabindex="0"${sorted ? ` aria-sort="${ariaSort}"` : ""}` : "";
        h += `<th class="colgroup${leaf ? " sortable" : ""}${!valueRow ? " num" : ""}" colspan="${(k - j) * nV}" style="${top(row)}"${attrs}>`
          + `${esc(partLabel(key[row]))}${sorted ? `<span class="dir">${dirMark}</span>` : ""}</th>`;
        j = k;
      }
      if (totals && row === 0) {
        const sorted = sort.by === "value";
        h += `<th class="colgroup sortable tot${!valueRow ? " num" : ""}" rowspan="${L}" colspan="${nV}" style="${top(0)}" data-sort="value" tabindex="0"${sorted ? ` aria-sort="${ariaSort}"` : ""}>Total${sorted ? `<span class="dir">${dirMark}</span>` : ""}</th>`;
      }
    } else {
      // the value row: one label per value under every column (and under Total)
      const cols = L ? result.columns.length : 0;
      for (let j = 0; j < cols; j++) {
        v.values.forEach((x, k) => (h += `<th class="num${k === 0 ? " edge" : ""}" style="${top(row)}">${esc(valueLabel(x))}</th>`));
      }
      if (totals || L === 0) {
        v.values.forEach((x, k) => {
          const sorted = L === 0 && k === 0 && sort.by === "value";
          const attrs = L === 0 && k === 0 ? ` data-sort="value" tabindex="0" class="num sortable${totals ? " tot" : ""}"` : ` class="num${L ? " tot" : ""}${k === 0 ? " edge" : ""}"`;
          h += `<th${attrs} style="${top(row)}"${sorted ? ` aria-sort="${ariaSort}"` : ""}>${esc(valueLabel(x))}${sorted ? `<span class="dir">${dirMark}</span>` : ""}</th>`;
        });
      }
    }
    h += `</tr>`;
  }
  h += `</thead><tbody>`;

  // heatmap scale per value over leaf cells
  const scales = v.values.map((_, k) => {
    if (!d.heatmap) return null;
    let lo = Infinity, hi = -Infinity;
    for (const r of result.rows) {
      if (r.group) continue;
      const xs = L ? r.cells.map(c => c[k]) : [r.total[k]];
      for (const x of xs) if (x != null) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
    }
    return lo <= hi ? { lo, hi } : null;
  });
  const cell = (x, k, extra, shade) => {
    if (x == null) return `<td class="num blank${extra}">–</td>`;
    let style = "";
    if (shade && scales[k]) {
      const { lo, hi } = scales[k];
      const fill = heat(hi === lo ? 1 : (x - lo) / (hi - lo));
      style = ` style="background:${fill};color:${inkOn(fill)}"`;
    }
    return `<td class="num${extra}"${style}>${esc(fmts[k](x))}</td>`;
  };

  const collapsedUnder = key => {
    for (let i = 1; i < key.length; i++) if (state.collapsed.has(JSON.stringify(key.slice(0, i)))) return true;
    return false;
  };
  const visible = result.rows.filter(r => !collapsedUnder(r.key));
  const perRow = (L ? result.columns.length : 0) * nV + nV;
  const limit = Math.min(MAX_TABLE_ROWS, Math.max(10, Math.floor(MAX_TABLE_CELLS / perRow)));
  const drawn = state.showAll ? visible : visible.slice(0, limit);
  let prev = [];
  for (const r of drawn) {
    h += `<tr${r.group ? ` class="group"` : ""}>`;
    for (let i = 0; i < nR; i++) {
      let text = "", extra = "";
      if (!rowFields.length) text = "All rows";
      else if (r.group) {
        if (i === r.depth) {
          const k = JSON.stringify(r.key);
          const closed = state.collapsed.has(k);
          text = `<button type="button" class="caret" data-toggle="${esc(k)}" aria-expanded="${!closed}" aria-label="${closed ? "Expand" : "Collapse"} ${esc(partLabel(r.key[i]))}">${closed ? "▶" : "▼"}</button>${esc(partLabel(r.key[i]))}`;
        } else if (i === r.depth + 1) {
          text = "Subtotal";
          extra = "sub";
        }
      } else if (i < r.key.length) {
        const same = prev.length > i && r.key.slice(0, i + 1).every((p, q) => p === prev[q]);
        text = same ? "" : esc(partLabel(r.key[i]));
      }
      h += `<td ${rl(i, extra)} title="${r.key[i] !== undefined ? esc(partLabel(r.key[i])) : ""}">${text}</td>`;
    }
    if (L) r.cells.forEach(c => c.forEach((x, k) => (h += cell(x, k, k === 0 ? " edge" : "", !r.group))));
    if (totals || L === 0) r.total.forEach((x, k) => (h += cell(x, k, (L ? " tot" : "") + (k === 0 ? " edge" : ""), !r.group && L === 0)));
    h += `</tr>`;
    prev = r.key;
  }
  h += `</tbody>`;
  if (d.totals || !rowFields.length) { // with no row field the totals row is the only row
    h += `<tfoot><tr>`;
    for (let i = 0; i < nR; i++) h += `<td ${rl(i)}>${i === 0 ? "Total" : ""}</td>`;
    if (L) result.totals.columns.forEach(c => c.forEach((x, k) => (h += cell(x, k, k === 0 ? " edge" : "", false))));
    if (totals || L === 0) result.totals.grand.forEach((x, k) => (h += cell(x, k, (L ? " tot" : "") + (k === 0 ? " edge" : ""), false)));
    h += `</tr></tfoot>`;
  }
  h += `</table></div>`;
  if (visible.length > drawn.length) {
    h += `<div class="more">Showing ${drawn.length.toLocaleString()} of ${visible.length.toLocaleString()} rows. <button type="button" id="showAll">Show all</button></div>`;
  }
  if (cut) {
    h += `<div class="more">Showing the first ${colLimit.toLocaleString()} of ${full.columns.length.toLocaleString()} columns; the totals cover all of them, and Export CSV has every column.</div>`;
  }
  if (d.heatmap && scales.some(Boolean)) {
    const k = scales.findIndex(Boolean);
    h += `<div class="heatkey"><span>${esc(valueLabel(v.values[k]))}</span><span>${esc(fmts[k](scales[k].lo))}</span>`
      + `<span class="steps">${HEAT.map(c => `<span style="background:${c}"></span>`).join("")}</span><span>${esc(fmts[k](scales[k].hi))}</span>`
      + (nV > 1 ? `<span>· each value shaded on its own scale</span>` : "") + `</div>`;
  }
  $("#result").innerHTML = h;
}

// -- the chart ------------------------------------------------------------------------------------

function renderChart() {
  const v = state.view;

  const first = v.rows[0] && field(v.rows[0].field);
  const isLine = v.rows.length === 1 && first?.kind === "time" && (v.rows[0].grain ?? "day") !== "weekday";
  let res;
  try {
    res = cachedPivot({ ...v, subtotals: false }, { maxColumns: MAX_SERIES });
  } catch (err) {
    fail("This view does not fit the data", err.message);
    return;
  }
  const hasCols = v.columns.length > 0;
  const folded = res.stats.folded;
  const names = hasCols ? res.columns.map(c => (c.key[0] === OTHER ? `Other (${folded} more)` : c.key.map(partLabel).join(" / "))) : ["value"];
  // colours follow the column's key, not its label: two columns may read alike
  const ids = hasCols ? res.columns.map(c => keyId(c.key)) : ["value"];
  // a new series field (or grain) starts the colours afresh; a filter keeps them
  const seriesKey = keyId(v.columns.map(a => [a.field, a.grain ?? null]));
  if (seriesKey !== state.seriesKey) {
    colors.reset();
    state.seriesKey = seriesKey;
  }
  const byId = colors.assign(ids, folded ? keyId([OTHER]) : null);
  const colorOf = j => byId.get(ids[j]);
  const width = Math.max(320, $("#result").clientWidth - 24);
  const stacked = state.display.stacked && additive() && hasCols && !isLine;
  const allRows = res.rows;
  const rows = isLine ? allRows : allRows.slice(0, MAX_BARS);

  let h = `<div class="chartwrap">`;
  if (hasCols && names.length > 1) { // one series needs no legend: the chart's title names it
    h += `<div class="legend" aria-label="Legend">` + names.map((n, j) => `<span class="item"><span class="${isLine ? "ln" : "sw"}" style="background:${colorOf(j)}"></span>${esc(n)}</span>`).join("") + `</div>`;
  }
  const blocks = [];
  v.values.forEach((x, k) => {
    const spec = { unit: field(x.field)?.unit, agg: x.agg, showAs: v.showAs };
    const format = valueFormatter(spec), compact = compactFormatter(spec);
    const series = names.map((n, j) => ({ name: hasCols ? n : valueLabel(x), color: colorOf(j) }));
    const title = `${valueLabel(x)}${v.rows.length ? ` by ${v.rows.map(axisLabel).join(" and ")}` : ""}`;
    if (isLine) {
      const model = {
        points: rows.map(r => partLabel(r.key[0])),
        series: series.map((s, j) => ({ ...s, values: rows.map(r => (hasCols ? r.cells[j][k] : r.total[k])) })),
        format, compact, width,
      };
      const { svg, geometry } = lineChart(model);
      blocks.push({ title, svg, bind: el => bindLine(el.querySelector("svg"), { ...model, geometry }, $("#tooltip")) });
    } else {
      const categories = rows.length
        ? rows.map(r => ({ label: r.key.map(partLabel).join(" · "), values: series.map((_, j) => (hasCols ? r.cells[j][k] : r.total[k])) }))
        : [{ label: "All rows", values: hasCols ? res.totals.columns.map(c => c[k]) : [res.totals.grand[k]] }];
      const { svg, tips } = barChart({ categories, series, stacked, format, compact, width });
      blocks.push({ title, svg, bind: el => bindBars(el, tips, $("#tooltip")) });
    }
  });
  h += blocks.map((b, i) => `<div class="multiple" data-block="${i}"><h3>${esc(b.title)}</h3>${b.svg}</div>`).join("");
  const notes = [];
  if (!isLine && allRows.length > rows.length) notes.push(`Showing the first ${rows.length} of ${allRows.length} rows in the current sort order; the table view has all of them.`);
  if (folded) notes.push(`The ${folded} smallest series are folded into “Other”, aggregated from their rows.`);
  if (v.values.length > 1) notes.push("Each value has its own chart and scale.");
  if (notes.length) h += `<div class="chartnote">${notes.map(esc).join(" ")}</div>`;
  h += `</div>`;
  $("#result").innerHTML = h;
  blocks.forEach((b, i) => b.bind($(`#result [data-block="${i}"]`)));
}

// -- changing the view ----------------------------------------------------------------------------

function update(change) {
  const rowsBefore = keyId(state.view.rows.map(a => [a.field, a.grain ?? null]));
  change(state.view);
  // collapsed groups belong to the row fields they were collapsed under
  if (keyId(state.view.rows.map(a => [a.field, a.grain ?? null])) !== rowsBefore) state.collapsed.clear();
  if (state.view.rows.length < 2) state.view.subtotals = false;
  render();
}

function addToShelf(shelf, name, index = null) {
  const f = field(name);
  if (!f) return;
  update(v => {
    if (shelf === "values") {
      const item = { field: name, agg: defaultAgg(f) };
      index == null ? v.values.push(item) : v.values.splice(index, 0, item);
    } else if (shelf === "filters") {
      if (!(name in v.filters)) v.filters[name] = { exclude: [] };
    } else {
      const from = ["rows", "columns"].find(s => v[s].some(a => a.field === name));
      let item = { field: name };
      if (from) {
        const i = v[from].findIndex(a => a.field === name);
        item = v[from][i];
        v[from].splice(i, 1);
        if (from === shelf && index != null && index > i) index--;
      } else if (f.kind === "time") {
        item.grain = defaultGrain(name);
      }
      index == null ? v[shelf].push(item) : v[shelf].splice(index, 0, item);
      if (v.sort?.by === "column") v.sort = { by: "label", dir: "asc" };
    }
  });
  if (shelf === "filters") {
    const i = Object.keys(state.view.filters).indexOf(name);
    openChipMenu("filters", i);
  }
}

// Dragging a chip moves it: it leaves the shelf it came from (a filter moved away drops its filter).
function moveChip(from, i, to, index = null) {
  if (from === to) {
    if (from === "filters") return;
    update(v => {
      const [item] = v[from].splice(i, 1);
      const at = index == null ? v[from].length : index > i ? index - 1 : index;
      v[from].splice(at, 0, item);
    });
    return;
  }
  const name = chipsFor(from)[i]?.name;
  if (!name) return;
  if ((from === "rows" || from === "columns") && (to === "rows" || to === "columns")) {
    addToShelf(to, name, index); // the axis item moves with its grain
    return;
  }
  if (from === "filters") delete state.view.filters[name];
  else state.view[from].splice(i, 1);
  if (state.view.sort?.by === "column") state.view.sort = { by: "label", dir: "asc" };
  addToShelf(to, name, index);
}

function removeChip(shelf, i) {
  update(v => {
    if (shelf === "filters") delete v.filters[Object.keys(v.filters)[i]];
    else v[shelf].splice(i, 1);
    if (v.sort?.by === "column") v.sort = { by: "label", dir: "asc" };
  });
}

function applyPreset(i) {
  const p = (PRESETS[presetKey()] ?? [])[i];
  if (!p) return;
  state.view = { ...emptyView(), ...structuredClone(p.view) };
  state.display = { ...DEFAULT_DISPLAY, ...p.display };
  state.collapsed.clear();
  state.showAll = false;
  colors.reset();
  render();
}

// -- popover menus --------------------------------------------------------------------------------

let popAnchor = null;

function openPopover(anchor, html, bind) {
  // a fresh element per menu, so no listener of an earlier menu survives into this one
  const pop = $("#popover").cloneNode(false);
  $("#popover").replaceWith(pop);
  pop.innerHTML = html;
  pop.hidden = false;
  popAnchor = anchor;
  const r = anchor.getBoundingClientRect();
  const w = pop.offsetWidth, hgt = pop.offsetHeight;
  pop.style.left = `${Math.max(8, Math.min(innerWidth - w - 8, r.left))}px`;
  pop.style.top = `${r.bottom + 6 + hgt > innerHeight ? Math.max(8, r.top - hgt - 6) : r.bottom + 6}px`;
  bind?.(pop);
  (pop.querySelector("input[type=search]") ?? pop.querySelector("button, input"))?.focus();
}

function closePopover(refocus = false) {
  const pop = $("#popover");
  if (pop.hidden) return;
  pop.hidden = true;
  pop.innerHTML = "";
  if (refocus && popAnchor?.isConnected) popAnchor.focus();
  popAnchor = null;
}

const item = (label, attrs, checked = null, unit = "") =>
  `<button type="button" class="item" ${attrs}${checked == null ? "" : ` role="menuitemradio" aria-checked="${checked}"`}>`
  + `<span class="tick">${checked ? "✓" : ""}</span>${esc(label)}${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</button>`;

function openChipMenu(shelf, i) {
  const anchor = document.querySelector(`.shelf[data-shelf="${shelf}"] .pchip[data-index="${i}"] .main`);
  if (!anchor) return;
  if (shelf === "filters") return openFilter(anchor, Object.keys(state.view.filters)[i]);
  const v = state.view;
  const list = shelf === "values" ? v.values : v[shelf];
  const it = list[i];
  const f = field(it.field);
  let html = `<div role="menu">`;
  if (shelf === "values") {
    html += `<h4>Aggregation</h4>` + aggsFor(f).map(a => item(AGG_LABEL[a] === "Distinct" ? "Distinct count" : AGG_LABEL[a], `data-agg="${a}"`, a === it.agg)).join("");
  } else if (f?.kind === "time") {
    html += `<h4>Time grain</h4>` + GRAINS.map(g => item(GRAIN_LABEL[g], `data-grain="${g}"`, g === (it.grain ?? "day"))).join("");
  }
  html += `<hr/>`;
  if (i > 0) html += item("Move left", `data-move="-1"`);
  if (i < list.length - 1) html += item("Move right", `data-move="1"`);
  if (shelf === "rows") html += item("Move to Columns", `data-to="columns"`);
  if (shelf === "columns") html += item("Move to Rows", `data-to="rows"`);
  html += item("Remove", `data-remove`) + `</div>`;
  openPopover(anchor, html, pop => {
    pop.addEventListener("click", e => {
      const b = e.target.closest("button.item");
      if (!b) return;
      closePopover();
      if (b.dataset.agg) update(v => (v.values[i].agg = b.dataset.agg));
      else if (b.dataset.grain) update(v => (v[shelf][i].grain = b.dataset.grain));
      else if (b.dataset.move) moveChip(shelf, i, shelf, i + (+b.dataset.move > 0 ? 2 : -1));
      else if (b.dataset.to) moveChip(shelf, i, b.dataset.to);
      else if ("remove" in b.dataset) removeChip(shelf, i);
      document.querySelector(`.shelf[data-shelf="${shelf}"] .add`)?.focus();
    });
  });
}

function openFilter(anchor, name) {
  const all = distinctValues(state.table, name);
  const f = state.view.filters[name] ?? { exclude: [] };
  const kept = new Set(f.include ?? all.map(x => x.value).filter(x => !(f.exclude ?? []).includes(x)));
  const label = field(name)?.label ?? name;
  const draw = pop => {
    const q = pop.querySelector("input[type=search]").value.trim().toLowerCase();
    const shown = all.filter(x => !q || partLabel(x.value).toLowerCase().includes(q));
    pop.querySelector(".vals").innerHTML = shown.slice(0, 500).map(x => {
      const i = all.indexOf(x);
      return `<label><input type="checkbox" data-i="${i}" ${kept.has(x.value) ? "checked" : ""}/>${esc(partLabel(x.value))}<span class="n">${x.count.toLocaleString()}</span></label>`;
    }).join("") + (shown.length > 500 ? `<div class="muted" style="padding:4px 6px">${shown.length - 500} more; search to narrow</div>` : "");
    pop.querySelector(".kept").textContent = `${kept.size.toLocaleString()} of ${all.length.toLocaleString()} kept`;
  };
  const commit = (redraw = false) => {
    const keep = all.filter(x => kept.has(x.value)).map(x => x.value);
    const drop = all.filter(x => !kept.has(x.value)).map(x => x.value);
    update(v => (v.filters[name] = keep.length < drop.length ? { include: keep } : { exclude: drop }));
    const pop = $("#popover");
    if (pop.hidden) return;
    if (redraw) draw(pop); // All or None changed many boxes
    else pop.querySelector(".kept").textContent = `${kept.size.toLocaleString()} of ${all.length.toLocaleString()} kept`;
  };
  const html = `<h4>Filter · ${esc(label)}</h4><input type="search" placeholder="Search values" aria-label="Search values of ${esc(label)}"/>`
    + `<div class="row"><button type="button" data-all>All</button><button type="button" data-none>None</button><span class="muted kept"></span></div>`
    + `<div class="vals" role="group" aria-label="Values of ${esc(label)}"></div>`
    + `<div class="row"><button type="button" data-remove>Remove filter</button></div>`;
  openPopover(anchor, html, pop => {
    draw(pop);
    pop.querySelector("input[type=search]").addEventListener("input", () => draw(pop));
    pop.addEventListener("change", e => {
      const i = e.target.dataset.i;
      if (i == null) return;
      e.target.checked ? kept.add(all[+i].value) : kept.delete(all[+i].value);
      commit();
    });
    pop.addEventListener("click", e => {
      const q = pop.querySelector("input[type=search]").value.trim().toLowerCase();
      const shown = all.filter(x => !q || partLabel(x.value).toLowerCase().includes(q));
      if (e.target.closest("[data-all]")) { shown.forEach(x => kept.add(x.value)); commit(true); }
      else if (e.target.closest("[data-none]")) { shown.forEach(x => kept.delete(x.value)); commit(true); }
      else if (e.target.closest("[data-remove]")) {
        closePopover();
        update(v => delete v.filters[name]);
      }
    });
  });
}

function openAddMenu(shelf, anchor) {
  const all = state.table?.fields ?? [];
  const eligible = all.filter(f => (shelf === "filters" ? !(f.name in state.view.filters) : shelf === "values" ? true : !state.view[shelf].some(a => a.field === f.name)));
  const draw = pop => {
    const q = pop.querySelector("input[type=search]").value.trim().toLowerCase();
    const list = eligible.filter(f => !q || f.label.toLowerCase().includes(q) || f.name.includes(q));
    pop.querySelector(".list").innerHTML = list.map(f => item(f.label, `data-add="${esc(f.name)}"`, null, KIND_BADGE[f.kind])).join("") || `<div class="muted" style="padding:6px 10px">No field left to add.</div>`;
  };
  openPopover(anchor, `<h4>Add to ${shelf}</h4><input type="search" placeholder="Search fields" aria-label="Search fields"/><div class="list" role="menu"></div>`, pop => {
    draw(pop);
    pop.querySelector("input[type=search]").addEventListener("input", () => draw(pop));
    pop.querySelector("input[type=search]").addEventListener("keydown", e => {
      if (e.key === "Enter") pop.querySelector("[data-add]")?.click();
    });
    pop.addEventListener("click", e => {
      const b = e.target.closest("[data-add]");
      if (!b) return;
      closePopover();
      addToShelf(shelf, b.dataset.add);
      if (shelf !== "filters") anchor.focus();
    });
  });
}

// -- drag and drop --------------------------------------------------------------------------------

const DRAG = "application/x-sdf-pivot";
let dragging = null; // {field} from the field list, or {shelf, index} from a chip

function dropIndex(shelfEl, x, y) {
  const chips = [...shelfEl.querySelectorAll(".pchip")];
  for (let i = 0; i < chips.length; i++) {
    const r = chips[i].getBoundingClientRect();
    if (y < r.top) return i;
    if (y <= r.bottom && x < r.left + r.width / 2) return i;
  }
  return chips.length;
}

function showInsert(shelfEl, index) {
  shelfEl.querySelector(".insert")?.remove();
  const marker = document.createElement("span");
  marker.className = "insert";
  const chips = shelfEl.querySelectorAll(".pchip");
  const box = shelfEl.querySelector(".chips");
  index < chips.length ? box.insertBefore(marker, chips[index]) : box.append(marker);
}

function bindDragAndDrop() {
  document.addEventListener("dragstart", e => {
    const f = e.target.closest?.(".field");
    const c = e.target.closest?.(".pchip");
    if (f) dragging = { field: f.dataset.field };
    else if (c) { dragging = { shelf: c.dataset.shelf, index: +c.dataset.index }; c.classList.add("dragging"); }
    else return;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData(DRAG, JSON.stringify(dragging));
    e.dataTransfer.setData("text/plain", dragging.field ?? "");
  });
  document.addEventListener("dragend", () => {
    dragging = null;
    document.querySelectorAll(".shelf.over").forEach(s => s.classList.remove("over"));
    document.querySelectorAll(".insert, .pchip.dragging").forEach(el => (el.classList.contains("insert") ? el.remove() : el.classList.remove("dragging")));
  });
  for (const shelfEl of document.querySelectorAll(".shelf")) {
    shelfEl.addEventListener("dragover", e => {
      if (!dragging || !state.table) return;
      e.preventDefault();
      shelfEl.classList.add("over");
      if (shelfEl.dataset.shelf !== "filters") showInsert(shelfEl, dropIndex(shelfEl, e.clientX, e.clientY));
    });
    shelfEl.addEventListener("dragleave", e => {
      if (shelfEl.contains(e.relatedTarget)) return;
      shelfEl.classList.remove("over");
      shelfEl.querySelector(".insert")?.remove();
    });
    shelfEl.addEventListener("drop", e => {
      e.preventDefault();
      shelfEl.querySelector(".insert")?.remove();
      const index = dropIndex(shelfEl, e.clientX, e.clientY);
      shelfEl.classList.remove("over");
      const d = dragging;
      dragging = null;
      if (!d) return;
      const to = shelfEl.dataset.shelf;
      if (d.field) addToShelf(to, d.field, to === "filters" ? null : index);
      else moveChip(d.shelf, d.index, to, to === "filters" ? null : index);
    });
  }
}

// -- the experiment request -----------------------------------------------------------------------

async function showExperimentForm() {
  $("#expForm").hidden = false;
  if (!state.catalog) {
    try {
      state.catalog = await api("/experiments/catalog");
    } catch (err) {
      $("#expNote").textContent = `Could not load the experiment catalogue: ${err.detail ?? err.message}`;
      return;
    }
    // the user may have picked a dataset while the catalogue loaded: then the form stays away
    if ($("#source").value !== "experiment") {
      $("#expForm").hidden = true;
      return;
    }
  }
  const cat = state.catalog;
  const body = state.source?.experiment ?? {
    interventions: cat.interventions.slice(0, 2),
    policies: cat.policies.slice(0, 2).map(c => ({ kind: c.kind })), // each parameter starts at the catalogue's default
    outcomes: [...cat.outcomes],
  };
  const checks = (list, chosen, name) => list.map(x => `<label><input type="checkbox" name="${name}" value="${esc(x)}" ${chosen.includes(x) ? "checked" : ""}/>${esc(x.replaceAll("_", " "))}</label>`).join("");
  $("#expInterventions").innerHTML = checks(cat.interventions, body.interventions ?? [], "intervention");
  $("#expOutcomes").innerHTML = checks(cat.outcomes, body.outcomes ?? [], "outcome");
  $("#expPolicies").innerHTML = "";
  for (const p of body.policies ?? []) addPolicyRow(p);
  limitChecks();
  renderSourceInfo();
}

function addPolicyRow(p = {}) {
  const cat = state.catalog;
  const kind = cat.policies.some(c => c.kind === p.kind) ? p.kind : cat.policies[0].kind;
  const row = document.createElement("div");
  row.className = "policy";
  const drawParams = k => {
    const spec = cat.policies.find(c => c.kind === k);
    row.querySelector(".params").innerHTML = spec.params.map(pr => {
      const step = pr.type === "int" ? 1 : 0.005;
      const val = p.kind === k && p[pr.name] != null ? p[pr.name] : pr.default;
      const bounds = `${pr.min != null ? ` min="${esc(pr.min)}"` : ""}${pr.max != null ? ` max="${esc(pr.max)}"` : ""}`;
      const hint = pr.min != null && pr.max != null ? `${pr.exclusive ? "between" : "from"} ${pr.min} ${pr.exclusive ? "and" : "to"} ${pr.max}` : "";
      return `<div class="ctrl"><label>${esc(pr.name.replaceAll("_", " "))}</label>`
        + `<input type="number" data-param="${esc(pr.name)}" data-type="${esc(pr.type)}" value="${esc(val)}" step="${step}"${bounds} title="${esc(hint)}"/></div>`;
    }).join("");
  };
  row.innerHTML = `<div class="ctrl"><label>Policy</label><select class="kind-select">${cat.policies.map(c => `<option ${c.kind === kind ? "selected" : ""}>${esc(c.kind)}</option>`).join("")}</select></div>`
    + `<span class="params" style="display:contents"></span><button type="button" class="remove-policy" aria-label="Remove this policy">×</button>`;
  $("#expPolicies").append(row);
  drawParams(kind);
  row.querySelector(".kind-select").addEventListener("change", e => drawParams(e.target.value));
  row.querySelector(".remove-policy").addEventListener("click", () => { row.remove(); limitChecks(); });
  limitChecks();
}

function limitChecks() {
  const max = state.catalog?.max_per_list ?? 6;
  for (const name of ["intervention", "outcome"]) {
    const boxes = [...document.querySelectorAll(`#expForm input[name=${name}]`)];
    const n = boxes.filter(b => b.checked).length;
    for (const b of boxes) b.disabled = !b.checked && n >= max;
  }
  const rows = document.querySelectorAll("#expPolicies .policy");
  $("#expAddPolicy").disabled = rows.length >= max;
  rows.forEach(r => (r.querySelector(".remove-policy").disabled = rows.length <= 1));
  $("#expNote").textContent = `At most ${max} of each.`;
}

// Why the form cannot be sent, or null: the checks the endpoint makes, from the catalogue's bounds.
function experimentFormError() {
  const body = readExperimentForm();
  if (!body.interventions.length) return "Choose at least one intervention.";
  if (!body.outcomes.length) return "Choose at least one outcome.";
  for (const [n, p] of body.policies.entries()) {
    const spec = state.catalog.policies.find(c => c.kind === p.kind);
    for (const pr of spec.params) {
      const v = p[pr.name];
      const where = `Policy ${n + 1}, ${pr.name.replaceAll("_", " ")}`;
      if (!Number.isFinite(v)) return `${where}: enter a number.`;
      if (pr.type === "int" && !Number.isInteger(v)) return `${where}: enter a whole number.`;
      const below = pr.min != null && (pr.exclusive ? v <= pr.min : v < pr.min);
      const above = pr.max != null && (pr.exclusive ? v >= pr.max : v > pr.max);
      if (below || above) {
        return pr.exclusive ? `${where} must be between ${pr.min} and ${pr.max}, both excluded.` : `${where} must be from ${pr.min} to ${pr.max}.`;
      }
    }
  }
  return null;
}

function readExperimentForm() {
  const picked = name => [...document.querySelectorAll(`#expForm input[name=${name}]:checked`)].map(b => b.value);
  const policies = [...document.querySelectorAll("#expPolicies .policy")].map(row => {
    const p = { kind: row.querySelector(".kind-select").value };
    for (const input of row.querySelectorAll("[data-param]")) {
      p[input.dataset.param] = input.value.trim() === "" ? NaN : Number(input.value);
    }
    return p;
  });
  return { interventions: picked("intervention"), policies, outcomes: picked("outcome") };
}

// -- source picker --------------------------------------------------------------------------------

function fillSourceSelect(unavailable) {
  const opts = state.datasets.map(d => `<option value="dataset:${esc(d.name)}">${esc(d.label)}</option>`).join("");
  $("#source").innerHTML = `<optgroup label="Datasets">${opts}</optgroup><optgroup label="Experiments"><option value="experiment">Policy experiment (what-if)</option></optgroup>`;
  const broken = Object.keys(unavailable ?? {});
  if (broken.length) $("#source").title = `Not available: ${broken.join(", ")}`;
}

function syncSourceSelect() {
  const s = state.source;
  const value = s?.dataset != null ? `dataset:${s.dataset}` : s?.experiment ? "experiment" : $("#source").value;
  if ([...$("#source").options].some(o => o.value === value)) $("#source").value = value;
  if (value === "experiment") showExperimentForm();
  else $("#expForm").hidden = true;
}

// -- toolbar actions ------------------------------------------------------------------------------

function toast(text) {
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  el.textContent = text;
  document.body.append(el);
  setTimeout(() => el.remove(), 1800);
}

function exportCsv() {
  if (!state.result) return toast("Nothing to export yet");
  const csv = toCsv(state.result, { rowFields: state.view.rows.map(axisLabel), values: state.view.values.map(valueLabel) });
  const name = (state.source?.dataset ?? "experiment").replace(/[^a-z0-9-]/gi, "-");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `${name}-pivot.csv`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function copyLink() {
  writeLink();
  try {
    await navigator.clipboard.writeText(location.href);
    toast("Link copied: it reopens this view");
  } catch {
    toast("Copy the address bar to share this view");
  }
}

// -- wiring ---------------------------------------------------------------------------------------

function bindPage() {
  $("#source").addEventListener("change", e => {
    const v = e.target.value;
    if (v === "experiment") {
      hideTip();
      state.seq++; // a dataset still loading must not replace the form
      setBusy(false); // and its request no longer counts as work in progress
      state.table = null;
      state.meta = null;
      state.source = null;
      state.result = null;
      $("#result").innerHTML = `<div class="empty"><b>Run an experiment</b>Choose interventions, policies and outcomes above, then press Run experiment.</div>`;
      $("#statusline").textContent = "";
      renderPresets(); renderFields(); renderShelves(); renderToolbar();
      showExperimentForm();
      history.replaceState(null, "", location.pathname + location.search);
    } else {
      loadSource({ dataset: v.slice("dataset:".length) });
    }
  });
  $("#expAddPolicy").addEventListener("click", () => addPolicyRow({}));
  $("#expForm").addEventListener("change", e => { if (e.target.name) limitChecks(); });
  $("#expRun").addEventListener("click", () => {
    const problem = experimentFormError();
    if (problem) {
      $("#expNote").textContent = problem;
      $("#expNote").classList.add("bad");
      return;
    }
    $("#expNote").classList.remove("bad");
    limitChecks();
    loadSource({ experiment: readExperimentForm() });
  });
  $("#presets").addEventListener("click", e => {
    const b = e.target.closest("[data-preset]");
    if (b) applyPreset(+b.dataset.preset);
  });
  $("#fieldSearch").addEventListener("input", renderFields);
  $("#fields").addEventListener("click", e => {
    const b = e.target.closest(".field");
    if (!b) return;
    const f = field(b.dataset.field);
    const shelf = f.kind === "measure" ? "values" : f.kind === "time" && state.view.rows.length ? "columns" : "rows";
    if (shelf !== "values" && onAxis(f.name)) return toast(`${f.label} is already on Rows or Columns`);
    addToShelf(shelf, f.name);
  });
  document.querySelector(".shelves").addEventListener("click", e => {
    const add = e.target.closest(".add");
    if (add) return state.table && openAddMenu(add.closest(".shelf").dataset.shelf, add);
    const chip = e.target.closest(".pchip");
    if (!chip) return;
    if (e.target.closest(".x")) removeChip(chip.dataset.shelf, +chip.dataset.index);
    else if (e.target.closest(".main")) openChipMenu(chip.dataset.shelf, +chip.dataset.index);
  });
  $("#asTable").addEventListener("click", () => { state.display.as = "table"; render(); });
  $("#asChart").addEventListener("click", () => { state.display.as = "chart"; render(); });
  $("#showAs").addEventListener("change", e => update(v => (v.showAs = e.target.value)));
  $("#subtotals").addEventListener("change", e => update(v => (v.subtotals = e.target.checked)));
  $("#totals").addEventListener("change", e => { state.display.totals = e.target.checked; render(); });
  $("#heatmap").addEventListener("change", e => { state.display.heatmap = e.target.checked; render(); });
  $("#stacked").addEventListener("change", e => { state.display.stacked = e.target.checked; render(); });
  $("#swap").addEventListener("click", () => update(v => {
    [v.rows, v.columns] = [v.columns, v.rows];
    if (v.sort?.by === "column") v.sort = { by: "label", dir: "asc" };
    if (v.showAs === "share_of_row") v.showAs = "share_of_column";
    else if (v.showAs === "share_of_column") v.showAs = "share_of_row";
  }));
  $("#exportCsv").addEventListener("click", exportCsv);
  $("#copyLink").addEventListener("click", copyLink);
  $("#reset").addEventListener("click", () => {
    const p = (PRESETS[presetKey()] ?? [])[0];
    state.view = { ...emptyView(), ...structuredClone(p?.view ?? fallbackView()) };
    state.display = { ...DEFAULT_DISPLAY, ...p?.display };
    state.collapsed.clear();
    state.showAll = false;
    render();
  });
  $("#result").addEventListener("click", e => {
    const t = e.target.closest("[data-toggle]");
    if (t) {
      const k = t.dataset.toggle;
      state.collapsed.has(k) ? state.collapsed.delete(k) : state.collapsed.add(k);
      renderTable(state.result);
      document.querySelector(`#result [data-toggle="${CSS.escape(k)}"]`)?.focus();
      return;
    }
    if (e.target.closest("#showAll")) { state.showAll = true; renderTable(state.result); return; }
    const th = e.target.closest("th[data-sort]");
    if (th) sortBy(th);
  });
  $("#result").addEventListener("keydown", e => {
    const th = e.target.closest?.("th[data-sort]");
    if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); sortBy(th); }
  });
  document.addEventListener("pointerdown", e => {
    if (!$("#popover").hidden && !e.target.closest("#popover") && !e.target.closest(".pchip .main, .shelf .add")) closePopover();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closePopover(true);
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && e.target.closest?.("#popover")) {
      const items = [...$("#popover").querySelectorAll("button.item, input")];
      const i = items.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
    }
  });
  window.addEventListener("hashchange", () => {
    if (location.hash && location.hash !== state.written) openLink();
  });
  let frame = 0;
  new ResizeObserver(() => {
    if (state.display.as !== "chart" || !state.result) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(renderChart);
  }).observe($("#result"));
  bindDragAndDrop();
}

function sortBy(th) {
  const by = th.dataset.sort;
  const key = by === "column" ? JSON.parse(th.dataset.key) : undefined;
  const cur = state.view.sort ?? {};
  const same = cur.by === by && JSON.stringify(cur.key ?? null) === JSON.stringify(key ?? null);
  const dir = same ? (cur.dir === "desc" ? "asc" : "desc") : by === "label" ? "asc" : "desc";
  update(v => (v.sort = key ? { by, key, dir } : { by, dir }));
  const again = [...document.querySelectorAll("#result th[data-sort]")].find(
    t => t.dataset.sort === by && (t.dataset.key ?? null) === (th.dataset.key ?? null),
  );
  again?.focus();
}

async function init() {
  bindPage();
  renderToolbar();
  let list;
  try {
    list = await api("/datasets");
  } catch (err) {
    fail("Could not list the datasets", err.detail ?? err.message);
    return;
  }
  state.datasets = list.datasets;
  fillSourceSelect(list.unavailable);
  if (openLink()) return;
  const first = state.datasets.find(d => d.name === "order-lines") ?? state.datasets[0];
  if (first) loadSource({ dataset: first.name });
  else fail("No dataset is available", "The server's catalogue is empty.");
}

init();
