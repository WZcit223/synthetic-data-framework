// The one mapping from a lib/pivot.js result to Tabulator's columns and rows, for
// PivotTable. Pure (no DOM beyond the text nodes a formatter returns), so it is
// tested without a table. It computes no number: every cell, subtotal and total
// shown is one pivot() returned. Contract: docs/refactor/frontend/interfaces.md §3.2.
import { keyId, partLabel } from "../../lib/pivot.js";

export const MAX_TABLE_COLUMNS = 400; // value cells across; wider results are cut, and the CSV export has them all

const text = s => document.createTextNode(s);
const mark = (sort, by, key) =>
  sort.by === by && (by !== "column" || keyId(sort.key ?? []) === keyId(key)) ? (sort.dir === "desc" ? " ▼" : " ▲") : "";

/**
 * Tabulator's columns and rows for `result`.
 * - `rowTitles`, `valueTitles`: the row fields' and the values' labels; `formats`: one per value.
 * - `totals`: the display's totals switch; `heat`: shade leaf cells, each value on its own
 *   scale over the ramp `ramp` (low to high), with `ink(fill)` the text colour on a fill.
 * Returns `{columns, data, tree, sorts, groupSorts, heatKey, cut}`: `tree` when subtotals nest
 * rows (Tabulator's data tree); `sorts` the sort each clickable leaf header asks for, keyed by
 * its field, and `groupSorts` each clickable group header's, keyed by its first leaf's field.
 */
export function pivotConfig(result, { view, rowTitles, valueTitles, formats, totals, heat, ramp, ink }) {
  const sort = view.sort ?? { by: "label", dir: "asc" };
  const nV = view.values.length;
  const L = view.columns.length;
  const tree = !!view.subtotals && view.rows.length > 1;
  const colLimit = Math.max(1, Math.floor(MAX_TABLE_COLUMNS / Math.max(1, nV)));
  const cut = result.columns.length > colLimit;
  const shownColumns = result.columns.slice(0, colLimit);
  const withTotalColumn = L === 0 || totals;
  const withTotalRow = totals || view.rows.length === 0; // with no row field the totals row is the only row
  /** @type {Record<string, {by: string, key?: any[]}>} */
  const sorts = {};
  // the sort of a group of values (a column's, or the totals'), keyed by the field of its first value:
  // Tabulator names a group column by no field of its own
  /** @type {Record<string, {by: string, key?: any[]}>} */
  const groupSorts = {};

  // heat scales per value, over leaf cells (and the total column when there are no columns)
  const scales = view.values.map((_, k) => {
    if (!heat) return null;
    let lo = Infinity, hi = -Infinity;
    for (const r of result.rows) {
      if (r.group) continue;
      const xs = L ? r.cells.slice(0, colLimit).map(c => c[k]) : [r.total[k]];
      for (const x of xs) if (x != null) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
    }
    return lo <= hi ? { lo, hi } : null;
  });
  const fill = (x, k) => {
    const s = scales[k];
    const t = s.hi === s.lo ? 1 : (x - s.lo) / (s.hi - s.lo);
    return ramp[Math.min(ramp.length - 1, Math.max(0, Math.floor(t * ramp.length)))];
  };
  const valueColumn = (field, k, title, { shade, total, calc }) => ({
    field,
    title,
    hozAlign: "right",
    headerHozAlign: "right",
    minWidth: 88,
    cssClass: total ? "tot" : undefined,
    titleFormatter: cell => text(cell.getValue()),
    formatter: cell => {
      const x = cell.getValue();
      if (x == null) return text("–");
      if (shade && scales[k] && !cell.getData()._group) {
        const bg = fill(x, k);
        const el = cell.getElement();
        el.style.background = bg;
        el.style.color = ink(bg);
      }
      return text(formats[k](x));
    },
    bottomCalc: withTotalRow ? () => calc : undefined,
    bottomCalcFormatter: cell => text(cell.getValue() == null ? "–" : formats[k](cell.getValue())),
  });

  // the row-label columns: one per row field, or one indented column when subtotals nest the rows
  const labelTitle = tree ? rowTitles.join(" / ") : null;
  const labelFields = tree ? ["label"] : rowTitles.length ? rowTitles.map((_, i) => `r${i}`) : ["r0"];
  const columns = labelFields.map((field, i) => {
    const title = tree ? labelTitle : rowTitles[i] ?? "";
    const sortable = rowTitles.length > 0 && i === 0;
    if (sortable) sorts[field] = { by: "label" };
    return {
      field,
      // Tabulator shows an empty title as the text "&nbsp;"; a space keeps the header blank
      title: (title || " ") + (sortable ? mark(sort, "label") : ""),
      frozen: true,
      minWidth: 96,
      titleFormatter: cell => text(cell.getValue()),
      formatter: cell => text(cell.getValue() ?? ""),
      cssClass: "rl",
      bottomCalc: withTotalRow ? () => (i === 0 ? "Total" : "") : undefined,
      bottomCalcFormatter: cell => text(cell.getValue() ?? ""),
    };
  });

  // the value columns: nested groups per column field, a value per leaf; then the totals
  const leaf = (j, key) => {
    const title = L ? partLabel(key[L - 1]) : "";
    const cols = view.values.map((_, k) => valueColumn(`c${j}_${k}`, k, nV > 1 ? valueTitles[k] : title, {
      shade: true, total: false, calc: result.totals.columns[j]?.[k] ?? null,
    }));
    if (nV === 1) {
      sorts[`c${j}_0`] = { by: "column", key };
      cols[0].title = title + mark(sort, "column", key);
      return cols;
    }
    groupSorts[`c${j}_0`] = { by: "column", key };
    return [{ title: title + mark(sort, "column", key), titleFormatter: cell => text(cell.getValue()), columns: cols, cssClass: "sortable" }];
  };
  const group = (from, to, depth) => {
    const out = [];
    let j = from;
    while (j < to) {
      const prefix = keyId(shownColumns[j].key.slice(0, depth + 1));
      let k = j + 1;
      while (k < to && keyId(shownColumns[k].key.slice(0, depth + 1)) === prefix) k++;
      if (depth === L - 1) {
        for (let q = j; q < k; q++) out.push(...leaf(q, shownColumns[q].key));
      } else {
        out.push({ title: partLabel(shownColumns[j].key[depth]), titleFormatter: cell => text(cell.getValue()), columns: group(j, k, depth + 1) });
      }
      j = k;
    }
    return out;
  };
  if (L) columns.push(...group(0, shownColumns.length, 0));
  if (withTotalColumn) {
    const cols = view.values.map((_, k) => valueColumn(`t_${k}`, k, valueTitles[k], {
      shade: L === 0, total: L > 0, calc: result.totals.grand[k],
    }));
    if (L) {
      if (nV > 1) {
        groupSorts["t_0"] = { by: "value" };
        columns.push({ title: "Total" + mark(sort, "value"), titleFormatter: cell => text(cell.getValue()), columns: cols, cssClass: "sortable" });
      } else {
        sorts["t_0"] = { by: "value" };
        cols[0].title = "Total" + mark(sort, "value");
        columns.push(cols[0]);
      }
    } else {
      sorts["t_0"] = { by: "value" };
      cols[0].title += mark(sort, "value");
      columns.push(...cols);
    }
  }
  for (const c of columns.flatMap(function flat(c) { return c.columns ? [c, ...c.columns.flatMap(flat)] : [c]; })) {
    if (c.field in sorts) c.cssClass = [c.cssClass, "sortable"].filter(Boolean).join(" ");
  }

  // the rows: flat, with a repeated prefix left blank, or nested under their subtotals
  const record = (r, i) => {
    const o = { id: i, _key: r.key, _group: r.group };
    if (tree) o.label = partLabel(r.key[r.depth]);
    else if (!view.rows.length) o.r0 = "All rows";
    r.cells.slice(0, colLimit).forEach((c, j) => c.forEach((x, k) => (o[`c${j}_${k}`] = x)));
    if (withTotalColumn) r.total.forEach((x, k) => (o[`t_${k}`] = x));
    return o;
  };
  let data;
  if (tree) {
    data = [];
    const stack = [];
    result.rows.forEach((r, i) => {
      const o = record(r, i);
      while (stack.length > r.depth) stack.pop();
      (stack.length ? (stack.at(-1)._children ??= []) : data).push(o);
      if (r.group) stack.push(o);
    });
  } else {
    let prev = [];
    data = result.rows.map((r, i) => {
      const o = record(r, i);
      view.rows.forEach((_, d) => {
        const same = prev.length > d && r.key.slice(0, d + 1).every((p, q) => p === prev[q]);
        o[`r${d}`] = same ? "" : partLabel(r.key[d]);
      });
      prev = r.key;
      return o;
    });
  }

  const k = scales.findIndex(Boolean);
  const heatKey = k < 0 ? null : { label: valueTitles[k], lo: formats[k](scales[k].lo), hi: formats[k](scales[k].hi), each: nV > 1 };
  return { columns, data, tree, sorts, groupSorts, heatKey, cut: cut ? { shown: colLimit, of: result.columns.length } : null };
}
