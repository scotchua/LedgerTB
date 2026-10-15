# Mutation sweep: `services/pattern_learning.py`

## Status

Stopped before mutation generation under the brief's Escalate-if condition. The module cannot be imported in the available offline Python environment. `services/__init__.py` imports `services/categorization.py`, which imports `config.py`; that import fails because `platformdirs` is unavailable. The relevant pytest files also fail during `tests/conftest.py` collection for the same reason. Installing packages and changing production code were outside this task.

## Scope reviewed

Read `services/pattern_learning.py` in full and reviewed the existing coverage in `tests/test_lows.py`, `tests/test_audit_log.py`, `tests/test_account_delete.py`, and `tests/test_posting.py`.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | 0 / 0; rate not measurable |
| Killed after new tests | 0 / 0; rate not measurable |
| Survivors left | 0; mutation runs did not start |
| New tests | None |
| Equivalent mutants | None evaluated |
| Untestable offline mutants | None generated; all candidate mutations blocked before execution |
| Defects found | None evaluated |

## Verification

- `python3 -c 'import services.pattern_learning'` failed with `ModuleNotFoundError: No module named 'platformdirs'` before loading the target module.
- `python3 -m pytest -q tests/test_lows.py tests/test_audit_log.py tests/test_account_delete.py tests/test_posting.py -m 'not performance'` failed while loading `tests/conftest.py` with the same error.
- `python3 -m pytest -q -m 'not performance'` failed during the same collection import.
- The requested `python -m pytest -q -m "not performance"` command could not run because `python` is unavailable; `python3` is available but lacks the dependency above.

No runner, tests, or production files were changed.
