# PR 6 — Forecasts page, detectors and detection on the existing pages

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §8.

## Goal

What PR 1 to 5 measure can be chosen, run and read from the browser, with the
same care as the Effects and Explore pages: every number comes from the
API, every bound from its catalogue, and every result opens in Explore.

## Scope

- **Forecasts page** (`ui/forecasts.html`, `ui/forecasts.js`, and a pure
  `ui/forecasts-model.js` tested with Node's runner):
  - the request form from `GET /forecasters`: forecasters (at most the
    published limit) with their parameters, the source (the world, or the
    benchmark with its parameters), horizon, origins and interval level;
    checked before sending, from the published bounds;
  - the results: the scores table (sortable, with the `true-distribution`
    row set apart as the reference), WAPE by days ahead as one line per
    forecaster, and one SKU's history with each forecaster's interval band
    for the last origin, with a SKU picker;
  - the request in the page's address, so a link reproduces it; "Open in
    Explore" for the three tables, through a new Explore source `forecasts`.
- **Dashboard:** the SKU chart draws the forecast's interval band from
  `demand-series.forecast`; the anomaly panel gains a detector choice from
  `GET /detectors` and lists `GET /anomalies`.
- **Synthesizers page:** a table evaluation shows the detection AUC with its
  interval, the verdict in words and the top features.
- **Navigation:** the Forecasts page in the header of every page.
- **Docs:** README and ONBOARDING (the page and its link format).

## Charts

Colours follow the entity, never its rank: each forecaster's colour is its
place in the catalogue, as for estimators. The interval band is the series
colour at low opacity with a 2 px line for the mean; the
`true-distribution` reference is a neutral dashed line. Every chart has a
legend, a table view and hover values; dark mode is checked separately.

## Tests

- `ui/forecasts-model.test.js`: the default request, fitting a request from a
  link (unknown forecasters and bad parameters dropped and named), the
  request checks against the published limits, reading the scores table,
  colour by catalogue order.
- The UI contract test covers the new API paths.
- Checked in Chromium on the default world and on the benchmark, desktop and
  390 px wide, light and dark; screenshots in the PR.

## Non-goals

- No new endpoint or API field; the page uses PR 1 to 5 as they are.
- No change to the Explore page beyond its new source.

## Acceptance

- `node --test ui/*.test.js` passes; the required checks of `AGENTS.md`
  pass unchanged.
- A link to a backtest on the benchmark, opened in a new tab, shows the same
  scores as `sdf forecast --benchmark` with the same parameters.

## Version

`Version: none` — UI and documentation: `ui/` is not part of the package's
versioned interface.
