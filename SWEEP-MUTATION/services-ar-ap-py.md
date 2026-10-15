# Mutation sweep: `services/ar_ap.py`

## Stopped before mutation

The available offline interpreter cannot collect the existing AR/AP tests. Running
`python3 -m pytest -q tests/test_ar_ap.py -m "not performance"` stops while loading
`tests/conftest.py`: `config.py` imports `platformdirs`, which is not installed.
The same interpreter also lacks `reportlab`, which `services/ar_ap.py` imports.
There is no project virtual environment in the worktree. The requested `python`
command is unavailable. Packages were not installed and no production files were
changed.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before | Not measurable |
| Killed after | Not measurable |
| Before kill rate | Not measurable |
| After kill rate | Not measurable |
| Survivors left | None generated |
| New tests | None |
| Defects found | None assessed |

The brief's escalate condition applies: `services/ar_ap.py` cannot be imported
and exercised with the available offline interpreter and dependencies. Mutation
classification requires a runnable baseline.
