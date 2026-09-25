# F4 — The Explore page on the components

> Status: implemented. The page is `pages/Explore.svelte` with its parts in
> `pages/explore/`: the view operations (`view.js`), the chart view's model
> (`chartModel.js`) and the experiment form (`experiment.js`) are pure modules
> with their own tests; the shelves, menus, field list, experiment form and
> chart view are components. The table is `components/tables/PivotTable.svelte`
> over the pure mapping `pivotConfig.js` (§3.2). With the Explore page rebuilt,
> nothing was left in `ui/src/legacy/`, so this step deleted the folder (F5
> had it).

Contract: [`interfaces.md`](interfaces.md) §3.2 and §5.3.

## Goal

The pivot page, the largest page (1,340 lines of page code today), becomes a
set of Svelte components around the unchanged `pivot.js`.

## Scope

- **Entry module:** `pages/explore.js` (§1.3), the page under `Nav.svelte`.
- **State:** one view object (`source`, `view`, `display`), as today, held in
  Svelte state and written to the `#view=` address on every change; the
  address is read on load and on `hashchange`.
- **Field shelf and drop zones:** Rows, Columns, Values and Filters, with
  drag and drop (native HTML5, as today).
- **Menus:** aggregation, time grain and filter values, as Svelte popovers.
- **Presets**, the source picker (catalogue datasets and the link sources of
  `sources.js`), CSV download and copy link.
- **Table view:** `PivotTable` (§3.2): column groups, frozen row labels,
  collapsible subtotals, totals, heat shading, sorting; virtual rendering
  instead of the row budget.
- **Chart view:** small multiples with `BarChart` (grouped or stacked) and
  `LineChart` for a time axis, the 50-bar and 8-series limits with "Other".

## Tests

- `pivot.test.js` unchanged.
- Component tests: a view restores its shelves and sort; collapsed groups
  clear when the row fields change, as today; the
  pivot's column groups and totals match `pivot()`'s result.
- Playwright: every preset renders; a pivot built by dragging fields; the chart
  view; a link from each source kind (dataset, synthesis run, effects,
  estimates) restores its view; 10,000 rows scroll without the page freezing,
  and the table holds far fewer row elements than rows (the virtual
  rendering of §3.2's bounded `maxHeight`).

## Non-goals

- No new pivot feature; no drill-through to records.

## Acceptance

- Every link from `main`'s tests and plans opens the same view; the pivot's
  numbers match `pivot()`; screenshots of a preset in both themes and at 390 px.

## Version

`Version: none` — UI only.
