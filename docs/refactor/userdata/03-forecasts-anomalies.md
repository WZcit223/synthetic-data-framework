# U3 — Forecasts and anomalies on any source

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §3.

## Goal

Every forecaster and detector, the user's own included, runs on the user's
demand as it runs on the world and the benchmark.

## Scope

- `POST /forecasts/backtest` takes `source: {"data": {"name": …}}`: the
  source's daily demand, at most 400 items, the busiest first; a source too
  short for the request refused with the days it has and needs.
- `GET /anomalies` takes `source=`: a frame with the `demand` signal; a
  detector needing other signals refused by the existing guard.
- Command line: `--source` on `forecast`, `anomalies` and `backtest`.
- Docs: `docs/VALIDATION.md` (the backtest's sources), `docs/PLUGINS.md`
  (a forecaster or detector on a user's demand).

## Tests

- A small source backtested with every built-in forecaster; the busiest
  items kept; a short source refused.
- Anomalies on a source with `seasonal-residual`; `isolation-forest` refused
  with the missing signals named.
- The world and benchmark answers unchanged.

## Non-goals

- No page change (U5). No new forecaster or detector.

## Acceptance

- The required checks, with `sdf demo` byte-identical and no recorded number
  changed.
- A backtest on the bundled `retail-10k` is refused as too short, and one on
  a longer test source answers every table the page reads.

## Version

`Version: MINOR 1.15.0 → 1.16.0` — a third backtest source and a source
choice for anomalies.
