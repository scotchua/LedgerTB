ALTER TABLE invoices ADD COLUMN tax_rate TEXT NULL;
ALTER TABLE invoices ADD COLUMN tax_amount_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE invoices ADD COLUMN tax_account_id INTEGER NULL REFERENCES accounts(id);

ALTER TABLE bills ADD COLUMN tax_rate TEXT NULL;
ALTER TABLE bills ADD COLUMN tax_amount_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE bills ADD COLUMN tax_account_id INTEGER NULL REFERENCES accounts(id);

CREATE TABLE credit_memos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    memo_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'posted', 'applied', 'voided')),
    original_invoice_id INTEGER NULL REFERENCES invoices(id),
    tax_rate TEXT NULL,
    tax_amount_cents INTEGER NOT NULL DEFAULT 0,
    control_account_id INTEGER NULL REFERENCES accounts(id),
    tax_account_id INTEGER NULL REFERENCES accounts(id),
    journal_entry_id INTEGER NULL REFERENCES journal_entries(id),
    voided_journal_entry_id INTEGER NULL REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE credit_memo_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_memo_id INTEGER NOT NULL REFERENCES credit_memos(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    revenue_account_id INTEGER NOT NULL REFERENCES accounts(id)
);

CREATE TABLE credit_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_memo_id INTEGER NOT NULL REFERENCES credit_memos(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    UNIQUE(credit_memo_id, invoice_id)
);

CREATE INDEX idx_credit_memos_client_customer
    ON credit_memos(client_id, customer_id);
CREATE INDEX idx_credit_memo_lines_memo
    ON credit_memo_lines(credit_memo_id);
CREATE INDEX idx_credit_applications_invoice
    ON credit_applications(invoice_id);
