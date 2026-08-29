-- Payroll bookkeeping records figures already determined outside LedgerTB.
-- Employee records intentionally contain only the minimal identifying fields
-- needed to associate those figures with a person.
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'terminated')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE pay_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    pay_period_start DATE NOT NULL,
    pay_period_end DATE NOT NULL,
    pay_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'posted')),
    journal_entry_id INTEGER,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);

CREATE TABLE pay_stubs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_run_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    gross_pay_cents INTEGER NOT NULL CHECK(gross_pay_cents >= 0),
    deductions TEXT NOT NULL,
    net_pay_cents INTEGER NOT NULL CHECK(net_pay_cents >= 0),
    FOREIGN KEY (pay_run_id) REFERENCES pay_runs(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    UNIQUE(pay_run_id, employee_id)
);

CREATE INDEX idx_employees_client ON employees(client_id);
CREATE INDEX idx_pay_runs_client ON pay_runs(client_id);
CREATE INDEX idx_pay_stubs_pay_run ON pay_stubs(pay_run_id);

