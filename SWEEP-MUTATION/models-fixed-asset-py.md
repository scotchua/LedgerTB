# Mutation test hardening: `models/fixed_asset.py`

## Stopped before mutation

The offline test environment cannot import the model through the existing test
suite. `python3 -m pytest -q tests/test_fixed_assets.py
tests/test_fixed_asset_depreciation_oracles.py -m 'not performance'` fails while
loading `tests/conftest.py`: `config.py` imports `platformdirs`, which is not
installed. The available Python interpreters lack that dependency. The requested
`python -m pytest -q -m "not performance"` command is also unavailable because
`python` is not on `PATH`. Installing packages is prohibited by this brief.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measurable; test collection fails |
| Before kill rate | Not measurable |
| Killed after new tests | Not measurable |
| After kill rate | Not measurable |
| Survivors left | None generated |
| New tests | None |

No mutation runner or test files were added. `models/fixed_asset.py` was not
modified.
