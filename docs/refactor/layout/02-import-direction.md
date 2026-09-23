# PR 2 — Import direction: no reverse edges, relative imports, no import-time side effects

> Status: implemented (layout sequence PR 2). Acceptance commands below pass;
> golden numbers and `sdf demo` output unchanged.

## Goal

Make the layer direction real and enforced: nothing below an entry point
imports an entry point, the synthesis layer does not import the application
layer, importing any submodule does not execute the whole package, and
intra-package imports follow `python-imports.instructions.md`.

## Scope

- New `synthesis/materialise.py` holding `build_registry(spec) -> (SyntheticWarehouse, DataSourceRegistry)`,
  moved verbatim from `cli.py`. Callers (`cli`, `api/app`, `workflow/pipeline`,
  `synthesis/scenarios`, tests) import it from there. `cli.build_registry` is
  removed, not aliased.
- New `synthesis/spec.py` holding `GenerationSpec` (moved from `warehouse.py`),
  so `scenarios.py` and the API can depend on the spec without the generator.
  `warehouse.py` imports it from `.spec`.
- `run_scenarios` moves from `synthesis/scenarios.py` to a new
  `application/scenarios.py`; `synthesis/scenarios.py` keeps only `SCENARIOS`
  and `_apply` (renamed `apply_scenario`, a pure `GenerationSpec -> GenerationSpec`
  transform). `cli` and `api` import the runner from `application`.
- `sdf/__init__.py` exports only `__version__`. The four re-exported names
  (`DataSourceRegistry`, `WarehouseGenerator`, `GenerationSpec`,
  `WarehouseIntelligence`) are imported from their modules by the two callers
  that use them (README snippet, `cli`).
- `api/app.py` raises `ImportError` (not `SystemExit`) when FastAPI is missing;
  the CLI is not affected because it never imports the API.
- Every intra-package import becomes a single-dot relative import inside its
  package, and an absolute `sdf.<pkg>` import across packages, per the
  instruction. Lazy (inside-function) imports that existed only to dodge a
  reverse edge move to module level; lazy imports that guard an optional
  dependency (`sdv_synth`, FastAPI) stay.
- New `src/sdf/layering_test.py`: parses every module's imports with `ast`
  and asserts the direction
  `foundation < synthesis < application < {observability, workflow, api, cli}`
  (PR 3 extends the ranking with `analytics` and `validation`), and asserts
  that importing `sdf.foundation.schema` alone does not import
  `sdf.application`.
- `economics.py` stops reading `intel._sku_daily_stats`: the method is made
  public as `WarehouseIntelligence.sku_daily_stats()` (rename only; PR 3
  replaces its body with the shared aggregation).

## Non-goals

- No file moves other than the three named above (`build_registry`,
  `GenerationSpec`, `run_scenarios`).
- No change to function bodies except import statements and the one rename.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check   # I and TID252 clean; no absolute sdf.<same package> imports remain (reviewed by hand)
uv run pytest                                     # all tests incl. golden_test and layering_test pass
uv run python -c "import sdf.foundation.schema, sys; assert 'sdf.application' not in sys.modules"
uv run python -c "import sdf.synthesis.scenarios, sys; assert 'sdf.cli' not in sys.modules and 'sdf.application' not in sys.modules"
uv run sdf demo                                   # output identical to the capture
```

## Version

`Version: MINOR 0.2.0 → 0.3.0` — import paths of `build_registry`,
`run_scenarios` and `GenerationSpec` change and the package root no longer
re-exports four names. None of these is a documented public interface (see
`00-overview.md`, Consequences), so this is not treated as MAJOR; the project
lead confirms or overrides in review.
