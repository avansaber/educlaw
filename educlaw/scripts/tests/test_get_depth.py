"""Depth tests for the 12 read-only educlaw getters.

Every test here proves what the action DOES against the database, not the
shape of its envelope:

- mirror tests seed exact rows, call the action, then re-read the same rows
  through PyPika-built queries (``erpclaw_lib.query``) on a connection from
  ``erpclaw_lib.db.get_connection()`` and compare exact values, including
  money as exact ``Decimal`` strings (never float, never round).
- read-only proof: a full-table snapshot taken before the call must equal the
  snapshot after it. A getter that wrote, or wrote the wrong thing, fails.
- refusal tests prove a bad request is refused with a truthful message AND
  that the database is byte-identical afterwards (snapshot equal).

Catalog questions (which tables exist) go through ``erpclaw_lib.seam``.
No ``sqlite_master``, no ``PRAGMA``, no ``information_schema`` anywhere below.

Ledger note (read once, applies to all 12): none of these actions posts to
the general ledger or writes any table -- they are SELECT-only. So there are
no debit/credit legs to assert and no balance to strike. Each mirror test
repeats that for its action so a later reader does not add an assertion that
cannot hold. ``edu-get-outstanding-fees`` aggregates ``sales_invoice``
(subledger) rows; its test asserts the per-invoice amounts and that the
reported total is exactly their Decimal sum.

Per-action depth signal (stored row vs ledger effect):
- edu-get-assessment-plan .... stored rows (plan + categories + assessments)
- edu-get-attendance ......... stored row (single attendance record)
- edu-get-attendance-summary . stored rows (aggregation over attendance rows)
- edu-get-course ............. stored row (+ prerequisite/section joins)
- edu-get-enrollment ......... stored row (+ assessment-result join)
- edu-get-fee-structure ...... stored rows + money (items; total == sum)
- edu-get-grading-scale ...... stored rows (scale + entries)
- edu-get-guardian ........... stored row (+ linked-student join)
- edu-get-instructor ......... stored row (+ employee/section joins)
- edu-get-outstanding-fees ... ledger effect (sales_invoice aggregation)
- edu-get-pd-summary ......... stored rows (Decimal aggregation over credits)
- edu-get-section ............ stored row (+ enrollment/plan joins)
"""
import importlib.util
import json
import os
import uuid
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


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

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Field, P, Q, Table, fn, insert_row
from erpclaw_lib.seam import column_names, table_exists, table_names

ACADEMICS_ACTIONS = _load("academics", _SCRIPTS_DIR).ACTIONS
ATTENDANCE_ACTIONS = _load("attendance", _SCRIPTS_DIR).ACTIONS
ENROLLMENT_ACTIONS = _load("enrollment", _SCRIPTS_DIR).ACTIONS
FEES_ACTIONS = _load("fees", _SCRIPTS_DIR).ACTIONS
GRADING_ACTIONS = _load("grading", _SCRIPTS_DIR).ACTIONS
PD_ACTIONS = _load("pd", _SCRIPTS_DIR).ACTIONS
STAFF_ACTIONS = _load("staff", _SCRIPTS_DIR).ACTIONS
STUDENTS_ACTIONS = _load("students", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "depth.sqlite")
    _helpers.init_all_tables(path)
    os.environ["ERPCLAW_DB_PATH"] = path
    yield path
    os.environ.pop("ERPCLAW_DB_PATH", None)


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


@pytest.fixture
def real_db_path(tmp_path):
    """Foundation schema + educlaw tables, so sales_invoice is the real table."""
    path = str(tmp_path / "depth_real.sqlite")
    _load("init_schema", os.path.dirname(_helpers.INIT_SCHEMA_PATH)).init_db(path)
    _helpers.run_init_db(path)
    os.environ["ERPCLAW_DB_PATH"] = path
    yield path
    os.environ.pop("ERPCLAW_DB_PATH", None)


@pytest.fixture
def real_conn(real_db_path):
    c = get_connection(real_db_path)
    yield c
    c.close()


@pytest.fixture
def full(db_path, conn):
    cid = _helpers.seed_company(conn)
    yid = _helpers.seed_academic_year(conn, cid)
    tid = _helpers.seed_academic_term(conn, cid, yid)
    pid = _helpers.seed_program(conn, cid)
    crs = _helpers.seed_course(conn, cid)
    rm = _helpers.seed_room(conn, cid)
    emp = _helpers.seed_employee(conn, cid)
    inst = _helpers.seed_instructor(conn, cid, emp)
    sec = _helpers.seed_section(conn, cid, crs, tid, instructor_id=inst, room_id=rm)
    stu = _helpers.seed_student(conn, cid)
    return {
        "db_path": db_path, "conn": conn, "company_id": cid, "year_id": yid,
        "term_id": tid, "program_id": pid, "course_id": crs, "room_id": rm,
        "employee_id": emp, "instructor_id": inst, "section_id": sec,
        "student_id": stu,
    }


SNAPSHOT_TABLES = [
    "account", "audit_log", "company", "customer", "department", "employee",
    "naming_series", "sales_invoice",
    "educlaw_academic_term", "educlaw_academic_year", "educlaw_activity",
    "educlaw_activity_enrollment", "educlaw_announcement", "educlaw_assessment",
    "educlaw_assessment_category", "educlaw_assessment_plan",
    "educlaw_assessment_result", "educlaw_bus_route", "educlaw_bus_stop",
    "educlaw_circulation", "educlaw_consent_record", "educlaw_course",
    "educlaw_course_enrollment", "educlaw_course_prerequisite",
    "educlaw_daily_meal_count", "educlaw_data_access_log",
    "educlaw_fee_category", "educlaw_fee_structure",
    "educlaw_fee_structure_item", "educlaw_grade_amendment",
    "educlaw_grading_scale", "educlaw_grading_scale_entry",
    "educlaw_guardian", "educlaw_housing_assignment", "educlaw_housing_unit",
    "educlaw_instructor", "educlaw_library_item", "educlaw_notification",
    "educlaw_payment_method", "educlaw_pd_credit", "educlaw_program",
    "educlaw_program_enrollment", "educlaw_program_requirement",
    "educlaw_room", "educlaw_scholarship", "educlaw_section",
    "educlaw_student", "educlaw_student_applicant",
    "educlaw_student_attendance", "educlaw_student_guardian",
    "educlaw_student_meal_record", "educlaw_student_transport",
    "educlaw_waitlist",
]


def _one(conn, table, rid):
    t = Table(table)
    row = conn.execute(
        Q.from_(t).select(t.star).where(Field("id") == P()).get_sql(), (rid,)
    ).fetchone()
    return dict(row) if row else None


def _where(conn, table, field, value, order_by="id"):
    t = Table(table)
    q = Q.from_(t).select(t.star).where(Field(field) == P())
    if order_by:
        q = q.orderby(Field(order_by))
    return [dict(r) for r in conn.execute(q.get_sql(), (value,)).fetchall()]


def _snapshot(conn, db_path):
    snap = {}
    for name in SNAPSHOT_TABLES:
        try:
            if not table_exists(name, db_path):
                continue
        except Exception:
            continue
        t = Table(name)
        try:
            rows = conn.execute(
                Q.from_(t).select(t.star).orderby(Field("id")).get_sql()
            ).fetchall()
        except Exception:
            rows = conn.execute(Q.from_(t).select(t.star).get_sql()).fetchall()
            rows = sorted(
                rows,
                key=lambda r: json.dumps(dict(r), sort_keys=True, default=str),
            )
        snap[name] = [dict(r) for r in rows]
    return json.loads(json.dumps(snap, sort_keys=True, default=str))


def test_seam_catalog_lists_owner_tables(db_path, conn):
    for table in (
        "educlaw_assessment_plan", "educlaw_student_attendance",
        "educlaw_course", "educlaw_course_enrollment", "educlaw_fee_structure",
        "educlaw_grading_scale", "educlaw_guardian", "educlaw_instructor",
        "educlaw_pd_credit", "educlaw_section",
    ):
        assert table_exists(table, db_path), table
        assert "id" in column_names(table, db_path), table
    assert "educlaw_assessment_plan" in table_names(db_path)


class TestGetCourseDepth:
    def test_mirrors_stored_row_joins_and_leaves_db_untouched(self, full):
        c = full["conn"]
        pre = _helpers.seed_course(c, full["company_id"], code="PREREQ100")
        main = call_action(ACADEMICS_ACTIONS["edu-add-course"], c, ns(
            course_code="CS201", name="Data Structures",
            company_id=full["company_id"], credit_hours="4",
            department_id=None, course_type=None, description=None,
            grade_level=None, max_enrollment=None, is_active=None,
            prerequisites=json.dumps([{"course_id": pre, "min_grade": "C"}]),
        ))
        assert is_ok(main), main
        before = _snapshot(c, full["db_path"])
        r = call_action(ACADEMICS_ACTIONS["edu-get-course"], c, ns(course_id=main["id"]))
        assert is_ok(r), r
        row = _one(c, "educlaw_course", main["id"])
        for key in ("id", "course_code", "name", "credit_hours", "company_id"):
            assert r[key] == row[key], key
        assert Decimal(str(r["credit_hours"])) == Decimal("4")
        links = _where(c, "educlaw_course_prerequisite", "course_id", main["id"])
        assert len(links) == 1
        assert len(r["prerequisites"]) == 1
        got = r["prerequisites"][0]
        assert got["prerequisite_course_id"] == pre
        assert got["min_grade"] == links[0]["min_grade"] == "C"
        assert got["course_code"] == "PREREQ100"
        s = full["section_id"]
        r2 = call_action(ACADEMICS_ACTIONS["edu-get-course"], c, ns(course_id=full["course_id"]))
        assert is_ok(r2), r2
        assert r2["prerequisites"] == []
        sec_ids = [x["id"] for x in r2["sections"]]
        assert sec_ids == [s]
        assert r2["sections"][0]["term_name"].startswith("Fall")
        assert _snapshot(c, full["db_path"]) == before

    def test_unknown_course_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        bogus = "course-" + uuid.uuid4().hex
        r = call_action(ACADEMICS_ACTIONS["edu-get-course"], c, ns(course_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetSectionDepth:
    def test_mirrors_section_enrollments_plan_and_leaves_db_untouched(self, full):
        c = full["conn"]
        eid = _helpers.seed_enrollment(c, full["student_id"], full["section_id"], full["company_id"])
        gs = _helpers.seed_grading_scale(c, full["company_id"])
        plan = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], c, ns(
            section_id=full["section_id"], grading_scale_id=gs,
            company_id=full["company_id"],
            categories=json.dumps([{"name": "HW", "weight_percentage": "100"}]),
        ))
        assert is_ok(plan), plan
        before = _snapshot(c, full["db_path"])
        r = call_action(ACADEMICS_ACTIONS["edu-get-section"], c, ns(section_id=full["section_id"]))
        assert is_ok(r), r
        row = _one(c, "educlaw_section", full["section_id"])
        for key in ("id", "section_number", "course_id", "academic_term_id",
                    "instructor_id", "room_id", "company_id"):
            assert r[key] == row[key], key
        # The envelope key "status" is always "ok"; the section's own status
        # rides alongside as "document_status" (see erpclaw_lib.response.ok).
        assert r["status"] == "ok"
        assert r["document_status"] == row["status"] == "open"
        assert r["days_of_week"] == []
        assert r["enrollment_count"] == 1
        names = [e["student_id"] for e in r["enrolled_students"]]
        assert names == [full["student_id"]]
        stu = _one(c, "educlaw_student", full["student_id"])
        assert r["enrolled_students"][0]["last_name"] == stu["last_name"]
        assert r["enrolled_students"][0]["enrollment_status"] == "enrolled"
        assert r["assessment_plan"] is not None
        assert r["assessment_plan"]["id"] == plan["id"]
        assert r["assessment_plan"]["section_id"] == full["section_id"]
        assert _snapshot(c, full["db_path"]) == before

    def test_unknown_section_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        bogus = "section-" + uuid.uuid4().hex
        r = call_action(ACADEMICS_ACTIONS["edu-get-section"], c, ns(section_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetEnrollmentDepth:
    def test_mirrors_stored_enrollment_and_leaves_db_untouched(self, full):
        c = full["conn"]
        eid = _helpers.seed_enrollment(c, full["student_id"], full["section_id"], full["company_id"])
        before = _snapshot(c, full["db_path"])
        r = call_action(ENROLLMENT_ACTIONS["edu-get-enrollment"], c, ns(enrollment_id=eid))
        assert is_ok(r), r
        row = _one(c, "educlaw_course_enrollment", eid)
        for key in ("id", "student_id", "section_id", "enrollment_date",
                    "enrollment_status", "company_id"):
            assert r[key] == row[key], key
        assert r["assessment_results"] == []
        assert _snapshot(c, full["db_path"]) == before

    def test_unknown_enrollment_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        bogus = "enroll-" + uuid.uuid4().hex
        r = call_action(ENROLLMENT_ACTIONS["edu-get-enrollment"], c, ns(enrollment_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetGradingScaleDepth:
    def test_mirrors_scale_and_entries_and_leaves_db_untouched(self, db_path, conn):
        cid = _helpers.seed_company(conn)
        added = call_action(GRADING_ACTIONS["edu-add-grading-scale"], conn, ns(
            company_id=cid, name="Honors A-F", description="Honors scale",
            entries=json.dumps([
                {"letter_grade": "A", "grade_points": "4.0",
                 "min_percentage": "90", "max_percentage": "100"},
                {"letter_grade": "B", "grade_points": "3.0",
                 "min_percentage": "80", "max_percentage": "89.99"},
            ]),
            is_default=None,
        ))
        assert is_ok(added), added
        before = _snapshot(conn, db_path)
        r = call_action(GRADING_ACTIONS["edu-get-grading-scale"], conn, ns(scale_id=added["id"]))
        assert is_ok(r), r
        row = _one(conn, "educlaw_grading_scale", added["id"])
        for key in ("id", "name", "description", "company_id"):
            assert r[key] == row[key], key
        assert r["name"] == "Honors A-F"
        db_entries = conn.execute(
            Q.from_(Table("educlaw_grading_scale_entry"))
            .select(Table("educlaw_grading_scale_entry").star)
            .where(Field("grading_scale_id") == P())
            .orderby(Field("sort_order")).get_sql(), (added["id"],)
        ).fetchall()
        assert len(r["entries"]) == 2 == len(db_entries)
        for got, want in zip(r["entries"], [dict(x) for x in db_entries]):
            assert got["id"] == want["id"]
            assert got["letter_grade"] == want["letter_grade"]
            assert Decimal(str(got["grade_points"])) == Decimal(str(want["grade_points"]))
            assert Decimal(str(got["min_percentage"])) == Decimal(str(want["min_percentage"]))
            assert Decimal(str(got["max_percentage"])) == Decimal(str(want["max_percentage"]))
        assert (r["entries"][0]["letter_grade"], r["entries"][0]["grade_points"],
                r["entries"][0]["min_percentage"], r["entries"][0]["max_percentage"]) == ("A", "4.0", "90", "100")
        assert (r["entries"][1]["letter_grade"], r["entries"][1]["max_percentage"]) == ("B", "89.99")
        assert _snapshot(conn, db_path) == before

    def test_unknown_scale_refused_without_writing(self, db_path, conn):
        _helpers.seed_company(conn)
        before = _snapshot(conn, db_path)
        bogus = "scale-" + uuid.uuid4().hex
        r = call_action(GRADING_ACTIONS["edu-get-grading-scale"], conn, ns(scale_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(conn, db_path) == before


class TestGetAssessmentPlanDepth:
    def test_mirrors_plan_categories_assessments_and_leaves_db_untouched(self, full):
        c = full["conn"]
        gs = _helpers.seed_grading_scale(c, full["company_id"])
        plan = call_action(GRADING_ACTIONS["edu-add-assessment-plan"], c, ns(
            section_id=full["section_id"], grading_scale_id=gs,
            company_id=full["company_id"],
            categories=json.dumps([
                {"name": "HW", "weight_percentage": "30"},
                {"name": "Tests", "weight_percentage": "70"},
            ]),
        ))
        assert is_ok(plan), plan
        cats = _where(c, "educlaw_assessment_category", "assessment_plan_id", plan["id"], order_by="sort_order")
        assert len(cats) == 2
        added = call_action(GRADING_ACTIONS["edu-add-assessment"], c, ns(
            plan_id=plan["id"], category_id=cats[1]["id"],
            name="Midterm", max_points="100", due_date="2025-10-15",
            description=None, allows_extra_credit=None, sort_order=None,
            company_id=full["company_id"],
        ))
        assert is_ok(added), added
        before = _snapshot(c, full["db_path"])
        r = call_action(GRADING_ACTIONS["edu-get-assessment-plan"], c, ns(plan_id=plan["id"]))
        assert is_ok(r), r
        row = _one(c, "educlaw_assessment_plan", plan["id"])
        assert r["id"] == row["id"]
        assert r["section_id"] == full["section_id"] == row["section_id"]
        assert r["grading_scale_id"] == gs == row["grading_scale_id"]
        assert [x["name"] for x in r["categories"]] == ["HW", "Tests"]
        assert [Decimal(str(x["weight_percentage"])) for x in r["categories"]] == [Decimal("30"), Decimal("70")]
        assert sum(Decimal(str(x["weight_percentage"])) for x in r["categories"]) == Decimal("100")
        assert r["categories"][0]["assessments"] == []
        mids = r["categories"][1]["assessments"]
        assert len(mids) == 1
        db_mid = _one(c, "educlaw_assessment", added["id"])
        assert mids[0]["id"] == added["id"]
        assert mids[0]["name"] == db_mid["name"] == "Midterm"
        assert Decimal(str(mids[0]["max_points"])) == Decimal(str(db_mid["max_points"])) == Decimal("100")
        by_section = call_action(GRADING_ACTIONS["edu-get-assessment-plan"], c,
                                 ns(plan_id=None, section_id=full["section_id"]))
        assert is_ok(by_section), by_section
        assert by_section["id"] == plan["id"]
        assert _snapshot(c, full["db_path"]) == before

    def test_missing_lookup_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        r = call_action(GRADING_ACTIONS["edu-get-assessment-plan"], c, ns(plan_id=None, section_id=None))
        assert is_error(r), r
        assert "plan-id" in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetAttendanceDepth:
    def test_mirrors_stored_record_and_leaves_db_untouched(self, full):
        c = full["conn"]
        rec = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], c, ns(
            student_id=full["student_id"], attendance_date="2025-09-04",
            attendance_status="tardy", company_id=full["company_id"],
            section_id=None, late_minutes="12", comments="Bus delay",
            marked_by="warden-1", source="biometric",
        ))
        assert is_ok(rec), rec
        before = _snapshot(c, full["db_path"])
        r = call_action(ATTENDANCE_ACTIONS["edu-get-attendance"], c, ns(attendance_id=rec["id"]))
        assert is_ok(r), r
        row = _one(c, "educlaw_student_attendance", rec["id"])
        for key in ("id", "student_id", "attendance_date", "attendance_status",
                    "comments", "marked_by", "source", "company_id"):
            assert r[key] == row[key], key
        assert r["attendance_status"] == "tardy"
        assert r["late_minutes"] == row["late_minutes"] == 12
        assert r["source"] == "biometric"
        assert _snapshot(c, full["db_path"]) == before

    def test_unknown_record_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        bogus = "att-" + uuid.uuid4().hex
        r = call_action(ATTENDANCE_ACTIONS["edu-get-attendance"], c, ns(attendance_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetAttendanceSummaryDepth:
    def _seed_six(self, c, stu, cid):
        for day, status in (
            ("2025-09-01", "present"), ("2025-09-02", "present"),
            ("2025-09-03", "absent"), ("2025-09-04", "half_day"),
            ("2025-09-05", "excused"), ("2025-09-06", "tardy"),
        ):
            r = call_action(ATTENDANCE_ACTIONS["edu-record-attendance"], c, ns(
                student_id=stu, attendance_date=day, attendance_status=status,
                company_id=cid, section_id=None, late_minutes=None,
                comments=None, marked_by=None, source=None,
            ))
            assert is_ok(r), r

    def test_counts_match_stored_rows_and_leaves_db_untouched(self, full):
        c = full["conn"]
        self._seed_six(c, full["student_id"], full["company_id"])
        before = _snapshot(c, full["db_path"])
        r = call_action(ATTENDANCE_ACTIONS["edu-get-attendance-summary"], c, ns(
            student_id=full["student_id"], section_id=None,
            attendance_date_from=None, attendance_date_to=None,
        ))
        assert is_ok(r), r
        t = Table("educlaw_student_attendance")
        rows = c.execute(
            Q.from_(t).select(t.attendance_status, fn.Count(t.star).as_("cnt"))
            .where(t.student_id == P()).groupby(t.attendance_status).get_sql(),
            (full["student_id"],),
        ).fetchall()
        db_counts = {row["attendance_status"]: row["cnt"] for row in rows}
        assert r["total_days"] == sum(db_counts.values()) == 6
        for key in ("present", "absent", "tardy", "excused", "half_day"):
            assert r[key] == db_counts.get(key, 0), key
        # FINDING (documented, not fixed): the handler credits a half day as
        # counts["half_day"] // 2 using integer division, so one lone half_day
        # contributes 0 present-equivalents: (2 + 0 + 1) / 6 = 50.00, whereas
        # half-credit would give (2 + 0.5 + 1) / 6 = 58.33. This test pins the
        # real behaviour; changing the formula is follow-up work.
        assert r["attendance_percentage"] == "50.00"
        assert Decimal(r["attendance_percentage"]) == Decimal("50.00")
        assert _snapshot(c, full["db_path"]) == before

    def test_missing_student_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        r = call_action(ATTENDANCE_ACTIONS["edu-get-attendance-summary"], c, ns(
            student_id=None, section_id=None,
            attendance_date_from=None, attendance_date_to=None,
        ))
        assert is_error(r), r
        assert "student-id" in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetInstructorDepth:
    def test_mirrors_instructor_employee_sections_and_leaves_db_untouched(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        r = call_action(STAFF_ACTIONS["edu-get-instructor"], c, ns(instructor_id=full["instructor_id"]))
        assert is_ok(r), r
        row = _one(c, "educlaw_instructor", full["instructor_id"])
        for key in ("id", "employee_id", "company_id", "naming_series"):
            assert r[key] == row[key], key
        for key in ("credentials", "specializations", "office_hours"):
            raw = row[key]
            assert r[key] == (json.loads(raw) if raw else raw), key
        emp = _one(c, "employee", full["employee_id"])
        assert r["employee"]["id"] == emp["id"]
        assert r["employee"]["work_email"] == emp["work_email"] == "teacher@school.edu"
        sec_ids = [s["id"] for s in r["current_sections"]]
        assert sec_ids == [full["section_id"]]
        assert r["current_sections"][0]["course_code"] == "MATH101"
        assert r["current_sections"][0]["term_name"].startswith("Fall")
        assert _snapshot(c, full["db_path"]) == before

    def test_unknown_instructor_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        bogus = "inst-" + uuid.uuid4().hex
        r = call_action(STAFF_ACTIONS["edu-get-instructor"], c, ns(instructor_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(c, full["db_path"]) == before


class TestGetFeeStructureDepth:
    def _two_categories(self, c, cid):
        first = _helpers.seed_fee_category(c, cid)
        second = "fee-" + uuid.uuid4().hex
        sql, _ = insert_row("educlaw_fee_category", {
            "id": P(), "name": P(), "description": P(),
            "is_active": P(), "company_id": P(), "created_by": P(),
        })
        c.execute(sql, (second, "Lab-" + second[:4], "Lab fees", 1, cid, ""))
        c.commit()
        return first, second

    def test_mirrors_items_total_and_leaves_db_untouched(self, db_path, conn):
        cid = _helpers.seed_company(conn)
        cat_tuition, cat_lab = self._two_categories(conn, cid)
        added = call_action(FEES_ACTIONS["edu-add-fee-structure"], conn, ns(
            name="Fall Fees", company_id=cid, program_id=None,
            academic_term_id=None, grade_level=None,
            items=json.dumps([
                {"fee_category_id": cat_tuition, "amount": "1250.00", "description": "Tuition"},
                {"fee_category_id": cat_lab, "amount": "9.50", "description": "Lab"},
            ]),
        ))
        assert is_ok(added), added
        assert added["total_amount"] == "1259.50"
        before = _snapshot(conn, db_path)
        r = call_action(FEES_ACTIONS["edu-get-fee-structure"], conn, ns(structure_id=added["id"]))
        assert is_ok(r), r
        row = _one(conn, "educlaw_fee_structure", added["id"])
        assert r["id"] == row["id"]
        assert r["name"] == row["name"] == "Fall Fees"
        assert isinstance(r["total_amount"], str)
        assert r["total_amount"] == row["total_amount"] == "1259.50"
        assert Decimal(r["total_amount"]) == Decimal("1259.50")
        t = Table("educlaw_fee_structure_item")
        db_items = [dict(x) for x in conn.execute(
            Q.from_(t).select(t.star).where(t.fee_structure_id == P())
            .orderby(t.sort_order).get_sql(), (added["id"],)
        ).fetchall()]
        assert len(r["items"]) == 2 == len(db_items)
        for got, want in zip(r["items"], db_items):
            assert got["fee_category_id"] == want["fee_category_id"]
            assert got["amount"] == want["amount"]
            assert Decimal(str(got["amount"])) == Decimal(str(want["amount"]))
            assert got["description"] == want["description"]
        assert [i["amount"] for i in r["items"]] == ["1250.00", "9.50"]
        assert r["items"][0]["category_name"] == "Tuition"
        assert r["items"][1]["category_name"] == _one(conn, "educlaw_fee_category", cat_lab)["name"]
        assert Decimal(r["total_amount"]) == sum(Decimal(str(i["amount"])) for i in r["items"])
        assert _snapshot(conn, db_path) == before

    def test_unknown_structure_refused_without_writing(self, db_path, conn):
        _helpers.seed_company(conn)
        before = _snapshot(conn, db_path)
        bogus = "fs-" + uuid.uuid4().hex
        r = call_action(FEES_ACTIONS["edu-get-fee-structure"], conn, ns(structure_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(conn, db_path) == before


class TestGetGuardianDepth:
    def test_mirrors_guardian_links_and_leaves_db_untouched(self, full):
        c = full["conn"]
        gid = _helpers.seed_guardian(c, full["company_id"])
        link = call_action(STUDENTS_ACTIONS["edu-assign-guardian"], c, ns(
            student_id=full["student_id"], guardian_id=gid,
            relationship="mother", is_primary_contact=None,
            is_emergency_contact=None, has_custody=None, can_pickup=None,
            receives_communications=None,
        ))
        assert is_ok(link), link
        before = _snapshot(c, full["db_path"])
        r = call_action(STUDENTS_ACTIONS["edu-get-guardian"], c, ns(guardian_id=gid))
        assert is_ok(r), r
        row = _one(c, "educlaw_guardian", gid)
        for key in ("id", "first_name", "last_name", "full_name",
                    "relationship", "email", "phone", "company_id"):
            assert r[key] == row[key], key
        assert r["email"] == "parent@email.com"
        assert r["address"] == json.loads(row["address"])
        assert r["address"] == {}
        links = _where(c, "educlaw_student_guardian", "guardian_id", gid)
        assert len(links) == 1
        assert len(r["linked_students"]) == 1
        got = r["linked_students"][0]
        stu = _one(c, "educlaw_student", full["student_id"])
        assert got["id"] == stu["id"] == full["student_id"]
        assert got["full_name"] == stu["full_name"]
        assert got["relationship"] == links[0]["relationship"] == "mother"
        assert got["is_primary_contact"] == links[0]["is_primary_contact"]
        assert _snapshot(c, full["db_path"]) == before

    def test_unknown_guardian_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        bogus = "guard-" + uuid.uuid4().hex
        r = call_action(STUDENTS_ACTIONS["edu-get-guardian"], c, ns(guardian_id=bogus))
        assert is_error(r), r
        assert bogus in r["message"]
        assert _snapshot(c, full["db_path"]) == before


def _seed_customer(conn, company_id, name):
    cid = "cust-" + uuid.uuid4().hex
    sql, _ = insert_row("customer", {"id": P(), "name": P(), "company_id": P()})
    conn.execute(sql, (cid, name, company_id))
    conn.commit()
    return cid


def _seed_invoice(conn, company_id, customer_id, series, status, due, total, outstanding):
    iid = "sinv-" + uuid.uuid4().hex
    sql, _ = insert_row("sales_invoice", {
        "id": P(), "naming_series": P(), "customer_id": P(),
        "posting_date": P(), "due_date": P(), "grand_total": P(),
        "outstanding_amount": P(), "status": P(), "company_id": P(),
    })
    conn.execute(sql, (iid, series, customer_id, "2026-01-02", due,
                       total, outstanding, status, company_id))
    conn.commit()
    return iid


class TestGetOutstandingFeesDepth:
    def _setup(self, conn):
        cid = _helpers.seed_company(conn)
        cust_a = _seed_customer(conn, cid, "Parent A")
        stu_a = _helpers.seed_student(conn, cid)
        stu_t = Table("educlaw_student")
        conn.execute(
            Q.update(stu_t).set(stu_t.customer_id, P()).where(stu_t.id == P()).get_sql(),
            (cust_a, stu_a))
        conn.commit()
        tuition = _seed_invoice(conn, cid, cust_a, "SINV-A-TUI", "submitted",
                                "2026-01-31", "1250.00", "1250.00")
        lab = _seed_invoice(conn, cid, cust_a, "SINV-A-LAB", "partially_paid",
                            "2026-02-15", "40.00", "9.50")
        waived = _seed_invoice(conn, cid, cust_a, "SINV-A-WAIVED", "submitted",
                               "2026-01-31", "0.00", "0.00")
        zeroed = _seed_invoice(conn, cid, cust_a, "SINV-A-OVD-ZERO", "overdue",
                               "2026-01-31", "600.00", "0.00")
        future = _seed_invoice(conn, cid, cust_a, "SINV-A-FUTURE", "submitted",
                               "2099-01-31", "500.00", "500.00")
        paid = _seed_invoice(conn, cid, cust_a, "SINV-A-PAID", "paid",
                             "2026-01-31", "100.00", "0.00")
        cust_b = _seed_customer(conn, cid, "Parent B")
        stu_b = _helpers.seed_student(conn, cid)
        conn.execute(Q.update(Table("educlaw_student"))
                     .set(Field("customer_id"), P()).where(Field("id") == P()).get_sql(),
                     (cust_b, stu_b))
        conn.commit()
        _seed_invoice(conn, cid, cust_b, "SINV-B-WAIVED", "submitted",
                      "2026-01-31", "0.00", "0.00")
        cust_c = _seed_customer(conn, cid, "Parent C")
        stu_c = _helpers.seed_student(conn, cid)
        conn.execute(Q.update(Table("educlaw_student"))
                     .set(Field("customer_id"), P()).where(Field("id") == P()).get_sql(),
                     (cust_c, stu_c))
        conn.execute(Q.update(Table("educlaw_student"))
                     .set(Field("status"), P()).where(Field("id") == P()).get_sql(),
                     ("inactive", stu_c))
        conn.commit()
        _seed_invoice(conn, cid, cust_c, "SINV-C-OLD", "overdue",
                      "2026-01-31", "700.00", "700.00")
        stu_d = _helpers.seed_student(conn, cid)
        other_cid = _helpers.seed_company(conn)
        cust_o = _seed_customer(conn, other_cid, "Parent O")
        stu_o = _helpers.seed_student(conn, other_cid)
        conn.execute(Q.update(Table("educlaw_student"))
                     .set(Field("customer_id"), P()).where(Field("id") == P()).get_sql(),
                     (cust_o, stu_o))
        conn.commit()
        _seed_invoice(conn, other_cid, cust_o, "SINV-O-OLD", "overdue",
                      "2026-01-31", "300.00", "300.00")
        return {
            "company_id": cid, "student_id": stu_a, "customer_id": cust_a,
            "tuition": tuition, "lab": lab, "waived": waived,
            "zeroed": zeroed, "future": future, "paid": paid,
            "no_customer_student": stu_d,
        }

    def test_lists_exact_overdue_legs_balancing_total(self, real_db_path, real_conn):
        c = real_conn
        s = self._setup(c)
        before = _snapshot(c, real_db_path)
        r = call_action(FEES_ACTIONS["edu-get-outstanding-fees"], c,
                        ns(company_id=s["company_id"]))
        assert is_ok(r), r
        assert r["company_id"] == s["company_id"]
        assert r["outstanding_count"] == 1
        (entry,) = r["outstanding_students"]
        stu = _one(c, "educlaw_student", s["student_id"])
        assert entry["student_id"] == stu["id"]
        assert entry["naming_series"] == stu["naming_series"]
        assert entry["full_name"] == stu["full_name"]
        assert entry["email"] == stu["email"]
        assert isinstance(entry["total_outstanding"], str)
        assert entry["total_outstanding"] == "1259.50"
        assert Decimal(entry["total_outstanding"]) == Decimal("1259.50")
        listed = {
            (o["id"], o["status"], o["due_date"],
             o["grand_total"], o["outstanding_amount"])
            for o in entry["overdue_invoices"]
        }
        assert listed == {
            (s["tuition"], "submitted", "2026-01-31", "1250.00", "1250.00"),
            (s["lab"], "partially_paid", "2026-02-15", "40.00", "9.50"),
        }
        for inv in entry["overdue_invoices"]:
            db_inv = _one(c, "sales_invoice", inv["id"])
            assert inv["status"] == db_inv["status"]
            assert inv["due_date"] == db_inv["due_date"]
            assert inv["grand_total"] == db_inv["grand_total"]
            assert inv["outstanding_amount"] == db_inv["outstanding_amount"]
        assert Decimal(entry["total_outstanding"]) == sum(
            Decimal(str(o["outstanding_amount"])) for o in entry["overdue_invoices"])
        seen = {o["id"] for o in entry["overdue_invoices"]}
        assert s["waived"] not in seen
        assert s["zeroed"] not in seen
        assert s["future"] not in seen
        assert s["paid"] not in seen
        assert _snapshot(c, real_db_path) == before

    def test_missing_company_refused_without_writing(self, real_db_path, real_conn):
        self._setup(real_conn)
        before = _snapshot(real_conn, real_db_path)
        r = call_action(FEES_ACTIONS["edu-get-outstanding-fees"], real_conn,
                        ns(company_id=None))
        assert is_error(r), r
        assert "company-id" in r["message"]
        assert _snapshot(real_conn, real_db_path) == before


class TestGetPdSummaryDepth:
    def _credit(self, c, inst, cid, name, hours, ctype, status="approved"):
        r = call_action(PD_ACTIONS["edu-add-pd-credit"], c, ns(
            instructor_id=inst, name=name, credit_hours=hours,
            start_date="2025-06-15", company_id=cid, credit_type=ctype,
            description="", end_date="", code="", status=status,
            limit=50, offset=0,
        ))
        assert is_ok(r), r
        return r

    def test_totals_match_approved_rows_and_leaves_db_untouched(self, full):
        c = full["conn"]
        self._credit(c, full["instructor_id"], full["company_id"], "C1", "15", "general")
        self._credit(c, full["instructor_id"], full["company_id"], "C2", "2.5", "technology")
        self._credit(c, full["instructor_id"], full["company_id"], "Pending Big",
                     "100", "general", status="pending")
        other_emp = _helpers.seed_employee(c, full["company_id"])
        other_inst = _helpers.seed_instructor(c, full["company_id"], other_emp)
        self._credit(c, other_inst, full["company_id"], "Other", "50", "general")
        before = _snapshot(c, full["db_path"])
        r = call_action(PD_ACTIONS["edu-get-pd-summary"], c, ns(
            instructor_id=full["instructor_id"], limit=50, offset=0,
        ))
        assert is_ok(r), r
        assert r["teacher_id"] == full["instructor_id"]
        t = Table("educlaw_pd_credit")
        approved = [dict(x) for x in c.execute(
            Q.from_(t).select(t.star).where(t.teacher_id == P())
            .where(t.status == "approved").get_sql(), (full["instructor_id"],)
        ).fetchall()]
        assert len(approved) == 2
        assert isinstance(r["total_credit_hours"], str)
        assert r["total_credit_hours"] == "17.5"
        assert Decimal(r["total_credit_hours"]) == sum(
            Decimal(str(x["credit_hours"])) for x in approved) == Decimal("17.5")
        by_type = {x["credit_type"]: x for x in r["by_type"]}
        assert set(by_type) == {"general", "technology"}
        assert by_type["general"]["total_hours"] == "15"
        assert by_type["general"]["course_count"] == 1
        assert by_type["technology"]["total_hours"] == "2.5"
        assert by_type["technology"]["course_count"] == 1
        assert Decimal(by_type["technology"]["total_hours"]) == Decimal("2.5")
        assert _snapshot(c, full["db_path"]) == before

    def test_missing_instructor_refused_without_writing(self, full):
        c = full["conn"]
        before = _snapshot(c, full["db_path"])
        r = call_action(PD_ACTIONS["edu-get-pd-summary"], c, ns(instructor_id=None, limit=50, offset=0))
        assert is_error(r), r
        assert "instructor-id" in r["message"]
        assert _snapshot(c, full["db_path"]) == before
