// Each kind of Explore source, loaded: a catalogue dataset, or a request repeated on the
// current world (an experiment, a synthesizer run, an effect study, an estimation).
// Returns the table's payload ({fields, rows}) and what the source bar says about it.
import { api } from "../../lib/api.js";

export async function fetchSource(source, datasets) {
  if (source.dataset != null) {
    const d = await api(`/datasets/${encodeURIComponent(source.dataset)}`);
    const entry = datasets.find(e => e.name === d.name);
    // a data source's rows do not come from the world, and a large one answers a uniform sample
    const meta = { title: d.label, description: entry?.description ?? "", world: d.world || null, total: d.total_rows, truncated: d.truncated, sampled: !!d.sampled };
    return { payload: d, meta };
  }
  if (source.experiment != null) {
    const d = await api("/experiments", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(source.experiment),
    });
    return {
      payload: d,
      meta: { title: "Policy experiment", description: "Each intervention replayed under each policy; one row per outcome metric.", world: null, total: d.rows.length, truncated: false },
    };
  }
  if (source.estimates != null) {
    // an estimation (causal interfaces.md §3.4): the same request again, on the current world
    const d = await api("/causal/estimates", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(source.estimates.request),
    });
    const observed = source.estimates.table === "data";
    const payload = observed ? d.data : { fields: d.fields, rows: d.rows };
    const truth = d.true_effect == null ? "no known truth" : `true effect ${d.true_effect.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    return {
      payload,
      meta: {
        title: observed ? "Promotion benchmark: observed rows" : "Estimator scores",
        description: observed
          ? "What an analyst would observe: one row per SKU, whether it was promoted and its weekly units."
          : `Each estimator on the same rows of ${d.source}; ${truth}.`,
        world: null,
        total: payload.rows.length,
        truncated: false,
      },
    };
  }
  if (source.forecasts != null) {
    // a forecast backtest (algorithms interfaces.md §8): the same request again, on the current world or the benchmark
    const d = await api("/forecasts/backtest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(source.forecasts.request),
    });
    const table = source.forecasts.table;
    const on = d.source === "world" ? `the current world (${d.world})` : "the demand benchmark";
    const TITLES = {
      scores: ["Forecast scores", `Each forecaster over every SKU, origin and day ahead on ${on}.`],
      by_horizon: ["Forecast scores by days ahead", `Each forecaster's scores for each day after the origin, on ${on}.`],
      forecasts: ["Forecasts after the last origin", `Each forecaster's mean and quantiles for every SKU and day, with the actual demand, on ${on}.`],
    };
    const [title, description] = TITLES[table];
    return { payload: d[table], meta: { title, description, world: null, total: d[table].rows.length, truncated: false } };
  }
  if (source.effects != null) {
    // an effect study (causal interfaces.md §1.5): the same request again, on the current world
    const d = await api("/effects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(source.effects.request),
    });
    const replicates = source.effects.table === "replicates";
    const payload = replicates ? d.replicates : { fields: d.fields, rows: d.rows };
    const n = d.rows.length ? d.rows[0][d.fields.findIndex(f => f.name === "replicates")] : 0;
    return {
      payload,
      meta: {
        title: replicates ? "Effect study: every replicate" : "Effect study: effects",
        description: replicates
          ? `Each arm's value in each of the ${n} paired replicates, with its difference from that replicate's baseline.`
          : `Each intervention against the baseline over ${n} paired replicates: the mean difference and its interval.`,
        world: null,
        total: payload.rows.length,
        truncated: false,
      },
    };
  }
  // a synthesizer run (interfaces.md §3): repeated with the parameters it reported, so it gives the same table
  const d = await api("/synthesis/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(source.synthesis),
  });
  const used = Object.entries(d.params).map(([k, v]) => `${k} ${JSON.stringify(v)}`).join(", ");
  return {
    payload: d,
    meta: {
      title: `${d.synthesizer}: real and synthetic`,
      description: `A run on source “${d.source}”${used ? ` with ${used}` : ""}; origin tells real rows from synthetic ones.`,
      world: null,
      total: d.rows.length,
      truncated: false,
      kind: d.kind,
    },
  };
}
