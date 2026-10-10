-- converted from q07_org_chart.sql (oracle)
SELECT
  emp_id,
  emp_name,
  LEVEL AS depth,
  SYS_CONNECT_BY_PATH(emp_name, '/') AS reporting_path,
  CONNECT_BY_ROOT emp_name AS top_manager
FROM employees
START WITH manager_id IS NULL
CONNECT BY PRIOR emp_id = manager_id
ORDER SIBLINGS BY
  emp_name;
