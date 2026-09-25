<!-- A point with its interval per row; an optional reference line (interfaces.md §2.2). -->
<script>
  import { colorBook } from "../../lib/palette.js";
  import { look, theme } from "../theme.svelte.js";
  import Chart from "./Chart.svelte";
  import { intervalConfig } from "./config.js";

  /** @type {{rows: {label: string, estimate: number, low: number|null, high: number|null, group?: string}[],
   *   format: (v: number) => string, reference?: number|null, height?: number}} */
  let { rows, format, reference = null, height } = $props();

  const books = new Map();
  const config = $derived.by(() => {
    const l = look(theme.scheme);
    if (!books.has(theme.scheme)) books.set(theme.scheme, colorBook(l.series, l.other));
    return intervalConfig({ rows, format, reference }, l, books.get(theme.scheme));
  });
</script>

<Chart {config} height={height ?? Math.max(120, 28 * rows.length + 60)} />
