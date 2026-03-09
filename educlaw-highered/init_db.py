#!/usr/bin/env python3
"""EduClaw Higher Education schema — 12 tables, ~80 columns, ~30 indexes.

6 tables (course, section, enrollment, student_record, aid_package, faculty)
have been merged into the educlaw base schema. This file creates only the
highered-specific tables that are NOT shared with other educlaw sub-verticals.

Domains: registrar (1 table), records (2 tables), finaid (1 table),
         alumni (3 tables), faculty (2 tables), admissions (2 tables),
         holds (1 table)

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
              educlaw base schema must also be present (provides educlaw_course,
              educlaw_section, educlaw_student, educlaw_course_enrollment,
              educlaw_scholarship, educlaw_instructor).
Owning skill: educlaw-highered
Run: python3 init_db.py [db_path]
"""
import os
import sqlite3
import sys


DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/erpclaw/data.sqlite")


def create_educlaw_highered_tables(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if "company" not in tables:
        print("ERROR: Foundation tables not found. Run erpclaw-setup first.")
        sys.exit(1)

    conn.executescript("""
    -- ==========================================================
    -- Registrar domain (1 table — degree programs)
    -- ==========================================================

    CREATE TABLE IF NOT EXISTS highered_degree_program (
        id TEXT PRIMARY KEY,
        naming_series TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        degree_type TEXT NOT NULL DEFAULT 'bachelor' CHECK(degree_type IN ('associate','bachelor','master','doctoral','certificate')),
        department TEXT NOT NULL DEFAULT '',
        credits_required INTEGER NOT NULL DEFAULT 0,
        program_status TEXT NOT NULL DEFAULT 'active' CHECK(program_status IN ('active','inactive','phasing_out')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hdp_company ON highered_degree_program(company_id);
    CREATE INDEX IF NOT EXISTS idx_hdp_dept ON highered_degree_program(department);

    -- ==========================================================
    -- Records domain (3 tables — holds, transcript, academic standing)
    -- ==========================================================

    CREATE TABLE IF NOT EXISTS highered_hold (
        id TEXT PRIMARY KEY,
        student_id TEXT NOT NULL DEFAULT '',
        hold_type TEXT NOT NULL DEFAULT 'administrative' CHECK(hold_type IN ('financial','academic','disciplinary','administrative')),
        reason TEXT NOT NULL DEFAULT '',
        placed_by TEXT NOT NULL DEFAULT '',
        placed_date TEXT NOT NULL DEFAULT '',
        removed_date TEXT NOT NULL DEFAULT '',
        hold_status TEXT NOT NULL DEFAULT 'active' CHECK(hold_status IN ('active','removed')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hh_student ON highered_hold(student_id);
    CREATE INDEX IF NOT EXISTS idx_hh_status ON highered_hold(hold_status);

    CREATE TABLE IF NOT EXISTS highered_transcript (
        id TEXT PRIMARY KEY,
        student_id TEXT NOT NULL DEFAULT '',
        section_id TEXT NOT NULL DEFAULT '',
        course_code TEXT NOT NULL DEFAULT '',
        course_name TEXT NOT NULL DEFAULT '',
        credits INTEGER NOT NULL DEFAULT 3,
        grade TEXT NOT NULL DEFAULT '',
        grade_points TEXT NOT NULL DEFAULT '0.00',
        term TEXT NOT NULL DEFAULT '',
        year INTEGER NOT NULL DEFAULT 0,
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_ht_student ON highered_transcript(student_id);
    CREATE INDEX IF NOT EXISTS idx_ht_company ON highered_transcript(company_id);

    CREATE TABLE IF NOT EXISTS highered_academic_standing (
        id TEXT PRIMARY KEY,
        student_id TEXT NOT NULL DEFAULT '',
        term TEXT NOT NULL DEFAULT '',
        year INTEGER NOT NULL DEFAULT 0,
        term_gpa TEXT NOT NULL DEFAULT '0.00',
        cumulative_gpa TEXT NOT NULL DEFAULT '0.00',
        total_credits INTEGER NOT NULL DEFAULT 0,
        standing TEXT NOT NULL DEFAULT 'good' CHECK(standing IN ('good','probation','suspension','dismissal','dean_list')),
        notes TEXT NOT NULL DEFAULT '',
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_has_student ON highered_academic_standing(student_id);
    CREATE INDEX IF NOT EXISTS idx_has_company ON highered_academic_standing(company_id);

    -- ==========================================================
    -- Financial Aid domain (1 table — disbursements)
    -- Note: aid_package fields merged into educlaw_scholarship
    -- ==========================================================

    CREATE TABLE IF NOT EXISTS highered_disbursement (
        id TEXT PRIMARY KEY,
        aid_package_id TEXT NOT NULL DEFAULT '',
        disbursement_date TEXT NOT NULL DEFAULT '',
        amount TEXT NOT NULL DEFAULT '0.00',
        aid_type TEXT NOT NULL DEFAULT 'grant' CHECK(aid_type IN ('grant','scholarship','loan','work_study')),
        fund_source TEXT NOT NULL DEFAULT '',
        disbursement_status TEXT NOT NULL DEFAULT 'pending' CHECK(disbursement_status IN ('pending','disbursed','returned')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hd_package ON highered_disbursement(aid_package_id);
    CREATE INDEX IF NOT EXISTS idx_hd_company ON highered_disbursement(company_id);

    -- ==========================================================
    -- Alumni domain (3 tables)
    -- ==========================================================

    CREATE TABLE IF NOT EXISTS highered_alumnus (
        id TEXT PRIMARY KEY,
        naming_series TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        graduation_year INTEGER NOT NULL DEFAULT 0,
        degree_program TEXT NOT NULL DEFAULT '',
        employer TEXT NOT NULL DEFAULT '',
        job_title TEXT NOT NULL DEFAULT '',
        is_donor INTEGER NOT NULL DEFAULT 0,
        total_giving TEXT NOT NULL DEFAULT '0',
        engagement_level TEXT NOT NULL DEFAULT 'inactive' CHECK(engagement_level IN ('inactive','low','medium','high','champion')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_ha_company ON highered_alumnus(company_id);

    CREATE TABLE IF NOT EXISTS highered_alumni_event (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL DEFAULT '',
        event_date TEXT NOT NULL DEFAULT '',
        event_type TEXT NOT NULL DEFAULT 'other' CHECK(event_type IN ('reunion','networking','fundraiser','career_fair','other')),
        attendees INTEGER NOT NULL DEFAULT 0,
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hae_company ON highered_alumni_event(company_id);

    CREATE TABLE IF NOT EXISTS highered_giving_record (
        id TEXT PRIMARY KEY,
        alumnus_id TEXT NOT NULL DEFAULT '' REFERENCES highered_alumnus(id) ON DELETE RESTRICT,
        amount TEXT NOT NULL DEFAULT '0.00',
        giving_date TEXT NOT NULL DEFAULT '',
        campaign TEXT NOT NULL DEFAULT '',
        gift_type TEXT NOT NULL DEFAULT 'cash' CHECK(gift_type IN ('cash','stock','planned','in_kind')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hgr_alumnus ON highered_giving_record(alumnus_id);
    CREATE INDEX IF NOT EXISTS idx_hgr_company ON highered_giving_record(company_id);

    -- ==========================================================
    -- Faculty domain (2 tables — course_assignment, research_grant)
    -- Note: highered_faculty merged into educlaw_instructor
    -- ==========================================================

    CREATE TABLE IF NOT EXISTS highered_course_assignment (
        id TEXT PRIMARY KEY,
        faculty_id TEXT NOT NULL DEFAULT '',
        section_id TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'primary' CHECK(role IN ('primary','secondary','ta')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hca_faculty ON highered_course_assignment(faculty_id);
    CREATE INDEX IF NOT EXISTS idx_hca_section ON highered_course_assignment(section_id);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_hca_fac_sec ON highered_course_assignment(faculty_id, section_id);

    CREATE TABLE IF NOT EXISTS highered_research_grant (
        id TEXT PRIMARY KEY,
        faculty_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        funding_agency TEXT NOT NULL DEFAULT '',
        amount TEXT NOT NULL DEFAULT '0.00',
        start_date TEXT NOT NULL DEFAULT '',
        end_date TEXT NOT NULL DEFAULT '',
        grant_status TEXT NOT NULL DEFAULT 'active' CHECK(grant_status IN ('proposed','active','completed','expired')),
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_hrg_faculty ON highered_research_grant(faculty_id);
    CREATE INDEX IF NOT EXISTS idx_hrg_company ON highered_research_grant(company_id);

    -- ==========================================================
    -- Admissions domain (2 tables)
    -- ==========================================================

    CREATE TABLE IF NOT EXISTS highered_application (
        id TEXT PRIMARY KEY,
        naming_series TEXT NOT NULL DEFAULT '',
        applicant_name TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        program_id TEXT DEFAULT '' REFERENCES highered_degree_program(id) ON DELETE RESTRICT,
        application_date TEXT NOT NULL DEFAULT '',
        intended_term TEXT NOT NULL DEFAULT '',
        intended_year INTEGER NOT NULL DEFAULT 0,
        gpa_incoming TEXT NOT NULL DEFAULT '0.00',
        test_scores TEXT NOT NULL DEFAULT '{}',
        documents TEXT NOT NULL DEFAULT '[]',
        application_status TEXT NOT NULL DEFAULT 'submitted'
            CHECK(application_status IN ('submitted','under_review','accepted','rejected','waitlisted','withdrawn')),
        notes TEXT NOT NULL DEFAULT '',
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_happ_company ON highered_application(company_id);
    CREATE INDEX IF NOT EXISTS idx_happ_program ON highered_application(program_id);

    CREATE TABLE IF NOT EXISTS highered_admission_decision (
        id TEXT PRIMARY KEY,
        application_id TEXT NOT NULL DEFAULT '' REFERENCES highered_application(id) ON DELETE RESTRICT,
        decision TEXT NOT NULL DEFAULT 'pending'
            CHECK(decision IN ('pending','admit','deny','waitlist','conditional_admit','defer')),
        decided_by TEXT NOT NULL DEFAULT '',
        decision_date TEXT NOT NULL DEFAULT '',
        conditions TEXT NOT NULL DEFAULT '',
        scholarship_offered TEXT NOT NULL DEFAULT '0.00',
        notes TEXT NOT NULL DEFAULT '',
        company_id TEXT NOT NULL DEFAULT '' REFERENCES company(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_had_app ON highered_admission_decision(application_id);
    CREATE INDEX IF NOT EXISTS idx_had_company ON highered_admission_decision(company_id);
    """)

    conn.commit()
    conn.close()
    print(f"educlaw-highered: 12 tables created in {db_path}")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    create_educlaw_highered_tables(db_path)
