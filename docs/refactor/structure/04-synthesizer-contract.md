# PR 4 — Synthesizer contract and registry

> Status: implemented (structure sequence PR 4). No number moved: golden tests,
> `VALIDATION.md` and `sdf demo` are identical to main. Deviations from the scope
> below: `bootstrap_synthesize` was replaced by the `BootstrapTable` class in
> `synthesis/bootstrap.py` instead of moving as a function, so the synthesizer
> has one interface; its first `sample()` reproduces the old function's rows.
> `FittedHourlyDemand` takes the series synthesizer as an argument (default
> `seasonal-profile`), so `synth --synthesizer` reaches it without the fit module
> importing the registry. `synth`, `tstr` and `privacy` print the synthesizer
> they used, and `--synthesizer` offers only the names that produce the kind of
> data the command needs (a series or a table).

Interface contract: [`interfaces.md` §2](interfaces.md#2-synthesizer-contract-sdfsynthesisapi-sdfsynthesisregistry--f1).

## Goal

Every synthesis algorithm is reached through one contract and chosen by name,
so adding a user-written algorithm later (F1) only means registering a class.

## Scope

- New `synthesis/api.py` (`SynthesizerInfo`, `SeriesData`, `TableData`,
  `Synthesizer` protocol) and `synthesis/registry.py` (`SynthesizerRegistry`,
  `default_registry`), exactly as in the contract.
- Built-ins registered by `default_registry()`:
  - `warehouse-spec` wraps `WarehouseGenerator`;
  - `seasonal-profile` is `FittedSeasonalDemand`, which now implements `fit(SeriesData)` / `sample`;
  - `bootstrap-table` moves from `validation/privacy.py` to `synthesis/bootstrap.py`;
  - `gaussian-copula` is registered only when the `synthesis` extra imports.
- Consumers by name, defaults preserving today's numbers:
  - `materialise.build_registry` and `simulation.World.generate` use `warehouse-spec`;
  - `tstr_report(..., synthesizer="seasonal-profile")`;
  - `FittedHourlyDemand` uses `seasonal-profile`;
  - the privacy path and snapshot use `bootstrap-table`;
  - CLI `synth`, `tstr` and `privacy` gain `--synthesizer NAME`, validated against the registry.
- `layering_test.py`: `validation` no longer defines a synthesizer.
- Tests: registry behaviour (duplicate name, unknown name lists valid names),
  every built-in conforms to the protocol, and the contract's `ShuffleSeries`
  plug-in example runs.

## Non-goals

- No entry-point loading (`load_entry_points`), no new algorithm (F1 follow-up).
- No change to any algorithm's output.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test unchanged; contract examples run
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf synth --synthesizer nope                    # usage error listing the registered names
```

## Version

`Version: MINOR 0.11.0 → 0.12.0` — new synthesis contract and registry;
`bootstrap_synthesize` changes import path.
