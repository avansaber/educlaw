"""EduClaw Higher Education — alumni domain module (8 actions)

Alumni records, events, giving/donations, engagement tracking, reports.
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

    ENTITY_PREFIXES.setdefault("highered_alumnus", "HALM-")
except ImportError:
    pass

SKILL = "highered-educlaw-highered"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_ENGAGEMENT_LEVELS = ("inactive", "low", "medium", "high", "champion")
VALID_EVENT_TYPES = ("reunion", "networking", "fundraiser", "career_fair", "other")
VALID_GIFT_TYPES = ("cash", "stock", "planned", "in_kind")


def _to_money(val):
    if val is None:
        return "0.00"
    return str(round_currency(to_decimal(val)))


# ===========================================================================
# Alumni CRUD
# ===========================================================================

def add_alumnus(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    name = getattr(args, "name", None)
    if not name:
        return err("--name is required")

    email = getattr(args, "email", None) or ""
    graduation_year = int(getattr(args, "graduation_year", None) or 0)
    degree_program = getattr(args, "degree_program", None) or ""
    employer = getattr(args, "employer", None) or ""
    job_title = getattr(args, "job_title", None) or ""
    engagement_level = getattr(args, "engagement_level", None) or "inactive"
    if engagement_level not in VALID_ENGAGEMENT_LEVELS:
        return err(f"Invalid engagement_level: {engagement_level}")

    alum_id = str(uuid.uuid4())
    now = _now_iso()
    naming = get_next_name(conn, "highered_alumnus", company_id=company_id)

    conn.execute("""
        INSERT INTO highered_alumnus
        (id, naming_series, name, email, graduation_year, degree_program,
         employer, job_title, is_donor, total_giving, engagement_level,
         company_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,0,'0',?,?,?,?)
    """, (alum_id, naming, name, email, graduation_year, degree_program,
          employer, job_title, engagement_level, company_id, now, now))
    audit(conn, SKILL, "highered-add-alumnus", "highered_alumnus", alum_id,
          new_values={"name": name})
    conn.commit()
    ok({"id": alum_id, "naming_series": naming, "name": name,
        "engagement_level": engagement_level})


def update_alumnus(conn, args):
    alum_id = getattr(args, "id", None)
    if not alum_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_alumnus WHERE id=?", (alum_id,)).fetchone()
    if not row:
        return err("Alumnus not found")

    updates, params = [], []
    for field in ("name", "email", "degree_program", "employer", "job_title"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    graduation_year = getattr(args, "graduation_year", None)
    if graduation_year is not None:
        updates.append("graduation_year=?")
        params.append(int(graduation_year))
    engagement_level = getattr(args, "engagement_level", None)
    if engagement_level is not None:
        if engagement_level not in VALID_ENGAGEMENT_LEVELS:
            return err(f"Invalid engagement_level: {engagement_level}")
        updates.append("engagement_level=?")
        params.append(engagement_level)
    if not updates:
        return err("No fields to update")
    updates.append("updated_at=?")
    params.append(_now_iso())
    params.append(alum_id)
    conn.execute(f"UPDATE highered_alumnus SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    ok({"id": alum_id, "updated": True})


def list_alumni(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_alumnus WHERE company_id=?"
    params = [company_id]
    graduation_year = getattr(args, "graduation_year", None)
    if graduation_year:
        q += " AND graduation_year=?"
        params.append(int(graduation_year))
    engagement_level = getattr(args, "engagement_level", None)
    if engagement_level:
        q += " AND engagement_level=?"
        params.append(engagement_level)
    is_donor = getattr(args, "is_donor", None)
    if is_donor is not None:
        q += " AND is_donor=?"
        params.append(int(is_donor))
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY name LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"alumni": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Alumni Events
# ===========================================================================

def add_alumni_event(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    name = getattr(args, "name", None)
    if not name:
        return err("--name is required")
    event_date = getattr(args, "event_date", None)
    if not event_date:
        return err("--event-date is required")
    event_type = getattr(args, "event_type", None) or "other"
    if event_type not in VALID_EVENT_TYPES:
        return err(f"Invalid event_type: {event_type}")
    attendees = int(getattr(args, "attendees", None) or 0)

    event_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO highered_alumni_event
        (id, name, event_date, event_type, attendees, company_id, created_at)
        VALUES (?,?,?,?,?,?,?)
    """, (event_id, name, event_date, event_type, attendees, company_id, _now_iso()))
    conn.commit()
    ok({"id": event_id, "name": name, "event_type": event_type})


def list_alumni_events(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_alumni_event WHERE company_id=?"
    params = [company_id]
    event_type = getattr(args, "event_type", None)
    if event_type:
        q += " AND event_type=?"
        params.append(event_type)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY event_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    ok({"events": [dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# Giving Records
# ===========================================================================

def add_giving_record(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    alumnus_id = getattr(args, "alumnus_id", None)
    if not alumnus_id:
        return err("--alumnus-id is required")
    alum = conn.execute("SELECT * FROM highered_alumnus WHERE id=?", (alumnus_id,)).fetchone()
    if not alum:
        return err(f"Alumnus {alumnus_id} not found")

    amount = _to_money(getattr(args, "amount", None))
    if to_decimal(amount) <= Decimal("0"):
        return err("--amount must be positive")
    giving_date = getattr(args, "giving_date", None) or _now_iso()
    campaign = getattr(args, "campaign", None) or ""
    gift_type = getattr(args, "gift_type", None) or "cash"
    if gift_type not in VALID_GIFT_TYPES:
        return err(f"Invalid gift_type: {gift_type}")

    record_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO highered_giving_record
        (id, alumnus_id, amount, giving_date, campaign, gift_type,
         company_id, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (record_id, alumnus_id, amount, giving_date, campaign, gift_type,
          company_id, _now_iso()))

    # Update alumnus total giving and donor status
    new_total = str(round_currency(to_decimal(alum["total_giving"]) + to_decimal(amount)))
    conn.execute(
        "UPDATE highered_alumnus SET total_giving=?, is_donor=1, updated_at=? WHERE id=?",
        (new_total, _now_iso(), alumnus_id)
    )
    conn.commit()
    ok({"id": record_id, "alumnus_id": alumnus_id, "amount": amount,
        "gift_type": gift_type, "total_giving": new_total})


# ===========================================================================
# Reports
# ===========================================================================

def alumni_giving_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT gift_type, COUNT(*) as count,
               SUM(CAST(amount AS REAL)) as total_amount
        FROM highered_giving_record
        WHERE company_id=?
        GROUP BY gift_type
        ORDER BY total_amount DESC
    """, (company_id,)).fetchall()
    grand_total = sum(r["total_amount"] or 0 for r in rows)
    ok({"by_type": [dict(r) for r in rows], "grand_total": grand_total})


def alumni_engagement_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    rows = conn.execute("""
        SELECT engagement_level, COUNT(*) as count
        FROM highered_alumnus
        WHERE company_id=?
        GROUP BY engagement_level
        ORDER BY count DESC
    """, (company_id,)).fetchall()
    total = sum(r["count"] for r in rows)
    ok({"engagement": [dict(r) for r in rows], "total_alumni": total})


# ===========================================================================
# Action map
# ===========================================================================

ACTIONS = {
    "highered-add-alumnus": add_alumnus,
    "highered-update-alumnus": update_alumnus,
    "highered-list-alumni": list_alumni,
    "highered-add-alumni-event": add_alumni_event,
    "highered-list-alumni-events": list_alumni_events,
    "highered-add-giving-record": add_giving_record,
    "highered-alumni-giving-report": alumni_giving_report,
    "highered-alumni-engagement-report": alumni_engagement_report,
}
