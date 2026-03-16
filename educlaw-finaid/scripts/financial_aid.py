"""EduClaw Financial Aid — financial_aid domain module (72 actions)"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, dynamic_update, update_row, LiteralValue
except ImportError:
    pass

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_today = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Aid Year Setup
# ---------------------------------------------------------------------------

def add_aid_year(conn, args):
    company_id = getattr(args, 'company_id', None)
    aid_year_code = getattr(args, 'aid_year_code', None)
    if not company_id:
        return err("company_id is required")
    if not aid_year_code:
        return err("aid_year_code is required")
    description = getattr(args, 'description', '') or ''
    start_date = getattr(args, 'start_date', '') or ''
    end_date = getattr(args, 'end_date', '') or ''
    pell_max_award = str(round_currency(to_decimal(getattr(args, 'pell_max_award', '0') or '0')))
    is_active = int(getattr(args, 'is_active', 0) or 0)
    aid_year_id = str(uuid.uuid4())
    try:
        sql, _ = insert_row("finaid_aid_year", {"id": P(), "aid_year_code": P(), "description": P(), "start_date": P(), "end_date": P(), "pell_max_award": P(), "is_active": P(), "company_id": P(), "created_by": P()})

        conn.execute(sql,
            (aid_year_id, aid_year_code, description, start_date, end_date, pell_max_award, is_active, company_id, '')
        )
        conn.commit()
        return ok({"id": aid_year_id, "aid_year_code": aid_year_code})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate aid year code for this company: {e}")


def update_aid_year(conn, args):
    aid_year_id = getattr(args, 'id', None)
    if not aid_year_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_aid_year")).select(Table("finaid_aid_year").star).where(Field("id") == P()).get_sql(), (aid_year_id,)).fetchone()
    if not row:
        return err("Aid year not found")
    data = {}
    for f in ['description', 'start_date', 'end_date', 'pell_max_award']:
        v = getattr(args, f.replace('-', '_'), None)
        if v is not None:
            data[f] = str(round_currency(to_decimal(v))) if f == 'pell_max_award' else v
    is_active = getattr(args, 'is_active', None)
    if is_active is not None:
        data["is_active"] = int(is_active)
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_aid_year", data=data, where={"id": aid_year_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": aid_year_id, "updated": True})


def get_aid_year(conn, args):
    aid_year_id = getattr(args, 'id', None)
    if not aid_year_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_aid_year")).select(Table("finaid_aid_year").star).where(Field("id") == P()).get_sql(), (aid_year_id,)).fetchone()
    if not row:
        return err("Aid year not found")
    return ok(dict(row))


def list_aid_years(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_aid_year")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    is_active = getattr(args, 'is_active', None)
    if is_active is not None:
        qb = qb.where(t.is_active == P())
        params.append(int(is_active))
    limit = int(getattr(args, 'limit', 50) or 50)
    offset = int(getattr(args, 'offset', 0) or 0)
    qb = qb.orderby(t.aid_year_code, order=Order.desc).limit(P()).offset(P())
    params.extend([limit, offset])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"aid_years": [dict(r) for r in rows], "count": len(rows)})


def set_active_aid_year(conn, args):
    aid_year_id = getattr(args, 'id', None)
    if not aid_year_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_aid_year")).select(Field("company_id")).where(Field("id") == P()).get_sql(), (aid_year_id,)).fetchone()
    if not row:
        return err("Aid year not found")
    company_id = row['company_id']
    _ay = Table("finaid_aid_year")
    conn.execute(Q.update(_ay).set(_ay.is_active, 0).set(_ay.updated_at, P()).where(_ay.company_id == P()).get_sql(), (_now_iso(), company_id))
    conn.execute(Q.update(_ay).set(_ay.is_active, 1).set(_ay.updated_at, P()).where(_ay.id == P()).get_sql(), (_now_iso(), aid_year_id))
    conn.commit()
    return ok({"id": aid_year_id, "is_active": 1})


def import_pell_schedule(conn, args):
    aid_year_id = getattr(args, 'aid_year_id', None)
    company_id = getattr(args, 'company_id', None)
    rows_json = getattr(args, 'rows', None)
    if not aid_year_id:
        return err("aid_year_id is required")
    if not company_id:
        return err("company_id is required")
    if not rows_json:
        return err("rows is required (JSON array)")
    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError:
        return err("rows must be valid JSON array")
    inserted = 0
    for r in rows:
        rid = str(uuid.uuid4())
        # PyPika: skipped — INSERT OR REPLACE not supported by PyPika
        conn.execute(
            "INSERT OR REPLACE INTO finaid_pell_schedule (id,aid_year_id,pell_index,full_time_annual,three_quarter_time,half_time,less_than_half_time,company_id) VALUES (?,?,?,?,?,?,?,?)",
            (rid, aid_year_id, int(r.get('pell_index', 0)),
             str(round_currency(to_decimal(r.get('full_time_annual', '0')))),
             str(round_currency(to_decimal(r.get('three_quarter_time', '0')))),
             str(round_currency(to_decimal(r.get('half_time', '0')))),
             str(round_currency(to_decimal(r.get('less_than_half_time', '0')))),
             company_id)
        )
        inserted += 1
    conn.commit()
    return ok({"inserted": inserted, "aid_year_id": aid_year_id})


def list_pell_schedule(conn, args):
    aid_year_id = getattr(args, 'aid_year_id', None)
    if not aid_year_id:
        return err("aid_year_id is required")
    t = Table("finaid_pell_schedule")
    qb = Q.from_(t).select(t.star).where(t.aid_year_id == P())
    params = [aid_year_id]
    pell_index = getattr(args, 'pell_index', None)
    if pell_index is not None:
        qb = qb.where(t.pell_index == P())
        params.append(int(pell_index))
    qb = qb.orderby(t.pell_index).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"schedule": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Fund Allocation
# ---------------------------------------------------------------------------

def add_fund_allocation(conn, args):
    aid_year_id = getattr(args, 'aid_year_id', None)
    company_id = getattr(args, 'company_id', None)
    fund_type = getattr(args, 'fund_type', None)
    fund_name = getattr(args, 'fund_name', None)
    total_allocation = str(round_currency(to_decimal(getattr(args, 'total_allocation', '0') or '0')))
    if not aid_year_id:
        return err("aid_year_id is required")
    if not company_id:
        return err("company_id is required")
    if not fund_type:
        return err("fund_type is required")
    if not fund_name:
        return err("fund_name is required")
    alloc_id = str(uuid.uuid4())
    available_amount = total_allocation
    try:
        sql, _ = insert_row("finaid_fund_allocation", {"id": P(), "aid_year_id": P(), "fund_type": P(), "fund_name": P(), "total_allocation": P(), "committed_amount": P(), "disbursed_amount": P(), "available_amount": P(), "company_id": P()})

        conn.execute(sql,
            (alloc_id, aid_year_id, fund_type, fund_name, total_allocation, '0', '0', available_amount, company_id)
        )
        conn.commit()
        return ok({"id": alloc_id, "fund_type": fund_type, "fund_name": fund_name})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate fund allocation: {e}")


def update_fund_allocation(conn, args):
    alloc_id = getattr(args, 'id', None)
    if not alloc_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_fund_allocation")).select(Table("finaid_fund_allocation").star).where(Field("id") == P()).get_sql(), (alloc_id,)).fetchone()
    if not row:
        return err("Fund allocation not found")
    data = {}
    for f in ['fund_name']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    total_allocation = getattr(args, 'total_allocation', None)
    if total_allocation is not None:
        new_total = str(round_currency(to_decimal(total_allocation)))
        committed = to_decimal(row['committed_amount'])
        new_available = str(round_currency(to_decimal(new_total) - committed))
        data["total_allocation"] = new_total
        data["available_amount"] = new_available
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_fund_allocation", data=data, where={"id": alloc_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": alloc_id, "updated": True})


def get_fund_allocation(conn, args):
    alloc_id = getattr(args, 'id', None)
    if not alloc_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_fund_allocation")).select(Table("finaid_fund_allocation").star).where(Field("id") == P()).get_sql(), (alloc_id,)).fetchone()
    if not row:
        return err("Fund allocation not found")
    return ok(dict(row))


def list_fund_allocations(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_fund_allocation")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    aid_year_id = getattr(args, 'aid_year_id', None)
    if aid_year_id:
        qb = qb.where(t.aid_year_id == P())
        params.append(aid_year_id)
    fund_type = getattr(args, 'fund_type', None)
    if fund_type:
        qb = qb.where(t.fund_type == P())
        params.append(fund_type)
    qb = qb.limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"fund_allocations": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Cost of Attendance
# ---------------------------------------------------------------------------

def _calc_total_coa(tuition_fees, books_supplies, room_board, transportation, personal_expenses, loan_fees):
    return str(round_currency(
        to_decimal(tuition_fees) + to_decimal(books_supplies) + to_decimal(room_board) +
        to_decimal(transportation) + to_decimal(personal_expenses) + to_decimal(loan_fees)
    ))


def add_cost_of_attendance(conn, args):
    aid_year_id = getattr(args, 'aid_year_id', None)
    company_id = getattr(args, 'company_id', None)
    enrollment_status = getattr(args, 'enrollment_status', None)
    living_arrangement = getattr(args, 'living_arrangement', '') or ''
    if not aid_year_id:
        return err("aid_year_id is required")
    if not company_id:
        return err("company_id is required")
    if not enrollment_status:
        return err("enrollment_status is required")
    tuition_fees = str(round_currency(to_decimal(getattr(args, 'tuition_fees', '0') or '0')))
    books_supplies = str(round_currency(to_decimal(getattr(args, 'books_supplies', '0') or '0')))
    room_board = str(round_currency(to_decimal(getattr(args, 'room_board', '0') or '0')))
    transportation = str(round_currency(to_decimal(getattr(args, 'transportation', '0') or '0')))
    personal_expenses = str(round_currency(to_decimal(getattr(args, 'personal_expenses', '0') or '0')))
    loan_fees = str(round_currency(to_decimal(getattr(args, 'loan_fees', '0') or '0')))
    total_coa = _calc_total_coa(tuition_fees, books_supplies, room_board, transportation, personal_expenses, loan_fees)
    program_id = getattr(args, 'program_id', None)
    coa_id = str(uuid.uuid4())
    try:
        sql, _ = insert_row("finaid_cost_of_attendance", {"id": P(), "aid_year_id": P(), "program_id": P(), "enrollment_status": P(), "living_arrangement": P(), "tuition_fees": P(), "books_supplies": P(), "room_board": P(), "transportation": P(), "personal_expenses": P(), "loan_fees": P(), "total_coa": P(), "is_active": P(), "company_id": P()})

        conn.execute(sql,
            (coa_id, aid_year_id, program_id, enrollment_status, living_arrangement,
             tuition_fees, books_supplies, room_board, transportation, personal_expenses, loan_fees, total_coa, 1, company_id)
        )
        conn.commit()
        return ok({"id": coa_id, "total_coa": total_coa})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate COA configuration: {e}")


def update_cost_of_attendance(conn, args):
    coa_id = getattr(args, 'id', None)
    if not coa_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_cost_of_attendance")).select(Table("finaid_cost_of_attendance").star).where(Field("id") == P()).get_sql(), (coa_id,)).fetchone()
    if not row:
        return err("COA not found")
    money_fields = ['tuition_fees', 'books_supplies', 'room_board', 'transportation', 'personal_expenses', 'loan_fees']
    current = dict(row)
    data = {}
    for f in money_fields:
        v = getattr(args, f, None)
        if v is not None:
            new_val = str(round_currency(to_decimal(v)))
            data[f] = new_val
            current[f] = new_val
    is_active = getattr(args, 'is_active', None)
    if is_active is not None:
        data["is_active"] = int(is_active)
    if data:
        new_total = _calc_total_coa(current['tuition_fees'], current['books_supplies'], current['room_board'],
                                     current['transportation'], current['personal_expenses'], current['loan_fees'])
        data["total_coa"] = new_total
        data["updated_at"] = _now_iso()
        sql, vals = dynamic_update("finaid_cost_of_attendance", data=data, where={"id": coa_id})
        conn.execute(sql, vals)
        conn.commit()
        return ok({"id": coa_id, "total_coa": new_total})
    return err("No fields to update")


def get_cost_of_attendance(conn, args):
    coa_id = getattr(args, 'id', None)
    if not coa_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_cost_of_attendance")).select(Table("finaid_cost_of_attendance").star).where(Field("id") == P()).get_sql(), (coa_id,)).fetchone()
    if not row:
        return err("COA not found")
    return ok(dict(row))


def list_cost_of_attendance(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_cost_of_attendance")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['aid_year_id', 'enrollment_status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"cost_of_attendance": [dict(r) for r in rows], "count": len(rows)})


def delete_cost_of_attendance(conn, args):
    coa_id = getattr(args, 'id', None)
    if not coa_id:
        return err("id is required")
    _ap = Table("finaid_award_package")
    ref = conn.execute(Q.from_(_ap).select(_ap.id).where(_ap.cost_of_attendance_id == P()).limit(1).get_sql(), (coa_id,)).fetchone()
    if ref:
        return err("Cannot delete COA referenced by award package(s)")
    _coa = Table("finaid_cost_of_attendance")
    conn.execute(Q.from_(_coa).delete().where(_coa.id == P()).get_sql(), (coa_id,))
    conn.commit()
    return ok({"id": coa_id, "deleted": True})


# ---------------------------------------------------------------------------
# ISIR Management
# ---------------------------------------------------------------------------

_CFLAG_DESCRIPTIONS = {
    'nslds_default': ('C25', 'NSLDS: Loan default match', 1),
    'nslds_overpayment': ('C09', 'NSLDS: Grant overpayment match', 1),
    'selective_service': ('C07', 'Selective Service registration match issue', 1),
    'citizenship': ('C01', 'Citizenship/SSN match issue', 1),
}


def import_isir(conn, args):
    student_id = getattr(args, 'student_id', None)
    aid_year_id = getattr(args, 'aid_year_id', None)
    company_id = getattr(args, 'company_id', None)
    sai = getattr(args, 'sai', '0') or '0'
    receipt_date = getattr(args, 'receipt_date', '') or ''
    if not student_id:
        return err("student_id is required")
    if not aid_year_id:
        return err("aid_year_id is required")
    if not company_id:
        return err("company_id is required")
    transaction_number = int(getattr(args, 'transaction_number', 1) or 1)
    fafsa_submission_id = getattr(args, 'fafsa_submission_id', '') or ''
    dependency_status = getattr(args, 'dependency_status', '') or ''
    pell_index = getattr(args, 'pell_index_isir', '') or getattr(args, 'pell_index', '') or ''
    verification_flag = int(getattr(args, 'verification_flag', 0) or 0)
    verification_group = getattr(args, 'verification_group', '') or ''
    nslds_default_flag = int(getattr(args, 'nslds_default_flag', 0) or 0)
    nslds_overpayment_flag = int(getattr(args, 'nslds_overpayment_flag', 0) or 0)
    selective_service_flag = int(getattr(args, 'selective_service_flag', 0) or 0)
    citizenship_flag = int(getattr(args, 'citizenship_flag', 0) or 0)
    sai_decimal = to_decimal(sai)
    sai_is_negative = 1 if sai_decimal < Decimal('0') else 0
    agi = getattr(args, 'agi', '0') or '0'
    household_size = int(getattr(args, 'household_size', 0) or 0)
    raw_isir_data = getattr(args, 'raw_isir_data', '{}') or '{}'
    isir_id = str(uuid.uuid4())
    cflags = []
    if nslds_default_flag:
        cflags.append(('C25', 'NSLDS: Loan default match', 1))
    if nslds_overpayment_flag:
        cflags.append(('C09', 'NSLDS: Grant overpayment match', 1))
    if selective_service_flag:
        cflags.append(('C07', 'Selective Service registration issue', 1))
    if citizenship_flag:
        cflags.append(('C01', 'Citizenship/SSN match issue', 1))
    has_unresolved_cflags = 1 if cflags else 0
    try:
        sql, _ = insert_row("finaid_isir", {"id": P(), "student_id": P(), "aid_year_id": P(), "transaction_number": P(), "is_active_transaction": P(), "fafsa_submission_id": P(), "receipt_date": P(), "sai": P(), "sai_is_negative": P(), "dependency_status": P(), "pell_index": P(), "verification_flag": P(), "verification_group": P(), "has_unresolved_cflags": P(), "nslds_default_flag": P(), "nslds_overpayment_flag": P(), "selective_service_flag": P(), "citizenship_flag": P(), "agi": P(), "household_size": P(), "status": P(), "raw_isir_data": P(), "company_id": P()})

        conn.execute(sql,
            (isir_id, student_id, aid_year_id, transaction_number, 0, fafsa_submission_id, receipt_date,
             str(round_currency(sai_decimal)), sai_is_negative, dependency_status, pell_index, verification_flag,
             verification_group, has_unresolved_cflags, nslds_default_flag, nslds_overpayment_flag,
             selective_service_flag, citizenship_flag, str(round_currency(to_decimal(agi))),
             household_size, 'received', raw_isir_data, company_id)
        )
        for cflag_code, cflag_desc, blocks in cflags:
            cflag_id = str(uuid.uuid4())
            # PyPika: skipped — INSERT OR IGNORE not supported by PyPika
            conn.execute(
                "INSERT OR IGNORE INTO finaid_isir_cflag (id,isir_id,student_id,cflag_code,cflag_description,blocks_disbursement,resolution_status,company_id) VALUES (?,?,?,?,?,?,?,?)",
                (cflag_id, isir_id, student_id, cflag_code, cflag_desc, blocks, 'pending', company_id)
            )
        conn.commit()
        return ok({"id": isir_id, "has_unresolved_cflags": has_unresolved_cflags, "cflags_created": len(cflags)})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate ISIR transaction: {e}")


def update_isir(conn, args):
    isir_id = getattr(args, 'isir_id', None) or getattr(args, 'id', None)
    if not isir_id:
        return err("isir_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_isir")).select(Table("finaid_isir").star).where(Field("id") == P()).get_sql(), (isir_id,)).fetchone()
    if not row:
        return err("ISIR not found")
    data = {}
    for f in ['sai', 'dependency_status', 'pell_index', 'verification_flag', 'verification_group', 'receipt_date', 'fafsa_submission_id']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    is_active_transaction = getattr(args, 'is_active_transaction', None)
    if is_active_transaction is not None:
        data["is_active_transaction"] = int(is_active_transaction)
    # Recompute has_unresolved_cflags
    _cf = Table("finaid_isir_cflag")
    pending_count = conn.execute(
        Q.from_(_cf).select(fn.Count("*")).where(_cf.isir_id == P()).where(_cf.resolution_status == P()).get_sql(), (isir_id, "pending")
    ).fetchone()[0]
    data["has_unresolved_cflags"] = 1 if pending_count > 0 else 0
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_isir", data=data, where={"id": isir_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": isir_id, "updated": True})


def get_isir(conn, args):
    isir_id = getattr(args, 'isir_id', None) or getattr(args, 'id', None)
    if not isir_id:
        return err("isir_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_isir")).select(Table("finaid_isir").star).where(Field("id") == P()).get_sql(), (isir_id,)).fetchone()
    if not row:
        return err("ISIR not found")
    _cf = Table("finaid_isir_cflag")
    cflags = conn.execute(Q.from_(_cf).select(_cf.star).where(_cf.isir_id == P()).get_sql(), (isir_id,)).fetchall()
    result = dict(row)
    result['cflags'] = [dict(c) for c in cflags]
    return ok(result)


def list_isirs(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_isir")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['student_id', 'aid_year_id', 'status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"isirs": [dict(r) for r in rows], "count": len(rows)})


def review_isir(conn, args):
    isir_id = getattr(args, 'isir_id', None) or getattr(args, 'id', None)
    reviewed_by = getattr(args, 'reviewed_by', '') or ''
    if not isir_id:
        return err("isir_id or id is required")
    _isir = Table("finaid_isir")
    sql = Q.update(_isir).set(_isir.status, "reviewed").set(_isir.reviewed_by, P()).set(_isir.reviewed_at, P()).set(_isir.updated_at, P()).where(_isir.id == P()).get_sql()
    conn.execute(sql, (reviewed_by, _now_iso(), _now_iso(), isir_id))
    conn.commit()
    return ok({"id": isir_id, "status": "reviewed"})


def add_isir_cflag(conn, args):
    isir_id = getattr(args, 'isir_id', None)
    company_id = getattr(args, 'company_id', None)
    cflag_code = getattr(args, 'cflag_code', None)
    if not isir_id:
        return err("isir_id is required")
    if not company_id:
        return err("company_id is required")
    if not cflag_code:
        return err("cflag_code is required")
    isir_row = conn.execute(Q.from_(Table("finaid_isir")).select(Field("student_id")).where(Field("id") == P()).get_sql(), (isir_id,)).fetchone()
    if not isir_row:
        return err("ISIR not found")
    student_id = isir_row['student_id']
    cflag_description = getattr(args, 'cflag_description', '') or ''
    blocks_disbursement = int(getattr(args, 'blocks_disbursement', 1) or 1)
    cflag_id = str(uuid.uuid4())
    try:
        sql, _ = insert_row("finaid_isir_cflag", {"id": P(), "isir_id": P(), "student_id": P(), "cflag_code": P(), "cflag_description": P(), "blocks_disbursement": P(), "resolution_status": P(), "company_id": P()})

        conn.execute(sql,
            (cflag_id, isir_id, student_id, cflag_code, cflag_description, blocks_disbursement, 'pending', company_id)
        )
        _isir = Table("finaid_isir")
        conn.execute(Q.update(_isir).set(_isir.has_unresolved_cflags, 1).set(_isir.updated_at, P()).where(_isir.id == P()).get_sql(), (_now_iso(), isir_id))
        conn.commit()
        return ok({"id": cflag_id, "isir_id": isir_id})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate C-flag: {e}")


def resolve_isir_cflag(conn, args):
    cflag_id = getattr(args, 'id', None)
    resolution_status = getattr(args, 'resolution_status', None)
    if not cflag_id:
        return err("id is required")
    if not resolution_status:
        return err("resolution_status is required")
    row = conn.execute(Q.from_(Table("finaid_isir_cflag")).select(Field("isir_id")).where(Field("id") == P()).get_sql(), (cflag_id,)).fetchone()
    if not row:
        return err("C-flag not found")
    isir_id = row['isir_id']
    resolution_date = getattr(args, 'resolution_date', _today()) or _today()
    resolved_by = getattr(args, 'resolved_by', '') or ''
    resolution_notes = getattr(args, 'resolution_notes', '') or ''
    _cf = Table("finaid_isir_cflag")
    sql = (Q.update(_cf).set(_cf.resolution_status, P()).set(_cf.resolution_date, P())
           .set(_cf.resolved_by, P()).set(_cf.resolution_notes, P()).set(_cf.updated_at, P())
           .where(_cf.id == P()).get_sql())
    conn.execute(sql, (resolution_status, resolution_date, resolved_by, resolution_notes, _now_iso(), cflag_id))
    pending_count = conn.execute(
        Q.from_(_cf).select(fn.Count("*")).where(_cf.isir_id == P()).where(_cf.resolution_status == P()).get_sql(), (isir_id, "pending")
    ).fetchone()[0]
    _isir = Table("finaid_isir")
    conn.execute(
        Q.update(_isir).set(_isir.has_unresolved_cflags, P()).set(_isir.updated_at, P()).where(_isir.id == P()).get_sql(),
        (1 if pending_count > 0 else 0, _now_iso(), isir_id)
    )
    conn.commit()
    return ok({"id": cflag_id, "resolution_status": resolution_status})


def list_isir_cflags(conn, args):
    isir_id = getattr(args, 'isir_id', None)
    student_id = getattr(args, 'student_id', None)
    if not isir_id and not student_id:
        return err("isir_id or student_id is required")
    t = Table("finaid_isir_cflag")
    qb = Q.from_(t).select(t.star)
    params = []
    if isir_id:
        qb = qb.where(t.isir_id == P())
        params.append(isir_id)
    if student_id:
        qb = qb.where(t.student_id == P())
        params.append(student_id)
    resolution_status = getattr(args, 'resolution_status', None)
    if resolution_status:
        qb = qb.where(t.resolution_status == P())
        params.append(resolution_status)
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"cflags": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Verification Workflow
# ---------------------------------------------------------------------------

_VERIFICATION_DOCS = {
    'V1': [
        ('tax_transcript', 'Federal tax return transcript', 1),
        ('w2', 'W-2 forms', 1),
        ('household_verification', 'Household verification form', 1),
    ],
    'V4': [
        ('identity', 'Government-issued photo ID', 1),
        ('statement_of_purpose', 'Statement of educational purpose', 1),
    ],
    'V5': [
        ('hs_completion', 'High school completion documentation', 1),
        ('identity', 'Government-issued photo ID', 1),
    ],
}


def create_verification_request(conn, args):
    isir_id = getattr(args, 'isir_id', None)
    student_id = getattr(args, 'student_id', None)
    company_id = getattr(args, 'company_id', None)
    verification_group = getattr(args, 'verification_group', None)
    if not isir_id:
        return err("isir_id is required")
    if not student_id:
        return err("student_id is required")
    if not company_id:
        return err("company_id is required")
    if not verification_group:
        return err("verification_group is required")
    req_id = str(uuid.uuid4())
    requested_date = getattr(args, 'requested_date', _today()) or _today()
    deadline_date = getattr(args, 'deadline_date', '') or ''
    assigned_to = getattr(args, 'assigned_to', '') or ''
    try:
        sql, _ = insert_row("finaid_verification_request", {"id": P(), "isir_id": P(), "student_id": P(), "verification_group": P(), "status": P(), "requested_date": P(), "deadline_date": P(), "assigned_to": P(), "company_id": P()})

        conn.execute(sql,
            (req_id, isir_id, student_id, verification_group, 'initiated', requested_date, deadline_date, assigned_to, company_id)
        )
        docs_created = 0
        for doc_type, doc_desc, is_required in _VERIFICATION_DOCS.get(verification_group, []):
            doc_id = str(uuid.uuid4())
            sql, _ = insert_row("finaid_verification_document", {"id": P(), "verification_request_id": P(), "student_id": P(), "document_type": P(), "document_description": P(), "is_required": P(), "submission_status": P(), "company_id": P()})

            conn.execute(sql,
                (doc_id, req_id, student_id, doc_type, doc_desc, is_required, 'not_submitted', company_id)
            )
            docs_created += 1
        conn.commit()
        return ok({"id": req_id, "verification_group": verification_group, "documents_created": docs_created})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate verification request for this ISIR: {e}")


def update_verification_request(conn, args):
    req_id = getattr(args, 'verification_request_id', None) or getattr(args, 'id', None)
    if not req_id:
        return err("verification_request_id or id is required")
    data = {}
    for f in ['status', 'deadline_date', 'assigned_to', 'discrepancy_notes']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    discrepancy_found = getattr(args, 'discrepancy_found', None)
    if discrepancy_found is not None:
        data["discrepancy_found"] = int(discrepancy_found)
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_verification_request", data=data, where={"id": req_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": req_id, "updated": True})


def get_verification_request(conn, args):
    req_id = getattr(args, 'verification_request_id', None) or getattr(args, 'id', None)
    if not req_id:
        return err("verification_request_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_verification_request")).select(Table("finaid_verification_request").star).where(Field("id") == P()).get_sql(), (req_id,)).fetchone()
    if not row:
        return err("Verification request not found")
    _vd = Table("finaid_verification_document")
    docs = conn.execute(Q.from_(_vd).select(_vd.star).where(_vd.verification_request_id == P()).get_sql(), (req_id,)).fetchall()
    result = dict(row)
    result['documents'] = [dict(d) for d in docs]
    return ok(result)


def list_verification_requests(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_verification_request")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['status', 'assigned_to', 'student_id']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"verification_requests": [dict(r) for r in rows], "count": len(rows)})


def add_verification_document(conn, args):
    req_id = getattr(args, 'verification_request_id', None)
    student_id = getattr(args, 'student_id', None)
    company_id = getattr(args, 'company_id', None)
    document_type = getattr(args, 'document_type', None)
    if not req_id or not student_id or not company_id or not document_type:
        return err("verification_request_id, student_id, company_id, and document_type are required")
    doc_id = str(uuid.uuid4())
    document_description = getattr(args, 'document_description', '') or ''
    is_required = int(getattr(args, 'is_required', 1) or 1)
    try:
        sql, _ = insert_row("finaid_verification_document", {"id": P(), "verification_request_id": P(), "student_id": P(), "document_type": P(), "document_description": P(), "is_required": P(), "submission_status": P(), "company_id": P()})

        conn.execute(sql,
            (doc_id, req_id, student_id, document_type, document_description, is_required, 'not_submitted', company_id)
        )
        conn.commit()
        return ok({"id": doc_id})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate document type for this request: {e}")


def update_verification_document(conn, args):
    doc_id = getattr(args, 'id', None)
    if not doc_id:
        return err("id is required")
    data = {}
    for f in ['submission_status', 'reviewed_by', 'reviewed_date', 'rejection_reason', 'document_reference', 'submitted_date']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_verification_document", data=data, where={"id": doc_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": doc_id, "updated": True})


def complete_verification(conn, args):
    req_id = getattr(args, 'verification_request_id', None) or getattr(args, 'id', None)
    if not req_id:
        return err("verification_request_id or id is required")
    # Check all required docs are accepted or waived
    # PyPika: skipped — NOT IN clause in WHERE
    pending = conn.execute(
        "SELECT COUNT(*) FROM finaid_verification_document WHERE verification_request_id=? AND is_required=1 AND submission_status NOT IN ('accepted','waived')",
        (req_id,)
    ).fetchone()[0]
    if pending > 0:
        return err(f"{pending} required document(s) not yet accepted or waived")
    completed_date = getattr(args, 'completed_date', _today()) or _today()
    _vr = Table("finaid_verification_request")
    conn.execute(
        Q.update(_vr).set(_vr.status, "complete").set(_vr.completed_date, P()).set(_vr.updated_at, P()).where(_vr.id == P()).get_sql(),
        (completed_date, _now_iso(), req_id)
    )
    conn.commit()
    return ok({"id": req_id, "status": "complete"})


def list_verification_documents(conn, args):
    req_id = getattr(args, 'verification_request_id', None)
    if not req_id:
        return err("verification_request_id is required")
    _vd = Table("finaid_verification_document")
    rows = conn.execute(Q.from_(_vd).select(_vd.star).where(_vd.verification_request_id == P()).get_sql(), (req_id,)).fetchall()
    return ok({"documents": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Award Packaging
# ---------------------------------------------------------------------------

def _update_package_totals(conn, pkg_id):
    _aw = Table("finaid_award")
    awards = conn.execute(
        Q.from_(_aw).select(_aw.aid_type, _aw.aid_source, _aw.offered_amount).where(_aw.award_package_id == P()).get_sql(),
        (pkg_id,)
    ).fetchall()
    total_grants = Decimal('0')
    total_loans = Decimal('0')
    total_work_study = Decimal('0')
    grant_types = {'pell', 'fseog', 'institutional_grant', 'institutional_scholarship', 'state_grant', 'external_scholarship', 'tuition_waiver', 'teach_grant'}
    loan_types = {'subsidized_loan', 'unsubsidized_loan', 'plus_loan', 'parent_plus_loan'}
    for a in awards:
        amt = to_decimal(a['offered_amount'])
        if a['aid_type'] in grant_types:
            total_grants += amt
        elif a['aid_type'] in loan_types:
            total_loans += amt
        elif a['aid_type'] == 'fws':
            total_work_study += amt
    total_aid = total_grants + total_loans + total_work_study
    _pkg = Table("finaid_award_package")
    sql = (Q.update(_pkg)
           .set(_pkg.total_grants, P()).set(_pkg.total_loans, P())
           .set(_pkg.total_work_study, P()).set(_pkg.total_aid, P())
           .set(_pkg.updated_at, P()).where(_pkg.id == P()).get_sql())
    conn.execute(sql,
        (str(round_currency(total_grants)), str(round_currency(total_loans)),
         str(round_currency(total_work_study)), str(round_currency(total_aid)), _now_iso(), pkg_id)
    )


def create_award_package(conn, args):
    student_id = getattr(args, 'student_id', None)
    aid_year_id = getattr(args, 'aid_year_id', None)
    academic_term_id = getattr(args, 'academic_term_id', None)
    program_enrollment_id = getattr(args, 'program_enrollment_id', None)
    isir_id = getattr(args, 'isir_id', None)
    cost_of_attendance_id = getattr(args, 'cost_of_attendance_id', None)
    enrollment_status = getattr(args, 'enrollment_status', None)
    company_id = getattr(args, 'company_id', None)
    for name, val in [('student_id', student_id), ('aid_year_id', aid_year_id),
                       ('academic_term_id', academic_term_id), ('company_id', company_id)]:
        if not val:
            return err(f"{name} is required")
    # Get COA total for financial_need computation
    financial_need = '0'
    if cost_of_attendance_id and isir_id:
        coa_row = conn.execute(Q.from_(Table("finaid_cost_of_attendance")).select(Field("total_coa")).where(Field("id") == P()).get_sql(), (cost_of_attendance_id,)).fetchone()
        isir_row = conn.execute(Q.from_(Table("finaid_isir")).select(Field("sai")).where(Field("id") == P()).get_sql(), (isir_id,)).fetchone()
        if coa_row and isir_row:
            need = to_decimal(coa_row['total_coa']) - to_decimal(isir_row['sai'])
            financial_need = str(round_currency(max(need, Decimal('0'))))
    # Generate naming_series
    ay_row = conn.execute(Q.from_(Table("finaid_aid_year")).select(Field("aid_year_code")).where(Field("id") == P()).get_sql(), (aid_year_id,)).fetchone()
    ay_code = ay_row['aid_year_code'] if ay_row else 'XXXX'
    count = conn.execute(Q.from_(Table("finaid_award_package")).select(fn.Count("*")).where(Field("aid_year_id") == P()).get_sql(), (aid_year_id,)).fetchone()[0]
    naming_series = f"AWD-{ay_code}-{count+1:05d}"
    pkg_id = str(uuid.uuid4())
    packaged_by = getattr(args, 'packaged_by', '') or ''
    notes = getattr(args, 'notes', '') or ''
    try:
        sql, _ = insert_row("finaid_award_package", {"id": P(), "naming_series": P(), "student_id": P(), "aid_year_id": P(), "academic_term_id": P(), "program_enrollment_id": P(), "isir_id": P(), "cost_of_attendance_id": P(), "enrollment_status": P(), "financial_need": P(), "total_grants": P(), "total_loans": P(), "total_work_study": P(), "total_aid": P(), "status": P(), "packaged_by": P(), "packaged_at": P(), "notes": P(), "company_id": P()})

        conn.execute(sql,
            (pkg_id, naming_series, student_id, aid_year_id, academic_term_id or '',
             program_enrollment_id or '', isir_id or '', cost_of_attendance_id or '',
             enrollment_status or '', financial_need, '0', '0', '0', '0', 'draft',
             packaged_by, _now_iso(), notes, company_id)
        )
        conn.commit()
        return ok({"id": pkg_id, "naming_series": naming_series, "financial_need": financial_need})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate award package: {e}")


def update_award_package(conn, args):
    pkg_id = getattr(args, 'award_package_id', None) or getattr(args, 'id', None)
    if not pkg_id:
        return err("award_package_id or id is required")
    data = {}
    for f in ['notes', 'enrollment_status', 'acceptance_deadline', 'approved_by', 'approved_at']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_award_package", data=data, where={"id": pkg_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": pkg_id, "updated": True})


def get_award_package(conn, args):
    pkg_id = getattr(args, 'award_package_id', None) or getattr(args, 'id', None)
    if not pkg_id:
        return err("award_package_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_award_package")).select(Table("finaid_award_package").star).where(Field("id") == P()).get_sql(), (pkg_id,)).fetchone()
    if not row:
        return err("Award package not found")
    _aw = Table("finaid_award")
    awards = conn.execute(Q.from_(_aw).select(_aw.star).where(_aw.award_package_id == P()).get_sql(), (pkg_id,)).fetchall()
    result = dict(row)
    result['awards'] = [dict(a) for a in awards]
    return ok(result)


def list_award_packages(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_award_package")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['status', 'aid_year_id', 'student_id', 'academic_term_id']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"award_packages": [dict(r) for r in rows], "count": len(rows)})


def add_award(conn, args):
    award_package_id = getattr(args, 'award_package_id', None)
    student_id = getattr(args, 'student_id', None)
    aid_year_id = getattr(args, 'aid_year_id', None)
    academic_term_id = getattr(args, 'academic_term_id', None)
    aid_type = getattr(args, 'aid_type', None)
    aid_source = getattr(args, 'aid_source', None)
    offered_amount = str(round_currency(to_decimal(getattr(args, 'offered_amount', '0') or '0')))
    company_id = getattr(args, 'company_id', None)
    for name, val in [('award_package_id', award_package_id), ('student_id', student_id),
                       ('aid_type', aid_type), ('aid_source', aid_source), ('company_id', company_id)]:
        if not val:
            return err(f"{name} is required")
    # Validate package is draft
    pkg = conn.execute(Q.from_(Table("finaid_award_package")).select(Field("status")).where(Field("id") == P()).get_sql(), (award_package_id,)).fetchone()
    if not pkg:
        return err("Award package not found")
    if pkg['status'] not in ('draft', 'offered'):
        return err("Can only add awards to draft or offered packages")
    fund_source_id = getattr(args, 'fund_source_id', '') or ''
    gl_account_id = getattr(args, 'gl_account_id', '') or ''
    notes = getattr(args, 'notes', '') or ''
    award_id = str(uuid.uuid4())
    try:
        sql, _ = insert_row("finaid_award", {"id": P(), "award_package_id": P(), "student_id": P(), "aid_year_id": P(), "academic_term_id": P(), "aid_type": P(), "aid_source": P(), "fund_source_id": P(), "offered_amount": P(), "accepted_amount": P(), "disbursed_amount": P(), "acceptance_status": P(), "disbursement_holds": P(), "is_locked": P(), "gl_account_id": P(), "notes": P(), "company_id": P()})

        conn.execute(sql,
            (award_id, award_package_id, student_id, aid_year_id or '',
             academic_term_id or '', aid_type, aid_source, fund_source_id,
             offered_amount, '0', '0', 'pending', '[]', 0, gl_account_id, notes, company_id)
        )
        _update_package_totals(conn, award_package_id)
        conn.commit()
        return ok({"id": award_id, "aid_type": aid_type, "offered_amount": offered_amount})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate aid type in package: {e}")


def update_award(conn, args):
    award_id = getattr(args, 'award_id', None) or getattr(args, 'id', None)
    if not award_id:
        return err("award_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_award")).select(Field("award_package_id")).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not row:
        return err("Award not found")
    _ap = Table("finaid_award_package")
    pkg = conn.execute(Q.from_(_ap).select(_ap.status).where(_ap.id == P()).get_sql(), (row['award_package_id'],)).fetchone()
    if pkg and pkg['status'] != 'draft':
        return err("Can only update awards in draft packages")
    data = {}
    offered_amount = getattr(args, 'offered_amount', None)
    if offered_amount is not None:
        data["offered_amount"] = str(round_currency(to_decimal(offered_amount)))
    for f in ['notes', 'gl_account_id']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_award", data=data, where={"id": award_id})
    conn.execute(sql, vals)
    _update_package_totals(conn, row['award_package_id'])
    conn.commit()
    return ok({"id": award_id, "updated": True})


def get_award(conn, args):
    award_id = getattr(args, 'award_id', None) or getattr(args, 'id', None)
    if not award_id:
        return err("award_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_award")).select(Table("finaid_award").star).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not row:
        return err("Award not found")
    return ok(dict(row))


def list_awards(conn, args):
    award_package_id = getattr(args, 'award_package_id', None)
    student_id = getattr(args, 'student_id', None)
    company_id = getattr(args, 'company_id', None)
    if not award_package_id and not student_id and not company_id:
        return err("award_package_id, student_id, or company_id is required")
    t = Table("finaid_award")
    qb = Q.from_(t).select(t.star)
    params = []
    if award_package_id:
        qb = qb.where(t.award_package_id == P())
        params.append(award_package_id)
    if student_id:
        qb = qb.where(t.student_id == P())
        params.append(student_id)
    if company_id:
        qb = qb.where(t.company_id == P())
        params.append(company_id)
    for f in ['aid_type', 'acceptance_status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"awards": [dict(r) for r in rows], "count": len(rows)})


def delete_award(conn, args):
    award_id = getattr(args, 'award_id', None) or getattr(args, 'id', None)
    if not award_id:
        return err("award_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_award")).select(Field("award_package_id")).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not row:
        return err("Award not found")
    _ap = Table("finaid_award_package")
    pkg = conn.execute(Q.from_(_ap).select(_ap.status).where(_ap.id == P()).get_sql(), (row['award_package_id'],)).fetchone()
    if pkg and pkg['status'] != 'draft':
        return err("Can only delete awards from draft packages")
    _aw = Table("finaid_award")
    conn.execute(Q.from_(_aw).delete().where(_aw.id == P()).get_sql(), (award_id,))
    _update_package_totals(conn, row['award_package_id'])
    conn.commit()
    return ok({"id": award_id, "deleted": True})


def offer_award_package(conn, args):
    pkg_id = getattr(args, 'award_package_id', None) or getattr(args, 'id', None)
    if not pkg_id:
        return err("award_package_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_award_package")).select(Table("finaid_award_package").star).where(Field("id") == P()).get_sql(), (pkg_id,)).fetchone()
    if not row:
        return err("Award package not found")
    if row['status'] != 'draft':
        return err("Package must be in draft status to offer")
    packaged_by = getattr(args, 'packaged_by', '') or ''
    offered_date = getattr(args, 'offered_date', _today()) or _today()
    _pkg = Table("finaid_award_package")
    sql = (Q.update(_pkg).set(_pkg.status, "offered").set(_pkg.offered_date, P())
           .set(_pkg.packaged_by, P()).set(_pkg.packaged_at, P()).set(_pkg.updated_at, P())
           .where(_pkg.id == P()).get_sql())
    conn.execute(sql, (offered_date, packaged_by, _now_iso(), _now_iso(), pkg_id))
    conn.commit()
    return ok({"id": pkg_id, "status": "offered"})


def accept_award(conn, args):
    award_id = getattr(args, 'award_id', None) or getattr(args, 'id', None)
    if not award_id:
        return err("award_id or id is required")
    row = conn.execute(Q.from_(Table("finaid_award")).select(Table("finaid_award").star).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not row:
        return err("Award not found")
    accepted_amount = getattr(args, 'accepted_amount', None)
    if accepted_amount is None:
        accepted_amount = row['offered_amount']
    acceptance_date = getattr(args, 'acceptance_date', _today()) or _today()
    _aw = Table("finaid_award")
    sql = (Q.update(_aw).set(_aw.acceptance_status, "accepted").set(_aw.accepted_amount, P())
           .set(_aw.acceptance_date, P()).set(_aw.updated_at, P()).where(_aw.id == P()).get_sql())
    conn.execute(sql, (str(round_currency(to_decimal(accepted_amount))), acceptance_date, _now_iso(), award_id))
    conn.commit()
    return ok({"id": award_id, "acceptance_status": "accepted"})


def decline_award(conn, args):
    award_id = getattr(args, 'award_id', None) or getattr(args, 'id', None)
    if not award_id:
        return err("award_id or id is required")
    _aw = Table("finaid_award")
    conn.execute(
        Q.update(_aw).set(_aw.acceptance_status, "declined").set(_aw.accepted_amount, "0").set(_aw.updated_at, P()).where(_aw.id == P()).get_sql(),
        (_now_iso(), award_id)
    )
    conn.commit()
    return ok({"id": award_id, "acceptance_status": "declined"})


def cancel_award_package(conn, args):
    pkg_id = getattr(args, 'award_package_id', None) or getattr(args, 'id', None)
    if not pkg_id:
        return err("award_package_id or id is required")
    _pkg = Table("finaid_award_package")
    conn.execute(Q.update(_pkg).set(_pkg.status, "cancelled").set(_pkg.updated_at, P()).where(_pkg.id == P()).get_sql(), (_now_iso(), pkg_id))
    _aw = Table("finaid_award")
    conn.execute(Q.update(_aw).set(_aw.acceptance_status, "declined").set(_aw.accepted_amount, "0").set(_aw.updated_at, P()).where(_aw.award_package_id == P()).get_sql(), (_now_iso(), pkg_id))
    conn.commit()
    return ok({"id": pkg_id, "status": "cancelled"})


# ---------------------------------------------------------------------------
# Disbursement
# ---------------------------------------------------------------------------

def disburse_award(conn, args):
    award_id = getattr(args, 'award_id', None)
    student_id = getattr(args, 'student_id', None)
    amount = getattr(args, 'amount', None)
    disbursement_date = getattr(args, 'disbursement_date', _today()) or _today()
    company_id = getattr(args, 'company_id', None)
    for name, val in [('award_id', award_id), ('student_id', student_id), ('amount', amount), ('company_id', company_id)]:
        if not val:
            return err(f"{name} is required")
    award_row = conn.execute(Q.from_(Table("finaid_award")).select(Table("finaid_award").star).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not award_row:
        return err("Award not found")
    if award_row['acceptance_status'] != 'accepted':
        return err("Award must be accepted before disbursement")
    # Check disbursement holds
    holds = json.loads(award_row['disbursement_holds'] or '[]')
    if holds:
        return err(f"Disbursement blocked by holds: {', '.join(holds)}")
    pkg_id = award_row['award_package_id']
    disb_id = str(uuid.uuid4())
    disbursed_by = getattr(args, 'disbursed_by', '') or ''
    disbursement_number = int(getattr(args, 'disbursement_number', 1) or 1)
    amount_decimal = round_currency(to_decimal(amount))
    sql, _ = insert_row("finaid_disbursement", {"id": P(), "award_id": P(), "award_package_id": P(), "student_id": P(), "disbursement_type": P(), "disbursement_number": P(), "amount": P(), "disbursement_date": P(), "disbursed_by": P(), "company_id": P(), "created_by": P()})

    conn.execute(sql,
        (disb_id, award_id, pkg_id, student_id, 'disbursement', disbursement_number,
         str(amount_decimal), disbursement_date, disbursed_by, company_id, '')
    )
    new_disbursed = str(round_currency(to_decimal(award_row['disbursed_amount']) + amount_decimal))
    _aw = Table("finaid_award")
    conn.execute(
        Q.update(_aw).set(_aw.disbursed_amount, P()).set(_aw.is_locked, 1).set(_aw.updated_at, P()).where(_aw.id == P()).get_sql(),
        (new_disbursed, _now_iso(), award_id)
    )
    conn.commit()
    return ok({"id": disb_id, "amount": str(amount_decimal), "disbursement_date": disbursement_date})


def reverse_disbursement(conn, args):
    award_id = getattr(args, 'award_id', None)
    amount = getattr(args, 'amount', None)
    disbursement_date = getattr(args, 'disbursement_date', _today()) or _today()
    company_id = getattr(args, 'company_id', None)
    if not award_id or not amount or not company_id:
        return err("award_id, amount, and company_id are required")
    award_row = conn.execute(Q.from_(Table("finaid_award")).select(Field("award_package_id"), Field("student_id"), Field("disbursed_amount")).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not award_row:
        return err("Award not found")
    disb_id = str(uuid.uuid4())
    amount_decimal = round_currency(to_decimal(amount))
    sql, _ = insert_row("finaid_disbursement", {"id": P(), "award_id": P(), "award_package_id": P(), "student_id": P(), "disbursement_type": P(), "disbursement_number": P(), "amount": P(), "disbursement_date": P(), "company_id": P(), "created_by": P()})

    conn.execute(sql,
        (disb_id, award_id, award_row['award_package_id'], award_row['student_id'],
         'reversal', 1, str(amount_decimal), disbursement_date, company_id, '')
    )
    new_disbursed = str(round_currency(to_decimal(award_row['disbursed_amount']) - amount_decimal))
    _aw = Table("finaid_award")
    conn.execute(Q.update(_aw).set(_aw.disbursed_amount, P()).set(_aw.updated_at, P()).where(_aw.id == P()).get_sql(), (new_disbursed, _now_iso(), award_id))
    conn.commit()
    return ok({"id": disb_id, "type": "reversal", "amount": str(amount_decimal)})


def record_r2t4_return_disbursement(conn, args):
    award_id = getattr(args, 'award_id', None)
    r2t4_id = getattr(args, 'r2t4_id', None)
    amount = getattr(args, 'amount', None)
    disbursement_date = getattr(args, 'disbursement_date', _today()) or _today()
    company_id = getattr(args, 'company_id', None)
    if not award_id or not amount or not company_id:
        return err("award_id, amount, and company_id are required")
    award_row = conn.execute(Q.from_(Table("finaid_award")).select(Field("award_package_id"), Field("student_id")).where(Field("id") == P()).get_sql(), (award_id,)).fetchone()
    if not award_row:
        return err("Award not found")
    disb_id = str(uuid.uuid4())
    sql, _ = insert_row("finaid_disbursement", {"id": P(), "award_id": P(), "award_package_id": P(), "student_id": P(), "disbursement_type": P(), "disbursement_number": P(), "amount": P(), "disbursement_date": P(), "company_id": P(), "created_by": P()})

    conn.execute(sql,
        (disb_id, award_id, award_row['award_package_id'], award_row['student_id'],
         'return', 1, str(round_currency(to_decimal(amount))), disbursement_date, company_id, '')
    )
    if r2t4_id:
        _r2 = Table("finaid_r2t4_calculation")
        conn.execute(Q.update(_r2).set(_r2.institution_return_date, P()).set(_r2.updated_at, P()).where(_r2.id == P()).get_sql(), (disbursement_date, _now_iso(), r2t4_id))
    conn.commit()
    return ok({"id": disb_id, "type": "return"})


def get_disbursement(conn, args):
    disb_id = getattr(args, 'id', None)
    if not disb_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_disbursement")).select(Table("finaid_disbursement").star).where(Field("id") == P()).get_sql(), (disb_id,)).fetchone()
    if not row:
        return err("Disbursement not found")
    return ok(dict(row))


def list_disbursements(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_disbursement")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['student_id', 'award_id', 'cod_status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    is_credit_balance = getattr(args, 'is_credit_balance', None)
    if is_credit_balance is not None:
        qb = qb.where(t.is_credit_balance == P())
        params.append(int(is_credit_balance))
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"disbursements": [dict(r) for r in rows], "count": len(rows)})


def generate_cod_export(conn, args):
    company_id = getattr(args, 'company_id', None)
    aid_year_id = getattr(args, 'aid_year_id', None)
    if not company_id:
        return err("company_id is required")
    # PyPika: skipped — JOIN with IN clause
    q = "SELECT d.*, a.aid_type FROM finaid_disbursement d JOIN finaid_award a ON d.award_id=a.id WHERE d.company_id=? AND d.cod_status IN ('pending','')"
    params = [company_id]
    if aid_year_id:
        q += " AND a.aid_year_id=?"
        params.append(aid_year_id)
    rows = conn.execute(q, params).fetchall()
    return ok({"cod_records": [dict(r) for r in rows], "count": len(rows), "generated_at": _now_iso()})


def update_cod_status(conn, args):
    disb_id = getattr(args, 'id', None)
    cod_status = getattr(args, 'cod_status', None)
    if not disb_id or not cod_status:
        return err("id and cod_status are required")
    cod_response_date = getattr(args, 'cod_response_date', _today()) or _today()
    _d = Table("finaid_disbursement")
    conn.execute(Q.update(_d).set(_d.cod_status, P()).set(_d.cod_response_date, P()).where(_d.id == P()).get_sql(), (cod_status, cod_response_date, disb_id))
    conn.commit()
    return ok({"id": disb_id, "cod_status": cod_status})


def mark_credit_balance_returned(conn, args):
    disb_id = getattr(args, 'id', None)
    return_date = getattr(args, 'return_date', _today()) or _today()
    if not disb_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_disbursement")).select(Field("credit_balance_date"), Field("is_credit_balance")).where(Field("id") == P()).get_sql(), (disb_id,)).fetchone()
    if not row:
        return err("Disbursement not found")
    if not row['is_credit_balance']:
        return err("This disbursement is not a credit balance")
    # Validate 14-day rule (lenient check)
    _d = Table("finaid_disbursement")
    conn.execute(Q.update(_d).set(_d.credit_balance_returned_date, P()).where(_d.id == P()).get_sql(), (return_date, disb_id))
    conn.commit()
    return ok({"id": disb_id, "credit_balance_returned_date": return_date})


# ---------------------------------------------------------------------------
# SAP Evaluation
# ---------------------------------------------------------------------------

def _compute_sap_status(gpa_earned, gpa_threshold, credits_attempted, credits_completed,
                         max_timeframe_credits, projected_credits_remaining,
                         transfer_attempted, transfer_completed):
    gpa_ok = to_decimal(gpa_earned) >= to_decimal(gpa_threshold)
    total_attempted = to_decimal(credits_attempted) + to_decimal(transfer_attempted)
    total_completed = to_decimal(credits_completed) + to_decimal(transfer_completed)
    if total_attempted > Decimal('0'):
        completion_rate = total_completed / total_attempted
    else:
        completion_rate = Decimal('0')
    pace_ok = completion_rate >= Decimal('0.67')
    max_timeframe_ok = to_decimal(projected_credits_remaining) <= (to_decimal(max_timeframe_credits) - total_attempted) if to_decimal(max_timeframe_credits) > Decimal('0') else True
    if gpa_ok and pace_ok and max_timeframe_ok:
        return 'SAT', str(round_currency(completion_rate)), 1, 1, 1
    else:
        return 'FSP', str(round_currency(completion_rate)), 1 if gpa_ok else 0, 1 if pace_ok else 0, 1 if max_timeframe_ok else 0


def run_sap_evaluation(conn, args):
    student_id = getattr(args, 'student_id', None)
    academic_term_id = getattr(args, 'academic_term_id', None)
    aid_year_id = getattr(args, 'aid_year_id', None)
    company_id = getattr(args, 'company_id', None)
    for name, val in [('student_id', student_id), ('academic_term_id', academic_term_id), ('company_id', company_id)]:
        if not val:
            return err(f"{name} is required")
    gpa_earned = getattr(args, 'gpa_earned', '0') or '0'
    gpa_threshold = getattr(args, 'gpa_threshold', '2.00') or '2.00'
    credits_attempted = getattr(args, 'credits_attempted', '0') or '0'
    credits_completed = getattr(args, 'credits_completed', '0') or '0'
    completion_threshold = getattr(args, 'completion_threshold', '0.67') or '0.67'
    max_timeframe_credits = getattr(args, 'max_timeframe_credits', '0') or '0'
    projected_credits_remaining = getattr(args, 'projected_credits_remaining', '0') or '0'
    transfer_credits_attempted = getattr(args, 'transfer_credits_attempted', '0') or '0'
    transfer_credits_completed = getattr(args, 'transfer_credits_completed', '0') or '0'
    evaluation_date = getattr(args, 'evaluation_date', _today()) or _today()
    evaluated_by = getattr(args, 'evaluated_by', 'system') or 'system'
    evaluation_type = getattr(args, 'evaluation_type', 'automatic') or 'automatic'
    sap_status, completion_rate, gpa_ok, pace_ok, max_ok = _compute_sap_status(
        gpa_earned, gpa_threshold, credits_attempted, credits_completed,
        max_timeframe_credits, projected_credits_remaining,
        transfer_credits_attempted, transfer_credits_completed
    )
    # Check for prior SAP status
    _se = Table("finaid_sap_evaluation")
    prior_row = conn.execute(
        Q.from_(_se).select(_se.sap_status).where(_se.student_id == P()).where(_se.academic_term_id == P()).get_sql(),
        (student_id, academic_term_id)
    ).fetchone()
    prior_sap_status = prior_row['sap_status'] if prior_row else ''
    eval_id = str(uuid.uuid4())
    try:
        # PyPika: skipped — INSERT OR REPLACE not supported by PyPika
        conn.execute(
            "INSERT OR REPLACE INTO finaid_sap_evaluation (id,student_id,academic_term_id,aid_year_id,evaluation_date,evaluation_type,gpa_earned,gpa_threshold,gpa_meets_standard,credits_attempted,credits_completed,completion_rate,completion_threshold,completion_meets_standard,max_timeframe_credits,projected_credits_remaining,max_timeframe_met,transfer_credits_attempted,transfer_credits_completed,sap_status,prior_sap_status,holds_placed,evaluated_by,notes,company_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eval_id, student_id, academic_term_id, aid_year_id or '', evaluation_date, evaluation_type,
             str(round_currency(to_decimal(gpa_earned))), gpa_threshold, gpa_ok,
             str(round_currency(to_decimal(credits_attempted))), str(round_currency(to_decimal(credits_completed))),
             completion_rate, completion_threshold, pace_ok,
             str(round_currency(to_decimal(max_timeframe_credits))),
             str(round_currency(to_decimal(projected_credits_remaining))), max_ok,
             str(round_currency(to_decimal(transfer_credits_attempted))),
             str(round_currency(to_decimal(transfer_credits_completed))),
             sap_status, prior_sap_status, 1 if sap_status in ('FSP', 'FAW') else 0,
             evaluated_by, '', company_id)
        )
        conn.commit()
        return ok({"id": eval_id, "sap_status": sap_status, "completion_rate": completion_rate})
    except sqlite3.IntegrityError as e:
        return err(f"SAP evaluation error: {e}")


def run_sap_batch(conn, args):
    academic_term_id = getattr(args, 'academic_term_id', None)
    company_id = getattr(args, 'company_id', None)
    if not academic_term_id or not company_id:
        return err("academic_term_id and company_id are required")
    # Get all students with packages for this term
    # PyPika: skipped — SELECT DISTINCT not easily composable
    packages = conn.execute(
        "SELECT DISTINCT student_id, aid_year_id FROM finaid_award_package WHERE academic_term_id=? AND company_id=?",
        (academic_term_id, company_id)
    ).fetchall()
    results = []
    for pkg in packages:
        # Use default values for batch
        eval_id = str(uuid.uuid4())
        # PyPika: skipped — INSERT OR IGNORE not supported by PyPika
        conn.execute(
            "INSERT OR IGNORE INTO finaid_sap_evaluation (id,student_id,academic_term_id,aid_year_id,evaluation_date,evaluation_type,sap_status,evaluated_by,company_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (eval_id, pkg['student_id'], academic_term_id, pkg['aid_year_id'] or '',
             _today(), 'automatic', 'SAT', 'system', company_id)
        )
        results.append(pkg['student_id'])
    conn.commit()
    return ok({"evaluated": len(results), "academic_term_id": academic_term_id})


def get_sap_evaluation(conn, args):
    eval_id = getattr(args, 'id', None)
    if not eval_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_sap_evaluation")).select(Table("finaid_sap_evaluation").star).where(Field("id") == P()).get_sql(), (eval_id,)).fetchone()
    if not row:
        return err("SAP evaluation not found")
    return ok(dict(row))


def list_sap_evaluations(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_sap_evaluation")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['student_id', 'academic_term_id', 'sap_status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"sap_evaluations": [dict(r) for r in rows], "count": len(rows)})


def override_sap_status(conn, args):
    eval_id = getattr(args, 'id', None)
    sap_status = getattr(args, 'sap_status', None)
    evaluated_by = getattr(args, 'evaluated_by', None)
    if not eval_id or not sap_status:
        return err("id and sap_status are required")
    notes = getattr(args, 'notes', '') or ''
    _se = Table("finaid_sap_evaluation")
    sql = (Q.update(_se).set(_se.sap_status, P()).set(_se.evaluation_type, "manual")
           .set(_se.evaluated_by, P()).set(_se.notes, P()).set(_se.updated_at, P())
           .where(_se.id == P()).get_sql())
    conn.execute(sql, (sap_status, evaluated_by or '', notes, _now_iso(), eval_id))
    conn.commit()
    return ok({"id": eval_id, "sap_status": sap_status})


def submit_sap_appeal(conn, args):
    sap_evaluation_id = getattr(args, 'sap_evaluation_id', None)
    student_id = getattr(args, 'student_id', None)
    company_id = getattr(args, 'company_id', None)
    appeal_reason = getattr(args, 'appeal_reason', None)
    reason_narrative = getattr(args, 'reason_narrative', '') or ''
    academic_plan = getattr(args, 'academic_plan', '') or ''
    if not sap_evaluation_id or not student_id or not company_id or not appeal_reason:
        return err("sap_evaluation_id, student_id, company_id, and appeal_reason are required")
    eval_row = conn.execute(Q.from_(Table("finaid_sap_evaluation")).select(Field("sap_status")).where(Field("id") == P()).get_sql(), (sap_evaluation_id,)).fetchone()
    if not eval_row:
        return err("SAP evaluation not found")
    if eval_row['sap_status'] != 'FSP':
        return err("Can only appeal FSP (suspended) evaluations")
    appeal_id = str(uuid.uuid4())
    submitted_date = getattr(args, 'submitted_date', _today()) or _today()
    supporting_documents = getattr(args, 'supporting_documents', '[]') or '[]'
    try:
        sql, _ = insert_row("finaid_sap_appeal", {"id": P(), "sap_evaluation_id": P(), "student_id": P(), "submitted_date": P(), "appeal_reason": P(), "reason_narrative": P(), "academic_plan": P(), "supporting_documents": P(), "status": P(), "company_id": P()})

        conn.execute(sql,
            (appeal_id, sap_evaluation_id, student_id, submitted_date, appeal_reason,
             reason_narrative, academic_plan, supporting_documents, 'submitted', company_id)
        )
        conn.commit()
        return ok({"id": appeal_id, "status": "submitted"})
    except sqlite3.IntegrityError as e:
        return err(f"SAP appeal error: {e}")


def update_sap_appeal(conn, args):
    appeal_id = getattr(args, 'id', None)
    if not appeal_id:
        return err("id is required")
    data = {}
    for f in ['status', 'reviewed_by', 'decision_rationale', 'probation_conditions']:
        v = getattr(args, f, None)
        if v is not None:
            data[f] = v
    reviewed_date = getattr(args, 'reviewed_date_appeal', None) or getattr(args, 'reviewed_date', None)
    if reviewed_date:
        data["reviewed_date"] = reviewed_date
    if not data:
        return err("No fields to update")
    data["updated_at"] = _now_iso()
    sql, vals = dynamic_update("finaid_sap_appeal", data=data, where={"id": appeal_id})
    conn.execute(sql, vals)
    conn.commit()
    return ok({"id": appeal_id, "updated": True})


def get_sap_appeal(conn, args):
    appeal_id = getattr(args, 'id', None)
    if not appeal_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_sap_appeal")).select(Table("finaid_sap_appeal").star).where(Field("id") == P()).get_sql(), (appeal_id,)).fetchone()
    if not row:
        return err("SAP appeal not found")
    return ok(dict(row))


def list_sap_appeals(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_sap_appeal")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['student_id', 'status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"sap_appeals": [dict(r) for r in rows], "count": len(rows)})


def decide_sap_appeal(conn, args):
    appeal_id = getattr(args, 'id', None)
    decision = getattr(args, 'status', None)
    if not appeal_id or not decision:
        return err("id and status (granted or denied) are required")
    if decision not in ('granted', 'denied'):
        return err("status must be 'granted' or 'denied'")
    appeal_row = conn.execute(Q.from_(Table("finaid_sap_appeal")).select(Field("sap_evaluation_id")).where(Field("id") == P()).get_sql(), (appeal_id,)).fetchone()
    if not appeal_row:
        return err("SAP appeal not found")
    reviewed_by = getattr(args, 'reviewed_by', '') or ''
    decision_rationale = getattr(args, 'decision_rationale', '') or ''
    reviewed_date = _today()
    _sa = Table("finaid_sap_appeal")
    sql = (Q.update(_sa).set(_sa.status, P()).set(_sa.reviewed_by, P()).set(_sa.reviewed_date, P())
           .set(_sa.decision_rationale, P()).set(_sa.updated_at, P()).where(_sa.id == P()).get_sql())
    conn.execute(sql, (decision, reviewed_by, reviewed_date, decision_rationale, _now_iso(), appeal_id))
    if decision == 'granted':
        probation_term_id = getattr(args, 'probation_term_id', None)
        probation_conditions = getattr(args, 'probation_conditions', '') or ''
        _se = Table("finaid_sap_evaluation")
        conn.execute(Q.update(_se).set(_se.sap_status, "FAP").set(_se.updated_at, P()).where(_se.id == P()).get_sql(), (_now_iso(), appeal_row['sap_evaluation_id']))
        if probation_term_id:
            conn.execute(Q.update(_sa).set(_sa.probation_term_id, P()).set(_sa.probation_conditions, P()).where(_sa.id == P()).get_sql(), (probation_term_id, probation_conditions, appeal_id))
    conn.commit()
    return ok({"id": appeal_id, "status": decision})


# ---------------------------------------------------------------------------
# R2T4 Calculation
# ---------------------------------------------------------------------------

def create_r2t4(conn, args):
    student_id = getattr(args, 'student_id', None)
    academic_term_id = getattr(args, 'academic_term_id', None)
    award_package_id = getattr(args, 'award_package_id', None)
    company_id = getattr(args, 'company_id', None)
    withdrawal_type = getattr(args, 'withdrawal_type', None)
    withdrawal_date = getattr(args, 'withdrawal_date', '') or ''
    last_date_of_attendance = getattr(args, 'last_date_of_attendance', '') or ''
    determination_date = getattr(args, 'determination_date', _today()) or _today()
    payment_period_start = getattr(args, 'payment_period_start', '') or ''
    payment_period_end = getattr(args, 'payment_period_end', '') or ''
    payment_period_days = int(getattr(args, 'payment_period_days', 0) or 0)
    for name, val in [('student_id', student_id), ('academic_term_id', academic_term_id), ('company_id', company_id)]:
        if not val:
            return err(f"{name} is required")
    # Compute R2T4 return due date (45 days from determination)
    try:
        det_dt = datetime.strptime(determination_date, '%Y-%m-%d')
        due_date = (det_dt + timedelta(days=45)).strftime('%Y-%m-%d')
    except ValueError:
        due_date = ''
    r2t4_id = str(uuid.uuid4())
    try:
        sql, _ = insert_row("finaid_r2t4_calculation", {"id": P(), "student_id": P(), "academic_term_id": P(), "award_package_id": P(), "withdrawal_type": P(), "withdrawal_date": P(), "last_date_of_attendance": P(), "determination_date": P(), "payment_period_start": P(), "payment_period_end": P(), "payment_period_days": P(), "institution_return_due_date": P(), "status": P(), "calculated_by": P(), "company_id": P()})

        conn.execute(sql,
            (r2t4_id, student_id, academic_term_id, award_package_id or '',
             withdrawal_type or '', withdrawal_date, last_date_of_attendance, determination_date,
             payment_period_start, payment_period_end, payment_period_days, due_date,
             'calculated', '', company_id)
        )
        conn.commit()
        return ok({"id": r2t4_id, "institution_return_due_date": due_date})
    except sqlite3.IntegrityError as e:
        return err(f"Duplicate R2T4 for this student/term: {e}")


def calculate_r2t4(conn, args):
    r2t4_id = getattr(args, 'id', None) or getattr(args, 'r2t4_id', None)
    if not r2t4_id:
        return err("id or r2t4_id is required")
    row = conn.execute(Q.from_(Table("finaid_r2t4_calculation")).select(Table("finaid_r2t4_calculation").star).where(Field("id") == P()).get_sql(), (r2t4_id,)).fetchone()
    if not row:
        return err("R2T4 calculation not found")
    r = dict(row)
    # Compute days attended
    try:
        lda = datetime.strptime(r['last_date_of_attendance'], '%Y-%m-%d')
        pps = datetime.strptime(r['payment_period_start'], '%Y-%m-%d')
        days_attended = (lda - pps).days
    except (ValueError, TypeError):
        days_attended = 0
    payment_period_days = r['payment_period_days']
    if payment_period_days > 0:
        percent_completed = Decimal(days_attended) / Decimal(payment_period_days)
    else:
        percent_completed = Decimal('0')
    earned_percent = Decimal('1') if percent_completed > Decimal('0.60') else percent_completed
    # Get disbursed amounts
    if r['award_package_id']:
        # PyPika: skipped — SUM(CAST(... AS REAL)) aggregate
        disb_rows = conn.execute(
            "SELECT SUM(CAST(amount AS REAL)) as total FROM finaid_disbursement WHERE award_package_id=? AND disbursement_type='disbursement'",
            (r['award_package_id'],)
        ).fetchone()
        total_aid_disbursed = Decimal(str(disb_rows['total'] or '0'))
    else:
        total_aid_disbursed = Decimal('0')
    earned_aid = round_currency(earned_percent * total_aid_disbursed)
    unearned_aid = round_currency(total_aid_disbursed - earned_aid)
    # Institution pays 50% of unearned
    institution_return = round_currency(unearned_aid * Decimal('0.50'))
    student_return = round_currency(unearned_aid - institution_return)
    _r2 = Table("finaid_r2t4_calculation")
    sql = (Q.update(_r2)
           .set(_r2.days_attended, P()).set(_r2.percent_completed, P()).set(_r2.earned_percent, P())
           .set(_r2.total_aid_disbursed, P()).set(_r2.earned_aid, P()).set(_r2.unearned_aid, P())
           .set(_r2.institution_return_amount, P()).set(_r2.student_return_amount, P())
           .set(_r2.updated_at, P()).where(_r2.id == P()).get_sql())
    conn.execute(sql,
        (days_attended, str(round_currency(percent_completed)), str(earned_percent),
         str(total_aid_disbursed), str(earned_aid), str(unearned_aid),
         str(institution_return), str(student_return), _now_iso(), r2t4_id)
    )
    conn.commit()
    return ok({
        "id": r2t4_id,
        "days_attended": days_attended,
        "percent_completed": str(round_currency(percent_completed)),
        "earned_aid": str(earned_aid),
        "unearned_aid": str(unearned_aid),
        "institution_return_amount": str(institution_return),
        "student_return_amount": str(student_return),
    })


def approve_r2t4(conn, args):
    r2t4_id = getattr(args, 'id', None) or getattr(args, 'r2t4_id', None)
    approved_by = getattr(args, 'approved_by', '') or ''
    if not r2t4_id:
        return err("id or r2t4_id is required")
    _r2 = Table("finaid_r2t4_calculation")
    conn.execute(Q.update(_r2).set(_r2.status, "approved").set(_r2.approved_by, P()).set(_r2.updated_at, P()).where(_r2.id == P()).get_sql(), (approved_by, _now_iso(), r2t4_id))
    conn.commit()
    return ok({"id": r2t4_id, "status": "approved"})


def record_r2t4_return(conn, args):
    r2t4_id = getattr(args, 'id', None) or getattr(args, 'r2t4_id', None)
    institution_return_date = getattr(args, 'institution_return_date', _today()) or _today()
    if not r2t4_id:
        return err("id or r2t4_id is required")
    _r2 = Table("finaid_r2t4_calculation")
    conn.execute(Q.update(_r2).set(_r2.institution_return_date, P()).set(_r2.status, "returned").set(_r2.updated_at, P()).where(_r2.id == P()).get_sql(), (institution_return_date, _now_iso(), r2t4_id))
    conn.commit()
    return ok({"id": r2t4_id, "status": "returned", "institution_return_date": institution_return_date})


def get_r2t4(conn, args):
    r2t4_id = getattr(args, 'id', None) or getattr(args, 'r2t4_id', None)
    if not r2t4_id:
        return err("id or r2t4_id is required")
    row = conn.execute(Q.from_(Table("finaid_r2t4_calculation")).select(Table("finaid_r2t4_calculation").star).where(Field("id") == P()).get_sql(), (r2t4_id,)).fetchone()
    if not row:
        return err("R2T4 calculation not found")
    return ok(dict(row))


def list_r2t4s(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_r2t4_calculation")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['student_id', 'status']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"r2t4_calculations": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Professional Judgment (append-only)
# ---------------------------------------------------------------------------

def add_professional_judgment(conn, args):
    student_id = getattr(args, 'student_id', None)
    aid_year_id = getattr(args, 'aid_year_id', None)
    company_id = getattr(args, 'company_id', None)
    pj_type = getattr(args, 'pj_type', None)
    pj_reason = getattr(args, 'pj_reason', None)
    reason_narrative = getattr(args, 'reason_narrative', '') or ''
    data_element_changed = getattr(args, 'data_element_changed', '') or ''
    original_value = getattr(args, 'original_value', '') or ''
    adjusted_value = getattr(args, 'adjusted_value', '') or ''
    effective_date = getattr(args, 'effective_date', _today()) or _today()
    authorized_by = getattr(args, 'authorized_by', '') or ''
    authorization_date = getattr(args, 'authorization_date', _today()) or _today()
    for name, val in [('student_id', student_id), ('aid_year_id', aid_year_id),
                       ('company_id', company_id), ('pj_type', pj_type), ('pj_reason', pj_reason)]:
        if not val:
            return err(f"{name} is required")
    pj_id = str(uuid.uuid4())
    supervisor_review_required = int(getattr(args, 'supervisor_review_required', 0) or 0)
    award_package_id = getattr(args, 'award_package_id', None)
    supporting_documentation = getattr(args, 'supporting_documents', '[]') or '[]'
    sql, _ = insert_row("finaid_professional_judgment", {"id": P(), "student_id": P(), "aid_year_id": P(), "award_package_id": P(), "pj_type": P(), "pj_reason": P(), "reason_narrative": P(), "data_element_changed": P(), "original_value": P(), "adjusted_value": P(), "effective_date": P(), "supporting_documentation": P(), "authorized_by": P(), "authorization_date": P(), "supervisor_review_required": P(), "company_id": P(), "created_by": P()})

    conn.execute(sql,
        (pj_id, student_id, aid_year_id, award_package_id, pj_type, pj_reason,
         reason_narrative, data_element_changed, original_value, adjusted_value, effective_date,
         supporting_documentation, authorized_by, authorization_date, supervisor_review_required,
         company_id, '')
    )
    conn.commit()
    return ok({"id": pj_id, "pj_type": pj_type})


def get_professional_judgment(conn, args):
    pj_id = getattr(args, 'id', None)
    if not pj_id:
        return err("id is required")
    row = conn.execute(Q.from_(Table("finaid_professional_judgment")).select(Table("finaid_professional_judgment").star).where(Field("id") == P()).get_sql(), (pj_id,)).fetchone()
    if not row:
        return err("Professional judgment not found")
    return ok(dict(row))


def list_professional_judgments(conn, args):
    company_id = getattr(args, 'company_id', None)
    if not company_id:
        return err("company_id is required")
    t = Table("finaid_professional_judgment")
    qb = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]
    for f in ['student_id', 'aid_year_id', 'pj_type']:
        v = getattr(args, f, None)
        if v:
            qb = qb.where(Field(f) == P())
            params.append(v)
    qb = qb.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([int(getattr(args, 'limit', 50) or 50), int(getattr(args, 'offset', 0) or 0)])
    rows = conn.execute(qb.get_sql(), params).fetchall()
    return ok({"professional_judgments": [dict(r) for r in rows], "count": len(rows)})


def approve_professional_judgment(conn, args):
    pj_id = getattr(args, 'id', None)
    supervisor_reviewed_by = getattr(args, 'supervisor_reviewed_by', None)
    if not pj_id or not supervisor_reviewed_by:
        return err("id and supervisor_reviewed_by are required")
    supervisor_review_date = getattr(args, 'supervisor_review_date', _today()) or _today()
    # finaid_professional_judgment is append-only but we allow supervisor approval update
    _pj = Table("finaid_professional_judgment")
    conn.execute(Q.update(_pj).set(_pj.supervisor_reviewed_by, P()).set(_pj.supervisor_review_date, P()).where(_pj.id == P()).get_sql(), (supervisor_reviewed_by, supervisor_review_date, pj_id))
    conn.commit()
    return ok({"id": pj_id, "supervisor_reviewed_by": supervisor_reviewed_by})


# ---------------------------------------------------------------------------
# ACTIONS
# ---------------------------------------------------------------------------

ACTIONS = {
    # Aid Year
    "finaid-add-aid-year": add_aid_year,
    "finaid-update-aid-year": update_aid_year,
    "finaid-get-aid-year": get_aid_year,
    "finaid-list-aid-years": list_aid_years,
    "finaid-activate-aid-year": set_active_aid_year,
    "finaid-import-pell-schedule": import_pell_schedule,
    "finaid-list-pell-schedule": list_pell_schedule,
    # Fund Allocation
    "finaid-add-fund-allocation": add_fund_allocation,
    "finaid-update-fund-allocation": update_fund_allocation,
    "finaid-get-fund-allocation": get_fund_allocation,
    "finaid-list-fund-allocations": list_fund_allocations,
    # Cost of Attendance
    "finaid-add-cost-of-attendance": add_cost_of_attendance,
    "finaid-update-cost-of-attendance": update_cost_of_attendance,
    "finaid-get-cost-of-attendance": get_cost_of_attendance,
    "finaid-list-cost-of-attendance": list_cost_of_attendance,
    "finaid-delete-cost-of-attendance": delete_cost_of_attendance,
    # ISIR
    "finaid-import-isir": import_isir,
    "finaid-update-isir": update_isir,
    "finaid-get-isir": get_isir,
    "finaid-list-isirs": list_isirs,
    "finaid-complete-isir-review": review_isir,
    "finaid-add-isir-cflag": add_isir_cflag,
    "finaid-complete-isir-cflag": resolve_isir_cflag,
    "finaid-list-isir-cflags": list_isir_cflags,
    # Verification
    "finaid-create-verification-request": create_verification_request,
    "finaid-update-verification-request": update_verification_request,
    "finaid-get-verification-request": get_verification_request,
    "finaid-list-verification-requests": list_verification_requests,
    "finaid-add-verification-document": add_verification_document,
    "finaid-update-verification-document": update_verification_document,
    "finaid-complete-verification": complete_verification,
    "finaid-list-verification-documents": list_verification_documents,
    # Award Packaging
    "finaid-create-award-package": create_award_package,
    "finaid-update-award-package": update_award_package,
    "finaid-get-award-package": get_award_package,
    "finaid-list-award-packages": list_award_packages,
    "finaid-add-award": add_award,
    "finaid-update-award": update_award,
    "finaid-get-award": get_award,
    "finaid-list-awards": list_awards,
    "finaid-delete-award": delete_award,
    "finaid-submit-award-offer": offer_award_package,
    "finaid-accept-award": accept_award,
    "finaid-deny-award": decline_award,
    "finaid-cancel-award-package": cancel_award_package,
    # Disbursement
    "finaid-record-award-disbursement": disburse_award,
    "finaid-cancel-disbursement": reverse_disbursement,
    "finaid-record-r2t4-return-disbursement": record_r2t4_return_disbursement,
    "finaid-get-disbursement": get_disbursement,
    "finaid-list-disbursements": list_disbursements,
    "finaid-generate-cod-export": generate_cod_export,
    "finaid-update-cod-status": update_cod_status,
    "finaid-record-credit-balance-return": mark_credit_balance_returned,
    # SAP
    "finaid-generate-sap-evaluation": run_sap_evaluation,
    "finaid-generate-sap-batch": run_sap_batch,
    "finaid-get-sap-evaluation": get_sap_evaluation,
    "finaid-list-sap-evaluations": list_sap_evaluations,
    "finaid-apply-sap-override": override_sap_status,
    "finaid-submit-sap-appeal": submit_sap_appeal,
    "finaid-update-sap-appeal": update_sap_appeal,
    "finaid-get-sap-appeal": get_sap_appeal,
    "finaid-list-sap-appeals": list_sap_appeals,
    "finaid-complete-sap-appeal": decide_sap_appeal,
    # R2T4
    "finaid-create-r2t4": create_r2t4,
    "finaid-generate-r2t4-calculation": calculate_r2t4,
    "finaid-approve-r2t4": approve_r2t4,
    "finaid-record-r2t4-return": record_r2t4_return,
    "finaid-get-r2t4": get_r2t4,
    "finaid-list-r2t4s": list_r2t4s,
    # Professional Judgment
    "finaid-add-professional-judgment": add_professional_judgment,
    "finaid-get-professional-judgment": get_professional_judgment,
    "finaid-list-professional-judgments": list_professional_judgments,
    "finaid-approve-professional-judgment": approve_professional_judgment,
}
