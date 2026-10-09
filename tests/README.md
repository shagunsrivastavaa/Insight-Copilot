# Insight Copilot tests

Run the standard-library test suite from the project root:

```powershell
python -m unittest discover -s tests -v
```

The suite checks deterministic routing and date-range handling, verifies that
the execution node calls only selected tools and preserves successful results
when another tool fails, and checks monthly and delivery answer summaries.
Tool calls are mocked and the synthesis tests use small in-memory dictionaries,
so these tests do not read or modify the Olist CSV files. The suite uses
`unittest` and adds no dependency; pytest can also discover and run these tests
if it is installed in the active environment.
