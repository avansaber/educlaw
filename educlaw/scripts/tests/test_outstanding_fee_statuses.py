"""Behaviour tests for edu-get-outstanding-fees over the real foundation schema.

The module's shared `db_path` fixture builds a stand-in sales_invoice table with
no due_date and no outstanding_amount, so this file builds its own database from
the foundation schema (erpclaw-setup init_schema) plus the educlaw tables, and
seeds sales_invoice rows directly with the statuses the foundation allows.

Pins:
  - past-due invoices in every open status (submitted, partially_paid, overdue)
    are listed, with the exact outstanding amounts and their exact sum;
  - paid, draft and cancelled invoices, and open invoices not yet due, are not;
  - a student whose only invoices are paid or not yet due is not listed, and a
    student with no customer is skipped;
  - a missing --company-id is refused with its reason.

All due dates are fixed: 2026-01-31 and 2026-02-15 are in the past and 2999-12-31
is in the future for any run of this suite, so the handler's use of today's date
does not change the outcome.
"""
import importlib.util
import os
import uuid

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", os.path.join(_HERE, "helpers.py"))
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error
get_conn = _helpers.get_conn
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student

FEES_ACTIONS = _load("fees", os.path.join(_SCRIPTS_DIR, "fees.py")).ACTIONS


@pytest.fixture
def real_conn(tmp_path):
    """Foundation schema + educlaw tables, so sales_invoice is the real table."""
    path = str(tmp_path / "real.sqlite")
    _load("init_schema_real", _helpers.INIT_SCHEMA_PATH).init_db(path)
    _helpers.run_init_db(path)
    os.environ["ERPCLAW_DB_PATH"] = path
    conn = get_conn(path)
    yield conn
    conn.close()
    os.environ.pop("ERPCLAW_DB_PATH", None)


def _student_with_customer(conn, company_id, customer_name):
    customer_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO customer (id, name, company_id) VALUES (?, ?, ?)",
        (customer_id, customer_name, company_id),
    )
    student_id = seed_student(conn, company_id)
    conn.execute(
        "UPDATE educlaw_student SET customer_id = ? WHERE id = ?",
        (customer_id, student_id),
    )
    conn.commit()
    return student_id, customer_id


def _outstanding(conn, company_id):
    return call_action(FEES_ACTIONS["edu-get-outstanding-fees"], conn, ns(company_id=company_id))


def _invoice(conn, company_id, customer_id, naming_series, status, due_date,
             outstanding_amount, grand_total="5000.00"):
    invoice_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sales_invoice (id, naming_series, customer_id, posting_date, "
        "due_date, grand_total, outstanding_amount, status, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (invoice_id, naming_series, customer_id, "2026-01-01", due_date,
         grand_total, outstanding_amount, status, company_id),
    )
    conn.commit()
    return invoice_id


class TestOutstandingFeeStatuses:

    def test_lists_past_due_invoices_in_every_open_status(self, real_conn):
        conn = real_conn
        cid = seed_company(conn)
        stu_a, cust_a = _student_with_customer(conn, cid, "Parent A")
        _stu_b, cust_b = _student_with_customer(conn, cid, "Parent B")
        # A student with no customer is skipped rather than failing the query.
        seed_student(conn, cid)

        submitted = _invoice(conn, cid, cust_a, "SINV-A-SUB", "submitted", "2026-01-31", "5000.00")
        partial = _invoice(conn, cid, cust_a, "SINV-A-PART", "partially_paid", "2026-02-15", "1200.50")
        overdue = _invoice(conn, cid, cust_a, "SINV-A-OVD", "overdue", "2026-01-31", "300.00")
        _invoice(conn, cid, cust_a, "SINV-A-PAID", "paid", "2026-01-31", "0")
        _invoice(conn, cid, cust_a, "SINV-A-DRAFT", "draft", "2026-01-31", "800.00")
        _invoice(conn, cid, cust_a, "SINV-A-CANC", "cancelled", "2026-01-31", "900.00")
        _invoice(conn, cid, cust_a, "SINV-A-FUTURE", "submitted", "2999-12-31", "400.00")
        _invoice(conn, cid, cust_b, "SINV-B-PAID", "paid", "2026-01-31", "0")
        _invoice(conn, cid, cust_b, "SINV-B-FUTURE", "partially_paid", "2999-12-31", "250.00")

        r = _outstanding(conn, cid)
        assert is_ok(r), r
        assert r["company_id"] == cid
        assert r["outstanding_count"] == 1
        (entry,) = r["outstanding_students"]
        assert entry["student_id"] == stu_a
        assert entry["total_outstanding"] == "6500.50"
        listed = {
            (o["id"], o["status"], o["due_date"], o["outstanding_amount"], o["grand_total"])
            for o in entry["overdue_invoices"]
        }
        assert listed == {
            (submitted, "submitted", "2026-01-31", "5000.00", "5000.00"),
            (partial, "partially_paid", "2026-02-15", "1200.50", "5000.00"),
            (overdue, "overdue", "2026-01-31", "300.00", "5000.00"),
        }

    def test_only_paid_or_not_yet_due_lists_nobody(self, real_conn):
        conn = real_conn
        cid = seed_company(conn)
        _stu, cust = _student_with_customer(conn, cid, "Parent C")
        _invoice(conn, cid, cust, "SINV-C-PAID", "paid", "2026-01-31", "0")
        _invoice(conn, cid, cust, "SINV-C-FUTURE", "submitted", "2999-12-31", "750.00")

        r = _outstanding(conn, cid)
        assert is_ok(r), r
        assert r["outstanding_count"] == 0
        assert r["outstanding_students"] == []

    def test_refuses_missing_company(self, real_conn):
        r = _outstanding(real_conn, None)
        assert is_error(r)
        assert r["message"] == "--company-id is required"
