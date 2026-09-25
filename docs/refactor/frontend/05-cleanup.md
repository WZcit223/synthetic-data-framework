# F5 — Remove the hand-written chart and table code; update the plans

> Status: implemented. One change to the scope below: `niceTicks` was not
> moved but deleted, with `effects-model.js`'s `axisFor`, its only user, which
> no page used any more (the Effects charts take their axes from Chart.js).
> `esc` went too, since no page writes HTML (`fmt` now returns text as it is),
> and so did `palette.js`'s `heat()`, used only by its own test.

Contract: [`interfaces.md`](interfaces.md).

## Goal

Nothing of the hand-written chart and table code remains, and the plans still
to be implemented are written for the new stack.

## Scope

- Move `niceTicks` and its tests into `lib/format.js` and `format.test.js`,
  unchanged, and point `effects-model.js` at it (§1.3).
- Delete `ui/src/lib/chart.js` and `chart.test.js` (§1.3). The `ui/src/legacy/`
  folder is already gone: F4 deleted it once its last page was rebuilt.
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
