"""Behaviour of the award disbursement actions, read back from the database.

finaid-record-award-disbursement, finaid-cancel-disbursement,
finaid-record-credit-balance-return and finaid-record-r2t4-return-disbursement
each write finaid_disbursement rows and move the award's disbursed_amount or a
related date. These tests pin the exact rows and amounts they write and the
refusals that must leave the database untouched: an award cannot be disbursed
past its accepted amount, a reversal cannot take back more than was disbursed
(so a fully cancelled disbursement cannot be cancelled again), a credit balance
cannot be returned twice, and a return cannot name an R2T4 calculation that does
not exist. None of these handlers posts to the general ledger.

All dates are passed explicitly, so nothing here depends on today's date.
"""
import importlib.util
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
        "term_id": tid, "program_enrollment_id": peid, "isir_id": isir_id,
        "cost_of_attendance_id": coa_id,
    }
    conn.close()


def _award(s, aid_type="pell", offered="5000.00", accepted="4000.00"):
    """A package with one award, accepted at `accepted`. Returns (package_id, award_id)."""
    conn = s["conn"]
    pkg = call_action(FA_ACTIONS["finaid-create-award-package"], conn, ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"], enrollment_status="full_time",
        financial_need=None, acceptance_deadline=None, packaged_by=None, notes=None))
    assert is_ok(pkg), pkg
    award = call_action(FA_ACTIONS["finaid-add-award"], conn, ns(
        award_package_id=pkg["id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=None, gl_account_id=None, notes=None))
    assert is_ok(award), award
    if accepted is not None:
        r = call_action(FA_ACTIONS["finaid-accept-award"], conn, ns(
            award_id=award["id"], accepted_amount=accepted, acceptance_date="2025-08-01"))
        assert is_ok(r), r
    return pkg["id"], award["id"]


def _disburse(s, award_id, amount, number=1, date="2025-09-02"):
    return call_action(FA_ACTIONS["finaid-record-award-disbursement"], s["conn"], ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date=date, company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=number))


def _cancel(s, award_id, amount, date="2025-09-20"):
    return call_action(FA_ACTIONS["finaid-cancel-disbursement"], s["conn"], ns(
        award_id=award_id, amount=amount, disbursement_date=date,
        company_id=s["company_id"]))


def _award_row(conn, award_id):
    return conn.execute(
        "SELECT offered_amount, accepted_amount, disbursed_amount, acceptance_status, is_locked "
        "FROM finaid_award WHERE id = ?", (award_id,)).fetchone()


def _disb_rows(conn, award_id):
    rows = conn.execute(
        "SELECT disbursement_type, disbursement_number, amount, disbursement_date, "
        "award_package_id, student_id, company_id, disbursed_by, cod_status, "
        "is_credit_balance, credit_balance_returned_date "
        "FROM finaid_disbursement WHERE award_id = ?", (award_id,)).fetchall()
    return sorted((tuple(r) for r in rows), key=lambda t: (t[3], t[0], t[1], t[2]))


# ---------------------------------------------------------------------------
# finaid-record-award-disbursement
# ---------------------------------------------------------------------------

def test_disbursements_write_rows_and_accumulate_on_the_award(env):
    s, conn = env, env["conn"]
    pkg_id, award_id = _award(s)
    r1 = _disburse(s, award_id, "1500.00", number=1, date="2025-09-02")
    assert is_ok(r1), r1
    assert (r1["amount"], r1["disbursement_date"]) == ("1500.00", "2025-09-02")
    r2 = _disburse(s, award_id, "1000.005", number=2, date="2026-01-15")
    assert is_ok(r2), r2
    assert r2["amount"] == "1000.01"

    assert _disb_rows(conn, award_id) == [
        ("disbursement", 1, "1500.00", "2025-09-02", pkg_id, s["student_id"],
         s["company_id"], "bursar", "", 0, ""),
        ("disbursement", 2, "1000.01", "2026-01-15", pkg_id, s["student_id"],
         s["company_id"], "bursar", "", 0, ""),
    ]
    award = _award_row(conn, award_id)
    assert tuple(award) == ("5000.00", "4000.00", "2500.01", "accepted", 1)
    pkg = conn.execute("SELECT total_grants, total_aid, status FROM finaid_award_package "
                       "WHERE id = ?", (pkg_id,)).fetchone()
    assert tuple(pkg) == ("5000.00", "5000.00", "draft")


def test_disbursement_up_to_the_accepted_amount_is_allowed_and_one_cent_more_is_refused(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "3000.00"))
    r = _disburse(s, award_id, "1000.01", number=2)
    assert is_error(r)
    assert "exceed the accepted amount 4000.00" in r["message"]
    assert _award_row(conn, award_id)["disbursed_amount"] == "3000.00"
    assert [t[2] for t in _disb_rows(conn, award_id)] == ["3000.00"]

    assert is_ok(_disburse(s, award_id, "1000.00", number=2))
    assert _award_row(conn, award_id)["disbursed_amount"] == "4000.00"


def test_disbursement_refuses_a_non_positive_amount(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s)
    r = _disburse(s, award_id, "-250.00")
    assert is_error(r)
    assert r["message"] == "amount must be greater than zero"
    assert _disb_rows(conn, award_id) == []
    assert _award_row(conn, award_id)["disbursed_amount"] == "0"


def test_disbursement_refuses_an_award_not_yet_accepted(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s, accepted=None)
    r = _disburse(s, award_id, "1500.00")
    assert is_error(r)
    assert r["message"] == "Award must be accepted before disbursement"
    assert _disb_rows(conn, award_id) == []
    award = _award_row(conn, award_id)
    assert (award["disbursed_amount"], award["acceptance_status"], award["is_locked"]) == \
        ("0", "pending", 0)


def test_disbursement_refuses_an_award_with_loan_holds(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s, aid_type="subsidized_loan", offered="3500.00", accepted="3500.00")
    loan = call_action(LOAN_ACTIONS["finaid-add-loan"], conn, ns(
        company_id=s["company_id"], student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], award_id=award_id, loan_type="subsidized",
        loan_period_start="2025-08-25", loan_period_end="2026-05-15",
        loan_amount="3500.00", first_disbursement_amount="1750.00",
        second_disbursement_amount="1750.00", origination_fee="29.05",
        interest_rate="6.53", borrower_id=s["student_id"], borrower_type="student",
        cod_loan_id=None, mpn_signed_date=None, entrance_counseling_required=1,
        entrance_counseling_date=None, exit_counseling_required=0,
        exit_counseling_date=None))
    assert is_ok(loan), loan
    r = _disburse(s, award_id, "1750.00")
    assert is_error(r)
    assert r["message"] == "Disbursement blocked by holds: mpn_pending, ec_pending"
    assert _disb_rows(conn, award_id) == []
    assert _award_row(conn, award_id)["disbursed_amount"] == "0"


# ---------------------------------------------------------------------------
# finaid-cancel-disbursement
# ---------------------------------------------------------------------------

def test_cancel_writes_a_reversal_row_and_lowers_the_disbursed_amount(env):
    s, conn = env, env["conn"]
    pkg_id, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "1500.00"))
    r = _cancel(s, award_id, "500.00", date="2025-09-20")
    assert is_ok(r), r
    assert (r["type"], r["amount"]) == ("reversal", "500.00")

    rows = _disb_rows(conn, award_id)
    assert rows == [
        ("disbursement", 1, "1500.00", "2025-09-02", pkg_id, s["student_id"],
         s["company_id"], "bursar", "", 0, ""),
        ("reversal", 1, "500.00", "2025-09-20", pkg_id, s["student_id"],
         s["company_id"], "", "", 0, ""),
    ]
    award = _award_row(conn, award_id)
    assert (award["disbursed_amount"], award["accepted_amount"], award["is_locked"]) == \
        ("1000.00", "4000.00", 1)


def test_a_fully_cancelled_disbursement_cannot_be_cancelled_again(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "1500.00"))
    assert is_ok(_cancel(s, award_id, "1500.00"))
    assert _award_row(conn, award_id)["disbursed_amount"] == "0.00"

    r = _cancel(s, award_id, "1500.00", date="2025-09-21")
    assert is_error(r)
    assert r["message"] == "Reversal of 1500.00 exceeds the disbursed amount 0.00"
    assert [(t[0], t[2]) for t in _disb_rows(conn, award_id)] == \
        [("disbursement", "1500.00"), ("reversal", "1500.00")]
    assert _award_row(conn, award_id)["disbursed_amount"] == "0.00"


def test_cancel_refuses_a_non_positive_amount_and_an_unknown_award(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "1500.00"))
    r = _cancel(s, award_id, "-500.00")
    assert is_error(r)
    assert r["message"] == "amount must be greater than zero"
    r = _cancel(s, "no-such-award", "500.00")
    assert is_error(r)
    assert r["message"] == "Award not found"
    assert [t[0] for t in _disb_rows(conn, award_id)] == ["disbursement"]
    assert conn.execute("SELECT COUNT(*) FROM finaid_disbursement").fetchone()[0] == 1
    assert _award_row(conn, award_id)["disbursed_amount"] == "1500.00"


# ---------------------------------------------------------------------------
# finaid-record-credit-balance-return
# ---------------------------------------------------------------------------

def _credit_balance_disbursement(s, award_id):
    """No action sets is_credit_balance today, so the flag is seeded on a
    disbursement the shipped action wrote."""
    conn = s["conn"]
    r = _disburse(s, award_id, "4000.00")
    assert is_ok(r), r
    conn.execute("UPDATE finaid_disbursement SET is_credit_balance = 1, "
                 "credit_balance_amount = ?, credit_balance_date = ? WHERE id = ?",
                 ("850.00", "2025-09-03", r["id"]))
    conn.commit()
    return r["id"]


def _return_credit_balance(s, disb_id, date):
    return call_action(FA_ACTIONS["finaid-record-credit-balance-return"], s["conn"], ns(
        id=disb_id, return_date=date))


def _credit_row(conn, disb_id):
    return conn.execute(
        "SELECT amount, is_credit_balance, credit_balance_amount, credit_balance_date, "
        "credit_balance_returned_date FROM finaid_disbursement WHERE id = ?",
        (disb_id,)).fetchone()


def test_credit_balance_return_records_the_return_date_once(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s)
    disb_id = _credit_balance_disbursement(s, award_id)
    r = _return_credit_balance(s, disb_id, "2025-09-10")
    assert is_ok(r), r
    assert r["credit_balance_returned_date"] == "2025-09-10"
    assert tuple(_credit_row(conn, disb_id)) == ("4000.00", 1, "850.00", "2025-09-03", "2025-09-10")

    again = _return_credit_balance(s, disb_id, "2025-09-15")
    assert is_error(again)
    assert again["message"] == "Credit balance already returned on 2025-09-10"
    assert tuple(_credit_row(conn, disb_id)) == ("4000.00", 1, "850.00", "2025-09-03", "2025-09-10")
    assert _award_row(conn, award_id)["disbursed_amount"] == "4000.00"


def test_credit_balance_return_refuses_a_disbursement_that_is_not_a_credit_balance(env):
    s, conn = env, env["conn"]
    _, award_id = _award(s)
    r = _disburse(s, award_id, "1500.00")
    assert is_ok(r), r
    refused = _return_credit_balance(s, r["id"], "2025-09-10")
    assert is_error(refused)
    assert refused["message"] == "This disbursement is not a credit balance"
    assert tuple(_credit_row(conn, r["id"])) == ("1500.00", 0, "0", "", "")

    missing = _return_credit_balance(s, "no-such-disbursement", "2025-09-10")
    assert is_error(missing)
    assert missing["message"] == "Disbursement not found"


# ---------------------------------------------------------------------------
# finaid-record-r2t4-return-disbursement
# ---------------------------------------------------------------------------

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


def _record_return(s, award_id, amount, r2t4_id=None, date="2025-10-20"):
    return call_action(FA_ACTIONS["finaid-record-r2t4-return-disbursement"], s["conn"], ns(
        award_id=award_id, r2t4_id=r2t4_id, amount=amount,
        disbursement_date=date, company_id=s["company_id"]))


def _r2t4_row(conn, r2t4_id):
    return conn.execute(
        "SELECT status, institution_return_due_date, institution_return_date "
        "FROM finaid_r2t4_calculation WHERE id = ?", (r2t4_id,)).fetchone()


def test_r2t4_return_writes_a_return_row_and_stamps_the_calculation(env):
    s, conn = env, env["conn"]
    pkg_id, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "4000.00"))
    r2t4_id = _r2t4(s, pkg_id)
    assert tuple(_r2t4_row(conn, r2t4_id)) == ("calculated", "2025-11-19", "")

    r = _record_return(s, award_id, "1200.004", r2t4_id=r2t4_id, date="2025-10-20")
    assert is_ok(r), r
    assert r["type"] == "return"
    assert _disb_rows(conn, award_id) == [
        ("disbursement", 1, "4000.00", "2025-09-02", pkg_id, s["student_id"],
         s["company_id"], "bursar", "", 0, ""),
        ("return", 1, "1200.00", "2025-10-20", pkg_id, s["student_id"],
         s["company_id"], "", "", 0, ""),
    ]
    assert tuple(_r2t4_row(conn, r2t4_id)) == ("calculated", "2025-11-19", "2025-10-20")


def test_r2t4_return_refuses_an_unknown_calculation_and_writes_nothing(env):
    s, conn = env, env["conn"]
    pkg_id, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "4000.00"))
    r = _record_return(s, award_id, "1200.00", r2t4_id="no-such-r2t4")
    assert is_error(r)
    assert r["message"] == "R2T4 calculation not found"
    assert [t[0] for t in _disb_rows(conn, award_id)] == ["disbursement"]


def test_r2t4_return_refuses_a_non_positive_amount_and_an_unknown_award(env):
    s, conn = env, env["conn"]
    pkg_id, award_id = _award(s)
    assert is_ok(_disburse(s, award_id, "4000.00"))
    r2t4_id = _r2t4(s, pkg_id)
    r = _record_return(s, award_id, "0.00", r2t4_id=r2t4_id)
    assert is_error(r)
    assert r["message"] == "amount must be greater than zero"
    r = _record_return(s, "no-such-award", "1200.00", r2t4_id=r2t4_id)
    assert is_error(r)
    assert r["message"] == "Award not found"
    assert conn.execute("SELECT COUNT(*) FROM finaid_disbursement").fetchone()[0] == 1
    assert tuple(_r2t4_row(conn, r2t4_id)) == ("calculated", "2025-11-19", "")
