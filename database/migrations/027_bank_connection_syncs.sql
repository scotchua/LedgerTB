CREATE TABLE bank_connection_syncs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL,
    synced_at TIMESTAMP NOT NULL,
    sync_window_start DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (connection_id) REFERENCES bank_connections(id)
);

CREATE INDEX idx_bank_connection_syncs_latest
ON bank_connection_syncs(connection_id, id);
