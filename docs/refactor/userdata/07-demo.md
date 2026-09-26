# U7 — The demo

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §7.

## Goal

One command, and one walkthrough, show the whole product on real data, as a
user would use it.

## Scope

- `sdf demo --source NAME`: the schema and load report; the demand; a table
  synthesizer's privacy and detection; the forecasters' backtest; a world
  from data and its replenishment comparison; the detectors; an effect
  estimated on the source as a dataset (the question chosen in this PR,
  stated with its assumptions).
- `docs/DEMO.md`: the same steps on the pages, with what to look at.
- README's first screen points to the demo.

## Tests

- `sdf demo --source` on a small test source prints every step; without
  `--source`, byte-identical to `main`.

## Non-goals

- No new algorithm; no change to any step's numbers.

## Acceptance

- The required checks.
- The demo run on `uci-retail-daily` (committed, so anyone can repeat it)
  and on the full UCI order lines, their output in the PR.

## Version

`Version: MINOR 1.18.0 → 1.19.0` — `sdf demo` takes `--source`.
