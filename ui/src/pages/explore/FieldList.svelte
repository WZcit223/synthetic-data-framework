<!--
  The loaded table's fields, grouped by kind. A field is dragged onto a shelf, or
  clicked (or Enter) to go where it fits.
-->
<script>
  import { DRAG, drag } from "./drag.js";
  import { KIND_BADGE, KIND_GROUP, used } from "./view.js";

  /** @type {{table: any, view: any, onpick: (name: string) => void}} */
  let { table, view, onpick } = $props();

  let q = $state("");

  const groups = $derived.by(() => {
    const s = q.trim().toLowerCase();
    const all = table?.fields ?? [];
    return KIND_GROUP.map(([kind, title]) => ({
      kind, title, fields: all.filter(f => f.kind === kind && (!s || f.label.toLowerCase().includes(s) || f.name.includes(s))),
    })).filter(g => g.fields.length);
  });

  function start(e, name) {
    drag.current = { field: name };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData(DRAG, JSON.stringify(drag.current));
    e.dataTransfer.setData("text/plain", name);
  }
</script>

<aside class="card fieldlist" aria-label="Fields">
  <input type="search" bind:value={q} placeholder="Search fields" aria-label="Search fields" />
  {#each groups as g (g.kind)}
    <div class="fgroup">
      <h3>{g.title}</h3>
      {#each g.fields as f (f.name)}
        <button type="button" class="field" class:used={used(view, f.name)} draggable="true" title={f.name} data-field={f.name}
          ondragstart={e => start(e, f.name)} ondragend={() => (drag.current = null)} onclick={() => onpick(f.name)}>
          <span class="kind {g.kind}">{KIND_BADGE[g.kind]}</span><span class="name">{f.label}</span>
          {#if f.unit}<span class="unit">{f.unit}</span>{/if}
        </button>
      {/each}
    </div>
  {:else}
    <p class="muted">{table?.fields.length ? "No field matches." : "No data loaded."}</p>
  {/each}
  <p class="note">Drag a field onto a shelf, or press Enter on it to add it where it fits.</p>
</aside>

<style>
  .fieldlist { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow: auto; padding: 12px; }
  @media (max-width: 900px) { .fieldlist { position: static; max-height: 280px; } }
  .fieldlist input[type=search] { width: 100%; }
  .fgroup h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-muted); margin: 14px 0 4px; font-weight: 600; }
  .field {
    display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border-radius: 6px; background: none;
    border: 1px solid transparent; color: var(--ink); text-align: left; font-size: 13px; cursor: grab;
  }
  .field:hover, .field:focus-visible { background: var(--surface-raised); border-color: var(--rule); }
  .field .unit { margin-left: auto; font-size: 11px; color: var(--ink-muted); }
  .field.used .name { color: var(--ink-muted); }
  .kind {
    font: 600 10px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; padding: 3px 0; border-radius: 4px;
    border: 1px solid var(--rule); color: var(--ink-muted); width: 34px; text-align: center; flex: none;
  }
  .kind.measure { color: var(--accent); }
</style>
