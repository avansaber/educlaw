"""M413 depth: behavioural evidence for 12 shape-or-routing-only actions.

Prior state (read before writing anything below):
- `edu-convert-applicant-to-student` had a shape-only test
  (`TestConvertApplicant.test_convert_to_student` in `test_educlaw_core.py`):
  it asserts the response is ok and carries a student id, never that a
  student row exists, what it contains, or that the applicant flipped to
  enrolled.
- `edu-create-program-enrollment` (`TestProgramEnrollment.test_create`) and
  `edu-create-section-enrollment` (`TestSectionEnrollment.test_enroll`)
  likewise assert only `is_ok`, never the enrollment row or the section
  counter.
- `edu-generate-student-record` (`TestStudentRecord`), `edu-get-academic-year`
  (`TestAcademicYear.test_get`), `edu-get-academic-term`
  (`TestAcademicTerm.test_get`) and `edu-get-announcement`
  (`TestAnnouncement.test_get`) assert only `is_ok`, never that the payload
  mirrors the stored row or that a read changes nothing.
- `edu-generate-fee-invoice`, `edu-generate-progress-report`,
  `edu-generate-report-card`, `edu-generate-section-grade` and
  `edu-get-applicant` have NO module test in this tree at all; they are
  reachable (present in their domain ACTIONS dicts) but unobserved here.

Every test below observes the database through `get_connection()` read-backs
built with PyPika (`erpclaw_lib.query`): the row that should exist afterwards
with exact values, the row that should have changed from what to what, and
what must NOT have changed. Catalog questions (does the table exist) go
through `erpclaw_lib.seam`; there is no `sqlite_master`, no `PRAGMA` and no
`information_schema` below. Money compares exact `Decimal` strings, never
float, never approximate, never `round`.

Ledger scope, stated once so no later reader adds a balance assertion that
cannot hold: eleven of these 12 handlers never reach the general ledger. The
seven `get`/`generate`-report readers are pure SELECTs;
`edu-generate-progress-report` writes only notifications;
`edu-generate-student-record` writes only one `educlaw_data_access_log` row;
the enrollment/convert writers touch only their own `educlaw_*` tables plus
notifications. The exception is `edu-generate-fee-invoice` (m678): it creates
a real `sales_invoice` through the selling module and submits it, so the
submit posts the receivable/income `gl_entry` legs, and educlaw stores its
own `educlaw_fee_invoice` link row plus the `fee_due` notification -- see
TestGenerateFeeInvoice. Every per-action section repeats its own ledger
note.

Signal depth per action (stored row unless noted):
- edu-convert-applicant-to-student: stored row (inserts student, flips applicant).
- edu-create-program-enrollment: stored row (inserts enrollment + notification).
- edu-create-section-enrollment: stored row (inserts enrollment, bumps counter).
- edu-generate-fee-invoice: stored rows (submitted sales_invoice with its GL legs via the selling delegate, educlaw_fee_invoice link, fee_due notification).
- edu-generate-progress-report: stored row (notification rows).
- edu-generate-report-card: stored row (read-only; payload mirrors rows, DB equal).
- edu-generate-section-grade: stored row (read-only preview; enrollment untouched).
- edu-generate-student-record: stored row (payload mirrors row + one access log).
- edu-get-academic-term: stored row (read-only; payload mirrors row, DB equal).
- edu-get-academic-year: stored row (read-only; payload mirrors row, DB equal).
- edu-get-announcement: stored row (read-only; payload mirrors row, DB equal).
- edu-get-applicant: stored row (read-only; payload mirrors row, DB equal).
"""
import importlib.util
import json
import os
import shutil
import sys
from datetime import date
from decimal import Decimal

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_LIB_DIR = os.path.join(_SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
if os.path.isdir(os.path.join(_LIB_DIR, "erpclaw_lib")) and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from erpclaw_lib.db import get_connection
from erpclaw_lib.query import Q, P, Table, Field, fn, insert_row
from erpclaw_lib import seam as _seam


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

ST = _load("students", _SCRIPTS_DIR).ACTIONS
AC = _load("academics", _SCRIPTS_DIR).ACTIONS
EN = _load("enrollment", _SCRIPTS_DIR).ACTIONS
FE = _load("fees", _SCRIPTS_DIR).ACTIONS
GR = _load("grading", _SCRIPTS_DIR).ACTIONS
CO = _load("communications", _SCRIPTS_DIR).ACTIONS
AT = _load("attendance", _SCRIPTS_DIR).ACTIONS

SNAPSHOT_TABLES = (
    "company",
    "naming_series",
    "sales_invoice",
    "audit_log",
    "educlaw_student_applicant",
    "educlaw_student",
    "educlaw_guardian",
    "educlaw_student_guardian",
    "educlaw_academic_year",
    "educlaw_academic_term",
    "educlaw_program",
    "educlaw_course",
    "educlaw_section",
    "educlaw_program_enrollment",
    "educlaw_course_enrollment",
    "educlaw_student_attendance",
    "educlaw_grading_scale",
    "educlaw_grading_scale_entry",
    "educlaw_assessment_plan",
    "educlaw_assessment_category",
    "educlaw_assessment",
    "educlaw_assessment_result",
    "educlaw_fee_category",
    "educlaw_fee_structure",
    "educlaw_fee_structure_item",
    "educlaw_scholarship",
    "educlaw_announcement",
    "educlaw_notification",
    "educlaw_data_access_log",
    "educlaw_consent_record",
)


@pytest.fixture(scope="module")
def template_path(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("m413tpl") / "template.sqlite")
    _helpers.init_all_tables(path)
    assert _seam.table_exists("educlaw_student", path)
    assert _seam.table_exists("educlaw_student_applicant", path)
    assert _seam.table_exists("educlaw_program_enrollment", path)
    assert _seam.table_exists("educlaw_course_enrollment", path)
    assert _seam.table_exists("educlaw_notification", path)
    assert _seam.table_exists("educlaw_data_access_log", path)
    assert _seam.table_exists("educlaw_fee_structure", path)
    assert _seam.table_exists("educlaw_announcement", path)
    assert _seam.table_exists("educlaw_academic_year", path)
    assert _seam.table_exists("educlaw_academic_term", path)
    return path


@pytest.fixture
def fconn(template_path, tmp_path):
    dest = str(tmp_path / "case.sqlite")
    shutil.copyfile(template_path, dest)
    conn = get_connection(dest)
    os.environ["ERPCLAW_DB_PATH"] = dest
    try:
        yield conn
    finally:
        conn.close()
        os.environ.pop("ERPCLAW_DB_PATH", None)


def _snapshot(conn):
    snap = {}
    for name in SNAPSHOT_TABLES:
        t = Table(name)
        rows = conn.execute(Q.from_(t).select("*").get_sql()).fetchall()
        snap[name] = sorted(repr(dict(r)) for r in rows)
    return snap


def _row(conn, table, row_id):
    t = Table(table)
    row = conn.execute(
        Q.from_(t).select("*").where(t.id == P()).get_sql(), (row_id,)).fetchone()
    return dict(row) if row is not None else None


def _count(conn, table):
    t = Table(table)
    return conn.execute(Q.from_(t).select(fn.Count("*")).get_sql()).fetchone()[0]


def _build_env(conn):
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
    return {"company_id": cid, "year_id": yid, "term_id": tid,
            "program_id": pid, "course_id": crs, "section_id": sec,
            "student_id": stu}


def _add_applicant(conn, cid, first="Conv", last="Test", dob="2018-06-01",
                   grade="10", email="conv@test.com"):
    r = call_action(ST["edu-add-student-applicant"], conn, ns(
        company_id=cid, first_name=first, last_name=last,
        date_of_birth=dob, gender=None, email=email,
        phone=None, address=None, grade_level=grade,
        applying_for_program_id=None, applying_for_term_id=None,
        application_date=None, documents=None, previous_school=None,
        previous_school_address=None, transfer_records=None,
        guardian_info=None, middle_name=None))
    assert is_ok(r), r
    return r["id"]


def _accept_applicant(conn, app_id):
    r = call_action(ST["edu-approve-applicant"], conn, ns(
        applicant_id=app_id, applicant_status="accepted",
        reviewed_by="admin", review_notes=None))
    assert is_ok(r), r


def _fee_setup(conn, s):
    cat2 = call_action(FE["edu-add-fee-category"], conn, ns(
        company_id=s["company_id"], name="Lab Fees", description="lab",
        revenue_account_id=None))
    assert is_ok(cat2), cat2
    t = Table("educlaw_fee_category")
    cat1 = conn.execute(
        Q.from_(t).select(t.id).where(t.company_id == P()).where(
            t.name == P()).get_sql(),
        (s["company_id"], "Tuition")).fetchone()
    if cat1 is None:
        r = call_action(FE["edu-add-fee-category"], conn, ns(
            company_id=s["company_id"], name="Tuition", description="tuition",
            revenue_account_id=None))
        assert is_ok(r), r
        cat1_id = r["id"]
    else:
        cat1_id = dict(cat1)["id"]
    fs = call_action(FE["edu-add-fee-structure"], conn, ns(
        company_id=s["company_id"], name="FS-2025", program_id=s["program_id"],
        academic_term_id=s["term_id"], grade_level=None,
        items=json.dumps([
            {"fee_category_id": cat1_id, "amount": "5000.00",
             "description": "tuition"},
            {"fee_category_id": cat2["id"], "amount": "500.00",
             "description": "lab"}])))
    assert is_ok(fs), fs
    assert fs["total_amount"] == "5500.00"
    assert Decimal(fs["total_amount"]) == Decimal("5500.00")
    return fs["id"]


def _grade_setup(conn, s, points="85"):
    gs = call_action(GR["edu-add-grading-scale"], conn, ns(
        company_id=s["company_id"], name="Depth Scale", description="m413",
        entries=json.dumps([
            {"letter_grade": "A", "grade_points": "4.0",
             "min_percentage": "80", "max_percentage": "100"},
            {"letter_grade": "B", "grade_points": "3.0",
             "min_percentage": "70", "max_percentage": "79.99"},
            {"letter_grade": "C", "grade_points": "2.0",
             "min_percentage": "60", "max_percentage": "69.99"},
            {"letter_grade": "F", "grade_points": "0.0",
             "min_percentage": "0", "max_percentage": "59.99"}]),
        is_default=None))
    assert is_ok(gs), gs
    plan = call_action(GR["edu-add-assessment-plan"], conn, ns(
        section_id=s["section_id"], grading_scale_id=gs["id"],
        company_id=s["company_id"],
        categories=json.dumps([{"name": "Tests", "weight_percentage": "100"}])))
    assert is_ok(plan), plan
    t = Table("educlaw_assessment_category")
    cat = conn.execute(
        Q.from_(t).select(t.id).where(
            t.assessment_plan_id == P()).get_sql(), (plan["id"],)).fetchone()
    asm = call_action(GR["edu-add-assessment"], conn, ns(
        plan_id=plan["id"], category_id=dict(cat)["id"], name="Midterm",
        max_points="100", due_date="2025-10-15", description=None,
        allows_extra_credit=None, sort_order=None,
        company_id=s["company_id"]))
    assert is_ok(asm), asm
    res = call_action(GR["edu-record-assessment-result"], conn, ns(
        assessment_id=asm["id"], student_id=s["student_id"],
        points_earned=points, graded_by="teacher", comments=None,
        is_exempt=None, is_late=None, enrollment_id=None))
    assert is_ok(res), res
    assert Decimal(res["points_earned"]) == Decimal(points)
    return {"scale_id": gs["id"], "plan_id": plan["id"],
            "assessment_id": asm["id"]}


def _seed_announcement(conn, cid, title="Storm Closure"):
    import uuid as _uuid
    ann_id = str(_uuid.uuid4())
    now = "2026-09-17T00:00:00Z"
    sql, _ = insert_row("educlaw_announcement", {
        "id": P(), "title": P(), "body": P(), "priority": P(),
        "audience_type": P(), "audience_filter": P(),
        "publish_date": P(), "expiry_date": P(),
        "announcement_status": P(), "published_by": P(),
        "company_id": P(), "created_at": P(), "updated_at": P(),
        "created_by": P()})
    conn.execute(sql, (ann_id, title, "School is closed.", "normal", "all",
                       "{}", "2025-09-01", "2025-12-31", "draft", "",
                       cid, now, now, ""))
    conn.commit()
    return ann_id


def _enroll_program_and_section(conn, s):
    r = call_action(EN["edu-create-program-enrollment"], conn, ns(
        student_id=s["student_id"], program_id=s["program_id"],
        academic_year_id=s["year_id"], company_id=s["company_id"],
        enrollment_date=None))
    assert is_ok(r), r
    r = call_action(EN["edu-create-section-enrollment"], conn, ns(
        student_id=s["student_id"], section_id=s["section_id"],
        company_id=s["company_id"], is_repeat=None, grade_type=None))
    assert is_ok(r), r
    return r["id"]


# ---------------------------------------------------------------------------
# edu-convert-applicant-to-student -- stored row (inserts student, flips applicant).
# No ledger effect: writes only educlaw_student (+ applicant status flip and
# one audit_log line). No journal/gl/sales_invoice involvement.
# Finding (deliberately not fixed): the applicant intake
# (edu-add-student-applicant) silently drops its grade_level argument -- the
# educlaw_student_applicant table has no such column -- so there is nothing
# for the converter to carry over. The happy path passes grade_level
# explicitly to the converter and the assertion pins the stored value.
# ---------------------------------------------------------------------------
class TestConvertApplicantToStudent:
    def test_convert_inserts_student_and_flips_applicant(self, fconn):
        s = _build_env(fconn)
        app_id = _add_applicant(fconn, s["company_id"])
        _accept_applicant(fconn, app_id)
        before_students = _count(fconn, "educlaw_student")
        r = call_action(ST["edu-convert-applicant-to-student"], fconn, ns(
            applicant_id=app_id, company_id=s["company_id"],
            grade_level="10"))
        assert is_ok(r), r
        assert _count(fconn, "educlaw_student") == before_students + 1
        stu = _row(fconn, "educlaw_student", r["id"])
        assert stu["first_name"] == "Conv"
        assert stu["last_name"] == "Test"
        assert stu["full_name"] == "Conv Test"
        assert stu["date_of_birth"] == "2018-06-01"
        assert stu["email"] == "conv@test.com"
        assert stu["student_applicant_id"] == app_id
        assert stu["grade_level"] == "10"
        assert stu["status"] == "active"
        assert stu["academic_standing"] == "good"
        assert stu["registration_hold"] == 0
        assert stu["is_coppa_applicable"] == 1
        assert stu["enrollment_date"] == date.today().isoformat()
        assert stu["naming_series"].startswith("STU-")
        assert r["applicant_id"] == app_id
        app = _row(fconn, "educlaw_student_applicant", app_id)
        assert app["status"] == "enrolled"
        assert app["first_name"] == "Conv"
        other = _row(fconn, "educlaw_student", s["student_id"])
        assert other["full_name"] == "Test Student"
        assert other["status"] == "active"

    def test_refuses_unaccepted_applicant_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        app_id = _add_applicant(fconn, s["company_id"])
        before = _snapshot(fconn)
        r = call_action(ST["edu-convert-applicant-to-student"], fconn, ns(
            applicant_id=app_id, company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == (
            "Applicant must be accepted or confirmed (current: applied)")
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-create-program-enrollment -- stored row (enrollment + notification).
# No ledger effect: writes only educlaw_program_enrollment, one
# enrollment_confirmed notification and one audit_log line.
# ---------------------------------------------------------------------------
class TestCreateProgramEnrollment:
    def test_create_writes_enrollment_and_confirmation(self, fconn):
        s = _build_env(fconn)
        before_notif = _count(fconn, "educlaw_notification")
        r = call_action(EN["edu-create-program-enrollment"], fconn, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None))
        assert is_ok(r), r
        enr = _row(fconn, "educlaw_program_enrollment", r["id"])
        assert enr["student_id"] == s["student_id"]
        assert enr["program_id"] == s["program_id"]
        assert enr["academic_year_id"] == s["year_id"]
        assert enr["enrollment_status"] == "active"
        assert enr["enrollment_date"] == date.today().isoformat()
        assert enr["company_id"] == s["company_id"]
        assert enr["naming_series"].startswith("PENR-")
        assert _count(fconn, "educlaw_notification") == before_notif + 1
        t = Table("educlaw_notification")
        notif = fconn.execute(
            Q.from_(t).select("*").where(t.reference_id == P()).get_sql(),
            (r["id"],)).fetchone()
        assert notif is not None
        assert dict(notif)["notification_type"] == "enrollment_confirmed"
        assert dict(notif)["recipient_id"] == s["student_id"]
        assert _count(fconn, "sales_invoice") == 0

    def test_refuses_duplicate_enrollment_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        r = call_action(EN["edu-create-program-enrollment"], fconn, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None))
        assert is_ok(r), r
        before = _snapshot(fconn)
        dup = call_action(EN["edu-create-program-enrollment"], fconn, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None))
        assert is_error(dup)
        assert dup["message"] == (
            "Student is already enrolled in this program for this academic year")
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-create-section-enrollment -- stored row (enrollment + section counter).
# No ledger effect: writes only educlaw_course_enrollment (and bumps
# educlaw_section.current_enrollment 0 -> 1) plus one audit_log line.
# ---------------------------------------------------------------------------
class TestCreateSectionEnrollment:
    def test_enroll_writes_row_and_bumps_section_count(self, fconn):
        s = _build_env(fconn)
        call_action(EN["edu-create-program-enrollment"], fconn, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None))
        sec_before = _row(fconn, "educlaw_section", s["section_id"])
        assert sec_before["current_enrollment"] == 0
        r = call_action(EN["edu-create-section-enrollment"], fconn, ns(
            student_id=s["student_id"], section_id=s["section_id"],
            company_id=s["company_id"], is_repeat=None, grade_type=None))
        assert is_ok(r), r
        enr = _row(fconn, "educlaw_course_enrollment", r["id"])
        assert enr["student_id"] == s["student_id"]
        assert enr["section_id"] == s["section_id"]
        assert enr["enrollment_status"] == "enrolled"
        assert enr["grade_type"] == "letter"
        assert enr["is_repeat"] == 0
        assert enr["is_grade_submitted"] == 0
        assert enr["company_id"] == s["company_id"]
        sec_after = _row(fconn, "educlaw_section", s["section_id"])
        assert sec_after["current_enrollment"] == 1
        assert _count(fconn, "sales_invoice") == 0

    def test_refuses_duplicate_section_enrollment_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        call_action(EN["edu-create-program-enrollment"], fconn, ns(
            student_id=s["student_id"], program_id=s["program_id"],
            academic_year_id=s["year_id"], company_id=s["company_id"],
            enrollment_date=None))
        r = call_action(EN["edu-create-section-enrollment"], fconn, ns(
            student_id=s["student_id"], section_id=s["section_id"],
            company_id=s["company_id"], is_repeat=None, grade_type=None))
        assert is_ok(r), r
        before = _snapshot(fconn)
        dup = call_action(EN["edu-create-section-enrollment"], fconn, ns(
            student_id=s["student_id"], section_id=s["section_id"],
            company_id=s["company_id"], is_repeat=None, grade_type=None))
        assert is_error(dup)
        assert dup["message"] == "Student is already enrolled in this section"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-generate-fee-invoice -- stored rows (m678: a real sales invoice).
# Ledger effect: this handler creates a draft sales_invoice through the
# selling module's own create-sales-invoice action and submits it, so the
# submit posts the receivable/income gl_entry legs; educlaw stores its own
# educlaw_fee_invoice link row plus the fee_due notification. The test pins
# the same maths the stub test pinned (5500.00 base, 1000 fixed off, 4500.00
# net) against the real ledger. Money is text throughout.
# ---------------------------------------------------------------------------
class TestGenerateFeeInvoice:
    def test_bills_through_selling_as_submitted_sales_invoice(self, tmp_path, monkeypatch):
        from test_fee_invoice_bills_through_selling import (
            make_full_db, seed_fee_env, setup_fee_structure,
            award_scholarship, generate_fee_invoice_ok,
            delegate_selling_in_process, read_lines, read_gl, read_fee_link,
        )
        path = str(tmp_path / "m413_fee_sell.sqlite")
        make_full_db(path)
        os.environ["ERPCLAW_DB_PATH"] = path
        from erpclaw_lib.cross_skill import _SERVICE_ITEM_CACHE
        _SERVICE_ITEM_CACHE.clear()
        handle = get_connection(path)
        try:
            env = seed_fee_env(handle)
            setup = setup_fee_structure(handle, env)
            award_scholarship(handle, env)
            delegate_selling_in_process(handle, monkeypatch)
            r = generate_fee_invoice_ok(handle, env, path)
            assert r["fee_structure_id"] == setup["fs_id"]
            assert r["base_amount"] == "5500.00"
            assert Decimal(r["base_amount"]) == Decimal("5500.00")
            assert r["total_discount"] == "1000.00"
            assert Decimal(r["total_discount"]) == Decimal("1000")
            assert r["final_amount"] == "4500.00"
            assert Decimal(r["final_amount"]) == Decimal("4500.00")
            assert [(i["discount"], i["billed_amount"]) for i in r["line_items"]] == [
                ("1000.00", "4000.00"), ("0.00", "500.00")]
            assert len(r["scholarships_applied"]) == 1
            assert r["scholarships_applied"][0]["applied_discount"] == "1000.00"
            assert r["sales_invoice_status"] == "submitted"
            si = _row(handle, "sales_invoice", r["sales_invoice_id"])
            assert si["status"] == "submitted"
            assert si["grand_total"] == "4500.00"
            assert si["outstanding_amount"] == "4500.00"
            lines = read_lines(handle, r["sales_invoice_id"])
            assert [(l["quantity"], l["rate"], l["amount"], l["net_amount"])
                    for l in lines] == [
                ("1.00", "4000.00", "4000.00", "4000.00"),
                ("1.00", "500.00", "500.00", "500.00")]
            legs = read_gl(handle, r["sales_invoice_id"])
            assert len(legs) == 2, legs
            link = read_fee_link(handle, r["sales_invoice_id"])
            assert link is not None
            assert link["id"] == r["invoice_id"]
            assert link["amount"] == "4500.00"
            t = Table("educlaw_notification")
            notifs = handle.execute(
                Q.from_(t).select("*").where(t.recipient_id == P()).where(
                    t.notification_type == P()).get_sql(),
                (env["student_id"], "fee_due")).fetchall()
            assert len(notifs) == 1
            assert dict(notifs[0])["reference_type"] == "educlaw_fee_invoice"
            assert dict(notifs[0])["reference_id"] == link["id"]
            assert "4500.00" in dict(notifs[0])["message"]
        finally:
            handle.close()
            os.environ.pop("ERPCLAW_DB_PATH", None)

    def test_refuses_unknown_student_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _fee_setup(fconn, s)
        before = _snapshot(fconn)
        ghost = "00000000-0000-0000-0000-000000000000"
        r = call_action(FE["edu-generate-fee-invoice"], fconn, ns(
            student_id=ghost, program_id=s["program_id"],
            academic_term_id=s["term_id"], company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == "Student %s not found" % ghost
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-generate-progress-report -- stored row (progress_report notifications).
# No ledger effect: writes only educlaw_notification rows (one per recipient),
# no grade or attendance row is created or modified.
# ---------------------------------------------------------------------------
class TestGenerateProgressReport:
    def test_report_counts_and_student_notification(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        att = call_action(AT["edu-record-attendance"], fconn, ns(
            student_id=s["student_id"], attendance_date="2025-09-01",
            attendance_status="present", company_id=s["company_id"],
            section_id=s["section_id"], late_minutes=None, comments=None,
            marked_by=None, source=None))
        assert is_ok(att), att
        before = _snapshot(fconn)
        r = call_action(CO["edu-generate-progress-report"], fconn, ns(
            student_id=s["student_id"], academic_term_id=s["term_id"],
            company_id=s["company_id"]))
        assert is_ok(r), r
        assert r["student_id"] == s["student_id"]
        assert r["academic_term_id"] == s["term_id"]
        assert r["enrollment_count"] == 1
        assert r["attendance_percentage"] == "100.00"
        assert r["notifications_created"] == 1
        assert r["recipients"][0]["recipient_id"] == s["student_id"]
        t = Table("educlaw_notification")
        rows = fconn.execute(
            Q.from_(t).select("*").where(t.notification_type == P()).get_sql(),
            ("progress_report",)).fetchall()
        assert len(rows) == 1
        body = dict(rows[0])
        assert body["recipient_type"] == "student"
        assert body["reference_id"] == s["term_id"]
        assert "Test Student" in body["title"]
        assert "MATH101" in body["message"]
        after = _snapshot(fconn)
        for table in SNAPSHOT_TABLES:
            if table == "educlaw_notification":
                assert len(after[table]) == len(before[table]) + 1
            else:
                assert after[table] == before[table], table

    def test_refuses_unknown_student_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        before = _snapshot(fconn)
        ghost = "00000000-0000-0000-0000-000000000001"
        r = call_action(CO["edu-generate-progress-report"], fconn, ns(
            student_id=ghost, academic_term_id=s["term_id"],
            company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == "Student %s not found" % ghost
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-generate-report-card -- stored row (read-only).
# No ledger effect: pure SELECTs over enrollments/courses/attendance; the
# snapshot equality below is the signal that nothing was written.
# ---------------------------------------------------------------------------
class TestGenerateReportCard:
    def test_card_mirrors_enrollment_and_attendance_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        att = call_action(AT["edu-record-attendance"], fconn, ns(
            student_id=s["student_id"], attendance_date="2025-09-01",
            attendance_status="present", company_id=s["company_id"],
            section_id=s["section_id"], late_minutes=None, comments=None,
            marked_by=None, source=None))
        assert is_ok(att), att
        stu = _row(fconn, "educlaw_student", s["student_id"])
        before = _snapshot(fconn)
        r = call_action(GR["edu-generate-report-card"], fconn, ns(
            student_id=s["student_id"], academic_term_id=s["term_id"]))
        assert is_ok(r), r
        assert r["academic_term_id"] == s["term_id"]
        assert r["student"]["id"] == s["student_id"]
        assert r["student"]["full_name"] == stu["full_name"] == "Test Student"
        assert r["student"]["grade_level"] == stu["grade_level"] == "10"
        assert len(r["courses"]) == 1
        assert r["courses"][0]["course_code"] == "MATH101"
        assert r["courses"][0]["credit_hours"] == "3"
        assert r["attendance"]["total_days"] == 1
        assert r["attendance"]["present"] == 1
        assert _snapshot(fconn) == before

    def test_refuses_unknown_student_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        before = _snapshot(fconn)
        ghost = "00000000-0000-0000-0000-000000000002"
        r = call_action(GR["edu-generate-report-card"], fconn, ns(
            student_id=ghost, academic_term_id=s["term_id"]))
        assert is_error(r)
        assert r["message"] == "Student %s not found" % ghost
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-generate-section-grade -- stored row (read-only preview).
# No ledger effect and no enrollment effect: is_preview True; the graded
# enrollment row keeps final_letter_grade "", is_grade_submitted 0 and status
# enrolled. The grade_setup scale maps 85 -> A on purpose (A covers 80-100),
# so the letter assertion pins the scale math, not a fallback.
# ---------------------------------------------------------------------------
class TestGenerateSectionGrade:
    def test_preview_maths_and_enrollment_untouched(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        _grade_setup(fconn, s, points="85")
        t = Table("educlaw_course_enrollment")
        enr_before = fconn.execute(
            Q.from_(t).select("*").where(t.student_id == P()).where(
                t.section_id == P()).get_sql(),
            (s["student_id"], s["section_id"])).fetchone()
        enr_id = dict(enr_before)["id"]
        before = _snapshot(fconn)
        r = call_action(GR["edu-generate-section-grade"], fconn, ns(
            section_id=s["section_id"], student_id=s["student_id"]))
        assert is_ok(r), r
        assert r["student_id"] == s["student_id"]
        assert r["section_id"] == s["section_id"]
        assert r["percentage"] == "85.00"
        assert Decimal(r["percentage"]) == Decimal("85.00")
        assert r["letter_grade"] == "A"
        assert Decimal(r["grade_points"]) == Decimal("4.0")
        assert r["is_preview"] is True
        enr_after = _row(fconn, "educlaw_course_enrollment", enr_id)
        assert enr_after["final_letter_grade"] == ""
        assert enr_after["is_grade_submitted"] == 0
        assert enr_after["enrollment_status"] == "enrolled"
        assert _snapshot(fconn) == before

    def test_refuses_missing_section_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        _grade_setup(fconn, s, points="85")
        before = _snapshot(fconn)
        r = call_action(GR["edu-generate-section-grade"], fconn, ns(
            section_id=None, student_id=s["student_id"]))
        assert is_error(r)
        assert r["message"] == "--section-id is required"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-generate-student-record -- stored row (payload + one access log).
# No ledger effect: the only write is a single educlaw_data_access_log row
# (access_type export, data_category grades); the student, enrollment,
# attendance and consent tables are only read.
# ---------------------------------------------------------------------------
class TestGenerateStudentRecord:
    def test_record_mirrors_student_and_logs_single_export(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        att = call_action(AT["edu-record-attendance"], fconn, ns(
            student_id=s["student_id"], attendance_date="2025-09-01",
            attendance_status="present", company_id=s["company_id"],
            section_id=s["section_id"], late_minutes=None, comments=None,
            marked_by=None, source=None))
        assert is_ok(att), att
        stu = _row(fconn, "educlaw_student", s["student_id"])
        logs_before = _count(fconn, "educlaw_data_access_log")
        snap_before = _snapshot(fconn)
        r = call_action(ST["edu-generate-student-record"], fconn, ns(
            student_id=s["student_id"], user_id="admin",
            company_id=s["company_id"]))
        assert is_ok(r), r
        assert r["student"]["id"] == s["student_id"]
        assert r["student"]["full_name"] == stu["full_name"] == "Test Student"
        assert r["student"]["email"] == stu["email"]
        assert len(r["course_enrollments"]) == 1
        assert r["course_enrollments"][0]["course_code"] == "MATH101"
        assert len(r["attendance_records"]) == 1
        assert r["attendance_records"][0]["attendance_status"] == "present"
        assert r["consent_records"] == []
        assert r["exported_by"] == "admin"
        assert _count(fconn, "educlaw_data_access_log") == logs_before + 1
        log = _row(fconn, "educlaw_data_access_log", r["access_log_id"])
        assert log["student_id"] == s["student_id"]
        assert log["data_category"] == "grades"
        assert log["access_type"] == "export"
        assert log["user_id"] == "admin"
        snap_after = _snapshot(fconn)
        for table in SNAPSHOT_TABLES:
            if table == "educlaw_data_access_log":
                assert len(snap_after[table]) == len(snap_before[table]) + 1
            else:
                assert snap_after[table] == snap_before[table], table

    def test_refuses_unknown_student_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _enroll_program_and_section(fconn, s)
        before = _snapshot(fconn)
        ghost = "00000000-0000-0000-0000-000000000003"
        r = call_action(ST["edu-generate-student-record"], fconn, ns(
            student_id=ghost, user_id="admin", company_id=s["company_id"]))
        assert is_error(r)
        assert r["message"] == "Student %s not found" % ghost
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-get-academic-term -- stored row (read-only).
# No ledger effect: pure SELECT plus a section COUNT; snapshot equality is
# the signal that the read wrote nothing.
# ---------------------------------------------------------------------------
class TestGetAcademicTerm:
    def test_payload_mirrors_term_and_section_count(self, fconn):
        s = _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(AC["edu-get-academic-term"], fconn, ns(
            term_id=s["term_id"]))
        assert is_ok(r), r
        row = _row(fconn, "educlaw_academic_term", s["term_id"])
        for key in ("name", "term_type", "academic_year_id", "start_date",
                    "end_date", "company_id"):
            assert r[key] == row[key], key
        assert row["status"] == "active"
        # BUG (documented, not fixed): same envelope shadowing as
        # edu-get-applicant -- the response "status": "ok" overwrites the
        # term row's own status ("active"), so it is unreadable here.
        assert r["status"] == "ok"
        assert r["section_count"] == 1
        assert _snapshot(fconn) == before

    def test_refuses_unknown_term_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(AC["edu-get-academic-term"], fconn, ns(
            term_id="no-such-term"))
        assert is_error(r)
        assert r["message"] == "Academic term no-such-term not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-get-academic-year -- stored row (read-only).
# No ledger effect: pure SELECT plus the terms list; snapshot equality is
# the signal that the read wrote nothing.
# ---------------------------------------------------------------------------
class TestGetAcademicYear:
    def test_payload_mirrors_year_and_terms(self, fconn):
        s = _build_env(fconn)
        other_term = _helpers.seed_academic_term(
            fconn, s["company_id"], s["year_id"])
        before = _snapshot(fconn)
        r = call_action(AC["edu-get-academic-year"], fconn, ns(
            year_id=s["year_id"]))
        assert is_ok(r), r
        row = _row(fconn, "educlaw_academic_year", s["year_id"])
        for key in ("name", "start_date", "end_date", "company_id"):
            assert r[key] == row[key], key
        term_ids = sorted(t["id"] for t in r["terms"])
        assert term_ids == sorted([s["term_id"], other_term])
        assert _snapshot(fconn) == before
        assert _row(fconn, "educlaw_academic_term",
                    other_term)["academic_year_id"] == s["year_id"]

    def test_refuses_unknown_year_and_writes_nothing(self, fconn):
        _build_env(fconn)
        before = _snapshot(fconn)
        r = call_action(AC["edu-get-academic-year"], fconn, ns(
            year_id="no-such-year"))
        assert is_error(r)
        assert r["message"] == "Academic year no-such-year not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-get-announcement -- stored row (read-only).
# No ledger effect: pure SELECT plus a notification COUNT; snapshot equality
# is the signal that the read wrote nothing. The seed goes through PyPika
# insert_row (the owner action edu-add-announcement stores NULL published_by,
# which the pre-existing TestAnnouncement works around with raw SQL).
# ---------------------------------------------------------------------------
class TestGetAnnouncement:
    def test_payload_mirrors_announcement_and_counts_notifications(self, fconn):
        s = _build_env(fconn)
        ann_id = _seed_announcement(fconn, s["company_id"])
        before = _snapshot(fconn)
        r = call_action(CO["edu-get-announcement"], fconn, ns(
            announcement_id=ann_id))
        assert is_ok(r), r
        row = _row(fconn, "educlaw_announcement", ann_id)
        for key in ("title", "body", "priority", "audience_type",
                    "announcement_status", "company_id"):
            assert r[key] == row[key], key
        assert r["title"] == "Storm Closure"
        assert r["notifications_sent"] == 0
        assert _snapshot(fconn) == before
        n = call_action(CO["edu-submit-notification"], fconn, ns(
            recipient_type="student", recipient_id=s["student_id"],
            notification_type="announcement", title="Hi", message="Read this",
            company_id=s["company_id"], reference_type="announcement",
            reference_id=ann_id, sent_via=None))
        assert is_ok(n), n
        r2 = call_action(CO["edu-get-announcement"], fconn, ns(
            announcement_id=ann_id))
        assert is_ok(r2), r2
        assert r2["notifications_sent"] == 1

    def test_refuses_unknown_announcement_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _seed_announcement(fconn, s["company_id"])
        before = _snapshot(fconn)
        r = call_action(CO["edu-get-announcement"], fconn, ns(
            announcement_id="no-such-announcement"))
        assert is_error(r)
        assert r["message"] == "Announcement no-such-announcement not found"
        assert _snapshot(fconn) == before


# ---------------------------------------------------------------------------
# edu-get-applicant -- stored row (read-only).
# No ledger effect: pure SELECT; snapshot equality is the signal that the
# read wrote nothing. A second applicant proves neighbours are untouched.
# ---------------------------------------------------------------------------
class TestGetApplicant:
    def test_payload_mirrors_applicant_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        app_id = _add_applicant(fconn, s["company_id"])
        other_id = _add_applicant(fconn, s["company_id"], first="Other",
                                  last="Person", email="other@test.com")
        before = _snapshot(fconn)
        r = call_action(ST["edu-get-applicant"], fconn, ns(applicant_id=app_id))
        assert is_ok(r), r
        row = _row(fconn, "educlaw_student_applicant", app_id)
        for key in ("first_name", "last_name", "date_of_birth", "email",
                    "naming_series", "company_id"):
            assert r[key] == row[key], key
        assert r["first_name"] == "Conv"
        assert row["status"] == "applied"
        # BUG (documented, not fixed): the response envelope's "status": "ok"
        # shadows the applicant row's own status ("applied") -- ok() overwrites
        # the row key, so callers cannot read the applicant's real status here.
        assert r["status"] == "ok"
        # BUG (documented, not fixed): the intake accepted grade_level="10"
        # but the applicant table has no such column, so the value was
        # silently dropped -- neither the row nor the payload carries it.
        assert "grade_level" not in row
        assert "grade_level" not in r
        assert _snapshot(fconn) == before
        other = _row(fconn, "educlaw_student_applicant", other_id)
        assert other["first_name"] == "Other"
        by_series = call_action(ST["edu-get-applicant"], fconn, ns(
            naming_series=row["naming_series"]))
        assert is_ok(by_series), by_series
        assert by_series["id"] == app_id

    def test_refuses_missing_selector_and_writes_nothing(self, fconn):
        s = _build_env(fconn)
        _add_applicant(fconn, s["company_id"])
        before = _snapshot(fconn)
        r = call_action(ST["edu-get-applicant"], fconn, ns())
        assert is_error(r)
        assert r["message"] == "--applicant-id or --naming-series is required"
        assert _snapshot(fconn) == before
