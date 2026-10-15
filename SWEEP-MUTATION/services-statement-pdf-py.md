# Mutation sweep: `services/statement_pdf.py`

## Stopped before mutation

The available offline Python environment cannot import or exercise the service. Importing `services.statement_pdf` raises `ModuleNotFoundError: No module named 'platformdirs'` while loading `config.py`. `reportlab`, which the service also imports, is absent. No packages were installed and no production files were changed.

The requested `python3 -m pytest -q -m 'not performance'` exits during `tests/conftest.py` import with the same missing `platformdirs` error. The requested `python -m pytest -q -m 'not performance'` cannot start because this environment has no `python` executable.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | 0 / 0; kill rate unavailable |
| Killed after new tests | 0 / 0; kill rate unavailable |
| Survivors left | None generated; equivalence, offline testability, and defects could not be assessed |
| New tests | None |

## Defects found

None assessed. The sweep stopped before any mutant could be exercised.
