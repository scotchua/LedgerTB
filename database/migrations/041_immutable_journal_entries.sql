ALTER TABLE journal_entries ADD COLUMN reverses_journal_entry_id INTEGER NULL
    REFERENCES journal_entries(id);
ALTER TABLE journal_entries ADD COLUMN reversed_by_journal_entry_id INTEGER NULL
    REFERENCES journal_entries(id);
