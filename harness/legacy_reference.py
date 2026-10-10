"""Expected output of each legacy query, computed with the source engine's semantics.

Neither SQL Server nor Oracle can run in this environment, so each legacy query is
reimplemented here in plain Python, following the documented behaviour of the
source engine (integer division, collation, LEN, CAST truncation, ROUND half away
from zero, CONNECT BY ordering ...). The results are written to expected/*.json
and act as the "legacy side" of every comparison.

When a real SQL Server or Oracle instance is available, run
harness/capture_legacy.py instead: it executes the original .sql files and
overwrites the same JSON files, so the tests then compare against the real engine.
"""

import json
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data"))
from sample_data import ROWS, SCHEMA  # noqa: E402

EXPECTED_DIR = ROOT / "expected"


def table(name):
    cols = [c for c, _ in SCHEMA[name]]
    return [dict(zip(cols, r)) for r in ROWS[name]]


customers, products, orders = table("customers"), table("products"), table("orders")
order_items, employees = table("order_items"), table("employees")
cust_by_id = {c["customer_id"]: c for c in customers}
prod_by_id = {p["product_id"]: p for p in products}
order_by_id = {o["order_id"]: o for o in orders}


# --- source engine semantics -------------------------------------------------

def tsql_eq(a, b):
    """SQL Server default collation (SQL_Latin1_General_CP1_CI_AS): case insensitive,
    trailing spaces ignored. NULL never matches."""
    if a is None or b is None:
        return False
    return a.rstrip().casefold() == b.rstrip().casefold()


def tsql_len(s):
    return None if s is None else len(s.rstrip())


def tsql_int_div(a, b):
    return int(a / b)  # truncates toward zero, like T-SQL int / int


def tsql_concat(*parts):
    return None if any(p is None for p in parts) else "".join(parts)


def tsql_charindex(sub, s):
    return None if s is None else s.find(sub) + 1


def oracle_round(x, places):
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


# --- queries -----------------------------------------------------------------

def q01():
    agg = defaultdict(lambda: {"rev": Decimal(0), "orders": set()})
    for oi in order_items:
        o = order_by_id[oi["order_id"]]
        if tsql_eq(o["status"], "CANCELLED"):
            continue
        a = agg[o["customer_id"]]
        a["rev"] += oi["quantity"] * oi["unit_price"]
        a["orders"].add(o["order_id"])
    rows = []
    for cid, a in agg.items():
        c = cust_by_id[cid]
        rows.append([cid, tsql_concat(c["name"], " (", c["city"], ")"),
                     c["email"] if c["email"] is not None else "n/a",
                     a["rev"], len(a["orders"])])
    rows.sort(key=lambda r: r[3], reverse=True)
    return ["customer_id", "customer_label", "contact_email", "gross_revenue", "order_count"], rows[:5]


def q02():
    from datetime import date
    groups = defaultdict(list)
    for o in orders:
        if tsql_eq(o["status"], "SHIPPED") and date(2025, 1, 1) <= o["order_date"] < date(2025, 7, 1):
            groups[o["order_date"].strftime("%Y-%m")].append(o)
    rows = []
    for month in sorted(groups):
        g = groups[month]
        dates = [o["order_date"] for o in g]
        rows.append([month, len(g), (max(dates) - min(dates)).days,
                     sum(o["discount_pct"] or 0 for o in g)])
    return ["order_month", "orders_shipped", "span_days", "total_discount_pct"], rows


def q03():
    groups = defaultdict(list)
    for oi in order_items:
        groups[prod_by_id[oi["product_id"]]["category"]].append(oi)
    rows = []
    for cat in sorted(groups):
        g = groups[cat]
        n_orders = len({oi["order_id"] for oi in g})
        qty = [oi["quantity"] for oi in g]
        avg_price = sum(oi["unit_price"] for oi in g) / len(g)
        rows.append([cat, n_orders,
                     tsql_int_div(sum(qty), n_orders),    # int / int
                     tsql_int_div(sum(qty), len(qty)),    # AVG(int) is integer
                     int(avg_price)])                     # CAST(... AS INT) truncates
    return ["category", "orders_with_category", "avg_units_per_order",
            "avg_line_quantity", "avg_price_whole"], rows


def q04():
    rows = []
    for c in sorted(customers, key=lambda c: c["customer_id"]):
        mine = [o for o in orders if o["customer_id"] == c["customer_id"]]
        if not mine:
            continue  # CROSS APPLY drops customers with no match
        lo = max(mine, key=lambda o: (o["order_date"], o["order_id"]))
        rows.append([c["customer_id"], c["name"], lo["order_id"], lo["order_date"], lo["status"]])
    return ["customer_id", "name", "order_id", "order_date", "status"], rows


def q05():
    rows = []
    for c in sorted(customers, key=lambda c: c["customer_id"]):
        if not tsql_eq(c["city"], "london"):
            continue
        email = c["email"]
        at = tsql_charindex("@", email)
        domain = None if email is None else email[at:at + tsql_len(email)]
        rows.append([c["customer_id"], c["name"], tsql_len(c["name"]), at, domain,
                     "missing" if c["phone"] is None else "ok"])
    return ["customer_id", "name", "name_length", "at_position", "email_domain", "phone_status"], rows


def q06():
    decode = {"SHIPPED": "Done", "PENDING": "Waiting"}  # Oracle DECODE is case sensitive
    totals = defaultdict(Decimal)
    for oi in order_items:
        totals[oi["order_id"]] += oi["quantity"] * oi["unit_price"]
    ranked = []
    for oid, total in totals.items():
        o = order_by_id[oid]
        disc = Decimal(o["discount_pct"] or 0)
        ranked.append([oid, cust_by_id[o["customer_id"]]["name"], o["order_date"].strftime("%Y-%m"),
                       decode.get(o["status"], "Other"),
                       oracle_round(total * (1 - disc / 100), 2)])
    ranked.sort(key=lambda r: (-r[4], r[0]))
    rows = [r + [i] for i, r in enumerate(ranked, start=1) if 5 < i <= 10]
    return ["order_id", "customer_name", "order_month", "status_label", "net_value", "rn"], rows


def q07():
    children = defaultdict(list)
    for e in employees:
        children[e["manager_id"]].append(e)
    rows = []

    def walk(e, depth, path, root):
        path = f"{path}/{e['emp_name']}"
        rows.append([e["emp_id"], e["emp_name"], depth, path, root])
        for child in sorted(children[e["emp_id"]], key=lambda x: x["emp_name"]):
            walk(child, depth + 1, path, root)

    for root in sorted(children[None], key=lambda x: x["emp_name"]):  # ORDER SIBLINGS BY
        walk(root, 1, "", root["emp_name"])
    return ["emp_id", "emp_name", "depth", "reporting_path", "top_manager"], rows


def q08():
    stats = {}
    for p in products:
        lines = [oi for oi in order_items if oi["product_id"] == p["product_id"]]
        stats[(p["category"], p["product_name"])] = (
            sum(oi["quantity"] for oi in lines),
            sum((oi["quantity"] * oi["unit_price"] for oi in lines), Decimal(0)),
            "Active" if lines else "Never sold",
        )
    rows = []
    by_cat = defaultdict(list)
    for (cat, name), s in stats.items():
        by_cat[cat].append((name, *s))
    for cat in sorted(by_cat):
        items = by_cat[cat]
        for name, units, rev, status in items:
            rank = 1 + sum(1 for other in items if other[2] > rev)
            rows.append([cat, name, units, rev, status, rank])
    rows.sort(key=lambda r: (r[0], r[5], r[1]))
    return ["category", "product_name", "units_sold", "revenue", "sales_status", "category_rank"], rows


QUERIES = {f"q0{i}": f for i, f in enumerate([q01, q02, q03, q04, q05, q06, q07, q08], start=1)}


def to_json_value(v):
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def build_all():
    EXPECTED_DIR.mkdir(exist_ok=True)
    for qid, fn in QUERIES.items():
        columns, rows = fn()
        payload = {"source": "reference implementation of legacy semantics (harness/legacy_reference.py)",
                   "columns": columns,
                   "rows": [[to_json_value(v) for v in r] for r in rows]}
        (EXPECTED_DIR / f"{qid}.json").write_text(json.dumps(payload, indent=2))
        print(f"expected/{qid}.json  {len(rows)} rows")


if __name__ == "__main__":
    build_all()
