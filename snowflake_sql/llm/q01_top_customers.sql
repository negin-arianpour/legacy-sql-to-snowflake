-- converted from q01_top_customers.sql (tsql)
SELECT
    c.customer_id,
    c.name || ' (' || c.city || ')' AS customer_label,
    COALESCE(c.email, 'n/a') AS contact_email,
    SUM(oi.quantity * oi.unit_price) AS gross_revenue,
    COUNT(DISTINCT o.order_id) AS order_count
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE UPPER(o.status) <> 'CANCELLED'
GROUP BY c.customer_id, c.name, c.city, c.email
ORDER BY gross_revenue DESC
LIMIT 5;
