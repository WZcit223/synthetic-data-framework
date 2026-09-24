# PR 4 — Finishing: loose ends and the refactor's records

## Goal

No known loose end of the refactor is left, and its records say it is finished.

## Scope

- Replace `httpx` with `httpx2` in the `dev` group if FastAPI's test client works
  with it on the locked versions, so the deprecation warning goes away; if it
  does not, keep `httpx` and record why in this plan's status.
- `ui/favicon.svg` and its `<link>`, so a dashboard load makes no failing request.
- `docs/VALIDATION.md`: prose that quotes a number the generated block already
  holds refers to the block instead; a number the block does not hold is added
  to the snapshot (with its golden test) or the sentence says it is illustrative.
- Records: `REFACTOR_PREP.md` §5 step 9 marked done with what each part became;
  each sequence overview's status points to the next; this overview's status
  lists the merged PRs.
- After merge, delete the merged remote branches (`refactor/*`,
  `feature/repo-governance`, `system-v1/synthetic-data-generation`) and list them
  in the PR's closing comment.

## Non-goals

- No new feature; F1–F3 and the algorithm phase remain for a separate decision.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv sync --extra api && uv run pytest                   # no httpx deprecation warning (or its reason recorded)
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
# manual: the dashboard served from ui/ loads without a failed request
```

## Version

`Version: PATCH 1.3.0 → 1.3.1` — development dependency, a UI asset and
documentation.
