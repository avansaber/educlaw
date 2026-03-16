"""L1 pytest tests for EduClaw K-12 — 76 actions across 4 domains.

Tests: discipline (~12), health_records (~12), special_education (~10),
       grade_promotion (~8) = ~42 tests.
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
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term

DISC_ACTIONS = _load("discipline", _SCRIPTS_DIR).ACTIONS
HEALTH_ACTIONS = _load("health_records", _SCRIPTS_DIR).ACTIONS
SPED_ACTIONS = _load("special_education", _SCRIPTS_DIR).ACTIONS
PROMO_ACTIONS = _load("grade_promotion", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yield conn, cid
    conn.close()


@pytest.fixture
def full_setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    sid = seed_student(conn, cid)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "year_id": yid, "term_id": tid,
    }
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# DISCIPLINE domain
# ══════════════════════════════════════════════════════════════════════════════

class TestDisciplineIncident:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=s["year_id"],
            academic_term_id=s["term_id"],
            incident_date="2025-09-15", incident_time="10:30",
            location="hallway", location_detail="B-wing",
            incident_type="fighting", severity="major",
            description="Physical altercation between students",
            is_reported_to_law_enforcement=0, is_mandatory_report=0,
            mandatory_report_date=None, mandatory_report_agency=None,
            is_title_ix=0, user_id="test-admin",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-list-discipline-incidents"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=None,
            incident_type=None, severity=None, incident_status=None,
            date_from=None, date_to=None, search=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=s["year_id"],
            academic_term_id=None,
            incident_date="2025-09-15", incident_time="10:30",
            location="classroom", location_detail=None,
            incident_type="classroom_disruption", severity="minor",
            description="Classroom disruption",
            is_reported_to_law_enforcement=0, is_mandatory_report=0,
            mandatory_report_date=None, mandatory_report_agency=None,
            is_title_ix=0, user_id="test-admin",
        ))
        assert is_ok(r)
        r2 = call_action(DISC_ACTIONS["k12-get-discipline-incident"], s["conn"], ns(
            incident_id=r["id"], company_id=s["company_id"],
            user_id="test-admin",
        ))
        assert is_ok(r2)

    def test_missing_date(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=s["year_id"],
            academic_term_id=None,
            incident_date=None, incident_time=None,
            location="gym", location_detail=None,
            incident_type="fighting", severity="major",
            description=None,
            is_reported_to_law_enforcement=0, is_mandatory_report=0,
            mandatory_report_date=None, mandatory_report_agency=None,
            is_title_ix=0, user_id=None,
        ))
        assert is_error(r)


class TestDisciplineStudent:
    def test_add(self, full_setup):
        s = full_setup
        incident = call_action(DISC_ACTIONS["k12-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=s["year_id"],
            academic_term_id=None,
            incident_date="2025-09-15", incident_time="10:30",
            location="hallway", location_detail=None,
            incident_type="fighting", severity="major",
            description="Test incident",
            is_reported_to_law_enforcement=0, is_mandatory_report=0,
            mandatory_report_date=None, mandatory_report_agency=None,
            is_title_ix=0, user_id=None,
        ))
        assert is_ok(incident)
        r = call_action(DISC_ACTIONS["k12-add-discipline-student"], s["conn"], ns(
            incident_id=incident["id"], student_id=s["student_id"],
            company_id=s["company_id"],
            role="offender", is_idea_eligible=0,
            description=None, notes=None, user_id=None,
        ))
        assert is_ok(r)


class TestDisciplineHistory:
    def test_get(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-get-discipline-history"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            user_id="test-admin", limit=50, offset=0,
        ))
        assert is_ok(r)


class TestCumulativeSuspension:
    def test_get(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-get-cumulative-suspension-days"], s["conn"], ns(
            student_id=s["student_id"], academic_year_id=s["year_id"],
            company_id=s["company_id"],
        ))
        assert is_ok(r)


class TestDisciplineReport:
    def test_generate(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["k12-generate-discipline-report"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=s["year_id"],
            date_from=None, date_to=None, limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH RECORDS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthProfile:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(HEALTH_ACTIONS["k12-add-health-profile"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            allergies='["peanuts"]', chronic_conditions='[]',
            physician_name="Dr. Smith", physician_phone="555-0123",
            physician_address=None, health_insurance_carrier="BlueCross",
            health_insurance_id="BC123", blood_type="A+",
            height_cm=None, weight_kg=None,
            vision_screening_date=None, hearing_screening_date=None,
            dental_screening_date=None, activity_restriction=None,
            activity_restriction_notes=None, is_provisional_immunization=0,
            provisional_enrollment_end_date=None, is_mckinney_vento=0,
            emergency_instructions=None, user_id="school-nurse",
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        # Create profile first
        call_action(HEALTH_ACTIONS["k12-add-health-profile"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            allergies='[]', chronic_conditions='[]',
            physician_name="Dr. Jones", physician_phone="555-0456",
            physician_address=None, health_insurance_carrier=None,
            health_insurance_id=None, blood_type=None,
            height_cm=None, weight_kg=None,
            vision_screening_date=None, hearing_screening_date=None,
            dental_screening_date=None, activity_restriction=None,
            activity_restriction_notes=None, is_provisional_immunization=0,
            provisional_enrollment_end_date=None, is_mckinney_vento=0,
            emergency_instructions=None, user_id="school-nurse",
        ))
        r = call_action(HEALTH_ACTIONS["k12-get-health-profile"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            user_id="school-nurse",
        ))
        assert is_ok(r)


class TestOfficeVisit:
    def test_add(self, full_setup):
        s = full_setup
        # Create health profile first
        call_action(HEALTH_ACTIONS["k12-add-health-profile"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            allergies='[]', chronic_conditions='[]',
            physician_name="Dr. Smith", physician_phone="555-0000",
            physician_address=None, health_insurance_carrier=None,
            health_insurance_id=None, blood_type=None,
            height_cm=None, weight_kg=None,
            vision_screening_date=None, hearing_screening_date=None,
            dental_screening_date=None, activity_restriction=None,
            activity_restriction_notes=None, is_provisional_immunization=0,
            provisional_enrollment_end_date=None, is_mckinney_vento=0,
            emergency_instructions=None, user_id="nurse",
        ))
        r = call_action(HEALTH_ACTIONS["k12-add-office-visit"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            visit_date="2025-09-15", visit_time="10:00",
            chief_complaint="headache", complaint_detail="student complains of headache",
            temperature=None, pulse=None,
            assessment="mild headache", treatment_provided="rest and water",
            disposition="returned_to_class",
            parent_contacted=0, parent_contact_time=None,
            parent_response=None, is_emergency=0, user_id="nurse",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(HEALTH_ACTIONS["k12-list-office-visits"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            date_from=None, date_to=None, disposition=None,
            limit=50, offset=0, user_id="nurse",
        ))
        assert is_ok(r)


class TestImmunization:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(HEALTH_ACTIONS["k12-add-immunization"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            vaccine_name="DTaP", cvx_code="20",
            dose_number=1, administration_date="2015-06-01",
            lot_number="LOT123", manufacturer="Sanofi",
            provider_name="City Clinic", provider_type="clinic",
            source="manual", iis_record_id=None,
            corrects_record_id=None, user_id="nurse",
        ))
        assert is_ok(r)

    def test_get_record(self, full_setup):
        s = full_setup
        r = call_action(HEALTH_ACTIONS["k12-get-immunization-record"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            user_id="nurse",
        ))
        assert is_ok(r)

    def test_compliance(self, full_setup):
        s = full_setup
        r = call_action(HEALTH_ACTIONS["k12-get-immunization-compliance"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            user_id="nurse",
        ))
        assert is_ok(r)


class TestHealthAlerts:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(HEALTH_ACTIONS["k12-list-health-alerts"], s["conn"], ns(
            company_id=s["company_id"], days_ahead=30,
            limit=50, offset=0, user_id="nurse",
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# SPECIAL EDUCATION domain
# ══════════════════════════════════════════════════════════════════════════════

class TestSpedReferral:
    def test_create(self, full_setup):
        s = full_setup
        r = call_action(SPED_ACTIONS["k12-create-sped-referral"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            referral_date="2025-09-15", referral_source="teacher",
            referral_reason="Academic difficulties",
            areas_of_concern='["reading", "math"]',
            prior_interventions='["tutoring"]',
            user_id="teacher1",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(SPED_ACTIONS["k12-list-sped-referrals"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            referral_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        ref = call_action(SPED_ACTIONS["k12-create-sped-referral"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            referral_date="2025-09-15", referral_source="parent",
            referral_reason="Behavioral concerns",
            areas_of_concern='["behavior"]',
            prior_interventions='[]',
            user_id="counselor",
        ))
        assert is_ok(ref)
        r = call_action(SPED_ACTIONS["k12-get-sped-referral"], s["conn"], ns(
            referral_id=ref["id"], company_id=s["company_id"],
            user_id="counselor",
        ))
        assert is_ok(r)


class TestSpedEligibility:
    def test_list_evaluations(self, full_setup):
        s = full_setup
        ref = call_action(SPED_ACTIONS["k12-create-sped-referral"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            referral_date="2025-09-20", referral_source="teacher",
            referral_reason="Academic difficulty",
            areas_of_concern='["reading"]',
            prior_interventions='[]',
            user_id="teacher1",
        ))
        assert is_ok(ref)
        r = call_action(SPED_ACTIONS["k12-list-sped-evaluations"], s["conn"], ns(
            referral_id=ref["id"],
        ))
        assert is_ok(r)


class TestIEP:
    def test_list_deadlines(self, full_setup):
        s = full_setup
        r = call_action(SPED_ACTIONS["k12-list-iep-deadlines"], s["conn"], ns(
            company_id=s["company_id"], days_window=30,
            limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_list_services(self, full_setup):
        s = full_setup
        import uuid
        r = call_action(SPED_ACTIONS["k12-list-iep-services"], s["conn"], ns(
            iep_id=str(uuid.uuid4()),
        ))
        assert is_ok(r)

    def test_list_reevaluation_due(self, full_setup):
        s = full_setup
        r = call_action(SPED_ACTIONS["k12-list-reevaluation-due"], s["conn"], ns(
            company_id=s["company_id"], days_window=90,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# GRADE PROMOTION domain
# ══════════════════════════════════════════════════════════════════════════════

class TestPromotionReview:
    def test_create(self, full_setup):
        s = full_setup
        r = call_action(PROMO_ACTIONS["k12-create-promotion-review"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            academic_year_id=s["year_id"],
            grade_level="5", gpa_ytd="2.5", attendance_rate_ytd="0.92",
            failing_subjects='["math"]', discipline_incident_count=1,
            teacher_recommendation="promote",
            teacher_rationale="Student shows improvement",
            counselor_recommendation=None, counselor_notes=None,
            prior_retention_count=0, interventions_tried='["tutoring"]',
            is_idea_eligible=0, user_id="teacher1",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(PROMO_ACTIONS["k12-list-promotion-reviews"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=None,
            grade_level=None, review_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


class TestAtRiskStudents:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(PROMO_ACTIONS["k12-list-at-risk-students"], s["conn"], ns(
            company_id=s["company_id"], academic_year_id=s["year_id"],
            gpa_threshold="2.0", attendance_threshold="0.90",
            grade_level=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestInterventionPlan:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(PROMO_ACTIONS["k12-list-intervention-plans"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
