<!--
  The Forecasts page: forecasters backtested per SKU from rolling origins, on the current
  world's demand or on the demand benchmark, whose exact distribution is known
  (POST /forecasts/backtest). The form is built from GET /forecasters; every score,
  interval and bound comes from the server. The address (#backtest=) keeps the request.
  Contract: docs/refactor/algorithms/interfaces.md §8.
-->
<script>
  import { untrack } from "svelte";

  import Nav from "../components/Nav.svelte";
  import LineChart from "../components/charts/LineChart.svelte";
  import DataTable from "../components/tables/DataTable.svelte";
  import { look, theme } from "../components/theme.svelte.js";
  import { api } from "../lib/api.js";
  import {
    LEVELS, REFERENCE, backtestBody, fitForecastRequest, forecastHash, forecastRequestError, forecastSkus, forecasterColors,
    forecastsLink, historyNeeded, historyText, levelQuantiles, readForecastHash, scoreReading, skuForecasts, tableRecords, wapeByHorizon,
  } from "../lib/forecasts-model.js";
  import { boundsText, readParam } from "../lib/synthesis.js";
  import ParamControl from "./synthesizers/ParamControl.svelte";
  import { initialEntry, rawOf } from "./synthesizers/form.js";

  /** @type {any} */
  let catalog = $state(null);
  /** @type {any} */
  let form = $state(null); // {forecasters, params: {name: {param: entry}}, source, benchmark: {name: {text, bad}}, horizon, origins, level}
  /** @type {{bad: boolean, lead?: string, text: string} | null} */
  let message = $state({ bad: false, text: "Loading the forecasters…" });
  /** @type {any} */
  let result = $state(null); // {response, request}
  let running = $state(false);
  let sku = $state("");

  let seq = 0; // the latest backtest; an older answer is dropped
  let written = ""; // the last #backtest= this page wrote

  // Each forecaster's colour follows its place in the catalogue, never its place on screen; past eight, grey.
  // The benchmark's reference is a neutral series.
  const colors = $derived.by(() => {
    const l = look(theme.scheme);
    const m = forecasterColors((catalog?.forecasters ?? []).map(f => f.name), l.series, l.other);
    m.set(REFERENCE, l.muted);
    return m;
  });

  const entryFor = (p, v) => ({ ...initialEntry(p), ...(v === undefined ? {} : { text: v == null ? "" : String(v), checked: v === true, choice: v == null ? "" : String(v), none: v === null }) });

  function toForm(request) {
    return {
      forecasters: [...request.forecasters],
      params: Object.fromEntries(catalog.forecasters.map(f => [
        f.name, Object.fromEntries(f.params.map(p => [p.name, entryFor(p, request.params[f.name]?.[p.name])])),
      ])),
      source: request.source,
      benchmark: Object.fromEntries(catalog.benchmark.params.map(p => {
        const v = request.benchmark[p.name];
        return [p.name, { text: v == null ? "" : String(v), bad: false }];
      })),
      horizon: String(request.horizon),
      origins: String(request.origins),
      level: request.level,
    };
  }

  const count = t => (t != null && String(t).trim() !== "" && Number.isFinite(Number(t)) ? Number(t) : NaN); // not a number: the check names it

  // The request the form holds; a parameter equal to its default is left out, so the link stays short.
  function readForm() {
    const params = {};
    for (const f of catalog.forecasters) {
      if (!form.forecasters.includes(f.name)) continue;
      for (const p of f.params) {
        const e = form.params[f.name][p.name];
        const read = e.bad ? { error: "" } : readParam(p, rawOf(p, e));
        const value = e.bad ? NaN : read.error == null ? read.value : rawOf(p, e); // NaN: text that is not a number
        if (value !== p.default) (params[f.name] ??= {})[p.name] = value;
      }
    }
    const benchmark = {};
    for (const p of catalog.benchmark.params) {
      const f = form.benchmark[p.name];
      const read = f.bad ? { error: "" } : readParam(p, f.text);
      benchmark[p.name] = f.bad ? NaN : read.error == null ? read.value : f.text; // NaN: text that is not a number
    }
    return {
      forecasters: catalog.forecasters.map(f => f.name).filter(n => form.forecasters.includes(n)),
      params,
      source: form.source,
      benchmark,
      horizon: count(form.horizon),
      origins: count(form.origins),
      level: Number(form.level),
    };
  }

  const problem = $derived(form && catalog ? forecastRequestError(readForm(), catalog) : null);
  // the days of history the backtest needs, once the horizon and the origins are numbers
  const needed = $derived.by(() => {
    if (!form || !catalog) return null;
    const r = readForm();
    return Number.isInteger(r.horizon) && Number.isInteger(r.origins) ? { text: historyText(r, catalog), need: historyNeeded(r, catalog) } : null;
  });

  function loadFromAddress() {
    seq++;
    result = null;
    running = false;
    written = location.hash;
    const link = readForecastHash(location.hash);
    const { request, dropped } = fitForecastRequest(link.request ?? null, catalog);
    form = toForm(request);
    if (link.error) {
      message = { bad: true, lead: "This link cannot be opened:", text: `${link.error}. The form shows the default backtest.` };
      return;
    }
    if (dropped.length) {
      message = { bad: true, lead: "This link names what this installation does not offer:", text: `${dropped.join(", ")}. Check the form, then run.` };
      return;
    }
    message = { bad: false, text: "Choose the forecasters and the data, then run the backtest." };
    if (link.request && !forecastRequestError(readForm(), catalog)) run(); // a link reproduces its backtest
  }

  async function start() {
    try {
      catalog = await api("/forecasters");
    } catch (err) {
      message = { bad: true, lead: "Could not load the forecasters.", text: err.detail ?? err.message };
      return;
    }
    untrack(loadFromAddress);
  }

  $effect(() => {
    untrack(start);
    const onhash = () => {
      if (catalog && location.hash !== written) loadFromAddress();
    };
    addEventListener("hashchange", onhash);
    return () => removeEventListener("hashchange", onhash);
  });

  async function run() {
    const request = readForm();
    if (forecastRequestError(request, catalog)) return;
    const mine = ++seq;
    written = forecastHash(request);
    if (location.hash !== written) history.replaceState(null, "", written);
    if (!result) message = { bad: false, text: `Backtesting ${request.forecasters.length} forecasters from ${request.origins} origins…` };
    running = true;
    try {
      const response = await api("/forecasts/backtest", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(backtestBody(request)),
      });
      if (mine !== seq) return;
      result = { response, request };
      const skus = forecastSkus(response);
      if (!skus.includes(sku)) sku = skus[0] ?? "";
      message = null;
    } catch (err) {
      if (mine !== seq) return;
      result = null;
      message = { bad: true, lead: "The backtest did not run.", text: err.detail ?? err.message };
    } finally {
      if (mine === seq) running = false;
    }
  }

  function toggle(name, on) {
    form.forecasters = on ? [...form.forecasters, name] : form.forecasters.filter(n => n !== name);
  }

  // -- the result -------------------------------------------------------------------------------

  const pct = v => (v == null ? "–" : `${(v * 100).toFixed(1)} %`);
  const num = v => (v == null ? "–" : v.toLocaleString(undefined, { maximumFractionDigits: 2 }));
  const secs = v => (v == null ? "–" : `${v.toFixed(2)} s`);

  // The columns a reader compares; the table's every column (the method, the error) opens in Explore.
  const SHOWN = ["forecaster", "wape", "relative_wape", "bias", "pinball", "coverage_closed", "width", "seconds"];
  const scores = $derived.by(() => {
    if (!result) return null;
    const t = result.response.scores;
    // the cells say the unit ("89.9 %", "0.09 s"), so the headers do not; the forecaster column fits the reference's label
    const shown = SHOWN.map(n => t.fields.find(f => f.name === n)).filter(Boolean)
      .map(f => ({ ...f, unit: null, ...(f.name === "forecaster" ? { minWidth: 230 } : {}) }));
    const fields = [...shown, { name: "reading", label: "Reading", kind: "dimension" }];
    const records = tableRecords(t);
    const failed = records.filter(r => r.error);
    const rows = records.map(r => fields.map(f =>
      f.name === "reading" ? scoreReading(r) : f.name === "forecaster" && r.forecaster === REFERENCE ? `${REFERENCE} (reference)` : r[f.name]));
    const format = Object.fromEntries(t.fields.map(f => [f.name, f.unit === "share" ? pct : f.unit === "s" ? secs : f.unit ? num : v => v ?? ""]));
    format.relative_wape = v => (v == null ? "–" : v.toFixed(2)); // a ratio to seasonal naive: below 1 beats it
    return { fields, rows, format, failed };
  });
  const scoreTone = { reading: v => (v === "error" || v === "not run" || v === "not finished" ? "bad" : null) };

  const byHorizon = $derived(result ? wapeByHorizon(result.response) : null);
  const skus = $derived(result ? forecastSkus(result.response) : []);
  const multiples = $derived(result && sku ? skuForecasts(result.response, sku, levelQuantiles(result.request.level)) : []);
  const levelText = $derived(result ? `${result.request.level * 100} % interval` : "");
  const shortDay = d => d.slice(5); // MM-DD: the year is in the run line
</script>

<Nav current="forecasts.html">
  <span class="badge demo">synthetic demo data</span>
</Nav>

<main class="wide">
  <p class="lead-text">A forecaster is judged on demand it has not seen: from each origin it sees only the days before,
    forecasts every SKU for the days ahead with an interval, and is scored on what happened. WAPE is the error
    as a share of demand; below 1 against seasonal naive is better than repeating last week. On the demand
    benchmark the exact distribution is known, so its row shows the best any forecaster can do.</p>

  <section class="card" aria-label="Backtest request">
    {#if form && catalog}
      <form novalidate onsubmit={e => { e.preventDefault(); run(); }}>
        <div class="forecastgrid">
          <fieldset>
            <legend>Forecasters</legend>
            <div class="checks">
              {#each catalog.forecasters as f (f.name)}
                {@const on = form.forecasters.includes(f.name)}
                <label title={f.description}><input type="checkbox" name="forecaster" value={f.name} checked={on}
                  disabled={!on && form.forecasters.length >= catalog.limits.max_forecasters}
                  onchange={ev => toggle(f.name, ev.currentTarget.checked)} />
                  <span class="swatch" style:background={colors.get(f.name)}></span>{f.name}
                  {#if f.origin !== "builtin"}<span class="desc">({f.origin})</span>{/if}</label>
              {/each}
            </div>
            {#if Object.keys(catalog.unavailable).length}
              <div class="hint">Unavailable: {#each Object.entries(catalog.unavailable) as [n, why], i (n)}{i ? ", " : ""}<b>{n}</b> ({why}){/each}</div>
            {/if}
          </fieldset>
          <fieldset>
            <legend>Data</legend>
            <div class="checks">
              <label><input type="radio" name="source" value="world" bind:group={form.source} />the current world's demand</label>
              <label><input type="radio" name="source" value="benchmark" bind:group={form.source} />the demand benchmark (its truth is known)</label>
            </div>
            {#if form.source === "benchmark"}
              <div class="paramgrid">
                {#each catalog.benchmark.params as p (p.name)}
                  <div class="ctrl"><label for="bench-{p.name}">{p.name.replaceAll("_", " ")}</label>
                    <input id="bench-{p.name}" type="number" value={form.benchmark[p.name].text} step={p.type === "int" ? 1 : "any"}
                      min={!p.exclusive && p.min != null ? p.min : undefined} max={!p.exclusive && p.max != null ? p.max : undefined}
                      oninput={e => { form.benchmark[p.name].text = e.currentTarget.value; form.benchmark[p.name].bad = !!e.currentTarget.validity?.badInput; }} />
                    <div class="hint">{[p.nullable ? "empty: none" : "", boundsText(p)].filter(Boolean).join(" · ")}</div></div>
                {/each}
              </div>
            {/if}
          </fieldset>
          <fieldset>
            <legend>Backtest</legend>
            <div class="paramgrid">
              <div class="ctrl"><label for="horizon">days ahead</label>
                <input id="horizon" type="number" step="1" min="1" max={catalog.limits.max_horizon} bind:value={form.horizon} />
                <div class="hint">from 1 to {catalog.limits.max_horizon}</div></div>
              <div class="ctrl"><label for="origins">origins</label>
                <input id="origins" type="number" step="1" min="1" max={catalog.limits.max_origins} bind:value={form.origins} />
                <div class="hint">from 1 to {catalog.limits.max_origins}, a week apart</div></div>
              <div class="ctrl"><label for="level">interval</label>
                <select id="level" bind:value={form.level}>
                  {#each LEVELS as l (l)}<option value={l}>{l * 100} %</option>{/each}
                </select></div>
            </div>
            <div class="hint">{#if needed}The history needs {needed.text} ({needed.need} days; the world has as many
              as it was generated with, 90 by default).{" "}{/if}At most {catalog.limits.max_forecasters} forecasters and {catalog.limits.max_skus} SKUs; after
              {catalog.limits.max_seconds} s, a forecaster not started is reported as not run, one still running as not finished.</div>
          </fieldset>
        </div>
        {#if catalog.forecasters.some(f => form.forecasters.includes(f.name) && f.params.length)}
          <div class="params">
            {#each catalog.forecasters.filter(f => form.forecasters.includes(f.name) && f.params.length) as f (f.name)}
              <fieldset>
                <legend><span class="swatch" style:background={colors.get(f.name)}></span>{f.name}</legend>
                <div class="paramrow">
                  {#each f.params as p (p.name)}
                    <ParamControl param={p} bind:entry={form.params[f.name][p.name]} prefix="f-{f.name}" />
                  {/each}
                </div>
              </fieldset>
            {/each}
          </div>
        {/if}
        <div class="exprun">
          <button type="submit" class="primary" disabled={!!problem || running}>Run backtest</button>
          <span class="formerror" aria-live="polite">{problem ?? ""}</span>
        </div>
      </form>
    {/if}
  </section>

  <section class="result" class:busy={running} aria-busy={running} aria-live="polite">
    {#if message}
      <div class="notice" class:bad={message.bad}>{#if message.lead}<b>{message.lead}</b>{" "}{/if}{message.text}</div>
    {/if}
    {#if result}
      {@const r = result.response}
      <p class="runline">{r.skus} SKUs of {r.source === "world" ? `the current world (${r.world})` : "the demand benchmark"};
        origins {r.origins.join(", ")}, {result.request.horizon} days ahead, {levelText}; {(r.elapsed_ms / 1000).toFixed(1)} s.</p>
      <div class="section">
        <h3>Scores</h3>
        <DataTable fields={scores.fields} rows={scores.rows} format={scores.format} tone={scoreTone} download="forecast-scores" />
        {#each scores.failed as f (f.forecaster)}
          <p class="bad small">{f.forecaster}: {f.error}</p>
        {/each}
      </div>
      <div class="section">
        <h3>WAPE by days ahead</h3>
        <p class="note">The error as a share of demand, for each day after the origin; lower is better.</p>
        <LineChart labels={byHorizon.days.map(d => `day ${d}`)} format={pct}
          series={byHorizon.series.map(s => ({ ...s, color: colors.get(s.name) }))} />
      </div>
      <div class="section">
        <h3>One SKU after the last origin</h3>
        <div class="pick">
          <label for="sku">SKU</label>
          <select id="sku" bind:value={sku}>
            {#each skus as s (s)}<option value={s}>{s}</option>{/each}
          </select>
          <span class="muted">Each forecaster's mean and {levelText}, with the demand that happened; each chart on its own scale.</span>
        </div>
        <div class="multiples">
          {#each multiples as m (m.forecaster)}
            <div class="multiple">
              <h4><span class="swatch" style:background={colors.get(m.forecaster)}></span>{m.forecaster}</h4>
              <LineChart labels={m.days.map(shortDay)} format={num} height={180}
                series={[{ name: "mean", values: m.mean, color: colors.get(m.forecaster) }, { name: "actual", values: m.actual, color: look(theme.scheme).ink }]}
                band={{ name: levelText, low: m.low, high: m.high }} />
            </div>
          {/each}
        </div>
      </div>
      <div class="actions">
        <a class="button primary" href={forecastsLink(result.request, "scores")}>Open scores in Explore</a>
        <a class="button" href={forecastsLink(result.request, "by_horizon")}>Open scores by days ahead in Explore</a>
        <a class="button" href={forecastsLink(result.request, "forecasts")}>Open the forecasts in Explore</a>
        <span class="muted">Explore repeats this backtest and opens its table to pivot.</span>
      </div>
    {/if}
  </section>
</main>

<style>
  .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--rule); margin-left: auto;
    color: var(--ink-muted); background: var(--surface-raised);
  }
  .demo { border-color: var(--warn); color: var(--warn); }
  .forecastgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; }
  .paramgrid { display: grid; grid-template-columns: repeat(2, minmax(110px, 1fr)); gap: 4px 12px; margin-top: 8px; }
  .paramgrid input, .paramgrid select { width: 100%; }
  .params {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px 18px;
    margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--rule);
  }
  .params legend { display: inline-flex; gap: 6px; align-items: center; }
  .small { font-size: 12.5px; margin: 4px 0 0; }
  .paramrow { display: flex; gap: 12px; flex-wrap: wrap; }
  .desc { color: var(--ink-muted); font-size: 11.5px; }
  .exprun { display: flex; gap: 12px; align-items: center; margin-top: 14px; flex-wrap: wrap; }
  .formerror { color: var(--bad); font-size: 12.5px; }
  .note { margin: 2px 0 8px; font-size: 12.5px; color: var(--ink-muted); }
  .multiples { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
  .multiple { min-width: 0; }
  .multiple h4 { display: flex; gap: 6px; align-items: center; margin: 0 0 4px; font-size: 12.5px; font-weight: 600; }
</style>
