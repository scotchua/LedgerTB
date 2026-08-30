CREATE TABLE email_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    sent_to TEXT NOT NULL,
    subject TEXT NOT NULL,
    document_type TEXT NOT NULL,
    document_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('sent', 'failed')),
    error TEXT NULL,
    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_email_log_client_document
    ON email_log(client_id, document_type, document_id);
