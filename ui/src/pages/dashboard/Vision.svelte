<!-- The shelf-occupancy heatmap and the stocktake, vision against the books. -->
<script>
  import HeatGrid from "../../components/charts/HeatGrid.svelte";
  import DataTable from "../../components/tables/DataTable.svelte";

  /** @type {{vision: {grid: any[], stock: any} | undefined}} */
  let { vision } = $props();

  const share = v => (v * 100).toFixed(0) + "%";
  const signed = v => (v > 0 ? "+" : "") + v;

  // One row per zone, one column per location position in it, in the API's order.
  const heat = $derived.by(() => {
    if (!vision) return null;
    const flagged = new Set(vision.stock.discrepancies.map(d => d.location_id));
    const rows = vision.grid.map(z => z.zone);
    const cells = vision.grid.flatMap(z =>
      z.aisles.flatMap(a => a.cells).map((c, i) => ({
        row: z.zone,
        column: String(i + 1),
        value: c.occupancy,
        flag: flagged.has(c.location_id),
        label: `${c.location_id}: occupancy ${share(c.occupancy)}, book ${c.book_units} · vision ${c.est_units}`,
      })));
    const width = Math.max(0, ...vision.grid.map(z => z.aisles.flatMap(a => a.cells).length));
    return { rows, cells, columns: Array.from({ length: width }, (_, i) => String(i + 1)) };
  });

  const FIELDS = [
    { name: "location_id", label: "Location", kind: "dimension" },
    { name: "book_units", label: "Book", kind: "measure" },
    { name: "vision_units", label: "Vision", kind: "measure" },
    { name: "diff", label: "Δ", kind: "measure" },
    { name: "direction", label: "Flag", kind: "dimension" },
  ];
  const rows = $derived((vision?.stock.discrepancies ?? []).map(d => FIELDS.map(f => d[f.name])));
  const tone = {
    diff: v => (v < 0 ? "bad" : "warn"),
    direction: v => (v === "shortage" ? "bad" : "warn"),
  };
</script>

<div class="grid two">
  <div class="card">
    <h3>Shelf-occupancy heatmap</h3>
    <div class="note top">Each square = one location, shaded by vision-estimated fill. Red ring = stocktake
      discrepancy vs book inventory.</div>
    {#if heat?.cells.length}
      <HeatGrid cells={heat.cells} rows={heat.rows} columns={heat.columns} format={share} domain={[0, 1]} />
      <div class="legend muted">
        <span>empty</span><span class="ramp"></span><span>full</span><span class="ring">discrepancy</span>
      </div>
    {:else if vision}
      <div class="muted">No vision signal.</div>
    {/if}
  </div>
  <div class="card">
    <h3>Stocktake — vision vs book <span class="pill">counting model is the ALGO-HOOK</span></h3>
    {#if vision}
      {@const s = vision.stock}
      <div class="figures">
        <div><div class="k">Match rate</div><div class="big good">{(s.match_rate * 100).toFixed(1)}%</div></div>
        <div><div class="k">Flagged</div><div class="big warn">{s.flagged}</div></div>
        <div><div class="k">Scanned</div><div class="big">{s.locations_scanned}</div></div>
        <div><div class="k">Net variance</div><div class="big" class:bad={s.net_unit_variance < 0}>{signed(s.net_unit_variance)}</div></div>
      </div>
      <DataTable fields={FIELDS} {rows} {tone} format={{ diff: signed }}
        placeholder="Vision matches the books at these settings." />
    {/if}
  </div>
</div>

<style>
  .top { margin: 0 0 10px; }
  .figures { margin-bottom: 10px; }
  .legend { display: flex; gap: 12px; align-items: center; margin-top: 10px; font-size: 11px; }
  .ramp {
    flex: 1; height: 10px; border-radius: 5px;
    background: linear-gradient(90deg, var(--heat-0), var(--heat-2), var(--heat-5));
  }
  .ring { margin-left: 12px; border: 2px solid var(--bad); border-radius: 3px; padding: 0 6px; }
</style>
