"""Run converted Snowflake SQL against the sample data.

Uses fakesnow, which patches the official snowflake-connector-python so that
queries execute locally (on DuckDB) with Snowflake syntax and semantics. To run
against a real Snowflake account instead, set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER,
SNOWFLAKE_PASSWORD, SNOWFLAKE_WAREHOUSE (and optionally SNOWFLAKE_DATABASE /
SNOWFLAKE_SCHEMA): the same code path is used with a real connection.
"""

import os
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data"))
from sample_data import ROWS, SCHEMA  # noqa: E402

import snowflake.connector  # noqa: E402

DB, SCHEMA_NAME = os.environ.get("SNOWFLAKE_DATABASE", "MIGRATION_TEST"), os.environ.get("SNOWFLAKE_SCHEMA", "SAMPLE")


def using_real_snowflake() -> bool:
    return bool(os.environ.get("SNOWFLAKE_ACCOUNT"))


def _load_sample_data(conn) -> None:
    cur = conn.cursor()
    for table, cols in SCHEMA.items():
        cur.execute(f"CREATE OR REPLACE TABLE {table} ({', '.join(f'{c} {t}' for c, t in cols)})")
        placeholders = ", ".join(["%s"] * len(cols))
        cur.executemany(f"INSERT INTO {table} VALUES ({placeholders})", ROWS[table])
    cur.close()


@contextmanager
def snowflake_session():
    """Yield a connection with the sample data loaded."""
    if using_real_snowflake():
        conn = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
            password=os.environ["SNOWFLAKE_PASSWORD"], warehouse=os.environ["SNOWFLAKE_WAREHOUSE"])
        conn.cursor().execute(f"CREATE DATABASE IF NOT EXISTS {DB}")
        conn.cursor().execute(f"CREATE SCHEMA IF NOT EXISTS {DB}.{SCHEMA_NAME}")
        conn.cursor().execute(f"USE SCHEMA {DB}.{SCHEMA_NAME}")
        try:
            _load_sample_data(conn)
            yield conn
        finally:
            conn.close()
        return

    import fakesnow

    with fakesnow.patch():
        conn = snowflake.connector.connect(database=DB, schema=SCHEMA_NAME)
        try:
            _load_sample_data(conn)
            yield conn
        finally:
            conn.close()


DATE_COLUMNS = {c for cols in SCHEMA.values() for c, t in cols if t == "DATE"}


def emulator_shims(sql: str) -> tuple[str, list[str]]:
    """Work around known fakesnow gaps without changing Snowflake semantics.

    fakesnow drops the format argument of TO_CHAR / TO_VARCHAR unless it can see that
    the input is a date, so TO_CHAR(order_date, 'YYYY-MM') would return '2025-01-03'.
    Wrapping a DATE column in CAST(... AS DATE) is a no op on real Snowflake and lets
    the emulator apply the format. Shims are applied identically to every converter
    and are listed in the report. Nothing is changed when running on real Snowflake.
    """
    if using_real_snowflake():
        return sql, []
    import sqlglot
    from sqlglot import exp

    try:
        tree = sqlglot.parse_one(sql, read="snowflake")
    except Exception:
        return sql, []
    applied = []
    for node in list(tree.find_all(exp.ToChar)):
        target = node.this
        if node.args.get("format") is not None and isinstance(target, exp.Column) \
                and target.name.lower() in DATE_COLUMNS:
            target.replace(exp.Cast(this=target.copy(), to=exp.DataType.build("DATE")))
            applied.append(f"TO_CHAR({target.sql('snowflake')}, ...) input cast to DATE")
    if not applied:
        return sql, []
    return tree.sql("snowflake"), applied


# Valid Snowflake syntax that the local emulator cannot execute faithfully. A query
# using one of these and failing locally is reported as "not verifiable locally"
# rather than as a conversion error.
EMULATOR_GAPS = {
    "(+)": "Oracle style (+) outer join: valid in Snowflake, but the emulator treats it as an inner join",
}


def emulator_gaps(sql: str) -> list[str]:
    if using_real_snowflake():
        return []
    compact = "".join(sql.split())
    return [reason for token, reason in EMULATOR_GAPS.items() if token in compact]


# Real Snowflake restrictions the emulator does not enforce. A query that the emulator
# runs happily may still be rejected by Snowflake, so these are checked statically.
def snowflake_restrictions(sql: str) -> list[str]:
    if using_real_snowflake():
        return []  # the real engine enforces its own rules
    import sqlglot
    from sqlglot import exp

    try:
        tree = sqlglot.parse_one(sql, read="snowflake")
    except Exception:
        return []
    found = []
    for lateral in tree.find_all(exp.Lateral):
        if lateral.find(exp.Limit):
            found.append("LIMIT inside a correlated LATERAL subquery: Snowflake allows LIMIT / FETCH "
                         "only in uncorrelated scalar subqueries (docs: Working with Subqueries)")
    return found


def run_query(conn, sql: str):
    """Execute one query; returns (column names, rows, emulator shims applied)."""
    statement, shims = emulator_shims(sql.strip().rstrip(";"))
    cur = conn.cursor()
    try:
        cur.execute(statement)
        columns = [d[0] for d in cur.description]
        return columns, [list(r) for r in cur.fetchall()], shims
    finally:
        cur.close()
