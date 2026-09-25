# F1 — Vite and Svelte in `ui/`, with nothing visible changed

> Status: implemented in this PR (F1).

Contract: [`interfaces.md`](interfaces.md) §1, §5.1 and §5.4.

## Goal

The UI is built and tested like any modern frontend, and CI does both, while
every page looks and works exactly as before.

## Scope

- **Tooling:** the Playwright harness with a smoke spec per page (§5.3);
  `ui/package.json` with the dependencies and scripts of §1.2, the
  lockfile, `vite.config.js` (four HTML entries, the `/api` proxy),
  `svelte.config.js`, `.gitignore` for `ui/node_modules` and `ui/dist`.
- **The four pages are built unchanged.** Vite takes today's HTML pages and
  their module scripts as entries; no page is rewritten yet. The shared
  modules move to `ui/src/lib/` (`common.js` splits into `api.js`,
  `format.js` and `legacy/dom.js`, export by export as in §1.2; `chart.js` moves too, until F5 deletes it) and the page
  scripts and styles to `ui/src/legacy/` (§1.2), with the imports updated and
  no logic changed. In the four HTML entries the only change is the path of
  each `<script type="module" src>` and `<link rel="stylesheet" href>`
  (`app.js` becomes `src/legacy/app.js`, `style.css` `src/legacy/style.css`,
  and so on), which Vite then rewrites to the hashed assets of `ui/dist`; the
  markup, the page URLs and the favicon link stay as they are.
- **Tests:** all seven `ui/*.test.js` files (`chart`, `common`,
  `effects-model`, `palette`, `pivot`, `sources`, `synthesis`) move next to
  their modules and run on Vitest (§5.1), assertions unchanged
  (`common.test.js` split in two, §1.2); `npm run check` runs `svelte-check`.
- **CI:** a `ui` job on Node 22: `npm ci`, `npm run check`, `npm test`,
  `npm run build`; it uploads `ui/dist` for the Python job, which runs the
  UI-reading tests against it (§5.4). The same job then sets up Node 22,
  runs `npm ci` in `ui/` (jobs share no `node_modules`), installs Chromium
  (`npx playwright install --with-deps chromium`), starts the API on
  `ui/dist` and runs `npm run e2e` (§5.3). The `node --test ui/*.test.js`
  step goes.
- **Python tests** that read `ui/` are pointed at the new layout (§5.4); each
  property they check is kept.
- **Docs:** README, ONBOARDING (`cd ui && npm ci && npm run build`, then
  `SDF_UI_DIR=ui/dist`; `npm run dev` for development), ARCHITECTURE (the UI
  section), AGENTS.md rule 7 (the `api()` function is in `ui/src/lib/api.js`),
  CONTRIBUTING (the UI checks), and the three earlier plans that ruled out a
  build step get a note pointing here.

## Tests

- Every pure-module test passes on Vitest with its assertions unchanged.
- The built `ui/dist` serves all four pages with every asset (the Python mount
  test).
- Playwright (§5.3, the harness is part of this PR): each page of `ui/dist`
  loads with no console error and no failed request, and makes the same API
  calls on its first load as on `main`. Screenshots of each page next to
  `main`'s are attached to the PR as a manual check, not a CI assertion.

## Non-goals

- No component, no chart or table library in use yet (F2).
- No visual change.

## Acceptance

- The required checks of `AGENTS.md`, plus the `ui` job, green.
- `SDF_UI_DIR=ui/dist` serves a UI indistinguishable from `main`'s.

## Version

`Version: none` — `ui/` and CI only.
