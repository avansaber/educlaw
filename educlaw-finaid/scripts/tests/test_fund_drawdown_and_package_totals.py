"""Fund allocation commit/draw-down and package totals excluding declined awards.

A fund allocation is a budget: accepting an award commits the accepted amount
(available goes down), over-acceptance is refused, decline/cancel/delete
releases the commitment, disbursement draws disbursed up and reversal draws it
back down. Package totals count only live awards. No handler here posts to the
general ledger.
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
        "term_id": tid, "program_enrollment_id": peid, "isir_id": isir_id,
        "cost_of_attendance_id": coa_id,
    }
    conn.close()


def _fund(s, name="FSEOG Campus Fund", total="5000.00", fund_type="fseog",
          aid_year_id=None, company_id=None):
    r = call_action(FA_ACTIONS["finaid-add-fund-allocation"], s["conn"], ns(
        aid_year_id=aid_year_id or s["aid_year_id"],
        company_id=company_id or s["company_id"],
        fund_type=fund_type, fund_name=name, total_allocation=total))
    assert is_ok(r), r
    return r["id"]


def _package(s):
    r = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
        student_id=s["student_id"], aid_year_id=s["aid_year_id"],
        academic_term_id=s["term_id"], company_id=s["company_id"],
        program_enrollment_id=s["program_enrollment_id"], isir_id=s["isir_id"],
        cost_of_attendance_id=s["cost_of_attendance_id"],
        enrollment_status="full_time",
        financial_need=None, acceptance_deadline=None, packaged_by=None, notes=None))
    assert is_ok(r), r
    return r["id"]


def _award(s, pkg_id, aid_type="fseog", offered="3000.00", fund_id=None):
    r = call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
        award_package_id=pkg_id, student_id=s["student_id"],
        aid_year_id=s["aid_year_id"], academic_term_id=s["term_id"],
        aid_type=aid_type, aid_source="federal", offered_amount=offered,
        company_id=s["company_id"], fund_source_id=fund_id,
        gl_account_id=None, notes=None))
    assert is_ok(r), r
    return r["id"]


def _accept(s, award_id, amount):
    return call_action(FA_ACTIONS["finaid-accept-award"], s["conn"], ns(
        award_id=award_id, accepted_amount=amount, acceptance_date="2025-08-01"))


def _decline(s, award_id):
    return call_action(FA_ACTIONS["finaid-deny-award"], s["conn"], ns(
        award_id=award_id))


def _F(conn, fund_id):
    row = conn.execute(
        "SELECT total_allocation, committed_amount, disbursed_amount, available_amount "
        "FROM finaid_fund_allocation WHERE id = ?", (fund_id,)).fetchone()
    return tuple(row)


def _snap(conn, tables):
    snap = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        snap[table] = sorted(
            tuple("" if value is None else str(value) for value in row)
            for row in rows
        )
    return snap


def _totals(conn, pkg_id):
    row = conn.execute(
        "SELECT total_grants, total_loans, total_work_study, total_aid "
        "FROM finaid_award_package WHERE id = ?", (pkg_id,)).fetchone()
    return tuple(row)


TABLES3 = ["finaid_award", "finaid_fund_allocation", "finaid_award_package"]


def test_accept_commits_reaccept_moves_difference_decline_releases(env):
    s, conn = env, env["conn"]
    fund_id = _fund(s)
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, offered="3000.00", fund_id=fund_id)
    r = _accept(s, award_id, "2000.00")
    assert is_ok(r), r
    assert _F(conn, fund_id) == ("5000.00", "2000.00", "0", "3000.00")
    assert is_ok(_accept(s, award_id, "2500.00"))
    assert _F(conn, fund_id) == ("5000.00", "2500.00", "0", "2500.00")
    assert is_ok(_decline(s, award_id))
    assert _F(conn, fund_id) == ("5000.00", "0.00", "0", "5000.00")


def test_over_allocation_refuses_and_writes_nothing(env):
    s, conn = env, env["conn"]
    fund_id = _fund(s)
    pkg_id = _package(s)
    award_a = _award(s, pkg_id, offered="3000.00", fund_id=fund_id)
    assert is_ok(_accept(s, award_a, "2000.00"))
    award_b = _award(s, pkg_id, offered="3500.00", fund_id=fund_id)
    before = _snap(conn, TABLES3)
    r = _accept(s, award_b, "3500.00")
    assert is_error(r)
    assert r["message"] == (
        "Fund allocation FSEOG Campus Fund has 3000.00 available; "
        "accepting 3500.00 needs 3500.00")
    assert _snap(conn, TABLES3) == before
    assert is_ok(_accept(s, award_b, "3000.00"))
    assert _F(conn, fund_id) == ("5000.00", "5000.00", "0", "0.00")


def test_disbursement_draws_and_reversal_returns(env):
    s, conn = env, env["conn"]
    fund_id = _fund(s)
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, offered="3000.00", fund_id=fund_id)
    assert is_ok(_accept(s, award_id, "2000.00"))
    r = call_action(FA_ACTIONS["finaid-record-award-disbursement"], conn, ns(
        award_id=award_id, student_id=s["student_id"], amount="1500.00",
        disbursement_date="2025-09-02", company_id=s["company_id"],
        disbursed_by="bursar", disbursement_number=1))
    assert is_ok(r), r
    assert _F(conn, fund_id) == ("5000.00", "2000.00", "1500.00", "3000.00")
    r = call_action(FA_ACTIONS["finaid-cancel-disbursement"], conn, ns(
        award_id=award_id, amount="500.00", disbursement_date="2025-09-20",
        company_id=s["company_id"]))
    assert is_ok(r), r
    assert _F(conn, fund_id) == ("5000.00", "2000.00", "1000.00", "3000.00")


def test_cancel_package_and_delete_award_release(env):
    s, conn = env, env["conn"]
    fund_id = _fund(s)
    pkg1 = _package(s)
    award1 = _award(s, pkg1, offered="3000.00", fund_id=fund_id)
    assert is_ok(_accept(s, award1, "2000.00"))
    r = call_action(FA_ACTIONS["finaid-cancel-award-package"], conn, ns(
        award_package_id=pkg1))
    assert is_ok(r), r
    assert _F(conn, fund_id) == ("5000.00", "0.00", "0", "5000.00")
    pkg2 = _package(s)
    award2 = _award(s, pkg2, offered="3000.00", fund_id=fund_id)
    assert is_ok(_accept(s, award2, "1200.00"))
    assert _F(conn, fund_id) == ("5000.00", "1200.00", "0", "3800.00")
    r = call_action(FA_ACTIONS["finaid-delete-award"], conn, ns(
        award_id=award2))
    assert is_ok(r), r
    assert _F(conn, fund_id) == ("5000.00", "0.00", "0", "5000.00")


def test_update_fund_allocation_refuses_total_below_committed(env):
    s, conn = env, env["conn"]
    fund_id = _fund(s)
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, offered="3000.00", fund_id=fund_id)
    assert is_ok(_accept(s, award_id, "2000.00"))
    before = _F(conn, fund_id)
    r = call_action(FA_ACTIONS["finaid-update-fund-allocation"], conn, ns(
        id=fund_id, total_allocation="1999.99"))
    assert is_error(r)
    assert r["message"] == (
        "total_allocation 1999.99 is below the committed amount 2000.00")
    assert _F(conn, fund_id) == before
    r = call_action(FA_ACTIONS["finaid-update-fund-allocation"], conn, ns(
        id=fund_id, total_allocation="4000.00"))
    assert is_ok(r), r
    assert _F(conn, fund_id) == ("4000.00", "2000.00", "0", "2000.00")


def test_award_without_a_fund_allocation_draws_nothing(env):
    s, conn = env, env["conn"]
    fund_id = _fund(s)
    pkg_id = _package(s)
    award_none = _award(s, pkg_id, aid_type="pell", offered="5000.00",
                        fund_id=None)
    assert is_ok(_accept(s, award_none, "4000.00"))
    award_ext = _award(s, pkg_id, aid_type="pell", offered="5000.00",
                       fund_id="external-sponsor-1")
    assert is_ok(_accept(s, award_ext, "4000.00"))
    assert _F(conn, fund_id) == ("5000.00", "0", "0", "5000.00")


def test_fund_of_another_company_refuses(env):
    s, conn = env, env["conn"]
    cid2 = _helpers.seed_company(conn)
    aid2 = _helpers.seed_aid_year(conn, cid2)
    other_id = _fund(s, name="Other Campus Fund", aid_year_id=aid2,
                     company_id=cid2)
    pkg_id = _package(s)
    award_id = _award(s, pkg_id, offered="3000.00", fund_id=other_id)
    before = _snap(conn, TABLES3)
    r = _accept(s, award_id, "2000.00")
    assert is_error(r)
    assert r["message"] == f"Fund allocation {other_id} belongs to another company"
    assert _snap(conn, TABLES3) == before


def test_package_totals_exclude_declined_and_cancelled_awards(env):
    s, conn = env, env["conn"]
    pkg_id = _package(s)
    _award(s, pkg_id, aid_type="pell", offered="5000.00", fund_id=None)
    loan_id = _award(s, pkg_id, aid_type="subsidized_loan", offered="3500.00",
                     fund_id=None)
    _award(s, pkg_id, aid_type="fws", offered="1200.00", fund_id=None)
    assert is_ok(_decline(s, loan_id))
    assert _totals(conn, pkg_id) == ("5000.00", "0.00", "1200.00", "6200.00")
    r = call_action(FA_ACTIONS["finaid-cancel-award-package"], conn, ns(
        award_package_id=pkg_id))
    assert is_ok(r), r
    assert _totals(conn, pkg_id) == ("0.00", "0.00", "0.00", "0.00")


def test_create_award_package_refuses_missing_or_unknown_links(env):
    s, conn = env, env["conn"]
    count_before = conn.execute(
        "SELECT COUNT(*) FROM finaid_award_package").fetchone()[0]

    def _create(**overrides):
        args = dict(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            academic_term_id=s["term_id"], company_id=s["company_id"],
            program_enrollment_id=s["program_enrollment_id"],
            isir_id=s["isir_id"],
            cost_of_attendance_id=s["cost_of_attendance_id"],
            enrollment_status="full_time")
        args.update(overrides)
        return call_action(
            FA_ACTIONS["finaid-create-award-package"], conn, ns(**args))

    cases = [
        (dict(program_enrollment_id=None), "program_enrollment_id is required"),
        (dict(isir_id=None), "isir_id is required"),
        (dict(cost_of_attendance_id=None), "cost_of_attendance_id is required"),
        (dict(enrollment_status=None), "enrollment_status is required"),
        (dict(enrollment_status="part_time"),
         "enrollment_status must be one of "
         "full_time, three_quarter, half_time, less_than_half"),
        (dict(program_enrollment_id="no-such-enrollment"),
         "Program enrollment no-such-enrollment not found"),
        (dict(isir_id="no-such-isir"), "ISIR no-such-isir not found"),
        (dict(cost_of_attendance_id="no-such-coa"),
         "Cost of attendance no-such-coa not found"),
    ]
    for kwargs, message in cases:
        r = _create(**kwargs)
        assert is_error(r), (kwargs, r)
        assert r["message"] == message, (kwargs, r)
    count_after = conn.execute(
        "SELECT COUNT(*) FROM finaid_award_package").fetchone()[0]
    assert count_after == count_before
