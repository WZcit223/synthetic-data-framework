// Pure helpers of the Effects page (no DOM), so Node's test runner covers them.
// Every number comes from POST /effects: the effects, their intervals and the work
// budget are the server's. These helpers only read, group, format and lay them out.
import { readParam } from "./synthesis.js";

export const CONFIDENCES = [0.8, 0.9, 0.95, 0.99];
export const COVERS = "not distinguishable from 0";

// A {fields, rows} table as one object per row.
export function records({ fields, rows }) {
  return rows.map(r => Object.fromEntries(fields.map((f, i) => [f.name, r[i]])));
}

// Whether an effect's interval covers 0. Its edges count as covering, so an
// interval that ends at 0, or collapses to the point 0, is not distinguishable from 0.
export const coversZero = r => r.ci_low <= 0 && 0 <= r.ci_high;

// How to read one effect, in words: the reading never depends on colour alone.
export const reading = r => (coversZero(r) ? COVERS : r.effect > 0 ? "above 0" : "below 0");

export const rowLabel = r => `${r.intervention} · ${r.policy}`;

// The effects grouped by metric, each group in the server's row order; one chart per group,
// since metrics have different units and a chart has one axis.
export function byMetric(effects) {
  const groups = new Map();
  for (const r of effects) {
    if (!groups.has(r.metric)) groups.set(r.metric, []);
    groups.get(r.metric).push(r);
  }
  return [...groups].map(([metric, rows]) => ({ metric, rows }));
}

// The paired differences behind each effect of one metric, read from the replicate
// table's difference field (the page subtracts nothing): one entry per effect row, with
// its dots in replicate order and the effect itself as their mean.
export function replicateRows(effects, replicates, metric) {
  return effects
    .filter(r => r.metric === metric)
    .map(r => ({
      ...r,
      dots: replicates
        .filter(x => x.metric === metric && x.intervention === r.intervention && x.policy === r.policy)
        .map(x => ({ replicate: x.replicate, seed: x.seed, difference: x.difference })),
    }));
}

/**
 * A number rounded as ``sdf effects`` rounds it: whole from 100 up, else three significant
 * digits, and scientific below 0.0001. The digits match the CLI's; the thousands separator is
 * the reader's locale, as on every page (the CLI prints a space). A true minus sign;
 * ``signed`` adds "+" to a positive value.
 */
export function amount(v, { signed = false, locale = undefined } = {}) {
  if (v == null || !Number.isFinite(v)) return "–";
  const sign = v < 0 ? "−" : signed && v > 0 ? "+" : "";
  const a = Math.abs(v);
  let text;
  if (a >= 100) text = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(a);
  else if (a !== 0 && a < 0.0001) {
    // Python's "{:.3g}" (the CLI) turns scientific below 1e-4 and drops trailing zeros: 5e-05, 6.79e-06
    const [mantissa, exponent] = a.toExponential(2).split("e");
    text = `${Number(mantissa)}e${exponent.replace("-", "−")}`;
  }
  else text = new Intl.NumberFormat(locale, { maximumSignificantDigits: 3 }).format(a);
  return sign + text;
}

export const intervalText = (r, locale) => `${amount(r.ci_low, { signed: true, locale })} to ${amount(r.ci_high, { signed: true, locale })}`;

// The relative change as a signed percentage; "–" when the baseline mean is 0 and there is none.
export function relativeText(v, locale = undefined) {
  if (v == null || !Number.isFinite(v)) return "–";
  const nf = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 });
  const text = nf.format(Math.abs(v));
  // a change that rounds to 0 % carries no sign: "+0%" would claim a direction the digits do not show
  return (text === nf.format(0) ? "" : v < 0 ? "−" : v > 0 ? "+" : "") + text;
}

// The server's check_only answer as the form shows it; the page holds no budget formula.
export function budgetView(answer, locale = undefined) {
  const n = v => new Intl.NumberFormat(locale).format(v);
  return {
    over: !answer.within_budget,
    share: answer.max_work > 0 ? Math.min(1, answer.work / answer.max_work) : 1,
    text: answer.within_budget
      ? `Work ${n(answer.work)} of ${n(answer.max_work)}: ${answer.size}.`
      : `Over the budget: work ${n(answer.work)} exceeds ${n(answer.max_work)} (${answer.size}). Lower the replicates or the lists.`,
  };
}

// The request the form starts from: the page's own default, a study of promo_spike.
export function defaultRequest(catalog) {
  const interventions = catalog.interventions.filter(n => n !== "baseline");
  const kind = catalog.policies.find(p => p.kind === "service-level") ?? catalog.policies[0];
  return {
    interventions: interventions.includes("promo_spike") ? ["promo_spike"] : interventions.slice(0, 1),
    policies: [policyDefaults(kind)],
    outcomes: catalog.outcomes.includes("simulated_cost") ? ["simulated_cost"] : catalog.outcomes.slice(0, 1),
    replicates: Math.min(10, catalog.effects.max_replicates),
    confidence: 0.95,
  };
}

// Service levels "Add policy" offers once every kind is on the form, in this order.
const MORE_LEVELS = [0.9, 0.99, 0.8, 0.85, 0.975, 0.7];

/**
 * The policy "Add policy" adds: a kind not yet on the form, else a service level not yet
 * on it, so a new row never repeats one already there. The server still has the last word
 * on duplicates (its 422 names them), since it names the policies.
 */
export function nextPolicy(catalog, policies) {
  const unused = catalog.policies.find(k => !policies.some(p => p.kind === k.kind));
  if (unused) return policyDefaults(unused);
  const kind = catalog.policies.find(k => k.kind === "service-level" && k.params.some(p => p.name === "service_level"));
  if (!kind) return policyDefaults(catalog.policies[0]);
  const taken = new Set(policies.filter(p => p.kind === kind.kind).map(p => p.service_level));
  const level = MORE_LEVELS.find(v => !taken.has(v));
  return { ...policyDefaults(kind), ...(level == null ? {} : { service_level: level }) };
}

const policyDefaults = kind => Object.fromEntries([["kind", kind.kind], ...kind.params.map(p => [p.name, p.default])]);

/**
 * A request read from a link, fitted to the catalogue: what the catalogue does not offer is
 * dropped and named in ``dropped``, and a missing list or number falls back to the default.
 */
export function fitRequest(raw, catalog) {
  const base = defaultRequest(catalog);
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { request: base, dropped: [] };
  const dropped = [];
  const names = (list, offered) => {
    if (!Array.isArray(list)) return null;
    const kept = list.filter(n => offered.includes(n) && n !== "baseline");
    dropped.push(...list.filter(n => !kept.includes(n)).map(String));
    return kept.length ? [...new Set(kept)] : null;
  };
  const interventions = names(raw.interventions, catalog.interventions); // in the request's order, so dropped is too
  const policies = Array.isArray(raw.policies)
    ? raw.policies.flatMap(p => {
        const kind = catalog.policies.find(k => k.kind === p?.kind);
        if (!kind) {
          dropped.push(String(p?.kind ?? p));
          return [];
        }
        return [{ ...policyDefaults(kind), ...Object.fromEntries(kind.params.filter(k => p[k.name] != null).map(k => [k.name, p[k.name]])) }];
      })
    : [];
  return {
    request: {
      interventions: interventions ?? base.interventions,
      policies: policies.length ? policies : base.policies,
      outcomes: names(raw.outcomes, catalog.outcomes) ?? base.outcomes,
      replicates: Number.isInteger(raw.replicates) ? raw.replicates : base.replicates,
      confidence: CONFIDENCES.includes(raw.confidence) ? raw.confidence : base.confidence,
    },
    dropped,
  };
}

// Why a request cannot be sent, or null: the checks the endpoint makes, from the catalogue's bounds.
export function requestError(request, catalog) {
  if (!request.interventions.length) return "Choose at least one intervention.";
  if (!request.outcomes.length) return "Choose at least one outcome.";
  if (!request.policies.length) return "Add at least one policy.";
  const max = catalog.max_per_list;
  for (const [k, list] of Object.entries({ interventions: request.interventions, policies: request.policies, outcomes: request.outcomes })) {
    if (list.length > max) return `At most ${max} ${k}.`;
  }
  for (const [n, p] of request.policies.entries()) {
    const kind = catalog.policies.find(k => k.kind === p.kind);
    if (!kind) return `Policy ${n + 1}: unknown kind ${p.kind}.`;
    for (const param of kind.params) {
      const read = readParam(param, p[param.name] == null ? "" : String(p[param.name]));
      if (read.error) return `Policy ${n + 1}, ${read.error.replaceAll("_", " ")}.`;
    }
  }
  const most = catalog.effects.max_replicates;
  if (!Number.isInteger(request.replicates) || request.replicates < 2 || request.replicates > most) {
    return `Replicates: a whole number from 2 to ${most}.`;
  }
  return null;
}

// The page's own address for a request, so a copied link reproduces the study.
export const requestHash = request => "#request=" + encodeURIComponent(JSON.stringify(request));

// The request held in an address, {error} when it cannot be read, or null when there is none.
export function readRequestHash(hash) {
  const m = /^#request=(.+)$/.exec(hash);
  if (!m) return null;
  try {
    const v = JSON.parse(decodeURIComponent(m[1]));
    return v && typeof v === "object" && !Array.isArray(v) ? { request: v } : { error: "the link holds no request" };
  } catch {
    return { error: "the request in this link is not valid JSON" };
  }
}

// The link that opens one of the study's tables in Explore (exploration contract §3.2).
export function exploreLink(request, table) {
  const body = { ...request };
  delete body.check_only; // a budget answer has no table
  return "explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { effects: { request: body, table } } }));
}
