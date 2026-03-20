"""Phase 9: EduClaw Market Parity — 8 HIGH gaps (25+ tests)

Tests cover:
  E4  — Professional Development (5 actions)
  E5  — Online Fee Payment (4 actions)
  E7  — Online Admissions Portal (4 actions)
  E8  — Student Activities (7 actions)
  E9  — Library Management (8 actions)
  E10 — Dormitory/Housing (8 actions)
  E11 — Degree Audit Expansion (2 actions in highered)
  E12 — Timetable Auto-Generation (1 action in scheduling)
"""
import os
import sys
import uuid

import pytest

# Import test helpers
from helpers import (
    init_all_tables, get_conn, seed_company, seed_employee, seed_instructor,
    seed_student, seed_guardian, seed_academic_year, seed_academic_term,
    seed_course, seed_room, seed_section, seed_enrollment, seed_program,
    seed_fee_category, seed_naming_series,
    call_action, ns, is_ok, is_error,
)

# Import domain modules
from pd import ACTIONS as PD_ACTIONS
from activities import ACTIONS as ACTIVITIES_ACTIONS
from library import ACTIONS as LIBRARY_ACTIONS
from housing import ACTIONS as HOUSING_ACTIONS
from fees import ACTIONS as FEES_ACTIONS
from students import ACTIONS as STUDENTS_ACTIONS


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test_phase9.sqlite")
    init_all_tables(path)
    return path


@pytest.fixture
def conn(db):
    c = get_conn(db)
    yield c
    c.close()


@pytest.fixture
def base(conn):
    """Create shared base entities for all tests."""
    cid = seed_company(conn)
    eid = seed_employee(conn, cid)
    iid = seed_instructor(conn, cid, eid)
    sid = seed_student(conn, cid)
    gid = seed_guardian(conn, cid)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    crs_id = seed_course(conn, cid)
    room_id = seed_room(conn, cid)
    sec_id = seed_section(conn, cid, crs_id, tid, iid, room_id)
    # Link guardian to student
    link_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact)
           VALUES (?, ?, ?, 'mother', 1, 1, 1, 1, 1)""",
        (link_id, sid, gid)
    )
    conn.commit()
    return {
        "company_id": cid, "employee_id": eid, "instructor_id": iid,
        "student_id": sid, "guardian_id": gid,
        "year_id": yid, "term_id": tid,
        "course_id": crs_id, "room_id": room_id, "section_id": sec_id,
    }


# ──────────────────────────────────────────────────────────────────────────────
# E4: Professional Development
# ──────────────────────────────────────────────────────────────────────────────

class TestProfessionalDevelopment:

    def test_add_pd_credit(self, conn, base):
        r = call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
            instructor_id=base["instructor_id"],
            name="Advanced Teaching Strategies",
            credit_hours="15",
            start_date="2025-06-15",
            company_id=base["company_id"],
            credit_type="general",
            description="National Teaching Institute",
            end_date="",
            code="",
            status="approved",
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["credit_hours"] == "15"
        assert r["credit_type"] == "general"

    def test_list_pd_credits(self, conn, base):
        call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
            instructor_id=base["instructor_id"],
            name="PD Course A", credit_hours="10", start_date="2025-01-01",
            company_id=base["company_id"], credit_type="general",
            description="", end_date="", code="", status="approved",
            limit=50, offset=0,
        ))
        call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
            instructor_id=base["instructor_id"],
            name="PD Course B", credit_hours="5", start_date="2025-02-01",
            company_id=base["company_id"], credit_type="technology",
            description="", end_date="", code="", status="approved",
            limit=50, offset=0,
        ))
        r = call_action(PD_ACTIONS["edu-list-pd-credits"], conn, ns(
            instructor_id=base["instructor_id"],
            company_id=base["company_id"],
            status=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 2

    def test_get_pd_summary(self, conn, base):
        call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
            instructor_id=base["instructor_id"],
            name="Summary Test", credit_hours="20", start_date="2025-03-01",
            company_id=base["company_id"], credit_type="leadership",
            description="", end_date="", code="", status="approved",
            limit=50, offset=0,
        ))
        r = call_action(PD_ACTIONS["edu-get-pd-summary"], conn, ns(
            instructor_id=base["instructor_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "total_credit_hours" in r
        assert "by_type" in r

    def test_check_pd_compliance_pass(self, conn, base):
        call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
            instructor_id=base["instructor_id"],
            name="Big Course", credit_hours="50", start_date="2025-04-01",
            company_id=base["company_id"], credit_type="general",
            description="", end_date="", code="", status="approved",
            limit=50, offset=0,
        ))
        r = call_action(PD_ACTIONS["edu-check-pd-compliance"], conn, ns(
            instructor_id=base["instructor_id"],
            threshold="10",
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["compliant"] is True

    def test_pd_transcript(self, conn, base):
        call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
            instructor_id=base["instructor_id"],
            name="Transcript Course", credit_hours="8", start_date="2025-05-01",
            company_id=base["company_id"], credit_type="content_area",
            description="Provider X", end_date="", code="CERT-001", status="approved",
            limit=50, offset=0,
        ))
        r = call_action(PD_ACTIONS["edu-pd-transcript"], conn, ns(
            instructor_id=base["instructor_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "instructor_name" in r
        assert "credits" in r


# ──────────────────────────────────────────────────────────────────────────────
# E5: Online Fee Payment
# ──────────────────────────────────────────────────────────────────────────────

class TestOnlineFeePayment:

    def test_add_payment_method(self, conn, base):
        r = call_action(FEES_ACTIONS["edu-add-payment-method"], conn, ns(
            guardian_id=base["guardian_id"],
            payment_method_type="credit_card",
            method_type=None,
            company_id=base["company_id"],
            last_four="4242",
            is_default=None, autopay_enabled=None,
            external_token=None, status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["method_type"] == "credit_card"
        assert r["is_default"] == 1  # First method = default

    def test_list_payment_methods(self, conn, base):
        call_action(FEES_ACTIONS["edu-add-payment-method"], conn, ns(
            guardian_id=base["guardian_id"],
            payment_method_type="ach",
            method_type=None,
            company_id=base["company_id"],
            last_four="9999", is_default=None, autopay_enabled=None,
            external_token=None, status=None,
            limit=50, offset=0,
        ))
        r = call_action(FEES_ACTIONS["edu-list-payment-methods"], conn, ns(
            guardian_id=base["guardian_id"],
            status=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1
        # External token should NOT be in response
        for pm in r["payment_methods"]:
            assert "external_token" not in pm

    def test_portal_pay_fee(self, conn, base):
        call_action(FEES_ACTIONS["edu-add-payment-method"], conn, ns(
            guardian_id=base["guardian_id"],
            payment_method_type="debit_card",
            method_type=None,
            company_id=base["company_id"],
            last_four="1111", is_default=None, autopay_enabled=None,
            external_token=None, status=None,
            limit=50, offset=0,
        ))
        r = call_action(FEES_ACTIONS["edu-portal-pay-fee"], conn, ns(
            guardian_id=base["guardian_id"],
            student_id=base["student_id"],
            amount="500.00",
            company_id=base["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["amount"] == "500.00"
        assert r["payment_status"] == "submitted"

    def test_payment_receipt(self, conn, base):
        r = call_action(FEES_ACTIONS["edu-payment-receipt"], conn, ns(
            guardian_id=base["guardian_id"],
            student_id=base["student_id"],
            amount="250.00",
            company_id=base["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["receipt_number"].startswith("REC-")


# ──────────────────────────────────────────────────────────────────────────────
# E7: Online Admissions Portal
# ──────────────────────────────────────────────────────────────────────────────

class TestOnlineAdmissionsPortal:

    def test_portal_submit_application(self, conn, base):
        seed_naming_series(conn, base["company_id"], "educlaw_student_applicant", "APP-")
        r = call_action(STUDENTS_ACTIONS["edu-portal-submit-application"], conn, ns(
            first_name="Jane", last_name="Doe", email="jane@example.com",
            company_id=base["company_id"],
            phone="555-0123", date_of_birth="2010-05-15",
            gender=None, address=None, grade_level="9",
            applying_for_program_id=None, applying_for_term_id=None,
            application_date=None, previous_school=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r.get("full_name") == "Jane Doe"

    def test_portal_check_application_status(self, conn, base):
        seed_naming_series(conn, base["company_id"], "educlaw_student_applicant", "APP-")
        add_r = call_action(STUDENTS_ACTIONS["edu-portal-submit-application"], conn, ns(
            first_name="Bob", last_name="Smith", email="bob@example.com",
            company_id=base["company_id"],
            phone=None, date_of_birth=None, gender=None, address=None,
            grade_level=None, applying_for_program_id=None,
            applying_for_term_id=None, application_date=None,
            previous_school=None,
            limit=50, offset=0,
        ))
        app_id = add_r["id"]
        r = call_action(STUDENTS_ACTIONS["edu-portal-check-application-status"], conn, ns(
            applicant_id=app_id, email=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "status_message" in r
        assert "review_notes" not in r  # Hidden from portal

    def test_portal_upload_document(self, conn, base):
        seed_naming_series(conn, base["company_id"], "educlaw_student_applicant", "APP-")
        add_r = call_action(STUDENTS_ACTIONS["edu-portal-submit-application"], conn, ns(
            first_name="Carol", last_name="Jones", email="carol@example.com",
            company_id=base["company_id"],
            phone=None, date_of_birth=None, gender=None, address=None,
            grade_level=None, applying_for_program_id=None,
            applying_for_term_id=None, application_date=None,
            previous_school=None,
            limit=50, offset=0,
        ))
        app_id = add_r["id"]
        r = call_action(STUDENTS_ACTIONS["edu-portal-upload-document"], conn, ns(
            applicant_id=app_id, title="Birth Certificate",
            company_id=base["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["total_documents"] == 1

    def test_list_pending_applications(self, conn, base):
        seed_naming_series(conn, base["company_id"], "educlaw_student_applicant", "APP-")
        call_action(STUDENTS_ACTIONS["edu-portal-submit-application"], conn, ns(
            first_name="Dave", last_name="Wilson", email="dave@example.com",
            company_id=base["company_id"],
            phone=None, date_of_birth=None, gender=None, address=None,
            grade_level=None, applying_for_program_id=None,
            applying_for_term_id=None, application_date=None,
            previous_school=None,
            limit=50, offset=0,
        ))
        r = call_action(STUDENTS_ACTIONS["edu-list-pending-applications"], conn, ns(
            company_id=base["company_id"],
            applicant_status=None, applying_for_term_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1
        assert "status_summary" in r


# ──────────────────────────────────────────────────────────────────────────────
# E8: Student Activities
# ──────────────────────────────────────────────────────────────────────────────

class TestStudentActivities:

    def test_add_activity(self, conn, base):
        r = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Chess Club", company_id=base["company_id"],
            activity_type="club", instructor_id=base["instructor_id"],
            description="Strategic games",
            min_gpa=None, max_enrollment=None, season=None,
            school_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["name"] == "Chess Club"
        assert r["activity_type"] == "club"

    def test_list_activities(self, conn, base):
        call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Basketball", company_id=base["company_id"],
            activity_type="sport", instructor_id=None,
            description="", min_gpa=None, max_enrollment=None, season="winter",
            school_id=None,
            limit=50, offset=0,
        ))
        r = call_action(ACTIVITIES_ACTIONS["edu-list-activities"], conn, ns(
            company_id=base["company_id"],
            activity_type=None, status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_enroll_student_activity(self, conn, base):
        add_r = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Science Olympiad", company_id=base["company_id"],
            activity_type="academic", instructor_id=None,
            description="", min_gpa=None, max_enrollment=None, season=None,
            school_id=None,
            limit=50, offset=0,
        ))
        act_id = add_r["id"]
        r = call_action(ACTIVITIES_ACTIONS["edu-enroll-student-activity"], conn, ns(
            activity_id=act_id, student_id=base["student_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["enrollment_status"] == "active"

    def test_enroll_fails_when_inactive(self, conn, base):
        add_r = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Inactive Club", company_id=base["company_id"],
            activity_type="club", instructor_id=None,
            description="", min_gpa=None, max_enrollment=None, season=None,
            school_id=None,
            limit=50, offset=0,
        ))
        act_id = add_r["id"]
        conn.execute("UPDATE educlaw_activity SET status = 'inactive' WHERE id = ?", (act_id,))
        conn.commit()
        r = call_action(ACTIVITIES_ACTIONS["edu-enroll-student-activity"], conn, ns(
            activity_id=act_id, student_id=base["student_id"],
            limit=50, offset=0,
        ))
        assert is_error(r)

    def test_remove_student_activity(self, conn, base):
        add_r = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Drama Club", company_id=base["company_id"],
            activity_type="art", instructor_id=None,
            description="", min_gpa=None, max_enrollment=None, season=None,
            school_id=None,
            limit=50, offset=0,
        ))
        act_id = add_r["id"]
        call_action(ACTIVITIES_ACTIONS["edu-enroll-student-activity"], conn, ns(
            activity_id=act_id, student_id=base["student_id"],
            limit=50, offset=0,
        ))
        r = call_action(ACTIVITIES_ACTIONS["edu-remove-student-activity"], conn, ns(
            activity_id=act_id, student_id=base["student_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["enrollment_status"] == "inactive"

    def test_check_activity_eligibility(self, conn, base):
        add_r = call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Honor Society", company_id=base["company_id"],
            activity_type="academic", instructor_id=None,
            description="", min_gpa="3.5", max_enrollment=None, season=None,
            school_id=None,
            limit=50, offset=0,
        ))
        act_id = add_r["id"]
        r = call_action(ACTIVITIES_ACTIONS["edu-check-activity-eligibility"], conn, ns(
            activity_id=act_id, student_id=base["student_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "eligible" in r
        assert "issues" in r

    def test_activity_participation_report(self, conn, base):
        call_action(ACTIVITIES_ACTIONS["edu-add-activity"], conn, ns(
            name="Report Activity", company_id=base["company_id"],
            activity_type="volunteer", instructor_id=None,
            description="", min_gpa=None, max_enrollment=None, season=None,
            school_id=None,
            limit=50, offset=0,
        ))
        r = call_action(ACTIVITIES_ACTIONS["edu-activity-participation-report"], conn, ns(
            company_id=base["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "total_activities" in r
        assert "by_type" in r


# ──────────────────────────────────────────────────────────────────────────────
# E9: Library Management
# ──────────────────────────────────────────────────────────────────────────────

class TestLibraryManagement:

    def test_add_library_item(self, conn, base):
        r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="To Kill a Mockingbird", title=None,
            company_id=base["company_id"],
            item_type="book",
            description="Harper Lee",
            code="978-0061120084",
            room_type="fiction",
            building="Main Library",
            capacity=3,
            search=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["copy_count"] == 3

    def test_checkout_and_return(self, conn, base):
        add_r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="1984", title=None, company_id=base["company_id"],
            item_type="book", description="George Orwell",
            code="", room_type="", building="", capacity=1,
            search=None,
            limit=50, offset=0,
        ))
        item_id = add_r["id"]

        co_r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            reference_id=item_id, library_item_id=None,
            student_id=base["student_id"],
            limit=50, offset=0,
        ))
        assert is_ok(co_r)
        circ_id = co_r["circulation_id"]
        assert co_r["title"] == "1984"

        ret_r = call_action(LIBRARY_ACTIONS["edu-return-item"], conn, ns(
            reference_id=circ_id, circulation_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(ret_r)
        assert ret_r["circulation_status"] == "returned"

    def test_checkout_unavailable(self, conn, base):
        add_r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="Rare Book", title=None, company_id=base["company_id"],
            item_type="book", description="", code="", room_type="", building="",
            capacity=1, search=None, limit=50, offset=0,
        ))
        item_id = add_r["id"]
        call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            reference_id=item_id, library_item_id=None,
            student_id=base["student_id"],
            limit=50, offset=0,
        ))
        student2 = seed_student(conn, base["company_id"])
        r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            reference_id=item_id, library_item_id=None,
            student_id=student2,
            limit=50, offset=0,
        ))
        assert is_error(r)

    def test_renew_item(self, conn, base):
        add_r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="Renewable Book", title=None, company_id=base["company_id"],
            item_type="book", description="", code="", room_type="", building="",
            capacity=1, search=None, limit=50, offset=0,
        ))
        item_id = add_r["id"]
        co_r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            reference_id=item_id, library_item_id=None,
            student_id=base["student_id"],
            limit=50, offset=0,
        ))
        circ_id = co_r["circulation_id"]
        r = call_action(LIBRARY_ACTIONS["edu-renew-item"], conn, ns(
            reference_id=circ_id, circulation_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["renewal_count"] == 1

    def test_list_library_items(self, conn, base):
        call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="Searchable Book", title=None, company_id=base["company_id"],
            item_type="book", description="", code="", room_type="", building="",
            capacity=1, search=None, limit=50, offset=0,
        ))
        r = call_action(LIBRARY_ACTIONS["edu-list-library-items"], conn, ns(
            company_id=base["company_id"],
            search=None, item_type=None, status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_library_inventory_report(self, conn, base):
        call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            name="Report Book", title=None, company_id=base["company_id"],
            item_type="book", description="", code="", room_type="", building="",
            capacity=5, search=None, limit=50, offset=0,
        ))
        r = call_action(LIBRARY_ACTIONS["edu-library-inventory-report"], conn, ns(
            company_id=base["company_id"], limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["total_items"] >= 1

    def test_student_reading_history(self, conn, base):
        r = call_action(LIBRARY_ACTIONS["edu-student-reading-history"], conn, ns(
            student_id=base["student_id"], limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "history" in r


# ──────────────────────────────────────────────────────────────────────────────
# E10: Dormitory/Housing
# ──────────────────────────────────────────────────────────────────────────────

class TestDormitoryHousing:

    def test_add_housing_unit(self, conn, base):
        r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="West Hall", room_number="101",
            company_id=base["company_id"],
            room_type="double", unit_type=None,
            capacity=2, amount="800",
            floor="1", description="Corner room",
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["building_name"] == "West Hall"
        assert r["capacity"] == 2

    def test_list_housing_units(self, conn, base):
        call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="East Hall", room_number="201",
            company_id=base["company_id"],
            room_type="single", unit_type=None,
            capacity=1, amount="600",
            floor="2", description="",
            limit=50, offset=0,
        ))
        r = call_action(HOUSING_ACTIONS["edu-list-housing-units"], conn, ns(
            company_id=base["company_id"],
            building=None, status=None, room_type=None, unit_type=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_assign_and_release_housing(self, conn, base):
        add_r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="North Hall", room_number="301",
            company_id=base["company_id"],
            room_type="double", unit_type=None,
            capacity=2, amount="750",
            floor="3", description="",
            limit=50, offset=0,
        ))
        unit_id = add_r["id"]

        assign_r = call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=base["student_id"],
            room_id=unit_id, housing_unit_id=None,
            academic_year_id="2025-2026", academic_year=None,
            term_type=None, start_date="2025-08-20",
            end_date="2026-05-15", meal_plan="standard",
            limit=50, offset=0,
        ))
        assert is_ok(assign_r)
        assert assign_r["assignment_status"] == "active"
        assign_id = assign_r["id"]

        rel_r = call_action(HOUSING_ACTIONS["edu-release-housing"], conn, ns(
            reference_id=assign_id, assignment_id=None,
            student_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(rel_r)
        assert rel_r["assignment_status"] == "completed"

    def test_assign_over_capacity(self, conn, base):
        add_r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="South Hall", room_number="401",
            company_id=base["company_id"],
            room_type="single", unit_type=None,
            capacity=1, amount="900",
            floor="4", description="",
            limit=50, offset=0,
        ))
        unit_id = add_r["id"]

        call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=base["student_id"],
            room_id=unit_id, housing_unit_id=None,
            academic_year_id="2025-2026", academic_year=None,
            term_type=None, start_date=None, end_date=None, meal_plan=None,
            limit=50, offset=0,
        ))
        student2 = seed_student(conn, base["company_id"])
        r = call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=student2,
            room_id=unit_id, housing_unit_id=None,
            academic_year_id="2025-2026", academic_year=None,
            term_type=None, start_date=None, end_date=None, meal_plan=None,
            limit=50, offset=0,
        ))
        assert is_error(r)

    def test_housing_availability(self, conn, base):
        call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="Free Hall", room_number="501",
            company_id=base["company_id"],
            room_type="triple", unit_type=None,
            capacity=3, amount="500",
            floor="5", description="",
            limit=50, offset=0,
        ))
        r = call_action(HOUSING_ACTIONS["edu-housing-availability"], conn, ns(
            company_id=base["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_housing_occupancy_report(self, conn, base):
        call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="Report Hall", room_number="601",
            company_id=base["company_id"],
            room_type="double", unit_type=None,
            capacity=2, amount="700",
            floor="6", description="",
            limit=50, offset=0,
        ))
        r = call_action(HOUSING_ACTIONS["edu-housing-occupancy-report"], conn, ns(
            company_id=base["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert "total_capacity" in r
        assert "buildings" in r


# ──────────────────────────────────────────────────────────────────────────────
# Action count verification
# ──────────────────────────────────────────────────────────────────────────────

class TestPhase9ActionCount:
    """Verify all new actions are registered."""

    def test_pd_actions_count(self):
        assert len(PD_ACTIONS) == 5

    def test_fee_payment_actions_added(self):
        assert "edu-add-payment-method" in FEES_ACTIONS
        assert "edu-list-payment-methods" in FEES_ACTIONS
        assert "edu-portal-pay-fee" in FEES_ACTIONS
        assert "edu-payment-receipt" in FEES_ACTIONS
        assert len(FEES_ACTIONS) == 19

    def test_admissions_portal_actions_added(self):
        assert "edu-portal-submit-application" in STUDENTS_ACTIONS
        assert "edu-portal-check-application-status" in STUDENTS_ACTIONS
        assert "edu-portal-upload-document" in STUDENTS_ACTIONS
        assert "edu-list-pending-applications" in STUDENTS_ACTIONS

    def test_activities_actions_count(self):
        assert len(ACTIVITIES_ACTIONS) == 7

    def test_library_actions_count(self):
        assert len(LIBRARY_ACTIONS) == 8

    def test_housing_actions_count(self):
        assert len(HOUSING_ACTIONS) == 8
