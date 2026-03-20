"""L1 pytest tests for EduClaw Phase 3 — Parent Portal, Cafeteria (NSLP),
and Transportation domains.

Tests: portal (6), cafeteria (5), transport (5) = 16 tests.
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
seed_guardian = _helpers.seed_guardian
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_course = _helpers.seed_course
seed_room = _helpers.seed_room
seed_employee = _helpers.seed_employee
seed_instructor = _helpers.seed_instructor
seed_section = _helpers.seed_section
seed_enrollment = _helpers.seed_enrollment
seed_fee_category = _helpers.seed_fee_category

PORTAL_ACTIONS = _load("portal", _SCRIPTS_DIR).ACTIONS
CAFETERIA_ACTIONS = _load("cafeteria", _SCRIPTS_DIR).ACTIONS
TRANSPORT_ACTIONS = _load("transport", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS
ATTENDANCE_ACTIONS = _load("attendance", _SCRIPTS_DIR).ACTIONS

import uuid


# ── Helpers ──────────────────────────────────────────────────────────────────

def seed_student_guardian_link(conn, student_id, guardian_id,
                                relationship="mother"):
    """Link a guardian to a student."""
    link_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact)
           VALUES (?, ?, ?, ?, 1, 1, 1, 1, 1)""",
        (link_id, student_id, guardian_id, relationship)
    )
    conn.commit()
    return link_id


def seed_announcement(conn, company_id, audience_type="all"):
    """Insert a published announcement."""
    ann_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_announcement
           (id, title, body, priority, audience_type, audience_filter,
            publish_date, expiry_date, announcement_status, published_by,
            company_id, created_by)
           VALUES (?, 'Test Announcement', 'Body text', 'normal', ?, '{}',
                   '2026-01-01', '2026-12-31', 'published', 'admin', ?, '')""",
        (ann_id, audience_type, company_id)
    )
    conn.commit()
    return ann_id


def seed_attendance_record(conn, student_id, company_id,
                            att_date="2026-03-15", status="absent"):
    """Insert a test attendance record."""
    att_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_attendance
           (id, student_id, attendance_date, attendance_status,
            marked_by, source, company_id, created_by)
           VALUES (?, ?, ?, ?, 'teacher', 'manual', ?, '')""",
        (att_id, student_id, att_date, status, company_id)
    )
    conn.commit()
    return att_id


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def portal_setup(db_path):
    """Setup for portal tests: company + student + guardian + link."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    stu_id = seed_student(conn, cid)
    guard_id = seed_guardian(conn, cid)
    seed_student_guardian_link(conn, stu_id, guard_id)
    yield {
        "conn": conn, "company_id": cid,
        "student_id": stu_id, "guardian_id": guard_id,
    }
    conn.close()


@pytest.fixture
def full_portal_setup(db_path):
    """Full setup for portal tests with course enrollment."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    crs_id = seed_course(conn, cid)
    rm_id = seed_room(conn, cid)
    emp_id = seed_employee(conn, cid)
    inst_id = seed_instructor(conn, cid, emp_id)
    sec_id = seed_section(conn, cid, crs_id, tid, instructor_id=inst_id, room_id=rm_id)
    stu_id = seed_student(conn, cid)
    enr_id = seed_enrollment(conn, stu_id, sec_id, cid)
    guard_id = seed_guardian(conn, cid)
    seed_student_guardian_link(conn, stu_id, guard_id)
    yield {
        "conn": conn, "company_id": cid,
        "year_id": yid, "term_id": tid,
        "course_id": crs_id, "section_id": sec_id,
        "student_id": stu_id, "enrollment_id": enr_id,
        "guardian_id": guard_id, "room_id": rm_id,
        "instructor_id": inst_id, "employee_id": emp_id,
    }
    conn.close()


@pytest.fixture
def cafeteria_setup(db_path):
    """Setup for cafeteria tests: company + student."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    stu_id = seed_student(conn, cid)
    yield {"conn": conn, "company_id": cid, "student_id": stu_id}
    conn.close()


@pytest.fixture
def transport_setup(db_path):
    """Setup for transport tests: company + student + guardian."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    stu_id = seed_student(conn, cid)
    guard_id = seed_guardian(conn, cid)
    seed_student_guardian_link(conn, stu_id, guard_id)
    yield {
        "conn": conn, "company_id": cid,
        "student_id": stu_id, "guardian_id": guard_id,
    }
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# PORTAL DOMAIN
# ══════════════════════════════════════════════════════════════════════════════

class TestPortalMyStudents:
    def test_portal_my_students(self, portal_setup):
        s = portal_setup
        r = call_action(PORTAL_ACTIONS["edu-portal-my-students"], s["conn"], ns(
            guardian_id=s["guardian_id"],
        ))
        assert is_ok(r)
        assert r["count"] == 1
        assert r["students"][0]["id"] == s["student_id"]


class TestPortalStudentGradesAccessDenied:
    def test_portal_student_grades_access_denied(self, portal_setup):
        """Wrong guardian should be denied access."""
        s = portal_setup
        # Create a second guardian not linked to the student
        other_guard = seed_guardian(s["conn"], s["company_id"])
        r = call_action(PORTAL_ACTIONS["edu-portal-student-grades"], s["conn"], ns(
            guardian_id=other_guard,
            student_id=s["student_id"],
        ))
        assert is_error(r)
        assert "Access denied" in r.get("message", r.get("error", ""))


class TestPortalStudentGradesSuccess:
    def test_portal_student_grades_success(self, full_portal_setup):
        s = full_portal_setup
        r = call_action(PORTAL_ACTIONS["edu-portal-student-grades"], s["conn"], ns(
            guardian_id=s["guardian_id"],
            student_id=s["student_id"],
        ))
        assert is_ok(r)
        assert "grades" in r
        # Student has an enrollment, so should see at least one entry
        assert r["count"] >= 1


class TestPortalStudentFees:
    def test_portal_student_fees(self, portal_setup):
        s = portal_setup
        r = call_action(PORTAL_ACTIONS["edu-portal-student-fees"], s["conn"], ns(
            guardian_id=s["guardian_id"],
            student_id=s["student_id"],
        ))
        assert is_ok(r)
        assert "invoices" in r
        assert "active_scholarships" in r


class TestPortalUpdateContactInfo:
    def test_portal_update_contact_info(self, portal_setup):
        s = portal_setup
        r = call_action(PORTAL_ACTIONS["edu-portal-update-contact-info"], s["conn"], ns(
            guardian_id=s["guardian_id"],
            phone="555-9999",
            email="updated@parent.com",
            address=None,
        ))
        assert is_ok(r)
        assert "phone" in r["updated_fields"]
        assert "email" in r["updated_fields"]

        # Verify the update persisted
        row = s["conn"].execute(
            "SELECT phone, email FROM educlaw_guardian WHERE id = ?",
            (s["guardian_id"],)
        ).fetchone()
        assert dict(row)["phone"] == "555-9999"
        assert dict(row)["email"] == "updated@parent.com"


class TestPortalSubmitAbsenceExcuse:
    def test_portal_submit_absence_excuse(self, portal_setup):
        s = portal_setup
        # Create an absence record first
        att_id = seed_attendance_record(
            s["conn"], s["student_id"], s["company_id"],
            att_date="2026-03-15", status="absent"
        )
        r = call_action(PORTAL_ACTIONS["edu-portal-submit-absence-excuse"], s["conn"], ns(
            guardian_id=s["guardian_id"],
            student_id=s["student_id"],
            absence_date="2026-03-15",
            reason="Doctor appointment",
        ))
        assert is_ok(r)
        assert r["excuse_submitted"] is True

        # Verify attendance updated to excused
        row = s["conn"].execute(
            "SELECT attendance_status, comments FROM educlaw_student_attendance WHERE id = ?",
            (att_id,)
        ).fetchone()
        assert dict(row)["attendance_status"] == "excused"
        assert "Doctor appointment" in dict(row)["comments"]


# ══════════════════════════════════════════════════════════════════════════════
# CAFETERIA DOMAIN
# ══════════════════════════════════════════════════════════════════════════════

class TestAddMealPlan:
    def test_add_meal_plan(self, cafeteria_setup):
        s = cafeteria_setup
        r = call_action(CAFETERIA_ACTIONS["edu-add-meal-plan"], s["conn"], ns(
            school_id=s["company_id"],
            plan_type="free",
            daily_rate="0.00",
            academic_year="2025-2026",
            description="Free lunch program",
        ))
        assert is_ok(r)
        assert r["plan_type"] == "free"
        assert r["daily_rate"] == "0.00"
        assert r["academic_year"] == "2025-2026"


class TestRecordDailyMealCount:
    def test_record_daily_meal_count(self, cafeteria_setup):
        s = cafeteria_setup
        r = call_action(CAFETERIA_ACTIONS["edu-record-daily-meal-count"], s["conn"], ns(
            school_id=s["company_id"],
            count_date="2026-03-15",
            free_breakfast=45,
            reduced_breakfast=12,
            regular_breakfast=30,
            free_lunch=50,
            reduced_lunch=15,
            regular_lunch=40,
            adult_meals=5,
            snack_count=20,
            counted_by="cafeteria_mgr",
            notes=None,
        ))
        assert is_ok(r)
        assert r["total_meals"] == 45 + 12 + 30 + 50 + 15 + 40 + 5 + 20


class TestRecordStudentMeal:
    def test_record_student_meal(self, cafeteria_setup):
        s = cafeteria_setup
        r = call_action(CAFETERIA_ACTIONS["edu-record-student-meal"], s["conn"], ns(
            student_id=s["student_id"],
            meal_date="2026-03-15",
            meal_type="lunch",
            eligibility="free",
            allergen_alert=1,
            served_by="Jane",
        ))
        assert is_ok(r)
        assert r["meal_type"] == "lunch"
        assert r["eligibility"] == "free"
        assert r["allergen_alert"] is True


class TestMealParticipationReport:
    def test_meal_participation_report(self, cafeteria_setup):
        s = cafeteria_setup
        # Seed some daily counts
        for day in range(1, 4):
            call_action(CAFETERIA_ACTIONS["edu-record-daily-meal-count"], s["conn"], ns(
                school_id=s["company_id"],
                count_date=f"2026-03-{day:02d}",
                free_breakfast=10,
                reduced_breakfast=5,
                regular_breakfast=8,
                free_lunch=12,
                reduced_lunch=6,
                regular_lunch=10,
                adult_meals=2,
                snack_count=5,
                counted_by=None,
                notes=None,
            ))

        r = call_action(CAFETERIA_ACTIONS["edu-meal-participation-report"], s["conn"], ns(
            school_id=s["company_id"],
            month="2026-03",
        ))
        assert is_ok(r)
        assert r["days_reported"] == 3
        assert r["totals"]["free_lunch"] == 36  # 12 * 3
        assert r["totals"]["total_breakfast"] == (10 + 5 + 8) * 3


class TestUsdaClaimReport:
    def test_usda_claim_report(self, cafeteria_setup):
        s = cafeteria_setup
        # Seed daily counts for 2 days
        for day in (10, 11):
            call_action(CAFETERIA_ACTIONS["edu-record-daily-meal-count"], s["conn"], ns(
                school_id=s["company_id"],
                count_date=f"2026-03-{day}",
                free_breakfast=20,
                reduced_breakfast=10,
                regular_breakfast=5,
                free_lunch=25,
                reduced_lunch=8,
                regular_lunch=15,
                adult_meals=3,
                snack_count=0,
                counted_by=None,
                notes=None,
            ))

        r = call_action(CAFETERIA_ACTIONS["edu-usda-claim-report"], s["conn"], ns(
            school_id=s["company_id"],
            month="2026-03",
        ))
        assert is_ok(r)
        assert r["days_in_report"] == 2
        assert len(r["claim_items"]) == 6

        # Verify calculation for free_lunch: 25*2=50 meals * $4.36 = $218.00
        free_lunch_item = next(
            i for i in r["claim_items"] if i["category"] == "free_lunch"
        )
        assert free_lunch_item["count"] == 50
        assert free_lunch_item["rate"] == "4.36"
        assert free_lunch_item["amount"] == "218.00"

        # Total claim should be positive
        from decimal import Decimal
        assert Decimal(r["total_claim"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# TRANSPORT DOMAIN
# ══════════════════════════════════════════════════════════════════════════════

class TestAddBusRoute:
    def test_add_bus_route(self, transport_setup):
        s = transport_setup
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], s["conn"], ns(
            school_id=s["company_id"],
            route_number="101",
            route_name="North Route",
            driver_name="John Smith",
            driver_phone="555-1111",
            vehicle_id=None,
            vehicle_number="BUS-42",
            capacity=48,
            am_start_time="07:00",
            pm_start_time="15:00",
            notes=None,
        ))
        assert is_ok(r)
        assert r["route_number"] == "101"
        assert r["route_status"] == "active"


class TestAddBusStop:
    def test_add_bus_stop(self, transport_setup):
        s = transport_setup
        # Create route first
        r1 = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], s["conn"], ns(
            school_id=s["company_id"],
            route_number="202",
            route_name=None, driver_name=None, driver_phone=None,
            vehicle_id=None, vehicle_number=None, capacity=None,
            am_start_time=None, pm_start_time=None, notes=None,
        ))
        assert is_ok(r1)
        route_id = r1["id"]

        r2 = call_action(TRANSPORT_ACTIONS["edu-add-bus-stop"], s["conn"], ns(
            route_id=route_id,
            stop_order=1,
            stop_name="Main St & 1st Ave",
            address="123 Main St",
            am_pickup_time="07:15",
            pm_dropoff_time="15:20",
        ))
        assert is_ok(r2)
        assert r2["stop_name"] == "Main St & 1st Ave"
        assert r2["stop_order"] == 1


class TestAssignStudentTransport:
    def test_assign_student_transport(self, transport_setup):
        s = transport_setup
        # Create route + stop
        r1 = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], s["conn"], ns(
            school_id=s["company_id"],
            route_number="303",
            route_name="East Route",
            driver_name=None, driver_phone=None,
            vehicle_id=None, vehicle_number=None, capacity=40,
            am_start_time=None, pm_start_time=None, notes=None,
        ))
        route_id = r1["id"]

        r2 = call_action(TRANSPORT_ACTIONS["edu-add-bus-stop"], s["conn"], ns(
            route_id=route_id, stop_order=1, stop_name="Elm St",
            address=None, am_pickup_time=None, pm_dropoff_time=None,
        ))
        stop_id = r2["id"]

        r3 = call_action(TRANSPORT_ACTIONS["edu-assign-student-transport"], s["conn"], ns(
            student_id=s["student_id"],
            route_id=route_id,
            bus_stop_id=stop_id,
            transport_type="both",
            special_needs_notes=None,
            effective_date="2026-03-01",
        ))
        assert is_ok(r3)
        assert r3["student_id"] == s["student_id"]
        assert r3["route_id"] == route_id
        assert r3["bus_stop_id"] == stop_id
        assert r3["transport_status"] == "active"


class TestBusRoster:
    def test_bus_roster(self, transport_setup):
        s = transport_setup
        # Create route + stop + assign student
        r1 = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], s["conn"], ns(
            school_id=s["company_id"],
            route_number="404",
            route_name="West Route",
            driver_name="Jane Driver",
            driver_phone="555-2222",
            vehicle_id=None, vehicle_number=None, capacity=30,
            am_start_time=None, pm_start_time=None, notes=None,
        ))
        route_id = r1["id"]

        r2 = call_action(TRANSPORT_ACTIONS["edu-add-bus-stop"], s["conn"], ns(
            route_id=route_id, stop_order=1, stop_name="Oak Ave",
            address=None, am_pickup_time=None, pm_dropoff_time=None,
        ))
        stop_id = r2["id"]

        call_action(TRANSPORT_ACTIONS["edu-assign-student-transport"], s["conn"], ns(
            student_id=s["student_id"],
            route_id=route_id,
            bus_stop_id=stop_id,
            transport_type="both",
            special_needs_notes=None,
            effective_date=None,
        ))

        r4 = call_action(TRANSPORT_ACTIONS["edu-bus-roster"], s["conn"], ns(
            route_id=route_id,
        ))
        assert is_ok(r4)
        assert r4["student_count"] == 1
        assert r4["route_number"] == "404"
        assert r4["driver_name"] == "Jane Driver"
        # Verify guardian info is included
        roster_entry = r4["roster"][0]
        assert len(roster_entry["guardians"]) >= 1
        assert roster_entry["guardians"][0]["guardian_name"] == "Test Parent"


class TestTransportReport:
    def test_transport_report(self, transport_setup):
        s = transport_setup
        # Create 2 routes, assign student to one
        r1 = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], s["conn"], ns(
            school_id=s["company_id"],
            route_number="501",
            route_name="Route A", driver_name=None, driver_phone=None,
            vehicle_id=None, vehicle_number=None, capacity=40,
            am_start_time=None, pm_start_time=None, notes=None,
        ))
        route1_id = r1["id"]

        call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], s["conn"], ns(
            school_id=s["company_id"],
            route_number="502",
            route_name="Route B", driver_name=None, driver_phone=None,
            vehicle_id=None, vehicle_number=None, capacity=30,
            am_start_time=None, pm_start_time=None, notes=None,
        ))

        call_action(TRANSPORT_ACTIONS["edu-assign-student-transport"], s["conn"], ns(
            student_id=s["student_id"],
            route_id=route1_id,
            bus_stop_id=None,
            transport_type="both",
            special_needs_notes=None,
            effective_date=None,
        ))

        r = call_action(TRANSPORT_ACTIONS["edu-transport-report"], s["conn"], ns(
            school_id=s["company_id"],
        ))
        assert is_ok(r)
        assert r["total_routes"] == 2
        assert r["total_students_transported"] == 1
        assert r["total_capacity"] == 70  # 40 + 30
        assert r["overall_utilization_pct"] > 0
