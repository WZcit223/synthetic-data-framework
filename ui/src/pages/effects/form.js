// The Effects page's study form, as data: the request it holds and back. Pure (no DOM);
// the checks and the defaults are lib/effects-model.js, used as it is.

let rows = 0; // policy rows made so far, for their field ids

/**
 * The form for a request: number fields as `{text, bad}` (`bad` is text the browser
 * cannot parse, which it reports as ""), each policy row with the policy it started
 * from, so switching its kind back restores that policy's values.
 */
export function toForm(request, catalog) {
  return {
    interventions: [...request.interventions],
    outcomes: [...request.outcomes],
    policies: request.policies.map(p => policyRow(p, catalog)),
    replicates: { text: String(request.replicates), bad: false },
    confidence: request.confidence,
  };
}

/** A policy row for `policy` (a kind not offered falls back to the first). */
export function policyRow(policy, catalog) {
  const kind = catalog.policies.some(c => c.kind === policy.kind) ? policy.kind : catalog.policies[0].kind;
  const row = { id: ++rows, kind, origin: policy, values: {} };
  setKind(row, kind, catalog);
  return row;
}

/** Switch a row's kind: its fields become that kind's, filled from the row's own policy or the defaults. */
export function setKind(row, kind, catalog) {
  const spec = catalog.policies.find(c => c.kind === kind);
  row.kind = kind;
  row.values = Object.fromEntries(spec.params.map(pr => {
    const v = row.origin.kind === kind && row.origin[pr.name] != null ? row.origin[pr.name] : pr.default;
    return [pr.name, { text: v == null ? "" : String(v), bad: false }];
  }));
}

// A number field's value: NaN for text it cannot parse or nothing, so the server takes no default for it.
const number = f => (f.bad || f.text.trim() === "" ? NaN : Number(f.text));

/** The request the form holds (lib/effects-model.js requestError checks it). */
export function readForm(form) {
  return {
    interventions: [...form.interventions],
    policies: form.policies.map(r => ({ kind: r.kind, ...Object.fromEntries(Object.entries(r.values).map(([k, f]) => [k, number(f)])) })),
    outcomes: [...form.outcomes],
    replicates: number(form.replicates),
    confidence: Number(form.confidence),
  };
}
