# PR 2 — Fail loudly: wrong or empty input is reported, never absorbed

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
  - `load_online_retail_csv` returns a `LoadReport` (rows read, rows kept,
    skipped rows by reason) alongside SKUs and orders; `register_online_retail`
    and the CLI print it.
  - The date format is a keyword parameter (`date_format`, default the current
    US order), so a day-first source can be read correctly by saying so.
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
