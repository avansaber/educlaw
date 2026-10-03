"""Behavioural depth tests for 12 educlaw-highered actions.

The pre-existing suites assert response shape (``status == ok`` and a few keys)
but never read the database back, so a routed action that wrote nothing -- or
the wrong thing -- still passed. Every test here reads rows back through
``erpclaw_lib.query`` (PyPika) over a connection from
``erpclaw_lib.db.get_connection`` and compares exact values; catalog questions
go through ``erpclaw_lib.seam``.

Ledger note (applies to all 12 actions in this file): none of these actions
reaches the ledger. They read or write highered/educlaw tables only and never
insert GL/journal legs, so there are no debit/credit legs to assert and no
balance check that could hold. Each test states this once more at the point of
use so a later reader does not add a ledger assertion that cannot hold.

Money note: every monetary assertion compares exact ``Decimal`` values held as
TEXT. No float, no approximation, no rounding in the tests.

Existing-test map (read before writing; the deepening, not a second shallow
test beside the first):
- ``highered-list-courses``: scripts/tests/test_highered.py::TestCourse::test_list
  (asserts ``is_ok`` only).
- ``highered-add-aid-package``: scripts/tests TestAidPackage::test_add and
  tests/test_highered.py TestAidPackage::test_add_package (shape only).
- ``highered-list-aid-packages``: scripts/tests TestAidPackage::test_list
  (``is_ok`` only); no behavioural test in tests/.
- ``highered-list-alumni-events``: scripts/tests TestAlumniEvent::test_list
  (``is_ok`` only); tests/ only covers add.
- ``highered-list-course-assignments``: tests/ covers add + duplicate refusal
  only; no list-effect test anywhere.
- ``highered-aid-summary-report``, ``highered-award-letter-report``,
  ``highered-academic-calendar-report``, ``highered-alumni-engagement-report``,
  ``highered-alumni-giving-report``, ``highered-faculty-workload-report``,
  ``highered-degree-completion-report`` (reports.py variant): imported in
  tests/test_highered.py but with no test body except the degree-completion
  status-only test; no test at all in scripts/tests.
"""
import os
import sys
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(os.path.dirname(_HERE), "scripts")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from helpers import (
    call_action,
    ns,
    seed_company,
    seed_degree_program,
    seed_course,
    seed_section,
    seed_student_record,
    seed_enrollment,
    seed_faculty,
    seed_alumnus,
    seed_aid_package,
)

from erpclaw_lib.db import get_connection
from erpclaw_lib import seam
from erpclaw_lib.query import Q, P, Table, Field, Order, dynamic_update

from registrar import list_courses, academic_calendar_report
from finaid import (
    add_aid_package as finaid_add_aid_package,
    list_aid_packages,
    aid_summary_report,
    award_letter_report,
    add_disbursement,
)
from alumni import (
    add_alumni_event,
    list_alumni_events,
    add_alumnus,
    add_giving_record,
    alumni_giving_report,
    alumni_engagement_report,
)
from faculty import (
    add_course_assignment,
    list_course_assignments,
    faculty_workload_report,
)
from reports import degree_completion_report


@pytest.fixture
def deep_conn(db_path):
    """Connection from the sanctioned helper plus a seeded company."""
    conn = get_connection(db_path)
    cid = seed_company(conn)
    yield conn, cid, db_path
    conn.close()


def _rows(conn, table):
    """Read every row of a table via PyPika; deterministic order for compare."""
    t = Table(table)
    q = Q.from_(t).select(t.star)
    fetched = conn.execute(q.get_sql()).fetchall()
    return sorted(
        (dict(r) for r in fetched),
        key=lambda d: repr(sorted((k, str(v)) for k, v in d.items())),
    )


def _snapshot(conn, tables):
    return {t: _rows(conn, t) for t in tables}


def _one(conn, table, pk):
    t = Table(table)
    q = (
        Q.from_(t)
        .select(t.star)
        .where(Field("id") == P())
    )
    row = conn.execute(q.get_sql(), (pk,)).fetchone()
    assert row is not None
    return dict(row)


def _count(conn, table):
    return len(_rows(conn, table))


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-courses — stored-row read. No ledger legs (read-only list).
# ══════════════════════════════════════════════════════════════════════════════

class TestListCoursesDepth:
    def test_lists_exactly_the_stored_rows(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("educlaw_course", db_path=db_path)
        c1 = seed_course(conn, cid, code="DEPTH101", name="Depth One", credits=3)
        c2 = seed_course(conn, cid, code="DEPTH202", name="Depth Two", credits=4)
        before = _snapshot(conn, ["educlaw_course"])
        result = call_action(list_courses, conn, ns(
            company_id=cid, department=None, is_active=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] >= 2
        by_id = {c["id"]: c for c in result["courses"]}
        assert by_id[c1]["code"] == "DEPTH101"
        assert by_id[c1]["name"] == "Depth One"
        assert by_id[c1]["credits"] == 3
        assert by_id[c2]["code"] == "DEPTH202"
        assert by_id[c2]["credits"] == 4
        stored = _one(conn, "educlaw_course", c1)
        assert stored["code"] == "DEPTH101"
        assert stored["name"] == "Depth One"
        assert stored["credits"] == 3
        assert _snapshot(conn, ["educlaw_course"]) == before

    def test_department_filter_matches_stored_rows(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        assert prog is not None
        c1 = seed_course(conn, cid, code="FILT111", name="Filtered", credits=2)
        t = Table("educlaw_course")
        filt = (
            Q.from_(t)
            .select(t.star)
            .where(t.company_id == P())
            .where(t.department == P())
        )
        eng_rows = conn.execute(filt.get_sql(), (cid, "Engineering")).fetchall()
        assert len(eng_rows) >= 1
        result = call_action(list_courses, conn, ns(
            company_id=cid, department="Engineering", is_active=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == len(eng_rows)
        assert c1 in {c["id"] for c in result["courses"]}

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        seed_course(conn, cid, code="REF999", name="Refusal", credits=1)
        before = _snapshot(conn, ["educlaw_course"])
        result = call_action(list_courses, conn, ns(
            company_id=None, department=None, is_active=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_course"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-academic-calendar-report — stored-row-derived report.
# No ledger legs (aggregate read over educlaw_section).
# ══════════════════════════════════════════════════════════════════════════════

class TestAcademicCalendarReportDepth:
    def test_term_row_matches_section_rows(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("educlaw_section", db_path=db_path)
        course = seed_course(conn, cid, code="CAL101", name="Calendar", credits=3)
        s1 = seed_section(conn, course, cid, term="Fall", year=2026, capacity=30)
        s2 = seed_section(conn, course, cid, term="Fall", year=2026, capacity=25)
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        seed_enrollment(conn, sid, s1, cid, status="enrolled")
        result = call_action(academic_calendar_report, conn, ns(
            company_id=cid, year=2026,
        ))
        assert result["status"] == "ok"
        rows_2026 = [r for r in result["calendar"] if r["year"] == 2026]
        assert len(rows_2026) == 1
        row = rows_2026[0]
        assert row["term"] == "Fall"
        assert row["total_sections"] == 2
        assert int(row["total_capacity"]) == 55
        assert int(row["total_enrolled"]) == 1
        assert _count(conn, "educlaw_section") == 2
        assert s1 in {r["id"] for r in _rows(conn, "educlaw_section")}
        assert s2 in {r["id"] for r in _rows(conn, "educlaw_section")}

    def test_year_filter_excludes_other_years(self, deep_conn):
        conn, cid, _ = deep_conn
        course = seed_course(conn, cid, code="CAL202", name="Cal Two", credits=3)
        seed_section(conn, course, cid, term="Spring", year=2027, capacity=20)
        result = call_action(academic_calendar_report, conn, ns(
            company_id=cid, year=2027,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["calendar"][0]["term"] == "Spring"
        assert result["calendar"][0]["total_sections"] == 1

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        course = seed_course(conn, cid, code="CALREF", name="Cal Ref", credits=1)
        seed_section(conn, course, cid, term="Fall", year=2026, capacity=10)
        before = _snapshot(conn, ["educlaw_section"])
        result = call_action(academic_calendar_report, conn, ns(
            company_id=None, year=None,
        ))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_section"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-add-aid-package — stored-row write to educlaw_scholarship.
# No ledger legs (no GL/journal write; aid is an offer record, not a posting).
# ══════════════════════════════════════════════════════════════════════════════

class TestAddAidPackageDepth:
    def test_stored_row_has_exact_money_text(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("educlaw_scholarship", db_path=db_path)
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        n_before = _count(conn, "educlaw_scholarship")
        disb_before = _count(conn, "highered_disbursement")
        result = call_action(finaid_add_aid_package, conn, ns(
            company_id=cid, student_id=sid, aid_year="2025-2026",
            total_cost="50000", efc="10000", total_need="40000",
            grants="5000", scholarships="5000", loans="3000", work_study="2000",
            package_status=None,
        ))
        assert result["status"] == "ok"
        assert result["total_aid"] == "15000.00"
        assert Decimal(str(result["total_aid"])) == Decimal("15000.00")
        assert result["package_status"] == "draft"
        assert _count(conn, "educlaw_scholarship") == n_before + 1
        stored = _one(conn, "educlaw_scholarship", result["id"])
        assert stored["student_id"] == sid
        assert stored["aid_year"] == "2025-2026"
        assert stored["total_cost"] == "50000.00"
        assert stored["efc"] == "10000.00"
        assert stored["total_need"] == "40000.00"
        assert stored["grants"] == "5000.00"
        assert stored["scholarships"] == "5000.00"
        assert stored["loans"] == "3000.00"
        assert stored["work_study"] == "2000.00"
        assert stored["total_aid"] == "15000.00"
        assert Decimal(str(stored["total_aid"])) == (
            Decimal(str(stored["grants"]))
            + Decimal(str(stored["scholarships"]))
            + Decimal(str(stored["loans"]))
            + Decimal(str(stored["work_study"]))
        )
        assert stored["package_status"] == "draft"
        assert _count(conn, "highered_disbursement") == disb_before

    def test_refusal_missing_student_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        before = _snapshot(conn, ["educlaw_scholarship"])
        result = call_action(finaid_add_aid_package, conn, ns(
            company_id=cid, student_id=None, aid_year="2025-2026",
            total_cost="10000", efc="2000", total_need="8000",
            grants="1000", scholarships="1000", loans="1000", work_study="1000",
            package_status=None,
        ))
        assert result["status"] == "error"
        assert "student" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_scholarship"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-aid-packages — stored-row read. No ledger legs (read-only).
# ══════════════════════════════════════════════════════════════════════════════

class TestListAidPackagesDepth:
    def test_filter_by_student_returns_exact_rows(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("educlaw_scholarship", db_path=db_path)
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog, name="Aid List A")
        sid_other = seed_student_record(conn, cid, prog, name="Aid List B")
        p1 = seed_aid_package(conn, sid, cid, package_status="offered",
                              total_aid="15000.00")
        seed_aid_package(conn, sid_other, cid, package_status="draft",
                         total_aid="8000.00")
        before = _snapshot(conn, ["educlaw_scholarship"])
        result = call_action(list_aid_packages, conn, ns(
            company_id=cid, student_id=sid, aid_year=None,
            package_status=None, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["packages"][0]["id"] == p1
        assert result["packages"][0]["total_aid"] == "15000.00"
        assert Decimal(str(result["packages"][0]["total_aid"])) == Decimal("15000.00")
        stored = _one(conn, "educlaw_scholarship", p1)
        assert stored["package_status"] == "offered"
        assert stored["total_aid"] == "15000.00"
        assert _snapshot(conn, ["educlaw_scholarship"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        seed_aid_package(conn, sid, cid)
        before = _snapshot(conn, ["educlaw_scholarship"])
        result = call_action(list_aid_packages, conn, ns(
            company_id=None, student_id=None, aid_year=None,
            package_status=None, limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_scholarship"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-aid-summary-report — stored-row-derived report (grouped counts).
# No ledger legs (aggregate read over educlaw_scholarship).
# ══════════════════════════════════════════════════════════════════════════════

class TestAidSummaryReportDepth:
    def test_summary_counts_match_stored_statuses(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        seed_aid_package(conn, sid, cid, package_status="draft",
                         total_aid="10000.00")
        seed_aid_package(conn, sid, cid, package_status="offered",
                         total_aid="15000.00")
        before = _snapshot(conn, ["educlaw_scholarship"])
        result = call_action(aid_summary_report, conn, ns(
            company_id=cid, aid_year="2025-2026",
        ))
        assert result["status"] == "ok"
        got = {r["package_status"]: r["count"] for r in result["summary"]}
        assert got.get("draft") == 1
        assert got.get("offered") == 1
        assert _snapshot(conn, ["educlaw_scholarship"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        seed_aid_package(conn, sid, cid)
        before = _snapshot(conn, ["educlaw_scholarship"])
        result = call_action(aid_summary_report, conn, ns(
            company_id=None, aid_year=None,
        ))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_scholarship"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-award-letter-report — stored-row read (package + disbursements).
# No ledger legs (read-only; disbursement rows are pending offers, not postings).
# ══════════════════════════════════════════════════════════════════════════════

class TestAwardLetterReportDepth:
    def test_package_and_disbursement_match_stored_rows(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        pkg = seed_aid_package(conn, sid, cid, package_status="offered",
                               total_aid="15000.00")
        before_pkg = _one(conn, "educlaw_scholarship", pkg)
        disb = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg, amount="5000",
            aid_type="grant", fund_source="Federal", disbursement_date=None,
        ))
        assert disb["status"] == "ok"
        assert disb["amount"] == "5000.00"
        before = _snapshot(conn, ["educlaw_scholarship", "highered_disbursement"])
        result = call_action(award_letter_report, conn, ns(id=pkg))
        assert result["status"] == "ok"
        assert result["package"]["id"] == pkg
        assert result["package"]["total_aid"] == "15000.00"
        assert Decimal(str(result["package"]["total_aid"])) == Decimal("15000.00")
        assert result["package"]["total_aid"] == before_pkg["total_aid"]
        assert len(result["disbursements"]) == 1
        assert result["disbursements"][0]["amount"] == "5000.00"
        assert Decimal(str(result["disbursements"][0]["amount"])) == Decimal("5000.00")
        stored_disb = _one(conn, "highered_disbursement", disb["id"])
        assert stored_disb["amount"] == "5000.00"
        assert stored_disb["disbursement_status"] == "pending"
        assert _snapshot(conn, ["educlaw_scholarship", "highered_disbursement"]) == before

    def test_refusal_unknown_package_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        sid = seed_student_record(conn, cid, prog)
        seed_aid_package(conn, sid, cid)
        before = _snapshot(conn, ["educlaw_scholarship", "highered_disbursement"])
        result = call_action(award_letter_report, conn, ns(id="no-such-package"))
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_scholarship", "highered_disbursement"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-alumni-events — stored-row read. No ledger legs (read-only).
# ══════════════════════════════════════════════════════════════════════════════

class TestListAlumniEventsDepth:
    def test_filter_by_type_returns_exact_rows(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("highered_alumni_event", db_path=db_path)
        r1 = call_action(add_alumni_event, conn, ns(
            company_id=cid, name="Depth Reunion",
            event_date="2026-10-15", event_type="reunion", attendees=200,
        ))
        assert r1["status"] == "ok"
        r2 = call_action(add_alumni_event, conn, ns(
            company_id=cid, name="Depth Mixer",
            event_date="2026-11-01", event_type="networking", attendees=50,
        ))
        assert r2["status"] == "ok"
        before = _snapshot(conn, ["highered_alumni_event"])
        result = call_action(list_alumni_events, conn, ns(
            company_id=cid, event_type="reunion", limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["events"][0]["id"] == r1["id"]
        assert result["events"][0]["name"] == "Depth Reunion"
        assert result["events"][0]["event_date"] == "2026-10-15"
        assert result["events"][0]["attendees"] == 200
        stored = _one(conn, "highered_alumni_event", r1["id"])
        assert stored["event_type"] == "reunion"
        assert stored["attendees"] == 200
        assert _one(conn, "highered_alumni_event", r2["id"])["event_type"] == "networking"
        assert _snapshot(conn, ["highered_alumni_event"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        call_action(add_alumni_event, conn, ns(
            company_id=cid, name="Refusal Event",
            event_date="2026-10-15", event_type="other", attendees=10,
        ))
        before = _snapshot(conn, ["highered_alumni_event"])
        result = call_action(list_alumni_events, conn, ns(
            company_id=None, event_type=None, limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["highered_alumni_event"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-alumni-giving-report — stored-row-derived report over
# highered_giving_record. No ledger legs (donation records, not GL postings).
# Money note: the report aggregates with CAST(amount AS NUMERIC), so per-type
# totals and the grand total come back NUMERIC, not TEXT; the tests compare
# them as exact Decimals, never floats.
# ══════════════════════════════════════════════════════════════════════════════

class TestAlumniGivingReportDepth:
    def test_totals_match_stored_gifts(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("highered_giving_record", db_path=db_path)
        aid = seed_alumnus(conn, cid)
        g1 = call_action(add_giving_record, conn, ns(
            company_id=cid, alumnus_id=aid, amount="5000",
            giving_date="2026-01-15", campaign="Annual Fund", gift_type="cash",
        ))
        assert g1["status"] == "ok"
        g2 = call_action(add_giving_record, conn, ns(
            company_id=cid, alumnus_id=aid, amount="2500",
            giving_date="2026-02-15", campaign="Annual Fund", gift_type="stock",
        ))
        assert g2["status"] == "ok"
        alum = _one(conn, "highered_alumnus", aid)
        assert alum["is_donor"] == 1
        assert alum["total_giving"] == "7500.00"
        assert Decimal(str(alum["total_giving"])) == Decimal("7500.00")
        before = _snapshot(conn, ["highered_giving_record", "highered_alumnus"])
        result = call_action(alumni_giving_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        by_type = {r["gift_type"]: r for r in result["by_type"]}
        assert by_type["cash"]["count"] == 1
        assert Decimal(str(by_type["cash"]["total_amount"])) == Decimal("5000")
        assert by_type["stock"]["count"] == 1
        assert Decimal(str(by_type["stock"]["total_amount"])) == Decimal("2500")
        assert Decimal(str(result["grand_total"])) == Decimal("7500")
        assert _snapshot(conn, ["highered_giving_record", "highered_alumnus"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        aid = seed_alumnus(conn, cid)
        call_action(add_giving_record, conn, ns(
            company_id=cid, alumnus_id=aid, amount="100",
            giving_date="2026-01-01", campaign="", gift_type="cash",
        ))
        before = _snapshot(conn, ["highered_giving_record", "highered_alumnus"])
        result = call_action(alumni_giving_report, conn, ns(company_id=None))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["highered_giving_record", "highered_alumnus"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-alumni-engagement-report — stored-row-derived report over
# highered_alumnus. No ledger legs (aggregate read).
# ══════════════════════════════════════════════════════════════════════════════

class TestAlumniEngagementReportDepth:
    def test_levels_match_stored_alumni(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("highered_alumnus", db_path=db_path)
        seed_alumnus(conn, cid, name="Eng Low")
        call_action(add_alumnus, conn, ns(
            company_id=cid, name="Eng High", email="high@alumni.edu",
            graduation_year=2015, degree_program="Biology",
            employer="BioTech", job_title="Researcher",
            engagement_level="high",
        ))
        call_action(add_alumnus, conn, ns(
            company_id=cid, name="Eng Med", email="med@alumni.edu",
            graduation_year=2016, degree_program="Math",
            employer="Corp", job_title="Analyst",
            engagement_level="medium",
        ))
        before = _snapshot(conn, ["highered_alumnus"])
        result = call_action(alumni_engagement_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["total_alumni"] == 3
        got = {r["engagement_level"]: r["count"] for r in result["engagement"]}
        assert got.get("low") == 1
        assert got.get("medium") == 1
        assert got.get("high") == 1
        assert sum(got.values()) == result["total_alumni"]
        assert _snapshot(conn, ["highered_alumnus"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        seed_alumnus(conn, cid)
        before = _snapshot(conn, ["highered_alumnus"])
        result = call_action(alumni_engagement_report, conn, ns(company_id=None))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["highered_alumnus"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-course-assignments — stored-row read.
# No ledger legs (read-only).
# ══════════════════════════════════════════════════════════════════════════════

class TestListCourseAssignmentsDepth:
    def test_filter_by_faculty_returns_exact_row(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("highered_course_assignment", db_path=db_path)
        fid = seed_faculty(conn, cid)
        course = seed_course(conn, cid, code="ASSIGN101", name="Assign", credits=3)
        sec = seed_section(conn, course, cid)
        made = call_action(add_course_assignment, conn, ns(
            company_id=cid, faculty_id=fid, section_id=sec, role="primary",
        ))
        assert made["status"] == "ok"
        before = _snapshot(conn, ["highered_course_assignment"])
        result = call_action(list_course_assignments, conn, ns(
            company_id=cid, faculty_id=fid, section_id=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["assignments"][0]["id"] == made["id"]
        assert result["assignments"][0]["faculty_id"] == fid
        assert result["assignments"][0]["section_id"] == sec
        assert result["assignments"][0]["role"] == "primary"
        stored = _one(conn, "highered_course_assignment", made["id"])
        assert stored["faculty_id"] == fid
        assert stored["section_id"] == sec
        assert stored["role"] == "primary"
        assert _snapshot(conn, ["highered_course_assignment"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        fid = seed_faculty(conn, cid)
        course = seed_course(conn, cid, code="ASSIGNREF", name="AssignRef", credits=1)
        sec = seed_section(conn, course, cid)
        call_action(add_course_assignment, conn, ns(
            company_id=cid, faculty_id=fid, section_id=sec, role="primary",
        ))
        before = _snapshot(conn, ["highered_course_assignment"])
        result = call_action(list_course_assignments, conn, ns(
            company_id=None, faculty_id=None, section_id=None,
            limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["highered_course_assignment"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-faculty-workload-report — stored-row-derived report joining
# educlaw_instructor, highered_course_assignment and highered_research_grant.
# No ledger legs (aggregate read).
# ══════════════════════════════════════════════════════════════════════════════

class TestFacultyWorkloadReportDepth:
    def test_sections_and_grants_match_stored_rows(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("educlaw_instructor", db_path=db_path)
        fid = seed_faculty(conn, cid, name="Dr. Workload")
        course = seed_course(conn, cid, code="WORK101", name="Work", credits=3)
        sec = seed_section(conn, course, cid)
        made = call_action(add_course_assignment, conn, ns(
            company_id=cid, faculty_id=fid, section_id=sec, role="primary",
        ))
        assert made["status"] == "ok"
        before = _snapshot(conn, ["educlaw_instructor", "highered_course_assignment",
                                  "highered_research_grant"])
        result = call_action(faculty_workload_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["count"] == 1
        row = result["workload"][0]
        assert row["id"] == fid
        assert row["name"] == "Dr. Workload"
        assert int(row["sections_assigned"]) == 1
        assert int(row["active_grants"]) == 0
        assert _snapshot(conn, ["educlaw_instructor", "highered_course_assignment",
                                "highered_research_grant"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        seed_faculty(conn, cid)
        before = _snapshot(conn, ["educlaw_instructor", "highered_course_assignment"])
        result = call_action(faculty_workload_report, conn, ns(company_id=None))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_instructor", "highered_course_assignment"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-degree-completion-report (reports.py variant) — stored-row-derived
# report joining educlaw_student to highered_degree_program.
# No ledger legs (aggregate read).
# ══════════════════════════════════════════════════════════════════════════════

class TestDegreeCompletionReportDepth:
    def test_eligible_count_matches_stored_students(self, deep_conn):
        conn, cid, db_path = deep_conn
        assert seam.table_exists("highered_degree_program", db_path=db_path)
        prog = seed_degree_program(conn, cid, credits_required=120)
        sid_grad = seed_student_record(conn, cid, prog, name="Graduate", gpa="3.50")
        sid_short = seed_student_record(conn, cid, prog, name="Short", gpa="3.00")
        t = Table("educlaw_student")
        sql, params = dynamic_update(
            "educlaw_student", {"total_credits": 130}, {"student_id": sid_grad})
        conn.execute(sql, params)
        sql2, params2 = dynamic_update(
            "educlaw_student", {"total_credits": 30}, {"student_id": sid_short})
        conn.execute(sql2, params2)
        conn.commit()
        before = _snapshot(conn, ["educlaw_student", "highered_degree_program"])
        result = call_action(degree_completion_report, conn, ns(company_id=cid))
        assert result["status"] == "ok"
        assert result["count"] == 1
        row = result["programs"][0]
        assert row["credits_required"] == 120
        assert int(row["total_students"]) == 2
        assert int(row["eligible_for_graduation"]) == 1
        check = conn.execute(
            Q.from_(t).select(t.student_id, t.total_credits, t.gpa)
            .where(t.company_id == P()).get_sql(), (cid,)).fetchall()
        assert len(check) == 2
        assert _snapshot(conn, ["educlaw_student", "highered_degree_program"]) == before

    def test_refusal_missing_company_id_writes_nothing(self, deep_conn):
        conn, cid, _ = deep_conn
        prog = seed_degree_program(conn, cid)
        seed_student_record(conn, cid, prog)
        before = _snapshot(conn, ["educlaw_student", "highered_degree_program"])
        result = call_action(degree_completion_report, conn, ns(company_id=None))
        assert result["status"] == "error"
        assert "company" in result["message"].lower()
        assert _snapshot(conn, ["educlaw_student", "highered_degree_program"]) == before
