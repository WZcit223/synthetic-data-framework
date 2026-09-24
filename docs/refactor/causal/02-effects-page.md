# PR 2 — The Effects page

> Status: planned (causal modelling sequence PR 2).

Contract: [`interfaces.md`](interfaces.md) §1.3 to §1.5; tables per
[`../explore/interfaces.md`](../explore/interfaces.md) §1.

## Goal

A user chooses interventions, policies, outcomes and the number of replicates,
runs an effect study, and reads each effect with its interval. It must be
clear at a glance which effects are distinguishable from zero. The result
opens in Explore like any other table.

## Scope

- New `ui/effects.html`, `ui/effects.js` and `ui/effects.css`, plus pure
  helpers in `ui/effects-model.js` with `ui/effects-model.test.js`. The page
  keeps the conventions of the other pages: modules only, no inline handler,
  and the dark theme's tokens.
- **The form** is built from `GET /api/v1/experiments/catalog`:
  - interventions (without `baseline`), policies with their service level, and
    outcomes;
  - replicates (2 to 20) and confidence (80 %, 90 %, 95 %, 99 %);
  - the work budget checked before sending, with the size shown ("10
    replicates × 3 arms × 2 policies × 1 outcome × 200 SKUs × 90 days"), with the
    formula of the contract (§1.5) and the constants from the catalogue's
    `effects` entry, so the page cannot drift from the server.
- **The result:**
  - **An interval chart, one per metric.** Metrics have different units, so
    each gets its own horizontal axis (one axis per chart, small multiples).
    Each row is an intervention × policy: a point at the effect, a line across
    the interval, and a zero line.
  - **Colour.** An interval that excludes 0 is drawn in the series colour. One
    that covers 0 is muted and labelled "not distinguishable from 0", so the
    reading never depends on colour alone.
  - **The table** has the effect, the interval, the relative change and the
    baseline and treated means, with the same formatting as Explore.
  - **A replicate view** for one metric shows each replicate's paired
    difference as a dot, with the mean.
  - **Hover** shows a tooltip with the numbers, and every chart has a table
    view.
- **Open in Explore** for the effects table and for the replicate rows. This
  adds the `effects` source shape to Explore's source validator and loader,
  as the exploration contract §3.2 now lists it, and a Node test of a link
  that round-trips through the validator.
- Navigation: the four pages link each other. The UI contract test covers the
  new page (paths in OpenAPI, no inline handler, assets and modules load,
  navigation links).
- Tests (Node):
  - the budget computation;
  - reading the interval ("covers 0" at the edges, including a zero-width
    interval at 0);
  - the chart's scale with a common zero;
  - the Explore link.
- Docs: README (the Effects page), `ARCHITECTURE.md`'s UI section, and this
  plan's status note.

## Non-goals

- No backend change. If a need for one appears, it goes back to PR 1's
  contract first.
- No estimation view (PR 5).
- No saving of studies on the server. The page address keeps the request, so a
  link reproduces the study.

## Acceptance

- The checks of PR 1's acceptance, and `node --test ui/*.test.js`.
- In Chromium against `SDF_UI_DIR=ui uvicorn sdf.api.app:app`:
  - The study of PR 1's acceptance shows `holding_cost` excluding 0 and
    `unmet_units` covering 0, with the same numbers as `sdf effects`.
  - Open in Explore reproduces both tables.
  - A request over budget is stopped in the page with its size shown.
  - The page reads correctly from 700 to 1440 px wide.
  - There is no failed request and no console error.
- The chart's two colours pass the palette validator on the dark surface.

## Version

`Version: none` — UI only: the `ui/` directory is not part of the Python
distribution.
