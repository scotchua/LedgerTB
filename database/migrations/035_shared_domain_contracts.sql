CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    name TEXT NOT NULL,
    UNIQUE(client_id, name)
);

ALTER TABLE employees ADD COLUMN department_id INTEGER
    REFERENCES departments(id);

ALTER TABLE inventory_movements ADD COLUMN source_type TEXT;
ALTER TABLE inventory_movements ADD COLUMN source_id INTEGER;
ALTER TABLE inventory_movements ADD COLUMN source_line_id INTEGER;

CREATE UNIQUE INDEX idx_inventory_movements_source
    ON inventory_movements(source_type, source_id, source_line_id)
    WHERE source_type IS NOT NULL;

CREATE TABLE invoices_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'posted', 'paid', 'partially_paid', 'voided')),
    journal_entry_id INTEGER,
    voided_journal_entry_id INTEGER,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (voided_journal_entry_id) REFERENCES journal_entries(id)
);

INSERT INTO invoices_new (
    id, client_id, customer_id, invoice_date, due_date, status,
    journal_entry_id, voided_journal_entry_id
)
SELECT id, client_id, customer_id, invoice_date, due_date, status,
       journal_entry_id, NULL
FROM invoices;

DROP TABLE invoices;
ALTER TABLE invoices_new RENAME TO invoices;
CREATE INDEX idx_invoices_client ON invoices(client_id);

CREATE TABLE bills_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    vendor_id INTEGER NOT NULL,
    bill_date DATE NOT NULL,
    due_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'posted', 'paid', 'partially_paid', 'voided')),
    journal_entry_id INTEGER,
    voided_journal_entry_id INTEGER,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (vendor_id) REFERENCES vendors(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (voided_journal_entry_id) REFERENCES journal_entries(id)
);

INSERT INTO bills_new (
    id, client_id, vendor_id, bill_date, due_date, status,
    journal_entry_id, voided_journal_entry_id
)
SELECT id, client_id, vendor_id, bill_date, due_date, status,
       journal_entry_id, NULL
FROM bills;

DROP TABLE bills;
ALTER TABLE bills_new RENAME TO bills;
CREATE INDEX idx_bills_client ON bills(client_id);
