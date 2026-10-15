# Mutation sweep: `services/import_identity.py`

## Stopped early

The available Python environment cannot import `services.import_identity` offline.
`python3 -c 'import services.import_identity'` fails while importing `config.py`
because `platformdirs` is not installed. The relevant pytest selection also stops
while loading `tests/conftest.py` for the same reason. The requested command,
`python -m pytest -q -m "not performance"`, cannot start because `python` is not
on `PATH`; `python3 -m pytest` reaches the missing dependency instead.

The brief requires stopping when the module cannot be imported or exercised
offline without changing production code. No packages were installed and no
production code was changed.

## Results

| Measure | Before new tests | After new tests |
| --- | ---: | ---: |
| Mutants generated | 0 | 0 |
| Mutants killed | 0 | 0 |
| Kill rate | Not measurable | Not measurable |

Survivors: none generated. New tests: none. Defects found: none assessed.
