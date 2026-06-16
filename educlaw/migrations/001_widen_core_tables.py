"""EduClaw migration 001: widen 6 core tables to match educlaw_base_schema (P6).

Audit P6 / Part F: educlaw/init_db.py defined 6 core tables with FEWER columns
than educlaw_base_schema.py (which the 6 educlaw sub-modules call). Both execute
with CREATE TABLE IF NOT EXISTS, so the column set was install-order-dependent.
init_db.py has been widened to match base_schema for fresh installs; this migration
adds the previously-missing columns to EXISTING educlaw DBs so fresh == migrated.

First real per-module migration — applied by module_manager via the foundation
migration runner (P1). Idempotent (checks column presence), dialect-aware. All
added columns are nullable-with-default, so the ALTER is safe on populated tables.
(CHECK constraints present on these columns in a fresh install are intentionally
omitted here — SQLite can't add a CHECK without a table rebuild, and the columns
are functional without it; the drift guard tracks column names, not CHECKs.)
"""
import argparse
import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")

# table -> [(column, "TYPE NOT NULL DEFAULT ..."), ...]  (the base-schema-only columns)
_WIDEN = {
    "educlaw_course": [
        ("code", "TEXT NOT NULL DEFAULT ''"),
        ("credits", "INTEGER NOT NULL DEFAULT 0"),
        ("department", "TEXT NOT NULL DEFAULT ''"),
        ("prerequisites", "TEXT NOT NULL DEFAULT ''"),
    ],
    "educlaw_course_enrollment": [
        ("grade", "TEXT NOT NULL DEFAULT ''"),
        ("grade_points", "TEXT NOT NULL DEFAULT ''"),
    ],
    "educlaw_instructor": [
        ("name", "TEXT NOT NULL DEFAULT ''"),
        ("email", "TEXT NOT NULL DEFAULT ''"),
        ("department", "TEXT NOT NULL DEFAULT ''"),
        ("rank", "TEXT NOT NULL DEFAULT ''"),
        ("tenure_status", "TEXT NOT NULL DEFAULT ''"),
        ("hire_date", "TEXT NOT NULL DEFAULT ''"),
    ],
    "educlaw_scholarship": [
        ("naming_series", "TEXT NOT NULL DEFAULT ''"),
        ("aid_year", "TEXT NOT NULL DEFAULT ''"),
        ("total_cost", "TEXT NOT NULL DEFAULT '0'"),
        ("efc", "TEXT NOT NULL DEFAULT '0'"),
        ("total_need", "TEXT NOT NULL DEFAULT '0'"),
        ("grants", "TEXT NOT NULL DEFAULT '0'"),
        ("scholarships", "TEXT NOT NULL DEFAULT '0'"),
        ("federal_aid", "TEXT NOT NULL DEFAULT '0'"),
        ("state_aid", "TEXT NOT NULL DEFAULT '0'"),
        ("institutional_aid", "TEXT NOT NULL DEFAULT '0'"),
        ("loans", "TEXT NOT NULL DEFAULT '0'"),
        ("work_study", "TEXT NOT NULL DEFAULT '0'"),
        ("total_aid", "TEXT NOT NULL DEFAULT '0'"),
        ("package_status", "TEXT NOT NULL DEFAULT ''"),
    ],
    "educlaw_section": [
        ("instructor", "TEXT NOT NULL DEFAULT ''"),
        ("term", "TEXT NOT NULL DEFAULT ''"),
        ("year", "INTEGER NOT NULL DEFAULT 0"),
        ("schedule", "TEXT NOT NULL DEFAULT ''"),
        ("location", "TEXT NOT NULL DEFAULT ''"),
        ("capacity", "INTEGER NOT NULL DEFAULT 0"),
        ("enrolled", "INTEGER NOT NULL DEFAULT 0"),
        ("section_status", "TEXT NOT NULL DEFAULT ''"),
    ],
    "educlaw_student": [
        ("name", "TEXT NOT NULL DEFAULT ''"),
        ("student_id", "TEXT NOT NULL DEFAULT ''"),
        ("program_id", "TEXT NOT NULL DEFAULT ''"),
        ("gpa", "TEXT NOT NULL DEFAULT ''"),
        ("total_credits", "INTEGER NOT NULL DEFAULT 0"),
        ("expected_graduation", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def _get_dialect():
    return os.environ.get("ERPCLAW_DB_DIALECT", "sqlite")


def _run_sqlite(path):
    conn = sqlite3.connect(path)
    try:
        from erpclaw_lib.db import setup_pragmas
        setup_pragmas(conn)
    except ImportError:
        conn.execute("PRAGMA busy_timeout=5000")
    added = 0
    for table, cols in _WIDEN.items():
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue  # educlaw core not installed on this DB
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, coldef in cols:
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
                added += 1
    conn.commit()
    conn.close()
    print(f"  widened educlaw core tables: {added} column(s) added.")


def _run_postgres(url):
    import psycopg2
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            for table, cols in _WIDEN.items():
                for col, coldef in cols:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coldef}")
        conn.commit()
        print("  Postgres: educlaw core tables widened (if present).")
    finally:
        conn.close()


def run_migration(db_path=None):
    if _get_dialect() == "postgresql":
        url = os.environ.get("ERPCLAW_DB_URL") or db_path
        if not url:
            print("Postgres dialect set but no connection URL (ERPCLAW_DB_URL). Nothing to migrate.")
            return
        _run_postgres(url)
        return
    path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)
    if not os.path.exists(path):
        print(f"Database not found at {path}. Nothing to migrate.")
        return
    _run_sqlite(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EduClaw migration 001: widen core tables")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    run_migration(args.db_path)
    print("EduClaw migration 001 complete.")
