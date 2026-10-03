"""Behavioural depth tests for 12 educlaw-statereport actions.

The pre-existing tests in test_statereport.py prove routing/shape (response
keys). Every test here instead observes the database: connections come from
erpclaw_lib.db.get_connection(), queries are built with PyPika through
erpclaw_lib.query, and catalog questions go through erpclaw_lib.seam. Each
happy-path test states what row exists afterwards with which exact values,
what changed from what to what, and what did NOT change. Money is compared
as exact Decimal strings, never float.

No test in this file touches the ledger: none of the 12 actions posts to the
GL, so each class carries a comment saying so rather than an assertion that
cannot hold.
"""
import importlib.util
import json
import os
import sys
import uuid
from decimal import Decimal, ROUND_HALF_UP

import pytest

os.environ.setdefault("ERPCLAW_FIELD_KEY", "test-key-for-unit-tests")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
_IN_TREE_LIB = os.path.join(
    _SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if _IN_TREE_LIB not in sys.path:
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, _IN_TREE_LIB)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, fn, insert_row, dynamic_update
from erpclaw_lib.seam import table_exists, column_names


def _load(name, directory):
    """Load a module by explicit file path (avoids sys.path collisions)."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(directory, "{}.py".format(name)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student
seed_academic_year = _helpers.seed_academic_year
seed_collection_window = _helpers.seed_collection_window
seed_edfi_config = _helpers.seed_edfi_config
seed_supplement = _helpers.seed_supplement

DV_ACTIONS = _load("data_validation", _SCRIPTS_DIR).ACTIONS
SR_ACTIONS = _load("state_reporting", _SCRIPTS_DIR).ACTIONS
DISC_ACTIONS = _load("discipline", _SCRIPTS_DIR).ACTIONS
EDFI_ACTIONS = _load("ed_fi", _SCRIPTS_DIR).ACTIONS
SUB_ACTIONS = _load("submission_tracking", _SCRIPTS_DIR).ACTIONS


# ---------------------------------------------------------------------------
# Read helpers: everything observed goes through get_connection + PyPika.
# ---------------------------------------------------------------------------

def fetch_one(conn, table, row_id):
    t = Table(table)
    sql = Q.from_(t).select(t.star).where(Field("id") == P()).get_sql()
    row = conn.execute(sql, (row_id,)).fetchone()
    return dict(row) if row else None


def fetch_where(conn, table, filters):
    t = Table(table)
    query = Q.from_(t).select(t.star)
    params = []
    for key, value in filters.items():
        query = query.where(Field(key) == P())
        params.append(value)
    query = query.orderby(Field("id"))
    return [dict(r) for r in conn.execute(query.get_sql(), tuple(params)).fetchall()]


def count_where(conn, table, filters):
    t = Table(table)
    query = Q.from_(t).select(fn.Count("*"))
    params = []
    for key, value in filters.items():
        query = query.where(Field(key) == P())
        params.append(value)
    return conn.execute(query.get_sql(), tuple(params)).fetchone()[0]


def dump_table(conn, table):
    return fetch_where(conn, table, {})


@pytest.fixture
def depth(db_path):
    conn = get_connection()
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


def add_depth_rule(conn, rule_code, sql_query, severity="critical",
                   category="enrollment"):
    r = call_action(DV_ACTIONS["statereport-add-validation-rule"], conn, ns(
        rule_code=rule_code, category=category, severity=severity,
        name="Depth probe {}".format(rule_code),
        description="depth test rule",
        applicable_windows="[]", applicable_states="[]",
        is_federal_rule=0, sql_query=sql_query,
        error_message_template="Depth probe hit {student_id}",
        user_id="depth-test"))
    assert is_ok(r)
    return r["id"]


def seed_program(conn, company_id):
    pid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_program", {
        "id": P(), "code": P(), "name": P(),
        "program_type": P(), "company_id": P(), "created_by": P()})
    conn.execute(sql, (pid, "PRG-{}".format(pid[:8]),
                       "Depth Probe Program", "k12", company_id, "depth-test"))
    conn.commit()
    return pid


def seed_enrollment(conn, student_id, program_id, year_id, company_id,
                    status="active", date="2025-03-01"):
    eid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_program_enrollment", {
        "id": P(), "naming_series": P(), "student_id": P(),
        "program_id": P(), "academic_year_id": P(), "enrollment_date": P(),
        "enrollment_status": P(), "company_id": P(), "created_by": P()})
    conn.execute(sql, (eid, "ENR-{}".format(eid[:8]), student_id, program_id,
                       year_id, date, status, company_id, "depth-test"))
    conn.commit()
    return eid


def seed_attendance(conn, student_id, company_id, day, status):
    aid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_student_attendance", {
        "id": P(), "student_id": P(), "attendance_date": P(),
        "attendance_status": P(), "company_id": P(), "created_by": P()})
    conn.execute(sql, (aid, student_id, day, status, company_id, "depth-test"))
    conn.commit()
    return aid


def mark_student(conn, student_id, grade_level="05", gender="female"):
    sql, params = dynamic_update(
        "educlaw_student",
        data={"grade_level": grade_level, "gender": gender},
        where={"id": student_id})
    conn.execute(sql, params)
    conn.commit()


class TestApplyValidationDepth:
    # No ledger effect: statereport-apply-validation writes
    # sr_validation_result and sr_submission_error only; it never posts to
    # the GL, so no debit/credit legs are asserted here.

    def test_writes_results_and_errors(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        wid, sid = depth["window_id"], depth["student_id"]
        assert table_exists("sr_validation_result")
        assert table_exists("sr_submission_error")
        assert "student_id" in column_names("sr_validation_result")
        rule_id = add_depth_rule(
            conn, "DEPTH-VAL-001",
            "SELECT id as student_id FROM educlaw_student "
            "WHERE id = '{}'".format(sid))
        other_window = seed_collection_window(conn, cid, depth["year_id"])

        r = call_action(DV_ACTIONS["statereport-apply-validation"], conn, ns(
            window_id=wid, company_id=cid, user_id="admin"))
        assert is_ok(r)
        assert r["rules_run"] == 1
        assert r["total_violations"] == 1

        results = fetch_where(conn, "sr_validation_result",
                              {"collection_window_id": wid})
        assert len(results) == 1
        row = results[0]
        assert row["rule_id"] == rule_id
        assert row["student_id"] == sid
        assert row["is_resolved"] == 0
        assert row["company_id"] == cid
        assert row["run_by"] == "admin"
        assert json.loads(row["error_detail"]) == {"student_id": sid}

        errors = fetch_where(conn, "sr_submission_error",
                             {"collection_window_id": wid})
        assert len(errors) == 1
        err_row = errors[0]
        assert err_row["error_code"] == "DEPTH-VAL-001"
        assert err_row["severity"] == "critical"
        assert err_row["error_category"] == "enrollment"
        assert err_row["error_source"] == "internal_validation"
        assert err_row["error_level"] == "2"
        assert err_row["resolution_status"] == "open"
        assert err_row["student_id"] == sid
        assert err_row["company_id"] == cid
        assert err_row["assigned_to"] == ""
        assert err_row["error_message"] == "Depth probe hit {}".format(sid)

        assert count_where(conn, "sr_validation_result",
                           {"collection_window_id": other_window}) == 0
        assert count_where(conn, "sr_submission_error",
                           {"collection_window_id": other_window}) == 0

        again = call_action(
            DV_ACTIONS["statereport-apply-validation"], conn, ns(
                window_id=wid, company_id=cid, user_id="admin"))
        assert is_ok(again)
        assert count_where(conn, "sr_validation_result",
                           {"collection_window_id": wid}) == 1

    def test_refuses_without_window_id(self, depth):
        conn = depth["conn"]
        before_results = dump_table(conn, "sr_validation_result")
        before_errors = dump_table(conn, "sr_submission_error")
        r = call_action(DV_ACTIONS["statereport-apply-validation"], conn, ns(
            window_id=None, company_id=depth["company_id"], user_id="admin"))
        assert is_error(r)
        assert "--window-id" in r["message"]
        assert dump_table(conn, "sr_validation_result") == before_results
        assert dump_table(conn, "sr_submission_error") == before_errors


class TestApplyStudentValidationDepth:
    # No ledger effect: statereport-apply-student-validation writes
    # sr_validation_result and sr_submission_error only; it never posts to
    # the GL, so no debit/credit legs are asserted here.

    # DOCUMENTED DEFECT (deliberately not fixed): on SQLite this action
    # always reports violations_found == 0 and writes no rows. It filters
    # with `v.get("student_id")` directly on the DBAPI Row object, which
    # has no .get; the AttributeError is swallowed by `except Exception`
    # and the run silently records nothing. No ledger effect either way:
    # the action never posts to the GL.

    def test_student_run_writes_nothing_on_sqlite(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        wid, sid_a = depth["window_id"], depth["student_id"]
        assert table_exists("sr_validation_result")
        assert table_exists("sr_submission_error")
        add_depth_rule(conn, "DEPTH-STU-001", _ALL_ACTIVE_STUDENTS)

        r = call_action(
            DV_ACTIONS["statereport-apply-student-validation"], conn, ns(
                window_id=wid, student_id=sid_a, company_id=cid,
                user_id="admin"))
        assert is_ok(r)
        # Real behaviour on SQLite: nothing found, nothing written.
        assert r["violations_found"] == 0
        assert count_where(conn, "sr_validation_result",
                           {"collection_window_id": wid}) == 0
        assert count_where(conn, "sr_submission_error",
                           {"collection_window_id": wid}) == 0

        # Contrast: the same rule through the window-wide run DOES match
        # this student, proving the zero above is the action's doing, not
        # the fixture's.
        w = call_action(DV_ACTIONS["statereport-apply-validation"], conn,
                        ns(window_id=wid, company_id=cid, user_id="admin"))
        assert is_ok(w)
        assert w["total_violations"] >= 1
        assert count_where(
            conn, "sr_validation_result",
            {"collection_window_id": wid, "student_id": sid_a}) == 1
        assert count_where(
            conn, "sr_submission_error",
            {"collection_window_id": wid, "student_id": sid_a}) == 1

    def test_refuses_without_student_id(self, depth):
        conn = depth["conn"]
        before_results = dump_table(conn, "sr_validation_result")
        before_errors = dump_table(conn, "sr_submission_error")
        r = call_action(
            DV_ACTIONS["statereport-apply-student-validation"], conn, ns(
                window_id=depth["window_id"], student_id=None,
                company_id=depth["company_id"], user_id="admin"))
        assert is_error(r)
        assert "--student-id" in r["message"]
        assert dump_table(conn, "sr_validation_result") == before_results
        assert dump_table(conn, "sr_submission_error") == before_errors


_ALL_ACTIVE_STUDENTS = (
    "SELECT id as student_id FROM educlaw_student WHERE status = 'active'")


def _run_window_errors(conn, window_id, company_id, rule_code, rule_sql=None):
    # Window-wide validation is the working error generator (the
    # student-scoped run is a documented no-op on SQLite). It executes every
    # active rule, so callers share one rule per test.
    if rule_sql is not None:
        add_depth_rule(conn, rule_code, rule_sql)
    r = call_action(DV_ACTIONS["statereport-apply-validation"], conn, ns(
        window_id=window_id, company_id=company_id, user_id="admin"))
    assert is_ok(r)
    return r


def _window_error_for(conn, window_id, student_id):
    rows = fetch_where(conn, "sr_submission_error",
                       {"collection_window_id": window_id,
                        "student_id": student_id})
    assert len(rows) == 1
    return rows[0]["id"]


class TestAssignSubmissionErrorDepth:
    # No ledger effect: statereport-assign-submission-error updates one
    # sr_submission_error row; it never posts to the GL.

    def test_assigns_one_error_row(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        wid = depth["window_id"]
        sid_b = seed_student(conn, cid)
        assert table_exists("sr_submission_error")
        _run_window_errors(conn, wid, cid, "DEPTH-ASN-ALL",
                           _ALL_ACTIVE_STUDENTS)
        err_a = _window_error_for(conn, wid, depth["student_id"])
        err_b = _window_error_for(conn, wid, sid_b)
        before_b = fetch_one(conn, "sr_submission_error", err_b)
        assert before_b["resolution_status"] == "open"
        assert before_b["assigned_to"] == ""

        r = call_action(
            DV_ACTIONS["statereport-assign-submission-error"], conn, ns(
                error_id=err_a, assigned_to="counselor-1", user_id="admin"))
        assert is_ok(r)
        assert r["assigned_to"] == "counselor-1"

        after_a = fetch_one(conn, "sr_submission_error", err_a)
        assert after_a["assigned_to"] == "counselor-1"
        assert after_a["resolution_status"] == "in_progress"
        assert after_a["assigned_at"] != ""
        assert after_a["updated_at"] != ""
        assert after_a["error_code"] == "DEPTH-ASN-ALL"
        assert after_a["student_id"] == depth["student_id"]
        assert after_a["collection_window_id"] == wid

        after_b = fetch_one(conn, "sr_submission_error", err_b)
        assert after_b == before_b

    def test_refuses_unknown_error_id(self, depth):
        conn = depth["conn"]
        before = dump_table(conn, "sr_submission_error")
        r = call_action(
            DV_ACTIONS["statereport-assign-submission-error"], conn, ns(
                error_id="does-not-exist", assigned_to="counselor-1",
                user_id="admin"))
        assert is_error(r)
        assert "not found" in r["message"]
        assert dump_table(conn, "sr_submission_error") == before


class TestBulkAssignErrorsDepth:
    # No ledger effect: statereport-assign-errors updates sr_submission_error
    # rows only; it never posts to the GL.

    def test_assigns_many_leaves_others_open(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        wid = depth["window_id"]
        sid_b = seed_student(conn, cid)
        other_window = seed_collection_window(conn, cid, depth["year_id"])
        assert table_exists("sr_submission_error")
        _run_window_errors(conn, wid, cid, "DEPTH-BLK-ALL",
                           _ALL_ACTIVE_STUDENTS)
        err_a = _window_error_for(conn, wid, depth["student_id"])
        err_b = _window_error_for(conn, wid, sid_b)
        _run_window_errors(conn, other_window, cid, "DEPTH-BLK-ALL")
        other_err = _window_error_for(conn, other_window, depth["student_id"])

        r = call_action(DV_ACTIONS["statereport-assign-errors"], conn, ns(
            error_ids=json.dumps([err_a, err_b]),
            assigned_to="principal-2", user_id="admin"))
        assert is_ok(r)
        assert r["assigned_count"] == 2
        assert r["assigned_to"] == "principal-2"

        for eid in (err_a, err_b):
            row = fetch_one(conn, "sr_submission_error", eid)
            assert row["assigned_to"] == "principal-2"
            assert row["resolution_status"] == "in_progress"
            assert row["assigned_at"] != ""

        untouched = fetch_one(conn, "sr_submission_error", other_err)
        assert untouched["resolution_status"] == "open"
        assert untouched["assigned_to"] == ""

    def test_refuses_bad_error_ids_json(self, depth):
        conn = depth["conn"]
        before = dump_table(conn, "sr_submission_error")
        r = call_action(DV_ACTIONS["statereport-assign-errors"], conn, ns(
            error_ids="not-json", assigned_to="principal-2",
            user_id="admin"))
        assert is_error(r)
        assert "JSON array" in r["message"]
        assert dump_table(conn, "sr_submission_error") == before


class TestDeleteDescriptorMappingDepth:
    # No ledger effect: statereport-delete-descriptor-mapping deletes one
    # sr_edfi_descriptor_map row; it never posts to the GL.

    def test_deletes_one_mapping_row(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        cfg = depth["edfi_config_id"]
        assert table_exists("sr_edfi_descriptor_map")
        first = call_action(
            EDFI_ACTIONS["statereport-add-descriptor-mapping"], conn, ns(
                config_id=cfg, company_id=cid,
                descriptor_type="grade_level", internal_code="K",
                edfi_descriptor_uri="uri://ed-fi.org/GradeLevelDescriptor"
                "#Kindergarten",
                description="Kindergarten", user_id="admin"))
        assert is_ok(first)
        second = call_action(
            EDFI_ACTIONS["statereport-add-descriptor-mapping"], conn, ns(
                config_id=cfg, company_id=cid,
                descriptor_type="race", internal_code="W",
                edfi_descriptor_uri="uri://ed-fi.org/RaceDescriptor#White",
                description="White", user_id="admin"))
        assert is_ok(second)

        r = call_action(
            EDFI_ACTIONS["statereport-delete-descriptor-mapping"], conn, ns(
                desc_id=first["id"], user_id="admin"))
        assert is_ok(r)
        assert r["id"] == first["id"]

        assert fetch_one(conn, "sr_edfi_descriptor_map", first["id"]) is None
        kept = fetch_one(conn, "sr_edfi_descriptor_map", second["id"])
        assert kept["descriptor_type"] == "race"
        assert kept["internal_code"] == "W"
        assert kept["edfi_descriptor_uri"] == \
            "uri://ed-fi.org/RaceDescriptor#White"
        assert kept["is_active"] == 1
        assert kept["config_id"] == cfg
        assert kept["company_id"] == cid

    def test_refuses_unknown_mapping(self, depth):
        conn = depth["conn"]
        before = dump_table(conn, "sr_edfi_descriptor_map")
        r = call_action(
            EDFI_ACTIONS["statereport-delete-descriptor-mapping"], conn, ns(
                desc_id="missing-mapping", user_id="admin"))
        assert is_error(r)
        assert "not found" in r["message"]
        assert dump_table(conn, "sr_edfi_descriptor_map") == before


def _add_incident(conn, company_id, incident_type):
    r = call_action(
        DISC_ACTIONS["statereport-add-discipline-incident"], conn, ns(
            company_id=company_id, school_year=2025,
            incident_date="2025-10-15", incident_type=incident_type,
            incident_time="10:30", incident_description="depth probe",
            campus_location="hallway", reported_by="teacher1",
            user_id="admin"))
    assert is_ok(r)
    return r["id"]


class TestDeleteDisciplineIncidentDepth:
    # No ledger effect: statereport-delete-discipline-incident deletes one
    # educlaw_k12_discipline_incident row; it never posts to the GL.

    def test_deletes_empty_incident_row(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        assert table_exists("educlaw_k12_discipline_incident")
        gone_id = _add_incident(conn, cid, "bullying")
        kept_id = _add_incident(conn, cid, "vandalism")

        r = call_action(
            DISC_ACTIONS["statereport-delete-discipline-incident"], conn, ns(
                incident_id=gone_id, user_id="admin"))
        assert is_ok(r)
        assert r["id"] == gone_id

        assert fetch_one(
            conn, "educlaw_k12_discipline_incident", gone_id) is None
        kept = fetch_one(conn, "educlaw_k12_discipline_incident", kept_id)
        assert kept["incident_type"] == "vandalism"
        assert kept["school_year"] == 2025
        assert kept["company_id"] == cid

    def test_refuses_incident_with_students(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        inc_id = _add_incident(conn, cid, "bullying")
        ds = call_action(
            DISC_ACTIONS["statereport-add-discipline-student"], conn, ns(
                incident_id=inc_id, student_id=depth["student_id"],
                role="offender", company_id=cid, user_id="admin"))
        assert is_ok(ds)
        before_incidents = dump_table(conn, "educlaw_k12_discipline_incident")
        before_students = dump_table(conn, "educlaw_k12_discipline_student")

        r = call_action(
            DISC_ACTIONS["statereport-delete-discipline-incident"], conn, ns(
                incident_id=inc_id, user_id="admin"))
        assert is_error(r)
        assert "1 student(s)" in r["message"]
        assert fetch_one(
            conn, "educlaw_k12_discipline_incident", inc_id) is not None
        assert fetch_one(
            conn, "educlaw_k12_discipline_student", ds["id"]) is not None
        assert dump_table(conn, "educlaw_k12_discipline_incident") == \
            before_incidents
        assert dump_table(conn, "educlaw_k12_discipline_student") == \
            before_students


class TestDeleteDisciplineStudentDepth:
    # No ledger effect: statereport-delete-discipline-student removes the
    # junction row and cascades to its actions; it never posts to the GL.

    def test_removes_student_and_cascades_actions(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        assert table_exists("educlaw_k12_discipline_student")
        assert table_exists("educlaw_k12_discipline_action")
        inc_id = _add_incident(conn, cid, "drug_alcohol")
        ds = call_action(
            DISC_ACTIONS["statereport-add-discipline-student"], conn, ns(
                incident_id=inc_id, student_id=depth["student_id"],
                role="offender", company_id=cid, user_id="admin"))
        assert is_ok(ds)
        act = call_action(
            DISC_ACTIONS["statereport-add-discipline-action"], conn, ns(
                discipline_student_id=ds["id"], action_type="oss_1_10",
                company_id=cid, days_removed=5,
                start_date="2025-10-16", end_date="2025-10-21",
                alternative_services_provided=1,
                alternative_services_description="Homework packets",
                mdr_required=None, mdr_outcome=None, mdr_date=None,
                user_id="admin"))
        assert is_ok(act)
        assert fetch_one(conn, "educlaw_k12_discipline_incident",
                         inc_id)["student_count_involved"] == 1

        r = call_action(
            DISC_ACTIONS["statereport-delete-discipline-student"], conn, ns(
                discipline_student_id=ds["id"], user_id="admin"))
        assert is_ok(r)
        assert r["id"] == ds["id"]

        assert fetch_one(conn, "educlaw_k12_discipline_student",
                         ds["id"]) is None
        assert fetch_one(conn, "educlaw_k12_discipline_action",
                         act["id"]) is None
        incident = fetch_one(conn, "educlaw_k12_discipline_incident", inc_id)
        assert incident is not None
        assert incident["student_count_involved"] == 0

    def test_refuses_unknown_discipline_student(self, depth):
        conn = depth["conn"]
        before_students = dump_table(conn, "educlaw_k12_discipline_student")
        before_actions = dump_table(conn, "educlaw_k12_discipline_action")
        before_incidents = dump_table(conn, "educlaw_k12_discipline_incident")
        r = call_action(
            DISC_ACTIONS["statereport-delete-discipline-student"], conn, ns(
                discipline_student_id="missing-record", user_id="admin"))
        assert is_error(r)
        assert "not found" in r["message"]
        assert dump_table(conn, "educlaw_k12_discipline_student") == \
            before_students
        assert dump_table(conn, "educlaw_k12_discipline_action") == \
            before_actions
        assert dump_table(conn, "educlaw_k12_discipline_incident") == \
            before_incidents


def _seed_ada_case(conn, company_id, student_id, year_id):
    """One active enrollment + 4 school days: 2 present, 1 half, 1 absent."""
    program_id = seed_program(conn, company_id)
    seed_enrollment(conn, student_id, program_id, year_id, company_id)
    seed_attendance(conn, student_id, company_id, "2025-03-03", "present")
    seed_attendance(conn, student_id, company_id, "2025-03-04", "present")
    seed_attendance(conn, student_id, company_id, "2025-03-05", "half_day")
    seed_attendance(conn, student_id, company_id, "2025-03-06", "absent")


class TestGenerateAdaDepth:
    # No stored row and no ledger effect: statereport-generate-ada is a
    # read-only calculation over attendance/enrollment rows. The depth signal
    # is the exact derived value, plus proof the database did not change.

    def test_derives_exact_ada_from_attendance(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        _seed_ada_case(conn, cid, depth["student_id"], depth["year_id"])
        before_att = dump_table(conn, "educlaw_student_attendance")
        before_enr = dump_table(conn, "educlaw_program_enrollment")

        r = call_action(SR_ACTIONS["statereport-generate-ada"], conn, ns(
            company_id=cid, date_from=None, date_to=None, school_year=2025))
        assert is_ok(r)
        assert r["school_days"] == 4
        assert r["present_days"] == 2
        assert r["half_days"] == 1
        assert r["ada"] == "0.6250"
        assert r["adm"] == "1"
        assert r["ada_rate_pct"] == "62.5000"
        assert Decimal(r["ada"]) == Decimal("0.6250")
        assert Decimal(r["adm"]) == Decimal("1")

        assert dump_table(conn, "educlaw_student_attendance") == before_att
        assert dump_table(conn, "educlaw_program_enrollment") == before_enr

    def test_refuses_without_company_id(self, depth):
        conn = depth["conn"]
        _seed_ada_case(conn, depth["company_id"], depth["student_id"],
                       depth["year_id"])
        before_att = dump_table(conn, "educlaw_student_attendance")
        before_enr = dump_table(conn, "educlaw_program_enrollment")
        r = call_action(SR_ACTIONS["statereport-generate-ada"], conn, ns(
            company_id=None, date_from=None, date_to=None, school_year=2025))
        assert is_error(r)
        assert "--company-id" in r["message"]
        assert dump_table(conn, "educlaw_student_attendance") == before_att
        assert dump_table(conn, "educlaw_program_enrollment") == before_enr


class TestAdaDashboardDepth:
    # No stored row and no ledger effect: statereport-get-ada-dashboard is a
    # read-only dashboard. Its funding figures are computed Decimal strings,
    # not postings, so both legs/balance assertions cannot hold; instead the
    # money math is asserted exactly as text.

    def test_derives_funding_from_ada_exactly(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        _seed_ada_case(conn, cid, depth["student_id"], depth["year_id"])
        before_att = dump_table(conn, "educlaw_student_attendance")
        before_enr = dump_table(conn, "educlaw_program_enrollment")

        r = call_action(SR_ACTIONS["statereport-get-ada-dashboard"], conn, ns(
            company_id=cid, school_year=2025, per_pupil_rate="12000"))
        assert is_ok(r)
        assert r["school_days_to_date"] == 4
        assert r["current_enrollment_adm"] == 1
        assert r["current_ada"] == "0.6250"
        assert r["current_ada_rate_pct"] == "62.5000"
        assert r["projected_annual_ada"] == "0.6250"
        assert r["per_pupil_rate"] == "12000"

        ada = Decimal("0.6250")
        rate = Decimal("12000")
        expected_funding = (ada * rate).quantize(Decimal("0.01"),
                                                 rounding=ROUND_HALF_UP)
        expected_one_pct = (ada * Decimal("0.01") * rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert Decimal(r["estimated_funding_allocation"]) == expected_funding
        assert r["estimated_funding_allocation"] == "7500.00"
        assert Decimal(r["one_pct_improvement_value"]) == expected_one_pct
        assert r["one_pct_improvement_value"] == "75.00"

        assert dump_table(conn, "educlaw_student_attendance") == before_att
        assert dump_table(conn, "educlaw_program_enrollment") == before_enr

    def test_refuses_without_school_year(self, depth):
        conn = depth["conn"]
        before_att = dump_table(conn, "educlaw_student_attendance")
        r = call_action(SR_ACTIONS["statereport-get-ada-dashboard"], conn, ns(
            company_id=depth["company_id"], school_year=None,
            per_pupil_rate="12000"))
        assert is_error(r)
        assert "--school-year" in r["message"]
        assert dump_table(conn, "educlaw_student_attendance") == before_att


def _seed_report_case(conn, company_id, student_id, year_id):
    """One active enrollment + supplement + marked student for reports."""
    mark_student(conn, student_id)
    program_id = seed_program(conn, company_id)
    seed_enrollment(conn, student_id, program_id, year_id, company_id)


class TestEnrollmentReportDepth:
    # No stored row and no ledger effect:
    # statereport-generate-enrollment-report aggregates enrollment and
    # supplement rows read-only. The depth signal is the exact disaggregation
    # including small-cell suppression, plus proof nothing was written.

    def test_disaggregates_one_student_exactly(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        _seed_report_case(conn, cid, depth["student_id"], depth["year_id"])
        before_enr = dump_table(conn, "educlaw_program_enrollment")
        before_supp = dump_table(conn, "sr_student_supplement")

        r = call_action(
            SR_ACTIONS["statereport-generate-enrollment-report"], conn, ns(
                company_id=cid, school_year=2025))
        assert is_ok(r)
        assert r["school_year"] == 2025
        assert r["by_race"] == [{"race_federal_rollup": "WHITE",
                                "count": "<10", "suppressed": True}]
        assert r["by_grade_level"] == [{"grade_level": "05", "count": 1}]
        assert r["subgroup_counts"]["el_count"] == 0
        assert r["subgroup_counts"]["sped_count"] == 0
        assert r["subgroup_counts"]["econ_disadv_count"] == 0
        assert r["subgroup_counts"]["homeless_count"] == 0
        assert r["subgroup_counts"]["migrant_count"] == 0
        assert r["subgroup_counts"]["foster_count"] == 0

        assert dump_table(conn, "educlaw_program_enrollment") == before_enr
        assert dump_table(conn, "sr_student_supplement") == before_supp

    def test_refuses_without_company_id(self, depth):
        conn = depth["conn"]
        before_enr = dump_table(conn, "educlaw_program_enrollment")
        r = call_action(
            SR_ACTIONS["statereport-generate-enrollment-report"], conn, ns(
                company_id=None, school_year=2025))
        assert is_error(r)
        assert "--company-id" in r["message"]
        assert dump_table(conn, "educlaw_program_enrollment") == before_enr


class TestCrdcReportDepth:
    # No stored row and no ledger effect:
    # statereport-generate-crdc-report aggregates enrollment, discipline and
    # supplement rows read-only. The depth signal is the exact subgroup
    # matrix including suppression, plus proof nothing was written.

    def test_reports_subgroups_with_suppression(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        _seed_report_case(conn, cid, depth["student_id"], depth["year_id"])
        before_enr = dump_table(conn, "educlaw_program_enrollment")

        r = call_action(
            SR_ACTIONS["statereport-generate-crdc-report"], conn, ns(
                company_id=cid, school_year=2025))
        assert is_ok(r)
        assert r["school_year"] == 2025
        assert r["enrollment_by_race_sex"] == [
            {"race_federal_rollup": "WHITE", "gender": "female",
             "count": "<10", "suppressed": True}]
        assert r["discipline_by_race_sex_action"] == []
        assert r["idea_enrollment_by_race_sex"] == []

        assert dump_table(conn, "educlaw_program_enrollment") == before_enr

    def test_refuses_without_school_year(self, depth):
        conn = depth["conn"]
        before_enr = dump_table(conn, "educlaw_program_enrollment")
        r = call_action(
            SR_ACTIONS["statereport-generate-crdc-report"], conn, ns(
                company_id=depth["company_id"], school_year=None))
        assert is_error(r)
        assert "--school-year" in r["message"]
        assert dump_table(conn, "educlaw_program_enrollment") == before_enr


class TestSubmissionPackageDepth:
    # No ledger effect: statereport-generate-submission-package is a
    # read-only export of the submission, its snapshot and the frozen
    # snapshot records. The depth signal is the exact linkage between those
    # stored rows, plus proof the export wrote nothing.

    def test_exports_linked_snapshot_and_records(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        _seed_report_case(conn, cid, depth["student_id"], depth["year_id"])
        assert table_exists("sr_snapshot")
        assert table_exists("sr_snapshot_record")
        assert table_exists("sr_submission")
        assert "data_json" in column_names("sr_snapshot_record")

        snap = call_action(SR_ACTIONS["statereport-create-snapshot"], conn,
                           ns(window_id=depth["window_id"], user_id="admin"))
        assert is_ok(snap)
        stored_snap = fetch_one(conn, "sr_snapshot", snap["id"])
        assert stored_snap["total_students"] == 1
        assert stored_snap["total_enrollment"] == 1
        assert stored_snap["snapshot_status"] == "draft"
        assert stored_snap["collection_window_id"] == depth["window_id"]

        sub = call_action(SUB_ACTIONS["statereport-add-submission"], conn, ns(
            window_id=depth["window_id"], company_id=cid,
            submission_type="initial", submission_method="edfi_api",
            snapshot_id=snap["id"], linked_submission_id=None,
            submitted_at=None, submitted_by=None,
            records_submitted=None, records_accepted=None,
            records_rejected=None, state_confirmation_id=None,
            state_confirmed_at=None, amendment_reason=None, user_id="admin"))
        assert is_ok(sub)
        before_snaps = dump_table(conn, "sr_snapshot")
        before_records = dump_table(conn, "sr_snapshot_record")
        before_subs = dump_table(conn, "sr_submission")

        r = call_action(
            SUB_ACTIONS["statereport-generate-submission-package"], conn, ns(
                submission_id=sub["id"]))
        assert is_ok(r)
        assert r["submission"]["id"] == sub["id"]
        assert r["snapshot"]["id"] == snap["id"]
        assert r["collection_window"]["id"] == depth["window_id"]
        assert r["collection_window"]["window_type"] == \
            fetch_one(conn, "sr_collection_window",
                      depth["window_id"])["window_type"]
        assert r["record_count"] == 1
        assert len(r["records"]) == 1
        record = r["records"][0]
        assert record["student_id"] == depth["student_id"]
        assert record["record_type"] == "student_enrollment"
        assert record["data_json"]["student_id"] == depth["student_id"]
        assert record["data_json"]["ssid"] == "SSN12345"
        assert record["data_json"]["race_federal_rollup"] == "WHITE"

        assert dump_table(conn, "sr_snapshot") == before_snaps
        assert dump_table(conn, "sr_snapshot_record") == before_records
        assert dump_table(conn, "sr_submission") == before_subs

    def test_refuses_snapshotless_submission_truthfully(self, depth):
        conn, cid = depth["conn"], depth["company_id"]
        bare = call_action(SUB_ACTIONS["statereport-add-submission"], conn,
                           ns(window_id=depth["window_id"], company_id=cid,
                              submission_type="initial",
                              submission_method="edfi_api", snapshot_id=None,
                              linked_submission_id=None, submitted_at=None,
                              submitted_by=None, records_submitted=None,
                              records_accepted=None, records_rejected=None,
                              state_confirmation_id=None,
                              state_confirmed_at=None, amendment_reason=None,
                              user_id="admin"))
        assert is_ok(bare)
        before_subs = dump_table(conn, "sr_submission")
        before_snaps = dump_table(conn, "sr_snapshot")

        r = call_action(
            SUB_ACTIONS["statereport-generate-submission-package"], conn, ns(
                submission_id=bare["id"]))
        assert is_error(r)
        assert "no linked snapshot" in r["message"]
        assert dump_table(conn, "sr_submission") == before_subs
        assert dump_table(conn, "sr_snapshot") == before_snaps

    def test_refuses_without_submission_id(self, depth):
        conn = depth["conn"]
        before_subs = dump_table(conn, "sr_submission")
        r = call_action(
            SUB_ACTIONS["statereport-generate-submission-package"], conn, ns(
                submission_id=None))
        assert is_error(r)
        assert "--submission-id" in r["message"]
        assert dump_table(conn, "sr_submission") == before_subs
