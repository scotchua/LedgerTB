-- Rebuild the fixed-asset graph with foreign keys enabled, preserving IDs.
-- The old inline asset/period UNIQUE constraint cannot be dropped in place.
CREATE TABLE fixed_asset_types_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    name TEXT NOT NULL,
    asset_account_id INTEGER NOT NULL REFERENCES accounts(id),
    accumulated_depreciation_account_id INTEGER NOT NULL REFERENCES accounts(id),
    depreciation_expense_account_id INTEGER NOT NULL REFERENCES accounts(id),
    method TEXT NOT NULL
        CHECK (method IN ('straight_line', 'declining_balance', 'units_of_production')),
    effective_life_months INTEGER,
    annual_rate REAL,
    convention TEXT NOT NULL DEFAULT 'full_month'
        CHECK (convention IN ('full_month', 'mid_month', 'half_year')),
    total_units INTEGER CHECK (total_units IS NULL OR
        (typeof(total_units) = 'integer' AND total_units > 0)),
    CHECK (
        (method = 'straight_line'
         AND effective_life_months IS NOT NULL AND effective_life_months > 0
         AND annual_rate IS NULL AND total_units IS NULL)
        OR
        (method = 'declining_balance'
         AND annual_rate IS NOT NULL AND annual_rate > 0 AND annual_rate <= 1
         AND effective_life_months IS NULL AND total_units IS NULL)
        OR
        (method = 'units_of_production' AND total_units IS NOT NULL
         AND annual_rate IS NULL AND effective_life_months IS NULL)
    ),
    CHECK (method != 'straight_line' OR convention != 'half_year'
           OR effective_life_months % 12 = 0),
    UNIQUE (client_id, name)
);

CREATE TABLE fixed_assets_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    fixed_asset_type_id INTEGER NOT NULL REFERENCES fixed_asset_types_new(id),
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

CREATE TABLE depreciation_runs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixed_asset_id INTEGER NOT NULL REFERENCES fixed_assets_new(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_seq INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(run_seq) = 'integer' AND run_seq >= 0),
    superseded_by INTEGER REFERENCES depreciation_runs_new(id),
    units_produced INTEGER CHECK (units_produced IS NULL OR
        (typeof(units_produced) = 'integer' AND units_produced > 0)),
    CHECK (superseded_by IS NULL OR superseded_by != id),
    CHECK (period_start <= period_end)
);

CREATE TABLE depreciation_draft_links_new (
    draft_entry_id INTEGER PRIMARY KEY REFERENCES draft_entries(id),
    fixed_asset_id INTEGER NOT NULL REFERENCES fixed_assets_new(id),
    period_end DATE NOT NULL,
    method TEXT NOT NULL
        CHECK (method IN ('straight_line', 'declining_balance', 'units_of_production')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    run_seq INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(run_seq) = 'integer' AND run_seq >= 0),
    units_produced INTEGER CHECK (units_produced IS NULL OR
        (typeof(units_produced) = 'integer' AND units_produced > 0))
);

INSERT INTO fixed_asset_types_new
    (id, client_id, name, asset_account_id, accumulated_depreciation_account_id,
     depreciation_expense_account_id, method, effective_life_months, annual_rate)
SELECT id, client_id, name, asset_account_id, accumulated_depreciation_account_id,
       depreciation_expense_account_id, method, effective_life_months, annual_rate
FROM fixed_asset_types;
INSERT INTO fixed_assets_new SELECT * FROM fixed_assets;
INSERT INTO depreciation_runs_new
    (id, fixed_asset_id, period_start, period_end, amount_cents,
     journal_entry_id, created_at, run_seq)
SELECT id, fixed_asset_id, period_start, period_end, amount_cents,
       journal_entry_id, created_at, 0 FROM depreciation_runs;
INSERT INTO depreciation_draft_links_new
    (draft_entry_id, fixed_asset_id, period_end, method, amount_cents, run_seq)
SELECT draft_entry_id, fixed_asset_id, period_end, method, amount_cents, 0
FROM depreciation_draft_links;

UPDATE sqlite_sequence SET seq = MAX(seq, COALESCE(
    (SELECT seq FROM sqlite_sequence WHERE name = 'fixed_asset_types'), 0))
WHERE name = 'fixed_asset_types_new';
UPDATE sqlite_sequence SET seq = MAX(seq, COALESCE(
    (SELECT seq FROM sqlite_sequence WHERE name = 'fixed_assets'), 0))
WHERE name = 'fixed_assets_new';
UPDATE sqlite_sequence SET seq = MAX(seq, COALESCE(
    (SELECT seq FROM sqlite_sequence WHERE name = 'depreciation_runs'), 0))
WHERE name = 'depreciation_runs_new';

DROP TABLE depreciation_draft_links;
DROP TABLE depreciation_runs;
DROP TABLE fixed_assets;
DROP TABLE fixed_asset_types;
ALTER TABLE fixed_asset_types_new RENAME TO fixed_asset_types;
ALTER TABLE fixed_assets_new RENAME TO fixed_assets;
ALTER TABLE depreciation_runs_new RENAME TO depreciation_runs;
ALTER TABLE depreciation_draft_links_new RENAME TO depreciation_draft_links;

CREATE INDEX idx_fixed_asset_types_client ON fixed_asset_types(client_id);
CREATE INDEX idx_fixed_assets_client_status ON fixed_assets(client_id, status);
CREATE INDEX idx_depreciation_runs_asset ON depreciation_runs(fixed_asset_id);
CREATE UNIQUE INDEX uq_depreciation_runs_asset_period
    ON depreciation_runs(fixed_asset_id, period_end, run_seq);
