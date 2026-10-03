"""edu-get-outstanding-fees lists an invoice only when its outstanding amount is
numerically greater than zero.

outstanding_amount is TEXT. The foundation stores a fully discounted invoice's
outstanding as "0.00", and compared as text "0.00" > "0" is true, so a
past-due invoice that owes nothing would be listed and a student who owes
nothing would appear as outstanding. The comparison must be numeric.

The module's shared `db_path` fixture builds a stand-in sales_invoice table
without due_date or outstanding_amount, so this file builds its database from
the foundation schema plus the educlaw tables, and seeds sales_invoice rows
directly. All due dates are fixed in 2026 and are in the past for any run of
this suite, so the handler's use of today's date does not change the outcome.
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


def _invoice(conn, company_id, customer_id, naming_series, status, due_date,
             grand_total, outstanding_amount):
    invoice_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sales_invoice (id, naming_series, customer_id, posting_date, "
        "due_date, grand_total, outstanding_amount, status, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (invoice_id, naming_series, customer_id, "2026-01-02", due_date,
         grand_total, outstanding_amount, status, company_id),
    )
    conn.commit()
    return invoice_id


def _outstanding(conn, company_id):
    return call_action(FEES_ACTIONS["edu-get-outstanding-fees"], conn,
                       ns(company_id=company_id))


def test_zero_outstanding_in_two_decimal_form_is_not_listed(real_conn):
    conn = real_conn
    cid = seed_company(conn)
    stu_a, cust_a = _student_with_customer(conn, cid, "Parent A")
    _stu_b, cust_b = _student_with_customer(conn, cid, "Parent B")

    tuition = _invoice(conn, cid, cust_a, "SINV-A-TUI", "submitted", "2026-01-31",
                       "1250.00", "1250.00")
    lab = _invoice(conn, cid, cust_a, "SINV-A-LAB", "partially_paid", "2026-02-15",
                   "40.00", "9.50")
    _invoice(conn, cid, cust_a, "SINV-A-WAIVED", "submitted", "2026-01-31",
             "0.00", "0.00")
    _invoice(conn, cid, cust_a, "SINV-A-OVD-ZERO", "overdue", "2026-01-31",
             "600.00", "0.00")
    _invoice(conn, cid, cust_b, "SINV-B-WAIVED", "submitted", "2026-01-31",
             "0.00", "0.00")
    _invoice(conn, cid, cust_b, "SINV-B-PART-ZERO", "partially_paid", "2026-02-15",
             "80.00", "0.00")

    r = _outstanding(conn, cid)
    assert is_ok(r), r
    assert r["company_id"] == cid
    assert r["outstanding_count"] == 1
    (entry,) = r["outstanding_students"]
    assert entry["student_id"] == stu_a
    assert entry["total_outstanding"] == "1259.50"
    listed = {
        (o["id"], o["status"], o["due_date"], o["grand_total"], o["outstanding_amount"])
        for o in entry["overdue_invoices"]
    }
    assert listed == {
        (tuition, "submitted", "2026-01-31", "1250.00", "1250.00"),
        (lab, "partially_paid", "2026-02-15", "40.00", "9.50"),
    }


def test_student_owing_nothing_on_past_due_invoices_is_not_listed(real_conn):
    conn = real_conn
    cid = seed_company(conn)
    _stu, cust = _student_with_customer(conn, cid, "Parent C")
    _invoice(conn, cid, cust, "SINV-C-WAIVED", "submitted", "2026-01-31", "0.00", "0.00")
    _invoice(conn, cid, cust, "SINV-C-OVD-ZERO", "overdue", "2026-02-15", "300.00", "0.00")

    r = _outstanding(conn, cid)
    assert is_ok(r), r
    assert r["outstanding_count"] == 0
    assert r["outstanding_students"] == []
