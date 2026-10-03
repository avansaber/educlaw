"""Behavioural depth tests (m428) for 12 educlaw-scheduling actions.

Each action below is exercised for what it actually does to the database, not
for the shape of its response envelope. Four of the twelve
(``schedule-add-schedule-pattern``, ``schedule-add-day-type``,
``schedule-add-bell-period``, ``schedule-add-instructor-constraint``) already
have a routing/shape test in ``test_scheduling.py`` asserting only ``is_ok``;
the other eight have no test at all. Those shallow tests are left untouched;
the tests here prove the effect: the exact row written (or flipped), the rows
that must NOT have changed, and one input-validation refusal per action that
must leave the database byte-identical.

None of these 12 handlers reaches the general ledger and none of them touches
money: every one of them writes only ``educlaw_*`` scheduling rows (plus one
``audit_log`` row and, for course requests and master schedules, a
``naming_series`` bump) and never posts journals. Each success test says so in
a comment so a later reader does not add debit/credit assertions that cannot
hold. There are no monetary columns in this module, so there is nothing to
compare as ``Decimal``; every assertion compares exact stored values.

Connections come from ``erpclaw_lib.db.get_connection()``; rows are read back
with plain ``SELECT`` statements over known business tables. No
catalog-introspection queries appear in this file — only reads of business rows.
"""
import importlib.util
import json
import os

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

from erpclaw_lib.db import get_connection  # noqa: E402

SP_ACTIONS = _load("schedule_patterns", _SCRIPTS_DIR).ACTIONS
MS_ACTIONS = _load("master_schedule", _SCRIPTS_DIR).ACTIONS
CR_ACTIONS = _load("conflict_resolution", _SCRIPTS_DIR).ACTIONS
RA_ACTIONS = _load("room_assignment", _SCRIPTS_DIR).ACTIONS
AU_ACTIONS = _load("auto_schedule", _SCRIPTS_DIR).ACTIONS

FAKE_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def env(db_path):
    conn = get_connection(db_path)
    cid = _helpers.seed_company(conn)
    s1 = _helpers.seed_student(conn, cid)
    s2 = _helpers.seed_student(conn, cid)
    yid = _helpers.seed_academic_year(conn, cid)
    tid = _helpers.seed_academic_term(conn, cid, yid)
    room = _helpers.seed_room(conn, cid)
    # employee_id is UNIQUE with a '' default, so each seeded instructor
    # gets a distinct value immediately (test seeding only).
    inst1 = _helpers.seed_instructor(conn, cid)
    conn.execute("UPDATE educlaw_instructor SET employee_id = 'EMP-1' WHERE id = ?", (inst1,))
    conn.commit()
    inst2 = _helpers.seed_instructor(conn, cid)
    conn.execute("UPDATE educlaw_instructor SET employee_id = 'EMP-2' WHERE id = ?", (inst2,))
    conn.commit()
    course_a = _helpers.seed_course(conn, cid)
    course_b = _helpers.seed_course(conn, cid)
    yield {
        "conn": conn, "company_id": cid, "student1": s1, "student2": s2,
        "year_id": yid, "term_id": tid, "room_id": room,
        "instructor1": inst1, "instructor2": inst2,
        "course_a": course_a, "course_b": course_b,
    }
    conn.close()


_SNAPSHOT_TABLES = (
    "educlaw_schedule_pattern",
    "educlaw_day_type",
    "educlaw_bell_period",
    "educlaw_master_schedule",
    "educlaw_course_request",
    "educlaw_section_meeting",
    "educlaw_room_booking",
    "educlaw_instructor_constraint",
    "educlaw_schedule_conflict",
    "audit_log",
    "naming_series",
)


def _snapshot(conn):
    """Full row dump of every owned table (plus audit_log/naming_series)."""
    snap = {}
    for table in _SNAPSHOT_TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        snap[table] = sorted(
            json.dumps(dict(r), sort_keys=True, default=str) for r in rows)
    return snap


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _pattern(s, name="Depth Pattern", active=0):
    r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
        company_id=s["company_id"], name=name, pattern_type="traditional",
        cycle_days=5, total_periods_per_cycle=35, description=None,
        notes=None, is_active=active, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _day(s, pattern_id, code="A", name="Day A"):
    r = call_action(SP_ACTIONS["schedule-add-day-type"], s["conn"], ns(
        schedule_pattern_id=pattern_id, company_id=s["company_id"],
        name=name, code=code, sort_order=1, description=None, user_id=None))
    assert is_ok(r), r
    return r["id"]


def _bell(s, pattern_id, day_id, number="1", start="08:00", end="08:50", order=1):
    r = call_action(SP_ACTIONS["schedule-add-bell-period"], s["conn"], ns(
        schedule_pattern_id=pattern_id, company_id=s["company_id"],
        period_number=number, period_name=f"Period {number}",
        start_time=start, end_time=end, duration_minutes=50,
        period_type="class", applies_to_day_types=f'["{day_id}"]',
        sort_order=order, user_id=None))
    assert is_ok(r), r
    return r["id"]


def _master(s, pattern_id, name="Depth Master"):
    r = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
        company_id=s["company_id"], academic_term_id=s["term_id"],
        schedule_pattern_id=pattern_id, name=name, description=None,
        build_notes=None, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _term_section(s, course_id=None, instructor_id=None, max_enrollment=30):
    """A section bound to the fixture term (seed leaves academic_term_id NULL)."""
    if course_id is None:
        course_id = _helpers.seed_course(s["conn"], s["company_id"])
    sec = _helpers.seed_section(s["conn"], s["company_id"], course_id)
    s["conn"].execute(
        "UPDATE educlaw_section SET academic_term_id = ?, instructor_id = ?, "
        "max_enrollment = ? WHERE id = ?",
        (s["term_id"], instructor_id, max_enrollment, sec))
    s["conn"].commit()
    return sec


def _meeting(s, master_id, section_id, day_id, bell_id, room_id=None, instructor_id=None):
    r = call_action(MS_ACTIONS["schedule-add-section-meeting"], s["conn"], ns(
        master_schedule_id=master_id, section_id=section_id,
        day_type_id=day_id, bell_period_id=bell_id, room_id=room_id,
        instructor_id=instructor_id, meeting_type="regular",
        meeting_mode="in_person", notes=None, user_id="admin"))
    assert is_ok(r), r
    return r["id"]


def _request(s, student_id, course_id, priority=1):
    r = call_action(MS_ACTIONS["schedule-submit-course-request"], s["conn"], ns(
        company_id=s["company_id"], student_id=student_id, course_id=course_id,
        academic_term_id=s["term_id"], request_priority=priority,
        is_alternate=0, alternate_for_course_id=None,
        prerequisite_override=None, prerequisite_override_by=None,
        prerequisite_override_note=None, has_iep_flag=0,
        submitted_by="counselor", user_id="counselor"))
    assert is_ok(r), r
    return r["id"]


# ---------------------------------------------------------------------------
# schedule-add-schedule-pattern — stored row
# ---------------------------------------------------------------------------

class TestAddSchedulePatternDepth:
    def test_writes_pattern_row_with_defaults_and_audit(self, env):
        s, conn = env, env["conn"]
        r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=s["company_id"], name="Traditional 7-Period",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35, description=None, notes=None,
            is_active=0, user_id="admin"))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT name, description, pattern_type, cycle_days, "
            "total_periods_per_cycle, notes, is_active, company_id, created_by "
            "FROM educlaw_schedule_pattern WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == ("Traditional 7-Period", "", "traditional", 5,
                              35, "", 0, s["company_id"], "admin")
        stamps = conn.execute(
            "SELECT created_at != '', updated_at != '' "
            "FROM educlaw_schedule_pattern WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(stamps) == (1, 1)
        assert _count(conn, "educlaw_schedule_pattern") == 1
        audit_rows = conn.execute(
            "SELECT skill, action, entity_type, entity_id FROM audit_log "
            "WHERE entity_id = ?", (r["id"],)).fetchall()
        assert [tuple(a) for a in audit_rows] == [
            ("schedule-educlaw-scheduling", "schedule-add-schedule-pattern",
             "educlaw_schedule_pattern", r["id"])]
        # No ledger legs: one pattern row plus one audit row, never journals.

    def test_refuses_a_missing_name_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=s["company_id"], name=None, pattern_type="traditional",
            cycle_days=5, total_periods_per_cycle=None, description=None,
            notes=None, is_active=0, user_id=None))
        assert is_error(r)
        assert r["message"] == "--name is required"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_schedule_pattern") == 0


# ---------------------------------------------------------------------------
# schedule-add-day-type — stored row
# ---------------------------------------------------------------------------

class TestAddDayTypeDepth:
    def test_writes_day_type_row_and_leaves_pattern_alone(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s)
        r = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
            schedule_pattern_id=pat, company_id=s["company_id"],
            name="Day A", code="A", sort_order=1,
            description=None, user_id=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT schedule_pattern_id, code, name, sort_order, company_id, "
            "created_by FROM educlaw_day_type WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (pat, "A", "Day A", 1, s["company_id"], "")
        assert _count(conn, "educlaw_day_type") == 1
        # The parent pattern is untouched (still inactive, same name).
        pat_row = conn.execute(
            "SELECT name, is_active FROM educlaw_schedule_pattern "
            "WHERE id = ?", (pat,)).fetchone()
        assert tuple(pat_row) == ("Depth Pattern", 0)
        # No ledger legs: one day-type row plus one audit row, never journals.

    def test_refuses_a_missing_code_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s)
        before = _snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
            schedule_pattern_id=pat, company_id=s["company_id"],
            name="Day B", code=None, sort_order=2,
            description=None, user_id=None))
        assert is_error(r)
        assert r["message"] == "--code is required"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_day_type") == 0


# ---------------------------------------------------------------------------
# schedule-add-bell-period — stored row
# ---------------------------------------------------------------------------

class TestAddBellPeriodDepth:
    def test_writes_bell_period_row_with_exact_minutes(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s)
        day = _day(s, pat)
        r = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
            schedule_pattern_id=pat, company_id=s["company_id"],
            period_number="1", period_name="Period 1",
            start_time="08:00", end_time="08:50", duration_minutes=50,
            period_type="class", applies_to_day_types=f'["{day}"]',
            sort_order=1, user_id=None))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT schedule_pattern_id, period_number, period_name, "
            "start_time, end_time, duration_minutes, period_type, "
            "applies_to_day_types, sort_order, company_id, created_by "
            "FROM educlaw_bell_period WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (pat, "1", "Period 1", "08:00", "08:50", 50,
                              "class", f'["{day}"]', 1, s["company_id"], "")
        assert _count(conn, "educlaw_bell_period") == 1
        # The day type it applies to is untouched.
        day_row = conn.execute(
            "SELECT code, name FROM educlaw_day_type WHERE id = ?", (day,)).fetchone()
        assert tuple(day_row) == ("A", "Day A")
        # No ledger legs: one bell-period row plus one audit row, never journals.

    def test_refuses_a_zero_duration_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s)
        day = _day(s, pat)
        before = _snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
            schedule_pattern_id=pat, company_id=s["company_id"],
            period_number="1", period_name="Period 1",
            start_time="08:00", end_time="08:50", duration_minutes=0,
            period_type="class", applies_to_day_types=f'["{day}"]',
            sort_order=1, user_id=None))
        assert is_error(r)
        assert r["message"] == "--duration-minutes must be > 0"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_bell_period") == 0


# ---------------------------------------------------------------------------
# schedule-activate-schedule-pattern — stored row (status flip)
# ---------------------------------------------------------------------------

class TestActivateSchedulePatternDepth:
    def test_flips_inactive_to_active_and_leaves_sibling_alone(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s)
        day = _day(s, pat)
        _bell(s, pat, day)
        sibling = _pattern(s, name="Sibling Pattern")
        assert conn.execute(
            "SELECT is_active FROM educlaw_schedule_pattern "
            "WHERE id = ?", (pat,)).fetchone()[0] == 0
        r = call_action(SP_ACTIONS["schedule-activate-schedule-pattern"], conn, ns(
            pattern_id=pat))
        assert is_ok(r), r
        assert r["is_active"] == 1
        assert (r["day_types"], r["bell_periods"]) == (1, 1)
        flags = dict(conn.execute(
            "SELECT id, is_active FROM educlaw_schedule_pattern").fetchall())
        assert flags == {pat: 1, sibling: 0}
        # No ledger legs: only the is_active flag moves, never journals.

    def test_refuses_a_pattern_with_no_day_types_and_flips_nothing(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s)
        before = _snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-activate-schedule-pattern"], conn, ns(
            pattern_id=pat))
        assert is_error(r)
        assert r["message"] == ("Cannot activate: pattern must have at least "
                                "one day type. Use add-day-type to add day "
                                "types first.")
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT is_active FROM educlaw_schedule_pattern "
            "WHERE id = ?", (pat,)).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# schedule-add-section-to-schedule — stored row (counter bump, no new row)
# ---------------------------------------------------------------------------

class TestAddSectionToScheduleDepth:
    def test_registers_two_sections_by_bumping_total_only(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        ms = _master(s, pat)
        sec1 = _term_section(s)
        sec2 = _term_section(s)
        assert conn.execute(
            "SELECT total_sections FROM educlaw_master_schedule "
            "WHERE id = ?", (ms,)).fetchone()[0] == 0
        r1 = call_action(MS_ACTIONS["schedule-add-section-to-schedule"], conn, ns(
            master_schedule_id=ms, section_id=sec1))
        assert is_ok(r1), r1
        assert r1["total_sections"] == 1
        r2 = call_action(MS_ACTIONS["schedule-add-section-to-schedule"], conn, ns(
            master_schedule_id=ms, section_id=sec2))
        assert is_ok(r2), r2
        assert r2["total_sections"] == 2
        stats = conn.execute(
            "SELECT total_sections, sections_placed, sections_with_room, "
            "open_conflicts, fulfillment_rate, schedule_status "
            "FROM educlaw_master_schedule WHERE id = ?", (ms,)).fetchone()
        assert tuple(stats) == (2, 0, 0, 0, "0.0%", "draft")
        # Registering creates no meetings: placement is a separate action.
        assert _count(conn, "educlaw_section_meeting") == 0
        # No ledger legs: only total_sections moves, never journals.

    def test_refuses_a_section_from_another_term_and_bumps_nothing(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        ms = _master(s, pat)
        # Seeded sections carry no academic_term_id, so they belong to no term.
        stray = _helpers.seed_section(conn, s["company_id"])
        before = _snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-add-section-to-schedule"], conn, ns(
            master_schedule_id=ms, section_id=stray))
        assert is_error(r)
        assert r["message"] == ("Section belongs to a different academic term "
                                "than this master schedule")
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT total_sections FROM educlaw_master_schedule "
            "WHERE id = ?", (ms,)).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# schedule-add-section-meeting — stored row (meeting + auto room booking)
# ---------------------------------------------------------------------------

class TestAddSectionMeetingDepth:
    def test_places_meeting_autobooks_room_and_refreshes_stats(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        day = _day(s, pat)
        bell = _bell(s, pat, day)
        ms = _master(s, pat)
        sec = _term_section(s)
        other = _term_section(s)
        reg = call_action(MS_ACTIONS["schedule-add-section-to-schedule"], conn, ns(
            master_schedule_id=ms, section_id=sec))
        assert is_ok(reg), reg
        r = call_action(MS_ACTIONS["schedule-add-section-meeting"], conn, ns(
            master_schedule_id=ms, section_id=sec, day_type_id=day,
            bell_period_id=bell, room_id=s["room_id"],
            instructor_id=s["instructor1"], meeting_type="regular",
            meeting_mode="in_person", notes=None, user_id="admin"))
        assert is_ok(r), r
        meeting = conn.execute(
            "SELECT section_id, master_schedule_id, day_type_id, "
            "bell_period_id, room_id, instructor_id, meeting_type, "
            "meeting_mode, is_active, notes, company_id, created_by "
            "FROM educlaw_section_meeting WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(meeting) == (sec, ms, day, bell, s["room_id"],
                                  s["instructor1"], "regular", "in_person",
                                  1, "", s["company_id"], "admin")
        bookings = conn.execute(
            "SELECT room_id, master_schedule_id, section_meeting_id, "
            "day_type_id, bell_period_id, booking_type, booking_title, "
            "booked_by, booking_status, company_id FROM educlaw_room_booking"
        ).fetchall()
        assert [tuple(b) for b in bookings] == [
            (s["room_id"], ms, r["id"], day, bell, "class", "Class: SEC-001",
             "admin", "confirmed", s["company_id"])]
        stats = conn.execute(
            "SELECT total_sections, sections_placed, sections_with_room, "
            "open_conflicts, fulfillment_rate, schedule_status "
            "FROM educlaw_master_schedule WHERE id = ?", (ms,)).fetchone()
        assert tuple(stats) == (1, 1, 1, 0, "100.0%", "draft")
        # The sibling section still has no meetings.
        assert conn.execute(
            "SELECT COUNT(*) FROM educlaw_section_meeting "
            "WHERE section_id = ?", (other,)).fetchone()[0] == 0
        # No ledger legs: a meeting row, a booking row and stats, never journals.

    def test_refuses_a_bad_meeting_type_and_places_nothing(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        day = _day(s, pat)
        bell = _bell(s, pat, day)
        ms = _master(s, pat)
        sec = _term_section(s)
        before = _snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-add-section-meeting"], conn, ns(
            master_schedule_id=ms, section_id=sec, day_type_id=day,
            bell_period_id=bell, room_id=None, instructor_id=None,
            meeting_type="nope", meeting_mode="in_person", notes=None,
            user_id="admin"))
        assert is_error(r)
        assert r["message"] == ("--meeting-type must be one of: regular, lab, "
                                "exam, field_trip, make_up")
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_section_meeting") == 0
        assert _count(conn, "educlaw_room_booking") == 0


# ---------------------------------------------------------------------------
# schedule-activate-course-requests — read-only (no stored row)
# ---------------------------------------------------------------------------

class TestActivateCourseRequestsDepth:
    def test_reports_live_request_count_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _request(s, s["student1"], s["course_a"])
        _request(s, s["student2"], s["course_a"])
        before = _snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-activate-course-requests"], conn, ns(
            academic_term_id=s["term_id"]))
        assert is_ok(r), r
        assert r["existing_requests"] == 2
        assert r["term_name"] == "Fall 2025"
        assert r["term_status"] == "active"
        assert r["ready_for_requests"] is True
        # Read-only proof: the call observes the database but changes nothing.
        assert _snapshot(conn) == before
        statuses = conn.execute(
            "SELECT DISTINCT request_status FROM educlaw_course_request").fetchall()
        assert [tuple(x) for x in statuses] == [("submitted",)]
        # No ledger legs: this action only reads the term and counts requests.

    def test_refuses_an_unknown_term_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        _request(s, s["student1"], s["course_a"])
        before = _snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-activate-course-requests"], conn, ns(
            academic_term_id=FAKE_ID))
        assert is_error(r)
        assert r["message"] == f"Academic term {FAKE_ID} not found"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_course_request") == 1


# ---------------------------------------------------------------------------
# schedule-approve-course-requests — stored rows (status flip)
# ---------------------------------------------------------------------------

class TestApproveCourseRequestsDepth:
    def test_approves_filtered_course_and_leaves_other_course_submitted(self, env):
        s, conn = env, env["conn"]
        q1 = _request(s, s["student1"], s["course_a"], priority=1)
        q2 = _request(s, s["student2"], s["course_a"], priority=2)
        q3 = _request(s, s["student1"], s["course_b"], priority=1)
        r = call_action(MS_ACTIONS["schedule-approve-course-requests"], conn, ns(
            academic_term_id=s["term_id"], course_id=s["course_a"],
            approved_by="registrar", user_id=None))
        assert is_ok(r), r
        assert r["requests_approved"] == 2
        assert r["approved_by"] == "registrar"
        rows = conn.execute(
            "SELECT id, request_status, approved_by, approved_at != '', "
            "request_priority FROM educlaw_course_request").fetchall()
        by_id = {row[0]: tuple(row[1:]) for row in rows}
        assert by_id[q1] == ("approved", "registrar", 1, 1)
        assert by_id[q2] == ("approved", "registrar", 1, 2)
        # The other course is out of the filter: still submitted, blank approver.
        assert by_id[q3] == ("submitted", "", 0, 1)
        # No ledger legs: only status/approver columns move, never journals.

    def test_refuses_without_an_approver_and_approves_nothing(self, env):
        s, conn = env, env["conn"]
        _request(s, s["student1"], s["course_a"])
        before = _snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-approve-course-requests"], conn, ns(
            academic_term_id=s["term_id"], course_id=None,
            approved_by=None, user_id=None))
        assert is_error(r)
        assert r["message"] == "--approved-by or --user-id is required"
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT request_status FROM educlaw_course_request").fetchone()[0] == "submitted"


# ---------------------------------------------------------------------------
# schedule-accept-conflict — stored row (status flip open -> accepted)
# ---------------------------------------------------------------------------

class TestAcceptConflictDepth:
    def _conflicted(self, s):
        conn = s["conn"]
        pat = _pattern(s, active=1)
        day = _day(s, pat)
        bell = _bell(s, pat, day)
        ms = _master(s, pat)
        sec1 = _term_section(s, instructor_id=s["instructor1"])
        sec2 = _term_section(s, instructor_id=s["instructor1"])
        _meeting(s, ms, sec1, day, bell, room_id=s["room_id"],
                 instructor_id=s["instructor1"])
        # Same instructor, same slot: recorded with a warning, still placed.
        second = call_action(MS_ACTIONS["schedule-add-section-meeting"], conn, ns(
            master_schedule_id=ms, section_id=sec2, day_type_id=day,
            bell_period_id=bell, room_id=None,
            instructor_id=s["instructor1"], meeting_type="regular",
            meeting_mode="in_person", notes=None, user_id="admin"))
        assert is_ok(second), second
        assert "warnings" in second
        gen = call_action(CR_ACTIONS["schedule-generate-conflict-check"], conn, ns(
            master_schedule_id=ms))
        assert is_ok(gen), gen
        return ms

    def test_accepts_a_medium_conflict_and_refreshes_open_count(self, env):
        s, conn = env, env["conn"]
        ms = self._conflicted(s)
        target = conn.execute(
            "SELECT id, severity, conflict_status FROM educlaw_schedule_conflict "
            "WHERE conflict_type = 'credential_mismatch' "
            "AND conflict_status = 'open' LIMIT 1").fetchone()
        assert tuple(target[1:]) == ("medium", "open")
        critical = conn.execute(
            "SELECT id FROM educlaw_schedule_conflict "
            "WHERE conflict_type = 'instructor_double_booking' "
            "AND conflict_status = 'open'").fetchall()
        assert len(critical) == 1
        open_before = conn.execute(
            "SELECT open_conflicts FROM educlaw_master_schedule "
            "WHERE id = ?", (ms,)).fetchone()[0]
        assert open_before >= 2
        r = call_action(CR_ACTIONS["schedule-accept-conflict"], conn, ns(
            conflict_id=target["id"], resolution_notes="Known exception",
            resolved_by="registrar", user_id=None))
        assert is_ok(r), r
        assert r["conflict_status"] == "accepted"
        row = conn.execute(
            "SELECT conflict_status, resolution_notes, resolved_by, "
            "resolved_at != '' FROM educlaw_schedule_conflict "
            "WHERE id = ?", (target["id"],)).fetchone()
        assert tuple(row) == ("accepted", "Known exception", "registrar", 1)
        open_after = conn.execute(
            "SELECT open_conflicts FROM educlaw_master_schedule "
            "WHERE id = ?", (ms,)).fetchone()[0]
        assert open_after == open_before - 1
        # The critical double-booking stays open: acceptance is not resolution.
        assert conn.execute(
            "SELECT conflict_status FROM educlaw_schedule_conflict "
            "WHERE id = ?", (critical[0]["id"],)).fetchone()[0] == "open"
        # No ledger legs: only conflict status columns move, never journals.

    def test_refuses_a_critical_conflict_and_changes_nothing(self, env):
        s, conn = env, env["conn"]
        self._conflicted(s)
        critical = conn.execute(
            "SELECT id FROM educlaw_schedule_conflict "
            "WHERE severity = 'critical' AND conflict_status = 'open' "
            "LIMIT 1").fetchone()
        before = _snapshot(conn)
        r = call_action(CR_ACTIONS["schedule-accept-conflict"], conn, ns(
            conflict_id=critical["id"], resolution_notes="let it slide",
            resolved_by="registrar", user_id=None))
        assert is_error(r)
        assert r["message"] == ("CRITICAL conflicts cannot be accepted \u2014 they "
                                "must be resolved before publishing. Use "
                                "complete-conflict instead.")
        assert _snapshot(conn) == before
        assert conn.execute(
            "SELECT conflict_status FROM educlaw_schedule_conflict "
            "WHERE id = ?", (critical["id"],)).fetchone()[0] == "open"


# ---------------------------------------------------------------------------
# schedule-add-room-block — stored row
# ---------------------------------------------------------------------------

class TestAddRoomBlockDepth:
    def test_writes_block_booking_row_for_the_slot(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        day = _day(s, pat)
        bell = _bell(s, pat, day)
        ms = _master(s, pat)
        r = call_action(RA_ACTIONS["schedule-add-room-block"], conn, ns(
            room_id=s["room_id"], day_type_id=day, bell_period_id=bell,
            booking_title="Science Fair", booked_by="principal",
            booking_type="event", master_schedule_id=ms,
            accessibility_required=None, company_id=s["company_id"],
            user_id="admin"))
        assert is_ok(r), r
        assert r["booking_status"] == "confirmed"
        row = conn.execute(
            "SELECT room_id, master_schedule_id, section_meeting_id, "
            "day_type_id, bell_period_id, booking_type, booking_title, "
            "booked_by, booking_status, accessibility_required, company_id, "
            "created_by FROM educlaw_room_booking WHERE id = ?",
            (r["booking_id"],)).fetchone()
        assert tuple(row) == (s["room_id"], ms, None, day, bell, "event",
                              "Science Fair", "principal", "confirmed", 0,
                              s["company_id"], "admin")
        assert _count(conn, "educlaw_room_booking") == 1
        # No ledger legs: one booking row plus one audit row, never journals.

    def test_refuses_a_double_booked_slot_and_keeps_the_first_block(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        day = _day(s, pat)
        bell = _bell(s, pat, day)
        ms = _master(s, pat)
        first = call_action(RA_ACTIONS["schedule-add-room-block"], conn, ns(
            room_id=s["room_id"], day_type_id=day, bell_period_id=bell,
            booking_title="Science Fair", booked_by="principal",
            booking_type="event", master_schedule_id=ms,
            accessibility_required=None, company_id=s["company_id"],
            user_id="admin"))
        assert is_ok(first), first
        before = _snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-add-room-block"], conn, ns(
            room_id=s["room_id"], day_type_id=day, bell_period_id=bell,
            booking_title="Second Event", booked_by="principal",
            booking_type="event", master_schedule_id=ms,
            accessibility_required=None, company_id=s["company_id"],
            user_id="admin"))
        assert is_error(r)
        assert r["message"] == f"Room {s['room_id']} is already booked for this slot"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_room_booking") == 1


# ---------------------------------------------------------------------------
# schedule-add-instructor-constraint — stored row
# ---------------------------------------------------------------------------

class TestAddInstructorConstraintDepth:
    def test_writes_constraint_row_with_priority(self, env):
        s, conn = env, env["conn"]
        r = call_action(RA_ACTIONS["schedule-add-instructor-constraint"], conn, ns(
            instructor_id=s["instructor1"], company_id=s["company_id"],
            academic_term_id=s["term_id"],
            constraint_type="max_periods_per_day", constraint_value=6,
            constraint_notes="Max 6 periods", priority="soft",
            start_time=None, end_time=None, day_type_id=None, user_id="admin"))
        assert is_ok(r), r
        row = conn.execute(
            "SELECT instructor_id, academic_term_id, constraint_type, "
            "constraint_value, constraint_notes, priority, is_active, "
            "company_id, created_by, day_type_id, bell_period_id "
            "FROM educlaw_instructor_constraint WHERE id = ?", (r["id"],)).fetchone()
        assert tuple(row) == (s["instructor1"], s["term_id"],
                              "max_periods_per_day", 6, "Max 6 periods",
                              "soft", 1, s["company_id"], "admin", None, None)
        assert _count(conn, "educlaw_instructor_constraint") == 1
        # No ledger legs: one constraint row plus one audit row, never journals.

    def test_refuses_an_unknown_type_and_writes_nothing(self, env):
        s, conn = env, env["conn"]
        before = _snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-add-instructor-constraint"], conn, ns(
            instructor_id=s["instructor1"], company_id=s["company_id"],
            academic_term_id=s["term_id"], constraint_type="teleportation",
            constraint_value=1, constraint_notes=None, priority="soft",
            start_time=None, end_time=None, day_type_id=None, user_id="admin"))
        assert is_error(r)
        assert r["message"] == ("--constraint-type must be one of: unavailable, "
                                "preferred, max_periods_per_day, "
                                "max_consecutive_periods, requires_prep_period, "
                                "preferred_building")
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_instructor_constraint") == 0


# ---------------------------------------------------------------------------
# edu-auto-build-schedule — stored rows (one meeting per placed section)
# ---------------------------------------------------------------------------

class TestAutoBuildScheduleDepth:
    def test_places_each_section_once_in_distinct_slots(self, env):
        s, conn = env, env["conn"]
        pat = _pattern(s, active=1)
        day = _day(s, pat)
        bell1 = _bell(s, pat, day, number="1", start="08:00", end="08:50", order=1)
        bell2 = _bell(s, pat, day, number="2", start="09:00", end="09:50", order=2)
        ms = _master(s, pat)
        sec1 = _term_section(s, course_id=s["course_a"],
                             instructor_id=s["instructor1"], max_enrollment=30)
        sec2 = _term_section(s, course_id=s["course_b"],
                             instructor_id=s["instructor2"], max_enrollment=10)
        r = call_action(AU_ACTIONS["edu-auto-build-schedule"], conn, ns(
            master_schedule_id=ms, company_id=s["company_id"]))
        assert is_ok(r), r
        assert (r["total_sections"], r["placed"], r["unplaced"]) == (2, 2, 0)
        assert r["success_rate_pct"] == 100.0
        m1 = conn.execute(
            "SELECT day_type_id, bell_period_id, room_id, instructor_id, "
            "meeting_type, meeting_mode, is_active, company_id, created_by "
            "FROM educlaw_section_meeting WHERE section_id = ? "
            "AND master_schedule_id = ?", (sec1, ms)).fetchall()
        assert [tuple(m) for m in m1] == [
            (day, bell1, s["room_id"], s["instructor1"], "regular",
             "in_person", 1, s["company_id"], "auto_scheduler")]
        m2 = conn.execute(
            "SELECT day_type_id, bell_period_id, room_id, instructor_id, "
            "meeting_type, meeting_mode, is_active, company_id, created_by "
            "FROM educlaw_section_meeting WHERE section_id = ? "
            "AND master_schedule_id = ?", (sec2, ms)).fetchall()
        assert [tuple(m) for m in m2] == [
            (day, bell2, s["room_id"], s["instructor2"], "regular",
             "in_person", 1, s["company_id"], "auto_scheduler")]
        # No slot is double-booked: two meetings, two distinct day/period cells.
        cells = conn.execute(
            "SELECT COUNT(DISTINCT day_type_id || bell_period_id || room_id) "
            "FROM educlaw_section_meeting "
            "WHERE master_schedule_id = ?", (ms,)).fetchone()[0]
        assert cells == 2
        # No ledger legs: meeting rows only, never journals.

    def test_refuses_an_unknown_master_schedule_and_places_nothing(self, env):
        s, conn = env, env["conn"]
        _term_section(s)
        before = _snapshot(conn)
        r = call_action(AU_ACTIONS["edu-auto-build-schedule"], conn, ns(
            master_schedule_id=FAKE_ID, company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == f"Master schedule {FAKE_ID} not found"
        assert _snapshot(conn) == before
        assert _count(conn, "educlaw_section_meeting") == 0
