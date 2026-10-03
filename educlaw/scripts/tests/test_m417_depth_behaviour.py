"""M417 depth tests for educlaw — behavioural evidence for 12 actions.

Each action below previously had only a shape test (response keys) or a
routability contract test. Every test here reads the database back after the
call and compares exact values, plus one refusal case per action proving the
refusal message is truthful and the database is unchanged afterwards.

Actions covered (12):
  edu-portal-student-discipline, edu-portal-student-fees,
  edu-portal-student-schedule, edu-record-assessment-result,
  edu-record-batch-attendance, edu-record-batch-results,
  edu-record-data-access, edu-student-reading-history,
  edu-submit-announcement, edu-submit-emergency-alert,
  edu-submit-grades, edu-submit-notification.

Conventions: money stays text (Decimal compared as exact strings, never
float); all reads go through PyPika (erpclaw_lib.query); no ledger exists for
any of these actions (each class says so explicitly), so the depth signal is
stored rows, never journal legs.
"""
import importlib.util
import json
import os
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
get_conn = _helpers.get_conn
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_course = _helpers.seed_course
seed_room = _helpers.seed_room
seed_employee = _helpers.seed_employee
seed_instructor = _helpers.seed_instructor
seed_section = _helpers.seed_section
seed_student = _helpers.seed_student
seed_guardian = _helpers.seed_guardian
seed_enrollment = _helpers.seed_enrollment

from erpclaw_lib.query import Q, Table, P, insert_row

PORTAL_ACTIONS = _load("portal", _SCRIPTS_DIR).ACTIONS
GRADING_ACTIONS = _load("grading", _SCRIPTS_DIR).ACTIONS
ATTENDANCE_ACTIONS = _load("attendance", _SCRIPTS_DIR).ACTIONS
COMMUNICATIONS_ACTIONS = _load("communications", _SCRIPTS_DIR).ACTIONS
STUDENTS_ACTIONS = _load("students", _SCRIPTS_DIR).ACTIONS
LIBRARY_ACTIONS = _load("library", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS


# ── DB read helpers (PyPika through erpclaw_lib.query) ───────────────────────

def _rows(conn, table, **filters):
    tbl = Table(table)
    q = Q.from_(tbl).select(tbl.star)
    params = []
    for key, value in filters.items():
        q = q.where(getattr(tbl, key) == P())
        params.append(value)
    return [dict(r) for r in conn.execute(q.get_sql(), params).fetchall()]


def _one(conn, table, **filters):
    found = _rows(conn, table, **filters)
    assert found, f"expected a row in {table} for {filters}"
    return found[0]


def _snapshot(conn, tables):
    """Serialised contents of the given tables for before/after comparison."""
    snap = {}
    for name in tables:
        tbl = Table(name)
        fetched = conn.execute(Q.from_(tbl).select(tbl.star).get_sql(), ()).fetchall()
        snap[name] = sorted(json.dumps(dict(r), sort_keys=True, default=str) for r in fetched)
    return snap


def _link_guardian(conn, student_id, guardian_id, relationship="mother"):
    sql, _ = insert_row("educlaw_student_guardian", {
        "id": P(), "student_id": P(), "guardian_id": P(),
        "relationship": P(), "has_custody": P(), "can_pickup": P(),
        "receives_communications": P(), "is_primary_contact": P(),
        "is_emergency_contact": P(),
    })
    conn.execute(sql, (str(uuid.uuid4()), student_id, guardian_id, relationship, 1, 1, 1, 1, 1))
    conn.commit()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def depth(db_path):
    """Company + term + course + section + two students/enrollments + guardian linked to first."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    crs = seed_course(conn, cid)
    rm = seed_room(conn, cid)
    emp = seed_employee(conn, cid)
    inst = seed_instructor(conn, cid, emp)
    sec = seed_section(conn, cid, crs, tid, instructor_id=inst, room_id=rm)
    s1 = seed_student(conn, cid)
    s2 = seed_student(conn, cid)
    e1 = seed_enrollment(conn, s1, sec, cid)
    e2 = seed_enrollment(conn, s2, sec, cid)
    g = seed_guardian(conn, cid)
    _link_guardian(conn, s1, g)
    yield {
        "conn": conn, "company_id": cid, "term_id": tid, "course_id": crs,
        "room_id": rm, "employee_id": emp, "instructor_id": inst,
        "section_id": sec, "student_id": s1, "student2_id": s2,
        "enrollment_id": e1, "enrollment2_id": e2, "guardian_id": g,
    }
    conn.close()


@pytest.fixture
def graded(depth):
    """Depth setup plus a grading scale/plan/category/assessment for the section."""
    conn = depth["conn"]
    cid = depth["company_id"]
    entries = [
        {"letter_grade": "A", "grade_points": "4.0", "min_percentage": "90", "max_percentage": "100"},
        {"letter_grade": "B", "grade_points": "3.0", "min_percentage": "80", "max_percentage": "89.99"},
        {"letter_grade": "F", "grade_points": "0.0", "min_percentage": "0", "max_percentage": "59.99"},
    ]
    r = call_action(GRADING_ACTIONS["edu-add-grading-scale"], conn, ns(
        company_id=cid, name="Depth Scale", description="",
        entries=json.dumps(entries), is_default=1,
    ))
    assert is_ok(r)
    scale_id = r["id"]
    r = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
        section_id=depth["section_id"], grading_scale_id=scale_id,
        company_id=cid,
        categories=json.dumps([{"name": "Tests", "weight_percentage": "100"}]),
    ))
    assert is_ok(r)
    plan_id = r["id"]
    category_id = _one(conn, "educlaw_assessment_category", assessment_plan_id=plan_id)["id"]
    r = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
        plan_id=plan_id, category_id=category_id, name="Midterm",
        max_points="100", due_date="2025-10-15", description=None,
        allows_extra_credit=None, sort_order=None, company_id=cid,
    ))
    assert is_ok(r)
    depth["scale_id"] = scale_id
    depth["plan_id"] = plan_id
    depth["category_id"] = category_id
    depth["assessment_id"] = r["id"]
    return depth


def _seed_draft_announcement(conn, company_id, title="Depth draft", body="Depth body text"):
    ann_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_announcement", {
        "id": P(), "title": P(), "body": P(), "priority": P(),
        "audience_type": P(), "audience_filter": P(), "publish_date": P(),
        "expiry_date": P(), "announcement_status": P(), "published_by": P(),
        "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P(),
    })
    now = "2025-09-01T00:00:00Z"
    conn.execute(sql, (ann_id, title, body, "normal", "all", "{}",
                       "2025-09-01", "2025-12-31", "draft", "", company_id, now, now, ""))
    conn.commit()
    return ann_id


# ══════════════════════════════════════════════════════════════════════════════
# PORTAL (read-only views: depth signal is stored-row reads, never ledger)
# ══════════════════════════════════════════════════════════════════════════════

class TestPortalStudentScheduleDepth:
    # No ledger effect: this action only SELECTs enrollments/sections; it
    # writes no rows anywhere, so the behavioural signal is that the returned
    # schedule matches the stored enrollment exactly and nothing changes.

    def test_schedule_matches_stored_enrollment(self, depth):
        before = _snapshot(depth["conn"], ["educlaw_course_enrollment", "educlaw_section", "audit_log"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-schedule"], depth["conn"], ns(
            guardian_id=depth["guardian_id"], student_id=depth["student_id"],
        ))
        assert is_ok(r)
        assert r["count"] == 1
        entry = r["schedule"][0]
        room = _one(depth["conn"], "educlaw_room", id=depth["room_id"])
        assert entry["course_code"] == "MATH101"
        assert entry["course_name"] == "Test Course"
        assert entry["section_number"] == "001"
        assert entry["room_number"] == room["room_number"]
        assert entry["building"] == "Main"
        assert entry["instructor_first_name"] == "Test"
        assert entry["instructor_last_name"] == "Teacher"
        # The guardian's other-unlinked student must not leak in.
        assert _snapshot(depth["conn"], ["educlaw_course_enrollment", "educlaw_section", "audit_log"]) == before

    def test_schedule_refusal_unlinked_guardian(self, depth):
        other = seed_guardian(depth["conn"], depth["company_id"])
        before = _snapshot(depth["conn"], ["educlaw_course_enrollment", "educlaw_section", "audit_log"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-schedule"], depth["conn"], ns(
            guardian_id=other, student_id=depth["student_id"],
        ))
        assert is_error(r)
        assert "Access denied" in r.get("message", "")
        assert _snapshot(depth["conn"], ["educlaw_course_enrollment", "educlaw_section", "audit_log"]) == before


class TestPortalStudentFeesDepth:
    # No ledger effect: this view reads sales_invoice rows and active
    # scholarships; it posts no charges, payments, or journal legs. Money is
    # text: invoice totals and discount amounts compare as exact strings.

    def test_fees_match_stored_invoice_and_scholarship(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        cust_id = str(uuid.uuid4())
        sql, _ = insert_row("customer", {
            "id": P(), "name": P(), "email": P(), "company_id": P(), "created_at": P(),
        })
        conn.execute(sql, (cust_id, "Depth Family", "depth@example.com", cid, "2025-09-01T00:00:00Z"))
        tbl = Table("educlaw_student")
        conn.execute(
            Q.update(tbl).set(tbl.customer_id, P()).where(tbl.id == P()).get_sql(),
            (cust_id, depth["student_id"]),
        )
        sql, _ = insert_row("sales_invoice", {
            "id": P(), "naming_series": P(), "customer_id": P(),
            "total_amount": P(), "status": P(), "company_id": P(), "created_at": P(),
        })
        conn.execute(sql, (str(uuid.uuid4()), "INV-1", cust_id, "1250.00", "unpaid", cid, "2025-09-01T00:00:00Z"))
        conn.commit()
        r = call_action(FEES_ACTIONS["edu-add-scholarship"], conn, ns(
            student_id=depth["student_id"], name="Depth Award",
            discount_type="fixed", discount_amount="250.00",
            company_id=cid, academic_term_id=None,
            applies_to_category_id=None, reason=None, approved_by=None,
        ))
        assert is_ok(r)
        before = _snapshot(conn, ["educlaw_scholarship", "sales_invoice", "audit_log"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-fees"], conn, ns(
            guardian_id=depth["guardian_id"], student_id=depth["student_id"],
        ))
        assert is_ok(r)
        assert len(r["invoices"]) == 1
        assert r["invoices"][0]["total_amount"] == "1250.00"
        assert Decimal(str(r["invoices"][0]["total_amount"])) == Decimal("1250.00")
        assert len(r["active_scholarships"]) == 1
        assert r["active_scholarships"][0]["discount_amount"] == "250.00"
        assert Decimal(str(r["active_scholarships"][0]["discount_amount"])) == Decimal("250.00")
        assert _snapshot(conn, ["educlaw_scholarship", "sales_invoice", "audit_log"]) == before

    def test_fees_refusal_missing_student(self, depth):
        before = _snapshot(depth["conn"], ["educlaw_scholarship", "sales_invoice", "audit_log"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-fees"], depth["conn"], ns(
            guardian_id=depth["guardian_id"], student_id=None,
        ))
        assert is_error(r)
        assert "--student-id is required" in r.get("message", "")
        assert _snapshot(depth["conn"], ["educlaw_scholarship", "sales_invoice", "audit_log"]) == before


class TestPortalStudentDisciplineDepth:
    # No ledger effect and no stored rows: core educlaw ships no discipline
    # table, so this action is a read-only placeholder. The test pins that
    # contract (empty list plus note) and that the call writes nothing.

    def test_discipline_placeholder_writes_nothing(self, depth):
        before = _snapshot(depth["conn"], ["educlaw_student_guardian", "educlaw_student", "audit_log"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-discipline"], depth["conn"], ns(
            guardian_id=depth["guardian_id"], student_id=depth["student_id"],
        ))
        assert is_ok(r)
        assert r["discipline_records"] == []
        assert r["note"] == "No discipline records found"
        assert r["student_id"] == depth["student_id"]
        assert _snapshot(depth["conn"], ["educlaw_student_guardian", "educlaw_student", "audit_log"]) == before

    def test_discipline_refusal_unlinked_guardian(self, depth):
        other = seed_guardian(depth["conn"], depth["company_id"])
        before = _snapshot(depth["conn"], ["educlaw_student_guardian", "educlaw_student", "audit_log"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-discipline"], depth["conn"], ns(
            guardian_id=other, student_id=depth["student_id"],
        ))
        assert is_error(r)
        assert "Access denied" in r.get("message", "")
        assert _snapshot(depth["conn"], ["educlaw_student_guardian", "educlaw_student", "audit_log"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# LIBRARY (read-only view over circulation rows)
# ══════════════════════════════════════════════════════════════════════════════

class TestStudentReadingHistoryDepth:
    # No ledger effect: this action SELECTs circulation rows; fines are TEXT
    # ("0") and no invoice or journal leg is posted. Setup writes go through
    # the owning library actions.

    def test_history_matches_stored_circulation(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="Depth Book", title=None, company_id=cid, item_type="book",
            description="Depth Author", code="DEPTH-ISBN-1", room_type="fiction",
            building="Main", capacity=1, search=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        item_id = r["id"]
        r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            reference_id=item_id, library_item_id=None,
            student_id=depth["student_id"], limit=50, offset=0,
        ))
        assert is_ok(r)
        circ_id = r["circulation_id"]
        before = _snapshot(conn, ["educlaw_circulation", "educlaw_library_item", "audit_log"])
        r = call_action(LIBRARY_ACTIONS["edu-student-reading-history"], conn, ns(
            student_id=depth["student_id"], limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["total_checkouts"] == 1
        assert r["total_books_returned"] == 0
        assert r["total_fines"] == "0"
        assert Decimal(str(r["total_fines"])) == Decimal("0")
        assert len(r["history"]) == 1
        entry = r["history"][0]
        stored = _one(conn, "educlaw_circulation", id=circ_id)
        assert entry["circulation_id"] == stored["id"] == circ_id
        assert entry["title"] == "Depth Book"
        assert entry["author"] == "Depth Author"
        assert entry["isbn"] == "DEPTH-ISBN-1"
        assert entry["status"] == "checked_out"
        assert entry["fine_amount"] == "0"
        assert _snapshot(conn, ["educlaw_circulation", "educlaw_library_item", "audit_log"]) == before

    def test_history_refusal_missing_student(self, depth):
        before = _snapshot(depth["conn"], ["educlaw_circulation", "audit_log"])
        r = call_action(LIBRARY_ACTIONS["edu-student-reading-history"], depth["conn"], ns(
            student_id=None, limit=50, offset=0,
        ))
        assert is_error(r)
        assert "--student-id is required" in r.get("message", "")
        assert _snapshot(depth["conn"], ["educlaw_circulation", "audit_log"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# GRADING (stored-row writes; percentages/points are exact TEXT, never ledger)
# ══════════════════════════════════════════════════════════════════════════════

class TestRecordAssessmentResultDepth:
    # No ledger effect: this action inserts/updates one educlaw_assessment_result
    # row (gradebook only). Points compare as exact Decimal strings.

    def test_result_row_stored_exactly(self, graded):
        conn = graded["conn"]
        before = _snapshot(conn, ["educlaw_assessment_result", "audit_log"])
        assert before["educlaw_assessment_result"] == []
        r = call_action(GRADING_ACTIONS["edu-record-assessment-result"], conn, ns(
            assessment_id=graded["assessment_id"], student_id=graded["student_id"],
            points_earned="85", graded_by="teacher-1", is_exempt=None,
            is_late=None, comments="Well done", enrollment_id=None,
        ))
        assert is_ok(r)
        assert r["points_earned"] == "85"
        row = _one(conn, "educlaw_assessment_result", id=r["id"])
        assert row["assessment_id"] == graded["assessment_id"]
        assert row["student_id"] == graded["student_id"]
        assert row["course_enrollment_id"] == graded["enrollment_id"]
        assert row["points_earned"] == "85"
        assert Decimal(str(row["points_earned"])) == Decimal("85")
        assert row["comments"] == "Well done"
        assert row["graded_by"] == "teacher-1"
        assert row["is_exempt"] == 0
        assert row["is_late"] == 0
        # The second student's row must not exist.
        assert _rows(conn, "educlaw_assessment_result", student_id=graded["student2_id"]) == []

    def test_result_refusal_over_max_writes_nothing(self, graded):
        conn = graded["conn"]
        before = _snapshot(conn, ["educlaw_assessment_result", "audit_log"])
        r = call_action(GRADING_ACTIONS["edu-record-assessment-result"], conn, ns(
            assessment_id=graded["assessment_id"], student_id=graded["student_id"],
            points_earned="101", graded_by="teacher-1", is_exempt=None,
            is_late=None, comments="", enrollment_id=None,
        ))
        assert is_error(r)
        assert "cannot exceed" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_assessment_result", "audit_log"]) == before


class TestRecordBatchResultsDepth:
    # No ledger effect: one row per student in educlaw_assessment_result only.

    def test_batch_rows_stored_exactly(self, graded):
        conn = graded["conn"]
        payload = json.dumps([
            {"student_id": graded["student_id"], "points_earned": "90"},
            {"student_id": graded["student2_id"], "points_earned": "75",
             "comments": "Late work", "is_late": 1},
        ])
        r = call_action(GRADING_ACTIONS["edu-record-batch-results"], conn, ns(
            assessment_id=graded["assessment_id"], results=payload, graded_by="teacher-1",
        ))
        assert is_ok(r)
        assert r["saved"] == 2
        assert r["errors"] == []
        first = _one(conn, "educlaw_assessment_result",
                     assessment_id=graded["assessment_id"], student_id=graded["student_id"])
        assert first["points_earned"] == "90"
        assert Decimal(str(first["points_earned"])) == Decimal("90")
        assert first["is_late"] == 0
        second = _one(conn, "educlaw_assessment_result",
                      assessment_id=graded["assessment_id"], student_id=graded["student2_id"])
        assert second["points_earned"] == "75"
        assert Decimal(str(second["points_earned"])) == Decimal("75")
        assert second["is_late"] == 1
        assert second["comments"] == "Late work"

    def test_batch_refusal_missing_results_writes_nothing(self, graded):
        conn = graded["conn"]
        before = _snapshot(conn, ["educlaw_assessment_result", "audit_log"])
        r = call_action(GRADING_ACTIONS["edu-record-batch-results"], conn, ns(
            assessment_id=graded["assessment_id"], results=None, graded_by="teacher-1",
        ))
        assert is_error(r)
        assert "--results is required" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_assessment_result", "audit_log"]) == before


class TestSubmitGradesDepth:
    # No ledger effect: submission flips enrollments to completed, stores exact
    # TEXT percentages/points, writes grade_posted notifications, and refreshes
    # the stored GPA. No journal legs exist on this path.

    def test_submission_updates_enrollment_notification_and_gpa(self, graded):
        conn = graded["conn"]
        solo = {k: graded[k] for k in ("conn", "company_id", "section_id", "student_id",
                                       "enrollment_id", "assessment_id")}
        r = call_action(GRADING_ACTIONS["edu-record-assessment-result"], conn, ns(
            assessment_id=solo["assessment_id"], student_id=solo["student_id"],
            points_earned="85", graded_by="teacher-1", is_exempt=None,
            is_late=None, comments="", enrollment_id=None,
        ))
        assert is_ok(r)
        before_enrollment = _one(conn, "educlaw_course_enrollment", id=solo["enrollment_id"])
        assert before_enrollment["enrollment_status"] == "enrolled"
        r = call_action(GRADING_ACTIONS["edu-submit-grades"], conn, ns(
            section_id=solo["section_id"], submitted_by="registrar",
        ))
        assert is_ok(r)
        assert r["grades_submitted"] >= 1
        after = _one(conn, "educlaw_course_enrollment", id=solo["enrollment_id"])
        assert before_enrollment["final_letter_grade"] != after["final_letter_grade"]
        assert after["enrollment_status"] == "completed"
        assert after["final_letter_grade"] == "B"
        assert after["final_grade_points"] == "3.0"
        assert Decimal(str(after["final_grade_points"])) == Decimal("3.0")
        assert after["final_percentage"] == "85.00"
        assert Decimal(str(after["final_percentage"])) == Decimal("85.00")
        assert after["grade_submitted_by"] == "registrar"
        assert after["is_grade_submitted"] == 1
        notifs = _rows(conn, "educlaw_notification",
                       reference_id=solo["enrollment_id"], notification_type="grade_posted")
        assert len(notifs) == 1
        assert notifs[0]["recipient_id"] == solo["student_id"]
        assert notifs[0]["title"] == "Grade Posted"
        assert "B (85.00%)" in notifs[0]["message"]
        student = _one(conn, "educlaw_student", id=solo["student_id"])
        assert student["cumulative_gpa"] == "3.00"
        assert Decimal(str(student["cumulative_gpa"])) == Decimal("3.00")

    def test_submit_refusal_missing_submitter_changes_nothing(self, graded):
        conn = graded["conn"]
        before = _snapshot(conn, ["educlaw_course_enrollment", "educlaw_notification",
                                  "educlaw_student", "audit_log"])
        r = call_action(GRADING_ACTIONS["edu-submit-grades"], conn, ns(
            section_id=graded["section_id"], submitted_by=None,
        ))
        assert is_error(r)
        assert "--submitted-by is required" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_course_enrollment", "educlaw_notification",
                                "educlaw_student", "audit_log"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE + FERPA DATA ACCESS (stored-row writes, no ledger)
# ══════════════════════════════════════════════════════════════════════════════

class TestRecordBatchAttendanceDepth:
    # No ledger effect: inserts educlaw_student_attendance rows only.

    def test_batch_attendance_rows_stored_exactly(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        payload = json.dumps([
            {"student_id": depth["student_id"], "attendance_status": "present"},
            {"student_id": depth["student2_id"], "attendance_status": "absent"},
        ])
        r = call_action(ATTENDANCE_ACTIONS["edu-record-batch-attendance"], conn, ns(
            attendance_date="2025-09-02", company_id=cid, records=payload,
            section_id=depth["section_id"], marked_by="teacher-1", source=None,
        ))
        assert is_ok(r)
        assert r["saved"] == 2
        assert r["errors"] == []
        present = _one(conn, "educlaw_student_attendance", student_id=depth["student_id"])
        assert present["attendance_date"] == "2025-09-02"
        assert present["attendance_status"] == "present"
        assert present["section_id"] == depth["section_id"]
        assert present["marked_by"] == "teacher-1"
        assert present["source"] == "manual"
        assert present["company_id"] == cid
        absent = _one(conn, "educlaw_student_attendance", student_id=depth["student2_id"])
        assert absent["attendance_status"] == "absent"
        assert absent["attendance_date"] == "2025-09-02"

    def test_batch_attendance_refusal_missing_records(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        before = _snapshot(conn, ["educlaw_student_attendance", "audit_log"])
        r = call_action(ATTENDANCE_ACTIONS["edu-record-batch-attendance"], conn, ns(
            attendance_date="2025-09-02", company_id=cid, records=None,
            section_id=depth["section_id"], marked_by="teacher-1", source=None,
        ))
        assert is_error(r)
        assert "--records is required" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_student_attendance", "audit_log"]) == before


class TestRecordDataAccessDepth:
    # No ledger effect: appends one educlaw_data_access_log row (FERPA trail).

    def test_access_log_row_stored_exactly(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        r = call_action(STUDENTS_ACTIONS["edu-record-data-access"], conn, ns(
            student_id=depth["student_id"], data_category="grades",
            access_type="view", access_reason="Parent conference",
            user_id="admin", ip_address="127.0.0.1", is_emergency_access=None,
            company_id=cid,
        ))
        assert is_ok(r)
        row = _one(conn, "educlaw_data_access_log", id=r["id"])
        assert row["user_id"] == "admin"
        assert row["student_id"] == depth["student_id"]
        assert row["data_category"] == "grades"
        assert row["access_type"] == "view"
        assert row["access_reason"] == "Parent conference"
        assert row["ip_address"] == "127.0.0.1"
        assert row["is_emergency_access"] == 0
        assert row["company_id"] == cid

    def test_access_refusal_bad_category_writes_nothing(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        before = _snapshot(conn, ["educlaw_data_access_log", "audit_log"])
        r = call_action(STUDENTS_ACTIONS["edu-record-data-access"], conn, ns(
            student_id=depth["student_id"], data_category="dreams",
            access_type="view", access_reason="Curiosity",
            user_id="admin", ip_address=None, is_emergency_access=None,
            company_id=cid,
        ))
        assert is_error(r)
        assert "--data-category must be one of" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_data_access_log", "audit_log"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# COMMUNICATIONS (stored-row writes + fan-out; no ledger anywhere here)
# ══════════════════════════════════════════════════════════════════════════════

class TestSubmitAnnouncementDepth:
    # No ledger effect: publishing flips one announcement row to published and
    # fans out notification rows (both students + guardian + employee). No
    # journal legs exist on this path.

    def test_publish_flips_row_and_fans_out(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        ann_id = _seed_draft_announcement(conn, cid)
        assert _one(conn, "educlaw_announcement", id=ann_id)["announcement_status"] == "draft"
        r = call_action(COMMUNICATIONS_ACTIONS["edu-submit-announcement"], conn, ns(
            announcement_id=ann_id, published_by="admin",
        ))
        assert is_ok(r)
        assert r["notifications_created"] == 4
        row = _one(conn, "educlaw_announcement", id=ann_id)
        assert row["announcement_status"] == "published"
        assert row["published_by"] == "admin"
        assert row["title"] == "Depth draft"
        assert row["body"] == "Depth body text"
        notifs = _rows(conn, "educlaw_notification", reference_id=ann_id)
        assert len(notifs) == 4
        assert {n["notification_type"] for n in notifs} == {"announcement"}
        assert {(n["recipient_type"], n["recipient_id"]) for n in notifs} == {
            ("student", depth["student_id"]),
            ("student", depth["student2_id"]),
            ("guardian", depth["guardian_id"]),
            ("employee", depth["employee_id"]),
        }
        assert r["notifications_created"] == len(notifs)

    def test_publish_refusal_republish_changes_nothing(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        ann_id = _seed_draft_announcement(conn, cid)
        first = call_action(COMMUNICATIONS_ACTIONS["edu-submit-announcement"], conn, ns(
            announcement_id=ann_id, published_by="admin",
        ))
        assert is_ok(first)
        before = _snapshot(conn, ["educlaw_announcement", "educlaw_notification", "audit_log"])
        r = call_action(COMMUNICATIONS_ACTIONS["edu-submit-announcement"], conn, ns(
            announcement_id=ann_id, published_by="admin",
        ))
        assert is_error(r)
        assert "already 'published'" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_announcement", "educlaw_notification", "audit_log"]) == before


class TestSubmitNotificationDepth:
    # No ledger effect: inserts exactly one educlaw_notification row.

    def test_notification_row_stored_exactly(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        r = call_action(COMMUNICATIONS_ACTIONS["edu-submit-notification"], conn, ns(
            recipient_type="student", recipient_id=depth["student_id"],
            notification_type="announcement", title="Depth title",
            message="Depth message body", company_id=cid,
            reference_type="depth-test", reference_id="depth-ref-1", sent_via=None,
        ))
        assert is_ok(r)
        row = _one(conn, "educlaw_notification", id=r["id"])
        assert row["recipient_type"] == "student"
        assert row["recipient_id"] == depth["student_id"]
        assert row["notification_type"] == "announcement"
        assert row["title"] == "Depth title"
        assert row["message"] == "Depth message body"
        assert row["reference_type"] == "depth-test"
        assert row["reference_id"] == "depth-ref-1"
        assert row["sent_via"] == "system"
        assert row["is_read"] == 0
        assert row["company_id"] == cid
        # No fan-out: exactly one row for this recipient.
        assert len(_rows(conn, "educlaw_notification", recipient_id=depth["student_id"])) == 1

    def test_notification_refusal_unknown_student_writes_nothing(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        before = _snapshot(conn, ["educlaw_notification", "audit_log"])
        r = call_action(COMMUNICATIONS_ACTIONS["edu-submit-notification"], conn, ns(
            recipient_type="student", recipient_id="no-such-student",
            notification_type="announcement", title="Depth title",
            message="Depth message body", company_id=cid,
            reference_type=None, reference_id=None, sent_via=None,
        ))
        assert is_error(r)
        assert "not found" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_notification", "audit_log"]) == before


class TestSubmitEmergencyAlertDepth:
    # No ledger effect: creates one emergency announcement row plus one
    # notification row per recipient (both students + guardian + employee).

    def test_alert_creates_announcement_and_fan_out(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        r = call_action(COMMUNICATIONS_ACTIONS["edu-submit-emergency-alert"], conn, ns(
            title="Depth closure", message="Depth closed for weather.",
            company_id=cid, sent_by="principal",
        ))
        assert is_ok(r)
        assert r["priority"] == "emergency"
        assert r["announcement_status"] == "published"
        assert r["notifications_created"] == 4
        row = _one(conn, "educlaw_announcement", id=r["announcement_id"])
        assert row["title"] == "Depth closure"
        assert row["body"] == "Depth closed for weather."
        assert row["priority"] == "emergency"
        assert row["announcement_status"] == "published"
        assert row["published_by"] == "principal"
        assert row["audience_type"] == "all"
        notifs = _rows(conn, "educlaw_notification", reference_id=r["announcement_id"])
        assert len(notifs) == 4
        assert {n["notification_type"] for n in notifs} == {"emergency"}
        assert {(n["recipient_type"], n["recipient_id"]) for n in notifs} == {
            ("student", depth["student_id"]),
            ("student", depth["student2_id"]),
            ("guardian", depth["guardian_id"]),
            ("employee", depth["employee_id"]),
        }
        assert all(n["title"] == "Depth closure" for n in notifs)

    def test_alert_refusal_missing_title_writes_nothing(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        before = _snapshot(conn, ["educlaw_announcement", "educlaw_notification", "audit_log"])
        r = call_action(COMMUNICATIONS_ACTIONS["edu-submit-emergency-alert"], conn, ns(
            title=None, message="Depth closed for weather.",
            company_id=cid, sent_by="principal",
        ))
        assert is_error(r)
        assert "--title is required" in r.get("message", "")
        assert _snapshot(conn, ["educlaw_announcement", "educlaw_notification", "audit_log"]) == before
