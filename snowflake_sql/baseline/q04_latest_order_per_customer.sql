-- converted from q04_latest_order_per_customer.sql (tsql)
SELECT
  c.customer_id,
  c.name,
  lo.order_id,
  lo.order_date,
  lo.status
FROM customers AS c INNER JOIN LATERAL (
  SELECT
    o.order_id,
    o.order_date,
    o.status
  FROM orders AS o
  WHERE
    o.customer_id = c.customer_id
  ORDER BY
    o.order_date DESC NULLS LAST,
    o.order_id DESC NULLS LAST
  LIMIT 1
) AS lo
ORDER BY
  c.customer_id NULLS FIRST;
