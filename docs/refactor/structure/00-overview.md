# Structure refactor — overview

Status: implemented by structure PRs 1–7 (#14–#20, 1.0.0); followed by
[`cleanup/`](../cleanup/00-overview.md). Approved by the project lead on
2026-09-23, including the version plan below. Third sequence after [`docs/refactor/layout/`](../layout/00-overview.md) and
[`docs/refactor/correctness/`](../correctness/00-overview.md). It covers steps 4–6
of [`docs/REFACTOR_PREP.md`](../../REFACTOR_PREP.md) §5 and prepares three
extension points the project lead asked for.

The authoritative interface contract for this sequence is
[`interfaces.md`](interfaces.md). Every PR plan links to it instead of
redefining names, parameters or return types.

## Why

After the correctness sequence the numbers are right and tied to the code, but
the structure still blocks the next steps:

- `application/intelligence.py` is a ~400-line class that computes KPIs, the
  replenishment policies, two kinds of anomaly, the vision stocktake and the
  text insights. Changing one of them means reading and re-testing all of them.
- Two replenishment rules answer the same question differently (7 versus 62
  SKUs needing an order on the default world), and no caller says which one it
  used. Some callers use the fixed 3-day rule, others the (s,S) policy.
- The simulation code that exists (the scenario runner, the economics
  counterfactual, the replenishment "closed loop") is three unrelated pieces of
  code. None of them can be combined with another.
- Every synthesis algorithm has its own calling convention: a spec-driven
  generator, a series fitter, a table bootstrap hidden in `validation/privacy.py`,
  and an optional Gaussian copula. There is no single way to list, choose or add
  one.
- The web backend replaces its "current world" in three separate assignments,
  so concurrent requests can see half-old, half-new data. The dashboard HTML
  lives inside the Python package, and the API serves it.
- The agent's approval flag is only written into the log. A tool marked
  `requires_approval=True` is still executed.

## Decisions taken with the plan

1. **The fixed rule-of-thumb replenishment is removed entirely** (project lead,
   2026-09-23). The (s,S) service-level policy is the only replenishment
   policy. The dashboard's "replenishment loop" panel is rebuilt on a policy
   comparison from the new simulation layer.
2. **`/generate` limits**: at most 500 SKUs and 180 days, one generation at a
   time (project lead, 2026-09-23).
3. **API contract tests** use FastAPI's test client, with `httpx` added to the
   `dev` dependency group only (project lead, 2026-09-23).

### Future requirements this sequence prepares for (not implemented here)

The project lead set three directions for later development. This sequence does
not deliver them, but every interface below is shaped so they can be added
without another restructuring:

- **F1. Pluggable synthesis.** All synthesis algorithms will be plug-ins that
  users can choose, add or write themselves. This sequence defines the
  `Synthesizer` contract and a registry that mounts every algorithm as a
  plug-in through the `sdf.synthesizers` entry-point group. Our own four
  algorithms are declared there as built-ins, exactly like a third-party
  plug-in would be (project lead, 2026-09-23). Choosing plug-ins from the UI is
  the follow-up.
- **F2. Composable policy simulation, ready for causal modelling.** One dataset
  must support many simulations, freely combined. This sequence adds a
  `simulation/` layer with four parts: a `World`, `Intervention`s (changes to
  the world), `Policy`s (decision rules) and `Outcome`s (named metrics). An
  `Experiment` runs every combination and returns tidy rows. An intervention is
  the `do()` of a causal model, and the tidy rows are the treatment/outcome table
  a causal estimator consumes, so causal modelling slots in without changing the
  shape.
- **F3. A fully separate UI.** The UI only carries user intent to the backend
  and presents results. It may do light, unaudited presentation transforms
  such as a pivot table, but never business logic. This sequence moves the
  dashboard out of the Python package into `ui/`. The backend becomes a
  JSON-only, versioned API (`/api/v1`) with an OpenAPI schema as its contract.
  The experiment endpoint returns tidy rows so the UI can pivot them.

## Target layout after this sequence

```
src/sdf/
  foundation/      schema.py registry.py adapters/
  analytics/       demand.py metrics.py forecast.py models.py anomaly.py
  synthesis/       api.py registry.py spec.py warehouse.py materialise.py
                   fit.py bootstrap.py sdv_synth.py scenarios.py
  validation/      quality.py fidelity.py tstr.py privacy.py
  simulation/      world.py policy.py engine.py intervention.py outcome.py experiment.py   (new)
  application/     intelligence.py (facade) kpi.py replenishment.py anomaly_rules.py
                   vision.py narrative.py economics.py knowledge.py scenarios.py snapshot.py
                   agent/ (tools.py executor.py planner.py agent.py)
  observability.py workflow/ api/ (app.py state.py schemas.py) cli.py
ui/                index.html app.js style.css   (static; talks only to /api/v1)
```

Layer ranks (enforced by `layering_test.py`; lower may not import higher):
`foundation 0 · analytics 1 · synthesis 2 · observability 2 · validation 3 ·
simulation 4 · application 5 · workflow 6 · api 7 · cli 7`. `ui/` is not Python.
It reaches the backend only over HTTP, and a test checks that every path it calls
exists in the OpenAPI schema.

## Sequence

| # | Plan | Purpose | Recorded numbers |
|---|---|---|---|
| 1 | [`01-split-intelligence.md`](01-split-intelligence.md) | Split the analysis class into one module per concern (pure move) | unchanged |
| 2 | [`02-simulation-layer.md`](02-simulation-layer.md) | New `simulation/` layer; economics, scenarios and (s,S) run through it | unchanged |
| 3 | [`03-retire-rule-policy.md`](03-retire-rule-policy.md) | Remove the fixed rule; every caller uses the (s,S) policy; rebuild the dashboard panel | agent proposal, insights, pipeline and demo change |
| 4 | [`04-synthesizer-contract.md`](04-synthesizer-contract.md) | `Synthesizer` contract + registry; existing algorithms behind it | unchanged |
| 5 | [`05-agent-executor.md`](05-agent-executor.md) | Approval enforced in one executor; `ToolResult`; `Planner` interface | unchanged |
| 6 | [`06-api-state.md`](06-api-state.md) | `create_app()`, immutable snapshot swapped atomically, `/generate` limits, contract tests | unchanged |
| 7 | [`07-ui-separation.md`](07-ui-separation.md) | Dashboard moves to `ui/`; JSON-only `/api/v1`; experiment endpoint | unchanged |

PR 1 comes first because every later PR edits one of the modules it creates.
PR 2 introduces the simulation layer before PR 3 removes the old rule, so the
replacement panel exists before the old one is deleted (introduce → migrate →
remove). PR 5 follows PR 3 because the agent's tools change when the rule
disappears. PR 6 stabilises the backend state before PR 7 changes its URL
space.

## Alternatives considered

- **Keep the fixed rule as a second named policy.** Rejected by the project
  lead: two answers to one question confuse users, and the (s,S) policy
  subsumes the rule.
- **Implement plug-in loading, causal models and the pivot UI now.** Rejected:
  they are new capabilities. This sequence only makes their interfaces exist and
  moves existing code behind them, so each PR stays reviewable.
- **Put policies and scenarios inside `application/`.** Rejected: the
  simulation layer must be usable without the application facade, e.g. from a
  notebook, a workflow step or a future causal module. Its own layer also keeps
  the dependency direction testable.
- **A JavaScript build tool for the UI.** Rejected for now: the dashboard is one
  static page. `ui/` stays plain HTML/JS until a feature needs more.

## Consequences

- **Rule-based numbers disappear.** The golden rule-based replenishment count
  (7) and the "closed loop" simulation (2 → 0 stockouts) go away. The agent's
  proposed order, the insights text, the workflow's `replenishment_flagged` and
  the `sdf demo` replenishment lines change to (s,S) values in PR 3, each one
  listed in that PR.
- **HTTP paths change twice.** PR 3 removes `/application/replenishment` and
  `/application/replenishment/simulate`. PR 7 moves every endpoint under
  `/api/v1`. Both change documented contracts (`REFACTOR_PREP.md` §2.2); see
  Version below.
- **Import paths change.** `bootstrap_synthesize` moves from
  `validation/privacy.py` to `synthesis/bootstrap.py`. The agent becomes a
  subpackage. The dashboard leaves the Python package.

## Non-goals

- No new synthesis algorithm (F1 follow-up).
- No causal estimator, no new intervention type beyond the existing scenarios
  and a plain policy comparison (F2 follow-up).
- No pivot table or other new UI feature (F3 follow-up).
- No LLM planner, no change to the knowledge Q&A routing.
- No change to the generator's random-number order, so no synthetic data
  changes.

## Version

Per the branch-and-PR workflow, MAJOR needs explicit approval. PRs 3 and 7
change documented contracts (CLI `demo` output and HTTP endpoints). The project
lead approved this scheme on 2026-09-23:

- **Stay on 0.x during the sequence.** PRs 1–6 are MINOR, including PR 3,
  whose breaking changes are listed in its description.
- **PR 7 is the MAJOR bump to 1.0.0.** It introduces the versioned `/api/v1`
  contract, so the first stable version number matches the first stable API.

The plan PR itself: `Version: none, documentation and plans only`.
