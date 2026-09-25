# PR 6 — Forecasts page, detectors and detection on the existing pages

> Status: planned. Rewritten for the frontend's new stack (Svelte, Chart.js,
> Tabulator; [`../frontend/`](../frontend/00-overview.md)) by its step F5.

Contract: [`interfaces.md`](interfaces.md) §8; the components, the build and
the tests are those of [`../frontend/interfaces.md`](../frontend/interfaces.md).

## Goal

What PR 1 to 5 measure can be chosen, run and read from the browser, with the
same care as the Effects and Explore pages: every number comes from the
API, every bound from its catalogue, and every result opens in Explore.

## Scope

- **A fifth page** (frontend interfaces §1.4). This PR owns every build and
  navigation change it needs:
  - the entry `ui/forecasts.html`, which holds `<div id="app"></div>` and its
    entry module, and its line in `vite.config.js`;
  - `ui/src/pages/forecasts.js`, which mounts `pages/Forecasts.svelte`;
  - the Forecasts link in `components/Nav.svelte`, so every page gets it;
  - `forecasts.html` added to `app_test.py`'s page list.
- **Forecasts page** (`pages/Forecasts.svelte`, its parts in `pages/forecasts/`,
  and a pure `lib/forecasts-model.js` tested with Vitest):
  - the request form from `GET /forecasters`: forecasters (at most the
    published limit) with their parameters, the source (the world, or the
    benchmark with its parameters), horizon, origins and interval level;
    checked before sending, from the published bounds;
  - the results:
    - the scores as a `DataTable`, sortable, with the `true-distribution`
      row set apart as the reference by its `tone`;
    - WAPE by days ahead as a `LineChart`, one series per forecaster;
    - one SKU's history with each forecaster's interval band for the last
      origin, with a SKU picker: one `LineChart` per forecaster (small
      multiples on a shared scale), each with the history, the
      forecaster's mean and its `band`;
  - the request in the page's address, so a link reproduces it; "Open in
    Explore" for the three tables, through a new Explore source `forecasts`
    (`lib/sources.js`, and a fetch case and presets in `pages/explore/`).
- **Dashboard:** the SKU chart (`pages/dashboard/Replenishment.svelte`) draws
  the forecast's interval band from `demand-series.forecast` with
  `LineChart`'s `band`; the anomaly panel gains a detector choice from
  `GET /detectors` and lists `GET /anomalies` in a `DataTable`.
- **Synthesizers page:** a table evaluation shows the detection AUC with its
  interval (`IntervalChart`, one row), the verdict in words and the top
  features.
- **Docs:** README and ONBOARDING (the page and its link format), and the UI
  section of ARCHITECTURE.

## Charts

The components of the frontend contract §2, with no hand-drawn chart. Colours
follow the entity, never its rank: each forecaster's colour is its place in
the catalogue, as for estimators (a `color` on each series). A band is the
series colour at low opacity under the mean's line, as `LineChart` draws it;
the `true-distribution` reference is a neutral series. Both themes are
checked. No accessibility layer is added (frontend overview, Non-goals).

## Tests

- `lib/forecasts-model.test.js`: the default request, fitting a request from a
  link (unknown forecasters and bad parameters dropped and named), the
  request checks against the published limits, reading the scores table,
  colour by catalogue order.
- `ui/e2e/forecasts.spec.js`: the smoke check (no console error, the first
  load's API calls); a backtest runs and shows the scores the API returned;
  a link with a request in its address runs it once; "Open in Explore" opens
  each table; nothing overflows at 390 px. The dashboard's and the
  Synthesizers page's specs gain the band, the detector choice and the AUC.
- The UI contract tests in `app_test.py` cover the new API paths and the
  fifth page.

## Non-goals

- No new endpoint or API field; the page uses PR 1 to 5 as they are.
- No change to the Explore page beyond its new source.

## Acceptance

- `npm run check`, `npm test`, `npm run build` and `npm run e2e` pass in
  `ui/`; the required checks of `AGENTS.md` pass unchanged.
- A link to a backtest on the benchmark, opened in a new tab, shows the same
  scores as `sdf forecast --benchmark` with the same parameters.
- Screenshots in the PR: desktop and 390 px, light and dark.

## Version

`Version: none` — UI and documentation: `ui/` is not part of the package's
versioned interface.
