# Mutation test run: `database/connection.py`

## Status

Stopped before mutant generation. The available Python environments cannot import
`database.connection` through the project's normal test path offline.

The requested `python -m pytest -q -m "not performance"` command cannot start
because `python` is not on `PATH`. Using `python3`, pytest fails while loading
`tests/conftest.py`: `database.connection` imports `config`, whose import raises
`ModuleNotFoundError: No module named 'platformdirs'`. The available interpreter
also lacks `sqlcipher3`, `streamlit`, and `pandas`. No packages were installed,
and no network calls were made.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable (test collection blocked) |
| Before kill rate | Not measurable (0 mutants run) |
| Killed after new tests | Not measurable (no new tests) |
| After kill rate | Not measurable (0 mutants run) |
| Survivors left | None generated; no equivalence or defect assessment possible |
| New test names | None |

## Defects found

None assessed. The escalation condition prevented behavior testing.
