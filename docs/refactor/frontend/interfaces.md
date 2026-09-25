# Frontend refactor — component and build contract

This is the **authoritative contract** for this sequence
([`00-overview.md`](00-overview.md)). PR plans link here and do not redefine
names, props or file locations. If an implementation must change one, the same
PR updates this file, the affected plans and every caller.

Every section is labelled **Current** (on `main` today) or **Target (after
PR Fn)** (runnable when that PR merges).

---

## 1. Layout and build

### 1.1 Current

```
ui/
  package.json            {"type": "module"}: no dependency, no script
  index.html  app.js      the dashboard
  explore.html  explore.js  pivot.js
  synthesizers.html  synthesizers.js  synthesis.js
  effects.html  effects.js  estimate.js  effects-model.js  estimate-model.js
  chart.js  palette.js  common.js  sources.js
  *.css  favicon.svg
  *.test.js               node --test ui/*.test.js
```

Each page loads one `<script type="module" src="x.js">`; modules import each
other by relative path. The API mounts the folder with
`SDF_UI_DIR=ui uv run uvicorn sdf.api.app:app`.

### 1.2 Target (after F1)

F1 changes the tooling and moves files; it rewrites no page.

```
ui/
  package.json  package-lock.json   pinned dependencies; scripts below
  vite.config.js                    four HTML entries, the /api proxy for development
  svelte.config.js
  index.html  explore.html  synthesizers.html  effects.html   entries; same file names, same URLs
  public/favicon.svg
  src/
    lib/            the pure modules, moved unchanged: api.js and format.js (split from
                    common.js, below), chart.js, palette.js, pivot.js, sources.js,
                    synthesis.js, effects-model.js, estimate-model.js, and their tests
    legacy/         today's page scripts and styles, moved unchanged: app.js, explore.js,
                    synthesizers.js, effects.js, estimate.js, *.css, and dom.js (below)
  e2e/              the Playwright harness and one smoke spec per page (§5.3)
  dist/             built by `npm run build`; ignored by git
```

Where each export of today's `common.js` goes, with its tests:

| Export | Module | Tests |
|---|---|---|
| `API`, `api`, `describeDetail` | `lib/api.js` | `describeDetail`'s cases of `common.test.js`, as `api.test.js` |
| `esc`, `fmt`, `valueFormatter`, `compactFormatter` | `lib/format.js` | the other cases of `common.test.js`, as `format.test.js` |
| `$` (the one DOM helper) | `legacy/dom.js`, for the legacy pages only | none today; deleted with `legacy/` in F5 |

`common.test.js` is split between the two new files with every assertion kept,
so the seven test files of today become eight.

Scripts in `ui/package.json`:

| Script | Does |
|---|---|
| `npm run dev` | Vite's development server on port 5173, `/api` proxied to `http://127.0.0.1:8000` |
| `npm run build` | writes `ui/dist/`: the four pages, hashed assets, no source maps |
| `npm test` | Vitest: the pure modules and the components (jsdom) |
| `npm run check` | `svelte-check`: types from JSDoc, and Svelte's own warnings, as errors |
| `npm run e2e` | Playwright against `ui/dist` served by the API (§5.3) |

Serving the built UI: `SDF_UI_DIR=ui/dist uv run uvicorn sdf.api.app:app`.
`create_app(ui_dir=…)` is unchanged: it still mounts a folder that has an
`index.html`.

**Dependencies** (versions pinned by the lockfile; ranges in `package.json`):

| Package | Role | Licence |
|---|---|---|
| `svelte` 5 | the components | MIT |
| `vite` 8, `@sveltejs/vite-plugin-svelte` 7 | the build | MIT |
| `chart.js` 4 | charts | MIT |
| `chartjs-chart-error-bars` 4 | interval (forest) plots | MIT |
| `chartjs-chart-matrix` 3 | the shelf heatmap | MIT |
| `tabulator-tables` 6 | tables | MIT |
| `vitest`, `@testing-library/svelte`, `jsdom`, `svelte-check`, `@playwright/test` | development only | MIT / Apache-2.0 |

Nothing is loaded from the network at run time.

### 1.3 Target (after F2 to F5)

Each PR adds its part and empties `legacy/` of the page it rebuilds:

```
ui/src/
  lib/csv.js  csv.test.js           F2 (§3.2)
  components/charts/  tables/       F2 (§2.2, §3.2); PivotTable in F4
  components/Nav.svelte             F2: the shared navigation, used by each page once rebuilt
  pages/Dashboard.svelte ...        F2 the dashboard; F3 Synthesizers and Effects; F4 Explore
  pages/dashboard.js ...            one entry module per rebuilt page, with its component (below)
  theme.css                         F2 (§4)
ui/e2e/                             the behaviour specs of §5.3, one per page as it is rebuilt
```

**Entry modules.** An HTML entry cannot mount a component by itself, and no
page may carry an inline script (§5.4). Each rebuilt page therefore has a
browser entry module next to its component, added by the PR that rebuilds the
page (`pages/dashboard.js` in F2; `synthesizers.js` and `effects.js` in F3;
`explore.js` in F4), and that PR points the page's
`<script type="module" src>` from `src/legacy/…` to it:

```js
// ui/src/pages/dashboard.js
import { mount } from "svelte";
import "../theme.css";
import Dashboard from "./Dashboard.svelte";

mount(Dashboard, { target: document.getElementById("app") });
```

The page's HTML keeps its `<head>` and holds `<div id="app"></div>` in its
body.

**`niceTicks` outlives `chart.js`.** `effects-model.js` imports `niceTicks`
from `chart.js` for its axis, and F3 uses `effects-model.js` as it is. F5
moves `niceTicks` and its tests from `chart.js` and `chart.test.js` into
`lib/format.js` and `format.test.js`, unchanged, points `effects-model.js`'s
import there, and only then deletes `legacy/` (empty by then), `lib/chart.js`
and `lib/chart.test.js`.

### 1.4 Adding a page (the algorithm phase's PR 6)

This sequence rebuilds the four pages that exist. The algorithm phase's PR 6
adds a fifth, `forecasts.html` (`../algorithms/interfaces.md` §8), after F5,
and owns every change it needs here: the HTML entry and its line in
`vite.config.js`, a `pages/Forecasts.svelte`, the Forecasts link in the shared
navigation component (`Nav.svelte`, one place, so every page gets it), the page's
Playwright spec, and the new files in §1.3's layout. The contract needs
no other change for it; F5 rewrites `06-pages.md` to say so.

---

## 2. Charts

### 2.1 Current

`ui/chart.js` exports `barChart`, `lineChart`, `bindBars`, `bindLine`,
`showTip`, `niceTicks`, `clip`, `stepIndex`; each chart is an SVG string put in
the page with `innerHTML`. The dashboard, the effect and estimator interval
plots and the replicate strip plot are drawn by hand in their page scripts.

### 2.2 Target (after F2): `ui/src/components/charts/`

One Svelte component per kind of chart; each owns one Chart.js instance,
updates it when its props change, and destroys it when it leaves the page.

```svelte
<LineChart     {series} {labels} {yLabel} {format} {band} />     <!-- lines; gaps at null; filled band -->
<BarChart      {series} {labels} {format} {stacked} {horizontal} />
<IntervalChart {rows} {format} {reference} />                   <!-- point + interval per row; reference line -->
<StripChart    {groups} {format} />                             <!-- jittered points per group, with its mean -->
<HeatGrid      {cells} {columns} {rows} {format} />             <!-- a value per cell on the sequential ramp -->
```

Optional props, which may be left out: `band` (no band), `stacked` and
`horizontal` (`false`), `reference` (no line). Every other prop is required.

The props, in JSDoc types (`number | null` is a missing value: a gap in a
line, no bar, an empty cell; never a zero):

```js
/** @typedef {{name: string, values: (number|null)[], color?: string}} Series */
// LineChart, BarChart: labels: string[]; every series' values has labels.length entries.
/** @typedef {{name: string, low: (number|null)[], high: (number|null)[]}} Band */
// LineChart's band: low and high have labels.length entries; the fill is drawn
// between them, and not where either is null. low > high is a caller error.
/** @typedef {{label: string, estimate: number, low: number|null, high: number|null, group?: string}} IntervalRow */
// IntervalChart: one row per line, top to bottom in the given order; a null
// low or high draws the point with no interval; group picks the colour by name.
// reference: number | null, a vertical line (0 for effects).
/** @typedef {{name: string, values: number[], mean: number}} StripGroup */
// StripChart: one row of points per group; jitter is seeded by the group's
// name, so a redraw does not move points. mean is required and is drawn as
// given: on the Effects page it is the effect the API sends (`effect`); the
// chart never computes a mean itself (AGENTS.md rule 7).
/** @typedef {{row: string, column: string, value: number|null}} HeatCell */
// HeatGrid: columns: string[] and rows: string[] give the order; a cell
// missing from cells, or with value null, is drawn empty.
```

Each component's test (§5.2) builds its Chart.js datasets from these shapes,
null and interval cases included.

- **`series`** is `[{name, values, color?}]`. A colour is never chosen by
  position on screen: it comes from `palette.colorBook()` by the series' name,
  as today, so a series keeps its colour when others are filtered out.
- **`format`** is a `(value) => string` from `lib/format.js` (`fmt`,
  `valueFormatter`), used by the ticks and the tooltip alike.
- **`band`** is `{low, high, name}` for PR 6 of the algorithm phase (forecast
  intervals).
- Tooltips, legends and hover use Chart.js's own, styled by the theme (§4).
  No accessibility layer is added (overview, Non-goals).

`IntervalChart` replaces the forest plots of `effects.js` and `estimate.js`
(`chartjs-chart-error-bars`, scatter with x error bars); `StripChart` the
replicate dots; `HeatGrid` the shelf heatmap (`chartjs-chart-matrix`).

---

## 3. Tables

### 3.1 Current

The dashboard, effects and estimator-score tables fill a `<tbody>` from
template strings; `explore.js` `renderTable` draws the pivot by hand
(multi-level headers, sticky row labels and totals, sorting, collapsible
subtotal groups, a 1,000-row budget, heat shading).

### 3.2 Target (after F2 and F4): `ui/src/components/tables/`

```svelte
<DataTable  {fields} {rows} {format} {sort} {download} {height} />
<PivotTable {result} {view} {heat} {collapsed} {maxHeight} onsort={…} ontoggle={…} />
```

Optional: `format`, `sort` (the initial sort), `download` (`false`), `height`
(the rows' natural height), `heat` (`false`) and `maxHeight` (`"70vh"`).
`PivotTable` always has a bounded height: `maxHeight` has a default and
cannot be unset, because Tabulator renders only the visible rows of a table
whose height is bounded, and the pivot's row budget goes on that promise
(below). A `DataTable` without `height` renders every row, which suits the
short tables it is used for. `collapsed` is the page's set
of collapsed group keys; `onsort` and `ontoggle` are callback props (Svelte 5
has no `on:` events on components) through which the page updates `view.sort`
and `collapsed`.

- **`DataTable`** wraps one Tabulator instance and takes the API's own table
  shape: `fields` is `[{name, label, kind, unit?, aggregate?}]` (the API's
  `FieldModel`) and `rows` is a list of arrays in the order of `fields`, so a
  `{fields, rows}` answer is passed as it is. The one mapping, from that shape
  to Tabulator's column definitions and row objects, is inside `DataTable`:
  `name` becomes the column's field, `label` (with `unit` in brackets) its
  title, and `kind` its alignment and sorter (`measure` right-aligned and
  numeric, `time` by date, `dimension` as text). A page that builds a table
  itself (the dashboard's replenishment rows, the effect estimates) builds
  it in the same shape. `format` is an optional `{[name]: (value) => string}`
  for fields that need more than `lib/format.js`'s default for their kind.
  Sorting is on for every column.
- **CSV.** `download` adds a CSV button. `lib/csv.js` holds the cell rule
  used today by `pivot.toCsv` (`csvCell`: quoting, and a leading `=`, `+`,
  `-`, `@`, tab or carriage return prefixed with `'` so a spreadsheet runs
  nothing), moved out of `pivot.js` unchanged, and a flat writer
  `tableCsv(fields, rows)` (a header of labels, then one line per row).
  `DataTable` writes through `tableCsv`; `PivotTable` through `pivot.toCsv`,
  which keeps its pivot-specific layout and now imports `csvCell`. Both are
  tested with the formula-injection cases of today's `pivot.test.js`.
- **`PivotTable`** renders the result of `lib/pivot.js` `pivot()`, unchanged,
  and computes no number: every cell, subtotal and total shown is one
  `pivot()` returned. Column groups become Tabulator column groups; the
  row-label columns are frozen. Subtotal rows are `result.rows` entries like
  any other, nested under their group with Tabulator's data tree, so a group
  collapses and its row still shows `pivot()`'s subtotal; Tabulator's row
  grouping and its group calculations are not used. The totals row is a
  bottom calculation row whose calculator returns `result.totals` as they
  are (a mean, a median or a share cannot be recomputed from the rows shown,
  and the subtotal rows would be counted twice). Heat shading uses the
  theme's ramp. A component test checks that the totals row equals
  `result.totals` for a mean and a share.
  Tabulator's virtual rendering draws only the visible rows, so the row
  budget and its "Show all" button go; the 400-column cut stays, as a limit
  of what a person can read.
- Sorting stays in `view.sort`, so a link restores it, as today. Collapsed
  groups stay page state, as today: they are not in the link (whose shape,
  `{source, view, display}`, does not change) and they clear when the row
  fields change. Clicking a Tabulator header or group toggle updates this
  state; Tabulator never keeps a sort or a collapse of its own.

---

## 4. Theme

- `ui/src/theme.css` defines the tokens as CSS custom properties, one set for
  `prefers-color-scheme: dark` (today's colours) and one for light:
  `--surface`, `--surface-raised`, `--ink`, `--ink-muted`, `--rule`,
  `--accent`, `--good`, `--warn`, `--bad`, and the heat ramp `--heat-0` to
  `--heat-5`.
- `lib/palette.js` stays the source of series colours and exports one set per
  theme; today's tests keep checking the dark set, unchanged.
- Chart.js and Tabulator read the tokens at render time and redraw when the
  scheme changes.

---

## 5. Tests

### 5.1 Pure modules (F1)

`ui/src/lib/*.test.js`, run by Vitest. All seven of today's `ui/*.test.js`
files move, `chart.test.js` included, with their assertions unchanged
(`common.test.js` split into `api.test.js` and `format.test.js`, §1.2); only
the imports change (`node:test` to `vitest`, `node:assert` stays).
`chart.test.js` is deleted in F5 together with `chart.js`. `csv.test.js` is
new in F2 (§3.2).

### 5.2 Components (F2 to F4)

Vitest with Testing Library in jsdom: a table renders the right numbers, a chart receives the datasets its props describe (the
Chart.js instance is inspected, not the canvas pixels), a link's view restores
the component's state.

### 5.3 Pages (F1 to F4)

`ui/e2e/*.spec.js`, Playwright in Chromium, against the built UI served by the
API on the default world. F1 adds the harness, the `npm run e2e` script, the CI
step and a smoke spec per page (the first point below, and the same API calls
as `main` for the page's first load); F2 to F4 add the other points for the
page each rebuilds:

- each page loads with no console error and no failed request;
- its main action works (dashboard: choose a SKU; Explore: build a pivot from
  a preset and switch to the chart; Synthesizers: run an evaluation; Effects:
  run a study and an estimation);
- a link with a view in its address restores that view;
- at 390 px wide nothing overflows horizontally.

CI installs Chromium with `npx playwright install --with-deps chromium`.

### 5.4 Python tests that read `ui/` (F1)

`src/sdf/api/app_test.py` keeps each property, pointed at the new layout:

| Test | Current | Target |
|---|---|---|
| every UI path is in the OpenAPI schema | `api("/…")` literals in `ui/*.js` | the same, in `ui/src/**/*.{js,svelte}` |
| the UI reaches the backend only through `api()` | one `fetch(` in `common.js` | one `fetch(` in `ui/src/lib/api.js`, none elsewhere in `ui/src` |
| no inline event handler | no `on…=` attribute in `ui/` | none in `ui/dist/*.html` and no inline `<script>` there |
| every page links the others | in `ui/*.html` | the same after F1; from F2, each page not yet rebuilt still in its HTML, and each rebuilt page through `components/Nav.svelte`, which the test reads once for all of them; after F4 only `Nav.svelte` |
| the UI folder is mounted | `ui/` | `ui/dist/`, skipped with the reason when it was not built; CI builds it first |

## 6. Compatibility

- Page file names, URLs and hash formats do not change; links made before this
  sequence open the same view after it.
- The API, its schema and every Python behaviour are unchanged; `sdf demo` and
  `docs/VALIDATION.md` do not move.
- `SDF_UI_DIR` keeps its meaning; only the folder to point it at changes, from
  `ui` to `ui/dist`, which F1 documents in the README, ONBOARDING and
  ARCHITECTURE.
