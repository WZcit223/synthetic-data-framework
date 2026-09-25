// The Explore page's chart view, as data: from a pivot result to one chart per value
// (small multiples), each a line over a time axis or bars, grouped or stacked. Pure
// (no DOM, no Chart.js), so the limits and the folded "Other" series are tested.
import { compactFormatter, valueFormatter } from "../../lib/format.js";
import { OTHER, keyId, partLabel } from "../../lib/pivot.js";
import { additive, axisLabel, valueLabel } from "./view.js";

export const MAX_BARS = 50; // categories a bar chart draws; the table view has the rest
export const MAX_SERIES = 8; // series a chart colours; the rest fold into "Other"

/** The view the chart pivots: no subtotals, at most MAX_SERIES columns (see pivot's maxColumns). */
export const chartPivot = view => [{ ...view, subtotals: false }, { maxColumns: MAX_SERIES }];

/** Whether the chart is a line: one time field on rows, at a grain that runs in order (not weekdays). */
export function isLine(table, view) {
  const first = view.rows[0] && table.fields.find(f => f.name === view.rows[0].field);
  return view.rows.length === 1 && first?.kind === "time" && (view.rows[0].grain ?? "day") !== "weekday";
}

/** The key each series' colour follows: a new series field (or grain) starts the colours afresh. */
export const seriesKey = view => keyId(view.columns.map(a => [a.field, a.grain ?? null]));

/**
 * The charts for `res` (a pivot of chartPivot(view)): `{line, stacked, ids, other,
 * charts: [{title, labels, series: [{id, name, values}], format, compact}], notes}`.
 * A series' `id` is its column key: colours follow it, not its label, since two columns may read alike.
 */
export function chartModel(res, table, view, display) {
  const line = isLine(table, view);
  const hasCols = view.columns.length > 0;
  const folded = res.stats.folded;
  const names = hasCols ? res.columns.map(c => (c.key[0] === OTHER ? `Other (${folded} more)` : c.key.map(partLabel).join(" / "))) : ["value"];
  const ids = hasCols ? res.columns.map(c => keyId(c.key)) : ["value"];
  const stacked = !!display.stacked && additive(view) && hasCols && !line;
  const rows = line ? res.rows : res.rows.slice(0, MAX_BARS);
  const unitOf = name => table.fields.find(f => f.name === name)?.unit;

  const charts = view.values.map((x, k) => {
    const spec = { unit: unitOf(x.field), agg: x.agg, showAs: view.showAs };
    const title = `${valueLabel(table, x)}${view.rows.length ? ` by ${view.rows.map(a => axisLabel(table, a)).join(" and ")}` : ""}`;
    const cell = (r, j) => (hasCols ? r.cells[j][k] : r.total[k]);
    let labels, series;
    if (rows.length || line) {
      labels = rows.map(r => r.key.map(partLabel).join(" · "));
      series = names.map((n, j) => ({ id: ids[j], name: hasCols ? n : valueLabel(table, x), values: rows.map(r => cell(r, j)) }));
    } else {
      // no row field: one category of the column totals (or the grand total)
      labels = ["All rows"];
      series = names.map((n, j) => ({ id: ids[j], name: hasCols ? n : valueLabel(table, x), values: [hasCols ? res.totals.columns[j][k] : res.totals.grand[k]] }));
    }
    return { title, labels, series, format: valueFormatter(spec), compact: compactFormatter(spec) };
  });

  const notes = [];
  if (!line && res.rows.length > rows.length) notes.push(`Showing the first ${rows.length} of ${res.rows.length} rows in the current sort order; the table view has all of them.`);
  if (folded) notes.push(`The ${folded} smallest series are folded into “Other”, aggregated from their rows.`);
  if (view.values.length > 1) notes.push("Each value has its own chart and scale.");
  return { line, stacked, ids, other: folded ? keyId([OTHER]) : null, charts, notes };
}
