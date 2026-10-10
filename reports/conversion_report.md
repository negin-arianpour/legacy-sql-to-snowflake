# Legacy SQL to Snowflake: conversion accuracy report

Generated 10 Oct 2026 10:58 · Snowflake engine: fakesnow (local Snowflake emulator on DuckDB)

## Accuracy

| Converter | Accurate | Failed | Not verifiable locally | Accuracy | pytest checks (pass / fail / skip) |
|---|---|---|---|---|---|
| LLM (Claude) | 8 / 8 | 0 | 0 | **100%** | 40 / 0 / 0 |
| Rule based baseline (sqlglot) | 0 / 7 | 7 | 1 | **0%** | 7 / 7 / 26 |

Accuracy = queries whose Snowflake output matches the legacy output exactly (columns, row count, values and row order) / queries that could be verified.

## Results by query

| Query | Dialect | Dialect traps in source | LLM | Baseline |
|---|---|---|---|---|
| Q01 Top 5 customers by gross revenue | tsql | TOP n row limit, + string concatenation, ISNULL, string comparison (case insensitive collation) | PASS | FAIL (execution_error) |
| Q02 Shipped orders per month, first half of 2025 | tsql | ISNULL, CONVERT with style code, string comparison (case insensitive collation) | PASS | FAIL (row_count_mismatch) |
| Q03 Basket statistics per product category | tsql | integer division, AVG over an integer column, CAST to INT (truncation) | PASS | FAIL (value_mismatch) |
| Q04 Most recent order for each customer | tsql | TOP n row limit, CROSS APPLY | PASS | FAIL (snowflake_restriction) |
| Q05 Contact data quality check for London customers | tsql | string comparison (case insensitive collation), LEN ignores trailing spaces | PASS | FAIL (row_count_mismatch) |
| Q06 Second page (rows 6 to 10) of orders ranked by net value | oracle | ROWNUM pagination, DECODE, NVL / NVL2, TO_CHAR date mask | PASS | FAIL (execution_error) |
| Q07 Organisation chart with reporting paths | oracle | CONNECT BY hierarchy, ORDER SIBLINGS BY | PASS | FAIL (execution_error) |
| Q08 Product sales ranked within category (including unsold products) | oracle | (+) outer join, NVL / NVL2 | PASS | NOT VERIFIABLE (not_verifiable_locally) |

## Errors caught by the checks

### Rule based baseline (sqlglot) · Q01 Top 5 customers by gross revenue

* **Converted SQL failed to run on Snowflake** (`execution_error`)
* 002043 (02000): Binder Error: No function matches the given name and argument types '+(VARCHAR, STRING_LITERAL)'. You might need to add explicit type casts. Candidate functions: +(TINYINT) -> TINYINT +(TINYINT, TINYINT) -> TINYINT +(SMALLINT) -> SMALLINT +(SMALLINT, SMALLINT) -> SMALLINT +(INTEGER) 

### Rule based baseline (sqlglot) · Q02 Shipped orders per month, first half of 2025

* **Different number of rows** (`row_count_mismatch`)
* expected 6 rows, got 1
* missing rows: [['2025-01', 2.0, 14.0, 5.0], ['2025-02', 1.0, 0.0, 10.0], ['2025-03', 2.0, 12.0, 0.0]]  
  unexpected rows: [[None, 9.0, 160.0, 20.0]]

### Rule based baseline (sqlglot) · Q03 Basket statistics per product category

* **Same shape, different values** (`value_mismatch`)
* 8 of 15 cells differ (columns: avg_line_quantity, avg_price_whole, avg_units_per_order)
* row 1, `avg_units_per_order`: expected `1.0`, got `1.6`
* row 1, `avg_line_quantity`: expected `1.0`, got `1.3333333333333333`
* row 1, `avg_price_whole`: expected `188.0`, got `189.0`
* row 2, `avg_units_per_order`: expected `24.0`, got `24.166666666666668`

### Rule based baseline (sqlglot) · Q04 Most recent order for each customer

* **Uses a construct real Snowflake rejects (emulator would accept it)** (`snowflake_restriction`)
* LIMIT inside a correlated LATERAL subquery: Snowflake allows LIMIT / FETCH only in uncorrelated scalar subqueries (docs: Working with Subqueries)

### Rule based baseline (sqlglot) · Q05 Contact data quality check for London customers

* **Different number of rows** (`row_count_mismatch`)
* expected 3 rows, got 1
* missing rows: [[1.0, 'Acme Ltd', 8.0, 5.0, 'acme.co.uk', 'ok'], [2.0, 'Brightway  ', 9.0, 6.0, 'brightway.com', 'missing'], [4.0, 'Delta Retail', 12.0, 4.0, 'delta.io', 'ok']]  
  unexpected rows: [[2.0, 'Brightway  ', 11.0, 6.0, 'brightway.com', 'missing']]

### Rule based baseline (sqlglot) · Q06 Second page (rows 6 to 10) of orders ranked by net value

* **Converted SQL failed to run on Snowflake** (`execution_error`)
* 002043 (02000): Binder Error: Referenced column "ROWNUM" not found in FROM clause! Candidate bindings: "NET_VALUE" LINE 1: ... ORDER BY NET_VALUE DESC NULLS FIRST, O.ORDER_ID) AS A WHERE ROWNUM <= 10) WHERE RN > 5 ORDER BY RN ^

### Rule based baseline (sqlglot) · Q07 Organisation chart with reporting paths

* **Converted SQL failed to run on Snowflake** (`execution_error`)
* 001003 (42000): Invalid expression / Unexpected token. Line 11, Col: 5. me AS top_manager FROM employees START WITH manager_id IS NULL CONNECT BY PRIOR emp_id = manager_id ORDER SIBLINGS BY emp_name

### Rule based baseline (sqlglot) · Q08 Product sales ranked within category (including unsold products)

* **Not verifiable on the local emulator** (`not_verifiable_locally`)
* local run differs (expected 7 rows, got 6); Oracle style (+) outer join: valid in Snowflake, but the emulator treats it as an inner join. Rerun against a real Snowflake account to verify.
* missing rows: [['Equipment', 'Forklift Battery', 0.0, 0.0, 'Never sold', 3.0]]  
  unexpected rows: []

## Are the checks strong enough? (negative controls)

10 of 10 deliberately injected migration bugs were detected.

| Injected bug | Query | Detected as |
|---|---|---|
| T-SQL integer division left as decimal division | Q03 | value_mismatch |
| CAST to INT rounds in Snowflake instead of truncating | Q03 | value_mismatch |
| case insensitive collation lost | Q05 | row_count_mismatch |
| LEN replaced by LENGTH without RTRIM | Q05 | value_mismatch |
| 'Shipped' no longer matches after migration | Q02 | value_mismatch |
| (+) outer join converted to an inner join | Q08 | row_count_mismatch |
| row limit changed | Q01 | row_count_mismatch |
| ORDER SIBLINGS BY emulated with the wrong sort | Q07 | row_order_mismatch |
| off by one page boundary when replacing ROWNUM | Q06 | value_mismatch |
| CROSS APPLY converted as OUTER APPLY (keeps customers without orders) | Q04 | row_count_mismatch |

## Method and limitations

* **Legacy side:** expected outputs in `expected/` come from `harness/legacy_reference.py`, a reimplementation of each query using the source engine's documented semantics. `harness/capture_legacy.py` replaces them with real SQL Server / Oracle output when a database is available.
* **Snowflake side:** converted SQL runs on fakesnow (local Snowflake emulator on DuckDB).
* **Documentation:** 8 of 8 generated docs contain all required sections.
* **Emulator shims** (no op on real Snowflake, applied to both converters): Q02: TO_CHAR(o.order_date, ...) input cast to DATE; Q06: TO_CHAR(o.order_date, ...) input cast to DATE.
* **Not verifiable locally:** valid Snowflake syntax the emulator cannot run faithfully; excluded from the accuracy denominator until checked on a real account.
