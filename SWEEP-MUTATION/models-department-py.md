# Mutation test: `models/department.py`

## Stopped before mutation

The required offline test run cannot collect tests. `python3 -m pytest -q tests/test_payroll_recording.py -k department` fails while importing `tests/conftest.py`: `config.py` requires `platformdirs`, which is not installed. The other installed Python interpreters also lack `platformdirs`; the available environment also lacks `streamlit` and `pandas`. The brief prohibits installing packages and production changes, so the escalation condition applies.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable |
| Before kill rate | Not measurable |
| Killed after new tests | Not measurable |
| After kill rate | Not measurable |
| Survivors left | None generated |
| New test names | None |

No mutation runner was created. `models/department.py` was read in full; the existing department use in `tests/test_payroll_recording.py` and the department schema test in `tests/test_shared_domain_migration.py` were inspected. No production file was changed.
