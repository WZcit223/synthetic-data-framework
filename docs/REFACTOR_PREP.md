# Refactor Preparation / 大规模重构准备

> 状态：基于 `main @ faf08a4` 的全量源码盘点（2026-09-22）。
> 目的：在动手重构之前，把"现状事实、必须保留的契约、已核实的缺陷、目标结构、
> 安全的施工顺序"固定下来，让重构可以分成多个**各自可合并、CI 始终绿**的 PR 推进。
>
> 本文与 `ARCHITECTURE.md`（设计意图）、`ALGORITHM_AND_DATA_CHECKLIST.md`（算法/数据缺口）、
> `VALIDATION.md`（度量数字）互补；本文只谈**代码结构与工程质量**。

---

## 0. 一页结论

- **仓库规模**：`src/sdf` 共 29 个 Python 文件（22 个实现模块 + 7 个 `__init__.py`）、约 3,100 行；1 个 581 行的零依赖前端；1 个测试文件 18 项测试（3.14 下 1 s 内跑完，`ruff` 干净）。
- **最大的结构问题不是某个 bug，而是三处"重心放错了地方"**：
  1. `build_registry()` 是所有入口（API、workflow、scenarios、tests）物化世界的唯一函数，却住在 `cli.py` 里，导致 `synthesis → cli`、`workflow → cli`、`api → cli` 三条反向依赖。
  2. "按 SKU 按天聚合需求"这件事在 `warehouse_demo._daily_demand`、`warehouse_demo._sku_daily_stats`、`warehouse_demo.demand_series`、`economics.financial_impact`、`forecast.daily_demand_series` 里各写了一遍，口径彼此不同。
  3. `WarehouseIntelligence` 是一个 396 行的上帝对象，同时承载 KPI、两套互不一致的补货逻辑、异常、视觉盘点、叙事；`economics.py` 直接读它的私有方法。
- **必须保留的外部契约**只有四类：CLI 子命令名与默认参数、仪表盘消费的 16 个 HTTP 端点及其 JSON 字段（另有 5 个业务端点与 `/health`、`/` 未被前端调用）、六个规范实体 + `GenerationSpec` 字段、`VALIDATION.md` 中的度量数字（固定种子下可复现）。其余都是内部实现，可以自由改。
- **施工顺序**：先加"特征化测试"（黄金数字 + 端点契约）作为安全网 → 再修依赖方向 → 再统一需求聚合并顺手修数值 bug → 再拆上帝对象 / 改 API 状态模型 / 加固 Agent 审批门 → 最后 CLI 与 HOOK 标记规范化。每一步都是一个独立 PR。

---

## 1. 现状事实（逐文件核对后的结论）

### 1.1 模块清单与职责

| 模块 | 行数 | 职责 | 备注 |
|---|---:|---|---|
| `foundation/schema.py` | 107 | 6 个规范实体 dataclass | 无任何字段校验 |
| `foundation/registry.py` | 88 | `DataSourceRegistry` 多源叠加 | 内存 list，`stream()` 每次全扫 |
| `foundation/adapters/retail_csv.py` | 93 | UCI Online Retail II → 实体 | 坏行静默丢弃；日期格式先试 `%m/%d` |
| `synthesis/warehouse.py` | 292 | `GenerationSpec` + `WarehouseGenerator` | 唯一含字面 `# ALGORITHM-HOOK` 的核心模块 |
| `synthesis/quality.py` | 74 | 结构性质量检查 | `passed` 对空 checks 返回 True |
| `synthesis/forecast.py` | 163 | 序列构建 + 基线 + walk-forward 回测 | MAPE 分母口径不一致 |
| `synthesis/models.py` | 85 | AR+季节 OLS（纯 Python 正规方程） | 近奇异列静默跳过 |
| `synthesis/fit.py` / `fidelity.py` / `tstr.py` | 77/81/68 | 拟合合成 / KS+剖面相关 / TSTR | `generate()` 每次重建同种子 RNG |
| `synthesis/anomaly.py` | 47 | 季节残差 + MAD 鲁棒 z | MAD=0 时 `1e-9` 兜底 |
| `synthesis/privacy.py` / `scenarios.py` / `sdv_synth.py` | 119/71/77 | DCR·NNDR / what-if / 高斯 Copula | `scenarios` 反向依赖 `cli` 与 `application` |
| `application/warehouse_demo.py` | 396 | `WarehouseIntelligence` 上帝对象 | 见 §3 |
| `application/knowledge.py` | 136 | 关键词路由问答 | 空世界下 `IndexError` |
| `application/economics.py` | 127 | (s,S) vs 朴素策略反事实 £ | 触碰 `intel._sku_daily_stats` |
| `application/agent.py` | 143 | 工具注册 + 关键词规划器 + 审计 | 审批门不短路（见 §3 P11） |
| `observability.py` | 109 | `RunLogger` | 输出被 `_summarise` 截断为 12 键，审计有损 |
| `workflow/pipeline.py` | 136 | 拓扑排序 DAG | `ctx` 混放隐藏对象；反向依赖 `cli` |
| `api/app.py` | 225 | FastAPI，23 个路由（21 个业务 + `/` + `/health`） | 模块级可变单例 `_state`；缺 fastapi 时 `SystemExit` |
| `api/static/dashboard.html` | 581 | 零依赖前端 | 一次刷新并发打 11 个端点 |
| `cli.py` | 319 | 手写 `if cmd ==` 分发 + `build_registry` | 被 4 处当作库导入 |
| `tests/test_generators.py` | 229 | 18 项冒烟/结构测试 | `sys.path` hack；可选依赖测试用 `return` 而非 `pytest.skip` |

### 1.2 实际依赖图（`grep "from sdf"` 得出）

> 2026-09-23（layout 序列 PR 2 之后）：下图的反向边已全部消除，并由
> `src/sdf/layering_test.py` 持续断言（`foundation < synthesis/observability <
> application < workflow < api/cli`，`api` 与 `cli` 互不导入）。保留原图作为改前记录。

```
foundation.schema ── ← synthesis.warehouse ← cli.build_registry ←──┐
foundation.registry ← application.warehouse_demo ← api.app        │
                    ← foundation.adapters.retail_csv ← synthesis.privacy
synthesis.forecast  ← synthesis.models, fit, tstr
                    ← application.warehouse_demo (lazy), application.knowledge (lazy)
synthesis.anomaly   ← application.warehouse_demo (lazy)
application.*       ← application.agent, workflow.pipeline, api.app, cli
observability       ← application.agent, workflow.pipeline

反向 / 跨层（PR 2 已消除）：
  synthesis.scenarios  → sdf.cli, sdf.application.warehouse_demo   → run_scenarios 迁至 application/scenarios.py
  workflow.pipeline    → sdf.cli                                   → build_registry 迁至 synthesis/materialise.py
  api.app              → sdf.cli                                   → 同上
  application.economics → intel._sku_daily_stats / intel.reg      → 方法改为公开 sku_daily_stats()（PR 3 换实现）
  sdf/__init__.py      → 顶层 eager import application.warehouse_demo → 包根只导出 __version__
```

---

## 2. 重构必须保留的契约（改动前先写测试锁住）

### 2.1 CLI 子命令（`cli.main`）

`demo | export [dir] | backtest [csv] | synth [csv] | tstr [csv] | sdv [csv] | agent "<q>" | pipeline | impact | scenarios | privacy [csv]`，
`[csv]` 默认 `data/sample_online_retail_ii.csv`，`export` 默认 `out`，无参数默认 `demo`。
已于 PR #3 迁到 click（`cli.py` 的 click 层 + `cli_test.py`）：名字与默认值不变；未知命令与不存在的 CSV 现在是 click 的用法错误（退出码 2，原为打印 `__doc__` 返回 1）；`sdv` 缺 extra 时仍退出 1。**新增**子命令（第 7 步的 `validate`）不受此限制。

### 2.2 HTTP 端点

`app.py` 共 23 个路由：`/`（仪表盘页面）、`/health`、21 个业务端点。其中 **16 个**被 `dashboard.html` 直接 `fetch`
（下表前 16 行，含 `POST /generate`），是重构期间字段必须逐个保持的契约；其余 5 个业务端点只出现在文档里，
只需保证路径存在与返回可 JSON 化。

> 2026-09-23（structure 序列 PR 3）：按项目负责人决定删除固定规则补货，`GET /application/replenishment`
> 与 `GET /application/replenishment/simulate` 两个端点随之移除（路由由 23 个变为 22 个，其中 15 个被仪表盘直接调用）；仪表盘改用新增的
> `GET /application/replenishment/comparison?service_level`（字段 `service_level,horizon_days,
> policies[].{policy,skus_needing_order,safety_stock_units,unmet_units,fill_rate,holding_cost,order_cost}`）。
> 下表保留为改前记录。
>
> 2026-09-23（structure 序列 PR 6）：仪表盘的 `POST /generate` 现在传 `horizon_days`；超过上限（500 SKU、180 天）
> 或低于下限的参数返回 422，另一生成进行中返回 409；响应新增 `generated_ms`。`/scenarios` 与 `/workflow/run`
> 改用当前世界，不再各自重新生成。`src/sdf/api/app_test.py` 覆盖下表仍存在的每个字段。
>
> 2026-09-23（structure 序列 PR 7，1.0.0）：所有端点移到 `/api/v1` 下并按 `docs/refactor/structure/interfaces.md`
> §4.3 的表改名（例如 `/application/overview` → `/api/v1/overview`，`POST /generate?…` → `POST /api/v1/world`
> 的 JSON 请求体，`/generate/limits` → `/api/v1/world/limits`）；`/` 不再返回 HTML，仪表盘移到仓库根目录的 `ui/`。
> 旧路径全部返回 404。`/application/kpis` 不再单独提供（KPI 在 `/api/v1/overview` 里）。

| 端点 | 前端消费的字段 |
|---|---|
| `POST /generate?n_skus&daily_orders_per_a_sku&stockout_pressure&seed` | 仅状态；注意前端**不传** `horizon_days` |
| `GET /application/overview` | `kpis.{total_skus,total_on_hand,inventory_value,outbound_lines,cancel_rate,express_rate}`、`abc`、`insights[]` |
| `GET /application/replenishment?top_n` | `sku_id,name,available,avg_daily_demand,reorder_point,suggested_order_qty,urgency` |
| `GET /application/replenishment/simulate` | `skus_flagged,stockouts_before,stockouts_after,service_level_before,service_level_after` |
| `GET /application/replenishment/ss?service_level` | `z,lead_time_days,review_days,skus_needing_order,total_safety_stock_units,rows[].{sku_id,avg_daily_demand,demand_std,safety_stock,reorder_point_s,order_up_to_S,order_qty}` |
| `GET /application/top_movers?n` | `sku_id,name,abc_class` |
| `GET /application/demand_series?sku_id` | `history[].{date,qty},forecast_avg_daily,forecast_total,forecast_horizon_days` |
| `GET /application/shelf_occupancy` | `[].{zone,aisles[].cells[].{location_id,occupancy,book_units,est_units}}` |
| `GET /application/stocktake` | `match_rate,flagged,locations_scanned,net_unit_variance,discrepancies[].{location_id,book_units,vision_units,diff,direction}` |
| `GET /validation/backtest` | `granularity,series_len,series_mean,best_model,results[].{model,MAE,RMSE,MAPE_pct,bias}` |
| `GET /application/ask?q` | `intent,answer` |
| `GET /application/demand_anomalies` | `count,series_len,granularity,seasonal_period,anomalies[].{index,direction,value,expected,robust_z}` |
| `GET /agent/ask?q` | `plan[],answer,proposed_actions[].{sku_id,quantity,status},trace[].{seq,name,status,duration_ms}` |
| `GET /economics/impact` | `annualised_net_saving,stockout_units_avoided,unmet_units.{naive,ours},horizon_days,assumptions.holding_cost_annual_rate,period` |
| `GET /workflow/run` | `trace[].{seq,name,status,duration_ms},run.{run_id,steps,total_ms,errors}` |
| `GET /scenarios` | `scenarios[].{scenario,outbound_lines,skus_needing_order,safety_stock_units,safety_stock_vs_baseline_pct}` |
| `GET /export?entity`、`/foundation/summary`、`/synthesis/quality`、`/application/kpis`、`/agent/tools` | 5 个未被前端调用的业务端点（`/health` 与 `/` 另计） |

### 2.3 数据契约

- 六个实体 dataclass 的字段名与顺序（`export` CSV 表头依赖 `asdict` 顺序）。
- `GenerationSpec` 字段：`n_skus, n_locations, horizon_days, start, seed, abc_split, daily_orders_per_a_sku, express_ratio, stockout_pressure, reference_dataset, requirements`。`scenarios.SCENARIOS` 与 `/generate` 都按名字引用。
- 生成器的**随机数消费顺序**：任何改动 `WarehouseGenerator` 内部抽样顺序的重构都会改变默认世界，从而改变 §2.5 的全部黄金数字。重构期间**不要碰** `_gen_*` 的调用顺序与 RNG 调用次数。
- `Tool(name, description, fn, read_only, requires_approval)`、`Step(name, run, depends_on)`、`LogEntry` 的 `to_dict` 键。这三者被 docs 标为"换 LLM / Airflow / OTel 时保持不变的契约"。

### 2.4 度量口径

`VALIDATION.md` 里的数字按来源分三类，重构后的复现要求不同：

| 来源 | 涉及的数字 | 现有复现路径 | 重构要求 |
|---|---|---|---|
| CLI 命令 | Phase 2.0 回测表、Phase 2.1 fidelity、Copula/SDMetrics、B2 TSTR、B3 隐私、Phase 4 经济与情景 | `backtest / synth / sdv / tstr / privacy / impact / scenarios` | 同一输入上结果不变（容差 ±0.5%） |
| 测试内联序列 | C1 "受控序列"表（趋势+季节 / 纯季节高噪） | `src/sdf/synthesis/models_test.py` 只断言"模型赢"，**没有记录数值** | 第 3 步数值 PR 把序列与数值写进 `golden_test.py` |
| 默认世界手工调用 | C2 (s,S) 表、C3 异常示例、Phase 4 agent 轨迹 | **无 CLI 路径**，是当时在 REPL/仪表盘上读出的 | 已以 `src/sdf/golden_test.py` 锁定 §2.5 快照；第 9 步补 `sdf validate` 子命令统一生成 |

因此"每个数字都能一键复现"是本次重构要**达成**的状态，不是当前状态。

### 2.5 黄金数字快照（`GenerationSpec()` 默认世界，seed=42；bundled CSV）

> 2026-09-23：本节是审计时（`main @ faf08a4`）的基线，保留为历史。当前值由 `uv run sdf validate` 生成并嵌入 `docs/VALIDATION.md`；correctness 序列 PR 3（MAPE 口径）与 PR 4（间歇 SKU 的安全库存）按计划改变了其中的 MAPE、(s,S)、经济与情景数值，逐项对照见两份 PR 与 `VALIDATION.md`。structure 序列 PR 3 删除了固定规则补货：表中"规则补货"与"simulate"两行不再存在，Agent 的提议改为 (s,S) 下订量最大的 SKU（`SKU-00028 ×119`）。

在 `main @ faf08a4` 上实测，供特征化测试直接引用：

| 项 | 值 |
|---|---|
| registry `by_entity` | SKU 200 · Location 120 · InventorySnapshot 200 · InboundOrder 180 · OutboundOrder 28,897 · SensorReading 624 |
| KPIs | on_hand 25,719 · inventory_value 4,612,609.6 · cancel_rate 0.0298 · express_rate 0.2525 |
| ABC | A 39 · B 55 · C 106 |
| 规则补货 | 7 个 SKU 触发；top1 `SKU-00176` 订 66 |
| simulate | flagged 7 · stockouts 2→0 · service 0.965→1.0 |
| (s,S) 90/95/99% | 需订 32/38/47 · 安全库存 2,952/3,788/5,357 |
| 规则异常 | stockout 2 · dead_stock 0 |
| 需求异常（C3） | 3 个；最大 index 37，value 2,416，expected 739，z 35.35 |
| 视觉盘点 | 40 扫描 · 32 匹配 · 8 标记 · 净差 −923 |
| 回测（默认世界，daily，period 7） | snaive7 MAE 174.071 < seas_linear7 200.903 < mean 226.21 < ma7 277.184 < naive 337.786 |
| 经济 | naive 未满足 5,269 → ours 17 · 年化 1,887,834 |
| Agent "reorder & impact" | plan `[replenishment, financial_impact]` · 3 步 · 提议 `SKU-00176 ×66 PENDING_APPROVAL` |
| 情景 | promo_spike +41.9% · supply_disruption +0.8% · seasonal_downturn −13.5% · high_variability +16.1% |
| `sample_online_retail_ii.csv` | 12 SKU / 3,428 单 / daily 139 点；snaive7 MAE 32.786；fidelity 95.4；TSTR 0.905；clone-risk 4.38% |
| `online_retail_ii_2010_10k.csv` | 2,015 SKU / 10,000 单 / hourly 44 点；naive MAE 950.786；fidelity 78.0；TSTR 1.002；clone-risk 7.62% "review" |

**已发现的文档漂移**：`VALIDATION.md` C2 表记录的 (s,S) 结果是 33/38/43 与 2,626/3,369/4,764；当前代码产出 32/38/47 与 2,952/3,788/5,357。原因是 (s,S) 数字在 `4042cad` 记录，之后 `b26c015` 在生成器里加入了需求冲击注入，改变了默认世界的方差。这正是 notes 里 P10 的实例：数字靠手工复跑，没有 CI 锁定。

---

## 3. 已核实的缺陷（按重构时的处理方式分组）

以下每条都在当前代码上复现过；行号以 `main @ faf08a4` 为准。

### 3.1 随重构顺手修（改动落在被重构的模块内）

| # | 位置 | 现象（已复现） | 修法 |
|---|---|---|---|
| C1 | `forecast.py:137-145` | MAPE 分子只累加 `actual>0` 的点，分母用全部点；`[0,10,0,10,…]` 上 mean 模型 MAPE 报 27.5% 而非 52.5% | 分母改为正实际值的计数，或改报 WAPE/sMAPE 并在 `VALIDATION.md` 注明口径 |
| C2 | `forecast.py:127-131` | `backtest([], m)` → `IndexError`（`n//3=0` 后 `test_len=1`，`values[-1]` 越界） | 空/过短序列显式返回 `{"error": …}` 或抛 `ValueError` |
| C3 | `anomaly.py:33` | MAD=0 时 `or 1e-9`：40 个 0 + 一个 1 的序列标 1 个异常；稀疏序列标 6 个 | MAD=0 时回退到均值绝对偏差或直接返回空并记 `note`；对间歇需求应先做零膨胀处理 |
| C4 | `quality.py:27-28` | `QualityReport(mode="x").passed is True` | `passed = bool(checks) and all(...)` |
| C5 | `warehouse_demo.py:206-212` | σ 用总体方差除以 horizon，且 `mu<=0` 的 SKU 被丢弃；间歇需求 SKU 的 σ 偏低 → 安全库存偏低 | 在统一的需求聚合模块里给出 `mean/std/zero_ratio`，(s,S) 决定如何用 |
| C6 | `fit.py:49` | `generate()` 每次 `random.Random(self.seed)`，两次调用返回相同序列 | RNG 放到实例上，或 `generate(seed=None)` 显式传种子 |
| C7 | `models.py:27-28` | 近奇异列静默 `continue`，返回的权重对该列为 0 且无告警 | 记录 `rank_deficient` 标志，或直接使用 ridge 并去掉分支 |
| I1 | `knowledge.py:92` | 空注册表上 `ask("forecast accuracy?")` → `IndexError` | 序列为空时返回"no demand"答案 |
| I2 | `agent.py:122` | 空注册表上 `handle("what is the cost?")` → `KeyError 'assumptions'`（`financial_impact` 返回 `{"error":"no demand"}`）；`wants_order` 分支因用 `.get` 而幸存 | 工具结果统一为 `ToolResult(ok, data, error)`，规划器按 `ok` 分支 |
| S3 | `registry.py:45-55` | `register` 同名静默覆盖 | 抛错或要求 `replace=True` |
| S4 | `scenarios.py:52,66` | 未知情景名静默变基线（`run_scenarios(names=["nope"])` 返回一行 `nope` 且数值=基线） | 未知名抛 `KeyError`；缺 baseline 时显式报错 |
| S5 | `pipeline.py:121-128` | 真实 CSV 路径下 economics `skipped`，report 的 `economics_annual_saving` 静默为 `None` | report 透传 `skipped` 原因 |

### 3.2 需要独立设计的结构性问题

| # | 位置 | 现象 | 方向 |
|---|---|---|---|
| P1（structure 序列 PR 6 已修复：`create_app()` + `WorldStore` 整体替换不可变快照，`/generate` 上限 500 SKU / 180 天，同时只允许一次生成） | `api/app.py:50, 44-48` | 模块级可变单例；`regenerate` 逐字段赋值，FastAPI 同步端点在线程池并发执行时可读到 `wh` 新 / `intel` 旧的撕裂状态；`/generate?n_skus=2000&horizon_days=365` 实测 9.2 s，无鉴权即 DoS 向量 | `create_app()` 工厂 + 不可变 `World` 对象整体原子替换（`_state.world = new_world`）+ `/generate` 限流/上限收紧 |
| P11（structure 序列 PR 5 已修复：`Executor` 对未审批的门控工具不调用 `fn`） | `agent.py:79-85` | `call()` 对 `requires_approval` 工具**仍执行** `tool.fn`，只加一条 note；当前安全仅因 `_propose_order` 无副作用；`Tool.read_only` 只在 `list_tools()`（l.141）里被序列化展示，**执行路径从不检查它** | 执行器级短路：`requires_approval and not approved → 返回 proposal，不调用 fn`；`read_only=False` 且未审批也拒绝 |
| A2/A4 | `scenarios.py:44-46`, `pipeline.py:92`, `api/app.py:28` | 三处反向导入 `sdf.cli.build_registry` | 把 `build_registry` 移到 `foundation`/`synthesis` 边界（建议 `sdf/synthesis/materialise.py` 或 `sdf/foundation/bootstrap.py`），`cli` 只保留薄壳 |
| A3 | `economics.py:65-72`, `warehouse_demo.py:197-213, 387-396, 124-147`, `forecast.py:22-39` | 五份"按 SKU/按天聚合"实现；`financial_impact` 用 `list(stats.items())[:max_skus]` 取**前 400 个首次出现**的 SKU 而非按重要性 | 单一 `demand.py`：`DemandTable(orders) → per_sku_daily(sku) / totals / stats`，其余模块只消费 |
| 双补货逻辑 | `warehouse_demo.py:62-94` vs `215-265` | `replenishment_suggestions`（固定 3 天安全库存、lead=7 硬编码）与 `replenishment_ss_policy`（(s,S)）并存；`insights`、`agent`、`knowledge._replenish`、`simulation` 用前者，`scenarios`、`knowledge._safety`、`economics` 用后者。同一问题"多少 SKU 需要补货"在同一世界里给出 7 和 38 两个答案 | 定义 `ReplenishmentPolicy` 接口，两种策略成为两个实现，所有调用方通过同一入口并显式声明策略；仪表盘两张表分别标注策略名 |
| 上帝对象 | `warehouse_demo.py` 全文 | KPI / 补货 ×2 / 异常 ×2 / 视觉 / 叙事 / 内部聚合混在一个类；`economics` 与 `knowledge` 直接依赖其私有细节 | 拆为 `kpi.py`、`replenishment.py`、`anomaly_rules.py`、`vision.py`、`narrative.py`，`WarehouseIntelligence` 退化为门面（保持现有公共方法签名以保护 API/前端） |
| 导入副作用 | `sdf/__init__.py:18-20`；`api/app.py:20-24` | 顶层 eager import；缺 `fastapi` 时 `raise SystemExit`（不是 `ImportError`），任何试图 `import sdf.api.app` 的测试/工具都会被杀掉 | `__init__` 只导出版本或用惰性 `__getattr__`；`app.py` 抛 `ImportError` 并让 CLI 决定退出 |
| 可选依赖测试 | `tests/test_generators.py:128-140` | 缺 `copulas/sdmetrics` 时 `return`，pytest 计为 **passed**，CI 从未真正跑过这条 | `pytest.importorskip` |
| 审计有损 | `observability.py:28-39` | `_summarise` 把 dict 截到 12 键、list 截到 3 项；"可核查审计轨迹"实际不可完整回放 | 摘要仅用于展示，sink 落盘写完整 JSON。**已处理**（清理 PR 3）：sink 写完整 JSON 与收尾摘要行，`agent`/`pipeline` 有 `--audit-log` |

### 3.3 记录在案、本轮不动

| # | 位置 | 现象 |
|---|---|---|
| S1 | `sdv_synth.py:64-65` | `except Exception: pass` 吞掉 CorrelationSimilarity 失败 |
| S2 | `retail_csv.py:56-63` | 坏行静默 `continue`，无计数 |
| I3 | `schema.py` | dataclass 零校验；适配器写入 `abc_class="?"`，而生成器 `_gen_inventory` 用 `{"A":..}[abc]` 索引，真实 SKU 若回流到生成器会 `KeyError`。校验部分**已处理**（清理 PR 2）：实体构造时校验字段，`?` 为合法的"未分类"。生成器的 `{"A":..}` 表仍只认 A/B/C；它只索引自己生成的 SKU，真实 SKU 目前不会进入这条路径，等真实 SKU 回流生成器时再处理 |
| I5 | `retail_csv.py:28-31`, `sdv_synth.py:31` | `%m/%d/%Y` 先于 `%d/%m/%Y`，DD/MM 数据静默错解（对 UCI 导出成立，对其他来源是隐患） |
| E1/E2/E5 | `registry.stream`、`privacy._two_nearest`、`economics._simulate` | O(n) 全扫 / O(n²) 暴力 / O(T²)。默认世界（28,897 行）下单端点均 <0.1 s，`/scenarios` 0.94 s、`/workflow/run` 0.22 s（各自**重新生成**整个世界）。演示规模无痛，放大前再处理 |
| R1/R2 | 多处 `seed=7`、`sdv_synth` 未设种子；KS 与 KSComplement 极性相反 | 属度量方法论，随 Stage C 处理 |
| R3 | 全仓 | 字面 `# ALGORITHM-HOOK`/`# DATA-HOOK` 只在 `warehouse.py`（4 处）与 `quality.py`（3 处）；其余 17 个模块的 HOOK 只在 docstring 或打印串里。`grep -rn "# ALGORITHM-HOOK" src` 得到的清单与 `CHECKLIST.md` 的 A1–D5 无法自动对齐 |
| 前端 | `dashboard.html` | `regen()` 不传 `horizon_days`；`refreshAll()` 并发 11 请求（含两个重生成世界的端点）；端点路径硬编码 |
| 大文件 | `data/*.csv` 共 1.07 MB | 在 `.gitignore` 白名单内；迁 LFS 或下载脚本另议 |

---

## 4. 目标结构（提案，供项目负责人在"方向性 PR"里裁定）

```
src/sdf/
  __init__.py                 只导出 __version__（无副作用）
  foundation/
    schema.py                 实体（+ 可选 __post_init__ 轻校验）
    registry.py               DataSourceRegistry（register 不再静默覆盖）
    adapters/retail_csv.py    + 返回 LoadReport(rows_skipped, reasons)
  synthesis/
    spec.py                   GenerationSpec（从 warehouse.py 拆出，scenarios 只依赖它）
    warehouse.py              WarehouseGenerator（RNG 调用顺序不变）
    materialise.py            build_registry(spec) -> (SyntheticWarehouse, DataSourceRegistry)   ← 从 cli 迁入
    fit.py sdv_synth.py       （forecast/models/anomaly 已迁至 analytics/，quality/fidelity/tstr/privacy 已迁至 validation/ —— layout PR 3）
    scenarios.py              只保留 SCENARIOS 表与 apply(spec, tweaks) -> spec 的纯变换（不依赖任何上层）
  analytics/                  纯函数，不持有状态（layout PR 3 已建：demand.py forecast.py models.py anomaly.py）
    demand.py                 DemandTable：唯一的按 SKU/按天聚合与统计（已完成）
    metrics.py                mae/rmse/mape(wape)/bias，供 forecast 与 tstr 共用
  application/
    intelligence.py           WarehouseIntelligence 门面（公共方法签名不变；改名已完成，拆分待后续）
    kpi.py                    kpis / abc_distribution / top_movers
    replenishment.py          ReplenishmentPolicy 接口 + RuleOfThumbPolicy + SSPolicy + simulation
    anomaly_rules.py          stockout / dead_stock 规则 + demand_anomalies 包装
    vision.py                 shelf_occupancy_grid / stocktake_discrepancies
    narrative.py              insights
    knowledge.py              路由表 + 处理器（处理器只调用公共入口）
    economics.py              只依赖 analytics.demand + replenishment.SSPolicy
    scenarios.py              run_scenarios：对每个情景 materialise → 评估（PR 2 已从 synthesis 迁入，无再导出）
    agent/
      tools.py                Tool / ToolResult / ToolRegistry
      executor.py             call()：审批门与 read_only 在此强制
      planner.py              Planner 接口 + KeywordPlanner（LLM planner 为 HOOK）
      agent.py                WarehouseAgent 组装
  validation/                 quality.py fidelity.py tstr.py privacy.py（layout PR 3 已建）
  observability.py            RunLogger（摘要与完整落盘分离）
  workflow/pipeline.py        ctx 分为 artifacts 与 resources 两个命名空间
  api/
    app.py                    create_app(world_provider) ；默认 app = create_app()
    state.py                  World 不可变快照 + 原子替换
    static/dashboard.html     不变
  cli/
    __init__.py               click 子命令（已完成）；每个子命令一个函数，只做参数解析与打印
src/sdf/（测试与源码同目录，`testpaths = ["src"]`）
  conftest.py                 已有：默认世界 fixture + 两个内置 CSV 路径 fixture
  golden_test.py              已有：§2.5 的黄金数字（整数精确、浮点 ±0.5%）
  cli_test.py                 已有：每个子命令冒烟 + 退出码
  <module>_test.py            已有：原 tests/test_generators.py 按模块拆入各自目录
  layering_test.py            第 2 步：ast 解析导入图，断言不存在反向依赖
  api/app_test.py             后续：`fastapi.testclient` 端点字段快照（`pytest.importorskip("fastapi")`）
  hooks_test.py               后续：grep `# ALGORITHM-HOOK[<id>]`，与 CHECKLIST.md 的 ID 集合对齐
```

设计约束（延续 `ARCHITECTURE.md`，不在本次重构中推翻）：

- 核心运行时依赖为 numpy / scipy / scikit-learn（2026-09-23 决定）；SDV、FastAPI、LightGBM、pywhy 因果栈与 pydantic 仍只进 extras。
- 生成器的随机数消费顺序不变，黄金数字不变。
- 公共方法签名不变；仪表盘不改。
- HOOK 标记统一为 `ALGORITHM-HOOK[C1]: …` / `DATA-HOOK[D1]: …`，方括号内为 `docs/ALGORITHM_AND_DATA_CHECKLIST.md` 的条目编号（不是行号），可出现在注释或 docstring 中；`sdf hooks` 列出并校验全部标记（cleanup 序列 PR 1）。

---

## 5. 施工顺序（每步一个 PR，前后不可调换）

> 2026-09-23：第 1～4 步的详细计划已落在 [`docs/refactor/layout/`](refactor/layout/00-overview.md)（overview + 每个 PR 一个计划文件；**该序列的 4 个 PR 已全部合入 main**，黄金数字未变），并把第 7 步已完成的 click 迁移之外的"分类"工作（`analytics/`、`validation/` 拆分、`intelligence.py` 改名、统一需求聚合）提前到该序列的第 3 个 PR；本表其余步骤（4～9）在该序列完成后另开计划目录。
>
> 2026-09-23：第 3 步（数值修复）与第 7 步的 `sdf validate` 部分合并为第二个序列，计划在 [`docs/refactor/correctness/`](refactor/correctness/00-overview.md)（4 个 PR：`sdf validate` 单一数字来源 → 错误显式化 → 误差指标 → 需求形态与安全库存）。第 3 步原列出的 C4、C6、I1、I2、S3、S4、S5 放在其 PR 2，C1、C2、C3、C7 在 PR 3，C5 在 PR 4。
>
> 2026-09-23：第 4～6 步（拆分分析类、补货策略、API 状态模型、Agent 执行器）与三项后续需求的接口准备（可插拔合成算法、可组合的策略模拟层、独立 UI）合并为第三个序列，计划在 [`docs/refactor/structure/`](refactor/structure/00-overview.md)，接口契约见其 `interfaces.md`。按项目负责人决定，固定补货规则整体删除。
>
> 2026-09-24：第 4～6 步由 structure 序列（#13–#20，1.0.0）完成。第 8、9 步与问题清单里剩下的两项（工作流的字符串上下文、实体记录不校验）合并为第四个、也是最后一个序列，计划在 [`docs/refactor/cleanup/`](refactor/cleanup/00-overview.md)。

| 步 | PR 类型（按 CONTRIBUTING） | 内容 | 完成判据 |
|---|---|---|---|
| 0 | 方向性（本文） | 项目负责人确认 §4 目标结构与 §3.2 的处理方向 | 本 PR 合并 |
| 1 | 实现 | ~~**特征化测试**~~ 已完成（layout 序列 PR 1）：`src/sdf/conftest.py`、`golden_test.py`、原 `tests/` 按模块拆为同目录 `_test.py`，`pytest.importorskip` 替换 `return`，删除 `tests/` 与 `demo/`；端点契约测试推迟到 API 状态模型那一步一并加 | 不改任何 `src/` 运行时代码；测试全绿 |
| 2 | 实现 | ~~**依赖方向**~~ 已完成（layout 序列 PR 2）：`synthesis/materialise.py`、`synthesis/spec.py`、`application/scenarios.py` 新建；`cli.build_registry` 与 `synthesis.scenarios.run_scenarios` 直接删除，不留再导出（与 `in-branch-api-compat` 一致）；`sdf/__init__` 只剩 `__version__`；`api/app.py` 改抛 `ImportError`；包内导入改单点相对导入，仅为绕开反向边而存在的函数内导入提升到模块级；`layering_test.py` 断言层方向 | 导入图无反向边（由测试断言）；黄金数字与 `sdf demo` 输出不变 |
| 3 | 实现 | ~~**需求聚合统一 + 数值修复**~~ 已完成（layout PR 3 统一聚合；correctness 序列 PR 2–4 完成数值修复，C1–C7、I1、I2、S3–S5 均已处理）：`analytics/demand.py`、`analytics/metrics.py`；`warehouse_demo`、`economics`、`forecast`、`knowledge` 改为消费；顺手修 C1、C2、C3、C4、C5、C6、C7、I1、I2、S3、S4、S5 | 黄金数字中 (s,S)/经济/回测项**会变**（C1/C5 影响），新值写回 `VALIDATION.md` 与 `test_golden.py`，并在 PR 里逐项解释差异 |
| 4 | 实现 | ~~**拆上帝对象**~~ 已完成（structure 序列 PR 1–3：`application/` 按关注点拆分、`WarehouseIntelligence` 为门面；`simulation/` 层承载策略；按项目负责人决定删除固定规则，所有调用方用 (s,S) 策略）：`application/` 按 §4 拆分，`WarehouseIntelligence` 变门面；`ReplenishmentPolicy` 接口；`knowledge`、`agent`、`scenarios` 显式选策略 | 端点契约测试不变；`insights` 与 `/scenarios` 的"需订 SKU 数"口径在文案里标明策略 |
| 5 | 实现 | ~~**API 状态模型**~~ 已完成（structure 序列 PR 6–7：`create_app()`、`WorldStore` 原子替换不可变快照、`GenerateLimits`、端点契约测试；随后 API 迁到 `/api/v1`，`POST /world` 取代 `/generate`）：`create_app()`、不可变 `World`、原子替换、`/generate` 参数上限收紧并记录耗时 | 并发 `POST /generate` + `GET` 压测无撕裂；单例仍导出为 `app` |
| 6 | 实现 | ~~**Agent 执行器**~~ 已完成（structure 序列 PR 5）：`agent/` 子包；审批门在 `executor.call` 强制；`ToolResult`；`Planner` 接口 | 新测试：注册一个有副作用的审批工具，断言 `fn` 未被调用 |
| 7 | 实现 | **CLI**：~~迁 argparse~~ 已于 PR #3 迁到 click（子命令名与默认值不变，`--help`/`--version` 可用，`cli_test.py` 覆盖）；~~本步只剩新增 `validate` 子命令~~ 已完成（correctness 序列 PR 1）：`sdf validate` 输出 §2.5 全部黄金数字（JSON / markdown），`golden_test.py` 与 `VALIDATION.md` 的生成块读同一份快照 | `cli_test.py` 不变通过；`sdf validate` 输出与 `test_golden.py` 一致 |
| 8 | 实现 | ~~**HOOK 规范化**~~ 已完成（cleanup 序列 PR 1）：标记统一为 `ALGORITHM-HOOK[<编号>]` / `DATA-HOOK[<编号>]`；`src/sdf/hooks.py` 扫描标记，`sdf hooks --update-doc` 在清单末尾生成"各条目在代码中的位置"表（`路径::符号`，不含行号），`hooks_test.py` 断言每个标记都对应清单编号且该表是最新的 | `grep` 结果与 CHECKLIST ID 集合相等 |
| 9 | 实现 | ~~**收尾**~~ 已完成（cleanup 序列 PR 2–4）：实体字段校验与 `WarehouseRun`（PR 2）；`observability` 的 sink 写完整 JSON 与收尾摘要行，`agent`/`pipeline` 有 `--audit-log`（PR 3）；`VALIDATION.md` 叙述中的数字改为引用生成块，块内新增序列均值与留出窗口，块外数字标明为记录或示意；测试客户端改用 `httpx2`；UI 加 favicon；合并完成后删除本次重构的远端分支（含 `feature/repo-governance`），保留 `system-v1/synthetic-data-generation`（PR 4） | `sdf validate --update-doc` 后 `VALIDATION.md` 无 diff；远端只剩 `main`、会话分支与 `system-v1/…` |

第 3 步是唯一会改变黄金数字的步骤，因此把它放在第 2 步（纯搬家）之后、第 4 步（纯拆分）之前，使每个 PR 的 diff 只解释一种变化。

---

## 6. 需要项目负责人拍板的事项

1. ~~**零依赖核心是否继续坚持**~~ 已决定：numpy / scipy / scikit-learn 进入核心依赖，pywhy 因果栈作为 `causal` extra。第 3 步中 `models.py`、`fidelity.py`、`privacy.py`、`anomaly.py` 改用 numpy/scipy 实现；数值可能在浮点舍入层面变化，须在同一 PR 更新 `test_golden.py` 与 `VALIDATION.md`。
2. ~~**紧凑单行风格是否保留**~~ 已决定：`ruff` 对齐 sciloom 并启用 `ruff format`，全仓库已在 PR #3 中一次性重排（29 个文件、行为与黄金数字均未变），后续步骤不再有格式 diff。
3. **`replenishment_suggestions` 的固定规则是否退役**。它在仪表盘"补货闭环"视图与 `insights` 里可见；退役意味着前端文案要改。建议保留为 `RuleOfThumbPolicy` 但从 `insights`/`agent` 默认路径切换到 (s,S)。
4. **第 3 步导致的度量数字变化如何对外解释**。MAPE 口径修正后，`VALIDATION.md` 中所有 MAPE 列会变；建议同一 PR 里同时给出旧口径与新口径一次，之后只维护新口径。
5. **`data/` 的 1 MB CSV 是否迁出**。与重构无关，可以并行。

---

## 7. 重构期间的操作纪律

- 每个 PR 开始前重跑 `src/sdf/golden_test.py`，结束后再跑一次；数字变动必须在 PR 描述里逐项列出原因。
- 不在同一个 PR 里同时"搬家"和"改行为"。
- 不改 `WarehouseGenerator` 内 `self._rng` 的调用次数与顺序。
- 不改 `dashboard.html`，除非端点契约测试先改。
- `# ALGORITHM-HOOK` 注释随代码搬家，不丢失。
