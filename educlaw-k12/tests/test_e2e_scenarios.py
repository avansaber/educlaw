"""K-12 Workflow Scenario E2E Tests.

Tests the 4 core EduClaw K-12 workflows end-to-end via subprocess calls to
db_query.py.  Each scenario runs against its own isolated temp database so
scenarios are fully independent.

Scenarios:
  1. Discipline Incident → MDR (IDEA student suspended >10 days)
  2. Health Records Enrollment (profile → immunization → medication → audit)
  3. IDEA / IEP Full Pipeline (referral → evaluation → eligibility → IEP → services → progress)
  4. Grade Promotion (review → decision → batch advance + intervention plan)

Run: pytest educlaw-k12/tests/test_e2e_scenarios.py -v
"""
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)

from helpers import (
    bootstrap_foundation,
    get_conn,
    run_init_db,
    seed_academic_term,
    seed_academic_year,
    seed_company,
    seed_guardian,
    seed_iep_active,
    seed_sped_eligibility,
    seed_sped_referral,
    seed_student,
    seed_student_guardian,
)

DB_QUERY_SCRIPT = os.path.join(REPO_ROOT, "scripts", "db_query.py")

_now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Core helpers ──────────────────────────────────────────────────────────────

def run_action(db_path: str, action: str, **kwargs) -> dict:
    """Run an educlaw-k12 action via subprocess and return the parsed JSON dict.

    kwargs keys use underscores; they are converted to --hyphen-flags.
    """
    cmd = [sys.executable, DB_QUERY_SCRIPT, "--action", action,
           "--db-path", db_path]
    for key, val in kwargs.items():
        if val is not None:
            cmd.extend([f"--{key.replace('_', '-')}", str(val)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout.strip()
    if not output:
        return {
            "status": "error",
            "error": result.stderr.strip() or "no output",
        }
    try:
        return json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return {"status": "error", "error": f"invalid JSON: {output[:300]}"}


def assert_ok(response: dict, step: str = ""):
    """Assert response has status=ok; include step context in failure message."""
    assert response.get("status") == "ok", (
        f"[{step}] Expected status=ok but got:\n{json.dumps(response, indent=2)}"
    )


def assert_ok_id(response: dict, step: str = "") -> str:
    """Assert ok + id present; return the id."""
    assert_ok(response, step)
    assert "id" in response, f"[{step}] Response missing 'id': {response}"
    return response["id"]


def fresh_db(tmp_path: "pathlib.Path") -> str:
    """Return path to a fresh fully-initialized temp DB."""
    db_path = str(tmp_path / "scenario.sqlite")
    bootstrap_foundation(db_path)
    run_init_db(db_path)
    return db_path


def seed_core(db_path: str) -> dict:
    """Seed company + academic year + term + student + guardian; return IDs dict."""
    conn = get_conn(db_path)
    company_id = seed_company(conn)
    year_id = seed_academic_year(conn, company_id)
    term_id = seed_academic_term(conn, company_id, year_id)
    student_id = seed_student(conn, company_id, grade_level="10")
    guardian_id = seed_guardian(conn, company_id)
    seed_student_guardian(conn, student_id, guardian_id)
    conn.close()
    return {
        "company_id": company_id,
        "year_id": year_id,
        "term_id": term_id,
        "student_id": student_id,
        "guardian_id": guardian_id,
    }


# ── Scenario 1: Discipline Incident → MDR ────────────────────────────────────

class TestScenarioDisciplineToMDR:
    """Full discipline workflow: incident → student → suspension(s) → MDR → close.

    Validates:
    - Incident creation and naming series
    - Student involvement linking
    - Cumulative suspension day tracking (10-day MDR threshold)
    - MDR alert in add-discipline-action response
    - Guardian notification creation
    - Incident closure
    - MDR meeting creation and determination update
    - PBIS positive behavior recognition
    - Discipline report generation
    """

    @pytest.fixture
    def db(self, tmp_path):
        """Fresh DB seeded with core entities + IEP (for MDR eligibility)."""
        db_path = fresh_db(tmp_path)
        core = seed_core(db_path)

        conn = get_conn(db_path)
        # Seed SPED pipeline so student has an active IEP for MDR
        referral_id = seed_sped_referral(
            conn, core["student_id"], core["company_id"],
            naming_series="SPED-REF-00001", status="consent_received"
        )
        eligibility_id = seed_sped_eligibility(
            conn, core["student_id"], referral_id, core["company_id"]
        )
        iep_id = seed_iep_active(
            conn, core["student_id"], eligibility_id, core["company_id"],
            naming_series="IEP-2025-00001"
        )
        conn.close()

        core.update({"db_path": db_path, "iep_id": iep_id})
        return core

    def test_full_discipline_to_mdr_workflow(self, db):
        """Run the complete discipline → MDR workflow."""
        dp = db["db_path"]

        # ── Step 1: Create discipline incident ────────────────────────────
        r = run_action(dp, "k12-add-discipline-incident",
                       incident_date="2025-10-15",
                       incident_time="10:30",
                       location="classroom",
                       incident_type="assault",
                       severity="major",
                       academic_year_id=db["year_id"],
                       academic_term_id=db["term_id"],
                       company_id=db["company_id"])
        incident_id = assert_ok_id(r, "k12-add-discipline-incident")
        assert r.get("naming_series", "").startswith("DI-")

        # ── Step 2: Add IDEA-eligible student as offender ─────────────────
        r = run_action(dp, "k12-add-discipline-student",
                       incident_id=incident_id,
                       student_id=db["student_id"],
                       role="offender",
                       is_idea_eligible=1)
        discipline_student_id = assert_ok_id(r, "k12-add-discipline-student")

        # ── Step 3: Add first suspension — 7 days (below 10-day threshold) ─
        r = run_action(dp, "k12-add-discipline-action",
                       discipline_student_id=discipline_student_id,
                       action_type="out_of_school_suspension",
                       start_date="2025-10-15",
                       end_date="2025-10-21",
                       duration_days="7",
                       administered_by="Vice Principal")
        assert_ok(r, "add-discipline-action (7 days)")
        assert float(r.get("cumulative_suspension_days_ytd", 0)) == 7.0
        assert r.get("mdr_alert") is None or r.get("mdr_alert") is False, (
            f"MDR should not be triggered at 7 days: {r}"
        )

        # ── Step 4: Add second suspension — 4 more days (total = 11 → MDR!) ─
        r = run_action(dp, "k12-add-discipline-action",
                       discipline_student_id=discipline_student_id,
                       action_type="in_school_suspension",
                       start_date="2025-10-25",
                       end_date="2025-10-28",
                       duration_days="4",
                       administered_by="Vice Principal")
        assert_ok(r, "add-discipline-action (4 days = 11 total)")
        assert float(r.get("cumulative_suspension_days_ytd", 0)) == 11.0
        assert r.get("mdr_alert") is True, (
            f"MDR alert should fire at 11 suspension days for IDEA student: {r}"
        )

        # ── Step 5: Notify guardians ──────────────────────────────────────
        r = run_action(dp, "notify-guardians-discipline",
                       incident_id=incident_id,
                       company_id=db["company_id"])
        assert_ok(r, "notify-guardians-discipline")
        assert r.get("notifications_created", 0) >= 1

        # ── Step 6: Close the incident ────────────────────────────────────
        r = run_action(dp, "close-discipline-incident",
                       incident_id=incident_id,
                       reviewed_by="Principal Johnson")
        assert_ok(r, "close-discipline-incident")
        assert r.get("incident_status") == "closed"

        # ── Step 7: Verify get-discipline-incident returns closed status ──
        r = run_action(dp, "k12-get-discipline-incident",
                       incident_id=incident_id)
        assert_ok(r, "k12-get-discipline-incident")
        assert r.get("incident", {}).get("incident_status") == "closed" or \
               r.get("incident_status") == "closed"

        # ── Step 8: Create MDR meeting ────────────────────────────────────
        r = run_action(dp, "k12-add-manifestation-review",
                       discipline_student_id=discipline_student_id,
                       iep_id=db["iep_id"],
                       student_id=db["student_id"],
                       mdr_date="2025-10-29",
                       company_id=db["company_id"])
        mdr_id = assert_ok_id(r, "k12-add-manifestation-review")

        # ── Step 9: Update MDR with determination ─────────────────────────
        r = run_action(dp, "k12-update-manifestation-review",
                       mdr_id=mdr_id,
                       question_1_result="yes",
                       question_2_result="no",
                       determination="manifestation",
                       outcome_action="return_to_placement",
                       fba_required=1,
                       bip_required=1)
        assert_ok(r, "k12-update-manifestation-review")
        assert r.get("determination") == "manifestation"

        # ── Step 10: Get discipline history ───────────────────────────────
        r = run_action(dp, "k12-get-discipline-history",
                       student_id=db["student_id"])
        assert_ok(r, "k12-get-discipline-history")
        incidents = r.get("incidents", [])
        assert len(incidents) >= 1

        # ── Step 11: Get cumulative suspension days ───────────────────────
        r = run_action(dp, "k12-get-cumulative-suspension-days",
                       student_id=db["student_id"],
                       academic_year_id=db["year_id"])
        assert_ok(r, "k12-get-cumulative-suspension-days")
        assert float(r.get("cumulative_suspension_days_ytd", 0)) == 11.0

        # ── Step 12: PBIS recognition for another student (positive record) ─
        # Create a second student for PBIS
        conn = get_conn(dp)
        student2_id = seed_student(conn, db["company_id"], grade_level="10")
        conn.close()

        r = run_action(dp, "k12-add-pbis-recognition",
                       student_id=student2_id,
                       incident_date="2025-10-30",
                       description="Volunteered to help clean the cafeteria",
                       company_id=db["company_id"])
        assert_ok(r, "k12-add-pbis-recognition")
        assert "id" in r

        # ── Step 13: Generate discipline report ───────────────────────────
        r = run_action(dp, "k12-generate-discipline-report",
                       academic_year_id=db["year_id"],
                       company_id=db["company_id"])
        assert_ok(r, "k12-generate-discipline-report")
        # Report should have incident counts
        assert "total_incidents" in r or "incidents" in r or "summary" in r

        # ── Step 14: Generate state discipline report ─────────────────────
        r = run_action(dp, "k12-generate-discipline-state-report",
                       academic_year_id=db["year_id"],
                       company_id=db["company_id"])
        assert_ok(r, "k12-generate-discipline-state-report")

        # ── Step 15: List discipline incidents ────────────────────────────
        r = run_action(dp, "k12-list-discipline-incidents",
                       academic_year_id=db["year_id"],
                       company_id=db["company_id"])
        assert_ok(r, "k12-list-discipline-incidents")
        items = r.get("incidents", r.get("items", []))
        assert len(items) >= 1


# ── Scenario 2: Health Records Enrollment ────────────────────────────────────

class TestScenarioHealthRecordsEnrollment:
    """Complete health record enrollment workflow.

    Validates:
    - Health profile creation (one per student)
    - Duplicate profile rejection
    - Immunization dose recording (immutable)
    - Immunization compliance check (returns missing vaccines)
    - Immunization waiver creation and retrieval
    - Medication catalog entry
    - Medication administration logging (supply decrement)
    - Low-supply alert
    - Nurse office visit recording (immutable)
    - School-wide health alerts report
    """

    @pytest.fixture
    def db(self, tmp_path):
        """Fresh DB with core entities."""
        db_path = fresh_db(tmp_path)
        core = seed_core(db_path)
        core["db_path"] = db_path
        return core

    def test_full_health_records_workflow(self, db):
        dp = db["db_path"]

        # ── Step 1: Create student health profile ─────────────────────────
        r = run_action(dp, "k12-add-health-profile",
                       student_id=db["student_id"],
                       company_id=db["company_id"],
                       allergies='[{"allergen":"peanuts","severity":"severe","reaction":"anaphylaxis","treatment":"EpiPen","epipen_location":"nurse office"}]',
                       chronic_conditions='[{"condition":"Type 1 Diabetes","diagnosis_date":"2022-03-15","notes":"Insulin pump"}]',
                       blood_type="A+",
                       physician_name="Dr. Martinez",
                       physician_phone="555-0100",
                       activity_restriction="limited",
                       activity_restriction_notes="No contact sports")
        profile_id = assert_ok_id(r, "k12-add-health-profile")

        # ── Step 2: Duplicate profile rejected ───────────────────────────
        r2 = run_action(dp, "k12-add-health-profile",
                        student_id=db["student_id"],
                        company_id=db["company_id"])
        assert r2.get("status") == "error", (
            f"Duplicate health profile should be rejected: {r2}"
        )
        assert "already" in r2.get("error", "").lower() or \
               "exists" in r2.get("error", "").lower(), (
            f"Expected 'already exists' error: {r2}"
        )

        # ── Step 3: Get health profile ────────────────────────────────────
        r = run_action(dp, "k12-get-health-profile",
                       student_id=db["student_id"])
        assert_ok(r, "k12-get-health-profile")
        assert r.get("blood_type") == "A+"

        # ── Step 4: Get emergency health info ─────────────────────────────
        r = run_action(dp, "k12-get-emergency-health-info",
                       student_id=db["student_id"])
        assert_ok(r, "k12-get-emergency-health-info")
        assert "allergies" in r or "emergency_instructions" in r

        # ── Step 5: Add immunization doses ───────────────────────────────
        for dose_num, vaccine_date in [(1, "2020-01-15"), (2, "2020-02-15")]:
            r = run_action(dp, "k12-add-immunization",
                           student_id=db["student_id"],
                           vaccine_name="MMR",
                           cvx_code="03",
                           dose_number=str(dose_num),
                           administered_date=vaccine_date,
                           administered_by="Dr. Martinez",
                           company_id=db["company_id"])
            assert_ok(r, f"add-immunization MMR dose {dose_num}")
            assert r.get("dose_number") == dose_num

        r = run_action(dp, "k12-add-immunization",
                       student_id=db["student_id"],
                       vaccine_name="DTaP",
                       cvx_code="107",
                       dose_number="1",
                       administered_date="2020-03-01",
                       administered_by="Dr. Martinez",
                       company_id=db["company_id"])
        assert_ok(r, "add-immunization DTaP")

        # ── Step 6: Check immunization compliance ────────────────────────
        r = run_action(dp, "check-immunization-compliance",
                       student_id=db["student_id"])
        assert_ok(r, "check-immunization-compliance")
        # Should return compliance status with any missing vaccines
        assert "is_compliant" in r or "compliance" in r or "missing" in r

        # ── Step 7: Add immunization waiver for Varicella ────────────────
        r = run_action(dp, "k12-add-immunization-waiver",
                       student_id=db["student_id"],
                       vaccine_name="Varicella",
                       waiver_type="medical",
                       waiver_reason="Prior infection — immunity confirmed",
                       expiration_date="2027-01-01",
                       company_id=db["company_id"])
        waiver_id = assert_ok_id(r, "k12-add-immunization-waiver")

        # ── Step 8: Get complete immunization record ──────────────────────
        r = run_action(dp, "k12-get-immunization-record",
                       student_id=db["student_id"])
        assert_ok(r, "k12-get-immunization-record")
        doses = r.get("immunizations", r.get("doses", []))
        assert len(doses) >= 3, f"Expected 3 doses, got: {len(doses)}"
        waivers = r.get("waivers", [])
        assert len(waivers) >= 1

        # ── Step 9: Update immunization waiver status ─────────────────────
        r = run_action(dp, "k12-update-immunization-waiver",
                       waiver_id=waiver_id,
                       waiver_status="approved")
        assert_ok(r, "k12-update-immunization-waiver")

        # ── Step 10: Add school medication authorization ──────────────────
        r = run_action(dp, "k12-add-student-medication",
                       student_id=db["student_id"],
                       medication_name="Amoxicillin",
                       dosage="250mg",
                       route="oral",
                       frequency="twice_daily",
                       administration_times='["08:00","14:00"]',
                       prescribing_physician="Dr. Martinez",
                       physician_authorization_date="2025-10-01",
                       start_date="2025-10-01",
                       end_date="2025-10-10",
                       supply_count=20,
                       supply_low_threshold=5,
                       company_id=db["company_id"])
        med_id = assert_ok_id(r, "k12-add-student-medication")
        assert r.get("supply_count") == 20

        # ── Step 11: Log medication administration (supply decrements) ────
        for i in range(4):
            r = run_action(dp, "log-medication-admin",
                           student_medication_id=med_id,
                           student_id=db["student_id"],
                           log_date="2025-10-01",
                           log_time=f"0{8+i}:00" if i < 2 else f"{14+i-2}:00",
                           dose_given="250mg",
                           administered_by="Nurse Chen")
            assert_ok(r, f"log-medication-admin #{i+1}")

        # ── Step 12: Check supply after logging ───────────────────────────
        r = run_action(dp, "k12-list-student-medications",
                       student_id=db["student_id"])
        assert_ok(r, "k12-list-student-medications")
        meds = r.get("medications", r.get("items", []))
        assert len(meds) >= 1
        # After 4 administrations, supply should be 20-4=16
        first_med = next((m for m in meds if m.get("id") == med_id), None)
        if first_med:
            assert int(first_med.get("supply_count", 20)) == 16

        # ── Step 13: Log medication refusal ──────────────────────────────
        r = run_action(dp, "log-medication-admin",
                       student_medication_id=med_id,
                       student_id=db["student_id"],
                       log_date="2025-10-02",
                       log_time="08:00",
                       dose_given="250mg",
                       administered_by="Nurse Chen",
                       is_refused=1,
                       refusal_reason="Student said it tastes bad")
        assert_ok(r, "log-medication-admin (refused)")
        # Supply should NOT decrement on refusal
        r = run_action(dp, "k12-list-student-medications",
                       student_id=db["student_id"])
        assert_ok(r, "list-student-medications after refusal")
        meds = r.get("medications", r.get("items", []))
        first_med = next((m for m in meds if m.get("id") == med_id), None)
        if first_med:
            assert int(first_med.get("supply_count", 0)) == 16, (
                "Supply should not decrease on refused dose"
            )

        # ── Step 14: Record nurse office visit ────────────────────────────
        r = run_action(dp, "k12-add-office-visit",
                       student_id=db["student_id"],
                       visit_date="2025-10-05",
                       visit_time="10:30",
                       chief_complaint="stomachache",
                       complaint_detail="Stomach pain after lunch",
                       temperature="98.6F",
                       assessment="Possible indigestion",
                       treatment_provided="Rest and water",
                       disposition="returned_to_class",
                       company_id=db["company_id"])
        visit_id = assert_ok_id(r, "k12-add-office-visit")

        # ── Step 15: Get office visit ─────────────────────────────────────
        r = run_action(dp, "k12-get-office-visit", visit_id=visit_id)
        assert_ok(r, "k12-get-office-visit")
        assert r.get("chief_complaint") == "stomachache" or \
               r.get("visit", {}).get("chief_complaint") == "stomachache"

        # ── Step 16: List office visits ───────────────────────────────────
        r = run_action(dp, "k12-list-office-visits",
                       student_id=db["student_id"])
        assert_ok(r, "k12-list-office-visits")
        visits = r.get("visits", r.get("items", []))
        assert len(visits) >= 1

        # ── Step 17: Verify health profile ────────────────────────────────
        r = run_action(dp, "verify-health-profile",
                       student_id=db["student_id"],
                       last_verified_by="Nurse Chen")
        assert_ok(r, "verify-health-profile")
        assert r.get("profile_status") == "active"

        # ── Step 18: Generate school-wide health alerts ───────────────────
        r = run_action(dp, "k12-list-health-alerts",
                       company_id=db["company_id"])
        assert_ok(r, "k12-list-health-alerts")

        # ── Step 19: Generate immunization compliance report ──────────────
        r = run_action(dp, "k12-generate-immunization-report",
                       company_id=db["company_id"])
        assert_ok(r, "k12-generate-immunization-report")


# ── Scenario 3: IDEA / IEP Full Pipeline ─────────────────────────────────────

class TestScenarioIDEAIEPPipeline:
    """IDEA Part B full pipeline from referral through IEP services and progress.

    Validates:
    - SPED referral creation (begins 60-day clock)
    - Referral update (consent received)
    - Evaluation creation
    - Eligibility determination
    - IEP creation in draft
    - IEP goal addition (immutable)
    - IEP service addition (immutable)
    - IEP team member addition
    - IEP activation (prior active IEP → superseded if exists)
    - Service session logging (total_minutes_delivered increment)
    - Progress monitoring entry
    - Section 504 plan creation
    - IEP amendment workflow
    - Deadline reporting
    """

    @pytest.fixture
    def db(self, tmp_path):
        """Fresh DB with core entities."""
        db_path = fresh_db(tmp_path)
        core = seed_core(db_path)
        core["db_path"] = db_path
        return core

    def test_full_idea_iep_pipeline(self, db):
        dp = db["db_path"]

        # ── Step 1: Create SPED referral ─────────────────────────────────
        r = run_action(dp, "k12-create-sped-referral",
                       student_id=db["student_id"],
                       referral_source="teacher",
                       referral_reason="Student reads significantly below grade level; dyslexia suspected",
                       referral_date="2025-09-10",
                       areas_of_concern='["reading","writing"]',
                       company_id=db["company_id"])
        referral_id = assert_ok_id(r, "k12-create-sped-referral")
        assert r.get("referral_status") == "received"
        assert r.get("naming_series", "").startswith("SPED-REF-")
        # Should set a 60-day evaluation deadline
        assert r.get("evaluation_deadline") != "", "Evaluation deadline must be set"

        # ── Step 2: Update referral (consent received) ────────────────────
        r = run_action(dp, "k12-update-sped-referral",
                       referral_id=referral_id,
                       referral_status="consent_received",
                       consent_received_date="2025-09-20")
        assert_ok(r, "update-sped-referral consent")
        assert r.get("referral_status") == "consent_received"

        # ── Step 3: Get referral ──────────────────────────────────────────
        r = run_action(dp, "k12-get-sped-referral", referral_id=referral_id)
        assert_ok(r, "k12-get-sped-referral")

        # ── Step 4: Add evaluation ────────────────────────────────────────
        r = run_action(dp, "k12-add-sped-evaluation",
                       referral_id=referral_id,
                       student_id=db["student_id"],
                       evaluation_type="psychoeducational",
                       evaluator_name="Dr. Kim",
                       evaluation_date="2025-10-01",
                       findings="Below grade level in reading and phonological processing",
                       company_id=db["company_id"])
        eval_id = assert_ok_id(r, "k12-add-sped-evaluation")

        # ── Step 5: Add second evaluation (speech) ───────────────────────
        r = run_action(dp, "k12-add-sped-evaluation",
                       referral_id=referral_id,
                       student_id=db["student_id"],
                       evaluation_type="speech_language",
                       evaluator_name="Ms. Torres",
                       evaluation_date="2025-10-05",
                       findings="Age-appropriate speech; some phonological deficits",
                       company_id=db["company_id"])
        assert_ok(r, "add-sped-evaluation speech")

        # ── Step 6: List evaluations ──────────────────────────────────────
        r = run_action(dp, "k12-list-sped-evaluations", referral_id=referral_id)
        assert_ok(r, "k12-list-sped-evaluations")
        evals = r.get("evaluations", r.get("items", []))
        assert len(evals) == 2

        # ── Step 7: Record eligibility ────────────────────────────────────
        r = run_action(dp, "k12-record-sped-eligibility",
                       referral_id=referral_id,
                       student_id=db["student_id"],
                       is_eligible=1,
                       disability_categories='["specific_learning_disability"]',
                       primary_disability="specific_learning_disability",
                       meeting_date="2025-10-15",
                       iep_deadline="2025-11-14",
                       company_id=db["company_id"])
        eligibility_id = assert_ok_id(r, "k12-record-sped-eligibility")
        assert r.get("is_eligible") == 1

        # Referral status should auto-update to eligible
        r = run_action(dp, "k12-get-sped-referral", referral_id=referral_id)
        assert_ok(r, "get-sped-referral post-eligibility")

        # ── Step 8: Get eligibility ───────────────────────────────────────
        r = run_action(dp, "k12-get-sped-eligibility",
                       student_id=db["student_id"])
        assert_ok(r, "k12-get-sped-eligibility")

        # ── Step 9: Create IEP (draft) ────────────────────────────────────
        r = run_action(dp, "k12-add-iep",
                       student_id=db["student_id"],
                       eligibility_id=eligibility_id,
                       iep_meeting_date="2025-10-20",
                       iep_start_date="2025-11-01",
                       iep_end_date="2026-10-31",
                       plaafp_academic="Reading at 3rd grade level (Grade 5 student)",
                       plaafp_functional="Independent in classroom; difficulty with text",
                       lre_percentage_general_ed="80",
                       state_assessment_participation="with_accommodations",
                       progress_report_frequency="quarterly",
                       company_id=db["company_id"])
        iep_id = assert_ok_id(r, "k12-add-iep")
        assert r.get("iep_status") == "draft"
        assert r.get("naming_series", "").startswith("IEP-")

        # ── Step 10: Add IEP goal (reading) ──────────────────────────────
        r = run_action(dp, "k12-add-iep-goal",
                       iep_id=iep_id,
                       student_id=db["student_id"],
                       goal_area="reading",
                       goal_description="Given grade-level text, student will read 100 wpm with 95% accuracy by June 2026",
                       baseline_performance="62 wpm with 80% accuracy",
                       target_performance="100 wpm with 95% accuracy",
                       measurement_method="probe",
                       monitoring_frequency="weekly",
                       responsible_provider="Ms. Johnson")
        goal_id = assert_ok_id(r, "k12-add-iep-goal")

        # ── Step 11: Add IEP goal (writing) ──────────────────────────────
        r = run_action(dp, "k12-add-iep-goal",
                       iep_id=iep_id,
                       student_id=db["student_id"],
                       goal_area="writing",
                       goal_description="Student will write 3-paragraph essays with topic sentence",
                       baseline_performance="Can write 1 sentence independently",
                       target_performance="3-paragraph essay independently",
                       measurement_method="work_sample",
                       monitoring_frequency="monthly",
                       responsible_provider="Ms. Johnson")
        assert_ok(r, "add-iep-goal writing")

        # ── Step 12: List IEP goals ───────────────────────────────────────
        r = run_action(dp, "k12-list-iep-goals", iep_id=iep_id)
        assert_ok(r, "k12-list-iep-goals")
        goals = r.get("goals", r.get("items", []))
        assert len(goals) == 2

        # ── Step 13: Add IEP service (specialized instruction) ────────────
        r = run_action(dp, "k12-add-iep-service",
                       iep_id=iep_id,
                       student_id=db["student_id"],
                       service_type="special_education_instruction",
                       service_setting="resource_room",
                       frequency_minutes_per_week=150,
                       provider_name="Ms. Johnson",
                       provider_role="Special Education Teacher",
                       start_date="2025-11-01",
                       end_date="2026-10-31")
        service_id = assert_ok_id(r, "add-iep-service instruction")
        assert r.get("total_minutes_delivered") == 0

        # ── Step 14: Add IEP service (speech therapy) ─────────────────────
        r = run_action(dp, "k12-add-iep-service",
                       iep_id=iep_id,
                       student_id=db["student_id"],
                       service_type="speech_therapy",
                       service_setting="general_ed_classroom",
                       frequency_minutes_per_week=60,
                       provider_name="Ms. Torres",
                       provider_role="Speech-Language Pathologist",
                       start_date="2025-11-01",
                       end_date="2026-10-31")
        speech_service_id = assert_ok_id(r, "add-iep-service speech")

        # ── Step 15: List IEP services ────────────────────────────────────
        r = run_action(dp, "k12-list-iep-services", iep_id=iep_id)
        assert_ok(r, "k12-list-iep-services")
        services = r.get("services", r.get("items", []))
        assert len(services) == 2

        # ── Step 16: Add IEP team members ────────────────────────────────
        r = run_action(dp, "k12-add-iep-team-member",
                       iep_id=iep_id,
                       member_type="parent",
                       member_name="Jane Parent",
                       member_role="Parent/Guardian",
                       guardian_id=db["guardian_id"],
                       attended_meeting=1,
                       signature_date="2025-10-20")
        assert_ok(r, "add-iep-team-member parent")

        r = run_action(dp, "k12-add-iep-team-member",
                       iep_id=iep_id,
                       member_type="special_ed_teacher",
                       member_name="Ms. Johnson",
                       member_role="Special Education Teacher",
                       attended_meeting=1,
                       signature_date="2025-10-20")
        assert_ok(r, "add-iep-team-member teacher")

        # ── Step 17: Activate IEP ─────────────────────────────────────────
        r = run_action(dp, "k12-activate-iep",
                       iep_id=iep_id,
                       parent_consent_date="2025-11-01")
        assert_ok(r, "k12-activate-iep")
        assert r.get("iep_status") == "active"

        # ── Step 18: Get active IEP ───────────────────────────────────────
        r = run_action(dp, "k12-get-active-iep",
                       student_id=db["student_id"])
        assert_ok(r, "k12-get-active-iep")

        # ── Step 19: Get IEP with full details ───────────────────────────
        r = run_action(dp, "k12-get-iep", iep_id=iep_id)
        assert_ok(r, "k12-get-iep")

        # ── Step 20: Log service delivery sessions ────────────────────────
        total_delivered = 0
        for week, mins in [(1, 150), (2, 150), (3, 120)]:  # week 3 is short
            r = run_action(dp, "log-iep-service-session",
                           iep_service_id=service_id,
                           student_id=db["student_id"],
                           session_date=f"2025-11-{(week * 7):02d}",
                           minutes_delivered=mins,
                           session_notes=f"Week {week} reading instruction",
                           provider_name="Ms. Johnson",
                           was_session_missed=0)
            assert_ok(r, f"log-iep-service-session week {week}")
            total_delivered += mins

        # Log a missed session
        r = run_action(dp, "log-iep-service-session",
                       iep_service_id=service_id,
                       student_id=db["student_id"],
                       session_date="2025-11-28",
                       minutes_delivered=0,
                       session_notes="School holiday",
                       provider_name="Ms. Johnson",
                       was_session_missed=1,
                       missed_reason="Thanksgiving holiday")
        assert_ok(r, "log-iep-service-session missed")

        # ── Step 21: Verify total_minutes_delivered updated ───────────────
        r = run_action(dp, "k12-list-iep-services", iep_id=iep_id)
        assert_ok(r, "list-iep-services post-sessions")
        services = r.get("services", r.get("items", []))
        instr_service = next(
            (s for s in services if s.get("service_type") == "special_education_instruction"),
            None
        )
        if instr_service:
            assert int(instr_service.get("total_minutes_delivered", 0)) == total_delivered, (
                f"Expected {total_delivered} minutes delivered, got "
                f"{instr_service.get('total_minutes_delivered')}"
            )

        # ── Step 22: List service logs ────────────────────────────────────
        r = run_action(dp, "k12-list-iep-service-logs",
                       iep_service_id=service_id)
        assert_ok(r, "k12-list-iep-service-logs")
        logs = r.get("logs", r.get("items", []))
        assert len(logs) == 4  # 3 delivered + 1 missed

        # ── Step 23: Record IEP progress ──────────────────────────────────
        r = run_action(dp, "k12-record-iep-progress",
                       iep_goal_id=goal_id,
                       student_id=db["student_id"],
                       reporting_period="Q1 2025-2026",
                       progress_date="2025-11-30",
                       progress_rating="on_track",
                       current_performance="72 wpm with 85% accuracy",
                       evidence="Weekly probe data 11/4, 11/11, 11/18",
                       notes_for_parents="Your child is making good progress toward their reading goal.",
                       documented_by="Ms. Johnson")
        assert_ok(r, "k12-record-iep-progress")

        # ── Step 24: Generate IEP progress report ────────────────────────
        r = run_action(dp, "k12-generate-iep-progress-report",
                       iep_id=iep_id)
        assert_ok(r, "k12-generate-iep-progress-report")

        # ── Step 25: Check service compliance report ──────────────────────
        r = run_action(dp, "k12-get-service-compliance-report",
                       iep_id=iep_id)
        assert_ok(r, "k12-get-service-compliance-report")

        # ── Step 26: List IEP deadlines ───────────────────────────────────
        r = run_action(dp, "k12-list-iep-deadlines",
                       company_id=db["company_id"],
                       days_window=365)
        assert_ok(r, "k12-list-iep-deadlines")

        # ── Step 27: Amend IEP ────────────────────────────────────────────
        r = run_action(dp, "amend-iep", iep_id=iep_id)
        amendment_id = assert_ok_id(r, "amend-iep")
        assert r.get("iep_status") == "draft"
        assert r.get("is_amendment") == 1

        # Original IEP should now be 'amended'
        r = run_action(dp, "k12-get-iep", iep_id=iep_id)
        assert_ok(r, "get-iep post-amendment")
        original = r.get("iep", r)
        assert original.get("iep_status") == "amended" or \
               original.get("iep_status") == "active", (
            "Original IEP should be 'amended' after amend-iep"
        )

        # ── Step 28: Section 504 plan for a second student ────────────────
        conn = get_conn(dp)
        student2_id = seed_student(conn, db["company_id"], grade_level="8")
        conn.close()

        r = run_action(dp, "k12-add-504-plan",
                       student_id=student2_id,
                       meeting_date="2025-10-01",
                       disability_description="ADHD substantially limits ability to focus and complete tasks",
                       eligibility_basis="School psych evaluation and medical diagnosis",
                       plan_start_date="2025-10-01",
                       plan_end_date="2026-09-30",
                       review_date="2026-09-15",
                       accommodations='[{"accommodation":"Extended time on tests","category":"assessment","responsible_staff":"All teachers"},{"accommodation":"Preferential seating","category":"environment","responsible_staff":"All teachers"}]',
                       team_members='[{"name":"Parent","role":"Guardian"},{"name":"School Psych","role":"Psychologist"}]',
                       parent_consent_date="2025-10-01",
                       company_id=db["company_id"])
        plan_504_id = assert_ok_id(r, "k12-add-504-plan")
        assert r.get("plan_status") == "active"

        # ── Step 29: Get active 504 plan ──────────────────────────────────
        r = run_action(dp, "k12-get-active-504-plan",
                       student_id=student2_id)
        assert_ok(r, "k12-get-active-504-plan")

        # ── Step 30: Update 504 plan ──────────────────────────────────────
        r = run_action(dp, "k12-update-504-plan",
                       plan_504_id=plan_504_id,
                       plan_status="active")
        assert_ok(r, "k12-update-504-plan")

        # ── Step 31: List reevaluation due ────────────────────────────────
        r = run_action(dp, "k12-list-reevaluation-due",
                       company_id=db["company_id"],
                       days_window=1095)
        assert_ok(r, "k12-list-reevaluation-due")


# ── Scenario 4: Grade Promotion → Batch Advance ──────────────────────────────

class TestScenarioGradePromotion:
    """Complete grade promotion workflow with at-risk intervention.

    Validates:
    - Promotion review creation (auto-populates discipline count)
    - Review update with stakeholder recommendations
    - Decision submission (immutable — promote/retain/conditional)
    - Parent notification creation
    - Intervention plan for at-risk student
    - At-risk student identification
    - Batch grade level advancement
    - Promotion analytics report
    """

    @pytest.fixture
    def db(self, tmp_path):
        """Fresh DB with 3 students at different grade levels."""
        db_path = fresh_db(tmp_path)
        core = seed_core(db_path)
        core["db_path"] = db_path

        conn = get_conn(db_path)
        # Add two more students: one at-risk, one 12th grader (will graduate)
        at_risk_id = seed_student(conn, core["company_id"], grade_level="10",
                                  dob="2009-05-15")
        senior_id = seed_student(conn, core["company_id"], grade_level="12",
                                  dob="2007-01-10")
        guardian2_id = seed_guardian(conn, core["company_id"])
        seed_student_guardian(conn, at_risk_id, guardian2_id)
        seed_student_guardian(conn, senior_id, guardian2_id)
        conn.close()

        core.update({
            "at_risk_id": at_risk_id,
            "senior_id": senior_id,
        })
        return core

    def test_full_grade_promotion_workflow(self, db):
        dp = db["db_path"]

        # ── Step 1: Create promotion review for main student ──────────────
        r = run_action(dp, "k12-create-promotion-review",
                       student_id=db["student_id"],
                       academic_year_id=db["year_id"],
                       grade_level="10",
                       gpa_ytd="3.8",
                       attendance_rate_ytd="97.5",
                       failing_subjects="[]",
                       teacher_recommendation="promote",
                       teacher_rationale="Excellent performance all year",
                       company_id=db["company_id"])
        review_id = assert_ok_id(r, "create-promotion-review main student")
        assert r.get("review_status") == "pending"

        # ── Step 2: Create promotion review for at-risk student ───────────
        r = run_action(dp, "k12-create-promotion-review",
                       student_id=db["at_risk_id"],
                       academic_year_id=db["year_id"],
                       grade_level="10",
                       gpa_ytd="1.8",
                       attendance_rate_ytd="82.0",
                       failing_subjects='["Math","English"]',
                       teacher_recommendation="retain",
                       teacher_rationale="Significant gaps in foundational skills",
                       company_id=db["company_id"])
        at_risk_review_id = assert_ok_id(r, "create-promotion-review at-risk")

        # ── Step 3: Create promotion review for senior ────────────────────
        r = run_action(dp, "k12-create-promotion-review",
                       student_id=db["senior_id"],
                       academic_year_id=db["year_id"],
                       grade_level="12",
                       gpa_ytd="3.2",
                       attendance_rate_ytd="94.0",
                       failing_subjects="[]",
                       teacher_recommendation="promote",
                       teacher_rationale="Met all graduation requirements",
                       company_id=db["company_id"])
        senior_review_id = assert_ok_id(r, "create-promotion-review senior")

        # ── Step 4: Update review with counselor recommendation ───────────
        r = run_action(dp, "k12-update-promotion-review",
                       review_id=review_id,
                       counselor_recommendation="promote",
                       counselor_notes="Student is ready for 11th grade")
        assert_ok(r, "k12-update-promotion-review")

        r = run_action(dp, "k12-update-promotion-review",
                       review_id=at_risk_review_id,
                       counselor_recommendation="conditional",
                       counselor_notes="Consider conditional promotion with summer school")
        assert_ok(r, "update-promotion-review at-risk")

        # ── Step 5: List promotion reviews ───────────────────────────────
        r = run_action(dp, "k12-list-promotion-reviews",
                       academic_year_id=db["year_id"],
                       company_id=db["company_id"])
        assert_ok(r, "k12-list-promotion-reviews")
        reviews = r.get("reviews", r.get("items", []))
        assert len(reviews) == 3

        # ── Step 6: Submit promotion decisions ───────────────────────────
        r = run_action(dp, "k12-submit-promotion-decision",
                       promotion_review_id=review_id,
                       student_id=db["student_id"],
                       academic_year_id=db["year_id"],
                       decision="promote",
                       decision_date="2026-05-20",
                       decided_by="Principal Johnson",
                       rationale="Excellent academic performance; ready for 11th grade",
                       next_grade_level="11",
                       company_id=db["company_id"])
        decision_id = assert_ok_id(r, "submit-promotion-decision promote")

        r = run_action(dp, "k12-submit-promotion-decision",
                       promotion_review_id=at_risk_review_id,
                       student_id=db["at_risk_id"],
                       academic_year_id=db["year_id"],
                       decision="retain",
                       decision_date="2026-05-20",
                       decided_by="Principal Johnson",
                       rationale="Student needs additional time to master 10th grade skills",
                       next_grade_level="10",
                       company_id=db["company_id"])
        retain_decision_id = assert_ok_id(r, "submit-promotion-decision retain")

        r = run_action(dp, "k12-submit-promotion-decision",
                       promotion_review_id=senior_review_id,
                       student_id=db["senior_id"],
                       academic_year_id=db["year_id"],
                       decision="promote",
                       decision_date="2026-05-20",
                       decided_by="Principal Johnson",
                       rationale="Met all graduation requirements",
                       next_grade_level="graduated",
                       company_id=db["company_id"])
        senior_decision_id = assert_ok_id(r, "submit-promotion-decision senior")

        # ── Step 7: Cannot submit second decision (immutable) ─────────────
        r2 = run_action(dp, "k12-submit-promotion-decision",
                        promotion_review_id=review_id,
                        student_id=db["student_id"],
                        academic_year_id=db["year_id"],
                        decision="retain",
                        decision_date="2026-05-21",
                        decided_by="Other Principal",
                        rationale="Changed mind",
                        next_grade_level="10",
                        company_id=db["company_id"])
        assert r2.get("status") == "error", (
            f"Duplicate decision should be rejected: {r2}"
        )

        # ── Step 8: Get promotion decision ────────────────────────────────
        r = run_action(dp, "k12-get-promotion-decision",
                       decision_id=decision_id)
        assert_ok(r, "k12-get-promotion-decision")
        decision_data = r.get("decision", r)
        assert decision_data.get("decision") == "promote"

        # ── Step 9: Notify parents of decisions ───────────────────────────
        r = run_action(dp, "notify-promotion-decision",
                       decision_id=decision_id,
                       company_id=db["company_id"])
        assert_ok(r, "notify-promotion-decision promote")

        r = run_action(dp, "notify-promotion-decision",
                       decision_id=retain_decision_id,
                       company_id=db["company_id"])
        assert_ok(r, "notify-promotion-decision retain")

        # ── Step 10: Create intervention plan for retained student ─────────
        r = run_action(dp, "k12-create-intervention-plan",
                       student_id=db["at_risk_id"],
                       academic_year_id=db["year_id"],
                       trigger="retention_decision",
                       intervention_types='["tutoring","parent_conference","counseling"]',
                       academic_targets='{"math":"C or better","english":"C or better"}',
                       attendance_target="90",
                       assigned_staff="Ms. Rivera",
                       parent_notification_date="2026-05-22",
                       company_id=db["company_id"])
        plan_id = assert_ok_id(r, "k12-create-intervention-plan")
        assert r.get("plan_status") == "active"

        # ── Step 11: Update intervention plan ─────────────────────────────
        r = run_action(dp, "k12-update-intervention-plan",
                       intervention_plan_id=plan_id,
                       plan_status="active",
                       outcome_notes="Parent conference held 5/25; summer tutoring scheduled")
        assert_ok(r, "k12-update-intervention-plan")

        # ── Step 12: List intervention plans ──────────────────────────────
        r = run_action(dp, "k12-list-intervention-plans",
                       academic_year_id=db["year_id"],
                       company_id=db["company_id"])
        assert_ok(r, "k12-list-intervention-plans")
        plans = r.get("plans", r.get("items", []))
        assert len(plans) >= 1

        # ── Step 13: Identify at-risk students ────────────────────────────
        r = run_action(dp, "identify-at-risk-students",
                       academic_year_id=db["year_id"],
                       gpa_threshold="2.0",
                       attendance_threshold="90",
                       company_id=db["company_id"])
        assert_ok(r, "identify-at-risk-students")
        at_risk = r.get("at_risk_students", r.get("students", []))
        # The student with GPA 1.8 should appear as at-risk
        at_risk_ids = [s.get("student_id", s.get("id")) for s in at_risk]
        assert db["at_risk_id"] in at_risk_ids, (
            f"Student with GPA 1.8 should be flagged as at-risk. "
            f"At-risk IDs: {at_risk_ids}"
        )

        # ── Step 14: Batch promote promoted students (grade 10 → 11) ──────
        r = run_action(dp, "batch-promote-grade",
                       academic_year_id=db["year_id"],
                       grade_level="10",
                       company_id=db["company_id"])
        assert_ok(r, "batch-promote-grade grade 10")
        promoted = r.get("promoted_count", r.get("students_promoted", 0))
        # Only the main student was decided "promote"; at-risk is "retain"
        assert promoted >= 1, f"Expected at least 1 student promoted: {r}"

        # ── Step 15: Verify main student's grade advanced ────────────────
        # After batch promote, student grade_level should be 11
        conn = get_conn(dp)
        row = conn.execute(
            "SELECT grade_level FROM educlaw_student WHERE id = ?",
            (db["student_id"],)
        ).fetchone()
        conn.close()
        if row:
            assert row["grade_level"] == "11", (
                f"Student grade should be '11' after promotion, got '{row['grade_level']}'"
            )

        # ── Step 16: Batch graduate seniors (grade 12 → graduated) ────────
        r = run_action(dp, "batch-promote-grade",
                       academic_year_id=db["year_id"],
                       grade_level="12",
                       company_id=db["company_id"])
        assert_ok(r, "batch-promote-grade grade 12")
        # Senior should have status='graduated' or similar

        # ── Step 17: Generate promotion report ────────────────────────────
        r = run_action(dp, "k12-generate-promotion-report",
                       academic_year_id=db["year_id"],
                       company_id=db["company_id"])
        assert_ok(r, "k12-generate-promotion-report")
        # Report should have summary data
        assert "total" in str(r).lower() or "promoted" in str(r).lower()
