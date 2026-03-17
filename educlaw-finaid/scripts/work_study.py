"""EduClaw Financial Aid — work_study domain module

Actions for the work_study domain: job postings, student assignments,
timesheets, payroll export, and earnings summaries.

Imported by db_query.py (unified router).
"""
import csv
import io
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, dynamic_update, update_row
except ImportError:
    pass

SKILL = "finaid-educlaw-finaid"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_today = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# WORK STUDY JOB
# ---------------------------------------------------------------------------

def add_work_study_job(conn, args):
    company_id = getattr(args, "company_id", None)
    aid_year_id = getattr(args, "aid_year_id", None)
    job_title = getattr(args, "job_title", None)
    job_type = getattr(args, "job_type", None)
    pay_rate = getattr(args, "pay_rate", None)
    total_positions = getattr(args, "total_positions", None)

    if not company_id:
        err("--company-id is required")
    if not aid_year_id:
        err("--aid-year-id is required")
    if not job_title:
        err("--job-title is required")
    if not job_type:
        err("--job-type is required")
    if job_type not in ("on_campus", "off_campus_community", "off_campus_other"):
        err("--job-type must be on_campus, off_campus_community, or off_campus_other")
    if not pay_rate:
        err("--pay-rate is required")
    if not total_positions:
        err("--total-positions is required")

    department_id = getattr(args, "department_id", None) or ""
    supervisor_id = getattr(args, "supervisor_id", None) or ""
    description = getattr(args, "description", None) or ""
    hours_per_week = getattr(args, "hours_per_week", None) or "0"

    job_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("finaid_work_study_job", {"id": P(), "job_title": P(), "department_id": P(), "supervisor_id": P(), "job_type": P(), "description": P(), "pay_rate": P(), "hours_per_week": P(), "total_positions": P(), "filled_positions": P(), "aid_year_id": P(), "status": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (job_id, job_title, department_id, supervisor_id, job_type, description,
             str(to_decimal(pay_rate)), str(to_decimal(hours_per_week)),
             int(total_positions), 0,
             aid_year_id, "open", company_id, now, now,
             getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Failed to create work study job: {e}")

    audit(conn, SKILL, "finaid-add-work-study-job", "finaid_work_study_job", job_id,
          new_values={"job_title": job_title, "job_type": job_type, "status": "open"})
    conn.commit()
    ok({
        "id": job_id,
        "job_title": job_title,
        "job_type": job_type,
        "pay_rate": str(to_decimal(pay_rate)),
        "total_positions": int(total_positions),
        "status": "open",
        "company_id": company_id,
    })


def update_work_study_job(conn, args):
    job_id = getattr(args, "id", None)
    if not job_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_job")).select(Table("finaid_work_study_job").star).where(Field("id") == P()).get_sql(), (job_id,)).fetchone()
    if not row:
        err(f"Work study job {job_id} not found")

    data = {}
    changed = []

    if getattr(args, "job_title", None) is not None:
        data["job_title"] = args.job_title
        changed.append("job_title")
    if getattr(args, "description", None) is not None:
        data["description"] = args.description
        changed.append("description")
    if getattr(args, "pay_rate", None) is not None:
        data["pay_rate"] = str(to_decimal(args.pay_rate))
        changed.append("pay_rate")
    if getattr(args, "hours_per_week", None) is not None:
        data["hours_per_week"] = str(to_decimal(args.hours_per_week))
        changed.append("hours_per_week")
    if getattr(args, "total_positions", None) is not None:
        data["total_positions"] = int(args.total_positions)
        changed.append("total_positions")
    if getattr(args, "department_id", None) is not None:
        data["department_id"] = args.department_id
        changed.append("department_id")
    if getattr(args, "supervisor_id", None) is not None:
        data["supervisor_id"] = args.supervisor_id
        changed.append("supervisor_id")

    if not changed:
        err("No fields to update")

    data["updated_at"] = _now_iso()
    sql, params = dynamic_update("finaid_work_study_job", data=data, where={"id": job_id})
    conn.execute(sql, params)
    conn.commit()
    ok({"id": job_id, "updated_fields": changed})


def get_work_study_job(conn, args):
    job_id = getattr(args, "id", None)
    if not job_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_job")).select(Table("finaid_work_study_job").star).where(Field("id") == P()).get_sql(), (job_id,)).fetchone()
    if not row:
        err(f"Work study job {job_id} not found")

    data = dict(row)

    _wa = Table("finaid_work_study_assignment")
    active_count_row = conn.execute(
        Q.from_(_wa).select(fn.Count("*").as_("cnt")).where(_wa.job_id == P()).where(_wa.status == P()).get_sql(),
        (job_id, "active")
    ).fetchone()
    data["active_assignment_count"] = active_count_row["cnt"] if active_count_row else 0

    ok(data)


def list_work_study_jobs(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    t = Table("finaid_work_study_job")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]

    if getattr(args, "aid_year_id", None):
        q = q.where(t.aid_year_id == P())
        params.append(args.aid_year_id)
    if getattr(args, "department_id", None):
        q = q.where(t.department_id == P())
        params.append(args.department_id)
    if getattr(args, "status", None):
        q = q.where(t.status == P())
        params.append(args.status)
    if getattr(args, "job_type", None):
        q = q.where(t.job_type == P())
        params.append(args.job_type)

    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([limit, offset])

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"jobs": [dict(r) for r in rows], "count": len(rows)})


def close_work_study_job(conn, args):
    job_id = getattr(args, "id", None)
    if not job_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_job")).select(Table("finaid_work_study_job").star).where(Field("id") == P()).get_sql(), (job_id,)).fetchone()
    if not row:
        err(f"Work study job {job_id} not found")

    _wj = Table("finaid_work_study_job")
    sql = Q.update(_wj).set(_wj.status, "closed").set(_wj.updated_at, P()).where(_wj.id == P()).get_sql()
    conn.execute(sql, (_now_iso(), job_id))
    conn.commit()
    ok({"id": job_id, "status": "closed"})


# ---------------------------------------------------------------------------
# WORK STUDY ASSIGNMENT
# ---------------------------------------------------------------------------

def assign_student_to_job(conn, args):
    student_id = getattr(args, "student_id", None)
    award_id = getattr(args, "award_id", None)
    job_id = getattr(args, "job_id", None)
    aid_year_id = getattr(args, "aid_year_id", None)
    academic_term_id = getattr(args, "academic_term_id", None)
    company_id = getattr(args, "company_id", None)
    start_date = getattr(args, "start_date", None)
    end_date = getattr(args, "end_date", None)
    award_limit = getattr(args, "award_limit", None)

    if not student_id:
        err("--student-id is required")
    if not award_id:
        err("--award-id is required")
    if not job_id:
        err("--job-id is required")
    if not aid_year_id:
        err("--aid-year-id is required")
    if not academic_term_id:
        err("--academic-term-id is required")
    if not company_id:
        err("--company-id is required")
    if not start_date:
        err("--start-date is required")
    if not end_date:
        err("--end-date is required")
    if not award_limit:
        err("--award-limit is required")

    # Validate job exists and is open
    job_row = conn.execute(Q.from_(Table("finaid_work_study_job")).select(Table("finaid_work_study_job").star).where(Field("id") == P()).get_sql(), (job_id,)).fetchone()
    if not job_row:
        err(f"Work study job {job_id} not found")
    job = dict(job_row)
    if job["status"] != "open":
        err(f"Job {job_id} is not open (status: {job['status']})")

    # Validate award_id is a valid FWS award
    _fa = Table("finaid_award")
    award_row = conn.execute(
        Q.from_(_fa).select(_fa.star).where(_fa.id == P()).where(_fa.aid_type == P()).get_sql(),
        (award_id, "fws")
    ).fetchone()
    if not award_row:
        err(f"Award {award_id} not found or is not a Federal Work Study (fws) award")

    assignment_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("finaid_work_study_assignment", {"id": P(), "student_id": P(), "award_id": P(), "job_id": P(), "aid_year_id": P(), "academic_term_id": P(), "start_date": P(), "end_date": P(), "award_limit": P(), "earned_to_date": P(), "status": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (assignment_id, student_id, award_id, job_id, aid_year_id, academic_term_id,
             start_date, end_date, str(to_decimal(award_limit)), "0.00", "active",
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Failed to create assignment: {e}")

    # Increment filled_positions
    new_filled = job["filled_positions"] + 1
    new_status = "filled" if new_filled >= job["total_positions"] else job["status"]
    _wj = Table("finaid_work_study_job")
    sql = Q.update(_wj).set(_wj.filled_positions, P()).set(_wj.status, P()).set(_wj.updated_at, P()).where(_wj.id == P()).get_sql()
    conn.execute(sql, (new_filled, new_status, now, job_id))

    audit(conn, SKILL, "finaid-assign-student-to-job", "finaid_work_study_assignment", assignment_id,
          new_values={"student_id": student_id, "job_id": job_id, "status": "active"})
    conn.commit()
    ok({
        "id": assignment_id,
        "student_id": student_id,
        "job_id": job_id,
        "award_id": award_id,
        "status": "active",
        "job_status": new_status,
    })


def update_work_study_assignment(conn, args):
    assignment_id = getattr(args, "id", None)
    if not assignment_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_assignment")).select(Table("finaid_work_study_assignment").star).where(Field("id") == P()).get_sql(), (assignment_id,)).fetchone()
    if not row:
        err(f"Work study assignment {assignment_id} not found")

    data = {}
    changed = []

    if getattr(args, "start_date", None) is not None:
        data["start_date"] = args.start_date
        changed.append("start_date")
    if getattr(args, "end_date", None) is not None:
        data["end_date"] = args.end_date
        changed.append("end_date")
    if getattr(args, "award_limit", None) is not None:
        data["award_limit"] = str(to_decimal(args.award_limit))
        changed.append("award_limit")

    if not changed:
        err("No fields to update")

    data["updated_at"] = _now_iso()
    sql, params = dynamic_update("finaid_work_study_assignment", data=data, where={"id": assignment_id})
    conn.execute(sql, params)
    conn.commit()
    ok({"id": assignment_id, "updated_fields": changed})


def get_work_study_assignment(conn, args):
    assignment_id = getattr(args, "id", None)
    if not assignment_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_assignment")).select(Table("finaid_work_study_assignment").star).where(Field("id") == P()).get_sql(), (assignment_id,)).fetchone()
    if not row:
        err(f"Work study assignment {assignment_id} not found")

    data = dict(row)

    # Earnings summary: sum of approved timesheet earnings
    # PyPika: skipped — COALESCE(SUM(CAST(... AS REAL))) aggregate
    earnings_row = conn.execute(
        """SELECT COALESCE(SUM(CAST(earnings AS NUMERIC)), 0) as approved_earnings
           FROM finaid_work_study_timesheet
           WHERE assignment_id = ? AND supervisor_approval_status = 'approved'""",
        (assignment_id,)
    ).fetchone()
    data["approved_earnings_sum"] = str(
        round_currency(to_decimal(earnings_row["approved_earnings"]))
    ) if earnings_row else "0.00"

    ok(data)


def list_work_study_assignments(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    t = Table("finaid_work_study_assignment")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]

    if getattr(args, "student_id", None):
        q = q.where(t.student_id == P())
        params.append(args.student_id)
    if getattr(args, "job_id", None):
        q = q.where(t.job_id == P())
        params.append(args.job_id)
    if getattr(args, "academic_term_id", None):
        q = q.where(t.academic_term_id == P())
        params.append(args.academic_term_id)
    if getattr(args, "status", None):
        q = q.where(t.status == P())
        params.append(args.status)

    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    params.extend([limit, offset])

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"assignments": [dict(r) for r in rows], "count": len(rows)})


def terminate_work_study_assignment(conn, args):
    assignment_id = getattr(args, "id", None)
    if not assignment_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_assignment")).select(Table("finaid_work_study_assignment").star).where(Field("id") == P()).get_sql(), (assignment_id,)).fetchone()
    if not row:
        err(f"Work study assignment {assignment_id} not found")

    assignment = dict(row)
    now = _now_iso()

    _wa = Table("finaid_work_study_assignment")
    sql = Q.update(_wa).set(_wa.status, "terminated").set(_wa.updated_at, P()).where(_wa.id == P()).get_sql()
    conn.execute(sql, (now, assignment_id))

    # Decrement job filled_positions; if job was filled, set back to open
    _wj = Table("finaid_work_study_job")
    job_row = conn.execute(
        Q.from_(_wj).select(_wj.star).where(_wj.id == P()).get_sql(), (assignment["job_id"],)
    ).fetchone()
    if job_row:
        job = dict(job_row)
        new_filled = max(0, job["filled_positions"] - 1)
        new_job_status = "open" if job["status"] == "filled" else job["status"]
        sql = Q.update(_wj).set(_wj.filled_positions, P()).set(_wj.status, P()).set(_wj.updated_at, P()).where(_wj.id == P()).get_sql()
        conn.execute(sql, (new_filled, new_job_status, now, job["id"]))

    audit(conn, SKILL, "finaid-terminate-work-study-assignment", "finaid_work_study_assignment",
          assignment_id, new_values={"status": "terminated"})
    conn.commit()
    ok({"id": assignment_id, "status": "terminated"})


# ---------------------------------------------------------------------------
# WORK STUDY TIMESHEET
# ---------------------------------------------------------------------------

def submit_work_study_timesheet(conn, args):
    assignment_id = getattr(args, "assignment_id", None)
    student_id = getattr(args, "student_id", None)
    company_id = getattr(args, "company_id", None)
    pay_period_start = getattr(args, "pay_period_start", None)
    pay_period_end = getattr(args, "pay_period_end", None)
    hours_worked = getattr(args, "hours_worked", None)
    submission_date = getattr(args, "submission_date", None)

    if not assignment_id:
        err("--assignment-id is required")
    if not student_id:
        err("--student-id is required")
    if not company_id:
        err("--company-id is required")
    if not pay_period_start:
        err("--pay-period-start is required")
    if not pay_period_end:
        err("--pay-period-end is required")
    if not hours_worked:
        err("--hours-worked is required")
    if not submission_date:
        err("--submission-date is required")

    # Validate assignment is active
    assignment_row = conn.execute(Q.from_(Table("finaid_work_study_assignment")).select(Table("finaid_work_study_assignment").star).where(Field("id") == P()).get_sql(), (assignment_id,)).fetchone()
    if not assignment_row:
        err(f"Assignment {assignment_id} not found")
    assignment = dict(assignment_row)
    if assignment["status"] != "active":
        err(f"Assignment {assignment_id} is not active (status: {assignment['status']})")

    # Check for duplicate (unique assignment_id + pay_period_start)
    dup = conn.execute(Q.from_(Table("finaid_work_study_timesheet")).select(Field("id")).where(Field("assignment_id") == P()).where(Field("pay_period_start") == P()).get_sql(), (assignment_id, pay_period_start)).fetchone()
    if dup:
        err(f"Timesheet already exists for assignment {assignment_id} and pay period starting {pay_period_start}")

    # Get pay_rate from job
    _wj = Table("finaid_work_study_job")
    job_row = conn.execute(
        Q.from_(_wj).select(_wj.star).where(_wj.id == P()).get_sql(), (assignment["job_id"],)
    ).fetchone()
    if not job_row:
        err(f"Job {assignment['job_id']} not found")
    job = dict(job_row)

    hours = to_decimal(hours_worked)
    pay_rate = to_decimal(job["pay_rate"])
    earnings = round_currency(hours * pay_rate)

    earned_to_date = to_decimal(assignment["earned_to_date"])
    award_limit = to_decimal(assignment["award_limit"])
    remaining = award_limit - earned_to_date

    # Cap earnings if they would exceed award_limit
    if earnings > remaining:
        earnings = round_currency(remaining)

    cumulative_earnings = round_currency(earned_to_date + earnings)

    timesheet_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        sql, _ = insert_row("finaid_work_study_timesheet", {"id": P(), "assignment_id": P(), "student_id": P(), "pay_period_start": P(), "pay_period_end": P(), "hours_worked": P(), "earnings": P(), "cumulative_earnings": P(), "submission_date": P(), "supervisor_approval_status": P(), "supervisor_approved_by": P(), "supervisor_approved_date": P(), "rejection_reason": P(), "payroll_exported": P(), "payroll_export_date": P(), "company_id": P(), "created_at": P(), "updated_at": P(), "created_by": P()})

        conn.execute(sql,
            (timesheet_id, assignment_id, student_id, pay_period_start, pay_period_end,
             str(hours), str(earnings), str(cumulative_earnings), submission_date,
             "pending", "", "", "", 0, "",
             company_id, now, now, getattr(args, "user_id", None) or "")
        )
    except sqlite3.IntegrityError as e:
        err(f"Failed to submit timesheet: {e}")

    audit(conn, SKILL, "finaid-submit-work-study-timesheet", "finaid_work_study_timesheet",
          timesheet_id,
          new_values={"assignment_id": assignment_id, "hours_worked": str(hours),
                      "earnings": str(earnings)})
    conn.commit()
    ok({
        "id": timesheet_id,
        "assignment_id": assignment_id,
        "student_id": student_id,
        "pay_period_start": pay_period_start,
        "pay_period_end": pay_period_end,
        "hours_worked": str(hours),
        "earnings": str(earnings),
        "cumulative_earnings": str(cumulative_earnings),
        "supervisor_approval_status": "pending",
    })


def update_work_study_timesheet(conn, args):
    timesheet_id = getattr(args, "id", None)
    if not timesheet_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_timesheet")).select(Table("finaid_work_study_timesheet").star).where(Field("id") == P()).get_sql(), (timesheet_id,)).fetchone()
    if not row:
        err(f"Timesheet {timesheet_id} not found")

    ts = dict(row)
    if ts["supervisor_approval_status"] != "pending":
        err(f"Timesheet {timesheet_id} cannot be updated: approval status is '{ts['supervisor_approval_status']}' (must be 'pending')")

    updates, params, changed = [], [], []

    hours_worked = getattr(args, "hours_worked", None)
    if hours_worked is not None:
        hours = to_decimal(hours_worked)

        # Recompute earnings based on job pay_rate
        _wa = Table("finaid_work_study_assignment")
        assignment_row = conn.execute(
            Q.from_(_wa).select(_wa.star).where(_wa.id == P()).get_sql(), (ts["assignment_id"],)
        ).fetchone()
        if not assignment_row:
            err(f"Assignment {ts['assignment_id']} not found")
        assignment = dict(assignment_row)

        _wj = Table("finaid_work_study_job")
        job_row = conn.execute(
            Q.from_(_wj).select(_wj.star).where(_wj.id == P()).get_sql(), (assignment["job_id"],)
        ).fetchone()
        if not job_row:
            err(f"Job {assignment['job_id']} not found")
        job = dict(job_row)

        pay_rate = to_decimal(job["pay_rate"])
        earnings = round_currency(hours * pay_rate)

        earned_to_date = to_decimal(assignment["earned_to_date"])
        award_limit = to_decimal(assignment["award_limit"])
        remaining = award_limit - earned_to_date

        if earnings > remaining:
            earnings = round_currency(remaining)

        cumulative_earnings = round_currency(earned_to_date + earnings)

        updates.append("hours_worked = ?")
        params.append(str(hours))
        changed.append("hours_worked")
        updates.append("earnings = ?")
        params.append(str(earnings))
        changed.append("earnings")
        updates.append("cumulative_earnings = ?")
        params.append(str(cumulative_earnings))
        changed.append("cumulative_earnings")

    if not changed:
        err("No fields to update")

    data = {}
    for i, field_name in enumerate(changed):
        data[field_name] = params[i]
    data["updated_at"] = _now_iso()
    _sql, _params = dynamic_update("finaid_work_study_timesheet", data=data, where={"id": timesheet_id})
    conn.execute(_sql, _params)
    conn.commit()
    ok({"id": timesheet_id, "updated_fields": changed})


def approve_work_study_timesheet(conn, args):
    timesheet_id = getattr(args, "id", None)
    supervisor_approved_by = getattr(args, "supervisor_approved_by", None)

    if not timesheet_id:
        err("--id is required")
    if not supervisor_approved_by:
        err("--supervisor-approved-by is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_timesheet")).select(Table("finaid_work_study_timesheet").star).where(Field("id") == P()).get_sql(), (timesheet_id,)).fetchone()
    if not row:
        err(f"Timesheet {timesheet_id} not found")

    ts = dict(row)
    if ts["supervisor_approval_status"] != "pending":
        err(f"Timesheet {timesheet_id} cannot be approved: status is '{ts['supervisor_approval_status']}'")

    today = _today()
    now = _now_iso()

    _ts = Table("finaid_work_study_timesheet")
    sql = (Q.update(_ts)
           .set(_ts.supervisor_approval_status, "approved")
           .set(_ts.supervisor_approved_by, P())
           .set(_ts.supervisor_approved_date, P())
           .set(_ts.updated_at, P())
           .where(_ts.id == P()).get_sql())
    conn.execute(sql, (supervisor_approved_by, today, now, timesheet_id))

    # Update assignment.earned_to_date += earnings
    earnings = to_decimal(ts["earnings"])
    # PyPika: skipped — inline CAST(ROUND(CAST(...) + ?, 2) AS TEXT) expression
    conn.execute(
        """UPDATE finaid_work_study_assignment
           SET earned_to_date = CAST(ROUND(CAST(earned_to_date AS NUMERIC) + ?, 2) AS TEXT),
               updated_at = ?
           WHERE id = ?""",
        (float(earnings), now, ts["assignment_id"])
    )

    audit(conn, SKILL, "finaid-approve-work-study-timesheet", "finaid_work_study_timesheet",
          timesheet_id,
          new_values={"supervisor_approval_status": "approved",
                      "supervisor_approved_by": supervisor_approved_by})
    conn.commit()
    ok({
        "id": timesheet_id,
        "supervisor_approval_status": "approved",
        "supervisor_approved_by": supervisor_approved_by,
        "supervisor_approved_date": today,
    })


def reject_work_study_timesheet(conn, args):
    timesheet_id = getattr(args, "id", None)
    supervisor_approved_by = getattr(args, "supervisor_approved_by", None)

    if not timesheet_id:
        err("--id is required")
    if not supervisor_approved_by:
        err("--supervisor-approved-by is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_timesheet")).select(Table("finaid_work_study_timesheet").star).where(Field("id") == P()).get_sql(), (timesheet_id,)).fetchone()
    if not row:
        err(f"Timesheet {timesheet_id} not found")

    ts = dict(row)
    if ts["supervisor_approval_status"] != "pending":
        err(f"Timesheet {timesheet_id} cannot be rejected: status is '{ts['supervisor_approval_status']}'")

    rejection_reason = getattr(args, "rejection_reason", None) or ""
    now = _now_iso()

    _ts = Table("finaid_work_study_timesheet")
    sql = (Q.update(_ts)
           .set(_ts.supervisor_approval_status, "rejected")
           .set(_ts.supervisor_approved_by, P())
           .set(_ts.rejection_reason, P())
           .set(_ts.updated_at, P())
           .where(_ts.id == P()).get_sql())
    conn.execute(sql, (supervisor_approved_by, rejection_reason, now, timesheet_id))

    audit(conn, SKILL, "finaid-reject-work-study-timesheet", "finaid_work_study_timesheet",
          timesheet_id,
          new_values={"supervisor_approval_status": "rejected",
                      "supervisor_approved_by": supervisor_approved_by})
    conn.commit()
    ok({
        "id": timesheet_id,
        "supervisor_approval_status": "rejected",
        "supervisor_approved_by": supervisor_approved_by,
        "rejection_reason": rejection_reason,
    })


def get_work_study_timesheet(conn, args):
    timesheet_id = getattr(args, "id", None)
    if not timesheet_id:
        err("--id is required")

    row = conn.execute(Q.from_(Table("finaid_work_study_timesheet")).select(Table("finaid_work_study_timesheet").star).where(Field("id") == P()).get_sql(), (timesheet_id,)).fetchone()
    if not row:
        err(f"Timesheet {timesheet_id} not found")

    ok(dict(row))


def list_work_study_timesheets(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    t = Table("finaid_work_study_timesheet")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    params = [company_id]

    if getattr(args, "student_id", None):
        q = q.where(t.student_id == P())
        params.append(args.student_id)
    if getattr(args, "assignment_id", None):
        q = q.where(t.assignment_id == P())
        params.append(args.assignment_id)
    if getattr(args, "supervisor_approval_status", None):
        q = q.where(t.supervisor_approval_status == P())
        params.append(args.supervisor_approval_status)
    if getattr(args, "pay_period_start", None):
        q = q.where(t.pay_period_start == P())
        params.append(args.pay_period_start)

    limit = int(getattr(args, "limit", None) or 50)
    offset = int(getattr(args, "offset", None) or 0)
    q = q.orderby(t.pay_period_start, order=Order.desc).limit(P()).offset(P())
    params.extend([limit, offset])

    rows = conn.execute(q.get_sql(), params).fetchall()
    ok({"timesheets": [dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# PAYROLL EXPORT
# ---------------------------------------------------------------------------

def export_work_study_payroll(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        err("--company-id is required")

    # PyPika: skipped — complex 3-table JOIN with conditional WHERE appends
    query = """
        SELECT
            t.id as timesheet_id,
            t.student_id,
            t.assignment_id,
            j.job_title,
            t.pay_period_start,
            t.pay_period_end,
            t.hours_worked,
            t.earnings,
            t.supervisor_approved_by
        FROM finaid_work_study_timesheet t
        JOIN finaid_work_study_assignment a ON a.id = t.assignment_id
        JOIN finaid_work_study_job j ON j.id = a.job_id
        WHERE t.company_id = ?
          AND t.supervisor_approval_status = 'approved'
          AND t.payroll_exported = 0
    """
    params = [company_id]

    if getattr(args, "academic_term_id", None):
        query += " AND a.academic_term_id = ?"
        params.append(args.academic_term_id)
    if getattr(args, "pay_period_start", None):
        query += " AND t.pay_period_start = ?"
        params.append(args.pay_period_start)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        ok({"exported_count": 0, "total_amount": "0.00", "csv_data": ""})
        return

    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "student_id", "assignment_id", "job_title",
        "pay_period_start", "pay_period_end",
        "hours_worked", "earnings", "supervisor_approved_by"
    ])
    writer.writeheader()

    total_amount = Decimal("0")
    timesheet_ids = []

    for row in rows:
        r = dict(row)
        timesheet_ids.append(r["timesheet_id"])
        total_amount += to_decimal(r["earnings"])
        writer.writerow({
            "student_id": r["student_id"],
            "assignment_id": r["assignment_id"],
            "job_title": r["job_title"],
            "pay_period_start": r["pay_period_start"],
            "pay_period_end": r["pay_period_end"],
            "hours_worked": r["hours_worked"],
            "earnings": r["earnings"],
            "supervisor_approved_by": r["supervisor_approved_by"],
        })

    csv_data = output.getvalue()
    today = _today()
    now = _now_iso()

    # Mark timesheets as exported
    _ts = Table("finaid_work_study_timesheet")
    _mark_sql = Q.update(_ts).set(_ts.payroll_exported, 1).set(_ts.payroll_export_date, P()).set(_ts.updated_at, P()).where(_ts.id == P()).get_sql()
    for ts_id in timesheet_ids:
        conn.execute(_mark_sql, (today, now, ts_id))

    conn.commit()
    ok({
        "exported_count": len(timesheet_ids),
        "total_amount": str(round_currency(total_amount)),
        "csv_data": csv_data,
    })


# ---------------------------------------------------------------------------
# EARNINGS SUMMARY
# ---------------------------------------------------------------------------

def get_work_study_earnings_summary(conn, args):
    student_id = getattr(args, "student_id", None)
    aid_year_id = getattr(args, "aid_year_id", None)
    company_id = getattr(args, "company_id", None)

    if not student_id:
        err("--student-id is required")
    if not aid_year_id:
        err("--aid-year-id is required")
    if not company_id:
        err("--company-id is required")

    # Get the active assignment for this student/aid_year/company
    # PyPika: skipped — JOIN with column alias from joined table
    assignment_row = conn.execute(
        """SELECT a.*, j.job_type
           FROM finaid_work_study_assignment a
           JOIN finaid_work_study_job j ON j.id = a.job_id
           WHERE a.student_id = ? AND a.aid_year_id = ? AND a.company_id = ?
             AND a.status = 'active'
           LIMIT 1""",
        (student_id, aid_year_id, company_id)
    ).fetchone()

    award_limit = Decimal("0")
    if assignment_row:
        award_limit = to_decimal(dict(assignment_row)["award_limit"])

    # Sum of approved timesheet earnings for the student/aid_year
    # PyPika: skipped — COALESCE(SUM(CAST(... AS REAL))) with JOIN
    earned_row = conn.execute(
        """SELECT COALESCE(SUM(CAST(t.earnings AS NUMERIC)), 0) as total_earned
           FROM finaid_work_study_timesheet t
           JOIN finaid_work_study_assignment a ON a.id = t.assignment_id
           WHERE a.student_id = ? AND a.aid_year_id = ? AND a.company_id = ?
             AND t.supervisor_approval_status = 'approved'""",
        (student_id, aid_year_id, company_id)
    ).fetchone()

    earned_to_date = to_decimal(earned_row["total_earned"]) if earned_row else Decimal("0")
    remaining_limit = round_currency(max(Decimal("0"), award_limit - earned_to_date))

    # Community service hours: sum of hours from on_campus or off_campus_community jobs
    # PyPika: skipped — COALESCE(SUM(CAST())) with 3-table JOIN and IN clause
    community_hours_row = conn.execute(
        """SELECT COALESCE(SUM(CAST(t.hours_worked AS REAL)), 0) as community_hours
           FROM finaid_work_study_timesheet t
           JOIN finaid_work_study_assignment a ON a.id = t.assignment_id
           JOIN finaid_work_study_job j ON j.id = a.job_id
           WHERE a.student_id = ? AND a.aid_year_id = ? AND a.company_id = ?
             AND j.job_type IN ('on_campus', 'off_campus_community')
             AND t.supervisor_approval_status = 'approved'""",
        (student_id, aid_year_id, company_id)
    ).fetchone()

    community_service_hours = to_decimal(
        community_hours_row["community_hours"]
    ) if community_hours_row else Decimal("0")

    ok({
        "student_id": student_id,
        "aid_year_id": aid_year_id,
        "company_id": company_id,
        "award_limit": str(round_currency(award_limit)),
        "earned_to_date": str(round_currency(earned_to_date)),
        "remaining_limit": str(remaining_limit),
        "community_service_hours": str(community_service_hours),
    })


# ---------------------------------------------------------------------------
# ACTIONS REGISTRY
# ---------------------------------------------------------------------------

ACTIONS = {
    "finaid-add-work-study-job": add_work_study_job,
    "finaid-update-work-study-job": update_work_study_job,
    "finaid-get-work-study-job": get_work_study_job,
    "finaid-list-work-study-jobs": list_work_study_jobs,
    "finaid-terminate-work-study-job": close_work_study_job,
    "finaid-assign-student-to-job": assign_student_to_job,
    "finaid-update-work-study-assignment": update_work_study_assignment,
    "finaid-get-work-study-assignment": get_work_study_assignment,
    "finaid-list-work-study-assignments": list_work_study_assignments,
    "finaid-terminate-work-study-assignment": terminate_work_study_assignment,
    "finaid-submit-work-study-timesheet": submit_work_study_timesheet,
    "finaid-update-work-study-timesheet": update_work_study_timesheet,
    "finaid-approve-work-study-timesheet": approve_work_study_timesheet,
    "finaid-deny-work-study-timesheet": reject_work_study_timesheet,
    "finaid-get-work-study-timesheet": get_work_study_timesheet,
    "finaid-list-work-study-timesheets": list_work_study_timesheets,
    "finaid-generate-payroll-export": export_work_study_payroll,
    "finaid-get-work-study-earnings-summary": get_work_study_earnings_summary,
}
