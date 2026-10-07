from pathlib import Path

import pytest

from app.catalog import Catalog
from app.engine import AnalyticsEngine
from app.loader import load_csv, load_dictionary
from app.sql_safety import UnsafeSQL, validate_sql

ROOT = Path(__file__).resolve().parents[1]


def make_engine():
    tables = {
        "sales_data": load_csv(ROOT / "data" / "sales_data.csv"),
        "targets": load_csv(ROOT / "data" / "targets.csv"),
    }
    return AnalyticsEngine(Catalog(tables, load_dictionary(ROOT / "data" / "data_dictionary.json")))


def test_loader_recovers_assignment_csv():
    df = load_csv(ROOT / "data" / "sales_data.csv")
    assert len(df.columns) == 15
    assert len(df) == 10
    assert "order_date" in df.columns


def test_top_cities():
    r = make_engine().run("Top 2 cities by profit")
    assert len(r.result) == 2
    assert r.result[0]["profit"] >= r.result[1]["profit"]


def test_target_join():
    r = make_engine().run("Which region missed its target in Feb?")
    assert all(x["actual_revenue"] < x["target_revenue"] for x in r.result)


def test_month_name_uses_dataset_calendar_year():
    r = make_engine().run("Total sales in India for March")
    assert "strftime(order_date, '%Y-%m') = '2024-03'" in r.generated_logic
    assert r.result == [{"total_sales": 108.0}]


def test_yoy_does_not_fabricate():
    r = make_engine().run("YoY growth in revenue")
    assert all(x["previous_revenue"] is None for x in r.result)


def test_sql_parser_treats_order_date_as_column():
    sql = "SELECT EXTRACT(YEAR FROM order_date) AS year FROM sales_data GROUP BY order_date"
    assert validate_sql(sql, {"sales_data", "targets"}) == sql


def test_sql_parser_handles_join_cte_and_subquery():
    sql = """
    WITH monthly AS (
        SELECT region, strftime(order_date, '%Y-%m') AS month,
               SUM(quantity * unit_price) AS revenue
        FROM sales_data
        GROUP BY region, order_date
    )
    SELECT m.region, m.revenue, t.target_revenue
    FROM monthly AS m
    JOIN targets AS t ON t.region = m.region AND t.month = m.month
    WHERE m.revenue > (SELECT AVG(revenue) FROM monthly)
    """
    assert validate_sql(sql, {"sales_data", "targets"}) == sql.strip()


def test_sql_parser_rejects_unknown_table_and_writes():
    with pytest.raises(UnsafeSQL, match="Unknown tables referenced"):
        validate_sql("SELECT * FROM not_a_dataset", {"sales_data"})
    with pytest.raises(UnsafeSQL):
        validate_sql("DROP TABLE sales_data", {"sales_data"})


def test_parser_cases_execute_against_loaded_tables():
    engine = make_engine()
    assert engine.executor.execute(
        "SELECT EXTRACT(YEAR FROM order_date) AS year FROM sales_data GROUP BY order_date"
    )
    assert engine.executor.execute(
        "SELECT s.region, t.target_revenue FROM sales_data s "
        "JOIN targets t ON s.region = t.region WHERE t.month = '2024-02'"
    )
    assert engine.executor.execute(
        "WITH x AS (SELECT region, SUM(profit) AS p FROM sales_data GROUP BY region) "
        "SELECT region, p FROM x WHERE p > (SELECT AVG(p) FROM x)"
    )
