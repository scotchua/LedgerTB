# Mutation sweep: `utils/assistant_access.py`

The sweep generated 31 single-edit, syntax-valid mutants across all three functions. Each mutant ran in a fresh Python process with a 10-second timeout. The runner loaded mutant source into an isolated module and ran a copy of `tests/test_assistant_access.py` with a temporary fake credential vault. It did not write to the production module. AST sites excluded comments and docstrings; the module has no comparisons, boolean operators, arithmetic operators, or raises to mutate.

| Test set | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Existing tests | 19 | 31 | 61.3% |
| Existing and new tests | 31 | 31 | 100% |

`K` means killed; `S` means survived. Every mutant listed below was killed after the new tests.

| Function | Mutant | Before | After |
| --- | --- | --- | --- |
| `book_scope` | Return `None`, empty string, or `False` (3 mutants) | K | K |
| `book_scope` | Change digest slice `32` to `31` | S | K |
| `book_scope` | Change digest slice `32` to `33` | S | K |
| `book_scope` | Remove canonical-path assignment | K | K |
| `credential_names` | Return `None`, empty string, or `False` (3 mutants) | K | K |
| `credential_names` | Replace `key` with `None` | K | K |
| `credential_names` | Replace `key` with empty string | S | K |
| `credential_names` | Replace `key` with `False` | K | K |
| `credential_names` | Replace `level` with `None`, empty string, or `False` (3 mutants) | S | K |
| `credential_names` | Replace `book_id` with `None`, empty string, or `False` (3 mutants) | S | K |
| `credential_names` | Replace `export_roots` with `None`, empty string, or `False` (3 mutants) | S | K |
| `credential_names` | Remove scope assignment | K | K |
| `revoke_legacy_credentials` | Return `None`, empty string, or `False` (3 mutants) | K | K |
| `revoke_legacy_credentials` | Negate the secret-found condition | K | K |
| `revoke_legacy_credentials` | Remove each of five statements in turn: initialize `found`, loop, condition, mark found, delete secret | K | K |

## New tests

- `test_book_scope_is_32_characters_of_canonical_path_hash` kills both digest-slice mutants. In isolation it passed on the original and failed on `book_scope.constant.32-1`.
- `test_credential_names_include_every_book_scoped_secret` kills all ten surviving credential-field mutants. In isolation it passed on the original and failed on `credential_names.level.empty`.

## Survivors left

None. No equivalent mutants, offline-untestable mutants, or defect-indicating mutants remained.

## Defects found

None.

## Verification limit

The isolated original run passed all four tests. The requested full-suite command, `python3 -m pytest -q -m 'not performance'`, stopped while loading `tests/conftest.py`: `ModuleNotFoundError: No module named 'platformdirs'`. The available Python interpreters lack that dependency, and no packages were installed. The full suite could therefore not be verified here.
