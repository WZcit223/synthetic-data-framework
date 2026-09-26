<!--
  The dashboard. It reaches the backend only through api() (lib/api.js) and
  computes no business number: every figure below is one the API returned.
-->
<script>
  import Nav from "../components/Nav.svelte";
  import { api } from "../lib/api.js";
  import Controls from "./dashboard/Controls.svelte";
  import Knowledge from "./dashboard/Knowledge.svelte";
  import Operations from "./dashboard/Operations.svelte";
  import Overview from "./dashboard/Overview.svelte";
  import Replenishment from "./dashboard/Replenishment.svelte";
  import Vision from "./dashboard/Vision.svelte";

  /** @type {any} */
  let d = $state({});
  let serviceLevel = $state("0.95");
  let sku = $state("");
  let detector = $state(""); // the per-SKU anomaly detector shown; the first mounted one until chosen
  /** @type {any} */
  let controls;

  const loadOverview = async () => { d.overview = await api("/overview"); };
  const loadComparison = async () => { d.comparison = await api("/replenishment/comparison?service_level=" + serviceLevel); };
  const loadPlan = async () => { d.plan = await api("/replenishment?service_level=" + serviceLevel); };
  const loadBacktest = async () => { d.backtest = await api("/backtest"); };
  const loadAnomalies = async () => { d.anomalies = await api("/demand-anomalies"); };
  const loadDetections = async () => {
    d.detectors ??= await api("/detectors");
    const names = d.detectors.detectors.map(x => x.name);
    if (!names.includes(detector)) detector = names.includes("seasonal-residual") ? "seasonal-residual" : names[0] ?? "";
    if (!detector) return;
    const asked = detector;
    let found;
    try {
      found = await api("/anomalies?detector=" + encodeURIComponent(asked));
    } catch (err) {
      found = { detector: asked, error: err.detail ?? err.message }; // shown in the panel, not left "running"
    }
    if (asked === detector) d.detections = found; // a later choice wins
  };
  const loadImpact = async () => { d.impact = await api("/economics"); };
  const loadWorkflow = async () => { d.workflow = await api("/workflow/run"); };
  const loadScenarios = async () => { d.scenarios = await api("/scenarios"); };
  const loadVision = async () => {
    const [grid, stock] = await Promise.all([api("/shelf-occupancy"), api("/stocktake")]);
    d.vision = { grid, stock };
  };
  const loadSeries = async () => {
    if (!sku) return;
    d.series = await api("/demand-series?sku_id=" + encodeURIComponent(sku));
  };
  const loadMovers = async () => {
    d.movers = await api("/top-movers?n=8");
    if (!d.movers.some(m => m.sku_id === sku)) sku = d.movers[0]?.sku_id ?? "";
    await loadSeries(); // part of the refresh, so its failure is reported and it cannot land late
  };

  function refreshAll() {
    return Promise.all([
      loadOverview(), loadComparison(), loadMovers(), loadVision(), loadBacktest(),
      loadPlan(), loadAnomalies(), loadDetections(), loadImpact(), loadWorkflow(), loadScenarios(),
    ]);
  }

  function chooseSku(next) {
    sku = next;
    loadSeries();
  }

  function chooseDetector(next) {
    detector = next;
    d.detections = null;
    loadDetections().catch(err => controls?.report("✗ could not load the detectors: " + (err.detail ?? err.message)));
  }

  function chooseServiceLevel(next) {
    serviceLevel = next;
    loadPlan();
    loadComparison();
  }

  refreshAll().catch(err => controls?.report("✗ could not load: " + err.message));
</script>

<Nav current="index.html">
  <div class="layers">
    <span class="badge">Foundation Layer</span>
    <span class="badge">Synthesis Layer</span>
    <span class="badge">Application Layer</span>
    <span class="badge demo">synthetic demo data</span>
  </div>
</Nav>

<main>
  <Controls bind:this={controls} onregenerated={refreshAll} />

  <h2>Framework capability overview <span class="muted">— for management</span></h2>
  <Overview overview={d.overview} />

  <h2>Deep dive — replenishment <span class="muted">— one policy, end to end</span></h2>
  <Replenishment
    movers={d.movers} {sku} series={d.series} comparison={d.comparison} plan={d.plan} backtest={d.backtest}
    {serviceLevel} onsku={chooseSku} onservicelevel={chooseServiceLevel} />

  <h2>Vision stocktake <span class="muted">— multimodal capability · synthetic CV signal</span></h2>
  <Vision vision={d.vision} />

  <h2>Knowledge &amp; anomalies <span class="muted">— C6 grounded Q&amp;A · C3 anomaly detection</span></h2>
  <Knowledge anomalies={d.anomalies} detectors={d.detectors} {detector} detections={d.detections} ondetector={chooseDetector} />

  <h2>Agent, economics &amp; workflow <span class="muted">— trusted agent · £ impact · DAG · what-if</span></h2>
  <Operations impact={d.impact} workflow={d.workflow} scenarios={d.scenarios} />

  <p class="note footer">
    Every rule-based stand-in above maps to a <code>#&nbsp;ALGORITHM-HOOK</code> in the source and a row in
    <code>docs/ALGORITHM_AND_DATA_CHECKLIST.md</code>. Swapping generators for SDV/CTGAN and the forecast for
    DeepAR/TFT upgrades this framework to a validated system without changing the layers or this dashboard.
  </p>
</main>

<style>
  .layers { display: flex; gap: 8px; margin-left: auto; flex-wrap: wrap; }
  .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--rule);
    color: var(--ink-muted); background: var(--surface-raised);
  }
  .demo { border-color: var(--warn); color: var(--warn); }
  .footer { margin: 26px 0 40px; }
</style>
