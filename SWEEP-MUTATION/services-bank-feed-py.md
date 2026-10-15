# `services/bank_feed.py` mutation sweep

## Stopped before mutation

The available offline Python environment cannot import `services.bank_feed` or
collect `tests/test_bank_feed.py`: both stop with
`ModuleNotFoundError: No module named 'platformdirs'` while importing
`config.py`. The worktree has no project virtual environment. Required runtime
packages including `platformdirs`, `streamlit`, and `sqlcipher3` are absent from
the available interpreter. Package installation and network access are outside
this task's constraints, so the brief's escalation condition applies.

## Results

| Measure | Before new tests | After new tests |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Mutants survived | 0 | 0 |
| Kill rate | Not measurable | Not measurable |

No mutants were run, no equivalent mutants or defects were classified, and no
new tests were added. The throwaway runner was not created. The requested
`python -m pytest -q -m "not performance"` verification could not run: the
available command is `python3`, whose pytest collection fails on the missing
dependency above.
