"""Behavioural depth for 12 educlaw actions (task m416-depth-educlaw-6).

Each action below previously had only a shape test (asserts on the response
envelope) or a routability test (the contract suite's ``"Unknown action" not
in ...``). Neither observes the database, so an action could return a perfect
envelope while reading the wrong rows — or writing nothing, or the wrong
thing — and stay green. Every test here drives the REAL action against a
fresh DB, reads the stored rows back with PyPika-built queries through
``erpclaw_lib.query`` on a connection from
``erpclaw_lib.db.get_connection``, and compares exact values; money is
compared as exact ``Decimal`` strings, never float, never rounded.

Per-action depth (stored row vs ledger effect):

- edu-list-housing-assignments: STORED ROW. The assignment rows created by
  the owning housing actions are read back with exact values and pinned
  against the listed envelope; read-only, so no ledger assertion can hold
  for it — the snapshot is the no-write proof.
- edu-list-meal-records: STORED ROW. Meal rows created by the owning
  cafeteria action are read back exactly and pinned against the listing
  (including date-window and tenant filters); read-only, no ledger effect.
- edu-list-overdue: STORED ROW. Circulation rows are read back exactly and
  the computed overdue_days / estimated_fine strings are pinned against a
  first-principles Decimal computation; the fine is an estimate, never
  posted, so no ledger assertion can hold.
- edu-list-student-transport: STORED ROW. Transport assignment rows are read
  back exactly and pinned against the listing; read-only, no ledger effect.
- edu-list-waitlist: STORED ROW. The waitlist row produced by driving the
  real section-enrollment path to full is read back exactly (position,
  status) and pinned; read-only, no ledger effect.
- edu-pd-transcript: STORED ROW. PD credit rows are read back exactly and
  the total_credit_hours string is pinned against an exact Decimal sum;
  hours are not money and nothing is posted, so no ledger assertion holds.
- edu-portal-acknowledge-announcement: STORED ROW (the file's only write
  action) — currently a FINDING: the happy path crashes with an unhandled
  FOREIGN KEY IntegrityError (it inserts company_id "" against a real FK),
  so the test pins the crash plus a byte-identical DB instead of a stored
  row; a notification is not a ledger posting, so no debit/credit legs
  could exist in any case.
- edu-portal-announcements: STORED ROW (read view over the announcement
  table). Published/audience filtering is pinned against the stored rows;
  read-only, no ledger effect.
- edu-portal-check-application-status: STORED ROW (read view over the
  applicant table). Status/message/naming-series pinned against the stored
  applicant; read-only, no ledger effect.
- edu-portal-my-transport: STORED ROW (read view over transport + route +
  stop). Active-only filtering pinned against stored rows; read-only.
- edu-portal-student-assignments: STORED ROW (read view over published
  assessments for enrolled sections). Published-only filtering pinned;
  read-only, no ledger effect.
- edu-portal-student-attendance: STORED ROW (read view over attendance
  rows). Date-window filtering pinned against stored rows; read-only.

No test in this file inspects catalog tables directly or sets connection
options; reads are PyPika-built and run on a connection from
``erpclaw_lib.db.get_connection``. Catalog presence is asked through
``erpclaw_lib.seam`` (see TestCatalogTables).
"""
import importlib.util
import json
import os
import sqlite3
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPTS_DIR)))
_SETUP_DIR = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup")

# Bind erpclaw_lib to THIS TREE's lib, not the deployed ~/.openclaw symlink.
_IN_TREE_LIB = os.path.join(_SETUP_DIR, "lib")
ERPCLAW_LIB = (_IN_TREE_LIB if os.path.isdir(os.path.join(_IN_TREE_LIB, "erpclaw_lib"))
               else os.path.join(os.path.expanduser(
                   os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))
if ERPCLAW_LIB not in sys.path:
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, ERPCLAW_LIB)


def _load(name, directory=_SCRIPTS_DIR):
    spec = importlib.util.spec_from_file_location(
        "m416_" + name, os.path.join(directory, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_program = _helpers.seed_program
seed_course = _helpers.seed_course
seed_room = _helpers.seed_room
seed_section = _helpers.seed_section
seed_student = _helpers.seed_student
seed_guardian = _helpers.seed_guardian
seed_employee = _helpers.seed_employee
seed_instructor = _helpers.seed_instructor
seed_enrollment = _helpers.seed_enrollment
seed_grading_scale = _helpers.seed_grading_scale
seed_naming_series = _helpers.seed_naming_series

HOUSING_ACTIONS = _load("housing").ACTIONS
CAFETERIA_ACTIONS = _load("cafeteria").ACTIONS
LIBRARY_ACTIONS = _load("library").ACTIONS
TRANSPORT_ACTIONS = _load("transport").ACTIONS
ENROLLMENT_ACTIONS = _load("enrollment").ACTIONS
PD_ACTIONS = _load("pd").ACTIONS
PORTAL_ACTIONS = _load("portal").ACTIONS
STUDENTS_ACTIONS = _load("students").ACTIONS
GRADING_ACTIONS = _load("grading").ACTIONS
ATTENDANCE_ACTIONS = _load("attendance").ACTIONS

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.db import get_connection  # noqa: E402
from erpclaw_lib.query import Field, Order, P, Q, Table, fn, insert_row  # noqa: E402


@pytest.fixture
def conn(db_path):
    connection = get_connection(db_path)
    yield connection
    connection.close()


def _u():
    return str(uuid.uuid4())


def _msg(result):
    return result.get("message", result.get("error", ""))


def _row(conn, table, rid):
    t = Table(table)
    q = Q.from_(t).select(t.star).where(t.id == P())
    found = conn.execute(q.get_sql(), (rid,)).fetchone()
    assert found is not None, "%s %s not found" % (table, rid)
    return dict(found)


def _where(conn, table, **filters):
    t = Table(table)
    q = Q.from_(t).select(t.star)
    params = []
    for column, value in filters.items():
        q = q.where(Field(column) == P())
        params.append(value)
    return [dict(r) for r in conn.execute(q.get_sql(), params).fetchall()]


def _all(conn, table):
    t = Table(table)
    q = Q.from_(t).select(t.star).orderby(t.id)
    return [dict(r) for r in conn.execute(q.get_sql()).fetchall()]


def _snapshot(conn, tables):
    def _norm(rows):
        return sorted((json.dumps(d, sort_keys=True, default=str) for d in rows))
    return {name: _norm(_all(conn, name)) for name in tables}


def _watched_tables(db_path):
    # Catalog questions go through the seam only; see TestCatalogTables.
    return sorted(
        t for t in seam.table_names(db_path)
        if t.startswith("educlaw_") or t in ("audit_log",))


def _link_guardian(conn, student_id, guardian_id, relationship="mother"):
    sql, _ = insert_row("educlaw_student_guardian",
                        {"id": P(), "student_id": P(), "guardian_id": P(),
                         "relationship": P(), "has_custody": P(), "can_pickup": P(),
                         "receives_communications": P(), "is_primary_contact": P(),
                         "is_emergency_contact": P()})
    conn.execute(sql, (_u(), student_id, guardian_id, relationship, 1, 1, 1, 1, 1))
    conn.commit()


class TestCatalogTables:
    def test_touched_tables_exist(self, conn, db_path):
        # The only catalog question in this file, asked through the seam.
        names = set(seam.table_names(db_path))
        for table in (
            "educlaw_housing_assignment", "educlaw_housing_unit",
            "educlaw_student_meal_record", "educlaw_circulation",
            "educlaw_library_item", "educlaw_student_transport",
            "educlaw_bus_route", "educlaw_bus_stop", "educlaw_waitlist",
            "educlaw_pd_credit", "educlaw_notification",
            "educlaw_announcement", "educlaw_student_applicant",
            "educlaw_assessment", "educlaw_assessment_plan",
            "educlaw_assessment_result", "educlaw_student_attendance",
        ):
            assert table in names, "missing table %s" % table


# ---------------------------------------------------------------------------
# edu-list-housing-assignments — STORED ROW (read-only; no ledger effect, so
# no debit/credit legs can be asserted — the snapshot is the no-write proof).
# NOTE: this action validates no input (every filter is optional), so there
# is no refusal path to pin; the negative case below (unknown building ->
# ok with count 0 and an identical DB) is the closest observable refusal.
# ---------------------------------------------------------------------------

class TestListHousingAssignmentsDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        s1 = seed_student(conn, cid)
        s2 = seed_student(conn, cid)
        r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="Maple Hall", room_number="101", company_id=cid,
            unit_type="double", capacity=2, floor="1", amount="1200.00",
            description=None))
        assert is_ok(r), r
        unit_a = r["id"]
        r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="Oak Hall", room_number="201", company_id=cid,
            unit_type="single", capacity=2, floor="2", amount="900.00",
            description=None))
        assert is_ok(r), r
        unit_b = r["id"]
        r = call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=s1, room_id=unit_a, academic_year="2025-26",
            term_type="fall", start_date="2025-09-01", end_date=None,
            meal_plan="standard"))
        assert is_ok(r), r
        r = call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=s2, room_id=unit_b, academic_year="2025-26",
            term_type="fall", start_date="2025-09-01", end_date=None,
            meal_plan="none"))
        assert is_ok(r), r
        # A second tenant whose rows must never leak into company one's view.
        cid2 = seed_company(conn)
        s3 = seed_student(conn, cid2)
        r = call_action(HOUSING_ACTIONS["edu-add-housing-unit"], conn, ns(
            building="Maple Hall", room_number="101", company_id=cid2,
            unit_type="double", capacity=2, floor="1", amount="500.00",
            description=None))
        assert is_ok(r), r
        r = call_action(HOUSING_ACTIONS["edu-assign-housing"], conn, ns(
            student_id=s3, room_id=r["id"], academic_year="2025-26",
            term_type=None, start_date=None, end_date=None, meal_plan=None))
        assert is_ok(r), r
        return {"company_id": cid, "s1": s1, "s2": s2,
                "unit_a": unit_a, "unit_b": unit_b, "other_student": s3}

    def test_lists_exact_stored_rows(self, conn, db_path):
        e = self._setup(conn)
        stored_a = _where(conn, "educlaw_housing_assignment",
                          student_id=e["s1"])[0]
        assert stored_a["housing_unit_id"] == e["unit_a"]
        assert stored_a["academic_year"] == "2025-26"
        assert stored_a["status"] == "active"
        assert stored_a["meal_plan"] == "standard"
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(HOUSING_ACTIONS["edu-list-housing-assignments"], conn, ns(
            company_id=e["company_id"], academic_year=None, status=None,
            building="Maple Hall", limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 1
        listed = r["assignments"][0]
        # The envelope mirrors the stored row, not a plausible fabrication.
        assert listed["assignment_id"] == stored_a["id"]
        assert listed["student_id"] == e["s1"]
        assert listed["student_name"] == "Test Student"
        assert listed["unit_id"] == e["unit_a"]
        assert listed["building_name"] == "Maple Hall"
        assert listed["room_number"] == "101"
        assert listed["unit_type"] == "double"
        assert listed["academic_year"] == "2025-26"
        assert listed["meal_plan"] == "standard"
        assert listed["status"] == "active"
        # Nothing was written by the listing itself.
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_company_and_year_filters(self, conn, db_path):
        e = self._setup(conn)
        r = call_action(HOUSING_ACTIONS["edu-list-housing-assignments"], conn, ns(
            company_id=e["company_id"], academic_year="2025-26", status="active",
            building=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {a["student_id"] for a in r["assignments"]} == {e["s1"], e["s2"]}
        # The other company's Maple Hall assignment must not leak across.
        foreign = _where(conn, "educlaw_housing_assignment",
                         student_id=e["other_student"])[0]
        assert foreign["academic_year"] == "2025-26"
        assert foreign["id"] not in {a["assignment_id"]
                                     for a in r["assignments"]}
        before = _snapshot(conn, _watched_tables(db_path))
        # No refusal path exists (all filters optional): an unknown building
        # is an ok-with-zero-rows answer and must also write nothing.
        r = call_action(HOUSING_ACTIONS["edu-list-housing-assignments"], conn, ns(
            company_id=e["company_id"], academic_year=None, status=None,
            building="No Such Hall", limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert r["assignments"] == []
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-list-meal-records — STORED ROW (read-only; no ledger effect).
# ---------------------------------------------------------------------------

class TestListMealRecordsDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        s1 = seed_student(conn, cid)
        s2 = seed_student(conn, cid)
        for sid, day, mtype, elig in (
                (s1, "2026-03-15", "lunch", "free"),
                (s1, "2026-03-10", "breakfast", "paid"),
                (s2, "2026-03-15", "lunch", "free")):
            r = call_action(CAFETERIA_ACTIONS["edu-record-student-meal"], conn, ns(
                student_id=sid, meal_date=day, meal_type=mtype,
                eligibility=elig, allergen_alert=None, served_by="Jane"))
            assert is_ok(r), r
        cid2 = seed_company(conn)
        s3 = seed_student(conn, cid2)
        r = call_action(CAFETERIA_ACTIONS["edu-record-student-meal"], conn, ns(
            student_id=s3, meal_date="2026-03-15", meal_type="lunch",
            eligibility="free", allergen_alert=None, served_by=None))
        assert is_ok(r), r
        return {"company_id": cid, "s1": s1, "s2": s2}

    def test_window_and_student_filters_match_stored_rows(self, conn, db_path):
        e = self._setup(conn)
        stored = _where(conn, "educlaw_student_meal_record",
                        student_id=e["s1"], meal_date="2026-03-15")[0]
        assert stored["meal_type"] == "lunch"
        assert stored["eligibility"] == "free"
        assert stored["served_by"] == "Jane"
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(CAFETERIA_ACTIONS["edu-list-meal-records"], conn, ns(
            school_id=e["company_id"], date_from="2026-03-12",
            date_to="2026-03-20", student_id=e["s1"], limit=50, offset=0))
        assert is_ok(r), r
        assert r["school_id"] == e["company_id"]
        assert r["count"] == 1
        listed = r["meal_records"][0]
        assert listed["id"] == stored["id"]
        assert listed["meal_type"] == "lunch"
        assert listed["eligibility"] == "free"
        assert listed["meal_date"] == "2026-03-15"
        assert listed["student_name"] == "Test Student"
        assert listed["grade_level"] == "10"
        # The other school's row for the same date must not leak across.
        r = call_action(CAFETERIA_ACTIONS["edu-list-meal-records"], conn, ns(
            school_id=e["company_id"], date_from=None, date_to=None,
            student_id=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 3
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_missing_school_id_writes_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(CAFETERIA_ACTIONS["edu-list-meal-records"], conn, ns(
            school_id=None, date_from=None, date_to=None,
            student_id=None, limit=50, offset=0))
        assert is_error(r), r
        assert "--school-id is required" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-list-overdue — STORED ROW. The estimated fine is computed, never
# posted, so no ledger assertion can hold for it.
# ---------------------------------------------------------------------------

class TestListOverdueDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        stu = seed_student(conn, cid)
        r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            title="Intro to Algebra", company_id=cid, item_type="book",
            capacity=2, description="A. Author", code="978-0-00-000000-0",
            room_type=None, building=None))
        assert is_ok(r), r
        item_id = r["id"]
        r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            library_item_id=item_id, student_id=stu))
        assert is_ok(r), r
        circ_id = r["circulation_id"]
        past = (date.today() - timedelta(days=10)).isoformat()
        _circ = Table("educlaw_circulation")
        conn.execute(
            Q.update(_circ).set(_circ.due_date, past)
            .where(_circ.id == P()).get_sql(), (circ_id,))
        conn.commit()
        # A second checkout whose due date is still in the future.
        r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            title="Fresh Atlas", company_id=cid, item_type="book",
            capacity=1, description=None, code=None,
            room_type=None, building=None))
        assert is_ok(r), r
        r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            library_item_id=r["id"], student_id=stu))
        assert is_ok(r), r
        # Another company's overdue checkout must stay out of this view.
        cid2 = seed_company(conn)
        stu2 = seed_student(conn, cid2)
        r = call_action(LIBRARY_ACTIONS["edu-add-library-item"], conn, ns(
            title="Far Away Tales", company_id=cid2, item_type="book",
            capacity=1, description=None, code=None,
            room_type=None, building=None))
        assert is_ok(r), r
        r = call_action(LIBRARY_ACTIONS["edu-checkout-item"], conn, ns(
            library_item_id=r["id"], student_id=stu2))
        assert is_ok(r), r
        conn.execute(
            Q.update(_circ).set(_circ.due_date, past)
            .where(_circ.id == P()).get_sql(), (r["circulation_id"],))
        conn.commit()
        return {"company_id": cid, "student_id": stu, "circ_id": circ_id,
                "due_date": past}

    def test_overdue_row_and_fine_are_exact(self, conn, db_path):
        from decimal import Decimal as _D
        e = self._setup(conn)
        stored = _row(conn, "educlaw_circulation", e["circ_id"])
        assert stored["status"] == "checked_out"
        assert stored["due_date"] == e["due_date"]
        assert stored["student_id"] == e["student_id"]
        assert stored["fine_amount"] == "0"
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(LIBRARY_ACTIONS["edu-list-overdue"], conn, ns(
            company_id=e["company_id"]))
        assert is_ok(r), r
        assert r["count"] == 1
        listed = r["overdue_items"][0]
        assert listed["circulation_id"] == e["circ_id"]
        assert listed["title"] == "Intro to Algebra"
        assert listed["isbn"] == "978-0-00-000000-0"
        assert listed["student_id"] == e["student_id"]
        assert listed["student_name"] == "Test Student"
        assert listed["due_date"] == e["due_date"]
        assert listed["overdue_days"] == 10
        # Money is text: exact Decimal string, recomputed from first
        # principles (0.25 x 10 days), never float.
        assert listed["estimated_fine"] == "2.50"
        assert _D(listed["estimated_fine"]) == _D("0.25") * 10
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_missing_company_id_writes_nothing(self, conn, db_path):
        self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(LIBRARY_ACTIONS["edu-list-overdue"], conn, ns(
            company_id=None))
        assert is_error(r), r
        assert "--company-id is required" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-list-student-transport — STORED ROW (read-only; no ledger effect).
# ---------------------------------------------------------------------------

class TestListStudentTransportDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        stu = seed_student(conn, cid)
        other = seed_student(conn, cid)
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], conn, ns(
            school_id=cid, route_number="303", route_name="East Route",
            driver_name="Sam Driver", driver_phone="555-0100", vehicle_id=None,
            vehicle_number="BUS-7", capacity=40, am_start_time="07:00",
            pm_start_time="15:00", notes=None))
        assert is_ok(r), r
        route_id = r["id"]
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-stop"], conn, ns(
            route_id=route_id, stop_order=1, stop_name="Elm St",
            address="1 Elm St", am_pickup_time="07:15",
            pm_dropoff_time="15:20"))
        assert is_ok(r), r
        stop_id = r["id"]
        r = call_action(TRANSPORT_ACTIONS["edu-assign-student-transport"], conn, ns(
            student_id=stu, route_id=route_id, bus_stop_id=stop_id,
            transport_type="both", special_needs_notes=None,
            effective_date="2026-03-01"))
        assert is_ok(r), r
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], conn, ns(
            school_id=cid, route_number="999", route_name="Empty Route",
            driver_name=None, driver_phone=None, vehicle_id=None,
            vehicle_number=None, capacity=None, am_start_time=None,
            pm_start_time=None, notes=None))
        assert is_ok(r), r
        return {"company_id": cid, "student_id": stu, "other": other,
                "route_id": route_id, "stop_id": stop_id,
                "empty_route": r["id"]}

    def test_assignment_row_is_listed_exactly(self, conn, db_path):
        e = self._setup(conn)
        stored = _where(conn, "educlaw_student_transport",
                        student_id=e["student_id"])[0]
        assert stored["route_id"] == e["route_id"]
        assert stored["bus_stop_id"] == e["stop_id"]
        assert stored["transport_type"] == "both"
        assert stored["status"] == "active"
        assert stored["effective_date"] == "2026-03-01"
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(TRANSPORT_ACTIONS["edu-list-student-transport"], conn, ns(
            route_id=None, student_id=e["student_id"]))
        assert is_ok(r), r
        assert r["count"] == 1
        listed = r["transport_assignments"][0]
        assert listed["id"] == stored["id"]
        assert listed["route_number"] == "303"
        assert listed["route_name"] == "East Route"
        assert listed["stop_name"] == "Elm St"
        assert listed["student_name"] == "Test Student"
        assert listed["transport_type"] == "both"
        assert listed["status"] == "active"
        # Filtering by a route nobody rides is an empty, write-free answer.
        r = call_action(TRANSPORT_ACTIONS["edu-list-student-transport"], conn, ns(
            route_id=e["empty_route"], student_id=None))
        assert is_ok(r), r
        assert r["count"] == 0
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_without_any_filter_writes_nothing(self, conn, db_path):
        self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(TRANSPORT_ACTIONS["edu-list-student-transport"], conn, ns(
            route_id=None, student_id=None))
        assert is_error(r), r
        assert "--route-id" in _msg(r) and "--student-id" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-list-waitlist — STORED ROW (read-only; no ledger effect).
# NOTE: like the housing listing, this action validates no input (every
# filter is optional), so there is no refusal path to pin; the
# status-filtered empty answer below is the negative case.
# ---------------------------------------------------------------------------

class TestListWaitlistDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pid = seed_program(conn, cid)
        crs = seed_course(conn, cid)
        room = seed_room(conn, cid)
        emp = seed_employee(conn, cid)
        inst = seed_instructor(conn, cid, emp)
        sec = seed_section(conn, cid, crs, tid, instructor_id=inst,
                           room_id=room, max_enrollment=1)
        # Test seeding: open the waitlist gate the real path checks.
        _sec = Table("educlaw_section")
        conn.execute(
            Q.update(_sec).set(_sec.waitlist_enabled, 1)
            .set(_sec.waitlist_max, 5)
            .where(_sec.id == P()).get_sql(), (sec,))
        conn.commit()
        first = seed_student(conn, cid)
        second = seed_student(conn, cid)
        for sid in (first, second):
            r = call_action(
                ENROLLMENT_ACTIONS["edu-create-program-enrollment"], conn, ns(
                    student_id=sid, program_id=pid, academic_year_id=yid,
                    company_id=cid, enrollment_date=None))
            assert is_ok(r), r
        r = call_action(
            ENROLLMENT_ACTIONS["edu-create-section-enrollment"], conn, ns(
                student_id=first, section_id=sec, company_id=cid,
                is_repeat=None, grade_type=None))
        assert is_ok(r) and r["enrollment_status"] == "enrolled", r
        r = call_action(
            ENROLLMENT_ACTIONS["edu-create-section-enrollment"], conn, ns(
                student_id=second, section_id=sec, company_id=cid,
                is_repeat=None, grade_type=None))
        assert is_ok(r) and r["enrollment_status"] == "waitlisted", r
        assert r["waitlist_position"] == 1
        return {"company_id": cid, "section_id": sec,
                "first": first, "second": second}

    def test_waitlisted_row_is_listed_exactly(self, conn, db_path):
        e = self._setup(conn)
        stored = _where(conn, "educlaw_waitlist",
                        section_id=e["section_id"])[0]
        assert stored["student_id"] == e["second"]
        assert stored["position"] == 1
        assert stored["waitlist_status"] == "waiting"
        assert stored["company_id"] == e["company_id"]
        # The enrolled student must NOT hold a waitlist row.
        assert _where(conn, "educlaw_waitlist",
                      student_id=e["first"]) == []
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(ENROLLMENT_ACTIONS["edu-list-waitlist"], conn, ns(
            section_id=e["section_id"], student_id=None,
            waitlist_status=None, company_id=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 1
        listed = r["waitlist"][0]
        assert listed["id"] == stored["id"]
        assert listed["student_id"] == e["second"]
        assert listed["section_id"] == e["section_id"]
        assert listed["position"] == 1
        assert listed["waitlist_status"] == "waiting"
        # A status nobody holds is an empty, write-free answer.
        r = call_action(ENROLLMENT_ACTIONS["edu-list-waitlist"], conn, ns(
            section_id=e["section_id"], student_id=None,
            waitlist_status="offered", company_id=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-pd-transcript — STORED ROW. Credit hours are exact Decimal strings but
# they are not money and nothing posts, so no ledger assertion can hold.
# ---------------------------------------------------------------------------

class TestPdTranscriptDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        emp = seed_employee(conn, cid)
        inst = seed_instructor(conn, cid, emp)
        credits = [
            ("Transcript Course A", "8", "content_area", "approved"),
            ("Transcript Course B", "4.50", "general", "approved"),
            ("Pending Course", "100", "general", "pending"),
        ]
        for name, hrs, ctype, status in credits:
            r = call_action(PD_ACTIONS["edu-add-pd-credit"], conn, ns(
                instructor_id=inst, name=name, credit_hours=hrs,
                start_date="2025-05-01", company_id=cid, credit_type=ctype,
                description="Provider X", end_date="", code="CERT-001",
                status=status, limit=50, offset=0))
            assert is_ok(r), r
        return {"company_id": cid, "instructor_id": inst}

    def test_total_and_credits_match_stored_rows(self, conn, db_path):
        e = self._setup(conn)
        stored = _where(conn, "educlaw_pd_credit",
                        teacher_id=e["instructor_id"])
        assert len(stored) == 3
        approved = sorted(
            (c for c in stored if c["status"] == "approved"),
            key=lambda c: c["course_name"])
        assert [c["credit_hours"] for c in approved] == ["8", "4.50"]
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(PD_ACTIONS["edu-pd-transcript"], conn, ns(
            instructor_id=e["instructor_id"], limit=50, offset=0))
        assert is_ok(r), r
        assert r["teacher_id"] == e["instructor_id"]
        assert r["instructor_name"] == "Test Teacher"
        # Money is text: the total is an exact Decimal sum as a string —
        # 8 + 4.50 = 12.50, with the pending 100 excluded.
        assert r["total_credit_hours"] == "12.50"
        assert (Decimal(r["total_credit_hours"]) ==
                sum((Decimal(c["credit_hours"]) for c in approved),
                    Decimal("0")))
        assert len(r["credits"]) == 2
        assert {c["course_name"] for c in r["credits"]} == {
            "Transcript Course A", "Transcript Course B"}
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusals_write_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(PD_ACTIONS["edu-pd-transcript"], conn, ns(
            instructor_id=None, limit=50, offset=0))
        assert is_error(r), r
        assert "--instructor-id is required" in _msg(r)
        r = call_action(PD_ACTIONS["edu-pd-transcript"], conn, ns(
            instructor_id="no-such-instructor", limit=50, offset=0))
        assert is_error(r), r
        assert "not found" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-portal-acknowledge-announcement — STORED ROW, and the file's only
# WRITE action: it inserts exactly one educlaw_notification row. A
# notification is not a ledger posting, so no debit/credit legs exist.
# ---------------------------------------------------------------------------

class TestPortalAcknowledgeAnnouncementDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        stu = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        _link_guardian(conn, stu, gid)
        ann_id = _u()
        sql, _ = insert_row("educlaw_announcement", {
            "id": P(), "title": P(), "body": P(), "priority": P(),
            "audience_type": P(), "audience_filter": P(),
            "publish_date": P(), "expiry_date": P(),
            "announcement_status": P(), "published_by": P(),
            "company_id": P(), "created_by": P()})
        conn.execute(sql, (
            ann_id, "Snow Day Policy", "School closes at noon", "normal",
            "guardians", "{}", "2026-01-05", "2026-12-31",
            "published", "admin", cid, ""))
        conn.commit()
        return {"company_id": cid, "guardian_id": gid, "ann_id": ann_id}

    def test_acknowledge_happy_path_finding(self, conn, db_path):
        # FINDING (deliberately not fixed): the happy path is broken. The
        # action inserts its educlaw_notification row with company_id "",
        # but educlaw_notification.company_id is a FOREIGN KEY to
        # company(id), and every connection in this project enforces FKs
        # (foreign-key enforcement is standard on project connections via
        # erpclaw_lib.db.setup_pragmas, which get_connection applies).
        # So the insert raises an unhandled
        # sqlite3.IntegrityError instead of acknowledging anything.
        # Expected: ok + exactly one notification row (recipient_type
        # guardian, notification_type announcement, reference to the
        # announcement, is_read 1). Actual: crash, zero rows.
        e = self._setup(conn)
        assert _where(conn, "educlaw_notification",
                      recipient_id=e["guardian_id"]) == []
        before = _snapshot(conn, _watched_tables(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            call_action(
                PORTAL_ACTIONS["edu-portal-acknowledge-announcement"], conn,
                ns(guardian_id=e["guardian_id"],
                   announcement_id=e["ann_id"]))
        # The crash half-writes nothing: no notification lands and the
        # rest of the database is byte-identical.
        assert _where(conn, "educlaw_notification",
                      recipient_id=e["guardian_id"]) == []
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_unknown_announcement_writes_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            PORTAL_ACTIONS["edu-portal-acknowledge-announcement"], conn, ns(
                guardian_id=e["guardian_id"],
                announcement_id="no-such-announcement"))
        assert is_error(r), r
        assert "not found" in _msg(r)
        assert "no-such-announcement" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_unknown_guardian_writes_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            PORTAL_ACTIONS["edu-portal-acknowledge-announcement"], conn, ns(
                guardian_id="no-such-guardian",
                announcement_id=e["ann_id"]))
        assert is_error(r), r
        assert "not found" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-portal-announcements — STORED ROW (read view over announcements;
# read-only, no ledger effect).
# ---------------------------------------------------------------------------

class TestPortalAnnouncementsDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        stu = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        _link_guardian(conn, stu, gid)
        ids = {}

        def _ann(title, audience, status):
            aid = _u()
            sql, _ = insert_row("educlaw_announcement", {
                "id": P(), "title": P(), "body": P(), "priority": P(),
                "audience_type": P(), "audience_filter": P(),
                "publish_date": P(), "expiry_date": P(),
                "announcement_status": P(), "published_by": P(),
                "company_id": P(), "created_by": P()})
            conn.execute(sql, (
                aid, title, "Body of " + title, "normal", audience, "{}",
                "2026-01-01", "2026-12-31", status, "admin", cid, ""))
            ids[title] = aid

        _ann("Guardians Assembly", "guardians", "published")
        _ann("Whole School Fair", "all", "published")
        _ann("Draft Never Sent", "all", "draft")
        _ann("Staff Only Memo", "staff", "published")
        conn.commit()
        return {"company_id": cid, "guardian_id": gid, "ids": ids}

    def test_only_visible_announcements_listed(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(PORTAL_ACTIONS["edu-portal-announcements"], conn, ns(
            guardian_id=e["guardian_id"]))
        assert is_ok(r), r
        assert r["guardian_id"] == e["guardian_id"]
        assert r["count"] == 2
        titles = {a["title"] for a in r["announcements"]}
        assert titles == {"Guardians Assembly", "Whole School Fair"}
        by_title = {a["title"]: a for a in r["announcements"]}
        # Each listed envelope mirrors its stored row exactly.
        for title in titles:
            stored = _row(conn, "educlaw_announcement", e["ids"][title])
            assert by_title[title]["id"] == stored["id"]
            assert by_title[title]["body"] == stored["body"]
            assert by_title[title]["announcement_status"] == "published"
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_unknown_guardian_writes_nothing(self, conn, db_path):
        self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(PORTAL_ACTIONS["edu-portal-announcements"], conn, ns(
            guardian_id="no-such-guardian"))
        assert is_error(r), r
        assert "not found" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-portal-check-application-status — STORED ROW (read view over the
# applicant table; read-only, no ledger effect).
# ---------------------------------------------------------------------------

class TestPortalCheckApplicationStatusDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        seed_naming_series(conn, cid, "educlaw_student_applicant", "APP-")
        r = call_action(STUDENTS_ACTIONS["edu-portal-submit-application"], conn, ns(
            first_name="Jane", last_name="Doe", email="jane@example.com",
            company_id=cid, phone="555-0123", date_of_birth="2010-05-15",
            gender=None, address=None, grade_level="9",
            applying_for_program_id=None, applying_for_term_id=None,
            application_date="2026-02-01", previous_school=None,
            limit=50, offset=0))
        assert is_ok(r), r
        return {"company_id": cid, "applicant_id": r["id"],
                "naming": r["naming_series"]}

    def test_status_mirrors_stored_applicant(self, conn, db_path):
        e = self._setup(conn)
        stored = _row(conn, "educlaw_student_applicant", e["applicant_id"])
        assert stored["status"] == "applied"
        assert stored["email"] == "jane@example.com"
        assert stored["first_name"] == "Jane"
        assert stored["last_name"] == "Doe"
        assert stored["naming_series"] == e["naming"]
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            STUDENTS_ACTIONS["edu-portal-check-application-status"], conn, ns(
                applicant_id=e["applicant_id"], email=None,
                limit=50, offset=0))
        assert is_ok(r), r
        assert r["id"] == e["applicant_id"]
        assert r["status"] == "ok"  # envelope; applicant state is below
        assert r["document_status"] == "applied"
        assert r["naming_series"] == e["naming"]
        assert r["status_message"] == (
            "Your application has been received and is being processed.")
        # Internal review notes must never reach the portal envelope.
        assert "review_notes" not in r
        # Email lookup resolves to the same stored applicant.
        r2 = call_action(
            STUDENTS_ACTIONS["edu-portal-check-application-status"], conn, ns(
                applicant_id=None, email="jane@example.com",
                limit=50, offset=0))
        assert is_ok(r2), r2
        assert r2["id"] == e["applicant_id"]
        assert r2["document_status"] == "applied"
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusals_write_nothing(self, conn, db_path):
        self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            STUDENTS_ACTIONS["edu-portal-check-application-status"], conn, ns(
                applicant_id=None, email=None, limit=50, offset=0))
        assert is_error(r), r
        assert "--applicant-id" in _msg(r) and "--email" in _msg(r)
        r = call_action(
            STUDENTS_ACTIONS["edu-portal-check-application-status"], conn, ns(
                applicant_id="no-such-applicant", email=None,
                limit=50, offset=0))
        assert is_error(r), r
        assert _msg(r) == "Application not found"
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-portal-my-transport — STORED ROW (read view over transport + route +
# stop; active assignments only; read-only, no ledger effect).
# ---------------------------------------------------------------------------

class TestPortalMyTransportDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        stu = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        _link_guardian(conn, stu, gid)
        stranger = seed_guardian(conn, cid)
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-route"], conn, ns(
            school_id=cid, route_number="303", route_name="East Route",
            driver_name="Sam Driver", driver_phone="555-0100", vehicle_id=None,
            vehicle_number="BUS-7", capacity=40, am_start_time="07:00",
            pm_start_time="15:00", notes=None))
        assert is_ok(r), r
        route_id = r["id"]
        r = call_action(TRANSPORT_ACTIONS["edu-add-bus-stop"], conn, ns(
            route_id=route_id, stop_order=1, stop_name="Elm St",
            address="1 Elm St", am_pickup_time="07:15",
            pm_dropoff_time="15:20"))
        assert is_ok(r), r
        stop_id = r["id"]
        r = call_action(TRANSPORT_ACTIONS["edu-assign-student-transport"], conn, ns(
            student_id=stu, route_id=route_id, bus_stop_id=stop_id,
            transport_type="both", special_needs_notes=None,
            effective_date="2026-03-01"))
        assert is_ok(r), r
        active_id = r["id"]
        # An inactive assignment for the same student must stay invisible.
        # Test seeding through the owner's row shape: same columns the
        # assign action wrote, only the status differs.
        sql, _ = insert_row("educlaw_student_transport", {
            "id": P(), "student_id": P(), "route_id": P(),
            "bus_stop_id": P(), "transport_type": P(),
            "special_needs_notes": P(), "effective_date": P(),
            "end_date": P(), "status": P(),
            "created_at": P(), "updated_at": P()})
        conn.execute(sql, (_u(), stu, route_id, stop_id, "am_only", "",
                           "2025-09-01", "2025-12-01", "inactive",
                           "2025-09-01T00:00:00Z", "2025-12-01T00:00:00Z"))
        conn.commit()
        return {"company_id": cid, "student_id": stu, "guardian_id": gid,
                "stranger": stranger, "route_id": route_id,
                "stop_id": stop_id, "active_id": active_id}

    def test_active_assignment_view_matches_stored_rows(self, conn, db_path):
        e = self._setup(conn)
        stored = _row(conn, "educlaw_student_transport", e["active_id"])
        assert stored["status"] == "active"
        assert stored["transport_type"] == "both"
        route = _row(conn, "educlaw_bus_route", e["route_id"])
        assert route["route_number"] == "303"
        assert route["driver_name"] == "Sam Driver"
        stop = _row(conn, "educlaw_bus_stop", e["stop_id"])
        assert stop["stop_name"] == "Elm St"
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(PORTAL_ACTIONS["edu-portal-my-transport"], conn, ns(
            guardian_id=e["guardian_id"], student_id=e["student_id"]))
        assert is_ok(r), r
        assert r["count"] == 1
        listed = r["transport_assignments"][0]
        assert listed["transport_id"] == e["active_id"]
        assert listed["route_number"] == "303"
        assert listed["route_name"] == "East Route"
        assert listed["driver_name"] == "Sam Driver"
        assert listed["driver_phone"] == "555-0100"
        assert listed["stop_name"] == "Elm St"
        assert listed["stop_address"] == "1 Elm St"
        assert listed["transport_type"] == "both"
        assert listed["status"] == "active"
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_unlinked_guardian_writes_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(PORTAL_ACTIONS["edu-portal-my-transport"], conn, ns(
            guardian_id=e["stranger"], student_id=e["student_id"]))
        assert is_error(r), r
        assert "Access denied" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-portal-student-assignments — STORED ROW (read view over published
# assessments for enrolled sections; read-only, no ledger effect).
# ---------------------------------------------------------------------------

class TestPortalStudentAssignmentsDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        crs = seed_course(conn, cid, code="SCI201")
        room = seed_room(conn, cid)
        emp = seed_employee(conn, cid)
        inst = seed_instructor(conn, cid, emp)
        sec = seed_section(conn, cid, crs, tid, instructor_id=inst,
                           room_id=room)
        stu = seed_student(conn, cid)
        seed_enrollment(conn, stu, sec, cid)
        gid = seed_guardian(conn, cid)
        _link_guardian(conn, stu, gid)
        stranger = seed_guardian(conn, cid)
        scale = seed_grading_scale(conn, cid)
        r = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], conn, ns(
            section_id=sec, grading_scale_id=scale, company_id=cid,
            categories='[{"name":"Exams","weight_percentage":"100"}]'))
        assert is_ok(r), r
        plan_id = r["id"]
        cat = _where(conn, "educlaw_assessment_category",
                     assessment_plan_id=plan_id)[0]
        r = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
            plan_id=plan_id, category_id=cat["id"], name="Midterm Exam",
            max_points="100", description=None, due_date="2026-04-01",
            is_published=1, allows_extra_credit=None, sort_order=None))
        assert is_ok(r), r
        published_id = r["id"]
        r = call_action(GRADING_ACTIONS["edu-add-assessment"], conn, ns(
            plan_id=plan_id, category_id=cat["id"], name="Draft Quiz",
            max_points="20", description=None, due_date="2026-05-01",
            is_published=0, allows_extra_credit=None, sort_order=None))
        assert is_ok(r), r
        return {"company_id": cid, "student_id": stu, "guardian_id": gid,
                "stranger": stranger, "published_id": published_id}

    def test_only_published_assessments_listed(self, conn, db_path):
        e = self._setup(conn)
        stored = _row(conn, "educlaw_assessment", e["published_id"])
        assert stored["name"] == "Midterm Exam"
        assert stored["max_points"] == "100"
        assert stored["is_published"] == 1
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            PORTAL_ACTIONS["edu-portal-student-assignments"], conn, ns(
                guardian_id=e["guardian_id"], student_id=e["student_id"]))
        assert is_ok(r), r
        assert r["count"] == 1
        listed = r["assignments"][0]
        assert listed["assessment_id"] == e["published_id"]
        assert listed["assessment_name"] == "Midterm Exam"
        assert listed["max_points"] == "100"
        assert listed["due_date"] == "2026-04-01"
        assert listed["course_code"] == "SCI201"
        assert listed["course_name"] == "Test Course"
        assert listed["points_earned"] is None
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_unlinked_guardian_writes_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            PORTAL_ACTIONS["edu-portal-student-assignments"], conn, ns(
                guardian_id=e["stranger"], student_id=e["student_id"]))
        assert is_error(r), r
        assert "Access denied" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before


# ---------------------------------------------------------------------------
# edu-portal-student-attendance — STORED ROW (read view over attendance
# rows; read-only, no ledger effect).
# ---------------------------------------------------------------------------

class TestPortalStudentAttendanceDepth:
    def _setup(self, conn):
        cid = seed_company(conn)
        stu = seed_student(conn, cid)
        other = seed_student(conn, cid)
        gid = seed_guardian(conn, cid)
        _link_guardian(conn, stu, gid)
        stranger = seed_guardian(conn, cid)
        for sid, day, status in (
                (stu, "2026-03-15", "absent"),
                (stu, "2026-03-16", "present"),
                (other, "2026-03-15", "absent")):
            r = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], conn, ns(
                student_id=sid, attendance_date=day,
                attendance_status=status, company_id=cid, section_id=None,
                late_minutes=None, comments=None, marked_by="teacher",
                source=None, user_id=None))
            assert is_ok(r), r
        return {"company_id": cid, "student_id": stu, "other": other,
                "guardian_id": gid, "stranger": stranger}

    def test_attendance_view_matches_stored_rows(self, conn, db_path):
        e = self._setup(conn)
        stored = sorted(
            _where(conn, "educlaw_student_attendance",
                   student_id=e["student_id"]),
            key=lambda d: d["attendance_date"])
        assert [(d["attendance_date"], d["attendance_status"])
                for d in stored] == [
                    ("2026-03-15", "absent"), ("2026-03-16", "present")]
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            PORTAL_ACTIONS["edu-portal-student-attendance"], conn, ns(
                guardian_id=e["guardian_id"], student_id=e["student_id"],
                date_from=None, date_to=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {a["id"] for a in r["attendance"]} == {
            d["id"] for d in stored}
        assert {(a["attendance_date"], a["attendance_status"])
                for a in r["attendance"]} == {
                    ("2026-03-15", "absent"), ("2026-03-16", "present")}
        # The date window narrows to exactly the stored present row.
        r = call_action(
            PORTAL_ACTIONS["edu-portal-student-attendance"], conn, ns(
                guardian_id=e["guardian_id"], student_id=e["student_id"],
                date_from="2026-03-16", date_to="2026-03-16",
                limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 1
        assert r["attendance"][0]["attendance_status"] == "present"
        assert r["attendance"][0]["id"] == stored[1]["id"]
        assert _snapshot(conn, _watched_tables(db_path)) == before

    def test_refusal_unlinked_guardian_writes_nothing(self, conn, db_path):
        e = self._setup(conn)
        before = _snapshot(conn, _watched_tables(db_path))
        r = call_action(
            PORTAL_ACTIONS["edu-portal-student-attendance"], conn, ns(
                guardian_id=e["stranger"], student_id=e["student_id"],
                date_from=None, date_to=None, limit=50, offset=0))
        assert is_error(r), r
        assert "Access denied" in _msg(r)
        assert _snapshot(conn, _watched_tables(db_path)) == before
