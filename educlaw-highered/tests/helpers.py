"""Shared helper functions for EduClaw Higher Education unit tests.

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
    """Load and execute init_db.py's create_educlaw_highered_tables against db_path."""
    spec = importlib.util.spec_from_file_location("init_db_highered", INIT_DB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_educlaw_highered_tables(db_path)


class _ConnWrapper:
    """Thin wrapper that allows setting arbitrary attributes (e.g. conn.company_id)
    on a sqlite3.Connection, which normally forbids __dict__ writes."""

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
    setup_pragmas(conn)
    return _ConnWrapper(conn)


def bootstrap_foundation(db_path: str):
    """Create the minimal foundation tables required by educlaw-highered init_db."""
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

        -- Stub tables referenced by educlaw base schema FKs
        CREATE TABLE IF NOT EXISTS employee (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS department (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS customer (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS account (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_id TEXT,
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
        (cid, f"Test Univ {cid[:6]}", f"TU{cid[:4]}")
    )
    conn.commit()
    return cid


def seed_degree_program(conn, company_id: str, name: str = "Computer Science",
                        degree_type: str = "bachelor", credits_required: int = 120) -> str:
    """Insert a test degree program and return its ID."""
    pid = str(uuid.uuid4())
    ns_val = f"HDEG-{pid[:8]}"
    conn.execute("""
        INSERT INTO highered_degree_program
        (id, naming_series, name, degree_type, department, credits_required,
         program_status, company_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'Engineering', ?, 'active', ?, ?, ?)
    """, (pid, ns_val, name, degree_type, credits_required, company_id, _now(), _now()))
    conn.commit()
    return pid


def seed_course(conn, company_id: str, code: str = "CS101",
                name: str = "Intro to CS", credits: int = 3) -> str:
    """Insert a test course and return its ID."""
    cid = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO educlaw_course
        (id, course_code, code, name, credits, credit_hours,
         department, prerequisites, description,
         is_active, company_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'Engineering', '', 'Test course', 1, ?, ?)
    """, (cid, code, code, name, credits, str(credits),
          company_id, _now()))
    conn.commit()
    return cid


def seed_section(conn, course_id: str, company_id: str,
                 term: str = "Fall", year: int = 2026,
                 capacity: int = 30) -> str:
    """Insert a test section and return its ID."""
    sid = str(uuid.uuid4())
    ns_val = f"SEC-{sid[:8]}"
    conn.execute("""
        INSERT INTO educlaw_section
        (id, naming_series, course_id, term, year, instructor, capacity,
         max_enrollment, enrolled, current_enrollment,
         schedule, location, section_status, status,
         company_id, created_at)
        VALUES (?, ?, ?, ?, ?, 'Dr. Smith', ?, ?, 0, 0,
                'MWF 10:00', 'Room 101', 'open', 'open', ?, ?)
    """, (sid, ns_val, course_id, term, year, capacity, capacity,
          company_id, _now()))
    conn.commit()
    return sid


def seed_student_record(conn, company_id: str, program_id: str,
                        name: str = "Test Student",
                        gpa: str = "3.50") -> str:
    """Insert a test student record and return its student_id."""
    rid = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    ns_val = f"HSTU-{rid[:8]}"
    conn.execute("""
        INSERT INTO educlaw_student
        (id, naming_series, student_id, name, email, program_id,
         enrollment_date, expected_graduation, total_credits, gpa,
         academic_standing, company_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'test@univ.edu', ?, '2024-08-01', '2028-05-15',
                0, ?, 'good', ?, ?, ?)
    """, (rid, ns_val, student_id, name, program_id, gpa, company_id, _now(), _now()))
    conn.commit()
    return student_id


def seed_enrollment(conn, student_id: str, section_id: str, company_id: str,
                    status: str = "enrolled", grade: str = "",
                    grade_points: str = "") -> str:
    """Insert a test enrollment and return its ID."""
    eid = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO educlaw_course_enrollment
        (id, student_id, section_id, enrollment_date, enrollment_status,
         grade, grade_points, company_id, created_at, updated_at)
        VALUES (?, ?, ?, '2026-08-25', ?, ?, ?, ?, ?, ?)
    """, (eid, student_id, section_id, status, grade, grade_points,
          company_id, _now(), _now()))
    if status == "enrolled":
        conn.execute(
            "UPDATE educlaw_section SET enrolled = enrolled + 1 WHERE id=?",
            (section_id,)
        )
    conn.commit()
    return eid


def seed_faculty(conn, company_id: str, name: str = "Dr. Johnson",
                 department: str = "Engineering",
                 rank: str = "professor") -> str:
    """Insert a test faculty member (educlaw_instructor) and return its ID."""
    fid = str(uuid.uuid4())
    ns_val = f"HFAC-{fid[:8]}"
    conn.execute("""
        INSERT INTO educlaw_instructor
        (id, naming_series, name, email, department, rank, tenure_status,
         hire_date, is_active, company_id, created_at, updated_at)
        VALUES (?, ?, ?, 'faculty@univ.edu', ?, ?, 'tenured',
                '2020-08-01', 1, ?, ?, ?)
    """, (fid, ns_val, name, department, rank, company_id, _now(), _now()))
    conn.commit()
    return fid


def seed_alumnus(conn, company_id: str, name: str = "Test Alum",
                 graduation_year: int = 2020) -> str:
    """Insert a test alumnus and return its ID."""
    aid = str(uuid.uuid4())
    ns_val = f"HALM-{aid[:8]}"
    conn.execute("""
        INSERT INTO highered_alumnus
        (id, naming_series, name, email, graduation_year, degree_program,
         employer, job_title, is_donor, total_giving, engagement_level,
         company_id, created_at, updated_at)
        VALUES (?, ?, ?, 'alum@email.com', ?, 'Computer Science',
                'Tech Corp', 'Engineer', 0, '0', 'low', ?, ?, ?)
    """, (aid, ns_val, name, graduation_year, company_id, _now(), _now()))
    conn.commit()
    return aid


def seed_application(conn, company_id: str, program_id: str = None,
                     name: str = "Test Applicant",
                     application_status: str = "submitted") -> str:
    """Insert a test application and return its ID."""
    app_id = str(uuid.uuid4())
    ns_val = f"HAPP-{app_id[:8]}"
    conn.execute("""
        INSERT INTO highered_application
        (id, naming_series, applicant_name, email, phone, program_id,
         application_date, intended_term, intended_year, gpa_incoming,
         test_scores, documents, application_status, notes,
         company_id, created_at, updated_at)
        VALUES (?, ?, ?, 'test@email.com', '555-1234', ?,
                '2026-01-15', 'Fall', 2026, '3.50',
                '{}', '[]', ?, '', ?, ?, ?)
    """, (app_id, ns_val, name, program_id or '', application_status,
          company_id, _now(), _now()))
    conn.commit()
    return app_id


def seed_aid_package(conn, student_id: str, company_id: str,
                     package_status: str = "offered",
                     total_aid: str = "15000.00") -> str:
    """Insert a test aid package and return its ID."""
    pid = str(uuid.uuid4())
    ns_val = f"HAID-{pid[:8]}"
    conn.execute("""
        INSERT INTO educlaw_scholarship
        (id, naming_series, student_id, aid_year, total_cost, efc, total_need,
         grants, scholarships, loans, work_study, total_aid,
         package_status, company_id, created_at, updated_at)
        VALUES (?, ?, ?, '2025-2026', '50000.00', '10000.00', '40000.00',
                '5000.00', '5000.00', '3000.00', '2000.00', ?,
                ?, ?, ?, ?)
    """, (pid, ns_val, student_id, total_aid, package_status, company_id, _now(), _now()))
    conn.commit()
    return pid


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


import argparse


def ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace from keyword args (mimics argparse output)."""
    return argparse.Namespace(**kwargs)
