# Mutation test audit: `models/transaction.py`

## Outcome

Stopped before mutant generation. The source cannot be imported or exercised in the available offline Python environments without adding dependencies, which the task forbids.

## Verification attempts

- `python3 -c 'import models.transaction'` failed with `ModuleNotFoundError: No module named 'platformdirs'` during `config.py` import.
- `/Users/scottedwards/.local/bin/python3.11 -c 'import models.transaction'` failed with `ModuleNotFoundError: No module named 'dotenv'` during `config.py` import.
- `python3 -m pytest -q tests/test_import_history.py tests/test_pagination.py tests/test_import_suggestions.py -m 'not performance'` failed while loading `tests/conftest.py` because `platformdirs` is missing.
- The requested `python -m pytest` invocation is unavailable because `python` is not on `PATH`.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable |
| Before kill rate | Not measurable (0 mutants run) |
| Killed after new tests | Not measurable |
| After kill rate | Not measurable (0 mutants run) |
| Survivors left | None generated |
| New tests | None |

No equivalent mutants, offline-untestable mutants, or defects were classified because no mutant could be run. No throwaway runner was created. `models/transaction.py` was not modified.
