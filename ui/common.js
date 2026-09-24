// Shared by every page: the one way to reach the backend, HTML escaping and
// number formatting. The pages talk to the backend only through api(), so the
// base URL is configurable (set window.SDF_API_BASE before the page's module
// loads to host the UI elsewhere) and every path they use can be checked
// against the OpenAPI schema.
// UI rule: reshape what the API returned (sort, filter, group, pivot, chart);
// never compute a business number here.
export const API = globalThis.SDF_API_BASE ?? "/api/v1";

export async function api(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    const err = new Error(`${path}: ${res.status}`);
    err.status = res.status;
    try {
      err.detail = describeDetail((await res.json()).detail);
    } catch {
      err.detail = null; // not a JSON error body
    }
    throw err;
  }
  return res.json();
}

// FastAPI's error detail as one line: a message, or the list a 422 carries.
export function describeDetail(detail) {
  if (detail == null) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(d => (d.loc ? `${d.loc.filter(p => p !== "body").join(".")}: ${d.msg}` : String(d.msg ?? d))).join("; ");
  }
  return JSON.stringify(detail);
}

export const $ = s => document.querySelector(s);

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
