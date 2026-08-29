-- Fixed-asset register and source-backed depreciation history. Book value and
-- accumulated depreciation are deliberately derived from depreciation_runs.
CREATE TABLE fixed_asset_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    name TEXT NOT NULL,
    asset_account_id INTEGER NOT NULL REFERENCES accounts(id),
    accumulated_depreciation_account_id INTEGER NOT NULL REFERENCES accounts(id),
    depreciation_expense_account_id INTEGER NOT NULL REFERENCES accounts(id),
    method TEXT NOT NULL
        CHECK (method IN ('straight_line', 'declining_balance')),
    effective_life_months INTEGER,
    annual_rate REAL,
    CHECK (
        (method = 'straight_line'
         AND effective_life_months IS NOT NULL AND effective_life_months > 0
         AND annual_rate IS NULL)
        OR
        (method = 'declining_balance'
         AND annual_rate IS NOT NULL AND annual_rate > 0 AND annual_rate <= 1
         AND effective_life_months IS NULL)
    ),
    UNIQUE (client_id, name)
);

CREATE TABLE fixed_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    fixed_asset_type_id INTEGER NOT NULL REFERENCES fixed_asset_types(id),
    description TEXT NOT NULL,
    acquisition_date DATE NOT NULL,
    cost_cents INTEGER NOT NULL CHECK (cost_cents >= 0),
    salvage_value_cents INTEGER NOT NULL DEFAULT 0
        CHECK (salvage_value_cents >= 0 AND salvage_value_cents <= cost_cents),
    in_service_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'registered'
        CHECK (status IN ('registered', 'disposed')),
    disposal_date DATE,
    disposal_proceeds_cents INTEGER,
    CHECK (
        (status = 'registered' AND disposal_date IS NULL
         AND disposal_proceeds_cents IS NULL)
        OR
        (status = 'disposed' AND disposal_date IS NOT NULL
         AND disposal_proceeds_cents IS NOT NULL
         AND disposal_proceeds_cents >= 0)
    )
);

CREATE TABLE depreciation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixed_asset_id INTEGER NOT NULL REFERENCES fixed_assets(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fixed_asset_id, period_end),
    CHECK (period_start <= period_end)
);

CREATE INDEX idx_fixed_asset_types_client ON fixed_asset_types(client_id);
CREATE INDEX idx_fixed_assets_client_status ON fixed_assets(client_id, status);
CREATE INDEX idx_depreciation_runs_asset ON depreciation_runs(fixed_asset_id);
