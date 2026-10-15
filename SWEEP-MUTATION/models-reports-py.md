# Mutation test run: `models/reports.py`

## Status

Stopped before mutation generation. The available `python3` environment cannot
import `models.reports` or collect the relevant tests offline: `platformdirs`
is missing. The requested `python` command is also unavailable. The task forbids
package installation, network access, and production changes, so the offline
import prerequisite cannot be met in this worktree.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before | Not measured (no runnable baseline) |
| Before kill rate | Not measured |
| Killed after | Not measured (no mutations or new tests) |
| After kill rate | Not measured |
| Survivors left | None generated |
| New tests | None |

No mutants were classified as equivalent, untestable offline, or defects because
mutation execution never started.

## Verification attempted

- `python3 -c 'import models.reports'` failed with
  `ModuleNotFoundError: No module named 'platformdirs'` through
  `models/__init__.py` and `database/connection.py`.
- `python3 -m pytest -q tests/test_reports.py tests/test_cash_flow.py
  tests/test_statement_presentation.py tests/test_account_groupings.py
  tests/test_fiscal_dates.py -m 'not performance'` failed while loading
  `tests/conftest.py` for the same missing dependency.
- `python -m pytest -q ...` could not start because `python` is not on `PATH`.

## Defects found

None assessed; source behavior could not be exercised.
