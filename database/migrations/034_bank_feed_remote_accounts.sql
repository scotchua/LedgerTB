CREATE TABLE bank_connection_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL,
    remote_account_id TEXT NOT NULL,
    remote_account_name TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (connection_id) REFERENCES bank_connections(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    UNIQUE (connection_id, remote_account_id)
);

CREATE INDEX idx_bank_connection_accounts_connection
ON bank_connection_accounts(connection_id, remote_account_id);

ALTER TABLE bank_connection_syncs ADD COLUMN remote_account_id TEXT;

CREATE INDEX idx_bank_connection_syncs_remote_latest
ON bank_connection_syncs(connection_id, remote_account_id, id);

ALTER TABLE bank_connections ADD COLUMN revoked_at TIMESTAMP;
