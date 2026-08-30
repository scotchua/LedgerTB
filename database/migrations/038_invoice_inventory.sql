ALTER TABLE invoice_lines ADD COLUMN inventory_item_id INTEGER NULL
    REFERENCES inventory_items(id);
