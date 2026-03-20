"""EduClaw — student activities domain module

Actions for managing clubs, sports, music, academic activities:
enrollment with GPA eligibility checks, roster management, participation reports.

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

VALID_ACTIVITY_TYPES = ("club", "sport", "music", "art", "academic", "volunteer", "other")
VALID_ENROLLMENT_STATUSES = ("active", "inactive", "ineligible")


# ─────────────────────────────────────────────────────────────────────────────
# ACTIVITY CRUD
# ─────────────────────────────────────────────────────────────────────────────

def add_activity(conn, args):
    """Create a new student activity (club, sport, etc.)."""
    name = getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)

    if not name:
        err("--name is required")
    if not company_id:
        err("--company-id is required")

    activity_type = getattr(args, "activity_type", None) or "other"
    if activity_type not in VALID_ACTIVITY_TYPES:
        err(f"Invalid activity type. Must be one of: {', '.join(VALID_ACTIVITY_TYPES)}")

    activity_id = str(uuid.uuid4())
    now = _now_iso()

    min_gpa = getattr(args, "min_gpa", None) or ""
    if min_gpa:
        try:
            gpa_val = Decimal(str(min_gpa))
            if gpa_val < 0 or gpa_val > Decimal("4.0"):
                err("--min-gpa must be between 0.0 and 4.0")
        except Exception:
            err("--min-gpa must be a valid number")

    max_enrollment_val = getattr(args, "max_enrollment", None)
    max_enr = int(max_enrollment_val) if max_enrollment_val else None

    sql, _ = insert_row("educlaw_activity", {
        "id": P(), "school_id": P(), "name": P(),
        "activity_type": P(), "advisor_id": P(), "description": P(),
        "min_gpa": P(), "max_enrollment": P(), "season": P(),
        "status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (
        activity_id,
        getattr(args, "school_id", None) or "",
        name, activity_type,
        getattr(args, "instructor_id", None) or "",
        getattr(args, "description", None) or "",
        min_gpa, max_enr,
        getattr(args, "season", None) or "",
        "active", company_id, now,
    ))
    audit(conn, SKILL, "edu-add-activity", "educlaw_activity", activity_id,
          new_values={"name": name, "activity_type": activity_type})
    conn.commit()
    ok({"id": activity_id, "name": name, "activity_type": activity_type, "activity_status": "active"})


def list_activities(conn, args):
    """List activities, filterable by type, status, company."""
    _act = Table("educlaw_activity")
    q = Q.from_(_act).select(_act.star)
    params = []

    company_id = getattr(args, "company_id", None)
    if company_id:
        q = q.where(_act.company_id == P())
        params.append(company_id)

    activity_type = getattr(args, "activity_type", None)
    if activity_type:
        q = q.where(_act.activity_type == P())
        params.append(activity_type)

    status = getattr(args, "status", None)
    if status:
        q = q.where(_act.status == P())
        params.append(status)

    q = q.orderby(_act.name)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()

    # Add enrollment counts
    result = []
    _ae = Table("educlaw_activity_enrollment")
    for r in rows:
        d = dict(r)
        cnt = conn.execute(
            Q.from_(_ae).select(fn.Count(_ae.id).as_("cnt"))
            .where(_ae.activity_id == P()).where(_ae.status == "active")
            .get_sql(), (d["id"],)
        ).fetchone()
        d["active_enrollment_count"] = dict(cnt)["cnt"] if cnt else 0
        result.append(d)

    ok({"activities": result, "count": len(result)})


def _get_student_gpa(conn, student_id):
    """Get a student's current GPA from course enrollments."""
    _ce = Table("educlaw_course_enrollment")
    _sec = Table("educlaw_section")
    _crs = Table("educlaw_course")

    rows = conn.execute(
        Q.from_(_ce).join(_sec).on(_sec.id == _ce.section_id)
        .join(_crs).on(_crs.id == _sec.course_id)
        .select(_ce.final_grade_points, _crs.credit_hours)
        .where(_ce.student_id == P())
        .where(_ce.enrollment_status == "completed")
        .where(_ce.final_letter_grade != "")
        .get_sql(), (student_id,)
    ).fetchall()

    if not rows:
        return None

    total_points = Decimal("0")
    total_credits = Decimal("0")
    for r in rows:
        gp = Decimal(str(r["final_grade_points"])) if r["final_grade_points"] else Decimal("0")
        ch = Decimal(str(r["credit_hours"])) if r["credit_hours"] else Decimal("0")
        total_points += gp * ch
        total_credits += ch

    if total_credits > 0:
        return (total_points / total_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return None


def enroll_student_activity(conn, args):
    """Enroll a student in an activity with GPA eligibility check."""
    activity_id = getattr(args, "activity_id", None)
    student_id = getattr(args, "student_id", None)

    if not activity_id:
        err("--activity-id is required")
    if not student_id:
        err("--student-id is required")

    # Verify activity exists
    _act = Table("educlaw_activity")
    act_row = conn.execute(
        Q.from_(_act).select(_act.star).where(_act.id == P()).get_sql(),
        (activity_id,)
    ).fetchone()
    if not act_row:
        err(f"Activity {activity_id} not found")

    activity = dict(act_row)
    if activity["status"] != "active":
        err("Activity is not active")

    # Verify student exists and is active
    _st = Table("educlaw_student")
    st_row = conn.execute(
        Q.from_(_st).select(_st.id, _st.status, _st.full_name)
        .where(_st.id == P()).get_sql(), (student_id,)
    ).fetchone()
    if not st_row:
        err(f"Student {student_id} not found")
    student = dict(st_row)
    if student["status"] != "active":
        err("Student must be active to enroll in activities")

    # Check not already enrolled
    _ae = Table("educlaw_activity_enrollment")
    existing = conn.execute(
        Q.from_(_ae).select(_ae.id)
        .where(_ae.activity_id == P()).where(_ae.student_id == P())
        .where(_ae.status == "active")
        .get_sql(), (activity_id, student_id)
    ).fetchone()
    if existing:
        err("Student is already enrolled in this activity")

    # Check max enrollment
    if activity["max_enrollment"]:
        cnt = conn.execute(
            Q.from_(_ae).select(fn.Count(_ae.id).as_("cnt"))
            .where(_ae.activity_id == P()).where(_ae.status == "active")
            .get_sql(), (activity_id,)
        ).fetchone()
        if cnt and dict(cnt)["cnt"] >= activity["max_enrollment"]:
            err(f"Activity is at maximum enrollment ({activity['max_enrollment']})")

    # GPA eligibility check
    gpa = _get_student_gpa(conn, student_id)
    gpa_at_enrollment = str(gpa) if gpa is not None else ""
    eligibility_status = "active"
    eligibility_checked = 1

    if activity["min_gpa"] and gpa is not None:
        min_gpa = Decimal(str(activity["min_gpa"]))
        if gpa < min_gpa:
            eligibility_status = "ineligible"
            err(f"Student GPA ({gpa}) does not meet minimum requirement ({min_gpa})")

    enrollment_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_activity_enrollment", {
        "id": P(), "activity_id": P(), "student_id": P(),
        "enrollment_date": P(), "status": P(),
        "eligibility_checked": P(), "gpa_at_enrollment": P(),
        "created_at": P(),
    })
    conn.execute(sql, (
        enrollment_id, activity_id, student_id,
        date.today().isoformat(), eligibility_status,
        eligibility_checked, gpa_at_enrollment, now,
    ))
    audit(conn, SKILL, "edu-enroll-student-activity", "educlaw_activity_enrollment",
          enrollment_id, new_values={"activity_id": activity_id, "student_id": student_id})
    conn.commit()
    ok({
        "id": enrollment_id, "activity_id": activity_id, "student_id": student_id,
        "enrollment_status": eligibility_status, "gpa_at_enrollment": gpa_at_enrollment,
        "activity_name": activity["name"],
    })


def remove_student_activity(conn, args):
    """Remove a student from an activity."""
    activity_id = getattr(args, "activity_id", None)
    student_id = getattr(args, "student_id", None)

    if not activity_id:
        err("--activity-id is required")
    if not student_id:
        err("--student-id is required")

    _ae = Table("educlaw_activity_enrollment")
    row = conn.execute(
        Q.from_(_ae).select(_ae.id)
        .where(_ae.activity_id == P()).where(_ae.student_id == P())
        .where(_ae.status == "active")
        .get_sql(), (activity_id, student_id)
    ).fetchone()
    if not row:
        err("Student is not actively enrolled in this activity")

    enrollment_id = dict(row)["id"]
    conn.execute(
        "UPDATE educlaw_activity_enrollment SET status = 'inactive' WHERE id = ?",
        (enrollment_id,)
    )
    audit(conn, SKILL, "edu-remove-student-activity", "educlaw_activity_enrollment",
          enrollment_id, new_values={"status": "inactive"})
    conn.commit()
    ok({"enrollment_id": enrollment_id, "activity_id": activity_id,
        "student_id": student_id, "enrollment_status": "inactive"})


def list_activity_roster(conn, args):
    """List all enrolled students for an activity."""
    activity_id = getattr(args, "activity_id", None)
    if not activity_id:
        err("--activity-id is required")

    _ae = Table("educlaw_activity_enrollment")
    _st = Table("educlaw_student")
    _act = Table("educlaw_activity")

    # Get activity info
    act_row = conn.execute(
        Q.from_(_act).select(_act.name, _act.activity_type, _act.min_gpa)
        .where(_act.id == P()).get_sql(), (activity_id,)
    ).fetchone()
    if not act_row:
        err(f"Activity {activity_id} not found")
    activity = dict(act_row)

    rows = conn.execute(
        Q.from_(_ae).join(_st).on(_st.id == _ae.student_id)
        .select(_ae.id.as_("enrollment_id"), _ae.enrollment_date, _ae.status,
                _ae.gpa_at_enrollment, _ae.eligibility_checked,
                _st.id.as_("student_id"), _st.naming_series, _st.full_name,
                _st.grade_level)
        .where(_ae.activity_id == P())
        .where(_ae.status == "active")
        .orderby(_st.last_name).orderby(_st.first_name)
        .get_sql(), (activity_id,)
    ).fetchall()

    ok({
        "activity_id": activity_id,
        "activity_name": activity["name"],
        "activity_type": activity["activity_type"],
        "roster": [dict(r) for r in rows],
        "count": len(rows),
    })


def check_activity_eligibility(conn, args):
    """Check if a student meets eligibility requirements for an activity."""
    activity_id = getattr(args, "activity_id", None)
    student_id = getattr(args, "student_id", None)

    if not activity_id:
        err("--activity-id is required")
    if not student_id:
        err("--student-id is required")

    _act = Table("educlaw_activity")
    act_row = conn.execute(
        Q.from_(_act).select(_act.star).where(_act.id == P()).get_sql(),
        (activity_id,)
    ).fetchone()
    if not act_row:
        err(f"Activity {activity_id} not found")
    activity = dict(act_row)

    _st = Table("educlaw_student")
    st_row = conn.execute(
        Q.from_(_st).select(_st.id, _st.status, _st.full_name)
        .where(_st.id == P()).get_sql(), (student_id,)
    ).fetchone()
    if not st_row:
        err(f"Student {student_id} not found")
    student = dict(st_row)

    issues = []
    eligible = True

    # Check student is active
    if student["status"] != "active":
        issues.append("Student is not active")
        eligible = False

    # Check activity is active
    if activity["status"] != "active":
        issues.append("Activity is not active")
        eligible = False

    # Check GPA requirement
    gpa = _get_student_gpa(conn, student_id)
    gpa_str = str(gpa) if gpa is not None else "N/A"
    if activity["min_gpa"] and gpa is not None:
        min_gpa = Decimal(str(activity["min_gpa"]))
        if gpa < min_gpa:
            issues.append(f"GPA {gpa} is below minimum {min_gpa}")
            eligible = False
    elif activity["min_gpa"] and gpa is None:
        issues.append("No GPA on record to verify minimum requirement")

    # Check enrollment capacity
    _ae = Table("educlaw_activity_enrollment")
    if activity["max_enrollment"]:
        cnt = conn.execute(
            Q.from_(_ae).select(fn.Count(_ae.id).as_("cnt"))
            .where(_ae.activity_id == P()).where(_ae.status == "active")
            .get_sql(), (activity_id,)
        ).fetchone()
        current = dict(cnt)["cnt"] if cnt else 0
        if current >= activity["max_enrollment"]:
            issues.append(f"Activity is full ({current}/{activity['max_enrollment']})")
            eligible = False

    # Check already enrolled
    existing = conn.execute(
        Q.from_(_ae).select(_ae.id)
        .where(_ae.activity_id == P()).where(_ae.student_id == P())
        .where(_ae.status == "active")
        .get_sql(), (activity_id, student_id)
    ).fetchone()
    if existing:
        issues.append("Student is already enrolled")
        eligible = False

    ok({
        "activity_id": activity_id,
        "activity_name": activity["name"],
        "student_id": student_id,
        "student_name": student["full_name"],
        "current_gpa": gpa_str,
        "eligible": eligible,
        "issues": issues,
    })


def activity_participation_report(conn, args):
    """Report showing activity participation across the school."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    _act = Table("educlaw_activity")
    _ae = Table("educlaw_activity_enrollment")

    activities = conn.execute(
        Q.from_(_act).select(_act.id, _act.name, _act.activity_type,
                             _act.max_enrollment, _act.status)
        .where(_act.company_id == P())
        .where(_act.status == "active")
        .orderby(_act.activity_type).orderby(_act.name)
        .get_sql(), (company_id,)
    ).fetchall()

    report = []
    total_enrollments = 0
    for act in activities:
        a = dict(act)
        cnt = conn.execute(
            Q.from_(_ae).select(fn.Count(_ae.id).as_("cnt"))
            .where(_ae.activity_id == P()).where(_ae.status == "active")
            .get_sql(), (a["id"],)
        ).fetchone()
        enrolled = dict(cnt)["cnt"] if cnt else 0
        total_enrollments += enrolled
        a["active_enrollments"] = enrolled
        if a["max_enrollment"]:
            a["utilization_pct"] = round(enrolled / a["max_enrollment"] * 100, 1)
        else:
            a["utilization_pct"] = None
        report.append(a)

    # Type summary
    type_summary = {}
    for a in report:
        t = a["activity_type"]
        if t not in type_summary:
            type_summary[t] = {"count": 0, "total_enrolled": 0}
        type_summary[t]["count"] += 1
        type_summary[t]["total_enrolled"] += a["active_enrollments"]

    ok({
        "company_id": company_id,
        "activities": report,
        "total_activities": len(report),
        "total_enrollments": total_enrollments,
        "by_type": type_summary,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-activity": add_activity,
    "edu-list-activities": list_activities,
    "edu-enroll-student-activity": enroll_student_activity,
    "edu-remove-student-activity": remove_student_activity,
    "edu-list-activity-roster": list_activity_roster,
    "edu-check-activity-eligibility": check_activity_eligibility,
    "edu-activity-participation-report": activity_participation_report,
}
