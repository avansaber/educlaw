"""EduClaw Higher Education -- admissions domain module (6 actions)

Applications, admission decisions, application tracking.
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
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row

    ENTITY_PREFIXES.setdefault("highered_application", "HAPP-")
except ImportError:
    pass

SKILL = "highered-educlaw-highered"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_APP_STATUSES = ("submitted", "under_review", "accepted", "rejected", "waitlisted", "withdrawn")
VALID_DECISIONS = ("pending", "admit", "deny", "waitlist", "conditional_admit", "defer")


def _to_money(val):
    if val is None:
        return "0.00"
    return str(round_currency(to_decimal(val)))


def _validate_company(conn, company_id):
    if not company_id:
        return err("--company-id is required")
    if not conn.execute(Q.from_(Table("company")).select(Field('id')).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        return err(f"Company {company_id} not found")


# ===========================================================================
# Application CRUD
# ===========================================================================

def add_application(conn, args):
    company_id = getattr(args, "company_id", None)
    _validate_company(conn, company_id)
    applicant_name = getattr(args, "name", None)
    if not applicant_name:
        return err("--name is required (applicant name)")

    email = getattr(args, "email", None) or ""
    phone = getattr(args, "phone", None) or ""
    program_id = getattr(args, "program_id", None)
    if program_id:
        if not conn.execute(Q.from_(Table("highered_degree_program")).select(Field('id')).where(Field("id") == P()).get_sql(), (program_id,)).fetchone():
            return err(f"Program {program_id} not found")
    application_date = getattr(args, "application_date", None) or _now_iso()[:10]
    intended_term = getattr(args, "term", None) or ""
    intended_year = int(getattr(args, "year", None) or 0)
    gpa_incoming = getattr(args, "gpa_incoming", None) or "0.00"
    test_scores = getattr(args, "test_scores", None) or "{}"
    documents = getattr(args, "documents", None) or "[]"
    notes = getattr(args, "reason", None) or ""

    app_id = str(uuid.uuid4())
    now = _now_iso()
    naming = get_next_name(conn, "highered_application", company_id=company_id)

    conn.execute("""
        INSERT INTO highered_application
        (id, naming_series, applicant_name, email, phone, program_id,
         application_date, intended_term, intended_year, gpa_incoming,
         test_scores, documents, application_status, notes,
         company_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'submitted',?,?,?,?)
    """, (app_id, naming, applicant_name, email, phone, program_id,
          application_date, intended_term, intended_year, gpa_incoming,
          test_scores, documents, notes, company_id, now, now))
    audit(conn, SKILL, "highered-add-application", "highered_application", app_id,
          new_values={"applicant_name": applicant_name})
    conn.commit()
    ok({"id": app_id, "naming_series": naming, "applicant_name": applicant_name,
        "application_status": "submitted"})


def list_applications(conn, args):
    company_id = getattr(args, "company_id", None)
    _validate_company(conn, company_id)
    q = "SELECT * FROM highered_application WHERE company_id=?"
    params = [company_id]
    program_id = getattr(args, "program_id", None)
    if program_id:
        q += " AND program_id=?"
        params.append(program_id)
    application_status = getattr(args, "application_status", None)
    if application_status:
        q += " AND application_status=?"
        params.append(application_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY application_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"applications": [dict(r) for r in rows], "count": len(rows)})


def get_application(conn, args):
    app_id = getattr(args, "id", None)
    if not app_id:
        return err("--id is required")
    row = conn.execute(Q.from_(Table("highered_application")).select(Table("highered_application").star).where(Field("id") == P()).get_sql(), (app_id,)).fetchone()
    if not row:
        return err("Application not found")
    # Get any decisions
    decisions = conn.execute(Q.from_(Table("highered_admission_decision")).select(Table("highered_admission_decision").star).where(Field("application_id") == P()).orderby(Field("decision_date")).get_sql(), (app_id,)).fetchall()
    ok({"application": dict(row), "decisions": [dict(d) for d in decisions]})


# ===========================================================================
# Admission Decision
# ===========================================================================

def add_admission_decision(conn, args):
    company_id = getattr(args, "company_id", None)
    _validate_company(conn, company_id)
    application_id = getattr(args, "application_id", None)
    if not application_id:
        return err("--application-id is required")
    app = conn.execute(Q.from_(Table("highered_application")).select(Table("highered_application").star).where(Field("id") == P()).get_sql(), (application_id,)).fetchone()
    if not app:
        return err(f"Application {application_id} not found")

    decision = getattr(args, "decision", None) or "pending"
    if decision not in VALID_DECISIONS:
        return err(f"Invalid decision: {decision}. Must be one of: {', '.join(VALID_DECISIONS)}")
    decided_by = getattr(args, "placed_by", None) or ""
    decision_date = getattr(args, "decision_date", None) or _now_iso()[:10]
    conditions = getattr(args, "conditions", None) or ""
    scholarship_offered = _to_money(getattr(args, "scholarship_offered", None))
    notes = getattr(args, "reason", None) or ""

    dec_id = str(uuid.uuid4())
    now = _now_iso()
    conn.execute("""
        INSERT INTO highered_admission_decision
        (id, application_id, decision, decided_by, decision_date, conditions,
         scholarship_offered, notes, company_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (dec_id, application_id, decision, decided_by, decision_date,
          conditions, scholarship_offered, notes, company_id, now, now))

    # Update application status based on decision
    status_map = {
        "admit": "accepted",
        "deny": "rejected",
        "waitlist": "waitlisted",
        "conditional_admit": "accepted",
        "defer": "under_review",
    }
    new_app_status = status_map.get(decision)
    if new_app_status:
        conn.execute(
            "UPDATE highered_application SET application_status=?, updated_at=? WHERE id=?",
            (new_app_status, now, application_id)
        )
    conn.commit()
    ok({"id": dec_id, "application_id": application_id, "decision": decision,
        "scholarship_offered": scholarship_offered})


def update_admission_decision(conn, args):
    dec_id = getattr(args, "id", None)
    if not dec_id:
        return err("--id is required")
    row = conn.execute(Q.from_(Table("highered_admission_decision")).select(Table("highered_admission_decision").star).where(Field("id") == P()).get_sql(), (dec_id,)).fetchone()
    if not row:
        return err("Decision not found")

    updates, params = [], []
    decision = getattr(args, "decision", None)
    if decision is not None:
        if decision not in VALID_DECISIONS:
            return err(f"Invalid decision: {decision}")
        updates.append("decision=?")
        params.append(decision)
    for field in ("decided_by", "conditions", "notes"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    decision_date = getattr(args, "decision_date", None)
    if decision_date is not None:
        updates.append("decision_date=?")
        params.append(decision_date)
    scholarship_offered = getattr(args, "scholarship_offered", None)
    if scholarship_offered is not None:
        updates.append("scholarship_offered=?")
        params.append(_to_money(scholarship_offered))
    if not updates:
        return err("No fields to update")
    updates.append("updated_at=?")
    params.append(_now_iso())
    params.append(dec_id)
    conn.execute(f"UPDATE highered_admission_decision SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    ok({"id": dec_id, "updated": True})


def list_admission_decisions(conn, args):
    company_id = getattr(args, "company_id", None)
    _validate_company(conn, company_id)
    q = "SELECT * FROM highered_admission_decision WHERE company_id=?"
    params = [company_id]
    application_id = getattr(args, "application_id", None)
    if application_id:
        q += " AND application_id=?"
        params.append(application_id)
    decision = getattr(args, "decision", None)
    if decision:
        q += " AND decision=?"
        params.append(decision)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY decision_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"decisions": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-add-application": add_application,
    "highered-list-applications": list_applications,
    "highered-get-application": get_application,
    "highered-add-admission-decision": add_admission_decision,
    "highered-update-admission-decision": update_admission_decision,
    "highered-list-admission-decisions": list_admission_decisions,
}
