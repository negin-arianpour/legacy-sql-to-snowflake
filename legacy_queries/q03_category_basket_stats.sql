-- dialect: tsql
-- title: Basket statistics per product category
-- ordered: true
SELECT
    p.category,
    COUNT(DISTINCT oi.order_id) AS orders_with_category,
    SUM(oi.quantity) / COUNT(DISTINCT oi.order_id) AS avg_units_per_order,
    AVG(oi.quantity) AS avg_line_quantity,
    CAST(AVG(oi.unit_price) AS INT) AS avg_price_whole
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
GROUP BY p.category
ORDER BY p.category;
