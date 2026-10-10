-- converted from q02_monthly_shipments.sql (tsql)
SELECT
    TO_CHAR(o.order_date, 'YYYY-MM') AS order_month,
    COUNT(*) AS orders_shipped,
    DATEDIFF(day, MIN(o.order_date), MAX(o.order_date)) AS span_days,
    SUM(COALESCE(o.discount_pct, 0)) AS total_discount_pct
FROM orders o
WHERE UPPER(o.status) = 'SHIPPED'
  AND o.order_date >= '2025-01-01'::DATE
  AND o.order_date < DATEADD(month, 6, '2025-01-01'::DATE)
GROUP BY TO_CHAR(o.order_date, 'YYYY-MM')
ORDER BY order_month;
