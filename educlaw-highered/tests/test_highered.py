"""Unit tests for EduClaw Higher Education — all 7 domains.

Tests cover: registrar (12), records (10), finaid (10), alumni (8), faculty (8),
             admissions (6), reports (6).
Total: 60+ tests.
"""
import pytest
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(os.path.dirname(_HERE), "scripts")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from helpers import (
    call_action, ns, get_conn,
    seed_company, seed_degree_program, seed_course, seed_section,
    seed_student_record, seed_enrollment, seed_faculty, seed_alumnus,
    seed_aid_package, seed_application,
)

from registrar import (
    add_degree_program, update_degree_program, list_degree_programs,
    add_course, update_course, list_courses,
    add_section, list_sections,
    add_enrollment, drop_enrollment, list_enrollments,
    academic_calendar_report,
)
from records import (
    get_student_record, list_student_records,
    generate_transcript, calculate_gpa, degree_audit,
    update_academic_standing,
    add_hold, remove_hold, list_holds,
    academic_standing_report,
)
from finaid import (
    add_aid_package as finaid_add_aid_package,
    update_aid_package, get_aid_package, list_aid_packages,
    add_disbursement, list_disbursements,
    calculate_sap, need_analysis, aid_summary_report, award_letter_report,
)
from alumni import (
    add_alumnus, update_alumnus, list_alumni,
    add_alumni_event, list_alumni_events,
    add_giving_record, alumni_giving_report, alumni_engagement_report,
)
from faculty import (
    add_faculty, update_faculty, list_faculty,
    add_course_assignment, list_course_assignments,
    add_research_grant, list_research_grants,
    faculty_workload_report,
)
from admissions import (
    add_application, list_applications, get_application,
    add_admission_decision, update_admission_decision, list_admission_decisions,
)
from reports import (
    enrollment_report, retention_report, degree_completion_report,
    alumni_giving_summary, faculty_workload_summary, status_action,
)


# ── Common fixture ────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db_path):
    """Seed common prerequisite data."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    prog_id = seed_degree_program(conn, cid)
    yield conn, cid, prog_id
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRAR domain
# ══════════════════════════════════════════════════════════════════════════════

class TestAddDegreeProgram:
    def test_happy_path(self, setup):
        conn, cid, _ = setup
        result = call_action(add_degree_program, conn, ns(
            company_id=cid, name="Biology", degree_type="bachelor",
            department="Sciences", credits_required=120,
            program_status="active",
        ))
        assert result["status"] == "ok"
        assert result["name"] == "Biology"
        assert result["degree_type"] == "bachelor"
        assert "naming_series" in result
        assert result["program_status"] == "active"

    def test_missing_name(self, setup):
        conn, cid, _ = setup
        result = call_action(add_degree_program, conn, ns(
            company_id=cid, name=None, degree_type="bachelor",
            department="", credits_required=0, program_status="active",
        ))
        assert result["status"] == "error"
        assert "name" in result["message"].lower()

    def test_invalid_degree_type(self, setup):
        conn, cid, _ = setup
        result = call_action(add_degree_program, conn, ns(
            company_id=cid, name="Test", degree_type="phd",
            department="", credits_required=0, program_status="active",
        ))
        assert result["status"] == "error"
        assert "degree_type" in result["message"]


class TestUpdateDegreeProgram:
    def test_update_name(self, setup):
        conn, cid, prog_id = setup
        result = call_action(update_degree_program, conn, ns(
            id=prog_id, name="Updated CS", degree_type=None,
            department=None, credits_required=None, program_status=None,
        ))
        assert result["status"] == "ok"
        assert result["updated"] is True

    def test_not_found(self, setup):
        conn, cid, _ = setup
        result = call_action(update_degree_program, conn, ns(
            id="nonexistent", name="X", degree_type=None,
            department=None, credits_required=None, program_status=None,
        ))
        assert result["status"] == "error"


class TestListDegreePrograms:
    def test_returns_programs(self, setup):
        conn, cid, _ = setup
        result = call_action(list_degree_programs, conn, ns(
            company_id=cid, department=None, program_status=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestAddCourse:
    def test_happy_path(self, setup):
        conn, cid, _ = setup
        result = call_action(add_course, conn, ns(
            company_id=cid, code="CS201", name="Data Structures",
            credits=4, department="Engineering",
            prerequisites="CS101", description="Advanced CS course",
        ))
        assert result["status"] == "ok"
        assert result["code"] == "CS201"
        assert result["credits"] == 4

    def test_duplicate_code(self, setup):
        conn, cid, _ = setup
        seed_course(conn, cid, code="DUP100")
        result = call_action(add_course, conn, ns(
            company_id=cid, code="DUP100", name="Dup",
            credits=3, department="", prerequisites="", description="",
        ))
        assert result["status"] == "error"
        assert "already exists" in result["message"]


class TestAddSection:
    def test_happy_path(self, setup):
        conn, cid, _ = setup
        course_id = seed_course(conn, cid)
        result = call_action(add_section, conn, ns(
            company_id=cid, course_id=course_id, term="Spring",
            year=2026, instructor="Dr. X", capacity=25,
            schedule="TTh 2:00", location="Room 200",
        ))
        assert result["status"] == "ok"
        assert result["section_status"] == "open"

    def test_invalid_course(self, setup):
        conn, cid, _ = setup
        result = call_action(add_section, conn, ns(
            company_id=cid, course_id="bad-id", term="Fall",
            year=2026, instructor="", capacity=30,
            schedule="", location="",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]


class TestEnrollment:
    def test_add_enrollment(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        student_id = seed_student_record(conn, cid, prog_id)
        result = call_action(add_enrollment, conn, ns(
            company_id=cid, student_id=student_id,
            section_id=section_id, enrollment_date=None,
        ))
        assert result["status"] == "ok"
        assert result["enrollment_status"] == "enrolled"
        # Verify enrolled count incremented
        sec = conn.execute("SELECT enrolled FROM highered_section WHERE id=?", (section_id,)).fetchone()
        assert sec["enrolled"] == 1

    def test_duplicate_enrollment(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        student_id = seed_student_record(conn, cid, prog_id)
        seed_enrollment(conn, student_id, section_id, cid)
        result = call_action(add_enrollment, conn, ns(
            company_id=cid, student_id=student_id,
            section_id=section_id, enrollment_date=None,
        ))
        assert result["status"] == "error"
        assert "already enrolled" in result["message"]

    def test_section_at_capacity(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid, capacity=1)
        s1 = seed_student_record(conn, cid, prog_id, name="S1")
        seed_enrollment(conn, s1, section_id, cid)
        s2 = seed_student_record(conn, cid, prog_id, name="S2")
        result = call_action(add_enrollment, conn, ns(
            company_id=cid, student_id=s2,
            section_id=section_id, enrollment_date=None,
        ))
        assert result["status"] == "error"
        assert "capacity" in result["message"].lower()

    def test_drop_enrollment(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        student_id = seed_student_record(conn, cid, prog_id)
        eid = seed_enrollment(conn, student_id, section_id, cid)
        result = call_action(drop_enrollment, conn, ns(id=eid))
        assert result["status"] == "ok"
        assert result["enrollment_status"] == "dropped"

    def test_drop_already_dropped(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        student_id = seed_student_record(conn, cid, prog_id)
        eid = seed_enrollment(conn, student_id, section_id, cid, status="dropped")
        result = call_action(drop_enrollment, conn, ns(id=eid))
        assert result["status"] == "error"


class TestListEnrollments:
    def test_filter_by_student(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        student_id = seed_student_record(conn, cid, prog_id)
        seed_enrollment(conn, student_id, section_id, cid)
        result = call_action(list_enrollments, conn, ns(
            company_id=cid, student_id=student_id,
            section_id=None, enrollment_status=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# RECORDS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestStudentRecord:
    def test_get_by_student_id(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        result = call_action(get_student_record, conn, ns(id=None, student_id=sid))
        assert result["status"] == "ok"
        assert result["student_id"] == sid

    def test_not_found(self, setup):
        conn, cid, _ = setup
        result = call_action(get_student_record, conn, ns(id="bad", student_id=None))
        assert result["status"] == "error"

    def test_list_records(self, setup):
        conn, cid, prog_id = setup
        seed_student_record(conn, cid, prog_id)
        result = call_action(list_student_records, conn, ns(
            company_id=cid, program_id=None, academic_standing=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestGPACalculation:
    def test_gpa_with_grades(self, setup):
        conn, cid, prog_id = setup
        student_id = seed_student_record(conn, cid, prog_id, gpa="0.00")
        c1 = seed_course(conn, cid, code="GPA101", credits=3)
        c2 = seed_course(conn, cid, code="GPA102", credits=3)
        s1 = seed_section(conn, c1, cid)
        s2 = seed_section(conn, c2, cid)
        seed_enrollment(conn, student_id, s1, cid, status="completed", grade="A")
        seed_enrollment(conn, student_id, s2, cid, status="completed", grade="B")
        result = call_action(calculate_gpa, conn, ns(student_id=student_id))
        assert result["status"] == "ok"
        assert result["gpa"] == "3.50"  # (4.0*3 + 3.0*3) / 6 = 3.50
        assert result["total_credits"] == 6

    def test_gpa_no_grades(self, setup):
        conn, cid, prog_id = setup
        student_id = seed_student_record(conn, cid, prog_id, gpa="0.00")
        result = call_action(calculate_gpa, conn, ns(student_id=student_id))
        assert result["status"] == "ok"
        assert result["gpa"] == "0.00"


class TestDegreeAudit:
    def test_progress_tracking(self, setup):
        conn, cid, prog_id = setup
        student_id = seed_student_record(conn, cid, prog_id)
        c1 = seed_course(conn, cid, code="DA101", credits=30)
        s1 = seed_section(conn, c1, cid)
        seed_enrollment(conn, student_id, s1, cid, status="completed", grade="A")
        result = call_action(degree_audit, conn, ns(student_id=student_id))
        assert result["status"] == "ok"
        assert result["credits_earned"] == 30
        assert result["credits_required"] == 120
        assert result["credits_remaining"] == 90
        assert result["progress_percent"] == 25.0


class TestAcademicStanding:
    def test_update_standing(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        result = call_action(update_academic_standing, conn, ns(
            student_id=sid, academic_standing="probation",
        ))
        assert result["status"] == "ok"
        assert result["academic_standing"] == "probation"
        assert result["previous_standing"] == "good"

    def test_invalid_standing(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        result = call_action(update_academic_standing, conn, ns(
            student_id=sid, academic_standing="expelled",
        ))
        assert result["status"] == "error"


class TestHolds:
    def test_add_and_remove_hold(self, setup):
        conn, cid, _ = setup
        sid = str("test-student-id")
        result = call_action(add_hold, conn, ns(
            company_id=cid, student_id=sid, hold_type="financial",
            reason="Unpaid tuition", placed_by="Bursar",
        ))
        assert result["status"] == "ok"
        assert result["hold_status"] == "active"
        hold_id = result["id"]

        result2 = call_action(remove_hold, conn, ns(id=hold_id))
        assert result2["status"] == "ok"
        assert result2["hold_status"] == "removed"

    def test_remove_already_removed(self, setup):
        conn, cid, _ = setup
        result = call_action(add_hold, conn, ns(
            company_id=cid, student_id="s1", hold_type="academic",
            reason="Test", placed_by="Dean",
        ))
        hold_id = result["id"]
        call_action(remove_hold, conn, ns(id=hold_id))
        result2 = call_action(remove_hold, conn, ns(id=hold_id))
        assert result2["status"] == "error"

    def test_list_holds_filter(self, setup):
        conn, cid, _ = setup
        call_action(add_hold, conn, ns(
            company_id=cid, student_id="s1", hold_type="financial",
            reason="Test", placed_by="X",
        ))
        result = call_action(list_holds, conn, ns(
            company_id=cid, student_id="s1", hold_status="active",
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1


class TestAcademicStandingReport:
    def test_report(self, setup):
        conn, cid, prog_id = setup
        seed_student_record(conn, cid, prog_id)
        result = call_action(academic_standing_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["total_students"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# FINAID domain
# ══════════════════════════════════════════════════════════════════════════════

class TestAidPackage:
    def test_add_package(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        result = call_action(finaid_add_aid_package, conn, ns(
            company_id=cid, student_id=sid, aid_year="2025-2026",
            total_cost="50000", efc="10000", total_need="40000",
            grants="5000", scholarships="5000", loans="3000", work_study="2000",
            package_status=None,
        ))
        assert result["status"] == "ok"
        assert result["total_aid"] == "15000.00"
        assert result["package_status"] == "draft"

    def test_update_package_amounts(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid, package_status="draft")
        result = call_action(update_aid_package, conn, ns(
            id=pkg_id, aid_year=None, total_cost=None, efc=None,
            total_need=None, grants="10000", scholarships=None,
            loans=None, work_study=None, package_status=None,
        ))
        assert result["status"] == "ok"

    def test_get_package(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid)
        result = call_action(get_aid_package, conn, ns(id=pkg_id))
        assert result["status"] == "ok"
        assert result["id"] == pkg_id


class TestDisbursement:
    def test_add_disbursement(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid, package_status="offered")
        result = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg_id, amount="5000",
            aid_type="grant", fund_source="Federal", disbursement_date=None,
        ))
        assert result["status"] == "ok"
        assert result["amount"] == "5000.00"
        assert result["disbursement_status"] == "pending"

    def test_disbursement_requires_offered_package(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid, package_status="draft")
        result = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg_id, amount="1000",
            aid_type="grant", fund_source="", disbursement_date=None,
        ))
        assert result["status"] == "error"

    def test_zero_amount_rejected(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid, package_status="offered")
        result = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg_id, amount="0",
            aid_type="grant", fund_source="", disbursement_date=None,
        ))
        assert result["status"] == "error"


class TestNeedAnalysis:
    def test_need_calculation(self, setup):
        conn, cid, _ = setup
        result = call_action(need_analysis, conn, ns(
            student_id="s1", total_cost="50000", efc="15000",
        ))
        assert result["status"] == "ok"
        assert result["financial_need"] == "35000.00"


class TestCalculateSAP:
    def test_sap_met(self, setup):
        conn, cid, prog_id = setup
        student_id = seed_student_record(conn, cid, prog_id, gpa="3.50")
        c1 = seed_course(conn, cid, code="SAP101", credits=30)
        s1 = seed_section(conn, c1, cid)
        seed_enrollment(conn, student_id, s1, cid, status="completed", grade="A")
        result = call_action(calculate_sap, conn, ns(student_id=student_id))
        assert result["status"] == "ok"
        assert result["sap_met"] is True


# ══════════════════════════════════════════════════════════════════════════════
# ALUMNI domain
# ══════════════════════════════════════════════════════════════════════════════

class TestAlumnus:
    def test_add_alumnus(self, setup):
        conn, cid, _ = setup
        result = call_action(add_alumnus, conn, ns(
            company_id=cid, name="Jane Doe", email="jane@alumni.edu",
            graduation_year=2015, degree_program="Biology",
            employer="BioTech", job_title="Researcher",
            engagement_level="medium",
        ))
        assert result["status"] == "ok"
        assert result["name"] == "Jane Doe"
        assert "naming_series" in result

    def test_update_alumnus(self, setup):
        conn, cid, _ = setup
        aid = seed_alumnus(conn, cid)
        result = call_action(update_alumnus, conn, ns(
            id=aid, name=None, email=None, degree_program=None,
            employer="New Corp", job_title="Manager",
            graduation_year=None, engagement_level="high",
        ))
        assert result["status"] == "ok"

    def test_list_alumni(self, setup):
        conn, cid, _ = setup
        seed_alumnus(conn, cid)
        result = call_action(list_alumni, conn, ns(
            company_id=cid, graduation_year=None,
            engagement_level=None, is_donor=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestAlumniEvent:
    def test_add_event(self, setup):
        conn, cid, _ = setup
        result = call_action(add_alumni_event, conn, ns(
            company_id=cid, name="Homecoming 2026",
            event_date="2026-10-15", event_type="reunion",
            attendees=200,
        ))
        assert result["status"] == "ok"
        assert result["event_type"] == "reunion"


class TestGiving:
    def test_add_giving_record(self, setup):
        conn, cid, _ = setup
        aid = seed_alumnus(conn, cid)
        result = call_action(add_giving_record, conn, ns(
            company_id=cid, alumnus_id=aid, amount="5000",
            giving_date="2026-01-15", campaign="Annual Fund",
            gift_type="cash",
        ))
        assert result["status"] == "ok"
        assert result["amount"] == "5000.00"
        # Check donor flag updated
        alum = conn.execute("SELECT is_donor, total_giving FROM highered_alumnus WHERE id=?", (aid,)).fetchone()
        assert alum["is_donor"] == 1
        assert alum["total_giving"] == "5000.00"

    def test_giving_invalid_alumnus(self, setup):
        conn, cid, _ = setup
        result = call_action(add_giving_record, conn, ns(
            company_id=cid, alumnus_id="bad-id", amount="100",
            giving_date="2026-01-01", campaign="", gift_type="cash",
        ))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# FACULTY domain
# ══════════════════════════════════════════════════════════════════════════════

class TestFaculty:
    def test_add_faculty(self, setup):
        conn, cid, _ = setup
        result = call_action(add_faculty, conn, ns(
            company_id=cid, name="Dr. Smith", email="smith@univ.edu",
            department="Physics", rank="associate_professor",
            tenure_status="tenure_track", hire_date="2022-08-01",
        ))
        assert result["status"] == "ok"
        assert result["rank"] == "associate_professor"
        assert "naming_series" in result

    def test_invalid_rank(self, setup):
        conn, cid, _ = setup
        result = call_action(add_faculty, conn, ns(
            company_id=cid, name="X", email="",
            department="", rank="dean",
            tenure_status="non_tenure", hire_date="",
        ))
        assert result["status"] == "error"

    def test_list_faculty(self, setup):
        conn, cid, _ = setup
        seed_faculty(conn, cid)
        result = call_action(list_faculty, conn, ns(
            company_id=cid, department=None, rank=None,
            tenure_status=None, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestCourseAssignment:
    def test_assign_faculty(self, setup):
        conn, cid, _ = setup
        fid = seed_faculty(conn, cid)
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        result = call_action(add_course_assignment, conn, ns(
            company_id=cid, faculty_id=fid, section_id=section_id,
            role="primary",
        ))
        assert result["status"] == "ok"
        assert result["role"] == "primary"

    def test_duplicate_assignment(self, setup):
        conn, cid, _ = setup
        fid = seed_faculty(conn, cid)
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        call_action(add_course_assignment, conn, ns(
            company_id=cid, faculty_id=fid, section_id=section_id, role="primary",
        ))
        result = call_action(add_course_assignment, conn, ns(
            company_id=cid, faculty_id=fid, section_id=section_id, role="secondary",
        ))
        assert result["status"] == "error"


class TestResearchGrant:
    def test_add_grant(self, setup):
        conn, cid, _ = setup
        fid = seed_faculty(conn, cid)
        result = call_action(add_research_grant, conn, ns(
            company_id=cid, faculty_id=fid, title="AI Research",
            funding_agency="NSF", amount="250000",
            start_date="2026-01-01", end_date="2028-12-31",
            grant_status="active",
        ))
        assert result["status"] == "ok"
        assert result["amount"] == "250000.00"
        assert result["grant_status"] == "active"

    def test_invalid_faculty(self, setup):
        conn, cid, _ = setup
        result = call_action(add_research_grant, conn, ns(
            company_id=cid, faculty_id="bad", title="Test",
            funding_agency="", amount="0", start_date="",
            end_date="", grant_status="proposed",
        ))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# ADMISSIONS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestAddApplication:
    def test_happy_path(self, setup):
        conn, cid, prog_id = setup
        result = call_action(add_application, conn, ns(
            company_id=cid, name="Alice Johnson", email="alice@test.com",
            phone="555-0100", program_id=prog_id,
            application_date="2026-02-01", term="Fall", year=2026,
            gpa_incoming="3.80", test_scores="{}", documents="[]",
            reason="", scholarship_offered=None,
            placed_by=None, decision=None, decision_date=None,
            conditions=None, application_id=None, application_status=None,
        ))
        assert result["status"] == "ok"
        assert result["applicant_name"] == "Alice Johnson"
        assert result["application_status"] == "submitted"
        assert "naming_series" in result

    def test_missing_name(self, setup):
        conn, cid, prog_id = setup
        result = call_action(add_application, conn, ns(
            company_id=cid, name=None, email="", phone="",
            program_id=None, application_date=None, term=None,
            year=None, gpa_incoming=None, test_scores=None,
            documents=None, reason=None, scholarship_offered=None,
            placed_by=None, decision=None, decision_date=None,
            conditions=None, application_id=None, application_status=None,
        ))
        assert result["status"] == "error"
        assert "name" in result["message"].lower()

    def test_invalid_program(self, setup):
        conn, cid, _ = setup
        result = call_action(add_application, conn, ns(
            company_id=cid, name="Bob", email="", phone="",
            program_id="nonexistent-prog", application_date=None,
            term=None, year=None, gpa_incoming=None,
            test_scores=None, documents=None, reason=None,
            scholarship_offered=None, placed_by=None,
            decision=None, decision_date=None, conditions=None,
            application_id=None, application_status=None,
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestListApplications:
    def test_list_with_filters(self, setup):
        conn, cid, prog_id = setup
        seed_application(conn, cid, prog_id)
        result = call_action(list_applications, conn, ns(
            company_id=cid, program_id=None,
            application_status=None, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1

    def test_filter_by_status(self, setup):
        conn, cid, prog_id = setup
        seed_application(conn, cid, prog_id, application_status="submitted")
        result = call_action(list_applications, conn, ns(
            company_id=cid, program_id=None,
            application_status="submitted", limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestGetApplication:
    def test_get_with_decisions(self, setup):
        conn, cid, prog_id = setup
        app_id = seed_application(conn, cid, prog_id)
        result = call_action(get_application, conn, ns(id=app_id))
        assert result["status"] == "ok"
        assert result["application"]["id"] == app_id
        assert isinstance(result["decisions"], list)

    def test_not_found(self, setup):
        conn, cid, _ = setup
        result = call_action(get_application, conn, ns(id="nonexistent"))
        assert result["status"] == "error"


class TestAdmissionDecision:
    def test_add_decision_admit(self, setup):
        conn, cid, prog_id = setup
        app_id = seed_application(conn, cid, prog_id)
        result = call_action(add_admission_decision, conn, ns(
            company_id=cid, application_id=app_id, decision="admit",
            placed_by="Dean Smith", decision_date="2026-03-01",
            conditions="", scholarship_offered="5000",
            reason="Strong candidate",
            # Extra args that may be on the namespace
            name=None, email=None, phone=None, program_id=None,
            application_date=None, term=None, year=None,
            gpa_incoming=None, test_scores=None, documents=None,
            application_status=None,
        ))
        assert result["status"] == "ok"
        assert result["decision"] == "admit"
        assert result["scholarship_offered"] == "5000.00"
        # Verify application status updated to "accepted"
        app = conn.execute(
            "SELECT application_status FROM highered_application WHERE id=?",
            (app_id,)
        ).fetchone()
        assert app["application_status"] == "accepted"

    def test_add_decision_deny(self, setup):
        conn, cid, prog_id = setup
        app_id = seed_application(conn, cid, prog_id)
        result = call_action(add_admission_decision, conn, ns(
            company_id=cid, application_id=app_id, decision="deny",
            placed_by="Committee", decision_date="2026-03-15",
            conditions="", scholarship_offered=None,
            reason="Below minimum GPA",
            name=None, email=None, phone=None, program_id=None,
            application_date=None, term=None, year=None,
            gpa_incoming=None, test_scores=None, documents=None,
            application_status=None,
        ))
        assert result["status"] == "ok"
        assert result["decision"] == "deny"
        app = conn.execute(
            "SELECT application_status FROM highered_application WHERE id=?",
            (app_id,)
        ).fetchone()
        assert app["application_status"] == "rejected"

    def test_invalid_decision(self, setup):
        conn, cid, prog_id = setup
        app_id = seed_application(conn, cid, prog_id)
        result = call_action(add_admission_decision, conn, ns(
            company_id=cid, application_id=app_id, decision="maybe",
            placed_by="", decision_date=None, conditions="",
            scholarship_offered=None, reason="",
            name=None, email=None, phone=None, program_id=None,
            application_date=None, term=None, year=None,
            gpa_incoming=None, test_scores=None, documents=None,
            application_status=None,
        ))
        assert result["status"] == "error"
        assert "decision" in result["message"].lower()

    def test_invalid_application(self, setup):
        conn, cid, _ = setup
        result = call_action(add_admission_decision, conn, ns(
            company_id=cid, application_id="bad-app-id", decision="admit",
            placed_by="", decision_date=None, conditions="",
            scholarship_offered=None, reason="",
            name=None, email=None, phone=None, program_id=None,
            application_date=None, term=None, year=None,
            gpa_incoming=None, test_scores=None, documents=None,
            application_status=None,
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestUpdateAdmissionDecision:
    def test_update_decision(self, setup):
        conn, cid, prog_id = setup
        app_id = seed_application(conn, cid, prog_id)
        # First add a decision
        r1 = call_action(add_admission_decision, conn, ns(
            company_id=cid, application_id=app_id, decision="waitlist",
            placed_by="Committee", decision_date="2026-03-01",
            conditions="", scholarship_offered=None, reason="",
            name=None, email=None, phone=None, program_id=None,
            application_date=None, term=None, year=None,
            gpa_incoming=None, test_scores=None, documents=None,
            application_status=None,
        ))
        dec_id = r1["id"]
        # Update it
        result = call_action(update_admission_decision, conn, ns(
            id=dec_id, decision="admit", decided_by="Dean",
            decision_date="2026-03-10", conditions="Maintain 3.0 GPA",
            scholarship_offered="10000", notes="Upgraded from waitlist",
        ))
        assert result["status"] == "ok"
        assert result["updated"] is True

    def test_not_found(self, setup):
        conn, cid, _ = setup
        result = call_action(update_admission_decision, conn, ns(
            id="bad-id", decision="admit", decided_by=None,
            decision_date=None, conditions=None,
            scholarship_offered=None, notes=None,
        ))
        assert result["status"] == "error"


class TestListAdmissionDecisions:
    def test_list_decisions(self, setup):
        conn, cid, prog_id = setup
        app_id = seed_application(conn, cid, prog_id)
        call_action(add_admission_decision, conn, ns(
            company_id=cid, application_id=app_id, decision="admit",
            placed_by="Dean", decision_date="2026-03-01",
            conditions="", scholarship_offered=None, reason="",
            name=None, email=None, phone=None, program_id=None,
            application_date=None, term=None, year=None,
            gpa_incoming=None, test_scores=None, documents=None,
            application_status=None,
        ))
        result = call_action(list_admission_decisions, conn, ns(
            company_id=cid, application_id=None,
            decision=None, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestReports:
    def test_enrollment_report(self, setup):
        conn, cid, prog_id = setup
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        sid = seed_student_record(conn, cid, prog_id)
        seed_enrollment(conn, sid, section_id, cid)
        result = call_action(enrollment_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["count"] >= 1

    def test_retention_report(self, setup):
        conn, cid, prog_id = setup
        seed_student_record(conn, cid, prog_id)
        result = call_action(retention_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["total_students"] >= 1
        assert result["retention_rate"] > 0

    def test_degree_completion_report(self, setup):
        conn, cid, prog_id = setup
        seed_student_record(conn, cid, prog_id)
        result = call_action(degree_completion_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"

    def test_alumni_giving_summary_empty(self, setup):
        conn, cid, _ = setup
        result = call_action(alumni_giving_summary, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["total_alumni"] == 0

    def test_faculty_workload_summary(self, setup):
        conn, cid, _ = setup
        seed_faculty(conn, cid)
        result = call_action(faculty_workload_summary, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["count"] >= 1

    def test_status(self, setup):
        conn, cid, _ = setup
        result = call_action(status_action, conn, ns())
        assert result["status"] == "ok"
        assert result["skill"] == "highered-educlaw-highered"
        assert "registrar" in result["domains"]
        assert "admissions" in result["domains"]


class TestTranscript:
    def test_generate_transcript(self, setup):
        conn, cid, prog_id = setup
        sid = seed_student_record(conn, cid, prog_id)
        course_id = seed_course(conn, cid, code="TR101")
        section_id = seed_section(conn, course_id, cid, term="Fall", year=2025)
        seed_enrollment(conn, sid, section_id, cid, status="completed", grade="A")
        result = call_action(generate_transcript, conn, ns(student_id=sid))
        assert result["status"] == "ok"
        assert result["student_id"] == sid
        assert len(result["terms"]) >= 1
        assert result["terms"][0]["courses"][0]["grade"] == "A"
