
-- QuickCart: load validated CSV data into core tables.
-- Temporary tables make the load repeatable.
-- Raw CSV files remain unchanged.

BEGIN;

CREATE TEMP TABLE load_customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT,
    email TEXT,
    city TEXT,
    signup_date DATE
) ON COMMIT DROP;

CREATE TEMP TABLE load_products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT,
    category TEXT,
    supplier_id BIGINT,
    cost_price NUMERIC(12, 2),
    selling_price NUMERIC(12, 2)
) ON COMMIT DROP;

CREATE TEMP TABLE load_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    product_id BIGINT,
    order_date DATE,
    quantity INTEGER,
    unit_price NUMERIC(12, 2),
    payment_status TEXT
) ON COMMIT DROP;

CREATE TEMP TABLE load_clickstream (
    event_id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    event_type TEXT,
    page_url TEXT,
    event_timestamp TIMESTAMPTZ,
    device_type TEXT
) ON COMMIT DROP;

-- Load cleaned CSV files into temporary tables.
\copy load_customers (customer_id, customer_name, email, city, signup_date) FROM '/data/processed/customers_clean.csv' WITH (FORMAT csv, HEADER true)
\copy load_products (product_id, product_name, category, supplier_id, cost_price, selling_price) FROM '/data/processed/products_clean.csv' WITH (FORMAT csv, HEADER true)
\copy load_orders (order_id, customer_id, product_id, order_date, quantity, unit_price, payment_status) FROM '/data/processed/orders_clean.csv' WITH (FORMAT csv, HEADER true)
\copy load_clickstream (event_id, customer_id, event_type, page_url, event_timestamp, device_type) FROM '/data/processed/clickstream_clean.csv' WITH (FORMAT csv, HEADER true)

-- Load parent tables first to satisfy foreign keys.
INSERT INTO core.customers (
    customer_id, customer_name, email, city, signup_date
)
SELECT customer_id, customer_name, email, city, signup_date
FROM load_customers
ON CONFLICT (customer_id) DO UPDATE SET
    customer_name = EXCLUDED.customer_name,
    email = EXCLUDED.email,
    city = EXCLUDED.city,
    signup_date = EXCLUDED.signup_date;

INSERT INTO core.products (
    product_id, product_name, category,
    supplier_id, cost_price, selling_price
)
SELECT product_id, product_name, category,
       supplier_id, cost_price, selling_price
FROM load_products
ON CONFLICT (product_id) DO UPDATE SET
    product_name = EXCLUDED.product_name,
    category = EXCLUDED.category,
    supplier_id = EXCLUDED.supplier_id,
    cost_price = EXCLUDED.cost_price,
    selling_price = EXCLUDED.selling_price;

-- Load orders after customers and products.
INSERT INTO core.orders (
    order_id, customer_id, product_id,
    order_date, quantity, unit_price, payment_status
)
SELECT order_id, customer_id, product_id,
       order_date, quantity, unit_price, payment_status
FROM load_orders
ON CONFLICT (order_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    product_id = EXCLUDED.product_id,
    order_date = EXCLUDED.order_date,
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    payment_status = EXCLUDED.payment_status;

-- Missing customer IDs are allowed for anonymous events.
INSERT INTO core.clickstream_events (
    event_id, customer_id, event_type,
    page_url, event_timestamp, device_type
)
SELECT event_id, customer_id, event_type,
       page_url, event_timestamp, device_type
FROM load_clickstream
ON CONFLICT (event_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    event_type = EXCLUDED.event_type,
    page_url = EXCLUDED.page_url,
    event_timestamp = EXCLUDED.event_timestamp,
    device_type = EXCLUDED.device_type;

COMMIT;
