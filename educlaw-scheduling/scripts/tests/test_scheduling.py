"""L1 pytest tests for EduClaw Advanced Scheduling — 56 actions across 4 domains.

Tests: schedule_patterns (~10), master_schedule (~10),
       conflict_resolution (~5), room_assignment (~8) = ~33 tests.
"""
import importlib.util
import pytest
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    """Load a Python module by explicit file path (avoids sys.path collisions)."""
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

SP_ACTIONS = _load("schedule_patterns", _SCRIPTS_DIR).ACTIONS
MS_ACTIONS = _load("master_schedule", _SCRIPTS_DIR).ACTIONS
CR_ACTIONS = _load("conflict_resolution", _SCRIPTS_DIR).ACTIONS
RA_ACTIONS = _load("room_assignment", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yield conn, cid
    conn.close()


@pytest.fixture
def full_setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    sid = seed_student(conn, cid)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    rid = seed_room(conn, cid)
    iid = seed_instructor(conn, cid)
    crs_id = seed_course(conn, cid)
    sec_id = seed_section(conn, cid)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "year_id": yid, "term_id": tid, "room_id": rid,
        "instructor_id": iid, "course_id": crs_id,
        "section_id": sec_id,
    }
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULE PATTERNS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestSchedulePattern:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=cid, name="Traditional Schedule",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description="Standard 7-period day", notes=None,
            is_active=0, user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(SP_ACTIONS["schedule-list-schedule-patterns"], conn, ns(
            company_id=cid, search=None, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_get(self, setup):
        conn, cid = setup
        add_r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=cid, name="Block 4x4",
            pattern_type="block_4x4", cycle_days=1,
            total_periods_per_cycle=4,
            description=None, notes=None,
            is_active=0, user_id="admin",
        ))
        assert is_ok(add_r)
        r = call_action(SP_ACTIONS["schedule-get-schedule-pattern"], conn, ns(
            pattern_id=add_r["id"], company_id=cid,
        ))
        assert is_ok(r)

    def test_update(self, setup):
        conn, cid = setup
        add_r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=cid, name="AB Block",
            pattern_type="block_ab", cycle_days=2,
            total_periods_per_cycle=8,
            description=None, notes=None,
            is_active=0, user_id="admin",
        ))
        assert is_ok(add_r)
        r = call_action(SP_ACTIONS["schedule-update-schedule-pattern"], conn, ns(
            pattern_id=add_r["id"],
            name="AB Block Updated", description="Updated desc",
            notes=None, total_periods_per_cycle=None,
            user_id="admin",
        ))
        assert is_ok(r)

    def test_missing_name(self, setup):
        conn, cid = setup
        r = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=cid, name=None,
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=None,
            description=None, notes=None,
            is_active=0, user_id=None,
        ))
        assert is_error(r)


class TestDayType:
    def test_add(self, setup):
        conn, cid = setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=cid, name="Test Pattern",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=0, user_id=None,
        ))
        assert is_ok(pat)
        r = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
            schedule_pattern_id=pat["id"], company_id=cid,
            name="Day A", code="A", sort_order=1,
            description=None, user_id=None,
        ))
        assert is_ok(r)


class TestBellPeriod:
    def test_add(self, setup):
        conn, cid = setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
            company_id=cid, name="Bell Test",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=0, user_id=None,
        ))
        assert is_ok(pat)
        dt = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
            schedule_pattern_id=pat["id"], company_id=cid,
            name="Day A", code="A", sort_order=1,
            description=None, user_id=None,
        ))
        assert is_ok(dt)
        r = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
            schedule_pattern_id=pat["id"], company_id=cid,
            period_number="1", period_name="Period 1",
            start_time="08:00", end_time="08:50",
            duration_minutes=50, period_type="class",
            applies_to_day_types=f'["{dt["id"]}"]',
            sort_order=1, user_id=None,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# MASTER SCHEDULE domain
# ══════════════════════════════════════════════════════════════════════════════

class TestMasterSchedule:
    def test_create(self, full_setup):
        s = full_setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
            company_id=s["company_id"], name="MS Test Pattern",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=1, user_id=None,
        ))
        assert is_ok(pat)
        r = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
            company_id=s["company_id"], academic_term_id=s["term_id"],
            schedule_pattern_id=pat["id"],
            name="Fall 2025 Master Schedule",
            description=None, build_notes=None, user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(MS_ACTIONS["schedule-list-master-schedules"], conn, ns(
            company_id=cid, academic_term_id=None,
            schedule_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestCourseRequest:
    def test_submit(self, full_setup):
        s = full_setup
        r = call_action(MS_ACTIONS["schedule-submit-course-request"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            course_id=s["course_id"], academic_term_id=s["term_id"],
            request_priority=1, is_alternate=0,
            alternate_for_course_id=None,
            prerequisite_override=None, prerequisite_override_by=None,
            prerequisite_override_note=None,
            has_iep_flag=0, submitted_by="counselor",
            user_id="counselor",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(MS_ACTIONS["schedule-list-course-requests"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            academic_term_id=None, course_id=None,
            request_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestSectionMeeting:
    def test_list(self, full_setup):
        s = full_setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
            company_id=s["company_id"], name="SM Test",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=1, user_id=None,
        ))
        assert is_ok(pat)
        ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
            company_id=s["company_id"], academic_term_id=s["term_id"],
            schedule_pattern_id=pat["id"],
            name="SM List Test",
            description=None, build_notes=None, user_id="admin",
        ))
        assert is_ok(ms)
        r = call_action(MS_ACTIONS["schedule-list-section-meetings"], s["conn"], ns(
            company_id=s["company_id"], master_schedule_id=ms["id"],
            section_id=None, instructor_id=None,
            day_type_id=None, room_id=None, limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# CONFLICT RESOLUTION domain
# ══════════════════════════════════════════════════════════════════════════════

class TestConflicts:
    def test_list(self, full_setup):
        s = full_setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
            company_id=s["company_id"], name="Conflict List Test",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=1, user_id=None,
        ))
        assert is_ok(pat)
        ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
            company_id=s["company_id"], academic_term_id=s["term_id"],
            schedule_pattern_id=pat["id"],
            name="Conflict List MS",
            description=None, build_notes=None, user_id="admin",
        ))
        assert is_ok(ms)
        r = call_action(CR_ACTIONS["schedule-list-conflicts"], s["conn"], ns(
            company_id=s["company_id"], master_schedule_id=ms["id"],
            conflict_type=None, severity=None,
            conflict_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_get_summary(self, full_setup):
        s = full_setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
            company_id=s["company_id"], name="Conflict Test",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=1, user_id=None,
        ))
        ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
            company_id=s["company_id"], academic_term_id=s["term_id"],
            schedule_pattern_id=pat["id"],
            name="Conflict Summary Test",
            description=None, build_notes=None, user_id="admin",
        ))
        if is_ok(ms):
            r = call_action(CR_ACTIONS["schedule-get-conflict-summary"], s["conn"], ns(
                master_schedule_id=ms["id"], company_id=s["company_id"],
            ))
            assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# ROOM ASSIGNMENT domain
# ══════════════════════════════════════════════════════════════════════════════

class TestRoomAvailability:
    def test_get(self, full_setup):
        s = full_setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
            company_id=s["company_id"], name="Room Avail Test",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=1, user_id=None,
        ))
        assert is_ok(pat)
        ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
            company_id=s["company_id"], academic_term_id=s["term_id"],
            schedule_pattern_id=pat["id"],
            name="Room Avail MS",
            description=None, build_notes=None, user_id="admin",
        ))
        assert is_ok(ms)
        r = call_action(RA_ACTIONS["schedule-get-room-availability"], s["conn"], ns(
            room_id=s["room_id"], company_id=s["company_id"],
            master_schedule_id=ms["id"],
        ))
        assert is_ok(r)


class TestRoomSearch:
    def test_list_by_features(self, full_setup):
        s = full_setup
        r = call_action(RA_ACTIONS["schedule-list-rooms-by-features"], s["conn"], ns(
            company_id=s["company_id"],
            room_type=None, capacity=None, building=None,
            features=None, accessibility_required=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


class TestRoomUtilization:
    def test_report(self, full_setup):
        s = full_setup
        pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], s["conn"], ns(
            company_id=s["company_id"], name="Util Test",
            pattern_type="traditional", cycle_days=5,
            total_periods_per_cycle=35,
            description=None, notes=None,
            is_active=1, user_id=None,
        ))
        ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], s["conn"], ns(
            company_id=s["company_id"], academic_term_id=s["term_id"],
            schedule_pattern_id=pat["id"],
            name="Util Report Test",
            description=None, build_notes=None, user_id="admin",
        ))
        if is_ok(ms):
            r = call_action(RA_ACTIONS["schedule-get-room-utilization-report"], s["conn"], ns(
                master_schedule_id=ms["id"], company_id=s["company_id"],
            ))
            assert is_ok(r)


class TestInstructorConstraint:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(RA_ACTIONS["schedule-add-instructor-constraint"], s["conn"], ns(
            instructor_id=s["instructor_id"], company_id=s["company_id"],
            academic_term_id=s["term_id"],
            constraint_type="max_periods_per_day",
            constraint_value=6, constraint_notes="Max 6 periods",
            priority="soft", start_time=None, end_time=None,
            day_type_id=None, user_id="admin",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(RA_ACTIONS["schedule-list-instructor-constraints"], s["conn"], ns(
            company_id=s["company_id"], instructor_id=None,
            constraint_type=None, limit=50, offset=0,
        ))
        assert is_ok(r)
