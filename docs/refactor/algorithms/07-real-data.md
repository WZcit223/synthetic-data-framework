# PR 7 — Two years of real demand (only with decision D1)

> Status: planned; waits for decision D1 of the overview. With D1 (c) it is
> dropped.

Contract: [`interfaces.md`](interfaces.md) §9.

## Goal

Every algorithm of PR 1 to 5 is validated on real demand long enough for
weekly and yearly patterns, not only on benchmarks, the synthetic world and
the 5-day extract.

## Scope

- **`sdf prepare-retail`** and **`DemandTable.from_daily_csv`** (§9), with
  the adapter's cleaning rules reused, not copied.
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

- `prepare-retail` on a small hand-made file in the UCI layout: cancellations
  and non-product codes dropped, days with no sale present as 0, SKUs ranked
  by units, the header comment written.
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

`Version: MINOR` from the version then current — a new command and a new
reader.
