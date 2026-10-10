-- converted from q06_order_pagination.sql (oracle)
SELECT order_id, customer_name, order_month, status_label, net_value, rn
FROM (
    SELECT o.order_id,
           c.name AS customer_name,
           TO_CHAR(o.order_date, 'YYYY-MM') AS order_month,
           DECODE(o.status, 'SHIPPED', 'Done', 'PENDING', 'Waiting', 'Other') AS status_label,
           ROUND(SUM(oi.quantity * oi.unit_price) * (1 - NVL(o.discount_pct, 0) / 100), 2) AS net_value,
           ROW_NUMBER() OVER (
               ORDER BY ROUND(SUM(oi.quantity * oi.unit_price) * (1 - NVL(o.discount_pct, 0) / 100), 2) DESC,
                        o.order_id
           ) AS rn
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY o.order_id, c.name, o.order_date, o.status, o.discount_pct
)
WHERE rn BETWEEN 6 AND 10
ORDER BY rn;
