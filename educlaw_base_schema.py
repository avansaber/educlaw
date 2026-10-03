"""EduClaw base schema — the 32 tables every educlaw vertical shares.

ONE OWNER (ADR-0034 phase 2). Until 2026-08-16 these 32 tables were declared
TWICE: here as a 745-line block of hand-written DDL, and again in
``educlaw/init_db.py`` as seam metadata. The copies drifted, and the drift was
not theoretical — ``educlaw_notification``'s CHECK rejected two values educlaw
core itself writes (M119), because core's copy was widened and this one was not.
A single declaration cannot drift from itself.

This file now owns the shared 32; ``educlaw/init_db.py`` imports them and keeps
only its own 13. The five sub-verticals (finaid, k12, lms, scheduling,
statereport) import THIS module and never reach into core.

It also removes the two seam bypasses that made those five unprovisionable on
PostgreSQL: a direct read of SQLite's catalog table, and a multi-statement
script exec. Both are dialect-specific; ``table_exists`` and ``provision`` are
not. (The retired spellings are named in the plan, not repeated here — the
bypass ratchet counts occurrences, so prose about a bypass reads as one.)

Index count is DERIVED (``len(BASE_METADATA.indexes)``), never restated in prose
— the header of the file this replaces claimed 88 while carrying 93.
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
    UniqueConstraint, now_default, provision, reference_table, table_exists,
    text,
)

BASE_METADATA = MetaData()

# Foundation tables the shared 32 point at but do not own — declared so the
# foreign keys resolve, never created here.
reference_table("company", BASE_METADATA)
reference_table("account", BASE_METADATA)
reference_table("customer", BASE_METADATA)
reference_table("department", BASE_METADATA)

# The sentinel: if this table is present the base set has been provisioned.
SENTINEL_TABLE = "educlaw_academic_term"

ACADEMIC_YEAR = Table(
    "educlaw_academic_year", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("start_date", Text, nullable=False, server_default=text("''")),
    Column("end_date", Text, nullable=False, server_default=text("''")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("company_id", "name"),
    CheckConstraint("start_date < end_date",
                    name="ck_educlaw_academic_year_dates"),
)

Index("idx_academic_year_company_active",
      ACADEMIC_YEAR.c.company_id, ACADEMIC_YEAR.c.is_active)
Index("idx_academic_year_company_name",
      ACADEMIC_YEAR.c.company_id, ACADEMIC_YEAR.c.name)

# ---------------------------------------------------------------------------
# 2. educlaw_academic_term
# ---------------------------------------------------------------------------
ACADEMIC_TERM = Table(
    "educlaw_academic_term", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("term_type", Text, nullable=False, server_default=text("''")),
    Column("academic_year_id", Text,
           ForeignKey("educlaw_academic_year.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("start_date", Text, nullable=False, server_default=text("''")),
    Column("end_date", Text, nullable=False, server_default=text("''")),
    Column("enrollment_start_date", Text, nullable=False,
           server_default=text("''")),
    Column("enrollment_end_date", Text, nullable=False,
           server_default=text("''")),
    Column("grade_submission_deadline", Text, nullable=False,
           server_default=text("''")),
    Column("status", Text, nullable=False, server_default=text("'setup'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "term_type IN ('semester','quarter','trimester','summer','custom')",
        name="ck_educlaw_academic_term_term_type"),
    CheckConstraint(
        "status IN ('setup','enrollment_open','active','grades_open',"
        "'grades_finalized','closed')",
        name="ck_educlaw_academic_term_status"),
    CheckConstraint("start_date < end_date",
                    name="ck_educlaw_academic_term_dates"),
)

Index("idx_academic_term_year", ACADEMIC_TERM.c.academic_year_id)
Index("idx_academic_term_company_status",
      ACADEMIC_TERM.c.company_id, ACADEMIC_TERM.c.status)
Index("idx_academic_term_dates",
      ACADEMIC_TERM.c.start_date, ACADEMIC_TERM.c.end_date)

# ---------------------------------------------------------------------------
# 3. educlaw_announcement
# ---------------------------------------------------------------------------
ANNOUNCEMENT = Table(
    "educlaw_announcement", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("title", Text, nullable=False, server_default=text("''")),
    Column("body", Text, nullable=False, server_default=text("''")),
    Column("priority", Text, nullable=False, server_default=text("'normal'")),
    Column("audience_type", Text, nullable=False, server_default=text("''")),
    Column("audience_filter", Text, nullable=False, server_default=text("'{}'")),
    Column("publish_date", Text, nullable=False, server_default=text("''")),
    Column("expiry_date", Text, nullable=False, server_default=text("''")),
    Column("announcement_status", Text, nullable=False,
           server_default=text("'draft'")),
    Column("published_by", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint("priority IN ('normal','urgent','emergency')",
                    name="ck_educlaw_announcement_priority"),
    CheckConstraint(
        "audience_type IN ('all','students','guardians','staff','program',"
        "'section','department','grade_level')",
        name="ck_educlaw_announcement_audience_type"),
    CheckConstraint(
        "announcement_status IN ('draft','published','archived')",
        name="ck_educlaw_announcement_announcement_status"),
)

Index("idx_announcement_company_status", ANNOUNCEMENT.c.company_id,
      ANNOUNCEMENT.c.announcement_status, ANNOUNCEMENT.c.publish_date)
Index("idx_announcement_audience", ANNOUNCEMENT.c.audience_type)

# ---------------------------------------------------------------------------
# 4. educlaw_course
# ---------------------------------------------------------------------------
COURSE = Table(
    "educlaw_course", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("course_code", Text, nullable=False, server_default=text("''")),
    Column("code", Text, nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("credit_hours", Text, nullable=False, server_default=text("'0'")),
    Column("credits", Integer, nullable=False, server_default=text("0")),
    Column("department_id", Text,
           ForeignKey("department.id", ondelete="RESTRICT")),
    Column("department", Text, nullable=False, server_default=text("''")),
    Column("course_type", Text, nullable=False,
           server_default=text("'lecture'")),
    Column("prerequisites", Text, nullable=False, server_default=text("''")),
    Column("grade_level", Text, nullable=False, server_default=text("''")),
    Column("max_enrollment", Integer, nullable=False, server_default=text("0")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("company_id", "course_code"),
    CheckConstraint(
        "course_type IN ('lecture','lab','seminar','independent_study',"
        "'internship','online')",
        name="ck_educlaw_course_course_type"),
)

Index("idx_course_company_code", COURSE.c.company_id, COURSE.c.course_code)
Index("idx_course_department", COURSE.c.department_id)
Index("idx_course_grade_level", COURSE.c.grade_level)
Index("idx_course_active", COURSE.c.company_id, COURSE.c.is_active)

# ---------------------------------------------------------------------------
# 5. educlaw_course_prerequisite
# ---------------------------------------------------------------------------
COURSE_PREREQUISITE = Table(
    "educlaw_course_prerequisite", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("course_id", Text,
           ForeignKey("educlaw_course.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("prerequisite_course_id", Text,
           ForeignKey("educlaw_course.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("min_grade", Text, nullable=False, server_default=text("''")),
    Column("is_corequisite", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("course_id", "prerequisite_course_id"),
    CheckConstraint("course_id != prerequisite_course_id",
                    name="ck_educlaw_course_prerequisite_self"),
)

Index("idx_prereq_course", COURSE_PREREQUISITE.c.course_id)
Index("idx_prereq_prereq", COURSE_PREREQUISITE.c.prerequisite_course_id)

# ---------------------------------------------------------------------------
# 6. educlaw_fee_category
# ---------------------------------------------------------------------------
FEE_CATEGORY = Table(
    "educlaw_fee_category", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("revenue_account_id", Text,
           ForeignKey("account.id", ondelete="RESTRICT")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
)

Index("idx_fee_category_company",
      FEE_CATEGORY.c.company_id, FEE_CATEGORY.c.is_active)

# ---------------------------------------------------------------------------
# 7. educlaw_grading_scale
# ---------------------------------------------------------------------------
GRADING_SCALE = Table(
    "educlaw_grading_scale", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("is_default", Integer, nullable=False, server_default=text("0")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("company_id", "name"),
)

Index("idx_grading_scale_company", GRADING_SCALE.c.company_id)
Index("idx_grading_scale_default",
      GRADING_SCALE.c.company_id, GRADING_SCALE.c.is_default)

# ---------------------------------------------------------------------------
# 8. educlaw_grading_scale_entry
# ---------------------------------------------------------------------------
GRADING_SCALE_ENTRY = Table(
    "educlaw_grading_scale_entry", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("grading_scale_id", Text,
           ForeignKey("educlaw_grading_scale.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("letter_grade", Text, nullable=False, server_default=text("''")),
    Column("grade_points", Text, nullable=False, server_default=text("'0'")),
    Column("min_percentage", Text, nullable=False, server_default=text("'0'")),
    Column("max_percentage", Text, nullable=False, server_default=text("'0'")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("is_passing", Integer, nullable=False, server_default=text("1")),
    Column("counts_in_gpa", Integer, nullable=False, server_default=text("1")),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("grading_scale_id", "letter_grade"),
    CheckConstraint(
        "CAST(min_percentage AS REAL) <= CAST(max_percentage AS REAL)",
        name="ck_educlaw_grading_scale_entry_percentage_range"),
)

Index("idx_scale_entry_scale", GRADING_SCALE_ENTRY.c.grading_scale_id)
Index("idx_scale_entry_sort",
      GRADING_SCALE_ENTRY.c.grading_scale_id, GRADING_SCALE_ENTRY.c.sort_order)

# ---------------------------------------------------------------------------
# 9. educlaw_guardian
# ---------------------------------------------------------------------------
GUARDIAN = Table(
    "educlaw_guardian", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("first_name", Text, nullable=False, server_default=text("''")),
    Column("last_name", Text, nullable=False, server_default=text("''")),
    Column("full_name", Text, nullable=False, server_default=text("''")),
    Column("relationship", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("phone", Text, nullable=False, server_default=text("''")),
    Column("alternate_phone", Text, nullable=False, server_default=text("''")),
    Column("address", Text, nullable=False, server_default=text("'{}'")),
    Column("occupation", Text, nullable=False, server_default=text("''")),
    Column("employer", Text, nullable=False, server_default=text("''")),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "relationship IN ('father','mother','guardian','grandparent',"
        "'stepparent','foster_parent','other')",
        name="ck_educlaw_guardian_relationship"),
)

Index("idx_guardian_company_name",
      GUARDIAN.c.company_id, GUARDIAN.c.last_name, GUARDIAN.c.first_name)
Index("idx_guardian_email", GUARDIAN.c.email)
Index("idx_guardian_customer", GUARDIAN.c.customer_id)

# ---------------------------------------------------------------------------
# 10. educlaw_instructor
# ---------------------------------------------------------------------------
INSTRUCTOR = Table(
    "educlaw_instructor", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, unique=True,
           server_default=text("''")),
    Column("employee_id", Text, unique=True, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("department", Text, nullable=False, server_default=text("''")),
    Column("credentials", Text, nullable=False, server_default=text("'[]'")),
    Column("specializations", Text, nullable=False,
           server_default=text("'[]'")),
    Column("max_teaching_load_hours", Integer, nullable=False,
           server_default=text("0")),
    Column("office_location", Text, nullable=False, server_default=text("''")),
    Column("office_hours", Text, nullable=False, server_default=text("'[]'")),
    Column("bio", Text, nullable=False, server_default=text("''")),
    Column("rank", Text, nullable=False, server_default=text("''")),
    Column("tenure_status", Text, nullable=False, server_default=text("''")),
    Column("hire_date", Text, nullable=False, server_default=text("''")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "rank IN ('','adjunct','instructor','assistant_professor',"
        "'associate_professor','professor','emeritus')",
        name="ck_educlaw_instructor_rank"),
    CheckConstraint(
        "tenure_status IN ('','non_tenure','tenure_track','tenured')",
        name="ck_educlaw_instructor_tenure_status"),
)

Index("idx_instructor_employee", INSTRUCTOR.c.employee_id)
Index("idx_instructor_company_active",
      INSTRUCTOR.c.company_id, INSTRUCTOR.c.is_active)
Index("idx_instructor_series", INSTRUCTOR.c.naming_series)

# ---------------------------------------------------------------------------
# 11. educlaw_notification
# ---------------------------------------------------------------------------
NOTIFICATION = Table(
    "educlaw_notification", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("recipient_type", Text, nullable=False, server_default=text("''")),
    Column("recipient_id", Text, nullable=False, server_default=text("''")),
    Column("notification_type", Text, nullable=False,
           server_default=text("''")),
    Column("title", Text, nullable=False, server_default=text("''")),
    Column("message", Text, nullable=False, server_default=text("''")),
    Column("reference_type", Text, nullable=False, server_default=text("''")),
    Column("reference_id", Text, nullable=False, server_default=text("''")),
    Column("is_read", Integer, nullable=False, server_default=text("0")),
    Column("sent_via", Text, nullable=False, server_default=text("'system'")),
    Column("sent_at", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "recipient_type IN ('student','guardian','employee')",
        name="ck_educlaw_notification_recipient_type"),
    CheckConstraint(
        "notification_type IN ('grade_posted','fee_due','absence',"
        "'announcement','progress_report','emergency','acceptance',"
        "'enrollment_confirmed','payment','housing_waitlist')",
        name="ck_educlaw_notification_notification_type"),
    CheckConstraint("sent_via IN ('system','email')",
                    name="ck_educlaw_notification_sent_via"),
)

Index("idx_notification_recipient", NOTIFICATION.c.recipient_type,
      NOTIFICATION.c.recipient_id, NOTIFICATION.c.is_read)
Index("idx_notification_company_type",
      NOTIFICATION.c.company_id, NOTIFICATION.c.notification_type)
Index("idx_notification_created", NOTIFICATION.c.created_at)

# ---------------------------------------------------------------------------
# 12. educlaw_program
# ---------------------------------------------------------------------------
PROGRAM = Table(
    "educlaw_program", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("code", Text, nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("program_type", Text, nullable=False, server_default=text("''")),
    Column("department_id", Text,
           ForeignKey("department.id", ondelete="RESTRICT")),
    Column("total_credits_required", Text, nullable=False,
           server_default=text("'0'")),
    Column("duration_years", Integer, nullable=False, server_default=text("0")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("company_id", "code"),
    CheckConstraint(
        "program_type IN ('k12','associate','bachelor','master','doctoral',"
        "'certificate','diploma')",
        name="ck_educlaw_program_program_type"),
)

Index("idx_program_company_code", PROGRAM.c.company_id, PROGRAM.c.code)
Index("idx_program_department", PROGRAM.c.department_id)
Index("idx_program_active", PROGRAM.c.company_id, PROGRAM.c.is_active)

# ---------------------------------------------------------------------------
# 13. educlaw_fee_structure
# ---------------------------------------------------------------------------
FEE_STRUCTURE = Table(
    "educlaw_fee_structure", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("program_id", Text,
           ForeignKey("educlaw_program.id", ondelete="RESTRICT")),
    Column("academic_term_id", Text,
           ForeignKey("educlaw_academic_term.id", ondelete="RESTRICT")),
    Column("grade_level", Text, nullable=False, server_default=text("''")),
    Column("total_amount", Text, nullable=False, server_default=text("'0'")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint("CAST(total_amount AS NUMERIC) >= 0",
                    name="ck_educlaw_fee_structure_total_amount"),
)

Index("idx_fee_structure_program_term", FEE_STRUCTURE.c.company_id,
      FEE_STRUCTURE.c.program_id, FEE_STRUCTURE.c.academic_term_id)
Index("idx_fee_structure_grade_term", FEE_STRUCTURE.c.company_id,
      FEE_STRUCTURE.c.grade_level, FEE_STRUCTURE.c.academic_term_id)
Index("idx_fee_structure_active",
      FEE_STRUCTURE.c.company_id, FEE_STRUCTURE.c.is_active)

# ---------------------------------------------------------------------------
# 14. educlaw_fee_structure_item
# ---------------------------------------------------------------------------
FEE_STRUCTURE_ITEM = Table(
    "educlaw_fee_structure_item", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("fee_structure_id", Text,
           ForeignKey("educlaw_fee_structure.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("fee_category_id", Text,
           ForeignKey("educlaw_fee_category.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("amount", Text, nullable=False, server_default=text("'0'")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("fee_structure_id", "fee_category_id"),
    CheckConstraint("CAST(amount AS NUMERIC) >= 0",
                    name="ck_educlaw_fee_structure_item_amount"),
)

Index("idx_fee_item_structure", FEE_STRUCTURE_ITEM.c.fee_structure_id)
Index("idx_fee_item_category", FEE_STRUCTURE_ITEM.c.fee_category_id)

# ---------------------------------------------------------------------------
# 15. educlaw_program_requirement
# ---------------------------------------------------------------------------
PROGRAM_REQUIREMENT = Table(
    "educlaw_program_requirement", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("program_id", Text,
           ForeignKey("educlaw_program.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("course_id", Text,
           ForeignKey("educlaw_course.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("requirement_type", Text, nullable=False, server_default=text("''")),
    Column("credit_category", Text, nullable=False, server_default=text("''")),
    Column("min_grade", Text, nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("program_id", "course_id"),
    CheckConstraint(
        "requirement_type IN ('required','elective','core','major',"
        "'general_education')",
        name="ck_educlaw_program_requirement_requirement_type"),
)

Index("idx_program_req_program", PROGRAM_REQUIREMENT.c.program_id)
Index("idx_program_req_course", PROGRAM_REQUIREMENT.c.course_id)

# ---------------------------------------------------------------------------
# 16. educlaw_room
# ---------------------------------------------------------------------------
ROOM = Table(
    "educlaw_room", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("room_number", Text, nullable=False, server_default=text("''")),
    Column("building", Text, nullable=False, server_default=text("''")),
    Column("capacity", Integer, nullable=False, server_default=text("0")),
    Column("room_type", Text, nullable=False,
           server_default=text("'classroom'")),
    Column("facilities", Text, nullable=False, server_default=text("'[]'")),
    Column("is_active", Integer, nullable=False, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    UniqueConstraint("company_id", "building", "room_number"),
    CheckConstraint(
        "room_type IN ('classroom','lab','auditorium','gym','library','office')",
        name="ck_educlaw_room_room_type"),
    CheckConstraint("capacity > 0", name="ck_educlaw_room_capacity"),
)

Index("idx_room_company_building",
      ROOM.c.company_id, ROOM.c.building, ROOM.c.room_number)
Index("idx_room_active", ROOM.c.company_id, ROOM.c.is_active)

# ---------------------------------------------------------------------------
# 17. educlaw_section
# ---------------------------------------------------------------------------
SECTION = Table(
    "educlaw_section", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, unique=True,
           server_default=text("''")),
    Column("section_number", Text, nullable=False, server_default=text("''")),
    Column("course_id", Text,
           ForeignKey("educlaw_course.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("academic_term_id", Text,
           ForeignKey("educlaw_academic_term.id", ondelete="RESTRICT")),
    Column("instructor_id", Text,
           ForeignKey("educlaw_instructor.id", ondelete="RESTRICT")),
    Column("instructor", Text, nullable=False, server_default=text("''")),
    Column("term", Text, nullable=False, server_default=text("''")),
    Column("year", Integer, nullable=False, server_default=text("0")),
    Column("room_id", Text, ForeignKey("educlaw_room.id", ondelete="RESTRICT")),
    Column("days_of_week", Text, nullable=False, server_default=text("'[]'")),
    Column("start_time", Text, nullable=False, server_default=text("''")),
    Column("end_time", Text, nullable=False, server_default=text("''")),
    Column("schedule", Text, nullable=False, server_default=text("''")),
    Column("location", Text, nullable=False, server_default=text("''")),
    Column("max_enrollment", Integer, nullable=False, server_default=text("0")),
    Column("capacity", Integer, nullable=False, server_default=text("0")),
    Column("current_enrollment", Integer, nullable=False,
           server_default=text("0")),
    Column("enrolled", Integer, nullable=False, server_default=text("0")),
    Column("waitlist_enabled", Integer, nullable=False,
           server_default=text("0")),
    Column("waitlist_max", Integer, nullable=False, server_default=text("0")),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("section_status", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "status IN ('draft','scheduled','open','closed','cancelled')",
        name="ck_educlaw_section_status"),
    CheckConstraint("section_status IN ('','open','closed','cancelled')",
                    name="ck_educlaw_section_section_status"),
    CheckConstraint("max_enrollment >= 0",
                    name="ck_educlaw_section_max_enrollment"),
    CheckConstraint("current_enrollment >= 0",
                    name="ck_educlaw_section_current_enrollment"),
)

Index("idx_section_course_term", SECTION.c.course_id, SECTION.c.academic_term_id)
Index("idx_section_instructor_term",
      SECTION.c.instructor_id, SECTION.c.academic_term_id)
Index("idx_section_room_term", SECTION.c.room_id, SECTION.c.academic_term_id)
Index("idx_section_company_status", SECTION.c.company_id, SECTION.c.status)
Index("idx_section_series", SECTION.c.naming_series)

# ---------------------------------------------------------------------------
# 18. educlaw_assessment_plan
# ---------------------------------------------------------------------------
ASSESSMENT_PLAN = Table(
    "educlaw_assessment_plan", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("section_id", Text,
           ForeignKey("educlaw_section.id", ondelete="RESTRICT"),
           nullable=False, unique=True, server_default=text("''")),
    Column("grading_scale_id", Text,
           ForeignKey("educlaw_grading_scale.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
)

Index("idx_assessment_plan_section", ASSESSMENT_PLAN.c.section_id)

# ---------------------------------------------------------------------------
# 19. educlaw_assessment_category
# ---------------------------------------------------------------------------
ASSESSMENT_CATEGORY = Table(
    "educlaw_assessment_category", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("assessment_plan_id", Text,
           ForeignKey("educlaw_assessment_plan.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("weight_percentage", Text, nullable=False,
           server_default=text("'0'")),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
)

Index("idx_assessment_category_plan", ASSESSMENT_CATEGORY.c.assessment_plan_id)
Index("idx_assessment_category_sort",
      ASSESSMENT_CATEGORY.c.assessment_plan_id, ASSESSMENT_CATEGORY.c.sort_order)

# ---------------------------------------------------------------------------
# 20. educlaw_assessment
# ---------------------------------------------------------------------------
ASSESSMENT = Table(
    "educlaw_assessment", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("assessment_plan_id", Text,
           ForeignKey("educlaw_assessment_plan.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("category_id", Text,
           ForeignKey("educlaw_assessment_category.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("max_points", Text, nullable=False, server_default=text("'0'")),
    Column("due_date", Text, nullable=False, server_default=text("''")),
    Column("is_published", Integer, nullable=False, server_default=text("0")),
    Column("allows_extra_credit", Integer, nullable=False,
           server_default=text("0")),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
)

Index("idx_assessment_plan_category",
      ASSESSMENT.c.assessment_plan_id, ASSESSMENT.c.category_id)
Index("idx_assessment_due_date", ASSESSMENT.c.due_date)

# ---------------------------------------------------------------------------
# 21. educlaw_student_applicant
# ---------------------------------------------------------------------------
STUDENT_APPLICANT = Table(
    "educlaw_student_applicant", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, unique=True,
           server_default=text("''")),
    Column("first_name", Text, nullable=False, server_default=text("''")),
    Column("middle_name", Text, nullable=False, server_default=text("''")),
    Column("last_name", Text, nullable=False, server_default=text("''")),
    Column("date_of_birth", Text, nullable=False, server_default=text("''")),
    Column("gender", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("phone", Text, nullable=False, server_default=text("''")),
    Column("address", Text, nullable=False, server_default=text("'{}'")),
    Column("applying_for_program_id", Text,
           ForeignKey("educlaw_program.id", ondelete="RESTRICT")),
    Column("applying_for_term_id", Text,
           ForeignKey("educlaw_academic_term.id", ondelete="RESTRICT")),
    Column("previous_school", Text, nullable=False, server_default=text("''")),
    Column("previous_school_address", Text, nullable=False,
           server_default=text("''")),
    Column("transfer_records", Text, nullable=False, server_default=text("''")),
    Column("application_date", Text, nullable=False, server_default=text("''")),
    Column("status", Text, nullable=False, server_default=text("'applied'")),
    Column("reviewed_by", Text, nullable=False, server_default=text("''")),
    Column("review_date", Text, nullable=False, server_default=text("''")),
    Column("review_notes", Text, nullable=False, server_default=text("''")),
    Column("acceptance_deadline", Text, nullable=False,
           server_default=text("''")),
    Column("guardian_info", Text, nullable=False, server_default=text("'[]'")),
    Column("documents", Text, nullable=False, server_default=text("'[]'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "gender IN ('male','female','non_binary','prefer_not_to_say','')",
        name="ck_educlaw_student_applicant_gender"),
    CheckConstraint(
        "status IN ('applied','under_review','accepted','rejected',"
        "'waitlisted','pending_info','confirmed','enrolled')",
        name="ck_educlaw_student_applicant_status"),
)

Index("idx_applicant_company_status",
      STUDENT_APPLICANT.c.company_id, STUDENT_APPLICANT.c.status)
Index("idx_applicant_term", STUDENT_APPLICANT.c.applying_for_term_id)
Index("idx_applicant_series", STUDENT_APPLICANT.c.naming_series)

# ---------------------------------------------------------------------------
# 22. educlaw_student
# ---------------------------------------------------------------------------
# `program_id` is a plain TEXT column with no foreign key while
# `current_program_id` beside it has one. That asymmetry ships today and is
# transcribed, not tidied.
STUDENT = Table(
    "educlaw_student", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, unique=True,
           server_default=text("''")),
    Column("student_id", Text, nullable=False, server_default=text("''")),
    Column("first_name", Text, nullable=False, server_default=text("''")),
    Column("middle_name", Text, nullable=False, server_default=text("''")),
    Column("last_name", Text, nullable=False, server_default=text("''")),
    Column("full_name", Text, nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("date_of_birth", Text, nullable=False, server_default=text("''")),
    Column("gender", Text, nullable=False, server_default=text("''")),
    Column("email", Text, nullable=False, server_default=text("''")),
    Column("phone", Text, nullable=False, server_default=text("''")),
    Column("address", Text, nullable=False, server_default=text("'{}'")),
    Column("emergency_contact", Text, nullable=False,
           server_default=text("'{}'")),
    Column("student_applicant_id", Text,
           ForeignKey("educlaw_student_applicant.id", ondelete="RESTRICT")),
    Column("customer_id", Text,
           ForeignKey("customer.id", ondelete="RESTRICT")),
    Column("current_program_id", Text,
           ForeignKey("educlaw_program.id", ondelete="RESTRICT")),
    Column("program_id", Text, nullable=False, server_default=text("''")),
    Column("grade_level", Text, nullable=False, server_default=text("''")),
    Column("cohort_year", Integer, nullable=False, server_default=text("0")),
    Column("cumulative_gpa", Text, nullable=False, server_default=text("''")),
    Column("gpa", Text, nullable=False, server_default=text("''")),
    Column("total_credits_earned", Text, nullable=False,
           server_default=text("'0'")),
    Column("total_credits", Integer, nullable=False, server_default=text("0")),
    Column("academic_standing", Text, nullable=False,
           server_default=text("'good'")),
    Column("expected_graduation", Text, nullable=False,
           server_default=text("''")),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("registration_hold", Integer, nullable=False,
           server_default=text("0")),
    Column("directory_info_opt_out", Integer, nullable=False,
           server_default=text("0")),
    Column("is_coppa_applicable", Integer, nullable=False,
           server_default=text("0")),
    Column("coppa_consent_type", Text, nullable=False,
           server_default=text("''")),
    Column("coppa_consent_date", Text, nullable=False,
           server_default=text("''")),
    Column("photo", Text, nullable=False, server_default=text("''")),
    Column("ssn_encrypted", Text, nullable=False, server_default=text("''")),
    Column("enrollment_date", Text, nullable=False, server_default=text("''")),
    Column("graduation_date", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "gender IN ('male','female','non_binary','prefer_not_to_say','')",
        name="ck_educlaw_student_gender"),
    CheckConstraint(
        "academic_standing IN ('good','deans_list','honor_roll','probation',"
        "'suspension','dismissal','dean_list')",
        name="ck_educlaw_student_academic_standing"),
    CheckConstraint(
        "status IN ('active','graduated','withdrawn','suspended','expelled',"
        "'transferred','inactive')",
        name="ck_educlaw_student_status"),
    CheckConstraint("coppa_consent_type IN ('parent','school','')",
                    name="ck_educlaw_student_coppa_consent_type"),
)

Index("idx_student_company_status", STUDENT.c.company_id, STUDENT.c.status)
Index("idx_student_name",
      STUDENT.c.company_id, STUDENT.c.last_name, STUDENT.c.first_name)
Index("idx_student_customer", STUDENT.c.customer_id)
Index("idx_student_program", STUDENT.c.current_program_id)
Index("idx_student_series", STUDENT.c.naming_series)
Index("idx_student_coppa", STUDENT.c.is_coppa_applicable)

# ---------------------------------------------------------------------------
# 23. educlaw_consent_record
# ---------------------------------------------------------------------------
CONSENT_RECORD = Table(
    "educlaw_consent_record", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("consent_type", Text, nullable=False, server_default=text("''")),
    Column("granted_by", Text, nullable=False, server_default=text("''")),
    Column("granted_by_relationship", Text, nullable=False,
           server_default=text("''")),
    Column("consent_date", Text, nullable=False, server_default=text("''")),
    Column("expiry_date", Text, nullable=False, server_default=text("''")),
    Column("is_revoked", Integer, nullable=False, server_default=text("0")),
    Column("revoked_date", Text, nullable=False, server_default=text("''")),
    Column("third_party_name", Text, nullable=False, server_default=text("''")),
    Column("purpose", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "consent_type IN ('ferpa_directory','ferpa_disclosure',"
        "'coppa_collection','coppa_school_consent')",
        name="ck_educlaw_consent_record_consent_type"),
    CheckConstraint(
        "granted_by_relationship IN ('parent','student','school_official','')",
        name="ck_educlaw_consent_record_granted_by_relationship"),
)

Index("idx_consent_student_type",
      CONSENT_RECORD.c.student_id, CONSENT_RECORD.c.consent_type)
Index("idx_consent_company_type",
      CONSENT_RECORD.c.company_id, CONSENT_RECORD.c.consent_type)
Index("idx_consent_revoked", CONSENT_RECORD.c.is_revoked)

# ---------------------------------------------------------------------------
# 24. educlaw_course_enrollment
# ---------------------------------------------------------------------------
# `student_id` and `section_id` carry no foreign key here, though the same two
# columns are foreign keys in `educlaw_waitlist` and `educlaw_student_attendance`.
# Preserved as it ships.
COURSE_ENROLLMENT = Table(
    "educlaw_course_enrollment", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("student_id", Text, nullable=False, server_default=text("''")),
    Column("section_id", Text, nullable=False, server_default=text("''")),
    Column("enrollment_date", Text, nullable=False, server_default=text("''")),
    Column("enrollment_status", Text, nullable=False,
           server_default=text("'enrolled'")),
    Column("drop_date", Text, nullable=False, server_default=text("''")),
    Column("drop_reason", Text, nullable=False, server_default=text("''")),
    Column("grade", Text, nullable=False, server_default=text("''")),
    Column("grade_points", Text, nullable=False, server_default=text("''")),
    Column("final_letter_grade", Text, nullable=False,
           server_default=text("''")),
    Column("final_grade_points", Text, nullable=False,
           server_default=text("'0'")),
    Column("final_percentage", Text, nullable=False,
           server_default=text("'0'")),
    Column("grade_submitted_by", Text, nullable=False,
           server_default=text("''")),
    Column("grade_submitted_at", Text, nullable=False,
           server_default=text("''")),
    Column("is_grade_submitted", Integer, nullable=False,
           server_default=text("0")),
    Column("is_repeat", Integer, nullable=False, server_default=text("0")),
    Column("grade_type", Text, nullable=False, server_default=text("'letter'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "enrollment_status IN ('enrolled','completed','dropped','withdrawn',"
        "'incomplete','waitlisted')",
        name="ck_educlaw_course_enrollment_enrollment_status"),
    CheckConstraint("grade_type IN ('letter','pass_fail','audit')",
                    name="ck_educlaw_course_enrollment_grade_type"),
)

Index("idx_course_enroll_student_section",
      COURSE_ENROLLMENT.c.student_id, COURSE_ENROLLMENT.c.section_id)
Index("idx_course_enroll_section_status",
      COURSE_ENROLLMENT.c.section_id, COURSE_ENROLLMENT.c.enrollment_status)
Index("idx_course_enroll_student_status",
      COURSE_ENROLLMENT.c.student_id, COURSE_ENROLLMENT.c.enrollment_status)
Index("idx_course_enroll_grade_submitted",
      COURSE_ENROLLMENT.c.company_id, COURSE_ENROLLMENT.c.is_grade_submitted)

# ---------------------------------------------------------------------------
# 25. educlaw_assessment_result
# ---------------------------------------------------------------------------
ASSESSMENT_RESULT = Table(
    "educlaw_assessment_result", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("assessment_id", Text,
           ForeignKey("educlaw_assessment.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("course_enrollment_id", Text,
           ForeignKey("educlaw_course_enrollment.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("points_earned", Text, nullable=False, server_default=text("''")),
    Column("is_exempt", Integer, nullable=False, server_default=text("0")),
    Column("is_late", Integer, nullable=False, server_default=text("0")),
    Column("comments", Text, nullable=False, server_default=text("''")),
    Column("graded_by", Text, nullable=False, server_default=text("''")),
    Column("graded_at", Text, nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
)

Index("idx_assessment_result_assessment_student",
      ASSESSMENT_RESULT.c.assessment_id, ASSESSMENT_RESULT.c.student_id)
Index("idx_assessment_result_enrollment",
      ASSESSMENT_RESULT.c.course_enrollment_id)
Index("idx_assessment_result_student", ASSESSMENT_RESULT.c.student_id)

# ---------------------------------------------------------------------------
# 26. educlaw_data_access_log
# ---------------------------------------------------------------------------
DATA_ACCESS_LOG = Table(
    "educlaw_data_access_log", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("user_id", Text, nullable=False, server_default=text("''")),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("data_category", Text, nullable=False, server_default=text("''")),
    Column("access_type", Text, nullable=False, server_default=text("''")),
    Column("access_reason", Text, nullable=False, server_default=text("''")),
    Column("is_emergency_access", Integer, nullable=False,
           server_default=text("0")),
    Column("ip_address", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "data_category IN ('demographics','grades','attendance','financial',"
        "'health','discipline','communications')",
        name="ck_educlaw_data_access_log_data_category"),
    CheckConstraint("access_type IN ('view','export','print','api')",
                    name="ck_educlaw_data_access_log_access_type"),
)

Index("idx_data_access_student_category",
      DATA_ACCESS_LOG.c.student_id, DATA_ACCESS_LOG.c.data_category)
Index("idx_data_access_user",
      DATA_ACCESS_LOG.c.user_id, DATA_ACCESS_LOG.c.created_at)
Index("idx_data_access_company",
      DATA_ACCESS_LOG.c.company_id, DATA_ACCESS_LOG.c.created_at)
Index("idx_data_access_emergency", DATA_ACCESS_LOG.c.is_emergency_access)

# ---------------------------------------------------------------------------
# 27. educlaw_grade_amendment
# ---------------------------------------------------------------------------
GRADE_AMENDMENT = Table(
    "educlaw_grade_amendment", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("course_enrollment_id", Text,
           ForeignKey("educlaw_course_enrollment.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("old_letter_grade", Text, nullable=False, server_default=text("''")),
    Column("new_letter_grade", Text, nullable=False, server_default=text("''")),
    Column("old_grade_points", Text, nullable=False, server_default=text("'0'")),
    Column("new_grade_points", Text, nullable=False, server_default=text("'0'")),
    Column("reason", Text, nullable=False, server_default=text("''")),
    Column("amended_by", Text, nullable=False, server_default=text("''")),
    Column("approved_by", Text, nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
)

Index("idx_grade_amendment_enrollment", GRADE_AMENDMENT.c.course_enrollment_id)
Index("idx_grade_amendment_created", GRADE_AMENDMENT.c.created_at)

# ---------------------------------------------------------------------------
# 28. educlaw_program_enrollment
# ---------------------------------------------------------------------------
PROGRAM_ENROLLMENT = Table(
    "educlaw_program_enrollment", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, unique=True,
           server_default=text("''")),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("program_id", Text,
           ForeignKey("educlaw_program.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("academic_year_id", Text,
           ForeignKey("educlaw_academic_year.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("enrollment_date", Text, nullable=False, server_default=text("''")),
    Column("enrollment_status", Text, nullable=False,
           server_default=text("'active'")),
    Column("fee_invoice_id", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "enrollment_status IN ('active','completed','withdrawn','suspended')",
        name="ck_educlaw_program_enrollment_enrollment_status"),
)

Index("idx_prog_enroll_student", PROGRAM_ENROLLMENT.c.student_id)
Index("idx_prog_enroll_program_year",
      PROGRAM_ENROLLMENT.c.program_id, PROGRAM_ENROLLMENT.c.academic_year_id)
Index("idx_prog_enroll_company_status",
      PROGRAM_ENROLLMENT.c.company_id, PROGRAM_ENROLLMENT.c.enrollment_status)

# ---------------------------------------------------------------------------
# 29. educlaw_scholarship
# ---------------------------------------------------------------------------
# Every other `naming_series` in this schema is UNIQUE; this one is not, and
# `student_id` here carries no foreign key. Both are transcribed as they ship.
# The aid-package columns are money and stay TEXT.
SCHOLARSHIP = Table(
    "educlaw_scholarship", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, nullable=False, server_default=text("''")),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("student_id", Text, nullable=False, server_default=text("''")),
    Column("academic_term_id", Text,
           ForeignKey("educlaw_academic_term.id", ondelete="RESTRICT")),
    Column("discount_type", Text, nullable=False, server_default=text("''")),
    Column("discount_amount", Text, nullable=False, server_default=text("'0'")),
    Column("applies_to_category_id", Text,
           ForeignKey("educlaw_fee_category.id", ondelete="RESTRICT")),
    Column("scholarship_status", Text, nullable=False,
           server_default=text("'active'")),
    Column("reason", Text, nullable=False, server_default=text("''")),
    Column("approved_by", Text, nullable=False, server_default=text("''")),
    Column("aid_year", Text, nullable=False, server_default=text("''")),
    Column("total_cost", Text, nullable=False, server_default=text("'0'")),
    Column("efc", Text, nullable=False, server_default=text("'0'")),
    Column("total_need", Text, nullable=False, server_default=text("'0'")),
    Column("grants", Text, nullable=False, server_default=text("'0'")),
    Column("scholarships", Text, nullable=False, server_default=text("'0'")),
    Column("federal_aid", Text, nullable=False, server_default=text("'0'")),
    Column("state_aid", Text, nullable=False, server_default=text("'0'")),
    Column("institutional_aid", Text, nullable=False,
           server_default=text("'0'")),
    Column("loans", Text, nullable=False, server_default=text("'0'")),
    Column("work_study", Text, nullable=False, server_default=text("'0'")),
    Column("total_aid", Text, nullable=False, server_default=text("'0'")),
    Column("package_status", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint("discount_type IN ('fixed','percentage','')",
                    name="ck_educlaw_scholarship_discount_type"),
    CheckConstraint(
        "scholarship_status IN ('active','expired','revoked')",
        name="ck_educlaw_scholarship_scholarship_status"),
    CheckConstraint(
        "package_status IN ('','draft','offered','accepted','revised',"
        "'cancelled')",
        name="ck_educlaw_scholarship_package_status"),
)

Index("idx_scholarship_student_term",
      SCHOLARSHIP.c.student_id, SCHOLARSHIP.c.academic_term_id)
Index("idx_scholarship_company_status",
      SCHOLARSHIP.c.company_id, SCHOLARSHIP.c.scholarship_status)

# ---------------------------------------------------------------------------
# 30. educlaw_student_attendance
# ---------------------------------------------------------------------------
STUDENT_ATTENDANCE = Table(
    "educlaw_student_attendance", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("attendance_date", Text, nullable=False, server_default=text("''")),
    Column("section_id", Text,
           ForeignKey("educlaw_section.id", ondelete="RESTRICT")),
    Column("attendance_status", Text, nullable=False,
           server_default=text("''")),
    Column("late_minutes", Integer, nullable=False, server_default=text("0")),
    Column("comments", Text, nullable=False, server_default=text("''")),
    Column("marked_by", Text, nullable=False, server_default=text("''")),
    Column("source", Text, nullable=False, server_default=text("'manual'")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "attendance_status IN ('present','absent','tardy','excused','half_day')",
        name="ck_educlaw_student_attendance_attendance_status"),
    CheckConstraint("source IN ('manual','biometric','app')",
                    name="ck_educlaw_student_attendance_source"),
)

Index("idx_attendance_student_date_section",
      STUDENT_ATTENDANCE.c.student_id, STUDENT_ATTENDANCE.c.attendance_date,
      STUDENT_ATTENDANCE.c.section_id)
Index("idx_attendance_section_date",
      STUDENT_ATTENDANCE.c.section_id, STUDENT_ATTENDANCE.c.attendance_date)
Index("idx_attendance_company_date",
      STUDENT_ATTENDANCE.c.company_id, STUDENT_ATTENDANCE.c.attendance_date)
Index("idx_attendance_student_status",
      STUDENT_ATTENDANCE.c.student_id, STUDENT_ATTENDANCE.c.attendance_status)

# ---------------------------------------------------------------------------
# 31. educlaw_student_guardian
# ---------------------------------------------------------------------------
STUDENT_GUARDIAN = Table(
    "educlaw_student_guardian", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("guardian_id", Text,
           ForeignKey("educlaw_guardian.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("relationship", Text, nullable=False, server_default=text("''")),
    Column("has_custody", Integer, nullable=False, server_default=text("1")),
    Column("can_pickup", Integer, nullable=False, server_default=text("1")),
    Column("receives_communications", Integer, nullable=False,
           server_default=text("1")),
    Column("is_primary_contact", Integer, nullable=False,
           server_default=text("0")),
    Column("is_emergency_contact", Integer, nullable=False,
           server_default=text("0")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "relationship IN ('father','mother','guardian','grandparent',"
        "'stepparent','foster_parent','other')",
        name="ck_educlaw_student_guardian_relationship"),
)

Index("idx_student_guardian_student", STUDENT_GUARDIAN.c.student_id)
Index("idx_student_guardian_guardian", STUDENT_GUARDIAN.c.guardian_id)

# ---------------------------------------------------------------------------
# 32. educlaw_waitlist
# ---------------------------------------------------------------------------
WAITLIST = Table(
    "educlaw_waitlist", BASE_METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("student_id", Text,
           ForeignKey("educlaw_student.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("section_id", Text,
           ForeignKey("educlaw_section.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("position", Integer, nullable=False, server_default=text("0")),
    Column("requested_date", Text, nullable=False, server_default=text("''")),
    Column("waitlist_status", Text, nullable=False,
           server_default=text("'waiting'")),
    Column("offer_expires_at", Text, nullable=False, server_default=text("''")),
    Column("company_id", Text, ForeignKey("company.id", ondelete="RESTRICT"),
           nullable=False, server_default=text("''")),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("created_by", Text, nullable=False, server_default=text("''")),
    CheckConstraint(
        "waitlist_status IN ('waiting','offered','accepted','expired',"
        "'cancelled')",
        name="ck_educlaw_waitlist_waitlist_status"),
)

Index("idx_waitlist_section_position", WAITLIST.c.section_id, WAITLIST.c.position)
Index("idx_waitlist_student_section", WAITLIST.c.student_id, WAITLIST.c.section_id)
Index("idx_waitlist_status", WAITLIST.c.company_id, WAITLIST.c.waitlist_status)

# ==========================================================
# DOMAIN: CAFETERIA / MEAL MANAGEMENT (NSLP)
# ==========================================================
# educlaw_meal_plan dropped 2026-07-22 (WS4/D5, M33b §5 ratified DROP):
# dead write-only surface — USDA claims use federal-constant rates, the
# table was never read. Existing DBs cleaned by migration 002.



# ---------------------------------------------------------------------------
# Five indexes that existed ONLY in the retired DDL string, carried forward
# verbatim (founder ruling 2026-08-16: shipped surface is never dropped in a
# conversion; anything we retire gets named in a plan first). A naive extraction
# from core's metadata would have yielded 88 and lost these silently.
# ---------------------------------------------------------------------------
Index("idx_course_code_company", COURSE.c.code, COURSE.c.company_id)
Index("idx_section_term_year", SECTION.c.term, SECTION.c.year)
Index("idx_section_company_secstatus", SECTION.c.company_id, SECTION.c.section_status)
Index("idx_student_student_id", STUDENT.c.student_id)
Index("idx_student_program_id", STUDENT.c.program_id)


def ensure_educlaw_base_tables(db_path=None):
    """Create the shared base tables if they are not already present.

    Same contract as the retired version — idempotent, safe to call from any
    sub-vertical installer, cheap when the tables already exist — but it asks
    the seam what exists instead of reading the SQLite catalog directly, and
    provisions through metadata instead of a raw script exec. Those two lines
    were the whole reason five educlaw sub-verticals could not provision on
    PostgreSQL.

    Takes a db_path, not a connection: the seam owns connections, and the
    callers' old ``get_connection`` dance existed only to feed the retired
    script exec.
    """
    if table_exists(SENTINEL_TABLE, db_path):
        return {"created": False, "tables": 0, "indexes": 0}
    result = provision(BASE_METADATA, db_path)
    return {"created": True,
            "tables": result["tables"],
            "indexes": result["indexes"]}
