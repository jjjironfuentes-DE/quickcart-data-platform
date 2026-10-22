
-- ============================================================
-- QUICKCART BUSINESS QUERIES
-- PostgreSQL
-- Revenue definition: only orders with payment_status = 'paid'
-- ============================================================


-- Q1. Top 10 customers by revenue
SELECT
    c.customer_id,
    c.customer_name,
    SUM(o.quantity * o.unit_price) AS revenue
FROM core.orders AS o
JOIN core.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.payment_status = 'paid'
GROUP BY c.customer_id, c.customer_name
ORDER BY revenue DESC
LIMIT 10;


-- Q2. Month-over-month sales growth
-- Include months with zero sales so LAG compares calendar months.
WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', order_date)::date AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM core.orders
    WHERE payment_status = 'paid'
    GROUP BY 1
),
month_bounds AS (
    SELECT MIN(month_start) AS first_month,
           MAX(month_start) AS last_month
    FROM monthly_sales
),
calendar AS (
    SELECT gs.generated_month::date AS month_start
    FROM month_bounds
    CROSS JOIN LATERAL GENERATE_SERIES(
        first_month::timestamp,
        last_month::timestamp,
        INTERVAL '1 month'
    ) AS gs(generated_month)
),
filled_months AS (
    SELECT
        c.month_start,
        COALESCE(m.revenue, 0::numeric) AS revenue
    FROM calendar AS c
    LEFT JOIN monthly_sales AS m USING (month_start)
),
with_previous AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_month_revenue
    FROM filled_months
)
SELECT
    month_start,
    revenue,
    previous_month_revenue,
    CASE
        WHEN previous_month_revenue IS NULL
          OR previous_month_revenue = 0
        THEN NULL
        ELSE ROUND(
            100.0 * (revenue - previous_month_revenue)
            / previous_month_revenue,
            2
        )
    END AS mom_growth_pct
FROM with_previous
ORDER BY month_start;


-- Q3. Customers who ordered in consecutive calendar months
-- This query considers all valid orders, regardless of payment status.
WITH customer_months AS (
    SELECT DISTINCT
        customer_id,
        DATE_TRUNC('month', order_date)::date AS order_month
    FROM core.orders
),
with_previous AS (
    SELECT
        customer_id,
        order_month,
        LAG(order_month) OVER (
            PARTITION BY customer_id
            ORDER BY order_month
        ) AS previous_order_month
    FROM customer_months
)
SELECT
    c.customer_id,
    c.customer_name,
    previous_order_month,
    order_month AS current_order_month
FROM with_previous AS w
JOIN core.customers AS c
    ON c.customer_id = w.customer_id
WHERE order_month =
      (previous_order_month + INTERVAL '1 month')::date
ORDER BY c.customer_id, order_month;


-- Q4. Products that have never been ordered
-- Any order status counts as an order for this definition.
SELECT
    p.product_id,
    p.product_name,
    p.category
FROM core.products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM core.orders AS o
    WHERE o.product_id = p.product_id
)
ORDER BY p.product_id;


-- Q5. Revenue contribution percentage by category
WITH category_revenue AS (
    SELECT
        p.category,
        COALESCE(
            SUM(o.quantity * o.unit_price)
                FILTER (WHERE o.payment_status = 'paid'),
            0::numeric
        ) AS revenue
    FROM core.products AS p
    LEFT JOIN core.orders AS o
        ON o.product_id = p.product_id
    GROUP BY p.category
)
SELECT
    category,
    revenue,
    ROUND(
        100.0 * revenue / NULLIF(SUM(revenue) OVER (), 0),
        2
    ) AS revenue_contribution_pct
FROM category_revenue
ORDER BY revenue DESC;


-- Q6. Rank customers by total paid revenue
WITH customer_revenue AS (
    SELECT
        c.customer_id,
        c.customer_name,
        COALESCE(
            SUM(o.quantity * o.unit_price),
            0::numeric
        ) AS revenue
    FROM core.customers AS c
    LEFT JOIN core.orders AS o
        ON o.customer_id = c.customer_id
       AND o.payment_status = 'paid'
    GROUP BY c.customer_id, c.customer_name
)
SELECT
    customer_id,
    customer_name,
    revenue,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
FROM customer_revenue
ORDER BY revenue_rank, customer_id;


-- Q7. Running total of paid sales by month
WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', order_date)::date AS month_start,
        SUM(quantity * unit_price) AS monthly_revenue
    FROM core.orders
    WHERE payment_status = 'paid'
    GROUP BY 1
)
SELECT
    month_start,
    monthly_revenue,
    SUM(monthly_revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM monthly_sales
ORDER BY month_start;


-- Q8. Highest-selling product per category
-- "Highest-selling" means greatest paid quantity sold.
WITH product_sales AS (
    SELECT
        p.category,
        p.product_id,
        p.product_name,
        COALESCE(
            SUM(o.quantity)
                FILTER (WHERE o.payment_status = 'paid'),
            0
        ) AS units_sold,
        COALESCE(
            SUM(o.quantity * o.unit_price)
                FILTER (WHERE o.payment_status = 'paid'),
            0::numeric
        ) AS paid_revenue
    FROM core.products AS p
    LEFT JOIN core.orders AS o
        ON o.product_id = p.product_id
    GROUP BY p.category, p.product_id, p.product_name
),
ranked_products AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY category
            ORDER BY units_sold DESC, paid_revenue DESC, product_id
        ) AS category_rank
    FROM product_sales
    WHERE units_sold > 0
)
SELECT
    category,
    product_id,
    product_name,
    units_sold,
    paid_revenue
FROM ranked_products
WHERE category_rank = 1
ORDER BY category;


-- Q9. Rolling 7-calendar-day average of paid sales
-- Zero-sales days are included. The first output day has
-- a complete window of seven calendar days.
WITH bounds AS (
    SELECT
        MIN(order_date) AS first_day,
        MAX(order_date) AS last_day
    FROM core.orders
    WHERE payment_status = 'paid'
),
calendar AS (
    SELECT gs.generated_day::date AS sales_date
    FROM bounds
    CROSS JOIN LATERAL GENERATE_SERIES(
        first_day::timestamp,
        last_day::timestamp,
        INTERVAL '1 day'
    ) AS gs(generated_day)
),
daily_sales AS (
    SELECT
        order_date AS sales_date,
        SUM(quantity * unit_price) AS daily_revenue
    FROM core.orders
    WHERE payment_status = 'paid'
    GROUP BY order_date
),
filled_days AS (
    SELECT
        c.sales_date,
        COALESCE(d.daily_revenue, 0::numeric) AS daily_revenue
    FROM calendar AS c
    LEFT JOIN daily_sales AS d USING (sales_date)
),
rolling AS (
    SELECT
        sales_date,
        daily_revenue,
        AVG(daily_revenue) OVER (
            ORDER BY sales_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7_day_average,
        COUNT(*) OVER (
            ORDER BY sales_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS days_in_window
    FROM filled_days
)
SELECT
    sales_date,
    daily_revenue,
    ROUND(rolling_7_day_average, 2) AS rolling_7_day_average
FROM rolling
WHERE days_in_window = 7
ORDER BY sales_date;


-- ============================================================
-- END OF BUSINESS QUERIES
-- ============================================================
