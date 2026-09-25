<!--
  One parameter's field, built from the catalogue: its type picks the control,
  its bounds the number field's limits and the hint.
-->
<script>
  import { boundsText } from "../../lib/synthesis.js";

  /** @type {{param: any, entry: {text: string, checked: boolean, choice: string, none: boolean, bad: boolean}, error?: string}} */
  let { param: p, entry = $bindable(), error = "" } = $props();

  const id = $derived(`p-${p.name}`);
  const label = $derived(p.name.replaceAll("_", " "));
  const numeric = $derived(p.type === "int" || p.type === "float");
  const hint = $derived([p.nullable && p.type !== "str" ? "empty: none" : "", boundsText(p)].filter(Boolean).join(" · "));

  function typed(e) {
    const input = e.currentTarget;
    entry.text = input.value;
    entry.bad = !!input.validity?.badInput;
  }
</script>

{#if p.type === "bool" && p.nullable}
  <!-- three states: a checkbox cannot say "none", and sending false would change the plug-in's default -->
  <div class="ctrl">
    <label for={id}>{label}</label>
    <select {id} bind:value={entry.choice} aria-invalid={error ? "true" : "false"}>
      <option value="">none</option><option value="true">true</option><option value="false">false</option>
    </select>
    <div class="hint"></div><div class="err">{error}</div>
  </div>
{:else if p.type === "bool"}
  <div class="ctrl">
    <label class="checkline"><input type="checkbox" bind:checked={entry.checked} />{p.name}</label>
    <div class="err">{error}</div>
  </div>
{:else if p.type === "str" && p.nullable}
  <!-- an empty text is a valid string, so "none" needs its own box -->
  <div class="ctrl">
    <label for={id}>{label}</label>
    <input {id} type="text" bind:value={entry.text} disabled={entry.none} aria-invalid={error ? "true" : "false"} />
    <label class="checkline hint"><input type="checkbox" bind:checked={entry.none} />none</label>
    <div class="err">{error}</div>
  </div>
{:else}
  <div class="ctrl">
    <label for={id}>{label}</label>
    <input {id} type={numeric ? "number" : "text"} value={entry.text} oninput={typed}
      step={numeric ? (p.type === "int" ? 1 : "any") : undefined}
      min={numeric && !p.exclusive && p.min != null ? p.min : undefined}
      max={numeric && !p.exclusive && p.max != null ? p.max : undefined}
      aria-invalid={error ? "true" : "false"} />
    <div class="hint">{hint}</div><div class="err">{error}</div>
  </div>
{/if}

<style>
  .ctrl { min-width: 140px; }
  input[type=number], input[type=text], select { width: 140px; }
</style>
