// The dashboard's policy comparison, as data: GET /replenishment/comparison to a DataTable
// with one column per policy, whatever their number. Pure, so tested.

const IN_SAMPLE = [
  ["SKUs to order", "skus_needing_order"], ["Safety stock", "safety_stock_units"],
  ["Unmet units", "unmet_units"], ["Holding cost", "holding_cost"], ["Order cost", "order_cost"],
];

export const pct = v => (v * 100).toFixed(1) + "%";

/** `{fields, rows}`: the in-sample metrics, then the out-of-sample ones when the API measured them. */
export function comparisonTable(comparison) {
  const policies = comparison?.policies ?? [];
  const rows = IN_SAMPLE.map(([label, key]) => [label, ...policies.map(p => p[key])]);
  if (comparison?.holdout_days) {
    const days = comparison.holdout_days;
    rows.push(
      [`Cost, last ${days} days`, ...policies.map(p => p.holdout_total_cost)],
      [`Fill, last ${days} days`, ...policies.map(p => (p.holdout_fill_rate == null ? null : pct(p.holdout_fill_rate)))],
    );
  }
  return {
    fields: [
      { name: "metric", label: "Metric", kind: "dimension" },
      ...policies.map((p, i) => ({ name: `p${i}`, label: p.policy, kind: "measure" })),
    ],
    rows,
  };
}

/** The cheapest policy on the days its levels were not fitted on, or null when there is no such measure. */
export function cheapestOutOfSample(comparison) {
  const measured = (comparison?.policies ?? []).filter(p => p.holdout_total_cost != null);
  return measured.length ? measured.reduce((a, b) => (b.holdout_total_cost < a.holdout_total_cost ? b : a)) : null;
}
