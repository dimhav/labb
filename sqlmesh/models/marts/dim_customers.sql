MODEL (
  name analytics.dim_customers,
  kind FULL,
  description 'Kunddimension med aggregerad livstidsintakt.',
  columns (
    customer_id INTEGER,
    name TEXT,
    country TEXT,
    segment TEXT,
    signup_date DATE,
    orders BIGINT,
    lifetime_revenue DECIMAL(18, 2),
    first_order_date DATE,
    last_order_date DATE
  ),
  audits (
    not_null(columns := (customer_id, country, segment)),
    unique_values(columns := (customer_id))
  )
);

SELECT
    c.customer_id,
    c.name,
    c.country,
    c.segment,
    c.signup_date,
    COALESCE(COUNT(o.order_id), 0)              AS orders,
    COALESCE(ROUND(SUM(o.revenue), 2), 0)       AS lifetime_revenue,
    MIN(o.order_date)                           AS first_order_date,
    MAX(o.order_date)                           AS last_order_date
FROM analytics.stg_customers AS c
LEFT JOIN analytics.stg_orders AS o
  ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name, c.country, c.segment, c.signup_date
