# `services/categorization.py` mutation run

## Stopped: offline import prerequisite

Read the full module and `tests/test_categorization.py`. The required test run cannot collect in the available Python environment. `python3 -m pytest -q tests/test_categorization.py` fails while importing `tests/conftest.py` because `platformdirs` is unavailable. A second attempt with an in-memory `platformdirs` stub and dotenv loading disabled fails during the same collection because `pandas` is unavailable. The brief prohibits installing packages and changing production code, so the offline mutation run stopped before generating mutants.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before | Not measurable |
| Before kill rate | Not measurable |
| Killed after | Not measurable |
| After kill rate | Not measurable |
| Survivors left | None generated; equivalent, untestable offline, and defect classifications unavailable |
| New tests | None |

## Defects found

None assessed.

The required full-suite command, `python -m pytest -q -m "not performance"`, is also unavailable because `python` is not on `PATH`; `python3` cannot collect the relevant tests for the dependency reasons above.
