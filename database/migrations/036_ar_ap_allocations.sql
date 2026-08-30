ALTER TABLE invoices ADD COLUMN control_account_id INTEGER
    REFERENCES accounts(id);
ALTER TABLE bills ADD COLUMN control_account_id INTEGER
    REFERENCES accounts(id);

CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    payment_date DATE NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    deposit_account_id INTEGER NOT NULL REFERENCES accounts(id),
    control_account_id INTEGER NOT NULL REFERENCES accounts(id),
    memo TEXT,
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    status TEXT NOT NULL DEFAULT 'recorded'
        CHECK(status IN ('recorded', 'voided')),
    voided_journal_entry_id INTEGER REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payment_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    applied_later INTEGER NOT NULL DEFAULT 0 CHECK(applied_later IN (0, 1)),
    UNIQUE(payment_id, invoice_id)
);

CREATE TABLE payment_refunds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    refund_date DATE NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    from_account_id INTEGER NOT NULL REFERENCES accounts(id),
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bill_payments_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    payment_date DATE NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    payment_account_id INTEGER NOT NULL REFERENCES accounts(id),
    control_account_id INTEGER NOT NULL REFERENCES accounts(id),
    memo TEXT,
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    status TEXT NOT NULL DEFAULT 'recorded'
        CHECK(status IN ('recorded', 'voided')),
    voided_journal_entry_id INTEGER REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bill_payment_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES bill_payments_v2(id),
    bill_id INTEGER NOT NULL REFERENCES bills(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    applied_later INTEGER NOT NULL DEFAULT 0 CHECK(applied_later IN (0, 1)),
    UNIQUE(payment_id, bill_id)
);

CREATE TABLE bill_payment_refunds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES bill_payments_v2(id),
    refund_date DATE NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    from_account_id INTEGER NOT NULL REFERENCES accounts(id),
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payments_client_customer ON payments(client_id, customer_id);
CREATE INDEX idx_payment_allocations_invoice ON payment_allocations(invoice_id);
CREATE INDEX idx_payment_refunds_payment ON payment_refunds(payment_id);
CREATE INDEX idx_bill_payments_v2_client_vendor ON bill_payments_v2(client_id, vendor_id);
CREATE INDEX idx_bill_payment_allocations_bill ON bill_payment_allocations(bill_id);
CREATE INDEX idx_bill_payment_refunds_payment ON bill_payment_refunds(payment_id);
