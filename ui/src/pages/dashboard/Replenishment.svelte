<!--
  One (s,S) policy end to end: a SKU's demand and forecast, the replayed policy
  comparison, the (s,S) levels at a service level, and the forecast backtest.
-->
<script>
  import LineChart from "../../components/charts/LineChart.svelte";
  import DataTable from "../../components/tables/DataTable.svelte";
  import { fmt } from "../../lib/format.js";
  import { demandChart } from "./series.js";

  /** @type {{movers: any[], sku: string, series: any, comparison: any, plan: any, backtest: any,
   *   serviceLevel: string, onsku: (sku: string) => void, onservicelevel: (level: string) => void}} */
  let { movers, sku, series, comparison, plan, backtest, serviceLevel, onsku, onservicelevel } = $props();

  const chart = $derived(series ? demandChart(series) : null);

  const LEVELS = [["0.90", "90%"], ["0.95", "95%"], ["0.975", "97.5%"], ["0.99", "99%"]];
  const pct = v => (v * 100).toFixed(1) + "%";
  const measure = (name, label) => ({ name, label, kind: "measure" });
  const dimension = (name, label) => ({ name, label, kind: "dimension" });

  const METRICS = [
    ["SKUs needing an order", "skus_needing_order"], ["Safety stock (units)", "safety_stock_units"],
    ["Unmet units", "unmet_units"], ["Holding cost", "holding_cost"], ["Order cost", "order_cost"],
  ];
  const policies = $derived(comparison?.policies ?? []);
  const comparisonTable = $derived({
    fields: [dimension("metric", "Metric"), ...policies.map((p, i) => measure(`p${i}`, p.policy))],
    rows: METRICS.map(([label, key]) => [label, ...policies.map(p => p[key])]),
  });

  const PLAN_FIELDS = [
    dimension("sku_id", "SKU"), measure("avg_daily_demand", "μ/day"), measure("demand_std", "σ"),
    measure("safety_stock", "Safety"), measure("reorder_point_s", "s (reorder)"),
    measure("order_up_to_S", "S (up-to)"), measure("order_qty", "Order"),
  ];
  const planRows = $derived((plan?.rows ?? []).map(r => PLAN_FIELDS.map(f => r[f.name])));

  const BACKTEST_FIELDS = [
    dimension("model", "Model"), measure("MAE", "MAE"), measure("RMSE", "RMSE"),
    measure("MAPE_pct", "MAPE %"), measure("WAPE_pct", "WAPE %"), measure("bias", "Bias"),
  ];
  const backtestRows = $derived((backtest?.results ?? []).map(r => BACKTEST_FIELDS.map(f => r[f.name])));
</script>

<div class="flow">
  <span class="step">Demand history</span><span class="arrow">→</span>
  <span class="step">Demand profile <span class="muted">(μ, variability)</span></span><span class="arrow">→</span>
  <span class="step">(s,S) levels at a service level</span><span class="arrow">→</span>
  <span class="step">Order</span><span class="arrow">→</span>
  <span class="step">Replayed fill rate vs no safety stock</span>
</div>

<div class="grid two">
  <div class="card">
    <div class="head">
      <h3>Demand &amp; forecast</h3>
      <select aria-label="SKU shown in the demand chart" value={sku} onchange={e => onsku(e.currentTarget.value)}>
        {#each movers ?? [] as m (m.sku_id)}
          <option value={m.sku_id}>{m.sku_id} · {m.name} ({m.abc_class})</option>
        {/each}
      </select>
    </div>
    {#if series}
      {#if series.history.length}
        <LineChart format={fmt} yLabel="units" labels={chart.labels} series={chart.series} band={chart.band} />
      {:else}
        <div class="muted">No demand for this SKU.</div>
      {/if}
      <div class="note" data-testid="series-meta">
        Forecast ({series.forecast.forecaster}) ≈ <b>{fmt(Math.round(chart.total))}</b> units over the next
        {series.forecast.days.length} days; each day's {Math.round(series.forecast.level * 100)} % interval is shaded
        ({series.history.length} days with demand in the history).
      </div>
    {/if}
  </div>
  <div class="card">
    <h3>Policy comparison <span class="pill">demand history replayed</span></h3>
    {#if policies.length === 2}
      <div class="figures">
        <div><div class="k">Fill rate — {policies[0].policy}</div><div class="big bad">{pct(policies[0].fill_rate)}</div></div>
        <div class="arrow big">→</div>
        <div><div class="k">Fill rate — {policies[1].policy}</div><div class="big good">{pct(policies[1].fill_rate)}</div></div>
      </div>
      <DataTable fields={comparisonTable.fields} rows={comparisonTable.rows} />
      <div class="note">Each SKU's {comparison.horizon_days}-day demand history is replayed under both policies
        (default cost assumptions). ALGO-HOOK: a stochastic demand and lead-time model gives distributions,
        not one number.</div>
    {/if}
  </div>
</div>

<div class="card spaced">
  <div class="head">
    <h3>(s, S) inventory optimisation <span class="pill">safety stock from demand variability</span></h3>
    <label class="muted level">service level
      <select value={serviceLevel} onchange={e => onservicelevel(e.currentTarget.value)}>
        {#each LEVELS as [value, label] (value)}<option {value}>{label}</option>{/each}
      </select>
    </label>
  </div>
  {#if plan}
    <div class="note top">z={fmt(plan.z)} · lead {plan.lead_time_days}d + review {plan.review_days}d ·
      <b>{plan.skus_needing_order}</b> SKUs need an order · total safety stock
      <b>{fmt(plan.total_safety_stock_units)}</b> units</div>
    <DataTable fields={PLAN_FIELDS} rows={planRows} height="360px" download="replenishment-plan" />
  {/if}
  <div class="note">s = μ·(L+R) + z·σ·√(L+R). Higher service level → more safety stock.
    ALGORITHM-HOOK: cost-based newsvendor + fitted lead-time demand distribution.</div>
</div>

<div class="card spaced">
  <h3>Forecast backtest — measured <span class="pill">walk-forward · real number</span></h3>
  {#if backtest}
    <div class="note top">{backtest.granularity} granularity · {backtest.series_len} points ·
      mean {fmt(backtest.series_mean)}/bucket · winner <b class="good">{backtest.best_model}</b></div>
    <DataTable fields={BACKTEST_FIELDS} rows={backtestRows}
      format={{ model: m => (m === backtest.best_model ? "🏆 " : "") + m }} />
  {/if}
  <div class="note">Backtested on the current synthetic world's demand. Same harness
    runs on real data via <code>uv run sdf backtest &lt;csv&gt;</code>. MAPE averages |error|/actual over
    buckets with sales; WAPE = Σ|error| / Σactual.
    ALGORITHM-HOOK: beat the winning baseline with DeepAR/TFT/LightGBM.</div>
</div>

<style>
  .flow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .step { background: var(--surface-raised); border: 1px solid var(--rule); border-radius: 8px; padding: 6px 11px; font-size: 12px; }
  .arrow { color: var(--ink-muted); }
  .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
  .head h3 { margin: 0; }
  .head select { max-width: 100%; }
  .level { font-size: 12px; margin-left: auto; display: flex; align-items: center; gap: 8px; }
  .figures { margin-bottom: 10px; }
  .spaced { margin-top: 14px; }
  .top { margin: 0 0 10px; }
</style>
