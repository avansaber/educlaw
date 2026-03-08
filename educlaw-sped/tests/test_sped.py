"""Unit tests for EduClaw SPED module.

Tests all 20 actions across 3 domains:
  iep (8): add-iep, list-ieps, get-iep, update-iep, activate-iep,
           add-iep-goal, list-iep-goals, update-iep-goal
  services (7): add-service, list-services, get-service, update-service,
                add-service-log, list-service-logs, service-hours-report
  compliance (4): compliance-check, overdue-iep-report,
                  service-utilization-report, caseload-report
  + status (1)
"""
import pytest
from helpers import (
    call_action, ns, get_conn,
    seed_company, seed_iep, seed_iep_goal,
    seed_service, seed_service_log,
)

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from iep import (
    add_iep, list_ieps, get_iep, update_iep, activate_iep,
    add_iep_goal, list_iep_goals, update_iep_goal,
)
from services import (
    add_service, list_services, get_service, update_service,
    add_service_log, list_service_logs, service_hours_report,
)
from compliance import (
    compliance_check, overdue_iep_report,
    service_utilization_report, caseload_report,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db_path):
    """Seed common prerequisite data for SPED tests."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yield conn, cid
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# IEP DOMAIN
# ══════════════════════════════════════════════════════════════════════════════


class TestAddIep:
    def test_happy_path(self, setup):
        conn, cid = setup
        result = call_action(add_iep, conn, ns(
            student_id="student-1",
            iep_date="2025-10-15",
            review_date="2026-04-15",
            annual_review_date="2026-10-15",
            disability_category="specific_learning_disability",
            placement="general_education",
            lre_percentage="80",
            case_manager="Ms. Johnson",
            meeting_participants='["Ms. Johnson", "Dr. Smith"]',
            notes="Initial IEP",
            company_id=cid,
            user_id="admin",
        ))
        assert result["status"] == "ok"
        assert "id" in result
        assert result["iep_status"] == "draft"
        assert result["student_id"] == "student-1"

    def test_missing_student_id(self, setup):
        conn, cid = setup
        result = call_action(add_iep, conn, ns(
            student_id=None,
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"].lower()

    def test_defaults_iep_date_to_today(self, setup):
        conn, cid = setup
        result = call_action(add_iep, conn, ns(
            student_id="student-1",
            iep_date=None,
            review_date=None,
            annual_review_date=None,
            disability_category=None,
            placement=None,
            lre_percentage=None,
            case_manager=None,
            meeting_participants=None,
            notes=None,
            company_id=cid,
            user_id=None,
        ))
        assert result["status"] == "ok"
        assert result["iep_date"] != ""


class TestListIeps:
    def test_list_all(self, setup):
        conn, cid = setup
        seed_iep(conn, cid, "student-1")
        seed_iep(conn, cid, "student-2")
        result = call_action(list_ieps, conn, ns(
            student_id=None, iep_status=None, company_id=cid,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_filter_by_student(self, setup):
        conn, cid = setup
        seed_iep(conn, cid, "student-1")
        seed_iep(conn, cid, "student-2")
        result = call_action(list_ieps, conn, ns(
            student_id="student-1", iep_status=None, company_id=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_filter_by_status(self, setup):
        conn, cid = setup
        seed_iep(conn, cid, "student-1", iep_status="draft")
        seed_iep(conn, cid, "student-2", iep_status="active")
        result = call_action(list_ieps, conn, ns(
            student_id=None, iep_status="active", company_id=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1


class TestGetIep:
    def test_happy_path(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, "student-1")
        result = call_action(get_iep, conn, ns(iep_id=iep_id))
        assert result["status"] == "ok"
        assert result["id"] == iep_id
        assert "goals" in result
        assert "services" in result
        assert isinstance(result["meeting_participants"], list)

    def test_not_found(self, setup):
        conn, cid = setup
        result = call_action(get_iep, conn, ns(iep_id="nonexistent"))
        assert result["status"] == "error"

    def test_missing_id(self, setup):
        conn, cid = setup
        result = call_action(get_iep, conn, ns(iep_id=None))
        assert result["status"] == "error"


class TestUpdateIep:
    def test_update_draft(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, "student-1", iep_status="draft")
        result = call_action(update_iep, conn, ns(
            iep_id=iep_id,
            case_manager="Mr. New Manager",
            disability_category=None,
            iep_date=None, review_date=None, annual_review_date=None,
            placement=None, lre_percentage=None, meeting_participants=None,
            notes=None, user_id="admin",
        ))
        assert result["status"] == "ok"
        # Verify update persisted
        row = conn.execute("SELECT case_manager FROM sped_iep WHERE id = ?", (iep_id,)).fetchone()
        assert row["case_manager"] == "Mr. New Manager"

    def test_cannot_update_active(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, "student-1", iep_status="active")
        result = call_action(update_iep, conn, ns(
            iep_id=iep_id,
            case_manager="Mr. New Manager",
            disability_category=None,
            iep_date=None, review_date=None, annual_review_date=None,
            placement=None, lre_percentage=None, meeting_participants=None,
            notes=None, user_id="admin",
        ))
        assert result["status"] == "error"
        assert "active" in result["message"].lower()

    def test_no_fields_to_update(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, "student-1", iep_status="draft")
        result = call_action(update_iep, conn, ns(
            iep_id=iep_id,
            case_manager=None, disability_category=None,
            iep_date=None, review_date=None, annual_review_date=None,
            placement=None, lre_percentage=None, meeting_participants=None,
            notes=None, user_id=None,
        ))
        assert result["status"] == "error"
        assert "no fields" in result["message"].lower()


class TestActivateIep:
    def test_activate_draft(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, "student-1", iep_status="draft")
        result = call_action(activate_iep, conn, ns(
            iep_id=iep_id, user_id="admin",
        ))
        assert result["status"] == "ok"
        assert result["iep_status"] == "active"

    def test_expires_previous_active(self, setup):
        conn, cid = setup
        old_id = seed_iep(conn, cid, "student-1", iep_status="active")
        new_id = seed_iep(conn, cid, "student-1", iep_status="draft")
        result = call_action(activate_iep, conn, ns(
            iep_id=new_id, user_id="admin",
        ))
        assert result["status"] == "ok"
        # Old IEP should be expired
        old = conn.execute("SELECT iep_status FROM sped_iep WHERE id = ?", (old_id,)).fetchone()
        assert old["iep_status"] == "expired"

    def test_cannot_activate_active(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, "student-1", iep_status="active")
        result = call_action(activate_iep, conn, ns(
            iep_id=iep_id, user_id="admin",
        ))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# IEP GOAL DOMAIN
# ══════════════════════════════════════════════════════════════════════════════


class TestAddIepGoal:
    def test_happy_path(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        result = call_action(add_iep_goal, conn, ns(
            iep_id=iep_id,
            goal_area="reading",
            goal_description="Increase reading fluency to grade level",
            baseline="60 wpm",
            target="100 wpm",
            current_progress="",
            measurement_method="probe",
            sort_order=1,
            user_id="admin",
        ))
        assert result["status"] == "ok"
        assert result["goal_status"] == "in_progress"

    def test_missing_description(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        result = call_action(add_iep_goal, conn, ns(
            iep_id=iep_id,
            goal_area="math",
            goal_description=None,
            baseline=None, target=None, current_progress=None,
            measurement_method=None, sort_order=0, user_id=None,
        ))
        assert result["status"] == "error"

    def test_invalid_iep(self, setup):
        conn, cid = setup
        result = call_action(add_iep_goal, conn, ns(
            iep_id="nonexistent",
            goal_description="Some goal",
            goal_area=None, baseline=None, target=None,
            current_progress=None, measurement_method=None,
            sort_order=0, user_id=None,
        ))
        assert result["status"] == "error"


class TestListIepGoals:
    def test_list_goals(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        seed_iep_goal(conn, iep_id)
        seed_iep_goal(conn, iep_id)
        result = call_action(list_iep_goals, conn, ns(iep_id=iep_id))
        assert result["status"] == "ok"
        assert result["count"] == 2


class TestUpdateIepGoal:
    def test_update_progress(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        goal_id = seed_iep_goal(conn, iep_id)
        result = call_action(update_iep_goal, conn, ns(
            goal_id=goal_id,
            current_progress="85 wpm",
            goal_status=None, goal_area=None, goal_description=None,
            baseline=None, target=None, measurement_method=None,
            sort_order=None, user_id="admin",
        ))
        assert result["status"] == "ok"
        row = conn.execute("SELECT current_progress FROM sped_iep_goal WHERE id = ?", (goal_id,)).fetchone()
        assert row["current_progress"] == "85 wpm"

    def test_mark_goal_met(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        goal_id = seed_iep_goal(conn, iep_id)
        result = call_action(update_iep_goal, conn, ns(
            goal_id=goal_id,
            goal_status="met",
            current_progress=None, goal_area=None, goal_description=None,
            baseline=None, target=None, measurement_method=None,
            sort_order=None, user_id="admin",
        ))
        assert result["status"] == "ok"
        row = conn.execute("SELECT goal_status FROM sped_iep_goal WHERE id = ?", (goal_id,)).fetchone()
        assert row["goal_status"] == "met"


# ══════════════════════════════════════════════════════════════════════════════
# SERVICES DOMAIN
# ══════════════════════════════════════════════════════════════════════════════


class TestAddService:
    def test_happy_path(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        result = call_action(add_service, conn, ns(
            student_id="student-1",
            iep_id=iep_id,
            service_type="speech_therapy",
            provider="Dr. Speech",
            frequency_minutes_per_week=60,
            setting="pull_out",
            start_date="2025-11-01",
            end_date="2026-10-31",
            notes="",
            company_id=cid,
            user_id="admin",
        ))
        assert result["status"] == "ok"
        assert result["service_type"] == "speech_therapy"
        assert result["service_status"] == "active"

    def test_missing_student_id(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        result = call_action(add_service, conn, ns(
            student_id=None, iep_id=iep_id, service_type="speech_therapy",
            provider=None, frequency_minutes_per_week=0, setting=None,
            start_date=None, end_date=None, notes=None,
            company_id=cid, user_id=None,
        ))
        assert result["status"] == "error"

    def test_invalid_service_type(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        result = call_action(add_service, conn, ns(
            student_id="student-1",
            iep_id=iep_id,
            service_type="invalid_type",
            provider=None, frequency_minutes_per_week=0, setting=None,
            start_date=None, end_date=None, notes=None,
            company_id=cid, user_id=None,
        ))
        assert result["status"] == "error"
        assert "invalid" in result["message"].lower()

    def test_invalid_iep(self, setup):
        conn, cid = setup
        result = call_action(add_service, conn, ns(
            student_id="student-1",
            iep_id="nonexistent",
            service_type="speech_therapy",
            provider=None, frequency_minutes_per_week=0, setting=None,
            start_date=None, end_date=None, notes=None,
            company_id=cid, user_id=None,
        ))
        assert result["status"] == "error"


class TestListServices:
    def test_list_all(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        seed_service(conn, cid, iep_id)
        seed_service(conn, cid, iep_id, service_type="occupational_therapy")
        result = call_action(list_services, conn, ns(
            student_id=None, iep_id=None, service_type=None,
            service_status=None, company_id=cid, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_filter_by_type(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        seed_service(conn, cid, iep_id, service_type="speech_therapy")
        seed_service(conn, cid, iep_id, service_type="occupational_therapy")
        result = call_action(list_services, conn, ns(
            student_id=None, iep_id=None,
            service_type="speech_therapy",
            service_status=None, company_id=None, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1


class TestGetService:
    def test_with_logs(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        seed_service_log(conn, svc_id, duration_minutes=30)
        seed_service_log(conn, svc_id, session_date="2025-11-12", duration_minutes=25)
        result = call_action(get_service, conn, ns(service_id=svc_id))
        assert result["status"] == "ok"
        assert len(result["logs"]) == 2
        assert result["total_minutes_delivered"] == 55

    def test_not_found(self, setup):
        conn, cid = setup
        result = call_action(get_service, conn, ns(service_id="nonexistent"))
        assert result["status"] == "error"

    def test_absent_sessions_excluded_from_total(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        seed_service_log(conn, svc_id, duration_minutes=30)
        seed_service_log(conn, svc_id, session_date="2025-11-12",
                         duration_minutes=0, was_absent=1)
        result = call_action(get_service, conn, ns(service_id=svc_id))
        assert result["status"] == "ok"
        assert result["total_minutes_delivered"] == 30


class TestUpdateService:
    def test_update_provider(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        result = call_action(update_service, conn, ns(
            service_id=svc_id,
            provider="Dr. New Provider",
            frequency_minutes_per_week=None, setting=None,
            start_date=None, end_date=None, notes=None,
            service_status=None, user_id="admin",
        ))
        assert result["status"] == "ok"
        row = conn.execute("SELECT provider FROM sped_service WHERE id = ?", (svc_id,)).fetchone()
        assert row["provider"] == "Dr. New Provider"

    def test_no_fields_to_update(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        result = call_action(update_service, conn, ns(
            service_id=svc_id,
            provider=None, frequency_minutes_per_week=None, setting=None,
            start_date=None, end_date=None, notes=None,
            service_status=None, user_id=None,
        ))
        assert result["status"] == "error"


class TestAddServiceLog:
    def test_happy_path(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        result = call_action(add_service_log, conn, ns(
            service_id=svc_id,
            session_date="2025-11-05",
            duration_minutes=30,
            provider="Dr. Speech",
            session_notes="Good progress today",
            is_makeup_session=0,
            was_absent=0,
            absence_reason=None,
            user_id="admin",
        ))
        assert result["status"] == "ok"
        assert result["duration_minutes"] == 30

    def test_invalid_service(self, setup):
        conn, cid = setup
        result = call_action(add_service_log, conn, ns(
            service_id="nonexistent",
            session_date="2025-11-05",
            duration_minutes=30,
            provider=None, session_notes=None,
            is_makeup_session=0, was_absent=0,
            absence_reason=None, user_id=None,
        ))
        assert result["status"] == "error"

    def test_defaults_provider_from_service(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        result = call_action(add_service_log, conn, ns(
            service_id=svc_id,
            session_date="2025-11-05",
            duration_minutes=30,
            provider=None,
            session_notes=None,
            is_makeup_session=0,
            was_absent=0,
            absence_reason=None,
            user_id=None,
        ))
        assert result["status"] == "ok"
        # Verify provider was copied from service
        log = conn.execute(
            "SELECT provider FROM sped_service_log WHERE id = ?", (result["id"],)
        ).fetchone()
        assert log["provider"] == "Dr. Speech"


class TestListServiceLogs:
    def test_list_logs(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        seed_service_log(conn, svc_id, session_date="2025-11-05")
        seed_service_log(conn, svc_id, session_date="2025-11-12")
        result = call_action(list_service_logs, conn, ns(
            service_id=svc_id,
            date_from=None, date_to=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_date_filter(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        seed_service_log(conn, svc_id, session_date="2025-11-05")
        seed_service_log(conn, svc_id, session_date="2025-12-05")
        result = call_action(list_service_logs, conn, ns(
            service_id=svc_id,
            date_from="2025-12-01", date_to="2025-12-31",
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1


class TestServiceHoursReport:
    def test_by_student(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        seed_service_log(conn, svc_id, duration_minutes=30)
        seed_service_log(conn, svc_id, session_date="2025-11-12", duration_minutes=25)
        result = call_action(service_hours_report, conn, ns(
            student_id="student-1",
            service_id=None,
            date_from=None, date_to=None,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1
        assert result["items"][0]["total_minutes_delivered"] == 55

    def test_missing_both_ids(self, setup):
        conn, cid = setup
        result = call_action(service_hours_report, conn, ns(
            student_id=None, service_id=None,
            date_from=None, date_to=None,
        ))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE DOMAIN
# ══════════════════════════════════════════════════════════════════════════════


class TestComplianceCheck:
    def test_finds_overdue_reviews(self, setup):
        conn, cid = setup
        seed_iep(conn, cid, "student-1", iep_status="active",
                 annual_review_date="2025-01-01")
        result = call_action(compliance_check, conn, ns(
            company_id=cid, days_ahead=30,
        ))
        assert result["status"] == "ok"
        overdue = [f for f in result["findings"] if f["finding_type"] == "overdue_annual_review"]
        assert len(overdue) >= 1

    def test_finds_stale_services(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid, iep_status="active")
        seed_service(conn, cid, iep_id)
        # No service logs at all -> should flag as stale
        result = call_action(compliance_check, conn, ns(
            company_id=cid, days_ahead=30,
        ))
        assert result["status"] == "ok"
        stale = [f for f in result["findings"] if f["finding_type"] == "stale_service"]
        assert len(stale) >= 1

    def test_no_findings_when_compliant(self, setup):
        conn, cid = setup
        # No IEPs, no services -> nothing to flag
        result = call_action(compliance_check, conn, ns(
            company_id=cid, days_ahead=30,
        ))
        assert result["status"] == "ok"
        assert result["total_findings"] == 0


class TestOverdueIepReport:
    def test_lists_overdue(self, setup):
        conn, cid = setup
        seed_iep(conn, cid, "student-1", iep_status="active",
                 annual_review_date="2024-06-01")
        seed_iep(conn, cid, "student-2", iep_status="active",
                 annual_review_date="2099-01-01")
        result = call_action(overdue_iep_report, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["items"][0]["days_overdue"] > 0


class TestServiceUtilizationReport:
    def test_report(self, setup):
        conn, cid = setup
        iep_id = seed_iep(conn, cid)
        svc_id = seed_service(conn, cid, iep_id)
        seed_service_log(conn, svc_id, duration_minutes=30)
        result = call_action(service_utilization_report, conn, ns(
            company_id=cid, date_from=None, date_to=None,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestCaseloadReport:
    def test_report(self, setup):
        conn, cid = setup
        seed_iep(conn, cid, "student-1", iep_status="active")
        seed_iep(conn, cid, "student-2", iep_status="active")
        result = call_action(caseload_report, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 1
        # Both IEPs have case_manager = "Ms. Johnson"
        assert result["items"][0]["active_iep_count"] == 2
