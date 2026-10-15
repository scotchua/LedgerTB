# Mutation results: `utils/client_context.py`

## Method and result

- Source: `utils/client_context.py`; SHA-256 after both runs: `fcc37d34cb35e0a9b92390b8578a556fd6f3135c0a65a60cb727e97b32bbba32`. The runner checked byte identity after each complete run; the source was never written by the runner.
- Each mutant was made from the parsed source in a temporary file and preloaded as `utils.client_context` for an isolated `pytest` subprocess. Each subprocess had an 8-second limit. No run timed out.
- The focused test command was `python3 -m pytest -q --noconftest tests/test_client_context.py`. Shared `tests/conftest.py` could not load without the unavailable `platformdirs` dependency.
- Operators: flip `<`, `<=`, `>`, `>=`, `==`, `!=` where present; swap `and`/`or`; negate `if` tests; shift integer constants by one; replace returns with `None`, empty string, or `False`; remove one statement; swap `+`/`-`. Comments, docstrings, and logging were skipped. There is no `raise` statement in this module to drop.
- Coverage: 79 unique valid mutants (cap: 150), across all eight functions or methods. Mutants are generated independently from the original source.

| Stage | Killed | Survived | Kill rate |
| --- | ---: | ---: | ---: |
| Existing tests | 61 | 18 | 77.2% |
| With new tests | 79 | 0 | 100.0% |

## New tests

Each named test passed on the original and failed in an isolated run against at least the listed mutant.

| Test | Mutant verified |
| --- | ---: |
| `test_book_identity_falls_back_when_resolution_fails` | 5 |
| `test_book_scoped_key_uses_twelve_hex_digits` | 12 |
| `test_active_context_initializes_and_counts_each_switch` | 22 |
| `test_active_context_recovers_missing_generation_on_switch` | 25 |
| `test_page_scope_updates_app_context` | 40 |
| `test_page_scope_recovers_missing_generation_on_switch` | 50 |
| `test_client_intent_returns_default_for_missing_and_stale_values` | 68 |

## Survivors left

None. Equivalent: none; untestable offline: none; defect: none.

## Defects found

None.

## Full-suite verification

`python3 -m pytest -q -m "not performance"` could not collect tests: `tests/conftest.py` imports `config.py`, which requires `platformdirs` (`ModuleNotFoundError`). The requested `python` executable is also unavailable; `python3` was used. No packages were installed.

## Mutant inventory

| ID | Function | Source line | Mutation | Before | After |
| ---: | --- | ---: | --- | --- | --- |
| 1 | `_book_identity` | 24 | remove statement | killed | killed |
| 2 | `_book_identity` | 26 | return None | killed | killed |
| 3 | `_book_identity` | 26 | return empty | killed | killed |
| 4 | `_book_identity` | 26 | return False | killed | killed |
| 5 | `_book_identity` | 28 | return None | survived | killed |
| 6 | `_book_identity` | 28 | return empty | survived | killed |
| 7 | `_book_identity` | 28 | return False | survived | killed |
| 8 | `client_context_identity` | 33 | return None | killed | killed |
| 9 | `client_context_identity` | 33 | return empty | killed | killed |
| 10 | `client_context_identity` | 33 | return False | killed | killed |
| 11 | `book_scoped_key` | 43 | remove statement | killed | killed |
| 12 | `book_scoped_key` | 43 | constant -1 | survived | killed |
| 13 | `book_scoped_key` | 43 | constant +1 | survived | killed |
| 14 | `book_scoped_key` | 44 | return None | killed | killed |
| 15 | `book_scoped_key` | 44 | return empty | killed | killed |
| 16 | `book_scoped_key` | 44 | return False | killed | killed |
| 17 | `sync_active_client_context` | 53 | remove statement | killed | killed |
| 18 | `sync_active_client_context` | 54 | remove statement | killed | killed |
| 19 | `sync_active_client_context` | 55 | remove statement | killed | killed |
| 20 | `sync_active_client_context` | 55 | swap and/or | killed | killed |
| 21 | `sync_active_client_context` | 55 | flip comparison | killed | killed |
| 22 | `sync_active_client_context` | 56 | negate condition | survived | killed |
| 23 | `sync_active_client_context` | 57 | remove statement | killed | killed |
| 24 | `sync_active_client_context` | 58 | swap +/- | killed | killed |
| 25 | `sync_active_client_context` | 58 | constant -1 | survived | killed |
| 26 | `sync_active_client_context` | 58 | constant +1 | survived | killed |
| 27 | `sync_active_client_context` | 58 | constant -1 | survived | killed |
| 28 | `sync_active_client_context` | 58 | constant +1 | survived | killed |
| 29 | `sync_active_client_context` | 61 | remove statement | survived | killed |
| 30 | `sync_active_client_context` | 61 | constant -1 | killed | killed |
| 31 | `sync_active_client_context` | 61 | constant +1 | killed | killed |
| 32 | `sync_active_client_context` | 62 | remove statement | killed | killed |
| 33 | `sync_active_client_context` | 63 | return None | killed | killed |
| 34 | `sync_active_client_context` | 63 | return empty | killed | killed |
| 35 | `sync_active_client_context` | 63 | return False | killed | killed |
| 36 | `key` | 77 | return None | killed | killed |
| 37 | `key` | 77 | return empty | killed | killed |
| 38 | `key` | 77 | return False | killed | killed |
| 39 | `scope_page_to_client` | 92 | remove statement | killed | killed |
| 40 | `scope_page_to_client` | 93 | remove statement | survived | killed |
| 41 | `scope_page_to_client` | 95 | remove statement | killed | killed |
| 42 | `scope_page_to_client` | 96 | remove statement | killed | killed |
| 43 | `scope_page_to_client` | 97 | remove statement | killed | killed |
| 44 | `scope_page_to_client` | 98 | remove statement | killed | killed |
| 45 | `scope_page_to_client` | 98 | swap and/or | killed | killed |
| 46 | `scope_page_to_client` | 98 | flip comparison | killed | killed |
| 47 | `scope_page_to_client` | 99 | negate condition | killed | killed |
| 48 | `scope_page_to_client` | 100 | remove statement | killed | killed |
| 49 | `scope_page_to_client` | 100 | swap +/- | killed | killed |
| 50 | `scope_page_to_client` | 100 | constant -1 | survived | killed |
| 51 | `scope_page_to_client` | 100 | constant +1 | survived | killed |
| 52 | `scope_page_to_client` | 100 | constant -1 | survived | killed |
| 53 | `scope_page_to_client` | 100 | constant +1 | survived | killed |
| 54 | `scope_page_to_client` | 102 | remove statement | killed | killed |
| 55 | `scope_page_to_client` | 102 | constant -1 | killed | killed |
| 56 | `scope_page_to_client` | 102 | constant +1 | killed | killed |
| 57 | `scope_page_to_client` | 103 | remove statement | killed | killed |
| 58 | `scope_page_to_client` | 105 | return None | killed | killed |
| 59 | `scope_page_to_client` | 105 | return empty | killed | killed |
| 60 | `scope_page_to_client` | 105 | return False | killed | killed |
| 61 | `set_client_intent` | 127 | remove statement | killed | killed |
| 62 | `pop_client_intent` | 141 | remove statement | killed | killed |
| 63 | `pop_client_intent` | 142 | negate condition | killed | killed |
| 64 | `pop_client_intent` | 142 | swap and/or | killed | killed |
| 65 | `pop_client_intent` | 142 | flip comparison | killed | killed |
| 66 | `pop_client_intent` | 142 | constant -1 | killed | killed |
| 67 | `pop_client_intent` | 142 | constant +1 | killed | killed |
| 68 | `pop_client_intent` | 143 | return None | survived | killed |
| 69 | `pop_client_intent` | 143 | return empty | killed | killed |
| 70 | `pop_client_intent` | 143 | return False | killed | killed |
| 71 | `pop_client_intent` | 144 | remove statement | killed | killed |
| 72 | `pop_client_intent` | 145 | negate condition | killed | killed |
| 73 | `pop_client_intent` | 145 | flip comparison | killed | killed |
| 74 | `pop_client_intent` | 146 | return None | survived | killed |
| 75 | `pop_client_intent` | 146 | return empty | killed | killed |
| 76 | `pop_client_intent` | 146 | return False | killed | killed |
| 77 | `pop_client_intent` | 147 | return None | killed | killed |
| 78 | `pop_client_intent` | 147 | return empty | killed | killed |
| 79 | `pop_client_intent` | 147 | return False | killed | killed |
