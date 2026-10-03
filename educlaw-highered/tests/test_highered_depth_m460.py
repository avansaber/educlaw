"""Behavioural depth tests for nine educlaw-highered actions.

Each action below already had a test that proved only response shape (the
module's own ``test_highered.py``) or mere routability (the contract suite in
``testing/integration/contract/test_educlaw_highered_contract.py``). Neither
observed the database, so a handler could return a perfectly shaped response
while writing nothing and still pass. These tests assert the effect instead:

- update actions: the exact stored row afterwards (changed fields move from
  the pinned before-values to the new values; every other column is unchanged).
- list actions: the returned rows match the stored rows exactly, filters and
  company scoping select the right rows, and counts are exact.
- pure-computation actions (``highered-transfer-credit-eval`` and
  ``highered-what-if-audit``): the computed values are derived from seeded
  enrollments, and the database is byte-identical afterwards (they write
  nothing by design).
- every action: one refusal case where the refusal happens, the message names
  the real reason, and the database is byte-identical afterwards.

Signal depth per action (stored row vs ledger effect): all nine assert stored
rows. None of these handlers reaches the general ledger -- no ``gl_entry``
write exists in ``registrar.py``, ``records.py``, ``finaid.py``, ``alumni.py``
or ``faculty.py`` -- so there are no balanced-legs assertions to add here. A
later reader must not add one; there are no legs to balance.

Money is text throughout: exact ``Decimal``-as-string comparisons only, never
float, never approximate, never ``round``.

Connections come from ``erpclaw_lib.db.get_connection()`` (which follows the
``ERPCLAW_DB_PATH`` the ``db_path`` fixture sets); verification reads are
built with PyPika through ``erpclaw_lib.query``. No ``sqlite_master``, no
``PRAGMA``, no ``information_schema``.
"""
import sys
import os
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(os.path.dirname(_HERE), "scripts")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from helpers import (
    call_action, ns,
    seed_company, seed_degree_program, seed_course, seed_section,
    seed_student_record, seed_enrollment, seed_faculty, seed_alumnus,
    seed_aid_package,
)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, dynamic_update, insert_row

from registrar import update_course, list_sections
from records import transfer_credit_eval, what_if_audit
from finaid import update_aid_package, list_disbursements, add_disbursement
from alumni import update_alumnus
from faculty import update_faculty, list_research_grants, add_research_grant


SNAPSHOT_TABLES = [
    "company", "naming_series", "audit_log",
    "highered_degree_program", "highered_hold", "highered_disbursement",
    "highered_alumnus", "highered_alumni_event", "highered_giving_record",
    "highered_course_assignment", "highered_research_grant",
    "highered_application", "highered_admission_decision",
    "educlaw_course", "educlaw_section", "educlaw_course_enrollment",
    "educlaw_student", "educlaw_scholarship", "educlaw_instructor",
]


@pytest.fixture
def env(db_path):
    """Fresh database with one company and one degree program.

    The ``db_path`` fixture builds the schema and points ``ERPCLAW_DB_PATH``
    at it, so ``get_connection()`` below opens the test database.
    """
    conn = get_connection()
    cid = seed_company(conn)
    prog_id = seed_degree_program(conn, cid)
    yield conn, cid, prog_id
    conn.close()


def _row_by_id(conn, table, row_id):
    """Read one stored row back through the seam; fail loudly if absent."""
    tab = Table(table)
    sql = Q.from_(tab).select(tab.star).where(Field("id") == P()).get_sql()
    row = conn.execute(sql, (row_id,)).fetchone()
    assert row is not None, f"expected a row in {table} with id {row_id}"
    return dict(row)


def _seed_faculty(conn, company_id, name, employee_id,
                  department="Engineering", rank="professor"):
    """Insert a faculty row with an explicit employee_id.

    The shared seed and the ``highered-add-faculty`` action both leave
    ``employee_id`` at its ``''`` default while that column is UNIQUE, so a
    second such row raises IntegrityError (recorded in CHANGES.md as a
    finding, deliberately not fixed here). Explicit ids keep this test's
    setup independent of that defect.
    """
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz
    fid = str(_uuid.uuid4())
    now = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql, _ = insert_row("educlaw_instructor", {
        "id": P(), "naming_series": P(), "employee_id": P(), "name": P(),
        "email": P(), "department": P(), "rank": P(), "tenure_status": P(),
        "hire_date": P(), "company_id": P(), "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql, (fid, f"HFAC-{fid[:8]}", employee_id, name,
          f"{fid[:6]}@univ.edu", department, rank, "tenured",
          "2020-08-01", company_id, now, now))
    conn.commit()
    return fid


def _snapshot(conn):
    """Byte-level picture of every table this module can write."""
    snap = {}
    for name in SNAPSHOT_TABLES:
        tab = Table(name)
        sql = Q.from_(tab).select(tab.star).orderby(tab.id).get_sql()
        rows = conn.execute(sql).fetchall()
        snap[name] = sorted(
            tuple("" if value is None else str(value) for value in tuple(row))
            for row in rows
        )
    return snap


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-disbursements (stored-row signal; no ledger legs -- finaid.py
# writes no gl_entry)
# ══════════════════════════════════════════════════════════════════════════════

class TestListDisbursementsDepth:
    def test_lists_exact_stored_rows_with_filter_and_scoping(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        pkg1 = seed_aid_package(conn, sid, cid, package_status="offered")
        d1 = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg1, amount="5000",
            aid_type="grant", fund_source="Federal", disbursement_date="2026-09-01",
        ))
        assert d1["status"] == "ok"
        d2 = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg1, amount="2500.5",
            aid_type="scholarship", fund_source="State", disbursement_date="2026-09-02",
        ))
        assert d2["status"] == "ok"
        pkg2 = seed_aid_package(conn, sid, cid, package_status="accepted")
        d3 = call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg2, amount="100",
            aid_type="loan", fund_source="", disbursement_date="2026-09-03",
        ))
        assert d3["status"] == "ok"
        other_cid = seed_company(conn)
        other_pkg = seed_aid_package(conn, sid, other_cid, package_status="offered")
        call_action(add_disbursement, conn, ns(
            company_id=other_cid, aid_package_id=other_pkg, amount="999",
            aid_type="grant", fund_source="", disbursement_date="2026-09-04",
        ))

        result = call_action(list_disbursements, conn, ns(
            company_id=cid, aid_package_id=pkg1, limit=50, offset=0,
        ))
        assert result["status"] == "ok"
        assert result["count"] == 2
        assert sorted(r["amount"] for r in result["disbursements"]) == ["2500.50", "5000.00"]
        for resp in result["disbursements"]:
            stored = _row_by_id(conn, "highered_disbursement", resp["id"])
            assert resp["aid_package_id"] == pkg1 == stored["aid_package_id"]
            assert resp["amount"] == stored["amount"]
            assert Decimal(resp["amount"]) == Decimal(stored["amount"])
            assert resp["aid_type"] == stored["aid_type"]
            assert resp["fund_source"] == stored["fund_source"]
            assert resp["disbursement_status"] == "pending" == stored["disbursement_status"]
        by_id = {r["id"]: r for r in result["disbursements"]}
        assert by_id[d1["id"]]["amount"] == "5000.00"
        assert by_id[d2["id"]]["amount"] == "2500.50"
        assert Decimal(by_id[d2["id"]]["amount"]) == Decimal("2500.50")

        unfiltered = call_action(list_disbursements, conn, ns(
            company_id=cid, aid_package_id=None, limit=50, offset=0,
        ))
        assert unfiltered["count"] == 3
        assert d3["id"] in {r["id"] for r in unfiltered["disbursements"]}
        other = call_action(list_disbursements, conn, ns(
            company_id=other_cid, aid_package_id=None, limit=50, offset=0,
        ))
        assert other["count"] == 1
        assert other["disbursements"][0]["amount"] == "999.00"

    def test_refusal_missing_company_writes_nothing(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        pkg = seed_aid_package(conn, sid, cid, package_status="offered")
        call_action(add_disbursement, conn, ns(
            company_id=cid, aid_package_id=pkg, amount="5000",
            aid_type="grant", fund_source="", disbursement_date="2026-09-01",
        ))
        before = _snapshot(conn)
        result = call_action(list_disbursements, conn, ns(
            company_id=None, aid_package_id=None, limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company-id" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-research-grants (stored-row signal; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestListResearchGrantsDepth:
    def test_lists_exact_stored_rows_with_filters(self, env):
        conn, cid, _ = env
        fid1 = _seed_faculty(conn, cid, "Dr. Alpha", "EMP-001")
        fid2 = _seed_faculty(conn, cid, "Dr. Beta", "EMP-002")
        g1 = call_action(add_research_grant, conn, ns(
            company_id=cid, faculty_id=fid1, title="AI Research",
            funding_agency="NSF", amount="250000",
            start_date="2026-01-01", end_date="2028-12-31", grant_status="active",
        ))
        assert g1["status"] == "ok"
        g2 = call_action(add_research_grant, conn, ns(
            company_id=cid, faculty_id=fid1, title="Robotics Lab",
            funding_agency="DARPA", amount="100000.5",
            start_date="2026-06-01", end_date="2027-06-01", grant_status="proposed",
        ))
        assert g2["status"] == "ok"
        g3 = call_action(add_research_grant, conn, ns(
            company_id=cid, faculty_id=fid2, title="Quantum Study",
            funding_agency="DOE", amount="75000",
            start_date="2026-03-01", end_date="2029-03-01", grant_status="active",
        ))
        assert g3["status"] == "ok"

        by_faculty = call_action(list_research_grants, conn, ns(
            company_id=cid, faculty_id=fid1, grant_status=None, limit=50, offset=0,
        ))
        assert by_faculty["status"] == "ok"
        assert by_faculty["count"] == 2
        assert sorted(r["title"] for r in by_faculty["grants"]) == ["AI Research", "Robotics Lab"]
        assert sorted(r["amount"] for r in by_faculty["grants"]) == ["100000.50", "250000.00"]
        for resp in by_faculty["grants"]:
            stored = _row_by_id(conn, "highered_research_grant", resp["id"])
            assert resp["faculty_id"] == fid1 == stored["faculty_id"]
            assert resp["title"] == stored["title"]
            assert resp["amount"] == stored["amount"]
            assert Decimal(resp["amount"]) == Decimal(stored["amount"])
            assert resp["funding_agency"] == stored["funding_agency"]
            assert resp["grant_status"] == stored["grant_status"]
        assert g1["amount"] == "250000.00"
        assert Decimal(_row_by_id(conn, "highered_research_grant", g1["id"])["amount"]) == Decimal("250000.00")

        active = call_action(list_research_grants, conn, ns(
            company_id=cid, faculty_id=None, grant_status="active", limit=50, offset=0,
        ))
        assert active["count"] == 2
        assert {r["id"] for r in active["grants"]} == {g1["id"], g3["id"]}

    def test_refusal_missing_company_writes_nothing(self, env):
        conn, cid, _ = env
        fid = seed_faculty(conn, cid)
        call_action(add_research_grant, conn, ns(
            company_id=cid, faculty_id=fid, title="Seed Grant",
            funding_agency="NSF", amount="1000",
            start_date="2026-01-01", end_date="2026-12-31", grant_status="active",
        ))
        before = _snapshot(conn)
        result = call_action(list_research_grants, conn, ns(
            company_id=None, faculty_id=None, grant_status=None, limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company-id" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-list-sections (stored-row signal; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestListSectionsDepth:
    def test_lists_exact_stored_rows_with_filters(self, env):
        conn, cid, _ = env
        c1 = seed_course(conn, cid, code="LSC101", name="List Course One")
        c2 = seed_course(conn, cid, code="LSC102", name="List Course Two")
        s1 = seed_section(conn, c1, cid, term="Fall", year=2026)
        s2 = seed_section(conn, c1, cid, term="Spring", year=2026)
        s3 = seed_section(conn, c2, cid, term="Fall", year=2026)

        by_course = call_action(list_sections, conn, ns(
            company_id=cid, course_id=c1, term=None, year=None,
            section_status=None, limit=50, offset=0,
        ))
        assert by_course["status"] == "ok"
        assert by_course["count"] == 2
        assert {r["id"] for r in by_course["sections"]} == {s1, s2}
        assert sorted(r["term"] for r in by_course["sections"]) == ["Fall", "Spring"]
        for resp in by_course["sections"]:
            stored = _row_by_id(conn, "educlaw_section", resp["id"])
            assert resp["course_id"] == c1 == stored["course_id"]
            assert resp["term"] == stored["term"]
            assert resp["year"] == stored["year"] == 2026
            assert resp["section_status"] == "open" == stored["section_status"]

        fall = call_action(list_sections, conn, ns(
            company_id=cid, course_id=None, term="Fall", year=2026,
            section_status=None, limit=50, offset=0,
        ))
        assert fall["count"] == 2
        assert {r["id"] for r in fall["sections"]} == {s1, s3}

    def test_refusal_missing_company_writes_nothing(self, env):
        conn, cid, _ = env
        course_id = seed_course(conn, cid)
        seed_section(conn, course_id, cid)
        before = _snapshot(conn)
        result = call_action(list_sections, conn, ns(
            company_id=None, course_id=None, term=None, year=None,
            section_status=None, limit=50, offset=0,
        ))
        assert result["status"] == "error"
        assert "company-id" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-transfer-credit-eval (pure computation: stored-row signal on the
# read side, and proof it writes nothing; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestTransferCreditEvalDepth:
    def test_evaluation_derives_from_enrollments_and_writes_nothing(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        c1 = seed_course(conn, cid, code="TCE101", name="Transfer Math", credits=30)
        s1 = seed_section(conn, c1, cid)
        seed_enrollment(conn, sid, s1, cid, status="completed", grade="A")
        c2 = seed_course(conn, cid, code="TCE102", name="Old Seminar", credits=4)
        s2 = seed_section(conn, c2, cid)
        seed_enrollment(conn, sid, s2, cid, status="completed", grade="B")
        sql, params = dynamic_update("educlaw_course", {"is_active": 0}, {"id": c2})
        conn.execute(sql, params)
        conn.commit()

        before = _snapshot(conn)
        result = call_action(transfer_credit_eval, conn, ns(
            student_id=sid, program_id=prog_id,
        ))
        assert result["status"] == "ok"
        assert result["student_id"] == sid
        assert result["target_program_id"] == prog_id
        assert result["credits_required"] == 120
        assert result["accepted_transfer_credits"] == 30
        assert result["credits_remaining"] == 90
        assert len(result["accepted_courses"]) == 1
        accepted = result["accepted_courses"][0]
        assert accepted["code"] == "TCE101"
        assert accepted["name"] == "Transfer Math"
        assert accepted["credits"] == 30
        assert accepted["grade"] == "A"
        assert accepted["status"] == "accepted"
        assert len(result["not_applicable_courses"]) == 1
        rejected = result["not_applicable_courses"][0]
        assert rejected["code"] == "TCE102"
        assert rejected["status"] == "not_applicable"
        assert _snapshot(conn) == before

    def test_refusal_unknown_student_writes_nothing(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        seed_enrollment(conn, sid, section_id, cid, status="completed", grade="A")
        before = _snapshot(conn)
        result = call_action(transfer_credit_eval, conn, ns(
            student_id="no-such-student", program_id=prog_id,
        ))
        assert result["status"] == "error"
        assert "Student record not found" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-update-aid-package (stored-row signal incl. money recalc; no ledger
# legs -- finaid.py writes no gl_entry)
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateAidPackageDepth:
    def test_amounts_recalc_and_untouched_fields_pinned(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid, package_status="draft")
        before = _row_by_id(conn, "educlaw_scholarship", pkg_id)
        assert before["grants"] == "5000.00"
        assert before["total_aid"] == "15000.00"

        result = call_action(update_aid_package, conn, ns(
            id=pkg_id, aid_year=None, total_cost=None, efc=None,
            total_need=None, grants="10000", scholarships=None,
            loans=None, work_study=None, package_status="offered",
        ))
        assert result["status"] == "ok"

        after = _row_by_id(conn, "educlaw_scholarship", pkg_id)
        assert after["grants"] == "10000.00"
        assert after["total_aid"] == "20000.00"
        assert after["package_status"] == "offered"
        assert Decimal(after["total_aid"]) == (
            Decimal(after["grants"]) + Decimal(after["scholarships"])
            + Decimal(after["loans"]) + Decimal(after["work_study"])
        )
        assert Decimal(after["total_aid"]) == Decimal("20000.00")
        for field in ("scholarships", "loans", "work_study", "total_cost",
                      "efc", "total_need", "aid_year", "student_id", "company_id"):
            assert after[field] == before[field], field

    def test_refusal_cancelled_package_writes_nothing(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        pkg_id = seed_aid_package(conn, sid, cid, package_status="cancelled")
        before = _snapshot(conn)
        result = call_action(update_aid_package, conn, ns(
            id=pkg_id, aid_year=None, total_cost=None, efc=None,
            total_need=None, grants="99999", scholarships=None,
            loans=None, work_study=None, package_status=None,
        ))
        assert result["status"] == "error"
        assert "cancelled" in result["message"]
        assert _snapshot(conn) == before
        assert _row_by_id(conn, "educlaw_scholarship", pkg_id)["grants"] == "5000.00"


# ══════════════════════════════════════════════════════════════════════════════
# highered-update-alumnus (stored-row signal; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateAlumnusDepth:
    def test_changed_fields_move_and_rest_pinned(self, env):
        conn, cid, _ = env
        aid = seed_alumnus(conn, cid)
        before = _row_by_id(conn, "highered_alumnus", aid)
        assert before["employer"] == "Tech Corp"
        assert before["engagement_level"] == "low"

        result = call_action(update_alumnus, conn, ns(
            id=aid, name=None, email=None, degree_program=None,
            employer="New Corp", job_title="Manager",
            graduation_year=None, engagement_level="high",
        ))
        assert result["status"] == "ok"

        after = _row_by_id(conn, "highered_alumnus", aid)
        assert after["employer"] == "New Corp"
        assert after["job_title"] == "Manager"
        assert after["engagement_level"] == "high"
        for field in ("name", "email", "graduation_year", "degree_program",
                      "is_donor", "total_giving", "company_id"):
            assert after[field] == before[field], field

    def test_refusal_invalid_engagement_writes_nothing(self, env):
        conn, cid, _ = env
        aid = seed_alumnus(conn, cid)
        before = _snapshot(conn)
        result = call_action(update_alumnus, conn, ns(
            id=aid, name=None, email=None, degree_program=None,
            employer=None, job_title=None,
            graduation_year=None, engagement_level="royalty",
        ))
        assert result["status"] == "error"
        assert "engagement_level" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-update-course (stored-row signal; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateCourseDepth:
    def test_changed_fields_move_and_rest_pinned(self, env):
        conn, cid, _ = env
        course_id = seed_course(conn, cid, code="UDC101", name="Old Name", credits=3)
        before = _row_by_id(conn, "educlaw_course", course_id)
        assert before["name"] == "Old Name"
        assert before["credits"] == 3

        result = call_action(update_course, conn, ns(
            id=course_id, name="New Name", department="Computer Science",
            prerequisites=None, description=None, credits=4, is_active=None,
        ))
        assert result["status"] == "ok"

        after = _row_by_id(conn, "educlaw_course", course_id)
        assert after["name"] == "New Name"
        assert after["credits"] == 4
        assert after["department"] == "Computer Science"
        for field in ("code", "course_code", "prerequisites", "description",
                      "is_active", "company_id"):
            assert after[field] == before[field], field

    def test_refusal_unknown_course_writes_nothing(self, env):
        conn, cid, _ = env
        seed_course(conn, cid)
        before = _snapshot(conn)
        result = call_action(update_course, conn, ns(
            id="no-such-course", name="Ghost", department=None,
            prerequisites=None, description=None, credits=None, is_active=None,
        ))
        assert result["status"] == "error"
        assert "Course not found" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-update-faculty (stored-row signal; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateFacultyDepth:
    def test_changed_fields_move_and_rest_pinned(self, env):
        conn, cid, _ = env
        fid = seed_faculty(conn, cid, department="Engineering", rank="professor")
        before = _row_by_id(conn, "educlaw_instructor", fid)
        assert before["rank"] == "professor"
        assert before["department"] == "Engineering"

        result = call_action(update_faculty, conn, ns(
            id=fid, name=None, email=None, department="Physics",
            hire_date=None, rank="associate_professor", tenure_status=None,
        ))
        assert result["status"] == "ok"

        after = _row_by_id(conn, "educlaw_instructor", fid)
        assert after["rank"] == "associate_professor"
        assert after["department"] == "Physics"
        for field in ("name", "email", "tenure_status", "hire_date",
                      "is_active", "company_id"):
            assert after[field] == before[field], field

    def test_refusal_invalid_rank_writes_nothing(self, env):
        conn, cid, _ = env
        fid = seed_faculty(conn, cid)
        before = _snapshot(conn)
        result = call_action(update_faculty, conn, ns(
            id=fid, name=None, email=None, department=None,
            hire_date=None, rank="dean", tenure_status=None,
        ))
        assert result["status"] == "error"
        assert "rank" in result["message"]
        assert _snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# highered-what-if-audit (pure computation: stored-row signal on the read
# side, and proof it writes nothing; no ledger legs)
# ══════════════════════════════════════════════════════════════════════════════

class TestWhatIfAuditDepth:
    def test_simulation_derives_from_enrollments_and_writes_nothing(self, env):
        conn, cid, prog_id = env
        alt_prog = seed_degree_program(
            conn, cid, name="Data Science",
            degree_type="master", credits_required=60,
        )
        sid = seed_student_record(conn, cid, prog_id)
        course_id = seed_course(conn, cid, code="WIA101", name="What If Stats", credits=30)
        section_id = seed_section(conn, course_id, cid)
        seed_enrollment(conn, sid, section_id, cid, status="completed", grade="A")

        before = _snapshot(conn)
        result = call_action(what_if_audit, conn, ns(
            student_id=sid, program_id=alt_prog,
        ))
        assert result["status"] == "ok"
        assert result["student_id"] == sid
        current = result["current_program"]
        assert current["id"] == prog_id
        assert current["credits_required"] == 120
        assert current["credits_earned"] == 30
        assert current["credits_remaining"] == 90
        assert current["progress_percent"] == 25.0
        target = result["what_if_program"]
        assert target["id"] == alt_prog
        assert target["name"] == "Data Science"
        assert target["degree_type"] == "master"
        assert target["credits_required"] == 60
        assert target["credits_earned"] == 30
        assert target["credits_remaining"] == 30
        assert target["progress_percent"] == 50.0
        assert len(result["completed_courses"]) == 1
        assert result["completed_courses"][0]["code"] == "WIA101"
        assert _snapshot(conn) == before

    def test_refusal_unknown_program_writes_nothing(self, env):
        conn, cid, prog_id = env
        sid = seed_student_record(conn, cid, prog_id)
        course_id = seed_course(conn, cid)
        section_id = seed_section(conn, course_id, cid)
        seed_enrollment(conn, sid, section_id, cid, status="completed", grade="A")
        before = _snapshot(conn)
        result = call_action(what_if_audit, conn, ns(
            student_id=sid, program_id="no-such-program",
        ))
        assert result["status"] == "error"
        assert "Target program not found" in result["message"]
        assert _snapshot(conn) == before
