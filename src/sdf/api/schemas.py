"""Request and response models of the ``/api/v1`` contract.

Each model declares the fields a client may rely on, so ``/api/v1/openapi.json``
describes them; ``extra="allow"`` passes any further fields through unchanged,
so adding a field to a response is not a breaking change. Fields that are absent
when there is too little data (for example a backtest on a very short series)
are optional.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="allow")


# -- world ----------------------------------------------------------------------------------


class Health(Model):
    status: str


class WorldSummary(Model):
    source_count: int
    by_entity: dict[str, int]
    by_origin: dict[str, int]


class Range(Model):
    min: int
    max: int


class WorldLimits(Model):
    n_skus: Range
    horizon_days: Range


class WorldSpec(Model):
    n_skus: int
    horizon_days: int
    daily_orders_per_a_sku: float
    stockout_pressure: float
    seed: int


class WorldGenerated(Model):
    ok: bool
    spec: WorldSpec
    generated_ms: int


class Quality(Model):
    mode: str
    passed: bool
    checks: dict[str, bool]
    metrics: dict[str, float]
    notes: list[str]


# -- application ----------------------------------------------------------------------------


class KPIs(Model):
    total_skus: int
    total_on_hand: int
    inventory_value: float
    outbound_lines: int
    cancel_rate: float
    express_rate: float


class Overview(Model):
    kpis: KPIs
    abc: dict[str, int]
    insights: list[str]
    anomalies_sample: list[dict[str, Any]]
    foundation: WorldSummary
    quality: Quality


class ReplenishmentRow(Model):
    sku_id: str
    name: str
    avg_daily_demand: float
    demand_std: float
    variability: float
    intermittent: bool
    safety_stock: float
    reorder_point_s: float
    order_up_to_S: float
    available: int
    order_qty: int


class Replenishment(Model):
    service_level: float
    z: float
    lead_time_days: int
    review_days: int
    skus_needing_order: int
    intermittent_needing_order: int
    total_safety_stock_units: float
    rows: list[ReplenishmentRow]


class PolicyMetrics(Model):
    policy: str
    skus_needing_order: int
    safety_stock_units: float
    intermittent_needing_order: int
    unmet_units: float
    fill_rate: float
    holding_cost: float
    order_cost: float
    lost_margin: float


class ReplenishmentComparison(Model):
    service_level: float
    horizon_days: int
    policies: list[PolicyMetrics]


class TopMover(Model):
    sku_id: str
    name: str
    abc_class: str
    avg_daily_demand: float


class DemandPoint(Model):
    date: str
    qty: int


class DemandSeries(Model):
    sku_id: str
    history: list[DemandPoint]
    forecast_avg_daily: float
    forecast_horizon_days: int
    forecast_total: float


class DemandAnomaly(Model):
    index: int
    value: float
    expected: float
    robust_z: float
    direction: str


class DemandAnomalies(Model):
    granularity: str
    seasonal_period: int
    series_len: int
    count: int
    anomalies: list[DemandAnomaly]


class ShelfCell(Model):
    location_id: str
    occupancy: float
    book_units: int
    est_units: int


class ShelfAisle(Model):
    aisle: str
    cells: list[ShelfCell]


class ShelfZone(Model):
    zone: str
    aisles: list[ShelfAisle]


class Discrepancy(Model):
    location_id: str
    book_units: int
    vision_units: int
    diff: int
    direction: str


class Stocktake(Model):
    locations_scanned: int
    matched: int
    flagged: int
    match_rate: float
    net_unit_variance: int
    discrepancies: list[Discrepancy]


class BacktestResult(Model):
    model: str
    MAE: float
    RMSE: float
    MAPE_pct: float | None = None  # n/a when no test day has positive demand
    WAPE_pct: float | None = None
    bias: float


class Backtest(Model):
    granularity: str
    seasonal_period: int
    series_len: int
    series_mean: float | None = None
    best_model: str | None = None
    results: list[BacktestResult] = []
    error: str | None = None  # set instead of results when the series is too short


class Answer(Model):
    intent: str
    answer: str


# -- agent, economics, workflow, scenarios -------------------------------------------------------


class RunSummary(Model):
    run_id: str
    steps: int
    ok: int
    errors: int
    total_ms: int


class TraceEntry(Model):
    seq: int
    name: str
    status: str
    duration_ms: int
    note: str = ""


class ProposedAction(Model):
    """A call held for approval: the action, its arguments and its status."""

    proposed_action: str
    status: str
    sku_id: str | None = None  # the arguments of a place_order proposal
    quantity: int | None = None


class AgentAnswer(Model):
    query: str | None
    answer: str
    plan: list[str]
    proposed_actions: list[ProposedAction]
    requires_approval: bool
    run: RunSummary
    trace: list[TraceEntry]


class ToolInfo(Model):
    name: str
    description: str
    read_only: bool
    requires_approval: bool


class AgentTools(Model):
    tools: list[ToolInfo]


class Economics(Model):
    assumptions: dict[str, float] | None = None
    skus_considered: int | None = None
    horizon_days: int | None = None
    unmet_units: dict[str, int] | None = None
    stockout_units_avoided: int | None = None
    period: dict[str, int] | None = None
    annualised_net_saving: int | None = None
    error: str | None = None  # set instead of the figures when the world has no demand


class WorkflowRun(Model):
    pipeline: str
    order: list[str]
    run: RunSummary
    trace: list[TraceEntry]


class ScenarioRow(Model):
    scenario: str
    outbound_lines: int
    inventory_value: float
    skus_needing_order: int
    safety_stock_units: float
    active_stockouts: int
    safety_stock_vs_baseline_pct: float


class Scenarios(Model):
    service_level: float
    scenarios: list[ScenarioRow]


# -- tables ----------------------------------------------------------------------------------


class FieldModel(Model):
    """A table column: dimension (group by it), time (an ISO date) or measure (a number)."""

    name: str
    label: str
    kind: Literal["dimension", "time", "measure"]
    unit: str | None = None
    aggregate: Literal["sum", "mean", "min", "max"] | None = None


class DatasetEntry(Model):
    name: str
    label: str
    description: str
    origin: Literal["builtin", "plugin", "runtime"]
    fields: list[FieldModel]


class DatasetList(Model):
    datasets: list[DatasetEntry]
    unavailable: dict[str, str]


class DatasetTable(Model):
    """One dataset over the current world; each row is an array in field order."""

    name: str
    label: str
    world: str
    fields: list[FieldModel]
    rows: list[list[Any]]
    total_rows: int
    truncated: bool


# -- experiments ------------------------------------------------------------------------------


class PolicyChoice(BaseModel):
    """A built-in policy: ``naive`` or ``service-level`` (with its service level)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["naive", "service-level"]
    service_level: float = Field(0.95, gt=0.5, lt=1.0)
    lead_time_days: int = Field(7, ge=1, le=90)
    review_days: int = Field(7, ge=1, le=90)


MAX_PER_LIST = 6  # interventions, policies and outcomes per experiment


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interventions: list[str] = Field(default_factory=lambda: ["baseline"], min_length=1, max_length=MAX_PER_LIST)
    policies: list[PolicyChoice] = Field(min_length=1, max_length=MAX_PER_LIST)
    outcomes: list[str] = Field(min_length=1, max_length=MAX_PER_LIST)


class OutcomeRowModel(Model):
    intervention: str
    policy: str
    metric: str
    value: float


class ExperimentResult(Model):
    rows: list[OutcomeRowModel]
    fields: list[FieldModel]


class ParamModel(Model):
    """One parameter a form can set: its type, default and bounds (``null`` when unbounded)."""

    name: str
    type: Literal["int", "float", "str", "bool"]
    default: Any = None
    min: int | float | None = None
    max: int | float | None = None
    exclusive: bool = False  # the bounds themselves are not allowed
    nullable: bool = False


class PolicyKind(Model):
    kind: str
    params: list[ParamModel]


class ExperimentCatalog(Model):
    interventions: list[str]
    policies: list[PolicyKind]
    outcomes: list[str]
    max_per_list: int
