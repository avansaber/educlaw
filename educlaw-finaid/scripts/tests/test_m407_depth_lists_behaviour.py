"""M407 depth: behavioural evidence for the 12 finaid list actions.

Prior state (read before writing anything below): each action here had only a
shape-only test in ``test_finaid.py`` (``TestVerification.test_list_requests``,
``TestSAPEvaluation.test_list``, ``TestR2T4.test_list``,
``TestProfessionalJudgment.test_list``, ``TestPellSchedule.test_list``,
``TestScholarshipProgram.test_list``,
``TestScholarshipApplication.test_list``,
``TestScholarshipRenewal.test_list``, ``TestWorkStudyJob.test_list`` and
``TestWorkStudyAssignment.test_list``) asserting the response is ok, plus
``finaid-list-sap-appeals`` and ``finaid-list-verification-documents`` which
had no module test at all and were reachable only through box-facing
routability contracts. None of them observed the database.

Every test below observes the database through a fresh ``get_connection()``
read-back built with PyPika (``erpclaw_lib.query``): seeded rows are written
through the owning write actions, the list payload is compared against the
stored rows field by field, filters and limit/offset are shown to partition
the set, and a before/after snapshot proves the read changed nothing.
Catalog questions (does the table exist) go through ``erpclaw_lib.seam``.
Money compares exact ``Decimal`` strings, never float, never approximate.

Ledger scope, stated once so no later reader adds a balance assertion that
cannot hold: all 12 handlers are pure reads (SELECT only). None of them
reaches the general ledger, so no debit/credit legs are asserted anywhere in
this file. Every per-action section repeats its own ledger note.

Signal depth per action (all stored row, read-only; payload mirrors rows):
- finaid-list-pell-schedule: stored rows (money exact, index filter, paging).
- finaid-list-verification-requests: stored rows (group filter, paging).
- finaid-list-verification-documents: stored rows (auto-created docs + added).
- finaid-list-sap-evaluations: stored rows (SAT vs FSP filter, paging).
- finaid-list-sap-appeals: stored rows (student/status filter, paging).
- finaid-list-r2t4s: stored rows (student/status filter, money zeros exact).
- finaid-list-professional-judgments: stored rows (pj_type filter, paging).
- finaid-list-scholarship-programs: stored rows (money exact, type filter).
- finaid-list-scholarship-applications: stored rows (student filter, paging).
- finaid-list-scholarship-renewals: stored rows (status filter, paging).
- finaid-list-work-study-jobs: stored rows (money exact, job_type filter).
- finaid-list-work-study-assignments: stored rows (money exact, job filter).

All dates are passed explicitly.
"""
import importlib.util
import json
import os
import shutil
import sys
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_LIB_DIR = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if os.path.isdir(os.path.join(_LIB_DIR, "erpclaw_lib")) and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, fn
from erpclaw_lib import seam as _seam


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error

FA = _load("financial_aid", _SCRIPTS_DIR).ACTIONS
SC = _load("scholarships", _SCRIPTS_DIR).ACTIONS
WS = _load("work_study", _SCRIPTS_DIR).ACTIONS

SNAPSHOT_TABLES = (
    "finaid_aid_year", "finaid_pell_schedule", "finaid_fund_allocation",
    "finaid_cost_of_attendance", "finaid_isir", "finaid_isir_cflag",
    "finaid_verification_request", "finaid_verification_document",
    "finaid_award_package", "finaid_award", "finaid_disbursement",
    "finaid_sap_evaluation", "finaid_sap_appeal", "finaid_r2t4_calculation",
    "finaid_professional_judgment", "finaid_scholarship_program",
    "finaid_scholarship_application", "finaid_scholarship_renewal",
    "finaid_work_study_job", "finaid_work_study_assignment",
    "finaid_work_study_timesheet", "finaid_loan",
    "audit_log",
)

LIST_TABLES = (
    "finaid_pell_schedule", "finaid_verification_request",
    "finaid_verification_document", "finaid_sap_evaluation",
    "finaid_sap_appeal", "finaid_r2t4_calculation",
    "finaid_professional_judgment", "finaid_scholarship_program",
    "finaid_scholarship_application", "finaid_scholarship_renewal",
    "finaid_work_study_job", "finaid_work_study_assignment",
)


@pytest.fixture(scope="module")
def template_path(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("m407tpl") / "template.sqlite")
    _helpers.init_all_tables(path)
    for name in LIST_TABLES:
        assert _seam.table_exists(name, path)
    return path


@pytest.fixture
def fconn(template_path, tmp_path):
    dest = str(tmp_path / "case.sqlite")
    shutil.copyfile(template_path, dest)
    conn = get_connection(dest)
    try:
        yield conn
    finally:
        conn.close()


def _snapshot(conn):
    snap = {}
    for name in SNAPSHOT_TABLES:
        t = Table(name)
        rows = conn.execute(Q.from_(t).select("*").get_sql()).fetchall()
        snap[name] = sorted(repr(dict(r)) for r in rows)
    return snap


def _row(conn, table, row_id):
    t = Table(table)
    row = conn.execute(
        Q.from_(t).select("*").where(t.id == P()).get_sql(), (row_id,)).fetchone()
    return dict(row) if row is not None else None


def _count(conn, table):
    t = Table(table)
    return conn.execute(Q.from_(t).select(fn.Count("*")).get_sql()).fetchone()[0]


def _build_env(conn):
    cid = _helpers.seed_company(conn)
    sid = _helpers.seed_student(conn, cid)
    aid = _helpers.seed_aid_year(conn, cid)
    yid = _helpers.seed_academic_year(conn, cid)
    tid = _helpers.seed_academic_term(conn, cid, yid)
    pid = _helpers.seed_program(conn, cid)
    peid = _helpers.seed_program_enrollment(conn, sid, pid, yid, cid)
    isir = _helpers.seed_isir(conn, sid, aid, cid)
    coa = _helpers.seed_cost_of_attendance(conn, aid, cid)
    return {"company_id": cid, "student_id": sid, "aid_year_id": aid,
            "year_id": yid, "term_id": tid, "program_id": pid,
            "program_enrollment_id": peid, "isir_id": isir,
            "cost_of_attendance_id": coa}


def _second_student(conn, s):
    sid = _helpers.seed_student(conn, s["company_id"])
    peid = _helpers.seed_program_enrollment(
        conn, sid, s["program_id"], s["year_id"], s["company_id"])
    isir = _helpers.seed_isir(conn, sid, s["aid_year_id"], s["company_id"])
    return sid, peid, isir


def _package(conn, s, student_id=None, peid=None, isir=None):
    r = call_action(FA["finaid-create-award-package"], conn, ns(
        student_id=student_id or s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=peid or s["program_enrollment_id"],
        isir_id=isir or s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", financial_need=None,
        acceptance_deadline=None, packaged_by=None, notes=None))
    assert is_ok(r), r
    return r["id"]


def _fws_award(conn, s, pkg_id, student_id, offered):
    r = call_action(FA["finaid-add-award"], conn, ns(
        award_package_id=pkg_id, student_id=student_id,
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type="fws", aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None,
        notes=None))
    assert is_ok(r), r
    return r["id"]


def _job(conn, s, title, job_type, pay, hours="15", positions=3):
    r = call_action(WS["finaid-add-work-study-job"], conn, ns(
        company_id=s["company_id"], aid_year_id=s["aid_year_id"],
        job_title=title, department_id=None, supervisor_id=None,
        job_type=job_type, pay_rate=pay, hours_per_week=hours,
        total_positions=positions, description=title + " duties"))
    assert is_ok(r), r
    return r["id"]


def _program(conn, s, code, stype, award, budget):
    r = call_action(SC["finaid-add-scholarship-program"], conn, ns(
        company_id=s["company_id"], name="Program " + code, code=code,
        scholarship_type=stype, funding_source="endowment",
        award_method="application_required", award_amount_type="fixed",
        award_amount=award, min_award="0", max_award="0",
        annual_budget=budget, max_recipients=20, renewal_eligible=1,
        renewal_gpa_minimum="3.00", renewal_credits_minimum="12",
        eligibility_criteria="{}", application_deadline="2025-08-01",
        award_period="annual", applies_to_aid_type="institutional_scholarship",
        description=""))
    assert is_ok(r), r
    return r["id"]


def _apply(conn, s, program_id, student_id, gpa):
    r = call_action(SC["finaid-submit-scholarship-application"], conn, ns(
        scholarship_program_id=program_id, student_id=student_id,
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        essay_response="Essay for " + student_id[:8], gpa_at_application=gpa,
        submission_date="2025-07-01"))
    assert is_ok(r), r
    return r["id"]


def _sap_eval(conn, s, student_id, gpa, attempted, completed, by="tester"):
    r = call_action(FA["finaid-generate-sap-evaluation"], conn, ns(
        student_id=student_id, academic_term_id=s["term_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        gpa_earned=gpa, gpa_threshold="2.00",
        credits_attempted=attempted, credits_completed=completed,
        completion_threshold="0.67", max_timeframe_credits="180",
        projected_credits_remaining="60",
        transfer_credits_attempted="0", transfer_credits_completed="0",
        evaluation_date="2025-12-01", evaluated_by=by,
        evaluation_type="automatic"))
    assert is_ok(r), r
    return r["id"]


# ---------------------------------------------------------------------------
# finaid-list-pell-schedule -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_pell_schedule.
# ---------------------------------------------------------------------------
class TestListPellSchedule:
    def _import(self, conn, s):
        rows = [
            {"pell_index": 0, "full_time_annual": "7395.00",
             "three_quarter_time": "5546.00", "half_time": "3698.00",
             "less_than_half_time": "1849.00"},
            {"pell_index": 1, "full_time_annual": "7345.00",
             "three_quarter_time": "5509.00", "half_time": "3673.00",
             "less_than_half_time": "1836.00"},
        ]
        r = call_action(FA["finaid-import-pell-schedule"], conn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            rows=json.dumps(rows)))
        assert is_ok(r), r
        assert r["inserted"] == 2
        return r

    def test_payload_mirrors_stored_money_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        self._import(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        by_index = {row["pell_index"]: row for row in r["schedule"]}
        assert sorted(by_index) == [0, 1]
        first = _row(fconn, "finaid_pell_schedule", by_index[0]["id"])
        assert first["full_time_annual"] == "7395.00"
        assert Decimal(first["full_time_annual"]) == Decimal("7395.00")
        assert first["half_time"] == "3698.00"
        assert Decimal(first["half_time"]) == Decimal("3698.00")
        for key in ("aid_year_id", "pell_index", "full_time_annual",
                    "three_quarter_time", "half_time", "less_than_half_time",
                    "company_id"):
            assert by_index[0][key] == first[key], key
        second = _row(fconn, "finaid_pell_schedule", by_index[1]["id"])
        assert second["full_time_annual"] == "7345.00"
        assert Decimal(second["full_time_annual"]) == Decimal("7345.00")
        filt = call_action(FA["finaid-list-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], pell_index=1, limit=50, offset=0))
        assert is_ok(filt), filt
        assert filt["count"] == 1
        assert filt["schedule"][0]["pell_index"] == 1
        assert filt["schedule"][0]["id"] == by_index[1]["id"]
        page0 = call_action(FA["finaid-list-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], limit=1, offset=0))
        page1 = call_action(FA["finaid-list-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert page0["schedule"][0]["id"] != page1["schedule"][0]["id"]
        assert {page0["schedule"][0]["id"], page1["schedule"][0]["id"]} == {
            by_index[0]["id"], by_index[1]["id"]}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_aid_year_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        self._import(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-pell-schedule"], fconn, ns(
            limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "aid_year_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_pell_schedule") == 2


# ---------------------------------------------------------------------------
# finaid-list-verification-requests -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_verification_request.
# ---------------------------------------------------------------------------
class TestListVerificationRequests:
    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, _peid2, isir2 = _second_student(fconn, s)
        req1 = call_action(FA["finaid-create-verification-request"], fconn, ns(
            isir_id=s["isir_id"], student_id=s["student_id"],
            company_id=s["company_id"], verification_group="V1",
            deadline_date="2025-06-01", requested_date="2025-05-01",
            assigned_to=None))
        assert is_ok(req1), req1
        req2 = call_action(FA["finaid-create-verification-request"], fconn, ns(
            isir_id=isir2, student_id=sid2, company_id=s["company_id"],
            verification_group="V4", deadline_date="2025-07-01",
            requested_date="2025-05-02", assigned_to="counselor-b"))
        assert is_ok(req2), req2
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-verification-requests"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["verification_requests"]}
        assert got == {req1["id"], req2["id"]}
        stored1 = _row(fconn, "finaid_verification_request", req1["id"])
        assert stored1["verification_group"] == "V1"
        assert stored1["status"] == "initiated"
        assert stored1["student_id"] == s["student_id"]
        assert stored1["deadline_date"] == "2025-06-01"
        stored2 = _row(fconn, "finaid_verification_request", req2["id"])
        assert stored2["verification_group"] == "V4"
        assert stored2["assigned_to"] == "counselor-b"
        mine = call_action(FA["finaid-list-verification-requests"], fconn, ns(
            company_id=s["company_id"], student_id=s["student_id"],
            aid_year_id=None, status=None, limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["verification_requests"][0]["id"] == req1["id"]
        assigned = call_action(FA["finaid-list-verification-requests"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            status="initiated", limit=50, offset=0))
        assert is_ok(assigned), assigned
        assert assigned["count"] == 2
        page0 = call_action(FA["finaid-list-verification-requests"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            status=None, limit=1, offset=0))
        page1 = call_action(FA["finaid-list-verification-requests"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            status=None, limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["verification_requests"][0]["id"],
                page1["verification_requests"][0]["id"]} == {req1["id"], req2["id"]}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        req = call_action(FA["finaid-create-verification-request"], fconn, ns(
            isir_id=s["isir_id"], student_id=s["student_id"],
            company_id=s["company_id"], verification_group="V1",
            deadline_date="2025-06-01", requested_date=None, assigned_to=None))
        assert is_ok(req), req
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-verification-requests"], fconn, ns(
            company_id=None, student_id=None, aid_year_id=None,
            status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_verification_request") == 1


# ---------------------------------------------------------------------------
# finaid-list-verification-documents -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_verification_document.
# ---------------------------------------------------------------------------
class TestListVerificationDocuments:
    def test_payload_mirrors_stored_docs_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        req = call_action(FA["finaid-create-verification-request"], fconn, ns(
            isir_id=s["isir_id"], student_id=s["student_id"],
            company_id=s["company_id"], verification_group="V1",
            deadline_date="2025-06-01", requested_date="2025-05-01",
            assigned_to=None))
        assert is_ok(req), req
        assert req["documents_created"] == 3
        extra = call_action(FA["finaid-add-verification-document"], fconn, ns(
            verification_request_id=req["id"], student_id=s["student_id"],
            company_id=s["company_id"], document_type="other",
            document_description="Extra bank statement", is_required=1))
        assert is_ok(extra), extra
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-verification-documents"], fconn, ns(
            verification_request_id=req["id"]))
        assert is_ok(r), r
        assert r["count"] == 4
        by_type = {row["document_type"]: row for row in r["documents"]}
        assert sorted(by_type) == ["household_verification", "other", "tax_transcript", "w2"]
        for row in r["documents"]:
            stored = _row(fconn, "finaid_verification_document", row["id"])
            for key in ("verification_request_id", "student_id", "document_type",
                        "document_description", "is_required",
                        "submission_status", "company_id"):
                assert row[key] == stored[key], key
            assert stored["submission_status"] == "not_submitted"
            assert stored["is_required"] == 1
        assert by_type["other"]["document_description"] == "Extra bank statement"
        assert by_type["tax_transcript"]["verification_request_id"] == req["id"]
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_request_id_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        req = call_action(FA["finaid-create-verification-request"], fconn, ns(
            isir_id=s["isir_id"], student_id=s["student_id"],
            company_id=s["company_id"], verification_group="V1",
            deadline_date="2025-06-01", requested_date=None, assigned_to=None))
        assert is_ok(req), req
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-verification-documents"], fconn, ns())
        assert is_error(r)
        assert r["message"] == "verification_request_id is required"
        assert _snapshot(fconn) == before
        t = Table("finaid_verification_document")
        got = fconn.execute(
            Q.from_(t).select(fn.Count("*")).get_sql()).fetchone()[0]
        assert got == 3


# ---------------------------------------------------------------------------
# finaid-list-sap-evaluations -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_sap_evaluation.
# ---------------------------------------------------------------------------
class TestListSapEvaluations:
    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, _peid2, _isir2 = _second_student(fconn, s)
        eval_sat = _sap_eval(fconn, s, s["student_id"], "3.50", "12", "12")
        eval_fsp = _sap_eval(fconn, s, sid2, "1.00", "12", "5")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-sap-evaluations"], fconn, ns(
            company_id=s["company_id"], student_id=None, academic_term_id=None,
            sap_status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["sap_evaluations"]}
        assert got == {eval_sat, eval_fsp}
        stored_sat = _row(fconn, "finaid_sap_evaluation", eval_sat)
        assert stored_sat["sap_status"] == "SAT"
        assert stored_sat["gpa_earned"] == "3.50"
        assert Decimal(stored_sat["gpa_earned"]) == Decimal("3.50")
        assert stored_sat["credits_attempted"] == "12.00"
        assert stored_sat["completion_rate"] == "1.00"
        assert Decimal(stored_sat["completion_rate"]) == Decimal("1.00")
        assert stored_sat["holds_placed"] == 0
        payload_sat = [x for x in r["sap_evaluations"] if x["id"] == eval_sat][0]
        for key in ("student_id", "academic_term_id", "sap_status",
                    "gpa_earned", "completion_rate", "company_id"):
            assert payload_sat[key] == stored_sat[key], key
        stored_fsp = _row(fconn, "finaid_sap_evaluation", eval_fsp)
        assert stored_fsp["sap_status"] == "FSP"
        assert stored_fsp["holds_placed"] == 1
        assert stored_fsp["completion_meets_standard"] == 0
        sat_only = call_action(FA["finaid-list-sap-evaluations"], fconn, ns(
            company_id=s["company_id"], student_id=None, academic_term_id=None,
            sap_status="SAT", limit=50, offset=0))
        assert is_ok(sat_only), sat_only
        assert sat_only["count"] == 1
        assert sat_only["sap_evaluations"][0]["id"] == eval_sat
        mine = call_action(FA["finaid-list-sap-evaluations"], fconn, ns(
            company_id=s["company_id"], student_id=sid2, academic_term_id=None,
            sap_status=None, limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["sap_evaluations"][0]["id"] == eval_fsp
        page0 = call_action(FA["finaid-list-sap-evaluations"], fconn, ns(
            company_id=s["company_id"], student_id=None, academic_term_id=None,
            sap_status=None, limit=1, offset=0))
        page1 = call_action(FA["finaid-list-sap-evaluations"], fconn, ns(
            company_id=s["company_id"], student_id=None, academic_term_id=None,
            sap_status=None, limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["sap_evaluations"][0]["id"],
                page1["sap_evaluations"][0]["id"]} == {eval_sat, eval_fsp}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _sap_eval(fconn, s, s["student_id"], "3.50", "12", "12")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-sap-evaluations"], fconn, ns(
            company_id=None, student_id=None, academic_term_id=None,
            sap_status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_sap_evaluation") == 1


# ---------------------------------------------------------------------------
# finaid-list-sap-appeals -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_sap_appeal.
# ---------------------------------------------------------------------------
class TestListSapAppeals:
    def _appeal(self, conn, s, student_id, eval_id, reason, date):
        r = call_action(FA["finaid-submit-sap-appeal"], conn, ns(
            sap_evaluation_id=eval_id, student_id=student_id,
            company_id=s["company_id"], appeal_reason=reason,
            reason_narrative="Narrative for " + reason,
            academic_plan="Plan for " + reason,
            supporting_documents="[]", submitted_date=date))
        assert is_ok(r), r
        return r["id"]

    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, _peid2, _isir2 = _second_student(fconn, s)
        eval1 = _sap_eval(fconn, s, s["student_id"], "1.00", "12", "5")
        eval2 = _sap_eval(fconn, s, sid2, "1.00", "12", "4")
        appeal1 = self._appeal(fconn, s, s["student_id"], eval1, "illness", "2025-12-05")
        appeal2 = self._appeal(fconn, s, sid2, eval2, "injury", "2025-12-06")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-sap-appeals"], fconn, ns(
            company_id=s["company_id"], student_id=None, status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["sap_appeals"]}
        assert got == {appeal1, appeal2}
        stored1 = _row(fconn, "finaid_sap_appeal", appeal1)
        assert stored1["appeal_reason"] == "illness"
        assert stored1["status"] == "submitted"
        assert stored1["submitted_date"] == "2025-12-05"
        assert stored1["sap_evaluation_id"] == eval1
        assert stored1["student_id"] == s["student_id"]
        payload1 = [x for x in r["sap_appeals"] if x["id"] == appeal1][0]
        for key in ("sap_evaluation_id", "student_id", "appeal_reason",
                    "status", "submitted_date", "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_sap_appeal", appeal2)
        assert stored2["appeal_reason"] == "injury"
        assert stored2["submitted_date"] == "2025-12-06"
        mine = call_action(FA["finaid-list-sap-appeals"], fconn, ns(
            company_id=s["company_id"], student_id=sid2, status=None,
            limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["sap_appeals"][0]["id"] == appeal2
        submitted = call_action(FA["finaid-list-sap-appeals"], fconn, ns(
            company_id=s["company_id"], student_id=None, status="submitted",
            limit=50, offset=0))
        assert is_ok(submitted), submitted
        assert submitted["count"] == 2
        page0 = call_action(FA["finaid-list-sap-appeals"], fconn, ns(
            company_id=s["company_id"], student_id=None, status=None,
            limit=1, offset=0))
        page1 = call_action(FA["finaid-list-sap-appeals"], fconn, ns(
            company_id=s["company_id"], student_id=None, status=None,
            limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["sap_appeals"][0]["id"],
                page1["sap_appeals"][0]["id"]} == {appeal1, appeal2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        eval1 = _sap_eval(fconn, s, s["student_id"], "1.00", "12", "5")
        self._appeal(fconn, s, s["student_id"], eval1, "illness", "2025-12-05")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-sap-appeals"], fconn, ns(
            company_id=None, student_id=None, status=None,
            limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_sap_appeal") == 1


# ---------------------------------------------------------------------------
# finaid-list-r2t4s -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_r2t4_calculation.
# ---------------------------------------------------------------------------
class TestListR2t4s:
    def _r2t4(self, conn, s, student_id, pkg_id, wtype, det_date):
        r = call_action(FA["finaid-create-r2t4"], conn, ns(
            student_id=student_id, academic_term_id=s["term_id"],
            award_package_id=pkg_id, company_id=s["company_id"],
            withdrawal_type=wtype, withdrawal_date="2025-10-01",
            last_date_of_attendance="2025-10-01",
            determination_date=det_date,
            payment_period_start="2025-08-25",
            payment_period_end="2025-12-20", payment_period_days=117))
        assert is_ok(r), r
        return r["id"]

    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, peid2, isir2 = _second_student(fconn, s)
        pkg1 = _package(fconn, s)
        pkg2 = _package(fconn, s, student_id=sid2, peid=peid2, isir=isir2)
        calc1 = self._r2t4(fconn, s, s["student_id"], pkg1, "official", "2025-10-05")
        calc2 = self._r2t4(fconn, s, sid2, pkg2, "unofficial", "2025-11-01")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-r2t4s"], fconn, ns(
            company_id=s["company_id"], student_id=None, status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["r2t4_calculations"]}
        assert got == {calc1, calc2}
        stored1 = _row(fconn, "finaid_r2t4_calculation", calc1)
        assert stored1["withdrawal_type"] == "official"
        assert stored1["status"] == "calculated"
        assert stored1["institution_return_due_date"] == "2025-11-19"
        assert stored1["student_id"] == s["student_id"]
        assert stored1["earned_aid"] == "0"
        assert Decimal(stored1["earned_aid"]) == Decimal("0")
        assert stored1["total_aid_disbursed"] == "0"
        assert Decimal(stored1["total_aid_disbursed"]) == Decimal("0")
        payload1 = [x for x in r["r2t4_calculations"] if x["id"] == calc1][0]
        for key in ("student_id", "academic_term_id", "withdrawal_type",
                    "determination_date", "institution_return_due_date",
                    "status", "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_r2t4_calculation", calc2)
        assert stored2["withdrawal_type"] == "unofficial"
        assert stored2["institution_return_due_date"] == "2025-12-16"
        mine = call_action(FA["finaid-list-r2t4s"], fconn, ns(
            company_id=s["company_id"], student_id=sid2, status=None,
            limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["r2t4_calculations"][0]["id"] == calc2
        calc_status = call_action(FA["finaid-list-r2t4s"], fconn, ns(
            company_id=s["company_id"], student_id=None, status="calculated",
            limit=50, offset=0))
        assert is_ok(calc_status), calc_status
        assert calc_status["count"] == 2
        page0 = call_action(FA["finaid-list-r2t4s"], fconn, ns(
            company_id=s["company_id"], student_id=None, status=None,
            limit=1, offset=0))
        page1 = call_action(FA["finaid-list-r2t4s"], fconn, ns(
            company_id=s["company_id"], student_id=None, status=None,
            limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["r2t4_calculations"][0]["id"],
                page1["r2t4_calculations"][0]["id"]} == {calc1, calc2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        pkg1 = _package(fconn, s)
        self._r2t4(fconn, s, s["student_id"], pkg1, "official", "2025-10-05")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-r2t4s"], fconn, ns(
            company_id=None, student_id=None, status=None,
            limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_r2t4_calculation") == 1


# ---------------------------------------------------------------------------
# finaid-list-professional-judgments -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_professional_judgment.
# ---------------------------------------------------------------------------
class TestListProfessionalJudgments:
    def _pj(self, conn, s, student_id, pj_type, pj_reason, orig, adj):
        r = call_action(FA["finaid-add-professional-judgment"], conn, ns(
            student_id=student_id, aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], pj_type=pj_type, pj_reason=pj_reason,
            reason_narrative="Narrative " + pj_type,
            data_element_changed="agi", original_value=orig,
            adjusted_value=adj, effective_date="2025-09-01",
            authorized_by="director-a", authorization_date="2025-09-02",
            supervisor_review_required=0, award_package_id=None,
            supporting_documents="[]"))
        assert is_ok(r), r
        return r["id"]

    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, _peid2, _isir2 = _second_student(fconn, s)
        pj1 = self._pj(fconn, s, s["student_id"], "sai_adjustment",
                       "job_loss", "50000", "30000")
        pj2 = self._pj(fconn, s, sid2, "coa_adjustment",
                       "illness_injury", "29800", "34800")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-professional-judgments"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            pj_type=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["professional_judgments"]}
        assert got == {pj1, pj2}
        stored1 = _row(fconn, "finaid_professional_judgment", pj1)
        assert stored1["pj_type"] == "sai_adjustment"
        assert stored1["pj_reason"] == "job_loss"
        assert stored1["original_value"] == "50000"
        assert stored1["adjusted_value"] == "30000"
        assert stored1["effective_date"] == "2025-09-01"
        payload1 = [x for x in r["professional_judgments"] if x["id"] == pj1][0]
        for key in ("student_id", "aid_year_id", "pj_type", "pj_reason",
                    "original_value", "adjusted_value", "effective_date",
                    "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_professional_judgment", pj2)
        assert stored2["pj_type"] == "coa_adjustment"
        assert stored2["pj_reason"] == "illness_injury"
        typed = call_action(FA["finaid-list-professional-judgments"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            pj_type="sai_adjustment", limit=50, offset=0))
        assert is_ok(typed), typed
        assert typed["count"] == 1
        assert typed["professional_judgments"][0]["id"] == pj1
        mine = call_action(FA["finaid-list-professional-judgments"], fconn, ns(
            company_id=s["company_id"], student_id=sid2, aid_year_id=None,
            pj_type=None, limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["professional_judgments"][0]["id"] == pj2
        page0 = call_action(FA["finaid-list-professional-judgments"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            pj_type=None, limit=1, offset=0))
        page1 = call_action(FA["finaid-list-professional-judgments"], fconn, ns(
            company_id=s["company_id"], student_id=None, aid_year_id=None,
            pj_type=None, limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["professional_judgments"][0]["id"],
                page1["professional_judgments"][0]["id"]} == {pj1, pj2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        self._pj(fconn, s, s["student_id"], "sai_adjustment",
                 "job_loss", "50000", "30000")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-professional-judgments"], fconn, ns(
            company_id=None, student_id=None, aid_year_id=None,
            pj_type=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_professional_judgment") == 1


# ---------------------------------------------------------------------------
# finaid-list-scholarship-programs -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_scholarship_program.
# ---------------------------------------------------------------------------
class TestListScholarshipPrograms:
    def test_payload_mirrors_stored_money_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        prog1 = _program(fconn, s, "MERIT-M407A", "merit", "5000.00", "100000.00")
        prog2 = _program(fconn, s, "NEED-M407B", "need_based", "2500.00", "50000.00")
        before = _snapshot(fconn)
        r = call_action(SC["finaid-list-scholarship-programs"], fconn, ns(
            company_id=s["company_id"], scholarship_type=None, status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["programs"]}
        assert got == {prog1, prog2}
        stored1 = _row(fconn, "finaid_scholarship_program", prog1)
        assert stored1["code"] == "MERIT-M407A"
        assert stored1["scholarship_type"] == "merit"
        assert stored1["award_amount"] == "5000.00"
        assert Decimal(stored1["award_amount"]) == Decimal("5000.00")
        assert stored1["annual_budget"] == "100000.00"
        assert Decimal(stored1["annual_budget"]) == Decimal("100000.00")
        assert stored1["budget_remaining"] == "100000.00"
        assert Decimal(stored1["budget_remaining"]) == Decimal("100000.00")
        assert stored1["is_active"] == 1
        payload1 = [x for x in r["programs"] if x["id"] == prog1][0]
        for key in ("name", "code", "scholarship_type", "award_amount",
                    "annual_budget", "budget_remaining", "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_scholarship_program", prog2)
        assert stored2["award_amount"] == "2500.00"
        assert Decimal(stored2["award_amount"]) == Decimal("2500.00")
        merit = call_action(SC["finaid-list-scholarship-programs"], fconn, ns(
            company_id=s["company_id"], scholarship_type="merit", status=None,
            limit=50, offset=0))
        assert is_ok(merit), merit
        assert merit["count"] == 1
        assert merit["programs"][0]["id"] == prog1
        page0 = call_action(SC["finaid-list-scholarship-programs"], fconn, ns(
            company_id=s["company_id"], scholarship_type=None, status=None,
            limit=1, offset=0))
        page1 = call_action(SC["finaid-list-scholarship-programs"], fconn, ns(
            company_id=s["company_id"], scholarship_type=None, status=None,
            limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["programs"][0]["id"],
                page1["programs"][0]["id"]} == {prog1, prog2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _program(fconn, s, "MERIT-M407A", "merit", "5000.00", "100000.00")
        before = _snapshot(fconn)
        r = call_action(SC["finaid-list-scholarship-programs"], fconn, ns(
            company_id=None, scholarship_type=None, status=None,
            limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_scholarship_program") == 1


# ---------------------------------------------------------------------------
# finaid-list-scholarship-applications -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_scholarship_application.
# ---------------------------------------------------------------------------
class TestListScholarshipApplications:
    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, _peid2, _isir2 = _second_student(fconn, s)
        prog = _program(fconn, s, "MERIT-M407A", "merit", "5000.00", "100000.00")
        app1 = _apply(fconn, s, prog, s["student_id"], "3.50")
        app2 = _apply(fconn, s, prog, sid2, "3.80")
        before = _snapshot(fconn)
        r = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, status=None, aid_year_id=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["applications"]}
        assert got == {app1, app2}
        stored1 = _row(fconn, "finaid_scholarship_application", app1)
        assert stored1["status"] == "submitted"
        assert stored1["gpa_at_application"] == "3.50"
        assert Decimal(stored1["gpa_at_application"]) == Decimal("3.50")
        assert stored1["submission_date"] == "2025-07-01"
        assert stored1["scholarship_program_id"] == prog
        payload1 = [x for x in r["applications"] if x["id"] == app1][0]
        for key in ("scholarship_program_id", "student_id", "aid_year_id",
                    "status", "gpa_at_application", "submission_date",
                    "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_scholarship_application", app2)
        assert stored2["gpa_at_application"] == "3.80"
        assert Decimal(stored2["gpa_at_application"]) == Decimal("3.80")
        # KNOWN BEHAVIOUR (not fixed): the handler reads scholarship_program_id,
        # status, aid_year_id and reviewer_id but never reads student_id, so a
        # student_id filter is silently ignored and both rows come back.
        ignored = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=s["company_id"], student_id=sid2,
            scholarship_program_id=None, status=None, aid_year_id=None,
            limit=50, offset=0))
        assert is_ok(ignored), ignored
        assert ignored["count"] == 2
        assert {row["id"] for row in ignored["applications"]} == {app1, app2}
        for_year = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, status=None,
            aid_year_id=s["aid_year_id"],
            limit=50, offset=0))
        assert is_ok(for_year), for_year
        assert for_year["count"] == 2
        for_prog = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=prog, status=None, aid_year_id=None,
            limit=50, offset=0))
        assert is_ok(for_prog), for_prog
        assert for_prog["count"] == 2
        page0 = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, status=None, aid_year_id=None,
            limit=1, offset=0))
        page1 = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, status=None, aid_year_id=None,
            limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["applications"][0]["id"],
                page1["applications"][0]["id"]} == {app1, app2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        prog = _program(fconn, s, "MERIT-M407A", "merit", "5000.00", "100000.00")
        _apply(fconn, s, prog, s["student_id"], "3.50")
        before = _snapshot(fconn)
        r = call_action(SC["finaid-list-scholarship-applications"], fconn, ns(
            company_id=None, student_id=None, scholarship_program_id=None,
            status=None, aid_year_id=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_scholarship_application") == 1


# ---------------------------------------------------------------------------
# finaid-list-scholarship-renewals -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_scholarship_renewal.
# ---------------------------------------------------------------------------
class TestListScholarshipRenewals:
    def _renew(self, conn, s, app_id, gpa, credits):
        r = call_action(SC["finaid-generate-scholarship-renewal"], conn, ns(
            scholarship_application_id=app_id, academic_term_id=s["term_id"],
            company_id=s["company_id"], gpa_at_evaluation=gpa,
            credits_attempted=credits, evaluated_by="reviewer-a"))
        assert is_ok(r), r
        return r["id"]

    def test_payload_mirrors_stored_rows_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, _peid2, _isir2 = _second_student(fconn, s)
        prog = _program(fconn, s, "MERIT-M407A", "merit", "5000.00", "100000.00")
        app1 = _apply(fconn, s, prog, s["student_id"], "3.60")
        app2 = _apply(fconn, s, prog, sid2, "3.70")
        ren1 = self._renew(fconn, s, app1, "3.60", 15)
        ren2 = self._renew(fconn, s, app2, "1.50", 15)
        before = _snapshot(fconn)
        r = call_action(SC["finaid-list-scholarship-renewals"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, renewal_status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["renewals"]}
        assert got == {ren1, ren2}
        stored1 = _row(fconn, "finaid_scholarship_renewal", ren1)
        assert stored1["renewal_status"] == "renewed"
        assert stored1["meets_criteria"] == 1
        assert stored1["gpa_at_evaluation"] == "3.60"
        assert Decimal(stored1["gpa_at_evaluation"]) == Decimal("3.60")
        assert stored1["credits_attempted"] == 15
        assert stored1["scholarship_application_id"] == app1
        payload1 = [x for x in r["renewals"] if x["id"] == ren1][0]
        for key in ("scholarship_application_id", "student_id",
                    "scholarship_program_id", "academic_term_id",
                    "renewal_status", "gpa_at_evaluation", "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_scholarship_renewal", ren2)
        assert stored2["renewal_status"] == "suspended"
        assert stored2["meets_criteria"] == 0
        assert Decimal(stored2["gpa_at_evaluation"]) == Decimal("1.50")
        renewed = call_action(SC["finaid-list-scholarship-renewals"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, renewal_status="renewed",
            limit=50, offset=0))
        assert is_ok(renewed), renewed
        assert renewed["count"] == 1
        assert renewed["renewals"][0]["id"] == ren1
        mine = call_action(SC["finaid-list-scholarship-renewals"], fconn, ns(
            company_id=s["company_id"], student_id=sid2,
            scholarship_program_id=None, renewal_status=None,
            limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["renewals"][0]["id"] == ren2
        page0 = call_action(SC["finaid-list-scholarship-renewals"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, renewal_status=None,
            limit=1, offset=0))
        page1 = call_action(SC["finaid-list-scholarship-renewals"], fconn, ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, renewal_status=None,
            limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["renewals"][0]["id"],
                page1["renewals"][0]["id"]} == {ren1, ren2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        prog = _program(fconn, s, "MERIT-M407A", "merit", "5000.00", "100000.00")
        app1 = _apply(fconn, s, prog, s["student_id"], "3.60")
        self._renew(fconn, s, app1, "3.60", 15)
        before = _snapshot(fconn)
        r = call_action(SC["finaid-list-scholarship-renewals"], fconn, ns(
            company_id=None, student_id=None, scholarship_program_id=None,
            renewal_status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_scholarship_renewal") == 1


# ---------------------------------------------------------------------------
# finaid-list-work-study-jobs -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_work_study_job.
# ---------------------------------------------------------------------------
class TestListWorkStudyJobs:
    def test_payload_mirrors_stored_money_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        job1 = _job(fconn, s, "Library Assistant", "on_campus", "12.50")
        job2 = _job(fconn, s, "Community Tutor", "off_campus_community", "15.00",
                    hours="10", positions=2)
        before = _snapshot(fconn)
        r = call_action(WS["finaid-list-work-study-jobs"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None, job_type=None,
            status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["jobs"]}
        assert got == {job1, job2}
        stored1 = _row(fconn, "finaid_work_study_job", job1)
        assert stored1["job_title"] == "Library Assistant"
        assert stored1["job_type"] == "on_campus"
        assert stored1["pay_rate"] == "12.50"
        assert Decimal(stored1["pay_rate"]) == Decimal("12.50")
        assert stored1["hours_per_week"] == "15"
        assert stored1["total_positions"] == 3
        assert stored1["filled_positions"] == 0
        assert stored1["status"] == "open"
        assert stored1["aid_year_id"] == s["aid_year_id"]
        payload1 = [x for x in r["jobs"] if x["id"] == job1][0]
        for key in ("job_title", "job_type", "pay_rate", "hours_per_week",
                    "total_positions", "filled_positions", "aid_year_id",
                    "status", "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_work_study_job", job2)
        assert stored2["pay_rate"] == "15.00"
        assert Decimal(stored2["pay_rate"]) == Decimal("15.00")
        campus = call_action(WS["finaid-list-work-study-jobs"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None,
            job_type="on_campus", status=None, limit=50, offset=0))
        assert is_ok(campus), campus
        assert campus["count"] == 1
        assert campus["jobs"][0]["id"] == job1
        for_year = call_action(WS["finaid-list-work-study-jobs"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            job_type=None, status=None, limit=50, offset=0))
        assert is_ok(for_year), for_year
        assert for_year["count"] == 2
        page0 = call_action(WS["finaid-list-work-study-jobs"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None, job_type=None,
            status=None, limit=1, offset=0))
        page1 = call_action(WS["finaid-list-work-study-jobs"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None, job_type=None,
            status=None, limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["jobs"][0]["id"],
                page1["jobs"][0]["id"]} == {job1, job2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _job(fconn, s, "Library Assistant", "on_campus", "12.50")
        before = _snapshot(fconn)
        r = call_action(WS["finaid-list-work-study-jobs"], fconn, ns(
            company_id=None, aid_year_id=None, job_type=None,
            status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_work_study_job") == 1


# ---------------------------------------------------------------------------
# finaid-list-work-study-assignments -- stored rows (read-only).
# No ledger effect: a pure SELECT over finaid_work_study_assignment.
# ---------------------------------------------------------------------------
class TestListWorkStudyAssignments:
    def _assign(self, conn, s, student_id, award_id, job_id, limit):
        r = call_action(WS["finaid-assign-student-to-job"], conn, ns(
            student_id=student_id, award_id=award_id, job_id=job_id,
            aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
            company_id=s["company_id"], start_date="2025-09-01",
            end_date="2025-12-20", award_limit=limit))
        assert is_ok(r), r
        return r["id"]

    def test_payload_mirrors_stored_money_filters_and_leaves_db_unchanged(self, fconn):
        s = _build_env(fconn)
        sid2, peid2, isir2 = _second_student(fconn, s)
        pkg1 = _package(fconn, s)
        award1 = _fws_award(fconn, s, pkg1, s["student_id"], "3000.00")
        job1 = _job(fconn, s, "Library Assistant", "on_campus", "12.50")
        pkg2 = _package(fconn, s, student_id=sid2, peid=peid2, isir=isir2)
        award2 = _fws_award(fconn, s, pkg2, sid2, "2000.00")
        job2 = _job(fconn, s, "Community Tutor", "off_campus_community", "15.00",
                    hours="10", positions=2)
        asg1 = self._assign(fconn, s, s["student_id"], award1, job1, "3000.00")
        asg2 = self._assign(fconn, s, sid2, award2, job2, "2000.00")
        before = _snapshot(fconn)
        r = call_action(WS["finaid-list-work-study-assignments"], fconn, ns(
            company_id=s["company_id"], student_id=None, job_id=None,
            status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        got = {row["id"] for row in r["assignments"]}
        assert got == {asg1, asg2}
        stored1 = _row(fconn, "finaid_work_study_assignment", asg1)
        assert stored1["student_id"] == s["student_id"]
        assert stored1["job_id"] == job1
        assert stored1["award_id"] == award1
        assert stored1["award_limit"] == "3000.00"
        assert Decimal(stored1["award_limit"]) == Decimal("3000.00")
        assert stored1["earned_to_date"] == "0.00"
        assert Decimal(stored1["earned_to_date"]) == Decimal("0.00")
        assert stored1["status"] == "active"
        payload1 = [x for x in r["assignments"] if x["id"] == asg1][0]
        for key in ("student_id", "award_id", "job_id", "aid_year_id",
                    "academic_term_id", "award_limit", "earned_to_date",
                    "status", "company_id"):
            assert payload1[key] == stored1[key], key
        stored2 = _row(fconn, "finaid_work_study_assignment", asg2)
        assert stored2["award_limit"] == "2000.00"
        assert Decimal(stored2["award_limit"]) == Decimal("2000.00")
        mine = call_action(WS["finaid-list-work-study-assignments"], fconn, ns(
            company_id=s["company_id"], student_id=sid2, job_id=None,
            status=None, limit=50, offset=0))
        assert is_ok(mine), mine
        assert mine["count"] == 1
        assert mine["assignments"][0]["id"] == asg2
        for_job = call_action(WS["finaid-list-work-study-assignments"], fconn, ns(
            company_id=s["company_id"], student_id=None, job_id=job1,
            status=None, limit=50, offset=0))
        assert is_ok(for_job), for_job
        assert for_job["count"] == 1
        assert for_job["assignments"][0]["id"] == asg1
        page0 = call_action(WS["finaid-list-work-study-assignments"], fconn, ns(
            company_id=s["company_id"], student_id=None, job_id=None,
            status=None, limit=1, offset=0))
        page1 = call_action(WS["finaid-list-work-study-assignments"], fconn, ns(
            company_id=s["company_id"], student_id=None, job_id=None,
            status=None, limit=1, offset=1))
        assert page0["count"] == 1 and page1["count"] == 1
        assert {page0["assignments"][0]["id"],
                page1["assignments"][0]["id"]} == {asg1, asg2}
        assert _snapshot(fconn) == before
        # No ledger legs: pure SELECT, never journals.

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        pkg1 = _package(fconn, s)
        award1 = _fws_award(fconn, s, pkg1, s["student_id"], "3000.00")
        job1 = _job(fconn, s, "Library Assistant", "on_campus", "12.50")
        self._assign(fconn, s, s["student_id"], award1, job1, "3000.00")
        before = _snapshot(fconn)
        r = call_action(WS["finaid-list-work-study-assignments"], fconn, ns(
            company_id=None, student_id=None, job_id=None,
            status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "--company-id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_work_study_assignment") == 1
