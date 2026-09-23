# AGENTS.md

Instructions for humans and coding agents working on this repository.

## Additional repository instructions

Agents must discover and read the applicable instruction files under
[`.github/instructions/`](.github/instructions/) before starting work. These are
required repository rules, not optional reference material.

- Use each file's `applyTo` patterns and `description` to determine its scope.
  Read the full contents of every applicable file before performing the related work.
- Apply workflow and environment instructions according to the activity being
  performed, including files without `applyTo`. Read the
  [shell-environment rules](.github/instructions/shell-environment.instructions.md)
  before terminal work and the
  [branch and PR workflow](.github/instructions/branch-and-pr-workflow.instructions.md)
  before making changes.
- Follow the [implementation and core-logic test rules](.github/instructions/implementation-and-tests.instructions.md)
  when implementing features, fixing bugs, refactoring or generating code:
  minimal abstraction, minimal scope expansion, `@dataclass` configuration,
  type-hinted public APIs, and a colocated `<source>_test.py` for the core path
  and its most likely failure patterns.
- Read and follow the [in-branch API compatibility rules](.github/instructions/in-branch-api-compat.instructions.md)
  before evolving in-progress APIs within a branch or adding compatibility wrappers,
  adapter layers, deprecated aliases or parallel interfaces.
- Follow the [Python import rules](.github/instructions/python-imports.instructions.md)
  when creating, editing or refactoring imports: single-dot relative imports for
  modules and subpackages inside the current package, absolute imports for parent
  packages, packages outside the current one, the standard library and third-party
  modules, never `..` or `...`, and stdlib / third-party / local groups.
- Follow the [repository documentation boundaries](.github/instructions/repository-doc-boundaries.instructions.md)
  when creating, editing or reorganizing `README.md`, `AGENTS.md`,
  `CONTRIBUTING.md` or anything under `docs/`.
- Recheck applicable instructions when the task expands to new files or activities.
  Do not assume the IDE or agent runtime has loaded them automatically.
- Explicit user instructions and higher-priority system/developer instructions
  take precedence over repository instruction files.

## How the instruction files map onto this repository

The instruction files are shared with other projects and describe some things by
the layout of those projects. Read them with the following mapping; where the
mapping is not yet decided, the item is marked **pending** and the instruction's
intent still applies.

- **Package layout.** This is a single uv-managed package under `src/sdf/`
  (`uv_build` backend, `uv.lock` committed), not a uv workspace. There is no
  `packages/` directory and no `website/`. Dependencies change only through
  `uv add` / `uv remove` so the lock file stays current; pip is not supported. Where an
  instruction names `packages/*`, read "the single package"; where it names
  `website/docs/`, read "there is no public site; user-facing documentation is
  `README.md` and `docs/`".
- **Version bump.** The version lives in `[project].version` in `pyproject.toml`
  and is mirrored by `__version__` in `src/sdf/__init__.py`; a bump changes both
  in the same PR: run `uv version --bump <kind>` and mirror the result in
  `__version__` by hand.
  The version decision and its `Version:` line are still required at the end of
  every PR description and refactor plan file. Shipped code is `src/sdf/`.
- **Tests.** Run with `uv run pytest`; `testpaths` covers both `src` (colocated
  `<source>_test.py` files, starting with `src/sdf/cli_test.py`) and the legacy
  `tests/test_generators.py`. New tests follow the colocated rule.
- **Configuration conventions.** There is no `models/model_config.py`. The
  established config object in this repository is `GenerationSpec` in
  `src/sdf/synthesis/warehouse.py`; new config dataclasses follow its shape and
  are validated in `__post_init__` as the instruction describes. Logging uses the
  standard library; do not introduce `loguru`.
- **Import rules and formatting.** `ruff` is configured to match sciloom
  (`pyproject.toml`): `ruff check` enforces the import grouping (`I`) and the
  parent-relative ban (`TID252`), and `ruff format --check` enforces layout.
  Preferring single-dot imports inside a package is reviewed by hand. The
  earlier compact one-statement-per-line style is gone; do not reintroduce it.
- **Documentation locations.** Internal architecture, validation results and
  refactor plans live in `docs/`. Root Markdown is `README.md`, `AGENTS.md`,
  `CLAUDE.md` and `CONTRIBUTING.md`; the last two are accepted exceptions to the
  "README and AGENTS only" rule because Claude Code reads `CLAUDE.md` and the
  contributor policy predates the instruction set. Refactor plans go under
  `docs/refactor/<slug>/` as the branch and PR workflow describes; the current
  pre-refactor audit is [`docs/REFACTOR_PREP.md`](docs/REFACTOR_PREP.md).
- **PR policy.** [`CONTRIBUTING.md`](CONTRIBUTING.md) defines two PR tracks:
  implementation PRs may auto-merge on green CI; architecture or directional PRs
  need a written plan approved by the project lead before merge. The instruction
  files' review gate applies on top of that policy, and the project lead's
  approval is what closes the gate for a directional PR.

## Project invariants

1. **Framework and algorithm are separate.** The framework proves the end-to-end
   flow with deterministic, dependency-free stand-ins; real models plug in at the
   points marked `# ALGORITHM-HOOK` and real data at `# DATA-HOOK`, catalogued in
   [`docs/ALGORITHM_AND_DATA_CHECKLIST.md`](docs/ALGORITHM_AND_DATA_CHECKLIST.md).
   Keep those markers when moving code and add one when introducing a new stand-in.
2. **The core's runtime dependencies are numpy, scipy, scikit-learn and click**
   (decided 2026-09-23; before that the core was standard-library only). Anything
   heavier (SDV/copulas, FastAPI, LightGBM, the pywhy causal stack) lives in the
   `pyproject.toml` extras, is imported lazily, and a test that needs it skips
   with `pytest.importorskip`. New numerical code uses numpy/scipy rather than
   hand-rolled loops; existing pure-Python stand-ins are ported in the refactor
   step that touches them.
3. **Layer direction is Foundation → Synthesis → Application → entry points**
   (`cli`, `api`, `workflow`). Do not add imports that point the other way; the
   known violations and their fix are listed in `docs/REFACTOR_PREP.md` §1.2.
4. **The generator's random-number consumption order is a contract.** Changing
   the order or count of `self._rng` calls in `WarehouseGenerator` changes every
   recorded number; do it only in a PR whose stated purpose is that change.
5. **Measured numbers are honest.** `docs/VALIDATION.md` records what the code
   produced, including where a model did not win. When a change moves a recorded
   number, update the document in the same PR and say why.
6. **The agent's approval gate is a guarantee, not a convention.** A tool with
   `requires_approval=True` must never have its function executed by the planner;
   see `docs/REFACTOR_PREP.md` §3.2 for the current gap.

## Required checks

Run before opening or updating a PR, from the repository root:

```bash
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run pytest
uv run python demo/run_demo.py
```

CI (`.github/workflows/ci.yml`) runs exactly these on Python 3.12, 3.13 and 3.14
for every PR into `main`, then `git diff --exit-code` to catch anything a check
rewrote. The optional extras are not installed in CI. Enable the versioned
pre-commit hook once per clone with `git config core.hooksPath .githooks`; it
runs `ruff check --fix-only` and `ruff format` on staged Python files.
