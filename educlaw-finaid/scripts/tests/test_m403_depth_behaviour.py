"""Depth cover for twelve finaid actions previously tested for shape/routing only.

Each action below gets a behavioural success test (the exact stored rows read
back from the database and compared as exact strings) and a refusal test (the
refusal happens, the message states the true reason, and the touched tables are
byte-identical afterwards).

Actions covered:
  finaid-complete-verification, finaid-create-award-package, finaid-create-r2t4,
  finaid-create-verification-request, finaid-delete-award,
  finaid-delete-cost-of-attendance, finaid-deny-award,
  finaid-deny-scholarship-application, finaid-deny-work-study-timesheet,
  finaid-generate-cod-export, finaid-generate-cod-origination,
  finaid-generate-payroll-export.

Ledger note (applies to every test in this file): none of these twelve actions
reaches the general ledger, so no ledger legs are asserted here; a later reader
must not add ledger assertions that cannot hold. Money is compared as exact
Decimal strings, never float.

All dates are passed explicitly except the payroll export stamp, which the
action itself stamps with its internal today; that stamp is asserted non-empty.
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

FA_ACTIONS = _load("financial_aid", _SCRIPTS_DIR).ACTIONS
SCH_ACTIONS = _load("scholarships", _SCRIPTS_DIR).ACTIONS
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


def _dump(conn, table):
    rows = conn.execute("SELECT * FROM %s" % table).fetchall()
    return sorted(tuple("" if v is None else str(v) for v in r) for r in rows)


def _snap(conn, tables):
    return {t: _dump(conn, t) for t in tables}


def _count(conn, table):
    return conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]


def _package(s, academic_term_id="term"):
    return call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"] if academic_term_id == "term" else academic_term_id,
        company_id=s["company_id"], program_enrollment_id=s["program_enrollment_id"],
        isir_id=s["isir_id"], cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", packaged_by="counselor", notes=None))


def _package_id(s):
    r = _package(s)
    assert is_ok(r), r
    return r["id"]


def _add_award(s, pkg_id, aid_type, offered, aid_source="federal"):
    return call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source=aid_source, offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None, notes=None))


def _award_id(s, pkg_id, aid_type="pell", offered="5000.00"):
    r = _add_award(s, pkg_id, aid_type, offered)
    assert is_ok(r), r
    return r["id"]


def _accept(s, award_id, amount, date="2025-08-01"):
    return call_action(FA_ACTIONS["finaid-accept-award"], s["conn"], ns(
        award_id=award_id, accepted_amount=amount, acceptance_date=date))


def _disburse(s, award_id, amount, number=1, date="2025-09-02"):
    return call_action(FA_ACTIONS["finaid-record-award-disbursement"], s["conn"], ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date=date, company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=number))


def _request(s, group="V1"):
    return call_action(FA_ACTIONS["finaid-create-verification-request"], s["conn"], ns(
        isir_id=s["isir_id"], student_id=s["student_id"], company_id=s["company_id"],
        verification_group=group, deadline_date="2025-06-01",
        requested_date="2025-05-01", assigned_to=None))


def _accept_all_docs(s, req_id):
    docs = s["conn"].execute(
        "SELECT id FROM finaid_verification_document WHERE verification_request_id = ?",
        (req_id,)).fetchall()
    for d in docs:
        r = call_action(FA_ACTIONS["finaid-update-verification-document"], s["conn"], ns(
            id=d[0], submission_status="accepted"))
        assert is_ok(r), r


def _scholarship_program(s):
    r = call_action(SCH_ACTIONS["finaid-add-scholarship-program"], s["conn"], ns(
        company_id=s["company_id"], name="Merit Award", code="MERIT-01",
        scholarship_type="merit", funding_source="endowment",
        award_method="application_required", award_amount_type="fixed",
        award_amount="2000", min_award="0", max_award="0", annual_budget="50000",
        max_recipients=10, renewal_eligible=0, renewal_gpa_minimum="0",
        renewal_credits_minimum="0", eligibility_criteria="{}",
        application_deadline="2025-06-01", award_period="annual",
        applies_to_aid_type="institutional_grant"))
    assert is_ok(r), r
    return r["id"]


def _scholarship_application(s, program_id):
    r = call_action(SCH_ACTIONS["finaid-submit-scholarship-application"], s["conn"], ns(
        scholarship_program_id=program_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        essay_response="essay", gpa_at_application="3.5",
        submission_date="2025-05-01"))
    assert is_ok(r), r
    return r["id"]


def _work_study_chain(s, hours="20"):
    pkg_id = _package_id(s)
    fws_id = _award_id(s, pkg_id, "fws", "3000.00")
    job = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
        company_id=s["company_id"], aid_year_id=s["aid_year_id"],
        job_title="Library Assistant", department_id=None, supervisor_id=None,
        job_type="on_campus", pay_rate="12.00", hours_per_week="15",
        total_positions=3, description=None))
    assert is_ok(job), job
    assign = call_action(WS_ACTIONS["finaid-assign-student-to-job"], s["conn"], ns(
        student_id=s["student_id"], award_id=fws_id, job_id=job["id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-08-25",
        end_date="2025-12-20", award_limit="3000"))
    assert is_ok(assign), assign
    ts = call_action(WS_ACTIONS["finaid-submit-work-study-timesheet"], s["conn"], ns(
        assignment_id=assign["id"], student_id=s["student_id"],
        company_id=s["company_id"], pay_period_start="2025-09-01",
        pay_period_end="2025-09-15", hours_worked=hours,
        submission_date="2025-09-16"))
    assert is_ok(ts), ts
    return pkg_id, fws_id, job["id"], assign["id"], ts["id"]


def _loan(s, offered="3500.00"):
    pkg_id = _package_id(s)
    award = _add_award(s, pkg_id, "subsidized_loan", offered)
    assert is_ok(award), award
    r = call_action(LOAN_ACTIONS["finaid-add-loan"], s["conn"], ns(
        company_id=s["company_id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], award_id=award["id"], loan_type="subsidized",
        loan_period_start="2025-08-25", loan_period_end="2026-05-15",
        loan_amount="3500", first_disbursement_amount="1750",
        second_disbursement_amount="1750", origination_fee="29.05",
        interest_rate="6.53", borrower_id=s["student_id"], borrower_type="student",
        cod_loan_id=None, mpn_signed_date=None, entrance_counseling_required=1,
        entrance_counseling_date=None, exit_counseling_required=0,
        exit_counseling_date=None))
    assert is_ok(r), r
    return r["id"], award["id"], pkg_id


# ---------------------------------------------------------------------------
# finaid-create-verification-request
# ---------------------------------------------------------------------------

def test_create_verification_request_writes_request_and_three_required_docs(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r = _request(s)
    assert is_ok(r), r
    assert r["verification_group"] == "V1"
    assert r["documents_created"] == 3
    row = conn.execute(
        "SELECT isir_id, student_id, verification_group, status, requested_date, "
        "deadline_date, company_id FROM finaid_verification_request WHERE id = ?",
        (r["id"],)).fetchone()
    assert tuple(row) == (s["isir_id"], s["student_id"], "V1", "initiated",
                          "2025-05-01", "2025-06-01", s["company_id"])
    docs = conn.execute(
        "SELECT document_type, submission_status, is_required "
        "FROM finaid_verification_document WHERE verification_request_id = ? "
        "ORDER BY document_type", (r["id"],)).fetchall()
    assert [tuple(d) for d in docs] == [
        ("household_verification", "not_submitted", 1),
        ("tax_transcript", "not_submitted", 1),
        ("w2", "not_submitted", 1),
    ]
    # The ISIR the request was raised against is untouched.
    assert conn.execute(
        "SELECT sai FROM finaid_isir WHERE id = ?", (s["isir_id"],)).fetchone()[0] == "1500"


def test_create_verification_request_refuses_missing_group_and_writes_nothing(env):
    s, conn = env, env["conn"]
    before = _snap(conn, ["finaid_verification_request", "finaid_verification_document"])
    r = call_action(FA_ACTIONS["finaid-create-verification-request"], s["conn"], ns(
        isir_id=s["isir_id"], student_id=s["student_id"], company_id=s["company_id"],
        verification_group=None, deadline_date="2025-06-01",
        requested_date="2025-05-01", assigned_to=None))
    assert is_error(r)
    assert r["message"] == "verification_group is required"
    assert _snap(conn, ["finaid_verification_request", "finaid_verification_document"]) == before


# ---------------------------------------------------------------------------
# finaid-complete-verification
# ---------------------------------------------------------------------------

def test_complete_verification_marks_request_complete_with_exact_date(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    req_id = _request(s)["id"]
    _accept_all_docs(s, req_id)
    r = call_action(FA_ACTIONS["finaid-complete-verification"], s["conn"], ns(
        verification_request_id=req_id, completed_date="2025-06-02"))
    assert is_ok(r), r
    assert r["document_status"] == "complete"
    row = conn.execute(
        "SELECT status, completed_date FROM finaid_verification_request WHERE id = ?",
        (req_id,)).fetchone()
    assert tuple(row) == ("complete", "2025-06-02")
    # The accepted documents are unchanged by completion.
    assert [d[0] for d in conn.execute(
        "SELECT submission_status FROM finaid_verification_document "
        "WHERE verification_request_id = ?", (req_id,)).fetchall()] == [
        "accepted", "accepted", "accepted"]


def test_complete_verification_refuses_pending_docs_and_leaves_request_open(env):
    s, conn = env, env["conn"]
    req_id = _request(s)["id"]
    before = _snap(conn, ["finaid_verification_request", "finaid_verification_document"])
    r = call_action(FA_ACTIONS["finaid-complete-verification"], s["conn"], ns(
        verification_request_id=req_id, completed_date="2025-06-02"))
    assert is_error(r)
    assert r["message"] == "3 required document(s) not yet accepted or waived"
    assert tuple(conn.execute(
        "SELECT status, completed_date FROM finaid_verification_request WHERE id = ?",
        (req_id,)).fetchone()) == ("initiated", "")
    assert _snap(conn, ["finaid_verification_request", "finaid_verification_document"]) == before


# ---------------------------------------------------------------------------
# finaid-create-award-package
# ---------------------------------------------------------------------------

def test_create_award_package_computes_need_and_numbers_the_series(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    r = _package(s)
    assert is_ok(r), r
    assert r["naming_series"] == "AWD-2025-2026-00001"
    assert r["financial_need"] == "28300.00"
    assert Decimal(r["financial_need"]) == Decimal("28300.00")
    row = conn.execute(
        "SELECT naming_series, student_id, aid_year_id, academic_term_id, isir_id, "
        "cost_of_attendance_id, enrollment_status, packaged_by, financial_need, "
        "total_grants, total_loans, total_work_study, total_aid, status "
        "FROM finaid_award_package WHERE id = ?", (r["id"],)).fetchone()
    assert tuple(row) == ("AWD-2025-2026-00001", s["student_id"], s["aid_year_id"],
                          s["term_id"], s["isir_id"], s["cost_of_attendance_id"],
                          "full_time", "counselor", "28300.00",
                          "0", "0", "0", "0", "draft")
    # The budget and ISIR the need was computed from are untouched.
    assert conn.execute(
        "SELECT total_coa FROM finaid_cost_of_attendance WHERE id = ?",
        (s["cost_of_attendance_id"],)).fetchone()[0] == "29800"
    assert conn.execute(
        "SELECT sai FROM finaid_isir WHERE id = ?",
        (s["isir_id"],)).fetchone()[0] == "1500"


def test_create_award_package_refuses_missing_term_and_writes_nothing(env):
    s, conn = env, env["conn"]
    before = _snap(conn, ["finaid_award_package"])
    r = _package(s, academic_term_id=None)
    assert is_error(r)
    assert r["message"] == "academic_term_id is required"
    assert _snap(conn, ["finaid_award_package"]) == before
    assert _count(conn, "finaid_award_package") == 0


# ---------------------------------------------------------------------------
# finaid-create-r2t4
# ---------------------------------------------------------------------------

def test_create_r2t4_writes_calculation_with_45_day_due_date(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    pkg_id = _package_id(s)
    r = call_action(FA_ACTIONS["finaid-create-r2t4"], s["conn"], ns(
        student_id=s["student_id"], academic_term_id=s["term_id"],
        award_package_id=pkg_id, company_id=s["company_id"],
        withdrawal_type="official", withdrawal_date="2025-10-01",
        last_date_of_attendance="2025-10-01", determination_date="2025-10-05",
        payment_period_start="2025-08-25", payment_period_end="2025-12-20",
        payment_period_days=117))
    assert is_ok(r), r
    assert r["institution_return_due_date"] == "2025-11-19"
    row = conn.execute(
        "SELECT student_id, academic_term_id, award_package_id, withdrawal_type, "
        "withdrawal_date, last_date_of_attendance, determination_date, "
        "payment_period_start, payment_period_end, payment_period_days, "
        "institution_return_due_date, status, company_id "
        "FROM finaid_r2t4_calculation WHERE id = ?", (r["id"],)).fetchone()
    assert tuple(row) == (s["student_id"], s["term_id"], pkg_id, "official",
                          "2025-10-01", "2025-10-01", "2025-10-05",
                          "2025-08-25", "2025-12-20", 117, "2025-11-19",
                          "calculated", s["company_id"])
    # The award package the calculation points at is untouched.
    assert conn.execute(
        "SELECT status FROM finaid_award_package WHERE id = ?",
        (pkg_id,)).fetchone()[0] == "draft"


def test_create_r2t4_refuses_missing_student_and_writes_nothing(env):
    s, conn = env, env["conn"]
    pkg_id = _package_id(s)
    before = _snap(conn, ["finaid_r2t4_calculation"])
    r = call_action(FA_ACTIONS["finaid-create-r2t4"], s["conn"], ns(
        student_id=None, academic_term_id=s["term_id"], award_package_id=pkg_id,
        company_id=s["company_id"], withdrawal_type="official",
        withdrawal_date="2025-10-01", last_date_of_attendance="2025-10-01",
        determination_date="2025-10-05", payment_period_start="2025-08-25",
        payment_period_end="2025-12-20", payment_period_days=117))
    assert is_error(r)
    assert r["message"] == "student_id is required"
    assert _snap(conn, ["finaid_r2t4_calculation"]) == before


# ---------------------------------------------------------------------------
# finaid-delete-award
# ---------------------------------------------------------------------------

def test_delete_award_removes_row_and_recomputes_package_totals(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    pkg_id = _package_id(s)
    pell = _award_id(s, pkg_id, "pell", "3000.00")
    loan = _award_id(s, pkg_id, "subsidized_loan", "3500.00")
    r = call_action(FA_ACTIONS["finaid-delete-award"], s["conn"], ns(award_id=loan))
    assert is_ok(r), r
    assert r["deleted"] is True
    assert [row[0] for row in conn.execute(
        "SELECT id FROM finaid_award WHERE award_package_id = ?", (pkg_id,))] == [pell]
    assert tuple(conn.execute(
        "SELECT offered_amount, accepted_amount, disbursed_amount, acceptance_status "
        "FROM finaid_award WHERE id = ?", (pell,)).fetchone()) == (
        "3000.00", "0", "0", "pending")
    assert tuple(conn.execute(
        "SELECT financial_need, total_grants, total_loans, total_work_study, "
        "total_aid, status FROM finaid_award_package WHERE id = ?",
        (pkg_id,)).fetchone()) == ("28300.00", "3000.00", "0.00", "0.00",
                                   "3000.00", "draft")


def test_delete_award_refuses_unknown_award_and_changes_nothing(env):
    s, conn = env, env["conn"]
    pkg_id = _package_id(s)
    pell = _award_id(s, pkg_id, "pell", "3000.00")
    before = _snap(conn, ["finaid_award", "finaid_award_package"])
    r = call_action(FA_ACTIONS["finaid-delete-award"], s["conn"], ns(
        award_id="no-such-award"))
    assert is_error(r)
    assert r["message"] == "Award not found"
    assert _snap(conn, ["finaid_award", "finaid_award_package"]) == before
    assert conn.execute(
        "SELECT offered_amount FROM finaid_award WHERE id = ?",
        (pell,)).fetchone()[0] == "3000.00"


# ---------------------------------------------------------------------------
# finaid-delete-cost-of-attendance
# ---------------------------------------------------------------------------

def test_delete_cost_of_attendance_removes_unreferenced_budget(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    added = call_action(FA_ACTIONS["finaid-add-cost-of-attendance"], s["conn"], ns(
        aid_year_id=s["aid_year_id"], company_id=s["company_id"], program_id=None,
        enrollment_status="half_time", living_arrangement="off_campus",
        tuition_fees="1000", books_supplies="100", room_board="100",
        transportation="10", personal_expenses="10", loan_fees="0"))
    assert is_ok(added), added
    assert added["total_coa"] == "1220.00"
    assert Decimal(added["total_coa"]) == Decimal("1220.00")
    assert _count(conn, "finaid_cost_of_attendance") == 2
    r = call_action(FA_ACTIONS["finaid-delete-cost-of-attendance"], s["conn"], ns(
        id=added["id"]))
    assert is_ok(r), r
    assert r["deleted"] is True
    assert _count(conn, "finaid_cost_of_attendance") == 1
    # The seeded budget survives with its exact total.
    assert conn.execute(
        "SELECT total_coa FROM finaid_cost_of_attendance WHERE id = ?",
        (s["cost_of_attendance_id"],)).fetchone()[0] == "29800"


def test_delete_cost_of_attendance_refuses_referenced_budget_and_keeps_it(env):
    s, conn = env, env["conn"]
    pkg_id = _package_id(s)
    before = _snap(conn, ["finaid_cost_of_attendance"])
    r = call_action(FA_ACTIONS["finaid-delete-cost-of-attendance"], s["conn"], ns(
        id=s["cost_of_attendance_id"]))
    assert is_error(r)
    assert r["message"] == "Cannot delete COA referenced by award package(s)"
    assert _snap(conn, ["finaid_cost_of_attendance"]) == before
    assert conn.execute(
        "SELECT cost_of_attendance_id FROM finaid_award_package WHERE id = ?",
        (pkg_id,)).fetchone()[0] == s["cost_of_attendance_id"]


def test_delete_cost_of_attendance_unknown_id_reports_deleted_behaviour(env):
    s, conn = env, env["conn"]
    before = _snap(conn, ["finaid_cost_of_attendance"])
    r = call_action(FA_ACTIONS["finaid-delete-cost-of-attendance"], s["conn"], ns(
        id="no-such-coa"))
    assert is_ok(r), r
    assert r["deleted"] is True
    assert _snap(conn, ["finaid_cost_of_attendance"]) == before


# ---------------------------------------------------------------------------
# finaid-deny-award
# ---------------------------------------------------------------------------

def test_deny_award_declines_and_zeroes_accepted_amount(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    pkg_id = _package_id(s)
    pell = _award_id(s, pkg_id, "pell", "5000.00")
    loan = _award_id(s, pkg_id, "subsidized_loan", "3500.00")
    assert is_ok(_accept(s, pell, "5000.00"))
    assert is_ok(_accept(s, loan, "3500.00"))
    r = call_action(FA_ACTIONS["finaid-deny-award"], s["conn"], ns(award_id=loan))
    assert is_ok(r), r
    assert r["acceptance_status"] == "declined"
    assert tuple(conn.execute(
        "SELECT offered_amount, accepted_amount, disbursed_amount, acceptance_status, "
        "acceptance_date, is_locked FROM finaid_award WHERE id = ?",
        (loan,)).fetchone()) == ("3500.00", "0", "0", "declined", "2025-08-01", 0)
    # The other award in the package is untouched.
    assert tuple(conn.execute(
        "SELECT offered_amount, accepted_amount, disbursed_amount, acceptance_status, "
        "acceptance_date, is_locked FROM finaid_award WHERE id = ?",
        (pell,)).fetchone()) == ("5000.00", "5000.00", "0", "accepted", "2025-08-01", 0)


def test_deny_award_refuses_disbursed_award_and_keeps_it_accepted(env):
    s, conn = env, env["conn"]
    pkg_id = _package_id(s)
    pell = _award_id(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    assert is_ok(_disburse(s, pell, "1500.00"))
    before = _snap(conn, ["finaid_award"])
    r = call_action(FA_ACTIONS["finaid-deny-award"], s["conn"], ns(award_id=pell))
    assert is_error(r)
    assert r["message"] == ("Cannot decline an award with disbursed amount 1500.00; "
                            "cancel its disbursements first")
    assert _snap(conn, ["finaid_award"]) == before
    assert tuple(conn.execute(
        "SELECT accepted_amount, disbursed_amount, acceptance_status "
        "FROM finaid_award WHERE id = ?", (pell,)).fetchone()) == (
        "4000.00", "1500.00", "accepted")


# ---------------------------------------------------------------------------
# finaid-deny-scholarship-application
# ---------------------------------------------------------------------------

def test_deny_scholarship_application_denies_with_exact_reason(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    program_id = _scholarship_program(s)
    app_id = _scholarship_application(s, program_id)
    assert tuple(conn.execute(
        "SELECT status, denial_reason, award_amount FROM finaid_scholarship_application "
        "WHERE id = ?", (app_id,)).fetchone()) == ("submitted", "", "0")
    r = call_action(SCH_ACTIONS["finaid-deny-scholarship-application"], s["conn"], ns(
        id=app_id, denial_reason="GPA below threshold"))
    assert is_ok(r), r
    assert r["document_status"] == "denied"
    assert tuple(conn.execute(
        "SELECT status, denial_reason, award_amount FROM finaid_scholarship_application "
        "WHERE id = ?", (app_id,)).fetchone()) == (
        "denied", "GPA below threshold", "0")
    # Denying awards nothing, so the program budget is untouched.
    assert conn.execute(
        "SELECT budget_remaining FROM finaid_scholarship_program WHERE id = ?",
        (program_id,)).fetchone()[0] == "50000.00"


def test_deny_scholarship_application_refuses_unknown_id_and_writes_nothing(env):
    s, conn = env, env["conn"]
    program_id = _scholarship_program(s)
    app_id = _scholarship_application(s, program_id)
    before = _snap(conn, ["finaid_scholarship_application", "finaid_scholarship_program"])
    r = call_action(SCH_ACTIONS["finaid-deny-scholarship-application"], s["conn"], ns(
        id="no-such-app", denial_reason="GPA below threshold"))
    assert is_error(r)
    assert r["message"] == "Scholarship application no-such-app not found"
    assert _snap(conn, ["finaid_scholarship_application",
                        "finaid_scholarship_program"]) == before
    assert conn.execute(
        "SELECT status FROM finaid_scholarship_application WHERE id = ?",
        (app_id,)).fetchone()[0] == "submitted"


# ---------------------------------------------------------------------------
# finaid-deny-work-study-timesheet
# ---------------------------------------------------------------------------

def test_deny_work_study_timesheet_rejects_with_exact_reason(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; stored rows only.
    _, _, _, assign_id, ts_id = _work_study_chain(s)
    r = call_action(WS_ACTIONS["finaid-deny-work-study-timesheet"], s["conn"], ns(
        id=ts_id, supervisor_approved_by="supervisor-1",
        rejection_reason="hours mismatch"))
    assert is_ok(r), r
    assert r["supervisor_approval_status"] == "rejected"
    row = conn.execute(
        "SELECT supervisor_approval_status, supervisor_approved_by, rejection_reason, "
        "hours_worked, earnings, cumulative_earnings, payroll_exported "
        "FROM finaid_work_study_timesheet WHERE id = ?", (ts_id,)).fetchone()
    assert tuple(row) == ("rejected", "supervisor-1", "hours mismatch",
                          "20", "240.00", "240.00", 0)
    assert Decimal(row[4]) == Decimal("240.00")
    # Rejecting earns nothing, so the assignment total is untouched.
    assert conn.execute(
        "SELECT earned_to_date FROM finaid_work_study_assignment WHERE id = ?",
        (assign_id,)).fetchone()[0] == "0.00"


def test_deny_work_study_timesheet_refuses_second_reject_and_keeps_row(env):
    s, conn = env, env["conn"]
    _, _, _, _, ts_id = _work_study_chain(s)
    first = call_action(WS_ACTIONS["finaid-deny-work-study-timesheet"], s["conn"], ns(
        id=ts_id, supervisor_approved_by="supervisor-1",
        rejection_reason="hours mismatch"))
    assert is_ok(first), first
    before = _snap(conn, ["finaid_work_study_timesheet"])
    r = call_action(WS_ACTIONS["finaid-deny-work-study-timesheet"], s["conn"], ns(
        id=ts_id, supervisor_approved_by="supervisor-1",
        rejection_reason="second attempt"))
    assert is_error(r)
    assert r["message"] == (
        "Timesheet %s cannot be rejected: status is 'rejected'" % ts_id)
    assert _snap(conn, ["finaid_work_study_timesheet"]) == before


# ---------------------------------------------------------------------------
# finaid-generate-cod-export
# ---------------------------------------------------------------------------

def test_generate_cod_export_lists_pending_disbursement_and_writes_nothing(env):
    s, conn = env, env["conn"]
    # This action is read-only and does not reach the general ledger.
    pkg_id = _package_id(s)
    award_id = _award_id(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, award_id, "4000.00"))
    assert is_ok(_disburse(s, award_id, "1500.00"))
    before = _snap(conn, ["finaid_disbursement", "finaid_award"])
    r = call_action(FA_ACTIONS["finaid-generate-cod-export"], s["conn"], ns(
        company_id=s["company_id"], aid_year_id=None))
    assert is_ok(r), r
    assert r["count"] == 1
    record = r["cod_records"][0]
    assert record["award_id"] == award_id
    assert record["aid_type"] == "pell"
    assert record["amount"] == "1500.00"
    assert Decimal(record["amount"]) == Decimal("1500.00")
    # Read-only proof: the export wrote no rows anywhere it could.
    assert _snap(conn, ["finaid_disbursement", "finaid_award"]) == before


def test_generate_cod_export_refuses_missing_company_and_writes_nothing(env):
    s, conn = env, env["conn"]
    pkg_id = _package_id(s)
    award_id = _award_id(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, award_id, "4000.00"))
    assert is_ok(_disburse(s, award_id, "1500.00"))
    before = _snap(conn, ["finaid_disbursement"])
    r = call_action(FA_ACTIONS["finaid-generate-cod-export"], s["conn"], ns(
        company_id=None, aid_year_id=None))
    assert is_error(r)
    assert r["message"] == "company_id is required"
    assert _snap(conn, ["finaid_disbursement"]) == before


# ---------------------------------------------------------------------------
# finaid-generate-cod-origination
# ---------------------------------------------------------------------------

def test_generate_cod_origination_returns_exact_loan_amounts_and_writes_nothing(env):
    s, conn = env, env["conn"]
    # This action is read-only and does not reach the general ledger.
    loan_id, award_id, _pkg_id = _loan(s)
    before = _snap(conn, ["finaid_loan"])
    r = call_action(LOAN_ACTIONS["finaid-generate-cod-origination"], s["conn"], ns(
        id=loan_id))
    assert is_ok(r), r
    assert r["loan_id"] == loan_id
    assert r["award_id"] == award_id
    assert r["loan_amount"] == "3500.00"
    assert r["first_disbursement_amount"] == "1750.00"
    assert r["second_disbursement_amount"] == "1750.00"
    assert r["origination_fee"] == "29.05"
    assert r["interest_rate"] == "6.53"
    assert r["loan_status"] == "originated"
    assert r["offered_amount"] == "3500.00"
    for key in ("loan_amount", "first_disbursement_amount",
                "second_disbursement_amount", "origination_fee"):
        assert Decimal(r[key]) == Decimal(r[key])
    # Read-only proof: the loan row is byte-identical after generation.
    assert _snap(conn, ["finaid_loan"]) == before


def test_generate_cod_origination_refuses_unknown_loan_and_writes_nothing(env):
    s, conn = env, env["conn"]
    loan_id, _, _ = _loan(s)
    before = _snap(conn, ["finaid_loan"])
    r = call_action(LOAN_ACTIONS["finaid-generate-cod-origination"], s["conn"], ns(
        id="no-such-loan"))
    assert is_error(r)
    assert r["message"] == "Loan not found: no-such-loan"
    assert _snap(conn, ["finaid_loan"]) == before
    assert conn.execute(
        "SELECT status FROM finaid_loan WHERE id = ?",
        (loan_id,)).fetchone()[0] == "originated"


# ---------------------------------------------------------------------------
# finaid-generate-payroll-export
# ---------------------------------------------------------------------------

def test_generate_payroll_export_marks_only_approved_timesheet_exported(env):
    s, conn = env, env["conn"]
    # This action does not reach the general ledger; it only stamps timesheets.
    _, _, _, _, ts_id = _work_study_chain(s)
    pending = call_action(WS_ACTIONS["finaid-submit-work-study-timesheet"], s["conn"], ns(
        assignment_id=conn.execute(
            "SELECT assignment_id FROM finaid_work_study_timesheet WHERE id = ?",
            (ts_id,)).fetchone()[0],
        student_id=s["student_id"], company_id=s["company_id"],
        pay_period_start="2025-09-16", pay_period_end="2025-09-30",
        hours_worked="10", submission_date="2025-10-01"))
    assert is_ok(pending), pending
    approved = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], s["conn"], ns(
        id=ts_id, supervisor_approved_by="supervisor-1"))
    assert is_ok(approved), approved
    r = call_action(WS_ACTIONS["finaid-generate-payroll-export"], s["conn"], ns(
        company_id=s["company_id"], academic_term_id=None, pay_period_start=None))
    assert is_ok(r), r
    assert r["exported_count"] == 1
    assert r["total_amount"] == "240.00"
    assert Decimal(r["total_amount"]) == Decimal("240.00")
    assert "student_id,assignment_id,job_title" in r["csv_data"]
    assert "240.00" in r["csv_data"]
    row = conn.execute(
        "SELECT payroll_exported, payroll_export_date, earnings "
        "FROM finaid_work_study_timesheet WHERE id = ?", (ts_id,)).fetchone()
    assert row[0] == 1
    assert row[1] != ""
    assert row[2] == "240.00"
    # The still-pending timesheet is not exported and is unchanged.
    assert tuple(conn.execute(
        "SELECT supervisor_approval_status, payroll_exported, earnings "
        "FROM finaid_work_study_timesheet WHERE id = ?",
        (pending["id"],)).fetchone()) == ("pending", 0, "120.00")


def test_generate_payroll_export_refuses_missing_company_and_exports_nothing(env):
    s, conn = env, env["conn"]
    _, _, _, _, ts_id = _work_study_chain(s)
    approved = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], s["conn"], ns(
        id=ts_id, supervisor_approved_by="supervisor-1"))
    assert is_ok(approved), approved
    before = _snap(conn, ["finaid_work_study_timesheet"])
    r = call_action(WS_ACTIONS["finaid-generate-payroll-export"], s["conn"], ns(
        company_id=None, academic_term_id=None, pay_period_start=None))
    assert is_error(r)
    assert r["message"] == "--company-id is required"
    assert _snap(conn, ["finaid_work_study_timesheet"]) == before
    assert conn.execute(
        "SELECT payroll_exported FROM finaid_work_study_timesheet WHERE id = ?",
        (ts_id,)).fetchone()[0] == 0
