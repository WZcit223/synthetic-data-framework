<!--
  The Synthesizers page: the catalogue of synthesis algorithms, a run form built
  from each one's parameters, and the run's scores with real and synthetic data
  side by side. Every number comes from the API; this page only lays it out.
  The address is #<synthesizer>.
-->
<script>
  import BarChart from "../components/charts/BarChart.svelte";
  import IntervalChart from "../components/charts/IntervalChart.svelte";
  import LineChart from "../components/charts/LineChart.svelte";
  import Nav from "../components/Nav.svelte";
  import { api } from "../lib/api.js";
  import { valueFormatter } from "../lib/format.js";
  import { column, exploreLink, histogram } from "../lib/synthesis.js";
  import { initialEntry, readForm } from "./synthesizers/form.js";
  import ParamControl from "./synthesizers/ParamControl.svelte";

  const PRODUCES = { series: "Series", table: "Table", warehouse: "Warehouse" };
  const ORIGIN = { builtin: "Built-in", plugin: "Plug-in", runtime: "Registered at runtime" };
  const SERIES_WINDOW = 240; // steps of a series drawn at once; the whole run is one click away in Explore

  /** @type {any[]} */
  let catalogue = $state([]);
  let unavailable = $state({});
  /** @type {any[]} */
  let sources = $state([]);
  let loadError = $state("");
  let loaded = $state(false);
  let selected = $state("");
  let source = $state("");
  /** @type {Record<string, any>} */
  let entries = $state({});
  /** @type {Record<string, string>} */
  let errors = $state({});
  /** @type {any} */
  let run = $state(null);
  let runError = $state("");
  let running = $state(false);
  let seq = 0;

  const chosen = $derived(catalogue.find(s => s.name === selected));

  function select(name) {
    selected = name;
    seq++; // a run still in flight belongs to the previous choice
    history.replaceState(null, "", `#${encodeURIComponent(name)}`);
    const s = catalogue.find(x => x.name === name);
    entries = Object.fromEntries((s?.params ?? []).map(p => [p.name, initialEntry(p)]));
    errors = {};
    run = null;
    runError = "";
    running = false;
  }

  async function submit(e) {
    e.preventDefault();
    const form = readForm(chosen.params, entries);
    errors = form.errors;
    if (!form.ok) return;
    const body = { synthesizer: chosen.name, source, params: form.values };
    const mine = ++seq;
    running = true;
    try {
      const r = await api("/synthesis/runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      if (mine === seq) { run = r; runError = ""; }
    } catch (err) {
      if (mine === seq) { run = null; runError = err.detail ?? err.message; }
    } finally {
      if (mine === seq) running = false;
    }
  }

  const num = (v, digits) => (v == null ? "–" : Number(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }));
  const signedPct = v => (v == null ? "–" : `${v > 0 ? "+" : ""}${num(v, 1)} %`);

  // The detection test of a table run (algorithms interfaces.md §7.3): the AUC with the spread over its folds, 0.5 marked.
  const detection = $derived.by(() => {
    const m = run?.kind === "table" ? run.metrics : null;
    if (!m || !("detection_verdict" in m)) return null;
    return {
      rows: m.detection_auc == null ? [] : [{ label: run.synthesizer, estimate: m.detection_auc, low: m.detection_auc_low, high: m.detection_auc_high }],
      verdict: m.detection_verdict,
      features: m.detection_top_features,
    };
  });
  const auc = v => (v == null ? "–" : v.toFixed(2));

  const tiles = $derived.by(() => {
    if (!run) return [];
    const m = run.metrics;
    return run.kind === "series"
      ? [
          [num(m.fidelity_score, 1), "Fidelity score", "out of 100: low KS and high profile correlation"],
          [num(m.ks_statistic, 4), "KS statistic", "0 = the same distribution of values"],
          [num(m.profile_corr, 4), "Profile correlation", "1 = the same daily shape"],
          [signedPct(m.mean_delta_pct), "Mean difference", "synthetic against real"],
          [signedPct(m.std_delta_pct), "Spread difference", "standard deviation, synthetic against real"],
        ]
      : [
          [num(m.dcr_median, 4), "Median distance to closest real row", "higher = further from copying a real row"],
          [`${num(m.clone_risk_pct, 1)} %`, "Clone risk", "synthetic rows that nearly duplicate a real one"],
          [String(m.verdict ?? "–"), "Verdict", `${num(m.n_real, 0)} real and ${num(m.n_synth, 0)} synthetic rows compared`],
        ];
  });

  const seriesChart = $derived.by(() => {
    if (run?.kind !== "series") return null;
    const real = column(run.rows, run.fields, "value", "real");
    const synth = column(run.rows, run.fields, "value", "synthetic");
    const n = Math.min(SERIES_WINDOW, Math.max(real.length, synth.length));
    return {
      n,
      total: real.length,
      labels: Array.from({ length: n }, (_, i) => String(i)),
      series: [{ name: "real", values: real.slice(0, n) }, { name: "synthetic", values: synth.slice(0, n) }],
    };
  });

  const histograms = $derived.by(() => {
    if (run?.kind !== "table") return [];
    return run.fields.filter(f => f.kind === "measure").map(f => {
      const h = histogram(column(run.rows, run.fields, f.name, "real"), column(run.rows, run.fields, f.name, "synthetic"));
      return { field: f, labels: h.labels, series: [{ name: "real", values: h.real }, { name: "synthetic", values: h.synthetic }] };
    });
  });

  const used = $derived(run ? Object.entries(run.params) : []);
  const link = $derived(run ? exploreLink(run) : null);
  const sourceLabel = $derived(run ? (sources.find(x => x.id === run.source)?.label ?? run.source) : "");
  const perStep = valueFormatter({ unit: "units", agg: "mean" });
  const share = valueFormatter({ showAs: "share_of_total" });

  async function init() {
    let cat, src;
    try {
      [cat, src] = await Promise.all([api("/synthesizers"), api("/synthesis/sources")]);
    } catch (err) {
      loadError = err.detail ?? err.message;
      return;
    }
    const order = { series: 0, table: 1, warehouse: 2 };
    catalogue = cat.synthesizers.sort((a, b) => order[a.produces] - order[b.produces] || a.name.localeCompare(b.name));
    unavailable = cat.unavailable;
    sources = src.sources;
    source = sources[0]?.id ?? "";
    loaded = true;
    let wanted = "";
    try {
      wanted = decodeURIComponent(location.hash.slice(1));
    } catch {
      wanted = ""; // a malformed hash (such as "#%") preselects nothing
    }
    const first = catalogue.find(s => s.name === wanted) ?? catalogue.find(s => s.produces !== "warehouse") ?? catalogue[0];
    if (first) select(first.name);
  }

  init();
</script>

<Nav current="synthesizers.html">
  <span class="badge demo">synthetic demo data</span>
</Nav>

<main class="wide">
  <p class="lead-text">Every synthesis algorithm this installation offers, the built-ins and any installed plug-in.
    Run one on a sample of real data to see how close its output comes, then open the run in Explore.
    How to add your own is in <code>docs/PLUGINS.md</code>.</p>
  <div class="layout">
    <aside aria-label="Synthesizers">
      <div class="catalogue">
        {#each catalogue as s (s.name)}
          <button type="button" class="scard" aria-current={s.name === selected} onclick={() => select(s.name)}>
            <div class="name">{s.name}</div>
            <div class="desc">{s.description}</div>
            <div class="tags">
              <span class="tag {s.produces}">{PRODUCES[s.produces] ?? s.produces}</span>
              <span class="tag">{ORIGIN[s.origin] ?? s.origin}</span>
              {#if s.requires.length}<span class="tag" title="modules it needs">needs {s.requires.join(", ")}</span>{/if}
            </div>
          </button>
        {:else}
          {#if loaded}<div class="notice">No synthesizer is installed.</div>{/if}
        {/each}
      </div>
      {#if Object.keys(unavailable).length}
        <div class="unavail">
          <h3>Unavailable</h3>
          <ul>{#each Object.entries(unavailable) as [n, why] (n)}<li><b>{n}</b>: {why}</li>{/each}</ul>
        </div>
      {/if}
    </aside>

    <section class="card panel" aria-live="polite">
      {#if loadError}
        <div class="notice bad"><b>Could not load the synthesizers.</b> {loadError}</div>
      {:else if !chosen}
        {#if loaded}<div class="notice">Choose a synthesizer on the left.</div>{/if}
      {:else}
        <h2>{chosen.name}</h2>
        <p class="about">{chosen.description}</p>
        {#if chosen.produces === "warehouse"}
          <div class="notice">This synthesizer builds the whole warehouse world rather than a series or a table, so it is not
            scored against a sample. Choose it as the <b>Generator</b> on the <a href="index.html">Dashboard</a> to build the world with it.</div>
        {:else if !sources.length}
          <div class="notice bad">The server found no sample data to run on. Start the API from the repository folder, or set
            <code>SDF_DATA_DIR</code> to the folder that holds <code>sample_online_retail_ii.csv</code>.</div>
        {:else}
          <form class="runform" novalidate onsubmit={submit}>
            <div class="ctrl"><label for="src">Real data</label>
              <select id="src" bind:value={source}>
                {#each sources as x (x.id)}<option value={x.id}>{x.label}</option>{/each}
              </select>
              <div class="hint">fitted on, then compared with</div></div>
            {#each chosen.params as p (p.name)}
              <ParamControl param={p} bind:entry={entries[p.name]} error={errors[p.name]} />
            {/each}
            <button type="submit" class="primary go" disabled={running}>Run</button>
          </form>
          <div class="result" class:busy={running} aria-busy={running}>
            {#if runError}
              <div class="notice bad"><b>The run did not complete.</b> {runError}</div>
            {:else if run}
              <div class="runline">Run of <b>{run.synthesizer}</b> on <b>{sourceLabel}</b>{#each used as [k, v] (k)}{" · "}{k} <b>{JSON.stringify(v)}</b>{/each}</div>
              <div class="tiles">
                {#each tiles as [v, k, h] (k)}<div class="tile"><div class="v">{v}</div><div class="k">{k}</div><div class="h">{h}</div></div>{/each}
              </div>
              {#if detection}
                <div class="detection">
                  <h3>Detection test: can a classifier tell the synthetic rows from real ones?</h3>
                  {#if detection.rows.length}
                    <p class="verdict"><b>{detection.verdict}</b>: AUC {auc(detection.rows[0].estimate)}, from
                      {auc(detection.rows[0].low)} to {auc(detection.rows[0].high)} over the folds; 0.5 is a coin toss,
                      1 gives every row away.{" "}{#if detection.features}The columns that give rows away most:
                      <b>{detection.features}</b>.{:else}No column gives the rows away.{/if}</p>
                    <!-- the whole scale from below a coin toss to every row given away, so the distance to 1 shows -->
                    <IntervalChart rows={detection.rows} reference={0.5} format={auc}
                      range={[Math.min(0.4, Math.floor(detection.rows[0].low * 10) / 10), 1]} />
                  {:else}
                    <p class="verdict muted">Not measured: {detection.verdict}.</p>
                  {/if}
                </div>
              {/if}
              <div class="charts">
                {#if seriesChart}
                  <h3>Demand per step, first {seriesChart.n.toLocaleString()} of {seriesChart.total.toLocaleString()} steps</h3>
                  <LineChart labels={seriesChart.labels} series={seriesChart.series} format={perStep} height={260} />
                {:else}
                  <div class="grid-charts">
                    {#each histograms as h (h.field.name)}
                      <div>
                        <h3>{h.field.label}: share of rows per range</h3>
                        <BarChart labels={h.labels} series={h.series} format={share} height={220} />
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
              <div class="actions">
                {#if link}
                  <a class="button primary" href={link}>Open in Explore</a>
                  <span class="muted">The same run, repeated with these parameters, as a table to pivot.</span>
                {:else}
                  <span class="muted">{run.synthesizer} has no seed parameter, so its run cannot be repeated exactly and is not offered in Explore.</span>
                {/if}
              </div>
            {:else}
              <div class="notice">{chosen.produces === "series"
                ? "A series synthesizer learns the sample's hourly demand; the run scores how close its series comes (fidelity)."
                : "A table synthesizer learns the sample's order lines (quantity, price, hour, weekday); the run scores how close its rows come to real ones (privacy) and how easily a classifier tells them apart (detection)."}</div>
            {/if}
          </div>
        {/if}
      {/if}
    </section>
  </div>
</main>

<style>
  .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--rule); margin-left: auto;
    color: var(--ink-muted); background: var(--surface-raised);
  }
  .demo { border-color: var(--warn); color: var(--warn); }
  .layout { display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 14px; align-items: start; }
  @media (max-width: 900px) { .layout { grid-template-columns: minmax(0, 1fr); } }
  .catalogue { display: flex; flex-direction: column; gap: 8px; }
  .scard {
    display: block; width: 100%; text-align: left; background: var(--surface); border: 1px solid var(--rule);
    border-radius: 12px; padding: 12px 14px; color: var(--ink); cursor: pointer; font: inherit;
  }
  .scard[aria-current="true"] { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
  .scard .name, .panel h2 { font: 600 13.5px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .scard .desc { color: var(--ink-muted); font-size: 12.5px; margin-top: 4px; }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .tag { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--rule); color: var(--ink-muted); background: var(--surface-raised); }
  .unavail { margin-top: 14px; border: 1px dashed var(--rule); border-radius: 12px; padding: 10px 14px; font-size: 12.5px; }
  .unavail h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-muted); margin: 0 0 6px; }
  .unavail li { margin: 4px 0; color: var(--ink-muted); }
  .unavail b { color: var(--ink); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .panel { padding: 18px 20px; min-height: 320px; }
  .panel h2 { margin: 0; font-size: 18px; text-transform: none; letter-spacing: 0; color: var(--ink); }
  .about { color: var(--ink-muted); margin: 6px 0 14px; }
  .runform {
    display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-start; padding: 14px 0;
    border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule);
  }
  .runform select { width: 140px; }
  .go { align-self: center; margin-top: 6px; }
  .runline { margin-bottom: 10px; }
  .detection { margin-top: 14px; }
  .detection h3 { font-size: 13px; margin: 0 0 4px; font-weight: 600; }
  .verdict { font-size: 12.5px; margin: 0 0 4px; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
  .tile { background: var(--surface-raised); border: 1px solid var(--rule); border-radius: 10px; padding: 12px 14px; }
  .tile .v { font-size: 24px; font-weight: 650; letter-spacing: -.01em; }
  .tile .k { font-size: 12px; margin-top: 2px; }
  .tile .h { font-size: 11px; color: var(--ink-muted); margin-top: 2px; }
  .charts { margin-top: 14px; }
  .charts h3 { font-size: 12.5px; margin: 12px 4px 4px; font-weight: 600; }
  .grid-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 6px 18px; }
  @media (max-width: 600px) { .grid-charts { grid-template-columns: minmax(0, 1fr); } }
</style>
