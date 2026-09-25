<!--
  The Effects page's "Simulate an action" view: choose interventions, policies,
  outcomes and replicates, run an effect study (POST /effects), and read each
  effect with its interval. The work budget shown while editing is the server's
  check_only answer; every number drawn comes from the study's tables. The
  address (#request=) keeps the request, so a link reproduces the study.
-->
<script>
  import { untrack } from "svelte";

  import IntervalChart from "../../components/charts/IntervalChart.svelte";
  import StripChart from "../../components/charts/StripChart.svelte";
  import DataTable from "../../components/tables/DataTable.svelte";
  import { look, theme } from "../../components/theme.svelte.js";
  import { api } from "../../lib/api.js";
  import {
    CONFIDENCES, COVERS, amount, budgetView, byMetric, coversZero, exploreLink, fitRequest, intervalText, nextPolicy,
    reading, readRequestHash, records, relativeText, replicateRows, requestError, requestHash, rowLabel,
  } from "../../lib/effects-model.js";
  import { policyRow, readForm, setKind, toForm } from "./form.js";

  /** @type {{active: boolean, tick: number, onaddress: (hash: string) => void}} */
  let { active, tick, onaddress } = $props();

  /** @type {any} */
  let catalog = $state(null);
  /** @type {any} */
  let form = $state(null);
  /** @type {{pending?: boolean, error?: string, answer?: any}} */
  let budget = $state({ pending: true }); // the budget line: {pending} | {error} | {answer}
  /** @type {{bad: boolean, lead?: string, text: string} | null} */
  let message = $state({ bad: false, text: "Choose the interventions and what to measure, then run the study." });
  /** @type {any} */
  let result = $state(null); // {response, request, effects, replicates}
  let metric = $state("");
  let running = $state(false);

  let budgetKey = ""; // the form's request the latest budget answer is for
  let budgetSeq = 0; // the latest budget question; an older answer is dropped
  let runSeq = 0; // the latest run; an older answer is dropped
  let loadSeq = 0; // the latest address loaded; a slower earlier one never runs
  let timer = 0;
  let written = ""; // the last #request= this view wrote
  let routeSeq = 0; // the latest route; one that waited on the catalogue behind a newer one stops
  /** @type {Promise<any> | null} */
  let catalogLoad = null;

  const max = $derived(catalog?.max_per_list ?? 0);
  const problem = $derived(form && catalog ? requestError(readForm(form), catalog) : null);
  const view = $derived(budget.answer ? budgetView(budget.answer) : null);
  const canRun = $derived(!!view && !view.over && !running && !budget.pending && !budget.error);

  // -- the budget -------------------------------------------------------------------------------

  // The server's answer to "is this within budget?", asked while the user edits (check_only).
  // Resolves to that answer, or null when the form is invalid, the request fails or a later edit superseded it.
  async function checkBudget() {
    const request = readForm(form);
    budgetKey = JSON.stringify(request);
    const seq = ++budgetSeq;
    const wrong = requestError(request, catalog);
    if (wrong) {
      budget = { error: wrong };
      return null;
    }
    budget = { pending: true };
    try {
      const answer = await api("/effects", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...request, check_only: true }) });
      if (seq !== budgetSeq) return null;
      budget = { answer };
      return answer;
    } catch (err) {
      if (seq === budgetSeq) budget = { error: err.detail ?? err.message };
      return null;
    }
  }

  // Every edit asks again after a pause; only a different request waits for a new answer.
  $effect(() => {
    if (!form || !catalog) return;
    const key = JSON.stringify(readForm(form));
    if (key === budgetKey) return;
    budgetKey = key;
    budget = { pending: true }; // Run waits for the server's answer on what the form now holds
    budgetSeq++; // an answer already in flight is for the form before this edit
    clearTimeout(timer);
    timer = setTimeout(checkBudget, 250);
  });

  // -- the run ----------------------------------------------------------------------------------

  async function run(request = readForm(form)) {
    const wrong = requestError(request, catalog);
    if (wrong) {
      budget = { error: wrong };
      return;
    }
    const seq = ++runSeq;
    written = requestHash(request);
    if (location.hash !== written) history.replaceState(null, "", written);
    onaddress(written);
    if (!result) message = { bad: false, text: `Running ${request.replicates} paired replicates…` };
    running = true;
    try {
      const response = await api("/effects", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
      if (seq !== runSeq) return;
      const effects = records(response);
      const groups = byMetric(effects);
      // the replicate view opens on the first metric with an effect distinguishable from 0
      if (!groups.some(g => g.metric === metric)) metric = (groups.find(g => g.rows.some(r => !coversZero(r))) ?? groups[0])?.metric ?? "";
      result = { response, request, effects, replicates: records(response.replicates) };
      message = null;
    } catch (err) {
      if (seq !== runSeq) return;
      result = null;
      message = { bad: true, lead: "The study did not run.", text: err.detail ?? err.message };
    } finally {
      if (seq === runSeq) running = false;
    }
  }

  // -- the address ------------------------------------------------------------------------------

  async function loadFromAddress() {
    // a new address is a new study: the previous result, and any run still in flight, no longer apply
    const load = ++loadSeq;
    written = location.hash; // the address this view now shows: going back to an earlier one reloads it
    onaddress(written || "#");
    runSeq++;
    running = false;
    result = null;
    message = { bad: false, text: "Choose the interventions and what to measure, then run the study." };
    const link = readRequestHash(location.hash);
    const { request, dropped } = fitRequest(link?.request ?? null, catalog);
    form = toForm(request, catalog);
    const answer = checkBudget();
    const asked = budgetKey; // the form as the budget question saw it
    if (link?.error) {
      message = { bad: true, lead: "This link cannot be opened:", text: `${link.error}. The form shows the default study.` };
      return;
    }
    if (dropped.length) {
      message = { bad: true, lead: "This link names what this installation does not offer:", text: `${dropped.join(", ")}. Check the form, then run the study.` };
      return;
    }
    if (!link?.request) return;
    // a link reproduces its study, once the server says it is within budget; else the budget line says why not
    const said = await answer;
    if (load !== loadSeq) return; // another address was opened meanwhile
    if (said?.within_budget && budgetKey === asked) run(readForm(form)); // unless the user edited meanwhile
    else if (said && !said.within_budget) {
      message = { bad: true, lead: "This link's study is over the work budget,", text: "so it was not run. Lower the replicates or the lists, then run it." };
    }
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
        catalogLoad ??= api("/experiments/catalog");
        let loaded;
        try {
          loaded = await catalogLoad;
        } catch (err) {
          catalogLoad = null; // a later visit tries again
          message = { bad: true, lead: "Could not load the catalogue.", text: err.detail ?? err.message };
          return;
        }
        if (!catalog) catalog = loaded;
        if (mine !== routeSeq || !active) return; // a newer address took over, or the user moved to the other view
        loadFromAddress();
      } else if (location.hash !== written) {
        loadFromAddress();
      }
    })();
  }

  // -- editing ----------------------------------------------------------------------------------

  function toggle(list, value, on) {
    form[list] = on ? [...form[list], value] : form[list].filter(v => v !== value);
  }

  function numberField(field, e) {
    field.text = e.currentTarget.value;
    field.bad = !!e.currentTarget.validity?.badInput;
  }

  // -- the result -------------------------------------------------------------------------------

  const colors = $derived.by(() => {
    const l = look(theme.scheme);
    return { shown: l.series[0], muted: l.other };
  });
  const method = $derived(result?.effects[0]?.method ?? "");
  const intervalLabel = $derived(`Interval (${method.replace(/^paired t, /, "")})`);
  const groups = $derived(result ? byMetric(result.effects) : []);
  const shownCount = $derived(result ? result.effects.filter(r => !coversZero(r)).length : 0);

  const intervalRows = rows => rows.map(r => ({
    label: rowLabel(r), estimate: r.effect, low: r.ci_low, high: r.ci_high, color: coversZero(r) ? colors.muted : colors.shown,
  }));

  const EFFECT_FIELDS = [
    { name: "metric", label: "Metric", kind: "dimension" },
    { name: "intervention", label: "Intervention", kind: "dimension" },
    { name: "policy", label: "Policy", kind: "dimension" },
    { name: "baseline", label: "Baseline mean", kind: "measure" },
    { name: "treated", label: "Treated mean", kind: "measure" },
    { name: "effect", label: "Effect", kind: "measure" },
    { name: "interval", label: "Interval", kind: "dimension" },
    { name: "relative_effect", label: "Relative change", kind: "measure" },
    { name: "reading", label: "Reading", kind: "dimension" },
  ];
  const effectTable = (rows, { withMetric = true } = {}) => {
    const fields = EFFECT_FIELDS.filter(f => withMetric || f.name !== "metric")
      .map(f => (f.name === "interval" ? { ...f, label: intervalLabel } : f));
    return {
      fields,
      rows: rows.map(r => fields.map(f => (f.name === "interval" ? intervalText(r) : f.name === "reading" ? reading(r) : r[f.name]))),
    };
  };
  const effectFormat = {
    baseline: v => amount(v),
    treated: v => amount(v),
    effect: v => amount(v, { signed: true }),
    relative_effect: v => relativeText(v),
  };
  const effectTone = { reading: v => (v === COVERS ? null : "good") };

  const strip = $derived.by(() => {
    if (!result || !metric) return [];
    return replicateRows(result.effects, result.replicates, metric).map(r => ({
      name: rowLabel(r), values: r.dots.map(d => d.difference).filter(v => v != null), mean: r.effect,
    }));
  });
</script>

<p class="lead-text">What happens if we take an action? Each intervention is compared with the baseline on
  paired replicate worlds of the dashboard's current world: every pair shares a seed, and the effect is the
  mean of the paired differences, with a confidence interval. An interval that covers 0 means the
  simulation cannot tell the effect apart from no effect.</p>

<section class="card" aria-label="Effect study request">
  {#if form && catalog}
    <form novalidate onsubmit={e => { e.preventDefault(); run(); }}>
      <div class="studygrid">
        <fieldset>
          <legend>Interventions</legend>
          <div class="checks">
            {#each catalog.interventions.filter(n => n !== "baseline") as x (x)}
              {@const on = form.interventions.includes(x)}
              <label><input type="checkbox" name="intervention" value={x} checked={on}
                disabled={!on && form.interventions.length >= max}
                onchange={e => toggle("interventions", x, e.currentTarget.checked)} />{x.replaceAll("_", " ")}</label>
            {/each}
          </div>
          <div class="hint">each compared with the baseline</div>
        </fieldset>
        <fieldset>
          <legend>Policies</legend>
          {#each form.policies as row (row.id)}
            <div class="policy">
              <div class="ctrl"><label for="policy-{row.id}">Policy</label>
                <select id="policy-{row.id}" value={row.kind} onchange={e => setKind(row, e.currentTarget.value, catalog)}>
                  {#each catalog.policies as c (c.kind)}<option>{c.kind}</option>{/each}
                </select></div>
              {#each catalog.policies.find(c => c.kind === row.kind).params as pr (pr.name)}
                <div class="ctrl"><label for="policy-{row.id}-{pr.name}">{pr.name.replaceAll("_", " ")}</label>
                  <input id="policy-{row.id}-{pr.name}" type="number" value={row.values[pr.name].text}
                    step={pr.type === "int" ? 1 : 0.005}
                    min={!pr.exclusive && pr.min != null ? pr.min : undefined} max={!pr.exclusive && pr.max != null ? pr.max : undefined}
                    oninput={e => numberField(row.values[pr.name], e)} /></div>
              {/each}
              <button type="button" class="remove" aria-label="Remove this policy" disabled={form.policies.length <= 1}
                onclick={() => (form.policies = form.policies.filter(r => r !== row))}>×</button>
            </div>
          {/each}
          <button type="button" disabled={form.policies.length >= max}
            onclick={() => (form.policies = [...form.policies, policyRow(nextPolicy(catalog, readForm(form).policies), catalog)])}>+ Add policy</button>
        </fieldset>
        <fieldset>
          <legend>Outcomes</legend>
          <div class="checks">
            {#each catalog.outcomes as x (x)}
              {@const on = form.outcomes.includes(x)}
              <label><input type="checkbox" name="outcome" value={x} checked={on}
                disabled={!on && form.outcomes.length >= max}
                onchange={e => toggle("outcomes", x, e.currentTarget.checked)} />{x.replaceAll("_", " ")}</label>
            {/each}
          </div>
        </fieldset>
        <fieldset>
          <legend>Replicates and interval</legend>
          <div class="ctrl"><label for="replicates">Replicates</label>
            <input id="replicates" type="number" min="2" max={catalog.effects.max_replicates} step="1" class="short"
              value={form.replicates.text} oninput={e => numberField(form.replicates, e)}
              aria-invalid={/^Replicates/.test(problem ?? "") ? "true" : "false"} />
            <div class="hint">from 2 to {catalog.effects.max_replicates}</div></div>
          <div class="ctrl"><label for="confidence">Confidence</label>
            <select id="confidence" class="short" bind:value={form.confidence}>
              {#each CONFIDENCES as c (c)}<option value={c}>{c * 100} %</option>{/each}
            </select></div>
        </fieldset>
      </div>
      <div class="exprun">
        <button type="submit" class="primary" disabled={!canRun}>Run study</button>
        <div class="budget" class:over={view?.over} class:error={!!budget.error} aria-live="polite">
          <div class="meter" aria-hidden="true"><span style:width={budget.pending || budget.error ? "0" : `${((view?.share ?? 0) * 100).toFixed(1)}%`}></span></div>
          <div class="btext muted">{budget.pending ? "Checking the work budget…" : budget.error ?? view?.text}</div>
        </div>
      </div>
    </form>
  {/if}
</section>

<section class="result" class:busy={running} aria-busy={running} aria-live="polite">
  {#if message}
    <div class="notice" class:bad={message.bad}>{#if message.lead}<b>{message.lead}</b> {/if}{message.text}</div>
  {/if}
  {#if result}
    {@const n = result.effects[0]?.replicates ?? result.request.replicates}
    {@const spec = result.response.spec ?? {}}
    <p class="headline"><b>{shownCount} of {result.effects.length}</b> effects are distinguishable from 0 ({method}).</p>
    <p class="runline">{n} paired replicates of the current world: <b>{spec.n_skus} SKUs × {spec.horizon_days} days</b>,
      seeds {spec.seed} to {spec.seed + n - 1}, generator <b>{result.response.synthesizer}</b>;
      {(result.response.elapsed_ms / 1000).toFixed(1)} s.</p>
    <div class="legend">
      <span class="item"><span class="swatch" style:background={colors.shown}></span>interval excludes 0</span>
      <span class="item"><span class="swatch" style:background={colors.muted}></span>interval covers 0: {COVERS}</span>
    </div>
    <div class="metrics">
      {#each groups as g (g.metric)}
        {@const table = effectTable(g.rows, { withMetric: false })}
        <section class="metric">
          <h3>{g.metric} <span class="muted">· {g.rows.filter(x => !coversZero(x)).length} of {g.rows.length} distinguishable from 0</span></h3>
          <IntervalChart rows={intervalRows(g.rows)} reference={0} format={v => amount(v)} />
          <details class="tableview"><summary>Table view</summary>
            <DataTable fields={table.fields} rows={table.rows} format={effectFormat} tone={effectTone} /></details>
        </section>
      {/each}
    </div>
    <div class="section">
      <h3>All effects</h3>
      {#if result}
        {@const table = effectTable(result.effects)}
        <DataTable fields={table.fields} rows={table.rows} format={effectFormat} tone={effectTone} download="effects" />
      {/if}
    </div>
    <div class="section">
      <h3>Paired differences per replicate</h3>
      <div class="pick"><label for="repMetric">Metric</label>
        <select id="repMetric" bind:value={metric}>{#each groups as g (g.metric)}<option>{g.metric}</option>{/each}</select></div>
      <p class="note">Each dot is one replicate: the intervention's value minus the same replicate's baseline. The tick is their mean, the effect.</p>
      <StripChart groups={strip} format={v => amount(v, { signed: true })} />
    </div>
    <div class="actions">
      <a class="button primary" href={exploreLink(result.request, "effects")}>Open effects in Explore</a>
      <a class="button" href={exploreLink(result.request, "replicates")}>Open replicate rows in Explore</a>
      <span class="muted">Explore repeats this request on the current world and opens its table to pivot.</span>
    </div>
  {/if}
</section>

<style>
  .studygrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; }
  @media (min-width: 1100px) {
    .studygrid { grid-template-columns: minmax(180px, 1fr) minmax(400px, 2fr) minmax(180px, 1fr) minmax(180px, 1fr); }
  }
  .ctrl { margin-bottom: 8px; }
  .policy { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; padding: 8px 0; border-bottom: 1px solid var(--rule); }
  .policy select { width: 136px; }
  .policy input { width: 76px; }
  .policy .ctrl { margin-bottom: 0; }
  .remove { margin-left: auto; padding: 7px 11px; }
  .short { width: 96px; }
  .exprun { display: flex; gap: 12px; align-items: center; margin-top: 14px; flex-wrap: wrap; }
  .budget { flex: 1; min-width: 260px; max-width: 720px; }
  .meter { height: 6px; border-radius: 3px; background: var(--surface-raised); border: 1px solid var(--rule); overflow: hidden; }
  .meter span { display: block; height: 100%; width: 0; background: var(--accent); transition: width .2s; }
  .over .meter span { background: var(--bad); }
  .btext { font-size: 12px; margin-top: 5px; }
  .over .btext, .error .btext { color: var(--bad); }
  .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 4px 22px; margin-top: 6px; }
  @media (max-width: 600px) { .metrics { grid-template-columns: minmax(0, 1fr); } }
  .metric { padding: 10px 0; border-top: 1px solid var(--rule); min-width: 0; }
  .metric h3 { font-size: 13px; margin: 0 0 6px; font-weight: 600; }
  .metric h3 .muted { font-weight: 500; }
  details.tableview { margin-top: 4px; font-size: 12.5px; }
  details.tableview summary { color: var(--ink-muted); cursor: pointer; width: max-content; }
  .note { margin: 2px 0 8px; }
</style>
