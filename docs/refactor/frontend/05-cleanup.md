# F5 — Remove the hand-written chart and table code; update the plans

> Status: planned.

Contract: [`interfaces.md`](interfaces.md).

## Goal

Nothing of the hand-written chart and table code remains, and the plans still
to be implemented are written for the new stack.

## Scope

- Move `niceTicks` and its tests into `lib/format.js` and `format.test.js`,
  unchanged, and point `effects-model.js` at it (§1.3).
- Delete `ui/src/lib/chart.js` and `chart.test.js`, and the `ui/src/legacy/`
  folder (§1.3); `app.js`, `explore.js`, `synthesizers.js`, `effects.js`,
  `estimate.js` and their styles have left it in F2 to F4.
- `docs/ARCHITECTURE.md`: the UI section describes the components and the build.
- The algorithm phase's PR 6 (`../algorithms/06-pages.md`): the Forecasts page
  and the dashboard's interval band are specified on `LineChart`'s `band`,
  `DataTable` and the Playwright tests; its "Charts" section points to §2
  here, and its scope lists the build and navigation changes of a fifth page
  (§1.4), which that PR owns.
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
