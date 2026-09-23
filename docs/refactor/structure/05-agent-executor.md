# PR 5 — Agent executor: approval enforced in one place

Interface contract: [`interfaces.md` §3](interfaces.md#3-agent-executor-sdfapplicationagent).

## Goal

A tool that needs approval, or that changes state, can never run without an
explicit approval, whoever plans the call. This must hold before any LLM
planner is connected.

## Scope

- `application/agent.py` becomes the subpackage `application/agent/`:
  - `tools.py` — `Tool`, `ToolResult`;
  - `executor.py` — `Executor.call(log, name, *, approved=False, **args) -> ToolResult`;
  - `planner.py` — `PlannedCall`, `Planner` protocol, `KeywordPlanner` (today's keyword rules, unchanged);
  - `agent.py` — `WarehouseAgent`, which plans, executes and composes the answer.
- The executor returns `pending_approval` without calling the function when a
  tool has `requires_approval=True` or `read_only=False` and `approved` is false.
  Tool errors become `ToolResult(ok=False, status="failed", error=…)`.
- Answer composition branches on `ToolResult.ok` instead of guessing dict keys.
- Tests: a state-changing fake tool is not called without approval and is
  called with it; a failing tool yields `failed`; the golden agent run (plan,
  step count, proposed action) is unchanged.

## Non-goals

- No LLM planner, no change to the keyword rules or answer wording.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test unchanged; approval tests pass
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
```

## Version

`Version: MINOR 0.12.0 → 0.13.0` — the agent becomes a subpackage with an
executor and planner interface.
