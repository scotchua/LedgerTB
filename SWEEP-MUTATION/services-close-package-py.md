# Mutation test report: `services/close_package.py`

## Escalation

The module cannot be imported or exercised offline in the available Python environments. `python3 -m pytest -q tests/test_close_package.py -m "not performance"` fails while loading `tests/conftest.py`: `ModuleNotFoundError: No module named 'platformdirs'`. A direct `import services.close_package` fails at the same dependency before this module loads. The available Python 3.11 environment also lacks pytest and the module's dependencies. Package installation is prohibited for this task.

## Mutation results

| Measure | Before new tests | After new tests |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | Not measurable | Not measurable |

No mutation runner was retained or run. There are no survivors to classify and no new test names. The original module and all production files were left unchanged.

## Defects found

None assessed; execution stopped before mutation testing.
