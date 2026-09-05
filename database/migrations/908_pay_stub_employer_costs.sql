-- Canonical JSON list of {label, amount_cents} recorded from the provider, never computed.
-- The empty-list default preserves existing pay stubs as having no recorded employer costs.
ALTER TABLE pay_stubs
ADD COLUMN employer_costs TEXT NOT NULL DEFAULT '[]';
