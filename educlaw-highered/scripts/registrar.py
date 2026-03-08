"""EduClaw Higher Education — registrar domain module (12 actions)

Degree programs, courses, sections, enrollments, and calendar reporting.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit

    ENTITY_PREFIXES.setdefault("highered_degree_program", "HDEG-")
except ImportError:
    pass

SKILL = "highered-educlaw-highered"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_today = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")

VALID_DEGREE_TYPES = ("associate", "bachelor", "master", "doctoral", "certificate")
VALID_PROGRAM_STATUSES = ("active", "inactive", "phasing_out")
VALID_SECTION_STATUSES = ("open", "closed", "cancelled")
VALID_ENROLLMENT_STATUSES = ("enrolled", "dropped", "withdrawn", "completed")


# ===========================================================================
# Degree Programs
# ===========================================================================

def add_degree_program(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    name = getattr(args, "name", None)
    if not name:
        return err("--name is required")
    degree_type = getattr(args, "degree_type", None) or "bachelor"
    if degree_type not in VALID_DEGREE_TYPES:
        return err(f"Invalid degree_type: {degree_type}. Must be one of: {', '.join(VALID_DEGREE_TYPES)}")
    department = getattr(args, "department", None) or ""
    credits_required = int(getattr(args, "credits_required", None) or 0)
    program_status = getattr(args, "program_status", None) or "active"
    if program_status not in VALID_PROGRAM_STATUSES:
        return err(f"Invalid program_status: {program_status}")

    prog_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = company_id
    naming = get_next_name(conn, "highered_degree_program")

    conn.execute("""
        INSERT INTO highered_degree_program
        (id, naming_series, name, degree_type, department, credits_required,
         program_status, company_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (prog_id, naming, name, degree_type, department, credits_required,
          program_status, company_id, now, now))
    audit(conn, SKILL, "highered-add-degree-program", "highered_degree_program", prog_id,
          new_values={"name": name, "degree_type": degree_type})
    conn.commit()
    ok({"id": prog_id, "naming_series": naming, "name": name,
        "degree_type": degree_type, "program_status": program_status})


def update_degree_program(conn, args):
    prog_id = getattr(args, "id", None)
    if not prog_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_degree_program WHERE id=?", (prog_id,)).fetchone()
    if not row:
        return err("Degree program not found")

    updates, params = [], []
    for field in ("name", "department"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    degree_type = getattr(args, "degree_type", None)
    if degree_type is not None:
        if degree_type not in VALID_DEGREE_TYPES:
            return err(f"Invalid degree_type: {degree_type}")
        updates.append("degree_type=?")
        params.append(degree_type)
    credits_required = getattr(args, "credits_required", None)
    if credits_required is not None:
        updates.append("credits_required=?")
        params.append(int(credits_required))
    program_status = getattr(args, "program_status", None)
    if program_status is not None:
        if program_status not in VALID_PROGRAM_STATUSES:
            return err(f"Invalid program_status: {program_status}")
        updates.append("program_status=?")
        params.append(program_status)
    if not updates:
        return err("No fields to update")
    updates.append("updated_at=?")
    params.append(_now_iso())
    params.append(prog_id)
    conn.execute(f"UPDATE highered_degree_program SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    ok({"id": prog_id, "updated": True})


def list_degree_programs(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_degree_program WHERE company_id=?"
    params = [company_id]
    department = getattr(args, "department", None)
    if department:
        q += " AND department=?"
        params.append(department)
    program_status = getattr(args, "program_status", None)
    if program_status:
        q += " AND program_status=?"
        params.append(program_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY name LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"programs": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Courses
# ===========================================================================

def add_course(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    code = getattr(args, "code", None)
    if not code:
        return err("--code is required")
    name = getattr(args, "name", None)
    if not name:
        return err("--name is required")
    credits = int(getattr(args, "credits", None) or 3)
    department = getattr(args, "department", None) or ""
    prerequisites = getattr(args, "prerequisites", None) or ""
    description = getattr(args, "description", None) or ""

    course_id = str(uuid.uuid4())
    try:
        conn.execute("""
            INSERT INTO highered_course
            (id, code, name, credits, department, prerequisites, description,
             is_active, company_id, created_at)
            VALUES (?,?,?,?,?,?,?,1,?,?)
        """, (course_id, code, name, credits, department, prerequisites,
              description, company_id, _now_iso()))
        audit(conn, SKILL, "highered-add-course", "highered_course", course_id,
              new_values={"code": code, "name": name})
        conn.commit()
        ok({"id": course_id, "code": code, "name": name, "credits": credits})
    except Exception as e:
        if "UNIQUE" in str(e):
            return err(f"Course code {code} already exists for this company")
        return err(str(e))


def update_course(conn, args):
    course_id = getattr(args, "id", None)
    if not course_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_course WHERE id=?", (course_id,)).fetchone()
    if not row:
        return err("Course not found")

    updates, params = [], []
    for field in ("name", "department", "prerequisites", "description"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    credits = getattr(args, "credits", None)
    if credits is not None:
        updates.append("credits=?")
        params.append(int(credits))
    is_active = getattr(args, "is_active", None)
    if is_active is not None:
        updates.append("is_active=?")
        params.append(int(is_active))
    if not updates:
        return err("No fields to update")
    params.append(course_id)
    conn.execute(f"UPDATE highered_course SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    ok({"id": course_id, "updated": True})


def list_courses(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_course WHERE company_id=?"
    params = [company_id]
    department = getattr(args, "department", None)
    if department:
        q += " AND department=?"
        params.append(department)
    is_active = getattr(args, "is_active", None)
    if is_active is not None:
        q += " AND is_active=?"
        params.append(int(is_active))
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY code LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"courses": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Sections
# ===========================================================================

def add_section(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    course_id = getattr(args, "course_id", None)
    if not course_id:
        return err("--course-id is required")
    if not conn.execute("SELECT id FROM highered_course WHERE id=?", (course_id,)).fetchone():
        return err(f"Course {course_id} not found")
    term = getattr(args, "term", None)
    if not term:
        return err("--term is required")
    year = getattr(args, "year", None)
    if not year:
        return err("--year is required")
    year = int(year)
    instructor = getattr(args, "instructor", None) or ""
    capacity = int(getattr(args, "capacity", None) or 30)
    schedule = getattr(args, "schedule", None) or ""
    location = getattr(args, "location", None) or ""

    section_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO highered_section
        (id, course_id, term, year, instructor, capacity, enrolled,
         schedule, location, section_status, company_id, created_at)
        VALUES (?,?,?,?,?,?,0,?,?,?,?,?)
    """, (section_id, course_id, term, year, instructor, capacity,
          schedule, location, "open", company_id, _now_iso()))
    audit(conn, SKILL, "highered-add-section", "highered_section", section_id,
          new_values={"course_id": course_id, "term": term, "year": year})
    conn.commit()
    ok({"id": section_id, "course_id": course_id, "term": term,
        "year": year, "section_status": "open"})


def list_sections(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_section WHERE company_id=?"
    params = [company_id]
    course_id = getattr(args, "course_id", None)
    if course_id:
        q += " AND course_id=?"
        params.append(course_id)
    term = getattr(args, "term", None)
    if term:
        q += " AND term=?"
        params.append(term)
    year = getattr(args, "year", None)
    if year:
        q += " AND year=?"
        params.append(int(year))
    section_status = getattr(args, "section_status", None)
    if section_status:
        q += " AND section_status=?"
        params.append(section_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY term, year LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"sections": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Enrollments
# ===========================================================================

def add_enrollment(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    section_id = getattr(args, "section_id", None)
    if not section_id:
        return err("--section-id is required")

    section = conn.execute("SELECT * FROM highered_section WHERE id=?", (section_id,)).fetchone()
    if not section:
        return err(f"Section {section_id} not found")
    if section["section_status"] != "open":
        return err("Section is not open for enrollment")
    if section["enrolled"] >= section["capacity"]:
        return err("Section is at capacity")

    # Check duplicate
    dup = conn.execute(
        "SELECT id FROM highered_enrollment WHERE student_id=? AND section_id=? AND enrollment_status='enrolled'",
        (student_id, section_id)
    ).fetchone()
    if dup:
        return err("Student already enrolled in this section")

    enrollment_id = str(uuid.uuid4())
    now = _now_iso()
    enrollment_date = getattr(args, "enrollment_date", None) or _today()
    conn.execute("""
        INSERT INTO highered_enrollment
        (id, student_id, section_id, enrollment_date, enrollment_status,
         grade, grade_points, company_id, created_at, updated_at)
        VALUES (?,?,?,?,'enrolled','','',?,?,?)
    """, (enrollment_id, student_id, section_id, enrollment_date,
          company_id, now, now))
    conn.execute(
        "UPDATE highered_section SET enrolled = enrolled + 1 WHERE id=?",
        (section_id,)
    )
    audit(conn, SKILL, "highered-add-enrollment", "highered_enrollment", enrollment_id,
          new_values={"student_id": student_id, "section_id": section_id})
    conn.commit()
    ok({"id": enrollment_id, "student_id": student_id,
        "section_id": section_id, "enrollment_status": "enrolled"})


def drop_enrollment(conn, args):
    enrollment_id = getattr(args, "id", None)
    if not enrollment_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_enrollment WHERE id=?", (enrollment_id,)).fetchone()
    if not row:
        return err("Enrollment not found")
    if row["enrollment_status"] != "enrolled":
        return err(f"Cannot drop: enrollment is '{row['enrollment_status']}'")

    now = _now_iso()
    conn.execute(
        "UPDATE highered_enrollment SET enrollment_status='dropped', updated_at=? WHERE id=?",
        (now, enrollment_id)
    )
    conn.execute(
        "UPDATE highered_section SET enrolled = MAX(enrolled - 1, 0) WHERE id=?",
        (row["section_id"],)
    )
    conn.commit()
    ok({"id": enrollment_id, "enrollment_status": "dropped"})


def list_enrollments(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_enrollment WHERE company_id=?"
    params = [company_id]
    student_id = getattr(args, "student_id", None)
    if student_id:
        q += " AND student_id=?"
        params.append(student_id)
    section_id = getattr(args, "section_id", None)
    if section_id:
        q += " AND section_id=?"
        params.append(section_id)
    enrollment_status = getattr(args, "enrollment_status", None)
    if enrollment_status:
        q += " AND enrollment_status=?"
        params.append(enrollment_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY enrollment_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"enrollments": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Reports
# ===========================================================================

def academic_calendar_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    year = getattr(args, "year", None)
    q = """
        SELECT s.term, s.year, COUNT(*) as total_sections,
               SUM(s.enrolled) as total_enrolled,
               SUM(s.capacity) as total_capacity
        FROM highered_section s
        WHERE s.company_id=?
    """
    params = [company_id]
    if year:
        q += " AND s.year=?"
        params.append(int(year))
    q += " GROUP BY s.term, s.year ORDER BY s.year DESC, s.term"
    rows = conn.execute(q, params).fetchall()
    ok({"calendar": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-add-degree-program": add_degree_program,
    "highered-update-degree-program": update_degree_program,
    "highered-list-degree-programs": list_degree_programs,
    "highered-add-course": add_course,
    "highered-update-course": update_course,
    "highered-list-courses": list_courses,
    "highered-add-section": add_section,
    "highered-list-sections": list_sections,
    "highered-add-enrollment": add_enrollment,
    "highered-drop-enrollment": drop_enrollment,
    "highered-list-enrollments": list_enrollments,
    "highered-academic-calendar-report": academic_calendar_report,
}
