<!-- A value per cell on the sequential ramp (interfaces.md §2.2). -->
<script>
  import { look, theme } from "../theme.svelte.js";
  import Chart from "./Chart.svelte";
  import { heatConfig } from "./config.js";

  /** @type {{cells: {row: string, column: string, value: number|null, label?: string, flag?: boolean}[],
   *   columns: string[], rows: string[], format: (v: number) => string, domain?: [number, number], height?: number}} */
  let { cells, columns, rows, format, domain, height } = $props();

  const config = $derived(heatConfig({ cells, columns, rows, format, domain }, look(theme.scheme)));
</script>

<Chart {config} height={height ?? Math.max(100, 26 * rows.length + 40)} />
