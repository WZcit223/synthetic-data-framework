# PR 4 — Finishing: loose ends and the refactor's records

## Goal

No known loose end of the refactor is left, and its records say it is finished.

## Scope

- Replace `httpx` with `httpx2` in the `dev` group if FastAPI's test client works
  with it on the locked versions, so the deprecation warning goes away; if it
  does not, keep `httpx` and record why in this plan's status. The locked
  Starlette (1.6.0) is the source of the warning: `starlette.testclient` imports
  `httpx2` first and falls back to `httpx` with "Using `httpx` with
  `starlette.testclient` is deprecated; install `httpx2` instead". The swap is
  `uv remove --dev httpx && uv add --dev httpx2`, and `api/app_test.py`'s
  `importorskip` names `httpx2`, or the API tests would skip themselves.
- `ui/favicon.svg` and its `<link>`, so a dashboard load makes no failing request.
- `docs/VALIDATION.md`: prose that quotes a number the generated block already
  holds refers to the block instead; a number the block does not hold is added
  to the snapshot (with its golden test) or the sentence says it is illustrative.
- Records: `REFACTOR_PREP.md` §5 step 9 marked done with what each part became;
  each sequence overview's status points to the next; this overview's status
  lists the merged PRs.
- After merge, delete the remote branches of this refactor, by exact name, each
  only after its pull request is confirmed merged into `main` (the PRs are
  squash-merged, so `git branch --merged` cannot tell):
  - `refactor/layout-01-safety-net`, `refactor/layout-02-import-direction`,
    `refactor/layout-03-module-layout`, `refactor/layout-04-contracts`;
  - `refactor/correctness-plan`, `refactor/correctness-01-validate`,
    `refactor/correctness-02-fail-loudly`, `refactor/correctness-03-metrics`,
    `refactor/correctness-04-demand-profile`;
  - `refactor/structure-plan`, `refactor/structure-01-split-intelligence`,
    `refactor/structure-02-simulation-layer`,
    `refactor/structure-03-retire-rule-policy`,
    `refactor/structure-04-synthesizer-contract`,
    `refactor/structure-05-agent-executor`, `refactor/structure-06-api-state`,
    `refactor/structure-07-ui-separation`;
  - `refactor/cleanup-plan`, `refactor/cleanup-01-hook-markers`,
    `refactor/cleanup-02-data-contracts`, `refactor/cleanup-03-full-audit-log`,
    `refactor/cleanup-04-finishing`;
  - `feature/repo-governance` (merged as #1) and the session branch
    `claude/upbeat-goodall-fb5jdk` (merged as #3);
  - `system-v1/synthetic-data-generation`, whose tip is contained in `main`,
    after tagging that tip `system-v1-snapshot`; `CONTRIBUTING.md`'s branching
    table names the tag instead of the branch.

  A branch whose PR is not merged, or whose tip moved after the merge, is left
  and named in the comment. The PR's closing comment lists what was deleted.
  Only `main` remains. The branches already merged when the plan merges are
  deleted then; the clean-up branches go as each PR merges.

## Non-goals

- No new feature; F1–F3 and the algorithm phase remain for a separate decision.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv sync --locked --extra api && uv run pytest          # no httpx deprecation warning (or its reason recorded)
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
# manual: the dashboard served from ui/ loads without a failed request
```

## Version

`Version: PATCH 1.3.0 → 1.3.1` — development dependency, a UI asset and
documentation.
