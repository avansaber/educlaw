"""Student account lists submitted payments with allocations, exact invoice keys.

``edu-get-student-account`` is a pure read: it reports the student's fee
invoices (keyed by ``naming_series``, never a stray ``name``) and the
customer's submitted ``payment_entry`` rows with their live
``payment_allocation`` children. Delinked allocations and draft entries
stay out. Money is TEXT in storage and compared as exact strings, never
float. Every database access below goes through PyPika
(``erpclaw_lib.query``) over a connection from ``erpclaw_lib.db``; the
fee billing itself runs through the real selling delegate from
``test_fee_invoice_bills_through_selling``.
"""
import os
import sys
import uuid

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
from erpclaw_lib.query import Q, P, Table, insert_row

from helpers import call_action, ns, is_ok

from test_fee_invoice_bills_through_selling import (
    make_full_db,
    seed_fee_env,
    setup_fee_structure,
    delegate_selling_in_process,
    generate_fee_invoice_ok,
)


def _load_fees():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fees_student_account", os.path.join(_SCRIPTS_DIR, "fees.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ACTIONS


FE = _load_fees()

INVOICE_KEYS = {"id", "naming_series", "posting_date", "grand_total",
                "status", "outstanding_amount"}
PAYMENT_KEYS = {"id", "naming_series", "posting_date", "paid_amount",
                "unallocated_amount", "allocations"}

SNAPSHOT_TABLES = ("sales_invoice", "payment_entry", "payment_allocation",
                   "gl_entry", "audit_log")


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "student_account.sqlite")
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


def _insert_payment_entry(conn, env, customer_id, naming_series, posting_date,
                          paid_amount, unallocated_amount, status):
    pe_id = str(uuid.uuid4())
    sql, _ = insert_row("payment_entry", {
        "id": P(), "naming_series": P(), "payment_type": P(),
        "posting_date": P(), "party_type": P(), "party_id": P(),
        "paid_from_account": P(), "paid_to_account": P(),
        "paid_amount": P(), "received_amount": P(),
        "unallocated_amount": P(), "status": P(), "company_id": P(),
    })
    conn.execute(sql, (pe_id, naming_series, "receive", posting_date,
                       "customer", customer_id, env["receivable_id"],
                       env["income_id"], paid_amount, paid_amount,
                       unallocated_amount, status, env["company_id"]))
    conn.commit()
    return pe_id


def _insert_allocation(conn, payment_entry_id, voucher_id, allocated_amount,
                       delinked=0):
    alloc_id = str(uuid.uuid4())
    sql, _ = insert_row("payment_allocation", {
        "id": P(), "payment_entry_id": P(), "voucher_type": P(),
        "voucher_id": P(), "allocated_amount": P(), "delinked": P(),
    })
    conn.execute(sql, (alloc_id, payment_entry_id, "sales_invoice",
                       voucher_id, allocated_amount, delinked))
    conn.commit()
    return alloc_id


def _setup_paid(conn, db_path, monkeypatch):
    env = seed_fee_env(conn)
    setup_fee_structure(conn, env)
    delegate_selling_in_process(conn, monkeypatch)
    billed = generate_fee_invoice_ok(conn, env, db_path)
    invoice_id = billed["sales_invoice_id"]
    student = dict(conn.execute(
        Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star)
        .where(Table("educlaw_student").id == P()).get_sql(),
        (env["student_id"],)).fetchone())
    customer_id = student["customer_id"]
    assert customer_id
    full_id = _insert_payment_entry(
        conn, env, customer_id, "PE-FULL-001", "2026-03-10",
        "1000.00", "0.00", "submitted")
    _insert_allocation(conn, full_id, invoice_id, "1000.00", delinked=0)
    _insert_payment_entry(
        conn, env, customer_id, "PE-DRAFT-001", "2026-03-15",
        "50.00", "50.00", "draft")
    delinked_id = _insert_payment_entry(
        conn, env, customer_id, "PE-DELINK-001", "2026-03-20",
        "200.00", "200.00", "submitted")
    _insert_allocation(conn, delinked_id, invoice_id, "200.00", delinked=1)
    return env, invoice_id, customer_id, full_id, delinked_id


def _get_account(conn, env):
    result = call_action(FE["edu-get-student-account"], conn, ns(
        student_id=env["student_id"], company_id=env["company_id"]))
    assert is_ok(result), result
    return result


def test_submitted_payment_listed_with_allocation(conn, db_path, monkeypatch):
    env, invoice_id, customer_id, full_id, delinked_id = _setup_paid(
        conn, db_path, monkeypatch)
    result = _get_account(conn, env)
    assert result["customer_id"] == customer_id
    payments = result["payments"]
    assert len(payments) == 2
    assert [entry["id"] for entry in payments] == [delinked_id, full_id]
    for entry in payments:
        assert set(entry.keys()) == PAYMENT_KEYS
    newest, oldest = payments
    assert newest["naming_series"] == "PE-DELINK-001"
    assert newest["paid_amount"] == "200.00"
    assert newest["allocations"] == []
    assert oldest["naming_series"] == "PE-FULL-001"
    assert oldest["paid_amount"] == "1000.00"
    assert oldest["unallocated_amount"] == "0.00"
    assert oldest["allocations"] == [{"voucher_type": "sales_invoice",
                                      "voucher_id": invoice_id,
                                      "allocated_amount": "1000.00"}]
    assert all(entry["naming_series"] != "PE-DRAFT-001" for entry in payments)


def test_invoice_keys_are_exact(conn, db_path, monkeypatch):
    env, invoice_id, _customer_id, _full_id, _delinked_id = _setup_paid(
        conn, db_path, monkeypatch)
    result = _get_account(conn, env)
    assert result["invoices"]
    stored = dict(conn.execute(
        Q.from_(Table("sales_invoice")).select(Table("sales_invoice").star)
        .where(Table("sales_invoice").id == P()).get_sql(),
        (invoice_id,)).fetchone())
    by_id = {inv["id"]: inv for inv in result["invoices"]}
    assert invoice_id in by_id
    for inv in result["invoices"]:
        assert set(inv.keys()) == INVOICE_KEYS
        assert "name" not in inv
        assert '"name"' not in inv
    assert by_id[invoice_id]["naming_series"] == stored["naming_series"]
    assert by_id[invoice_id]["grand_total"] == stored["grand_total"]
    assert by_id[invoice_id]["outstanding_amount"] == stored["outstanding_amount"]


def _snapshot(conn):
    snap = {}
    for name in SNAPSHOT_TABLES:
        table = Table(name)
        rows = conn.execute(
            Q.from_(table).select(table.star).get_sql()).fetchall()
        snap[name] = sorted(repr(dict(row)) for row in rows)
    return snap


def test_account_writes_nothing(conn, db_path, monkeypatch):
    env, _invoice_id, _customer_id, _full_id, _delinked_id = _setup_paid(
        conn, db_path, monkeypatch)
    before = _snapshot(conn)
    _get_account(conn, env)
    assert _snapshot(conn) == before


def test_skill_rows_name_the_router():
    path = os.path.join(_SRC_DIR, "educlaw", "educlaw", "SKILL.md")
    with open(path) as handle:
        lines = handle.read().splitlines()
    assert len(lines) <= 300
    rows = [line for line in lines
            if "edu-generate-fee-invoice" in line or "edu-apply-late-fee" in line]
    assert len(rows) == 2
    for row in rows:
        assert "through the erpclaw router" in row
        assert "; needs --user-confirmed" not in row
