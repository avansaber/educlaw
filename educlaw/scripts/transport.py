"""EduClaw — transport domain module (Bus/Transportation Management)

8 actions for bus route management, stop assignment, student transport
enrollment, bus roster generation, and transport reporting.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, LiteralValue
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_ROUTE_STATUSES = ("active", "inactive", "suspended")
VALID_TRANSPORT_TYPES = ("both", "am_only", "pm_only", "none")
VALID_TRANSPORT_STATUSES = ("active", "inactive")


# ─────────────────────────────────────────────────────────────────────────────
# BUS ROUTE
# ─────────────────────────────────────────────────────────────────────────────

def add_bus_route(conn, args):
    """Create a new bus route."""
    school_id = getattr(args, "school_id", None)
    route_number = getattr(args, "route_number", None)

    if not school_id:
        err("--school-id is required")
    if not route_number:
        err("--route-number is required")

    route_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_bus_route", {
        "id": P(), "school_id": P(), "route_number": P(),
        "route_name": P(), "driver_name": P(), "driver_phone": P(),
        "vehicle_id": P(), "vehicle_number": P(), "capacity": P(),
        "am_start_time": P(), "pm_start_time": P(),
        "status": P(), "notes": P(),
        "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql,
        (route_id, school_id, route_number,
         getattr(args, "route_name", None) or "",
         getattr(args, "driver_name", None) or "",
         getattr(args, "driver_phone", None) or "",
         getattr(args, "vehicle_id", None) or "",
         getattr(args, "vehicle_number", None) or "",
         int(getattr(args, "capacity", None) or 0) if getattr(args, "capacity", None) else None,
         getattr(args, "am_start_time", None) or "",
         getattr(args, "pm_start_time", None) or "",
         "active", getattr(args, "notes", None) or "",
         now, now)
    )

    audit(conn, SKILL, "edu-add-bus-route", "educlaw_bus_route", route_id,
          new_values={"route_number": route_number, "school_id": school_id})
    conn.commit()
    ok({"id": route_id, "school_id": school_id, "route_number": route_number,
        "route_status": "active"})


def update_bus_route(conn, args):
    """Update an existing bus route."""
    route_id = getattr(args, "route_id", None)
    if not route_id:
        err("--route-id is required")

    _br = Table("educlaw_bus_route")
    row = conn.execute(
        Q.from_(_br).select(_br.star).where(_br.id == P()).get_sql(),
        (route_id,)
    ).fetchone()
    if not row:
        err(f"Bus route {route_id} not found")

    updates, params, changed = [], [], []

    for field in ("route_number", "route_name", "driver_name", "driver_phone",
                  "vehicle_id", "vehicle_number", "am_start_time",
                  "pm_start_time", "notes"):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field} = ?"); params.append(val)
            changed.append(field)

    if getattr(args, "capacity", None) is not None:
        updates.append("capacity = ?"); params.append(int(args.capacity))
        changed.append("capacity")

    if getattr(args, "status", None) is not None:
        if args.status not in VALID_ROUTE_STATUSES:
            err(f"--status must be one of: {', '.join(VALID_ROUTE_STATUSES)}")
        updates.append("status = ?"); params.append(args.status)
        changed.append("status")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(route_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_bus_route SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"id": route_id, "updated_fields": changed})


def list_bus_routes(conn, args):
    """List bus routes for a school."""
    school_id = getattr(args, "school_id", None)
    if not school_id:
        err("--school-id is required")

    _br = Table("educlaw_bus_route")
    q = Q.from_(_br).select(_br.star).where(_br.school_id == P())
    params = [school_id]

    if getattr(args, "status", None):
        q = q.where(_br.status == P()); params.append(args.status)

    q = q.orderby(_br.route_number)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"school_id": school_id, "bus_routes": [dict(r) for r in rows],
        "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# BUS STOP
# ─────────────────────────────────────────────────────────────────────────────

def add_bus_stop(conn, args):
    """Add a stop to a bus route."""
    route_id = getattr(args, "route_id", None)
    stop_order = getattr(args, "stop_order", None)
    stop_name = getattr(args, "stop_name", None)

    if not route_id:
        err("--route-id is required")
    if stop_order is None:
        err("--stop-order is required")
    if not stop_name:
        err("--stop-name is required")

    _br = Table("educlaw_bus_route")
    if not conn.execute(
        Q.from_(_br).select(_br.id).where(_br.id == P()).get_sql(),
        (route_id,)
    ).fetchone():
        err(f"Bus route {route_id} not found")

    stop_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_bus_stop", {
        "id": P(), "route_id": P(), "stop_order": P(),
        "stop_name": P(), "address": P(),
        "am_pickup_time": P(), "pm_dropoff_time": P(),
        "created_at": P(),
    })
    conn.execute(sql,
        (stop_id, route_id, int(stop_order), stop_name,
         getattr(args, "address", None) or "",
         getattr(args, "am_pickup_time", None) or "",
         getattr(args, "pm_dropoff_time", None) or "",
         now)
    )

    audit(conn, SKILL, "edu-add-bus-stop", "educlaw_bus_stop", stop_id,
          new_values={"stop_name": stop_name, "route_id": route_id})
    conn.commit()
    ok({"id": stop_id, "route_id": route_id, "stop_order": int(stop_order),
        "stop_name": stop_name})


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT TRANSPORT ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

def assign_student_transport(conn, args):
    """Assign a student to a bus route (and optionally a stop)."""
    student_id = getattr(args, "student_id", None)
    route_id = getattr(args, "route_id", None)

    if not student_id:
        err("--student-id is required")
    if not route_id:
        err("--route-id is required")

    _st = Table("educlaw_student")
    if not conn.execute(
        Q.from_(_st).select(_st.id).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone():
        err(f"Student {student_id} not found")

    _br = Table("educlaw_bus_route")
    if not conn.execute(
        Q.from_(_br).select(_br.id).where(_br.id == P()).get_sql(),
        (route_id,)
    ).fetchone():
        err(f"Bus route {route_id} not found")

    bus_stop_id = getattr(args, "bus_stop_id", None)
    if bus_stop_id:
        _bs = Table("educlaw_bus_stop")
        if not conn.execute(
            Q.from_(_bs).select(_bs.id).where(_bs.id == P()).get_sql(),
            (bus_stop_id,)
        ).fetchone():
            err(f"Bus stop {bus_stop_id} not found")

    transport_type = getattr(args, "transport_type", None) or "both"
    if transport_type not in VALID_TRANSPORT_TYPES:
        err(f"--transport-type must be one of: {', '.join(VALID_TRANSPORT_TYPES)}")

    assign_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_student_transport", {
        "id": P(), "student_id": P(), "route_id": P(),
        "bus_stop_id": P(), "transport_type": P(),
        "special_needs_notes": P(), "effective_date": P(),
        "end_date": P(), "status": P(),
        "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql,
        (assign_id, student_id, route_id, bus_stop_id,
         transport_type,
         getattr(args, "special_needs_notes", None) or "",
         getattr(args, "effective_date", None) or "",
         None, "active", now, now)
    )

    audit(conn, SKILL, "edu-assign-student-transport", "educlaw_student_transport",
          assign_id,
          new_values={"student_id": student_id, "route_id": route_id})
    conn.commit()
    ok({"id": assign_id, "student_id": student_id, "route_id": route_id,
        "bus_stop_id": bus_stop_id, "transport_type": transport_type,
        "transport_status": "active"})


# ─────────────────────────────────────────────────────────────────────────────
# LIST STUDENT TRANSPORT
# ─────────────────────────────────────────────────────────────────────────────

def list_student_transport(conn, args):
    """List transport assignments. Filter by --route-id or --student-id."""
    route_id = getattr(args, "route_id", None)
    student_id = getattr(args, "student_id", None)

    if not route_id and not student_id:
        err("At least one of --route-id or --student-id is required")

    _tr = Table("educlaw_student_transport")
    _br = Table("educlaw_bus_route")
    _bs = Table("educlaw_bus_stop")
    _st = Table("educlaw_student")

    q = (Q.from_(_tr)
         .join(_br).on(_br.id == _tr.route_id)
         .join(_st).on(_st.id == _tr.student_id)
         .left_join(_bs).on(_bs.id == _tr.bus_stop_id)
         .select(
             _tr.star,
             _br.route_number, _br.route_name,
             _st.full_name.as_("student_name"), _st.grade_level,
             _bs.stop_name,
         ))
    params = []

    if route_id:
        q = q.where(_tr.route_id == P()); params.append(route_id)
    if student_id:
        q = q.where(_tr.student_id == P()); params.append(student_id)

    q = q.orderby(_st.last_name).orderby(_st.first_name)
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"transport_assignments": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# BUS ROSTER
# ─────────────────────────────────────────────────────────────────────────────

def bus_roster(conn, args):
    """Full roster for a route: students, stops, guardian contacts."""
    route_id = getattr(args, "route_id", None)
    if not route_id:
        err("--route-id is required")

    _br = Table("educlaw_bus_route")
    route_row = conn.execute(
        Q.from_(_br).select(_br.star).where(_br.id == P()).get_sql(),
        (route_id,)
    ).fetchone()
    if not route_row:
        err(f"Bus route {route_id} not found")

    route_info = dict(route_row)

    # Get all students on this route
    _tr = Table("educlaw_student_transport")
    _st = Table("educlaw_student")
    _bs = Table("educlaw_bus_stop")

    students = conn.execute(
        Q.from_(_tr)
        .join(_st).on(_st.id == _tr.student_id)
        .left_join(_bs).on(_bs.id == _tr.bus_stop_id)
        .select(
            _st.id.as_("student_id"), _st.full_name, _st.grade_level,
            _st.phone.as_("student_phone"),
            _tr.transport_type, _tr.special_needs_notes,
            _bs.stop_name, _bs.stop_order,
            _bs.am_pickup_time, _bs.pm_dropoff_time,
        )
        .where(_tr.route_id == P())
        .where(_tr.status == "active")
        .orderby(_bs.stop_order)
        .orderby(_st.last_name)
        .get_sql(),
        (route_id,)
    ).fetchall()

    # Enrich with guardian contact info
    _sg = Table("educlaw_student_guardian")
    _g = Table("educlaw_guardian")
    roster = []
    for stu in students:
        s = dict(stu)
        guardians = conn.execute(
            Q.from_(_sg)
            .join(_g).on(_g.id == _sg.guardian_id)
            .select(
                _g.full_name.as_("guardian_name"),
                _g.phone.as_("guardian_phone"),
                _g.email.as_("guardian_email"),
                _sg.relationship, _sg.is_emergency_contact,
            )
            .where(_sg.student_id == P())
            .orderby(_sg.is_primary_contact, order=Order.desc)
            .get_sql(),
            (s["student_id"],)
        ).fetchall()
        s["guardians"] = [dict(g) for g in guardians]
        roster.append(s)

    ok({"route_id": route_id, "route_number": route_info.get("route_number"),
        "route_name": route_info.get("route_name"),
        "driver_name": route_info.get("driver_name"),
        "driver_phone": route_info.get("driver_phone"),
        "roster": roster, "student_count": len(roster)})


# ─────────────────────────────────────────────────────────────────────────────
# TRANSPORT REPORT
# ─────────────────────────────────────────────────────────────────────────────

def transport_report(conn, args):
    """Transport summary: route count, students transported, capacity utilization."""
    school_id = getattr(args, "school_id", None)
    if not school_id:
        err("--school-id is required")

    _br = Table("educlaw_bus_route")
    routes = conn.execute(
        Q.from_(_br).select(_br.star)
        .where(_br.school_id == P())
        .where(_br.status == "active")
        .orderby(_br.route_number)
        .get_sql(),
        (school_id,)
    ).fetchall()

    _tr = Table("educlaw_student_transport")
    route_details = []
    total_students = 0
    total_capacity = 0

    for route in routes:
        r = dict(route)
        student_count = conn.execute(
            Q.from_(_tr).select(fn.Count(_tr.id))
            .where(_tr.route_id == P())
            .where(_tr.status == "active")
            .get_sql(),
            (r["id"],)
        ).fetchone()[0]

        cap = r.get("capacity") or 0
        utilization = 0
        if cap > 0:
            utilization = round(student_count / cap * 100, 1)

        route_details.append({
            "route_id": r["id"],
            "route_number": r["route_number"],
            "route_name": r.get("route_name", ""),
            "driver_name": r.get("driver_name", ""),
            "capacity": cap,
            "students_assigned": student_count,
            "utilization_pct": utilization,
        })
        total_students += student_count
        total_capacity += cap

    overall_utilization = 0
    if total_capacity > 0:
        overall_utilization = round(total_students / total_capacity * 100, 1)

    ok({"school_id": school_id,
        "total_routes": len(routes),
        "total_students_transported": total_students,
        "total_capacity": total_capacity,
        "overall_utilization_pct": overall_utilization,
        "routes": route_details})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-bus-route": add_bus_route,
    "edu-update-bus-route": update_bus_route,
    "edu-list-bus-routes": list_bus_routes,
    "edu-add-bus-stop": add_bus_stop,
    "edu-assign-student-transport": assign_student_transport,
    "edu-list-student-transport": list_student_transport,
    "edu-bus-roster": bus_roster,
    "edu-transport-report": transport_report,
}
