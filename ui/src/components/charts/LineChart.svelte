<!-- Lines over shared labels; gaps at null; an optional filled band (interfaces.md §2.2). -->
<script>
  import { colorBook } from "../../lib/palette.js";
  import { look, theme } from "../theme.svelte.js";
  import Chart from "./Chart.svelte";
  import { lineConfig } from "./config.js";

  /** @type {{series: {name: string, values: (number|null)[], color?: string}[], labels: string[], yLabel?: string,
   *   format: (v: number) => string, band?: {name: string, low: (number|null)[], high: (number|null)[]}, height?: number}} */
  let { series, labels, yLabel, format, band, height } = $props();

  const books = new Map();
  const config = $derived.by(() => {
    const l = look(theme.scheme);
    if (!books.has(theme.scheme)) books.set(theme.scheme, colorBook(l.series, l.other));
    return lineConfig({ series, labels, yLabel, format, band }, l, books.get(theme.scheme));
  });
</script>

<Chart {config} {height} />
