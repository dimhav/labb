MODEL (
  name analytics.stg_customers,
  kind FULL,
  description 'Stadat kundregister fran raw.customers.',
  columns (
    customer_id INTEGER,
    name TEXT,
    country TEXT,
    segment TEXT,
    signup_date DATE
  ),
  audits (
    not_null(columns := (customer_id, country, segment)),
    unique_values(columns := (customer_id))
  )
);

SELECT
    customer_id,
    TRIM(name)      AS name,
    UPPER(country)  AS country,
    segment,
    signup_date
FROM raw.customers
