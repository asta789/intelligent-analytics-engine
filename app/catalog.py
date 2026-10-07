from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class ColumnInfo:
    name: str
    dtype: str
    sample_values: list[Any]
    nullable: bool
    temporal_coverage: str | None = None


@dataclass
class TableInfo:
    name: str
    row_count: int
    columns: list[ColumnInfo]


class Catalog:
    def __init__(self, tables: dict[str, pd.DataFrame], dictionary: dict[str, Any] | None = None):
        self.tables = tables
        self.dictionary = dictionary or {}
        self.table_info = {name: self._inspect(name, df) for name, df in tables.items()}

    @staticmethod
    def _inspect(name: str, df: pd.DataFrame) -> TableInfo:
        columns = []
        for c in df.columns:
            values = df[c].dropna().head(5).tolist()
            temporal_coverage = None
            if pd.api.types.is_datetime64_any_dtype(df[c]) and not df[c].dropna().empty:
                dates = df[c].dropna()
                years = sorted(dates.dt.year.unique().tolist())
                temporal_coverage = (
                    f"{dates.min().date()} through {dates.max().date()}; "
                    f"years={years}"
                )
            columns.append(
                ColumnInfo(c, str(df[c].dtype), values, bool(df[c].isna().any()), temporal_coverage)
            )
        return TableInfo(name, len(df), columns)

    def prompt_context(self) -> str:
        lines = ["AVAILABLE DATASETS:"]
        for t in self.table_info.values():
            lines.append(f"TABLE {t.name} ({t.row_count} rows)")
            for c in t.columns:
                samples = ", ".join(repr(v) for v in c.sample_values[:3])
                coverage = f"; coverage={c.temporal_coverage}" if c.temporal_coverage else ""
                lines.append(f"  - {c.name}: {c.dtype}; examples=[{samples}]{coverage}")

        metrics = self.dictionary.get("metrics", {})
        dimensions = self.dictionary.get("dimensions", [])
        synonyms = self.dictionary.get("synonyms", {})
        if metrics:
            lines.append("BUSINESS METRICS:")
            for k, v in metrics.items():
                lines.append(f"  - {k}: {v}")
        if dimensions:
            lines.append("KNOWN DIMENSIONS: " + ", ".join(map(str, dimensions)))
        if synonyms:
            lines.append("BUSINESS SYNONYMS:")
            lines.extend(f"  - {k} -> {v}" for k, v in synonyms.items())
        return "\n".join(lines)
