"""EduClaw — grading domain module

Actions for grading: grading scales, assessment plans, grade calculation,
grade submission (immutable), GPA calculation, transcripts, report cards.

Imported by db_query.py (unified router).
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, Case, LiteralValue
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _d(val, default="0"):
    """Safe Decimal conversion."""
    try:
        return Decimal(str(val)) if val not in (None, "", "None") else Decimal(default)
    except (InvalidOperation, Exception):
        return Decimal(default)


def _log_data_access_internal(conn, user_id, student_id, data_category,
                               access_type, access_reason, company_id):
    log_id = str(uuid.uuid4())
    try:
        sql, _ = insert_row("educlaw_data_access_log", {"id": P(), "user_id": P(), "student_id": P(), "data_category": P(), "access_type": P(), "access_reason": P(), "is_emergency_access": P(), "ip_address": P(), "company_id": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (log_id, user_id, student_id, data_category, access_type,
             access_reason, 0, "", company_id, _now_iso(), user_id)
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# GRADING SCALE
# ─────────────────────────────────────────────────────────────────────────────

def add_grading_scale(conn, args):
    name = getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)
    entries_json = getattr(args, "entries", None)

    if not name:
        err("--name is required")
    if not company_id:
        err("--company-id is required")
    if not entries_json:
        err("--entries is required (JSON array of grade entries)")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    try:
        entries = json.loads(entries_json) if isinstance(entries_json, str) else entries_json
        if not isinstance(entries, list) or not entries:
            err("--entries must be a non-empty JSON array")
    except (json.JSONDecodeError, TypeError):
        err("--entries must be valid JSON array")

    is_default = int(getattr(args, "is_default", None) or 0)

    scale_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_grading_scale", {"id": P(), "name": P(), "description": P(), "is_default": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (scale_id, name, getattr(args, "description", None) or "",
             is_default, company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Grading scale '{name}' already exists for this company")

    # If setting as default, clear other defaults
    if is_default:
        _gs2 = Table("educlaw_grading_scale")
        conn.execute(
            Q.update(_gs2).set(_gs2.is_default, 0)
            .where(_gs2.company_id == P()).where(_gs2.id != P())
            .get_sql(),
            (company_id, scale_id)
        )

    # Insert entries
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        entry_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_grading_scale_entry", {"id": P(), "grading_scale_id": P(), "letter_grade": P(), "grade_points": P(), "min_percentage": P(), "max_percentage": P(), "description": P(), "is_passing": P(), "counts_in_gpa": P(), "sort_order": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (entry_id, scale_id,
             entry.get("letter_grade", ""),
             str(_d(entry.get("grade_points", "0"))),
             str(_d(entry.get("min_percentage", "0"))),
             str(_d(entry.get("max_percentage", "0"))),
             entry.get("description", ""),
             int(entry.get("is_passing", 1)),
             int(entry.get("counts_in_gpa", 1)),
             entry.get("sort_order", i + 1),
             now, getattr(args, "user_id", None) or "")
        )

    audit(conn, SKILL, "edu-add-grading-scale", "educlaw_grading_scale", scale_id,
          new_values={"name": name, "entry_count": len(entries)})
    conn.commit()
    ok({"id": scale_id, "name": name, "is_default": is_default, "entry_count": len(entries)})


def update_grading_scale(conn, args):
    scale_id = getattr(args, "scale_id", None)
    if not scale_id:
        err("--scale-id is required")

    row = conn.execute(Q.from_(Table("educlaw_grading_scale")).select(Table("educlaw_grading_scale").star).where(Field("id") == P()).get_sql(), (scale_id,)).fetchone()
    if not row:
        err(f"Grading scale {scale_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "description", None) is not None:
        updates.append("description = ?"); params.append(args.description); changed.append("description")
    if getattr(args, "is_default", None) is not None:
        updates.append("is_default = ?"); params.append(int(args.is_default)); changed.append("is_default")

    if getattr(args, "is_default", None) and int(args.is_default):
        r = dict(row)
        _gs2 = Table("educlaw_grading_scale")
        conn.execute(
            Q.update(_gs2).set(_gs2.is_default, 0)
            .where(_gs2.company_id == P()).where(_gs2.id != P())
            .get_sql(),
            (r["company_id"], scale_id)
        )

    # Replace entries if provided
    entries_json = getattr(args, "entries", None)
    if entries_json:
        try:
            entries = json.loads(entries_json) if isinstance(entries_json, str) else entries_json
        except Exception:
            err("--entries must be valid JSON array")

        _gse = Table("educlaw_grading_scale_entry")
        conn.execute(Q.from_(_gse).delete().where(_gse.grading_scale_id == P()).get_sql(), (scale_id,))
        now = _now_iso()
        for i, entry in enumerate(entries):
            entry_id = str(uuid.uuid4())
            sql, _ = insert_row("educlaw_grading_scale_entry", {"id": P(), "grading_scale_id": P(), "letter_grade": P(), "grade_points": P(), "min_percentage": P(), "max_percentage": P(), "description": P(), "is_passing": P(), "counts_in_gpa": P(), "sort_order": P(), "created_at": P(), "created_by": P()})

            conn.execute(sql,
                (entry_id, scale_id,
                 entry.get("letter_grade", ""),
                 str(_d(entry.get("grade_points", "0"))),
                 str(_d(entry.get("min_percentage", "0"))),
                 str(_d(entry.get("max_percentage", "0"))),
                 entry.get("description", ""),
                 int(entry.get("is_passing", 1)),
                 int(entry.get("counts_in_gpa", 1)),
                 entry.get("sort_order", i + 1),
                 now, getattr(args, "user_id", None) or "")
            )
        changed.append("entries")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(scale_id)
    if updates[:-1]:  # Only update if there are non-timestamp changes
        conn.execute(  # PyPika: skipped — dynamic column set built conditionally
            f"UPDATE educlaw_grading_scale SET {', '.join(updates)} WHERE id = ?", params)

    audit(conn, SKILL, "edu-update-grading-scale", "educlaw_grading_scale", scale_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": scale_id, "updated_fields": changed})


def list_grading_scales(conn, args):
    _gs = Table("educlaw_grading_scale")
    q = Q.from_(_gs).select(_gs.star)
    params = []

    if getattr(args, "company_id", None):
        q = q.where(_gs.company_id == P()); params.append(args.company_id)
    if getattr(args, "is_default", None) is not None:
        q = q.where(_gs.is_default == P()); params.append(int(args.is_default))

    q = q.orderby(_gs.name)
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"grading_scales": [dict(r) for r in rows], "count": len(rows)})


def get_grading_scale(conn, args):
    scale_id = getattr(args, "scale_id", None)
    if not scale_id:
        err("--scale-id is required")

    row = conn.execute(Q.from_(Table("educlaw_grading_scale")).select(Table("educlaw_grading_scale").star).where(Field("id") == P()).get_sql(), (scale_id,)).fetchone()
    if not row:
        err(f"Grading scale {scale_id} not found")

    data = dict(row)
    _gse = Table("educlaw_grading_scale_entry")
    entries = conn.execute(
        Q.from_(_gse).select(_gse.star).where(_gse.grading_scale_id == P())
        .orderby(_gse.sort_order).get_sql(),
        (scale_id,)
    ).fetchall()
    data["entries"] = [dict(e) for e in entries]
    ok(data)


# ─────────────────────────────────────────────────────────────────────────────
# ASSESSMENT PLAN
# ─────────────────────────────────────────────────────────────────────────────

def add_assessment_plan(conn, args):
    section_id = getattr(args, "section_id", None)
    grading_scale_id = getattr(args, "grading_scale_id", None)
    company_id = getattr(args, "company_id", None)
    categories_json = getattr(args, "categories", None)

    if not section_id:
        err("--section-id is required")
    if not grading_scale_id:
        err("--grading-scale-id is required")
    if not company_id:
        err("--company-id is required")
    if not categories_json:
        err("--categories is required (JSON array of {name, weight_percentage, sort_order})")

    if not conn.execute(Q.from_(Table("educlaw_section")).select(Field("id")).where(Field("id") == P()).get_sql(), (section_id,)).fetchone():
        err(f"Section {section_id} not found")
    if not conn.execute(Q.from_(Table("educlaw_grading_scale")).select(Field("id")).where(Field("id") == P()).get_sql(), (grading_scale_id,)).fetchone():
        err(f"Grading scale {grading_scale_id} not found")

    _ap2 = Table("educlaw_assessment_plan")
    existing = conn.execute(
        Q.from_(_ap2).select(_ap2.id).where(_ap2.section_id == P()).get_sql(), (section_id,)
    ).fetchone()
    if existing:
        err(f"Assessment plan already exists for section {section_id}")

    try:
        categories = json.loads(categories_json) if isinstance(categories_json, str) else categories_json
        if not isinstance(categories, list) or not categories:
            err("--categories must be a non-empty JSON array")
    except (json.JSONDecodeError, TypeError):
        err("--categories must be valid JSON array")

    # Validate weights sum to 100
    total_weight = sum(_d(c.get("weight_percentage", 0)) for c in categories if isinstance(c, dict))
    if total_weight != Decimal("100"):
        err(f"Category weights must sum to 100% (got {total_weight}%)")

    plan_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_assessment_plan", {"id": P(), "section_id": P(), "grading_scale_id": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})


    conn.execute(sql,
        (plan_id, section_id, grading_scale_id, company_id, now, now,
         getattr(args, "user_id", None) or "")
    )

    for i, cat in enumerate(categories):
        if not isinstance(cat, dict):
            continue
        cat_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_assessment_category", {"id": P(), "assessment_plan_id": P(), "name": P(), "weight_percentage": P(), "sort_order": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (cat_id, plan_id, cat.get("name", f"Category {i+1}"),
             str(_d(cat.get("weight_percentage", "0"))),
             cat.get("sort_order", i + 1), now, getattr(args, "user_id", None) or "")
        )

    audit(conn, SKILL, "edu-add-assessment-plan", "educlaw_assessment_plan", plan_id,
          new_values={"section_id": section_id, "category_count": len(categories)})
    conn.commit()
    ok({"id": plan_id, "section_id": section_id, "category_count": len(categories)})


def update_assessment_plan(conn, args):
    plan_id = getattr(args, "plan_id", None)
    if not plan_id:
        err("--plan-id is required")

    row = conn.execute(Q.from_(Table("educlaw_assessment_plan")).select(Table("educlaw_assessment_plan").star).where(Field("id") == P()).get_sql(), (plan_id,)).fetchone()
    if not row:
        err(f"Assessment plan {plan_id} not found")

    changed = []
    updates, params = [], []

    if getattr(args, "grading_scale_id", None) is not None:
        if not conn.execute(Q.from_(Table("educlaw_grading_scale")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.grading_scale_id,)).fetchone():
            err(f"Grading scale {args.grading_scale_id} not found")
        updates.append("grading_scale_id = ?"); params.append(args.grading_scale_id)
        changed.append("grading_scale_id")

    categories_json = getattr(args, "categories", None)
    if categories_json:
        try:
            categories = json.loads(categories_json) if isinstance(categories_json, str) else categories_json
        except Exception:
            err("--categories must be valid JSON array")

        total_weight = sum(_d(c.get("weight_percentage", 0)) for c in categories if isinstance(c, dict))
        if total_weight != Decimal("100"):
            err(f"Category weights must sum to 100% (got {total_weight}%)")

        _ac_del = Table("educlaw_assessment_category")
        conn.execute(
            Q.from_(_ac_del).delete().where(_ac_del.assessment_plan_id == P()).get_sql(), (plan_id,)
        )
        now = _now_iso()
        for i, cat in enumerate(categories):
            cat_id = str(uuid.uuid4())
            sql, _ = insert_row("educlaw_assessment_category", {"id": P(), "assessment_plan_id": P(), "name": P(), "weight_percentage": P(), "sort_order": P(), "created_at": P(), "created_by": P()})

            conn.execute(sql,
                (cat_id, plan_id, cat.get("name", f"Category {i+1}"),
                 str(_d(cat.get("weight_percentage", "0"))),
                 cat.get("sort_order", i + 1), now, getattr(args, "user_id", None) or "")
            )
        changed.append("categories")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(plan_id)
    if updates[:-1]:
        conn.execute(  # PyPika: skipped — dynamic column set built conditionally
            f"UPDATE educlaw_assessment_plan SET {', '.join(updates)} WHERE id = ?", params)

    audit(conn, SKILL, "edu-update-assessment-plan", "educlaw_assessment_plan", plan_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": plan_id, "updated_fields": changed})


def get_assessment_plan(conn, args):
    plan_id = getattr(args, "plan_id", None)
    section_id = getattr(args, "section_id", None)

    if not plan_id and not section_id:
        err("--plan-id or --section-id is required")

    if plan_id:
        row = conn.execute(Q.from_(Table("educlaw_assessment_plan")).select(Table("educlaw_assessment_plan").star).where(Field("id") == P()).get_sql(), (plan_id,)).fetchone()
    else:
        _ap3 = Table("educlaw_assessment_plan")
        row = conn.execute(Q.from_(_ap3).select(_ap3.star).where(_ap3.section_id == P()).get_sql(), (section_id,)).fetchone()

    if not row:
        err("Assessment plan not found")

    data = dict(row)
    _ac = Table("educlaw_assessment_category")
    categories = conn.execute(
        Q.from_(_ac).select(_ac.star).where(_ac.assessment_plan_id == P())
        .orderby(_ac.sort_order).get_sql(),
        (data["id"],)
    ).fetchall()
    data["categories"] = []
    for cat in categories:
        cat_data = dict(cat)
        _asmt = Table("educlaw_assessment")
        assessments = conn.execute(
            Q.from_(_asmt).select(_asmt.star).where(_asmt.category_id == P())
            .orderby(_asmt.sort_order).orderby(_asmt.due_date).get_sql(),
            (cat_data["id"],)
        ).fetchall()
        cat_data["assessments"] = [dict(a) for a in assessments]
        data["categories"].append(cat_data)
    ok(data)


# ─────────────────────────────────────────────────────────────────────────────
# ASSESSMENT
# ─────────────────────────────────────────────────────────────────────────────

def add_assessment(conn, args):
    plan_id = getattr(args, "plan_id", None)
    category_id = getattr(args, "category_id", None)
    name = getattr(args, "name", None)
    max_points = getattr(args, "max_points", None)

    if not plan_id:
        err("--plan-id is required")
    if not category_id:
        err("--category-id is required")
    if not name:
        err("--name is required")
    if not max_points:
        err("--max-points is required")
    if _d(max_points) <= 0:
        err("--max-points must be greater than 0")

    if not conn.execute(Q.from_(Table("educlaw_assessment_plan")).select(Field("id")).where(Field("id") == P()).get_sql(), (plan_id,)).fetchone():
        err(f"Assessment plan {plan_id} not found")
    if not conn.execute(Q.from_(Table("educlaw_assessment_category")).select(Field("id")).where(Field("id") == P()).get_sql(), (category_id,)).fetchone():
        err(f"Assessment category {category_id} not found")

    assessment_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_assessment", {"id": P(), "assessment_plan_id": P(), "category_id": P(), "name": P(), "description": P(), "max_points": P(), "due_date": P(), "is_published": P(), "allows_extra_credit": P(), "sort_order": P(), "created_at": P(), "updated_at": P(), "created_by": P()})


    conn.execute(sql,
        (assessment_id, plan_id, category_id, name,
         getattr(args, "description", None) or "",
         str(_d(max_points)),
         getattr(args, "due_date", None) or "",
         int(getattr(args, "is_published", None) or 0),
         int(getattr(args, "allows_extra_credit", None) or 0),
         int(getattr(args, "sort_order", None) or 0),
         now, now, getattr(args, "user_id", None) or "")
    )

    # Auto-create result stubs for all enrolled students
    plan_row = conn.execute(Q.from_(Table("educlaw_assessment_plan")).select(Field("section_id"), Field("company_id")).where(Field("id") == P()).get_sql(), (plan_id,)).fetchone()
    result_count = 0
    if plan_row:
        p = dict(plan_row)
        _ce = Table("educlaw_course_enrollment")
        enrolled = conn.execute(
            Q.from_(_ce).select(_ce.id, _ce.student_id)
            .where(_ce.section_id == P()).where(_ce.enrollment_status == 'enrolled')
            .get_sql(),
            (p["section_id"],)
        ).fetchall()
        for enr in enrolled:
            e = dict(enr)
            result_id = str(uuid.uuid4())
            try:
                sql, _ = insert_row("educlaw_assessment_result", {"id": P(), "assessment_id": P(), "student_id": P(), "course_enrollment_id": P(), "points_earned": P(), "is_exempt": P(), "is_late": P(), "comments": P(), "graded_by": P(), "graded_at": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

                conn.execute(sql,
                    (result_id, assessment_id, e["student_id"], e["id"],
                     None, 0, 0, "", "", "", now, now, getattr(args, "user_id", None) or "")
                )
                result_count += 1
            except sqlite3.IntegrityError:
                pass

    audit(conn, SKILL, "edu-add-assessment", "educlaw_assessment", assessment_id,
          new_values={"name": name, "plan_id": plan_id, "result_stubs_created": result_count})
    conn.commit()
    ok({"id": assessment_id, "name": name, "max_points": str(_d(max_points)),
        "result_stubs_created": result_count})


def update_assessment(conn, args):
    assessment_id = getattr(args, "assessment_id", None)
    if not assessment_id:
        err("--assessment-id is required")

    row = conn.execute(Q.from_(Table("educlaw_assessment")).select(Table("educlaw_assessment").star).where(Field("id") == P()).get_sql(), (assessment_id,)).fetchone()
    if not row:
        err(f"Assessment {assessment_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "description", None) is not None:
        updates.append("description = ?"); params.append(args.description); changed.append("description")
    if getattr(args, "max_points", None) is not None:
        if _d(args.max_points) <= 0:
            err("--max-points must be greater than 0")
        updates.append("max_points = ?"); params.append(str(_d(args.max_points)))
        changed.append("max_points")
    if getattr(args, "due_date", None) is not None:
        updates.append("due_date = ?"); params.append(args.due_date); changed.append("due_date")
    if getattr(args, "is_published", None) is not None:
        updates.append("is_published = ?"); params.append(int(args.is_published))
        changed.append("is_published")
    if getattr(args, "allows_extra_credit", None) is not None:
        updates.append("allows_extra_credit = ?"); params.append(int(args.allows_extra_credit))
        changed.append("allows_extra_credit")
    if getattr(args, "sort_order", None) is not None:
        updates.append("sort_order = ?"); params.append(int(args.sort_order))
        changed.append("sort_order")

    if not changed:
        err("No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(assessment_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_assessment SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "edu-update-assessment", "educlaw_assessment", assessment_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": assessment_id, "updated_fields": changed})


def list_assessments(conn, args):
    _a = Table("educlaw_assessment")
    q = Q.from_(_a).select(_a.star)
    params = []

    if getattr(args, "plan_id", None):
        q = q.where(_a.assessment_plan_id == P()); params.append(args.plan_id)
    if getattr(args, "category_id", None):
        q = q.where(_a.category_id == P()); params.append(args.category_id)
    if getattr(args, "is_published", None) is not None:
        q = q.where(_a.is_published == P()); params.append(int(args.is_published))

    from_date = getattr(args, "due_date_from", None)
    to_date = getattr(args, "due_date_to", None)
    if from_date:
        q = q.where(_a.due_date >= P()); params.append(from_date)
    if to_date:
        q = q.where(_a.due_date <= P()); params.append(to_date)

    q = q.orderby(_a.sort_order).orderby(_a.due_date)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"assessments": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# GRADE ENTRY
# ─────────────────────────────────────────────────────────────────────────────

def enter_assessment_result(conn, args):
    assessment_id = getattr(args, "assessment_id", None)
    student_id = getattr(args, "student_id", None)
    points_earned = getattr(args, "points_earned", None)

    if not assessment_id:
        err("--assessment-id is required")
    if not student_id:
        err("--student-id is required")

    a_row = conn.execute(Q.from_(Table("educlaw_assessment")).select(Table("educlaw_assessment").star).where(Field("id") == P()).get_sql(), (assessment_id,)).fetchone()
    if not a_row:
        err(f"Assessment {assessment_id} not found")
    a = dict(a_row)

    # Validate extra credit constraint
    if points_earned is not None:
        pts = _d(points_earned)
        if not a["allows_extra_credit"] and pts > _d(a["max_points"]):
            err(f"Points earned ({pts}) cannot exceed max_points ({a['max_points']}) for this assessment")

    # Find existing result
    _ar = Table("educlaw_assessment_result")
    result_row = conn.execute(
        Q.from_(_ar).select(_ar.star).where(_ar.assessment_id == P()).where(_ar.student_id == P()).get_sql(),
        (assessment_id, student_id)
    ).fetchone()

    now = _now_iso()
    graded_by = getattr(args, "graded_by", None) or getattr(args, "user_id", None) or ""
    is_exempt = int(getattr(args, "is_exempt", None) or 0)
    is_late = int(getattr(args, "is_late", None) or 0)
    comments = getattr(args, "comments", None) or ""

    if result_row:
        r = dict(result_row)
        # Check enrollment grade not already submitted
        _ce2 = Table("educlaw_course_enrollment")
        enr_row = conn.execute(
            Q.from_(_ce2).select(_ce2.is_grade_submitted).where(_ce2.id == P()).get_sql(),
            (r["course_enrollment_id"],)
        ).fetchone()
        if enr_row and dict(enr_row)["is_grade_submitted"]:
            err("Cannot modify grades after final grades have been submitted")

        _ar2 = Table("educlaw_assessment_result")
        conn.execute(
            Q.update(_ar2)
            .set(_ar2.points_earned, P())
            .set(_ar2.is_exempt, P())
            .set(_ar2.is_late, P())
            .set(_ar2.comments, P())
            .set(_ar2.graded_by, P())
            .set(_ar2.graded_at, P())
            .set(_ar2.updated_at, LiteralValue("datetime('now')"))
            .where(_ar2.id == P())
            .get_sql(),
            (str(pts) if points_earned is not None else None,
             is_exempt, is_late, comments, graded_by, now, r["id"])
        )
        result_id = r["id"]
    else:
        # Need enrollment ID
        enrollment_id = getattr(args, "enrollment_id", None)
        if not enrollment_id:
            # Try to find it
            _ap4 = Table("educlaw_assessment_plan")
            plan_row = conn.execute(
                Q.from_(_ap4).select(_ap4.section_id).where(_ap4.id == P()).get_sql(),
                (a["assessment_plan_id"],)
            ).fetchone()
            if plan_row:
                _ce3 = Table("educlaw_course_enrollment")
                enr_row = conn.execute(
                    Q.from_(_ce3).select(_ce3.id)
                    .where(_ce3.student_id == P()).where(_ce3.section_id == P())
                    .get_sql(),
                    (student_id, dict(plan_row)["section_id"])
                ).fetchone()
                enrollment_id = dict(enr_row)["id"] if enr_row else None
        if not enrollment_id:
            err("Could not find course enrollment for this student and assessment")

        result_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_assessment_result", {"id": P(), "assessment_id": P(), "student_id": P(), "course_enrollment_id": P(), "points_earned": P(), "is_exempt": P(), "is_late": P(), "comments": P(), "graded_by": P(), "graded_at": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (result_id, assessment_id, student_id, enrollment_id,
             str(_d(points_earned)) if points_earned is not None else None,
             is_exempt, is_late, comments, graded_by, now, now, now, graded_by)
        )

    conn.commit()
    ok({"id": result_id, "assessment_id": assessment_id, "student_id": student_id,
        "points_earned": str(_d(points_earned)) if points_earned is not None else None})


def batch_enter_results(conn, args):
    assessment_id = getattr(args, "assessment_id", None)
    results_json = getattr(args, "results", None)

    if not assessment_id:
        err("--assessment-id is required")
    if not results_json:
        err("--results is required (JSON array of {student_id, points_earned, is_exempt, comments})")

    try:
        results = json.loads(results_json) if isinstance(results_json, str) else results_json
        if not isinstance(results, list):
            err("--results must be a JSON array")
    except (json.JSONDecodeError, TypeError):
        err("--results must be valid JSON array")

    a_row = conn.execute(Q.from_(Table("educlaw_assessment")).select(Table("educlaw_assessment").star).where(Field("id") == P()).get_sql(), (assessment_id,)).fetchone()
    if not a_row:
        err(f"Assessment {assessment_id} not found")
    a = dict(a_row)

    _ap5 = Table("educlaw_assessment_plan")
    plan_row = conn.execute(
        Q.from_(_ap5).select(_ap5.section_id).where(_ap5.id == P()).get_sql(),
        (a["assessment_plan_id"],)
    ).fetchone()
    section_id = dict(plan_row)["section_id"] if plan_row else None

    now = _now_iso()
    graded_by = getattr(args, "graded_by", None) or getattr(args, "user_id", None) or ""
    saved_count = 0
    errors = []

    for result in results:
        if not isinstance(result, dict):
            continue
        student_id = result.get("student_id")
        points_earned = result.get("points_earned")
        is_exempt = int(result.get("is_exempt", 0))
        is_late = int(result.get("is_late", 0))
        comments = result.get("comments", "")

        if not student_id:
            errors.append({"error": "student_id is required", "data": result})
            continue

        # Find enrollment
        enrollment_id = None
        if section_id:
            enr_row = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Field("id")).where(Field("student_id") == P()).where(Field("section_id") == P()).get_sql(), (student_id, section_id)).fetchone()
            enrollment_id = dict(enr_row)["id"] if enr_row else None

        # Find existing result
        existing = conn.execute(Q.from_(Table("educlaw_assessment_result")).select(Field("id")).where(Field("assessment_id") == P()).where(Field("student_id") == P()).get_sql(), (assessment_id, student_id)).fetchone()

        pts_str = str(_d(points_earned)) if points_earned is not None else None

        try:
            if existing:
                _ar3 = Table("educlaw_assessment_result")
                conn.execute(
                    Q.update(_ar3)
                    .set(_ar3.points_earned, P())
                    .set(_ar3.is_exempt, P())
                    .set(_ar3.is_late, P())
                    .set(_ar3.comments, P())
                    .set(_ar3.graded_by, P())
                    .set(_ar3.graded_at, P())
                    .set(_ar3.updated_at, LiteralValue("datetime('now')"))
                    .where(_ar3.id == P())
                    .get_sql(),
                    (pts_str, is_exempt, is_late, comments, graded_by, now, dict(existing)["id"])
                )
            elif enrollment_id:
                result_id = str(uuid.uuid4())
                sql, _ = insert_row("educlaw_assessment_result", {"id": P(), "assessment_id": P(), "student_id": P(), "course_enrollment_id": P(), "points_earned": P(), "is_exempt": P(), "is_late": P(), "comments": P(), "graded_by": P(), "graded_at": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

                conn.execute(sql,
                    (result_id, assessment_id, student_id, enrollment_id,
                     pts_str, is_exempt, is_late, comments, graded_by, now, now, now, graded_by)
                )
            saved_count += 1
        except Exception as e:
            errors.append({"student_id": student_id, "error": str(e)})

    conn.commit()
    ok({"assessment_id": assessment_id, "saved": saved_count, "errors": errors})


# ─────────────────────────────────────────────────────────────────────────────
# GRADE CALCULATION
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_grade_for_student(conn, plan_id, student_id, enrollment_id, scale_entries):
    """Calculate weighted final grade. Returns (percentage, letter_grade, grade_points)."""
    _ac = Table("educlaw_assessment_category")
    categories = conn.execute(
        Q.from_(_ac).select(_ac.star).where(_ac.assessment_plan_id == P())
        .orderby(_ac.sort_order).get_sql(),
        (plan_id,)
    ).fetchall()

    weighted_sum = Decimal("0")
    total_weight = Decimal("0")

    for cat in categories:
        c = dict(cat)
        cat_weight = _d(c["weight_percentage"]) / Decimal("100")

        # Get all assessments in this category
        _asmt2 = Table("educlaw_assessment")
        assessments = conn.execute(
            Q.from_(_asmt2).select(_asmt2.star).where(_asmt2.category_id == P()).get_sql(), (c["id"],)
        ).fetchall()

        cat_earned = Decimal("0")
        cat_max = Decimal("0")

        for asmnt in assessments:
            a = dict(asmnt)
            _ar4 = Table("educlaw_assessment_result")
            result = conn.execute(
                Q.from_(_ar4).select(_ar4.star)
                .where(_ar4.assessment_id == P()).where(_ar4.student_id == P())
                .get_sql(),
                (a["id"], student_id)
            ).fetchone()

            if result:
                r = dict(result)
                if r["is_exempt"]:
                    continue
                if r["points_earned"] is not None:
                    earned = _d(r["points_earned"])
                    max_pts = _d(a["max_points"])
                    cat_earned += earned
                    cat_max += max_pts
            else:
                cat_max += _d(a["max_points"])

        if cat_max > 0:
            cat_pct = (cat_earned / cat_max) * Decimal("100")
            weighted_sum += cat_pct * cat_weight
            total_weight += cat_weight

    if total_weight == 0:
        return "0", "F", "0"

    # Normalize if some categories had no graded items
    if total_weight < Decimal("1"):
        final_pct = weighted_sum / total_weight if total_weight > 0 else Decimal("0")
    else:
        final_pct = weighted_sum

    final_pct = final_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Map to letter grade
    letter = "F"
    points = "0.0"
    for entry in scale_entries:
        e = dict(entry)
        if _d(e["min_percentage"]) <= final_pct <= _d(e["max_percentage"]):
            letter = e["letter_grade"]
            points = e["grade_points"]
            break

    return str(final_pct), letter, points


def calculate_section_grade(conn, args):
    section_id = getattr(args, "section_id", None)
    student_id = getattr(args, "student_id", None)

    if not section_id:
        err("--section-id is required")

    _ap = Table("educlaw_assessment_plan")
    plan_row = conn.execute(
        Q.from_(_ap).select(_ap.star).where(_ap.section_id == P()).get_sql(), (section_id,)
    ).fetchone()
    if not plan_row:
        err(f"No assessment plan found for section {section_id}")

    plan = dict(plan_row)
    _gse = Table("educlaw_grading_scale_entry")
    scale_entries = conn.execute(
        Q.from_(_gse).select(_gse.star).where(_gse.grading_scale_id == P())
        .orderby(_gse.sort_order).get_sql(),
        (plan["grading_scale_id"],)
    ).fetchall()

    if student_id:
        enr_row = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Field("id")).where(Field("student_id") == P()).where(Field("section_id") == P()).get_sql(), (student_id, section_id)).fetchone()
        if not enr_row:
            err(f"Student {student_id} is not enrolled in section {section_id}")
        enrollment_id = dict(enr_row)["id"]
        pct, letter, pts = _calculate_grade_for_student(
            conn, plan["id"], student_id, enrollment_id, scale_entries
        )
        ok({"student_id": student_id, "section_id": section_id,
            "percentage": pct, "letter_grade": letter, "grade_points": pts,
            "is_preview": True})
    else:
        # All enrolled students
        _ce4 = Table("educlaw_course_enrollment")
        enrollments = conn.execute(
            Q.from_(_ce4).select(_ce4.id, _ce4.student_id)
            .where(_ce4.section_id == P()).where(_ce4.enrollment_status == 'enrolled')
            .get_sql(),
            (section_id,)
        ).fetchall()
        results = []
        for enr in enrollments:
            e = dict(enr)
            pct, letter, pts = _calculate_grade_for_student(
                conn, plan["id"], e["student_id"], e["id"], scale_entries
            )
            results.append({"student_id": e["student_id"], "enrollment_id": e["id"],
                            "percentage": pct, "letter_grade": letter, "grade_points": pts})
        ok({"section_id": section_id, "grades": results, "is_preview": True})


def submit_grades(conn, args):
    """Submit official final grades for all students in section. Immutable."""
    section_id = getattr(args, "section_id", None)
    submitted_by = getattr(args, "submitted_by", None) or getattr(args, "user_id", None)

    if not section_id:
        err("--section-id is required")
    if not submitted_by:
        err("--submitted-by is required")

    _ap6 = Table("educlaw_assessment_plan")
    plan_row = conn.execute(
        Q.from_(_ap6).select(_ap6.star).where(_ap6.section_id == P()).get_sql(), (section_id,)
    ).fetchone()
    if not plan_row:
        err(f"No assessment plan found for section {section_id}")

    plan = dict(plan_row)
    _gse2 = Table("educlaw_grading_scale_entry")
    scale_entries = conn.execute(
        Q.from_(_gse2).select(_gse2.star).where(_gse2.grading_scale_id == P())
        .orderby(_gse2.sort_order).get_sql(),
        (plan["grading_scale_id"],)
    ).fetchall()

    _ce5 = Table("educlaw_course_enrollment")
    enrollments = conn.execute(
        Q.from_(_ce5).select(_ce5.star)
        .where(_ce5.section_id == P()).where(_ce5.enrollment_status == 'enrolled')
        .get_sql(),
        (section_id,)
    ).fetchall()

    now = _now_iso()
    submitted_count = 0
    company_id = None

    for enr in enrollments:
        e = dict(enr)
        if e["is_grade_submitted"]:
            continue

        company_id = e.get("company_id", "")
        pct, letter, pts = _calculate_grade_for_student(
            conn, plan["id"], e["student_id"], e["id"], scale_entries
        )

        _ce6 = Table("educlaw_course_enrollment")
        conn.execute(
            Q.update(_ce6)
            .set(_ce6.enrollment_status, 'completed')
            .set(_ce6.final_letter_grade, P())
            .set(_ce6.final_grade_points, P())
            .set(_ce6.final_percentage, P())
            .set(_ce6.grade_submitted_by, P())
            .set(_ce6.grade_submitted_at, P())
            .set(_ce6.is_grade_submitted, 1)
            .set(_ce6.updated_at, LiteralValue("datetime('now')"))
            .where(_ce6.id == P())
            .get_sql(),
            (letter, pts, pct, submitted_by, now, e["id"])
        )

        # Send grade_posted notification
        notif_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (notif_id, "student", e["student_id"], "grade_posted",
             "Grade Posted",
             f"Your final grade has been posted: {letter} ({pct}%)",
             "educlaw_course_enrollment", e["id"], company_id, now, submitted_by)
        )

        # Trigger GPA recalculation
        _calculate_gpa_internal(conn, e["student_id"])
        submitted_count += 1

    conn.commit()
    ok({"section_id": section_id, "submitted_by": submitted_by,
        "grades_submitted": submitted_count})


def amend_grade(conn, args):
    enrollment_id = getattr(args, "enrollment_id", None)
    new_letter_grade = getattr(args, "new_letter_grade", None)
    new_grade_points = getattr(args, "new_grade_points", None)
    reason = getattr(args, "reason", None)
    amended_by = getattr(args, "amended_by", None) or getattr(args, "user_id", None)

    if not enrollment_id:
        err("--enrollment-id is required")
    if not new_letter_grade:
        err("--new-letter-grade is required")
    if not reason:
        err("--reason is required")
    if not amended_by:
        err("--amended-by is required")

    row = conn.execute(Q.from_(Table("educlaw_course_enrollment")).select(Table("educlaw_course_enrollment").star).where(Field("id") == P()).get_sql(), (enrollment_id,)).fetchone()
    if not row:
        err(f"Enrollment {enrollment_id} not found")

    r = dict(row)
    if not r["is_grade_submitted"]:
        err("Grade amendments can only be made after official grade submission")

    now = _now_iso()
    amendment_id = str(uuid.uuid4())

    sql, _ = insert_row("educlaw_grade_amendment", {"id": P(), "course_enrollment_id": P(), "old_letter_grade": P(), "new_letter_grade": P(), "old_grade_points": P(), "new_grade_points": P(), "reason": P(), "amended_by": P(), "approved_by": P(), "created_at": P(), "created_by": P()})


    conn.execute(sql,
        (amendment_id, enrollment_id, r["final_letter_grade"], new_letter_grade,
         r["final_grade_points"],
         str(_d(new_grade_points)) if new_grade_points else r["final_grade_points"],
         reason, amended_by,
         getattr(args, "approved_by", None) or "",
         now, amended_by)
    )

    _ce7 = Table("educlaw_course_enrollment")
    conn.execute(
        Q.update(_ce7)
        .set(_ce7.final_letter_grade, P())
        .set(_ce7.final_grade_points, P())
        .set(_ce7.updated_at, LiteralValue("datetime('now')"))
        .where(_ce7.id == P())
        .get_sql(),
        (new_letter_grade,
         str(_d(new_grade_points)) if new_grade_points else r["final_grade_points"],
         enrollment_id)
    )

    # Recalculate GPA
    _calculate_gpa_internal(conn, r["student_id"])

    audit(conn, SKILL, "edu-amend-grade", "educlaw_grade_amendment", amendment_id,
          new_values={"old_grade": r["final_letter_grade"], "new_grade": new_letter_grade})
    conn.commit()
    ok({"amendment_id": amendment_id, "enrollment_id": enrollment_id,
        "old_letter_grade": r["final_letter_grade"], "new_letter_grade": new_letter_grade})


def _calculate_gpa_internal(conn, student_id):
    """Recalculate cumulative GPA and total credits for student."""
    _ce8 = Table("educlaw_course_enrollment")
    _s2 = Table("educlaw_section")
    _c2 = Table("educlaw_course")
    enrollments = conn.execute(
        Q.from_(_ce8).join(_s2).on(_s2.id == _ce8.section_id)
        .join(_c2).on(_c2.id == _s2.course_id)
        .select(_ce8.final_grade_points, _ce8.final_letter_grade, _c2.credit_hours, _ce8.grade_type)
        .where(_ce8.student_id == P()).where(_ce8.is_grade_submitted == 1)
        .where(_ce8.enrollment_status == 'completed')
        .get_sql(),
        (student_id,)
    ).fetchall()

    # Grades that don't count in GPA
    exclude_grades = {"W", "I", "P", "NP", "AU", ""}

    total_points = Decimal("0")
    total_credits = Decimal("0")
    gpa_credits = Decimal("0")
    all_credits = Decimal("0")

    for enr in enrollments:
        e = dict(enr)
        credits = _d(e["credit_hours"])
        all_credits += credits
        if e["final_letter_grade"] not in exclude_grades and e["grade_type"] != "audit":
            grade_pts = _d(e["final_grade_points"])
            total_points += grade_pts * credits
            gpa_credits += credits

    cumulative_gpa = "0.00"
    if gpa_credits > 0:
        raw_gpa = total_points / gpa_credits
        cumulative_gpa = str(raw_gpa.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # Determine academic standing
    gpa_val = _d(cumulative_gpa)
    if gpa_val >= Decimal("3.5"):
        standing = "deans_list"
    elif gpa_val >= Decimal("3.0"):
        standing = "honor_roll"
    elif gpa_val < Decimal("2.0") and gpa_credits > 0:
        standing = "probation"
    else:
        standing = "good"

    _stu = Table("educlaw_student")
    conn.execute(
        Q.update(_stu)
        .set(_stu.cumulative_gpa, P())
        .set(_stu.total_credits_earned, P())
        .set(_stu.academic_standing, P())
        .set(_stu.updated_at, LiteralValue("datetime('now')"))
        .where(_stu.id == P())
        .get_sql(),
        (cumulative_gpa, str(all_credits), standing, student_id)
    )


def calculate_gpa(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        err("--student-id is required")

    row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not row:
        err(f"Student {student_id} not found")

    _calculate_gpa_internal(conn, student_id)
    conn.commit()

    updated = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    u = dict(updated)
    ok({"student_id": student_id, "cumulative_gpa": u["cumulative_gpa"],
        "total_credits_earned": u["total_credits_earned"],
        "academic_standing": u["academic_standing"]})


def generate_transcript(conn, args):
    student_id = getattr(args, "student_id", None)
    company_id = getattr(args, "company_id", None)
    user_id = getattr(args, "user_id", None) or "system"

    if not student_id:
        err("--student-id is required")
    if not company_id:
        err("--company-id is required")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")

    student = dict(student_row)
    student.pop("ssn_encrypted", None)

    _ce9 = Table("educlaw_course_enrollment")
    _sec2 = Table("educlaw_section")
    _c3 = Table("educlaw_course")
    _at2 = Table("educlaw_academic_term")
    _ay2 = Table("educlaw_academic_year")
    enrollments = conn.execute(
        Q.from_(_ce9)
        .join(_sec2).on(_sec2.id == _ce9.section_id)
        .join(_c3).on(_c3.id == _sec2.course_id)
        .join(_at2).on(_at2.id == _sec2.academic_term_id)
        .join(_ay2).on(_ay2.id == _at2.academic_year_id)
        .select(_ce9.star, _sec2.section_number, _sec2.naming_series.as_("section_series"),
                _c3.course_code, _c3.name.as_("course_name"), _c3.credit_hours,
                _at2.name.as_("term_name"), _at2.start_date, _at2.end_date,
                _ay2.name.as_("year_name"))
        .where(_ce9.student_id == P()).where(_ce9.is_grade_submitted == 1)
        .orderby(_at2.start_date).orderby(_c3.course_code)
        .get_sql(),
        (student_id,)
    ).fetchall()

    # Group by term
    terms_dict = {}
    for enr in enrollments:
        e = dict(enr)
        term_key = e["term_name"]
        if term_key not in terms_dict:
            terms_dict[term_key] = {
                "term_name": e["term_name"],
                "year_name": e["year_name"],
                "start_date": e["start_date"],
                "courses": [],
                "term_gpa": "0.00",
                "term_credits": "0"
            }
        terms_dict[term_key]["courses"].append({
            "course_code": e["course_code"],
            "course_name": e["course_name"],
            "credit_hours": e["credit_hours"],
            "final_letter_grade": e["final_letter_grade"],
            "final_grade_points": e["final_grade_points"],
            "final_percentage": e["final_percentage"],
            "grade_type": e["grade_type"],
        })

    # Calculate term GPAs
    for term_key in terms_dict:
        t = terms_dict[term_key]
        term_pts = Decimal("0")
        term_cr = Decimal("0")
        all_cr = Decimal("0")
        exclude_grades = {"W", "I", "P", "NP", "AU", ""}
        for course in t["courses"]:
            cr = _d(course["credit_hours"])
            all_cr += cr
            if course["final_letter_grade"] not in exclude_grades and course["grade_type"] != "audit":
                term_pts += _d(course["final_grade_points"]) * cr
                term_cr += cr
        if term_cr > 0:
            t["term_gpa"] = str((term_pts / term_cr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        t["term_credits"] = str(all_cr)

    # Log FERPA data access
    _log_data_access_internal(conn, user_id, student_id, "grades", "view",
                               "Transcript generation", company_id)
    conn.commit()

    ok({
        "student": {
            "id": student["id"],
            "naming_series": student["naming_series"],
            "full_name": student["full_name"],
            "cumulative_gpa": student["cumulative_gpa"],
            "total_credits_earned": student["total_credits_earned"],
            "academic_standing": student["academic_standing"],
        },
        "terms": sorted(terms_dict.values(), key=lambda x: x["start_date"]),
        "generated_at": _now_iso(),
    })


def generate_report_card(conn, args):
    student_id = getattr(args, "student_id", None)
    academic_term_id = getattr(args, "academic_term_id", None)

    if not student_id:
        err("--student-id is required")
    if not academic_term_id:
        err("--academic-term-id is required")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")

    student = dict(student_row)

    _ce10 = Table("educlaw_course_enrollment")
    _sec3 = Table("educlaw_section")
    _c4 = Table("educlaw_course")
    enrollments = conn.execute(
        Q.from_(_ce10).join(_sec3).on(_sec3.id == _ce10.section_id)
        .join(_c4).on(_c4.id == _sec3.course_id)
        .select(_ce10.star, _c4.course_code, _c4.name.as_("course_name"),
                _c4.credit_hours, _sec3.section_number)
        .where(_ce10.student_id == P()).where(_sec3.academic_term_id == P())
        .orderby(_c4.course_code)
        .get_sql(),
        (student_id, academic_term_id)
    ).fetchall()

    # Attendance summary for term — PyPika: skipped — SUM(CASE WHEN) complex aggregation
    attendance_summary = conn.execute(
        """SELECT
             COUNT(*) as total_days,
             SUM(CASE WHEN attendance_status = 'present' THEN 1 ELSE 0 END) as present,
             SUM(CASE WHEN attendance_status = 'absent' THEN 1 ELSE 0 END) as absent,
             SUM(CASE WHEN attendance_status = 'tardy' THEN 1 ELSE 0 END) as tardy,
             SUM(CASE WHEN attendance_status = 'excused' THEN 1 ELSE 0 END) as excused
           FROM educlaw_student_attendance sa
           JOIN educlaw_section s ON s.id = sa.section_id
           WHERE sa.student_id = ? AND s.academic_term_id = ?""",
        (student_id, academic_term_id)
    ).fetchone()

    ok({
        "student": {
            "id": student["id"],
            "full_name": student["full_name"],
            "grade_level": student["grade_level"],
            "academic_standing": student["academic_standing"],
        },
        "academic_term_id": academic_term_id,
        "courses": [dict(e) for e in enrollments],
        "attendance": dict(attendance_summary) if attendance_summary else {},
        "generated_at": _now_iso(),
    })


def list_grades(conn, args):
    _ce = Table("educlaw_course_enrollment")
    q = Q.from_(_ce).select(_ce.star)
    params = []

    if getattr(args, "student_id", None):
        q = q.where(_ce.student_id == P()); params.append(args.student_id)
    if getattr(args, "section_id", None):
        q = q.where(_ce.section_id == P()); params.append(args.section_id)
    if getattr(args, "academic_term_id", None):
        _sec_sub = Table("educlaw_section")
        sub = Q.from_(_sec_sub).select(_sec_sub.id).where(_sec_sub.academic_term_id == P())
        q = q.where(_ce.section_id.isin(sub))
        params.append(args.academic_term_id)
    if getattr(args, "is_grade_submitted", None) is not None:
        q = q.where(_ce.is_grade_submitted == P()); params.append(int(args.is_grade_submitted))

    q = q.orderby(_ce.is_grade_submitted).orderby(_ce.student_id)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"grades": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-grading-scale": add_grading_scale,
    "edu-update-grading-scale": update_grading_scale,
    "edu-list-grading-scales": list_grading_scales,
    "edu-get-grading-scale": get_grading_scale,
    "edu-add-assessment-plan": add_assessment_plan,
    "edu-update-assessment-plan": update_assessment_plan,
    "edu-get-assessment-plan": get_assessment_plan,
    "edu-add-assessment": add_assessment,
    "edu-update-assessment": update_assessment,
    "edu-list-assessments": list_assessments,
    "edu-record-assessment-result": enter_assessment_result,
    "edu-record-batch-results": batch_enter_results,
    "edu-generate-section-grade": calculate_section_grade,
    "edu-submit-grades": submit_grades,
    "edu-update-grade": amend_grade,
    "edu-generate-gpa": calculate_gpa,
    "edu-generate-transcript": generate_transcript,
    "edu-generate-report-card": generate_report_card,
    "edu-list-grades": list_grades,
}
