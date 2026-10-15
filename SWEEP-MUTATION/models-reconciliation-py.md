# Mutation test sweep: `models/reconciliation.py`

## Stop reason

The module and its existing reconciliation tests were read, but the offline
Python environment cannot import the test suite or `models.reconciliation`.
Directly importing `models.reconciliation` also raises `ModuleNotFoundError`
for `platformdirs`.
`python3 -m pytest -q -m 'not performance'` stops while loading
`tests/conftest.py`: `config.py` imports `platformdirs`, which is absent
(`ModuleNotFoundError`). The available Python installations also lack the
project's `sqlcipher3` dependency. Installing packages is prohibited for this
task, so the escalation condition applies before mutation execution.

## Results

| Measure | Before new tests | After new tests |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | N/A (0/0) | N/A (0/0) |

No mutants were classified as killed, survived, equivalent, untestable, or
defects. No new tests were added. Defects found: none assessed.

## Verification

`python3 -m pytest -q -m 'not performance'` could not collect tests because
`platformdirs` is missing. No production file was modified.
