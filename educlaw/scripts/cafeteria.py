"""EduClaw — cafeteria domain module (Meal Management / NSLP)

8 actions for USDA National School Lunch Program compliance:
meal plans, daily counts, student meal records, participation reporting,
USDA reimbursement claim calculation, and allergen alerts.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

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

VALID_PLAN_TYPES = ("free", "reduced", "paid")
VALID_MEAL_TYPES = ("breakfast", "lunch", "snack")
VALID_ELIGIBILITIES = ("free", "reduced", "paid")

# USDA NSLP reimbursement rates (SY 2025-26 approximate)
USDA_RATES = {
    "free_lunch": Decimal("4.36"),
    "reduced_lunch": Decimal("3.96"),
    "regular_lunch": Decimal("0.53"),
    "free_breakfast": Decimal("2.28"),
    "reduced_breakfast": Decimal("1.98"),
    "regular_breakfast": Decimal("0.36"),
}


def _d(val, default="0"):
    try:
        return Decimal(str(val)) if val not in (None, "", "None") else Decimal(default)
    except (InvalidOperation, Exception):
        return Decimal(default)


# ─────────────────────────────────────────────────────────────────────────────
# MEAL PLAN
# ─────────────────────────────────────────────────────────────────────────────

def add_meal_plan(conn, args):
    """Create a meal plan for a school."""
    school_id = getattr(args, "school_id", None)
    plan_type = getattr(args, "plan_type", None)
    daily_rate = getattr(args, "daily_rate", None)
    academic_year = getattr(args, "academic_year", None)

    if not school_id:
        err("--school-id is required")
    if not plan_type:
        err("--plan-type is required (free, reduced, paid)")
    if plan_type not in VALID_PLAN_TYPES:
        err(f"--plan-type must be one of: {', '.join(VALID_PLAN_TYPES)}")
    if not daily_rate:
        err("--daily-rate is required")
    if _d(daily_rate) < 0:
        err("--daily-rate must be >= 0")
    if not academic_year:
        err("--academic-year is required")

    plan_id = str(uuid.uuid4())
    now = _now_iso()
    description = getattr(args, "description", None) or ""

    sql, _ = insert_row("educlaw_meal_plan", {
        "id": P(), "school_id": P(), "academic_year": P(),
        "plan_type": P(), "daily_rate": P(), "description": P(),
        "status": P(), "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql,
        (plan_id, school_id, academic_year, plan_type,
         str(_d(daily_rate)), description, "active", now, now)
    )

    audit(conn, SKILL, "edu-add-meal-plan", "educlaw_meal_plan", plan_id,
          new_values={"plan_type": plan_type, "daily_rate": str(_d(daily_rate))})
    conn.commit()
    ok({"id": plan_id, "school_id": school_id, "plan_type": plan_type,
        "daily_rate": str(_d(daily_rate)), "academic_year": academic_year})


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT MEAL ELIGIBILITY
# ─────────────────────────────────────────────────────────────────────────────

def update_student_meal_eligibility(conn, args):
    """Update a student's meal eligibility (free/reduced/paid)."""
    student_id = getattr(args, "student_id", None)
    eligibility = getattr(args, "eligibility", None)

    if not student_id:
        err("--student-id is required")
    if not eligibility:
        err("--eligibility is required (free, reduced, paid)")
    if eligibility not in VALID_ELIGIBILITIES:
        err(f"--eligibility must be one of: {', '.join(VALID_ELIGIBILITIES)}")

    _st = Table("educlaw_student")
    student_row = conn.execute(
        Q.from_(_st).select(_st.id).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")

    # Store eligibility in a meal record context — the student table
    # doesn't have a meal_eligibility column, so we record this as a
    # notification/audit trail. The eligibility is tracked per-meal-record.
    now = _now_iso()
    audit(conn, SKILL, "edu-update-student-meal-eligibility",
          "educlaw_student", student_id,
          new_values={"meal_eligibility": eligibility})
    conn.commit()
    ok({"student_id": student_id, "eligibility": eligibility,
        "updated_at": now})


# ─────────────────────────────────────────────────────────────────────────────
# DAILY MEAL COUNT
# ─────────────────────────────────────────────────────────────────────────────

def record_daily_meal_count(conn, args):
    """Record daily meal counts by category for NSLP reporting."""
    school_id = getattr(args, "school_id", None)
    count_date = getattr(args, "count_date", None)

    if not school_id:
        err("--school-id is required")
    if not count_date:
        err("--count-date is required")

    count_id = str(uuid.uuid4())
    now = _now_iso()

    free_breakfast = int(getattr(args, "free_breakfast", None) or 0)
    reduced_breakfast = int(getattr(args, "reduced_breakfast", None) or 0)
    regular_breakfast = int(getattr(args, "regular_breakfast", None) or 0)
    free_lunch = int(getattr(args, "free_lunch", None) or 0)
    reduced_lunch = int(getattr(args, "reduced_lunch", None) or 0)
    regular_lunch = int(getattr(args, "regular_lunch", None) or 0)
    adult_meals = int(getattr(args, "adult_meals", None) or 0)
    snack_count = int(getattr(args, "snack_count", None) or 0)
    counted_by = getattr(args, "counted_by", None) or ""
    notes = getattr(args, "notes", None) or ""

    try:
        sql, _ = insert_row("educlaw_daily_meal_count", {
            "id": P(), "school_id": P(), "count_date": P(),
            "free_breakfast": P(), "reduced_breakfast": P(), "regular_breakfast": P(),
            "free_lunch": P(), "reduced_lunch": P(), "regular_lunch": P(),
            "adult_meals": P(), "snack_count": P(),
            "counted_by": P(), "notes": P(), "created_at": P(),
        })
        conn.execute(sql,
            (count_id, school_id, count_date,
             free_breakfast, reduced_breakfast, regular_breakfast,
             free_lunch, reduced_lunch, regular_lunch,
             adult_meals, snack_count, counted_by, notes, now)
        )
    except sqlite3.IntegrityError:
        err(f"Meal count already recorded for {school_id} on {count_date}")

    conn.commit()
    total = (free_breakfast + reduced_breakfast + regular_breakfast +
             free_lunch + reduced_lunch + regular_lunch + adult_meals + snack_count)
    ok({"id": count_id, "school_id": school_id, "count_date": count_date,
        "total_meals": total})


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT MEAL RECORD
# ─────────────────────────────────────────────────────────────────────────────

def record_student_meal(conn, args):
    """Record an individual student meal served."""
    student_id = getattr(args, "student_id", None)
    meal_date = getattr(args, "meal_date", None)
    meal_type = getattr(args, "meal_type", None)
    eligibility = getattr(args, "eligibility", None)

    if not student_id:
        err("--student-id is required")
    if not meal_date:
        err("--meal-date is required")
    if not meal_type:
        err("--meal-type is required (breakfast, lunch, snack)")
    if meal_type not in VALID_MEAL_TYPES:
        err(f"--meal-type must be one of: {', '.join(VALID_MEAL_TYPES)}")
    if not eligibility:
        err("--eligibility is required (free, reduced, paid)")
    if eligibility not in VALID_ELIGIBILITIES:
        err(f"--eligibility must be one of: {', '.join(VALID_ELIGIBILITIES)}")

    _st = Table("educlaw_student")
    if not conn.execute(
        Q.from_(_st).select(_st.id).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone():
        err(f"Student {student_id} not found")

    record_id = str(uuid.uuid4())
    now = _now_iso()
    allergen_alert = int(getattr(args, "allergen_alert", None) or 0)
    served_by = getattr(args, "served_by", None) or ""

    sql, _ = insert_row("educlaw_student_meal_record", {
        "id": P(), "student_id": P(), "meal_date": P(),
        "meal_type": P(), "eligibility": P(),
        "allergen_alert": P(), "served_by": P(), "created_at": P(),
    })
    conn.execute(sql,
        (record_id, student_id, meal_date, meal_type, eligibility,
         allergen_alert, served_by, now)
    )
    conn.commit()
    ok({"id": record_id, "student_id": student_id, "meal_date": meal_date,
        "meal_type": meal_type, "eligibility": eligibility,
        "allergen_alert": bool(allergen_alert)})


# ─────────────────────────────────────────────────────────────────────────────
# MEAL RECORDS LIST
# ─────────────────────────────────────────────────────────────────────────────

def list_meal_records(conn, args):
    """List student meal records with optional filters."""
    school_id = getattr(args, "school_id", None)
    if not school_id:
        err("--school-id is required")

    _mr = Table("educlaw_student_meal_record")
    _st = Table("educlaw_student")

    q = (Q.from_(_mr)
         .join(_st).on(_st.id == _mr.student_id)
         .select(_mr.star, _st.full_name.as_("student_name"),
                 _st.grade_level)
         .where(_st.company_id == P()))
    params = [school_id]

    if getattr(args, "date_from", None):
        q = q.where(_mr.meal_date >= P()); params.append(args.date_from)
    if getattr(args, "date_to", None):
        q = q.where(_mr.meal_date <= P()); params.append(args.date_to)
    if getattr(args, "student_id", None):
        q = q.where(_mr.student_id == P()); params.append(args.student_id)

    q = q.orderby(_mr.meal_date, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"school_id": school_id, "meal_records": [dict(r) for r in rows],
        "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# MEAL PARTICIPATION REPORT
# ─────────────────────────────────────────────────────────────────────────────

def meal_participation_report(conn, args):
    """Daily counts by category for a given month (NSLP reporting)."""
    school_id = getattr(args, "school_id", None)
    month = getattr(args, "month", None)  # YYYY-MM format

    if not school_id:
        err("--school-id is required")
    if not month:
        err("--month is required (YYYY-MM format)")

    _dmc = Table("educlaw_daily_meal_count")
    month_start = f"{month}-01"
    # Calculate month end
    try:
        y, m = int(month[:4]), int(month[5:7])
        if m == 12:
            month_end = f"{y + 1}-01-01"
        else:
            month_end = f"{y}-{m + 1:02d}-01"
    except (ValueError, IndexError):
        err("--month must be in YYYY-MM format")

    rows = conn.execute(
        Q.from_(_dmc).select(_dmc.star)
        .where(_dmc.school_id == P())
        .where(_dmc.count_date >= P())
        .where(_dmc.count_date < P())
        .orderby(_dmc.count_date)
        .get_sql(),
        (school_id, month_start, month_end)
    ).fetchall()

    # Aggregate totals
    totals = {
        "free_breakfast": 0, "reduced_breakfast": 0, "regular_breakfast": 0,
        "free_lunch": 0, "reduced_lunch": 0, "regular_lunch": 0,
        "adult_meals": 0, "snack_count": 0,
    }
    for row in rows:
        r = dict(row)
        for key in totals:
            totals[key] += r.get(key, 0) or 0

    totals["total_breakfast"] = totals["free_breakfast"] + totals["reduced_breakfast"] + totals["regular_breakfast"]
    totals["total_lunch"] = totals["free_lunch"] + totals["reduced_lunch"] + totals["regular_lunch"]

    ok({"school_id": school_id, "month": month,
        "daily_counts": [dict(r) for r in rows],
        "days_reported": len(rows),
        "totals": totals})


# ─────────────────────────────────────────────────────────────────────────────
# USDA CLAIM REPORT
# ─────────────────────────────────────────────────────────────────────────────

def usda_claim_report(conn, args):
    """NSLP reimbursement calculation: count x rate per category for a month."""
    school_id = getattr(args, "school_id", None)
    month = getattr(args, "month", None)

    if not school_id:
        err("--school-id is required")
    if not month:
        err("--month is required (YYYY-MM format)")

    _dmc = Table("educlaw_daily_meal_count")
    month_start = f"{month}-01"
    try:
        y, m = int(month[:4]), int(month[5:7])
        if m == 12:
            month_end = f"{y + 1}-01-01"
        else:
            month_end = f"{y}-{m + 1:02d}-01"
    except (ValueError, IndexError):
        err("--month must be in YYYY-MM format")

    rows = conn.execute(
        Q.from_(_dmc).select(_dmc.star)
        .where(_dmc.school_id == P())
        .where(_dmc.count_date >= P())
        .where(_dmc.count_date < P())
        .get_sql(),
        (school_id, month_start, month_end)
    ).fetchall()

    # Sum counts
    counts = {
        "free_lunch": 0, "reduced_lunch": 0, "regular_lunch": 0,
        "free_breakfast": 0, "reduced_breakfast": 0, "regular_breakfast": 0,
    }
    for row in rows:
        r = dict(row)
        for key in counts:
            counts[key] += r.get(key, 0) or 0

    # Calculate reimbursement
    claim_items = []
    total_claim = Decimal("0")
    for category, count in counts.items():
        rate = USDA_RATES.get(category, Decimal("0"))
        amount = (Decimal(str(count)) * rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        claim_items.append({
            "category": category,
            "count": count,
            "rate": str(rate),
            "amount": str(amount),
        })
        total_claim += amount

    ok({"school_id": school_id, "month": month,
        "claim_items": claim_items,
        "total_claim": str(total_claim),
        "days_in_report": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ALLERGEN ALERT LIST
# ─────────────────────────────────────────────────────────────────────────────

def allergen_alert_list(conn, args):
    """Students with active allergen alerts for today's meals."""
    school_id = getattr(args, "school_id", None)
    if not school_id:
        err("--school-id is required")

    today = date.today().isoformat()

    _mr = Table("educlaw_student_meal_record")
    _st = Table("educlaw_student")

    rows = conn.execute(
        Q.from_(_mr)
        .join(_st).on(_st.id == _mr.student_id)
        .select(
            _mr.id.as_("record_id"), _mr.meal_type, _mr.eligibility,
            _st.id.as_("student_id"), _st.full_name.as_("student_name"),
            _st.grade_level,
        )
        .where(_st.company_id == P())
        .where(_mr.meal_date == P())
        .where(_mr.allergen_alert == 1)
        .orderby(_st.last_name).orderby(_st.first_name)
        .get_sql(),
        (school_id, today)
    ).fetchall()

    ok({"school_id": school_id, "date": today,
        "allergen_alerts": [dict(r) for r in rows],
        "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-meal-plan": add_meal_plan,
    "edu-update-student-meal-eligibility": update_student_meal_eligibility,
    "edu-record-daily-meal-count": record_daily_meal_count,
    "edu-record-student-meal": record_student_meal,
    "edu-list-meal-records": list_meal_records,
    "edu-meal-participation-report": meal_participation_report,
    "edu-usda-claim-report": usda_claim_report,
    "edu-allergen-alert-list": allergen_alert_list,
}
