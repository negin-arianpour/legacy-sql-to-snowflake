"""Negative controls: prove the checks catch realistic migration mistakes.

Each mutation reintroduces a classic dialect bug into a conversion that is known to
pass. The comparison must fail with the expected category; if a mutation slipped
through, the test suite would be too weak to trust its green results.
"""

import json

import pytest

from converter.common import REPORTS_DIR, converted_path, load_queries
from harness.compare import compare_rows, load_expected
from harness.snowflake_runner import run_query

QUERIES = {q.qid: q for q in load_queries()}

MUTATIONS = [
    # (id, query, find, replace, expected category, what it simulates)
    ("int-division", "q03", "CAST(TRUNC(SUM(oi.quantity) / COUNT(DISTINCT oi.order_id)) AS INT)",
     "SUM(oi.quantity) / COUNT(DISTINCT oi.order_id)", "value_mismatch",
     "T-SQL integer division left as decimal division"),
    ("cast-rounding", "q03", "CAST(TRUNC(AVG(oi.unit_price)) AS INT)", "CAST(AVG(oi.unit_price) AS INT)",
     "value_mismatch", "CAST to INT rounds in Snowflake instead of truncating"),
    ("collation", "q05", "LOWER(c.city) = 'london'", "c.city = 'london'", "row_count_mismatch",
     "case insensitive collation lost"),
    ("len-trailing-spaces", "q05", "LENGTH(RTRIM(c.name))", "LENGTH(c.name)", "value_mismatch",
     "LEN replaced by LENGTH without RTRIM"),
    ("status-case", "q02", "UPPER(o.status) = 'SHIPPED'", "o.status = 'SHIPPED'", "value_mismatch",
     "'Shipped' no longer matches after migration"),
    ("outer-join-lost", "q08", "LEFT JOIN", "JOIN", "row_count_mismatch",
     "(+) outer join converted to an inner join"),
    ("top-n", "q01", "LIMIT 5", "LIMIT 6", "row_count_mismatch", "row limit changed"),
    ("sibling-order", "q07", "ORDER BY reporting_path", "ORDER BY depth, emp_name", "row_order_mismatch",
     "ORDER SIBLINGS BY emulated with the wrong sort"),
    ("pagination-offset", "q06", "BETWEEN 6 AND 10", "BETWEEN 5 AND 9", "value_mismatch",
     "off by one page boundary when replacing ROWNUM"),
    ("cross-apply-as-outer", "q04", "JOIN orders o ON o.customer_id = c.customer_id",
     "LEFT JOIN orders o ON o.customer_id = c.customer_id", "row_count_mismatch",
     "CROSS APPLY converted as OUTER APPLY (keeps customers without orders)"),
]

_OUTCOMES = []


@pytest.mark.parametrize("mid,qid,find,replace,expected,description", MUTATIONS,
                         ids=[m[0] for m in MUTATIONS])
def test_mutation_is_detected(snowflake_conn, mid, qid, find, replace, expected, description):
    q = QUERIES[qid]
    sql = converted_path("llm", q).read_text()
    assert find in sql, f"mutation anchor not found in {q.name}"
    mutated = sql.replace(find, replace, 1)

    exp_cols, exp_rows = load_expected(q)
    act_cols, act_rows, _ = run_query(snowflake_conn, mutated)
    category, message, *_ = compare_rows(exp_cols, exp_rows, act_cols, act_rows, q.ordered)

    _OUTCOMES.append({"id": mid, "query": qid, "simulates": description,
                      "expected_category": expected, "detected_as": category, "message": message})
    (REPORTS_DIR / "mutations.json").write_text(json.dumps(_OUTCOMES, indent=2))

    assert category is not None, f"mutation '{description}' was NOT detected"
    assert category == expected, f"detected, but as {category} instead of {expected}"
