CREATE TABLE document_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    doc_type TEXT NOT NULL,
    doc_key TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK(
        length(content_hash) = 64
        AND content_hash NOT GLOB '*[^0-9a-f]*'
    ),
    canonicalization_version INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    audit_log_id INTEGER,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (audit_log_id) REFERENCES audit_log(id)
);

CREATE INDEX idx_document_audits_client ON document_audits(client_id);
CREATE INDEX idx_document_audits_doc_key ON document_audits(doc_type, doc_key);
CREATE INDEX idx_document_audits_audit_log ON document_audits(audit_log_id);
