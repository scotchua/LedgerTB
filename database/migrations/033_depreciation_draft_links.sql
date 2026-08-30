CREATE UNIQUE INDEX IF NOT EXISTS uq_depreciation_runs_asset_period
    ON depreciation_runs(fixed_asset_id, period_end);

CREATE TABLE depreciation_draft_links (
    draft_entry_id INTEGER PRIMARY KEY REFERENCES draft_entries(id),
    fixed_asset_id INTEGER NOT NULL REFERENCES fixed_assets(id),
    period_end DATE NOT NULL,
    method TEXT NOT NULL
        CHECK (method IN ('straight_line', 'declining_balance')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0)
);
