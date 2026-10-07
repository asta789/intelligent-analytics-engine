# Data handling and robustness

## What happens when you replace the data?

1. Every CSV in `data/` is loaded automatically.
2. The filename becomes the SQL table name (`sales_data.csv` -> `sales_data`).
3. The loader accepts ordinary CSV and the assignment's line-quoted CSV format.
4. Column types are inferred conservatively. Columns containing `date` or `time` are parsed as datetimes; numeric-looking columns become numeric; other values stay strings.
5. The catalog inspects row counts, types, nullability, and sample values at runtime.
6. The planner receives that live schema on every query.
7. The optional `data_dictionary.json` adds business semantics, formulas, synonyms, and time mappings.
8. The generated SQL is validated before execution.

## How to add a new dataset

Drop a new `.csv` into `data/`. No executor code needs to change.

If the new data has business metrics whose meaning cannot be inferred from column names, update `data_dictionary.json`. For example:

```json
{
  "metrics": {
    "net_sales": "gross_sales - returns"
  },
  "synonyms": {
    "sales": "net_sales"
  }
}
```

The LLM will then use that definition when planning queries.

## Important limitation

Schema inference can discover that a column is numeric, categorical, or temporal. It cannot reliably infer every business definition. That is why the semantic dictionary is deliberately external. This avoids baking today's business rules into Python code.

## Safety

The model is never given permission to execute Python or arbitrary shell commands. It proposes read-only SQL. The SQL safety gate blocks DDL/DML, multiple statements, unknown physical tables, and common file/system operations.
