"""EduClaw SPED — iep domain module

Actions: add-iep, list-ieps, get-iep, update-iep, activate-iep,
         add-iep-goal, list-iep-goals, update-iep-goal

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

ENTITY_PREFIXES.setdefault("sped_iep", "IEP-")

SKILL = "sped-educlaw-sped"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_json(value, default=None):
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default if default is not None else []


def _resolve_company_id(conn, company_id):
    """Resolve company_id: use provided value or fall back to first company."""
    if company_id:
        return company_id
    row = conn.execute("SELECT id FROM company LIMIT 1").fetchone()
    return row["id"] if row else ""


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: add-iep
# ─────────────────────────────────────────────────────────────────────────────

def add_iep(conn, args):
    """Create a new IEP in draft status."""
    student_id = getattr(args, "student_id", None) or None
    iep_date = getattr(args, "iep_date", None) or datetime.now().strftime("%Y-%m-%d")
    review_date = getattr(args, "review_date", None) or ""
    annual_review_date = getattr(args, "annual_review_date", None) or ""
    disability_category = getattr(args, "disability_category", None) or ""
    placement = getattr(args, "placement", None) or ""
    lre_percentage = getattr(args, "lre_percentage", None) or ""
    case_manager = getattr(args, "case_manager", None) or ""
    meeting_participants = getattr(args, "meeting_participants", None) or "[]"
    notes = getattr(args, "notes", None) or ""
    company_id = _resolve_company_id(conn, getattr(args, "company_id", None) or None)
    created_by = getattr(args, "user_id", None) or ""

    if not student_id:
        return err("--student-id is required")

    iep_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        ns = get_next_name(conn, "sped_iep", company_id)
    except Exception:
        ns = f"IEP-{iep_id[:8]}"

    conn.execute(
        """INSERT INTO sped_iep
           (id, naming_series, student_id, iep_date, review_date,
            annual_review_date, disability_category, placement,
            lre_percentage, case_manager, meeting_participants,
            notes, iep_status, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
        (iep_id, ns, student_id, iep_date, review_date,
         annual_review_date, disability_category, placement,
         lre_percentage, case_manager, meeting_participants,
         notes, company_id, now, now, created_by)
    )
    conn.commit()

    audit(conn, created_by, SKILL, "sped-add-iep", "sped_iep", iep_id,
          description=f"Created IEP {ns} for student {student_id}")

    return ok({
        "id": iep_id,
        "naming_series": ns,
        "iep_status": "draft",
        "student_id": student_id,
        "iep_date": iep_date,
        "message": f"IEP {ns} created in draft status",
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: list-ieps
# ─────────────────────────────────────────────────────────────────────────────

def list_ieps(conn, args):
    """List IEPs with optional filters."""
    student_id = getattr(args, "student_id", None) or None
    iep_status = getattr(args, "iep_status", None) or None
    company_id = getattr(args, "company_id", None) or None
    limit = getattr(args, "limit", None) or 50
    offset = getattr(args, "offset", None) or 0

    query = "SELECT * FROM sped_iep WHERE 1=1"
    params = []

    if student_id:
        query += " AND student_id = ?"
        params.append(student_id)
    if iep_status:
        query += " AND iep_status = ?"
        params.append(iep_status)
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    items = rows_to_list(rows)
    for item in items:
        item["meeting_participants"] = _parse_json(item.get("meeting_participants"))

    return ok({"items": items, "count": len(items)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: get-iep
# ─────────────────────────────────────────────────────────────────────────────

def get_iep(conn, args):
    """Get a single IEP by ID."""
    iep_id = getattr(args, "iep_id", None) or None
    if not iep_id:
        return err("--iep-id is required")

    row = conn.execute("SELECT * FROM sped_iep WHERE id = ?", (iep_id,)).fetchone()
    if not row:
        return err(f"IEP {iep_id} not found")

    data = row_to_dict(row)
    data["meeting_participants"] = _parse_json(data.get("meeting_participants"))

    # Include goals
    goals = conn.execute(
        "SELECT * FROM sped_iep_goal WHERE iep_id = ? ORDER BY sort_order", (iep_id,)
    ).fetchall()
    data["goals"] = rows_to_list(goals)

    # Include services
    services = conn.execute(
        "SELECT * FROM sped_service WHERE iep_id = ? ORDER BY service_type", (iep_id,)
    ).fetchall()
    data["services"] = rows_to_list(services)

    return ok(data)


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: update-iep
# ─────────────────────────────────────────────────────────────────────────────

def update_iep(conn, args):
    """Update a draft IEP. Active/expired IEPs cannot be modified."""
    iep_id = getattr(args, "iep_id", None) or None
    if not iep_id:
        return err("--iep-id is required")

    row = conn.execute("SELECT * FROM sped_iep WHERE id = ?", (iep_id,)).fetchone()
    if not row:
        return err(f"IEP {iep_id} not found")

    if row["iep_status"] != "draft":
        return err(f"Cannot update IEP in '{row['iep_status']}' status. Only draft IEPs can be modified.")

    updates = []
    params = []
    fields = {
        "iep_date": "iep_date",
        "review_date": "review_date",
        "annual_review_date": "annual_review_date",
        "disability_category": "disability_category",
        "placement": "placement",
        "lre_percentage": "lre_percentage",
        "case_manager": "case_manager",
        "meeting_participants": "meeting_participants",
        "notes": "notes",
    }

    for arg_name, col_name in fields.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)

    if not updates:
        return err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(iep_id)

    conn.execute(
        f"UPDATE sped_iep SET {', '.join(updates)} WHERE id = ?", params
    )
    conn.commit()

    user_id = getattr(args, "user_id", None) or ""
    audit(conn, user_id, SKILL, "sped-update-iep", "sped_iep", iep_id,
          description=f"Updated IEP {iep_id}")

    return ok({"id": iep_id, "message": "IEP updated"})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: activate-iep
# ─────────────────────────────────────────────────────────────────────────────

def activate_iep(conn, args):
    """Activate a draft IEP. Expires any previously active IEP for the same student."""
    iep_id = getattr(args, "iep_id", None) or None
    if not iep_id:
        return err("--iep-id is required")

    row = conn.execute("SELECT * FROM sped_iep WHERE id = ?", (iep_id,)).fetchone()
    if not row:
        return err(f"IEP {iep_id} not found")

    if row["iep_status"] != "draft":
        return err(f"Cannot activate IEP in '{row['iep_status']}' status. Only draft IEPs can be activated.")

    student_id = row["student_id"]
    now = _now_iso()

    # Expire any currently active IEP for this student
    conn.execute(
        """UPDATE sped_iep SET iep_status = 'expired', updated_at = ?
           WHERE student_id = ? AND iep_status = 'active'""",
        (now, student_id)
    )

    # Activate this IEP
    conn.execute(
        "UPDATE sped_iep SET iep_status = 'active', updated_at = ? WHERE id = ?",
        (now, iep_id)
    )
    conn.commit()

    user_id = getattr(args, "user_id", None) or ""
    audit(conn, user_id, SKILL, "sped-activate-iep", "sped_iep", iep_id,
          description=f"Activated IEP {iep_id} for student {student_id}")

    return ok({
        "id": iep_id,
        "iep_status": "active",
        "message": f"IEP activated. Any previous active IEP for student {student_id} has been expired.",
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: add-iep-goal
# ─────────────────────────────────────────────────────────────────────────────

def add_iep_goal(conn, args):
    """Add a measurable goal to an IEP."""
    iep_id = getattr(args, "iep_id", None) or None
    goal_area = getattr(args, "goal_area", None) or ""
    goal_description = getattr(args, "goal_description", None) or ""
    baseline = getattr(args, "baseline", None) or ""
    target = getattr(args, "target", None) or ""
    current_progress = getattr(args, "current_progress", None) or ""
    measurement_method = getattr(args, "measurement_method", None) or ""
    sort_order = getattr(args, "sort_order", None) or 0
    created_by = getattr(args, "user_id", None) or ""

    if not iep_id:
        return err("--iep-id is required")
    if not goal_description:
        return err("--goal-description is required")

    # Verify IEP exists
    iep = conn.execute("SELECT id, iep_status FROM sped_iep WHERE id = ?", (iep_id,)).fetchone()
    if not iep:
        return err(f"IEP {iep_id} not found")

    goal_id = str(uuid.uuid4())
    now = _now_iso()

    conn.execute(
        """INSERT INTO sped_iep_goal
           (id, iep_id, goal_area, goal_description, baseline, target,
            current_progress, measurement_method, goal_status, sort_order,
            created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?, ?, ?, ?)""",
        (goal_id, iep_id, goal_area, goal_description, baseline, target,
         current_progress, measurement_method, sort_order, now, now, created_by)
    )
    conn.commit()

    audit(conn, created_by, SKILL, "sped-add-iep-goal", "sped_iep_goal", goal_id,
          description=f"Added goal to IEP {iep_id}: {goal_area}")

    return ok({
        "id": goal_id,
        "iep_id": iep_id,
        "goal_area": goal_area,
        "goal_status": "in_progress",
        "message": f"Goal added to IEP {iep_id}",
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: list-iep-goals
# ─────────────────────────────────────────────────────────────────────────────

def list_iep_goals(conn, args):
    """List goals for a given IEP."""
    iep_id = getattr(args, "iep_id", None) or None
    if not iep_id:
        return err("--iep-id is required")

    rows = conn.execute(
        "SELECT * FROM sped_iep_goal WHERE iep_id = ? ORDER BY sort_order",
        (iep_id,)
    ).fetchall()

    return ok({"items": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTION: update-iep-goal
# ─────────────────────────────────────────────────────────────────────────────

def update_iep_goal(conn, args):
    """Update an IEP goal's progress or status."""
    goal_id = getattr(args, "goal_id", None) or None
    if not goal_id:
        return err("--goal-id is required")

    row = conn.execute("SELECT * FROM sped_iep_goal WHERE id = ?", (goal_id,)).fetchone()
    if not row:
        return err(f"Goal {goal_id} not found")

    updates = []
    params = []
    fields = {
        "goal_area": "goal_area",
        "goal_description": "goal_description",
        "baseline": "baseline",
        "target": "target",
        "current_progress": "current_progress",
        "measurement_method": "measurement_method",
        "goal_status": "goal_status",
        "sort_order": "sort_order",
    }

    for arg_name, col_name in fields.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)

    if not updates:
        return err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(goal_id)

    conn.execute(
        f"UPDATE sped_iep_goal SET {', '.join(updates)} WHERE id = ?", params
    )
    conn.commit()

    user_id = getattr(args, "user_id", None) or ""
    audit(conn, user_id, SKILL, "sped-update-iep-goal", "sped_iep_goal", goal_id,
          description=f"Updated goal {goal_id}")

    return ok({"id": goal_id, "message": "Goal updated"})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS dict
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "sped-add-iep": add_iep,
    "sped-list-ieps": list_ieps,
    "sped-get-iep": get_iep,
    "sped-update-iep": update_iep,
    "sped-activate-iep": activate_iep,
    "sped-add-iep-goal": add_iep_goal,
    "sped-list-iep-goals": list_iep_goals,
    "sped-update-iep-goal": update_iep_goal,
}
