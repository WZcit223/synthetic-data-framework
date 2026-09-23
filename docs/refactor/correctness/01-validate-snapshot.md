# PR 1 — `sdf validate`: one source for every recorded number

> Status: implemented (correctness sequence PR 1, #9). The snapshot records a
> CSV's file name rather than its path so the output does not depend on the
> working directory; CSV headings are derived from the input. Since correctness
> PR 3 every backtest row also carries `WAPE_pct` (JSON and markdown).

## Goal

Every number the repository records (golden tests, `VALIDATION.md`) is
computed by one function, printed by one command, and checked by a test, so a
document can no longer drift from the code.

## Scope

- New `src/sdf/application/snapshot.py`:
  - `default_world_snapshot(spec: GenerationSpec | None = None) -> dict` —
    registry counts, structural quality, KPIs, ABC mix, rule-based
    replenishment (count + top 3), replenishment simulation, (s,S) at 90/95/99 %,
    rule anomalies, demand anomalies (count + top), vision stocktake, the
    backtest table, economics, the scenario table, and the agent's
    "reorder & impact" run (plan, step count, proposed actions).
  - `csv_snapshot(path: str) -> dict` — SKU/order counts, series shape, the
    backtest table, fitted fidelity, TSTR and privacy.
  - `snapshot(sample_csv: str, retail_csv: str) -> dict` combining the three.
  - `render_markdown(snap: dict) -> str` — the tables that `VALIDATION.md`
    embeds.
  Values are plain JSON types, rounded as the existing functions already round
  them.
- New CLI command `sdf validate`:
  - `--format json|markdown` (default `json`);
  - `--sample PATH` / `--retail PATH` default to the two bundled CSVs;
  - `--update-doc PATH` rewrites the block between
    `<!-- sdf-validate:begin -->` and `<!-- sdf-validate:end -->` in `PATH`.
- `golden_test.py` asserts on the snapshot dictionaries instead of calling
  each function itself, for every golden number including the agent run; the
  expected literals do not change.
- New `src/sdf/application/snapshot_test.py`:
  - the generated block in `docs/VALIDATION.md` equals
    `render_markdown(snapshot(...))`, so a changed number without a regenerated
    document fails the suite;
  - `--update-doc` only touches the marked block.
- `docs/VALIDATION.md`: add a "Reproducible numbers" section holding the
  generated block. Hand-copied tables that the snapshot covers (backtest tables
  for both CSVs, the C2 (s,S) table, the TSTR table, the economics table) are
  replaced by a sentence pointing to the generated block; the narrative stays.
  The stale C2 values (33/38/43, 2 626/3 369/4 764) disappear as a result.
  The full-dataset headline stays and is labelled "manual run on the full
  dataset, not reproducible from the repository".
- `docs/REFACTOR_PREP.md` §5 step 7 marked done; `CONTRIBUTING.md` /
  `AGENTS.md` mention `uv run sdf validate --update-doc docs/VALIDATION.md`
  as the way to refresh recorded numbers.

## Non-goals

- No change to any computed value; `golden_test.py` literals stay as they are.
- No new metric.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test unchanged; snapshot_test passes
uv run sdf validate | python -m json.tool > /dev/null  # valid JSON
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf demo                                        # output identical to main
```

## Version

`Version: MINOR 0.4.1 → 0.5.0` — adds the `sdf validate` command and the
`sdf.application.snapshot` module.
