"""EduClaw SPED — services domain module

Actions: add-service, list-services, get-service, update-service,
         add-service-log, list-service-logs, service-hours-report

Imported by scripts/db_query.py.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict, rows_to_list
    from erpclaw_lib.audit import audit
except ImportError:
    pass

ENTITY_PREFIXES.setdefault("sped_service", "SVC-")

SKILL = "sped-educlaw-sped"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_SERVICE_TYPES = (
    "speech_therapy", "occupational_therapy", "physical_therapy",
    "counseling", "behavioral", "aide", "transport", "other",
)


def _resolve_company_id(conn, company_id):
    if company_id:
        return company_id
    row = conn.execute("SELECT id FROM company LIMIT 1").fetchone()
    return row["id"] if row else ""


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: add-service
# ─────────────────────────────────────────────────────────────────────────────

def add_service(conn, args):
    """Add a SPED service allocation linked to an IEP."""
    student_id = getattr(args, "student_id", None) or None
    iep_id = getattr(args, "iep_id", None) or None
    service_type = getattr(args, "service_type", None) or None
    provider = getattr(args, "provider", None) or ""
    frequency_minutes_per_week = getattr(args, "frequency_minutes_per_week", None) or 0
    setting = getattr(args, "setting", None) or ""
    start_date = getattr(args, "start_date", None) or ""
    end_date = getattr(args, "end_date", None) or ""
    notes = getattr(args, "notes", None) or ""
    company_id = _resolve_company_id(conn, getattr(args, "company_id", None) or None)
    created_by = getattr(args, "user_id", None) or ""

    if not student_id:
        return err("--student-id is required")
    if not iep_id:
        return err("--iep-id is required")
    if not service_type:
        return err("--service-type is required")
    if service_type not in VALID_SERVICE_TYPES:
        return err(f"Invalid service type '{service_type}'. Must be one of: {', '.join(VALID_SERVICE_TYPES)}")

    # Verify IEP exists
    iep = conn.execute("SELECT id FROM sped_iep WHERE id = ?", (iep_id,)).fetchone()
    if not iep:
        return err(f"IEP {iep_id} not found")

    svc_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        ns = get_next_name(conn, "sped_service", company_id)
    except Exception:
        ns = f"SVC-{svc_id[:8]}"

    conn.execute(
        """INSERT INTO sped_service
           (id, naming_series, student_id, iep_id, service_type, provider,
            frequency_minutes_per_week, setting, start_date, end_date,
            notes, service_status, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
        (svc_id, ns, student_id, iep_id, service_type, provider,
         int(frequency_minutes_per_week), setting, start_date, end_date,
         notes, company_id, now, now, created_by)
    )
    conn.commit()

    audit(conn, created_by, SKILL, "sped-add-service", "sped_service", svc_id,
          description=f"Added {service_type} service for student {student_id}")

    return ok({
        "id": svc_id,
        "naming_series": ns,
        "service_type": service_type,
        "service_status": "active",
        "student_id": student_id,
        "iep_id": iep_id,
        "message": f"Service {ns} created",
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: list-services
# ─────────────────────────────────────────────────────────────────────────────

def list_services(conn, args):
    """List services with optional filters."""
    student_id = getattr(args, "student_id", None) or None
    iep_id = getattr(args, "iep_id", None) or None
    service_type = getattr(args, "service_type", None) or None
    service_status = getattr(args, "service_status", None) or None
    company_id = getattr(args, "company_id", None) or None
    limit = getattr(args, "limit", None) or 50
    offset = getattr(args, "offset", None) or 0

    query = "SELECT * FROM sped_service WHERE 1=1"
    params = []

    if student_id:
        query += " AND student_id = ?"
        params.append(student_id)
    if iep_id:
        query += " AND iep_id = ?"
        params.append(iep_id)
    if service_type:
        query += " AND service_type = ?"
        params.append(service_type)
    if service_status:
        query += " AND service_status = ?"
        params.append(service_status)
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return ok({"items": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: get-service
# ─────────────────────────────────────────────────────────────────────────────

def get_service(conn, args):
    """Get a single service by ID, including session logs."""
    service_id = getattr(args, "service_id", None) or None
    if not service_id:
        return err("--service-id is required")

    row = conn.execute("SELECT * FROM sped_service WHERE id = ?", (service_id,)).fetchone()
    if not row:
        return err(f"Service {service_id} not found")

    data = row_to_dict(row)

    # Include session logs
    logs = conn.execute(
        "SELECT * FROM sped_service_log WHERE service_id = ? ORDER BY session_date DESC",
        (service_id,)
    ).fetchall()
    data["logs"] = rows_to_list(logs)
    data["total_minutes_delivered"] = sum(
        l["duration_minutes"] for l in data["logs"] if not l.get("was_absent")
    )

    return ok(data)


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: update-service
# ─────────────────────────────────────────────────────────────────────────────

def update_service(conn, args):
    """Update a service's details or status."""
    service_id = getattr(args, "service_id", None) or None
    if not service_id:
        return err("--service-id is required")

    row = conn.execute("SELECT * FROM sped_service WHERE id = ?", (service_id,)).fetchone()
    if not row:
        return err(f"Service {service_id} not found")

    updates = []
    params = []
    fields = {
        "provider": "provider",
        "frequency_minutes_per_week": "frequency_minutes_per_week",
        "setting": "setting",
        "start_date": "start_date",
        "end_date": "end_date",
        "notes": "notes",
        "service_status": "service_status",
    }

    for arg_name, col_name in fields.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            if arg_name == "frequency_minutes_per_week":
                val = int(val)
            updates.append(f"{col_name} = ?")
            params.append(val)

    if not updates:
        return err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(service_id)

    conn.execute(
        f"UPDATE sped_service SET {', '.join(updates)} WHERE id = ?", params
    )
    conn.commit()

    user_id = getattr(args, "user_id", None) or ""
    audit(conn, user_id, SKILL, "sped-update-service", "sped_service", service_id,
          description=f"Updated service {service_id}")

    return ok({"id": service_id, "message": "Service updated"})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: add-service-log
# ─────────────────────────────────────────────────────────────────────────────

def add_service_log(conn, args):
    """Log an individual service session."""
    service_id = getattr(args, "service_id", None) or None
    session_date = getattr(args, "session_date", None) or datetime.now().strftime("%Y-%m-%d")
    duration_minutes = getattr(args, "duration_minutes", None) or 0
    provider = getattr(args, "provider", None) or ""
    session_notes = getattr(args, "session_notes", None) or ""
    is_makeup_session = getattr(args, "is_makeup_session", None) or 0
    was_absent = getattr(args, "was_absent", None) or 0
    absence_reason = getattr(args, "absence_reason", None) or ""
    created_by = getattr(args, "user_id", None) or ""

    if not service_id:
        return err("--service-id is required")

    # Verify service exists
    svc = conn.execute("SELECT id, provider FROM sped_service WHERE id = ?", (service_id,)).fetchone()
    if not svc:
        return err(f"Service {service_id} not found")

    # Default provider to service's assigned provider
    if not provider:
        provider = svc["provider"]

    log_id = str(uuid.uuid4())
    now = _now_iso()

    conn.execute(
        """INSERT INTO sped_service_log
           (id, service_id, session_date, duration_minutes, provider,
            session_notes, is_makeup_session, was_absent, absence_reason,
            created_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (log_id, service_id, session_date, int(duration_minutes), provider,
         session_notes, int(is_makeup_session), int(was_absent), absence_reason,
         now, created_by)
    )
    conn.commit()

    audit(conn, created_by, SKILL, "sped-add-service-log", "sped_service_log", log_id,
          description=f"Logged session for service {service_id}")

    return ok({
        "id": log_id,
        "service_id": service_id,
        "session_date": session_date,
        "duration_minutes": int(duration_minutes),
        "message": "Service session logged",
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: list-service-logs
# ─────────────────────────────────────────────────────────────────────────────

def list_service_logs(conn, args):
    """List session logs for a service."""
    service_id = getattr(args, "service_id", None) or None
    date_from = getattr(args, "date_from", None) or None
    date_to = getattr(args, "date_to", None) or None
    limit = getattr(args, "limit", None) or 50
    offset = getattr(args, "offset", None) or 0

    if not service_id:
        return err("--service-id is required")

    query = "SELECT * FROM sped_service_log WHERE service_id = ?"
    params = [service_id]

    if date_from:
        query += " AND session_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND session_date <= ?"
        params.append(date_to)

    query += " ORDER BY session_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return ok({"items": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: service-hours-report
# ─────────────────────────────────────────────────────────────────────────────

def service_hours_report(conn, args):
    """Report on service hours delivered vs. prescribed for a student or service."""
    student_id = getattr(args, "student_id", None) or None
    service_id = getattr(args, "service_id", None) or None
    date_from = getattr(args, "date_from", None) or None
    date_to = getattr(args, "date_to", None) or None

    if not student_id and not service_id:
        return err("--student-id or --service-id is required")

    query = """
        SELECT s.id as service_id, s.service_type, s.provider,
               s.frequency_minutes_per_week, s.student_id,
               s.start_date, s.end_date, s.service_status,
               COALESCE(SUM(CASE WHEN sl.was_absent = 0 THEN sl.duration_minutes ELSE 0 END), 0) as total_minutes_delivered,
               COUNT(sl.id) as total_sessions,
               COALESCE(SUM(sl.was_absent), 0) as absent_sessions
        FROM sped_service s
        LEFT JOIN sped_service_log sl ON sl.service_id = s.id
    """
    params = []
    conditions = []

    if student_id:
        conditions.append("s.student_id = ?")
        params.append(student_id)
    if service_id:
        conditions.append("s.id = ?")
        params.append(service_id)
    if date_from:
        conditions.append("(sl.session_date IS NULL OR sl.session_date >= ?)")
        params.append(date_from)
    if date_to:
        conditions.append("(sl.session_date IS NULL OR sl.session_date <= ?)")
        params.append(date_to)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY s.id ORDER BY s.service_type"

    rows = conn.execute(query, params).fetchall()
    items = rows_to_list(rows)

    return ok({"items": items, "count": len(items)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS dict
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "sped-add-service": add_service,
    "sped-list-services": list_services,
    "sped-get-service": get_service,
    "sped-update-service": update_service,
    "sped-add-service-log": add_service_log,
    "sped-list-service-logs": list_service_logs,
    "sped-service-hours-report": service_hours_report,
}
