# Mutation probe: `models/payables.py`

## Scope and method

Read the full model and the payable paths in `tests/test_ar_ap.py` and `services/ar_ap.py`. The source has no comparisons, Boolean conditions, raises, logging, or docstrings to mutate. Selected one change at a time in dataclass defaults and the three computed properties. Each mutant was loaded from a temporary file; the production module was never written. Each subprocess had a 10-second limit. All 39 mutants were within the 150-mutant cap and covered `Vendor`, `BillLine`, and `Bill`.

The baseline attempt ran `tests/test_ar_ap.py` against every mutant with a temporary import plugin. All 39 runs failed during `tests/conftest.py` collection because `platformdirs` is not installed. They are **untestable offline**, not surviving assertions. The original file SHA-256 before and after the probe was `f467d43d6ae3868bdbf715093ecb5fa8a1d13d7f32817213237d48cbdb3fdaef`.

## Kill rates

| Test set | Killed | Assessed | Rate |
| --- | ---: | ---: | ---: |
| Existing payable tests, before | 0 | 0 | N/A: 39 collection errors |
| New isolated model tests, after | 37 | 39 | 94.9% |
| New tests, behavior-changing mutants only | 37 | 37 | 100% |

The before rate cannot be measured here. Treating collection errors as survived mutants would falsely imply the existing assertions ran. The after rate includes two equivalent mutants in its denominator.

## Mutants generated

Every before result below is `collection error (platformdirs)`. `Killed` means at least one new test failed on the mutant and the original passed.

| ID | Class | One source change | After |
| --- | --- | --- | --- |
| V01 | Vendor | `id: Optional[int] = None -> id: Optional[int] = 0` | killed |
| V02 | Vendor | `client_id: int = 0 -> client_id: int = 1` | killed |
| V03 | Vendor | `name: str = "" -> name: str = None` | killed |
| V04 | Vendor | `normalized_name: str = "" -> normalized_name: str = None` | killed |
| V05 | Vendor | `email: Optional[str] = None -> email: Optional[str] = ""` | killed |
| V06 | Vendor | `created_at: Optional[str] = None -> created_at: Optional[str] = ""` | killed |
| L01 | BillLine | `id: Optional[int] = None -> id: Optional[int] = 0` | killed |
| L02 | BillLine | `bill_id: Optional[int] = None -> bill_id: Optional[int] = 0` | killed |
| L03 | BillLine | `description: str = "" -> description: str = None` | killed |
| L04 | BillLine | `quantity: int = 1 -> quantity: int = 2` | killed |
| L05 | BillLine | `unit_price_cents: int = 0 -> unit_price_cents: int = 1` | killed |
| L06 | BillLine | `expense_account_id: int = 0 -> expense_account_id: int = 1` | killed |
| L07 | BillLine | `return self.quantity * self.unit_price_cents -> return self.quantity + self.unit_price_cents` | killed |
| L08 | BillLine | `return self.quantity * self.unit_price_cents -> return self.unit_price_cents` | killed |
| L09 | BillLine | `return self.quantity * self.unit_price_cents -> return None` | killed |
| L10 | BillLine | `return self.quantity * self.unit_price_cents -> return False` | killed |
| L11 | BillLine | `return self.quantity * self.unit_price_cents -> return self.quantity * (self.unit_price_cents + 1)` | killed |
| B01 | Bill | `id: Optional[int] = None -> id: Optional[int] = 0` | killed |
| B02 | Bill | `client_id: int = 0 -> client_id: int = 1` | killed |
| B03 | Bill | `vendor_id: int = 0 -> vendor_id: int = 1` | killed |
| B04 | Bill | `bill_date: Optional[date] = None -> bill_date: Optional[date] = date(2026, 1, 1)` | killed |
| B05 | Bill | `due_date: Optional[date] = None -> due_date: Optional[date] = date(2026, 1, 1)` | killed |
| B06 | Bill | `status: str = "draft" -> status: str = "posted"` | killed |
| B07 | Bill | `journal_entry_id: Optional[int] = None -> journal_entry_id: Optional[int] = 0` | killed |
| B08 | Bill | `voided_journal_entry_id: Optional[int] = None -> voided_journal_entry_id: Optional[int] = 0` | killed |
| B09 | Bill | `control_account_id: Optional[int] = None -> control_account_id: Optional[int] = 0` | killed |
| B10 | Bill | `tax_rate: Optional[str] = None -> tax_rate: Optional[str] = "0"` | killed |
| B11 | Bill | `tax_amount_cents: int = 0 -> tax_amount_cents: int = 1` | killed |
| B12 | Bill | `tax_account_id: Optional[int] = None -> tax_account_id: Optional[int] = 0` | killed |
| B13 | Bill | `lines: List[BillLine] = field(default_factory=list) -> lines: List[BillLine] = field(default_factory=dict)` | killed |
| B14 | Bill | `return sum(line.amount_cents for line in self.lines) -> return 0` | killed |
| B15 | Bill | `return sum(line.amount_cents for line in self.lines) -> return None` | killed |
| B16 | Bill | `return sum(line.amount_cents for line in self.lines) -> return sum(line.unit_price_cents for line in self.lines)` | killed |
| B17 | Bill | `return sum(line.amount_cents for line in self.lines) -> return sum((line.amount_cents for line in self.lines), 0)` | equivalent survivor |
| B18 | Bill | `return self.subtotal_cents + self.tax_amount_cents -> return self.subtotal_cents - self.tax_amount_cents` | killed |
| B19 | Bill | `return self.subtotal_cents + self.tax_amount_cents -> return self.tax_amount_cents` | killed |
| B20 | Bill | `return self.subtotal_cents + self.tax_amount_cents -> return None` | killed |
| B21 | Bill | `return self.subtotal_cents + self.tax_amount_cents -> return self.tax_amount_cents + self.subtotal_cents` | equivalent survivor |
| B22 | Bill | `lines: List[BillLine] = field(default_factory=list) -> lines: List[BillLine] = field(default_factory=lambda: globals().setdefault('_shared_bill_lines', []))` | killed |

## Surviving mutants

- `B17`: `sum(generator, 0)` is identical to `sum(generator)` for every input; the default start value is already zero.
- `B21`: reordering the two integer operands of addition does not change the payable total.

No behavior-changing mutant survived the new tests. No defect in the original code was found.

## New tests

### Vendor

- `test_vendor_defaults` - fails on `V01`, `V02`, `V03`, `V04`, `V05`, `V06`; passes on the original.

### BillLine

- `test_bill_line_defaults` - fails on `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L09`, `L11`; passes on the original.
- `test_bill_line_amount_uses_quantity_and_unit_price` - fails on `L07`, `L08`, `L09`, `L10`, `L11`; passes on the original.

### Bill

- `test_bill_defaults` - fails on `B01`, `B02`, `B03`, `B04`, `B05`, `B06`, `B07`, `B08`, `B09`, `B10`, `B11`, `B12`, `B13`, `B15`, `B20`; passes on the original.
- `test_bill_lines_are_independent` - fails on `L07`, `L08`, `L09`, `L10`, `L11`, `B13`, `B14`, `B15`, `B16`, `B22`; passes on the original.
- `test_bill_subtotal_sums_each_extended_line` - fails on `L07`, `L08`, `L09`, `L10`, `L11`, `B14`, `B15`, `B16`; passes on the original.
- `test_bill_total_adds_tax_once` - fails on `L07`, `L08`, `L09`, `L10`, `L11`, `B14`, `B15`, `B16`, `B18`, `B19`, `B20`; passes on the original.

## Verification and limits

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q --noconftest -p no:cacheprovider tests/test_payables_model.py`: 7 passed.
- `python3 -m pytest -q -m "not performance"`: stopped in collection with `ModuleNotFoundError: No module named 'platformdirs'`. The requested `python` command is unavailable in this environment, so `python3` was used.
- The existing integration tests and full suite require installed runtime dependencies. No packages were installed, no network was used, and no production file was changed.
