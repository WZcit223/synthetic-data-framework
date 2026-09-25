# Contributing

This repository follows a protected-`main` + feature-branch workflow. The goal is
a clean, reviewable history that a new engineer can trust as a production baseline.

## Branching model

| Branch | Purpose |
| --- | --- |
| `main` | Protected, always-releasable default branch. No direct pushes. |
| `feature/*` | All new work: features, refactors, fixes. Branched from `main`, merged back via PR. |
| `system-v1/synthetic-data-generation` | Frozen snapshot of the initial v1 build, kept for reference. Not part of ongoing flow. When the merged branches are deleted, it is first tagged `system-v1-snapshot`, which then replaces the branch. |

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
- the **CI status check must pass** before merge (lint + format + tests).

Required approvals are currently **0**: the project lead (**@WZcit223**) owns and
approves all changes in this account, and CI is the merge gate. If a second
engineer joins the repo, raise the required-approvals count to 1.

## Two tracks for Pull Requests

### 1. Implementation PRs — may auto-merge

For PRs that only implement already-agreed requirements or design and **do not
change the overall architecture**:

- ensure `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` pass locally;
- open the PR (fill the template);
- you may enable **auto-merge** — GitHub merges automatically once CI is green
  and any branch-protection rules are satisfied. No extra human approval step is
  required beyond the protection rules.

### 2. Architecture / directional PRs — plan first, merge manually

For PRs that change the overall system architecture, introduce a new core
component or tech stack, or perform a large refactor of a core module:

- **first** describe the proposal, scope of impact and alternatives in the PR (or
  a linked issue), so the decision is documented;
- the **project lead (@WZcit223)** reviews the plan and approves it before it is
  implemented and merged;
- **do not enable auto-merge** — these are reviewed and merged manually.

When in doubt about which track a change belongs to, treat it as directional and
write the short plan first.

## Local checks

```bash
uv sync                        # environment (Python 3.14) + pytest + ruff, locked to uv.lock
uv run ruff check              # lint
uv run ruff format --check     # formatting
uv run pytest                  # tests
uv run sdf validate --update-doc docs/VALIDATION.md   # after a change that moves a recorded number
```

For a change under `ui/` (Node 22), from `ui/`:

```bash
npm ci                         # dependencies, locked to package-lock.json
npm run check                  # svelte-check
npm test                       # unit tests (Vitest)
npm run build                  # ui/dist, which the API tests and the page tests use
npm run e2e                    # page tests in Chromium (Playwright)
```

UI dependencies change only through `npm install` in `ui/`, so
`package-lock.json` stays current.

Enable the versioned pre-commit hook once per clone with
`git config core.hooksPath .githooks`; it formats and lints staged Python files.
Dependencies are managed only through uv: add them with `uv add` (or
`uv add --group dev` / `uv add --optional <extra>`) so `uv.lock` stays current, and
commit the lock file with the change.

Both must pass before opening a PR; CI runs the same checks on Python 3.12, 3.13 and 3.14.
