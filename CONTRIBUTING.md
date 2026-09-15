# Contributing

This repository follows a protected-`main` + feature-branch workflow. The goal is
a clean, reviewable history that a new engineer — or the CTO — can trust as a
production baseline.

## Branching model

| Branch | Purpose |
| --- | --- |
| `main` | Protected, always-releasable default branch. No direct pushes. |
| `feature/*` | All new work: features, refactors, fixes. Branched from `main`, merged back via PR. |
| `system-v1/synthetic-data-generation` | Frozen snapshot of the initial v1 build, kept for reference. Not part of ongoing flow. |

Examples: `feature/synthetic-pipeline`, `feature/api-refactor`.

## Workflow

```bash
git checkout main && git pull                 # start from latest main
git checkout -b feature/<short-name>          # branch
# ... develop, commit in small logical steps ...
git push -u origin feature/<short-name>       # publish
# open a Pull Request into main
```

Never push directly to `main`; branch protection rejects it. Keep feature
branches short-lived and rebase/merge `main` in if they fall behind.

## `main` branch protection

`main` is configured so that:

- changes land **only** through a Pull Request;
- **direct pushes and force-pushes are blocked**;
- the **CI status check must pass** before merge (lint + tests).

Required approvals are currently **0** because the team is a single maintainer;
CI is the merge gate. When a second engineer or the CTO joins the repo, raise the
required-approvals count to 1.

## Two tracks for Pull Requests

### 1. Implementation PRs — may auto-merge

For PRs that only implement already-agreed requirements or design and **do not
change the overall architecture**:

- ensure `ruff check .` and `pytest` pass locally;
- open the PR (fill the template);
- you may enable **auto-merge** — GitHub merges automatically once CI is green
  and any branch-protection rules are satisfied. No extra human approval step is
  required beyond the protection rules.

### 2. Architecture / directional PRs — human sign-off required

For PRs that change the overall system architecture, introduce a new core
component or tech stack, or perform a large refactor of a core module:

- **first** describe the proposal, scope of impact and alternatives in the PR (or
  a linked issue);
- **@-tag the CTO / designated owner** and get explicit confirmation before
  implementing and merging;
- **do not enable auto-merge** — these are reviewed and merged manually.

When in doubt about which track a change belongs to, treat it as directional and
ask first.

## Local checks

```bash
pip install -e ".[dev]"     # pytest + ruff
ruff check .                # lint
pytest                      # tests
```

Both must pass before opening a PR; CI runs the same checks on Python 3.9 and 3.11.
