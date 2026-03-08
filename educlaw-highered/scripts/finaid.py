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

    ENTITY_PREFIXES.setdefault("highered_aid_package", "HAID-")
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
    conn.company_id = company_id
    naming = get_next_name(conn, "highered_aid_package")
    conn.execute("""
        INSERT INTO highered_aid_package
        (id, naming_series, student_id, aid_year, total_cost, efc, total_need,
         grants, scholarships, loans, work_study, total_aid,
         package_status, company_id, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (pkg_id, naming, student_id, aid_year, total_cost, efc, total_need,
          grants, scholarships, loans, work_study, total_aid,
          "draft", company_id, now, now))
    audit(conn, SKILL, "highered-add-aid-package", "highered_aid_package", pkg_id,
          new_values={"student_id": student_id, "total_aid": total_aid})
    conn.commit()
    ok({"id": pkg_id, "naming_series": naming, "student_id": student_id,
        "total_aid": total_aid, "package_status": "draft"})


def update_aid_package(conn, args):
    pkg_id = getattr(args, "id", None)
    if not pkg_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_aid_package WHERE id=?", (pkg_id,)).fetchone()
    if not row:
        return err("Aid package not found")
    if row["package_status"] == "cancelled":
        return err("Cannot update a cancelled package")
    updates, params = [], []
    for field in ("aid_year",):
        val = getattr(args, field, None)
        if val is not None:
            updates.append(f"{field}=?")
            params.append(val)
    for mf in ("total_cost", "efc", "total_need", "grants", "scholarships", "loans", "work_study"):
        val = getattr(args, mf, None)
        if val is not None:
            updates.append(f"{mf}=?")
            params.append(_to_money(val))
    package_status = getattr(args, "package_status", None)
    if package_status is not None:
        if package_status not in VALID_PACKAGE_STATUSES:
            return err(f"Invalid package_status: {package_status}")
        updates.append("package_status=?")
        params.append(package_status)
    if not updates:
        return err("No fields to update")
    recalc = {"grants", "scholarships", "loans", "work_study"}
    if recalc.intersection(f.split("=")[0] for f in updates):
        cur = dict(row)
        for mf in ("grants", "scholarships", "loans", "work_study"):
            val = getattr(args, mf, None)
            if val is not None:
                cur[mf] = _to_money(val)
        total_aid = str(round_currency(
            to_decimal(cur["grants"]) + to_decimal(cur["scholarships"]) +
            to_decimal(cur["loans"]) + to_decimal(cur["work_study"])
        ))
        updates.append("total_aid=?")
        params.append(total_aid)
    updates.append("updated_at=?")
    params.append(_now_iso())
    params.append(pkg_id)
    conn.execute(f"UPDATE highered_aid_package SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    ok({"id": pkg_id, "updated": True})


def get_aid_package(conn, args):
    pkg_id = getattr(args, "id", None)
    if not pkg_id:
        return err("--id is required")
    row = conn.execute("SELECT * FROM highered_aid_package WHERE id=?", (pkg_id,)).fetchone()
    if not row:
        return err("Aid package not found")
    ok(dict(row))


def list_aid_packages(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_aid_package WHERE company_id=?"
    p = [company_id]
    student_id = getattr(args, "student_id", None)
    if student_id:
        q += " AND student_id=?"
        p.append(student_id)
    aid_year = getattr(args, "aid_year", None)
    if aid_year:
        q += " AND aid_year=?"
        p.append(aid_year)
    package_status = getattr(args, "package_status", None)
    if package_status:
        q += " AND package_status=?"
        p.append(package_status)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    p.extend([limit, offset])
    rows = conn.execute(q, p).fetchall()
    ok({"packages": [dict(r) for r in rows], "count": len(rows)})


def add_disbursement(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    aid_package_id = getattr(args, "aid_package_id", None)
    if not aid_package_id:
        return err("--aid-package-id is required")
    pkg = conn.execute("SELECT * FROM highered_aid_package WHERE id=?", (aid_package_id,)).fetchone()
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
    conn.execute("""
        INSERT INTO highered_disbursement
        (id, aid_package_id, disbursement_date, amount, aid_type,
         fund_source, disbursement_status, company_id, created_at)
        VALUES (?,?,?,?,?,?,'pending',?,?)
    """, (disb_id, aid_package_id, disbursement_date, amount, aid_type,
          fund_source, company_id, _now_iso()))
    conn.commit()
    ok({"id": disb_id, "aid_package_id": aid_package_id,
        "amount": amount, "aid_type": aid_type, "disbursement_status": "pending"})


def list_disbursements(conn, args):
    company_id = getattr(args, "company_id", None)
    if not company_id:
        return err("--company-id is required")
    q = "SELECT * FROM highered_disbursement WHERE company_id=?"
    p = [company_id]
    aid_package_id = getattr(args, "aid_package_id", None)
    if aid_package_id:
        q += " AND aid_package_id=?"
        p.append(aid_package_id)
    limit = int(getattr(args, "limit", 50) or 50)
    offset = int(getattr(args, "offset", 0) or 0)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    p.extend([limit, offset])
    rows = conn.execute(q, p).fetchall()
    ok({"disbursements": [dict(r) for r in rows], "count": len(rows)})


def calculate_sap(conn, args):
    student_id = getattr(args, "student_id", None)
    if not student_id:
        return err("--student-id is required")
    record = conn.execute("SELECT * FROM highered_student_record WHERE student_id=?", (student_id,)).fetchone()
    if not record:
        return err("Student record not found")
    program = conn.execute("SELECT * FROM highered_degree_program WHERE id=?", (record["program_id"],)).fetchone()
    attempted = conn.execute("""
        SELECT SUM(c.credits) as total_credits
        FROM highered_enrollment e
        JOIN highered_section s ON e.section_id = s.id
        JOIN highered_course c ON s.course_id = c.id
        WHERE e.student_id=? AND e.enrollment_status IN ('completed','dropped','enrolled')
    """, (student_id,)).fetchone()
    completed = conn.execute("""
        SELECT SUM(c.credits) as total_credits
        FROM highered_enrollment e
        JOIN highered_section s ON e.section_id = s.id
        JOIN highered_course c ON s.course_id = c.id
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
    q = "SELECT package_status, COUNT(*) as count FROM highered_aid_package WHERE company_id=?"
    p = [company_id]
    if aid_year:
        q += " AND aid_year=?"
        p.append(aid_year)
    q += " GROUP BY package_status"
    rows = conn.execute(q, p).fetchall()
    ok({"summary": [dict(r) for r in rows]})


def award_letter_report(conn, args):
    pkg_id = getattr(args, "id", None)
    if not pkg_id:
        return err("--id is required")
    pkg = conn.execute("SELECT * FROM highered_aid_package WHERE id=?", (pkg_id,)).fetchone()
    if not pkg:
        return err("Aid package not found")
    disbursements = conn.execute("SELECT * FROM highered_disbursement WHERE aid_package_id=?", (pkg_id,)).fetchall()
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
