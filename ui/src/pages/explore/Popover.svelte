<!--
  A menu under (or above) its anchor, closed by Escape or a press outside it.
  Its content is the children; the arrow keys move between its buttons and inputs.
-->
<script>
  import { tick } from "svelte";

  /** @type {{anchor: HTMLElement, onclose: (refocus?: boolean) => void, children: import("svelte").Snippet}} */
  let { anchor, onclose, children } = $props();

  /** @type {HTMLDivElement | undefined} */
  let pop = $state();
  let left = $state(0);
  let top = $state(0);

  $effect(() => {
    if (!pop || !anchor) return;
    const r = anchor.getBoundingClientRect();
    const w = pop.offsetWidth, h = pop.offsetHeight;
    left = Math.max(8, Math.min(innerWidth - w - 8, r.left));
    top = r.bottom + 6 + h > innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6;
    tick().then(() => /** @type {HTMLElement | null | undefined} */ (pop?.querySelector("input[type=search]") ?? pop?.querySelector("button, input"))?.focus());
  });

  $effect(() => {
    const down = e => {
      if (!pop?.contains(e.target) && !anchor.contains(e.target)) onclose();
    };
    const key = e => {
      if (e.key === "Escape") return onclose(true);
      if ((e.key === "ArrowDown" || e.key === "ArrowUp") && pop?.contains(e.target)) {
        const items = /** @type {HTMLElement[]} */ ([...pop.querySelectorAll("button.item, input")]);
        const i = items.indexOf(/** @type {HTMLElement} */ (document.activeElement));
        if (i < 0) return;
        e.preventDefault();
        items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
      }
    };
    document.addEventListener("pointerdown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("keydown", key);
    };
  });
</script>

<div class="popover" bind:this={pop} style:left="{left}px" style:top="{top}px">
  {@render children()}
</div>

<style>
  .popover {
    position: fixed; z-index: 50; min-width: 200px; max-width: min(320px, calc(100vw - 16px)); max-height: 60vh; overflow: auto;
    background: var(--surface-raised); border: 1px solid var(--rule); border-radius: 10px; padding: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, .25); font-size: 13px;
  }
  .popover :global(h4) { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-muted); margin: 6px 8px 4px; }
  .popover :global(hr) { border: 0; border-top: 1px solid var(--rule); margin: 6px 0; }
  .popover :global(.item) {
    display: flex; gap: 8px; align-items: center; width: 100%; text-align: left; background: none; border: 0;
    padding: 6px 10px; color: var(--ink); border-radius: 6px; font-size: 13px;
  }
  .popover :global(.item:hover), .popover :global(.item:focus-visible) { background: var(--surface); outline: none; }
  .popover :global(.item .tick) { width: 14px; color: var(--accent); font-weight: 700; }
  .popover :global(.item .unit) { margin-left: auto; color: var(--ink-muted); font-size: 11px; }
  .popover :global(input[type=search]) { width: 100%; margin: 4px 0; }
  .popover :global(.row) { display: flex; gap: 6px; align-items: center; padding: 4px 2px; }
  .popover :global(.row button) { padding: 4px 10px; font-size: 12px; }
  .popover :global(.vals) { display: flex; flex-direction: column; max-height: 260px; overflow: auto; }
  .popover :global(.vals label) { display: flex; gap: 8px; align-items: center; padding: 3px 6px; }
  .popover :global(.vals .n) { margin-left: auto; color: var(--ink-muted); font-size: 11px; }
</style>
