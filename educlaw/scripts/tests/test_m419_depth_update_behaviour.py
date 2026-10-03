"""M419 depth: behavioural tests for ten edu-update-* actions.

Each action below already had a test that proved the wrong thing: the three
covered in test_educlaw_core.py (update-student, update-room,
update-student-status) assert the response envelope only, and the other seven
are covered only by routability contract tests. The tests here prove what each
action actually does to the database: the exact row written (money as exact
TEXT strings compared through Decimal, never float), the columns and sibling
rows that must NOT have changed, and one input-validation refusal that must
leave the database byte-identical.

None of these ten handlers reaches the general ledger: each writes its own
domain row (meal eligibility writes only an audit_log row and no domain row at
all -- see the finding note on that class) and never posts journals. Every
success test says so in a comment so a later reader does not add debit/credit
assertions that cannot hold.

All dates are fixed strings, so nothing here depends on today's date.
"""
import importlib.util
import json
import os
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error

STUDENTS_ACTIONS = _load("students", _SCRIPTS_DIR).ACTIONS
ACADEMICS_ACTIONS = _load("academics", _SCRIPTS_DIR).ACTIONS
GRADING_ACTIONS = _load("grading", _SCRIPTS_DIR).ACTIONS
STAFF_ACTIONS = _load("staff", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS
CAFETERIA_ACTIONS = _load("cafeteria", _SCRIPTS_DIR).ACTIONS

_SNAPSHOT_TABLES = (
    "educlaw_student",
    "educlaw_student_applicant",
    "educlaw_guardian",
    "educlaw_grading_scale",
    "educlaw_grading_scale_entry",
    "educlaw_instructor",
    "educlaw_room",
    "educlaw_section",
    "educlaw_scholarship",
    "audit_log",
)


def _snapshot(conn):
    snap = {}
    for table in _SNAPSHOT_TABLES:
        rows = conn.execute("SELECT * FROM " + table).fetchall()
        snap[table] = sorted(json.dumps(dict(r), sort_keys=True, default=str) for r in rows)
    return snap


def _count(conn, table):
    return conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


@pytest.fixture
def env(db_path):
    conn = _helpers.get_conn(db_path)
    cid = _helpers.seed_company(conn)
    yid = _helpers.seed_academic_year(conn, cid)
    tid = _helpers.seed_academic_term(conn, cid, yid)
    pid = _helpers.seed_program(conn, cid)
    crs = _helpers.seed_course(conn, cid)
    rm = _helpers.seed_room(conn, cid)
    eid = _helpers.seed_employee(conn, cid)
    iid = _helpers.seed_instructor(conn, cid, eid)
    sec = _helpers.seed_section(conn, cid, crs, tid, instructor_id=iid, room_id=rm)
    stu = _helpers.seed_student(conn, cid)
    gid = _helpers.seed_guardian(conn, cid)
    gsid = _helpers.seed_grading_scale(conn, cid)
    r = call_action(STUDENTS_ACTIONS["edu-add-student-applicant"], conn, ns(
        company_id=cid, first_name="Jane", last_name="Depth",
        date_of_birth="2010-03-15", gender="female", email="applicant@test.com",
        phone="555-0100", address=None, grade_level="9",
        applying_for_program_id=None, applying_for_term_id=None,
        application_date="2025-07-01", documents=None, previous_school=None,
        previous_school_address=None, transfer_records=None,
        guardian_info=None, middle_name=None))
    assert is_ok(r), r
    aid = r["id"]
    s = call_action(FEES_ACTIONS["edu-add-scholarship"], conn, ns(
        student_id=stu, name="Depth Merit", discount_type="fixed",
        discount_amount="1000.00", company_id=cid, academic_term_id=None,
        applies_to_category_id=None, reason="seed", approved_by="registrar"))
    assert is_ok(s), s
    scid = s["id"]
    yield {
        "conn": conn, "company_id": cid, "year_id": yid, "term_id": tid,
        "program_id": pid, "course_id": crs, "room_id": rm,
        "employee_id": eid, "instructor_id": iid, "section_id": sec,
        "student_id": stu, "guardian_id": gid, "scale_id": gsid,
        "applicant_id": aid, "scholarship_id": scid,
    }
    conn.close()


# ---------------------------------------------------------------------------
# edu-update-grading-scale -- stored row (scale plus money-exact entries)
# ---------------------------------------------------------------------------

class TestUpdateGradingScaleDepth:
    def test_renames_scale_and_replaces_entries_with_exact_money(self, env):
        conn = env["conn"]
        gsid = env["scale_id"]
        before = conn.execute(
            "SELECT name, description, is_default, company_id "
            "FROM educlaw_grading_scale WHERE id = ?", (gsid,)).fetchone()
        before_name = before[0]
        sibling = _helpers.seed_grading_scale(conn, env["company_id"])
        sibling_before = tuple(conn.execute(
            "SELECT name, description FROM educlaw_grading_scale WHERE id = ?",
            (sibling,)).fetchone())
        entries = json.dumps([{
            "letter_grade": "A", "grade_points": "4.00",
            "min_percentage": "93.00", "max_percentage": "100.00",
            "description": "Excellent", "is_passing": 1,
            "counts_in_gpa": 1, "sort_order": 1}])
        r = call_action(GRADING_ACTIONS["edu-update-grading-scale"], conn, ns(
            scale_id=gsid, name="Renamed Scale", description="Depth desc",
            is_default=None, entries=entries))
        assert is_ok(r), r
        assert r["id"] == gsid
        row = conn.execute(
            "SELECT name, description, is_default, company_id "
            "FROM educlaw_grading_scale WHERE id = ?", (gsid,)).fetchone()
        assert tuple(row) == ("Renamed Scale", "Depth desc", before[2], env["company_id"])
        assert before_name != "Renamed Scale"
        erows = conn.execute(
            "SELECT letter_grade, grade_points, min_percentage, max_percentage, "
            "description, is_passing, counts_in_gpa, sort_order "
            "FROM educlaw_grading_scale_entry WHERE grading_scale_id = ? "
            "ORDER BY sort_order", (gsid,)).fetchall()
        assert [tuple(e) for e in erows] == [
            ("A", "4.00", "93.00", "100.00", "Excellent", 1, 1, 1)]
        assert Decimal(erows[0][1]) == Decimal("4.00")
        assert Decimal(erows[0][2]) == Decimal("93.00")
        assert Decimal(erows[0][3]) == Decimal("100.00")
        assert erows[0][1] == "4.00" and erows[0][2] == "93.00" and erows[0][3] == "100.00"
        after_sibling = tuple(conn.execute(
            "SELECT name, description FROM educlaw_grading_scale WHERE id = ?",
            (sibling,)).fetchone())
        assert after_sibling == sibling_before
        # No ledger legs: only the scale row and its entry rows move, never journals.

    def test_refuses_unknown_scale_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        count = _count(conn, "educlaw_grading_scale")
        r = call_action(GRADING_ACTIONS["edu-update-grading-scale"], conn, ns(
            scale_id="no-such-scale", name="X", description=None,
            is_default=None, entries=None))
        assert is_error(r)
        assert r["message"] == "Grading scale no-such-scale not found"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_grading_scale") == count


# ---------------------------------------------------------------------------
# edu-update-guardian -- stored row
# ---------------------------------------------------------------------------

class TestUpdateGuardianDepth:
    def test_updates_email_and_leaves_names_and_sibling_alone(self, env):
        conn = env["conn"]
        gid = env["guardian_id"]
        before = conn.execute(
            "SELECT first_name, last_name, relationship, email, phone "
            "FROM educlaw_guardian WHERE id = ?", (gid,)).fetchone()
        assert tuple(before) == ("Test", "Parent", "mother", "parent@email.com", "555-1234")
        sibling = _helpers.seed_guardian(conn, env["company_id"])
        sibling_before = tuple(conn.execute(
            "SELECT email FROM educlaw_guardian WHERE id = ?", (sibling,)).fetchone())
        r = call_action(STUDENTS_ACTIONS["edu-update-guardian"], conn, ns(
            guardian_id=gid, first_name=None, last_name=None,
            email="newparent@example.com", phone=None, alternate_phone=None,
            occupation=None, employer=None, address=None, relationship=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT first_name, last_name, full_name, relationship, email, phone "
            "FROM educlaw_guardian WHERE id = ?", (gid,)).fetchone()
        assert tuple(row) == ("Test", "Parent", "Test Parent", "mother",
                              "newparent@example.com", "555-1234")
        assert tuple(conn.execute(
            "SELECT email FROM educlaw_guardian WHERE id = ?", (sibling,)).fetchone()) == sibling_before
        # No ledger legs: only the guardian row moves, never journals.

    def test_refuses_bad_relationship_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(STUDENTS_ACTIONS["edu-update-guardian"], conn, ns(
            guardian_id=env["guardian_id"], first_name=None, last_name=None,
            email=None, phone=None, alternate_phone=None, occupation=None,
            employer=None, address=None, relationship="sibling"))
        assert is_error(r)
        assert r["message"] == ("--relationship must be one of: father, mother, "
                                "guardian, grandparent, stepparent, foster_parent, other")
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# edu-update-instructor -- stored row
# ---------------------------------------------------------------------------

class TestUpdateInstructorDepth:
    def test_updates_office_and_bio_and_leaves_load_alone(self, env):
        conn = env["conn"]
        iid = env["instructor_id"]
        before = conn.execute(
            "SELECT office_location, bio, max_teaching_load_hours, is_active "
            "FROM educlaw_instructor WHERE id = ?", (iid,)).fetchone()
        assert tuple(before) == ("", "", 0, 1)
        eid2 = _helpers.seed_employee(conn, env["company_id"])
        iid2 = _helpers.seed_instructor(conn, env["company_id"], eid2)
        sib_before = tuple(conn.execute(
            "SELECT office_location, bio FROM educlaw_instructor WHERE id = ?",
            (iid2,)).fetchone())
        r = call_action(STAFF_ACTIONS["edu-update-instructor"], conn, ns(
            instructor_id=iid, credentials=None, specializations=None,
            max_teaching_load_hours=None, office_location="Room 204",
            office_hours=None, bio="Math veteran", is_active=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT office_location, bio, max_teaching_load_hours, is_active, "
            "credentials, specializations "
            "FROM educlaw_instructor WHERE id = ?", (iid,)).fetchone()
        assert tuple(row) == ("Room 204", "Math veteran", 0, 1, "[]", "[]")
        assert tuple(conn.execute(
            "SELECT office_location, bio FROM educlaw_instructor WHERE id = ?",
            (iid2,)).fetchone()) == sib_before
        # No ledger legs: only the instructor row moves, never journals.

    def test_refuses_bad_credentials_json_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(STAFF_ACTIONS["edu-update-instructor"], conn, ns(
            instructor_id=env["instructor_id"], credentials="not-json",
            specializations=None, max_teaching_load_hours=None,
            office_location=None, office_hours=None, bio=None, is_active=None))
        assert is_error(r)
        assert r["message"] == "--credentials must be valid JSON"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# edu-update-room -- stored row
# ---------------------------------------------------------------------------

class TestUpdateRoomDepth:
    def test_updates_capacity_and_leaves_number_and_sibling_alone(self, env):
        conn = env["conn"]
        rid = env["room_id"]
        before = conn.execute(
            "SELECT room_number, building, capacity, room_type "
            "FROM educlaw_room WHERE id = ?", (rid,)).fetchone()
        assert before[2] == 30
        number, building = before[0], before[1]
        sibling = _helpers.seed_room(conn, env["company_id"])
        sib_before = tuple(conn.execute(
            "SELECT capacity FROM educlaw_room WHERE id = ?", (sibling,)).fetchone())
        r = call_action(ACADEMICS_ACTIONS["edu-update-room"], conn, ns(
            room_id=rid, room_number=None, building=None, capacity="45",
            room_type=None, facilities=None, is_active=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT room_number, building, capacity, room_type, is_active "
            "FROM educlaw_room WHERE id = ?", (rid,)).fetchone()
        assert tuple(row) == (number, building, 45, "classroom", 1)
        assert tuple(conn.execute(
            "SELECT capacity FROM educlaw_room WHERE id = ?", (sibling,)).fetchone()) == sib_before
        # No ledger legs: only the room row moves, never journals.

    def test_refuses_zero_capacity_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(ACADEMICS_ACTIONS["edu-update-room"], conn, ns(
            room_id=env["room_id"], room_number=None, building=None,
            capacity="0", room_type=None, facilities=None, is_active=None))
        assert is_error(r)
        assert r["message"] == "--capacity must be greater than 0"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT capacity FROM educlaw_room WHERE id = ?",
            (env["room_id"],)).fetchone()[0] == 30


# ---------------------------------------------------------------------------
# edu-update-scholarship -- stored row with exact money
# ---------------------------------------------------------------------------

class TestUpdateScholarshipDepth:
    def test_updates_amount_and_status_with_exact_money_strings(self, env):
        conn = env["conn"]
        scid = env["scholarship_id"]
        before = conn.execute(
            "SELECT name, discount_type, discount_amount, scholarship_status "
            "FROM educlaw_scholarship WHERE id = ?", (scid,)).fetchone()
        assert tuple(before) == ("Depth Merit", "fixed", "1000.00", "active")
        audit_before = _count(conn, "audit_log")
        r = call_action(FEES_ACTIONS["edu-update-scholarship"], conn, ns(
            scholarship_id=scid, name=None, discount_type=None,
            discount_amount="1500.50", scholarship_status="revoked",
            reason="Depth review", approved_by=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT name, discount_type, discount_amount, scholarship_status, reason "
            "FROM educlaw_scholarship WHERE id = ?", (scid,)).fetchone()
        assert tuple(row) == ("Depth Merit", "fixed", "1500.50", "revoked", "Depth review")
        assert Decimal(row[2]) == Decimal("1500.50")
        assert row[2] == "1500.50"
        assert _count(conn, "audit_log") == audit_before
        # No ledger legs and no audit row from this handler: only the
        # scholarship row moves, never journals.

    def test_refuses_bad_discount_type_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(FEES_ACTIONS["edu-update-scholarship"], conn, ns(
            scholarship_id=env["scholarship_id"], name=None,
            discount_type="bogus", discount_amount=None,
            scholarship_status=None, reason=None, approved_by=None))
        assert is_error(r)
        assert r["message"] == "--discount-type must be 'fixed' or 'percentage'"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# edu-update-section -- stored row
# ---------------------------------------------------------------------------

class TestUpdateSectionDepth:
    def test_updates_max_enrollment_and_leaves_status_and_course_alone(self, env):
        conn = env["conn"]
        sec = env["section_id"]
        before = conn.execute(
            "SELECT max_enrollment, status, course_id, academic_term_id "
            "FROM educlaw_section WHERE id = ?", (sec,)).fetchone()
        assert before[0] == 30 and before[1] == "open"
        course_id, term_id = before[2], before[3]
        r = call_action(ACADEMICS_ACTIONS["edu-update-section"], conn, ns(
            section_id=sec, section_number=None, instructor_id=None,
            room_id=None, days_of_week=None, start_time=None, end_time=None,
            max_enrollment="28", waitlist_enabled=None, waitlist_max=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT max_enrollment, status, course_id, academic_term_id, "
            "section_number FROM educlaw_section WHERE id = ?", (sec,)).fetchone()
        assert tuple(row) == (28, "open", course_id, term_id, "001")
        # No ledger legs: only the section row moves, never journals.

    def test_refuses_zero_max_enrollment_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(ACADEMICS_ACTIONS["edu-update-section"], conn, ns(
            section_id=env["section_id"], section_number=None,
            instructor_id=None, room_id=None, days_of_week=None,
            start_time=None, end_time=None, max_enrollment="0",
            waitlist_enabled=None, waitlist_max=None))
        assert is_error(r)
        assert r["message"] == "--max-enrollment must be greater than 0"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT max_enrollment FROM educlaw_section WHERE id = ?",
            (env["section_id"],)).fetchone()[0] == 30


# ---------------------------------------------------------------------------
# edu-update-student -- stored row
# ---------------------------------------------------------------------------

class TestUpdateStudentDepth:
    def test_updates_email_and_leaves_identity_and_sibling_alone(self, env):
        conn = env["conn"]
        sid = env["student_id"]
        before = conn.execute(
            "SELECT first_name, last_name, email, grade_level, status "
            "FROM educlaw_student WHERE id = ?", (sid,)).fetchone()
        assert tuple(before) == ("Test", "Student", "test@school.edu", "10", "active")
        sib = _helpers.seed_student(conn, env["company_id"])
        sib_before = tuple(conn.execute(
            "SELECT email FROM educlaw_student WHERE id = ?", (sib,)).fetchone())
        r = call_action(STUDENTS_ACTIONS["edu-update-student"], conn, ns(
            student_id=sid, email="newemail@school.edu",
            first_name=None, last_name=None, middle_name=None,
            date_of_birth=None, gender=None, phone=None, address=None,
            grade_level=None, emergency_contact=None, current_program_id=None,
            cohort_year=None, enrollment_date=None, registration_hold=None,
            directory_info_opt_out=None, academic_standing=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT first_name, last_name, full_name, email, grade_level, status "
            "FROM educlaw_student WHERE id = ?", (sid,)).fetchone()
        assert tuple(row) == ("Test", "Student", "Test Student",
                              "newemail@school.edu", "10", "active")
        assert tuple(conn.execute(
            "SELECT email FROM educlaw_student WHERE id = ?", (sib,)).fetchone()) == sib_before
        # No ledger legs: only the student row moves, never journals.

    def test_refuses_bad_standing_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(STUDENTS_ACTIONS["edu-update-student"], conn, ns(
            student_id=env["student_id"], email=None,
            first_name=None, last_name=None, middle_name=None,
            date_of_birth=None, gender=None, phone=None, address=None,
            grade_level=None, emergency_contact=None, current_program_id=None,
            cohort_year=None, enrollment_date=None, registration_hold=None,
            directory_info_opt_out=None, academic_standing="bogus"))
        assert is_error(r)
        assert r["message"] == ("--academic-standing must be one of: good, deans_list, "
                                "honor_roll, probation, suspension")
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# edu-update-student-applicant -- stored row
# ---------------------------------------------------------------------------

class TestUpdateStudentApplicantDepth:
    def test_updates_email_and_leaves_name_status_alone(self, env):
        conn = env["conn"]
        aid = env["applicant_id"]
        before = conn.execute(
            "SELECT first_name, last_name, email, phone, status "
            "FROM educlaw_student_applicant WHERE id = ?", (aid,)).fetchone()
        assert tuple(before) == ("Jane", "Depth", "applicant@test.com", "555-0100", "applied")
        r = call_action(STUDENTS_ACTIONS["edu-update-student-applicant"], conn, ns(
            applicant_id=aid, first_name=None, middle_name=None, last_name=None,
            email="jane.new@test.com", phone=None, previous_school=None,
            previous_school_address=None, transfer_records=None,
            acceptance_deadline=None, review_notes=None, date_of_birth=None,
            gender=None, address=None, guardian_info=None, documents=None,
            applying_for_program_id=None, applying_for_term_id=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT first_name, last_name, email, phone, status "
            "FROM educlaw_student_applicant WHERE id = ?", (aid,)).fetchone()
        assert tuple(row) == ("Jane", "Depth", "jane.new@test.com", "555-0100", "applied")
        # No ledger legs: only the applicant row moves, never journals.

    def test_refuses_bad_gender_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(STUDENTS_ACTIONS["edu-update-student-applicant"], conn, ns(
            applicant_id=env["applicant_id"], first_name=None, middle_name=None,
            last_name=None, email=None, phone=None, previous_school=None,
            previous_school_address=None, transfer_records=None,
            acceptance_deadline=None, review_notes=None, date_of_birth=None,
            gender="bogus", address=None, guardian_info=None, documents=None,
            applying_for_program_id=None, applying_for_term_id=None))
        assert is_error(r)
        assert r["message"] == "--gender must be one of: male, female, non_binary, prefer_not_to_say"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# edu-update-student-meal-eligibility -- audit-only (finding, no stored row)
# ---------------------------------------------------------------------------

class TestUpdateStudentMealEligibilityDepth:
    # FINDING documented, not fixed: this action returns ok but persists no
    # eligibility state on any domain row. The student row is byte-identical
    # afterwards; the only new row is the audit trail entry. A reader looking
    # for where eligibility is stored will not find it outside audit_log.
    def test_writes_only_audit_row_and_leaves_student_identical(self, env):
        conn = env["conn"]
        sid = env["student_id"]
        before_student = dict(conn.execute(
            "SELECT * FROM educlaw_student WHERE id = ?", (sid,)).fetchone())
        audit_before = _count(conn, "audit_log")
        others_before = _snapshot(conn)
        r = call_action(CAFETERIA_ACTIONS["edu-update-student-meal-eligibility"],
                        conn, ns(student_id=sid, eligibility="free"))
        assert is_ok(r), r
        assert r["eligibility"] == "free"
        after_student = dict(conn.execute(
            "SELECT * FROM educlaw_student WHERE id = ?", (sid,)).fetchone())
        assert after_student == before_student
        assert _count(conn, "audit_log") == audit_before + 1
        trail = conn.execute(
            "SELECT new_values FROM audit_log "
            "WHERE action = 'edu-update-student-meal-eligibility' AND entity_id = ?",
            (sid,)).fetchall()
        assert len(trail) == 1
        assert json.loads(trail[0][0]) == {"meal_eligibility": "free"}
        for table in _SNAPSHOT_TABLES:
            if table == "audit_log":
                continue
            assert _snapshot(conn)[table] == others_before[table]
        # No ledger legs: only one audit_log row is added, never journals.

    def test_refuses_bad_eligibility_and_writes_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(CAFETERIA_ACTIONS["edu-update-student-meal-eligibility"],
                        conn, ns(student_id=env["student_id"], eligibility="bogus"))
        assert is_error(r)
        assert r["message"] == "--eligibility must be one of: free, reduced, paid"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# edu-update-student-status -- stored row (status flip)
# ---------------------------------------------------------------------------

class TestUpdateStudentStatusDepth:
    def test_suspends_active_student_and_leaves_email_alone(self, env):
        conn = env["conn"]
        sid = env["student_id"]
        before = conn.execute(
            "SELECT status, email FROM educlaw_student WHERE id = ?", (sid,)).fetchone()
        assert tuple(before) == ("active", "test@school.edu")
        r = call_action(STUDENTS_ACTIONS["edu-update-student-status"], conn, ns(
            student_id=sid, student_status="suspended", reason="Depth review"))
        assert is_ok(r), r
        assert r["old_status"] == "active"
        assert r["student_status"] == "suspended"
        row = conn.execute(
            "SELECT status, email FROM educlaw_student WHERE id = ?", (sid,)).fetchone()
        assert tuple(row) == ("suspended", "test@school.edu")
        # No ledger legs: only the student status flag moves, never journals.

    def test_refuses_bad_status_and_flips_nothing(self, env):
        conn = env["conn"]
        before = _snapshot(conn)
        r = call_action(STUDENTS_ACTIONS["edu-update-student-status"], conn, ns(
            student_id=env["student_id"], student_status="bogus", reason="Depth review"))
        assert is_error(r)
        assert r["message"] == ("--student-status must be one of: active, graduated, "
                                "withdrawn, suspended, expelled, transferred, inactive")
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT status FROM educlaw_student WHERE id = ?",
            (env["student_id"],)).fetchone()[0] == "active"
