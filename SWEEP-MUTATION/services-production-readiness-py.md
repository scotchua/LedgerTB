# Mutation test sweep: `services/production_readiness.py`

## Stopped before mutation

The module cannot be imported or exercised in the available offline Python environment. `python3 -c 'import services.production_readiness'` fails while importing `config.py` with `ModuleNotFoundError: No module named 'platformdirs'`. The relevant existing tests also stop while loading `tests/conftest.py` for the same reason. The requested `python -m pytest -q -m "not performance"` cannot start because this environment has no `python` command. The available `python3` executable cannot load the suite. Package installation is prohibited by the brief.

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | Not measurable | Not measurable |

Survivors left: none generated. New tests: none. Equivalent mutants: none assessed. Untestable offline mutants: none generated. Defects found: none assessed.
