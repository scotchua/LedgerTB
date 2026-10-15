# Mutation test run: `models/recurring_entry.py`

Stopped before mutation generation under the brief's Escalate-if condition. The available offline Python environments cannot import the model: `python3 -c 'import models.recurring_entry'` raises `ModuleNotFoundError: No module named 'platformdirs'` while importing `config.py`. The relevant existing tests also stop during collection for the same reason (`python3 -m pytest -q tests/test_recurring_entries.py -m 'not performance'`). The requested `python` executable is unavailable.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable (0 run) |
| Before kill rate | Not measurable |
| Killed after new tests | Not measurable (0 run) |
| After kill rate | Not measurable |
| Survivors left | None assessed; no mutants were run |
| New tests | None |

## Defects found

None assessed.
