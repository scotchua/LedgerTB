# Mutation probe: `utils/aje_entry_form.py`

## Scope and method

The full 291-line module was read. A search of existing tests found no import or call of `utils.aje_entry_form`, `render_aje_form`, or `render_aje_quick_add`. Thus the relevant pre-existing test set for this module is empty. No existing test expectation was changed.

The temporary runner made 38 single-edit mutants, 30 in `render_aje_form` and 8 in `render_aje_quick_add`, below the 150-mutant cap. It wrote each mutant to a separate temporary Python file, ran the offline tests in a new process with a five-second timeout, and deleted the temporary copy before the next mutant. It never wrote to the production module and checked its bytes afterward. Edits targeted executable code only: comparison flips, `and`/`or` swaps, condition negation, numeric constants changed by one, return replacements with `None`, `[]`, or `False`, single-statement removals, and dropped exception handling. The module contains no explicit `raise` statement or numeric `+`/`-` operation suitable for those mutation operators; its only `+` joins option lists.

## Results

| Stage | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Before new tests | 0 | 38 | 0% |
| After new tests | 38 | 38 | 100% |

All 38 mutants changed observable behavior and were killed. Survivors left: **none**. Equivalent mutants: **none**. Untestable offline mutants: **none**. Defects found: **none**. There are no expected failures.

## Mutants generated

Every ID below was killed after the new tests were added. Before the new tests, all survived because no existing test exercised this module.

| Function | Mutant IDs |
| --- | --- |
| `render_aje_form` | `form_no_accounts_negated`, `form_no_accounts_return_empty`, `form_default_index_plus_one`, `form_prefill_and_to_or`, `form_prefill_negated`, `form_prefill_index_removed`, `form_cancel_negated`, `form_cancel_callback_negated`, `form_cancel_callback_removed`, `form_cancel_return_false`, `form_submit_negated`, `form_line_account_and_to_or`, `form_line_amount_or_to_and`, `form_line_condition_negated`, `form_debit_gt_to_ge`, `form_credit_gt_to_ge`, `form_debit_gt_to_lt`, `form_credit_gt_to_lt`, `form_debit_zero_plus_one`, `form_credit_zero_plus_one`, `form_memo_condition_negated`, `form_source_condition_negated`, `form_line_append_removed`, `form_save_removed`, `form_success_removed`, `form_on_save_negated`, `form_on_save_removed`, `form_return_entry_none`, `form_exception_dropped`, `form_error_removed` |
| `render_aje_quick_add` | `quick_debit_amount_none`, `quick_debit_credit_zero_plus_one`, `quick_credit_debit_zero_plus_one`, `quick_credit_amount_none`, `quick_save_removed`, `quick_return_entry_none`, `quick_exception_dropped`, `quick_error_return_false` |

## New tests and a mutant each killed

All tests are in `tests/test_aje_entry_form_mutations.py`, grouped by function. These examples are from the recorded mutant runs; most tests killed several mutants.

| Test | Example mutant killed |
| --- | --- |
| `AjeFormTests.test_no_accounts_warns_and_does_not_open_form` | `form_no_accounts_return_empty` |
| `AjeFormTests.test_cancel_calls_only_cancel_callback` | `form_cancel_callback_removed` |
| `AjeFormTests.test_save_builds_selected_lines_metadata_and_calls_callback` | `form_prefill_index_removed` |
| `AjeFormTests.test_optional_line_requires_account_and_positive_amount` | `form_line_account_and_to_or` |
| `AjeFormTests.test_positive_optional_credit_is_included` | `form_credit_gt_to_lt` |
| `AjeFormTests.test_save_validation_error_is_shown_and_not_returned` | `form_exception_dropped` |
| `AjeQuickAddTests.test_quick_add_saves_balanced_entry_and_metadata` | `quick_debit_amount_none` |
| `AjeQuickAddTests.test_quick_add_returns_none_on_validation_error` | `quick_exception_dropped` |

## Verification

`python3 -m unittest discover -s tests -p test_aje_entry_form_mutations.py -v` passes all eight tests on the original module. The tests inject local doubles for Streamlit and the imported model modules and make no network or API calls. The requested `python -m pytest -q -m "not performance"` cannot run here because `python` is not on `PATH`. The equivalent available command, `python3 -m pytest -q -m "not performance"`, stops during collection: `tests/conftest.py` imports `config.py`, which raises `ModuleNotFoundError: No module named 'platformdirs'`. No packages were installed. The production module was still importable and exercisable offline through the local doubles, so the escalation condition did not apply.
