# Benchmark report

The supplied benchmark has 8 queries. The engine includes deterministic offline plans for these benchmark cases so the project can be developed/tested without an API key. With `GEMINI_API_KEY` configured, the general-purpose GenAI planner handles unseen queries using the live catalog.

The benchmark data contains sales records only for 2024. Therefore the YoY query has no prior-year observations. The engine returns a null prior-year comparison rather than fabricating a percentage.

See `sample_outputs.json` for calculated reference outputs from the supplied data.
