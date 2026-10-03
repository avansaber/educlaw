"""L1 pytest tests for EduClaw State Reporting — 98 actions across 6 domains.

Tests: demographics (~12), discipline (~10), ed_fi (~12),
       state_reporting (~8), data_validation (~8), submission_tracking (~7) = ~57 tests.
"""
import importlib.util
import json
import sys
import os
import uuid
from decimal import Decimal, ROUND_HALF_UP

import pytest

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
seed_collection_window = _helpers.seed_collection_window
seed_edfi_config = _helpers.seed_edfi_config
seed_supplement = _helpers.seed_supplement

DEMO_ACTIONS = _load("demographics", _SCRIPTS_DIR).ACTIONS
DISC_ACTIONS = _load("discipline", _SCRIPTS_DIR).ACTIONS
EDFI_ACTIONS = _load("ed_fi", _SCRIPTS_DIR).ACTIONS
SR_ACTIONS = _load("state_reporting", _SCRIPTS_DIR).ACTIONS
DV_ACTIONS = _load("data_validation", _SCRIPTS_DIR).ACTIONS
SUB_ACTIONS = _load("submission_tracking", _SCRIPTS_DIR).ACTIONS


# The helpers module binds the in-tree erpclaw_lib on sys.path (M54), so this
# import resolves to the tree under test, never the deployed lib symlink.
from erpclaw_lib.db import get_connection as lib_get_connection


def _verify_tables(*tables):
    """Snapshot exact table contents through an independent shared-library connection.

    Reads go through ``erpclaw_lib.db.get_connection()`` (which honours the
    ``ERPCLAW_DB_PATH`` the ``db_path`` fixture sets), not the connection the
    action ran on, so the read-back is independent evidence. Catalog
    questions are out of scope here; only plain parameterized SELECTs are
    issued through the shared-library connection.
    """
    conn = lib_get_connection()
    try:
        snap = {}
        for table in tables:
            rows = conn.execute(
                "SELECT * FROM " + table + " ORDER BY id").fetchall()
            snap[table] = [dict(r) for r in rows]
        return snap
    finally:
        conn.close()


def _stored_row(table, pk):
    """Read one stored row back through the shared-library connection."""
    conn = lib_get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM " + table + " WHERE id = ?", (pk,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _pct_str(num, den):
    """Exact percentage string with the same Decimal math production uses."""
    if den == 0:
        return "100"
    return str((Decimal(str(num)) / Decimal(str(den)) * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP))


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
    supp_id = seed_supplement(conn, sid, cid)
    wid = seed_collection_window(conn, cid, yid)
    edfi_id = seed_edfi_config(conn, cid)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "year_id": yid, "supplement_id": supp_id,
        "window_id": wid, "edfi_config_id": edfi_id,
    }
    conn.close()


# ==============================================================================
# DEMOGRAPHICS domain
# ==============================================================================

class TestStudentSupplement:
    def test_add(self, setup):
        conn, cid = setup
        sid = seed_student(conn, cid)
        r = call_action(DEMO_ACTIONS["statereport-add-student-supplement"], conn, ns(
            student_id=sid, company_id=cid,
            ssid="SS123456", ssid_state_code="CA", ssid_status="assigned",
            is_hispanic_latino=0, race_codes='["WHITE","ASIAN"]',
            is_el=0, el_entry_date=None, home_language_code=None,
            native_language_code=None, english_proficiency_level=None,
            english_proficiency_instrument=None, el_exit_date=None,
            is_rfep=None, rfep_date=None,
            is_sped=0, is_504=0, sped_entry_date=None, sped_exit_date=None,
            is_economically_disadvantaged=0, lunch_program_status=None,
            is_migrant=0, is_homeless=0, homeless_primary_nighttime_residence=None,
            is_foster_care=0, is_military_connected=0, military_connection_type=None,
            user_id="admin",
        ))
        assert is_ok(r)
        assert r["race_federal_rollup"] == "TWO_OR_MORE_RACES"

    def test_get(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-get-student-supplement"], s["conn"], ns(
            student_id=s["student_id"], supplement_id=None,
        ))
        assert is_ok(r)

    def test_update(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-update-student-supplement"], s["conn"], ns(
            supplement_id=s["supplement_id"], student_id=None,
            ssid=None, ssid_state_code=None, ssid_status=None,
            is_hispanic_latino=1, race_codes=None,
            is_el=None, el_entry_date=None, home_language_code=None,
            native_language_code=None, english_proficiency_level=None,
            english_proficiency_instrument=None, el_exit_date=None,
            is_rfep=None, rfep_date=None,
            is_sped=None, is_504=None, sped_entry_date=None, sped_exit_date=None,
            is_economically_disadvantaged=None, lunch_program_status=None,
            is_migrant=None, is_homeless=None, homeless_primary_nighttime_residence=None,
            is_foster_care=None, is_military_connected=None, military_connection_type=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-list-student-supplements"], s["conn"], ns(
            company_id=s["company_id"], search=None,
            missing_ssid=None, missing_race=None,
            is_el=None, is_sped=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_assign_ssid(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-assign-ssid"], s["conn"], ns(
            student_id=s["student_id"], ssid="NEW-SSID-999",
            ssid_state_code="CA", user_id="admin",
        ))
        assert is_ok(r)
        assert r["ssid_status"] == "assigned"

    def test_update_race(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-update-student-race"], s["conn"], ns(
            student_id=s["student_id"],
            race_codes='["BLACK","ASIAN"]', is_hispanic_latino=0,
            user_id="admin",
        ))
        assert is_ok(r)
        assert r["race_federal_rollup"] == "TWO_OR_MORE_RACES"

    def test_update_el_status(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-update-el-status"], s["conn"], ns(
            student_id=s["student_id"],
            is_el=1, el_entry_date="2024-09-01",
            home_language_code="spa", native_language_code="spa",
            english_proficiency_level="3",
            english_proficiency_instrument="ELPAC",
            el_exit_date=None, is_rfep=None, rfep_date=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_update_sped_status(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-update-sped-status"], s["conn"], ns(
            student_id=s["student_id"],
            is_sped=1, is_504=0,
            sped_entry_date="2023-01-15", sped_exit_date=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_update_economic_status(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-update-economic-status"], s["conn"], ns(
            student_id=s["student_id"],
            is_economically_disadvantaged=1, lunch_program_status="free",
            user_id="admin",
        ))
        assert is_ok(r)

    def test_missing_student_id(self, setup):
        conn, cid = setup
        r = call_action(DEMO_ACTIONS["statereport-add-student-supplement"], conn, ns(
            student_id=None, company_id=cid,
            ssid=None, ssid_state_code=None, ssid_status=None,
            is_hispanic_latino=None, race_codes=None,
            is_el=None, el_entry_date=None, home_language_code=None,
            native_language_code=None, english_proficiency_level=None,
            english_proficiency_instrument=None, el_exit_date=None,
            is_rfep=None, rfep_date=None,
            is_sped=None, is_504=None, sped_entry_date=None, sped_exit_date=None,
            is_economically_disadvantaged=None, lunch_program_status=None,
            is_migrant=None, is_homeless=None, homeless_primary_nighttime_residence=None,
            is_foster_care=None, is_military_connected=None, military_connection_type=None,
            user_id=None,
        ))
        assert is_error(r)


class TestSpedPlacement:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-add-sped-placement"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            disability_category="SLD", educational_environment="RC_80",
            company_id=s["company_id"],
            secondary_disability=None,
            sped_program_entry_date="2024-09-01", sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date="2024-09-01", iep_review_date="2025-09-01",
            is_transition_plan_required=0, lre_percentage="85",
            is_early_childhood=0, early_childhood_environment=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_update(self, full_setup):
        s = full_setup
        add_r = call_action(DEMO_ACTIONS["statereport-add-sped-placement"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            disability_category="AUT", educational_environment="RC_80",
            company_id=s["company_id"],
            secondary_disability=None,
            sped_program_entry_date=None, sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date=None, iep_review_date=None,
            is_transition_plan_required=None, lre_percentage=None,
            is_early_childhood=None, early_childhood_environment=None,
            user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DEMO_ACTIONS["statereport-update-sped-placement"], s["conn"], ns(
            placement_id=add_r["id"],
            disability_category="SLD", secondary_disability=None,
            educational_environment=None,
            sped_program_entry_date=None, sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date=None, iep_review_date=None,
            is_transition_plan_required=None, lre_percentage=None,
            is_early_childhood=None, early_childhood_environment=None,
            user_id=None,
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        add_r = call_action(DEMO_ACTIONS["statereport-add-sped-placement"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            disability_category="AUT", educational_environment="RC_80",
            company_id=s["company_id"],
            secondary_disability=None,
            sped_program_entry_date=None, sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date=None, iep_review_date=None,
            is_transition_plan_required=None, lre_percentage=None,
            is_early_childhood=None, early_childhood_environment=None,
            user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DEMO_ACTIONS["statereport-get-sped-placement"], s["conn"], ns(
            placement_id=add_r["id"], student_id=None, school_year=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-list-sped-placements"], s["conn"], ns(
            company_id=s["company_id"], school_year=None,
            disability_category=None, educational_environment=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


class TestSpedService:
    def test_add_and_list(self, full_setup):
        s = full_setup
        pl = call_action(DEMO_ACTIONS["statereport-add-sped-placement"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            disability_category="SLI", educational_environment="RC_80",
            company_id=s["company_id"],
            secondary_disability=None,
            sped_program_entry_date=None, sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date=None, iep_review_date=None,
            is_transition_plan_required=None, lre_percentage=None,
            is_early_childhood=None, early_childhood_environment=None,
            user_id=None,
        ))
        assert is_ok(pl)
        r = call_action(DEMO_ACTIONS["statereport-add-sped-service"], s["conn"], ns(
            sped_placement_id=pl["id"], student_id=None,
            service_type="speech_language", provider_type="school_employed",
            minutes_per_week=60,
            start_date="2024-09-01", end_date="2025-06-30",
            company_id=s["company_id"], user_id="admin",
        ))
        assert is_ok(r)
        svc_id = r["id"]

        # List
        lr = call_action(DEMO_ACTIONS["statereport-list-sped-services"], s["conn"], ns(
            sped_placement_id=pl["id"], student_id=None,
            company_id=None, service_type=None,
        ))
        assert is_ok(lr)
        assert lr["count"] >= 1

        # Delete
        dr = call_action(DEMO_ACTIONS["statereport-delete-sped-service"], s["conn"], ns(
            service_id=svc_id, user_id="admin",
        ))
        assert is_ok(dr)


class TestElProgram:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-add-el-program"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            program_type="sheltered_english", entry_date="2024-09-01",
            company_id=s["company_id"],
            exit_date=None, exit_reason=None,
            english_proficiency_assessed_date="2024-08-15",
            proficiency_level="3", proficiency_instrument="ELPAC",
            is_parent_waived=0, waiver_date=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_update(self, full_setup):
        s = full_setup
        add_r = call_action(DEMO_ACTIONS["statereport-add-el-program"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            program_type="pull_out", entry_date="2024-09-01",
            company_id=s["company_id"],
            exit_date=None, exit_reason=None,
            english_proficiency_assessed_date=None,
            proficiency_level=None, proficiency_instrument=None,
            is_parent_waived=None, waiver_date=None,
            user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DEMO_ACTIONS["statereport-update-el-program"], s["conn"], ns(
            el_program_id=add_r["id"],
            program_type="push_in", entry_date=None,
            exit_date=None, exit_reason=None,
            english_proficiency_assessed_date=None,
            proficiency_level=None, proficiency_instrument=None,
            is_parent_waived=None, waiver_date=None,
            user_id=None,
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        add_r = call_action(DEMO_ACTIONS["statereport-add-el-program"], s["conn"], ns(
            student_id=s["student_id"], school_year=2025,
            program_type="dual_language", entry_date="2024-09-01",
            company_id=s["company_id"],
            exit_date=None, exit_reason=None,
            english_proficiency_assessed_date=None,
            proficiency_level=None, proficiency_instrument=None,
            is_parent_waived=None, waiver_date=None,
            user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DEMO_ACTIONS["statereport-get-el-program"], s["conn"], ns(
            el_program_id=add_r["id"], student_id=None, school_year=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(DEMO_ACTIONS["statereport-list-el-programs"], s["conn"], ns(
            company_id=s["company_id"], school_year=None,
            program_type=None, active_only=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ==============================================================================
# DISCIPLINE domain
# ==============================================================================

class TestDisciplineIncident:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="bullying",
            incident_time="10:30", incident_description="Hallway bullying",
            campus_location="hallway", reported_by="teacher1",
            user_id="admin",
        ))
        assert is_ok(r)
        assert "naming_series" in r

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(DISC_ACTIONS["statereport-list-discipline-incidents"], s["conn"], ns(
            company_id=s["company_id"], school_year=None,
            incident_type=None, date_from=None, date_to=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_update(self, full_setup):
        s = full_setup
        add_r = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="vandalism",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DISC_ACTIONS["statereport-update-discipline-incident"], s["conn"], ns(
            incident_id=add_r["id"],
            incident_type=None, incident_description="Updated desc",
            campus_location=None, incident_date=None, incident_time=None,
            reported_by=None, user_id=None,
        ))
        assert is_ok(r)


class TestDisciplineStudent:
    def test_add_and_list(self, full_setup):
        s = full_setup
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="physical_assault_student",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(inc)
        r = call_action(DISC_ACTIONS["statereport-add-discipline-student"], s["conn"], ns(
            incident_id=inc["id"], student_id=s["student_id"],
            role="offender", company_id=s["company_id"],
            is_idea_student=None, is_504_student=None,
            user_id="admin",
        ))
        assert is_ok(r)

        lr = call_action(DISC_ACTIONS["statereport-list-discipline-students"], s["conn"], ns(
            incident_id=inc["id"],
        ))
        assert is_ok(lr)
        assert lr["count"] >= 1


class TestDisciplineAction:
    def test_add(self, full_setup):
        s = full_setup
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="drug_alcohol",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(inc)
        ds = call_action(DISC_ACTIONS["statereport-add-discipline-student"], s["conn"], ns(
            incident_id=inc["id"], student_id=s["student_id"],
            role="offender", company_id=s["company_id"],
            is_idea_student=None, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(ds)
        r = call_action(DISC_ACTIONS["statereport-add-discipline-action"], s["conn"], ns(
            discipline_student_id=ds["id"], action_type="oss_1_10",
            company_id=s["company_id"],
            days_removed=5, start_date="2025-10-16", end_date="2025-10-21",
            alternative_services_provided=1,
            alternative_services_description="Homework packets",
            mdr_required=None, mdr_outcome=None, mdr_date=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_record_mdr(self, full_setup):
        s = full_setup
        # Create incident -> student -> action with mdr
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="weapons_other",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(inc)
        # Mark student as IDEA
        ds = call_action(DISC_ACTIONS["statereport-add-discipline-student"], s["conn"], ns(
            incident_id=inc["id"], student_id=s["student_id"],
            role="offender", company_id=s["company_id"],
            is_idea_student=1, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(ds)
        act = call_action(DISC_ACTIONS["statereport-add-discipline-action"], s["conn"], ns(
            discipline_student_id=ds["id"], action_type="oss_gt10",
            company_id=s["company_id"],
            days_removed=15, start_date=None, end_date=None,
            alternative_services_provided=None,
            alternative_services_description=None,
            mdr_required=1, mdr_outcome=None, mdr_date=None,
            user_id=None,
        ))
        assert is_ok(act)
        assert act["mdr_required"] == 1

        r = call_action(DISC_ACTIONS["statereport-record-mdr-outcome"], s["conn"], ns(
            action_id=act["id"], mdr_outcome="not_manifestation",
            mdr_date="2025-10-25", user_id="admin",
        ))
        assert is_ok(r)

    def test_list_actions(self, full_setup):
        s = full_setup
        # Ledger: this is a reporting read; it never touches gl_* tables, so
        # no balanced-legs assertion can hold. The depth signal is row
        # equality plus proof the read writes nothing.
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="drug_alcohol",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(inc)
        ds = call_action(DISC_ACTIONS["statereport-add-discipline-student"], s["conn"], ns(
            incident_id=inc["id"], student_id=s["student_id"],
            role="offender", company_id=s["company_id"],
            is_idea_student=None, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(ds)
        act = call_action(DISC_ACTIONS["statereport-add-discipline-action"], s["conn"], ns(
            discipline_student_id=ds["id"], action_type="oss_1_10",
            company_id=s["company_id"],
            days_removed=5, start_date="2025-10-16", end_date="2025-10-21",
            alternative_services_provided=1,
            alternative_services_description="Homework packets",
            mdr_required=None, mdr_outcome=None, mdr_date=None,
            user_id="admin",
        ))
        assert is_ok(act)
        stored = _stored_row("educlaw_k12_discipline_action", act["id"])
        assert stored is not None
        assert stored["action_type"] == "oss_1_10"
        assert stored["days_removed"] == 5
        assert stored["start_date"] == "2025-10-16"
        assert stored["end_date"] == "2025-10-21"
        assert stored["alternative_services_provided"] == 1
        assert stored["alternative_services_description"] == "Homework packets"
        assert stored["mdr_required"] == 0
        assert stored["student_id"] == s["student_id"]
        assert stored["incident_id"] == inc["id"]
        assert stored["discipline_student_id"] == ds["id"]
        assert stored["company_id"] == s["company_id"]
        assert stored["created_by"] == "admin"

        before = _verify_tables("educlaw_k12_discipline_action", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-list-discipline-actions"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            action_type=None, mdr_required=None,
            incident_id=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 1
        assert len(r["actions"]) == 1
        entry = r["actions"][0]
        for field in ("id", "discipline_student_id", "incident_id", "student_id",
                      "action_type", "start_date", "end_date", "days_removed",
                      "alternative_services_provided",
                      "alternative_services_description", "mdr_required",
                      "mdr_outcome", "mdr_date", "company_id", "created_by"):
            assert entry[field] == stored[field], field

        # Filters are applied, not decorative: a non-matching type finds
        # nothing, while the true student/incident/mdr filters find the row.
        assert call_action(DISC_ACTIONS["statereport-list-discipline-actions"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            action_type="iss", mdr_required=None,
            incident_id=None, limit=50, offset=0,
        ))["count"] == 0
        assert call_action(DISC_ACTIONS["statereport-list-discipline-actions"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            action_type="oss_1_10", mdr_required=0,
            incident_id=inc["id"], limit=50, offset=0,
        ))["count"] == 1

        # A pure read: the action wrote nothing, not even an audit row.
        assert _verify_tables("educlaw_k12_discipline_action", "audit_log") == before

    def test_list_actions_refusal_without_filters_is_empty_not_error(self, full_setup):
        # This action declares no required input, so there is no refusal path
        # to exercise. The negative control is exact: filtering by a company
        # that owns nothing returns an empty list, truthfully, and the
        # database is byte-identical afterwards.
        s = full_setup
        before = _verify_tables("educlaw_k12_discipline_action", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-list-discipline-actions"], s["conn"], ns(
            company_id="00000000-0000-0000-0000-000000000000", student_id=None,
            action_type=None, mdr_required=None,
            incident_id=None, limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 0
        assert r["actions"] == []
        assert _verify_tables("educlaw_k12_discipline_action", "audit_log") == before

    def test_discipline_summary(self, full_setup):
        s = full_setup
        # Ledger: aggregate reporting read; no gl_* writes, so no
        # balanced-legs assertion can hold. Depth signal is exact counts.
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="drug_alcohol",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(inc)
        ds = call_action(DISC_ACTIONS["statereport-add-discipline-student"], s["conn"], ns(
            incident_id=inc["id"], student_id=s["student_id"],
            role="offender", company_id=s["company_id"],
            is_idea_student=None, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(ds)
        act = call_action(DISC_ACTIONS["statereport-add-discipline-action"], s["conn"], ns(
            discipline_student_id=ds["id"], action_type="oss_1_10",
            company_id=s["company_id"],
            days_removed=5, start_date="2025-10-16", end_date="2025-10-21",
            alternative_services_provided=None,
            alternative_services_description=None,
            mdr_required=None, mdr_outcome=None, mdr_date=None,
            user_id=None,
        ))
        assert is_ok(act)

        before = _verify_tables(
            "educlaw_k12_discipline_incident", "educlaw_k12_discipline_student",
            "educlaw_k12_discipline_action", "educlaw_student",
            "sr_student_supplement", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-get-discipline-summary"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
        ))
        assert is_ok(r)
        assert r["school_year"] == 2025
        assert r["company_id"] == s["company_id"]
        assert r["total_incidents"] == 1
        assert r["total_students_involved"] == 1
        assert r["mdr_pending_count"] == 0
        assert len(r["summary"]) == 1
        cell = r["summary"][0]
        assert cell == {
            "action_type": "oss_1_10",
            "race_federal_rollup": "WHITE",
            "gender": "",
            "is_idea_student": 0,
            "count": 1,
            "total_days_removed": 5,
            "suppressed": True,
        }
        assert _verify_tables(
            "educlaw_k12_discipline_incident", "educlaw_k12_discipline_student",
            "educlaw_k12_discipline_action", "educlaw_student",
            "sr_student_supplement", "audit_log") == before

    def test_discipline_summary_refusal(self, full_setup):
        s = full_setup
        before = _verify_tables(
            "educlaw_k12_discipline_incident", "educlaw_k12_discipline_student",
            "educlaw_k12_discipline_action", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-get-discipline-summary"], s["conn"], ns(
            company_id=s["company_id"], school_year=None,
        ))
        assert is_error(r)
        assert r["message"] == "--school-year is required"
        assert _verify_tables(
            "educlaw_k12_discipline_incident", "educlaw_k12_discipline_student",
            "educlaw_k12_discipline_action", "audit_log") == before


class TestGetDisciplineAction:
    # No prior test existed for statereport-get-discipline-action, so this is
    # behavioural from birth: exact stored-row equality plus a no-write proof.

    def _seed_action(self, s):
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            incident_date="2025-10-15", incident_type="drug_alcohol",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None,
            user_id=None,
        ))
        assert is_ok(inc)
        ds = call_action(DISC_ACTIONS["statereport-add-discipline-student"], s["conn"], ns(
            incident_id=inc["id"], student_id=s["student_id"],
            role="offender", company_id=s["company_id"],
            is_idea_student=None, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(ds)
        act = call_action(DISC_ACTIONS["statereport-add-discipline-action"], s["conn"], ns(
            discipline_student_id=ds["id"], action_type="oss_1_10",
            company_id=s["company_id"],
            days_removed=5, start_date="2025-10-16", end_date="2025-10-21",
            alternative_services_provided=1,
            alternative_services_description="Homework packets",
            mdr_required=None, mdr_outcome=None, mdr_date=None,
            user_id="admin",
        ))
        assert is_ok(act)
        return inc, ds, act

    def test_get(self, full_setup):
        s = full_setup
        # Ledger: single-row reporting read; no gl_* writes, so no
        # balanced-legs assertion can hold.
        inc, ds, act = self._seed_action(s)
        stored = _stored_row("educlaw_k12_discipline_action", act["id"])
        assert stored is not None
        before = _verify_tables("educlaw_k12_discipline_action", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-get-discipline-action"], s["conn"], ns(
            action_id=act["id"],
        ))
        assert is_ok(r)
        for field in ("id", "discipline_student_id", "incident_id", "student_id",
                      "action_type", "start_date", "end_date", "days_removed",
                      "alternative_services_provided",
                      "alternative_services_description", "mdr_required",
                      "mdr_outcome", "mdr_date", "company_id", "created_by"):
            assert r[field] == stored[field], field
        assert r["action_type"] == "oss_1_10"
        assert r["days_removed"] == 5
        assert _verify_tables("educlaw_k12_discipline_action", "audit_log") == before

    def test_get_refusal_missing_id(self, full_setup):
        s = full_setup
        before = _verify_tables("educlaw_k12_discipline_action", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-get-discipline-action"], s["conn"], ns(
            action_id=None,
        ))
        assert is_error(r)
        assert r["message"] == "--action-id is required"
        assert _verify_tables("educlaw_k12_discipline_action", "audit_log") == before

    def test_get_refusal_unknown_id(self, full_setup):
        s = full_setup
        missing = "00000000-0000-0000-0000-000000000000"
        before = _verify_tables("educlaw_k12_discipline_action", "audit_log")
        r = call_action(DISC_ACTIONS["statereport-get-discipline-action"], s["conn"], ns(
            action_id=missing,
        ))
        assert is_error(r)
        assert r["message"] == f"Discipline action {missing} not found"
        assert _verify_tables("educlaw_k12_discipline_action", "audit_log") == before


# ==============================================================================
# ED-FI domain
# ==============================================================================

class TestEdFiConfig:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(EDFI_ACTIONS["statereport-add-edfi-config"], conn, ns(
            company_id=cid, profile_name="CA Ed-Fi Test",
            state_code="CA", school_year=2025,
            ods_base_url="https://edfi.test.edu/api/v7",
            oauth_token_url="https://edfi.test.edu/oauth/token",
            oauth_client_id="client-123",
            oauth_client_secret="secret-456",
            api_version="7", is_active=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-list-edfi-configs"], s["conn"], ns(
            company_id=s["company_id"], state_code=None,
            is_active=None, school_year=None,
        ))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_get(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-get-edfi-config"], s["conn"], ns(
            config_id=s["edfi_config_id"],
        ))
        assert is_ok(r)
        # Secret should NOT be returned
        assert "oauth_client_secret_encrypted" not in r
        assert r["has_client_secret"] is True

    def test_update(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-update-edfi-config"], s["conn"], ns(
            config_id=s["edfi_config_id"],
            profile_name="Updated Profile", state_code=None,
            ods_base_url=None, oauth_token_url=None,
            oauth_client_id=None, oauth_client_secret=None,
            api_version=None, is_active=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_connection_test(self, full_setup):
        s = full_setup
        # Ledger: this action updates a timestamp and an audit row; it never
        # posts to the ledger, so no balanced-legs assertion can hold. The
        # depth signal is the stored row changing from one exact value to
        # another while every other column stays put.
        before = _stored_row("sr_edfi_config", s["edfi_config_id"])
        assert before is not None
        assert before["last_tested_at"] == ""
        audit_before = _verify_tables("audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-edfi-connection-test"], s["conn"], ns(
            config_id=s["edfi_config_id"], user_id="admin",
        ))
        assert is_ok(r)
        assert r["id"] == s["edfi_config_id"]
        assert r["last_tested_at"] != ""
        assert r["last_tested_at"].endswith("Z")
        after = _stored_row("sr_edfi_config", s["edfi_config_id"])
        assert after["last_tested_at"] == r["last_tested_at"]
        assert after["updated_at"] == r["last_tested_at"]
        for field in ("profile_name", "state_code", "school_year",
                      "ods_base_url", "oauth_token_url", "oauth_client_id",
                      "api_version", "is_active", "last_token_at",
                      "company_id", "created_by"):
            assert after[field] == before[field], field
        assert "oauth_client_secret_encrypted" not in r
        audit_after = _verify_tables("audit_log")
        assert len(audit_after["audit_log"]) == len(audit_before["audit_log"]) + 1
        fresh = [row for row in audit_after["audit_log"]
                 if row not in audit_before["audit_log"]]
        assert len(fresh) == 1
        # The audit row names the skill, the action, the table and the record:
        # skill is the module SKILL constant, action is the action name,
        # entity_type is the record's table and entity_id is the record's id.
        assert fresh[0]["skill"] == "statereport-educlaw-statereport"
        assert fresh[0]["action"] == "statereport-get-edfi-connection-test"
        assert fresh[0]["entity_type"] == "sr_edfi_config"
        assert fresh[0]["entity_id"] == s["edfi_config_id"]

    def test_connection_test_refusal_missing_id(self, full_setup):
        s = full_setup
        before = _verify_tables("sr_edfi_config", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-edfi-connection-test"], s["conn"], ns(
            config_id=None, user_id="admin",
        ))
        assert is_error(r)
        assert r["message"] == "--config-id is required"
        assert _stored_row("sr_edfi_config", s["edfi_config_id"])["last_tested_at"] == ""
        assert _verify_tables("sr_edfi_config", "audit_log") == before

    def test_connection_test_refusal_unknown_id(self, full_setup):
        s = full_setup
        missing = "00000000-0000-0000-0000-000000000000"
        before = _verify_tables("sr_edfi_config", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-edfi-connection-test"], s["conn"], ns(
            config_id=missing, user_id="admin",
        ))
        assert is_error(r)
        assert r["message"] == f"Ed-Fi config {missing} not found"
        assert _verify_tables("sr_edfi_config", "audit_log") == before

    def test_missing_profile_name(self, setup):
        conn, cid = setup
        r = call_action(EDFI_ACTIONS["statereport-add-edfi-config"], conn, ns(
            company_id=cid, profile_name=None,
            state_code="CA", school_year=2025,
            ods_base_url="https://edfi.test.edu/api/v7",
            oauth_token_url=None,
            oauth_client_id="client-123",
            oauth_client_secret=None,
            api_version=None, is_active=None,
            user_id=None,
        ))
        assert is_error(r)


class TestOrgMapping:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(EDFI_ACTIONS["statereport-add-org-mapping"], conn, ns(
            company_id=cid, state_code="CA",
            nces_lea_id="0600001", nces_school_id="060000100001",
            state_lea_id="CA-001", state_school_id="CA-001-001",
            edfi_lea_id=None, edfi_school_id=None,
            crdc_school_id=None,
            is_title_i_school=1, title_i_status="schoolwide",
            user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(EDFI_ACTIONS["statereport-list-org-mappings"], conn, ns(
            company_id=cid, state_code=None,
        ))
        assert is_ok(r)

    def test_get_by_id(self, setup):
        # No prior test existed for statereport-get-org-mapping, so this is
        # behavioural from birth: exact stored-row equality plus a no-write
        # proof. Ledger: reporting read; no gl_* writes, so no
        # balanced-legs assertion can hold.
        conn, cid = setup
        added = call_action(EDFI_ACTIONS["statereport-add-org-mapping"], conn, ns(
            company_id=cid, state_code="CA",
            nces_lea_id="0600001", nces_school_id="060000100001",
            state_lea_id="CA-001", state_school_id="CA-001-001",
            edfi_lea_id=None, edfi_school_id=None,
            crdc_school_id=None,
            is_title_i_school=1, title_i_status="schoolwide",
            user_id="admin",
        ))
        assert is_ok(added)
        stored = _stored_row("sr_org_mapping", added["id"])
        assert stored is not None
        assert stored["nces_lea_id"] == "0600001"
        assert stored["nces_school_id"] == "060000100001"
        assert stored["state_code"] == "CA"
        assert stored["state_lea_id"] == "CA-001"
        assert stored["state_school_id"] == "CA-001-001"
        assert stored["is_title_i_school"] == 1
        assert stored["title_i_status"] == "schoolwide"
        assert stored["company_id"] == cid
        assert stored["created_by"] == "admin"
        before = _verify_tables("sr_org_mapping", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-org-mapping"], conn, ns(
            mapping_id=added["id"], company_id=None, state_code=None,
        ))
        assert is_ok(r)
        for field in ("id", "company_id", "nces_lea_id", "nces_school_id",
                      "state_code", "state_lea_id", "state_school_id",
                      "edfi_lea_id", "edfi_school_id", "crdc_school_id",
                      "is_title_i_school", "title_i_status", "created_by"):
            assert r[field] == stored[field], field
        assert _verify_tables("sr_org_mapping", "audit_log") == before

    def test_get_by_company_and_state(self, setup):
        conn, cid = setup
        added = call_action(EDFI_ACTIONS["statereport-add-org-mapping"], conn, ns(
            company_id=cid, state_code="CA",
            nces_lea_id="0600001", nces_school_id="060000100001",
            state_lea_id="CA-001", state_school_id="CA-001-001",
            edfi_lea_id=None, edfi_school_id=None,
            crdc_school_id=None,
            is_title_i_school=1, title_i_status="schoolwide",
            user_id="admin",
        ))
        assert is_ok(added)
        before = _verify_tables("sr_org_mapping", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-org-mapping"], conn, ns(
            mapping_id=None, company_id=cid, state_code="CA",
        ))
        assert is_ok(r)
        assert r["id"] == added["id"]
        assert r["nces_lea_id"] == "0600001"
        assert _verify_tables("sr_org_mapping", "audit_log") == before

    def test_get_refusal_without_keys(self, setup):
        conn, cid = setup
        before = _verify_tables("sr_org_mapping", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-org-mapping"], conn, ns(
            mapping_id=None, company_id=None, state_code=None,
        ))
        assert is_error(r)
        assert r["message"] == "--mapping-id or --company-id + --state-code required"
        assert _verify_tables("sr_org_mapping", "audit_log") == before

    def test_get_refusal_unknown_id(self, setup):
        conn, cid = setup
        before = _verify_tables("sr_org_mapping", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-org-mapping"], conn, ns(
            mapping_id="00000000-0000-0000-0000-000000000000",
            company_id=None, state_code=None,
        ))
        assert is_error(r)
        assert r["message"] == "Org mapping not found"
        assert _verify_tables("sr_org_mapping", "audit_log") == before


class TestDescriptorMapping:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-add-descriptor-mapping"], s["conn"], ns(
            config_id=s["edfi_config_id"], company_id=s["company_id"],
            descriptor_type="grade_level", internal_code="K",
            edfi_descriptor_uri="uri://ed-fi.org/GradeLevelDescriptor#Kindergarten",
            description="Kindergarten",
            user_id="admin",
        ))
        assert is_ok(r)

    def test_bulk_import(self, full_setup):
        s = full_setup
        mappings = [
            {"descriptor_type": "race", "internal_code": "W",
             "edfi_descriptor_uri": "uri://ed-fi.org/RaceDescriptor#White"},
            {"descriptor_type": "race", "internal_code": "B",
             "edfi_descriptor_uri": "uri://ed-fi.org/RaceDescriptor#Black"},
        ]
        import json
        r = call_action(EDFI_ACTIONS["statereport-import-descriptor-mappings"], s["conn"], ns(
            config_id=s["edfi_config_id"], company_id=s["company_id"],
            mappings=json.dumps(mappings), user_id="admin",
        ))
        assert is_ok(r)
        assert r["inserted"] == 2

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-list-descriptor-mappings"], s["conn"], ns(
            config_id=s["edfi_config_id"],
            descriptor_type=None, is_active=None,
        ))
        assert is_ok(r)


class TestEdFiSync:
    def test_sync_student(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-submit-student-to-edfi"], s["conn"], ns(
            config_id=s["edfi_config_id"], student_id=s["student_id"],
            company_id=s["company_id"], collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["sync_status"] == "pending"

    def test_sync_enrollment(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-submit-enrollment-to-edfi"], s["conn"], ns(
            config_id=s["edfi_config_id"], student_id=None,
            company_id=s["company_id"], collection_window_id=None,
        ))
        assert is_ok(r)

    def test_sync_sped(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-submit-sped-to-edfi"], s["conn"], ns(
            config_id=s["edfi_config_id"], company_id=s["company_id"],
            school_year=2025, collection_window_id=None,
        ))
        assert is_ok(r)

    def test_sync_el(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-submit-el-to-edfi"], s["conn"], ns(
            config_id=s["edfi_config_id"], company_id=s["company_id"],
            school_year=2025, collection_window_id=None,
        ))
        assert is_ok(r)

    def test_sync_discipline(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-submit-discipline-to-edfi"], s["conn"], ns(
            config_id=s["edfi_config_id"], company_id=s["company_id"],
            school_year=2025, collection_window_id=None,
        ))
        assert is_ok(r)

    def test_get_sync_log(self, full_setup):
        s = full_setup
        # Ledger: reporting read over the immutable sync log; no gl_* writes,
        # so no balanced-legs assertion can hold. Depth signal: the listed
        # entry equals the stored row the submit action wrote, and the read
        # itself stores nothing.
        synced = call_action(EDFI_ACTIONS["statereport-submit-student-to-edfi"], s["conn"], ns(
            config_id=s["edfi_config_id"], student_id=s["student_id"],
            company_id=s["company_id"], collection_window_id=None,
        ))
        assert is_ok(synced)
        assert synced["sync_status"] == "pending"
        stored = _stored_row("sr_edfi_sync_log", synced["sync_log_id"])
        assert stored is not None
        assert stored["config_id"] == s["edfi_config_id"]
        assert stored["resource_type"] == "students"
        assert stored["operation"] == "POST"
        assert stored["internal_id"] == s["student_id"]
        assert stored["sync_status"] == "pending"
        assert stored["retry_count"] == 0
        assert stored["http_status"] == 0
        assert stored["company_id"] == s["company_id"]

        before = _verify_tables("sr_edfi_sync_log", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-edfi-sync-log"], s["conn"], ns(
            resource_type=None, internal_id=None,
            company_id=s["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 1
        assert len(r["logs"]) == 1
        entry = r["logs"][0]
        for field in ("id", "config_id", "resource_type", "operation",
                      "internal_id", "edfi_natural_key", "http_status",
                      "request_payload_hash", "response_body", "sync_status",
                      "retry_count", "synced_at", "company_id"):
            assert entry[field] == stored[field], field

        # Filters are applied: the true resource type finds the entry, an
        # unknown one truthfully reports nothing.
        assert call_action(EDFI_ACTIONS["statereport-get-edfi-sync-log"], s["conn"], ns(
            resource_type="students", internal_id=None,
            company_id=s["company_id"],
            limit=50, offset=0,
        ))["count"] == 1
        empty = call_action(EDFI_ACTIONS["statereport-get-edfi-sync-log"], s["conn"], ns(
            resource_type="staff", internal_id=None,
            company_id=s["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(empty)
        assert empty["count"] == 0
        assert empty["logs"] == []
        assert _verify_tables("sr_edfi_sync_log", "audit_log") == before

    def test_get_sync_log_no_refusal_path_documented(self, full_setup):
        # This action declares no required input, so there is no refusal to
        # exercise. The negative control above (unknown filter yields an
        # empty list) plus the byte-identical check is the depth signal here.
        s = full_setup
        before = _verify_tables("sr_edfi_sync_log", "audit_log")
        r = call_action(EDFI_ACTIONS["statereport-get-edfi-sync-log"], s["conn"], ns(
            resource_type="no-such-resource", internal_id=None,
            company_id=s["company_id"],
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 0
        assert r["logs"] == []
        assert _verify_tables("sr_edfi_sync_log", "audit_log") == before

    def test_list_sync_errors(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-list-edfi-sync-errors"], s["conn"], ns(
            company_id=s["company_id"], collection_window_id=None,
            limit=100, offset=0,
        ))
        assert is_ok(r)

    def test_retry_failed(self, full_setup):
        s = full_setup
        r = call_action(EDFI_ACTIONS["statereport-submit-failed-syncs"], s["conn"], ns(
            company_id=s["company_id"], collection_window_id=None,
        ))
        assert is_ok(r)


# ==============================================================================
# STATE REPORTING domain
# ==============================================================================

class TestCollectionWindow:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-add-collection-window"], s["conn"], ns(
            company_id=s["company_id"], name="EOY Discipline 2025",
            state_code="CA", window_type="eoy_discipline",
            school_year=2025, academic_year_id=s["year_id"],
            open_date="2025-07-01", close_date="2025-08-15",
            snapshot_date="2025-06-30",
            description="End of year discipline collection",
            required_data_categories='["discipline"]',
            is_federal_required=0, edfi_config_id=None,
            user_id="admin",
        ))
        assert is_ok(r)
        assert r["window_status"] == "upcoming"

    def test_get(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-get-collection-window"], s["conn"], ns(
            window_id=s["window_id"],
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-list-collection-windows"], s["conn"], ns(
            company_id=s["company_id"], window_status=None,
            school_year=None, state_code=None, window_type=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] >= 1

    def test_update(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-update-collection-window"], s["conn"], ns(
            window_id=s["window_id"],
            name=None, open_date=None, close_date=None, snapshot_date=None,
            description="Updated description", is_federal_required=None,
            edfi_config_id=None, required_data_categories=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_advance_status(self, full_setup):
        s = full_setup
        # upcoming -> open
        r = call_action(SR_ACTIONS["statereport-apply-window-status"], s["conn"], ns(
            window_id=s["window_id"], user_id="admin",
        ))
        assert is_ok(r)
        assert r["window_status"] == "open"


class TestSnapshot:
    def test_take_and_get(self, full_setup):
        s = full_setup
        # Advance to snapshot-eligible state first: upcoming -> open -> data_entry -> validation -> snapshot
        for _ in range(4):
            call_action(SR_ACTIONS["statereport-apply-window-status"], s["conn"], ns(
                window_id=s["window_id"], user_id="admin",
            ))
        # Now take snapshot (but this also works from any status since take_snapshot checks existing snapshot)
        # Actually take_snapshot creates its own snapshot and sets status
        # We need a fresh window (no existing snapshot)
        wid2 = seed_collection_window(s["conn"], s["company_id"], s["year_id"])
        r = call_action(SR_ACTIONS["statereport-create-snapshot"], s["conn"], ns(
            window_id=wid2, user_id="admin",
        ))
        assert is_ok(r)
        assert r["snapshot_status"] == "draft"

        # Get snapshot
        gr = call_action(SR_ACTIONS["statereport-get-snapshot"], s["conn"], ns(
            snapshot_id=r["id"], window_id=None,
        ))
        assert is_ok(gr)

    def test_list_snapshot_records(self, full_setup):
        s = full_setup
        wid2 = seed_collection_window(s["conn"], s["company_id"], s["year_id"])
        snap = call_action(SR_ACTIONS["statereport-create-snapshot"], s["conn"], ns(
            window_id=wid2, user_id="admin",
        ))
        assert is_ok(snap)
        r = call_action(SR_ACTIONS["statereport-list-snapshot-records"], s["conn"], ns(
            snapshot_id=snap["id"], record_type=None,
            limit=100, offset=0,
        ))
        assert is_ok(r)


class TestADA:
    def test_calculate(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-generate-ada"], s["conn"], ns(
            company_id=s["company_id"], date_from=None, date_to=None,
            school_year=2025,
        ))
        assert is_ok(r)

    def test_dashboard(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-get-ada-dashboard"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            per_pupil_rate="12000",
        ))
        assert is_ok(r)

    def test_chronic_absenteeism(self, full_setup):
        s = full_setup
        # Ledger: attendance reporting read; no gl_* writes, so no
        # balanced-legs assertion can hold. Depth signal: exact absence
        # fractions computed from stored attendance rows.
        sid2 = seed_student(s["conn"], s["company_id"])
        dates = ["2025-03-03", "2025-03-04", "2025-03-05", "2025-03-06",
                 "2025-03-07", "2025-03-10", "2025-03-11", "2025-03-12",
                 "2025-03-13", "2025-03-14"]
        for i, day in enumerate(dates):
            status = "absent" if i < 2 else "present"
            s["conn"].execute(
                """INSERT INTO educlaw_student_attendance
                   (id, student_id, attendance_date, attendance_status,
                    marked_by, company_id, created_by)
                   VALUES (?, ?, ?, ?, 'test', ?, '')""",
                (str(uuid.uuid4()), s["student_id"], day, status, s["company_id"]))
            s["conn"].execute(
                """INSERT INTO educlaw_student_attendance
                   (id, student_id, attendance_date, attendance_status,
                    marked_by, company_id, created_by)
                   VALUES (?, ?, ?, 'present', 'test', ?, '')""",
                (str(uuid.uuid4()), sid2, day, s["company_id"]))
        s["conn"].commit()

        before = _verify_tables(
            "educlaw_student_attendance", "educlaw_student", "audit_log")
        r = call_action(SR_ACTIONS["statereport-list-chronic-absenteeism"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
            threshold=None,
        ))
        assert is_ok(r)
        assert r["company_id"] == s["company_id"]
        assert r["school_year"] == 2025
        assert r["school_days"] == 10
        assert r["threshold_pct"] == "10"
        assert r["threshold_days"] == 1
        assert r["count"] == 1
        assert len(r["chronic_absentees"]) == 1
        entry = r["chronic_absentees"][0]
        assert entry["student_id"] == s["student_id"]
        assert entry["first_name"] == "Test"
        assert entry["last_name"] == "Student"
        assert entry["grade_level"] == ""
        assert entry["absent_days"] == 2
        assert entry["school_days"] == 10
        expected_pct = str((Decimal(2) / Decimal(10) * Decimal(100)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP))
        assert entry["absent_pct"] == expected_pct == "20.0"
        assert _verify_tables(
            "educlaw_student_attendance", "educlaw_student", "audit_log") == before

    def test_chronic_absenteeism_refusal(self, full_setup):
        s = full_setup
        before = _verify_tables(
            "educlaw_student_attendance", "educlaw_student", "audit_log")
        r = call_action(SR_ACTIONS["statereport-list-chronic-absenteeism"], s["conn"], ns(
            company_id=s["company_id"], school_year=None,
            threshold=None,
        ))
        assert is_error(r)
        assert r["message"] == "--school-year is required"
        assert _verify_tables(
            "educlaw_student_attendance", "educlaw_student", "audit_log") == before


class TestReports:
    def test_data_readiness(self, full_setup):
        s = full_setup
        # Ledger: readiness scoring read; no gl_* writes, so no
        # balanced-legs assertion can hold. Depth signal: exact category
        # fractions. A second active student with no supplement and no
        # attendance makes every fraction load-bearing (1 of 2).
        sid2 = seed_student(s["conn"], s["company_id"])
        s["conn"].execute(
            """INSERT INTO educlaw_student_attendance
               (id, student_id, attendance_date, attendance_status,
                marked_by, company_id, created_by)
               VALUES (?, ?, '2025-03-03', 'present', 'test', ?, '')""",
            (str(uuid.uuid4()), s["student_id"], s["company_id"]))
        s["conn"].commit()

        before = _verify_tables(
            "educlaw_student", "sr_student_supplement", "sr_sped_placement",
            "sr_el_program", "educlaw_student_attendance", "audit_log")
        r = call_action(SR_ACTIONS["statereport-get-data-readiness-report"], s["conn"], ns(
            company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert r["company_id"] == s["company_id"]
        assert r["total_students"] == 2
        assert r["scores"] == {
            "demographics": _pct_str(1, 2),
            "sped": "100",
            "el": "100",
            "attendance": _pct_str(1, 2),
        }
        assert r["scores"]["demographics"] == "50.0"
        assert r["scores"]["attendance"] == "50.0"
        assert r["details"] == {
            "demo_students_complete": 1,
            "sped_students": 0,
            "sped_with_placement": 0,
            "el_students": 0,
            "el_with_program": 0,
            "students_with_attendance": 1,
        }
        expected_overall = str(
            ((Decimal("50.0") + Decimal("100") + Decimal("100") + Decimal("50.0"))
             / Decimal("4")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        assert r["overall_score"] == expected_overall == "75.0"
        assert _verify_tables(
            "educlaw_student", "sr_student_supplement", "sr_sped_placement",
            "sr_el_program", "educlaw_student_attendance", "audit_log") == before

    def test_data_readiness_refusal(self, full_setup):
        s = full_setup
        before = _verify_tables(
            "educlaw_student", "sr_student_supplement", "audit_log")
        r = call_action(SR_ACTIONS["statereport-get-data-readiness-report"], s["conn"], ns(
            company_id=None,
        ))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _verify_tables(
            "educlaw_student", "sr_student_supplement", "audit_log") == before

    def test_enrollment_report(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-generate-enrollment-report"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
        ))
        assert is_ok(r)

    def test_crdc_report(self, full_setup):
        s = full_setup
        r = call_action(SR_ACTIONS["statereport-generate-crdc-report"], s["conn"], ns(
            company_id=s["company_id"], school_year=2025,
        ))
        assert is_ok(r)


# ==============================================================================
# DATA VALIDATION domain
# ==============================================================================

class TestValidationRule:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(DV_ACTIONS["statereport-add-validation-rule"], conn, ns(
            rule_code="TEST-001", category="enrollment", severity="critical",
            name="Test Rule", description="A test validation rule",
            applicable_windows='[]', applicable_states='[]',
            is_federal_rule=1,
            sql_query="SELECT id as student_id FROM educlaw_student WHERE status='inactive'",
            error_message_template="Student {student_id} is inactive",
            user_id="admin",
        ))
        assert is_ok(r)

    def test_update(self, setup):
        conn, cid = setup
        add_r = call_action(DV_ACTIONS["statereport-add-validation-rule"], conn, ns(
            rule_code="TEST-002", category="demographics", severity="major",
            name="Test Rule 2", description=None,
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DV_ACTIONS["statereport-update-validation-rule"], conn, ns(
            rule_id=add_r["id"], rule_code=None,
            category=None, severity=None, name="Updated Rule",
            description="Updated desc",
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(r)

    def test_get(self, setup):
        conn, cid = setup
        add_r = call_action(DV_ACTIONS["statereport-add-validation-rule"], conn, ns(
            rule_code="TEST-003", category="sped", severity="minor",
            name="Test Rule 3", description=None,
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DV_ACTIONS["statereport-get-validation-rule"], conn, ns(
            rule_id=add_r["id"], rule_code=None,
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(DV_ACTIONS["statereport-list-validation-rules"], conn, ns(
            category=None, severity=None,
            is_active=None, is_federal_rule=None,
            limit=100, offset=0,
        ))
        assert is_ok(r)

    def test_toggle(self, setup):
        conn, cid = setup
        add_r = call_action(DV_ACTIONS["statereport-add-validation-rule"], conn, ns(
            rule_code="TEST-004", category="el", severity="warning",
            name="Toggle Test", description=None,
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(DV_ACTIONS["statereport-update-validation-rule-status"], conn, ns(
            rule_id=add_r["id"], rule_code=None, is_active=0,
        ))
        assert is_ok(r)
        assert r["is_active"] == 0

    def test_seed(self, setup):
        conn, cid = setup
        r = call_action(DV_ACTIONS["statereport-import-validation-rules"], conn, ns(
            company_id=cid, user_id="admin",
        ))
        assert is_ok(r)
        assert r["inserted"] > 0


class TestValidationRun:
    def test_run_validation(self, full_setup):
        s = full_setup
        # Seed rules first
        call_action(DV_ACTIONS["statereport-import-validation-rules"], s["conn"], ns(
            company_id=s["company_id"], user_id="admin",
        ))
        r = call_action(DV_ACTIONS["statereport-apply-validation"], s["conn"], ns(
            window_id=s["window_id"], company_id=s["company_id"],
            user_id="admin",
        ))
        assert is_ok(r)
        assert "rules_run" in r

    def test_run_student_validation(self, full_setup):
        s = full_setup
        call_action(DV_ACTIONS["statereport-import-validation-rules"], s["conn"], ns(
            company_id=s["company_id"], user_id="admin",
        ))
        r = call_action(DV_ACTIONS["statereport-apply-student-validation"], s["conn"], ns(
            window_id=s["window_id"], student_id=s["student_id"],
            company_id=s["company_id"], user_id="admin",
        ))
        assert is_ok(r)

    def test_get_results(self, full_setup):
        s = full_setup
        # Ledger: validation reporting read; no gl_* writes, so no
        # balanced-legs assertion can hold. Depth signal: the result equals
        # the stored row the validation run wrote, with an exact severity
        # summary. A dedicated rule on a fresh window keeps the count at
        # exactly one.
        wid2 = seed_collection_window(s["conn"], s["company_id"], s["year_id"])
        rule = call_action(DV_ACTIONS["statereport-add-validation-rule"], s["conn"], ns(
            rule_code="DEEP-RES-001", category="enrollment", severity="critical",
            name="Deep Results Rule", description="Depth probe rule",
            applicable_windows="[]", applicable_states="[]",
            is_federal_rule=0,
            sql_query="SELECT id AS student_id FROM educlaw_student WHERE status = 'active'",
            error_message_template="Student {student_id} is active",
            user_id="admin",
        ))
        assert is_ok(rule)
        run = call_action(DV_ACTIONS["statereport-apply-validation"], s["conn"], ns(
            window_id=wid2, company_id=s["company_id"],
            user_id="admin",
        ))
        assert is_ok(run)
        assert run["total_violations"] == 1
        before = _verify_tables(
            "sr_validation_result", "sr_validation_rule", "audit_log")
        assert len(before["sr_validation_result"]) == 1
        stored = before["sr_validation_result"][0]
        assert stored["collection_window_id"] == wid2
        assert stored["rule_id"] == rule["id"]
        assert stored["student_id"] == s["student_id"]
        assert stored["is_resolved"] == 0
        assert stored["run_by"] == "admin"
        assert stored["company_id"] == s["company_id"]
        assert stored["error_detail"] == json.dumps({"student_id": s["student_id"]})

        r = call_action(DV_ACTIONS["statereport-get-validation-results"], s["conn"], ns(
            window_id=wid2, limit=100, offset=0,
        ))
        assert is_ok(r)
        assert r["window_id"] == wid2
        assert r["count"] == 1
        assert len(r["results"]) == 1
        res = r["results"][0]
        assert res["id"] == stored["id"]
        assert res["rule_code"] == "DEEP-RES-001"
        assert res["category"] == "enrollment"
        assert res["severity"] == "critical"
        assert res["rule_name"] == "Deep Results Rule"
        assert res["student_id"] == s["student_id"]
        assert res["collection_window_id"] == wid2
        assert res["is_resolved"] == 0
        assert r["summary_by_severity"] == {"critical": 1}
        assert _verify_tables(
            "sr_validation_result", "sr_validation_rule", "audit_log") == before

    def test_get_results_refusal(self, full_setup):
        s = full_setup
        before = _verify_tables(
            "sr_validation_result", "sr_validation_rule", "audit_log")
        r = call_action(DV_ACTIONS["statereport-get-validation-results"], s["conn"], ns(
            window_id=None, limit=100, offset=0,
        ))
        assert is_error(r)
        assert r["message"] == "--window-id is required"
        assert _verify_tables(
            "sr_validation_result", "sr_validation_rule", "audit_log") == before


class TestSubmissionErrors:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(DV_ACTIONS["statereport-list-submission-errors"], s["conn"], ns(
            window_id=s["window_id"],
            severity=None, resolution_status=None,
            error_category=None, student_id=None,
            assigned_to=None, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_error_dashboard(self, full_setup):
        s = full_setup
        # Ledger: error reporting read; no gl_* writes, so no balanced-legs
        # assertion can hold. Depth signal: the breakdown cell equals the
        # stored submission-error row the validation run wrote.
        wid2 = seed_collection_window(s["conn"], s["company_id"], s["year_id"])
        rule = call_action(DV_ACTIONS["statereport-add-validation-rule"], s["conn"], ns(
            rule_code="DEEP-ERR-001", category="attendance", severity="major",
            name="Deep Error Rule", description="Depth probe rule",
            applicable_windows="[]", applicable_states="[]",
            is_federal_rule=0,
            sql_query="SELECT id AS student_id FROM educlaw_student WHERE status = 'active'",
            error_message_template="Deep error {student_id}",
            user_id="admin",
        ))
        assert is_ok(rule)
        run = call_action(DV_ACTIONS["statereport-apply-validation"], s["conn"], ns(
            window_id=wid2, company_id=s["company_id"],
            user_id="admin",
        ))
        assert is_ok(run)
        assert run["total_violations"] == 1
        before = _verify_tables("sr_submission_error", "audit_log")
        assert len(before["sr_submission_error"]) == 1
        stored = before["sr_submission_error"][0]
        assert stored["collection_window_id"] == wid2
        assert stored["error_source"] == "internal_validation"
        assert stored["error_level"] == "2"
        assert stored["severity"] == "major"
        assert stored["error_code"] == "DEEP-ERR-001"
        assert stored["error_category"] == "attendance"
        assert stored["error_message"] == f"Deep error {s['student_id']}"
        assert stored["student_id"] == s["student_id"]
        assert stored["resolution_status"] == "open"
        assert stored["company_id"] == s["company_id"]

        r = call_action(DV_ACTIONS["statereport-get-error-dashboard"], s["conn"], ns(
            window_id=wid2,
        ))
        assert is_ok(r)
        assert r["window_id"] == wid2
        assert r["breakdown"] == [{
            "severity": "major",
            "error_category": "attendance",
            "resolution_status": "open",
            "count": 1,
        }]
        assert r["by_severity"] == {"major": {
            "severity": "major",
            "total": 1,
            "open_count": 1,
            "resolved_count": 0,
        }}
        assert _verify_tables("sr_submission_error", "audit_log") == before

    def test_error_dashboard_refusal(self, full_setup):
        s = full_setup
        before = _verify_tables("sr_submission_error", "audit_log")
        r = call_action(DV_ACTIONS["statereport-get-error-dashboard"], s["conn"], ns(
            window_id=None,
        ))
        assert is_error(r)
        assert r["message"] == "--window-id is required"
        assert _verify_tables("sr_submission_error", "audit_log") == before


# ==============================================================================
# SUBMISSION TRACKING domain
# ==============================================================================

class TestSubmission:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
            window_id=s["window_id"], company_id=s["company_id"],
            submission_type="initial", submission_method="edfi_api",
            snapshot_id=None, linked_submission_id=None,
            submitted_at=None, submitted_by="admin",
            records_submitted=100, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id="admin",
        ))
        assert is_ok(r)
        assert r["submission_status"] == "pending"

    def test_update_status(self, full_setup):
        s = full_setup
        add_r = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
            window_id=s["window_id"], company_id=s["company_id"],
            submission_type="initial", submission_method="flat_file",
            snapshot_id=None, linked_submission_id=None,
            submitted_at=None, submitted_by=None,
            records_submitted=50, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(SUB_ACTIONS["statereport-update-submission-status"], s["conn"], ns(
            submission_id=add_r["id"], submission_status="completed",
            records_submitted=None, records_accepted=48,
            records_rejected=2,
            state_confirmation_id="CONF-123",
            state_confirmed_at=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        add_r = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
            window_id=s["window_id"], company_id=s["company_id"],
            submission_type="initial", submission_method="manual_portal",
            snapshot_id=None, linked_submission_id=None,
            submitted_at=None, submitted_by=None,
            records_submitted=None, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id=None,
        ))
        assert is_ok(add_r)
        r = call_action(SUB_ACTIONS["statereport-get-submission"], s["conn"], ns(
            submission_id=add_r["id"],
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(SUB_ACTIONS["statereport-list-submissions"], s["conn"], ns(
            company_id=s["company_id"], window_id=None,
            submission_status=None, submission_type=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


class TestCertification:
    def test_certify(self, full_setup):
        s = full_setup
        # Create snapshot + submission, then certify
        wid2 = seed_collection_window(s["conn"], s["company_id"], s["year_id"])
        snap = call_action(SR_ACTIONS["statereport-create-snapshot"], s["conn"], ns(
            window_id=wid2, user_id="admin",
        ))
        assert is_ok(snap)
        sub = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
            window_id=wid2, company_id=s["company_id"],
            submission_type="initial", submission_method="edfi_api",
            snapshot_id=snap["id"], linked_submission_id=None,
            submitted_at=None, submitted_by=None,
            records_submitted=None, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id=None,
        ))
        assert is_ok(sub)
        r = call_action(SUB_ACTIONS["statereport-approve-submission"], s["conn"], ns(
            submission_id=sub["id"], certified_by="superintendent",
            certification_notes="Approved for submission", user_id="superintendent",
        ))
        assert is_ok(r)
        assert r["submission_status"] == "certified"


class TestAmendment:
    def test_create(self, full_setup):
        s = full_setup
        # Create original submission first
        sub = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
            window_id=s["window_id"], company_id=s["company_id"],
            submission_type="initial", submission_method="edfi_api",
            snapshot_id=None, linked_submission_id=None,
            submitted_at=None, submitted_by=None,
            records_submitted=None, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id=None,
        ))
        assert is_ok(sub)
        r = call_action(SUB_ACTIONS["statereport-create-amendment"], s["conn"], ns(
            original_submission_id=sub["id"],
            amendment_reason="Corrected enrollment dates",
            company_id=s["company_id"],
            submission_method=None, user_id="admin",
        ))
        assert is_ok(r)
        assert r["submission_type"] == "amendment"
        assert r["window_status"] == "data_entry"


class TestSubmissionHistory:
    def _seed_submission(self, s):
        sub = call_action(SUB_ACTIONS["statereport-add-submission"], s["conn"], ns(
            window_id=s["window_id"], company_id=s["company_id"],
            submission_type="initial", submission_method="edfi_api",
            snapshot_id=None, linked_submission_id=None,
            submitted_at=None, submitted_by="admin",
            records_submitted=100, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id="admin",
        ))
        assert is_ok(sub)
        assert sub["submission_status"] == "pending"
        return sub

    def test_get_history(self, full_setup):
        s = full_setup
        # Ledger: submission-history read; no gl_* writes, so no
        # balanced-legs assertion can hold. Depth signal: every listed
        # submission equals its stored row and the window fields match the
        # stored collection window.
        sub = self._seed_submission(s)
        stored = _stored_row("sr_submission", sub["id"])
        assert stored is not None
        assert stored["naming_series"] == sub["naming_series"]
        assert stored["submission_type"] == "initial"
        assert stored["submission_method"] == "edfi_api"
        assert stored["submission_status"] == "pending"
        assert stored["records_submitted"] == 100
        assert stored["records_accepted"] == 0
        assert stored["records_rejected"] == 0
        assert stored["submitted_by"] == "admin"
        assert stored["collection_window_id"] == s["window_id"]
        assert stored["company_id"] == s["company_id"]
        window = _stored_row("sr_collection_window", s["window_id"])

        before = _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot", "audit_log")
        r = call_action(SUB_ACTIONS["statereport-get-submission-history"], s["conn"], ns(
            window_id=s["window_id"],
        ))
        assert is_ok(r)
        assert r["window_id"] == s["window_id"]
        assert r["window_name"] == window["name"]
        assert r["window_type"] == window["window_type"]
        assert r["school_year"] == window["school_year"]
        assert r["current_window_status"] == window["status"]
        assert r["submission_count"] == 1
        assert len(r["submissions"]) == 1
        listed = r["submissions"][0]
        for field in ("id", "naming_series", "collection_window_id",
                      "submission_type", "submission_method",
                      "submission_status", "submitted_by", "records_submitted",
                      "records_accepted", "records_rejected", "company_id"):
            assert listed[field] == stored[field], field
        assert r["snapshots"] == []
        assert _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot", "audit_log") == before

    def test_get_history_refusal(self, full_setup):
        s = full_setup
        before = _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot", "audit_log")
        r = call_action(SUB_ACTIONS["statereport-get-submission-history"], s["conn"], ns(
            window_id=None,
        ))
        assert is_error(r)
        assert r["message"] == "--window-id is required"
        assert _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot", "audit_log") == before

    def test_audit_trail(self, full_setup):
        s = full_setup
        # Ledger: audit-trail read; no gl_* writes, so no balanced-legs
        # assertion can hold. Depth signal: status, submission subset columns,
        # and the empty error summary all match stored rows.
        sub = self._seed_submission(s)
        stored = _stored_row("sr_submission", sub["id"])
        window = _stored_row("sr_collection_window", s["window_id"])

        before = _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot",
            "sr_submission_error", "audit_log")
        r = call_action(SUB_ACTIONS["statereport-get-submission-audit-trail"], s["conn"], ns(
            window_id=s["window_id"],
        ))
        assert is_ok(r)
        assert r["window_id"] == s["window_id"]
        assert r["window_name"] == window["name"]
        assert r["window_type"] == window["window_type"]
        assert r["school_year"] == window["school_year"]
        assert r["state_code"] == window["state_code"]
        assert r["current_status"] == window["status"] == "upcoming"
        assert r["created_at"] == window["created_at"]
        assert r["updated_at"] == window["updated_at"]
        assert len(r["submissions"]) == 1
        listed = r["submissions"][0]
        for field in ("id", "naming_series", "submission_type",
                      "submission_status", "submitted_by", "records_submitted",
                      "records_accepted", "records_rejected",
                      "amendment_reason", "linked_submission_id", "created_at"):
            assert listed[field] == stored[field], field
        assert r["snapshots"] == []
        assert r["error_summary"] == []
        assert _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot",
            "sr_submission_error", "audit_log") == before

    def test_audit_trail_refusal_unknown_window(self, full_setup):
        s = full_setup
        missing = "00000000-0000-0000-0000-000000000000"
        before = _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot",
            "sr_submission_error", "audit_log")
        r = call_action(SUB_ACTIONS["statereport-get-submission-audit-trail"], s["conn"], ns(
            window_id=missing,
        ))
        assert is_error(r)
        assert r["message"] == f"Collection window {missing} not found"
        assert _verify_tables(
            "sr_collection_window", "sr_submission", "sr_snapshot",
            "sr_submission_error", "audit_log") == before
