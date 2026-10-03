"""Educlaw fee invoices bill through the selling module.

A fee invoice IS a sales invoice. ``edu-generate-fee-invoice`` creates it
through the selling module's own ``create-sales-invoice`` action and submits
it through ``submit-sales-invoice``; educlaw stores the link in its own
``educlaw_fee_invoice`` table. A fee structure is billed to a student once; a
late fee is its own sales invoice tied to one overdue fee invoice and refused
a second time; a scholarship limited to one fee category discounts only that
category's line.

Every database read-back below goes through PyPika (``erpclaw_lib.query``)
over a connection from ``erpclaw_lib.db.get_connection``; catalog questions
go to ``erpclaw_lib.seam``. Money compares exact ``Decimal`` strings, never
float. The selling/inventory calls run in-process through the same delegate
shape as constructclaw's ``test_progress_bill_g703.py`` (real foundation
functions, recording exactly which action and flags the vertical sent), plus
an ``add-customer`` branch that passes every attribute ``add_customer``
reads. Each test fails before the fix: there is no sales invoice, no link
table, and no refusal.
"""
import argparse
import importlib.util
import io
import json
import os
import sys
import uuid
from datetime import date
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
from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, line_order
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

POSTING_DATE = "2026-03-02"
DUE_DATE = "2026-04-01"

SNAPSHOT_TABLES = (
    "sales_invoice",
    "sales_invoice_item",
    "gl_entry",
    "customer",
    "item",
    "educlaw_fee_invoice",
    "educlaw_notification",
    "educlaw_student",
    "audit_log",
)


def make_full_db(path):
    """Provision the real foundation schema plus the educlaw core tables."""
    init_path = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "init_schema.py")
    spec = importlib.util.spec_from_file_location("fee_sell_init_schema", init_path)
    init_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_mod)
    init_mod.init_db(path)
    edu_path = os.path.join(_SRC_DIR, "educlaw", "educlaw", "init_db.py")
    spec = importlib.util.spec_from_file_location("fee_sell_educlaw_init", edu_path)
    edu_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edu_mod)
    edu_mod.create_educlaw_tables(path)
    return path


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "fee_sell.sqlite")
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
    """Redirect cross_skill.call_skill_action to the REAL foundation functions.

    A copy of ``_delegate_selling_in_process`` from constructclaw's
    ``test_progress_bill_g703.py``, with an ``add-customer`` branch added that
    calls selling ``add_customer`` with every attribute it reads. Keeps every
    assertion real (customer, item resolution, totals, GL postings) while
    recording exactly which action and flags the vertical sent through the
    shared library.
    """
    def _load_domain(domain):
        path = os.path.join(_SRC_DIR, "erpclaw", "scripts", domain, "db_query.py")
        spec = importlib.util.spec_from_file_location("_fee_sell_%s" % domain, path)
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
    """Company as construct_helpers.seed_company, plus submit prerequisites."""
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


def setup_fee_structure(conn, env):
    """Tuition 5000.00 (sort 1), Lab Fees 500.00 (sort 2), total 5500.00."""
    tuition = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Tuition", description="tuition",
        revenue_account_id=None))
    assert is_ok(tuition), tuition
    lab = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Lab Fees", description="lab",
        revenue_account_id=None))
    assert is_ok(lab), lab
    fs = call_action(FE["edu-add-fee-structure"], conn, ns(
        company_id=env["company_id"], name="FS-2026",
        program_id=env["program_id"], academic_term_id=env["term_id"],
        grade_level=None,
        items=json.dumps([
            {"fee_category_id": tuition["id"], "amount": "5000.00",
             "description": "tuition", "sort_order": 1},
            {"fee_category_id": lab["id"], "amount": "500.00",
             "description": "lab", "sort_order": 2}])))
    assert is_ok(fs), fs
    assert fs["total_amount"] == "5500.00"
    return {"fs_id": fs["id"], "tuition_id": tuition["id"], "lab_id": lab["id"]}


def award_scholarship(conn, env, discount_type="fixed", discount_amount="1000",
                      applies_to_category_id=None):
    sch = call_action(FE["edu-add-scholarship"], conn, ns(
        student_id=env["student_id"], name="Merit Award",
        discount_type=discount_type, discount_amount=discount_amount,
        company_id=env["company_id"], academic_term_id=None,
        applies_to_category_id=applies_to_category_id,
        reason=None, approved_by=None))
    assert is_ok(sch), sch
    return sch["id"]


def generate_fee_invoice_ok(conn, env, db_path, **overrides):
    params = dict(student_id=env["student_id"], program_id=env["program_id"],
                  academic_term_id=env["term_id"], company_id=env["company_id"],
                  posting_date=POSTING_DATE, due_date=DUE_DATE,
                  db_path=db_path, user_id=None)
    params.update(overrides)
    r = call_action(FE["edu-generate-fee-invoice"], conn, ns(**params))
    assert is_ok(r), r
    return r


def _row(conn, table, rid):
    t = Table(table)
    row = conn.execute(
        Q.from_(t).select(t.star).where(t.id == P()).get_sql(), (rid,)).fetchone()
    return dict(row) if row is not None else None


def read_lines(conn, sales_invoice_id):
    t = Table("sales_invoice_item")
    return [dict(r) for r in conn.execute(
        Q.from_(t).select(t.star).where(t.sales_invoice_id == P())
        .orderby(line_order(t)).get_sql(), (sales_invoice_id,)).fetchall()]


def read_gl(conn, sales_invoice_id):
    t = Table("gl_entry")
    return [dict(r) for r in conn.execute(
        Q.from_(t).select(t.star)
        .where(t.voucher_type == P()).where(t.voucher_id == P()).get_sql(),
        ("sales_invoice", sales_invoice_id,)).fetchall()]


def read_fee_link(conn, sales_invoice_id):
    try:
        t = Table("educlaw_fee_invoice")
        row = conn.execute(
            Q.from_(t).select(t.star).where(t.sales_invoice_id == P()).get_sql(),
            (sales_invoice_id,)).fetchone()
    except Exception:
        return None
    return dict(row) if row is not None else None


def snapshot_tables(conn):
    snap = {}
    for name in SNAPSHOT_TABLES:
        try:
            t = Table(name)
            rows = conn.execute(Q.from_(t).select(t.star).get_sql()).fetchall()
            snap[name] = sorted(repr(dict(r)) for r in rows)
        except Exception:
            snap[name] = []
    return snap


def item_code(conn, item_id):
    row = _row(conn, "item", item_id)
    assert row is not None
    return row["item_code"]


def _notifications_for(conn, reference_id):
    t = Table("educlaw_notification")
    return [dict(r) for r in conn.execute(
        Q.from_(t).select(t.star).where(t.reference_id == P()).get_sql(),
        (reference_id,)).fetchall()]


def test_fee_invoice_is_a_submitted_sales_invoice(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup = setup_fee_structure(conn, env)
    award_scholarship(conn, env)
    captured = delegate_selling_in_process(conn, monkeypatch)
    r = generate_fee_invoice_ok(conn, env, db_path)

    assert r["sales_invoice_status"] == "submitted"
    assert "note" not in r
    si_id = r["sales_invoice_id"]
    student = _row(conn, "educlaw_student", env["student_id"])
    assert student["customer_id"]
    assert r["customer_id"] == student["customer_id"]
    assert r["base_amount"] == "5500.00"
    assert r["total_discount"] == "1000.00"
    assert r["final_amount"] == "4500.00"
    assert r["scholarships_applied"][0]["applied_discount"] == "1000.00"
    assert [(i["discount"], i["billed_amount"]) for i in r["line_items"]] == [
        ("1000.00", "4000.00"), ("0.00", "500.00")]

    si = _row(conn, "sales_invoice", si_id)
    assert si["status"] == "submitted"
    assert si["customer_id"] == student["customer_id"]
    assert si["total_amount"] == "4500.00"
    assert si["grand_total"] == "4500.00"
    assert si["outstanding_amount"] == "4500.00"
    assert si["posting_date"] == POSTING_DATE
    assert si["due_date"] == DUE_DATE

    lines = read_lines(conn, si_id)
    assert len(lines) == 2
    assert (lines[0]["quantity"], lines[0]["rate"], lines[0]["amount"],
            lines[0]["net_amount"]) == ("1.00", "4000.00", "4000.00", "4000.00")
    assert item_code(conn, lines[0]["item_id"]) == "EDU-FEE-%s" % setup["tuition_id"]
    assert (lines[1]["quantity"], lines[1]["rate"], lines[1]["amount"],
            lines[1]["net_amount"]) == ("1.00", "500.00", "500.00", "500.00")
    assert item_code(conn, lines[1]["item_id"]) == "EDU-FEE-%s" % setup["lab_id"]

    legs = read_gl(conn, si_id)
    assert len(legs) == 2, legs
    by_account = {leg["account_id"]: leg for leg in legs}
    recv = by_account[env["receivable_id"]]
    assert (recv["debit"], recv["credit"]) == ("4500.00", "0.00"), legs
    assert (recv["party_type"], recv["party_id"]) == ("customer", student["customer_id"])
    inc = by_account[env["income_id"]]
    assert (inc["debit"], inc["credit"]) == ("0.00", "4500.00"), legs

    link = read_fee_link(conn, si_id)
    assert link is not None
    assert link["id"] == r["invoice_id"]
    assert link["invoice_kind"] == "fee"
    assert link["student_id"] == env["student_id"]
    assert link["fee_structure_id"] == setup["fs_id"]
    assert link["amount"] == "4500.00"

    notifs = _notifications_for(conn, link["id"])
    assert len(notifs) == 1
    assert notifs[0]["notification_type"] == "fee_due"
    assert notifs[0]["reference_type"] == "educlaw_fee_invoice"


def test_same_structure_refused_on_repeat(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup = setup_fee_structure(conn, env)
    award_scholarship(conn, env)
    captured = delegate_selling_in_process(conn, monkeypatch)
    first = generate_fee_invoice_ok(conn, env, db_path)

    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-generate-fee-invoice"], conn, ns(
        student_id=env["student_id"], program_id=env["program_id"],
        academic_term_id=env["term_id"], company_id=env["company_id"],
        posting_date=POSTING_DATE, due_date=DUE_DATE,
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == (
        "Fee structure %s is already billed to student %s (sales invoice %s)"
        % (setup["fs_id"], env["student_id"], first["sales_invoice_id"]))
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_category_scholarship_discounts_only_its_category(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup = setup_fee_structure(conn, env)
    award_scholarship(conn, env, discount_type="percentage",
                      discount_amount="50",
                      applies_to_category_id=setup["lab_id"])
    delegate_selling_in_process(conn, monkeypatch)
    r = generate_fee_invoice_ok(conn, env, db_path)

    assert r["final_amount"] == "5250.00"
    assert r["total_discount"] == "250.00"
    assert r["scholarships_applied"][0]["applied_discount"] == "250.00"
    assert [(i["discount"], i["billed_amount"]) for i in r["line_items"]] == [
        ("0.00", "5000.00"), ("250.00", "250.00")]
    si = _row(conn, "sales_invoice", r["sales_invoice_id"])
    assert si["grand_total"] == "5250.00"
    legs = read_gl(conn, r["sales_invoice_id"])
    assert len(legs) == 2, legs
    by_account = {leg["account_id"]: leg for leg in legs}
    assert (by_account[env["receivable_id"]]["debit"],
            by_account[env["receivable_id"]]["credit"]) == ("5250.00", "0.00")
    assert (by_account[env["income_id"]]["debit"],
            by_account[env["income_id"]]["credit"]) == ("0.00", "5250.00")


def test_category_fixed_scholarship_capped_at_its_line(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup = setup_fee_structure(conn, env)
    award_scholarship(conn, env, discount_type="fixed",
                      discount_amount="800",
                      applies_to_category_id=setup["lab_id"])
    delegate_selling_in_process(conn, monkeypatch)
    r = generate_fee_invoice_ok(conn, env, db_path)

    assert r["final_amount"] == "5000.00"
    assert r["total_discount"] == "500.00"
    assert r["scholarships_applied"][0]["applied_discount"] == "500.00"
    assert [(i["discount"], i["billed_amount"]) for i in r["line_items"]] == [
        ("0.00", "5000.00"), ("500.00", "0.00")]


def _setup_billed(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_fee_structure(conn, env)
    award_scholarship(conn, env)
    captured = delegate_selling_in_process(conn, monkeypatch)
    first = generate_fee_invoice_ok(conn, env, db_path)
    return env, first, captured


def test_late_fee_bills_once_per_overdue_invoice(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    si1 = first["sales_invoice_id"]
    late_cat = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Late Fees", description="late",
        revenue_account_id=None))
    assert is_ok(late_cat), late_cat

    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=si1, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_ok(r), r
    assert r["late_fee_amount"] == "25.50"
    assert r["overdue_sales_invoice_id"] == si1
    assert "note" not in r
    si2 = r["sales_invoice_id"]
    assert si2 != si1

    si = _row(conn, "sales_invoice", si2)
    assert si["status"] == "submitted"
    assert si["grand_total"] == "25.50"
    assert si["customer_id"] == first["customer_id"]
    lines = read_lines(conn, si2)
    assert len(lines) == 1
    assert (lines[0]["quantity"], lines[0]["rate"], lines[0]["amount"],
            lines[0]["net_amount"]) == ("1.00", "25.50", "25.50", "25.50")
    assert item_code(conn, lines[0]["item_id"]) == "EDU-FEE-%s" % late_cat["id"]
    legs = read_gl(conn, si2)
    assert len(legs) == 2, legs
    by_account = {leg["account_id"]: leg for leg in legs}
    assert (by_account[env["receivable_id"]]["debit"],
            by_account[env["receivable_id"]]["credit"]) == ("25.50", "0.00")
    assert (by_account[env["income_id"]]["debit"],
            by_account[env["income_id"]]["credit"]) == ("0.00", "25.50")

    link = read_fee_link(conn, si2)
    assert link is not None
    assert link["invoice_kind"] == "late_fee"
    assert link["late_fee_for_sales_invoice_id"] == si1
    assert link["fee_category_id"] == late_cat["id"]
    assert link["amount"] == "25.50"
    assert _notifications_for(conn, link["id"])[0]["notification_type"] == "fee_due"

    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    dup = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=si1, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_error(dup)
    assert dup["message"] == (
        "A late fee was already applied to sales invoice %s (late fee invoice %s)"
        % (si1, si2))
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_late_fee_refused_when_not_overdue(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    si1 = first["sales_invoice_id"]
    late_cat = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Late Fees", description="late",
        revenue_account_id=None))
    assert is_ok(late_cat), late_cat
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=si1, posting_date="2026-03-15",
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == "Sales invoice %s is not overdue (due 2026-04-01)" % si1
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_late_fee_refused_for_foreign_invoice(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    from erpclaw_lib import cross_skill as _cs_mod
    foreign = _cs_mod.create_invoice(
        customer_id=first["customer_id"],
        items=[{"item_id": read_lines(conn, first["sales_invoice_id"])[0]["item_id"],
                "qty": "1", "rate": "10.00"}],
        company_id=env["company_id"], posting_date=POSTING_DATE,
        db_path=db_path)
    foreign_id = foreign["sales_invoice_id"]
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"],
        fee_category_id=setup_lab_id(conn, env),
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=foreign_id, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == ("Sales invoice %s is not a fee invoice for student %s"
                            % (foreign_id, env["student_id"]))
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def setup_lab_id(conn, env):
    t = Table("educlaw_fee_category")
    row = conn.execute(
        Q.from_(t).select(t.id).where(t.company_id == P()).where(t.name == P()).get_sql(),
        (env["company_id"], "Lab Fees")).fetchone()
    return dict(row)["id"]


def test_late_fee_requires_invoice_id(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=setup_lab_id(conn, env),
        amount="25.50", company_id=env["company_id"],
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == "--sales-invoice-id is required"
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def _other_company(conn):
    other = str(uuid.uuid4())
    sql, _ = insert_row("company", {"id": P(), "name": P(), "abbr": P(),
                                    "default_currency": P(), "country": P(),
                                    "fiscal_year_start_month": P()})
    conn.execute(sql, (other, "Other School %s" % other[:6], "OS%s" % other[:4],
                       "USD", "United States", 1))
    conn.commit()
    return other


def test_late_fee_refused_for_other_company(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    si1 = first["sales_invoice_id"]
    late_cat = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Late Fees", description="late",
        revenue_account_id=None))
    assert is_ok(late_cat), late_cat
    other = _other_company(conn)
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=other,
        sales_invoice_id=si1, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == ("Sales invoice %s belongs to company %s, not %s"
                            % (si1, env["company_id"], other))
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_late_fee_refused_for_other_student_company(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    si1 = first["sales_invoice_id"]
    late_cat = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Late Fees", description="late",
        revenue_account_id=None))
    assert is_ok(late_cat), late_cat
    other = _other_company(conn)
    _st = Table("educlaw_student")
    conn.execute(
        Q.update(_st).set("company_id", P()).where(_st.id == P()).get_sql(),
        (other, env["student_id"]))
    conn.commit()
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=si1, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == ("Student %s belongs to company %s, not %s"
                            % (env["student_id"], other, env["company_id"]))
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_late_fee_refused_for_other_category_company(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    si1 = first["sales_invoice_id"]
    late_cat = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Late Fees", description="late",
        revenue_account_id=None))
    assert is_ok(late_cat), late_cat
    other = _other_company(conn)
    _fc = Table("educlaw_fee_category")
    conn.execute(
        Q.update(_fc).set("company_id", P()).where(_fc.id == P()).get_sql(),
        (other, late_cat["id"]))
    conn.commit()
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=si1, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == ("Fee category %s belongs to company %s, not %s"
                            % (late_cat["id"], other, env["company_id"]))
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_late_fee_refused_without_due_date(conn, db_path, monkeypatch):
    env, first, captured = _setup_billed(conn, db_path, monkeypatch)
    si1 = first["sales_invoice_id"]
    late_cat = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=env["company_id"], name="Late Fees", description="late",
        revenue_account_id=None))
    assert is_ok(late_cat), late_cat
    _si = Table("sales_invoice")
    conn.execute(
        Q.update(_si).set("due_date", P()).where(_si.id == P()).get_sql(),
        (None, si1))
    conn.commit()
    before = snapshot_tables(conn)
    calls_before = len(captured["calls"])
    r = call_action(FE["edu-apply-late-fee"], conn, ns(
        student_id=env["student_id"], fee_category_id=late_cat["id"],
        amount="25.50", company_id=env["company_id"],
        sales_invoice_id=si1, posting_date="2026-05-01",
        db_path=db_path, user_id=None))
    assert is_error(r)
    assert r["message"] == ("Sales invoice %s has no due date" % si1)
    assert snapshot_tables(conn) == before
    assert len(captured["calls"]) == calls_before


def test_migration_004_adds_the_table(tmp_path):
    from erpclaw_lib import seam
    sa = seam._sqlalchemy()
    path = str(tmp_path / "mig.sqlite")
    init_path = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "init_schema.py")
    spec = importlib.util.spec_from_file_location("fee_sell_mig_init_schema", init_path)
    init_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_mod)
    init_mod.init_db(path)
    edu_path = os.path.join(_SRC_DIR, "educlaw", "educlaw", "init_db.py")
    spec = importlib.util.spec_from_file_location("fee_sell_mig_educlaw_init", edu_path)
    edu_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edu_mod)
    edu_mod.ensure_educlaw_base_tables(path)
    without_fee = sa.MetaData()
    for table in edu_mod.METADATA.sorted_tables:
        if table.name == "educlaw_fee_invoice":
            continue
        table.to_metadata(without_fee)
    seam.provision(without_fee, path)
    assert not seam.table_exists("educlaw_fee_invoice", path)
    student_before = seam.column_names("educlaw_student", path)

    mig_path = os.path.join(_SRC_DIR, "educlaw", "educlaw", "migrations",
                            "004_add_fee_invoice_link.py")
    spec = importlib.util.spec_from_file_location("fee_sell_migration_004", mig_path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    result = mig.run_migration(path)
    assert seam.table_exists("educlaw_fee_invoice", path)
    assert seam.column_names("educlaw_student", path) == student_before
    again = mig.run_migration(path)
    assert again["tables"] == 0
    assert again["indexes"] == 0

    foundation_only = str(tmp_path / "foundation.sqlite")
    init_mod.init_db(foundation_only)
    skipped = mig.run_migration(foundation_only)
    assert skipped["tables"] == 0
    assert not seam.table_exists("educlaw_fee_invoice", foundation_only)


def test_fee_actions_are_confirmed_actions(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_fee_structure(conn, env)
    award_scholarship(conn, env)
    captured = delegate_selling_in_process(conn, monkeypatch)
    first = generate_fee_invoice_ok(conn, env, db_path)
    assert is_ok(first), first

    router_path = os.path.join(_SRC_DIR, "erpclaw", "scripts", "db_query.py")
    spec = importlib.util.spec_from_file_location("_fee_sell_gate_router", router_path)
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    assert "edu-generate-fee-invoice" in router.DANGEROUS_ACTIONS
    assert "edu-apply-late-fee" in router.DANGEROUS_ACTIONS

    submits = [c for c in captured["calls"] if c["action"] == "submit-sales-invoice"]
    assert submits
    recorded = submits[0]
    argv = ["db_query.py", "--action", recorded["action"]]
    for key, value in recorded["args"].items():
        argv.append(key)
        if value is not None:
            argv.append(str(value))

    with patch.object(sys, "argv", argv):
        router._gate_dangerous_action(recorded["action"])

    stripped = [a for a in argv if a != "--user-confirmed"]
    buf = io.StringIO()
    with patch.object(sys, "argv", stripped), \
            patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        router._gate_dangerous_action(recorded["action"])
    assert exc.value.code == 2
    assert json.loads(buf.getvalue())["error"] == "user_confirmation_required"
