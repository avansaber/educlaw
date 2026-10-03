"""EduClaw — fees domain module

Actions for fees: fee categories, fee structures, scholarships,
fee invoice generation via erpclaw-selling, outstanding fee queries.

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
    import importlib.util
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, LiteralValue, now as sql_now
    from erpclaw_lib.cross_skill import (
        create_customer, ensure_service_item, create_invoice, submit_invoice,
        CrossSkillError,
    )
except ImportError:
    pass

SKILL = "educlaw"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _d(val, default="0"):
    try:
        return Decimal(str(val)) if val not in (None, "", "None") else Decimal(default)
    except (InvalidOperation, Exception):
        return Decimal(default)


# ─────────────────────────────────────────────────────────────────────────────
# FEE CATEGORY
# ─────────────────────────────────────────────────────────────────────────────

def add_fee_category(conn, args):
    name = getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)

    if not name:
        err("--name is required")
    if not company_id:
        err("--company-id is required")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    revenue_account_id = getattr(args, "revenue_account_id", None)
    if revenue_account_id:
        if not conn.execute(Q.from_(Table("account")).select(Field("id")).where(Field("id") == P()).get_sql(), (revenue_account_id,)).fetchone():
            err(f"Account {revenue_account_id} not found")

    cat_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("educlaw_fee_category", {"id": P(), "name": P(), "description": P(), "revenue_account_id": P(), "is_active": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (cat_id, name, getattr(args, "description", None) or "",
             revenue_account_id, 1, company_id, now, now,
             getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Fee category '{name}' already exists for this company")

    audit(conn, SKILL, "edu-add-fee-category", "educlaw_fee_category", cat_id,
          new_values={"name": name})
    conn.commit()
    ok({"id": cat_id, "name": name, "company_id": company_id})


def update_fee_category(conn, args):
    category_id = getattr(args, "category_id", None)
    if not category_id:
        err("--category-id is required")

    row = conn.execute(Q.from_(Table("educlaw_fee_category")).select(Table("educlaw_fee_category").star).where(Field("id") == P()).get_sql(), (category_id,)).fetchone()
    if not row:
        err(f"Fee category {category_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "description", None) is not None:
        updates.append("description = ?"); params.append(args.description); changed.append("description")
    if getattr(args, "revenue_account_id", None) is not None:
        if args.revenue_account_id and not conn.execute(Q.from_(Table("account")).select(Field("id")).where(Field("id") == P()).get_sql(), (args.revenue_account_id,)).fetchone():
            err(f"Account {args.revenue_account_id} not found")
        updates.append("revenue_account_id = ?"); params.append(args.revenue_account_id)
        changed.append("revenue_account_id")
    if getattr(args, "is_active", None) is not None:
        updates.append("is_active = ?"); params.append(int(args.is_active)); changed.append("is_active")

    if not changed:
        err("No fields to update")

    updates.append(f"updated_at = {sql_now()}")
    params.append(category_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_fee_category SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"id": category_id, "updated_fields": changed})


def list_fee_categories(conn, args):
    _fc = Table("educlaw_fee_category")
    q = Q.from_(_fc).select(_fc.star)
    params = []

    if getattr(args, "is_active", None) is not None:
        q = q.where(_fc.is_active == P()); params.append(int(args.is_active))
    if getattr(args, "company_id", None):
        q = q.where(_fc.company_id == P()); params.append(args.company_id)

    q = q.orderby(_fc.name)
    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"fee_categories": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# FEE STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

def add_fee_structure(conn, args):
    name = getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)
    items_json = getattr(args, "items", None)

    if not name:
        err("--name is required")
    if not company_id:
        err("--company-id is required")
    if not items_json:
        err("--items is required (JSON array of {fee_category_id, amount, description})")

    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")

    try:
        items = json.loads(items_json) if isinstance(items_json, str) else items_json
        if not isinstance(items, list) or not items:
            err("--items must be a non-empty JSON array")
    except (json.JSONDecodeError, TypeError):
        err("--items must be valid JSON array")

    program_id = getattr(args, "program_id", None)
    if program_id:
        if not conn.execute(Q.from_(Table("educlaw_program")).select(Field("id")).where(Field("id") == P()).get_sql(), (program_id,)).fetchone():
            err(f"Program {program_id} not found")

    academic_term_id = getattr(args, "academic_term_id", None)
    if academic_term_id:
        if not conn.execute(Q.from_(Table("educlaw_academic_term")).select(Field("id")).where(Field("id") == P()).get_sql(), (academic_term_id,)).fetchone():
            err(f"Academic term {academic_term_id} not found")

    # Validate items and calculate total
    total = Decimal("0")
    for item in items:
        if not isinstance(item, dict):
            continue
        cat_id = item.get("fee_category_id")
        amount = _d(item.get("amount", "0"))
        if not cat_id:
            err("Each item must have a fee_category_id")
        if not conn.execute(Q.from_(Table("educlaw_fee_category")).select(Field("id")).where(Field("id") == P()).get_sql(), (cat_id,)).fetchone():
            err(f"Fee category {cat_id} not found")
        if amount < 0:
            err(f"Amount must be >= 0 (got {amount} for category {cat_id})")
        total += amount

    struct_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_fee_structure", {"id": P(), "name": P(), "program_id": P(), "academic_term_id": P(), "grade_level": P(), "total_amount": P(), "is_active": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})


    conn.execute(sql,
        (struct_id, name, program_id, academic_term_id,
         getattr(args, "grade_level", None) or "",
         str(total), 1, company_id, now, now, getattr(args, "user_id", None) or "")
    )

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = str(uuid.uuid4())
        sql, _ = insert_row("educlaw_fee_structure_item", {"id": P(), "fee_structure_id": P(), "fee_category_id": P(), "amount": P(), "description": P(), "sort_order": P(), "created_at": P(), "created_by": P()})

        conn.execute(sql,
            (item_id, struct_id, item.get("fee_category_id"),
             str(_d(item.get("amount", "0"))),
             item.get("description", ""),
             item.get("sort_order", i + 1), now, getattr(args, "user_id", None) or "")
        )

    audit(conn, SKILL, "edu-add-fee-structure", "educlaw_fee_structure", struct_id,
          new_values={"name": name, "total_amount": str(total)})
    conn.commit()
    ok({"id": struct_id, "name": name, "total_amount": str(total), "item_count": len(items)})


def update_fee_structure(conn, args):
    structure_id = getattr(args, "structure_id", None)
    if not structure_id:
        err("--structure-id is required")

    row = conn.execute(Q.from_(Table("educlaw_fee_structure")).select(Table("educlaw_fee_structure").star).where(Field("id") == P()).get_sql(), (structure_id,)).fetchone()
    if not row:
        err(f"Fee structure {structure_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "grade_level", None) is not None:
        updates.append("grade_level = ?"); params.append(args.grade_level); changed.append("grade_level")
    if getattr(args, "is_active", None) is not None:
        updates.append("is_active = ?"); params.append(int(args.is_active)); changed.append("is_active")

    items_json = getattr(args, "items", None)
    if items_json:
        try:
            items = json.loads(items_json) if isinstance(items_json, str) else items_json
        except Exception:
            err("--items must be valid JSON array")

        total = Decimal("0")
        _fcat = Table("educlaw_fee_category")
        for item in items:
            if not isinstance(item, dict):
                continue
            if not conn.execute(Q.from_(_fcat).select(_fcat.id).where(_fcat.id == P()).get_sql(),
                                (item.get("fee_category_id"),)).fetchone():
                err(f"Fee category {item.get('fee_category_id')} not found")
            total += _d(item.get("amount", "0"))

        _fsi = Table("educlaw_fee_structure_item")
        conn.execute(
            Q.from_(_fsi).delete().where(_fsi.fee_structure_id == P()).get_sql(), (structure_id,)
        )
        now = _now_iso()
        for i, item in enumerate(items):
            item_id = str(uuid.uuid4())
            sql, _ = insert_row("educlaw_fee_structure_item", {"id": P(), "fee_structure_id": P(), "fee_category_id": P(), "amount": P(), "description": P(), "sort_order": P(), "created_at": P(), "created_by": P()})

            conn.execute(sql,
                (item_id, structure_id, item.get("fee_category_id"),
                 str(_d(item.get("amount", "0"))), item.get("description", ""),
                 item.get("sort_order", i + 1), now, getattr(args, "user_id", None) or "")
            )
        updates.append("total_amount = ?"); params.append(str(total))
        changed.append("items")

    if not changed:
        err("No fields to update")

    updates.append(f"updated_at = {sql_now()}")
    params.append(structure_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_fee_structure SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"id": structure_id, "updated_fields": changed})


def get_fee_structure(conn, args):
    structure_id = getattr(args, "structure_id", None)
    if not structure_id:
        err("--structure-id is required")

    row = conn.execute(Q.from_(Table("educlaw_fee_structure")).select(Table("educlaw_fee_structure").star).where(Field("id") == P()).get_sql(), (structure_id,)).fetchone()
    if not row:
        err(f"Fee structure {structure_id} not found")

    data = dict(row)
    _fsi = Table("educlaw_fee_structure_item")
    _fc = Table("educlaw_fee_category")
    items = conn.execute(
        Q.from_(_fsi).join(_fc).on(_fc.id == _fsi.fee_category_id)
        .select(_fsi.star, _fc.name.as_("category_name"))
        .where(_fsi.fee_structure_id == P())
        .orderby(_fsi.sort_order)
        .get_sql(),
        (structure_id,)
    ).fetchall()
    data["items"] = [dict(i) for i in items]
    ok(data)


def list_fee_structures(conn, args):
    _fs = Table("educlaw_fee_structure")
    q = Q.from_(_fs).select(_fs.star)
    params = []

    if getattr(args, "program_id", None):
        q = q.where(_fs.program_id == P()); params.append(args.program_id)
    if getattr(args, "academic_term_id", None):
        q = q.where(_fs.academic_term_id == P()); params.append(args.academic_term_id)
    if getattr(args, "grade_level", None):
        q = q.where(_fs.grade_level == P()); params.append(args.grade_level)
    if getattr(args, "is_active", None) is not None:
        q = q.where(_fs.is_active == P()); params.append(int(args.is_active))
    if getattr(args, "company_id", None):
        q = q.where(_fs.company_id == P()); params.append(args.company_id)

    q = q.orderby(_fs.name)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"fee_structures": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# SCHOLARSHIP
# ─────────────────────────────────────────────────────────────────────────────

def add_scholarship(conn, args):
    name = getattr(args, "name", None)
    student_id = getattr(args, "student_id", None)
    discount_type = getattr(args, "discount_type", None)
    discount_amount = getattr(args, "discount_amount", None)
    company_id = getattr(args, "company_id", None)

    if not name:
        err("--name is required")
    if not student_id:
        err("--student-id is required")
    if not discount_type:
        err("--discount-type is required (fixed or percentage)")
    if discount_type not in ("fixed", "percentage"):
        err("--discount-type must be 'fixed' or 'percentage'")
    if not discount_amount:
        err("--discount-amount is required")
    if not company_id:
        err("--company-id is required")

    if _d(discount_amount) < 0:
        err("--discount-amount must be >= 0")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")
    if dict(student_row)["status"] != "active":
        err("Student must be active to receive scholarship")

    academic_term_id = getattr(args, "academic_term_id", None)
    if academic_term_id:
        if not conn.execute(Q.from_(Table("educlaw_academic_term")).select(Field("id")).where(Field("id") == P()).get_sql(), (academic_term_id,)).fetchone():
            err(f"Academic term {academic_term_id} not found")

    applies_to_category_id = getattr(args, "applies_to_category_id", None)
    if applies_to_category_id:
        if not conn.execute(Q.from_(Table("educlaw_fee_category")).select(Field("id")).where(Field("id") == P()).get_sql(), (applies_to_category_id,)).fetchone():
            err(f"Fee category {applies_to_category_id} not found")

    schol_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_scholarship", {"id": P(), "name": P(), "student_id": P(), "academic_term_id": P(), "discount_type": P(), "discount_amount": P(), "applies_to_category_id": P(), "scholarship_status": P(), "reason": P(), "approved_by": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})


    conn.execute(sql,
        (schol_id, name, student_id, academic_term_id, discount_type,
         str(_d(discount_amount)), applies_to_category_id, "active",
         getattr(args, "reason", None) or "",
         getattr(args, "approved_by", None) or "",
         company_id, now, now, getattr(args, "user_id", None) or "")
    )

    audit(conn, SKILL, "edu-add-scholarship", "educlaw_scholarship", schol_id,
          new_values={"name": name, "student_id": student_id, "discount_type": discount_type})
    conn.commit()
    ok({"id": schol_id, "name": name, "student_id": student_id,
        "discount_type": discount_type, "discount_amount": str(_d(discount_amount)),
        "scholarship_status": "active"})


def update_scholarship(conn, args):
    scholarship_id = getattr(args, "scholarship_id", None)
    if not scholarship_id:
        err("--scholarship-id is required")

    row = conn.execute(Q.from_(Table("educlaw_scholarship")).select(Table("educlaw_scholarship").star).where(Field("id") == P()).get_sql(), (scholarship_id,)).fetchone()
    if not row:
        err(f"Scholarship {scholarship_id} not found")

    updates, params, changed = [], [], []

    if getattr(args, "name", None) is not None:
        updates.append("name = ?"); params.append(args.name); changed.append("name")
    if getattr(args, "discount_type", None) is not None:
        if args.discount_type not in ("fixed", "percentage"):
            err("--discount-type must be 'fixed' or 'percentage'")
        updates.append("discount_type = ?"); params.append(args.discount_type)
        changed.append("discount_type")
    if getattr(args, "discount_amount", None) is not None:
        updates.append("discount_amount = ?"); params.append(str(_d(args.discount_amount)))
        changed.append("discount_amount")
    if getattr(args, "scholarship_status", None) is not None:
        if args.scholarship_status not in ("active", "expired", "revoked"):
            err("--scholarship-status must be active, expired, or revoked")
        updates.append("scholarship_status = ?"); params.append(args.scholarship_status)
        changed.append("scholarship_status")
    if getattr(args, "reason", None) is not None:
        updates.append("reason = ?"); params.append(args.reason); changed.append("reason")
    if getattr(args, "approved_by", None) is not None:
        updates.append("approved_by = ?"); params.append(args.approved_by)
        changed.append("approved_by")

    if not changed:
        err("No fields to update")

    updates.append(f"updated_at = {sql_now()}")
    params.append(scholarship_id)
    conn.execute(  # PyPika: skipped — dynamic column set built conditionally
        f"UPDATE educlaw_scholarship SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    ok({"id": scholarship_id, "updated_fields": changed})


def list_scholarships(conn, args):
    _sch = Table("educlaw_scholarship")
    q = Q.from_(_sch).select(_sch.star)
    params = []

    if getattr(args, "student_id", None):
        q = q.where(_sch.student_id == P()); params.append(args.student_id)
    if getattr(args, "academic_term_id", None):
        q = q.where(_sch.academic_term_id == P()); params.append(args.academic_term_id)
    if getattr(args, "scholarship_status", None):
        q = q.where(_sch.scholarship_status == P()); params.append(args.scholarship_status)
    if getattr(args, "company_id", None):
        q = q.where(_sch.company_id == P()); params.append(args.company_id)

    q = q.orderby(_sch.created_at, order=Order.desc)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"scholarships": [dict(r) for r in rows], "count": len(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# FEE INVOICE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def _apply_scholarships_to_lines(conn, student_id, academic_term_id, lines):
    """Discount each structure line through the student's active scholarships.

    Scholarships read via PyPika: this student's, active, either open to
    every term or to this one, oldest first. A scholarship with no
    ``applies_to_category_id`` targets every line; one naming a category
    targets only that category's line, applying ``0.00`` when the category
    is not on the structure. ``percentage`` takes ``original line amount *
    pct / 100`` (2dp) off each targeted line; ``fixed`` takes its amount
    from the targeted lines in sort order. No line drops below ``0.00``;
    ``applied_discount`` is what was actually taken, in two places.
    """
    _sch = Table("educlaw_scholarship")
    term = academic_term_id or ""
    rows = conn.execute(
        Q.from_(_sch).select(_sch.star)
        .where(_sch.student_id == P())
        .where(_sch.scholarship_status == "active")
        .where((_sch.academic_term_id.isnull()) | (_sch.academic_term_id == P()))
        .orderby(_sch.created_at).orderby(_sch.id)
        .get_sql(),
        (student_id, term),
    ).fetchall()

    state = []
    for ln in lines:
        line = dict(ln)
        amount = _d(line.get("amount", "0")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        state.append({
            "fee_category_id": line.get("fee_category_id"),
            "category_name": line.get("category_name") or "",
            "amount": amount,
            "discount": Decimal("0.00"),
        })

    details = []
    for schol in rows:
        sch = dict(schol)
        applies = sch.get("applies_to_category_id")
        targets = [i for i, entry in enumerate(state)
                   if applies is None or entry["fee_category_id"] == applies]
        taken = Decimal("0.00")
        if sch["discount_type"] == "percentage":
            pct = _d(sch["discount_amount"])
            for i in targets:
                disc = (state[i]["amount"] * pct / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)
                room = state[i]["amount"] - state[i]["discount"]
                take = disc if disc < room else room
                state[i]["discount"] += take
                taken += take
        else:
            remaining = _d(sch["discount_amount"])
            for i in targets:
                if remaining <= 0:
                    break
                room = state[i]["amount"] - state[i]["discount"]
                take = room if room < remaining else remaining
                state[i]["discount"] += take
                taken += take
                remaining -= take
        details.append({
            "scholarship_id": sch["id"],
            "name": sch["name"],
            "discount_type": sch["discount_type"],
            "discount_amount": sch["discount_amount"],
            "applied_discount": str(taken.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)),
        })

    total = sum((entry["discount"] for entry in state), Decimal("0.00"))
    return state, details, total


def generate_fee_invoice(conn, args):
    """Generate fee invoice for program enrollment. Bills the fee structure as a submitted sales invoice."""
    student_id = getattr(args, "student_id", None)
    program_id = getattr(args, "program_id", None)
    academic_term_id = getattr(args, "academic_term_id", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not company_id:
        err("--company-id is required")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")

    student = dict(student_row)

    # Find applicable fee structure
    _fs = Table("educlaw_fee_structure")
    fee_struct = None
    if program_id and academic_term_id:
        fee_struct = conn.execute(
            Q.from_(_fs).select(_fs.star)
            .where(_fs.company_id == P()).where(_fs.program_id == P())
            .where(_fs.academic_term_id == P()).where(_fs.is_active == 1)
            .limit(1).get_sql(),
            (company_id, program_id, academic_term_id)
        ).fetchone()
    if not fee_struct and academic_term_id and student.get("grade_level"):
        fee_struct = conn.execute(
            Q.from_(_fs).select(_fs.star)
            .where(_fs.company_id == P()).where(_fs.grade_level == P())
            .where(_fs.academic_term_id == P()).where(_fs.is_active == 1)
            .limit(1).get_sql(),
            (company_id, student["grade_level"], academic_term_id)
        ).fetchone()

    if not fee_struct:
        err("No active fee structure found for this student/program/term combination")

    fs = dict(fee_struct)

    # A fee structure is billed to a student once: refuse before any write.
    _fi = Table("educlaw_fee_invoice")
    billed = conn.execute(
        Q.from_(_fi).select(_fi.sales_invoice_id)
        .where(_fi.student_id == P()).where(_fi.fee_structure_id == P())
        .where(_fi.invoice_kind == "fee").get_sql(),
        (student_id, fs["id"]),
    ).fetchone()
    if billed:
        err(f"Fee structure {fs['id']} is already billed to student {student_id} (sales invoice {dict(billed)['sales_invoice_id']})")

    # Get line items
    _fsi = Table("educlaw_fee_structure_item")
    _fc = Table("educlaw_fee_category")
    items = conn.execute(
        Q.from_(_fsi).join(_fc).on(_fc.id == _fsi.fee_category_id)
        .select(_fsi.star, _fc.name.as_("category_name"))
        .where(_fsi.fee_structure_id == P())
        .orderby(_fsi.sort_order)
        .get_sql(),
        (fs["id"],)
    ).fetchall()

    # Apply scholarships, per line.
    base_amount = _d(fs["total_amount"])
    state, scholarship_details, total_discount = _apply_scholarships_to_lines(
        conn, student_id, academic_term_id, items)
    total_discount = total_discount.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    final_amount = (base_amount - total_discount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    if final_amount < 0:
        final_amount = Decimal("0.00")
    if final_amount == 0:
        err("Nothing to bill: scholarships cover the whole fee structure")

    db_path = getattr(args, "db_path", None)

    # The student owes the money as a customer. Link them first and commit,
    # so a later failure never leaves an unlinked customer a retry would
    # duplicate.
    customer_id = student.get("customer_id")
    if not customer_id:
        try:
            created_customer = create_customer(
                student.get("full_name") or "", company_id, "individual",
                student.get("email"), db_path=db_path)
        except CrossSkillError as e:
            err(f"Fee invoice could not be created: {e}")
        customer_id = ((created_customer or {}).get("customer_id")
                       or (created_customer or {}).get("id"))
        if not customer_id:
            err("Fee invoice could not be created: customer creation returned no id")
        _st = Table("educlaw_student")
        conn.execute(
            Q.update(_st).set("customer_id", P()).where(_st.id == P()).get_sql(),
            (customer_id, student_id))
        conn.commit()

    # One service item per billed line, then the draft invoice itself.
    try:
        item_ids = []
        for line in state:
            item_ids.append(ensure_service_item(
                company_id, db_path,
                item_code="EDU-FEE-%s" % line["fee_category_id"],
                item_name=line["category_name"] or line["fee_category_id"]))
        billed_lines = []
        for item_id, line in zip(item_ids, state):
            net_line = (line["amount"] - line["discount"]).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            billed_lines.append({"item_id": item_id, "qty": "1",
                                 "rate": str(net_line)})
        posting_date = getattr(args, "posting_date", None) or date.today().isoformat()
        created_invoice = create_invoice(
            customer_id=customer_id, items=billed_lines, company_id=company_id,
            posting_date=posting_date, due_date=getattr(args, "due_date", None),
            db_path=db_path)
    except CrossSkillError as e:
        err(f"Fee invoice could not be created: {e}")
    si_id = (created_invoice or {}).get("sales_invoice_id")
    if not si_id:
        err("Fee invoice could not be created: sales invoice creation returned no id")

    # The link on educlaw's own side, with its audit line, in one transaction.
    row_id = str(uuid.uuid4())
    now = _now_iso()
    net = str(final_amount)
    sql, _ = insert_row("educlaw_fee_invoice", {"id": P(), "student_id": P(), "invoice_kind": P(), "fee_structure_id": P(), "fee_category_id": P(), "academic_term_id": P(), "sales_invoice_id": P(), "late_fee_for_sales_invoice_id": P(), "amount": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (row_id, student_id, "fee", fs["id"], None, academic_term_id, si_id,
         None, net, company_id, now, getattr(args, "user_id", None) or "")
    )
    audit(conn, SKILL, "edu-generate-fee-invoice", "educlaw_fee_invoice", row_id,
          new_values={"student_id": student_id, "fee_structure_id": fs["id"],
                      "sales_invoice_id": si_id, "amount": net})
    conn.commit()

    # Submit through the selling module. The link row stays when this fails,
    # so a retry is refused as already billed and names the draft.
    try:
        submit_invoice(si_id, db_path=db_path)
    except CrossSkillError as e:
        err(f"Sales invoice {si_id} was created for this fee but could not be submitted: {e}")

    # Send fee_due notification
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (notif_id, "student", student_id, "fee_due",
         "Fee Invoice Generated",
         f"Your fee invoice for the term has been generated. Total due: ${net}",
         "educlaw_fee_invoice", row_id, company_id, now,
         getattr(args, "user_id", None) or "")
    )
    conn.commit()

    line_items = []
    for raw, line in zip(items, state):
        entry = dict(raw)
        entry["discount"] = str(line["discount"].quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP))
        entry["billed_amount"] = str((line["amount"] - line["discount"]).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP))
        line_items.append(entry)

    ok({
        "invoice_id": row_id,
        "sales_invoice_id": si_id,
        "sales_invoice_status": "submitted",
        "customer_id": customer_id,
        "student_id": student_id,
        "fee_structure_id": fs["id"],
        "base_amount": str(base_amount),
        "total_discount": str(total_discount),
        "final_amount": net,
        "line_items": line_items,
        "scholarships_applied": scholarship_details,
        "generated_at": now,
    })


def list_fee_invoices(conn, args):
    """List fee invoices. Reads from sales_invoice filtered by student's customer_id."""
    student_id = getattr(args, "student_id", None)

    # Try to read from sales_invoice if erpclaw-selling is available
    if student_id:
        student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Field("customer_id")).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
        if not student_row:
            err(f"Student {student_id} not found")
        customer_id = dict(student_row).get("customer_id")
        if customer_id:
            try:
                _si = Table("sales_invoice")
                invoices = conn.execute(
                    Q.from_(_si).select(_si.star).where(_si.customer_id == P())
                    .orderby(_si.posting_date, order=Order.desc).get_sql(),
                    (customer_id,)
                ).fetchall()
                ok({"student_id": student_id, "invoices": [dict(i) for i in invoices],
                    "count": len(invoices)})
                return
            except Exception:
                pass

    ok({"student_id": student_id, "invoices": [],
        "message": "Connect erpclaw-selling to view invoices"})


def get_student_account(conn, args):
    """Full financial summary for student."""
    student_id = getattr(args, "student_id", None)
    if not student_id:
        err("--student-id is required")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")

    student = dict(student_row)
    customer_id = student.get("customer_id")

    invoices = []
    payments = []
    outstanding = Decimal("0")

    if customer_id:
        _si = Table("sales_invoice")
        inv_rows = conn.execute(
            Q.from_(_si).select(_si.id, _si.naming_series, _si.posting_date, _si.grand_total,
                                _si.status, _si.outstanding_amount)
            .where(_si.customer_id == P())
            .orderby(_si.posting_date, order=Order.desc).get_sql(),
            (customer_id,)
        ).fetchall()
        invoices = [dict(r) for r in inv_rows]
        for inv in invoices:
            outstanding += _d(inv.get("outstanding_amount", "0"))

        _pe = Table("payment_entry")
        pe_rows = conn.execute(
            Q.from_(_pe).select(_pe.id, _pe.naming_series, _pe.posting_date,
                                _pe.paid_amount, _pe.unallocated_amount)
            .where(_pe.party_type == P()).where(_pe.party_id == P()).where(_pe.status == P())
            .orderby(_pe.posting_date, order=Order.desc).orderby(_pe.id)
            .get_sql(),
            ("customer", customer_id, "submitted")
        ).fetchall()
        payments = []
        for pe_row in pe_rows:
            entry = dict(pe_row)
            entry["allocations"] = []
            payments.append(entry)
        if payments:
            _pa = Table("payment_allocation")
            _pe2 = Table("payment_entry")
            alloc_rows = conn.execute(
                Q.from_(_pa).join(_pe2).on(_pa.payment_entry_id == _pe2.id)
                .select(_pa.payment_entry_id, _pa.voucher_type, _pa.voucher_id,
                        _pa.allocated_amount)
                .where(_pe2.party_type == P()).where(_pe2.party_id == P())
                .where(_pe2.status == P()).where(_pa.delinked == P())
                .orderby(_pa.voucher_id)
                .get_sql(),
                ("customer", customer_id, "submitted", 0)
            ).fetchall()
            by_entry = {}
            for alloc_row in alloc_rows:
                alloc = dict(alloc_row)
                by_entry.setdefault(alloc.pop("payment_entry_id"), []).append({
                    "voucher_type": alloc["voucher_type"],
                    "voucher_id": alloc["voucher_id"],
                    "allocated_amount": alloc["allocated_amount"],
                })
            for entry in payments:
                entry["allocations"] = by_entry.get(entry["id"], [])

    _sch = Table("educlaw_scholarship")
    scholarships = conn.execute(
        Q.from_(_sch).select(_sch.star)
        .where(_sch.student_id == P()).where(_sch.scholarship_status == 'active')
        .get_sql(),
        (student_id,)
    ).fetchall()

    ok({
        "student_id": student_id,
        "customer_id": customer_id,
        "invoices": invoices,
        "payments": payments,
        "outstanding_balance": str(outstanding),
        "active_scholarships": [dict(s) for s in scholarships],
    })


def get_outstanding_fees(conn, args):
    """List all students with outstanding fees past due date."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    today = date.today().isoformat()
    _st = Table("educlaw_student")
    students = conn.execute(
        Q.from_(_st).select(_st.id, _st.naming_series, _st.full_name, _st.customer_id, _st.email)
        .where(_st.company_id == P()).where(_st.status == 'active')
        .get_sql(),
        (company_id,)
    ).fetchall()

    outstanding_list = []
    for student in students:
        s = dict(student)
        if not s.get("customer_id"):
            continue
        try:
            _si = Table("sales_invoice")
            overdue = conn.execute(
                Q.from_(_si).select(_si.id, _si.posting_date, _si.due_date,
                                    _si.grand_total, _si.outstanding_amount, _si.status)
                .where(_si.customer_id == P())
                .where(_si.status.isin(['submitted', 'partially_paid', 'overdue']))
                .where(_si.due_date < P())
                # outstanding_amount is TEXT: compare its numeric value, so an
                # invoice stored with outstanding "0.00" is not listed.
                .where(fn.Cast(_si.outstanding_amount, "NUMERIC") > 0)
                .get_sql(),
                (s["customer_id"], today)
            ).fetchall()
            if overdue:
                total_outstanding = sum(_d(o["outstanding_amount"]) for o in overdue)
                outstanding_list.append({
                    "student_id": s["id"],
                    "naming_series": s["naming_series"],
                    "full_name": s["full_name"],
                    "email": s["email"],
                    "total_outstanding": str(total_outstanding),
                    "overdue_invoices": [dict(o) for o in overdue],
                })
        except Exception:
            pass

    ok({"company_id": company_id, "outstanding_count": len(outstanding_list),
        "outstanding_students": outstanding_list})


def apply_late_fee(conn, args):
    """Apply late fee to an overdue fee invoice, once per overdue invoice."""
    student_id = getattr(args, "student_id", None)
    fee_category_id = getattr(args, "fee_category_id", None)
    amount = getattr(args, "amount", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not fee_category_id:
        err("--fee-category-id is required")
    if not amount:
        err("--amount is required")
    if not company_id:
        err("--company-id is required")
    if _d(amount) <= 0:
        err("--amount must be greater than 0")

    student_row = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("id") == P()).get_sql(), (student_id,)).fetchone()
    if not student_row:
        err(f"Student {student_id} not found")
    student = dict(student_row)
    cat_row = conn.execute(Q.from_(Table("educlaw_fee_category")).select(Table("educlaw_fee_category").star).where(Field("id") == P()).get_sql(), (fee_category_id,)).fetchone()
    if not cat_row:
        err(f"Fee category {fee_category_id} not found")

    try:
        fee_amount = Decimal(str(amount))
    except InvalidOperation:
        err("--amount must have at most two decimal places")
    if not fee_amount.is_finite() or fee_amount.as_tuple().exponent < -2:
        err("--amount must have at most two decimal places")
    norm = str(fee_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    sales_invoice_id = getattr(args, "sales_invoice_id", None)
    if not sales_invoice_id:
        err("--sales-invoice-id is required")
    db_path = getattr(args, "db_path", None)

    _fi = Table("educlaw_fee_invoice")
    fee_row = conn.execute(
        Q.from_(_fi).select(_fi.star)
        .where(_fi.sales_invoice_id == P()).where(_fi.student_id == P())
        .where(_fi.invoice_kind == "fee").get_sql(),
        (sales_invoice_id, student_id)).fetchone()
    if not fee_row:
        err(f"Sales invoice {sales_invoice_id} is not a fee invoice for student {student_id}")
    prior = conn.execute(
        Q.from_(_fi).select(_fi.sales_invoice_id)
        .where(_fi.late_fee_for_sales_invoice_id == P()).get_sql(),
        (sales_invoice_id,)).fetchone()
    if prior:
        err(f"A late fee was already applied to sales invoice {sales_invoice_id} (late fee invoice {dict(prior)['sales_invoice_id']})")

    _si = Table("sales_invoice")
    inv_row = conn.execute(
        Q.from_(_si).select(_si.star).where(_si.id == P()).get_sql(),
        (sales_invoice_id,)).fetchone()
    if not inv_row:
        err(f"Sales invoice {sales_invoice_id} is not a fee invoice for student {student_id}")
    inv = dict(inv_row)
    fee_link = dict(fee_row)
    link_company = fee_link.get("company_id") or inv.get("company_id")
    if link_company != company_id:
        err(f"Sales invoice {sales_invoice_id} belongs to company {link_company}, not {company_id}")
    if student.get("company_id") != company_id:
        err(f"Student {student_id} belongs to company {student.get('company_id')}, not {company_id}")
    if dict(cat_row).get("company_id") != company_id:
        err(f"Fee category {fee_category_id} belongs to company {dict(cat_row).get('company_id')}, not {company_id}")
    if inv.get("status") not in ("submitted", "partially_paid", "overdue") or _d(inv.get("outstanding_amount", "0")) <= 0:
        err(f"Sales invoice {sales_invoice_id} is {inv.get('status')}; a late fee applies only to an unpaid submitted invoice")
    posting_date = getattr(args, "posting_date", None) or date.today().isoformat()
    if not inv.get("due_date"):
        err(f"Sales invoice {sales_invoice_id} has no due date")
    if not str(inv.get("due_date")) < str(posting_date):
        err(f"Sales invoice {sales_invoice_id} is not overdue (due {inv.get('due_date')})")

    category = dict(cat_row)
    try:
        item_id = ensure_service_item(
            company_id, db_path,
            item_code="EDU-FEE-%s" % fee_category_id,
            item_name=category.get("name") or fee_category_id)
        created = create_invoice(
            customer_id=inv["customer_id"],
            items=[{"item_id": item_id, "qty": "1", "rate": norm}],
            company_id=company_id, posting_date=posting_date,
            db_path=db_path)
    except CrossSkillError as e:
        err(f"Late fee could not be created: {e}")
    late_si_id = (created or {}).get("sales_invoice_id")
    if not late_si_id:
        err("Late fee could not be created: sales invoice creation returned no id")

    row_id = str(uuid.uuid4())
    now = _now_iso()
    sql, _ = insert_row("educlaw_fee_invoice", {"id": P(), "student_id": P(), "invoice_kind": P(), "fee_structure_id": P(), "fee_category_id": P(), "academic_term_id": P(), "sales_invoice_id": P(), "late_fee_for_sales_invoice_id": P(), "amount": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (row_id, student_id, "late_fee", None, fee_category_id, None,
         late_si_id, sales_invoice_id, norm, company_id, now,
         getattr(args, "user_id", None) or "")
    )
    audit(conn, SKILL, "edu-apply-late-fee", "educlaw_fee_invoice", row_id,
          new_values={"student_id": student_id,
                      "sales_invoice_id": late_si_id,
                      "late_fee_for_sales_invoice_id": sales_invoice_id,
                      "amount": norm})
    conn.commit()

    # Submit through the selling module; the link row stays when this fails.
    try:
        submit_invoice(late_si_id, db_path=db_path)
    except CrossSkillError as e:
        err(f"Sales invoice {late_si_id} was created for this fee but could not be submitted: {e}")

    now2 = _now_iso()
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {"id": P(), "recipient_type": P(), "recipient_id": P(), "notification_type": P(), "title": P(), "message": P(), "reference_type": P(), "reference_id": P(), "company_id": P(), "created_at": P(), "created_by": P()})

    conn.execute(sql,
        (notif_id, "student", student_id, "fee_due",
         "Late Fee Applied",
         f"A late fee of ${norm} has been applied to your account.",
         "educlaw_fee_invoice", row_id, company_id, now2,
         getattr(args, "user_id", None) or "")
    )
    conn.commit()

    ok({
        "student_id": student_id,
        "late_fee_amount": norm,
        "fee_category_id": fee_category_id,
        "overdue_sales_invoice_id": sales_invoice_id,
        "sales_invoice_id": late_si_id,
        "applied_at": now2,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ONLINE PAYMENT METHODS
# ─────────────────────────────────────────────────────────────────────────────

VALID_PAYMENT_METHOD_TYPES = ("ach", "credit_card", "debit_card")


def add_payment_method(conn, args):
    """Register a payment method for a guardian (tokenized, no raw card data stored)."""
    guardian_id = getattr(args, "guardian_id", None)
    method_type = getattr(args, "payment_method_type", None) or getattr(args, "method_type", None)
    company_id = getattr(args, "company_id", None)

    if not guardian_id:
        err("--guardian-id is required")
    if not method_type:
        err("--payment-method-type is required (ach, credit_card, debit_card)")
    if method_type not in VALID_PAYMENT_METHOD_TYPES:
        err(f"--payment-method-type must be one of: {', '.join(VALID_PAYMENT_METHOD_TYPES)}")
    if not company_id:
        err("--company-id is required")

    # Verify guardian exists
    _g = Table("educlaw_guardian")
    if not conn.execute(Q.from_(_g).select(_g.id).where(_g.id == P()).get_sql(), (guardian_id,)).fetchone():
        err(f"Guardian {guardian_id} not found")

    pm_id = str(uuid.uuid4())
    now = _now_iso()
    is_default = int(getattr(args, "is_default", None) or 0)
    autopay = int(getattr(args, "autopay_enabled", None) or 0)

    # If this is the first payment method, make it default
    existing = conn.execute(
        Q.from_(Table("educlaw_payment_method")).select(fn.Count(Field("id")).as_("cnt"))
        .where(Field("guardian_id") == P()).where(Field("status") == "active")
        .get_sql(), (guardian_id,)
    ).fetchone()
    if existing and dict(existing)["cnt"] == 0:
        is_default = 1

    # If setting as default, unset other defaults
    if is_default:
        conn.execute(
            "UPDATE educlaw_payment_method SET is_default = 0 WHERE guardian_id = ? AND status = 'active'",
            (guardian_id,)
        )

    sql, _ = insert_row("educlaw_payment_method", {
        "id": P(), "guardian_id": P(), "method_type": P(),
        "last_four": P(), "is_default": P(), "autopay_enabled": P(),
        "external_token": P(), "status": P(), "company_id": P(),
        "created_at": P(),
    })
    conn.execute(sql, (
        pm_id, guardian_id, method_type,
        getattr(args, "last_four", None) or "",
        is_default, autopay,
        getattr(args, "external_token", None) or "",
        "active", company_id, now,
    ))
    audit(conn, SKILL, "edu-add-payment-method", "educlaw_payment_method", pm_id,
          new_values={"guardian_id": guardian_id, "method_type": method_type})
    conn.commit()
    ok({"id": pm_id, "guardian_id": guardian_id, "method_type": method_type,
        "is_default": is_default, "status": "active"})


def list_payment_methods(conn, args):
    """List payment methods for a guardian."""
    guardian_id = getattr(args, "guardian_id", None)
    if not guardian_id:
        err("--guardian-id is required")

    _pm = Table("educlaw_payment_method")
    q = Q.from_(_pm).select(_pm.star).where(_pm.guardian_id == P())
    params = [guardian_id]

    status = getattr(args, "status", None)
    if status:
        q = q.where(_pm.status == P())
        params.append(status)
    else:
        q = q.where(_pm.status == "active")

    q = q.orderby(_pm.is_default, order=Order.desc).orderby(_pm.created_at, order=Order.desc)
    rows = conn.execute(q.get_sql(), params).fetchall()

    # Mask tokens for security
    result = []
    for r in rows:
        d = dict(r)
        d.pop("external_token", None)
        result.append(d)

    ok({"guardian_id": guardian_id, "payment_methods": result, "count": len(result)})


def portal_pay_fee(conn, args):
    """Request an online fee payment (records a request; no money moves until the school records the payment).

    No payment gateway exists, so this action never takes a payment, posts to
    the ledger, or writes to any foundation table. It checks the guardian-student
    link and the guardian's active payment method, reads the student's open fee
    invoices, refuses when nothing is outstanding or when the requested amount
    exceeds the outstanding total, and otherwise records a notification that a
    payment was requested. The balance is unchanged until the school records the
    payment received against the invoice.
    """
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    amount = getattr(args, "amount", None)
    company_id = getattr(args, "company_id", None)

    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")
    if not amount:
        err("--amount is required")
    if not company_id:
        err("--company-id is required")

    pay_amount = _d(amount)
    if pay_amount <= 0:
        err("--amount must be greater than 0")

    # Verify guardian-student link
    _sg = Table("educlaw_student_guardian")
    link = conn.execute(
        Q.from_(_sg).select(Field("id"))
        .where(_sg.guardian_id == P()).where(_sg.student_id == P())
        .get_sql(), (guardian_id, student_id)
    ).fetchone()
    if not link:
        err("Guardian is not linked to this student")

    # Find default payment method
    _pm = Table("educlaw_payment_method")
    pm_row = conn.execute(
        Q.from_(_pm).select(_pm.star)
        .where(_pm.guardian_id == P()).where(_pm.status == "active")
        .orderby(_pm.is_default, order=Order.desc)
        .limit(1).get_sql(), (guardian_id,)
    ).fetchone()
    if not pm_row:
        err("No active payment method found. Add a payment method first.")

    pm = dict(pm_row)

    # Read the student's open fee invoices for the company (read only): the
    # sales_invoice rows linked through educlaw_fee_invoice.sales_invoice_id
    # with an open status and an outstanding amount above zero.
    _fi = Table("educlaw_fee_invoice")
    _si = Table("sales_invoice")
    open_rows = conn.execute(
        Q.from_(_fi).join(_si).on(_si.id == _fi.sales_invoice_id)
        .select(_si.id, _si.outstanding_amount)
        .where(_fi.student_id == P()).where(_fi.company_id == P())
        .where(_si.company_id == P())
        .where(_si.status.isin(["submitted", "partially_paid", "overdue"]))
        .where(fn.Cast(_si.outstanding_amount, "NUMERIC") > 0)
        .get_sql(), (student_id, company_id, company_id)
    ).fetchall()

    invoices = []
    total = Decimal("0")
    for _row in open_rows:
        _inv = dict(_row)
        _amt = _d(_inv.get("outstanding_amount", "0"))
        if _amt <= 0:
            continue
        _amt_str = str(_amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        invoices.append({"id": _inv["id"], "sales_invoice_id": _inv["id"],
                         "outstanding_amount": _amt_str})
        total += _amt

    if not invoices or total <= 0:
        err("No outstanding fees for this student")

    pay_str = str(pay_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    total_str = str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if pay_amount > total:
        err(f"Requested amount {pay_str} exceeds outstanding fees of {total_str} for this student")

    now = _now_iso()
    payment_ref = str(uuid.uuid4())

    # Record the request only. No money moves: never write to sales_invoice,
    # payment_entry, gl_entry or any other foundation table.
    notif_id = str(uuid.uuid4())
    sql, _ = insert_row("educlaw_notification", {
        "id": P(), "recipient_type": P(), "recipient_id": P(),
        "notification_type": P(), "title": P(), "message": P(),
        "reference_type": P(), "reference_id": P(),
        "company_id": P(), "created_at": P(), "created_by": P(),
    })
    conn.execute(sql, (
        notif_id, "guardian", guardian_id, "payment",
        "Payment Request Received",
        f"Payment request of ${pay_str} received for student account via {pm['method_type']} ending in {pm['last_four']}. "
        f"No payment has been taken and the balance of ${total_str} is unchanged until the school records the payment.",
        "educlaw_payment_method", pm["id"],
        company_id, now, guardian_id,
    ))
    conn.commit()

    ok({
        "payment_reference": payment_ref,
        "guardian_id": guardian_id,
        "student_id": student_id,
        "amount": pay_str,
        "outstanding_amount": total_str,
        "invoices": invoices,
        "payment_method_id": pm["id"],
        "method_type": pm["method_type"],
        "last_four": pm["last_four"],
        "payment_status": "requested",
        "submitted_at": now,
        "note": "No payment was taken. This records a request only; the balance is unchanged until the school records the payment received against the invoice.",
    })


def payment_receipt(conn, args):
    """Generate a payment receipt for a guardian's payment."""
    guardian_id = getattr(args, "guardian_id", None)
    student_id = getattr(args, "student_id", None)
    amount = getattr(args, "amount", None)
    company_id = getattr(args, "company_id", None)

    if not guardian_id:
        err("--guardian-id is required")
    if not student_id:
        err("--student-id is required")
    if not amount:
        err("--amount is required")
    if not company_id:
        err("--company-id is required")

    # Get guardian info
    _g = Table("educlaw_guardian")
    g_row = conn.execute(
        Q.from_(_g).select(_g.full_name, _g.email).where(_g.id == P()).get_sql(),
        (guardian_id,)
    ).fetchone()
    if not g_row:
        err(f"Guardian {guardian_id} not found")

    # Get student info
    _st = Table("educlaw_student")
    st_row = conn.execute(
        Q.from_(_st).select(_st.full_name, _st.naming_series).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone()
    if not st_row:
        err(f"Student {student_id} not found")

    guardian = dict(g_row)
    student = dict(st_row)

    # Get company info
    _co = Table("company")
    co_row = conn.execute(
        Q.from_(_co).select(_co.name).where(_co.id == P()).get_sql(),
        (company_id,)
    ).fetchone()
    company_name = dict(co_row)["name"] if co_row else company_id

    now = _now_iso()
    receipt_number = f"REC-{uuid.uuid4().hex[:8].upper()}"

    ok({
        "receipt_number": receipt_number,
        "guardian_name": guardian["full_name"],
        "guardian_email": guardian["email"],
        "student_name": student["full_name"],
        "student_id_series": student["naming_series"],
        "amount": str(_d(amount)),
        "company_name": company_name,
        "payment_date": now,
        "note": "This receipt confirms payment submission.",
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-fee-category": add_fee_category,
    "edu-update-fee-category": update_fee_category,
    "edu-list-fee-categories": list_fee_categories,
    "edu-add-fee-structure": add_fee_structure,
    "edu-update-fee-structure": update_fee_structure,
    "edu-get-fee-structure": get_fee_structure,
    "edu-list-fee-structures": list_fee_structures,
    "edu-add-scholarship": add_scholarship,
    "edu-update-scholarship": update_scholarship,
    "edu-list-scholarships": list_scholarships,
    "edu-generate-fee-invoice": generate_fee_invoice,
    "edu-list-fee-invoices": list_fee_invoices,
    "edu-get-student-account": get_student_account,
    "edu-get-outstanding-fees": get_outstanding_fees,
    "edu-apply-late-fee": apply_late_fee,
    "edu-add-payment-method": add_payment_method,
    "edu-list-payment-methods": list_payment_methods,
    "edu-portal-pay-fee": portal_pay_fee,
    "edu-payment-receipt": payment_receipt,
}
