"""Automated equivalence checks: legacy expected output vs converted Snowflake output.

Each converter x query pair runs five checks, from coarse to fine. A pair counts as
an accurate conversion only when all of them pass.
"""

import pytest

from converter.common import CONVERTERS, DOCS_DIR
from tests.conftest import QUERIES

# Baseline pairs carry a marker: they are expected to fail and serve as evidence that
# the checks catch real errors. `pytest -m "not baseline"` is the CI gate for the LLM output.
pairs = pytest.mark.parametrize(
    "converter,query",
    [pytest.param(c, q, marks=[getattr(pytest.mark, c)], id=f"{c}-{q.qid}")
     for c in CONVERTERS for q in QUERIES],
)


def _detail(c):
    lines = [f"[{c.category}] {c.message}"]
    for d in c.diffs[:5]:
        lines.append(f"    {d}")
    return "\n".join(lines)


@pairs
def test_executes_on_snowflake(comparison):
    assert comparison.category not in ("execution_error", "snowflake_restriction"), _detail(comparison)


@pairs
def test_same_columns(comparison):
    if comparison.category in ("execution_error", "snowflake_restriction"):
        pytest.skip("query did not run")
    assert comparison.category not in ("column_count_mismatch", "column_name_mismatch"), _detail(comparison)


@pairs
def test_same_row_count(comparison):
    if comparison.category in ("execution_error", "snowflake_restriction",
                               "column_count_mismatch", "column_name_mismatch"):
        pytest.skip("earlier check failed")
    assert comparison.category != "row_count_mismatch", _detail(comparison)


@pairs
def test_same_values(comparison):
    if comparison.category in ("execution_error", "snowflake_restriction", "column_count_mismatch",
                               "column_name_mismatch", "row_count_mismatch"):
        pytest.skip("earlier check failed")
    assert comparison.category != "value_mismatch", _detail(comparison)


@pairs
def test_same_row_order(comparison, query):
    if not query.ordered:
        pytest.skip("query has no ORDER BY")
    if comparison.category not in (None, "row_order_mismatch"):
        pytest.skip("earlier check failed")
    assert comparison.category != "row_order_mismatch", _detail(comparison)


@pytest.mark.parametrize("query", QUERIES, ids=[q.qid for q in QUERIES])
def test_llm_documentation_generated(query):
    doc = DOCS_DIR / f"{query.name}.md"
    assert doc.exists(), "documentation file missing"
    text = doc.read_text()
    for section in ("Purpose", "Logic", "Output columns", "Conversion notes"):
        assert f"## {section}" in text, f"documentation lacks a '{section}' section"
