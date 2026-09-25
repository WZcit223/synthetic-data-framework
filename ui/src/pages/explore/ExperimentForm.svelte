<!--
  The policy experiment request: interventions, policies and outcomes, each list
  capped at the catalogue's max_per_list. Run sends the request to `onrun` once it
  passes the endpoint's own checks.
-->
<script>
  import { untrack } from "svelte";

  import { policyRow, setKind } from "../effects/form.js";
  import { experimentError, readExperimentForm, toExperimentForm } from "./experiment.js";

  /** @type {{catalog: any, request: any, onrun: (request: any) => void}} */
  let { catalog, request, onrun } = $props();

  // the form starts from the request it is given; the page keys this component on the request,
  // so a new one (a link opened, an experiment run) starts the form again
  let form = $state(untrack(() => toExperimentForm(request, catalog)));

  /** @type {string | null} */
  let problem = $state(null);
  const max = $derived(catalog.max_per_list ?? 6);

  function toggle(list, value, on) {
    form[list] = on ? [...form[list], value] : form[list].filter(v => v !== value);
  }

  function numberField(field, e) {
    field.text = e.currentTarget.value;
    field.bad = !!e.currentTarget.validity?.badInput;
  }

  function run() {
    const body = readExperimentForm(form);
    problem = experimentError(body, catalog);
    if (!problem) onrun(body);
  }
</script>

<section class="card expform" aria-label="Experiment request">
  <form novalidate onsubmit={e => { e.preventDefault(); run(); }}>
    <div class="expgrid">
      {#snippet checks(list, name, all)}
        <div class="checks">
          {#each all as x (x)}
            {@const on = form[list].includes(x)}
            <label><input type="checkbox" {name} value={x} checked={on} disabled={!on && form[list].length >= max}
              onchange={e => toggle(list, x, e.currentTarget.checked)} />{x.replaceAll("_", " ")}</label>
          {/each}
        </div>
      {/snippet}
      <fieldset>
        <legend>Interventions</legend>
        {@render checks("interventions", "intervention", catalog.interventions)}
      </fieldset>
      <fieldset>
        <legend>Policies</legend>
        {#each form.policies as row (row.id)}
          <div class="policy">
            <div class="ctrl"><label for="exp-policy-{row.id}">Policy</label>
              <select id="exp-policy-{row.id}" class="kind-select" value={row.kind} onchange={e => setKind(row, e.currentTarget.value, catalog)}>
                {#each catalog.policies as c (c.kind)}<option>{c.kind}</option>{/each}
              </select></div>
            {#each catalog.policies.find(c => c.kind === row.kind).params as pr (pr.name)}
              <div class="ctrl"><label for="exp-policy-{row.id}-{pr.name}">{pr.name.replaceAll("_", " ")}</label>
                <input id="exp-policy-{row.id}-{pr.name}" type="number" data-param={pr.name} value={row.values[pr.name].text}
                  step={pr.type === "int" ? 1 : 0.005} min={pr.min ?? undefined} max={pr.max ?? undefined}
                  title={pr.min != null && pr.max != null ? `${pr.exclusive ? "between" : "from"} ${pr.min} ${pr.exclusive ? "and" : "to"} ${pr.max}` : ""}
                  oninput={e => numberField(row.values[pr.name], e)} /></div>
            {/each}
            <button type="button" class="remove-policy" aria-label="Remove this policy" disabled={form.policies.length <= 1}
              onclick={() => (form.policies = form.policies.filter(r => r !== row))}>×</button>
          </div>
        {/each}
        <button type="button" disabled={form.policies.length >= max}
          onclick={() => (form.policies = [...form.policies, policyRow({}, catalog)])}>+ Add policy</button>
      </fieldset>
      <fieldset>
        <legend>Outcomes</legend>
        {@render checks("outcomes", "outcome", catalog.outcomes)}
      </fieldset>
    </div>
    <div class="exprun">
      <button type="submit" class="primary">Run experiment</button>
      <span class="muted" class:bad={!!problem} aria-live="polite">{problem ?? `At most ${max} of each.`}</span>
    </div>
  </form>
</section>

<style>
  .expgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; }
  .policy { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; padding: 8px 0; border-bottom: 1px solid var(--rule); }
  .policy .ctrl { min-width: 0; margin-bottom: 0; }
  .policy select { width: 136px; }
  .policy input[type=number] { width: 76px; }
  .remove-policy { margin-left: auto; padding: 7px 11px; }
  .policy + button { margin-top: 8px; }
  .exprun { display: flex; gap: 12px; align-items: center; margin-top: 14px; }
  .bad { color: var(--bad); }
</style>
