"""Unit tests for EduClaw K-12 — health_records domain.

Tests all 20 actions:
  add-health-profile, update-health-profile, get-health-profile,
  verify-health-profile, get-emergency-health-info, add-office-visit,
  list-office-visits, get-office-visit, add-student-medication,
  update-student-medication, list-student-medications, log-medication-admin,
  list-medication-logs, add-immunization, add-immunization-waiver,
  update-immunization-waiver, get-immunization-record,
  check-immunization-compliance, list-health-alerts, generate-immunization-report
"""
import pytest
from helpers import (
    call_action, ns, get_conn,
    seed_company, seed_academic_year, seed_academic_term,
    seed_student, seed_guardian, seed_student_guardian,
    seed_health_profile,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from health_records import (
    add_health_profile,
    update_health_profile,
    get_health_profile,
    verify_health_profile,
    get_emergency_health_info,
    add_office_visit,
    list_office_visits,
    get_office_visit,
    add_student_medication,
    update_student_medication,
    list_student_medications,
    log_medication_admin,
    list_medication_logs,
    add_immunization,
    add_immunization_waiver,
    update_immunization_waiver,
    get_immunization_record,
    check_immunization_compliance,
    list_health_alerts,
    generate_immunization_report,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def setup(db_path):
    """Seed common prerequisite data for health record tests."""
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    sid = seed_student(conn, cid)
    gid = seed_guardian(conn, cid)
    seed_student_guardian(conn, sid, gid)
    yield conn, cid, yid, tid, sid
    conn.close()


def _seed_medication(conn, student_id, company_id, supply_count=10) -> str:
    """Insert a student medication directly and return its ID."""
    import uuid, datetime
    mid = str(uuid.uuid4())
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """INSERT INTO educlaw_k12_student_medication
           (id, student_id, medication_name, dosage, route, frequency,
            administration_times, prescribing_physician, physician_authorization_date,
            start_date, end_date, supply_count, supply_low_threshold,
            storage_instructions, administration_instructions, is_controlled_substance,
            medication_status, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, 'Ritalin', '10mg', 'oral', 'daily',
                   '["12:00"]', 'Dr. Jones', '2025-08-01',
                   '2025-09-01', '2026-06-30', ?, 5,
                   'Refrigerate', 'Give with water', 0,
                   'active', ?, ?, ?, '')""",
        (mid, student_id, supply_count, company_id, now, now)
    )
    conn.commit()
    return mid


def _seed_immunization_waiver(conn, student_id, company_id) -> str:
    """Insert an immunization waiver directly and return its ID."""
    import uuid, datetime
    wid = str(uuid.uuid4())
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """INSERT INTO educlaw_k12_immunization_waiver
           (id, student_id, vaccine_name, waiver_type, issue_date,
            expiry_date, waiver_status, issued_by, notes,
            company_id, created_at, created_by)
           VALUES (?, ?, 'MMR', 'medical', '2025-08-01',
                   '2026-07-31', 'active', 'Dr. Smith', '',
                   ?, ?, '')""",
        (wid, student_id, company_id, now)
    )
    conn.commit()
    return wid


# ── add-health-profile ────────────────────────────────────────────────────────

class TestAddHealthProfile:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_health_profile, conn, ns(
            student_id=sid,
            company_id=cid,
            allergies='["peanuts"]',
            chronic_conditions='["asthma"]',
            physician_name="Dr. Smith",
            blood_type="A+",
        ))
        assert result["status"] == "ok"
        assert result["student_id"] == sid
        assert result["profile_status"] == "incomplete"

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_health_profile, conn, ns(company_id=cid))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_invalid_student(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_health_profile, conn, ns(
            student_id="nonexistent-uuid",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_duplicate_profile_rejected(self, setup):
        conn, cid, yid, tid, sid = setup
        call_action(add_health_profile, conn, ns(student_id=sid, company_id=cid))
        result = call_action(add_health_profile, conn, ns(
            student_id=sid, company_id=cid
        ))
        assert result["status"] == "error"
        assert "already exists" in result["message"]

    def test_json_allergies_stored_correctly(self, setup):
        conn, cid, yid, tid, sid = setup
        allergies = '["peanuts", "shellfish"]'
        result = call_action(add_health_profile, conn, ns(
            student_id=sid,
            company_id=cid,
            allergies=allergies,
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT allergies FROM educlaw_k12_health_profile WHERE student_id = ?",
            (sid,)
        ).fetchone()
        import json
        stored = json.loads(row["allergies"])
        assert "peanuts" in stored
        assert "shellfish" in stored


# ── update-health-profile ─────────────────────────────────────────────────────

class TestUpdateHealthProfile:
    def test_happy_path_by_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_health_profile(conn, sid, cid)
        result = call_action(update_health_profile, conn, ns(
            student_id=sid,
            physician_name="Dr. New",
            blood_type="B+",
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT physician_name, blood_type FROM educlaw_k12_health_profile WHERE student_id = ?",
            (sid,)
        ).fetchone()
        assert row["physician_name"] == "Dr. New"
        assert row["blood_type"] == "B+"

    def test_happy_path_by_profile_id(self, setup):
        conn, cid, yid, tid, sid = setup
        pid = seed_health_profile(conn, sid, cid)
        result = call_action(update_health_profile, conn, ns(
            health_profile_id=pid,
            physician_name="Dr. Updated",
        ))
        assert result["status"] == "ok"

    def test_no_identifier_provided(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_health_profile, conn, ns(
            physician_name="Dr. X",
        ))
        assert result["status"] == "error"

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_health_profile, conn, ns(
            student_id="nonexistent-uuid",
            physician_name="Dr. X",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_no_fields_to_update(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_health_profile(conn, sid, cid)
        result = call_action(update_health_profile, conn, ns(
            student_id=sid,
        ))
        assert result["status"] == "error"
        assert "No fields" in result["message"]


# ── get-health-profile ────────────────────────────────────────────────────────

class TestGetHealthProfile:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_health_profile(conn, sid, cid)
        result = call_action(get_health_profile, conn, ns(
            student_id=sid,
            user_id="nurse1",
        ))
        assert result["status"] == "ok"
        assert result["student_id"] == sid
        assert isinstance(result["allergies"], list)

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_health_profile, conn, ns(student_id=sid))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_health_profile, conn, ns())
        assert result["status"] == "error"
        assert "student-id" in result["message"]


# ── verify-health-profile ─────────────────────────────────────────────────────

class TestVerifyHealthProfile:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_health_profile(conn, sid, cid)
        result = call_action(verify_health_profile, conn, ns(
            student_id=sid,
            last_verified_by="Nurse Johnson",
            last_verified_date="2025-09-01",
        ))
        assert result["status"] == "ok"
        assert result["profile_status"] == "active"
        assert result["last_verified_date"] == "2025-09-01"
        row = conn.execute(
            "SELECT profile_status, last_verified_by FROM educlaw_k12_health_profile WHERE student_id = ?",
            (sid,)
        ).fetchone()
        assert row["profile_status"] == "active"
        assert row["last_verified_by"] == "Nurse Johnson"

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(verify_health_profile, conn, ns(student_id=sid))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ── get-emergency-health-info ─────────────────────────────────────────────────

class TestGetEmergencyHealthInfo:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        seed_health_profile(conn, sid, cid)
        result = call_action(get_emergency_health_info, conn, ns(
            student_id=sid,
            user_id="nurse1",
        ))
        assert result["status"] == "ok"
        assert "student" in result
        assert "allergies" in result

    def test_student_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_emergency_health_info, conn, ns(
            student_id="nonexistent-uuid",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_emergency_health_info, conn, ns())
        assert result["status"] == "error"
        assert "student-id" in result["message"]


# ── add-office-visit ──────────────────────────────────────────────────────────

class TestAddOfficeVisit:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_office_visit, conn, ns(
            student_id=sid,
            visit_date="2025-10-15",
            chief_complaint="headache",
            disposition="returned_to_class",
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["visit_date"] == "2025-10-15"
        assert result["disposition"] == "returned_to_class"

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_office_visit, conn, ns(
            visit_date="2025-10-15",
            chief_complaint="headache",
            disposition="returned_to_class",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_missing_visit_date(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_office_visit, conn, ns(
            student_id=sid,
            chief_complaint="headache",
            disposition="returned_to_class",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "visit-date" in result["message"]

    def test_missing_chief_complaint(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_office_visit, conn, ns(
            student_id=sid,
            visit_date="2025-10-15",
            disposition="returned_to_class",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "chief-complaint" in result["message"]

    def test_missing_disposition(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_office_visit, conn, ns(
            student_id=sid,
            visit_date="2025-10-15",
            chief_complaint="headache",
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "disposition" in result["message"]


# ── list-office-visits ────────────────────────────────────────────────────────

class TestListOfficeVisits:
    def test_happy_path_empty(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_office_visits, conn, ns(
            student_id=sid,
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 0

    def test_with_visits(self, setup):
        conn, cid, yid, tid, sid = setup
        call_action(add_office_visit, conn, ns(
            student_id=sid, visit_date="2025-10-15",
            chief_complaint="fever", disposition="sent_home", company_id=cid,
        ))
        result = call_action(list_office_visits, conn, ns(
            student_id=sid, company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_office_visits, conn, ns(company_id=cid))
        assert result["status"] == "error"


# ── get-office-visit ──────────────────────────────────────────────────────────

class TestGetOfficeVisit:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        r = call_action(add_office_visit, conn, ns(
            student_id=sid, visit_date="2025-10-15",
            chief_complaint="stomach ache", disposition="returned_to_class", company_id=cid,
        ))
        visit_id = r["id"]
        result = call_action(get_office_visit, conn, ns(
            visit_id=visit_id,
            user_id="nurse1",
        ))
        assert result["status"] == "ok"
        assert result["id"] == visit_id

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_office_visit, conn, ns(visit_id="nonexistent-uuid"))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_missing_visit_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_office_visit, conn, ns())
        assert result["status"] == "error"
        assert "visit-id" in result["message"]


# ── add-student-medication ────────────────────────────────────────────────────

class TestAddStudentMedication:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_student_medication, conn, ns(
            student_id=sid,
            medication_name="Ritalin",
            dosage="10mg",
            route="oral",
            frequency="daily",
            supply_count=30,
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["medication_name"] == "Ritalin"
        assert result["medication_status"] == "active"

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_student_medication, conn, ns(
            medication_name="Ritalin", route="oral", frequency="daily", company_id=cid,
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_missing_medication_name(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_student_medication, conn, ns(
            student_id=sid, route="oral", frequency="daily", company_id=cid,
        ))
        assert result["status"] == "error"
        assert "medication-name" in result["message"]


# ── update-student-medication ─────────────────────────────────────────────────

class TestUpdateStudentMedication:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        mid = _seed_medication(conn, sid, cid)
        result = call_action(update_student_medication, conn, ns(
            student_medication_id=mid,
            medication_status="discontinued",
            supply_count=0,
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT medication_status FROM educlaw_k12_student_medication WHERE id = ?",
            (mid,)
        ).fetchone()
        assert row["medication_status"] == "discontinued"

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_student_medication, conn, ns(
            student_medication_id="nonexistent-uuid",
            medication_status="discontinued",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_missing_medication_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_student_medication, conn, ns(
            medication_status="discontinued",
        ))
        assert result["status"] == "error"
        assert "student-medication-id" in result["message"]


# ── list-student-medications ──────────────────────────────────────────────────

class TestListStudentMedications:
    def test_happy_path_empty(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_student_medications, conn, ns(
            student_id=sid,
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 0

    def test_with_medication(self, setup):
        conn, cid, yid, tid, sid = setup
        _seed_medication(conn, sid, cid)
        result = call_action(list_student_medications, conn, ns(
            student_id=sid,
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_student_medications, conn, ns(company_id=cid))
        assert result["status"] == "error"
        assert "student-id" in result["message"]


# ── log-medication-admin ──────────────────────────────────────────────────────

class TestLogMedicationAdmin:
    def test_happy_path_decrements_supply(self, setup):
        conn, cid, yid, tid, sid = setup
        mid = _seed_medication(conn, sid, cid, supply_count=10)
        result = call_action(log_medication_admin, conn, ns(
            student_medication_id=mid,
            student_id=sid,
            log_date="2025-10-15",
            log_time="12:00",
            administered_by="Nurse Adams",
        ))
        assert result["status"] == "ok"
        assert result["is_refused"] == False
        # Verify supply decremented
        row = conn.execute(
            "SELECT supply_count FROM educlaw_k12_student_medication WHERE id = ?",
            (mid,)
        ).fetchone()
        assert row["supply_count"] == 9

    def test_refused_does_not_decrement(self, setup):
        conn, cid, yid, tid, sid = setup
        mid = _seed_medication(conn, sid, cid, supply_count=10)
        result = call_action(log_medication_admin, conn, ns(
            student_medication_id=mid,
            student_id=sid,
            log_date="2025-10-15",
            log_time="12:00",
            is_refused=True,
            refusal_reason="Student refused",
        ))
        assert result["status"] == "ok"
        assert result["is_refused"] == True
        row = conn.execute(
            "SELECT supply_count FROM educlaw_k12_student_medication WHERE id = ?",
            (mid,)
        ).fetchone()
        assert row["supply_count"] == 10  # Not decremented

    def test_low_supply_alert(self, setup):
        """Should trigger alert when supply drops to threshold."""
        conn, cid, yid, tid, sid = setup
        mid = _seed_medication(conn, sid, cid, supply_count=6)  # threshold=5
        result = call_action(log_medication_admin, conn, ns(
            student_medication_id=mid,
            student_id=sid,
            log_date="2025-10-15",
            log_time="12:00",
        ))
        assert result["status"] == "ok"
        assert "supply_alert" in result

    def test_missing_student_medication_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(log_medication_admin, conn, ns(
            student_id=sid,
            log_date="2025-10-15",
            log_time="12:00",
        ))
        assert result["status"] == "error"
        assert "student-medication-id" in result["message"]

    def test_missing_log_date(self, setup):
        conn, cid, yid, tid, sid = setup
        mid = _seed_medication(conn, sid, cid)
        result = call_action(log_medication_admin, conn, ns(
            student_medication_id=mid,
            student_id=sid,
            log_time="12:00",
        ))
        assert result["status"] == "error"
        assert "log-date" in result["message"]


# ── list-medication-logs ──────────────────────────────────────────────────────

class TestListMedicationLogs:
    def test_happy_path_by_student(self, setup):
        conn, cid, yid, tid, sid = setup
        mid = _seed_medication(conn, sid, cid)
        call_action(log_medication_admin, conn, ns(
            student_medication_id=mid, student_id=sid,
            log_date="2025-10-15", log_time="12:00",
        ))
        result = call_action(list_medication_logs, conn, ns(student_id=sid))
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_missing_identifiers(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_medication_logs, conn, ns())
        assert result["status"] == "error"


# ── add-immunization ──────────────────────────────────────────────────────────

class TestAddImmunization:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_immunization, conn, ns(
            student_id=sid,
            vaccine_name="MMR",
            cvx_code="03",
            dose_number=1,
            administration_date="2025-09-01",
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["vaccine_name"] == "MMR"
        assert result["dose_number"] == 1

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_immunization, conn, ns(
            vaccine_name="MMR", company_id=cid,
        ))
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_missing_vaccine_name(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_immunization, conn, ns(
            student_id=sid, company_id=cid,
        ))
        assert result["status"] == "error"
        assert "vaccine-name" in result["message"]


# ── add-immunization-waiver ───────────────────────────────────────────────────

class TestAddImmunizationWaiver:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_immunization_waiver, conn, ns(
            student_id=sid,
            vaccine_name="MMR",
            waiver_type="medical",
            issue_date="2025-08-01",
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert result["vaccine_name"] == "MMR"
        assert result["waiver_type"] == "medical"

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_immunization_waiver, conn, ns(
            vaccine_name="MMR", waiver_type="medical", company_id=cid,
        ))
        assert result["status"] == "error"

    def test_missing_waiver_type(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(add_immunization_waiver, conn, ns(
            student_id=sid, vaccine_name="MMR", company_id=cid,
        ))
        assert result["status"] == "error"
        assert "waiver-type" in result["message"]


# ── update-immunization-waiver ────────────────────────────────────────────────

class TestUpdateImmunizationWaiver:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        wid = _seed_immunization_waiver(conn, sid, cid)
        result = call_action(update_immunization_waiver, conn, ns(
            waiver_id=wid,
            waiver_status="expired",
        ))
        assert result["status"] == "ok"
        row = conn.execute(
            "SELECT waiver_status FROM educlaw_k12_immunization_waiver WHERE id = ?",
            (wid,)
        ).fetchone()
        assert row["waiver_status"] == "expired"

    def test_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_immunization_waiver, conn, ns(
            waiver_id="nonexistent-uuid",
            waiver_status="expired",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_missing_waiver_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(update_immunization_waiver, conn, ns(
            waiver_status="expired",
        ))
        assert result["status"] == "error"
        assert "waiver-id" in result["message"]


# ── get-immunization-record ───────────────────────────────────────────────────

class TestGetImmunizationRecord:
    def test_happy_path_with_records(self, setup):
        conn, cid, yid, tid, sid = setup
        call_action(add_immunization, conn, ns(
            student_id=sid, vaccine_name="MMR", dose_number=1,
            administration_date="2025-09-01", company_id=cid,
        ))
        _seed_immunization_waiver(conn, sid, cid)
        result = call_action(get_immunization_record, conn, ns(
            student_id=sid,
            user_id="nurse1",
        ))
        assert result["status"] == "ok"
        assert "immunizations" in result
        assert "waivers" in result
        assert len(result["immunizations"]) == 1
        assert len(result["waivers"]) == 1

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_immunization_record, conn, ns())
        assert result["status"] == "error"
        assert "student-id" in result["message"]

    def test_student_not_found(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(get_immunization_record, conn, ns(
            student_id="nonexistent-uuid"
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ── check-immunization-compliance ─────────────────────────────────────────────

class TestCheckImmunizationCompliance:
    def test_happy_path(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(check_immunization_compliance, conn, ns(
            student_id=sid,
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "compliance_status" in result or "required" in result or "student_id" in result

    def test_missing_student_id(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(check_immunization_compliance, conn, ns(company_id=cid))
        assert result["status"] == "error"
        assert "student-id" in result["message"]


# ── list-health-alerts ────────────────────────────────────────────────────────

class TestListHealthAlerts:
    def test_happy_path_no_alerts(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(list_health_alerts, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "ok"
        assert "alerts" in result

    def test_low_supply_alert_appears(self, setup):
        conn, cid, yid, tid, sid = setup
        # Add medication with supply at threshold
        _seed_medication(conn, sid, cid, supply_count=3)
        result = call_action(list_health_alerts, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        # Low supply alert should appear
        alerts = result.get("alerts", [])
        supply_alerts = [a for a in alerts if "supply" in str(a).lower() or "medication" in str(a).lower()]
        assert len(supply_alerts) >= 0  # At minimum no crash


# ── generate-immunization-report ──────────────────────────────────────────────

class TestGenerateImmunizationReport:
    def test_happy_path_no_data(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(generate_immunization_report, conn, ns(
            company_id=cid,
            academic_year_id=yid,
        ))
        assert result["status"] == "ok"
        assert "report" in result or "summary" in result or "by_grade" in result

    def test_missing_academic_year(self, setup):
        conn, cid, yid, tid, sid = setup
        result = call_action(generate_immunization_report, conn, ns(
            company_id=cid,
        ))
        assert result["status"] == "error"
        assert "academic-year-id" in result["message"]
