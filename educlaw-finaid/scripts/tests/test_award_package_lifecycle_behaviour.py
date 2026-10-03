"""Behaviour of the award package lifecycle actions, read back from the database.

finaid-create-award-package, finaid-add-award, finaid-update-award,
finaid-delete-award, finaid-accept-award, finaid-deny-award,
finaid-update-award-package and finaid-cancel-award-package move a student's
offered and accepted aid and the package totals; finaid-add-cost-of-attendance
and finaid-add-fund-allocation set up the budget and fund those packages draw
on. These tests pin the exact amounts and statuses each action writes and the
refusals that must leave the database untouched: an award is offered for a
positive amount, a student cannot accept more than was offered or less than was
already disbursed, an award in a cancelled package cannot be accepted, a
disbursed award cannot be declined, and a locked award cannot be changed or
deleted, a package with disbursed awards cannot be cancelled, an unknown award
or package is reported rather than silently "updated", and budget components and
fund totals cannot be negative.

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


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _create_package(s, academic_term_id="term"):
    return call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"] if academic_term_id == "term" else academic_term_id,
        company_id=s["company_id"], program_enrollment_id=s["program_enrollment_id"],
        isir_id=s["isir_id"], cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time", packaged_by="counselor", notes=None))


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


def _award(s, pkg_id, aid_type="pell", offered="5000.00"):
    r = _add_award(s, pkg_id, aid_type, offered)
    assert is_ok(r), r
    return r["id"]


def _accept(s, award_id, amount, date="2025-08-01"):
    return call_action(FA_ACTIONS["finaid-accept-award"], s["conn"], ns(
        award_id=award_id, accepted_amount=amount, acceptance_date=date))


def _decline(s, award_id):
    return call_action(FA_ACTIONS["finaid-deny-award"], s["conn"], ns(award_id=award_id))


def _update_award(s, award_id, offered=None, notes=None):
    return call_action(FA_ACTIONS["finaid-update-award"], s["conn"], ns(
        award_id=award_id, offered_amount=offered, notes=notes, gl_account_id=None))


def _delete_award(s, award_id):
    return call_action(FA_ACTIONS["finaid-delete-award"], s["conn"], ns(award_id=award_id))


def _cancel_package(s, pkg_id):
    return call_action(FA_ACTIONS["finaid-cancel-award-package"], s["conn"], ns(
        award_package_id=pkg_id))


def _offer_package(s, pkg_id):
    r = call_action(FA_ACTIONS["finaid-submit-award-offer"], s["conn"], ns(
        award_package_id=pkg_id, packaged_by="counselor", offered_date="2025-07-15"))
    assert is_ok(r), r


def _disburse(s, award_id, amount):
    r = call_action(FA_ACTIONS["finaid-record-award-disbursement"], s["conn"], ns(
        award_id=award_id, student_id=s["student_id"], amount=amount,
        disbursement_date="2025-09-02", company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=1))
    assert is_ok(r), r


def _package_row(conn, pkg_id):
    return tuple(conn.execute(
        "SELECT financial_need, total_grants, total_loans, total_work_study, total_aid, status "
        "FROM finaid_award_package WHERE id = ?", (pkg_id,)).fetchone())


def _award_row(conn, award_id):
    return tuple(conn.execute(
        "SELECT offered_amount, accepted_amount, disbursed_amount, acceptance_status, "
        "acceptance_date, is_locked FROM finaid_award WHERE id = ?", (award_id,)).fetchone())


# ---------------------------------------------------------------------------
# finaid-create-award-package
# ---------------------------------------------------------------------------

def test_create_award_package_computes_need_from_the_budget_and_numbers_the_series(env):
    s, conn = env, env["conn"]
    first = _create_package(s)
    assert is_ok(first), first
    assert (first["naming_series"], first["financial_need"]) == ("AWD-2025-2026-00001", "28300.00")
    row = conn.execute(
        "SELECT naming_series, student_id, aid_year_id, academic_term_id, isir_id, "
        "cost_of_attendance_id, enrollment_status, packaged_by FROM finaid_award_package "
        "WHERE id = ?", (first["id"],)).fetchone()
    assert tuple(row) == ("AWD-2025-2026-00001", s["student_id"], s["aid_year_id"], s["term_id"],
                          s["isir_id"], s["cost_of_attendance_id"], "full_time", "counselor")
    # cost of attendance 29800 minus SAI 1500
    assert _package_row(conn, first["id"]) == ("28300.00", "0", "0", "0", "0", "draft")

    second = _create_package(s)
    assert is_ok(second), second
    assert second["naming_series"] == "AWD-2025-2026-00002"
    assert _count(conn, "finaid_award_package") == 2


def test_create_award_package_refuses_a_missing_term_and_writes_nothing(env):
    s, conn = env, env["conn"]
    r = _create_package(s, academic_term_id=None)
    assert is_error(r)
    assert r["message"] == "academic_term_id is required"
    assert _count(conn, "finaid_award_package") == 0


# ---------------------------------------------------------------------------
# finaid-add-award
# ---------------------------------------------------------------------------

def test_add_award_writes_a_pending_award_and_rolls_up_package_totals(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    r = _add_award(s, pkg_id, "pell", "3000.004")
    assert is_ok(r), r
    assert r["offered_amount"] == "3000.00"
    pell_id = r["id"]
    _award(s, pkg_id, "institutional_grant", "1000.00")
    _award(s, pkg_id, "subsidized_loan", "3500.00")
    _award(s, pkg_id, "fws", "1200.505")

    row = conn.execute(
        "SELECT award_package_id, student_id, aid_type, aid_source, offered_amount, "
        "accepted_amount, disbursed_amount, acceptance_status, disbursement_holds, is_locked "
        "FROM finaid_award WHERE id = ?", (pell_id,)).fetchone()
    assert tuple(row) == (pkg_id, s["student_id"], "pell", "federal", "3000.00",
                          "0", "0", "pending", "[]", 0)
    offered = sorted(r[0] for r in conn.execute(
        "SELECT offered_amount FROM finaid_award WHERE award_package_id = ?", (pkg_id,)))
    assert offered == ["1000.00", "1200.51", "3000.00", "3500.00"]
    assert _package_row(conn, pkg_id) == ("28300.00", "4000.00", "3500.00", "1200.51",
                                          "8700.51", "draft")


def test_add_award_refuses_a_non_positive_amount_and_a_closed_or_unknown_package(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _award(s, pkg_id, "pell", "3000.00")
    for amount in ("0", "-500.00"):
        r = _add_award(s, pkg_id, "fseog", amount)
        assert is_error(r)
        assert r["message"] == "offered_amount must be greater than zero"
    r = _add_award(s, "no-such-package", "fseog", "500.00")
    assert is_error(r)
    assert r["message"] == "Award package not found"

    cancelled = _package(s)
    assert is_ok(_cancel_package(s, cancelled))
    r = _add_award(s, cancelled, "fseog", "500.00")
    assert is_error(r)
    assert r["message"] == "Can only add awards to draft or offered packages"

    assert _count(conn, "finaid_award") == 1
    assert _package_row(conn, pkg_id) == ("28300.00", "3000.00", "0.00", "0.00", "3000.00", "draft")


# ---------------------------------------------------------------------------
# finaid-update-award
# ---------------------------------------------------------------------------

def test_update_award_changes_the_offer_and_recomputes_package_totals(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "3000.00")
    _award(s, pkg_id, "unsubsidized_loan", "2000.00")
    r = _update_award(s, pell, offered="2500.255", notes="revised after verification")
    assert is_ok(r), r
    row = conn.execute("SELECT offered_amount, notes FROM finaid_award WHERE id = ?",
                       (pell,)).fetchone()
    assert tuple(row) == ("2500.26", "revised after verification")
    assert _package_row(conn, pkg_id) == ("28300.00", "2500.26", "2000.00", "0.00",
                                          "4500.26", "draft")


def test_update_award_refuses_an_offer_below_acceptance_and_a_non_positive_offer(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    r = _update_award(s, pell, offered="3999.99")
    assert is_error(r)
    assert r["message"] == "Offered amount 3999.99 is below the accepted amount 4000.00"
    r = _update_award(s, pell, offered="-1.00")
    assert is_error(r)
    assert r["message"] == "offered_amount must be greater than zero"
    assert _award_row(conn, pell) == ("5000.00", "4000.00", "0", "accepted", "2025-08-01", 0)
    assert _package_row(conn, pkg_id)[1:5] == ("5000.00", "0.00", "0.00", "5000.00")


def test_update_award_refuses_a_locked_award_an_offered_package_and_an_unknown_award(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    _disburse(s, pell, "1500.00")
    r = _update_award(s, pell, offered="6000.00")
    assert is_error(r)
    assert r["message"] == "Award is locked by a disbursement and cannot be updated"
    assert _award_row(conn, pell) == ("5000.00", "4000.00", "1500.00", "accepted", "2025-08-01", 1)

    offered_pkg = _package(s)
    grant = _award(s, offered_pkg, "institutional_grant", "800.00")
    _offer_package(s, offered_pkg)
    r = _update_award(s, grant, offered="900.00")
    assert is_error(r)
    assert r["message"] == "Can only update awards in draft packages"
    assert _award_row(conn, grant)[0] == "800.00"

    r = _update_award(s, "no-such-award", offered="900.00")
    assert is_error(r)
    assert r["message"] == "Award not found"


# ---------------------------------------------------------------------------
# finaid-delete-award
# ---------------------------------------------------------------------------

def test_delete_award_removes_the_row_and_recomputes_package_totals(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "3000.00")
    loan = _award(s, pkg_id, "subsidized_loan", "3500.00")
    r = _delete_award(s, loan)
    assert is_ok(r), r
    assert r["deleted"] is True
    assert [row[0] for row in conn.execute(
        "SELECT id FROM finaid_award WHERE award_package_id = ?", (pkg_id,))] == [pell]
    assert _package_row(conn, pkg_id) == ("28300.00", "3000.00", "0.00", "0.00", "3000.00", "draft")


def test_delete_award_refuses_a_locked_award_an_offered_package_and_an_unknown_award(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, pell, "5000.00"))
    _disburse(s, pell, "2500.00")
    r = _delete_award(s, pell)
    assert is_error(r)
    assert r["message"] == "Award is locked by a disbursement and cannot be deleted"
    assert _award_row(conn, pell) == ("5000.00", "5000.00", "2500.00", "accepted", "2025-08-01", 1)
    assert _package_row(conn, pkg_id)[1:5] == ("5000.00", "0.00", "0.00", "5000.00")

    offered_pkg = _package(s)
    grant = _award(s, offered_pkg, "institutional_grant", "800.00")
    _offer_package(s, offered_pkg)
    r = _delete_award(s, grant)
    assert is_error(r)
    assert r["message"] == "Can only delete awards from draft packages"

    r = _delete_award(s, "no-such-award")
    assert is_error(r)
    assert r["message"] == "Award not found"
    assert _count(conn, "finaid_award") == 2


# ---------------------------------------------------------------------------
# finaid-accept-award
# ---------------------------------------------------------------------------

def test_accept_award_records_a_partial_or_a_full_acceptance(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _offer_package(s, pkg_id)
    pell = _award(s, pkg_id, "pell", "5000.00")
    loan = _award(s, pkg_id, "subsidized_loan", "3500.00")

    r = _accept(s, pell, "2500.005", date="2025-08-03")
    assert is_ok(r), r
    assert r["acceptance_status"] == "accepted"
    assert _award_row(conn, pell) == ("5000.00", "2500.01", "0", "accepted", "2025-08-03", 0)

    # no amount given: the offered amount is accepted
    assert is_ok(_accept(s, loan, None, date="2025-08-04"))
    assert _award_row(conn, loan) == ("3500.00", "3500.00", "0", "accepted", "2025-08-04", 0)

    # accepting the full offer later replaces the partial acceptance
    assert is_ok(_accept(s, pell, "5000.00", date="2025-08-10"))
    assert _award_row(conn, pell) == ("5000.00", "5000.00", "0", "accepted", "2025-08-10", 0)
    assert _package_row(conn, pkg_id) == ("28300.00", "5000.00", "3500.00", "0.00",
                                          "8500.00", "offered")


def test_accept_award_refuses_more_than_offered_and_a_non_positive_amount(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    r = _accept(s, pell, "5000.01")
    assert is_error(r)
    assert r["message"] == "Accepted amount 5000.01 exceeds the offered amount 5000.00"
    for amount in ("0", "-100.00"):
        r = _accept(s, pell, amount)
        assert is_error(r)
        assert r["message"] == "accepted_amount must be greater than zero"
    assert _award_row(conn, pell) == ("5000.00", "0", "0", "pending", "", 0)


def test_accept_award_refuses_less_than_disbursed_a_cancelled_package_and_an_unknown_award(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    _disburse(s, pell, "1500.00")
    r = _accept(s, pell, "1499.99", date="2025-09-10")
    assert is_error(r)
    assert r["message"] == "Accepted amount 1499.99 is below the disbursed amount 1500.00"
    assert _award_row(conn, pell) == ("5000.00", "4000.00", "1500.00", "accepted", "2025-08-01", 1)

    cancelled = _package(s)
    grant = _award(s, cancelled, "institutional_grant", "800.00")
    assert is_ok(_cancel_package(s, cancelled))
    r = _accept(s, grant, "800.00", date="2025-09-10")
    assert is_error(r)
    assert r["message"] == "Cannot accept an award in a cancelled package"
    assert _award_row(conn, grant) == ("800.00", "0", "0", "declined", "", 0)

    r = _accept(s, "no-such-award", "800.00")
    assert is_error(r)
    assert r["message"] == "Award not found"


# ---------------------------------------------------------------------------
# finaid-deny-award
# ---------------------------------------------------------------------------

def test_deny_award_declines_and_zeroes_the_accepted_amount(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    loan = _award(s, pkg_id, "subsidized_loan", "3500.00")
    assert is_ok(_accept(s, loan, "3500.00"))
    assert is_ok(_accept(s, pell, "5000.00"))
    r = _decline(s, loan)
    assert is_ok(r), r
    assert r["acceptance_status"] == "declined"
    assert _award_row(conn, loan) == ("3500.00", "0", "0", "declined", "2025-08-01", 0)
    assert _award_row(conn, pell) == ("5000.00", "5000.00", "0", "accepted", "2025-08-01", 0)


def test_deny_award_refuses_a_disbursed_award_and_an_unknown_award(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    _disburse(s, pell, "1500.00")
    r = _decline(s, pell)
    assert is_error(r)
    assert r["message"] == ("Cannot decline an award with disbursed amount 1500.00; "
                            "cancel its disbursements first")
    assert _award_row(conn, pell) == ("5000.00", "4000.00", "1500.00", "accepted", "2025-08-01", 1)

    r = _decline(s, "no-such-award")
    assert is_error(r)
    assert r["message"] == "Award not found"


# ---------------------------------------------------------------------------
# finaid-update-award-package
# ---------------------------------------------------------------------------

def test_update_award_package_writes_the_given_fields_only(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _award(s, pkg_id, "pell", "5000.00")
    r = call_action(FA_ACTIONS["finaid-update-award-package"], conn, ns(
        award_package_id=pkg_id, notes="needs SAP review", acceptance_deadline="2025-08-15",
        approved_by="director", approved_at="2025-07-20", enrollment_status=None))
    assert is_ok(r), r
    row = conn.execute(
        "SELECT notes, acceptance_deadline, approved_by, approved_at, enrollment_status "
        "FROM finaid_award_package WHERE id = ?", (pkg_id,)).fetchone()
    assert tuple(row) == ("needs SAP review", "2025-08-15", "director", "2025-07-20", "full_time")
    assert _package_row(conn, pkg_id) == ("28300.00", "5000.00", "0.00", "0.00", "5000.00", "draft")


def test_update_award_package_refuses_an_unknown_package_and_an_empty_update(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    r = call_action(FA_ACTIONS["finaid-update-award-package"], conn, ns(
        award_package_id="no-such-package", notes="x"))
    assert is_error(r)
    assert r["message"] == "Award package not found"
    r = call_action(FA_ACTIONS["finaid-update-award-package"], conn, ns(award_package_id=pkg_id))
    assert is_error(r)
    assert r["message"] == "No fields to update"
    assert conn.execute("SELECT notes FROM finaid_award_package WHERE id = ?",
                        (pkg_id,)).fetchone()[0] == ""


# ---------------------------------------------------------------------------
# finaid-cancel-award-package
# ---------------------------------------------------------------------------

def test_cancel_award_package_cancels_and_declines_every_award(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _offer_package(s, pkg_id)
    pell = _award(s, pkg_id, "pell", "5000.00")
    loan = _award(s, pkg_id, "subsidized_loan", "3500.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    other_pkg = _package(s)
    other = _award(s, other_pkg, "pell", "2000.00")
    assert is_ok(_accept(s, other, "2000.00"))

    r = _cancel_package(s, pkg_id)
    assert is_ok(r), r
    assert r["document_status"] == "cancelled"
    assert _package_row(conn, pkg_id)[5] == "cancelled"
    assert _award_row(conn, pell) == ("5000.00", "0", "0", "declined", "2025-08-01", 0)
    assert _award_row(conn, loan) == ("3500.00", "0", "0", "declined", "", 0)
    # another package is untouched
    assert _package_row(conn, other_pkg)[5] == "draft"
    assert _award_row(conn, other) == ("2000.00", "2000.00", "0", "accepted", "2025-08-01", 0)


def test_cancel_award_package_refuses_disbursed_awards_and_an_unknown_package(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    pell = _award(s, pkg_id, "pell", "5000.00")
    grant = _award(s, pkg_id, "institutional_grant", "1000.00")
    assert is_ok(_accept(s, pell, "4000.00"))
    assert is_ok(_accept(s, grant, "1000.00"))
    _disburse(s, pell, "1500.00")
    r = _cancel_package(s, pkg_id)
    assert is_error(r)
    assert r["message"] == ("Cannot cancel a package with disbursed awards; "
                            "cancel their disbursements first")
    assert _package_row(conn, pkg_id)[5] == "draft"
    assert _award_row(conn, pell) == ("5000.00", "4000.00", "1500.00", "accepted", "2025-08-01", 1)
    assert _award_row(conn, grant) == ("1000.00", "1000.00", "0", "accepted", "2025-08-01", 0)

    r = _cancel_package(s, "no-such-package")
    assert is_error(r)
    assert r["message"] == "Award package not found"
    assert [row[0] for row in conn.execute("SELECT status FROM finaid_award_package")] == ["draft"]


# ---------------------------------------------------------------------------
# finaid-add-cost-of-attendance
# ---------------------------------------------------------------------------

def _add_coa(s, living="off_campus", program=True, **amounts):
    values = dict(tuition_fees="12500.005", books_supplies="1200", room_board="9000.50",
                  transportation="1500.25", personal_expenses="2000", loan_fees="99.99")
    values.update(amounts)
    return call_action(FA_ACTIONS["finaid-add-cost-of-attendance"], s["conn"], ns(
        aid_year_id=s["aid_year_id"], company_id=s["company_id"],
        program_id=s["program_id"] if program else None,
        enrollment_status="half_time", living_arrangement=living, **values))


def test_add_cost_of_attendance_rounds_each_component_and_totals_them(env):
    s, conn = env, env["conn"]
    r = _add_coa(s)
    assert is_ok(r), r
    assert r["total_coa"] == "26300.75"
    row = conn.execute(
        "SELECT program_id, enrollment_status, living_arrangement, tuition_fees, books_supplies, "
        "room_board, transportation, personal_expenses, loan_fees, total_coa, is_active "
        "FROM finaid_cost_of_attendance WHERE id = ?", (r["id"],)).fetchone()
    assert tuple(row) == (s["program_id"], "half_time", "off_campus", "12500.01", "1200.00",
                          "9000.50", "1500.25", "2000.00", "99.99", "26300.75", 1)


def test_add_cost_of_attendance_refuses_a_negative_component_and_a_duplicate_budget(env):
    s, conn = env, env["conn"]
    assert is_ok(_add_coa(s))
    before = _count(conn, "finaid_cost_of_attendance")
    r = _add_coa(s, living="with_parent", room_board="-9000.00")
    assert is_error(r)
    assert r["message"] == "room_board cannot be negative"
    r = _add_coa(s)
    assert is_error(r)
    assert r["message"].startswith("Duplicate COA configuration")
    assert _count(conn, "finaid_cost_of_attendance") == before


# ---------------------------------------------------------------------------
# finaid-add-fund-allocation
# ---------------------------------------------------------------------------

def _add_fund(s, total, name="FSEOG Campus Fund", fund_type="fseog"):
    return call_action(FA_ACTIONS["finaid-add-fund-allocation"], s["conn"], ns(
        aid_year_id=s["aid_year_id"], company_id=s["company_id"], fund_type=fund_type,
        fund_name=name, total_allocation=total))


def test_add_fund_allocation_opens_with_the_whole_allocation_available(env):
    s, conn = env, env["conn"]
    r = _add_fund(s, "250000.005")
    assert is_ok(r), r
    row = conn.execute(
        "SELECT fund_type, fund_name, total_allocation, committed_amount, disbursed_amount, "
        "available_amount FROM finaid_fund_allocation WHERE id = ?", (r["id"],)).fetchone()
    assert tuple(row) == ("fseog", "FSEOG Campus Fund", "250000.01", "0", "0", "250000.01")


def test_add_fund_allocation_refuses_a_negative_total_a_duplicate_and_a_missing_type(env):
    s, conn = env, env["conn"]
    assert is_ok(_add_fund(s, "250000.00"))
    r = _add_fund(s, "-1.00", name="Negative Fund")
    assert is_error(r)
    assert r["message"] == "total_allocation cannot be negative"
    r = _add_fund(s, "1000.00")
    assert is_error(r)
    assert r["message"].startswith("Duplicate fund allocation")
    r = _add_fund(s, "1000.00", name="Untyped Fund", fund_type=None)
    assert is_error(r)
    assert r["message"] == "fund_type is required"
    rows = conn.execute("SELECT fund_name, total_allocation, available_amount "
                        "FROM finaid_fund_allocation").fetchall()
    assert [tuple(x) for x in rows] == [("FSEOG Campus Fund", "250000.00", "250000.00")]
