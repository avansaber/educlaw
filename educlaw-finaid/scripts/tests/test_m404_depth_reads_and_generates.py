"""M404 depth: behavioural evidence for 12 shape-or-routing-only actions.

Prior state (read before writing anything below):
- `finaid-get-aid-year` had a shape-only test (`TestAidYear.test_get` in
  `test_finaid.py`): it asserts the response is ok, never that the payload
  matches the stored `finaid_aid_year` row.
- `finaid-get-award`, `finaid-get-award-package`,
  `finaid-get-cost-of-attendance`, `finaid-get-disbursement`,
  `finaid-get-fund-allocation` and `finaid-get-isir` had NO module test at
  all; they were covered only by box-facing routability contracts
  (`testing/integration/contract/test_educlaw_finaid_contract.py`, e.g.
  `test_finaid_get_award_exists`) and CRUD smoke stubs
  (`testing/integration/smoke/test_educlaw_finaid_auto.py`) that assert an
  action can be reached, not what it does.
- `finaid-generate-r2t4-calculation`, `finaid-generate-sap-batch`,
  `finaid-generate-sap-evaluation`, `finaid-generate-scholarship-matches`
  and `finaid-generate-scholarship-renewal` likewise had only routability
  contracts (`test_finaid_generate_*_exists`).

Every test below observes the database through a fresh `get_connection()`
read-back built with PyPika (`erpclaw_lib.query`): the row that should exist
afterwards with exact values, the row that should have changed from what to
what, and what must NOT have changed. Catalog questions (does the table
exist) go through `erpclaw_lib.seam`. Money compares exact `Decimal`
strings, never float, never approximate.

Ledger scope, stated once so no later reader adds a balance assertion that
cannot hold: none of these 12 handlers reaches the general ledger. The seven
`get` actions are pure reads; the five `generate` actions write only their
own `finaid_*` tables (plus one `audit_log` line for the two scholarship
generators). Every per-action section repeats its own ledger note.

Signal depth per action (stored row unless noted):
- finaid-get-aid-year: stored row (read-only; payload mirrors row, DB equal).
- finaid-get-fund-allocation: stored row (read-only; payload mirrors row).
- finaid-get-cost-of-attendance: stored row (read-only; payload mirrors row).
- finaid-get-isir: stored row (read-only; payload mirrors row + cflags).
- finaid-get-award-package: stored row (read-only; payload mirrors row+awards).
- finaid-get-award: stored row (read-only; payload mirrors row).
- finaid-get-disbursement: stored row (read-only; payload mirrors row).
- finaid-generate-sap-evaluation: stored row (inserts/updates evaluation).
- finaid-generate-sap-batch: stored row (inserts one evaluation per student).
- finaid-generate-r2t4-calculation: stored row (updates the calculation row).
- finaid-generate-scholarship-matches: stored row (inserts award rows).
- finaid-generate-scholarship-renewal: stored row (inserts a renewal row).
"""
import importlib.util
import os
import shutil
import sys
from datetime import datetime, timezone
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


@pytest.fixture(scope="module")
def template_path(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("m404tpl") / "template.sqlite")
    _helpers.init_all_tables(path)
    assert _seam.table_exists("finaid_award", path)
    assert _seam.table_exists("finaid_sap_evaluation", path)
    assert _seam.table_exists("finaid_r2t4_calculation", path)
    assert _seam.table_exists("finaid_scholarship_renewal", path)
    return path


@pytest.fixture
def fconn(template_path, tmp_path):
    dest = str(tmp_path / "case.sqlite")
    shutil.copyfile(template_path, dest)
    conn = get_connection(dest)
    os.environ["ERPCLAW_DB_PATH"] = dest
    try:
        yield conn
    finally:
        conn.close()
        os.environ.pop("ERPCLAW_DB_PATH", None)


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


def _make_package(env_conn, s, aid_type="pell", offered="5000.00", accepted="4000.00"):
    conn = env_conn
    pkg = call_action(FA["finaid-create-award-package"], conn, ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", financial_need=None,
        acceptance_deadline=None, packaged_by=None, notes=None))
    assert is_ok(pkg), pkg
    award = call_action(FA["finaid-add-award"], conn, ns(
        award_package_id=pkg["id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None,
        notes=None))
    assert is_ok(award), award
    if accepted is not None:
        acc = call_action(FA["finaid-accept-award"], conn, ns(
            award_id=award["id"], accepted_amount=accepted,
            acceptance_date="2025-08-01"))
        assert is_ok(acc), acc
    return pkg["id"], award["id"]


def _disburse(conn, s, award_id, amount, date="2025-09-02", number=1):
    r = call_action(FA["finaid-record-award-disbursement"], conn, ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date=date, company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=number))
    assert is_ok(r), r
    return r["id"]


def _scholarship_program(conn, s, code="MERIT-AUTO"):
    r = call_action(SC["finaid-add-scholarship-program"], conn, ns(
        company_id=s["company_id"], name="Merit Auto " + code, code=code,
        description="", scholarship_type="merit", funding_source="endowment",
        award_method="auto_match", award_amount_type="fixed",
        award_amount="1000.00", min_award="0", max_award="0",
        annual_budget="50000", max_recipients=10, renewal_eligible=1,
        renewal_gpa_minimum="3.00", renewal_credits_minimum="12",
        eligibility_criteria="{}", application_deadline="2025-08-01",
        award_period="annual", applies_to_aid_type="institutional_scholarship",
        gl_account_id=""))
    assert is_ok(r), r
    return r["id"]


def _scholarship_application(conn, s, program_id, student_id=None, gpa="3.50"):
    r = call_action(SC["finaid-submit-scholarship-application"], conn, ns(
        scholarship_program_id=program_id,
        student_id=student_id or s["student_id"], aid_year_id=s["aid_year_id"],
        company_id=s["company_id"], essay_response="essay",
        gpa_at_application=gpa, submission_date="2025-07-01"))
    assert is_ok(r), r
    return r["id"]




# ---------------------------------------------------------------------------
# finaid-get-aid-year -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetAidYear:
    def test_payload_mirrors_the_stored_row_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        other = call_action(FA["finaid-add-aid-year"], fconn, ns(
            company_id=s["company_id"], aid_year_code="2026-2027",
            description="Next year", start_date="2026-07-01",
            end_date="2027-06-30", pell_max_award="7395"))
        assert is_ok(other), other
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-aid-year"], fconn, ns(id=s["aid_year_id"]))
        assert is_ok(r), r
        row = _row(fconn, "finaid_aid_year", s["aid_year_id"])
        assert row["aid_year_code"] == "2025-2026"
        assert Decimal(row["pell_max_award"]) == Decimal("7395")
        assert row["is_active"] == 1
        for key in ("aid_year_code", "description", "start_date", "end_date",
                    "pell_max_award", "company_id"):
            assert r[key] == row[key], key
        assert _snapshot(fconn) == before
        assert _row(fconn, "finaid_aid_year", other["id"])["aid_year_code"] == "2026-2027"

    def test_refuses_an_unknown_id_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-aid-year"], fconn, ns(id="no-such-year"))
        assert is_error(r)
        assert r["message"] == "Aid year not found"
        assert _snapshot(fconn) == before
        r = call_action(FA["finaid-get-aid-year"], fconn, ns())
        assert is_error(r)
        assert r["message"] == "id is required"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-get-fund-allocation -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetFundAllocation:
    def test_payload_mirrors_the_stored_row_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        added = call_action(FA["finaid-add-fund-allocation"], fconn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            fund_type="fseog", fund_name="FSEOG Campus Fund",
            total_allocation="25000.005"))
        assert is_ok(added), added
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-fund-allocation"], fconn, ns(id=added["id"]))
        assert is_ok(r), r
        row = _row(fconn, "finaid_fund_allocation", added["id"])
        assert row["total_allocation"] == "25000.01"
        assert Decimal(row["total_allocation"]) == Decimal("25000.01")
        assert row["committed_amount"] == "0"
        assert row["disbursed_amount"] == "0"
        assert row["available_amount"] == "25000.01"
        for key in ("fund_type", "fund_name", "total_allocation",
                    "committed_amount", "disbursed_amount", "available_amount",
                    "aid_year_id", "company_id"):
            assert r[key] == row[key], key
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_id_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        added = call_action(FA["finaid-add-fund-allocation"], fconn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            fund_type="fseog", fund_name="FSEOG Campus Fund",
            total_allocation="25000.00"))
        assert is_ok(added), added
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-fund-allocation"], fconn, ns(id="no-such-fund"))
        assert is_error(r)
        assert r["message"] == "Fund allocation not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-get-cost-of-attendance -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetCostOfAttendance:
    def test_payload_mirrors_the_stored_row_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-cost-of-attendance"], fconn,
                        ns(id=s["cost_of_attendance_id"]))
        assert is_ok(r), r
        row = _row(fconn, "finaid_cost_of_attendance", s["cost_of_attendance_id"])
        assert (row["tuition_fees"], row["books_supplies"], row["room_board"],
                row["transportation"], row["personal_expenses"],
                row["loan_fees"], row["total_coa"]) == (
                    "15000", "1200", "10000", "1500", "2000", "100", "29800")
        assert Decimal(row["total_coa"]) == Decimal("29800")
        for key in ("tuition_fees", "books_supplies", "room_board",
                    "transportation", "personal_expenses", "loan_fees",
                    "total_coa", "enrollment_status", "living_arrangement",
                    "aid_year_id", "company_id"):
            assert r[key] == row[key], key
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_id_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-cost-of-attendance"], fconn, ns(id="no-such-coa"))
        assert is_error(r)
        assert r["message"] == "COA not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-get-isir -- stored row (read-only).
# No ledger effect: a pure SELECT (+ cflag SELECT) that never touches
# journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetIsir:
    def test_payload_mirrors_the_stored_row_and_cflags(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-isir"], fconn, ns(isir_id=s["isir_id"]))
        assert is_ok(r), r
        row = _row(fconn, "finaid_isir", s["isir_id"])
        assert row["sai"] == "1500"
        assert Decimal(row["sai"]) == Decimal("1500")
        assert row["dependency_status"] == "dependent"
        assert row["status"] == "received"
        assert r["sai"] == row["sai"] == "1500"
        assert r["cflags"] == []
        cflags = fconn.execute(
            Q.from_(Table("finaid_isir_cflag")).select("*").where(
                Field("isir_id") == P()).get_sql(), (s["isir_id"],)).fetchall()
        assert list(cflags) == []
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_or_missing_id_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-isir"], fconn, ns(isir_id="no-such-isir"))
        assert is_error(r)
        assert r["message"] == "ISIR not found"
        assert _snapshot(fconn) == before
        r = call_action(FA["finaid-get-isir"], fconn, ns())
        assert is_error(r)
        assert r["message"] == "isir_id or id is required"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-get-award-package -- stored row (read-only).
# No ledger effect: a pure SELECT (+ awards SELECT) that never touches
# journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetAwardPackage:
    def test_payload_mirrors_the_stored_package_and_its_awards(self, fconn):
        s = _build_env(fconn)
        pkg_id, award_id = _make_package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-award-package"], fconn,
                        ns(award_package_id=pkg_id))
        assert is_ok(r), r
        row = _row(fconn, "finaid_award_package", pkg_id)
        assert row["financial_need"] == "28300.00"
        assert Decimal(row["financial_need"]) == Decimal("28300.00")
        assert row["total_grants"] == "5000.00"
        assert row["total_aid"] == "5000.00"
        assert row["status"] == "draft"
        assert r["financial_need"] == row["financial_need"]
        assert r["total_grants"] == row["total_grants"]
        assert r["total_aid"] == row["total_aid"]
        assert len(r["awards"]) == 1
        assert r["awards"][0]["id"] == award_id
        assert r["awards"][0]["offered_amount"] == "5000.00"
        assert r["awards"][0]["accepted_amount"] == "4000.00"
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_package_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _make_package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-award-package"], fconn,
                        ns(award_package_id="no-such-package"))
        assert is_error(r)
        assert r["message"] == "Award package not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-get-award -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetAward:
    def test_payload_mirrors_the_stored_award(self, fconn):
        s = _build_env(fconn)
        pkg_id, award_id = _make_package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-award"], fconn, ns(award_id=award_id))
        assert is_ok(r), r
        row = _row(fconn, "finaid_award", award_id)
        assert (row["offered_amount"], row["accepted_amount"],
                row["disbursed_amount"], row["acceptance_status"]) == (
                    "5000.00", "4000.00", "0", "accepted")
        assert Decimal(row["offered_amount"]) == Decimal("5000.00")
        assert Decimal(row["accepted_amount"]) == Decimal("4000.00")
        for key in ("offered_amount", "accepted_amount", "disbursed_amount",
                    "acceptance_status", "aid_type", "aid_source",
                    "award_package_id", "student_id"):
            assert r[key] == row[key], key
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_award_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _make_package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-award"], fconn, ns(award_id="no-such-award"))
        assert is_error(r)
        assert r["message"] == "Award not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-get-disbursement -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetDisbursement:
    def test_payload_mirrors_the_stored_disbursement(self, fconn):
        s = _build_env(fconn)
        _, award_id = _make_package(fconn, s)
        disb_id = _disburse(fconn, s, award_id, "1500.00")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-disbursement"], fconn, ns(id=disb_id))
        assert is_ok(r), r
        row = _row(fconn, "finaid_disbursement", disb_id)
        assert row["amount"] == "1500.00"
        assert Decimal(row["amount"]) == Decimal("1500.00")
        assert row["disbursement_type"] == "disbursement"
        assert row["disbursement_date"] == "2025-09-02"
        assert row["award_id"] == award_id
        for key in ("amount", "disbursement_type", "disbursement_date",
                    "award_id", "award_package_id", "student_id"):
            assert r[key] == row[key], key
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_disbursement_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _, award_id = _make_package(fconn, s)
        _disburse(fconn, s, award_id, "1500.00")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-get-disbursement"], fconn, ns(id="no-such-disb"))
        assert is_error(r)
        assert r["message"] == "Disbursement not found"
        assert _snapshot(fconn) == before
        r = call_action(FA["finaid-get-disbursement"], fconn, ns())
        assert is_error(r)
        assert r["message"] == "id is required"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-generate-sap-evaluation -- stored row (finaid_sap_evaluation).
# No ledger effect: inserts/updates the evaluation row only; never touches
# journal/gl tables.
# ---------------------------------------------------------------------------
class TestGenerateSapEvaluation:
    def _evaluate(self, conn, s, **over):
        args = dict(student_id=s["student_id"], academic_term_id=s["term_id"],
                    aid_year_id=s["aid_year_id"], company_id=s["company_id"],
                    gpa_earned="3.50", gpa_threshold="2.00",
                    credits_attempted="12", credits_completed="12",
                    completion_threshold="0.67", max_timeframe_credits="180",
                    projected_credits_remaining="60",
                    transfer_credits_attempted="0",
                    transfer_credits_completed="0",
                    evaluation_date="2025-12-01", evaluated_by="tester",
                    evaluation_type="automatic")
        args.update(over)
        return call_action(FA["finaid-generate-sap-evaluation"], conn, ns(**args))

    def test_passing_evaluation_writes_a_sat_row_with_exact_values(self, fconn):
        s = _build_env(fconn)
        assert _count(fconn, "finaid_sap_evaluation") == 0
        r = self._evaluate(fconn, s)
        assert is_ok(r), r
        assert r["sap_status"] == "SAT"
        assert r["completion_rate"] == "1.00"
        row = _row(fconn, "finaid_sap_evaluation", r["id"])
        assert row["sap_status"] == "SAT"
        assert row["gpa_earned"] == "3.50"
        assert Decimal(row["gpa_earned"]) == Decimal("3.50")
        assert row["gpa_threshold"] == "2.00"
        assert row["gpa_meets_standard"] == 1
        assert row["credits_attempted"] == "12.00"
        assert row["credits_completed"] == "12.00"
        assert row["completion_rate"] == "1.00"
        assert row["completion_meets_standard"] == 1
        assert row["max_timeframe_credits"] == "180.00"
        assert row["projected_credits_remaining"] == "60.00"
        assert row["max_timeframe_met"] == 1
        assert row["holds_placed"] == 0
        assert row["prior_sap_status"] == ""
        assert row["evaluation_date"] == "2025-12-01"
        assert r["sap_status"] == row["sap_status"]
        assert r["completion_rate"] == row["completion_rate"]
        assert _count(fconn, "finaid_sap_evaluation") == 1

    def test_second_run_updates_the_same_row_and_records_prior_status(self, fconn):
        s = _build_env(fconn)
        first = self._evaluate(fconn, s)
        assert is_ok(first), first
        second = self._evaluate(fconn, s, gpa_earned="1.00",
                                credits_completed="6",
                                evaluation_date="2025-12-15")
        assert is_ok(second), second
        assert second["id"] == first["id"]
        assert second["sap_status"] == "FSP"
        row = _row(fconn, "finaid_sap_evaluation", first["id"])
        assert row["sap_status"] == "FSP"
        assert row["gpa_earned"] == "1.00"
        assert row["gpa_meets_standard"] == 0
        assert row["completion_rate"] == "0.50"
        assert Decimal(row["completion_rate"]) == Decimal("0.50")
        assert row["completion_meets_standard"] == 0
        assert row["holds_placed"] == 1
        assert row["prior_sap_status"] == "SAT"
        assert _count(fconn, "finaid_sap_evaluation") == 1

    def test_refuses_a_missing_student_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-generate-sap-evaluation"], fconn, ns(
            academic_term_id=s["term_id"], company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == "student_id is required"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-generate-sap-batch -- stored row (finaid_sap_evaluation, one row per
# student without one yet).
# No ledger effect: inserts evaluation rows only; never touches journal/gl.
# Real behaviour pinned below: `evaluated` counts award packages scanned
# (including students that already have an evaluation), not rows inserted.
# ---------------------------------------------------------------------------
class TestGenerateSapBatch:
    def test_batch_inserts_only_missing_evaluations_but_counts_packages(self, fconn):
        s = _build_env(fconn)
        _make_package(fconn, s)
        first = call_action(FA["finaid-generate-sap-evaluation"], fconn, ns(
            student_id=s["student_id"], academic_term_id=s["term_id"],
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            gpa_earned="3.50", gpa_threshold="2.00",
            credits_attempted="12", credits_completed="12",
            completion_threshold="0.67", max_timeframe_credits="180",
            projected_credits_remaining="60",
            transfer_credits_attempted="0", transfer_credits_completed="0",
            evaluation_date="2025-12-01", evaluated_by="tester",
            evaluation_type="automatic"))
        assert is_ok(first), first
        sid2 = _helpers.seed_student(fconn, s["company_id"])
        peid2 = _helpers.seed_program_enrollment(
            fconn, sid2, s["program_id"], s["year_id"], s["company_id"])
        isir2 = _helpers.seed_isir(fconn, sid2, s["aid_year_id"], s["company_id"])
        pkg2 = call_action(FA["finaid-create-award-package"], fconn, ns(
            student_id=sid2, aid_year_id=s["aid_year_id"],
            academic_term_id=s["term_id"], company_id=s["company_id"],
            program_enrollment_id=peid2, isir_id=isir2,
            cost_of_attendance_id=s["cost_of_attendance_id"],
            enrollment_status="full_time", financial_need=None,
            acceptance_deadline=None, packaged_by=None, notes=None))
        assert is_ok(pkg2), pkg2
        r = call_action(FA["finaid-generate-sap-batch"], fconn, ns(
            academic_term_id=s["term_id"], company_id=s["company_id"]))
        assert is_ok(r), r
        assert r["evaluated"] == 2
        t = Table("finaid_sap_evaluation")
        rows = fconn.execute(
            Q.from_(t).select("*").where(
                t.academic_term_id == P()).get_sql(), (s["term_id"],)).fetchall()
        assert len(rows) == 2
        by_student = {dict(x)["student_id"]: dict(x) for x in rows}
        assert by_student[s["student_id"]]["id"] == first["id"]
        assert by_student[s["student_id"]]["sap_status"] == "SAT"
        assert by_student[sid2]["sap_status"] == "SAT"
        assert by_student[sid2]["evaluation_type"] == "automatic"

    def test_refuses_a_missing_term_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _make_package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-generate-sap-batch"], fconn,
                        ns(company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == "academic_term_id and company_id are required"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-generate-r2t4-calculation -- stored row (updates finaid_r2t4_calculation).
# No ledger effect: updates the calculation row only; the disbursement rows it
# reads are left untouched, and nothing reaches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGenerateR2t4Calculation:
    def _r2t4(self, conn, s, pkg_id):
        r = call_action(FA["finaid-create-r2t4"], conn, ns(
            student_id=s["student_id"], academic_term_id=s["term_id"],
            award_package_id=pkg_id, company_id=s["company_id"],
            withdrawal_type="official", withdrawal_date="2025-10-01",
            last_date_of_attendance="2025-10-01",
            determination_date="2025-10-05",
            payment_period_start="2025-08-25",
            payment_period_end="2025-12-20", payment_period_days=117))
        assert is_ok(r), r
        return r["id"]

    def test_calculation_updates_the_row_with_exact_amounts(self, fconn):
        s = _build_env(fconn)
        pkg_id, award_id = _make_package(fconn, s)
        _disburse(fconn, s, award_id, "1500.00")
        r2t4_id = self._r2t4(fconn, s, pkg_id)
        before_calc = _row(fconn, "finaid_r2t4_calculation", r2t4_id)
        assert before_calc["earned_aid"] == "0"
        assert before_calc["institution_return_due_date"] == "2025-11-19"
        disb_before = _count(fconn, "finaid_disbursement")
        r = call_action(FA["finaid-generate-r2t4-calculation"], fconn,
                        ns(id=r2t4_id))
        assert is_ok(r), r
        assert r["days_attended"] == 37
        assert r["percent_completed"] == "0.32"
        assert r["earned_aid"] == "474.36"
        assert r["unearned_aid"] == "1025.64"
        assert r["institution_return_amount"] == "512.82"
        assert r["student_return_amount"] == "512.82"
        row = _row(fconn, "finaid_r2t4_calculation", r2t4_id)
        assert row["days_attended"] == 37
        assert row["percent_completed"] == "0.32"
        assert row["total_aid_disbursed"] == "1500"
        assert Decimal(row["total_aid_disbursed"]) == Decimal("1500")
        assert row["earned_aid"] == "474.36"
        assert Decimal(row["earned_aid"]) == Decimal("474.36")
        assert row["unearned_aid"] == "1025.64"
        assert row["institution_return_amount"] == "512.82"
        assert Decimal(row["institution_return_amount"]) == Decimal("512.82")
        assert row["student_return_amount"] == "512.82"
        assert Decimal(row["earned_aid"]) + Decimal(row["unearned_aid"]) == Decimal("1500")
        assert Decimal(row["institution_return_amount"]) + Decimal(
            row["student_return_amount"]) == Decimal(row["unearned_aid"])
        assert row["status"] == "calculated"
        assert row["institution_return_due_date"] == "2025-11-19"
        assert _count(fconn, "finaid_disbursement") == disb_before

    def test_refuses_an_unknown_calculation_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id, award_id = _make_package(fconn, s)
        _disburse(fconn, s, award_id, "1500.00")
        self._r2t4(fconn, s, pkg_id)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-generate-r2t4-calculation"], fconn,
                        ns(id="no-such-r2t4"))
        assert is_error(r)
        assert r["message"] == "R2T4 calculation not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-generate-scholarship-matches -- stored row (finaid_award, one row per
# package per auto_match program).
# No ledger effect: inserts award rows only; never touches journal/gl tables.
# FINDING (documented, not fixed): the match writer inserts the award line
# directly and never refreshes the package totals, so the package still reads
# total_grants/total_aid '0' after a 1000.00 match. The test pins that real
# behaviour; fixing the totals roll-up is follow-up work.
# ---------------------------------------------------------------------------
class TestGenerateScholarshipMatches:
    def test_match_creates_one_pending_award_per_package(self, fconn):
        s = _build_env(fconn)
        program_id = _scholarship_program(fconn, s)
        pkg = call_action(FA["finaid-create-award-package"], fconn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            academic_term_id=s["term_id"], company_id=s["company_id"],
            program_enrollment_id=s["program_enrollment_id"],
            isir_id=s["isir_id"],
            cost_of_attendance_id=s["cost_of_attendance_id"],
            enrollment_status="full_time", financial_need=None,
            acceptance_deadline=None, packaged_by=None, notes=None))
        assert is_ok(pkg), pkg
        pkg_id = pkg["id"]
        assert _count(fconn, "finaid_award") == 0
        r = call_action(SC["finaid-generate-scholarship-matches"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"]))
        assert is_ok(r), r
        assert r["matches_created"] == 1
        assert r["programs_evaluated"] == 1
        t = Table("finaid_award")
        rows = fconn.execute(
            Q.from_(t).select("*").where(
                t.award_package_id == P()).get_sql(), (pkg_id,)).fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["aid_type"] == "institutional_scholarship"
        assert row["aid_source"] == "institutional"
        assert row["fund_source_id"] == program_id
        assert row["offered_amount"] == "1000.00"
        assert Decimal(row["offered_amount"]) == Decimal("1000.00")
        assert row["accepted_amount"] == "0"
        assert row["disbursed_amount"] == "0"
        assert row["acceptance_status"] == "pending"
        assert row["student_id"] == s["student_id"]
        assert row["aid_year_id"] == s["aid_year_id"]
        assert row["academic_term_id"] == s["term_id"]
        assert r["matches"][0]["award_id"] == row["id"]
        assert r["matches"][0]["offered_amount"] == "1000.00"
        totals = _row(fconn, "finaid_award_package", pkg_id)
        assert totals["total_grants"] == "0"
        assert totals["total_aid"] == "0"
        again = call_action(SC["finaid-generate-scholarship-matches"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"]))
        assert is_ok(again), again
        assert again["matches_created"] == 0
        assert _count(fconn, "finaid_award") == 1

    def test_refuses_an_unknown_aid_year_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _scholarship_program(fconn, s)
        pkg = call_action(FA["finaid-create-award-package"], fconn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            academic_term_id=s["term_id"], company_id=s["company_id"],
            program_enrollment_id=s["program_enrollment_id"],
            isir_id=s["isir_id"],
            cost_of_attendance_id=s["cost_of_attendance_id"],
            enrollment_status="full_time", financial_need=None,
            acceptance_deadline=None, packaged_by=None, notes=None))
        assert is_ok(pkg), pkg
        before = _snapshot(fconn)
        r = call_action(SC["finaid-generate-scholarship-matches"], fconn, ns(
            company_id=s["company_id"], aid_year_id="no-such-year"))
        assert is_error(r)
        assert r["message"] == "Aid year no-such-year not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# finaid-generate-scholarship-renewal -- stored row (finaid_scholarship_renewal).
# No ledger effect: inserts the renewal row only; never touches journal/gl.
# FINDING (documented, not fixed): the handler docstring claims
# UNIQUE(scholarship_application_id, academic_term_id) and the code has a
# duplicate branch for it, but the table carries only a plain index, so a
# second evaluation for the same application and term inserts a second row
# instead of refusing. The test pins that real behaviour.
# ---------------------------------------------------------------------------
class TestGenerateScholarshipRenewal:
    def _evaluate(self, conn, s, app_id, gpa="3.50", credits=12):
        return call_action(SC["finaid-generate-scholarship-renewal"], conn, ns(
            scholarship_application_id=app_id, academic_term_id=s["term_id"],
            company_id=s["company_id"], gpa_at_evaluation=gpa,
            credits_attempted=credits))

    def test_passing_evaluation_writes_a_renewed_row(self, fconn):
        s = _build_env(fconn)
        program_id = _scholarship_program(fconn, s)
        app_id = _scholarship_application(fconn, s, program_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = self._evaluate(fconn, s, app_id)
        assert is_ok(r), r
        assert r["renewal_status"] == "renewed"
        assert r["meets_criteria"] == 1
        assert r["gpa_at_evaluation"] == "3.50"
        assert r["credits_attempted"] == 12
        assert r["reason"] == "All renewal criteria met"
        row = _row(fconn, "finaid_scholarship_renewal", r["id"])
        assert row["scholarship_application_id"] == app_id
        assert row["student_id"] == s["student_id"]
        assert row["scholarship_program_id"] == program_id
        assert row["academic_term_id"] == s["term_id"]
        assert row["renewal_status"] == "renewed"
        assert row["meets_criteria"] == 1
        assert row["gpa_at_evaluation"] == "3.50"
        assert Decimal(row["gpa_at_evaluation"]) == Decimal("3.50")
        assert row["credits_attempted"] == 12
        assert row["reason"] == "All renewal criteria met"
        assert row["evaluation_date"] == today
        assert row["company_id"] == s["company_id"]

    def test_failing_evaluation_writes_a_suspended_row_with_reasons(self, fconn):
        s = _build_env(fconn)
        program_id = _scholarship_program(fconn, s)
        sid2 = _helpers.seed_student(fconn, s["company_id"])
        app_id = _scholarship_application(fconn, s, program_id, student_id=sid2,
                                          gpa="2.00")
        r = self._evaluate(fconn, s, app_id, gpa="2.00", credits=6)
        assert is_ok(r), r
        assert r["renewal_status"] == "suspended"
        assert r["meets_criteria"] == 0
        assert r["reason"] == ("GPA 2.00 below minimum 3.00; "
                               "Credits 6 below minimum 12")
        row = _row(fconn, "finaid_scholarship_renewal", r["id"])
        assert row["renewal_status"] == "suspended"
        assert row["meets_criteria"] == 0
        assert row["student_id"] == sid2

    def test_second_evaluation_for_the_same_term_inserts_again(self, fconn):
        s = _build_env(fconn)
        program_id = _scholarship_program(fconn, s)
        app_id = _scholarship_application(fconn, s, program_id)
        first = self._evaluate(fconn, s, app_id)
        assert is_ok(first), first
        second = self._evaluate(fconn, s, app_id)
        assert is_ok(second), second
        assert second["id"] != first["id"]
        assert second["renewal_status"] == "renewed"
        t = Table("finaid_scholarship_renewal")
        rows = fconn.execute(
            Q.from_(t).select("*").where(
                t.scholarship_application_id == P()).get_sql(), (app_id,)).fetchall()
        assert len(rows) == 2

    def test_refuses_an_unknown_application_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        program_id = _scholarship_program(fconn, s)
        _scholarship_application(fconn, s, program_id)
        before = _snapshot(fconn)
        r = call_action(SC["finaid-generate-scholarship-renewal"], fconn, ns(
            scholarship_application_id="no-such-application",
            academic_term_id=s["term_id"], company_id=s["company_id"],
            gpa_at_evaluation="3.50", credits_attempted=12))
        assert is_error(r)
        assert r["message"] == "Scholarship application no-such-application not found"
        assert _snapshot(fconn) == before
