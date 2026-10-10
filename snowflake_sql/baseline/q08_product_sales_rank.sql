-- converted from q08_product_sales_rank.sql (oracle)
SELECT
  p.category,
  p.product_name,
  COALESCE(SUM(oi.quantity), 0) AS units_sold,
  COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
  NVL2(MAX(oi.order_id), 'Active', 'Never sold') AS sales_status,
  RANK() OVER (
    PARTITION BY p.category
    ORDER BY COALESCE(SUM(oi.quantity * oi.unit_price), 0) DESC
  ) AS category_rank
FROM products AS p, order_items AS oi
WHERE
  p.product_id = oi.product_id (+)
GROUP BY
  p.category,
  p.product_name
ORDER BY
  p.category,
  category_rank,
  p.product_name;
