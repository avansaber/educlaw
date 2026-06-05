"""L1 pytest tests for EduClaw LMS Integration — 25 actions across 4 domains.

Tests: lms_sync (~8), assignments (~4), online_gradebook (~4),
       course_materials (~4) = ~20 tests.
"""
import importlib.util
import pytest
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    """Load a Python module by explicit file path (avoids sys.path collisions)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
get_conn = _helpers.get_conn
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_section = _helpers.seed_section

LMS_ACTIONS = _load("lms_sync", _SCRIPTS_DIR).ACTIONS
ASSIGN_ACTIONS = _load("assignments", _SCRIPTS_DIR).ACTIONS
GRADE_ACTIONS = _load("online_gradebook", _SCRIPTS_DIR).ACTIONS
MAT_ACTIONS = _load("course_materials", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yield conn, cid
    conn.close()


@pytest.fixture
def full_setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    sid = seed_student(conn, cid)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    sec_id = seed_section(conn, cid)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "year_id": yid, "term_id": tid, "section_id": sec_id,
    }
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# LMS SYNC domain
# ══════════════════════════════════════════════════════════════════════════════

class TestLmsConnection:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
            company_id=cid, lms_type="canvas",
            display_name="Canvas Test",
            endpoint_url="https://canvas.test.edu/api/v1",
            client_id="test-client", client_secret="test-secret",
            site_token=None, google_credentials=None,
            grade_direction="lms_to_sis",
            has_dpa_signed=1, dpa_signed_date="2025-01-01",
            is_coppa_verified=0, coppa_cert_url=None,
            allowed_data_fields='["name","email"]',
            default_course_prefix="CRS",
            auto_push_assignments=0,
            auto_sync_enabled=None, sync_frequency_hours=None,
            connection_status=None, user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(LMS_ACTIONS["lms-list-lms-connections"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_get(self, setup):
        conn, cid = setup
        add_r = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
            company_id=cid, lms_type="moodle",
            display_name="Moodle Test",
            endpoint_url="https://moodle.test.edu",
            client_id="moodle-client", client_secret="moodle-secret",
            site_token=None, google_credentials=None,
            grade_direction="lms_to_sis",
            has_dpa_signed=1, dpa_signed_date="2025-01-01",
            is_coppa_verified=0, coppa_cert_url=None,
            allowed_data_fields='[]',
            default_course_prefix=None,
            auto_push_assignments=0,
            auto_sync_enabled=None, sync_frequency_hours=None,
            connection_status=None, user_id="admin",
        ))
        assert is_ok(add_r)
        r = call_action(LMS_ACTIONS["lms-get-lms-connection"], conn, ns(
            connection_id=add_r["id"], company_id=cid,
        ))
        assert is_ok(r)

    def test_missing_type(self, setup):
        conn, cid = setup
        r = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
            company_id=cid, lms_type=None,
            display_name="Test", endpoint_url=None,
            client_id=None, client_secret=None,
            site_token=None, google_credentials=None,
            grade_direction=None, has_dpa_signed=0,
            dpa_signed_date=None, is_coppa_verified=0,
            coppa_cert_url=None, allowed_data_fields=None,
            default_course_prefix=None, auto_push_assignments=0,
            auto_sync_enabled=None, sync_frequency_hours=None,
            connection_status=None, user_id=None,
        ))
        assert is_error(r)


class TestSyncLog:
    def test_list(self, setup):
        conn, cid = setup
        add_r = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
            company_id=cid, lms_type="canvas",
            display_name="Sync Log Test",
            endpoint_url="https://canvas.test.edu/api/v1",
            client_id="test-client", client_secret="test-secret",
            site_token=None, google_credentials=None,
            grade_direction="lms_to_sis",
            has_dpa_signed=1, dpa_signed_date="2025-01-01",
            is_coppa_verified=0, coppa_cert_url=None,
            allowed_data_fields='[]',
            default_course_prefix=None,
            auto_push_assignments=0,
            auto_sync_enabled=None, sync_frequency_hours=None,
            connection_status=None, user_id="admin",
        ))
        assert is_ok(add_r)
        r = call_action(LMS_ACTIONS["lms-list-sync-logs"], conn, ns(
            connection_id=add_r["id"],
            sync_type=None, sync_status=None,
            from_date=None, to_date=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# ASSIGNMENTS domain
# ══════════════════════════════════════════════════════════════════════════════

def _create_connection(conn, cid):
    """Helper to create an LMS connection for tests that need one."""
    return call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
        company_id=cid, lms_type="canvas",
        display_name="Test Connection",
        endpoint_url="https://canvas.test.edu/api/v1",
        client_id="test-client", client_secret="test-secret",
        site_token=None, google_credentials=None,
        grade_direction="lms_to_sis",
        has_dpa_signed=1, dpa_signed_date="2025-01-01",
        is_coppa_verified=0, coppa_cert_url=None,
        allowed_data_fields='[]',
        default_course_prefix=None,
        auto_push_assignments=0,
        auto_sync_enabled=None, sync_frequency_hours=None,
        connection_status=None, user_id="admin",
    ))


class TestLmsAssignments:
    def test_list(self, full_setup):
        s = full_setup
        lms_conn = _create_connection(s["conn"], s["company_id"])
        assert is_ok(lms_conn)
        r = call_action(ASSIGN_ACTIONS["lms-list-lms-assignments"], s["conn"], ns(
            company_id=s["company_id"], section_id=None,
            connection_id=lms_conn["id"], assignment_sync_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# ONLINE GRADEBOOK domain
# ══════════════════════════════════════════════════════════════════════════════

class TestGradeConflicts:
    def test_list(self, full_setup):
        s = full_setup
        lms_conn = _create_connection(s["conn"], s["company_id"])
        assert is_ok(lms_conn)
        r = call_action(GRADE_ACTIONS["lms-list-grade-conflicts"], s["conn"], ns(
            company_id=s["company_id"], section_id=None,
            connection_id=lms_conn["id"],
            conflict_type=None, conflict_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# COURSE MATERIALS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestCourseMaterials:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(MAT_ACTIONS["lms-add-course-material"], s["conn"], ns(
            company_id=s["company_id"], section_id=s["section_id"],
            name="Syllabus", description="Course syllabus",
            material_type="syllabus", access_type="url",
            external_url="https://example.edu/syllabus.pdf", file_path=None,
            lms_connection_id=None, is_visible_to_students=1,
            available_from=None, available_until=None,
            sort_order=1, user_id="instructor",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(MAT_ACTIONS["lms-list-course-materials"], s["conn"], ns(
            company_id=s["company_id"], section_id=s["section_id"],
            material_type=None, include_archived=False,
            is_visible_to_students=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# Audit / FERPA-log silencer fix (A11) — dialect-agnostic, surfaces real failures
# ══════════════════════════════════════════════════════════════════════════════
#
# These tests guard the fix that replaced `except Exception: pass` around the
# FERPA data-access log and audit() writes with dialect-agnostic handling:
#   - a missing table (minimal install) is tolerated silently,
#   - any OTHER database error is surfaced on stderr (never silently swallowed),
#   - non-database errors propagate normally.
# Regression target: a broken FERPA/audit trail must never fail silently again.

import sqlite3 as _sqlite3

# The FERPA helper lives at module scope; load the module to reach it.
_GRADEBOOK_MOD = _load("online_gradebook", _SCRIPTS_DIR)
_log_ferpa_access = _GRADEBOOK_MOD._log_ferpa_access


class TestAuditFerpaSilencerFix:
    def test_db_error_types_sqlite_shape(self):
        """Under the default (sqlite) dialect, db_error_types() returns the
        sqlite3 missing-table + base error classes — not hardcoded anywhere."""
        from erpclaw_lib.db import db_error_types
        missing_table, db_error = db_error_types()
        assert _sqlite3.OperationalError in missing_table
        assert db_error is _sqlite3.Error
        # missing-table class must subclass the base, so except-ordering holds
        assert issubclass(missing_table[0], db_error)

    def test_ferpa_log_writes_row(self, db_path):
        """Happy path: the ported insert_row() write lands a real row."""
        conn = get_conn(db_path)
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        _log_ferpa_access(conn, sid, cid, "unit-test grade access", "tester")
        conn.commit()
        row = conn.execute(
            "SELECT student_id, data_category, access_type, access_reason, created_by "
            "FROM educlaw_data_access_log WHERE student_id = ?", (sid,)
        ).fetchone()
        assert row is not None
        assert row["student_id"] == sid
        assert row["data_category"] == "grades"
        assert row["access_type"] == "api"
        assert row["access_reason"] == "unit-test grade access"
        conn.close()

    def test_ferpa_log_tolerates_missing_table(self, db_path):
        """Minimal install (table absent) is tolerated silently — no raise."""
        conn = get_conn(db_path)
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        conn.execute("DROP TABLE educlaw_data_access_log")
        conn.commit()
        # Must NOT raise even though the table is gone.
        _log_ferpa_access(conn, sid, cid, "reason", "tester")
        conn.close()

    def test_ferpa_log_surfaces_other_db_error(self, db_path, capsys):
        """A real DB error (FK violation here) is surfaced on stderr, NOT
        silently swallowed and NOT raised into the caller's main operation."""
        conn = get_conn(db_path)
        cid = seed_company(conn)
        bogus_student = "does-not-exist-" + cid[:8]  # FK to educlaw_student fails
        # Must not raise (logging never aborts the main op)...
        _log_ferpa_access(conn, bogus_student, cid, "reason", "tester")
        # ...but the failure must be visible, not silent.
        assert "WARN" in capsys.readouterr().err
        # And nothing was written.
        cnt = conn.execute(
            "SELECT COUNT(*) FROM educlaw_data_access_log WHERE student_id = ?",
            (bogus_student,)).fetchone()[0]
        assert cnt == 0
        conn.close()

    def test_audit_safe_writes_row(self, db_path):
        """audit_safe() happy path writes to audit_log."""
        from erpclaw_lib.audit import audit_safe
        conn = get_conn(db_path)
        cid = seed_company(conn)
        audit_safe(conn, "lms-educlaw-lms", "unit-test-action", "company", cid,
                   new_values={"k": "v"})
        conn.commit()
        row = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log WHERE entity_id = ?",
            (cid,)).fetchone()
        assert row is not None
        assert row["action"] == "unit-test-action"
        assert row["entity_type"] == "company"
        conn.close()

    def test_audit_safe_tolerates_missing_table(self, db_path):
        """audit_safe() tolerates a missing audit_log table without raising."""
        from erpclaw_lib.audit import audit_safe
        conn = get_conn(db_path)
        cid = seed_company(conn)
        conn.execute("DROP TABLE audit_log")
        conn.commit()
        audit_safe(conn, "lms-educlaw-lms", "unit-test-action", "company", cid)
        conn.close()
