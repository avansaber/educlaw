"""Behavioural depth tests for the 12 LMS actions previously covered by shape only.

Each action below already had a test asserting the response envelope (``is_ok``)
in ``test_lms.py``. Those tests stay untouched; the tests here prove what each
action actually does to the database: the exact row written (scores as exact
``TEXT`` strings built via ``Decimal``, never float), the rows that must NOT
have changed, and one input-validation refusal that must leave the database
byte-identical.

None of these 12 handlers reaches the general ledger: every one of them reads
or writes only ``educlaw_lms_*`` rows (writes also append one ``audit_log`` row
and, for grade/assignment pushes and pulls, FERPA rows in
``educlaw_data_access_log``) and never posts journals. Each success test says
so in a comment so a later reader does not add debit/credit assertions that
cannot hold.

Depth classification per action (stored row vs ledger effect):
  stored row : all 12 (lms-get-online-gradebook, lms-get-sync-log,
               lms-import-grades, lms-import-lms-assignments,
               lms-list-course-materials, lms-list-grade-conflicts,
               lms-list-lms-assignments, lms-list-lms-connections,
               lms-list-sync-logs, lms-submit-assessment-to-lms,
               lms-update-course-material, lms-update-lms-connection)
  ledger     : none — this module never posts journals.

No production file is touched by this file. Where a live LMS API would be
needed (grade/assignment pull/push over HTTP), a stub adapter is injected via
``unittest.mock`` so the test observes the database effect offline; the
oneroster_csv push path needs no stub at all.
"""
import importlib.util
import json
import os
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error

LMS_ACTIONS = _load("lms_sync", _SCRIPTS_DIR).ACTIONS
ASSIGN_MOD = _load("assignments", _SCRIPTS_DIR)
ASSIGN_ACTIONS = ASSIGN_MOD.ACTIONS
GRADE_MOD = _load("online_gradebook", _SCRIPTS_DIR)
GRADE_ACTIONS = GRADE_MOD.ACTIONS
MAT_ACTIONS = _load("course_materials", _SCRIPTS_DIR).ACTIONS


# ---------------------------------------------------------------------------
# Setup helpers (base tables are owned by educlaw core; direct INSERT is the
# only setup path — production code never does this, tests must).
# ---------------------------------------------------------------------------

def _seed_grading_scale(conn, company_id):
    gsid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_grading_scale (id, name, description, is_default,"
        " company_id, created_by) VALUES (?, ?, 'Standard scale', 1, ?, '')",
        (gsid, f"Standard {gsid[:4]}", company_id))
    conn.commit()
    return gsid


def _seed_plan(conn, section_id, company_id, grading_scale_id):
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment_plan (id, section_id, grading_scale_id,"
        " company_id, created_by) VALUES (?, ?, ?, ?, '')",
        (pid, section_id, grading_scale_id, company_id))
    conn.commit()
    return pid


def _seed_category(conn, plan_id, name="Exams"):
    cid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment_category (id, assessment_plan_id, name,"
        " weight_percentage, sort_order, created_by)"
        " VALUES (?, ?, ?, '100', 1, '')",
        (cid, plan_id, name))
    conn.commit()
    return cid


def _seed_assessment(conn, plan_id, category_id, name="Midterm Exam",
                     max_points="100.00", is_published=1):
    aid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment (id, assessment_plan_id, category_id,"
        " name, description, max_points, due_date, is_published,"
        " allows_extra_credit, sort_order, created_by)"
        " VALUES (?, ?, ?, ?, '', ?, '2025-10-15', ?, 0, 1, '')",
        (aid, plan_id, category_id, name, str(Decimal(max_points)), is_published))
    conn.commit()
    return aid


def _seed_enrollment(conn, student_id, section_id, company_id):
    eid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_course_enrollment (id, student_id, section_id,"
        " enrollment_date, enrollment_status, company_id, created_by)"
        " VALUES (?, ?, ?, '2025-08-25', 'enrolled', ?, '')",
        (eid, student_id, section_id, company_id))
    conn.commit()
    return eid


def _seed_result(conn, assessment_id, student_id, enrollment_id, points):
    rid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment_result (id, assessment_id, student_id,"
        " course_enrollment_id, points_earned, is_exempt, is_late, comments,"
        " graded_by, graded_at, created_by)"
        " VALUES (?, ?, ?, ?, ?, 0, 0, '', 'instructor',"
        " '2025-10-16T10:00:00Z', '')",
        (rid, assessment_id, student_id, enrollment_id, str(Decimal(points))))
    conn.commit()
    return rid


def _seed_course_mapping(conn, lms_connection_id, section_id,
                         lms_course_id="LMS_COURSE_1"):
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_lms_course_mapping (id, lms_connection_id,"
        " section_id, lms_course_id, lms_course_url, lms_term_id, sync_status,"
        " created_by) VALUES (?, ?, ?, ?, 'https://lms.test.edu/c/1',"
        " 'LMS_TERM_1', 'synced', '')",
        (mid, lms_connection_id, section_id, lms_course_id))
    conn.commit()
    return mid


def _seed_user_mapping(conn, lms_connection_id, student_id, lms_user_id):
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_lms_user_mapping (id, lms_connection_id,"
        " sis_user_type, sis_user_id, lms_user_id, lms_username,"
        " lms_login_email, sync_status, created_by)"
        " VALUES (?, ?, 'student', ?, ?, ?, ?, 'synced', '')",
        (mid, lms_connection_id, student_id, lms_user_id,
         f"user_{lms_user_id}", f"{lms_user_id}@test.edu"))
    conn.commit()
    return mid


def _seed_assignment_mapping(conn, lms_connection_id, assessment_id,
                             lms_assignment_id, direction="sis_to_lms"):
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_lms_assignment_mapping (id, lms_connection_id,"
        " assessment_id, lms_assignment_id, lms_assignment_url,"
        " lms_grade_scheme, push_direction, is_published_in_lms, sync_status,"
        " created_by) VALUES (?, ?, ?, ?, 'https://lms.test.edu/a/1',"
        " 'points', ?, 1, 'synced', '')",
        (mid, lms_connection_id, assessment_id, lms_assignment_id, direction))
    conn.commit()
    return mid


def _add_connection(conn, company_id, lms_type="canvas",
                    display_name="Depth Connection",
                    grade_direction="lms_to_sis", has_dpa_signed=1):
    r = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
        company_id=company_id, lms_type=lms_type,
        display_name=display_name,
        endpoint_url="https://canvas.test.edu/api/v1" if lms_type != "oneroster_csv" else "",
        client_id="depth-client", client_secret="depth-secret",
        site_token=None, google_credentials=None,
        grade_direction=grade_direction,
        has_dpa_signed=has_dpa_signed, dpa_signed_date="2025-01-01",
        is_coppa_verified=0, coppa_cert_url=None,
        allowed_data_fields='[]',
        default_course_prefix=None,
        auto_push_assignments=0,
        auto_sync_enabled=None, sync_frequency_hours=None,
        connection_status=None, user_id="admin",
    ))
    assert is_ok(r), r
    return r["id"]


def _add_material(conn, company_id, section_id, name="Syllabus",
                  material_type="syllabus", sort_order=1):
    r = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
        company_id=company_id, section_id=section_id,
        name=name, description=f"{name} description",
        material_type=material_type, access_type="url",
        external_url="https://example.edu/syllabus.pdf", file_path=None,
        lms_connection_id=None, is_visible_to_students=1,
        available_from=None, available_until=None,
        sort_order=sort_order, user_id="instructor",
    ))
    assert is_ok(r), r
    return r["id"]


@pytest.fixture
def env(db_path):
    conn = _helpers.get_conn(db_path)
    cid = _helpers.seed_company(conn)
    sid = _helpers.seed_student(conn, cid)
    yid = _helpers.seed_academic_year(conn, cid)
    tid = _helpers.seed_academic_term(conn, cid, yid)
    sec = _helpers.seed_section(conn, cid)
    gs = _seed_grading_scale(conn, cid)
    plan = _seed_plan(conn, sec, cid, gs)
    cat = _seed_category(conn, plan)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "year_id": yid, "term_id": tid, "section_id": sec,
        "grading_scale_id": gs, "plan_id": plan, "category_id": cat,
    }
    conn.close()


_SNAPSHOT_TABLES = (
    "educlaw_lms_connection",
    "educlaw_lms_sync_log",
    "educlaw_lms_course_mapping",
    "educlaw_lms_user_mapping",
    "educlaw_lms_assignment_mapping",
    "educlaw_lms_grade_sync",
    "educlaw_lms_course_material",
    "educlaw_assessment_plan",
    "educlaw_assessment_category",
    "educlaw_assessment",
    "educlaw_course_enrollment",
    "educlaw_assessment_result",
    "educlaw_data_access_log",
    "naming_series",
    "audit_log",
)


def _snapshot(conn):
    snap = {}
    for table in _SNAPSHOT_TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        except Exception:
            continue
        snap[table] = sorted(
            json.dumps(dict(r), sort_keys=True, default=str) for r in rows)
    return snap


def _count(conn, table, where="", params=()):
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0]


class _FakeAssignmentAdapter:
    """Stub for pull_all_assignments — no HTTP, canned LMS payload."""

    def __init__(self, assignments):
        self._assignments = assignments

    def pull_all_assignments(self, lms_course_id, connection):
        return self._assignments


class _FakeGradeAdapter:
    """Stub for pull_grades — no HTTP, canned LMS payload."""

    def __init__(self, grades):
        self._grades = grades

    def pull_grades(self, lms_course_id, lms_assignment_id, connection):
        return self._grades


# ---------------------------------------------------------------------------
# lms-update-lms-connection — stored row
# ---------------------------------------------------------------------------

class TestUpdateLmsConnectionDepth:
    def test_updates_two_fields_and_leaves_the_rest_alone(self, env):
        s, conn = env, env["conn"]
        conn_id = _add_connection(conn, s["company_id"],
                                  display_name="Orig Display")
        before = conn.execute(
            "SELECT display_name, lms_type, endpoint_url, client_id,"
            " grade_direction, has_dpa_signed, status"
            " FROM educlaw_lms_connection WHERE id = ?", (conn_id,)).fetchone()
        assert tuple(before) == ("Orig Display", "canvas",
                                 "https://canvas.test.edu/api/v1",
                                 "depth-client", "lms_to_sis", 1, "draft")
        r = call_action(LMS_ACTIONS["lms-update-lms-connection"], conn, ns(
            connection_id=conn_id, display_name="Renamed Display",
            grade_direction="manual",
        ))
        assert is_ok(r), r
        assert r["id"] == conn_id
        after = conn.execute(
            "SELECT display_name, lms_type, endpoint_url, client_id,"
            " grade_direction, has_dpa_signed, status"
            " FROM educlaw_lms_connection WHERE id = ?", (conn_id,)).fetchone()
        assert tuple(after) == ("Renamed Display", "canvas",
                                "https://canvas.test.edu/api/v1",
                                "depth-client", "manual", 1, "draft")
        # No ledger legs: only the connection row (plus one audit_log row)
        # moves, never journals.

    def test_refuses_bad_grade_direction_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        conn_id = _add_connection(conn, s["company_id"],
                                  display_name="Orig Display")
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-update-lms-connection"], conn, ns(
            connection_id=conn_id, grade_direction="sideways",
        ))
        assert is_error(r)
        assert r["message"] == ("--grade-direction must be one of: lms_to_sis,"
                                " sis_to_lms, manual")
        assert _snapshot(conn) == before
        still = conn.execute(
            "SELECT display_name, grade_direction FROM educlaw_lms_connection"
            " WHERE id = ?", (conn_id,)).fetchone()
        assert tuple(still) == ("Orig Display", "lms_to_sis")


# ---------------------------------------------------------------------------
# lms-list-lms-connections — stored rows (read-only)
# ---------------------------------------------------------------------------

class TestListLmsConnectionsDepth:
    def test_lists_exactly_the_stored_connections(self, env):
        s, conn = env, env["conn"]
        _add_connection(conn, s["company_id"], lms_type="canvas",
                        display_name="Alpha Canvas")
        _add_connection(conn, s["company_id"], lms_type="moodle",
                        display_name="Beta Moodle")
        snap_before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-list-lms-connections"], conn, ns(
            company_id=s["company_id"], limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a list writes nothing
        assert r["total"] == 2
        by_name = {c["display_name"]: c for c in r["connections"]}
        assert set(by_name) == {"Alpha Canvas", "Beta Moodle"}
        assert (by_name["Alpha Canvas"]["lms_type"],
                by_name["Alpha Canvas"]["connection_status"],
                by_name["Alpha Canvas"]["has_dpa_signed"]) == ("canvas", "draft", 1)
        assert (by_name["Beta Moodle"]["lms_type"],
                by_name["Beta Moodle"]["connection_status"]) == ("moodle", "draft")
        # No ledger legs: a read returns stored rows, never journals.

    def test_refuses_missing_company_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _add_connection(conn, s["company_id"], display_name="Alpha Canvas")
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-list-lms-connections"], conn, ns(
            company_id=None, limit=50, offset=0,
        ))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-submit-assessment-to-lms — stored row (+ sync log row)
# ---------------------------------------------------------------------------

def _submit_setup(env, lms_type="oneroster_csv"):
    """Full stack for a push: connection, course mapping, assessment."""
    s, conn = env, env["conn"]
    conn_id = _add_connection(conn, s["company_id"], lms_type=lms_type,
                              display_name="Push Connection")
    _seed_course_mapping(conn, conn_id, s["section_id"],
                         lms_course_id="LMS_PUSH_C1")
    assess_id = _seed_assessment(conn, s["plan_id"], s["category_id"],
                                 name="Midterm Exam",
                                 max_points=str(Decimal("100.00")))
    return conn_id, assess_id


class TestSubmitAssessmentDepth:
    def test_push_writes_mapping_and_log_and_is_idempotent(self, env):
        s, conn = env, env["conn"]
        conn_id, assess_id = _submit_setup(env)
        other_id = _seed_assessment(conn, s["plan_id"], s["category_id"],
                                    name="Untouched Quiz",
                                    max_points=str(Decimal("10.00")))
        r = call_action(ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn, ns(
            assessment_id=assess_id, connection_id=conn_id, user_id="teacher",
        ))
        assert is_ok(r), r
        expected_lms_id = f"oneroster_assign_{assess_id[:8]}"
        assert r["lms_assignment_id"] == expected_lms_id
        row = conn.execute(
            "SELECT lms_connection_id, assessment_id, lms_assignment_id,"
            " push_direction, sync_status, lms_grade_scheme,"
            " is_published_in_lms"
            " FROM educlaw_lms_assignment_mapping WHERE id = ?",
            (r["id"],)).fetchone()
        assert tuple(row) == (conn_id, assess_id, expected_lms_id,
                              "sis_to_lms", "synced", "points", 1)
        log = conn.execute(
            "SELECT sync_type, status, section_id, lms_connection_id"
            " FROM educlaw_lms_sync_log WHERE id = ?",
            (r["sync_log_id"],)).fetchone()
        assert tuple(log) == ("assignment_push", "completed",
                              s["section_id"], conn_id)
        # The sibling assessment gained no mapping.
        assert _count(conn, "educlaw_lms_assignment_mapping",
                       "WHERE assessment_id = ?", (other_id,)) == 0
        # A second push is idempotent: same id, no new row.
        again = call_action(
            ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn, ns(
                assessment_id=assess_id, connection_id=conn_id,
                user_id="teacher",
            ))
        assert is_ok(again), again
        assert again["id"] == r["id"]
        assert _count(conn, "educlaw_lms_assignment_mapping",
                       "WHERE assessment_id = ?", (assess_id,)) == 1
        # No ledger legs: push writes mapping + sync-log (+ audit/FERPA)
        # rows only, never journals.

    def test_refuses_missing_assessment_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        conn_id, _ = _submit_setup(env)
        before = _snapshot(conn)
        r = call_action(ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn, ns(
            assessment_id=None, connection_id=conn_id, user_id="teacher",
        ))
        assert is_error(r)
        assert r["message"] == "--assessment-id is required"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_lms_assignment_mapping") == 0
        assert _count(conn, "educlaw_lms_sync_log") == 0


# ---------------------------------------------------------------------------
# lms-list-lms-assignments — stored rows (read-only)
# ---------------------------------------------------------------------------

class TestListLmsAssignmentsDepth:
    def test_lists_exactly_the_stored_mapping(self, env):
        s, conn = env, env["conn"]
        conn_id, assess_id = _submit_setup(env)
        pushed = call_action(ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn, ns(
            assessment_id=assess_id, connection_id=conn_id, user_id="teacher",
        ))
        assert is_ok(pushed), pushed
        snap_before = _snapshot(conn)
        r = call_action(ASSIGN_ACTIONS["lms-list-lms-assignments"], conn, ns(
            company_id=s["company_id"], section_id=None,
            connection_id=conn_id, assignment_sync_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a list writes nothing
        assert r["total"] == 1
        row = r["assignments"][0]
        assert row["assessment_id"] == assess_id
        assert row["lms_assignment_id"] == f"oneroster_assign_{assess_id[:8]}"
        assert row["push_direction"] == "sis_to_lms"
        assert row["assignment_sync_status"] == "synced"
        assert row["assessment_name"] == "Midterm Exam"
        # No ledger legs: a read returns stored rows, never journals.

    def test_refuses_missing_connection_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _submit_setup(env)
        before = _snapshot(conn)
        r = call_action(ASSIGN_ACTIONS["lms-list-lms-assignments"], conn, ns(
            company_id=s["company_id"], section_id=None,
            connection_id=None, assignment_sync_status=None,
            limit=50, offset=0,
        ))
        assert is_error(r)
        assert r["message"] == "--connection-id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-list-sync-logs — stored rows (read-only)
# ---------------------------------------------------------------------------

class TestListSyncLogsDepth:
    def test_lists_exactly_the_stored_log(self, env):
        s, conn = env, env["conn"]
        conn_id, assess_id = _submit_setup(env)
        pushed = call_action(ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn, ns(
            assessment_id=assess_id, connection_id=conn_id, user_id="teacher",
        ))
        assert is_ok(pushed), pushed
        snap_before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-list-sync-logs"], conn, ns(
            connection_id=conn_id,
            sync_type=None, sync_status=None,
            from_date=None, to_date=None,
            limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a list writes nothing
        assert r["total"] == 1
        row = r["sync_logs"][0]
        assert row["sync_type"] == "assignment_push"
        assert row["sync_status"] == "completed"
        assert row["section_id"] == s["section_id"]
        stored_conn = conn.execute(
            "SELECT lms_connection_id FROM educlaw_lms_sync_log WHERE id = ?",
            (row["id"],)).fetchone()[0]
        assert stored_conn == conn_id
        # No ledger legs: a read returns stored rows, never journals.

    def test_refuses_missing_connection_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _submit_setup(env)
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-list-sync-logs"], conn, ns(
            connection_id=None,
            sync_type=None, sync_status=None,
            from_date=None, to_date=None,
            limit=50, offset=0,
        ))
        assert is_error(r)
        assert r["message"] == "--connection-id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-get-sync-log — stored row (read-only)
# ---------------------------------------------------------------------------

class TestGetSyncLogDepth:
    def test_returns_exactly_the_stored_log(self, env):
        s, conn = env, env["conn"]
        conn_id, assess_id = _submit_setup(env)
        pushed = call_action(ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn, ns(
            assessment_id=assess_id, connection_id=conn_id, user_id="teacher",
        ))
        assert is_ok(pushed), pushed
        log_id = conn.execute(
            "SELECT id FROM educlaw_lms_sync_log WHERE lms_connection_id = ?",
            (conn_id,)).fetchone()[0]
        snap_before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-get-sync-log"], conn, ns(
            sync_log_id=log_id,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a get writes nothing
        assert r["id"] == log_id
        assert r["sync_type"] == "assignment_push"
        assert r["sync_status"] == "completed"
        assert r["section_id"] == s["section_id"]
        assert r["lms_connection_id"] == conn_id
        assert r["error_summary"] == []
        # No ledger legs: a read returns the stored row, never journals.

    def test_refuses_unknown_log_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _submit_setup(env)
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-get-sync-log"], conn, ns(
            sync_log_id="no-such-log",
        ))
        assert is_error(r)
        assert r["message"] == "Sync log no-such-log not found"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-import-lms-assignments — stored rows (staged LMS payload + SIS rows)
# ---------------------------------------------------------------------------

def _canned_lms_assignments():
    return [
        {"lms_assignment_id": "canvas_asg_101", "name": "Quiz 1",
         "max_points": str(Decimal("10.00")), "due_date": "2025-10-01",
         "lms_grade_scheme": "points", "is_published": 1,
         "lms_assignment_url": "https://canvas.test.edu/a/101"},
        {"lms_assignment_id": "canvas_asg_102", "name": "Quiz 2",
         "max_points": str(Decimal("20.00")), "due_date": "2025-10-08",
         "lms_grade_scheme": "points", "is_published": 0,
         "lms_assignment_url": "https://canvas.test.edu/a/102"},
    ]


class TestImportLmsAssignmentsDepth:
    def test_pull_creates_assessments_and_mappings_with_exact_scores(self, env):
        s, conn = env, env["conn"]
        conn_id = _add_connection(conn, s["company_id"], lms_type="canvas",
                                  display_name="Import Connection")
        _seed_course_mapping(conn, conn_id, s["section_id"],
                             lms_course_id="CANVAS_C9")
        pre_id = _seed_assessment(conn, s["plan_id"], s["category_id"],
                                  name="Pre-existing",
                                  max_points=str(Decimal("5.00")))
        fake = _FakeAssignmentAdapter(_canned_lms_assignments())
        with patch.object(ASSIGN_MOD, "_get_adapter", return_value=fake):
            r = call_action(
                ASSIGN_ACTIONS["lms-import-lms-assignments"], conn, ns(
                    connection_id=conn_id, section_id=s["section_id"],
                    create_assessments=True, plan_id=s["plan_id"],
                    category_id=s["category_id"], user_id="teacher",
                ))
        assert is_ok(r), r
        assert r["mappings_created"] == 2
        assert r["lms_assignments_found"] == 2
        created = conn.execute(
            "SELECT name, max_points FROM educlaw_assessment"
            " WHERE assessment_plan_id = ? AND id != ?"
            " ORDER BY name",
            (s["plan_id"], pre_id)).fetchall()
        assert [tuple(x) for x in created] == [
            ("Quiz 1", str(Decimal("10.00"))),
            ("Quiz 2", str(Decimal("20.00"))),
        ]
        maps = conn.execute(
            "SELECT lms_assignment_id, push_direction, sync_status"
            " FROM educlaw_lms_assignment_mapping"
            " WHERE lms_connection_id = ? ORDER BY lms_assignment_id",
            (conn_id,)).fetchall()
        assert [tuple(x) for x in maps] == [
            ("canvas_asg_101", "lms_to_sis", "synced"),
            ("canvas_asg_102", "lms_to_sis", "synced"),
        ]
        # Every mapping links to the assessment created for it.
        linked = conn.execute(
            "SELECT COUNT(*) FROM educlaw_lms_assignment_mapping am"
            " JOIN educlaw_assessment a ON a.id = am.assessment_id"
            " WHERE am.lms_connection_id = ?", (conn_id,)).fetchone()[0]
        assert linked == 2
        # The pre-existing assessment gained no mapping and is untouched.
        assert _count(conn, "educlaw_lms_assignment_mapping",
                       "WHERE assessment_id = ?", (pre_id,)) == 0
        kept = conn.execute(
            "SELECT name, max_points FROM educlaw_assessment WHERE id = ?",
            (pre_id,)).fetchone()
        assert tuple(kept) == ("Pre-existing", str(Decimal("5.00")))
        # No ledger legs: import stages LMS payload + SIS assessment rows
        # only, never journals.

    def test_refuses_missing_section_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        conn_id = _add_connection(conn, s["company_id"], lms_type="canvas",
                                  display_name="Import Connection")
        _seed_course_mapping(conn, conn_id, s["section_id"],
                             lms_course_id="CANVAS_C9")
        before = _snapshot(conn)
        fake = _FakeAssignmentAdapter(_canned_lms_assignments())
        with patch.object(ASSIGN_MOD, "_get_adapter", return_value=fake):
            r = call_action(
                ASSIGN_ACTIONS["lms-import-lms-assignments"], conn, ns(
                    connection_id=conn_id, section_id=None,
                    create_assessments=True, plan_id=s["plan_id"],
                    category_id=s["category_id"], user_id="teacher",
                ))
        assert is_error(r)
        assert r["message"] == "--section-id is required"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_assessment") == 0
        assert _count(conn, "educlaw_lms_assignment_mapping") == 0


# ---------------------------------------------------------------------------
# lms-import-grades — stored rows (grade_sync + auto-applied SIS result)
# ---------------------------------------------------------------------------

def _grade_import_setup(env):
    """Canvas stack for a grade pull: mapping, enrollment, user mapping."""
    s, conn = env, env["conn"]
    conn_id = _add_connection(conn, s["company_id"], lms_type="canvas",
                              display_name="Grade Connection")
    _seed_course_mapping(conn, conn_id, s["section_id"],
                         lms_course_id="CANVAS_C1")
    assess_id = _seed_assessment(conn, s["plan_id"], s["category_id"],
                                 name="Final Exam",
                                 max_points=str(Decimal("100.00")))
    _seed_assignment_mapping(conn, conn_id, assess_id, "canvas_a1")
    enr_id = _seed_enrollment(conn, s["student_id"], s["section_id"],
                              s["company_id"])
    _seed_user_mapping(conn, conn_id, s["student_id"], "canvas_u1")
    return conn_id, assess_id, enr_id


def _canned_grades(score):
    return [{"lms_user_id": "canvas_u1", "lms_score": str(Decimal(score)),
             "lms_grade": "B", "lms_submitted_at": "2025-10-02T10:00:00Z",
             "lms_graded_at": "2025-10-03T10:00:00Z",
             "is_late": 0, "is_missing": 0, "lms_comments": "good work"}]


class TestImportGradesDepth:
    def test_pull_applies_new_grade_with_exact_decimal_strings(self, env):
        s, conn = env, env["conn"]
        conn_id, assess_id, _ = _grade_import_setup(env)
        other_sid = _helpers.seed_student(conn, s["company_id"])
        _seed_enrollment(conn, other_sid, s["section_id"], s["company_id"])
        fake = _FakeGradeAdapter(_canned_grades("85.50"))
        with patch.object(GRADE_MOD, "_get_adapter", return_value=fake):
            r = call_action(GRADE_ACTIONS["lms-import-grades"], conn, ns(
                connection_id=conn_id, section_id=s["section_id"],
                assessment_id=None, academic_term_id=None, user_id="teacher",
            ))
        assert is_ok(r), r
        assert r["grades_pulled"] == 1
        assert r["grades_applied"] == 1
        assert r["conflicts_flagged"] == 0
        gs = conn.execute(
            "SELECT lms_assignment_id, lms_user_id, assessment_id, student_id,"
            " lms_score, sis_score, is_conflict, conflict_type, sync_status"
            " FROM educlaw_lms_grade_sync WHERE sync_log_id = ?",
            (r["sync_log_id"],)).fetchone()
        assert tuple(gs) == ("canvas_a1", "canvas_u1", assess_id,
                             s["student_id"], str(Decimal("85.50")), "",
                             0, "", "applied")
        res = conn.execute(
            "SELECT assessment_id, student_id, points_earned"
            " FROM educlaw_assessment_result"
            " WHERE assessment_id = ? AND student_id = ?",
            (assess_id, s["student_id"])).fetchone()
        assert tuple(res) == (assess_id, s["student_id"],
                              str(Decimal("85.50")))
        log = conn.execute(
            "SELECT sync_type, grades_pulled, grades_applied, conflicts_flagged"
            " FROM educlaw_lms_sync_log WHERE id = ?",
            (r["sync_log_id"],)).fetchone()
        assert tuple(log) == ("grade_pull", 1, 1, 0)
        # The unenrolled-in-LMS student gained no result row.
        assert _count(conn, "educlaw_assessment_result",
                       "WHERE student_id = ?", (other_sid,)) == 0
        # No ledger legs: pull stages grade_sync + SIS result rows only,
        # never journals.

    def test_refuses_missing_connection_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _grade_import_setup(env)
        before = _snapshot(conn)
        fake = _FakeGradeAdapter(_canned_grades("85.50"))
        with patch.object(GRADE_MOD, "_get_adapter", return_value=fake):
            r = call_action(GRADE_ACTIONS["lms-import-grades"], conn, ns(
                connection_id=None, section_id=s["section_id"],
                assessment_id=None, academic_term_id=None, user_id="teacher",
            ))
        assert is_error(r)
        assert r["message"] == "--connection-id is required"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_lms_grade_sync") == 0
        assert _count(conn, "educlaw_assessment_result") == 0
        assert _count(conn, "educlaw_lms_sync_log") == 0


# ---------------------------------------------------------------------------
# lms-get-online-gradebook — stored rows (read-only matrix)
# ---------------------------------------------------------------------------

class TestGetOnlineGradebookDepth:
    def test_matrix_shows_exact_sis_and_lms_scores(self, env):
        s, conn = env, env["conn"]
        conn_id, final_id, _ = _grade_import_setup(env)
        fake = _FakeGradeAdapter(_canned_grades("85.50"))
        with patch.object(GRADE_MOD, "_get_adapter", return_value=fake):
            pulled = call_action(GRADE_ACTIONS["lms-import-grades"], conn, ns(
                connection_id=conn_id, section_id=s["section_id"],
                assessment_id=None, academic_term_id=None, user_id="teacher",
            ))
        assert is_ok(pulled), pulled
        hw_id = _seed_assessment(conn, s["plan_id"], s["category_id"],
                                 name="Homework 1",
                                 max_points=str(Decimal("20.00")))
        hw_enr = conn.execute(
            "SELECT id FROM educlaw_course_enrollment WHERE student_id = ?"
            " AND section_id = ?", (s["student_id"], s["section_id"])).fetchone()[0]
        _seed_result(conn, hw_id, s["student_id"], hw_enr, "18.50")
        snap_before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-get-online-gradebook"], conn, ns(
            section_id=s["section_id"], connection_id=conn_id,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a get writes nothing
        assert r["assessment_count"] == 2
        assert r["student_count"] == 1
        cols = {c["assessment_id"]: c for c in r["assessments"]}
        assert cols[final_id]["has_lms_mapping"] is True
        assert cols[hw_id]["has_lms_mapping"] is False
        student_row = r["rows"][0]
        assert student_row["student_id"] == s["student_id"]
        assert student_row["student_name"] == "Student, Test"
        assert student_row["grades"][final_id]["sis_score"] == str(Decimal("85.50"))
        assert student_row["grades"][final_id]["lms_score"] == str(Decimal("85.50"))
        assert student_row["grades"][final_id]["is_conflict"] == 0
        assert student_row["grades"][hw_id]["sis_score"] == str(Decimal("18.50"))
        assert student_row["grades"][hw_id]["lms_score"] == ""
        # No ledger legs: a read returns the stored matrix, never journals.

    def test_refuses_missing_section_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        conn_id, _, _ = _grade_import_setup(env)
        before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-get-online-gradebook"], conn, ns(
            section_id=None, connection_id=conn_id,
        ))
        assert is_error(r)
        assert r["message"] == "--section-id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-list-grade-conflicts — stored rows (read-only)
# ---------------------------------------------------------------------------

class TestListGradeConflictsDepth:
    def test_conflict_lists_exact_mismatched_scores_and_keeps_sis(self, env):
        s, conn = env, env["conn"]
        conn_id, assess_id, enr_id = _grade_import_setup(env)
        _seed_result(conn, assess_id, s["student_id"], enr_id, "70.00")
        fake = _FakeGradeAdapter(_canned_grades("75.00"))
        with patch.object(GRADE_MOD, "_get_adapter", return_value=fake):
            pulled = call_action(GRADE_ACTIONS["lms-import-grades"], conn, ns(
                connection_id=conn_id, section_id=s["section_id"],
                assessment_id=None, academic_term_id=None, user_id="teacher",
            ))
        assert is_ok(pulled), pulled
        assert pulled["conflicts_flagged"] == 1
        assert pulled["grades_applied"] == 0
        stored = conn.execute(
            "SELECT lms_score, sis_score, is_conflict, conflict_type,"
            " sync_status FROM educlaw_lms_grade_sync"
            " WHERE sync_log_id = ?", (pulled["sync_log_id"],)).fetchone()
        assert tuple(stored) == (str(Decimal("75.00")), str(Decimal("70.00")),
                                 1, "score_mismatch", "conflict")
        # The SIS result was not overwritten by the conflicting pull.
        kept = conn.execute(
            "SELECT points_earned FROM educlaw_assessment_result"
            " WHERE assessment_id = ? AND student_id = ?",
            (assess_id, s["student_id"])).fetchone()
        assert tuple(kept) == (str(Decimal("70.00")),)
        snap_before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-list-grade-conflicts"], conn, ns(
            company_id=s["company_id"], section_id=None,
            connection_id=conn_id,
            conflict_type=None, conflict_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a list writes nothing
        assert r["total"] == 1
        row = r["conflicts"][0]
        assert row["lms_score"] == str(Decimal("75.00"))
        assert row["sis_score"] == str(Decimal("70.00"))
        assert row["conflict_type"] == "score_mismatch"
        assert row["grade_sync_status"] == "conflict"
        assert row["assessment_name"] == "Final Exam"
        # No ledger legs: a read returns stored conflict rows, never journals.

    def test_refuses_missing_connection_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _grade_import_setup(env)
        before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-list-grade-conflicts"], conn, ns(
            company_id=s["company_id"], section_id=None,
            connection_id=None,
            conflict_type=None, conflict_status=None,
            limit=50, offset=0,
        ))
        assert is_error(r)
        assert r["message"] == "--connection-id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-list-course-materials — stored rows (read-only)
# ---------------------------------------------------------------------------

class TestListCourseMaterialsDepth:
    def test_lists_active_materials_in_sort_order_archived_excluded(self, env):
        s, conn = env, env["conn"]
        _add_material(conn, s["company_id"], s["section_id"],
                      name="Syllabus", material_type="syllabus", sort_order=2)
        _add_material(conn, s["company_id"], s["section_id"],
                      name="Week 1 Reading", material_type="reading",
                      sort_order=1)
        old_id = _add_material(conn, s["company_id"], s["section_id"],
                               name="Old Notes", material_type="other",
                               sort_order=0)
        archived = call_action(
            MAT_ACTIONS["lms-delete-course-material"], conn,
            ns(material_id=old_id))
        assert is_ok(archived), archived
        snap_before = _snapshot(conn)
        r = call_action(MAT_ACTIONS["lms-list-course-materials"], conn, ns(
            company_id=s["company_id"], section_id=s["section_id"],
            material_type=None, include_archived=False,
            is_visible_to_students=None,
            limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert _snapshot(conn) == snap_before  # a list writes nothing
        assert r["total"] == 2
        assert [(m["name"], m["material_type"], m["access_type"],
                 m["material_status"]) for m in r["materials"]] == [
            ("Week 1 Reading", "reading", "url", "active"),
            ("Syllabus", "syllabus", "url", "active"),
        ]
        # The archived row still exists but is excluded from the listing.
        assert conn.execute(
            "SELECT status FROM educlaw_lms_course_material WHERE id = ?",
            (old_id,)).fetchone()[0] == "archived"
        # No ledger legs: a read returns stored rows, never journals.

    def test_refuses_missing_section_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _add_material(conn, s["company_id"], s["section_id"], name="Syllabus")
        before = _snapshot(conn)
        r = call_action(MAT_ACTIONS["lms-list-course-materials"], conn, ns(
            company_id=s["company_id"], section_id=None,
            material_type=None, include_archived=False,
            is_visible_to_students=None,
            limit=50, offset=0,
        ))
        assert is_error(r)
        assert r["message"] == "--section-id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# lms-update-course-material — stored row
# ---------------------------------------------------------------------------

class TestUpdateCourseMaterialDepth:
    def test_updates_two_fields_and_leaves_the_rest_alone(self, env):
        s, conn = env, env["conn"]
        mat_id = _add_material(conn, s["company_id"], s["section_id"],
                               name="Syllabus v1", material_type="syllabus",
                               sort_order=1)
        before = conn.execute(
            "SELECT name, description, material_type, access_type,"
            " external_url, is_visible_to_students, sort_order, section_id,"
            " status FROM educlaw_lms_course_material WHERE id = ?",
            (mat_id,)).fetchone()
        assert tuple(before) == ("Syllabus v1", "Syllabus v1 description",
                                 "syllabus", "url",
                                 "https://example.edu/syllabus.pdf",
                                 1, 1, s["section_id"], "active")
        r = call_action(MAT_ACTIONS["lms-update-course-material"], conn, ns(
            material_id=mat_id, name="Syllabus v2", sort_order=3,
        ))
        assert is_ok(r), r
        assert r["id"] == mat_id
        after = conn.execute(
            "SELECT name, description, material_type, access_type,"
            " external_url, is_visible_to_students, sort_order, section_id,"
            " status FROM educlaw_lms_course_material WHERE id = ?",
            (mat_id,)).fetchone()
        assert tuple(after) == ("Syllabus v2", "Syllabus v1 description",
                                "syllabus", "url",
                                "https://example.edu/syllabus.pdf",
                                1, 3, s["section_id"], "active")
        # No ledger legs: only the material row (plus one audit_log row)
        # moves, never journals.

    def test_refuses_bad_material_type_and_changes_nothing(self, env):
        s, conn = env, env["conn"]
        mat_id = _add_material(conn, s["company_id"], s["section_id"],
                               name="Syllabus v1", material_type="syllabus",
                               sort_order=1)
        before = _snapshot(conn)
        r = call_action(MAT_ACTIONS["lms-update-course-material"], conn, ns(
            material_id=mat_id, material_type="slideshow",
        ))
        assert is_error(r)
        assert r["message"] == ("--material-type must be one of: syllabus,"
                                " reading, video_link, assignment_guide,"
                                " rubric, other")
        assert _snapshot(conn) == before
        still = conn.execute(
            "SELECT name, material_type, sort_order"
            " FROM educlaw_lms_course_material WHERE id = ?",
            (mat_id,)).fetchone()
        assert tuple(still) == ("Syllabus v1", "syllabus", 1)
