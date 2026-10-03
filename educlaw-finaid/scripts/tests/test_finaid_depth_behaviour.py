"""Behavioural depth tests for 12 finaid actions previously covered by shape only.

Each action below already had a test asserting the response envelope (``is_ok``)
in ``test_finaid.py``. Those tests stay untouched; the tests here prove what each
action actually does to the database: the exact row written (money as exact
``TEXT`` strings, never float), the rows that must NOT have changed, and one
input-validation refusal that must leave the database byte-identical.

None of these 12 handlers reaches the general ledger: every one of them writes
only ``finaid_*`` rows (scholarships and work-study also append one ``audit_log``
row) and never posts journals. Each success test says so in a comment so a later
reader does not add debit/credit assertions that cannot hold.

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
SCHOL_ACTIONS = _load("scholarships", _SCRIPTS_DIR).ACTIONS
WS_ACTIONS = _load("work_study", _SCRIPTS_DIR).ACTIONS
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
    """Full row dump of every owned table (plus audit_log) for before/after compare."""
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


def _create_package(s, **kw):
    args = dict(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", financial_need=None,
        acceptance_deadline=None, packaged_by=None, notes=None)
    args.update(kw)
    return call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(**args))


def _package(s):
    r = _create_package(s)
    assert is_ok(r), r
    return r["id"]


def _add_award(s, pkg_id, aid_type, offered, aid_source="federal"):
    return call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source=aid_source, offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None, notes=None))


# ---------------------------------------------------------------------------
# finaid-add-aid-year — stored row
# ---------------------------------------------------------------------------

class TestAddAidYearDepth:
    def test_writes_aid_year_row_with_exact_money_and_inactive(self, env):
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-add-aid-year"], conn, ns(
            company_id=s["company_id"], aid_year_code="2026-2027",
            description="Depth year", start_date="2026-07-01",
            end_date="2027-06-30", pell_max_award="7395.005"))
        assert is_ok(r), r
        assert r["aid_year_code"] == "2026-2027"
        row = conn.execute(
            "SELECT aid_year_code, description, start_date, end_date, "
            "pell_max_award, is_active, company_id "
            "FROM finaid_aid_year WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == ("2026-2027", "Depth year", "2026-07-01",
                              "2027-06-30", "7395.01", 0, s["company_id"])
        # The seeded year is untouched and still the active one.
        seed = conn.execute(
            "SELECT aid_year_code, pell_max_award, is_active "
            "FROM finaid_aid_year WHERE id = ?", (s["aid_year_id"],)).fetchone()
        assert tuple(seed) == ("2025-2026", "7395", 1)
        # No ledger legs: only a finaid_aid_year row is written, never journals.

    def test_refuses_a_missing_code_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-add-aid-year"], conn, ns(
            company_id=s["company_id"], aid_year_code=None, description=None,
            start_date="2026-07-01", end_date="2027-06-30", pell_max_award=None))
        assert is_error(r)
        assert r["message"] == "aid_year_code is required"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_aid_year") == 1


# ---------------------------------------------------------------------------
# finaid-activate-aid-year — stored row (status flip on two rows)
# ---------------------------------------------------------------------------

class TestActivateAidYearDepth:
    def test_activates_new_year_and_deactivates_old_year(self, env):
        s, conn = env, env["conn"]
        created = call_action(FA_ACTIONS["finaid-add-aid-year"], conn, ns(
            company_id=s["company_id"], aid_year_code="2026-2027",
            description="Next", start_date="2026-07-01",
            end_date="2027-06-30", pell_max_award="7395"))
        assert is_ok(created), created
        new_id = created["id"]
        assert conn.execute(
            "SELECT is_active FROM finaid_aid_year WHERE id = ?",
            (new_id,)).fetchone()[0] == 0
        r = call_action(FA_ACTIONS["finaid-activate-aid-year"], conn, ns(
            id=new_id, company_id=s["company_id"]))
        assert is_ok(r), r
        assert r["is_active"] == 1
        flags = dict(conn.execute(
            "SELECT aid_year_code, is_active FROM finaid_aid_year").fetchall())
        assert flags == {"2025-2026": 0, "2026-2027": 1}
        # No ledger legs: only is_active flags move, never journals.

    def test_refuses_an_unknown_year_and_flips_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-activate-aid-year"], conn, ns(
            id="no-such-aid-year", company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == "Aid year not found"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT is_active FROM finaid_aid_year WHERE id = ?",
            (s["aid_year_id"],)).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# finaid-add-award — stored row
# ---------------------------------------------------------------------------

class TestAddAwardDepth:
    def test_writes_award_and_rolls_package_grant_totals(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        r = _add_award(s, pkg_id, "pell", "5000.005")
        assert is_ok(r), r
        assert r["offered_amount"] == "5000.01"
        row = conn.execute(
            "SELECT award_package_id, student_id, aid_year_id, academic_term_id, "
            "aid_type, aid_source, offered_amount, accepted_amount, "
            "disbursed_amount, acceptance_status, is_locked, company_id "
            "FROM finaid_award WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (pkg_id, s["student_id"], s["aid_year_id"],
                              s["term_id"], "pell", "federal", "5000.01",
                              "0", "0", "pending", 0, s["company_id"])
        totals = conn.execute(
            "SELECT total_grants, total_loans, total_work_study, total_aid "
            "FROM finaid_award_package WHERE id = ?", (pkg_id,)).fetchone()
        assert tuple(totals) == ("5000.01", "0.00", "0.00", "5000.01")
        # No ledger legs: award packaging moves offered totals only, never journals.

    def test_refuses_a_non_positive_offer_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        before = _snapshot(conn)
        r = _add_award(s, pkg_id, "pell", "0")
        assert is_error(r)
        assert r["message"] == "offered_amount must be greater than zero"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_award") == 0
        totals = conn.execute(
            "SELECT total_grants, total_aid FROM finaid_award_package "
            "WHERE id = ?", (pkg_id,)).fetchone()
        assert tuple(totals) == ("0", "0")


# ---------------------------------------------------------------------------
# finaid-accept-award — stored row (status change)
# ---------------------------------------------------------------------------

class TestAcceptAwardDepth:
    def test_accepts_partial_amount_and_leaves_offer_and_siblings_alone(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        r = _add_award(s, pkg_id, "pell", "5000.00")
        assert is_ok(r), r
        award_id = r["id"]
        other_pkg = _package(s)
        other = _add_award(s, other_pkg, "fseog", "2000.00")
        assert is_ok(other), other
        acc = call_action(FA_ACTIONS["finaid-accept-award"], conn, ns(
            award_id=award_id, accepted_amount="4000.00",
            acceptance_date="2025-08-01"))
        assert is_ok(acc), acc
        row = conn.execute(
            "SELECT offered_amount, accepted_amount, disbursed_amount, "
            "acceptance_status, acceptance_date "
            "FROM finaid_award WHERE id = ?", (award_id,)).fetchone()
        assert tuple(row) == ("5000.00", "4000.00", "0", "accepted", "2025-08-01")
        untouched = conn.execute(
            "SELECT offered_amount, accepted_amount, acceptance_status "
            "FROM finaid_award WHERE id = ?", (other["id"],)).fetchone()
        assert tuple(untouched) == ("2000.00", "0", "pending")
        # No ledger legs: acceptance flips status/amounts only, never journals.

    def test_refuses_more_than_offered_and_changes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        r = _add_award(s, pkg_id, "pell", "5000.00")
        assert is_ok(r), r
        before = _snapshot(conn)
        acc = call_action(FA_ACTIONS["finaid-accept-award"], conn, ns(
            award_id=r["id"], accepted_amount="6000.00",
            acceptance_date="2025-08-01"))
        assert is_error(acc)
        assert acc["message"] == ("Accepted amount 6000.00 exceeds the "
                                  "offered amount 5000.00")
        assert _snapshot(conn) == before
        row = conn.execute(
            "SELECT accepted_amount, acceptance_status, acceptance_date "
            "FROM finaid_award WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == ("0", "pending", "")


# ---------------------------------------------------------------------------
# finaid-add-cost-of-attendance — stored row
# ---------------------------------------------------------------------------

class TestAddCostOfAttendanceDepth:
    def test_writes_rounded_components_and_exact_total(self, env):
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-add-cost-of-attendance"], conn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            program_id=s["program_id"], enrollment_status="half_time",
            living_arrangement="off_campus", tuition_fees="12500.005",
            books_supplies="1200", room_board="9000.50",
            transportation="1500.25", personal_expenses="2000",
            loan_fees="99.99"))
        assert is_ok(r), r
        assert r["total_coa"] == "26300.75"
        row = conn.execute(
            "SELECT program_id, enrollment_status, living_arrangement, "
            "tuition_fees, books_supplies, room_board, transportation, "
            "personal_expenses, loan_fees, total_coa, is_active "
            "FROM finaid_cost_of_attendance WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (s["program_id"], "half_time", "off_campus",
                              "12500.01", "1200.00", "9000.50", "1500.25",
                              "2000.00", "99.99", "26300.75", 1)
        # The seeded budget is untouched.
        seed = conn.execute(
            "SELECT total_coa FROM finaid_cost_of_attendance WHERE id = ?",
            (s["cost_of_attendance_id"],)).fetchone()
        assert tuple(seed) == ("29800",)
        # No ledger legs: a budget definition row only, never journals.

    def test_refuses_a_negative_component_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-add-cost-of-attendance"], conn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            program_id=None, enrollment_status="half_time",
            living_arrangement="with_parent", tuition_fees="12500",
            books_supplies="1200", room_board="-9000.00",
            transportation="1500", personal_expenses="2000", loan_fees="100"))
        assert is_error(r)
        assert r["message"] == "room_board cannot be negative"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_cost_of_attendance") == 1


# ---------------------------------------------------------------------------
# finaid-add-fund-allocation — stored row
# ---------------------------------------------------------------------------

class TestAddFundAllocationDepth:
    def test_opens_with_whole_allocation_available(self, env):
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-add-fund-allocation"], conn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            fund_type="fseog", fund_name="Depth Campus Fund",
            total_allocation="250000.005"))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT aid_year_id, fund_type, fund_name, total_allocation, "
            "committed_amount, disbursed_amount, available_amount, company_id "
            "FROM finaid_fund_allocation WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (s["aid_year_id"], "fseog", "Depth Campus Fund",
                              "250000.01", "0", "0", "250000.01",
                              s["company_id"])
        # No ledger legs: fund setup moves no money, never journals.

    def test_refuses_a_missing_fund_type_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-add-fund-allocation"], conn, ns(
            aid_year_id=s["aid_year_id"], company_id=s["company_id"],
            fund_type=None, fund_name="Untyped Fund",
            total_allocation="1000.00"))
        assert is_error(r)
        assert r["message"] == "fund_type is required"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_fund_allocation") == 0


# ---------------------------------------------------------------------------
# finaid-add-isir-cflag — stored row
# ---------------------------------------------------------------------------

class TestAddIsirCFlagDepth:
    def test_writes_pending_cflag_and_marks_isir_unresolved(self, env):
        s, conn = env, env["conn"]
        assert conn.execute(
            "SELECT has_unresolved_cflags FROM finaid_isir WHERE id = ?",
            (s["isir_id"],)).fetchone()[0] == 0
        r = call_action(FA_ACTIONS["finaid-add-isir-cflag"], conn, ns(
            isir_id=s["isir_id"], company_id=s["company_id"],
            cflag_code="C01", cflag_description="SSN match flag",
            blocks_disbursement=1))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT isir_id, student_id, cflag_code, cflag_description, "
            "blocks_disbursement, resolution_status, company_id "
            "FROM finaid_isir_cflag WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (s["isir_id"], s["student_id"], "C01",
                              "SSN match flag", 1, "pending", s["company_id"])
        assert conn.execute(
            "SELECT has_unresolved_cflags FROM finaid_isir WHERE id = ?",
            (s["isir_id"],)).fetchone()[0] == 1
        # No ledger legs: flags only gate disbursement, never journals.

    def test_refuses_an_unknown_isir_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-add-isir-cflag"], conn, ns(
            isir_id="no-such-isir", company_id=s["company_id"],
            cflag_code="C01", cflag_description="SSN match flag",
            blocks_disbursement=1))
        assert is_error(r)
        assert r["message"] == "ISIR not found"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_isir_cflag") == 0
        assert conn.execute(
            "SELECT has_unresolved_cflags FROM finaid_isir WHERE id = ?",
            (s["isir_id"],)).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# finaid-add-loan — stored row
# ---------------------------------------------------------------------------

def _loan_award(s, pkg_id, aid_type="subsidized_loan", offered="3500"):
    r = _add_award(s, pkg_id, aid_type, offered)
    assert is_ok(r), r
    return r["id"]


def _add_loan(s, award_id, amount="3500.005"):
    return call_action(LOAN_ACTIONS["finaid-add-loan"], s["conn"], ns(
        company_id=s["company_id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], award_id=award_id,
        loan_type="subsidized", loan_period_start="2025-08-25",
        loan_period_end="2026-05-15", loan_amount=amount,
        first_disbursement_amount="1750", second_disbursement_amount="1750",
        origination_fee="29.05", interest_rate="6.53",
        borrower_id=s["student_id"], borrower_type="student",
        cod_loan_id=None, mpn_signed_date=None,
        entrance_counseling_required=1, entrance_counseling_date=None,
        exit_counseling_required=0, exit_counseling_date=None))


class TestAddLoanDepth:
    def test_writes_loan_and_holds_on_the_award(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        award_id = _loan_award(s, pkg_id)
        r = _add_loan(s, award_id)
        assert is_ok(r), r
        row = conn.execute(
            "SELECT student_id, award_id, aid_year_id, loan_type, "
            "loan_period_start, loan_period_end, loan_amount, "
            "first_disbursement_amount, second_disbursement_amount, "
            "origination_fee, interest_rate, mpn_required, mpn_signed, "
            "entrance_counseling_required, entrance_counseling_complete, "
            "exit_counseling_required, borrower_id, borrower_type, status, "
            "company_id "
            "FROM finaid_loan WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (s["student_id"], award_id, s["aid_year_id"],
                              "subsidized", "2025-08-25", "2026-05-15",
                              "3500.01", "1750.00", "1750.00", "29.05",
                              "6.53", 1, 0, 1, 0, 0, s["student_id"],
                              "student", "originated", s["company_id"])
        holds = conn.execute(
            "SELECT disbursement_holds FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()[0]
        assert json.loads(holds) == ["mpn_pending", "ec_pending"]
        # No ledger legs: origination tracking only, never journals.

    def test_refuses_a_non_loan_award_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        grant_award = _loan_award(s, pkg_id, aid_type="pell", offered="5000")
        before = _snapshot(conn)
        r = _add_loan(s, grant_award)
        assert is_error(r)
        assert "is not a loan type" in r["message"]
        assert r["message"].startswith("Award aid_type 'pell'")
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_loan") == 0
        holds = conn.execute(
            "SELECT disbursement_holds FROM finaid_award WHERE id = ?",
            (grant_award,)).fetchone()[0]
        assert json.loads(holds) == []


# ---------------------------------------------------------------------------
# finaid-add-professional-judgment — stored row
# ---------------------------------------------------------------------------

class TestAddProfessionalJudgmentDepth:
    def test_writes_pj_request_with_exact_values(self, env):
        s, conn = env, env["conn"]
        r = call_action(FA_ACTIONS["finaid-add-professional-judgment"], conn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], pj_type="sai_adjustment",
            pj_reason="job_loss", reason_narrative="Parent laid off in June",
            data_element_changed="agi", original_value="50000",
            adjusted_value="20000", effective_date="2025-08-01",
            authorized_by="counselor", authorization_date="2025-08-02"))
        assert is_ok(r), r
        assert r["pj_type"] == "sai_adjustment"
        row = conn.execute(
            "SELECT student_id, aid_year_id, award_package_id, pj_type, "
            "pj_reason, reason_narrative, data_element_changed, "
            "original_value, adjusted_value, effective_date, "
            "supporting_documentation, authorized_by, authorization_date, "
            "supervisor_review_required, company_id "
            "FROM finaid_professional_judgment WHERE id = ?",
            (r["id"],)).fetchone()
        assert tuple(row) == (s["student_id"], s["aid_year_id"], None,
                              "sai_adjustment", "job_loss",
                              "Parent laid off in June", "agi", "50000",
                              "20000", "2025-08-01", "[]", "counselor",
                              "2025-08-02", 0, s["company_id"])
        # No ledger legs: a judgment request row only, never journals.

    def test_refuses_a_missing_pj_type_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-add-professional-judgment"], conn, ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            company_id=s["company_id"], pj_type=None, pj_reason="job_loss",
            reason_narrative="narr", data_element_changed="agi",
            original_value="50000", adjusted_value="20000",
            effective_date="2025-08-01", authorized_by="counselor",
            authorization_date="2025-08-02"))
        assert is_error(r)
        assert r["message"] == "pj_type is required"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_professional_judgment") == 0


# ---------------------------------------------------------------------------
# finaid-add-scholarship-program — stored row
# ---------------------------------------------------------------------------

def _add_program(s, name="Depth Merit", code="DEPTH-MERIT-1"):
    return call_action(SCHOL_ACTIONS["finaid-add-scholarship-program"], s["conn"], ns(
        company_id=s["company_id"], name=name, code=code,
        scholarship_type="merit", funding_source="endowment",
        award_method="application_required", award_amount_type="fixed",
        award_amount="5000.005", min_award="1000", max_award="8000",
        annual_budget="100000", max_recipients=20, renewal_eligible=1,
        renewal_gpa_minimum="3.0", renewal_credits_minimum="12",
        eligibility_criteria="{}", application_deadline="2025-06-01",
        award_period="annual", applies_to_aid_type="institutional_scholarship",
        description="Depth program"))


class TestAddScholarshipProgramDepth:
    def test_writes_program_with_full_budget_remaining(self, env):
        s, conn = env, env["conn"]
        r = _add_program(s)
        assert is_ok(r), r
        assert r["code"] == "DEPTH-MERIT-1"
        row = conn.execute(
            "SELECT name, code, scholarship_type, funding_source, "
            "award_method, award_amount_type, award_amount, min_award, "
            "max_award, annual_budget, budget_remaining, max_recipients, "
            "renewal_eligible, renewal_gpa_minimum, renewal_credits_minimum, "
            "award_period, applies_to_aid_type, is_active, company_id "
            "FROM finaid_scholarship_program WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == ("Depth Merit", "DEPTH-MERIT-1", "merit",
                              "endowment", "application_required", "fixed",
                              "5000.01", "1000.00", "8000.00", "100000.00",
                              "100000.00", 20, 1, "3.0", "12", "annual",
                              "institutional_scholarship", 1, s["company_id"])
        audit_rows = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ?", (r["id"],)).fetchall()
        assert [tuple(a) for a in audit_rows] == [
            ("finaid-educlaw-finaid", "finaid-add-scholarship-program",
             "finaid_scholarship_program", r["id"])]
        # No ledger legs: program definition plus one audit row, never journals.

    def test_refuses_a_missing_name_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(SCHOL_ACTIONS["finaid-add-scholarship-program"], s["conn"], ns(
            company_id=s["company_id"], name=None, code="NO-NAME-1",
            scholarship_type="merit", funding_source="endowment",
            award_method="application_required", award_amount_type="fixed",
            award_amount="5000", min_award=None, max_award=None,
            annual_budget="100000", max_recipients=20, renewal_eligible=1,
            renewal_gpa_minimum="3.0", renewal_credits_minimum=None,
            eligibility_criteria=None, application_deadline=None,
            award_period="annual",
            applies_to_aid_type="institutional_scholarship",
            description=None))
        assert is_error(r)
        assert r["message"] == "--name is required"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_scholarship_program") == 0


# ---------------------------------------------------------------------------
# finaid-add-verification-document — stored row
# ---------------------------------------------------------------------------

def _v1_request(s):
    r = call_action(FA_ACTIONS["finaid-create-verification-request"], s["conn"], ns(
        isir_id=s["isir_id"], student_id=s["student_id"],
        company_id=s["company_id"], verification_group="V1",
        deadline_date="2025-06-01", requested_date="2025-04-02",
        assigned_to="counselor"))
    assert is_ok(r), r
    return r["id"]


def _doc_count(conn, req_id):
    return conn.execute(
        "SELECT COUNT(*) FROM finaid_verification_document "
        "WHERE verification_request_id = ?", (req_id,)).fetchone()[0]


class TestAddVerificationDocumentDepth:
    def test_appends_document_and_leaves_request_and_siblings_alone(self, env):
        s, conn = env, env["conn"]
        req_id = _v1_request(s)
        assert _doc_count(conn, req_id) == 3
        r = call_action(FA_ACTIONS["finaid-add-verification-document"], conn, ns(
            verification_request_id=req_id, student_id=s["student_id"],
            company_id=s["company_id"], document_type="other",
            document_description="Extra bank statement", is_required=1))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT verification_request_id, student_id, document_type, "
            "document_description, is_required, submission_status, company_id "
            "FROM finaid_verification_document WHERE id = ?",
            (r["id"],)).fetchone()
        assert tuple(row) == (req_id, s["student_id"], "other",
                              "Extra bank statement", 1, "not_submitted",
                              s["company_id"])
        assert _doc_count(conn, req_id) == 4
        req = conn.execute(
            "SELECT status FROM finaid_verification_request WHERE id = ?",
            (req_id,)).fetchone()
        assert tuple(req) == ("initiated",)
        # No ledger legs: a document row only, never journals.

    def test_refuses_a_missing_document_type_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        req_id = _v1_request(s)
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-add-verification-document"], conn, ns(
            verification_request_id=req_id, student_id=s["student_id"],
            company_id=s["company_id"], document_type=None,
            document_description="Extra", is_required=1))
        assert is_error(r)
        assert r["message"] == ("verification_request_id, student_id, "
                                "company_id, and document_type are required")
        assert _snapshot(conn) == before
        assert _doc_count(conn, req_id) == 3

    def test_optional_flag_zero_is_stored_as_required(self, env):
        # KNOWN BEHAVIOUR (not fixed): the handler computes
        # ``int(getattr(args, 'is_required', 1) or 1)``, so an explicit 0 is
        # coerced back to 1 and an optional document cannot be recorded.
        s, conn = env, env["conn"]
        req_id = _v1_request(s)
        r = call_action(FA_ACTIONS["finaid-add-verification-document"], conn, ns(
            verification_request_id=req_id, student_id=s["student_id"],
            company_id=s["company_id"], document_type="other",
            document_description="Optional note", is_required=0))
        assert is_ok(r), r
        assert conn.execute(
            "SELECT is_required FROM finaid_verification_document "
            "WHERE id = ?", (r["id"],)).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# finaid-add-work-study-job — stored row
# ---------------------------------------------------------------------------

class TestAddWorkStudyJobDepth:
    def test_writes_open_job_with_exact_pay(self, env):
        s, conn = env, env["conn"]
        r = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            job_title="Library Assistant", department_id=None,
            supervisor_id=None, job_type="on_campus", pay_rate="12.50",
            hours_per_week="15", total_positions=3,
            description="Shelving books"))
        assert is_ok(r), r
        # The response lib moves the job's own status under document_status
        # so the envelope status stays "ok".
        assert r["document_status"] == "open"
        row = conn.execute(
            "SELECT job_title, department_id, supervisor_id, job_type, "
            "description, pay_rate, hours_per_week, total_positions, "
            "filled_positions, aid_year_id, status, company_id "
            "FROM finaid_work_study_job WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == ("Library Assistant", "", "", "on_campus",
                              "Shelving books", "12.50", "15", 3, 0,
                              s["aid_year_id"], "open", s["company_id"])
        audit_rows = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ?", (r["id"],)).fetchall()
        assert [tuple(a) for a in audit_rows] == [
            ("finaid-educlaw-finaid", "finaid-add-work-study-job",
             "finaid_work_study_job", r["id"])]
        # No ledger legs: a job posting plus one audit row, never journals.

    def test_refuses_a_missing_title_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            job_title=None, department_id=None, supervisor_id=None,
            job_type="on_campus", pay_rate="12.50", hours_per_week="15",
            total_positions=3, description=None))
        assert is_error(r)
        assert r["message"] == "--job-title is required"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_work_study_job") == 0
