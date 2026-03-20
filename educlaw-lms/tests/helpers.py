"""Shared helper functions for EduClaw LMS Integration tests.

Provides:
  - DB connection helpers
  - Seed functions for all entities
  - call_action() test runner
  - ns() namespace builder
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
    """Load and execute init_db.py against db_path."""
    spec = importlib.util.spec_from_file_location("init_db_lms", INIT_DB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_educlaw_lms_tables(db_path)


def get_conn(db_path: str) -> sqlite3.Connection:
    """Return a sqlite3.Connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    setup_pragmas(conn)
    return conn


def bootstrap_foundation(db_path: str):
    """Create the minimal foundation tables required by educlaw-lms init_db."""
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
            skill TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            table_name TEXT NOT NULL DEFAULT '',
            record_id TEXT NOT NULL DEFAULT '',
            old_values TEXT NOT NULL DEFAULT '{}',
            new_values TEXT NOT NULL DEFAULT '{}',
            changed_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- department (referenced by educlaw_course)
        CREATE TABLE IF NOT EXISTS department (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- employee (referenced by educlaw_instructor)
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
    cid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO company (id, name, abbr) VALUES (?, ?, ?)",
        (cid, f"Test School {cid[:6]}", f"TS{cid[:4]}")
    )
    conn.commit()
    return cid


def seed_academic_year(conn, company_id) -> str:
    yid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_year
           (id, name, start_date, end_date, is_active, company_id, created_by)
           VALUES (?, ?, ?, ?, 1, ?, '')""",
        (yid, f"AY-{yid[:6]}", "2025-08-01", "2026-07-31", company_id)
    )
    conn.commit()
    return yid


def seed_academic_term(conn, company_id, year_id) -> str:
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


def seed_course(conn, company_id) -> str:
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_course
           (id, course_code, name, description, credit_hours,
            course_type, grade_level, max_enrollment, is_active, company_id, created_by)
           VALUES (?, ?, ?, '', '3', 'lecture', '10', 30, 1, ?, '')""",
        (cid, f"MATH-{cid[:6]}", "Algebra I", company_id)
    )
    conn.commit()
    return cid


def seed_section(conn, company_id, course_id, term_id, status="open") -> str:
    sid = str(uuid.uuid4())
    ns = f"SEC-{sid[:8]}"
    conn.execute(
        """INSERT INTO educlaw_section
           (id, naming_series, section_number, course_id, academic_term_id,
            days_of_week, start_time, end_time, max_enrollment, current_enrollment,
            status, company_id, created_by)
           VALUES (?, ?, ?, ?, ?, '[]', '08:00', '09:00', 30, 0, ?, ?, '')""",
        (sid, ns, "001", course_id, term_id, status, company_id)
    )
    conn.commit()
    return sid


def seed_grading_scale(conn, company_id) -> str:
    gsid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_grading_scale
           (id, name, description, is_default, company_id, created_by)
           VALUES (?, ?, '', 1, ?, '')""",
        (gsid, f"Scale-{gsid[:6]}", company_id)
    )
    conn.commit()
    return gsid


def seed_assessment_plan(conn, section_id, grading_scale_id, company_id) -> str:
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_assessment_plan
           (id, section_id, grading_scale_id, company_id, created_by)
           VALUES (?, ?, ?, ?, '')""",
        (pid, section_id, grading_scale_id, company_id)
    )
    conn.commit()
    return pid


def seed_assessment_category(conn, plan_id) -> str:
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_assessment_category
           (id, assessment_plan_id, name, weight_percentage, sort_order, created_by)
           VALUES (?, ?, 'Homework', '50', 1, '')""",
        (cid, plan_id)
    )
    conn.commit()
    return cid


def seed_assessment(conn, plan_id, category_id, name="Quiz 1") -> str:
    aid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_assessment
           (id, assessment_plan_id, category_id, name, description,
            max_points, due_date, is_published, allows_extra_credit, sort_order,
            created_by)
           VALUES (?, ?, ?, ?, '', '100', '2025-10-01', 1, 0, 1, '')""",
        (aid, plan_id, category_id, name)
    )
    conn.commit()
    return aid


def seed_lms_connection(conn, company_id, lms_type="oneroster_csv",
                         has_dpa=1, status="active") -> str:
    lid = str(uuid.uuid4())
    ns_val = f"LMS-{lid[:6]}"
    conn.execute(
        """INSERT INTO educlaw_lms_connection
           (id, naming_series, display_name, lms_type, endpoint_url,
            client_id, client_secret_encrypted, site_token_encrypted,
            google_credentials_encrypted, grade_direction, auto_push_assignments,
            has_dpa_signed, dpa_signed_date, is_coppa_verified, coppa_cert_url,
            allowed_data_fields, default_course_prefix, status,
            company_id, created_by)
           VALUES (?, ?, ?, ?, '', '', '', '', '', 'lms_to_sis', 0,
                   ?, '2025-01-01', 0, '', '[]', '', ?, ?, '')""",
        (lid, ns_val, "Test LMS", lms_type, has_dpa, status, company_id)
    )
    conn.commit()
    return lid


def seed_course_mapping(conn, lms_conn_id, section_id) -> str:
    mid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_lms_course_mapping
           (id, lms_connection_id, section_id, lms_course_id, lms_course_url,
            lms_term_id, sync_status, last_synced_at, created_by)
           VALUES (?, ?, ?, ?, '', '', 'synced', ?, '')""",
        (mid, lms_conn_id, section_id, f"lms_course_{section_id[:8]}", _now())
    )
    conn.commit()
    return mid


def seed_student(conn, company_id) -> str:
    sid = str(uuid.uuid4())
    ns_val = f"STU-{sid[:8]}"
    conn.execute(
        """INSERT INTO educlaw_student
           (id, naming_series, first_name, middle_name, last_name, full_name,
            date_of_birth, email, phone, address, emergency_contact,
            grade_level, cohort_year, total_credits_earned,
            cumulative_gpa, status, company_id, created_by)
           VALUES (?, ?, 'Test', '', 'Student', 'Test Student',
                   '2010-01-01', 'test@school.edu', '', '{}', '{}',
                   '10', 2025, '0', '', 'active', ?, '')""",
        (sid, ns_val, company_id)
    )
    conn.commit()
    return sid


def seed_enrollment(conn, student_id, section_id, company_id) -> str:
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_course_enrollment
           (id, student_id, section_id, enrollment_date, enrollment_status,
            drop_date, drop_reason, final_letter_grade, final_grade_points,
            final_percentage, grade_submitted_by, grade_submitted_at,
            is_grade_submitted, is_repeat, grade_type, company_id, created_by)
           VALUES (?, ?, ?, '2025-08-25', 'enrolled',
                   '', '', '', '0', '0', '', '', 0, 0, 'letter', ?, '')""",
        (eid, student_id, section_id, company_id)
    )
    conn.commit()
    return eid


# ──────────────────────────────────────────────────────────────────────────────
# Test action runner
# ──────────────────────────────────────────────────────────────────────────────

def call_action(fn, conn, args) -> dict:
    """Call an action function (which calls ok()/err() → sys.exit()),
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
    """Build an argparse.Namespace from keyword args."""
    return argparse.Namespace(**kwargs)
