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
