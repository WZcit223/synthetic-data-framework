# PR 2 — Fail loudly: wrong or empty input is reported, never absorbed

> Status: implemented (correctness sequence PR 2). Golden numbers and `sdf demo`
> output unchanged. The CSV sections of the `sdf validate` block gained a
> "rows kept / read" row. `--date-format` is also offered on `privacy`, which
> reads the same InvoiceDate column; `sdv` keeps its own reader (optional extra).

## Goal

When input is empty, malformed or ambiguous, the code either raises an error
that names the problem or returns a result that says what was skipped and why.
No function pretends a problem did not happen.

## Scope

- **Empty data answers "no data".**
  - `backtest` / `compare_models` on fewer than 3 points return
    `{"error": ...}` instead of `IndexError`.
  - `KnowledgeQA._forecast` answers "no demand history" on an empty registry.
  - `WarehouseAgent.handle` checks `financial_impact`'s `error` before reading
    its fields (the `KeyError: 'assumptions'` path).
- **Duplicates and unknown names raise.**
  - `DataSourceRegistry.register(..., *, replace: bool = False)` raises
    `ValueError` on an existing name unless `replace=True`.
  - `run_scenarios(names=[...])` raises `KeyError` listing the valid names for
    an unknown scenario; `apply_scenario` keeps its signature.
  - `QualityReport.passed` is `False` when no check ran.
- **Skipped rows are counted.**
  - `load_online_retail_csv` returns `(skus, orders, report)` where `report`
    is a `LoadReport` (rows read, rows kept, skipped rows by reason);
    `register_online_retail` returns the `LoadReport` (which also carries the
    SKU and order counts) instead of a `(n_skus, n_orders)` tuple.
  - Every caller is updated in this PR: the `backtest`, `synth` and `tstr`
    CLI commands (they print the skipped-row summary when it is not empty),
    the workflow's real-CSV `ingest` step (its artifact includes the report,
    so skip reasons reach the run record), the adapter package exports, and
    the tests and golden paths that unpack the loader.
  - The date format is a keyword parameter `date_format` (default: the current
    month-first order) on `load_online_retail_csv` and
    `register_online_retail`, passed through `warehouse_pipeline(...,
    date_format=...)` and a `--date-format` option on the CSV commands, so a
    day-first source can be read correctly on every real-CSV path.
- **Pipeline keeps reasons.** The workflow report carries each step's
  `skipped` reason instead of reducing economics to a `None` saving.
- **Repeated generation differs.** `FittedSeasonalDemand` creates its random
  generator once in `__init__`; `generate(seed=...)` can still pin one call.
  The golden paths call `generate()` once per model, so no recorded number
  moves.
- **Numeric options by keyword.** Public functions with two or more optional
  numeric parameters take them keyword-only (`*`):
  `replenishment_ss_policy`, `stocktake_discrepancies`, `financial_impact`
  (`cost_model`, `max_skus`), `backtest`/`compare_models` (`test_len`),
  `privacy_report`, `bootstrap_synthesize`, `gaussian_copula_fidelity`,
  `hourly_business_series`, `FittedHourlyDemand.fit`. All in-repo callers are
  updated.
- Colocated tests for every guard above (one test per behaviour: the error is
  raised or reported and names the problem).

## Non-goals

- No change to any formula; `golden_test.py` literals stay as they are.
- No entity-level `__post_init__` validation of `SKU`/orders yet (needs the
  `abc_class=None` decision in the structural sequence).
- `sdv_synth`'s broad `except` stays until the optional-extra rework.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                     # new guard tests pass; golden_test unchanged
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf demo                   # output identical to main
```

## Version

`Version: MINOR 0.5.0 → 0.6.0` — `register` now raises on duplicates, several
functions take their numeric options by keyword only, and the CSV loader
returns a load report.
