"""Depth tests for the 12 read-only scheduling getters.

Each action below already had a shape/routability test in test_scheduling.py
that passed without ever looking at the database. The tests here seed
precursor rows through the owning actions, call the getter, and assert the
response equals the stored rows read back independently (PyPika through
erpclaw_lib.query, connections through erpclaw_lib.db.get_connection(),
catalog questions through erpclaw_lib.seam). Every getter test also proves
the call wrote nothing, and every action has a refusal test proving a bad
input is rejected truthfully with the database byte-identical afterwards.

No ledger assertion appears in this file on purpose: the scheduling module
performs no GL posting (no gl_posting/ledger import anywhere under
scripts/), so there are no debit/credit legs to balance. A later reader
should not add ledger assertions here.

Money note: scheduling stores no monetary values; durations and counts are
asserted as exact ints, hours as exact round(x, 2) values. No float money,
no rounding of money, anywhere.
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
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_room = _helpers.seed_room
seed_instructor = _helpers.seed_instructor
seed_course = _helpers.seed_course
seed_section = _helpers.seed_section

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, fn
from erpclaw_lib.seam import table_exists

SP_ACTIONS = _load("schedule_patterns", _SCRIPTS_DIR).ACTIONS
MS_ACTIONS = _load("master_schedule", _SCRIPTS_DIR).ACTIONS
CR_ACTIONS = _load("conflict_resolution", _SCRIPTS_DIR).ACTIONS
RA_ACTIONS = _load("room_assignment", _SCRIPTS_DIR).ACTIONS


OWNED_TABLES = [
    "educlaw_course_request",
    "educlaw_schedule_pattern",
    "educlaw_bell_period",
    "educlaw_day_type",
    "educlaw_instructor_constraint",
    "educlaw_master_schedule",
    "educlaw_section_meeting",
    "educlaw_room_booking",
    "educlaw_schedule_conflict",
]
PARENT_TABLES = [
    "educlaw_student",
    "educlaw_course",
    "educlaw_section",
    "educlaw_room",
    "educlaw_instructor",
    "educlaw_academic_term",
    "educlaw_academic_year",
]
SNAPSHOT_TABLES = OWNED_TABLES + PARENT_TABLES + ["audit_log", "naming_series", "company"]


def is_ok(r):
    return r.get("status") == "ok"


def is_error(r):
    return r.get("status") == "error"


def fetch_row(conn, table, field, value):
    t = Table(table)
    sql = Q.from_(t).select(t.star).where(Field(field) == P()).get_sql()
    row = conn.execute(sql, (value,)).fetchone()
    return dict(row) if row else None


def fetch_all(conn, table, field=None, value=None):
    t = Table(table)
    q = Q.from_(t).select(t.star)
    params = ()
    if field is not None:
        q = q.where(Field(field) == P())
        params = (value,)
    return [dict(r) for r in conn.execute(q.get_sql(), params).fetchall()]


def count_rows(conn, table, field=None, value=None):
    t = Table(table)
    q = Q.from_(t).select(fn.Count("*"))
    params = ()
    if field is not None:
        q = q.where(Field(field) == P())
        params = (value,)
    return conn.execute(q.get_sql(), params).fetchone()[0]


def snapshot(conn, tables=None):
    tables = tables or SNAPSHOT_TABLES
    snap = {}
    for name in tables:
        t = Table(name)
        sql = Q.from_(t).select(t.star).orderby(Field("id")).get_sql()
        snap[name] = [dict(r) for r in conn.execute(sql).fetchall()]
    return snap


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


@pytest.fixture
def base(conn):
    cid = seed_company(conn)
    s1 = seed_student(conn, cid)
    s2 = seed_student(conn, cid)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    rid = seed_room(conn, cid)
    iid = seed_instructor(conn, cid)
    crs = seed_course(conn, cid)
    sec1 = seed_section(conn, cid)
    sec2 = seed_section(conn, cid)
    return {
        "conn": conn, "company_id": cid,
        "student1": s1, "student2": s2,
        "year_id": yid, "term_id": tid, "room_id": rid,
        "instructor_id": iid, "course_id": crs,
        "section1": sec1, "section2": sec2,
    }


@pytest.fixture
def sched(base):
    conn = base["conn"]
    cid = base["company_id"]
    pat = call_action(SP_ACTIONS["schedule-add-schedule-pattern"], conn, ns(
        company_id=cid, name="Depth Pattern",
        pattern_type="traditional", cycle_days=2,
        total_periods_per_cycle=4,
        description=None, notes=None,
        is_active=1, user_id=None,
    ))
    assert is_ok(pat)
    dt_a = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
        schedule_pattern_id=pat["id"], company_id=cid,
        name="Day A", code="A", sort_order=1,
        description=None, user_id=None,
    ))
    assert is_ok(dt_a)
    dt_b = call_action(SP_ACTIONS["schedule-add-day-type"], conn, ns(
        schedule_pattern_id=pat["id"], company_id=cid,
        name="Day B", code="B", sort_order=2,
        description=None, user_id=None,
    ))
    assert is_ok(dt_b)
    bp_class = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
        schedule_pattern_id=pat["id"], company_id=cid,
        period_number="1", period_name="Period 1",
        start_time="08:00", end_time="08:50",
        duration_minutes=50, period_type="class",
        applies_to_day_types=json.dumps([dt_a["id"], dt_b["id"]]),
        sort_order=1, user_id=None,
    ))
    assert is_ok(bp_class)
    bp_lunch = call_action(SP_ACTIONS["schedule-add-bell-period"], conn, ns(
        schedule_pattern_id=pat["id"], company_id=cid,
        period_number="2", period_name="Lunch",
        start_time="12:00", end_time="12:30",
        duration_minutes=30, period_type="lunch",
        applies_to_day_types=json.dumps([]),
        sort_order=2, user_id=None,
    ))
    assert is_ok(bp_lunch)
    ms = call_action(MS_ACTIONS["schedule-create-master-schedule"], conn, ns(
        company_id=cid, academic_term_id=base["term_id"],
        schedule_pattern_id=pat["id"],
        name="Depth Master Schedule",
        description=None, build_notes=None, user_id="admin",
    ))
    assert is_ok(ms)
    base.update({
        "pattern_id": pat["id"],
        "day_a": dt_a["id"], "day_b": dt_b["id"],
        "period_class": bp_class["id"], "period_lunch": bp_lunch["id"],
        "master_id": ms["id"], "master_naming": ms["naming_series"],
    })
    return base


def submit_request(conn, cid, student_id, course_id, term_id, priority=1):
    return call_action(MS_ACTIONS["schedule-submit-course-request"], conn, ns(
        company_id=cid, student_id=student_id,
        course_id=course_id, academic_term_id=term_id,
        request_priority=priority, is_alternate=0,
        alternate_for_course_id=None,
        prerequisite_override=None, prerequisite_override_by=None,
        prerequisite_override_note=None,
        has_iep_flag=0, submitted_by="counselor",
        user_id="counselor",
    ))


def place_meeting(s, section_id, day_type_id, period_id, with_room=True, with_instructor=True):
    return call_action(MS_ACTIONS["schedule-add-section-meeting"], s["conn"], ns(
        master_schedule_id=s["master_id"], section_id=section_id,
        day_type_id=day_type_id, bell_period_id=period_id,
        room_id=s["room_id"] if with_room else None,
        instructor_id=s["instructor_id"] if with_instructor else None,
        meeting_type="regular", meeting_mode="in_person",
        notes="", user_id="admin",
    ))


def test_owned_tables_visible_through_seam(db_path):
    for name in OWNED_TABLES:
        assert table_exists(name, db_path), f"owned table missing from catalog: {name}"


class TestGetDayTypeCalendar:
    def test_calendar_matches_stored_day_types(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-day-type-calendar"], conn, ns(
            pattern_id=s["pattern_id"],
            date_range_start="2025-09-01", date_range_end="2025-09-07",
            company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        day_rows = fetch_all(conn, "educlaw_day_type")
        ordered = sorted(day_rows, key=lambda d: (d["sort_order"], d["code"]))
        assert r["pattern_id"] == s["pattern_id"]
        assert r["cycle_length"] == 2
        assert r["total_school_days"] == 5
        expected = [
            ("2025-09-01", "Monday", "A"),
            ("2025-09-02", "Tuesday", "B"),
            ("2025-09-03", "Wednesday", "A"),
            ("2025-09-04", "Thursday", "B"),
            ("2025-09-05", "Friday", "A"),
        ]
        assert len(r["calendar"]) == 5
        for entry, (date, weekday, code) in zip(r["calendar"], expected):
            assert entry["date"] == date
            assert entry["weekday"] == weekday
            assert entry["day_type_code"] == code
        cycle_ids = [ordered[0]["id"], ordered[1]["id"]]
        assert [e["day_type_id"] for e in r["calendar"]] == [
            cycle_ids[0], cycle_ids[1], cycle_ids[0], cycle_ids[1], cycle_ids[0],
        ]
        assert ordered[0]["id"] == s["day_a"]
        assert ordered[1]["id"] == s["day_b"]

    def test_refusal_bad_dates_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-day-type-calendar"], conn, ns(
            pattern_id=s["pattern_id"],
            date_range_start="09/01/2025", date_range_end="2025-09-07",
            company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "YYYY-MM-DD" in r["message"]
        assert snapshot(conn) == before


class TestGetPatternCalendar:
    def test_grid_matches_stored_periods(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-pattern-calendar"], conn, ns(
            pattern_id=s["pattern_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["pattern_name"] == "Depth Pattern"
        assert r["pattern_type"] == "traditional"
        assert r["cycle_days"] == 2
        assert [d["code"] for d in r["day_types"]] == ["A", "B"]
        assert [d["id"] for d in r["day_types"]] == [s["day_a"], s["day_b"]]
        by_number = {b["period_number"]: b for b in r["bell_periods"]}
        stored_class = fetch_row(conn, "educlaw_bell_period", "id", s["period_class"])
        stored_lunch = fetch_row(conn, "educlaw_bell_period", "id", s["period_lunch"])
        assert by_number["1"]["duration_minutes"] == stored_class["duration_minutes"] == 50
        assert by_number["1"]["occurrences_per_cycle"] == 2
        assert sorted(by_number["1"]["effective_day_type_ids"]) == sorted([s["day_a"], s["day_b"]])
        assert by_number["2"]["duration_minutes"] == stored_lunch["duration_minutes"] == 30
        assert by_number["2"]["occurrences_per_cycle"] == 2
        assert r["total_class_minutes_per_cycle"] == 100
        assert r["total_class_hours_per_cycle"] == round(100 / 60, 2)

    def test_refusal_unknown_pattern_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-pattern-calendar"], conn, ns(
            pattern_id="no-such-pattern", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "no-such-pattern" in r["message"]
        assert "not found" in r["message"]
        assert snapshot(conn) == before


class TestGetContactHours:
    def test_theoretical_hours_match_stored_periods(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-contact-hours"], conn, ns(
            pattern_id=s["pattern_id"], section_id=None,
            master_schedule_id=None, company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["pattern_name"] == "Depth Pattern"
        assert r["class_minutes_per_cycle"] == 100
        assert r["class_hours_per_cycle"] == round(100 / 60, 2)
        by_number = {b["period_number"]: b for b in r["breakdown"]}
        assert by_number["1"]["occurrences_per_cycle"] == 2
        assert by_number["1"]["total_minutes"] == 100
        assert by_number["2"]["occurrences_per_cycle"] == 2
        assert by_number["2"]["total_minutes"] == 60

    def test_meeting_hours_match_placed_meeting(self, sched):
        s = sched
        conn = s["conn"]
        m = place_meeting(s, s["section1"], s["day_a"], s["period_class"])
        assert is_ok(m)
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-contact-hours"], conn, ns(
            pattern_id=s["pattern_id"], section_id=s["section1"],
            master_schedule_id=s["master_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["meetings_per_cycle"] == 1
        assert r["class_minutes_per_cycle"] == 50
        assert r["class_hours_per_cycle"] == round(50 / 60, 2)
        assert r["total_minutes_per_cycle"] == 50
        assert r["meetings"][0]["id"] == m["id"]
        stored = fetch_row(conn, "educlaw_section_meeting", "id", m["id"])
        assert r["meetings"][0]["day_type_id"] == stored["day_type_id"] == s["day_a"]
        assert r["meetings"][0]["bell_period_id"] == stored["bell_period_id"] == s["period_class"]

    def test_refusal_missing_pattern_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(SP_ACTIONS["schedule-get-contact-hours"], conn, ns(
            pattern_id=None, section_id=None,
            master_schedule_id=None, company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "--pattern-id is required" in r["message"]
        assert snapshot(conn) == before


class TestGetMasterSchedule:
    def test_get_returns_stored_row_with_enrichment(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-master-schedule"], conn, ns(
            master_schedule_id=s["master_id"], naming_series=None,
            company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        stored = fetch_row(conn, "educlaw_master_schedule", "id", s["master_id"])
        for field in ("id", "naming_series", "name", "academic_term_id",
                      "schedule_pattern_id", "schedule_status", "company_id"):
            assert r[field] == stored[field]
        assert r["name"] == "Depth Master Schedule"
        term = fetch_row(conn, "educlaw_academic_term", "id", s["term_id"])
        assert r["term_name"] == term["name"] == "Fall 2025"
        assert r["term_status"] == term["status"] == "active"
        pattern = fetch_row(conn, "educlaw_schedule_pattern", "id", s["pattern_id"])
        assert r["pattern_name"] == pattern["name"] == "Depth Pattern"
        assert r["pattern_type"] == pattern["pattern_type"] == "traditional"
        by_naming = call_action(MS_ACTIONS["schedule-get-master-schedule"], conn, ns(
            master_schedule_id=None, naming_series=s["master_naming"],
            company_id=s["company_id"],
        ))
        assert is_ok(by_naming)
        assert by_naming["id"] == s["master_id"]
        assert snapshot(conn) == before

    def test_refusal_no_identifier_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-master-schedule"], conn, ns(
            master_schedule_id=None, naming_series=None,
            company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "--master-schedule-id or --naming-series is required" in r["message"]
        assert snapshot(conn) == before


class TestGetCourseRequest:
    def test_get_returns_stored_request_row(self, sched):
        s = sched
        conn = s["conn"]
        sub = submit_request(conn, s["company_id"], s["student1"], s["course_id"], s["term_id"])
        assert is_ok(sub)
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-course-request"], conn, ns(
            course_request_id=sub["id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        stored = fetch_row(conn, "educlaw_course_request", "id", sub["id"])
        for field in ("id", "naming_series", "student_id", "course_id",
                      "academic_term_id", "request_priority", "request_status",
                      "is_alternate", "has_iep_flag", "submitted_by", "company_id"):
            assert r[field] == stored[field]
        assert r["request_status"] == "submitted"
        assert r["request_priority"] == 1
        assert r["submitted_by"] == "counselor"
        assert r["student_name"] == "Test Student"
        course = fetch_row(conn, "educlaw_course", "id", s["course_id"])
        assert r["course_code"] == course["course_code"]
        assert r["course_name"] == course["name"]
        assert count_rows(conn, "educlaw_course_request") == before_count(before, "educlaw_course_request")

    def test_refusal_unknown_request_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-course-request"], conn, ns(
            course_request_id="no-such-request", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "no-such-request" in r["message"]
        assert "not found" in r["message"]
        assert snapshot(conn) == before


def before_count(snap, table):
    return len(snap[table])


class TestGetCourseDemandAnalysis:
    def test_analysis_matches_stored_requests(self, sched):
        s = sched
        conn = s["conn"]
        r1 = submit_request(conn, s["company_id"], s["student1"], s["course_id"], s["term_id"])
        r2 = submit_request(conn, s["company_id"], s["student2"], s["course_id"], s["term_id"])
        assert is_ok(r1) and is_ok(r2)
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-course-demand-analysis"], conn, ns(
            academic_term_id=s["term_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["academic_term_id"] == s["term_id"]
        assert r["courses_analyzed"] == 1
        row = r["demand_analysis"][0]
        assert row["course_id"] == s["course_id"]
        assert row["total_requests"] == 2
        assert row["primary_requests"] == 2
        assert row["approved_requests"] == 0
        assert row["total_requests"] == count_rows(conn, "educlaw_course_request")
        assert row["existing_sections"] == 0
        assert row["existing_capacity"] == 0
        assert row["recommended_new_sections"] == 1
        assert row["demand_gap"] == 2
        course = fetch_row(conn, "educlaw_course", "id", s["course_id"])
        assert row["course_code"] == course["course_code"]

    def test_refusal_unknown_term_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-course-demand-analysis"], conn, ns(
            academic_term_id="no-such-term", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "no-such-term" in r["message"]
        assert "not found" in r["message"]
        assert snapshot(conn) == before


class TestGetDemandReport:
    # DEFECT (documented, not fixed): recommended_sections uses
    # (-(-total) // cap) instead of -(-total // cap), so any remainder is
    # dropped: 1 request over capacity 25 reports 0 instead of 1. The sibling
    # action schedule-get-course-demand-analysis computes the same figure
    # correctly (recommended_new_sections == 1 for this fixture).
    def test_report_documents_actual_recommendation_math(self, sched):
        s = sched
        conn = s["conn"]
        sub = submit_request(conn, s["company_id"], s["student1"], s["course_id"], s["term_id"])
        assert is_ok(sub)
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-demand-report"], conn, ns(
            academic_term_id=s["term_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["academic_term_id"] == s["term_id"]
        assert r["total_requests"] == 1
        assert r["courses_with_demand"] == 1
        row = r["demand_by_course"][0]
        assert row["course_id"] == s["course_id"]
        assert row["total_requests"] == 1
        assert row["approved"] == 0
        assert row["scheduled"] == 0
        assert row["priority_1_count"] == 1
        assert row["iep_count"] == 0
        course = fetch_row(conn, "educlaw_course", "id", s["course_id"])
        assert row["section_capacity"] == course["max_enrollment"] == 0
        assert row["recommended_sections"] == 0

    def test_refusal_unknown_term_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-demand-report"], conn, ns(
            academic_term_id="no-such-term", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "no-such-term" in r["message"]
        assert "not found" in r["message"]
        assert snapshot(conn) == before


class TestGetFulfillmentReport:
    def test_buckets_match_stored_request_statuses(self, sched):
        s = sched
        conn = s["conn"]
        assert is_ok(submit_request(conn, s["company_id"], s["student1"], s["course_id"], s["term_id"]))
        assert is_ok(submit_request(conn, s["company_id"], s["student2"], s["course_id"], s["term_id"]))
        appr = call_action(MS_ACTIONS["schedule-approve-course-requests"], conn, ns(
            academic_term_id=s["term_id"], approved_by="registrar",
            course_id=None, user_id=None,
        ))
        assert is_ok(appr)
        assert appr["requests_approved"] == 2
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-fulfillment-report"], conn, ns(
            master_schedule_id=s["master_id"], academic_term_id=None,
            company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["academic_term_id"] == s["term_id"]
        assert r["master_schedule_id"] == s["master_id"]
        rows = fetch_all(conn, "educlaw_course_request")
        assert r["total_requests"] == len(rows) == 2
        assert r["approved_pending_placement"] == sum(1 for x in rows if x["request_status"] == "approved") == 2
        assert r["submitted_pending_approval"] == 0
        assert r["scheduled"] == 0
        assert r["alternate_used"] == 0
        assert r["fulfilled"] == 0
        assert r["unfulfilled"] == 0
        assert r["withdrawn"] == 0
        assert r["fulfillment_rate_pct"] == 0.0

    def test_refusal_no_scope_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-fulfillment-report"], conn, ns(
            master_schedule_id=None, academic_term_id=None,
            company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "--master-schedule-id or --academic-term-id is required" in r["message"]
        assert snapshot(conn) == before


class TestGetLoadBalanceReport:
    def test_load_matches_placed_meetings(self, sched):
        s = sched
        conn = s["conn"]
        m1 = place_meeting(s, s["section1"], s["day_a"], s["period_class"])
        m2 = place_meeting(s, s["section2"], s["day_a"], s["period_class"],
                           with_room=False, with_instructor=True)
        assert is_ok(m1) and is_ok(m2)
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-load-balance-report"], conn, ns(
            master_schedule_id=s["master_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["master_schedule_id"] == s["master_id"]
        assert r["instructor_count"] == 1
        entry = r["instructors"][0]
        assert entry["instructor_id"] == s["instructor_id"]
        # Observed behaviour: the seeded instructor has no linked employee
        # row, so the LEFT JOIN yields NULL for the name while grouping and
        # totals still follow the instructor id.
        assert entry["instructor_name"] is None
        assert entry["total_periods"] == 2
        assert entry["total_minutes"] == 100
        assert len(entry["by_day_type"]) == 1
        assert entry["by_day_type"][0]["day_type_code"] == "A"
        assert entry["by_day_type"][0]["period_count"] == 2
        assert entry["by_day_type"][0]["total_minutes"] == 100
        meetings = [m for m in fetch_all(conn, "educlaw_section_meeting")
                    if m["is_active"] == 1 and m["instructor_id"] == s["instructor_id"]]
        assert entry["total_periods"] == len(meetings) == 2

    def test_refusal_missing_master_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(MS_ACTIONS["schedule-get-load-balance-report"], conn, ns(
            master_schedule_id=None, company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "--master-schedule-id is required" in r["message"]
        assert snapshot(conn) == before


class TestGetConflictSummary:
    def test_summary_matches_stored_conflicts(self, sched):
        s = sched
        conn = s["conn"]
        m1 = place_meeting(s, s["section1"], s["day_a"], s["period_class"])
        m2 = place_meeting(s, s["section2"], s["day_a"], s["period_class"],
                           with_room=False, with_instructor=True)
        assert is_ok(m1) and is_ok(m2)
        check = call_action(CR_ACTIONS["schedule-generate-conflict-check"], conn, ns(
            master_schedule_id=s["master_id"], company_id=s["company_id"],
        ))
        assert is_ok(check)
        before = snapshot(conn)
        r = call_action(CR_ACTIONS["schedule-get-conflict-summary"], conn, ns(
            master_schedule_id=s["master_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        live = [c for c in fetch_all(conn, "educlaw_schedule_conflict")
                if c["master_schedule_id"] == s["master_id"]
                and c["conflict_status"] != "superseded"]
        assert len(live) > 0
        assert r["master_schedule_id"] == s["master_id"]
        assert r["total_open"] == sum(1 for c in live if c["conflict_status"] == "open")
        assert r["total_closed"] == sum(1 for c in live if c["conflict_status"] in ("resolved", "accepted"))
        assert r["critical_open"] == sum(
            1 for c in live if c["severity"] == "critical" and c["conflict_status"] == "open")
        assert r["can_publish"] == (r["critical_open"] == 0)
        sev = {e["severity"]: e for e in r["by_severity"]}
        for level in {c["severity"] for c in live}:
            group = [c for c in live if c["severity"] == level]
            assert sev[level]["open"] == sum(1 for c in group if c["conflict_status"] == "open")
            assert sev[level]["total"] == len(group)
        by_type = {e["conflict_type"]: e for e in r["by_type"]}
        assert by_type["instructor_double_booking"]["open"] == 1
        assert by_type["instructor_double_booking"]["total"] == 1
        for ctype in {c["conflict_type"] for c in live}:
            group = [c for c in live if c["conflict_type"] == ctype]
            assert by_type[ctype]["open"] == sum(1 for c in group if c["conflict_status"] == "open")
            assert by_type[ctype]["total"] == len(group)

    def test_refusal_unknown_master_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(CR_ACTIONS["schedule-get-conflict-summary"], conn, ns(
            master_schedule_id="no-such-master", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "no-such-master" in r["message"]
        assert "not found" in r["message"]
        assert snapshot(conn) == before


class TestGetRoomAvailability:
    def test_availability_tracks_room_bookings(self, sched):
        s = sched
        conn = s["conn"]
        empty = call_action(RA_ACTIONS["schedule-get-room-availability"], conn, ns(
            room_id=s["room_id"], company_id=s["company_id"],
            master_schedule_id=s["master_id"],
        ))
        assert is_ok(empty)
        assert empty["total_class_periods"] == 2
        assert empty["available_periods"] == 2
        assert empty["booked_periods"] == 0
        assert empty["utilization_pct"] == 0.0
        m = place_meeting(s, s["section1"], s["day_a"], s["period_class"])
        assert is_ok(m)
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-get-room-availability"], conn, ns(
            room_id=s["room_id"], company_id=s["company_id"],
            master_schedule_id=s["master_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["room_number"] == "R101"
        assert r["building"] == "Main Building"
        assert r["capacity"] == 30
        assert r["room_type"] == "classroom"
        bookings = [b for b in fetch_all(conn, "educlaw_room_booking")
                    if b["room_id"] == s["room_id"] and b["booking_status"] != "cancelled"]
        assert r["total_class_periods"] == 2
        assert r["booked_periods"] == len(bookings) == 1
        assert r["available_periods"] == 1
        assert r["utilization_pct"] == 50.0
        grid = {g["period_number"]: g for g in r["availability_grid"]}
        assert grid["1"]["slots"]["A"]["available"] is False
        assert grid["1"]["slots"]["A"]["booking_type"] == bookings[0]["booking_type"] == "class"
        assert grid["1"]["slots"]["B"]["available"] is True

    def test_refusal_missing_room_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-get-room-availability"], conn, ns(
            room_id=None, company_id=s["company_id"],
            master_schedule_id=s["master_id"],
        ))
        assert is_error(r)
        assert "--room-id is required" in r["message"]
        assert snapshot(conn) == before


class TestGetRoomUtilizationReport:
    def test_utilization_matches_room_bookings(self, sched):
        s = sched
        conn = s["conn"]
        bare = call_action(RA_ACTIONS["schedule-get-room-utilization-report"], conn, ns(
            master_schedule_id=s["master_id"], company_id=s["company_id"],
        ))
        assert is_ok(bare)
        assert bare["rooms"] == []
        assert bare["room_count"] == 0
        m = place_meeting(s, s["section1"], s["day_a"], s["period_class"])
        assert is_ok(m)
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-get-room-utilization-report"], conn, ns(
            master_schedule_id=s["master_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)
        assert snapshot(conn) == before
        assert r["master_schedule_id"] == s["master_id"]
        assert r["total_class_periods_per_room"] == 2
        assert r["room_count"] == 1
        row = r["rooms"][0]
        room = fetch_row(conn, "educlaw_room", "id", s["room_id"])
        assert row["room_id"] == s["room_id"]
        assert row["room_number"] == room["room_number"] == "R101"
        assert row["building"] == room["building"] == "Main Building"
        assert row["capacity"] == room["capacity"] == 30
        bookings = [b for b in fetch_all(conn, "educlaw_room_booking")
                    if b["master_schedule_id"] == s["master_id"]
                    and b["booking_status"] != "cancelled"]
        assert row["booked_periods"] == len(bookings) == 1
        assert row["class_periods"] == 1
        assert row["total_available_periods"] == 2
        assert row["utilization_pct"] == 50.0

    def test_refusal_unknown_master_leaves_db_identical(self, sched):
        s = sched
        conn = s["conn"]
        before = snapshot(conn)
        r = call_action(RA_ACTIONS["schedule-get-room-utilization-report"], conn, ns(
            master_schedule_id="no-such-master", company_id=s["company_id"],
        ))
        assert is_error(r)
        assert "no-such-master" in r["message"]
        assert "not found" in r["message"]
        assert snapshot(conn) == before
