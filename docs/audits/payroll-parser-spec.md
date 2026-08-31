# Payroll provider parser contract

This document specifies the contract for importing Gusto Payroll Journal and
QuickBooks Online Payroll Summary exports into `payroll_import_batches` and
`payroll_import_rows`. It is an expectation, not evidence that any listed
provider spelling occurs in a real export. No real exports or network sources
were available when it was written.

## Common contract

The parser accepts one complete file and returns either a refusal or a batch
object containing `provider`, `source_report`, and ordered `rows`. A staged row
has exactly these keys:

```text
employee_name_raw, department_raw, pay_period_start, pay_period_end, pay_date,
gross_pay_cents, deductions, employer_costs, net_pay_cents, raw_row, status
```

Dates are ISO `YYYY-MM-DD` strings. SQL-null values are represented by Python
`None`. `status` is always `pending`; matching IDs are omitted because matching
occurs after parsing. `raw_row` is a compact JSON object containing only
recognized, non-PII canonical input fields, with keys sorted lexicographically.

`deductions` and `employer_costs` use canonical JSON text: a JSON array of
objects with exactly `amount_cents` (integer) and `label` (string), object keys
in that order, items ordered by normalized source-column order, UTF-8 characters
unescaped, and no insignificant whitespace. Empty-but-present categories are
`[]`; an absent optional category is SQL NULL (`None`). Examples are
`[{\"amount_cents\":1234,\"label\":\"Benefits\"}]` and `[]`.

Header matching first removes one U+FEFF only at the start of the first header,
then removes leading and trailing Unicode whitespace and collapses every
internal run of Unicode whitespace to one ASCII space. Matching is
case-insensitive by Unicode `casefold()`. No Unicode normalization and no
punctuation insertion, deletion, or substitution occurs. Each resulting token
must equal exactly one alias below. Headers not in an alias table are unknown.

Files must be UTF-8 (a leading UTF-8 BOM is allowed), comma-delimited RFC 4180
CSV. CRLF and LF records are accepted. Quoting follows RFC 4180, including
escaped quotes and commas inside quoted fields. Blank physical records at the
end are ignored; a blank record between data records is refused. Invalid UTF-8,
NUL bytes, malformed quoting, or a different delimiter is refused.

Money permits an optional `$`, comma thousands separators, parentheses for a
negative value, or a trailing minus. Currency symbols other than `$` are
refused. Commas must form groups of three after a leading group of one to three
digits. Parentheses and trailing minus may not be combined. After decorations,
the value must be decimal digits with at most one decimal point. More than two
fractional digits are rounded to cents using decimal round-half-even. Thus
`1.005` is 100 cents and `1.015` is 102 cents. Blank means NULL; `0`, `0.00`,
and `$0.00` mean integer zero and remain distinguishable from blank.

Dates accept only the unambiguous formats listed for a provider. A slash date
whose first and second components are both at most 12 is ambiguous and refuses
the whole file, including `03/04/2026`. Start and end are independent full dates,
so a cross-month or cross-year period is represented directly, for example
`2026-12-20` through `2027-01-02`. End before start, or pay date before period
end, is refused.

## Gusto Payroll Journal

No exact spelling below is CONFIRMED because no checkable Gusto export or
provider documentation was supplied. LIKELY rows follow strong payroll-report
conventions; GUESS rows are explicit placeholders.

| Canonical field | Accepted header spelling | Confidence |
| --- | --- | --- |
| employee_name | Employee | LIKELY |
| employee_name | Employee Name | GUESS |
| department | Department | LIKELY |
| pay_period_start | Pay Period Start | GUESS |
| pay_period_end | Pay Period End | GUESS |
| pay_date | Check Date | GUESS |
| pay_date | Pay Date | LIKELY |
| gross_pay | Gross Pay | LIKELY |
| deduction_benefits | Benefits | GUESS |
| deduction_employee_taxes | Employee Taxes | GUESS |
| employer_cost_employer_taxes | Employer Taxes | LIKELY |
| employer_cost_contributions | Employer Contributions | GUESS |
| net_pay | Net Pay | LIKELY |
| row_type | Row Type | GUESS |

Required fields are `employee_name`, `pay_period_start`, `pay_period_end`,
`pay_date`, `gross_pay`, and `net_pay`. `department`, every deduction and
employer-cost category, and `row_type` are optional. A missing `department`
yields NULL. If all deduction headers are absent, `deductions` is NULL; if one
or more are present, it is a JSON array containing nonblank values (including
zero) and is `[]` when every present value is blank. Employer costs follow the
same rule. A missing `row_type` invokes the structural labels below.

Accepted dates are `YYYY-MM-DD`, `MM/DD/YYYY` only when unambiguous because the
day is greater than 12, and `Mon D, YYYY` using the case-insensitive English
abbreviations Jan through Dec.

If `row_type` exists, normalized values `employee`, `department total`, and
`grand total` identify the structure. Without it, a nonblank employee name is
an employee row; an empty employee with a nonblank department and amounts is a
department total; employee value `Total` with amounts is the grand total.
Only employee rows are staged. Exactly one grand total is required. Department
totals, if present, are validation-only and must equal their employee rows.

PII columns expected and always dropped before `raw_row` construction are:
`SSN`, `Social Security Number`, `Home Address`, `Address`, `Address 2`, `City`,
`State`, `ZIP`, `Date of Birth`, `DOB`, `Bank Account`, `Bank Account Number`,
`Routing Number`, `Account Type`, `Filing Status`, `Federal Withholding`,
`State Withholding`, and `Local Withholding`. Employee name alone is retained.

## QuickBooks Online Payroll Summary

No exact spelling below is CONFIRMED because no checkable QuickBooks export or
provider documentation was supplied. LIKELY rows follow strong payroll-report
conventions; GUESS rows are explicit placeholders.

| Canonical field | Accepted header spelling | Confidence |
| --- | --- | --- |
| employee_name | Employee | LIKELY |
| employee_name | Employee Name | GUESS |
| department | Department | LIKELY |
| department | Class | GUESS |
| pay_period_start | Pay Period Start | GUESS |
| pay_period_end | Pay Period End | GUESS |
| pay_date | Pay Date | LIKELY |
| gross_pay | Gross Pay | LIKELY |
| deduction_total | Employee Deductions | GUESS |
| employer_cost_taxes | Employer Taxes | LIKELY |
| employer_cost_contributions | Company Contributions | GUESS |
| net_pay | Net Pay | LIKELY |
| row_type | Type | GUESS |

Required fields and missing optional behavior are identical to Gusto, with
`deduction_total` supplying the deductions array and the two QuickBooks
employer-cost fields supplying employer costs.

Accepted dates are `YYYY-MM-DD`, `MM/DD/YYYY` only when unambiguous because the
day is greater than 12, and `M/D/YYYY` under that same rule. No two-digit years
or month names are accepted.

If `row_type` exists, normalized values `employee`, `department total`, and
`total` identify the structure. Without it, a nonblank employee name is an
employee row; an empty employee with a nonblank department and amounts is a
department total; employee value `TOTAL` with amounts is the grand total. Only
employee rows are staged. Exactly one grand total is required. Department
totals, if present, are validation-only and must equal their employee rows.

PII columns expected and always dropped before `raw_row` construction are:
`Social Security No.`, `SSN`, `Home Address`, `Street`, `City`, `State`, `ZIP`,
`Birth Date`, `Date of Birth`, `Bank Account`, `Account Number`, `Routing Number`,
`Direct Deposit`, `Filing Status`, `Federal Income Tax`, `State Income Tax`, and
`Local Tax`. Employee name alone is retained.

## Refusal rules

1. Refuse an empty file or a header-only file. The error is respectively
   `EMPTY_FILE` or `NO_DATA_ROWS`.
2. Refuse a missing required canonical field with
   `MISSING_REQUIRED_HEADER: <canonical>` and an unknown header with
   `UNKNOWN_HEADER: <exact decoded header>`. Unknown columns are not silently
   dropped: strict refusal prevents unreviewed financial or PII data entering
   staging. The explicit PII drop lists are recognized exceptions.
3. Refuse duplicate canonical headers, including two different aliases mapping
   to one canonical field, with `DUPLICATE_HEADER: <canonical>`.
4. Refuse malformed encoding, delimiter, quoting, record width, interior blank
   row, money, or date with `INVALID_<kind>: row <1-based data row>, field
   <canonical>`. Header failures occur before any row is returned.
5. Refuse any file without exactly one identifiable grand-total row, or with a
   detail row that cannot be classified. Totals and subtotal rows are never
   staged.
6. Refuse unless the sum of staged employee rows equals every supplied
   department total and the grand total for `gross_pay`, `net_pay`, each named
   deduction, and each named employer cost. Tolerance is exactly zero cents;
   the source reports cents, so tolerating a discrepancy could create an
   unbalanced ledger entry. The error names the scope, field, expected cents,
   and actual cents.
7. Refuse a file containing any unknown column. Recognized PII columns are
   dropped at parse time and must not appear in `raw_row`, deductions,
   employer costs, errors containing row values, or staged output.

Refusal is atomic: it returns no batch and no rows, and callers must perform no
database writes. Errors name exact offending headers but never echo PII values.

## What a real sample must settle

A holder of one untouched export from each provider should check these points:

- exact report title and CSV preamble, if any;
- exact headers, their order, and whether category labels are fixed or dynamic;
- delimiter, encoding, line endings, quoting, and BOM behavior;
- whether dates appear in headers, preamble cells, or every detail row, and
  their exact formats and provider locale guarantees;
- exact employee, department subtotal, and grand-total markers;
- whether blank category cells mean absent, zero, or inherited values;
- sign conventions for deductions, taxes, reversals, and voided payroll;
- whether displayed totals are sums of displayed rounded rows;
- all PII columns and any opaque identifiers included by default;
- whether multi-department employees produce one row or multiple rows.

Until checked, every GUESS alias should be replaced or removed rather than
promoted by assumption. Any newly observed spelling must be added explicitly
with a checkable sample reference before acceptance.
