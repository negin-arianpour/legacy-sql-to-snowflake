-- converted from q03_category_basket_stats.sql (tsql)
SELECT
    p.category,
    COUNT(DISTINCT oi.order_id) AS orders_with_category,
    CAST(TRUNC(SUM(oi.quantity) / COUNT(DISTINCT oi.order_id)) AS INT) AS avg_units_per_order,
    CAST(TRUNC(AVG(oi.quantity)) AS INT) AS avg_line_quantity,
    CAST(TRUNC(AVG(oi.unit_price)) AS INT) AS avg_price_whole
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
GROUP BY p.category
ORDER BY p.category;
