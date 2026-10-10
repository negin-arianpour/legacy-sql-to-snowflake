-- converted from q04_latest_order_per_customer.sql (tsql)
SELECT
    c.customer_id,
    c.name,
    o.order_id,
    o.order_date,
    o.status
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
) = 1
ORDER BY c.customer_id;
