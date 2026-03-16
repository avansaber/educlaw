"""EduClaw Higher Education — finaid domain module (10 actions)

Financial aid packages, disbursements, SAP calculation, need analysis, reports.
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row, dynamic_update
    from erpclaw_lib.vendor.pypika.terms import LiteralValue

    ENTITY_PREFIXES.setdefault("educlaw_scholarship", "HAID-")
except ImportError:
    pass

SKILL = "highered-educlaw-highered"
_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
VALID_PACKAGE_STATUSES = ("draft", "offered", "accepted", "revised", "cancelled")
VALID_AID_TYPES = ("grant", "scholarship", "loan", "work_study")


def _to_money(val):
    if val is None:
        return "0.00"
    return str(round_currency(to_decimal(val)))


def add_aid_package(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    aid_year = getattr(args, "aid_year", None) or ""
    total_cost = _to_money(getattr(args, "total_cost", None))
    efc = _to_money(getattr(args, "efc", None))
    total_need = _to_money(getattr(args, "total_need", None))
    grants = _to_money(getattr(args, "grants", None))
    scholarships = _to_money(getattr(args, "scholarships", None))
    loans = _to_money(getattr(args, "loans", None))
    work_study = _to_money(getattr(args, "work_study", None))
    total_aid = str(round_currency(
        to_decimal(grants) + to_decimal(scholarships) +
        to_decimal(loans) + to_decimal(work_study)
    ))
    pkg_id = str(uuid.uuid4())
    now = _now_iso()
    naming = get_next_name(conn, "educlaw_scholarship", company_id=company_id)
    sql, _ = insert_row("educlaw_scholarship", {
        "id": P(), "naming_series": P(), "student_id": P(), "aid_year": P(),
        "total_cost": P(), "efc": P(), "total_need": P(), "grants": P(),
        "scholarships": P(), "loans": P(), "work_study": P(), "total_aid": P(),
        "package_status": P(), "company_id": P(), "created_at": P(), "updated_at": P(),
    })
    conn.execute(sql, (pkg_id, naming, student_id, aid_year, total_cost, efc, total_need,
          grants, scholarships, loans, work_study, total_aid,
          "draft", company_id, now, now))
    audit(conn, SKILL, "highered-add-aid-package", "educlaw_scholarship", pkg_id,
          new_values={"student_id": student_id, "total_aid": total_aid})
    conn.commit()
    ok({"id": pkg_id, "naming_series": naming, "student_id": student_id,
        "total_aid": total_aid, "package_status": "draft"})


def update_aid_package(conn, args):
    pkg_id = getattr(args, "id", None)
    if not pkg_id:
        return err("--id is required")
    row = conn.execute(Q.from_(Table("educlaw_scholarship")).select(Table("educlaw_scholarship").star).where(Field("id") == P()).get_sql(), (pkg_id,)).fetchone()
    if not row:
        return err("Aid package not found")
    if row["package_status"] == "cancelled":
        return err("Cannot update a cancelled package")
    data = {}
    for field in ("aid_year",):
        val = getattr(args, field, None)
        if val is not None:
            data[field] = val
    for mf in ("total_cost", "efc", "total_need", "grants", "scholarships", "loans", "work_study"):
        val = getattr(args, mf, None)
        if val is not None:
            data[mf] = _to_money(val)
    package_status = getattr(args, "package_status", None)
    if package_status is not None:
        if package_status not in VALID_PACKAGE_STATUSES:
            return err(f"Invalid package_status: {package_status}")
        data["package_status"] = package_status
    if not data:
        return err("No fields to update")
    recalc = {"grants", "scholarships", "loans", "work_study"}
    if recalc.intersection(data.keys()):
        cur = dict(row)
        for mf in ("grants", "scholarships", "loans", "work_study"):
            val = getattr(args, mf, None)
            if val is not None:
                cur[mf] = _to_money(val)
        total_aid = str(round_currency(
            to_decimal(cur["grants"]) + to_decimal(cur["scholarships"]) +
            to_decimal(cur["loans"]) + to_decimal(cur["work_study"])
        ))
        data["total_aid"] = total_aid
    data["updated_at"] = _now_iso()
    sql, params = dynamic_update("educlaw_scholarship", data, {"id": pkg_id})
    conn.execute(sql, params)
    conn.commit()
    ok({"id": pkg_id, "updated": True})


def get_aid_package(conn, args):
    pkg_id = getattr(args, "id", None)
    if not pkg_id:
        return err("--id is required")
    row = conn.execute(Q.from_(Table("educlaw_scholarship")).select(Table("educlaw_scholarship").star).where(Field("id") == P()).get_sql(), (pkg_id,)).fetchone()
    if not row:
        return err("Aid package not found")
    ok(dict(row))


def list_aid_packages(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t = Table("educlaw_scholarship")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    p = [company_id]
    student_id = getattr(args, "student_id", None)
    if student_id:
        q = q.where(t.student_id == P())
        p.append(student_id)
    aid_year = getattr(args, "aid_year", None)
    if aid_year:
        q = q.where(t.aid_year == P())
        p.append(aid_year)
    package_status = getattr(args, "package_status", None)
    if package_status:
        q = q.where(t.package_status == P())
        p.append(package_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    p.extend([limit, offset])
    rows = conn.execute(q.get_sql(), p).fetchall()
    ok({"packages": [dict(r) for r in rows], "count": len(rows)})


def add_disbursement(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    aid_package_id = getattr(args, "aid_package_id", None)
    if not aid_package_id:
        return err("--aid-package-id is required")
    pkg = conn.execute(Q.from_(Table("educlaw_scholarship")).select(Table("educlaw_scholarship").star).where(Field("id") == P()).get_sql(), (aid_package_id,)).fetchone()
    if not pkg:
        return err(f"Aid package {aid_package_id} not found")
    if pkg["package_status"] not in ("offered", "accepted"):
        return err("Aid package must be offered or accepted for disbursement")
    amount = _to_money(getattr(args, "amount", None))
    if to_decimal(amount) <= Decimal("0"):
        return err("--amount must be positive")
    aid_type = getattr(args, "aid_type", None) or "grant"
    if aid_type not in VALID_AID_TYPES:
        return err(f"Invalid aid_type: {aid_type}")
    fund_source = getattr(args, "fund_source", None) or ""
    disbursement_date = getattr(args, "disbursement_date", None) or _now_iso()
    disb_id = str(uuid.uuid4())
    sql, _ = insert_row("highered_disbursement", {
        "id": P(), "aid_package_id": P(), "disbursement_date": P(),
        "amount": P(), "aid_type": P(), "fund_source": P(),
        "disbursement_status": P(), "company_id": P(), "created_at": P(),
    })
    conn.execute(sql, (disb_id, aid_package_id, disbursement_date, amount, aid_type,
          fund_source, "pending", company_id, _now_iso()))
    conn.commit()
    ok({"id": disb_id, "aid_package_id": aid_package_id,
        "amount": amount, "aid_type": aid_type, "disbursement_status": "pending"})


def list_disbursements(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    t = Table("highered_disbursement")
    q = Q.from_(t).select(t.star).where(t.company_id == P())
    p = [company_id]
    aid_package_id = getattr(args, "aid_package_id", None)
    if aid_package_id:
        q = q.where(t.aid_package_id == P())
        p.append(aid_package_id)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q = q.orderby(t.created_at, order=Order.desc).limit(P()).offset(P())
    p.extend([limit, offset])
    rows = conn.execute(q.get_sql(), p).fetchall()
    ok({"disbursements": [dict(r) for r in rows], "count": len(rows)})


def calculate_sap(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute(Q.from_(Table("educlaw_student")).select(Table("educlaw_student").star).where(Field("student_id") == P()).get_sql(), (student_id,)).fetchone()
    if not record:
        return err("Student record not found")
    program = conn.execute(Q.from_(Table("highered_degree_program")).select(Table("highered_degree_program").star).where(Field("id") == P()).get_sql(), (record["program_id"],)).fetchone()
    attempted = conn.execute("""
        SELECT SUM(c.credits) as total_credits
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status IN ('completed','dropped','enrolled')
    """, (student_id,)).fetchone()
    completed = conn.execute("""
        SELECT SUM(c.credits) as total_credits
        FROM educlaw_course_enrollment e
        JOIN educlaw_section s ON e.section_id = s.id
        JOIN educlaw_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status='completed' AND e.grade NOT IN ('F','')
    """, (student_id,)).fetchone()
    attempted_credits = attempted["total_credits"] or 0
    completed_credits = completed["total_credits"] or 0
    gpa = to_decimal(record["gpa"])
    completion_rate = round(completed_credits / attempted_credits * 100, 1) if attempted_credits > 0 else 0
    max_credits = int((program["credits_required"] if program else 120) * 1.5)
    within_timeframe = attempted_credits <= max_credits
    gpa_met = gpa >= Decimal("2.00")
    pace_met = completion_rate >= 67.0
    sap_met = gpa_met and pace_met and within_timeframe
    ok({
        "student_id": student_id, "gpa": str(gpa), "gpa_requirement": "2.00",
        "gpa_met": gpa_met, "attempted_credits": attempted_credits,
        "completed_credits": completed_credits, "completion_rate": completion_rate,
        "pace_requirement": 67.0, "pace_met": pace_met,
        "max_credits_allowed": max_credits, "within_timeframe": within_timeframe,
        "sap_met": sap_met,
    })


def need_analysis(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    total_cost = _to_money(getattr(args, "total_cost", None))
    efc = _to_money(getattr(args, "efc", None))
    financial_need = str(round_currency(max(to_decimal(total_cost) - to_decimal(efc), Decimal("0"))))
    ok({"student_id": student_id, "total_cost": total_cost, "efc": efc, "financial_need": financial_need})


def aid_summary_report(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    aid_year = getattr(args, "aid_year", None)
    t = Table("educlaw_scholarship")
    q = Q.from_(t).select(t.package_status, fn.Count(t.star).as_("count")).where(t.company_id == P())
    p = [company_id]
    if aid_year:
        q = q.where(t.aid_year == P())
        p.append(aid_year)
    q = q.groupby(t.package_status)
    rows = conn.execute(q.get_sql(), p).fetchall()
    ok({"summary": [dict(r) for r in rows]})


def award_letter_report(conn, args):
    pkg_id = getattr(args, "id", None)
    if not pkg_id:
        return err("--id is required")
    pkg = conn.execute(Q.from_(Table("educlaw_scholarship")).select(Table("educlaw_scholarship").star).where(Field("id") == P()).get_sql(), (pkg_id,)).fetchone()
    if not pkg:
        return err("Aid package not found")
    disbursements = conn.execute(Q.from_(Table("highered_disbursement")).select(Table("highered_disbursement").star).where(Field("aid_package_id") == P()).get_sql(), (pkg_id,)).fetchall()
    ok({"package": dict(pkg), "disbursements": [dict(d) for d in disbursements]})


ACTIONS = {
    "highered-add-aid-package": add_aid_package,
    "highered-update-aid-package": update_aid_package,
    "highered-get-aid-package": get_aid_package,
    "highered-list-aid-packages": list_aid_packages,
    "highered-add-disbursement": add_disbursement,
    "highered-list-disbursements": list_disbursements,
    "highered-calculate-sap": calculate_sap,
    "highered-aid-summary-report": aid_summary_report,
    "highered-need-analysis": need_analysis,
    "highered-award-letter-report": award_letter_report,
}
