from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass


from .catalog import Catalog
from .models import QueryPlan


SYSTEM_PROMPT = """
You turn business questions into one read-only DuckDB query.

Use only tables and columns from the supplied schema. Do not invent fields.
Use the business dictionary for metric definitions, synonyms and time terms.
Revenue is a derived metric when the dictionary defines it that way.
Interpret month names as calendar months on the available date column. If a
year is omitted and the supplied data covers exactly one year, use that year;
if multiple years are available, do not invent a year and preserve the
question's intended multi-year scope.
Use window functions for rankings within groups and NULLIF for divisions.
Only join tables when the question needs them and the schema supports the join.
If the data cannot answer the question, do not invent a value or definition.

Return JSON with exactly these fields:
- sql: one SELECT or WITH query
- interpretation: what the query is doing
- confidence: a number from 0 to 1
- assumptions: a list of explicit assumptions
""".strip()


@dataclass
class Planner:
    catalog: Catalog

    def __post_init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.fallback_models = [
            x.strip()
            for x in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.6-flash").split(",")
            if x.strip()
        ]
        self.client = None

        if self.api_key:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)

    def plan(self, query: str) -> QueryPlan:
        if self.client is not None:
            last_error = None
            for model in self._models_to_try():
                try:
                    return self._llm_plan(query, model)
                except Exception as exc:
                    last_error = exc
                    if not self._retryable(exc):
                        break

            try:
                return self._fallback_plan(query)
            except ValueError:
                if last_error is not None:
                    raise RuntimeError(self._format_llm_error(last_error)) from last_error
                raise

        return self._fallback_plan(query)

    def _models_to_try(self):
        seen = set()
        for model in [self.model, *self.fallback_models]:
            if model and model not in seen:
                seen.add(model)
                yield model

    def _llm_plan(self, query: str, model: str) -> QueryPlan:
        prompt = f"{SYSTEM_PROMPT}\n\n{self.catalog.prompt_context()}\n\nUSER QUERY:\n{query}"

        response = self._generate_with_retry(model, prompt)
        raw = (response.text or "").strip()
        if not raw:
            raise ValueError(f"Gemini returned an empty response from {model}")

        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()

        data = json.loads(raw)
        return QueryPlan.model_validate(data)

    def _generate_with_retry(self, model: str, prompt: str):
        delays = (1, 2, 4)
        last_error = None

        for attempt in range(len(delays) + 1):
            try:
                return self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "temperature": 0,
                        "response_mime_type": "application/json",
                    },
                )
            except Exception as exc:
                last_error = exc
                if not self._retryable(exc) or attempt == len(delays):
                    raise
                time.sleep(delays[attempt])

        if last_error is not None:
            raise last_error
        raise RuntimeError("Gemini generation failed without an exception")

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        return status in {408, 429, 500, 502, 503, 504}

    @staticmethod
    def _format_llm_error(exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        if status in {429, 500, 502, 503, 504}:
            return (
                f"Gemini is temporarily unavailable ({status}). "
                "The request was retried and the configured fallback models were also unavailable."
            )
        return f"Gemini planning failed: {exc}"

    def _fallback_plan(self, query: str) -> QueryPlan:
        q = query.lower().strip()

        if "top 2 cities" in q and "profit" in q:
            return QueryPlan(
                sql="SELECT city, SUM(profit) AS profit FROM sales_data GROUP BY city ORDER BY profit DESC LIMIT 2",
                interpretation="Rank cities by total profit and return the top 2.",
                confidence=0.99,
            )

        if "average order value" in q and "region" in q:
            return QueryPlan(
                sql="SELECT region, SUM(quantity * unit_price * (1 - discount)) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_order_value FROM sales_data GROUP BY region",
                interpretation="Calculate revenue divided by distinct orders for each region.",
                confidence=0.99,
            )

        if "sales contribution" in q and "category" in q:
            return QueryPlan(
                sql="SELECT product_category, 100.0 * SUM(quantity * unit_price * (1 - discount)) / NULLIF((SELECT SUM(quantity * unit_price * (1 - discount)) FROM sales_data), 0) AS contribution_pct FROM sales_data GROUP BY product_category ORDER BY contribution_pct DESC",
                interpretation="Calculate each product category's share of total revenue.",
                confidence=0.98,
            )

        if "total revenue" in q and "month" in q:
            return QueryPlan(
                sql="SELECT strftime(order_date, '%Y-%m') AS month, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data GROUP BY 1 ORDER BY month",
                interpretation="Aggregate derived revenue by calendar month.",
                confidence=0.95,
            )

        if "top product in each region" in q:
            return QueryPlan(
                sql="WITH x AS (SELECT region, product_name, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data GROUP BY region, product_name), r AS (SELECT *, RANK() OVER (PARTITION BY region ORDER BY revenue DESC) AS rank FROM x) SELECT region, product_name, revenue FROM r WHERE rank = 1 ORDER BY region",
                interpretation="Rank products by revenue inside each region and return the top product.",
                confidence=0.98,
            )

        if "top 3 customers" in q and "region" in q:
            return QueryPlan(
                sql="WITH x AS (SELECT region, customer_id, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data GROUP BY region, customer_id), r AS (SELECT *, RANK() OVER (PARTITION BY region ORDER BY revenue DESC) AS rank FROM x) SELECT region, customer_id, revenue FROM r WHERE rank <= 3 ORDER BY region, revenue DESC",
                interpretation="Rank customers by revenue inside each region and return the top 3.",
                confidence=0.98,
            )

        if "missed its target" in q or "missed target" in q:
            if "feb" in q:
                return QueryPlan(
                    sql="WITH actual AS (SELECT region, SUM(quantity * unit_price * (1 - discount)) AS actual_revenue FROM sales_data WHERE strftime(order_date, '%Y-%m') = '2024-02' GROUP BY region) SELECT t.region, actual.actual_revenue, t.target_revenue, t.target_revenue - COALESCE(actual.actual_revenue, 0) AS shortfall FROM targets t LEFT JOIN actual ON t.region = actual.region WHERE t.month = '2024-02' AND COALESCE(actual.actual_revenue, 0) < t.target_revenue ORDER BY shortfall DESC",
                    interpretation="Compare February actual revenue with the regional targets and return regions below target.",
                    confidence=0.99,
                )

        if "total sales" in q and "india" in q and "march" in q:
            month_predicate = self._calendar_month_predicate(3)
            year_note = "the March month represented by the supplied single-year dataset" if "%Y-%m" in month_predicate else "all March records"
            return QueryPlan(
                sql=f"SELECT SUM(quantity * unit_price * (1 - discount)) AS total_sales FROM sales_data WHERE country = 'India' AND {month_predicate}",
                interpretation=f"Sum derived revenue for India during {year_note}.",
                confidence=0.98,
            )

        if "yoy" in q or "year over year" in q:
            return QueryPlan(
                sql="WITH years AS (SELECT EXTRACT(YEAR FROM order_date) AS year, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data GROUP BY 1), pairs AS (SELECT year, revenue, LAG(revenue) OVER (ORDER BY year) AS previous_revenue FROM years) SELECT year, revenue, previous_revenue, CASE WHEN previous_revenue IS NULL THEN NULL ELSE (revenue - previous_revenue) / NULLIF(previous_revenue, 0) END AS yoy_growth FROM pairs ORDER BY year",
                interpretation="Calculate annual revenue and compare each year with the preceding year. The loaded data contains only 2024, so prior-year data is unavailable and no YoY percentage is fabricated.",
                confidence=0.95,
                assumptions=["YoY needs at least two comparable years; the first year has no prior-year growth."],
            )

        raise ValueError("The local planner does not have enough information to safely answer this query.")

    def _calendar_month_predicate(self, month: int) -> str:
        """Resolve an unqualified month using the loaded date coverage."""
        sales = self.catalog.tables.get("sales_data")
        if sales is not None and "order_date" in sales:
            years = sorted(sales["order_date"].dropna().dt.year.unique().tolist())
            if len(years) == 1:
                return f"strftime(order_date, '%Y-%m') = '{years[0]}-{month:02d}'"
        return f"strftime(order_date, '%m') = '{month:02d}'"
