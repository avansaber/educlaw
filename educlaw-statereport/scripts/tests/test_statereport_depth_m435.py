"""Depth (behavioural) tests for 12 educlaw-statereport actions.

Each action below previously had only shape/routability coverage: the test
asserted the response envelope had the right keys but never read the database.
Every test here asserts the STORED EFFECT read back through the seam
(PyPika-built queries via ``erpclaw_lib.query``), plus what did NOT change,
plus one refusal case proving a bad call writes nothing.

None of these 12 actions reaches the ledger (no GL postings anywhere in this
module); each behavioural test says so explicitly so a later reader does not
add balance assertions that cannot hold.

Money is text in this repo; none of the tables touched here carry a money
column, so there are no monetary assertions to make.

Actions covered (12):
  ed_fi: submit-attendance/enrollment/sped/el/discipline/staff-to-edfi,
         list-edfi-sync-errors, submit-failed-syncs, update-descriptor-mapping
  state_reporting: list-snapshot-records, update-collection-window
  data_validation: submit-error-escalation
"""
import importlib.util
import json
import os
import uuid
from datetime import datetime, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
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

from erpclaw_lib.query import Q, Table, Field, P  # noqa: E402

DEMO_ACTIONS = _load("demographics", _SCRIPTS_DIR).ACTIONS
DISC_ACTIONS = _load("discipline", _SCRIPTS_DIR).ACTIONS
EDFI_ACTIONS = _load("ed_fi", _SCRIPTS_DIR).ACTIONS
SR_ACTIONS = _load("state_reporting", _SCRIPTS_DIR).ACTIONS
DV_ACTIONS = _load("data_validation", _SCRIPTS_DIR).ACTIONS


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


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_row(conn, table, row_id):
    t = Table(table)
    sql = Q.from_(t).select(t.star).where(t.id == P()).get_sql()
    row = conn.execute(sql, (row_id,)).fetchone()
    return dict(row) if row else None


def _logs_for_company(conn, company_id):
    t = Table("sr_edfi_sync_log")
    sql = Q.from_(t).select(t.star).where(t.company_id == P()).orderby(t.internal_id).get_sql()
    return [dict(r) for r in conn.execute(sql, (company_id,)).fetchall()]


def _dump(conn, table):
    t = Table(table)
    sql = Q.from_(t).select(t.star).orderby(t.id).get_sql()
    return json.dumps([dict(r) for r in conn.execute(sql).fetchall()], sort_keys=True, default=str)


def _dump_all(conn):
    return "\n".join(
        _dump(conn, t) for t in (
            "sr_edfi_sync_log", "sr_edfi_descriptor_map", "sr_collection_window",
            "sr_snapshot", "sr_snapshot_record", "sr_submission_error", "audit_log",
        )
    )


def _seed_program(conn, company_id, year_id):
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_program (id, code, name, program_type, company_id)
           VALUES (?, ?, ?, 'k12', ?)""",
        (pid, f"PRG-{pid[:8]}", "Grade 5", company_id))
    conn.commit()
    return pid


def _seed_enrollment(conn, student_id, program_id, year_id, company_id,
                     status="active", date="2025-09-02"):
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_program_enrollment
           (id, naming_series, student_id, program_id, academic_year_id,
            enrollment_date, enrollment_status, company_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, f"ENR-{eid[:8]}", student_id, program_id, year_id,
         date, status, company_id))
    conn.commit()
    return eid


def _seed_attendance(conn, student_id, company_id, date, status):
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_attendance
           (id, student_id, attendance_date, section_id, attendance_status, company_id)
           VALUES (?, ?, ?, NULL, ?, ?)""",
        (aid, student_id, date, status, company_id))
    conn.commit()
    return aid


def _seed_employee(conn, company_id, first="Ada", last="Lovelace"):
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO employee (id, naming_series, first_name, last_name, company_id)
           VALUES (?, ?, ?, ?, ?)""",
        (eid, f"EMP-{eid[:8]}", first, last, company_id))
    conn.commit()
    return eid


def _seed_instructor(conn, employee_id, company_id, active=1):
    iid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_instructor
           (id, naming_series, employee_id, name, email, is_active, company_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (iid, f"INS-{iid[:8]}", employee_id, "Ada Lovelace",
         "ada@school.edu", active, company_id))
    conn.commit()
    return iid


def _seed_error(conn, window_id, company_id, student_id=None):
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_submission_error
           (id, collection_window_id, error_source, error_level, severity,
            error_code, error_category, error_message, student_id,
            resolution_status, resolution_method, state_ticket_id, company_id)
           VALUES (?, ?, 'internal_validation', '1', 'critical',
                   'E-TEST-001', 'enrollment', 'Missing enrollment date', ?,
                   'open', '', '', ?)""",
        (eid, window_id, student_id or "", company_id))
    conn.commit()
    return eid


def _seed_sync_log(conn, config_id, company_id, status, internal_id,
                   resource_type="students", retry_count=0, window_id=None):
    lid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_edfi_sync_log
           (id, config_id, collection_window_id, resource_type, operation,
            internal_id, edfi_natural_key, http_status, request_payload_hash,
            response_body, sync_status, retry_count, synced_at, company_id, created_at)
           VALUES (?, ?, ?, ?, 'POST', ?, ?, 0, 'ab', '{}', ?, ?, ?, ?, ?)""",
        (lid, config_id, window_id, resource_type, internal_id,
         json.dumps({"k": internal_id}), status, retry_count,
         _now(), company_id, _now()))
    conn.commit()
    return lid


# ==============================================================================
# 1. statereport-submit-enrollment-to-edfi — stored-row effect
# ==============================================================================

class TestSubmitEnrollmentDepth:
    def test_writes_sync_log_row(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        pid = _seed_program(conn, cid, s["year_id"])
        eid = _seed_enrollment(conn, s["student_id"], pid, s["year_id"], cid)
        # No ledger effect: this action only appends sr_edfi_sync_log rows.
        assert _logs_for_company(conn, cid) == []
        r = call_action(EDFI_ACTIONS["statereport-submit-enrollment-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], student_id=s["student_id"],
            company_id=cid, collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["synced_count"] == 1
        logs = _logs_for_company(conn, cid)
        assert len(logs) == 1
        log = logs[0]
        assert log["resource_type"] == "studentSchoolAssociations"
        assert log["internal_id"] == eid
        assert log["operation"] == "POST"
        assert log["sync_status"] == "pending"
        assert log["config_id"] == s["edfi_config_id"]
        assert log["company_id"] == cid
        assert log["retry_count"] == 0
        assert log["http_status"] == 0
        assert json.loads(log["edfi_natural_key"])["studentUniqueId"] == s["student_id"]
        assert len(log["request_payload_hash"]) == 64
        int(log["request_payload_hash"], 16)
        # Source enrollment untouched.
        enr = _read_row(conn, "educlaw_program_enrollment", eid)
        assert enr["enrollment_status"] == "active"

    def test_refusal_missing_config_writes_nothing(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-enrollment-to-edfi"], conn, ns(
            config_id=None, student_id=s["student_id"],
            company_id=cid, collection_window_id=None,
        ))
        assert is_error(r)
        assert "config-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 2. statereport-submit-attendance-to-edfi — stored-row effect
# ==============================================================================

class TestSubmitAttendanceDepth:
    def test_writes_one_log_per_attendance_row(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        a1 = _seed_attendance(conn, s["student_id"], cid, "2025-10-06", "absent")
        a2 = _seed_attendance(conn, s["student_id"], cid, "2025-10-07", "present")
        # No ledger effect: this action only appends sr_edfi_sync_log rows.
        r = call_action(EDFI_ACTIONS["statereport-submit-attendance-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            date_from=None, date_to=None, collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["synced_count"] == 2
        logs = _logs_for_company(conn, cid)
        assert len(logs) == 2
        assert sorted(l["internal_id"] for l in logs) == sorted([a1, a2])
        for log in logs:
            assert log["resource_type"] == "studentSchoolAttendanceEvents"
            assert log["operation"] == "POST"
            assert log["sync_status"] == "pending"
        keys = {json.loads(l["edfi_natural_key"])["eventDate"] for l in logs}
        assert keys == {"2025-10-06", "2025-10-07"}
        # Source attendance rows untouched.
        assert _read_row(conn, "educlaw_student_attendance", a1)["attendance_status"] == "absent"
        assert _read_row(conn, "educlaw_student_attendance", a2)["attendance_status"] == "present"

    def test_refusal_missing_company_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-attendance-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=None,
            date_from=None, date_to=None, collection_window_id=None,
        ))
        assert is_error(r)
        assert "company-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 3. statereport-submit-sped-to-edfi — stored-row effect
# ==============================================================================

class TestSubmitSpedDepth:
    def test_writes_sync_log_for_placement(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        add_r = call_action(DEMO_ACTIONS["statereport-add-sped-placement"], conn, ns(
            student_id=s["student_id"], school_year=2025,
            disability_category="SLD", educational_environment="RC_80",
            company_id=cid, secondary_disability=None,
            sped_program_entry_date="2024-09-01", sped_program_exit_date=None,
            sped_exit_reason=None, iep_start_date="2024-09-01",
            iep_review_date="2025-09-01", is_transition_plan_required=0,
            lre_percentage="85", is_early_childhood=0,
            early_childhood_environment=None, user_id="admin",
        ))
        assert is_ok(add_r)
        # No ledger effect: this action only appends sr_edfi_sync_log rows.
        r = call_action(EDFI_ACTIONS["statereport-submit-sped-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            school_year=2025, collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["synced_count"] == 1
        logs = _logs_for_company(conn, cid)
        assert len(logs) == 1
        assert logs[0]["resource_type"] == "studentSpecialEducationProgramAssociations"
        assert logs[0]["internal_id"] == add_r["id"]
        assert logs[0]["sync_status"] == "pending"
        assert json.loads(logs[0]["edfi_natural_key"])["studentUniqueId"] == "SSN12345"

    def test_refusal_missing_school_year_writes_nothing(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-sped-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            school_year=None, collection_window_id=None,
        ))
        assert is_error(r)
        assert "school-year" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 4. statereport-submit-el-to-edfi — stored-row effect
# ==============================================================================

class TestSubmitElDepth:
    def test_writes_sync_log_for_el_program(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        add_r = call_action(DEMO_ACTIONS["statereport-add-el-program"], conn, ns(
            student_id=s["student_id"], school_year=2025,
            program_type="sheltered_english", entry_date="2024-09-01",
            company_id=cid, exit_date=None, exit_reason=None,
            english_proficiency_assessed_date="2024-08-15",
            proficiency_level="3", proficiency_instrument="ELPAC",
            is_parent_waived=0, waiver_date=None, user_id="admin",
        ))
        assert is_ok(add_r)
        # No ledger effect: this action only appends sr_edfi_sync_log rows.
        r = call_action(EDFI_ACTIONS["statereport-submit-el-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            school_year=2025, collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["synced_count"] == 1
        logs = _logs_for_company(conn, cid)
        assert len(logs) == 1
        assert logs[0]["resource_type"] == "studentLanguageInstructionProgramAssociations"
        assert logs[0]["internal_id"] == add_r["id"]
        assert logs[0]["sync_status"] == "pending"

    def test_refusal_unknown_config_writes_nothing(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-el-to-edfi"], conn, ns(
            config_id="does-not-exist", company_id=cid,
            school_year=2025, collection_window_id=None,
        ))
        assert is_error(r)
        assert "not found" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 5. statereport-submit-discipline-to-edfi — stored-row effect
# ==============================================================================

class TestSubmitDisciplineDepth:
    def test_writes_sync_log_for_incident(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        inc = call_action(DISC_ACTIONS["statereport-add-discipline-incident"], conn, ns(
            company_id=cid, school_year=2025,
            incident_date="2025-10-15", incident_type="weapons_other",
            incident_time=None, incident_description=None,
            campus_location=None, reported_by=None, user_id="admin",
        ))
        assert is_ok(inc)
        # No ledger effect: this action only appends sr_edfi_sync_log rows.
        r = call_action(EDFI_ACTIONS["statereport-submit-discipline-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            school_year=2025, collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["synced_count"] == 1
        logs = _logs_for_company(conn, cid)
        assert len(logs) == 1
        assert logs[0]["resource_type"] == "disciplineIncidents"
        assert logs[0]["internal_id"] == inc["id"]
        assert logs[0]["sync_status"] == "pending"
        assert json.loads(logs[0]["edfi_natural_key"])["incidentIdentifier"] == inc["naming_series"]

    def test_refusal_missing_company_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-discipline-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=None,
            school_year=2025, collection_window_id=None,
        ))
        assert is_error(r)
        assert "company-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 6. statereport-submit-staff-to-edfi — stored-row effect
# ==============================================================================

class TestSubmitStaffDepth:
    def test_syncs_only_active_instructors(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        emp_active = _seed_employee(conn, cid, "Ada", "Lovelace")
        _seed_instructor(conn, emp_active, cid, active=1)
        emp_idle = _seed_employee(conn, cid, "Grace", "Hopper")
        _seed_instructor(conn, emp_idle, cid, active=0)
        # No ledger effect: this action only appends sr_edfi_sync_log rows.
        r = call_action(EDFI_ACTIONS["statereport-submit-staff-to-edfi"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["synced_count"] == 1
        logs = _logs_for_company(conn, cid)
        assert len(logs) == 1
        assert logs[0]["resource_type"] == "staffs"
        assert logs[0]["internal_id"] == emp_active
        assert logs[0]["sync_status"] == "pending"
        # Inactive instructor must NOT be synced.
        assert all(l["internal_id"] != emp_idle for l in logs)

    def test_refusal_missing_config_writes_nothing(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-staff-to-edfi"], conn, ns(
            config_id=None, company_id=cid, collection_window_id=None,
        ))
        assert is_error(r)
        assert "config-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 7. statereport-list-edfi-sync-errors — stored-row (filter) effect
# ==============================================================================

class TestListEdFiSyncErrorsDepth:
    def test_returns_only_pending_error_retry(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        cfg = s["edfi_config_id"]
        lp = _seed_sync_log(conn, cfg, cid, "pending", "int-pending")
        le = _seed_sync_log(conn, cfg, cid, "error", "int-error")
        lr = _seed_sync_log(conn, cfg, cid, "retry", "int-retry")
        ls = _seed_sync_log(conn, cfg, cid, "success", "int-success")
        before = _dump(conn, "sr_edfi_sync_log")
        # No ledger effect: read-only list over sr_edfi_sync_log.
        r = call_action(EDFI_ACTIONS["statereport-list-edfi-sync-errors"], conn, ns(
            company_id=cid, collection_window_id=None, limit=100, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 3
        assert sorted(e["internal_id"] for e in r["errors"]) == ["int-error", "int-pending", "int-retry"]
        assert "int-success" not in [e["internal_id"] for e in r["errors"]]
        assert {e["sync_status"] for e in r["errors"]} == {"pending", "error", "retry"}
        # Listing changed nothing.
        assert _dump(conn, "sr_edfi_sync_log") == before

    def test_no_refusal_path_documented(self, full_setup):
        # FINDING (deliberately not fixed): list-edfi-sync-errors performs no
        # input validation at all — every parameter is optional, so there is no
        # refusal to test. This documents that a call with no filters succeeds
        # and writes nothing, rather than refusing.
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-list-edfi-sync-errors"], conn, ns(
            company_id=cid, collection_window_id=None, limit=100, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 0
        assert _dump_all(conn) == before


# ==============================================================================
# 8. statereport-list-snapshot-records — stored-row effect
# ==============================================================================

class TestListSnapshotRecordsDepth:
    def test_returns_frozen_enrollment_record(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        pid = _seed_program(conn, cid, s["year_id"])
        _seed_enrollment(conn, s["student_id"], pid, s["year_id"], cid)
        wid2 = seed_collection_window(conn, cid, s["year_id"])
        snap = call_action(SR_ACTIONS["statereport-create-snapshot"], conn, ns(
            window_id=wid2, user_id="admin",
        ))
        assert is_ok(snap)
        before = _dump(conn, "sr_snapshot_record")
        # No ledger effect: read-only list over sr_snapshot_record.
        r = call_action(SR_ACTIONS["statereport-list-snapshot-records"], conn, ns(
            snapshot_id=snap["id"], record_type=None, limit=100, offset=0,
        ))
        assert is_ok(r)
        assert r["count"] == 1
        rec = r["records"][0]
        assert rec["student_id"] == s["student_id"]
        assert rec["record_type"] == "student_enrollment"
        assert rec["school_year"] == 2025
        assert rec["company_id"] == cid
        data = rec["data_json"]
        assert data["enrollment_status"] == "active"
        assert data["ssid"] == "SSN12345"
        assert data["race_federal_rollup"] == "WHITE"
        # Listing changed nothing.
        assert _dump(conn, "sr_snapshot_record") == before

    def test_refusal_missing_snapshot_id_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(SR_ACTIONS["statereport-list-snapshot-records"], conn, ns(
            snapshot_id=None, record_type=None, limit=100, offset=0,
        ))
        assert is_error(r)
        assert "snapshot-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 9. statereport-update-collection-window — stored-row effect
# ==============================================================================

class TestUpdateCollectionWindowDepth:
    def test_updates_description_leaves_rest(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _read_row(conn, "sr_collection_window", s["window_id"])
        assert before["description"] == "Test window"
        assert before["status"] == "upcoming"
        # No ledger effect: single-row UPDATE on sr_collection_window.
        r = call_action(SR_ACTIONS["statereport-update-collection-window"], conn, ns(
            window_id=s["window_id"], name=None, open_date=None,
            close_date=None, snapshot_date=None,
            description="Updated description", is_federal_required=None,
            edfi_config_id=None, required_data_categories=None,
            user_id="admin",
        ))
        assert is_ok(r)
        after = _read_row(conn, "sr_collection_window", s["window_id"])
        assert after["description"] == "Updated description"
        assert before["description"] == "Test window"
        assert after["status"] == "upcoming"
        assert after["name"] == before["name"]
        assert after["open_date"] == before["open_date"]
        assert after["close_date"] == before["close_date"]
        assert after["snapshot_date"] == before["snapshot_date"]

    def test_refusal_missing_window_id_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(SR_ACTIONS["statereport-update-collection-window"], conn, ns(
            window_id=None, name=None, open_date=None,
            close_date=None, snapshot_date=None,
            description="Updated description", is_federal_required=None,
            edfi_config_id=None, required_data_categories=None,
            user_id="admin",
        ))
        assert is_error(r)
        assert "window-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 10. statereport-update-descriptor-mapping — stored-row effect
# ==============================================================================

class TestUpdateDescriptorMappingDepth:
    def test_updates_uri_description_active(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        add_r = call_action(EDFI_ACTIONS["statereport-add-descriptor-mapping"], conn, ns(
            config_id=s["edfi_config_id"], company_id=cid,
            descriptor_type="grade_level", internal_code="K",
            edfi_descriptor_uri="uri://ed-fi.org/GradeLevelDescriptor#Kindergarten",
            description="Kindergarten", user_id="admin",
        ))
        assert is_ok(add_r)
        before = _read_row(conn, "sr_edfi_descriptor_map", add_r["id"])
        assert before["is_active"] == 1
        # No ledger effect: single-row UPDATE on sr_edfi_descriptor_map.
        r = call_action(EDFI_ACTIONS["statereport-update-descriptor-mapping"], conn, ns(
            desc_id=add_r["id"],
            edfi_descriptor_uri="uri://ed-fi.org/GradeLevelDescriptor#FirstGrade",
            description="Updated desc", is_active=0, user_id="admin",
        ))
        assert is_ok(r)
        after = _read_row(conn, "sr_edfi_descriptor_map", add_r["id"])
        assert after["edfi_descriptor_uri"] == "uri://ed-fi.org/GradeLevelDescriptor#FirstGrade"
        assert before["edfi_descriptor_uri"] == "uri://ed-fi.org/GradeLevelDescriptor#Kindergarten"
        assert after["description"] == "Updated desc"
        assert after["is_active"] == 0
        assert after["descriptor_type"] == before["descriptor_type"] == "grade_level"
        assert after["internal_code"] == before["internal_code"] == "K"
        assert after["config_id"] == before["config_id"]

    def test_refusal_missing_desc_id_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-update-descriptor-mapping"], conn, ns(
            desc_id=None, edfi_descriptor_uri="uri://x#Y",
            description=None, is_active=None, user_id="admin",
        ))
        assert is_error(r)
        assert "desc-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 11. statereport-submit-error-escalation — stored-row effect
# ==============================================================================

class TestSubmitErrorEscalationDepth:
    def test_marks_in_progress_with_ticket(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        eid = _seed_error(conn, s["window_id"], cid, s["student_id"])
        before = _read_row(conn, "sr_submission_error", eid)
        assert before["resolution_status"] == "open"
        assert before["state_ticket_id"] == ""
        # No ledger effect: single-row UPDATE on sr_submission_error.
        r = call_action(DV_ACTIONS["statereport-submit-error-escalation"], conn, ns(
            error_id=eid, state_ticket_id="ST-12345", user_id="admin",
        ))
        assert is_ok(r)
        after = _read_row(conn, "sr_submission_error", eid)
        assert after["state_ticket_id"] == "ST-12345"
        assert after["resolution_status"] == "in_progress"
        assert after["error_message"] == before["error_message"]
        assert after["error_category"] == before["error_category"]
        assert after["severity"] == before["severity"]

    def test_refusal_missing_error_id_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(DV_ACTIONS["statereport-submit-error-escalation"], conn, ns(
            error_id=None, state_ticket_id="ST-12345", user_id="admin",
        ))
        assert is_error(r)
        assert "error-id" in r["message"].lower()
        assert _dump_all(conn) == before


# ==============================================================================
# 12. statereport-submit-failed-syncs — stored-row effect
# ==============================================================================

class TestSubmitFailedSyncsDepth:
    def test_retries_only_error_and_retry(self, full_setup):
        s = full_setup
        conn, cid = s["conn"], s["company_id"]
        cfg = s["edfi_config_id"]
        le = _seed_sync_log(conn, cfg, cid, "error", "int-error", retry_count=0)
        lr = _seed_sync_log(conn, cfg, cid, "retry", "int-retry", retry_count=2)
        lp = _seed_sync_log(conn, cfg, cid, "pending", "int-pending", retry_count=0)
        ls = _seed_sync_log(conn, cfg, cid, "success", "int-success", retry_count=0)
        # No ledger effect: UPDATEs sr_edfi_sync_log retry state only.
        r = call_action(EDFI_ACTIONS["statereport-submit-failed-syncs"], conn, ns(
            company_id=cid, collection_window_id=None,
        ))
        assert is_ok(r)
        assert r["retried_count"] == 2
        after_e = _read_row(conn, "sr_edfi_sync_log", le)
        after_r = _read_row(conn, "sr_edfi_sync_log", lr)
        after_p = _read_row(conn, "sr_edfi_sync_log", lp)
        after_s = _read_row(conn, "sr_edfi_sync_log", ls)
        assert (after_e["sync_status"], after_e["retry_count"]) == ("retry", 1)
        assert (after_r["sync_status"], after_r["retry_count"]) == ("retry", 3)
        assert (after_p["sync_status"], after_p["retry_count"]) == ("pending", 0)
        assert (after_s["sync_status"], after_s["retry_count"]) == ("success", 0)

    def test_refusal_missing_company_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _dump_all(conn)
        r = call_action(EDFI_ACTIONS["statereport-submit-failed-syncs"], conn, ns(
            company_id=None, collection_window_id=None,
        ))
        assert is_error(r)
        assert "company-id" in r["message"].lower()
        assert _dump_all(conn) == before
