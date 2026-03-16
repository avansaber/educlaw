"""Shared helper functions for EduClaw core unit tests.

Provides:
  - DB bootstrap and connection helpers
  - Seed functions for all prerequisite entities
  - call_action() test runner (captures ok()/err() stdout + SystemExit)
  - ns() namespace builder for argparse args
"""
import argparse
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
MODULE_DIR = os.path.dirname(TESTS_DIR)           # scripts/
ROOT_DIR = os.path.dirname(MODULE_DIR)             # educlaw/
PARENT_DIR = os.path.dirname(ROOT_DIR)             # src/educlaw/
SRC_DIR = os.path.dirname(PARENT_DIR)              # src/
SETUP_DIR = os.path.join(SRC_DIR, "erpclaw", "scripts", "erpclaw-setup")
INIT_SCHEMA_PATH = os.path.join(SETUP_DIR, "init_schema.py")
BASE_SCHEMA_PATH = os.path.join(PARENT_DIR, "educlaw_base_schema.py")
VERTICAL_INIT_PATH = os.path.join(ROOT_DIR, "init_db.py")

# Make scripts importable
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

# Make erpclaw_lib importable
ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────

class _ConnWrapper:
    """Thin wrapper that allows setting arbitrary attributes on a sqlite3.Connection."""

    def __init__(self, raw_conn):
        object.__setattr__(self, "_conn", raw_conn)
        object.__setattr__(self, "_extra", {})

    def __getattr__(self, name):
        extra = object.__getattribute__(self, "_extra")
        if name in extra:
            return extra[name]
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            object.__getattribute__(self, "_extra")[name] = value


def get_conn(db_path: str):
    """Return a wrapped sqlite3.Connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _ConnWrapper(conn)


def bootstrap_foundation(db_path: str):
    """Create the minimal foundation tables required by educlaw init_db."""
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

        CREATE TABLE IF NOT EXISTS department (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

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

        CREATE TABLE IF NOT EXISTS customer (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS account (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            account_type TEXT NOT NULL DEFAULT '',
            company_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sales_invoice (
            id TEXT PRIMARY KEY,
            naming_series TEXT NOT NULL DEFAULT '',
            customer_id TEXT,
            total_amount TEXT NOT NULL DEFAULT '0',
            status TEXT NOT NULL DEFAULT 'draft',
            company_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def run_init_db(db_path: str):
    """Load and execute init_db.py's create_educlaw_tables against db_path."""
    spec = importlib.util.spec_from_file_location("init_db_educlaw", VERTICAL_INIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_educlaw_tables(db_path)


def init_all_tables(db_path: str):
    """Bootstrap foundation + educlaw core tables."""
    bootstrap_foundation(db_path)
    run_init_db(db_path)


def load_db_query():
    """Load db_query.py and return its ACTIONS dict."""
    spec = importlib.util.spec_from_file_location(
        "db_query_educlaw",
        os.path.join(MODULE_DIR, "db_query.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ACTIONS


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


def seed_naming_series(conn, company_id: str, entity_type: str, prefix: str):
    """Insert a naming series entry."""
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO naming_series (id, entity_type, prefix, current_value, company_id) VALUES (?,?,?,0,?)",
        (sid, entity_type, prefix, company_id)
    )
    conn.commit()


def seed_employee(conn, company_id: str) -> str:
    """Insert a test employee and return its ID."""
    eid = str(uuid.uuid4())
    ns_val = f"EMP-{eid[:8]}"
    conn.execute(
        """INSERT INTO employee (id, naming_series, first_name, last_name, work_email, company_id)
           VALUES (?, ?, 'Test', 'Teacher', 'teacher@school.edu', ?)""",
        (eid, ns_val, company_id)
    )
    conn.commit()
    return eid


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


def seed_program(conn, company_id: str) -> str:
    """Insert a test program and return its ID."""
    pid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_program
           (id, code, name, program_type, total_credits_required, duration_years,
            is_active, company_id, created_by)
           VALUES (?, ?, 'Test Program', 'bachelor', '120', 4, 1, ?, '')""",
        (pid, f"PROG-{pid[:6]}", company_id)
    )
    conn.commit()
    return pid


def seed_course(conn, company_id: str, code: str = "MATH101") -> str:
    """Insert a test course and return its ID."""
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_course
           (id, course_code, name, credit_hours, is_active, company_id, created_by)
           VALUES (?, ?, 'Test Course', '3', 1, ?, '')""",
        (cid, code, company_id)
    )
    conn.commit()
    return cid


def seed_room(conn, company_id: str) -> str:
    """Insert a test room and return its ID."""
    rid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_room
           (id, room_number, building, capacity, room_type, is_active, company_id, created_by)
           VALUES (?, ?, 'Main', 30, 'classroom', 1, ?, '')""",
        (rid, f"R-{rid[:4]}", company_id)
    )
    conn.commit()
    return rid


def seed_instructor(conn, company_id: str, employee_id: str) -> str:
    """Insert a test instructor and return its ID."""
    iid = str(uuid.uuid4())
    ns_val = f"INST-{iid[:8]}"
    conn.execute(
        """INSERT INTO educlaw_instructor
           (id, naming_series, employee_id, is_active, company_id, created_by)
           VALUES (?, ?, ?, 1, ?, '')""",
        (iid, ns_val, employee_id, company_id)
    )
    conn.commit()
    return iid


def seed_section(conn, company_id: str, course_id: str, term_id: str,
                 instructor_id: str = None, room_id: str = None,
                 max_enrollment: int = 30, status: str = "open") -> str:
    """Insert a test section and return its ID."""
    sid = str(uuid.uuid4())
    ns_val = f"SEC-{sid[:8]}"
    conn.execute(
        """INSERT INTO educlaw_section
           (id, naming_series, section_number, course_id, academic_term_id,
            instructor_id, room_id, max_enrollment, current_enrollment,
            status, company_id, created_by)
           VALUES (?, ?, '001', ?, ?, ?, ?, ?, 0, ?, ?, '')""",
        (sid, ns_val, course_id, term_id, instructor_id, room_id,
         max_enrollment, status, company_id)
    )
    conn.commit()
    return sid


def seed_student(conn, company_id: str, dob: str = "2010-01-01",
                 grade_level: str = "10") -> str:
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
                   ?, 2025, '0', '', 'active', ?, '')""",
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
           VALUES (?, 'Test', 'Parent', 'Test Parent', 'mother', 'parent@email.com', '555-1234',
                   '', '{}', ?, '')""",
        (gid, company_id)
    )
    conn.commit()
    return gid


def seed_grading_scale(conn, company_id: str) -> str:
    """Insert a test grading scale and return its ID."""
    gsid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_grading_scale
           (id, name, description, is_default, company_id, created_by)
           VALUES (?, ?, 'Standard scale', 1, ?, '')""",
        (gsid, f"Standard {gsid[:4]}", company_id)
    )
    conn.commit()
    return gsid


def seed_fee_category(conn, company_id: str) -> str:
    """Insert a test fee category and return its ID."""
    fid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_fee_category
           (id, name, description, is_active, company_id, created_by)
           VALUES (?, 'Tuition', 'Tuition fees', 1, ?, '')""",
        (fid, company_id)
    )
    conn.commit()
    return fid


def seed_enrollment(conn, student_id: str, section_id: str,
                    company_id: str) -> str:
    """Insert a test course enrollment and return its ID."""
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_course_enrollment
           (id, student_id, section_id, enrollment_date, enrollment_status,
            company_id, created_by)
           VALUES (?, ?, ?, '2025-08-25', 'enrolled', ?, '')""",
        (eid, student_id, section_id, company_id)
    )
    conn.execute(
        "UPDATE educlaw_section SET current_enrollment = current_enrollment + 1 WHERE id = ?",
        (section_id,)
    )
    conn.commit()
    return eid


def build_env(db_path):
    """Set environment variables for test execution."""
    os.environ["ERPCLAW_DB_PATH"] = db_path


# ──────────────────────────────────────────────────────────────────────────────
# Test action runner
# ──────────────────────────────────────────────────────────────────────────────

def call_action(fn, conn, args) -> dict:
    """Call a domain action function (which calls ok()/err() -> sys.exit()),
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


def ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace from keyword args (mimics argparse output)."""
    return argparse.Namespace(**kwargs)


def is_ok(result: dict) -> bool:
    return result.get("status") == "ok"


def is_error(result: dict) -> bool:
    return result.get("status") == "error"
