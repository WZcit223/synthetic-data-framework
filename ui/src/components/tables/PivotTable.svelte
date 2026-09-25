<!--
  A lib/pivot.js result on one Tabulator instance (interfaces.md §3.2): frozen row
  labels, column groups, collapsible subtotals (a data tree), the totals row as
  pivot() returned it, heat shading, and sorting that stays in the view. The
  height is bounded, so Tabulator draws only the rows in sight.
-->
<script>
  import { untrack } from "svelte";
  import {
    ColumnCalcsModule, DataTreeModule, FormatModule, FrozenColumnsModule, InteractionModule, ResizeTableModule, Tabulator,
  } from "tabulator-tables";

  import { inkOn, paletteFor } from "../../lib/palette.js";
  import { keyId } from "../../lib/pivot.js";
  import { theme } from "../theme.svelte.js";
  import { pivotConfig } from "./pivotConfig.js";

  // Interaction: header clicks (the sort); DataTree: the subtotal groups; ColumnCalcs: the totals row
  Tabulator.registerModule([FormatModule, FrozenColumnsModule, DataTreeModule, ColumnCalcsModule, InteractionModule, ResizeTableModule]);

  /** @type {{result: any, view: any, rowTitles: string[], valueTitles: string[], formats: ((v: number) => string)[],
   *   totals: boolean, heat?: boolean, collapsed: Set<string>, maxHeight?: string,
   *   onsort: (sort: {by: string, key?: any[]}) => void, ontoggle: (key: string) => void}} */
  let { result, view, rowTitles, valueTitles, formats, totals, heat = false, collapsed, maxHeight = "70vh", onsort, ontoggle } = $props();

  /** @type {HTMLDivElement | undefined} */
  let holder = $state();
  /** @type {any} */
  let table;

  const config = $derived.by(() => {
    const ramp = paletteFor(theme.scheme).HEAT;
    return pivotConfig(result, { view, rowTitles, valueTitles, formats, totals, heat, ramp, ink: inkOn });
  });

  // Built afresh for each result: its columns, tree and totals are the result's own. The collapsed
  // groups are read, not tracked: a click already folded the tree, and redrawing would lose the scroll.
  $effect(() => {
    const c = config;
    const closed = untrack(() => collapsed);
    if (!holder) return;
    table?.destroy();
    table = new Tabulator(holder, {
      columns: c.columns,
      data: c.data,
      maxHeight,
      layout: "fitDataFill",
      placeholder: "No rows.",
      columnCalcs: "table",
      dataTree: c.tree,
      dataTreeStartExpanded: row => !closed.has(keyId(row.getData()._key)),
      dataTreeChildIndent: 14,
      columnDefaults: { resizable: false, headerSort: false },
    });
    table.on("headerClick", (e, column) => {
      const field = column.getField() ?? column.getSubColumns?.()[0]?.getField();
      const s = c.sorts[field];
      if (s) onsort(s);
    });
    table.on("dataTreeRowExpanded", row => ontoggle(keyId(row.getData()._key)));
    table.on("dataTreeRowCollapsed", row => ontoggle(keyId(row.getData()._key)));
  });

  $effect(() => () => {
    table?.destroy();
    table = undefined;
  });
</script>

<div class="pivot">
  <div bind:this={holder}></div>
  {#if config.cut}
    <div class="more">Showing the first {config.cut.shown.toLocaleString()} of {config.cut.of.toLocaleString()} columns; the totals cover
      all of them, and Export CSV has every column.</div>
  {/if}
  {#if config.heatKey}
    <div class="heatkey">
      <span>{config.heatKey.label}</span><span>{config.heatKey.lo}</span>
      <span class="steps">{#each paletteFor(theme.scheme).HEAT as c (c)}<span style:background={c}></span>{/each}</span>
      <span>{config.heatKey.hi}</span>
      {#if config.heatKey.each}<span>· each value shaded on its own scale</span>{/if}
    </div>
  {/if}
</div>

<style>
  .pivot { min-width: 0; }
  .more, .heatkey { font-size: 12px; color: var(--ink-muted); padding: 8px 4px 0; }
  .heatkey { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .steps { display: inline-flex; }
  .steps span { width: 18px; height: 10px; display: inline-block; }
  .pivot :global(.tabulator-col) { cursor: default; }
  .pivot :global(.tabulator-col.sortable) { cursor: pointer; }
  .pivot :global(.tabulator-col.sortable:hover .tabulator-col-title) { color: var(--ink); }
  .pivot :global(.tabulator-row.tabulator-tree-level-0) { font-weight: 400; }
  .pivot :global(.tabulator-cell.tot), .pivot :global(.tabulator-col.tot) { border-left: 1px solid var(--rule); }
  /* Tabulator's own totals colours are !important, so the theme's must be too */
  .pivot :global(.tabulator-calcs-holder) { border-top: 1px solid var(--ink-muted); font-weight: 600; background: var(--surface-raised) !important; }
  .pivot :global(.tabulator-calcs-holder .tabulator-row) { background: var(--surface-raised) !important; color: var(--ink); }
  .pivot :global(.tabulator-calcs-holder .tabulator-frozen) { background: var(--surface-raised); }
  .pivot :global(.tabulator-frozen) { background: var(--surface); }
  .pivot :global(.tabulator-header .tabulator-frozen) { background: var(--surface); }
  .pivot :global(.tabulator-data-tree-control) { border-color: var(--ink-muted); }
</style>
