"""Deterministic sample dataset shared by the legacy reference and the Snowflake run.

The data is small on purpose, but it contains the edge cases that typically
break a dialect migration:

* trailing spaces in names           (T-SQL LEN ignores them, Snowflake LENGTH does not)
* mixed case values ('London', 'london', 'LONDON', 'Shipped')
                                      (SQL Server default collation is case insensitive,
                                       Snowflake comparisons are case sensitive)
* NULL city / email / phone / discount (NULL concatenation and NVL/ISNULL handling)
* a customer with no orders            (CROSS APPLY vs outer joins)
* a product that was never sold        (Oracle (+) outer join)
* two orders on the same date          (deterministic tie breaking)
* integer quantities and decimal prices (T-SQL integer division / AVG / CAST truncation)
* two roots in the employee hierarchy  (CONNECT BY with START WITH)
"""

from datetime import date
from decimal import Decimal as D

SCHEMA = {
    "customers": [
        ("customer_id", "INTEGER"),
        ("name", "VARCHAR(50)"),
        ("city", "VARCHAR(30)"),
        ("email", "VARCHAR(80)"),
        ("phone", "VARCHAR(20)"),
        ("created_date", "DATE"),
    ],
    "products": [
        ("product_id", "INTEGER"),
        ("product_name", "VARCHAR(50)"),
        ("category", "VARCHAR(30)"),
        ("unit_price", "DECIMAL(10,2)"),
    ],
    "orders": [
        ("order_id", "INTEGER"),
        ("customer_id", "INTEGER"),
        ("order_date", "DATE"),
        ("status", "VARCHAR(20)"),
        ("discount_pct", "INTEGER"),
    ],
    "order_items": [
        ("order_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("quantity", "INTEGER"),
        ("unit_price", "DECIMAL(10,2)"),
    ],
    "employees": [
        ("emp_id", "INTEGER"),
        ("emp_name", "VARCHAR(50)"),
        ("manager_id", "INTEGER"),
        ("dept", "VARCHAR(20)"),
        ("salary", "INTEGER"),
        ("hire_date", "DATE"),
    ],
}

ROWS = {
    "customers": [
        (1, "Acme Ltd", "London", "info@acme.co.uk", "0201", date(2023, 1, 15)),
        (2, "Brightway  ", "london", "sales@brightway.com", None, date(2023, 3, 2)),
        (3, "Cobalt Freight", "Ipswich", None, "0147", date(2023, 5, 20)),
        (4, "Delta Retail", "LONDON", "ops@delta.io", "0203", date(2023, 7, 11)),
        (5, "Evergreen Co", None, "hello@evergreen.org", None, date(2024, 1, 5)),
        (6, "Fjord Logistics", "Felixstowe", "team@fjord.no", "0139", date(2024, 2, 14)),
        (7, "Granite Group  ", "Manchester", "admin@granite.com", "0161", date(2024, 4, 30)),
        (8, "Harbour Supplies", "Felixstowe", "contact@harbour.co.uk", "0139", date(2024, 6, 1)),
    ],
    "products": [
        (1, "Pallet Wrap", "Packaging", D("12.50")),
        (2, "Box Large", "Packaging", D("3.20")),
        (3, "Barcode Scanner", "Equipment", D("149.99")),
        (4, "Label Printer", "Equipment", D("229.00")),
        (5, "Hi-Vis Vest", "Safety", D("7.75")),
        (6, "Hard Hat", "Safety", D("18.40")),
        (7, "Forklift Battery", "Equipment", D("1850.00")),
    ],
    "orders": [
        (101, 1, date(2025, 1, 3), "SHIPPED", 0),
        (102, 2, date(2025, 1, 17), "SHIPPED", 5),
        (103, 1, date(2025, 2, 2), "PENDING", None),
        (104, 3, date(2025, 2, 14), "SHIPPED", 10),
        (105, 4, date(2025, 2, 28), "CANCELLED", 0),
        (106, 5, date(2025, 3, 9), "SHIPPED", None),
        (107, 6, date(2025, 3, 21), "SHIPPED", 0),
        (108, 1, date(2025, 4, 4), "SHIPPED", 0),
        (109, 7, date(2025, 4, 18), "PENDING", 0),
        (110, 2, date(2025, 5, 6), "SHIPPED", 5),
        (111, 4, date(2025, 5, 31), "SHIPPED", 0),
        (112, 6, date(2025, 6, 12), "RETURNED", 0),
        (113, 3, date(2025, 6, 30), "Shipped", 0),
        (114, 7, date(2025, 7, 15), "SHIPPED", 0),
        (115, 6, date(2025, 6, 12), "SHIPPED", 0),
    ],
    "order_items": [
        (101, 1, 10, D("12.50")), (101, 2, 25, D("3.20")),
        (102, 3, 1, D("149.99")), (102, 5, 4, D("7.75")),
        (103, 2, 40, D("3.20")),
        (104, 4, 1, D("229.00")), (104, 1, 6, D("12.50")),
        (105, 6, 3, D("18.40")),
        (106, 5, 40, D("7.75")), (106, 6, 2, D("18.40")),
        (107, 3, 2, D("149.99")), (107, 4, 1, D("229.00")),
        (108, 1, 15, D("12.50")),
        (109, 2, 30, D("3.20")), (109, 5, 5, D("7.75")),
        (110, 6, 7, D("18.40")),
        (111, 3, 1, D("145.00")),
        (112, 5, 3, D("7.75")),
        (113, 1, 8, D("12.50")), (113, 2, 11, D("3.20")),
        (114, 4, 2, D("229.00")),
        (115, 6, 1, D("18.40")),
    ],
    "employees": [
        (1, "Morgan Ellis", None, "Exec", 120000, date(2015, 3, 1)),
        (2, "Ava Patel", 1, "Ops", 85000, date(2016, 6, 13)),
        (3, "Ben Carter", 1, "Sales", 82000, date(2017, 9, 4)),
        (4, "Chloe Nguyen", 2, "Ops", 56000, date(2019, 1, 21)),
        (5, "Dan Okafor", 2, "Ops", 54000, date(2020, 5, 11)),
        (6, "Eve Rossi", 3, "Sales", 61000, date(2018, 11, 26)),
        (7, "Finn Walsh", 4, "Ops", 41000, date(2022, 2, 7)),
        (8, "Grace Kim", 6, "Sales", 43000, date(2023, 8, 14)),
        (9, "Zara Quinn", None, "Board", 95000, date(2014, 10, 1)),
        (10, "Iris Bell", 9, "Board", 47000, date(2021, 3, 29)),
    ],
}
