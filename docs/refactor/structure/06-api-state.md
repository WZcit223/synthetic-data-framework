# PR 6 — Backend state: app factory, atomic snapshot, generation limits

Interface contract: [`interfaces.md` §4.2](interfaces.md#42-target-after-pr-6-app-factory-and-atomic-snapshot).

## Goal

Concurrent requests never see a half-replaced world, one request cannot tie up
the server, and the HTTP contract is covered by tests. Endpoint paths stay the
same.

## Scope

- New `api/state.py`: `GenerateLimits` (defaults `max_skus=500`,
  `max_horizon_days=180`), `Snapshot` (frozen: `World`, `WarehouseIntelligence`,
  `generated_ms`), `WorldStore` (`current`; `regenerate` acquires a lock without
  blocking, raises `GenerationBusy` if another generation holds it, otherwise
  builds a new snapshot and swaps it in one assignment).
- `api/app.py`: `create_app(*, limits=GenerateLimits(), ui_dir=None)`;
  module-level `app = create_app()`; every endpoint reads `store.current` once.
  `/scenarios` and `/workflow/run` use the current snapshot's world instead of
  regenerating their own. `/generate` maps `GenerationBusy` to 409, rejects
  parameters above the limits with 422, and returns `generated_ms`.
- Dashboard: the generation call sends `horizon_days`, and the sliders' ranges
  match the limits.
- `httpx` added to the `dev` dependency group only; new `api/app_test.py`
  (`pytest.importorskip("fastapi")`) with a field test for every endpoint the
  dashboard uses (`REFACTOR_PREP.md` §2.2), plus 409/422 behaviour and a
  concurrent generate/read test that never sees a mixed snapshot.
- CI installs the `api` extra for the test job so these tests run.

## Non-goals

- No path changes, no `/api/v1` (PR 7). No authentication.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run --extra api pytest                              # app_test runs; golden_test unchanged
uv run pytest                                          # still green without the extra (app_test skipped)
```

## Version

`Version: MINOR 0.13.0 → 0.14.0` — app factory and `/generate` limits
(parameters above the limits are now rejected).
