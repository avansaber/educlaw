"""EduClaw — portal domain module (Parent/Guardian Portal)

12 guardian-scoped read actions. Every action verifies guardian-student
relationship before returning data. FERPA-compliant access control.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, date, timezone
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


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _verify_guardian(conn, guardian_id):
    """Verify the guardian exists. Return row or call err()."""
    _g = Table("educlaw_guardian")
    row = conn.execute(
        Q.from_(_g).select(_g.star).where(_g.id == P()).get_sql(),
        (guardian_id,)
    ).fetchone()
    if not row:
        err(f"Guardian {guardian_id} not found")
    return row


def _verify_guardian_student_link(conn, guardian_id, student_id):
    """Verify guardian is linked to student. err() if not."""
    _sg = Table("educlaw_student_guardian")
    link = conn.execute(
        Q.from_(_sg).select(Field("id"))
        .where(_sg.guardian_id == P())
        .where(_sg.student_id == P())
        .get_sql(),
        (guardian_id, student_id)
    ).fetchone()
    if not link:
        err("Access denied: not authorized to view this student's records")


# ─────────────────────────────────────────────────────────────────────────────
# PORTAL ACTIONS
# ─────────────────────────────────────────────────────────────────────────────

def portal_my_students(conn, args):
    """List all students linked to this guardian."""
    guardian_id = getattr(args, "guardian_id", None)
    if not guardian_id:
        err("--guardian-id is required")

    _verify_guardian(conn, guardian_id)

    _sg = Table("educlaw_student_guardian")
    _st = Table("educlaw_student")
    rows = conn.execute(
        Q.from_(_sg).join(_st).on(_st.id == _sg.student_id)
        .select(
            _st.id, _st.naming_series, _st.first_name, _st.last_name,
            _st.full_name, _st.grade_level, _st.status,
            _sg.relationship, _sg.is_primary_contact
        )
        .where(_sg.guardian_id == P())
        .orderby(_st.last_name).orderby(_st.first_name)
        .get_sql(),
        (guardian_id,)
    ).fetchall()

    ok({"guardian_id": guardian_id, "students": [dict(r) for r in rows],
        "count": len(rows)})


def portal_student_grades(conn, args):
    """View current term grades for a linked student."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    _ce = Table("educlaw_course_enrollment")
    _sec = Table("educlaw_section")
    _crs = Table("educlaw_course")
    rows = conn.execute(
        Q.from_(_ce)
        .join(_sec).on(_sec.id == _ce.section_id)
        .join(_crs).on(_crs.id == _sec.course_id)
        .select(
            _ce.id.as_("enrollment_id"),
            _crs.course_code, _crs.name.as_("course_name"),
            _ce.enrollment_status,
            _ce.final_letter_grade, _ce.final_grade_points,
            _ce.final_percentage, _ce.is_grade_submitted,
        )
        .where(_ce.student_id == P())
        .where(_ce.enrollment_status.isin(["enrolled", "completed"]))
        .orderby(_crs.course_code)
        .get_sql(),
        (student_id,)
    ).fetchall()

    ok({"guardian_id": guardian_id, "student_id": student_id,
        "grades": [dict(r) for r in rows], "count": len(rows)})


def portal_student_attendance(conn, args):
    """View attendance records for a linked student."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    _att = Table("educlaw_student_attendance")
    q = Q.from_(_att).select(_att.star).where(_att.student_id == P())
    params = [student_id]

    date_from = getattr(args, "date_from", None)
    date_to = getattr(args, "date_to", None)
    if date_from:
        q = q.where(_att.attendance_date >= P())
        params.append(date_from)
    if date_to:
        q = q.where(_att.attendance_date <= P())
        params.append(date_to)

    q = q.orderby(_att.attendance_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"guardian_id": guardian_id, "student_id": student_id,
        "attendance": [dict(r) for r in rows], "count": len(rows)})


def portal_student_schedule(conn, args):
    """View current schedule/timetable for a linked student."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    _ce = Table("educlaw_course_enrollment")
    _sec = Table("educlaw_section")
    _crs = Table("educlaw_course")
    _rm = Table("educlaw_room")
    _inst = Table("educlaw_instructor")
    _emp = Table("employee")

    rows = conn.execute(
        Q.from_(_ce)
        .join(_sec).on(_sec.id == _ce.section_id)
        .join(_crs).on(_crs.id == _sec.course_id)
        .left_join(_rm).on(_rm.id == _sec.room_id)
        .left_join(_inst).on(_inst.id == _sec.instructor_id)
        .left_join(_emp).on(_emp.id == _inst.employee_id)
        .select(
            _crs.course_code, _crs.name.as_("course_name"),
            _sec.section_number, _sec.days_of_week,
            _sec.start_time, _sec.end_time,
            _rm.room_number, _rm.building,
            _emp.first_name.as_("instructor_first_name"),
            _emp.last_name.as_("instructor_last_name"),
        )
        .where(_ce.student_id == P())
        .where(_ce.enrollment_status == "enrolled")
        .orderby(_sec.start_time)
        .get_sql(),
        (student_id,)
    ).fetchall()

    ok({"guardian_id": guardian_id, "student_id": student_id,
        "schedule": [dict(r) for r in rows], "count": len(rows)})


def portal_student_fees(conn, args):
    """View outstanding fees and payment history for a linked student."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    # Get student's customer_id for invoice lookups
    _st = Table("educlaw_student")
    student_row = conn.execute(
        Q.from_(_st).select(_st.customer_id).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone()

    invoices = []
    if student_row:
        customer_id = dict(student_row).get("customer_id")
        if customer_id:
            try:
                _si = Table("sales_invoice")
                inv_rows = conn.execute(
                    Q.from_(_si).select(_si.star)
                    .where(_si.customer_id == P())
                    .orderby(_si.created_at, order=Order.desc)
                    .get_sql(),
                    (customer_id,)
                ).fetchall()
                invoices = [dict(r) for r in inv_rows]
            except Exception:
                pass

    # Get scholarships
    _sch = Table("educlaw_scholarship")
    scholarships = conn.execute(
        Q.from_(_sch).select(_sch.star)
        .where(_sch.student_id == P())
        .where(_sch.scholarship_status == "active")
        .get_sql(),
        (student_id,)
    ).fetchall()

    ok({"guardian_id": guardian_id, "student_id": student_id,
        "invoices": invoices,
        "active_scholarships": [dict(s) for s in scholarships]})


def portal_announcements(conn, args):
    """View school announcements visible to guardians."""
    guardian_id = getattr(args, "guardian_id", None)
    if not guardian_id:
        err("--guardian-id is required")

    _verify_guardian(conn, guardian_id)

    _ann = Table("educlaw_announcement")
    rows = conn.execute(
        Q.from_(_ann).select(_ann.star)
        .where(_ann.announcement_status == "published")
        .where(_ann.audience_type.isin(["guardians", "all"]))
        .orderby(_ann.publish_date, order=Order.desc)
        .limit(50)
        .get_sql(),
        ()
    ).fetchall()

    ok({"guardian_id": guardian_id, "announcements": [dict(r) for r in rows],
        "count": len(rows)})


def portal_student_assignments(conn, args):
    """View recent assignments for a linked student (if LMS data exists)."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    _ce = Table("educlaw_course_enrollment")
    _asmnt = Table("educlaw_assessment")
    _ap = Table("educlaw_assessment_plan")
    _sec = Table("educlaw_section")
    _crs = Table("educlaw_course")
    _ar = Table("educlaw_assessment_result")

    # Get enrolled section ids
    enrollments = conn.execute(
        Q.from_(_ce).select(_ce.id, _ce.section_id)
        .where(_ce.student_id == P())
        .where(_ce.enrollment_status == "enrolled")
        .get_sql(),
        (student_id,)
    ).fetchall()

    assignments = []
    for enr in enrollments:
        e = dict(enr)
        section_id = e["section_id"]
        enrollment_id = e["id"]

        rows = conn.execute(
            Q.from_(_asmnt)
            .join(_ap).on(_ap.id == _asmnt.assessment_plan_id)
            .join(_sec).on(_sec.id == _ap.section_id)
            .join(_crs).on(_crs.id == _sec.course_id)
            .left_join(_ar).on(
                (_ar.assessment_id == _asmnt.id) & (_ar.student_id == P())
            )
            .select(
                _asmnt.id.as_("assessment_id"),
                _asmnt.name.as_("assessment_name"),
                _asmnt.max_points, _asmnt.due_date,
                _crs.course_code, _crs.name.as_("course_name"),
                _ar.points_earned, _ar.is_exempt,
            )
            .where(_ap.section_id == P())
            .where(_asmnt.is_published == 1)
            .orderby(_asmnt.due_date, order=Order.desc)
            .limit(20)
            .get_sql(),
            (student_id, section_id)
        ).fetchall()
        assignments.extend([dict(r) for r in rows])

    ok({"guardian_id": guardian_id, "student_id": student_id,
        "assignments": assignments, "count": len(assignments)})


def portal_student_discipline(conn, args):
    """View discipline records for a linked student (sanitized per FERPA).

    Note: EduClaw core does not have a dedicated discipline table yet.
    This action returns a placeholder. When a discipline module is added,
    it will read from the appropriate table.
    """
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    # No discipline table in core educlaw — return empty
    ok({"guardian_id": guardian_id, "student_id": student_id,
        "discipline_records": [],
        "note": "No discipline records found"})


def portal_update_contact_info(conn, args):
    """Guardian updates their own contact information."""
    guardian_id = getattr(args, "guardian_id", None)
    if not guardian_id:
        err("--guardian-id is required")

    _verify_guardian(conn, guardian_id)

    updates, params, changed = [], [], []

    if getattr(args, "phone", None) is not None:
        updates.append("phone = ?"); params.append(args.phone)
        changed.append("phone")
    if getattr(args, "email", None) is not None:
        updates.append("email = ?"); params.append(args.email)
        changed.append("email")
    if getattr(args, "address", None) is not None:
        updates.append("address = ?"); params.append(args.address)
        changed.append("address")

    if not changed:
        err("No fields to update. Provide at least one of: --phone, --email, --address")

    updates.append("updated_at = datetime('now')")
    params.append(guardian_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_guardian SET {', '.join(updates)} WHERE id = ?", params)

    audit(conn, SKILL, "edu-portal-update-contact-info", "educlaw_guardian",
          guardian_id, new_values={k: v for k, v in zip(changed, params[:len(changed)])})
    conn.commit()
    ok({"guardian_id": guardian_id, "updated_fields": changed})


def portal_acknowledge_announcement(conn, args):
    """Guardian acknowledges receipt of an announcement."""
    guardian_id = getattr(args, "guardian_id", None)
    announcement_id = getattr(args, "announcement_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not announcement_id:
        err("--announcement-id is required")

    _verify_guardian(conn, guardian_id)

    # Verify announcement exists
    _ann = Table("educlaw_announcement")
    ann_row = conn.execute(
        Q.from_(_ann).select(_ann.id).where(_ann.id == P()).get_sql(),
        (announcement_id,)
    ).fetchone()
    if not ann_row:
        err(f"Announcement {announcement_id} not found")

    # Record acknowledgement as a notification (read=1)
    now = _now_iso()
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {
        "id": P(), "recipient_type": P(), "recipient_id": P(),
        "notification_type": P(), "title": P(), "message": P(),
        "reference_type": P(), "reference_id": P(), "is_read": P(),
        "sent_via": P(), "sent_at": P(), "company_id": P(),
        "created_at": P(), "created_by": P(),
    })
    conn.execute(sql,
        (notif_id, "guardian", guardian_id, "announcement",
         "Announcement Acknowledged", f"Guardian acknowledged announcement {announcement_id}",
         "educlaw_announcement", announcement_id, 1,
         "system", now, "", now, guardian_id)
    )
    conn.commit()

    ok({"guardian_id": guardian_id, "announcement_id": announcement_id,
        "acknowledged": True, "acknowledged_at": now})


def portal_submit_absence_excuse(conn, args):
    """Guardian submits an excuse for a student's absence."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    absence_date = getattr(args, "absence_date", None)
    reason = getattr(args, "reason", None)

    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")
    if not absence_date:
        err("--absence-date is required")
    if not reason:
        err("--reason is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    # Find the attendance record for this date
    _att = Table("educlaw_student_attendance")
    att_row = conn.execute(
        Q.from_(_att).select(_att.id, _att.attendance_status)
        .where(_att.student_id == P())
        .where(_att.attendance_date == P())
        .get_sql(),
        (student_id, absence_date)
    ).fetchone()

    if att_row:
        att = dict(att_row)
        # Update the attendance record to excused with the reason
        conn.execute(
            "UPDATE educlaw_student_attendance SET attendance_status = 'excused', "
            "comments = ?, updated_at = datetime('now') WHERE id = ?",
            (f"Guardian excuse: {reason}", att["id"])
        )
    else:
        # Create a new excused attendance record
        new_id = str(uuid.uuid4())
        now = _now_iso()
        # Look up company_id from student
        _st = Table("educlaw_student")
        st_row = conn.execute(
            Q.from_(_st).select(_st.company_id).where(_st.id == P()).get_sql(),
            (student_id,)
        ).fetchone()
        company_id = dict(st_row)["company_id"] if st_row else ""

        sql, _ = insert_row("educlaw_student_attendance", {
            "id": P(), "student_id": P(), "attendance_date": P(),
            "attendance_status": P(), "comments": P(),
            "marked_by": P(), "source": P(),
            "company_id": P(), "created_at": P(), "created_by": P(),
        })
        conn.execute(sql,
            (new_id, student_id, absence_date, "excused",
             f"Guardian excuse: {reason}", guardian_id, "app",
             company_id, now, guardian_id)
        )

    conn.commit()
    ok({"guardian_id": guardian_id, "student_id": student_id,
        "absence_date": absence_date, "excuse_submitted": True,
        "reason": reason})


def portal_my_transport(conn, args):
    """View bus route/stop assignment for a linked student."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")

    _verify_guardian(conn, guardian_id)
    _verify_guardian_student_link(conn, guardian_id, student_id)

    _tr = Table("educlaw_student_transport")
    _br = Table("educlaw_bus_route")
    _bs = Table("educlaw_bus_stop")

    rows = conn.execute(
        Q.from_(_tr)
        .join(_br).on(_br.id == _tr.route_id)
        .left_join(_bs).on(_bs.id == _tr.bus_stop_id)
        .select(
            _tr.id.as_("transport_id"), _tr.transport_type, _tr.status,
            _tr.special_needs_notes, _tr.effective_date, _tr.end_date,
            _br.route_number, _br.route_name,
            _br.driver_name, _br.driver_phone,
            _br.am_start_time, _br.pm_start_time,
            _bs.stop_name, _bs.address.as_("stop_address"),
            _bs.am_pickup_time, _bs.pm_dropoff_time,
        )
        .where(_tr.student_id == P())
        .where(_tr.status == "active")
        .get_sql(),
        (student_id,)
    ).fetchall()

    ok({"guardian_id": guardian_id, "student_id": student_id,
        "transport_assignments": [dict(r) for r in rows],
        "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-portal-my-students": portal_my_students,
    "edu-portal-student-grades": portal_student_grades,
    "edu-portal-student-attendance": portal_student_attendance,
    "edu-portal-student-schedule": portal_student_schedule,
    "edu-portal-student-fees": portal_student_fees,
    "edu-portal-announcements": portal_announcements,
    "edu-portal-student-assignments": portal_student_assignments,
    "edu-portal-student-discipline": portal_student_discipline,
    "edu-portal-update-contact-info": portal_update_contact_info,
    "edu-portal-acknowledge-announcement": portal_acknowledge_announcement,
    "edu-portal-submit-absence-excuse": portal_submit_absence_excuse,
    "edu-portal-my-transport": portal_my_transport,
}
