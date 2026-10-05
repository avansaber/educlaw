"""Student receivables to the ledger v1.

Posts one assessed student charge exactly once as a balanced
receivable/revenue pair through the shared GL seam.

Money is text throughout: exact Decimal-as-string comparisons only.
All reads and writes go through PyPika via erpclaw_lib.query with bound
parameters; connections come from erpclaw_lib.db.get_connection.
"""
import argparse
import importlib.util
import io
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(os.path.dirname(_HERE), "scripts")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

_SRC = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPTS)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_EDUCLAW_DIR = os.path.join(_SRC, "educlaw")
if _EDUCLAW_DIR not in sys.path:
    sys.path.insert(0, _EDUCLAW_DIR)

_INIT_SCHEMA_PATH = os.path.join(_SRC, "erpclaw", "scripts", "erpclaw-setup", "init_schema.py")
_HIGHERED_INIT_PATH = os.path.join(os.path.dirname(_HERE), "init_db.py")

from erpclaw_lib.db import get_connection as _get_conn
from erpclaw_lib.query import Q, P, Table, Field, fn, insert_row

from receivables import post_student_charge, add_student_charge


AMOUNT = "500.03"
POSTING_DATE = "2026-09-15"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def base_db_path(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("base") / "base.sqlite")
    schema = _load(_INIT_SCHEMA_PATH, "foundation_schema_ledger")
    schema.init_db(path)
    from educlaw_base_schema import ensure_educlaw_base_tables
    ensure_educlaw_base_tables(path)
    highered = _load(_HIGHERED_INIT_PATH, "highered_init_ledger")
    highered.create_educlaw_highered_tables(path)
    yield path


@pytest.fixture
def db_path(tmp_path, monkeypatch, base_db_path):
    path = str(tmp_path / "test.sqlite")
    shutil.copy(base_db_path, path)
    monkeypatch.setenv("ERPCLAW_DB_PATH", path)
    yield path


@pytest.fixture
def env(db_path):
    conn = _get_conn(db_path)
    cid = _seed_company(conn, "Test Univ", "TU")
    recv = _seed_account(conn, cid, "Student Receivables", "asset")
    rev = _seed_account(conn, cid, "Tuition Revenue", "income")
    cc = _seed_cost_center(conn, cid, "Campus")
    _seed_fiscal_year(conn, cid)
    yield conn, cid, recv, rev, cc
    conn.close()


def call_action(fn, conn, args):
    buf = io.StringIO()

    def _fake_exit(code=0):
        raise SystemExit(code)

    try:
        with patch("sys.stdout", buf), patch("sys.exit", side_effect=_fake_exit):
            fn(conn, args)
    except SystemExit:
        pass
    output = buf.getvalue().strip()
    if not output:
        return {"status": "error", "message": "no output captured"}
    return json.loads(output)


def ns(**kwargs):
    return argparse.Namespace(**kwargs)


def _seed_company(conn, name, abbr):
    cid = str(uuid.uuid4())
    sql, _ = insert_row("company", {"id": P(), "name": P(), "abbr": P()})
    conn.execute(sql, (cid, name + " " + cid[:6], abbr + cid[:4]))
    conn.commit()
    return cid


def _seed_account(conn, company_id, name, root_type, **overrides):
    aid = str(uuid.uuid4())
    direction = "debit_normal" if root_type in ("asset", "expense") else "credit_normal"
    data = {
        "id": P(), "name": P(), "account_number": P(), "root_type": P(),
        "balance_direction": P(), "company_id": P(), "is_group": P(),
        "disabled": P(), "depth": P(),
    }
    sql, _ = insert_row("account", data)
    conn.execute(sql, (
        aid, name + " " + aid[:4], "ACC-" + aid[:6], root_type,
        direction, company_id, int(overrides.get("is_group", 0)),
        int(overrides.get("disabled", 0)), 0,
    ))
    conn.commit()
    return aid


def _seed_cost_center(conn, company_id, name="Campus", is_group=0):
    ccid = str(uuid.uuid4())
    sql, _ = insert_row("cost_center", {
        "id": P(), "name": P(), "company_id": P(), "is_group": P(),
    })
    conn.execute(sql, (ccid, name + " " + ccid[:4], company_id, int(is_group)))
    conn.commit()
    return ccid


def _seed_fiscal_year(conn, company_id, start="2026-01-01", end="2026-12-31"):
    fid = str(uuid.uuid4())
    sql, _ = insert_row("fiscal_year", {
        "id": P(), "name": P(), "start_date": P(), "end_date": P(), "company_id": P(),
    })
    conn.execute(sql, (fid, "FY-" + fid[:6], start, end, company_id))
    conn.commit()
    return fid


def _seed_charge(conn, company_id, amount=AMOUNT, status="assessed", student_id=None):
    chid = str(uuid.uuid4())
    now = _now()
    sql, _ = insert_row("highered_student_charge", {
        "id": P(), "naming_series": P(), "student_id": P(), "description": P(),
        "amount": P(), "charge_date": P(), "charge_status": P(),
        "company_id": P(), "receivable_account_id": P(), "revenue_account_id": P(),
        "cost_center_id": P(), "gl_entry_ids": P(), "posting_date": P(),
        "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql, (
        chid, "HCHG-" + chid[:8], student_id or ("STU-" + chid[:8]),
        "Tuition Fall 2026", amount, "2026-08-20", status, company_id,
        "", "", "", "", "", now, now,
    ))
    conn.commit()
    return chid


def _charge_row(conn, charge_id):
    t = Table("highered_student_charge")
    sql = Q.from_(t).select(t.star).where(Field("id") == P()).get_sql()
    row = conn.execute(sql, (charge_id,)).fetchone()
    return dict(row) if row else None


def _gl_rows(conn, charge_id):
    t = Table("gl_entry")
    sql = Q.from_(t).select(t.star).where(Field("voucher_id") == P()).get_sql()
    return [dict(r) for r in conn.execute(sql, (charge_id,)).fetchall()]


def _gl_count(conn):
    t = Table("gl_entry")
    sql = Q.from_(t).select(fn.Count(t.star).as_("cnt")).get_sql()
    return conn.execute(sql, ()).fetchone()["cnt"]


def _audit_count(conn, charge_id):
    t = Table("audit_log")
    sql = Q.from_(t).select(fn.Count(t.star).as_("cnt")).where(Field("entity_id") == P()).get_sql()
    return conn.execute(sql, (charge_id,)).fetchone()["cnt"]


def _post(conn, cid, charge_id, amount, recv, rev, cc=None, posting_date=POSTING_DATE):
    return call_action(post_student_charge, conn, ns(
        company_id=cid, charge_id=charge_id, id=charge_id, amount=amount,
        posting_date=posting_date, receivable_account_id=recv,
        revenue_account_id=rev, cost_center_id=cc,
    ))


class TestExactPosting:
    def test_balanced_500_03_posting(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        result = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert result["status"] == "ok", result
        assert result["charge_id"] == chid
        assert result["amount"] == "500.03"
        assert Decimal(result["amount"]) == Decimal("500.03")
        assert result["posting_date"] == POSTING_DATE
        assert len(result["gl_entry_ids"]) == 2
        legs = _gl_rows(conn, chid)
        assert len(legs) == 2
        by_account = {r["account_id"]: r for r in legs}
        assert set(by_account) == {recv, rev}
        assert by_account[recv]["debit"] == "500.03"
        assert Decimal(by_account[recv]["debit"]) == Decimal("500.03")
        assert by_account[recv]["credit"] == "0.00"
        assert by_account[rev]["debit"] == "0.00"
        assert by_account[rev]["credit"] == "500.03"
        assert Decimal(by_account[rev]["credit"]) == Decimal("500.03")
        total_debit = sum(Decimal(r["debit"]) for r in legs)
        total_credit = sum(Decimal(r["credit"]) for r in legs)
        assert total_debit == Decimal("500.03")
        assert total_credit == Decimal("500.03")
        assert total_debit == total_credit
        assert {r["voucher_type"] for r in legs} == {"journal_entry"}
        assert {r["posting_date"] for r in legs} == {POSTING_DATE}
        # Legs carry no company_id by foundation design; company scope is
        # enforced by the posting validation (accounts, cost center and
        # fiscal year must all belong to the charge company) and proven by
        # the company-isolation tests below.
        assert {r["is_cancelled"] for r in legs} == {0}
        assert by_account[rev]["cost_center_id"] == cc
        stored = _charge_row(conn, chid)
        assert stored["charge_status"] == "posted"
        assert stored["posting_date"] == POSTING_DATE
        assert stored["receivable_account_id"] == recv
        assert stored["revenue_account_id"] == rev
        assert stored["cost_center_id"] == cc
        assert set(stored["gl_entry_ids"].split(",")) == set(result["gl_entry_ids"])
        assert _audit_count(conn, chid) >= 1

    def test_add_action_creates_assessed_charge(self, env):
        conn, cid, recv, rev, cc = env
        result = call_action(add_student_charge, conn, ns(
            company_id=cid, student_id="STU-001", amount=AMOUNT,
            charge_date="2026-08-20", charge_status="assessed",
            description="Tuition",
        ))
        assert result["status"] == "ok", result
        assert result["amount"] == "500.03"
        assert result["charge_status"] == "assessed"
        stored = _charge_row(conn, result["id"])
        assert stored is not None
        assert stored["amount"] == "500.03"
        assert Decimal(stored["amount"]) == Decimal("500.03")


class TestIdempotency:
    def test_identical_retry_returns_same_ids(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        first = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert first["status"] == "ok", first
        count_before = _gl_count(conn)
        second = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert second["status"] == "ok", second
        assert set(second["gl_entry_ids"]) == set(first["gl_entry_ids"])
        assert second["amount"] == "500.03"
        assert _gl_count(conn) == count_before
        assert len(_gl_rows(conn, chid)) == 2

    def test_changed_account_retry_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        first = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert first["status"] == "ok", first
        other_rev = _seed_account(conn, cid, "Other Revenue", "income")
        count_before = _gl_count(conn)
        refused = _post(conn, cid, chid, AMOUNT, recv, other_rev, cc)
        assert refused["status"] == "error", refused
        assert "already posted" in refused["message"]
        assert _gl_count(conn) == count_before
        assert len(_gl_rows(conn, chid)) == 2
        stored = _charge_row(conn, chid)
        assert stored["revenue_account_id"] == rev
        assert set(stored["gl_entry_ids"].split(",")) == set(first["gl_entry_ids"])

    def test_changed_amount_retry_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        first = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert first["status"] == "ok", first
        count_before = _gl_count(conn)
        refused = _post(conn, cid, chid, "600.00", recv, rev, cc)
        assert refused["status"] == "error", refused
        assert _gl_count(conn) == count_before


class TestSourceValidation:
    def test_draft_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid, status="draft")
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert result["status"] == "error", result
        assert "draft" in result["message"]
        assert _gl_count(conn) == before
        assert _charge_row(conn, chid)["charge_status"] == "draft"
        assert _gl_rows(conn, chid) == []

    def test_cancelled_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid, status="cancelled")
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert result["status"] == "error", result
        assert "cancelled" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []

    def test_missing_refused(self, env):
        conn, cid, recv, rev, cc = env
        before = _gl_count(conn)
        result = _post(conn, cid, "no-such-charge", AMOUNT, recv, rev, cc)
        assert result["status"] == "error", result
        assert "not found" in result["message"]
        assert _gl_count(conn) == before

    def test_zero_amount_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid, amount="0.00")
        before = _gl_count(conn)
        result = call_action(post_student_charge, conn, ns(
            company_id=cid, charge_id=chid, id=chid, amount="0.00",
            posting_date=POSTING_DATE, receivable_account_id=recv,
            revenue_account_id=rev, cost_center_id=cc,
        ))
        assert result["status"] == "error", result
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []
        assert _charge_row(conn, chid)["charge_status"] == "assessed"

    def test_amount_mismatch_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        before = _gl_count(conn)
        result = _post(conn, cid, chid, "500.04", recv, rev, cc)
        assert result["status"] == "error", result
        assert "does not match" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []
        assert _charge_row(conn, chid)["charge_status"] == "assessed"


class TestAccountValidation:
    def test_group_receivable_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        group = _seed_account(conn, cid, "Group AR", "asset", is_group=1)
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, group, rev, cc)
        assert result["status"] == "error", result
        assert "group" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []

    def test_disabled_revenue_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        bad = _seed_account(conn, cid, "Old Revenue", "income", disabled=1)
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, bad, cc)
        assert result["status"] == "error", result
        assert "disabled" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []

    def test_wrong_root_types_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        liability = _seed_account(conn, cid, "Payables", "liability")
        expense = _seed_account(conn, cid, "Supplies", "expense")
        before = _gl_count(conn)
        r1 = _post(conn, cid, chid, AMOUNT, liability, rev, cc)
        assert r1["status"] == "error", r1
        assert "root type" in r1["message"]
        r2 = _post(conn, cid, chid, AMOUNT, recv, expense, cc)
        assert r2["status"] == "error", r2
        assert "root type" in r2["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []

    def test_missing_account_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, "no-such-account", rev, cc)
        assert result["status"] == "error", result
        assert "not found" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []


class TestCostCenter:
    def test_missing_cost_center_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, rev)
        assert result["status"] == "error", result
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []
        assert _charge_row(conn, chid)["charge_status"] == "assessed"

    def test_foreign_cost_center_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        other_cid = _seed_company(conn, "Other Univ", "OU")
        foreign_cc = _seed_cost_center(conn, other_cid, "Remote")
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, rev, foreign_cc)
        assert result["status"] == "error", result
        assert "different company" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []

    def test_group_cost_center_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        group_cc = _seed_cost_center(conn, cid, "Group", is_group=1)
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, rev, group_cc)
        assert result["status"] == "error", result
        assert "group" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []

    def test_changed_cost_center_retry_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        first = _post(conn, cid, chid, AMOUNT, recv, rev, cc)
        assert first["status"] == "ok", first
        other_cc = _seed_cost_center(conn, cid, "Annex")
        before = _gl_count(conn)
        refused = _post(conn, cid, chid, AMOUNT, recv, rev, other_cc)
        assert refused["status"] == "error", refused
        assert "already posted" in refused["message"]
        assert _gl_count(conn) == before
        assert len(_gl_rows(conn, chid)) == 2


class TestCompanyIsolation:
    def test_foreign_charge_refused(self, env):
        conn, cid, recv, rev, cc = env
        other_cid = _seed_company(conn, "Other Univ", "OU")
        _seed_fiscal_year(conn, other_cid)
        foreign_charge = _seed_charge(conn, other_cid)
        before = _gl_count(conn)
        result = _post(conn, cid, foreign_charge, AMOUNT, recv, rev, cc)
        assert result["status"] == "error", result
        assert "different company" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, foreign_charge) == []
        assert _charge_row(conn, foreign_charge)["charge_status"] == "assessed"

    def test_foreign_account_refused(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        other_cid = _seed_company(conn, "Other Univ", "OU")
        foreign_rev = _seed_account(conn, other_cid, "Foreign Revenue", "income")
        before = _gl_count(conn)
        result = _post(conn, cid, chid, AMOUNT, recv, foreign_rev, cc)
        assert result["status"] == "error", result
        assert "different company" in result["message"]
        assert _gl_count(conn) == before
        assert _gl_rows(conn, chid) == []


class TestNoPartialWrites:
    def test_failed_post_writes_nothing(self, env):
        conn, cid, recv, rev, cc = env
        chid = _seed_charge(conn, cid)
        stored_before = _charge_row(conn, chid)
        gl_before = _gl_count(conn)
        audit_before = _audit_count(conn, chid)
        bad_rev = _seed_account(conn, cid, "Bad Revenue", "income", disabled=1)
        result = _post(conn, cid, chid, AMOUNT, recv, bad_rev, cc)
        assert result["status"] == "error", result
        assert _gl_count(conn) == gl_before
        assert _gl_rows(conn, chid) == []
        stored_after = _charge_row(conn, chid)
        assert stored_after == stored_before
        assert _audit_count(conn, chid) == audit_before
