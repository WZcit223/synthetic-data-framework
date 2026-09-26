# U5 — The Data page

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §5.

## Goal

Everything U1 to U4 opened, in the browser: a user uploads a file, checks how
it was read, and uses it on every page.

## Scope

- `ui/data.html` and its Svelte page: upload, preview, kinds and roles as
  choices (an ambiguous date format must be picked), the check's report, the
  list of sources with their actions.
- The Synthesizers and Forecasts pages read `/sources` for their pickers,
  with the column and row choice on the Synthesizers page; links carry the
  source's name.
- The dashboard names a world from data and its cut, and labels the
  synthesized panels.
- `api()` accepts an answer with no body.
- Docs: README, `docs/ONBOARDING.md`, the pages' section of
  `docs/ARCHITECTURE.md`.

## Tests

- Unit tests of the page's pure helpers (schema edits, name proposal, the
  picker lists).
- End-to-end: upload a small CSV, fix a role, save, open it in Explore, run
  a synthesizer on it, make it the world, remove it.

## Non-goals

- No Python change. Anything the page needs from the server is found by
  then, or goes in its own PR first.

## Acceptance

- The UI checks (`npm run check`, unit tests, build, end-to-end) and the
  Python checks, with no recorded number changed.

## Version

`Version: none` — UI and documentation only.
