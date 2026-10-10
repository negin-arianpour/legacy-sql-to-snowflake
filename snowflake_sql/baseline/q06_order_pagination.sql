-- converted from q06_order_pagination.sql (oracle)
SELECT
  order_id,
  customer_name,
  order_month,
  status_label,
  net_value,
  rn
FROM (
  SELECT
    a.*,
    ROWNUM AS rn
  FROM (
    SELECT
      o.order_id,
      c.name AS customer_name,
      TO_CHAR(o.order_date, 'YYYY-MM') AS order_month,
      DECODE(o.status, 'SHIPPED', 'Done', 'PENDING', 'Waiting', 'Other') AS status_label,
      ROUND(SUM(oi.quantity * oi.unit_price) * (
        1 - COALESCE(o.discount_pct, 0) / 100
      ), 2) AS net_value
    FROM orders AS o, customers AS c, order_items AS oi
    WHERE
      o.customer_id = c.customer_id AND oi.order_id = o.order_id
    GROUP BY
      o.order_id,
      c.name,
      o.order_date,
      o.status,
      o.discount_pct
    ORDER BY
      net_value DESC,
      o.order_id
  ) AS a
  WHERE
    ROWNUM <= 10
)
WHERE
  rn > 5
ORDER BY
  rn;
