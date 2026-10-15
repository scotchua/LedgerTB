# Mutation results: `models/receivables.py`

The source was read in full. The existing receivables coverage is indirect, mainly
`tests/test_ar_ap.py` through `services/ar_ap.py`; there were no direct model tests.
The throwaway runner and final statement-removal check made 14 single changes
to temporary copies of the source, one at a time, with a 15-second limit per
pytest run. The source file was never edited;
its SHA-256 before and after was
`624d5094e95deb134a86b1dd72bb90688d362828add0d92795a4391c33bd068c`.
The selected sites cover every explicit function and each dataclass. This module
has no comparison, Boolean condition, or exception raise to mutate. Comment,
logging, and docstring text was excluded.

## Kill rates

| Test set | Killed | Rate | Interpretation |
| --- | ---: | ---: | --- |
| Existing `tests/test_ar_ap.py` | 0/14 observed | 0% observed | **Unscorable:** all 14 attempts stopped during collection, before any test ran, because `platformdirs` is missing. This is not an estimate of the suite's true kill rate. |
| New `tests/test_receivables_model.py` | 14/14 | 100% | Every mutant produced at least one test failure; the unmutated file passed all nine tests. |

## Mutants

| ID | Single change | Killed by new test |
| --- | --- | --- |
| M01 | `Customer.client_id`: default 0 → 1 | `test_customer_defaults` |
| M02 | `InvoiceLine.quantity`: default 1 → 2 | `test_invoice_line_amount_cents` |
| M03 | `InvoiceLine.amount_cents`: return `None` | `test_invoice_line_amount_cents` |
| M04 | `Invoice.tax_amount_cents`: default 0 → 1 | `test_invoice_defaults` |
| M05 | `Invoice.subtotal_cents`: return `None` | `test_invoice_subtotal_cents` |
| M06 | `Invoice.total_cents`: return `None` | `test_invoice_total_cents` |
| M07 | `Invoice.total_cents`: `+` → `-` | `test_invoice_total_cents` |
| M08 | `CreditMemoLine.quantity`: default 1 → 2 | `test_credit_memo_line_amount_cents` |
| M09 | `CreditMemoLine.amount_cents`: return `None` | `test_credit_memo_line_amount_cents` |
| M10 | `CreditMemo.tax_amount_cents`: default 0 → 1 | `test_credit_memo_defaults` |
| M11 | `CreditMemo.subtotal_cents`: return `None` | `test_credit_memo_subtotal_cents` |
| M12 | `CreditMemo.total_cents`: return `None` | `test_credit_memo_total_cents` |
| M13 | `CreditMemo.total_cents`: `+` → `-` | `test_credit_memo_total_cents` |
| M14 | `InvoiceLine.amount_cents`: remove its return statement | `test_invoice_line_amount_cents` |

The new tests are grouped by model property and defaults. Each of the nine
tests above fails on at least one listed mutant. All 14 mutants survived the
existing-test attempts for the **untestable offline** reason above; none survived
the new tests. Equivalent mutants: none. Defects found: none.

## Verification

- `python3 -m pytest -q --noconftest tests/test_receivables_model.py`:
  9 passed on the original source.
- `python3 -m pytest -q -m "not performance"`: stopped while loading
  `tests/conftest.py` because `platformdirs` is not installed. No packages were
  installed and no network calls were made.
