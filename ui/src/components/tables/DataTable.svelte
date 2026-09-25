<!--
  One Tabulator table over the API's own table shape: `fields` and `rows` as a
  `{fields, rows}` answer carries them (interfaces.md §3.2). Every column sorts;
  `download` adds a CSV button that writes through lib/csv.js.
-->
<script>
  import { FormatModule, ResizeTableModule, SortModule, Tabulator } from "tabulator-tables";

  import { tableCsv } from "../../lib/csv.js";
  import { columns, records } from "./config.js";

  Tabulator.registerModule([FormatModule, SortModule, ResizeTableModule]);

  /** @type {{fields: {name: string, label: string, kind: string, unit?: string|null}[], rows: any[][],
   *   format?: Record<string, (v: any) => string>, tone?: Record<string, (v: any, record: any) => string|null>,
   *   sort?: {column: string, dir: "asc"|"desc"}, download?: string|false, height?: string, placeholder?: string}} */
  let { fields, rows, format = {}, tone = {}, sort, download = false, height, placeholder = "No rows." } = $props();

  /** @type {HTMLDivElement | undefined} */
  let holder = $state();
  /** @type {any} */
  let table;
  let built = false;
  /** @type {{cols: any[], data: any[]} | null} */
  let pending = null;

  const apply = ({ cols, data }) => {
    table.setColumns(cols);
    table.replaceData(data);
  };

  $effect(() => {
    const next = { cols: columns(fields, { format, tone }), data: records(fields, rows) };
    if (!holder) return;
    if (!table) {
      table = new Tabulator(holder, {
        columns: next.cols,
        data: next.data,
        layout: "fitColumns",
        height,
        placeholder,
        initialSort: sort ? [{ column: sort.column, dir: sort.dir }] : [],
        columnDefaults: { resizable: false },
      });
      table.on("tableBuilt", () => {
        built = true;
        if (pending) apply(pending);
        pending = null;
      });
    } else if (built) {
      apply(next);
    } else {
      pending = next; // the table is still being built; the newest props win
    }
  });

  $effect(() => () => {
    table?.destroy();
    table = undefined;
    built = false;
    pending = null;
  });

  function save() {
    const blob = new Blob([tableCsv(fields, rows)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${download}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

<div class="data-table">
  {#if download}
    <div class="bar"><button type="button" class="csv" onclick={save}>CSV</button></div>
  {/if}
  <div bind:this={holder}></div>
</div>

<style>
  .data-table {
    max-width: 100%;
    min-width: 0;
  }
  .bar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 6px;
  }
  .csv {
    font-size: 11px;
    padding: 2px 8px;
  }
</style>
