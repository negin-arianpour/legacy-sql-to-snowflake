-- converted from q07_org_chart.sql (oracle)
WITH RECURSIVE org (emp_id, emp_name, depth, reporting_path, top_manager) AS (
    SELECT emp_id,
           emp_name,
           1,
           '/' || emp_name,
           emp_name
    FROM employees
    WHERE manager_id IS NULL
    UNION ALL
    SELECT e.emp_id,
           e.emp_name,
           o.depth + 1,
           o.reporting_path || '/' || e.emp_name,
           o.top_manager
    FROM employees e
    JOIN org o ON e.manager_id = o.emp_id
)
SELECT emp_id, emp_name, depth, reporting_path, top_manager
FROM org
ORDER BY reporting_path;
