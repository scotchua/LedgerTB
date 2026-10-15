# Mutation test run: `models/assistant_review.py`

## Stop reason

The offline import gate failed before any review test could run. `python3 -m pytest -q tests/test_assistant_setup_and_review.py -k 'review_queue or review_checkpoint or review_audit'` stopped while loading `tests/conftest.py`: `config.py` imports `platformdirs`, which is unavailable (`ModuleNotFoundError: No module named 'platformdirs'`). The prescribed `python -m pytest` command is also unavailable because this environment has no `python` executable. Package installation and network access are prohibited by the task.

The task's escalation condition applies: the module cannot be imported through its normal dependency path or exercised by the existing suite in this offline environment. No production code was changed.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0; stopped at the import gate |
| Killed before | Unavailable; no test run started |
| Before kill rate | Unavailable |
| Killed after | Unavailable; no mutations or tests were added |
| After kill rate | Unavailable |
| Survivors left | None generated |
| New test names | None |

## Defects found

None assessed.
