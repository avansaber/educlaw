"""EduClaw migration 004: add the educlaw_fee_invoice link table.

A fee invoice IS a sales invoice owned by the foundation, so educlaw keeps
only the link on its own side: which student, which structure (billed once),
which sales invoice, and — for a late fee — which overdue fee invoice it was
raised against. Fresh installs already carry the table because
``init_db.py`` declares it; this migration provisions it on installs that
predate the declaration.

THE DECLARATION IS NOT REPEATED HERE. The new table is copied from core's
OWN ``init_db.py`` declaration via ``to_metadata`` into a fresh MetaData,
with the three declarations it points at carried along so its references
resolve — the same load-by-file shape as migration 003, which copies the
shared base declaration instead of re-typing it. A second hand-typed copy
is the exact drift class migration 003 exists to repair.

WHO CAN NEED IT. Only an install where educlaw core is present runs an
educlaw core migration. The guard is the student table: where it is absent
the migration prints and does nothing, so a foundation-only database is
left untouched.

NOTHING ELSE IS TOUCHED. The provisioner creates only what is missing, so a
re-run creates nothing, and no existing row is read or rewritten.
"""
import argparse
import importlib.util
import os
import sys

# A new table only: nothing any row held before this run is different
# afterwards.
MIGRATION_DATA_CLASS = "none"

# Deployed-lib bootstrap, guarded: production has nothing pre-imported so this
# resolves the installed lib, while a caller that already bound a tree (tests,
# the module runner inside a worktree) keeps its binding (ADR-0034 step 2d).
if importlib.util.find_spec("erpclaw_lib") is None:  # pragma: no cover - env-dependent
    sys.path.insert(0, os.path.join(
        os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.paths import db_default  # noqa: E402

DEFAULT_DB_PATH = db_default()

TABLE = "educlaw_fee_invoice"


def _fee_invoice_metadata():
    """The link-table declaration, loaded — never re-typed here.

    Copies ``company``, ``educlaw_student``, ``educlaw_fee_structure`` and
    ``educlaw_fee_invoice`` from core's own ``init_db.py`` into a fresh
    MetaData that ``seam.provision`` can act on. The first three are
    reference-only declarations there, and stay reference-only in the copy,
    so the provisioner never creates another module's table; the link table
    is the only owned table in the fresh metadata and the only thing a run
    can create.
    """
    init_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "init_db.py")
    spec = importlib.util.spec_from_file_location("educlaw_init_db_004",
                                                  init_path)
    init_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_mod)

    sa = seam._sqlalchemy()
    fresh = sa.MetaData()
    init_mod.METADATA.tables["company"].to_metadata(fresh)
    init_mod.METADATA.tables["educlaw_student"].to_metadata(fresh)
    init_mod.METADATA.tables["educlaw_fee_structure"].to_metadata(fresh)
    init_mod.FEE_INVOICE.to_metadata(fresh)
    return fresh


def run_migration(db_path=None, report_only=False):
    path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)

    if not seam.table_exists("educlaw_student", path):
        print(f"  educlaw_student absent on this install. Nothing to do.")
        return {"provisioned": False, "reason": "educlaw core not installed",
                "tables": 0, "indexes": 0, "report_only": report_only}

    already = seam.table_exists(TABLE, path)
    if report_only:
        if already:
            print(f"  {TABLE} already present. Nothing to do.")
        else:
            print(f"  report-only: the real run would provision {TABLE} "
                  f"from the init_db.py declaration. Nothing written.")
        return {"provisioned": False, "already_present": already,
                "tables": 0, "indexes": 0, "report_only": True}

    metadata = _fee_invoice_metadata()
    created = seam.provision(metadata, path)
    print(f"  provisioned {TABLE} from the init_db.py declaration: "
          f"{created['tables']} table(s), {created['indexes']} index(es).")
    return {"provisioned": bool(created["tables"]),
            "already_present": already,
            "tables": created["tables"], "indexes": created["indexes"],
            "report_only": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migration 004: add the educlaw_fee_invoice link table")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--report-only", action="store_true",
                        help="State what the real run would do; write nothing.")
    args = parser.parse_args()
    run_migration(args.db_path, report_only=args.report_only)
    print("educlaw migration 004 "
          + ("report complete (no writes)." if args.report_only else "complete."))
