"""EduClaw Higher Education: receivables domain module (2 actions)

Student receivables bridge: one assessed student charge posts to the company
books exactly once as a balanced receivable/revenue pair through the shared
GL seam. Not enrollment, collections, financial aid, or payment processing.
"""
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

try:
    import importlib.util
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row, dynamic_update

    ENTITY_PREFIXES.setdefault("highered_student_charge", "HCHG-")
except ImportError:
    pass

try:
    from erpclaw_lib.gl_posting import insert_gl_entries
    HAS_GL = True
except ImportError:
    HAS_GL = False

SKILL = "highered-educlaw-highered"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_CHARGE_STATUSES = ("draft", "assessed", "posted", "cancelled")
ELIGIBLE_STATUSES = ("assessed", "posted")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _to_money(val):
    if val is None:
        return "0.00"
    return str(round_currency(to_decimal(val)))


def _valid_posting_date(value):
    if not value or not _DATE_RE.match(str(value)):
        return False
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _get_charge(conn, charge_id):
    t = Table("highered_student_charge")
    sql = Q.from_(t).select(t.star).where(Field("id") == P()).get_sql()
    row = conn.execute(sql, (charge_id,)).fetchone()
    return dict(row) if row else None


def _get_account(conn, account_id):
    t = Table("account")
    sql = Q.from_(t).select(t.star).where(Field("id") == P()).get_sql()
    row = conn.execute(sql, (account_id,)).fetchone()
    return dict(row) if row else None


def _validate_posting_account(conn, account_id, company_id, flag, expected_root):
    if not account_id:
        return err(flag + " is required")
    acct = _get_account(conn, account_id)
    if not acct:
        return err(flag + " account " + str(account_id) + " not found")
    if acct.get("company_id") and acct.get("company_id") != company_id:
        return err(flag + " account " + str(account_id) + " belongs to a different company")
    if acct.get("is_group"):
        return err(flag + " account '" + str(acct.get("name", account_id)) + "' is a group account")
    if acct.get("disabled"):
        return err(flag + " account '" + str(acct.get("name", account_id)) + "' is disabled")
    if acct.get("is_frozen"):
        return err(flag + " account '" + str(acct.get("name", account_id)) + "' is frozen")
    if expected_root and acct.get("root_type") and acct.get("root_type") != expected_root:
        return err(flag + " account '" + str(acct.get("name", account_id)) + "' must have root type " + expected_root)
    return acct


def _validate_cost_center(conn, cost_center_id, company_id):
    if not cost_center_id:
        return None
    t = Table("cost_center")
    sql = Q.from_(t).select(t.star).where(Field("id") == P()).get_sql()
    row = conn.execute(sql, (cost_center_id,)).fetchone()
    if not row:
        return err("--cost-center-id cost center " + str(cost_center_id) + " not found")
    cc = dict(row)
    if cc.get("is_group"):
        return err("--cost-center-id cost center '" + str(cc.get("name", cost_center_id)) + "' is a group")
    if cc.get("company_id") and cc.get("company_id") != company_id:
        return err("--cost-center-id cost center '" + str(cc.get("name", cost_center_id)) + "' belongs to a different company")
    return cc


def add_student_charge(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    try:
        amount = _to_money(getattr(args, "amount", None))
    except (ValueError, TypeError) as exc:
        return err("--amount must be a valid decimal: " + str(exc))
    if to_decimal(amount) < Decimal("0"):
        return err("--amount must not be negative")
    charge_date = getattr(args, "charge_date", None) or getattr(args, "posting_date", None) or ""
    charge_status = getattr(args, "charge_status", None) or "assessed"
    if charge_status not in VALID_CHARGE_STATUSES:
        return err("Invalid charge_status: " + str(charge_status))
    description = getattr(args, "description", None) or ""
    charge_id = str(uuid.uuid4())
    now = _now_iso()
    naming = get_next_name(conn, "highered_student_charge", company_id=company_id)
    sql, _ = insert_row("highered_student_charge", {
        "id": P(), "naming_series": P(), "student_id": P(), "description": P(),
        "amount": P(), "charge_date": P(), "charge_status": P(),
        "company_id": P(), "receivable_account_id": P(), "revenue_account_id": P(),
        "cost_center_id": P(), "gl_entry_ids": P(), "posting_date": P(),
        "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql, (charge_id, naming, student_id, description, amount,
          charge_date, charge_status, company_id, "", "", "", "", "", now, now))
    audit(conn, SKILL, "highered-add-student-charge", "highered_student_charge", charge_id,
          new_values={"student_id": student_id, "amount": amount, "charge_status": charge_status})
    conn.commit()
    ok({"id": charge_id, "naming_series": naming, "student_id": student_id,
        "amount": amount, "charge_status": charge_status})


def post_student_charge(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    charge_id = getattr(args, "charge_id", None) or getattr(args, "id", None)
    if not charge_id:
        return err("--charge-id is required")
    raw_amount = getattr(args, "amount", None)
    if raw_amount is None or str(raw_amount).strip() == "":
        return err("--amount is required")
    try:
        req_amount_dec = round_currency(to_decimal(raw_amount))
    except (ValueError, TypeError) as exc:
        return err("--amount must be a valid decimal: " + str(exc))
    if req_amount_dec <= Decimal("0"):
        return err("--amount must be positive")
    req_amount = str(req_amount_dec)
    posting_date = getattr(args, "posting_date", None)
    if not posting_date:
        return err("--posting-date is required")
    if not _valid_posting_date(posting_date):
        return err("--posting-date must be YYYY-MM-DD")
    receivable_account_id = getattr(args, "receivable_account_id", None)
    if not receivable_account_id:
        return err("--receivable-account-id is required")
    revenue_account_id = getattr(args, "revenue_account_id", None)
    if not revenue_account_id:
        return err("--revenue-account-id is required")
    cost_center_id = getattr(args, "cost_center_id", None) or ""
    charge = _get_charge(conn, charge_id)
    if not charge:
        return err("Student charge " + str(charge_id) + " not found")
    if charge.get("company_id") != company_id:
        return err("Student charge " + str(charge_id) + " belongs to a different company")
    status = charge.get("charge_status", "")
    if status not in ELIGIBLE_STATUSES:
        return err("Student charge " + str(charge_id) + " is '" + str(status) + "' and cannot be posted")
    try:
        stored_dec = round_currency(to_decimal(charge.get("amount", "0")))
    except (ValueError, TypeError):
        return err("Student charge " + str(charge_id) + " has an invalid amount")
    if stored_dec <= Decimal("0"):
        return err("Student charge " + str(charge_id) + " has zero amount and cannot be posted")
    if req_amount_dec != stored_dec:
        return err("Amount " + req_amount + " does not match assessed charge amount " + str(stored_dec))
    stored_ids = [s for s in str(charge.get("gl_entry_ids", "") or "").split(",") if s]
    if status == "posted" or stored_ids:
        prev_recv = charge.get("receivable_account_id", "") or ""
        prev_rev = charge.get("revenue_account_id", "") or ""
        prev_cc = charge.get("cost_center_id", "") or ""
        prev_posting = charge.get("posting_date", "") or ""
        if (prev_recv == receivable_account_id and prev_rev == revenue_account_id
                and prev_cc == cost_center_id and prev_posting == posting_date):
            ok({"charge_id": charge_id, "amount": str(stored_dec),
                "posting_date": prev_posting or posting_date,
                "gl_entry_ids": stored_ids})
            return
        return err("Student charge " + str(charge_id) + " is already posted with different accounts or posting date")
    _validate_posting_account(conn, receivable_account_id, company_id,
                              "--receivable-account-id", "asset")
    _validate_posting_account(conn, revenue_account_id, company_id,
                              "--revenue-account-id", "income")
    _validate_cost_center(conn, cost_center_id, company_id)
    if not HAS_GL:
        return err("GL posting is not available")
    amount_text = str(stored_dec)
    try:
        revenue_leg = {"account_id": revenue_account_id, "debit": "0.00", "credit": amount_text}
        if cost_center_id:
            revenue_leg["cost_center_id"] = cost_center_id
        entries = [
            {"account_id": receivable_account_id, "debit": amount_text, "credit": "0.00"},
            revenue_leg,
        ]
        gl_ids = insert_gl_entries(
            conn, entries,
            voucher_type="journal_entry",
            voucher_id=charge_id,
            posting_date=posting_date,
            company_id=company_id,
            remarks="Student charge " + str(charge.get("naming_series") or charge_id),
            entry_set="primary",
        )
        gl_ids_str = ",".join(gl_ids)
        now = _now_iso()
        sql, params = dynamic_update("highered_student_charge", {
            "charge_status": "posted",
            "receivable_account_id": receivable_account_id,
            "revenue_account_id": revenue_account_id,
            "cost_center_id": cost_center_id,
            "gl_entry_ids": gl_ids_str,
            "posting_date": posting_date,
            "updated_at": now,
        }, {"id": charge_id})
        conn.execute(sql, params)
        audit(conn, SKILL, "highered-post-student-charge", "highered_student_charge", charge_id,
              new_values={"charge_status": "posted", "amount": amount_text,
                          "posting_date": posting_date, "gl_entry_count": len(gl_ids)})
        conn.commit()
    except SystemExit:
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return err("GL posting failed for student charge " + str(charge_id) + ": " + str(exc))
    ok({"charge_id": charge_id, "amount": amount_text,
        "posting_date": posting_date, "gl_entry_ids": gl_ids})


ACTIONS = {
    "highered-add-student-charge": add_student_charge,
    "highered-post-student-charge": post_student_charge,
}
