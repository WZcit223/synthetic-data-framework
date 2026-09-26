<!-- Grounded questions over the computed facts, the demand anomalies, and each SKU's anomalies by a chosen detector. -->
<script>
  import DataTable from "../../components/tables/DataTable.svelte";
  import { api } from "../../lib/api.js";

  /** @type {{anomalies: any, detectors: any, detector: string, detections: any, ondetector: (name: string) => void}} */
  let { anomalies, detectors, detector, detections, ondetector } = $props();

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

  const chosen = $derived(detectors?.detectors.find(x => x.name === detector));
  const detectionTone = { direction: v => (v === "spike" ? "warn" : v === "drop" ? "bad" : null) };
  const detectionFormat = { score: v => (v == null ? "–" : v.toLocaleString(undefined, { maximumFractionDigits: 3 })) };
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
    <h3 class="sub">Each SKU's anomalies <span class="pill">detector plug-ins</span></h3>
    {#if detectors}
      <div class="pick">
        <label for="detector">Detector</label>
        <select id="detector" value={detector} onchange={e => ondetector(e.currentTarget.value)}>
          {#each detectors.detectors as x (x.name)}<option value={x.name}>{x.name}</option>{/each}
        </select>
        {#if chosen}<span class="muted">{chosen.description}; reads {chosen.signals.join(", ")}</span>{/if}
      </div>
      {#if detections?.error && detections.detector === detector}
        <div class="note top bad">{detector} did not run: {detections.error}</div>
      {:else if detections && detections.detector === detector}
        <div class="note top"><b>{detections.rows.length}</b> SKU-days flagged on the current world, highest score first.</div>
        <DataTable fields={detections.fields} rows={detections.rows} tone={detectionTone} format={detectionFormat}
          height="260px" download="anomalies" placeholder="No SKU-day flagged." />
      {:else}
        <div class="note top muted">Running {detector}…</div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .ask { display: flex; gap: 8px; }
  .ask input { flex: 1; min-width: 0; }
  .answer { margin-top: 12px; font-size: 14px; min-height: 40px; }
  .chips { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { color: var(--ink); cursor: pointer; }
  .top { margin: 0 0 8px; }
  .sub { margin-top: 18px; }
</style>
