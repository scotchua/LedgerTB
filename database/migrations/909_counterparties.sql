CREATE TABLE counterparties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    kind TEXT NOT NULL CHECK (kind IN ('customer', 'vendor', 'employee', 'other')),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    source_id INTEGER,
    UNIQUE(kind, source_id)
);

ALTER TABLE journal_entry_lines ADD COLUMN counterparty_id INTEGER NULL
    REFERENCES counterparties(id);

CREATE INDEX idx_journal_lines_counterparty_amount
    ON journal_entry_lines(counterparty_id, (debit - credit), journal_entry_id);

INSERT INTO counterparties (client_id, kind, display_name, source_id)
    SELECT client_id, 'customer', name, id FROM customers ORDER BY id;
INSERT INTO counterparties (client_id, kind, display_name, source_id)
    SELECT client_id, 'vendor', name, id FROM vendors ORDER BY id;

-- Source IDs are typed by kind; names and free-form journal text are not links.
CREATE TRIGGER counterparties_source_insert
BEFORE INSERT ON counterparties
WHEN NEW.source_id IS NOT NULL AND (
    (NEW.kind = 'customer' AND NOT EXISTS (
        SELECT 1 FROM customers WHERE id = NEW.source_id AND client_id = NEW.client_id))
    OR (NEW.kind = 'vendor' AND NOT EXISTS (
        SELECT 1 FROM vendors WHERE id = NEW.source_id AND client_id = NEW.client_id))
    OR (NEW.kind = 'employee' AND NOT EXISTS (
        SELECT 1 FROM employees WHERE id = NEW.source_id AND client_id = NEW.client_id))
    OR NEW.kind = 'other'
)
BEGIN
    SELECT RAISE(ABORT, 'Counterparty source must belong to the selected client.');
END;

CREATE TRIGGER counterparties_identity_update
BEFORE UPDATE OF client_id, kind, source_id ON counterparties
WHEN NEW.client_id != OLD.client_id OR NEW.kind != OLD.kind
    OR NEW.source_id IS NOT OLD.source_id
BEGIN
    SELECT RAISE(ABORT, 'Counterparty source identity cannot be changed.');
END;

CREATE TRIGGER journal_lines_counterparty_insert
BEFORE INSERT ON journal_entry_lines
WHEN NEW.counterparty_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM counterparties c JOIN journal_entries j ON j.client_id = c.client_id
    WHERE c.id = NEW.counterparty_id AND j.id = NEW.journal_entry_id
)
BEGIN
    SELECT RAISE(ABORT, 'Counterparty must belong to the journal entry client.');
END;

CREATE TRIGGER journal_lines_counterparty_update
BEFORE UPDATE OF counterparty_id, journal_entry_id ON journal_entry_lines
WHEN NEW.counterparty_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM counterparties c JOIN journal_entries j ON j.client_id = c.client_id
    WHERE c.id = NEW.counterparty_id AND j.id = NEW.journal_entry_id
)
BEGIN
    SELECT RAISE(ABORT, 'Counterparty must belong to the journal entry client.');
END;

CREATE VIEW journal_counterparty_sources AS
    SELECT d.client_id, j.id AS journal_entry_id, 'customer' AS kind,
           d.customer_id AS source_id, 'invoice:' || d.id AS source_reference,
           d.voided_journal_entry_id IS NOT NULL AS reversed
    FROM invoices d JOIN journal_entries j
      ON j.id IN (d.journal_entry_id, d.voided_journal_entry_id) AND j.client_id = d.client_id
    UNION ALL
    SELECT d.client_id, j.id, 'vendor', d.vendor_id, 'bill:' || d.id,
           d.voided_journal_entry_id IS NOT NULL
    FROM bills d JOIN journal_entries j
      ON j.id IN (d.journal_entry_id, d.voided_journal_entry_id) AND j.client_id = d.client_id
    UNION ALL
    SELECT p.client_id, j.id, 'customer', p.customer_id, 'customer_payment:' || p.id,
           p.voided_journal_entry_id IS NOT NULL
    FROM payments p JOIN journal_entries j
      ON j.id IN (p.journal_entry_id, p.voided_journal_entry_id) AND j.client_id = p.client_id
    UNION ALL
    SELECT p.client_id, j.id, 'vendor', p.vendor_id, 'vendor_payment:' || p.id,
           p.voided_journal_entry_id IS NOT NULL
    FROM bill_payments_v2 p JOIN journal_entries j
      ON j.id IN (p.journal_entry_id, p.voided_journal_entry_id) AND j.client_id = p.client_id
    UNION ALL
    SELECT p.client_id, r.journal_entry_id, 'customer', p.customer_id,
           'customer_refund:' || r.id, 0
    FROM payment_refunds r JOIN payments p ON p.id = r.payment_id
    UNION ALL
    SELECT p.client_id, r.journal_entry_id, 'vendor', p.vendor_id,
           'vendor_refund:' || r.id, 0
    FROM bill_payment_refunds r JOIN bill_payments_v2 p ON p.id = r.payment_id
    UNION ALL
    SELECT d.client_id, j.id, 'customer', d.customer_id, 'credit_memo:' || d.id,
           d.voided_journal_entry_id IS NOT NULL
    FROM credit_memos d JOIN journal_entries j
      ON j.id IN (d.journal_entry_id, d.voided_journal_entry_id) AND j.client_id = d.client_id
    UNION ALL
    SELECT d.client_id, p.journal_entry_id, 'customer', d.customer_id,
           'legacy_invoice_payment:' || p.id, 0
    FROM invoice_payments p JOIN invoices d ON d.id = p.invoice_id
    UNION ALL
    SELECT d.client_id, p.journal_entry_id, 'vendor', d.vendor_id,
           'legacy_bill_payment:' || p.id, 0
    FROM bill_payments p JOIN bills d ON d.id = p.bill_id
    UNION ALL
    SELECT d.client_id, m.journal_entry_id, 'customer', d.customer_id,
           'invoice_inventory:' || d.id, d.voided_journal_entry_id IS NOT NULL
    FROM inventory_movements m JOIN invoices d ON d.id = m.source_id
    WHERE m.source_type IN ('invoice', 'invoice_void');

-- Propagate only explicit source and reversal links, including old AR/AP voids.
WITH RECURSIVE attributed(client_id, journal_entry_id, counterparty_id) AS (
    SELECT s.client_id, s.journal_entry_id, c.id
    FROM journal_counterparty_sources s JOIN counterparties c
      ON c.client_id = s.client_id AND c.kind = s.kind AND c.source_id = s.source_id
    UNION
    SELECT a.client_id, j.id, a.counterparty_id
    FROM attributed a JOIN journal_entries original ON original.id = a.journal_entry_id
    JOIN journal_entries j ON j.client_id = a.client_id AND (
        j.reverses_journal_entry_id = original.id OR j.reversed_by_journal_entry_id = original.id
        OR j.id = original.reverses_journal_entry_id OR j.id = original.reversed_by_journal_entry_id
    )
), unambiguous AS (
    SELECT a.journal_entry_id, MIN(a.counterparty_id) AS counterparty_id
    FROM attributed a JOIN journal_entries j
      ON j.id = a.journal_entry_id AND j.client_id = a.client_id
    GROUP BY a.journal_entry_id HAVING COUNT(DISTINCT a.counterparty_id) = 1
)
UPDATE journal_entry_lines SET counterparty_id = (
    SELECT u.counterparty_id FROM unambiguous u WHERE u.journal_entry_id = journal_entry_lines.journal_entry_id
)
WHERE journal_entry_id IN (SELECT journal_entry_id FROM unambiguous);
