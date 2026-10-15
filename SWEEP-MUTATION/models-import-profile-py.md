# Mutation probe: `models/import_profile.py`

## Method and rates

The throwaway runner made 27 single-change mutants in temporary files and loaded them into separate, eight-second-boxed pytest processes. It attempted `tests/test_import_profiles.py` against every mutant through an import hook. Every attempt stopped during `tests/conftest.py` import: the installed Python lacks `platformdirs`. The existing-suite **before kill rate is unmeasurable** (0 observed kills out of 27 attempts; 27 collection errors). Counting those collection errors as kills would be incorrect.

The standalone offline tests in `tests/test_import_profile_mutations.py` use an invented in-memory account/profile database and an audit stub. Their first pass killed **24/26 mutants (92.3%)**; M06 and M26 survived and prompted two tests. A boundary-constant mutant, M27, was then added. On the final 27-mutant set, the added tests killed **27/27 (100%)**. All 15 tests pass on the original module. The true combined-suite before-to-after improvement cannot be quantified until the project dependencies are available.

The runner compared `models/import_profile.py` byte for byte with its initial read after all runs. Its final SHA-256 was `c083b371b3bbcdff18d2e479121097eac17a1d1c19ae3ec3cfe203a40daae2c1`. No production file was edited. No package was installed and no network or API call was made.

## Generated mutants

All entries below were killed by the added tests in the final run. The existing-test result for each was a collection error, not a test outcome.

| ID | Function | One change |
| --- | --- | --- |
| M01 | `_from_row` | Read account ID from the client ID field |
| M02 | `_from_row` | Replace creation timestamp with `None` |
| M03 | `validate` | Reject an 80-character name (`>` to `>=`) |
| M04 | `validate` | Require both IDs missing before raising (`or` to `and`) |
| M05 | `validate` | Remove clearing of the unused debit column |
| M06 | `validate` | Require both separate amount columns (`and` to `or`) |
| M07 | `signature_for_columns` | Return `None` |
| M08 | `save` | Reverse the saved-ID presence condition |
| M09 | `save` | Reverse the missing-old-row condition |
| M10 | `save` | Reverse the missing-account condition |
| M11 | `save` | Reject eligible account types (`not in` to `in`) |
| M12 | `save` | Reverse the duplicate-name condition |
| M13 | `save` | Reverse update versus insert selection |
| M14 | `save` | Return `None` instead of the saved ID |
| M15 | `save` | Omit the amount column from new audit values |
| M16 | `get_by_id` | Always return `None` |
| M17 | `list_for_account` | Always return an empty list |
| M18 | `match_for_columns` | Reverse the single-exact-match comparison |
| M19 | `match_for_columns` | Select profiles with missing columns |
| M20 | `match_for_columns` | Reverse the single-compatible-match comparison |
| M21 | `delete` | Treat an existing row as missing |
| M22 | `delete` | Return `False` after deletion |
| M23 | `resolve_columns` | Mark present columns as missing |
| M24 | `resolve_columns` | Apply saved mapping when columns are missing |
| M25 | `resolve_columns` | Reverse detected single/separate amount selection |
| M26 | `validate` | Drop the invalid-sign-convention exception raise |
| M27 | `validate` | Increase the name-length limit from 80 to 81 |

The generated set covers every function in the module. It includes comparison changes, `and`/`or` swaps, condition negations, a numeric constant increment, return replacements, one removed assignment, and one dropped exception raise. The module has no executable `+` or `-` expression to swap. Comments, logging, and docstrings were not mutation targets. The cap was 150; 27 mutants were generated.

## New tests

Each test below failed on at least one recorded mutant and passed on the original module:

| Function | Test names |
| --- | --- |
| `_from_row` | `test_from_row_preserves_all_saved_fields` |
| `validate` | `test_validate_rejects_boundary_length_and_missing_account`, `test_validate_clears_unused_columns_and_requires_separate_amount`, `test_validate_accepts_one_separate_amount_column`, `test_validate_rejects_unknown_sign_convention` |
| `signature_for_columns` | `test_signature_distinguishes_header_order_and_escaping` |
| `save` | `test_save_requires_existing_profile_and_eligible_account`, `test_save_updates_exact_record_and_audits_new_values` |
| `get_by_id` | `test_get_by_id_rejects_other_client_and_unknown_id` |
| `list_for_account` | `test_list_for_account_orders_names_and_scopes_account` |
| `match_for_columns` | `test_match_for_columns_prefers_exact_and_rejects_ambiguous`, `test_match_for_columns_accepts_one_compatible_legacy_profile` |
| `delete` | `test_delete_removes_only_requested_profile_and_audits` |
| `resolve_columns` | `test_resolve_columns_applies_separate_mapping_and_falls_back`, `test_resolve_columns_uses_detected_single_amount` |

## Survivors and defects

Final surviving mutants: **none**. Equivalent mutants: **none identified**. Mutants untestable offline: **none in the standalone harness**. Defects found: **none**. M06 and M26 were real-behavior survivors in the first pass and are killed by the new validation tests.

## Verification limit

`python3 -m pytest -q --noconftest tests/test_import_profile_mutations.py`: **15 passed**. `python3 -m pytest -q -m 'not performance'`: **collection error**, `ModuleNotFoundError: No module named 'platformdirs'` from `tests/conftest.py`. The requested `python` executable is absent; `python3` was used. The full suite result remains unknown in this environment.
