# `utils/ui.py` mutation sweep

## Method and result

The sweep generated 38 single-edit AST mutants across all seven functions, below the 150-mutant cap. It changed a temporary copy, loaded each variant into `utils.ui` in memory, and time-boxed each pytest run at 15 seconds. `utils/ui.py` was never written and remained byte-identical (SHA-256 `02525a9a6271db726e86cb093343c5021dd33d502ddc41b110b40c3928381eb4`). Comments, CSS, docstrings, and logging were excluded. There is no `raise` statement in the module, so no exception-raise deletion was possible.

The baseline used 13 existing `statement_html` tests from `tests/test_statement_presentation.py`. The other directly relevant existing test modules and the full suite cannot load in this offline environment: `streamlit` and `platformdirs` are missing. The baseline loaded a minimal in-memory Streamlit stub and disabled repository `conftest.py`; the new tests use the same baseline. This is a measured kill rate for the runnable existing tests, not a claim about the unavailable full suite.

| Stage | Killed | Generated | Kill rate | Survived |
| --- | ---: | ---: | ---: | ---: |
| Existing runnable tests | 14 | 38 | 36.8% | 24 |
| Existing plus new tests | 38 | 38 | 100% | 0 |

`python3 -m pytest -q -m 'not performance'` stopped during `tests/conftest.py` import with `ModuleNotFoundError: platformdirs`. The requested `python -m pytest -q -m "not performance"` could not start because this environment has no `python` command. The isolated original-code run of the new test file passed: 8 passed.

## Mutant inventory

`K` means killed; `S` means survived. Line numbers refer to the unchanged source.

| ID | Function:line | Single edit | Before | After |
| --- | --- | --- | :---: | :---: |
| M01 | `apply_default_on_change:54` | `!=` to `==` | S | K |
| M02 | `apply_default_on_change:55` | Remove dependency tracker assignment | S | K |
| M03 | `apply_default_on_change:56` | Remove widget value assignment | S | K |
| M04 | `view_switcher:76` | `not in` to `in` | S | K |
| M05 | `view_switcher:77` | Remove invalid-selection fallback | S | K |
| M06 | `view_switcher:78` | `!=` to `==` | S | K |
| M07 | `view_switcher:79` | Remove widget synchronization | S | K |
| M08 | `view_switcher:83` | Remove style rendering | S | K |
| M09 | `view_switcher:87` | Remove plain selection update | S | K |
| M10 | `view_switcher:88` | Remove rendered-selection update | S | K |
| M11 | `view_switcher:89` | Return `None` | S | K |
| M12 | `external_link_button:105` | Negate button condition | S | K |
| M13 | `external_link_button:108` | Remove browser opening | S | K |
| M14 | `is_parking_account:116` | `or` to `and` in label fallback | S | K |
| M15 | `is_parking_account:116` | Return `False` | S | K |
| M16 | `is_parking_account:116` | Return `None` | S | K |
| M17 | `statement_html:177` | Row length `> 2` to `>= 2` | S | K |
| M18 | `statement_html:177` | `and` to `or` in column discovery | K | K |
| M19 | `statement_html:178` | `+` to `-` in format padding | K | K |
| M20 | `statement_html:181` | Negate header condition | K | K |
| M21 | `statement_html:183` | Remove header-row append | K | K |
| M22 | `statement_html:184` | `+` to `-` in label column count | K | K |
| M23 | `statement_html:192` | Negate link condition | K | K |
| M24 | `statement_html:193` | Remove escaped-link assignment | S | K |
| M25 | `statement_html:202` | Negate note condition | K | K |
| M26 | `statement_html:204` | `==` to `!=` for note rows | K | K |
| M27 | `statement_html:211` | `+` to `-` in amount padding | K | K |
| M28 | `statement_html:216` | `and` to `or` for numbered items | K | K |
| M29 | `statement_html:223` | `>=` to `>` for wide layout | K | K |
| M30 | `statement_html:226` | Return `None` | K | K |
| M31 | `financial_statement:253` | Remove `st.html` call | S | K |
| M32 | `ledger_table:298` | `==` to `!=` for right alignment | S | K |
| M33 | `ledger_table:303` | `or` to `and` for default row classes | S | K |
| M34 | `ledger_table:308` | `is not None` to `is None` | S | K |
| M35 | `ledger_table:309` | Remove total-row append | S | K |
| M36 | `ledger_table:310` | Remove `st.html` call | S | K |
| M37 | `statement_html:223` | Wide-layout threshold `4` to `5` | K | K |
| M38 | `statement_html:226` | Return empty string | K | K |

## New tests

All are in `tests/test_ui_mutation.py`. Each passed on the original and failed on at least one recorded mutant:

| Test | Mutants killed |
| --- | --- |
| `test_apply_default_on_change_tracks_dependency_and_updates_value` | M01–M03 |
| `test_view_switcher_syncs_programmatic_selection_and_user_click` | M04–M11 |
| `test_external_link_button_opens_only_after_click` | M12–M13 |
| `test_is_parking_account_returns_a_boolean_for_each_label` | M14–M16 |
| `test_statement_html_accepts_a_short_note_row_and_escapes_links` | M17, M24 |
| `test_financial_statement_sends_markup_to_streamlit` | M31 |
| `test_ledger_table_renders_rows_with_alignment_and_default_classes` | M32–M34, M36 |
| `test_ledger_table_renders_optional_total` | M32–M36 |

## Survivors left

None. No equivalent, untestable-offline, or defect mutants remain in this selected set.

## Defects found

None. No expected-failure test was needed.
