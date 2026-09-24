// Pure helpers of the Effects page's "Estimate from data" view (no DOM), so Node's test
// runner covers them. Every number comes from POST /causal/estimates and every bound from
// GET /estimators; these helpers only read, check and lay them out.
import { OTHER, SERIES } from "./palette.js";
import { CONFIDENCES } from "./effects-model.js";
import { readParam } from "./synthesis.js";

export const SWEEP = [0, 0.75, 1.5, 2.25, 3]; // the confounding sweep: five steps over the benchmark's range
const PREFERRED = ["difference-in-means", "regression-adjustment", "ipw"];

// Each estimator's colour follows its place in the catalogue, never its place on screen; past eight, grey.
export function estimatorColors(names) {
  return new Map(names.map((n, i) => [n, i < SERIES.length ? SERIES[i] : OTHER]));
}

const benchmarkDefaults = catalog => Object.fromEntries(catalog.benchmark.params.map(p => [p.name, p.default]));

// The request the view starts from: the built-ins that are mounted, the benchmark's defaults, its whole adjustment set.
export function defaultEstimateRequest(catalog) {
  const names = catalog.estimators.map(e => e.name);
  const preferred = PREFERRED.filter(n => names.includes(n));
  return {
    estimators: (preferred.length ? preferred : names).slice(0, catalog.limits.max_estimators),
    benchmark: benchmarkDefaults(catalog),
    question: { ...catalog.benchmark.question, covariates: [...catalog.benchmark.question.covariates] },
    confidence: 0.95,
  };
}

/**
 * A request read from a link, fitted to the catalogue: estimators not mounted and covariates
 * the benchmark does not have are dropped and named in ``dropped``; anything missing falls
 * back to the default. Parameter values are kept as given, so the form shows and checks them.
 */
export function fitEstimateRequest(raw, catalog) {
  const base = defaultEstimateRequest(catalog);
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { request: base, dropped: [] };
  const dropped = [];
  const mounted = catalog.estimators.map(e => e.name);
  let estimators = base.estimators;
  if (Array.isArray(raw.estimators)) {
    const kept = [...new Set(raw.estimators.filter(n => mounted.includes(n)))];
    dropped.push(...raw.estimators.filter(n => !mounted.includes(n)).map(String));
    if (kept.length) estimators = kept;
  }
  const benchmark = { ...base.benchmark };
  if (raw.benchmark && typeof raw.benchmark === "object") {
    for (const p of catalog.benchmark.params) if (raw.benchmark[p.name] !== undefined) benchmark[p.name] = raw.benchmark[p.name];
  }
  const offered = catalog.benchmark.question.covariates;
  let covariates = base.question.covariates;
  if (Array.isArray(raw.question?.covariates)) {
    covariates = offered.filter(c => raw.question.covariates.includes(c)); // in the benchmark's order
    dropped.push(...raw.question.covariates.filter(c => !offered.includes(c)).map(String));
  }
  return {
    request: {
      estimators,
      benchmark,
      question: { ...base.question, covariates },
      confidence: CONFIDENCES.includes(raw.confidence) ? raw.confidence : base.confidence,
    },
    dropped,
  };
}

// Why a request cannot be sent, or null: the checks the endpoint makes, from the published bounds.
export function estimateRequestError(request, catalog) {
  if (!request.estimators.length) return "Choose at least one estimator.";
  const most = catalog.limits.max_estimators;
  if (request.estimators.length > most) return `At most ${most} estimators.`;
  for (const p of catalog.benchmark.params) {
    const v = request.benchmark[p.name];
    const read = readParam(p, v == null ? "" : String(v));
    if (read.error) return `Benchmark ${read.error.replaceAll("_", " ")}.`;
  }
  return null;
}

// The page's address for the view's request, so a link reproduces the estimation.
export const estimateHash = request => "#estimate=" + encodeURIComponent(JSON.stringify(request));

// The request an address holds, {error} when it cannot be read, {} for the bare view, or null for another view.
export function readEstimateHash(hash) {
  const m = /^#estimate(?:=(.*))?$/.exec(hash);
  if (!m) return null;
  if (!m[1]) return {}; // the bare view: "#estimate" or "#estimate="
  try {
    const v = JSON.parse(decodeURIComponent(m[1]));
    return v && typeof v === "object" && !Array.isArray(v) ? { request: v } : { error: "the link holds no request" };
  } catch {
    return { error: "the request in this link is not valid JSON" };
  }
}

// How a score row reads, in words: covering the truth, missing it, without an interval, or an error.
export function scoreReading(row) {
  if (row.effect == null) return row.seconds == null ? "not run" : "error";
  if (row.ci_low == null) return "no interval";
  if (row.covers == null) return "no truth to compare";
  return row.covers === "yes" ? "covers the truth" : "misses the truth";
}

// The confounding sweep's requests: the view's request at each step, nothing else changed.
export const sweepRequests = request => SWEEP.map(c => ({ ...request, benchmark: { ...request.benchmark, confounding: c } }));

/**
 * The sweep's lines: one per estimator, its bias at each step (null where it failed),
 * read from each step's scores table; the page computes no bias itself.
 */
export function sweepSeries(results, estimators) {
  return estimators.map(name => ({
    name,
    values: results.map(rows => {
      const row = rows.find(r => r.estimator === name);
      return row?.bias ?? null;
    }),
  }));
}

// The link that opens the estimation's scores, or the benchmark's observed rows, in Explore.
export function estimatesLink(request, table) {
  return "explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { estimates: { request, table } } }));
}
