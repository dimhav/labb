MODEL (
  name analytics.fct_daily_sales,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column order_date
  ),
  description 'Daglig forsaljning per land, produkt och segment.',
  columns (
    order_date DATE,
    country TEXT,
    segment TEXT,
    product TEXT,
    orders BIGINT,
    units BIGINT,
    revenue DECIMAL(18, 2)
  ),
  audits (
    not_null(columns := (order_date, revenue)),
    unique_combination_of_columns(columns := (order_date, country, segment, product))
  )
);

SELECT
    o.order_date,
    c.country,
    c.segment,
    o.product,
    COUNT(*)                      AS orders,
    SUM(o.quantity)::BIGINT       AS units,
    ROUND(SUM(o.revenue), 2)      AS revenue
FROM analytics.stg_orders AS o
JOIN analytics.stg_customers AS c
  ON o.customer_id = c.customer_id
WHERE o.order_date BETWEEN @start_date AND @end_date
GROUP BY o.order_date, c.country, c.segment, o.product
