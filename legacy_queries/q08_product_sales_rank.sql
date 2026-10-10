-- dialect: oracle
-- title: Product sales ranked within category (including unsold products)
-- ordered: true
SELECT p.category,
       p.product_name,
       NVL(SUM(oi.quantity), 0) AS units_sold,
       NVL(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
       NVL2(MAX(oi.order_id), 'Active', 'Never sold') AS sales_status,
       RANK() OVER (PARTITION BY p.category
                    ORDER BY NVL(SUM(oi.quantity * oi.unit_price), 0) DESC) AS category_rank
FROM products p, order_items oi
WHERE p.product_id = oi.product_id(+)
GROUP BY p.category, p.product_name
ORDER BY p.category, category_rank, p.product_name;
