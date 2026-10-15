# Mutation check: `services/recurring_entries.py`

## Stopped before mutation

The module cannot be imported or exercised with the available offline Python environments. The direct import `ANTHROPIC_API_KEY=test-key-never-used python3 -c 'import services.recurring_entries'` fails in `config.py` with `ModuleNotFoundError: No module named 'platformdirs'`. The relevant test command `python3 -m pytest -q tests/test_recurring_entries.py` fails while loading `tests/conftest.py` for the same reason. The available Python 3.14 and system Python 3.9 interpreters also lack `sqlcipher3`, which the database-backed tests require. No packages were installed and no production files were changed.

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | N/A (no executable baseline) | N/A (no executable baseline) |

Survivors left: none generated. Equivalent, offline-untestable, and defect classifications could not be evaluated. Defects found: none evaluated. New tests: none. The requested full-suite verification could not run because test collection stops at the missing dependency.
