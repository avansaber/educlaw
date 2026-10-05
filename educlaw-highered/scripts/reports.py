"""EduClaw Higher Education — reports domain module (6 actions + status)

Cross-domain reports: enrollment, retention, degree completion, alumni giving, faculty workload.
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

try:
    import importlib.util
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))
    from erpclaw_lib.db import DEFAULT_DB_PATH
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row
except ImportError:
    DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")

SKILL = "highered-educlaw-highered"


def enrollment_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT s.term, s.year, COUNT(e.id) as total_enrolled,
               SUM(CASE WHEN e.enrollment_status = 'enrolled' THEN 1 ELSE 0 END) as active,
               SUM(CASE WHEN e.enrollment_status = 'dropped' THEN 1 ELSE 0 END) as dropped,
               SUM(CASE WHEN e.enrollment_status = 'withdrawn' THEN 1 ELSE 0 END) as withdrawn,
               SUM(CASE WHEN e.enrollment_status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        WHERE s.company_id=?
        GROUP BY s.term, s.year
        ORDER BY s.year DESC, s.term
    """, (company_id,)).fetchall()
    ok({"enrollment": [dict(r) for r in rows], "count": len(rows)})


def retention_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t = Table("educlaw_student")
    total = conn.execute(
        Q.from_(t).select(fn.Count(t.star).as_("cnt"))
        .where(t.company_id == P()).get_sql(),
        (company_id,)
    ).fetchone()["cnt"]
    active = conn.execute(
        Q.from_(t).select(fn.Count(t.star).as_("cnt"))
        .where(t.company_id == P())
        .where(t.academic_standing.notin(["suspension", "dismissal"])).get_sql(),
        (company_id,)
    ).fetchone()["cnt"]
    retention_rate = round(active / total * 100, 1) if total > 0 else 0
    ok({
        "total_students": total,
        "active_students": active,
        "attrited": total - active,
        "retention_rate": retention_rate,
    })


def degree_completion_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT dp.name as program, dp.degree_type, dp.credits_required,
               COUNT(sr.id) as total_students,
               SUM(CASE WHEN sr.total_credits >= dp.credits_required AND sr.gpa >= '2.00'
                   THEN 1 ELSE 0 END) as eligible_for_graduation
        FROM educlaw_student sr
        JOIN highered_degree_program dp ON sr.program_id = dp.id
        WHERE sr.company_id=?
        GROUP BY dp.id
        ORDER BY dp.name
    """, (company_id,)).fetchall()
    ok({"programs": [dict(r) for r in rows], "count": len(rows)})


def alumni_giving_summary(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t_alum = Table("highered_alumnus")
    total_donors = conn.execute(
        Q.from_(t_alum).select(fn.Count(t_alum.star).as_("cnt"))
        .where(t_alum.company_id == P()).where(t_alum.is_donor == 1).get_sql(),
        (company_id,)
    ).fetchone()["cnt"]
    total_alumni = conn.execute(
        Q.from_(t_alum).select(fn.Count(t_alum.star).as_("cnt"))
        .where(t_alum.company_id == P()).get_sql(),
        (company_id,)
    ).fetchone()["cnt"]
    # PyPika: skipped — COALESCE+SUM+CAST aggregate
    total_giving = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS NUMERIC)), 0) as total FROM highered_giving_record WHERE company_id=?",
        (company_id,)
    ).fetchone()["total"]
    participation = round(total_donors / total_alumni * 100, 1) if total_alumni > 0 else 0
    ok({
        "total_alumni": total_alumni,
        "total_donors": total_donors,
        "participation_rate": participation,
        "total_giving": total_giving,
    })


def faculty_workload_summary(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT f.department,
               COUNT(DISTINCT f.id) as faculty_count,
               COUNT(ca.id) as total_assignments,
               ROUND(CAST(COUNT(ca.id) AS REAL) / MAX(COUNT(DISTINCT f.id), 1), 1) as avg_load
        FROM educlaw_instructor f
        LEFT JOIN highered_course_assignment ca ON ca.faculty_id = f.id
        WHERE f.company_id=?
        GROUP BY f.department
        ORDER BY f.department
    """, (company_id,)).fetchall()
    ok({"departments": [dict(r) for r in rows], "count": len(rows)})


PROGRAM_TABLE = "highered_degree_program"
STUDENT_TABLE = "educlaw_student"
MIN_PREVIEW_GPA = Decimal("2.00")


def _preview_decimal(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        text_value = str(value).strip()
    except Exception:
        return None
    if text_value == "":
        return None
    try:
        return Decimal(text_value)
    except (InvalidOperation, ValueError, AttributeError, TypeError):
        return None


def ipeds_completions_preview(conn, args):
    """IPEDS Completions preview over stored records.

    Traceable candidate counts per active degree program. A stored row
    counts as an eligible candidate only when its stored credit total
    reaches the program threshold and its stored GPA reaches 2.00.
    Read only; preview only and not a certified submission.
    """
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    prog = Table(PROGRAM_TABLE)
    prog_q = (
        Q.from_(prog)
        .select(prog.id, prog.name, prog.degree_type, prog.credits_required)
        .where(prog.company_id == P())
        .where(prog.program_status == P())
        .orderby(prog.id)
    )
    prog_rows = conn.execute(prog_q.get_sql(), (company_id, "active")).fetchall()
    stu = Table(STUDENT_TABLE)
    stu_q = (
        Q.from_(stu)
        .select(
            stu.program_id,
            stu.total_credits,
            stu.total_credits_earned,
            stu.gpa,
            stu.cumulative_gpa,
        )
        .where(stu.company_id == P())
    )
    stu_rows = [dict(r) for r in conn.execute(stu_q.get_sql(), (company_id,)).fetchall()]
    programs = []
    total_students = 0
    total_eligible = 0
    for p in prog_rows:
        prog_id = p["id"]
        required = _preview_decimal(p["credits_required"])
        members = [s for s in stu_rows if s.get("program_id") == prog_id]
        student_count = len(members)
        eligible = 0
        if required is not None:
            for s in members:
                credit_options = (
                    _preview_decimal(s.get("total_credits")),
                    _preview_decimal(s.get("total_credits_earned")),
                )
                gpa_options = (
                    _preview_decimal(s.get("gpa")),
                    _preview_decimal(s.get("cumulative_gpa")),
                )
                credits_ok = any(
                    c is not None and c >= required for c in credit_options
                )
                gpa_ok = any(
                    g is not None and g >= MIN_PREVIEW_GPA for g in gpa_options
                )
                if credits_ok and gpa_ok:
                    eligible += 1
        total_students += student_count
        total_eligible += eligible
        programs.append({
            "program_id": prog_id,
            "name": p["name"],
            "program_name": p["name"],
            "degree_type": p["degree_type"],
            "credits_required": p["credits_required"],
            "student_count": student_count,
            "eligible_candidate_count": eligible,
            "eligible_count": eligible,
            "eligible_candidates": eligible,
        })
    programs = sorted(programs, key=lambda d: str(d["program_id"]))
    ok({
        "survey": "Completions",
        "mode": "preview",
        "certifiable": False,
        "company_id": company_id,
        "programs": programs,
        "count": len(programs),
        "program_count": len(programs),
        "total_students": total_students,
        "total_eligible_candidates": total_eligible,
        "total_eligible": total_eligible,
        "total_eligible_count": total_eligible,
        "sources": {
            "programs": PROGRAM_TABLE,
            "students": STUDENT_TABLE,
            "student_count": STUDENT_TABLE,
            "eligible_candidate_count": STUDENT_TABLE,
        },
        "source_tables": [PROGRAM_TABLE, STUDENT_TABLE],
        "program_table": PROGRAM_TABLE,
        "student_table": STUDENT_TABLE,
    })


def status_action(conn, args):
    ok({
        "skill": SKILL,
        "version": "1.0.0",
        "domains": ["registrar", "records", "finaid", "alumni", "faculty", "admissions", "reports"],
        "database": DEFAULT_DB_PATH,
    })


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-enrollment-report": enrollment_report,
    "highered-retention-report": retention_report,
    "highered-degree-completion-report": degree_completion_report,
    "highered-ipeds-completions-preview": ipeds_completions_preview,
    "highered-alumni-giving-summary": alumni_giving_summary,
    "highered-faculty-workload-summary": faculty_workload_summary,
    "status": status_action,
}
