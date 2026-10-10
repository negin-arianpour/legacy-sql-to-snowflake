import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converter.common import REPORTS_DIR, load_queries  # noqa: E402
from harness.compare import compare_query, save_results  # noqa: E402
from harness.snowflake_runner import snowflake_session  # noqa: E402

QUERIES = load_queries()
_RESULTS = {}


@pytest.fixture(scope="session")
def snowflake_conn():
    with snowflake_session() as conn:
        yield conn


@pytest.fixture
def comparison(snowflake_conn, converter, query):
    """Run the converted query once and cache the comparison for all checks."""
    key = (converter, query.qid)
    if key not in _RESULTS:
        _RESULTS[key] = compare_query(snowflake_conn, converter, query)
    result = _RESULTS[key]
    if result.passed is None:
        pytest.skip(f"not verifiable locally: {'; '.join(result.emulator_gaps)}")
    return result


def pytest_sessionfinish(session, exitstatus):
    if _RESULTS:
        ordered = [_RESULTS[k] for k in sorted(_RESULTS)]
        save_results(ordered, REPORTS_DIR / "results.json")
