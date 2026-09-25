<!--
  The Explore chart view: one chart per value (small multiples), a line over a time
  axis or bars, grouped or stacked. Series colours follow each column's key across
  redraws (a filter keeps them; a new series field or source starts them afresh), and the
  folded "Other" series is grey.
-->
<script>
  import BarChart from "../../components/charts/BarChart.svelte";
  import LineChart from "../../components/charts/LineChart.svelte";
  import { look, theme } from "../../components/theme.svelte.js";
  import { colorBook } from "../../lib/palette.js";
  import { chartModel, seriesKey } from "./chartModel.js";

  /** @type {{result: any, table: any, view: any, display: any}} */
  let { result, table, view, display } = $props();

  const books = new Map(); // one per colour scheme
  let keyed = ""; // the series key the books' colours were assigned for
  let keyedTable = null; // and the table: a new source starts the colours afresh

  const model = $derived(chartModel(result, table, view, display));

  const charts = $derived.by(() => {
    const l = look(theme.scheme);
    const key = seriesKey(view);
    if (key !== keyed || table !== keyedTable) {
      for (const b of books.values()) b.reset();
      keyed = key;
      keyedTable = table;
    }
    if (!books.has(theme.scheme)) books.set(theme.scheme, colorBook(l.series, l.other));
    const byId = books.get(theme.scheme).assign(model.ids, model.other);
    return model.charts.map(c => ({ ...c, series: c.series.map(s => ({ name: s.name, values: s.values, color: byId.get(s.id) })) }));
  });

  // Bars a label can sit under: past about 16 categories, the bars run across instead.
  const horizontal = $derived(!model.line && (charts[0]?.labels.length ?? 0) > 16);
  const barHeight = $derived(horizontal ? Math.max(220, 26 * (charts[0]?.labels.length ?? 0) + 60) : 280);
</script>

<div class="multiples">
  {#each charts as c, i (i)}
    <figure class="multiple">
      <figcaption>{c.title}</figcaption>
      {#if model.line}
        <LineChart series={c.series} labels={c.labels} format={c.format} tickFormat={c.compact} height={280} />
      {:else}
        <BarChart series={c.series} labels={c.labels} format={c.format} tickFormat={c.compact} stacked={model.stacked} {horizontal} height={barHeight} />
      {/if}
    </figure>
  {/each}
  {#if model.notes.length}<p class="chartnote">{model.notes.join(" ")}</p>{/if}
</div>

<style>
  .multiples { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
  .multiple { margin: 0; min-width: 0; }
  figcaption { font-size: 13px; font-weight: 600; margin: 0 0 6px; }
  .chartnote { font-size: 12px; color: var(--ink-muted); margin: 0; }
</style>
