<!--
  The Effects page's "Estimate from data" view: estimators scored on the promotion
  benchmark, whose true effect is known (POST /causal/estimates). The form is built
  from GET /estimators; every estimate, interval, bias and bound comes from the
  server. The address (#estimate=) keeps the request.
-->
<script>
  import { untrack } from "svelte";

  import IntervalChart from "../../components/charts/IntervalChart.svelte";
  import LineChart from "../../components/charts/LineChart.svelte";
  import DataTable from "../../components/tables/DataTable.svelte";
  import { look, theme } from "../../components/theme.svelte.js";
  import { api } from "../../lib/api.js";
  import { CONFIDENCES, amount, intervalText, records, relativeText } from "../../lib/effects-model.js";
  import {
    SWEEP, estimateHash, estimateRequestError, estimatesLink, fitEstimateRequest, readEstimateHash,
    scoreReading, sweepRequests, sweepSeries,
  } from "../../lib/estimate-model.js";
  import { boundsText, readParam } from "../../lib/synthesis.js";

  /** @type {{active: boolean, tick: number, onaddress: (hash: string) => void}} */
  let { active, tick, onaddress } = $props();

  /** @type {any} */
  let catalog = $state(null);
  /** @type {any} */
  let form = $state(null); // {estimators, benchmark: {name: {text, bad}}, covariates, confidence}
  /** @type {{bad: boolean, lead?: string, text: string} | null} */
  let message = $state({ bad: false, text: "Choose the estimators and the adjustment set, then estimate." });
  /** @type {any} */
  let result = $state(null); // {response, request, rows}
  /** @type {any} */
  let sweep = $state(null); // {series} | {progress} | {error}
  let running = $state(false);
  let sweeping = $state(false);

  let seq = 0; // the latest estimation; an older answer is dropped
  let sweepSeq = 0;
  let written = ""; // the last #estimate= this view wrote
  let routeSeq = 0; // the latest route; one that waited on the catalogue behind a newer one stops
  /** @type {Promise<any> | null} */
  let loading = null;

  // Each estimator's colour follows its place in the catalogue, never its place on screen; past eight,
  // grey (lib/estimate-model.js estimatorColors), in the palette of the scheme shown.
  const colors = $derived.by(() => {
    const l = look(theme.scheme);
    return new Map((catalog?.estimators ?? []).map((e, i) => [e.name, i < l.series.length ? l.series[i] : l.other]));
  });

  function toForm(request) {
    return {
      estimators: [...request.estimators],
      benchmark: Object.fromEntries(catalog.benchmark.params.map(p => {
        const v = request.benchmark[p.name];
        return [p.name, { text: v == null ? "" : String(v), bad: false }];
      })),
      covariates: [...request.question.covariates],
      confidence: request.confidence,
    };
  }

  function readForm() {
    const benchmark = {};
    for (const p of catalog.benchmark.params) {
      const f = form.benchmark[p.name];
      const read = f.bad ? { error: "" } : readParam(p, f.text);
      benchmark[p.name] = read.error == null ? read.value : f.text; // an invalid text stays, so the check names it
    }
    const q = catalog.benchmark.question;
    return {
      estimators: catalog.estimators.map(e => e.name).filter(n => form.estimators.includes(n)),
      benchmark,
      question: { ...q, covariates: q.covariates.filter(c => form.covariates.includes(c)) },
      confidence: Number(form.confidence),
    };
  }

  const problem = $derived(form && catalog ? estimateRequestError(readForm(), catalog) : null);

  function loadFromAddress() {
    seq++;
    sweepSeq++;
    result = null;
    sweep = null;
    running = false;
    written = location.hash;
    const link = readEstimateHash(location.hash) ?? {};
    const { request, dropped } = fitEstimateRequest(link.request ?? null, catalog);
    form = toForm(request);
    if (link.error) {
      message = { bad: true, lead: "This link cannot be opened:", text: `${link.error}. The form shows the default estimation.` };
      return;
    }
    if (dropped.length) {
      message = { bad: true, lead: "This link names what this installation does not offer:", text: `${dropped.join(", ")}. Check the form, then estimate.` };
      return;
    }
    message = { bad: false, text: "Choose the estimators and the adjustment set, then estimate." };
    if (link.request && !estimateRequestError(readForm(), catalog)) run(); // a link reproduces its estimation
  }

  // Shown, or its address changed: load the catalogue once, then the address unless this view wrote it.
  // Only `tick` and `active` start a route: what the route reads and writes (the form, the result) is
  // untracked, or loading an address would rewrite the form, re-run this effect, and load it again.
  $effect(() => {
    tick;
    if (!active) return;
    untrack(route);
  });

  function route() {
    const mine = ++routeSeq;
    (async () => {
      if (!catalog) {
        loading ??= api("/estimators");
        let loaded;
        try {
          loaded = await loading;
        } catch (err) {
          loading = null; // a later visit tries again
          message = { bad: true, lead: "Could not load the estimators.", text: err.detail ?? err.message };
          return;
        }
        if (!catalog) catalog = loaded;
        if (mine !== routeSeq || !active) return; // a newer address took over, or the user left this view
      }
      if (location.hash === written && result) return; // the address this view wrote itself
      loadFromAddress();
    })();
  }

  async function run() {
    const request = readForm();
    if (estimateRequestError(request, catalog)) return;
    const mine = ++seq;
    sweepSeq++; // a sweep of the previous request no longer applies
    written = estimateHash(request);
    if (location.hash !== written) history.replaceState(null, "", written);
    onaddress(written);
    if (!result) message = { bad: false, text: `Estimating with ${request.estimators.length} estimators…` };
    running = true;
    try {
      const response = await api("/causal/estimates", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
      if (mine !== seq) return;
      result = { response, request, rows: records(response) };
      sweep = null;
      sweeping = false;
      message = null;
    } catch (err) {
      if (mine !== seq) return;
      result = null;
      message = { bad: true, lead: "The estimation did not run.", text: err.detail ?? err.message };
    } finally {
      if (mine === seq) running = false;
    }
  }

  async function runSweep() {
    if (!result) return;
    const mine = ++sweepSeq;
    sweeping = true;
    const results = [];
    try {
      for (const [k, request] of sweepRequests(result.request).entries()) {
        sweep = { progress: `Estimating at confounding ${SWEEP[k]} (${k + 1} of ${SWEEP.length})…` };
        const response = await api("/causal/estimates", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
        if (mine !== sweepSeq) return;
        results.push(records(response));
      }
    } catch (err) {
      if (mine === sweepSeq) sweep = { error: err.detail ?? err.message };
      return;
    } finally {
      if (mine === sweepSeq) sweeping = false;
    }
    sweep = { series: sweepSeries(results, result.request.estimators).map(s => ({ ...s, color: colors.get(s.name) })) };
  }

  function toggle(list, value, on) {
    form[list] = on ? [...form[list], value] : form[list].filter(v => v !== value);
  }

  // -- the result -------------------------------------------------------------------------------

  const perUnit = $derived.by(() => {
    const unit = result?.response.fields.find(f => f.name === "effect")?.unit;
    return unit === "units" ? " units/week" : unit ? ` ${unit}` : "";
  });
  const scored = $derived(result ? result.rows.filter(r => r.effect != null && r.ci_low != null) : []);
  const chartRows = $derived(result
    ? result.rows.filter(r => r.effect != null).map(r => ({
        label: r.estimator, estimate: r.effect, low: r.ci_low, high: r.ci_high, color: colors.get(r.estimator) ?? look(theme.scheme).other,
      }))
    : []);
  const missing = $derived(result ? result.rows.filter(r => r.effect == null) : []);

  const SCORE_FIELDS = [
    { name: "estimator", label: "Estimator", kind: "dimension" },
    { name: "effect", label: "Estimate", kind: "measure" },
    { name: "interval", label: "Interval", kind: "dimension" },
    { name: "bias", label: "Bias", kind: "measure" },
    { name: "relative_bias", label: "Relative bias", kind: "measure" },
    { name: "reading", label: "Reading", kind: "dimension" },
    { name: "seconds", label: "Run time", kind: "measure" },
    { name: "method", label: "Method", kind: "dimension" },
  ];
  const scoreRows = $derived(result ? result.rows.map(r => SCORE_FIELDS.map(f =>
    f.name === "interval" ? (r.ci_low == null ? null : intervalText(r)) : f.name === "reading" ? scoreReading(r) : r[f.name])) : []);
  const scoreFormat = {
    effect: v => amount(v, { signed: true }),
    bias: v => amount(v, { signed: true }),
    relative_bias: v => relativeText(v),
    seconds: v => (v == null ? "–" : `${v.toFixed(2)} s`),
    method: v => v ?? "",
  };
  const scoreTone = { reading: v => (v === "covers the truth" ? "good" : v === "misses the truth" || v === "error" ? "bad" : null) };
</script>

<p class="lead-text">Observed data does not come with its effects. An estimator infers one from rows, adjusting
  for the covariates you declare; if the set misses a cause of both treatment and outcome, the estimate is
  biased. The promotion benchmark knows its true effect: high-demand SKUs are promoted more often, so the naive
  difference is confounded. Compare the estimators with the truth, drop covariates to watch the bias return,
  and sweep the confounding.</p>

<section class="card" aria-label="Estimation request">
  {#if form && catalog}
    <form novalidate onsubmit={e => { e.preventDefault(); run(); }}>
      <div class="estimategrid">
        <fieldset>
          <legend>Estimators</legend>
          <div class="checks">
            {#each catalog.estimators as e (e.name)}
              {@const on = form.estimators.includes(e.name)}
              <label title={e.description}><input type="checkbox" name="estimator" value={e.name} checked={on}
                disabled={!on && form.estimators.length >= catalog.limits.max_estimators}
                onchange={ev => toggle("estimators", e.name, ev.currentTarget.checked)} />
                <span class="swatch" style:background={colors.get(e.name)}></span>{e.name}
                {#if e.origin !== "builtin"}<span class="desc">({e.origin})</span>{/if}</label>
            {/each}
          </div>
          {#if Object.keys(catalog.unavailable).length}
            <div class="hint">Unavailable: {#each Object.entries(catalog.unavailable) as [n, why], i (n)}{i ? ", " : ""}<b>{n}</b> ({why}){/each}</div>
          {/if}
        </fieldset>
        <fieldset>
          <legend>Promotion benchmark</legend>
          <div class="paramgrid">
            {#each catalog.benchmark.params as p (p.name)}
              <div class="ctrl"><label for="bench-{p.name}">{p.name}</label>
                <input id="bench-{p.name}" type="number" value={form.benchmark[p.name].text} step={p.type === "int" ? 1 : "any"}
                  min={!p.exclusive && p.min != null ? p.min : undefined} max={!p.exclusive && p.max != null ? p.max : undefined}
                  oninput={e => { form.benchmark[p.name].text = e.currentTarget.value; form.benchmark[p.name].bad = !!e.currentTarget.validity?.badInput; }} />
                <div class="hint">{boundsText(p)}</div></div>
            {/each}
          </div>
        </fieldset>
        <fieldset>
          <legend>Adjustment set</legend>
          <div class="checks">
            {#each catalog.benchmark.question.covariates as c (c)}
              <label><input type="checkbox" name="covariate" value={c} checked={form.covariates.includes(c)}
                onchange={e => toggle("covariates", c, e.currentTarget.checked)} />{c}</label>
            {/each}
          </div>
          <div class="hint">{catalog.benchmark.question.treatment} → {catalog.benchmark.question.outcome}; uncheck a covariate to leave it out</div>
        </fieldset>
        <fieldset>
          <legend>Interval</legend>
          <div class="ctrl"><label for="estimateConfidence">Confidence</label>
            <select id="estimateConfidence" bind:value={form.confidence}>
              {#each CONFIDENCES as c (c)}<option value={c}>{c * 100} %</option>{/each}
            </select></div>
          <div class="hint">At most {catalog.limits.max_estimators} estimators, {catalog.limits.max_rows.toLocaleString()} rows
            and {catalog.limits.max_seconds} s per request.</div>
        </fieldset>
      </div>
      <div class="exprun">
        <button type="submit" class="primary" disabled={!!problem || running}>Estimate</button>
        <span class="formerror" aria-live="polite">{problem ?? ""}</span>
      </div>
    </form>
  {/if}
</section>

<section class="result" class:busy={running} aria-busy={running} aria-live="polite">
  {#if message}
    <div class="notice" class:bad={message.bad}>{#if message.lead}<b>{message.lead}</b> {/if}{message.text}</div>
  {/if}
  {#if result}
    {@const r = result.response}
    {@const b = result.request.benchmark}
    <p class="headline">True effect <b>{amount(r.true_effect, { signed: true })}{perUnit}</b>:
      {scored.filter(x => x.covers === "yes").length} of {scored.length} intervals cover it.</p>
    <p class="runline">{r.data?.rows.length ?? "–"} SKUs of the current world, uplift {amount(b.uplift * 100)} %,
      confounding {b.confounding}, noise {b.noise}, seed {b.seed}; adjusting for <b>{r.question.covariates.join(", ") || "nothing"}</b>;
      {(r.elapsed_ms / 1000).toFixed(1)} s.</p>
    <div class="legend">
      <span class="item"><span class="truth"></span>true effect</span>
      <span class="item">each estimator: its estimate and {result.request.confidence * 100} % interval, in its own colour</span>
    </div>
    {#if chartRows.length}
      <IntervalChart rows={chartRows} reference={r.true_effect} format={v => amount(v, { signed: true })} />
    {/if}
    {#each missing as m (m.estimator)}
      <p class="bad small">{m.estimator}: {scoreReading(m)}{m.method ? `: ${m.method}` : ""}</p>
    {/each}
    <div class="section">
      <h3>Scores</h3>
      <DataTable fields={SCORE_FIELDS} rows={scoreRows} format={scoreFormat} tone={scoreTone} download="estimates" />
    </div>
    <div class="section">
      <h3>Bias as confounding grows</h3>
      <div class="pick">
        <button type="button" disabled={sweeping} onclick={runSweep}>Sweep confounding from {SWEEP[0]} to {SWEEP.at(-1)}</button>
        <span class="muted">{SWEEP.length} estimations with everything else as above; each estimator's bias at each step.</span>
      </div>
      {#if sweep?.progress}
        <div class="notice">{sweep.progress}</div>
      {:else if sweep?.error}
        <div class="notice bad"><b>The sweep stopped.</b> {sweep.error}</div>
      {:else if sweep?.series}
        <p class="note">Bias (estimate minus the true effect) against confounding; 0 is no bias.</p>
        <LineChart labels={SWEEP.map(c => `confounding ${c}`)} series={sweep.series} format={v => amount(v, { signed: true })} />
      {/if}
    </div>
    <div class="actions">
      <a class="button primary" href={estimatesLink(result.request, "scores")}>Open scores in Explore</a>
      <a class="button" href={estimatesLink(result.request, "data")}>Open the observed rows in Explore</a>
      <span class="muted">Explore repeats this request on the current world and opens its table to pivot.</span>
    </div>
  {/if}
</section>

<style>
  .estimategrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; }
  @media (min-width: 1100px) {
    .estimategrid { grid-template-columns: minmax(200px, 1.2fr) minmax(280px, 1.4fr) minmax(180px, 1fr) minmax(160px, .8fr); }
  }
  .paramgrid { display: grid; grid-template-columns: repeat(2, minmax(110px, 1fr)); gap: 4px 12px; }
  .paramgrid input { width: 100%; }
  .desc { color: var(--ink-muted); font-size: 11.5px; }
  .exprun { display: flex; gap: 12px; align-items: center; margin-top: 14px; flex-wrap: wrap; }
  .formerror { color: var(--bad); font-size: 12.5px; }
  .truth { width: 0; height: 12px; border-left: 1.5px dashed var(--ink); display: inline-block; }
  .small { font-size: 12.5px; margin: 2px 0; }
  .note { margin: 2px 0 8px; }
</style>
