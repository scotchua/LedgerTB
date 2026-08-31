# Migrations

Applied in filename order (`sorted(glob("*.sql"))`), tracked in
`schema_migrations` by the **full filename stem**, not the numeric prefix. Each
file runs at most once. See `database/schema.py`.

## Fork-only migrations use the reserved 900+ band

`upstream` is charliebarmore/LedgerTB, the production reference. It owns the
low numbers and keeps climbing. This fork owns **900 and up**, so the two
sequences can never collide again.

**Adding a migration here: take the next free number at or above 900.**

Why this exists. Upstream reached `024` independently while this fork was at
`042`, and three numbers collided on completely unrelated schema changes:

| Number | Upstream | This fork (before the move) |
|---|---|---|
| 022 | `client_business_context` | `account_grouping` |
| 023 | `app_preferences` | `cash_flow_section` |
| 024 | `document_audits` | `document_audits` |

Fighting over three numbers would have solved nothing, because upstream's `025`
would then collide with `025_inventory`, and so on through the whole range. So
the fork's three colliding files moved to `900`, `901`, `902` (2026-08-31), and
everything new goes in that band.

Renaming a migration is only safe because **this fork has no client databases**
(confirmed by Scott, 2026-08-31). On a book that already applied a file, the
tracking row is keyed by the old filename, so a rename makes an applied
migration look pending and it re-runs. `_added_column_if_sole_statement` heals
exactly one case, a lone `ALTER TABLE ... ADD COLUMN`, and nothing else:
`902_document_audits` is multi-statement and would have crashed on
`CREATE TABLE`. This is not hypothetical. `account_grouping` shipped as
`020_account_grouping.sql`, was renamed to `022`, and crashed every launch with
"duplicate column name" until the healing case was added. That is the test at
`tests/test_schema_migrations.py::test_a_migration_renumbered_after_a_book_applied_it_heals_instead_of_crashing`.

**So: once this fork has real books, renumbering stops being free.** Take the
next number in the band and leave history alone.

`tests/test_schema_migrations.py` asserts the exact ordered list. That is the
guard; a new migration fails it until the list is updated deliberately.
