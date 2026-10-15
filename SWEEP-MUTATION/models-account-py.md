# Mutation sweep: `models/account.py`

## Stopped before mutation

The offline test environment cannot import `models.account` through the project's normal import path. `python3 -m pytest -q tests/test_account_subtypes.py tests/test_account_delete.py tests/test_counts.py -m "not performance"` stops while loading `tests/conftest.py`: `config.py` requires `platformdirs`, which is not installed. A temporary in-process shim for `platformdirs` (with dotenv loading disabled) reaches a second missing dependency: `models/__init__.py` requires `pandas`. The task prohibits package installation and production changes, so the escalation condition applies.

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | Not measurable | Not measurable |

No mutants were run, no survivors were classified, and no tests were added. The source file was not changed. The requested full-suite verification is unavailable for the same import failure.

## Defects found

None evaluated.
