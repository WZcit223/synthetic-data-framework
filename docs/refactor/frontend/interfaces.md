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
                    common.js), chart.js, palette.js, pivot.js, sources.js, synthesis.js,
                    effects-model.js, estimate-model.js, and all seven *.test.js
    legacy/         today's page scripts and styles, moved unchanged: app.js, explore.js,
                    synthesizers.js, effects.js, estimate.js, *.css
  dist/             built by `npm run build`; ignored by git
```

### 1.3 Target (after F2 to F5)

Each PR adds its part and empties `legacy/` of the page it rebuilds:

```
ui/src/
  lib/csv.js  csv.test.js           F2 (§3.2)
  components/charts/  tables/       F2 (§2.2, §3.2); PivotTable in F4
  components/Nav.svelte             F2: the shared navigation, every page's links
  pages/Dashboard.svelte ...        F2 the dashboard; F3 Synthesizers and Effects; F4 Explore
  theme.css                         F2 (§4)
ui/e2e/                             F2: the Playwright harness; one spec per page as it is rebuilt
```

F5 deletes `legacy/` (empty by then), `lib/chart.js` and `lib/chart.test.js`.

Scripts in `ui/package.json`:

| Script | Does |
|---|---|
| `npm run dev` | Vite's development server on port 5173, `/api` proxied to `http://127.0.0.1:8000` |
| `npm run build` | writes `ui/dist/`: the four pages, hashed assets, no source maps |
| `npm test` | Vitest: the pure modules and the components (jsdom) |
| `npm run check` | `svelte-check`: types from JSDoc, and Svelte's own warnings, as errors |
| `npm run e2e` | Playwright against `ui/dist` served by the API (§5.3) |

### 1.4 Adding a page (the algorithm phase's PR 6)

This sequence rebuilds the four pages that exist. The algorithm phase's PR 6
adds a fifth, `forecasts.html` (`../algorithms/interfaces.md` §10), after F5,
and owns every change it needs here: the HTML entry and its line in
`vite.config.js`, a `pages/Forecasts.svelte`, the Forecasts link in the shared
navigation component (`Nav.svelte`, one place, so every page gets it), the page's
Playwright spec, and the new files in §1.3's layout. The contract needs
no other change for it; F5 rewrites `06-pages.md` to say so.

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
<LineChart     {series} {labels} {yLabel} {format} {summary} {band}? />  <!-- lines; gaps at null; optional filled band -->
<BarChart      {series} {labels} {format} {summary} {stacked}? {horizontal}? />
<IntervalChart {rows} {format} {summary} {reference}? />         <!-- point + interval per row; optional reference line -->
<StripChart    {groups} {format} {summary} />                    <!-- jittered points per group, with the group mean -->
<HeatGrid      {cells} {columns} {rows} {format} {summary} />    <!-- a value per cell on the sequential ramp -->
```

- **`series`** is `[{name, values, color?}]`. A colour is never chosen by
  position on screen: it comes from `palette.colorBook()` by the series' name,
  as today, so a series keeps its colour when others are filtered out.
- **`format`** is a `(value) => string` from `lib/format.js` (`fmt`,
  `valueFormatter`), used by the ticks and the tooltip alike.
- **`band`** is `{low, high, name}` for PR 6 of the algorithm phase (forecast
  intervals).
- **`summary`** is required on every chart: a sentence rendered for screen
  readers (`aria-label` on the canvas, `role="img"`). A chart without one is a
  `svelte-check` error (the prop has no default). Every chart is followed by the page's table view of
  the same numbers; no number is shown only in a chart.
- Tooltips, legends and hover use Chart.js's own, styled by the theme (§4).
  Keyboard access to data points comes from the table view.

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
<DataTable {fields} {rows} {format}? {sort}? {download}? {height}? />
<PivotTable {result} {view} {heat}? on:sort on:toggle />
```

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
- **`PivotTable`** renders the result of `lib/pivot.js` `pivot()`, unchanged:
  column groups become Tabulator column groups; the row-label columns are
  frozen; subtotal groups are Tabulator row groups, collapsible; the totals
  row is a bottom calculation row; heat shading uses the theme's ramp.
  Tabulator's virtual rendering draws only the visible rows, so the row
  budget and its "Show all" button go; the 400-column cut stays, as a limit
  of what a person can read.
- Sorting and collapsing stay in the view state (`view.sort`, collapsed
  groups), so a link still restores them.

---

## 4. Theme

- `ui/src/theme.css` defines the tokens as CSS custom properties, one set for
  `prefers-color-scheme: dark` (today's colours) and one for light:
  `--surface`, `--surface-raised`, `--ink`, `--ink-muted`, `--rule`,
  `--accent`, `--good`, `--warn`, `--bad`, and the heat ramp `--heat-0` to
  `--heat-5`.
- `lib/palette.js` stays the source of series colours and exports one set per
  theme; its tests check contrast against both surfaces.
- Chart.js and Tabulator read the tokens at render time and redraw when the
  scheme changes.

---

## 5. Tests

### 5.1 Pure modules (F1)

`ui/src/lib/*.test.js`, run by Vitest. All seven of today's `ui/*.test.js`
files move, `chart.test.js` included, with their assertions unchanged; only
the imports change (`node:test` to `vitest`, `node:assert` stays).
`chart.test.js` is deleted in F5 together with `chart.js`. `csv.test.js` is
new in F2 (§3.2).

### 5.2 Components (F2 to F4)

Vitest with Testing Library in jsdom: a component renders its table view with
the right numbers, a chart receives the datasets its props describe (the
Chart.js instance is inspected, not the canvas pixels), a link's view restores
the component's state.

### 5.3 Pages (F2 to F4)

`ui/e2e/*.spec.js`, Playwright in Chromium, against the built UI served by the
API on the default world:

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
| every page links the others | in `ui/*.html` | the same after F1; from F2, in `components/Nav.svelte`, which every page uses |
| the UI folder is mounted | `ui/` | `ui/dist/`, skipped with the reason when it was not built; CI builds it first |

## 6. Compatibility

- Page file names, URLs and hash formats do not change; links made before this
  sequence open the same view after it.
- The API, its schema and every Python behaviour are unchanged; `sdf demo` and
  `docs/VALIDATION.md` do not move.
- `SDF_UI_DIR` keeps its meaning; only the folder to point it at changes, from
  `ui` to `ui/dist`, which F1 documents in the README, ONBOARDING and
  ARCHITECTURE.
