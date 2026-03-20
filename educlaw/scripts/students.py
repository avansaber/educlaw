"""EduClaw — students domain module

Actions for the students domain: student applicants, students, guardians,
and FERPA compliance (data access log, consent records).

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.decimal_utils import to_decimal
    from erpclaw_lib.naming import get_next_name
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, LiteralValue
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_APPLICANT_STATUSES = (
    "applied", "under_review", "accepted", "rejected",
    "waitlisted", "pending_info", "confirmed", "enrolled"
)
VALID_STUDENT_STATUSES = (
    "active", "graduated", "withdrawn", "suspended", "expelled", "transferred", "inactive"
)
VALID_ACADEMIC_STANDINGS = ("good", "deans_list", "honor_roll", "probation", "suspension")
VALID_GENDERS = ("male", "female", "non_binary", "prefer_not_to_say", "")
VALID_RELATIONSHIPS = (
    "father", "mother", "guardian", "grandparent", "stepparent", "foster_parent", "other"
)
VALID_CONSENT_TYPES = (
    "ferpa_directory", "ferpa_disclosure", "coppa_collection", "coppa_school_consent"
)
VALID_DATA_CATEGORIES = (
    "demographics", "grades", "attendance", "financial", "health", "discipline", "communications"
)
VALID_ACCESS_TYPES = ("view", "export", "print", "api")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _is_coppa_applicable(date_of_birth_str, enrollment_date_str=None):
    """Return True if student is under 13 at enrollment."""
    try:
        dob = date.fromisoformat(date_of_birth_str)
        ref = date.fromisoformat(enrollment_date_str) if enrollment_date_str else date.today()
        age_years = (ref - dob).days / 365.25
        return age_years < 13
    except Exception:
        return False


def _log_data_access_internal(conn, user_id, student_id, data_category,
                               access_type, access_reason, is_emergency, company_id):
    """Internal helper to log FERPA data access without failing main operation."""
    log_id = str(uuid.uuid4())
    now = _now_iso()
    try:
        sql, _ = insert_row("educlaw_data_access_log", {"id": P(), "user_id": P(), "student_id": P(), "data_category": P(), "access_type": P(), "access_reason": P(), "is_emergency_access": P(), "ip_address": P(), "company_id": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (log_id, user_id, student_id, data_category, access_type,
             access_reason, int(is_emergency), "", company_id, now, user_id)
        )
    except Exception:
        pass  # Don't fail the main operation if logging fails


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT APPLICANT
# ─────────────────────────────────────────────────────────────────────────────

def add_student_applicant(conn, args):
    first_name = getattr(args, "first_name", None)
    last_name = getattr(args, "last_name", None)
    date_of_birth = getattr(args, "date_of_birth", None)
    company_id = getattr(args, "company_id", None)
    application_date = getattr(args, "application_date", None) or _now_iso()[:10]

    if not first_name:
        err("--first-name is required")
    if not last_name:
        err("--last-name is required")
    if not date_of_birth:
        err("--date-of-birth is required")
    try:
        dob = date.fromisoformat(date_of_birth)
        if dob > date.today():
            err(f"--date-of-birth cannot be in the future: {date_of_birth}")
    except (ValueError, TypeError):
        err(f"Invalid date-of-birth format: {date_of_birth}. Use YYYY-MM-DD")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    gender = getattr(args, "gender", None) or ""
    if gender and gender not in VALID_GENDERS:
        err(f"--gender must be one of: {', '.join(g for g in VALID_GENDERS if g)}")

    applying_for_program_id = getattr(args, "applying_for_program_id", None)
    if applying_for_program_id:
        if not conn.execute(Q.from_(Table("educlaw_program")).select(Field("id")).where(Field("id") == P()).get_sql(), (applying_for_program_id,)).fetchone():
            err(f"Program {applying_for_program_id} not found")

    applying_for_term_id = getattr(args, "applying_for_term_id", None)
    if applying_for_term_id:
        if not conn.execute(Q.from_(Table("educlaw_academic_term")).select(Field("id")).where(Field("id") == P()).get_sql(), (applying_for_term_id,)).fetchone():
            err(f"Academic term {applying_for_term_id} not found")

    naming = get_next_name(conn, "educlaw_student_applicant", company_id=company_id)
    applicant_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_student_applicant", {"id": P(), "naming_series": P(), "first_name": P(), "middle_name": P(), "last_name": P(), "date_of_birth": P(), "gender": P(), "email": P(), "phone": P(), "address": P(), "applying_for_program_id": P(), "applying_for_term_id": P(), "previous_school": P(), "previous_school_address": P(), "transfer_records": P(), "application_date": P(), "status": P(), "review_notes": P(), "acceptance_deadline": P(), "guardian_info": P(), "documents": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (applicant_id, naming, first_name,
             getattr(args, "middle_name", None) or "",
             last_name, date_of_birth, gender,
             getattr(args, "email", None) or "",
             getattr(args, "phone", None) or "",
             getattr(args, "address", None) or "{}",
             applying_for_program_id, applying_for_term_id,
             getattr(args, "previous_school", None) or "",
             getattr(args, "previous_school_address", None) or "",
             getattr(args, "transfer_records", None) or "",
             application_date, "applied", "", "",
             getattr(args, "guardian_info", None) or "[]",
             getattr(args, "documents", None) or "[]",
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Applicant creation failed: {e}")

    audit(conn, SKILL, "edu-add-student-applicant", "educlaw_student_applicant", applicant_id,
          new_values={"naming_series": naming, "first_name": first_name, "last_name": last_name})
    conn.commit()
    ok({"id": applicant_id, "naming_series": naming, "first_name": first_name,
        "last_name": last_name, "applicant_status": "applied"})


def update_student_applicant(conn, args):
    applicant_id = getattr(args, "applicant_id", None)
    if not applicant_id:
        err("--applicant-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student_applicant")).select(Table("educlaw_student_applicant").star).where(Field("id") == P()).get_sql(), (applicant_id,)).fetchone()
    if not row:
        err(f"Applicant {applicant_id} not found")

    r = dict(row)
    if r["status"] == "enrolled":
        err("Cannot update an enrolled applicant — student record already created")

    updates, params, changed = [], [], []

    for field in ("first_name", "middle_name", "last_name", "email", "phone",
                  "previous_school", "previous_school_address", "transfer_records",
                  "acceptance_deadline", "review_notes"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field} = ?"); params.append(val); changed.append(field)

    if getattr(args, "date_of_birth", None) is not None:
        updates.append("date_of_birth = ?"); params.append(args.date_of_birth)
        changed.append("date_of_birth")
    if getattr(args, "gender", None) is not None:
        if args.gender not in VALID_GENDERS:
            err(f"--gender must be one of: {', '.join(g for g in VALID_GENDERS if g)}")
        updates.append("gender = ?"); params.append(args.gender); changed.append("gender")
    if getattr(args, "address", None) is not None:
        updates.append("address = ?"); params.append(args.address); changed.append("address")
    if getattr(args, "guardian_info", None) is not None:
        updates.append("guardian_info = ?"); params.append(args.guardian_info)
        changed.append("guardian_info")
    if getattr(args, "documents", None) is not None:
        updates.append("documents = ?"); params.append(args.documents); changed.append("documents")
    if getattr(args, "applying_for_program_id", None) is not None:
        if not conn.execute(Q.from_(Table("educlaw_program")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.applying_for_program_id,)).fetchone():
            err(f"Program {args.applying_for_program_id} not found")
        updates.append("applying_for_program_id = ?"); params.append(args.applying_for_program_id)
        changed.append("applying_for_program_id")
    if getattr(args, "applying_for_term_id", None) is not None:
        if not conn.execute(Q.from_(Table("educlaw_academic_term")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.applying_for_term_id,)).fetchone():
            err(f"Academic term {args.applying_for_term_id} not found")
        updates.append("applying_for_term_id = ?"); params.append(args.applying_for_term_id)
        changed.append("applying_for_term_id")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(applicant_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_student_applicant SET {', '.join(updates)} WHERE id = ?", params
    )
    audit(conn, SKILL, "edu-update-student-applicant", "educlaw_student_applicant", applicant_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": applicant_id, "updated_fields": changed})


def get_applicant(conn, args):
    applicant_id = getattr(args, "applicant_id", None)
    naming_series = getattr(args, "naming_series", None)

    if not applicant_id and not naming_series:
        err("--applicant-id or --naming-series is required")

    if applicant_id:
        row = conn.execute(Q.from_(Table("educlaw_student_applicant")).select(Table("educlaw_student_applicant").star).where(Field("id") == P()).get_sql(), (applicant_id,)).fetchone()
    else:
        _sa = Table("educlaw_student_applicant")
        row = conn.execute(
            Q.from_(_sa).select(_sa.star).where(_sa.naming_series == P()).get_sql(), (naming_series,)
        ).fetchone()

    if not row:
        err("Applicant not found")

    data = dict(row)
    for field in ("address", "guardian_info", "documents"):
        try:
            if data.get(field):
                data[field] = json.loads(data[field])
        except Exception:
            pass
    ok(data)


def list_applicants(conn, args):
    _sa = Table("educlaw_student_applicant")
    q = Q.from_(_sa).select(_sa.star)
    params = []

    if getattr(args, "applicant_status", None):
        q = q.where(_sa.status == P()); params.append(args.applicant_status)
    if getattr(args, "applying_for_term_id", None):
        q = q.where(_sa.applying_for_term_id == P()); params.append(args.applying_for_term_id)
    if getattr(args, "applying_for_program_id", None):
        q = q.where(_sa.applying_for_program_id == P()); params.append(args.applying_for_program_id)
    if getattr(args, "company_id", None):
        q = q.where(_sa.company_id == P()); params.append(args.company_id)

    q = q.orderby(_sa.application_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"applicants": [dict(r) for r in rows], "count": len(rows)})


def review_applicant(conn, args):
    applicant_id = getattr(args, "applicant_id", None)
    new_status = getattr(args, "applicant_status", None)
    reviewed_by = getattr(args, "reviewed_by", None)

    if not applicant_id:
        err("--applicant-id is required")
    if not new_status:
        err("--applicant-status is required")
    if new_status not in VALID_APPLICANT_STATUSES:
        err(f"--applicant-status must be one of: {', '.join(VALID_APPLICANT_STATUSES)}")
    if not reviewed_by:
        err("--reviewed-by is required")

    row = conn.execute(Q.from_(Table("educlaw_student_applicant")).select(Table("educlaw_student_applicant").star).where(Field("id") == P()).get_sql(), (applicant_id,)).fetchone()
    if not row:
        err(f"Applicant {applicant_id} not found")

    r = dict(row)
    if r["status"] == "enrolled":
        err("Cannot review an enrolled applicant")

    now = _now_iso()
    _sa = Table("educlaw_student_applicant")
    conn.execute(
        Q.update(_sa)
        .set(_sa.status, P())
        .set(_sa.reviewed_by, P())
        .set(_sa.review_date, P())
        .set(_sa.review_notes, P())
        .set(_sa.updated_at, LiteralValue("datetime('now')"))
        .where(_sa.id == P())
        .get_sql(),
        (new_status, reviewed_by, now[:10],
         getattr(args, "review_notes", None) or r.get("review_notes", ""),
         applicant_id)
    )

    if new_status == "accepted":
        notif_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (notif_id, "student", applicant_id, "acceptance",
             "Application Accepted",
             f"Congratulations! Your application {r['naming_series']} has been accepted.",
             "educlaw_student_applicant", applicant_id, r["company_id"], now, reviewed_by)
        )

    audit(conn, SKILL, "edu-review-applicant", "educlaw_student_applicant", applicant_id,
          new_values={"old_status": r["status"], "new_status": new_status})
    conn.commit()
    ok({"id": applicant_id, "applicant_status": new_status, "reviewed_by": reviewed_by})


def convert_applicant_to_student(conn, args):
    applicant_id = getattr(args, "applicant_id", None)
    company_id = getattr(args, "company_id", None)

    if not applicant_id:
        err("--applicant-id is required")
    if not company_id:
        err("--company-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student_applicant")).select(Table("educlaw_student_applicant").star).where(Field("id") == P()).get_sql(), (applicant_id,)).fetchone()
    if not row:
        err(f"Applicant {applicant_id} not found")

    r = dict(row)
    if r["status"] not in ("accepted", "confirmed"):
        err(f"Applicant must be accepted or confirmed (current: {r['status']})")

    _stu = Table("educlaw_student")
    existing = conn.execute(
        Q.from_(_stu).select(_stu.id).where(_stu.student_applicant_id == P()).get_sql(),
        (applicant_id,)
    ).fetchone()
    if existing:
        err(f"Applicant already converted to student {existing['id']}")

    enrollment_date = getattr(args, "enrollment_date", None) or _now_iso()[:10]
    coppa = 1 if _is_coppa_applicable(r["date_of_birth"], enrollment_date) else 0

    naming = get_next_name(conn, "educlaw_student", company_id=company_id)
    student_id = str(uuid.uuid4())

    mid = r.get("middle_name", "") or ""
    full_name = f"{r['first_name']} {mid} {r['last_name']}".replace("  ", " ").strip()
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_student", {"id": P(), "naming_series": P(), "first_name": P(), "middle_name": P(), "last_name": P(), "full_name": P(), "date_of_birth": P(), "gender": P(), "email": P(), "phone": P(), "address": P(), "emergency_contact": P(), "student_applicant_id": P(), "current_program_id": P(), "grade_level": P(), "cohort_year": P(), "cumulative_gpa": P(), "total_credits_earned": P(), "academic_standing": P(), "status": P(), "registration_hold": P(), "directory_info_opt_out": P(), "is_coppa_applicable": P(), "coppa_consent_type": P(), "coppa_consent_date": P(), "enrollment_date": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (student_id, naming, r["first_name"], mid, r["last_name"],
             full_name, r["date_of_birth"], r.get("gender", ""), r.get("email", ""),
             r.get("phone", ""), r.get("address", "{}"),
             getattr(args, "emergency_contact", None) or "{}",
             applicant_id, r.get("applying_for_program_id"),
             getattr(args, "grade_level", None) or "",
             int(getattr(args, "cohort_year", None) or 0),
             "", "0", "good", "active",
             0, int(getattr(args, "directory_info_opt_out", None) or 0),
             coppa, "", "", enrollment_date,
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Student creation failed: {e}")

    _sa2 = Table("educlaw_student_applicant")
    conn.execute(
        Q.update(_sa2)
        .set(_sa2.status, 'enrolled')
        .set(_sa2.updated_at, LiteralValue("datetime('now')"))
        .where(_sa2.id == P())
        .get_sql(),
        (applicant_id,)
    )
    audit(conn, SKILL, "edu-convert-applicant-to-student", "educlaw_student", student_id,
          new_values={"naming_series": naming, "applicant_id": applicant_id})
    conn.commit()
    ok({"id": student_id, "naming_series": naming, "full_name": full_name,
        "applicant_id": applicant_id, "is_coppa_applicable": coppa})


def add_student(conn, args):
    first_name = getattr(args, "first_name", None)
    last_name = getattr(args, "last_name", None)
    date_of_birth = getattr(args, "date_of_birth", None)
    company_id = getattr(args, "company_id", None)

    if not first_name:
        err("--first-name is required")
    if not last_name:
        err("--last-name is required")
    if not date_of_birth:
        err("--date-of-birth is required")
    try:
        dob = date.fromisoformat(date_of_birth)
        if dob > date.today():
            err(f"--date-of-birth cannot be in the future: {date_of_birth}")
    except (ValueError, TypeError):
        err(f"Invalid date-of-birth format: {date_of_birth}. Use YYYY-MM-DD")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    gender = getattr(args, "gender", None) or ""
    if gender and gender not in VALID_GENDERS:
        err(f"--gender must be one of: {', '.join(g for g in VALID_GENDERS if g)}")

    current_program_id = getattr(args, "current_program_id", None)
    if current_program_id:
        if not conn.execute(Q.from_(Table("educlaw_program")).select(Field("id")).where(Field("id") == P()).get_sql(), (current_program_id,)).fetchone():
            err(f"Program {current_program_id} not found")

    enrollment_date = getattr(args, "enrollment_date", None) or _now_iso()[:10]
    coppa = 1 if _is_coppa_applicable(date_of_birth, enrollment_date) else 0

    naming = get_next_name(conn, "educlaw_student", company_id=company_id)
    student_id = str(uuid.uuid4())

    middle_name = getattr(args, "middle_name", None) or ""
    full_name = f"{first_name} {middle_name} {last_name}".replace("  ", " ").strip()
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_student", {"id": P(), "naming_series": P(), "first_name": P(), "middle_name": P(), "last_name": P(), "full_name": P(), "date_of_birth": P(), "gender": P(), "email": P(), "phone": P(), "address": P(), "emergency_contact": P(), "student_applicant_id": P(), "current_program_id": P(), "grade_level": P(), "cohort_year": P(), "cumulative_gpa": P(), "total_credits_earned": P(), "academic_standing": P(), "status": P(), "registration_hold": P(), "directory_info_opt_out": P(), "is_coppa_applicable": P(), "coppa_consent_type": P(), "coppa_consent_date": P(), "enrollment_date": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (student_id, naming, first_name, middle_name, last_name, full_name,
             date_of_birth, gender,
             getattr(args, "email", None) or "",
             getattr(args, "phone", None) or "",
             getattr(args, "address", None) or "{}",
             getattr(args, "emergency_contact", None) or "{}",
             None, current_program_id,
             getattr(args, "grade_level", None) or "",
             int(getattr(args, "cohort_year", None) or 0),
             "", "0", "good", "active",
             0, int(getattr(args, "directory_info_opt_out", None) or 0),
             coppa, "", "", enrollment_date,
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Student creation failed: {e}")

    audit(conn, SKILL, "edu-add-student", "educlaw_student", student_id,
          new_values={"naming_series": naming, "first_name": first_name, "last_name": last_name})
    conn.commit()
    ok({"id": student_id, "naming_series": naming, "full_name": full_name,
        "is_coppa_applicable": coppa})


def update_student(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        err("--student-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        err(f"Student {student_id} not found")

    r = dict(row)
    updates, params, changed = [], [], []

    for field in ("first_name", "middle_name", "last_name", "email", "phone",
                  "grade_level", "photo"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field} = ?"); params.append(val); changed.append(field)

    if getattr(args, "address", None) is not None:
        updates.append("address = ?"); params.append(args.address); changed.append("address")
    if getattr(args, "emergency_contact", None) is not None:
        updates.append("emergency_contact = ?"); params.append(args.emergency_contact)
        changed.append("emergency_contact")
    if getattr(args, "academic_standing", None) is not None:
        if args.academic_standing not in VALID_ACADEMIC_STANDINGS:
            err(f"--academic-standing must be one of: {', '.join(VALID_ACADEMIC_STANDINGS)}")
        updates.append("academic_standing = ?"); params.append(args.academic_standing)
        changed.append("academic_standing")
    if getattr(args, "current_program_id", None) is not None:
        if not conn.execute(Q.from_(Table("educlaw_program")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.current_program_id,)).fetchone():
            err(f"Program {args.current_program_id} not found")
        updates.append("current_program_id = ?"); params.append(args.current_program_id)
        changed.append("current_program_id")
    if getattr(args, "registration_hold", None) is not None:
        updates.append("registration_hold = ?"); params.append(int(args.registration_hold))
        changed.append("registration_hold")
    if getattr(args, "directory_info_opt_out", None) is not None:
        updates.append("directory_info_opt_out = ?")
        params.append(int(args.directory_info_opt_out))
        changed.append("directory_info_opt_out")
    if getattr(args, "cohort_year", None) is not None:
        updates.append("cohort_year = ?"); params.append(int(args.cohort_year))
        changed.append("cohort_year")

    if not changed:
        err("No fields to update")

    # Recompute full_name if name changed
    if any(f in changed for f in ("first_name", "middle_name", "last_name")):
        new_first = getattr(args, "first_name", None) or r["first_name"]
        new_mid = getattr(args, "middle_name", None) or r.get("middle_name", "") or ""
        new_last = getattr(args, "last_name", None) or r["last_name"]
        full_name = f"{new_first} {new_mid} {new_last}".replace("  ", " ").strip()
        updates.append("full_name = ?"); params.append(full_name)

    updates.append("updated_at = datetime('now')")
    params.append(student_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_student SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-student", "educlaw_student", student_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": student_id, "updated_fields": changed})


def get_student(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        err("--student-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        err(f"Student {student_id} not found")

    data = dict(row)
    data.pop("ssn_encrypted", None)  # Never expose encrypted SSN

    for field in ("address", "emergency_contact"):
        try:
            if data.get(field):
                data[field] = json.loads(data[field])
        except Exception:
            pass

    _g = Table("educlaw_guardian")
    _sg = Table("educlaw_student_guardian")
    guardians = conn.execute(
        Q.from_(_g).join(_sg).on(_sg.guardian_id == _g.id)
        .select(_g.id, _g.first_name, _g.last_name, _g.full_name, _g.email, _g.phone,
                _sg.relationship, _sg.has_custody, _sg.can_pickup,
                _sg.receives_communications, _sg.is_primary_contact, _sg.is_emergency_contact)
        .where(_sg.student_id == P())
        .get_sql(),
        (student_id,)
    ).fetchall()
    data["guardians"] = [dict(g) for g in guardians]

    # Auto-log FERPA data access
    user_id = getattr(args, "user_id", None) or "system"
    access_reason = getattr(args, "access_reason", None) or "Administrative access"
    company_id = data.get("company_id", "")
    _log_data_access_internal(conn, user_id, student_id, "demographics", "view",
                               access_reason, 0, company_id)
    conn.commit()
    ok(data)


def list_students(conn, args):
    _s = Table("educlaw_student")
    q = Q.from_(_s).select(
        _s.id, _s.naming_series, _s.first_name, _s.last_name, _s.full_name, _s.email,
        _s.grade_level, _s.current_program_id, _s.academic_standing, _s.status,
        _s.registration_hold, _s.company_id)
    params = []

    if getattr(args, "student_status", None):
        q = q.where(_s.status == P()); params.append(args.student_status)
    if getattr(args, "current_program_id", None):
        q = q.where(_s.current_program_id == P()); params.append(args.current_program_id)
    if getattr(args, "grade_level", None):
        q = q.where(_s.grade_level == P()); params.append(args.grade_level)
    if getattr(args, "academic_standing", None):
        q = q.where(_s.academic_standing == P()); params.append(args.academic_standing)
    if getattr(args, "company_id", None):
        q = q.where(_s.company_id == P()); params.append(args.company_id)

    q = q.orderby(_s.last_name).orderby(_s.first_name)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"students": [dict(r) for r in rows], "count": len(rows)})


def change_student_status(conn, args):
    student_id = getattr(args, "student_id", None)
    new_status = getattr(args, "student_status", None)
    reason = getattr(args, "reason", None)

    if not student_id:
        err("--student-id is required")
    if not new_status:
        err("--student-status is required")
    if new_status not in VALID_STUDENT_STATUSES:
        err(f"--student-status must be one of: {', '.join(VALID_STUDENT_STATUSES)}")
    if not reason:
        err("--reason is required for status change")

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        err(f"Student {student_id} not found")

    r = dict(row)
    _s = Table("educlaw_student")
    conn.execute(
        Q.update(_s)
        .set(_s.status, P())
        .set(_s.updated_at, LiteralValue("datetime('now')"))
        .where(_s.id == P())
        .get_sql(),
        (new_status, student_id)
    )
    audit(conn, SKILL, "edu-change-student-status", "educlaw_student", student_id,
          new_values={"old_status": r["status"], "new_status": new_status, "reason": reason})
    conn.commit()
    ok({"id": student_id, "old_status": r["status"], "student_status": new_status, "reason": reason})


def graduate_student(conn, args):
    student_id = getattr(args, "student_id", None)
    graduation_date = getattr(args, "graduation_date", None) or _now_iso()[:10]

    if not student_id:
        err("--student-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        err(f"Student {student_id} not found")

    r = dict(row)
    if r["status"] != "active":
        err(f"Student must be active to graduate (current: {r['status']})")

    _s = Table("educlaw_student")
    conn.execute(
        Q.update(_s)
        .set(_s.status, 'graduated')
        .set(_s.graduation_date, P())
        .set(_s.updated_at, LiteralValue("datetime('now')"))
        .where(_s.id == P())
        .get_sql(),
        (graduation_date, student_id)
    )

    # Complete active program enrollment
    _pe = Table("educlaw_program_enrollment")
    prog_enr = conn.execute(
        Q.from_(_pe).select(_pe.id)
        .where(_pe.student_id == P()).where(_pe.enrollment_status == 'active')
        .get_sql(),
        (student_id,)
    ).fetchone()
    if prog_enr:
        conn.execute(
            Q.update(_pe)
            .set(_pe.enrollment_status, 'completed')
            .set(_pe.updated_at, LiteralValue("datetime('now')"))
            .where(_pe.id == P())
            .get_sql(),
            (prog_enr["id"],)
        )

    audit(conn, SKILL, "edu-graduate-student", "educlaw_student", student_id,
          new_values={"graduation_date": graduation_date})
    conn.commit()
    ok({"id": student_id, "student_status": "graduated", "graduation_date": graduation_date})


# ─────────────────────────────────────────────────────────────────────────────
# GUARDIAN
# ─────────────────────────────────────────────────────────────────────────────

def add_guardian(conn, args):
    first_name = getattr(args, "first_name", None)
    last_name = getattr(args, "last_name", None)
    relationship = getattr(args, "relationship", None)
    company_id = getattr(args, "company_id", None)
    phone = getattr(args, "phone", None)

    if not first_name:
        err("--first-name is required")
    if not last_name:
        err("--last-name is required")
    if not relationship:
        err("--relationship is required")
    if relationship not in VALID_RELATIONSHIPS:
        err(f"--relationship must be one of: {', '.join(VALID_RELATIONSHIPS)}")
    if not company_id:
        err("--company-id is required")
    if not phone:
        err("--phone is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    guardian_id = str(uuid.uuid4())
    full_name = f"{first_name} {last_name}".strip()
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_guardian", {"id": P(), "first_name": P(), "last_name": P(), "full_name": P(), "relationship": P(), "email": P(), "phone": P(), "alternate_phone": P(), "address": P(), "occupation": P(), "employer": P(), "customer_id": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (guardian_id, first_name, last_name, full_name, relationship,
             getattr(args, "email", None) or "",
             phone,
             getattr(args, "alternate_phone", None) or "",
             getattr(args, "address", None) or "{}",
             getattr(args, "occupation", None) or "",
             getattr(args, "employer", None) or "",
             None,
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Guardian creation failed: {e}")

    # Link to student if student_id provided
    student_id = getattr(args, "student_id", None)
    if student_id:
        if not conn.execute(Q.from_(Table("educlaw_student")).select(Field("id")).where(Field("id") == P()).get_sql(), (student_id,)).fetchone():
            err(f"Student {student_id} not found")
        link_id = str(uuid.uuid4())
        try:
            sql, _ = insert_row("educlaw_student_guardian", {"id": P(), "student_id": P(), "guardian_id": P(), "relationship": P(), "has_custody": P(), "can_pickup": P(), "receives_communications": P(), "is_primary_contact": P(), "is_emergency_contact": P(), "created_at": P(), "created_by": P()})

            conn.execute(sql,
                (link_id, student_id, guardian_id, relationship,
                 int(getattr(args, "has_custody", None) or 1),
                 int(getattr(args, "can_pickup", None) or 1),
                 int(getattr(args, "receives_communications", None) or 1),
                 int(getattr(args, "is_primary_contact", None) or 0),
                 int(getattr(args, "is_emergency_contact", None) or 0),
                 now, getattr(args, "user_id", None) or "")
            )
        except sqlite3.IntegrityError:
            pass

    audit(conn, SKILL, "edu-add-guardian", "educlaw_guardian", guardian_id,
          new_values={"first_name": first_name, "last_name": last_name})
    conn.commit()
    ok({"id": guardian_id, "full_name": full_name, "relationship": relationship,
        "student_id": student_id})


def update_guardian(conn, args):
    guardian_id = getattr(args, "guardian_id", None)
    if not guardian_id:
        err("--guardian-id is required")

    row = conn.execute(Q.from_(Table("educlaw_guardian")).select(Table("educlaw_guardian").star).where(Field("id") == P()).get_sql(), (guardian_id,)).fetchone()
    if not row:
        err(f"Guardian {guardian_id} not found")

    r = dict(row)
    updates, params, changed = [], [], []

    for field in ("first_name", "last_name", "email", "phone", "alternate_phone",
                  "occupation", "employer"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field} = ?"); params.append(val); changed.append(field)

    if getattr(args, "address", None) is not None:
        updates.append("address = ?"); params.append(args.address); changed.append("address")
    if getattr(args, "relationship", None) is not None:
        if args.relationship not in VALID_RELATIONSHIPS:
            err(f"--relationship must be one of: {', '.join(VALID_RELATIONSHIPS)}")
        updates.append("relationship = ?"); params.append(args.relationship)
        changed.append("relationship")

    if not changed:
        err("No fields to update")

    if any(f in changed for f in ("first_name", "last_name")):
        new_first = getattr(args, "first_name", None) or r["first_name"]
        new_last = getattr(args, "last_name", None) or r["last_name"]
        updates.append("full_name = ?")
        params.append(f"{new_first} {new_last}".strip())

    updates.append("updated_at = datetime('now')")
    params.append(guardian_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_guardian SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-guardian", "educlaw_guardian", guardian_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": guardian_id, "updated_fields": changed})


def get_guardian(conn, args):
    guardian_id = getattr(args, "guardian_id", None)
    if not guardian_id:
        err("--guardian-id is required")

    row = conn.execute(Q.from_(Table("educlaw_guardian")).select(Table("educlaw_guardian").star).where(Field("id") == P()).get_sql(), (guardian_id,)).fetchone()
    if not row:
        err(f"Guardian {guardian_id} not found")

    data = dict(row)
    try:
        if data.get("address"):
            data["address"] = json.loads(data["address"])
    except Exception:
        pass

    _s = Table("educlaw_student")
    _sg = Table("educlaw_student_guardian")
    linked_students = conn.execute(
        Q.from_(_s).join(_sg).on(_sg.student_id == _s.id)
        .select(_s.id, _s.naming_series, _s.full_name, _sg.relationship, _sg.is_primary_contact)
        .where(_sg.guardian_id == P())
        .get_sql(),
        (guardian_id,)
    ).fetchall()
    data["linked_students"] = [dict(s) for s in linked_students]
    ok(data)


def list_guardians(conn, args):
    student_id = getattr(args, "student_id", None)

    _g = Table("educlaw_guardian")
    _sg = Table("educlaw_student_guardian")
    params = []

    if student_id:
        q = Q.from_(_g).join(_sg).on(_sg.guardian_id == _g.id).select(_g.star).where(_sg.student_id == P())
        params = [student_id]
    else:
        q = Q.from_(_g).select(_g.star)
        if getattr(args, "company_id", None):
            q = q.where(_g.company_id == P()); params.append(args.company_id)
        q = q.orderby(_g.last_name).orderby(_g.first_name)

    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"guardians": [dict(r) for r in rows], "count": len(rows)})


def link_guardian_to_student(conn, args):
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    relationship = getattr(args, "relationship", None)

    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")
    if not relationship:
        err("--relationship is required")
    if relationship not in VALID_RELATIONSHIPS:
        err(f"--relationship must be one of: {', '.join(VALID_RELATIONSHIPS)}")

    if not conn.execute(Q.from_(Table("educlaw_guardian")).select(Field("id")).where(Field("id") == P()).get_sql(), (guardian_id,)).fetchone():
        err(f"Guardian {guardian_id} not found")
    if not conn.execute(Q.from_(Table("educlaw_student")).select(Field("id")).where(Field("id") == P()).get_sql(), (student_id,)).fetchone():
        err(f"Student {student_id} not found")

    existing = conn.execute(Q.from_(Table("educlaw_student_guardian")).select(Field("id")).where(Field("student_id") == P()).where(Field("guardian_id") == P()).get_sql(), (student_id, guardian_id)).fetchone()
    if existing:
        err(f"Guardian {guardian_id} is already linked to student {student_id}")

    link_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_student_guardian", {"id": P(), "student_id": P(), "guardian_id": P(), "relationship": P(), "has_custody": P(), "can_pickup": P(), "receives_communications": P(), "is_primary_contact": P(), "is_emergency_contact": P(), "created_at": P(), "created_by": P()})


    conn.execute(sql,
        (link_id, student_id, guardian_id, relationship,
         int(getattr(args, "has_custody", None) or 1),
         int(getattr(args, "can_pickup", None) or 1),
         int(getattr(args, "receives_communications", None) or 1),
         int(getattr(args, "is_primary_contact", None) or 0),
         int(getattr(args, "is_emergency_contact", None) or 0),
         now, getattr(args, "user_id", None) or "")
    )
    audit(conn, SKILL, "edu-link-guardian-to-student", "educlaw_student_guardian", link_id,
          new_values={"student_id": student_id, "guardian_id": guardian_id})
    conn.commit()
    ok({"id": link_id, "student_id": student_id, "guardian_id": guardian_id,
        "relationship": relationship})


# ─────────────────────────────────────────────────────────────────────────────
# ONLINE ADMISSIONS PORTAL
# ─────────────────────────────────────────────────────────────────────────────

def portal_submit_application(conn, args):
    """Self-service application submission with limited fields (no internal-only data)."""
    first_name = getattr(args, "first_name", None)
    last_name = getattr(args, "last_name", None)
    email = getattr(args, "email", None)
    company_id = getattr(args, "company_id", None)

    if not first_name:
        err("--first-name is required")
    if not last_name:
        err("--last-name is required")
    if not email:
        err("--email is required")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    from erpclaw_lib.naming import get_next_name
    naming = get_next_name(conn, "educlaw_student_applicant", company_id=company_id)
    applicant_id = str(uuid.uuid4())
    now = _now_iso()
    full_name = f"{first_name} {last_name}".strip()

    applying_for_program_id = getattr(args, "applying_for_program_id", None) or None
    applying_for_term_id = getattr(args, "applying_for_term_id", None) or None
    application_date = getattr(args, "application_date", None) or date.today().isoformat()

    sql, _ = insert_row("educlaw_student_applicant", {
        "id": P(), "naming_series": P(), "first_name": P(), "last_name": P(),
        "email": P(), "phone": P(), "date_of_birth": P(),
        "gender": P(), "address": P(),
        "applying_for_program_id": P(), "applying_for_term_id": P(),
        "application_date": P(), "previous_school": P(),
        "status": P(), "company_id": P(),
        "created_at": P(), "updated_at": P(), "created_by": P(),
    })
    conn.execute(sql, (
        applicant_id, naming, first_name, last_name,
        email,
        getattr(args, "phone", None) or "",
        getattr(args, "date_of_birth", None) or "",
        getattr(args, "gender", None) or "",
        getattr(args, "address", None) or "{}",
        applying_for_program_id, applying_for_term_id,
        application_date,
        getattr(args, "previous_school", None) or "",
        "applied", company_id, now, now, "portal",
    ))

    audit(conn, SKILL, "edu-portal-submit-application", "educlaw_student_applicant",
          applicant_id, new_values={"full_name": full_name, "source": "portal"})
    conn.commit()
    ok({
        "id": applicant_id, "naming_series": naming, "full_name": full_name,
        "application_status": "applied", "application_date": application_date,
        "message": "Application submitted successfully. You will be notified of the decision.",
    })


def portal_check_application_status(conn, args):
    """Check the status of a submitted application."""
    applicant_id = getattr(args, "applicant_id", None)
    email = getattr(args, "email", None)

    if not applicant_id and not email:
        err("--applicant-id or --email is required")

    _app = Table("educlaw_student_applicant")

    if applicant_id:
        row = conn.execute(
            Q.from_(_app).select(_app.id, _app.naming_series, _app.full_name,
                                 _app.status, _app.application_date, _app.review_notes)
            .where(_app.id == P()).get_sql(), (applicant_id,)
        ).fetchone()
    else:
        row = conn.execute(
            Q.from_(_app).select(_app.id, _app.naming_series, _app.full_name,
                                 _app.status, _app.application_date, _app.review_notes)
            .where(_app.email == P())
            .orderby(_app.application_date, order=Order.desc)
            .limit(1).get_sql(), (email,)
        ).fetchone()

    if not row:
        err("Application not found")

    data = dict(row)
    # Map internal statuses to portal-friendly messages
    status_messages = {
        "applied": "Your application has been received and is being processed.",
        "under_review": "Your application is currently under review.",
        "accepted": "Congratulations! Your application has been accepted.",
        "rejected": "We regret to inform you that your application was not accepted.",
        "waitlisted": "Your application has been placed on the waitlist.",
        "pending_info": "Additional information is required. Please check your email.",
        "confirmed": "Your enrollment has been confirmed.",
        "enrolled": "You are now enrolled.",
    }
    data["status_message"] = status_messages.get(data["status"], "Status unknown.")
    # Don't expose internal review notes to portal users
    data.pop("review_notes", None)
    ok(data)


def portal_upload_document(conn, args):
    """Link a document reference to an application (document storage is external)."""
    applicant_id = getattr(args, "applicant_id", None)
    title = getattr(args, "title", None)
    company_id = getattr(args, "company_id", None)

    if not applicant_id:
        err("--applicant-id is required")
    if not title:
        err("--title is required (document title/description)")
    if not company_id:
        err("--company-id is required")

    _app = Table("educlaw_student_applicant")
    app_row = conn.execute(
        Q.from_(_app).select(_app.id, _app.documents)
        .where(_app.id == P()).get_sql(), (applicant_id,)
    ).fetchone()
    if not app_row:
        err(f"Applicant {applicant_id} not found")

    app = dict(app_row)
    existing_docs = []
    if app.get("documents"):
        try:
            existing_docs = json.loads(app["documents"]) if isinstance(app["documents"], str) else app["documents"]
        except Exception:
            existing_docs = []

    doc_entry = {
        "id": str(uuid.uuid4()),
        "title": title,
        "uploaded_at": _now_iso(),
        "uploaded_by": "portal",
    }
    existing_docs.append(doc_entry)

    conn.execute(
        "UPDATE educlaw_student_applicant SET documents = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(existing_docs), applicant_id)
    )
    conn.commit()

    ok({
        "applicant_id": applicant_id,
        "document_id": doc_entry["id"],
        "title": title,
        "total_documents": len(existing_docs),
    })


def list_pending_applications(conn, args):
    """Admin view: list all pending/in-review applications."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    _app = Table("educlaw_student_applicant")
    q = Q.from_(_app).select(_app.star).where(_app.company_id == P())
    params = [company_id]

    # Filter by status (default: applied + under_review)
    status_filter = getattr(args, "applicant_status", None)
    if status_filter:
        q = q.where(_app.status == P())
        params.append(status_filter)
    else:
        q = q.where(_app.status.isin(["applied", "under_review", "pending_info"]))

    term_id = getattr(args, "applying_for_term_id", None)
    if term_id:
        q = q.where(_app.applying_for_term_id == P())
        params.append(term_id)

    q = q.orderby(_app.application_date)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()

    # Summary counts
    counts = conn.execute(
        Q.from_(_app).select(_app.status, fn.Count(_app.star).as_("cnt"))
        .where(_app.company_id == P())
        .groupby(_app.status).get_sql(), (company_id,)
    ).fetchall()

    ok({
        "applications": [dict(r) for r in rows],
        "count": len(rows),
        "status_summary": {c["status"]: c["cnt"] for c in counts},
    })


# ─────────────────────────────────────────────────────────────────────────────
# FERPA COMPLIANCE
# ─────────────────────────────────────────────────────────────────────────────

def log_data_access(conn, args):
    user_id = getattr(args, "user_id", None)
    student_id = getattr(args, "student_id", None)
    data_category = getattr(args, "data_category", None)
    access_type = getattr(args, "access_type", None)
    company_id = getattr(args, "company_id", None)

    if not user_id:
        err("--user-id is required")
    if not student_id:
        err("--student-id is required")
    if not data_category:
        err("--data-category is required")
    if data_category not in VALID_DATA_CATEGORIES:
        err(f"--data-category must be one of: {', '.join(VALID_DATA_CATEGORIES)}")
    if not access_type:
        err("--access-type is required")
    if access_type not in VALID_ACCESS_TYPES:
        err(f"--access-type must be one of: {', '.join(VALID_ACCESS_TYPES)}")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("educlaw_student")).select(Field("id")).where(Field("id") == P()).get_sql(), (student_id,)).fetchone():
        err(f"Student {student_id} not found")

    log_id = str(uuid.uuid4())
    now = _now_iso()
    is_emergency = int(getattr(args, "is_emergency_access", None) or 0)

    sql, _ = insert_row("educlaw_data_access_log", {"id": P(), "user_id": P(), "student_id": P(), "data_category": P(), "access_type": P(), "access_reason": P(), "is_emergency_access": P(), "ip_address": P(), "company_id": P(), "created_at": P(), "created_by": P()})


    conn.execute(sql,
        (log_id, user_id, student_id, data_category, access_type,
         getattr(args, "access_reason", None) or "",
         is_emergency,
         getattr(args, "ip_address", None) or "",
         company_id, now, user_id)
    )
    conn.commit()
    ok({"id": log_id, "user_id": user_id, "student_id": student_id,
        "data_category": data_category, "access_type": access_type})


def add_consent_record(conn, args):
    student_id = getattr(args, "student_id", None)
    consent_type = getattr(args, "consent_type", None)
    granted_by = getattr(args, "granted_by", None)
    consent_date = getattr(args, "consent_date", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not consent_type:
        err("--consent-type is required")
    if consent_type not in VALID_CONSENT_TYPES:
        err(f"--consent-type must be one of: {', '.join(VALID_CONSENT_TYPES)}")
    if not granted_by:
        err("--granted-by is required")
    if not consent_date:
        err("--consent-date is required")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("educlaw_student")).select(Field("id")).where(Field("id") == P()).get_sql(), (student_id,)).fetchone():
        err(f"Student {student_id} not found")

    consent_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_consent_record", {"id": P(), "student_id": P(), "consent_type": P(), "granted_by": P(), "granted_by_relationship": P(), "consent_date": P(), "expiry_date": P(), "is_revoked": P(), "revoked_date": P(), "third_party_name": P(), "purpose": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})


    conn.execute(sql,
        (consent_id, student_id, consent_type, granted_by,
         getattr(args, "granted_by_relationship", None) or "",
         consent_date,
         getattr(args, "expiry_date", None) or "",
         0, "",
         getattr(args, "third_party_name", None) or "",
         getattr(args, "purpose", None) or "",
         company_id, now, now, getattr(args, "user_id", None) or "")
    )
    audit(conn, SKILL, "edu-add-consent-record", "educlaw_consent_record", consent_id,
          new_values={"consent_type": consent_type, "student_id": student_id})
    conn.commit()
    ok({"id": consent_id, "consent_type": consent_type, "student_id": student_id})


def revoke_consent(conn, args):
    consent_id = getattr(args, "consent_id", None)
    if not consent_id:
        err("--consent-id is required")

    row = conn.execute(Q.from_(Table("educlaw_consent_record")).select(Table("educlaw_consent_record").star).where(Field("id") == P()).get_sql(), (consent_id,)).fetchone()
    if not row:
        err(f"Consent record {consent_id} not found")

    r = dict(row)
    if r["is_revoked"]:
        err("Consent record is already revoked")

    revoked_date = getattr(args, "revoked_date", None) or _now_iso()[:10]
    _cr = Table("educlaw_consent_record")
    conn.execute(
        Q.update(_cr)
        .set(_cr.is_revoked, 1)
        .set(_cr.revoked_date, P())
        .set(_cr.updated_at, LiteralValue("datetime('now')"))
        .where(_cr.id == P())
        .get_sql(),
        (revoked_date, consent_id)
    )
    audit(conn, SKILL, "edu-revoke-consent", "educlaw_consent_record", consent_id,
          new_values={"is_revoked": 1, "revoked_date": revoked_date})
    conn.commit()
    ok({"id": consent_id, "is_revoked": 1, "revoked_date": revoked_date})


def export_student_record(conn, args):
    student_id = getattr(args, "student_id", None)
    user_id = getattr(args, "user_id", None) or "system"
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not company_id:
        err("--company-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        err(f"Student {student_id} not found")

    student = dict(row)
    student.pop("ssn_encrypted", None)

    _ce = Table("educlaw_course_enrollment")
    _sec = Table("educlaw_section")
    _c = Table("educlaw_course")
    _at2 = Table("educlaw_academic_term")
    enrollments = conn.execute(
        Q.from_(_ce)
        .join(_sec).on(_sec.id == _ce.section_id)
        .join(_c).on(_c.id == _sec.course_id)
        .join(_at2).on(_at2.id == _sec.academic_term_id)
        .select(_ce.star, _sec.naming_series.as_("section_series"), _sec.section_number,
                _c.course_code, _c.name.as_("course_name"), _c.credit_hours,
                _at2.name.as_("term_name"), _at2.start_date.as_("term_start"))
        .where(_ce.student_id == P())
        .orderby(_at2.start_date)
        .get_sql(),
        (student_id,)
    ).fetchall()

    _att = Table("educlaw_student_attendance")
    attendance = conn.execute(
        Q.from_(_att)
        .select(_att.attendance_date, _att.attendance_status, _att.late_minutes,
                _att.comments, _att.source)
        .where(_att.student_id == P())
        .orderby(_att.attendance_date, order=Order.desc).limit(1000)
        .get_sql(),
        (student_id,)
    ).fetchall()

    _cr = Table("educlaw_consent_record")
    consent = conn.execute(
        Q.from_(_cr).select(_cr.star).where(_cr.student_id == P()).get_sql(),
        (student_id,)
    ).fetchall()

    now = _now_iso()
    export_log_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_data_access_log", {"id": P(), "user_id": P(), "student_id": P(), "data_category": P(), "access_type": P(), "access_reason": P(), "is_emergency_access": P(), "ip_address": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (export_log_id, user_id, student_id, "grades", "export",
         "FERPA education record export request",
         0, "", company_id, now, user_id)
    )
    conn.commit()

    ok({
        "student": student,
        "course_enrollments": [dict(e) for e in enrollments],
        "attendance_records": [dict(a) for a in attendance],
        "consent_records": [dict(c) for c in consent],
        "exported_at": now,
        "exported_by": user_id,
        "access_log_id": export_log_id,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-student-applicant": add_student_applicant,
    "edu-update-student-applicant": update_student_applicant,
    "edu-get-applicant": get_applicant,
    "edu-list-applicants": list_applicants,
    "edu-approve-applicant": review_applicant,
    "edu-convert-applicant-to-student": convert_applicant_to_student,
    "edu-add-student": add_student,
    "edu-update-student": update_student,
    "edu-get-student": get_student,
    "edu-list-students": list_students,
    "edu-update-student-status": change_student_status,
    "edu-complete-graduation": graduate_student,
    "edu-add-guardian": add_guardian,
    "edu-update-guardian": update_guardian,
    "edu-get-guardian": get_guardian,
    "edu-list-guardians": list_guardians,
    "edu-assign-guardian": link_guardian_to_student,
    "edu-record-data-access": log_data_access,
    "edu-add-consent-record": add_consent_record,
    "edu-cancel-consent": revoke_consent,
    "edu-generate-student-record": export_student_record,
    "edu-portal-submit-application": portal_submit_application,
    "edu-portal-check-application-status": portal_check_application_status,
    "edu-portal-upload-document": portal_upload_document,
    "edu-list-pending-applications": list_pending_applications,
}
