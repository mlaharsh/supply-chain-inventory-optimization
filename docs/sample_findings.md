# Sample Findings — Seed 42

**Analysis date:** 2026-09-30  
**Scope:** 60 active SKUs, 12 suppliers, 24 months of synthetic operating history  
**Data:** deterministic synthetic dataset; not a real company

This is the business narrative that accompanies the generated outputs. Every number is reproducible with:

```bash
python -m inventory_opt.pipeline --regenerate
```

The dataset deliberately includes an end-of-horizon replenishment freeze on eight high-velocity SKUs. That creates realistic reorder and stockout exceptions; it is a synthetic stress scenario, not a claim about real supply-chain behavior.

---

## 1. Executive readout

1. **Value is concentrated but inventory is less concentrated than sales.** 19 A SKUs generate **81.2%** of annual consumption value, yet carry **62.6%** of current inventory value and **70.5%** of annualized holding cost. The A class is where service failures are most expensive, but also where most working capital sits.
2. **The portfolio has a small, high-severity exception set.** 5 SKUs are High/Critical stockout risk, 3 are already stocked out, and 2 more are below their dynamic ROP. Projected lost-revenue exposure is **$30,834**, concentrated in one AX SKU (**$26,463**).
3. **Holding cost is a long-tail problem.** Annualized holding cost is **$49,231** on a 52-week average inventory of **$203,954**. The top 10 SKUs account for **49.3%** of holding cost; the top 20 account for **72.2%**.
4. **Supplier lead-time variability is not fully captured by average variance.** The weighted average variance is **−0.66 days** because many POs arrive early, yet one supplier is on time only **66.7%** of the time with a **6.1-day** lead-time standard deviation. Averages hide the late tail that drives safety stock.
5. **Forecast quality is acceptable for steady demand and weak for intermittent/seasonal demand.** Weighted holdout WAPE is **26.5%**, but it ranges from **11.2%** for steady SKUs to **49.5%** for intermittent SKUs. The risk model, not the point forecast alone, should drive exceptions.

---

## 2. Portfolio structure: ABC-XYZ

### 2.1 ABC value concentration

| Class | SKUs | Annual consumption value | Share of ACV | Current inventory value | Share of inventory | Annualized holding cost | Share of holding cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 19 | $1,314,477 | 81.2% | $111,457 | 62.6% | $34,694 | 70.5% |
| B | 19 | $227,191 | 14.0% | $47,350 | 26.6% | $10,478 | 21.3% |
| C | 22 | $76,319 | 4.7% | $19,241 | 10.8% | $4,059 | 8.2% |

The A class is a genuine Pareto group: 31.7% of SKUs produce 81.2% of value. The boundary SKU completes the 80% threshold rather than being pushed into B, so A may slightly exceed 80%.

### 2.2 ABC-XYZ matrix

| ABC \ XYZ | X | Y | Z | Total SKUs |
|---|---:|---:|---:|---:|
| **A** | 9 | 7 | 3 | 19 |
| **B** | 12 | 5 | 2 | 19 |
| **C** | 5 | 6 | 11 | 22 |
| **Total** | 26 | 18 | 16 | 60 |

**Reading the matrix**

- **AX (9 SKUs, 60.1% of ACV):** high value and relatively predictable. These should be protected with tight ROP discipline, supplier collaboration, and automated replenishment.
- **AZ (3 SKUs, 4.2% of ACV):** high value but erratic. These deserve forecast overrides, buffer review, and possibly dual sourcing. They are small in count but can create outsized service failures.
- **CZ (11 SKUs, 2.0% of ACV):** low value and erratic. Candidates for make-to-order, substitution, or non-stock treatment. Do not spend planner attention here proportional to SKU count.
- **CX (5 SKUs):** low value and stable. Simplify with min/max or vendor-managed inventory.

### 2.3 Demand archetypes

| Pattern | SKUs | Weighted holdout WAPE | Interpretation |
|---|---:|---:|---|
| Steady | 21 | 11.2% | Forecast is a reliable planning input |
| Seasonal | 18 | 39.0% | One annual cycle is not enough to estimate seasonality robustly; use judgment and supplier flexibility |
| Intermittent | 21 | 49.5% | Many zero months; point forecasts are weak, so probabilistic risk and service-level buffers matter more |

---

## 3. Working capital and holding cost

### 3.1 The cost base

| Metric | Value |
|---|---:|
| Current on-hand inventory value | $178,048 |
| 52-week average inventory value | $203,954 |
| Annualized holding cost at the 52-week average | $49,231 |
| Annual consumption value | $1,617,987 |
| Implied annual carrying rate | 24.1% of average inventory value |

The holding-cost rate is SKU-specific (18%–32%), so the portfolio total is not simply average inventory × one rate. Current inventory is lower than the 52-week average partly because the stress scenario has depleted several high-velocity SKUs at the horizon.

### 3.2 Concentration

| Rank | SKU | Segment | Current inventory value | 52-week average inventory value | Annualized holding cost | Annual consumption value |
|---:|---|---|---:|---:|---:|---:|
| 1 | SKU-0004 | AX | $585 | $22,166 | $4,196 | $348,392 |
| 2 | SKU-0008 | AX | $13,905 | $14,444 | $3,683 | $146,535 |
| 3 | SKU-0047 | AX | $8,030 | $11,160 | $3,215 | $140,439 |
| 4 | SKU-0012 | AX | $3,621 | $7,214 | $2,295 | $63,315 |
| 5 | SKU-0060 | AX | $3,091 | $7,490 | $2,173 | $79,335 |
| 6 | SKU-0003 | AX | $8,906 | $7,708 | $1,960 | $62,330 |
| 7 | SKU-0010 | AY | $4,323 | $7,563 | $1,854 | $63,404 |
| 8 | SKU-0016 | AX | $9,533 | $9,480 | $1,778 | $66,624 |
| 9 | SKU-0011 | AZ | $8,769 | $5,294 | $1,619 | $22,584 |
| 10 | SKU-0017 | AZ | $8,970 | $5,738 | $1,497 | $20,880 |

**The SKU-0004 paradox.** It has the highest annualized holding cost ($4,196) because it carried a large average buffer, but only 5 units remain at the analysis date. The replenishment freeze turned a former overstock into a stockout. This is exactly the kind of SKU that a static "average inventory" view would misclassify: it looks expensive on the year and critical today. The dashboard must show both current stock and 52-week average inventory.

### 3.3 Service-level trade-off

If every SKU were held at the same cycle service level, the safety-stock requirement would be:

| Service level | Safety-stock units | Safety-stock value at cost | Incremental value vs previous level |
|---:|---:|---:|---:|
| 90% | 933 | $33,362 | — |
| 95% | 1,198 | $42,819 | +$9,458 |
| 99% | 1,694 | $60,560 | +$17,741 |

Moving the whole portfolio from 95% to 99% would add roughly **$17.7k** of inventory and **$4.2k** of annual holding cost. That may be justified for A/critical SKUs but is rarely justified for CZ items. The current policy already differentiates by SKU: 17 SKUs target 90%, 27 target 95%, and 16 target 99%.

**Recommendation:** use a service-level matrix rather than a blanket target:

- AX/AY: 97.5%–99%, with supplier collaboration and expedite playbooks.
- AZ: 95%–97.5% plus scenario planning and dual sourcing where economically viable.
- B: 95%.
- CX/CY: 90%–95%, with min/max simplification.
- CZ: 90% or non-stock, with substitution rules.

---

## 4. Stockout risk and the reorder queue

### 4.1 Summary

| Status | SKUs |
|---|---:|
| Healthy | 39 |
| Inbound Pending | 15 |
| Watch | 1 |
| Reorder Now | 2 |
| Stocked Out | 3 |
| **Total** | **60** |

- **High/Critical risk:** 5 SKUs (4 Critical, 1 High).
- **Current inventory value at risk:** $8,615.
- **Projected lost-revenue exposure:** $30,834.
- **Open purchase orders:** 19, of which 1 is overdue.
- **Open inbound units:** 2,784.

### 4.2 Priority exceptions

| SKU | Segment | On hand | Position | Dynamic ROP | Stockout probability | Risk | Action | Suggested order | Lost-revenue exposure | Lead time (d) | Supplier |
|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---|
| SKU-0004 | AX | 5 | 5 | 223.5 | 100% | Critical | Reorder Now | 476 | $26,463 | 20.9 | Sierra Plastics |
| SKU-0044 | AY | 0 | 0 | 106.1 | 100% | Critical | Stocked Out | 413 | $3,763 | 23.8 | Summit Industrial |
| SKU-0042 | BX | 0 | 0 | 73.1 | 100% | Critical | Stocked Out | 804 | $448 | 9.3 | BlueLine Packaging |
| SKU-0040 | CX | 0 | 0 | 32.1 | 100% | Critical | Stocked Out | 411 | $160 | 11.4 | Northwind Components |
| SKU-0047 | AX | 235 | 558 | 627.6 | 41% | High | Reorder Now | 389 | $0 | 48.0 | Apex Optics |
| SKU-0023 | AY | 113 | 113 | 106.2 | 12% | Watch | Watch | 0 | $0 | 41.0 | Orion Metals |

**Interpretation**

- The four Critical SKUs are already at or near zero on hand. Their 100% probability is not a model error; it is the correct answer given no supply inside the lead-time window.
- SKU-0047 is the most interesting "High" case: it still has 235 units and 558 in position, but a 48-day lead time and 41% stockout probability. The ROP breach is real, but the action is to validate the inbound and consider expedite rather than panic-buy.
- SKU-0023 is a Watch item: 113 units, 12% risk, 41-day lead time. It does not need an order today; it needs monitoring and a supplier check.
- Suggested order quantities are decision support, not automatic POs. They respect MOQ but not cash, storage, or supplier capacity.

### 4.3 Why the stress scenario matters

Eight high-velocity SKUs stop placing orders during the final 35 days:

`SKU-0003`, `SKU-0004`, `SKU-0040`, `SKU-0042`, `SKU-0044`, `SKU-0047`, `SKU-0050`, `SKU-0060`.

Existing POs still arrive, but new replenishment stops. This produces a mix of stocked-out, reorder-now, high-risk, and inbound-pending states. Without it, the dashboard would be almost entirely green and would not demonstrate exception management. The scenario is recorded in `data/raw/generation_manifest.json`.

---

## 5. Supplier performance and lead-time exposure

### 5.1 Scorecard

| Supplier | Promised LT (d) | Actual LT (d) | LT std (d) | P90 LT (d) | On-time | Avg variance (d) | Exposure value | SKUs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sierra Plastics | 21 | 20.9 | 3.1 | 24.0 | 85% | −0.1 | $2,470 | 7 |
| Cascade Chemicals | 45 | 44.2 | 3.0 | 46.2 | 84% | −0.8 | $459 | 8 |
| BlueLine Packaging | 10 | 9.3 | 1.7 | 12.0 | 78% | −0.7 | $302 | 7 |
| Meridian Textiles | 14 | 13.6 | 2.8 | 15.4 | 87% | −0.4 | $275 | 5 |
| Apex Optics | 49 | 48.0 | 1.8 | 49.0 | 98% | −1.0 | $227 | 5 |
| Redwood Paper | 35 | 38.2 | 6.1 | 45.5 | 67% | +3.2 | $209 | 1 |
| Harbor Safety | 30 | 28.7 | 1.4 | 30.0 | 95% | −1.3 | $163 | 5 |
| Northwind Components | 12 | 11.4 | 2.4 | 12.6 | 88% | −0.6 | $163 | 4 |
| Summit Industrial | 25 | 23.8 | 2.8 | 24.9 | 92% | −1.2 | $98 | 2 |
| Vertex Electronics | 7 | 6.4 | 1.5 | 8.0 | 88% | −0.6 | $34 | 10 |
| Atlas Fasteners | 18 | 16.9 | 1.8 | 19.0 | 86% | −1.1 | $32 | 2 |
| Orion Metals | 42 | 41.0 | 1.1 | 42.0 | 100% | −1.0 | $18 | 4 |

### 5.2 What the averages hide

- **Sierra Plastics** has the highest exposure value ($2,470) because it supplies seven SKUs, including the highest-risk SKU-0004. Its average actual lead time is essentially on plan, but its P90 is 24 days and its on-time rate is 85%. The risk is in the tail, not the mean.
- **Redwood Paper** is the clearest variability problem: actual lead time averages 38.2 days against a 35-day promise, with a 6.1-day standard deviation and only 67% on-time. It carries one SKU and modest exposure ($209), so the financial urgency is lower than Sierra's, but the process signal is worse.
- **BlueLine Packaging** is fast (9.3 days) but only 78% on-time. Short lead times reduce exposure per unit, but a 22% late rate still matters for high-velocity SKUs.
- **Orion Metals** is 100% on time with 1.1-day standard deviation; it is a candidate for a lower safety-stock parameter or a longer review cycle.

### 5.3 Exposure formula and interpretation

For each SKU:

```text
SS_variable = Z × sqrt(actual_mean_LT × daily_std² + avg_daily² × actual_LT_std²)
SS_promised = Z × sqrt(promised_LT × daily_std²)
safety_stock_penalty = max(SS_variable - SS_promised, 0)
cycle_stock_penalty  = max((actual_mean_LT - promised_LT) × avg_daily, 0)
exposure_units       = safety_stock_penalty + cycle_stock_penalty
exposure_value       = exposure_units × unit_cost
```

Portfolio totals:

| Component | Units | Value |
|---|---:|---:|
| Safety-stock penalty from lead-time variability | 108.7 | — |
| Cycle-stock extension from longer actual lead time | 4.5 | — |
| **Total SKU-level exposure** | **113.2** | **$4,451** |

The SKU-level `lead_time_exposure_value` column sums to **$4,451** and reconciles to the exposure column in `supplier_performance.csv`. The `supplier_total_lead_time_exposure_value` column in `inventory_overview.csv` is a supplier attribute repeated on every SKU row; summing it at SKU grain produces **$27,938**, which is inflated. **Sum `lead_time_exposure_value` at SKU grain, or use `supplier_performance.csv` for supplier totals.**

**Recommendation:** do not select suppliers on average variance alone. Use a two-dimensional view:

- x-axis: on-time rate or lead-time CV;
- y-axis: exposure value or annual consumption value;
- size: SKU count;
- color: overdue inbound units.

This separates "high-spend but reliable" from "low-spend but chaotic" and prevents a cheap supplier from winning on price while destroying service.

---

## 6. Forecast quality

### 6.1 Headline

| Metric | Result |
|---|---:|
| Weighted holdout WAPE (3 months) | 26.5% |
| Median SKU WAPE | 31.4% |
| Weighted bias | +1.2% |
| SKUs evaluated | 60 |

### 6.2 By demand pattern

| Pattern | SKUs | Weighted WAPE | Weighted bias |
|---|---:|---:|---:|
| Steady | 21 | 11.2% | −0.0% |
| Seasonal | 18 | 39.0% | +8.1% |
| Intermittent | 21 | 49.5% | −9.5% |

The aggregate 26.5% is respectable for a 24-month synthetic history, but it masks a wide range. Steady SKUs are forecastable; intermittent SKUs are not, and pretending otherwise would produce false precision.

### 6.3 Model mix and holdout refit

Final model, fit on all 24 months and selected by AIC:

| Model | SKUs |
|---|---:|
| Simple exponential smoothing | 43 |
| Holt-Winters additive (damped) | 16 |
| Linear trend ETS | 1 |

All 16 Holt-Winters selections are seasonal SKUs. Two seasonal SKUs selected simple exponential smoothing and had very high holdout errors; that is a useful signal that 24 months is a thin history for annual seasonality. The holdout was **not** used to pick models, so the accuracy numbers are not leakage-optimistic.

**The holdout is a separate refit.** It is trained on the first 21 months, so AIC can select a different specification than the final 24-month model:

| Holdout refit model (21 months) | SKUs |
|---|---:|
| Simple exponential smoothing | 56 |
| Damped trend ETS | 3 |
| Linear trend ETS | 1 |

Of the 16 SKUs that use Holt-Winters in the final model, **14 selected simple exponential smoothing** and 2 selected damped trend on the holdout window. The seasonal WAPE therefore measures the selection-and-forecast procedure at 21 months, not the exact final Holt-Winters forecast. That instability is itself the finding: one annual cycle is not enough to make seasonality selection stable. `forecast_accuracy.csv` reports `final_model` and `holdout_model` side by side so the difference is auditable.

### 6.4 Worst holdout cases

| SKU | Pattern | Holdout model | Actual (3 mo) | Forecast (3 mo) | WAPE | Bias |
|---|---|---|---:|---:|---:|---:|
| SKU-0035 | Intermittent | Simple exponential smoothing | 7 | 31.1 | 344.9% | +344.9% |
| SKU-0038 | Intermittent | Simple exponential smoothing | 31 | 98.1 | 216.6% | +216.6% |
| SKU-0036 | Intermittent | Simple exponential smoothing | 14 | 19.6 | 146.6% | +39.8% |
| SKU-0048 | Seasonal | Simple exponential smoothing | 59 | 134.3 | 127.6% | +127.6% |
| SKU-0039 | Seasonal | Simple exponential smoothing | 94 | 204.2 | 117.3% | +117.3% |
| SKU-0015 | Intermittent | Simple exponential smoothing | 179 | 42.9 | 76.1% | −76.1% |

These are not reasons to discard the model. They are reasons to:

- show SKU-level WAPE in the dashboard so planners know where to trust the forecast;
- use the Monte Carlo risk layer for intermittent items rather than a point forecast;
- add Croston/TSB, rolling-origin validation, and manual overrides in production;
- capture unconstrained demand and stockout events to reduce censoring bias.

---

## 7. Recommended actions

### 7.1 Next 0–30 days

1. **Place or expedite replenishment for the four Critical SKUs.** SKU-0004 alone accounts for $26.5k of projected lost revenue. Validate the suggested quantities against MOQ, cash, and storage.
2. **Protect SKU-0047.** It is not stocked out, but a 48-day lead time and 41% risk make it the most likely next failure. Confirm the open PO promise date and consider a partial expedite.
3. **Review Sierra Plastics and BlueLine Packaging.** Both have on-time rates below 86%; Sierra carries the largest exposure. Ask for a recovery plan and P90 commitment, not just an average.
4. **Freeze the reorder queue as a daily stand-up artifact.** The `reorder_alerts.csv` extract is small enough to review in a 15-minute meeting.

### 7.2 Next 30–60 days

1. **Implement the service-level matrix.** Stop treating 95% as a universal target. Move AX/AY toward 97.5%–99%, keep B at 95%, and simplify CZ.
2. **Recalculate ROP weekly, not quarterly.** The dynamic ROP already uses the latest forecast; the operating cadence should match the weekly snapshot.
3. **Add a supplier scorecard review.** Use on-time rate, P90 lead time, standard deviation, and exposure value together. A supplier with a low average variance but a fat late tail is still risky.
4. **Set forecast override rules.** Planner override required for AZ and any SKU with WAPE above 50% or a forecast change greater than 30% week over week.

### 7.3 Next 60–90 days

1. **Pilot dual sourcing or a buffer for AZ SKUs.** The three AZ SKUs are only 4.2% of ACV but carry high service risk.
2. **Reduce excess buffer where current stock and 52-week average are both high and risk is Low.** Reclaim working capital without touching the critical exception set.
3. **Move from monthly to weekly forecasting for A SKUs.** Monthly is adequate for C items; A items need a shorter review cycle.
4. **Add hierarchical reconciliation.** SKU forecasts should reconcile to category and supplier totals before purchase planning.

---

## 8. What would change in production

The synthetic project demonstrates the analytical chain. A production deployment would need:

- **Unconstrained demand and stockout events.** Current history records fulfilled sales only, so demand is censored during stockouts.
- **Supplier-lane grain.** Lead-time mean/variance should be estimated by supplier × origin × mode × SKU where material.
- **Open PO promise reliability.** A promised date is not a receipt probability; model supplier promise accuracy and carrier transit separately.
- **Rolling-origin validation.** A single 3-month holdout is a portfolio demonstration, not a model-monitoring regime.
- **Promotions, price, weather, and macro drivers.** These are absent from the synthetic generator and would improve forecast accuracy.
- **Multi-echelon inventory.** The current model is single-location; DC/store allocation and transshipment are out of scope.
- **Write-back controls.** Suggested orders must pass approval, budget, and supplier-capacity checks before becoming POs.
- **Data contracts and monitoring.** Freshness, row-count deltas, null rates, and distribution drift should alert before a dashboard misleads.

---

## 9. Caveats

- All data is synthetic and generated for portfolio demonstration. Do not present these results as a real company's performance.
- The stress scenario is deliberate. The 100% stockout probabilities at the horizon are a consequence of the replenishment freeze, not a forecasting failure.
- Lost sales are not recorded as negative demand. ABC value and forecast accuracy are therefore biased downward during stockouts.
- Holding cost uses a 52-week average inventory value, not the ending snapshot. This is the correct run-rate view but can differ materially from current inventory value.
- Supplier exposure is diagnostic and excludes price, quality, capacity, and freight terms.
- Service level is a cycle service level, not a fill rate or OTIF.
- Tableau workbook is specified, not shipped; the CSVs are the contract.

For formulas and assumptions, see [`methodology.md`](methodology.md). For field definitions, see [`data_dictionary.md`](data_dictionary.md). For the dashboard build, see [`tableau_dashboard_spec.md`](tableau_dashboard_spec.md).
