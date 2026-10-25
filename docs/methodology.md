# Methodology, Formulas, and Assumptions

This document is the technical reference for the Supply Chain Inventory Optimization & Reorder Forecasting project. It explains how the synthetic dataset is constructed, every calculation used in the analysis, and the conditions under which each calculation should not be trusted.

The project is intentionally explicit about assumptions: an EOQ or ROP that is mathematically correct can still be operationally wrong.

---

## 1. Scope and horizon

| Item | Value |
|---|---|
| History | 2024-10-01 to 2026-09-30 (730 days) |
| Analysis date | 2026-09-30 |
| SKUs | 60 active |
| Suppliers | 12 |
| Forecast horizon | 3 months (Oct–Dec 2026) |
| Holdout | Last 3 months of history |
| Service levels | 90%, 95%, 99% |
| Stockout simulation | 20,000 paths per SKU |
| Reorder review | Every weekday during simulation |

The horizon is fixed so that screenshots, tests, and portfolio metrics are reproducible.

---

## 2. Synthetic data generation

### 2.1 Demand archetypes

Three demand processes are generated to prevent the analysis from only working on well-behaved fast movers.

**Steady demand**

\[
\mu_t = B \times w_t \times s_t \times g_t
\]

where \(B\) is a SKU base rate, \(w_t\) is a weekday factor, \(s_t\) is a mild seasonal factor, and \(g_t\) is a slow trend. Demand is drawn from a negative binomial:

\[
D_t \sim \text{NB}(\mu_t, \phi), \qquad
\mathbb{E}[D_t]=\mu_t, \qquad
\operatorname{Var}(D_t)=\mu_t+\frac{\mu_t^2}{\phi}
\]

This introduces realistic overdispersion rather than pure Poisson noise.

**Seasonal demand**

\[
s_t = 1 + A\cos\left(\frac{2\pi(\text{day of year}_t-P)}{365.25}\right)
\]

with amplitude \(A\) and a random annual peak day \(P\). This creates annual inventory builds and markdown/stockout pressure depending on whether procurement responds in time.

**Intermittent demand**

\[
D_t =
\begin{cases}
\text{NB}(\mu_{\text{event}}, \phi_{\text{event}}), & \text{with probability } p_t\\
0, & \text{otherwise}
\end{cases}
\]

Zero days are retained in the analytical calendar. This is the single most important design choice for an honest XYZ classification.

The seed-42 dataset contains 21 steady, 18 seasonal, and 21 intermittent SKUs. Promotions, weekend effects, and random demand spikes add additional noise.

### 2.2 Supplier lead times

Each supplier has:

- a quoted lead time \(L_{\text{promised}}\);
- a planning standard deviation \(\sigma_L\);
- an on-time target.

When a PO is placed, the generator samples an actual lead time. With probability equal to the supplier's on-time target, the shipment arrives on time or a few days early. Otherwise it draws a late delay from a gamma tail scaled by the supplier's variability. Carrier weekends are handled by moving receipt to the next business day.

This produces observed actual-vs-promised variance and a right-skewed late tail, which is more realistic than a symmetric normal lead-time assumption at the individual-PO level.

### 2.3 Inventory simulation

For each SKU, the simulator operates a daily-review reorder policy:

1. Receive any POs due that day.
2. Fulfil demand up to available on-hand stock.
3. Record lost sales if demand exceeds stock.
4. Review inventory position = on hand + open inbound.
5. If position ≤ ROP and it is a weekday, place an order.
6. Sample the actual supplier lead time and schedule receipt.
7. Record a weekly on-hand/inbound snapshot and a final horizon snapshot.

The simulator uses the specified EOQ and safety-stock formulas with practical order-size guardrails. It is not intended to be a perfect replica of an ERP; it creates an internally consistent world for analytics.

### 2.4 Deliberate end-of-horizon stress scenario

Eight high-velocity SKUs stop placing new orders for the final 35 days. Existing POs still arrive, but expected replenishment stops. This creates a mix of:

- genuine stockouts at the analysis date;
- open POs and inbound pending;
- high stockout probability even where some stock remains.

The scenario is disclosed in `data/raw/generation_manifest.json` (`understocked_skus`, `end_order_freeze_days`). Without it, the dashboard would be almost entirely green and would not demonstrate exception management. This is a synthetic data design choice, not a claim that all real supply chains behave this way.

### 2.5 Dataset accounting

Seed 42:

- planned demand ≈ 91,105 units;
- fulfilled units = 90,148;
- lost sales = 957 units (≈1.05%);
- 28,470 sale lines;
- 446 purchase orders;
- 6,300 weekly SKU snapshots (105 weeks × 60 SKUs).

Lost sales are **not** represented as negative sales. Consequently, observed history is censored demand. See limitations.

---

## 3. ABC-XYZ classification

### 3.1 Annual consumption value

Using the trailing 365 days and standard cost, not selling price:

\[
ACV_i = \left(\sum_{t=\text{last 365d}} q_{i,t}\right)c_i
\]

At cost is the correct measure for an inventory policy because it represents working capital, not revenue.

### 3.2 ABC cumulative-value rule

Sort SKUs by descending \(ACV\). Let \(S_i\) be cumulative share through SKU \(i\), and \(S_i^{-}\) be cumulative share **before** SKU \(i\):

\[
\text{ABC}_i =
\begin{cases}
A, & S_i^{-} < 0.80\\
B, & 0.80 \le S_i^{-} < 0.95\\
C, & S_i^{-} \ge 0.95
\end{cases}
\]

This ensures the A class carries at least 80% of annual value, even if the boundary SKU crosses the threshold. It is a value-based Pareto rule, not a fixed 20% SKU count.

### 3.3 XYZ volatility rule

For each SKU, aggregate calendar-complete daily demand to Monday-start weeks. Over the latest 52 complete weeks:

\[
CV_i = \frac{\sigma_{i,\text{weekly}}}{\mu_{i,\text{weekly}}}
\]

\[
XYZ_i =
\begin{cases}
X, & CV \le 0.50\\
Y, & 0.50 < CV \le 1.00\\
Z, & CV > 1.00
\end{cases}
\]

A zero-mean SKU is Z (non-operational), not X. The 52-week window excludes the partial horizon-end week.

Why include zeros? An item that sells 50 units in 20% of weeks has high effective uncertainty. Computing CV only on selling weeks would label it stable and understate safety stock.

### 3.4 Interpretation

- **AX/AY**: high value, relatively predictable → automate and protect.
- **AZ**: high value, volatile → forecast and supplier collaboration priority.
- **CX/CY**: low value, stable → simplify, min/max or vendor-managed inventory.
- **CZ**: low value, erratic → consider make-to-order, substitution, or non-stock.

### 3.5 Seed-42 result

- A/B/C: 19 / 19 / 22 SKUs
- Value share: 81.2% / 14.0% / 4.7%
- X/Y/Z: 26 / 18 / 16 SKUs

The high A value share confirms the Pareto shape.

---

## 4. EOQ

### 4.1 Formula

With annual demand \(D\), fixed order cost \(S\), unit cost \(c\), and annual holding rate \(h\):

\[
H = c h
\]

\[
EOQ = \sqrt{\frac{2DS}{H}}
\]

### 4.2 Derivation

The classic annual relevant cost is:

\[
TC(Q) = \frac{D}{Q}S + \frac{Q}{2}H
\]

Set the first derivative to zero:

\[
\frac{dTC}{dQ} = -\frac{DS}{Q^2} + \frac{H}{2} = 0
\]

\[
Q^* = \sqrt{\frac{2DS}{H}}
\]

The second derivative \(2DS/Q^3>0\) confirms a minimum.

### 4.3 Assumptions and operational caveats

The formula assumes:

- constant, known annual demand;
- fixed cost per order;
- holding cost proportional to average cycle stock;
- no quantity discounts;
- no stockout cost in the model;
- deterministic replenishment;
- unlimited supplier capacity and storage.

These are restrictive. In operations, an EOQ should be blended with:

- minimum order quantity and pack-size rounding;
- truckload/freight breaks and quantity discounts;
- shelf life, storage capacity, and cash constraints;
- supplier capacity and allocation;
- forecast uncertainty, handled by safety stock and ROP, not EOQ itself.

The pipeline preserves `eoq_units` for audit and exposes `recommended_order_qty` after MOQ enforcement. The data simulator caps its practical order quantity to roughly 120 days of demand. That cap is a synthetic-operations choice, not part of the EOQ formula.

---

## 5. Safety stock and reorder point

### 5.1 Lead-time demand variance

Let daily demand \(D_t\) be independent with mean \(\bar D\) and variance \(\sigma_D^2\). Let lead time \(L\) be a non-negative random variable, independent of demand, with mean \(\bar L\) and variance \(\sigma_L^2\). Then:

\[
D_L = \sum_{t=1}^{L}D_t
\]

By the law of total variance:

\[
\operatorname{Var}(D_L)
= \mathbb{E}[L]\operatorname{Var}(D)
 + \operatorname{Var}(L)(\mathbb{E}[D])^2
= \bar L\sigma_D^2 + \bar D^2\sigma_L^2
\]

The two terms have different operational meanings:

- \(\bar L\sigma_D^2\): demand noise over the expected lead time.
- \(\bar D^2\sigma_L^2\): uncertainty caused by not knowing when the shipment arrives.

### 5.2 Safety stock

\[
SS = Z \times \sqrt{\bar L\sigma_D^2+\bar D^2\sigma_L^2}
\]

\[
ROP = \bar D\bar L + SS
\]

\(Z=\Phi^{-1}(\text{service level})\):

| Service level | \(Z\) |
|---:|---:|
| 90% | 1.2816 |
| 95% | 1.6449 |
| 99% | 2.3263 |

The outputs contain safety stock and ROP for all three service levels:

- `safety_stock_90_units`, `rop_90_units`
- `safety_stock_95_units`, `rop_95_units`
- `safety_stock_99_units`, `rop_99_units`

The SKU's target service level chooses the static target columns; the forecast-driven decision layer computes dynamic variants.

### 5.3 What does "95% service level" mean?

It is a **cycle service level**: the probability that demand during a replenishment cycle does not exceed inventory. It is not:

- an order fill rate;
- a unit fill rate;
- OTIF;
- the probability that no item in the portfolio stocks out.

One SKU at 95% cycle service still has a 5% chance of stockout per cycle. With many SKUs and many cycles, portfolio-level stockouts are common. A production policy should distinguish critical-item fill rates, customer penalties, and substitution.

### 5.4 Forecast-driven dynamic ROP

For the reorder engine, \(\bar D\) is replaced by the forecast daily rate over the SKU's lead-time horizon:

\[
SS_{\text{dynamic}}=Z\sqrt{\bar L\sigma_D^2+
\bar D_{\text{forecast}}^2\sigma_L^2}
\]

\[
ROP_{\text{dynamic}}=
\bar D_{\text{forecast}}\bar L+SS_{\text{dynamic}}
\]

Historical demand variance stays in the variance term because the forecast mean is more stable than a single future day. This is a pragmatic forecast-plus-safety-stock policy, not a full stochastic dynamic program.

### 5.5 Assumptions and limitations

- Demand and lead time are independent.
- Daily demand is independent and approximately normal.
- Lead time is stationary over the planning window.
- Service level is constant over the SKU's lifecycle.
- There is one supply source and no correlated disruptions.
- No capacity constraint or order minimum in the statistical formula.
- Intermittent demand violates normality; the Monte Carlo risk model is the operational check.

The generated supplier mean/variance uses received history at supplier level. That is appropriate when product lead times share a supplier process. If supplier lanes differ by SKU or port, estimate at a lower grain.

---

## 6. Demand forecasting

### 6.1 Preparation

- Aggregate fulfilled sales to calendar-complete months.
- Include zero-sale months as zero.
- Keep the SKU product as the forecasting unit.
- Hold out the last three months for evaluation.
- Fit future forecasts on all available history.

### 6.2 Model candidates

`statsmodels.tsa.holtwinters.ExponentialSmoothing` with additive errors. Candidates depend on the demand archetype:

| Pattern | Candidate models |
|---|---|
| Seasonal | Holt-Winters additive seasonal + damped trend; damped trend ETS; simple exponential smoothing |
| Steady | Damped trend ETS; linear trend ETS; simple exponential smoothing |
| Intermittent | Simple exponential smoothing; damped trend ETS |

AIC selects the candidate with the lowest score, with a naïve 12-month average fallback if optimization fails or the series is too short/all zero.

Why not SARIMA? Exponential smoothing is easier to explain, fast to refit across 60 SKUs, and naturally handles the short 24-month history. A production comparison should evaluate SARIMA, Croston/TSB for intermittent items, and hierarchical reconciliation.

### 6.3 Forecast accuracy

Weighted absolute percentage error on the holdout:

\[
WAPE = \frac{\sum_i\sum_h |F_{i,h}-A_{i,h}|}
{\sum_i\sum_h A_{i,h}}
\]

WAPE is used instead of MAPE because intermittent SKUs have zero actuals in the denominator; weighted aggregation prevents tiny-volume SKUs from dominating.

Seed-42 result:

| Metric | Result |
|---|---:|
| Weighted WAPE | 26.5% |
| Median SKU WAPE | 31.4% |
| Weighted bias | +1.2% |
| SKUs evaluated | 60 |

WAPE above 30% for some intermittent SKUs is expected, not a modeling failure. The dashboard exposes SKU-level WAPE so planners know where forecast trust is low. Demand smoothing, stockout censoring, and 24 months of history also limit accuracy.

The holdout is a separate refit on the first 21 months. Its AIC-selected specification can differ from the final 24-month model: on seed 42, 14 of the 16 final Holt-Winters SKUs selected simple exponential smoothing on the holdout window. The seasonal WAPE therefore measures the selection-and-forecast procedure at 21 months, not the exact final specification. `forecast_accuracy.csv` reports `final_model` and `holdout_model` separately.

### 6.4 Forecast intervals

The 95% interval is approximated as:

\[
\hat D_{t+h} \pm 1.96\,\hat\sigma_{\text{resid}}\sqrt{h}
\]

where \(\hat\sigma_{\text{resid}}\) is the in-sample residual RMSE. This is a simple random-walk-like scaling. It does not fully capture parameter uncertainty, seasonality, or regime changes. A production system should use simulation intervals or rolling-origin conformal intervals.

### 6.5 Backtest leakage control

- Candidate selection for the holdout uses only the training period.
- The last three months are never used to select the holdout model.
- Future forecasts are fit on the full series after evaluation, with AIC re-evaluated on that full series.
- The final and holdout model labels can therefore differ; both are exposed in `forecast_accuracy.csv`.
- Accuracy is reported, not used to overwrite future predictions.

---

## 7. Stockout probability over lead time

### 7.1 Available inventory

For a lead-time horizon \(L\):

\[
A = \text{on hand}
 + \sum_{\text{open POs with promised date} \le t+L}
\text{open units}
\]

Only inbound promised within the horizon is counted as available. Counting all future inbound would understate risk. All open inbound still contributes to the reorder **position**, because it is committed supply.

### 7.2 Monte Carlo process

For each of 20,000 paths:

1. Sample lead time from a gamma distribution with supplier mean \(\bar L\) and standard deviation \(\sigma_L\).
2. Sample a daily demand rate from a normal distribution centered on the forecast rate, with forecast-rate uncertainty.
3. Draw lead-time demand from a negative binomial calibrated to historical daily variance:

\[
\mathbb{E}[D_L] = \lambda L
\]

\[
\operatorname{Var}(D_L) = L\sigma_D^2
\]

If variance ≤ mean, use a Poisson fallback. This preserves burstiness and zeros better than a normal distribution for intermittent SKUs.

4. Record whether \(D_L>A\).

\[
\hat P(\text{stockout}) =
\frac{1}{N}\sum_{j=1}^{N}\mathbf{1}\{D_{L_j}^{(j)}>A\}
\]

The 95th percentile of simulated lead-time demand is retained as an operational stress number.

### 7.3 Analytic benchmark

The normal approximation:

\[
P(D_L>A)=1-\Phi\left(
\frac{A-\bar D\bar L}
{\sqrt{\bar L\sigma_D^2+
\bar D^2\sigma_L^2+
(\bar L\sigma_{\text{rate}})^2}}
\right)
\]

is also stored. Divergence between the analytic and simulated probabilities is a useful diagnostic: large gaps usually mean intermittent demand or a highly skewed lead-time distribution.

### 7.4 Risk tiers

| Tier | Probability | Operational response |
|---|---|---|
| Critical | ≥ 50% | Expedite or reorder immediately; validate supply |
| High | 25–50% | Review order quantity, inbound timing, service level |
| Watch | 10–25% | Monitor; check forecast and supplier |
| Low | < 10% | No exception action |

The main `stockout_risk_flag` is High/Critical. `watchlist_flag` includes Watch.

### 7.5 Limitations

- Lead-time samples assume a stationary gamma distribution.
- Demand rate uncertainty is modeled as a horizon-wide shift, not day-by-day correlation.
- Inbound delays are represented by promised dates, not a carrier/port process.
- Lost-sales censoring biases the historical demand distribution downward.
- A stockout probability is not a financial loss estimate; the dashboard pairs it with current inventory value and projected lost revenue.

---

## 8. Supplier lead-time performance and safety-stock impact

### 8.1 Observed metrics

For received POs:

\[
\text{actual lead time} = \text{received date} - \text{order date}
\]

\[
\text{promised lead time} = \text{promised date} - \text{order date}
\]

\[
\text{variance} = \text{actual} - \text{promised}
\]

\[
\text{on-time} = \mathbf{1}\{\text{received date}\le\text{promised date}\}
\]

Supplier scorecards aggregate mean actual, mean promised, mean variance, standard deviation, P90 actual lead time, on-time rate, average days late, open/overdue PO count, and overdue units.

### 8.2 Safety-stock penalty

For the SKU's target service level \(Z\), compare:

\[
SS_{\text{variable}} = Z\sqrt{
\bar L_{\text{actual}}\sigma_D^2+
\bar D^2\sigma_{L,\text{actual}}^2
}
\]

against a constant-promised-lead-time baseline:

\[
SS_{\text{promised}} = Z\sqrt{
L_{\text{promised}}\sigma_D^2
}
\]

The incremental units:

\[
\Delta SS = \max(SS_{\text{variable}}-SS_{\text{promised}},0)
\]

are converted to dollars at standard cost. This captures the inventory consequence of both longer average lead time and variable lead time. The pipeline also reports cycle-stock extension from mean lead-time differences.

This calculation is diagnostic. It does not prove causality or include supplier price differences; a lower-cost supplier may still be economically better despite higher safety stock. The dashboard shows both exposure and annual consumption so the user can weigh trade-offs.

### 8.3 Seed-42 monitoring signals

- Weighted on-time rate: 88.3%
- Weighted average variance: −0.66 days (many early arrivals offset late tails)
- 19 open POs, one overdue at the analysis date
- Safety-stock exposure varies by supplier and is concentrated in longer-lead suppliers

A negative average variance does not mean the supplier is low risk. The late tail, P90 lead time, and variance still drive safety stock and stockout risk.

---

## 9. Decision engine logic

The dynamic ROP is required against inventory position. Stockout probability is evaluated against available inventory inside the lead-time window.

Status precedence:

1. **Stocked Out** — current stock is zero and demand risk exists.
2. **Reorder Now** — inventory position ≤ dynamic ROP.
3. **Expedite** — high risk despite an inbound position above ROP.
4. **At Risk** — high risk with no immediate ROP breach.
5. **Inbound Pending** — on hand below ROP but committed inbound covers the position.
6. **Watch** — moderate uncertainty.
7. **Healthy** — no exception.

`Suggested order units` tops the inventory position up to dynamic ROP plus a recommended cycle quantity, subject to MOQ. It is not an automated purchase order.

---

## 10. Data quality controls

### Application-level

- No duplicate SKU.
- Positive sales quantities.
- Referential integrity across sales, POs, suppliers, and inventory.
- No receipt before order.
- No negative inventory.
- Forecast horizon beyond analysis date.
- Probabilities in [0,1].
- Finiteness and stock-position consistency.
- Current stock equals latest snapshot.

### SQL-level

`sql/03_quality_checks.sql` covers:

- duplicate SKUs;
- orphan sales and POs;
- supplier mismatch (advisory for supplier-change history);
- invalid PO dates/quantities;
- missing latest inventory;
- snapshot count gaps;
- calendar completeness;
- open overdue POs.

The SQL files were syntax-parsed with a PostgreSQL parser during the build, but no live PostgreSQL server was available, so execution semantics and performance remain unverified. Run the views and quality checks against a local instance before production use.

### Production additions

- dbt tests or Great Expectations for freshness, uniqueness, not-null, accepted values, and row-count deltas.
- Contract tests between generation, database load, forecast output, and Tableau extract.
- Distribution drift checks on demand and lead times.
- Forecast monitoring against realized demand.
- Alert if >X% of SKUs have no current forecast.

---

## 11. Why this is a portfolio project, not a production planning system

It demonstrates the full analytical chain and the judgment required to use it responsibly. A production deployment would need:

- Actual ERP/WMS/TMS data with supplier-lane grain.
- Unconstrained demand and explicit stockout events.
- Order, receipt, and allocation status at line level.
- Hierarchy and lifecycle handling (new/discontinued SKUs).
- Promotions, pricing, weather, and macro drivers.
- Rolling-origin validation, model monitoring, and manual overrides.
- Supplier capacity, MOQ, freight, and cash constraints.
- Multi-echelon (DC/store) inventory and service-level optimization.
- Role-based access, audit trails, and write-back controls.

The current implementation is deliberately transparent so the assumptions and trade-offs can be interrogated by an interviewer or business partner.
