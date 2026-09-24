// The pivot engine: a pure module (no DOM), so Node's test runner covers it.
// Contract: docs/refactor/explore/interfaces.md §3. It reshapes the rows the API
// returned (group, filter, aggregate, share); it computes no business number.

export const GRAINS = ["day", "week", "month", "quarter", "year", "weekday"];
export const AGGREGATIONS = ["sum", "count", "count_distinct", "mean", "median", "min", "max"];
export const SHOW_AS = ["value", "share_of_total", "share_of_row", "share_of_column"];
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// The key part of the column that folds the columns past ``maxColumns``; sorts last.
// An object, so no value in a table (text, a number or null) can equal it.
export const OTHER = Object.freeze({ other: true });

// A key's identity: JSON of its parts, so no text can merge two keys and null stays apart from "null".
export const keyId = parts => JSON.stringify(parts);
const DAY_MS = 86_400_000;

// A table payload (§2) whose rows are arrays in field order or objects keyed by field name.
export function toTable(payload) {
  const fields = payload.fields ?? [];
  const rows = (payload.rows ?? []).map(r => (Array.isArray(r) ? r : fields.map(f => r[f.name] ?? null)));
  return { ...payload, fields, rows };
}

// The key of an ISO date ("YYYY-MM-DD") at a time grain; null stays null.
export function timeKey(iso, grain = "day") {
  if (iso == null) return null;
  const y = +iso.slice(0, 4), m = +iso.slice(5, 7), d = +iso.slice(8, 10);
  switch (grain) {
    case "day": return iso;
    case "month": return iso.slice(0, 7);
    case "year": return iso.slice(0, 4);
    case "quarter": return `${iso.slice(0, 4)}-Q${Math.floor((m - 1) / 3) + 1}`;
    case "weekday": return WEEKDAYS[(new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7];
    case "week": {
      // ISO 8601: the week belongs to the year of its Thursday.
      const t = Date.UTC(y, m - 1, d);
      const thursday = new Date(t + (3 - ((new Date(t).getUTCDay() + 6) % 7)) * DAY_MS);
      const ty = thursday.getUTCFullYear();
      const week = Math.floor((thursday - Date.UTC(ty, 0, 1)) / DAY_MS / 7) + 1;
      return `${ty}-W${String(week).padStart(2, "0")}`;
    }
    default: throw new Error(`unknown time grain ${JSON.stringify(grain)}; choose from ${GRAINS.join(", ")}`);
  }
}

// Order of two key parts: weekdays Mon..Sun, numbers numerically, text naturally; blanks last.
export function compareParts(a, b) {
  if (a === b) return 0;
  if (a === OTHER) return 1;
  if (b === OTHER) return -1;
  if (a == null) return 1;
  if (b == null) return -1;
  const wa = WEEKDAYS.indexOf(a), wb = WEEKDAYS.indexOf(b);
  if (wa >= 0 && wb >= 0) return wa - wb;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function compareKeys(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const c = compareParts(a[i], b[i]);
    if (c) return c;
  }
  return a.length - b.length;
}

// Distinct values of one field with their row counts, in label order (the filter list).
export function distinctValues(table, name) {
  const i = fieldIndex(table, name);
  const counts = new Map();
  for (const row of table.rows) counts.set(row[i], (counts.get(row[i]) ?? 0) + 1);
  return [...counts].map(([value, count]) => ({ value, count })).sort((a, b) => compareParts(a.value, b.value));
}

function fieldIndex(table, name) {
  const i = table.fields.findIndex(f => f.name === name);
  if (i < 0) throw new Error(`unknown field ${JSON.stringify(name)}`);
  return i;
}

function accumulator(agg) {
  switch (agg) {
    case "count": { let n = 0; return { add() { n++; }, value: () => n }; }
    case "count_distinct": {
      const seen = new Set();
      return { add(v) { if (v != null) seen.add(v); }, value: () => seen.size };
    }
    case "sum": case "mean": {
      let s = 0, n = 0;
      return { add(v) { if (v != null) { s += v; n++; } }, value: () => (n ? (agg === "sum" ? s : s / n) : null) };
    }
    case "min": case "max": {
      let best = null;
      const better = agg === "min" ? (v, b) => v < b : (v, b) => v > b;
      return { add(v) { if (v != null && (best == null || better(v, best))) best = v; }, value: () => best };
    }
    case "median": {
      const xs = [];
      return {
        add(v) { if (v != null) xs.push(v); },
        value() {
          if (!xs.length) return null;
          xs.sort((a, b) => a - b);
          const h = xs.length >> 1;
          return xs.length % 2 ? xs[h] : (xs[h - 1] + xs[h]) / 2;
        },
      };
    }
    default: throw new Error(`unknown aggregation ${JSON.stringify(agg)}; choose from ${AGGREGATIONS.join(", ")}`);
  }
}

function resolveAxis(table, specs = []) {
  return specs.map(({ field, grain }) => {
    const i = fieldIndex(table, field);
    const kind = table.fields[i].kind;
    if (grain != null && kind !== "time") throw new Error(`field ${field}: a time grain applies to a time field only`);
    if (kind !== "time") return { i, key: v => v };
    const g = grain ?? "day";
    timeKey("2025-01-01", g); // rejects an unknown grain before any row is read
    const cache = new Map();
    return {
      i,
      key(v) {
        let k = cache.get(v);
        if (k === undefined) { k = timeKey(v, g); cache.set(v, k); }
        return k;
      },
    };
  });
}

function resolveFilters(table, filters = {}) {
  return Object.entries(filters).map(([field, f]) => {
    const i = fieldIndex(table, field);
    if (f.include != null && f.exclude != null) throw new Error(`filter on ${field}: give include or exclude, not both`);
    if (f.include != null) { const s = new Set(f.include); return row => s.has(row[i]); }
    if (f.exclude != null) { const s = new Set(f.exclude); return row => !s.has(row[i]); }
    throw new Error(`filter on ${field}: needs include or exclude`);
  });
}

const now = () => (globalThis.performance ?? Date).now();

/**
 * Cross-tabulate ``table`` by ``view`` (interfaces.md §3.1).
 * Every total is aggregated from the underlying rows, never from the cells it spans.
 *
 * ``options.maxColumns`` (for a chart's series) keeps the ``maxColumns - 1``
 * columns whose first-value total is largest in size (absolute value: a large
 * negative series weighs on a chart as much as a large positive one) and folds
 * the rest into one column keyed ``[OTHER]``, aggregated from their rows like
 * any other column.
 */
export function pivot(table, view = {}, options = {}) {
  const t0 = now();
  let fold = null;
  const max = options.maxColumns;
  if (max != null && view.columns?.length) {
    const probe = pivot(table, { ...view, rows: [], sort: undefined, showAs: "value" });
    if (probe.columns.length > max) {
      const ranked = probe.columns
        .map((c, j) => ({ key: keyId(c.key), v: probe.totals.columns[j][0] }))
        .sort((a, b) => (a.v == null) - (b.v == null) || Math.abs(b.v ?? 0) - Math.abs(a.v ?? 0));
      fold = { keep: new Set(ranked.slice(0, max - 1).map(c => c.key)), count: ranked.length - (max - 1) };
    }
  }
  const rowAxis = resolveAxis(table, view.rows);
  const colAxis = resolveAxis(table, view.columns);
  const values = (view.values ?? []).map(({ field, agg }) => {
    const i = fieldIndex(table, field);
    accumulator(agg); // rejects an unknown aggregation up front
    const kind = table.fields[i].kind;
    if (kind !== "measure" && !["count", "count_distinct"].includes(agg)) {
      throw new Error(`field ${field}: ${agg} needs a measure; a ${kind} field takes count or count_distinct`);
    }
    return { i, agg };
  });
  const keep = resolveFilters(table, view.filters);
  const showAs = view.showAs ?? "value";
  if (!SHOW_AS.includes(showAs)) throw new Error(`unknown showAs ${JSON.stringify(showAs)}; choose from ${SHOW_AS.join(", ")}`);

  const accs = () => values.map(v => accumulator(v.agg));
  const add = (target, row) => { for (let k = 0; k < values.length; k++) target[k].add(row[values[k].i]); };
  const node = (key, depth) => ({ key, depth, children: new Map(), cells: new Map(), total: accs() });

  const root = node([], -1); // its cells are the column totals and its total the grand total
  const columns = new Map();
  let rowsUsed = 0;
  for (const row of table.rows) {
    if (!keep.every(f => f(row))) continue;
    rowsUsed++;
    let cparts = colAxis.map(a => a.key(row[a.i]));
    let ckey = keyId(cparts);
    if (fold && !fold.keep.has(ckey)) { cparts = [OTHER]; ckey = keyId(cparts); }
    if (colAxis.length && !columns.has(ckey)) columns.set(ckey, cparts);
    let n = root;
    for (let d = -1; d < rowAxis.length; d++) {
      if (d >= 0) {
        const part = rowAxis[d].key(row[rowAxis[d].i]);
        let child = n.children.get(part);
        if (!child) { child = node([...n.key, part], d); n.children.set(part, child); }
        n = child;
      }
      add(n.total, row);
      if (colAxis.length) {
        let cell = n.cells.get(ckey);
        if (!cell) { cell = accs(); n.cells.set(ckey, cell); }
        add(cell, row);
      }
    }
  }

  const colList = [...columns.values()].sort(compareKeys);
  const colKeys = colList.map(keyId);
  const read = list => (list ? list.map(a => a.value()) : values.map(() => null));
  const grand = read(root.total);
  const colTotals = colKeys.map(k => read(root.cells.get(k)));

  const share = (x, whole) => (x == null || whole == null || whole === 0 ? null : x / whole);
  const shape = (cells, total) => {
    switch (showAs) {
      case "share_of_total": return [cells.map(c => c.map((x, k) => share(x, grand[k]))), total.map((x, k) => share(x, grand[k]))];
      case "share_of_row": return [cells.map(c => c.map((x, k) => share(x, total[k]))), total.map((x, k) => share(x, total[k]))];
      case "share_of_column": return [cells.map((c, j) => c.map((x, k) => share(x, colTotals[j][k]))), total.map((x, k) => share(x, grand[k]))];
      default: return [cells, total];
    }
  };

  const sort = view.sort ?? { by: "label" };
  const dir = sort.dir === "desc" ? -1 : 1;
  const sortCol = sort.by === "column" ? keyId(sort.key ?? []) : null;
  // Rows sort by the number shown: under showAs, the share, not the raw value.
  const sortColIndex = colKeys.indexOf(sortCol);
  const metric = n => {
    const total = n.total[0]?.value() ?? null;
    if (sort.by === "value") {
      return showAs === "value" ? total : showAs === "share_of_row" ? share(total, total) : share(total, grand[0]);
    }
    if (sort.by !== "column") return undefined;
    const x = n.cells.get(sortCol)?.[0]?.value() ?? null;
    switch (showAs) {
      case "share_of_total": return share(x, grand[0]);
      case "share_of_row": return share(x, total);
      case "share_of_column": return share(x, sortColIndex < 0 ? null : colTotals[sortColIndex][0]);
      default: return x;
    }
  };
  const order = list => {
    if (sort.by !== "value" && sort.by !== "column") {
      return list.sort((a, b) => dir * compareParts(a.key.at(-1), b.key.at(-1)));
    }
    const m = new Map(list.map(n => [n, metric(n)]));
    return list.sort((a, b) => {
      const x = m.get(a), y = m.get(b);
      if (x == null || y == null) return (x == null) - (y == null) || compareParts(a.key.at(-1), b.key.at(-1));
      return dir * (x - y) || compareParts(a.key.at(-1), b.key.at(-1));
    });
  };

  const rows = [];
  const leafDepth = rowAxis.length - 1;
  const emit = n => {
    const isGroup = n.depth < leafDepth;
    if (!isGroup || view.subtotals) {
      const [cells, total] = shape(colKeys.map(k => read(n.cells.get(k))), read(n.total));
      rows.push({ key: n.key, depth: n.depth, group: isGroup, cells, total });
    }
    if (isGroup) for (const c of order([...n.children.values()])) emit(c);
  };
  for (const c of order([...root.children.values()])) emit(c);

  const [columnCells, grandShaped] = shape(colTotals, grand);
  return {
    columns: colList.map(key => ({ key })),
    rows,
    totals: { columns: columnCells, grand: grandShaped },
    stats: {
      rowsIn: table.rows.length,
      rowsUsed,
      groups: rows.filter(r => !r.group).length,
      folded: fold ? fold.count : 0,
      ms: Math.round((now() - t0) * 10) / 10,
    },
  };
}

// How a key part reads: a missing value is "(blank)", the folded column "Other".
export const partLabel = part => (part === OTHER ? "Other" : part == null ? "(blank)" : String(part));

// One CSV cell: quoted when needed, and a text that a spreadsheet would read as a
// formula (=, +, -, @ first) is prefixed with ' so opening the file runs nothing.
function csvCell(v) {
  if (v == null) return "";
  if (typeof v === "number") return String(v);
  let s = String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

/**
 * The result as CSV: one column per row field, then one per column and value,
 * then the row totals; the last line holds the column totals. Numbers are raw
 * (shares as fractions); a blank cell is empty. ``labels`` gives the row field
 * labels and the value labels.
 */
export function toCsv(result, { rowFields = [], values = [] }) {
  const valueHead = (prefix, k) => (values.length > 1 || !prefix ? [prefix, values[k]].filter(Boolean).join(" · ") : prefix);
  const head = [...rowFields];
  for (const c of result.columns) values.forEach((_, k) => head.push(valueHead(c.key.map(partLabel).join(" / "), k)));
  values.forEach((_, k) => head.push(valueHead("Total", k)));
  const lines = [head];
  for (const r of result.rows) {
    const labels = rowFields.map((_, d) => (d < r.key.length ? partLabel(r.key[d]) : d === r.key.length ? "Subtotal" : ""));
    lines.push([...labels, ...r.cells.flat(), ...r.total]);
  }
  const totalLabels = rowFields.map((_, d) => (d === 0 ? "Total" : ""));
  lines.push([...(rowFields.length ? totalLabels : []), ...result.totals.columns.flat(), ...result.totals.grand]);
  return lines.map(l => l.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

const isObject = x => x != null && typeof x === "object" && !Array.isArray(x);

/**
 * Why ``view`` is not a view ``pivot`` can take, or null. A link carries a view
 * from outside the page, so its shape is checked before any of it is used; the
 * field names are checked against the table by ``pivot`` itself.
 */
export function viewError(view) {
  if (!isObject(view)) return "the view must be an object";
  const known = ["rows", "columns", "values", "filters", "showAs", "sort", "subtotals"];
  const extra = Object.keys(view).filter(k => !known.includes(k));
  if (extra.length) return `the view has unknown keys ${JSON.stringify(extra)}`;
  for (const axis of ["rows", "columns"]) {
    const list = axis in view ? view[axis] : []; // present means a list: null is not "none"
    if (!Array.isArray(list)) return `${axis} must be a list`;
    for (const a of list) {
      if (!isObject(a) || typeof a.field !== "string") return `each of ${axis} needs a field name`;
      if (a.grain != null && !GRAINS.includes(a.grain)) return `unknown time grain ${JSON.stringify(a.grain)}`;
    }
  }
  const values = "values" in view ? view.values : [];
  if (!Array.isArray(values)) return "values must be a list";
  for (const v of values) {
    if (!isObject(v) || typeof v.field !== "string") return "each value needs a field name";
    if (!AGGREGATIONS.includes(v.agg)) return `unknown aggregation ${JSON.stringify(v.agg)}`;
  }
  const filters = "filters" in view ? view.filters : {};
  if (!isObject(filters)) return "filters must be an object";
  for (const [name, f] of Object.entries(filters)) {
    const lists = ["include", "exclude"].filter(k => isObject(f) && k in f);
    if (lists.length !== 1 || !Array.isArray(f[lists[0]])) return `the filter on ${name} needs one include or exclude list`;
  }
  if ("showAs" in view && !SHOW_AS.includes(view.showAs)) return `unknown showAs ${JSON.stringify(view.showAs)}`;
  if ("sort" in view) {
    const s = view.sort;
    if (!isObject(s) || !["label", "value", "column"].includes(s.by)) return "sort.by must be label, value or column";
    if (s.dir != null && s.dir !== "asc" && s.dir !== "desc") return "sort.dir must be asc or desc";
    if (s.by === "column" && !Array.isArray(s.key)) return "a column sort needs the column's key";
  }
  if ("subtotals" in view && typeof view.subtotals !== "boolean") return "subtotals must be true or false";
  return null;
}

// How many of a field's distinct values a filter keeps (values it names that the data lacks do not count).
export function keptCount(values, filter) {
  if (filter?.include) {
    const s = new Set(filter.include);
    return values.filter(x => s.has(x.value)).length;
  }
  const s = new Set(filter?.exclude ?? []);
  return values.filter(x => !s.has(x.value)).length;
}
