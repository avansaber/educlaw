"""Behavioural depth tests for 12 educlaw-lms actions.

Each action below already had a test that proved the wrong thing: the
contract suite (testing/integration/contract/test_educlaw_lms_contract.py)
asserts all 12 are routable, and test_lms.py asserts response shape for
lms-add-course-material and lms-get-lms-connection. Neither observes the
database. The tests here assert the stored-row effect instead: which row
exists afterwards with which exact values, which row changed from what to
what, and what did not change. Rows are read back with PyPika queries
through erpclaw_lib.query on connections from erpclaw_lib.db.get_connection().

Ledger note: none of these 12 actions posts to the general ledger, so no
balanced-legs assertion can hold for any of them. Each happy-path test says
so once rather than asserting legs that do not exist.

Money note: scores are TEXT columns. Assertions compare exact Decimal values
as strings, never float, never approximate.
"""
import importlib.util
import os
import sys
import uuid
from decimal import Decimal

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
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_course = _helpers.seed_course

from erpclaw_lib.db import get_connection as _erp_get_connection
from erpclaw_lib.query import Q, P, Table, Field, insert_row

LMS_ACTIONS = _load("lms_sync", _SCRIPTS_DIR).ACTIONS
ASSIGN_ACTIONS = _load("assignments", _SCRIPTS_DIR).ACTIONS
GRADE_ACTIONS = _load("online_gradebook", _SCRIPTS_DIR).ACTIONS
MAT_ACTIONS = _load("course_materials", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def conn(db_path):
    handle = _erp_get_connection(db_path)
    yield handle
    try:
        handle.close()
    except Exception:
        pass


def _section(conn, company_id, course_id, term_id, number="SEC-001"):
    sec_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_section (id, naming_series, section_number, course_id,"
        " academic_term_id, max_enrollment, current_enrollment, status, company_id, created_by)"
        " VALUES (?, ?, ?, ?, ?, 30, 0, 'open', ?, '')",
        (sec_id, "SEC-" + sec_id[:8], number, course_id, term_id, company_id))
    conn.commit()
    return sec_id


def _enrollment(conn, student_id, section_id, company_id, status="enrolled"):
    enr_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_course_enrollment (id, student_id, section_id,"
        " enrollment_status, company_id) VALUES (?, ?, ?, ?, ?)",
        (enr_id, student_id, section_id, status, company_id))
    conn.commit()
    return enr_id


def _assessment_chain(conn, section_id, company_id, name="Midterm",
                      max_points="100", published=1):
    scale_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_grading_scale (id, name, company_id, created_by)"
        " VALUES (?, 'Depth Scale', ?, '')",
        (scale_id, company_id))
    plan_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment_plan (id, section_id, grading_scale_id,"
        " company_id, created_by) VALUES (?, ?, ?, ?, '')",
        (plan_id, section_id, scale_id, company_id))
    cat_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment_category (id, assessment_plan_id, name,"
        " weight_percentage, sort_order, created_by)"
        " VALUES (?, ?, 'Exams', '100', 1, '')",
        (cat_id, plan_id))
    assess_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment (id, assessment_plan_id, category_id, name,"
        " description, max_points, due_date, is_published, created_by)"
        " VALUES (?, ?, ?, ?, 'Depth assessment', ?, '2025-10-15', ?, '')",
        (assess_id, plan_id, cat_id, name, max_points, published))
    conn.commit()
    return assess_id


def _result(conn, assessment_id, student_id, enrollment_id, points):
    res_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_assessment_result (id, assessment_id, student_id,"
        " course_enrollment_id, points_earned, created_by)"
        " VALUES (?, ?, ?, ?, ?, '')",
        (res_id, assessment_id, student_id, enrollment_id, points))
    conn.commit()
    return res_id


def _connection(conn, company_id, lms_type="oneroster_csv",
                display_name="Depth LMS", dpa_signed=1):
    r = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
        company_id=company_id, lms_type=lms_type, display_name=display_name,
        endpoint_url=("https://lms.depth.test/api"
                      if lms_type in ("canvas", "moodle") else None),
        client_id=("depth-client"
                   if lms_type in ("canvas", "moodle") else None),
        client_secret=("depth-secret"
                       if lms_type in ("canvas", "moodle") else None),
        site_token=None, google_credentials=None,
        grade_direction="lms_to_sis",
        has_dpa_signed=dpa_signed, dpa_signed_date="2025-01-01",
        is_coppa_verified=0, coppa_cert_url=None,
        allowed_data_fields="[]",
        default_course_prefix=None,
        auto_push_assignments=0,
        auto_sync_enabled=None, sync_frequency_hours=None,
        connection_status=None, user_id="admin",
    ))
    assert is_ok(r)
    return r["id"]


def _activate(conn, conn_id):
    r = call_action(LMS_ACTIONS["lms-activate-lms-connection"], conn, ns(
        connection_id=conn_id))
    assert is_ok(r)
    return r


def _course_mapping(conn, conn_id, section_id, status="synced"):
    mid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_lms_course_mapping", {
        "id": P(), "lms_connection_id": P(), "section_id": P(),
        "lms_course_id": P(), "lms_course_url": P(), "lms_term_id": P(),
        "sync_status": P(), "last_synced_at": P(), "created_by": P()})
    conn.execute(sql, [mid, conn_id, section_id, "lms-depth-" + mid[:8],
                       "", "", status, "", "depth-test"])
    conn.commit()
    return mid


def _user_mapping(conn, conn_id, student_id, status="error", error="conflict!"):
    umid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_lms_user_mapping", {
        "id": P(), "lms_connection_id": P(), "sis_user_type": P(),
        "sis_user_id": P(), "lms_user_id": P(), "lms_username": P(),
        "lms_login_email": P(), "is_coppa_restricted": P(),
        "is_directory_restricted": P(), "sync_status": P(),
        "last_synced_at": P(), "sync_error": P(), "created_by": P()})
    conn.execute(sql, [umid, conn_id, "student", student_id,
                       "lms-depth-u-" + umid[:8],
                       "depth-u", "u@depth.test", 0, 0, status, "", error,
                       "depth-test"])
    conn.commit()
    return umid


def _sync_log(conn, conn_id, company_id, sync_type="roster_push",
              status="completed"):
    lid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_lms_sync_log", {
        "id": P(), "naming_series": P(), "lms_connection_id": P(),
        "sync_type": P(), "triggered_by": P(), "status": P(),
        "company_id": P(), "created_by": P()})
    conn.execute(sql, [lid, "SYN-DEPTH-" + lid[:8], conn_id, sync_type,
                       "depth-test", status, company_id, "depth-test"])
    conn.commit()
    return lid


def _grade_sync(conn, conn_id, log_id, assessment_id, student_id, result_id,
                lms_score="85.50", sis_score="70.00"):
    gid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_lms_grade_sync", {
        "id": P(), "lms_connection_id": P(), "sync_log_id": P(),
        "lms_assignment_id": P(), "lms_user_id": P(), "assessment_id": P(),
        "student_id": P(), "assessment_result_id": P(), "lms_score": P(),
        "sis_score": P(), "is_conflict": P(), "conflict_type": P(),
        "sync_status": P(), "created_by": P()})
    conn.execute(sql, [gid, conn_id, log_id, "lms-depth-assign",
                       "lms-depth-user", assessment_id, student_id, result_id,
                       lms_score, sis_score, 1, "score_mismatch", "conflict",
                       "depth-test"])
    conn.commit()
    return gid


def _row(conn, table, row_id):
    t = Table(table)
    return conn.execute(
        Q.from_(t).select(t.star).where(Field("id") == P()).get_sql(),
        (row_id,)).fetchone()


_SNAPSHOT_TABLES = (
    "educlaw_lms_connection",
    "educlaw_lms_sync_log",
    "educlaw_lms_course_mapping",
    "educlaw_lms_user_mapping",
    "educlaw_lms_assignment_mapping",
    "educlaw_lms_grade_sync",
    "educlaw_lms_course_material",
    "educlaw_assessment",
    "educlaw_assessment_result",
    "educlaw_course_enrollment",
    "educlaw_section",
    "educlaw_student",
    "company",
    "audit_log",
    "educlaw_data_access_log",
)


def _snapshot(conn):
    snap = {}
    for name in _SNAPSHOT_TABLES:
        rows = conn.execute("SELECT * FROM %s ORDER BY id" % name).fetchall()
        snap[name] = sorted(
            tuple("" if v is None else str(v) for v in tuple(r))
            for r in rows)
    return snap


class TestActivateLmsConnection:
    def test_activate_oneroster_marks_connection_active(self, conn, db_path):
        cid = seed_company(conn)
        conn_id = _connection(conn, cid, display_name="Depth OR")
        before = dict(_row(conn, "educlaw_lms_connection", conn_id))
        assert before["status"] == "draft"
        other = _connection(conn, cid, lms_type="canvas",
                            display_name="Depth Canvas")
        r = call_action(
            LMS_ACTIONS["lms-activate-lms-connection"], conn,
            ns(connection_id=conn_id))
        assert is_ok(r)
        assert r["connection_status"] == "active"
        after = dict(_row(conn, "educlaw_lms_connection", conn_id))
        assert after["status"] == "active"
        assert after["lms_site_name"] == "OneRoster CSV Export"
        assert after["lms_version"] == "1.1"
        assert after["naming_series"] == before["naming_series"]
        assert after["display_name"] == "Depth OR"
        assert dict(_row(conn, "educlaw_lms_connection", other))["status"] == "draft"
        # Ledger: activation updates connection status only; no GL postings.

    def test_activate_refuses_without_connection_id(self, conn, db_path):
        cid = seed_company(conn)
        _connection(conn, cid, display_name="Depth OR")
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-activate-lms-connection"], conn,
                        ns(connection_id=None))
        assert is_error(r)
        assert r["message"] == "--connection-id is required"
        assert _snapshot(conn) == before


class TestAddCourseMaterial:
    def test_add_material_stores_exact_row(self, conn, db_path):
        cid = seed_company(conn)
        sec = _section(conn, cid, seed_course(conn, cid),
                       seed_academic_term(conn, cid, seed_academic_year(conn, cid)))
        decoy = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
            company_id=cid, section_id=sec, name="Decoy",
            description="untouched", material_type="syllabus",
            access_type="url", external_url="https://example.edu/decoy.pdf",
            file_path=None, lms_connection_id=None,
            is_visible_to_students=1, available_from=None,
            available_until=None, sort_order=1, user_id="instructor"))
        assert is_ok(decoy)
        r = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
            company_id=cid, section_id=sec, name="Week 3 Reading",
            description="Chapter 3 handout", material_type="reading",
            access_type="url", external_url="https://example.edu/week3.pdf",
            file_path=None, lms_connection_id=None,
            is_visible_to_students=1, available_from=None,
            available_until=None, sort_order=7, user_id="instructor"))
        assert is_ok(r)
        stored = dict(_row(conn, "educlaw_lms_course_material", r["id"]))
        assert stored["section_id"] == sec
        assert stored["name"] == "Week 3 Reading"
        assert stored["description"] == "Chapter 3 handout"
        assert stored["material_type"] == "reading"
        assert stored["access_type"] == "url"
        assert stored["external_url"] == "https://example.edu/week3.pdf"
        assert int(stored["is_visible_to_students"]) == 1
        assert int(stored["sort_order"]) == 7
        assert stored["status"] == "active"
        assert stored["company_id"] == cid
        untouched = dict(_row(conn, "educlaw_lms_course_material", decoy["id"]))
        assert untouched["name"] == "Decoy"
        assert int(untouched["sort_order"]) == 1
        # Ledger: material creation writes one document row; no GL postings.

    def test_add_material_refuses_without_name(self, conn, db_path):
        cid = seed_company(conn)
        sec = _section(conn, cid, seed_course(conn, cid),
                       seed_academic_term(conn, cid, seed_academic_year(conn, cid)))
        before = _snapshot(conn)
        r = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
            company_id=cid, section_id=sec, name=None,
            description="nameless", material_type="reading",
            access_type="url", external_url="https://example.edu/x.pdf",
            file_path=None, lms_connection_id=None,
            is_visible_to_students=1, available_from=None,
            available_until=None, sort_order=0, user_id="instructor"))
        assert is_error(r)
        assert r["message"] == "--name is required"
        assert _snapshot(conn) == before


class TestApplyAssessmentUpdate:
    def _setup(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        sec = _section(conn, cid, seed_course(conn, cid), tid)
        conn_id = _connection(conn, cid)
        _activate(conn, conn_id)
        _course_mapping(conn, conn_id, sec)
        assess = _assessment_chain(conn, sec, cid)
        pushed = call_action(
            ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn,
            ns(assessment_id=assess, connection_id=conn_id, section_id=None,
               lms_grade_scheme="points", user_id="admin"))
        assert is_ok(pushed)
        return cid, conn_id, assess, pushed["lms_assignment_id"]

    def test_update_marks_mapping_synced(self, conn, db_path):
        cid, conn_id, assess, lms_assign_id = self._setup(conn)
        mapping = conn.execute(
            Q.from_(Table("educlaw_lms_assignment_mapping")).select(
                Table("educlaw_lms_assignment_mapping").star).where(
                Field("assessment_id") == P()).get_sql(), (assess,)).fetchone()
        conn.execute(
            "UPDATE educlaw_lms_assignment_mapping SET sync_status = 'error',"
            " sync_error = 'stale', is_published_in_lms = 0 WHERE id = ?",
            (mapping["id"],))
        conn.commit()
        r = call_action(ASSIGN_ACTIONS["lms-apply-assessment-update"], conn,
                        ns(assessment_id=assess, connection_id=conn_id))
        assert is_ok(r)
        assert r["updated"] is True
        after = dict(_row(conn, "educlaw_lms_assignment_mapping", mapping["id"]))
        assert after["sync_status"] == "synced"
        assert after["sync_error"] == ""
        assert int(after["is_published_in_lms"]) == 1
        assert after["last_synced_at"] != ""
        assert after["lms_assignment_id"] == lms_assign_id
        assess_row = dict(_row(conn, "educlaw_assessment", assess))
        assert assess_row["name"] == "Midterm"
        assert assess_row["max_points"] == "100"
        # Ledger: assignment sync touches mapping metadata only; no GL postings.

    def test_update_refuses_without_assessment_id(self, conn, db_path):
        cid, conn_id, _, _ = self._setup(conn)
        before = _snapshot(conn)
        r = call_action(ASSIGN_ACTIONS["lms-apply-assessment-update"], conn,
                        ns(assessment_id=None, connection_id=conn_id))
        assert is_error(r)
        assert r["message"] == "--assessment-id is required"
        assert _snapshot(conn) == before


class TestApplyCourseSync:
    def test_sync_writes_log_and_mappings(self, conn, db_path):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        sid = seed_student(conn, cid)
        sec = _section(conn, cid, seed_course(conn, cid), tid)
        _enrollment(conn, sid, sec, cid)
        conn_id = _connection(conn, cid, display_name="Depth Sync")
        _activate(conn, conn_id)
        before_sync_at = dict(
            _row(conn, "educlaw_lms_connection", conn_id))["last_sync_at"]
        r = call_action(LMS_ACTIONS["lms-apply-course-sync"], conn, ns(
            connection_id=conn_id, academic_term_id=tid, company_id=cid,
            section_id=None, user_id="admin"))
        assert is_ok(r)
        assert r["sync_status"] == "completed"
        assert r["sections_synced"] == 1
        assert r["students_synced"] == 1
        assert r["errors_count"] == 0
        log = conn.execute(
            Q.from_(Table("educlaw_lms_sync_log")).select(
                Table("educlaw_lms_sync_log").star).where(
                Field("id") == P()).get_sql(),
            (r["sync_log_id"],)).fetchone()
        assert log is not None
        log = dict(log)
        assert log["sync_type"] == "roster_push"
        assert log["status"] == "completed"
        assert log["academic_term_id"] == tid
        assert int(log["sections_synced"]) == 1
        assert int(log["students_synced"]) == 1
        assert int(log["errors_count"]) == 0
        cmap = conn.execute(
            "SELECT * FROM educlaw_lms_course_mapping"
            " WHERE lms_connection_id = ? AND section_id = ?",
            (conn_id, sec)).fetchone()
        assert cmap is not None
        cmap = dict(cmap)
        assert cmap["lms_course_id"] == "oneroster_" + sec[:8]
        assert cmap["sync_status"] == "synced"
        umap = conn.execute(
            "SELECT * FROM educlaw_lms_user_mapping"
            " WHERE lms_connection_id = ? AND sis_user_id = ?",
            (conn_id, sid)).fetchone()
        assert umap is not None
        umap = dict(umap)
        assert umap["lms_user_id"] == "oneroster_stu_" + sid[:8]
        assert umap["sync_status"] == "synced"
        assert dict(_row(conn, "educlaw_lms_connection", conn_id))[
            "last_sync_at"] != before_sync_at
        ferpa = conn.execute(
            "SELECT * FROM educlaw_data_access_log WHERE student_id = ?",
            (sid,)).fetchone()
        assert ferpa is not None
        ferpa = dict(ferpa)
        assert ferpa["data_category"] == "demographics"
        assert ferpa["access_reason"] == "LMS roster disclosure to Depth Sync"
        # Ledger: roster push writes sync/mapping/disclosure rows; no GL postings.

    def test_sync_refuses_without_term(self, conn, db_path):
        cid = seed_company(conn)
        conn_id = _connection(conn, cid)
        _activate(conn, conn_id)
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-apply-course-sync"], conn, ns(
            connection_id=conn_id, academic_term_id=None, company_id=cid,
            section_id=None, user_id="admin"))
        assert is_error(r)
        assert r["message"] == "--academic-term-id is required"
        assert _snapshot(conn) == before


class TestApplyGradeResolution:
    def _setup(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        sid = seed_student(conn, cid)
        sec = _section(conn, cid, seed_course(conn, cid), tid)
        enr = _enrollment(conn, sid, sec, cid)
        assess = _assessment_chain(conn, sec, cid)
        res = _result(conn, assess, sid, enr, "70.00")
        other_sid = seed_student(conn, cid)
        other_enr = _enrollment(conn, other_sid, sec, cid)
        other_res = _result(conn, assess, other_sid, other_enr, "60.00")
        conn_id = _connection(conn, cid)
        log_id = _sync_log(conn, conn_id, cid)
        gsid = _grade_sync(conn, conn_id, log_id, assess, sid, res)
        return conn_id, gsid, res, other_res

    def test_lms_wins_applies_exact_text_score(self, conn, db_path):
        _, gsid, res, other_res = self._setup(conn)
        r = call_action(GRADE_ACTIONS["lms-apply-grade-resolution"], conn, ns(
            grade_sync_id=gsid, resolution="lms_wins",
            resolved_by="registrar", new_score=None, push_to_lms=False,
            user_id="registrar"))
        assert is_ok(r)
        assert r["grade_sync_status"] == "applied"
        synced = dict(_row(conn, "educlaw_lms_grade_sync", gsid))
        assert synced["sync_status"] == "applied"
        assert synced["resolution"] == "lms_wins"
        assert synced["resolved_by"] == "registrar"
        assert synced["resolved_at"] != ""
        assert synced["assessment_result_id"] == res
        stored = dict(_row(conn, "educlaw_assessment_result", res))
        assert stored["points_earned"] == "85.50"
        assert Decimal(stored["points_earned"]) == Decimal("85.50")
        assert dict(_row(conn, "educlaw_assessment_result",
                         other_res))["points_earned"] == "60.00"
        # Ledger: resolution rewrites the SIS result and sync metadata;
        # no GL postings, so no balanced-legs assertion can hold.

    def test_resolution_refuses_unknown_strategy(self, conn, db_path):
        _, gsid, _, _ = self._setup(conn)
        before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-apply-grade-resolution"], conn, ns(
            grade_sync_id=gsid, resolution="bogus",
            resolved_by="registrar", new_score=None, push_to_lms=False,
            user_id="registrar"))
        assert is_error(r)
        assert r["message"] == ("--resolution must be one of:"
                                " lms_wins, sis_wins, manual")
        assert _snapshot(conn) == before


class TestApplySyncResolution:
    def test_user_sis_wins_requeues_mapping(self, conn, db_path):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        conn_id = _connection(conn, cid)
        umid = _user_mapping(conn, conn_id, sid)
        kept = _user_mapping(conn, conn_id, seed_student(conn, cid),
                             status="synced", error="")
        r = call_action(LMS_ACTIONS["lms-apply-sync-resolution"], conn, ns(
            connection_id=conn_id, entity_type="user", entity_id=umid,
            resolution="sis_wins"))
        assert is_ok(r)
        assert r["sync_status"] == "pending"
        after = dict(_row(conn, "educlaw_lms_user_mapping", umid))
        assert after["sync_status"] == "pending"
        assert after["sync_error"] == ""
        assert after["last_synced_at"] != ""
        assert dict(_row(conn, "educlaw_lms_user_mapping", kept))[
            "sync_status"] == "synced"
        # Ledger: conflict resolution flips mapping status only; no GL postings.

    def test_sync_resolution_refuses_unknown_entity(self, conn, db_path):
        cid = seed_company(conn)
        conn_id = _connection(conn, cid)
        _user_mapping(conn, conn_id, seed_student(conn, cid))
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-apply-sync-resolution"], conn, ns(
            connection_id=conn_id, entity_type="bogus", entity_id="x",
            resolution="sis_wins"))
        assert is_error(r)
        assert r["message"] == "--entity-type must be one of: user, course"
        assert _snapshot(conn) == before


class TestCompleteLmsCourse:
    def test_close_marks_mapping_closed_with_log(self, conn, db_path):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        sec = _section(conn, cid, seed_course(conn, cid), tid)
        conn_id = _connection(conn, cid)
        mid = _course_mapping(conn, conn_id, sec)
        umid = _user_mapping(conn, conn_id, seed_student(conn, cid),
                             status="synced", error="")
        r = call_action(GRADE_ACTIONS["lms-complete-lms-course"], conn, ns(
            section_id=sec, connection_id=conn_id, user_id="admin"))
        assert is_ok(r)
        assert r["course_map_status"] == "closed"
        closed = dict(_row(conn, "educlaw_lms_course_mapping", mid))
        assert closed["sync_status"] == "closed"
        assert closed["last_synced_at"] != ""
        log = dict(_row(conn, "educlaw_lms_sync_log", r["sync_log_id"]))
        assert log["sync_type"] == "roster_push"
        assert log["status"] == "completed"
        assert log["section_id"] == sec
        assert dict(_row(conn, "educlaw_lms_user_mapping", umid))[
            "sync_status"] == "synced"
        # Ledger: closure flips the mapping and appends a log; no GL postings.

    def test_close_refuses_without_section(self, conn, db_path):
        cid = seed_company(conn)
        conn_id = _connection(conn, cid)
        before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-complete-lms-course"], conn, ns(
            section_id=None, connection_id=conn_id, user_id="admin"))
        assert is_error(r)
        assert r["message"] == "--section-id is required"
        assert _snapshot(conn) == before


class TestDeleteCourseMaterial:
    def test_delete_archives_material_row(self, conn, db_path):
        cid = seed_company(conn)
        sec = _section(conn, cid, seed_course(conn, cid),
                       seed_academic_term(conn, cid, seed_academic_year(conn, cid)))
        added = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
            company_id=cid, section_id=sec, name="Ephemeral",
            description="to archive", material_type="reading",
            access_type="url", external_url="https://example.edu/e.pdf",
            file_path=None, lms_connection_id=None,
            is_visible_to_students=1, available_from=None,
            available_until=None, sort_order=2, user_id="instructor"))
        assert is_ok(added)
        before = dict(_row(conn, "educlaw_lms_course_material", added["id"]))
        assert before["status"] == "active"
        r = call_action(MAT_ACTIONS["lms-delete-course-material"], conn, ns(
            material_id=added["id"]))
        assert is_ok(r)
        assert r["material_status"] == "archived"
        after = dict(_row(conn, "educlaw_lms_course_material", added["id"]))
        assert after["status"] == "archived"
        assert after["name"] == "Ephemeral"
        assert after["updated_at"] != ""
        # Ledger: archival flips one status column; no GL postings.

    def test_delete_refuses_unknown_material(self, conn, db_path):
        cid = seed_company(conn)
        _section(conn, cid, seed_course(conn, cid),
                 seed_academic_term(conn, cid, seed_academic_year(conn, cid)))
        before = _snapshot(conn)
        r = call_action(MAT_ACTIONS["lms-delete-course-material"], conn, ns(
            material_id="mat-does-not-exist"))
        assert is_error(r)
        assert r["message"] == "Course material mat-does-not-exist not found"
        assert _snapshot(conn) == before


class TestDeleteLmsAssignment:
    def _setup(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        sec = _section(conn, cid, seed_course(conn, cid), tid)
        conn_id = _connection(conn, cid)
        _activate(conn, conn_id)
        mid = _course_mapping(conn, conn_id, sec)
        assess = _assessment_chain(conn, sec, cid)
        pushed = call_action(
            ASSIGN_ACTIONS["lms-submit-assessment-to-lms"], conn,
            ns(assessment_id=assess, connection_id=conn_id, section_id=None,
               lms_grade_scheme="points", user_id="admin"))
        assert is_ok(pushed)
        return conn_id, assess, mid

    def test_delete_unlinks_mapping_with_reason(self, conn, db_path):
        conn_id, assess, course_mid = self._setup(conn)
        mapping = conn.execute(
            "SELECT * FROM educlaw_lms_assignment_mapping"
            " WHERE lms_connection_id = ? AND assessment_id = ?",
            (conn_id, assess)).fetchone()
        assert dict(mapping)["sync_status"] == "synced"
        r = call_action(ASSIGN_ACTIONS["lms-delete-lms-assignment"], conn, ns(
            assessment_id=assess, connection_id=conn_id))
        assert is_ok(r)
        assert r["assignment_sync_status"] == "error"
        after = dict(_row(conn, "educlaw_lms_assignment_mapping", mapping["id"]))
        assert after["sync_status"] == "error"
        assert after["sync_error"] == "unlinked by user"
        assert after["last_synced_at"] != ""
        assert dict(_row(conn, "educlaw_lms_course_mapping",
                         course_mid))["sync_status"] == "synced"
        # Ledger: unlinking flips the mapping row only; no GL postings.

    def test_delete_refuses_without_connection(self, conn, db_path):
        conn_id, assess, _ = self._setup(conn)
        before = _snapshot(conn)
        r = call_action(ASSIGN_ACTIONS["lms-delete-lms-assignment"], conn, ns(
            assessment_id=assess, connection_id=None))
        assert is_error(r)
        assert r["message"] == "--connection-id is required"
        assert _snapshot(conn) == before


class TestGenerateOnerosterCsv:
    def _setup(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        sid = seed_student(conn, cid)
        sec = _section(conn, cid, seed_course(conn, cid), tid)
        _enrollment(conn, sid, sec, cid)
        return cid, tid

    def test_export_without_connection_writes_zip_and_no_log(self, conn, db_path,
                                                             tmp_path):
        cid, tid = self._setup(conn)
        outdir = str(tmp_path / "oneroster")
        os.makedirs(outdir, exist_ok=True)
        logs_before = conn.execute(
            "SELECT COUNT(*) FROM educlaw_lms_sync_log").fetchone()[0]
        r = call_action(GRADE_ACTIONS["lms-generate-oneroster-csv"], conn, ns(
            academic_term_id=tid, output_dir=outdir, company_id=cid,
            include_grades=False, connection_id=None, user_id="admin"))
        assert is_ok(r)
        assert r["sync_log_id"] is None
        assert r["student_count"] == 1
        assert r["section_count"] == 1
        assert r["zip_path"].endswith(".zip")
        assert os.path.exists(r["zip_path"])
        assert len(r["files_generated"]) >= 1
        assert conn.execute(
            "SELECT COUNT(*) FROM educlaw_lms_sync_log").fetchone()[0] == logs_before
        # Ledger: CSV export writes files, not ledger rows; no GL postings.

    def test_export_with_connection_crashes_on_log_insert(self, conn, db_path,
                                                          tmp_path):
        # DEFECT (deliberately not fixed): with --connection-id the action
        # builds a sync-log INSERT with 12 placeholders but 13 bound values
        # (a stray "completed" alongside the 'completed' literal), so sqlite
        # raises ProgrammingError instead of returning a response. The export
        # zip itself is written before the crash; no sync-log row is stored.
        cid, tid = self._setup(conn)
        conn_id = _connection(conn, cid)
        outdir = str(tmp_path / "oneroster-conn")
        os.makedirs(outdir, exist_ok=True)
        with pytest.raises(Exception, match="bindings"):
            call_action(GRADE_ACTIONS["lms-generate-oneroster-csv"], conn, ns(
                academic_term_id=tid, output_dir=outdir, company_id=cid,
                include_grades=False, connection_id=conn_id, user_id="admin"))
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) FROM educlaw_lms_sync_log"
            " WHERE sync_type = 'oneroster_export'").fetchone()[0] == 0

    def test_export_refuses_without_output_dir(self, conn, db_path):
        cid, tid = self._setup(conn)
        before = _snapshot(conn)
        r = call_action(GRADE_ACTIONS["lms-generate-oneroster-csv"], conn, ns(
            academic_term_id=tid, output_dir=None, company_id=cid,
            include_grades=False, connection_id=None, user_id="admin"))
        assert is_error(r)
        assert r["message"] == "--output-dir is required"
        assert _snapshot(conn) == before


class TestGetCourseMaterial:
    def test_get_returns_stored_values_not_shape(self, conn, db_path):
        cid = seed_company(conn)
        sec = _section(conn, cid, seed_course(conn, cid),
                       seed_academic_term(conn, cid, seed_academic_year(conn, cid)))
        first = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
            company_id=cid, section_id=sec, name="Real Syllabus",
            description="The authoritative copy", material_type="syllabus",
            access_type="url", external_url="https://example.edu/real.pdf",
            file_path=None, lms_connection_id=None,
            is_visible_to_students=1, available_from=None,
            available_until=None, sort_order=3, user_id="instructor"))
        second = call_action(MAT_ACTIONS["lms-add-course-material"], conn, ns(
            company_id=cid, section_id=sec, name="Other Doc",
            description="decoy", material_type="other",
            access_type="url", external_url="https://example.edu/other.pdf",
            file_path=None, lms_connection_id=None,
            is_visible_to_students=0, available_from=None,
            available_until=None, sort_order=4, user_id="instructor"))
        assert is_ok(first) and is_ok(second)
        r = call_action(MAT_ACTIONS["lms-get-course-material"], conn, ns(
            material_id=first["id"]))
        assert is_ok(r)
        stored = dict(_row(conn, "educlaw_lms_course_material", first["id"]))
        assert r["id"] == stored["id"] == first["id"]
        assert r["name"] == stored["name"] == "Real Syllabus"
        assert r["description"] == stored["description"] == "The authoritative copy"
        assert r["material_type"] == stored["material_type"] == "syllabus"
        assert r["access_type"] == stored["access_type"] == "url"
        assert r["external_url"] == stored["external_url"] == "https://example.edu/real.pdf"
        assert r["material_status"] == "active" == stored["status"]
        assert r["name"] != "Other Doc"
        # Ledger: a lookup writes nothing at all; no GL postings.

    def test_get_refuses_unknown_material(self, conn, db_path):
        cid = seed_company(conn)
        _section(conn, cid, seed_course(conn, cid),
                 seed_academic_term(conn, cid, seed_academic_year(conn, cid)))
        before = _snapshot(conn)
        r = call_action(MAT_ACTIONS["lms-get-course-material"], conn, ns(
            material_id="mat-does-not-exist"))
        assert is_error(r)
        assert r["message"] == "Course material mat-does-not-exist not found"
        assert _snapshot(conn) == before


class TestGetLmsConnection:
    def test_get_returns_masked_stored_values(self, conn, db_path):
        cid = seed_company(conn)
        added = call_action(LMS_ACTIONS["lms-add-lms-connection"], conn, ns(
            company_id=cid, lms_type="canvas", display_name="Mask Check",
            endpoint_url="https://canvas.check.edu/api/v1",
            client_id="check-client", client_secret="test-secret-value",
            site_token=None, google_credentials=None,
            grade_direction="sis_to_lms",
            has_dpa_signed=1, dpa_signed_date="2025-02-01",
            is_coppa_verified=0, coppa_cert_url=None,
            allowed_data_fields="[]", default_course_prefix=None,
            auto_push_assignments=0, auto_sync_enabled=None,
            sync_frequency_hours=None, connection_status=None,
            user_id="admin"))
        assert is_ok(added)
        r = call_action(LMS_ACTIONS["lms-get-lms-connection"], conn, ns(
            connection_id=added["id"], company_id=cid))
        assert is_ok(r)
        stored = dict(_row(conn, "educlaw_lms_connection", added["id"]))
        assert r["display_name"] == stored["display_name"] == "Mask Check"
        assert r["lms_type"] == stored["lms_type"] == "canvas"
        assert r["endpoint_url"] == stored["endpoint_url"] == "https://canvas.check.edu/api/v1"
        assert r["grade_direction"] == stored["grade_direction"] == "sis_to_lms"
        assert r["connection_status"] == stored["status"] == "draft"
        assert r["client_secret_masked"] == "*************alue"
        assert stored["client_secret_encrypted"] != "test-secret-value"
        assert not [k for k in r if "encrypted" in k]
        # Ledger: a lookup writes nothing at all; no GL postings.

    def test_get_refuses_unknown_connection(self, conn, db_path):
        cid = seed_company(conn)
        _connection(conn, cid)
        before = _snapshot(conn)
        r = call_action(LMS_ACTIONS["lms-get-lms-connection"], conn, ns(
            connection_id="conn-does-not-exist", company_id=cid))
        assert is_error(r)
        assert r["message"] == "LMS connection conn-does-not-exist not found"
        assert _snapshot(conn) == before
