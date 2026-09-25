# F5 — Remove the hand-written chart and table code; update the plans

> Status: planned.

Contract: [`interfaces.md`](interfaces.md).

## Goal

Nothing of the hand-written chart and table code remains, and the plans still
to be implemented are written for the new stack.

## Scope

- Delete `ui/chart.js` and `chart.test.js`, and any page code left from before
  F2 to F4; `app.js`, `explore.js`, `synthesizers.js`, `effects.js`,
  `estimate.js` are gone by then.
- `docs/ARCHITECTURE.md`: the UI section describes the components and the build.
- The algorithm phase's PR 6 (`../algorithms/06-pages.md`): the Forecasts page
  and the dashboard's interval band are specified on `LineChart`'s `band`,
  `DataTable` and the Playwright tests; its "Charts" section points to §2 here.
- `docs/ROADMAP.md` and the README: "offline" stays true and says why (all
  assets are bundled).
- A short "Adding a chart or a table" section in ARCHITECTURE, for the next
  page.

## Tests

- The full UI suite and the Python suite; `rg` finds no `innerHTML` building a
  chart or a table in `ui/src`.

## Non-goals

- No feature change.

## Acceptance

- The required checks and the `ui` job green; the algorithm phase can resume
  with its PR 2.

## Version

`Version: none` — UI and documentation.
