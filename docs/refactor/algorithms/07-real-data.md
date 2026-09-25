# PR 7 — Two years of real demand (only with decision D1)

> Status: planned. Decision D1 (a) was taken on 2026-09-25: the compact daily
> table is committed. The PR starts once the project lead provides the
> dataset file.

Contract: [`interfaces.md`](interfaces.md) §9.

## Goal

Every algorithm of PR 1 to 5 is validated on real demand long enough for
weekly and yearly patterns, not only on benchmarks, the synthetic world and
the 5-day extract.

## Scope

- **`sdf prepare-retail`** and **`DemandTable.from_daily_csv`** (§9), with
  the adapter's cleaning rules reused, not copied. Today the adapter
  (`sdf.foundation.adapters.retail_csv`) skips rows without a `StockCode`
  and turns negative quantities into cancelled orders; it does not drop
  non-product codes (postage `POST`, manual `M`, bank charges and the like).
  This PR adds that rule to the adapter as an option, `drop_non_product`,
  off by default so every existing load and recorded number is unchanged,
  and `prepare-retail` turns it on.
- **With D1 (a):** `data/online_retail_ii_daily_top200.csv` committed with
  its attribution in the header and in `docs/DATASETS.md` (source, licence
  CC BY 4.0, date of download, the command that made it). The file's size is
  recorded in the PR; if it is over 1 MB, the PR lowers `--top` and says so.
- **Real-data runs:** `sdf forecast`, the replenishment replay and
  `sdf anomalies` accept `--daily-csv PATH`; with D1 (a), CI runs them on the
  committed table.
- **Docs:** a new section in `docs/VALIDATION.md`, "Two years of real
  demand", with the backtest of every forecaster (horizon 28, 8 origins), the
  replenishment comparison out of sample (fitted on the first year, replayed
  on the second), and the anomaly detections the detectors agree on; the
  checklist's "Minimum data" list marks item 1 as met.

## Tests

- `drop_non_product`: off, the adapter loads exactly as today; on, every
  code of the contract's list (§9) is skipped, whatever its case and
  surrounding whitespace (` post `, `Post`), as are codes starting with
  `GIFT_` or `TEST`, and each is counted in the load report; a code with no
  digit that is not on the list (for example `XYZ`) is kept and reported.
- `prepare-retail` on a small hand-made file in the UCI layout: cancelled
  lines and non-product codes left out of demand, days with no sale present
  as 0, SKUs ranked by units, the header comment written.
- `from_daily_csv` reads back what `prepare-retail` wrote.
- With D1 (a), a test pins the committed table's shape and totals, so a
  changed file is noticed.

## Non-goals

- No full order-level file in the repository; only the daily table.
- No change to the synthetic sample, the extract or any recorded number.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`.
- The PR records, on the real table: each forecaster's WAPE,
  `relative_wape` and both coverages; the cost saving of `cost-based` over
  `service-level-95` out of sample; and the detections. Where a result on
  real data contradicts the benchmark, the PR says so; the plan is not
  adjusted to hide it.

## Version

`Version: MINOR 1.13.0 → 1.14.0` — a new command, a new reader and a new
adapter option. PR 6 changes no version, so PR 7 follows PR 5's 1.13.0; if
another release lands first, the PR states its actual transition.
