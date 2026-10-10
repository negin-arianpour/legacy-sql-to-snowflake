"""Compare a converted query's result set with the legacy expected output."""

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from converter.common import EXPECTED_DIR, LegacyQuery, converted_path
from harness.snowflake_runner import emulator_gaps, run_query, snowflake_restrictions

NUM_TOLERANCE = 1e-6

# Ordered from most to least severe; the first failing check names the category.
CATEGORIES = {
    "execution_error": "Converted SQL failed to run on Snowflake",
    "snowflake_restriction": "Uses a construct real Snowflake rejects (emulator would accept it)",
    "column_count_mismatch": "Different number of output columns",
    "column_name_mismatch": "Output column names differ",
    "row_count_mismatch": "Different number of rows",
    "row_order_mismatch": "Same rows, different order (query has ORDER BY)",
    "value_mismatch": "Same shape, different values",
}
# Not a conversion error: valid Snowflake the local emulator cannot run faithfully.
INCONCLUSIVE = "not_verifiable_locally"


@dataclass
class Comparison:
    converter: str
    qid: str
    name: str
    dialect: str
    title: str
    passed: bool | None          # None = inconclusive (emulator gap)
    category: str | None = None
    message: str = ""
    expected_rows: int = 0
    actual_rows: int | None = None
    cells_checked: int = 0
    cells_matching: int = 0
    diffs: list = field(default_factory=list)
    emulator_shims: list = field(default_factory=list)
    emulator_gaps: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def load_expected(q: LegacyQuery):
    data = json.loads((EXPECTED_DIR / f"{q.qid}.json").read_text())
    return data["columns"], data["rows"]


def _norm(v):
    """Normalise a value for comparison across engines and drivers."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, str):
        try:  # expected JSON stores decimals as strings, e.g. "592.75"
            if v.strip() and v.strip().lstrip("-").replace(".", "", 1).isdigit():
                return float(v)
        except ValueError:
            pass
        return v
    return str(v)


def _equal(a, b) -> bool:
    a, b = _norm(a), _norm(b)
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=NUM_TOLERANCE, abs_tol=NUM_TOLERANCE)
    return a == b


def _sort_key(row):
    return [(_norm(v) is None, str(_norm(v))) for v in row]


def compare_rows(exp_cols, exp_rows, act_cols, act_rows, ordered: bool):
    """Returns (category or None, message, cells_checked, cells_matching, diffs)."""
    if len(exp_cols) != len(act_cols):
        return ("column_count_mismatch",
                f"expected {len(exp_cols)} columns {exp_cols}, got {len(act_cols)} {act_cols}", 0, 0, [])
    if [c.lower() for c in exp_cols] != [c.lower() for c in act_cols]:
        return "column_name_mismatch", f"expected {exp_cols}, got {act_cols}", 0, 0, []

    if len(exp_rows) != len(act_rows):
        def key(r):
            return tuple(str(round(n, 6)) if isinstance(n := _norm(v), float) else str(n) for v in r)
        act_keys, exp_keys = {key(r) for r in act_rows}, {key(r) for r in exp_rows}
        missing = [[_norm(v) for v in r] for r in exp_rows if key(r) not in act_keys][:3]
        extra = [[_norm(v) for v in r] for r in act_rows if key(r) not in exp_keys][:3]
        return ("row_count_mismatch",
                f"expected {len(exp_rows)} rows, got {len(act_rows)}",
                0, 0, [{"missing_rows": missing, "unexpected_rows": extra}])

    def cell_diffs(e_rows, a_rows):
        diffs, matching = [], 0
        for i, (er, ar) in enumerate(zip(e_rows, a_rows)):
            for col, ev, av in zip(exp_cols, er, ar):
                if _equal(ev, av):
                    matching += 1
                else:
                    diffs.append({"row": i + 1, "column": col, "expected": _norm(ev), "actual": _norm(av)})
        return diffs, matching

    cells = len(exp_rows) * len(exp_cols)
    diffs, matching = cell_diffs(exp_rows, act_rows)
    if not diffs:
        return None, "identical", cells, matching, []

    sorted_diffs, sorted_matching = cell_diffs(sorted(exp_rows, key=_sort_key), sorted(act_rows, key=_sort_key))
    if not sorted_diffs:
        if ordered:
            return "row_order_mismatch", "same rows in a different order", cells, matching, diffs[:10]
        return None, "identical (order not significant)", cells, cells, []

    cols = sorted({d["column"] for d in sorted_diffs})
    return ("value_mismatch", f"{len(sorted_diffs)} of {cells} cells differ (columns: {', '.join(cols)})",
            cells, sorted_matching, sorted_diffs[:10])


def compare_query(conn, converter: str, q: LegacyQuery) -> Comparison:
    exp_cols, exp_rows = load_expected(q)
    result = Comparison(converter=converter, qid=q.qid, name=q.name, dialect=q.dialect,
                        title=q.title, passed=False, expected_rows=len(exp_rows))
    sql = converted_path(converter, q).read_text()
    if "TRANSPILE ERROR" in sql:
        result.category = "execution_error"
        result.message = sql.splitlines()[1].lstrip("- ")
        return result
    restrictions = snowflake_restrictions(sql)
    if restrictions:
        result.category, result.message = "snowflake_restriction", "; ".join(restrictions)
        return result
    try:
        act_cols, act_rows, result.emulator_shims = run_query(conn, sql)
    except Exception as exc:
        result.category = "execution_error"
        result.message = " ".join(str(exc).split())[:300]
        return result

    result.actual_rows = len(act_rows)
    category, message, checked, matching, diffs = compare_rows(exp_cols, exp_rows, act_cols, act_rows, q.ordered)
    result.category, result.message, result.diffs = category, message, diffs
    result.cells_checked, result.cells_matching = checked, matching
    result.passed = category is None
    result.emulator_gaps = emulator_gaps(sql)
    if not result.passed and result.emulator_gaps:
        result.passed, result.category = None, INCONCLUSIVE
        result.message = (f"local run differs ({message}); " + "; ".join(result.emulator_gaps)
                          + ". Rerun against a real Snowflake account to verify.")
    return result


def save_results(results: list[Comparison], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps([r.to_dict() for r in results], indent=2, default=str))
