
-- QuickCart: load original CSV files into staging.
-- Source files are read-only and remain unchanged.

BEGIN;

TRUNCATE TABLE
    staging.stg_clickstream,
    staging.stg_orders,
    staging.stg_products,
    staging.stg_customers;

COMMIT;

\copy staging.stg_customers (customer_id, customer_name, email, city, signup_date) FROM '/data/raw/customers.csv' WITH (FORMAT csv, HEADER true)
\copy staging.stg_orders (order_id, customer_id, product_id, order_date, quantity, unit_price, payment_status) FROM '/data/raw/orders.csv' WITH (FORMAT csv, HEADER true)
\copy staging.stg_products (product_id, product_name, category, supplier_id, cost_price, selling_price) FROM '/data/raw/products.csv' WITH (FORMAT csv, HEADER true)
\copy staging.stg_clickstream (event_id, customer_id, event_type, page_url, event_timestamp, device_type) FROM '/data/raw/clickstream.csv' WITH (FORMAT csv, HEADER true)
