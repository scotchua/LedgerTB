# Mutation test report: `models/audit_log.py`

## Method

- Source SHA-256 before and after: `50f4e3609d86025a21aeffa034f0053533c216969189e1c8b8142a2aa3ddfc22`. The runner loaded each one-change mutant from a unique temporary file; it never wrote to the production module.
- Forty mutants cover all 16 methods. Operators include comparison flips (including inclusive SQL boundaries), `and`/`or`, condition negation, a numeric constant increased by one, return replacement, one removed statement, `+` to `-`, and a dropped exception raise. Comments, logging calls, and docstrings were excluded. Each subprocess had an eight-second timeout.
- Before: six test functions from `tests/test_audit_log.py` were executed from their original function bodies in a temporary SQLite harness. The harness only supplied an in-memory connection and injected the audit class; it did not run the full app fixtures. The functions were `test_get_all_finds_same_day_entries`, `test_get_all_excludes_entries_outside_range`, `test_get_earliest_date`, `test_log_change_safe_swallows_and_logs_failure`, `test_operational_event_actions_are_supported`, and `test_changed_at_is_local_not_utc`.
- After: `python3 -m pytest -q --noconftest tests/test_audit_log_mutations.py` ran the new dependency-light tests against each mutant. The normal suite could not collect because `platformdirs` is absent in this offline interpreter.

## Kill rates

| Test set | Killed | Total | Kill rate |
| --- | ---: | ---: | ---: |
| Selected existing tests in offline harness | 18 | 40 | 45% |
| Selected existing tests plus new tests | 40 | 40 | 100% |

## Mutants generated

| ID | Function | Mutation | Before | After |
| --- | --- | --- | --- | --- |
| M01 | `get_session_id` | invert session cache guard | survived | killed |
| M02 | `_current_session_id` | invert app context guard | survived | killed |
| M03 | `_current_session_id` | lose app session result | survived | killed |
| M04 | `_json` | invert null guard | killed | killed |
| M05 | `_json` | disable stable key order | survived | killed |
| M06 | `write` | invert action validation | killed | killed |
| M07 | `write` | drop invalid action exception | survived | killed |
| M08 | `write` | lose old values | survived | killed |
| M09 | `write` | lose new values | killed | killed |
| M10 | `write` | ignore supplied session | survived | killed |
| M11 | `write` | lose inserted id | killed | killed |
| M12 | `log_change` | lose returned id | killed | killed |
| M13 | `log_event` | lose event mapping | killed | killed |
| M14 | `log_change_safe` | lose successful id | killed | killed |
| M15 | `log_change_safe` | false on audit failure | killed | killed |
| M16 | `get_by_id` | invert row presence | killed | killed |
| M17 | `get_by_id` | lose fetched row | killed | killed |
| M18 | `get_earliest_date` | swap nullable row conjunction | killed | killed |
| M19 | `get_earliest_date` | lose earliest timestamp | killed | killed |
| M20 | `get_history` | lose history results | survived | killed |
| M21 | `get_history` | remove row append | survived | killed |
| M22 | `get_all` | minimum page size plus one | survived | killed |
| M23 | `get_all` | minimum offset plus one | killed | killed |
| M24 | `get_all` | lose filtered rows | killed | killed |
| M25 | `_filter_sql` | negate start bound | killed | killed |
| M26 | `_filter_sql` | negate end bound | survived | killed |
| M27 | `_filter_sql` | negate table filter | killed | killed |
| M28 | `_filter_sql` | negate action filter | killed | killed |
| M29 | `_filter_sql` | negate text filter | killed | killed |
| M30 | `_filter_sql` | lose search parameters | survived | killed |
| M31 | `get_filtered_counts` | lose count result | survived | killed |
| M32 | `get_entry_changes` | lose entry results | survived | killed |
| M33 | `format_changes` | invert insert action | survived | killed |
| M34 | `format_changes` | invert update difference | survived | killed |
| M35 | `format_changes` | subtract update key lists | survived | killed |
| M36 | `format_changes` | lose update fallback | survived | killed |
| M37 | `_format_values` | invert internal key exclusion | survived | killed |
| M38 | `_format_values` | lose formatted text | survived | killed |
| M39 | `_filter_sql` | exclude exact start boundary | survived | killed |
| M40 | `_filter_sql` | exclude exact end boundary | survived | killed |

## Survivors left

None: 0 equivalent, 0 untestable offline, 0 defect mutants. All 22 mutants that survived the selected existing tests were killed by the new tests.

## New tests

- `test_get_session_id_reuses_value`
- `test_current_session_id_selects_context`
- `test_json_serializes_dates_and_empty_values`
- `test_write_rejects_unknown_action`
- `test_write_records_payload_and_supplied_session`
- `test_log_change_returns_persisted_id`
- `test_log_event_maps_event_fields`
- `test_log_change_safe_returns_successful_id`
- `test_log_change_safe_returns_none_after_failure`
- `test_get_by_id_decodes_fields_and_missing_row`
- `test_get_earliest_date_includes_book_events_but_excludes_other_clients`
- `test_get_earliest_date_returns_none_for_empty_trail`
- `test_get_history_orders_ties_and_decodes_actor`
- `test_get_all_filters_inclusive_dates_and_pages`
- `test_filter_sql_searches_old_and_new_values`
- `test_get_filtered_counts_covers_actions_and_book_events`
- `test_get_entry_changes_matches_entry_and_lines_for_one_client`
- `test_get_entry_changes_does_not_match_partial_entry_id`
- `test_format_changes_reports_only_changed_values`
- `test_format_values_omits_internal_fields`

Every new test is associated with at least one recorded failing mutant. On the original module, 19 tests pass and the one known-defect test is an expected failure.

## Defects found

- `get_entry_changes(7, 4)` also returns a line whose JSON contains `"journal_entry_id": 40` because its SQL `LIKE` pattern matches the prefix. `test_get_entry_changes_does_not_match_partial_entry_id` records this as a strict expected failure. Production code was not changed.

## Verification limits

- `python3 -m pytest -q -m "not performance"` stopped during `tests/conftest.py` import with `ModuleNotFoundError: No module named 'platformdirs'`. No packages were installed.
- The before rate measures the six executable existing audit tests in the temporary harness. It is not a kill rate for the entire repository suite or every test in `tests/test_audit_log.py`.
