# F2 — Chart and table components, themes, page tests; the dashboard on them

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §2, §3, §4, §5.2 and §5.3.

## Goal

The shared components exist and are proven on the simplest page: the dashboard
is a Svelte page whose charts are Chart.js and whose tables are Tabulator.

## Scope

- **Charts:** `LineChart`, `BarChart`, `IntervalChart`, `StripChart`,
  `HeatGrid` (§2.2), registered once with only the Chart.js parts they use.
- **Tables:** `DataTable` (§3.2).
- **Theme:** `theme.css` with the light and dark sets; `palette.js` with a set
  per theme and its contrast tests on both surfaces.
- **The dashboard** (`index.html`) as `pages/Dashboard.svelte` and its parts:
  the ABC bars (`BarChart`), the SKU demand chart (`LineChart`, the forecast
  average as a second series), the shelf heatmap (`HeatGrid`), and its seven
  tables (`DataTable`, sortable). The CSV export links stay.
- **Page tests:** the Playwright harness (§5.3), in CI, and the dashboard's
  test.

## Tests

- Each component in Vitest: datasets from props, colours by name, the summary
  text, updates when props change, destroyed on unmount.
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
