<!-- Grounded questions over the computed facts, and the demand anomalies. -->
<script>
  import DataTable from "../../components/tables/DataTable.svelte";
  import { api } from "../../lib/api.js";

  /** @type {{anomalies: any}} */
  let { anomalies } = $props();

  const SAMPLES = ["which SKUs are stockout?", "safety stock at 95%?", "how good is the forecast?",
    "any demand anomalies?", "inventory value?", "ABC mix?"];

  let question = $state("");
  /** @type {{intent: string, answer: string} | null} */
  let reply = $state(null);
  let asking = $state(false);

  async function ask(q = question) {
    if (!q) return;
    question = q;
    asking = true;
    try {
      reply = await api("/ask?q=" + encodeURIComponent(q));
    } finally {
      asking = false;
    }
  }

  const FIELDS = [
    { name: "index", label: "#", kind: "measure" },
    { name: "direction", label: "Type", kind: "dimension" },
    { name: "value", label: "Actual", kind: "measure" },
    { name: "expected", label: "Expected", kind: "measure" },
    { name: "robust_z", label: "Robust-z", kind: "measure" },
  ];
  const rows = $derived((anomalies?.anomalies ?? []).map(a => FIELDS.map(f => a[f.name])));
  const tone = { direction: v => (v === "spike" ? "warn" : "bad") };
</script>

<div class="grid two">
  <div class="card">
    <h3>Ask the warehouse <span class="pill">grounded · LLM+KG is the ALGO-HOOK</span></h3>
    <form class="ask" onsubmit={e => { e.preventDefault(); ask(); }}>
      <input bind:value={question} aria-label="Question about the warehouse data"
        placeholder="e.g. safety stock at 95%?  which SKUs are stockout?" />
      <button class="primary">Ask</button>
    </form>
    <div class="answer">
      {#if asking}<span class="muted">…</span>
      {:else if reply}<span class="pill">{reply.intent}</span> {reply.answer}{/if}
    </div>
    <div class="chips">
      {#each SAMPLES as q (q)}<button type="button" class="pill chip" onclick={() => ask(q)}>{q}</button>{/each}
    </div>
    <div class="note">Every answer is routed to computed facts — nothing invented.</div>
  </div>
  <div class="card">
    <h3>Demand anomalies <span class="pill">seasonal residual · robust-z</span></h3>
    {#if anomalies}
      <div class="note top"><b>{anomalies.count}</b> anomalies on a {anomalies.series_len}-point
        {anomalies.granularity} series (period {anomalies.seasonal_period}).</div>
      <DataTable fields={FIELDS} {rows} {tone} placeholder="No anomalies at current settings." />
    {/if}
    <div class="note">ALGORITHM-HOOK: Isolation Forest / autoencoder over multivariate state.</div>
  </div>
</div>

<style>
  .ask { display: flex; gap: 8px; }
  .ask input { flex: 1; min-width: 0; }
  .answer { margin-top: 12px; font-size: 14px; min-height: 40px; }
  .chips { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { color: var(--ink); cursor: pointer; }
  .top { margin: 0 0 8px; }
</style>
