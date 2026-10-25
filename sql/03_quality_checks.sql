-- =============================================================================
-- Data quality checks
-- Each query should return zero rows for the "exception" checks. Result-set
-- names identify the control; use these in a dbt/Airflow validation task.
-- =============================================================================

SET search_path TO supply_chain, public;

-- Row counts and horizon
SELECT 'suppliers' AS table_name, COUNT(*) AS row_count FROM suppliers
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'sales_transactions', COUNT(*) FROM sales_transactions
UNION ALL SELECT 'purchase_orders', COUNT(*) FROM purchase_orders
UNION ALL SELECT 'inventory_snapshots', COUNT(*) FROM inventory_snapshots;

SELECT MIN(sale_date) AS first_sale, MAX(sale_date) AS last_sale,
       COUNT(DISTINCT date_trunc('month', sale_date)) AS months_of_history
FROM sales_transactions;

-- 1. Duplicate SKUs (expect 0)
SELECT sku, COUNT(*) AS duplicate_count
FROM products
GROUP BY sku
HAVING COUNT(*) > 1;

-- 2. Sales with no product / purchase orders with no product (expect 0)
SELECT s.sale_id, s.product_id
FROM sales_transactions s
LEFT JOIN products p ON p.product_id = s.product_id
WHERE p.product_id IS NULL;

SELECT po.po_id, po.product_id
FROM purchase_orders po
LEFT JOIN products p ON p.product_id = po.product_id
WHERE p.product_id IS NULL;

-- 3. Purchase order supplier does not match the product's current supplier.
--    In this project's data model this should be 0. In a real system a product
--    can change supplier, so treat this as an advisory check rather than a hard
--    constraint unless supplier history is maintained.
SELECT po.po_id, po.product_id, po.supplier_id, p.supplier_id AS product_supplier_id
FROM purchase_orders po
JOIN products p ON p.product_id = po.product_id
WHERE po.supplier_id <> p.supplier_id;

-- 4. Invalid lead-time or quantity relationships (expect 0)
SELECT po_id
FROM purchase_orders
WHERE quantity_received > quantity_ordered
   OR received_date < order_date
   OR promised_date < order_date
   OR (status = 'RECEIVED' AND received_date IS NULL);

-- 5. Negative or zero demand (expect 0)
SELECT sale_id, quantity_sold
FROM sales_transactions
WHERE quantity_sold <= 0;

-- 6. Inventory snapshots: missing latest position for an active SKU (expect 0)
SELECT p.sku
FROM products p
LEFT JOIN LATERAL (
    SELECT snapshot_date
    FROM inventory_snapshots i
    WHERE i.product_id = p.product_id
    ORDER BY snapshot_date DESC
    LIMIT 1
) latest ON TRUE
WHERE p.is_active
  AND latest.snapshot_date IS NULL;

-- 7. Snapshot gaps: products with fewer weekly snapshots than expected.
--    Adjust the expected count to the project horizon.
WITH expected AS (
    SELECT COUNT(DISTINCT snapshot_date) AS snapshot_days
    FROM inventory_snapshots
),
observed AS (
    SELECT product_id, COUNT(*) AS snapshot_count
    FROM inventory_snapshots
    GROUP BY product_id
)
SELECT p.sku, o.snapshot_count, e.snapshot_days
FROM products p
JOIN observed o ON o.product_id = p.product_id
CROSS JOIN expected e
WHERE o.snapshot_count <> e.snapshot_days;

-- 8. Calendar completeness: daily demand rows should equal active SKUs x days.
WITH bounds AS (
    SELECT MIN(sale_date) AS min_date, MAX(sale_date) AS max_date
    FROM sales_transactions
),
counts AS (
    SELECT COUNT(*) AS actual_rows FROM v_daily_demand
)
SELECT c.actual_rows,
       (SELECT COUNT(*) FROM products WHERE is_active)
       * (SELECT (max_date - min_date + 1) FROM bounds) AS expected_rows,
       c.actual_rows - (SELECT COUNT(*) FROM products WHERE is_active)
       * (SELECT (max_date - min_date + 1) FROM bounds) AS difference
FROM counts c;

-- 9. Lead-time observations summary
SELECT COUNT(*) AS received_pos,
       MIN(actual_lead_time_days) AS min_lead,
       AVG(actual_lead_time_days)::numeric(10, 2) AS avg_lead,
       MAX(actual_lead_time_days) AS max_lead,
       SUM(CASE WHEN on_time THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) AS on_time_rate
FROM v_purchase_order_performance;

-- 10. Open POs past their promised date at the latest snapshot (business alert)
SELECT po.po_number, po.sku, po.promised_date, po.quantity_ordered, po.status
FROM purchase_orders po
JOIN v_latest_inventory inv ON inv.product_id = po.product_id
WHERE po.status IN ('OPEN', 'PARTIALLY_RECEIVED')
  AND po.promised_date < inv.snapshot_date
ORDER BY po.promised_date;
