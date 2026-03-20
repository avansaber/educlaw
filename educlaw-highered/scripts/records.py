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
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row, dynamic_update
    from erpclaw_lib.vendor.pypika.terms import LiteralValue

    ENTITY_PREFIXES.setdefault("educlaw_student", "HSTU-")
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
        row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (record_id,)).fetchone()
    else:
        row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        return err("Student record not found")
    ok(dict(row))


def list_student_records(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t = Table("educlaw_student")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    program_id = getattr(args, "program_id", None)
    if program_id:
        q = q.where(t.program_id == P())
        params.append(program_id)
    academic_standing = getattr(args, "academic_standing", None)
    if academic_standing:
        q = q.where(t.academic_standing == P())
        params.append(academic_standing)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q = q.orderby(t.name).limit(P()).offset(P())
    params.extend([limit, offset])
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"records": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Transcript & GPA
# ===========================================================================

def generate_transcript(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    enrollments = conn.execute("""
        SELECT e.*, c.code as course_code, c.name as course_name,
               c.credits as course_credits, s.term, s.year
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
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
    record = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    enrollments = conn.execute("""
        SELECT e.grade, c.credits
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
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
    sql, upd_params = dynamic_update("educlaw_student",
        {"gpa": gpa, "total_credits": total_credits, "updated_at": now},
        {"student_id": student_id})
    conn.execute(sql, upd_params)
    conn.commit()
    ok({"student_id": student_id, "gpa": gpa, "total_credits": total_credits})


# ===========================================================================
# Degree Audit
# ===========================================================================

def degree_audit(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    program = conn.execute(Q.from_(Table("highered_degree_program")).select(Table("highered_degree_program").star).where(Field("id") == P()).get_sql(), (record["program_id"],)).fetchone()
    if not program:
        return err("Degree program not found")

    completed = conn.execute("""
        SELECT c.code, c.name, c.credits, e.grade
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
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
# Degree Audit Expansion
# ===========================================================================

def transfer_credit_eval(conn, args):
    """Evaluate transfer credits against a program's requirements.

    Takes a student and evaluates how their transfer courses (provided as JSON)
    map to the target program's required courses.
    """
    student_id = getattr(args, "student_id", None)
    program_id = getattr(args, "program_id", None)

    if not student_id:
        return err("--student-id is required")
    if not program_id:
        return err("--program-id is required (target program)")

    record = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    program = conn.execute(Q.from_(Table("highered_degree_program")).select(Table("highered_degree_program").star).where(Field("id") == P()).get_sql(), (program_id,)).fetchone()
    if not program:
        return err("Degree program not found")

    # Get all completed courses for this student (including transfers)
    completed = conn.execute("""
        SELECT c.code, c.name, c.credits, e.grade
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status='completed' AND e.grade NOT IN ('F', '')
    """, (student_id,)).fetchall()

    completed_codes = {r["code"] for r in completed}
    earned_credits = sum(r["credits"] for r in completed)
    required_credits = program["credits_required"]

    # Check each completed course for transfer applicability
    # A transfer credit is accepted if it maps to a course in the program catalog
    program_courses = conn.execute("""
        SELECT c.code, c.name, c.credits
        FROM educlaw_course c
        WHERE c.is_active = 1
    """, ()).fetchall()
    program_codes = {r["code"] for r in program_courses}

    accepted = []
    not_applicable = []
    for c in completed:
        cd = dict(c)
        if cd["code"] in program_codes:
            accepted.append({
                "code": cd["code"], "name": cd["name"],
                "credits": cd["credits"], "grade": cd["grade"],
                "status": "accepted",
            })
        else:
            not_applicable.append({
                "code": cd["code"], "name": cd["name"],
                "credits": cd["credits"], "grade": cd["grade"],
                "status": "not_applicable",
            })

    accepted_credits = sum(c["credits"] for c in accepted)
    remaining = max(0, required_credits - accepted_credits)

    ok({
        "student_id": student_id,
        "target_program": program["name"],
        "target_program_id": program_id,
        "credits_required": required_credits,
        "accepted_transfer_credits": accepted_credits,
        "credits_remaining": remaining,
        "accepted_courses": accepted,
        "not_applicable_courses": not_applicable,
        "evaluation_date": _now_iso(),
    })


def what_if_audit(conn, args):
    """Simulate a degree audit as if the student changed to a different major/program.

    Runs the same logic as degree_audit but against a hypothetical target program
    instead of the student's current program.
    """
    student_id = getattr(args, "student_id", None)
    program_id = getattr(args, "program_id", None)

    if not student_id:
        return err("--student-id is required")
    if not program_id:
        return err("--program-id is required (target program for what-if)")

    record = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not record:
        return err("Student record not found")

    current_program_id = record["program_id"]

    # Get hypothetical program
    target_program = conn.execute(Q.from_(Table("highered_degree_program")).select(Table("highered_degree_program").star).where(Field("id") == P()).get_sql(), (program_id,)).fetchone()
    if not target_program:
        return err("Target program not found")

    # Also load current program for comparison
    current_program = None
    if current_program_id:
        current_program = conn.execute(Q.from_(Table("highered_degree_program")).select(Table("highered_degree_program").star).where(Field("id") == P()).get_sql(), (current_program_id,)).fetchone()

    # Get completed courses
    completed = conn.execute("""
        SELECT c.code, c.name, c.credits, e.grade
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status='completed' AND e.grade NOT IN ('F', '')
    """, (student_id,)).fetchall()

    earned_credits = sum(r["credits"] for r in completed)
    target_required = target_program["credits_required"]
    target_remaining = max(0, target_required - earned_credits)
    target_progress = round(earned_credits / target_required * 100, 1) if target_required > 0 else 0

    current_required = current_program["credits_required"] if current_program else 0
    current_remaining = max(0, current_required - earned_credits)
    current_progress = round(earned_credits / current_required * 100, 1) if current_required > 0 else 0

    ok({
        "student_id": student_id,
        "current_program": {
            "id": current_program_id,
            "name": current_program["name"] if current_program else "None",
            "credits_required": current_required,
            "credits_earned": earned_credits,
            "credits_remaining": current_remaining,
            "progress_percent": current_progress,
        },
        "what_if_program": {
            "id": program_id,
            "name": target_program["name"],
            "degree_type": target_program["degree_type"],
            "credits_required": target_required,
            "credits_earned": earned_credits,
            "credits_remaining": target_remaining,
            "progress_percent": target_progress,
        },
        "completed_courses": [dict(r) for r in completed],
        "gpa": record["gpa"],
        "simulation_date": _now_iso(),
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

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        return err("Student record not found")

    old_standing = row["academic_standing"]
    now = _now_iso()
    sql, upd_params = dynamic_update("educlaw_student",
        {"academic_standing": academic_standing, "updated_at": now},
        {"student_id": student_id})
    conn.execute(sql, upd_params)
    audit(conn, SKILL, "highered-update-academic-standing", "educlaw_student", row["id"],
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
    sql, _ = insert_row("highered_hold", {
        "id": P(), "student_id": P(), "hold_type": P(), "reason": P(),
        "placed_by": P(), "placed_date": P(), "removed_date": P(),
        "hold_status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (hold_id, student_id, hold_type, reason, placed_by, now,
          "", "active", company_id, now))
    conn.commit()
    ok({"id": hold_id, "student_id": student_id,
        "hold_type": hold_type, "hold_status": "active"})


def remove_hold(conn, args):
    hold_id = getattr(args, "id", None)
    if not hold_id:
        return err("--id is required")
    row = conn.execute(Q.from_(Table("highered_hold")).select(Table("highered_hold").star).where(Field("id") == P()).get_sql(), (hold_id,)).fetchone()
    if not row:
        return err("Hold not found")
    if row["hold_status"] != "active":
        return err("Hold is already removed")

    now = _now_iso()
    sql, upd_params = dynamic_update("highered_hold",
        {"hold_status": "removed", "removed_date": now}, {"id": hold_id})
    conn.execute(sql, upd_params)
    conn.commit()
    ok({"id": hold_id, "hold_status": "removed"})


def list_holds(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t = Table("highered_hold")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    student_id = getattr(args, "student_id", None)
    if student_id:
        q = q.where(t.student_id == P())
        params.append(student_id)
    hold_status = getattr(args, "hold_status", None)
    if hold_status:
        q = q.where(t.hold_status == P())
        params.append(hold_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([limit, offset])
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"holds": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Reports
# ===========================================================================

def academic_standing_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t = Table("educlaw_student")
    rows = conn.execute(
        Q.from_(t).select(t.academic_standing, fn.Count(t.star).as_("count"))
        .where(t.company_id == P()).groupby(t.academic_standing)
        .orderby(Field("count"), order=Order.desc).get_sql(),
        (company_id,)
    ).fetchall()
    total = sum(r["count"] for r in rows)
    ok({"standings": [dict(r) for r in rows], "total_students": total})


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-generate-transcript": generate_transcript,
    "highered-calculate-gpa": calculate_gpa,
    "highered-degree-audit": degree_audit,
    "highered-transfer-credit-eval": transfer_credit_eval,
    "highered-what-if-audit": what_if_audit,
    "highered-update-academic-standing": update_academic_standing,
    "highered-add-hold": add_hold,
    "highered-remove-hold": remove_hold,
    "highered-list-holds": list_holds,
    "highered-get-student-record": get_student_record,
    "highered-list-student-records": list_student_records,
    "highered-academic-standing-report": academic_standing_report,
}
