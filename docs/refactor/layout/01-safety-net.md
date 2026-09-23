# PR 1 — Safety net: characterisation tests and colocated test layout

## Goal

Lock the current behaviour in tests that live next to the code, so that the
pure-move PRs that follow can be verified mechanically, and remove the two
`sys.path` hacks that let tests run against an uninstalled tree.

## Scope

- Add `src/sdf/conftest.py` with a session-scoped `default_world` fixture
  (`build_registry(GenerationSpec())` plus its `WarehouseIntelligence`) so the
  world is generated once per test session.
- Add `src/sdf/golden_test.py` asserting every value in
  `docs/REFACTOR_PREP.md` §2.5 for the default world and for the two bundled
  CSVs (`data/sample_online_retail_ii.csv`, `data/online_retail_ii_2010_10k.csv`),
  with an exact match for integers and a ±0.5 % tolerance for floats.
- Split `tests/test_generators.py` by the module each test exercises into
  colocated files: `synthesis/warehouse_test.py`, `synthesis/quality_test.py`,
  `synthesis/forecast_test.py`, `synthesis/fit_test.py`, `synthesis/tstr_test.py`,
  `synthesis/anomaly_test.py`, `synthesis/privacy_test.py`,
  `synthesis/scenarios_test.py`, `synthesis/sdv_synth_test.py`,
  `application/warehouse_demo_test.py`, `application/knowledge_test.py`,
  `application/economics_test.py`, `application/agent_test.py`,
  `observability_test.py`, `workflow/pipeline_test.py`. Test bodies move
  unchanged except for fixture use; the optional-dependency test switches from
  `return` to `pytest.importorskip("copulas")` so it reports as skipped, not
  passed.
- Delete `tests/` and its `sys.path.insert`; set `testpaths = ["src"]`.
- Delete `demo/run_demo.py` (its `sys.path.insert` is the other hack; the
  command is `uv run sdf demo`). Update README, ONBOARDING, AGENTS.md required
  checks and CI (`uv run sdf demo` replaces `uv run python demo/run_demo.py`).

## Non-goals

- No change under `src/sdf/` other than adding test and conftest files.
- No new assertions beyond the golden numbers and the moved tests.

## Acceptance

```bash
uv sync --locked
uv run ruff check && uv run ruff format --check
uv run pytest                      # 18 moved + 18 cli + golden tests pass; sdv test reports "skipped"
uv run sdf demo                    # output identical to the current capture
git ls-files tests demo            # empty
grep -rn "sys.path" src demo tests # no matches
```

## Version

`Version: none` — tests, fixtures and documentation only; `src/sdf/` runtime
code is untouched.
