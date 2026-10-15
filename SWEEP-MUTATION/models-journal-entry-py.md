# Mutation test report: `models/journal_entry.py`

## Stop reason

The offline Python environment cannot import the journal entry module through the existing test suite. Test collection stops while importing `tests/conftest.py` because `config.py` requires the unavailable `platformdirs` package. The environment also lacks `sqlcipher3`, which the database-backed journal tests require. The job prohibits package installation and network access, so the brief's escalation condition applies.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | 0 of 0; rate unavailable |
| Killed after new tests | 0 of 0; rate unavailable |
| Survivors left | None generated |
| New tests | None |

## Verification

`python3 -m pytest -q -m 'not performance'` stopped during test collection with `ModuleNotFoundError: No module named 'platformdirs'`. The requested `python -m pytest` command is unavailable because this environment has no `python` executable; `python3` was used for the collection check.

## Defects found

None assessed. No mutants were run.
