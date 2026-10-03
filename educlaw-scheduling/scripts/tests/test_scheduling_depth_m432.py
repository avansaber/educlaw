"""Depth tests for 9 scheduling actions previously covered by shape only.

Effect tests read the owned rows back through PyPika-built queries and compare
exact values: what row exists afterwards with which values, what changed from
what to what, and what did not change. Refusal tests prove invalid input is
rejected with a truthful message and leaves every owned table byte-identical.

Ledger note, applying to every test in this file: none of these 9 actions
posts to the ledger or touches a monetary column. The scheduling schema holds
no TEXT Decimal money columns, so there are no two legs to balance and no
Decimal assertions to make; this comment stands so a later reader does not
add an assertion that cannot hold.
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
get_conn = _helpers.get_conn
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

from erpclaw_lib.query import Field, P, Q, Table

SP_ACTIONS = _load("schedule_patterns", _SCRIPTS_DIR).ACTIONS
MS_ACTIONS = _load("master_schedule", _SCRIPTS_DIR).ACTIONS
RA_ACTIONS = _load("room_assignment", _SCRIPTS_DIR).ACTIONS

SNAPSHOT_TABLES = (
    "company", "naming_series", "audit_log",
    "educlaw_schedule_pattern", "educlaw_day_type", "educlaw_bell_period",
    "educlaw_master_schedule", "educlaw_section_meeting",
    "educlaw_room_booking", "educlaw_course_request",
    "educlaw_instructor_constraint", "educlaw_schedule_conflict",
    "educlaw_section", "educlaw_course", "educlaw_student",
    "educlaw_academic_term", "educlaw_academic_year",
    "educlaw_room", "educlaw_instructor",
)


def read_row(conn, table, row_id):
    tbl = Table(table)
    row = conn.execute(
        Q.from_(tbl).select(tbl.star).where(Field("id") == P()).get_sql(),
        (row_id,)).fetchone()
    assert row is not None, f"expected row {row_id} in {table}"
    return dict(row)


def snapshot(conn):
    data = {}
    for name in SNAPSHOT_TABLES:
        tbl = Table(name)
        rows = conn.execute(
            Q.from_(tbl).select(tbl.star).orderby(tbl.id).get_sql()).fetchall()
        data[name] = [dict(r) for r in rows]
    return data


@pytest.fixture
def conn(db_path):
    c = get_conn(db_path)
    yield c
    c.close()


@pytest.fixture
def base(conn):
    cid = seed_company(conn)
    yid = seed_academic_year(conn, cid)
    return {
        "conn": conn, "company_id": cid,
        "student_id": seed_student(conn, cid),
        "year_id": yid,
        "term_id": seed_academic_term(conn, cid, yid),
        "room_id": seed_room(conn, cid),
        "instructor_id": seed_instructor(conn, cid),
        "course_id": seed_course(conn, cid),
        "section_id": None,
    }


@pytest.fixture
def based(conn, base):
    base["section_id"] = seed_section(conn, base["company_id"], base["course_id"])
    return base


@pytest.fixture
def pattern_env(based):
    conn, cid = based["conn"], based["company_id"]
    pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
        company_id=cid, name="Depth Pattern", pattern_type="traditional",
        cycle_days=5, total_periods_per_cycle=35,
        description=None, notes=None, is_active=1, user_id=None))
    assert is_ok(pat)
    dt = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
        schedule_pattern_id=pat["id"], company_id=cid,
        name="Day A", code="A", sort_order=1, description=None, user_id=None))
    assert is_ok(dt)
    bp = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
        schedule_pattern_id=pat["id"], company_id=cid,
        period_number="1", period_name="Period 1",
        start_time="08:00", end_time="08:50", duration_minutes=50,
        period_type="class", applies_to_day_types=json.dumps([dt["id"]]),
        sort_order=1, user_id=None))
    assert is_ok(bp)
    based.update({"pattern_id": pat["id"], "day_type_id": dt["id"],
                  "bell_period_id": bp["id"]})
    return based


@pytest.fixture
def ms_env(pattern_env):
    conn = pattern_env["conn"]
    ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], conn, ns(
        company_id=pattern_env["company_id"],
        academic_term_id=pattern_env["term_id"],
        schedule_pattern_id=pattern_env["pattern_id"],
        name="Depth Master Schedule",
        description=None, build_notes=None, user_id="admin"))
    assert is_ok(ms)
    pattern_env["master_id"] = ms["id"]
    return pattern_env


def add_room(conn, company_id, number="R102", capacity=40):
    rid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_room
           (id, room_number, room_type, capacity, building,
            is_active, company_id, created_by)
           VALUES (?, ?, 'classroom', ?, 'Main Building', 1, ?, '')""",
        (rid, number, capacity, company_id))
    conn.commit()
    return rid


def add_bell_period(conn, company_id, pattern_id, day_type_id,
                    number="2", name="Period 2"):
    bp = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
        schedule_pattern_id=pattern_id, company_id=company_id,
        period_number=number, period_name=name,
        start_time="09:00", end_time="09:50", duration_minutes=50,
        period_type="class",
        applies_to_day_types=json.dumps([day_type_id]),
        sort_order=int(number), user_id=None))
    assert is_ok(bp)
    return bp["id"]


def place_meeting(env, section_id, day_type_id, bell_period_id,
                  room_id=None, instructor_id=None):
    conn = env["conn"]
    r = call_action(MS_ACTIONS["schedule-add-section-meeting"], conn, ns(
        master_schedule_id=env["master_id"], section_id=section_id,
        day_type_id=day_type_id, bell_period_id=bell_period_id,
        room_id=room_id, instructor_id=instructor_id,
        meeting_type=None, meeting_mode=None, notes=None, user_id="admin"))
    assert is_ok(r)
    return r["id"]


def set_master_status(env, new_status):
    r = call_action(MS_ACTIONS["schedule-update-master-schedule"], env["conn"], ns(
        master_schedule_id=env["master_id"], name=None, build_notes=None,
        schedule_status=new_status, user_id="admin"))
    assert is_ok(r)
    return r


def add_second_term(conn, company_id):
    yid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_year
           (id, name, start_date, end_date, is_active, company_id, created_by)
           VALUES (?, 'AY-2026', '2026-08-01', '2027-07-31', 1, ?, '')""",
        (yid, company_id))
    tid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_term
           (id, name, term_type, academic_year_id, start_date, end_date,
            enrollment_start_date, enrollment_end_date,
            grade_submission_deadline, status, company_id, created_by)
           VALUES (?, 'Spring 2026', 'semester', ?, '2026-01-10', '2026-05-15',
                   '2025-11-01', '2026-01-05', '2026-06-01', 'active', ?, '')""",
        (tid, yid, company_id))
    conn.commit()
    return tid


# ══════════════════════════════════════════════════════════════════════════════
# schedule-propose-room (read-only: proves the suggestion set, writes nothing)
# ══════════════════════════════════════════════════════════════════════════════

class TestProposeRoomDepth:
    def test_effect_suggests_only_free_rooms_and_writes_nothing(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        room_b = add_room(conn, env["company_id"])
        sec_b = seed_section(conn, env["company_id"], env["course_id"])
        meeting_a = place_meeting(env, env["section_id"], env["day_type_id"],
                                  env["bell_period_id"], room_id=env["room_id"])
        meeting_b = place_meeting(env, sec_b, env["day_type_id"],
                                  env["bell_period_id"])
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-propose-room"], conn, ns(
            section_meeting_id=meeting_b, room_type=None,
            accessibility_required=None, company_id=env["company_id"]))
        assert is_ok(r)
        assert r["meeting_id"] == meeting_b
        assert r["day_type_id"] == env["day_type_id"]
        assert r["bell_period_id"] == env["bell_period_id"]
        assert r["minimum_capacity_needed"] == 0
        assert r["total_available"] == 1
        assert len(r["suggestions"]) == 1
        only = r["suggestions"][0]
        assert only["id"] == room_b
        assert only["room_number"] == "R102"
        assert only["capacity"] == 40
        assert only["availability_score"] == 92
        assert only["current_booking_count"] == 0
        assert only["facilities"] == []
        assert env["room_id"] not in [s["id"] for s in r["suggestions"]]
        assert snapshot(conn) == before

    def test_refusal_unknown_meeting_writes_nothing(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-propose-room"], conn, ns(
            section_meeting_id="00000000-0000-0000-0000-000000000000",
            room_type=None, accessibility_required=None,
            company_id=env["company_id"]))
        assert is_error(r)
        assert "not found" in r["message"]
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-submit-course-request (effect deepened in test_scheduling.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestSubmitCourseRequestDepth:
    def _submit(self, env, priority=1):
        return call_action(MS_ACTIONS["schedule-submit-course-request"],
                           env["conn"], ns(
            company_id=env["company_id"], student_id=env["student_id"],
            course_id=env["course_id"], academic_term_id=env["term_id"],
            request_priority=priority, is_alternate=0,
            alternate_for_course_id=None,
            prerequisite_override=None, prerequisite_override_by=None,
            prerequisite_override_note=None,
            has_iep_flag=0, submitted_by="counselor", user_id="counselor"))

    def test_refusal_duplicate_writes_nothing(self, based):
        first = self._submit(based)
        assert is_ok(first)
        before = snapshot(based["conn"])
        r = self._submit(based)
        assert is_error(r)
        assert "already has a request" in r["message"]
        assert r["message"].endswith(first["id"])
        assert snapshot(based["conn"]) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-submit-master-schedule
# ══════════════════════════════════════════════════════════════════════════════

class TestSubmitMasterScheduleDepth:
    def test_effect_publishes_and_counts_placed_sections(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        set_master_status(env, "building")
        place_meeting(env, env["section_id"], env["day_type_id"],
                      env["bell_period_id"])
        set_master_status(env, "review")
        before_master = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert before_master["schedule_status"] == "review"
        r = call_action(MS_ACTIONS["schedule-submit-master-schedule"], conn, ns(
            master_schedule_id=env["master_id"],
            published_by="registrar", user_id="registrar"))
        assert is_ok(r)
        assert r["schedule_status"] == "published"
        assert r["sections_scheduled"] == 1
        after = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert after["schedule_status"] == "published"
        assert before_master["schedule_status"] == "review"
        assert after["published_by"] == "registrar"
        assert after["published_at"] != ""
        assert after["locked_at"] == before_master["locked_at"] == ""
        term = read_row(conn, "educlaw_academic_term", env["term_id"])
        assert term["status"] == "active"
        section = read_row(conn, "educlaw_section", env["section_id"])
        assert section["status"] == "open"

    def test_refusal_publish_from_draft_writes_nothing(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-submit-master-schedule"], conn, ns(
            master_schedule_id=env["master_id"],
            published_by="registrar", user_id="registrar"))
        assert is_error(r)
        assert "Can only publish from 'review' or 'building' status" in r["message"]
        assert "current: draft" in r["message"]
        assert read_row(conn, "educlaw_master_schedule",
                        env["master_id"])["schedule_status"] == "draft"
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-update-course-request
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateCourseRequestDepth:
    def _submit(self, env):
        r = call_action(MS_ACTIONS["schedule-submit-course-request"],
                        env["conn"], ns(
            company_id=env["company_id"], student_id=env["student_id"],
            course_id=env["course_id"], academic_term_id=env["term_id"],
            request_priority=1, is_alternate=0, alternate_for_course_id=None,
            prerequisite_override=None, prerequisite_override_by=None,
            prerequisite_override_note=None,
            has_iep_flag=0, submitted_by="counselor", user_id="counselor"))
        assert is_ok(r)
        return r["id"]

    def test_effect_changes_only_given_fields(self, based):
        conn, req_id = based["conn"], self._submit(based)
        before = read_row(conn, "educlaw_course_request", req_id)
        assert before["request_priority"] == 1
        assert before["has_iep_flag"] == 0
        r = call_action(MS_ACTIONS["schedule-update-course-request"], conn, ns(
            course_request_id=req_id, request_priority=5, is_alternate=None,
            alternate_for_course_id=None, has_iep_flag=1))
        assert is_ok(r)
        assert r["updated_fields"] == ["request_priority", "has_iep_flag"]
        after = read_row(conn, "educlaw_course_request", req_id)
        assert after["request_priority"] == 5
        assert after["has_iep_flag"] == 1
        assert after["is_alternate"] == before["is_alternate"] == 0
        assert after["request_status"] == before["request_status"] == "submitted"
        assert after["student_id"] == before["student_id"] == based["student_id"]
        assert after["course_id"] == before["course_id"] == based["course_id"]
        assert after["academic_term_id"] == before["academic_term_id"] == based["term_id"]
        assert after["naming_series"] == before["naming_series"]
        assert after["submitted_by"] == before["submitted_by"] == "counselor"

    def test_refusal_no_fields_writes_nothing(self, based):
        conn, req_id = based["conn"], self._submit(based)
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-update-course-request"], conn, ns(
            course_request_id=req_id, request_priority=None, is_alternate=None,
            alternate_for_course_id=None, has_iep_flag=None))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-update-instructor-constraint
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateInstructorConstraintDepth:
    def _add(self, env):
        r = call_action(RA_ACTIONS["schedule-add-instructor-constraint"],
                        env["conn"], ns(
            instructor_id=env["instructor_id"], company_id=env["company_id"],
            academic_term_id=env["term_id"],
            constraint_type="max_periods_per_day", constraint_value=6,
            constraint_notes="Max 6 periods", priority="soft",
            start_time=None, end_time=None, day_type_id=None, user_id="admin"))
        assert is_ok(r)
        return r["id"]

    def test_effect_changes_value_notes_priority_flag(self, based):
        conn, cid = based["conn"], self._add(based)
        before = read_row(conn, "educlaw_instructor_constraint", cid)
        assert (before["constraint_value"], before["constraint_notes"],
                before["priority"], before["is_active"]) == (6, "Max 6 periods",
                                                             "soft", 1)
        r = call_action(RA_ACTIONS["schedule-update-instructor-constraint"],
                        conn, ns(
            constraint_id=cid, constraint_value=4,
            constraint_notes="Max 4 periods", priority="hard", is_active=0))
        assert is_ok(r)
        assert r["updated_fields"] == ["constraint_value", "constraint_notes",
                                      "priority", "is_active"]
        after = read_row(conn, "educlaw_instructor_constraint", cid)
        assert after["constraint_value"] == 4
        assert after["constraint_notes"] == "Max 4 periods"
        assert after["priority"] == "hard"
        assert after["is_active"] == 0
        assert after["instructor_id"] == before["instructor_id"] == based["instructor_id"]
        assert after["constraint_type"] == before["constraint_type"] == "max_periods_per_day"
        assert after["academic_term_id"] == before["academic_term_id"] == based["term_id"]
        assert after["company_id"] == before["company_id"] == based["company_id"]

    def test_refusal_bad_priority_writes_nothing(self, based):
        conn, cid = based["conn"], self._add(based)
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-update-instructor-constraint"],
                        conn, ns(
            constraint_id=cid, constraint_value=None, constraint_notes=None,
            priority="urgent", is_active=None))
        assert is_error(r)
        assert "--priority must be one of" in r["message"]
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-update-master-schedule
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateMasterScheduleDepth:
    def test_effect_renames_and_advances_status(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        before = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert before["name"] == "Depth Master Schedule"
        assert before["build_notes"] == ""
        assert before["schedule_status"] == "draft"
        r = call_action(MS_ACTIONS["schedule-update-master-schedule"], conn, ns(
            master_schedule_id=env["master_id"], name="Depth MS v2",
            build_notes="rebalanced", schedule_status=None, user_id="admin"))
        assert is_ok(r)
        assert r["updated_fields"] == ["name", "build_notes"]
        mid = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert mid["name"] == "Depth MS v2"
        assert mid["build_notes"] == "rebalanced"
        assert mid["schedule_status"] == "draft"
        r2 = call_action(MS_ACTIONS["schedule-update-master-schedule"], conn, ns(
            master_schedule_id=env["master_id"], name=None, build_notes=None,
            schedule_status="building", user_id="admin"))
        assert is_ok(r2)
        assert r2["updated_fields"] == ["schedule_status"]
        after = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert after["schedule_status"] == "building"
        assert after["name"] == "Depth MS v2"
        assert after["academic_term_id"] == before["academic_term_id"] == env["term_id"]
        assert after["schedule_pattern_id"] == before["schedule_pattern_id"] == env["pattern_id"]
        assert after["company_id"] == before["company_id"] == env["company_id"]
        assert after["total_sections"] == before["total_sections"] == 0

    def test_refusal_bad_transition_writes_nothing(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-update-master-schedule"], conn, ns(
            master_schedule_id=env["master_id"], name=None, build_notes=None,
            schedule_status="published", user_id="admin"))
        assert is_error(r)
        assert "Cannot transition from 'draft' to 'published'" in r["message"]
        assert read_row(conn, "educlaw_master_schedule",
                        env["master_id"])["schedule_status"] == "draft"
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-update-room-swap
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateRoomSwapDepth:
    def _two_room_setup(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        room_b = add_room(conn, env["company_id"])
        sec_b = seed_section(conn, env["company_id"], env["course_id"])
        bell_b = add_bell_period(conn, env["company_id"], env["pattern_id"],
                                 env["day_type_id"])
        meeting_a = place_meeting(env, env["section_id"], env["day_type_id"],
                                  env["bell_period_id"], room_id=env["room_id"])
        meeting_b = place_meeting(env, sec_b, env["day_type_id"], bell_b,
                                  room_id=room_b)
        return meeting_a, meeting_b, room_b

    def test_effect_exchanges_rooms_and_rebooks(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        meeting_a, meeting_b, room_b = self._two_room_setup(ms_env)
        room_a = env["room_id"]
        row_a = read_row(conn, "educlaw_section_meeting", meeting_a)
        row_b = read_row(conn, "educlaw_section_meeting", meeting_b)
        assert row_a["room_id"] == room_a
        assert row_b["room_id"] == room_b
        r = call_action(RA_ACTIONS["schedule-update-room-swap"], conn, ns(
            section_meeting_id=meeting_a, section_meeting_id_b=meeting_b,
            user_id="admin"))
        assert is_ok(r)
        assert r["room_now_in_a"] == room_b
        assert r["room_now_in_b"] == room_a
        new_a = read_row(conn, "educlaw_section_meeting", meeting_a)
        new_b = read_row(conn, "educlaw_section_meeting", meeting_b)
        assert new_a["room_id"] == room_b
        assert new_b["room_id"] == room_a
        assert new_a["day_type_id"] == row_a["day_type_id"]
        assert new_a["bell_period_id"] == row_a["bell_period_id"]
        assert new_a["section_id"] == row_a["section_id"]
        assert new_b["day_type_id"] == row_b["day_type_id"]
        assert new_b["bell_period_id"] == row_b["bell_period_id"]
        assert new_b["section_id"] == row_b["section_id"]
        tbl = Table("educlaw_room_booking")
        cancelled = conn.execute(
            Q.from_(tbl).select(tbl.star).where(
                (Field("section_meeting_id") == P()) &
                (Field("booking_status") == P())).get_sql(),
            (meeting_a, "cancelled")).fetchall()
        assert len(cancelled) == 1
        assert dict(cancelled[0])["cancellation_reason"] == "Room swap"
        assert dict(cancelled[0])["room_id"] == room_a
        live = conn.execute(
            Q.from_(tbl).select(tbl.star).where(
                (Field("section_meeting_id") == P()) &
                (Field("booking_status") == P())).get_sql(),
            (meeting_a, "confirmed")).fetchall()
        assert len(live) == 1
        assert dict(live[0])["room_id"] == room_b
        live_b = conn.execute(
            Q.from_(tbl).select(tbl.star).where(
                (Field("section_meeting_id") == P()) &
                (Field("booking_status") == P())).get_sql(),
            (meeting_b, "confirmed")).fetchall()
        assert len(live_b) == 1
        assert dict(live_b[0])["room_id"] == room_a
        all_rows = conn.execute(
            Q.from_(tbl).select(tbl.star).get_sql()).fetchall()
        assert len(all_rows) == 4

    def test_refusal_cross_master_writes_nothing(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        meeting_a, _meeting_b, _room_b = self._two_room_setup(ms_env)
        term2 = add_second_term(conn, env["company_id"])
        ms2 = call_action(MS_ACTIONS["schedule-create-master-schedule"], conn, ns(
            company_id=env["company_id"], academic_term_id=term2,
            schedule_pattern_id=env["pattern_id"],
            name="Second Master", description=None, build_notes=None,
            user_id="admin"))
        assert is_ok(ms2)
        other_section = seed_section(conn, env["company_id"], env["course_id"])
        other = call_action(MS_ACTIONS["schedule-add-section-meeting"], conn, ns(
            master_schedule_id=ms2["id"], section_id=other_section,
            day_type_id=env["day_type_id"], bell_period_id=env["bell_period_id"],
            room_id=None, instructor_id=None, meeting_type=None,
            meeting_mode=None, notes=None, user_id="admin"))
        assert is_ok(other)
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-update-room-swap"], conn, ns(
            section_meeting_id=meeting_a, section_meeting_id_b=other["id"],
            user_id="admin"))
        assert is_error(r)
        assert "Both meetings must belong to the same master schedule" in r["message"]
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-update-schedule-lock
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateScheduleLockDepth:
    def _published(self, ms_env):
        env = ms_env
        set_master_status(env, "building")
        set_master_status(env, "review")
        r = call_action(MS_ACTIONS["schedule-submit-master-schedule"],
                        env["conn"], ns(
            master_schedule_id=env["master_id"],
            published_by="registrar", user_id="registrar"))
        assert is_ok(r)
        return r

    def test_effect_locks_published_schedule(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        pub = self._published(ms_env)
        before = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert before["schedule_status"] == "published"
        r = call_action(MS_ACTIONS["schedule-update-schedule-lock"], conn, ns(
            master_schedule_id=env["master_id"],
            locked_by="registrar", user_id="registrar"))
        assert is_ok(r)
        assert r["schedule_status"] == "locked"
        assert r["locked_by"] == "registrar"
        after = read_row(conn, "educlaw_master_schedule", env["master_id"])
        assert after["schedule_status"] == "locked"
        assert after["locked_by"] == "registrar"
        assert after["locked_at"] != ""
        assert after["published_by"] == before["published_by"] == "registrar"
        assert after["published_at"] == before["published_at"] == pub["published_at"]

    def test_refusal_lock_from_draft_writes_nothing(self, ms_env):
        env, conn = ms_env, ms_env["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-update-schedule-lock"], conn, ns(
            master_schedule_id=env["master_id"],
            locked_by="registrar", user_id="registrar"))
        assert is_error(r)
        assert "Can only lock a published master schedule" in r["message"]
        assert "current: draft" in r["message"]
        assert read_row(conn, "educlaw_master_schedule",
                        env["master_id"])["schedule_status"] == "draft"
        assert snapshot(conn) == before


# ══════════════════════════════════════════════════════════════════════════════
# schedule-update-schedule-pattern (effect deepened in test_scheduling.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateSchedulePatternDepth:
    def test_refusal_no_fields_writes_nothing(self, base):
        conn = base["conn"]
        add_r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=base["company_id"], name="Refusal Pattern",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35, description=None, notes=None,
            is_active=0, user_id="admin"))
        assert is_ok(add_r)
        before = snapshot(conn)
        before_row = read_row(conn, "educlaw_schedule_pattern", add_r["id"])
        r = call_action(SP_ACTIONS["schedule-update-schedule-pattern"], conn, ns(
            pattern_id=add_r["id"], name=None, description=None, notes=None,
            total_periods_per_cycle=None, user_id="admin"))
        assert is_error(r)
        assert r["message"] == "No fields to update"
        assert read_row(conn, "educlaw_schedule_pattern",
                        add_r["id"]) == before_row
        assert snapshot(conn) == before
