"""Behavioural depth tests for 12 read-only educlaw-scheduling actions.

Each action covered here already had a test in test_scheduling.py, but those
tests assert only the response envelope (``status == "ok"``). A routed action
returning a well-shaped but content-free response passed them. These tests
assert what each action actually observes in the database:

- setup writes rows through the owning module's own actions,
- the action's response is compared field-by-field against those stored rows,
  read back through ``erpclaw_lib.db.get_connection()`` with queries built by
  PyPika through ``erpclaw_lib.query``,
- a snapshot of every reachable table before the call is byte-identical
  afterwards, proving a read action writes nothing,
- one refusal case per action that validates input proves the refusal happens,
  the message names the real problem, and the database is byte-identical
  afterwards.

Ledger note (stated once here, not twelve times): none of these 12 actions
reaches the ledger. They perform SELECTs only and emit no postings, so no
balanced-legs assertion can hold for any of them.

Money note: this module holds no monetary values, so there is nothing to
assert with ``Decimal``. Every exact-value comparison below is on TEXT or
INTEGER identifiers, names and codes, compared exactly, never approximate.
"""
import importlib.util
import json
import os
import sys
import uuid

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_ROOT_DIR = os.path.dirname(_SCRIPTS_DIR)
_PARENT_DIR = os.path.dirname(_ROOT_DIR)
_SRC_DIR = os.path.dirname(_PARENT_DIR)

_IN_TREE_LIB = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if os.path.isdir(os.path.join(_IN_TREE_LIB, "erpclaw_lib")) and _IN_TREE_LIB not in sys.path:
    sys.path.insert(0, _IN_TREE_LIB)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, f"{name}.py"))
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
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_instructor = _helpers.seed_instructor
seed_course = _helpers.seed_course
seed_section = _helpers.seed_section

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.db import get_connection  # noqa: E402
from erpclaw_lib.query import Field, P, Q, Table, insert_row  # noqa: E402

SP = _load("schedule_patterns", _SCRIPTS_DIR).ACTIONS
MS = _load("master_schedule", _SCRIPTS_DIR).ACTIONS
CR = _load("conflict_resolution", _SCRIPTS_DIR).ACTIONS
RA = _load("room_assignment", _SCRIPTS_DIR).ACTIONS

OWNED_TABLES = (
    "educlaw_schedule_pattern",
    "educlaw_day_type",
    "educlaw_bell_period",
    "educlaw_master_schedule",
    "educlaw_section_meeting",
    "educlaw_course_request",
    "educlaw_schedule_conflict",
    "educlaw_room_booking",
    "educlaw_instructor_constraint",
)

SNAPSHOT_TABLES = (
    "company",
    "audit_log",
    "naming_series",
    "educlaw_student",
    "educlaw_academic_year",
    "educlaw_academic_term",
    "educlaw_room",
    "educlaw_instructor",
    "educlaw_course",
    "educlaw_section",
    "educlaw_course_enrollment",
) + OWNED_TABLES


@pytest.fixture
def conn(db_path):
    handle = get_connection(db_path)
    yield handle
    try:
        handle.close()
    except Exception:
        pass


def _rows(handle, table_name, order=("id",), **filters):
    table = Table(table_name)
    query = Q.from_(table).select(table.star)
    params = []
    for column, value in filters.items():
        query = query.where(Field(column) == P())
        params.append(value)
    for column in order:
        query = query.orderby(Field(column))
    return [dict(r) for r in handle.execute(query.get_sql(), tuple(params)).fetchall()]


def _snapshot(handle):
    return {name: _rows(handle, name) for name in SNAPSHOT_TABLES}


def _add_pattern(handle, cid, name, ptype="traditional", cycle=5, total=35):
    r = call_action(SP["schedule-add-schedule-pattern"], handle, ns(
        company_id=cid, name=name, pattern_type=ptype, cycle_days=cycle,
        total_periods_per_cycle=total, description=name + " desc", notes=None,
        is_active=0, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _add_day(handle, cid, pattern_id, name, code, sort):
    r = call_action(SP["schedule-add-day-type"], handle, ns(
        schedule_pattern_id=pattern_id, company_id=cid, name=name, code=code,
        sort_order=sort, description=None, user_id=None))
    assert is_ok(r), r
    return r["id"]


def _add_bell(handle, cid, pattern_id, day_id, number, pname,
              start="08:00", end="08:50", duration=50, sort=1):
    r = call_action(SP["schedule-add-bell-period"], handle, ns(
        schedule_pattern_id=pattern_id, company_id=cid, period_number=number,
        period_name=pname, start_time=start, end_time=end,
        duration_minutes=duration, period_type="class",
        applies_to_day_types=json.dumps([day_id]), sort_order=sort, user_id=None))
    assert is_ok(r), r
    return r["id"]


def _seed_term(handle, cid, yid, name, start, end):
    tid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_academic_term", {
        "id": P(), "name": P(), "term_type": P(), "academic_year_id": P(),
        "start_date": P(), "end_date": P(), "enrollment_start_date": P(),
        "enrollment_end_date": P(), "grade_submission_deadline": P(),
        "status": P(), "company_id": P(), "created_by": P()})
    handle.execute(sql, (tid, name, "semester", yid, start, end, start, end,
                         end, "active", cid, ""))
    handle.commit()
    return tid


def _add_master(handle, cid, term_id, pattern_id, name):
    r = call_action(MS["schedule-create-master-schedule"], handle, ns(
        company_id=cid, academic_term_id=term_id, schedule_pattern_id=pattern_id,
        name=name, description=None, build_notes=None, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _place(handle, master_id, section_id, day_id, bell_id,
           instructor_id=None, room_id=None):
    r = call_action(MS["schedule-add-section-meeting"], handle, ns(
        master_schedule_id=master_id, section_id=section_id, day_type_id=day_id,
        bell_period_id=bell_id, room_id=room_id, instructor_id=instructor_id,
        meeting_type=None, meeting_mode=None, notes=None, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _request(handle, cid, sid, course_id, term_id, priority=1):
    r = call_action(MS["schedule-submit-course-request"], handle, ns(
        company_id=cid, student_id=sid, course_id=course_id,
        academic_term_id=term_id, request_priority=priority, is_alternate=0,
        alternate_for_course_id=None, prerequisite_override=None,
        prerequisite_override_by=None, prerequisite_override_note=None,
        has_iep_flag=0, submitted_by="counselor", user_id="counselor"))
    assert is_ok(r), r
    return r["id"]


def _constraint(handle, iid, cid, term_id, ctype, value, priority):
    r = call_action(RA["schedule-add-instructor-constraint"], handle, ns(
        instructor_id=iid, company_id=cid, academic_term_id=term_id,
        constraint_type=ctype, constraint_value=value,
        constraint_notes=ctype + " note", priority=priority,
        start_time=None, end_time=None, day_type_id=None, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _room(handle, cid, number, building, capacity, room_type, facilities):
    rid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_room", {
        "id": P(), "room_number": P(), "building": P(), "capacity": P(),
        "room_type": P(), "facilities": P(), "is_active": P(),
        "company_id": P(), "created_by": P()})
    handle.execute(sql, (rid, number, building, capacity, room_type,
                         json.dumps(facilities), 1, cid, ""))
    handle.commit()
    return rid


def _enroll(handle, cid, sid, section_id, status="enrolled"):
    eid = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_course_enrollment", {
        "id": P(), "student_id": P(), "section_id": P(),
        "enrollment_date": P(), "enrollment_status": P(),
        "company_id": P(), "created_by": P()})
    handle.execute(sql, (eid, sid, section_id, "2025-08-01", status, cid, ""))
    handle.commit()
    return eid


def _run_conflict_check(handle, master_id):
    r = call_action(CR["schedule-generate-conflict-check"], handle, ns(
        master_schedule_id=master_id, user_id="admin"))
    assert is_ok(r), r
    return r


def test_owned_tables_visible_through_seam(db_path, conn):
    for name in OWNED_TABLES:
        assert seam.table_exists(name, db_path), f"owned table missing: {name}"
    cols = seam.column_names("educlaw_schedule_pattern", db_path)
    assert {"id", "name", "pattern_type", "company_id"} <= set(cols)


class TestGetSchedulePatternDepth:
    def test_get_returns_the_stored_pattern_with_children(self, conn):
        cid = seed_company(conn)
        pat = _add_pattern(conn, cid, "Depth Pattern")
        day = _add_day(conn, cid, pat, "Day A", "A", 1)
        bell = _add_bell(conn, cid, pat, day, "1", "Period 1")
        before = _snapshot(conn)

        r = call_action(SP["schedule-get-schedule-pattern"], conn, ns(
            pattern_id=pat, company_id=cid))
        assert is_ok(r), r
        assert r["name"] == "Depth Pattern"
        assert r["pattern_type"] == "traditional"
        assert r["cycle_days"] == 5
        assert r["total_periods_per_cycle"] == 35
        assert r["description"] == "Depth Pattern desc"
        assert len(r["day_types"]) == 1
        assert r["day_types"][0]["code"] == "A"
        assert r["day_types"][0]["name"] == "Day A"
        assert len(r["bell_periods"]) == 1
        assert r["bell_periods"][0]["period_name"] == "Period 1"
        assert r["bell_periods"][0]["start_time"] == "08:00"
        assert r["bell_periods"][0]["end_time"] == "08:50"
        assert r["bell_periods"][0]["duration_minutes"] == 50
        assert r["bell_periods"][0]["applies_to_day_types"] == [day]

        stored = _rows(conn, "educlaw_schedule_pattern", id=pat)
        assert len(stored) == 1
        assert stored[0]["name"] == r["name"]
        assert stored[0]["pattern_type"] == r["pattern_type"]
        assert stored[0]["cycle_days"] == r["cycle_days"]
        assert stored[0]["total_periods_per_cycle"] == r["total_periods_per_cycle"]
        assert stored[0]["company_id"] == cid
        assert _rows(conn, "educlaw_day_type", id=day)[0]["code"] == "A"
        assert _rows(conn, "educlaw_bell_period", id=bell)[0]["period_name"] == "Period 1"
        assert _snapshot(conn) == before

    def test_get_refuses_without_a_pattern_id(self, conn):
        cid = seed_company(conn)
        pat = _add_pattern(conn, cid, "Refusal Pattern")
        before = _snapshot(conn)

        missing = call_action(SP["schedule-get-schedule-pattern"], conn, ns(
            company_id=cid))
        assert is_error(missing)
        assert "required" in missing["message"].lower()

        unknown = call_action(SP["schedule-get-schedule-pattern"], conn, ns(
            pattern_id="00000000-0000-0000-0000-000000000000", company_id=cid))
        assert is_error(unknown)
        assert "not found" in unknown["message"].lower()
        assert _rows(conn, "educlaw_schedule_pattern", id=pat)[0]["name"] == "Refusal Pattern"
        assert _snapshot(conn) == before


class TestListSchedulePatternsDepth:
    def test_list_returns_exactly_the_stored_patterns(self, conn):
        cid = seed_company(conn)
        _add_pattern(conn, cid, "Alpha Depth", ptype="traditional")
        _add_pattern(conn, cid, "Beta Depth", ptype="block_4x4")
        before = _snapshot(conn)

        r = call_action(SP["schedule-list-schedule-patterns"], conn, ns(
            company_id=cid, search=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {p["name"] for p in r["schedule_patterns"]} == {"Alpha Depth", "Beta Depth"}

        searched = call_action(SP["schedule-list-schedule-patterns"], conn, ns(
            company_id=cid, search="Alpha", limit=50, offset=0))
        assert is_ok(searched), searched
        assert searched["count"] == 1
        assert searched["schedule_patterns"][0]["name"] == "Alpha Depth"
        assert searched["schedule_patterns"][0]["pattern_type"] == "traditional"

        stored = _rows(conn, "educlaw_schedule_pattern", company_id=cid)
        assert len(stored) == 2
        assert {s["pattern_type"] for s in stored} == {"traditional", "block_4x4"}
        assert _snapshot(conn) == before

    def test_list_has_no_refusal_path_unknown_company_returns_empty(self, conn):
        # This action defines no err() branch: every argument is an optional
        # filter, so there is no input it refuses. The closest truthful check
        # is that an unknown scope returns an empty ok response and writes
        # nothing.
        cid = seed_company(conn)
        _add_pattern(conn, cid, "Lonely Depth")
        before = _snapshot(conn)

        r = call_action(SP["schedule-list-schedule-patterns"], conn, ns(
            company_id="00000000-0000-0000-0000-000000000000",
            search=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert r["schedule_patterns"] == []
        assert _snapshot(conn) == before


class TestGetScheduleMatrixDepth:
    def test_matrix_places_the_stored_meeting_in_its_slot(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pat = _add_pattern(conn, cid, "Matrix Depth")
        day = _add_day(conn, cid, pat, "Day A", "A", 1)
        bell = _add_bell(conn, cid, pat, day, "1", "Period 1")
        course = seed_course(conn, cid)
        sec = seed_section(conn, cid, course)
        mid = _add_master(conn, cid, tid, pat, "Matrix MS")
        _place(conn, mid, sec, day, bell)
        before = _snapshot(conn)

        r = call_action(MS["schedule-get-schedule-matrix"], conn, ns(
            master_schedule_id=mid))
        assert is_ok(r), r
        assert r["master_schedule_id"] == mid
        assert r["master_schedule_name"] == "Matrix MS"
        assert [d["code"] for d in r["day_types"]] == ["A"]
        assert len(r["matrix"]) == 1
        slot = r["matrix"][0]
        assert slot["period_number"] == "1"
        assert slot["period_name"] == "Period 1"
        assert len(slot["slots"]["A"]) == 1
        assert slot["slots"]["A"][0]["section_id"] == sec

        stored = _rows(conn, "educlaw_section_meeting", master_schedule_id=mid)
        assert len(stored) == 1
        assert stored[0]["section_id"] == sec
        assert stored[0]["day_type_id"] == day
        assert stored[0]["bell_period_id"] == bell
        assert _snapshot(conn) == before

    def test_matrix_refuses_without_a_master_schedule_id(self, conn):
        cid = seed_company(conn)
        before = _snapshot(conn)

        missing = call_action(MS["schedule-get-schedule-matrix"], conn, ns())
        assert is_error(missing)
        assert "required" in missing["message"].lower()

        unknown = call_action(MS["schedule-get-schedule-matrix"], conn, ns(
            master_schedule_id="00000000-0000-0000-0000-000000000000"))
        assert is_error(unknown)
        assert "not found" in unknown["message"].lower()
        assert _snapshot(conn) == before


class TestListMasterSchedulesDepth:
    def test_list_returns_exactly_the_stored_masters(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        t1 = _seed_term(conn, cid, yid, "Fall Depth", "2025-08-25", "2025-12-20")
        t2 = _seed_term(conn, cid, yid, "Spring Depth", "2026-01-20", "2026-05-15")
        pat = _add_pattern(conn, cid, "MS List Depth")
        _add_master(conn, cid, t1, pat, "MS Fall Depth")
        _add_master(conn, cid, t2, pat, "MS Spring Depth")
        before = _snapshot(conn)

        r = call_action(MS["schedule-list-master-schedules"], conn, ns(
            company_id=cid, academic_term_id=None, schedule_status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {m["name"] for m in r["master_schedules"]} == {
            "MS Fall Depth", "MS Spring Depth"}

        narrowed = call_action(MS["schedule-list-master-schedules"], conn, ns(
            company_id=cid, academic_term_id=t1, schedule_status=None,
            limit=50, offset=0))
        assert is_ok(narrowed), narrowed
        assert narrowed["count"] == 1
        assert narrowed["master_schedules"][0]["name"] == "MS Fall Depth"
        assert narrowed["master_schedules"][0]["academic_term_id"] == t1

        stored = _rows(conn, "educlaw_master_schedule", company_id=cid)
        assert len(stored) == 2
        assert {s["academic_term_id"] for s in stored} == {t1, t2}
        assert _snapshot(conn) == before

    def test_list_has_no_refusal_path_unknown_company_returns_empty(self, conn):
        # No err() branch exists here either: all arguments are optional
        # filters, so an unknown scope must return empty, never refuse.
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pat = _add_pattern(conn, cid, "MS Lonely Depth")
        _add_master(conn, cid, tid, pat, "MS Lonely")
        before = _snapshot(conn)

        r = call_action(MS["schedule-list-master-schedules"], conn, ns(
            company_id="00000000-0000-0000-0000-000000000000",
            academic_term_id=None, schedule_status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert r["master_schedules"] == []
        assert _snapshot(conn) == before


class TestListSectionMeetingsDepth:
    def test_list_returns_exactly_the_placed_meetings(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pat = _add_pattern(conn, cid, "Meetings Depth")
        day_a = _add_day(conn, cid, pat, "Day A", "A", 1)
        day_b = _add_day(conn, cid, pat, "Day B", "B", 2)
        bell = _add_bell(conn, cid, pat, day_a, "1", "Period 1")
        sec1 = seed_section(conn, cid, seed_course(conn, cid))
        sec2 = seed_section(conn, cid, seed_course(conn, cid))
        mid = _add_master(conn, cid, tid, pat, "Meetings MS")
        _place(conn, mid, sec1, day_a, bell)
        _place(conn, mid, sec2, day_b, bell)
        before = _snapshot(conn)

        r = call_action(MS["schedule-list-section-meetings"], conn, ns(
            company_id=cid, master_schedule_id=mid, section_id=None,
            instructor_id=None, day_type_id=None, room_id=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {m["section_id"] for m in r["section_meetings"]} == {sec1, sec2}

        narrowed = call_action(MS["schedule-list-section-meetings"], conn, ns(
            company_id=cid, master_schedule_id=mid, section_id=sec1,
            instructor_id=None, day_type_id=None, room_id=None,
            limit=50, offset=0))
        assert is_ok(narrowed), narrowed
        assert narrowed["count"] == 1
        assert narrowed["section_meetings"][0]["day_type_id"] == day_a

        stored = _rows(conn, "educlaw_section_meeting", master_schedule_id=mid)
        assert len(stored) == 2
        by_section = {s["section_id"]: (s["day_type_id"], s["bell_period_id"])
                      for s in stored}
        assert by_section == {sec1: (day_a, bell), sec2: (day_b, bell)}
        assert _snapshot(conn) == before

    def test_list_refuses_without_a_master_schedule_id(self, conn):
        cid = seed_company(conn)
        before = _snapshot(conn)

        r = call_action(MS["schedule-list-section-meetings"], conn, ns(
            company_id=cid, master_schedule_id=None, section_id=None,
            instructor_id=None, day_type_id=None, room_id=None,
            limit=50, offset=0))
        assert is_error(r)
        assert "required" in r["message"].lower()
        assert _snapshot(conn) == before


class TestListCourseRequestsDepth:
    def test_list_returns_exactly_the_submitted_requests(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        s1 = seed_student(conn, cid)
        s2 = seed_student(conn, cid)
        c1 = seed_course(conn, cid)
        c2 = seed_course(conn, cid)
        _request(conn, cid, s1, c1, tid, priority=1)
        _request(conn, cid, s2, c2, tid, priority=2)
        before = _snapshot(conn)

        r = call_action(MS["schedule-list-course-requests"], conn, ns(
            company_id=cid, student_id=None, academic_term_id=None,
            course_id=None, request_status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {(q["student_id"], q["course_id"]) for q in r["course_requests"]} == {
            (s1, c1), (s2, c2)}

        narrowed = call_action(MS["schedule-list-course-requests"], conn, ns(
            company_id=cid, student_id=s1, academic_term_id=None,
            course_id=None, request_status=None, limit=50, offset=0))
        assert is_ok(narrowed), narrowed
        assert narrowed["count"] == 1
        assert narrowed["course_requests"][0]["course_id"] == c1
        assert narrowed["course_requests"][0]["request_status"] == "submitted"
        assert narrowed["course_requests"][0]["request_priority"] == 1

        stored = _rows(conn, "educlaw_course_request", company_id=cid)
        assert len(stored) == 2
        by_student = {s["student_id"]: s for s in stored}
        assert by_student[s1]["request_status"] == "submitted"
        assert by_student[s2]["request_priority"] == 2
        assert _snapshot(conn) == before

    def test_list_has_no_refusal_path_unknown_student_returns_empty(self, conn):
        # All arguments are optional filters and no err() branch exists, so an
        # unknown scope must return empty, never refuse.
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        _request(conn, cid, seed_student(conn, cid), seed_course(conn, cid), tid)
        before = _snapshot(conn)

        r = call_action(MS["schedule-list-course-requests"], conn, ns(
            company_id=cid, student_id="00000000-0000-0000-0000-000000000000",
            academic_term_id=None, course_id=None, request_status=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert r["course_requests"] == []
        assert _snapshot(conn) == before


class TestGetSingletonAnalysisDepth:
    def test_analysis_flags_only_the_course_with_one_request(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        solo = seed_course(conn, cid)
        popular = seed_course(conn, cid)
        s1 = seed_student(conn, cid)
        s2 = seed_student(conn, cid)
        s3 = seed_student(conn, cid)
        _request(conn, cid, s1, solo, tid)
        _request(conn, cid, s1, popular, tid)
        _request(conn, cid, s2, popular, tid)
        _request(conn, cid, s3, popular, tid)
        solo_code = _rows(conn, "educlaw_course", id=solo)[0]["course_code"]
        before = _snapshot(conn)

        r = call_action(MS["schedule-get-singleton-analysis"], conn, ns(
            academic_term_id=tid, min_requests=None, company_id=cid))
        assert is_ok(r), r
        assert r["academic_term_id"] == tid
        assert r["singleton_courses"] == 1
        assert len(r["singletons"]) == 1
        assert r["singletons"][0]["course_id"] == solo
        assert r["singletons"][0]["course_code"] == solo_code
        assert r["singletons"][0]["total_requests"] == 1

        stored = _rows(conn, "educlaw_course_request", academic_term_id=tid)
        counts = {}
        for row in stored:
            counts[row["course_id"]] = counts.get(row["course_id"], 0) + 1
        assert counts == {solo: 1, popular: 3}
        assert _snapshot(conn) == before

    def test_analysis_refuses_without_an_academic_term_id(self, conn):
        cid = seed_company(conn)
        before = _snapshot(conn)

        r = call_action(MS["schedule-get-singleton-analysis"], conn, ns(
            academic_term_id=None, min_requests=None, company_id=cid))
        assert is_error(r)
        assert "required" in r["message"].lower()
        assert _snapshot(conn) == before


class TestListConflictsDepth:
    def test_list_returns_the_conflict_the_check_wrote(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pat = _add_pattern(conn, cid, "Conflict Depth")
        day = _add_day(conn, cid, pat, "Day A", "A", 1)
        bell = _add_bell(conn, cid, pat, day, "1", "Period 1")
        iid = seed_instructor(conn, cid)
        course = seed_course(conn, cid)
        sec1 = seed_section(conn, cid, course)
        sec2 = seed_section(conn, cid, course)
        mid = _add_master(conn, cid, tid, pat, "Conflict MS")
        meet1 = _place(conn, mid, sec1, day, bell, instructor_id=iid)
        meet2 = _place(conn, mid, sec2, day, bell, instructor_id=iid)
        check = _run_conflict_check(conn, mid)
        assert check["results_by_type"]["instructor_double_booking"] == 1
        before = _snapshot(conn)

        r = call_action(CR["schedule-list-conflicts"], conn, ns(
            company_id=cid, master_schedule_id=mid,
            conflict_type="instructor_double_booking", severity=None,
            conflict_status=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 1
        row = r["conflicts"][0]
        assert row["master_schedule_id"] == mid
        assert row["conflict_type"] == "instructor_double_booking"
        assert row["severity"] == "critical"
        assert row["conflict_status"] == "open"
        assert row["instructor_id"] == iid
        assert {row["section_meeting_id_a"], row["section_meeting_id_b"]} == {
            meet1, meet2}

        stored = _rows(conn, "educlaw_schedule_conflict", id=row["id"])
        assert len(stored) == 1
        assert stored[0]["conflict_type"] == row["conflict_type"]
        assert stored[0]["severity"] == row["severity"]
        assert stored[0]["conflict_status"] == row["conflict_status"]
        assert stored[0]["master_schedule_id"] == mid

        unfiltered = call_action(CR["schedule-list-conflicts"], conn, ns(
            company_id=cid, master_schedule_id=mid, conflict_type=None,
            severity=None, conflict_status=None, limit=50, offset=0))
        assert is_ok(unfiltered), unfiltered
        assert unfiltered["count"] >= 1
        assert {c["master_schedule_id"] for c in unfiltered["conflicts"]} == {mid}
        assert _snapshot(conn) == before

    def test_list_refuses_without_a_master_schedule_id(self, conn):
        cid = seed_company(conn)
        before = _snapshot(conn)

        r = call_action(CR["schedule-list-conflicts"], conn, ns(
            company_id=cid, master_schedule_id=None, conflict_type=None,
            severity=None, conflict_status=None, limit=50, offset=0))
        assert is_error(r)
        assert "required" in r["message"].lower()
        assert _snapshot(conn) == before


class TestGetSingletonConflictMapDepth:
    def test_map_flags_two_singletons_sharing_one_slot(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pat = _add_pattern(conn, cid, "Singleton Depth")
        day = _add_day(conn, cid, pat, "Day A", "A", 1)
        bell = _add_bell(conn, cid, pat, day, "1", "Period 1")
        course_a = seed_course(conn, cid)
        course_b = seed_course(conn, cid)
        sec_a = seed_section(conn, cid, course_a)
        sec_b = seed_section(conn, cid, course_b)
        mid = _add_master(conn, cid, tid, pat, "Singleton MS")
        _place(conn, mid, sec_a, day, bell)
        _place(conn, mid, sec_b, day, bell)
        code_a = _rows(conn, "educlaw_course", id=course_a)[0]["course_code"]
        code_b = _rows(conn, "educlaw_course", id=course_b)[0]["course_code"]
        before = _snapshot(conn)

        r = call_action(CR["schedule-get-singleton-conflict-map"], conn, ns(
            master_schedule_id=mid, company_id=cid))
        assert is_ok(r), r
        assert r["master_schedule_id"] == mid
        assert r["singleton_courses"] == 2
        assert len(r["all_singletons"]) == 2
        assert r["singleton_conflicts"] == 1
        assert len(r["conflict_slots"]) == 1
        slot = r["conflict_slots"][0]
        assert slot["day_code"] == "A"
        assert slot["period_name"] == "Period 1"
        assert {c["course_code"] for c in slot["conflicting_courses"]} == {
            code_a, code_b}

        stored = _rows(conn, "educlaw_section_meeting", master_schedule_id=mid)
        assert len(stored) == 2
        assert {(s["day_type_id"], s["bell_period_id"]) for s in stored} == {
            (day, bell)}
        assert _snapshot(conn) == before

    def test_map_refuses_without_a_master_schedule_id(self, conn):
        cid = seed_company(conn)
        before = _snapshot(conn)

        missing = call_action(CR["schedule-get-singleton-conflict-map"], conn, ns(
            master_schedule_id=None, company_id=cid))
        assert is_error(missing)
        assert "required" in missing["message"].lower()

        unknown = call_action(CR["schedule-get-singleton-conflict-map"], conn, ns(
            master_schedule_id="00000000-0000-0000-0000-000000000000",
            company_id=cid))
        assert is_error(unknown)
        assert "not found" in unknown["message"].lower()
        assert _snapshot(conn) == before


class TestGetStudentConflictReportDepth:
    def test_report_names_the_double_enrolled_student(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        pat = _add_pattern(conn, cid, "Student Conflict Depth")
        day = _add_day(conn, cid, pat, "Day A", "A", 1)
        bell = _add_bell(conn, cid, pat, day, "1", "Period 1")
        course_a = seed_course(conn, cid)
        course_b = seed_course(conn, cid)
        sec_a = seed_section(conn, cid, course_a)
        sec_b = seed_section(conn, cid, course_b)
        sid = seed_student(conn, cid)
        _enroll(conn, cid, sid, sec_a)
        _enroll(conn, cid, sid, sec_b)
        mid = _add_master(conn, cid, tid, pat, "Student Conflict MS")
        _place(conn, mid, sec_a, day, bell)
        _place(conn, mid, sec_b, day, bell)
        code_a = _rows(conn, "educlaw_course", id=course_a)[0]["course_code"]
        code_b = _rows(conn, "educlaw_course", id=course_b)[0]["course_code"]
        before = _snapshot(conn)

        r = call_action(CR["schedule-get-student-conflict-report"], conn, ns(
            master_schedule_id=mid, company_id=cid))
        assert is_ok(r), r
        assert r["master_schedule_id"] == mid
        assert r["students_with_registered_conflicts"] == 0
        assert r["conflict_student_list"] == []
        assert len(r["enrollment_conflict_details"]) == 1
        detail = r["enrollment_conflict_details"][0]
        assert detail["student_id"] == sid
        assert detail["cnt"] == 2
        assert detail["day_code"] == "A"
        assert code_a in detail["conflicting_courses"]
        assert code_b in detail["conflicting_courses"]

        stored = _rows(conn, "educlaw_course_enrollment", student_id=sid)
        assert len(stored) == 2
        assert {e["enrollment_status"] for e in stored} == {"enrolled"}
        assert _snapshot(conn) == before

    def test_report_refuses_without_a_master_schedule_id(self, conn):
        cid = seed_company(conn)
        before = _snapshot(conn)

        missing = call_action(CR["schedule-get-student-conflict-report"], conn, ns(
            master_schedule_id=None, company_id=cid))
        assert is_error(missing)
        assert "required" in missing["message"].lower()

        unknown = call_action(CR["schedule-get-student-conflict-report"], conn, ns(
            master_schedule_id="00000000-0000-0000-0000-000000000000",
            company_id=cid))
        assert is_error(unknown)
        assert "not found" in unknown["message"].lower()
        assert _snapshot(conn) == before


class TestListRoomsByFeaturesDepth:
    def test_search_filters_on_capacity_and_facilities(self, conn):
        cid = seed_company(conn)
        _room(conn, cid, "LAB-201", "Science Hall", 40, "lab",
              ["projector", "lab_benches"])
        _room(conn, cid, "CLS-102", "Main Building", 30, "classroom",
              ["projector"])
        before = _snapshot(conn)

        big = call_action(RA["schedule-list-rooms-by-features"], conn, ns(
            company_id=cid, room_type=None, capacity=35, building=None,
            features=None, accessibility_required=None, limit=50, offset=0))
        assert is_ok(big), big
        assert big["count"] == 1
        assert big["rooms"][0]["room_number"] == "LAB-201"
        assert big["rooms"][0]["capacity"] == 40
        assert big["rooms"][0]["facilities"] == ["projector", "lab_benches"]

        projector = call_action(RA["schedule-list-rooms-by-features"], conn, ns(
            company_id=cid, room_type=None, capacity=None, building=None,
            features=json.dumps(["projector"]), accessibility_required=None,
            limit=50, offset=0))
        assert is_ok(projector), projector
        assert projector["count"] == 2

        benches = call_action(RA["schedule-list-rooms-by-features"], conn, ns(
            company_id=cid, room_type=None, capacity=None, building=None,
            features=json.dumps(["lab_benches"]), accessibility_required=None,
            limit=50, offset=0))
        assert is_ok(benches), benches
        assert benches["count"] == 1
        assert benches["rooms"][0]["room_number"] == "LAB-201"

        stored = _rows(conn, "educlaw_room", company_id=cid)
        assert len(stored) == 2
        assert {s["room_number"] for s in stored} == {"LAB-201", "CLS-102"}
        assert _snapshot(conn) == before

    def test_search_has_no_refusal_path_impossible_filter_returns_empty(self, conn):
        # Every argument is an optional filter and no err() branch exists, so
        # an impossible filter must return empty, never refuse.
        cid = seed_company(conn)
        _room(conn, cid, "CLS-103", "Main Building", 30, "classroom", [])
        before = _snapshot(conn)

        r = call_action(RA["schedule-list-rooms-by-features"], conn, ns(
            company_id=cid, room_type=None, capacity=9999, building=None,
            features=None, accessibility_required=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert r["rooms"] == []
        assert _snapshot(conn) == before


class TestListInstructorConstraintsDepth:
    def test_list_returns_exactly_the_stored_constraints(self, conn):
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        iid = seed_instructor(conn, cid)
        _constraint(conn, iid, cid, tid, "max_periods_per_day", 6, "soft")
        _constraint(conn, iid, cid, tid, "unavailable", 0, "hard")
        before = _snapshot(conn)

        r = call_action(RA["schedule-list-instructor-constraints"], conn, ns(
            company_id=cid, instructor_id=iid, constraint_type=None,
            limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 2
        assert {c["constraint_type"] for c in r["instructor_constraints"]} == {
            "max_periods_per_day", "unavailable"}

        narrowed = call_action(RA["schedule-list-instructor-constraints"], conn, ns(
            company_id=cid, instructor_id=iid,
            constraint_type="max_periods_per_day", limit=50, offset=0))
        assert is_ok(narrowed), narrowed
        assert narrowed["count"] == 1
        row = narrowed["instructor_constraints"][0]
        assert row["constraint_value"] == 6
        assert row["priority"] == "soft"
        assert row["academic_term_id"] == tid
        assert row["constraint_notes"] == "max_periods_per_day note"

        stored = _rows(conn, "educlaw_instructor_constraint", instructor_id=iid)
        assert len(stored) == 2
        by_type = {s["constraint_type"]: s for s in stored}
        assert by_type["max_periods_per_day"]["constraint_value"] == 6
        assert by_type["unavailable"]["priority"] == "hard"
        assert _snapshot(conn) == before

    def test_list_has_no_refusal_path_unknown_instructor_returns_empty(self, conn):
        # All arguments are optional filters and no err() branch exists, so an
        # unknown scope must return empty, never refuse.
        cid = seed_company(conn)
        yid = seed_academic_year(conn, cid)
        tid = seed_academic_term(conn, cid, yid)
        _constraint(conn, seed_instructor(conn, cid), cid, tid,
                    "max_periods_per_day", 6, "soft")
        before = _snapshot(conn)

        r = call_action(RA["schedule-list-instructor-constraints"], conn, ns(
            company_id=cid, instructor_id="00000000-0000-0000-0000-000000000000",
            constraint_type=None, limit=50, offset=0))
        assert is_ok(r), r
        assert r["count"] == 0
        assert r["instructor_constraints"] == []
        assert _snapshot(conn) == before
