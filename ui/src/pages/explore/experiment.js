// The Explore page's experiment request (POST /experiments), as data: the form a request
// fills, the request a form holds, and why it cannot be sent. Pure (no DOM); the policy
// rows are the Effects page's (effects/form.js), used as they are.
import { policyRow } from "../effects/form.js";

/** The request the form starts from: the first two interventions and policies, every outcome. */
export function defaultExperiment(catalog) {
  return {
    interventions: catalog.interventions.slice(0, 2),
    policies: catalog.policies.slice(0, 2).map(c => ({ kind: c.kind })), // each parameter starts at the catalogue's default
    outcomes: [...catalog.outcomes],
  };
}

export function toExperimentForm(request, catalog) {
  return {
    interventions: [...(request.interventions ?? [])],
    outcomes: [...(request.outcomes ?? [])],
    policies: (request.policies ?? []).map(p => policyRow(p, catalog)),
  };
}

// A number field's value: NaN for text it cannot parse or nothing, so the server takes no default for it.
const number = f => (f.bad || f.text.trim() === "" ? NaN : Number(f.text));

export function readExperimentForm(form) {
  return {
    interventions: [...form.interventions],
    policies: form.policies.map(r => ({ kind: r.kind, ...Object.fromEntries(Object.entries(r.values).map(([k, f]) => [k, number(f)])) })),
    outcomes: [...form.outcomes],
  };
}

/** Why the request cannot be sent, or null: the checks the endpoint makes, from the catalogue's bounds. */
export function experimentError(request, catalog) {
  if (!request.interventions.length) return "Choose at least one intervention.";
  if (!request.outcomes.length) return "Choose at least one outcome.";
  for (const [n, p] of request.policies.entries()) {
    const spec = catalog.policies.find(c => c.kind === p.kind);
    for (const pr of spec.params) {
      const v = p[pr.name];
      const where = `Policy ${n + 1}, ${pr.name.replaceAll("_", " ")}`;
      if (!Number.isFinite(v)) return `${where}: enter a number.`;
      if (pr.type === "int" && !Number.isInteger(v)) return `${where}: enter a whole number.`;
      const below = pr.min != null && (pr.exclusive ? v <= pr.min : v < pr.min);
      const above = pr.max != null && (pr.exclusive ? v >= pr.max : v > pr.max);
      if (below || above) {
        return pr.exclusive ? `${where} must be between ${pr.min} and ${pr.max}, both excluded.` : `${where} must be from ${pr.min} to ${pr.max}.`;
      }
    }
  }
  return null;
}
