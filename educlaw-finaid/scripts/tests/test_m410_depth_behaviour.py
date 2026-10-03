"""Depth cover for eight finaid update actions previously tested for routing only.

Each action below was previously covered only by a routability contract test
(``testing/integration/contract/test_educlaw_finaid_contract.py`` asserts the
action name resolves, never what it writes). The tests here prove what each
action actually does to the database: the exact row changed, from what to
what, the rows that must NOT have changed, and one input-validation refusal
that must leave the database byte-identical.

Actions covered (all assert stored rows; none reaches the ledger):
  finaid-update-sap-appeal, finaid-update-scholarship-application,
  finaid-update-scholarship-program, finaid-update-verification-document,
  finaid-update-verification-request, finaid-update-work-study-assignment,
  finaid-update-work-study-job, finaid-update-work-study-timesheet.

Ledger note (applies to every test in this file): none of these eight actions
reaches the general ledger. The financial_aid and work_study updates write
only their own finaid_* row and no audit_log row; the scholarships updates
write their finaid_* row plus one audit_log row. No debit/credit legs exist,
so no ledger assertions are made here; a later reader must not add ledger
assertions that cannot hold. Money is compared as exact Decimal strings,
never float, never round.

Known defects documented (not fixed) -- see CHANGES.md:
  D1. finaid-update-sap-appeal, finaid-update-verification-request and
      finaid-update-verification-document report {"updated": True} for an
      unknown id without writing anything.
  D2. The same three actions let an invalid enum value escape as a raw
      sqlite3.IntegrityError instead of an error envelope.
"""
import importlib.util
import json
import os
import sqlite3
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


def _row(conn, table, row_id):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _request(s, group="V1"):
    r = call_action(FA_ACTIONS["finaid-create-verification-request"], s["conn"], ns(
        isir_id=s["isir_id"], student_id=s["student_id"], company_id=s["company_id"],
        verification_group=group, deadline_date="2025-06-01",
        requested_date="2025-05-01", assigned_to=None))
    assert is_ok(r), r
    return r["id"]


def _fsp_evaluation(s):
    r = call_action(FA_ACTIONS["finaid-generate-sap-evaluation"], s["conn"], ns(
        student_id=s["student_id"], academic_term_id=s["term_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        gpa_earned="1.0", gpa_threshold="2.00",
        credits_attempted="12", credits_completed="3",
        evaluation_date="2025-12-20"))
    assert is_ok(r), r
    assert r["sap_status"] == "FSP"
    return r["id"]


def _sap_appeal(s, eval_id):
    r = call_action(FA_ACTIONS["finaid-submit-sap-appeal"], s["conn"], ns(
        sap_evaluation_id=eval_id, student_id=s["student_id"],
        company_id=s["company_id"], appeal_reason="illness",
        reason_narrative="flu during finals", academic_plan="retake failed courses",
        submitted_date="2025-12-21"))
    assert is_ok(r), r
    return r["id"]


def _sch_program(s):
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


def _sch_application(s, program_id):
    r = call_action(SCH_ACTIONS["finaid-submit-scholarship-application"], s["conn"], ns(
        scholarship_program_id=program_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        essay_response="first essay", gpa_at_application="3.5",
        submission_date="2025-05-01"))
    assert is_ok(r), r
    return r["id"]


def _package(s):
    r = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"],
        isir_id=s["isir_id"], cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", packaged_by="counselor", notes=None))
    assert is_ok(r), r
    return r["id"]


def _fws_award(s, pkg_id, offered="3000.00"):
    r = call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type="fws", aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None,
        notes=None))
    assert is_ok(r), r
    return r["id"]


def _ws_job(s, pay_rate="12.00", hours="15"):
    r = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
        company_id=s["company_id"], aid_year_id=s["aid_year_id"],
        job_title="Library Assistant", department_id=None, supervisor_id=None,
        job_type="on_campus", pay_rate=pay_rate, hours_per_week=hours,
        total_positions=3, description=None))
    assert is_ok(r), r
    return r["id"]


def _ws_assign(s, award_id, job_id, award_limit="3000"):
    r = call_action(WS_ACTIONS["finaid-assign-student-to-job"], s["conn"], ns(
        student_id=s["student_id"], award_id=award_id, job_id=job_id,
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-08-25",
        end_date="2025-12-20", award_limit=award_limit))
    assert is_ok(r), r
    return r["id"]


def _ws_timesheet(s, assign_id, hours="20", period_start="2025-09-01"):
    r = call_action(WS_ACTIONS["finaid-submit-work-study-timesheet"], s["conn"], ns(
        assignment_id=assign_id, student_id=s["student_id"],
        company_id=s["company_id"], pay_period_start=period_start,
        pay_period_end="2025-09-15", hours_worked=hours,
        submission_date="2025-09-16"))
    assert is_ok(r), r
    return r["id"]


# ---------------------------------------------------------------------------
# finaid-update-sap-appeal -- stored row
# ---------------------------------------------------------------------------

class TestUpdateSapAppealDepth:
    def test_moves_submitted_to_under_review_with_exact_review_fields(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row only.
        appeal_id = _sap_appeal(s, _fsp_evaluation(s))
        before = _row(conn, "finaid_sap_appeal", appeal_id)
        assert before["status"] == "submitted"
        assert before["reviewed_by"] == ""
        r = call_action(FA_ACTIONS["finaid-update-sap-appeal"], conn, ns(
            id=appeal_id, status="under_review", reviewed_by="dean-1",
            decision_rationale="docs verified", reviewed_date="2025-12-22"))
        assert is_ok(r), r
        assert r["id"] == appeal_id
        assert r["updated"] is True
        after = _row(conn, "finaid_sap_appeal", appeal_id)
        assert after["status"] == "under_review"
        assert after["reviewed_by"] == "dean-1"
        assert after["decision_rationale"] == "docs verified"
        assert after["reviewed_date"] == "2025-12-22"
        # Untouched: the appeal's identity, reason, narrative, plan and probation.
        for key in ("sap_evaluation_id", "student_id", "submitted_date",
                    "appeal_reason", "reason_narrative", "academic_plan",
                    "supporting_documents", "probation_conditions",
                    "company_id"):
            assert after[key] == before[key], key
        assert _count(conn, "finaid_sap_appeal") == 1
        # The appealed evaluation still reads FSP; the update moves only the appeal.
        assert _row(conn, "finaid_sap_evaluation",
                    before["sap_evaluation_id"])["sap_status"] == "FSP"
        # No ledger legs and no audit row: only the appeal row is written.
        assert _count(conn, "audit_log") == 0

    def test_refuses_no_fields_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        appeal_id = _sap_appeal(s, _fsp_evaluation(s))
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-sap-appeal"], conn, ns(
            id=appeal_id))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_sap_appeal", appeal_id)["status"] == "submitted"

    def test_unknown_id_reports_updated_without_writing_known_defect(self, env):
        # KNOWN DEFECT D1 (not fixed): an unknown id reports success instead
        # of refusing, so a caller cannot tell nothing was written.
        s, conn = env, env["conn"]
        appeal_id = _sap_appeal(s, _fsp_evaluation(s))
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-sap-appeal"], conn, ns(
            id="no-such-appeal", status="under_review"))
        assert is_ok(r), r
        assert r["updated"] is True
        assert _row(conn, "finaid_sap_appeal", "no-such-appeal") is None
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_sap_appeal", appeal_id)["status"] == "submitted"

    def test_invalid_status_escapes_as_integrity_error_known_defect(self, env):
        # KNOWN DEFECT D2 (not fixed): an invalid status escapes as a raw
        # sqlite3.IntegrityError instead of an error envelope. Expected: an
        # error response naming the bad value; observed: the CHECK constraint
        # exception propagates out of the action.
        s, conn = env, env["conn"]
        appeal_id = _sap_appeal(s, _fsp_evaluation(s))
        with pytest.raises(sqlite3.IntegrityError):
            call_action(FA_ACTIONS["finaid-update-sap-appeal"], conn, ns(
                id=appeal_id, status="bogus"))
        conn.rollback()
        assert _row(conn, "finaid_sap_appeal", appeal_id)["status"] == "submitted"


# ---------------------------------------------------------------------------
# finaid-update-scholarship-application -- stored row
# ---------------------------------------------------------------------------

class TestUpdateScholarshipApplicationDepth:
    def test_revises_essay_and_gpa_with_exact_decimal_strings(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row plus one
        # audit_log row, never journals.
        program_id = _sch_program(s)
        app_id = _sch_application(s, program_id)
        before = _row(conn, "finaid_scholarship_application", app_id)
        assert before["essay_response"] == "first essay"
        assert before["gpa_at_application"] == "3.5"
        r = call_action(SCH_ACTIONS["finaid-update-scholarship-application"], conn, ns(
            id=app_id, essay_response="revised essay", gpa_at_application="3.75"))
        assert is_ok(r), r
        assert r["id"] == app_id
        after = _row(conn, "finaid_scholarship_application", app_id)
        assert after["essay_response"] == "revised essay"
        assert after["gpa_at_application"] == "3.75"
        assert Decimal(after["gpa_at_application"]) == Decimal("3.75")
        # Untouched: links, dates, status and the (unawarded) amount.
        for key in ("scholarship_program_id", "student_id", "aid_year_id",
                    "submission_date", "status", "award_amount", "company_id"):
            assert after[key] == before[key], key
        assert _count(conn, "finaid_scholarship_application") == 1
        # The program row the application points at is untouched.
        assert _row(conn, "finaid_scholarship_program",
                    program_id)["award_amount"] == "2000.00"
        # Exactly one audit row records this update.
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ? AND entity_id = ?",
            ("finaid-update-scholarship-application", app_id)).fetchone()[0] == 1

    def test_refuses_an_invalid_gpa_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        app_id = _sch_application(s, _sch_program(s))
        before = _snapshot(conn)
        r = call_action(SCH_ACTIONS["finaid-update-scholarship-application"], conn, ns(
            id=app_id, gpa_at_application="not-a-number"))
        assert is_error(r)
        assert r["message"].startswith("Invalid gpa_at_application value:")
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_scholarship_application",
                    app_id)["gpa_at_application"] == "3.5"


# ---------------------------------------------------------------------------
# finaid-update-scholarship-program -- stored row
# ---------------------------------------------------------------------------

class TestUpdateScholarshipProgramDepth:
    def test_updates_text_counts_and_exact_money_with_budget_recomputed(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row plus one
        # audit_log row, never journals.
        program_id = _sch_program(s)
        before = _row(conn, "finaid_scholarship_program", program_id)
        assert before["award_amount"] == "2000.00"
        assert before["annual_budget"] == "50000.00"
        assert before["budget_remaining"] == "50000.00"
        r = call_action(SCH_ACTIONS["finaid-update-scholarship-program"], conn, ns(
            id=program_id, description="Updated desc", max_recipients=20,
            award_amount="2500", annual_budget="60000"))
        assert is_ok(r), r
        assert r["id"] == program_id
        after = _row(conn, "finaid_scholarship_program", program_id)
        assert after["description"] == "Updated desc"
        assert after["max_recipients"] == 20
        assert after["award_amount"] == "2500"
        assert Decimal(after["award_amount"]) == Decimal("2500")
        assert after["annual_budget"] == "60000.00"
        assert Decimal(after["annual_budget"]) == Decimal("60000.00")
        # Nothing spent yet, so the remaining budget tracks the new budget.
        assert after["budget_remaining"] == "60000.00"
        assert Decimal(after["budget_remaining"]) == Decimal("60000.00")
        # Untouched: identity, type, bounds, deadline and criteria.
        for key in ("name", "code", "min_award", "max_award",
                    "application_deadline", "eligibility_criteria",
                    "company_id"):
            assert after[key] == before[key], key
        assert _count(conn, "finaid_scholarship_program") == 1
        assert _count(conn, "finaid_scholarship_application") == 0
        # Exactly one audit row records this update.
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ? AND entity_id = ?",
            ("finaid-update-scholarship-program", program_id)).fetchone()[0] == 1

    def test_refuses_an_invalid_budget_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        program_id = _sch_program(s)
        before = _snapshot(conn)
        r = call_action(SCH_ACTIONS["finaid-update-scholarship-program"], conn, ns(
            id=program_id, annual_budget="not-money"))
        assert is_error(r)
        assert r["message"].startswith("Invalid annual_budget value:")
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_scholarship_program",
                    program_id)["annual_budget"] == "50000.00"


# ---------------------------------------------------------------------------
# finaid-update-verification-document -- stored row
# ---------------------------------------------------------------------------

class TestUpdateVerificationDocumentDepth:
    def test_marks_one_document_submitted_with_exact_reference(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row only.
        req_id = _request(s)
        docs = conn.execute(
            "SELECT id FROM finaid_verification_document "
            "WHERE verification_request_id = ? ORDER BY document_type",
            (req_id,)).fetchall()
        assert len(docs) == 3
        doc_id = docs[0][0]
        before = _row(conn, "finaid_verification_document", doc_id)
        assert before["submission_status"] == "not_submitted"
        r = call_action(FA_ACTIONS["finaid-update-verification-document"], conn, ns(
            id=doc_id, submission_status="submitted",
            document_reference="scan-001", submitted_date="2025-05-10"))
        assert is_ok(r), r
        assert r["id"] == doc_id
        assert r["updated"] is True
        after = _row(conn, "finaid_verification_document", doc_id)
        assert after["submission_status"] == "submitted"
        assert after["document_reference"] == "scan-001"
        assert after["submitted_date"] == "2025-05-10"
        # Untouched: type, review fields and ownership.
        for key in ("document_type", "reviewed_by", "reviewed_date",
                    "rejection_reason", "student_id",
                    "verification_request_id", "company_id"):
            assert after[key] == before[key], key
        # The two sibling documents are still not submitted.
        siblings = conn.execute(
            "SELECT submission_status FROM finaid_verification_document "
            "WHERE verification_request_id = ? AND id != ?",
            (req_id, doc_id)).fetchall()
        assert [t[0] for t in siblings] == ["not_submitted", "not_submitted"]
        # The parent request row is untouched by a document update.
        assert _row(conn, "finaid_verification_request",
                    req_id)["status"] == "initiated"
        # No ledger legs and no audit row: only the document row is written.
        assert _count(conn, "audit_log") == 0

    def test_refuses_no_fields_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        req_id = _request(s)
        doc_id = conn.execute(
            "SELECT id FROM finaid_verification_document "
            "WHERE verification_request_id = ?", (req_id,)).fetchone()[0]
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-verification-document"], conn, ns(
            id=doc_id))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_verification_document",
                    doc_id)["submission_status"] == "not_submitted"

    def test_unknown_id_reports_updated_without_writing_known_defect(self, env):
        # KNOWN DEFECT D1 (not fixed): an unknown id reports success instead
        # of refusing, so a caller cannot tell nothing was written.
        s, conn = env, env["conn"]
        req_id = _request(s)
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-verification-document"], conn, ns(
            id="no-such-document", submission_status="accepted"))
        assert is_ok(r), r
        assert r["updated"] is True
        assert _row(conn, "finaid_verification_document", "no-such-document") is None
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_verification_document") == 3
        assert _row(conn, "finaid_verification_request",
                    req_id)["status"] == "initiated"


# ---------------------------------------------------------------------------
# finaid-update-verification-request -- stored row
# ---------------------------------------------------------------------------

class TestUpdateVerificationRequestDepth:
    def test_moves_initiated_to_in_review_with_exact_assignment(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row only.
        req_id = _request(s)
        before = _row(conn, "finaid_verification_request", req_id)
        assert before["status"] == "initiated"
        assert before["discrepancy_found"] == 0
        r = call_action(FA_ACTIONS["finaid-update-verification-request"], conn, ns(
            id=req_id, status="in_review", assigned_to="counselor-1",
            discrepancy_found=1, discrepancy_notes="checking docs"))
        assert is_ok(r), r
        assert r["id"] == req_id
        assert r["updated"] is True
        after = _row(conn, "finaid_verification_request", req_id)
        assert after["status"] == "in_review"
        assert after["assigned_to"] == "counselor-1"
        assert after["discrepancy_found"] == 1
        assert after["discrepancy_notes"] == "checking docs"
        # Untouched: group, dates, links and completion.
        for key in ("verification_group", "requested_date", "deadline_date",
                    "completed_date", "isir_id", "student_id", "company_id"):
            assert after[key] == before[key], key
        assert _count(conn, "finaid_verification_request") == 1
        # All three required documents are still not submitted.
        assert conn.execute(
            "SELECT COUNT(*) FROM finaid_verification_document "
            "WHERE verification_request_id = ? AND submission_status = ?",
            (req_id, "not_submitted")).fetchone()[0] == 3
        # No ledger legs and no audit row: only the request row is written.
        assert _count(conn, "audit_log") == 0

    def test_refuses_a_missing_id_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _request(s)
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-verification-request"], conn, ns(
            status="in_review"))
        assert is_error(r)
        assert r["message"] == "verification_request_id or id is required"
        assert _snapshot(conn) == before
        assert _count(conn, "finaid_verification_request") == 1

    def test_unknown_id_reports_updated_without_writing_known_defect(self, env):
        # KNOWN DEFECT D1 (not fixed): an unknown id reports success instead
        # of refusing, so a caller cannot tell nothing was written.
        s, conn = env, env["conn"]
        req_id = _request(s)
        before = _snapshot(conn)
        r = call_action(FA_ACTIONS["finaid-update-verification-request"], conn, ns(
            id="no-such-request", status="in_review"))
        assert is_ok(r), r
        assert r["updated"] is True
        assert _row(conn, "finaid_verification_request", "no-such-request") is None
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_verification_request",
                    req_id)["status"] == "initiated"


# ---------------------------------------------------------------------------
# finaid-update-work-study-assignment -- stored row
# ---------------------------------------------------------------------------

class TestUpdateWorkStudyAssignmentDepth:
    def test_extends_end_date_and_raises_limit_with_exact_money(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row only.
        pkg_id = _package(s)
        job_id = _ws_job(s)
        assign_id = _ws_assign(s, _fws_award(s, pkg_id), job_id)
        before = _row(conn, "finaid_work_study_assignment", assign_id)
        assert before["end_date"] == "2025-12-20"
        assert before["award_limit"] == "3000"
        r = call_action(WS_ACTIONS["finaid-update-work-study-assignment"], conn, ns(
            id=assign_id, end_date="2025-12-31", award_limit="3500"))
        assert is_ok(r), r
        assert r["id"] == assign_id
        assert r["updated_fields"] == ["end_date", "award_limit"]
        after = _row(conn, "finaid_work_study_assignment", assign_id)
        assert after["end_date"] == "2025-12-31"
        assert after["award_limit"] == "3500"
        assert Decimal(after["award_limit"]) == Decimal("3500")
        # Untouched: links, start, earnings-to-date and status.
        for key in ("student_id", "award_id", "job_id", "start_date",
                    "earned_to_date", "status", "company_id"):
            assert after[key] == before[key], key
        assert after["earned_to_date"] == "0.00"
        assert _count(conn, "finaid_work_study_assignment") == 1
        # The job's filled count is untouched by an assignment update.
        assert _row(conn, "finaid_work_study_job",
                    job_id)["filled_positions"] == 1
        # No ledger legs and no audit row: only the assignment row is written.
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ? AND entity_id = ?",
            ("finaid-update-work-study-assignment", assign_id)).fetchone()[0] == 0

    def test_refuses_an_unknown_assignment_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        assign_id = _ws_assign(s, _fws_award(s, pkg_id), _ws_job(s))
        before = _snapshot(conn)
        r = call_action(WS_ACTIONS["finaid-update-work-study-assignment"], conn, ns(
            id="no-such-assignment", end_date="2025-12-31"))
        assert is_error(r)
        assert r["message"] == "Work study assignment no-such-assignment not found"
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_work_study_assignment",
                    assign_id)["end_date"] == "2025-12-20"


# ---------------------------------------------------------------------------
# finaid-update-work-study-job -- stored row
# ---------------------------------------------------------------------------

class TestUpdateWorkStudyJobDepth:
    def test_retitles_and_reprices_with_exact_money(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row only.
        job_id = _ws_job(s)
        before = _row(conn, "finaid_work_study_job", job_id)
        assert before["job_title"] == "Library Assistant"
        assert before["pay_rate"] == "12.00"
        r = call_action(WS_ACTIONS["finaid-update-work-study-job"], conn, ns(
            id=job_id, job_title="Library Aide", pay_rate="13.50",
            hours_per_week="18"))
        assert is_ok(r), r
        assert r["id"] == job_id
        assert r["updated_fields"] == ["job_title", "pay_rate", "hours_per_week"]
        after = _row(conn, "finaid_work_study_job", job_id)
        assert after["job_title"] == "Library Aide"
        assert after["pay_rate"] == "13.50"
        assert Decimal(after["pay_rate"]) == Decimal("13.50")
        assert after["hours_per_week"] == "18"
        assert Decimal(after["hours_per_week"]) == Decimal("18")
        # Untouched: type, capacity, fill, status and description.
        for key in ("job_type", "total_positions", "filled_positions",
                    "status", "description", "aid_year_id", "company_id"):
            assert after[key] == before[key], key
        assert _count(conn, "finaid_work_study_job") == 1
        assert _count(conn, "finaid_work_study_assignment") == 0
        # No ledger legs and no audit row: only the job row is written.
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ? AND entity_id = ?",
            ("finaid-update-work-study-job", job_id)).fetchone()[0] == 0

    def test_refuses_an_unknown_job_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        job_id = _ws_job(s)
        before = _snapshot(conn)
        r = call_action(WS_ACTIONS["finaid-update-work-study-job"], conn, ns(
            id="no-such-job", job_title="Other"))
        assert is_error(r)
        assert r["message"] == "Work study job no-such-job not found"
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_work_study_job",
                    job_id)["job_title"] == "Library Assistant"


# ---------------------------------------------------------------------------
# finaid-update-work-study-timesheet -- stored row
# ---------------------------------------------------------------------------

class TestUpdateWorkStudyTimesheetDepth:
    def test_recomputes_earnings_from_hours_with_exact_money(self, env):
        s, conn = env, env["conn"]
        # This action does not reach the general ledger; stored row only.
        pkg_id = _package(s)
        assign_id = _ws_assign(s, _fws_award(s, pkg_id), _ws_job(s))
        ts_id = _ws_timesheet(s, assign_id, hours="20")
        before = _row(conn, "finaid_work_study_timesheet", ts_id)
        assert before["hours_worked"] == "20"
        assert before["earnings"] == "240.00"
        assert before["cumulative_earnings"] == "240.00"
        r = call_action(WS_ACTIONS["finaid-update-work-study-timesheet"], conn, ns(
            id=ts_id, hours_worked="10"))
        assert is_ok(r), r
        assert r["id"] == ts_id
        assert r["updated_fields"] == ["hours_worked", "earnings",
                                       "cumulative_earnings"]
        after = _row(conn, "finaid_work_study_timesheet", ts_id)
        # 10 hours at the job's 12.00 rate, nothing earned to date yet.
        assert after["hours_worked"] == "10"
        assert after["earnings"] == "120.00"
        assert Decimal(after["earnings"]) == Decimal("120.00")
        assert after["cumulative_earnings"] == "120.00"
        assert Decimal(after["cumulative_earnings"]) == Decimal("120.00")
        # Untouched: periods, student, approval state and export flags.
        for key in ("assignment_id", "student_id", "pay_period_start",
                    "pay_period_end", "supervisor_approval_status",
                    "submission_date", "company_id"):
            assert after[key] == before[key], key
        assert _count(conn, "finaid_work_study_timesheet") == 1
        # The assignment's earned-to-date moves only on approval, not on edit.
        assert _row(conn, "finaid_work_study_assignment",
                    assign_id)["earned_to_date"] == "0.00"
        # No ledger legs and no audit row: only the timesheet row is written.
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ? AND entity_id = ?",
            ("finaid-update-work-study-timesheet", ts_id)).fetchone()[0] == 0

    def test_refuses_an_unknown_timesheet_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pkg_id = _package(s)
        assign_id = _ws_assign(s, _fws_award(s, pkg_id), _ws_job(s))
        ts_id = _ws_timesheet(s, assign_id, hours="20")
        before = _snapshot(conn)
        r = call_action(WS_ACTIONS["finaid-update-work-study-timesheet"], conn, ns(
            id="no-such-timesheet", hours_worked="5"))
        assert is_error(r)
        assert r["message"] == "Timesheet no-such-timesheet not found"
        assert _snapshot(conn) == before
        assert _row(conn, "finaid_work_study_timesheet",
                    ts_id)["hours_worked"] == "20"
