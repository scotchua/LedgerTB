# Mutation test report: `utils/book_lock.py`

## Method and results

The throwaway AST runner generated 61 one-change mutants across all 18 functions. It changed code only in memory, skipped docstrings, and ran each mutant in a fresh subprocess with a 12-second time box. No production file was written. It copied the five existing lease tests from `tests/test_books.py` into a temporary test module, preserving their test bodies and replacing only their unused `settings` fixture and global lease cleanup fixture. This was necessary because normal collection of `tests/conftest.py` fails before any test runs: the available Python lacks `platformdirs`. The tests and runner made no network calls.

| Suite | Killed | Survived | Timed out | Kill rate |
| --- | ---: | ---: | ---: | ---: |
| Existing lease tests | 45 | 15 | 1 | 45/61 (73.8%) |
| Existing lease tests plus new tests | 61 | 0 | 0 | 61/61 (100%) |

The existing-test run initially reported M007 killed, but an isolated rerun passed; it is conservatively counted as a survivor. M021 timed out in the combined run both before and after. Its new focused test fails directly on M021 in 0.02 seconds, so the after count records it as killed by that test. M007 also fails its focused new test after the truncation assertion was added.

## Mutants generated

| ID | Function:line | Change | Before | After |
| --- | --- | --- | --- | --- |
| M000 | `lock_path:30` | swap + and - (Sub) | killed | killed |
| M001 | `_now:34` | replace return value (None) | killed | killed |
| M002 | `_me:39` | replace return value (None) | killed | killed |
| M003 | `_me:40` | swap and/or (And) | killed | killed |
| M004 | `read_lock:52` | replace return value (None) | killed | killed |
| M005 | `read_lock:54` | replace return value (empty) | survived | killed |
| M006 | `_write_handle:59` | increase numeric constant by one | killed | killed |
| M007 | `_write_handle:60` | increase numeric constant by one | survived | killed |
| M008 | `_write_handle:58` | swap + and - (Sub) | killed | killed |
| M009 | `_write_handle:62` | remove statement | survived | killed |
| M010 | `_remember:69` | negate condition | killed | killed |
| M011 | `_remember:71` | remove statement | killed | killed |
| M012 | `_remember:72` | remove statement | killed | killed |
| M013 | `_forget:79` | negate condition | killed | killed |
| M014 | `_forget:80` | remove statement | survived | killed |
| M015 | `_forget:82` | negate condition | survived | killed |
| M016 | `_reset:91` | remove statement | survived | killed |
| M017 | `_owned_token:98` | replace return value (None) | killed | killed |
| M018 | `_owned_token:98` | negate condition | killed | killed |
| M019 | `held_books:104` | replace return value (None) | killed | killed |
| M020 | `held_books:104` | replace return value (empty) | survived | killed |
| M021 | `_heartbeat:115` | negate condition | timeout | killed |
| M022 | `_heartbeat:117` | remove statement | killed | killed |
| M023 | `_start_heartbeat:126` | negate condition | killed | killed |
| M024 | `_start_heartbeat:129` | remove statement | survived | killed |
| M025 | `_start_heartbeat:130` | remove statement | killed | killed |
| M026 | `is_stale:140` | negate condition | killed | killed |
| M027 | `is_stale:144` | negate condition | survived | killed |
| M028 | `is_stale:146` | flip comparison (GtE) | survived | killed |
| M029 | `is_stale:146` | swap + and - (Add) | killed | killed |
| M030 | `is_stale:146` | swap and/or (And) | killed | killed |
| M031 | `is_stale:148` | replace return value (False) | survived | killed |
| M032 | `acquire:156` | negate condition | killed | killed |
| M033 | `acquire:156` | swap and/or (Or) | killed | killed |
| M034 | `acquire:156` | flip comparison (NotEq) | killed | killed |
| M035 | `acquire:157` | replace return value (None) | killed | killed |
| M036 | `acquire:164` | replace return value (None) | killed | killed |
| M037 | `acquire:170` | drop exception raise | survived | killed |
| M038 | `acquire:172` | replace return value (None) | killed | killed |
| M039 | `takeover:179` | negate condition | killed | killed |
| M040 | `takeover:182` | remove statement | killed | killed |
| M041 | `takeover:183` | negate condition | killed | killed |
| M042 | `takeover:185` | flip comparison (Eq) | killed | killed |
| M043 | `takeover:185` | swap and/or (And) | survived | killed |
| M044 | `takeover:191` | replace return value (None) | killed | killed |
| M045 | `verify_and_refresh:198` | negate condition | killed | killed |
| M046 | `verify_and_refresh:201` | negate condition | killed | killed |
| M047 | `verify_and_refresh:201` | swap and/or (And) | killed | killed |
| M048 | `verify_and_refresh:201` | flip comparison (Eq) | killed | killed |
| M049 | `verify_and_refresh:203` | drop exception raise | killed | killed |
| M050 | `verify_and_refresh:205` | increase numeric constant by one | killed | killed |
| M051 | `verify_and_refresh:206` | replace return value (None) | survived | killed |
| M052 | `release:216` | negate condition | killed | killed |
| M053 | `release:216` | swap and/or (Or) | killed | killed |
| M054 | `release:216` | flip comparison (NotEq) | killed | killed |
| M055 | `release:217` | remove statement | survived | killed |
| M056 | `describe:224` | negate condition | killed | killed |
| M057 | `describe:227` | remove statement | killed | killed |
| M058 | `describe:228` | remove statement | killed | killed |
| M059 | `describe:234` | swap + and - (Sub) | killed | killed |
| M060 | `describe:235` | negate condition | killed | killed |

## New tests and previously surviving behavior

| New test in `tests/test_book_lock_mutations.py` | Mutants caught |
| --- | --- |
| `test_read_lock_returns_none_for_unreadable_sidecar` | M005 |
| `test_write_handle_flushes_sidecar` | M007, M009 |
| `test_forget_stops_heartbeat_and_closes_handle` | M014, M015 |
| `test_reset_forgets_all_held_books` | M016 |
| `test_held_books_lists_its_book` | M020 |
| `test_heartbeat_refreshes_until_stopped` | M021 |
| `test_start_heartbeat_tracks_its_stop_event` | M024 |
| `test_is_stale_handles_naive_fresh_and_invalid_timestamps` | M027, M028, M031 |
| `test_acquire_propagates_write_failure_and_removes_sidecar` | M037 |
| `test_takeover_refuses_when_observed_holder_disappears` | M043 |
| `test_verify_and_refresh_reports_current_ownership` | M051 |
| `test_release_removes_its_sidecar` | M055 |

Each of the 12 new tests passed on the original module and failed on at least one listed mutant. Every previously surviving mutant and the timed-out mutant also failed its focused new test.

## Survivors left

None. Equivalent: none. Untestable offline: none. Defects found: none.

## Verification limits

`python3 -m pytest -q --noconftest tests/test_book_lock_mutations.py`: 12 passed. The copied existing lease tests: 5 passed. `python3 -m pytest -q -m "not performance"` could not collect tests because `platformdirs` is not installed. The requested `python` command is unavailable in this environment, so `python3` was used. `git diff --exit-code -- utils/book_lock.py` succeeded; no production file was changed.
