<!-- Jittered points per group with the group's mean, as given (interfaces.md §2.2). -->
<script>
  import { colorBook } from "../../lib/palette.js";
  import { look, theme } from "../theme.svelte.js";
  import Chart from "./Chart.svelte";
  import { stripConfig } from "./config.js";

  /** @type {{groups: {name: string, values: number[], mean: number}[], format: (v: number) => string, height?: number}} */
  let { groups, format, height } = $props();

  const books = new Map();
  const config = $derived.by(() => {
    const l = look(theme.scheme);
    if (!books.has(theme.scheme)) books.set(theme.scheme, colorBook(l.series, l.other));
    return stripConfig({ groups, format }, l, books.get(theme.scheme));
  });
</script>

<Chart {config} height={height ?? Math.max(120, 36 * groups.length + 60)} />
