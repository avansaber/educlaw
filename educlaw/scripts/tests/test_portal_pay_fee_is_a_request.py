"""Portal fee "payment" is a request: no gateway, no money moves.

``edu-portal-pay-fee`` has no payment gateway behind it, so it must never
claim a payment was made. It records a payment *request* (one
``educlaw_notification`` row) and leaves the invoice balance untouched until
the school records the payment received against the invoice.

Setup uses a real fee invoice generated with ``edu-generate-fee-invoice``
(single Tuition line) so the ``sales_invoice`` total is hand-known: the exact
string ``"4000.00"``. Reads go through PyPika (``erpclaw_lib.query``) over a
connection from ``erpclaw_lib.db.get_connection``; money compares exact
``Decimal`` strings, never float.
"""
import argparse
import importlib.util
import io
import json
import os
import sys
import uuid
from decimal import Decimal
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
from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row

from helpers import (
    seed_academic_year, seed_academic_term, seed_program, seed_student,
    seed_guardian, call_action, ns, is_ok, is_error,
)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FE = _load("fees", _SCRIPTS_DIR).ACTIONS

SELLING = _load("db_query", os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-selling"))
INVENTORY = _load("db_query", os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-inventory"))

POSTING_DATE = "2026-03-02"
DUE_DATE = "2026-04-01"

# Hand-known invoice total used by every test below (exact string).
TOTAL = "4000.00"

NOTE = ("No payment was taken. This records a request only; the balance is "
        "unchanged until the school records the payment received against "
        "the invoice.")


def make_full_db(path):
    """Provision the real foundation schema plus the educlaw core tables."""
    init_path = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "init_schema.py")
    spec = importlib.util.spec_from_file_location("pay_req_init_schema", init_path)
    init_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_mod)
    init_mod.init_db(path)
    edu_path = os.path.join(_SRC_DIR, "educlaw", "educlaw", "init_db.py")
    spec = importlib.util.spec_from_file_location("pay_req_educlaw_init", edu_path)
    edu_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edu_mod)
    edu_mod.create_educlaw_tables(path)
    return path


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "portal_pay_request.sqlite")
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
    selling = SELLING
    inventory = INVENTORY
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
    """Company plus submit prerequisites, academic setup and one student."""
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
    gid = seed_guardian(conn, cid)
    link_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact)
           VALUES (?, ?, ?, 'mother', 1, 1, 1, 1, 1)""",
        (link_id, sid, gid))
    conn.commit()
    return {"company_id": cid, "year_id": yid, "term_id": tid,
            "program_id": pid, "student_id": sid, "guardian_id": gid,
            "receivable_id": recv_id, "income_id": inc_id}


def setup_tuition_4000(conn, env):
    """Single Tuition line of exactly 4000.00; total is the hand-known TOTAL."""
    tuition = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Tuition", description="tuition",
        revenue_account_id=None))
    assert is_ok(tuition), tuition
    fs = call_action(FE["edu-add-fee-structure"], conn, ns(
        company_id=env["company_id"], name="FS-4000",
        program_id=env["program_id"], academic_term_id=env["term_id"],
        grade_level=None,
        items=json.dumps([
            {"fee_category_id": tuition["id"], "amount": TOTAL,
             "description": "tuition", "sort_order": 1}])))
    assert is_ok(fs), fs
    assert fs["total_amount"] == TOTAL
    return fs


def add_payment_method(conn, env, last_four="4242"):
    r = call_action(FE["edu-add-payment-method"], conn, ns(
        guardian_id=env["guardian_id"],
        payment_method_type="credit_card",
        method_type=None,
        company_id=env["company_id"],
        last_four=last_four,
        is_default=None, autopay_enabled=None,
        external_token=None, status=None,
        limit=50, offset=0))
    assert is_ok(r), r
    return r


def generate_invoice(conn, env, db_path):
    r = call_action(FE["edu-generate-fee-invoice"], conn, ns(
        student_id=env["student_id"], program_id=env["program_id"],
        academic_term_id=env["term_id"], company_id=env["company_id"],
        posting_date=POSTING_DATE, due_date=DUE_DATE,
        db_path=db_path, user_id=None))
    assert is_ok(r), r
    assert r["final_amount"] == TOTAL
    return r


def setup_billed(conn, env, db_path):
    setup_tuition_4000(conn, env)
    add_payment_method(conn, env)
    return generate_invoice(conn, env, db_path)


def portal_pay(conn, env, amount):
    return call_action(FE["edu-portal-pay-fee"], conn, ns(
        guardian_id=env["guardian_id"],
        student_id=env["student_id"],
        amount=amount,
        company_id=env["company_id"],
        limit=50, offset=0))


def _table_snapshot(conn, table):
    t = Table(table)
    try:
        rows = conn.execute(Q.from_(t).select(t.star).get_sql()).fetchall()
    except Exception:
        return []
    return sorted(repr(dict(r)) for r in rows)


def _notifications(conn):
    t = Table("educlaw_notification")
    return [dict(r) for r in conn.execute(
        Q.from_(t).select(t.star).get_sql()).fetchall()]


def _sales_invoice(conn, si_id):
    t = Table("sales_invoice")
    row = conn.execute(
        Q.from_(t).select(t.star).where(t.id == P()).get_sql(),
        (si_id,)).fetchone()
    return dict(row) if row is not None else None


def test_request_does_not_claim_payment(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    gen = setup_billed(conn, env, db_path)
    assert gen["final_amount"] == TOTAL

    r = portal_pay(conn, env, "1000.00")
    assert is_ok(r), r
    assert r["payment_status"] == "requested"
    assert r["amount"] == "1000.00"
    assert r["outstanding_amount"] == TOTAL
    assert r["note"] == NOTE
    assert "payment_reference" in r and r["payment_reference"]
    ids = [i["id"] for i in r["invoices"]]
    assert gen["sales_invoice_id"] in ids
    for inv in r["invoices"]:
        assert inv["outstanding_amount"] == TOTAL


def test_request_moves_no_money(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    gen = setup_billed(conn, env, db_path)
    si_id = gen["sales_invoice_id"]

    before_si = _table_snapshot(conn, "sales_invoice")
    before_pe = _table_snapshot(conn, "payment_entry")
    before_gl = _table_snapshot(conn, "gl_entry")
    before_notifs = _notifications(conn)

    r = portal_pay(conn, env, "1000.00")
    assert is_ok(r), r

    assert _table_snapshot(conn, "sales_invoice") == before_si
    assert _table_snapshot(conn, "payment_entry") == before_pe
    assert _table_snapshot(conn, "gl_entry") == before_gl
    si = _sales_invoice(conn, si_id)
    assert si["outstanding_amount"] == TOTAL

    after_notifs = _notifications(conn)
    assert len(after_notifs) == len(before_notifs) + 1
    fresh = [n for n in after_notifs
             if n["id"] not in {m["id"] for m in before_notifs}]
    assert len(fresh) == 1
    assert fresh[0]["title"] == "Payment Request Received"


def test_amount_above_outstanding_refused(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    setup_billed(conn, env, db_path)
    over = str(Decimal(TOTAL) + Decimal("0.01"))
    assert over == "4000.01"

    before_notifs = _notifications(conn)
    r = portal_pay(conn, env, over)
    assert is_error(r), r
    assert TOTAL in r["message"]
    assert over in r["message"]
    assert _notifications(conn) == before_notifs


def test_nothing_outstanding_refused(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    add_payment_method(conn, env)
    fresh_student = seed_student(conn, env["company_id"])
    link_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact)
           VALUES (?, ?, ?, 'mother', 1, 1, 1, 1, 1)""",
        (link_id, fresh_student, env["guardian_id"]))
    conn.commit()

    before_notifs = _notifications(conn)
    r = call_action(FE["edu-portal-pay-fee"], conn, ns(
        guardian_id=env["guardian_id"],
        student_id=fresh_student,
        amount="10.00",
        company_id=env["company_id"],
        limit=50, offset=0))
    assert is_error(r), r
    assert r["message"] == "No outstanding fees for this student"
    assert _notifications(conn) == before_notifs


def test_unlinked_guardian_refused(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    setup_billed(conn, env, db_path)
    stranger = seed_guardian(conn, env["company_id"])
    before_notifs = _notifications(conn)
    r = call_action(FE["edu-portal-pay-fee"], conn, ns(
        guardian_id=stranger,
        student_id=env["student_id"],
        amount="10.00",
        company_id=env["company_id"],
        limit=50, offset=0))
    assert is_error(r), r
    assert r["message"] == "Guardian is not linked to this student"
    assert _notifications(conn) == before_notifs


def test_no_active_payment_method_refused(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    setup_tuition_4000(conn, env)
    generate_invoice(conn, env, db_path)
    bare_guardian = seed_guardian(conn, env["company_id"])
    link_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact)
           VALUES (?, ?, ?, 'father', 1, 1, 1, 0, 0)""",
        (link_id, env["student_id"], bare_guardian))
    conn.commit()
    before_notifs = _notifications(conn)
    r = call_action(FE["edu-portal-pay-fee"], conn, ns(
        guardian_id=bare_guardian,
        student_id=env["student_id"],
        amount="10.00",
        company_id=env["company_id"],
        limit=50, offset=0))
    assert is_error(r), r
    assert r["message"] == "No active payment method found. Add a payment method first."
    assert _notifications(conn) == before_notifs


def test_non_positive_amount_refused(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    delegate_selling_in_process(conn, monkeypatch)
    setup_billed(conn, env, db_path)
    before_notifs = _notifications(conn)
    r = portal_pay(conn, env, "0")
    assert is_error(r), r
    assert r["message"] == "--amount must be greater than 0"
    assert _notifications(conn) == before_notifs
