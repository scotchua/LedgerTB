# AI provider module mutation sweep

## Status

Stopped before mutation generation. The repository's Python environment cannot
import or exercise `services.ai_providers` through the existing test suite
offline: `platformdirs`, a required package imported by `config.py`, is not
installed. No packages were installed and no production code was changed.

## Evidence

- `python3 -c 'import services.ai_providers'` fails with
  `ModuleNotFoundError: No module named 'platformdirs'` while importing
  `config.py` through `services/__init__.py`.
- `python3 -m pytest -q -m 'not performance' tests/test_categorization.py`
  fails while loading `tests/conftest.py` with the same missing package.
- The available `/usr/bin/python3` and `/usr/local/bin/python3` also lack
  `platformdirs`.

## Mutation results

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | Not measured; 0/0 |
| Killed after new tests | Not measured; 0/0 |
| Survivors left | None generated |
| New tests | None |

## Defects found

None assessed.

The throwaway mutation runner was not created because the escalation condition
fired before mutation testing could begin.
