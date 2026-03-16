"""EduClaw — communications domain module

Actions for communications: announcements (draft → publish → archive),
targeted notifications, progress reports, emergency alerts.

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

VALID_PRIORITIES = ("normal", "urgent", "emergency")
VALID_AUDIENCE_TYPES = ("all", "students", "guardians", "staff", "program", "section", "department", "grade_level")
VALID_ANNOUNCEMENT_STATUSES = ("draft", "published", "archived")
VALID_RECIPIENT_TYPES = ("student", "guardian", "employee")
VALID_NOTIFICATION_TYPES = ("grade_posted", "fee_due", "absence", "announcement",
                             "progress_report", "emergency", "acceptance", "enrollment_confirmed")
VALID_SENT_VIA = ("system", "email")


def _create_notification(conn, recipient_type, recipient_id, notification_type,
                          title, message, company_id, reference_type=None,
                          reference_id=None, sent_via="system"):
    """Internal helper to insert a single notification record."""
    now = _now_iso()
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {
        "id": P(), "recipient_type": P(), "recipient_id": P(),
        "notification_type": P(), "title": P(), "message": P(),
        "reference_type": P(), "reference_id": P(), "is_read": P(),
        "sent_via": P(), "sent_at": P(), "company_id": P(), "created_at": P()
    })
    conn.execute(sql,
        (notif_id, recipient_type, recipient_id, notification_type,
         title, message, reference_type, reference_id,
         0, sent_via, now, company_id, now)
    )
    return notif_id


def _get_audience_recipients(conn, audience_type, audience_filter_json, company_id):
    """Return list of (recipient_type, recipient_id) tuples for given audience."""
    recipients = []
    af = {}
    if audience_filter_json:
        try:
            af = json.loads(audience_filter_json) if isinstance(audience_filter_json, str) else audience_filter_json
        except (json.JSONDecodeError, TypeError):
            af = {}

    if audience_type in ("all", "students"):
        _st = Table("educlaw_student")
        rows = conn.execute(
            Q.from_(_st).select(_st.id).where(_st.company_id == P()).where(_st.status == 'active').get_sql(),
            (company_id,)
        ).fetchall()
        recipients.extend(("student", r["id"]) for r in rows)

    if audience_type in ("all", "guardians"):
        _g = Table("educlaw_guardian")
        _sg = Table("educlaw_student_guardian")
        _st2 = Table("educlaw_student")
        rows = conn.execute(
            Q.from_(_g).join(_sg).on(_sg.guardian_id == _g.id)
            .join(_st2).on(_st2.id == _sg.student_id)
            .select(_g.id).distinct()
            .where(_st2.company_id == P()).where(_st2.status == 'active')
            .where(_sg.receives_communications == 1)
            .get_sql(),
            (company_id,)
        ).fetchall()
        recipients.extend(("guardian", r["id"]) for r in rows)

    if audience_type in ("all", "staff"):
        _emp = Table("employee")
        rows = conn.execute(
            Q.from_(_emp).select(_emp.id).where(_emp.company_id == P()).get_sql(),
            (company_id,)
        ).fetchall()
        recipients.extend(("employee", r["id"]) for r in rows)

    if audience_type == "program":
        program_id = af.get("program_id")
        if program_id:
            _st3 = Table("educlaw_student")
            _pe = Table("educlaw_program_enrollment")
            rows = conn.execute(
                Q.from_(_st3).join(_pe).on(_pe.student_id == _st3.id)
                .select(_st3.id).distinct()
                .where(_pe.program_id == P()).where(_pe.enrollment_status == 'active')
                .where(_st3.company_id == P())
                .get_sql(),
                (program_id, company_id)
            ).fetchall()
            recipients.extend(("student", r["id"]) for r in rows)

    if audience_type == "section":
        section_id = af.get("section_id")
        if section_id:
            _st4 = Table("educlaw_student")
            _ce = Table("educlaw_course_enrollment")
            rows = conn.execute(
                Q.from_(_st4).join(_ce).on(_ce.student_id == _st4.id)
                .select(_st4.id).distinct()
                .where(_ce.section_id == P()).where(_ce.enrollment_status == 'enrolled')
                .where(_st4.company_id == P())
                .get_sql(),
                (section_id, company_id)
            ).fetchall()
            recipients.extend(("student", r["id"]) for r in rows)

    if audience_type == "department":
        department_id = af.get("department_id")
        if department_id:
            _emp2 = Table("employee")
            rows = conn.execute(
                Q.from_(_emp2).select(_emp2.id)
                .where(_emp2.department_id == P()).where(_emp2.company_id == P())
                .get_sql(),
                (department_id, company_id)
            ).fetchall()
            recipients.extend(("employee", r["id"]) for r in rows)

    if audience_type == "grade_level":
        grade_level = af.get("grade_level")
        if grade_level:
            _st5 = Table("educlaw_student")
            rows = conn.execute(
                Q.from_(_st5).select(_st5.id)
                .where(_st5.grade_level == P()).where(_st5.company_id == P())
                .where(_st5.status == 'active')
                .get_sql(),
                (grade_level, company_id)
            ).fetchall()
            recipients.extend(("student", r["id"]) for r in rows)

    return recipients


# ─────────────────────────────────────────────────────────────────────────────
# ANNOUNCEMENTS
# ─────────────────────────────────────────────────────────────────────────────

def add_announcement(conn, args):
    """Create a new announcement in draft status."""
    title = getattr(args, "title", None)
    body = getattr(args, "body", None)
    company_id = getattr(args, "company_id", None)

    if not title:
        err("--title is required")
    if not body:
        err("--body is required")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    priority = getattr(args, "priority", None) or "normal"
    if priority not in VALID_PRIORITIES:
        err(f"--priority must be one of: {', '.join(VALID_PRIORITIES)}")

    audience_type = getattr(args, "audience_type", None) or "all"
    if audience_type not in VALID_AUDIENCE_TYPES:
        err(f"--audience-type must be one of: {', '.join(VALID_AUDIENCE_TYPES)}")

    audience_filter = getattr(args, "audience_filter", None)
    if audience_filter:
        try:
            json.loads(audience_filter) if isinstance(audience_filter, str) else audience_filter
        except (json.JSONDecodeError, TypeError):
            err("--audience-filter must be valid JSON")

    ann_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_announcement", {
            "id": P(), "title": P(), "body": P(), "priority": P(),
            "audience_type": P(), "audience_filter": P(),
            "publish_date": P(), "expiry_date": P(), "announcement_status": P(),
            "published_by": P(), "company_id": P(), "created_at": P(), "updated_at": P()
        })
        conn.execute(sql,
            (ann_id, title, body, priority, audience_type,
             audience_filter,
             getattr(args, "publish_date", None),
             getattr(args, "expiry_date", None),
             "draft", None,
             company_id, now, now)
        )
    except sqlite3.IntegrityError as e:
        err(f"Announcement creation failed: {e}")

    audit(conn, SKILL, "edu-add-announcement", "educlaw_announcement", ann_id,
          new_values={"title": title, "audience_type": audience_type})
    conn.commit()
    ok({"id": ann_id, "announcement_status": "draft", "title": title})


def update_announcement(conn, args):
    """Update announcement content (draft only)."""
    announcement_id = getattr(args, "announcement_id", None)
    if not announcement_id:
        err("--announcement-id is required")

    row = conn.execute(Q.from_(Table("educlaw_announcement")).select(Table("educlaw_announcement").star).where(Field("id") == P()).get_sql(), (announcement_id,)).fetchone()
    if not row:
        err(f"Announcement {announcement_id} not found")
    if row["announcement_status"] != "draft":
        err(f"Cannot update announcement in status '{row['announcement_status']}'. Only draft announcements can be updated.")

    updates, params, changed = [], [], []

    if getattr(args, "title", None) is not None:
        updates.append("title = ?"); params.append(args.title); changed.append("title")
    if getattr(args, "body", None) is not None:
        updates.append("body = ?"); params.append(args.body); changed.append("body")
    if getattr(args, "priority", None) is not None:
        if args.priority not in VALID_PRIORITIES:
            err(f"--priority must be one of: {', '.join(VALID_PRIORITIES)}")
        updates.append("priority = ?"); params.append(args.priority); changed.append("priority")
    if getattr(args, "audience_type", None) is not None:
        if args.audience_type not in VALID_AUDIENCE_TYPES:
            err(f"--audience-type must be one of: {', '.join(VALID_AUDIENCE_TYPES)}")
        updates.append("audience_type = ?"); params.append(args.audience_type); changed.append("audience_type")
    if getattr(args, "audience_filter", None) is not None:
        try:
            json.loads(args.audience_filter) if isinstance(args.audience_filter, str) else args.audience_filter
        except (json.JSONDecodeError, TypeError):
            err("--audience-filter must be valid JSON")
        updates.append("audience_filter = ?"); params.append(args.audience_filter); changed.append("audience_filter")
    if getattr(args, "publish_date", None) is not None:
        updates.append("publish_date = ?"); params.append(args.publish_date); changed.append("publish_date")
    if getattr(args, "expiry_date", None) is not None:
        updates.append("expiry_date = ?"); params.append(args.expiry_date); changed.append("expiry_date")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(announcement_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_announcement SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-announcement", "educlaw_announcement", announcement_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": announcement_id, "updated_fields": changed})


def publish_announcement(conn, args):
    """Publish announcement and create notifications for each recipient."""
    announcement_id = getattr(args, "announcement_id", None)
    if not announcement_id:
        err("--announcement-id is required")

    row = conn.execute(Q.from_(Table("educlaw_announcement")).select(Table("educlaw_announcement").star).where(Field("id") == P()).get_sql(), (announcement_id,)).fetchone()
    if not row:
        err(f"Announcement {announcement_id} not found")
    if row["announcement_status"] != "draft":
        err(f"Announcement is already '{row['announcement_status']}'. Only draft announcements can be published.")

    published_by = getattr(args, "published_by", None) or getattr(args, "user_id", None) or ""
    now = _now_iso()

    # Use publish_date from record or now
    publish_date = row["publish_date"] or now

    _ann = Table("educlaw_announcement")
    conn.execute(
        Q.update(_ann)
        .set(_ann.announcement_status, 'published')
        .set(_ann.published_by, P())
        .set(_ann.publish_date, P())
        .set(_ann.updated_at, P())
        .where(_ann.id == P())
        .get_sql(),
        (published_by, publish_date, now, announcement_id)
    )

    company_id = row["company_id"]
    audience_type = row["audience_type"]
    audience_filter = row["audience_filter"]
    title = row["title"]
    priority = row["priority"]
    body = row["body"][:500] if row["body"] else ""  # Truncate for notification message

    recipients = _get_audience_recipients(conn, audience_type, audience_filter, company_id)

    notif_count = 0
    for recipient_type, recipient_id in recipients:
        _create_notification(
            conn, recipient_type, recipient_id, "announcement",
            title, body, company_id,
            reference_type="educlaw_announcement", reference_id=announcement_id
        )
        notif_count += 1

    audit(conn, SKILL, "edu-publish-announcement", "educlaw_announcement", announcement_id,
          new_values={"published_by": published_by, "notifications_created": notif_count})
    conn.commit()
    ok({"id": announcement_id, "announcement_status": "published",
        "notifications_created": notif_count, "audience_type": audience_type})


def list_announcements(conn, args):
    """List announcements with optional filters."""
    _ann = Table("educlaw_announcement")
    q = Q.from_(_ann).select(_ann.star)
    params = []

    if getattr(args, "announcement_status", None):
        q = q.where(_ann.announcement_status == P()); params.append(args.announcement_status)
    if getattr(args, "audience_type", None):
        q = q.where(_ann.audience_type == P()); params.append(args.audience_type)
    if getattr(args, "company_id", None):
        q = q.where(_ann.company_id == P()); params.append(args.company_id)
    if getattr(args, "date_from", None):
        q = q.where(_ann.publish_date >= P()); params.append(args.date_from)
    if getattr(args, "date_to", None):
        q = q.where(_ann.publish_date <= P()); params.append(args.date_to)
    if getattr(args, "priority", None):
        q = q.where(_ann.priority == P()); params.append(args.priority)

    q = q.orderby(_ann.created_at, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()

    announcements = []
    for r in rows:
        d = dict(r)
        if d.get("audience_filter"):
            try:
                d["audience_filter"] = json.loads(d["audience_filter"])
            except Exception:
                d["audience_filter"] = {}
        announcements.append(d)

    ok({"announcements": announcements, "count": len(announcements)})


def get_announcement(conn, args):
    """Get announcement details."""
    announcement_id = getattr(args, "announcement_id", None)
    if not announcement_id:
        err("--announcement-id is required")

    row = conn.execute(Q.from_(Table("educlaw_announcement")).select(Table("educlaw_announcement").star).where(Field("id") == P()).get_sql(), (announcement_id,)).fetchone()
    if not row:
        err(f"Announcement {announcement_id} not found")

    data = dict(row)
    if data.get("audience_filter"):
        try:
            data["audience_filter"] = json.loads(data["audience_filter"])
        except Exception:
            data["audience_filter"] = {}

    # Count notifications sent for this announcement
    _n = Table("educlaw_notification")
    notif_count = conn.execute(
        Q.from_(_n).select(fn.Count(_n.star).as_("cnt")).where(_n.reference_id == P()).get_sql(),
        (announcement_id,)
    ).fetchone()
    data["notifications_sent"] = notif_count["cnt"] if notif_count else 0

    ok(data)


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

def send_notification(conn, args):
    """Send targeted notification to a specific recipient."""
    recipient_type = getattr(args, "recipient_type", None)
    recipient_id = getattr(args, "recipient_id", None)
    notification_type = getattr(args, "notification_type", None)
    title = getattr(args, "title", None)
    message = getattr(args, "message", None)
    company_id = getattr(args, "company_id", None)

    if not recipient_type:
        err("--recipient-type is required")
    if not recipient_id:
        err("--recipient-id is required")
    if not notification_type:
        err("--notification-type is required")
    if not title:
        err("--title is required")
    if not message:
        err("--message is required")
    if not company_id:
        err("--company-id is required")

    if recipient_type not in VALID_RECIPIENT_TYPES:
        err(f"--recipient-type must be one of: {', '.join(VALID_RECIPIENT_TYPES)}")
    if notification_type not in VALID_NOTIFICATION_TYPES:
        err(f"--notification-type must be one of: {', '.join(VALID_NOTIFICATION_TYPES)}")

    # Validate recipient exists
    if recipient_type == "student":
        if not conn.execute(Q.from_(Table("educlaw_student")).select(Field("id")).where(Field("id") == P()).get_sql(), (recipient_id,)).fetchone():
            err(f"Student {recipient_id} not found")
    elif recipient_type == "guardian":
        if not conn.execute(Q.from_(Table("educlaw_guardian")).select(Field("id")).where(Field("id") == P()).get_sql(), (recipient_id,)).fetchone():
            err(f"Guardian {recipient_id} not found")
    elif recipient_type == "employee":
        if not conn.execute(Q.from_(Table("employee")).select(Field("id")).where(Field("id") == P()).get_sql(), (recipient_id,)).fetchone():
            err(f"Employee {recipient_id} not found")

    sent_via = getattr(args, "sent_via", None) or "system"
    if sent_via not in VALID_SENT_VIA:
        err(f"--sent-via must be one of: {', '.join(VALID_SENT_VIA)}")

    reference_type = getattr(args, "reference_type", None)
    reference_id_val = getattr(args, "reference_id", None)

    notif_id = _create_notification(
        conn, recipient_type, recipient_id, notification_type,
        title, message, company_id,
        reference_type=reference_type, reference_id=reference_id_val,
        sent_via=sent_via
    )
    conn.commit()
    ok({"id": notif_id, "recipient_type": recipient_type, "recipient_id": recipient_id,
        "notification_type": notification_type})


def list_notifications(conn, args):
    """List notifications with optional filters."""
    _n = Table("educlaw_notification")
    q = Q.from_(_n).select(_n.star)
    params = []

    if getattr(args, "recipient_type", None):
        q = q.where(_n.recipient_type == P()); params.append(args.recipient_type)
    if getattr(args, "recipient_id", None):
        q = q.where(_n.recipient_id == P()); params.append(args.recipient_id)
    if getattr(args, "notification_type", None):
        q = q.where(_n.notification_type == P()); params.append(args.notification_type)
    if getattr(args, "is_read", None) is not None:
        q = q.where(_n.is_read == P()); params.append(int(args.is_read))
    if getattr(args, "company_id", None):
        q = q.where(_n.company_id == P()); params.append(args.company_id)

    q = q.orderby(_n.created_at, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 100)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"notifications": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# PROGRESS REPORT
# ─────────────────────────────────────────────────────────────────────────────

def send_progress_report(conn, args):
    """Generate and send mid-term progress report to student and guardians."""
    student_id = getattr(args, "student_id", None)
    academic_term_id = getattr(args, "academic_term_id", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not academic_term_id:
        err("--academic-term-id is required")
    if not company_id:
        err("--company-id is required")

    # Validate student
    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")

    # Validate academic term
    term_row = conn.execute(Q.from_(Table("educlaw_academic_term")).select(Table("educlaw_academic_term").star).where(Field("id") == P()).get_sql(), (academic_term_id,)).fetchone()
    if not term_row:
        err(f"Academic term {academic_term_id} not found")

    student = dict(student_row)
    term = dict(term_row)

    # Get current grades per section in this term
    _ce = Table("educlaw_course_enrollment")
    _sec = Table("educlaw_section")
    _c = Table("educlaw_course")
    enrollments = conn.execute(
        Q.from_(_ce).join(_sec).on(_sec.id == _ce.section_id)
        .join(_c).on(_c.id == _sec.course_id)
        .select(_ce.id, _ce.section_id, _ce.final_percentage, _ce.final_letter_grade,
                _ce.is_grade_submitted, _ce.enrollment_status,
                _sec.section_number, _c.course_code, _c.name.as_("course_name"), _c.credit_hours)
        .where(_ce.student_id == P()).where(_sec.academic_term_id == P())
        .where(_ce.enrollment_status.notin(['dropped', 'withdrawn']))
        .orderby(_c.course_code)
        .get_sql(),
        (student_id, academic_term_id)
    ).fetchall()

    # Get attendance summary for the term
    _sa = Table("educlaw_student_attendance")
    att_rows = conn.execute(
        Q.from_(_sa).select(_sa.attendance_status, fn.Count(_sa.star).as_("cnt"))
        .where(_sa.student_id == P())
        .where(_sa.attendance_date >= P()).where(_sa.attendance_date <= P())
        .groupby(_sa.attendance_status)
        .get_sql(),
        (student_id, term["start_date"], term["end_date"])
    ).fetchall()
    att_counts = {r["attendance_status"]: r["cnt"] for r in att_rows}
    total_days = sum(att_counts.values())
    present = att_counts.get("present", 0)
    excused = att_counts.get("excused", 0)
    absent = att_counts.get("absent", 0)
    tardy = att_counts.get("tardy", 0)
    att_pct = "0.00"
    if total_days > 0:
        pct = (Decimal(str(present + excused)) / Decimal(str(total_days)) * Decimal("100"))
        att_pct = str(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # Build progress report message
    enrollment_lines = []
    for e in enrollments:
        grade_info = e["final_letter_grade"] or "In Progress"
        pct_info = f" ({e['final_percentage']}%)" if e["final_percentage"] else ""
        enrollment_lines.append(f"{e['course_code']} {e['course_name']}: {grade_info}{pct_info}")

    report_body = (
        f"Progress Report for {student['full_name']} — {term['name']}\n\n"
        f"Academic Standing: {student.get('academic_standing', 'N/A')}\n"
        f"Cumulative GPA: {student.get('cumulative_gpa', 'N/A')}\n\n"
        f"Current Courses:\n" + "\n".join(enrollment_lines) + "\n\n"
        f"Attendance ({term['name']}): {present+excused}/{total_days} days "
        f"({att_pct}%) | Absent: {absent} | Tardy: {tardy}"
    )

    report_title = f"Progress Report: {student['full_name']} — {term['name']}"
    notifications_created = []

    # Send to student
    notif_id = _create_notification(
        conn, "student", student_id, "progress_report",
        report_title, report_body, company_id,
        reference_type="educlaw_academic_term", reference_id=academic_term_id
    )
    notifications_created.append({"recipient_type": "student", "recipient_id": student_id, "notif_id": notif_id})

    # Send to guardians who receive communications
    _g = Table("educlaw_guardian")
    _sg = Table("educlaw_student_guardian")
    guardians = conn.execute(
        Q.from_(_g).join(_sg).on(_sg.guardian_id == _g.id)
        .select(_g.id, _g.full_name)
        .where(_sg.student_id == P()).where(_sg.receives_communications == 1)
        .get_sql(),
        (student_id,)
    ).fetchall()
    for g in guardians:
        guardian_title = f"Progress Report: {student['full_name']} — {term['name']}"
        notif_id = _create_notification(
            conn, "guardian", g["id"], "progress_report",
            guardian_title, report_body, company_id,
            reference_type="educlaw_academic_term", reference_id=academic_term_id
        )
        notifications_created.append({"recipient_type": "guardian", "recipient_id": g["id"], "notif_id": notif_id})

    conn.commit()
    ok({
        "student_id": student_id,
        "academic_term_id": academic_term_id,
        "enrollment_count": len(enrollments),
        "attendance_percentage": att_pct,
        "notifications_created": len(notifications_created),
        "recipients": notifications_created,
    })


# ─────────────────────────────────────────────────────────────────────────────
# EMERGENCY ALERT
# ─────────────────────────────────────────────────────────────────────────────

def send_emergency_alert(conn, args):
    """Broadcast emergency message to ALL recipients (students + guardians + staff)."""
    title = getattr(args, "title", None)
    message = getattr(args, "message", None)
    company_id = getattr(args, "company_id", None)

    if not title:
        err("--title is required")
    if not message:
        err("--message is required")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    sent_by = getattr(args, "sent_by", None) or getattr(args, "user_id", None) or ""
    now = _now_iso()

    # Create emergency announcement
    ann_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_announcement", {
        "id": P(), "title": P(), "body": P(), "priority": P(),
        "audience_type": P(), "audience_filter": P(),
        "publish_date": P(), "expiry_date": P(), "announcement_status": P(),
        "published_by": P(), "company_id": P(), "created_at": P(), "updated_at": P()
    })
    conn.execute(sql,
        (ann_id, title, message, "emergency", "all", None,
         now, None, "published", sent_by, company_id, now, now)
    )

    # Get ALL recipients in the company
    all_recipients = _get_audience_recipients(conn, "all", None, company_id)

    notif_count = 0
    for recipient_type, recipient_id in all_recipients:
        _create_notification(
            conn, recipient_type, recipient_id, "emergency",
            title, message, company_id,
            reference_type="educlaw_announcement", reference_id=ann_id
        )
        notif_count += 1

    # Enhanced audit logging
    audit(conn, SKILL, "edu-send-emergency-alert", "educlaw_announcement", ann_id,
          new_values={
              "title": title,
              "sent_by": sent_by,
              "notifications_created": notif_count,
              "priority": "emergency",
              "company_id": company_id,
          })

    conn.commit()
    ok({
        "announcement_id": ann_id,
        "announcement_status": "published",
        "priority": "emergency",
        "notifications_created": notif_count,
        "company_id": company_id,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-announcement": add_announcement,
    "edu-update-announcement": update_announcement,
    "edu-submit-announcement": publish_announcement,
    "edu-list-announcements": list_announcements,
    "edu-get-announcement": get_announcement,
    "edu-submit-notification": send_notification,
    "edu-list-notifications": list_notifications,
    "edu-generate-progress-report": send_progress_report,
    "edu-submit-emergency-alert": send_emergency_alert,
}
