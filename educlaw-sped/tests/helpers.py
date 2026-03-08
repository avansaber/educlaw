"""Shared helper functions for EduClaw SPED unit tests.

Provides:
  - DB bootstrap and connection helpers
  - Seed functions for prerequisite entities
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


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────

def run_init_db(db_path: str):
    """Load and execute init_db.py's create_sped_tables against db_path."""
    spec = importlib.util.spec_from_file_location("init_db_sped", INIT_DB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_sped_tables(db_path)


def get_conn(db_path: str) -> sqlite3.Connection:
    """Return a sqlite3.Connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def bootstrap_foundation(db_path: str):
    """Create the minimal foundation tables required by educlaw-sped init_db.

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
        (cid, f"Test SPED School {cid[:6]}", f"SP{cid[:4]}")
    )
    conn.commit()
    return cid


def seed_iep(conn, company_id: str, student_id: str = "student-1",
             iep_status: str = "draft",
             annual_review_date: str = "2026-10-15") -> str:
    """Insert a SPED IEP directly and return its ID."""
    iep_id = str(uuid.uuid4())
    ns = f"IEP-{iep_id[:8]}"
    conn.execute(
        """INSERT INTO sped_iep
           (id, naming_series, student_id, iep_date, review_date,
            annual_review_date, disability_category, placement,
            lre_percentage, case_manager, meeting_participants,
            notes, iep_status, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, '2025-10-15', '2026-04-15', ?, 'specific_learning_disability',
                   'general_education', '80', 'Ms. Johnson',
                   '["Ms. Johnson", "Dr. Smith"]', '', ?, ?, ?, ?, '')""",
        (iep_id, ns, student_id, annual_review_date, iep_status, company_id,
         _now(), _now())
    )
    conn.commit()
    return iep_id


def seed_iep_goal(conn, iep_id: str) -> str:
    """Insert an IEP goal directly and return its ID."""
    goal_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sped_iep_goal
           (id, iep_id, goal_area, goal_description, baseline, target,
            current_progress, measurement_method, goal_status, sort_order,
            created_at, updated_at, created_by)
           VALUES (?, ?, 'reading', 'Increase reading fluency', '60 wpm', '100 wpm',
                   '75 wpm', 'probe', 'in_progress', 1, ?, ?, '')""",
        (goal_id, iep_id, _now(), _now())
    )
    conn.commit()
    return goal_id


def seed_service(conn, company_id: str, iep_id: str,
                 student_id: str = "student-1",
                 service_type: str = "speech_therapy",
                 service_status: str = "active") -> str:
    """Insert a SPED service directly and return its ID."""
    svc_id = str(uuid.uuid4())
    ns = f"SVC-{svc_id[:8]}"
    conn.execute(
        """INSERT INTO sped_service
           (id, naming_series, student_id, iep_id, service_type, provider,
            frequency_minutes_per_week, setting, start_date, end_date,
            notes, service_status, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, 'Dr. Speech', 60, 'pull_out', '2025-11-01',
                   '2026-10-31', '', ?, ?, ?, ?, '')""",
        (svc_id, ns, student_id, iep_id, service_type, service_status,
         company_id, _now(), _now())
    )
    conn.commit()
    return svc_id


def seed_service_log(conn, service_id: str, session_date: str = "2025-11-05",
                     duration_minutes: int = 30, was_absent: int = 0) -> str:
    """Insert a service log directly and return its ID."""
    log_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sped_service_log
           (id, service_id, session_date, duration_minutes, provider,
            session_notes, is_makeup_session, was_absent, absence_reason,
            created_at, created_by)
           VALUES (?, ?, ?, ?, 'Dr. Speech', 'Good session', 0, ?, '', ?, '')""",
        (log_id, service_id, session_date, duration_minutes, was_absent, _now())
    )
    conn.commit()
    return log_id


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
