-- Adds the configurable financial-statement legend to firm branding.
-- NULL or blank uses the default report legend.
ALTER TABLE firm_branding ADD COLUMN report_legend TEXT;
