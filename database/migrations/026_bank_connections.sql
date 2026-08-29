CREATE TABLE bank_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    bank_account_id INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'simplefin'
        CHECK(provider IN ('simplefin')),
    secret_name TEXT NOT NULL,
    last_synced_at TIMESTAMP,
    sync_window_start DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (bank_account_id) REFERENCES accounts(id),
    UNIQUE (client_id, bank_account_id, provider),
    UNIQUE (secret_name)
);

CREATE INDEX idx_bank_connections_client
ON bank_connections(client_id, bank_account_id);
