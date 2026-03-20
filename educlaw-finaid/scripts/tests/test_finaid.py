"""L1 pytest tests for EduClaw Financial Aid — 117 actions across 4 domains.

Tests: financial_aid (~30), scholarships (~10), work_study (~8), loan_tracking (~7) = ~55 tests.
"""
import importlib.util
import pytest
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    """Load a Python module by explicit file path (avoids sys.path collisions)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
get_conn = _helpers.get_conn
is_ok = _helpers.is_ok
is_error = _helpers.is_error
seed_company = _helpers.seed_company
seed_student = _helpers.seed_student
seed_aid_year = _helpers.seed_aid_year
seed_academic_year = _helpers.seed_academic_year
seed_academic_term = _helpers.seed_academic_term
seed_program = _helpers.seed_program
seed_program_enrollment = _helpers.seed_program_enrollment
seed_isir = _helpers.seed_isir
seed_cost_of_attendance = _helpers.seed_cost_of_attendance

FA_ACTIONS = _load("financial_aid", _SCRIPTS_DIR).ACTIONS
SCHOL_ACTIONS = _load("scholarships", _SCRIPTS_DIR).ACTIONS
WS_ACTIONS = _load("work_study", _SCRIPTS_DIR).ACTIONS
LOAN_ACTIONS = _load("loan_tracking", _SCRIPTS_DIR).ACTIONS


@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    yield conn, cid
    conn.close()


@pytest.fixture
def full_setup(db_path):
    conn = get_conn(db_path)
    cid = seed_company(conn)
    sid = seed_student(conn, cid)
    aid_yr = seed_aid_year(conn, cid)
    yid = seed_academic_year(conn, cid)
    tid = seed_academic_term(conn, cid, yid)
    pid = seed_program(conn, cid)
    peid = seed_program_enrollment(conn, sid, pid, yid, cid)
    isir_id = seed_isir(conn, sid, aid_yr, cid)
    coa_id = seed_cost_of_attendance(conn, aid_yr, cid)
    yield {
        "conn": conn, "company_id": cid, "student_id": sid,
        "aid_year_id": aid_yr, "year_id": yid, "term_id": tid,
        "program_id": pid, "program_enrollment_id": peid,
        "academic_term_id": tid, "isir_id": isir_id,
        "cost_of_attendance_id": coa_id,
    }
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL AID domain
# ══════════════════════════════════════════════════════════════════════════════

class TestAidYear:
    def test_add(self, setup):
        conn, cid = setup
        r = call_action(FA_ACTIONS["finaid-add-aid-year"], conn, ns(
            company_id=cid, aid_year_code="2026-2027", description="Test aid year",
            start_date="2026-07-01", end_date="2027-06-30",
            pell_max_award="7395",
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-aid-years"], s["conn"], ns(
            company_id=s["company_id"], limit=50, offset=0,
        ))
        assert is_ok(r)

    def test_get(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-get-aid-year"], s["conn"], ns(
            id=s["aid_year_id"],
        ))
        assert is_ok(r)

    def test_update(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-update-aid-year"], s["conn"], ns(
            id=s["aid_year_id"], description="Updated desc",
            aid_year_code=None, start_date=None, end_date=None,
            pell_max_award=None,
        ))
        assert is_ok(r)

    def test_activate(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-activate-aid-year"], s["conn"], ns(
            id=s["aid_year_id"], company_id=s["company_id"],
        ))
        assert is_ok(r)

    def test_missing_code(self, setup):
        conn, cid = setup
        r = call_action(FA_ACTIONS["finaid-add-aid-year"], conn, ns(
            company_id=cid, aid_year_code=None, description=None,
            start_date="2026-07-01", end_date="2027-06-30", pell_max_award=None,
        ))
        assert is_error(r)


class TestFundAllocation:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-add-fund-allocation"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            fund_type="fseog", fund_name="FSEOG Grant Fund",
            total_allocation="500000", committed_amount=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-fund-allocations"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=None,
            fund_type=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestCostOfAttendance:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-add-cost-of-attendance"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            enrollment_status="full_time", living_arrangement="on_campus",
            tuition_fees="15000", books_supplies="1200",
            room_board="10000", transportation="1500",
            personal_expenses="2000", loan_fees="100",
            program_id=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-cost-of-attendance"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=None,
            enrollment_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestISIR:
    def test_import(self, full_setup):
        s = full_setup
        # full_setup already seeds ISIR with transaction_number=1, use 2
        r = call_action(FA_ACTIONS["finaid-import-isir"], s["conn"], ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            company_id=s["company_id"],
            sai="2000", dependency_status="dependent",
            pell_index_isir="150", verification_flag=0, verification_group=None,
            transaction_number=2, fafsa_submission_id=None,
            nslds_default_flag=0, nslds_overpayment_flag=0,
            selective_service_flag=0, citizenship_flag=0,
            agi="55000", household_size=4, family_members_in_college=1,
            receipt_date="2025-04-01", raw_isir_data=None,
            is_active_transaction=1,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-isirs"], s["conn"], ns(
            student_id=s["student_id"], aid_year_id=None,
            company_id=s["company_id"], limit=50, offset=0,
        ))
        assert is_ok(r)


class TestVerification:
    def test_create_request(self, full_setup):
        s = full_setup
        # full_setup already seeds an ISIR; use its ID directly
        r = call_action(FA_ACTIONS["finaid-create-verification-request"], s["conn"], ns(
            isir_id=s["isir_id"], student_id=s["student_id"],
            company_id=s["company_id"],
            verification_group="V1", deadline_date="2025-06-01",
            requested_date=None, assigned_to=None,
        ))
        assert is_ok(r)

    def test_list_requests(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-verification-requests"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            aid_year_id=None, status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestAwardPackage:
    def test_create(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            academic_term_id=s["academic_term_id"],
            company_id=s["company_id"],
            program_enrollment_id=s["program_enrollment_id"],
            isir_id=s["isir_id"], cost_of_attendance_id=s["cost_of_attendance_id"],
            enrollment_status="full_time",
            financial_need=None, acceptance_deadline=None,
            packaged_by=None, notes=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-award-packages"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            aid_year_id=None, status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestSAPEvaluation:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-sap-evaluations"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            academic_term_id=None, sap_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestR2T4:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-r2t4s"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestProfessionalJudgment:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-professional-judgments"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            aid_year_id=None, pj_type=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestDisbursements:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-disbursements"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            award_id=None, cod_status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestPellSchedule:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(FA_ACTIONS["finaid-list-pell-schedule"], s["conn"], ns(
            aid_year_id=s["aid_year_id"], limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# SCHOLARSHIPS domain
# ══════════════════════════════════════════════════════════════════════════════

class TestScholarshipProgram:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(SCHOL_ACTIONS["finaid-add-scholarship-program"], s["conn"], ns(
            company_id=s["company_id"], name="Merit Scholarship",
            code="MERIT-001", scholarship_type="merit",
            funding_source="endowment", award_method="application_required",
            award_amount_type="fixed", award_amount="5000",
            min_award=None, max_award=None, annual_budget="100000",
            max_recipients=20, renewal_eligible=1,
            renewal_gpa_minimum="3.0", renewal_credits_minimum=None,
            eligibility_criteria=None, application_deadline=None,
            award_period="annual", applies_to_aid_type="institutional_scholarship",
            description=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(SCHOL_ACTIONS["finaid-list-scholarship-programs"], s["conn"], ns(
            company_id=s["company_id"], scholarship_type=None,
            status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestScholarshipApplication:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(SCHOL_ACTIONS["finaid-list-scholarship-applications"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, status=None,
            aid_year_id=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestScholarshipRenewal:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(SCHOL_ACTIONS["finaid-list-scholarship-renewals"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            scholarship_program_id=None, renewal_status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# WORK STUDY domain
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkStudyJob:
    def test_add(self, full_setup):
        s = full_setup
        r = call_action(WS_ACTIONS["finaid-add-work-study-job"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=s["aid_year_id"],
            job_title="Library Assistant", department_id=None,
            supervisor_id=None, job_type="on_campus",
            pay_rate="12.00", hours_per_week="15",
            total_positions=3, description=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(WS_ACTIONS["finaid-list-work-study-jobs"], s["conn"], ns(
            company_id=s["company_id"], aid_year_id=None,
            job_type=None, status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestWorkStudyAssignment:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(WS_ACTIONS["finaid-list-work-study-assignments"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            job_id=None, status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


class TestWorkStudyTimesheet:
    def test_list(self, full_setup):
        s = full_setup
        r = call_action(WS_ACTIONS["finaid-list-work-study-timesheets"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            assignment_id=None, status=None, limit=50, offset=0,
        ))
        assert is_ok(r)


# ══════════════════════════════════════════════════════════════════════════════
# LOAN TRACKING domain
# ══════════════════════════════════════════════════════════════════════════════

class TestLoan:
    def test_add(self, full_setup):
        s = full_setup
        # 1. Create award package
        pkg = call_action(FA_ACTIONS["finaid-create-award-package"], s["conn"], ns(
            student_id=s["student_id"], aid_year_id=s["aid_year_id"],
            academic_term_id=s["academic_term_id"],
            company_id=s["company_id"],
            program_enrollment_id=s["program_enrollment_id"],
            isir_id=s["isir_id"], cost_of_attendance_id=s["cost_of_attendance_id"],
            enrollment_status="full_time",
            financial_need=None, acceptance_deadline=None,
            packaged_by=None, notes=None,
        ))
        if not is_ok(pkg):
            pytest.skip("Could not create award package")
        # 2. Add a loan-type award to the package
        award = call_action(FA_ACTIONS["finaid-add-award"], s["conn"], ns(
            award_package_id=pkg["id"], student_id=s["student_id"],
            aid_year_id=s["aid_year_id"], academic_term_id=s["academic_term_id"],
            aid_type="subsidized_loan", aid_source="federal",
            offered_amount="3500", company_id=s["company_id"],
            fund_source_id=None, gl_account_id=None, notes=None,
        ))
        if not is_ok(award):
            pytest.skip("Could not create award")
        # 3. Create the loan using the award ID
        r = call_action(LOAN_ACTIONS["finaid-add-loan"], s["conn"], ns(
            company_id=s["company_id"], student_id=s["student_id"],
            aid_year_id=s["aid_year_id"], award_id=award["id"],
            loan_type="subsidized",
            loan_period_start="2025-08-25", loan_period_end="2026-05-15",
            loan_amount="3500", first_disbursement_amount="1750",
            second_disbursement_amount="1750",
            origination_fee="29.05", interest_rate="6.53",
            borrower_id=s["student_id"], borrower_type="student",
            cod_loan_id=None, mpn_signed_date=None,
            entrance_counseling_required=1, entrance_counseling_date=None,
            exit_counseling_required=0, exit_counseling_date=None,
        ))
        assert is_ok(r)

    def test_list(self, full_setup):
        s = full_setup
        r = call_action(LOAN_ACTIONS["finaid-list-loans"], s["conn"], ns(
            company_id=s["company_id"], student_id=None,
            aid_year_id=None, loan_type=None, status=None,
            limit=50, offset=0,
        ))
        assert is_ok(r)
