"""M504 depth: behavioural tests for two special_education actions.

Each action below already had a test proving the wrong thing. In
``test_k12.py``, ``TestSpedReferral::test_list`` calls
``k12-list-sped-referrals`` on an empty database and asserts only ``is_ok`` --
it would pass if the action returned an empty list forever, filtered nothing,
or mirrored no stored row. ``k12-update-iep`` has no test at all there; its
nearest neighbours (``TestIEP::test_list_*``) likewise assert only ``is_ok``.
The tests here assert what each action does to the database instead of what
its response envelope looks like.

Ledger scope, stated once so no later reader adds a balance assertion that
cannot hold: neither handler reaches the general ledger.
``k12-list-sped-referrals`` is a pure SELECT (it writes no audit row either);
``k12-update-iep`` writes the ``educlaw_k12_iep`` row plus one ``audit_log``
line. There are no monetary columns on any table touched here, so there is no
Decimal comparison to make; money-is-text holds vacuously for this file.

Signal depth per action (stored row unless noted):
- k12-list-sped-referrals: stored rows (read-only; payload mirrors the rows,
  filters pinned, the read changes nothing).
- k12-update-iep: stored row (draft fields move from exact before-values to
  exact after-values; sibling rows byte-identical).

Read-backs use ``erpclaw_lib.db.get_connection`` with PyPika
(``erpclaw_lib.query``); catalog questions use ``erpclaw_lib.seam``. No
``sqlite_master``, no ``PRAGMA``, no ``information_schema`` below.
"""
import importlib.util
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_LIB_DIR = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if os.path.isdir(os.path.join(_LIB_DIR, "erpclaw_lib")) and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, fn
from erpclaw_lib import seam as _seam


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student

SPED = _load("special_education", _SCRIPTS_DIR).ACTIONS

SNAPSHOT_TABLES = (
    "educlaw_k12_sped_referral",
    "educlaw_k12_sped_eligibility",
    "educlaw_k12_iep",
    "audit_log",
)


@pytest.fixture
def tconn(db_path):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _snapshot(conn):
    snap = {}
    for name in SNAPSHOT_TABLES:
        t = Table(name)
        rows = conn.execute(Q.from_(t).select("*").get_sql()).fetchall()
        snap[name] = sorted(repr(dict(r)) for r in rows)
    return snap


def _row(conn, table, row_id):
    t = Table(table)
    row = conn.execute(
        Q.from_(t).select("*").where(t.id == P()).get_sql(), (row_id,)).fetchone()
    return dict(row) if row is not None else None


def _audit_count(conn, action, entity_id):
    t = Table("audit_log")
    return conn.execute(
        Q.from_(t).select(fn.Count("*")).where(
            (t.action == P()) & (t.entity_id == P())).get_sql(),
        (action, entity_id)).fetchone()[0]


def _create_referral(conn, cid, sid, when, source, reason):
    r = call_action(SPED["k12-create-sped-referral"], conn, ns(
        student_id=sid, company_id=cid,
        referral_date=when, referral_source=source,
        referral_reason=reason,
        areas_of_concern='["reading"]',
        prior_interventions='["tutoring"]',
        user_id="teacher1",
    ))
    assert is_ok(r), r
    return r["id"]


def _make_draft_iep(conn, cid, sid, start="2025-11-01", end="2026-10-31"):
    ref = _create_referral(conn, cid, sid, "2025-09-15", "teacher", "Reading delays")
    elig = call_action(SPED["k12-record-sped-eligibility"], conn, ns(
        referral_id=ref, student_id=sid, company_id=cid,
        eligibility_meeting_date="2025-10-15", is_eligible=1,
        primary_disability="specific_learning_disability",
        disability_categories='["specific_learning_disability"]',
        user_id="sped-coord",
    ))
    assert is_ok(elig), elig
    iep = call_action(SPED["k12-add-iep"], conn, ns(
        student_id=sid, eligibility_id=elig["id"], company_id=cid,
        iep_start_date=start, iep_end_date=end,
        plaafp_academic="Reads below grade level",
        lre_percentage_general_ed="80",
        user_id="sped-coord",
    ))
    assert is_ok(iep), iep
    assert iep["iep_status"] == "draft"
    return iep["id"]


# ---------------------------------------------------------------------------
# k12-list-sped-referrals -- stored rows (read-only).
# No ledger effect: a pure SELECT that never touches journal/gl tables and
# writes no audit_log row either (asserted below via snapshot equality).
# ---------------------------------------------------------------------------
class TestListSpedReferrals:
    def test_returns_exact_stored_rows_in_date_order_and_reads_change_nothing(
            self, tconn, db_path):
        assert _seam.table_exists("educlaw_k12_sped_referral", db_path)
        cid = seed_company(tconn)
        stu_a = seed_student(tconn, cid)
        stu_b = seed_student(tconn, cid)
        a1 = _create_referral(tconn, cid, stu_a, "2025-09-15", "teacher", "Reading delays")
        b1 = _create_referral(tconn, cid, stu_b, "2025-09-12", "counselor", "Speech concerns")
        a2 = _create_referral(tconn, cid, stu_a, "2025-09-10", "parent", "Math delays")
        mv = call_action(SPED["k12-update-sped-referral"], tconn, ns(
            referral_id=a2, referral_status="consent_pending",
        ))
        assert is_ok(mv), mv

        before = _snapshot(tconn)
        r = call_action(SPED["k12-list-sped-referrals"], tconn, ns(
            company_id=cid, student_id=None,
            referral_status=None, limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert r["count"] == 3
        assert [row["id"] for row in r["referrals"]] == [a1, b1, a2]
        for payload in r["referrals"]:
            stored = _row(tconn, "educlaw_k12_sped_referral", payload["id"])
            assert stored is not None
            for key in ("naming_series", "student_id", "referral_date",
                        "referral_source", "referral_reason", "referral_status",
                        "company_id"):
                assert payload[key] == stored[key], key
        assert [row["referral_date"] for row in r["referrals"]] == [
            "2025-09-15", "2025-09-12", "2025-09-10"]
        assert _snapshot(tconn) == before

        f = call_action(SPED["k12-list-sped-referrals"], tconn, ns(
            company_id=cid, student_id=stu_a,
            referral_status=None, limit=50, offset=0,
        ))
        assert is_ok(f), f
        assert f["count"] == 2
        assert {row["id"] for row in f["referrals"]} == {a1, a2}
        other = _row(tconn, "educlaw_k12_sped_referral", b1)
        assert other["student_id"] == stu_b
        assert other["referral_reason"] == "Speech concerns"
        assert other["referral_status"] == "received"

        g = call_action(SPED["k12-list-sped-referrals"], tconn, ns(
            company_id=cid, student_id=None,
            referral_status="consent_pending", limit=50, offset=0,
        ))
        assert is_ok(g), g
        assert g["count"] == 1
        assert g["referrals"][0]["id"] == a2
        assert _snapshot(tconn) == before

    def test_refuses_unknown_company_and_writes_nothing(self, tconn):
        cid = seed_company(tconn)
        sid = seed_student(tconn, cid)
        _create_referral(tconn, cid, sid, "2025-09-15", "teacher", "Reading delays")
        before = _snapshot(tconn)
        r = call_action(SPED["k12-list-sped-referrals"], tconn, ns(
            company_id=None, company_name="No Such School", student_id=None,
            referral_status=None, limit=50, offset=0,
        ))
        assert "error" in r
        assert "No Such School" in r["error"]
        assert "not found" in r["error"]
        assert _snapshot(tconn) == before


# ---------------------------------------------------------------------------
# k12-update-iep -- stored row (writes the IEP row plus one audit_log line).
# No ledger effect: the handler never touches journal/gl tables (asserted via
# the audit-only side effect and snapshot-scoped comparisons below).
# ---------------------------------------------------------------------------
class TestUpdateIep:
    def test_updates_draft_fields_and_leaves_everything_else_byte_identical(
            self, tconn, db_path):
        assert _seam.table_exists("educlaw_k12_iep", db_path)
        cid = seed_company(tconn)
        stu_a = seed_student(tconn, cid)
        stu_b = seed_student(tconn, cid)
        iep_a = _make_draft_iep(tconn, cid, stu_a)
        iep_b = _make_draft_iep(tconn, cid, stu_b)
        before_a = _row(tconn, "educlaw_k12_iep", iep_a)
        before_b = _row(tconn, "educlaw_k12_iep", iep_b)
        assert before_a["iep_status"] == "draft"
        assert before_a["plaafp_academic"] == "Reads below grade level"
        assert _audit_count(tconn, "k12-update-iep", iep_a) == 0

        r = call_action(SPED["k12-update-iep"], tconn, ns(
            iep_id=iep_a,
            iep_meeting_date="2025-10-20",
            plaafp_academic="Reads at grade level with support",
            plaafp_functional="Improved attention span",
            lre_percentage_general_ed="85",
            progress_report_frequency="monthly",
        ))
        assert is_ok(r), r
        assert r["id"] == iep_a

        after_a = _row(tconn, "educlaw_k12_iep", iep_a)
        assert after_a["plaafp_academic"] == "Reads at grade level with support"
        assert after_a["plaafp_functional"] == "Improved attention span"
        assert after_a["lre_percentage_general_ed"] == "85"
        assert after_a["progress_report_frequency"] == "monthly"
        assert after_a["iep_meeting_date"] == "2025-10-20"
        for key in ("student_id", "eligibility_id", "naming_series",
                    "iep_version", "iep_status", "company_id", "iep_end_date",
                    "iep_start_date", "state_assessment_participation",
                    "transition_plan_required"):
            assert after_a[key] == before_a[key], key
        assert after_a["updated_at"] != ""
        assert _row(tconn, "educlaw_k12_iep", iep_b) == before_b
        assert _audit_count(tconn, "k12-update-iep", iep_a) == 1
        assert _audit_count(tconn, "k12-update-iep", iep_b) == 0

    def test_refusals_write_nothing(self, tconn):
        cid = seed_company(tconn)
        sid = seed_student(tconn, cid)
        iep = _make_draft_iep(tconn, cid, sid)

        before = _snapshot(tconn)
        r = call_action(SPED["k12-update-iep"], tconn, ns(
            plaafp_academic="Should not land anywhere",
        ))
        assert is_error(r)
        assert r["message"] == "--iep-id is required"
        assert _snapshot(tconn) == before

        r = call_action(SPED["k12-update-iep"], tconn, ns(
            iep_id="no-such-iep", plaafp_academic="Should not land anywhere",
        ))
        assert is_error(r)
        assert "no-such-iep" in r["message"]
        assert "not found" in r["message"]
        assert _snapshot(tconn) == before

        r = call_action(SPED["k12-update-iep"], tconn, ns(iep_id=iep))
        assert is_error(r)
        assert r["message"] == "No fields provided to update"
        assert _snapshot(tconn) == before

        act = call_action(SPED["k12-activate-iep"], tconn, ns(
            iep_id=iep, parent_consent_date="2025-11-01",
        ))
        assert is_ok(act), act
        locked = _snapshot(tconn)
        r = call_action(SPED["k12-update-iep"], tconn, ns(
            iep_id=iep, plaafp_academic="Should not land anywhere",
        ))
        assert is_error(r)
        assert "Only draft IEPs" in r["message"]
        assert "active" in r["message"]
        assert _snapshot(tconn) == locked
        assert _row(tconn, "educlaw_k12_iep", iep)["iep_status"] == "active"
