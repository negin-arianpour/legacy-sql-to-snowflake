-- dialect: tsql
-- title: Shipped orders per month, first half of 2025
-- ordered: true
SELECT
    CONVERT(VARCHAR(7), o.order_date, 120) AS order_month,
    COUNT(*) AS orders_shipped,
    DATEDIFF(day, MIN(o.order_date), MAX(o.order_date)) AS span_days,
    SUM(ISNULL(o.discount_pct, 0)) AS total_discount_pct
FROM orders o
WHERE o.status = 'SHIPPED'
  AND o.order_date >= '2025-01-01'
  AND o.order_date < DATEADD(month, 6, '2025-01-01')
GROUP BY CONVERT(VARCHAR(7), o.order_date, 120)
ORDER BY order_month;
