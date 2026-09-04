-- NULL means a pre-905 or ordinary reversal; only 'void' pairs are hidden by default.
ALTER TABLE journal_entries ADD COLUMN reversal_kind TEXT NULL
    CHECK (reversal_kind IN ('reversal', 'void'));
