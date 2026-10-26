# Supply Chain Inventory Optimization & Reorder Forecasting

[![CI](https://github.com/mlaharsh/supply-chain-inventory-optimization/actions/workflows/ci.yml/badge.svg)](https://github.com/mlaharsh/supply-chain-inventory-optimization/actions/workflows/ci.yml)
[![Live dashboard](https://img.shields.io/badge/dashboard-live-0e7c86)](https://mlaharsh.github.io/supply-chain-inventory-optimization/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-0b1f3a)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-0b1f3a)](LICENSE)

An end-to-end supply-chain analytics portfolio project: synthetic operating history → PostgreSQL model → ABC-XYZ segmentation → EOQ / safety-stock / reorder policy → demand forecasting → probabilistic stockout risk → Tableau executive dashboard.

Built for a Senior Supply Chain Data Analyst / Data Engineer portfolio. Everything is reproducible from a deterministic seed and runs locally without a database, while the PostgreSQL + Tableau deployment path is included.

---

## Live demo

| Artifact | Link | What it shows |
|---|---|---|
| **Executive dashboard** | <https://mlaharsh.github.io/supply-chain-inventory-optimization/> | Designed landing page with the 1440×900 dashboard preview, methodology, and reproduction steps |
| **Full-size preview** | <https://mlaharsh.github.io/supply-chain-inventory-optimization/preview.html> | Responsive, scaled wrapper around the interactive HTML dashboard |
| **CI pipeline** | <https://github.com/mlaharsh/supply-chain-inventory-optimization/actions/workflows/ci.yml> | Tests, full pipeline regeneration, output-contract checks, and downloadable build artifacts |
| **Deployment guide** | [`docs/deployment.md`](docs/deployment.md) | GitHub Pages, Streamlit, Actions, Tableau, and PostgreSQL runbooks |

The GitHub Pages dashboard is static. The Streamlit app (`app.py`) is the interactive version with filters, drilldowns, and CSV downloads; deployment instructions are in the [deployment guide](docs/deployment.md#2-streamlit-community-cloud).

---

## 1. Business problem

Inventory leaders have to balance three competing failures:

1. **Too much stock** ties up cash and increases holding cost.
2. **Too little stock** creates lost sales, expediting costs, and service failures.
3. **Inconsistent supplier lead times** make a static reorder point unreliable.

This project answers four operational questions:

- Which SKUs matter most, and which are hardest to forecast? (ABC-XYZ)
- How much should we order at a time? (EOQ)
- What buffer and reorder point are justified at 90%, 95%, and 99% service levels? (Safety stock / ROP)
- Which SKUs are likely to stock out before the next receipt, and which suppliers are creating the exposure? (Forecasting + Monte Carlo risk + lead-time performance)

## 2. Headline results

Generated from seed `42`, 24 months ended **2026-09-30**:

| Result | Value |
|---|---:|
| Active SKUs / suppliers / days | 60 / 12 / 730 |
| Sales transactions / purchase orders / inventory snapshots | 28,470 / 446 / 6,300 |
| Current on-hand inventory value | **$178,048** |
| 52-week average inventory value | $203,954 |
| Annualized holding cost (52-week average inventory) | **$49,231** |
| Annual consumption value | $1,617,987 |
| ABC mix (A / B / C) | 19 / 19 / 22 |
| XYZ mix (X / Y / Z) | 26 / 18 / 16 |
| High/critical stockout-risk SKUs | **5** (4 critical) |
| SKUs below dynamic ROP / stocked out | 2 / 3 |
| Projected lost-revenue exposure | **$30,834** |
| Weighted supplier on-time rate | 88.3% |
| Forecast holdout WAPE (3 months) | **26.5%** |

> The data is synthetic. A deliberate end-of-horizon replenishment freeze on a subset of high-velocity SKUs creates realistic exceptions for the dashboard. The generator records this in `data/raw/generation_manifest.json`. See [sample findings](docs/sample_findings.md) and the auto-generated `outputs/executive_summary.md`.

### Dashboard preview

![Executive overview dashboard](docs/dashboard_preview.png)

A 1440×900 high-fidelity mockup of the Tableau **Executive Overview** page, built from the seed-42 outputs. The complete workbook specification — data relationships, sheets, calculated fields, actions, and publishing checks — is in [`docs/tableau_dashboard_spec.md`](docs/tableau_dashboard_spec.md). The editable source is [`docs/dashboard_preview.html`](docs/dashboard_preview.html).

### Start here

| If you want to… | Open |
|---|---|
| See the live executive dashboard | <https://mlaharsh.github.io/supply-chain-inventory-optimization/> |
| Run the interactive dashboard locally | `streamlit run app.py` · [setup](docs/deployment.md#2-streamlit-community-cloud) |
| See the business story and exceptions | [`docs/sample_findings.md`](docs/sample_findings.md) |
| Check the formulas and assumptions | [`docs/methodology.md`](docs/methodology.md) |
| Understand the schema and fields | [`docs/data_dictionary.md`](docs/data_dictionary.md) |
| Build or present the dashboard | [`docs/tableau_dashboard_spec.md`](docs/tableau_dashboard_spec.md), [`docs/portfolio_playbook.md`](docs/portfolio_playbook.md) |
| Reproduce the run | [Quickstart](#5-quickstart) |
| Deploy the portfolio | [`docs/deployment.md`](docs/deployment.md) |

## 3. Architecture

```mermaid
flowchart LR
    A["Python synthetic generator\nNumPy / Pandas\n60 SKUs · 24 months"] --> B["PostgreSQL core schema\nsuppliers, products,\nsales, POs, snapshots"]
    A --> C["Raw CSV contract\ndata/raw/*.csv"]
    B --> D["SQL views\nABC-XYZ, lead time,\nSQL ROP engine"]
    B --> E["Quality checks"]
    C --> F["Python analytics\nABC-XYZ · EOQ · SS/ROP\nHolt-Winters / ETS\nMonte Carlo stockout risk"]
    F --> G["Curated Tableau exports\noutputs/tableau/*.csv"]
    F --> H["Analytics outputs\noutputs/analytics/*.csv\nrun_summary.json"]
    D --> I["Tableau dashboard\nor PostgreSQL live connection"]
    G --> I
```

The core pipeline is deliberately database-optional so the project can be reproduced in one command. The SQL and loader show how the same data model would run in production.

## 4. Repository layout

```text
.
├── data/raw/                      # Generated CSVs + generation manifest
├── docs/
│   ├── dashboard_preview.png      # 1440×900 executive dashboard mockup
│   ├── dashboard_preview.html     # Editable source for the mockup
│   ├── data_dictionary.md         # Core schema, derived-field and CSV contracts
│   ├── methodology.md             # Formulas, assumptions, model validation
│   ├── sample_findings.md         # Business narrative from the seeded dataset
│   ├── tableau_dashboard_spec.md  # Wireframe, sheets and calculated fields
│   └── portfolio_playbook.md      # Demo script, résumé bullets, interview prep
├── inventory_opt/                 # Reusable Python package
│   ├── config.py
│   ├── generation.py              # Demand + replenishment simulator
│   ├── inventory.py               # Pure EOQ / SS / ROP / ABC-XYZ formulas
│   ├── analytics.py               # Calendarization, policy, supplier analytics
│   ├── forecasting.py             # statsmodels ETS/Holt-Winters + backtest
│   ├── stockout.py                # Lead-time demand simulation
│   ├── optimization.py            # Forecast-driven ROP and actions
│   └── pipeline.py                # CLI orchestrator and exports
├── scripts/
│   ├── generate_data.py
│   ├── run_analysis.py
│   └── load_postgres.py
├── sql/
│   ├── 01_schema.sql
│   ├── 02_views.sql
│   └── 03_quality_checks.sql
├── tests/
├── outputs/
│   ├── analytics/                 # Detailed analysis tables
│   ├── tableau/                   # Dashboard-ready extracts
│   ├── run_summary.json
│   ├── data_quality_report.json
│   └── executive_summary.md
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── README.md
```

Generated CSVs, `run_summary.json`, and the executive summary are intentionally ignored by Git; they are reproducible artifacts. The generation manifest, SQL, tests, documentation, and dashboard preview are tracked.

## 5. Quickstart

Requires Python 3.11+.

### PowerShell (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m inventory_opt.pipeline --regenerate
python -m pytest
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m inventory_opt.pipeline --regenerate
python -m pytest
```

The full pipeline takes a few seconds on a laptop. It writes:

- `data/raw/*.csv` — reproducible source dataset
- `outputs/analytics/*.csv` — detailed analytical tables
- `outputs/tableau/*.csv` — curated Tableau data sources
- `outputs/run_summary.json` — KPI and model audit
- `outputs/executive_summary.md` — one-page findings

Run analysis only (reuse raw data):

```bash
python -m inventory_opt.pipeline
# or
python scripts/run_analysis.py
```

Generate data only:

```bash
python scripts/generate_data.py --seed 42 --products 60 --understocked-skus 8
```

### Important CLI options

| Option | Purpose |
|---|---|
| `--regenerate` | Rebuild the synthetic core dataset |
| `--seed 42` | Change reproducible demand/lead-time shocks |
| `--products 60` | Number of SKUs (must be ≥ 50 for the brief) |
| `--start 2024-10-01 --end 2026-09-30` | Analysis horizon for a fresh generation |
| `--raw-dir` / `--output-dir` | Isolate a run or a test |

## 6. PostgreSQL deployment

The schema is in [`sql/01_schema.sql`](sql/01_schema.sql); views and quality checks are in [`sql/02_views.sql`](sql/02_views.sql) and [`sql/03_quality_checks.sql`](sql/03_quality_checks.sql).

```bash
createdb supply_chain

# With psql:
psql "postgresql://postgres:postgres@localhost:5432/supply_chain" -f sql/01_schema.sql
psql "postgresql://postgres:postgres@localhost:5432/supply_chain" -f sql/02_views.sql
psql "postgresql://postgres:postgres@localhost:5432/supply_chain" -f sql/03_quality_checks.sql
```

Or use the transactional `COPY` loader, which applies schema, views, and sequence fixes:

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/supply_chain"
python scripts/load_postgres.py --truncate
```

The loader refuses to overwrite populated tables unless `--truncate` is explicit.

> **Build-environment caveat:** no PostgreSQL server or Docker was available when this repository was built. The schema, views, and quality-check SQL were statically reviewed and syntax-parsed with a PostgreSQL parser, but not executed against a live server. Run the commands above against a local instance before relying on the SQL path.

### Data model in 30 seconds

| Table | Grain | Why it exists |
|---|---|---|
| `suppliers` | Supplier | Contracted lead time, variability assumption, on-time target |
| `products` | SKU | Cost, price, holding rate, ordering cost, MOQ, service target |
| `sales_transactions` | Fulfilled sale line | Demand, revenue, channel |
| `purchase_orders` | PO | Order/promise/receipt dates, quoted lead-time snapshot, open supply |
| `inventory_snapshots` | SKU/week | On-hand and inbound at a point in time |

Current stock is **not** denormalized on `products`; the latest inventory snapshot is the source of truth. POs store their own quoted lead time so a later supplier-contract change does not rewrite history. Full details: [`docs/data_dictionary.md`](docs/data_dictionary.md).

## 7. Analysis workflow

### Step 1 — Calendarize before measuring volatility

Raw sales rows only contain selling days. Calculating a CV on those rows hides zero-demand days and makes intermittent SKUs look more stable than they are. The pipeline builds a calendar-complete SKU-day table before week/month aggregation.

### Step 2 — ABC-XYZ

**Annual consumption value** uses the trailing 365 days and standard cost:

\[
ACV_i = \text{annual units}_i \times \text{unit cost}_i
\]

SKUs are sorted by descending ACV and classified by cumulative value:

- **A**: first 80% of consumption value
- **B**: next 15% (up to 95%)
- **C**: remaining 5%

The implementation assigns a SKU to a class based on cumulative value *before* it, so the boundary SKU completes A's 80% rather than being pushed into B.

**XYZ** uses the coefficient of variation of **calendar-complete weekly demand over the trailing 52 weeks**:

\[
CV = \frac{\sigma_{weekly}}{\mu_{weekly}}, \qquad
X: CV \le 0.50,\quad Y: 0.50 < CV \le 1.00,\quad Z: CV > 1.00
\]

Intermittent demand therefore lands in Y/Z, which tells the planner that the normal safety-stock approximation deserves extra scrutiny.

### Step 3 — EOQ

Holding cost per unit per year:

\[
H = c \times h
\]

Economic order quantity:

\[
EOQ = \sqrt{\frac{2DS}{H}}
\]

where:

- \(D\) = annual demand
- \(S\) = fixed ordering cost per purchase order
- \(c\) = unit cost
- \(h\) = annual holding-cost percentage (e.g. 0.22)

The raw EOQ is preserved in `eoq_units`. `recommended_order_qty` enforces the MOQ. The simulator uses a practical cap of roughly 120 days of demand; a real planner should also impose pack size, cash, shelf-life, and supplier capacity constraints.

### Step 4 — Safety stock with variable demand *and* variable lead time

For normally distributed, independent daily demand and lead time:

\[
SS = Z \times \sqrt{\bar L \sigma_D^2 + \bar D^2 \sigma_L^2}
\]

\[
ROP = \bar D \bar L + SS
\]

This is the variance of lead-time demand: lead-time uncertainty contributes \(\bar D^2\sigma_L^2\), while daily demand noise contributes \(\bar L\sigma_D^2\).

| Service level | Z |
|---:|---:|
| 90% | 1.2816 |
| 95% | 1.6449 |
| 99% | 2.3263 |

The output has complete `safety_stock_*_units` and `rop_*_units` columns for all three levels, plus a **forecast-driven dynamic ROP** used by the reorder engine. The service level is the probability of no stockout in a replenishment cycle, not the fill rate. See [methodology](docs/methodology.md#safety-stock-and-reorder-point).

The weekly snapshot extract also carries **retrospective** planning fields — `historical_safety_stock_target_units`, `historical_rop_target_units`, `on_hand_vs_rop_units`, and `snapshot_stock_status` — so the trend chart compares each week's stock with the policy that applied at that time. Current stockout probability is a point-in-time measure and appears in `inventory_overview.csv` and `reorder_alerts.csv`, not in the historical snapshot extract.

### Step 5 — Demand forecasting

Per SKU, monthly demand is fit with `statsmodels.tsa.holtwinters.ExponentialSmoothing`. Candidate models:

- Holt-Winters additive seasonality with damped trend (seasonal SKUs)
- Damped / linear trend exponential smoothing
- Simple exponential smoothing

AIC selects the specification **in-sample**. The last three months are held out to report out-of-sample WAPE; the holdout is **not** used to choose the model, so the accuracy estimate is not leakage-optimistic. Future forecasts cover three months and include approximate 95% intervals from in-sample RMSE. Results for seed 42:

- Weighted holdout WAPE: **26.5%**
- Weighted bias: **+1.2%**
- 60 SKUs evaluated

Final model per SKU (fit on 24 months):

| Model | SKUs |
|---|---:|
| Simple exponential smoothing | 43 |
| Holt-Winters additive (damped) | 16 |
| Linear trend ETS | 1 |

All 16 Holt-Winters selections are seasonal SKUs. Two seasonal SKUs selected simple exponential smoothing and had high holdout errors — a signal that 24 months is a thin history for annual seasonality. See [`docs/sample_findings.md`](docs/sample_findings.md) for the error breakdown by demand archetype.

**Final model vs holdout refit.** The final forecast is fit on all 24 months. The holdout is a separate refit on the first 21 months, and AIC can select a different specification on that shorter window: on seed 42 the holdout refit selected simple exponential smoothing for **14 of the 16** SKUs that ultimately use Holt-Winters. `forecast_accuracy.csv` exposes both `final_model` and `holdout_model` so the distinction is auditable. The reported seasonal WAPE therefore measures the selection-and-forecast procedure at 21 months, not a validation of the exact final specification. That instability is a finding, not something to hide.

The forecast is not treated as truth. Its rate uncertainty feeds the stockout simulation, and the dashboard shows confidence bands.

### Step 6 — Probabilistic stockout risk

For each SKU, 20,000 paths simulate:

- lead time from a gamma distribution matched to supplier mean/variance;
- a daily demand rate from the forecast distribution;
- lead-time demand from a negative binomial calibrated to historical daily dispersion.

\[
P(\text{stockout}) = P(D_L > A)
\]

where \(A\) = on-hand plus open POs promised inside the lead-time horizon. The analytic normal benchmark is also stored for auditability:

\[
P(D_L > A) = 1-\Phi\left(\frac{A-\bar D\bar L}
{\sqrt{\bar L\sigma_D^2+\bar D^2\sigma_L^2+
(\bar L\sigma_{\text{forecast rate}})^2}}\right)
\]

Risk tiers: **Low** < 10%, **Watch** 10–25%, **High** 25–50%, **Critical** ≥ 50%. The primary risk flag is High/Critical.

### Step 7 — Reorder action engine

The current on-hand position, all open inbound, forecast lead-time demand, dynamic ROP, projected ending inventory, and risk probability combine into an action status:

- `Stocked Out`
- `Reorder Now`
- `Expedite` (high risk despite inbound)
- `At Risk`
- `Inbound Pending`
- `Watch`
- `Healthy`

The recommended quantity is a decision-support signal, not an automatic purchase order.

## 8. Supplier lead-time impact

For each received PO:

\[
\text{Actual LT} = \text{received date} - \text{order date}
\]

\[
\text{Variance} = \text{actual LT} - \text{promised LT}
\]

Supplier scorecards report actual vs promised, on-time rate, average days late, P90 lead time, standard deviation, open/overdue POs, and the SKU-level cost of variability:

\[
\text{SS}_{\text{variable}} - \text{SS}_{\text{constant promised LT}}
\]

This compares the lead-time-variable safety stock with a constant-promised-lead-time baseline, and converts the incremental units to dollars. A separate cycle-stock extension captures the extra inventory required simply because average actual lead time is longer than promised. The dashboard turns this into a supplier risk-vs-cost view.

## 9. Tableau dashboard

The executive layout is previewed above and published on GitHub Pages: [landing page](https://mlaharsh.github.io/supply-chain-inventory-optimization/) · [full-size preview](https://mlaharsh.github.io/supply-chain-inventory-optimization/preview.html). The complete build specification is here: [`docs/tableau_dashboard_spec.md`](docs/tableau_dashboard_spec.md).

Data sources in `outputs/tableau/`:

| File | Grain | Dashboard use |
|---|---|---|
| `inventory_overview.csv` | SKU | ABC-XYZ, reorder engine, KPI cards |
| `abc_xyz_summary.csv` | ABC × XYZ | Matrix heatmap |
| `weekly_demand.csv` | SKU-week | Demand trend |
| `monthly_demand_forecast.csv` | SKU-month | Actual + forecast + interval |
| `demand_forecast.csv` | SKU-month future | Forecast detail |
| `supplier_performance.csv` | Supplier | Lead-time scorecard |
| `purchase_order_lead_times.csv` | PO | Actual vs promised dot plot |
| `inventory_snapshots.csv` | SKU-week | On-hand vs retrospective ROP trend |
| `forecast_accuracy.csv` | SKU | Forecast quality |
| `reorder_alerts.csv` | Actionable SKU | Pre-filtered action queue |

Recommended Tableau pages:

1. **Executive Overview** — KPI band, ABC-XYZ heatmap, holding-cost concentration, risk queue.
2. **Reorder Engine** — dynamic ROP vs inventory position, risk probability, suggested order, inbound POs.
3. **Supplier Performance** — promised vs actual lead time, on-time rate, variance, safety-stock exposure.
4. **SKU Drilldown** — actual vs forecast, confidence band, inventory vs ROP, PO timeline.

The spec includes a wireframe, exact calculated fields, filters, dashboard actions, formatting, and publishing checklist.

Three field-level cautions for the build:

- `annual_holding_cost_52w_avg` is the annualized cost of the **52-week average inventory**, not the ending snapshot. It is the right run-rate measure, but it can differ materially from `current_inventory_value`.
- `supplier_total_lead_time_exposure_value` is a **supplier attribute repeated on every SKU row**. Do not sum it at SKU grain; use `supplier_performance.csv` for supplier totals or sum the SKU-level `lead_time_exposure_value`.
- `inventory_snapshots.csv` contains historical ROP fields for trend analysis, not the current stockout probability. Current risk is in `inventory_overview.csv` and `reorder_alerts.csv`.

## 10. Outputs and definitions

Detailed definitions are in [`docs/data_dictionary.md`](docs/data_dictionary.md). Key action fields:

| Field | Definition |
|---|---|
| `annual_holding_cost_52w_avg` | Annualized holding cost of 52-week average inventory; not the ending-snapshot cost |
| `inventory_position_units` | On hand + all open inbound |
| `available_for_lead_time_units` | On hand + POs promised within the lead-time horizon |
| `dynamic_rop_target_units` | Forecast daily rate × lead time + forecast-driven safety stock at the SKU's target service level |
| `stockout_probability` | Monte Carlo probability that lead-time demand exceeds available units |
| `risk_tier` | Low / Watch / High / Critical |
| `reorder_status` | Operational action state |
| `suggested_order_units` | Decision-support top-up quantity when action is required |
| `projected_ending_inventory_units` | Available units − expected lead-time demand |
| `lead_time_exposure_value` | SKU-level incremental safety + cycle stock required for actual supplier lead time, at cost |
| `historical_rop_target_units` | Retrospective ROP that applied in each weekly snapshot; for trend analysis only |
| `snapshot_stock_status` | Snapshot on-hand vs the retrospective ROP, not current risk |

## 11. Tests and validation

```bash
python -m pytest
```

The suite contains **15 tests** and covers:

- closed-form EOQ, safety-stock, and ROP calculations;
- ABC cumulative-value boundaries and XYZ thresholds;
- forecast output validity and a 3-month holdout;
- lead-time-horizon demand conversion;
- Monte Carlo risk monotonicity and zero-demand behavior;
- synthetic data integrity and final snapshot completeness;
- a full 10-SKU pipeline smoke test with Tableau export checks.

The pipeline also validates unique SKUs, probability bounds, non-negative stock/forecasts, future forecast horizon, finite ROPs, and that current stock matches the latest snapshot. `sql/03_quality_checks.sql` contains database controls for duplicates, orphan records, invalid PO dates, missing snapshots, and calendar completeness; those SQL checks require a live PostgreSQL instance to execute.

## 12. Key assumptions and limitations

Documented in full in [`docs/methodology.md`](docs/methodology.md):

- EOQ assumes deterministic constant demand, fixed costs, no quantity discounts, no stockouts, and no supplier capacity constraints.
- Safety stock assumes independent normally distributed demand/lead time and targets cycle service level. It is a planning approximation, especially for intermittent SKUs; the Monte Carlo model is the operational cross-check.
- Lost sales censor observed demand. In a production system, capture unconstrained demand or stockout events to reduce forecast bias.
- Lead-time mean/variance is estimated at supplier level. If lead times vary materially by SKU/route, model at that lower grain.
- Forecasts are per SKU with no hierarchy reconciliation, promotion pipeline, or external drivers. A production upgrade should use hierarchical reconciliation, rolling-origin evaluation, and override workflows.
- Holding cost is the annualized cost of the **52-week average inventory**, not the ending snapshot. It is a run-rate view; current on-hand value can be materially lower after a depletion event.
- The synthetic data is designed for portfolio demonstration, not a representation of any real company.
- Tableau workbook is specified, not shipped as a `.twb/.twbx`; the exported CSVs and [`docs/dashboard_preview.png`](docs/dashboard_preview.png) make the intended build concrete.
- The PostgreSQL path is supplied but was not live-tested in the build environment; the database-optional Python pipeline is the verified path.

## 13. Portfolio talking points

- Why calendar-complete zeros matter for intermittent-demand CV.
- Why ABC is value-based rather than a fixed 20% SKU count.
- Why EOQ is an economic baseline, not an ordering instruction.
- Why service level is a cycle-level probability, not a fill rate.
- Why variable lead time has a squared effect on safety stock.
- Why the forecast WAPE is high for intermittent SKUs and why that is expected.
- How supplier variance converts directly into working-capital exposure.
- How to prioritize limited planner attention using risk × value.

See [`docs/portfolio_playbook.md`](docs/portfolio_playbook.md) for a five-minute demo script, ten-minute technical walkthrough, screenshot checklist, résumé bullets, interview prompts, and a production roadmap.

## 14. Deployment

The public portfolio is deployed in layers:

| Layer | Host | Status |
|---|---|---|
| Source code | GitHub | Live |
| Executive dashboard | GitHub Pages (`main` / `docs`) | Live — <https://mlaharsh.github.io/supply-chain-inventory-optimization/> |
| Interactive dashboard | Streamlit Community Cloud (`app.py`) | See the [deployment guide](docs/deployment.md#2-streamlit-community-cloud) |
| Tests + regenerated artifacts | GitHub Actions | [CI workflow](https://github.com/mlaharsh/supply-chain-inventory-optimization/actions/workflows/ci.yml) |
| Workbook | Tableau Public | Optional — specification included, no workbook published |
| Database | Managed PostgreSQL | Optional — SQL included, not live-tested |

The dashboard snapshot in `outputs/tableau/` (10 CSVs, about 2 MB) is committed so the Streamlit app has data without running the pipeline at startup. All other generated files remain ignored and reproducible. Full runbooks, including Pages setup, Streamlit deployment, artifact retention, Tableau Public, and managed PostgreSQL, are in [`docs/deployment.md`](docs/deployment.md).

## License

MIT © 2026 MLA Harsh. See [`LICENSE`](LICENSE).
