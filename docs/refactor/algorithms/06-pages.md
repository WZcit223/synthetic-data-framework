# PR 6 — Forecasts page, detectors and detection on the existing pages

> Status: implemented. Rewritten for the frontend's new stack (Svelte, Chart.js,
> Tabulator; [`../frontend/`](../frontend/00-overview.md)) by its step F5. The
> acceptance is met: a benchmark link shows the scores `sdf forecast
> --benchmark` prints for the same request, row for row. Where the
> implementation departs from the plan, and why:
>
> - **"One SKU's history" is the days after the last origin.** The backtest's
>   `forecasts` table holds each SKU's actual demand only over the forecast
>   days, and this PR adds no API field. Each small multiple therefore shows
>   the forecaster's mean, its interval and the demand that happened over those
>   days.
> - **The scores table shows the columns a reader compares.** Those are WAPE,
>   relative WAPE, bias, pinball loss, coverage with the bounds, interval width,
>   run time, and a reading; a failed forecaster's error is written under the
>   table. Every column, the method included, opens in Explore.
> - **The default request is the three fast built-ins**
>   (`seasonal-naive`, `moving-average`, `seasonal-linear`: under a second).
>   `gradient-boosting` takes about 15 s on the world, so it is offered but not
>   ticked.
> - **`IntervalChart` gains an optional `range`,** so the detection AUC is drawn
>   on the whole scale from below a coin toss to 1 (frontend contract §2.2).
> - **The dashboard keeps the demand anomalies of the whole series,** and adds
>   each SKU's anomalies from the chosen detector below them.
> - **The page has no `pages/forecasts/` folder.** Its parts fit in
>   `Forecasts.svelte`, with the logic in `lib/forecasts-model.js`, which
>   also checks what the server would refuse before sending: the history a
>   benchmark needs (horizon, origins a week apart and the days before the
>   first) and a number field holding text that is not a number.

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
    - the scores as a `DataTable`, sortable; the `true-distribution` row is
      the reference, named so in its label (`tone` is for a status colour,
      not for this);
    - WAPE by days ahead as a `LineChart`, one series per forecaster;
    - one SKU's history with each forecaster's interval band for the last
      origin, with a SKU picker: one `LineChart` per forecaster (small
      multiples, each on its own scale), each with the forecaster's mean as
      its first series (a band takes the first series' colour), the history
      second, and the interval as its `band`;
  - the request in the page's address, so a link reproduces it; "Open in
    Explore" for the three tables, through a new Explore source `forecasts`
    (`lib/sources.js`, and a fetch case and presets in `pages/explore/`).
- **Dashboard:** the SKU chart already draws the forecast's interval
  (`demand-series.forecast`, PR 2); the anomaly panel gains a detector choice
  from `GET /detectors` and lists `GET /anomalies` in a `DataTable`.
- **Synthesizers page:** a table evaluation shows the detection AUC with its
  interval (`IntervalChart`, one row), the verdict in words and the top
  features.
- **Docs:** README and ONBOARDING (the page and its link format), and the UI
  section of ARCHITECTURE.

## Charts

The components of the frontend contract §2, with no hand-drawn chart. Colours
follow the entity, never its rank: each forecaster's colour is its place in
the catalogue, as for estimators (a `color` on each series). A band is the
first series' colour at low opacity, as `LineChart` draws it, so the mean
comes first; the `true-distribution` reference is a neutral series. A chart
that needs more (a band in a colour of its own, a scale shared across small
multiples) adds it to `LineChart` and to the frontend contract §2.2 in this PR. Both themes are
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
  Synthesizers page's specs gain the detector choice and the AUC.
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

`Version: none, UI and documentation only; ui/ is not part of the package's
versioned interface, and no shipped Python code changes.`
