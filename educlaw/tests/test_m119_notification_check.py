"""Educlaw notification accepts what core writes, on every install.

The narrow `notification_type` CHECK once rejected `'payment'` and
`'housing_waitlist'` — the two values core writes (`fees.py:905`,
`housing.py:444`). Fresh installs are fixed at the single declaration in
`educlaw_base_schema.py`; existing narrow installs are repaired by migration
003, which renames the live table aside, provisions the base declaration,
copies every row verbatim and drops the aside copy.

Claims pinned here:

  1. the planted narrow variant is positively identified as narrow;
  2. a fresh base-first install accepts both values and still refuses unknown
     values;
  3. the table has one owner (base owns it, core imports it);
  4. an existing narrow install is rebuilt rows-verbatim, report-only writes
     nothing, the rebuild matches a fresh base-first install, and a second run
     says already wide;
  5. a wide install is left alone;
  6. a table with no CHECK is reported and left alone;
  7. interrupted rebuilds resume with every row intact;
  8. a declaration-load failure writes nothing.

Self-contained: each test builds its own database under `tmp_path`. All
connections come from `erpclaw_lib.db.get_connection`, all catalog questions
go through `erpclaw_lib.seam`, all DDL goes through `seam.provision`. The
`company` table the tests need is provisioned through the seam from a minimal
owned declaration in this file.
"""
import importlib.util
import os
import sys
import uuid

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_TESTS_DIR)
_VERTICAL_DIR = os.path.dirname(_MODULE_DIR)
_SOURCE_DIR = os.path.dirname(_VERTICAL_DIR)
_IN_TREE_LIB = os.path.join(_SOURCE_DIR, "erpclaw", "scripts",
                            "erpclaw-setup", "lib")
if _IN_TREE_LIB not in sys.path:
    sys.path.insert(0, _IN_TREE_LIB)

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.db import get_connection  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load("m119_base_schema",
             os.path.join(_VERTICAL_DIR, "educlaw_base_schema.py"))
core = _load("m119_core_init", os.path.join(_MODULE_DIR, "init_db.py"))
mig = _load("m119_migration",
            os.path.join(_MODULE_DIR, "migrations",
                         "003_widen_notification_check.py"))

TABLE = "educlaw_notification"
ASIDE = "educlaw_notification_m119_aside"
CHECK_NAME = "ck_educlaw_notification_notification_type"
CANONICAL_INDEXES = [
    "idx_notification_company_type",
    "idx_notification_created",
    "idx_notification_recipient",
]
SUFFIX = ",'payment','housing_waitlist'"

# Fixed strings also executed by the migration itself.
_RENAME_ASIDE = ("ALTER TABLE educlaw_notification "
                 "RENAME TO educlaw_notification_m119_aside")
_DROP_INDEXES = (
    "DROP INDEX IF EXISTS idx_notification_recipient",
    "DROP INDEX IF EXISTS idx_notification_company_type",
    "DROP INDEX IF EXISTS idx_notification_created",
)


def _provision_company(db_path):
    owned = seam.MetaData()
    seam.Table(
        "company", owned,
        seam.Column("id", seam.Text, primary_key=True, nullable=True),
    )
    seam.provision(owned, db_path)


def _seed_company(db_path):
    _provision_company(db_path)
    cid = str(uuid.uuid4())
    conn = get_connection(db_path)
    try:
        conn.execute("INSERT INTO company (id) VALUES (?)", (cid,))
        conn.commit()
    finally:
        conn.close()
    return cid


def _try_insert(db_path, cid, value):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO educlaw_notification (id, recipient_type, "
            "recipient_id, notification_type, title, message, company_id) "
            "VALUES (?, 'guardian', 'g1', ?, 't', 'm', ?)",
            (str(uuid.uuid4()), value, cid))
        conn.commit()
        return "ok"
    except seam.error_types():
        try:
            conn.rollback()
        except Exception:
            pass
        return "blocked"
    finally:
        conn.close()


def _insert_row(db_path, cid, value):
    conn = get_connection(db_path)
    try:
        nid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO educlaw_notification (id, recipient_type, "
            "recipient_id, notification_type, title, message, company_id) "
            "VALUES (?, 'guardian', 'g1', ?, 't', 'm', ?)",
            (nid, value, cid))
        conn.commit()
        return nid
    finally:
        conn.close()


def _rows(db_path):
    conn = get_connection(db_path)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT id, notification_type, company_id FROM "
            "educlaw_notification ORDER BY id").fetchall()]
    finally:
        conn.close()


def _aside_rows(db_path):
    conn = get_connection(db_path)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT id, notification_type, company_id FROM "
            "educlaw_notification_m119_aside ORDER BY id").fetchall()]
    finally:
        conn.close()


def _state(db_path):
    return {
        "tables": seam.table_names(db_path),
        "table": seam.describe_table(TABLE, db_path),
        "constraints": seam.describe_constraints(TABLE, db_path),
        "rows": _rows(db_path),
    }


def _narrow_fresh():
    fresh = seam.MetaData()
    base.BASE_METADATA.tables["company"].to_metadata(fresh)
    base.NOTIFICATION.to_metadata(fresh)
    table = fresh.tables[TABLE]
    old = next(
        c for c in table.constraints
        if getattr(c, "name", None) == CHECK_NAME)
    original = str(old.sqltext)
    narrow = original.replace(SUFFIX, "")
    assert "'enrollment_confirmed'" in narrow
    assert "'payment'" not in narrow
    table.constraints.remove(old)
    table.append_constraint(seam.CheckConstraint(narrow, name=CHECK_NAME))
    return fresh, narrow, original


def _plant_narrow_db(tmp_path, name):
    db_path = str(tmp_path / (name + ".sqlite"))
    cid = _seed_company(db_path)
    fresh, narrow, _original = _narrow_fresh()
    seam.provision(fresh, db_path)
    return db_path, cid, narrow


def _base_first_db(tmp_path, name):
    db_path = str(tmp_path / (name + ".sqlite"))
    cid = _seed_company(db_path)
    base.ensure_educlaw_base_tables(db_path)
    return db_path, cid


def _provision_base_notification_direct(db_path):
    fresh = seam.MetaData()
    base.BASE_METADATA.tables["company"].to_metadata(fresh)
    base.NOTIFICATION.to_metadata(fresh)
    return seam.provision(fresh, db_path)


def _provision_bare_notification(db_path):
    owned = seam.MetaData()
    base.BASE_METADATA.tables["company"].to_metadata(owned)
    seam.Table(
        "educlaw_notification", owned,
        seam.Column("id", seam.Text, primary_key=True, nullable=True),
        seam.Column("recipient_type", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("recipient_id", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("notification_type", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("title", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("message", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("reference_type", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("reference_id", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("is_read", seam.Integer, nullable=False,
                    server_default=seam.text("0")),
        seam.Column("sent_via", seam.Text, nullable=False,
                    server_default=seam.text("'system'")),
        seam.Column("sent_at", seam.Text, nullable=False,
                    server_default=seam.text("''")),
        seam.Column("company_id", seam.Text,
                    seam.ForeignKey("company.id", ondelete="RESTRICT"),
                    nullable=False, server_default=seam.text("''")),
        seam.Column("created_at", seam.Text, nullable=False,
                    server_default=seam.text("CURRENT_TIMESTAMP")),
        seam.Column("created_by", seam.Text, nullable=False,
                    server_default=seam.text("''")),
    )
    return seam.provision(owned, db_path)


def _notification_checks(db_path):
    return [
        body for body in
        seam.describe_constraints(TABLE, db_path)["checks"]
        if "notification_type in" in body.lower()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Narrow plant
# ─────────────────────────────────────────────────────────────────────────────


def test_narrow_plant_reports_narrow(tmp_path):
    db_path, _cid, narrow = _plant_narrow_db(tmp_path, "narrow-plant")
    found = _notification_checks(db_path)
    assert len(found) == 1
    assert found[0] == narrow
    assert mig._check_variant(db_path) == "narrow"


# ─────────────────────────────────────────────────────────────────────────────
# Fresh install
# ─────────────────────────────────────────────────────────────────────────────


def test_fresh_base_first_install_accepts_what_core_writes(tmp_path):
    db_path, cid = _base_first_db(tmp_path, "fresh-wide")
    assert mig._check_variant(db_path) == "wide"
    assert _try_insert(db_path, cid, "payment") == "ok"
    assert _try_insert(db_path, cid, "housing_waitlist") == "ok"
    assert _try_insert(db_path, cid, "not_a_real_type") == "blocked"


# ─────────────────────────────────────────────────────────────────────────────
# One owner
# ─────────────────────────────────────────────────────────────────────────────


def test_notification_has_a_single_owner(tmp_path):
    assert TABLE not in core.METADATA.tables
    reference_names = sorted(
        name for name, table in core.METADATA.tables.items()
        if table.info.get("erpclaw_reference_only"))
    assert reference_names == [
        "account",
        "company",
        "customer",
        "department",
        "educlaw_fee_structure",
        "educlaw_guardian",
        "educlaw_instructor",
        "educlaw_student",
    ]
    owned = base.BASE_METADATA.tables[TABLE]
    assert not owned.info.get("erpclaw_reference_only")

    db_path = str(tmp_path / "core-full.sqlite")
    cid = _seed_company(db_path)
    core.create_educlaw_tables(db_path)
    assert seam.table_exists(TABLE, db_path)
    assert _try_insert(db_path, cid, "payment") == "ok"
    assert _try_insert(db_path, cid, "housing_waitlist") == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Migration on a narrow install
# ─────────────────────────────────────────────────────────────────────────────


def test_migration_rebuilds_a_narrow_install_rows_verbatim(tmp_path):
    db_path, cid, _narrow = _plant_narrow_db(tmp_path, "narrow-migrate")
    assert _try_insert(db_path, cid, "payment") == "blocked"
    assert _try_insert(db_path, cid, "housing_waitlist") == "blocked"

    first_id = _insert_row(db_path, cid, "grade_posted")
    second_id = _insert_row(db_path, cid, "fee_due")
    before = _rows(db_path)
    assert [r[0] for r in before] == sorted([first_id, second_id])
    assert sorted(r[1] for r in before) == ["fee_due", "grade_posted"]
    assert all(r[2] == cid for r in before)
    before_state = _state(db_path)

    result = mig.run_migration(db_path, report_only=True)
    assert result["would_rebuild"] is True
    assert result["rows"] == 2
    assert _state(db_path) == before_state

    result = mig.run_migration(db_path)
    assert result["rebuilt"] is True
    assert result["rows"] == 2
    assert _rows(db_path) == before
    assert sorted(seam.index_names(TABLE, db_path)) == CANONICAL_INDEXES
    assert not seam.table_exists(ASIDE, db_path)

    fresh_db, _fresh_cid = _base_first_db(tmp_path, "fresh-compare")
    assert (seam.describe_constraints(TABLE, db_path)
            == seam.describe_constraints(TABLE, fresh_db))

    assert _try_insert(db_path, cid, "payment") == "ok"
    assert _try_insert(db_path, cid, "housing_waitlist") == "ok"
    assert _try_insert(db_path, cid, "not_a_real_type") == "blocked"

    result = mig.run_migration(db_path)
    assert result["rebuilt"] is False
    assert result["reason"] == "already wide"


def test_migration_leaves_a_wide_install_alone(tmp_path):
    db_path, _cid = _base_first_db(tmp_path, "wide-alone")
    before = _state(db_path)
    result = mig.run_migration(db_path)
    assert result["rebuilt"] is False
    assert result["reason"] == "already wide"
    assert _state(db_path) == before


def test_migration_declines_a_table_it_cannot_identify(tmp_path):
    db_path = str(tmp_path / "bare.sqlite")
    cid = _seed_company(db_path)
    _provision_bare_notification(db_path)
    first_id = _insert_row(db_path, cid, "anything_goes")
    before = _state(db_path)
    assert mig._check_variant(db_path) == "missing"

    result = mig.run_migration(db_path)
    assert result["rebuilt"] is False
    assert result["reason"] == "no narrow check"
    assert _state(db_path) == before
    assert [r[0] for r in _rows(db_path)] == [first_id]


# ─────────────────────────────────────────────────────────────────────────────
# Crash resume
# ─────────────────────────────────────────────────────────────────────────────


def test_migration_resumes_phase1_crash_state(tmp_path):
    db_path, cid, _narrow = _plant_narrow_db(tmp_path, "phase1")
    first_id = _insert_row(db_path, cid, "fee_due")
    second_id = _insert_row(db_path, cid, "absence")
    before = _rows(db_path)

    conn = get_connection(db_path)
    try:
        conn.execute(_RENAME_ASIDE)
        for stmt in _DROP_INDEXES:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    assert seam.table_exists(ASIDE, db_path)
    assert not seam.table_exists(TABLE, db_path)

    result = mig.run_migration(db_path)
    assert result["rebuilt"] is True
    assert result["rows"] == 2
    assert _rows(db_path) == before
    assert [r[0] for r in _rows(db_path)] == sorted([first_id, second_id])
    assert not seam.table_exists(ASIDE, db_path)
    assert _try_insert(db_path, cid, "payment") == "ok"


def test_migration_resumes_phase2_crash_state(tmp_path):
    db_path, cid, _narrow = _plant_narrow_db(tmp_path, "phase2")
    only_id = _insert_row(db_path, cid, "emergency")
    before = _rows(db_path)

    conn = get_connection(db_path)
    try:
        conn.execute(_RENAME_ASIDE)
        for stmt in _DROP_INDEXES:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    _provision_base_notification_direct(db_path)
    assert seam.table_exists(ASIDE, db_path)
    assert seam.table_exists(TABLE, db_path)
    assert _rows(db_path) == []
    assert _aside_rows(db_path) == before

    result = mig.run_migration(db_path)
    assert result["rebuilt"] is True
    assert result["rows"] == 1
    assert _rows(db_path) == before
    assert [r[0] for r in _rows(db_path)] == [only_id]
    assert not seam.table_exists(ASIDE, db_path)


def test_report_only_on_resume_state_names_resume_and_writes_nothing(tmp_path):
    db_path, cid, _narrow = _plant_narrow_db(tmp_path, "resume-report")
    _insert_row(db_path, cid, "fee_due")
    aside_before = None
    conn = get_connection(db_path)
    try:
        conn.execute(_RENAME_ASIDE)
        conn.commit()
    finally:
        conn.close()
    tables_before = seam.table_names(db_path)
    aside_before = _aside_rows(db_path)

    result = mig.run_migration(db_path, report_only=True)
    assert result.get("resume") is True
    assert result["report_only"] is True
    assert seam.table_names(db_path) == tables_before
    assert _aside_rows(db_path) == aside_before


# ─────────────────────────────────────────────────────────────────────────────
# Declaration-load failure writes nothing
# ─────────────────────────────────────────────────────────────────────────────


def test_declaration_load_failure_leaves_live_table_untouched(tmp_path, monkeypatch):
    db_path, cid, _narrow = _plant_narrow_db(tmp_path, "load-fail")
    first_id = _insert_row(db_path, cid, "grade_posted")
    second_id = _insert_row(db_path, cid, "fee_due")
    before = _rows(db_path)

    def _boom():
        raise RuntimeError("declaration unavailable")

    monkeypatch.setattr(mig, "_core_notification_metadata", _boom)
    with pytest.raises(RuntimeError):
        mig.run_migration(db_path)
    assert seam.table_exists(TABLE, db_path)
    assert not seam.table_exists(ASIDE, db_path)
    assert _rows(db_path) == before
    assert [r[0] for r in _rows(db_path)] == sorted([first_id, second_id])
    assert sorted(seam.index_names(TABLE, db_path)) == CANONICAL_INDEXES


def test_declaration_load_failure_leaves_aside_untouched(tmp_path, monkeypatch):
    db_path, cid, _narrow = _plant_narrow_db(tmp_path, "load-fail-resume")
    _insert_row(db_path, cid, "grade_posted")
    _insert_row(db_path, cid, "fee_due")
    before_aside = _rows(db_path)

    conn = get_connection(db_path)
    try:
        conn.execute(_RENAME_ASIDE)
        for stmt in _DROP_INDEXES:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    assert _aside_rows(db_path) == before_aside

    def _boom():
        raise RuntimeError("declaration unavailable")

    monkeypatch.setattr(mig, "_core_notification_metadata", _boom)
    with pytest.raises(RuntimeError):
        mig.run_migration(db_path)
    assert not seam.table_exists(TABLE, db_path)
    assert seam.table_exists(ASIDE, db_path)
    assert _aside_rows(db_path) == before_aside
