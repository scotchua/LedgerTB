# Mutation test sweep: `services/import_corrections.py`

## Stopped before mutation

The service cannot be imported or exercised with the available offline Python environment. `python3 -c 'import services.import_corrections'` fails with `ModuleNotFoundError: No module named 'platformdirs'` while importing `config.py`. The relevant test command, `python3 -m pytest -q tests/test_import_corrections.py tests/test_import_batch_reversal.py -m 'not performance'`, fails during `tests/conftest.py` import for the same reason. The requested `python -m pytest -q -m "not performance"` cannot run because `python` is not on `PATH`; `python3` cannot collect tests for the reason above. No packages were installed and no network calls were made.

## Results

| Measure | Before new tests | After new tests |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | N/A | N/A |

No mutation runner or new tests were created. There are no survivors to classify, no equivalent mutants, no new test names, and no defects found. Mutation testing can resume when the existing project dependencies are available offline.
