# Mutation test stop report: `models/import_coding.py`

The escalation condition fired before mutation testing. The module cannot be
imported normally in this offline environment: `config.py` imports
`platformdirs`, which is not installed. The existing tests also fail while
loading `tests/conftest.py` for the same reason. No packages were installed and
no production files were changed.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before | Not measured; tests cannot load |
| Before kill rate | Not measurable |
| Killed after | Not measured |
| After kill rate | Not measurable |
| Survivors left | None generated |
| New tests | None |
| Defects found | Not assessed |

Verification attempted with `python3 -m pytest -q -m 'not performance'`.
Pytest exited during `tests/conftest.py` import with
`ModuleNotFoundError: No module named 'platformdirs'`.
