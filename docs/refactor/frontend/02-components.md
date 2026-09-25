# F2 — Chart and table components, themes, page tests; the dashboard on them

> Status: implemented in this PR (F2).

Contract: [`interfaces.md`](interfaces.md) §2, §3, §4, §5.2 and §5.3.

## Goal

The shared components exist and are proven on the simplest page: the dashboard
is a Svelte page whose charts are Chart.js and whose tables are Tabulator.

## Scope

- **Charts:** `LineChart`, `BarChart`, `IntervalChart`, `StripChart`,
  `HeatGrid` (§2.2), registered once with only the Chart.js parts they use.
- **Tables:** `DataTable` (§3.2), and `lib/csv.js` with `csvCell` moved out of
  `pivot.js` and the flat writer `tableCsv`.
- **Theme:** `theme.css` with the light and dark sets; `palette.js` with a set
  per theme; today's palette tests unchanged.
- **The dashboard** (`index.html`) as `pages/Dashboard.svelte`, mounted by the
  entry module `pages/dashboard.js` (§1.3) under `components/Nav.svelte`, and its parts:
  the ABC bars (`BarChart`), the SKU demand chart (`LineChart`, the forecast
  average as a second series), the shelf heatmap (`HeatGrid`), and its seven
  tables (`DataTable`, sortable). The CSV export links stay.
- **Page tests:** the dashboard's behaviour spec (§5.3) on the harness F1
  added.

## Tests

- Each component in Vitest: datasets from props, colours by name, updates when props change, destroyed on unmount.
- `DataTable` takes an API `{fields, rows}` answer as it is: titles, alignment
  and sort order follow each field's `label`, `unit` and `kind`.
- `csv.test.js`: `tableCsv` on a flat table, and the formula-injection cases
  of `pivot.test.js` through both writers; `pivot.test.js` passes unchanged.
- The dashboard in Playwright: loads without console errors, choosing a SKU
  redraws its chart, the tables sort, 390 px has no horizontal overflow.

## Non-goals

- The other pages stay as they are (F3, F4); `chart.js` stays until F5.

## Acceptance

- The dashboard shows the same numbers as on `main` (checked against the API
  responses in the Playwright test), in both themes, desktop and 390 px wide;
  screenshots in the PR.

## Version

`Version: none` — UI only.
