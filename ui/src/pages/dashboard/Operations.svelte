<!-- The agent with its audit trace, the business impact, the workflow run and the scenarios. -->
<script>
  import DataTable from "../../components/tables/DataTable.svelte";
  import { api } from "../../lib/api.js";
  import { fmt } from "../../lib/format.js";

  /** @type {{impact: any, workflow: any, scenarios: any}} */
  let { impact, workflow, scenarios } = $props();

  let request = $state("");
  /** @type {any} */
  let run = $state(null);
  let running = $state(false);

  async function agentAsk() {
    if (!request) request = "should I reorder and what's the money impact?";
    running = true;
    run = null;
    try {
      run = await api("/agent/ask?q=" + encodeURIComponent(request));
    } finally {
      running = false;
    }
  }

  const TRACE = [
    { name: "seq", label: "#", kind: "measure" },
    { name: "name", label: "Tool", kind: "dimension" },
    { name: "status", label: "Status", kind: "dimension" },
    { name: "duration_ms", label: "ms", kind: "measure" },
  ];
  const traceRows = $derived((run?.trace ?? []).map(e => TRACE.map(f => e[f.name])));
  const statusTone = { status: v => (v === "ok" ? "good" : "bad") };

  const SCENARIOS = [
    { name: "scenario", label: "Scenario", kind: "dimension" },
    { name: "outbound_lines", label: "Outbound lines", kind: "measure" },
    { name: "skus_needing_order", label: "SKUs to order", kind: "measure" },
    { name: "safety_stock_units", label: "Safety stock", kind: "measure" },
    { name: "safety_stock_vs_baseline_pct", label: "vs baseline", kind: "measure" },
  ];
  const scenarioRows = $derived((scenarios?.scenarios ?? []).map(s => SCENARIOS.map(f => s[f.name])));
  const scenarioFormat = {
    safety_stock_units: v => fmt(Math.round(v)),
    safety_stock_vs_baseline_pct: v => `${v > 0 ? "+" : ""}${v}%`,
  };
  const scenarioTone = { safety_stock_vs_baseline_pct: v => (v > 0 ? "warn" : null) };
</script>

<div class="grid two">
  <div class="card">
    <h3>Warehouse agent <span class="pill">tool calls · audit trace · human-in-loop</span></h3>
    <form class="ask" onsubmit={e => { e.preventDefault(); agentAsk(); }}>
      <input bind:value={request} aria-label="Request for the warehouse agent"
        placeholder="e.g. should I reorder and what's the money impact?" />
      <button class="primary">Run</button>
    </form>
    <div class="answer">
      {#if running}<span class="muted">…</span>
      {:else if run}<span class="pill">{run.plan.join(" → ")}</span> {run.answer}{/if}
    </div>
    {#if run?.proposed_actions?.length}
      {@const a = run.proposed_actions[0]}
      <div><span class="pill proposed">⏳ proposed: {a.proposed_action} {a.sku_id} ×{a.quantity} — {a.status}</span></div>
    {/if}
    {#if run}
      <DataTable fields={TRACE} rows={traceRows} tone={statusTone} />
    {/if}
    <div class="note">State-changing actions are proposed, not executed — they need approval.
      ALGO-HOOK: LLM tool-use planner; same tools, guardrails, audit log.</div>
  </div>
  <div class="card">
    <h3>Business impact <span class="pill">counterfactual £ · assumptions stated</span></h3>
    {#if impact}
      <div class="figures">
        <div><div class="k">Annualised net saving</div><div class="big good">≈ {fmt(impact.annualised_net_saving)}</div></div>
        <div><div class="k">Stockout-units avoided</div><div class="big">{fmt(impact.stockout_units_avoided)}</div></div>
      </div>
      <div class="note">naive {fmt(impact.unmet_units.naive)} → ours {fmt(impact.unmet_units.ours)} unmet units
        over {impact.horizon_days} days · assumes {(impact.assumptions.holding_cost_annual_rate * 100).toFixed(0)}% holding,
        95% service. DATA-HOOK: real unit costs.</div>
    {/if}
    <h3 class="wf-title">Data Intelligence Workflow <span class="pill">DAG run record</span></h3>
    {#if workflow}
      <div class="note">
        {#each workflow.trace as e (e.seq)}
          <span class="pill step" class:ok={e.status === "ok"} class:failed={e.status !== "ok"}>{e.seq}. {e.name} · {e.duration_ms}ms</span>
        {/each}
        <div class="run">run <b>{workflow.run.run_id}</b> · {workflow.run.steps} steps · {workflow.run.total_ms}ms ·
          {workflow.run.errors} errors</div>
      </div>
    {/if}
  </div>
</div>

<div class="card spaced">
  <h3>What-if scenario simulation <span class="pill">generator → simulation engine</span></h3>
  <div class="note top">Same framework, a family of stress scenarios — safety stock re-sized per scenario.</div>
  {#if scenarios}
    <DataTable fields={SCENARIOS} rows={scenarioRows} format={scenarioFormat} tone={scenarioTone} />
  {/if}
</div>

<style>
  .ask { display: flex; gap: 8px; }
  .ask input { flex: 1; min-width: 0; }
  .answer { margin-top: 12px; font-size: 14px; min-height: 36px; }
  .proposed { border-color: var(--warn); display: inline-block; margin: 8px 0; }
  .wf-title { margin: 14px 0 6px; }
  .step { display: inline-block; margin: 2px; }
  .ok { border-color: var(--good); }
  .failed { border-color: var(--bad); }
  .run { margin-top: 6px; }
  .spaced { margin-top: 14px; }
  .top { margin: 0 0 8px; }
</style>
