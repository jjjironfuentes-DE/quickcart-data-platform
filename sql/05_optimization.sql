
-- QUICKCART: SQL QUERY OPTIMIZATION
-- Baseline execution plan for the assessment scenario.

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    c.customer_name,
    SUM(o.quantity * o.unit_price) AS total_revenue
FROM core.orders AS o
JOIN core.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_date >= DATE '2025-01-01'
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY total_revenue DESC;
