"""EduClaw SPED — compliance domain module (includes reports + status)

Actions: compliance-check, overdue-iep-report, service-utilization-report,
         caseload-report, status

Imported by scripts/db_query.py.
"""
import os
import sys
from datetime import datetime, timezone, date, timedelta

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err, rows_to_list
except ImportError:
    pass

SKILL = "sped-educlaw-sped"
VERSION = "1.0.0"


def _today():
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: compliance-check
# ─────────────────────────────────────────────────────────────────────────────

def compliance_check(conn, args):
    """Check IEP compliance: overdue annual reviews, expired IEPs still active, etc."""
    company_id = getattr(args, "company_id", None) or None
    days_ahead = getattr(args, "days_ahead", None) or 30

    today = _today()
    cutoff = (date.today() + timedelta(days=int(days_ahead))).isoformat()

    findings = []

    # 1. Active IEPs with overdue annual review
    query = """
        SELECT id, naming_series, student_id, annual_review_date, iep_status
        FROM sped_iep
        WHERE iep_status = 'active'
          AND annual_review_date != ''
          AND annual_review_date < ?
    """
    params = [today]
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    overdue = conn.execute(query, params).fetchall()
    for row in overdue:
        findings.append({
            "finding_type": "overdue_annual_review",
            "severity": "high",
            "iep_id": row["id"],
            "naming_series": row["naming_series"],
            "student_id": row["student_id"],
            "annual_review_date": row["annual_review_date"],
            "message": f"IEP {row['naming_series']} annual review was due {row['annual_review_date']}",
        })

    # 2. Active IEPs with upcoming annual review (within days_ahead)
    query2 = """
        SELECT id, naming_series, student_id, annual_review_date
        FROM sped_iep
        WHERE iep_status = 'active'
          AND annual_review_date != ''
          AND annual_review_date >= ?
          AND annual_review_date <= ?
    """
    params2 = [today, cutoff]
    if company_id:
        query2 += " AND company_id = ?"
        params2.append(company_id)

    upcoming = conn.execute(query2, params2).fetchall()
    for row in upcoming:
        findings.append({
            "finding_type": "upcoming_annual_review",
            "severity": "medium",
            "iep_id": row["id"],
            "naming_series": row["naming_series"],
            "student_id": row["student_id"],
            "annual_review_date": row["annual_review_date"],
            "message": f"IEP {row['naming_series']} annual review due {row['annual_review_date']}",
        })

    # 3. Active services without recent logs (no log in last 14 days)
    two_weeks_ago = (date.today() - timedelta(days=14)).isoformat()
    query3 = """
        SELECT s.id, s.service_type, s.student_id, s.provider,
               MAX(sl.session_date) as last_session
        FROM sped_service s
        LEFT JOIN sped_service_log sl ON sl.service_id = s.id
        WHERE s.service_status = 'active'
    """
    params3 = []
    if company_id:
        query3 += " AND s.company_id = ?"
        params3.append(company_id)

    query3 += " GROUP BY s.id HAVING last_session IS NULL OR last_session < ?"
    params3.append(two_weeks_ago)

    stale_services = conn.execute(query3, params3).fetchall()
    for row in stale_services:
        findings.append({
            "finding_type": "stale_service",
            "severity": "medium",
            "service_id": row["id"],
            "service_type": row["service_type"],
            "student_id": row["student_id"],
            "provider": row["provider"],
            "last_session": row["last_session"] or "never",
            "message": f"Active {row['service_type']} service has no sessions in last 14 days",
        })

    return ok({
        "findings": findings,
        "total_findings": len(findings),
        "checked_at": _today(),
        "days_ahead": int(days_ahead),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: overdue-iep-report
# ─────────────────────────────────────────────────────────────────────────────

def overdue_iep_report(conn, args):
    """List all IEPs with overdue annual reviews."""
    company_id = getattr(args, "company_id", None) or None
    today = _today()

    query = """
        SELECT id, naming_series, student_id, iep_date, annual_review_date,
               iep_status, case_manager
        FROM sped_iep
        WHERE iep_status = 'active'
          AND annual_review_date != ''
          AND annual_review_date < ?
    """
    params = [today]
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    query += " ORDER BY annual_review_date ASC"

    rows = conn.execute(query, params).fetchall()
    items = rows_to_list(rows)

    # Calculate days overdue
    for item in items:
        try:
            review = date.fromisoformat(item["annual_review_date"])
            item["days_overdue"] = (date.today() - review).days
        except Exception:
            item["days_overdue"] = 0

    return ok({"items": items, "count": len(items), "report_date": today})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: service-utilization-report
# ─────────────────────────────────────────────────────────────────────────────

def service_utilization_report(conn, args):
    """Report service utilization across all active services."""
    company_id = getattr(args, "company_id", None) or None
    date_from = getattr(args, "date_from", None) or None
    date_to = getattr(args, "date_to", None) or None

    query = """
        SELECT s.service_type,
               COUNT(DISTINCT s.id) as service_count,
               COUNT(DISTINCT s.student_id) as student_count,
               SUM(s.frequency_minutes_per_week) as total_prescribed_minutes_per_week,
               COALESCE(SUM(CASE WHEN sl.was_absent = 0 THEN sl.duration_minutes ELSE 0 END), 0) as total_minutes_delivered,
               COUNT(sl.id) as total_sessions,
               COALESCE(SUM(sl.was_absent), 0) as absent_sessions
        FROM sped_service s
        LEFT JOIN sped_service_log sl ON sl.service_id = s.id
    """
    conditions = ["s.service_status = 'active'"]
    params = []

    if company_id:
        conditions.append("s.company_id = ?")
        params.append(company_id)
    if date_from:
        conditions.append("(sl.session_date IS NULL OR sl.session_date >= ?)")
        params.append(date_from)
    if date_to:
        conditions.append("(sl.session_date IS NULL OR sl.session_date <= ?)")
        params.append(date_to)

    query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY s.service_type ORDER BY s.service_type"

    rows = conn.execute(query, params).fetchall()
    return ok({"items": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: caseload-report
# ─────────────────────────────────────────────────────────────────────────────

def caseload_report(conn, args):
    """Report caseload by case manager (active IEPs per manager)."""
    company_id = getattr(args, "company_id", None) or None

    query = """
        SELECT case_manager,
               COUNT(*) as active_iep_count,
               COUNT(DISTINCT student_id) as student_count
        FROM sped_iep
        WHERE iep_status = 'active'
          AND case_manager != ''
    """
    params = []
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    query += " GROUP BY case_manager ORDER BY active_iep_count DESC"

    rows = conn.execute(query, params).fetchall()
    return ok({"items": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: status (registered in db_query.py, but provided as fallback)
# ─────────────────────────────────────────────────────────────────────────────

# status is registered directly in db_query.py — not in ACTIONS here.


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS dict
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "sped-compliance-check": compliance_check,
    "sped-overdue-iep-report": overdue_iep_report,
    "sped-service-utilization-report": service_utilization_report,
    "sped-caseload-report": caseload_report,
}
