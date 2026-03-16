"""EduClaw — academics domain module

Actions for the academics domain: academic years, terms, rooms,
programs, courses, sections, and institutional calendar.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.naming import get_next_name
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, LiteralValue
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_TERM_TYPES = ("semester", "quarter", "trimester", "summer", "custom")
VALID_TERM_STATUSES = ("setup", "enrollment_open", "active", "grades_open", "grades_finalized", "closed")
VALID_ROOM_TYPES = ("classroom", "lab", "auditorium", "gym", "library", "office")
VALID_PROGRAM_TYPES = ("k12", "associate", "bachelor", "master", "doctoral", "certificate", "diploma")
VALID_COURSE_TYPES = ("lecture", "lab", "seminar", "independent_study", "internship", "online")
VALID_SECTION_STATUSES = ("draft", "scheduled", "open", "closed", "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _validate_json_field(value, field_name):
    """Return parsed JSON list/dict or raise err."""
    if value is None:
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, (list, dict)):
            err(f"{field_name} must be a JSON array or object")
        return parsed
    except (json.JSONDecodeError, TypeError):
        err(f"{field_name} must be valid JSON")


def _times_overlap(start1, end1, start2, end2):
    """Return True if two time ranges overlap."""
    if not start1 or not end1 or not start2 or not end2:
        return False
    return start1 < end2 and end1 > start2


def _days_overlap(days1_json, days2_json):
    """Return True if two day-of-week JSON arrays share any day."""
    try:
        d1 = set(json.loads(days1_json) if isinstance(days1_json, str) else (days1_json or []))
        d2 = set(json.loads(days2_json) if isinstance(days2_json, str) else (days2_json or []))
        return bool(d1 & d2)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ACADEMIC YEAR
# ─────────────────────────────────────────────────────────────────────────────

def add_academic_year(conn, args):
    name = getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)
    start_date = getattr(args, "start_date", None)
    end_date = getattr(args, "end_date", None)

    if not name:
        err("--name is required")
    if not company_id:
        err("--company-id is required")
    if not start_date:
        err("--start-date is required")
    if not end_date:
        err("--end-date is required")
    if start_date >= end_date:
        err("start_date must be before end_date")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    # Check date overlap with existing years
    _ay = Table("educlaw_academic_year")
    existing = conn.execute(
        Q.from_(_ay).select(_ay.id, _ay.name)
        .where(_ay.company_id == P())
        .where(LiteralValue('NOT ("end_date"<=? OR "start_date">=?)'))
        .get_sql(),
        (company_id, start_date, end_date)
    ).fetchone()
    if existing:
        err(f"Dates overlap with existing academic year '{existing['name']}'")

    year_id = str(uuid.uuid4())
    is_active = int(getattr(args, "is_active", None) or 1)
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_academic_year", {"id": P(), "name": P(), "start_date": P(), "end_date": P(), "is_active": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (year_id, name, start_date, end_date, is_active, company_id, now, now,
             getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Academic year creation failed: {e}")

    audit(conn, SKILL, "edu-add-academic-year", "educlaw_academic_year", year_id,
          new_values={"name": name, "start_date": start_date, "end_date": end_date})
    conn.commit()
    ok({"id": year_id, "name": name, "start_date": start_date, "end_date": end_date})


def update_academic_year(conn, args):
    year_id = getattr(args, "year_id", None)
    if not year_id:
        err("--year-id is required")

    row = conn.execute(Q.from_(Table("educlaw_academic_year")).select(Table("educlaw_academic_year").star).where(Field("id") == P()).get_sql(), (year_id,)).fetchone()
    if not row:
        err(f"Academic year {year_id} not found")

    r = dict(row)
    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "start_date", None) is not None:
        updates.append("start_date = ?"); params.append(args.start_date); changed.append("start_date")
    if getattr(args, "end_date", None) is not None:
        updates.append("end_date = ?"); params.append(args.end_date); changed.append("end_date")
    if getattr(args, "is_active", None) is not None:
        updates.append("is_active = ?"); params.append(int(args.is_active)); changed.append("is_active")

    if not changed:
        err("No fields to update")

    start = getattr(args, "start_date", None) or r["start_date"]
    end = getattr(args, "end_date", None) or r["end_date"]
    if start >= end:
        err("start_date must be before end_date")

    updates.append("updated_at = datetime('now')")
    params.append(year_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_academic_year SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-academic-year", "educlaw_academic_year", year_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": year_id, "updated_fields": changed})


def get_academic_year(conn, args):
    year_id = getattr(args, "year_id", None)
    if not year_id:
        err("--year-id is required")

    row = conn.execute(Q.from_(Table("educlaw_academic_year")).select(Table("educlaw_academic_year").star).where(Field("id") == P()).get_sql(), (year_id,)).fetchone()
    if not row:
        err(f"Academic year {year_id} not found")

    data = dict(row)
    _at = Table("educlaw_academic_term")
    terms = conn.execute(
        Q.from_(_at).select(_at.star).where(_at.academic_year_id == P())
        .orderby(_at.start_date).get_sql(),
        (year_id,)
    ).fetchall()
    data["terms"] = [dict(t) for t in terms]
    ok(data)


def list_academic_years(conn, args):
    _ay = Table("educlaw_academic_year")
    q = Q.from_(_ay).select(_ay.star)
    params = []

    company_id = getattr(args, "company_id", None)
    if company_id:
        q = q.where(_ay.company_id == P()); params.append(company_id)

    is_active = getattr(args, "is_active", None)
    if is_active is not None:
        q = q.where(_ay.is_active == P()); params.append(int(is_active))

    q = q.orderby(_ay.start_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"academic_years": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACADEMIC TERM
# ─────────────────────────────────────────────────────────────────────────────

def add_academic_term(conn, args):
    name = getattr(args, "name", None)
    term_type = getattr(args, "term_type", None)
    academic_year_id = getattr(args, "academic_year_id", None)
    start_date = getattr(args, "start_date", None)
    end_date = getattr(args, "end_date", None)
    company_id = getattr(args, "company_id", None)

    if not name:
        err("--name is required")
    if not term_type:
        err("--term-type is required")
    if term_type not in VALID_TERM_TYPES:
        err(f"--term-type must be one of: {', '.join(VALID_TERM_TYPES)}")
    if not academic_year_id:
        err("--academic-year-id is required")
    if not start_date:
        err("--start-date is required")
    if not end_date:
        err("--end-date is required")
    if not company_id:
        err("--company-id is required")
    if start_date >= end_date:
        err("start_date must be before end_date")

    year_row = conn.execute(Q.from_(Table("educlaw_academic_year")).select(Table("educlaw_academic_year").star).where(Field("id") == P()).get_sql(), (academic_year_id,)).fetchone()
    if not year_row:
        err(f"Academic year {academic_year_id} not found")

    year = dict(year_row)
    if start_date < year["start_date"] or end_date > year["end_date"]:
        err(f"Term dates must fall within academic year ({year['start_date']} to {year['end_date']})")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    term_id = str(uuid.uuid4())
    enrollment_start = getattr(args, "enrollment_start_date", None) or ""
    enrollment_end = getattr(args, "enrollment_end_date", None) or ""
    grade_deadline = getattr(args, "grade_submission_deadline", None) or ""
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_academic_term", {"id": P(), "name": P(), "term_type": P(), "academic_year_id": P(), "start_date": P(), "end_date": P(), "enrollment_start_date": P(), "enrollment_end_date": P(), "grade_submission_deadline": P(), "status": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (term_id, name, term_type, academic_year_id, start_date, end_date,
             enrollment_start, enrollment_end, grade_deadline,
             "setup", company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Academic term creation failed: {e}")

    audit(conn, SKILL, "edu-add-academic-term", "educlaw_academic_term", term_id,
          new_values={"name": name, "term_type": term_type, "academic_year_id": academic_year_id})
    conn.commit()
    ok({"id": term_id, "name": name, "term_type": term_type, "academic_year_id": academic_year_id,
        "start_date": start_date, "end_date": end_date})


def update_academic_term(conn, args):
    term_id = getattr(args, "term_id", None)
    if not term_id:
        err("--term-id is required")

    row = conn.execute(Q.from_(Table("educlaw_academic_term")).select(Table("educlaw_academic_term").star).where(Field("id") == P()).get_sql(), (term_id,)).fetchone()
    if not row:
        err(f"Academic term {term_id} not found")

    r = dict(row)
    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "term_type", None) is not None:
        if args.term_type not in VALID_TERM_TYPES:
            err(f"--term-type must be one of: {', '.join(VALID_TERM_TYPES)}")
        updates.append("term_type = ?"); params.append(args.term_type); changed.append("term_type")
    if getattr(args, "start_date", None) is not None:
        updates.append("start_date = ?"); params.append(args.start_date); changed.append("start_date")
    if getattr(args, "end_date", None) is not None:
        updates.append("end_date = ?"); params.append(args.end_date); changed.append("end_date")
    if getattr(args, "enrollment_start_date", None) is not None:
        updates.append("enrollment_start_date = ?"); params.append(args.enrollment_start_date)
        changed.append("enrollment_start_date")
    if getattr(args, "enrollment_end_date", None) is not None:
        updates.append("enrollment_end_date = ?"); params.append(args.enrollment_end_date)
        changed.append("enrollment_end_date")
    if getattr(args, "grade_submission_deadline", None) is not None:
        updates.append("grade_submission_deadline = ?"); params.append(args.grade_submission_deadline)
        changed.append("grade_submission_deadline")
    if getattr(args, "term_status", None) is not None:
        new_status = args.term_status
        if new_status not in VALID_TERM_STATUSES:
            err(f"--term-status must be one of: {', '.join(VALID_TERM_STATUSES)}")
        updates.append("status = ?"); params.append(new_status); changed.append("status")

    if not changed:
        err("No fields to update")

    start = getattr(args, "start_date", None) or r["start_date"]
    end = getattr(args, "end_date", None) or r["end_date"]
    if start >= end:
        err("start_date must be before end_date")

    updates.append("updated_at = datetime('now')")
    params.append(term_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_academic_term SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-academic-term", "educlaw_academic_term", term_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": term_id, "updated_fields": changed})


def get_academic_term(conn, args):
    term_id = getattr(args, "term_id", None)
    if not term_id:
        err("--term-id is required")

    row = conn.execute(Q.from_(Table("educlaw_academic_term")).select(Table("educlaw_academic_term").star).where(Field("id") == P()).get_sql(), (term_id,)).fetchone()
    if not row:
        err(f"Academic term {term_id} not found")

    data = dict(row)
    _sec = Table("educlaw_section")
    section_count = conn.execute(
        Q.from_(_sec).select(fn.Count(_sec.star))
        .where(_sec.academic_term_id == P()).where(_sec.status != 'cancelled')
        .get_sql(),
        (term_id,)
    ).fetchone()[0]
    data["section_count"] = section_count
    ok(data)


def list_academic_terms(conn, args):
    _at = Table("educlaw_academic_term")
    q = Q.from_(_at).select(_at.star)
    params = []

    if getattr(args, "academic_year_id", None):
        q = q.where(_at.academic_year_id == P()); params.append(args.academic_year_id)
    if getattr(args, "term_status", None):
        q = q.where(_at.status == P()); params.append(args.term_status)
    if getattr(args, "company_id", None):
        q = q.where(_at.company_id == P()); params.append(args.company_id)

    q = q.orderby(_at.start_date)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"academic_terms": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ROOM
# ─────────────────────────────────────────────────────────────────────────────

def add_room(conn, args):
    room_number = getattr(args, "room_number", None)
    company_id = getattr(args, "company_id", None)
    capacity = getattr(args, "capacity", None)

    if not room_number:
        err("--room-number is required")
    if not company_id:
        err("--company-id is required")
    if not capacity:
        err("--capacity is required")
    if int(capacity) <= 0:
        err("--capacity must be greater than 0")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    building = getattr(args, "building", None) or ""
    room_type = getattr(args, "room_type", None) or "classroom"
    if room_type not in VALID_ROOM_TYPES:
        err(f"--room-type must be one of: {', '.join(VALID_ROOM_TYPES)}")

    facilities_raw = getattr(args, "facilities", None)
    facilities = "[]"
    if facilities_raw:
        _validate_json_field(facilities_raw, "--facilities")
        facilities = facilities_raw

    room_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_room", {"id": P(), "room_number": P(), "building": P(), "capacity": P(), "room_type": P(), "facilities": P(), "is_active": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (room_id, room_number, building, int(capacity), room_type, facilities, 1,
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Room already exists: {e}")

    audit(conn, SKILL, "edu-add-room", "educlaw_room", room_id,
          new_values={"room_number": room_number, "building": building})
    conn.commit()
    ok({"id": room_id, "room_number": room_number, "building": building, "capacity": int(capacity)})


def update_room(conn, args):
    room_id = getattr(args, "room_id", None)
    if not room_id:
        err("--room-id is required")

    row = conn.execute(Q.from_(Table("educlaw_room")).select(Table("educlaw_room").star).where(Field("id") == P()).get_sql(), (room_id,)).fetchone()
    if not row:
        err(f"Room {room_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "room_number", None) is not None:
        updates.append("room_number = ?"); params.append(args.room_number); changed.append("room_number")
    if getattr(args, "building", None) is not None:
        updates.append("building = ?"); params.append(args.building); changed.append("building")
    if getattr(args, "capacity", None) is not None:
        if int(args.capacity) <= 0:
            err("--capacity must be greater than 0")
        updates.append("capacity = ?"); params.append(int(args.capacity)); changed.append("capacity")
    if getattr(args, "room_type", None) is not None:
        if args.room_type not in VALID_ROOM_TYPES:
            err(f"--room-type must be one of: {', '.join(VALID_ROOM_TYPES)}")
        updates.append("room_type = ?"); params.append(args.room_type); changed.append("room_type")
    if getattr(args, "facilities", None) is not None:
        _validate_json_field(args.facilities, "--facilities")
        updates.append("facilities = ?"); params.append(args.facilities); changed.append("facilities")
    if getattr(args, "is_active", None) is not None:
        updates.append("is_active = ?"); params.append(int(args.is_active)); changed.append("is_active")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(room_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_room SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-room", "educlaw_room", room_id, new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": room_id, "updated_fields": changed})


def list_rooms(conn, args):
    _rm = Table("educlaw_room")
    q = Q.from_(_rm).select(_rm.star)
    params = []

    if getattr(args, "room_type", None):
        q = q.where(_rm.room_type == P()); params.append(args.room_type)
    if getattr(args, "building", None):
        q = q.where(_rm.building == P()); params.append(args.building)
    if getattr(args, "is_active", None) is not None:
        q = q.where(_rm.is_active == P()); params.append(int(args.is_active))
    if getattr(args, "company_id", None):
        q = q.where(_rm.company_id == P()); params.append(args.company_id)

    q = q.orderby(_rm.building).orderby(_rm.room_number)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["facilities"] = _validate_json_field(d.get("facilities"), "facilities")
        result.append(d)
    ok({"rooms": result, "count": len(result)})


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAM
# ─────────────────────────────────────────────────────────────────────────────

def add_program(conn, args):
    code = getattr(args, "code", None)
    name = getattr(args, "name", None)
    program_type = getattr(args, "program_type", None)
    company_id = getattr(args, "company_id", None)

    if not code:
        err("--code is required")
    if not name:
        err("--name is required")
    if not program_type:
        err("--program-type is required")
    if program_type not in VALID_PROGRAM_TYPES:
        err(f"--program-type must be one of: {', '.join(VALID_PROGRAM_TYPES)}")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    dept_id = getattr(args, "department_id", None)
    if dept_id:
        if not conn.execute(Q.from_(Table("department")).select(Field("id")).where(Field("id") == P()).get_sql(), (dept_id,)).fetchone():
            err(f"Department {dept_id} not found")

    credits_required = str(to_decimal(getattr(args, "total_credits_required", None) or "0"))
    duration = int(getattr(args, "duration_years", None) or 0)

    prog_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_program", {"id": P(), "code": P(), "name": P(), "description": P(), "program_type": P(), "department_id": P(), "total_credits_required": P(), "duration_years": P(), "is_active": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (prog_id, code, name, getattr(args, "description", None) or "", program_type,
             dept_id, credits_required, duration, 1, company_id, now, now,
             getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Program code '{code}' already exists for this company")

    audit(conn, SKILL, "edu-add-program", "educlaw_program", prog_id,
          new_values={"code": code, "name": name, "program_type": program_type})
    conn.commit()
    ok({"id": prog_id, "code": code, "name": name, "program_type": program_type})


def update_program(conn, args):
    program_id = getattr(args, "program_id", None)
    if not program_id:
        err("--program-id is required")

    row = conn.execute(Q.from_(Table("educlaw_program")).select(Table("educlaw_program").star).where(Field("id") == P()).get_sql(), (program_id,)).fetchone()
    if not row:
        err(f"Program {program_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "description", None) is not None:
        updates.append("description = ?"); params.append(args.description); changed.append("description")
    if getattr(args, "program_type", None) is not None:
        if args.program_type not in VALID_PROGRAM_TYPES:
            err(f"--program-type must be one of: {', '.join(VALID_PROGRAM_TYPES)}")
        updates.append("program_type = ?"); params.append(args.program_type); changed.append("program_type")
    if getattr(args, "department_id", None) is not None:
        if not conn.execute(Q.from_(Table("department")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.department_id,)).fetchone():
            err(f"Department {args.department_id} not found")
        updates.append("department_id = ?"); params.append(args.department_id); changed.append("department_id")
    if getattr(args, "total_credits_required", None) is not None:
        updates.append("total_credits_required = ?")
        params.append(str(to_decimal(args.total_credits_required))); changed.append("total_credits_required")
    if getattr(args, "duration_years", None) is not None:
        updates.append("duration_years = ?"); params.append(int(args.duration_years)); changed.append("duration_years")
    if getattr(args, "is_active", None) is not None:
        updates.append("is_active = ?"); params.append(int(args.is_active)); changed.append("is_active")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(program_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_program SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-program", "educlaw_program", program_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": program_id, "updated_fields": changed})


def get_program(conn, args):
    program_id = getattr(args, "program_id", None)
    if not program_id:
        err("--program-id is required")

    row = conn.execute(Q.from_(Table("educlaw_program")).select(Table("educlaw_program").star).where(Field("id") == P()).get_sql(), (program_id,)).fetchone()
    if not row:
        err(f"Program {program_id} not found")

    data = dict(row)
    # Requirements with course info
    _pr = Table("educlaw_program_requirement")
    _c = Table("educlaw_course")
    reqs = conn.execute(
        Q.from_(_pr).join(_c).on(_c.id == _pr.course_id)
        .select(_pr.star, _c.course_code, _c.name.as_("course_name"), _c.credit_hours)
        .where(_pr.program_id == P())
        .get_sql(),
        (program_id,)
    ).fetchall()
    data["requirements"] = [dict(r) for r in reqs]
    ok(data)


def list_programs(conn, args):
    _p = Table("educlaw_program")
    q = Q.from_(_p).select(_p.star)
    params = []

    if getattr(args, "program_type", None):
        q = q.where(_p.program_type == P()); params.append(args.program_type)
    if getattr(args, "department_id", None):
        q = q.where(_p.department_id == P()); params.append(args.department_id)
    if getattr(args, "is_active", None) is not None:
        q = q.where(_p.is_active == P()); params.append(int(args.is_active))
    if getattr(args, "company_id", None):
        q = q.where(_p.company_id == P()); params.append(args.company_id)

    q = q.orderby(_p.name)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"programs": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# COURSE
# ─────────────────────────────────────────────────────────────────────────────

def add_course(conn, args):
    course_code = getattr(args, "course_code", None)
    name = getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)
    credit_hours = getattr(args, "credit_hours", None)

    if not course_code:
        err("--course-code is required")
    if not name:
        err("--name is required")
    if not company_id:
        err("--company-id is required")
    if not credit_hours:
        err("--credit-hours is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    dept_id = getattr(args, "department_id", None)
    if dept_id:
        if not conn.execute(Q.from_(Table("department")).select(Field("id")).where(Field("id") == P()).get_sql(), (dept_id,)).fetchone():
            err(f"Department {dept_id} not found")

    course_type = getattr(args, "course_type", None) or "lecture"
    if course_type not in VALID_COURSE_TYPES:
        err(f"--course-type must be one of: {', '.join(VALID_COURSE_TYPES)}")

    credit_val = str(to_decimal(credit_hours))
    max_enrollment = int(getattr(args, "max_enrollment", None) or 0)

    course_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_course", {"id": P(), "course_code": P(), "name": P(), "description": P(), "credit_hours": P(), "department_id": P(), "course_type": P(), "grade_level": P(), "max_enrollment": P(), "is_active": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (course_id, course_code, name, getattr(args, "description", None) or "",
             credit_val, dept_id, course_type, getattr(args, "grade_level", None) or "",
             max_enrollment, 1, company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Course code '{course_code}' already exists for this company")

    # Optional prerequisites
    prereqs_json = getattr(args, "prerequisites", None)
    if prereqs_json:
        prereqs = _validate_json_field(prereqs_json, "--prerequisites")
        if isinstance(prereqs, list):
            for prereq in prereqs:
                prereq_course_id = prereq.get("course_id") if isinstance(prereq, dict) else prereq
                if prereq_course_id == course_id:
                    err("Course cannot be its own prerequisite")
                if not conn.execute(Q.from_(Table("educlaw_course")).select(Field("id")).where(Field("id") == P()).get_sql(), (prereq_course_id,)).fetchone():
                    err(f"Prerequisite course {prereq_course_id} not found")
                prereq_id = str(uuid.uuid4())
                conn.execute(  # PyPika: skipped — INSERT OR IGNORE not supported by PyPika
                    """INSERT OR IGNORE INTO educlaw_course_prerequisite
                       (id, course_id, prerequisite_course_id, min_grade, is_corequisite, created_at, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (prereq_id, course_id, prereq_course_id,
                     prereq.get("min_grade", "") if isinstance(prereq, dict) else "",
                     int(prereq.get("is_corequisite", 0)) if isinstance(prereq, dict) else 0,
                     now, getattr(args, "user_id", None) or "")
                )

    audit(conn, SKILL, "edu-add-course", "educlaw_course", course_id,
          new_values={"course_code": course_code, "name": name})
    conn.commit()
    ok({"id": course_id, "course_code": course_code, "name": name, "credit_hours": credit_val})


def update_course(conn, args):
    course_id = getattr(args, "course_id", None)
    if not course_id:
        err("--course-id is required")

    row = conn.execute(Q.from_(Table("educlaw_course")).select(Table("educlaw_course").star).where(Field("id") == P()).get_sql(), (course_id,)).fetchone()
    if not row:
        err(f"Course {course_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "description", None) is not None:
        updates.append("description = ?"); params.append(args.description); changed.append("description")
    if getattr(args, "credit_hours", None) is not None:
        updates.append("credit_hours = ?")
        params.append(str(to_decimal(args.credit_hours))); changed.append("credit_hours")
    if getattr(args, "course_type", None) is not None:
        if args.course_type not in VALID_COURSE_TYPES:
            err(f"--course-type must be one of: {', '.join(VALID_COURSE_TYPES)}")
        updates.append("course_type = ?"); params.append(args.course_type); changed.append("course_type")
    if getattr(args, "grade_level", None) is not None:
        updates.append("grade_level = ?"); params.append(args.grade_level); changed.append("grade_level")
    if getattr(args, "max_enrollment", None) is not None:
        updates.append("max_enrollment = ?"); params.append(int(args.max_enrollment)); changed.append("max_enrollment")
    if getattr(args, "is_active", None) is not None:
        updates.append("is_active = ?"); params.append(int(args.is_active)); changed.append("is_active")
    if getattr(args, "department_id", None) is not None:
        if not conn.execute(Q.from_(Table("department")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.department_id,)).fetchone():
            err(f"Department {args.department_id} not found")
        updates.append("department_id = ?"); params.append(args.department_id); changed.append("department_id")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(course_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_course SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-course", "educlaw_course", course_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": course_id, "updated_fields": changed})


def get_course(conn, args):
    course_id = getattr(args, "course_id", None)
    if not course_id:
        err("--course-id is required")

    row = conn.execute(Q.from_(Table("educlaw_course")).select(Table("educlaw_course").star).where(Field("id") == P()).get_sql(), (course_id,)).fetchone()
    if not row:
        err(f"Course {course_id} not found")

    data = dict(row)

    _cp = Table("educlaw_course_prerequisite")
    _c2 = Table("educlaw_course")
    prereqs = conn.execute(
        Q.from_(_cp).join(_c2).on(_c2.id == _cp.prerequisite_course_id)
        .select(_cp.star, _c2.course_code, _c2.name.as_("prereq_name"))
        .where(_cp.course_id == P())
        .get_sql(),
        (course_id,)
    ).fetchall()
    data["prerequisites"] = [dict(p) for p in prereqs]

    _sec = Table("educlaw_section")
    _at = Table("educlaw_academic_term")
    sections = conn.execute(
        Q.from_(_sec).join(_at).on(_at.id == _sec.academic_term_id)
        .select(_sec.star, _at.name.as_("term_name"))
        .where(_sec.course_id == P()).where(_sec.status != 'cancelled')
        .orderby(_at.start_date, order=Order.desc)
        .get_sql(),
        (course_id,)
    ).fetchall()
    data["sections"] = [dict(s) for s in sections]
    ok(data)


def list_courses(conn, args):
    _c = Table("educlaw_course")
    q = Q.from_(_c).select(_c.star)
    params = []

    if getattr(args, "department_id", None):
        q = q.where(_c.department_id == P()); params.append(args.department_id)
    if getattr(args, "grade_level", None):
        q = q.where(_c.grade_level == P()); params.append(args.grade_level)
    if getattr(args, "course_type", None):
        q = q.where(_c.course_type == P()); params.append(args.course_type)
    if getattr(args, "is_active", None) is not None:
        q = q.where(_c.is_active == P()); params.append(int(args.is_active))
    if getattr(args, "company_id", None):
        q = q.where(_c.company_id == P()); params.append(args.company_id)

    q = q.orderby(_c.course_code)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"courses": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# SECTION
# ─────────────────────────────────────────────────────────────────────────────

def _check_section_conflicts(conn, academic_term_id, instructor_id, room_id,
                              days_of_week, start_time, end_time, exclude_section_id=None):
    """Validate no instructor or room conflicts. Returns error message or None."""
    if not start_time or not end_time or not days_of_week:
        return None

    # Get all sections in same term with schedule info
    _sec = Table("educlaw_section")
    _q = Q.from_(_sec).select(
        _sec.id, _sec.instructor_id, _sec.room_id, _sec.days_of_week,
        _sec.start_time, _sec.end_time
    ).where(_sec.academic_term_id == P()).where(_sec.status != 'cancelled')
    params = [academic_term_id]
    if exclude_section_id:
        _q = _q.where(_sec.id != P())
        params.append(exclude_section_id)

    existing = conn.execute(_q.get_sql(), params).fetchall()
    for s in existing:
        s = dict(s)
        if not _times_overlap(start_time, end_time, s["start_time"], s["end_time"]):
            continue
        if not _days_overlap(days_of_week, s["days_of_week"]):
            continue
        # Time + day overlap → check instructor and room
        if instructor_id and s["instructor_id"] == instructor_id:
            return f"Instructor has a conflicting section at this time"
        if room_id and s["room_id"] == room_id:
            return f"Room is already booked at this time"
    return None


def add_section(conn, args):
    course_id = getattr(args, "course_id", None)
    academic_term_id = getattr(args, "academic_term_id", None)
    section_number = getattr(args, "section_number", None)
    company_id = getattr(args, "company_id", None)
    max_enrollment = getattr(args, "max_enrollment", None)

    if not course_id:
        err("--course-id is required")
    if not academic_term_id:
        err("--academic-term-id is required")
    if not section_number:
        err("--section-number is required")
    if not company_id:
        err("--company-id is required")
    if not max_enrollment:
        err("--max-enrollment is required")
    if int(max_enrollment) <= 0:
        err("--max-enrollment must be greater than 0")

    if not conn.execute(Q.from_(Table("educlaw_course")).select(Field("id")).where(Field("id") == P()).get_sql(), (course_id,)).fetchone():
        err(f"Course {course_id} not found")
    if not conn.execute(Q.from_(Table("educlaw_academic_term")).select(Field("id")).where(Field("id") == P()).get_sql(), (academic_term_id,)).fetchone():
        err(f"Academic term {academic_term_id} not found")
    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    instructor_id = getattr(args, "instructor_id", None)
    if instructor_id:
        if not conn.execute(Q.from_(Table("educlaw_instructor")).select(Field("id")).where(Field("id") == P()).get_sql(), (instructor_id,)).fetchone():
            err(f"Instructor {instructor_id} not found")

    room_id = getattr(args, "room_id", None)
    if room_id:
        room_row = conn.execute(Q.from_(Table("educlaw_room")).select(Table("educlaw_room").star).where(Field("id") == P()).get_sql(), (room_id,)).fetchone()
        if not room_row:
            err(f"Room {room_id} not found")
        # Validate room capacity >= max_enrollment
        if dict(room_row)["capacity"] < int(max_enrollment):
            err(f"Room capacity ({dict(room_row)['capacity']}) is less than max_enrollment ({max_enrollment})")

    days_of_week = getattr(args, "days_of_week", None) or "[]"
    start_time = getattr(args, "start_time", None) or ""
    end_time = getattr(args, "end_time", None) or ""

    # Validate no conflicts
    conflict = _check_section_conflicts(conn, academic_term_id, instructor_id, room_id,
                                        days_of_week, start_time, end_time)
    if conflict:
        err(conflict)

    # Generate naming series
    section_series = get_next_name(conn, "educlaw_section", company_id=company_id)

    section_id = str(uuid.uuid4())
    waitlist_enabled = int(getattr(args, "waitlist_enabled", None) or 0)
    waitlist_max = int(getattr(args, "waitlist_max", None) or 0)
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_section", {"id": P(), "naming_series": P(), "section_number": P(), "course_id": P(), "academic_term_id": P(), "instructor_id": P(), "room_id": P(), "days_of_week": P(), "start_time": P(), "end_time": P(), "max_enrollment": P(), "current_enrollment": P(), "waitlist_enabled": P(), "waitlist_max": P(), "status": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (section_id, section_series, section_number, course_id, academic_term_id,
             instructor_id, room_id, days_of_week, start_time, end_time,
             int(max_enrollment), 0, waitlist_enabled, waitlist_max,
             "draft", company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Section creation failed: {e}")

    audit(conn, SKILL, "edu-add-section", "educlaw_section", section_id,
          new_values={"naming_series": section_series, "course_id": course_id,
                      "academic_term_id": academic_term_id})
    conn.commit()
    ok({"id": section_id, "naming_series": section_series, "section_number": section_number,
        "course_id": course_id, "academic_term_id": academic_term_id})


def update_section(conn, args):
    section_id = getattr(args, "section_id", None)
    if not section_id:
        err("--section-id is required")

    row = conn.execute(Q.from_(Table("educlaw_section")).select(Table("educlaw_section").star).where(Field("id") == P()).get_sql(), (section_id,)).fetchone()
    if not row:
        err(f"Section {section_id} not found")

    r = dict(row)
    if r["status"] in ("cancelled",):
        err("Cannot update a cancelled section")

    updates, params, changed = [], [], []

    if getattr(args, "section_number", None) is not None:
        updates.append("section_number = ?"); params.append(args.section_number); changed.append("section_number")
    if getattr(args, "instructor_id", None) is not None:
        if args.instructor_id and not conn.execute(Q.from_(Table("educlaw_instructor")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.instructor_id,)).fetchone():
            err(f"Instructor {args.instructor_id} not found")
        updates.append("instructor_id = ?"); params.append(args.instructor_id); changed.append("instructor_id")
    if getattr(args, "room_id", None) is not None:
        if args.room_id:
            room_row = conn.execute(Q.from_(Table("educlaw_room")).select(Table("educlaw_room").star).where(Field("id") == P()).get_sql(), (args.room_id,)).fetchone()
            if not room_row:
                err(f"Room {args.room_id} not found")
            new_max = getattr(args, "max_enrollment", None) or r["max_enrollment"]
            if dict(room_row)["capacity"] < int(new_max):
                err(f"Room capacity is less than max_enrollment")
        updates.append("room_id = ?"); params.append(args.room_id); changed.append("room_id")
    if getattr(args, "days_of_week", None) is not None:
        updates.append("days_of_week = ?"); params.append(args.days_of_week); changed.append("days_of_week")
    if getattr(args, "start_time", None) is not None:
        updates.append("start_time = ?"); params.append(args.start_time); changed.append("start_time")
    if getattr(args, "end_time", None) is not None:
        updates.append("end_time = ?"); params.append(args.end_time); changed.append("end_time")
    if getattr(args, "max_enrollment", None) is not None:
        if int(args.max_enrollment) <= 0:
            err("--max-enrollment must be greater than 0")
        updates.append("max_enrollment = ?"); params.append(int(args.max_enrollment)); changed.append("max_enrollment")
    if getattr(args, "waitlist_enabled", None) is not None:
        updates.append("waitlist_enabled = ?"); params.append(int(args.waitlist_enabled)); changed.append("waitlist_enabled")
    if getattr(args, "waitlist_max", None) is not None:
        updates.append("waitlist_max = ?"); params.append(int(args.waitlist_max)); changed.append("waitlist_max")

    if not changed:
        err("No fields to update")

    # Re-validate conflicts after update
    new_instructor = getattr(args, "instructor_id", None) or r["instructor_id"]
    new_room = getattr(args, "room_id", None) or r["room_id"]
    new_days = getattr(args, "days_of_week", None) or r["days_of_week"]
    new_start = getattr(args, "start_time", None) or r["start_time"]
    new_end = getattr(args, "end_time", None) or r["end_time"]

    conflict = _check_section_conflicts(conn, r["academic_term_id"], new_instructor, new_room,
                                        new_days, new_start, new_end, exclude_section_id=section_id)
    if conflict:
        err(conflict)

    updates.append("updated_at = datetime('now')")
    params.append(section_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_section SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-section", "educlaw_section", section_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": section_id, "updated_fields": changed})


def get_section(conn, args):
    section_id = getattr(args, "section_id", None)
    if not section_id:
        err("--section-id is required")

    row = conn.execute(Q.from_(Table("educlaw_section")).select(Table("educlaw_section").star).where(Field("id") == P()).get_sql(), (section_id,)).fetchone()
    if not row:
        err(f"Section {section_id} not found")

    data = dict(row)
    try:
        data["days_of_week"] = json.loads(data["days_of_week"]) if data.get("days_of_week") else []
    except Exception:
        data["days_of_week"] = []

    _ce = Table("educlaw_course_enrollment")
    _st = Table("educlaw_student")
    enrollments = conn.execute(
        Q.from_(_ce).join(_st).on(_st.id == _ce.student_id)
        .select(_ce.star, _st.naming_series, _st.first_name, _st.last_name)
        .where(_ce.section_id == P())
        .where(_ce.enrollment_status.isin(['enrolled', 'waitlisted']))
        .orderby(_st.last_name).orderby(_st.first_name)
        .get_sql(),
        (section_id,)
    ).fetchall()
    data["enrolled_students"] = [dict(e) for e in enrollments]
    data["enrollment_count"] = len([e for e in data["enrolled_students"]
                                    if dict(e)["enrollment_status"] == "enrolled"])

    _ap = Table("educlaw_assessment_plan")
    plan = conn.execute(
        Q.from_(_ap).select(_ap.star).where(_ap.section_id == P()).get_sql(), (section_id,)
    ).fetchone()
    data["assessment_plan"] = dict(plan) if plan else None
    ok(data)


def list_sections(conn, args):
    _sec = Table("educlaw_section")
    q = Q.from_(_sec).select(_sec.star)
    params = []

    if getattr(args, "academic_term_id", None):
        q = q.where(_sec.academic_term_id == P()); params.append(args.academic_term_id)
    if getattr(args, "course_id", None):
        q = q.where(_sec.course_id == P()); params.append(args.course_id)
    if getattr(args, "instructor_id", None):
        q = q.where(_sec.instructor_id == P()); params.append(args.instructor_id)
    if getattr(args, "section_status", None):
        q = q.where(_sec.status == P()); params.append(args.section_status)
    if getattr(args, "company_id", None):
        q = q.where(_sec.company_id == P()); params.append(args.company_id)

    q = q.orderby(_sec.naming_series)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"sections": [dict(r) for r in rows], "count": len(rows)})


def open_section(conn, args):
    section_id = getattr(args, "section_id", None)
    if not section_id:
        err("--section-id is required")

    row = conn.execute(Q.from_(Table("educlaw_section")).select(Table("educlaw_section").star).where(Field("id") == P()).get_sql(), (section_id,)).fetchone()
    if not row:
        err(f"Section {section_id} not found")

    r = dict(row)
    current_status = r["status"]

    # open-section transitions draft or scheduled → open (enrollment opened)
    allowed_from = {"draft", "scheduled"}
    if current_status not in allowed_from:
        err(f"Cannot open section from status '{current_status}'. Must be 'draft' or 'scheduled'")

    # Validate instructor and room assigned before opening
    if not r["instructor_id"]:
        err("Instructor must be assigned before opening section")
    if not r["room_id"]:
        err("Room must be assigned before opening section")

    new_status = "open"
    _sec2 = Table("educlaw_section")
    conn.execute(
        Q.update(_sec2)
        .set(_sec2.status, P())
        .set(_sec2.updated_at, LiteralValue("datetime('now')"))
        .where(_sec2.id == P())
        .get_sql(),
        (new_status, section_id)
    )
    audit(conn, SKILL, "edu-open-section", "educlaw_section", section_id,
          new_values={"old_status": current_status, "new_status": new_status})
    conn.commit()
    ok({"id": section_id, "old_status": current_status, "section_status": new_status})


def cancel_section(conn, args):
    section_id = getattr(args, "section_id", None)
    if not section_id:
        err("--section-id is required")

    row = conn.execute(Q.from_(Table("educlaw_section")).select(Table("educlaw_section").star).where(Field("id") == P()).get_sql(), (section_id,)).fetchone()
    if not row:
        err(f"Section {section_id} not found")

    r = dict(row)
    if r["status"] == "cancelled":
        err("Section is already cancelled")

    # Drop all enrolled students
    _ce = Table("educlaw_course_enrollment")
    enrolled = conn.execute(
        Q.from_(_ce).select(_ce.id, _ce.student_id)
        .where(_ce.section_id == P()).where(_ce.enrollment_status == 'enrolled')
        .get_sql(),
        (section_id,)
    ).fetchall()

    now = _now_iso()
    dropped_count = 0
    for enr in enrolled:
        enr = dict(enr)
        _ce2 = Table("educlaw_course_enrollment")
        conn.execute(
            Q.update(_ce2)
            .set(_ce2.enrollment_status, 'dropped')
            .set(_ce2.drop_date, P())
            .set(_ce2.drop_reason, 'Section cancelled')
            .set(_ce2.updated_at, LiteralValue("datetime('now')"))
            .where(_ce2.id == P())
            .get_sql(),
            (now[:10], enr["id"])
        )
        # Create notification for each dropped student
        notif_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (notif_id, "student", enr["student_id"], "announcement",
             "Section Cancelled",
             f"Your enrollment in section {r['naming_series']} has been dropped due to section cancellation.",
             "educlaw_section", section_id, r["company_id"], now,
             getattr(args, "user_id", None) or "")
        )
        dropped_count += 1

    # Cancel waitlisted entries
    _wl = Table("educlaw_waitlist")
    conn.execute(
        Q.update(_wl)
        .set(_wl.waitlist_status, 'cancelled')
        .set(_wl.updated_at, LiteralValue("datetime('now')"))
        .where(_wl.section_id == P()).where(_wl.waitlist_status == 'waiting')
        .get_sql(),
        (section_id,)
    )

    _sec3 = Table("educlaw_section")
    conn.execute(
        Q.update(_sec3)
        .set(_sec3.status, 'cancelled')
        .set(_sec3.current_enrollment, 0)
        .set(_sec3.updated_at, LiteralValue("datetime('now')"))
        .where(_sec3.id == P())
        .get_sql(),
        (section_id,)
    )
    audit(conn, SKILL, "edu-cancel-section", "educlaw_section", section_id,
          new_values={"dropped_students": dropped_count})
    conn.commit()
    ok({"id": section_id, "section_status": "cancelled", "dropped_students": dropped_count})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-academic-year": add_academic_year,
    "edu-update-academic-year": update_academic_year,
    "edu-get-academic-year": get_academic_year,
    "edu-list-academic-years": list_academic_years,
    "edu-add-academic-term": add_academic_term,
    "edu-update-academic-term": update_academic_term,
    "edu-get-academic-term": get_academic_term,
    "edu-list-academic-terms": list_academic_terms,
    "edu-add-room": add_room,
    "edu-update-room": update_room,
    "edu-list-rooms": list_rooms,
    "edu-add-program": add_program,
    "edu-update-program": update_program,
    "edu-get-program": get_program,
    "edu-list-programs": list_programs,
    "edu-add-course": add_course,
    "edu-update-course": update_course,
    "edu-get-course": get_course,
    "edu-list-courses": list_courses,
    "edu-add-section": add_section,
    "edu-update-section": update_section,
    "edu-get-section": get_section,
    "edu-list-sections": list_sections,
    "edu-activate-section": open_section,
    "edu-cancel-section": cancel_section,
}
