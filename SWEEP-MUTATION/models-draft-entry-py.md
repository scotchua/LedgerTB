# Mutation sweep: `models/draft_entry.py`

## Stopped before mutation

The offline environment cannot import `models.draft_entry` through the normal
package path. `python3 -c 'import models.draft_entry'` fails in `config.py` with
`ModuleNotFoundError: No module named 'platformdirs'`. The same missing dependency
prevents pytest from loading `tests/conftest.py`, so the existing draft tests
cannot exercise the module. The available Python 3.11 has no pytest. Package
installation and network access are excluded by the task.

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | N/A (no executable mutants) | N/A (no executable mutants) |

Survivors left: none generated. New tests: none. Defects found: none assessed.
The throwaway runner was not created because no mutant could be run against
the existing tests. No production file was changed.

## Verification attempted

- `python3 -m pytest -q tests/test_draft_entries.py`: pytest could not load
  `tests/conftest.py` because `platformdirs` is missing.
- `python3 -c 'import models.draft_entry'`: failed for the same reason.
- The requested `python -m pytest -q -m "not performance"` cannot run because
  `python` is unavailable; `python3` encounters the dependency failure above.
