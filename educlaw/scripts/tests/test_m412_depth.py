"""M412 depth: behavioural evidence for 12 educlaw actions.

Each action below already had a shape-only or routing-only test. The tests
here assert what each action does to stored rows. Rows are read back with
PyPika through ``erpclaw_lib.query`` over connections from
``erpclaw_lib.db.get_connection``; catalog questions go to
``erpclaw_lib.seam``. Every class also carries one input-validation refusal
that must leave the touched tables identical.

Ledger note, true for all 12 classes: none of these actions posts to the
ledger. Money appears only as exact TEXT (scholarship ``discount_amount``,
late-fee response and message text). There are no debit or credit legs to
assert and none are asserted here; a later reader must not add balance
assertions to these tests.
"""
from datetime import date
from decimal import Decimal

import pytest

from helpers import (
    init_all_tables,
    seed_company, seed_employee, seed_instructor,
    seed_student, seed_guardian,
    seed_academic_year, seed_academic_term,
    seed_course, seed_room, seed_section, seed_enrollment,
    seed_program, seed_fee_category,
    call_action, ns, is_ok, is_error,
)
from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, Table, Field, P, insert_row
from erpclaw_lib import seam

from staff import ACTIONS as STAFF_ACTIONS
from academics import ACTIONS as ACADEMICS_ACTIONS
from fees import ACTIONS as FEES_ACTIONS
from cafeteria import ACTIONS as CAFETERIA_ACTIONS
from enrollment import ACTIONS as ENROLLMENT_ACTIONS
from students import ACTIONS as STUDENTS_ACTIONS
from activities import ACTIONS as ACTIVITIES_ACTIONS


# ── fixtures / read helpers ──────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "m412.sqlite")
    init_all_tables(path)
    return path


@pytest.fixture
def conn(db_path):
    handle = get_connection(db_path)
    yield handle
    handle.close()


def fetch_one(handle, table, row_id):
    t = Table(table)
    q = Q.from_(t).select(t.star).where(Field("id") == P())
    row = handle.execute(q.get_sql(), (row_id,)).fetchone()
    return dict(row) if row else None


def fetch_where(handle, table, column, value):
    t = Table(table)
    q = Q.from_(t).select(t.star).where(Field(column) == P())
    return [dict(r) for r in handle.execute(q.get_sql(), (value,)).fetchall()]


def fetch_all(handle, table):
    t = Table(table)
    q = Q.from_(t).select(t.star)
    return [dict(r) for r in handle.execute(q.get_sql()).fetchall()]


def snapshot(handle, tables):
    out = {}
    for name in tables:
        t = Table(name)
        q = Q.from_(t).select(t.star)
        rows = handle.execute(q.get_sql()).fetchall()
        out[name] = sorted(
            tuple(sorted((k, "--null--" if v is None else str(v))
                         for k, v in dict(r).items()))
            for r in rows
        )
    return out


def seed_full(handle):
    cid = seed_company(handle)
    yid = seed_academic_year(handle, cid)
    tid = seed_academic_term(handle, cid, yid)
    pid = seed_program(handle, cid)
    crs = seed_course(handle, cid)
    rid = seed_room(handle, cid)
    eid = seed_employee(handle, cid)
    iid = seed_instructor(handle, cid, eid)
    sec = seed_section(handle, cid, crs, tid, instructor_id=iid, room_id=rid)
    stu = seed_student(handle, cid)
    return {"company_id": cid, "year_id": yid, "term_id": tid,
            "program_id": pid, "course_id": crs, "room_id": rid,
            "employee_id": eid, "instructor_id": iid,
            "section_id": sec, "student_id": stu}


def test_seam_catalog_lists_educlaw_tables(db_path):
    names = seam.table_names(db_path)
    for owned in ("educlaw_student", "educlaw_instructor", "educlaw_room",
                  "educlaw_section", "educlaw_scholarship",
                  "educlaw_notification", "educlaw_waitlist",
                  "educlaw_consent_record", "educlaw_program_enrollment",
                  "educlaw_student_guardian", "educlaw_activity",
                  "educlaw_student_meal_record"):
        assert owned in names


# ── 1. edu-add-instructor ────────────────────────────────────────────────

class TestAddInstructorDepth:
    def test_effect_writes_instructor_row(self, conn):
        cid = seed_company(conn)
        eid = seed_employee(conn, cid)
        before = fetch_all(conn, "educlaw_instructor")
        r = call_action(STAFF_ACTIONS["edu-add-instructor"], conn, ns(
            employee_id=eid, company_id=cid,
            credentials=None, specializations=None,
            max_teaching_load_hours=None, office_location=None,
            office_hours=None, bio=None,
        ))
        assert is_ok(r)
        row = fetch_one(conn, "educlaw_instructor", r["id"])
        assert row is not None
        assert row["employee_id"] == eid
        assert row["company_id"] == cid
        assert str(row["is_active"]) == "1"
        assert row["naming_series"] == r["naming_series"]
        assert row["naming_series"] != ""
        assert str(row["max_teaching_load_hours"]) == "0"
        after = fetch_all(conn, "educlaw_instructor")
        assert len(after) == len(before) + 1
        other_emp = seed_employee(conn, cid)
        assert fetch_where(conn, "educlaw_instructor", "employee_id", other_emp) == []
        # No ledger legs: writes educlaw_instructor only.

    def test_refusal_unknown_employee_writes_nothing(self, conn):
        cid = seed_company(conn)
        tables = ["educlaw_instructor", "audit_log"]
        before = snapshot(conn, tables)
        r = call_action(STAFF_ACTIONS["edu-add-instructor"], conn, ns(
            employee_id="no-such-employee", company_id=cid,
            credentials=None, specializations=None,
            max_teaching_load_hours=None, office_location=None,
            office_hours=None, bio=None,
        ))
        assert is_error(r)
        assert "not found" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 2. edu-add-room ──────────────────────────────────────────────────────

class TestAddRoomDepth:
    def test_effect_writes_room_row(self, conn):
        cid = seed_company(conn)
        control = seed_room(conn, cid)
        control_before = fetch_one(conn, "educlaw_room", control)
        r = call_action(ACADEMICS_ACTIONS["edu-add-room"], conn, ns(
            company_id=cid, room_number="R-101-DEPTH", building="Science",
            capacity="35", room_type="lab", facilities=None, is_active=None,
        ))
        assert is_ok(r)
        assert r["capacity"] == 35
        row = fetch_one(conn, "educlaw_room", r["id"])
        assert row is not None
        assert row["room_number"] == "R-101-DEPTH"
        assert row["building"] == "Science"
        assert str(row["capacity"]) == "35"
        assert row["room_type"] == "lab"
        assert str(row["is_active"]) == "1"
        assert row["company_id"] == cid
        assert fetch_one(conn, "educlaw_room", control) == control_before
        # No ledger legs: writes educlaw_room only.

    def test_refusal_zero_capacity_writes_nothing(self, conn):
        cid = seed_company(conn)
        tables = ["educlaw_room", "audit_log"]
        before = snapshot(conn, tables)
        r = call_action(ACADEMICS_ACTIONS["edu-add-room"], conn, ns(
            company_id=cid, room_number="R-BAD", building="Main",
            capacity="0", room_type="classroom", facilities=None, is_active=None,
        ))
        assert is_error(r)
        assert "greater than 0" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 3. edu-add-scholarship ───────────────────────────────────────────────

class TestAddScholarshipDepth:
    def test_effect_writes_scholarship_money_as_text(self, conn):
        s = seed_full(conn)
        other_student = seed_student(conn, s["company_id"])
        r = call_action(FEES_ACTIONS["edu-add-scholarship"], conn, ns(
            student_id=s["student_id"], name="Depth Merit",
            discount_type="fixed", discount_amount="1000",
            company_id=s["company_id"], academic_term_id=None,
            applies_to_category_id=None, reason=None, approved_by=None,
        ))
        assert is_ok(r)
        assert r["discount_amount"] == "1000"
        assert Decimal(r["discount_amount"]) == Decimal("1000")
        row = fetch_one(conn, "educlaw_scholarship", r["id"])
        assert row is not None
        assert row["name"] == "Depth Merit"
        assert row["student_id"] == s["student_id"]
        assert row["discount_type"] == "fixed"
        assert row["discount_amount"] == "1000"
        assert Decimal(row["discount_amount"]) == Decimal("1000")
        assert row["scholarship_status"] == "active"
        assert row["company_id"] == s["company_id"]
        assert fetch_where(conn, "educlaw_scholarship", "student_id", other_student) == []
        # No ledger legs: writes educlaw_scholarship only; money stays TEXT.

    def test_refusal_bad_discount_type_writes_nothing(self, conn):
        s = seed_full(conn)
        tables = ["educlaw_scholarship", "audit_log"]
        before = snapshot(conn, tables)
        r = call_action(FEES_ACTIONS["edu-add-scholarship"], conn, ns(
            student_id=s["student_id"], name="Bad Award",
            discount_type="bogus", discount_amount="100",
            company_id=s["company_id"], academic_term_id=None,
            applies_to_category_id=None, reason=None, approved_by=None,
        ))
        assert is_error(r)
        assert "percentage" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 4. edu-allergen-alert-list (read-only) ───────────────────────────────

class TestAllergenAlertListDepth:
    def _insert_meal(self, handle, sid, day, meal, elig, alert):
        import uuid as _uuid
        sql, _ = insert_row("educlaw_student_meal_record", {
            "id": P(), "student_id": P(), "meal_date": P(),
            "meal_type": P(), "eligibility": P(), "allergen_alert": P()})
        mid = str(_uuid.uuid4())
        handle.execute(sql, (mid, sid, day, meal, elig, alert))
        return mid

    def test_effect_returns_exactly_todays_alert_rows(self, conn):
        cid = seed_company(conn)
        s1 = seed_student(conn, cid)
        s2 = seed_student(conn, cid)
        today = date.today().isoformat()
        self._insert_meal(conn, s1, today, "lunch", "free", 1)
        self._insert_meal(conn, s1, today, "breakfast", "free", 0)
        self._insert_meal(conn, s2, today, "lunch", "paid", 1)
        self._insert_meal(conn, s1, "2024-01-02", "lunch", "free", 1)
        conn.commit()
        before = snapshot(conn, ["educlaw_student_meal_record", "educlaw_student"])
        r = call_action(CAFETERIA_ACTIONS["edu-allergen-alert-list"], conn, ns(
            school_id=cid,
        ))
        assert is_ok(r)
        assert r["date"] == today
        assert r["count"] == 2
        assert len(r["allergen_alerts"]) == 2
        keys = sorted((a["student_id"], a["meal_type"]) for a in r["allergen_alerts"])
        assert keys == sorted([(s1, "lunch"), (s2, "lunch")])
        for alert in r["allergen_alerts"]:
            assert alert["student_name"] != ""
        assert snapshot(conn, ["educlaw_student_meal_record", "educlaw_student"]) == before
        # No ledger legs: read-only; writes nothing at all.

    def test_refusal_missing_school_writes_nothing(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        self._insert_meal(conn, sid, date.today().isoformat(), "lunch", "free", 1)
        conn.commit()
        tables = ["educlaw_student_meal_record", "educlaw_student"]
        before = snapshot(conn, tables)
        r = call_action(CAFETERIA_ACTIONS["edu-allergen-alert-list"], conn, ns(
            school_id=None,
        ))
        assert is_error(r)
        assert "required" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 5. edu-apply-late-fee ────────────────────────────────────────────────

class TestApplyLateFeeDepth:
    def test_refusal_missing_invoice_id_writes_nothing(self, conn):
        # m678: a late fee bills exactly one overdue fee invoice through the
        # selling module, so the overdue invoice is a required input. Without
        # it the action refuses before any write; the billing behaviour
        # itself lives in test_fee_invoice_bills_through_selling.py (the
        # once-per-invoice test).
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        fid = seed_fee_category(conn, cid)
        tables = ["educlaw_notification", "educlaw_student", "educlaw_fee_category"]
        before = snapshot(conn, tables)
        r = call_action(FEES_ACTIONS["edu-apply-late-fee"], conn, ns(
            student_id=sid, fee_category_id=fid, amount="25.50",
            company_id=cid,
        ))
        assert is_error(r)
        assert r["message"] == "--sales-invoice-id is required"
        assert snapshot(conn, tables) == before

    def test_refusal_zero_amount_writes_nothing(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        fid = seed_fee_category(conn, cid)
        tables = ["educlaw_notification", "educlaw_student", "educlaw_fee_category"]
        before = snapshot(conn, tables)
        r = call_action(FEES_ACTIONS["edu-apply-late-fee"], conn, ns(
            student_id=sid, fee_category_id=fid, amount="0",
            company_id=cid,
        ))
        assert is_error(r)
        assert "greater than 0" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 6. edu-apply-waitlist ────────────────────────────────────────────────

class TestApplyWaitlistDepth:
    def _insert_waiting(self, handle, sid, sec, pos, cid):
        import uuid as _uuid
        sql, _ = insert_row("educlaw_waitlist", {
            "id": P(), "student_id": P(), "section_id": P(),
            "position": P(), "requested_date": P(),
            "waitlist_status": P(), "company_id": P()})
        wid = str(_uuid.uuid4())
        handle.execute(sql, (wid, sid, sec, pos, date.today().isoformat(),
                             "waiting", cid))
        return wid

    def test_effect_offers_first_waiting_student(self, conn):
        s = seed_full(conn)
        s2 = seed_student(conn, s["company_id"])
        w1 = self._insert_waiting(conn, s["student_id"], s["section_id"], 1,
                                  s["company_id"])
        w2 = self._insert_waiting(conn, s2, s["section_id"], 2, s["company_id"])
        conn.commit()
        sec_before = fetch_one(conn, "educlaw_section", s["section_id"])
        assert str(sec_before["current_enrollment"]) == "0"
        r = call_action(ENROLLMENT_ACTIONS["edu-apply-waitlist"], conn, ns(
            section_id=s["section_id"],
        ))
        assert is_ok(r)
        first = fetch_one(conn, "educlaw_waitlist", w1)
        second = fetch_one(conn, "educlaw_waitlist", w2)
        assert first["waitlist_status"] == "offered"
        assert first["offer_expires_at"] != ""
        assert second["waitlist_status"] == "waiting"
        assert second["offer_expires_at"] == ""
        sec_after = fetch_one(conn, "educlaw_section", s["section_id"])
        assert sec_after["current_enrollment"] == sec_before["current_enrollment"]
        notes = [n for n in fetch_where(conn, "educlaw_notification",
                                        "recipient_id", s["student_id"])
                 if n["notification_type"] == "enrollment_confirmed"
                 and n["reference_id"] == w1]
        assert len(notes) == 1
        # No ledger legs: flips waitlist status and inserts a notification.

    def test_refusal_unknown_section_writes_nothing(self, conn):
        s = seed_full(conn)
        self._insert_waiting(conn, s["student_id"], s["section_id"], 1,
                             s["company_id"])
        conn.commit()
        tables = ["educlaw_waitlist", "educlaw_notification", "educlaw_section"]
        before = snapshot(conn, tables)
        r = call_action(ENROLLMENT_ACTIONS["edu-apply-waitlist"], conn, ns(
            section_id="no-such-section",
        ))
        assert is_error(r)
        assert "not found" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 7. edu-assign-guardian ───────────────────────────────────────────────

class TestAssignGuardianDepth:
    def test_effect_writes_link_row(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        other_sid = seed_student(conn, cid)
        r = call_action(STUDENTS_ACTIONS["edu-assign-guardian"], conn, ns(
            student_id=sid, guardian_id=gid, relationship="mother",
            is_primary_contact=1, is_emergency_contact=None,
            has_custody=None, can_pickup=None, receives_communications=None,
        ))
        assert is_ok(r)
        assert r["relationship"] == "mother"
        row = fetch_one(conn, "educlaw_student_guardian", r["id"])
        assert row is not None
        assert row["student_id"] == sid
        assert row["guardian_id"] == gid
        assert row["relationship"] == "mother"
        assert str(row["has_custody"]) == "1"
        assert str(row["can_pickup"]) == "1"
        assert str(row["receives_communications"]) == "1"
        assert str(row["is_primary_contact"]) == "1"
        assert str(row["is_emergency_contact"]) == "0"
        assert fetch_where(conn, "educlaw_student_guardian", "student_id", other_sid) == []
        # No ledger legs: writes educlaw_student_guardian only.

    def test_refusal_bad_relationship_writes_nothing(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        tables = ["educlaw_student_guardian"]
        before = snapshot(conn, tables)
        r = call_action(STUDENTS_ACTIONS["edu-assign-guardian"], conn, ns(
            student_id=sid, guardian_id=gid, relationship="cousin",
            is_primary_contact=None, is_emergency_contact=None,
            has_custody=None, can_pickup=None, receives_communications=None,
        ))
        assert is_error(r)
        assert "must be one of" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 8. edu-cancel-consent ────────────────────────────────────────────────

class TestCancelConsentDepth:
    def _grant(self, handle, sid, cid):
        r = call_action(STUDENTS_ACTIONS["edu-add-consent-record"], handle, ns(
            student_id=sid, consent_type="ferpa_directory",
            consent_date="2025-09-01", granted_by="Depth Parent",
            granted_by_relationship="parent",
            expiry_date=None, third_party_name=None, purpose=None,
            company_id=cid,
        ))
        assert is_ok(r)
        return r["id"]

    def test_effect_revokes_consent_row(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        cid2 = self._grant(conn, sid, cid)
        granted = fetch_one(conn, "educlaw_consent_record", cid2)
        assert str(granted["is_revoked"]) == "0"
        assert granted["revoked_date"] == ""
        r = call_action(STUDENTS_ACTIONS["edu-cancel-consent"], conn, ns(
            consent_id=cid2, revoked_date="2025-10-01",
        ))
        assert is_ok(r)
        assert r["is_revoked"] == 1
        row = fetch_one(conn, "educlaw_consent_record", cid2)
        assert str(row["is_revoked"]) == "1"
        assert row["revoked_date"] == "2025-10-01"
        assert row["consent_type"] == granted["consent_type"]
        assert row["granted_by"] == granted["granted_by"]
        assert row["student_id"] == granted["student_id"]
        # No ledger legs: flips flags on educlaw_consent_record only.

    def test_refusal_missing_id_writes_nothing(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        self._grant(conn, sid, cid)
        tables = ["educlaw_consent_record", "audit_log"]
        before = snapshot(conn, tables)
        r = call_action(STUDENTS_ACTIONS["edu-cancel-consent"], conn, ns(
            consent_id=None, revoked_date="2025-10-01",
        ))
        assert is_error(r)
        assert "required" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 9. edu-cancel-program-enrollment ─────────────────────────────────────

class TestCancelProgramEnrollmentDepth:
    def _enroll(self, handle, s):
        r = call_action(ENROLLMENT_ACTIONS["edu-create-program-enrollment"], handle, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None,
        ))
        assert is_ok(r)
        return r["id"]

    def test_effect_withdraws_enrollment_row(self, conn):
        s = seed_full(conn)
        eid = self._enroll(conn, s)
        created = fetch_one(conn, "educlaw_program_enrollment", eid)
        assert created["enrollment_status"] == "active"
        student_before = fetch_one(conn, "educlaw_student", s["student_id"])
        r = call_action(ENROLLMENT_ACTIONS["edu-cancel-program-enrollment"], conn, ns(
            enrollment_id=eid,
        ))
        assert is_ok(r)
        assert r["enrollment_status"] == "withdrawn"
        row = fetch_one(conn, "educlaw_program_enrollment", eid)
        assert row["enrollment_status"] == "withdrawn"
        assert row["student_id"] == created["student_id"]
        assert row["program_id"] == created["program_id"]
        notes = [n for n in fetch_where(conn, "educlaw_notification",
                                        "recipient_id", s["student_id"])
                 if n["reference_id"] == eid
                 and n["title"] == "Program Withdrawal Processed"]
        assert len(notes) == 1
        assert notes[0]["notification_type"] == "announcement"
        assert fetch_one(conn, "educlaw_student", s["student_id"]) == student_before
        # No ledger legs: flips enrollment status and inserts a notification.

    def test_refusal_unknown_enrollment_writes_nothing(self, conn):
        s = seed_full(conn)
        self._enroll(conn, s)
        tables = ["educlaw_program_enrollment", "educlaw_notification", "audit_log"]
        before = snapshot(conn, tables)
        r = call_action(ENROLLMENT_ACTIONS["edu-cancel-program-enrollment"], conn, ns(
            enrollment_id="no-such-enrollment",
        ))
        assert is_error(r)
        assert "not found" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 10. edu-cancel-section ───────────────────────────────────────────────

class TestCancelSectionDepth:
    def test_effect_cancels_section_and_drops_enrollments(self, conn):
        s = seed_full(conn)
        enr = seed_enrollment(conn, s["student_id"], s["section_id"], s["company_id"])
        import uuid as _uuid
        sql, _ = insert_row("educlaw_waitlist", {
            "id": P(), "student_id": P(), "section_id": P(),
            "position": P(), "requested_date": P(),
            "waitlist_status": P(), "company_id": P()})
        wid = str(_uuid.uuid4())
        conn.execute(sql, (wid, s["student_id"], s["section_id"], 1,
                           date.today().isoformat(), "waiting", s["company_id"]))
        conn.commit()
        control_sec = seed_section(conn, s["company_id"], s["course_id"], s["term_id"])
        sec_before = fetch_one(conn, "educlaw_section", s["section_id"])
        assert sec_before["status"] == "open"
        r = call_action(ACADEMICS_ACTIONS["edu-cancel-section"], conn, ns(
            section_id=s["section_id"],
        ))
        assert is_ok(r)
        assert r["dropped_students"] == 1
        sec = fetch_one(conn, "educlaw_section", s["section_id"])
        assert sec["status"] == "cancelled"
        assert str(sec["current_enrollment"]) == "0"
        enrollment = fetch_one(conn, "educlaw_course_enrollment", enr)
        assert enrollment["enrollment_status"] == "dropped"
        assert enrollment["drop_reason"] == "Section cancelled"
        assert enrollment["drop_date"] != ""
        wait = fetch_one(conn, "educlaw_waitlist", wid)
        assert wait["waitlist_status"] == "cancelled"
        notes = [n for n in fetch_where(conn, "educlaw_notification",
                                        "recipient_id", s["student_id"])
                 if n["reference_id"] == s["section_id"]]
        assert len(notes) >= 1
        assert notes[0]["title"] == "Section Cancelled"
        assert fetch_one(conn, "educlaw_section", control_sec)["status"] == "open"
        # No ledger legs: flips section/enrollment/waitlist rows, notifies.

    def test_refusal_missing_id_writes_nothing(self, conn):
        s = seed_full(conn)
        seed_enrollment(conn, s["student_id"], s["section_id"], s["company_id"])
        tables = ["educlaw_section", "educlaw_course_enrollment",
                  "educlaw_waitlist", "educlaw_notification"]
        before = snapshot(conn, tables)
        r = call_action(ACADEMICS_ACTIONS["edu-cancel-section"], conn, ns(
            section_id=None,
        ))
        assert is_error(r)
        assert "required" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 11. edu-check-activity-eligibility (read-only) ───────────────────────

class TestCheckActivityEligibilityDepth:
    def _add_activity(self, handle, cid, name, gpa=None, max_enr=None):
        r = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], handle, ns(
            name=name, company_id=cid, activity_type="academic",
            instructor_id=None, description="", min_gpa=gpa,
            max_enrollment=max_enr, season=None, school_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        return r["id"]

    def test_effect_reports_db_state_and_writes_nothing(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        aid = self._add_activity(conn, cid, "Depth Chess")
        stored = fetch_one(conn, "educlaw_activity", aid)
        assert stored["status"] == "active"
        tables = ["educlaw_activity", "educlaw_activity_enrollment", "educlaw_student"]
        before = snapshot(conn, tables)
        r = call_action(ACTIVITIES_ACTIONS["edu-check-activity-eligibility"], conn, ns(
            activity_id=aid, student_id=sid, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["eligible"] is True
        assert r["issues"] == []
        assert r["current_gpa"] == "N/A"
        assert r["activity_name"] == stored["name"]
        assert snapshot(conn, tables) == before
        enroll = call_action(ACTIVITIES_ACTIONS["edu-enroll-student-activity"], conn, ns(
            activity_id=aid, student_id=sid, limit=50, offset=0,
        ))
        assert is_ok(enroll)
        mid = snapshot(conn, tables)
        r2 = call_action(ACTIVITIES_ACTIONS["edu-check-activity-eligibility"], conn, ns(
            activity_id=aid, student_id=sid, limit=50, offset=0,
        ))
        assert is_ok(r2)
        assert r2["eligible"] is False
        assert "already enrolled" in " ".join(r2["issues"]).lower()
        assert snapshot(conn, tables) == mid
        # No ledger legs: read-only; writes nothing at all.

    def test_effect_min_gpa_without_gpa_documents_real_behaviour(self, conn):
        # FINDING (not fixed): with min_gpa set and no GPA on record the
        # action reports eligible True while listing an issue. This test pins
        # that real behaviour so a later change is a deliberate decision.
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        aid = self._add_activity(conn, cid, "Depth Honor", gpa="3.5")
        r = call_action(ACTIVITIES_ACTIONS["edu-check-activity-eligibility"], conn, ns(
            activity_id=aid, student_id=sid, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["eligible"] is True
        assert r["issues"] == ["No GPA on record to verify minimum requirement"]
        # No ledger legs: read-only.

    def test_refusal_missing_activity_writes_nothing(self, conn):
        cid = seed_company(conn)
        sid = seed_student(conn, cid)
        tables = ["educlaw_activity", "educlaw_activity_enrollment", "educlaw_student"]
        before = snapshot(conn, tables)
        r = call_action(ACTIVITIES_ACTIONS["edu-check-activity-eligibility"], conn, ns(
            activity_id=None, student_id=sid, limit=50, offset=0,
        ))
        assert is_error(r)
        assert "required" in r.get("message", "")
        assert snapshot(conn, tables) == before


# ── 12. edu-complete-graduation ──────────────────────────────────────────

class TestCompleteGraduationDepth:
    def test_effect_graduates_student_and_completes_enrollment(self, conn):
        s = seed_full(conn)
        control = seed_student(conn, s["company_id"])
        control_before = fetch_one(conn, "educlaw_student", control)
        penr = call_action(ENROLLMENT_ACTIONS["edu-create-program-enrollment"], conn, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None,
        ))
        assert is_ok(penr)
        assert fetch_one(conn, "educlaw_program_enrollment",
                         penr["id"])["enrollment_status"] == "active"
        r = call_action(STUDENTS_ACTIONS["edu-complete-graduation"], conn, ns(
            student_id=s["student_id"], graduation_date="2026-05-15",
        ))
        assert is_ok(r)
        assert r["graduation_date"] == "2026-05-15"
        row = fetch_one(conn, "educlaw_student", s["student_id"])
        assert row["status"] == "graduated"
        assert row["graduation_date"] == "2026-05-15"
        prog = fetch_one(conn, "educlaw_program_enrollment", penr["id"])
        assert prog["enrollment_status"] == "completed"
        assert fetch_one(conn, "educlaw_student", control) == control_before
        # No ledger legs: flips student/program-enrollment status only.

    def test_refusal_unknown_student_writes_nothing(self, conn):
        s = seed_full(conn)
        tables = ["educlaw_student", "educlaw_program_enrollment", "audit_log"]
        before = snapshot(conn, tables)
        r = call_action(STUDENTS_ACTIONS["edu-complete-graduation"], conn, ns(
            student_id="no-such-student", graduation_date="2026-05-15",
        ))
        assert is_error(r)
        assert "not found" in r.get("message", "")
        assert snapshot(conn, tables) == before
