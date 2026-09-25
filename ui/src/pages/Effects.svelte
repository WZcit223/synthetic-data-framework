<!--
  The Effects page: two views on one page. The address picks the view:
  #estimate… is the estimation view, anything else the simulation. Each view
  keeps its own last address, so switching tabs returns to where it was.
-->
<script>
  import Nav from "../components/Nav.svelte";
  import { readEstimateHash } from "../lib/estimate-model.js";
  import Estimate from "./effects/Estimate.svelte";
  import Simulate from "./effects/Simulate.svelte";

  let tick = $state(0);
  let estimating = $state(readEstimateHash(location.hash) !== null);
  let simulateHref = $state("#");
  let estimateHref = $state(readEstimateHash(location.hash) !== null ? location.hash : "#estimate");

  function route() {
    estimating = readEstimateHash(location.hash) !== null;
    if (estimating) estimateHref = location.hash;
    tick++;
  }

  $effect(() => {
    addEventListener("hashchange", route);
    return () => removeEventListener("hashchange", route);
  });
</script>

<Nav current="effects.html">
  <span class="badge demo">synthetic demo data</span>
</Nav>

<main class="wide">
  <div class="viewtabs" role="tablist" aria-label="Views">
    <a role="tab" href={simulateHref} aria-selected={!estimating} aria-controls="simulateView">Simulate an action</a>
    <a role="tab" href={estimateHref} aria-selected={estimating} aria-controls="estimateView">Estimate from data</a>
  </div>
  <div id="simulateView" role="tabpanel" hidden={estimating}>
    <Simulate active={!estimating} {tick} onaddress={h => (simulateHref = h || "#")} />
  </div>
  <div id="estimateView" role="tabpanel" hidden={!estimating}>
    <Estimate active={estimating} {tick} onaddress={h => (estimateHref = h)} />
  </div>
</main>

<style>
  .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--rule); margin-left: auto;
    color: var(--ink-muted); background: var(--surface-raised);
  }
  .demo { border-color: var(--warn); color: var(--warn); }
  .viewtabs { display: flex; gap: 4px; margin: 0 0 14px; border-bottom: 1px solid var(--rule); flex-wrap: wrap; }
  .viewtabs a {
    color: var(--ink-muted); text-decoration: none; padding: 8px 14px; font-size: 13.5px; font-weight: 550;
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .viewtabs a:hover { color: var(--ink); }
  .viewtabs a[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--accent); }
</style>
