"""Behavioural depth for the 12 m408 finaid actions (task m408-depth-educlaw-finaid-8).

Each action below was previously covered only by a routability contract test in
``testing/integration/contract/test_educlaw_finaid_contract.py`` (and, for
``finaid-list-work-study-timesheets``, a shape-only ``is_ok`` test in
``test_finaid.py``). Those tests stay untouched; the tests here prove what each
action actually does to the database: the exact row written (money as exact
``TEXT`` strings compared through ``Decimal``, never float), the rows that must
NOT have changed, and one input-validation refusal that must leave the database
byte-identical.

Depth signal per action (stored row unless noted):
  finaid-list-work-study-timesheets ....... read-only list (payload mirrors rows)
  finaid-record-award-disbursement ........ stored disbursement row + award total
  finaid-record-credit-balance-return ..... stored return-date stamp
  finaid-record-r2t4-return ............... stored status/date stamp
  finaid-record-r2t4-return-disbursement .. stored return row + calc stamp
  finaid-submit-award-offer ............... stored package state transition
  finaid-submit-sap-appeal ................ stored appeal row
  finaid-submit-scholarship-application ... stored application row + audit row
  finaid-submit-work-study-timesheet ...... stored timesheet row + audit row
  finaid-terminate-scholarship-program .... stored deactivation + audit row
  finaid-terminate-work-study-assignment .. stored termination + job seat + audit
  finaid-terminate-work-study-job ......... stored close (no audit row written)

Ledger note (applies to every test in this file): none of these twelve handlers
writes a general-ledger journal; ``financial_aid.py`` contains no ledger write
at all, and the ``scholarships.py``/``work_study.py`` handlers used here append
at most one ``audit_log`` row. Every success test asserts stored rows, never
ledger legs; a later reader must not add balanced-legs assertions here.

All dates the caller controls are passed explicitly, so nothing here depends on
today's date except handler-stamped fields (``packaged_at``), which are asserted
non-empty rather than exact.
"""
import importlib.util
import json
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

from erpclaw_lib.db import get_connection

FA_ACTIONS = _load("financial_aid", _SCRIPTS_DIR).ACTIONS
SCHOL_ACTIONS = _load("scholarships", _SCRIPTS_DIR).ACTIONS
WS_ACTIONS = _load("work_study", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def fx(db_path):
    conn = get_connection()
    company_id = _helpers.seed_company(conn)
    student_id = _helpers.seed_student(conn, company_id)
    aid_year_id = _helpers.seed_aid_year(conn, company_id)
    year_id = _helpers.seed_academic_year(conn, company_id)
    term_id = _helpers.seed_academic_term(conn, company_id, year_id)
    program_id = _helpers.seed_program(conn, company_id)
    enrollment_id = _helpers.seed_program_enrollment(conn, student_id, program_id, year_id, company_id)
    isir_id = _helpers.seed_isir(conn, student_id, aid_year_id, company_id)
    coa_id = _helpers.seed_cost_of_attendance(conn, aid_year_id, company_id)
    yield {
        "conn": conn, "company_id": company_id, "student_id": student_id,
        "aid_year_id": aid_year_id, "term_id": term_id,
        "program_enrollment_id": enrollment_id, "isir_id": isir_id,
        "cost_of_attendance_id": coa_id,
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
            rows = conn.execute("SELECT * FROM %s" % table).fetchall()
        except Exception:
            continue
        snap[table] = sorted(
            json.dumps(dict(row), sort_keys=True, default=str) for row in rows)
    return snap


def _unchanged_except(before, after, touched):
    for table, rows in before.items():
        if table not in touched:
            assert after[table] == rows, table


def _package(fx):
    resp = call_action(FA_ACTIONS["finaid-create-award-package"], fx["conn"], ns(
        student_id=fx["student_id"], aid_year_id=fx["aid_year_id"],
        academic_term_id=fx["term_id"], company_id=fx["company_id"],
        program_enrollment_id=fx["program_enrollment_id"], isir_id=fx["isir_id"],
        cost_of_attendance_id=fx["cost_of_attendance_id"],
        enrollment_status="full_time", financial_need=None,
        acceptance_deadline=None, packaged_by=None, notes=None))
    assert is_ok(resp), resp
    return resp["id"]


def _award(fx, package_id, aid_type="pell", offered="5000.00"):
    resp = call_action(FA_ACTIONS["finaid-add-award"], fx["conn"], ns(
        award_package_id=package_id, student_id=fx["student_id"],
        aid_year_id=fx["aid_year_id"], academic_term_id=fx["term_id"],
        aid_type=aid_type, aid_source="federal", offered_amount=offered,
        company_id=fx["company_id"], fund_source_id=None, gl_account_id=None,
        notes=None))
    assert is_ok(resp), resp
    return resp["id"]


def _accept(fx, award_id, amount, date="2025-08-01"):
    resp = call_action(FA_ACTIONS["finaid-accept-award"], fx["conn"], ns(
        award_id=award_id, accepted_amount=amount, acceptance_date=date))
    assert is_ok(resp), resp


def _disburse(fx, award_id, amount, number=1, date="2025-09-02"):
    return call_action(FA_ACTIONS["finaid-record-award-disbursement"], fx["conn"], ns(
        award_id=award_id, student_id=fx["student_id"], amount=amount,
        disbursement_date=date, company_id=fx["company_id"],
        disbursed_by="bursar", disbursement_number=number))


def _r2t4(fx, package_id):
    resp = call_action(FA_ACTIONS["finaid-create-r2t4"], fx["conn"], ns(
        student_id=fx["student_id"], academic_term_id=fx["term_id"],
        award_package_id=package_id, company_id=fx["company_id"],
        withdrawal_type="official", withdrawal_date="2025-10-01",
        last_date_of_attendance="2025-10-01", determination_date="2025-10-05",
        payment_period_start="2025-08-25", payment_period_end="2025-12-20",
        payment_period_days=117))
    assert is_ok(resp), resp
    return resp["id"]


def _fsp_evaluation(fx):
    resp = call_action(FA_ACTIONS["finaid-generate-sap-evaluation"], fx["conn"], ns(
        student_id=fx["student_id"], academic_term_id=fx["term_id"],
        aid_year_id=fx["aid_year_id"], company_id=fx["company_id"],
        gpa_earned="1.50", gpa_threshold="2.00",
        credits_attempted="12", credits_completed="6",
        evaluation_date="2025-12-20", evaluated_by="system"))
    assert is_ok(resp), resp
    assert resp["sap_status"] == "FSP", resp
    return resp["id"]


def _scholarship_program(fx, name="M408 Merit", code="M408-MERIT"):
    resp = call_action(SCHOL_ACTIONS["finaid-add-scholarship-program"], fx["conn"], ns(
        company_id=fx["company_id"], name=name, code=code,
        scholarship_type="merit", funding_source="endowment",
        award_method="application_required", award_amount_type="fixed",
        award_amount="2000.00", award_period="annual",
        applies_to_aid_type="institutional_scholarship",
        annual_budget="10000.00", max_recipients=5))
    assert is_ok(resp), resp
    return resp["id"]


def _ws_job(fx, title="Library Assistant", total_positions=1):
    resp = call_action(WS_ACTIONS["finaid-add-work-study-job"], fx["conn"], ns(
        company_id=fx["company_id"], aid_year_id=fx["aid_year_id"],
        job_title=title, department_id=None, supervisor_id=None,
        job_type="on_campus", pay_rate="12.00", hours_per_week="15",
        total_positions=total_positions, description=None))
    assert is_ok(resp), resp
    return resp["id"]


def _ws_assignment(fx, job_id, award_limit="3000.00"):
    package_id = _package(fx)
    award_id = _award(fx, package_id, aid_type="fws", offered="3000.00")
    resp = call_action(WS_ACTIONS["finaid-assign-student-to-job"], fx["conn"], ns(
        student_id=fx["student_id"], award_id=award_id, job_id=job_id,
        aid_year_id=fx["aid_year_id"], academic_term_id=fx["term_id"],
        company_id=fx["company_id"], start_date="2025-09-01",
        end_date="2026-05-15", award_limit=award_limit))
    assert is_ok(resp), resp
    return resp["id"]


# ---------------------------------------------------------------------------
# finaid-submit-award-offer — stored package state transition
# ---------------------------------------------------------------------------

class TestSubmitAwardOfferDepth:
    def test_offer_moves_package_from_draft_to_offered_with_exact_fields(self, fx):
        conn = fx["conn"]
        # No ledger legs: a package status transition only, never journals.
        package_id = _package(fx)
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-submit-award-offer"], conn, ns(
            award_package_id=package_id, packaged_by="counselor",
            offered_date="2025-07-15"))
        assert is_ok(resp), resp
        assert resp["document_status"] == "offered"
        row = conn.execute(
            "SELECT status, offered_date, packaged_by, financial_need, "
            "total_grants, total_loans, total_work_study, total_aid, packaged_at "
            "FROM finaid_award_package WHERE id = ?", (package_id,)).fetchone()
        assert tuple(row[:8]) == ("offered", "2025-07-15", "counselor",
                                  "28300.00", "0", "0", "0", "0")
        assert Decimal(row[3]) == Decimal("28300.00")
        assert row[8] != ""
        _unchanged_except(before, _snapshot(conn), {"finaid_award_package"})
        repeat = call_action(FA_ACTIONS["finaid-submit-award-offer"], conn, ns(
            award_package_id=package_id, packaged_by="counselor",
            offered_date="2025-07-15"))
        assert is_error(repeat)
        assert repeat["message"] == "Package must be in draft status to offer"
        assert conn.execute(
            "SELECT status FROM finaid_award_package WHERE id = ?",
            (package_id,)).fetchone()[0] == "offered"

    def test_offer_refuses_a_missing_package_id_and_writes_nothing(self, fx):
        conn = fx["conn"]
        package_id = _package(fx)
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-submit-award-offer"], conn, ns(
            award_package_id=None, packaged_by="counselor",
            offered_date="2025-07-15"))
        assert is_error(resp)
        assert resp["message"] == "award_package_id or id is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT status FROM finaid_award_package WHERE id = ?",
            (package_id,)).fetchone()[0] == "draft"


# ---------------------------------------------------------------------------
# finaid-record-award-disbursement — stored disbursement row + award total
# ---------------------------------------------------------------------------

class TestRecordAwardDisbursementDepth:
    def test_disbursement_writes_exact_row_and_accumulates_on_award(self, fx):
        conn = fx["conn"]
        # No ledger legs: a disbursement row plus the award total, never journals.
        package_id = _package(fx)
        award_id = _award(fx, package_id)
        _accept(fx, award_id, "4000.00")
        before = _snapshot(conn)
        resp = _disburse(fx, award_id, "1500.00")
        assert is_ok(resp), resp
        assert resp["amount"] == "1500.00"
        assert resp["disbursement_date"] == "2025-09-02"
        row = conn.execute(
            "SELECT disbursement_type, disbursement_number, amount, "
            "disbursement_date, award_package_id, student_id, company_id, "
            "disbursed_by, cod_status, is_credit_balance, "
            "credit_balance_returned_date "
            "FROM finaid_disbursement WHERE id = ?", (resp["id"],)).fetchone()
        assert tuple(row) == ("disbursement", 1, "1500.00", "2025-09-02",
                              package_id, fx["student_id"], fx["company_id"],
                              "bursar", "", 0, "")
        assert Decimal(row[2]) == Decimal("1500.00")
        award = conn.execute(
            "SELECT offered_amount, accepted_amount, disbursed_amount, "
            "acceptance_status, is_locked FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()
        assert tuple(award) == ("5000.00", "4000.00", "1500.00", "accepted", 1)
        assert Decimal(award[2]) == Decimal("1500.00")
        _unchanged_except(before, _snapshot(conn),
                          {"finaid_disbursement", "finaid_award"})

    def test_disbursement_refuses_a_missing_amount_and_writes_nothing(self, fx):
        conn = fx["conn"]
        package_id = _package(fx)
        award_id = _award(fx, package_id)
        _accept(fx, award_id, "4000.00")
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-record-award-disbursement"], conn, ns(
            award_id=award_id, student_id=fx["student_id"], amount=None,
            disbursement_date="2025-09-02", company_id=fx["company_id"],
            disbursed_by="bursar", disbursement_number=1))
        assert is_error(resp)
        assert resp["message"] == "amount is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT disbursed_amount FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()[0] == "0"
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_disbursement").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# finaid-record-credit-balance-return — stored return-date stamp
# ---------------------------------------------------------------------------

class TestRecordCreditBalanceReturnDepth:
    def _credit_balance(self, fx, disb_id):
        conn = fx["conn"]
        conn.execute(
            "UPDATE finaid_disbursement SET is_credit_balance = 1, "
            "credit_balance_amount = ?, credit_balance_date = ? WHERE id = ?",
            ("850.00", "2025-09-03", disb_id))
        conn.commit()

    def test_return_records_the_date_once_and_leaves_amounts_alone(self, fx):
        conn = fx["conn"]
        # No ledger legs: a date stamp on the disbursement row, never journals.
        package_id = _package(fx)
        award_id = _award(fx, package_id)
        _accept(fx, award_id, "4000.00")
        disb = _disburse(fx, award_id, "4000.00")
        assert is_ok(disb), disb
        self._credit_balance(fx, disb["id"])
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-record-credit-balance-return"], conn, ns(
            id=disb["id"], return_date="2025-09-10"))
        assert is_ok(resp), resp
        assert resp["credit_balance_returned_date"] == "2025-09-10"
        row = conn.execute(
            "SELECT amount, is_credit_balance, credit_balance_amount, "
            "credit_balance_date, credit_balance_returned_date "
            "FROM finaid_disbursement WHERE id = ?", (disb["id"],)).fetchone()
        assert tuple(row) == ("4000.00", 1, "850.00", "2025-09-03", "2025-09-10")
        assert Decimal(row[0]) == Decimal("4000.00")
        assert Decimal(row[2]) == Decimal("850.00")
        assert conn.execute(
            "SELECT disbursed_amount FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()[0] == "4000.00"
        _unchanged_except(before, _snapshot(conn), {"finaid_disbursement"})
        again = call_action(FA_ACTIONS["finaid-record-credit-balance-return"], conn, ns(
            id=disb["id"], return_date="2025-09-15"))
        assert is_error(again)
        assert again["message"] == "Credit balance already returned on 2025-09-10"
        assert conn.execute(
            "SELECT credit_balance_returned_date FROM finaid_disbursement "
            "WHERE id = ?", (disb["id"],)).fetchone()[0] == "2025-09-10"

    def test_return_refuses_a_missing_id_and_writes_nothing(self, fx):
        conn = fx["conn"]
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-record-credit-balance-return"], conn, ns(
            id=None, return_date="2025-09-10"))
        assert is_error(resp)
        assert resp["message"] == "id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-record-r2t4-return — stored status/date stamp
# ---------------------------------------------------------------------------

class TestRecordR2t4ReturnDepth:
    def test_return_marks_the_calculation_returned_with_exact_date(self, fx):
        conn = fx["conn"]
        # No ledger legs: a status/date stamp on the calculation, never journals.
        package_id = _package(fx)
        calc_id = _r2t4(fx, package_id)
        assert tuple(conn.execute(
            "SELECT status, institution_return_due_date, institution_return_date "
            "FROM finaid_r2t4_calculation WHERE id = ?", (calc_id,)).fetchone()) == (
            "calculated", "2025-11-19", "")
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-record-r2t4-return"], conn, ns(
            id=calc_id, institution_return_date="2025-10-20"))
        assert is_ok(resp), resp
        assert resp["document_status"] == "returned"
        assert tuple(conn.execute(
            "SELECT status, institution_return_due_date, institution_return_date "
            "FROM finaid_r2t4_calculation WHERE id = ?", (calc_id,)).fetchone()) == (
            "returned", "2025-11-19", "2025-10-20")
        _unchanged_except(before, _snapshot(conn), {"finaid_r2t4_calculation"})

    def test_return_reports_ok_for_an_unknown_calculation_without_writing(self, fx):
        conn = fx["conn"]
        # KNOWN BEHAVIOUR (not fixed): the handler updates without checking the
        # row exists, so an unknown id reports ok and writes nothing.
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-record-r2t4-return"], conn, ns(
            id="no-such-calculation", institution_return_date="2025-10-20"))
        assert is_ok(resp), resp
        assert resp["document_status"] == "returned"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_r2t4_calculation").fetchone()[0] == 0

    def test_return_refuses_a_missing_id_and_writes_nothing(self, fx):
        conn = fx["conn"]
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-record-r2t4-return"], conn, ns(
            id=None, institution_return_date="2025-10-20"))
        assert is_error(resp)
        assert resp["message"] == "id or r2t4_id is required"
        assert _snapshot(conn) == before


# ---------------------------------------------------------------------------
# finaid-record-r2t4-return-disbursement — stored return row + calc stamp
# ---------------------------------------------------------------------------

class TestRecordR2t4ReturnDisbursementDepth:
    def test_return_disbursement_writes_exact_row_and_stamps_calculation(self, fx):
        conn = fx["conn"]
        # No ledger legs: a return row plus a date stamp, never journals.
        package_id = _package(fx)
        award_id = _award(fx, package_id)
        _accept(fx, award_id, "4000.00")
        assert is_ok(_disburse(fx, award_id, "4000.00"))
        calc_id = _r2t4(fx, package_id)
        before = _snapshot(conn)
        resp = call_action(
            FA_ACTIONS["finaid-record-r2t4-return-disbursement"], conn, ns(
                award_id=award_id, r2t4_id=calc_id, amount="1200.00",
                disbursement_date="2025-10-20", company_id=fx["company_id"]))
        assert is_ok(resp), resp
        assert resp["type"] == "return"
        rows = conn.execute(
            "SELECT disbursement_type, disbursement_number, amount, "
            "disbursement_date, award_package_id, student_id, company_id, "
            "disbursed_by, cod_status, is_credit_balance, "
            "credit_balance_returned_date "
            "FROM finaid_disbursement WHERE award_id = ? "
            "ORDER BY disbursement_date", (award_id,)).fetchall()
        assert [tuple(row) for row in rows] == [
            ("disbursement", 1, "4000.00", "2025-09-02", package_id,
             fx["student_id"], fx["company_id"], "bursar", "", 0, ""),
            ("return", 1, "1200.00", "2025-10-20", package_id,
             fx["student_id"], fx["company_id"], "", "", 0, ""),
        ]
        assert Decimal(rows[1][2]) == Decimal("1200.00")
        assert tuple(conn.execute(
            "SELECT status, institution_return_due_date, institution_return_date "
            "FROM finaid_r2t4_calculation WHERE id = ?", (calc_id,)).fetchone()) == (
            "calculated", "2025-11-19", "2025-10-20")
        assert conn.execute(
            "SELECT disbursed_amount FROM finaid_award WHERE id = ?",
            (award_id,)).fetchone()[0] == "4000.00"
        _unchanged_except(before, _snapshot(conn),
                          {"finaid_disbursement", "finaid_r2t4_calculation"})

    def test_return_disbursement_refuses_a_non_positive_amount_and_writes_nothing(self, fx):
        conn = fx["conn"]
        package_id = _package(fx)
        award_id = _award(fx, package_id)
        _accept(fx, award_id, "4000.00")
        assert is_ok(_disburse(fx, award_id, "4000.00"))
        calc_id = _r2t4(fx, package_id)
        before = _snapshot(conn)
        resp = call_action(
            FA_ACTIONS["finaid-record-r2t4-return-disbursement"], conn, ns(
                award_id=award_id, r2t4_id=calc_id, amount="0.00",
                disbursement_date="2025-10-20", company_id=fx["company_id"]))
        assert is_error(resp)
        assert resp["message"] == "amount must be greater than zero"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_disbursement").fetchone()[0] == 1
        assert conn.execute(
            "SELECT institution_return_date FROM finaid_r2t4_calculation "
            "WHERE id = ?", (calc_id,)).fetchone()[0] == ""


# ---------------------------------------------------------------------------
# finaid-submit-sap-appeal — stored appeal row
# ---------------------------------------------------------------------------

class TestSubmitSapAppealDepth:
    def test_appeal_writes_exact_row_and_leaves_evaluation_suspended(self, fx):
        conn = fx["conn"]
        # No ledger legs and no audit row: one appeal row only, never journals.
        eval_id = _fsp_evaluation(fx)
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-submit-sap-appeal"], conn, ns(
            sap_evaluation_id=eval_id, student_id=fx["student_id"],
            company_id=fx["company_id"], appeal_reason="illness",
            reason_narrative="hospitalized in November",
            academic_plan="retake failed courses",
            supporting_documents='["note.pdf"]', submitted_date="2025-12-21"))
        assert is_ok(resp), resp
        assert resp["document_status"] == "submitted"
        row = conn.execute(
            "SELECT sap_evaluation_id, student_id, submitted_date, appeal_reason, "
            "reason_narrative, academic_plan, supporting_documents, status, "
            "company_id FROM finaid_sap_appeal WHERE id = ?",
            (resp["id"],)).fetchone()
        assert tuple(row) == (eval_id, fx["student_id"], "2025-12-21", "illness",
                              "hospitalized in November", "retake failed courses",
                              '["note.pdf"]', "submitted", fx["company_id"])
        assert conn.execute(
            "SELECT sap_status FROM finaid_sap_evaluation WHERE id = ?",
            (eval_id,)).fetchone()[0] == "FSP"
        _unchanged_except(before, _snapshot(conn), {"finaid_sap_appeal"})

    def test_appeal_refuses_a_missing_reason_and_writes_nothing(self, fx):
        conn = fx["conn"]
        eval_id = _fsp_evaluation(fx)
        before = _snapshot(conn)
        resp = call_action(FA_ACTIONS["finaid-submit-sap-appeal"], conn, ns(
            sap_evaluation_id=eval_id, student_id=fx["student_id"],
            company_id=fx["company_id"], appeal_reason=None,
            reason_narrative="", academic_plan="", supporting_documents="[]",
            submitted_date="2025-12-21"))
        assert is_error(resp)
        assert resp["message"] == ("sap_evaluation_id, student_id, company_id, "
                                   "and appeal_reason are required")
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_sap_appeal").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# finaid-submit-scholarship-application — stored application row + audit row
# ---------------------------------------------------------------------------

class TestSubmitScholarshipApplicationDepth:
    def test_application_writes_exact_row_plus_one_audit_row(self, fx):
        conn = fx["conn"]
        # No ledger legs: one application row plus one audit row, never journals.
        program_id = _scholarship_program(fx)
        before = _snapshot(conn)
        resp = call_action(
            SCHOL_ACTIONS["finaid-submit-scholarship-application"], conn, ns(
                scholarship_program_id=program_id, student_id=fx["student_id"],
                aid_year_id=fx["aid_year_id"], company_id=fx["company_id"],
                essay_response="Why I merit this award",
                gpa_at_application="3.60", submission_date="2025-03-10"))
        assert is_ok(resp), resp
        assert resp["document_status"] == "submitted"
        row = conn.execute(
            "SELECT scholarship_program_id, student_id, aid_year_id, "
            "submission_date, status, essay_response, gpa_at_application, "
            "award_amount, company_id "
            "FROM finaid_scholarship_application WHERE id = ?",
            (resp["id"],)).fetchone()
        assert tuple(row) == (program_id, fx["student_id"], fx["aid_year_id"],
                              "2025-03-10", "submitted",
                              "Why I merit this award", "3.60", "0",
                              fx["company_id"])
        assert Decimal(row[6]) == Decimal("3.60")
        assert Decimal(row[7]) == Decimal("0")
        audit = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ?", (resp["id"],)).fetchall()
        assert [tuple(entry) for entry in audit] == [
            ("finaid-educlaw-finaid", "finaid-submit-scholarship-application",
             "finaid_scholarship_application", resp["id"])]
        _unchanged_except(before, _snapshot(conn),
                          {"finaid_scholarship_application", "audit_log"})

    def test_second_application_for_the_same_triple_is_accepted(self, fx):
        conn = fx["conn"]
        # KNOWN BEHAVIOUR (not fixed): the duplicate refusal in the handler is
        # unreachable because no UNIQUE index covers
        # (scholarship_program_id, student_id, aid_year_id), so a second
        # identical application succeeds with a second row.
        program_id = _scholarship_program(fx)
        first = call_action(
            SCHOL_ACTIONS["finaid-submit-scholarship-application"], conn, ns(
                scholarship_program_id=program_id, student_id=fx["student_id"],
                aid_year_id=fx["aid_year_id"], company_id=fx["company_id"],
                essay_response="first", gpa_at_application="3.60",
                submission_date="2025-03-10"))
        assert is_ok(first), first
        second = call_action(
            SCHOL_ACTIONS["finaid-submit-scholarship-application"], conn, ns(
                scholarship_program_id=program_id, student_id=fx["student_id"],
                aid_year_id=fx["aid_year_id"], company_id=fx["company_id"],
                essay_response="second", gpa_at_application="3.10",
                submission_date="2025-03-11"))
        assert is_ok(second), second
        assert second["id"] != first["id"]
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_scholarship_application "
            "WHERE scholarship_program_id = ? AND student_id = ? "
            "AND aid_year_id = ?",
            (program_id, fx["student_id"], fx["aid_year_id"])).fetchone()[0] == 2

    def test_application_refuses_a_missing_program_id_and_writes_nothing(self, fx):
        conn = fx["conn"]
        before = _snapshot(conn)
        resp = call_action(
            SCHOL_ACTIONS["finaid-submit-scholarship-application"], conn, ns(
                scholarship_program_id=None, student_id=fx["student_id"],
                aid_year_id=fx["aid_year_id"], company_id=fx["company_id"],
                essay_response="essay", gpa_at_application="3.60",
                submission_date="2025-03-10"))
        assert is_error(resp)
        assert resp["message"] == "--scholarship-program-id is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_scholarship_application").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# finaid-submit-work-study-timesheet — stored timesheet row + audit row
# ---------------------------------------------------------------------------

class TestSubmitWorkStudyTimesheetDepth:
    def test_timesheet_writes_exact_earnings_math_plus_one_audit_row(self, fx):
        conn = fx["conn"]
        # No ledger legs: one timesheet row plus one audit row, never journals.
        job_id = _ws_job(fx)
        assignment_id = _ws_assignment(fx, job_id)
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-submit-work-study-timesheet"], conn, ns(
                assignment_id=assignment_id, student_id=fx["student_id"],
                company_id=fx["company_id"], pay_period_start="2025-09-01",
                pay_period_end="2025-09-15", hours_worked="10",
                submission_date="2025-09-16"))
        assert is_ok(resp), resp
        assert resp["hours_worked"] == "10"
        assert resp["earnings"] == "120.00"
        assert resp["cumulative_earnings"] == "120.00"
        assert resp["supervisor_approval_status"] == "pending"
        row = conn.execute(
            "SELECT assignment_id, student_id, pay_period_start, pay_period_end, "
            "hours_worked, earnings, cumulative_earnings, submission_date, "
            "supervisor_approval_status, payroll_exported, company_id "
            "FROM finaid_work_study_timesheet WHERE id = ?", (resp["id"],)).fetchone()
        assert tuple(row) == (assignment_id, fx["student_id"], "2025-09-01",
                              "2025-09-15", "10", "120.00", "120.00",
                              "2025-09-16", "pending", 0, fx["company_id"])
        assert Decimal(row[5]) == Decimal("10") * Decimal("12.00")
        assert Decimal(row[6]) == Decimal("120.00")
        audit = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ?", (resp["id"],)).fetchall()
        assert [tuple(entry) for entry in audit] == [
            ("finaid-educlaw-finaid", "finaid-submit-work-study-timesheet",
             "finaid_work_study_timesheet", resp["id"])]
        _unchanged_except(before, _snapshot(conn),
                          {"finaid_work_study_timesheet", "audit_log"})
        duplicate = call_action(
            WS_ACTIONS["finaid-submit-work-study-timesheet"], conn, ns(
                assignment_id=assignment_id, student_id=fx["student_id"],
                company_id=fx["company_id"], pay_period_start="2025-09-01",
                pay_period_end="2025-09-15", hours_worked="5",
                submission_date="2025-09-16"))
        assert is_error(duplicate)
        assert duplicate["message"] == (
            "Timesheet already exists for assignment %s "
            "and pay period starting 2025-09-01" % assignment_id)
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_work_study_timesheet").fetchone()[0] == 1

    def test_timesheet_refuses_a_missing_assignment_and_writes_nothing(self, fx):
        conn = fx["conn"]
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-submit-work-study-timesheet"], conn, ns(
                assignment_id=None, student_id=fx["student_id"],
                company_id=fx["company_id"], pay_period_start="2025-09-01",
                pay_period_end="2025-09-15", hours_worked="10",
                submission_date="2025-09-16"))
        assert is_error(resp)
        assert resp["message"] == "--assignment-id is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_work_study_timesheet").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# finaid-terminate-scholarship-program — stored deactivation + audit row
# ---------------------------------------------------------------------------

class TestTerminateScholarshipProgramDepth:
    def test_terminate_sets_is_active_zero_and_leaves_sibling_alone(self, fx):
        conn = fx["conn"]
        # No ledger legs: a flag flip plus one audit row, never journals.
        program_id = _scholarship_program(fx, name="M408 Merit", code="M408-TERM")
        sibling_id = _scholarship_program(fx, name="Sibling Fund", code="SIB-FUND")
        before = _snapshot(conn)
        resp = call_action(
            SCHOL_ACTIONS["finaid-terminate-scholarship-program"], conn, ns(
                id=program_id))
        assert is_ok(resp), resp
        assert resp["is_active"] == 0
        row = conn.execute(
            "SELECT name, code, is_active, annual_budget, company_id "
            "FROM finaid_scholarship_program WHERE id = ?", (program_id,)).fetchone()
        assert tuple(row) == ("M408 Merit", "M408-TERM", 0, "10000.00",
                              fx["company_id"])
        assert Decimal(row[3]) == Decimal("10000.00")
        assert conn.execute(
            "SELECT is_active FROM finaid_scholarship_program WHERE id = ?",
            (sibling_id,)).fetchone()[0] == 1
        audit = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ? ORDER BY rowid", (program_id,)).fetchall()
        assert [tuple(entry) for entry in audit][-1] == (
            "finaid-educlaw-finaid", "finaid-deactivate-scholarship-program",
            "finaid_scholarship_program", program_id)
        _unchanged_except(before, _snapshot(conn),
                          {"finaid_scholarship_program", "audit_log"})

    def test_terminate_refuses_a_missing_id_and_writes_nothing(self, fx):
        conn = fx["conn"]
        program_id = _scholarship_program(fx)
        before = _snapshot(conn)
        resp = call_action(
            SCHOL_ACTIONS["finaid-terminate-scholarship-program"], conn, ns(
                id=None))
        assert is_error(resp)
        assert resp["message"] == "--id is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT is_active FROM finaid_scholarship_program WHERE id = ?",
            (program_id,)).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# finaid-terminate-work-study-assignment — stored termination + freed seat
# ---------------------------------------------------------------------------

class TestTerminateWorkStudyAssignmentDepth:
    def test_terminate_ends_assignment_and_frees_exactly_one_seat(self, fx):
        conn = fx["conn"]
        # No ledger legs: an assignment status plus the job seat, one audit row.
        job_id = _ws_job(fx)
        assignment_id = _ws_assignment(fx, job_id)
        assert tuple(conn.execute(
            "SELECT filled_positions, status FROM finaid_work_study_job "
            "WHERE id = ?", (job_id,)).fetchone()) == (1, "filled")
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-terminate-work-study-assignment"], conn, ns(
                id=assignment_id))
        assert is_ok(resp), resp
        assert resp["document_status"] == "terminated"
        assert conn.execute(
            "SELECT status FROM finaid_work_study_assignment WHERE id = ?",
            (assignment_id,)).fetchone()[0] == "terminated"
        assert tuple(conn.execute(
            "SELECT filled_positions, status FROM finaid_work_study_job "
            "WHERE id = ?", (job_id,)).fetchone()) == (0, "open")
        audit = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ?", (assignment_id,)).fetchall()
        assert [tuple(entry) for entry in audit][-1] == (
            "finaid-educlaw-finaid", "finaid-terminate-work-study-assignment",
            "finaid_work_study_assignment", assignment_id)
        _unchanged_except(before, _snapshot(conn),
                          {"finaid_work_study_assignment",
                           "finaid_work_study_job", "audit_log"})

    def test_terminate_refuses_an_unknown_assignment_and_writes_nothing(self, fx):
        conn = fx["conn"]
        job_id = _ws_job(fx)
        assignment_id = _ws_assignment(fx, job_id)
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-terminate-work-study-assignment"], conn, ns(
                id="no-such-assignment"))
        assert is_error(resp)
        assert resp["message"] == "Work study assignment no-such-assignment not found"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT status FROM finaid_work_study_assignment WHERE id = ?",
            (assignment_id,)).fetchone()[0] == "active"
        assert tuple(conn.execute(
            "SELECT filled_positions, status FROM finaid_work_study_job "
            "WHERE id = ?", (job_id,)).fetchone()) == (1, "filled")


# ---------------------------------------------------------------------------
# finaid-terminate-work-study-job — stored close
# ---------------------------------------------------------------------------

class TestTerminateWorkStudyJobDepth:
    def test_terminate_closes_the_job_and_keeps_seat_counts(self, fx):
        conn = fx["conn"]
        # No ledger legs and no audit row from this handler: a status flip only.
        job_id = _ws_job(fx, title="Closing Job", total_positions=2)
        other_id = _ws_job(fx, title="Other Job", total_positions=2)
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-terminate-work-study-job"], conn, ns(id=job_id))
        assert is_ok(resp), resp
        assert resp["document_status"] == "closed"
        assert tuple(conn.execute(
            "SELECT status, filled_positions, total_positions "
            "FROM finaid_work_study_job WHERE id = ?", (job_id,)).fetchone()) == (
            "closed", 0, 2)
        assert tuple(conn.execute(
            "SELECT status, filled_positions FROM finaid_work_study_job "
            "WHERE id = ?", (other_id,)).fetchone()) == ("open", 0)
        _unchanged_except(before, _snapshot(conn), {"finaid_work_study_job"})

    def test_terminate_refuses_a_missing_id_and_writes_nothing(self, fx):
        conn = fx["conn"]
        job_id = _ws_job(fx)
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-terminate-work-study-job"], conn, ns(id=None))
        assert is_error(resp)
        assert resp["message"] == "--id is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT status FROM finaid_work_study_job WHERE id = ?",
            (job_id,)).fetchone()[0] == "open"


# ---------------------------------------------------------------------------
# finaid-list-work-study-timesheets — read-only list mirroring stored rows
# ---------------------------------------------------------------------------

class TestListWorkStudyTimesheetsDepth:
    def _two_timesheets(self, fx):
        conn = fx["conn"]
        job_id = _ws_job(fx)
        assignment_id = _ws_assignment(fx, job_id)
        first = call_action(
            WS_ACTIONS["finaid-submit-work-study-timesheet"], conn, ns(
                assignment_id=assignment_id, student_id=fx["student_id"],
                company_id=fx["company_id"], pay_period_start="2025-09-01",
                pay_period_end="2025-09-15", hours_worked="10",
                submission_date="2025-09-16"))
        assert is_ok(first), first
        second = call_action(
            WS_ACTIONS["finaid-submit-work-study-timesheet"], conn, ns(
                assignment_id=assignment_id, student_id=fx["student_id"],
                company_id=fx["company_id"], pay_period_start="2025-09-16",
                pay_period_end="2025-09-30", hours_worked="5",
                submission_date="2025-10-01"))
        assert is_ok(second), second
        return assignment_id, first["id"], second["id"]

    def test_list_returns_both_rows_exact_and_writes_nothing(self, fx):
        conn = fx["conn"]
        # No ledger legs: a read-only list; the table must be byte-identical.
        assignment_id, first_id, second_id = self._two_timesheets(fx)
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-list-work-study-timesheets"], conn, ns(
                company_id=fx["company_id"], student_id=None,
                assignment_id=None, status=None, limit=50, offset=0))
        assert is_ok(resp), resp
        assert resp["count"] == 2
        assert [row["id"] for row in resp["timesheets"]] == [second_id, first_id]
        assert [(row["pay_period_start"], row["hours_worked"],
                 row["earnings"]) for row in resp["timesheets"]] == [
            ("2025-09-16", "5", "60.00"),
            ("2025-09-01", "10", "120.00"),
        ]
        assert Decimal(resp["timesheets"][0]["earnings"]) == Decimal("60.00")
        assert Decimal(resp["timesheets"][1]["earnings"]) == Decimal("120.00")
        filtered = call_action(
            WS_ACTIONS["finaid-list-work-study-timesheets"], conn, ns(
                company_id=fx["company_id"], student_id=fx["student_id"],
                assignment_id=assignment_id, status=None, limit=50, offset=0))
        assert is_ok(filtered), filtered
        assert filtered["count"] == 2
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_work_study_timesheet").fetchone()[0] == 2

    def test_list_refuses_a_missing_company_and_writes_nothing(self, fx):
        conn = fx["conn"]
        self._two_timesheets(fx)
        before = _snapshot(conn)
        resp = call_action(
            WS_ACTIONS["finaid-list-work-study-timesheets"], conn, ns(
                company_id=None, student_id=None, assignment_id=None,
                status=None, limit=50, offset=0))
        assert is_error(resp)
        assert resp["message"] == "--company-id is required"
        assert _snapshot(conn) == before
