<!--
  The generation controls: sliders sized to the backend's limits, the generator,
  the regenerate button and its status, and the CSV exports.
-->
<script>
  import { API, api } from "../../lib/api.js";
  import { onGrid } from "./sliders.js";

  /** @type {{onregenerated: () => Promise<unknown>}} */
  let { onregenerated } = $props();

  let spec = $state({ n_skus: 200, horizon_days: 90, daily_orders_per_a_sku: 6, stockout_pressure: 0.08, seed: 42 });
  let bounds = $state({ n_skus: { min: 20, max: 500 }, horizon_days: { min: 30, max: 180 } });
  /** @type {{name: string, description: string}[]} */
  let generators = $state([]);
  let generator = $state("");
  let builtBy = $state("");
  let status = $state("");

  const EXPORTS = ["skus", "inventory", "outbound", "sensors"];
  const STEPS = { n_skus: 20, horizon_days: 10 };

  // Size the generation sliders to what this backend accepts; keep the page defaults if it cannot say.
  async function loadLimits() {
    let l;
    try { l = await api("/world/limits"); } catch (err) { console.warn("world limits unavailable:", err.message); return; }
    bounds = { n_skus: l.n_skus, horizon_days: l.horizon_days };
    for (const key of ["n_skus", "horizon_days"]) spec[key] = onGrid(spec[key], bounds[key], STEPS[key]);
  }

  // The warehouse generators this server offers; the current world's is preselected and named.
  async function loadGenerators() {
    let catalogue, world;
    try { [catalogue, world] = await Promise.all([api("/synthesizers"), api("/world")]); }
    catch (err) { console.warn("generators unavailable:", err.message); return; }
    generators = catalogue.synthesizers.filter(s => s.produces === "warehouse");
    generator = world.synthesizer;
    builtBy = world.synthesizer;
  }

  async function regen() {
    status = "regenerating…";
    const body = { ...spec, synthesizer: generator || undefined };
    let g;
    try {
      g = await api("/world", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    } catch (err) {
      const why = err.status === 409 ? "another generation is running — try again in a moment"
        : `rejected: ${err.detail ?? err.status ?? err.message}`;
      status = "✗ " + why;
      return;
    }
    builtBy = g.synthesizer; // the world is replaced now, whether or not every panel refreshes
    try {
      await onregenerated();
    } catch (err) {
      status = `✓ generated (${g.generated_ms} ms), but a panel failed to refresh: ${err.message}`;
      return;
    }
    status = `✓ updated with ${g.synthesizer} (${g.generated_ms} ms)`;
    setTimeout(() => (status = ""), 1500);
  }

  export function report(message) {
    status = message;
  }

  loadLimits();
  loadGenerators();
</script>

<div class="card">
  <div class="controls">
    <label class="ctrl">SKUs <output>{spec.n_skus}</output>
      <input type="range" min={bounds.n_skus.min} max={bounds.n_skus.max} step={STEPS.n_skus} bind:value={spec.n_skus} />
    </label>
    <label class="ctrl">Days of history <output>{spec.horizon_days}</output>
      <input type="range" min={bounds.horizon_days.min} max={bounds.horizon_days.max} step={STEPS.horizon_days} bind:value={spec.horizon_days} />
    </label>
    <label class="ctrl">Demand intensity (class-A) <output>{spec.daily_orders_per_a_sku.toFixed(1)}</output>
      <input type="range" min="1" max="16" step="0.5" bind:value={spec.daily_orders_per_a_sku} />
    </label>
    <label class="ctrl">Stockout pressure <output>{spec.stockout_pressure.toFixed(2)}</output>
      <input type="range" min="0" max="0.4" step="0.01" bind:value={spec.stockout_pressure} />
    </label>
    <label class="ctrl">Seed <output>{spec.seed}</output>
      <input type="range" min="1" max="99" step="1" bind:value={spec.seed} />
    </label>
    {#if generators.length}
      <label class="ctrl">Generator
        <select bind:value={generator}>
          {#each generators as g (g.name)}<option value={g.name} title={g.description}>{g.name}</option>{/each}
        </select>
      </label>
    {/if}
    <button class="primary" onclick={regen}>↻ Regenerate synthetic world</button>
    <span class="muted">{status}</span>
  </div>
  <div class="note">
    {#if builtBy}World built by <b>{builtBy}</b> (<a href="synthesizers.html">synthesizers</a>).{/if}
    Sliders re-drive the <code>GenerationSpec</code> (reference-dataset + generation requirements). This dashboard runs
    on seeded synthetic data; measured results on real data are in <code>docs/VALIDATION.md</code>.
  </div>
  <div class="exports">
    <span class="muted">Export synthetic CSV:</span>
    {#each EXPORTS as entity (entity)}
      <a class="button" href="{API}/export?entity={entity}" download>{entity}</a>
    {/each}
  </div>
</div>

<style>
  .controls { display: flex; gap: 18px; flex-wrap: wrap; align-items: flex-end; }
  .ctrl { display: flex; flex-direction: column; gap: 5px; min-width: 150px; font-size: 11.5px; color: var(--ink-muted); }
  output { font-size: 12px; color: var(--accent); font-variant-numeric: tabular-nums; }
  .exports { margin-top: 12px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 12px; }
</style>
