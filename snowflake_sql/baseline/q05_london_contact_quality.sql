-- converted from q05_london_contact_quality.sql (tsql)
SELECT
  c.customer_id,
  c.name,
  LENGTH(CAST(c.name AS VARCHAR)) AS name_length,
  CHARINDEX('@', c.email) AS at_position,
  SUBSTRING(c.email, CHARINDEX('@', c.email) + 1, LENGTH(CAST(c.email AS VARCHAR))) AS email_domain,
  CASE WHEN c.phone IS NULL THEN 'missing' ELSE 'ok' END AS phone_status
FROM customers AS c
WHERE
  c.city = 'london'
ORDER BY
  c.customer_id NULLS FIRST;
