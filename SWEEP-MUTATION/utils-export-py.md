# Mutation test of `utils/export.py`

## Stopped before mutation

`utils/export.py` cannot be imported in the available offline Python environment because `pandas` is not installed (`ModuleNotFoundError: No module named 'pandas'`). The requested verification command, `python -m pytest -q -m "not performance"`, cannot run because `python` is not on `PATH`. Its available equivalent, `python3 -m pytest -q -m "not performance"`, fails while loading `tests/conftest.py` because `platformdirs` is also missing.

The brief requires stopping if the module cannot be imported or exercised offline without changing production code. No packages were installed, and no production code was changed.

## Results

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | N/A (no runnable mutants) | N/A (no runnable mutants) |

Survivors: none generated. New tests: none. Defects found: none assessed.
