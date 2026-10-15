# Mutation test run: `services/import_batch_reversal.py`

Stopped before mutation generation under the brief's escalation condition. The service cannot be imported or exercised offline with the available Python environments without changing production code or installing packages, both outside this run's constraints.

- `python3 -c 'import services.import_batch_reversal'` fails with `ModuleNotFoundError: No module named 'platformdirs'` from `config.py`.
- `python3 -m pytest -q tests/test_import_batch_reversal.py` fails during `tests/conftest.py` import with the same error, before test collection.
- The available `python3.11` has neither `pytest` nor the application dependencies. The requested `python -m pytest -q -m "not performance"` cannot start because `python` is not on `PATH`.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before | Not measured |
| Before kill rate | Not measured |
| Killed after | Not measured |
| After kill rate | Not measured |
| Survivors left | None generated |
| New tests | None |
| Defects found | Not assessed |

The production module was not modified. No mutation runner was retained.
