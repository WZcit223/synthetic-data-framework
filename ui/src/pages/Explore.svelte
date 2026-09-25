<!--
  The Explore page: a pivot table and chart over any source (a catalogue dataset,
  a policy experiment, a synthesizer run, an effect study, an estimation). The
  whole view (source, shelves, display) is one object, written to the #view=
  address on every change, so a link reopens exactly this view.
-->
<script>
  import { onMount } from "svelte";

  import Nav from "../components/Nav.svelte";
  import PivotTable from "../components/tables/PivotTable.svelte";
  import { api } from "../lib/api.js";
  import { valueFormatter } from "../lib/format.js";
  import { pivot, toCsv, toTable, viewError } from "../lib/pivot.js";
  import { sourceError } from "../lib/sources.js";
  import { chartPivot } from "./explore/chartModel.js";
  import ExperimentForm from "./explore/ExperimentForm.svelte";
  import { defaultExperiment } from "./explore/experiment.js";
  import { fetchSource } from "./explore/fetch.js";
  import FieldList from "./explore/FieldList.svelte";
  import PivotChart from "./explore/PivotChart.svelte";
  import Shelves from "./explore/Shelves.svelte";
  import {
    DEFAULT_DISPLAY, PRESETS, addToShelf, additive, axisLabel, describeSource, displayError, emptyView, fallbackView,
    isPreset, linkHash, nextSort, onAxis, presetKey, readLink, rowsKey, swapAxes, valueLabel,
  } from "./explore/view.js";

  /** @type {{name: string, label: string, description?: string}[]} */
  let datasets = $state([]);
  /** @type {Record<string, string>} */
  let unavailable = $state({});
  /** @type {any} */
  let catalog = $state(null); // GET /experiments/catalog, fetched when the experiment is first picked
  let catalogError = $state("");
  let picked = $state(""); // the source select's value
  /** @type {any} */
  let source = $state.raw(null); // {dataset} | {experiment} | {synthesis} | {effects|estimates: {request, table}}
  /** @type {any} */
  let table = $state.raw(null); // toTable(payload)
  /** @type {any} */
  let meta = $state.raw(null); // {title, description, world, total, truncated}
  /** @type {any} */
  let view = $state.raw(emptyView());
  /** @type {any} */
  let display = $state.raw({ ...DEFAULT_DISPLAY });
  /** @type {{title: string, detail: string} | null} */
  let failure = $state(null);
  let busy = $state(false);
  let toast = $state("");

  // keys of collapsed group rows: the table folds itself on a click, and reads this only when it is built again
  let collapsed = $state.raw(new Set());
  let seq = 0; // the latest source request; an older answer is dropped
  let written = ""; // the last #view= this page wrote
  let toastTimer = 0;

  // The last pivots of the loaded table: a display change (heatmap, totals, table or chart)
  // redraws without aggregating the rows again.
  let pivots = new Map();
  function cachedPivot(v, options = {}) {
    const key = JSON.stringify([v, options]);
    if (!pivots.has(key)) {
      if (pivots.size >= 4) pivots.delete(pivots.keys().next().value);
      pivots.set(key, pivot(table, v, options));
    }
    return pivots.get(key);
  }

  const fieldOf = name => table?.fields.find(f => f.name === name);

  // -- the result -------------------------------------------------------------------------------

  // {result} | {empty} | {error}; the chart pivots again with its own options (chartPivot)
  const outcome = $derived.by(() => {
    if (!table) return null;
    if (!view.values.length) return { empty: true };
    try {
      const result = cachedPivot(view);
      const chart = display.as === "chart" ? cachedPivot(...chartPivot(view)) : null;
      return { result, chart };
    } catch (err) {
      return { error: err.message };
    }
  });

  const presets = $derived(table ? PRESETS[presetKey(source, meta)] ?? [] : []);
  const canStack = $derived(additive(view));
  const experimentRequest = $derived(catalog ? source?.experiment ?? defaultExperiment(catalog) : null);

  const sourceTitle = $derived(picked === "experiment" && !source?.experiment ? "Policy experiment" : meta?.title ?? "");
  const sourceInfo = $derived.by(() => {
    if (picked === "experiment" && !source?.experiment) return "Choose interventions, policies and outcomes, then run the experiment.";
    if (!meta) return "";
    return [meta.description, `${meta.total.toLocaleString()} rows`, meta.world ? `world ${meta.world}` : ""].filter(Boolean).join(" · ");
  });

  // -- the address ------------------------------------------------------------------------------

  $effect(() => {
    if (!source || !table) return;
    const hash = linkHash(source, view, display);
    written = hash;
    if (location.hash !== hash) history.replaceState(null, "", hash);
  });

  function openLink() {
    const link = readLink(location.hash);
    if (!link) return false;
    if (link.error) {
      seq++;
      clear();
      fail("This link cannot be opened", link.error);
    } else {
      loadSource(link.source, { view: link.view ?? null, display: link.display ?? null });
    }
    return true;
  }

  // -- loading a source -------------------------------------------------------------------------

  function clear() {
    source = null;
    table = null;
    meta = null;
    pivots = new Map();
  }

  function fail(title, detail) {
    failure = { title, detail };
    busy = false; // a failure ends the work in progress, a cancelled request's included
  }

  const selectValue = s => (s?.dataset != null ? `dataset:${s.dataset}` : s?.experiment ? "experiment" : s?.synthesis ? "synthesis" : s?.effects ? "effects" : s?.estimates ? "estimates" : picked);

  async function loadSource(next, { view: linkView = null, display: linkDisplay = null } = {}) {
    const mine = ++seq;
    const problem = sourceError(next) ?? (linkView == null ? null : viewError(linkView)) ?? displayError(linkDisplay);
    if (problem) {
      clear();
      return fail("This link cannot be opened", problem);
    }
    busy = true;
    try {
      const { payload, meta: m } = await fetchSource(next, datasets);
      if (mine !== seq) return;
      const t = toTable(payload);
      const preset = (PRESETS[presetKey(next, m)] ?? [])[0];
      // copies: editing the view must never edit the preset or the parsed link it came from
      const v = { ...emptyView(), ...structuredClone(linkView ?? preset?.view ?? fallbackView(t)) };
      const d = { ...DEFAULT_DISPLAY, ...structuredClone(linkView ? linkDisplay : preset?.display) };
      if (linkView) {
        // a link's view must also fit this table (every field it names, grains on time fields): refuse it whole if
        // not. With no values the pivot still resolves the rows, columns and filters, so an empty view is checked too.
        try {
          pivot(t, v);
        } catch (err) {
          clear();
          return fail("This link cannot be opened", err.message);
        }
      }
      pivots = new Map();
      collapsed = new Set();
      failure = null;
      source = next;
      table = t;
      meta = m;
      view = v;
      display = d;
      picked = selectValue(next);
      if (picked === "experiment") loadCatalog();
    } catch (err) {
      if (mine !== seq) return;
      clear();
      fail(`Could not load ${describeSource(next)}`, err.detail ?? err.message);
    } finally {
      if (mine === seq) busy = false;
    }
  }

  async function loadCatalog() {
    if (catalog) return;
    try {
      catalog = await api("/experiments/catalog");
      catalogError = "";
    } catch (err) {
      catalogError = `Could not load the experiment catalogue: ${err.detail ?? err.message}`;
    }
  }

  function pickSource(value) {
    picked = value;
    if (value === "experiment") {
      seq++; // a dataset still loading must not replace the form
      busy = false; // and its request no longer counts as work in progress
      clear();
      failure = null;
      history.replaceState(null, "", location.pathname + location.search);
      loadCatalog();
    } else {
      loadSource({ dataset: value.slice("dataset:".length) });
    }
  }

  // -- changing the view ------------------------------------------------------------------------

  function setView(next) {
    // collapsed groups belong to the row fields they were collapsed under
    if (rowsKey(next) !== rowsKey(view)) collapsed = new Set();
    view = next.rows.length < 2 && next.subtotals ? { ...next, subtotals: false } : next;
  }

  const setDisplay = change => (display = { ...display, ...change });

  function applyPreset(p) {
    collapsed = new Set();
    view = { ...emptyView(), ...structuredClone(p.view) };
    display = { ...DEFAULT_DISPLAY, ...p.display };
  }

  function reset() {
    const p = presets[0];
    collapsed = new Set();
    view = { ...emptyView(), ...structuredClone(p?.view ?? fallbackView(table)) };
    display = { ...DEFAULT_DISPLAY, ...p?.display };
  }

  function pickField(name) {
    const f = fieldOf(name);
    if (!f) return;
    const shelf = f.kind === "measure" ? "values" : f.kind === "time" && view.rows.length ? "columns" : "rows";
    if (shelf !== "values" && onAxis(view, name)) return say(`${f.label} is already on Rows or Columns`);
    setView(addToShelf(view, table, shelf, name));
  }

  function toggleGroup(k) {
    collapsed.has(k) ? collapsed.delete(k) : collapsed.add(k);
  }

  // -- toolbar actions --------------------------------------------------------------------------

  function say(text) {
    toast = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = ""), 1800);
  }

  function exportCsv() {
    const result = outcome?.result;
    if (!result) return say("Nothing to export yet");
    const csv = toCsv(result, { rowFields: view.rows.map(a => axisLabel(table, a)), values: view.values.map(x => valueLabel(table, x)) });
    const name = (source?.dataset ?? "experiment").replace(/[^a-z0-9-]/gi, "-");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `${name}-pivot.csv`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(location.href);
      say("Link copied: it reopens this view");
    } catch {
      say("Copy the address bar to share this view");
    }
  }

  // -- start ------------------------------------------------------------------------------------

  onMount(() => {
    const hashchange = () => {
      if (location.hash && location.hash !== written) openLink();
    };
    addEventListener("hashchange", hashchange);
    (async () => {
      let list;
      try {
        list = await api("/datasets");
      } catch (err) {
        fail("Could not list the datasets", err.detail ?? err.message);
        return;
      }
      datasets = list.datasets;
      unavailable = list.unavailable ?? {};
      if (openLink()) return;
      const first = datasets.find(d => d.name === "order-lines") ?? datasets[0];
      if (first) loadSource({ dataset: first.name });
      else fail("No dataset is available", "The server's catalogue is empty.");
    })();
    return () => removeEventListener("hashchange", hashchange);
  });

  const formats = $derived(view.values.map(x => valueFormatter({ unit: fieldOf(x.field)?.unit, agg: x.agg, showAs: view.showAs })));
  const broken = $derived(Object.keys(unavailable));
</script>

<Nav current="explore.html">
  <span class="badge demo">synthetic demo data</span>
</Nav>

<main class="wide">
  <section class="card sourcebar" aria-label="Data source">
    <div class="ctrl">
      <label for="source">Source</label>
      <select id="source" value={picked} title={broken.length ? `Not available: ${broken.join(", ")}` : ""}
        onchange={e => pickSource(e.currentTarget.value)}>
        <optgroup label="Datasets">
          {#each datasets as d (d.name)}<option value="dataset:{d.name}">{d.label}</option>{/each}
        </optgroup>
        <optgroup label="Experiments"><option value="experiment">Policy experiment (what-if)</option></optgroup>
        <optgroup label="Synthesizers"><option value="synthesis" disabled>Synthesizer run (from the Synthesizers page)</option></optgroup>
        <optgroup label="Effects">
          <option value="effects" disabled>Effect study (from the Effects page)</option>
          <option value="estimates" disabled>Estimation (from the Effects page)</option>
        </optgroup>
      </select>
    </div>
    <div class="sourceinfo">
      <div class="sourcetitle">{sourceTitle}</div>
      <div class="muted">{sourceInfo}</div>
    </div>
    {#if presets.length}
      <div class="presets" aria-label="Preset views">
        <span class="lead">Presets</span>
        {#each presets as p (p.label)}
          <button type="button" class="preset" aria-pressed={isPreset(p, view, display)} onclick={() => applyPreset(p)}>{p.label}</button>
        {/each}
      </div>
    {/if}
  </section>

  {#if picked === "experiment"}
    {#if catalog}
      {#key experimentRequest}
        <ExperimentForm {catalog} request={experimentRequest} onrun={body => loadSource({ experiment: body })} />
      {/key}
    {:else if catalogError}
      <div class="notice bad">{catalogError}</div>
    {/if}
  {/if}

  <div class="workspace">
    <FieldList {table} {view} onpick={pickField} />

    <section class="canvas" aria-label="Pivot">
      <Shelves {table} {view} onview={setView} />

      <div class="toolbar" role="toolbar" aria-label="View">
        <div class="seg" role="group" aria-label="Display">
          <button type="button" aria-pressed={display.as === "table"} onclick={() => setDisplay({ as: "table" })}>Table</button>
          <button type="button" aria-pressed={display.as === "chart"} onclick={() => setDisplay({ as: "chart" })}>Chart</button>
        </div>
        <label class="toggle">Show values as
          <select value={view.showAs} onchange={e => setView({ ...view, showAs: e.currentTarget.value })}>
            <option value="value">Value</option>
            <option value="share_of_total">Share of total</option>
            <option value="share_of_row">Share of row</option>
            <option value="share_of_column">Share of column</option>
          </select>
        </label>
        <label class="toggle" title={view.rows.length < 2 ? "Subtotals need two or more row fields" : ""}>
          <input type="checkbox" checked={!!view.subtotals} disabled={view.rows.length < 2}
            onchange={e => setView({ ...view, subtotals: e.currentTarget.checked })} /> Subtotals</label>
        <label class="toggle"><input type="checkbox" checked={display.totals} onchange={e => setDisplay({ totals: e.currentTarget.checked })} /> Totals</label>
        {#if display.as === "table"}
          <label class="toggle"><input type="checkbox" checked={display.heatmap} onchange={e => setDisplay({ heatmap: e.currentTarget.checked })} /> Heatmap</label>
        {:else}
          <label class="toggle" title={canStack ? "" : "Stacking needs values that add up: sums or counts, not averages or column shares"}>
            <input type="checkbox" checked={display.stacked && canStack} disabled={!canStack}
              onchange={e => setDisplay({ stacked: e.currentTarget.checked })} /> Stacked</label>
        {/if}
        <span class="spacer"></span>
        <button type="button" title="Swap rows and columns" disabled={!table} onclick={() => setView(swapAxes(view))}>⇄ Swap</button>
        <button type="button" disabled={!table} onclick={exportCsv}>Export CSV</button>
        <button type="button" disabled={!table} onclick={copyLink}>Copy link</button>
        <button type="button" disabled={!table} onclick={reset}>Reset</button>
      </div>

      <div class="card result" class:busy class:chart={display.as === "chart"} aria-busy={busy} aria-live="polite">
        {#if failure}
          <div class="failure"><b>{failure.title}</b><div>{failure.detail}</div></div>
        {:else if picked === "experiment" && !source?.experiment}
          <div class="empty"><b>Run an experiment</b>Choose interventions, policies and outcomes above, then press Run experiment.</div>
        {:else if !outcome}
          <div class="empty">Loading…</div>
        {:else if outcome.empty}
          <div class="empty"><b>Add a value</b>Drag a measure onto Values, or pick a preset above.</div>
        {:else if outcome.error}
          <div class="failure"><b>This view does not fit the data</b><div>{outcome.error}</div></div>
        {:else if display.as === "chart"}
          <PivotChart result={outcome.chart} {table} {view} {display} />
        {:else}
          <PivotTable result={outcome.result} {view} rowTitles={view.rows.map(a => axisLabel(table, a))}
            valueTitles={view.values.map(x => valueLabel(table, x))} {formats} totals={display.totals} heat={display.heatmap}
            {collapsed} onsort={s => setView({ ...view, sort: nextSort(view.sort, s.by, s.key) })} ontoggle={toggleGroup} />
        {/if}
      </div>
      <div class="statusline">
        {#if outcome?.result && !failure}
          {@const s = outcome.result.stats}
          <span>{s.rowsIn.toLocaleString()} rows read</span><span>{s.rowsUsed.toLocaleString()} after filters</span>
          <span>{s.groups.toLocaleString()} groups</span><span>{s.ms} ms</span>
        {/if}
        {#if meta?.truncated && table && !failure}
          <span class="warn">⚠ the server sent the first {table.rows.length.toLocaleString()} of {meta.total.toLocaleString()} rows; totals cover those rows only</span>
        {/if}
      </div>
    </section>
  </div>
</main>

{#if toast}<div class="toast" role="status">{toast}</div>{/if}

<style>
  .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--rule); margin-left: auto;
    color: var(--ink-muted); background: var(--surface-raised);
  }
  .demo { border-color: var(--warn); color: var(--warn); }
  .sourcebar { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
  .sourcebar .ctrl { margin-bottom: 0; }
  .sourcebar select { min-width: 240px; max-width: 100%; }
  .sourceinfo { flex: 1; min-width: 240px; }
  .sourcetitle { font-weight: 650; }
  .sourceinfo .muted { font-size: 12.5px; }
  .presets { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .presets .lead { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-muted); margin-right: 2px; }
  .preset { font-size: 12px; padding: 5px 10px; border-radius: 999px; }
  .preset[aria-pressed="true"] { border-color: var(--accent); color: var(--ink); background: var(--surface-raised); box-shadow: inset 0 0 0 1px var(--accent); }
  .workspace { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 14px; margin-top: 14px; align-items: start; }
  @media (max-width: 900px) { .workspace { grid-template-columns: minmax(0, 1fr); } }
  .canvas { min-width: 0; }
  .toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 12px 0; }
  .toolbar button, .toolbar select { padding: 6px 11px; font-size: 12.5px; }
  .spacer { flex: 1; }
  .seg { display: inline-flex; border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; background: var(--surface-raised); }
  .seg button + button { border-left: 1px solid var(--rule); }
  .seg button[aria-pressed="true"] { background: var(--accent); color: #fff; font-weight: 600; }
  .toggle { display: inline-flex; gap: 6px; align-items: center; font-size: 12.5px; color: var(--ink-muted); }
  .result { padding: 0; overflow: hidden; position: relative; min-height: 220px; }
  .result.chart { padding: 12px 16px; }
  .empty { padding: 56px 24px; text-align: center; color: var(--ink-muted); }
  .empty b { color: var(--ink); display: block; font-size: 15px; margin-bottom: 6px; }
  .failure { padding: 24px; border-left: 3px solid var(--bad); }
  .failure b { color: var(--bad); }
  .statusline { font-size: 12px; color: var(--ink-muted); margin-top: 8px; font-variant-numeric: tabular-nums; display: flex; gap: 14px; flex-wrap: wrap; }
  .statusline .warn { color: var(--warn); }
  .toast {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); background: var(--surface-raised);
    border: 1px solid var(--rule); padding: 8px 14px; border-radius: 8px; font-size: 13px; z-index: 70;
  }
</style>
