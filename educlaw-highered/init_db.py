#!/usr/bin/env python3
"""EduClaw Higher Education schema — 10 tables, 102 columns, 19 indexes.

6 tables (course, section, enrollment, student_record, aid_package, faculty)
have been merged into the educlaw base schema. This file creates only the
highered-specific tables that are NOT shared with other educlaw sub-verticals.

Domains: registrar (1 table), records (1 table), finaid (1 table),
         alumni (3 tables), faculty (2 tables), admissions (2 tables)

The header used to read "12 tables, ~80 columns, ~30 indexes" and the domain
line still counted `highered_transcript` and `highered_academic_standing`, which
the 2026-06-01 P2 audit removed. Corrected here against what the file actually
creates (ADR-0034 phase 2 bulk-39).

Unlike its five sibling sub-verticals, this module does NOT call
`ensure_educlaw_base_tables`: none of its foreign keys point at an educlaw base
table, so it never needed the shared schema at install time. Its tests bootstrap
the base tables themselves. That absence is preserved, not corrected — adding the
call would create 32 tables this installer has never created.

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
              educlaw base schema must also be present (provides educlaw_course,
              educlaw_section, educlaw_student, educlaw_course_enrollment,
              educlaw_scholarship, educlaw_instructor).
Owning skill: educlaw-highered
Run: python3 init_db.py [db_path]

ADR-0034 phase 2 bulk-39. This module's schema is declared as metadata and
provisioned through `erpclaw_lib.seam`, which emits dialect-correct DDL, instead
of a hand-written ``CREATE TABLE`` block opened with ``sqlite3.connect``. The old
shape could not run on PostgreSQL at all. Conversion rules are the pilot's
(`erpclaw-esign`): seam vocabulary only, money and IDs stay TEXT, and
``primary_key=True, nullable=True`` reproduces SQLite's ``id TEXT PRIMARY KEY``
without adding a NOT NULL that never shipped.
"""
import importlib.util
import os
import sys

# Bootstrap the shared lib only when it is not already reachable — an
# unconditional insert at position 0 overrides a caller that deliberately bound a
# different tree (ADR-0034 phase 2 step 2d).
if importlib.util.find_spec("erpclaw_lib") is None:
    sys.path.insert(0, os.path.join(os.path.expanduser(
        os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))

from erpclaw_lib.seam import (  # noqa: E402
    CheckConstraint, Column, ForeignKey, Index, Integer, MetaData, Table, Text,
    provision, reference_table, table_exists, text,
)

DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")

# The pre-conversion probe asked for `company` alone. Transcribed, not widened.
REQUIRED_FOUNDATION = ["company"]

METADATA = MetaData()

# The one table this module points at but does not own. Declared for foreign key
# resolution only and never created here; see `seam.reference_table`.
reference_table("company", METADATA)

# ==========================================================
# Registrar domain (1 table — degree programs)
# ==========================================================

DEGREE_PROGRAM = Table(
    "highered_degree_program", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("degree_type", Text, nullable=False,
           server_default=text("'bachelor'")),
    Column("department", Text, nullable=False, server_default=text("''")),
    Column("credits_required", Integer, nullable=False, server_default=text("0")),
    Column("program_status", Text, nullable=False,
           server_default=text("'active'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "degree_type IN ('associate','bachelor','master','doctoral','certificate')",
        name="ck_highered_degree_program_degree_type"),
    CheckConstraint(
        "program_status IN ('active','inactive','phasing_out')",
        name="ck_highered_degree_program_program_status"),
)

Index("idx_hdp_company", DEGREE_PROGRAM.c.company_id)
Index("idx_hdp_dept", DEGREE_PROGRAM.c.department)

# ==========================================================
# Records domain (1 table — holds)
# highered_transcript / highered_academic_standing removed 2026-06-01 (audit P2):
# dead scaffolding (zero code/doc references). Dropped from existing DBs by this
# module's migration 001.
# ==========================================================

HOLD = Table(
    "highered_hold", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    # No foreign key on `student_id`, although `educlaw_student` exists. The
    # pre-conversion DDL had none; a conversion is not the place to add one.
    Column("student_id", Text, nullable=False, server_default=text("''")),
    Column("hold_type", Text, nullable=False,
           server_default=text("'administrative'")),
    Column("reason", Text, nullable=False, server_default=text("''")),
    Column("placed_by", Text, nullable=False, server_default=text("''")),
    Column("placed_date", Text, nullable=False, server_default=text("''")),
    Column("removed_date", Text, nullable=False, server_default=text("''")),
    Column("hold_status", Text, nullable=False, server_default=text("'active'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "hold_type IN ('financial','academic','disciplinary','administrative')",
        name="ck_highered_hold_hold_type"),
    CheckConstraint(
        "hold_status IN ('active','removed')",
        name="ck_highered_hold_hold_status"),
)

Index("idx_hh_student", HOLD.c.student_id)
Index("idx_hh_status", HOLD.c.hold_status)

# ==========================================================
# Financial Aid domain (1 table — disbursements)
# Note: aid_package fields merged into educlaw_scholarship
# ==========================================================

DISBURSEMENT = Table(
    "highered_disbursement", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    # `aid_package_id` points at educlaw_scholarship by convention only — the
    # shipped DDL declares no foreign key, so neither does this.
    Column("aid_package_id", Text, nullable=False, server_default=text("''")),
    Column("disbursement_date", Text, nullable=False, server_default=text("''")),
    # Money is TEXT on every backend (ADR-0034 dec. 1).
    Column("amount", Text, nullable=False, server_default=text("'0.00'")),
    Column("aid_type", Text, nullable=False, server_default=text("'grant'")),
    Column("fund_source", Text, nullable=False, server_default=text("''")),
    Column("disbursement_status", Text, nullable=False,
           server_default=text("'pending'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "aid_type IN ('grant','scholarship','loan','work_study')",
        name="ck_highered_disbursement_aid_type"),
    CheckConstraint(
        "disbursement_status IN ('pending','disbursed','returned')",
        name="ck_highered_disbursement_disbursement_status"),
)

Index("idx_hd_package", DISBURSEMENT.c.aid_package_id)
Index("idx_hd_company", DISBURSEMENT.c.company_id)

# ==========================================================
# Alumni domain (3 tables)
# ==========================================================

ALUMNUS = Table(
    "highered_alumnus", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("graduation_year", Integer, nullable=False, server_default=text("0")),
    Column("degree_program", Text, nullable=False, server_default=text("''")),
    Column("employer", Text, nullable=False, server_default=text("''")),
    Column("job_title", Text, nullable=False, server_default=text("''")),
    Column("is_donor", Integer, nullable=False, server_default=text("0")),
    # Money, and its default is spelled '0' here where `amount` elsewhere in this
    # module uses '0.00'. Both spellings are preserved as shipped.
    Column("total_giving", Text, nullable=False, server_default=text("'0'")),
    Column("engagement_level", Text, nullable=False,
           server_default=text("'inactive'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "engagement_level IN ('inactive','low','medium','high','champion')",
        name="ck_highered_alumnus_engagement_level"),
)

Index("idx_ha_company", ALUMNUS.c.company_id)

ALUMNI_EVENT = Table(
    "highered_alumni_event", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("event_date", Text, nullable=False, server_default=text("''")),
    Column("event_type", Text, nullable=False, server_default=text("'other'")),
    Column("attendees", Integer, nullable=False, server_default=text("0")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "event_type IN ('reunion','networking','fundraiser','career_fair','other')",
        name="ck_highered_alumni_event_event_type"),
)

Index("idx_hae_company", ALUMNI_EVENT.c.company_id)

GIVING_RECORD = Table(
    "highered_giving_record", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("alumnus_id", Text,
           ForeignKey("highered_alumnus.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("amount", Text, nullable=False, server_default=text("'0.00'")),
    Column("giving_date", Text, nullable=False, server_default=text("''")),
    Column("campaign", Text, nullable=False, server_default=text("''")),
    Column("gift_type", Text, nullable=False, server_default=text("'cash'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "gift_type IN ('cash','stock','planned','in_kind')",
        name="ck_highered_giving_record_gift_type"),
)

Index("idx_hgr_alumnus", GIVING_RECORD.c.alumnus_id)
Index("idx_hgr_company", GIVING_RECORD.c.company_id)

# ==========================================================
# Faculty domain (2 tables — course_assignment, research_grant)
# Note: highered_faculty merged into educlaw_instructor
# ==========================================================

COURSE_ASSIGNMENT = Table(
    "highered_course_assignment", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    # `faculty_id` -> educlaw_instructor and `section_id` -> educlaw_section by
    # convention; the shipped DDL declares neither as a foreign key.
    Column("faculty_id", Text, nullable=False, server_default=text("''")),
    Column("section_id", Text, nullable=False, server_default=text("''")),
    Column("role", Text, nullable=False, server_default=text("'primary'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "role IN ('primary','secondary','ta')",
        name="ck_highered_course_assignment_role"),
)

Index("idx_hca_faculty", COURSE_ASSIGNMENT.c.faculty_id)
Index("idx_hca_section", COURSE_ASSIGNMENT.c.section_id)
# The module's one uniqueness key: a faculty member is assigned to a section
# once. Shipped as a UNIQUE INDEX rather than a table-level UNIQUE, so it stays
# an index here — the two are not interchangeable to the catalog.
Index("uq_hca_fac_sec", COURSE_ASSIGNMENT.c.faculty_id,
      COURSE_ASSIGNMENT.c.section_id, unique=True)

RESEARCH_GRANT = Table(
    "highered_research_grant", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("faculty_id", Text, nullable=False, server_default=text("''")),
    Column("title", Text, nullable=False, server_default=text("''")),
    Column("funding_agency", Text, nullable=False, server_default=text("''")),
    Column("amount", Text, nullable=False, server_default=text("'0.00'")),
    Column("start_date", Text, nullable=False, server_default=text("''")),
    Column("end_date", Text, nullable=False, server_default=text("''")),
    Column("grant_status", Text, nullable=False, server_default=text("'active'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "grant_status IN ('proposed','active','completed','expired')",
        name="ck_highered_research_grant_grant_status"),
)

Index("idx_hrg_faculty", RESEARCH_GRANT.c.faculty_id)
Index("idx_hrg_company", RESEARCH_GRANT.c.company_id)

# ==========================================================
# Admissions domain (2 tables)
# ==========================================================

APPLICATION = Table(
    "highered_application", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, server_default=text("''")),
    Column("applicant_name", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("phone", Text, nullable=False, server_default=text("''")),
    # The module's only nullable column: `program_id` ships without NOT NULL
    # while every other column has it. Preserved.
    Column("program_id", Text,
           ForeignKey("highered_degree_program.id", ondelete="RESTRICT"),
           server_default=text("''")),
    Column("application_date", Text, nullable=False, server_default=text("''")),
    Column("intended_term", Text, nullable=False, server_default=text("''")),
    Column("intended_year", Integer, nullable=False, server_default=text("0")),
    Column("gpa_incoming", Text, nullable=False, server_default=text("'0.00'")),
    Column("test_scores", Text, nullable=False, server_default=text("'{}'")),
    Column("documents", Text, nullable=False, server_default=text("'[]'")),
    Column("application_status", Text, nullable=False,
           server_default=text("'submitted'")),
    Column("notes", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "application_status IN ('submitted','under_review','accepted',"
        "'rejected','waitlisted','withdrawn')",
        name="ck_highered_application_application_status"),
)

Index("idx_happ_company", APPLICATION.c.company_id)
Index("idx_happ_program", APPLICATION.c.program_id)

ADMISSION_DECISION = Table(
    "highered_admission_decision", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("application_id", Text,
           ForeignKey("highered_application.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("decision", Text, nullable=False, server_default=text("'pending'")),
    Column("decided_by", Text, nullable=False, server_default=text("''")),
    Column("decision_date", Text, nullable=False, server_default=text("''")),
    Column("conditions", Text, nullable=False, server_default=text("''")),
    Column("scholarship_offered", Text, nullable=False,
           server_default=text("'0.00'")),
    Column("notes", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "decision IN ('pending','admit','deny','waitlist','conditional_admit',"
        "'defer')",
        name="ck_highered_admission_decision_decision"),
)

Index("idx_had_app", ADMISSION_DECISION.c.application_id)
Index("idx_had_company", ADMISSION_DECISION.c.company_id)


def _require_foundation(db_path):
    """Refuse to install onto a database with no ERPClaw foundation.

    Same check and same message as before the conversion; the pre-conversion
    version read `sqlite_master` directly, which is a hard error on PostgreSQL
    rather than a false, so it is asked through the seam instead.
    """
    missing = [t for t in REQUIRED_FOUNDATION if not table_exists(t, db_path)]
    if missing:
        print("ERROR: Foundation tables not found. Run erpclaw-setup first.")
        sys.exit(1)


def create_educlaw_highered_tables(db_path):
    """Create the higher-education tables and indexes on whichever backend is configured.

    Same contract as before the ADR-0034 conversion, including the fact that this
    installer creates only its own 10 tables and never the shared educlaw base
    schema. Idempotent, and the returned counts are what was ACTUALLY created
    rather than what was declared.
    """
    _require_foundation(db_path)

    result = provision(METADATA, db_path)
    return {
        "database": db_path,
        "tables": result["tables"],
        "indexes": result["indexes"],
    }


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    result = create_educlaw_highered_tables(db_path)
    print(f"educlaw-highered: {result['tables']} tables created in "
          f"{result['database']}")
