"""Shared helper functions for EduClaw State Reporting unit tests."""
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

# Set ERPCLAW_FIELD_KEY before importing ed_fi module (needs it for encryption)
os.environ.setdefault("ERPCLAW_FIELD_KEY", "test-key-for-unit-tests")

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(TESTS_DIR)           # scripts/
ROOT_DIR = os.path.dirname(MODULE_DIR)             # educlaw-statereport/
PARENT_DIR = os.path.dirname(ROOT_DIR)             # src/educlaw/
SRC_DIR = os.path.dirname(PARENT_DIR)              # src/
VERTICAL_INIT_PATH = os.path.join(ROOT_DIR, "init_db.py")
K12_ROOT_DIR = os.path.join(PARENT_DIR, "educlaw-k12")
K12_INIT_PATH = os.path.join(K12_ROOT_DIR, "init_db.py")

if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)


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
    conn = sqlite3.connect(db_path, isolation_level=None)
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
    spec = importlib.util.spec_from_file_location("init_db_statereport", VERTICAL_INIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.create_educlaw_statereport_tables(db_path)


def bootstrap_discipline_tables(db_path: str):
    """Create discipline tables with the CRDC-aligned schema that statereport expects.

    The statereport discipline module writes to educlaw_k12_discipline_* tables
    with a different column set than the k12 module's version (CRDC-specific
    columns like school_year, campus_location, is_idea_student, mdr_outcome, etc.).
    We create the tables here with statereport's expected schema.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS educlaw_k12_discipline_incident (
            id TEXT PRIMARY KEY,
            naming_series TEXT NOT NULL UNIQUE DEFAULT '',
            company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
            school_year INTEGER NOT NULL DEFAULT 0,
            incident_date TEXT NOT NULL DEFAULT '',
            incident_time TEXT NOT NULL DEFAULT '',
            incident_type TEXT NOT NULL DEFAULT '',
            incident_description TEXT NOT NULL DEFAULT '',
            campus_location TEXT NOT NULL DEFAULT '',
            reported_by TEXT NOT NULL DEFAULT '',
            student_count_involved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS educlaw_k12_discipline_student (
            id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_k12_discipline_incident(id) ON DELETE RESTRICT,
            student_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_student(id) ON DELETE RESTRICT,
            role TEXT NOT NULL DEFAULT '',
            is_idea_student INTEGER NOT NULL DEFAULT 0,
            is_504_student INTEGER NOT NULL DEFAULT 0,
            company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS educlaw_k12_discipline_action (
            id TEXT PRIMARY KEY,
            discipline_student_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_k12_discipline_student(id) ON DELETE RESTRICT,
            incident_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_k12_discipline_incident(id) ON DELETE RESTRICT,
            student_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_student(id) ON DELETE RESTRICT,
            action_type TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            days_removed INTEGER NOT NULL DEFAULT 0,
            alternative_services_provided INTEGER NOT NULL DEFAULT 0,
            alternative_services_description TEXT NOT NULL DEFAULT '',
            mdr_required INTEGER NOT NULL DEFAULT 0,
            mdr_outcome TEXT NOT NULL DEFAULT '',
            mdr_date TEXT NOT NULL DEFAULT '',
            company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()


def init_all_tables(db_path: str):
    bootstrap_foundation(db_path)
    bootstrap_discipline_tables(db_path)  # CRDC-aligned discipline tables for statereport
    run_init_db(db_path)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_company(conn) -> str:
    cid = str(uuid.uuid4())
    conn.execute("INSERT INTO company (id, name, abbr) VALUES (?, ?, ?)",
                 (cid, f"Test District {cid[:6]}", f"TD{cid[:4]}"))
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
                   '2008-03-15', 'test@school.edu', 'active', ?, '')""",
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


_WINDOW_COUNTER = 0
_WINDOW_TYPES = [
    "fall_enrollment", "fall_sped", "winter_update", "spring_enrollment",
    "eoy_attendance", "eoy_discipline", "eoy_grades", "staffing", "crdc", "summer_correction",
]


def seed_collection_window(conn, company_id: str, academic_year_id: str = None) -> str:
    """Seed a collection window for testing. Uses unique window_type each call."""
    global _WINDOW_COUNTER
    wtype = _WINDOW_TYPES[_WINDOW_COUNTER % len(_WINDOW_TYPES)]
    _WINDOW_COUNTER += 1
    wid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_collection_window
           (id, name, state_code, window_type, school_year, academic_year_id,
            open_date, close_date, snapshot_date, status,
            required_data_categories, description, is_federal_required,
            edfi_config_id, company_id, created_at, updated_at, created_by)
           VALUES (?, ?, 'CA', ?, 2025, ?,
                   '2025-10-01', '2025-10-31', '2025-10-01', 'upcoming',
                   '[]', 'Test window', 0,
                   NULL, ?, ?, ?, '')""",
        (wid, f"Window {wtype} 2025", wtype, academic_year_id, company_id, _now(), _now()))
    conn.commit()
    return wid


def seed_edfi_config(conn, company_id: str) -> str:
    """Seed an Ed-Fi config for testing."""
    from erpclaw_lib.crypto import encrypt_field, derive_key
    _FIELD_PASSPHRASE = os.environ.get("ERPCLAW_FIELD_KEY", "test-key-for-unit-tests")
    _FIELD_SALT = b"educlaw_statereport_edfi_salt_v1"
    _FIELD_KEY = derive_key(_FIELD_PASSPHRASE, _FIELD_SALT)
    encrypted_secret = encrypt_field("test-secret", _FIELD_KEY)

    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_edfi_config
           (id, profile_name, state_code, school_year, ods_base_url,
            oauth_token_url, oauth_client_id, oauth_client_secret_encrypted,
            api_version, is_active, last_tested_at, last_token_at,
            company_id, created_at, updated_at, created_by)
           VALUES (?, 'Test Config', 'CA', 2025, 'https://edfi.test.edu/api',
                   'https://edfi.test.edu/oauth/token', 'test-client-id', ?,
                   '7', 1, '', '',
                   ?, ?, ?, '')""",
        (cid, encrypted_secret, company_id, _now(), _now()))
    conn.commit()
    return cid


def seed_supplement(conn, student_id: str, company_id: str) -> str:
    """Seed a student supplement record."""
    supp_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO sr_student_supplement
           (id, student_id, ssid, ssid_state_code, ssid_status,
            is_hispanic_latino, race_codes, race_federal_rollup,
            is_el, el_entry_date, home_language_code, native_language_code,
            english_proficiency_level, english_proficiency_instrument,
            el_exit_date, is_rfep, rfep_date,
            is_sped, is_504, sped_entry_date, sped_exit_date,
            is_economically_disadvantaged, lunch_program_status,
            is_migrant, is_homeless, homeless_primary_nighttime_residence,
            is_foster_care, is_military_connected, military_connection_type,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, 'SSN12345', 'CA', 'assigned',
                   0, '["WHITE"]', 'WHITE',
                   0, '', '', '',
                   '', '',
                   '', 0, '',
                   0, 0, '', '',
                   0, '',
                   0, 0, '',
                   0, 0, '',
                   ?, ?, ?, '')""",
        (supp_id, student_id, company_id, _now(), _now()))
    conn.commit()
    return supp_id


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
