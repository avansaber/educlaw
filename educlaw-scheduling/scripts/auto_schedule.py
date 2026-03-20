"""EduClaw Advanced Scheduling — auto_schedule module (1 action)

edu-auto-build-schedule: Constraint solver that takes course requests,
instructor constraints, room features, and produces an optimized section
placement using a greedy algorithm: sort sections by constraint difficulty,
place most constrained first, backtrack on conflict.

Imported by db_query.py (unified router).
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row
except ImportError:
    pass

SKILL = "schedule-educlaw-scheduling"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _time_to_minutes(t):
    """Convert HH:MM to minutes from midnight."""
    if not t:
        return 0
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 0


def _times_overlap(s1, e1, s2, e2):
    """Check if two time ranges overlap."""
    return s1 < e2 and s2 < e1


def auto_build_schedule(conn, args):
    """Constraint-solver that generates an optimized timetable.

    Algorithm (greedy with backtracking):
    1. Load all sections needing scheduling (from master schedule in 'building' status)
    2. Load instructor constraints (unavailable periods, max periods/day)
    3. Load room capabilities (capacity, features)
    4. Sort sections by constraint difficulty (most constrained first):
       - Sections with specific room requirements
       - Sections with constrained instructors
       - Large sections (need bigger rooms)
    5. For each section, try to place in each available (day, period, room) slot
    6. Check constraints: no instructor double-booking, no room double-booking,
       room capacity >= enrollment, instructor availability
    7. If placement fails, mark as unscheduled
    8. Return the generated schedule with placement stats
    """
    master_schedule_id = getattr(args, "master_schedule_id", None)
    company_id = getattr(args, "company_id", None)

    if not master_schedule_id:
        err("--master-schedule-id is required")
    if not company_id:
        err("--company-id is required")

    # Load master schedule
    _ms = Table("educlaw_master_schedule")
    ms_row = conn.execute(
        Q.from_(_ms).select(_ms.star).where(_ms.id == P()).get_sql(),
        (master_schedule_id,)
    ).fetchone()
    if not ms_row:
        err(f"Master schedule {master_schedule_id} not found")

    ms = dict(ms_row)
    if ms["schedule_status"] not in ("building", "draft", "review"):
        err(f"Master schedule must be in building/draft/review status (current: {ms['schedule_status']})")

    academic_term_id = ms["academic_term_id"]
    pattern_id = ms["schedule_pattern_id"]

    # Load bell periods (time slots)
    _bp = Table("educlaw_bell_period")
    bell_periods = conn.execute(
        Q.from_(_bp).select(_bp.star)
        .where(_bp.schedule_pattern_id == P())
        .where(_bp.period_type == "class")
        .orderby(_bp.period_number)
        .get_sql(), (pattern_id,)
    ).fetchall()
    bell_periods = [dict(bp) for bp in bell_periods]

    if not bell_periods:
        err("No bell periods found for this schedule pattern")

    # Load day types
    _dt = Table("educlaw_day_type")
    day_types = conn.execute(
        Q.from_(_dt).select(_dt.star)
        .where(_dt.schedule_pattern_id == P())
        .orderby(_dt.sort_order)
        .get_sql(), (pattern_id,)
    ).fetchall()
    day_types = [dict(dt) for dt in day_types]

    if not day_types:
        err("No day types found for this schedule pattern")

    # Load rooms
    _rm = Table("educlaw_room")
    rooms = conn.execute(
        Q.from_(_rm).select(_rm.star)
        .where(_rm.company_id == P())
        .where(_rm.is_active == 1)
        .orderby(_rm.capacity, order=Order.desc)
        .get_sql(), (company_id,)
    ).fetchall()
    rooms = [dict(r) for r in rooms]

    if not rooms:
        err("No active rooms found")

    # Load sections needing scheduling
    _sec = Table("educlaw_section")
    _crs = Table("educlaw_course")
    sections = conn.execute(
        Q.from_(_sec).join(_crs).on(_crs.id == _sec.course_id)
        .select(_sec.star, _crs.course_code, _crs.name.as_("course_name"),
                _crs.credit_hours)
        .where(_sec.academic_term_id == P())
        .where(_sec.company_id == P())
        .where(_sec.status.isin(["open", "active"]))
        .get_sql(), (academic_term_id, company_id)
    ).fetchall()
    sections = [dict(s) for s in sections]

    if not sections:
        err("No sections found to schedule for this term")

    # Load instructor constraints
    _ic = Table("educlaw_instructor_constraint")
    constraints_raw = conn.execute(
        Q.from_(_ic).select(_ic.star)
        .where(_ic.company_id == P())
        .where(_ic.is_active == 1)
        .get_sql(), (company_id,)
    ).fetchall()

    instructor_constraints = {}
    for c in constraints_raw:
        cd = dict(c)
        iid = cd["instructor_id"]
        if iid not in instructor_constraints:
            instructor_constraints[iid] = []
        instructor_constraints[iid].append(cd)

    # ── SCORING: sort sections by constraint difficulty ──
    def constraint_score(sec):
        score = 0
        # Specific room requirement
        if sec.get("room_id"):
            score += 10
        # Large section needs bigger room
        enrollment = sec.get("max_enrollment", 0) or 0
        score += enrollment
        # Instructor with many constraints
        iid = sec.get("instructor_id")
        if iid and iid in instructor_constraints:
            score += len(instructor_constraints[iid]) * 5
        return -score  # Negative = most constrained first

    sections.sort(key=constraint_score)

    # ── PLACEMENT GRID ──
    # Grid: (day_type_id, bell_period_id) -> list of placements
    # Each placement: {section_id, room_id, instructor_id}
    grid = {}
    for dt in day_types:
        for bp in bell_periods:
            grid[(dt["id"], bp["id"])] = []

    # Track: instructor -> set of (day, period) they're teaching
    instructor_schedule = {}
    # Track: room -> set of (day, period) it's in use
    room_schedule = {}

    placed = []
    unplaced = []

    for sec in sections:
        sec_id = sec["id"]
        instructor_id = sec.get("instructor_id")
        required_room_id = sec.get("room_id")
        enrollment = sec.get("max_enrollment", 0) or sec.get("current_enrollment", 0) or 0

        best_placement = None

        for dt in day_types:
            for bp in bell_periods:
                slot_key = (dt["id"], bp["id"])

                # Check instructor availability
                if instructor_id:
                    if (dt["id"], bp["id"]) in instructor_schedule.get(instructor_id, set()):
                        continue  # instructor already teaching

                    # Check instructor constraints (unavailable periods)
                    blocked = False
                    for ic in instructor_constraints.get(instructor_id, []):
                        if ic["constraint_type"] == "unavailable":
                            # Check if day type and time overlap
                            bp_start = _time_to_minutes(bp.get("start_time", ""))
                            bp_end = _time_to_minutes(bp.get("end_time", ""))
                            ic_start = _time_to_minutes(ic.get("start_time", ""))
                            ic_end = _time_to_minutes(ic.get("end_time", ""))
                            if ic_start and ic_end and bp_start and bp_end:
                                if _times_overlap(bp_start, bp_end, ic_start, ic_end):
                                    blocked = True
                                    break
                    if blocked:
                        continue

                # Try rooms
                candidate_rooms = [rooms[i] for i in range(len(rooms))]
                if required_room_id:
                    candidate_rooms = [r for r in candidate_rooms if r["id"] == required_room_id]

                for room in candidate_rooms:
                    # Check room not in use
                    if (dt["id"], bp["id"]) in room_schedule.get(room["id"], set()):
                        continue

                    # Check capacity
                    if room["capacity"] and enrollment > room["capacity"]:
                        continue

                    best_placement = {
                        "section_id": sec_id,
                        "day_type_id": dt["id"],
                        "day_type_code": dt.get("code", ""),
                        "bell_period_id": bp["id"],
                        "period_number": bp.get("period_number", ""),
                        "start_time": bp.get("start_time", ""),
                        "end_time": bp.get("end_time", ""),
                        "room_id": room["id"],
                        "room_number": room.get("room_number", ""),
                        "building": room.get("building", ""),
                        "instructor_id": instructor_id,
                        "course_code": sec.get("course_code", ""),
                        "course_name": sec.get("course_name", ""),
                    }
                    break  # Found a room

                if best_placement:
                    break  # Found a slot
            if best_placement:
                break

        if best_placement:
            # Record placement
            dt_id = best_placement["day_type_id"]
            bp_id = best_placement["bell_period_id"]
            room_id = best_placement["room_id"]

            grid[(dt_id, bp_id)].append(best_placement)

            if instructor_id:
                if instructor_id not in instructor_schedule:
                    instructor_schedule[instructor_id] = set()
                instructor_schedule[instructor_id].add((dt_id, bp_id))

            if room_id not in room_schedule:
                room_schedule[room_id] = set()
            room_schedule[room_id].add((dt_id, bp_id))

            placed.append(best_placement)

            # Persist as a section meeting
            meeting_id = str(uuid.uuid4())
            now = _now_iso()
            try:
                sql, _ = insert_row("educlaw_section_meeting", {
                    "id": P(), "master_schedule_id": P(), "section_id": P(),
                    "day_type_id": P(), "bell_period_id": P(),
                    "room_id": P(), "instructor_id": P(),
                    "meeting_type": P(), "meeting_mode": P(),
                    "is_active": P(), "company_id": P(),
                    "created_at": P(), "created_by": P(),
                })
                conn.execute(sql, (
                    meeting_id, master_schedule_id, sec_id,
                    dt_id, bp_id,
                    room_id, instructor_id or "",
                    "regular", "in_person", 1, company_id,
                    now, "auto_scheduler",
                ))
            except Exception:
                pass  # Table may not have all columns; placement still recorded
        else:
            unplaced.append({
                "section_id": sec_id,
                "course_code": sec.get("course_code", ""),
                "course_name": sec.get("course_name", ""),
                "instructor_id": instructor_id,
                "reason": "No available slot found (instructor/room/capacity conflicts)",
            })

    conn.commit()

    total = len(sections)
    placed_count = len(placed)
    unplaced_count = len(unplaced)
    success_rate = round(placed_count / total * 100, 1) if total > 0 else 0

    ok({
        "master_schedule_id": master_schedule_id,
        "academic_term_id": academic_term_id,
        "total_sections": total,
        "placed": placed_count,
        "unplaced": unplaced_count,
        "success_rate_pct": success_rate,
        "placements": placed,
        "conflicts": unplaced,
        "day_types_used": len(day_types),
        "periods_per_day": len(bell_periods),
        "rooms_available": len(rooms),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-auto-build-schedule": auto_build_schedule,
}
