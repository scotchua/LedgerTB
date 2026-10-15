# Mutation results: `utils/folder_picker.py`

## Method

- Read the complete module and `tests/test_folder_picker.py`; the relevant existing cases were the five tests in that file. `tests/test_data_safety_page.py` also stubs `choose_folder`, so it does not exercise the implementation.
- Generated one AST mutation per run, capped at 150. The 46 generated mutants cover both functions. The runner loaded each changed copy from a temporary directory in a separate Python process; it never wrote the production module. Each run was limited to eight seconds. Comments, docstrings, logging, and embedded AppleScript/PowerShell strings were not mutated. There are no Python `+` or `-` expressions in this module to swap.
- The original module was byte-identical before and after both sweeps. Its SHA-256 is `66c1fd2fa709f47798fe967682de7e59d666fae485ea6cd6b99f65be0b7349e1`; `git diff -- utils/folder_picker.py` is empty.
- Before: `python3 -m pytest -q --noconftest tests/test_folder_picker.py` (five existing tests). After: the same command (five existing plus ten new parameter cases).

## Kill rates

| Sweep | Generated | Killed | Survived | Kill rate |
| --- | ---: | ---: | ---: | ---: |
| Before | 46 | 31 | 15 | 67.4% |
| After | 46 | 46 | 0 | 100.0% |

## Mutants

| ID | Function:line | Change | Before | After |
| --- | --- | --- | --- | --- |
| M001 | `_starting_folder:17` | remove statement | killed | killed |
| M002 | `_starting_folder:18` | negate condition | killed | killed |
| M003 | `_starting_folder:20` | return None | killed | killed |
| M004 | `_starting_folder:20` | return '' | killed | killed |
| M005 | `_starting_folder:20` | return False | killed | killed |
| M006 | `choose_folder:25` | remove statement | killed | killed |
| M007 | `choose_folder:27` | negate condition | killed | killed |
| M008 | `choose_folder:93` | remove statement | killed | killed |
| M009 | `choose_folder:94` | return None | killed | killed |
| M010 | `choose_folder:94` | return '' | killed | killed |
| M011 | `choose_folder:94` | return False | killed | killed |
| M012 | `_starting_folder:19` | remove statement | killed | killed |
| M013 | `choose_folder:27` | comparison | killed | killed |
| M014 | `choose_folder:28` | remove statement | killed | killed |
| M015 | `choose_folder:35` | remove statement | killed | killed |
| M016 | `choose_folder:40` | negate condition | killed | killed |
| M017 | `choose_folder:45` | negate condition | killed | killed |
| M018 | `choose_folder:94` | negate condition | killed | killed |
| M019 | `_starting_folder:19` | negate condition | killed | killed |
| M020 | `choose_folder:41` | negate condition | killed | killed |
| M021 | `choose_folder:43` | drop raise | survived | killed |
| M022 | `choose_folder:45` | comparison | killed | killed |
| M023 | `choose_folder:46` | remove statement | killed | killed |
| M024 | `choose_folder:58` | remove statement | killed | killed |
| M025 | `choose_folder:59` | remove statement | killed | killed |
| M026 | `choose_folder:66` | negate condition | killed | killed |
| M027 | `choose_folder:72` | remove statement | killed | killed |
| M028 | `choose_folder:73` | negate condition | killed | killed |
| M029 | `choose_folder:77` | remove statement | survived | killed |
| M030 | `choose_folder:88` | negate condition | survived | killed |
| M031 | `choose_folder:90` | negate condition | survived | killed |
| M032 | `choose_folder:41` | boolean swap | survived | killed |
| M033 | `choose_folder:42` | return '' | killed | killed |
| M034 | `choose_folder:42` | return False | killed | killed |
| M035 | `choose_folder:67` | drop raise | survived | killed |
| M036 | `choose_folder:74` | drop raise | killed | killed |
| M037 | `choose_folder:88` | comparison | survived | killed |
| M038 | `choose_folder:89` | return '' | survived | killed |
| M039 | `choose_folder:89` | return False | survived | killed |
| M040 | `choose_folder:91` | drop raise | survived | killed |
| M041 | `_starting_folder:17` | boolean swap | killed | killed |
| M042 | `choose_folder:43` | boolean swap | survived | killed |
| M043 | `choose_folder:88` | numeric +1 | survived | killed |
| M044 | `choose_folder:68` | boolean swap | survived | killed |
| M045 | `choose_folder:91` | boolean swap | survived | killed |
| M046 | `choose_folder:64` | numeric +1 | survived | killed |

## New tests

Each case below passed on the original and failed when run alone against the listed mutant. The full folder picker file passed: 15 tests.

| Test case in `tests/test_folder_picker.py` | Mutant killed alone |
| --- | --- |
| `test_macos_folder_picker_treats_cancel_code_as_no_change` | M032 |
| `test_macos_folder_picker_reports_failure[Finder denied access-Finder denied access]` | M021 |
| `test_macos_folder_picker_reports_failure[-Finder could not choose a folder.]` | M042 |
| `test_windows_folder_picker_reports_failure[PowerShell denied access-PowerShell denied access]` | M035 |
| `test_windows_folder_picker_reports_failure[-Windows could not choose a folder.]` | M044 |
| `test_windows_folder_picker_uses_zero_when_creation_flag_is_missing` | M046 |
| `test_linux_folder_picker_returns_zenity_selection` | M029 |
| `test_linux_folder_picker_treats_cancel_as_no_change` | M038 |
| `test_linux_folder_picker_reports_failure[Zenity denied access-Zenity denied access]` | M040 |
| `test_linux_folder_picker_reports_failure[-Could not choose a folder.]` | M045 |

## Survivors left

None. There are no equivalent, offline-untestable, or defect mutants left.

## Defects found

None.

## Verification limits

- `python3 -m pytest -q --noconftest tests/test_folder_picker.py`: 15 passed.
- The requested full-suite run, `python3 -m pytest -q -m "not performance"`, could not collect tests because the available interpreter lacks `platformdirs` (`config.py` import via shared `tests/conftest.py`). The `python` executable is also unavailable; no packages were installed.
