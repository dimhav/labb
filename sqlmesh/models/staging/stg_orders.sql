MODEL (
  name analytics.stg_orders,
  kind FULL,
  description 'Stadade ordrar fran raw.orders.',
  columns (
    order_id BIGINT,
    customer_id INTEGER,
    order_ts TIMESTAMP,
    order_date DATE,
    product TEXT,
    quantity INTEGER,
    unit_price DECIMAL(10, 2),
    status TEXT,
    revenue DECIMAL(18, 2)
  ),
  audits (
    not_null(columns := (order_id, customer_id, order_ts)),
    unique_values(columns := (order_id))
  )
);

SELECT
    order_id,
    customer_id,
    order_ts,
    CAST(order_ts AS DATE)          AS order_date,
    product,
    quantity,
    unit_price,
    status,
    ROUND(quantity * unit_price, 2) AS revenue
FROM raw.orders
WHERE status <> 'cancelled'
