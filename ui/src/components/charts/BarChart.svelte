<!-- Bars, grouped or stacked, vertical or horizontal (interfaces.md §2.2). -->
<script>
  import { colorBook } from "../../lib/palette.js";
  import { look, theme } from "../theme.svelte.js";
  import Chart from "./Chart.svelte";
  import { barConfig } from "./config.js";

  /** @type {{series: {name: string, values: (number|null)[], color?: string}[], labels: string[],
   *   format: (v: number) => string, tickFormat?: (v: number) => string, stacked?: boolean, horizontal?: boolean, height?: number}} */
  let { series, labels, format, tickFormat, stacked = false, horizontal = false, height } = $props();

  const books = new Map();
  const config = $derived.by(() => {
    const l = look(theme.scheme);
    if (!books.has(theme.scheme)) books.set(theme.scheme, colorBook(l.series, l.other));
    return barConfig({ series, labels, format, tickFormat, stacked, horizontal }, l, books.get(theme.scheme));
  });
</script>

<Chart {config} {height} />
