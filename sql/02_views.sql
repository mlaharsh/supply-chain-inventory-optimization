-- =============================================================================
-- Reusable SQL views for validation, BI, and a live Tableau connection.
-- Run after 01_schema.sql:
--   psql "$DATABASE_URL" -f sql/01_schema.sql
--   psql "$DATABASE_URL" -f sql/02_views.sql
-- =============================================================================

SET search_path TO supply_chain, public;

-- 1. Calendar-complete daily demand. Zero-sale days are retained because they
--    are required for unbiased CV, safety-stock, and intermittent-demand maths.
CREATE OR REPLACE VIEW v_daily_demand AS
WITH bounds AS (
    SELECT MIN(sale_date) AS min_date,
           MAX(sale_date) AS max_date
    FROM sales_transactions
),
calendar AS (
    SELECT generate_series(min_date, max_date, interval '1 day')::date AS demand_date
    FROM bounds
),
product_calendar AS (
    SELECT p.product_id, p.sku, c.demand_date
    FROM products p
    CROSS JOIN calendar c
    WHERE p.is_active
),
daily_sales AS (
    SELECT product_id,
           sale_date,
           SUM(quantity_sold)::integer AS units_sold,
           SUM(quantity_sold * unit_price) AS revenue
    FROM sales_transactions
    GROUP BY product_id, sale_date
)
SELECT pc.product_id,
       pc.sku,
       pc.demand_date,
       COALESCE(ds.units_sold, 0) AS units_sold,
       COALESCE(ds.revenue, 0) AS revenue
FROM product_calendar pc
LEFT JOIN daily_sales ds
       ON ds.product_id = pc.product_id
      AND ds.sale_date = pc.demand_date;

COMMENT ON VIEW v_daily_demand IS
    'Daily sell-through with zero-demand days; use this view for demand variability, not raw sales.';


-- 2. Weekly demand. The dashboard uses these rows for trend lines and XYZ CV.
CREATE OR REPLACE VIEW v_weekly_demand AS
WITH weekly AS (
    SELECT product_id,
           sku,
           date_trunc('week', demand_date)::date AS week_start,
           units_sold,
           revenue
    FROM v_daily_demand
)
SELECT product_id,
       sku,
       week_start,
       (week_start + 6)::date AS week_end,
       SUM(units_sold)::integer AS units_sold,
       SUM(revenue) AS revenue
FROM weekly
GROUP BY product_id, sku, week_start;

COMMENT ON VIEW v_weekly_demand IS
    'Monday-start weekly demand, including zero-demand weeks through calendar completion.';


-- 3. Trailing 52 complete weeks of demand statistics. Complete weeks prevent a
--    partial horizon-end week from understating demand or distorting the CV.
CREATE OR REPLACE VIEW v_weekly_demand_stats AS
WITH complete_weeks AS (
    SELECT w.product_id,
           w.sku,
           w.week_start,
           w.week_end,
           w.units_sold,
           ROW_NUMBER() OVER (
               PARTITION BY w.product_id
               ORDER BY w.week_start DESC
           ) AS recency_rank
    FROM v_weekly_demand w
    WHERE w.week_end <= (SELECT MAX(sale_date) FROM sales_transactions)
),
recent_weeks AS (
    SELECT *
    FROM complete_weeks
    WHERE recency_rank <= 52
)
SELECT product_id,
       sku,
       COUNT(*) AS weeks_observed,
       AVG(units_sold)::numeric(14, 3) AS weekly_mean_units,
       COALESCE(STDDEV_SAMP(units_sold), 0)::numeric(14, 3) AS weekly_std_units,
       COALESCE(
           STDDEV_SAMP(units_sold) / NULLIF(AVG(units_sold), 0),
           0
       )::numeric(10, 4) AS demand_cv
FROM recent_weeks
GROUP BY product_id, sku;

COMMENT ON VIEW v_weekly_demand_stats IS
    'Trailing 52 complete-week demand mean, standard deviation, and coefficient of variation.';


-- 4. Last 365 days of consumption value at cost. This is the ABC input.
CREATE OR REPLACE VIEW v_annual_consumption AS
WITH bounds AS (
    SELECT MAX(sale_date) AS max_date
    FROM sales_transactions
),
annual_sales AS (
    SELECT s.product_id,
           SUM(s.quantity_sold)::integer AS annual_units,
           SUM(s.quantity_sold * s.unit_price) AS annual_revenue
    FROM sales_transactions s
    CROSS JOIN bounds b
    WHERE s.sale_date > (b.max_date - interval '365 days')
      AND s.sale_date <= b.max_date
    GROUP BY s.product_id
)
SELECT p.product_id,
       p.sku,
       p.product_name,
       p.category,
       p.demand_pattern,
       p.supplier_id,
       COALESCE(a.annual_units, 0) AS annual_units,
       COALESCE(a.annual_units, 0) * p.unit_cost AS annual_consumption_value,
       COALESCE(a.annual_revenue, 0) AS annual_revenue,
       p.unit_cost
FROM products p
LEFT JOIN annual_sales a ON a.product_id = p.product_id
WHERE p.is_active;

COMMENT ON VIEW v_annual_consumption IS
    'Trailing 365-day annual units and consumption value at standard cost.';


-- 5. ABC classification using cumulative consumption value: A = 80% of value,
--    B = next 15%, C = remaining 5%. Cumulative value through the previous SKU
--    is used so each boundary SKU is assigned to the class it completes.
CREATE OR REPLACE VIEW v_abc_xyz AS
WITH ranked AS (
    SELECT a.*,
           SUM(a.annual_consumption_value) OVER () AS total_consumption_value,
           COALESCE(
               SUM(a.annual_consumption_value) OVER (
                   ORDER BY a.annual_consumption_value DESC, a.sku
                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
               ),
               0
           ) AS value_ranked_before
    FROM v_annual_consumption a
),
abc AS (
    SELECT r.*,
           CASE
               WHEN r.total_consumption_value = 0 THEN 'C'
               WHEN r.value_ranked_before / r.total_consumption_value < 0.80 THEN 'A'
               WHEN r.value_ranked_before / r.total_consumption_value < 0.95 THEN 'B'
               ELSE 'C'
           END AS abc_class
    FROM ranked r
)
SELECT a.product_id,
       a.sku,
       a.product_name,
       a.category,
       a.demand_pattern,
       a.supplier_id,
       a.annual_units,
       a.annual_consumption_value,
       a.annual_revenue,
       a.abc_class,
       COALESCE(w.weekly_mean_units, 0) AS weekly_mean_units,
       COALESCE(w.weekly_std_units, 0) AS weekly_std_units,
       COALESCE(w.demand_cv, 0) AS demand_cv,
       CASE
           WHEN COALESCE(w.weekly_mean_units, 0) <= 0 THEN 'Z'
           WHEN COALESCE(w.demand_cv, 0) <= 0.50 THEN 'X'
           WHEN COALESCE(w.demand_cv, 0) <= 1.00 THEN 'Y'
           ELSE 'Z'
       END AS xyz_class,
       a.abc_class || CASE
           WHEN COALESCE(w.weekly_mean_units, 0) <= 0 THEN 'Z'
           WHEN COALESCE(w.demand_cv, 0) <= 0.50 THEN 'X'
           WHEN COALESCE(w.demand_cv, 0) <= 1.00 THEN 'Y'
           ELSE 'Z'
       END AS abc_xyz_segment
FROM abc a
LEFT JOIN v_weekly_demand_stats w ON w.product_id = a.product_id;

COMMENT ON VIEW v_abc_xyz IS
    'ABC by annual consumption value (80/95 cumulative split) and XYZ by weekly demand CV (0.5/1.0).';


-- 6. Latest on-hand position and all open inbound units.
CREATE OR REPLACE VIEW v_latest_inventory AS
WITH latest AS (
    SELECT DISTINCT ON (product_id)
           product_id,
           snapshot_date,
           on_hand_units,
           inbound_units
    FROM inventory_snapshots
    ORDER BY product_id, snapshot_date DESC
)
SELECT l.product_id,
       p.sku,
       p.product_name,
       l.snapshot_date,
       l.on_hand_units,
       l.inbound_units,
       l.on_hand_units + l.inbound_units AS inventory_position_units,
       l.on_hand_units * p.unit_cost AS on_hand_value
FROM latest l
JOIN products p ON p.product_id = l.product_id;

CREATE OR REPLACE VIEW v_open_inbound AS
SELECT p.product_id,
       p.sku,
       COUNT(*)::integer AS open_po_count,
       SUM(po.quantity_ordered - po.quantity_received)::integer AS open_inbound_units,
       MIN(po.promised_date) AS next_promised_date,
       SUM(
           CASE WHEN po.promised_date < (SELECT MAX(snapshot_date) FROM inventory_snapshots)
                THEN po.quantity_ordered - po.quantity_received
                ELSE 0
           END
       )::integer AS overdue_inbound_units
FROM purchase_orders po
JOIN products p ON p.product_id = po.product_id
WHERE po.status IN ('OPEN', 'PARTIALLY_RECEIVED')
GROUP BY p.product_id, p.sku;

COMMENT ON VIEW v_open_inbound IS
    'Open inbound supply, including units past their promised date at the latest inventory snapshot.';


-- 7. Purchase-order lead-time observations and supplier scorecard.
CREATE OR REPLACE VIEW v_purchase_order_performance AS
SELECT po.po_id,
       po.po_number,
       po.product_id,
       p.sku,
       po.supplier_id,
       s.supplier_name,
       po.order_date,
       po.promised_date,
       po.received_date,
       po.quoted_lead_time_days,
       (po.received_date - po.order_date) AS actual_lead_time_days,
       (po.promised_date - po.order_date) AS promised_lead_time_days,
       (po.received_date - po.promised_date) AS variance_days,
       (po.received_date <= po.promised_date) AS on_time,
       GREATEST(po.received_date - po.promised_date, 0) AS days_late,
       po.quantity_ordered,
       po.quantity_received,
       po.status
FROM purchase_orders po
JOIN products p ON p.product_id = po.product_id
JOIN suppliers s ON s.supplier_id = po.supplier_id
WHERE po.received_date IS NOT NULL
  AND po.status <> 'CANCELLED';

CREATE OR REPLACE VIEW v_supplier_performance AS
SELECT supplier_id,
       supplier_name,
       COUNT(*)::integer AS received_po_count,
       AVG(actual_lead_time_days)::numeric(8, 2) AS avg_actual_lead_time_days,
       AVG(promised_lead_time_days)::numeric(8, 2) AS avg_promised_lead_time_days,
       STDDEV_SAMP(actual_lead_time_days)::numeric(8, 2) AS lead_time_std_days,
       AVG(variance_days)::numeric(8, 2) AS avg_variance_days,
       AVG(days_late)::numeric(8, 2) AS avg_days_late,
       AVG(CASE WHEN on_time THEN 1.0 ELSE 0.0 END)::numeric(6, 4) AS on_time_rate,
       (PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY actual_lead_time_days))
           ::numeric(8, 2) AS p90_actual_lead_time_days,
       SUM(quantity_ordered)::integer AS units_ordered,
       SUM(quantity_received)::integer AS units_received
FROM v_purchase_order_performance
GROUP BY supplier_id, supplier_name;

CREATE OR REPLACE VIEW v_lead_time_stats AS
SELECT s.supplier_id,
       s.supplier_name,
       s.promised_lead_time_days,
       COALESCE(sp.received_po_count, 0) AS received_po_count,
       COALESCE(sp.avg_actual_lead_time_days, s.promised_lead_time_days) AS planning_lead_time_days,
       COALESCE(sp.lead_time_std_days, s.lead_time_sigma_days) AS planning_lead_time_std_days,
       COALESCE(sp.on_time_rate, 0) AS historical_on_time_rate
FROM suppliers s
LEFT JOIN v_supplier_performance sp ON sp.supplier_id = s.supplier_id;

COMMENT ON VIEW v_lead_time_stats IS
    'Actual lead-time mean/std used by the safety-stock formula, with contractual fallback.';


-- 8. Trailing 365-day daily demand statistics, including zero-demand days.
CREATE OR REPLACE VIEW v_daily_demand_stats AS
WITH bounds AS (
    SELECT MAX(demand_date) AS max_date
    FROM v_daily_demand
)
SELECT product_id,
       sku,
       COUNT(*)::integer AS days_observed,
       AVG(units_sold)::numeric(14, 4) AS avg_daily_units,
       COALESCE(STDDEV_SAMP(units_sold), 0)::numeric(14, 4) AS daily_std_units,
       SUM(units_sold)::integer AS annual_units
FROM v_daily_demand d
CROSS JOIN bounds b
WHERE d.demand_date > (b.max_date - interval '365 days')
GROUP BY product_id, sku;

COMMENT ON VIEW v_daily_demand_stats IS
    'Daily mean and standard deviation over 365 calendar days; zero-sale days included.';


-- 9. SQL implementation of the service-level / ROP engine. This mirrors the
--    Python calculation and is useful for a live Tableau extract.
CREATE OR REPLACE VIEW v_reorder_recommendations AS
WITH base AS (
    SELECT p.product_id,
           p.sku,
           p.product_name,
           p.category,
           p.demand_pattern,
           p.unit_cost,
           p.unit_price,
           p.holding_cost_pct,
           p.ordering_cost,
           p.target_service_level,
           p.supplier_id,
           COALESCE(ac.annual_units, 0) AS annual_units,
           COALESCE(ac.annual_consumption_value, 0) AS annual_consumption_value,
           COALESCE(ds.avg_daily_units, 0) AS avg_daily_units,
           COALESCE(ds.daily_std_units, 0) AS daily_std_units,
           ls.planning_lead_time_days AS avg_lead_time_days,
           ls.planning_lead_time_std_days AS lead_time_std_days,
           ls.historical_on_time_rate,
           COALESCE(inv.on_hand_units, 0) AS on_hand_units,
           COALESCE(inb.open_inbound_units, 0) AS inbound_units,
           COALESCE(inv.snapshot_date, CURRENT_DATE) AS as_of_date
    FROM products p
    LEFT JOIN v_annual_consumption ac ON ac.product_id = p.product_id
    LEFT JOIN v_daily_demand_stats ds ON ds.product_id = p.product_id
    LEFT JOIN v_lead_time_stats ls ON ls.supplier_id = p.supplier_id
    LEFT JOIN v_latest_inventory inv ON inv.product_id = p.product_id
    LEFT JOIN v_open_inbound inb ON inb.product_id = p.product_id
    WHERE p.is_active
),
policy AS (
    SELECT b.*,
           (b.on_hand_units + b.inbound_units) AS inventory_position_units,
           GREATEST(
               0,
               1.2815515655 * sqrt(
                   b.avg_lead_time_days * power(b.daily_std_units, 2)
                   + power(b.avg_daily_units, 2) * power(b.lead_time_std_days, 2)
               )
           )::numeric(12, 2) AS safety_stock_90_units,
           GREATEST(
               0,
               1.6448536270 * sqrt(
                   b.avg_lead_time_days * power(b.daily_std_units, 2)
                   + power(b.avg_daily_units, 2) * power(b.lead_time_std_days, 2)
               )
           )::numeric(12, 2) AS safety_stock_95_units,
           GREATEST(
               0,
               2.3263478740 * sqrt(
                   b.avg_lead_time_days * power(b.daily_std_units, 2)
                   + power(b.avg_daily_units, 2) * power(b.lead_time_std_days, 2)
               )
           )::numeric(12, 2) AS safety_stock_99_units,
           CASE
               WHEN b.unit_cost > 0 AND b.holding_cost_pct > 0
               THEN sqrt(
                   (2 * b.annual_units * b.ordering_cost)
                   / (b.unit_cost * b.holding_cost_pct)
               )
               ELSE 0
           END::numeric(14, 2) AS eoq_units
    FROM base b
),
recommendations AS (
    SELECT p.*,
           (p.avg_daily_units * p.avg_lead_time_days + p.safety_stock_90_units)::numeric(14, 2) AS rop_90_units,
           (p.avg_daily_units * p.avg_lead_time_days + p.safety_stock_95_units)::numeric(14, 2) AS rop_95_units,
           (p.avg_daily_units * p.avg_lead_time_days + p.safety_stock_99_units)::numeric(14, 2) AS rop_99_units,
           (
               p.avg_daily_units * p.avg_lead_time_days
               + CASE
                   WHEN p.target_service_level <= 0.90 THEN p.safety_stock_90_units
                   WHEN p.target_service_level <= 0.95 THEN p.safety_stock_95_units
                   ELSE p.safety_stock_99_units
                 END
           )::numeric(14, 2) AS rop_at_target_units,
           (p.inventory_position_units
               - (p.avg_daily_units * p.avg_lead_time_days + p.safety_stock_95_units)
           )::numeric(14, 2) AS gap_to_rop_95_units
    FROM policy p
)
SELECT r.*,
       (r.inventory_position_units - r.rop_at_target_units)::numeric(14, 2)
           AS gap_to_rop_target_units,
       CASE
           WHEN r.inventory_position_units <= 0 THEN 'Stocked out'
           WHEN r.inventory_position_units <= r.rop_at_target_units THEN 'Reorder now'
           WHEN r.on_hand_units <= r.rop_at_target_units THEN 'Inbound pending'
           ELSE 'Healthy'
       END AS stock_status
FROM recommendations r;

COMMENT ON VIEW v_reorder_recommendations IS
    'SQL ROP engine at 90/95/99% service levels, using actual supplier lead-time variability.';
