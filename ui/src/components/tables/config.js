// The one mapping from the API's table shape to Tabulator's: `fields` is the
// API's `[{name, label, kind, unit?, aggregate?}]` and `rows` are arrays in their
// order. Pure (no DOM), so the mapping is tested without a table.
// Contract: docs/refactor/frontend/interfaces.md §3.2.
import { fmt } from "../../lib/format.js";

// How a cell reads when the page gives no formatter: a number as fmt() writes it,
// a blank as "–", anything else as its text.
export const cellText = v => (v == null ? "–" : typeof v === "number" ? fmt(v) : String(v));

// Sort order by kind: numbers as numbers, ISO dates and times as text (which orders
// them), dimensions as text; a blank sorts first.
const SORTERS = { measure: "number", time: "string", dimension: "string" };

/**
 * Tabulator column definitions. `label` (with `unit` in brackets) is the title;
 * `kind` gives the alignment and the sorter. `format` is `{[name]: v => text}`,
 * `tone` is `{[name]: (v, record) => "good"|"warn"|"bad"|null}`: a cell class,
 * so a status reads in colour. Titles and cells are text, never HTML: a label
 * can come from the API (a policy's name), and Tabulator would write it as markup.
 */
export function columns(fields, { format = {}, tone = {} } = {}) {
  return fields.map(f => ({
    field: f.name,
    title: f.unit ? `${f.label} (${f.unit})` : f.label,
    titleFormatter: cell => document.createTextNode(cell.getValue()),
    hozAlign: f.kind === "measure" ? "right" : "left",
    headerHozAlign: f.kind === "measure" ? "right" : "left",
    sorter: SORTERS[f.kind] ?? "string",
    headerSort: true,
    // wide enough for the title and a typical value; a narrow screen scrolls the table, not the page
    minWidth: Math.max(f.kind === "measure" ? 72 : 110, 8 * String(f.label).length + 34),
    formatter: cell => {
      const v = cell.getValue();
      const cls = tone[f.name]?.(v, cell.getData());
      if (cls) cell.getElement().classList.add(`tone-${cls}`);
      return document.createTextNode((format[f.name] ?? cellText)(v));
    },
  }));
}

/** The rows as Tabulator's records: one object per row, keyed by field name. */
export function records(fields, rows) {
  return rows.map(r => Object.fromEntries(fields.map((f, i) => [f.name, r[i]])));
}
