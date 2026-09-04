-- Suggestions are append-only proposals; decided_at is the tri-state marker
-- for never reviewed, human coded, or human cleared. RESTRICT keeps proposal
-- evidence until ImportedTransaction.delete/delete_batch removes and audits it.
CREATE TABLE import_suggestions (
    id INTEGER PRIMARY KEY,
    imported_transaction_id INTEGER NOT NULL REFERENCES imported_transactions(id) ON DELETE RESTRICT,
    suggested_account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    confidence TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    reason TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 500),
    source TEXT NOT NULL CHECK (source IN ('assistant','in_app')),
    request_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL
);

CREATE INDEX idx_import_suggestions_txn
    ON import_suggestions(imported_transaction_id, created_at DESC, id DESC);
CREATE UNIQUE INDEX idx_import_suggestions_request
    ON import_suggestions(request_id, imported_transaction_id);

ALTER TABLE imported_transactions ADD COLUMN decided_account_id INTEGER NULL REFERENCES accounts(id);
ALTER TABLE imported_transactions ADD COLUMN decided_at TIMESTAMP NULL;
ALTER TABLE imported_transactions ADD COLUMN decided_by TEXT NULL;
ALTER TABLE imported_transactions ADD COLUMN decided_suggestion_id INTEGER NULL REFERENCES import_suggestions(id);

CREATE TRIGGER import_suggestions_same_client
BEFORE INSERT ON import_suggestions
WHEN (SELECT client_id FROM imported_transactions WHERE id = NEW.imported_transaction_id)
     != (SELECT client_id FROM accounts WHERE id = NEW.suggested_account_id)
BEGIN
    SELECT RAISE(ABORT, 'suggestion account belongs to another client');
END;

CREATE TRIGGER import_suggestions_undecided
BEFORE INSERT ON import_suggestions
WHEN (SELECT decided_at FROM imported_transactions WHERE id = NEW.imported_transaction_id) IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'transaction already decided');
END;
