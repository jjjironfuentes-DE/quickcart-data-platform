
-- =========================================================
-- QUICKCART DATA PLATFORM
-- 01 - Create staging, core and operational schemas
-- Database: PostgreSQL
-- =========================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ops;


-- ---------------------------------------------------------
-- 1. STAGING TABLES
-- Store source values as TEXT to preserve the raw input.
-- Typed validation and transformations happen downstream.
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.stg_customers (
    customer_id   TEXT,
    customer_name TEXT,
    email         TEXT,
    city          TEXT,
    signup_date   TEXT,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.stg_orders (
    order_id       TEXT,
    customer_id    TEXT,
    product_id     TEXT,
    order_date     TEXT,
    quantity       TEXT,
    unit_price     TEXT,
    payment_status TEXT,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.stg_products (
    product_id   TEXT,
    product_name TEXT,
    category     TEXT,
    supplier_id  TEXT,
    cost_price   TEXT,
    selling_price TEXT,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.stg_clickstream (
    event_id        TEXT,
    customer_id     TEXT,
    event_type      TEXT,
    page_url        TEXT,
    event_timestamp TEXT,
    device_type     TEXT,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------
-- 2. CORE TABLES
-- Typed, validated data for application and analytics use.
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.customers (
    customer_id   BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email         TEXT,
    city          TEXT,
    signup_date   DATE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.products (
    product_id    BIGINT PRIMARY KEY,
    product_name  TEXT NOT NULL,
    category      TEXT NOT NULL,
    supplier_id   BIGINT,
    cost_price    NUMERIC(12, 2) NOT NULL CHECK (cost_price >= 0),
    selling_price NUMERIC(12, 2) NOT NULL CHECK (selling_price >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.orders (
    order_id       BIGINT PRIMARY KEY,
    customer_id    BIGINT NOT NULL REFERENCES core.customers(customer_id),
    product_id     BIGINT NOT NULL REFERENCES core.products(product_id),
    order_date     DATE NOT NULL,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(12, 2) NOT NULL CHECK (unit_price > 0),
    payment_status TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.clickstream_events (
    event_id        BIGINT PRIMARY KEY,
    customer_id     BIGINT REFERENCES core.customers(customer_id),
    event_type      TEXT NOT NULL,
    page_url        TEXT,
    event_timestamp TIMESTAMPTZ NOT NULL,
    device_type     TEXT NOT NULL DEFAULT 'unknown',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------
-- 3. OPERATIONAL TABLES
-- Shipment tracking, inventory, and customer support.
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS ops.shipments (
    shipment_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       BIGINT NOT NULL REFERENCES core.orders(order_id),
    tracking_number TEXT UNIQUE,
    carrier        TEXT,
    shipment_status TEXT NOT NULL DEFAULT 'pending',
    shipped_at     TIMESTAMPTZ,
    delivered_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        delivered_at IS NULL
        OR shipped_at IS NULL
        OR delivered_at >= shipped_at
    )
);

CREATE TABLE IF NOT EXISTS ops.shipment_events (
    shipment_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id       BIGINT NOT NULL REFERENCES ops.shipments(shipment_id),
    event_timestamp   TIMESTAMPTZ NOT NULL,
    event_status      TEXT NOT NULL,
    location          TEXT,
    description       TEXT
);

CREATE TABLE IF NOT EXISTS ops.warehouses (
    warehouse_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    warehouse_name TEXT NOT NULL,
    city           TEXT
);

CREATE TABLE IF NOT EXISTS ops.inventory (
    product_id       BIGINT NOT NULL REFERENCES core.products(product_id),
    warehouse_id     BIGINT NOT NULL REFERENCES ops.warehouses(warehouse_id),
    quantity_on_hand INTEGER NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    quantity_reserved INTEGER NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0),
    reorder_level    INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (product_id, warehouse_id),
    CHECK (quantity_reserved <= quantity_on_hand)
);

CREATE TABLE IF NOT EXISTS ops.support_tickets (
    ticket_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  BIGINT NOT NULL REFERENCES core.customers(customer_id),
    order_id     BIGINT REFERENCES core.orders(order_id),
    subject      TEXT NOT NULL,
    description  TEXT,
    status       TEXT NOT NULL DEFAULT 'open',
    priority     TEXT NOT NULL DEFAULT 'normal',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at    TIMESTAMPTZ
);


-- ---------------------------------------------------------
-- 4. INDEXES
-- Primary keys and unique constraints already create indexes.
-- These indexes support common filters, joins and lookups.
-- ---------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_customers_email
    ON core.customers (LOWER(email));

CREATE INDEX IF NOT EXISTS idx_orders_order_date
    ON core.orders (order_date);

CREATE INDEX IF NOT EXISTS idx_orders_customer_date
    ON core.orders (customer_id, order_date);

CREATE INDEX IF NOT EXISTS idx_orders_product
    ON core.orders (product_id);

CREATE INDEX IF NOT EXISTS idx_orders_payment_date
    ON core.orders (order_date)
    WHERE payment_status = 'paid';

CREATE INDEX IF NOT EXISTS idx_products_category
    ON core.products (category);

CREATE INDEX IF NOT EXISTS idx_clickstream_timestamp
    ON core.clickstream_events (event_timestamp);

CREATE INDEX IF NOT EXISTS idx_clickstream_customer_timestamp
    ON core.clickstream_events (customer_id, event_timestamp);

CREATE INDEX IF NOT EXISTS idx_shipments_order
    ON ops.shipments (order_id);

CREATE INDEX IF NOT EXISTS idx_shipment_events_shipment_time
    ON ops.shipment_events (shipment_id, event_timestamp);

CREATE INDEX IF NOT EXISTS idx_support_tickets_customer_status
    ON ops.support_tickets (customer_id, status);

CREATE INDEX IF NOT EXISTS idx_inventory_warehouse
    ON ops.inventory (warehouse_id);


-- =========================================================
-- END OF SCHEMA
-- =========================================================
