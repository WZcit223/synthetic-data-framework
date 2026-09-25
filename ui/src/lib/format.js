// HTML escaping and number formatting, shared by every page.

// Every string that came from the API is escaped before it goes into innerHTML:
// product names, for one, come from imported files and may contain markup.
export const esc = v => String(v ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
export const fmt = n => (typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : n == null ? "–" : esc(n));

/**
 * A formatter for one pivot value: ``{unit, agg, showAs}`` in, ``v => text`` out.
 * Shares read as percentages, counts as whole numbers, currency and averages
 * with two decimals; a blank is "–", never 0.
 */
export function valueFormatter({ unit = null, agg = "sum", showAs = "value" } = {}, locale = undefined) {
  const counting = agg === "count" || agg === "count_distinct";
  let nf;
  if (showAs !== "value" || (unit === "share" && !counting)) {
    nf = new Intl.NumberFormat(locale, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
  } else if (counting) {
    nf = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  } else if (unit === "currency" || agg === "mean" || agg === "median") {
    nf = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else {
    const whole = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
    const frac = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return v => (v == null ? "–" : Number.isInteger(v) ? whole.format(v) : frac.format(v));
  }
  return v => (v == null ? "–" : nf.format(v));
}

// Short axis labels: 12K, 3.4M; shares as whole percentages.
export function compactFormatter({ unit = null, agg = "sum", showAs = "value" } = {}, locale = undefined) {
  const counting = agg === "count" || agg === "count_distinct";
  const nf = showAs !== "value" || (unit === "share" && !counting)
    ? new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 })
    : new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 });
  return v => (v == null ? "–" : nf.format(v));
}
