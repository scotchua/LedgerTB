# Mutation test report: `services/branding.py`

## Stopped before mutation

The module cannot be imported or exercised offline with the available Python
interpreters. Importing `services.branding` stops in `config.py` because
`platformdirs` is missing. Loading `tests/conftest.py` fails for the same reason.
The task forbids package installation and requires stopping at this condition.

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | Not measurable | Not measurable |

No mutants were run, no survivors were classified, and no new tests were added.
The requested full suite could not start because its `conftest.py` import failed.
