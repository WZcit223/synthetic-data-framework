# U6 — Real data

> Status: planned. Replaces algorithm PR 7 ([`../algorithms/07-real-data.md`](../algorithms/07-real-data.md)).

Contract: [`interfaces.md`](interfaces.md) §6. Decision E3.

## Goal

Real public datasets enter through the same path a user's file takes, and
every algorithm is measured on real demand.

## Scope

- `sdf data fetch NAME [--from FILE]`, with the UCI Online Retail II and M5
  conversions; a new extra, `data` (`openpyxl`).
- The non-product codes of UCI left out, listed in the provenance (from
  algorithm PR 7's `drop_non_product`).
- `docs/DATASETS.md`: each dataset's URL, licence, conversion and date.
- **The committed table** `data/uci_retail_daily_top200.csv` (D1 (a)): the
  third bundled source, `uci-retail-daily` (§6).
- `docs/VALIDATION.md`, "Real demand", in the generated block, from the
  committed table: the forecasters' backtest (horizon 28, 8 origins), the
  replenishment comparison out of sample on a world from data, the detectors
  on its demand. Beside it, by hand, the table synthesizers' privacy and
  detection on the full order lines, with the commands that reproduce them.
- The checklist's "Minimum data" list marks item 1 as met.

## Tests

- The conversions on tiny archives built in the test (an Excel workbook in
  a zip; an M5-shaped wide file); no network in any test.
- The committed table's shape and totals pinned.
- `fetch` without network fails naming the host and `--from`.

## Non-goals

- No full order lines committed; only the compact table. No change to a
  model or a policy because of these numbers; a finding becomes its own
  proposal.
- M5 numbers are committed only after the project lead confirms its terms
  allow it.

## Acceptance

- The required checks, with `sdf demo` byte-identical and the generated
  block of `docs/VALIDATION.md` unchanged.
- The committed table made from UCI Online Retail II, by `fetch` from the
  host or `--from` a file the project lead provides, and the "Real demand"
  section recomputed by `sdf validate` in CI.

## Version

`Version: MINOR 1.17.0 → 1.18.0` — a new command and a new extra.
