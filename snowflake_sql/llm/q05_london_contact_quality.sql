-- converted from q05_london_contact_quality.sql (tsql)
SELECT
    c.customer_id,
    c.name,
    LENGTH(RTRIM(c.name)) AS name_length,
    CHARINDEX('@', c.email) AS at_position,
    SUBSTRING(c.email, CHARINDEX('@', c.email) + 1, LENGTH(RTRIM(c.email))) AS email_domain,
    CASE WHEN c.phone IS NULL THEN 'missing' ELSE 'ok' END AS phone_status
FROM customers c
WHERE LOWER(c.city) = 'london'
ORDER BY c.customer_id;
