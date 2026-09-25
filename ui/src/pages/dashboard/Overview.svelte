<!-- KPIs, the capability cards, the ABC distribution and the generated insights. -->
<script>
  import BarChart from "../../components/charts/BarChart.svelte";
  import { fmt } from "../../lib/format.js";

  /** @type {{overview: any}} */
  let { overview } = $props();

  const CAPS = [
    { h: "Data management", p: "Multi-source overlay via the DataSourceRegistry; canonical entities keep synthetic & real interchangeable.", t: "Foundation Layer" },
    { h: "Decision support", p: "(s,S) reorder points and order quantities per SKU, sized to a service level.", t: "Application · ALGO-HOOK: newsvendor" },
    { h: "Insight / anomaly", p: "Stockout & dead-stock detection and portfolio KPIs surfaced automatically.", t: "Application · ALGO-HOOK: anomaly model" },
    { h: "Knowledge organisation", p: "Templated narrative insights today; LLM + knowledge-graph is the upgrade path.", t: "Application · ALGO-HOOK: LLM+KG" },
  ];

  const kpis = $derived.by(() => {
    const k = overview?.kpis;
    if (!k) return [];
    return [
      ["Total SKUs", fmt(k.total_skus)],
      ["Units on hand", fmt(k.total_on_hand)],
      ["Inventory value", "≈ " + fmt(Math.round(k.inventory_value))],
      ["Outbound lines", fmt(k.outbound_lines)],
      ["Cancel rate", (k.cancel_rate * 100).toFixed(1) + "%"],
      ["Express share", (k.express_rate * 100).toFixed(1) + "%"],
    ];
  });
  const abc = $derived(Object.entries(overview?.abc ?? {}));
</script>

<div class="grid kpis">
  {#each kpis as [label, value] (label)}
    <div class="card kpi"><div class="v">{value}</div><div class="k">{label}</div></div>
  {/each}
</div>

<div class="grid caps">
  {#each CAPS as c (c.h)}
    <div class="card cap"><h3>{c.h}</h3><p>{c.p}</p><span class="tag">{c.t}</span></div>
  {/each}
</div>

<div class="grid two">
  <div class="card">
    <h3>ABC distribution</h3>
    {#if abc.length}
      <BarChart horizontal height={140} format={fmt}
        labels={abc.map(([cls]) => "Class " + cls)} series={[{ name: "SKUs", values: abc.map(([, n]) => n) }]} />
    {/if}
  </div>
  <div class="card">
    <h3>Auto-generated insights <span class="pill">knowledge stub</span></h3>
    <ul class="insights">
      {#each overview?.insights ?? [] as line, i (i)}<li>{line}</li>{/each}
    </ul>
  </div>
</div>

<style>
  .kpis { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .caps { grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); margin: 14px 0; }
  .kpi .v { font-size: 26px; font-weight: 680; letter-spacing: -.02em; }
  .kpi .k { font-size: 12px; color: var(--ink-muted); margin-top: 2px; }
  .cap h3 { margin: 0 0 4px; }
  .cap p { margin: 0; color: var(--ink-muted); font-size: 12.5px; }
  .cap .tag { font-size: 10.5px; color: var(--accent); margin-top: 8px; display: inline-block; }
  .insights { padding-left: 18px; margin: 0; }
  .insights li { margin: 6px 0; }
</style>
