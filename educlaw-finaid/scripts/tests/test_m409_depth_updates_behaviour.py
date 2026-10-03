"""Behavioural depth tests for the 12 finaid update actions (m409).

Each action below was previously covered only by a shape check (``is_ok``
on the response in ``test_finaid.py``) or by a routability probe
(``testing/integration/contract/test_educlaw_finaid_contract.py``).
Neither observes the database, so a handler could return a perfect
envelope while writing nothing or writing the wrong thing. The tests
here assert the effect: the exact stored row afterwards (money as exact
``TEXT`` strings, never float), the sibling rows that must NOT have
changed, and one input-validation refusal per action that must leave
the database byte-identical.

Two of the twelve (``finaid-update-award`` and
``finaid-update-award-package``) already have behavioural tests in
``test_award_package_lifecycle_behaviour.py``; the tests here use
different field paths and add snapshot-based refusal proof rather than
replacing those.

None of these 12 handlers reaches the general ledger: each writes only
``finaid_*`` rows and never posts journals, so every success test says
so in a comment (the snapshot covers every owned table plus
``audit_log``, which would catch a stray write).

All dates are passed explicitly, so nothing here depends on today's date.
"""
import importlib.util
import json
import os

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
is_ok = _helpers.is_ok
is_error = _helpers.is_error

FA_ACTIONS = _load("financial_aid", _SCRIPTS_DIR).ACTIONS
LOAN_ACTIONS = _load("loan_tracking", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def env(db_path):
    conn = _helpers.get_conn(db_path)
    cid = _helpers.seed_company(conn)
    sid = _helpers.seed_student(conn, cid)
    aid_yr = _helpers.seed_aid_year(conn, cid)
    yid = _helpers.seed_academic_year(conn, cid)
    tid = _helpers.seed_academic_term(conn, cid, yid)
    pid = _helpers.seed_program(conn, cid)
    peid = _helpers.seed_program_enrollment(conn, sid, pid, yid, cid)
    isir_id = _helpers.seed_isir(conn, sid, aid_yr, cid)
    coa_id = _helpers.seed_cost_of_attendance(conn, aid_yr, cid)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid, "aid_year_id": aid_yr,
        "term_id": tid, "program_id": pid, "program_enrollment_id": peid,
        "isir_id": isir_id, "cost_of_attendance_id": coa_id,
    }
    conn.close()


_SNAPSHOT_TABLES = (
    "finaid_aid_year",
    "finaid_pell_schedule",
    "finaid_fund_allocation",
    "finaid_cost_of_attendance",
    "finaid_isir",
    "finaid_isir_cflag",
    "finaid_verification_request",
    "finaid_verification_document",
    "finaid_award_package",
    "finaid_award",
    "finaid_disbursement",
    "finaid_sap_evaluation",
    "finaid_sap_appeal",
    "finaid_r2t4_calculation",
    "finaid_professional_judgment",
    "finaid_cod_origination",
    "finaid_scholarship_program",
    "finaid_scholarship_application",
    "finaid_scholarship_renewal",
    "finaid_work_study_job",
    "finaid_work_study_assignment",
    "finaid_work_study_timesheet",
    "finaid_loan",
    "audit_log",
)


def _snapshot(conn):
    snap = {}
    for table in _SNAPSHOT_TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        except Exception:
            continue
        snap[table] = sorted(
            json.dumps(dict(r), sort_keys=True, default=str) for r in rows)
    return snap


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _package(s):
    r = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", financial_need=None,
        acceptance_deadline=None, packaged_by=None, notes=None))
    assert is_ok(r), r
    return r["id"]


def _award(s, pkg_id, aid_type, offered, aid_source="federal"):
    r = call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source=aid_source, offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None,
        notes=None))
    assert is_ok(r), r
    return r["id"]


def _package_row(conn, pkg_id):
    return tuple(conn.execute(
        "SELECT financial_need, total_grants, total_loans, total_work_study, "
        "total_aid, status FROM finaid_award_package WHERE id = ?",
        (pkg_id,)).fetchone())


def _loan_award(s, pkg_id, offered="3500.00"):
    return _award(s, pkg_id, "subsidized_loan", offered)


def _add_loan(s, award_id):
    return call_action(LOAN_ACTIONS["finaid-add-loan"], s["conn"], ns(
        company_id=s["company_id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], award_id=award_id,
        loan_type="subsidized",
        loan_period_start="2025-08-25", loan_period_end="2026-05-15",
        loan_amount="3500.00", first_disbursement_amount="1750.00",
        second_disbursement_amount="1750.00",
        origination_fee="29.05", interest_rate="6.53",
        borrower_id=s["student_id"], borrower_type="student",
        cod_loan_id=None, mpn_signed_date=None,
        entrance_counseling_required=1, entrance_counseling_date=None,
        exit_counseling_required=0, exit_counseling_date=None))


def _loan(s):
    pkg_id = _package(s)
    award_id = _loan_award(s, pkg_id)
    r = _add_loan(s, award_id)
    assert is_ok(r), r
    return r["id"], award_id, pkg_id


def _loan_row(conn, loan_id):
    return tuple(conn.execute(
        "SELECT loan_amount, first_disbursement_amount, "
        "second_disbursement_amount, origination_fee, interest_rate, "
        "cod_loan_id, cod_origination_status, cod_origination_date, "
        "mpn_signed, mpn_signed_date, entrance_counseling_complete, "
        "entrance_counseling_date, exit_counseling_complete, "
        "exit_counseling_date, loan_period_start, loan_period_end, "
        "status FROM finaid_loan WHERE id = ?", (loan_id,)).fetchone())


def _holds(conn, award_id):
    return json.loads(conn.execute(
        "SELECT disbursement_holds FROM finaid_award WHERE id = ?",
        (award_id,)).fetchone()[0])


def _accepted_pell(s, offered="5000.00", accepted="4000.00"):
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, "pell", offered)
    r = call_action(FA_ACTIONS["finaid-accept-award"], s["conn"], ns(
        award_id=award_id, accepted_amount=accepted,
        acceptance_date="2025-08-01"))
    assert is_ok(r), r
    return pkg_id, award_id


def _disburse(s, award_id, amount="1500.00", number=1, date="2025-09-02"):
    r = call_action(FA_ACTIONS["finaid-record-award-disbursement"], s["conn"], ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date=date, company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=number))
    assert is_ok(r), r
    return r["id"]


# ---------------------------------------------------------------------------
# finaid-update-aid-year — stored row
# ---------------------------------------------------------------------------

class TestUpdateAidYearDepth:
    def test_rewrites_description_and_pell_max_and_leaves_code_and_sibling_year(self, env):
        s, conn = env, env["conn"]
        other = call_action(FA_ACTIONS["finaid-add-aid-year"], conn, ns(
            company_id=s["company_id"], aid_year_code="2026-2027",
            description="Next year", start_date="2026-07-01",
            end_date="2027-06-30", pell_max_award="7395"))
        assert is_ok(other), other
        other_before = tuple(conn.execute(
            "SELECT aid_year_code, description, start_date, end_date, "
            "pell_max_award, is_active FROM finaid_aid_year WHERE id = ?",
            (other["id"],)).fetchone())
        assert other_before == ("2026-2027", "Next year", "2026-07-01",
                                "2027-06-30", "7395.00", 0)
        r = call_action(FA_ACTIONS["finaid-update-aid-year"], conn, ns(
            id=s["aid_year_id"], description="Revised 2025-2026",
            pell_max_award="8000", aid_year_code=None, start_date=None,
            end_date=None, is_active=None))
        assert is_ok(r), r
        assert r["updated"] is True
        row = tuple(conn.execute(
            "SELECT aid_year_code, description, start_date, end_date, "
            "pell_max_award, is_active FROM finaid_aid_year WHERE id = ?",
            (s["aid_year_id"],)).fetchone())
        assert row == ("2025-2026", "Revised 2025-2026", "2025-07-01",
                       "2026-06-30", "8000.00", 1)
        assert tuple(conn.execute(
            "SELECT aid_year_code, description, start_date, end_date, "
            "pell_max_award, is_active FROM finaid_aid_year WHERE id = ?",
            (other["id"],)).fetchone()) == other_before
        # No ledger legs: an aid-year parameter row only, never journals.

    def test_refuses_an_unknown_year_and_an_empty_update_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-aid-year"], conn, ns(
            id="no-such-year", description="x", aid_year_code=None,
            start_date=None, end_date=None, pell_max_award=None,
            is_active=None))
        assert is_error(r)
        assert r["message"] == "Aid year not found"
        r = call_action(FA_ACTIONS["finaid-update-aid-year"], conn, ns(
            id=s["aid_year_id"], description=None, aid_year_code=None,
            start_date=None, end_date=None, pell_max_award=None,
            is_active=None))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-update-fund-allocation — stored row
# ---------------------------------------------------------------------------

class TestUpdateFundAllocationDepth:
    def test_raises_the_total_and_recomputes_available_and_leaves_sibling_fund(self, env):
        s, conn = env, env["conn"]
        fseog = call_action(FA_ACTIONS["finaid-add-fund-allocation"], conn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fseog", fund_name="FSEOG Grant Fund",
            total_allocation="500000", committed_amount=None))
        assert is_ok(fseog), fseog
        pell = call_action(FA_ACTIONS["finaid-add-fund-allocation"], conn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fws", fund_name="FWS Fund",
            total_allocation="200000", committed_amount=None))
        assert is_ok(pell), pell
        r = call_action(FA_ACTIONS["finaid-update-fund-allocation"], conn, ns(
            id=fseog["id"], fund_name="FSEOG Revised",
            total_allocation="600000"))
        assert is_ok(r), r
        assert r["updated"] is True
        row = tuple(conn.execute(
            "SELECT fund_type, fund_name, total_allocation, committed_amount, "
            "disbursed_amount, available_amount FROM finaid_fund_allocation "
            "WHERE id = ?", (fseog["id"],)).fetchone())
        assert row == ("fseog", "FSEOG Revised", "600000.00", "0", "0",
                       "600000.00")
        sibling = tuple(conn.execute(
            "SELECT fund_type, fund_name, total_allocation, committed_amount, "
            "disbursed_amount, available_amount FROM finaid_fund_allocation "
            "WHERE id = ?", (pell["id"],)).fetchone())
        assert sibling == ("fws", "FWS Fund", "200000.00", "0", "0",
                           "200000.00")
        # No ledger legs: a fund-budget row only, never journals.

    def test_refuses_a_missing_and_an_unknown_id_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        alloc = call_action(FA_ACTIONS["finaid-add-fund-allocation"], conn, ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fseog", fund_name="FSEOG Grant Fund",
            total_allocation="500000", committed_amount=None))
        assert is_ok(alloc), alloc
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-fund-allocation"], conn, ns(
            id=None, fund_name="x", total_allocation=None))
        assert is_error(r)
        assert r["message"] == "id is required"
        r = call_action(FA_ACTIONS["finaid-update-fund-allocation"], conn, ns(
            id="no-such-allocation", fund_name="x", total_allocation=None))
        assert is_error(r)
        assert r["message"] == "Fund allocation not found"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-update-cost-of-attendance — stored row
# ---------------------------------------------------------------------------

class TestUpdateCostOfAttendanceDepth:
    def test_rewrites_one_component_and_retotals_and_leaves_the_rest(self, env):
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-update-cost-of-attendance"], conn, ns(
            id=s["cost_of_attendance_id"], tuition_fees="16000",
            books_supplies=None, room_board=None, transportation=None,
            personal_expenses=None, loan_fees=None, is_active=None))
        assert is_ok(r), r
        assert r["total_coa"] == "30800.00"
        row = tuple(conn.execute(
            "SELECT tuition_fees, books_supplies, room_board, transportation, "
            "personal_expenses, loan_fees, total_coa, enrollment_status, "
            "living_arrangement, is_active FROM finaid_cost_of_attendance "
            "WHERE id = ?", (s["cost_of_attendance_id"],)).fetchone())
        assert row == ("16000.00", "1200", "10000", "1500", "2000", "100",
                       "30800.00", "full_time", "on_campus", 1)
        # No ledger legs: a budget row only, never journals.

    def test_refuses_an_unknown_budget_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-cost-of-attendance"], conn, ns(
            id="no-such-coa", tuition_fees="16000", books_supplies=None,
            room_board=None, transportation=None, personal_expenses=None,
            loan_fees=None, is_active=None))
        assert is_error(r)
        assert r["message"] == "COA not found"
        assert _snapshot(conn) == before

    def test_finding_negative_component_is_stored_not_refused(self, env):
        """FINDING (deliberately not fixed): ``finaid-add-cost-of-attendance``
        refuses a negative component, but this update path stores it and
        retotals around it. Real behaviour pinned here; fix is a later task."""
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-update-cost-of-attendance"], conn, ns(
            id=s["cost_of_attendance_id"], tuition_fees=None,
            books_supplies="-200", room_board=None, transportation=None,
            personal_expenses=None, loan_fees=None, is_active=None))
        assert is_ok(r), r
        row = tuple(conn.execute(
            "SELECT books_supplies, total_coa FROM finaid_cost_of_attendance "
            "WHERE id = ?", (s["cost_of_attendance_id"],)).fetchone())
        assert row == ("-200.00", "28400.00")


# ---------------------------------------------------------------------------
# finaid-update-isir — stored row
# ---------------------------------------------------------------------------

class TestUpdateIsirDepth:
    def test_rewrites_named_fields_verbatim_and_leaves_the_rest(self, env):
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-update-isir"], conn, ns(
            isir_id=s["isir_id"], sai="-1500",
            dependency_status="independent", verification_group="V1",
            pell_index=None, verification_flag=None, receipt_date=None,
            fafsa_submission_id=None, is_active_transaction=None))
        assert is_ok(r), r
        assert r["updated"] is True
        row = tuple(conn.execute(
            "SELECT sai, dependency_status, pell_index, verification_flag, "
            "verification_group, has_unresolved_cflags, agi, household_size, "
            "status, receipt_date FROM finaid_isir WHERE id = ?",
            (s["isir_id"],)).fetchone())
        assert row == ("-1500", "independent", "100", 0, "V1", 0, "50000",
                       4, "received", "2025-03-01")
        # No ledger legs: an ISIR row only, never journals.

    def test_refuses_an_unknown_isir_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-isir"], conn, ns(
            isir_id="no-such-isir", sai="-1500", dependency_status=None,
            pell_index=None, verification_flag=None, verification_group=None,
            receipt_date=None, fafsa_submission_id=None,
            is_active_transaction=None))
        assert is_error(r)
        assert r["message"] == "ISIR not found"
        assert _snapshot(conn) == before

    def test_finding_empty_update_reports_updated(self, env):
        """FINDING (deliberately not fixed): unlike its sibling update
        actions, this one has no "No fields to update" guard, so an empty
        update still reports success. Business columns are untouched."""
        s, conn = env, env["conn"]
        cols = ("sai, dependency_status, pell_index, verification_flag, "
                "verification_group, has_unresolved_cflags, agi, "
                "household_size, status, receipt_date")
        before = tuple(conn.execute(
            f"SELECT {cols} FROM finaid_isir WHERE id = ?",
            (s["isir_id"],)).fetchone())
        r = call_action(FA_ACTIONS["finaid-update-isir"], conn, ns(
            isir_id=s["isir_id"], sai=None, dependency_status=None,
            pell_index=None, verification_flag=None, verification_group=None,
            receipt_date=None, fafsa_submission_id=None,
            is_active_transaction=None))
        assert is_ok(r), r
        assert r["updated"] is True
        after = tuple(conn.execute(
            f"SELECT {cols} FROM finaid_isir WHERE id = ?",
            (s["isir_id"],)).fetchone())
        assert after == before


# ---------------------------------------------------------------------------
# finaid-update-award-package — stored row
# ---------------------------------------------------------------------------

class TestUpdateAwardPackageDepth:
    def test_writes_only_the_given_fields_and_leaves_totals_and_awards(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        award_id = _award(s, pkg_id, "pell", "5000.00")
        r = call_action(FA_ACTIONS["finaid-update-award-package"], conn, ns(
            award_package_id=pkg_id, notes="needs SAP review",
            acceptance_deadline="2025-08-15", approved_by="director",
            approved_at="2025-07-20", enrollment_status=None))
        assert is_ok(r), r
        assert r["updated"] is True
        row = tuple(conn.execute(
            "SELECT notes, acceptance_deadline, approved_by, approved_at, "
            "enrollment_status FROM finaid_award_package WHERE id = ?",
            (pkg_id,)).fetchone())
        assert row == ("needs SAP review", "2025-08-15", "director",
                       "2025-07-20", "full_time")
        assert _package_row(conn, pkg_id) == ("28300.00", "5000.00", "0.00",
                                              "0.00", "5000.00", "draft")
        assert conn.execute(
            "SELECT offered_amount FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()[0] == "5000.00"
        # No ledger legs: package header fields only, never journals.

    def test_refuses_an_empty_update_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        _award(s, pkg_id, "pell", "5000.00")
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-award-package"], conn, ns(
            award_package_id=pkg_id, notes=None, enrollment_status=None,
            acceptance_deadline=None, approved_by=None, approved_at=None))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-update-award — stored row
# ---------------------------------------------------------------------------

class TestUpdateAwardDepth:
    def test_raises_the_offer_and_rolls_package_totals_and_leaves_sibling(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        pell = _award(s, pkg_id, "pell", "5000.00")
        loan_award = _award(s, pkg_id, "subsidized_loan", "2000.00")
        r = call_action(FA_ACTIONS["finaid-update-award"], conn, ns(
            award_id=pell, offered_amount="5500.75", notes="revised",
            gl_account_id="GL-100"))
        assert is_ok(r), r
        assert r["updated"] is True
        row = tuple(conn.execute(
            "SELECT offered_amount, accepted_amount, notes, gl_account_id "
            "FROM finaid_award WHERE id = ?", (pell,)).fetchone())
        assert row == ("5500.75", "0", "revised", "GL-100")
        assert conn.execute(
            "SELECT offered_amount FROM finaid_award WHERE id = ?",
            (loan_award,)).fetchone()[0] == "2000.00"
        assert _package_row(conn, pkg_id) == ("28300.00", "5500.75",
                                              "2000.00", "0.00", "7500.75",
                                              "draft")
        # No ledger legs: offer and roll-up totals only, never journals.

    def test_refuses_below_accepted_and_non_positive_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        pell = _award(s, pkg_id, "pell", "5000.00")
        accept = call_action(FA_ACTIONS["finaid-accept-award"], conn, ns(
            award_id=pell, accepted_amount="4000.00",
            acceptance_date="2025-08-01"))
        assert is_ok(accept), accept
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-award"], conn, ns(
            award_id=pell, offered_amount="3999.99", notes=None,
            gl_account_id=None))
        assert is_error(r)
        assert r["message"] == ("Offered amount 3999.99 is below the accepted "
                                "amount 4000.00")
        r = call_action(FA_ACTIONS["finaid-update-award"], conn, ns(
            award_id=pell, offered_amount="0", notes=None,
            gl_account_id=None))
        assert is_error(r)
        assert r["message"] == "offered_amount must be greater than zero"
        assert _snapshot(conn) == before
        assert tuple(conn.execute(
            "SELECT offered_amount, accepted_amount FROM finaid_award "
            "WHERE id = ?", (pell,)).fetchone()) == ("5000.00", "4000.00")


# ---------------------------------------------------------------------------
# finaid-update-cod-status — stored row
# ---------------------------------------------------------------------------

class TestUpdateCodStatusDepth:
    def test_stamps_status_and_response_date_and_leaves_amounts(self, env):
        s, conn = env, env["conn"]
        _pkg_id, award_id = _accepted_pell(s)
        disb_id = _disburse(s, award_id)
        r = call_action(FA_ACTIONS["finaid-update-cod-status"], conn, ns(
            id=disb_id, cod_status="acknowledged",
            cod_response_date="2025-09-10"))
        assert is_ok(r), r
        assert r["cod_status"] == "acknowledged"
        row = tuple(conn.execute(
            "SELECT cod_status, cod_response_date, amount, disbursement_type "
            "FROM finaid_disbursement WHERE id = ?", (disb_id,)).fetchone())
        assert row == ("acknowledged", "2025-09-10", "1500.00",
                       "disbursement")
        assert conn.execute(
            "SELECT disbursed_amount FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()[0] == "1500.00"
        # No ledger legs: a COD reporting stamp only, never journals.

    def test_refuses_a_missing_status_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _pkg_id, award_id = _accepted_pell(s)
        disb_id = _disburse(s, award_id)
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-cod-status"], conn, ns(
            id=disb_id, cod_status=None, cod_response_date=None))
        assert is_error(r)
        assert r["message"] == "id and cod_status are required"
        assert _snapshot(conn) == before

    def test_finding_unknown_disbursement_reports_ok_and_writes_nothing(self, env):
        """FINDING (deliberately not fixed): this handler checks neither
        that the disbursement exists nor how many rows it touched, so an
        unknown id still reports success. Real behaviour pinned here; fix
        is a later task."""
        s, conn = env, env["conn"]
        _pkg_id, award_id = _accepted_pell(s)
        _disburse(s, award_id)
        before = _snapshot(conn)
        count_before = _count(conn, "finaid_disbursement")
        r = call_action(FA_ACTIONS["finaid-update-cod-status"], conn, ns(
            id="no-such-disbursement", cod_status="acknowledged",
            cod_response_date="2025-09-10"))
        assert is_ok(r), r
        assert r["cod_status"] == "acknowledged"
        assert _count(conn, "finaid_disbursement") == count_before
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-update-loan — stored row
# ---------------------------------------------------------------------------

class TestUpdateLoanDepth:
    def test_rewrites_amount_rate_and_cod_id_and_leaves_the_rest(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        r = call_action(LOAN_ACTIONS["finaid-update-loan"], conn, ns(
            id=loan_id, loan_amount="4000", interest_rate="7.05",
            cod_loan_id="COD-123", loan_period_start=None,
            loan_period_end=None, first_disbursement_amount=None,
            second_disbursement_amount=None, origination_fee=None))
        assert is_ok(r), r
        assert r["updated"] is True
        assert _loan_row(conn, loan_id) == (
            "4000.00", "1750.00", "1750.00", "29.05", "7.05", "COD-123",
            "", "", 0, "", 0, "", 0, "", "2025-08-25", "2026-05-15",
            "originated")
        assert _holds(conn, award_id) == ["mpn_pending", "ec_pending"]
        # No ledger legs: loan tracking fields only, never journals.

    def test_refuses_an_empty_update_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        loan_id, _award_id, _pkg_id = _loan(s)
        before = _snapshot(conn)
        r = call_action(LOAN_ACTIONS["finaid-update-loan"], conn, ns(
            id=loan_id, loan_amount=None, interest_rate=None,
            cod_loan_id=None, loan_period_start=None, loan_period_end=None,
            first_disbursement_amount=None,
            second_disbursement_amount=None, origination_fee=None))
        assert is_error(r)
        assert r["message"] == "No updatable fields provided"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-update-mpn-status — stored row
# ---------------------------------------------------------------------------

class TestUpdateMpnStatusDepth:
    def test_signs_the_mpn_and_clears_only_the_mpn_hold(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        assert _holds(conn, award_id) == ["mpn_pending", "ec_pending"]
        r = call_action(LOAN_ACTIONS["finaid-update-mpn-status"], conn, ns(
            id=loan_id, mpn_signed_date="2025-08-22"))
        assert is_ok(r), r
        assert r["mpn_signed"] is True
        assert r["mpn_signed_date"] == "2025-08-22"
        assert _loan_row(conn, loan_id) == (
            "3500.00", "1750.00", "1750.00", "29.05", "6.53", "", "", "",
            1, "2025-08-22", 0, "", 0, "", "2025-08-25", "2026-05-15",
            "originated")
        assert _holds(conn, award_id) == ["ec_pending"]
        # No ledger legs: an MPN flag and one hold entry only, never journals.

    def test_refuses_a_missing_date_and_an_unknown_loan_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        before = _snapshot(conn)
        r = call_action(LOAN_ACTIONS["finaid-update-mpn-status"], conn, ns(
            id=loan_id, mpn_signed_date=None))
        assert is_error(r)
        assert r["message"] == "Missing required field: mpn_signed_date"
        r = call_action(LOAN_ACTIONS["finaid-update-mpn-status"], conn, ns(
            id="no-such-loan", mpn_signed_date="2025-08-22"))
        assert is_error(r)
        assert r["message"] == "Loan not found: no-such-loan"
        assert _snapshot(conn) == before
        assert _holds(conn, award_id) == ["mpn_pending", "ec_pending"]


# ---------------------------------------------------------------------------
# finaid-update-entrance-counseling — stored row
# ---------------------------------------------------------------------------

class TestUpdateEntranceCounselingDepth:
    def test_completes_counseling_and_clears_only_the_ec_hold(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        r = call_action(LOAN_ACTIONS["finaid-update-entrance-counseling"], conn, ns(
            id=loan_id, entrance_counseling_date="2025-08-20"))
        assert is_ok(r), r
        assert r["entrance_counseling_complete"] is True
        assert r["entrance_counseling_date"] == "2025-08-20"
        assert _loan_row(conn, loan_id) == (
            "3500.00", "1750.00", "1750.00", "29.05", "6.53", "", "", "",
            0, "", 1, "2025-08-20", 0, "", "2025-08-25", "2026-05-15",
            "originated")
        assert _holds(conn, award_id) == ["mpn_pending"]
        # No ledger legs: a counseling flag and one hold entry only, never journals.

    def test_refuses_a_missing_date_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        before = _snapshot(conn)
        r = call_action(LOAN_ACTIONS["finaid-update-entrance-counseling"], conn, ns(
            id=loan_id, entrance_counseling_date=None))
        assert is_error(r)
        assert r["message"] == "Missing required field: entrance_counseling_date"
        assert _snapshot(conn) == before
        assert _holds(conn, award_id) == ["mpn_pending", "ec_pending"]


# ---------------------------------------------------------------------------
# finaid-update-exit-counseling — stored row
# ---------------------------------------------------------------------------

class TestUpdateExitCounselingDepth:
    def test_completes_exit_counseling_and_leaves_mpn_and_entrance(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        r = call_action(LOAN_ACTIONS["finaid-update-exit-counseling"], conn, ns(
            id=loan_id, exit_counseling_date="2026-05-01"))
        assert is_ok(r), r
        assert r["exit_counseling_complete"] is True
        assert r["exit_counseling_date"] == "2026-05-01"
        assert _loan_row(conn, loan_id) == (
            "3500.00", "1750.00", "1750.00", "29.05", "6.53", "", "", "",
            0, "", 0, "", 1, "2026-05-01", "2025-08-25", "2026-05-15",
            "originated")
        assert _holds(conn, award_id) == ["mpn_pending", "ec_pending"]
        # No ledger legs: a counseling flag only, never journals.

    def test_refuses_an_unknown_loan_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        loan_id, _award_id, _pkg_id = _loan(s)
        before = _snapshot(conn)
        r = call_action(LOAN_ACTIONS["finaid-update-exit-counseling"], conn, ns(
            id="no-such-loan", exit_counseling_date="2026-05-01"))
        assert is_error(r)
        assert r["message"] == "Loan not found: no-such-loan"
        assert _snapshot(conn) == before
        assert _loan_row(conn, loan_id)[12:14] == (0, "")


# ---------------------------------------------------------------------------
# finaid-update-cod-origination-status — stored row
# ---------------------------------------------------------------------------

class TestUpdateCodOriginationStatusDepth:
    def test_accepted_flips_the_loan_active_and_rejected_leaves_it_originated(self, env):
        s, conn = env, env["conn"]
        loan_id, award_id, _pkg_id = _loan(s)
        r = call_action(LOAN_ACTIONS["finaid-update-cod-origination-status"], conn, ns(
            id=loan_id, cod_origination_status="accepted",
            cod_origination_date="2025-10-01"))
        assert is_ok(r), r
        assert r["cod_origination_status"] == "accepted"
        assert r["cod_origination_date"] == "2025-10-01"
        assert r["loan_status"] == "active"
        assert _loan_row(conn, loan_id) == (
            "3500.00", "1750.00", "1750.00", "29.05", "6.53", "", "accepted",
            "2025-10-01", 0, "", 0, "", 0, "", "2025-08-25", "2026-05-15",
            "active")
        assert _holds(conn, award_id) == ["mpn_pending", "ec_pending"]
        second_id, _second_award, _second_pkg = _loan(s)
        r = call_action(LOAN_ACTIONS["finaid-update-cod-origination-status"], conn, ns(
            id=second_id, cod_origination_status="rejected",
            cod_origination_date="2025-10-02"))
        assert is_ok(r), r
        assert r["loan_status"] is None
        assert _loan_row(conn, second_id)[6:8] == ("rejected", "2025-10-02")
        assert _loan_row(conn, second_id)[16] == "originated"
        # No ledger legs: origination tracking flags only, never journals.

    def test_refuses_an_invalid_status_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        loan_id, _award_id, _pkg_id = _loan(s)
        before = _snapshot(conn)
        r = call_action(LOAN_ACTIONS["finaid-update-cod-origination-status"], conn, ns(
            id=loan_id, cod_origination_status="shipped",
            cod_origination_date="2025-10-01"))
        assert is_error(r)
        assert r["message"] == ("Invalid cod_origination_status 'shipped'. "
                                "Must be one of: 'pending', 'accepted', "
                                "'rejected', ''")
        assert _snapshot(conn) == before
        assert _loan_row(conn, loan_id)[6:8] == ("", "")
