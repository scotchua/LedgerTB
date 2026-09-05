import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_SINGLE_ADD_COLUMN = re.compile(
    r"^ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN\s+(\w+)\b", re.IGNORECASE | re.DOTALL
)


def _added_column_if_sole_statement(migration_sql: str):
    """The column name, if this migration is exactly one ALTER TABLE ADD
    COLUMN statement; otherwise None.

    A migration file can be renumbered (a later file collides with an
    upstream release, say) after a book has already applied it under the old
    filename: the column is really there, but the tracking row is keyed by
    filename and doesn't recognize it. Recognizing that narrow case lets the
    tracker heal instead of crashing, but only for a single ADD COLUMN
    statement -- a multi-statement migration could be partially applied in a
    way this can't distinguish from fully applied, so it is never eligible.
    """
    body = "\n".join(
        line for line in migration_sql.splitlines()
        if not line.strip().startswith("--")
    ).strip()
    if body.count(";") != 1 or not body.endswith(";"):
        return None
    match = _SINGLE_ADD_COLUMN.match(body)
    return match.group(1) if match else None


def _reconcile_document_audits(conn, migration_sql: str, version: str):
    """Record the 902 -> 045 rename only for the complete shipped schema.

    Compare stored DDL, including checks, foreign keys and every index, with
    the unchanged migration in an empty in-memory database. A tracking row
    alone cannot prove that this multi-statement migration finished.
    """
    def objects(connection):
        return [tuple(row) for row in connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = 'document_audits' ORDER BY type, name"
        )]

    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(migration_sql)
        expected = objects(reference)
    finally:
        reference.close()

    try:
        conn.execute("BEGIN IMMEDIATE")
        if objects(conn) != expected:
            raise RuntimeError(
                "Cannot reconcile 902_document_audits to 045_document_audits: "
                "the existing table and indexes do not match the shipped schema."
            )
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def create_tables(conn: sqlite3.Connection):
    """Bring the database schema up to date by applying any migrations in
    database/migrations/ that haven't run yet, in filename order (numeric
    prefix). Each migration runs at most once, tracked in schema_migrations.
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    cursor.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in cursor.fetchall()}

    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration_path.stem
        if version in applied:
            continue

        migration_sql = migration_path.read_text().strip()
        if not migration_sql.endswith(";"):
            migration_sql += ";"
        if version == "045_document_audits" and "902_document_audits" in applied:
            _reconcile_document_audits(conn, migration_sql, version)
            continue
        # version is a filename stem (controlled), but quote-escape defensively.
        safe_version = version.replace("'", "''")

        # Run the migration's statements AND record its version inside a single
        # explicit transaction. Otherwise executescript() commits the DDL on its
        # own and a crash before the separate version-insert would leave the
        # migration applied-but-unrecorded -- re-running it on the next startup,
        # which is unsafe for any non-idempotent migration (e.g. ALTER TABLE).
        script = (
            "BEGIN;\n"
            f"{migration_sql}\n"
            f"INSERT INTO schema_migrations (version) VALUES ('{safe_version}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(script)
        except Exception as exc:
            conn.rollback()
            # Match on the message, not the exception type: the connection is
            # sqlcipher3's driver or the stdlib's depending on whether
            # SQLCipher is installed (see database/connection.py), and the
            # two modules' OperationalError classes are not related.
            added_column = _added_column_if_sole_statement(migration_sql)
            if (
                added_column
                and str(exc) == f"duplicate column name: {added_column}"
            ):
                # The column is already there from a run under this
                # migration's previous filename; only the tracking row is
                # missing. Record it and move on rather than crash on a
                # column that already exists correctly.
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )
                conn.commit()
                continue
            raise
