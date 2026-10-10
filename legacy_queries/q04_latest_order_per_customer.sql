-- dialect: tsql
-- title: Most recent order for each customer
-- ordered: true
SELECT
    c.customer_id,
    c.name,
    lo.order_id,
    lo.order_date,
    lo.status
FROM customers c
CROSS APPLY (
    SELECT TOP 1 o.order_id, o.order_date, o.status
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
) lo
ORDER BY c.customer_id;
