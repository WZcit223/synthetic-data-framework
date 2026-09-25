<!--
  One Chart.js instance on a canvas: created when the component mounts, given the
  new configuration whenever `config` changes, destroyed when it leaves the page.
  The chart components build `config` (config.js) and render this.
-->
<script>
  import { Chart } from "./chartjs.js";

  /** @type {{config: any, height?: number}} */
  let { config, height = 220 } = $props();

  /** @type {HTMLCanvasElement | undefined} */
  let canvas = $state();
  /** @type {any} */
  let chart;

  $effect(() => {
    const next = config;
    if (!canvas) return;
    if (!chart) {
      chart = new Chart(canvas, next);
    } else {
      chart.data = next.data;
      chart.options = next.options;
      chart.update("none");
    }
  });

  $effect(() => () => {
    chart?.destroy();
    chart = undefined;
  });
</script>

<div class="chart" style:height="{height}px">
  <canvas bind:this={canvas}></canvas>
</div>

<style>
  .chart {
    position: relative;
    width: 100%;
    min-width: 0;
  }
</style>
