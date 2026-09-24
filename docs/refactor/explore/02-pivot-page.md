# PR 2 — The Explore page: pivot table and chart

> Status: implemented (exploration sequence PR 2). Changes from this plan, each
> recorded in `interfaces.md` §3: the tests run with `node --test ui/*.test.js`
> (Node 22 does not search a folder given as `ui/`); the link also carries the
> display (table or chart, heatmap, totals, stacked); the heatmap uses six
> discrete steps of the blue ramp, because at the middle step (`#2a78d6`)
> neither white nor dark text reaches 4.5:1; charts fold past eight series with
> `pivot(table, view, { maxColumns: 8 })`. Beyond the files listed here the page
> has `ui/explore.css` and `ui/chart.js`, and `ui/common.test.js` covers the
> number formatting. A synthesis link is read and answered with a clear message
> until PR 3 adds its endpoint.

Contract: [`interfaces.md`](interfaces.md) §2.1 (the tables it reads) and §3
(the pivot engine).

## Goal

A user opens any catalogue dataset or experiment result, builds a
cross-tabulation by dragging fields, and reads it as a table or a chart, with
the finish of a professional analysis tool: correct totals, clear number
formats, filters, sorting, collapsible groups, and a link that reproduces the
view.

## Scope

**Engine (`ui/pivot.js`)**, a pure module as the contract describes:
aggregations `sum`, `count`, `count_distinct`, `mean`, `median`, `min`, `max`;
time grains `day`, `week`, `month`, `quarter`, `year`, `weekday`; include and
exclude filters; value shares of the grand, row or column total; sorting by
label or by value; subtotals for nested row fields; totals aggregated from rows,
not from cells.

**Page (`ui/explore.html`, `ui/explore.js`)**:

- *Source bar.* A dataset picker fed by `GET /datasets`, showing each dataset's
  description (its row count, `total_rows`, appears once the dataset is
  loaded), and an **Experiment** source that builds a request
  from `GET /experiments/catalog` (interventions, policies with their
  parameters, outcomes) and pivots the `POST /experiments` result.
- *Field list.* Fields grouped as Dimensions, Time and Measures, each with its
  kind icon and unit, and a search box.
- *Shelves.* Rows, Columns, Values and Filters. Fields are dragged onto a shelf,
  or added from a shelf's "+" menu with the keyboard. A chip shows its
  aggregation or time grain and opens a small menu to change it, and can be
  reordered or removed.
- *Filters.* A value list with search, select all and none, and a count of the
  values kept.
- *Toolbar.* Table or chart view; "show values as" (value, share of total,
  share of row, share of column); subtotals and totals on or off; heatmap
  shading on or off; swap rows and columns; export the result as CSV; copy a
  link to the view; reset.
- *Presets.* One-click starting views, for example "Line value by category and
  month" or "Stock value by zone and ABC class". A preset is just a saved view,
  so it goes through the same code as a view the user builds.
- *Table.* Sticky column headers and sticky row labels; right-aligned tabular
  numbers formatted by unit (currency, units, shares as percentages); blank
  cells shown as "–", never 0; nested row fields collapse and expand; clicking a
  column header sorts by it; row and column totals are set apart; optional
  heatmap shading on a single-hue sequential ramp, with values kept readable.
- *Chart.* A bar chart of rows by column series, or a line chart when the row
  field is time; grouped or stacked bars. One y-axis only: several values
  become small multiples. Series take the categorical palette in fixed order,
  and beyond eight series the rest fold into "Other". There is always a legend
  for two or more series, a hover tooltip on every mark, and a table view one
  click away. The colours are fixed constants in `ui/palette.js`:
  - the eight series colours, in this order: `#3987e5`, `#d95926`, `#199e70`,
    `#c98500`, `#d55181`, `#008300`, `#9085e9`, `#e66767`. This is a published
    categorical order stepped for dark surfaces and checked for colour-blind
    separation between neighbours;
  - the heatmap's single-hue blue ramp, `#104281` (low) to `#86b6ef` (high).

  `ui/palette.test.js` asserts the order and that every series colour has at
  least 3:1 WCAG contrast against the page surface `#161b22`, so a later edit
  cannot quietly break either.
- *Status line.* Rows read, rows after filters, groups, and time taken; a
  truncated dataset says so.
- *State in the address.* The source (a dataset or an experiment request) and
  the view are encoded in `explore.html#view=…` as `interfaces.md` §3 defines;
  opening that link repeats the request and rebuilds the view. The `synthesis`
  source shape is read by this page but only produced once PR 3's endpoint
  exists.
- *Empty, loading and error states.* No field chosen, a request in flight, a
  422 or 404 from the API: each has its own message.

**Shared UI code.** `api()`, `esc()` and the number formatting move from
`ui/app.js` into `ui/common.js`, used by the dashboard and the Explore page. The
dashboard becomes a module page: `index.html` loads `app.js` with
`<script type="module">`, and every inline handler becomes a listener
registered in `app.js`, because a module's functions are not globals:

- the `onclick` handlers of the regenerate, ask and agent-run buttons;
- the `onchange` handlers of the SKU (mover) and service-level selects;
- the `onkeydown` Enter handlers of the question and agent inputs;
- the suggested-question chips that `app.js` renders with inline `onclick`.
  They carry the question in a `data-question` attribute instead, with one
  delegated listener on their container.

After the change `ui/index.html` and `ui/*.js` contain no inline `on…=`
handler, which a test checks. A navigation bar (Dashboard, Explore) is added to
both pages.

**Tests and CI.**

- `ui/package.json` (`{"type": "module"}` only) makes Node load `ui/*.js` as
  ES modules. `ui/pivot.test.js` runs under `node --test ui/*.test.js`. It covers each aggregation,
  each grain, filters, shares, sorting, subtotals, totals from rows,
  `null`-not-`0`, and both row forms of `toTable`.
- CI gains a step that runs `node --test ui/*.test.js` (Node is preinstalled on the
  runners).
- `api/app_test.py`'s check that every UI path is in the OpenAPI schema reads
  every `ui/*.js`, not only `app.js`.

## Non-goals

- No backend change; the tables come from PR 1.
- No frontend framework, bundler or npm dependency; plain ES modules.
- No saved views on the server and no view sharing beyond the link.
- No editing of data: the page reads tables and shows derived views only.

## Acceptance

```bash
uv sync --locked --extra api
uv run ruff check && uv run ruff format --check
uv run pytest                                # includes the UI-path-in-OpenAPI check over every ui/*.js
node --test ui/*.test.js
```

Manual, in a browser against `SDF_UI_DIR=ui uv run uvicorn sdf.api.app:app`:

- Every preset renders. A view built by dragging fields matches the same view
  opened from its copied link.
- Totals match the dashboard's figures for the same world: the count of order
  lines against "Outbound lines", the sum of stock value against "Inventory
  value", and the count of plan rows that need an order against the
  replenishment panel at 95 %.
- A 180-day, 500-SKU world (the largest the API allows) pivots by date and
  category without the page freezing.
- The dashboard still works as a module page: every panel renders, and each
  migrated control works: regenerate, the SKU choice, the service-level choice,
  ask by button, by Enter and by a suggested-question chip, the agent run by
  button and by Enter, and the export links.
- No failed request and no console error.

## Version

`Version: none` — the UI in `ui/` and the CI workflow are not part of the
Python distribution; no shipped code changes.
