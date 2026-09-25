# F3 — The Synthesizers and Effects pages on the components

> Status: implemented in this PR (F3).

Contract: [`interfaces.md`](interfaces.md) §2, §3 and §5.3.

## Goal

The two pages with forms, runs and interval plots are Svelte pages on the
shared components, with every address and link unchanged.

## Scope

- **Entry modules:** `pages/synthesizers.js` and `pages/effects.js` (§1.3),
  each page under `Nav.svelte`.
- **Synthesizers:** the catalogue and parameter form, the run, the real-versus-
  synthetic line chart and the per-measure histograms (`LineChart`, or
  `BarChart` for the histograms), the metrics table (`DataTable`), "Open in
  Explore"; the `#<synthesizer>` address.
- **Effects:** the study form with its work budget, the effects per metric
  (`IntervalChart` with the zero line) and their table views, the replicate
  differences (`StripChart`), "Open in Explore"; the `#request=` address.
- **Estimation view:** the request form and link, the scores
  (`IntervalChart` with the true effect as the reference line, `DataTable`),
  the confounding sweep (`LineChart`); the `#estimate=` address and the
  tabs remembering each view's address.
- `effects-model.js`, `estimate-model.js` and `synthesis.js` are used as they
  are; their tests do not change.

## Tests

- Playwright: each page's main run, a link restoring a study, an estimation and
  a synthesizer choice, "Open in Explore" opening the right view, no console
  error, 390 px.
- Component tests for the form parts that check bounds from the catalogue.

## Non-goals

- No change to what the pages compute or request.

## Acceptance

- Both pages show the same numbers as on `main` for the same request; every
  address format of today opens the same view; screenshots in both themes.

## Version

`Version: none` — UI only.
