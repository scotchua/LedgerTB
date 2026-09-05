-- Cash flow section override: where this account's counterpart cash activity
-- presents when the statement-subtype default is wrong for this client (a
-- note receivable that is operating for a lender, a deposit that is
-- investing). NULL preserves the derived classification, which is what every
-- account does today, so an existing book reads exactly as it did.
--
-- Named cash_flow_section rather than cash_flow_class: books opened under a
-- pre-release fork experiment already carry an unused cash_flow_class column,
-- and adding a same-named column would refuse to open them.
ALTER TABLE accounts ADD COLUMN cash_flow_section TEXT
    CHECK (
        cash_flow_section IS NULL
        OR cash_flow_section IN ('operating', 'investing', 'financing')
    );
