"""Behaviour of the finaid approval/completion actions, read back from the database.

finaid-complete-isir-review, finaid-complete-isir-cflag, finaid-apply-sap-override,
finaid-complete-sap-appeal, finaid-approve-r2t4, finaid-approve-professional-judgment,
finaid-complete-scholarship-review, finaid-approve-scholarship-application,
finaid-assign-student-to-job, finaid-approve-work-study-timesheet,
finaid-cancel-award-package and finaid-cancel-disbursement each move one or two
owned rows from one exact state to another. These tests pin the rows and values
each action writes, what it must leave alone, and the refusals that must leave
the database byte-identical: a missing id, an unknown row, or an illegal state
transition is reported truthfully and writes nothing.

None of these twelve handlers posts to the general ledger (no gl_entry write
exists in financial_aid.py, scholarships.py or work_study.py), so every test
below asserts stored rows, never ledger legs. A later reader must not add a
balanced-legs assertion here; there are no legs to balance.

All dates the caller controls are passed explicitly, so nothing here depends on
today's date except three fields the handlers stamp themselves (scholarship
review_date, timesheet supervisor_approval_date, appeal reviewed_date), where
the test computes the expected today value at assertion time.
"""
import importlib.util
import os
from datetime import datetime, timezone
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


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@pytest.fixture
def env(db_path):
    conn = get_connection()
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
        "aid_year_id": aid_yr, "year_id": yid, "term_id": tid,
        "program_id": pid, "program_enrollment_id": peid,
        "isir_id": isir_id, "cost_of_attendance_id": coa_id,
    }
    conn.close()


def _snapshot(conn, tables):
    snap = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        snap[table] = sorted(
            tuple("" if value is None else str(value) for value in row)
            for row in rows
        )
    return snap


def _row(conn, table, row_id):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    assert row is not None, f"expected a row in {table} with id {row_id}"
    return dict(row)


def _unchanged(before, after, ignore):
    return {k: v for k, v in before.items() if k not in ignore} == \
        {k: v for k, v in after.items() if k not in ignore}


def _package(s, **kwargs):
    args = dict(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", packaged_by=None, notes=None)
    args.update(kwargs)
    r = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(**args))
    assert is_ok(r), r
    return r["id"]


def _award(s, pkg_id, aid_type="pell", offered="5000.00"):
    r = call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None, notes=None))
    assert is_ok(r), r
    return r["id"]


def _fsp_evaluation(s, **kwargs):
    args = dict(
        student_id=s["student_id"], academic_term_id=s["term_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        gpa_earned="1.50", gpa_threshold="2.00",
        credits_attempted="12", credits_completed="6",
        evaluation_date="2025-12-20", evaluated_by="system")
    args.update(kwargs)
    r = call_action(FA_ACTIONS["finaid-generate-sap-evaluation"], s["conn"], ns(**args))
    assert is_ok(r), r
    assert r["sap_status"] == "FSP", r
    return r["id"]


def _sap_appeal(s, eval_id, reason="illness"):
    r = call_action(FA_ACTIONS["finaid-submit-sap-appeal"], s["conn"], ns(
        sap_evaluation_id=eval_id, student_id=s["student_id"],
        company_id=s["company_id"], appeal_reason=reason,
        reason_narrative="hospitalized in November", academic_plan="retake failed courses",
        submitted_date="2025-12-21"))
    assert is_ok(r), r
    return r["id"]


def _r2t4(s, pkg_id):
    r = call_action(FA_ACTIONS["finaid-create-r2t4"], s["conn"], ns(
        student_id=s["student_id"], academic_term_id=s["term_id"],
        award_package_id=pkg_id, company_id=s["company_id"],
        withdrawal_type="official", withdrawal_date="2025-10-01",
        last_date_of_attendance="2025-10-01", determination_date="2025-10-05",
        payment_period_start="2025-08-25", payment_period_end="2025-12-20",
        payment_period_days=117))
    assert is_ok(r), r
    return r["id"]


def _pj(s):
    r = call_action(FA_ACTIONS["finaid-add-professional-judgment"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        company_id=s["company_id"], pj_type="sai_adjustment", pj_reason="job_loss",
        reason_narrative="parent laid off", data_element_changed="agi",
        original_value="50000", adjusted_value="30000",
        effective_date="2025-09-01", authorized_by="counselor",
        authorization_date="2025-09-02"))
    assert is_ok(r), r
    return r["id"]


def _schol_program(s, annual_budget="10000.00"):
    r = call_action(SCHOL_ACTIONS["finaid-add-scholarship-program"], s["conn"], ns(
        company_id=s["company_id"], name="Dean Merit", code="DEAN-MERIT",
        scholarship_type="merit", funding_source="endowment",
        award_method="application_required", award_amount_type="fixed",
        award_amount="2000.00", award_period="annual",
        applies_to_aid_type="institutional_scholarship",
        annual_budget=annual_budget, max_recipients=5))
    assert is_ok(r), r
    return r["id"]


def _schol_application(s, program_id):
    r = call_action(SCHOL_ACTIONS["finaid-submit-scholarship-application"], s["conn"], ns(
        scholarship_program_id=program_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        essay_response="essay", gpa_at_application="3.60",
        submission_date="2025-03-10"))
    assert is_ok(r), r
    return r["id"]


def _ws_job(s, total_positions=1):
    r = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
        company_id=s["company_id"], aid_year_id=s["aid_year_id"],
        job_title="Library Assistant", department_id=None, supervisor_id=None,
        job_type="on_campus", pay_rate="12.00", hours_per_week="15",
        total_positions=total_positions, description=None))
    assert is_ok(r), r
    return r["id"]


def _ws_assignment(s, job_id, award_limit="3000.00"):
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, aid_type="fws", offered="3000.00")
    r = call_action(WS_ACTIONS["finaid-assign-student-to-job"], s["conn"], ns(
        student_id=s["student_id"], award_id=award_id, job_id=job_id,
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-09-01",
        end_date="2026-05-15", award_limit=award_limit))
    assert is_ok(r), r
    return r["id"]


def _ws_timesheet(s, assignment_id, start="2025-09-01", hours="15", end="2025-09-15"):
    r = call_action(WS_ACTIONS["finaid-submit-work-study-timesheet"], s["conn"], ns(
        assignment_id=assignment_id, student_id=s["student_id"],
        company_id=s["company_id"], pay_period_start=start,
        pay_period_end=end, hours_worked=hours,
        submission_date="2025-09-16"))
    assert is_ok(r), r
    return r["id"]


# ---------------------------------------------------------------------------
# finaid-complete-isir-review
# ---------------------------------------------------------------------------

def test_complete_isir_review_marks_the_isir_reviewed_and_nothing_else(env):
    s, conn = env, env["conn"]
    before = _row(conn, "finaid_isir", s["isir_id"])
    assert before["status"] == "received"

    r = call_action(FA_ACTIONS["finaid-complete-isir-review"], conn, ns(
        isir_id=s["isir_id"], reviewed_by="officer-1"))
    assert is_ok(r), r

    after = _row(conn, "finaid_isir", s["isir_id"])
    assert after["status"] == "reviewed"
    assert after["reviewed_by"] == "officer-1"
    assert after["reviewed_at"] != ""
    assert _unchanged(before, after, {"status", "reviewed_by", "reviewed_at", "updated_at"})
    assert after["sai"] == "1500"
    assert after["has_unresolved_cflags"] == 0


def test_complete_isir_review_refuses_a_missing_id_and_writes_nothing(env):
    s, conn = env, env["conn"]
    before = _snapshot(conn, ["finaid_isir", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-complete-isir-review"], conn, ns(
        isir_id=None, reviewed_by="officer-1"))
    assert is_error(r)
    assert r["message"] == "isir_id or id is required"
    assert _snapshot(conn, ["finaid_isir", "audit_log"]) == before


def test_complete_isir_review_reports_ok_for_an_unknown_isir_without_writing(env):
    # FINDING (deliberately not fixed): review_isir never checks the row
    # exists, so an unknown id returns ok yet changes nothing. The test pins
    # that real behaviour: a passing envelope with zero database effect.
    s, conn = env, env["conn"]
    before = _snapshot(conn, ["finaid_isir", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-complete-isir-review"], conn, ns(
        isir_id="no-such-isir", reviewed_by="officer-1"))
    assert is_ok(r), r
    assert _snapshot(conn, ["finaid_isir", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-complete-isir-cflag
# ---------------------------------------------------------------------------

def _cflag(s, code):
    r = call_action(FA_ACTIONS["finaid-add-isir-cflag"], s["conn"], ns(
        isir_id=s["isir_id"], company_id=s["company_id"], cflag_code=code,
        cflag_description="citizenship", blocks_disbursement=1))
    assert is_ok(r), r
    return r["id"]


def test_complete_isir_cflag_resolves_one_flag_and_clears_the_isir_only_when_none_remain(env):
    s, conn = env, env["conn"]
    first = _cflag(s, "C01")
    second = _cflag(s, "C02")
    assert _row(conn, "finaid_isir", s["isir_id"])["has_unresolved_cflags"] == 1

    r = call_action(FA_ACTIONS["finaid-complete-isir-cflag"], conn, ns(
        id=first, resolution_status="resolved", resolution_date="2025-04-10",
        resolved_by="officer-1", resolution_notes="docs verified"))
    assert is_ok(r), r
    assert r["resolution_status"] == "resolved"

    row = _row(conn, "finaid_isir_cflag", first)
    assert (row["cflag_code"], row["resolution_status"], row["resolution_date"],
            row["resolved_by"], row["resolution_notes"]) == \
        ("C01", "resolved", "2025-04-10", "officer-1", "docs verified")
    assert (row["isir_id"], row["student_id"], row["company_id"]) == \
        (s["isir_id"], s["student_id"], s["company_id"])
    assert _row(conn, "finaid_isir_cflag", second)["resolution_status"] == "pending"
    assert _row(conn, "finaid_isir", s["isir_id"])["has_unresolved_cflags"] == 1

    r = call_action(FA_ACTIONS["finaid-complete-isir-cflag"], conn, ns(
        id=second, resolution_status="waived", resolution_date="2025-04-11",
        resolved_by="officer-1", resolution_notes="DHS match"))
    assert is_ok(r), r
    assert _row(conn, "finaid_isir_cflag", second)["resolution_status"] == "waived"
    assert _row(conn, "finaid_isir", s["isir_id"])["has_unresolved_cflags"] == 0


def test_complete_isir_cflag_refuses_a_missing_status_and_an_unknown_flag(env):
    s, conn = env, env["conn"]
    flag_id = _cflag(s, "C01")
    before = _snapshot(conn, ["finaid_isir_cflag", "finaid_isir", "audit_log"])

    r = call_action(FA_ACTIONS["finaid-complete-isir-cflag"], conn, ns(
        id=flag_id, resolution_status=None))
    assert is_error(r)
    assert r["message"] == "resolution_status is required"

    r = call_action(FA_ACTIONS["finaid-complete-isir-cflag"], conn, ns(
        id="no-such-flag", resolution_status="resolved"))
    assert is_error(r)
    assert r["message"] == "C-flag not found"
    assert _snapshot(conn, ["finaid_isir_cflag", "finaid_isir", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-apply-sap-override
# ---------------------------------------------------------------------------

def test_apply_sap_override_moves_the_evaluation_to_manual_probation(env):
    s, conn = env, env["conn"]
    eval_id = _fsp_evaluation(s)
    before = _row(conn, "finaid_sap_evaluation", eval_id)
    assert (before["sap_status"], before["evaluation_type"]) == ("FSP", "automatic")

    r = call_action(FA_ACTIONS["finaid-apply-sap-override"], conn, ns(
        id=eval_id, sap_status="FAP", evaluated_by="director",
        notes="probation plan signed"))
    assert is_ok(r), r
    assert r["sap_status"] == "FAP"

    after = _row(conn, "finaid_sap_evaluation", eval_id)
    assert (after["sap_status"], after["evaluation_type"],
            after["evaluated_by"], after["notes"]) == \
        ("FAP", "manual", "director", "probation plan signed")
    assert _unchanged(before, after,
                      {"sap_status", "evaluation_type", "evaluated_by", "notes", "updated_at"})
    assert after["gpa_earned"] == "1.50"
    assert after["completion_rate"] == "0.50"
    assert after["holds_placed"] == 1


def test_apply_sap_override_refuses_a_missing_status_and_writes_nothing(env):
    s, conn = env, env["conn"]
    eval_id = _fsp_evaluation(s)
    before = _snapshot(conn, ["finaid_sap_evaluation", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-apply-sap-override"], conn, ns(
        id=eval_id, sap_status=None))
    assert is_error(r)
    assert r["message"] == "id and sap_status are required"
    assert _snapshot(conn, ["finaid_sap_evaluation", "audit_log"]) == before


def test_apply_sap_override_reports_ok_for_an_unknown_evaluation_without_writing(env):
    # FINDING (deliberately not fixed): override_sap_status never checks the
    # row exists, so an unknown id returns ok yet changes nothing.
    s, conn = env, env["conn"]
    _fsp_evaluation(s)
    before = _snapshot(conn, ["finaid_sap_evaluation", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-apply-sap-override"], conn, ns(
        id="no-such-evaluation", sap_status="FAP", evaluated_by="director"))
    assert is_ok(r), r
    assert _snapshot(conn, ["finaid_sap_evaluation", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-complete-sap-appeal
# ---------------------------------------------------------------------------

def test_complete_sap_appeal_denied_leaves_the_student_suspended(env):
    s, conn = env, env["conn"]
    eval_id = _fsp_evaluation(s)
    appeal_id = _sap_appeal(s, eval_id)

    r = call_action(FA_ACTIONS["finaid-complete-sap-appeal"], conn, ns(
        id=appeal_id, status="denied", reviewed_by="dean",
        decision_rationale="insufficient documentation"))
    assert is_ok(r), r
    assert r["document_status"] == "denied"

    appeal = _row(conn, "finaid_sap_appeal", appeal_id)
    assert (appeal["status"], appeal["reviewed_by"],
            appeal["decision_rationale"], appeal["reviewed_date"]) == \
        ("denied", "dean", "insufficient documentation", _today())
    assert appeal["sap_evaluation_id"] == eval_id
    assert _row(conn, "finaid_sap_evaluation", eval_id)["sap_status"] == "FSP"


def test_complete_sap_appeal_granted_moves_the_evaluation_to_probation(env):
    s, conn = env, env["conn"]
    eval_id = _fsp_evaluation(s)
    appeal_id = _sap_appeal(s, eval_id)

    r = call_action(FA_ACTIONS["finaid-complete-sap-appeal"], conn, ns(
        id=appeal_id, status="granted", reviewed_by="dean",
        decision_rationale="hospital records verified",
        probation_term_id=s["term_id"], probation_conditions="meet advisor monthly"))
    assert is_ok(r), r
    assert r["document_status"] == "granted"

    appeal = _row(conn, "finaid_sap_appeal", appeal_id)
    assert (appeal["status"], appeal["reviewed_by"], appeal["probation_term_id"],
            appeal["probation_conditions"]) == \
        ("granted", "dean", s["term_id"], "meet advisor monthly")
    assert _row(conn, "finaid_sap_evaluation", eval_id)["sap_status"] == "FAP"


def test_complete_sap_appeal_refuses_a_bad_decision_and_an_unknown_appeal(env):
    s, conn = env, env["conn"]
    eval_id = _fsp_evaluation(s)
    appeal_id = _sap_appeal(s, eval_id)
    before = _snapshot(conn, ["finaid_sap_appeal", "finaid_sap_evaluation", "audit_log"])

    r = call_action(FA_ACTIONS["finaid-complete-sap-appeal"], conn, ns(
        id=appeal_id, status="maybe"))
    assert is_error(r)
    assert r["message"] == "status must be 'granted' or 'denied'"

    r = call_action(FA_ACTIONS["finaid-complete-sap-appeal"], conn, ns(
        id="no-such-appeal", status="granted"))
    assert is_error(r)
    assert r["message"] == "SAP appeal not found"
    assert _snapshot(conn, ["finaid_sap_appeal", "finaid_sap_evaluation", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-approve-r2t4
# ---------------------------------------------------------------------------

def test_approve_r2t4_marks_the_calculation_approved_and_nothing_else(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    r2t4_id = _r2t4(s, pkg_id)
    before = _row(conn, "finaid_r2t4_calculation", r2t4_id)
    assert before["status"] == "calculated"
    assert before["institution_return_due_date"] == "2025-11-19"

    r = call_action(FA_ACTIONS["finaid-approve-r2t4"], conn, ns(
        id=r2t4_id, approved_by="director"))
    assert is_ok(r), r

    after = _row(conn, "finaid_r2t4_calculation", r2t4_id)
    assert (after["status"], after["approved_by"]) == ("approved", "director")
    assert _unchanged(before, after, {"status", "approved_by", "updated_at"})
    assert after["institution_return_due_date"] == "2025-11-19"
    assert after["institution_return_date"] == ""


def test_approve_r2t4_refuses_a_missing_id_and_writes_nothing(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _r2t4(s, pkg_id)
    before = _snapshot(conn, ["finaid_r2t4_calculation", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-approve-r2t4"], conn, ns(
        id=None, approved_by="director"))
    assert is_error(r)
    assert r["message"] == "id or r2t4_id is required"
    assert _snapshot(conn, ["finaid_r2t4_calculation", "audit_log"]) == before


def test_approve_r2t4_reports_ok_for_an_unknown_calculation_without_writing(env):
    # FINDING (deliberately not fixed): approve_r2t4 never checks the row
    # exists, so an unknown id returns ok yet changes nothing.
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _r2t4(s, pkg_id)
    before = _snapshot(conn, ["finaid_r2t4_calculation", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-approve-r2t4"], conn, ns(
        id="no-such-r2t4", approved_by="director"))
    assert is_ok(r), r
    assert _snapshot(conn, ["finaid_r2t4_calculation", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-approve-professional-judgment
# ---------------------------------------------------------------------------

def test_approve_professional_judgment_records_the_supervisor_review(env):
    s, conn = env, env["conn"]
    pj_id = _pj(s)
    before = _row(conn, "finaid_professional_judgment", pj_id)
    assert before["supervisor_reviewed_by"] == ""

    r = call_action(FA_ACTIONS["finaid-approve-professional-judgment"], conn, ns(
        id=pj_id, supervisor_reviewed_by="director",
        supervisor_review_date="2025-09-03"))
    assert is_ok(r), r
    assert r["supervisor_reviewed_by"] == "director"

    after = _row(conn, "finaid_professional_judgment", pj_id)
    assert (after["supervisor_reviewed_by"], after["supervisor_review_date"]) == \
        ("director", "2025-09-03")
    assert _unchanged(before, after,
                      {"supervisor_reviewed_by", "supervisor_review_date"})
    assert (after["pj_type"], after["pj_reason"], after["original_value"],
            after["adjusted_value"]) == \
        ("sai_adjustment", "job_loss", "50000", "30000")


def test_approve_professional_judgment_refuses_a_missing_reviewer_and_writes_nothing(env):
    s, conn = env, env["conn"]
    pj_id = _pj(s)
    before = _snapshot(conn, ["finaid_professional_judgment", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-approve-professional-judgment"], conn, ns(
        id=pj_id, supervisor_reviewed_by=None))
    assert is_error(r)
    assert r["message"] == "id and supervisor_reviewed_by are required"
    assert _snapshot(conn, ["finaid_professional_judgment", "audit_log"]) == before


def test_approve_professional_judgment_reports_ok_for_an_unknown_record_without_writing(env):
    # FINDING (deliberately not fixed): approve_professional_judgment never
    # checks the row exists, so an unknown id returns ok yet changes nothing.
    s, conn = env, env["conn"]
    _pj(s)
    before = _snapshot(conn, ["finaid_professional_judgment", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-approve-professional-judgment"], conn, ns(
        id="no-such-pj", supervisor_reviewed_by="director"))
    assert is_ok(r), r
    assert _snapshot(conn, ["finaid_professional_judgment", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-complete-scholarship-review
# ---------------------------------------------------------------------------

def test_complete_scholarship_review_assigns_a_reviewer_and_marks_under_review(env):
    s, conn = env, env["conn"]
    program_id = _schol_program(s)
    app_id = _schol_application(s, program_id)
    before = _row(conn, "finaid_scholarship_application", app_id)
    assert before["status"] == "submitted"

    r = call_action(SCHOL_ACTIONS["finaid-complete-scholarship-review"], conn, ns(
        id=app_id, reviewer_id="rev-1", review_notes="strong essay"))
    assert is_ok(r), r

    after = _row(conn, "finaid_scholarship_application", app_id)
    assert (after["status"], after["reviewer_id"], after["review_date"],
            after["review_notes"]) == \
        ("under_review", "rev-1", _today(), "strong essay")
    assert _unchanged(before, after,
                      {"status", "reviewer_id", "review_date", "review_notes", "updated_at"})
    assert after["gpa_at_application"] == "3.60"
    assert after["award_amount"] == "0"


def test_complete_scholarship_review_refuses_a_missing_reviewer_and_an_unknown_application(env):
    s, conn = env, env["conn"]
    program_id = _schol_program(s)
    app_id = _schol_application(s, program_id)
    before = _snapshot(conn, ["finaid_scholarship_application",
                              "finaid_scholarship_program", "audit_log"])

    r = call_action(SCHOL_ACTIONS["finaid-complete-scholarship-review"], conn, ns(
        id=app_id, reviewer_id=None))
    assert is_error(r)
    assert r["message"] == "--reviewer-id is required"

    r = call_action(SCHOL_ACTIONS["finaid-complete-scholarship-review"], conn, ns(
        id="no-such-application", reviewer_id="rev-1"))
    assert is_error(r)
    assert r["message"] == "Scholarship application no-such-application not found"
    assert _snapshot(conn, ["finaid_scholarship_application",
                            "finaid_scholarship_program", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-approve-scholarship-application
# ---------------------------------------------------------------------------

def test_approve_scholarship_application_awards_and_decrements_the_program_budget(env):
    s, conn = env, env["conn"]
    program_id = _schol_program(s)
    app_id = _schol_application(s, program_id)
    assert conn.execute("SELECT budget_remaining FROM finaid_scholarship_program "
                        "WHERE id = ?", (program_id,)).fetchone()[0] == "10000.00"

    r = call_action(SCHOL_ACTIONS["finaid-approve-scholarship-application"], conn, ns(
        id=app_id, award_amount="1500.005", award_term_id=s["term_id"]))
    assert is_ok(r), r
    assert r["award_amount"] == "1500.01"

    app = _row(conn, "finaid_scholarship_application", app_id)
    assert (app["status"], app["award_amount"], app["award_term_id"]) == \
        ("awarded", "1500.01", s["term_id"])
    assert Decimal(app["award_amount"]) == Decimal("1500.01")
    program = _row(conn, "finaid_scholarship_program", program_id)
    assert program["budget_remaining"] == "8499.99"
    assert Decimal(program["budget_remaining"]) == \
        Decimal("10000.00") - Decimal("1500.01")
    assert program["annual_budget"] == "10000.00"


def test_approve_scholarship_application_refuses_a_missing_amount_and_an_unknown_application(env):
    s, conn = env, env["conn"]
    program_id = _schol_program(s)
    app_id = _schol_application(s, program_id)
    before = _snapshot(conn, ["finaid_scholarship_application",
                              "finaid_scholarship_program", "audit_log"])

    r = call_action(SCHOL_ACTIONS["finaid-approve-scholarship-application"], conn, ns(
        id=app_id, award_amount=None))
    assert is_error(r)
    assert r["message"] == "--award-amount is required"

    r = call_action(SCHOL_ACTIONS["finaid-approve-scholarship-application"], conn, ns(
        id="no-such-application", award_amount="1500.00"))
    assert is_error(r)
    assert r["message"] == "Scholarship application no-such-application not found"
    assert _snapshot(conn, ["finaid_scholarship_application",
                            "finaid_scholarship_program", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-assign-student-to-job
# ---------------------------------------------------------------------------

def test_assign_student_to_job_creates_the_assignment_and_fills_a_single_seat_job(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s, total_positions=1)
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, aid_type="fws", offered="3000.00")

    r = call_action(WS_ACTIONS["finaid-assign-student-to-job"], conn, ns(
        student_id=s["student_id"], award_id=award_id, job_id=job_id,
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-09-01",
        end_date="2026-05-15", award_limit="3000.00"))
    assert is_ok(r), r
    assert r["job_status"] == "filled"

    assignment = _row(conn, "finaid_work_study_assignment", r["id"])
    assert (assignment["student_id"], assignment["award_id"], assignment["job_id"],
            assignment["aid_year_id"], assignment["academic_term_id"],
            assignment["start_date"], assignment["end_date"]) == \
        (s["student_id"], award_id, job_id, s["aid_year_id"], s["term_id"],
         "2025-09-01", "2026-05-15")
    assert assignment["award_limit"] == "3000.00"
    assert Decimal(assignment["award_limit"]) == Decimal("3000.00")
    assert (assignment["earned_to_date"], assignment["status"],
            assignment["company_id"]) == ("0.00", "active", s["company_id"])
    job = _row(conn, "finaid_work_study_job", job_id)
    assert (job["filled_positions"], job["status"]) == (1, "filled")


def test_assign_student_to_job_refuses_a_missing_student_and_an_unknown_job(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s)
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, aid_type="fws", offered="3000.00")
    before = _snapshot(conn, ["finaid_work_study_assignment",
                              "finaid_work_study_job", "audit_log"])

    r = call_action(WS_ACTIONS["finaid-assign-student-to-job"], conn, ns(
        student_id=None, award_id=award_id, job_id=job_id,
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-09-01",
        end_date="2026-05-15", award_limit="3000.00"))
    assert is_error(r)
    assert r["message"] == "--student-id is required"

    r = call_action(WS_ACTIONS["finaid-assign-student-to-job"], conn, ns(
        student_id=s["student_id"], award_id=award_id, job_id="no-such-job",
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        company_id=s["company_id"], start_date="2025-09-01",
        end_date="2026-05-15", award_limit="3000.00"))
    assert is_error(r)
    assert r["message"] == "Work study job no-such-job not found"
    assert _snapshot(conn, ["finaid_work_study_assignment",
                            "finaid_work_study_job", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-approve-work-study-timesheet
# ---------------------------------------------------------------------------

def test_approve_work_study_timesheet_approves_and_accumulates_earnings(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s)
    assignment_id = _ws_assignment(s, job_id)
    ts_id = _ws_timesheet(s, assignment_id)
    before = _row(conn, "finaid_work_study_timesheet", ts_id)
    assert before["supervisor_approval_status"] == "pending"
    assert before["earnings"] == "180.00"

    r = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts_id, supervisor_approved_by="sup-1"))
    assert is_ok(r), r

    after = _row(conn, "finaid_work_study_timesheet", ts_id)
    assert (after["supervisor_approval_status"], after["supervisor_approved_by"],
            after["supervisor_approved_date"]) == ("approved", "sup-1", _today())
    assert _unchanged(before, after,
                      {"supervisor_approval_status", "supervisor_approved_by",
                       "supervisor_approved_date", "updated_at"})
    # Money is text with its cents: earned_to_date accumulates exact two-place money.
    assignment = _row(conn, "finaid_work_study_assignment", assignment_id)
    assert assignment["earned_to_date"] == "180.00"
    assert Decimal(assignment["earned_to_date"]) == Decimal("180.00")


class _FakeRow:
    def __init__(self, data, order):
        self._data = data
        self._order = order
    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[self._order[key]]
        return self._data[key]
    def keys(self):
        return list(self._order)
    def __len__(self):
        return len(self._order)
    def __iter__(self):
        for col in self._order:
            yield self._data[col]


class _PatchCursor:
    def __init__(self, real_cur, patch):
        self._cur = real_cur
        self._patch = patch
        try:
            self.rowcount = real_cur.rowcount
        except Exception:
            self.rowcount = -1
        try:
            self.lastrowid = real_cur.lastrowid
        except Exception:
            self.lastrowid = None
        try:
            self.description = real_cur.description
        except Exception:
            self.description = None
    def _wrap(self, row):
        if row is None:
            return None
        desc = self._cur.description or []
        order = [d[0] for d in desc]
        data = {}
        for col in order:
            try:
                data[col] = row[col]
            except Exception:
                data[col] = None
        for col, val in self._patch.items():
            if col in data:
                data[col] = val
        return _FakeRow(data, order)
    def fetchone(self):
        return self._wrap(self._cur.fetchone())
    def fetchall(self):
        rows = self._cur.fetchall()
        return [self._wrap(r) for r in rows]
    def fetchmany(self, size=None):
        rows = self._cur.fetchmany(size) if size else self._cur.fetchmany()
        return [self._wrap(r) for r in rows]


class _StaleProxy:
    def __init__(self, real_conn, stale):
        self._c = real_conn
        self._stale = stale
    def execute(self, sql, params=()):
        if params is None:
            params = ()
        stripped = sql.strip().upper() if isinstance(sql, str) else ""
        if stripped.startswith("SELECT"):
            patch = {}
            for table, cols in self._stale.items():
                if table in sql:
                    for col, val in cols.items():
                        if col in sql or "*" in sql:
                            patch[col] = val
            if patch:
                real_cur = self._c.execute(sql, params)
                return _PatchCursor(real_cur, patch)
        return self._c.execute(sql, params)
    def __getattr__(self, name):
        return getattr(self._c, name)


def test_approve_two_timesheets_accumulates_exact_cents(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s)
    assignment_id = _ws_assignment(s, job_id)
    ts1 = _ws_timesheet(s, assignment_id, start="2025-09-01", hours="15")
    ts2 = _ws_timesheet(s, assignment_id, start="2025-09-16", end="2025-09-30", hours="0.1")
    assert _row(conn, "finaid_work_study_timesheet", ts1)["earnings"] == "180.00"
    assert _row(conn, "finaid_work_study_timesheet", ts2)["earnings"] == "1.20"

    assert is_ok(call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts1, supervisor_approved_by="sup-1"))), "first approval"
    assert is_ok(call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts2, supervisor_approved_by="sup-1"))), "second approval"

    assignment = _row(conn, "finaid_work_study_assignment", assignment_id)
    assert assignment["earned_to_date"] == "181.20"
    assert Decimal(assignment["earned_to_date"]) == Decimal("181.20")
    assert _row(conn, "finaid_work_study_timesheet", ts1)["earnings"] == "180.00"
    assert _row(conn, "finaid_work_study_timesheet", ts2)["earnings"] == "1.20"


def test_approve_refuses_when_earned_to_date_changed_underneath(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s)
    assignment_id = _ws_assignment(s, job_id)
    ts_id = _ws_timesheet(s, assignment_id)
    assert _row(conn, "finaid_work_study_assignment", assignment_id)["earned_to_date"] == "0.00"
    before_audit = _snapshot(conn, ["audit_log"])

    proxy = _StaleProxy(conn, {"finaid_work_study_assignment": {"earned_to_date": "999.99"}})
    r = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], proxy, ns(
        id=ts_id, supervisor_approved_by="sup-1"))
    assert is_error(r), r
    assert r["message"] == (
        f"Concurrent change to finaid_work_study_assignment {assignment_id}: "
        "earned_to_date is no longer 999.99; nothing was written"
    ), r

    assert _row(conn, "finaid_work_study_timesheet", ts_id)["supervisor_approval_status"] == "pending"
    assert _row(conn, "finaid_work_study_assignment", assignment_id)["earned_to_date"] == "0.00"
    assert _snapshot(conn, ["audit_log"]) == before_audit


def test_approve_work_study_timesheet_refuses_a_second_approval_and_an_unknown_sheet(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s)
    assignment_id = _ws_assignment(s, job_id)
    ts_id = _ws_timesheet(s, assignment_id)
    assert is_ok(call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts_id, supervisor_approved_by="sup-1")))
    before = _snapshot(conn, ["finaid_work_study_timesheet",
                              "finaid_work_study_assignment", "audit_log"])

    r = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts_id, supervisor_approved_by="sup-1"))
    assert is_error(r)
    assert r["message"] == f"Timesheet {ts_id} cannot be approved: status is 'approved'"

    r = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id="no-such-timesheet", supervisor_approved_by="sup-1"))
    assert is_error(r)
    assert r["message"] == "Timesheet no-such-timesheet not found"

    r = call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=None, supervisor_approved_by="sup-1"))
    assert is_error(r)
    assert r["message"] == "--id is required"
    assert _snapshot(conn, ["finaid_work_study_timesheet",
                            "finaid_work_study_assignment", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-cancel-award-package
# ---------------------------------------------------------------------------

def test_cancel_award_package_cancels_an_empty_package_and_leaves_the_rest_alone(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    other_pkg = _package(s)
    other_award = _award(s, other_pkg, aid_type="pell", offered="2000.00")
    assert conn.execute("SELECT COUNT(*) FROM finaid_award").fetchone()[0] == 1

    r = call_action(FA_ACTIONS["finaid-cancel-award-package"], conn, ns(
        award_package_id=pkg_id))
    assert is_ok(r), r
    assert conn.execute("SELECT status FROM finaid_award_package "
                        "WHERE id = ?", (pkg_id,)).fetchone()[0] == "cancelled"
    assert conn.execute("SELECT COUNT(*) FROM finaid_award").fetchone()[0] == 1
    assert conn.execute("SELECT status FROM finaid_award_package "
                        "WHERE id = ?", (other_pkg,)).fetchone()[0] == "draft"
    assert conn.execute("SELECT accepted_amount, acceptance_status FROM finaid_award "
                        "WHERE id = ?", (other_award,)).fetchone()[0] == "0"
    assert conn.execute("SELECT COUNT(*) FROM finaid_disbursement").fetchone()[0] == 0


def test_cancel_award_package_refuses_a_missing_id_and_writes_nothing(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _award(s, pkg_id, aid_type="pell", offered="5000.00")
    before = _snapshot(conn, ["finaid_award_package", "finaid_award",
                              "finaid_disbursement", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-cancel-award-package"], conn, ns(
        award_package_id=None))
    assert is_error(r)
    assert r["message"] == "award_package_id or id is required"
    assert _snapshot(conn, ["finaid_award_package", "finaid_award",
                            "finaid_disbursement", "audit_log"]) == before


# ---------------------------------------------------------------------------
# finaid-cancel-disbursement
# ---------------------------------------------------------------------------

def _disbursed_award(s, offered="5000.00", accepted="4000.00", amount="1500.00"):
    conn = s["conn"]
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, offered=offered)
    r = call_action(FA_ACTIONS["finaid-accept-award"], conn, ns(
        award_id=award_id, accepted_amount=accepted, acceptance_date="2025-08-01"))
    assert is_ok(r), r
    r = call_action(FA_ACTIONS["finaid-record-award-disbursement"], conn, ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date="2025-09-02", company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=1))
    assert is_ok(r), r
    return pkg_id, award_id


def test_cancel_disbursement_rounds_each_reversal_and_drains_the_award_to_zero(env):
    s, conn = env, env["conn"]
    pkg_id, award_id = _disbursed_award(s)

    r = call_action(FA_ACTIONS["finaid-cancel-disbursement"], conn, ns(
        award_id=award_id, amount="500.005", disbursement_date="2025-09-20",
        company_id=s["company_id"]))
    assert is_ok(r), r
    assert (r["type"], r["amount"]) == ("reversal", "500.01")
    assert conn.execute("SELECT disbursed_amount FROM finaid_award "
                        "WHERE id = ?", (award_id,)).fetchone()[0] == "999.99"

    r = call_action(FA_ACTIONS["finaid-cancel-disbursement"], conn, ns(
        award_id=award_id, amount="999.99", disbursement_date="2025-09-21",
        company_id=s["company_id"]))
    assert is_ok(r), r
    rows = conn.execute(
        "SELECT disbursement_type, disbursement_number, amount, disbursement_date, "
        "award_package_id, student_id, company_id "
        "FROM finaid_disbursement WHERE award_id = ? ORDER BY disbursement_date",
        (award_id,)).fetchall()
    assert [tuple(row) for row in rows] == [
        ("disbursement", 1, "1500.00", "2025-09-02", pkg_id, s["student_id"], s["company_id"]),
        ("reversal", 1, "500.01", "2025-09-20", pkg_id, s["student_id"], s["company_id"]),
        ("reversal", 1, "999.99", "2025-09-21", pkg_id, s["student_id"], s["company_id"]),
    ]
    award = conn.execute(
        "SELECT disbursed_amount, accepted_amount, is_locked FROM finaid_award "
        "WHERE id = ?", (award_id,)).fetchone()
    assert tuple(award) == ("0.00", "4000.00", 1)


def test_cancel_disbursement_refuses_a_missing_company_and_writes_nothing(env):
    s, conn = env, env["conn"]
    _, award_id = _disbursed_award(s)
    before = _snapshot(conn, ["finaid_disbursement", "finaid_award", "audit_log"])
    r = call_action(FA_ACTIONS["finaid-cancel-disbursement"], conn, ns(
        award_id=award_id, amount="500.00", disbursement_date="2025-09-20",
        company_id=None))
    assert is_error(r)
    assert r["message"] == "award_id, amount, and company_id are required"
    assert _snapshot(conn, ["finaid_disbursement", "finaid_award", "audit_log"]) == before


def test_approve_work_study_timesheet_accumulates_exact_cents(env):
    s, conn = env, env["conn"]
    job_id = _ws_job(s)
    assignment_id = _ws_assignment(s, job_id)
    ts1 = _ws_timesheet(s, assignment_id, start="2025-09-01", hours="15")
    ts2 = _ws_timesheet(s, assignment_id, start="2025-09-16", hours="12.5")
    assert is_ok(call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts1, supervisor_approved_by="sup-1")))
    assert is_ok(call_action(WS_ACTIONS["finaid-approve-work-study-timesheet"], conn, ns(
        id=ts2, supervisor_approved_by="sup-1")))
    assignment = _row(conn, "finaid_work_study_assignment", assignment_id)
    assert assignment["earned_to_date"] == "330.00"
