"""M411 depth evidence for 12 educlaw actions.

Each action below already had a shape-only or routability-only test (see
test_educlaw_core.py and test_phase9.py: they assert response keys, not
database effects). The tests here assert WHAT EACH ACTION DOES to the database:

- happy path: the exact row (or rows) written, read back with PyPika queries
  built through erpclaw_lib.query on a connection from
  erpclaw_lib.db.get_connection, compared with exact values (money as Decimal
  strings, never float, never approximate);
- what did NOT change: a pre-existing sibling row is byte-identical after;
- refusal: one input-validation refusal per action; the error message names the
  real rule, and the snapshotted tables are byte-identical afterwards
  (a refusal that half-writes is worse than no refusal).

Ledger note (applies to every test in this file): none of these 12 actions
reaches the ledger. They write reference/state rows only, so there are no
debit/credit legs to assert and nothing to balance; each test says so inline so
a later reader does not add a balancing assertion that cannot hold.

Known defects documented, not fixed (see CHANGES.md):
- edu-add-announcement cannot succeed on this tree -- its INSERT passes NULL
  for NOT NULL columns, so every call fails and writes nothing;
- edu-add-assessment writes its assessment row but its auto-created result
  stubs always die on NOT NULL points_earned (swallowed IntegrityError), so
  result_stubs_created is always 0.
Their tests pin that real behaviour.
"""
import importlib.util
import os
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(directory, "%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
init_all_tables = _helpers.init_all_tables
call_action = _helpers.call_action
ns = _helpers.ns
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
seed_guardian = _helpers.seed_guardian
seed_grading_scale = _helpers.seed_grading_scale
seed_fee_category = _helpers.seed_fee_category
seed_enrollment = _helpers.seed_enrollment

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Field, P, Q, Table

ACADEMICS_ACTIONS = _load("academics", _SCRIPTS_DIR).ACTIONS
ACTIVITIES_ACTIONS = _load("activities", _SCRIPTS_DIR).ACTIONS
COMMUNICATIONS_ACTIONS = _load("communications", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS
GRADING_ACTIONS = _load("grading", _SCRIPTS_DIR).ACTIONS
STUDENTS_ACTIONS = _load("students", _SCRIPTS_DIR).ACTIONS


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "m411.sqlite")
    init_all_tables(path)
    c = get_connection(path)
    yield c
    c.close()


@pytest.fixture
def company(conn):
    return conn, seed_company(conn)


@pytest.fixture
def school(conn):
    """Company + year + term + program + course + room + instructor + section + student."""
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    pid = seed_program(conn, cid)
    crs = seed_course(conn, cid)
    room = seed_room(conn, cid)
    emp = seed_employee(conn, cid)
    inst = seed_instructor(conn, cid, emp)
    sec = seed_section(conn, cid, crs, tid, instructor_id=inst, room_id=room)
    stu = seed_student(conn, cid)
    return {
        "conn": conn, "company_id": cid, "year_id": yid, "term_id": tid,
        "program_id": pid, "course_id": crs, "room_id": room,
        "employee_id": emp, "instructor_id": inst,
        "section_id": sec, "student_id": stu,
    }


# ── Read-back helpers (rows, not envelopes) ──────────────────────────────────

def _one(conn, table, row_id):
    t = Table(table)
    row = conn.execute(
        Q.from_(t).select(t.star).where(t.id == P()).get_sql(),
        (row_id,)).fetchone()
    assert row is not None, "expected row %s in %s" % (row_id, table)
    return dict(row)


def _children(conn, table, column, value):
    t = Table(table)
    rows = conn.execute(
        Q.from_(t).select(t.star).where(getattr(t, column) == P())
        .orderby(t.id).get_sql(), (value,)).fetchall()
    return [dict(r) for r in rows]


def _dump(conn, table):
    t = Table(table)
    rows = conn.execute(
        Q.from_(t).select(t.star).orderby(t.id).get_sql()).fetchall()
    return [dict(r) for r in rows]


def _snap(conn, *tables):
    return {t: _dump(conn, t) for t in tables}


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-academic-year — stored row in educlaw_academic_year
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddAcademicYear:
    def test_writes_row_with_exact_values(self, company):
        conn, cid = company
        before_id = seed_academic_year(conn, cid)
        before_row = _one(conn, "educlaw_academic_year", before_id)
        # No ledger effect: reference row only, never posts to gl_entry.
        r = call_action(ACADEMICS_ACTIONS["edu-add-academic-year"], conn, ns(
            company_id=cid, name="2030-2031",
            start_date="2030-08-01", end_date="2031-07-31",
            is_active=None,
        ))
        assert is_ok(r)
        row = _one(conn, "educlaw_academic_year", r["id"])
        assert row["name"] == "2030-2031"
        assert row["start_date"] == "2030-08-01"
        assert row["end_date"] == "2031-07-31"
        assert row["company_id"] == cid
        assert row["is_active"] == 1
        assert _one(conn, "educlaw_academic_year", before_id) == before_row

    def test_refusal_start_after_end_writes_nothing(self, company):
        conn, cid = company
        before = _snap(conn, "educlaw_academic_year", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(ACADEMICS_ACTIONS["edu-add-academic-year"], conn, ns(
            company_id=cid, name="Bad Year",
            start_date="2031-07-31", end_date="2030-08-01",
            is_active=None,
        ))
        assert is_error(r)
        assert "start_date must be before end_date" in r["message"]
        assert _snap(conn, "educlaw_academic_year", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-academic-term — stored row in educlaw_academic_term
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddAcademicTerm:
    def test_writes_row_with_exact_values(self, company):
        conn, cid = company
        yid = seed_academic_year(conn, cid)
        # No ledger effect: reference row only, never posts to gl_entry.
        r = call_action(ACADEMICS_ACTIONS["edu-add-academic-term"], conn, ns(
            company_id=cid, academic_year_id=yid, name="Spring 2026",
            term_type="semester", start_date="2026-01-15", end_date="2026-05-15",
            enrollment_start_date=None, enrollment_end_date=None,
            grade_submission_deadline=None,
        ))
        assert is_ok(r)
        row = _one(conn, "educlaw_academic_term", r["id"])
        assert row["name"] == "Spring 2026"
        assert row["term_type"] == "semester"
        assert row["academic_year_id"] == yid
        assert row["start_date"] == "2026-01-15"
        assert row["end_date"] == "2026-05-15"
        assert row["status"] == "setup"
        assert row["company_id"] == cid

    def test_refusal_bad_term_type_writes_nothing(self, company):
        conn, cid = company
        yid = seed_academic_year(conn, cid)
        before = _snap(conn, "educlaw_academic_term", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(ACADEMICS_ACTIONS["edu-add-academic-term"], conn, ns(
            company_id=cid, academic_year_id=yid, name="Bogus",
            term_type="epoch", start_date="2026-01-15", end_date="2026-05-15",
            enrollment_start_date=None, enrollment_end_date=None,
            grade_submission_deadline=None,
        ))
        assert is_error(r)
        assert "--term-type must be one of:" in r["message"]
        assert _snap(conn, "educlaw_academic_term", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-activate-section — state change draft -> open on educlaw_section
# ══════════════════════════════════════════════════════════════════════════════

class TestM411ActivateSection:
    def test_moves_draft_to_open_and_touches_nothing_else(self, school):
        s = school
        conn = s["conn"]
        draft = seed_section(conn, s["company_id"], s["course_id"], s["term_id"],
                             instructor_id=s["instructor_id"], room_id=s["room_id"],
                             status="draft")
        assert _one(conn, "educlaw_section", draft)["status"] == "draft"
        control = _one(conn, "educlaw_section", s["section_id"])
        # No ledger effect: status transition only, never posts to gl_entry.
        r = call_action(ACADEMICS_ACTIONS["edu-activate-section"], conn, ns(
            section_id=draft,
        ))
        assert is_ok(r)
        assert r["old_status"] == "draft"
        assert r["section_status"] == "open"
        after = _one(conn, "educlaw_section", draft)
        assert after["status"] == "open"
        assert after["instructor_id"] == s["instructor_id"]
        assert after["room_id"] == s["room_id"]
        assert after["current_enrollment"] == 0
        assert _one(conn, "educlaw_section", s["section_id"]) == control

    def test_refusal_open_section_writes_nothing(self, school):
        s = school
        conn = s["conn"]
        before = _snap(conn, "educlaw_section", "audit_log")
        before_row = _one(conn, "educlaw_section", s["section_id"])
        assert before_row["status"] == "open"
        # No ledger effect: refused transition writes nothing, nothing to balance.
        r = call_action(ACADEMICS_ACTIONS["edu-activate-section"], conn, ns(
            section_id=s["section_id"],
        ))
        assert is_error(r)
        assert "Cannot open section from status 'open'" in r["message"]
        assert _one(conn, "educlaw_section", s["section_id"]) == before_row
        assert _snap(conn, "educlaw_section", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-activity-participation-report — read-model over stored rows, no writes
# ══════════════════════════════════════════════════════════════════════════════

class TestM411ActivityParticipationReport:
    def test_computes_counts_from_stored_rows_and_writes_nothing(self, school):
        s = school
        conn = s["conn"]
        a1 = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="M411 Chess", company_id=s["company_id"],
            activity_type="club", instructor_id=None, description="boards",
            min_gpa=None, max_enrollment=None, season=None, school_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(a1)
        a2 = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="M411 Swim", company_id=s["company_id"],
            activity_type="sport", instructor_id=None, description="laps",
            min_gpa=None, max_enrollment=None, season=None, school_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(a2)
        e1 = call_action(ACTIVITIES_ACTIONS["edu-enroll-student-activity"], conn, ns(
            activity_id=a1["id"], student_id=s["student_id"],
            limit=50, offset=0,
        ))
        assert is_ok(e1)
        before = _snap(conn, "educlaw_activity", "educlaw_activity_enrollment",
                       "audit_log")
        # No ledger effect: pure read-model, never posts to gl_entry.
        r = call_action(
            ACTIVITIES_ACTIONS["edu-activity-participation-report"], conn, ns(
                company_id=s["company_id"], limit=50, offset=0,
            ))
        assert is_ok(r)
        assert r["total_activities"] == 2
        assert r["total_enrollments"] == 1
        assert r["by_type"]["club"] == {"count": 1, "total_enrolled": 1}
        assert r["by_type"]["sport"] == {"count": 1, "total_enrolled": 0}
        by_id = {a["id"]: a for a in r["activities"]}
        assert by_id[a1["id"]]["active_enrollments"] == 1
        assert by_id[a2["id"]]["active_enrollments"] == 0
        assert _snap(conn, "educlaw_activity", "educlaw_activity_enrollment",
                     "audit_log") == before

    def test_refusal_missing_company_writes_nothing(self, school):
        s = school
        conn = s["conn"]
        before = _snap(conn, "educlaw_activity", "educlaw_activity_enrollment",
                       "audit_log")
        # No ledger effect: validation fails before any read, nothing to balance.
        r = call_action(
            ACTIVITIES_ACTIONS["edu-activity-participation-report"], conn, ns(
                company_id=None, limit=50, offset=0,
            ))
        assert is_error(r)
        assert "--company-id is required" in r["message"]
        assert _snap(conn, "educlaw_activity", "educlaw_activity_enrollment",
                     "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-announcement — KNOWN DEFECT: valid input always fails, writes nothing
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddAnnouncement:
    def test_valid_input_fails_on_not_null_and_writes_nothing(self, company):
        # KNOWN DEFECT (deliberately not fixed): add_announcement passes NULL
        # for NOT NULL columns (audience_filter, published_by, publish_date,
        # expiry_date), so the INSERT always raises and the handler returns the
        # IntegrityError text. Expected: one draft row. Actual: error, zero rows.
        # No ledger effect: nothing is ever written, so nothing to balance.
        conn, cid = company
        r = call_action(COMMUNICATIONS_ACTIONS["edu-add-announcement"], conn, ns(
            title="Snow Day", body="School closed.", company_id=cid,
            priority=None, audience_type=None, audience_filter=None,
            publish_date=None, expiry_date=None,
        ))
        assert is_error(r)
        assert "NOT NULL constraint failed" in r["message"]
        assert "audience_filter" in r["message"]
        assert _dump(conn, "educlaw_announcement") == []

    def test_refusal_missing_title_writes_nothing(self, company):
        conn, cid = company
        before = _snap(conn, "educlaw_announcement", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(COMMUNICATIONS_ACTIONS["edu-add-announcement"], conn, ns(
            title=None, body="No title.", company_id=cid,
            priority=None, audience_type=None, audience_filter=None,
            publish_date=None, expiry_date=None,
        ))
        assert is_error(r)
        assert "--title is required" in r["message"]
        assert _snap(conn, "educlaw_announcement", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-assessment — stored row in educlaw_assessment; stubs never persist (defect)
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddAssessment:
    def test_writes_assessment_but_stub_creation_silently_fails(self, school):
        # KNOWN DEFECT (deliberately not fixed): add_assessment auto-creates
        # one educlaw_assessment_result stub per enrolled student, but the stub
        # INSERT passes points_earned=None into a NOT NULL column, so every
        # stub raises IntegrityError, which the handler swallows
        # (a bare IntegrityError catch that skips the stub). Expected: 1 stub
        # enrollment below. Actual: result_stubs_created is 0 and zero stub
        # rows exist, while the assessment row itself is written exactly.
        # No ledger effect: assessment rows only, never posts to gl_entry.
        s = school
        conn = s["conn"]
        gs = seed_grading_scale(conn, s["company_id"])
        plan = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=s["section_id"], grading_scale_id=gs,
            company_id=s["company_id"],
            categories='[{"name":"Tests","weight_percentage":"100"}]',
        ))
        assert is_ok(plan)
        cat = _children(conn, "educlaw_assessment_category",
                        "assessment_plan_id", plan["id"])[0]
        seed_enrollment(conn, s["student_id"], s["section_id"],
                        s["company_id"])
        r = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
            plan_id=plan["id"], category_id=cat["id"],
            name="Midterm", max_points="100", due_date="2025-10-15",
            description=None, allows_extra_credit=None, sort_order=None,
            company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert r["result_stubs_created"] == 0
        row = _one(conn, "educlaw_assessment", r["id"])
        assert row["name"] == "Midterm"
        assert row["max_points"] == str(Decimal("100"))
        assert Decimal(row["max_points"]) == Decimal("100")
        assert row["assessment_plan_id"] == plan["id"]
        assert row["category_id"] == cat["id"]
        stubs = _children(conn, "educlaw_assessment_result",
                          "assessment_id", r["id"])
        assert stubs == []

    def test_refusal_zero_max_points_writes_nothing(self, school):
        s = school
        conn = s["conn"]
        gs = seed_grading_scale(conn, s["company_id"])
        plan = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=s["section_id"], grading_scale_id=gs,
            company_id=s["company_id"],
            categories='[{"name":"Tests","weight_percentage":"100"}]',
        ))
        assert is_ok(plan)
        cat = _children(conn, "educlaw_assessment_category",
                        "assessment_plan_id", plan["id"])[0]
        before = _snap(conn, "educlaw_assessment", "educlaw_assessment_result",
                       "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
            plan_id=plan["id"], category_id=cat["id"],
            name="Zero", max_points="0", due_date="2025-10-15",
            description=None, allows_extra_credit=None, sort_order=None,
            company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "--max-points must be greater than 0" in r["message"]
        assert _snap(conn, "educlaw_assessment", "educlaw_assessment_result",
                     "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-assessment-plan — stored plan plus category rows, weights sum to 100
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddAssessmentPlan:
    def test_writes_plan_and_exact_category_weights(self, school):
        s = school
        conn = s["conn"]
        gs = seed_grading_scale(conn, s["company_id"])
        # No ledger effect: plan rows only, never posts to gl_entry.
        r = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=s["section_id"], grading_scale_id=gs,
            company_id=s["company_id"],
            categories='[{"name":"Homework","weight_percentage":"30"},'
                       '{"name":"Tests","weight_percentage":"70"}]',
        ))
        assert is_ok(r)
        assert r["category_count"] == 2
        plan = _one(conn, "educlaw_assessment_plan", r["id"])
        assert plan["section_id"] == s["section_id"]
        assert plan["grading_scale_id"] == gs
        assert plan["company_id"] == s["company_id"]
        cats = _children(conn, "educlaw_assessment_category",
                         "assessment_plan_id", r["id"])
        assert len(cats) == 2
        by_name = {c["name"]: c for c in cats}
        assert by_name["Homework"]["weight_percentage"] == str(Decimal("30"))
        assert by_name["Tests"]["weight_percentage"] == str(Decimal("70"))
        total = sum(Decimal(c["weight_percentage"]) for c in cats)
        assert total == Decimal("100")

    def test_refusal_weights_not_100_writes_nothing(self, school):
        s = school
        conn = s["conn"]
        gs = seed_grading_scale(conn, s["company_id"])
        before = _snap(conn, "educlaw_assessment_plan",
                       "educlaw_assessment_category", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=s["section_id"], grading_scale_id=gs,
            company_id=s["company_id"],
            categories='[{"name":"Homework","weight_percentage":"30"},'
                       '{"name":"Tests","weight_percentage":"60"}]',
        ))
        assert is_error(r)
        assert "Category weights must sum to 100%" in r["message"]
        assert _snap(conn, "educlaw_assessment_plan",
                     "educlaw_assessment_category", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-consent-record — stored row in educlaw_consent_record
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddConsentRecord:
    def test_writes_row_with_exact_values(self, school):
        s = school
        conn = s["conn"]
        # No ledger effect: consent row only, never posts to gl_entry.
        r = call_action(STUDENTS_ACTIONS["edu-add-consent-record"], conn, ns(
            student_id=s["student_id"], consent_type="ferpa_directory",
            consent_date="2025-09-01", granted_by="Test Parent",
            granted_by_relationship="parent",
            expiry_date=None, third_party_name=None, purpose=None,
            company_id=s["company_id"],
        ))
        assert is_ok(r)
        row = _one(conn, "educlaw_consent_record", r["id"])
        assert row["student_id"] == s["student_id"]
        assert row["consent_type"] == "ferpa_directory"
        assert row["consent_date"] == "2025-09-01"
        assert row["granted_by"] == "Test Parent"
        assert row["granted_by_relationship"] == "parent"
        assert row["is_revoked"] == 0
        assert row["company_id"] == s["company_id"]

    def test_refusal_bad_consent_type_writes_nothing(self, school):
        s = school
        conn = s["conn"]
        before = _snap(conn, "educlaw_consent_record", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(STUDENTS_ACTIONS["edu-add-consent-record"], conn, ns(
            student_id=s["student_id"], consent_type="mind-meld",
            consent_date="2025-09-01", granted_by="Test Parent",
            granted_by_relationship="parent",
            expiry_date=None, third_party_name=None, purpose=None,
            company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "--consent-type must be one of:" in r["message"]
        assert _snap(conn, "educlaw_consent_record", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-fee-category — stored row in educlaw_fee_category
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddFeeCategory:
    def test_writes_row_with_exact_values(self, company):
        conn, cid = company
        control_id = seed_fee_category(conn, cid)
        control = _one(conn, "educlaw_fee_category", control_id)
        # No ledger effect: reference row only, never posts to gl_entry.
        r = call_action(FEES_ACTIONS["edu-add-fee-category"], conn, ns(
            company_id=cid, name="M411 Lab Fee", code=None, description="Labs",
            revenue_account_id=None, is_active=None,
        ))
        assert is_ok(r)
        row = _one(conn, "educlaw_fee_category", r["id"])
        assert row["name"] == "M411 Lab Fee"
        assert row["description"] == "Labs"
        assert row["company_id"] == cid
        assert row["is_active"] == 1
        assert _one(conn, "educlaw_fee_category", control_id) == control

    def test_refusal_missing_name_writes_nothing(self, company):
        conn, cid = company
        before = _snap(conn, "educlaw_fee_category", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(FEES_ACTIONS["edu-add-fee-category"], conn, ns(
            company_id=cid, name=None, code=None, description=None,
            revenue_account_id=None, is_active=None,
        ))
        assert is_error(r)
        assert "--name is required" in r["message"]
        assert _snap(conn, "educlaw_fee_category", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-fee-structure — stored structure plus items, money totals balance
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddFeeStructure:
    def test_writes_structure_and_items_with_exact_money(self, school):
        import json as _json
        import uuid as _uuid
        s = school
        conn = s["conn"]
        cat_tuition = seed_fee_category(conn, s["company_id"])
        cat_transport = str(_uuid.uuid4())
        conn.execute(
            "INSERT INTO educlaw_fee_category "
            "(id, name, description, is_active, company_id, created_by) "
            "VALUES (?, 'M411 Transport', 'Buses', 1, ?, '')",
            (cat_transport, s["company_id"]))
        conn.commit()
        # No ledger effect: a fee structure only PRICES charges; posting to
        # gl_entry happens (if at all) when an invoice is raised, so there are
        # no debit/credit legs to assert here -- only exact stored money text.
        r = call_action(FEES_ACTIONS["edu-add-fee-structure"], conn, ns(
            name="M411 Grade 10 Fees", company_id=s["company_id"],
            program_id=None, academic_term_id=None, grade_level=None,
            items=_json.dumps([
                {"fee_category_id": cat_tuition, "amount": "3000"},
                {"fee_category_id": cat_transport, "amount": "2000"},
            ]),
        ))
        assert is_ok(r)
        assert r["total_amount"] == str(Decimal("5000"))
        assert r["item_count"] == 2
        head = _one(conn, "educlaw_fee_structure", r["id"])
        assert head["name"] == "M411 Grade 10 Fees"
        assert head["total_amount"] == str(Decimal("5000"))
        assert head["company_id"] == s["company_id"]
        items = _children(conn, "educlaw_fee_structure_item",
                          "fee_structure_id", r["id"])
        assert len(items) == 2
        by_cat = {i["fee_category_id"]: i for i in items}
        assert by_cat[cat_tuition]["amount"] == str(Decimal("3000"))
        assert by_cat[cat_transport]["amount"] == str(Decimal("2000"))
        assert sum(Decimal(i["amount"]) for i in items) == Decimal(head["total_amount"])

    def test_refusal_negative_amount_writes_nothing(self, school):
        import json as _json
        s = school
        conn = s["conn"]
        cat = seed_fee_category(conn, s["company_id"])
        before = _snap(conn, "educlaw_fee_structure",
                       "educlaw_fee_structure_item", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(FEES_ACTIONS["edu-add-fee-structure"], conn, ns(
            name="Bad Fees", company_id=s["company_id"],
            program_id=None, academic_term_id=None, grade_level=None,
            items=_json.dumps([{"fee_category_id": cat, "amount": "-5"}]),
        ))
        assert is_error(r)
        assert "Amount must be >= 0" in r["message"]
        assert _snap(conn, "educlaw_fee_structure",
                     "educlaw_fee_structure_item", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-grading-scale — stored scale plus entry rows, decimals as text
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddGradingScale:
    def test_writes_scale_and_entries_with_exact_values(self, company):
        conn, cid = company
        # No ledger effect: reference rows only, never posts to gl_entry.
        r = call_action(GRADING_ACTIONS["edu-add-grading-scale"], conn, ns(
            company_id=cid, name="M411 Standard", description="A-F scale",
            entries='[{"letter_grade":"A","grade_points":"4.0",'
                    '"min_percentage":"90","max_percentage":"100"}]',
            is_default=None,
        ))
        assert is_ok(r)
        assert r["entry_count"] == 1
        scale = _one(conn, "educlaw_grading_scale", r["id"])
        assert scale["name"] == "M411 Standard"
        assert scale["company_id"] == cid
        entries = _children(conn, "educlaw_grading_scale_entry",
                            "grading_scale_id", r["id"])
        assert len(entries) == 1
        assert entries[0]["letter_grade"] == "A"
        assert entries[0]["grade_points"] == str(Decimal("4.0"))
        assert entries[0]["min_percentage"] == str(Decimal("90"))
        assert entries[0]["max_percentage"] == str(Decimal("100"))
        assert Decimal(entries[0]["grade_points"]) == Decimal("4.0")

    def test_refusal_empty_entries_writes_nothing(self, company):
        conn, cid = company
        before = _snap(conn, "educlaw_grading_scale",
                       "educlaw_grading_scale_entry", "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(GRADING_ACTIONS["edu-add-grading-scale"], conn, ns(
            company_id=cid, name="Empty", description=None,
            entries='[]', is_default=None,
        ))
        assert is_error(r)
        assert "--entries must be a non-empty JSON array" in r["message"]
        assert _snap(conn, "educlaw_grading_scale",
                     "educlaw_grading_scale_entry", "audit_log") == before


# ══════════════════════════════════════════════════════════════════════════════
# edu-add-guardian — stored row in educlaw_guardian
# ══════════════════════════════════════════════════════════════════════════════

class TestM411AddGuardian:
    def test_writes_row_with_exact_values(self, company):
        conn, cid = company
        control_id = seed_guardian(conn, cid)
        control = _one(conn, "educlaw_guardian", control_id)
        # No ledger effect: person row only, never posts to gl_entry.
        r = call_action(STUDENTS_ACTIONS["edu-add-guardian"], conn, ns(
            company_id=cid, first_name="John", last_name="Parent",
            relationship="father", email="john@test.com", phone="555-9876",
            alternate_phone=None, address=None, occupation=None, employer=None,
            middle_name=None,
        ))
        assert is_ok(r)
        assert r["full_name"] == "John Parent"
        row = _one(conn, "educlaw_guardian", r["id"])
        assert row["first_name"] == "John"
        assert row["last_name"] == "Parent"
        assert row["full_name"] == "John Parent"
        assert row["relationship"] == "father"
        assert row["email"] == "john@test.com"
        assert row["phone"] == "555-9876"
        assert row["company_id"] == cid
        assert _one(conn, "educlaw_guardian", control_id) == control

    def test_refusal_bad_relationship_writes_nothing(self, company):
        conn, cid = company
        before = _snap(conn, "educlaw_guardian", "educlaw_student_guardian",
                       "audit_log")
        # No ledger effect: validation fails before any write, nothing to balance.
        r = call_action(STUDENTS_ACTIONS["edu-add-guardian"], conn, ns(
            company_id=cid, first_name="Zed", last_name="Zed",
            relationship="nemesis", email=None, phone="555-0000",
            alternate_phone=None, address=None, occupation=None, employer=None,
            middle_name=None,
        ))
        assert is_error(r)
        assert "--relationship must be one of:" in r["message"]
        assert _snap(conn, "educlaw_guardian", "educlaw_student_guardian",
                     "audit_log") == before
