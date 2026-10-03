"""Withdrawing a student from a program names the fee bills still open.

``edu-cancel-program-enrollment`` flips the enrollment to ``withdrawn`` and
leaves every bill untouched, but the response now lists the student's open
fee invoices (through ``educlaw_fee_invoice`` to the foundation
``sales_invoice``) with the total still owed, so the school knows the bill
needs a decision under its refund policy.

Setup below is copied from ``test_fee_invoice_bills_through_selling.py``
(real foundation schema plus educlaw tables, real selling-module billing
in-process); nothing is imported across test files. The fee structure holds
a single Tuition line of 4000.00, so every expected amount is the
hand-computed string "4000.00". Money compares exact strings, never float.
"""
import argparse
import importlib.util
import io
import json
import os
import sys
import uuid
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
_LIB_DIR = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if os.path.isdir(os.path.join(_LIB_DIR, "erpclaw_lib")) and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, Order, insert_row
from erpclaw_lib import seam as _seam

from helpers import (
    seed_academic_year, seed_academic_term, seed_program, seed_student,
    call_action, ns, is_ok, is_error,
)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FE = _load("fees", _SCRIPTS_DIR).ACTIONS
EN = _load("enrollment", _SCRIPTS_DIR).ACTIONS

POSTING_DATE = "2026-03-02"
DUE_DATE = "2026-04-01"

# Single Tuition line: 4000.00 billed, 4000.00 owed.
TUITION_TOTAL = "4000.00"


def make_full_db(path):
    """Provision the real foundation schema plus the educlaw core tables."""
    init_path = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "init_schema.py")
    spec = importlib.util.spec_from_file_location("wdw_init_schema", init_path)
    init_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_mod)
    init_mod.init_db(path)
    edu_path = os.path.join(_SRC_DIR, "educlaw", "educlaw", "init_db.py")
    spec = importlib.util.spec_from_file_location("wdw_educlaw_init", edu_path)
    edu_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edu_mod)
    edu_mod.create_educlaw_tables(path)
    return path


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "withdraw_bills.sqlite")
    make_full_db(path)
    os.environ["ERPCLAW_DB_PATH"] = path
    try:
        yield path
    finally:
        os.environ.pop("ERPCLAW_DB_PATH", None)


@pytest.fixture
def conn(db_path):
    from erpclaw_lib.cross_skill import _SERVICE_ITEM_CACHE
    _SERVICE_ITEM_CACHE.clear()
    handle = get_connection(db_path)
    try:
        yield handle
    finally:
        handle.close()


def delegate_selling_in_process(conn, monkeypatch):
    """Redirect cross_skill.call_skill_action to the REAL foundation functions."""
    def _load_domain(domain):
        path = os.path.join(_SRC_DIR, "erpclaw", "scripts", domain, "db_query.py")
        spec = importlib.util.spec_from_file_location("_wdw_%s" % domain, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    selling = _load_domain("erpclaw-selling")
    inventory = _load_domain("erpclaw-inventory")
    from erpclaw_lib import cross_skill as _cs
    captured = {}

    def _run(fn, args_ns):
        buf = io.StringIO()

        def _fake_exit(code=0):
            raise SystemExit(code)

        try:
            with patch("sys.stdout", buf), patch("sys.exit", side_effect=_fake_exit):
                fn(conn, args_ns)
        except SystemExit:
            pass
        return json.loads(buf.getvalue().strip())

    def _in_process(skill_name, action, args=None, db_path=None, timeout=30):
        flags = dict(args or {})
        captured.setdefault("calls", []).append(
            {"skill": skill_name, "action": action, "args": flags})
        if action == "add-item":
            result = _run(inventory.add_item, argparse.Namespace(
                item_code=flags.get("--item-code"),
                item_name=flags.get("--item-name"),
                item_type=flags.get("--item-type"),
                valuation_method=None, item_group=None, stock_uom=None,
                has_batch=None, has_serial=None, standard_rate=None,
                custom_fields=None))
        elif action == "list-items":
            result = _run(inventory.list_items, argparse.Namespace(
                item_group=None, item_type=None, search=flags.get("--search"),
                limit="20", offset="0", warehouse_id=None, company_id=None))
        elif action == "add-customer":
            result = _run(selling.add_customer, argparse.Namespace(
                name=flags.get("--name"),
                company_id=flags.get("--company-id"),
                customer_type=flags.get("--customer-type"),
                customer_group=flags.get("--customer-group"),
                payment_terms_id=flags.get("--payment-terms-id"),
                credit_limit=flags.get("--credit-limit"),
                tax_id=flags.get("--tax-id"),
                exempt_from_sales_tax=flags.get("--exempt-from-sales-tax"),
                primary_address=flags.get("--primary-address"),
                primary_contact=flags.get("--primary-contact"),
                email=flags.get("--email"),
                phone=flags.get("--phone"),
                default_price_list_id=flags.get("--default-price-list-id"),
                custom_fields=flags.get("--custom-fields")))
        elif action == "create-sales-invoice":
            result = _run(selling.create_sales_invoice, argparse.Namespace(
                company_id=flags.get("--company-id"),
                customer_id=flags.get("--customer-id"),
                tax_template_id=None, sales_order_id=None,
                delivery_note_id=None,
                posting_date=flags.get("--posting-date"),
                due_date=flags.get("--due-date"),
                items=flags.get("--items"), payment_terms_id=None))
        elif action == "submit-sales-invoice":
            result = _run(selling.submit_sales_invoice, argparse.Namespace(
                sales_invoice_id=flags.get("--sales-invoice-id")))
        else:
            raise AssertionError("unexpected cross-skill action %s" % action)
        if result.get("status") == "error":
            raise _cs.CrossSkillError(
                result.get("message", "%s failed" % action))
        return result

    monkeypatch.setattr(_cs, "call_skill_action", _in_process)
    return captured


def seed_fee_env(conn):
    """Company with submit prerequisites, plus year/term/program/student."""
    cid = str(uuid.uuid4())
    sql, _ = insert_row("company", {"id": P(), "name": P(), "abbr": P(),
                                    "default_currency": P(), "country": P(),
                                    "fiscal_year_start_month": P()})
    conn.execute(sql, (cid, "Test School %s" % cid[:6], "TS%s" % cid[:4],
                       "USD", "United States", 1))
    recv_id = str(uuid.uuid4())
    sql, _ = insert_row("account", {"id": P(), "name": P(), "account_number": P(),
                                    "root_type": P(), "account_type": P(),
                                    "balance_direction": P(), "company_id": P(),
                                    "depth": P()})
    conn.execute(sql, (recv_id, "Debtors %s" % recv_id[:6], "1200-%s" % recv_id[:6],
                       "asset", "receivable", "debit_normal", cid, 0))
    inc_id = str(uuid.uuid4())
    conn.execute(sql, (inc_id, "Sales %s" % inc_id[:6], "4100-%s" % inc_id[:6],
                       "income", "revenue", "credit_normal", cid, 0))
    fy_id = str(uuid.uuid4())
    sql, _ = insert_row("fiscal_year", {"id": P(), "name": P(), "start_date": P(),
                                        "end_date": P(), "company_id": P()})
    conn.execute(sql, (fy_id, "FY-%s" % fy_id[:6], "2026-01-01", "2026-12-31", cid))
    cc_id = str(uuid.uuid4())
    sql, _ = insert_row("cost_center", {"id": P(), "name": P(), "company_id": P(),
                                        "is_group": P()})
    conn.execute(sql, (cc_id, "Main %s" % cc_id[:6], cid, 0))
    conn.commit()
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    pid = seed_program(conn, cid)
    sid = seed_student(conn, cid)
    return {"company_id": cid, "year_id": yid, "term_id": tid,
            "program_id": pid, "student_id": sid,
            "receivable_id": recv_id, "income_id": inc_id}


def setup_single_fee_structure(conn, env):
    """One Tuition line of 4000.00, so the billed total is 4000.00 by hand."""
    tuition = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Tuition", description="tuition",
        revenue_account_id=None))
    assert is_ok(tuition), tuition
    fs = call_action(FE["edu-add-fee-structure"], conn, ns(
        company_id=env["company_id"], name="FS-2026",
        program_id=env["program_id"], academic_term_id=env["term_id"],
        grade_level=None,
        items=json.dumps([
            {"fee_category_id": tuition["id"], "amount": TUITION_TOTAL,
             "description": "tuition", "sort_order": 1}])))
    assert is_ok(fs), fs
    assert fs["total_amount"] == TUITION_TOTAL
    return {"fs_id": fs["id"], "tuition_id": tuition["id"]}


def enroll_ok(conn, env):
    r = call_action(EN["edu-create-program-enrollment"], conn, ns(
        student_id=env["student_id"], program_id=env["program_id"],
        academic_year_id=env["year_id"], company_id=env["company_id"],
        enrollment_date=None))
    assert is_ok(r), r
    return r["id"]


def generate_fee_invoice_ok(conn, env, db_path):
    r = call_action(FE["edu-generate-fee-invoice"], conn, ns(
        student_id=env["student_id"], program_id=env["program_id"],
        academic_term_id=env["term_id"], company_id=env["company_id"],
        posting_date=POSTING_DATE, due_date=DUE_DATE,
        db_path=db_path, user_id=None))
    assert is_ok(r), r
    return r


def withdraw(conn, enrollment_id):
    return call_action(EN["edu-cancel-program-enrollment"], conn, ns(
        enrollment_id=enrollment_id))


def snapshot_table(conn, table):
    t = Table(table)
    rows = conn.execute(Q.from_(t).select(t.star).get_sql()).fetchall()
    return sorted(
        tuple(sorted((k, "--null--" if v is None else str(v))
                     for k, v in dict(r).items()))
        for r in rows
    )


def latest_withdraw_audit(conn, enrollment_id):
    t = Table("audit_log")
    rows = conn.execute(
        Q.from_(t).select(t.star)
        .where(t.entity_id == P()).where(t.action == P())
        .get_sql(),
        (enrollment_id, "edu-withdraw-from-program")).fetchall()
    assert len(rows) == 1, [dict(r) for r in rows]
    return dict(rows[0])


def test_withdrawal_names_open_bill(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_single_fee_structure(conn, env)
    delegate_selling_in_process(conn, monkeypatch)
    enrollment_id = enroll_ok(conn, env)
    first = generate_fee_invoice_ok(conn, env, db_path)
    si_id = first["sales_invoice_id"]

    r = withdraw(conn, enrollment_id)
    assert is_ok(r), r
    assert r["id"] == enrollment_id
    assert r["enrollment_status"] == "withdrawn"
    assert r["open_fee_invoices"] == [{
        "sales_invoice_id": si_id,
        "invoice_kind": "fee",
        "grand_total": TUITION_TOTAL,
        "outstanding_amount": TUITION_TOTAL,
    }]
    assert r["open_fee_balance"] == TUITION_TOTAL
    assert r["billing_review_required"] is True
    assert r["suggestion"] == (
        "This student still owes 4000.00 on 1 fee invoice(s). "
        "Withdrawal does not change the bill. Decide under the school's "
        "refund policy whether to keep, credit or refund it.")

    row = dict(conn.execute(
        Q.from_(Table("educlaw_program_enrollment")).select(Field("enrollment_status"))
        .where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone())
    assert row["enrollment_status"] == "withdrawn"

    audit_row = latest_withdraw_audit(conn, enrollment_id)
    new_values = json.loads(audit_row["new_values"])
    assert new_values["enrollment_status"] == "withdrawn"
    assert new_values["open_fee_invoices"] == [si_id]
    assert new_values["open_fee_balance"] == TUITION_TOTAL


def test_withdrawal_changes_no_bill(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_single_fee_structure(conn, env)
    delegate_selling_in_process(conn, monkeypatch)
    enrollment_id = enroll_ok(conn, env)
    generate_fee_invoice_ok(conn, env, db_path)

    before = {t: snapshot_table(conn, t) for t in
              ("sales_invoice", "payment_entry", "gl_entry")}
    assert len(before["sales_invoice"]) >= 1

    r = withdraw(conn, enrollment_id)
    assert is_ok(r), r

    after = {t: snapshot_table(conn, t) for t in
             ("sales_invoice", "payment_entry", "gl_entry")}
    assert after == before


def test_withdrawal_with_nothing_owed(conn):
    env = seed_fee_env(conn)
    enrollment_id = enroll_ok(conn, env)

    r = withdraw(conn, enrollment_id)
    assert is_ok(r), r
    assert r["enrollment_status"] == "withdrawn"
    assert r["open_fee_invoices"] == []
    assert r["open_fee_balance"] == "0.00"
    assert r["billing_review_required"] is False
    assert "suggestion" not in r

    audit_row = latest_withdraw_audit(conn, enrollment_id)
    new_values = json.loads(audit_row["new_values"])
    assert new_values["open_fee_invoices"] == []
    assert new_values["open_fee_balance"] == "0.00"


def test_other_company_and_paid_bills_not_listed(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_single_fee_structure(conn, env)
    delegate_selling_in_process(conn, monkeypatch)
    enrollment_id = enroll_ok(conn, env)
    first = generate_fee_invoice_ok(conn, env, db_path)

    # The fee is fully paid: outstanding 0.00 must not be listed.
    _si = Table("sales_invoice")
    conn.execute(
        Q.update(_si).set(_si.status, P()).set(_si.outstanding_amount, P())
        .where(_si.id == P()).get_sql(),
        ("paid", "0.00", first["sales_invoice_id"]))
    conn.commit()

    # A bill for the same student under a second company is not listed either.
    other_company = str(uuid.uuid4())
    sql, _ = insert_row("company", {"id": P(), "name": P(), "abbr": P(),
                                    "default_currency": P(), "country": P(),
                                    "fiscal_year_start_month": P()})
    conn.execute(sql, (other_company, "Other School %s" % other_company[:6],
                       "OS%s" % other_company[:4], "USD", "United States", 1))
    other_customer = str(uuid.uuid4())
    sql, _ = insert_row("customer", {"id": P(), "name": P(), "company_id": P()})
    conn.execute(sql, (other_customer, "Other Parent", other_company))
    other_invoice = str(uuid.uuid4())
    sql, _ = insert_row("sales_invoice",
                        {"id": P(), "naming_series": P(), "customer_id": P(),
                         "posting_date": P(), "due_date": P(),
                         "grand_total": P(), "outstanding_amount": P(),
                         "status": P(), "company_id": P()})
    conn.execute(sql, (other_invoice, "SINV-OTHER-1", other_customer,
                       "2026-02-01", "2026-03-01", "250.00", "250.00",
                       "submitted", other_company))
    sql, _ = insert_row("educlaw_fee_invoice",
                        {"id": P(), "student_id": P(), "invoice_kind": P(),
                         "sales_invoice_id": P(), "amount": P(),
                         "company_id": P(), "created_by": P()})
    conn.execute(sql, (str(uuid.uuid4()), env["student_id"], "fee",
                       other_invoice, "250.00", other_company, ""))
    conn.commit()

    r = withdraw(conn, enrollment_id)
    assert is_ok(r), r
    assert r["enrollment_status"] == "withdrawn"
    assert r["open_fee_invoices"] == []
    assert r["open_fee_balance"] == "0.00"
    assert r["billing_review_required"] is False
    assert "suggestion" not in r


def test_fee_read_failure_is_not_reported_as_nothing_owed(conn):
    env = seed_fee_env(conn)
    enrollment_id = enroll_ok(conn, env)
    notif_before = snapshot_table(conn, "educlaw_notification")
    audit_before = snapshot_table(conn, "audit_log")

    class _FailingReadConn:
        def __init__(self, inner):
            object.__setattr__(self, "_inner", inner)

        def execute(self, sql, params=()):
            if "educlaw_fee_invoice" in str(sql):
                raise RuntimeError("simulated fee read failure")
            return self._inner.execute(sql, params)

        def __getattr__(self, name):
            return getattr(object.__getattribute__(self, "_inner"), name)

    try:
        r = call_action(EN["edu-cancel-program-enrollment"], _FailingReadConn(conn), ns(
            enrollment_id=enrollment_id))
    except RuntimeError as exc:
        conn.rollback()
        r = {"status": "error", "message": str(exc)}
    assert is_error(r), r
    assert "open_fee_balance" not in r
    row = conn.execute(
        Q.from_(Table("educlaw_program_enrollment")).select(Field("enrollment_status"))
        .where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    assert dict(row)["enrollment_status"] == "active"
    assert snapshot_table(conn, "educlaw_notification") == notif_before
    assert snapshot_table(conn, "audit_log") == audit_before


def test_unreadable_amount_refuses_before_any_write(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_single_fee_structure(conn, env)
    delegate_selling_in_process(conn, monkeypatch)
    enrollment_id = enroll_ok(conn, env)
    first = generate_fee_invoice_ok(conn, env, db_path)
    si_id = first["sales_invoice_id"]
    _si = Table("sales_invoice")
    conn.execute(
        Q.update(_si).set(_si.outstanding_amount, P())
        .where(_si.id == P()).get_sql(),
        ("abc", si_id))
    conn.commit()
    sales_before = snapshot_table(conn, "sales_invoice")
    notif_before = snapshot_table(conn, "educlaw_notification")
    audit_before = snapshot_table(conn, "audit_log")
    r = withdraw(conn, enrollment_id)
    assert is_error(r), r
    assert r["message"] == (
        "Cannot withdraw: fee invoice %s has an unreadable amount; "
        "correct it in selling before withdrawing" % si_id)
    row = conn.execute(
        Q.from_(Table("educlaw_program_enrollment")).select(Field("enrollment_status"))
        .where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    assert dict(row)["enrollment_status"] == "active"
    assert snapshot_table(conn, "educlaw_notification") == notif_before
    assert snapshot_table(conn, "audit_log") == audit_before
    assert snapshot_table(conn, "sales_invoice") == sales_before


def test_withdrawal_refuses_missing_id(conn):
    tables = ("educlaw_program_enrollment", "educlaw_notification", "audit_log")
    before = {t: snapshot_table(conn, t) for t in tables}
    r = withdraw(conn, None)
    assert is_error(r)
    assert r["message"] == "--enrollment-id is required"
    assert {t: snapshot_table(conn, t) for t in tables} == before


def test_withdrawal_refuses_unknown_enrollment(conn):
    tables = ("educlaw_program_enrollment", "educlaw_notification", "audit_log")
    before = {t: snapshot_table(conn, t) for t in tables}
    r = withdraw(conn, "no-such-enrollment")
    assert is_error(r)
    assert r["message"] == "Program enrollment no-such-enrollment not found"
    assert {t: snapshot_table(conn, t) for t in tables} == before


def test_withdrawal_refuses_non_active_enrollment(conn):
    env = seed_fee_env(conn)
    enrollment_id = enroll_ok(conn, env)
    first = withdraw(conn, enrollment_id)
    assert is_ok(first), first

    tables = ("educlaw_program_enrollment", "educlaw_notification", "audit_log")
    before = {t: snapshot_table(conn, t) for t in tables}
    r = withdraw(conn, enrollment_id)
    assert is_error(r)
    assert r["message"] == "Only active enrollments can be withdrawn (current: withdrawn)"
    assert {t: snapshot_table(conn, t) for t in tables} == before
