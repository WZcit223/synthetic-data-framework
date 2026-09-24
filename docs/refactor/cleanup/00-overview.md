# Clean-up refactor — overview

Status: implemented by clean-up PRs 1–4 (#22–#25, 1.1.0 → 1.3.1) after the plan
(#21); the refactor is finished except the deletion of the merged remote
branches, which the project lead runs (see [`04-finishing.md`](04-finishing.md)). Approved by the project lead on 2026-09-24
("完全同意你的方案"), including
the version plan below. Fourth and last sequence of the refactor, after
[`layout/`](../layout/00-overview.md), [`correctness/`](../correctness/00-overview.md)
and [`structure/`](../structure/00-overview.md). It finishes steps 8 and 9 of
[`docs/REFACTOR_PREP.md`](../../REFACTOR_PREP.md) §5 and the two items of the
refactor's problem list that no earlier sequence took up: stringly-typed workflow
context and unchecked entity records.

## Why

- **Hook markers cannot be found by a program.** The code has 39 `ALGORITHM-HOOK`
  / `DATA-HOOK` markers (and three prose mentions of the convention). Only 2 carry
  the checklist ID they belong to (`ALGORITHM-HOOK[C2]`); nothing ties the other 37 to a row of
  `docs/ALGORITHM_AND_DATA_CHECKLIST.md`, and nothing notices when a row loses
  its last marker or a marker names a row that does not exist.
- **Entity records accept anything.** `OutboundOrder(quantity=-5, status="lost")`
  constructs fine and flows into every KPI. The canonical schema is the contract
  between real and synthetic data; today it only states types.
- **Workflow steps share data through underscore keys.** `warehouse_pipeline`
  passes the registry, the warehouse and the analysis facade between steps as
  `ctx["registry"]`, `ctx["_warehouse"]`, `ctx["_intel"]`. A typo is a `KeyError`
  at run time, and nothing says which step owns which key.
- **The audit log is truncated.** `RunLogger` keeps inputs and outputs shortened
  to 240 characters, 12 keys and 3 list items, and writes exactly that to its
  JSONL sink. The durable audit log therefore cannot answer "what exactly did the
  agent see" afterwards. No command exposes the sink either.
- **Loose ends.** Starlette warns that its test client prefers `httpx2` over
  `httpx`; the dashboard has no favicon (one 404 per load); `docs/VALIDATION.md`
  prose still quotes a few hand-copied numbers next to the generated block; the
  merged branches of the refactor remain on the remote.

## Decisions taken with the plan

1. Hook markers take the form `ALGORITHM-HOOK[<ID>]` / `DATA-HOOK[<ID>]` with an
   ID from the checklist. The checklist gains a generated section listing where
   each ID plugs into the code; a test keeps both in step.
2. Invalid entity records raise `ValueError` naming the field. The synthetic
   generator and the bundled CSVs must produce no invalid record, so no recorded
   number moves; the CSV adapter counts a row it cannot turn into a valid record
   as skipped, like any other unusable row.
3. `httpx` is replaced by `httpx2` in the `dev` group if FastAPI's test client
   works with it on the locked versions; otherwise `httpx` stays and the plan's
   status records why.
4. Every merged remote branch is deleted (project lead's decision, 2026-09-24),
   by exact name and only once its PR is confirmed merged with the branch tip
   equal to the merged head ([`04-finishing.md`](04-finishing.md) lists them).
   That includes `feature/repo-governance` (#1), the session branch
   `claude/upbeat-goodall-fb5jdk` (#3) and `system-v1/synthetic-data-generation`,
   whose tip is contained in `main`; the frozen initial-v1 snapshot stays
   reachable as the tag `system-v1-snapshot`, and `CONTRIBUTING.md` says so.

## Sequence

| # | Plan | Purpose | Recorded numbers |
|---|---|---|---|
| 1 | [`01-hook-markers.md`](01-hook-markers.md) | Every marker names its checklist ID; generated code index in the checklist; `sdf hooks` | unchanged |
| 2 | [`02-data-contracts.md`](02-data-contracts.md) | Entity records validate their fields; typed workflow state | unchanged |
| 3 | [`03-full-audit-log.md`](03-full-audit-log.md) | The JSONL audit log keeps full inputs and outputs; `--audit-log` on `agent` and `pipeline` | unchanged |
| 4 | [`04-finishing.md`](04-finishing.md) | `httpx2`, favicon, generated numbers in `VALIDATION.md` prose, close the refactor records, delete merged branches | unchanged |

The order is independent except for PR 4, which closes the records of the whole
refactor and so comes last.

## Non-goals

- No new synthesis algorithm, no causal model, no pivot view, no LLM planner
  (F1–F3 and the algorithm phase; they need their own decision).
- No change to the generator's random-number order, so no synthetic data changes.

## Version

- PR 1: MINOR (new `sdf hooks` command).
- PR 2: MINOR (records reject invalid values; workflow context changes shape).
- PR 3: MINOR (the audit log's content and two new CLI options).
- PR 4: PATCH (the `sdf validate` snapshot gains each backtest series' mean and
  held-out window, so `docs/VALIDATION.md` prose can refer to them; plus a
  development dependency, favicon and documentation).

The plan PR itself: `Version: none, documentation and plans only`.
