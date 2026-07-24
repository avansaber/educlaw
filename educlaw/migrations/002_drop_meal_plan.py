"""EduClaw migration 002: drop the dead educlaw_meal_plan table (WS4/D5, M33b §5).

`educlaw_meal_plan` was a write-only surface: `edu-add-meal-plan` wrote rows that
NOTHING ever read — `edu-usda-claim-report` computes reimbursements from a hardcoded
federal-rate constant (`cafeteria.py` USDA_RATES), never from this table. The M33b
dossier ratified DROP over consume. The action + table + index are removed from the
module for fresh installs (init_db.py); this migration drops the table (and its
index, which SQLite/Postgres remove with the table) from EXISTING educlaw DBs so
fresh == migrated.

Second per-module educlaw migration — applied by module_manager via the foundation
migration runner (P1), recorded under `educlaw` in the shared ledger. Idempotent
(DROP TABLE IF EXISTS), dialect-aware. Forward-only: the table was never read, so
there is no downstream data to preserve. Sibling to the foundation dead-orphan drop
batches (migrations 013/028), ADR-0028 clause 4 (dead-surface-only drops keep
rollback-foundation's file-only rollback safe). No inbound FKs reference this table
(SIM-verified), so drop order is immaterial.
"""
import argparse
import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")

_DROP_TABLE = "educlaw_meal_plan"
_DROP_INDEX = "idx_educlaw_meal_plan_school"


def _get_dialect():
    return os.environ.get("ERPCLAW_DB_DIALECT", "sqlite")


def _run_sqlite(path):
    conn = sqlite3.connect(path)
    try:
        from erpclaw_lib.db import setup_pragmas
        setup_pragmas(conn)
    except ImportError:
        conn.execute("PRAGMA busy_timeout=5000")
    existed = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_DROP_TABLE,)).fetchone()
    conn.execute(f"DROP INDEX IF EXISTS {_DROP_INDEX}")
    conn.execute(f"DROP TABLE IF EXISTS {_DROP_TABLE}")
    conn.commit()
    conn.close()
    print(f"  dropped: {_DROP_TABLE if existed else '(none — already absent)'}")


def _run_postgres(url):
    import psycopg2
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP INDEX IF EXISTS {_DROP_INDEX}")
            cur.execute(f"DROP TABLE IF EXISTS {_DROP_TABLE}")
        conn.commit()
        print(f"  Postgres: {_DROP_TABLE} dropped (if present).")
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
    parser = argparse.ArgumentParser(description="EduClaw migration 002: drop educlaw_meal_plan")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    run_migration(args.db_path)
    print("EduClaw migration 002 complete.")
