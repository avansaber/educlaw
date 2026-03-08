"""Unit tests for EduClaw K-12 — discipline domain.

Tests all 15 actions:
  add-discipline-incident, update-discipline-incident, add-discipline-student,
  add-discipline-action, close-discipline-incident, get-discipline-incident,
  list-discipline-incidents, get-discipline-history, get-cumulative-suspension-days,
  add-manifestation-review, update-manifestation-review, add-pbis-recognition,
  notify-guardians-discipline, generate-discipline-report, generate-discipline-state-report
"""
import pytest
from helpers import (
    call_action, ns, get_conn,
    seed_company, seed_academic_year, seed_academic_term,
    seed_student, seed_guardian, seed_student_guardian,
    seed_discipline_incident, seed_discipline_student,
    seed_iep_active, seed_sped_eligibility, seed_sped_referral,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from discipline import (
    add_discipline_incident,
    update_discipline_incident,
    add_discipline_student,
    add_discipline_action,
    close_discipline_incident,
    get_discipline_incident,
    list_discipline_incidents,
    get_discipline_history,
    get_cumulative_suspension_days,
    add_manifestation_review,
    update_manifestation_review,
    add_pbis_recognition,
    notify_guardians_discipline,
    generate_discipline_report,
    generate_discipline_state_report,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db_path):
    """Seed common prerequisite data for discipline tests."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    sid = seed_student(conn, cid)
    gid = seed_guardian(conn, cid)
    seed_student_guardian(conn, sid, gid)
    yield conn, cid, yid, tid, sid
    conn.close()


# ── add-discipline-incident ───────────────────────────────────────────────────

class TestAddDisciplineIncident:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01",
            location="classroom",
            incident_type="fighting",
            severity="major",
            academic_year_id=yid,
            academic_term_id=tid,
            description="Test fight incident",
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "id" in result
        assert result["incident_status"] == "open"
        assert "naming_series" in result

    def test_missing_incident_date(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            location="classroom",
            incident_type="fighting",
            severity="major",
            academic_year_id=yid,
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "incident-date" in result["message"]

    def test_missing_location(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01",
            incident_type="fighting",
            severity="major",
            academic_year_id=yid,
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "location" in result["message"]

    def test_missing_incident_type(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01",
            location="classroom",
            severity="major",
            academic_year_id=yid,
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "incident-type" in result["message"]

    def test_missing_severity(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01",
            location="classroom",
            incident_type="fighting",
            academic_year_id=yid,
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "severity" in result["message"]

    def test_missing_academic_year(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01",
            location="classroom",
            incident_type="fighting",
            severity="major",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "academic-year-id" in result["message"]

    def test_invalid_academic_year(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01",
            location="classroom",
            incident_type="fighting",
            severity="major",
            academic_year_id="nonexistent-uuid",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_naming_series_increments(self, setup):
        conn, cid, yid, tid, sid = setup
        r1 = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-01", location="classroom",
            incident_type="fighting", severity="major",
            academic_year_id=yid, company_id=cid,
        ))
        r2 = call_action(add_discipline_incident, conn, ns(
            incident_date="2025-10-02", location="hallway",
            incident_type="disrespectful_language", severity="minor",
            academic_year_id=yid, company_id=cid,
        ))
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"
        assert r1["naming_series"] != r2["naming_series"]


# ── update-discipline-incident ────────────────────────────────────────────────

class TestUpdateDisciplineIncident:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(update_discipline_incident, conn, ns(
            incident_id=iid,
            location="gym",
            severity="minor",
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT location, severity FROM educlaw_k12_discipline_incident WHERE id = ?",
            (iid,)
        ).fetchone()
        assert row["location"] == "gym"
        assert row["severity"] == "minor"

    def test_missing_incident_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_discipline_incident, conn, ns(
            location="gymnasium",
        ))
        assert result["status"] == "error"
        assert "incident-id" in result["message"]

    def test_closed_incident_cannot_be_updated(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        conn.execute(
            "UPDATE educlaw_k12_discipline_incident SET incident_status = 'closed' WHERE id = ?",
            (iid,)
        )
        conn.commit()
        result = call_action(update_discipline_incident, conn, ns(
            incident_id=iid,
            location="gymnasium",
        ))
        assert result["status"] == "error"
        assert "closed" in result["message"]

    def test_no_fields_to_update(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(update_discipline_incident, conn, ns(
            incident_id=iid,
        ))
        assert result["status"] == "error"
        assert "No fields" in result["message"]


# ── add-discipline-student ────────────────────────────────────────────────────

class TestAddDisciplineStudent:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(add_discipline_student, conn, ns(
            incident_id=iid,
            student_id=sid,
            role="offender",
        ))
        assert result["status"] == "ok"
        assert "id" in result

    def test_missing_incident_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_student, conn, ns(
            student_id=sid,
            role="offender",
        ))
        assert result["status"] == "error"
        assert "incident-id" in result["message"]

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(add_discipline_student, conn, ns(
            incident_id=iid,
            role="offender",
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_missing_role(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(add_discipline_student, conn, ns(
            incident_id=iid,
            student_id=sid,
        ))
        assert result["status"] == "error"
        assert "role" in result["message"]

    def test_invalid_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(add_discipline_student, conn, ns(
            incident_id=iid,
            student_id="nonexistent-uuid",
            role="offender",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_duplicate_student_rejected(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        call_action(add_discipline_student, conn, ns(
            incident_id=iid, student_id=sid, role="offender",
        ))
        result = call_action(add_discipline_student, conn, ns(
            incident_id=iid, student_id=sid, role="victim",
        ))
        assert result["status"] == "error"
        assert "already added" in result["message"]


# ── add-discipline-action ─────────────────────────────────────────────────────

class TestAddDisciplineAction:
    def test_happy_path_non_suspension(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid)
        result = call_action(add_discipline_action, conn, ns(
            discipline_student_id=dsid,
            action_type="detention",
            start_date="2025-10-05",
            duration_days="1",
        ))
        assert result["status"] == "ok"
        assert result["action_type"] == "detention"
        assert "cumulative_suspension_days_ytd" not in result

    def test_suspension_triggers_cumulative_calc(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid, is_idea_eligible=1)
        result = call_action(add_discipline_action, conn, ns(
            discipline_student_id=dsid,
            action_type="out_of_school_suspension",
            duration_days="3",
        ))
        assert result["status"] == "ok"
        assert "cumulative_suspension_days_ytd" in result
        assert float(result["cumulative_suspension_days_ytd"]) == 3.0

    def test_mdr_alert_at_10_days(self, setup):
        """IDEA-eligible student with 10+ suspension days should trigger MDR alert."""
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid, is_idea_eligible=1)
        # Add a real 9-day suspension action first so recalc picks it up
        call_action(add_discipline_action, conn, ns(
            discipline_student_id=dsid,
            action_type="out_of_school_suspension",
            duration_days="9",
        ))
        # Now add 2 more days — cumulative = 11 → MDR required
        result = call_action(add_discipline_action, conn, ns(
            discipline_student_id=dsid,
            action_type="out_of_school_suspension",
            duration_days="2",
        ))
        assert result["status"] == "ok"
        assert "mdr_alert" in result

    def test_missing_discipline_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_discipline_action, conn, ns(
            action_type="detention",
        ))
        assert result["status"] == "error"
        assert "discipline-student-id" in result["message"]

    def test_missing_action_type(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid)
        result = call_action(add_discipline_action, conn, ns(
            discipline_student_id=dsid,
        ))
        assert result["status"] == "error"
        assert "action-type" in result["message"]


# ── close-discipline-incident ─────────────────────────────────────────────────

class TestCloseDisciplineIncident:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(close_discipline_incident, conn, ns(
            incident_id=iid,
            reviewed_by="Principal Smith",
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT incident_status FROM educlaw_k12_discipline_incident WHERE id = ?",
            (iid,)
        ).fetchone()
        assert row["incident_status"] == "closed"

    def test_already_closed(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        call_action(close_discipline_incident, conn, ns(incident_id=iid))
        result = call_action(close_discipline_incident, conn, ns(incident_id=iid))
        assert result["status"] == "error"
        assert "already closed" in result["message"]

    def test_missing_incident_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(close_discipline_incident, conn, ns())
        assert result["status"] == "error"
        assert "incident-id" in result["message"]

    def test_incident_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(close_discipline_incident, conn, ns(
            incident_id="nonexistent-uuid"
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ── get-discipline-incident ───────────────────────────────────────────────────

class TestGetDisciplineIncident:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid)
        result = call_action(get_discipline_incident, conn, ns(
            incident_id=iid,
            user_id="nurse1",
        ))
        assert result["status"] == "ok"
        assert result["id"] == iid
        assert "students" in result
        # Actions are nested inside each student dict, not at the top level
        assert isinstance(result["students"], list)

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_discipline_incident, conn, ns(
            incident_id="nonexistent-uuid",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_missing_incident_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_discipline_incident, conn, ns())
        assert result["status"] == "error"
        assert "incident-id" in result["message"]


# ── list-discipline-incidents ─────────────────────────────────────────────────

class TestListDisciplineIncidents:
    def test_happy_path_empty(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_discipline_incidents, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "incidents" in result
        assert result["count"] == 0

    def test_with_incidents(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_discipline_incident(conn, cid, yid, "DI-2025-00001")
        seed_discipline_incident(conn, cid, yid, "DI-2025-00002")
        result = call_action(list_discipline_incidents, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_filter_by_severity(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_discipline_incident(conn, cid, yid, "DI-2025-00001")
        result = call_action(list_discipline_incidents, conn, ns(
            company_id=cid,
            severity="major",
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1


# ── get-discipline-history ────────────────────────────────────────────────────

class TestGetDisciplineHistory:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        seed_discipline_student(conn, iid, sid)
        result = call_action(get_discipline_history, conn, ns(
            student_id=sid,
            user_id="counselor1",
        ))
        assert result["status"] == "ok"
        assert "history" in result  # response key is "history", not "incidents"
        assert result["student_id"] == sid

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_discipline_history, conn, ns())
        assert result["status"] == "error"
        assert "student-id" in result["message"]


# ── get-cumulative-suspension-days ────────────────────────────────────────────

class TestGetCumulativeSuspensionDays:
    def test_happy_path_no_suspensions(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_cumulative_suspension_days, conn, ns(
            student_id=sid,
            academic_year_id=yid,
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "total_suspension_days" in result  # response key is "total_suspension_days"

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_cumulative_suspension_days, conn, ns(
            academic_year_id=yid,
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_missing_academic_year_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_cumulative_suspension_days, conn, ns(
            student_id=sid,
        ))
        assert result["status"] == "error"
        assert "academic-year-id" in result["message"]


# ── add-manifestation-review ──────────────────────────────────────────────────

class TestAddManifestationReview:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid, is_idea_eligible=1)
        ref_id = seed_sped_referral(conn, sid, cid)
        elig_id = seed_sped_eligibility(conn, sid, ref_id, cid)
        iep_id = seed_iep_active(conn, sid, elig_id, cid)
        result = call_action(add_manifestation_review, conn, ns(
            discipline_student_id=dsid,
            student_id=sid,
            iep_id=iep_id,
            mdr_date="2025-10-15",
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "id" in result
        assert result["determination"] == "pending"

    def test_missing_discipline_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_manifestation_review, conn, ns(
            student_id=sid,
            iep_id="some-id",
        ))
        assert result["status"] == "error"
        assert "discipline-student-id" in result["message"]

    def test_missing_iep_id(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid)
        result = call_action(add_manifestation_review, conn, ns(
            discipline_student_id=dsid,
            student_id=sid,
        ))
        assert result["status"] == "error"
        assert "iep-id" in result["message"]


# ── update-manifestation-review ───────────────────────────────────────────────

class TestUpdateManifestationReview:
    def _make_mdr(self, conn, cid, yid, sid):
        """Helper to create a full MDR chain."""
        iid = seed_discipline_incident(conn, cid, yid)
        dsid = seed_discipline_student(conn, iid, sid, is_idea_eligible=1)
        ref_id = seed_sped_referral(conn, sid, cid)
        elig_id = seed_sped_eligibility(conn, sid, ref_id, cid)
        iep_id = seed_iep_active(conn, sid, elig_id, cid)
        result = call_action(add_manifestation_review, conn, ns(
            discipline_student_id=dsid,
            student_id=sid,
            iep_id=iep_id,
            company_id=cid,
        ))
        return result["id"]

    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        mdr_id = self._make_mdr(conn, cid, yid, sid)
        result = call_action(update_manifestation_review, conn, ns(
            mdr_id=mdr_id,
            question_1_result="yes",
            question_2_result="no",
            determination="manifestation",
            outcome_action="return_to_placement",
            fba_required=True,
            bip_required=True,
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT determination, fba_required FROM educlaw_k12_manifestation_review WHERE id = ?",
            (mdr_id,)
        ).fetchone()
        assert row["determination"] == "manifestation"
        assert row["fba_required"] == 1

    def test_missing_mdr_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_manifestation_review, conn, ns(
            determination="manifestation",
        ))
        assert result["status"] == "error"
        assert "mdr-id" in result["message"]

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_manifestation_review, conn, ns(
            mdr_id="nonexistent-uuid",
            determination="manifestation",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ── add-pbis-recognition ──────────────────────────────────────────────────────

class TestAddPbisRecognition:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_pbis_recognition, conn, ns(
            student_id=sid,
            academic_year_id=yid,
            incident_date="2025-10-01",
            description="Helped classmate with homework",
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "id" in result
        assert "discipline_student_id" in result
        # Verify it's stored with PBIS prefix
        row = conn.execute(
            "SELECT description, incident_type, severity, incident_status FROM educlaw_k12_discipline_incident WHERE id = ?",
            (result["id"],)
        ).fetchone()
        assert "[PBIS]" in row["description"]
        assert row["incident_type"] == "other_minor"
        assert row["severity"] == "minor"
        assert row["incident_status"] == "closed"

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_pbis_recognition, conn, ns(
            academic_year_id=yid,
            incident_date="2025-10-01",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_missing_incident_date(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_pbis_recognition, conn, ns(
            student_id=sid,
            academic_year_id=yid,
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "incident-date" in result["message"]


# ── notify-guardians-discipline ───────────────────────────────────────────────

class TestNotifyGuardiansDiscipline:
    def test_happy_path_with_guardian(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        seed_discipline_student(conn, iid, sid, role="offender")
        result = call_action(notify_guardians_discipline, conn, ns(
            incident_id=iid,
            user_id="admin1",
        ))
        assert result["status"] == "ok"
        assert result["notifications_created"] == 1

    def test_no_students_in_incident(self, setup):
        conn, cid, yid, tid, sid = setup
        iid = seed_discipline_incident(conn, cid, yid)
        result = call_action(notify_guardians_discipline, conn, ns(
            incident_id=iid,
        ))
        assert result["status"] == "ok"
        assert result["notifications_created"] == 0

    def test_missing_incident_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(notify_guardians_discipline, conn, ns())
        assert result["status"] == "error"
        assert "incident-id" in result["message"]

    def test_incident_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(notify_guardians_discipline, conn, ns(
            incident_id="nonexistent-uuid"
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ── generate-discipline-report ────────────────────────────────────────────────

class TestGenerateDisciplineReport:
    def test_happy_path_no_data(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(generate_discipline_report, conn, ns(
            company_id=cid,
            academic_year_id=yid,
        ))
        assert result["status"] == "ok"
        assert "summary" in result
        assert "by_type" in result
        assert "by_severity" in result

    def test_with_incidents(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_discipline_incident(conn, cid, yid)
        result = call_action(generate_discipline_report, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["summary"]["total_incidents"] >= 1


# ── generate-discipline-state-report ─────────────────────────────────────────

class TestGenerateDisciplineStateReport:
    def test_happy_path_no_data(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(generate_discipline_state_report, conn, ns(
            company_id=cid,
            academic_year_id=yid,
        ))
        assert result["status"] == "ok"
        assert "report_type" in result

    def test_missing_academic_year(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(generate_discipline_state_report, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "academic-year-id" in result["message"]
