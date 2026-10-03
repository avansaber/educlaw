"""M709: every statereport audit row names the skill, the action, the table and the record.

Product rule: an audit row carries skill = "statereport-educlaw-statereport",
action = the statereport-* action name, entity_type = the record's table and
entity_id = that record's id, so a record's trail is found under its own id.
Reads go through PyPika (erpclaw_lib.query) with bound parameters.
"""
import importlib.util
import json
import os
import sys
import uuid

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

from erpclaw_lib.query import Q, P, Table, Field

call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student
seed_academic_year = _helpers.seed_academic_year
seed_collection_window = _helpers.seed_collection_window
seed_edfi_config = _helpers.seed_edfi_config
seed_supplement = _helpers.seed_supplement

SUB = _load("submission_tracking", _SCRIPTS_DIR).ACTIONS
DV = _load("data_validation", _SCRIPTS_DIR).ACTIONS
DEMO = _load("demographics", _SCRIPTS_DIR).ACTIONS
DISC = _load("discipline", _SCRIPTS_DIR).ACTIONS
EDFI = _load("ed_fi", _SCRIPTS_DIR).ACTIONS
SR = _load("state_reporting", _SCRIPTS_DIR).ACTIONS

SKILL = "statereport-educlaw-statereport"


@pytest.fixture
def env(db_path):
    conn = _helpers.get_conn(db_path)
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


def _audit_rows_for(conn, entity_id):
    """Audit rows for one record id, via a PyPika select with a bound parameter."""
    tbl = Table("audit_log")
    sql = Q.from_(tbl).select(
        Field("skill"), Field("action"), Field("entity_type"),
        Field("entity_id"), Field("new_values"),
    ).where(Field("entity_id") == P()).get_sql()
    return [dict(r) for r in conn.execute(sql, (entity_id,)).fetchall()]


def _all_audit_rows(conn):
    tbl = Table("audit_log")
    sql = Q.from_(tbl).select(
        Field("skill"), Field("action"), Field("entity_type"),
        Field("entity_id"), Field("new_values"),
    ).get_sql()
    return [dict(r) for r in conn.execute(sql).fetchall()]


def _single_audit(conn, entity_id):
    rows = _audit_rows_for(conn, entity_id)
    assert len(rows) == 1, f"expected exactly one audit row for {entity_id}, got {len(rows)}"
    return rows[0]


# ---------------------------------------------------------------------------
# Direct seeds (no audit row) for records that update/delete actions need.
# ---------------------------------------------------------------------------

def _seed_submission(conn, window_id, company_id, status="pending"):
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_submission
           (id, naming_series, collection_window_id, submission_type,
            submission_method, submission_status, company_id)
           VALUES (?, ?, ?, 'initial', 'flat_file', ?, ?)""",
        (sid, f"SUB-{sid[:8]}", window_id, status, company_id))
    conn.commit()
    return sid


def _seed_rule(conn):
    rid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sr_validation_rule (id, rule_code, category, severity, name)"
        " VALUES (?, ?, 'demographics', 'major', 'Seeded rule')",
        (rid, f"RULE-{rid[:8]}"))
    conn.commit()
    return rid


def _seed_error(conn, window_id, company_id, student_id):
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_submission_error
           (id, collection_window_id, error_source, error_level, severity,
            error_code, error_category, error_message, student_id,
            resolution_status, resolution_method, state_ticket_id, company_id)
           VALUES (?, ?, 'internal_validation', '1', 'major',
                   ?, 'demographics', 'Seeded error', ?,
                   'open', '', '', ?)""",
        (eid, window_id, f"E-{eid[:8]}", student_id, company_id))
    conn.commit()
    return eid


def _seed_placement(conn, student_id, company_id):
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_sped_placement
           (id, student_id, school_year, disability_category,
            educational_environment, company_id)
           VALUES (?, ?, 2025, 'AUT', 'RC_80', ?)""",
        (pid, student_id, company_id))
    conn.commit()
    return pid


def _seed_service(conn, placement_id, student_id, company_id):
    svc = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_sped_service
           (id, sped_placement_id, student_id, service_type, provider_type,
            minutes_per_week, company_id)
           VALUES (?, ?, ?, 'speech_language', 'school_employed', 60, ?)""",
        (svc, placement_id, student_id, company_id))
    conn.commit()
    return svc


def _seed_el_program(conn, student_id, company_id):
    prog = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_el_program
           (id, student_id, school_year, program_type, entry_date, company_id)
           VALUES (?, ?, 2025, 'pull_out', '2024-09-01', ?)""",
        (prog, student_id, company_id))
    conn.commit()
    return prog


def _seed_incident(conn, company_id):
    iid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_discipline_incident
           (id, naming_series, company_id, school_year, incident_date, incident_type)
           VALUES (?, ?, ?, 2025, '2025-10-15', 'bullying')""",
        (iid, f"INC-{iid[:8]}", company_id))
    conn.commit()
    return iid


def _seed_ds(conn, incident_id, student_id, company_id):
    dsid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_discipline_student
           (id, incident_id, student_id, role, company_id)
           VALUES (?, ?, ?, 'offender', ?)""",
        (dsid, incident_id, student_id, company_id))
    conn.commit()
    return dsid


def _seed_action(conn, ds_id, incident_id, student_id, company_id):
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_discipline_action
           (id, discipline_student_id, incident_id, student_id, action_type, company_id)
           VALUES (?, ?, ?, ?, 'oss_1_10', ?)""",
        (aid, ds_id, incident_id, student_id, company_id))
    conn.commit()
    return aid


def _seed_mapping(conn, company_id):
    mid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_org_mapping (id, company_id, state_code, nces_lea_id)
           VALUES (?, ?, 'CA', ?)""",
        (mid, company_id, f"LEA-{mid[:8]}"))
    conn.commit()
    return mid


def _seed_config(conn, company_id, state_code, school_year, profile_name):
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_edfi_config
           (id, profile_name, state_code, school_year, ods_base_url,
            oauth_client_id, company_id)
           VALUES (?, ?, ?, ?, 'https://edfi.test.edu/api/v7', 'seed-client', ?)""",
        (cid, profile_name, state_code, school_year, company_id))
    conn.commit()
    return cid


def _seed_descriptor(conn, config_id, company_id, code):
    did = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_edfi_descriptor_map
           (id, config_id, descriptor_type, internal_code, edfi_descriptor_uri, company_id)
           VALUES (?, ?, 'grade_level', ?, 'uri://ed-fi.org/GradeLevelDescriptor#Seeded', ?)""",
        (did, config_id, code, company_id))
    conn.commit()
    return did


# ---------------------------------------------------------------------------
# One test per product file: drive each audit-writing action once.
# ---------------------------------------------------------------------------

class TestSubmissionTrackingAuditRows:
    def test_each_action_names_skill_action_table_and_record(self, env):
        conn, cid = env["conn"], env["company_id"]
        wid = env["window_id"]

        r = call_action(SUB["statereport-add-submission"], conn, ns(
            window_id=wid, company_id=cid,
            submission_type="initial", submission_method="flat_file",
            snapshot_id=None, linked_submission_id=None,
            submitted_at=None, submitted_by=None,
            records_submitted=None, records_accepted=None,
            records_rejected=None,
            state_confirmation_id=None, state_confirmed_at=None,
            amendment_reason=None, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-submission", "sr_submission")

        sub2 = _seed_submission(conn, wid, cid)
        r = call_action(SUB["statereport-update-submission-status"], conn, ns(
            submission_id=sub2, submission_status="completed",
            records_submitted=None, records_accepted=48,
            records_rejected=2,
            state_confirmation_id="CONF-123",
            state_confirmed_at=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, sub2)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-submission-status", "sr_submission")

        sub3 = _seed_submission(conn, wid, cid)
        r = call_action(SUB["statereport-approve-submission"], conn, ns(
            submission_id=sub3, certified_by="certifier-1",
            certification_notes="Approved", user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, sub3)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-approve-submission", "sr_submission")

        sub4 = _seed_submission(conn, wid, cid)
        r = call_action(SUB["statereport-create-amendment"], conn, ns(
            original_submission_id=sub4,
            amendment_reason="Corrected dates",
            company_id=cid,
            submission_method=None, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-create-amendment", "sr_submission")


class TestDataValidationAuditRows:
    def test_each_action_names_skill_action_table_and_record(self, env):
        conn, cid = env["conn"], env["company_id"]
        wid, sid = env["window_id"], env["student_id"]

        r = call_action(DV["statereport-add-validation-rule"], conn, ns(
            rule_code="AUDIT-R1", category="demographics", severity="major",
            name="Audit Rule", description="Before",
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-validation-rule", "sr_validation_rule")

        rule2 = _seed_rule(conn)
        r = call_action(DV["statereport-update-validation-rule"], conn, ns(
            rule_id=rule2, rule_code=None,
            category=None, severity="critical", name="Renamed",
            description="After",
            applicable_windows=None, applicable_states=None,
            is_federal_rule=None, sql_query=None,
            error_message_template=None, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, rule2)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-validation-rule", "sr_validation_rule")

        err1 = _seed_error(conn, wid, cid, sid)
        r = call_action(DV["statereport-assign-submission-error"], conn, ns(
            error_id=err1, assigned_to="counselor-1", user_id=None))
        assert is_ok(r), r
        row = _single_audit(conn, err1)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-assign-submission-error", "sr_submission_error")

        err2 = _seed_error(conn, wid, cid, sid)
        r = call_action(DV["statereport-update-error-resolution"], conn, ns(
            error_id=err2, resolution_status="in_progress",
            resolution_method="data_corrected",
            resolution_notes="Fixed in SIS",
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, err2)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-error-resolution", "sr_submission_error")

        err3 = _seed_error(conn, wid, cid, sid)
        r = call_action(DV["statereport-submit-error-escalation"], conn, ns(
            error_id=err3, state_ticket_id="ST-12345", user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, err3)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-submit-error-escalation", "sr_submission_error")


class TestDemographicsAuditRows:
    def test_each_action_names_skill_action_table_and_record(self, env):
        conn, cid = env["conn"], env["company_id"]

        stu_a = seed_student(conn, cid)
        r = call_action(DEMO["statereport-add-student-supplement"], conn, ns(
            student_id=stu_a, company_id=cid,
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
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-student-supplement", "sr_student_supplement")

        stu_b = seed_student(conn, cid)
        supp_b = seed_supplement(conn, stu_b, cid)
        r = call_action(DEMO["statereport-update-student-supplement"], conn, ns(
            supplement_id=supp_b, student_id=None,
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
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, supp_b)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-student-supplement", "sr_student_supplement")

        stu_c = seed_student(conn, cid)
        supp_c = seed_supplement(conn, stu_c, cid)
        r = call_action(DEMO["statereport-assign-ssid"], conn, ns(
            student_id=stu_c, ssid="NEW-SSID-999",
            ssid_state_code="CA", user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, supp_c)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-assign-ssid", "sr_student_supplement")

        stu_d = seed_student(conn, cid)
        supp_d = seed_supplement(conn, stu_d, cid)
        r = call_action(DEMO["statereport-update-student-race"], conn, ns(
            student_id=stu_d,
            race_codes='["BLACK","ASIAN"]', is_hispanic_latino=0,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, supp_d)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-student-race", "sr_student_supplement")

        stu_e = seed_student(conn, cid)
        supp_e = seed_supplement(conn, stu_e, cid)
        r = call_action(DEMO["statereport-update-el-status"], conn, ns(
            student_id=stu_e,
            is_el=1, el_entry_date="2024-09-01",
            home_language_code="spa", native_language_code="spa",
            english_proficiency_level="3",
            english_proficiency_instrument="ELPAC",
            el_exit_date=None, is_rfep=None, rfep_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, supp_e)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-el-status", "sr_student_supplement")

        stu_f = seed_student(conn, cid)
        supp_f = seed_supplement(conn, stu_f, cid)
        r = call_action(DEMO["statereport-update-sped-status"], conn, ns(
            student_id=stu_f,
            is_sped=1, is_504=0,
            sped_entry_date="2023-01-15", sped_exit_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, supp_f)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-sped-status", "sr_student_supplement")

        stu_g = seed_student(conn, cid)
        supp_g = seed_supplement(conn, stu_g, cid)
        r = call_action(DEMO["statereport-update-economic-status"], conn, ns(
            student_id=stu_g,
            is_economically_disadvantaged=1, lunch_program_status="free",
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, supp_g)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-economic-status", "sr_student_supplement")

        stu_h = seed_student(conn, cid)
        r = call_action(DEMO["statereport-add-sped-placement"], conn, ns(
            student_id=stu_h, school_year=2025,
            disability_category="SLD", educational_environment="RC_80",
            company_id=cid,
            secondary_disability=None,
            sped_program_entry_date="2024-09-01", sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date="2024-09-01", iep_review_date="2025-09-01",
            is_transition_plan_required=0, lre_percentage="85",
            is_early_childhood=0, early_childhood_environment=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-sped-placement", "sr_sped_placement")

        stu_i = seed_student(conn, cid)
        pl_i = _seed_placement(conn, stu_i, cid)
        r = call_action(DEMO["statereport-update-sped-placement"], conn, ns(
            placement_id=pl_i,
            disability_category="SLD", secondary_disability=None,
            educational_environment=None,
            sped_program_entry_date=None, sped_program_exit_date=None,
            sped_exit_reason=None,
            iep_start_date=None, iep_review_date=None,
            is_transition_plan_required=None, lre_percentage=None,
            is_early_childhood=None, early_childhood_environment=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, pl_i)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-sped-placement", "sr_sped_placement")

        stu_j = seed_student(conn, cid)
        pl_j = _seed_placement(conn, stu_j, cid)
        r = call_action(DEMO["statereport-add-sped-service"], conn, ns(
            sped_placement_id=pl_j, student_id=None,
            service_type="speech_language", provider_type="school_employed",
            minutes_per_week=60,
            start_date="2024-09-01", end_date="2025-06-30",
            company_id=cid, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-sped-service", "sr_sped_service")

        stu_k = seed_student(conn, cid)
        pl_k = _seed_placement(conn, stu_k, cid)
        svc_k = _seed_service(conn, pl_k, stu_k, cid)
        r = call_action(DEMO["statereport-update-sped-service"], conn, ns(
            service_id=svc_k,
            service_type=None, provider_type="contracted",
            minutes_per_week=90, start_date=None, end_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, svc_k)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-sped-service", "sr_sped_service")

        stu_m = seed_student(conn, cid)
        pl_m = _seed_placement(conn, stu_m, cid)
        svc_m = _seed_service(conn, pl_m, stu_m, cid)
        r = call_action(DEMO["statereport-delete-sped-service"], conn, ns(
            service_id=svc_m, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, svc_m)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-delete-sped-service", "sr_sped_service")

        stu_n = seed_student(conn, cid)
        r = call_action(DEMO["statereport-add-el-program"], conn, ns(
            student_id=stu_n, school_year=2025,
            program_type="sheltered_english", entry_date="2024-09-01",
            company_id=cid,
            exit_date=None, exit_reason=None,
            english_proficiency_assessed_date="2024-08-15",
            proficiency_level="3", proficiency_instrument="ELPAC",
            is_parent_waived=0, waiver_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-el-program", "sr_el_program")

        stu_p = seed_student(conn, cid)
        prog_p = _seed_el_program(conn, stu_p, cid)
        r = call_action(DEMO["statereport-update-el-program"], conn, ns(
            el_program_id=prog_p,
            program_type="push_in", entry_date=None,
            exit_date=None, exit_reason=None,
            english_proficiency_assessed_date=None,
            proficiency_level=None, proficiency_instrument=None,
            is_parent_waived=None, waiver_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, prog_p)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-el-program", "sr_el_program")


class TestDisciplineAuditRows:
    def test_each_action_names_skill_action_table_and_record(self, env):
        conn, cid = env["conn"], env["company_id"]
        sid = env["student_id"]

        r = call_action(DISC["statereport-add-discipline-incident"], conn, ns(
            company_id=cid, school_year=2025,
            incident_date="2025-10-15", incident_type="bullying",
            incident_time="10:30", incident_description="Hallway bullying",
            campus_location="hallway", reported_by="teacher1",
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-discipline-incident", "educlaw_k12_discipline_incident")

        inc_u = _seed_incident(conn, cid)
        r = call_action(DISC["statereport-update-discipline-incident"], conn, ns(
            incident_id=inc_u,
            incident_type=None, incident_description="Updated desc",
            campus_location=None, incident_date=None, incident_time=None,
            reported_by=None, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, inc_u)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-discipline-incident", "educlaw_k12_discipline_incident")

        inc_d = _seed_incident(conn, cid)
        r = call_action(DISC["statereport-delete-discipline-incident"], conn, ns(
            incident_id=inc_d, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, inc_d)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-delete-discipline-incident", "educlaw_k12_discipline_incident")

        inc_s = _seed_incident(conn, cid)
        r = call_action(DISC["statereport-add-discipline-student"], conn, ns(
            incident_id=inc_s, student_id=sid,
            role="offender", company_id=cid,
            is_idea_student=None, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-discipline-student", "educlaw_k12_discipline_student")

        inc_su = _seed_incident(conn, cid)
        ds_su = _seed_ds(conn, inc_su, sid, cid)
        r = call_action(DISC["statereport-update-discipline-student"], conn, ns(
            discipline_student_id=ds_su, role="victim",
            is_idea_student=None, is_504_student=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, ds_su)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-discipline-student", "educlaw_k12_discipline_student")

        inc_sr = _seed_incident(conn, cid)
        ds_sr = _seed_ds(conn, inc_sr, sid, cid)
        r = call_action(DISC["statereport-delete-discipline-student"], conn, ns(
            discipline_student_id=ds_sr, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, ds_sr)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-delete-discipline-student", "educlaw_k12_discipline_student")

        inc_a = _seed_incident(conn, cid)
        ds_a = _seed_ds(conn, inc_a, sid, cid)
        r = call_action(DISC["statereport-add-discipline-action"], conn, ns(
            discipline_student_id=ds_a, action_type="oss_1_10",
            company_id=cid,
            days_removed=5, start_date="2025-10-16", end_date="2025-10-21",
            alternative_services_provided=1,
            alternative_services_description="Homework packets",
            mdr_required=None, mdr_outcome=None, mdr_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-discipline-action", "educlaw_k12_discipline_action")

        inc_au = _seed_incident(conn, cid)
        ds_au = _seed_ds(conn, inc_au, sid, cid)
        act_au = _seed_action(conn, ds_au, inc_au, sid, cid)
        r = call_action(DISC["statereport-update-discipline-action"], conn, ns(
            action_id=act_au,
            action_type=None, start_date=None, end_date="2025-10-22",
            days_removed=None,
            alternative_services_provided=None,
            alternative_services_description=None,
            mdr_required=None, mdr_outcome=None, mdr_date=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, act_au)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-discipline-action", "educlaw_k12_discipline_action")

        inc_m = _seed_incident(conn, cid)
        ds_m = _seed_ds(conn, inc_m, sid, cid)
        act_m = _seed_action(conn, ds_m, inc_m, sid, cid)
        r = call_action(DISC["statereport-record-mdr-outcome"], conn, ns(
            action_id=act_m, mdr_outcome="not_manifestation",
            mdr_date="2025-10-25", user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, act_m)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-record-mdr-outcome", "educlaw_k12_discipline_action")


class TestEdFiAuditRows:
    def test_each_action_names_skill_action_table_and_record(self, env):
        conn, cid = env["conn"], env["company_id"]

        r = call_action(EDFI["statereport-add-edfi-config"], conn, ns(
            company_id=cid, profile_name="TX Ed-Fi Audit",
            state_code="TX", school_year=2024,
            ods_base_url="https://edfi.test.edu/api/v7",
            oauth_token_url="https://edfi.test.edu/oauth/token",
            oauth_client_id="client-123",
            oauth_client_secret="secret-456",
            api_version="7", is_active=None,
            user_id=None,
        ))
        assert is_ok(r), r
        cfg_tx = r["id"]
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-edfi-config", "sr_edfi_config")

        cfg_u = _seed_config(conn, cid, "NY", 2025, "Seeded Update")
        r = call_action(EDFI["statereport-update-edfi-config"], conn, ns(
            config_id=cfg_u,
            profile_name="Renamed Profile", state_code=None,
            ods_base_url=None, oauth_token_url=None,
            oauth_client_id=None, oauth_client_secret=None,
            api_version=None, is_active=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, cfg_u)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-edfi-config", "sr_edfi_config")

        cfg_t = _seed_config(conn, cid, "CA", 2024, "Seeded Conn Test")
        r = call_action(EDFI["statereport-get-edfi-connection-test"], conn, ns(
            config_id=cfg_t, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, cfg_t)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-get-edfi-connection-test", "sr_edfi_config")

        r = call_action(EDFI["statereport-add-org-mapping"], conn, ns(
            company_id=cid, state_code="CA",
            nces_lea_id="0600001", nces_school_id="060000100001",
            state_lea_id="CA-001", state_school_id="CA-001-001",
            edfi_lea_id=None, edfi_school_id=None,
            crdc_school_id=None,
            is_title_i_school=1, title_i_status="schoolwide",
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-org-mapping", "sr_org_mapping")

        map_u = _seed_mapping(conn, cid)
        r = call_action(EDFI["statereport-update-org-mapping"], conn, ns(
            mapping_id=map_u,
            nces_lea_id=None, nces_school_id=None,
            state_lea_id=None, state_school_id=None,
            edfi_lea_id=None, edfi_school_id=None,
            crdc_school_id=None,
            is_title_i_school=None, title_i_status="targeted_assistance",
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, map_u)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-org-mapping", "sr_org_mapping")

        cfg_d = cfg_tx
        r = call_action(EDFI["statereport-add-descriptor-mapping"], conn, ns(
            config_id=cfg_d, company_id=cid,
            descriptor_type="grade_level", internal_code="K",
            edfi_descriptor_uri="uri://ed-fi.org/GradeLevelDescriptor#Kindergarten",
            description="Kindergarten",
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-descriptor-mapping", "sr_edfi_descriptor_map")

        desc_du = _seed_descriptor(conn, cfg_tx, cid, "KU")
        r = call_action(EDFI["statereport-update-descriptor-mapping"], conn, ns(
            desc_id=desc_du,
            edfi_descriptor_uri="uri://ed-fi.org/GradeLevelDescriptor#Updated",
            description=None, is_active=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, desc_du)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-descriptor-mapping", "sr_edfi_descriptor_map")

        desc_dd = _seed_descriptor(conn, cfg_tx, cid, "KD")
        r = call_action(EDFI["statereport-delete-descriptor-mapping"], conn, ns(
            desc_id=desc_dd, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, desc_dd)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-delete-descriptor-mapping", "sr_edfi_descriptor_map")


class TestStateReportingAuditRows:
    def test_each_action_names_skill_action_table_and_record(self, env):
        conn, cid = env["conn"], env["company_id"]
        yid = env["year_id"]

        r = call_action(SR["statereport-add-collection-window"], conn, ns(
            company_id=cid, name="EOY Discipline 2026",
            state_code="CA", window_type="eoy_discipline",
            school_year=2026, academic_year_id=yid,
            open_date="2025-07-01", close_date="2025-08-15",
            snapshot_date="2025-06-30",
            description="End of year discipline collection",
            required_data_categories='["discipline"]',
            is_federal_required=0, edfi_config_id=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-add-collection-window", "sr_collection_window")

        win_u = seed_collection_window(conn, cid, yid)
        r = call_action(SR["statereport-update-collection-window"], conn, ns(
            window_id=win_u,
            name=None, open_date=None, close_date=None, snapshot_date=None,
            description="Updated description", is_federal_required=None,
            edfi_config_id=None, required_data_categories=None,
            user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, win_u)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-update-collection-window", "sr_collection_window")

        win_a = seed_collection_window(conn, cid, yid)
        r = call_action(SR["statereport-apply-window-status"], conn, ns(
            window_id=win_a, user_id=None,
        ))
        assert is_ok(r), r
        row = _single_audit(conn, win_a)
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-apply-window-status", "sr_collection_window")

        win_s = seed_collection_window(conn, cid, yid)
        r = call_action(SR["statereport-create-snapshot"], conn, ns(
            window_id=win_s, user_id="snapshot-user",
        ))
        assert is_ok(r), r
        row = _single_audit(conn, r["id"])
        assert (row["skill"], row["action"], row["entity_type"]) == (
            "statereport-educlaw-statereport", "statereport-create-snapshot", "sr_snapshot")


def test_no_audit_row_uses_a_verb_or_a_table_as_its_name(env):
    conn, cid = env["conn"], env["company_id"]
    yid = env["year_id"]
    sid = env["student_id"]

    sub = call_action(SUB["statereport-add-submission"], conn, ns(
        window_id=env["window_id"], company_id=cid,
        submission_type="initial", submission_method="flat_file",
        snapshot_id=None, linked_submission_id=None,
        submitted_at=None, submitted_by=None,
        records_submitted=None, records_accepted=None,
        records_rejected=None,
        state_confirmation_id=None, state_confirmed_at=None,
        amendment_reason=None, user_id=None,
    ))
    assert is_ok(sub), sub

    rule = call_action(DV["statereport-add-validation-rule"], conn, ns(
        rule_code="AUDIT-R9", category="demographics", severity="major",
        name="Audit Rule", description="Before",
        applicable_windows=None, applicable_states=None,
        is_federal_rule=None, sql_query=None,
        error_message_template=None, user_id=None,
    ))
    assert is_ok(rule), rule

    stu = seed_student(conn, cid)
    supp = call_action(DEMO["statereport-add-student-supplement"], conn, ns(
        student_id=stu, company_id=cid,
        ssid="SS123456", ssid_state_code="CA", ssid_status="assigned",
        is_hispanic_latino=0, race_codes='["WHITE"]',
        is_el=0, el_entry_date=None, home_language_code=None,
        native_language_code=None, english_proficiency_level=None,
        english_proficiency_instrument=None, el_exit_date=None,
        is_rfep=None, rfep_date=None,
        is_sped=0, is_504=0, sped_entry_date=None, sped_exit_date=None,
        is_economically_disadvantaged=0, lunch_program_status=None,
        is_migrant=0, is_homeless=0, homeless_primary_nighttime_residence=None,
        is_foster_care=0, is_military_connected=0, military_connection_type=None,
        user_id=None,
    ))
    assert is_ok(supp), supp

    inc = call_action(DISC["statereport-add-discipline-incident"], conn, ns(
        company_id=cid, school_year=2025,
        incident_date="2025-10-15", incident_type="bullying",
        incident_time=None, incident_description=None,
        campus_location=None, reported_by=None,
        user_id=None,
    ))
    assert is_ok(inc), inc

    cfg = call_action(EDFI["statereport-add-edfi-config"], conn, ns(
        company_id=cid, profile_name="TX Ed-Fi Audit",
        state_code="TX", school_year=2024,
        ods_base_url="https://edfi.test.edu/api/v7",
        oauth_token_url="https://edfi.test.edu/oauth/token",
        oauth_client_id="client-123",
        oauth_client_secret="secret-456",
        api_version="7", is_active=None,
        user_id=None,
    ))
    assert is_ok(cfg), cfg

    win = call_action(SR["statereport-add-collection-window"], conn, ns(
        company_id=cid, name="EOY Discipline 2026",
        state_code="CA", window_type="eoy_discipline",
        school_year=2026, academic_year_id=yid,
        open_date="2025-07-01", close_date="2025-08-15",
        snapshot_date="2025-06-30",
        description="End of year discipline collection",
        required_data_categories='["discipline"]',
        is_federal_required=0, edfi_config_id=None,
        user_id=None,
    ))
    assert is_ok(win), win

    rows = _all_audit_rows(conn)
    assert len(rows) == 6, f"expected 6 audit rows, got {len(rows)}"
    for row in rows:
        assert row["entity_type"] not in ("INSERT", "UPDATE", "DELETE"), row
        assert not row["skill"].startswith("sr_"), row
        assert not row["skill"].startswith("educlaw_"), row
    for row in rows:
        if row["skill"] == "statereport-educlaw-statereport":
            assert row["action"].startswith("statereport-"), row


def test_user_id_new_values_present_and_absent(env):
    conn, cid = env["conn"], env["company_id"]
    wid = env["window_id"]

    sub = _seed_submission(conn, wid, cid)
    r = call_action(SUB["statereport-approve-submission"], conn, ns(
        submission_id=sub, certified_by="certifier-7",
        certification_notes="Approved", user_id=None,
    ))
    assert is_ok(r), r
    row = _single_audit(conn, sub)
    assert (row["skill"], row["action"], row["entity_type"]) == (
        "statereport-educlaw-statereport", "statereport-approve-submission", "sr_submission")
    assert json.loads(row["new_values"]) == {"user_id": "certifier-7"}

    inc = call_action(DISC["statereport-add-discipline-incident"], conn, ns(
        company_id=cid, school_year=2025,
        incident_date="2025-10-15", incident_type="bullying",
        incident_time=None, incident_description=None,
        campus_location=None, reported_by=None,
        user_id=None,
    ))
    assert is_ok(inc), inc
    row = _single_audit(conn, inc["id"])
    assert (row["skill"], row["action"], row["entity_type"]) == (
        "statereport-educlaw-statereport", "statereport-add-discipline-incident", "educlaw_k12_discipline_incident")
    assert row["new_values"] is None
