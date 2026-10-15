# Mutation run: `services/fixed_assets.py`

## Stopped before mutation

The offline Python environment cannot import the module through the application's
normal package path. `python3 -m pytest -q tests/test_fixed_assets.py
tests/test_fixed_asset_depreciation_oracles.py -k 'not migration'` stops while loading
`tests/conftest.py`: `ModuleNotFoundError: No module named 'platformdirs'`.
An import retry with an in-memory `platformdirs` stub reaches
`ModuleNotFoundError: No module named 'pandas'` through `models/reports.py`.
The environment also lacks other declared dependencies, including `streamlit`,
`rapidfuzz`, `portalocker`, and `mcp`. The task forbids package installation.
Consequently the module cannot be exercised with the existing test harness
offline in this worktree.

## Results

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | Not measured | Not measured |
| Kill rate | Not measured | Not measured |
| Survivors | Not measured | Not measured |

No mutant classifications, new tests, or defects were recorded. The source
file's SHA-256 was `03f5e4b3204552e96964406fa4bcf4095e96cae12ad9b70ffc21bd90a3feb514`;
it was not modified. The required full-suite command could not run because
`python` is unavailable, and `python3 -m pytest` stops at the same dependency
failure.
