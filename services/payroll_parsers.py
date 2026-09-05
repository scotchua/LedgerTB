import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN


@dataclass(frozen=True)
class ParsedBatch:
    provider: str
    source_report: str
    rows: list[dict]

    def __getitem__(self, key):
        return getattr(self, key)


class ParserRefusal(ValueError):
    def __init__(self, message, *, unknown_headers=None,
                 missing_required_headers=None, malformed_rows=None):
        super().__init__(message)
        self.unknown_headers = unknown_headers or []
        self.missing_required_headers = missing_required_headers or []
        self.malformed_rows = malformed_rows or []


GUSTO_ALIASES = {
    "employee_name": (("Employee", "LIKELY"), ("Employee Name", "GUESS")),
    "department": (("Department", "LIKELY"),),
    "pay_period_start": (("Pay Period Start", "GUESS"),),
    "pay_period_end": (("Pay Period End", "GUESS"),),
    "pay_date": (("Check Date", "GUESS"), ("Pay Date", "LIKELY")),
    "gross_pay": (("Gross Pay", "LIKELY"),),
    "deduction_benefits": (("Benefits", "GUESS"),),
    "deduction_employee_taxes": (("Employee Taxes", "GUESS"),),
    "employer_cost_employer_taxes": (("Employer Taxes", "LIKELY"),),
    "employer_cost_contributions": (("Employer Contributions", "GUESS"),),
    "net_pay": (("Net Pay", "LIKELY"),),
    "row_type": (("Row Type", "GUESS"),),
}

QBO_ALIASES = {
    "employee_name": (("Employee", "LIKELY"), ("Employee Name", "GUESS")),
    "department": (("Department", "LIKELY"), ("Class", "GUESS")),
    "pay_period_start": (("Pay Period Start", "GUESS"),),
    "pay_period_end": (("Pay Period End", "GUESS"),),
    "pay_date": (("Pay Date", "LIKELY"),),
    "gross_pay": (("Gross Pay", "LIKELY"),),
    "deduction_total": (("Employee Deductions", "GUESS"),),
    "employer_cost_taxes": (("Employer Taxes", "LIKELY"),),
    "employer_cost_contributions": (("Company Contributions", "GUESS"),),
    "net_pay": (("Net Pay", "LIKELY"),),
    "row_type": (("Type", "GUESS"),),
}

_PII = {
    "gusto": (
        "SSN", "Social Security Number", "Home Address", "Address", "Address 2",
        "City", "State", "ZIP", "Date of Birth", "DOB", "Bank Account",
        "Bank Account Number", "Routing Number", "Account Type", "Filing Status",
        "Federal Withholding", "State Withholding", "Local Withholding",
    ),
    "quickbooks": (
        "Social Security No.", "SSN", "Home Address", "Street", "City", "State",
        "ZIP", "Birth Date", "Date of Birth", "Bank Account", "Account Number",
        "Routing Number", "Direct Deposit", "Filing Status", "Federal Income Tax",
        "State Income Tax", "Local Tax",
    ),
}

_REQUIRED = {
    "employee_name", "pay_period_start", "pay_period_end", "pay_date",
    "gross_pay", "net_pay",
}
_MONEY_FIELDS = {
    "gross_pay", "net_pay", "deduction_benefits", "deduction_employee_taxes",
    "deduction_total", "employer_cost_employer_taxes", "employer_cost_taxes",
    "employer_cost_contributions",
}
_DEDUCTIONS = {
    "gusto": ("deduction_benefits", "deduction_employee_taxes"),
    "quickbooks": ("deduction_total",),
}
_EMPLOYER_COSTS = {
    "gusto": ("employer_cost_employer_taxes", "employer_cost_contributions"),
    "quickbooks": ("employer_cost_taxes", "employer_cost_contributions"),
}
_LABELS = {
    "deduction_benefits": "Benefits",
    "deduction_employee_taxes": "Employee Taxes",
    "deduction_total": "Employee Deductions",
    "employer_cost_employer_taxes": "Employer Taxes",
    "employer_cost_taxes": "Employer Taxes",
    "employer_cost_contributions": {
        "gusto": "Employer Contributions", "quickbooks": "Company Contributions",
    },
}


def _normalize_header(value, first=False):
    if first and value.startswith("\ufeff"):
        value = value[1:]
    return " ".join(value.split()).casefold()


def _aliases(provider):
    return GUSTO_ALIASES if provider == "gusto" else QBO_ALIASES


def _header_map(provider):
    return {
        _normalize_header(alias): canonical
        for canonical, aliases in _aliases(provider).items()
        for alias, _confidence in aliases
    }


def _pii_headers(provider):
    return {_normalize_header(header) for header in _PII[provider]}


def _read_records(content):
    if not content:
        raise ParserRefusal("EMPTY_FILE")
    if "\x00" in content:
        raise ParserRefusal("INVALID_ENCODING: row 0, field file")
    try:
        reader = csv.reader(io.StringIO(content, newline=""), strict=True)
        return list(reader)
    except (csv.Error, UnicodeError) as exc:
        raise ParserRefusal("INVALID_RECORD: row 0, field row") from exc


def detect_provider(content):
    try:
        records = _read_records(content)
    except ParserRefusal:
        return None
    if not records:
        return None
    headers = records[0]
    matches = []
    for provider in ("gusto", "quickbooks"):
        known = set(_header_map(provider)) | _pii_headers(provider)
        normalized = [_normalize_header(value, index == 0)
                      for index, value in enumerate(headers)]
        if normalized and all(value in known for value in normalized):
            canonicals = {_header_map(provider).get(value) for value in normalized}
            if _REQUIRED.issubset(canonicals):
                matches.append(provider)
    return matches[0] if len(matches) == 1 else None


def _money(value, row_number, field):
    raw = value.strip()
    if raw == "":
        return None
    negative = False
    if raw.startswith("(") or raw.endswith(")"):
        if not (raw.startswith("(") and raw.endswith(")")):
            raise ParserRefusal(
                f"INVALID_MONEY: row {row_number}, field {field}",
                malformed_rows=[row_number],
            )
        negative = True
        raw = raw[1:-1]
    if raw.endswith("-"):
        if negative:
            raise ParserRefusal(
                f"INVALID_MONEY: row {row_number}, field {field}",
                malformed_rows=[row_number],
            )
        negative = True
        raw = raw[:-1]
    if raw.startswith("$"):
        raw = raw[1:]
    if "$" in raw or any(not (char.isdigit() or char in ",.") for char in raw):
        raise ParserRefusal(
            f"INVALID_MONEY: row {row_number}, field {field}",
            malformed_rows=[row_number],
        )
    if raw.count(".") > 1:
        valid = False
    else:
        whole = raw.split(".", 1)[0]
        groups = whole.split(",")
        valid = bool(whole) and (
            len(groups) == 1 and groups[0].isdigit()
            or 1 <= len(groups[0]) <= 3 and groups[0].isdigit()
            and len(groups) > 1 and all(len(group) == 3 and group.isdigit()
                                    for group in groups[1:])
        )
        fraction = raw.split(".", 1)[1] if "." in raw else None
        valid = valid and (fraction is None or fraction.isdigit())
    if not valid:
        raise ParserRefusal(
            f"INVALID_MONEY: row {row_number}, field {field}",
            malformed_rows=[row_number],
        )
    try:
        cents = int((Decimal(raw.replace(",", "")) * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN
        ))
    except InvalidOperation as exc:
        raise ParserRefusal(
            f"INVALID_MONEY: row {row_number}, field {field}",
            malformed_rows=[row_number],
        ) from exc
    return -cents if negative else cents


def _date(value, provider, row_number, field):
    raw = value.strip()
    parsed = None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        if "/" in raw:
            parts = raw.split("/")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                month, day, year = map(int, parts)
                if month <= 12 and day <= 12:
                    parsed = None
                elif len(parts[2]) == 4 and (provider == "quickbooks" or
                                             len(parts[0]) == len(parts[1]) == 2):
                    try:
                        parsed = date(year, month, day)
                    except ValueError:
                        pass
        elif provider == "gusto":
            try:
                parsed = datetime.strptime(raw.title(), "%b %d, %Y").date()
            except ValueError:
                pass
    if parsed is None:
        raise ParserRefusal(
            f"INVALID_DATE: row {row_number}, field {field}",
            malformed_rows=[row_number],
        )
    return parsed.isoformat()


def _canonical_items(provider, fields, values, present):
    if not any(field in present for field in fields):
        return None
    items = []
    for field in fields:
        amount = values.get(field)
        if field in present and amount is not None:
            label = _LABELS[field]
            if isinstance(label, dict):
                label = label[provider]
            items.append({"amount_cents": amount, "label": label})
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def _sum(rows, field):
    return sum(row["values"].get(field) or 0 for row in rows)


def _parse(provider, content):
    records = _read_records(content)
    while records and (records[-1] == [] or all(not cell for cell in records[-1])):
        records.pop()
    if not records:
        raise ParserRefusal("EMPTY_FILE")
    if len(records) == 1:
        raise ParserRefusal("NO_DATA_ROWS")
    headers = records[0]
    if len(headers) == 1 and any(delimiter in headers[0] for delimiter in (";", "\t", "|")):
        raise ParserRefusal("INVALID_DELIMITER: row 0, field file")
    aliases = _header_map(provider)
    pii = _pii_headers(provider)
    canonical_headers = []
    unknown = []
    seen = set()
    for index, header in enumerate(headers):
        normalized = _normalize_header(header, index == 0)
        canonical = aliases.get(normalized)
        if canonical is None:
            if normalized not in pii:
                unknown.append(header)
            canonical_headers.append(None)
        else:
            if canonical in seen:
                raise ParserRefusal(f"DUPLICATE_HEADER: {canonical}")
            seen.add(canonical)
            canonical_headers.append(canonical)
    if unknown:
        detail = "; ".join(
            f"UNKNOWN_HEADER: {header}. This column is not one this parser knows for "
            f"{provider}. The parser was written without a real export; send one export "
            "so the aliases can be confirmed."
            for header in unknown
        )
        raise ParserRefusal(detail, unknown_headers=unknown)
    missing = sorted(_REQUIRED - seen)
    if missing:
        raise ParserRefusal(
            "; ".join(f"MISSING_REQUIRED_HEADER: {field}" for field in missing),
            missing_required_headers=missing,
        )

    parsed = []
    for row_number, record in enumerate(records[1:], start=1):
        if not record or all(cell == "" for cell in record):
            raise ParserRefusal(
                f"INVALID_RECORD: row {row_number}, field row",
                malformed_rows=[row_number],
            )
        if len(record) != len(headers):
            raise ParserRefusal(
                f"INVALID_RECORD: row {row_number}, field row",
                malformed_rows=[row_number],
            )
        raw_values = {canonical_headers[index]: value for index, value in enumerate(record)
                      if canonical_headers[index] is not None}
        values = dict(raw_values)
        for field in _MONEY_FIELDS & seen:
            values[field] = _money(raw_values[field], row_number, field)
        for field in ("pay_period_start", "pay_period_end", "pay_date"):
            if raw_values[field].strip():
                values[field] = _date(raw_values[field], provider, row_number, field)
            else:
                values[field] = None
        row_type = raw_values.get("row_type", "").strip().casefold()
        employee = raw_values["employee_name"].strip()
        department = raw_values.get("department", "").strip()
        has_amount = any(values.get(field) is not None for field in _MONEY_FIELDS & seen)
        if "row_type" in seen:
            allowed = {"employee", "department total",
                       "grand total" if provider == "gusto" else "total"}
            if row_type not in allowed:
                raise ParserRefusal(f"INVALID_RECORD: row {row_number}, field row_type",
                                    malformed_rows=[row_number])
            kind = "grand" if row_type in ("grand total", "total") else row_type
        elif employee.casefold() == "total" and has_amount:
            kind = "grand"
        elif employee:
            kind = "employee"
        elif department and has_amount:
            kind = "department total"
        else:
            raise ParserRefusal(f"INVALID_RECORD: row {row_number}, field row",
                                malformed_rows=[row_number])
        if kind == "employee":
            if any(values[field] is None for field in _REQUIRED - {"employee_name"}):
                field = next(field for field in _REQUIRED - {"employee_name"}
                             if values[field] is None)
                raise ParserRefusal(f"INVALID_RECORD: row {row_number}, field {field}",
                                    malformed_rows=[row_number])
            if values["pay_period_end"] < values["pay_period_start"]:
                raise ParserRefusal(
                    f"INVALID_DATE: row {row_number}, field pay_period_end",
                    malformed_rows=[row_number],
                )
            if values["pay_date"] < values["pay_period_end"]:
                raise ParserRefusal(
                    f"INVALID_DATE: row {row_number}, field pay_date",
                    malformed_rows=[row_number],
                )
        parsed.append({"kind": kind, "department": department, "values": values,
                       "raw_values": raw_values})

    employees = [row for row in parsed if row["kind"] == "employee"]
    grand_totals = [row for row in parsed if row["kind"] == "grand"]
    if len(grand_totals) != 1:
        raise ParserRefusal("MISSING_GRAND_TOTAL" if not grand_totals
                            else "MULTIPLE_GRAND_TOTALS")
    total_fields = ["gross_pay", "net_pay", *_DEDUCTIONS[provider],
                    *_EMPLOYER_COSTS[provider]]
    for field in total_fields:
        if field not in seen:
            continue
        expected = grand_totals[0]["values"].get(field) or 0
        actual = _sum(employees, field)
        if expected != actual:
            raise ParserRefusal(
                f"TOTAL_MISMATCH: grand total, {field}, expected {expected}, actual {actual}"
            )
    for subtotal in (row for row in parsed if row["kind"] == "department total"):
        department_rows = [row for row in employees
                           if row["department"] == subtotal["department"]]
        for field in total_fields:
            if field not in seen:
                continue
            expected = subtotal["values"].get(field) or 0
            actual = _sum(department_rows, field)
            if expected != actual:
                raise ParserRefusal(
                    f"TOTAL_MISMATCH: department {subtotal['department']}, {field}, "
                    f"expected {expected}, actual {actual}"
                )

    output = []
    present = set(seen)
    for row in employees:
        values = row["values"]
        raw_row = json.dumps(row["raw_values"], ensure_ascii=False,
                             separators=(",", ":"), sort_keys=True)
        output.append({
            "employee_name_raw": row["raw_values"]["employee_name"],
            "department_raw": row["raw_values"].get("department") or None,
            "pay_period_start": values["pay_period_start"],
            "pay_period_end": values["pay_period_end"],
            "pay_date": values["pay_date"],
            "gross_pay_cents": values["gross_pay"],
            "deductions": _canonical_items(provider, _DEDUCTIONS[provider], values, present),
            "employer_costs": _canonical_items(provider, _EMPLOYER_COSTS[provider], values, present),
            "net_pay_cents": values["net_pay"],
            "raw_row": raw_row,
            "status": "pending",
        })
    return ParsedBatch(provider, "payroll_journal" if provider == "gusto"
                       else "payroll_summary", output)


def parse_gusto_payroll_journal(content):
    return _parse("gusto", content)


def parse_qbo_payroll_summary(content):
    return _parse("quickbooks", content)
