<!--
  Rows, Columns, Values and Filters: the chips on each, drag and drop (native HTML5),
  and the menus: a chip's aggregation, time grain, moves and removal; a filter's
  values; the fields a shelf can take. Every change goes to `onview` as a new view.
-->
<script>
  import { tick } from "svelte";

  import { GRAINS, distinctValues, partLabel } from "../../lib/pivot.js";
  import { DRAG, drag, dropIndex } from "./drag.js";
  import Popover from "./Popover.svelte";
  import {
    AGG_LABEL, GRAIN_LABEL, KIND_BADGE, SHELVES, addToShelf, aggsFor, chipsFor, moveChip, removeChip,
  } from "./view.js";

  /** @type {{table: any, view: any, onview: (view: any) => void}} */
  let { table, view, onview } = $props();

  /** @type {HTMLDivElement | undefined} */
  let root = $state();
  /** @type {{kind: "chip"|"filter"|"add", shelf: string, index?: number, name?: string, anchor: HTMLElement} | null} */
  let menu = $state(null);
  /** @type {{shelf: string, index: number} | null} */
  let over = $state(null);

  // a menu belongs to the table it was opened on: a new one (another source, a link) closes it
  $effect(() => {
    void table;
    menu = null;
  });

  const TITLES = { rows: "Rows", columns: "Columns", values: "Values", filters: "Filters" };
  const fieldOf = name => table?.fields.find(f => f.name === name);
  const chips = $derived(Object.fromEntries(SHELVES.map(s => [s, table ? chipsFor(table, view, s) : []])));

  function close(refocus = false) {
    const anchor = menu?.anchor;
    menu = null;
    if (refocus && anchor?.isConnected) anchor.focus();
  }

  // Once the view changes, a filter just added opens its values, as a field dropped on Filters does.
  async function openFilter(name) {
    await tick();
    const index = Object.keys(view.filters).indexOf(name);
    const anchor = root?.querySelector(`.shelf[data-shelf="filters"] .pchip[data-index="${index}"] .main`);
    if (anchor) openMenu("filters", index, anchor);
  }

  function add(shelf, name, index = null) {
    onview(addToShelf(view, table, shelf, name, index));
    if (shelf === "filters") openFilter(name);
  }

  function move(from, i, to, index = null) {
    const name = chips[from][i]?.name;
    onview(moveChip(view, table, from, i, to, index));
    if (to === "filters" && from !== "filters" && name) openFilter(name);
  }

  // -- drag and drop --------------------------------------------------------------------------

  /** @type {{shelf: string, index: number} | null} */
  let dragging = $state(null);

  function dragChip(e, shelf, index) {
    drag.current = dragging = { shelf, index };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData(DRAG, JSON.stringify(drag.current));
    e.dataTransfer.setData("text/plain", "");
  }

  // A drag that ends anywhere (a field let go outside a shelf, say) leaves no marker behind.
  $effect(() => {
    const end = () => { dragging = null; over = null; };
    document.addEventListener("dragend", end);
    return () => document.removeEventListener("dragend", end);
  });

  function dragOver(e, shelf) {
    if (!drag.current || !table) return;
    e.preventDefault();
    over = { shelf, index: shelf === "filters" ? -1 : dropIndex(e.currentTarget, e.clientX, e.clientY) };
  }

  function dragLeave(e) {
    if (!e.currentTarget.contains(e.relatedTarget)) over = null;
  }

  function drop(e, shelf) {
    e.preventDefault();
    const index = shelf === "filters" ? null : dropIndex(e.currentTarget, e.clientX, e.clientY);
    over = null;
    const d = drag.current;
    drag.current = dragging = null;
    if (!d) return;
    if (d.field) add(shelf, d.field, index);
    else move(d.shelf, d.index, shelf, index);
  }

  // -- the chip menu ---------------------------------------------------------------------------

  function chipAction(action) {
    const { shelf, index: i } = menu;
    close();
    if (action.agg) onview({ ...view, values: view.values.map((v, k) => (k === i ? { ...v, agg: action.agg } : v)) });
    else if (action.grain) onview({ ...view, [shelf]: view[shelf].map((a, k) => (k === i ? { ...a, grain: action.grain } : a)) });
    else if (action.move) move(shelf, i, shelf, i + (action.move > 0 ? 2 : -1));
    else if (action.to) move(shelf, i, action.to);
    else if (action.remove) onview(removeChip(view, shelf, i));
    tick().then(() => /** @type {HTMLElement | null | undefined} */ (root?.querySelector(`.shelf[data-shelf="${shelf}"] .add`))?.focus());
  }

  // -- the filter menu -------------------------------------------------------------------------

  let filterQuery = $state("");
  const filterValues = $derived(menu?.kind === "filter" ? distinctValues(table, menu.name) : []);
  const kept = $derived.by(() => {
    if (menu?.kind !== "filter") return new Set();
    const f = view.filters[menu.name] ?? { exclude: [] };
    return new Set(f.include ?? filterValues.map(x => x.value).filter(x => !(f.exclude ?? []).includes(x)));
  });
  const shownValues = $derived(filterValues.filter(x => !filterQuery.trim() || partLabel(x.value).toLowerCase().includes(filterQuery.trim().toLowerCase())));

  function setKept(next) {
    const keep = filterValues.filter(x => next.has(x.value)).map(x => x.value);
    const dropped = filterValues.filter(x => !next.has(x.value)).map(x => x.value);
    onview({ ...view, filters: { ...view.filters, [menu.name]: keep.length < dropped.length ? { include: keep } : { exclude: dropped } } });
  }

  function toggleValue(value, on) {
    const next = new Set(kept);
    on ? next.add(value) : next.delete(value);
    setKept(next);
  }

  function all(on) {
    const next = new Set(kept);
    for (const x of shownValues) on ? next.add(x.value) : next.delete(x.value);
    setKept(next);
  }

  function removeFilter() {
    const name = menu.name;
    close();
    const filters = { ...view.filters };
    delete filters[name];
    onview({ ...view, filters });
  }

  // -- the add menu ----------------------------------------------------------------------------

  let addQuery = $state("");
  const eligible = $derived.by(() => {
    if (menu?.kind !== "add") return [];
    const s = addQuery.trim().toLowerCase();
    return (table?.fields ?? [])
      .filter(f => (menu.shelf === "filters" ? !(f.name in view.filters) : menu.shelf === "values" ? true : !view[menu.shelf].some(a => a.field === f.name)))
      .filter(f => !s || f.label.toLowerCase().includes(s) || f.name.includes(s));
  });

  function openAdd(shelf, anchor) {
    if (!table) return;
    addQuery = "";
    menu = { kind: "add", shelf, anchor };
  }

  function pickAdd(name) {
    const { shelf, anchor } = menu;
    close();
    add(shelf, name);
    if (shelf !== "filters") anchor.focus();
  }

  function openMenu(shelf, index, anchor) {
    filterQuery = "";
    menu = shelf === "filters" ? { kind: "filter", shelf, index, name: Object.keys(view.filters)[index], anchor } : { kind: "chip", shelf, index, anchor };
  }
</script>

<div class="shelves" bind:this={root}>
  {#each SHELVES as shelf (shelf)}
    <div class="shelf" class:over={over?.shelf === shelf} data-shelf={shelf} role="group" aria-label={TITLES[shelf]}
      ondragover={e => dragOver(e, shelf)} ondragleave={dragLeave} ondrop={e => drop(e, shelf)}>
      <span class="shelf-label">{TITLES[shelf]}</span>
      <div class="chips">
        {#each chips[shelf] as c, i (shelf + i + c.label)}
          {#if over?.shelf === shelf && over.index === i}<span class="insert"></span>{/if}
          <span class="pchip {fieldOf(c.name)?.kind ?? 'dimension'}" class:dragging={dragging?.shelf === shelf && dragging?.index === i}
            draggable="true" data-index={i} role="listitem" ondragstart={e => dragChip(e, shelf, i)} ondragend={() => (drag.current = null)}>
            <button type="button" class="main" aria-haspopup="menu" title={c.label} onclick={e => openMenu(shelf, i, e.currentTarget)}>
              {c.label}<span class="caret">▾</span></button>
            <button type="button" class="x" aria-label="Remove {c.label}" onclick={() => onview(removeChip(view, shelf, i))}>×</button>
          </span>
        {:else}
          <span class="empty-shelf">Drop a field here</span>
        {/each}
        {#if over?.shelf === shelf && over.index === chips[shelf].length && chips[shelf].length}<span class="insert"></span>{/if}
      </div>
      <button type="button" class="add" aria-label={shelf === "filters" ? "Add a filter" : `Add a field to ${TITLES[shelf]}`}
        onclick={e => openAdd(shelf, e.currentTarget)}>+</button>
    </div>
  {/each}
</div>

{#if menu?.kind === "chip" && (menu.shelf === "values" ? view.values : view[menu.shelf])[menu.index]}
  {@const list = menu.shelf === "values" ? view.values : view[menu.shelf]}
  {@const it = list[menu.index]}
  {@const f = fieldOf(it.field)}
  <Popover anchor={menu.anchor} onclose={close}>
    <div role="menu">
      {#if menu.shelf === "values"}
        <h4>Aggregation</h4>
        {#each aggsFor(f) as a (a)}
          <button type="button" class="item" role="menuitemradio" aria-checked={a === it.agg} onclick={() => chipAction({ agg: a })}>
            <span class="tick">{a === it.agg ? "✓" : ""}</span>{a === "count_distinct" ? "Distinct count" : AGG_LABEL[a]}</button>
        {/each}
      {:else if f?.kind === "time"}
        <h4>Time grain</h4>
        {#each GRAINS as g (g)}
          <button type="button" class="item" role="menuitemradio" aria-checked={g === (it.grain ?? "day")} onclick={() => chipAction({ grain: g })}>
            <span class="tick">{g === (it.grain ?? "day") ? "✓" : ""}</span>{GRAIN_LABEL[g]}</button>
        {/each}
      {/if}
      <hr />
      {#if menu.index > 0}<button type="button" class="item" onclick={() => chipAction({ move: -1 })}><span class="tick"></span>Move left</button>{/if}
      {#if menu.index < list.length - 1}<button type="button" class="item" onclick={() => chipAction({ move: 1 })}><span class="tick"></span>Move right</button>{/if}
      {#if menu.shelf === "rows"}<button type="button" class="item" onclick={() => chipAction({ to: "columns" })}><span class="tick"></span>Move to Columns</button>{/if}
      {#if menu.shelf === "columns"}<button type="button" class="item" onclick={() => chipAction({ to: "rows" })}><span class="tick"></span>Move to Rows</button>{/if}
      <button type="button" class="item" onclick={() => chipAction({ remove: true })}><span class="tick"></span>Remove</button>
    </div>
  </Popover>
{:else if menu?.kind === "filter" && menu.name in view.filters}
  {@const label = fieldOf(menu.name)?.label ?? menu.name}
  <Popover anchor={menu.anchor} onclose={close}>
    <h4>Filter · {label}</h4>
    <input type="search" placeholder="Search values" aria-label="Search values of {label}" bind:value={filterQuery} />
    <div class="row">
      <button type="button" onclick={() => all(true)}>All</button><button type="button" onclick={() => all(false)}>None</button>
      <span class="muted kept">{kept.size.toLocaleString()} of {filterValues.length.toLocaleString()} kept</span>
    </div>
    <div class="vals" role="group" aria-label="Values of {label}">
      {#each shownValues.slice(0, 500) as x (x.value)}
        <label><input type="checkbox" checked={kept.has(x.value)} onchange={e => toggleValue(x.value, e.currentTarget.checked)} />
          {partLabel(x.value)}<span class="n">{x.count.toLocaleString()}</span></label>
      {/each}
      {#if shownValues.length > 500}<div class="muted">{shownValues.length - 500} more; search to narrow</div>{/if}
    </div>
    <div class="row"><button type="button" onclick={removeFilter}>Remove filter</button></div>
  </Popover>
{:else if menu?.kind === "add"}
  <Popover anchor={menu.anchor} onclose={close}>
    <h4>Add to {menu.shelf}</h4>
    <input type="search" placeholder="Search fields" aria-label="Search fields" bind:value={addQuery}
      onkeydown={e => { if (e.key === "Enter" && eligible.length) pickAdd(eligible[0].name); }} />
    <div role="menu">
      {#each eligible as f (f.name)}
        <button type="button" class="item" onclick={() => pickAdd(f.name)}><span class="tick"></span>{f.label}<span class="unit">{KIND_BADGE[f.kind]}</span></button>
      {:else}
        <div class="muted">No field left to add.</div>
      {/each}
    </div>
  </Popover>
{/if}

<style>
  .shelves { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 700px) { .shelves { grid-template-columns: minmax(0, 1fr); } }
  .shelf {
    display: flex; align-items: center; gap: 8px; min-height: 46px; padding: 6px 8px; border: 1px dashed var(--rule);
    border-radius: 10px; background: var(--surface); min-width: 0;
  }
  .shelf.over { border-color: var(--accent); border-style: solid; }
  .shelf-label { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-muted); width: 60px; flex: none; font-weight: 600; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; min-width: 0; }
  .empty-shelf { color: var(--ink-muted); font-size: 12px; opacity: .7; }
  .add { padding: 2px 10px; border-radius: 999px; font-size: 15px; line-height: 1.4; flex: none; }
  .pchip { display: inline-flex; align-items: center; border: 1px solid var(--rule); border-radius: 999px; background: var(--surface-raised); max-width: 100%; }
  .pchip.measure { border-color: var(--accent); }
  .pchip.dragging { opacity: .4; }
  .pchip .main {
    background: none; border: 0; padding: 4px 4px 4px 11px; color: var(--ink); border-radius: 999px 0 0 999px; font-size: 12.5px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px;
  }
  .pchip .main .caret { color: var(--ink-muted); margin-left: 4px; }
  .pchip .x { background: none; border: 0; padding: 4px 9px 4px 5px; color: var(--ink-muted); border-radius: 0 999px 999px 0; font-size: 13px; }
  .pchip .x:hover { color: var(--ink); }
  .insert { width: 2px; align-self: stretch; background: var(--accent); border-radius: 1px; }
</style>
