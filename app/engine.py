from __future__ import annotations

from .catalog import Catalog
from .executor import QueryExecutor
from .models import QueryResponse
from .planner import Planner
from .sql_safety import UnsafeSQL, validate_sql


class AnalyticsEngine:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.planner = Planner(catalog)
        self.executor = QueryExecutor(catalog.tables)

    def run(self, query: str) -> QueryResponse:
        plan = self.planner.plan(query)
        try:
            sql = validate_sql(plan.sql, set(self.catalog.tables))
            result = self.executor.execute(sql)
        except UnsafeSQL:
            raise
        except Exception as exc:
            # Do not hide execution failures behind a fake result.
            raise RuntimeError(f"Generated query could not be executed: {exc}") from exc

        explanation = f"{plan.interpretation} The system executed a validated read-only analytical query against the loaded datasets."
        if plan.assumptions:
            explanation += " Assumptions: " + "; ".join(plan.assumptions)
        # Successful validation and execution confirm the referenced relations
        # and columns. Explicit assumptions reduce confidence because they
        # represent unresolved interpretation rather than execution failure.
        confidence = plan.confidence - min(0.15, 0.05 * len(plan.assumptions))
        return QueryResponse(
            query=query,
            generated_logic=plan.sql,
            result=result,
            confidence_score=round(max(0.0, confidence), 3),
            explanation=explanation,
            assumptions=plan.assumptions,
        )
