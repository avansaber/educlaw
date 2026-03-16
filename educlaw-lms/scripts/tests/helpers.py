"""Shared helper functions for EduClaw LMS unit tests."""
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

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(TESTS_DIR)           # scripts/
ROOT_DIR = os.path.dirname(MODULE_DIR)             # educlaw-lms/
PARENT_DIR = os.path.dirname(ROOT_DIR)             # src/educlaw/
SRC_DIR = os.path.dirname(PARENT_DIR)              # src/
VERTICAL_INIT_PATH = os.path.join(ROOT_DIR, "init_db.py")

if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)

# LMS module needs an encryption key for credential storage
os.environ.setdefault("EDUCLAW_LMS_ENCRYPTION_KEY", "test-key-for-unit-tests")


class _ConnWrapper:
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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _ConnWrapper(conn)


def bootstrap_foundation(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS company (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, abbr TEXT NOT NULL UNIQUE,
            default_currency TEXT NOT NULL DEFAULT 'USD', country TEXT NOT NULL DEFAULT 'United States',
            tax_id TEXT, default_receivable_account_id TEXT, default_payable_account_id TEXT,
            default_income_account_id TEXT, default_expense_account_id TEXT,
            default_cost_center_id TEXT, default_warehouse_id TEXT,
            default_bank_account_id TEXT, default_cash_account_id TEXT,
            round_off_account_id TEXT, exchange_gain_loss_account_id TEXT,
            stock_received_not_billed_account_id TEXT, stock_adjustment_account_id TEXT,
            depreciation_expense_account_id TEXT, accumulated_depreciation_account_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS naming_series (
            id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, prefix TEXT NOT NULL,
            current_value INTEGER NOT NULL DEFAULT 0,
            company_id TEXT NOT NULL REFERENCES company(id) ON DELETE RESTRICT,
            UNIQUE(entity_type, prefix, company_id)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY, timestamp TEXT DEFAULT (datetime('now')),
            user_id TEXT, skill TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
            entity_type TEXT, entity_id TEXT, old_values TEXT, new_values TEXT, description TEXT
        );
        CREATE TABLE IF NOT EXISTS department (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
            company_id TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS employee (
            id TEXT PRIMARY KEY, naming_series TEXT NOT NULL UNIQUE DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
            work_email TEXT NOT NULL DEFAULT '',
            company_id TEXT REFERENCES company(id), created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')), created_by TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS customer (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
            company_id TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS account (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', account_type TEXT NOT NULL DEFAULT '',
            company_id TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def run_init_db(db_path: str):
    spec = importlib.util.spec_from_file_location("init_db_lms", VERTICAL_INIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_educlaw_lms_tables(db_path)


def init_all_tables(db_path: str):
    bootstrap_foundation(db_path)
    run_init_db(db_path)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_company(conn) -> str:
    cid = str(uuid.uuid4())
    conn.execute("INSERT INTO company (id, name, abbr) VALUES (?, ?, ?)",
                 (cid, f"Test Inst {cid[:6]}", f"TI{cid[:4]}"))
    conn.commit()
    return cid


def seed_student(conn, company_id: str) -> str:
    sid = str(uuid.uuid4())
    ns_val = f"STU-{sid[:8]}"
    conn.execute(
        """INSERT INTO educlaw_student
           (id, naming_series, first_name, last_name, full_name,
            date_of_birth, email, status, company_id, created_by)
           VALUES (?, ?, 'Test', 'Student', 'Test Student',
                   '2005-01-01', 'test@inst.edu', 'active', ?, '')""",
        (sid, ns_val, company_id))
    conn.commit()
    return sid


def seed_academic_year(conn, company_id: str) -> str:
    yid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_year
           (id, name, start_date, end_date, is_active, company_id, created_by)
           VALUES (?, 'AY-2025', '2025-08-01', '2026-07-31', 1, ?, '')""",
        (yid, company_id))
    conn.commit()
    return yid


def seed_academic_term(conn, company_id: str, year_id: str) -> str:
    tid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_academic_term
           (id, name, term_type, academic_year_id, start_date, end_date,
            enrollment_start_date, enrollment_end_date,
            grade_submission_deadline, status, company_id, created_by)
           VALUES (?, 'Fall 2025', 'semester', ?, '2025-08-25', '2025-12-20',
                   '2025-07-01', '2025-08-20', '2026-01-10', 'active', ?, '')""",
        (tid, year_id, company_id))
    conn.commit()
    return tid


def seed_course(conn, company_id: str) -> str:
    crs_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_course
           (id, course_code, code, name, is_active, company_id, created_by)
           VALUES (?, 'LMS101', 'LMS101', 'LMS Test Course', 1, ?, '')""",
        (crs_id, company_id))
    conn.commit()
    return crs_id


def seed_section(conn, company_id: str, course_id: str = None) -> str:
    if course_id is None:
        course_id = seed_course(conn, company_id)
    sec_id = str(uuid.uuid4())
    ns_val = f"SEC-{sec_id[:8]}"
    conn.execute(
        """INSERT INTO educlaw_section
           (id, naming_series, section_number, course_id,
            max_enrollment, current_enrollment,
            status, company_id, created_by)
           VALUES (?, ?, 'SEC-001', ?, 30, 0, 'open', ?, '')""",
        (sec_id, ns_val, course_id, company_id))
    conn.commit()
    return sec_id


def call_action(fn, conn, args) -> dict:
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
    return argparse.Namespace(**kwargs)

def is_ok(r): return r.get("status") == "ok"
def is_error(r): return r.get("status") == "error"
