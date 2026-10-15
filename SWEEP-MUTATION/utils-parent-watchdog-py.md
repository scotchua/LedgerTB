# Mutation sweep: `utils/parent_watchdog.py`

The original module was read in full and left byte-identical (SHA-256 `c4a07ba944ca0153ae8b0647e4fd8af26dac12efd5ff1a342e683a837a44ec61`). Each mutant was written into a temporary shadow `utils` package; the worktree module was never edited. Each pytest run had a 12-second timeout, and its process group was cleaned up afterward.

## Results

| Stage | Killed | Mutants scored | Kill rate |
| --- | ---: | ---: | ---: |
| Existing watchdog tests | 19 | 48 | 39.6% |
| Existing and new watchdog tests | 48 | 48 | 100.0% |

The runner generated 49 trial mutants. One trial removing `logging.shutdown()` was excluded as a logging call, leaving 48 scored mutants. The scored sweep covered `_parent_is_alive`, `_watch_parent`, and `start_parent_watchdog`. It changed comparisons, Boolean conditions, return values, numeric constants, and individual executable statements. The module has no `+` or `-` binary expression or explicit `raise` statement to mutate. Comments, logging calls, and docstrings were excluded from the scored set.

| Function | Mutant | Before | After |
| --- | --- | --- | --- |
| `_parent_is_alive` | `ppid-equal` | killed | killed |
| `_parent_is_alive` | `ppid-less` | survived | killed |
| `_parent_is_alive` | `ppid-greater` | survived | killed |
| `_parent_is_alive` | `ppid-return-true` | killed | killed |
| `_parent_is_alive` | `ppid-return-none` | survived | killed |
| `_parent_is_alive` | `ppid-drop-return` | survived | killed |
| `_parent_is_alive` | `kill-signal-plus-one` | survived | killed |
| `_parent_is_alive` | `kill-signal-minus-one` | killed | killed |
| `_parent_is_alive` | `drop-kill` | survived | killed |
| `_parent_is_alive` | `missing-return-true` | survived | killed |
| `_parent_is_alive` | `missing-return-none` | survived | killed |
| `_parent_is_alive` | `missing-drop-return` | survived | killed |
| `_parent_is_alive` | `denied-return-false` | survived | killed |
| `_parent_is_alive` | `denied-raise` | survived | killed |
| `_parent_is_alive` | `alive-return-false` | killed | killed |
| `_parent_is_alive` | `alive-return-none` | killed | killed |
| `_watch_parent` | `negate-loop` | killed | killed |
| `_watch_parent` | `drop-loop` | killed | killed |
| `_watch_parent` | `wait-plus-one` | survived | killed |
| `_watch_parent` | `wait-minus-one` | survived | killed |
| `_watch_parent` | `drop-wait` | killed | killed |
| `_watch_parent` | `drop-held-books` | killed | killed |
| `_watch_parent` | `drop-release` | killed | killed |
| `_watch_parent` | `drop-stdout-flush` | survived | killed |
| `_watch_parent` | `drop-stderr-flush` | survived | killed |
| `_watch_parent` | `exit-plus-one` | survived | killed |
| `_watch_parent` | `exit-minus-one` | survived | killed |
| `_watch_parent` | `drop-exit` | killed | killed |
| `start_parent_watchdog` | `guard-and` | killed | killed |
| `start_parent_watchdog` | `guard-negate-value` | killed | killed |
| `start_parent_watchdog` | `guard-negate-started` | killed | killed |
| `start_parent_watchdog` | `guard-return-true` | killed | killed |
| `start_parent_watchdog` | `guard-return-none` | killed | killed |
| `start_parent_watchdog` | `invalid-return-true` | survived | killed |
| `start_parent_watchdog` | `invalid-drop-return` | survived | killed |
| `start_parent_watchdog` | `positive-less` | survived | killed |
| `start_parent_watchdog` | `positive-greater-equal` | killed | killed |
| `start_parent_watchdog` | `positive-equal` | survived | killed |
| `start_parent_watchdog` | `positive-not-equal` | killed | killed |
| `start_parent_watchdog` | `positive-threshold-plus-one` | survived | killed |
| `start_parent_watchdog` | `positive-threshold-minus-one` | survived | killed |
| `start_parent_watchdog` | `positive-return-true` | survived | killed |
| `start_parent_watchdog` | `started-false` | survived | killed |
| `start_parent_watchdog` | `drop-started` | survived | killed |
| `start_parent_watchdog` | `daemon-false` | survived | killed |
| `start_parent_watchdog` | `drop-thread-start` | killed | killed |
| `start_parent_watchdog` | `success-return-false` | survived | killed |
| `start_parent_watchdog` | `success-return-none` | survived | killed |

## New tests

| Test | Example mutant it kills |
| --- | --- |
| `test_parent_is_alive_rejects_a_different_parent` | `ppid-less` |
| `test_parent_is_alive_checks_process_with_signal_zero` | `kill-signal-plus-one` |
| `test_parent_is_alive_handles_process_probe_errors` | `missing-return-true` |
| `test_watch_parent_waits_then_releases_books_and_exits` | `wait-plus-one` |
| `test_start_parent_watchdog_rejects_invalid_parent_ids` | `positive-less` |
| `test_start_parent_watchdog_starts_one_daemon_thread` | `started-false` |

Each new test passed against the original and failed when run alone against its listed mutant. Parameterized cases cover parent IDs on both sides of the expected PID, both process-probe errors, and malformed, zero, and negative startup PIDs.

## Survivors left

None. Equivalent: none; untestable offline: none; defect: none.

## Defects found

None.

## Verification

- `python3 -m pytest --noconftest -q tests/test_parent_watchdog.py -m "not performance"`: 12 passed.
- `python3 -m pytest -q -m "not performance"`: test setup stopped because the installed environment lacks `platformdirs` (`tests/conftest.py` imports `config.py`, which imports it). The requested `python -m pytest` command is also unavailable because `python` is not on PATH. No packages were installed.
