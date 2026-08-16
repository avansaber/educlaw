"""Part A — M119: educlaw_notification accepts what core writes, on every install.

The defect: `educlaw_base_schema.py` and core's `init_db.py` both declare
`educlaw_notification` with IF-NOT-EXISTS semantics, and the base's
`notification_type` CHECK omitted `'payment'` and `'housing_waitlist'` — the two
values core writes (`fees.py:905`, `housing.py:444`). Install a sub-vertical
before core and portal fee payments plus housing waitlisting failed at runtime.

Three claims are pinned here, and each was proven red-able before it went green:

  1. a FRESH base-first install now accepts both values (the base DDL fix —
     revert `educlaw_base_schema.py`'s widened CHECK and the first test is red);
  2. the two declarations AGREE on this table's constraints (the drift pin —
     the divergence that hid this defect cannot re-open silently while the
     one-owner restructure is pending);
  3. an EXISTING narrow install is repaired by migration 003 — rows verbatim,
     report-only writes nothing, idempotent, crash-resumable, and a table it
     cannot positively identify as narrow is left alone.

Self-contained on purpose: the educlaw module has no shared DB conftest, and
this file provisions exactly what each claim needs (the elimination-retirement
test's discipline — the fixture builds the PRE-fix shape, so "the defect no
longer exists in the tree" cannot be what makes the repair test pass).
"""
import hashlib
import importlib.util
import os
import sqlite3
import sys
import uuid

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_TESTS_DIR)                    # educlaw/educlaw/
_VERTICAL_DIR = os.path.dirname(_MODULE_DIR)                 # educlaw/
_SOURCE_DIR = os.path.dirname(_VERTICAL_DIR)                 # source/
_IN_TREE_LIB = os.path.join(_SOURCE_DIR, "erpclaw", "scripts",
                            "erpclaw-setup", "lib")
if _IN_TREE_LIB not in sys.path:
    sys.path.insert(0, _IN_TREE_LIB)

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.db import get_connection  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base = _load("m119_base_schema",
             os.path.join(_VERTICAL_DIR, "educlaw_base_schema.py"))
core = _load("m119_core_init", os.path.join(_MODULE_DIR, "init_db.py"))
mig = _load("m119_migration",
            os.path.join(_MODULE_DIR, "migrations",
                         "003_widen_notification_check.py"))

# The shipped-narrow variant a pre-fix install carries. Derived from the live
# DDL by removing exactly the two widened values, and ASSERTED to have worked —
# if the base DDL changes shape this plant fails loudly instead of testing air.
_NARROW_DDL = base.BASE_TABLES_DDL.replace(",'payment','housing_waitlist'", "")


def _company(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS company (id TEXT PRIMARY KEY, name TEXT, "
        "abbr TEXT)")
    cid = str(uuid.uuid4())
    conn.execute("INSERT INTO company VALUES (?, 'M119 School', 'MS')", (cid,))
    conn.commit()
    return cid


def _base_first_db(tmp_path, narrow):
    """A base-first install — the exact shape ensure_educlaw_base_tables serves."""
    db = str(tmp_path / f"base-{'narrow' if narrow else 'fixed'}-{uuid.uuid4().hex[:8]}.sqlite")
    conn = sqlite3.connect(db)
    cid = _company(conn)
    ddl = _NARROW_DDL if narrow else base.BASE_TABLES_DDL
    if narrow:
        assert "'payment'" not in ddl, "narrow plant failed — DDL shape moved"
    conn.executescript(ddl)
    conn.commit()
    return db, conn, cid


def _try_insert(conn, cid, value):
    try:
        conn.execute(
            "INSERT INTO educlaw_notification (id, recipient_type, "
            "recipient_id, notification_type, title, message, company_id) "
            "VALUES (?, 'guardian', 'g1', ?, 't', 'm', ?)",
            (str(uuid.uuid4()), value, cid))
        conn.commit()
        return "ok"
    except sqlite3.IntegrityError:
        conn.rollback()
        return "blocked"


def _schema_hash(db):
    sql = sqlite3.connect(db).execute(
        "SELECT group_concat(sql, '|') FROM sqlite_master ORDER BY name"
    ).fetchone()[0]
    return hashlib.sha256(sql.encode()).hexdigest()


def _rows(conn):
    return [tuple(r) for r in conn.execute(
        "SELECT id, notification_type, company_id FROM educlaw_notification "
        "ORDER BY id").fetchall()]


# ──────────────────────────────────────────────────────────────────────────────
# 1. Fresh installs are fixed at the declaration
# ──────────────────────────────────────────────────────────────────────────────

def test_fresh_base_first_install_accepts_what_core_writes(tmp_path):
    """The base DDL fix: install order no longer decides whether fee payments
    and housing waitlisting work. Red before the widening, green after."""
    _db, conn, cid = _base_first_db(tmp_path, narrow=False)
    assert _try_insert(conn, cid, "payment") == "ok"
    assert _try_insert(conn, cid, "housing_waitlist") == "ok"
    assert _try_insert(conn, cid, "not_a_real_type") == "blocked", \
        "the CHECK must still constrain — widening is not unconstraining"
    conn.close()


def test_base_and_core_agree_on_notification_constraints(tmp_path):
    """The drift pin: both declarations of this table produce the SAME CHECK
    bodies, foreign keys and uniques. This divergence hid M119; until the
    one-owner restructure lands, it stays pinned shut."""
    base_db, conn_b, _ = _base_first_db(tmp_path, narrow=False)
    conn_b.close()

    core_db = str(tmp_path / "corefirst.sqlite")
    conn_c = get_connection(core_db)
    _company(conn_c)
    conn_c.close()
    seam.provision(core.METADATA, core_db)

    described_base = seam.describe_constraints("educlaw_notification", base_db)
    described_core = seam.describe_constraints("educlaw_notification", core_db)
    assert described_base["checks"] == described_core["checks"], (
        "the two declarations of educlaw_notification disagree on CHECK "
        "bodies again — the exact drift that produced M119:\n"
        f"base: {described_base['checks']}\ncore: {described_core['checks']}")
    assert described_base["foreign_keys"] == described_core["foreign_keys"]
    assert described_base["uniques"] == described_core["uniques"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. Existing narrow installs are repaired by migration 003
# ──────────────────────────────────────────────────────────────────────────────

def test_migration_rebuilds_a_narrow_install_rows_verbatim(tmp_path):
    db, conn, cid = _base_first_db(tmp_path, narrow=True)

    # The defect, driven red first — on the planted pre-fix install the two
    # values core writes are refused.
    assert _try_insert(conn, cid, "payment") == "blocked"
    assert _try_insert(conn, cid, "housing_waitlist") == "blocked"
    assert _try_insert(conn, cid, "grade_posted") == "ok"
    assert _try_insert(conn, cid, "fee_due") == "ok"
    before = _rows(conn)
    conn.close()

    # Report-only states the rebuild and writes nothing.
    h = _schema_hash(db)
    r = mig.run_migration(db, report_only=True)
    assert r["would_rebuild"] and r["rows"] == 2
    assert _schema_hash(db) == h, "report-only changed the schema"

    # The real run: rebuilt, rows verbatim, canonical indexes present.
    r = mig.run_migration(db)
    assert r["rebuilt"] and r["rows"] == 2

    conn = get_connection(db)
    assert _rows(conn) == before, "rows not carried verbatim"
    assert sorted(seam.index_names("educlaw_notification", db)) == [
        "idx_notification_company_type", "idx_notification_created",
        "idx_notification_recipient"]
    assert not seam.table_exists("educlaw_notification_m119_aside", db)

    # Green now — and still constrained.
    assert _try_insert(conn, cid, "payment") == "ok"
    assert _try_insert(conn, cid, "housing_waitlist") == "ok"
    assert _try_insert(conn, cid, "not_a_real_type") == "blocked"
    conn.close()

    # Idempotent.
    r = mig.run_migration(db)
    assert not r["rebuilt"] and r["reason"] == "already wide"


def test_migration_leaves_a_wide_install_alone(tmp_path):
    """A core-first install (the correct CHECK) is a no-op, byte-identical."""
    db = str(tmp_path / "corefirst.sqlite")
    conn = get_connection(db)
    _company(conn)
    conn.close()
    seam.provision(core.METADATA, db)

    h = _schema_hash(db)
    r = mig.run_migration(db)
    assert not r["rebuilt"] and r["reason"] == "already wide"
    assert _schema_hash(db) == h


def test_migration_declines_a_table_it_cannot_identify(tmp_path):
    """No narrow CHECK positively identified -> reported, untouched. An
    unconstrained table already accepts what core writes; constraining an
    operator's existing rows is not this migration's licence."""
    db = str(tmp_path / "bare.sqlite")
    conn = get_connection(db)
    _company(conn)
    conn.execute(
        "CREATE TABLE educlaw_notification (id TEXT PRIMARY KEY, "
        "recipient_type TEXT, recipient_id TEXT, notification_type TEXT, "
        "title TEXT, message TEXT, reference_type TEXT, reference_id TEXT, "
        "is_read INTEGER, sent_via TEXT, sent_at TEXT, company_id TEXT, "
        "created_at TEXT, created_by TEXT)")
    conn.commit()
    conn.close()

    h = _schema_hash(db)
    r = mig.run_migration(db)
    assert not r["rebuilt"] and r["reason"] == "no narrow check"
    assert _schema_hash(db) == h


def test_migration_resumes_after_a_crash_between_phases(tmp_path):
    """The crash story, executed rather than narrated. Phase-1 crash: the aside
    table exists and the real one is gone -> the migration provisions and
    finishes. Phase-2 crash: both exist, the real one empty -> it copies and
    finishes. Both end with every row intact."""
    # phase-1 crash state
    db, conn, cid = _base_first_db(tmp_path, narrow=True)
    assert _try_insert(conn, cid, "fee_due") == "ok"
    assert _try_insert(conn, cid, "absence") == "ok"
    before = _rows(conn)
    conn.execute("ALTER TABLE educlaw_notification "
                 "RENAME TO educlaw_notification_m119_aside")
    conn.execute("DROP INDEX IF EXISTS idx_notification_recipient")
    conn.execute("DROP INDEX IF EXISTS idx_notification_company_type")
    conn.execute("DROP INDEX IF EXISTS idx_notification_created")
    conn.commit()
    conn.close()

    r = mig.run_migration(db)
    assert r["rebuilt"] and r["rows"] == 2
    conn = get_connection(db)
    assert _rows(conn) == before
    assert _try_insert(conn, cid, "payment") == "ok"
    conn.close()

    # phase-2 crash state: aside populated, real provisioned but empty
    db2, conn2, cid2 = _base_first_db(tmp_path, narrow=True)
    assert _try_insert(conn2, cid2, "emergency") == "ok"
    before2 = _rows(conn2)
    conn2.execute("ALTER TABLE educlaw_notification "
                  "RENAME TO educlaw_notification_m119_aside")
    conn2.execute("DROP INDEX IF EXISTS idx_notification_recipient")
    conn2.execute("DROP INDEX IF EXISTS idx_notification_company_type")
    conn2.execute("DROP INDEX IF EXISTS idx_notification_created")
    conn2.commit()
    conn2.close()
    seam.provision(mig._core_notification_metadata(), db2)

    r = mig.run_migration(db2)
    assert r["rebuilt"] and r["rows"] == 1
    conn2 = get_connection(db2)
    assert _rows(conn2) == before2
    conn2.close()

    # report-only on a resume state names it and writes nothing
    db3, conn3, cid3 = _base_first_db(tmp_path, narrow=True)
    conn3.execute("ALTER TABLE educlaw_notification "
                  "RENAME TO educlaw_notification_m119_aside")
    conn3.commit()
    conn3.close()
    h = _schema_hash(db3)
    r = mig.run_migration(db3, report_only=True)
    assert r.get("resume") and r["report_only"]
    assert _schema_hash(db3) == h
