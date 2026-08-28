CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    inventory_account_id INTEGER NOT NULL,
    cogs_account_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (inventory_account_id) REFERENCES accounts(id),
    FOREIGN KEY (cogs_account_id) REFERENCES accounts(id),
    UNIQUE(client_id, sku)
);

CREATE TABLE inventory_movements (
    id INTEGER PRIMARY KEY,
    inventory_item_id INTEGER NOT NULL,
    movement_date DATE NOT NULL,
    movement_type TEXT NOT NULL CHECK(movement_type IN (
        'purchase', 'sale', 'adjustment', 'count'
    )),
    quantity REAL NOT NULL,
    unit_cost_cents INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    journal_entry_id INTEGER,
    FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);

CREATE INDEX idx_inventory_items_client ON inventory_items(client_id);
CREATE INDEX idx_inventory_movements_item_date
    ON inventory_movements(inventory_item_id, movement_date, id);
