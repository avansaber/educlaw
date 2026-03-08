"""EduClaw Higher Education — records domain module (10 actions)

Student records, transcripts, GPA calculation, degree audit, holds, academic standing.
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.decimal_utils import to_decimal, round_currency

    ENTITY_PREFIXES.setdefault("highered_student_record", "HSTU-")
except ImportError:
    pass

SKILL = "highered-educlaw-highered"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_STANDINGS = ("good", "probation", "suspension", "dismissal", "dean_list")
VALID_HOLD_TYPES = ("financial", "academic", "disciplinary", "administrative")

# Grade point mapping (standard 4.0 scale)
GRADE_POINTS = {
    "A+": "4.00", "A": "4.00", "A-": "3.70",
    "B+": "3.30", "B": "3.00", "B-": "2.70",
    "C+": "2.30", "C": "2.00", "C-": "1.70",
    "D+": "1.30", "D": "1.00", "D-": "0.70",
    "F": "0.00",
}


# ===========================================================================
# Student Record CRUD
# ===========================================================================

def get_student_record(conn, args):
    record_id = getattr(args, "id", None)
    student_id = getattr(args, "student_id", None)
    if not record_id and not student_id:
        return err("--id or --student-id is required")
    if record_id:
        row = conn.execute("SELECT * FROM highered_student_record WHERE id=?", (record_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM highered_student_record WHERE student_id=?", (student_id,)).fetchone()
    if not row:
        return err("Student record not found")
    ok(dict(row))


def list_student_records(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_student_record WHERE company_id=?"
    params = [company_id]
    program_id = getattr(args, "program_id", None)
    if program_id:
        q += " AND program_id=?"
        params.append(program_id)
    academic_standing = getattr(args, "academic_standing", None)
    if academic_standing:
        q += " AND academic_standing=?"
        params.append(academic_standing)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY name LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"records": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Transcript & GPA
# ===========================================================================

def generate_transcript(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute("SELECT * FROM highered_student_record WHERE student_id=?", (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    enrollments = conn.execute("""
        SELECT e.*, c.code as course_code, c.name as course_name,
               c.credits as course_credits, s.term, s.year
        FROM highered_enrollment e
        JOIN highered_section s ON e.section_id = s.id
        JOIN highered_course c ON s.course_id = c.id
        WHERE e.student_id=?
        ORDER BY s.year, s.term
    """, (student_id,)).fetchall()

    terms = {}
    for e in enrollments:
        key = f"{e['term']} {e['year']}"
        if key not in terms:
            terms[key] = {"term": e["term"], "year": e["year"], "courses": []}
        terms[key]["courses"].append({
            "code": e["course_code"],
            "name": e["course_name"],
            "credits": e["course_credits"],
            "grade": e["grade"],
            "grade_points": e["grade_points"],
            "enrollment_status": e["enrollment_status"],
        })

    ok({
        "student_id": student_id,
        "name": record["name"],
        "program_id": record["program_id"],
        "gpa": record["gpa"],
        "total_credits": record["total_credits"],
        "academic_standing": record["academic_standing"],
        "terms": list(terms.values()),
    })


def calculate_gpa(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute("SELECT * FROM highered_student_record WHERE student_id=?", (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    enrollments = conn.execute("""
        SELECT e.grade, c.credits
        FROM highered_enrollment e
        JOIN highered_section s ON e.section_id = s.id
        JOIN highered_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status='completed' AND e.grade != ''
    """, (student_id,)).fetchall()

    total_points = Decimal("0")
    total_credits = 0
    for e in enrollments:
        gp = GRADE_POINTS.get(e["grade"])
        if gp is not None:
            total_points += to_decimal(gp) * Decimal(str(e["credits"]))
            total_credits += e["credits"]

    if total_credits > 0:
        gpa = str((total_points / Decimal(str(total_credits))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    else:
        gpa = "0.00"

    now = _now_iso()
    conn.execute(
        "UPDATE highered_student_record SET gpa=?, total_credits=?, updated_at=? WHERE student_id=?",
        (gpa, total_credits, now, student_id)
    )
    conn.commit()
    ok({"student_id": student_id, "gpa": gpa, "total_credits": total_credits})


# ===========================================================================
# Degree Audit
# ===========================================================================

def degree_audit(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute("SELECT * FROM highered_student_record WHERE student_id=?", (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    program = conn.execute("SELECT * FROM highered_degree_program WHERE id=?", (record["program_id"],)).fetchone()
    if not program:
        return err("Degree program not found")

    completed = conn.execute("""
        SELECT c.code, c.name, c.credits, e.grade
        FROM highered_enrollment e
        JOIN highered_section s ON e.section_id = s.id
        JOIN highered_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status='completed' AND e.grade NOT IN ('F', '')
    """, (student_id,)).fetchall()

    earned_credits = sum(r["credits"] for r in completed)
    required_credits = program["credits_required"]
    remaining = max(0, required_credits - earned_credits)
    progress_pct = round(earned_credits / required_credits * 100, 1) if required_credits > 0 else 0

    ok({
        "student_id": student_id,
        "program": program["name"],
        "degree_type": program["degree_type"],
        "credits_required": required_credits,
        "credits_earned": earned_credits,
        "credits_remaining": remaining,
        "progress_percent": progress_pct,
        "completed_courses": [dict(r) for r in completed],
        "gpa": record["gpa"],
    })


# ===========================================================================
# Academic Standing
# ===========================================================================

def update_academic_standing(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    academic_standing = getattr(args, "academic_standing", None)
    if not academic_standing:
        return err("--academic-standing is required")
    if academic_standing not in VALID_STANDINGS:
        return err(f"Invalid standing: {academic_standing}. Must be one of: {', '.join(VALID_STANDINGS)}")

    row = conn.execute("SELECT * FROM highered_student_record WHERE student_id=?", (student_id,)).fetchone()
    if not row:
        return err("Student record not found")

    old_standing = row["academic_standing"]
    now = _now_iso()
    conn.execute(
        "UPDATE highered_student_record SET academic_standing=?, updated_at=? WHERE student_id=?",
        (academic_standing, now, student_id)
    )
    audit(conn, SKILL, "highered-update-academic-standing", "highered_student_record", row["id"],
          old_values={"academic_standing": old_standing},
          new_values={"academic_standing": academic_standing})
    conn.commit()
    ok({"student_id": student_id, "academic_standing": academic_standing,
        "previous_standing": old_standing})


# ===========================================================================
# Holds
# ===========================================================================

def add_hold(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    hold_type = getattr(args, "hold_type", None) or "administrative"
    if hold_type not in VALID_HOLD_TYPES:
        return err(f"Invalid hold_type: {hold_type}. Must be one of: {', '.join(VALID_HOLD_TYPES)}")
    reason = getattr(args, "reason", None) or ""
    placed_by = getattr(args, "placed_by", None) or ""

    hold_id = str(uuid.uuid4())
    now = _now_iso()
    conn.execute("""
        INSERT INTO highered_hold
        (id, student_id, hold_type, reason, placed_by, placed_date,
         removed_date, hold_status, company_id, created_at)
        VALUES (?,?,?,?,?,?,'','active',?,?)
    """, (hold_id, student_id, hold_type, reason, placed_by, now,
          company_id, now))
    conn.commit()
    ok({"id": hold_id, "student_id": student_id,
        "hold_type": hold_type, "hold_status": "active"})


def remove_hold(conn, args):
    hold_id = getattr(args, "id", None)
    if not hold_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_hold WHERE id=?", (hold_id,)).fetchone()
    if not row:
        return err("Hold not found")
    if row["hold_status"] != "active":
        return err("Hold is already removed")

    now = _now_iso()
    conn.execute(
        "UPDATE highered_hold SET hold_status='removed', removed_date=? WHERE id=?",
        (now, hold_id)
    )
    conn.commit()
    ok({"id": hold_id, "hold_status": "removed"})


def list_holds(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_hold WHERE company_id=?"
    params = [company_id]
    student_id = getattr(args, "student_id", None)
    if student_id:
        q += " AND student_id=?"
        params.append(student_id)
    hold_status = getattr(args, "hold_status", None)
    if hold_status:
        q += " AND hold_status=?"
        params.append(hold_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"holds": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Reports
# ===========================================================================

def academic_standing_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT academic_standing, COUNT(*) as count
        FROM highered_student_record
        WHERE company_id=?
        GROUP BY academic_standing
        ORDER BY count DESC
    """, (company_id,)).fetchall()
    total = sum(r["count"] for r in rows)
    ok({"standings": [dict(r) for r in rows], "total_students": total})


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-generate-transcript": generate_transcript,
    "highered-calculate-gpa": calculate_gpa,
    "highered-degree-audit": degree_audit,
    "highered-update-academic-standing": update_academic_standing,
    "highered-add-hold": add_hold,
    "highered-remove-hold": remove_hold,
    "highered-list-holds": list_holds,
    "highered-get-student-record": get_student_record,
    "highered-list-student-records": list_student_records,
    "highered-academic-standing-report": academic_standing_report,
}
