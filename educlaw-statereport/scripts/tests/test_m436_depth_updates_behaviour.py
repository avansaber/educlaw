"""M436 depth: behavioural evidence for 12 update actions tested only for shape/routing.

Prior state (each action's existing test was read before writing anything below):
- `statereport-update-student-supplement`: shape-only
  (`TestStudentSupplement.test_update` in `test_statereport.py` asserts `is_ok` only).
- `statereport-update-el-status`: shape-only (`test_update_el_status` asserts `is_ok`).
- `statereport-update-sped-status`: shape-only (`test_update_sped_status` asserts `is_ok`).
- `statereport-update-economic-status`: shape-only (`test_update_economic_status`).
- `statereport-update-sped-placement`: shape-only (`TestSpedPlacement.test_update`).
- `statereport-update-sped-service`: NO existing test (only add/list/delete are covered).
- `statereport-update-el-program`: shape-only (`TestElProgram.test_update`).
- `statereport-update-discipline-student`: NO existing test (only add/list are covered).
- `statereport-update-discipline-action`: NO existing test (only add is covered).
- `statereport-update-edfi-config`: shape-only (`TestEdFiConfig.test_update`).
- `statereport-update-org-mapping`: NO existing test (only add/list are covered).
- `statereport-update-error-resolution`: NO existing test at all.

Every success test below observes the database through a FRESH `get_connection()`
read-back (a different connection than the one the action wrote through) built with
PyPika (`erpclaw_lib.query`): the exact stored row afterwards, the from->to change,
and the columns that must NOT have changed. Catalog questions go through
`erpclaw_lib.seam`; there is no `sqlite_master`, no `PRAGMA`, no `information_schema`.

Money note: none of these 12 actions stores money. The touched tables hold TEXT
status codes, INTEGER flags/counters and TEXT dates; there is no Decimal column in
scope, so no monetary assertion belongs here and none is added.

Ledger note, stated once so no later reader adds a balance assertion that cannot
hold: none of these 12 handlers reaches the general ledger. Each writes only its
own domain table plus one `audit_log` line. Every per-action section repeats its
own ledger scope inline.

Signal depth per action (all stored-row; none is a ledger effect):
- statereport-update-student-supplement: stored row (`sr_student_supplement`).
- statereport-update-el-status: stored row (`sr_student_supplement` EL columns).
- statereport-update-sped-status: stored row (`sr_student_supplement` SPED columns).
- statereport-update-economic-status: stored row (`sr_student_supplement` econ columns).
- statereport-update-sped-placement: stored row (`sr_sped_placement`).
- statereport-update-sped-service: stored row (`sr_sped_service`).
- statereport-update-el-program: stored row (`sr_el_program`).
- statereport-update-discipline-student: stored row (`educlaw_k12_discipline_student`).
- statereport-update-discipline-action: stored row (`educlaw_k12_discipline_action`).
- statereport-update-edfi-config: stored row (`sr_edfi_config`).
- statereport-update-org-mapping: stored row (`sr_org_mapping`).
- statereport-update-error-resolution: stored row (`sr_submission_error`).
"""
import importlib.util
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_LIB_DIR = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if os.path.isdir(os.path.join(_LIB_DIR, "erpclaw_lib")) and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, insert_row
from erpclaw_lib import seam as _seam

call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error

DEMO = _load("demographics", _SCRIPTS_DIR).ACTIONS
DISC = _load("discipline", _SCRIPTS_DIR).ACTIONS
EDFI = _load("ed_fi", _SCRIPTS_DIR).ACTIONS
DV = _load("data_validation", _SCRIPTS_DIR).ACTIONS


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def env(db_path):
    os.environ["ERPCLAW_DB_PATH"] = db_path
    assert _seam.table_exists("sr_student_supplement", db_path)
    assert _seam.table_exists("sr_sped_placement", db_path)
    assert _seam.table_exists("sr_submission_error", db_path)
    conn = _helpers.get_conn(db_path)
    cid = _helpers.seed_company(conn)
    sid = _helpers.seed_student(conn, cid)
    yid = _helpers.seed_academic_year(conn, cid)
    supp_id = _helpers.seed_supplement(conn, sid, cid)
    wid = _helpers.seed_collection_window(conn, cid, yid)
    edfi_id = _helpers.seed_edfi_config(conn, cid)
    yield {
        "conn": conn, "db_path": db_path, "company_id": cid,
        "student_id": sid, "year_id": yid, "supplement_id": supp_id,
        "window_id": wid, "edfi_config_id": edfi_id,
    }
    conn.close()
    os.environ.pop("ERPCLAW_DB_PATH", None)


def _read(db_path, table, rid):
    """Read one row back through a fresh seam connection (not the action's conn)."""
    conn = get_connection(db_path)
    try:
        tbl = Table(table)
        sql = Q.from_(tbl).select(tbl.star).where(Field("id") == P()).get_sql()
        row = conn.execute(sql, (rid,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _dump(conn, table):
    tbl = Table(table)
    rows = conn.execute(Q.from_(tbl).select(tbl.star).get_sql()).fetchall()
    return sorted(tuple("" if v is None else str(v) for v in r) for r in rows)


def _snap(conn, tables):
    return {t: _dump(conn, t) for t in tables}


def _count(conn, table):
    tbl = Table(table)
    sql = Q.from_(tbl).select(Field("id")).get_sql()
    return len(conn.execute(sql).fetchall())


def _add_incident(e, incident_type="bullying"):
    r = call_action(DISC["statereport-add-discipline-incident"], e["conn"], ns(
        company_id=e["company_id"], school_year=2025,
        incident_date="2025-10-15", incident_type=incident_type,
        incident_time=None, incident_description=None,
        campus_location=None, reported_by=None,
        user_id=None,
    ))
    assert is_ok(r), r
    return r["id"]


def _add_discipline_student(e, incident_id, role="offender", is_idea=None):
    r = call_action(DISC["statereport-add-discipline-student"], e["conn"], ns(
        incident_id=incident_id, student_id=e["student_id"],
        role=role, company_id=e["company_id"],
        is_idea_student=is_idea, is_504_student=None,
        user_id=None,
    ))
    assert is_ok(r), r
    return r["id"]


def _add_placement(e, disability="AUT"):
    r = call_action(DEMO["statereport-add-sped-placement"], e["conn"], ns(
        student_id=e["student_id"], school_year=2025,
        disability_category=disability, educational_environment="RC_80",
        company_id=e["company_id"],
        secondary_disability=None,
        sped_program_entry_date="2024-09-01", sped_program_exit_date=None,
        sped_exit_reason=None,
        iep_start_date="2024-09-01", iep_review_date=None,
        is_transition_plan_required=None, lre_percentage=None,
        is_early_childhood=None, early_childhood_environment=None,
        user_id=None,
    ))
    assert is_ok(r), r
    return r["id"]


def _seed_error(e):
    """Seed one open submission error via the owning module's own table shape."""
    err_id = str(uuid.uuid4())
    now = _now_iso()
    sql, _ = insert_row("sr_submission_error", {
        "id": P(), "collection_window_id": P(), "submission_id": P(),
        "error_source": P(), "error_level": P(), "severity": P(),
        "error_code": P(), "error_category": P(), "error_message": P(),
        "student_id": P(), "staff_id": P(), "record_type": P(),
        "field_name": P(), "field_value": P(), "resolution_status": P(),
        "resolution_method": P(), "resolved_by": P(), "resolved_at": P(),
        "resolution_notes": P(), "assigned_to": P(), "assigned_at": P(),
        "state_ticket_id": P(), "company_id": P(), "created_at": P(),
        "updated_at": P(), "created_by": P(),
    })
    e["conn"].execute(sql, (
        err_id, e["window_id"], None,
        "internal_validation", "2", "major",
        "TEST-001", "demographics", "Missing race for student",
        e["student_id"], None, "demographics",
        "", "", "open",
        "", "", "",
        "", "", "",
        "", e["company_id"], now,
        now, "seeder",
    ))
    e["conn"].commit()
    return err_id


# ---------------------------------------------------------------------------
# statereport-update-student-supplement (stored row)
# ---------------------------------------------------------------------------

def test_update_student_supplement_persists_ssid_and_rollup(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    before = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert before["ssid"] == "SSN12345"
    assert before["race_federal_rollup"] == "WHITE"
    r = call_action(DEMO["statereport-update-student-supplement"], conn, ns(
        supplement_id=e["supplement_id"], student_id=None,
        ssid="SS-DEEP-001", ssid_state_code=None, ssid_status=None,
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
    assert is_ok(r), r
    assert r["id"] == e["supplement_id"]
    after = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert after["ssid"] == "SS-DEEP-001"
    assert after["is_hispanic_latino"] == 1
    assert after["race_codes"] == '["WHITE"]'
    assert after["race_federal_rollup"] == "HISPANIC_OR_LATINO"
    assert after["student_id"] == e["student_id"]
    assert after["ssid_state_code"] == "CA"
    assert after["ssid_status"] == "assigned"
    assert after["is_el"] == 0
    assert after["is_sped"] == 0
    assert after["is_economically_disadvantaged"] == 0
    assert after["updated_at"] != ""


def test_update_student_supplement_refuses_bad_ssid_status_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_student_supplement", "audit_log"])
    r = call_action(DEMO["statereport-update-student-supplement"], conn, ns(
        supplement_id=e["supplement_id"], student_id=None,
        ssid=None, ssid_state_code=None, ssid_status="bogus",
        is_hispanic_latino=None, race_codes=None,
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
    assert is_error(r)
    assert r["message"] == "--ssid-status must be one of: pending, assigned, not_applicable"
    assert _snap(conn, ["sr_student_supplement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-el-status (stored row)
# ---------------------------------------------------------------------------

def test_update_el_status_persists_el_columns(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    before = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert before["is_el"] == 0
    r = call_action(DEMO["statereport-update-el-status"], conn, ns(
        student_id=e["student_id"],
        is_el=1, el_entry_date="2024-09-01",
        home_language_code="spa", native_language_code="spa",
        english_proficiency_level="3",
        english_proficiency_instrument="ELPAC",
        el_exit_date=None, is_rfep=None, rfep_date=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == e["supplement_id"]
    after = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert after["is_el"] == 1
    assert after["el_entry_date"] == "2024-09-01"
    assert after["home_language_code"] == "spa"
    assert after["native_language_code"] == "spa"
    assert after["english_proficiency_level"] == "3"
    assert after["english_proficiency_instrument"] == "ELPAC"
    assert after["el_exit_date"] == ""
    assert after["is_rfep"] == 0
    assert after["is_sped"] == 0
    assert after["ssid"] == "SSN12345"


def test_update_el_status_refuses_missing_student_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_student_supplement", "audit_log"])
    r = call_action(DEMO["statereport-update-el-status"], conn, ns(
        student_id=None,
        is_el=1, el_entry_date=None,
        home_language_code=None, native_language_code=None,
        english_proficiency_level=None,
        english_proficiency_instrument=None,
        el_exit_date=None, is_rfep=None, rfep_date=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--student-id is required"
    assert _snap(conn, ["sr_student_supplement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-sped-status (stored row)
# ---------------------------------------------------------------------------

def test_update_sped_status_persists_sped_columns(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    before = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert before["is_sped"] == 0
    assert before["is_504"] == 0
    r = call_action(DEMO["statereport-update-sped-status"], conn, ns(
        student_id=e["student_id"],
        is_sped=1, is_504=1,
        sped_entry_date="2023-01-15", sped_exit_date=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == e["supplement_id"]
    after = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert after["is_sped"] == 1
    assert after["is_504"] == 1
    assert after["sped_entry_date"] == "2023-01-15"
    assert after["sped_exit_date"] == ""
    assert after["is_el"] == 0
    assert after["ssid"] == "SSN12345"


def test_update_sped_status_refuses_unknown_student_and_writes_nothing(env):
    e, conn = env, env["conn"]
    ghost = str(uuid.uuid4())
    before = _snap(conn, ["sr_student_supplement", "audit_log"])
    r = call_action(DEMO["statereport-update-sped-status"], conn, ns(
        student_id=ghost,
        is_sped=1, is_504=None,
        sped_entry_date=None, sped_exit_date=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "No supplement found for student %s" % ghost
    assert _snap(conn, ["sr_student_supplement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-economic-status (stored row)
# ---------------------------------------------------------------------------

def test_update_economic_status_persists_econ_columns(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    before = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert before["is_economically_disadvantaged"] == 0
    assert before["lunch_program_status"] == ""
    r = call_action(DEMO["statereport-update-economic-status"], conn, ns(
        student_id=e["student_id"],
        is_economically_disadvantaged=1, lunch_program_status="free",
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == e["supplement_id"]
    after = _read(e["db_path"], "sr_student_supplement", e["supplement_id"])
    assert after["is_economically_disadvantaged"] == 1
    assert after["lunch_program_status"] == "free"
    assert after["is_el"] == 0
    assert after["is_sped"] == 0
    assert after["ssid"] == "SSN12345"


def test_update_economic_status_refuses_bad_lunch_status_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_student_supplement", "audit_log"])
    r = call_action(DEMO["statereport-update-economic-status"], conn, ns(
        student_id=e["student_id"],
        is_economically_disadvantaged=None, lunch_program_status="caviar",
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--lunch-program-status must be one of: free, reduced, paid, direct_certification, "
    assert _snap(conn, ["sr_student_supplement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-sped-placement (stored row)
# ---------------------------------------------------------------------------

def test_update_sped_placement_persists_changed_fields(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    pid = _add_placement(e, disability="AUT")
    before = _read(e["db_path"], "sr_sped_placement", pid)
    assert before["disability_category"] == "AUT"
    r = call_action(DEMO["statereport-update-sped-placement"], conn, ns(
        placement_id=pid,
        disability_category="SLD", secondary_disability=None,
        educational_environment=None,
        sped_program_entry_date=None, sped_program_exit_date=None,
        sped_exit_reason=None,
        iep_start_date=None, iep_review_date="2025-09-01",
        is_transition_plan_required=None, lre_percentage="85",
        is_early_childhood=None, early_childhood_environment=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == pid
    after = _read(e["db_path"], "sr_sped_placement", pid)
    assert after["disability_category"] == "SLD"
    assert after["lre_percentage"] == "85"
    assert after["iep_review_date"] == "2025-09-01"
    assert after["educational_environment"] == "RC_80"
    assert after["school_year"] == 2025
    assert after["student_id"] == e["student_id"]
    assert after["secondary_disability"] == ""
    assert after["updated_at"] != ""


def test_update_sped_placement_refuses_missing_id_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_sped_placement", "audit_log"])
    r = call_action(DEMO["statereport-update-sped-placement"], conn, ns(
        placement_id=None,
        disability_category="SLD", secondary_disability=None,
        educational_environment=None,
        sped_program_entry_date=None, sped_program_exit_date=None,
        sped_exit_reason=None,
        iep_start_date=None, iep_review_date=None,
        is_transition_plan_required=None, lre_percentage=None,
        is_early_childhood=None, early_childhood_environment=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--placement-id is required"
    assert _snap(conn, ["sr_sped_placement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-sped-service (stored row)
# ---------------------------------------------------------------------------

def test_update_sped_service_persists_changed_fields(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    pid = _add_placement(e, disability="SLI")
    add_r = call_action(DEMO["statereport-add-sped-service"], conn, ns(
        sped_placement_id=pid, student_id=None,
        service_type="speech_language", provider_type="school_employed",
        minutes_per_week=60,
        start_date="2024-09-01", end_date="2025-06-30",
        company_id=e["company_id"], user_id="admin",
    ))
    assert is_ok(add_r), add_r
    svc_id = add_r["id"]
    before = _read(e["db_path"], "sr_sped_service", svc_id)
    assert before["minutes_per_week"] == 60
    assert before["provider_type"] == "school_employed"
    r = call_action(DEMO["statereport-update-sped-service"], conn, ns(
        service_id=svc_id,
        service_type=None, provider_type="contracted",
        minutes_per_week=90, start_date=None, end_date=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == svc_id
    after = _read(e["db_path"], "sr_sped_service", svc_id)
    assert after["minutes_per_week"] == 90
    assert after["provider_type"] == "contracted"
    assert after["service_type"] == "speech_language"
    assert after["start_date"] == "2024-09-01"
    assert after["end_date"] == "2025-06-30"
    assert after["sped_placement_id"] == pid
    assert after["student_id"] == e["student_id"]


def test_update_sped_service_refuses_missing_id_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_sped_service", "audit_log"])
    r = call_action(DEMO["statereport-update-sped-service"], conn, ns(
        service_id=None,
        service_type=None, provider_type="contracted",
        minutes_per_week=None, start_date=None, end_date=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--service-id is required"
    assert _snap(conn, ["sr_sped_service", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-el-program (stored row)
# ---------------------------------------------------------------------------

def test_update_el_program_persists_changed_fields(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    add_r = call_action(DEMO["statereport-add-el-program"], conn, ns(
        student_id=e["student_id"], school_year=2025,
        program_type="pull_out", entry_date="2024-09-01",
        company_id=e["company_id"],
        exit_date=None, exit_reason=None,
        english_proficiency_assessed_date=None,
        proficiency_level=None, proficiency_instrument=None,
        is_parent_waived=None, waiver_date=None,
        user_id=None,
    ))
    assert is_ok(add_r), add_r
    prog_id = add_r["id"]
    before = _read(e["db_path"], "sr_el_program", prog_id)
    assert before["program_type"] == "pull_out"
    r = call_action(DEMO["statereport-update-el-program"], conn, ns(
        el_program_id=prog_id,
        program_type="push_in", entry_date=None,
        exit_date=None, exit_reason=None,
        english_proficiency_assessed_date=None,
        proficiency_level="4", proficiency_instrument="ELPAC",
        is_parent_waived=None, waiver_date=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == prog_id
    after = _read(e["db_path"], "sr_el_program", prog_id)
    assert after["program_type"] == "push_in"
    assert after["proficiency_level"] == "4"
    assert after["proficiency_instrument"] == "ELPAC"
    assert after["entry_date"] == "2024-09-01"
    assert after["school_year"] == 2025
    assert after["student_id"] == e["student_id"]
    assert after["exit_date"] == ""
    assert after["updated_at"] != ""


def test_update_el_program_refuses_missing_id_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_el_program", "audit_log"])
    r = call_action(DEMO["statereport-update-el-program"], conn, ns(
        el_program_id=None,
        program_type="push_in", entry_date=None,
        exit_date=None, exit_reason=None,
        english_proficiency_assessed_date=None,
        proficiency_level=None, proficiency_instrument=None,
        is_parent_waived=None, waiver_date=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--el-program-id is required"
    assert _snap(conn, ["sr_el_program", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-discipline-student (stored row)
# ---------------------------------------------------------------------------

def test_update_discipline_student_persists_role_and_flags(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    inc_id = _add_incident(e)
    ds_id = _add_discipline_student(e, inc_id, role="offender")
    before = _read(e["db_path"], "educlaw_k12_discipline_student", ds_id)
    assert before["role"] == "offender"
    assert before["is_idea_student"] == 0
    r = call_action(DISC["statereport-update-discipline-student"], conn, ns(
        discipline_student_id=ds_id,
        role="victim", is_idea_student=1, is_504_student=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == ds_id
    after = _read(e["db_path"], "educlaw_k12_discipline_student", ds_id)
    assert after["role"] == "victim"
    assert after["is_idea_student"] == 1
    assert after["is_504_student"] == 0
    assert after["incident_id"] == inc_id
    assert after["student_id"] == e["student_id"]


def test_update_discipline_student_refuses_bad_role_and_writes_nothing(env):
    e, conn = env, env["conn"]
    inc_id = _add_incident(e)
    ds_id = _add_discipline_student(e, inc_id, role="offender")
    before = _snap(conn, ["educlaw_k12_discipline_student", "audit_log"])
    r = call_action(DISC["statereport-update-discipline-student"], conn, ns(
        discipline_student_id=ds_id,
        role="bystander", is_idea_student=None, is_504_student=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--role must be one of: offender, victim, witness"
    assert _snap(conn, ["educlaw_k12_discipline_student", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-discipline-action (stored row)
# ---------------------------------------------------------------------------

def test_update_discipline_action_persists_changed_fields(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    inc_id = _add_incident(e, incident_type="drug_alcohol")
    ds_id = _add_discipline_student(e, inc_id, role="offender")
    add_r = call_action(DISC["statereport-add-discipline-action"], conn, ns(
        discipline_student_id=ds_id, action_type="oss_1_10",
        company_id=e["company_id"],
        days_removed=5, start_date="2025-10-16", end_date="2025-10-21",
        alternative_services_provided=1,
        alternative_services_description="Homework packets",
        mdr_required=None, mdr_outcome=None, mdr_date=None,
        user_id="admin",
    ))
    assert is_ok(add_r), add_r
    act_id = add_r["id"]
    before = _read(e["db_path"], "educlaw_k12_discipline_action", act_id)
    assert before["days_removed"] == 5
    r = call_action(DISC["statereport-update-discipline-action"], conn, ns(
        action_id=act_id,
        action_type=None, start_date=None, end_date=None,
        days_removed=10,
        alternative_services_provided=None,
        alternative_services_description="Updated packets",
        mdr_required=None, mdr_outcome=None, mdr_date=None,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == act_id
    after = _read(e["db_path"], "educlaw_k12_discipline_action", act_id)
    assert after["days_removed"] == 10
    assert after["alternative_services_description"] == "Updated packets"
    assert after["action_type"] == "oss_1_10"
    assert after["start_date"] == "2025-10-16"
    assert after["end_date"] == "2025-10-21"
    assert after["alternative_services_provided"] == 1
    assert after["mdr_required"] == 0
    assert after["discipline_student_id"] == ds_id
    assert after["updated_at"] != ""


def test_update_discipline_action_refuses_bad_type_and_writes_nothing(env):
    e, conn = env, env["conn"]
    inc_id = _add_incident(e, incident_type="drug_alcohol")
    ds_id = _add_discipline_student(e, inc_id, role="offender")
    add_r = call_action(DISC["statereport-add-discipline-action"], conn, ns(
        discipline_student_id=ds_id, action_type="oss_1_10",
        company_id=e["company_id"],
        days_removed=5, start_date=None, end_date=None,
        alternative_services_provided=None,
        alternative_services_description=None,
        mdr_required=None, mdr_outcome=None, mdr_date=None,
        user_id=None,
    ))
    assert is_ok(add_r), add_r
    before = _snap(conn, ["educlaw_k12_discipline_action", "audit_log"])
    r = call_action(DISC["statereport-update-discipline-action"], conn, ns(
        action_id=add_r["id"],
        action_type="detention_forever", start_date=None, end_date=None,
        days_removed=None,
        alternative_services_provided=None,
        alternative_services_description=None,
        mdr_required=None, mdr_outcome=None, mdr_date=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == (
        "--action-type must be one of: iss, oss_1_10, oss_gt10, "
        "expulsion_with_services, expulsion_without_services, "
        "alternative_placement, law_enforcement_referral, "
        "school_related_arrest, no_action"
    )
    assert _snap(conn, ["educlaw_k12_discipline_action", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-edfi-config (stored row)
# ---------------------------------------------------------------------------

def test_update_edfi_config_persists_profile_and_preserves_secret(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    before = _read(e["db_path"], "sr_edfi_config", e["edfi_config_id"])
    assert before["profile_name"] == "Test Config"
    assert before["is_active"] == 1
    assert before["oauth_client_secret_encrypted"] != ""
    r = call_action(EDFI["statereport-update-edfi-config"], conn, ns(
        config_id=e["edfi_config_id"],
        profile_name="Deepened Profile", state_code=None,
        ods_base_url=None, oauth_token_url=None,
        oauth_client_id=None, oauth_client_secret=None,
        api_version=None, is_active=0,
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == e["edfi_config_id"]
    after = _read(e["db_path"], "sr_edfi_config", e["edfi_config_id"])
    assert after["profile_name"] == "Deepened Profile"
    assert after["is_active"] == 0
    assert after["ods_base_url"] == "https://edfi.test.edu/api"
    assert after["oauth_client_id"] == "test-client-id"
    assert after["oauth_client_secret_encrypted"] == before["oauth_client_secret_encrypted"]
    assert after["state_code"] == "CA"
    assert after["updated_at"] != ""


def test_update_edfi_config_refuses_missing_id_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_edfi_config", "audit_log"])
    r = call_action(EDFI["statereport-update-edfi-config"], conn, ns(
        config_id=None,
        profile_name="Deepened Profile", state_code=None,
        ods_base_url=None, oauth_token_url=None,
        oauth_client_id=None, oauth_client_secret=None,
        api_version=None, is_active=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--config-id is required"
    assert _snap(conn, ["sr_edfi_config", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-org-mapping (stored row)
# ---------------------------------------------------------------------------

def test_update_org_mapping_persists_changed_fields(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    add_r = call_action(EDFI["statereport-add-org-mapping"], conn, ns(
        company_id=e["company_id"], state_code="CA",
        nces_lea_id="0600001", nces_school_id="060000100001",
        state_lea_id="CA-001", state_school_id="CA-001-001",
        edfi_lea_id=None, edfi_school_id=None,
        crdc_school_id=None,
        is_title_i_school=1, title_i_status="schoolwide",
        user_id="admin",
    ))
    assert is_ok(add_r), add_r
    map_id = add_r["id"]
    before = _read(e["db_path"], "sr_org_mapping", map_id)
    assert before["state_school_id"] == "CA-001-001"
    r = call_action(EDFI["statereport-update-org-mapping"], conn, ns(
        mapping_id=map_id,
        nces_lea_id=None, nces_school_id=None,
        state_lea_id=None, state_school_id="CA-001-099",
        edfi_lea_id=None, edfi_school_id=None, crdc_school_id=None,
        is_title_i_school=None, title_i_status="targeted_assistance",
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == map_id
    after = _read(e["db_path"], "sr_org_mapping", map_id)
    assert after["state_school_id"] == "CA-001-099"
    assert after["title_i_status"] == "targeted_assistance"
    assert after["nces_lea_id"] == "0600001"
    assert after["nces_school_id"] == "060000100001"
    assert after["state_code"] == "CA"
    assert after["state_lea_id"] == "CA-001"
    assert after["is_title_i_school"] == 1
    assert after["updated_at"] != ""


def test_update_org_mapping_unvalidated_status_raises_integrity_error(env):
    # DOCUMENTS REAL (BROKEN) BEHAVIOUR, deliberately not fixed here: unlike the
    # add path's callers, `statereport-update-org-mapping` validates no enum, so a
    # value outside the DB CHECK (`targeted_assistance`, `schoolwide`,
    # `not_title_i`, ``) escapes as a raw `sqlite3.IntegrityError` instead of a
    # truthful refusal. This action does not reach the general ledger.
    import sqlite3
    e, conn = env, env["conn"]
    add_r = call_action(EDFI["statereport-add-org-mapping"], conn, ns(
        company_id=e["company_id"], state_code="CA",
        nces_lea_id="0600001", nces_school_id="060000100001",
        state_lea_id="CA-001", state_school_id="CA-001-001",
        edfi_lea_id=None, edfi_school_id=None,
        crdc_school_id=None,
        is_title_i_school=1, title_i_status="schoolwide",
        user_id="admin",
    ))
    assert is_ok(add_r), add_r
    with pytest.raises(sqlite3.IntegrityError):
        call_action(EDFI["statereport-update-org-mapping"], conn, ns(
            mapping_id=add_r["id"],
            nces_lea_id=None, nces_school_id=None,
            state_lea_id=None, state_school_id=None,
            edfi_lea_id=None, edfi_school_id=None, crdc_school_id=None,
            is_title_i_school=None, title_i_status="targeted",
            user_id="admin",
        ))
    after = _read(e["db_path"], "sr_org_mapping", add_r["id"])
    assert after["title_i_status"] == "schoolwide"
    assert after["state_school_id"] == "CA-001-001"


def test_update_org_mapping_refuses_missing_id_and_writes_nothing(env):
    e, conn = env, env["conn"]
    before = _snap(conn, ["sr_org_mapping", "audit_log"])
    r = call_action(EDFI["statereport-update-org-mapping"], conn, ns(
        mapping_id=None,
        nces_lea_id=None, nces_school_id=None,
        state_lea_id=None, state_school_id="CA-001-099",
        edfi_lea_id=None, edfi_school_id=None, crdc_school_id=None,
        is_title_i_school=None, title_i_status=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == "--mapping-id is required"
    assert _snap(conn, ["sr_org_mapping", "audit_log"]) == before


# ---------------------------------------------------------------------------
# statereport-update-error-resolution (stored row)
# ---------------------------------------------------------------------------

def test_update_error_resolution_persists_status_method_notes(env):
    e, conn = env, env["conn"]
    # This action does not reach the general ledger; stored row only.
    err_id = _seed_error(e)
    before = _read(e["db_path"], "sr_submission_error", err_id)
    assert before["resolution_status"] == "open"
    assert _count(conn, "sr_validation_result") == 0
    r = call_action(DV["statereport-update-error-resolution"], conn, ns(
        error_id=err_id, resolution_status="in_progress",
        resolution_method="data_corrected",
        resolution_notes="Fixed in SIS",
        user_id="admin",
    ))
    assert is_ok(r), r
    assert r["id"] == err_id
    assert r["resolution_status"] == "in_progress"
    after = _read(e["db_path"], "sr_submission_error", err_id)
    assert after["resolution_status"] == "in_progress"
    assert after["resolution_method"] == "data_corrected"
    assert after["resolution_notes"] == "Fixed in SIS"
    assert after["assigned_to"] == ""
    assert after["resolved_by"] == ""
    assert after["resolved_at"] == ""
    assert after["error_code"] == "TEST-001"
    assert after["student_id"] == e["student_id"]
    assert after["updated_at"] != ""
    # A non-"resolved" status must not touch the validation results table.
    assert _count(conn, "sr_validation_result") == 0


def test_update_error_resolution_refuses_bad_status_and_writes_nothing(env):
    e, conn = env, env["conn"]
    err_id = _seed_error(e)
    before = _snap(conn, ["sr_submission_error", "sr_validation_result", "audit_log"])
    r = call_action(DV["statereport-update-error-resolution"], conn, ns(
        error_id=err_id, resolution_status="wontfix",
        resolution_method=None,
        resolution_notes=None,
        user_id="admin",
    ))
    assert is_error(r)
    assert r["message"] == (
        "--resolution-status must be one of: "
        "open, in_progress, resolved, deferred, state_waived"
    )
    assert _snap(conn, ["sr_submission_error", "sr_validation_result", "audit_log"]) == before
