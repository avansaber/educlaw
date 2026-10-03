"""M415 depth: behavioural tests for 12 read/report actions.

Each action below already had a test that proved only response shape
(keys present, status ok) or bare routability. The tests here prove what
the action actually observes in the database:

  - seed rows with exact values through the owning actions (or direct
    inserts where no owning action exists for the seed),
  - call the read/report action,
  - compare the response against rows read back from the database,
  - snapshot the touched tables before/after and assert byte-identical
    content (reads must not write; refusals must not half-write).

Ledger note (applies to all 12): none of these actions posts to the
ledger. Eleven are pure reads; ``edu-housing-waitlist`` in add mode
writes one ``educlaw_notification`` row, which is a queue entry, not a
journal entry. There are no debit/credit legs to assert, so each test
says so once and asserts stored rows instead.

Money note: monetary values are TEXT in storage and ``Decimal`` in
assertions, compared as exact strings. Never float, never rounded.

No production file is touched by this module.
"""
import importlib.util
import os
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
seed_student = _helpers.seed_student
seed_guardian = _helpers.seed_guardian
seed_grading_scale = _helpers.seed_grading_scale
seed_fee_category = _helpers.seed_fee_category
seed_employee = _helpers.seed_employee
seed_instructor = _helpers.seed_instructor
seed_section = _helpers.seed_section
seed_enrollment = _helpers.seed_enrollment

STUDENTS_ACTIONS = _load("students", _SCRIPTS_DIR).ACTIONS
ATTENDANCE_ACTIONS = _load("attendance", _SCRIPTS_DIR).ACTIONS
STAFF_ACTIONS = _load("staff", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS
GRADING_ACTIONS = _load("grading", _SCRIPTS_DIR).ACTIONS
HOUSING_ACTIONS = _load("housing", _SCRIPTS_DIR).ACTIONS
ACTIVITIES_ACTIONS = _load("activities", _SCRIPTS_DIR).ACTIONS
TRANSPORT_ACTIONS = _load("transport", _SCRIPTS_DIR).ACTIONS

import uuid


# ── local fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yield conn, cid
    conn.close()


@pytest.fixture
def full(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    pid = seed_program(conn, cid)
    crs = seed_course(conn, cid)
    rid = seed_room(conn, cid)
    eid = seed_employee(conn, cid)
    iid = seed_instructor(conn, cid, eid)
    sec = seed_section(conn, cid, crs, tid, instructor_id=iid, room_id=rid)
    stu = seed_student(conn, cid)
    yield {
        "conn": conn, "company_id": cid, "year_id": yid, "term_id": tid,
        "program_id": pid, "course_id": crs, "room_id": rid,
        "employee_id": eid, "instructor_id": iid,
        "section_id": sec, "student_id": stu,
    }
    conn.close()


# ── snapshot helpers ─────────────────────────────────────────────────────────

def _snapshot(conn, tables):
    """Return {table: sorted row tuples} for explicit table names only.

    No catalog introspection: callers name the tables the action under
    test can plausibly touch.
    """
    snap = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        snap[table] = sorted(repr(sorted(dict(r).items())) for r in rows)
    return snap


def _row_by_id(conn, table, row_id):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    assert row is not None, f"expected row {row_id} in {table}"
    return dict(row)


def _link_guardian(conn, student_id, guardian_id):
    link_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact)
           VALUES (?, ?, ?, 'mother', 1, 1, 1, 1, 1)""",
        (link_id, student_id, guardian_id)
    )
    conn.commit()
    return link_id


# ══════════════════════════════════════════════════════════════════════════════
# 1. edu-get-section-attendance — stored-row assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestGetSectionAttendanceDepth:
    TABLES = ["educlaw_student_attendance", "educlaw_student", "educlaw_section"]

    def test_reflects_seeded_attendance_rows(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        stu2 = seed_student(conn, cid)
        for sid, status in ((s["student_id"], "present"), (stu2, "absent")):
            r = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], conn, ns(
                student_id=sid, attendance_date="2025-09-02",
                attendance_status=status, company_id=cid,
                section_id=s["section_id"], late_minutes=None,
                comments=None, marked_by=None, source=None,
            ))
            assert is_ok(r)
        before = _snapshot(conn, self.TABLES)
        r = call_action(ATTENDANCE_ACTIONS["edu-get-section-attendance"], conn, ns(
            section_id=s["section_id"], attendance_date="2025-09-02",
            attendance_date_from=None, attendance_date_to=None, limit=200,
        ))
        assert is_ok(r)
        assert r["section_id"] == s["section_id"]
        assert r["count"] == 2
        by_student = {rec["student_id"]: rec for rec in r["attendance_records"]}
        assert by_student[s["student_id"]]["attendance_status"] == "present"
        assert by_student[stu2]["attendance_status"] == "absent"
        for rec in r["attendance_records"]:
            assert rec["attendance_date"] == "2025-09-02"
            stored = _row_by_id(conn, "educlaw_student_attendance", rec["id"])
            assert rec["student_id"] == stored["student_id"]
            assert rec["attendance_status"] == stored["attendance_status"]
            assert rec["attendance_date"] == stored["attendance_date"]
        # A date with no records is a truthful empty, not an error.
        r_empty = call_action(ATTENDANCE_ACTIONS["edu-get-section-attendance"], conn, ns(
            section_id=s["section_id"], attendance_date="2025-09-03",
            attendance_date_from=None, attendance_date_to=None, limit=200,
        ))
        assert is_ok(r_empty)
        assert r_empty["count"] == 0
        assert r_empty["attendance_records"] == []
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_missing_section_id_writes_nothing(self, full):
        s, conn = full, full["conn"]
        before = _snapshot(conn, self.TABLES)
        r = call_action(ATTENDANCE_ACTIONS["edu-get-section-attendance"], conn, ns(
            section_id=None, attendance_date=None,
            attendance_date_from=None, attendance_date_to=None, limit=200,
        ))
        assert is_error(r)
        assert "section-id" in r["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 2. edu-get-student-account — stored-row assertions (money as Decimal text)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetStudentAccountDepth:
    TABLES = ["educlaw_student", "educlaw_scholarship", "sales_invoice", "customer"]

    def _seed_customer_with_invoices(self, conn, cid, student_id):
        cust_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO customer (id, name, email, company_id) VALUES (?, ?, ?, ?)",
            (cust_id, "Test Student", "test@school.edu", cid)
        )
        conn.execute(
            "UPDATE educlaw_student SET customer_id = ? WHERE id = ?",
            (cust_id, student_id)
        )
        for total in ("5000", "2500"):
            inv_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO sales_invoice
                   (id, naming_series, customer_id, total_amount, status, company_id)
                   VALUES (?, ?, ?, ?, 'draft', ?)""",
                (inv_id, f"INV-{inv_id[:6]}", cust_id, total, cid)
            )
        conn.commit()
        return cust_id

    def test_account_reports_zero_balance_and_real_scholarship(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        sch = call_action(FEES_ACTIONS["edu-add-scholarship"], conn, ns(
            student_id=s["student_id"], name="Merit Award",
            discount_type="fixed", discount_amount="1000",
            company_id=cid, academic_term_id=None,
            applies_to_category_id=None, reason=None, approved_by=None,
        ))
        assert is_ok(sch)
        cust_id = self._seed_customer_with_invoices(conn, cid, s["student_id"])
        before = _snapshot(conn, self.TABLES)
        r = call_action(FEES_ACTIONS["edu-get-student-account"], conn, ns(
            student_id=s["student_id"], company_id=cid,
        ))
        assert is_ok(r)
        assert r["student_id"] == s["student_id"]
        assert r["customer_id"] == cust_id
        # Money is text: exact Decimal comparison, no float.
        assert {inv["id"] for inv in r["invoices"]} == set(
            dict(row)["id"] for row in conn.execute(
                "SELECT id FROM sales_invoice WHERE customer_id = ?", (cust_id,)
            ).fetchall()
        )
        for inv in r["invoices"]:
            assert inv["status"] == "draft"
            assert inv["grand_total"] == "0"
            assert inv["outstanding_amount"] == "0"
            assert "name" not in inv
            assert '"name"' not in inv
        assert Decimal(str(r["outstanding_balance"])) == Decimal("0")
        assert str(r["outstanding_balance"]) == "0"
        assert r["payments"] == []
        assert len(r["active_scholarships"]) == 1
        got = r["active_scholarships"][0]
        stored = _row_by_id(conn, "educlaw_scholarship", got["id"])
        assert got["name"] == stored["name"] == "Merit Award"
        assert Decimal(str(got["discount_amount"])) == Decimal("1000")
        assert str(stored["discount_amount"]) == "1000"
        assert got["scholarship_status"] == stored["scholarship_status"] == "active"
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_unknown_student_writes_nothing(self, full):
        s, conn = full, full["conn"]
        before = _snapshot(conn, self.TABLES)
        r = call_action(FEES_ACTIONS["edu-get-student-account"], conn, ns(
            student_id="no-such-student", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "not found" in r["message"].lower()
        r2 = call_action(FEES_ACTIONS["edu-get-student-account"], conn, ns(
            student_id=None, company_id=s["company_id"],
        ))
        assert is_error(r2)
        assert "student-id" in r2["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 3. edu-get-teaching-load — stored-row assertions (money-free; credits text)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetTeachingLoadDepth:
    TABLES = ["educlaw_section", "educlaw_course", "educlaw_instructor"]

    def test_load_sums_credits_from_stored_sections(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        crs2 = seed_course(conn, cid, code="ENG202")
        conn.execute("UPDATE educlaw_course SET credit_hours = '4' WHERE id = ?", (crs2,))
        conn.commit()
        sec2 = seed_section(conn, cid, crs2, s["term_id"],
                            instructor_id=s["instructor_id"], room_id=s["room_id"])
        conn.execute(
            "UPDATE educlaw_instructor SET max_teaching_load_hours = 6 WHERE id = ?",
            (s["instructor_id"],)
        )
        conn.commit()
        before = _snapshot(conn, self.TABLES)
        r = call_action(STAFF_ACTIONS["edu-get-teaching-load"], conn, ns(
            instructor_id=s["instructor_id"], academic_term_id=s["term_id"],
        ))
        assert is_ok(r)
        assert r["instructor_id"] == s["instructor_id"]
        assert r["academic_term_id"] == s["term_id"]
        assert len(r["sections"]) == 2
        by_section = {row["id"]: row for row in r["sections"]}
        assert set(by_section) == {s["section_id"], sec2}
        assert Decimal(str(by_section[s["section_id"]]["credit_hours"])) == Decimal("3")
        assert Decimal(str(by_section[sec2]["credit_hours"])) == Decimal("4")
        assert by_section[s["section_id"]]["course_code"] == "MATH101"
        assert by_section[sec2]["course_code"] == "ENG202"
        for sec_id, row in by_section.items():
            stored_sec = _row_by_id(conn, "educlaw_section", sec_id)
            assert row["section_number"] == stored_sec["section_number"]
        assert Decimal(str(r["total_credit_hours"])) == Decimal("7")
        assert str(r["total_credit_hours"]) == "7"
        assert r["max_teaching_load_hours"] == 6
        assert r["exceeds_limit"] is True
        # A term with no sections is a truthful zero, not an error.
        tid2 = seed_academic_term(conn, cid, s["year_id"])
        r_empty = call_action(STAFF_ACTIONS["edu-get-teaching-load"], conn, ns(
            instructor_id=s["instructor_id"], academic_term_id=tid2,
        ))
        assert is_ok(r_empty)
        assert r_empty["sections"] == []
        assert str(r_empty["total_credit_hours"]) == "0"
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_unknown_instructor_writes_nothing(self, full):
        s, conn = full, full["conn"]
        before = _snapshot(conn, self.TABLES)
        r = call_action(STAFF_ACTIONS["edu-get-teaching-load"], conn, ns(
            instructor_id="no-such-instructor", academic_term_id=s["term_id"],
        ))
        assert is_error(r)
        assert "not found" in r["message"].lower()
        r2 = call_action(STAFF_ACTIONS["edu-get-teaching-load"], conn, ns(
            instructor_id=s["instructor_id"], academic_term_id=None,
        ))
        assert is_error(r2)
        assert "academic-term-id" in r2["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 4. edu-get-truancy-report — stored-row assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestGetTruancyReportDepth:
    TABLES = ["educlaw_student", "educlaw_student_attendance",
              "educlaw_student_guardian", "educlaw_guardian"]

    def _record(self, conn, cid, student_id, att_date, status):
        r = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], conn, ns(
            student_id=student_id, attendance_date=att_date,
            attendance_status=status, company_id=cid,
            section_id=None, late_minutes=None, comments=None,
            marked_by=None, source=None,
        ))
        assert is_ok(r)

    def test_truant_set_matches_attendance_math(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        stu2 = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        _link_guardian(conn, s["student_id"], gid)
        for day, status in (("2025-09-01", "present"), ("2025-09-02", "present"),
                            ("2025-09-03", "absent"), ("2025-09-04", "absent")):
            self._record(conn, cid, s["student_id"], day, status)
        for day in ("2025-09-01", "2025-09-02", "2025-09-03", "2025-09-04"):
            self._record(conn, cid, stu2, day, "present")
        before = _snapshot(conn, self.TABLES)
        r = call_action(ATTENDANCE_ACTIONS["edu-get-truancy-report"], conn, ns(
            company_id=cid, threshold=90, grade_level=None,
        ))
        assert is_ok(r)
        assert r["threshold_pct"] == 90
        assert r["truant_student_count"] == 1
        truant = r["truant_students"][0]
        assert truant["student_id"] == s["student_id"]
        assert truant["total_days"] == 4
        assert truant["present"] == 2
        assert truant["absent"] == 2
        assert truant["attendance_percentage"] == 50.0
        assert truant["grade_level"] == "10"
        assert stu2 not in {t["student_id"] for t in r["truant_students"]}
        assert truant["guardians"][0]["full_name"] == "Test Parent"
        # A permissive threshold clears the list truthfully.
        r_clear = call_action(ATTENDANCE_ACTIONS["edu-get-truancy-report"], conn, ns(
            company_id=cid, threshold=50, grade_level=None,
        ))
        assert is_ok(r_clear)
        assert r_clear["truant_student_count"] == 0
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_missing_company_writes_nothing(self, full):
        s, conn = full, full["conn"]
        before = _snapshot(conn, self.TABLES)
        r = call_action(ATTENDANCE_ACTIONS["edu-get-truancy-report"], conn, ns(
            company_id=None, threshold=None, grade_level=None,
        ))
        assert is_error(r)
        assert "company-id" in r["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 5. edu-housing-occupancy-report — stored-row assertions (money as text)
# ══════════════════════════════════════════════════════════════════════════════

class TestHousingOccupancyReportDepth:
    TABLES = ["educlaw_housing_unit", "educlaw_housing_assignment"]

    def _add_unit(self, conn, cid, building, room, capacity, amount):
        r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building=building, room_number=room, company_id=cid,
            room_type="double", unit_type=None, capacity=capacity,
            amount=amount, floor="1", description="",
            limit=50, offset=0,
        ))
        assert is_ok(r)
        return r["id"]

    def test_building_math_matches_units_and_assignments(self, setup):
        conn, cid = setup
        stu = seed_student(conn, cid)
        unit_a = self._add_unit(conn, cid, "Maple Hall", "101", 2, "700")
        unit_b = self._add_unit(conn, cid, "Maple Hall", "102", 3, "900")
        assign = call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=stu, room_id=unit_a, housing_unit_id=None,
            academic_year_id="2025-2026", academic_year=None,
            term_type=None, start_date="2025-08-20", end_date="2026-05-15",
            meal_plan="standard", limit=50, offset=0,
        ))
        assert is_ok(assign)
        before = _snapshot(conn, self.TABLES)
        r = call_action(HOUSING_ACTIONS["edu-housing-occupancy-report"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["company_id"] == cid
        assert len(r["buildings"]) == 1
        hall = r["buildings"][0]
        assert hall["building_name"] == "Maple Hall"
        assert hall["unit_count"] == 2
        assert hall["total_capacity"] == 5
        assert hall["occupied"] == 1
        assert hall["available"] == 4
        assert hall["occupancy_rate"] == 20.0
        assert r["total_capacity"] == 5
        assert r["total_occupied"] == 1
        assert r["total_available"] == 4
        assert r["overall_occupancy_rate"] == 20.0
        # Money is text: the stored monthly rates are exact Decimal strings.
        assert str(_row_by_id(conn, "educlaw_housing_unit", unit_a)["monthly_rate"]) == "700"
        assert str(_row_by_id(conn, "educlaw_housing_unit", unit_b)["monthly_rate"]) == "900"
        assert Decimal(str(_row_by_id(conn, "educlaw_housing_unit", unit_a)["monthly_rate"])) == Decimal("700")
        # The assignment the report counted is the one just created.
        rows = conn.execute(
            "SELECT * FROM educlaw_housing_assignment WHERE housing_unit_id = ? AND status = 'active'",
            (unit_a,)
        ).fetchall()
        assert len(rows) == 1
        assert dict(rows[0])["student_id"] == stu
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_missing_company_writes_nothing(self, setup):
        conn, _cid = setup
        before = _snapshot(conn, self.TABLES)
        r = call_action(HOUSING_ACTIONS["edu-housing-waitlist"], conn, ns(
            company_id=None, student_id=None, academic_year=None,
            academic_year_id=None, limit=50, offset=0,
        ))
        assert is_error(r)
        assert "company-id" in r["message"].lower()
        r2 = call_action(HOUSING_ACTIONS["edu-housing-occupancy-report"], conn, ns(
            company_id=None, limit=50, offset=0,
        ))
        assert is_error(r2)
        assert "company-id" in r2["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 6. edu-housing-waitlist — stored-row assertions (add mode WRITES one row)
# ══════════════════════════════════════════════════════════════════════════════

class TestHousingWaitlistDepth:
    TABLES = ["educlaw_notification", "educlaw_student"]

    def test_add_mode_stores_exact_notification_row(self, setup):
        conn, cid = setup
        stu = seed_student(conn, cid)
        before = _snapshot(conn, self.TABLES)
        r = call_action(HOUSING_ACTIONS["edu-housing-waitlist"], conn, ns(
            student_id=stu, company_id=cid, academic_year=None,
            academic_year_id="2025-2026", limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["student_id"] == stu
        assert r["academic_year"] == "2025-2026"
        assert r["waitlist_status"] == "waiting"
        after = _snapshot(conn, self.TABLES)
        assert len(after["educlaw_notification"]) == len(before["educlaw_notification"]) + 1
        assert after["educlaw_student"] == before["educlaw_student"]
        stored = conn.execute(
            "SELECT * FROM educlaw_notification WHERE recipient_id = ? AND notification_type = 'housing_waitlist'",
            (stu,)
        ).fetchall()
        assert len(stored) == 1
        note = dict(stored[0])
        assert note["recipient_type"] == "student"
        assert note["title"] == "Housing Waitlist Request"
        assert note["reference_type"] == "housing_waitlist"
        assert note["reference_id"] == "2025-2026"
        assert note["company_id"] == cid
        # Ledger: the write is a notification queue row, not a journal
        # entry; no debit/credit legs exist.

    def test_list_mode_reflects_waitlist_and_writes_nothing(self, setup):
        conn, cid = setup
        stu = seed_student(conn, cid)
        add = call_action(HOUSING_ACTIONS["edu-housing-waitlist"], conn, ns(
            student_id=stu, company_id=cid, academic_year=None,
            academic_year_id="2025-2026", limit=50, offset=0,
        ))
        assert is_ok(add)
        before = _snapshot(conn, self.TABLES)
        r = call_action(HOUSING_ACTIONS["edu-housing-waitlist"], conn, ns(
            student_id=None, company_id=cid, academic_year=None,
            academic_year_id=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 1
        entry = r["waitlist"][0]
        assert entry["student_id"] == stu
        assert entry["student_name"] == "Test Student"
        assert entry["academic_year"] == "2025-2026"
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_missing_year_adds_no_row(self, setup):
        conn, cid = setup
        stu = seed_student(conn, cid)
        before = _snapshot(conn, self.TABLES)
        r = call_action(HOUSING_ACTIONS["edu-housing-waitlist"], conn, ns(
            student_id=stu, company_id=cid, academic_year=None,
            academic_year_id=None, limit=50, offset=0,
        ))
        assert is_error(r)
        assert "academic-year" in r["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 7. edu-list-activity-roster — stored-row assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestListActivityRosterDepth:
    TABLES = ["educlaw_activity", "educlaw_activity_enrollment", "educlaw_student"]

    def test_roster_matches_enrollment_rows_exactly(self, setup):
        conn, cid = setup
        stu2 = seed_student(conn, cid)
        stu1 = seed_student(conn, cid)
        act = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Chess Club", company_id=cid, activity_type="club",
            school_id=None, instructor_id=None, description=None,
            min_gpa=None, max_enrollment=None, season=None,
        ))
        assert is_ok(act)
        activity_id = act["id"]
        enrolled_ids = set()
        for sid in (stu1, stu2):
            e = call_action(ACTIVITIES_ACTIONS["edu-enroll-student-activity"], conn, ns(
                activity_id=activity_id, student_id=sid,
            ))
            assert is_ok(e)
            enrolled_ids.add(e["id"])
        before = _snapshot(conn, self.TABLES)
        r = call_action(ACTIVITIES_ACTIONS["edu-list-activity-roster"], conn, ns(
            activity_id=activity_id,
        ))
        assert is_ok(r)
        assert r["activity_id"] == activity_id
        assert r["activity_name"] == "Chess Club"
        assert r["activity_type"] == "club"
        assert r["count"] == 2
        assert {row["student_id"] for row in r["roster"]} == {stu1, stu2}
        assert {row["enrollment_id"] for row in r["roster"]} == enrolled_ids
        for row in r["roster"]:
            assert row["status"] == "active"
            stored = _row_by_id(conn, "educlaw_activity_enrollment", row["enrollment_id"])
            assert stored["student_id"] == row["student_id"]
            assert stored["activity_id"] == activity_id
            assert stored["status"] == "active"
            assert row["gpa_at_enrollment"] == stored["gpa_at_enrollment"]
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_unknown_activity_writes_nothing(self, setup):
        conn, _cid = setup
        before = _snapshot(conn, self.TABLES)
        r = call_action(ACTIVITIES_ACTIONS["edu-list-activity-roster"], conn, ns(
            activity_id="no-such-activity",
        ))
        assert is_error(r)
        assert "not found" in r["message"].lower()
        r2 = call_action(ACTIVITIES_ACTIONS["edu-list-activity-roster"], conn, ns(
            activity_id=None,
        ))
        assert is_error(r2)
        assert "activity-id" in r2["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 8. edu-list-applicants — stored-row assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestListApplicantsDepth:
    TABLES = ["educlaw_student_applicant"]

    def _add(self, conn, cid, first, last, dob):
        r = call_action(STUDENTS_ACTIONS["edu-add-student-applicant"], conn, ns(
            company_id=cid, first_name=first, last_name=last,
            date_of_birth=dob, gender=None, email=None,
            phone=None, address=None, grade_level=None,
            applying_for_program_id=None, applying_for_term_id=None,
            application_date="2025-08-01", documents=None, previous_school=None,
            previous_school_address=None, transfer_records=None,
            guardian_info=None, middle_name=None,
        ))
        assert is_ok(r)
        return r["id"]

    def test_list_returns_exact_applicant_rows(self, setup):
        conn, cid = setup
        jane = self._add(conn, cid, "Jane", "Doe", "2010-03-15")
        john = self._add(conn, cid, "John", "Smith", "2009-11-30")
        # An applicant for another company must never leak across.
        # Seeded directly: edu-add-student-applicant mints a naming_series
        # with no company scope, so a second company's first applicant
        # collides on the global UNIQUE (see FINDING in CHANGES.md).
        cid2 = seed_company(conn)
        other_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO educlaw_student_applicant
               (id, naming_series, first_name, last_name, date_of_birth,
                application_date, status, company_id)
               VALUES (?, 'APP-OTHER-1', 'Other', 'Company', '2010-01-01',
                       '2025-08-01', 'applied', ?)""",
            (other_id, cid2)
        )
        conn.commit()
        before = _snapshot(conn, self.TABLES)
        r = call_action(STUDENTS_ACTIONS["edu-list-applicants"], conn, ns(
            company_id=cid, applicant_status=None,
            applying_for_term_id=None, applying_for_program_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 2
        by_id = {a["id"]: a for a in r["applicants"]}
        assert set(by_id) == {jane, john}
        assert by_id[jane]["first_name"] == "Jane"
        assert by_id[jane]["last_name"] == "Doe"
        assert by_id[jane]["date_of_birth"] == "2010-03-15"
        assert by_id[john]["first_name"] == "John"
        for app_id, row in by_id.items():
            stored = _row_by_id(conn, "educlaw_student_applicant", app_id)
            assert row["first_name"] == stored["first_name"]
            assert row["last_name"] == stored["last_name"]
            assert row["status"] == stored["status"] == "applied"
            assert row["company_id"] == cid
        # A status filter that matches nothing is a truthful empty.
        r_none = call_action(STUDENTS_ACTIONS["edu-list-applicants"], conn, ns(
            company_id=cid, applicant_status="accepted",
            applying_for_term_id=None, applying_for_program_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r_none)
        assert r_none["count"] == 0
        assert r_none["applicants"] == []
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_unmatched_filter_writes_nothing(self, setup):
        # This list action has no required parameter and therefore no
        # validating refusal path; the closest refusal-shaped behaviour is
        # a filter that matches nothing, which must stay truthful and
        # write nothing.
        conn, cid = setup
        self._add(conn, cid, "Jane", "Doe", "2010-03-15")
        before = _snapshot(conn, self.TABLES)
        r = call_action(STUDENTS_ACTIONS["edu-list-applicants"], conn, ns(
            company_id=cid, applicant_status="rejected",
            applying_for_term_id=None, applying_for_program_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 0
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 9. edu-list-assessments — stored-row assertions (money-free; points text)
# ══════════════════════════════════════════════════════════════════════════════

class TestListAssessmentsDepth:
    TABLES = ["educlaw_assessment", "educlaw_assessment_plan",
              "educlaw_assessment_category"]

    def _seed_plan_with_two(self, conn, cid, section_id):
        gs = seed_grading_scale(conn, cid)
        plan = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=section_id, grading_scale_id=gs, company_id=cid,
            categories='[{"name":"Tests","weight_percentage":"100"}]',
        ))
        assert is_ok(plan)
        cat = conn.execute(
            "SELECT id FROM educlaw_assessment_category WHERE assessment_plan_id = ?",
            (plan["id"],)
        ).fetchone()
        cat_id = cat["id"]
        mid = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
            plan_id=plan["id"], category_id=cat_id, name="Midterm",
            max_points="100", due_date="2025-10-15", description=None,
            allows_extra_credit=None, sort_order=1, company_id=cid,
        ))
        assert is_ok(mid)
        fin = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
            plan_id=plan["id"], category_id=cat_id, name="Final",
            max_points="50", due_date="2025-12-10", description=None,
            allows_extra_credit=None, sort_order=2, company_id=cid,
        ))
        assert is_ok(fin)
        return plan["id"], mid["id"], fin["id"]

    def test_list_returns_exact_assessment_rows(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        plan_id, mid_id, fin_id = self._seed_plan_with_two(conn, cid, s["section_id"])
        before = _snapshot(conn, self.TABLES)
        assess_before = _snapshot(conn, ["educlaw_assessment"])
        r = call_action(GRADING_ACTIONS["edu-list-assessments"], conn, ns(
            plan_id=plan_id, section_id=None, company_id=cid,
            category_id=None, is_published=None,
            due_date_from=None, due_date_to=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 2
        by_id = {a["id"]: a for a in r["assessments"]}
        assert set(by_id) == {mid_id, fin_id}
        assert by_id[mid_id]["name"] == "Midterm"
        assert by_id[fin_id]["name"] == "Final"
        assert Decimal(str(by_id[mid_id]["max_points"])) == Decimal("100")
        assert Decimal(str(by_id[fin_id]["max_points"])) == Decimal("50")
        assert str(by_id[mid_id]["max_points"]) == "100"
        assert by_id[mid_id]["due_date"] == "2025-10-15"
        for aid, row in by_id.items():
            stored = _row_by_id(conn, "educlaw_assessment", aid)
            assert row["name"] == stored["name"]
            assert str(row["max_points"]) == str(stored["max_points"])
            assert row["assessment_plan_id"] == plan_id
        # A plan with no assessments is a truthful empty. Plans are
        # one-per-section, so the empty plan lives on a second section.
        sec2 = seed_section(conn, cid, s["course_id"], s["term_id"],
                            instructor_id=s["instructor_id"], room_id=s["room_id"])
        gs2 = seed_grading_scale(conn, cid)
        empty_plan = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=sec2, grading_scale_id=gs2, company_id=cid,
            categories='[{"name":"Quiz","weight_percentage":"100"}]',
        ))
        assert is_ok(empty_plan)
        r_empty = call_action(GRADING_ACTIONS["edu-list-assessments"], conn, ns(
            plan_id=empty_plan["id"], section_id=None, company_id=cid,
            category_id=None, is_published=None,
            due_date_from=None, due_date_to=None, limit=50, offset=0,
        ))
        assert is_ok(r_empty)
        assert r_empty["count"] == 0
        # Ledger: pure read, no journal legs exist. (Scoped to the
        # assessment table: the empty plan created mid-test legitimately
        # adds plan/category rows, which are not this action's writes.)
        assert _snapshot(conn, ["educlaw_assessment"]) == assess_before

    def test_unmatched_filter_writes_nothing(self, full):
        # No required parameter exists on this list action, so there is no
        # validating refusal path; assert the truthful empty instead.
        s, conn, cid = full, full["conn"], full["company_id"]
        self._seed_plan_with_two(conn, cid, s["section_id"])
        before = _snapshot(conn, self.TABLES)
        r = call_action(GRADING_ACTIONS["edu-list-assessments"], conn, ns(
            plan_id="no-such-plan", section_id=None, company_id=cid,
            category_id=None, is_published=None,
            due_date_from=None, due_date_to=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 0
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 10. edu-list-bus-routes — stored-row assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestListBusRoutesDepth:
    TABLES = ["educlaw_bus_route"]

    def _add_route(self, conn, cid, number, name, driver, capacity):
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], conn, ns(
            school_id=cid, route_number=number, route_name=name,
            driver_name=driver, driver_phone=None, vehicle_id=None,
            vehicle_number=None, capacity=capacity,
            am_start_time=None, pm_start_time=None, notes=None,
        ))
        assert is_ok(r)
        return r["id"]

    def test_list_returns_exact_route_rows(self, setup):
        conn, cid = setup
        r101 = self._add_route(conn, cid, "101", "North Route", "Al Driver", 40)
        r102 = self._add_route(conn, cid, "102", "South Route", "Bo Driver", 30)
        before = _snapshot(conn, self.TABLES)
        r = call_action(TRANSPORT_ACTIONS["edu-list-bus-routes"], conn, ns(
            school_id=cid, status=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["school_id"] == cid
        assert r["count"] == 2
        by_id = {b["id"]: b for b in r["bus_routes"]}
        assert set(by_id) == {r101, r102}
        assert by_id[r101]["route_number"] == "101"
        assert by_id[r101]["route_name"] == "North Route"
        assert by_id[r101]["driver_name"] == "Al Driver"
        assert by_id[r101]["capacity"] == 40
        assert by_id[r102]["route_number"] == "102"
        assert by_id[r102]["capacity"] == 30
        for rid, row in by_id.items():
            stored = _row_by_id(conn, "educlaw_bus_route", rid)
            assert row["route_number"] == stored["route_number"]
            assert row["route_name"] == stored["route_name"]
            assert row["school_id"] == cid
            assert row["status"] == stored["status"] == "active"
        # A status filter that matches nothing is a truthful empty.
        r_none = call_action(TRANSPORT_ACTIONS["edu-list-bus-routes"], conn, ns(
            school_id=cid, status="retired", limit=50, offset=0,
        ))
        assert is_ok(r_none)
        assert r_none["count"] == 0
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_missing_school_writes_nothing(self, setup):
        conn, _cid = setup
        before = _snapshot(conn, self.TABLES)
        r = call_action(TRANSPORT_ACTIONS["edu-list-bus-routes"], conn, ns(
            school_id=None, status=None, limit=50, offset=0,
        ))
        assert is_error(r)
        assert "school-id" in r["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 11. edu-list-fee-invoices — stored-row assertions (money as Decimal text)
# ══════════════════════════════════════════════════════════════════════════════

class TestListFeeInvoicesDepth:
    TABLES = ["sales_invoice", "educlaw_student", "customer"]

    def test_known_student_returns_graceful_fallback_unchanged(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        cust_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO customer (id, name, email, company_id) VALUES (?, ?, ?, ?)",
            (cust_id, "Test Student", "test@school.edu", cid)
        )
        conn.execute(
            "UPDATE educlaw_student SET customer_id = ? WHERE id = ?",
            (cust_id, s["student_id"])
        )
        inv_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO sales_invoice
               (id, naming_series, customer_id, total_amount, status, company_id)
               VALUES (?, ?, ?, '5000', 'draft', ?)""",
            (inv_id, f"INV-{inv_id[:6]}", cust_id, cid)
        )
        conn.commit()
        before = _snapshot(conn, self.TABLES)
        r = call_action(FEES_ACTIONS["edu-list-fee-invoices"], conn, ns(
            student_id=s["student_id"], company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["student_id"] == s["student_id"]
        # The list path uses SELECT *, so the seeded row is returned with
        # exact stored values (the ORDER BY over the absent posting_date
        # column is a constant no-op, not an error).
        assert r["count"] == 1
        assert len(r["invoices"]) == 1
        got = r["invoices"][0]
        stored = _row_by_id(conn, "sales_invoice", inv_id)
        assert got["id"] == inv_id
        assert got["customer_id"] == cust_id
        assert got["naming_series"] == stored["naming_series"]
        assert got["status"] == stored["status"] == "draft"
        assert got["company_id"] == cid
        # Money is text: exact Decimal comparison, no float.
        assert Decimal(str(got["total_amount"])) == Decimal("5000")
        assert str(got["total_amount"]) == str(stored["total_amount"]) == "5000"
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_refusal_unknown_student_writes_nothing(self, full):
        s, conn = full, full["conn"]
        before = _snapshot(conn, self.TABLES)
        r = call_action(FEES_ACTIONS["edu-list-fee-invoices"], conn, ns(
            student_id="no-such-student", company_id=s["company_id"],
            limit=50, offset=0,
        ))
        assert is_error(r)
        assert "not found" in r["message"].lower()
        assert _snapshot(conn, self.TABLES) == before


# ══════════════════════════════════════════════════════════════════════════════
# 12. edu-list-grades — stored-row assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestListGradesDepth:
    TABLES = ["educlaw_course_enrollment", "educlaw_section"]

    def test_list_returns_exact_enrollment_rows(self, full):
        s, conn, cid = full, full["conn"], full["company_id"]
        stu2 = seed_student(conn, cid)
        enr1 = seed_enrollment(conn, s["student_id"], s["section_id"], cid)
        enr2 = seed_enrollment(conn, stu2, s["section_id"], cid)
        before = _snapshot(conn, self.TABLES)
        r = call_action(GRADING_ACTIONS["edu-list-grades"], conn, ns(
            student_id=None, section_id=s["section_id"],
            academic_term_id=None, company_id=cid,
            is_grade_submitted=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 2
        by_student = {g["student_id"]: g for g in r["grades"]}
        assert set(by_student) == {s["student_id"], stu2}
        assert by_student[s["student_id"]]["section_id"] == s["section_id"]
        assert by_student[s["student_id"]]["enrollment_status"] == "enrolled"
        for grade in r["grades"]:
            stored = _row_by_id(conn, "educlaw_course_enrollment", grade["id"])
            assert grade["student_id"] == stored["student_id"]
            assert grade["section_id"] == stored["section_id"]
            assert grade["enrollment_status"] == stored["enrollment_status"] == "enrolled"
        assert {g["id"] for g in r["grades"]} == {enr1, enr2}
        # A per-student filter isolates exactly one stored row.
        r_one = call_action(GRADING_ACTIONS["edu-list-grades"], conn, ns(
            student_id=stu2, section_id=None,
            academic_term_id=None, company_id=cid,
            is_grade_submitted=None, limit=50, offset=0,
        ))
        assert is_ok(r_one)
        assert r_one["count"] == 1
        assert r_one["grades"][0]["id"] == enr2
        # Ledger: pure read, no journal legs exist.
        assert _snapshot(conn, self.TABLES) == before

    def test_unmatched_filter_writes_nothing(self, full):
        # No required parameter exists on this list action, so there is no
        # validating refusal path; assert the truthful empty instead.
        s, conn, cid = full, full["conn"], full["company_id"]
        seed_enrollment(conn, s["student_id"], s["section_id"], cid)
        before = _snapshot(conn, self.TABLES)
        r = call_action(GRADING_ACTIONS["edu-list-grades"], conn, ns(
            student_id=None, section_id="no-such-section",
            academic_term_id=None, company_id=cid,
            is_grade_submitted=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 0
        assert r["grades"] == []
        assert _snapshot(conn, self.TABLES) == before
