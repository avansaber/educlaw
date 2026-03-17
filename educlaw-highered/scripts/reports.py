"""EduClaw Higher Education — reports domain module (6 actions + status)

Cross-domain reports: enrollment, retention, degree completion, alumni giving, faculty workload.
"""
import os
import sys
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import DEFAULT_DB_PATH
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row
except ImportError:
    DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/erpclaw/data.sqlite")

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
    "highered-alumni-giving-summary": alumni_giving_summary,
    "highered-faculty-workload-summary": faculty_workload_summary,
    "status": status_action,
}
