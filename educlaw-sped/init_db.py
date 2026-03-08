#!/usr/bin/env python3
"""EduClaw SPED — Special Education module schema.

Tables: 4 (sped_iep, sped_iep_goal, sped_service, sped_service_log)
Indexes: 12

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
Run: python3 init_db.py [db_path]
"""
import os
import sqlite3
import sys


DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/erpclaw/data.sqlite")

REQUIRED_FOUNDATION = ["company", "naming_series", "audit_log"]


def create_sped_tables(db_path=None):
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")

    # Verify foundation exists
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    for t in REQUIRED_FOUNDATION:
        if t not in tables:
            print(f"ERROR: Foundation table '{t}' not found. Run erpclaw-setup first.")
            conn.close()
            sys.exit(1)

    conn.executescript("""
    -- ==========================================================
    -- EduClaw SPED Tables
    -- ==========================================================

    -- sped_iep: Individualized Education Program
    CREATE TABLE IF NOT EXISTS sped_iep (
        id TEXT PRIMARY KEY,
        naming_series TEXT NOT NULL DEFAULT '',
        student_id TEXT NOT NULL DEFAULT '',
        iep_date TEXT NOT NULL DEFAULT '',
        review_date TEXT NOT NULL DEFAULT '',
        annual_review_date TEXT NOT NULL DEFAULT '',
        disability_category TEXT NOT NULL DEFAULT '',
        placement TEXT NOT NULL DEFAULT '',
        lre_percentage TEXT NOT NULL DEFAULT '',
        case_manager TEXT NOT NULL DEFAULT '',
        meeting_participants TEXT NOT NULL DEFAULT '[]',
        notes TEXT NOT NULL DEFAULT '',
        iep_status TEXT NOT NULL DEFAULT 'draft'
            CHECK(iep_status IN ('draft','active','expired','archived')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_by TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_sped_iep_student ON sped_iep(student_id);
    CREATE INDEX IF NOT EXISTS idx_sped_iep_status ON sped_iep(iep_status);
    CREATE INDEX IF NOT EXISTS idx_sped_iep_company ON sped_iep(company_id);
    CREATE INDEX IF NOT EXISTS idx_sped_iep_annual_review ON sped_iep(annual_review_date);

    -- sped_iep_goal: Measurable objectives within an IEP
    CREATE TABLE IF NOT EXISTS sped_iep_goal (
        id TEXT PRIMARY KEY,
        iep_id TEXT NOT NULL DEFAULT '' REFERENCES sped_iep(id) ON DELETE CASCADE,
        goal_area TEXT NOT NULL DEFAULT '',
        goal_description TEXT NOT NULL DEFAULT '',
        baseline TEXT NOT NULL DEFAULT '',
        target TEXT NOT NULL DEFAULT '',
        current_progress TEXT NOT NULL DEFAULT '',
        measurement_method TEXT NOT NULL DEFAULT '',
        goal_status TEXT NOT NULL DEFAULT 'in_progress'
            CHECK(goal_status IN ('in_progress','met','not_met','discontinued')),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_by TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_sped_iep_goal_iep ON sped_iep_goal(iep_id);

    -- sped_service: Service allocations (speech therapy, OT, PT, etc.)
    CREATE TABLE IF NOT EXISTS sped_service (
        id TEXT PRIMARY KEY,
        naming_series TEXT NOT NULL DEFAULT '',
        student_id TEXT NOT NULL DEFAULT '',
        iep_id TEXT NOT NULL DEFAULT '' REFERENCES sped_iep(id) ON DELETE RESTRICT,
        service_type TEXT NOT NULL DEFAULT ''
            CHECK(service_type IN ('speech_therapy','occupational_therapy','physical_therapy',
                                   'counseling','behavioral','aide','transport','other')),
        provider TEXT NOT NULL DEFAULT '',
        frequency_minutes_per_week INTEGER NOT NULL DEFAULT 0,
        setting TEXT NOT NULL DEFAULT '',
        start_date TEXT NOT NULL DEFAULT '',
        end_date TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        service_status TEXT NOT NULL DEFAULT 'active'
            CHECK(service_status IN ('active','paused','completed','cancelled')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_by TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_sped_service_student ON sped_service(student_id);
    CREATE INDEX IF NOT EXISTS idx_sped_service_iep ON sped_service(iep_id);
    CREATE INDEX IF NOT EXISTS idx_sped_service_type ON sped_service(service_type);
    CREATE INDEX IF NOT EXISTS idx_sped_service_company ON sped_service(company_id);

    -- sped_service_log: Individual session records
    CREATE TABLE IF NOT EXISTS sped_service_log (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL DEFAULT '' REFERENCES sped_service(id) ON DELETE RESTRICT,
        session_date TEXT NOT NULL DEFAULT '',
        duration_minutes INTEGER NOT NULL DEFAULT 0,
        provider TEXT NOT NULL DEFAULT '',
        session_notes TEXT NOT NULL DEFAULT '',
        is_makeup_session INTEGER NOT NULL DEFAULT 0,
        was_absent INTEGER NOT NULL DEFAULT 0,
        absence_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        created_by TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_sped_service_log_service ON sped_service_log(service_id);
    CREATE INDEX IF NOT EXISTS idx_sped_service_log_date ON sped_service_log(session_date);
    """)

    conn.commit()
    conn.close()
    print(f"[educlaw-sped] Created 4 tables, 12 indexes in {db_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    create_sped_tables(path)
