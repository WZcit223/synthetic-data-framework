# Demo Script — 5 minutes / 演示讲稿

Audience: management + prospective client. Goal: show the framework's effect and
make the framework-vs-full-system boundary explicit and credible.

**Setup (before the room):**
```bash
pip install fastapi uvicorn
PYTHONPATH=src uvicorn sdf.api.app:app --port 8000
# open http://127.0.0.1:8000
```

---

### 0:00 — Framing (30s)
> "The bottleneck in industrial AI is rarely the model — it's **data cost,
> data scarcity, and trustworthiness**. So we built a framework where **synthetic
> data is the core capability**: we can stand up and demonstrate an AI application
> *before* real data exists, then swap real data in to validate. Warehouse
> management is our first validation scenario because it exercises every core
> capability — data management, decision support, insight, and multimodal vision."

### 0:30 — One architecture, three layers (45s)
Point at the three badges in the header.
> "Everything runs on three layers: a **Foundation** layer where any data source —
> synthetic or real — becomes interchangeable; a **Synthesis** layer that generates
> data from a declarative spec; and an **Application** layer, here the warehouse
> demo. The orange badge is deliberate: this is **framework mode — no data validation
> yet**. That honesty is the point."

### 1:15 — Live synthetic data (45s)
Drag the **SKUs** and **Stockout pressure** sliders, click **Regenerate**.
> "This entire world — 200 SKUs, 28,000 order lines, inventory, sensors — is
> synthetic and regenerates live. In framework mode it's a seeded sampler; the exact
> same spec later drives a fitted generative model. No real data was needed to
> build any of what you're about to see."

### 2:00 — Capability overview, for management (45s)
Gesture across the KPI row and the four capability cards.
> "For a portfolio view: inventory value, cancel and express rates, ABC mix, and
> auto-generated insights. Each capability card names the algorithm that upgrades
> it — you can see exactly where research plugs in."

### 2:45 — Depth: the replenishment closed loop (60s)
Scroll to the deep-dive; pick a SKU in the dropdown.
> "Now one capability end-to-end: real demand history → forecast → reorder point →
> suggested order → **projected service level, 98% to 100%**. This is the loop that
> saves money in a real warehouse. Today the forecast is a baseline — and here's
> the important part —"
Switch to a terminal:
```bash
python -m sdf.cli backtest
```
> "— we already ran it on a **real retail dataset**. The harness backtests four
> models and correctly finds the weekly-seasonality model wins (MAE 46 vs 122 for
> naive). That's our first measured number, and the bar the production model beats."

### 3:45 — Multimodal: vision stocktake (45s)
Scroll to the heatmap.
> "Reusing our multimodal/vision work: a shelf-occupancy heatmap where the camera
> estimate is reconciled against the book inventory. **82% match; 7 locations
> flagged** as shortage or surplus — the misplacements and miscounts a manual audit
> misses. The signal is synthetic today; the real-image hook is marked and ready."

### 4:30 — The honest boundary + the ask (30s)
Hold up / screen-share `ALGORITHM_AND_DATA_CHECKLIST.md`.
> "Everything you saw is a working framework. This checklist is the deliverable that
> comes with it: **exactly which algorithms and which data** turn each demo into
> production — line by line, each tied to a marker in the code. Give us one real
> order history and a handful of labelled shelf images, and we validate the two
> flagship loops. That's the plan."

---

## The one-sentence takeaways
- **Effect:** a full AI-warehouse application, running today, on data we generated.
- **Rigor:** the framework/algorithm boundary is explicit — `# ALGORITHM-HOOK` in code,
  a checklist for the client, and a first real backtest number already on the board.
- **Reusability:** the three layers are domain-agnostic; warehouse is scenario #1.

## Fallback (no server)
Run `python demo/run_demo.py` and `python -m sdf.cli backtest` — both are pure
stdlib and print the same story in the terminal. Screenshots live in the repo PRs.
