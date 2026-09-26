# U2 — Evaluation on any source

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §2.

## Goal

A user's synthesizer, or a built-in, can be evaluated on the user's own
data, on the columns the user chooses, through the API and the command line.

## Scope

- `POST /api/v1/synthesis/runs` takes any source, `columns` (with the time
  role's `.hour` and `.weekday`) and `rows` (`sample` or `first`).
- Table runs: the source's kinds become `TableData.kinds`; category labels
  are coded by frequency and decoded in the run table; the answer notes
  categories read as ordered codes.
- Series runs: the source's demand summed over items, with `build_series`'s
  grain rule; a source without demand refused.
- The bundled sources with no column choice run today's reader unchanged.
- The run table's fields come from the source.
- Command line: `--source`, `--columns`, `--rows`, `--param` on `privacy`,
  `synth` and `tstr`; a path still works as today.
- Docs: `docs/PLUGINS.md` (what a table synthesizer receives from a user's
  source), `docs/VALIDATION.md` (no numbers change; the note on category
  codes).

## Tests

- A small user source through every table and series synthesizer, the
  privacy and detection checks included.
- The derived hour and weekday; the row filter; the seeded sample repeatable.
- The bundled sources' answers equal today's (the golden tests).
- A source without demand refused for a series synthesizer; an unknown
  column refused with the columns the source has.

## Non-goals

- No change to a synthesizer or a metric. Category distances stay numeric.
- No page change (U5).

## Acceptance

- The required checks, with `sdf demo` byte-identical and no recorded number
  changed.
- `bayesian-network` and `gaussian-copula` evaluated through the API on a
  user source with a text category column.

## Version

`Version: MINOR 1.14.0 → 1.15.0` — the synthesis run takes any source and a
column and row choice.
