// CSV writing shared by every table: the one cell rule, and a writer for flat tables.

// One CSV cell: quoted when needed, and a text that a spreadsheet would read as a
// formula (=, +, -, @ first) is prefixed with ' so opening the file runs nothing.
export function csvCell(v) {
  if (v == null) return "";
  if (typeof v === "number") return String(v);
  let s = String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

/**
 * A flat table as CSV: a header of the fields' labels, then one line per row.
 * ``fields`` is the API's ``[{name, label, ...}]``; ``rows`` are arrays in their order.
 * Numbers are written raw; a blank cell is empty.
 */
export function tableCsv(fields, rows) {
  const lines = [fields.map(f => f.label ?? f.name), ...rows];
  return lines.map(l => l.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
