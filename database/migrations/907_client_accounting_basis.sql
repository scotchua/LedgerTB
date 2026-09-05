-- A person's declaration of accounting basis; LedgerTB never infers it.
-- NULL means no basis prints on statements.
ALTER TABLE clients ADD COLUMN accounting_basis TEXT NULL CHECK (accounting_basis IN ('cash','accrual'));
