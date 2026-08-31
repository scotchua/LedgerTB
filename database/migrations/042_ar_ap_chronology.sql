-- Preserve the effective date of allocations so historical aging reports do
-- not change when an old on-account credit is applied later. Existing rows are
-- backfilled from their audit timestamp where possible, bounded by the dates
-- on which both sides of the application existed.
ALTER TABLE payment_allocations ADD COLUMN application_date DATE;
ALTER TABLE bill_payment_allocations ADD COLUMN application_date DATE;
ALTER TABLE credit_applications ADD COLUMN application_date DATE;

UPDATE payment_allocations
SET application_date = (
    SELECT MAX(
        p.payment_date,
        i.invoice_date,
        CASE WHEN payment_allocations.applied_later = 1 THEN
            COALESCE((
                SELECT DATE(al.changed_at)
                FROM audit_log al
                WHERE al.table_name = 'payment_allocations'
                  AND al.record_id = payment_allocations.id
                  AND al.action = 'INSERT'
                ORDER BY al.id LIMIT 1
            ), p.payment_date)
        ELSE p.payment_date END
    )
    FROM payments p, invoices i
    WHERE p.id = payment_allocations.payment_id
      AND i.id = payment_allocations.invoice_id
);

UPDATE bill_payment_allocations
SET application_date = (
    SELECT MAX(
        p.payment_date,
        b.bill_date,
        CASE WHEN bill_payment_allocations.applied_later = 1 THEN
            COALESCE((
                SELECT DATE(al.changed_at)
                FROM audit_log al
                WHERE al.table_name = 'bill_payment_allocations'
                  AND al.record_id = bill_payment_allocations.id
                  AND al.action = 'INSERT'
                ORDER BY al.id LIMIT 1
            ), p.payment_date)
        ELSE p.payment_date END
    )
    FROM bill_payments_v2 p, bills b
    WHERE p.id = bill_payment_allocations.payment_id
      AND b.id = bill_payment_allocations.bill_id
);

UPDATE credit_applications
SET application_date = (
    SELECT MAX(
        cm.memo_date,
        i.invoice_date,
        COALESCE((
            SELECT DATE(al.changed_at)
            FROM audit_log al
            WHERE al.table_name = 'credit_applications'
              AND al.record_id = credit_applications.id
              AND al.action = 'INSERT'
            ORDER BY al.id LIMIT 1
        ), cm.memo_date)
    )
    FROM credit_memos cm, invoices i
    WHERE cm.id = credit_applications.credit_memo_id
      AND i.id = credit_applications.invoice_id
);

-- Older releases allowed an impossible due date. Normalize those rows to the
-- issue date and retain the original value in the append-only audit trail.
INSERT INTO audit_log (
    client_id, table_name, record_id, action, old_values, new_values, performed_by
)
SELECT client_id, 'invoices', id, 'UPDATE',
       '{"due_date":"' || due_date || '"}',
       '{"due_date":"' || invoice_date || '"}',
       'LedgerTB migration 042'
FROM invoices
WHERE due_date < invoice_date;

UPDATE invoices
SET due_date = invoice_date
WHERE due_date < invoice_date;

INSERT INTO audit_log (
    client_id, table_name, record_id, action, old_values, new_values, performed_by
)
SELECT client_id, 'bills', id, 'UPDATE',
       '{"due_date":"' || due_date || '"}',
       '{"due_date":"' || bill_date || '"}',
       'LedgerTB migration 042'
FROM bills
WHERE due_date < bill_date;

UPDATE bills
SET due_date = bill_date
WHERE due_date < bill_date;

-- Cross-row/date invariants cannot be expressed as ALTERed CHECK constraints
-- in SQLite, so triggers enforce them for every writer, not only the UI.
CREATE TRIGGER invoices_due_date_insert
BEFORE INSERT ON invoices
WHEN NEW.due_date < NEW.invoice_date
BEGIN
    SELECT RAISE(ABORT, 'Invoice due date cannot precede invoice date');
END;

CREATE TRIGGER invoices_due_date_update
BEFORE UPDATE OF invoice_date, due_date ON invoices
WHEN NEW.due_date < NEW.invoice_date
BEGIN
    SELECT RAISE(ABORT, 'Invoice due date cannot precede invoice date');
END;

CREATE TRIGGER bills_due_date_insert
BEFORE INSERT ON bills
WHEN NEW.due_date < NEW.bill_date
BEGIN
    SELECT RAISE(ABORT, 'Bill due date cannot precede bill date');
END;

CREATE TRIGGER bills_due_date_update
BEFORE UPDATE OF bill_date, due_date ON bills
WHEN NEW.due_date < NEW.bill_date
BEGIN
    SELECT RAISE(ABORT, 'Bill due date cannot precede bill date');
END;

CREATE TRIGGER payment_allocation_date_insert
BEFORE INSERT ON payment_allocations
WHEN NEW.application_date IS NULL
  OR NEW.application_date < (SELECT payment_date FROM payments WHERE id = NEW.payment_id)
  OR NEW.application_date < (SELECT invoice_date FROM invoices WHERE id = NEW.invoice_id)
BEGIN
    SELECT RAISE(ABORT, 'Customer payment application date is invalid');
END;

CREATE TRIGGER payment_allocation_date_update
BEFORE UPDATE OF payment_id, invoice_id, application_date ON payment_allocations
WHEN NEW.application_date IS NULL
  OR NEW.application_date < (SELECT payment_date FROM payments WHERE id = NEW.payment_id)
  OR NEW.application_date < (SELECT invoice_date FROM invoices WHERE id = NEW.invoice_id)
BEGIN
    SELECT RAISE(ABORT, 'Customer payment application date is invalid');
END;

CREATE TRIGGER bill_payment_allocation_date_insert
BEFORE INSERT ON bill_payment_allocations
WHEN NEW.application_date IS NULL
  OR NEW.application_date < (SELECT payment_date FROM bill_payments_v2 WHERE id = NEW.payment_id)
  OR NEW.application_date < (SELECT bill_date FROM bills WHERE id = NEW.bill_id)
BEGIN
    SELECT RAISE(ABORT, 'Vendor payment application date is invalid');
END;

CREATE TRIGGER bill_payment_allocation_date_update
BEFORE UPDATE OF payment_id, bill_id, application_date ON bill_payment_allocations
WHEN NEW.application_date IS NULL
  OR NEW.application_date < (SELECT payment_date FROM bill_payments_v2 WHERE id = NEW.payment_id)
  OR NEW.application_date < (SELECT bill_date FROM bills WHERE id = NEW.bill_id)
BEGIN
    SELECT RAISE(ABORT, 'Vendor payment application date is invalid');
END;

CREATE TRIGGER credit_application_date_insert
BEFORE INSERT ON credit_applications
WHEN NEW.application_date IS NULL
  OR NEW.application_date < (SELECT memo_date FROM credit_memos WHERE id = NEW.credit_memo_id)
  OR NEW.application_date < (SELECT invoice_date FROM invoices WHERE id = NEW.invoice_id)
BEGIN
    SELECT RAISE(ABORT, 'Credit memo application date is invalid');
END;

CREATE TRIGGER credit_application_date_update
BEFORE UPDATE OF credit_memo_id, invoice_id, application_date ON credit_applications
WHEN NEW.application_date IS NULL
  OR NEW.application_date < (SELECT memo_date FROM credit_memos WHERE id = NEW.credit_memo_id)
  OR NEW.application_date < (SELECT invoice_date FROM invoices WHERE id = NEW.invoice_id)
BEGIN
    SELECT RAISE(ABORT, 'Credit memo application date is invalid');
END;

CREATE TRIGGER payment_refund_date_insert
BEFORE INSERT ON payment_refunds
WHEN NEW.refund_date < (SELECT payment_date FROM payments WHERE id = NEW.payment_id)
BEGIN
    SELECT RAISE(ABORT, 'Customer refund date cannot precede payment date');
END;

CREATE TRIGGER bill_payment_refund_date_insert
BEFORE INSERT ON bill_payment_refunds
WHEN NEW.refund_date < (SELECT payment_date FROM bill_payments_v2 WHERE id = NEW.payment_id)
BEGIN
    SELECT RAISE(ABORT, 'Vendor refund date cannot precede payment date');
END;

CREATE TRIGGER payment_void_date_update
BEFORE UPDATE OF status, voided_journal_entry_id ON payments
WHEN NEW.status = 'voided' AND (
    NEW.voided_journal_entry_id IS NULL OR
    (SELECT entry_date FROM journal_entries WHERE id = NEW.voided_journal_entry_id) < NEW.payment_date
)
BEGIN
    SELECT RAISE(ABORT, 'Customer payment void date cannot precede payment date');
END;

CREATE TRIGGER bill_payment_void_date_update
BEFORE UPDATE OF status, voided_journal_entry_id ON bill_payments_v2
WHEN NEW.status = 'voided' AND (
    NEW.voided_journal_entry_id IS NULL OR
    (SELECT entry_date FROM journal_entries WHERE id = NEW.voided_journal_entry_id) < NEW.payment_date
)
BEGIN
    SELECT RAISE(ABORT, 'Vendor payment void date cannot precede payment date');
END;

CREATE TRIGGER invoice_void_date_update
BEFORE UPDATE OF status, voided_journal_entry_id ON invoices
WHEN NEW.status = 'voided' AND (
    NEW.voided_journal_entry_id IS NULL OR
    (SELECT entry_date FROM journal_entries WHERE id = NEW.voided_journal_entry_id) < NEW.invoice_date
)
BEGIN
    SELECT RAISE(ABORT, 'Invoice void date cannot precede invoice date');
END;

CREATE TRIGGER bill_void_date_update
BEFORE UPDATE OF status, voided_journal_entry_id ON bills
WHEN NEW.status = 'voided' AND (
    NEW.voided_journal_entry_id IS NULL OR
    (SELECT entry_date FROM journal_entries WHERE id = NEW.voided_journal_entry_id) < NEW.bill_date
)
BEGIN
    SELECT RAISE(ABORT, 'Bill void date cannot precede bill date');
END;

CREATE TRIGGER credit_memo_void_date_update
BEFORE UPDATE OF status, voided_journal_entry_id ON credit_memos
WHEN NEW.status = 'voided' AND (
    NEW.voided_journal_entry_id IS NULL OR
    (SELECT entry_date FROM journal_entries WHERE id = NEW.voided_journal_entry_id) < NEW.memo_date
)
BEGIN
    SELECT RAISE(ABORT, 'Credit memo void date cannot precede memo date');
END;
