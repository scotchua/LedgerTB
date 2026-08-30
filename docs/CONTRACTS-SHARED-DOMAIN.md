# Shared Domain Contracts

Subledger rows that point to a source document use three nullable columns: `source_type`, `source_id`, and `source_line_id`. A partial unique index covers all three columns when `source_type` is not null. The line ID is required because one document can contain the same item more than once. Rows created without a source document leave all three columns null. Payment allocations are exempt: they remain first-class join tables with real foreign keys.

A voidable document has a status that includes `voided` and a nullable `voided_journal_entry_id` foreign key to the reversing journal entry. A document cannot be voided while it has payments or allocations outstanding, and trying to void an already voided document is an error. Idempotency is by refusal. A reversal posts through `JournalEntry.save`. Its entry date is the void date, not the original document date, when the original period is closed.

Any subledger-only row dated in a closed fiscal period must be rejected by its service before it is saved, even when no journal entry is involved. This includes inventory movements, staged imports, and payroll staging. Services use `FiscalPeriod.get_closed_period_for_date` for this check. `JournalEntry.save` already gates paths that post a journal entry.

Departments are the shared, module-neutral dimension. The `departments` table belongs to a client and requires department names to be unique within that client. Payroll uses it first; AR/AP and inventory may use the same table in later builds.
