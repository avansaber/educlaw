"""EduClaw — dormitory/housing management domain module

Actions for managing housing units, student room assignments,
occupancy reports, availability, and waitlists.

Imported by db_query.py (unified router).
"""
import json
import os
import sys
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_UNIT_TYPES = ("single", "double", "triple", "suite", "apartment")
VALID_UNIT_STATUSES = ("available", "occupied", "maintenance", "closed")
VALID_ASSIGNMENT_STATUSES = ("active", "completed", "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# HOUSING UNIT CRUD
# ─────────────────────────────────────────────────────────────────────────────

def add_housing_unit(conn, args):
    """Add a housing unit (dorm room)."""
    building_name = getattr(args, "building", None)
    room_number = getattr(args, "room_number", None)
    company_id = getattr(args, "company_id", None)

    if not building_name:
        err("--building is required (building name)")
    if not room_number:
        err("--room-number is required")
    if not company_id:
        err("--company-id is required")

    unit_type = getattr(args, "unit_type", None) or getattr(args, "room_type", None) or "double"
    if unit_type not in VALID_UNIT_TYPES:
        err(f"Invalid unit type. Must be one of: {', '.join(VALID_UNIT_TYPES)}")

    capacity = int(getattr(args, "capacity", None) or 1)
    if capacity < 1:
        err("--capacity must be at least 1")

    unit_id = str(uuid.uuid4())
    now = _now_iso()
    monthly_rate = getattr(args, "amount", None) or "0"

    sql, _ = insert_row("educlaw_housing_unit", {
        "id": P(), "building_name": P(), "floor": P(), "room_number": P(),
        "capacity": P(), "unit_type": P(), "amenities": P(),
        "monthly_rate": P(), "status": P(), "company_id": P(),
        "created_at": P(),
    })
    conn.execute(sql, (
        unit_id, building_name,
        getattr(args, "floor", None) or "",
        room_number, capacity, unit_type,
        getattr(args, "description", None) or "",
        str(Decimal(str(monthly_rate))),
        "available", company_id, now,
    ))
    audit(conn, SKILL, "edu-add-housing-unit", "educlaw_housing_unit", unit_id,
          new_values={"building": building_name, "room": room_number})
    conn.commit()
    ok({"id": unit_id, "building_name": building_name, "room_number": room_number,
        "unit_type": unit_type, "capacity": capacity, "status": "available"})


def list_housing_units(conn, args):
    """List housing units with filters."""
    _hu = Table("educlaw_housing_unit")
    q = Q.from_(_hu).select(_hu.star)
    params = []

    company_id = getattr(args, "company_id", None)
    if company_id:
        q = q.where(_hu.company_id == P())
        params.append(company_id)

    building = getattr(args, "building", None)
    if building:
        q = q.where(_hu.building_name == P())
        params.append(building)

    status = getattr(args, "status", None)
    if status:
        q = q.where(_hu.status == P())
        params.append(status)

    unit_type = getattr(args, "unit_type", None) or getattr(args, "room_type", None)
    if unit_type:
        q = q.where(_hu.unit_type == P())
        params.append(unit_type)

    q = q.orderby(_hu.building_name).orderby(_hu.room_number)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()

    # Add current occupancy
    _ha = Table("educlaw_housing_assignment")
    result = []
    for r in rows:
        d = dict(r)
        cnt = conn.execute(
            Q.from_(_ha).select(fn.Count(_ha.id).as_("cnt"))
            .where(_ha.housing_unit_id == P()).where(_ha.status == "active")
            .get_sql(), (d["id"],)
        ).fetchone()
        d["current_occupancy"] = dict(cnt)["cnt"] if cnt else 0
        result.append(d)

    ok({"housing_units": result, "count": len(result)})


def assign_housing(conn, args):
    """Assign a student to a housing unit."""
    student_id = getattr(args, "student_id", None)
    housing_unit_id = getattr(args, "room_id", None) or getattr(args, "housing_unit_id", None)
    academic_year = getattr(args, "academic_year", None) or getattr(args, "academic_year_id", None)

    if not student_id:
        err("--student-id is required")
    if not housing_unit_id:
        err("--room-id is required (housing unit ID)")
    if not academic_year:
        err("--academic-year-id is required")

    # Verify student
    _st = Table("educlaw_student")
    st_row = conn.execute(
        Q.from_(_st).select(_st.id, _st.full_name).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone()
    if not st_row:
        err(f"Student {student_id} not found")

    # Verify housing unit
    _hu = Table("educlaw_housing_unit")
    hu_row = conn.execute(
        Q.from_(_hu).select(_hu.star).where(_hu.id == P()).get_sql(),
        (housing_unit_id,)
    ).fetchone()
    if not hu_row:
        err(f"Housing unit {housing_unit_id} not found")
    unit = dict(hu_row)

    if unit["status"] in ("maintenance", "closed"):
        err(f"Housing unit is not available (status: {unit['status']})")

    # Check capacity
    _ha = Table("educlaw_housing_assignment")
    cnt = conn.execute(
        Q.from_(_ha).select(fn.Count(_ha.id).as_("cnt"))
        .where(_ha.housing_unit_id == P()).where(_ha.status == "active")
        .get_sql(), (housing_unit_id,)
    ).fetchone()
    current = dict(cnt)["cnt"] if cnt else 0
    if current >= unit["capacity"]:
        err(f"Housing unit is at capacity ({current}/{unit['capacity']})")

    # Check student not already assigned this year
    existing = conn.execute(
        Q.from_(_ha).select(_ha.id)
        .where(_ha.student_id == P()).where(_ha.academic_year == P())
        .where(_ha.status == "active")
        .get_sql(), (student_id, academic_year)
    ).fetchone()
    if existing:
        err("Student already has an active housing assignment for this academic year")

    assign_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_housing_assignment", {
        "id": P(), "student_id": P(), "housing_unit_id": P(),
        "academic_year": P(), "semester": P(),
        "move_in_date": P(), "move_out_date": P(),
        "meal_plan": P(), "status": P(), "created_at": P(),
    })
    conn.execute(sql, (
        assign_id, student_id, housing_unit_id,
        academic_year,
        getattr(args, "term_type", None) or "",
        getattr(args, "start_date", None) or "",
        getattr(args, "end_date", None) or "",
        getattr(args, "meal_plan", None) or "",
        "active", now,
    ))

    # Update unit status if now full
    if current + 1 >= unit["capacity"]:
        conn.execute(
            "UPDATE educlaw_housing_unit SET status = 'occupied' WHERE id = ?",
            (housing_unit_id,)
        )

    audit(conn, SKILL, "edu-assign-housing", "educlaw_housing_assignment", assign_id,
          new_values={"student_id": student_id, "unit_id": housing_unit_id})
    conn.commit()
    ok({
        "id": assign_id, "student_id": student_id,
        "housing_unit_id": housing_unit_id,
        "building": unit["building_name"], "room": unit["room_number"],
        "academic_year": academic_year, "assignment_status": "active",
    })


def release_housing(conn, args):
    """Release a student's housing assignment."""
    assignment_id = getattr(args, "reference_id", None) or getattr(args, "assignment_id", None)
    student_id = getattr(args, "student_id", None)

    if not assignment_id and not student_id:
        err("--reference-id (assignment ID) or --student-id is required")

    _ha = Table("educlaw_housing_assignment")
    if assignment_id:
        row = conn.execute(
            Q.from_(_ha).select(_ha.star).where(_ha.id == P()).where(_ha.status == "active")
            .get_sql(), (assignment_id,)
        ).fetchone()
    else:
        row = conn.execute(
            Q.from_(_ha).select(_ha.star).where(_ha.student_id == P()).where(_ha.status == "active")
            .orderby(_ha.created_at, order=Order.desc).limit(1)
            .get_sql(), (student_id,)
        ).fetchone()

    if not row:
        err("Active housing assignment not found")

    assignment = dict(row)
    move_out = date.today().isoformat()

    conn.execute(
        "UPDATE educlaw_housing_assignment SET status = 'completed', move_out_date = ? WHERE id = ?",
        (move_out, assignment["id"])
    )

    # Update unit status back to available
    _hu = Table("educlaw_housing_unit")
    conn.execute(
        "UPDATE educlaw_housing_unit SET status = 'available' WHERE id = ?",
        (assignment["housing_unit_id"],)
    )

    audit(conn, SKILL, "edu-release-housing", "educlaw_housing_assignment",
          assignment["id"], new_values={"status": "completed", "move_out_date": move_out})
    conn.commit()
    ok({
        "assignment_id": assignment["id"],
        "student_id": assignment["student_id"],
        "housing_unit_id": assignment["housing_unit_id"],
        "move_out_date": move_out, "assignment_status": "completed",
    })


def list_housing_assignments(conn, args):
    """List housing assignments with filters."""
    _ha = Table("educlaw_housing_assignment")
    _hu = Table("educlaw_housing_unit")
    _st = Table("educlaw_student")

    q = Q.from_(_ha).join(_hu).on(_hu.id == _ha.housing_unit_id) \
        .join(_st).on(_st.id == _ha.student_id) \
        .select(
            _ha.id.as_("assignment_id"), _ha.academic_year, _ha.semester,
            _ha.move_in_date, _ha.move_out_date, _ha.meal_plan, _ha.status,
            _st.id.as_("student_id"), _st.full_name.as_("student_name"),
            _st.naming_series.as_("student_series"),
            _hu.id.as_("unit_id"), _hu.building_name, _hu.room_number, _hu.unit_type,
        )
    params = []

    company_id = getattr(args, "company_id", None)
    if company_id:
        q = q.where(_hu.company_id == P())
        params.append(company_id)

    academic_year = getattr(args, "academic_year", None) or getattr(args, "academic_year_id", None)
    if academic_year:
        q = q.where(_ha.academic_year == P())
        params.append(academic_year)

    status = getattr(args, "status", None)
    if status:
        q = q.where(_ha.status == P())
        params.append(status)

    building = getattr(args, "building", None)
    if building:
        q = q.where(_hu.building_name == P())
        params.append(building)

    q = q.orderby(_hu.building_name).orderby(_hu.room_number)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"assignments": [dict(r) for r in rows], "count": len(rows)})


def housing_occupancy_report(conn, args):
    """Generate housing occupancy report by building."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    _hu = Table("educlaw_housing_unit")
    _ha = Table("educlaw_housing_assignment")

    buildings = conn.execute(
        Q.from_(_hu).select(
            _hu.building_name,
            fn.Count(_hu.id).as_("unit_count"),
            fn.Sum(_hu.capacity).as_("total_capacity"),
        )
        .where(_hu.company_id == P())
        .where(_hu.status != "closed")
        .groupby(_hu.building_name)
        .orderby(_hu.building_name)
        .get_sql(), (company_id,)
    ).fetchall()

    report = []
    grand_capacity = 0
    grand_occupied = 0
    for b in buildings:
        bd = dict(b)
        cap = bd["total_capacity"] or 0
        # Count active assignments in this building
        occupied = conn.execute(
            Q.from_(_ha).join(_hu).on(_hu.id == _ha.housing_unit_id)
            .select(fn.Count(_ha.id).as_("cnt"))
            .where(_hu.building_name == P())
            .where(_hu.company_id == P())
            .where(_ha.status == "active")
            .get_sql(), (bd["building_name"], company_id)
        ).fetchone()
        occ = dict(occupied)["cnt"] if occupied else 0

        bd["occupied"] = occ
        bd["available"] = cap - occ
        bd["occupancy_rate"] = round(occ / cap * 100, 1) if cap > 0 else 0
        grand_capacity += cap
        grand_occupied += occ
        report.append(bd)

    ok({
        "company_id": company_id,
        "buildings": report,
        "total_capacity": grand_capacity,
        "total_occupied": grand_occupied,
        "total_available": grand_capacity - grand_occupied,
        "overall_occupancy_rate": round(grand_occupied / grand_capacity * 100, 1) if grand_capacity > 0 else 0,
    })


def housing_availability(conn, args):
    """List available housing units with remaining capacity."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    _hu = Table("educlaw_housing_unit")
    _ha = Table("educlaw_housing_assignment")

    units = conn.execute(
        Q.from_(_hu).select(_hu.star)
        .where(_hu.company_id == P())
        .where(_hu.status.isin(["available", "occupied"]))
        .orderby(_hu.building_name).orderby(_hu.room_number)
        .get_sql(), (company_id,)
    ).fetchall()

    available = []
    for u in units:
        ud = dict(u)
        cnt = conn.execute(
            Q.from_(_ha).select(fn.Count(_ha.id).as_("cnt"))
            .where(_ha.housing_unit_id == P()).where(_ha.status == "active")
            .get_sql(), (ud["id"],)
        ).fetchone()
        occupied = dict(cnt)["cnt"] if cnt else 0
        remaining = ud["capacity"] - occupied
        if remaining > 0:
            ud["current_occupancy"] = occupied
            ud["remaining_capacity"] = remaining
            available.append(ud)

    ok({"available_units": available, "count": len(available)})


def housing_waitlist(conn, args):
    """Manage housing waitlist. If student_id provided, adds to waitlist. Otherwise lists waitlist."""
    student_id = getattr(args, "student_id", None)
    company_id = getattr(args, "company_id", None)

    if not company_id:
        err("--company-id is required")

    # If student provided, this is a waitlist request
    if student_id:
        _st = Table("educlaw_student")
        st_row = conn.execute(
            Q.from_(_st).select(_st.id, _st.full_name).where(_st.id == P()).get_sql(),
            (student_id,)
        ).fetchone()
        if not st_row:
            err(f"Student {student_id} not found")

        academic_year = getattr(args, "academic_year", None) or getattr(args, "academic_year_id", None)
        if not academic_year:
            err("--academic-year-id is required for waitlist")

        # Use educlaw_notification to track housing waitlist requests
        now = _now_iso()
        notif_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_notification", {
            "id": P(), "recipient_type": P(), "recipient_id": P(),
            "notification_type": P(), "title": P(), "message": P(),
            "reference_type": P(), "reference_id": P(),
            "company_id": P(), "created_at": P(), "created_by": P(),
        })
        conn.execute(sql, (
            notif_id, "student", student_id, "housing_waitlist",
            "Housing Waitlist Request",
            f"Student has been added to the housing waitlist for {academic_year}.",
            "housing_waitlist", academic_year,
            company_id, now, "system",
        ))
        conn.commit()
        ok({
            "student_id": student_id,
            "academic_year": academic_year,
            "waitlist_status": "waiting",
            "added_at": now,
        })
    else:
        # List current waitlist (housing_waitlist notifications)
        _notif = Table("educlaw_notification")
        rows = conn.execute(
            Q.from_(_notif).select(_notif.star)
            .where(_notif.company_id == P())
            .where(_notif.notification_type == "housing_waitlist")
            .where(_notif.is_read == 0)
            .orderby(_notif.created_at)
            .get_sql(), (company_id,)
        ).fetchall()

        waitlist = []
        _st = Table("educlaw_student")
        for r in rows:
            rd = dict(r)
            st = conn.execute(
                Q.from_(_st).select(_st.full_name, _st.naming_series)
                .where(_st.id == P()).get_sql(), (rd["recipient_id"],)
            ).fetchone()
            entry = {
                "student_id": rd["recipient_id"],
                "student_name": dict(st)["full_name"] if st else "Unknown",
                "academic_year": rd["reference_id"],
                "requested_at": rd["created_at"],
            }
            waitlist.append(entry)

        ok({"waitlist": waitlist, "count": len(waitlist)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-housing-unit": add_housing_unit,
    "edu-list-housing-units": list_housing_units,
    "edu-assign-housing": assign_housing,
    "edu-release-housing": release_housing,
    "edu-list-housing-assignments": list_housing_assignments,
    "edu-housing-occupancy-report": housing_occupancy_report,
    "edu-housing-availability": housing_availability,
    "edu-housing-waitlist": housing_waitlist,
}
