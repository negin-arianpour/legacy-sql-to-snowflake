"""Capture expected outputs from a real SQL Server and/or Oracle database.

This replaces the reference implementation (harness/legacy_reference.py) with the
real engines' output, so the tests compare against true legacy behaviour.

    pip install pyodbc oracledb
    export MSSQL_CONN="DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;UID=sa;PWD=...;TrustServerCertificate=yes"
    export ORACLE_DSN="localhost/FREEPDB1" ORACLE_USER=... ORACLE_PASSWORD=...
    python -m harness.capture_legacy

Quick local engines with Docker:
    docker run -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=... -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
    docker run -e ORACLE_PASSWORD=... -p 1521:1521 gvenzl/oracle-free:slim

Not run in the original build environment (no database engines were reachable);
the reference implementation was used instead.
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))

from converter.common import EXPECTED_DIR, load_queries  # noqa: E402
from sample_data import ROWS, SCHEMA  # noqa: E402

ORACLE_TYPES = {"INTEGER": "NUMBER(10)", "DATE": "DATE"}


def _json(v):
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "isoformat"):
        # Oracle DATE comes back as datetime; the sample data has no time part
        return v.date().isoformat() if hasattr(v, "date") and v.hour == v.minute == v.second == 0 else v.isoformat()
    return v


def _load(conn, dialect):
    cur = conn.cursor()
    for table, cols in SCHEMA.items():
        drop = (f"IF OBJECT_ID('{table}') IS NOT NULL DROP TABLE {table}" if dialect == "tsql" else
                f"BEGIN EXECUTE IMMEDIATE 'DROP TABLE {table}'; EXCEPTION WHEN OTHERS THEN NULL; END;")
        cur.execute(drop)
        defs = ", ".join(f"{c} {ORACLE_TYPES.get(t, t.replace('VARCHAR', 'VARCHAR2')) if dialect == 'oracle' else t}"
                         for c, t in cols)
        cur.execute(f"CREATE TABLE {table} ({defs})")
        marks = ", ".join(["?"] * len(cols)) if dialect == "tsql" else \
            ", ".join(f":{i + 1}" for i in range(len(cols)))
        cur.executemany(f"INSERT INTO {table} VALUES ({marks})", ROWS[table])
    conn.commit()


def _connect(dialect):
    if dialect == "tsql" and os.environ.get("MSSQL_CONN"):
        import pyodbc
        return pyodbc.connect(os.environ["MSSQL_CONN"])
    if dialect == "oracle" and os.environ.get("ORACLE_DSN"):
        import oracledb
        return oracledb.connect(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"],
                                dsn=os.environ["ORACLE_DSN"])
    return None


def main():
    queries = load_queries()
    for dialect in ("tsql", "oracle"):
        conn = _connect(dialect)
        if conn is None:
            print(f"skipping {dialect}: connection settings not provided")
            continue
        _load(conn, dialect)
        cur = conn.cursor()
        for q in [q for q in queries if q.dialect == dialect]:
            cur.execute(q.body.rstrip().rstrip(";"))
            columns = [d[0].lower() for d in cur.description]
            rows = [[_json(v) for v in r] for r in cur.fetchall()]
            (EXPECTED_DIR / f"{q.qid}.json").write_text(json.dumps(
                {"source": f"captured from real {dialect} engine", "columns": columns, "rows": rows}, indent=2))
            print(f"captured {q.name}: {len(rows)} rows")
        conn.close()


if __name__ == "__main__":
    main()
