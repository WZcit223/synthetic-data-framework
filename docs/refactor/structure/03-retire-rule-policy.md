# PR 3 — Remove the fixed replenishment rule; the (s,S) policy is the only one

Interface contract: [`interfaces.md` §1](interfaces.md#1-simulation-layer-sdfsimulation--f2)
(`ServiceLevelPolicy`, `plan_orders`, `Experiment`).

## Goal

Every answer to "which SKUs need an order, and how much" comes from one policy,
the (s,S) service-level policy, so the product never shows two different
numbers for one question (project lead's decision, 2026-09-23).

## Scope

- Delete `WarehouseIntelligence.replenishment_suggestions`,
  `replenishment_simulation`, `_daily_demand` uses that only served them, and
  the rule functions in `application/replenishment.py`.
- Switch every caller to `plan_orders(world, ServiceLevelPolicy(service_level=0.95))`:
  - `narrative.insights` ("N SKUs need an order under the 95 % service-level policy");
  - the agent's `replenishment` tool and its proposed order;
  - `knowledge._replenish`;
  - the workflow's `replenishment_flagged`;
  - the `sdf demo` "top replenishment suggestions" lines.
- New endpoint `GET /application/replenishment/comparison?service_level=0.95`:
  an `Experiment` with `NaivePolicy` versus `ServiceLevelPolicy` and
  `SimulatedCost` + `ReplenishmentNeed`. It returns the unmet units, fill rate,
  holding cost and SKUs needing an order for each policy.
- Remove `GET /application/replenishment` and
  `GET /application/replenishment/simulate`. The dashboard's "replenishment
  loop" panel is rebuilt on the comparison endpoint and shows the policy name.
- Snapshot and golden test: drop `rule_replenishment` and
  `replenishment_simulation`, add `replenishment_comparison`. Update the agent
  proposal. Regenerate `VALIDATION.md`, re-capture the `sdf demo` output, and
  list every moved or removed number in the PR description.
- `REFACTOR_PREP.md` §2.2 (HTTP contract) and §2.5 note the removal.

## Non-goals

- No change to the (s,S) formula or to any (s,S) number.
- No `/api/v1` prefix yet (PR 7).

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test updated only for the listed numbers
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
grep -rn "replenishment_suggestions\|replenishment_simulation" src docs --include=*.py --include=*.html --include=*.md | grep -v "docs/refactor/\|REFACTOR_PREP"   # nothing
```

## Version

`Version: MINOR 0.10.0 → 0.11.0` — removes the rule-based policy, two HTTP
endpoints and changes the `sdf demo` output; minor under the pre-1.0 policy
proposed in the overview (project lead to confirm).
