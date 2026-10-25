# Portfolio Playbook

**Project:** Supply Chain Inventory Optimization & Reorder Forecasting  
**Artifact:** reproducible Python + PostgreSQL + Tableau portfolio project  
**Dataset:** 60 SKUs, 12 suppliers, 24 months, deterministic seed 42  
**Analysis date:** 2026-09-30

This playbook turns the repository into a presentation. It gives you a demo script, a screenshot checklist, résumé bullets, interview answers, a publishing checklist, and a production roadmap. Use the numbers exactly as reported; do not imply that the synthetic dataset represents a real company.

---

## 1. What the project proves

In one project, it demonstrates that you can:

1. **Model an operating dataset** — design a five-table PostgreSQL schema whose grain, keys, and history-preserving choices are defensible.
2. **Turn raw transactions into planning logic** — calendarize demand, handle intermittent zeros, build ABC-XYZ, EOQ, safety stock, and ROP.
3. **Forecast and quantify uncertainty** — select per-SKU exponential smoothing models, backtest on a holdout, and convert forecast error into a probabilistic stockout risk.
4. **Connect analysis to action** — produce a ranked reorder queue, supplier exposure, and an executive dashboard specification rather than a pile of charts.
5. **Engineer for reproducibility** — one command regenerates the data and outputs; tests cover formulas, data integrity, and the end-to-end pipeline.

The strongest signal is not any single formula. It is the **chain of reasoning from schema → metric → decision**, with assumptions and failure modes stated explicitly.

---

## 2. The two-minute elevator pitch

> I built an end-to-end inventory optimization project on 24 months of synthetic supply-chain data for 60 SKUs and 12 suppliers. The pipeline loads a five-table PostgreSQL model, builds calendar-complete demand, segments SKUs with ABC-XYZ, calculates EOQ and service-level-based safety stock, forecasts monthly demand with statsmodels, and runs a 20,000-path Monte Carlo simulation of stockout risk over supplier lead time.
>
> The output is a planner-ready exception queue and a Tableau dashboard spec. On the seeded dataset, 5 SKUs are high or critical risk, 3 are already stocked out, and projected lost-revenue exposure is about $30,800, concentrated in one AX SKU. Annualized holding cost is about $49,200 on a 52-week average inventory of about $204,000.
>
> The important part is that the model separates **value concentration**, **forecastability**, and **service risk**. A SKU can be expensive to hold and still be the most urgent stockout. The project also documents where the approach breaks — censored demand, intermittent SKUs, and a single-location assumption — and what I would change in production.

---

## 3. Five-minute demo script

### Before you present

- Run `python -m inventory_opt.pipeline --regenerate` and `python -m pytest`.
- Open `docs/dashboard_preview.png` full-screen, or open `docs/dashboard_preview.html` in a browser at 1440×900.
- Keep these files ready in tabs or windows:
  - `outputs/run_summary.json`
  - `outputs/tableau/reorder_alerts.csv`
  - `outputs/tableau/supplier_performance.csv`
  - `docs/methodology.md`
- Do not read the README aloud. Use it as a leave-behind.

### 0:00–0:30 — Frame the problem

Say:

> Inventory teams are managing three failures at once: too much cash in stock, too little service, and supplier lead times that make a static reorder point unreliable. I built this to connect all three in one decision loop.

Point at the KPI band:

- **$178,048** current on-hand value
- **$49,231** annualized holding cost
- **5** high/critical risk SKUs
- **$30,834** projected lost-revenue exposure
- **26.5%** weighted holdout WAPE
- **88.3%** weighted supplier on-time rate

### 0:30–1:20 — Show the data model, not just the dashboard

Open the schema section of the README or `docs/data_dictionary.md`.

Key points to make:

- Five tables: `suppliers`, `products`, `sales_transactions`, `purchase_orders`, `inventory_snapshots`.
- Current stock comes from the latest snapshot, not a denormalized column on `products`.
- Each PO stores its own quoted lead time, so a later supplier-contract change does not rewrite history.
- The pipeline is database-optional: the CSVs are a contract, and the PostgreSQL loader is the production path.

Why this matters: **the dashboard is only as trustworthy as the grain beneath it.**

### 1:20–2:10 — ABC-XYZ and the value/volatility split

Point at the matrix.

- A class: 19 SKUs, **81.2%** of annual consumption value.
- AX: 9 SKUs, **60.1%** of ACV — protect these.
- CZ: 11 SKUs, **2.0%** of ACV — do not spend planner attention proportional to SKU count.
- The A class carries **62.6%** of current inventory value and **70.5%** of holding cost.

Say:

> ABC is value-based, not a fixed 20% SKU cut. XYZ uses calendar-complete weekly demand, so zero-demand days are not hidden. That is why intermittent SKUs land in Y and Z instead of looking artificially stable.

### 2:10–3:00 — Policy: EOQ, safety stock, ROP

Use the formulas as a whiteboard, not a lecture.

- \(EOQ = \sqrt{2DS/H}\), where \(H = c \times h\).
- \(SS = Z\sqrt{\bar L\sigma_D^2 + \bar D^2\sigma_L^2}\).
- \(ROP = \bar D\bar L + SS\).

Make two distinctions:

1. **EOQ is an economic baseline, not an order instruction.** MOQ, pack size, shelf life, cash, and supplier capacity still apply.
2. **95% service level is a cycle service level**, not a fill rate or OTIF.

Then mention the static columns for 90/95/99% and the forecast-driven dynamic ROP used by the action engine.

### 3:00–3:50 — Forecast and risk

- Per-SKU monthly ETS/Holt-Winters; AIC selects the specification.
- The last three months are held out **only for reporting accuracy**, not for model selection.
- The holdout is a separate refit on 21 months, so its AIC choice can differ from the final 24-month model. On seed 42, 14 of the 16 final Holt-Winters SKUs selected simple exponential smoothing in the holdout.
- Weighted holdout WAPE: **26.5%**; steady SKUs **11.2%**, intermittent SKUs **49.5%**.
- 20,000 Monte Carlo paths combine variable lead time, demand-rate uncertainty, and negative-binomial lead-time demand.

Say:

> I do not treat the point forecast as truth. The forecast feeds a distribution, and the output is a probability that lead-time demand exceeds available stock. That is why the dashboard can distinguish a Watch item from a Critical one even when both have the same point forecast.

### 3:50–4:40 — The exception queue

Open the reorder table in the dashboard preview or `reorder_alerts.csv`.

Tell the story:

- **SKU-0004** — AX, 5 units on hand, 224-unit dynamic ROP, 100% stockout probability, **$26,463** of the **$30,834** total exposure. It was expensive to hold on a 52-week average and is critical today.
- **SKU-0047** — 558 units in position, 628 ROP, 41% risk, 48-day lead time. The action is to validate inbound and consider expedite, not panic-buy.
- **SKU-0023** — 113 units, 12% risk, Watch. Monitor; no order today.
- Three SKUs are already stocked out: SKU-0044, SKU-0042, SKU-0040.

Say:

> Suggested quantities are decision support. They respect MOQ but not cash, storage, or supplier capacity. The queue is designed for a 15-minute daily stand-up, not automated purchasing.

### 4:40–5:00 — Supplier exposure and close

- Sierra Plastics has the largest exposure at **$2,470**, driven by seven SKUs including SKU-0004.
- Redwood Paper is the clearest variability signal: **6.1-day** lead-time standard deviation, **66.7%** on-time, +3.2-day average variance.
- Weighted on-time is **88.3%**, but averages hide the late tail that drives safety stock.

Close with the limitation:

> This is a single-location planning model on synthetic data. In production I would add unconstrained demand, supplier-lane lead times, rolling-origin validation, and approval controls before any suggested order became a PO.

---

## 4. Ten-minute technical deep dive

Use this version for a data analyst, data engineer, or analytics engineer interview.

### 4.1 Schema and grain (2 minutes)

| Table | Grain | Design decision |
|---|---|---|
| `suppliers` | Supplier | Contracted lead time, variability assumption, on-time target |
| `products` | SKU | Cost, price, holding rate, ordering cost, MOQ, service target |
| `sales_transactions` | Fulfilled sale line | Demand, revenue, channel |
| `purchase_orders` | PO | Order/promise/receipt dates, quoted lead time snapshot, open supply |
| `inventory_snapshots` | SKU × week | On-hand and inbound at a point in time |

Defend these choices:

- **Snapshot table instead of a stock column on `products`:** stock is time-varying; a column would overwrite history and make retrospective ROP impossible.
- **Quoted lead time on the PO:** preserves the promise made at order time; supplier master data can change later.
- **Raw CSV plus PostgreSQL:** the CSV contract makes the project reproducible without a server; the SQL path shows production deployment.
- **Sequence fixes in the loader:** CSV-loaded IDs do not advance PostgreSQL sequences automatically; the loader handles that.

### 4.2 Calendarization and ABC-XYZ (2 minutes)

- Raw sales rows contain only selling days. A CV on those rows hides zero-demand days.
- Build a calendar-complete SKU-day table, then aggregate to weeks and months.
- ABC: sort by annual consumption value descending, assign by cumulative value before the SKU, so the boundary SKU completes the 80% class.
- XYZ: CV of calendar-complete weekly demand over the trailing 52 weeks; X ≤ 0.50, Y ≤ 1.00, Z > 1.00.
- AIC selects the forecast model; the holdout is not used for selection, avoiding leakage-optimistic accuracy.

### 4.3 Safety stock derivation (2 minutes)

For independent daily demand \(D\) and lead time \(L\):

\[
\operatorname{Var}(D_L) = \bar L\sigma_D^2 + \bar D^2\sigma_L^2
\]

\[
SS = Z\sqrt{\bar L\sigma_D^2 + \bar D^2\sigma_L^2}, \qquad ROP = \bar D\bar L + SS
\]

Explain the two terms:

- \(\bar L\sigma_D^2\): demand noise over an average lead time.
- \(\bar D^2\sigma_L^2\): the same daily rate applied to a longer or shorter lead time. Because the rate is squared, lead-time variance can dominate for high-volume SKUs.

Then state the assumption: independence and approximate normality. For intermittent SKUs, the normal approximation is weak; the Monte Carlo model is the cross-check.

### 4.4 Monte Carlo stockout risk (2 minutes)

For each SKU:

1. Draw lead time from a gamma distribution matched to supplier mean/variance.
2. Draw a daily demand rate from the forecast distribution.
3. Draw lead-time demand from a negative binomial calibrated to historical daily dispersion.
4. Compare with available stock: on-hand plus POs promised inside the lead-time horizon.
5. Report \(P(D_L > A)\) over 20,000 paths.

Risk tiers: Low < 10%, Watch 10–25%, High 25–50%, Critical ≥ 50%.

Explain why four SKUs show 100%: they have no supply inside the lead-time window, so the probability is not a model error. It is the correct answer to the question being asked.

### 4.5 Validation and failure modes (2 minutes)

- 15 tests: formula unit tests, ABC/XYZ boundaries, forecast validity, Monte Carlo monotonicity, synthetic data integrity, and a 10-SKU end-to-end smoke test.
- Pipeline validation: unique SKUs, probability bounds, non-negative stock/forecasts, future horizon, finite ROPs, latest snapshot equality.
- SQL quality checks: duplicates, orphans, invalid PO dates, missing snapshots, calendar completeness.
- Known limitations: censored demand, single-location, supplier-level lead-time variance, thin 24-month seasonality, no hierarchy reconciliation, no write-back controls.
- No live PostgreSQL server was available in the build environment, so the SQL is statically reviewed but not server-executed. Say this plainly; do not claim a live deployment.

---

## 5. Screenshot and artifact checklist

Capture these for a portfolio site, GitHub README, or slide deck. Use a 1440×900 browser viewport for the dashboard. Keep the UI text legible; do not stretch a screenshot beyond its native resolution.

| # | Artifact | What it proves | Suggested caption |
|---:|---|---|---|
| 1 | `docs/dashboard_preview.png` | Executive layout, KPI band, ABC-XYZ, risk queue, holding-cost Pareto, supplier exposure, ROP exceptions | "Executive overview: value, risk, and action in one view" |
| 2 | `outputs/tableau/abc_xyz_summary.csv` as a table or heatmap | Segment counts and value shares reconcile | "ABC-XYZ matrix: 60 SKUs, 81.2% of value in A" |
| 3 | `outputs/tableau/reorder_alerts.csv` | Actionable exception queue with probabilities and suggested quantities | "Reorder queue: 5 high/critical SKUs, $30.8k exposure" |
| 4 | `outputs/tableau/supplier_performance.csv` | On-time, P90, lead-time std, exposure value by supplier | "Supplier scorecard: averages hide the late tail" |
| 5 | `docs/methodology.md` formula block | Mathematical rigor and assumptions | "Safety stock with variable demand and variable lead time" |
| 6 | `sql/01_schema.sql` + `sql/02_views.sql` | Relational modeling and SQL analytics | "PostgreSQL schema and SQL ROP engine" |
| 7 | `python -m pytest` output | Reproducibility and quality control | "15 tests covering formulas, data integrity, and pipeline" |
| 8 | `outputs/run_summary.json` | Deterministic KPI and model audit | "One command produces a complete run summary" |

### Screenshot quality rules

- Show the **entire** dashboard, including the synthetic-data footer.
- Do not crop out the caveat that the data is synthetic.
- Use the seed-42 numbers consistently; do not mix runs.
- If you annotate, use one accent color and no more than three callouts.
- Prefer a PNG for dashboards; use JPEG only when file size matters.
- Name files descriptively: `dashboard_executive_overview.png`, not `screenshot1.png`.

---

## 6. Résumé bullets

Choose three or four. Keep the numbers; they are reproducible.

### Supply-chain analyst version

- Built an end-to-end inventory optimization model for **60 SKUs / 12 suppliers / 24 months**, combining ABC-XYZ segmentation, EOQ, service-level safety stock, and forecast-driven reorder points.
- Quantified **$30.8k** projected lost-revenue exposure across **5** high/critical-risk SKUs and converted the result into a prioritized reorder queue with suggested quantities and supplier actions.
- Modeled **$49.2k** annualized holding cost on a **$204.0k** 52-week average inventory; identified a long-tail concentration where the top 10 SKUs drive **49.3%** of carrying cost.
- Diagnosed supplier lead-time risk beyond averages: one supplier had a **6.1-day** lead-time standard deviation and **66.7%** on-time rate, despite a weighted portfolio on-time rate of **88.3%**.

### Data analyst version

- Designed a five-table PostgreSQL model and a database-optional Python pipeline that regenerates **28,470 sales rows**, **446 POs**, and **6,300 inventory snapshots** from a deterministic seed.
- Implemented per-SKU ETS/Holt-Winters forecasting with AIC selection and a leakage-controlled 3-month holdout; achieved **26.5%** weighted WAPE, with error decomposed by demand archetype.
- Built a **20,000-path** Monte Carlo stockout simulation combining variable lead time, demand-rate uncertainty, and negative-binomial demand; stored an analytic normal benchmark for auditability.
- Wrote **15 automated tests** and SQL quality checks for formula correctness, segment boundaries, forecast validity, referential integrity, and end-to-end pipeline behavior.

### Data engineer / analytics engineer version

- Built a modular Python package (`config`, `generation`, `inventory`, `analytics`, `forecasting`, `stockout`, `optimization`, `pipeline`) with typed dataclasses, validated CSV contracts, and a one-command CLI.
- Designed a normalized PostgreSQL schema with history-preserving PO lead times, weekly inventory snapshots, analytical views, and a transactional `COPY` loader with sequence repair and overwrite protection.
- Produced **10 Tableau-ready extracts** at four different grains, with explicit grain documentation and fan-out warnings to prevent double counting.
- Documented null semantics, field lineage, formula assumptions, validation controls, and a dashboard build spec suitable for another analyst to reproduce.

### Short LinkedIn version

> Built a reproducible supply-chain inventory optimization project: 60 SKUs, 24 months, PostgreSQL, ABC-XYZ, EOQ, variable-lead-time safety stock, per-SKU demand forecasting, and a 20,000-path Monte Carlo stockout model. The seeded run surfaces 5 high/critical SKUs and $30.8k of projected lost-revenue exposure. The part I care about most: every metric traces back to a documented grain and assumption.

---

## 7. Interview prompts and strong answers

### Q1. Why not just use a fixed safety-stock rule?

**Answer:** A fixed rule ignores both demand volatility and lead-time volatility. The project uses \(SS = Z\sqrt{\bar L\sigma_D^2 + \bar D^2\sigma_L^2}\), so a high-volume SKU with a variable supplier gets a larger buffer than a low-volume SKU with the same average lead time. It also exposes the trade-off: moving the whole portfolio from 95% to 99% would add roughly **$17.7k** of inventory and **$4.2k** of annual holding cost, which is rarely justified for CZ items.

### Q2. Why is ABC not just the top 20% of SKUs?

**Answer:** Because value concentration is empirical, not a fixed count. In this dataset, 19 of 60 SKUs (**31.7%**) produce **81.2%** of annual consumption value. Assigning by cumulative value lets the data define the boundary. The implementation assigns a SKU to a class based on cumulative value before it, so the boundary SKU completes A rather than being pushed into B.

### Q3. Why does the forecast WAPE look high?

**Answer:** The portfolio mixes steady, seasonal, and intermittent demand. Weighted WAPE is **26.5%**, but steady SKUs are **11.2%** and intermittent SKUs are **49.5%**. Intermittent demand has many zero months; a point forecast is a weak representation. That is why the risk layer is probabilistic and why the dashboard shows SKU-level WAPE rather than one headline number.

### Q4. Why use AIC if you have a holdout?

**Answer:** AIC is used for in-sample specification selection; the holdout is used only to report out-of-sample accuracy. The final forecast is fit on all 24 months, while the holdout is a separate refit on the first 21 months, so AIC can choose a different specification. On seed 42, 14 of the 16 final Holt-Winters SKUs selected simple exponential smoothing in the holdout. `forecast_accuracy.csv` reports both `final_model` and `holdout_model`, and the seasonal WAPE should be read as the performance of the selection procedure at 21 months, not as a validation of the exact final model. That instability is a finding about the thin seasonality history.

### Q5. Why four SKUs at 100% stockout probability?

**Answer:** They have no available supply inside the lead-time window. The model is not claiming certainty about the future; it is answering a conditional question: given current on-hand, open POs promised inside the horizon, and simulated lead-time demand, what fraction of paths end in a stockout? When available stock is zero and demand is positive, the answer is 100%. The stress scenario deliberately creates this state.

### Q6. What is the difference between inventory position and available-for-lead-time units?

**Answer:** Inventory position is on-hand plus **all** open inbound. Available-for-lead-time is on-hand plus only POs promised **inside** the lead-time horizon. A PO arriving after the risk window does not protect service during that window. This distinction prevents the model from overstating coverage.

### Q7. How do you avoid double counting supplier exposure?

**Answer:** `lead_time_exposure_value` is a SKU-level measure. `supplier_total_lead_time_exposure_value` is a supplier attribute repeated on every SKU row. Summing the supplier attribute at SKU grain inflates the total, so the dashboard uses `supplier_performance.csv` for supplier totals and sums the SKU-level column only at SKU grain.

### Q8. What would you do first in production?

**Answer:** Fix the demand signal before adding model complexity. Capture unconstrained demand and stockout events, then add supplier-lane lead-time distributions, rolling-origin validation, and approval controls. A better model on censored demand is still biased.

### Q9. Why PostgreSQL if the pipeline runs on CSVs?

**Answer:** The CSV path makes the portfolio reproducible without infrastructure. The PostgreSQL schema shows the production data model: constraints, keys, views, and quality checks. The loader is transactional and refuses to overwrite populated tables without `--truncate`. The honest caveat is that no live server was available in the build environment, so the SQL is statically reviewed rather than server-tested.

### Q10. What is the biggest weakness of the analysis?

**Answer:** Censored demand and single-location scope. Sales transactions record fulfilled units, so demand during stockouts is missing. ABC value and forecast accuracy are therefore biased downward during stockout periods. The model is also single-echelon and estimates lead-time variance at supplier level. Both are documented; neither is hidden.

### Q11. How would you monitor this after launch?

**Answer:** Track forecast bias and WAPE by segment on a rolling origin, monitor stockout probability calibration, watch supplier P90 and on-time rate, reconcile open PO promise dates, and alert on data freshness, null rates, and row-count deltas. Model monitoring should include distribution drift, not just accuracy.

### Q12. What did you learn from the stress scenario?

**Answer:** That average inventory and current inventory tell different stories. SKU-0004 had the highest annualized holding cost (**$4,196**) because it carried a large average buffer, but only 5 units remained at the analysis date. A static "average inventory" view would call it overstocked while it was actually the most urgent stockout. The dashboard shows both current stock and 52-week average.

---

## 8. Publishing checklist

### Repository

- [ ] `README.md` opens with the business problem and headline results, not installation instructions.
- [ ] `docs/dashboard_preview.png` is committed and renders on GitHub.
- [ ] `docs/methodology.md`, `docs/data_dictionary.md`, `docs/sample_findings.md`, and `docs/tableau_dashboard_spec.md` are linked.
- [ ] `LICENSE` is present and matches `pyproject.toml`.
- [ ] `.gitignore` excludes generated CSVs and outputs; the manifest and documentation remain tracked.
- [ ] `python -m pytest` passes from a clean environment.
- [ ] `python -m inventory_opt.pipeline --regenerate` completes and reports the expected KPIs.
- [ ] No secrets, local paths, or environment files are committed.

### GitHub presentation

- [ ] Repository description: "End-to-end supply-chain inventory optimization: PostgreSQL, ABC-XYZ, EOQ, safety stock, demand forecasting, Monte Carlo risk, Tableau."
- [ ] Topics: `supply-chain`, `inventory-management`, `demand-forecasting`, `postgresql`, `tableau`, `python`, `statsmodels`, `monte-carlo`.
- [ ] Pin the repository and add the dashboard preview as the social preview image.
- [ ] Add a short "What to look at first" section at the top of the README.
- [ ] Include one honest limitation in the README; it builds more trust than a perfect-sounding claim.

### Portfolio site / LinkedIn

- [ ] Lead with the decision, not the tool: "Which SKUs need action this week, and why?"
- [ ] Use no more than three numbers in the post: **5** high/critical SKUs, **$30.8k** exposure, **26.5%** WAPE.
- [ ] Link to the repository and the dashboard image.
- [ ] State that the data is synthetic.
- [ ] Mention one thing you would change in production.

### Demo hygiene

- [ ] Regenerate before recording so screenshots and numbers match.
- [ ] Close unrelated browser tabs and notifications.
- [ ] Use a clean 1440×900 viewport; do not crop the footer.
- [ ] Rehearse the five-minute script once without notes.
- [ ] Have the methodology open for formula questions.
- [ ] Do not claim a live PostgreSQL or Tableau deployment that was not performed.

---

## 9. Blog / LinkedIn post outline

**Title:** *From 60 SKUs to a Weekly Reorder Queue: Building an Inventory Optimization Pipeline*

1. **The problem:** cash, service, and supplier variability.
2. **The data model:** five tables, snapshot grain, PO lead-time history.
3. **The segmentation:** ABC by value, XYZ by calendar-complete CV.
4. **The policy:** EOQ as a baseline; safety stock with variable demand and lead time.
5. **The forecast:** per-SKU ETS, AIC selection, leakage-controlled holdout.
6. **The risk:** Monte Carlo over lead time, not a single point forecast.
7. **The decision:** a ranked exception queue with suggested quantities.
8. **The honest part:** censored demand, intermittent SKUs, single-location scope.
9. **What's next:** unconstrained demand, supplier-lane data, rolling-origin validation, write-back controls.

Keep code snippets short. Show the formula for safety stock and one small table of results. Link to the repository for the rest.

---

## 10. Production roadmap

### Phase 1 — Data foundation (weeks 1–4)

- Capture unconstrained demand and stockout/lost-sale events.
- Move from supplier-level to supplier × origin × mode × SKU lead-time grain where material.
- Add PO promise reliability and receipt-event history.
- Define freshness, completeness, and referential-integrity SLAs.
- Stand up the PostgreSQL schema with migrations, not ad-hoc DDL.

### Phase 2 — Planning model (weeks 5–8)

- Replace the single holdout with rolling-origin backtesting.
- Add Croston/TSB or intermittent-demand models for Z items.
- Reconcile SKU forecasts to category and supplier totals.
- Add promotion, price, weather, and macro drivers where justified.
- Calibrate the risk model against observed stockouts; measure reliability, not just discrimination.

### Phase 3 — Operations (weeks 9–12)

- Put the reorder queue into a daily planner workflow with owners and due dates.
- Add approval, budget, MOQ, pack-size, shelf-life, and supplier-capacity checks.
- Integrate supplier collaboration for P90 commitments and expedite playbooks.
- Define service-level matrix by ABC-XYZ and customer/channel criticality.
- Add audit logs for overrides and order recommendations.

### Phase 4 — Monitoring and scale (quarter 2+)

- Monitor forecast bias/WAPE, risk calibration, supplier P90, and data freshness.
- Add drift detection and alerting before a dashboard misleads.
- Extend to multi-echelon allocation and transshipment if the business requires it.
- Add scenario planning for supply disruptions and demand shocks.
- Formalize model ownership, review cadence, and change control.

---

## 11. What not to claim

- Do not say the data is real or belongs to a company.
- Do not say the Tableau workbook is shipped; it is specified, and the CSVs are the build contract.
- Do not say PostgreSQL was live-tested; no server was available in the build environment.
- Do not present the 26.5% WAPE as a universal accuracy claim; it is a 3-month holdout on this synthetic dataset.
- Do not present 100% stockout probability as a forecast of certainty; it is conditional on current supply and the stress scenario.
- Do not present suggested order quantities as approved purchase orders.
- Do not sum `supplier_total_lead_time_exposure_value` at SKU grain; use the supplier table or the SKU-level exposure column.
- Do not call the service level a fill rate.

---

## 12. File map for a reviewer

| Reviewer question | Open this |
|---|---|
| What does the project do? | `README.md` |
| How is the data modeled? | `docs/data_dictionary.md`, `sql/01_schema.sql` |
| How are the formulas derived? | `docs/methodology.md` |
| What did the seeded run find? | `docs/sample_findings.md`, `outputs/executive_summary.md` |
| What does the dashboard look like? | `docs/dashboard_preview.png`, `docs/tableau_dashboard_spec.md` |
| What is the action queue? | `outputs/tableau/reorder_alerts.csv` |
| How is quality controlled? | `tests/`, `sql/03_quality_checks.sql`, `outputs/data_quality_report.json` |
| How do I reproduce it? | `README.md` Quickstart, `python -m inventory_opt.pipeline --regenerate` |
| What are the limitations? | `docs/methodology.md` §11, `docs/sample_findings.md` §8–9 |

---

## 13. Final reminder

The project is strongest when you present it as a **decision system with explicit assumptions**, not as a model showcase. Lead with the exception queue, explain the chain that produced it, and be the first person to name its limitations. That is what senior analytics work sounds like.
