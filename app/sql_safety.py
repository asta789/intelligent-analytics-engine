from __future__ import annotations

import re

import sqlglot
from sqlglot import exp


class UnsafeSQL(ValueError):
    pass


FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|COPY|ATTACH|DETACH|INSTALL|LOAD|PRAGMA|CALL|EXPORT|IMPORT|VACUUM|TRUNCATE|REPLACE)\b",
    re.I,
)


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise UnsafeSQL("Empty SQL")
    if ";" in sql:
        raise UnsafeSQL("Multiple SQL statements are not allowed")
    if not re.match(r"^(SELECT|WITH)\b", sql, re.I):
        raise UnsafeSQL("Only SELECT/WITH queries are allowed")
    if FORBIDDEN.search(sql):
        raise UnsafeSQL("SQL contains a forbidden operation")

    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except sqlglot.ParseError as exc:
        raise UnsafeSQL(f"Invalid SQL: {exc}") from exc

    # Inspect actual Table expressions so column names such as order_date are
    # never mistaken for relations. CTE names are local query objects.
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    referenced = {
        table.name.lower()
        for table in tree.find_all(exp.Table)
        if table.name and table.name.lower() not in ctes
    }
    visible = {x.lower() for x in allowed_tables}
    unknown = referenced - visible
    if unknown:
        raise UnsafeSQL(f"Unknown tables referenced: {sorted(unknown)}")
    return sql
