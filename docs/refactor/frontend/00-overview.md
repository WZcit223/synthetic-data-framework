# Frontend refactor — overview

Status: proposed on 2026-09-25. On 2026-09-25 the project lead asked, before
the algorithm phase continues past its PR 1, for the frontend to be rebuilt on
mature libraries: a charting library instead of the hand-written chart code, a
table library instead of the hand-written tables, and, if it helps, a UI
framework (React or Svelte) to organise the pages. This sequence does that. The
algorithm phase resumes with its PR 2 when it is done; its PR 6 (the pages) is
then written on the new stack.

The component and build contract every PR follows is
[`interfaces.md`](interfaces.md).

## Why

`ui/` is 5,946 lines of plain HTML and JavaScript modules, with no dependency
and no build step, a choice recorded three times
([`../structure/00-overview.md`](../structure/00-overview.md),
[`../explore/00-overview.md`](../explore/00-overview.md) Decision 6,
[`../explore/02-pivot-page.md`](../explore/02-pivot-page.md) non-goals). It was
right while the UI was small. It no longer is:

- **Every chart is hand-drawn SVG text.** `ui/chart.js` (272 lines) draws bars
  and lines, and four more charts are drawn by hand elsewhere: the dashboard's
  bars, line and shelf heatmap (`app.js`), the effect and estimator interval
  plots and the replicate strip plot (`effects.js`, `estimate.js`). Each one
  re-implements scales, ticks, tooltips, legends and keyboard access, and
  each new chart (the algorithm phase needs interval bands, per-day error
  lines and a detection chart) adds another.
- **Every table is a template string.** The dashboard, effects and estimator
  tables fill a `<tbody>` by hand, with no sorting or paging; the Explore
  pivot table is 165 lines of DOM code for multi-level headers, sticky row
  labels, collapsible groups, sort and a row budget.
- **State and rendering are interleaved.** `explore.js` is 1,340 lines;
  `effects.js` 503. The pure computation already lives in tested modules
  (`pivot.js`, `effects-model.js`, `estimate-model.js`, `synthesis.js`,
  `palette.js`), but each page redraws by rebuilding `innerHTML` strings.

## Decisions

1. **Svelte 5, built with Vite, as a multi-page app.** Each of the four pages
   keeps its HTML entry and its URL (`index.html`, `explore.html`,
   `synthesizers.html`, `effects.html`) and mounts a Svelte component. Svelte
   compiles components to plain JavaScript (no virtual DOM, a small runtime),
   keeps markup, style and state of a component in one file, and its runes
   (`$state`, `$derived`, `$effect`) replace the hand-written redraw calls.
   *Alternative:* React 19. A larger ecosystem, but a bigger runtime, more
   boilerplate for the same pages, and none of the chosen libraries needs it.
   *Alternative:* no framework, libraries only. It would remove the chart and
   table code but keep the `innerHTML` state handling that makes `explore.js`
   hard to change. (Decision D1.)
2. **Chart.js 4 for every chart.** It draws lines, bars (grouped and stacked),
   filled bands between two lines, scatter and strip plots, with tooltips,
   legends, responsive resizing and animation built in. Two maintained MIT
   plug-ins cover the rest: `chartjs-chart-error-bars` for the interval
   (forest) plots of effects and estimators, and `chartjs-chart-matrix` for the
   shelf-occupancy heatmap. Charts draw on canvas, so every chart keeps its
   table view (the pages already have one) and gets a text summary for screen
   readers. *Alternative:* d3.js. A toolkit for building charts rather than a
   chart library: scales, axes, tooltips and legends would still be our code,
   which is what this sequence removes. (Decision D2; "3d.js" in the request
   is read as d3.js.)
3. **Tabulator 6 for every table.** An MIT table library without a framework
   dependency: sorting, multi-level column headers, frozen columns, collapsible
   row groups, calculated total rows, CSV download and a virtual DOM that
   renders only visible rows (which replaces the pivot's 1,000-row budget).
   *Alternative:* AG Grid Community. Row grouping, pivoting and grouped totals
   are Enterprise (paid) features there. *Alternative:* TanStack Table.
   Headless, so the markup, sticky columns and virtualisation would remain ours.
   (Decision D3.)
4. **The pivot's computation stays ours.** `pivot.js` (387 lines, 24 tests)
   computes filters, aggregations, shares, subtotals and the CSV. No free
   library replaces it well (PivotTable.js is unmaintained and needs jQuery;
   AG Grid's pivot is Enterprise; Perspective ships a 5 MB WebAssembly engine).
   Tabulator renders its result.
5. **The build is part of the repository, the output is not.** `ui/` holds a
   `package.json` with pinned dependencies and a lockfile, and `npm run build`
   writes `ui/dist/`, which is not committed. CI builds it; the API serves it
   with `SDF_UI_DIR=ui/dist`, as today with `ui`. Everything is bundled: no
   CDN, so the dashboard still works offline. Node 22 and npm become
   development requirements for the UI only; the Python package, the CLI and
   the API are untouched and need no Node. (Decision D4.)
6. **The boundary with the API does not move.** One `api()` function in
   `ui/src/lib/api.js` holds the only `fetch`; the UI computes no business
   number (`AGENTS.md` rule 7); every page keeps its address and its link
   formats (`#view=`, `#request=`, `#estimate=`, `#<synthesizer>`), so every
   link already shared keeps working.
7. **Tests at three levels.** The pure modules keep their tests, moved from
   `node --test` to Vitest with their assertions unchanged. Components get
   Vitest tests with Testing Library. Every page gets a Playwright test in
   Chromium against a live API (the four pages, their main actions, a link
   that restores a view, no console error). The Python tests that read `ui/`
   are rewritten to read `ui/src` and the built `ui/dist`.
8. **Light and dark themes.** Colours move to CSS custom properties with a
   light and a dark set, chosen by `prefers-color-scheme`; `palette.js` stays
   the one source of series colours, checked for contrast on both surfaces.
   Today the UI is dark only.

## Decisions for the project lead

- **D1. The framework:** Svelte 5 (recommended), React 19, or none.
- **D2. The chart library:** Chart.js (recommended) or d3.js. The request says
  "3d.js"; this plan reads it as d3.js.
- **D3. The table library:** Tabulator (recommended) or AG Grid Community.
- **D4. The build output:** built in CI and not committed (recommended), or
  committed to `ui/dist/` so that serving the UI never needs Node.

## What the spike showed

A two-page Vite build with Svelte 5, Chart.js 4.5 and both plug-ins, and
Tabulator 6.5, in the environment CI uses (Node 22):

| Bundle | Size | Compressed |
|---|---|---|
| Chart component (Svelte runtime, Chart.js, error bars, matrix) | 226 KB | 78 KB |
| Table component (Tabulator, all modules) | 449 KB | 103 KB |
| Tabulator's dark theme | 30 KB | 4 KB |

The build takes about 1 second. All seven packages are MIT (d3 would be ISC).

## Sequence

Each PR passes the full gate (review, fixes, squash merge) before the next one
starts. Every PR after F1 is checked in Chromium, desktop and 390 px wide,
light and dark, with screenshots in the PR.

| # | Plan | Outcome | Version |
|---|---|---|---|
| F1 | [`01-tooling.md`](01-tooling.md) | Vite and Svelte in `ui/`, the four pages built unchanged, pure modules and their tests moved to `ui/src/lib` and Vitest, CI builds and tests the UI, the API serves `ui/dist` | none |
| F2 | [`02-components.md`](02-components.md) | The chart and table components, the themes, the Playwright harness; the dashboard rebuilt on them | none |
| F3 | [`03-synthesizers-effects.md`](03-synthesizers-effects.md) | The Synthesizers and Effects pages (with the estimation view) rebuilt | none |
| F4 | [`04-explore.md`](04-explore.md) | The Explore page rebuilt: the pivot on Tabulator, its charts, drag and drop, menus, presets and links | none |
| F5 | [`05-cleanup.md`](05-cleanup.md) | The hand-written chart and table code removed, the docs and the algorithm plan's PR 6 updated | none |

## Non-goals

- **No API change** and no change to any Python behaviour or recorded number.
- **No new page and no new feature** beyond the light theme and the table
  features the library gives for free (sorting everywhere, CSV download).
- **No server-side rendering and no SvelteKit.** The API stays the only server;
  the UI is static files.
- **No CDN** and no runtime download.
- **No TypeScript migration.** Components are JavaScript with JSDoc types,
  checked by `svelte-check`.

## Version

`ui/` is not part of the package's versioned interface, so every PR is
`Version: none`. The plan PR itself: `Version: none, documentation and plans only`.
