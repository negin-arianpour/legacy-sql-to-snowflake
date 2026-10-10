-- converted from q02_monthly_shipments.sql (tsql)
SELECT
  TRY_CAST(TO_CHAR(o.order_date, 'yyyy-mm-DD hh24:mi:ss') AS VARCHAR(7)) AS order_month,
  COUNT(*) AS orders_shipped,
  DATEDIFF(DAY, CAST(MIN(o.order_date) AS TIMESTAMP), CAST(MAX(o.order_date) AS TIMESTAMP)) AS span_days,
  SUM(COALESCE(o.discount_pct, 0)) AS total_discount_pct
FROM orders AS o
WHERE
  o.status = 'SHIPPED'
  AND o.order_date >= '2025-01-01'
  AND o.order_date < DATEADD(MONTH, 6, '2025-01-01')
GROUP BY
  TRY_CAST(TO_CHAR(o.order_date, 'yyyy-mm-DD hh24:mi:ss') AS VARCHAR(7))
ORDER BY
  order_month NULLS FIRST;
