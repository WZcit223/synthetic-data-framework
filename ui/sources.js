// The sources an Explore link may name (docs/refactor/explore/interfaces.md §3.2), and why
// a link's source cannot be opened. Pure, so the pages that build links and the Explore
// page that opens them are checked against the same rules by Node's test runner.

export const EFFECT_TABLES = ["effects", "replicates"];

const SHAPES = "dataset, experiment, synthesis or effects";

// Why a link's source cannot be opened, or null.
export function sourceError(source) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return "the link names no source";
  const keys = Object.keys(source);
  if (keys.length !== 1) return `a source names exactly one of ${SHAPES}; got ${JSON.stringify(keys)}`;
  const [k] = keys;
  if (k === "dataset") return typeof source.dataset === "string" ? null : "dataset must be a name";
  if (k === "experiment" || k === "synthesis") return isObject(source[k]) ? null : `${k} must be a request body`;
  if (k === "effects") return effectsError(source.effects);
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

const isObject = v => v != null && typeof v === "object" && !Array.isArray(v);
