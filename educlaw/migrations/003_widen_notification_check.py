"""EduClaw migration 003: widen educlaw_notification's CHECK to what core writes (M119).

`educlaw_base_schema.py` and educlaw core's `init_db.py` both declare
`educlaw_notification`, and their CHECK bodies disagreed: the base omitted
`'payment'` and `'housing_waitlist'`, and core WRITES both (`fees.py:905`,
`housing.py:444`). Both declarations create with IF NOT EXISTS, so whichever ran
first won. Install a sub-vertical before educlaw core — the exact case
`ensure_educlaw_base_tables` exists to serve — and portal fee payments plus
housing waitlisting fail at runtime with `CHECK constraint failed`, today, on
SQLite. Driven both ways before the fix (M119 row); pre-existing, ADR-0034
neither caused nor cured it.

The base declaration is widened for FRESH installs in the same commit as this
file. This migration repairs EXISTING installs that already carry the narrow
CHECK baked into the live table. SQLite cannot alter a CHECK in place — the
dodge that left this behind is named in migration 001's own docstring — so the
repair is the standard rebuild: rename the live table aside, provision the
correct one, copy every row verbatim, drop the aside copy.

THE CORRECT DDL IS NOT WRITTEN HERE. The rebuilt table is provisioned from
core's OWN `init_db.NOTIFICATION` declaration via `seam.provision`, because a
third hand-written copy of this table is the exact drift class that produced
the defect. What this migration believes about the table is a load of
`../init_db.py`, never a string of its own.

WHO CAN NEED IT. Only an install where educlaw core is present runs an educlaw
core migration, and only core writes the two blocked values. A PostgreSQL
install cannot carry the narrow CHECK at all — `educlaw_base_schema.py` is
SQLite-only (`executescript`), so on PostgreSQL core's declaration always ran
first. The detection is dialect-portable anyway; on a correct install of either
dialect this migration prints and does nothing.

DETECTION IS POSITIVE, BOTH WAYS. The rebuild fires only when the
`notification_type` CHECK is positively identified as the narrow variant
(`'enrollment_confirmed'` present, `'payment'` absent). A table with the wide
CHECK — or one with NO `notification_type` CHECK at all — is reported and left
alone: an unconstrained table already accepts what core writes, and adding a
constraint over an operator's existing rows could refuse values this migration
never audited.

NOTHING A ROW HELD IS DIFFERENT AFTERWARDS. Every column of every row is copied
verbatim (the M102 "verbatim copy into a rebuilt table" case), the copy is
COUNTED against the source before the aside table is dropped, and a count
mismatch raises with the aside table left in place — the operator's rows are
never the thing this migration risks. Every value the narrow CHECK accepted is
a member of the wide set, so the copy cannot be refused by the rebuilt table.

CRASH SAFETY, stated the way 036 states it: three phases, not one, because
`seam.provision` opens its own engine and cannot join this connection's
transaction.

  phase 1 — rename aside + drop the table's three indexes, one transaction;
  phase 2 — provision the correct table + indexes from core's declaration;
  phase 3 — copy rows + drop the aside table, one transaction.

A crash between phases leaves the aside table present, and the migration is
RESUMABLE: on entry, an existing aside table routes execution to whichever
phase is still owed (real table absent -> resume at phase 2; real table present
and empty with aside rows -> resume at phase 3). Re-running after success finds
the wide CHECK and no aside table, and says so.

`--report-only` writes nothing at all — not even a rolled-back rename, which
would still take the table lock (migration 031's rule) — and states the CHECK
variant found, the row count, and exactly what the real run would do.

Authored through the seam (ADR-0034): `erpclaw_lib.db.get_connection` for the
connection, `erpclaw_lib.seam` for every catalog question, `seam.provision`
for the DDL. Every statement is a FIXED string (migration 031's rule) — the
three index names are enumerated because base and core declare the same three.

SIM: planning/simlogs/m119_SIM_2026-08-13.md
Plan home: planning/pending_items.md row M119.

Usage:
    python3 003_widen_notification_check.py [--db-path PATH] [--report-only]
"""
import argparse
import importlib.util
import os
import sys

# M102: a verbatim copy of every row into a rebuilt table — nothing a row held
# before this run is different afterwards. The only schema delta is the CHECK
# body, and the wide set is a superset of the narrow one, so no existing value
# changes acceptance status retroactively either.
MIGRATION_DATA_CLASS = "none"

MIGRATION_DATA_EXEMPTIONS = {
    ("INSERT", "educlaw_notification"): (
        "the rebuild copy: every column of every row, verbatim, from the "
        "renamed aside table into the freshly provisioned one — the M102 "
        "'verbatim copy into a rebuilt table' case, counted before the aside "
        "table is dropped."),
    ("DROP", "educlaw_notification_m119_aside"): (
        "the aside copy of the live table, dropped only after the verbatim "
        "copy is counted equal; it exists only inside this migration's "
        "rebuild and holds nothing the rebuilt table does not."),
}

# Deployed-lib bootstrap, guarded: production has nothing pre-imported so this
# resolves the installed lib, while a caller that already bound a tree (tests,
# the module runner inside a worktree) keeps its binding (ADR-0034 step 2d).
if importlib.util.find_spec("erpclaw_lib") is None:  # pragma: no cover - env-dependent
    sys.path.insert(0, os.path.join(
        os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.db import get_connection  # noqa: E402
from erpclaw_lib.paths import db_default  # noqa: E402

DEFAULT_DB_PATH = db_default()

TABLE = "educlaw_notification"
ASIDE = "educlaw_notification_m119_aside"

# Base and core declare the SAME three index names for this table, so the drop
# set is closed and each statement stays a fixed string.
_INDEXES = (
    "idx_notification_recipient",
    "idx_notification_company_type",
    "idx_notification_created",
)

# Every statement is a LITERAL, never composed: the M102 gate reads table names
# statically, and a name it cannot read forces a '<dynamic>' exemption that
# blankets the whole file — the exact width the convention exists to refuse.
# The column list is spelled out so the copy is order-safe on a table whose
# column ORDER may differ between a base-created and a core-created install.
_RENAME_ASIDE = ("ALTER TABLE educlaw_notification "
                 "RENAME TO educlaw_notification_m119_aside")
_DROP_INDEXES = (
    "DROP INDEX IF EXISTS idx_notification_recipient",
    "DROP INDEX IF EXISTS idx_notification_company_type",
    "DROP INDEX IF EXISTS idx_notification_created",
)
_COPY_ROWS = (
    "INSERT INTO educlaw_notification "
    "(id, recipient_type, recipient_id, notification_type, title, message, "
    "reference_type, reference_id, is_read, sent_via, sent_at, company_id, "
    "created_at, created_by) "
    "SELECT id, recipient_type, recipient_id, notification_type, title, "
    "message, reference_type, reference_id, is_read, sent_via, sent_at, "
    "company_id, created_at, created_by "
    "FROM educlaw_notification_m119_aside")
_COUNT_ASIDE = "SELECT COUNT(*) FROM educlaw_notification_m119_aside"
_COUNT_REAL = "SELECT COUNT(*) FROM educlaw_notification"
_DROP_ASIDE = "DROP TABLE educlaw_notification_m119_aside"


def _core_notification_metadata():
    """Core's own declaration of this table, loaded — never re-written here.

    Copies `educlaw_notification` (with its indexes) and the reference-only
    `company` declaration (so the foreign key resolves) into a fresh MetaData
    that `seam.provision` can act on. `provision` skips reference-only tables,
    and `company` always exists on a live install regardless.
    """
    init_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "init_db.py")
    spec = importlib.util.spec_from_file_location("educlaw_init_db_m119",
                                                  init_db_path)
    init_db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_db)

    sa = seam._sqlalchemy()
    fresh = sa.MetaData()
    init_db.METADATA.tables["company"].to_metadata(fresh)
    init_db.NOTIFICATION.to_metadata(fresh)
    return fresh


def _check_variant(db_path):
    """'wide' | 'narrow' | 'missing' — positively identified, never guessed."""
    for body in seam.describe_constraints(TABLE, db_path)["checks"]:
        if "notification_type in" in body.lower():
            if "'payment'" in body and "'housing_waitlist'" in body:
                return "wide"
            if "'enrollment_confirmed'" in body and "'payment'" not in body:
                return "narrow"
            return "missing"  # some third variant: report, do not touch
    return "missing"


def run_migration(db_path=None, report_only=False):
    path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)

    aside_present = seam.table_exists(ASIDE, path)
    real_present = seam.table_exists(TABLE, path)

    if not real_present and not aside_present:
        print(f"  {TABLE} absent on this install. Nothing to do.")
        return {"rebuilt": False, "reason": "table absent",
                "report_only": report_only}

    conn = get_connection(path)
    try:
        # ── resume routes (a prior run crashed between phases) ───────────────
        if aside_present:
            aside_rows = conn.execute(_COUNT_ASIDE).fetchone()[0]
            if report_only:
                print(f"  RESUME state: {ASIDE} present ({aside_rows} rows), "
                      f"{TABLE} {'present' if real_present else 'absent'} — the "
                      f"real run would finish the interrupted rebuild.")
                return {"rebuilt": False, "resume": True,
                        "report_only": True}
            if not real_present:
                print(f"  resuming interrupted rebuild at phase 2 "
                      f"({aside_rows} rows preserved in {ASIDE}).")
                seam.provision(_core_notification_metadata(), path)
            else:
                print(f"  resuming interrupted rebuild at phase 3 "
                      f"({aside_rows} rows preserved in {ASIDE}).")
            return _copy_and_drop(conn, aside_rows)

        # ── the normal path ──────────────────────────────────────────────────
        variant = _check_variant(path)
        rows = conn.execute(_COUNT_REAL).fetchone()[0]

        if variant == "wide":
            print(f"  {TABLE}: notification_type CHECK already accepts "
                  f"'payment' and 'housing_waitlist'. Nothing to do.")
            return {"rebuilt": False, "reason": "already wide",
                    "report_only": report_only}
        if variant == "missing":
            print(f"  {TABLE}: no narrow notification_type CHECK identified — "
                  f"left untouched. An unconstrained table already accepts "
                  f"what core writes, and adding a CHECK over {rows} existing "
                  f"row(s) is not this migration's licence.")
            return {"rebuilt": False, "reason": "no narrow check",
                    "report_only": report_only}

        print(f"  {TABLE}: NARROW CHECK found (rejects 'payment' and "
              f"'housing_waitlist' — the values core writes). {rows} row(s) "
              f"to carry through a rebuild.")
        if report_only:
            print(f"  report-only: the real run would rename {TABLE} aside, "
                  f"provision core's declaration, copy all {rows} row(s) "
                  f"verbatim, and drop the aside copy. Nothing written.")
            return {"rebuilt": False, "would_rebuild": True, "rows": rows,
                    "report_only": True}

        # phase 1 — one transaction: the live table steps aside.
        conn.execute(_RENAME_ASIDE)
        for stmt in _DROP_INDEXES:
            conn.execute(stmt)
        conn.commit()

        # phase 2 — core's declaration provisions the correct table + indexes.
        created = seam.provision(_core_notification_metadata(), path)
        print(f"  provisioned from core's init_db declaration: "
              f"{created['tables']} table, {created['indexes']} indexes.")

        # phase 3 — one transaction: verbatim copy, counted, then the aside
        # copy goes.
        return _copy_and_drop(conn, rows)
    finally:
        conn.close()


def _copy_and_drop(conn, expected_rows):
    conn.execute(_COPY_ROWS)
    copied = conn.execute(_COUNT_REAL).fetchone()[0]
    if copied != expected_rows:
        conn.rollback()
        raise RuntimeError(
            f"rebuild copy count mismatch: {ASIDE} holds {expected_rows} "
            f"row(s) but {TABLE} holds {copied} after the copy. Rolled back; "
            f"the aside table is left in place and no data was lost.")
    conn.execute(_DROP_ASIDE)
    conn.commit()
    print(f"  {copied} row(s) carried verbatim; {ASIDE} dropped. "
          f"'payment' and 'housing_waitlist' notifications now store.")
    return {"rebuilt": True, "rows": copied, "report_only": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migration 003: widen educlaw_notification's CHECK to "
                    "what core writes (M119)")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--report-only", action="store_true",
                        help="State what the real run would do; write nothing.")
    args = parser.parse_args()
    run_migration(args.db_path, report_only=args.report_only)
    print("educlaw migration 003 "
          + ("report complete (no writes)." if args.report_only else "complete."))
