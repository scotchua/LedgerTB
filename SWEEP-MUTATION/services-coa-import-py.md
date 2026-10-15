# Mutation test report: `services/coa_import.py`

## Stopped before mutation

The available Python interpreters cannot import or exercise `services.coa_import` offline. `python3 -c 'import services.coa_import'` fails because `platformdirs` is missing from the environment. `rapidfuzz`, which `services/coa_import.py` imports directly, is also unavailable. The relevant pytest command fails while loading `tests/conftest.py` for the same missing `platformdirs` dependency. The task's escalate-if condition requires stopping here; no packages were installed and no production code was changed.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | 0; kill rate not measurable (0 mutants run) |
| Killed after new tests | 0; kill rate not measurable (0 mutants run) |
| Survivors left | None generated; equivalence, offline testability, and defects could not be assessed |
| New tests | None |

## Defects found

None assessed.

## Verification attempted

`python3 -m pytest -q tests/test_coa_import.py -m 'not performance'` stopped during collection with `ModuleNotFoundError: No module named 'platformdirs'`. The requested full-suite verification cannot run in this environment for the same reason.
