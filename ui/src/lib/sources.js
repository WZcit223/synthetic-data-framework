// The sources an Explore link may name (docs/refactor/explore/interfaces.md §3.2), and why
// a link's source cannot be opened. Pure, so the pages that build links and the Explore
// page that opens them are checked against the same rules by Node's test runner.

export const EFFECT_TABLES = ["effects", "replicates"];
export const ESTIMATE_TABLES = ["scores", "data"];
export const FORECAST_TABLES = ["scores", "by_horizon", "forecasts"];

const SHAPES = "dataset, experiment, synthesis, effects, estimates or forecasts";

// Why a link's source cannot be opened, or null.
export function sourceError(source) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return "the link names no source";
  const keys = Object.keys(source);
  if (keys.length !== 1) return `a source names exactly one of ${SHAPES}; got ${JSON.stringify(keys)}`;
  const [k] = keys;
  if (k === "dataset") return typeof source.dataset === "string" ? null : "dataset must be a name";
  if (k === "experiment" || k === "synthesis") return isObject(source[k]) ? null : `${k} must be a request body`;
  if (k === "effects") return effectsError(source.effects);
  if (k === "estimates") return estimatesError(source.estimates);
  if (k === "forecasts") return forecastsError(source.forecasts);
  return `unknown source ${JSON.stringify(k)}`;
}

// {effects: {request, table}}: the POST /effects body, and which of the answer's tables to pivot.
function effectsError(effects) {
  if (!isObject(effects)) return "effects must hold a request and a table";
  const extra = Object.keys(effects).filter(k => k !== "request" && k !== "table");
  if (extra.length) return `effects holds only request and table; got ${JSON.stringify(extra)}`;
  if (!isObject(effects.request)) return "effects.request must be a request body";
  // only a study has tables: check_only may be absent or false, nothing else
  if ("check_only" in effects.request && effects.request.check_only !== false) return "effects.request asks for the budget only, which has no table";
  if (!EFFECT_TABLES.includes(effects.table)) return `effects.table must be one of ${EFFECT_TABLES.join(" or ")}`;
  return null;
}

// {estimates: {request, table}}: the POST /causal/estimates body, and the scores or the benchmark's observed rows.
function estimatesError(estimates) {
  if (!isObject(estimates)) return "estimates must hold a request and a table";
  const extra = Object.keys(estimates).filter(k => k !== "request" && k !== "table");
  if (extra.length) return `estimates holds only request and table; got ${JSON.stringify(extra)}`;
  if (!isObject(estimates.request)) return "estimates.request must be a request body";
  if (!ESTIMATE_TABLES.includes(estimates.table)) return `estimates.table must be one of ${ESTIMATE_TABLES.join(" or ")}`;
  if (estimates.table === "data" && !isObject(estimates.request.benchmark)) {
    return 'estimates.table "data" needs a benchmark request; a catalogue dataset opens as {dataset: name}';
  }
  return null;
}

// {forecasts: {request, table}}: the POST /forecasts/backtest body, and which of the answer's three tables to pivot.
function forecastsError(forecasts) {
  if (!isObject(forecasts)) return "forecasts must hold a request and a table";
  const extra = Object.keys(forecasts).filter(k => k !== "request" && k !== "table");
  if (extra.length) return `forecasts holds only request and table; got ${JSON.stringify(extra)}`;
  if (!isObject(forecasts.request)) return "forecasts.request must be a request body";
  if (!FORECAST_TABLES.includes(forecasts.table)) return `forecasts.table must be one of ${FORECAST_TABLES.join(", ")}`;
  return null;
}

const isObject = v => v != null && typeof v === "object" && !Array.isArray(v);
