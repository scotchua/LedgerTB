# `utils/books.py` mutation test

The runner generated 54 one-change AST mutants across all six functions and
the module-level recent-book limit. It executed each in a fresh Python process
with a 15-second timeout. The original `utils/books.py` was read into memory
and never written. Mutations targeted comparisons, `or`, conditions, integer
constants, return values, arithmetic, and individual statements. There is no
explicit `raise` statement in this module to drop. Comments and docstrings
were excluded.

The offline harness supplied a minimal `config` module and selected the three
existing direct tests in `tests/test_books.py`: registry round trip, legacy
environment override, and local-book detection. It used `--noconftest` because
the available Python environment lacks `platformdirs`. The after run added
`tests/test_books_mutation.py`. The original module passed all three selected
tests before and all nine selected tests after.

| Area | Mutants generated | Killed before | Killed after |
| --- | --- | ---: | ---: |
| `MAX_RECENT` | M001 | 0/1 | 1/1 |
| `_load` | M023–M025, M042–M044 | 6/6 | 6/6 |
| `_save` | M002–M006, M026–M029, M045, M051, M054 | 6/12 | 12/12 |
| `active_book` | M007–M011, M030–M033 | 9/9 | 9/9 |
| `is_local_book` | M034–M039, M046–M048, M052 | 8/10 | 10/10 |
| `set_active_book` | M012–M018, M049, M053 | 9/9 | 9/9 |
| `recent_books` | M019–M022, M040–M041, M050 | 7/7 | 7/7 |
| **Total** | **54** | **45/54 (83.3%)** | **54/54 (100%)** |

The nine initially surviving mutants and the tests that killed them:

| Mutant | Change | New test |
| --- | --- | --- |
| M001 | Raise the recent-book limit from 8 to 9 | `test_set_active_book_keeps_eight_recent_books` |
| M002 | Remove registry parent directory creation | `test_save_creates_private_registry_directory` |
| M026 | Remove parent directory permission restriction | `test_save_restricts_existing_registry_directory` |
| M029 | Remove temporary file descriptor close | `test_save_closes_temporary_file` |
| M045 | Change file creation mode from `0o600` to `0o601` | `test_save_creates_private_registry_directory` |
| M047 | Return `None` after a path resolution error | `test_is_local_book_returns_false_when_path_resolution_fails` |
| M048 | Return an empty list after a path resolution error | `test_is_local_book_returns_false_when_path_resolution_fails` |
| M051 | Change directory mode from `0o700` to `0o701` | `test_save_creates_private_registry_directory` |
| M054 | Change JSON indentation from 2 to 3 spaces | `test_save_uses_stable_json_format` |

Survivors left: none. Equivalent mutants: none. Untestable offline mutants:
none. Defects found: none. No expected failures were added.

The requested full-suite verification, `python3 -m pytest -q -m 'not
performance'`, stopped while loading `tests/conftest.py` because the installed
interpreter has no `platformdirs` package. The normal suite therefore could
not be evaluated in this environment. The isolated nine-test baseline and
all 54 mutant runs completed offline.
