-- dialect: oracle
-- title: Second page (rows 6 to 10) of orders ranked by net value
-- ordered: true
SELECT order_id, customer_name, order_month, status_label, net_value, rn
FROM (
    SELECT a.*, ROWNUM rn
    FROM (
        SELECT o.order_id,
               c.name AS customer_name,
               TO_CHAR(o.order_date, 'YYYY-MM') AS order_month,
               DECODE(o.status, 'SHIPPED', 'Done', 'PENDING', 'Waiting', 'Other') AS status_label,
               ROUND(SUM(oi.quantity * oi.unit_price) * (1 - NVL(o.discount_pct, 0) / 100), 2) AS net_value
        FROM orders o, customers c, order_items oi
        WHERE o.customer_id = c.customer_id
          AND oi.order_id = o.order_id
        GROUP BY o.order_id, c.name, o.order_date, o.status, o.discount_pct
        ORDER BY net_value DESC, o.order_id
    ) a
    WHERE ROWNUM <= 10
)
WHERE rn > 5
ORDER BY rn;
