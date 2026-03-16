"""EduClaw — enrollment domain module

Actions for enrollment: program enrollment, course section enrollment,
drop/add, waitlist management, prerequisite enforcement.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.naming import get_next_name
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, LiteralValue
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAM ENROLLMENT
# ─────────────────────────────────────────────────────────────────────────────

def enroll_in_program(conn, args):
    student_id = getattr(args, "student_id", None)
    program_id = getattr(args, "program_id", None)
    academic_year_id = getattr(args, "academic_year_id", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not program_id:
        err("--program-id is required")
    if not academic_year_id:
        err("--academic-year-id is required")
    if not company_id:
        err("--company-id is required")

    # Validate student exists and is active
    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")
    student = dict(student_row)
    if student["status"] != "active":
        err(f"Student must be active to enroll (current status: {student['status']})")
    if student["registration_hold"]:
        err("Student has a registration hold — resolve outstanding fees before enrolling")

    # Validate program and academic year
    if not conn.execute(Q.from_(Table("educlaw_program")).select(Field("id")).where(Field("id") == P()).get_sql(), (program_id,)).fetchone():
        err(f"Program {program_id} not found")
    if not conn.execute(Q.from_(Table("educlaw_academic_year")).select(Field("id")).where(Field("id") == P()).get_sql(), (academic_year_id,)).fetchone():
        err(f"Academic year {academic_year_id} not found")
    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    # Check for existing active enrollment in same program/year
    _pe = Table("educlaw_program_enrollment")
    existing = conn.execute(
        Q.from_(_pe).select(_pe.id)
        .where(_pe.student_id == P()).where(_pe.program_id == P()).where(_pe.academic_year_id == P())
        .get_sql(),
        (student_id, program_id, academic_year_id)
    ).fetchone()
    if existing:
        err(f"Student is already enrolled in this program for this academic year")

    naming = get_next_name(conn, "educlaw_program_enrollment", company_id=company_id)
    enr_id = str(uuid.uuid4())
    enrollment_date = getattr(args, "enrollment_date", None) or _now_iso()[:10]
    now = _now_iso()

    sql, _ = insert_row("educlaw_program_enrollment", {"id": P(), "naming_series": P(), "student_id": P(), "program_id": P(), "academic_year_id": P(), "enrollment_date": P(), "enrollment_status": P(), "fee_invoice_id": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})


    conn.execute(sql,
        (enr_id, naming, student_id, program_id, academic_year_id,
         enrollment_date, "active", "",
         company_id, now, now, getattr(args, "user_id", None) or "")
    )

    # Send enrollment confirmed notification
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (notif_id, "student", student_id, "enrollment_confirmed",
         "Program Enrollment Confirmed",
         f"You have been enrolled in the program. Enrollment ID: {naming}",
         "educlaw_program_enrollment", enr_id, company_id, now,
         getattr(args, "user_id", None) or "")
    )

    audit(conn, SKILL, "edu-enroll-in-program", "educlaw_program_enrollment", enr_id,
          new_values={"naming_series": naming, "student_id": student_id,
                      "program_id": program_id, "academic_year_id": academic_year_id})
    conn.commit()
    ok({"id": enr_id, "naming_series": naming, "student_id": student_id,
        "program_id": program_id, "enrollment_status": "active"})


def withdraw_from_program(conn, args):
    enrollment_id = getattr(args, "enrollment_id", None)
    if not enrollment_id:
        err("--enrollment-id is required")

    row = conn.execute(Q.from_(Table("educlaw_program_enrollment")).select(Table("educlaw_program_enrollment").star).where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    if not row:
        err(f"Program enrollment {enrollment_id} not found")

    r = dict(row)
    if r["enrollment_status"] != "active":
        err(f"Only active enrollments can be withdrawn (current: {r['enrollment_status']})")

    now = _now_iso()
    _pe = Table("educlaw_program_enrollment")
    conn.execute(
        Q.update(_pe)
        .set(_pe.enrollment_status, 'withdrawn')
        .set(_pe.updated_at, LiteralValue("datetime('now')"))
        .where(_pe.id == P())
        .get_sql(),
        (enrollment_id,)
    )

    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (notif_id, "student", r["student_id"], "announcement",
         "Program Withdrawal Processed",
         f"Your withdrawal from program enrollment {r['naming_series']} has been processed.",
         "educlaw_program_enrollment", enrollment_id, r["company_id"], now,
         getattr(args, "user_id", None) or "")
    )

    audit(conn, SKILL, "edu-withdraw-from-program", "educlaw_program_enrollment", enrollment_id,
          new_values={"enrollment_status": "withdrawn"})
    conn.commit()
    ok({"id": enrollment_id, "enrollment_status": "withdrawn"})


def list_program_enrollments(conn, args):
    _pe = Table("educlaw_program_enrollment")
    q = Q.from_(_pe).select(_pe.star)
    params = []

    if getattr(args, "student_id", None):
        q = q.where(_pe.student_id == P()); params.append(args.student_id)
    if getattr(args, "program_id", None):
        q = q.where(_pe.program_id == P()); params.append(args.program_id)
    if getattr(args, "academic_year_id", None):
        q = q.where(_pe.academic_year_id == P()); params.append(args.academic_year_id)
    if getattr(args, "enrollment_status", None):
        q = q.where(_pe.enrollment_status == P()); params.append(args.enrollment_status)
    if getattr(args, "company_id", None):
        q = q.where(_pe.company_id == P()); params.append(args.company_id)

    q = q.orderby(_pe.enrollment_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"program_enrollments": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# COURSE SECTION ENROLLMENT
# ─────────────────────────────────────────────────────────────────────────────

def _check_prerequisite(conn, student_id, course_id):
    """Check if student has met all prerequisites for a course. Returns error msg or None."""
    _cp = Table("educlaw_course_prerequisite")
    _c = Table("educlaw_course")
    prereqs = conn.execute(
        Q.from_(_cp).join(_c).on(_c.id == _cp.prerequisite_course_id)
        .select(_cp.prerequisite_course_id, _cp.min_grade, _cp.is_corequisite, _c.course_code)
        .where(_cp.course_id == P())
        .get_sql(),
        (course_id,)
    ).fetchall()

    for prereq in prereqs:
        p = dict(prereq)
        if p["is_corequisite"]:
            continue  # Corequisites can be taken concurrently

        # Check if student has completed this prerequisite with sufficient grade
        _ce = Table("educlaw_course_enrollment")
        _s = Table("educlaw_section")
        completed = conn.execute(
            Q.from_(_ce).join(_s).on(_s.id == _ce.section_id)
            .select(_ce.final_letter_grade, _ce.final_grade_points, _ce.is_grade_submitted,
                    _ce.enrollment_status)
            .where(_ce.student_id == P()).where(_s.course_id == P())
            .where(_ce.is_grade_submitted == 1)
            .where(_ce.enrollment_status == 'completed')
            .get_sql(),
            (student_id, p["prerequisite_course_id"])
        ).fetchone()

        if not completed:
            return f"Prerequisite not met: {p['course_code']} must be completed first"

        if p["min_grade"]:
            # Check that final_grade >= min_grade
            # Grade comparison: A > B > C > D > F (need to compare via grade_points if possible)
            grade_map = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
                         "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "D-": 0.7,
                         "F": 0.0, "P": None, "NP": None, "W": None, "I": None}
            c = dict(completed)
            req_pts = grade_map.get(p["min_grade"], 0.0)
            earned_pts = float(c["final_grade_points"]) if c["final_grade_points"] else 0.0
            if req_pts is not None and earned_pts < req_pts:
                return (f"Prerequisite {p['course_code']} requires minimum grade "
                        f"{p['min_grade']} (earned: {c['final_letter_grade']})")
    return None


def enroll_in_section(conn, args):
    student_id = getattr(args, "student_id", None)
    section_id = getattr(args, "section_id", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not section_id:
        err("--section-id is required")
    if not company_id:
        err("--company-id is required")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")
    student = dict(student_row)
    if student["status"] != "active":
        err(f"Student must be active to enroll in sections")
    if student["registration_hold"]:
        err("Student has a registration hold")

    section_row = conn.execute(Q.from_(Table("educlaw_section")).select(Table("educlaw_section").star).where(Field("id") == P()).get_sql(), (section_id,)).fetchone()
    if not section_row:
        err(f"Section {section_id} not found")
    section = dict(section_row)

    if section["status"] != "open":
        err(f"Section is not open for enrollment (status: {section['status']})")

    # Check for active program enrollment in same term
    _at = Table("educlaw_academic_term")
    term_row = conn.execute(
        Q.from_(_at).select(_at.academic_year_id).where(_at.id == P()).get_sql(),
        (section["academic_term_id"],)
    ).fetchone()
    if term_row:
        _pe = Table("educlaw_program_enrollment")
        prog_enr = conn.execute(
            Q.from_(_pe).select(_pe.id)
            .where(_pe.student_id == P()).where(_pe.academic_year_id == P())
            .where(_pe.enrollment_status == 'active')
            .get_sql(),
            (student_id, term_row["academic_year_id"])
        ).fetchone()
        if not prog_enr:
            err("Student must have an active program enrollment for this academic year")

    # Check for duplicate enrollment
    dup = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Field("id")).where(Field("student_id") == P()).where(Field("section_id") == P()).get_sql(), (student_id, section_id)).fetchone()
    if dup:
        err("Student is already enrolled in this section")

    # Check for duplicate course in same term (same course, different section)
    _ce2 = Table("educlaw_course_enrollment")
    _s2 = Table("educlaw_section")
    same_course = conn.execute(
        Q.from_(_ce2).join(_s2).on(_s2.id == _ce2.section_id)
        .select(_ce2.id)
        .where(_ce2.student_id == P()).where(_s2.course_id == P())
        .where(_s2.academic_term_id == P())
        .where(_ce2.enrollment_status.isin(['enrolled', 'waitlisted']))
        .get_sql(),
        (student_id, section["course_id"], section["academic_term_id"])
    ).fetchone()
    if same_course:
        err("Student is already enrolled in another section of this course this term")

    # Check prerequisites
    prereq_err = _check_prerequisite(conn, student_id, section["course_id"])
    if prereq_err:
        err(prereq_err)

    now = _now_iso()
    grade_type = getattr(args, "grade_type", None) or "letter"

    # Check if section is full
    if section["current_enrollment"] >= section["max_enrollment"]:
        if section["waitlist_enabled"]:
            # Add to waitlist
            _wl = Table("educlaw_waitlist")
            wait_count = conn.execute(
                Q.from_(_wl).select(fn.Count(_wl.star))
                .where(_wl.section_id == P()).where(_wl.waitlist_status == 'waiting')
                .get_sql(),
                (section_id,)
            ).fetchone()[0]
            if section["waitlist_max"] > 0 and wait_count >= section["waitlist_max"]:
                err("Section is full and waitlist is also full")
            position = wait_count + 1
            wait_id = str(uuid.uuid4())
            sql, _ = insert_row("educlaw_waitlist", {"id": P(), "student_id": P(), "section_id": P(), "position": P(), "requested_date": P(), "waitlist_status": P(), "offer_expires_at": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

            conn.execute(sql,
                (wait_id, student_id, section_id, position, now, "waiting", "",
                 company_id, now, now, getattr(args, "user_id", None) or "")
            )
            conn.commit()
            ok({"id": wait_id, "enrollment_status": "waitlisted", "waitlist_position": position,
                "section_id": section_id, "student_id": student_id})
            return
        else:
            err("Section is full and waitlist is not enabled")

    # Enroll student
    enr_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_course_enrollment", {"id": P(), "student_id": P(), "section_id": P(), "enrollment_date": P(), "enrollment_status": P(), "drop_date": P(), "drop_reason": P(), "final_letter_grade": P(), "final_grade_points": P(), "final_percentage": P(), "grade_submitted_by": P(), "grade_submitted_at": P(), "is_grade_submitted": P(), "is_repeat": P(), "grade_type": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

    conn.execute(sql,
        (enr_id, student_id, section_id, now[:10], "enrolled",
         "", "", "", "0", "0",
         "", "", 0, int(getattr(args, "is_repeat", None) or 0),
         grade_type, company_id, now, now, getattr(args, "user_id", None) or "")
    )

    # Increment section enrollment count
    _sec = Table("educlaw_section")
    conn.execute(
        Q.update(_sec)
        .set(_sec.current_enrollment, LiteralValue('"current_enrollment"+1'))
        .set(_sec.updated_at, LiteralValue("datetime('now')"))
        .where(_sec.id == P())
        .get_sql(),
        (section_id,)
    )

    audit(conn, SKILL, "edu-enroll-in-section", "educlaw_course_enrollment", enr_id,
          new_values={"student_id": student_id, "section_id": section_id})
    conn.commit()
    ok({"id": enr_id, "enrollment_status": "enrolled", "student_id": student_id,
        "section_id": section_id})


def drop_enrollment(conn, args):
    enrollment_id = getattr(args, "enrollment_id", None)
    if not enrollment_id:
        err("--enrollment-id is required")

    row = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Table("educlaw_course_enrollment").star).where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    if not row:
        err(f"Enrollment {enrollment_id} not found")

    r = dict(row)
    if r["enrollment_status"] != "enrolled":
        err(f"Only active enrollments can be dropped (current: {r['enrollment_status']})")
    if r["is_grade_submitted"]:
        err("Cannot drop enrollment after grades have been submitted")

    now = _now_iso()
    drop_reason = getattr(args, "drop_reason", None) or ""
    _ce = Table("educlaw_course_enrollment")
    conn.execute(
        Q.update(_ce)
        .set(_ce.enrollment_status, 'dropped')
        .set(_ce.drop_date, P())
        .set(_ce.drop_reason, P())
        .set(_ce.updated_at, LiteralValue("datetime('now')"))
        .where(_ce.id == P())
        .get_sql(),
        (now[:10], drop_reason, enrollment_id)
    )

    # Decrement section count
    _sec = Table("educlaw_section")
    conn.execute(
        Q.update(_sec)
        .set(_sec.current_enrollment, LiteralValue('MAX(0,"current_enrollment"-1)'))
        .set(_sec.updated_at, LiteralValue("datetime('now')"))
        .where(_sec.id == P())
        .get_sql(),
        (r["section_id"],)
    )

    # Process waitlist if enabled
    section_row = conn.execute(
        Q.from_(_sec).select(_sec.star).where(_sec.id == P()).get_sql(), (r["section_id"],)
    ).fetchone()
    if section_row and dict(section_row)["waitlist_enabled"]:
        _advance_waitlist(conn, r["section_id"], dict(section_row)["company_id"], now)

    audit(conn, SKILL, "edu-drop-enrollment", "educlaw_course_enrollment", enrollment_id,
          new_values={"enrollment_status": "dropped", "drop_reason": drop_reason})
    conn.commit()
    ok({"id": enrollment_id, "enrollment_status": "dropped", "drop_date": now[:10]})


def withdraw_enrollment(conn, args):
    """Withdraw after drop/add period — records W grade."""
    enrollment_id = getattr(args, "enrollment_id", None)
    if not enrollment_id:
        err("--enrollment-id is required")

    row = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Table("educlaw_course_enrollment").star).where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    if not row:
        err(f"Enrollment {enrollment_id} not found")

    r = dict(row)
    if r["enrollment_status"] not in ("enrolled",):
        err(f"Only enrolled courses can be withdrawn (current: {r['enrollment_status']})")
    if r["is_grade_submitted"]:
        err("Cannot withdraw after grades have been submitted")

    now = _now_iso()
    _ce = Table("educlaw_course_enrollment")
    conn.execute(
        Q.update(_ce)
        .set(_ce.enrollment_status, 'withdrawn')
        .set(_ce.drop_date, P())
        .set(_ce.drop_reason, P())
        .set(_ce.final_letter_grade, 'W')
        .set(_ce.updated_at, LiteralValue("datetime('now')"))
        .where(_ce.id == P())
        .get_sql(),
        (now[:10], getattr(args, "drop_reason", None) or "Student withdrawal", enrollment_id)
    )

    _sec = Table("educlaw_section")
    conn.execute(
        Q.update(_sec)
        .set(_sec.current_enrollment, LiteralValue('MAX(0,"current_enrollment"-1)'))
        .set(_sec.updated_at, LiteralValue("datetime('now')"))
        .where(_sec.id == P())
        .get_sql(),
        (r["section_id"],)
    )

    audit(conn, SKILL, "edu-withdraw-enrollment", "educlaw_course_enrollment", enrollment_id,
          new_values={"enrollment_status": "withdrawn", "final_letter_grade": "W"})
    conn.commit()
    ok({"id": enrollment_id, "enrollment_status": "withdrawn",
        "final_letter_grade": "W", "drop_date": now[:10]})


def get_enrollment(conn, args):
    enrollment_id = getattr(args, "enrollment_id", None)
    if not enrollment_id:
        err("--enrollment-id is required")

    row = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Table("educlaw_course_enrollment").star).where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    if not row:
        err(f"Enrollment {enrollment_id} not found")

    data = dict(row)

    # Assessment results summary
    _ar = Table("educlaw_assessment_result")
    _a = Table("educlaw_assessment")
    _ac = Table("educlaw_assessment_category")
    results = conn.execute(
        Q.from_(_ar)
        .join(_a).on(_a.id == _ar.assessment_id)
        .join(_ac).on(_ac.id == _a.category_id)
        .select(_ar.star, _a.name.as_("assessment_name"), _a.max_points, _a.due_date,
                _ac.name.as_("category_name"))
        .where(_ar.course_enrollment_id == P())
        .orderby(_a.due_date)
        .get_sql(),
        (enrollment_id,)
    ).fetchall()
    data["assessment_results"] = [dict(r) for r in results]
    ok(data)


def list_enrollments(conn, args):
    _ce = Table("educlaw_course_enrollment")
    q = Q.from_(_ce).select(_ce.star)
    params = []

    if getattr(args, "student_id", None):
        q = q.where(_ce.student_id == P()); params.append(args.student_id)
    if getattr(args, "section_id", None):
        q = q.where(_ce.section_id == P()); params.append(args.section_id)
    if getattr(args, "academic_term_id", None):
        _sec_sub = Table("educlaw_section")
        sub = Q.from_(_sec_sub).select(_sec_sub.id).where(_sec_sub.academic_term_id == P())
        q = q.where(_ce.section_id.isin(sub))
        params.append(args.academic_term_id)
    if getattr(args, "enrollment_status", None):
        q = q.where(_ce.enrollment_status == P()); params.append(args.enrollment_status)
    if getattr(args, "is_grade_submitted", None) is not None:
        q = q.where(_ce.is_grade_submitted == P()); params.append(int(args.is_grade_submitted))
    if getattr(args, "company_id", None):
        q = q.where(_ce.company_id == P()); params.append(args.company_id)

    q = q.orderby(_ce.enrollment_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"enrollments": [dict(r) for r in rows], "count": len(rows)})


def _advance_waitlist(conn, section_id, company_id, now):
    """Advance waitlist — offer seat to first waiting student."""
    _wl = Table("educlaw_waitlist")
    next_wait = conn.execute(
        Q.from_(_wl).select(_wl.star)
        .where(_wl.section_id == P()).where(_wl.waitlist_status == 'waiting')
        .orderby(_wl.position, order=Order.asc).limit(1)
        .get_sql(),
        (section_id,)
    ).fetchone()
    if not next_wait:
        return

    w = dict(next_wait)
    # Calculate offer expiry (48 hours)
    from datetime import timedelta
    offer_expires = (datetime.now(timezone.utc) + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute(
        Q.update(_wl)
        .set(_wl.waitlist_status, 'offered')
        .set(_wl.offer_expires_at, P())
        .set(_wl.updated_at, LiteralValue("datetime('now')"))
        .where(_wl.id == P())
        .get_sql(),
        (offer_expires, w["id"])
    )
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (notif_id, "student", w["student_id"], "enrollment_confirmed",
         "Waitlist Seat Offered",
         f"A seat is now available in section {section_id}. Offer expires: {offer_expires}",
         "educlaw_waitlist", w["id"], company_id, now, "system")
    )


def process_waitlist(conn, args):
    section_id = getattr(args, "section_id", None)
    if not section_id:
        err("--section-id is required")

    section_row = conn.execute(Q.from_(Table("educlaw_section")).select(Table("educlaw_section").star).where(Field("id") == P()).get_sql(), (section_id,)).fetchone()
    if not section_row:
        err(f"Section {section_id} not found")

    section = dict(section_row)
    now = _now_iso()

    if section["current_enrollment"] >= section["max_enrollment"]:
        ok({"section_id": section_id, "message": "Section is full — no seat to offer"})
        return

    _advance_waitlist(conn, section_id, section["company_id"], now)
    conn.commit()
    ok({"section_id": section_id, "message": "Waitlist processed — next student offered seat"})


def list_waitlist(conn, args):
    _wl = Table("educlaw_waitlist")
    q = Q.from_(_wl).select(_wl.star)
    params = []

    if getattr(args, "section_id", None):
        q = q.where(_wl.section_id == P()); params.append(args.section_id)
    if getattr(args, "student_id", None):
        q = q.where(_wl.student_id == P()); params.append(args.student_id)
    if getattr(args, "waitlist_status", None):
        q = q.where(_wl.waitlist_status == P()); params.append(args.waitlist_status)
    if getattr(args, "company_id", None):
        q = q.where(_wl.company_id == P()); params.append(args.company_id)

    q = q.orderby(_wl.section_id).orderby(_wl.position)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"waitlist": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-create-program-enrollment": enroll_in_program,
    "edu-cancel-program-enrollment": withdraw_from_program,
    "edu-list-program-enrollments": list_program_enrollments,
    "edu-create-section-enrollment": enroll_in_section,
    "edu-cancel-enrollment": drop_enrollment,
    "edu-terminate-enrollment": withdraw_enrollment,
    "edu-get-enrollment": get_enrollment,
    "edu-list-enrollments": list_enrollments,
    "edu-apply-waitlist": process_waitlist,
    "edu-list-waitlist": list_waitlist,
}
