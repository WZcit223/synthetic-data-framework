// The Explore page's view, as data: presets, labels, the link format, and every
// change a user makes to the shelves. Pure (no DOM), so each is tested; the
// numbers come from lib/pivot.js, used as it is.
import { AGGREGATIONS, distinctValues, keptCount, keyId, partLabel } from "../../lib/pivot.js";

export const AGG_LABEL = { sum: "Sum", count: "Count", count_distinct: "Distinct", mean: "Mean", median: "Median", min: "Min", max: "Max" };
export const GRAIN_LABEL = { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year", weekday: "Weekday" };
export const KIND_BADGE = { dimension: "Abc", time: "Date", measure: "123" };
export const KIND_GROUP = [["dimension", "Dimensions"], ["time", "Time"], ["measure", "Measures"]];
export const SHELVES = ["rows", "columns", "values", "filters"];
export const DEFAULT_DISPLAY = { as: "table", heatmap: false, totals: true, stacked: false };

export function emptyView() {
  return { rows: [], columns: [], values: [], filters: {}, showAs: "value", sort: { by: "label", dir: "asc" }, subtotals: false };
}

// One-click starting views. A preset is a saved view: it goes through the same code as one a user builds.
export const PRESETS = {
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
  "synthesis-series": [
    { label: "Real and synthetic side by side", view: { rows: [{ field: "origin" }], values: [{ field: "value", agg: "mean" }, { field: "value", agg: "median" }, { field: "value", agg: "max" }, { field: "value", agg: "sum" }] } },
  ],
  "synthesis-table": [
    { label: "Real and synthetic side by side", view: { rows: [{ field: "origin" }], values: [{ field: "qty", agg: "mean" }, { field: "price", agg: "mean" }, { field: "hour", agg: "mean" }, { field: "weekday", agg: "mean" }] } },
    { label: "Spread of price and quantity", view: { rows: [{ field: "origin" }], values: [{ field: "price", agg: "min" }, { field: "price", agg: "median" }, { field: "price", agg: "max" }, { field: "qty", agg: "median" }, { field: "qty", agg: "max" }] } },
  ],
  "effects-effects": [
    { label: "Effect and interval by metric, intervention and policy", view: { rows: [{ field: "metric" }, { field: "intervention" }, { field: "policy" }], values: [{ field: "effect", agg: "mean" }, { field: "ci_low", agg: "mean" }, { field: "ci_high", agg: "mean" }, { field: "relative_effect", agg: "mean" }] } },
  ],
  "effects-replicates": [
    { label: "Paired difference per replicate", view: { rows: [{ field: "metric" }, { field: "intervention" }, { field: "policy" }], columns: [{ field: "replicate" }], values: [{ field: "difference", agg: "mean" }], filters: { intervention: { exclude: ["baseline"] } } } },
    { label: "Each arm's value per replicate", view: { rows: [{ field: "metric" }, { field: "intervention" }, { field: "policy" }], columns: [{ field: "replicate" }], values: [{ field: "value", agg: "mean" }] } },
  ],
  "estimates-scores": [
    { label: "Estimate, interval and bias by estimator", view: { rows: [{ field: "estimator" }], values: [{ field: "effect", agg: "mean" }, { field: "ci_low", agg: "mean" }, { field: "ci_high", agg: "mean" }, { field: "bias", agg: "mean" }, { field: "seconds", agg: "sum" }] } },
  ],
  "estimates-data": [
    { label: "Weekly units by promotion and ABC class", view: { rows: [{ field: "abc_class" }], columns: [{ field: "promoted" }], values: [{ field: "weekly_units", agg: "mean" }] } },
    { label: "Who gets promoted: promoted share by ABC class", view: { rows: [{ field: "abc_class" }], values: [{ field: "promoted", agg: "mean" }, { field: "log_demand", agg: "mean" }, { field: "sku_id", agg: "count" }] } },
  ],
  "forecasts-scores": [
    { label: "Error, interval and run time by forecaster", view: { rows: [{ field: "forecaster" }], values: [{ field: "wape", agg: "mean" }, { field: "relative_wape", agg: "mean" }, { field: "pinball", agg: "mean" }, { field: "coverage_closed", agg: "mean" }, { field: "seconds", agg: "sum" }] } },
  ],
  "forecasts-by_horizon": [
    { label: "Mean error over the days ahead by forecaster", view: { rows: [{ field: "forecaster" }], values: [{ field: "wape", agg: "mean" }, { field: "mae", agg: "mean" }, { field: "coverage_closed", agg: "mean" }, { field: "width", agg: "mean" }] } },
  ],
  "forecasts-forecasts": [
    { label: "Forecast demand by day and forecaster", view: { rows: [{ field: "date", grain: "day" }], columns: [{ field: "forecaster" }], values: [{ field: "mean", agg: "sum" }] }, display: { as: "chart" } },
    { label: "Forecast and actual by SKU", view: { rows: [{ field: "sku_id" }], columns: [{ field: "forecaster" }], values: [{ field: "mean", agg: "sum" }, { field: "actual", agg: "sum" }], sort: { by: "value", dir: "desc" } } },
  ],
  experiment: [
    { label: "Outcomes by metric, intervention and policy", view: { rows: [{ field: "metric" }, { field: "intervention" }], columns: [{ field: "policy" }], values: [{ field: "value", agg: "mean" }] } },
  ],
};

// The presets offered for a source ({dataset} | {experiment} | {synthesis} | {effects} | {estimates} | {forecasts}).
export function presetKey(source, meta) {
  if (source?.dataset != null) return source.dataset;
  if (source?.experiment) return "experiment";
  if (source?.synthesis) return `synthesis-${meta?.kind}`;
  if (source?.effects) return `effects-${source.effects.table}`;
  if (source?.estimates) return `estimates-${source.estimates.table}`;
  if (source?.forecasts) return `forecasts-${source.forecasts.table}`;
  return null;
}

// The presets of a source that fit its table: a preset naming a field the table lacks is left out
// (a synthesizer run on a user's source has its own columns, not the retail table's).
export function presetsFor(source, meta, table) {
  const names = new Set(table.fields.map(f => f.name));
  const fieldsOf = p => {
    const v = p.view;
    const shelved = [...(v.rows ?? []), ...(v.columns ?? []), ...(v.values ?? [])].map(a => a.field);
    return [...shelved, ...Object.keys(v.filters ?? {})];
  };
  return (PRESETS[presetKey(source, meta)] ?? []).filter(p => fieldsOf(p).every(f => names.has(f)));
}

// Whether a view and display are this preset, unchanged.
export function isPreset(p, view, display) {
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  return same(view, { ...emptyView(), ...p.view }) && same(display, { ...DEFAULT_DISPLAY, ...p.display });
}

export const defaultAgg = f => (f.kind === "measure" ? f.aggregate ?? "sum" : "count");
export const aggsFor = f => (f.kind === "measure" ? AGGREGATIONS : ["count", "count_distinct"]);

// A view for a table no preset knows: its first dimension by its first measure.
export function fallbackView(table) {
  const fs = table.fields;
  const dim = fs.find(f => f.kind === "dimension");
  const m = fs.find(f => f.kind === "measure");
  return {
    rows: dim ? [{ field: dim.name }] : [],
    values: m ? [{ field: m.name, agg: defaultAgg(m) }] : fs.length ? [{ field: fs[0].name, agg: "count" }] : [],
  };
}

export function describeSource(source) {
  if (source?.dataset != null) return `dataset "${source.dataset}"`;
  if (source?.experiment) return "the experiment";
  if (source?.synthesis) return "the synthesizer run";
  if (source?.effects) return "the effect study";
  if (source?.estimates) return "the estimation";
  if (source?.forecasts) return "the forecast backtest";
  return "this source";
}

// -- labels -----------------------------------------------------------------------------------

const fieldOf = (table, name) => table?.fields.find(f => f.name === name);

export function axisLabel(table, a) {
  const f = fieldOf(table, a.field);
  return f?.kind === "time" ? `${f.label} · ${GRAIN_LABEL[a.grain ?? "day"]}` : f?.label ?? a.field;
}

export function valueLabel(table, v) {
  const f = fieldOf(table, v.field);
  if (v.agg === "count") return "Count of rows";
  if (v.agg === "count_distinct") return `Distinct ${f?.label ?? v.field}`;
  return `${AGG_LABEL[v.agg]} of ${f?.label ?? v.field}`;
}

export function filterSummary(table, name, f) {
  const values = distinctValues(table, name);
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

// The chips a shelf shows: the field each names and its label.
export function chipsFor(table, view, shelf) {
  if (shelf === "filters") return Object.entries(view.filters).map(([name, f]) => ({ name, label: `${fieldOf(table, name)?.label ?? name}: ${filterSummary(table, name, f)}` }));
  if (shelf === "values") return view.values.map(x => ({ name: x.field, label: valueLabel(table, x) }));
  return view[shelf].map(a => ({ name: a.field, label: axisLabel(table, a) }));
}

// A time field's first grain: days for a month of data, weeks up to about half a year, then months.
export function defaultGrain(table, name) {
  const days = distinctValues(table, name).length;
  return days <= 31 ? "day" : days <= 200 ? "week" : "month";
}

export const onAxis = (view, name) => [...view.rows, ...view.columns].some(a => a.field === name);
export const used = (view, name) => onAxis(view, name) || view.values.some(v => v.field === name) || name in view.filters;

// Whether the values add up, so a chart may stack them: sums or counts, and no column shares.
export const additive = view => view.values.every(v => v.agg === "sum" || v.agg === "count") && view.showAs !== "share_of_column";

// -- the link ---------------------------------------------------------------------------------

/** The link in an address: `{source, view, display}`, `{error}`, or null when the address holds none. */
export function readLink(hash) {
  const m = hash.match(/^#view=(.+)$/);
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

export const linkHash = (source, view, display) => "#view=" + encodeURIComponent(JSON.stringify({ source, view, display }));

// Why a link's display settings cannot be used, or null.
export function displayError(display) {
  if (display == null) return null;
  if (typeof display !== "object" || Array.isArray(display)) return "the display must be an object";
  for (const [k, v] of Object.entries(display)) {
    if (k === "as") { if (v !== "table" && v !== "chart") return "display.as must be table or chart"; }
    else if (["heatmap", "totals", "stacked"].includes(k)) { if (typeof v !== "boolean") return `display.${k} must be true or false`; }
    else return `the display has an unknown key ${JSON.stringify(k)}`;
  }
  return null;
}

// -- changing the view ------------------------------------------------------------------------
// Each change takes the view and returns a new one; the page keeps the rest (collapsed groups
// belong to the row fields they were collapsed under: rowsKey tells when they changed).

export const rowsKey = view => keyId(view.rows.map(a => [a.field, a.grain ?? null]));

function tidy(view) {
  if (view.rows.length < 2) view.subtotals = false;
  return view;
}

const unsortColumn = v => { if (v.sort?.by === "column") v.sort = { by: "label", dir: "asc" }; };

/** Put field `name` on `shelf` (at `index`, else last); an axis field on the other axis moves with its grain. */
export function addToShelf(view, table, shelf, name, index = null) {
  const f = fieldOf(table, name);
  if (!f) return view;
  const v = structuredClone(view);
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
      item.grain = defaultGrain(table, name);
    }
    index == null ? v[shelf].push(item) : v[shelf].splice(index, 0, item);
    unsortColumn(v);
  }
  return tidy(v);
}

/** Move the `i`-th chip of shelf `from` to shelf `to` (at `index`); a filter moved away drops its filter. */
export function moveChip(view, table, from, i, to, index = null) {
  if (from === to) {
    if (from === "filters") return view;
    const v = structuredClone(view);
    const [item] = v[from].splice(i, 1);
    const at = index == null ? v[from].length : index > i ? index - 1 : index;
    v[from].splice(at, 0, item);
    return tidy(v);
  }
  const name = chipsFor(table, view, from)[i]?.name;
  if (!name) return view;
  if ((from === "rows" || from === "columns") && (to === "rows" || to === "columns")) return addToShelf(view, table, to, name, index);
  const v = structuredClone(view);
  if (from === "filters") delete v.filters[name];
  else v[from].splice(i, 1);
  unsortColumn(v);
  return addToShelf(tidy(v), table, to, name, index);
}

export function removeChip(view, shelf, i) {
  const v = structuredClone(view);
  if (shelf === "filters") delete v.filters[Object.keys(v.filters)[i]];
  else v[shelf].splice(i, 1);
  unsortColumn(v);
  return tidy(v);
}

export function swapAxes(view) {
  const v = structuredClone(view);
  [v.rows, v.columns] = [v.columns, v.rows];
  unsortColumn(v);
  if (v.showAs === "share_of_row") v.showAs = "share_of_column";
  else if (v.showAs === "share_of_column") v.showAs = "share_of_row";
  return tidy(v);
}

/** The sort a click on a header asks for: the same header again flips its direction. */
export function nextSort(current, by, key) {
  const cur = current ?? {};
  const same = cur.by === by && JSON.stringify(cur.key ?? null) === JSON.stringify(key ?? null);
  const dir = same ? (cur.dir === "desc" ? "asc" : "desc") : by === "label" ? "asc" : "desc";
  return key ? { by, key, dir } : { by, dir };
}
