# Mutation test of `utils/recurring_ui.py`

## Stopped before mutation

The supplied offline Python environment cannot import `utils.recurring_ui`: `pandas` is missing. `streamlit` and `sqlcipher3` are also unavailable. Neither available Python interpreter has these packages, and installing packages is prohibited by the task. The requested pytest suite cannot collect because `tests/conftest.py` reaches a missing `platformdirs` import.

The module was read in full. Existing UI coverage was found in `tests/test_accounting_pages.py` (the recurring view generation and rejected reversal regeneration tests); `tests/test_recurring_entries.py` covers the underlying models and service, not this UI module directly.

## Results

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | Not measurable | Not measurable |
| Kill rate | Not measurable | Not measurable |

No mutation runner or tests were added. There are no recorded survivors, equivalent mutants, new test names, or defects found. `utils/recurring_ui.py` was not modified.
