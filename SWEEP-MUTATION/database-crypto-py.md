# `database/crypto.py` mutation audit

The 17 one-change mutants cover all 16 functions. They include comparison and
Boolean flips, a negated condition, a numeric increment, a `None` return, a
removed statement, a `+` to `-` swap, and a dropped raise. Mutations were made
to temporary copies of the module, with a 12-second limit per check. The source
module was byte-identical before and after the run.

## Kill rates

| Check set | Killed | Rate |
| --- | ---: | ---: |
| Before: runnable assertions from existing encryption and rename tests | 4 / 17 | 23.5% |
| After: those assertions plus `test_crypto_mutation_guards.py` | 17 / 17 | 100% |

The existing pytest modules could not be collected in this environment:
`platformdirs` is missing, and `sqlcipher3` is unavailable. The **before** rate
therefore measures only existing assertions that could be run offline after
loading `crypto.py` directly: key determinism, distinction, length, the
compatibility digest, database state, and the plaintext backup path. It is not
a kill rate for the complete existing suite. The **after** rate uses those same
assertions plus the new isolated tests, run with `--noconftest` and a local fake
SQLCipher driver. It does not prove behavior against a real SQLCipher build.

| Mutant | Function | Change | Before | After | New test that kills it |
| --- | --- | --- | --- | --- | --- |
| M01 | `derive_key` | Increment KDF iterations | killed | killed | Already killed by compatibility digest |
| M02 | `key_pragma` | `or` to `and` in validation | survived | killed | `test_key_pragma_rejects_non_hex_and_wrong_length` |
| M03 | `key_pragma` | Drop invalid-key raise | survived | killed | `test_key_pragma_rejects_non_hex_and_wrong_length` |
| M04 | `_sql_str` | Remove quote doubling | survived | killed | `test_sql_str_doubles_quotes_in_an_invented_book_name` |
| M05 | `_has_sqlite_header` | `==` to `!=` | killed | killed | `test_has_sqlite_header_requires_all_sixteen_bytes` |
| M06 | `database_state` | `or` to `and` for absent file | killed | killed | `test_database_state_distinguishes_missing_empty_plain_and_encrypted` |
| M07 | `plaintext_backup_path` | `+` to `-` in suffix | killed | killed | `test_plaintext_backup_path_appends_suffix` |
| M08 | `is_plaintext_sqlite` | `and` to `or` for symlink check | survived | killed | `test_is_plaintext_sqlite_rejects_symlink` |
| M09 | `verify_passphrase` | Success return to `None` | survived | killed | `test_verify_passphrase_closes_connection_after_success_and_failure` |
| M10 | `_fsync_path` | Remove descriptor close | survived | killed | `test_fsync_path_closes_fd_when_sync_fails` |
| M11 | `_on_windows` | `==` to `!=` | survived | killed | `test_on_windows_uses_os_name` |
| M12 | `_replace_or_explain` | Remove replacement statement | survived | killed | `test_replace_or_explain_replaces_prepared_book` |
| M13 | `_data_version` | Read column 1 instead of 0 | survived | killed | `test_data_version_reads_first_column` |
| M14 | `rekey_file` | Negate integrity result check | survived | killed | `test_rekey_file_rejects_bad_integrity_and_preserves_source` |
| M15 | `key_fingerprint` | Increase marker length by one | survived | killed | `test_key_fingerprint_is_stable_and_key_specific` |
| M16 | `change_passphrase` | `!=` to `==` for concurrent write | survived | killed | `test_change_passphrase_rejects_changed_data_version` |
| M17 | `encrypt_plaintext_db` | `!=` to `==` for integrity result | survived | killed | `test_encrypt_plaintext_db_rejects_corrupt_export` |

Survivors left: **none**. No equivalent mutants, offline-untestable survivors, or
defect mutants remained among these 17. Defects found: **none**.

The new test file has 15 tests. Each passes on the original module and fails
on at least one listed mutant. M05, M06, and M07 were also killed by the
limited existing-assertion baseline. The throwaway runner was removed after
recording these results.
