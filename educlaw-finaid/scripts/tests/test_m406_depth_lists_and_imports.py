"""M406 depth: behavioural evidence for 12 list/import/get actions.

Prior state (read before writing anything below):
- Eight of these actions had a shape-only test in ``test_finaid.py`` that
  asserts only ``is_ok(r)`` on a seeded database, never that the payload
  matches a stored row: ``finaid-list-aid-years`` (``TestAidYear.test_list``),
  ``finaid-list-fund-allocations`` (``TestFundAllocation.test_list``),
  ``finaid-list-cost-of-attendance`` (``TestCostOfAttendance.test_list``),
  ``finaid-import-isir`` (``TestISIR.test_import``),
  ``finaid-list-isirs`` (``TestISIR.test_list``),
  ``finaid-list-award-packages`` (``TestAwardPackage.test_list``),
  ``finaid-list-disbursements`` (``TestDisbursements.test_list``) and
  ``finaid-list-loans`` (``TestLoan.test_list``). Those tests stay untouched.
- The other four -- ``finaid-get-work-study-timesheet``,
  ``finaid-import-pell-schedule``, ``finaid-list-awards`` and
  ``finaid-list-isir-cflags`` -- had NO module test at all in this tree; they
  were covered only by box-facing routability contracts outside this tree
  that assert an action can be reached, not what it does.

Every test below observes the database through a fresh ``get_connection()``
read-back built with PyPika (``erpclaw_lib.query``): the row that should
exist afterwards with exact values, the row that should have changed from
what to what, and what must NOT have changed. Catalog questions (does the
table exist) go through ``erpclaw_lib.seam``; there is no ``sqlite_master``,
no ``PRAGMA`` and no ``information_schema`` below. Money compares exact
``Decimal`` strings, never float, never approximate, never ``round``.

Ledger scope, stated once so no later reader adds a balance assertion that
cannot hold: none of these 12 handlers reaches the general ledger. The ten
read actions are pure SELECTs; the two import actions write only their own
``finaid_*`` tables (``finaid_isir`` + ``finaid_isir_cflag``,
``finaid_pell_schedule``). Every per-action section repeats its own ledger
note. No test below asserts journal/GL legs because none can exist.

Signal depth per action (stored row unless noted):
- finaid-list-aid-years: stored row (read-only; payload mirrors rows).
- finaid-list-award-packages: stored row (read-only; payload mirrors rows).
- finaid-list-awards: stored row (read-only; payload mirrors rows).
- finaid-list-cost-of-attendance: stored row (read-only; payload mirrors rows).
- finaid-list-disbursements: stored row (read-only; payload mirrors rows).
- finaid-list-fund-allocations: stored row (read-only; payload mirrors rows).
- finaid-list-isir-cflags: stored row (read-only; payload mirrors rows).
- finaid-list-isirs: stored row (read-only; payload mirrors rows).
- finaid-list-loans: stored row (read-only; payload mirrors rows).
- finaid-get-work-study-timesheet: stored row (read-only; payload mirrors row).
- finaid-import-isir: stored row (inserts ISIR + C-flag rows).
- finaid-import-pell-schedule: stored row (inserts/updates schedule rows).

All dates are passed explicitly, so nothing here depends on today's date.
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
WS = _load("work_study", _SCRIPTS_DIR).ACTIONS
LN = _load("loan_tracking", _SCRIPTS_DIR).ACTIONS

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
    path = str(tmp_path_factory.mktemp("m406tpl") / "template.sqlite")
    _helpers.init_all_tables(path)
    assert _seam.table_exists("finaid_aid_year", path)
    assert _seam.table_exists("finaid_isir", path)
    assert _seam.table_exists("finaid_pell_schedule", path)
    assert _seam.table_exists("finaid_award", path)
    assert _seam.table_exists("finaid_loan", path)
    assert _seam.table_exists("finaid_work_study_timesheet", path)
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


def _package(conn, s, **kw):
    args = dict(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", financial_need=None,
        acceptance_deadline=None, packaged_by=None, notes=None)
    args.update(kw)
    r = call_action(FA["finaid-create-award-package"], conn, ns(**args))
    assert is_ok(r), r
    return r["id"]


def _award(conn, s, pkg_id, aid_type, offered, aid_source="federal"):
    r = call_action(FA["finaid-add-award"], conn, ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source=aid_source, offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None,
        notes=None))
    assert is_ok(r), r
    return r["id"]


def _accept(conn, award_id, amount, date="2025-08-01"):
    r = call_action(FA["finaid-accept-award"], conn, ns(
        award_id=award_id, accepted_amount=amount, acceptance_date=date))
    assert is_ok(r), r
    return r


def _disburse(conn, s, award_id, amount, date="2025-09-02", number=1):
    r = call_action(FA["finaid-record-award-disbursement"], conn, ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date=date, company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=number))
    assert is_ok(r), r
    return r["id"]


def _loan(conn, s, award_id):
    r = call_action(LN["finaid-add-loan"], conn, ns(
        company_id=s["company_id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], award_id=award_id,
        loan_type="subsidized",
        loan_period_start="2025-08-25", loan_period_end="2026-05-15",
        loan_amount="3500", first_disbursement_amount="1750",
        second_disbursement_amount="1750",
        origination_fee="29.05", interest_rate="6.53",
        borrower_id=s["student_id"], borrower_type="student",
        cod_loan_id=None, mpn_signed_date=None,
        entrance_counseling_required=1, entrance_counseling_date=None,
        exit_counseling_required=0, exit_counseling_date=None))
    assert is_ok(r), r
    return r["id"]


def _timesheet(conn, s):
    job = call_action(WS["finaid-add-work-study-job"], conn, ns(
        company_id=s["company_id"], aid_year_id=s["aid_year_id"],
        job_title="Library Assistant", department_id=None, supervisor_id=None,
        job_type="on_campus", pay_rate="15.00", hours_per_week="10",
        total_positions=3, description=None))
    assert is_ok(job), job
    pkg_id = _package(conn, s)
    award_id = _award(conn, s, pkg_id, "fws", "3000")
    assign = call_action(WS["finaid-assign-student-to-job"], conn, ns(
        student_id=s["student_id"], award_id=award_id, job_id=job["id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-08-25",
        end_date="2026-05-15", award_limit="3000"))
    assert is_ok(assign), assign
    ts = call_action(WS["finaid-submit-work-study-timesheet"], conn, ns(
        assignment_id=assign["id"], student_id=s["student_id"],
        company_id=s["company_id"], pay_period_start="2025-09-01",
        pay_period_end="2025-09-15", hours_worked="10",
        submission_date="2025-09-16"))
    assert is_ok(ts), ts
    return ts["id"], assign["id"], job["id"]


# ---------------------------------------------------------------------------
# finaid-list-aid-years -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListAidYears:
    def test_lists_both_years_with_exact_money_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        added = call_action(FA["finaid-add-aid-year"], fconn, ns(
            company_id=s["company_id"], aid_year_code="2026-2027",
            description="Next year", start_date="2026-07-01",
            end_date="2027-06-30", pell_max_award="7400.005"))
        assert is_ok(added), added
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-aid-years"], fconn, ns(
            company_id=s["company_id"], limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert [y["aid_year_code"] for y in r["aid_years"]] == ["2026-2027", "2025-2026"]
        by_code = {y["aid_year_code"]: y for y in r["aid_years"]}
        assert by_code["2026-2027"]["pell_max_award"] == "7400.01"
        assert Decimal(by_code["2026-2027"]["pell_max_award"]) == Decimal("7400.01")
        assert by_code["2025-2026"]["pell_max_award"] == "7395"
        assert Decimal(by_code["2025-2026"]["pell_max_award"]) == Decimal("7395")
        row = _row(fconn, "finaid_aid_year", added["id"])
        for key in ("aid_year_code", "description", "start_date", "end_date",
                    "pell_max_award", "company_id"):
            assert by_code["2026-2027"][key] == row[key], key
        active_only = call_action(FA["finaid-list-aid-years"], fconn, ns(
            company_id=s["company_id"], is_active=1, limit=50, offset=0))
        assert is_ok(active_only), active_only
        assert active_only["count"] == 1
        assert active_only["aid_years"][0]["aid_year_code"] == "2025-2026"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_aid_year") == 2

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-aid-years"], fconn, ns(
            company_id=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_aid_year") == 1


# ---------------------------------------------------------------------------
# finaid-list-award-packages -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListAwardPackages:
    def test_lists_packages_with_exact_need_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_a = _package(fconn, s)
        pkg_b = _package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-award-packages"], fconn, ns(
            company_id=s["company_id"], student_id=s["student_id"],
            aid_year_id=None, status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        by_id = {p["id"]: p for p in r["award_packages"]}
        assert set(by_id) == {pkg_a, pkg_b}
        for pid in (pkg_a, pkg_b):
            row = _row(fconn, "finaid_award_package", pid)
            assert by_id[pid]["financial_need"] == "28300.00"
            assert Decimal(by_id[pid]["financial_need"]) == Decimal("28300.00")
            assert by_id[pid]["total_grants"] == "0"
            assert by_id[pid]["status"] == "draft"
            for key in ("financial_need", "total_grants", "total_loans",
                        "total_work_study", "total_aid", "status",
                        "student_id", "aid_year_id", "company_id"):
                assert by_id[pid][key] == row[key], key
        offered = call_action(FA["finaid-list-award-packages"], fconn, ns(
            company_id=s["company_id"], status="offered", limit=50, offset=0))
        assert is_ok(offered), offered
        assert offered["count"] == 0
        assert _snapshot(fconn) == before

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _package(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-award-packages"], fconn, ns(
            company_id=None, student_id=None, aid_year_id=None,
            status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_award_package") == 1


# ---------------------------------------------------------------------------
# finaid-list-awards -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListAwards:
    def test_lists_package_awards_with_exact_money_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id = _package(fconn, s)
        pell_id = _award(fconn, s, pkg_id, "pell", "5000.00")
        fseog_id = _award(fconn, s, pkg_id, "fseog", "1200.50")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-awards"], fconn, ns(
            award_package_id=pkg_id, student_id=None, company_id=None,
            aid_type=None, acceptance_status=None))
        assert is_ok(r), r
        assert r["count"] == 2
        by_type = {a["aid_type"]: a for a in r["awards"]}
        assert set(by_type) == {"pell", "fseog"}
        assert by_type["pell"]["offered_amount"] == "5000.00"
        assert Decimal(by_type["pell"]["offered_amount"]) == Decimal("5000.00")
        assert by_type["fseog"]["offered_amount"] == "1200.50"
        assert Decimal(by_type["fseog"]["offered_amount"]) == Decimal("1200.50")
        for aid, wid in (("pell", pell_id), ("fseog", fseog_id)):
            row = _row(fconn, "finaid_award", wid)
            assert (by_type[aid]["accepted_amount"], by_type[aid]["disbursed_amount"],
                    by_type[aid]["acceptance_status"]) == ("0", "0", "pending")
            for key in ("offered_amount", "accepted_amount", "disbursed_amount",
                        "acceptance_status", "aid_source", "award_package_id",
                        "student_id", "company_id"):
                assert by_type[aid][key] == row[key], key
        pell_only = call_action(FA["finaid-list-awards"], fconn, ns(
            award_package_id=pkg_id, student_id=None, company_id=None,
            aid_type="pell", acceptance_status=None))
        assert is_ok(pell_only), pell_only
        assert pell_only["count"] == 1
        assert pell_only["awards"][0]["id"] == pell_id
        assert _snapshot(fconn) == before

    def test_refuses_a_filterless_call_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id = _package(fconn, s)
        _award(fconn, s, pkg_id, "pell", "5000.00")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-awards"], fconn, ns(
            award_package_id=None, student_id=None, company_id=None,
            aid_type=None, acceptance_status=None))
        assert is_error(r)
        assert r["message"] == "award_package_id, student_id, or company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_award") == 1


# ---------------------------------------------------------------------------
# finaid-list-cost-of-attendance -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListCostOfAttendance:
    def test_lists_coa_rows_with_exact_money_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        added = call_action(FA["finaid-add-cost-of-attendance"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            enrollment_status="half_time", living_arrangement="off_campus",
            tuition_fees="8000", books_supplies="600", room_board="5000",
            transportation="750", personal_expenses="1000", loan_fees="50",
            program_id=None))
        assert is_ok(added), added
        assert added["total_coa"] == "15400.00"
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-cost-of-attendance"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None,
            enrollment_status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        by_status = {c["enrollment_status"]: c for c in r["cost_of_attendance"]}
        assert set(by_status) == {"full_time", "half_time"}
        seeded = by_status["full_time"]
        assert (seeded["tuition_fees"], seeded["books_supplies"], seeded["room_board"],
                seeded["transportation"], seeded["personal_expenses"],
                seeded["loan_fees"], seeded["total_coa"]) == (
                    "15000", "1200", "10000", "1500", "2000", "100", "29800")
        assert Decimal(seeded["total_coa"]) == Decimal("29800")
        assert by_status["half_time"]["total_coa"] == "15400.00"
        assert Decimal(by_status["half_time"]["total_coa"]) == Decimal("15400.00")
        row = _row(fconn, "finaid_cost_of_attendance", added["id"])
        for key in ("tuition_fees", "books_supplies", "room_board",
                    "transportation", "personal_expenses", "loan_fees",
                    "total_coa", "enrollment_status", "living_arrangement",
                    "aid_year_id", "company_id"):
            assert by_status["half_time"][key] == row[key], key
        full_time = call_action(FA["finaid-list-cost-of-attendance"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None,
            enrollment_status="full_time", limit=50, offset=0))
        assert is_ok(full_time), full_time
        assert full_time["count"] == 1
        assert full_time["cost_of_attendance"][0]["id"] == s["cost_of_attendance_id"]
        assert _snapshot(fconn) == before

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-cost-of-attendance"], fconn, ns(
            company_id=None, aid_year_id=None, enrollment_status=None,
            limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_cost_of_attendance") == 1


# ---------------------------------------------------------------------------
# finaid-list-disbursements -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables (the
# disbursing action itself writes only finaid_disbursement + finaid_award).
# ---------------------------------------------------------------------------
class TestListDisbursements:
    def test_lists_disbursement_with_exact_money_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id = _package(fconn, s)
        award_id = _award(fconn, s, pkg_id, "pell", "5000.00")
        _accept(fconn, award_id, "4000.00")
        disb_id = _disburse(fconn, s, award_id, "1500.00")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-disbursements"], fconn, ns(
            company_id=s["company_id"], student_id=None, award_id=award_id,
            cod_status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 1
        payload = r["disbursements"][0]
        assert payload["amount"] == "1500.00"
        assert Decimal(payload["amount"]) == Decimal("1500.00")
        assert payload["disbursement_type"] == "disbursement"
        assert payload["disbursement_date"] == "2025-09-02"
        row = _row(fconn, "finaid_disbursement", disb_id)
        for key in ("amount", "disbursement_type", "disbursement_date",
                    "award_id", "award_package_id", "student_id", "company_id"):
            assert payload[key] == row[key], key
        assert row["award_package_id"] == pkg_id
        other = call_action(FA["finaid-list-disbursements"], fconn, ns(
            company_id=s["company_id"], student_id=None, award_id="no-such-award",
            cod_status=None, limit=50, offset=0))
        assert is_ok(other), other
        assert other["count"] == 0
        assert _snapshot(fconn) == before
        award = _row(fconn, "finaid_award", award_id)
        assert award["disbursed_amount"] == "1500.00"

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id = _package(fconn, s)
        award_id = _award(fconn, s, pkg_id, "pell", "5000.00")
        _accept(fconn, award_id, "4000.00")
        _disburse(fconn, s, award_id, "1500.00")
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-disbursements"], fconn, ns(
            company_id=None, student_id=None, award_id=None,
            cod_status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_disbursement") == 1


# ---------------------------------------------------------------------------
# finaid-list-fund-allocations -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListFundAllocations:
    def test_lists_allocations_with_exact_money_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        first = call_action(FA["finaid-add-fund-allocation"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fseog", fund_name="FSEOG Campus Fund",
            total_allocation="25000.00", committed_amount=None))
        assert is_ok(first), first
        second = call_action(FA["finaid-add-fund-allocation"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fws", fund_name="FWS Campus Fund",
            total_allocation="75000.00", committed_amount=None))
        assert is_ok(second), second
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-fund-allocations"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None, fund_type=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        by_type = {a["fund_type"]: a for a in r["fund_allocations"]}
        assert set(by_type) == {"fseog", "fws"}
        assert by_type["fseog"]["total_allocation"] == "25000.00"
        assert Decimal(by_type["fseog"]["total_allocation"]) == Decimal("25000.00")
        assert by_type["fws"]["total_allocation"] == "75000.00"
        assert Decimal(by_type["fws"]["total_allocation"]) == Decimal("75000.00")
        row = _row(fconn, "finaid_fund_allocation", first["id"])
        assert (row["committed_amount"], row["disbursed_amount"],
                row["available_amount"]) == ("0", "0", "25000.00")
        for key in ("fund_type", "fund_name", "total_allocation",
                    "committed_amount", "disbursed_amount", "available_amount",
                    "aid_year_id", "company_id"):
            assert by_type["fseog"][key] == row[key], key
        fseog_only = call_action(FA["finaid-list-fund-allocations"], fconn, ns(
            company_id=s["company_id"], aid_year_id=None, fund_type="fseog",
            limit=50, offset=0))
        assert is_ok(fseog_only), fseog_only
        assert fseog_only["count"] == 1
        assert fseog_only["fund_allocations"][0]["id"] == first["id"]
        assert _snapshot(fconn) == before

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        added = call_action(FA["finaid-add-fund-allocation"], fconn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fseog", fund_name="FSEOG Campus Fund",
            total_allocation="25000.00", committed_amount=None))
        assert is_ok(added), added
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-fund-allocations"], fconn, ns(
            company_id=None, aid_year_id=None, fund_type=None,
            limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_fund_allocation") == 1


# ---------------------------------------------------------------------------
# finaid-list-isir-cflags -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListIsirCflags:
    def _import_flagged(self, conn, s, txn=2):
        r = call_action(FA["finaid-import-isir"], conn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], sai="2000",
            dependency_status="dependent", pell_index_isir="150",
            verification_flag=0, verification_group=None, transaction_number=txn,
            fafsa_submission_id=None, nslds_default_flag=1,
            nslds_overpayment_flag=0, selective_service_flag=0,
            citizenship_flag=1, agi="55000", household_size=4,
            family_members_in_college=1, receipt_date="2025-04-01",
            raw_isir_data=None, is_active_transaction=1))
        assert is_ok(r), r
        return r["id"]

    def test_lists_cflags_with_exact_codes_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        isir_id = self._import_flagged(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-isir-cflags"], fconn, ns(
            isir_id=isir_id, student_id=None, resolution_status=None))
        assert is_ok(r), r
        assert r["count"] == 2
        assert sorted(c["cflag_code"] for c in r["cflags"]) == ["C01", "C25"]
        by_code = {c["cflag_code"]: c for c in r["cflags"]}
        for code in ("C01", "C25"):
            assert by_code[code]["resolution_status"] == "pending"
            assert by_code[code]["blocks_disbursement"] == 1
            assert by_code[code]["student_id"] == s["student_id"]
            assert by_code[code]["isir_id"] == isir_id
        t = Table("finaid_isir_cflag")
        stored = fconn.execute(
            Q.from_(t).select("*").where(Field("isir_id") == P()).get_sql(),
            (isir_id,)).fetchall()
        assert len(stored) == 2
        assert sorted(dict(x)["cflag_code"] for x in stored) == ["C01", "C25"]
        clean = call_action(FA["finaid-list-isir-cflags"], fconn, ns(
            isir_id=s["isir_id"], student_id=None, resolution_status=None))
        assert is_ok(clean), clean
        assert clean["count"] == 0
        assert _snapshot(fconn) == before

    def test_refuses_a_filterless_call_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        self._import_flagged(fconn, s)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-isir-cflags"], fconn, ns(
            isir_id=None, student_id=None, resolution_status=None))
        assert is_error(r)
        assert r["message"] == "isir_id or student_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_isir_cflag") == 2


# ---------------------------------------------------------------------------
# finaid-list-isirs -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestListIsirs:
    def test_lists_isirs_with_exact_sai_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        imported = call_action(FA["finaid-import-isir"], fconn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], sai="2000.005",
            dependency_status="independent", pell_index_isir="150",
            verification_flag=0, verification_group=None, transaction_number=2,
            fafsa_submission_id=None, nslds_default_flag=0,
            nslds_overpayment_flag=0, selective_service_flag=0,
            citizenship_flag=0, agi="55000", household_size=4,
            family_members_in_college=1, receipt_date="2025-04-01",
            raw_isir_data=None, is_active_transaction=1))
        assert is_ok(imported), imported
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-isirs"], fconn, ns(
            student_id=s["student_id"], aid_year_id=None,
            company_id=s["company_id"], limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        by_txn = {i["transaction_number"]: i for i in r["isirs"]}
        assert set(by_txn) == {1, 2}
        assert by_txn[1]["sai"] == "1500"
        assert Decimal(by_txn[1]["sai"]) == Decimal("1500")
        assert by_txn[2]["sai"] == "2000.01"
        assert Decimal(by_txn[2]["sai"]) == Decimal("2000.01")
        assert by_txn[1]["status"] == "received"
        assert by_txn[2]["status"] == "received"
        row = _row(fconn, "finaid_isir", imported["id"])
        for key in ("sai", "dependency_status", "pell_index", "status",
                    "student_id", "aid_year_id", "company_id"):
            assert by_txn[2][key] == row[key], key
        seed_row = _row(fconn, "finaid_isir", s["isir_id"])
        assert seed_row["sai"] == "1500"
        assert seed_row["transaction_number"] == 1
        reviewed = call_action(FA["finaid-list-isirs"], fconn, ns(
            student_id=s["student_id"], aid_year_id=None,
            company_id=s["company_id"], status="reviewed",
            limit=50, offset=0))
        assert is_ok(reviewed), reviewed
        assert reviewed["count"] == 0
        assert _snapshot(fconn) == before

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-list-isirs"], fconn, ns(
            student_id=s["student_id"], aid_year_id=None,
            company_id=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "company_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_isir") == 1


# ---------------------------------------------------------------------------
# finaid-list-loans -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables (the
# loan-creation action itself writes only finaid_loan + award holds).
# ---------------------------------------------------------------------------
class TestListLoans:
    def test_lists_loan_with_exact_money_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id = _package(fconn, s)
        award_id = _award(fconn, s, pkg_id, "subsidized_loan", "3500")
        loan_id = _loan(fconn, s, award_id)
        before = _snapshot(fconn)
        r = call_action(LN["finaid-list-loans"], fconn, ns(
            company_id=s["company_id"], student_id=s["student_id"],
            aid_year_id=None, loan_type=None, status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 1
        payload = r["loans"][0]
        assert payload["loan_amount"] == "3500.00"
        assert Decimal(payload["loan_amount"]) == Decimal("3500.00")
        assert payload["first_disbursement_amount"] == "1750.00"
        assert Decimal(payload["first_disbursement_amount"]) == Decimal("1750.00")
        assert payload["second_disbursement_amount"] == "1750.00"
        assert payload["origination_fee"] == "29.05"
        assert Decimal(payload["origination_fee"]) == Decimal("29.05")
        assert payload["interest_rate"] == "6.53"
        assert Decimal(payload["interest_rate"]) == Decimal("6.53")
        assert payload["status"] == "originated"
        assert payload["loan_type"] == "subsidized"
        row = _row(fconn, "finaid_loan", loan_id)
        for key in ("loan_amount", "first_disbursement_amount",
                    "second_disbursement_amount", "origination_fee",
                    "interest_rate", "status", "loan_type", "award_id",
                    "student_id", "aid_year_id", "company_id"):
            assert payload[key] == row[key], key
        assert row["award_id"] == award_id
        plus = call_action(LN["finaid-list-loans"], fconn, ns(
            company_id=s["company_id"], student_id=s["student_id"],
            aid_year_id=None, loan_type="plus", status=None,
            limit=50, offset=0))
        assert is_ok(plus), plus
        assert plus["count"] == 0
        assert _snapshot(fconn) == before

    def test_refuses_a_missing_company_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        pkg_id = _package(fconn, s)
        award_id = _award(fconn, s, pkg_id, "subsidized_loan", "3500")
        _loan(fconn, s, award_id)
        before = _snapshot(fconn)
        r = call_action(LN["finaid-list-loans"], fconn, ns(
            company_id=None, student_id=None, aid_year_id=None,
            loan_type=None, status=None, limit=50, offset=0))
        assert is_error(r)
        assert r["message"] == "Missing required field: company_id"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_loan") == 1


# ---------------------------------------------------------------------------
# finaid-get-work-study-timesheet -- stored row (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables.
# ---------------------------------------------------------------------------
class TestGetWorkStudyTimesheet:
    def test_payload_mirrors_the_stored_timesheet_and_reads_change_nothing(self, fconn):
        s = _build_env(fconn)
        ts_id, assign_id, _job_id = _timesheet(fconn, s)
        before = _snapshot(fconn)
        r = call_action(WS["finaid-get-work-study-timesheet"], fconn, ns(id=ts_id))
        assert is_ok(r), r
        row = _row(fconn, "finaid_work_study_timesheet", ts_id)
        assert row["hours_worked"] == "10"
        assert row["earnings"] == "150.00"
        assert Decimal(row["earnings"]) == Decimal("150.00")
        assert row["cumulative_earnings"] == "150.00"
        assert Decimal(row["cumulative_earnings"]) == Decimal("150.00")
        assert row["supervisor_approval_status"] == "pending"
        assert row["pay_period_start"] == "2025-09-01"
        assert row["pay_period_end"] == "2025-09-15"
        for key in ("hours_worked", "earnings", "cumulative_earnings",
                    "supervisor_approval_status", "pay_period_start",
                    "pay_period_end", "assignment_id", "student_id",
                    "company_id"):
            assert r[key] == row[key], key
        assert row["assignment_id"] == assign_id
        assert _snapshot(fconn) == before

    def test_refuses_an_unknown_or_missing_id_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _timesheet(fconn, s)
        before = _snapshot(fconn)
        r = call_action(WS["finaid-get-work-study-timesheet"], fconn, ns(id="no-such-ts"))
        assert is_error(r)
        assert r["message"] == "Timesheet no-such-ts not found"
        assert _snapshot(fconn) == before
        missing = call_action(WS["finaid-get-work-study-timesheet"], fconn, ns(id=None))
        assert is_error(missing)
        assert missing["message"] == "--id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_work_study_timesheet") == 1


# ---------------------------------------------------------------------------
# finaid-import-isir -- stored row (inserts ISIR + C-flag rows).
# No ledger effect: writes only finaid_isir / finaid_isir_cflag, never
# journal/gl tables.
# ---------------------------------------------------------------------------
class TestImportIsir:
    def test_writes_isir_and_cflag_rows_with_exact_money(self, fconn):
        s = _build_env(fconn)
        before_count = _count(fconn, "finaid_isir")
        assert before_count == 1
        r = call_action(FA["finaid-import-isir"], fconn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], sai="2000.005",
            dependency_status="independent", pell_index_isir="150",
            verification_flag=0, verification_group=None, transaction_number=2,
            fafsa_submission_id=None, nslds_default_flag=1,
            nslds_overpayment_flag=0, selective_service_flag=0,
            citizenship_flag=0, agi="55000.456", household_size=4,
            family_members_in_college=1, receipt_date="2025-04-01",
            raw_isir_data=None, is_active_transaction=1))
        assert is_ok(r), r
        assert r["has_unresolved_cflags"] == 1
        assert r["cflags_created"] == 1
        assert _count(fconn, "finaid_isir") == 2
        row = _row(fconn, "finaid_isir", r["id"])
        assert row["student_id"] == s["student_id"]
        assert row["aid_year_id"] == s["aid_year_id"]
        assert row["transaction_number"] == 2
        assert row["sai"] == "2000.01"
        assert Decimal(row["sai"]) == Decimal("2000.01")
        assert row["sai_is_negative"] == 0
        assert row["dependency_status"] == "independent"
        assert row["pell_index"] == "150"
        assert row["agi"] == "55000.46"
        assert Decimal(row["agi"]) == Decimal("55000.46")
        assert row["household_size"] == 4
        assert row["has_unresolved_cflags"] == 1
        assert row["status"] == "received"
        assert row["company_id"] == s["company_id"]
        t = Table("finaid_isir_cflag")
        flags = fconn.execute(
            Q.from_(t).select("*").where(Field("isir_id") == P()).get_sql(),
            (r["id"],)).fetchall()
        assert len(flags) == 1
        flag = dict(flags[0])
        assert flag["cflag_code"] == "C25"
        assert flag["resolution_status"] == "pending"
        assert flag["blocks_disbursement"] == 1
        assert flag["student_id"] == s["student_id"]
        seed = _row(fconn, "finaid_isir", s["isir_id"])
        assert seed["sai"] == "1500"
        assert seed["transaction_number"] == 1
        assert seed["has_unresolved_cflags"] == 0
        # No ledger legs: only finaid_isir / finaid_isir_cflag rows move.

    def test_refuses_a_missing_student_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-import-isir"], fconn, ns(
            student_id=None, aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], sai="2000",
            dependency_status="dependent", pell_index_isir="150",
            verification_flag=0, verification_group=None, transaction_number=2,
            fafsa_submission_id=None, nslds_default_flag=0,
            nslds_overpayment_flag=0, selective_service_flag=0,
            citizenship_flag=0, agi="55000", household_size=4,
            family_members_in_college=1, receipt_date="2025-04-01",
            raw_isir_data=None, is_active_transaction=1))
        assert is_error(r)
        assert r["message"] == "student_id is required"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_isir") == 1
        assert _count(fconn, "finaid_isir_cflag") == 0


# ---------------------------------------------------------------------------
# finaid-import-pell-schedule -- stored row (inserts/updates schedule rows).
# No ledger effect: writes only finaid_pell_schedule, never journal/gl tables.
# ---------------------------------------------------------------------------
class TestImportPellSchedule:
    def _rows(self, full0="7395.005", full1="7100.00"):
        return json.dumps([
            {"pell_index": 0, "full_time_annual": full0,
             "three_quarter_time": "5546.26", "half_time": "3697.50",
             "less_than_half_time": "1848.75"},
            {"pell_index": 1, "full_time_annual": full1,
             "three_quarter_time": "5325.00", "half_time": "3550.00",
             "less_than_half_time": "1775.00"},
        ])

    def test_inserts_then_upserts_schedule_rows_with_exact_money(self, fconn):
        s = _build_env(fconn)
        assert _count(fconn, "finaid_pell_schedule") == 0
        r = call_action(FA["finaid-import-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            rows=self._rows()))
        assert is_ok(r), r
        assert r["inserted"] == 2
        assert r["aid_year_id"] == s["aid_year_id"]
        assert _count(fconn, "finaid_pell_schedule") == 2
        t = Table("finaid_pell_schedule")
        stored = fconn.execute(
            Q.from_(t).select("*").where(Field("aid_year_id") == P()).get_sql(),
            (s["aid_year_id"],)).fetchall()
        by_idx = {dict(x)["pell_index"]: dict(x) for x in stored}
        assert set(by_idx) == {0, 1}
        assert by_idx[0]["full_time_annual"] == "7395.01"
        assert Decimal(by_idx[0]["full_time_annual"]) == Decimal("7395.01")
        assert by_idx[0]["three_quarter_time"] == "5546.26"
        assert by_idx[0]["half_time"] == "3697.50"
        assert by_idx[0]["less_than_half_time"] == "1848.75"
        assert by_idx[1]["full_time_annual"] == "7100.00"
        again = call_action(FA["finaid-import-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            rows=json.dumps([{"pell_index": 0, "full_time_annual": "7000.00",
                              "three_quarter_time": "5250.00",
                              "half_time": "3500.00",
                              "less_than_half_time": "1750.00"}])))
        assert is_ok(again), again
        assert again["inserted"] == 1
        assert _count(fconn, "finaid_pell_schedule") == 2
        updated = fconn.execute(
            Q.from_(t).select("*").where(Field("aid_year_id") == P()).where(
                Field("pell_index") == P()).get_sql(),
            (s["aid_year_id"], 0)).fetchall()
        assert len(updated) == 1
        assert dict(updated[0])["full_time_annual"] == "7000.00"
        assert Decimal(dict(updated[0])["full_time_annual"]) == Decimal("7000.00")
        untouched = _row_by_index(fconn, s["aid_year_id"], 1)
        assert untouched["full_time_annual"] == "7100.00"
        assert untouched["three_quarter_time"] == "5325.00"
        # No ledger legs: only finaid_pell_schedule rows move.

    def test_refuses_missing_or_bad_rows_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(FA["finaid-import-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"], rows=None))
        assert is_error(r)
        assert r["message"] == "rows is required (JSON array)"
        assert _snapshot(fconn) == before
        bad = call_action(FA["finaid-import-pell-schedule"], fconn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            rows="not-json"))
        assert is_error(bad)
        assert bad["message"] == "rows must be valid JSON array"
        assert _snapshot(fconn) == before
        assert _count(fconn, "finaid_pell_schedule") == 0


def _row_by_index(conn, aid_year_id, pell_index):
    t = Table("finaid_pell_schedule")
    row = conn.execute(
        Q.from_(t).select("*").where(Field("aid_year_id") == P()).where(
            Field("pell_index") == P()).get_sql(),
        (aid_year_id, pell_index)).fetchone()
    return dict(row)
