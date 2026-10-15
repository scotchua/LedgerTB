# Mutation test assessment: `utils/unlock.py`

## Stopped before mutation

The offline environment cannot import `utils.unlock` or collect the existing tests without missing application dependencies. Direct import fails at `import streamlit as st` with `ModuleNotFoundError: No module named 'streamlit'`. The requested verification command (using the available `python3` executable) fails while loading `tests/conftest.py`: `config.py` requires the missing `platformdirs` package. `sqlcipher3` is also unavailable. The job prohibits installing packages and changing production code, so the brief's escalation condition applies.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measured; tests could not collect |
| Before kill rate | Not available (0 mutants run) |
| Killed after new tests | Not measured; no new tests added |
| After kill rate | Not available (0 mutants run) |
| Survivors left | None generated; import and test collection blocked offline |
| New test names | None |
| Defects found | Not assessed |

No mutation runner was retained. `utils/unlock.py` and all production files were left unchanged.
