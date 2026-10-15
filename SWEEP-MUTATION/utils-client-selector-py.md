# utils/client_selector.py mutation run

## Status

Stopped under the brief's escalation condition: the selector cannot be imported in the available offline Python environment. `python3 -c 'import utils.client_selector'` raises `ModuleNotFoundError: No module named 'streamlit'`. No alternate project interpreter or installed Streamlit was found. Installing packages is prohibited for this task.

The requested verification, `python3 -m pytest -q -m "not performance"`, stops while loading `tests/conftest.py`: `config.py` requires the unavailable `platformdirs` package. Consequently the existing tests cannot be run against mutants in this environment.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable (0/0) |
| Killed after new tests | Not measurable (0/0) |
| Survivors left | None generated; classification unavailable |
| New tests | None |

No production file was modified. No mutation runner or new test was retained.
