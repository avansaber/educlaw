"""Shared helper functions for EduClaw K-12 unit tests.

Provides:
  - DB bootstrap and connection helpers
  - Seed functions for all prerequisite entities
  - call_action() test runner (captures ok()/err() stdout + SystemExit)
  - ns() namespace builder for argparse args
"""
import importlib.util
import io
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
INIT_DB_PATH = os.path.join(REPO_ROOT, "init_db.py")

# Make scripts importable
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Make erpclaw_lib importable
ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)

from erpclaw_lib.db import setup_pragmas


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────

def run_init_db(db_path: str):
    """Load and execute init_db.py's create_educlaw_k12_tables against db_path."""
    spec = importlib.util.spec_from_file_location("init_db_k12", INIT_DB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_educlaw_k12_tables(db_path)


def get_conn(db_path: str) -> sqlite3.Connection:
    """Return a sqlite3.Connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    setup_pragmas(conn)
    return conn


def bootstrap_foundation(db_path: str):
    """Create the minimal foundation tables required by educlaw-k12 init_db.

    These are erpclaw-setup tables that must exist before init_db runs.
    """
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS company (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            abbr TEXT NOT NULL UNIQUE,
            default_currency TEXT NOT NULL DEFAULT 'USD',
            country TEXT NOT NULL DEFAULT 'United States',
            tax_id TEXT,
            default_receivable_account_id TEXT,
            default_payable_account_id TEXT,
            default_income_account_id TEXT,
            default_expense_account_id TEXT,
            default_cost_center_id TEXT,
            default_warehouse_id TEXT,
            default_bank_account_id TEXT,
            default_cash_account_id TEXT,
            round_off_account_id TEXT,
            exchange_gain_loss_account_id TEXT,
            stock_received_not_billed_account_id TEXT,
            stock_adjustment_account_id TEXT,
            depreciation_expense_account_id TEXT,
            accumulated_depreciation_account_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS naming_series (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            prefix TEXT NOT NULL,
            current_value INTEGER NOT NULL DEFAULT 0,
            company_id TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            UNIQUE(entity_type, prefix, company_id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            timestamp TEXT DEFAULT (datetime('now')),
            user_id TEXT,
            skill TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            entity_type TEXT,
            entity_id TEXT,
            old_values TEXT,
            new_values TEXT,
            description TEXT
        );

        -- department (referenced by educlaw_course)
        CREATE TABLE IF NOT EXISTS department (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- employee (referenced by educlaw_instructor, IEP team members)
        CREATE TABLE IF NOT EXISTS employee (
            id TEXT PRIMARY KEY,
            naming_series TEXT NOT NULL UNIQUE DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            work_email TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT ''
        );

        -- customer (referenced by educlaw_student, educlaw_guardian)
        CREATE TABLE IF NOT EXISTS customer (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Seed helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_company(conn) -> str:
    """Insert a test company and return its ID."""
    cid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO company (id, name, abbr) VALUES (?, ?, ?)",
        (cid, f"Test School {cid[:6]}", f"TS{cid[:4]}")
    )
    conn.commit()
    return cid


def seed_academic_year(conn, company_id: str) -> str:
    """Insert a test academic year and return its ID."""
    yid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_year
           (id, name, start_date, end_date, is_active, company_id, created_by)
           VALUES (?, ?, ?, ?, 1, ?, '')""",
        (yid, f"AY-{yid[:6]}", "2025-08-01", "2026-07-31", company_id)
    )
    conn.commit()
    return yid


def seed_academic_term(conn, company_id: str, year_id: str) -> str:
    """Insert a test academic term and return its ID."""
    tid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_term
           (id, name, term_type, academic_year_id, start_date, end_date,
            enrollment_start_date, enrollment_end_date,
            grade_submission_deadline, status, company_id, created_by)
           VALUES (?, ?, 'semester', ?, ?, ?, ?, ?, ?, 'active', ?, '')""",
        (tid, f"Fall {tid[:6]}", year_id,
         "2025-08-25", "2025-12-20",
         "2025-07-01", "2025-08-20",
         "2026-01-10", company_id)
    )
    conn.commit()
    return tid


def seed_student(conn, company_id: str, grade_level: str = "10",
                 dob: str = "2010-01-01") -> str:
    """Insert a test student and return its ID."""
    sid = str(uuid.uuid4())
    ns_val = f"STU-{sid[:8]}"
    conn.execute(
        """INSERT INTO educlaw_student
           (id, naming_series, first_name, middle_name, last_name, full_name,
            date_of_birth, email, phone, address, emergency_contact,
            grade_level, cohort_year, total_credits_earned,
            cumulative_gpa, status, company_id, created_by)
           VALUES (?, ?, 'Test', '', 'Student', 'Test Student',
                   ?, 'test@school.edu', '', '{}', '{}',
                   ?, 2025, '0', '3.5', 'active', ?, '')""",
        (sid, ns_val, dob, grade_level, company_id)
    )
    conn.commit()
    return sid


def seed_guardian(conn, company_id: str) -> str:
    """Insert a test guardian and return its ID."""
    gid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_guardian
           (id, first_name, last_name, full_name, relationship, email, phone,
            alternate_phone, address, company_id, created_by)
           VALUES (?, 'Test', 'Parent', 'Test Parent', 'mother', 'parent@email.com', '',
                   '', '{}', ?, '')""",
        (gid, company_id)
    )
    conn.commit()
    return gid


def seed_student_guardian(conn, student_id: str, guardian_id: str,
                           relationship: str = "mother") -> str:
    """Insert a student-guardian link and return its ID."""
    sgid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_student_guardian
           (id, student_id, guardian_id, relationship, has_custody, can_pickup,
            receives_communications, is_primary_contact, is_emergency_contact, created_by)
           VALUES (?, ?, ?, ?, 1, 1, 1, 1, 1, '')""",
        (sgid, student_id, guardian_id, relationship)
    )
    conn.commit()
    return sgid


def seed_discipline_incident(conn, company_id: str, year_id: str,
                              naming_series: str = "DI-2025-00001") -> str:
    """Insert a discipline incident directly and return its ID."""
    iid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_discipline_incident
           (id, naming_series, incident_date, incident_time, location, location_detail,
            incident_type, severity, description, is_reported_to_law_enforcement,
            is_mandatory_report, mandatory_report_date, mandatory_report_agency,
            is_title_ix, incident_status, academic_year_id, academic_term_id,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, '2025-10-01', '', 'classroom', '', 'fighting', 'major',
                   'Test incident', 0, 0, '', '', 0, 'open', ?, NULL,
                   ?, ?, ?, '')""",
        (iid, naming_series, year_id, company_id, _now(), _now())
    )
    conn.commit()
    return iid


def seed_discipline_student(conn, incident_id: str, student_id: str,
                              role: str = "offender",
                              is_idea_eligible: int = 0) -> str:
    """Insert a discipline student record directly and return its ID."""
    dsid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_discipline_student
           (id, incident_id, student_id, role, is_idea_eligible,
            cumulative_suspension_days_ytd, mdr_required, notes, created_at, created_by)
           VALUES (?, ?, ?, ?, ?, '0', 0, '', ?, '')""",
        (dsid, incident_id, student_id, role, is_idea_eligible, _now())
    )
    conn.commit()
    return dsid


def seed_health_profile(conn, student_id: str, company_id: str) -> str:
    """Insert a health profile for a student and return its ID."""
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_health_profile
           (id, student_id, allergies, chronic_conditions, physician_name, physician_phone,
            physician_address, health_insurance_carrier, health_insurance_id, blood_type,
            height_cm, weight_kg, vision_screening_date, hearing_screening_date,
            dental_screening_date, activity_restriction, activity_restriction_notes,
            is_provisional_immunization, provisional_enrollment_end_date, is_mckinney_vento,
            emergency_instructions, profile_status, last_verified_date, last_verified_by,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, '[]', '[]', 'Dr. Smith', '', '', '', '', 'O+',
                   '', '', '', '', '', 'none', '', 0, '', 0, '',
                   'incomplete', '', '', ?, ?, ?, '')""",
        (pid, student_id, company_id, _now(), _now())
    )
    conn.commit()
    return pid


def seed_sped_referral(conn, student_id: str, company_id: str,
                        naming_series: str = "SPED-REF-00001",
                        status: str = "received") -> str:
    """Insert a SPED referral directly and return its ID."""
    rid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_sped_referral
           (id, naming_series, student_id, referral_date, referral_source,
            referral_reason, areas_of_concern, prior_interventions,
            referral_status, consent_request_date, consent_received_date,
            consent_denied_date, evaluation_deadline,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, '2025-09-01', 'teacher', 'Academic delays', '[]', '',
                   ?, '', '', '', '', ?, ?, ?, '')""",
        (rid, naming_series, student_id, status, company_id, _now(), _now())
    )
    conn.commit()
    return rid


def seed_sped_eligibility(conn, student_id: str, referral_id: str,
                           company_id: str) -> str:
    """Insert a SPED eligibility record and return its ID."""
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_sped_eligibility
           (id, student_id, referral_id, eligibility_meeting_date, is_eligible,
            disability_categories, primary_disability, iep_deadline,
            team_members_present, company_id, created_at, created_by)
           VALUES (?, ?, ?, '2025-10-15', 1, '["specific_learning_disability"]',
                   'specific_learning_disability', '2025-11-15', '[]',
                   ?, ?, '')""",
        (eid, student_id, referral_id, company_id, _now())
    )
    conn.commit()
    return eid


def seed_iep_draft(conn, student_id: str, eligibility_id: str,
                   company_id: str, naming_series: str = "IEP-2025-00001") -> str:
    """Insert a draft IEP directly and return its ID."""
    iid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_iep
           (id, naming_series, student_id, eligibility_id, iep_version,
            is_amendment, parent_iep_id, iep_meeting_date, iep_start_date,
            iep_end_date, annual_review_due_date, triennial_reevaluation_due_date,
            plaafp_academic, plaafp_functional, lre_percentage_general_ed,
            lre_justification, supplementary_aids, program_modifications,
            state_assessment_participation, state_assessment_accommodations,
            transition_plan_required, transition_postsecondary_goal,
            transition_employment_goal, transition_independent_living_goal,
            progress_report_frequency, iep_status, parent_consent_date,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, 1, 0, NULL, '2025-10-15', '2025-11-01',
                   '2026-10-31', '2026-10-31', '',
                   'Academic performance at grade level', 'Attention challenges', '80',
                   'Appropriate LRE', '', '', 'with_accommodations', '',
                   0, '', '', '', 'quarterly', 'draft', '',
                   ?, ?, ?, '')""",
        (iid, naming_series, student_id, eligibility_id, company_id, _now(), _now())
    )
    conn.commit()
    return iid


def seed_iep_active(conn, student_id: str, eligibility_id: str,
                    company_id: str, naming_series: str = "IEP-2025-00001") -> str:
    """Insert an active IEP directly and return its ID."""
    iid = seed_iep_draft(conn, student_id, eligibility_id, company_id, naming_series)
    conn.execute(
        "UPDATE educlaw_k12_iep SET iep_status = 'active', parent_consent_date = '2025-11-01' WHERE id = ?",
        (iid,)
    )
    conn.commit()
    return iid


def seed_iep_goal(conn, iep_id: str, student_id: str) -> str:
    """Insert an IEP goal directly and return its ID.

    Args:
        iep_id: Parent IEP id.
        student_id: Owning student id (denormalised on the table).
    """
    gid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_iep_goal
           (id, iep_id, student_id, goal_area, goal_description,
            baseline_performance, target_performance,
            measurement_method, monitoring_frequency,
            responsible_provider, sort_order, is_met, created_at, created_by)
           VALUES (?, ?, ?, 'reading', 'Increase reading fluency to grade level',
                   'Reading at 3rd grade level', 'Reading at 5th grade level',
                   'probe', 'weekly', 'Reading Specialist',
                   1, 0, ?, '')""",
        (gid, iep_id, student_id, _now())
    )
    conn.commit()
    return gid


def seed_iep_service(conn, iep_id: str, student_id: str) -> str:
    """Insert an IEP service directly and return its ID.

    Args:
        iep_id: Parent IEP id.
        student_id: Owning student id (denormalised on the table).
    """
    sid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_iep_service
           (id, iep_id, student_id, service_type, service_setting,
            frequency_minutes_per_week,
            provider_name, provider_role, start_date, end_date,
            total_minutes_delivered, created_at, created_by)
           VALUES (?, ?, ?, 'special_education_instruction', 'resource_room', 150,
                   'Mr. Jones', 'Special Education Teacher',
                   '2025-11-01', '2026-10-31', 0,
                   ?, '')""",
        (sid, iep_id, student_id, _now())
    )
    conn.commit()
    return sid


def seed_promotion_review(conn, student_id: str, year_id: str,
                           company_id: str) -> str:
    """Insert a promotion review directly and return its ID."""
    rid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_promotion_review
           (id, student_id, academic_year_id, grade_level, review_date,
            gpa_ytd, attendance_rate_ytd, failing_subjects, discipline_incident_count,
            teacher_recommendation, teacher_rationale, counselor_recommendation,
            counselor_notes, is_idea_eligible, prior_retention_count,
            interventions_tried, review_status, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, '10', '2026-05-15', '3.5', '96.2', '[]', 0,
                   'promote', '', 'promote', '', 0, 0, '[]', 'pending',
                   ?, ?, ?, '')""",
        (rid, student_id, year_id, company_id, _now(), _now())
    )
    conn.commit()
    return rid


def seed_promotion_decision(conn, review_id: str, student_id: str,
                             year_id: str, company_id: str,
                             decision: str = "promote") -> str:
    """Insert a promotion decision directly and return its ID."""
    did = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_k12_promotion_decision
           (id, promotion_review_id, student_id, academic_year_id, decision,
            decision_date, decided_by, rationale, team_members, conditions,
            parent_notified_date, parent_notified_by, notification_method,
            appeal_deadline, is_appealed, appeal_filed_date, appeal_outcome,
            appeal_decision_date, next_grade_level, company_id, created_at, created_by)
           VALUES (?, ?, ?, ?, ?, '2026-05-20', 'Principal', 'On track', '[]', '',
                   '', '', 'letter', '', 0, '', 'not_applicable', '', '11',
                   ?, ?, '')""",
        (did, review_id, student_id, year_id, decision, company_id, _now())
    )
    # Update review status to decided
    conn.execute(
        "UPDATE educlaw_k12_promotion_review SET review_status = 'decided' WHERE id = ?",
        (review_id,)
    )
    conn.commit()
    return did


# ──────────────────────────────────────────────────────────────────────────────
# Test action runner
# ──────────────────────────────────────────────────────────────────────────────

def call_action(fn, conn, args) -> dict:
    """Call a domain action function (which calls ok()/err() → sys.exit()),
    capture its stdout output, and return the parsed JSON response dict."""
    buf = io.StringIO()

    def _fake_exit(code=0):
        raise SystemExit(code)

    try:
        with patch("sys.stdout", buf), patch("sys.exit", side_effect=_fake_exit):
            fn(conn, args)
    except SystemExit:
        pass

    output = buf.getvalue().strip()
    if not output:
        return {"status": "error", "message": "no output captured"}
    return json.loads(output)


import argparse


def ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace from keyword args (mimics argparse output)."""
    return argparse.Namespace(**kwargs)
