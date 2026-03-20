"""EduClaw — library management domain module

Actions for library catalog, circulation (checkout/return/renew),
overdue tracking, inventory reports, and student reading history.

Imported by db_query.py (unified router).
"""
import json
import os
import sys
import uuid
from datetime import datetime, date, timedelta, timezone
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

VALID_ITEM_TYPES = ("book", "periodical", "dvd", "digital", "equipment", "other")
VALID_ITEM_STATUSES = ("available", "checked_out", "reserved", "lost", "damaged")

DEFAULT_LOAN_DAYS = 14
DEFAULT_RENEWAL_LIMIT = 2
DAILY_FINE_RATE = Decimal("0.25")


# ─────────────────────────────────────────────────────────────────────────────
# LIBRARY ITEM CRUD
# ─────────────────────────────────────────────────────────────────────────────

def add_library_item(conn, args):
    """Add a new item to the library catalog."""
    title = getattr(args, "title", None) or getattr(args, "name", None)
    company_id = getattr(args, "company_id", None)

    if not title:
        err("--title is required (or --name)")
    if not company_id:
        err("--company-id is required")

    item_type = getattr(args, "item_type", None) or "book"
    if item_type not in VALID_ITEM_TYPES:
        err(f"Invalid item type. Must be one of: {', '.join(VALID_ITEM_TYPES)}")

    copy_count = int(getattr(args, "capacity", None) or 1)
    if copy_count < 1:
        err("Total copies must be at least 1")

    item_id = str(uuid.uuid4())
    now = _now_iso()

    sql, _ = insert_row("educlaw_library_item", {
        "id": P(), "title": P(), "author": P(), "isbn": P(),
        "item_type": P(), "category": P(), "location": P(),
        "copy_count": P(), "available_copies": P(),
        "status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (
        item_id, title,
        getattr(args, "description", None) or "",  # author mapped to description
        getattr(args, "code", None) or "",  # isbn mapped to code
        item_type,
        getattr(args, "room_type", None) or "",  # category mapped to room-type
        getattr(args, "building", None) or "",  # location mapped to building
        copy_count, copy_count,
        "available", company_id, now,
    ))
    audit(conn, SKILL, "edu-add-library-item", "educlaw_library_item", item_id,
          new_values={"title": title, "item_type": item_type})
    conn.commit()
    ok({"id": item_id, "title": title, "item_type": item_type,
        "copy_count": copy_count, "status": "available"})


def list_library_items(conn, args):
    """List library catalog items with search and filters."""
    _li = Table("educlaw_library_item")
    q = Q.from_(_li).select(_li.star)
    params = []

    company_id = getattr(args, "company_id", None)
    if company_id:
        q = q.where(_li.company_id == P())
        params.append(company_id)

    search = getattr(args, "search", None)
    if search:
        q = q.where(
            (_li.title.like(P())) | (_li.author.like(P())) | (_li.isbn.like(P()))
        )
        search_val = f"%{search}%"
        params.extend([search_val, search_val, search_val])

    item_type = getattr(args, "item_type", None)
    if item_type:
        q = q.where(_li.item_type == P())
        params.append(item_type)

    status = getattr(args, "status", None)
    if status:
        q = q.where(_li.status == P())
        params.append(status)

    q = q.orderby(_li.title)
    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.limit(limit).offset(offset)

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"library_items": [dict(r) for r in rows], "count": len(rows)})


def checkout_item(conn, args):
    """Check out a library item to a student."""
    library_item_id = getattr(args, "library_item_id", None) or getattr(args, "reference_id", None)
    student_id = getattr(args, "student_id", None)

    if not library_item_id:
        err("--reference-id is required (library item ID)")
    if not student_id:
        err("--student-id is required")

    # Verify item exists and has available copies
    _li = Table("educlaw_library_item")
    item_row = conn.execute(
        Q.from_(_li).select(_li.star).where(_li.id == P()).get_sql(),
        (library_item_id,)
    ).fetchone()
    if not item_row:
        err(f"Library item {library_item_id} not found")

    item = dict(item_row)
    if item["available_copies"] <= 0:
        err(f"No copies available for '{item['title']}'")

    # Verify student exists
    _st = Table("educlaw_student")
    st_row = conn.execute(
        Q.from_(_st).select(_st.id, _st.full_name).where(_st.id == P()).get_sql(),
        (student_id,)
    ).fetchone()
    if not st_row:
        err(f"Student {student_id} not found")

    circ_id = str(uuid.uuid4())
    now = _now_iso()
    checkout_date = date.today().isoformat()
    due_date = (date.today() + timedelta(days=DEFAULT_LOAN_DAYS)).isoformat()

    sql, _ = insert_row("educlaw_circulation", {
        "id": P(), "library_item_id": P(), "student_id": P(),
        "checkout_date": P(), "due_date": P(), "return_date": P(),
        "renewed": P(), "fine_amount": P(), "status": P(),
        "created_at": P(),
    })
    conn.execute(sql, (
        circ_id, library_item_id, student_id,
        checkout_date, due_date, "", 0, "0", "checked_out", now,
    ))

    # Decrement available copies
    new_avail = item["available_copies"] - 1
    conn.execute(
        "UPDATE educlaw_library_item SET available_copies = ?, status = ? WHERE id = ?",
        (new_avail, "available" if new_avail > 0 else "checked_out", library_item_id)
    )

    audit(conn, SKILL, "edu-checkout-item", "educlaw_circulation", circ_id,
          new_values={"library_item_id": library_item_id, "student_id": student_id})
    conn.commit()
    ok({
        "circulation_id": circ_id,
        "library_item_id": library_item_id,
        "title": item["title"],
        "student_id": student_id,
        "checkout_date": checkout_date,
        "due_date": due_date,
    })


def return_item(conn, args):
    """Return a checked-out library item."""
    circulation_id = getattr(args, "reference_id", None) or getattr(args, "circulation_id", None)
    if not circulation_id:
        err("--reference-id is required (circulation ID)")

    _circ = Table("educlaw_circulation")
    circ_row = conn.execute(
        Q.from_(_circ).select(_circ.star).where(_circ.id == P()).get_sql(),
        (circulation_id,)
    ).fetchone()
    if not circ_row:
        err(f"Circulation record {circulation_id} not found")

    circ = dict(circ_row)
    if circ["status"] not in ("checked_out", "overdue"):
        err(f"Item is not checked out (current status: {circ['status']})")

    return_date = date.today().isoformat()

    # Calculate fine if overdue
    fine = Decimal("0")
    due = date.fromisoformat(circ["due_date"])
    if date.today() > due:
        overdue_days = (date.today() - due).days
        fine = (DAILY_FINE_RATE * Decimal(str(overdue_days))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    conn.execute(
        "UPDATE educlaw_circulation SET status = 'returned', return_date = ?, fine_amount = ? WHERE id = ?",
        (return_date, str(fine), circulation_id)
    )

    # Increment available copies
    _li = Table("educlaw_library_item")
    item_row = conn.execute(
        Q.from_(_li).select(_li.available_copies, _li.copy_count).where(_li.id == P()).get_sql(),
        (circ["library_item_id"],)
    ).fetchone()
    if item_row:
        item = dict(item_row)
        new_avail = min(item["available_copies"] + 1, item["copy_count"])
        conn.execute(
            "UPDATE educlaw_library_item SET available_copies = ?, status = 'available' WHERE id = ?",
            (new_avail, circ["library_item_id"])
        )

    audit(conn, SKILL, "edu-return-item", "educlaw_circulation", circulation_id,
          new_values={"return_date": return_date, "fine_amount": str(fine)})
    conn.commit()
    ok({
        "circulation_id": circulation_id,
        "library_item_id": circ["library_item_id"],
        "return_date": return_date,
        "fine_amount": str(fine),
        "circulation_status": "returned",
    })


def renew_item(conn, args):
    """Renew a checked-out library item (extend due date)."""
    circulation_id = getattr(args, "reference_id", None) or getattr(args, "circulation_id", None)
    if not circulation_id:
        err("--reference-id is required (circulation ID)")

    _circ = Table("educlaw_circulation")
    circ_row = conn.execute(
        Q.from_(_circ).select(_circ.star).where(_circ.id == P()).get_sql(),
        (circulation_id,)
    ).fetchone()
    if not circ_row:
        err(f"Circulation record {circulation_id} not found")

    circ = dict(circ_row)
    if circ["status"] not in ("checked_out", "overdue"):
        err(f"Item is not checked out (current status: {circ['status']})")

    if circ["renewed"] >= DEFAULT_RENEWAL_LIMIT:
        err(f"Maximum renewal limit reached ({DEFAULT_RENEWAL_LIMIT})")

    # Extend due date from today
    new_due = (date.today() + timedelta(days=DEFAULT_LOAN_DAYS)).isoformat()
    new_renewed = circ["renewed"] + 1

    conn.execute(
        "UPDATE educlaw_circulation SET due_date = ?, renewed = ?, status = 'checked_out' WHERE id = ?",
        (new_due, new_renewed, circulation_id)
    )

    audit(conn, SKILL, "edu-renew-item", "educlaw_circulation", circulation_id,
          new_values={"new_due_date": new_due, "renewal_count": new_renewed})
    conn.commit()
    ok({
        "circulation_id": circulation_id,
        "new_due_date": new_due,
        "renewal_count": new_renewed,
        "max_renewals": DEFAULT_RENEWAL_LIMIT,
    })


def list_overdue(conn, args):
    """List all overdue library items."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    today = date.today().isoformat()
    _circ = Table("educlaw_circulation")
    _li = Table("educlaw_library_item")
    _st = Table("educlaw_student")

    rows = conn.execute(
        Q.from_(_circ)
        .join(_li).on(_li.id == _circ.library_item_id)
        .left_join(_st).on(_st.id == _circ.student_id)
        .select(
            _circ.id.as_("circulation_id"),
            _li.title, _li.isbn,
            _st.id.as_("student_id"), _st.full_name.as_("student_name"),
            _st.naming_series.as_("student_series"),
            _circ.checkout_date, _circ.due_date, _circ.renewed,
        )
        .where(_circ.status == "checked_out")
        .where(_circ.due_date < P())
        .where(_li.company_id == P())
        .orderby(_circ.due_date)
        .get_sql(), (today, company_id)
    ).fetchall()

    # Calculate fines
    result = []
    for r in rows:
        d = dict(r)
        due = date.fromisoformat(d["due_date"])
        overdue_days = (date.today() - due).days
        d["overdue_days"] = overdue_days
        d["estimated_fine"] = str(
            (DAILY_FINE_RATE * Decimal(str(overdue_days))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        result.append(d)

    ok({"overdue_items": result, "count": len(result)})


def library_inventory_report(conn, args):
    """Generate a library inventory summary report."""
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    _li = Table("educlaw_library_item")

    # By type
    by_type = conn.execute(
        Q.from_(_li).select(
            _li.item_type,
            fn.Count(_li.id).as_("item_count"),
            fn.Sum(_li.copy_count).as_("copy_count"),
            fn.Sum(_li.available_copies).as_("available_copies"),
        )
        .where(_li.company_id == P())
        .groupby(_li.item_type)
        .orderby(_li.item_type)
        .get_sql(), (company_id,)
    ).fetchall()

    # By status
    by_status = conn.execute(
        Q.from_(_li).select(_li.status, fn.Count(_li.id).as_("count"))
        .where(_li.company_id == P())
        .groupby(_li.status)
        .get_sql(), (company_id,)
    ).fetchall()

    # Totals
    totals = conn.execute(
        Q.from_(_li).select(
            fn.Count(_li.id).as_("total_items"),
            fn.Sum(_li.copy_count).as_("copy_count"),
            fn.Sum(_li.available_copies).as_("total_available"),
        )
        .where(_li.company_id == P())
        .get_sql(), (company_id,)
    ).fetchone()

    t = dict(totals) if totals else {"total_items": 0, "copy_count": 0, "total_available": 0}

    ok({
        "company_id": company_id,
        "total_items": t["total_items"],
        "copy_count": t["copy_count"] or 0,
        "total_available": t["total_available"] or 0,
        "by_type": [dict(r) for r in by_type],
        "by_status": {r["status"]: r["count"] for r in by_status},
    })


def student_reading_history(conn, args):
    """Get a student's library checkout/reading history."""
    student_id = getattr(args, "student_id", None)
    if not student_id:
        err("--student-id is required")

    _circ = Table("educlaw_circulation")
    _li = Table("educlaw_library_item")

    rows = conn.execute(
        Q.from_(_circ).join(_li).on(_li.id == _circ.library_item_id)
        .select(
            _circ.id.as_("circulation_id"),
            _li.title, _li.author, _li.item_type, _li.isbn,
            _circ.checkout_date, _circ.due_date, _circ.return_date,
            _circ.renewed, _circ.fine_amount, _circ.status,
        )
        .where(_circ.student_id == P())
        .orderby(_circ.checkout_date, order=Order.desc)
        .get_sql(), (student_id,)
    ).fetchall()

    total_books_read = sum(1 for r in rows if r["status"] == "returned")
    total_fines = sum(Decimal(str(r["fine_amount"])) for r in rows if r["fine_amount"])

    ok({
        "student_id": student_id,
        "history": [dict(r) for r in rows],
        "total_checkouts": len(rows),
        "total_books_returned": total_books_read,
        "total_fines": str(total_fines),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "edu-add-library-item": add_library_item,
    "edu-list-library-items": list_library_items,
    "edu-checkout-item": checkout_item,
    "edu-return-item": return_item,
    "edu-renew-item": renew_item,
    "edu-list-overdue": list_overdue,
    "edu-library-inventory-report": library_inventory_report,
    "edu-student-reading-history": student_reading_history,
}
