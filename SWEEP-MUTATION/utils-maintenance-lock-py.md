# Mutation test: `utils/maintenance_lock.py`

## Escalation

The available offline Python environment cannot import the module: `python3 -c 'import utils.maintenance_lock'` raises `ModuleNotFoundError: No module named 'portalocker'`. The requested pytest run also cannot reach test collection because `platformdirs` is missing. No packages were installed and no production files were changed.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measured; module import blocked |
| Before kill rate | Not available |
| Killed after new tests | Not measured; module import blocked |
| After kill rate | Not available |
| Survivors left | None classified; no mutants were run |
| New tests | None |

## Defects found

None assessed.

## Verification

`python3 -m pytest -q tests/test_maintenance_processes.py tests/test_passphrase_change.py -k 'maintenance or lock or assistant_write or overlapping_writes or nesting_on_one_thread or coordination_file or live_holders'` stopped while loading `tests/conftest.py`: `ModuleNotFoundError: No module named 'platformdirs'`.

The requested `python -m pytest -q -m "not performance"` could not start because `python` is not available in `PATH`.
