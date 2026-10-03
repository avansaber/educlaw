"""Depth cover for twelve educlaw actions previously tested for shape/routing only.

Each action below gets a behavioural success test (the exact stored rows read
back from the database and compared as exact values) and a refusal test (the
refusal happens, the message states the true reason, and the touched tables are
byte-identical afterwards).

Actions covered:
  edu-terminate-enrollment, edu-update-academic-term, edu-update-academic-year,
  edu-update-announcement, edu-update-assessment, edu-update-assessment-plan,
  edu-update-attendance, edu-update-bus-route, edu-update-course,
  edu-update-fee-category, edu-update-fee-structure, edu-update-grade.

Ledger note (applies to every test in this file): none of these twelve actions
reaches the general ledger — they update master/transaction rows in the owning
educlaw tables only — so no ledger legs are asserted here; a later reader must
not add ledger assertions that cannot hold. Money is compared as exact Decimal
strings, never float.

Existing-test note: edu-update-academic-year, edu-update-academic-term and
edu-update-course already have shape-only tests in test_educlaw_core.py (they
assert the response is ok); the other nine are covered in-tree only by
routability contract tests. Those tests were read first and are left intact;
the tests below deepen the signal by observing the database.
"""
import importlib.util
import json
import os
import uuid
from datetime import datetime, timezone
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
seed_program = _helpers.seed_program
seed_course = _helpers.seed_course
seed_room = _helpers.seed_room
seed_employee = _helpers.seed_employee
seed_instructor = _helpers.seed_instructor
seed_section = _helpers.seed_section
seed_student = _helpers.seed_student
seed_grading_scale = _helpers.seed_grading_scale
seed_fee_category = _helpers.seed_fee_category
seed_enrollment = _helpers.seed_enrollment

ACADEMICS_ACTIONS = _load("academics", _SCRIPTS_DIR).ACTIONS
ENROLLMENT_ACTIONS = _load("enrollment", _SCRIPTS_DIR).ACTIONS
GRADING_ACTIONS = _load("grading", _SCRIPTS_DIR).ACTIONS
ATTENDANCE_ACTIONS = _load("attendance", _SCRIPTS_DIR).ACTIONS
COMMUNICATIONS_ACTIONS = _load("communications", _SCRIPTS_DIR).ACTIONS
TRANSPORT_ACTIONS = _load("transport", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def env(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    pid = seed_program(conn, cid)
    crs_id = seed_course(conn, cid)
    rm_id = seed_room(conn, cid)
    emp_id = seed_employee(conn, cid)
    inst_id = seed_instructor(conn, cid, emp_id)
    sec_id = seed_section(conn, cid, crs_id, tid, instructor_id=inst_id, room_id=rm_id)
    stu_id = seed_student(conn, cid)
    yield {
        "conn": conn, "company_id": cid, "year_id": yid, "term_id": tid,
        "program_id": pid, "course_id": crs_id, "room_id": rm_id,
        "employee_id": emp_id, "instructor_id": inst_id,
        "section_id": sec_id, "student_id": stu_id,
    }
    conn.close()


def _dump(conn, table):
    rows = conn.execute("SELECT * FROM %s" % table).fetchall()
    return sorted(tuple("" if v is None else str(v) for v in r) for r in rows)


def _snap(conn, tables):
    return {t: _dump(conn, t) for t in tables}


def _seed_draft_announcement(conn, company_id, title="Draft notice", status="draft"):
    ann_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_announcement
           (id, title, body, priority, audience_type, audience_filter,
            publish_date, expiry_date, announcement_status, published_by,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, 'Original body', 'normal', 'all', '{}',
                   '2025-09-01', '2025-12-31', ?, '',
                   ?, datetime('now'), datetime('now'), '')""",
        (ann_id, title, status, company_id)
    )
    conn.commit()
    return ann_id


def _seed_second_fee_category(conn, company_id):
    fid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_fee_category
           (id, name, description, is_active, company_id, created_by)
           VALUES (?, 'Lab Fee', 'Science lab consumables', 1, ?, '')""",
        (fid, company_id)
    )
    conn.commit()
    return fid


def _add_plan(s, categories):
    gs_id = seed_grading_scale(s["conn"], s["company_id"])
    r = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], s["conn"], ns(
        section_id=s["section_id"], grading_scale_id=gs_id,
        company_id=s["company_id"], categories=json.dumps(categories),
    ))
    assert is_ok(r), r
    return r["id"]


def _add_assessment(s, plan_id, name="Midterm", max_points="100", due_date="2025-10-15"):
    cat = s["conn"].execute(
        "SELECT id FROM educlaw_assessment_category WHERE assessment_plan_id = ?",
        (plan_id,)).fetchone()
    r = call_action(GRADING_ACTIONS["edu-add-assessment"], s["conn"], ns(
        plan_id=plan_id, category_id=cat["id"], name=name,
        max_points=max_points, due_date=due_date, description=None,
        allows_extra_credit=None, sort_order=None, company_id=s["company_id"],
    ))
    assert is_ok(r), r
    return r["id"]


def _add_fee_structure(s, fc_id, amount="5000", name="Standard Fee"):
    r = call_action(FEES_ACTIONS["edu-add-fee-structure"], s["conn"], ns(
        company_id=s["company_id"], name=name, program_id=s["program_id"],
        academic_term_id=s["term_id"],
        items=json.dumps([{"fee_category_id": fc_id, "amount": amount}]),
        grade_level=None,
    ))
    assert is_ok(r), r
    return r["id"]


def _submit_enrollment_grade(conn, enrollment_id, letter="B", points="3.0"):
    conn.execute(
        """UPDATE educlaw_course_enrollment
           SET enrollment_status = 'completed', is_grade_submitted = 1,
               final_letter_grade = ?, final_grade_points = ?
           WHERE id = ?""",
        (letter, points, enrollment_id)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# edu-terminate-enrollment
# ---------------------------------------------------------------------------

def test_terminate_enrollment_withdraws_row_and_frees_section_seat(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    eid = seed_enrollment(conn, s["student_id"], s["section_id"], s["company_id"])
    other_student = seed_student(conn, s["company_id"])
    other_eid = seed_enrollment(conn, other_student, s["section_id"], s["company_id"])
    seats_before = conn.execute(
        "SELECT current_enrollment FROM educlaw_section WHERE id = ?",
        (s["section_id"],)).fetchone()[0]
    r = call_action(ENROLLMENT_ACTIONS["edu-terminate-enrollment"], conn, ns(
        enrollment_id=eid, drop_reason="Family relocation",
    ))
    assert is_ok(r), r
    assert r["enrollment_status"] == "withdrawn"
    assert r["final_letter_grade"] == "W"
    row = conn.execute(
        "SELECT enrollment_status, drop_reason, final_letter_grade, drop_date,"
        " student_id, section_id FROM educlaw_course_enrollment WHERE id = ?",
        (eid,)).fetchone()
    assert tuple(row) == ("withdrawn", "Family relocation", "W", today,
                          s["student_id"], s["section_id"])
    assert conn.execute(
        "SELECT current_enrollment FROM educlaw_section WHERE id = ?",
        (s["section_id"],)).fetchone()[0] == seats_before - 1
    # The other enrollment in the same section is untouched.
    assert conn.execute(
        "SELECT enrollment_status FROM educlaw_course_enrollment WHERE id = ?",
        (other_eid,)).fetchone()[0] == "enrolled"


def test_terminate_enrollment_refuses_second_withdrawal_and_writes_nothing(env):
    s, conn = env, env["conn"]
    eid = seed_enrollment(conn, s["student_id"], s["section_id"], s["company_id"])
    r = call_action(ENROLLMENT_ACTIONS["edu-terminate-enrollment"], conn, ns(
        enrollment_id=eid, drop_reason="Leaving",
    ))
    assert is_ok(r), r
    before = _snap(conn, ["educlaw_course_enrollment", "educlaw_section", "audit_log"])
    r2 = call_action(ENROLLMENT_ACTIONS["edu-terminate-enrollment"], conn, ns(
        enrollment_id=eid, drop_reason="Leaving again",
    ))
    assert is_error(r2)
    assert r2["message"] == "Only enrolled courses can be withdrawn (current: withdrawn)"
    assert _snap(conn, ["educlaw_course_enrollment", "educlaw_section", "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-academic-year
# ---------------------------------------------------------------------------

def test_update_academic_year_renames_row_leaving_dates_active_flag(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r = call_action(ACADEMICS_ACTIONS["edu-update-academic-year"], conn, ns(
        year_id=s["year_id"], name="Senior Year 2026", start_date=None,
        end_date=None, is_active=None,
    ))
    assert is_ok(r), r
    assert r["updated_fields"] == ["name"]
    row = conn.execute(
        "SELECT name, start_date, end_date, is_active FROM educlaw_academic_year WHERE id = ?",
        (s["year_id"],)).fetchone()
    assert tuple(row) == ("Senior Year 2026", "2025-08-01", "2026-07-31", 1)


def test_update_academic_year_refuses_empty_update_and_writes_nothing(env):
    s, conn = env, env["conn"]
    before = _snap(conn, ["educlaw_academic_year", "audit_log"])
    r = call_action(ACADEMICS_ACTIONS["edu-update-academic-year"], conn, ns(
        year_id=s["year_id"], name=None, start_date=None, end_date=None,
        is_active=None,
    ))
    assert is_error(r)
    assert r["message"] == "No fields to update"
    assert _snap(conn, ["educlaw_academic_year", "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-academic-term
# ---------------------------------------------------------------------------

def test_update_academic_term_renames_and_opens_enrollment_leaving_dates(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r = call_action(ACADEMICS_ACTIONS["edu-update-academic-term"], conn, ns(
        term_id=s["term_id"], name="Fall Extended", term_type=None,
        start_date=None, end_date=None, enrollment_start_date=None,
        enrollment_end_date=None, grade_submission_deadline=None,
        term_status="enrollment_open",
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["name", "status"]
    row = conn.execute(
        "SELECT name, status, start_date, end_date, term_type"
        " FROM educlaw_academic_term WHERE id = ?",
        (s["term_id"],)).fetchone()
    assert tuple(row) == ("Fall Extended", "enrollment_open", "2025-08-25",
                          "2025-12-20", "semester")


def test_update_academic_term_refuses_bad_status_and_writes_nothing(env):
    s, conn = env, env["conn"]
    before = _snap(conn, ["educlaw_academic_term", "audit_log"])
    r = call_action(ACADEMICS_ACTIONS["edu-update-academic-term"], conn, ns(
        term_id=s["term_id"], name=None, term_type=None, start_date=None,
        end_date=None, enrollment_start_date=None, enrollment_end_date=None,
        grade_submission_deadline=None, term_status="eternal",
    ))
    assert is_error(r)
    assert r["message"] == ("--term-status must be one of: setup, enrollment_open, "
                            "active, grades_open, grades_finalized, closed")
    assert _snap(conn, ["educlaw_academic_term", "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-announcement
# ---------------------------------------------------------------------------

def test_update_announcement_revises_draft_leaving_status_and_body(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    ann_id = _seed_draft_announcement(conn, s["company_id"])
    r = call_action(COMMUNICATIONS_ACTIONS["edu-update-announcement"], conn, ns(
        announcement_id=ann_id, title="Revised title", body=None,
        priority="urgent", audience_type=None, audience_filter=None,
        publish_date=None, expiry_date=None,
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["priority", "title"]
    row = conn.execute(
        "SELECT title, body, priority, announcement_status FROM educlaw_announcement"
        " WHERE id = ?",
        (ann_id,)).fetchone()
    assert tuple(row) == ("Revised title", "Original body", "urgent", "draft")


def test_update_announcement_refuses_published_row_and_writes_nothing(env):
    s, conn = env, env["conn"]
    ann_id = _seed_draft_announcement(conn, s["company_id"], status="published")
    before = _snap(conn, ["educlaw_announcement", "audit_log"])
    r = call_action(COMMUNICATIONS_ACTIONS["edu-update-announcement"], conn, ns(
        announcement_id=ann_id, title="Sneaky edit", body=None,
        priority=None, audience_type=None, audience_filter=None,
        publish_date=None, expiry_date=None,
    ))
    assert is_error(r)
    assert r["message"] == ("Cannot update announcement in status 'published'. "
                            "Only draft announcements can be updated.")
    assert _snap(conn, ["educlaw_announcement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-assessment
# ---------------------------------------------------------------------------

def test_update_assessment_renames_and_repoints_leaving_due_date(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    plan_id = _add_plan(s, [{"name": "Tests", "weight_percentage": "100"}])
    aid = _add_assessment(s, plan_id)
    r = call_action(GRADING_ACTIONS["edu-update-assessment"], conn, ns(
        assessment_id=aid, name="Final Midterm", description=None,
        max_points="150", due_date=None, is_published=None,
        allows_extra_credit=None, sort_order=None,
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["max_points", "name"]
    row = conn.execute(
        "SELECT name, max_points, due_date, is_published FROM educlaw_assessment"
        " WHERE id = ?",
        (aid,)).fetchone()
    assert row["name"] == "Final Midterm"
    assert row["due_date"] == "2025-10-15"
    assert row["is_published"] == 0
    assert Decimal(str(row["max_points"])) == Decimal("150")
    assert str(row["max_points"]) == "150"


def test_update_assessment_refuses_zero_max_points_and_writes_nothing(env):
    s, conn = env, env["conn"]
    plan_id = _add_plan(s, [{"name": "Tests", "weight_percentage": "100"}])
    aid = _add_assessment(s, plan_id)
    before = _snap(conn, ["educlaw_assessment", "audit_log"])
    r = call_action(GRADING_ACTIONS["edu-update-assessment"], conn, ns(
        assessment_id=aid, name=None, description=None, max_points="0",
        due_date=None, is_published=None, allows_extra_credit=None,
        sort_order=None,
    ))
    assert is_error(r)
    assert r["message"] == "--max-points must be greater than 0"
    assert _snap(conn, ["educlaw_assessment", "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-assessment-plan
# ---------------------------------------------------------------------------

def test_update_assessment_plan_replaces_categories_with_exact_weights(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    plan_id = _add_plan(s, [{"name": "Homework", "weight_percentage": "100"}])
    scale_before = conn.execute(
        "SELECT grading_scale_id FROM educlaw_assessment_plan WHERE id = ?",
        (plan_id,)).fetchone()[0]
    r = call_action(GRADING_ACTIONS["edu-update-assessment-plan"], conn, ns(
        plan_id=plan_id, grading_scale_id=None,
        categories=json.dumps([
            {"name": "Midterm", "weight_percentage": "60"},
            {"name": "Final", "weight_percentage": "40"},
        ]),
    ))
    assert is_ok(r), r
    assert r["updated_fields"] == ["categories"]
    cats = conn.execute(
        "SELECT name, weight_percentage FROM educlaw_assessment_category"
        " WHERE assessment_plan_id = ? ORDER BY name",
        (plan_id,)).fetchall()
    assert [(c["name"], str(c["weight_percentage"])) for c in cats] == [
        ("Final", "40"), ("Midterm", "60")]
    for c in cats:
        assert Decimal(str(c["weight_percentage"])) in (Decimal("40"), Decimal("60"))
    # The old category is gone and the plan still points at the same scale.
    assert conn.execute(
        "SELECT COUNT(*) FROM educlaw_assessment_category"
        " WHERE assessment_plan_id = ? AND name = 'Homework'",
        (plan_id,)).fetchone()[0] == 0
    assert conn.execute(
        "SELECT grading_scale_id FROM educlaw_assessment_plan WHERE id = ?",
        (plan_id,)).fetchone()[0] == scale_before


def test_update_assessment_plan_refuses_unbalanced_weights_and_writes_nothing(env):
    s, conn = env, env["conn"]
    plan_id = _add_plan(s, [{"name": "Homework", "weight_percentage": "100"}])
    before = _snap(conn, ["educlaw_assessment_plan", "educlaw_assessment_category",
                          "audit_log"])
    r = call_action(GRADING_ACTIONS["edu-update-assessment-plan"], conn, ns(
        plan_id=plan_id, grading_scale_id=None,
        categories=json.dumps([
            {"name": "Midterm", "weight_percentage": "60"},
            {"name": "Final", "weight_percentage": "30"},
        ]),
    ))
    assert is_error(r)
    assert r["message"] == "Category weights must sum to 100% (got 90%)"
    assert _snap(conn, ["educlaw_assessment_plan", "educlaw_assessment_category",
                        "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-attendance
# ---------------------------------------------------------------------------

def test_update_attendance_flips_status_with_exact_minutes_and_comment(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r1 = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], conn, ns(
        student_id=s["student_id"], attendance_date="2025-09-01",
        attendance_status="absent", company_id=s["company_id"],
        section_id=None, late_minutes=None, comments=None,
        marked_by=None, source=None,
    ))
    assert is_ok(r1), r1
    att_id = r1["id"]
    r = call_action(ATTENDANCE_ACTIONS["edu-update-attendance"], conn, ns(
        attendance_id=att_id, attendance_status="present", late_minutes=5,
        comments="Arrived during homeroom", marked_by=None,
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["attendance_status", "comments",
                                           "late_minutes"]
    row = conn.execute(
        "SELECT attendance_status, late_minutes, comments, attendance_date,"
        " student_id FROM educlaw_student_attendance WHERE id = ?",
        (att_id,)).fetchone()
    assert tuple(row) == ("present", 5, "Arrived during homeroom",
                          "2025-09-01", s["student_id"])


def test_update_attendance_refuses_unknown_status_and_writes_nothing(env):
    s, conn = env, env["conn"]
    r1 = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], conn, ns(
        student_id=s["student_id"], attendance_date="2025-09-01",
        attendance_status="absent", company_id=s["company_id"],
        section_id=None, late_minutes=None, comments=None,
        marked_by=None, source=None,
    ))
    assert is_ok(r1), r1
    before = _snap(conn, ["educlaw_student_attendance"])
    r = call_action(ATTENDANCE_ACTIONS["edu-update-attendance"], conn, ns(
        attendance_id=r1["id"], attendance_status="sleeping",
        late_minutes=None, comments=None, marked_by=None,
    ))
    assert is_error(r)
    assert r["message"] == ("--attendance-status must be one of: present, absent, "
                            "tardy, excused, half_day")
    assert _snap(conn, ["educlaw_student_attendance"]) == before


# ---------------------------------------------------------------------------
# edu-update-bus-route
# ---------------------------------------------------------------------------

def test_update_bus_route_reassigns_driver_and_capacity_leaving_number(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r1 = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], conn, ns(
        school_id=s["company_id"], route_number="R-101",
        route_name="North Route", driver_name="John Smith",
        driver_phone=None, vehicle_id=None, vehicle_number=None,
        capacity=40, am_start_time=None, pm_start_time=None, notes=None,
    ))
    assert is_ok(r1), r1
    route_id = r1["id"]
    r = call_action(TRANSPORT_ACTIONS["edu-update-bus-route"], conn, ns(
        route_id=route_id, route_number=None, route_name=None,
        driver_name="Amara Diallo", driver_phone=None, vehicle_id=None,
        vehicle_number=None, capacity=48, am_start_time=None,
        pm_start_time=None, notes=None, status=None,
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["capacity", "driver_name"]
    row = conn.execute(
        "SELECT route_number, driver_name, capacity, status FROM educlaw_bus_route"
        " WHERE id = ?",
        (route_id,)).fetchone()
    assert tuple(row) == ("R-101", "Amara Diallo", 48, "active")


def test_update_bus_route_refuses_bad_status_and_writes_nothing(env):
    s, conn = env, env["conn"]
    r1 = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], conn, ns(
        school_id=s["company_id"], route_number="R-102",
        route_name=None, driver_name=None, driver_phone=None,
        vehicle_id=None, vehicle_number=None, capacity=None,
        am_start_time=None, pm_start_time=None, notes=None,
    ))
    assert is_ok(r1), r1
    before = _snap(conn, ["educlaw_bus_route"])
    r = call_action(TRANSPORT_ACTIONS["edu-update-bus-route"], conn, ns(
        route_id=r1["id"], route_number=None, route_name=None,
        driver_name=None, driver_phone=None, vehicle_id=None,
        vehicle_number=None, capacity=None, am_start_time=None,
        pm_start_time=None, notes=None, status="flying",
    ))
    assert is_error(r)
    assert r["message"] == "--status must be one of: active, inactive, suspended"
    assert _snap(conn, ["educlaw_bus_route"]) == before


# ---------------------------------------------------------------------------
# edu-update-course
# ---------------------------------------------------------------------------

def test_update_course_renames_and_recredits_leaving_code(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r = call_action(ACADEMICS_ACTIONS["edu-update-course"], conn, ns(
        course_id=s["course_id"], name="Advanced Mathematics",
        course_code=None, credit_hours="4", course_type=None,
        description=None, department_id=None, grade_level=None,
        max_enrollment=None, is_active=None, prerequisites=None,
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["credit_hours", "name"]
    row = conn.execute(
        "SELECT name, credit_hours, course_code FROM educlaw_course WHERE id = ?",
        (s["course_id"],)).fetchone()
    assert row["name"] == "Advanced Mathematics"
    assert row["course_code"] == "MATH101"
    assert Decimal(str(row["credit_hours"])) == Decimal("4")
    assert str(row["credit_hours"]) == "4"


def test_update_course_refuses_bad_type_and_writes_nothing(env):
    s, conn = env, env["conn"]
    before = _snap(conn, ["educlaw_course", "audit_log"])
    r = call_action(ACADEMICS_ACTIONS["edu-update-course"], conn, ns(
        course_id=s["course_id"], name=None, course_code=None,
        credit_hours=None, course_type="telepathy", description=None,
        department_id=None, grade_level=None, max_enrollment=None,
        is_active=None, prerequisites=None,
    ))
    assert is_error(r)
    assert r["message"] == ("--course-type must be one of: lecture, lab, seminar, "
                            "independent_study, internship, online")
    assert _snap(conn, ["educlaw_course", "audit_log"]) == before


# ---------------------------------------------------------------------------
# edu-update-fee-category
# ---------------------------------------------------------------------------

def test_update_fee_category_renames_row_leaving_company(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    fc_id = seed_fee_category(conn, s["company_id"])
    r = call_action(FEES_ACTIONS["edu-update-fee-category"], conn, ns(
        category_id=fc_id, name="Laboratory Fee",
        description="Science lab consumables", revenue_account_id=None,
        is_active=None,
    ))
    assert is_ok(r), r
    assert sorted(r["updated_fields"]) == ["description", "name"]
    row = conn.execute(
        "SELECT name, description, company_id FROM educlaw_fee_category WHERE id = ?",
        (fc_id,)).fetchone()
    assert tuple(row) == ("Laboratory Fee", "Science lab consumables",
                          s["company_id"])


def test_update_fee_category_refuses_missing_id_and_writes_nothing(env):
    s, conn = env, env["conn"]
    fc_id = seed_fee_category(conn, s["company_id"])
    before = _snap(conn, ["educlaw_fee_category"])
    r = call_action(FEES_ACTIONS["edu-update-fee-category"], conn, ns(
        category_id=None, name="Laboratory Fee", description=None,
        revenue_account_id=None, is_active=None,
    ))
    assert is_error(r)
    assert r["message"] == "--category-id is required"
    assert _snap(conn, ["educlaw_fee_category"]) == before
    assert conn.execute(
        "SELECT name FROM educlaw_fee_category WHERE id = ?",
        (fc_id,)).fetchone()[0] == "Tuition"


# ---------------------------------------------------------------------------
# edu-update-fee-structure
# ---------------------------------------------------------------------------

def test_update_fee_structure_replaces_items_and_retotals_exactly(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    fc1 = seed_fee_category(conn, s["company_id"])
    fc2 = _seed_second_fee_category(conn, s["company_id"])
    struct_id = _add_fee_structure(s, fc1)
    r = call_action(FEES_ACTIONS["edu-update-fee-structure"], conn, ns(
        structure_id=struct_id, name=None, grade_level=None,
        is_active=None,
        items=json.dumps([
            {"fee_category_id": fc1, "amount": "5000"},
            {"fee_category_id": fc2, "amount": "2500"},
        ]),
    ))
    assert is_ok(r), r
    assert r["updated_fields"] == ["items"]
    total = conn.execute(
        "SELECT total_amount, name FROM educlaw_fee_structure WHERE id = ?",
        (struct_id,)).fetchone()
    assert total["name"] == "Standard Fee"
    assert Decimal(str(total["total_amount"])) == Decimal("7500")
    assert str(total["total_amount"]) == "7500"
    items = conn.execute(
        "SELECT fee_category_id, amount FROM educlaw_fee_structure_item"
        " WHERE fee_structure_id = ? ORDER BY amount DESC",
        (struct_id,)).fetchall()
    assert [(i["fee_category_id"], str(i["amount"])) for i in items] == [
        (fc1, "5000"), (fc2, "2500")]
    for i in items:
        assert Decimal(str(i["amount"])) in (Decimal("5000"), Decimal("2500"))


def test_update_fee_structure_refuses_unknown_category_and_writes_nothing(env):
    s, conn = env, env["conn"]
    fc1 = seed_fee_category(conn, s["company_id"])
    struct_id = _add_fee_structure(s, fc1)
    before = _snap(conn, ["educlaw_fee_structure", "educlaw_fee_structure_item"])
    r = call_action(FEES_ACTIONS["edu-update-fee-structure"], conn, ns(
        structure_id=struct_id, name=None, grade_level=None,
        is_active=None,
        items=json.dumps([{"fee_category_id": "no-such-cat", "amount": "100"}]),
    ))
    assert is_error(r)
    assert r["message"] == "Fee category no-such-cat not found"
    assert _snap(conn, ["educlaw_fee_structure",
                        "educlaw_fee_structure_item"]) == before


# ---------------------------------------------------------------------------
# edu-update-grade
# ---------------------------------------------------------------------------

def test_update_grade_amends_submitted_grade_and_recalculates_gpa(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    eid = seed_enrollment(conn, s["student_id"], s["section_id"], s["company_id"])
    _submit_enrollment_grade(conn, eid, "B", "3.0")
    r = call_action(GRADING_ACTIONS["edu-update-grade"], conn, ns(
        enrollment_id=eid, new_letter_grade="A", new_grade_points="4.0",
        reason="Re-evaluation of final exam", amended_by="registrar",
        approved_by=None, user_id=None,
    ))
    assert is_ok(r), r
    assert r["old_letter_grade"] == "B"
    assert r["new_letter_grade"] == "A"
    amendment = conn.execute(
        "SELECT course_enrollment_id, old_letter_grade, new_letter_grade,"
        " old_grade_points, new_grade_points, reason, amended_by"
        " FROM educlaw_grade_amendment WHERE id = ?",
        (r["amendment_id"],)).fetchone()
    assert tuple(amendment) == (eid, "B", "A", "3.0", "4.0",
                                "Re-evaluation of final exam", "registrar")
    assert Decimal(str(amendment["old_grade_points"])) == Decimal("3.0")
    assert Decimal(str(amendment["new_grade_points"])) == Decimal("4.0")
    enrollment = conn.execute(
        "SELECT final_letter_grade, final_grade_points FROM educlaw_course_enrollment"
        " WHERE id = ?",
        (eid,)).fetchone()
    assert tuple(enrollment) == ("A", "4.0")
    # One amended 3-credit A: GPA 4.00 over 3 credits, dean's list.
    student = conn.execute(
        "SELECT cumulative_gpa, total_credits_earned, academic_standing"
        " FROM educlaw_student WHERE id = ?",
        (s["student_id"],)).fetchone()
    assert tuple(student) == ("4.00", "3", "deans_list")


def test_update_grade_refuses_unsubmitted_enrollment_and_writes_nothing(env):
    s, conn = env, env["conn"]
    eid = seed_enrollment(conn, s["student_id"], s["section_id"], s["company_id"])
    before = _snap(conn, ["educlaw_course_enrollment", "educlaw_grade_amendment",
                          "educlaw_student"])
    r = call_action(GRADING_ACTIONS["edu-update-grade"], conn, ns(
        enrollment_id=eid, new_letter_grade="A", new_grade_points="4.0",
        reason="Too early", amended_by="registrar", approved_by=None,
        user_id=None,
    ))
    assert is_error(r)
    assert r["message"] == ("Grade amendments can only be made after official "
                            "grade submission")
    assert _snap(conn, ["educlaw_course_enrollment", "educlaw_grade_amendment",
                        "educlaw_student"]) == before
