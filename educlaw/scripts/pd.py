"""EduClaw — professional development (PD) domain module

Actions for tracking teacher professional development credits,
compliance checks, and PD transcripts.

Imported by db_query.py (unified router).
"""
import json
import os
import sys
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_CREDIT_TYPES = ("general", "content_area", "leadership", "technology", "special_education")
VALID_PD_STATUSES = ("pending", "approved", "rejected")

# Default state PD requirement (hours per renewal cycle — varies by state)
DEFAULT_PD_HOURS_REQUIRED = Decimal("120")
DEFAULT_RENEWAL_YEARS = 5


# ─────────────────────────────────────────────────────────────────────────────
# PD CREDIT CRUD
# ─────────────────────────────────────────────────────────────────────────────

def add_pd_credit(conn, args):
    """Record a professional development credit for a teacher/instructor."""
    teacher_id = getattr(args, "instructor_id", None)
    course_name = getattr(args, "name", None)
    credit_hours = getattr(args, "credit_hours", None)
    completion_date = getattr(args, "completion_date", None) or getattr(args, "start_date", None)
    company_id = getattr(args, "company_id", None)

    if not teacher_id:
        err("--instructor-id is required (teacher's instructor ID)")
    if not course_name:
        err("--name is required (PD course name)")
    if not credit_hours:
        err("--credit-hours is required")
    if not completion_date:
        err("--start-date is required (completion date)")
    if not company_id:
        err("--company-id is required")

    # Validate teacher exists
    _instr = Table("educlaw_instructor")
    instr_row = conn.execute(
        Q.from_(_instr).select(_instr.id).where(_instr.id == P()).get_sql(),
        (teacher_id,)
    ).fetchone()
    if not instr_row:
        err(f"Instructor {teacher_id} not found")

    credit_type = getattr(args, "credit_type", None) or "general"
    if credit_type not in VALID_CREDIT_TYPES:
        err(f"Invalid credit type. Must be one of: {', '.join(VALID_CREDIT_TYPES)}")

    try:
        hrs = Decimal(str(credit_hours))
        if hrs <= 0:
            err("--credit-hours must be greater than 0")
    except Exception:
        err("--credit-hours must be a valid number")

    pd_id = str(uuid.uuid4())
    now = _now_iso()
    status = getattr(args, "status", None) or "approved"
    if status not in VALID_PD_STATUSES:
        err(f"Invalid status. Must be one of: {', '.join(VALID_PD_STATUSES)}")

    sql, _ = insert_row("educlaw_pd_credit", {
        "id": P(), "teacher_id": P(), "course_name": P(),
        "provider": P(), "credit_hours": P(), "credit_type": P(),
        "completion_date": P(), "expiration_date": P(),
        "certificate_number": P(), "status": P(),
        "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (
        pd_id, teacher_id, course_name,
        getattr(args, "description", None) or "",
        str(hrs), credit_type,
        completion_date,
        getattr(args, "end_date", None) or "",
        getattr(args, "code", None) or "",
        status, company_id, now,
    ))
    audit(conn, SKILL, "edu-add-pd-credit", "educlaw_pd_credit", pd_id,
          new_values={"teacher_id": teacher_id, "course_name": course_name, "credit_hours": str(hrs)})
    conn.commit()
    ok({"id": pd_id, "teacher_id": teacher_id, "course_name": course_name,
        "credit_hours": str(hrs), "credit_type": credit_type, "status": status})


def list_pd_credits(conn, args):
    """List PD credits, filterable by teacher and company."""
    _pd = Table("educlaw_pd_credit")
    q = Q.from_(_pd).select(_pd.star)
    params = []

    teacher_id = getattr(args, "instructor_id", None)
    if teacher_id:
        q = q.where(_pd.teacher_id == P())
        params.append(teacher_id)

    company_id = getattr(args, "company_id", None)
    if company_id:
        q = q.where(_pd.company_id == P())
        params.append(company_id)

    status = getattr(args, "status", None)
    if status:
        q = q.where(_pd.status == P())
        params.append(status)

    q = q.orderby(_pd.completion_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"pd_credits": [dict(r) for r in rows], "count": len(rows)})


def get_pd_summary(conn, args):
    """Get total PD credits by teacher, grouped by credit type."""
    teacher_id = getattr(args, "instructor_id", None)
    if not teacher_id:
        err("--instructor-id is required")

    _pd = Table("educlaw_pd_credit")
    rows = conn.execute(
        Q.from_(_pd)
        .select(_pd.credit_type, fn.Count(_pd.star).as_("course_count"))
        .where(_pd.teacher_id == P())
        .where(_pd.status == "approved")
        .groupby(_pd.credit_type)
        .get_sql(),
        (teacher_id,)
    ).fetchall()

    # Also get raw approved credits to sum properly with Decimal
    all_credits = conn.execute(
        Q.from_(_pd).select(_pd.credit_hours, _pd.credit_type)
        .where(_pd.teacher_id == P())
        .where(_pd.status == "approved")
        .get_sql(),
        (teacher_id,)
    ).fetchall()

    type_totals = {}
    grand_total = Decimal("0")
    for c in all_credits:
        ct = c["credit_type"]
        hrs = Decimal(str(c["credit_hours"]))
        type_totals[ct] = type_totals.get(ct, Decimal("0")) + hrs
        grand_total += hrs

    summary = []
    for r in rows:
        ct = r["credit_type"]
        summary.append({
            "credit_type": ct,
            "total_hours": str(type_totals.get(ct, Decimal("0"))),
            "course_count": r["course_count"],
        })

    ok({
        "teacher_id": teacher_id,
        "total_credit_hours": str(grand_total),
        "by_type": summary,
    })


def check_pd_compliance(conn, args):
    """Check if a teacher meets PD requirements for license renewal."""
    teacher_id = getattr(args, "instructor_id", None)
    if not teacher_id:
        err("--instructor-id is required")

    required_hours = DEFAULT_PD_HOURS_REQUIRED
    custom_threshold = getattr(args, "threshold", None)
    if custom_threshold:
        try:
            required_hours = Decimal(str(custom_threshold))
        except Exception:
            err("--threshold must be a valid number")

    _pd = Table("educlaw_pd_credit")
    credits = conn.execute(
        Q.from_(_pd).select(_pd.credit_hours, _pd.credit_type, _pd.completion_date, _pd.expiration_date)
        .where(_pd.teacher_id == P())
        .where(_pd.status == "approved")
        .get_sql(),
        (teacher_id,)
    ).fetchall()

    today_str = date.today().isoformat()
    total_valid = Decimal("0")
    expired_count = 0
    for c in credits:
        exp = c["expiration_date"]
        if exp and exp < today_str:
            expired_count += 1
            continue
        total_valid += Decimal(str(c["credit_hours"]))

    compliant = total_valid >= required_hours
    remaining = max(Decimal("0"), required_hours - total_valid)

    ok({
        "teacher_id": teacher_id,
        "required_hours": str(required_hours),
        "earned_hours": str(total_valid),
        "remaining_hours": str(remaining),
        "expired_credits": expired_count,
        "compliant": compliant,
        "renewal_cycle_years": DEFAULT_RENEWAL_YEARS,
    })


def pd_transcript(conn, args):
    """Generate a complete PD transcript for a teacher."""
    teacher_id = getattr(args, "instructor_id", None)
    if not teacher_id:
        err("--instructor-id is required")

    # Get instructor info
    _instr = Table("educlaw_instructor")
    _emp = Table("employee")
    instr_row = conn.execute(
        Q.from_(_instr).join(_emp).on(_emp.id == _instr.employee_id)
        .select(_instr.id, _instr.naming_series, _emp.first_name, _emp.last_name)
        .where(_instr.id == P())
        .get_sql(),
        (teacher_id,)
    ).fetchone()
    if not instr_row:
        err(f"Instructor {teacher_id} not found")
    instr = dict(instr_row)

    _pd = Table("educlaw_pd_credit")
    credits = conn.execute(
        Q.from_(_pd).select(_pd.star)
        .where(_pd.teacher_id == P())
        .where(_pd.status == "approved")
        .orderby(_pd.completion_date, order=Order.desc)
        .get_sql(),
        (teacher_id,)
    ).fetchall()

    total_hours = Decimal("0")
    credit_list = []
    for c in credits:
        cd = dict(c)
        total_hours += Decimal(str(cd["credit_hours"]))
        credit_list.append(cd)

    ok({
        "teacher_id": teacher_id,
        "instructor_name": f"{instr['first_name']} {instr['last_name']}",
        "naming_series": instr["naming_series"],
        "total_credit_hours": str(total_hours),
        "credits": credit_list,
        "generated_at": _now_iso(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-pd-credit": add_pd_credit,
    "edu-list-pd-credits": list_pd_credits,
    "edu-get-pd-summary": get_pd_summary,
    "edu-check-pd-compliance": check_pd_compliance,
    "edu-pd-transcript": pd_transcript,
}
