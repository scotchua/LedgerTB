# Mutation test report: `models/fiscal_period.py`

## Stopped before mutation

The offline test environment cannot import the model through the existing test
suite. `python3 -m pytest -q tests/test_close_checklist.py
tests/test_fiscal_dates.py tests/test_assistant_setup_and_review.py -m 'not
performance'` stops while importing `tests/conftest.py`: `config.py` requires
`platformdirs`, which is not installed. The `python` command is unavailable.
The installed `python3` also lacks other declared runtime dependencies,
including `portalocker`, `pandas`, `streamlit`, `rapidfuzz`, `mcp`, and
`reportlab`. Package installation is prohibited for this task. Tests cannot
be run against either the original or mutants in this environment.

The model and its direct tests were read. The original model's SHA-256 is
`7343d2c2f2c56113fa11a7bf32be4defbfea6b43b318101b3f61b70f8dc5ad47`.
No production file was changed.

## Results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 (stopped before mutation) |
| Killed before new tests | Not measurable |
| Before kill rate | Not measurable (0 mutants run) |
| Killed after new tests | Not measurable |
| After kill rate | Not measurable (0 mutants run) |
| Survivors left | None classified; no mutants were run |
| New tests | None |

## Defects found

None evaluated. No conclusion about defects can be drawn from this run.
