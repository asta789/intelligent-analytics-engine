from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


class DataLoadError(Exception):
    pass


def _parse_text_csv(text: str) -> pd.DataFrame:
    """Read normal CSVs and the assignment's one-field quoted CSV variant."""
    text = text.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise DataLoadError("CSV is empty")

    # Assignment data is: "col1,col2,..." on each physical line.
    if len(rows[0]) == 1 and "," in rows[0][0]:
        reparsed: list[list[str]] = []
        for row in rows:
            if len(row) != 1:
                reparsed.append(row)
                continue
            reparsed.append(next(csv.reader([row[0]])))
        rows = reparsed

    header = [str(x).strip() for x in rows[0]]
    if len(set(header)) != len(header):
        raise DataLoadError(f"Duplicate columns found: {header}")

    data = rows[1:]
    if any(len(r) != len(header) for r in data):
        bad = next((r for r in data if len(r) != len(header)), None)
        raise DataLoadError(f"CSV row has wrong number of fields: {bad}")

    return pd.DataFrame(data, columns=header)


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        s = df[col].astype("string").str.strip()
        non_null = s.notna().sum()
        # Only attempt date parsing for columns whose names indicate temporal data.
        # This avoids expensive/noisy date parsing on ordinary categorical columns.
        if any(k in col.lower() for k in ["date", "time"]):
            parsed_date = pd.to_datetime(s, errors="coerce")
            if non_null and parsed_date.notna().sum() / non_null >= 0.9:
                df[col] = parsed_date
                continue

        numeric = pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce")
        if non_null and numeric.notna().sum() / non_null >= 0.95:
            df[col] = numeric
        else:
            df[col] = s
    return df


def load_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    try:
        df = _parse_text_csv(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        df = _parse_text_csv(path.read_text(encoding="latin-1"))
    return _coerce_types(df)


def table_name(path: str | Path) -> str:
    name = Path(path).stem.lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    return name.strip("_") or "table"


def _repair_line_quoted_json(raw: str) -> str:
    """Repair the benchmark's JSON where individual JSON lines were CSV-quoted."""
    out = []
    for line in raw.splitlines():
        if line.lstrip().startswith('"'):
            try:
                parsed = next(csv.reader([line]))
                if len(parsed) == 1:
                    line = parsed[0]
            except Exception:
                pass
        out.append(line)
    return "\n".join(out)


def load_dictionary(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    raw = _repair_line_quoted_json(raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Be explicit: a malformed dictionary should not silently become an empty dictionary.
        raise DataLoadError(f"Invalid JSON dictionary: {exc}") from exc
    if not isinstance(obj, dict):
        raise DataLoadError("Data dictionary must be a JSON object")
    return obj


def load_query_tests(path: str | Path) -> list[dict[str, str]]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    raw = _repair_line_quoted_json(raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"Invalid query test JSON: {exc}") from exc
    if not isinstance(obj, list):
        raise DataLoadError("nl_queries.json must contain a list")
    return obj
