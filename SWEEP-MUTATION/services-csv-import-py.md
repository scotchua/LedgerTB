# Mutation test report: `services/csv_import.py`

## Status

Stopped before mutation generation. The available offline Python environment cannot import the target module: `pandas` is absent (`ModuleNotFoundError: No module named 'pandas'`). The existing pytest setup also cannot collect the relevant tests because `tests/conftest.py` imports application configuration, which requires the absent `platformdirs` package. The job prohibits installing packages or using the network. No production code was changed.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable (0 mutants run) |
| Before kill rate | Not measurable |
| Killed after new tests | Not measurable (0 mutants run) |
| After kill rate | Not measurable |
| Survivors left | None generated; equivalence, offline testability, and defects were not assessed |
| New test names | None |
| Defects found | None assessed |

## Verification attempted

- `python3 -m pytest -q tests/test_csv_import.py tests/test_sign_convention_default.py -m 'not performance'` stopped during conftest import with `ModuleNotFoundError: No module named 'platformdirs'`.
- `python3 -c 'import pandas; print(pandas.__version__)'` failed with `ModuleNotFoundError: No module named 'pandas'`.
- The requested `python -m pytest -q -m "not performance"` command is unavailable because this environment has `python3` but no `python` executable; pytest collection would also encounter the missing dependency above.
