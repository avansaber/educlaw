"""Behaviour of the twelve read-only finaid lookup actions, read back from the database.

The contract suite (testing/integration/contract/test_educlaw_finaid_contract.py)
only proves these actions are routable ("Unknown action" is absent). A routed
action can still return a perfectly shaped response for the wrong row, so each
action below gets a behavioural test: the test builds the underlying records
through the owning create actions, calls the get action, then reads the stored
rows back with PyPika queries and compares exact values, including money as
exact Decimal strings. Because every action here is a read, each happy-path
test also snapshots the relevant tables before the call and asserts the
snapshot is identical afterwards: what should NOT have changed is the whole
database. None of these twelve actions posts to the general ledger, so no
debit/credit legs are asserted; each test says so where the assertion would
otherwise be expected.

Refusal tests prove the input validation is truthful (exact messages) and that
a refused call leaves the database byte-identical: a refusal that half-writes
is worse than no refusal.

One action is broken and deliberately not fixed (see the DEFECT test):
finaid-get-work-study-earnings-summary raises TypeError as soon as one approved
timesheet exists on an on_campus or off_campus_community job, because the
community-hours aggregate comes back as a float and to_decimal(float) refuses
it. The defect test pins that crash; the happy-path test covers the paths that
work (no timesheets, pending-only timesheets, approved off_campus_other
timesheets).

All dates are passed explicitly, so nothing here depends on today's date.
"""
import importlib.util
import os
from decimal import Decimal

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

from erpclaw_lib.query import Q, P, Table, Field

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
        "conn": conn, "company_id": cid, "student_id": sid,
        "aid_year_id": aid_yr, "term_id": tid,
        "program_enrollment_id": peid, "isir_id": isir_id,
        "cost_of_attendance_id": coa_id,
    }
    conn.close()


def _row(conn, table_name, row_id):
    table = Table(table_name)
    query = Q.from_(table).select(table.star).where(Field("id") == P())
    return conn.execute(query.get_sql(), (row_id,)).fetchone()


def _child_rows(conn, table_name, column, value, order="id"):
    table = Table(table_name)
    query = (Q.from_(table).select(table.star)
             .where(Field(column) == P()).orderby(Field(order)))
    return conn.execute(query.get_sql(), (value,)).fetchall()


def _snapshot(conn, tables):
    snap = {}
    for name in tables:
        table = Table(name)
        query = Q.from_(table).select(table.star).orderby(table.id)
        snap[name] = [tuple(row) for row in conn.execute(query.get_sql()).fetchall()]
    return snap


def _package(s):
    result = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"],
        isir_id=s["isir_id"], cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", packaged_by="counselor", notes=None))
    assert is_ok(result), result
    return result["id"]


def _award(s, package_id, aid_type, offered, aid_year_id=None):
    result = call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=package_id, student_id=s["student_id"],
        aid_year_id=aid_year_id or s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None, notes=None))
    assert is_ok(result), result
    return result["id"]


def _loan(s, award_id, loan_type="subsidized", amount="3500.00",
          first="1750.00", second="1750.00", fee="29.05", rate="6.53",
          entrance_required=1, aid_year_id=None):
    result = call_action(LOAN_ACTIONS["finaid-add-loan"], s["conn"], ns(
        company_id=s["company_id"], student_id=s["student_id"],
        aid_year_id=aid_year_id or s["aid_year_id"], award_id=award_id,
        loan_type=loan_type,
        loan_period_start="2025-08-25", loan_period_end="2026-05-15",
        loan_amount=amount, first_disbursement_amount=first,
        second_disbursement_amount=second,
        origination_fee=fee, interest_rate=rate,
        borrower_id=s["student_id"], borrower_type="student",
        cod_loan_id=None, mpn_signed_date=None,
        entrance_counseling_required=entrance_required,
        entrance_counseling_date=None,
        exit_counseling_required=0, exit_counseling_date=None))
    assert is_ok(result), result
    return result["id"]


def _second_aid_year_loan(s):
    year = call_action(FA_ACTIONS["finaid-add-aid-year"], s["conn"], ns(
        company_id=s["company_id"], aid_year_code="2024-2025",
        description="Prior aid year", start_date="2024-07-01",
        end_date="2025-06-30", pell_max_award="7395"))
    assert is_ok(year), year
    isir = call_action(FA_ACTIONS["finaid-import-isir"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=year["id"],
        company_id=s["company_id"], transaction_number=1,
        receipt_date="2024-03-01", sai="2000"))
    assert is_ok(isir), isir
    coa = call_action(FA_ACTIONS["finaid-add-cost-of-attendance"], s["conn"], ns(
        aid_year_id=year["id"], company_id=s["company_id"],
        enrollment_status="full_time", living_arrangement="on_campus",
        tuition_fees="15000", books_supplies="1200", room_board="10000",
        transportation="1500", personal_expenses="2000", loan_fees="100"))
    assert is_ok(coa), coa
    package = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=year["id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"],
        isir_id=isir["id"], cost_of_attendance_id=coa["id"],
        enrollment_status="full_time", packaged_by="counselor", notes=None))
    assert is_ok(package), package
    award = _award(s, package["id"], "subsidized_loan", "1000.00",
                   aid_year_id=year["id"])
    return _loan(s, award, amount="1000.00", first="500.00", second="500.00",
                 fee="9.68", entrance_required=0, aid_year_id=year["id"])


def _schol_program(s):
    result = call_action(SCHOL_ACTIONS["finaid-add-scholarship-program"], s["conn"], ns(
        company_id=s["company_id"], name="Merit Grant", code="MERIT-2025",
        scholarship_type="merit", funding_source="endowment",
        award_method="application_required", award_amount_type="fixed",
        award_amount="2000", min_award="500", max_award="2000",
        annual_budget="50000", max_recipients=10, renewal_eligible=0,
        renewal_gpa_minimum="3.0", renewal_credits_minimum="12",
        eligibility_criteria="{}", application_deadline="2025-06-01",
        award_period="annual", applies_to_aid_type="institutional_scholarship",
        description=None, gl_account_id=None, user_id=None))
    assert is_ok(result), result
    return result["id"]


def _schol_application(s, program_id):
    result = call_action(SCHOL_ACTIONS["finaid-submit-scholarship-application"], s["conn"], ns(
        scholarship_program_id=program_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        essay_response="Community service essay", gpa_at_application="3.5",
        submission_date="2025-05-01", user_id=None))
    assert is_ok(result), result
    return result["id"]


def _verification(s):
    result = call_action(FA_ACTIONS["finaid-create-verification-request"], s["conn"], ns(
        isir_id=s["isir_id"], student_id=s["student_id"],
        company_id=s["company_id"], verification_group="V1",
        requested_date="2025-04-01", deadline_date="2025-05-01",
        assigned_to="counselor"))
    assert is_ok(result), result
    return result["id"]


def _sap_evaluation(s):
    result = call_action(FA_ACTIONS["finaid-generate-sap-evaluation"], s["conn"], ns(
        student_id=s["student_id"], academic_term_id=s["term_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        gpa_earned="1.2", gpa_threshold="2.00",
        credits_attempted="12", credits_completed="3",
        completion_threshold="0.67", max_timeframe_credits="180",
        projected_credits_remaining="100",
        transfer_credits_attempted="0", transfer_credits_completed="0",
        evaluation_date="2025-12-20", evaluated_by="system",
        evaluation_type="automatic"))
    assert is_ok(result), result
    return result["id"]


def _sap_appeal(s, evaluation_id):
    result = call_action(FA_ACTIONS["finaid-submit-sap-appeal"], s["conn"], ns(
        sap_evaluation_id=evaluation_id, student_id=s["student_id"],
        company_id=s["company_id"], appeal_reason="illness",
        reason_narrative="hospital stay", academic_plan="repeat courses",
        supporting_documents="[]", submitted_date="2025-12-21"))
    assert is_ok(result), result
    return result["id"]


def _r2t4(s, package_id):
    result = call_action(FA_ACTIONS["finaid-create-r2t4"], s["conn"], ns(
        student_id=s["student_id"], academic_term_id=s["term_id"],
        award_package_id=package_id, company_id=s["company_id"],
        withdrawal_type="official", withdrawal_date="2025-10-01",
        last_date_of_attendance="2025-10-01", determination_date="2025-10-05",
        payment_period_start="2025-08-25", payment_period_end="2025-12-20",
        payment_period_days=117))
    assert is_ok(result), result
    return result["id"]


def _pj(s, package_id):
    result = call_action(FA_ACTIONS["finaid-add-professional-judgment"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        company_id=s["company_id"], pj_type="dependency_override",
        pj_reason="job_loss", reason_narrative="parent job loss",
        data_element_changed="dependency", original_value="dependent",
        adjusted_value="independent", effective_date="2025-08-01",
        authorized_by="director", authorization_date="2025-08-02",
        supervisor_review_required=0, award_package_id=package_id,
        supporting_documents="[]"))
    assert is_ok(result), result
    return result["id"]


def _ws_job(s, title="Library Assistant", job_type="on_campus"):
    result = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
        company_id=s["company_id"], aid_year_id=s["aid_year_id"],
        job_title=title, department_id=None, supervisor_id=None,
        job_type=job_type, pay_rate="12.00", hours_per_week="15",
        total_positions=3, description=None))
    assert is_ok(result), result
    return result["id"]


def _fws_award(s, package_id, offered="4000.00"):
    return _award(s, package_id, "fws", offered)


def _ws_assignment(s, job_id, award_id, limit="4000"):
    result = call_action(WS_ACTIONS["finaid-assign-student-to-job"], s["conn"], ns(
        student_id=s["student_id"], award_id=award_id, job_id=job_id,
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-08-25",
        end_date="2025-12-20", award_limit=limit))
    assert is_ok(result), result
    return result["id"]


def _timesheet(s, assignment_id, start="2025-09-01", end="2025-09-14",
               hours="20", submitted="2025-09-15"):
    result = call_action(WS_ACTIONS["finaid-submit-work-study-timesheet"], s["conn"], ns(
        assignment_id=assignment_id, student_id=s["student_id"],
        company_id=s["company_id"], pay_period_start=start,
        pay_period_end=end, hours_worked=hours, submission_date=submitted))
    assert is_ok(result), result
    return result["id"]


def _approve_timesheet(s, timesheet_id):
    result = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], s["conn"], ns(
        id=timesheet_id, supervisor_approved_by="supervisor-1"))
    assert is_ok(result), result
    return result


READ_TABLES = {
    "finaid-get-loan": ["finaid_loan", "finaid_award", "finaid_award_package", "audit_log"],
    "finaid-get-loan-limits-status": ["finaid_loan", "audit_log"],
    "finaid-get-professional-judgment": ["finaid_professional_judgment", "audit_log"],
    "finaid-get-r2t4": ["finaid_r2t4_calculation", "audit_log"],
    "finaid-get-sap-appeal": ["finaid_sap_appeal", "finaid_sap_evaluation", "audit_log"],
    "finaid-get-sap-evaluation": ["finaid_sap_evaluation", "audit_log"],
    "finaid-get-scholarship-application": ["finaid_scholarship_application", "finaid_scholarship_program", "audit_log"],
    "finaid-get-scholarship-program": ["finaid_scholarship_program", "audit_log"],
    "finaid-get-verification-request": ["finaid_verification_request", "finaid_verification_document", "audit_log"],
    "finaid-get-work-study-assignment": ["finaid_work_study_assignment", "finaid_work_study_timesheet", "finaid_work_study_job", "audit_log"],
    "finaid-get-work-study-earnings-summary": ["finaid_work_study_assignment", "finaid_work_study_timesheet", "finaid_work_study_job", "audit_log"],
    "finaid-get-work-study-job": ["finaid_work_study_job", "finaid_work_study_assignment", "audit_log"],
}


# ---------------------------------------------------------------------------
# finaid-get-loan — stored-row read
# ---------------------------------------------------------------------------

def test_get_loan_returns_exact_stored_row(env):
    # No ledger effect: finaid-get-loan is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    loan_id = _loan(env, _award(env, _package(env), "subsidized_loan", "3500.00"))
    before = _snapshot(conn, READ_TABLES["finaid-get-loan"])
    result = call_action(LOAN_ACTIONS["finaid-get-loan"], conn, ns(id=loan_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_loan", loan_id)
    assert result["id"] == row["id"] == loan_id
    assert result["loan_amount"] == row["loan_amount"] == "3500.00"
    assert Decimal(result["loan_amount"]) == Decimal("3500.00")
    assert result["first_disbursement_amount"] == row["first_disbursement_amount"] == "1750.00"
    assert result["second_disbursement_amount"] == row["second_disbursement_amount"] == "1750.00"
    assert result["origination_fee"] == row["origination_fee"] == "29.05"
    assert result["interest_rate"] == row["interest_rate"] == "6.53"
    assert result["loan_type"] == row["loan_type"] == "subsidized"
    assert result["award_id"] == row["award_id"]
    assert result["borrower_id"] == row["borrower_id"] == env["student_id"]
    assert result["document_status"] == row["status"] == "originated"
    assert result["status"] == "ok"
    assert _snapshot(conn, READ_TABLES["finaid-get-loan"]) == before


def test_get_loan_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    loan_id = _loan(env, _award(env, _package(env), "subsidized_loan", "3500.00"))
    before = _snapshot(conn, READ_TABLES["finaid-get-loan"])
    missing = call_action(LOAN_ACTIONS["finaid-get-loan"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "Missing required field: id"
    unknown = call_action(LOAN_ACTIONS["finaid-get-loan"], conn, ns(id="no-such-loan"))
    assert is_error(unknown)
    assert unknown["message"] == "Loan not found: no-such-loan"
    assert _row(conn, "finaid_loan", loan_id)["loan_amount"] == "3500.00"
    assert _snapshot(conn, READ_TABLES["finaid-get-loan"]) == before


# ---------------------------------------------------------------------------
# finaid-get-loan-limits-status — computed aggregate over stored rows
# ---------------------------------------------------------------------------

def test_get_loan_limits_status_totals_match_stored_loans(env):
    # No ledger effect: this action only sums finaid_loan rows; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    package_id = _package(env)
    _loan(env, _award(env, package_id, "subsidized_loan", "3500.00"))
    _loan(env, _award(env, package_id, "unsubsidized_loan", "2000.00"),
          loan_type="unsubsidized", amount="2000.00", first="1000.00",
          second="1000.00", fee="9.68")
    _second_aid_year_loan(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-loan-limits-status"])
    result = call_action(LOAN_ACTIONS["finaid-get-loan-limits-status"], conn, ns(
        student_id=env["student_id"], aid_year_id=env["aid_year_id"],
        company_id=env["company_id"]))
    assert is_ok(result), result
    assert result["current_year_total"] == "5500.00"
    assert Decimal(result["current_year_total"]) == Decimal("5500.00")
    assert result["current_year_subsidized"] == "3500.00"
    assert Decimal(result["current_year_subsidized"]) == Decimal("3500.00")
    assert result["aggregate_total"] == "6500.00"
    assert Decimal(result["aggregate_total"]) == Decimal("6500.00")
    assert result["aggregate_subsidized"] == "4500.00"
    assert Decimal(result["aggregate_subsidized"]) == Decimal("4500.00")
    assert result["annual_limit_dependent"] == "7500.00"
    assert result["annual_limit_independent"] == "12500.00"
    assert result["aggregate_limit_dependent"] == "31000.00"
    assert result["aggregate_limit_independent"] == "57500.00"
    assert len(result["loans"]) == 2
    assert sorted(loan["loan_amount"] for loan in result["loans"]) == ["2000.00", "3500.00"]
    current_rows = _child_rows(conn, "finaid_loan", "aid_year_id", env["aid_year_id"])
    recomputed = sum((Decimal(dict(stored)["loan_amount"]) for stored in current_rows), Decimal("0"))
    assert recomputed == Decimal("5500.00")
    assert _snapshot(conn, READ_TABLES["finaid-get-loan-limits-status"]) == before


def test_get_loan_limits_status_refuses_missing_student_without_writing(env):
    conn = env["conn"]
    _loan(env, _award(env, _package(env), "subsidized_loan", "3500.00"))
    before = _snapshot(conn, READ_TABLES["finaid-get-loan-limits-status"])
    refused = call_action(LOAN_ACTIONS["finaid-get-loan-limits-status"], conn, ns(
        student_id=None, aid_year_id=env["aid_year_id"],
        company_id=env["company_id"]))
    assert is_error(refused)
    assert refused["message"] == "Missing required field: student_id"
    assert _snapshot(conn, READ_TABLES["finaid-get-loan-limits-status"]) == before


# ---------------------------------------------------------------------------
# finaid-get-professional-judgment — stored-row read
# ---------------------------------------------------------------------------

def test_get_professional_judgment_returns_exact_stored_row(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    judgment_id = _pj(env, _package(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-professional-judgment"])
    result = call_action(FA_ACTIONS["finaid-get-professional-judgment"], conn, ns(id=judgment_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_professional_judgment", judgment_id)
    assert result["id"] == row["id"] == judgment_id
    assert result["pj_type"] == row["pj_type"] == "dependency_override"
    assert result["pj_reason"] == row["pj_reason"] == "job_loss"
    assert result["reason_narrative"] == row["reason_narrative"] == "parent job loss"
    assert result["data_element_changed"] == row["data_element_changed"] == "dependency"
    assert result["original_value"] == row["original_value"] == "dependent"
    assert result["adjusted_value"] == row["adjusted_value"] == "independent"
    assert result["effective_date"] == row["effective_date"] == "2025-08-01"
    assert result["authorized_by"] == row["authorized_by"] == "director"
    assert result["student_id"] == row["student_id"] == env["student_id"]
    assert result["status"] == "ok"
    assert "document_status" not in result
    assert _snapshot(conn, READ_TABLES["finaid-get-professional-judgment"]) == before


def test_get_professional_judgment_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    judgment_id = _pj(env, _package(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-professional-judgment"])
    missing = call_action(FA_ACTIONS["finaid-get-professional-judgment"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "id is required"
    unknown = call_action(FA_ACTIONS["finaid-get-professional-judgment"], conn, ns(id="no-such-judgment"))
    assert is_error(unknown)
    assert unknown["message"] == "Professional judgment not found"
    assert _row(conn, "finaid_professional_judgment", judgment_id)["pj_type"] == "dependency_override"
    assert _snapshot(conn, READ_TABLES["finaid-get-professional-judgment"]) == before


# ---------------------------------------------------------------------------
# finaid-get-r2t4 — stored-row read
# ---------------------------------------------------------------------------

def test_get_r2t4_returns_exact_stored_row(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    calc_id = _r2t4(env, _package(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-r2t4"])
    result = call_action(FA_ACTIONS["finaid-get-r2t4"], conn, ns(id=calc_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_r2t4_calculation", calc_id)
    assert result["id"] == row["id"] == calc_id
    assert result["withdrawal_type"] == row["withdrawal_type"] == "official"
    assert result["withdrawal_date"] == row["withdrawal_date"] == "2025-10-01"
    assert result["last_date_of_attendance"] == row["last_date_of_attendance"] == "2025-10-01"
    assert result["determination_date"] == row["determination_date"] == "2025-10-05"
    assert result["payment_period_start"] == row["payment_period_start"] == "2025-08-25"
    assert result["payment_period_end"] == row["payment_period_end"] == "2025-12-20"
    assert result["payment_period_days"] == row["payment_period_days"] == 117
    assert result["institution_return_due_date"] == row["institution_return_due_date"] == "2025-11-19"
    assert result["student_id"] == row["student_id"] == env["student_id"]
    assert result["document_status"] == row["status"] == "calculated"
    assert result["status"] == "ok"
    assert _snapshot(conn, READ_TABLES["finaid-get-r2t4"]) == before


def test_get_r2t4_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    calc_id = _r2t4(env, _package(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-r2t4"])
    missing = call_action(FA_ACTIONS["finaid-get-r2t4"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "id or r2t4_id is required"
    unknown = call_action(FA_ACTIONS["finaid-get-r2t4"], conn, ns(id="no-such-r2t4"))
    assert is_error(unknown)
    assert unknown["message"] == "R2T4 calculation not found"
    assert _row(conn, "finaid_r2t4_calculation", calc_id)["withdrawal_type"] == "official"
    assert _snapshot(conn, READ_TABLES["finaid-get-r2t4"]) == before


# ---------------------------------------------------------------------------
# finaid-get-sap-appeal — stored-row read
# ---------------------------------------------------------------------------

def test_get_sap_appeal_returns_exact_stored_row(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    appeal_id = _sap_appeal(env, _sap_evaluation(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-sap-appeal"])
    result = call_action(FA_ACTIONS["finaid-get-sap-appeal"], conn, ns(id=appeal_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_sap_appeal", appeal_id)
    assert result["id"] == row["id"] == appeal_id
    assert result["sap_evaluation_id"] == row["sap_evaluation_id"]
    assert result["appeal_reason"] == row["appeal_reason"] == "illness"
    assert result["reason_narrative"] == row["reason_narrative"] == "hospital stay"
    assert result["academic_plan"] == row["academic_plan"] == "repeat courses"
    assert result["submitted_date"] == row["submitted_date"] == "2025-12-21"
    assert result["student_id"] == row["student_id"] == env["student_id"]
    assert result["document_status"] == row["status"] == "submitted"
    assert result["status"] == "ok"
    assert _snapshot(conn, READ_TABLES["finaid-get-sap-appeal"]) == before


def test_get_sap_appeal_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    appeal_id = _sap_appeal(env, _sap_evaluation(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-sap-appeal"])
    missing = call_action(FA_ACTIONS["finaid-get-sap-appeal"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "id is required"
    unknown = call_action(FA_ACTIONS["finaid-get-sap-appeal"], conn, ns(id="no-such-appeal"))
    assert is_error(unknown)
    assert unknown["message"] == "SAP appeal not found"
    assert _row(conn, "finaid_sap_appeal", appeal_id)["appeal_reason"] == "illness"
    assert _snapshot(conn, READ_TABLES["finaid-get-sap-appeal"]) == before


# ---------------------------------------------------------------------------
# finaid-get-sap-evaluation — stored-row read
# ---------------------------------------------------------------------------

def test_get_sap_evaluation_returns_exact_stored_row(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    evaluation_id = _sap_evaluation(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-sap-evaluation"])
    result = call_action(FA_ACTIONS["finaid-get-sap-evaluation"], conn, ns(id=evaluation_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_sap_evaluation", evaluation_id)
    assert result["id"] == row["id"] == evaluation_id
    assert result["sap_status"] == row["sap_status"] == "FSP"
    assert result["completion_rate"] == row["completion_rate"] == "0.25"
    assert result["gpa_earned"] == row["gpa_earned"] == "1.20"
    assert result["gpa_threshold"] == row["gpa_threshold"] == "2.00"
    assert result["credits_attempted"] == row["credits_attempted"] == "12.00"
    assert result["credits_completed"] == row["credits_completed"] == "3.00"
    assert result["evaluation_date"] == row["evaluation_date"] == "2025-12-20"
    assert result["student_id"] == row["student_id"] == env["student_id"]
    assert result["status"] == "ok"
    assert "document_status" not in result
    assert _snapshot(conn, READ_TABLES["finaid-get-sap-evaluation"]) == before


def test_get_sap_evaluation_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    evaluation_id = _sap_evaluation(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-sap-evaluation"])
    missing = call_action(FA_ACTIONS["finaid-get-sap-evaluation"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "id is required"
    unknown = call_action(FA_ACTIONS["finaid-get-sap-evaluation"], conn, ns(id="no-such-evaluation"))
    assert is_error(unknown)
    assert unknown["message"] == "SAP evaluation not found"
    assert _row(conn, "finaid_sap_evaluation", evaluation_id)["sap_status"] == "FSP"
    assert _snapshot(conn, READ_TABLES["finaid-get-sap-evaluation"]) == before


# ---------------------------------------------------------------------------
# finaid-get-scholarship-application — stored-row read
# ---------------------------------------------------------------------------

def test_get_scholarship_application_returns_exact_stored_row(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    application_id = _schol_application(env, _schol_program(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-scholarship-application"])
    result = call_action(SCHOL_ACTIONS["finaid-get-scholarship-application"], conn, ns(id=application_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_scholarship_application", application_id)
    assert result["id"] == row["id"] == application_id
    assert result["scholarship_program_id"] == row["scholarship_program_id"]
    assert result["gpa_at_application"] == row["gpa_at_application"] == "3.5"
    assert Decimal(result["gpa_at_application"]) == Decimal("3.5")
    assert result["essay_response"] == row["essay_response"] == "Community service essay"
    assert result["submission_date"] == row["submission_date"] == "2025-05-01"
    assert result["award_amount"] == row["award_amount"] == "0"
    assert result["student_id"] == row["student_id"] == env["student_id"]
    assert result["document_status"] == row["status"] == "submitted"
    assert result["status"] == "ok"
    assert _snapshot(conn, READ_TABLES["finaid-get-scholarship-application"]) == before


def test_get_scholarship_application_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    application_id = _schol_application(env, _schol_program(env))
    before = _snapshot(conn, READ_TABLES["finaid-get-scholarship-application"])
    missing = call_action(SCHOL_ACTIONS["finaid-get-scholarship-application"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "--id is required"
    unknown = call_action(SCHOL_ACTIONS["finaid-get-scholarship-application"], conn, ns(id="no-such-application"))
    assert is_error(unknown)
    assert unknown["message"] == "Scholarship application no-such-application not found"
    assert _row(conn, "finaid_scholarship_application", application_id)["gpa_at_application"] == "3.5"
    assert _snapshot(conn, READ_TABLES["finaid-get-scholarship-application"]) == before


# ---------------------------------------------------------------------------
# finaid-get-scholarship-program — stored-row read
# ---------------------------------------------------------------------------

def test_get_scholarship_program_returns_exact_stored_row(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    program_id = _schol_program(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-scholarship-program"])
    result = call_action(SCHOL_ACTIONS["finaid-get-scholarship-program"], conn, ns(id=program_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_scholarship_program", program_id)
    assert result["id"] == row["id"] == program_id
    assert result["name"] == row["name"] == "Merit Grant"
    assert result["code"] == row["code"] == "MERIT-2025"
    assert result["award_amount"] == row["award_amount"] == "2000.00"
    assert Decimal(result["award_amount"]) == Decimal("2000.00")
    assert result["min_award"] == row["min_award"] == "500.00"
    assert result["max_award"] == row["max_award"] == "2000.00"
    assert result["annual_budget"] == row["annual_budget"] == "50000.00"
    assert result["budget_remaining"] == row["budget_remaining"] == "50000.00"
    assert Decimal(result["budget_remaining"]) == Decimal("50000.00")
    assert result["max_recipients"] == row["max_recipients"] == 10
    assert result["is_active"] == row["is_active"] == 1
    assert result["status"] == "ok"
    assert "document_status" not in result
    assert _snapshot(conn, READ_TABLES["finaid-get-scholarship-program"]) == before


def test_get_scholarship_program_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    program_id = _schol_program(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-scholarship-program"])
    missing = call_action(SCHOL_ACTIONS["finaid-get-scholarship-program"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "--id is required"
    unknown = call_action(SCHOL_ACTIONS["finaid-get-scholarship-program"], conn, ns(id="no-such-program"))
    assert is_error(unknown)
    assert unknown["message"] == "Scholarship program no-such-program not found"
    assert _row(conn, "finaid_scholarship_program", program_id)["award_amount"] == "2000.00"
    assert _snapshot(conn, READ_TABLES["finaid-get-scholarship-program"]) == before


# ---------------------------------------------------------------------------
# finaid-get-verification-request — stored-row read with child rows
# ---------------------------------------------------------------------------

def test_get_verification_request_returns_request_with_documents(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    request_id = _verification(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-verification-request"])
    result = call_action(FA_ACTIONS["finaid-get-verification-request"], conn, ns(id=request_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_verification_request", request_id)
    assert result["id"] == row["id"] == request_id
    assert result["verification_group"] == row["verification_group"] == "V1"
    assert result["requested_date"] == row["requested_date"] == "2025-04-01"
    assert result["deadline_date"] == row["deadline_date"] == "2025-05-01"
    assert result["assigned_to"] == row["assigned_to"] == "counselor"
    assert result["isir_id"] == row["isir_id"] == env["isir_id"]
    assert result["student_id"] == row["student_id"] == env["student_id"]
    assert result["document_status"] == row["status"] == "initiated"
    assert result["status"] == "ok"
    stored_docs = _child_rows(conn, "finaid_verification_document",
                              "verification_request_id", request_id,
                              order="document_type")
    assert len(stored_docs) == 3
    assert len(result["documents"]) == 3
    assert sorted(doc["document_type"] for doc in result["documents"]) == [
        "household_verification", "tax_transcript", "w2"]
    for stored in stored_docs:
        stored = dict(stored)
        match = [doc for doc in result["documents"] if doc["id"] == stored["id"]]
        assert len(match) == 1
        assert match[0]["document_type"] == stored["document_type"]
        assert match[0]["submission_status"] == stored["submission_status"] == "not_submitted"
        assert match[0]["verification_request_id"] == request_id
    assert _snapshot(conn, READ_TABLES["finaid-get-verification-request"]) == before


def test_get_verification_request_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    request_id = _verification(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-verification-request"])
    missing = call_action(FA_ACTIONS["finaid-get-verification-request"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "verification_request_id or id is required"
    unknown = call_action(FA_ACTIONS["finaid-get-verification-request"], conn, ns(id="no-such-request"))
    assert is_error(unknown)
    assert unknown["message"] == "Verification request not found"
    assert _row(conn, "finaid_verification_request", request_id)["verification_group"] == "V1"
    assert len(_child_rows(conn, "finaid_verification_document",
                           "verification_request_id", request_id)) == 3
    assert _snapshot(conn, READ_TABLES["finaid-get-verification-request"]) == before


# ---------------------------------------------------------------------------
# finaid-get-work-study-assignment — stored row plus computed earnings
# ---------------------------------------------------------------------------

def test_get_work_study_assignment_returns_row_and_approved_earnings(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    package_id = _package(env)
    assignment_id = _ws_assignment(env, _ws_job(env), _fws_award(env, package_id))
    timesheet_id = _timesheet(env, assignment_id)
    _approve_timesheet(env, timesheet_id)
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-assignment"])
    result = call_action(WS_ACTIONS["finaid-get-work-study-assignment"], conn, ns(id=assignment_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_work_study_assignment", assignment_id)
    assert result["id"] == row["id"] == assignment_id
    assert result["award_limit"] == row["award_limit"] == "4000"
    assert Decimal(result["award_limit"]) == Decimal("4000")
    assert result["earned_to_date"] == row["earned_to_date"] == "240.00"
    assert Decimal(result["earned_to_date"]) == Decimal("240.00")
    assert result["start_date"] == row["start_date"] == "2025-08-25"
    assert result["end_date"] == row["end_date"] == "2025-12-20"
    assert result["approved_earnings_sum"] == "240.00"
    assert Decimal(result["approved_earnings_sum"]) == Decimal("240.00")
    assert result["document_status"] == row["status"] == "active"
    assert result["status"] == "ok"
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-assignment"]) == before


def test_get_work_study_assignment_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    package_id = _package(env)
    assignment_id = _ws_assignment(env, _ws_job(env), _fws_award(env, package_id))
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-assignment"])
    missing = call_action(WS_ACTIONS["finaid-get-work-study-assignment"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "--id is required"
    unknown = call_action(WS_ACTIONS["finaid-get-work-study-assignment"], conn, ns(id="no-such-assignment"))
    assert is_error(unknown)
    assert unknown["message"] == "Work study assignment no-such-assignment not found"
    assert _row(conn, "finaid_work_study_assignment", assignment_id)["award_limit"] == "4000"
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-assignment"]) == before


# ---------------------------------------------------------------------------
# finaid-get-work-study-earnings-summary — computed aggregate over stored rows
# ---------------------------------------------------------------------------

def test_get_work_study_earnings_summary_ignores_pending_timesheets(env):
    # No ledger effect: this action only aggregates timesheet rows; it posts no
    # GL entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    package_id = _package(env)
    _ws_assignment(env, _ws_job(env), _fws_award(env, package_id))
    assignment_id = _child_rows(conn, "finaid_work_study_assignment",
                                "student_id", env["student_id"])[0]["id"]
    _timesheet(env, assignment_id)
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-earnings-summary"])
    result = call_action(WS_ACTIONS["finaid-get-work-study-earnings-summary"], conn, ns(
        student_id=env["student_id"], aid_year_id=env["aid_year_id"],
        company_id=env["company_id"]))
    assert is_ok(result), result
    assert result["award_limit"] == "4000.00"
    assert Decimal(result["award_limit"]) == Decimal("4000.00")
    assert result["earned_to_date"] == "0.00"
    assert Decimal(result["earned_to_date"]) == Decimal("0")
    assert result["remaining_limit"] == "4000.00"
    assert Decimal(result["remaining_limit"]) == Decimal("4000.00")
    assert result["community_service_hours"] == "0"
    assert Decimal(result["community_service_hours"]) == Decimal("0")
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-earnings-summary"]) == before


def test_get_work_study_earnings_summary_unknown_student_returns_zeroed_summary(env):
    # No ledger effect: see the pending-timesheets test above.
    conn = env["conn"]
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-earnings-summary"])
    result = call_action(WS_ACTIONS["finaid-get-work-study-earnings-summary"], conn, ns(
        student_id="no-such-student", aid_year_id=env["aid_year_id"],
        company_id=env["company_id"]))
    assert is_ok(result), result
    assert result["award_limit"] == "0.00"
    assert result["earned_to_date"] == "0.00"
    assert result["remaining_limit"] == "0.00"
    assert result["community_service_hours"] == "0"
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-earnings-summary"]) == before


def test_get_work_study_earnings_summary_defect_crashes_on_approved_community_hours(env):
    """DEFECT, deliberately not fixed: with one approved timesheet on an
    on_campus job the action raises ``TypeError: Cannot convert float 20.0 to
    Decimal`` instead of returning a summary. The community-hours aggregate
    comes back from SQLite as a float and ``to_decimal`` refuses floats. This
    test pins the crash so a future fix is visible as a test failure here."""
    conn = env["conn"]
    package_id = _package(env)
    assignment_id = _ws_assignment(env, _ws_job(env), _fws_award(env, package_id))
    _approve_timesheet(env, _timesheet(env, assignment_id))
    with pytest.raises(TypeError, match="Cannot convert float"):
        call_action(WS_ACTIONS["finaid-get-work-study-earnings-summary"], conn, ns(
            student_id=env["student_id"], aid_year_id=env["aid_year_id"],
            company_id=env["company_id"]))


def test_get_work_study_earnings_summary_refuses_missing_student_without_writing(env):
    conn = env["conn"]
    package_id = _package(env)
    _ws_assignment(env, _ws_job(env), _fws_award(env, package_id))
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-earnings-summary"])
    refused = call_action(WS_ACTIONS["finaid-get-work-study-earnings-summary"], conn, ns(
        student_id=None, aid_year_id=env["aid_year_id"],
        company_id=env["company_id"]))
    assert is_error(refused)
    assert refused["message"] == "--student-id is required"
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-earnings-summary"]) == before


# ---------------------------------------------------------------------------
# finaid-get-work-study-job — stored row plus computed assignment count
# ---------------------------------------------------------------------------

def test_get_work_study_job_returns_row_and_active_assignment_count(env):
    # No ledger effect: this action is a read-only lookup; it posts no GL
    # entries, so no debit/credit legs are asserted here.
    conn = env["conn"]
    package_id = _package(env)
    job_id = _ws_job(env)
    _ws_assignment(env, job_id, _fws_award(env, package_id))
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-job"])
    result = call_action(WS_ACTIONS["finaid-get-work-study-job"], conn, ns(id=job_id))
    assert is_ok(result), result
    row = _row(conn, "finaid_work_study_job", job_id)
    assert result["id"] == row["id"] == job_id
    assert result["job_title"] == row["job_title"] == "Library Assistant"
    assert result["job_type"] == row["job_type"] == "on_campus"
    assert result["pay_rate"] == row["pay_rate"] == "12.00"
    assert Decimal(result["pay_rate"]) == Decimal("12.00")
    assert result["hours_per_week"] == row["hours_per_week"] == "15"
    assert result["total_positions"] == row["total_positions"] == 3
    assert result["filled_positions"] == row["filled_positions"] == 1
    assert result["active_assignment_count"] == 1
    assert result["document_status"] == row["status"] == "open"
    assert result["status"] == "ok"
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-job"]) == before


def test_get_work_study_job_refuses_missing_and_unknown_id_without_writing(env):
    conn = env["conn"]
    job_id = _ws_job(env)
    before = _snapshot(conn, READ_TABLES["finaid-get-work-study-job"])
    missing = call_action(WS_ACTIONS["finaid-get-work-study-job"], conn, ns(id=None))
    assert is_error(missing)
    assert missing["message"] == "--id is required"
    unknown = call_action(WS_ACTIONS["finaid-get-work-study-job"], conn, ns(id="no-such-job"))
    assert is_error(unknown)
    assert unknown["message"] == "Work study job no-such-job not found"
    assert _row(conn, "finaid_work_study_job", job_id)["pay_rate"] == "12.00"
    assert _snapshot(conn, READ_TABLES["finaid-get-work-study-job"]) == before
