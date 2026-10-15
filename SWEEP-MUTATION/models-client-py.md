# models/client.py mutation test report

Source SHA-256 before and after: `2f0654ad8fd6e44830d5eeed6ff766accb8d36b56c3e6a8925d38d411627e0dc`. The runner loaded each mutated copy in memory and checked the original file after every AST mutant and after the final targeted mutants.

## Kill rates

| Test set | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Existing `tests/test_client_model.py` cases | 38 | 59 | 64.4% |
| Existing cases plus new client mutation tests | 59 | 59 | 100.0% |

The existing test functions were invoked against a temporary SQLite book with isolated import stubs. Each parametrized accounting-basis case was invoked separately. Each mutant ran in its own process with a 10-second timeout. This measures the existing assertions, but it is not a normal pytest collection run.

## Mutants generated

59 mutations (55 AST generated, 4 targeted source edits) cover `_from_row`, `get_all`, `get_by_id`, `save` (including `audit_snapshot`), `categorization_context`, `deactivate`, `has_transactions`, and `get_first`. Candidate sites came only from executable AST nodes, so comments, docstrings, and logging were excluded. The set includes comparison flips, `and`/`or` swaps, condition negations, numeric changes by one, return replacement, statement removal, and `+`/`-` swaps. The four targeted edits exercised an exception raise, a false return, an empty return, and transaction commit removal.

| ID | Function:line | Change | Before | After |
| --- | --- | --- | --- | --- |
| M001 | `_from_row:34` | return None | killed | killed |
| M002 | `get_all:59` | negate condition | survived | killed |
| M003 | `get_all:60` | remove statement | survived | killed |
| M004 | `get_all:62` | remove statement | survived | killed |
| M005 | `get_all:63` | remove statement | killed | killed |
| M006 | `get_all:64` | return None | killed | killed |
| M007 | `get_by_id:70` | remove statement | killed | killed |
| M008 | `get_by_id:71` | remove statement | killed | killed |
| M009 | `get_by_id:72` | return None | killed | killed |
| M010 | `save:86` | remove statement | killed | killed |
| M011 | `save:86` | flip comparison | killed | killed |
| M012 | `save:87` | negate condition | killed | killed |
| M013 | `save:88` | remove statement | killed | killed |
| M014 | `save:89` | remove statement | killed | killed |
| M015 | `save:89` | flip comparison | killed | killed |
| M016 | `save:90` | remove statement | killed | killed |
| M017 | `save.audit_snapshot:93` | remove statement | killed | killed |
| M018 | `save.audit_snapshot:94` | return None | survived | killed |
| M019 | `save.audit_snapshot:103` | numeric +1 | survived | killed |
| M020 | `save:115` | remove statement | killed | killed |
| M021 | `save:117` | remove statement | killed | killed |
| M022 | `save:123` | negate condition | killed | killed |
| M023 | `save:124` | remove statement | killed | killed |
| M024 | `save:133` | swap + and - | killed | killed |
| M025 | `save:136` | remove statement | killed | killed |
| M026 | `save:138` | remove statement | survived | killed |
| M027 | `save:139` | remove statement | killed | killed |
| M028 | `save:140` | negate condition | survived | killed |
| M029 | `save:141` | remove statement | survived | killed |
| M030 | `save:142` | remove statement | killed | killed |
| M031 | `save:151` | swap + and - | killed | killed |
| M032 | `save:151` | swap + and - | killed | killed |
| M033 | `save:156` | negate condition | killed | killed |
| M034 | `save:156` | swap and/or | survived | killed |
| M035 | `save:157` | remove statement | killed | killed |
| M036 | `save:160` | swap and/or | survived | killed |
| M037 | `categorization_context:212` | remove statement | killed | killed |
| M038 | `categorization_context:213` | negate condition | killed | killed |
| M039 | `categorization_context:214` | remove statement | killed | killed |
| M040 | `categorization_context:215` | negate condition | killed | killed |
| M041 | `categorization_context:216` | remove statement | killed | killed |
| M042 | `categorization_context:217` | remove statement | killed | killed |
| M043 | `categorization_context:217` | swap and/or | killed | killed |
| M044 | `categorization_context:218` | negate condition | killed | killed |
| M045 | `categorization_context:219` | remove statement | killed | killed |
| M046 | `deactivate:224` | remove statement | survived | killed |
| M047 | `deactivate:225` | remove statement | survived | killed |
| M048 | `has_transactions:231` | remove statement | survived | killed |
| M049 | `has_transactions:235` | return None | survived | killed |
| M050 | `has_transactions:235` | flip comparison | survived | killed |
| M051 | `has_transactions:235` | numeric +1 | survived | killed |
| M052 | `has_transactions:235` | numeric +1 | survived | killed |
| M053 | `get_first:240` | remove statement | survived | killed |
| M054 | `get_first:241` | return None | survived | killed |
| M055 | `get_first:241` | numeric +1 | survived | killed |
| M056 | `save:199` | drop raise | killed | killed |
| M057 | `get_first:241` | return False | survived | killed |
| M058 | `categorization_context:220` | return empty | killed | killed |
| M059 | `save:195` | remove commit statement | killed | killed |

## New tests and witness mutants

| Function | New test | Recorded mutant it kills |
| --- | --- | --- |
| `_from_row` | `test_from_row_handles_legacy_optional_columns` | M001 |
| `get_all` | `test_get_all_filters_inactive_and_orders_by_name` | M002 |
| `get_by_id` | `test_get_by_id_returns_none_for_missing_client` | M009 |
| `save` | `test_save_preserves_caller_transaction_and_audit_snapshot` | M019 |
| `save` | `test_save_update_records_old_and_new_values` | M026 |
| `save` | `test_save_seeds_only_new_clients_when_requested_with_defaults` | M034, M036 |
| `categorization_context` | `test_categorization_context_uses_only_opted_in_fields` | M037 |
| `deactivate` | `test_deactivate_persists_inactive_state` | M046 |
| `has_transactions` | `test_has_transactions_checks_requested_client_and_zero_boundary` | M050 |
| `get_first` | `test_get_first_returns_first_active_client_or_none` | M055, M057 |

All ten new tests passed on the original source and each failed on its listed mutant. The 21 mutants surviving the existing assertions were M002, M003, M004, M018, M019, M026, M028, M029, M034, M036, M046, M047, M048, M049, M050, M051, M052, M053, M054, M055, and M057; all were killed after the new tests.

## Survivors left

None. Equivalent: none identified. Untestable offline: none in the selected set. Defects found: none; no expected failures were added.

## Verification limit

The requested full pytest command could not collect tests in this environment. `python` is unavailable; `python3 -m pytest -q -m "not performance"` stops while importing `tests/conftest.py` because the environment lacks `platformdirs` and `pandas` (a temporary `platformdirs` import shim exposed the latter). No packages were installed and no network calls were made. The isolated original-source run of all ten new tests passed.
