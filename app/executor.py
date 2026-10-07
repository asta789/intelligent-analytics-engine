from __future__ import annotations

import duckdb
import pandas as pd

from .sql_safety import validate_sql


class QueryExecutor:
    def __init__(self, tables: dict[str, pd.DataFrame]):
        self.tables = tables
        self.conn = duckdb.connect(database=":memory:")
        for name, df in tables.items():
            self.conn.register(name, df)

    def execute(self, sql: str) -> list[dict]:
        sql = validate_sql(sql, set(self.tables))
        result = self.conn.execute(sql).fetchdf()
        # JSON-safe output, including timestamps and numpy scalars.
        # Cast first so pandas does not retain NaN in numeric columns when
        # replacing SQL NULLs with JSON-safe None values.
        result = result.astype(object).where(pd.notnull(result), None)
        return result.to_dict(orient="records")
