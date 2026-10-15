# services/backups.py mutation sweep

## Stopped before mutation

The offline test environment cannot import `services.backups` or collect its
existing tests. The available `python3` has no `platformdirs`; direct import
stops in `config.py`. A temporary `platformdirs` shim outside the worktree
exposed another missing dependency, `pandas`, through `models/reports.py`.
Installing packages is prohibited for this task. The required existing-test
baseline and mutant runs therefore could not be performed.

| Measure | Result |
| --- | --- |
| Mutants generated | 0 |
| Killed before new tests | 0 / 0 (rate undefined) |
| Killed after new tests | 0 / 0 (rate undefined) |
| Survivors left | 0 recorded; no mutants were run |
| New tests | None |

No equivalent, untestable, or defect mutants were identified. No production
file was changed. `services/backups.py` SHA-256 remained
`296d6ed0aae31e22d88358505193a86948c6301e36f5c696842981022b148951`.

## Verification attempted

- `python3 -m pytest -q tests/test_backups.py tests/test_passphrase_change.py -m 'not performance'`: collection stopped at missing `platformdirs`.
- `python3 -m pytest -q tests/test_backups.py -m 'not performance'` with a temporary `platformdirs` shim: collection stopped at missing `pandas`.
- `python3 -c 'import services.backups'`: import stopped at missing `platformdirs`; with the same temporary shim, it stopped at missing `pandas`.
- `python -m pytest -q -m "not performance"` could not run because this environment has no `python` command. The available `python3` cannot collect the suite for the dependency reasons above.
