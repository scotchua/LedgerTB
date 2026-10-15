# Mutation sweep: `models/payroll.py`

The sweep generated 31 single-change mutants across all eight methods in the
module. Each mutant was loaded from a modified in-memory copy in a fresh Python
process; the tracked source file was never rewritten. The before run used the
37 tests in `test_mcp_payroll.py`, `test_payroll_recording.py`, and
`test_payroll_discard.py`. The after run added the five tests in
`test_payroll_model_mutations.py`. Each run had a 20-second limit; the final
repeat of M29 used 45 seconds after two timeouts. `.env` loading was disabled
and no network or API calls were made.

| Measure | Before | After |
| --- | ---: | ---: |
| Killed / generated | 23 / 31 | 29 / 31 |
| Kill rate | 74.2% | 93.5% |
| Killed / non-equivalent | 23 / 29 | 29 / 29 |
| Non-equivalent kill rate | 79.3% | 100% |

`K` means a relevant test failed or errored; `S` means all relevant tests passed.
No mutant changed comments, logging, or docstrings. The module has no Python
`and`/`or` expression or numeric arithmetic expression, so the sweep also
exercised the corresponding SQL and query-building operations.

| ID | Method | Mutation | Before | After |
| --- | --- | --- | :---: | :---: |
| M01 | `Employee._from_row` | Drop parsed start date | K | K |
| M02 | `Employee._from_row` | Force status to active | S | K |
| M03 | `Employee.get_all` | Negate `active_only` | S | K |
| M04 | `Employee.get_all` | Return empty list | K | K |
| M05 | `Employee.save` | Invert blank-name guard | K | K |
| M06 | `Employee.save` | Invert missing-date guard | K | K |
| M07 | `Employee.save` | Invert allowed-status comparison | K | K |
| M08 | `Employee.save` | Invert department-presence comparison | K | K |
| M09 | `Employee.save` | Invert department lookup result | K | K |
| M10 | `Employee.save` | Swap insert/update branch | K | K |
| M11 | `Employee.save` | Invert missing-employee guard | K | K |
| M12 | `Employee.save` | Remove assignment of inserted ID | K | K |
| M13 | `Employee.save` | Remove commit | K | K |
| M14 | `Employee.save` | Remove explicit rollback | S | S |
| M15 | `Employee.save` | Return `None` | S | K |
| M16 | `Employee.save` | Drop blank-name raise | S | K |
| M17 | `Employee.deactivate` | Keep status active | S | K |
| M18 | `Employee.deactivate` | Remove save call | K | K |
| M19 | `PayRun._from_row` | Drop parsed pay date | K | K |
| M20 | `PayRun.get_by_id` | Negate row condition | K | K |
| M21 | `PayRun.get_by_id` | Return `None` | K | K |
| M22 | `PayRun.get_all` | Return empty list | K | K |
| M23 | `PayStub.get_all` | Zero gross pay | K | K |
| M24 | `PayStub.get_all` | Return empty deductions | K | K |
| M25 | `PayStub.get_all` | Zero net pay | K | K |
| M26 | `PayStub.get_all` | Return empty employer costs | K | K |
| M27 | `Employee.get_all` | Replace query `+` with `-` | K | K |
| M28 | `PayStub.get_all` | Add early empty-list return | K | K |
| M29 | `Employee.save` | Change SQL `SELECT 1` to `SELECT 2` | S | S |
| M30 | `Employee.save` | Change department SQL `AND` to `OR` | S | K |
| M31 | `Employee.get_all` | Change client SQL `=` to `!=` | K | K |

## New tests

| Test | Mutant killed |
| --- | --- |
| `test_employee_get_all_filters_active_status` | M03 |
| `test_employee_save_returns_persisted_id` | M15 |
| `test_employee_save_rejects_blank_name` | M16 |
| `test_employee_save_rejects_other_company_department` | M30 |
| `test_employee_deactivate_persists_terminated_status` | M02, M17 |

Each new test passes on the original module and fails on the mutant listed.

## Survivors left

- **M14 - equivalent:** the exception handler still closes the SQLite/SQLCipher
  connection; closing an uncommitted connection rolls back its transaction.
  The explicit rollback does not change persisted data in this path.
- **M29 - equivalent:** the department query checks only whether a row exists.
  `SELECT 1` and `SELECT 2` return the same row set, and the selected value is
  never read. The after run passed 42 tests on the 45-second retry.

## Defects found

None. No expected-failure test was needed.

The source SHA-256 before and after the sweep was
`ab60b61c52801bb60e99c7bb772c28cd3e27c5682a1fd1664302639a05b72b0d`.
The full non-performance suite passed: 1087 passed, 5 skipped, 3 deselected.
