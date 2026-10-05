"""L1 pytest tests for EduClaw Higher Education — 60 actions across 7 domains.

Tests: registrar (~10), records (~5), finaid (~5), alumni (~5),
       faculty (~5), admissions (~5), reports (~5) = ~40 tests.
"""
import importlib.util
import pytest
import sys
import os

from decimal import Decimal

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

from erpclaw_lib.query import Q, P, Table, Field

REG_ACTIONS = _load("registrar", _SCRIPTS_DIR).ACTIONS
REC_ACTIONS = _load("records", _SCRIPTS_DIR).ACTIONS
FIN_ACTIONS = _load("finaid", _SCRIPTS_DIR).ACTIONS
ALU_ACTIONS = _load("alumni", _SCRIPTS_DIR).ACTIONS
FAC_ACTIONS = _load("faculty", _SCRIPTS_DIR).ACTIONS
ADM_ACTIONS = _load("admissions", _SCRIPTS_DIR).ACTIONS
RPT_ACTIONS = _load("reports", _SCRIPTS_DIR).ACTIONS


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
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "year_id": yid, "term_id": tid,
    }
    conn.close()


def _package_rows(conn):
    t = Table("educlaw_scholarship")
    q = Q.from_(t).select(t.star)
    rows = conn.execute(q.get_sql()).fetchall()
    return sorted(
        (dict(r) for r in rows),
        key=lambda d: repr(sorted((k, str(v)) for k, v in d.items())),
    )


def _table_count(conn, table):
    t = Table(table)
    q = Q.from_(t).select(t.star)
    return len(conn.execute(q.get_sql()).fetchall())


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRAR domain
# ══════════════════════════════════════════════════════════════════════════════

class TestDegreeProgram:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
            company_id=cid, name="Computer Science", degree_type="bachelor",
            department="Engineering", credits_required=120,
            program_status="active",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(REG_ACTIONS["highered-list-degree-programs"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_update(self, setup):
        conn, cid = setup
        r = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
            company_id=cid, name="Biology", degree_type="bachelor",
            department="Science", credits_required=120,
            program_status="active",
        ))
        assert is_ok(r)
        r2 = call_action(REG_ACTIONS["highered-update-degree-program"], conn, ns(
            id=r["id"], name="Biology Updated", degree_type=None,
            department=None, credits_required=None, program_status=None,
        ))
        assert is_ok(r2)

    def test_missing_name(self, setup):
        conn, cid = setup
        r = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
            company_id=cid, name=None, degree_type="bachelor",
            department=None, credits_required=None, program_status=None,
        ))
        assert is_error(r)


class TestCourse:
    def test_add(self, setup):
        conn, cid = setup
        # Need a program first
        prog = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
            company_id=cid, name="CS Program", degree_type="bachelor",
            department="CS", credits_required=120, program_status="active",
        ))
        r = call_action(REG_ACTIONS["highered-add-course"], conn, ns(
            company_id=cid, name="Intro to CS", code="CS101",
            credits=3, program_id=prog["id"],
            prerequisites=None, description="Intro course",
            is_active=1,
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(REG_ACTIONS["highered-list-courses"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestSection:
    def test_add(self, setup):
        conn, cid = setup
        prog = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
            company_id=cid, name="CS Prog", degree_type="bachelor",
            department="CS", credits_required=120, program_status="active",
        ))
        course = call_action(REG_ACTIONS["highered-add-course"], conn, ns(
            company_id=cid, name="CS 101", code="CS101",
            credits=3, program_id=prog["id"],
            prerequisites=None, description=None, is_active=1,
        ))
        r = call_action(REG_ACTIONS["highered-add-section"], conn, ns(
            company_id=cid, course_id=course["id"],
            term="Fall", year=2025, instructor="Dr. Smith",
            capacity=30, schedule="MWF 9-10", location="Room 101",
            section_status="open",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(REG_ACTIONS["highered-list-sections"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestEnrollment:
    def test_add(self, full_setup):
        s = full_setup
        prog = call_action(REG_ACTIONS["highered-add-degree-program"], s["conn"], ns(
            company_id=s["company_id"], name="CS", degree_type="bachelor",
            department="CS", credits_required=120, program_status="active",
        ))
        course = call_action(REG_ACTIONS["highered-add-course"], s["conn"], ns(
            company_id=s["company_id"], name="CS 101", code="CS101",
            credits=3, program_id=prog["id"],
            prerequisites=None, description=None, is_active=1,
        ))
        section = call_action(REG_ACTIONS["highered-add-section"], s["conn"], ns(
            company_id=s["company_id"], course_id=course["id"],
            term="Fall", year=2025, instructor="Dr. Smith",
            capacity=30, schedule="MWF 9-10", location="Room 101",
            section_status="open",
        ))
        r = call_action(REG_ACTIONS["highered-add-enrollment"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            section_id=section["id"], enrollment_date="2025-08-25",
            enrollment_status="enrolled", grade=None, grade_points=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(REG_ACTIONS["highered-list-enrollments"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# RECORDS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestHolds:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-add-hold"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            hold_type="financial", reason="Unpaid balance",
            placed_by="Bursar", hold_status=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-list-holds"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            hold_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestStudentRecord:
    def test_get(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-get-student-record"], s["conn"], ns(
            id=s["student_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-list-student-records"], s["conn"], ns(
            company_id=s["company_id"], limit=50, offset=0,
        ))
        assert is_ok(r)


class TestAcademicStanding:
    def test_update(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-update-academic-standing"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
            academic_standing="probation",
        ))
        assert is_ok(r)


class TestGPA:
    def test_calculate(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-calculate-gpa"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)


class TestTranscript:
    def test_generate(self, full_setup):
        s = full_setup
        r = call_action(REC_ACTIONS["highered-generate-transcript"], s["conn"], ns(
            student_id=s["student_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)


class TestDegreeAudit:
    def test_audit(self, full_setup):
        s = full_setup
        prog = call_action(REG_ACTIONS["highered-add-degree-program"], s["conn"], ns(
            company_id=s["company_id"], name="CS", degree_type="bachelor",
            department="CS", credits_required=120, program_status="active",
        ))
        # Assign program to student (degree_audit reads from student record)
        s["conn"].execute(
            "UPDATE educlaw_student SET program_id=? WHERE id=?",
            (prog["id"], s["student_id"]))
        s["conn"].commit()
        r = call_action(REC_ACTIONS["highered-degree-audit"], s["conn"], ns(
            student_id=s["student_id"], program_id=prog["id"],
            company_id=s["company_id"],
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# FINAID domain (highered-specific)
# ══════════════════════════════════════════════════════════════════════════════

class TestAidPackage:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(FIN_ACTIONS["highered-add-aid-package"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            aid_year="2025-2026", total_cost="30000", efc="5000",
            total_need="25000", grants="10000", scholarships="5000",
            loans="7000", work_study="3000", package_status="offered",
        ))
        assert is_ok(r)

    def test_add_stores_exact_money_text(self, full_setup):
        s = full_setup
        conn, cid, sid = s["conn"], s["company_id"], s["student_id"]
        n_before = _table_count(conn, "educlaw_scholarship")
        disb_before = _table_count(conn, "highered_disbursement")
        r = call_action(FIN_ACTIONS["highered-add-aid-package"], conn, ns(
            company_id=cid, student_id=sid,
            aid_year="2025-2026", total_cost="50000", efc="10000",
            total_need="40000", grants="5000", scholarships="5000",
            loans="3000", work_study="2000", package_status=None,
        ))
        assert is_ok(r)
        assert r["total_aid"] == "15000.00"
        assert Decimal(str(r["total_aid"])) == Decimal("15000.00")
        assert r["package_status"] == "draft"
        assert _table_count(conn, "educlaw_scholarship") == n_before + 1
        t = Table("educlaw_scholarship")
        q = Q.from_(t).select(t.star).where(Field("id") == P())
        row = conn.execute(q.get_sql(), (r["id"],)).fetchone()
        assert row is not None
        stored = dict(row)
        assert stored["student_id"] == sid
        assert stored["company_id"] == cid
        assert stored["aid_year"] == "2025-2026"
        assert stored["package_status"] == "draft"
        assert stored["total_cost"] == "50000.00"
        assert stored["efc"] == "10000.00"
        assert stored["total_need"] == "40000.00"
        assert stored["grants"] == "5000.00"
        assert stored["scholarships"] == "5000.00"
        assert stored["loans"] == "3000.00"
        assert stored["work_study"] == "2000.00"
        assert stored["total_aid"] == "15000.00"
        assert Decimal(str(stored["total_aid"])) == (
            Decimal(str(stored["grants"]))
            + Decimal(str(stored["scholarships"]))
            + Decimal(str(stored["loans"]))
            + Decimal(str(stored["work_study"]))
        )
        assert _table_count(conn, "highered_disbursement") == disb_before

    def test_add_missing_student_id_writes_nothing(self, full_setup):
        s = full_setup
        conn = s["conn"]
        before = _package_rows(conn)
        r = call_action(FIN_ACTIONS["highered-add-aid-package"], conn, ns(
            company_id=s["company_id"], student_id=None,
            aid_year="2025-2026", total_cost="50000", efc="10000",
            total_need="40000", grants="5000", scholarships="5000",
            loans="3000", work_study="2000", package_status=None,
        ))
        assert is_error(r)
        assert "student" in r["message"].lower()
        assert _package_rows(conn) == before

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FIN_ACTIONS["highered-list-aid-packages"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# ALUMNI domain
# ══════════════════════════════════════════════════════════════════════════════

class TestAlumnus:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(ALU_ACTIONS["highered-add-alumnus"], conn, ns(
            company_id=cid, name="John Doe", email="john@alumni.edu",
            graduation_year=2020, degree_program="Computer Science",
            employer="Tech Corp", job_title="Engineer",
            engagement_level="high", is_donor=0,
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(ALU_ACTIONS["highered-list-alumni"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_update(self, setup):
        conn, cid = setup
        r = call_action(ALU_ACTIONS["highered-add-alumnus"], conn, ns(
            company_id=cid, name="Jane Doe", email="jane@alumni.edu",
            graduation_year=2021, degree_program="Math",
            employer=None, job_title=None,
            engagement_level=None, is_donor=0,
        ))
        assert is_ok(r)
        r2 = call_action(ALU_ACTIONS["highered-update-alumnus"], conn, ns(
            id=r["id"], employer="New Corp", job_title="Manager",
            name=None, email=None, graduation_year=None,
            degree_program=None, engagement_level=None, is_donor=None,
        ))
        assert is_ok(r2)


class TestAlumniEvent:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(ALU_ACTIONS["highered-add-alumni-event"], conn, ns(
            company_id=cid, name="Homecoming 2025",
            event_date="2025-10-15", event_type="reunion",
            description="Annual homecoming", attendees=200,
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(ALU_ACTIONS["highered-list-alumni-events"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestGivingRecord:
    def test_add(self, setup):
        conn, cid = setup
        alumnus = call_action(ALU_ACTIONS["highered-add-alumnus"], conn, ns(
            company_id=cid, name="Donor Test", email="donor@test.edu",
            graduation_year=2015, degree_program="CS",
            employer=None, job_title=None,
            engagement_level=None, is_donor=1,
        ))
        r = call_action(ALU_ACTIONS["highered-add-giving-record"], conn, ns(
            company_id=cid, alumnus_id=alumnus["id"],
            amount="5000", giving_date="2025-03-01",
            campaign="Annual Fund", gift_type="cash",
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# FACULTY domain
# ══════════════════════════════════════════════════════════════════════════════

class TestFaculty:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(FAC_ACTIONS["highered-add-faculty"], conn, ns(
            company_id=cid, name="Dr. Smith",
            department="CS", rank="professor",
            tenure_status="tenured", hire_date="2010-01-15",
            email=None,
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(FAC_ACTIONS["highered-list-faculty"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_update(self, setup):
        conn, cid = setup
        r = call_action(FAC_ACTIONS["highered-add-faculty"], conn, ns(
            company_id=cid, name="Dr. Jones",
            department="Math", rank="associate_professor",
            tenure_status="tenure_track", hire_date="2015-09-01",
            email=None,
        ))
        assert is_ok(r)
        r2 = call_action(FAC_ACTIONS["highered-update-faculty"], conn, ns(
            id=r["id"], rank="professor", tenure_status="tenured",
            name=None, department=None, hire_date=None, email=None,
        ))
        assert is_ok(r2)


class TestResearchGrant:
    def test_add(self, setup):
        conn, cid = setup
        fac = call_action(FAC_ACTIONS["highered-add-faculty"], conn, ns(
            company_id=cid, name="Dr. Grant",
            department="Physics", rank="professor",
            tenure_status="tenured", hire_date="2008-01-01",
            email=None,
        ))
        r = call_action(FAC_ACTIONS["highered-add-research-grant"], conn, ns(
            company_id=cid, faculty_id=fac["id"],
            title="Quantum Research", funding_agency="NSF",
            amount="100000", start_date="2025-01-01",
            end_date="2027-12-31", grant_status="active",
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(FAC_ACTIONS["highered-list-research-grants"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# ADMISSIONS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestApplication:
    def test_add(self, setup):
        conn, cid = setup
        prog = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
            company_id=cid, name="CS", degree_type="bachelor",
            department="CS", credits_required=120, program_status="active",
        ))
        r = call_action(ADM_ACTIONS["highered-add-application"], conn, ns(
            company_id=cid, name="Applicant Test",
            email="applicant@test.edu", phone="555-1234",
            program_id=prog["id"], application_date="2025-03-01",
            gpa_incoming="3.5", test_scores="SAT:1400",
            documents=None, application_status=None,
        ))
        assert is_ok(r)

    def test_list(self, setup):
        conn, cid = setup
        r = call_action(ADM_ACTIONS["highered-list-applications"], conn, ns(
            company_id=cid, application_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


class TestAdmissionDecision:
    def test_list(self, setup):
        conn, cid = setup
        r = call_action(ADM_ACTIONS["highered-list-admission-decisions"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestEnrollmentReport:
    def test_generate(self, setup):
        conn, cid = setup
        r = call_action(RPT_ACTIONS["highered-enrollment-report"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestRetentionReport:
    def test_generate(self, setup):
        conn, cid = setup
        r = call_action(RPT_ACTIONS["highered-retention-report"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestAlumniGivingReport:
    def test_generate(self, setup):
        conn, cid = setup
        r = call_action(RPT_ACTIONS["highered-alumni-giving-summary"], conn, ns(
            company_id=cid, limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# IPEDS completions preview v1: traceable candidate counts, read only
# ══════════════════════════════════════════════════════════════════════════════

def _preview_program(conn, cid, name="Preview CS", credits=120):
    r = call_action(REG_ACTIONS["highered-add-degree-program"], conn, ns(
        company_id=cid, name=name, degree_type="bachelor",
        department="CS", credits_required=credits, program_status="active",
    ))
    assert is_ok(r)
    return r["id"]


def _preview_student(conn, cid, program_id, total_credits, gpa):
    import uuid as _uuid
    rid = str(_uuid.uuid4())
    sid = str(_uuid.uuid4())
    conn.execute(
        "INSERT INTO educlaw_student"
        " (id, naming_series, student_id, name, program_id,"
        " total_credits, gpa, company_id, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, "HSTU-" + rid[:8], sid, "Preview Student",
         program_id, total_credits, gpa, cid,
         "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    return sid


def _preview_snapshot(conn, tables):
    out = {}
    for t in tables:
        tbl = Table(t)
        rows = conn.execute(Q.from_(tbl).select(tbl.star).get_sql()).fetchall()
        out[t] = sorted(
            repr(sorted((k, str(v)) for k, v in dict(r).items())) for r in rows
        )
    return out


class TestIpedsCompletionsPreview:
    def test_eligible_and_ineligible_counts(self, setup):
        conn, cid = setup
        prog = _preview_program(conn, cid)
        _preview_student(conn, cid, prog, 130, "3.50")
        _preview_student(conn, cid, prog, 30, "3.00")
        before = _preview_snapshot(
            conn, ["educlaw_student", "highered_degree_program", "audit_log"])
        r = call_action(
            RPT_ACTIONS["highered-ipeds-completions-preview"],
            conn, ns(company_id=cid),
        )
        assert is_ok(r)
        assert r["survey"] == "Completions"
        assert r["mode"] == "preview"
        assert r["certifiable"] is False
        assert r["company_id"] == cid
        assert len(r["programs"]) == 1
        row = r["programs"][0]
        assert row["program_id"] == prog
        assert row["student_count"] == 2
        assert row["eligible_candidate_count"] == 1
        assert r["total_students"] == 2
        assert r["total_eligible_candidates"] == 1
        assert "highered_degree_program" in str(r.get("sources", "")) or \
            "highered_degree_program" in str(r.get("source_tables", ""))
        assert "educlaw_student" in str(r.get("sources", "")) or \
            "educlaw_student" in str(r.get("source_tables", ""))
        assert _preview_snapshot(
            conn, ["educlaw_student", "highered_degree_program", "audit_log"]) == before

    def test_other_company_student_excluded(self, setup):
        conn, cid = setup
        prog = _preview_program(conn, cid)
        _preview_student(conn, cid, prog, 130, "3.50")
        other = seed_company(conn)
        _preview_student(conn, other, prog, 150, "4.00")
        r = call_action(
            RPT_ACTIONS["highered-ipeds-completions-preview"],
            conn, ns(company_id=cid),
        )
        assert is_ok(r)
        assert r["total_students"] == 1
        assert r["total_eligible_candidates"] == 1
        assert r["programs"][0]["student_count"] == 1
        assert r["programs"][0]["eligible_candidate_count"] == 1

    def test_exact_decimal_boundary_qualifies(self, setup):
        conn, cid = setup
        prog = _preview_program(conn, cid, credits=120)
        _preview_student(conn, cid, prog, "120.00", "2.00")
        r = call_action(
            RPT_ACTIONS["highered-ipeds-completions-preview"],
            conn, ns(company_id=cid),
        )
        assert is_ok(r)
        assert r["programs"][0]["student_count"] == 1
        assert r["programs"][0]["eligible_candidate_count"] == 1
        assert r["total_eligible_candidates"] == 1

    def test_invalid_gpa_does_not_crash_or_qualify(self, setup):
        conn, cid = setup
        prog = _preview_program(conn, cid)
        _preview_student(conn, cid, prog, 150, "not-a-gpa")
        r = call_action(
            RPT_ACTIONS["highered-ipeds-completions-preview"],
            conn, ns(company_id=cid),
        )
        assert is_ok(r)
        assert r["programs"][0]["student_count"] == 1
        assert r["programs"][0]["eligible_candidate_count"] == 0
        assert r["total_eligible_candidates"] == 0

    def test_missing_company_id_refuses_without_writes(self, setup):
        conn, cid = setup
        prog = _preview_program(conn, cid)
        _preview_student(conn, cid, prog, 130, "3.50")
        before = _preview_snapshot(
            conn, ["educlaw_student", "highered_degree_program", "audit_log"])
        r = call_action(
            RPT_ACTIONS["highered-ipeds-completions-preview"],
            conn, ns(company_id=None),
        )
        assert is_error(r)
        assert _preview_snapshot(
            conn, ["educlaw_student", "highered_degree_program", "audit_log"]) == before
