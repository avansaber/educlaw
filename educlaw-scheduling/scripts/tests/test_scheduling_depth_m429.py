"""Behavioural depth tests for 12 scheduling actions (m429-depth-educlaw-scheduling-2).

Each action below already had a test that proved the wrong thing: the
contract suite (testing/integration/contract/test_educlaw_scheduling_contract.py)
only proves the action is routable, and the shape tests in
test_scheduling.py only prove the response has the expected keys. Neither
observes the database, so an action could return a perfectly shaped response
while writing nothing (or the wrong thing) and still pass.

Every test here asserts the database effect instead: the exact stored row(s)
read back afterwards through PyPika queries over erpclaw_lib.db connections,
what changed from what to what, and what did NOT change. Each action also has
one refusal test proving the refusal message is truthful and the owned tables
are byte-identical afterwards.

Money discipline: scheduling tables hold no monetary columns, so there are no
Decimal assertions to make here; fulfillment_rate is a TEXT percentage and is
compared as an exact string, never rounded or approximated.

Ledger discipline: no scheduling action posts to the ledger. All 12 tests
below assert stored rows; none asserts a ledger effect, because none can hold.
A later reader must not add gl_entry assertions to these actions.

Two findings are documented, not fixed (per TASK.md rule 6):
  FINDING-1  schedule-assign-rooms crashes with sqlite3.ProgrammingError
             ("Error binding parameter 10") because bulk_assign_rooms passes
             the erpclaw_lib.query.now *function* as a bind parameter instead
             of calling it. Nothing is written.
  FINDING-2  schedule-complete-course-requests does not mark anything
             complete: despite its docstring ("mark remaining submitted
             requests as unfulfilled") it only counts requests by status and
             leaves every row untouched.
"""
import importlib.util
import json
import os
import uuid

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


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
seed_room = _helpers.seed_room
seed_instructor = _helpers.seed_instructor
seed_course = _helpers.seed_course
seed_section = _helpers.seed_section

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, insert_row

SP_ACTIONS = _load("schedule_patterns", _SCRIPTS_DIR).ACTIONS
MS_ACTIONS = _load("master_schedule", _SCRIPTS_DIR).ACTIONS
CR_ACTIONS = _load("conflict_resolution", _SCRIPTS_DIR).ACTIONS
RA_ACTIONS = _load("room_assignment", _SCRIPTS_DIR).ACTIONS

OWNED_TABLES = (
    "educlaw_master_schedule",
    "educlaw_course_request",
    "educlaw_section_meeting",
    "educlaw_schedule_conflict",
    "educlaw_room_booking",
    "educlaw_instructor_constraint",
)


@pytest.fixture
def conn(db_path):
    handle = get_connection(db_path)
    yield handle
    handle.close()


def _rows(handle, table, where=None):
    ref = Table(table)
    query = Q.from_(ref).select(ref.star)
    params = []
    if where:
        for column, value in where.items():
            query = query.where(Field(column) == P())
            params.append(value)
    return [dict(r) for r in handle.execute(query.get_sql(), params).fetchall()]


def _row(handle, table, row_id):
    found = _rows(handle, table, {"id": row_id})
    return found[0] if found else None


def _snapshot(handle):
    snap = {}
    for table in OWNED_TABLES:
        snap[table] = sorted(
            json.dumps(r, sort_keys=True, default=str) for r in _rows(handle, table)
        )
    return snap


def _base(handle):
    company_id = seed_company(handle)
    student_id = seed_student(handle, company_id)
    year_id = seed_academic_year(handle, company_id)
    term_id = seed_academic_term(handle, company_id, year_id)
    room_id = seed_room(handle, company_id)
    instructor_id = seed_instructor(handle, company_id)
    course_id = seed_course(handle, company_id)
    section_id = seed_section(handle, company_id)
    return {
        "company_id": company_id, "student_id": student_id,
        "year_id": year_id, "term_id": term_id, "room_id": room_id,
        "instructor_id": instructor_id, "course_id": course_id,
        "section_id": section_id,
    }


def _pattern(handle, company_id):
    pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], handle, ns(
        company_id=company_id, name="Depth Pattern",
        pattern_type="traditional", cycle_days=5,
        total_periods_per_cycle=35,
        description=None, notes=None,
        is_active=1, user_id=None,
    ))
    assert is_ok(pat)
    day = call_action(SP_ACTIONS["schedule-add-day-type"], handle, ns(
        schedule_pattern_id=pat["id"], company_id=company_id,
        name="Day A", code="A", sort_order=1,
        description=None, user_id=None,
    ))
    assert is_ok(day)
    bell = call_action(SP_ACTIONS["schedule-add-bell-period"], handle, ns(
        schedule_pattern_id=pat["id"], company_id=company_id,
        period_number="1", period_name="Period 1",
        start_time="08:00", end_time="08:50",
        duration_minutes=50, period_type="class",
        applies_to_day_types=json.dumps([day["id"]]),
        sort_order=1, user_id=None,
    ))
    assert is_ok(bell)
    return pat["id"], day["id"], bell["id"]


def _master(handle, company_id, term_id, pattern_id, name="Depth Master"):
    made = call_action(MS_ACTIONS["schedule-create-master-schedule"], handle, ns(
        company_id=company_id, academic_term_id=term_id,
        schedule_pattern_id=pattern_id,
        name=name, description=None, build_notes=None, user_id="admin",
    ))
    assert is_ok(made)
    return made["id"]


def _meeting(handle, master_id, section_id, day_id, bell_id,
             room_id=None, instructor_id=None):
    placed = call_action(MS_ACTIONS["schedule-add-section-meeting"], handle, ns(
        master_schedule_id=master_id, section_id=section_id,
        day_type_id=day_id, bell_period_id=bell_id,
        room_id=room_id, instructor_id=instructor_id,
        meeting_type="regular", meeting_mode="in_person",
        notes=None, user_id="admin",
    ))
    assert is_ok(placed)
    return placed["id"]


def _second_room(handle, company_id):
    room_id = str(uuid.uuid4())
    sql, _cols = insert_row("educlaw_room", {
        "id": P(), "room_number": P(), "room_type": P(),
        "capacity": P(), "building": P(), "is_active": P(),
        "company_id": P(), "created_by": P(),
    })
    handle.execute(sql, (room_id, "R102", "classroom", 30,
                         "Main Building", 1, company_id, ""))
    handle.commit()
    return room_id


def _second_term(handle, company_id, year_id):
    term_id = str(uuid.uuid4())
    sql, _cols = insert_row("educlaw_academic_term", {
        "id": P(), "name": P(), "term_type": P(),
        "academic_year_id": P(), "start_date": P(), "end_date": P(),
        "enrollment_start_date": P(), "enrollment_end_date": P(),
        "grade_submission_deadline": P(), "status": P(),
        "company_id": P(), "created_by": P(),
    })
    handle.execute(sql, (term_id, "Spring 2026", "semester", year_id,
                         "2026-01-12", "2026-05-15", "2025-11-01",
                         "2026-01-05", "2026-06-01", "active",
                         company_id, ""))
    handle.commit()
    return term_id


# No ledger: schedule-create-master-schedule inserts one master_schedule row.
class TestCreateMasterScheduleDepth:
    def test_writes_exact_master_row(self, conn):
        base = _base(conn)
        pattern_id, _day, _bell = _pattern(conn, base["company_id"])
        before = _snapshot(conn)
        assert before["educlaw_master_schedule"] == []
        made = call_action(MS_ACTIONS["schedule-create-master-schedule"], conn, ns(
            company_id=base["company_id"], academic_term_id=base["term_id"],
            schedule_pattern_id=pattern_id,
            name="Fall 2025 Master", description=None,
            build_notes=None, user_id="admin",
        ))
        assert is_ok(made)
        assert made["schedule_status"] == "draft"
        assert made["naming_series"].startswith("MS-")
        stored = _row(conn, "educlaw_master_schedule", made["id"])
        assert stored["name"] == "Fall 2025 Master"
        assert stored["academic_term_id"] == base["term_id"]
        assert stored["schedule_pattern_id"] == pattern_id
        assert stored["company_id"] == base["company_id"]
        assert stored["naming_series"] == made["naming_series"]
        assert stored["schedule_status"] == "draft"
        assert stored["total_sections"] == 0
        assert stored["sections_placed"] == 0
        assert stored["sections_with_room"] == 0
        assert stored["open_conflicts"] == 0
        assert stored["fulfillment_rate"] == "0.0%"
        assert stored["cloned_from_id"] is None
        assert stored["published_at"] == ""
        assert stored["locked_at"] == ""
        for table in ("educlaw_course_request", "educlaw_section_meeting",
                      "educlaw_schedule_conflict", "educlaw_room_booking",
                      "educlaw_instructor_constraint"):
            assert _rows(conn, table) == []

    def test_refusal_missing_name_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, _day, _bell = _pattern(conn, base["company_id"])
        before = _snapshot(conn)
        refused = call_action(MS_ACTIONS["schedule-create-master-schedule"], conn, ns(
            company_id=base["company_id"], academic_term_id=base["term_id"],
            schedule_pattern_id=pattern_id,
            name=None, description=None,
            build_notes=None, user_id=None,
        ))
        assert is_error(refused)
        assert refused["message"] == "--name is required"
        assert _snapshot(conn) == before


# No ledger: schedule-create-schedule-clone inserts one master_schedule row.
class TestCreateScheduleCloneDepth:
    def test_clone_copies_pattern_and_links_source(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        source_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        source_before = _row(conn, "educlaw_master_schedule", source_id)
        target_term = _second_term(conn, base["company_id"], base["year_id"])
        cloned = call_action(MS_ACTIONS["schedule-create-schedule-clone"], conn, ns(
            master_schedule_id=source_id,
            target_academic_term_id=target_term,
            name="Spring Clone", company_id=base["company_id"],
            user_id="admin",
        ))
        assert is_ok(cloned)
        assert cloned["cloned_from_id"] == source_id
        assert cloned["academic_term_id"] == target_term
        stored = _row(conn, "educlaw_master_schedule", cloned["id"])
        assert stored["name"] == "Spring Clone"
        assert stored["academic_term_id"] == target_term
        assert stored["schedule_pattern_id"] == source_before["schedule_pattern_id"]
        assert stored["schedule_status"] == "draft"
        assert stored["cloned_from_id"] == source_id
        assert stored["naming_series"] != source_before["naming_series"]
        assert stored["build_notes"] == (
            "Cloned from %s: %s" % (source_before["naming_series"],
                                    source_before["build_notes"])
        )
        assert stored["total_sections"] == 0
        assert stored["sections_placed"] == 0
        assert stored["sections_with_room"] == 0
        assert stored["open_conflicts"] == 0
        assert stored["fulfillment_rate"] == "0.0%"
        assert _row(conn, "educlaw_master_schedule", source_id) == source_before
        assert _rows(conn, "educlaw_section_meeting",
                      {"master_schedule_id": cloned["id"]}) == []

    def test_refusal_occupied_target_term_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, _day, _bell = _pattern(conn, base["company_id"])
        source_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        before = _snapshot(conn)
        refused = call_action(MS_ACTIONS["schedule-create-schedule-clone"], conn, ns(
            master_schedule_id=source_id,
            target_academic_term_id=base["term_id"],
            name=None, company_id=None, user_id=None,
        ))
        assert is_error(refused)
        assert "already has a master schedule" in refused["message"]
        assert source_id in refused["message"]
        assert _snapshot(conn) == before


# No ledger: schedule-delete-section-meeting hard-deletes the meeting row and
# its child room_booking rows, then refreshes master stats.
class TestDeleteSectionMeetingDepth:
    def test_removes_meeting_bookings_and_refreshes_stats(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        section_two = seed_section(conn, base["company_id"])
        doomed = _meeting(conn, master_id, base["section_id"], day_id, bell_id,
                          room_id=None, instructor_id=base["instructor_id"])
        kept = _meeting(conn, master_id, section_two, day_id, bell_id,
                        room_id=None, instructor_id=None)
        assigned = call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id=doomed, room_id=base["room_id"],
            booking_type="class", booked_by="admin",
            accessibility_required=0, user_id="admin",
        ))
        assert is_ok(assigned)
        kept_before = _row(conn, "educlaw_section_meeting", kept)
        removed = call_action(
            MS_ACTIONS["schedule-delete-section-meeting"], conn,
            ns(section_meeting_id=doomed))
        assert is_ok(removed)
        assert removed["id"] == doomed
        assert removed["section_id"] == base["section_id"]
        assert _row(conn, "educlaw_section_meeting", doomed) is None
        assert _rows(conn, "educlaw_room_booking",
                      {"section_meeting_id": doomed}) == []
        assert _row(conn, "educlaw_section_meeting", kept) == kept_before
        master = _row(conn, "educlaw_master_schedule", master_id)
        assert master["sections_placed"] == 1
        assert master["sections_with_room"] == 0
        assert master["open_conflicts"] == 0
        assert master["fulfillment_rate"] == "0.0%"

    def test_refusal_unknown_meeting_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        _meeting(conn, master_id, base["section_id"], day_id, bell_id)
        before = _snapshot(conn)
        refused = call_action(
            MS_ACTIONS["schedule-delete-section-meeting"], conn,
            ns(section_meeting_id="does-not-exist"))
        assert is_error(refused)
        assert refused["message"] == "Section meeting does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger: schedule-complete-course-requests only counts requests by status.
# FINDING-2: its docstring says it marks remaining submitted requests
# unfulfilled, but the code performs no UPDATE; every row is untouched.
class TestCompleteCourseRequestsDepth:
    def test_reports_counts_and_changes_no_rows(self, conn):
        base = _base(conn)
        course_two = seed_course(conn, base["company_id"])
        for course_id in (base["course_id"], course_two):
            submitted = call_action(
                MS_ACTIONS["schedule-submit-course-request"], conn, ns(
                    company_id=base["company_id"], student_id=base["student_id"],
                    course_id=course_id, academic_term_id=base["term_id"],
                    request_priority=1, is_alternate=0,
                    alternate_for_course_id=None,
                    prerequisite_override=None, prerequisite_override_by=None,
                    prerequisite_override_note=None,
                    has_iep_flag=0, submitted_by="counselor",
                    user_id="counselor",
                ))
            assert is_ok(submitted)
        before = _rows(conn, "educlaw_course_request",
                       {"academic_term_id": base["term_id"]})
        assert len(before) == 2
        closed = call_action(
            MS_ACTIONS["schedule-complete-course-requests"], conn,
            ns(academic_term_id=base["term_id"]))
        assert is_ok(closed)
        assert closed["academic_term_id"] == base["term_id"]
        assert closed["request_summary"] == {"submitted": 2}
        assert closed["total_requests"] == 2
        after = _rows(conn, "educlaw_course_request",
                      {"academic_term_id": base["term_id"]})
        assert after == before
        assert [r["request_status"] for r in after] == ["submitted", "submitted"]

    @pytest.mark.xfail(strict=True, reason='FINDING-2: close leaves statuses submitted')
    def test_intended_unfulfilled_transition_does_not_happen(self, conn):
        base = _base(conn)
        submitted = call_action(
            MS_ACTIONS["schedule-submit-course-request"], conn, ns(
                company_id=base["company_id"], student_id=base["student_id"],
                course_id=base["course_id"], academic_term_id=base["term_id"],
                request_priority=1, is_alternate=0,
                alternate_for_course_id=None,
                prerequisite_override=None, prerequisite_override_by=None,
                prerequisite_override_note=None,
                has_iep_flag=0, submitted_by="counselor",
                user_id="counselor",
            ))
        assert is_ok(submitted)
        call_action(MS_ACTIONS["schedule-complete-course-requests"], conn,
                    ns(academic_term_id=base["term_id"]))
        stored = _row(conn, "educlaw_course_request", submitted["id"])
        assert stored["request_status"] == "unfulfilled"

    def test_refusal_unknown_term_writes_nothing(self, conn):
        base = _base(conn)
        before = _snapshot(conn)
        refused = call_action(
            MS_ACTIONS["schedule-complete-course-requests"], conn,
            ns(academic_term_id="does-not-exist"))
        assert is_error(refused)
        assert refused["message"] == "Academic term does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger: schedule-generate-conflict-check inserts conflict rows,
# supersedes prior opens, and refreshes the master open_conflicts count.
class TestGenerateConflictCheckDepth:
    def _colliding(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        section_two = seed_section(conn, base["company_id"])
        first = _meeting(conn, master_id, base["section_id"], day_id, bell_id,
                         room_id=None, instructor_id=base["instructor_id"])
        second = _meeting(conn, master_id, section_two, day_id, bell_id,
                          room_id=None, instructor_id=base["instructor_id"])
        return base, master_id, first, second

    def test_detects_double_booking_and_counts_match(self, conn):
        base, master_id, first, second = self._colliding(conn)
        checked = call_action(
            CR_ACTIONS["schedule-generate-conflict-check"], conn,
            ns(master_schedule_id=master_id))
        assert is_ok(checked)
        opens = _rows(conn, "educlaw_schedule_conflict",
                      {"master_schedule_id": master_id,
                       "conflict_status": "open"})
        assert checked["new_conflicts_found"] == len(opens)
        assert checked["open_conflicts"] == len(opens)
        assert len(opens) >= 1
        doubles = [r for r in opens
                   if r["conflict_type"] == "instructor_double_booking"]
        assert len(doubles) == 1
        assert doubles[0]["severity"] == "critical"
        assert doubles[0]["conflict_status"] == "open"
        assert doubles[0]["instructor_id"] == base["instructor_id"]
        assert {doubles[0]["section_meeting_id_a"],
                doubles[0]["section_meeting_id_b"]} == {first, second}
        master = _row(conn, "educlaw_master_schedule", master_id)
        assert master["open_conflicts"] == len(opens)

    def test_second_run_supersedes_first_run_opens(self, conn):
        _base2, master_id, _first, _second = self._colliding(conn)
        first_run = call_action(
            CR_ACTIONS["schedule-generate-conflict-check"], conn,
            ns(master_schedule_id=master_id))
        assert is_ok(first_run)
        first_ids = [r["id"] for r in _rows(
            conn, "educlaw_schedule_conflict", {"master_schedule_id": master_id})]
        assert len(first_ids) == first_run["new_conflicts_found"]
        second_run = call_action(
            CR_ACTIONS["schedule-generate-conflict-check"], conn,
            ns(master_schedule_id=master_id))
        assert is_ok(second_run)
        for old_id in first_ids:
            assert _row(conn, "educlaw_schedule_conflict", old_id)[
                "conflict_status"] == "superseded"
        opens = _rows(conn, "educlaw_schedule_conflict",
                      {"master_schedule_id": master_id,
                       "conflict_status": "open"})
        assert second_run["new_conflicts_found"] == len(opens)
        assert second_run["open_conflicts"] == len(opens)
        assert _row(conn, "educlaw_master_schedule", master_id)[
            "open_conflicts"] == len(opens)

    def test_refusal_unknown_master_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        _meeting(conn, master_id, base["section_id"], day_id, bell_id)
        before = _snapshot(conn)
        refused = call_action(
            CR_ACTIONS["schedule-generate-conflict-check"], conn,
            ns(master_schedule_id="does-not-exist"))
        assert is_error(refused)
        assert refused["message"] == "Master schedule does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger: schedule-get-conflict is a read; the test proves the response
# matches the stored row exactly and that nothing is written.
class TestGetConflictDepth:
    def test_returns_stored_row_and_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        section_two = seed_section(conn, base["company_id"])
        first = _meeting(conn, master_id, base["section_id"], day_id, bell_id,
                         room_id=None, instructor_id=base["instructor_id"])
        _meeting(conn, master_id, section_two, day_id, bell_id,
                 room_id=None, instructor_id=base["instructor_id"])
        checked = call_action(
            CR_ACTIONS["schedule-generate-conflict-check"], conn,
            ns(master_schedule_id=master_id))
        assert is_ok(checked)
        target = _rows(conn, "educlaw_schedule_conflict",
                       {"master_schedule_id": master_id,
                        "conflict_type": "instructor_double_booking"})[0]
        before = _snapshot(conn)
        fetched = call_action(CR_ACTIONS["schedule-get-conflict"], conn,
                              ns(conflict_id=target["id"]))
        assert is_ok(fetched)
        for field in ("id", "master_schedule_id", "conflict_type", "severity",
                      "section_meeting_id_a", "section_meeting_id_b",
                      "instructor_id", "conflict_status", "description",
                      "company_id"):
            assert fetched[field] == target[field]
        meeting_a = _row(conn, "educlaw_section_meeting",
                         target["section_meeting_id_a"])
        assert fetched["meeting_a_details"]["id"] == meeting_a["id"]
        assert fetched["meeting_a_details"]["section_id"] == meeting_a["section_id"]
        assert _snapshot(conn) == before

    def test_refusal_unknown_conflict_writes_nothing(self, conn):
        base = _base(conn)
        _pattern(conn, base["company_id"])
        before = _snapshot(conn)
        refused = call_action(CR_ACTIONS["schedule-get-conflict"], conn,
                              ns(conflict_id="does-not-exist"))
        assert is_error(refused)
        assert refused["message"] == "Conflict does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger: schedule-complete-conflict updates one conflict row to resolved
# and refreshes the master open_conflicts count.
class TestCompleteConflictDepth:
    def test_resolves_row_and_decrements_open_count(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        section_two = seed_section(conn, base["company_id"])
        _meeting(conn, master_id, base["section_id"], day_id, bell_id,
                 room_id=None, instructor_id=base["instructor_id"])
        _meeting(conn, master_id, section_two, day_id, bell_id,
                 room_id=None, instructor_id=base["instructor_id"])
        checked = call_action(
            CR_ACTIONS["schedule-generate-conflict-check"], conn,
            ns(master_schedule_id=master_id))
        assert is_ok(checked)
        target = _rows(conn, "educlaw_schedule_conflict",
                       {"master_schedule_id": master_id,
                        "conflict_type": "instructor_double_booking"})[0]
        opens_before = len(_rows(conn, "educlaw_schedule_conflict",
                                 {"master_schedule_id": master_id,
                                  "conflict_status": "open"}))
        others_before = [r for r in _rows(conn, "educlaw_schedule_conflict",
                                          {"master_schedule_id": master_id})
                         if r["id"] != target["id"]]
        resolved = call_action(
            CR_ACTIONS["schedule-complete-conflict"], conn, ns(
                conflict_id=target["id"],
                resolution_notes="Moved second section to Period 2",
                resolved_by="admin"))
        assert is_ok(resolved)
        assert resolved["conflict_status"] == "resolved"
        stored = _row(conn, "educlaw_schedule_conflict", target["id"])
        assert stored["conflict_status"] == "resolved"
        assert stored["resolution_notes"] == "Moved second section to Period 2"
        assert stored["resolved_by"] == "admin"
        assert stored["resolved_at"] == resolved["resolved_at"]
        assert stored["resolved_at"] != ""
        for other in others_before:
            assert _row(conn, "educlaw_schedule_conflict", other["id"]) == other
        master = _row(conn, "educlaw_master_schedule", master_id)
        assert master["open_conflicts"] == opens_before - 1
        assert master["open_conflicts"] == len(_rows(
            conn, "educlaw_schedule_conflict",
            {"master_schedule_id": master_id, "conflict_status": "open"}))

    def test_refusal_already_resolved_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        section_two = seed_section(conn, base["company_id"])
        _meeting(conn, master_id, base["section_id"], day_id, bell_id,
                 room_id=None, instructor_id=base["instructor_id"])
        _meeting(conn, master_id, section_two, day_id, bell_id,
                 room_id=None, instructor_id=base["instructor_id"])
        call_action(CR_ACTIONS["schedule-generate-conflict-check"], conn,
                    ns(master_schedule_id=master_id))
        target = _rows(conn, "educlaw_schedule_conflict",
                       {"master_schedule_id": master_id,
                        "conflict_type": "instructor_double_booking"})[0]
        first = call_action(CR_ACTIONS["schedule-complete-conflict"], conn, ns(
            conflict_id=target["id"], resolution_notes="done",
            resolved_by="admin"))
        assert is_ok(first)
        before = _snapshot(conn)
        refused = call_action(CR_ACTIONS["schedule-complete-conflict"], conn, ns(
            conflict_id=target["id"], resolution_notes="again",
            resolved_by="admin"))
        assert is_error(refused)
        assert refused["message"] == "Conflict is already resolved"
        assert _snapshot(conn) == before


# No ledger: schedule-assign-room inserts one room_booking row, sets the
# meeting room_id, and refreshes the master sections_with_room count.
class TestAssignRoomDepth:
    def test_booking_row_meeting_update_and_master_count(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        meeting_id = _meeting(conn, master_id, base["section_id"],
                              day_id, bell_id)
        assert _row(conn, "educlaw_section_meeting", meeting_id)["room_id"] is None
        assigned = call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id=meeting_id, room_id=base["room_id"],
            booking_type="class", booked_by="admin",
            accessibility_required=0, user_id="admin",
        ))
        assert is_ok(assigned)
        assert assigned["meeting_id"] == meeting_id
        assert assigned["room_id"] == base["room_id"]
        assert assigned["booking_status"] == "confirmed"
        booking = _row(conn, "educlaw_room_booking", assigned["booking_id"])
        assert booking["room_id"] == base["room_id"]
        assert booking["master_schedule_id"] == master_id
        assert booking["section_meeting_id"] == meeting_id
        assert booking["day_type_id"] == day_id
        assert booking["bell_period_id"] == bell_id
        assert booking["booking_type"] == "class"
        assert booking["booking_status"] == "confirmed"
        assert _row(conn, "educlaw_section_meeting", meeting_id)[
            "room_id"] == base["room_id"]
        assert _row(conn, "educlaw_master_schedule", master_id)[
            "sections_with_room"] == 1
        for table in ("educlaw_schedule_conflict",
                      "educlaw_instructor_constraint",
                      "educlaw_course_request"):
            assert _rows(conn, table) == []

    def test_refusal_unknown_meeting_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        _meeting(conn, master_id, base["section_id"], day_id, bell_id)
        before = _snapshot(conn)
        refused = call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id="does-not-exist", room_id=base["room_id"],
            booking_type="class", booked_by=None,
            accessibility_required=None, user_id=None,
        ))
        assert is_error(refused)
        assert refused["message"] == "Section meeting does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger: schedule-assign-room-emergency cancels each active source-room
# booking, inserts a confirmed target-room booking per slot, and repoints
# the meetings.
class TestAssignRoomEmergencyDepth:
    def test_moves_booking_and_repoints_meeting(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        meeting_id = _meeting(conn, master_id, base["section_id"],
                              day_id, bell_id)
        target_room = _second_room(conn, base["company_id"])
        assigned = call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id=meeting_id, room_id=base["room_id"],
            booking_type="class", booked_by="admin",
            accessibility_required=0, user_id="admin",
        ))
        assert is_ok(assigned)
        moved = call_action(
            RA_ACTIONS["schedule-assign-room-emergency"], conn, ns(
                room_id=base["room_id"], target_room_id=target_room,
                master_schedule_id=master_id, user_id="admin",
            ))
        assert is_ok(moved)
        assert moved["bookings_moved"] == 1
        assert moved["source_room_id"] == base["room_id"]
        assert moved["target_room_id"] == target_room
        bookings = _rows(conn, "educlaw_room_booking",
                         {"section_meeting_id": meeting_id})
        assert len(bookings) == 2
        old = [b for b in bookings if b["id"] == assigned["booking_id"]][0]
        new = [b for b in bookings if b["id"] != assigned["booking_id"]][0]
        assert old["booking_status"] == "cancelled"
        assert old["cancellation_reason"] == "Emergency room reassignment"
        assert new["room_id"] == target_room
        assert new["booking_status"] == "confirmed"
        assert new["day_type_id"] == old["day_type_id"]
        assert new["bell_period_id"] == old["bell_period_id"]
        assert _row(conn, "educlaw_section_meeting", meeting_id)[
            "room_id"] == target_room

    def test_refusal_unknown_target_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        meeting_id = _meeting(conn, master_id, base["section_id"],
                              day_id, bell_id)
        call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id=meeting_id, room_id=base["room_id"],
            booking_type="class", booked_by="admin",
            accessibility_required=0, user_id="admin",
        ))
        before = _snapshot(conn)
        refused = call_action(
            RA_ACTIONS["schedule-assign-room-emergency"], conn, ns(
                room_id=base["room_id"], target_room_id="does-not-exist",
                master_schedule_id=master_id, user_id=None,
            ))
        assert is_error(refused)
        assert refused["message"] == "Target room does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger touches either path: the validation refusal below, or the crash.
# FINDING-1: schedule-assign-rooms never succeeds. bulk_assign_rooms passes
# the erpclaw_lib.query.now function object itself as a bind parameter
# (room_assignment.py bulk loop: `..., company_id, now, now, user_id`) so the
# first INSERT raises sqlite3.ProgrammingError and nothing is written.
class TestAssignRoomsDepth:
    def test_defect_first_insert_crashes_and_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        _meeting(conn, master_id, base["section_id"], day_id, bell_id)
        with pytest.raises(Exception, match="binding parameter"):
            call_action(RA_ACTIONS["schedule-assign-rooms"], conn, ns(
                master_schedule_id=master_id, room_type=None,
                user_id="admin",
            ))
        conn.rollback()
        assert _rows(conn, "educlaw_room_booking") == []
        for meeting in _rows(conn, "educlaw_section_meeting"):
            assert meeting["room_id"] is None
        assert _row(conn, "educlaw_master_schedule", master_id)[
            "sections_with_room"] == 0

    @pytest.mark.xfail(strict=True, reason='FINDING-1: bulk assign crashes before writing')
    def test_intended_bulk_assignment_does_not_happen(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        meeting_id = _meeting(conn, master_id, base["section_id"],
                              day_id, bell_id)
        call_action(RA_ACTIONS["schedule-assign-rooms"], conn, ns(
            master_schedule_id=master_id, room_type=None, user_id="admin",
        ))
        assert _row(conn, "educlaw_section_meeting", meeting_id)[
            "room_id"] == base["room_id"]

    def test_refusal_unknown_master_writes_nothing(self, conn):
        base = _base(conn)
        _pattern(conn, base["company_id"])
        before = _snapshot(conn)
        refused = call_action(RA_ACTIONS["schedule-assign-rooms"], conn, ns(
            master_schedule_id="does-not-exist", room_type=None,
            user_id=None,
        ))
        assert is_error(refused)
        assert refused["message"] == "Master schedule does-not-exist not found"
        assert _snapshot(conn) == before


# No ledger: schedule-delete-room-assignment cancels the booking row and
# nulls the meeting room_id, then refreshes the master count.
class TestDeleteRoomAssignmentDepth:
    def test_cancels_booking_nulls_meeting_and_refreshes_count(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        meeting_id = _meeting(conn, master_id, base["section_id"],
                              day_id, bell_id)
        assigned = call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id=meeting_id, room_id=base["room_id"],
            booking_type="class", booked_by="admin",
            accessibility_required=0, user_id="admin",
        ))
        assert is_ok(assigned)
        unassigned = call_action(
            RA_ACTIONS["schedule-delete-room-assignment"], conn,
            ns(section_meeting_id=meeting_id, booking_id=None))
        assert is_ok(unassigned)
        assert unassigned["meeting_id"] == meeting_id
        assert unassigned["room_unassigned"] == base["room_id"]
        assert _row(conn, "educlaw_section_meeting", meeting_id)[
            "room_id"] is None
        booking = _row(conn, "educlaw_room_booking", assigned["booking_id"])
        assert booking["booking_status"] == "cancelled"
        assert booking["cancellation_reason"] == "Room unassigned"
        assert _row(conn, "educlaw_master_schedule", master_id)[
            "sections_with_room"] == 0

    def test_refusal_neither_id_writes_nothing(self, conn):
        base = _base(conn)
        pattern_id, day_id, bell_id = _pattern(conn, base["company_id"])
        master_id = _master(conn, base["company_id"], base["term_id"], pattern_id)
        meeting_id = _meeting(conn, master_id, base["section_id"],
                              day_id, bell_id)
        call_action(RA_ACTIONS["schedule-assign-room"], conn, ns(
            section_meeting_id=meeting_id, room_id=base["room_id"],
            booking_type="class", booked_by="admin",
            accessibility_required=0, user_id="admin",
        ))
        before = _snapshot(conn)
        refused = call_action(
            RA_ACTIONS["schedule-delete-room-assignment"], conn,
            ns(section_meeting_id=None, booking_id=None))
        assert is_error(refused)
        assert refused["message"] == "--section-meeting-id or --booking-id is required"
        assert _snapshot(conn) == before


# No ledger: schedule-delete-instructor-constraint hard-deletes the row.
class TestDeleteInstructorConstraintDepth:
    def _add(self, conn, base, ctype="max_periods_per_day", value=6):
        added = call_action(
            RA_ACTIONS["schedule-add-instructor-constraint"], conn, ns(
                instructor_id=base["instructor_id"],
                company_id=base["company_id"],
                academic_term_id=base["term_id"],
                constraint_type=ctype, constraint_value=value,
                constraint_notes="depth", priority="soft",
                start_time=None, end_time=None, day_type_id=None,
                user_id="admin",
            ))
        assert is_ok(added)
        return added["id"]

    def test_deletes_only_the_named_constraint(self, conn):
        base = _base(conn)
        doomed = self._add(conn, base, "max_periods_per_day", 6)
        kept = self._add(conn, base, "max_consecutive_periods", 3)
        kept_before = _row(conn, "educlaw_instructor_constraint", kept)
        assert kept_before["constraint_value"] == 3
        deleted = call_action(
            RA_ACTIONS["schedule-delete-instructor-constraint"], conn,
            ns(constraint_id=doomed))
        assert is_ok(deleted)
        assert deleted["id"] == doomed
        assert deleted["instructor_id"] == base["instructor_id"]
        assert deleted["constraint_type"] == "max_periods_per_day"
        assert _row(conn, "educlaw_instructor_constraint", doomed) is None
        assert _row(conn, "educlaw_instructor_constraint", kept) == kept_before

    def test_refusal_unknown_constraint_writes_nothing(self, conn):
        base = _base(conn)
        _pattern(conn, base["company_id"])
        self._add(conn, base)
        before = _snapshot(conn)
        refused = call_action(
            RA_ACTIONS["schedule-delete-instructor-constraint"], conn,
            ns(constraint_id="does-not-exist"))
        assert is_error(refused)
        assert refused["message"] == "Instructor constraint does-not-exist not found"
        assert _snapshot(conn) == before
