# Mutation sweep: `services/document_import.py`

## Result

| Phase | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Existing offline checks | 17 | 44 | 38.6% |
| Existing plus new checks | 43 | 44 | 97.7% |

The one remaining mutant is equivalent for the tested behavior, so the final behavioral kill rate is 43/43 (100%). No defect was found in the original code.

## Method and scope

The throwaway runner applied one source-token edit at a time in memory and loaded the result as a separate module. It never wrote to `services/document_import.py`; its SHA-256 after the sweep was `1a7acb1385f5e420b3b889d1dd0502fdfae7edfe09cdd065071e300dce2215b4`. Each mutant ran in a separate process with an eight-second limit. The 44 edits cover all seven functions and include comparison flips, condition negations, `or`/`and` swaps, a `+`/`-` swap, one-step numeric boundary changes, return changes, statement removal, and a dropped exception raise. Comments, logging, and docstrings were excluded.

The available Python environment lacks `platformdirs` and `reportlab`. To run existing checks without changing production code or installing packages, the runner executed the three dependency-free parser and AI test functions from `tests/test_document_import.py` against each mutant. It could not execute that file's PDF tests or the full suite. All tests used local fakes; no API calls were made.

## Mutants

| Function | Killed by existing checks | Newly killed | Survivor |
| --- | --- | --- | --- |
| `_validate_document` | - | `validate_extension`, `validate_empty`, `validate_size`, `validate_pdf_magic`, `validate_png_magic`, `validate_jpeg_magic`, `validate_return` | - |
| `_vision_ocr` | - | `vision_decode`, `vision_drop_raise`, `vision_pixels`, `vision_render`, `vision_perform`, `vision_candidates`, `vision_rows`, `vision_return` | - |
| `extract_document` | - | `extract_branch`, `extract_image_blank`, `extract_page_limit`, `extract_native_threshold`, `extract_warning`, `extract_readable` | `extract_render_scale` (equivalent) |
| `_parse_date` | `date_separator` | `date_no_fallback` | - |
| `_parse_money` | `money_negative`, `money_sign` | - | - |
| `parse_statement_text` | `parser_strategy`, `parser_match`, `parser_drop_final_record`, `parser_continuation`, `parser_filter`, `parser_pick`, `parser_description`, `parser_return` | `parser_description_limit`, `parser_source_limit` | - |
| `parse_statement_with_ai` | `ai_key`, `ai_guidance`, `ai_tool_missing`, `ai_description`, `ai_empty`, `ai_return` | `ai_size`, `ai_skip_bad_row` | - |

`extract_render_scale` changes `estimated_pixels > MAX_IMAGE_PIXELS` to `>=`. At equality, the branch recomputes the same `2.2` scale from `sqrt(MAX_IMAGE_PIXELS / (width * height))`; it does not change the rendered page. There are no survivors classified as untestable offline or as a defect. **Defects found:** none.

## New tests

Each test passed against the original module and failed against at least the listed mutant in a per-test mutation matrix:

| Test | Example mutant killed |
| --- | --- |
| `test_validate_document_rejects_empty_and_wrong_image_signatures` | `validate_extension` |
| `test_validate_document_accepts_exact_size_limit_and_returns_extension` | `validate_size` |
| `test_vision_ocr_reports_decode_render_and_request_errors` | `vision_decode` |
| `test_vision_ocr_allows_exact_pixel_limit` | `vision_pixels` |
| `test_vision_ocr_groups_nearby_words_and_skips_empty_candidates` | `vision_rows` |
| `test_extract_document_rejects_blank_image_and_reads_valid_image` | `extract_image_blank` |
| `test_extract_document_accepts_exact_page_limit` | `extract_page_limit` |
| `test_extract_document_uses_native_text_at_exact_threshold` | `extract_native_threshold` |
| `test_extract_document_warns_for_empty_ocr_page` | `extract_warning` |
| `test_parse_date_returns_none_for_invalid_value` | `date_no_fallback` |
| `test_parse_statement_text_preserves_source_limit` | `parser_source_limit` |
| `test_parse_statement_text_limits_description` | `parser_description_limit` |
| `test_parse_statement_with_ai_accepts_exact_text_limit` | `ai_size` |
| `test_parse_statement_with_ai_skips_invalid_rows` | `ai_skip_bad_row` |

Verification: `python3 -m pytest -q --noconftest tests/test_document_import_mutations.py` passed (14 tests). `python3 -m pytest -q -m 'not performance'` stopped during collection with `ModuleNotFoundError: platformdirs`; the requested `python` executable is absent in this environment. Full-suite status remains unverified.
