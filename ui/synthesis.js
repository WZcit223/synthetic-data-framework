// Pure helpers of the Synthesizers page (no DOM), so Node's test runner covers them.
// They reshape what the API returned; the scores themselves come from the server.

/**
 * The value a form control holds for one parameter (``Param`` in interfaces.md §2.1),
 * or why it cannot be sent: the same checks the server makes, so a run the form
 * allows is never refused for its parameters.
 * ``raw`` is the input's text, or a boolean for a checkbox.
 */
export function readParam(param, raw) {
  if (param.type === "bool") {
    if (typeof raw === "boolean") return { value: raw }; // a checkbox
    if (raw === "true" || raw === "false") return { value: raw === "true" }; // the choice of a nullable bool
    return param.nullable ? { value: null } : { error: `${param.name}: choose true or false` };
  }
  const text = typeof raw === "string" ? raw.trim() : raw;
  if (text === "" || text == null) {
    return param.nullable ? { value: null } : { error: `${param.name}: enter a value` };
  }
  if (param.type === "str") return { value: String(raw) };
  const value = Number(text);
  if (!Number.isFinite(value)) return { error: `${param.name}: enter a number` };
  if (param.type === "int" && !Number.isInteger(value)) return { error: `${param.name}: enter a whole number` };
  const below = param.min != null && (param.exclusive ? value <= param.min : value < param.min);
  const above = param.max != null && (param.exclusive ? value >= param.max : value > param.max);
  if (below || above) return { error: `${param.name}: ${boundsText(param)}` };
  return { value };
}

// "from 0 to 1", "between 0.5 and 1, both excluded", "at least 0", "at most 10"; "" when unbounded.
export function boundsText(param) {
  const { min, max, exclusive } = param;
  if (min != null && max != null) return exclusive ? `between ${min} and ${max}, both excluded` : `from ${min} to ${max}`;
  if (min != null) return exclusive ? `above ${min}` : `at least ${min}`;
  if (max != null) return exclusive ? `below ${max}` : `at most ${max}`;
  return "";
}

// The column values of one origin ("real" or "synthetic") from a run's rows.
export function column(rows, fields, name, origin) {
  const i = fields.findIndex(f => f.name === name);
  const o = fields.findIndex(f => f.name === "origin");
  if (i < 0 || o < 0) throw new Error(`the run has no ${i < 0 ? name : "origin"} column`);
  return rows.filter(r => r[o] === origin && r[i] != null).map(r => r[i]);
}

function quantile(sorted, q) {
  if (!sorted.length) return null;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/**
 * Two distributions on shared bins: the share of real and of synthetic values
 * per bin. The bins span the real data's 1st to 99th percentile, so one outlier
 * does not squeeze the rest into a single bin; values beyond fall into the edge
 * bins. A column with few distinct whole values (an hour, a weekday) gets one
 * bin per value instead.
 */
export function histogram(real, synth, bins = 12) {
  const all = [...real, ...synth];
  if (!all.length) return { labels: [], real: [], synthetic: [] };
  const sorted = [...real].sort((a, b) => a - b);
  const distinct = new Set(real.map(v => Math.round(v)));
  const whole = real.every(v => Number.isInteger(v)) && distinct.size <= 24;
  let edges;
  if (whole) {
    const values = [...distinct].sort((a, b) => a - b);
    edges = values.map(v => v - 0.5).concat(values.at(-1) + 0.5);
  } else {
    let lo = quantile(sorted.length ? sorted : [...all].sort((a, b) => a - b), 0.01);
    let hi = quantile(sorted.length ? sorted : [...all].sort((a, b) => a - b), 0.99);
    if (!(hi > lo)) { lo -= 0.5; hi += 0.5; }
    edges = Array.from({ length: bins + 1 }, (_, k) => lo + ((hi - lo) * k) / bins);
  }
  const n = edges.length - 1;
  const count = values => {
    const c = new Array(n).fill(0);
    for (const v of values) {
      let k = edges.findIndex((e, j) => j > 0 && v < e) - 1;
      if (k < 0) k = v < edges[0] ? 0 : n - 1; // beyond the edges: the edge bins
      c[k]++;
    }
    return c.map(x => (values.length ? x / values.length : null));
  };
  const labels = whole
    ? edges.slice(0, -1).map(e => String(e + 0.5))
    : edges.slice(0, -1).map((e, k) => `${short(e)}–${short(edges[k + 1])}`);
  return { labels, real: count(real), synthetic: count(synth) };
}

const short = v => (Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-US") : String(Math.round(v * 100) / 100));

// The link that reopens a run's table in the Explore page (interfaces.md §3), or null when the run cannot be repeated.
export function exploreLink(run) {
  if (!run.repeatable) return null;
  const source = { synthesis: { synthesizer: run.synthesizer, source: run.source, params: run.params } };
  return "explore.html#view=" + encodeURIComponent(JSON.stringify({ source }));
}
