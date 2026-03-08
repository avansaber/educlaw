"""EduClaw Higher Education — faculty domain module (8 actions)

Faculty records, course assignments, research grants, workload reporting.
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

    ENTITY_PREFIXES.setdefault("highered_faculty", "HFAC-")
except ImportError:
    pass

SKILL = "highered-educlaw-highered"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_RANKS = ("adjunct", "instructor", "assistant_professor", "associate_professor", "professor", "emeritus")
VALID_TENURE_STATUSES = ("non_tenure", "tenure_track", "tenured")
VALID_ASSIGNMENT_ROLES = ("primary", "secondary", "ta")
VALID_GRANT_STATUSES = ("proposed", "active", "completed", "expired")


def _to_money(val):
    if val is None:
        return "0.00"
    return str(round_currency(to_decimal(val)))


# ===========================================================================
# Faculty CRUD
# ===========================================================================

def add_faculty(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    name = getattr(args, "name", None)
    if not name:
        return err("--name is required")

    email = getattr(args, "email", None) or ""
    department = getattr(args, "department", None) or ""
    rank = getattr(args, "rank", None) or "instructor"
    if rank not in VALID_RANKS:
        return err(f"Invalid rank: {rank}. Must be one of: {', '.join(VALID_RANKS)}")
    tenure_status = getattr(args, "tenure_status", None) or "non_tenure"
    if tenure_status not in VALID_TENURE_STATUSES:
        return err(f"Invalid tenure_status: {tenure_status}")
    hire_date = getattr(args, "hire_date", None) or ""

    fac_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = company_id
    naming = get_next_name(conn, "highered_faculty")

    conn.execute("""
        INSERT INTO highered_faculty
        (id, naming_series, name, email, department, rank, tenure_status,
         hire_date, company_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (fac_id, naming, name, email, department, rank, tenure_status,
          hire_date, company_id, now, now))
    audit(conn, SKILL, "highered-add-faculty", "highered_faculty", fac_id,
          new_values={"name": name, "rank": rank})
    conn.commit()
    ok({"id": fac_id, "naming_series": naming, "name": name,
        "rank": rank, "tenure_status": tenure_status})


def update_faculty(conn, args):
    fac_id = getattr(args, "id", None)
    if not fac_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_faculty WHERE id=?", (fac_id,)).fetchone()
    if not row:
        return err("Faculty not found")

    updates, params = [], []
    for field in ("name", "email", "department", "hire_date"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    rank = getattr(args, "rank", None)
    if rank is not None:
        if rank not in VALID_RANKS:
            return err(f"Invalid rank: {rank}")
        updates.append("rank=?")
        params.append(rank)
    tenure_status = getattr(args, "tenure_status", None)
    if tenure_status is not None:
        if tenure_status not in VALID_TENURE_STATUSES:
            return err(f"Invalid tenure_status: {tenure_status}")
        updates.append("tenure_status=?")
        params.append(tenure_status)
    if not updates:
        return err("No fields to update")
    updates.append("updated_at=?")
    params.append(_now_iso())
    params.append(fac_id)
    conn.execute(f"UPDATE highered_faculty SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    ok({"id": fac_id, "updated": True})


def list_faculty(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_faculty WHERE company_id=?"
    params = [company_id]
    department = getattr(args, "department", None)
    if department:
        q += " AND department=?"
        params.append(department)
    rank = getattr(args, "rank", None)
    if rank:
        q += " AND rank=?"
        params.append(rank)
    tenure_status = getattr(args, "tenure_status", None)
    if tenure_status:
        q += " AND tenure_status=?"
        params.append(tenure_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY name LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"faculty": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Course Assignments
# ===========================================================================

def add_course_assignment(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    faculty_id = getattr(args, "faculty_id", None)
    if not faculty_id:
        return err("--faculty-id is required")
    if not conn.execute("SELECT id FROM highered_faculty WHERE id=?", (faculty_id,)).fetchone():
        return err(f"Faculty {faculty_id} not found")
    section_id = getattr(args, "section_id", None)
    if not section_id:
        return err("--section-id is required")
    if not conn.execute("SELECT id FROM highered_section WHERE id=?", (section_id,)).fetchone():
        return err(f"Section {section_id} not found")

    role = getattr(args, "role", None) or "primary"
    if role not in VALID_ASSIGNMENT_ROLES:
        return err(f"Invalid role: {role}")

    assign_id = str(uuid.uuid4())
    try:
        conn.execute("""
            INSERT INTO highered_course_assignment
            (id, faculty_id, section_id, role, company_id, created_at)
            VALUES (?,?,?,?,?,?)
        """, (assign_id, faculty_id, section_id, role, company_id, _now_iso()))
        conn.commit()
        ok({"id": assign_id, "faculty_id": faculty_id,
            "section_id": section_id, "role": role})
    except Exception as e:
        if "UNIQUE" in str(e):
            return err("Faculty already assigned to this section")
        return err(str(e))


def list_course_assignments(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_course_assignment WHERE company_id=?"
    params = [company_id]
    faculty_id = getattr(args, "faculty_id", None)
    if faculty_id:
        q += " AND faculty_id=?"
        params.append(faculty_id)
    section_id = getattr(args, "section_id", None)
    if section_id:
        q += " AND section_id=?"
        params.append(section_id)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"assignments": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Research Grants
# ===========================================================================

def add_research_grant(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    faculty_id = getattr(args, "faculty_id", None)
    if not faculty_id:
        return err("--faculty-id is required")
    if not conn.execute("SELECT id FROM highered_faculty WHERE id=?", (faculty_id,)).fetchone():
        return err(f"Faculty {faculty_id} not found")
    title = getattr(args, "title", None)
    if not title:
        return err("--title is required")

    funding_agency = getattr(args, "funding_agency", None) or ""
    amount = _to_money(getattr(args, "amount", None))
    start_date = getattr(args, "start_date", None) or ""
    end_date = getattr(args, "end_date", None) or ""
    grant_status = getattr(args, "grant_status", None) or "proposed"
    if grant_status not in VALID_GRANT_STATUSES:
        return err(f"Invalid grant_status: {grant_status}")

    grant_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO highered_research_grant
        (id, faculty_id, title, funding_agency, amount, start_date, end_date,
         grant_status, company_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (grant_id, faculty_id, title, funding_agency, amount, start_date,
          end_date, grant_status, company_id, _now_iso()))
    conn.commit()
    ok({"id": grant_id, "faculty_id": faculty_id, "title": title,
        "amount": amount, "grant_status": grant_status})


def list_research_grants(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_research_grant WHERE company_id=?"
    params = [company_id]
    faculty_id = getattr(args, "faculty_id", None)
    if faculty_id:
        q += " AND faculty_id=?"
        params.append(faculty_id)
    grant_status = getattr(args, "grant_status", None)
    if grant_status:
        q += " AND grant_status=?"
        params.append(grant_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"grants": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Reports
# ===========================================================================

def faculty_workload_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT f.id, f.name, f.department, f.rank,
               COUNT(ca.id) as sections_assigned,
               (SELECT COUNT(*) FROM highered_research_grant g
                WHERE g.faculty_id = f.id AND g.grant_status = 'active') as active_grants
        FROM highered_faculty f
        LEFT JOIN highered_course_assignment ca ON ca.faculty_id = f.id
        WHERE f.company_id=?
        GROUP BY f.id
        ORDER BY sections_assigned DESC
    """, (company_id,)).fetchall()
    ok({"workload": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-add-faculty": add_faculty,
    "highered-update-faculty": update_faculty,
    "highered-list-faculty": list_faculty,
    "highered-add-course-assignment": add_course_assignment,
    "highered-list-course-assignments": list_course_assignments,
    "highered-add-research-grant": add_research_grant,
    "highered-list-research-grants": list_research_grants,
    "highered-faculty-workload-report": faculty_workload_report,
}
