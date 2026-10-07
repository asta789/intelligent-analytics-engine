from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from .catalog import Catalog
from .engine import AnalyticsEngine
from .loader import load_csv, load_dictionary, table_name
from .models import QueryRequest, QueryResponse

load_dotenv()

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", BASE / "data"))


def build_engine() -> AnalyticsEngine:
    tables = {}
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        tables[table_name(csv_path)] = load_csv(csv_path)
    dictionary_path = DATA_DIR / "data_dictionary.json"
    dictionary = load_dictionary(dictionary_path) if dictionary_path.exists() else {}
    return AnalyticsEngine(Catalog(tables, dictionary))


engine = build_engine()
app = FastAPI(title="Intelligent Analytics Query Engine", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "tables": list(engine.catalog.tables), "rows": {k: len(v) for k, v in engine.catalog.tables.items()}}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    try:
        return engine.run(request.query)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
