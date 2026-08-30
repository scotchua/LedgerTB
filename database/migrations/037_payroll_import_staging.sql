CREATE TABLE payroll_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    provider TEXT NOT NULL CHECK(provider IN ('gusto', 'quickbooks')),
    source_report TEXT NOT NULL,
    file_name TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payroll_import_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES payroll_import_batches(id),
    employee_name_raw TEXT NOT NULL,
    matched_employee_id INTEGER REFERENCES employees(id),
    department_raw TEXT,
    matched_department_id INTEGER REFERENCES departments(id),
    pay_period_start DATE,
    pay_period_end DATE,
    pay_date DATE,
    gross_pay_cents INTEGER,
    deductions TEXT,
    employer_costs TEXT,
    net_pay_cents INTEGER,
    raw_row TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'accepted', 'dismissed'))
);

CREATE INDEX idx_payroll_import_batches_client
    ON payroll_import_batches(client_id);
CREATE INDEX idx_payroll_import_rows_batch
    ON payroll_import_rows(batch_id);
