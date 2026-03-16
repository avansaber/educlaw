"""EduClaw — attendance domain module

Actions for attendance: daily homeroom and per-section attendance,
attendance summaries, truancy reporting.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, LiteralValue
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_ATTENDANCE_STATUSES = ("present", "absent", "tardy", "excused", "half_day")
VALID_SOURCES = ("manual", "biometric", "app")


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────────────────────────────────────────

def mark_attendance(conn, args):
    student_id = getattr(args, "student_id", None)
    attendance_date = getattr(args, "attendance_date", None)
    attendance_status = getattr(args, "attendance_status", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not attendance_date:
        err("--attendance-date is required")
    if not attendance_status:
        err("--attendance-status is required")
    if attendance_status not in VALID_ATTENDANCE_STATUSES:
        err(f"--attendance-status must be one of: {', '.join(VALID_ATTENDANCE_STATUSES)}")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("educlaw_student")).select(Field("id")).where(Field("id") == P()).get_sql(), (student_id,)).fetchone():
        err(f"Student {student_id} not found")

    section_id = getattr(args, "section_id", None)
    if section_id:
        if not conn.execute(Q.from_(Table("educlaw_section")).select(Field("id")).where(Field("id") == P()).get_sql(), (section_id,)).fetchone():
            err(f"Section {section_id} not found")

    source = getattr(args, "source", None) or "manual"
    if source not in VALID_SOURCES:
        err(f"--source must be one of: {', '.join(VALID_SOURCES)}")

    att_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_student_attendance", {"id": P(), "student_id": P(), "attendance_date": P(), "section_id": P(), "attendance_status": P(), "late_minutes": P(), "comments": P(), "marked_by": P(), "source": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (att_id, student_id, attendance_date, section_id, attendance_status,
             int(getattr(args, "late_minutes", None) or 0),
             getattr(args, "comments", None) or "",
             getattr(args, "marked_by", None) or getattr(args, "user_id", None) or "",
             source, company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError:
        err(f"Attendance already recorded for student {student_id} on {attendance_date}"
            + (f" in section {section_id}" if section_id else ""))

    conn.commit()
    ok({"id": att_id, "student_id": student_id, "attendance_date": attendance_date,
        "attendance_status": attendance_status, "section_id": section_id})


def batch_mark_attendance(conn, args):
    attendance_date = getattr(args, "attendance_date", None)
    company_id = getattr(args, "company_id", None)
    records_json = getattr(args, "records", None)

    if not attendance_date:
        err("--attendance-date is required")
    if not company_id:
        err("--company-id is required")
    if not records_json:
        err("--records is required (JSON array of {student_id, attendance_status})")

    try:
        records = json.loads(records_json) if isinstance(records_json, str) else records_json
        if not isinstance(records, list):
            err("--records must be a JSON array")
    except (json.JSONDecodeError, TypeError):
        err("--records must be valid JSON")

    section_id = getattr(args, "section_id", None)
    source = getattr(args, "source", None) or "manual"
    marked_by = getattr(args, "marked_by", None) or getattr(args, "user_id", None) or ""
    now = _now_iso()

    saved_count = 0
    errors = []

    for rec in records:
        if not isinstance(rec, dict):
            continue
        student_id = rec.get("student_id")
        status = rec.get("attendance_status", None) or "present"

        if not student_id:
            errors.append({"error": "student_id is required", "data": rec})
            continue
        if status not in VALID_ATTENDANCE_STATUSES:
            errors.append({"student_id": student_id,
                           "error": f"Invalid attendance_status: {status}"})
            continue

        att_id = str(uuid.uuid4())
        try:
            sql, _ = insert_row("educlaw_student_attendance", {"id": P(), "student_id": P(), "attendance_date": P(), "section_id": P(), "attendance_status": P(), "late_minutes": P(), "comments": P(), "marked_by": P(), "source": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

            conn.execute(sql,
                (att_id, student_id, attendance_date, section_id, status,
                 int(rec.get("late_minutes", 0)),
                 rec.get("comments", ""),
                 marked_by, source, company_id, now, now, marked_by)
            )
            saved_count += 1
        except sqlite3.IntegrityError:
            errors.append({"student_id": student_id,
                           "error": "Attendance already recorded for this date/section"})

    conn.commit()
    ok({"attendance_date": attendance_date, "saved": saved_count, "errors": errors})


def update_attendance(conn, args):
    attendance_id = getattr(args, "attendance_id", None)
    if not attendance_id:
        err("--attendance-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student_attendance")).select(Table("educlaw_student_attendance").star).where(Field("id") == P()).get_sql(), (attendance_id,)).fetchone()
    if not row:
        err(f"Attendance record {attendance_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "attendance_status", None) is not None:
        if args.attendance_status not in VALID_ATTENDANCE_STATUSES:
            err(f"--attendance-status must be one of: {', '.join(VALID_ATTENDANCE_STATUSES)}")
        updates.append("attendance_status = ?"); params.append(args.attendance_status)
        changed.append("attendance_status")
    if getattr(args, "late_minutes", None) is not None:
        updates.append("late_minutes = ?"); params.append(int(args.late_minutes))
        changed.append("late_minutes")
    if getattr(args, "comments", None) is not None:
        updates.append("comments = ?"); params.append(args.comments); changed.append("comments")
    if getattr(args, "marked_by", None) is not None:
        updates.append("marked_by = ?"); params.append(args.marked_by); changed.append("marked_by")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(attendance_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_student_attendance SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"id": attendance_id, "updated_fields": changed})


def get_attendance(conn, args):
    attendance_id = getattr(args, "attendance_id", None)
    if not attendance_id:
        err("--attendance-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student_attendance")).select(Table("educlaw_student_attendance").star).where(Field("id") == P()).get_sql(), (attendance_id,)).fetchone()
    if not row:
        err(f"Attendance record {attendance_id} not found")
    ok(dict(row))


def list_attendance(conn, args):
    _sa = Table("educlaw_student_attendance")
    q = Q.from_(_sa).select(_sa.star)
    params = []

    if getattr(args, "student_id", None):
        q = q.where(_sa.student_id == P()); params.append(args.student_id)
    if getattr(args, "section_id", None):
        q = q.where(_sa.section_id == P()); params.append(args.section_id)
    if getattr(args, "attendance_date_from", None):
        q = q.where(_sa.attendance_date >= P()); params.append(args.attendance_date_from)
    if getattr(args, "attendance_date_to", None):
        q = q.where(_sa.attendance_date <= P()); params.append(args.attendance_date_to)
    if getattr(args, "attendance_status", None):
        q = q.where(_sa.attendance_status == P()); params.append(args.attendance_status)
    if getattr(args, "company_id", None):
        q = q.where(_sa.company_id == P()); params.append(args.company_id)

    q = q.orderby(_sa.attendance_date, order=Order.desc).orderby(_sa.student_id)
    limit = int(getattr(args, "limit", None) or 100)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"attendance_records": [dict(r) for r in rows], "count": len(rows)})


def get_attendance_summary(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        err("--student-id is required")

    _sa = Table("educlaw_student_attendance")
    q = Q.from_(_sa).select(_sa.attendance_status, fn.Count(_sa.star).as_("cnt")).where(_sa.student_id == P())
    params = [student_id]

    section_id = getattr(args, "section_id", None)
    if section_id:
        q = q.where(_sa.section_id == P()); params.append(section_id)

    from_date = getattr(args, "attendance_date_from", None)
    to_date = getattr(args, "attendance_date_to", None)
    if from_date:
        q = q.where(_sa.attendance_date >= P()); params.append(from_date)
    if to_date:
        q = q.where(_sa.attendance_date <= P()); params.append(to_date)

    q = q.groupby(_sa.attendance_status)
    rows = conn.execute(q.get_sql(), params).fetchall()

    counts = {r["attendance_status"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    present = counts.get("present", 0) + counts.get("half_day", 0) // 2
    absent = counts.get("absent", 0)
    tardy = counts.get("tardy", 0)
    excused = counts.get("excused", 0)

    attendance_pct = "0.00"
    if total > 0:
        pct = (Decimal(str(present + excused)) / Decimal(str(total)) * Decimal("100"))
        attendance_pct = str(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    ok({
        "student_id": student_id,
        "total_days": total,
        "present": counts.get("present", 0),
        "absent": absent,
        "tardy": tardy,
        "excused": excused,
        "half_day": counts.get("half_day", 0),
        "attendance_percentage": attendance_pct,
    })


def get_section_attendance(conn, args):
    section_id = getattr(args, "section_id", None)
    if not section_id:
        err("--section-id is required")

    _sa = Table("educlaw_student_attendance")
    _s = Table("educlaw_student")
    q = (Q.from_(_sa).join(_s).on(_s.id == _sa.student_id)
         .select(_sa.star, _s.first_name, _s.last_name, _s.naming_series)
         .where(_sa.section_id == P()))
    params = [section_id]

    from_date = getattr(args, "attendance_date_from", None)
    to_date = getattr(args, "attendance_date_to", None)
    att_date = getattr(args, "attendance_date", None)

    if att_date:
        q = q.where(_sa.attendance_date == P()); params.append(att_date)
    if from_date:
        q = q.where(_sa.attendance_date >= P()); params.append(from_date)
    if to_date:
        q = q.where(_sa.attendance_date <= P()); params.append(to_date)

    q = q.orderby(_sa.attendance_date).orderby(_s.last_name).orderby(_s.first_name)
    limit = int(getattr(args, "limit", None) or 200)
    q = q.limit(limit)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"section_id": section_id, "attendance_records": [dict(r) for r in rows],
        "count": len(rows)})


def get_truancy_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    threshold = float(getattr(args, "threshold", None) or 90)

    from_date = getattr(args, "attendance_date_from", None)
    to_date = getattr(args, "attendance_date_to", None)
    grade_level = getattr(args, "grade_level", None)
    section_id = getattr(args, "section_id", None)

    # Get all active students for company
    _st = Table("educlaw_student")
    sq = Q.from_(_st).select(_st.id, _st.naming_series, _st.full_name, _st.grade_level).where(_st.company_id == P()).where(_st.status == 'active')
    student_params = [company_id]
    if grade_level:
        sq = sq.where(_st.grade_level == P()); student_params.append(grade_level)

    students = conn.execute(sq.get_sql(), student_params).fetchall()
    truant_students = []

    for student in students:
        s = dict(student)
        # Count attendance for this student
        _sa2 = Table("educlaw_student_attendance")
        aq = Q.from_(_sa2).select(_sa2.attendance_status, fn.Count(_sa2.star).as_("cnt")).where(_sa2.student_id == P()).where(_sa2.company_id == P())
        att_params = [s["id"], company_id]
        if section_id:
            aq = aq.where(_sa2.section_id == P()); att_params.append(section_id)
        if from_date:
            aq = aq.where(_sa2.attendance_date >= P()); att_params.append(from_date)
        if to_date:
            aq = aq.where(_sa2.attendance_date <= P()); att_params.append(to_date)
        aq = aq.groupby(_sa2.attendance_status)

        counts = {r["attendance_status"]: r["cnt"]
                  for r in conn.execute(aq.get_sql(), att_params).fetchall()}
        total = sum(counts.values())
        if total == 0:
            continue

        present = counts.get("present", 0)
        excused = counts.get("excused", 0)
        pct = (Decimal(str(present + excused)) / Decimal(str(total)) * Decimal("100"))
        att_pct = float(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        if att_pct < threshold:
            # Get guardian contact
            _g = Table("educlaw_guardian")
            _sg = Table("educlaw_student_guardian")
            guardians = conn.execute(
                Q.from_(_g).join(_sg).on(_sg.guardian_id == _g.id)
                .select(_g.full_name, _g.phone, _g.email, _sg.is_primary_contact)
                .where(_sg.student_id == P()).where(_sg.receives_communications == 1)
                .orderby(_sg.is_primary_contact, order=Order.desc)
                .get_sql(),
                (s["id"],)
            ).fetchall()

            truant_students.append({
                "student_id": s["id"],
                "naming_series": s["naming_series"],
                "full_name": s["full_name"],
                "grade_level": s["grade_level"],
                "total_days": total,
                "present": present,
                "excused": excused,
                "absent": counts.get("absent", 0),
                "attendance_percentage": att_pct,
                "guardians": [dict(g) for g in guardians],
            })

    ok({
        "threshold_pct": threshold,
        "truant_student_count": len(truant_students),
        "truant_students": truant_students,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-record-attendance": mark_attendance,
    "edu-record-batch-attendance": batch_mark_attendance,
    "edu-update-attendance": update_attendance,
    "edu-get-attendance": get_attendance,
    "edu-list-attendance": list_attendance,
    "edu-get-attendance-summary": get_attendance_summary,
    "edu-get-section-attendance": get_section_attendance,
    "edu-get-truancy-report": get_truancy_report,
}
