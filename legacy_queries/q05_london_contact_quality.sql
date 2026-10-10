-- dialect: tsql
-- title: Contact data quality check for London customers
-- ordered: true
SELECT
    c.customer_id,
    c.name,
    LEN(c.name) AS name_length,
    CHARINDEX('@', c.email) AS at_position,
    SUBSTRING(c.email, CHARINDEX('@', c.email) + 1, LEN(c.email)) AS email_domain,
    CASE WHEN c.phone IS NULL THEN 'missing' ELSE 'ok' END AS phone_status
FROM customers c
WHERE c.city = 'london'
ORDER BY c.customer_id;
