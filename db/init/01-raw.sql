-- ===========================================================================
--  Raw-lager i warehouse-databasen.
--
--  raw.*      : radata, seedas med exempeldata nedan.
--  analytics.*: byggs av SQLMesh (se sqlmesh/models/).
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id   INTEGER PRIMARY KEY,
    name          TEXT        NOT NULL,
    country       TEXT        NOT NULL,
    segment       TEXT        NOT NULL,
    signup_date   DATE        NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.orders (
    order_id      BIGINT PRIMARY KEY,
    customer_id   INTEGER     NOT NULL REFERENCES raw.customers (customer_id),
    order_ts      TIMESTAMP   NOT NULL,
    product       TEXT        NOT NULL,
    quantity      INTEGER     NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10, 2) NOT NULL,
    status        TEXT        NOT NULL
);

-- ---------------------------------------------------------------------------
-- Seed: kunder
-- ---------------------------------------------------------------------------
INSERT INTO raw.customers (customer_id, name, country, segment, signup_date)
SELECT
    i,
    'Customer ' || i,
    (ARRAY['SE','NO','DK','FI','DE','NL'])[1 + (i % 6)],
    (ARRAY['Enterprise','Mid-Market','SMB'])[1 + (i % 3)],
    DATE '2024-01-01' + ((i * 7) % 700)
FROM generate_series(1, 500) AS i
ON CONFLICT (customer_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Seed: ordrar - ca 18 manader av transaktioner
-- ---------------------------------------------------------------------------
INSERT INTO raw.orders (order_id, customer_id, order_ts, product, quantity, unit_price, status)
SELECT
    i,
    1 + (i % 500),
    TIMESTAMP '2025-05-01 00:00:00'
        + ((i * 37) % 540) * INTERVAL '1 day'
        + ((i * 13) % 24) * INTERVAL '1 hour',
    (ARRAY['Widget','Gadget','Doohickey','Sprocket','Thingamajig'])[1 + (i % 5)],
    1 + (i % 9),
    ROUND((5 + (i % 95) + (i % 7) * 0.5)::numeric, 2),
    (ARRAY['completed','completed','completed','shipped','pending','cancelled'])[1 + (i % 6)]
FROM generate_series(1, 20000) AS i
ON CONFLICT (order_id) DO NOTHING;

ANALYZE raw.customers;
ANALYZE raw.orders;
