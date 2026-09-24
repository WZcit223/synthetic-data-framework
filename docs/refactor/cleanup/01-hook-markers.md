# PR 1 — Hook markers name their checklist row

## Goal

Every place a real algorithm or real data plugs in is marked with the checklist
row it belongs to, and the checklist shows where each row plugs in, kept in step
by a test.

## Scope

- Marker grammar: `ALGORITHM-HOOK[<ID>]: <text>` and `DATA-HOOK[<ID>]: <text>`,
  where `<ID>` is a row of `docs/ALGORITHM_AND_DATA_CHECKLIST.md` (A1–A5, B1–B4,
  C1–C7, D1–D5). Prose that names the convention itself writes it in double
  backticks (``` ``ALGORITHM-HOOK`` ```) and is not a marker.
- Give each of the 43 existing markers its ID. CLI hints that print a marker
  print the same form.
- New root module `src/sdf/hooks.py` (imports nothing from `sdf`): scan the
  package for markers, read the checklist IDs, render the code index, replace a
  generated block between `<!-- sdf-hooks:begin -->` and `<!-- sdf-hooks:end -->`.
  Locations are `path::symbol` (the enclosing function or class), not line
  numbers, so ordinary edits do not churn the index.
- The checklist gains a "Where it plugs in" section holding that block: one row
  per checklist ID with its markers' locations, or "no code yet".
- `sdf hooks` prints the index; `sdf hooks --update-doc PATH` rewrites the block.
- `hooks_test.py`: every marker has an ID and every ID exists in the checklist;
  no bare `ALGORITHM-HOOK:` / `DATA-HOOK:` remains; the checklist's block equals
  the rendered index. `layering_test.py` ranks `hooks` with the other root
  modules.
- `REFACTOR_PREP.md` §5 step 8 is marked done.

## Non-goals

- No new marker for code that has none today, and no change to the checklist's
  rows.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # hooks_test passes; golden_test unchanged
uv run sdf hooks --update-doc docs/ALGORITHM_AND_DATA_CHECKLIST.md && git diff --exit-code docs/ALGORITHM_AND_DATA_CHECKLIST.md
grep -rnE "(ALGORITHM|DATA)-HOOK:" src                 # nothing
```

## Version

`Version: MINOR 1.0.0 → 1.1.0` — new `sdf hooks` command and a generated code
index in the checklist.
