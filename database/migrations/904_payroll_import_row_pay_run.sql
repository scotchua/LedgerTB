-- Accepted import rows need a direct link to their draft pay run so discarding
-- that run can return the source rows to review instead of stranding them.
ALTER TABLE payroll_import_rows
    ADD COLUMN pay_run_id INTEGER REFERENCES pay_runs(id);

UPDATE payroll_import_rows
SET pay_run_id = (
    SELECT json_extract(a.new_values, '$.pay_run_id')
    FROM audit_log a
    JOIN pay_runs p
        ON p.id = json_extract(a.new_values, '$.pay_run_id')
    WHERE a.table_name = 'payroll_import_rows'
      AND a.action = 'UPDATE'
      AND a.record_id = payroll_import_rows.id
      AND json_extract(a.new_values, '$.pay_run_id') IS NOT NULL
    ORDER BY a.id DESC
    LIMIT 1
)
WHERE status = 'accepted'
  AND pay_run_id IS NULL
  AND EXISTS (
      SELECT 1
      FROM audit_log a
      JOIN pay_runs p
          ON p.id = json_extract(a.new_values, '$.pay_run_id')
      WHERE a.table_name = 'payroll_import_rows'
        AND a.action = 'UPDATE'
        AND a.record_id = payroll_import_rows.id
        AND json_extract(a.new_values, '$.pay_run_id') IS NOT NULL
  );
