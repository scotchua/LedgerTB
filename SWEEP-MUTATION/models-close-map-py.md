# Mutation sweep: `models/close_map.py`

## Stopped before mutation

The offline test environment cannot import the existing close-map tests. The
repository's `tests/conftest.py` imports `database.connection`, which imports
`config.py`; importing `config.py` fails with
`ModuleNotFoundError: No module named 'platformdirs'`. The available Python
interpreters also lack `sqlcipher3` and `streamlit`, both needed by the
existing tests. No packages were installed and no network access was used.

The brief's escalation condition applies: a direct `import models.close_map`
and the existing tests both fail offline at the missing `platformdirs` import.
The required command, `python -m pytest -q -m "not performance"`, cannot start
because `python` is unavailable. The available `python3 -m pytest -q -m "not
performance"` fails while loading `tests/conftest.py` for the same missing
dependency.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before | 0; kill rate not applicable |
| Killed after | 0; kill rate not applicable |
| Survivors left | 0; no mutants were run |
| Equivalent, untestable offline, or defect mutants | None classified |
| New tests and test names | None |

## Defects found

None assessed. The production module was not modified.
