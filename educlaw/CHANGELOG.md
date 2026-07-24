# Changelog

All notable changes to the educlaw core module.

## [1.2.0] — 2026-07-23 — remove dead meal-plan surface (v4.13.0 stabilization)

### Removed
- **`edu-add-meal-plan` action and the `educlaw_meal_plan` table.** The table had a single writer and no reader: the USDA claim report always used the built-in federal reimbursement constants and never consulted a school-entered plan rate, and the schema shape (three plan types, one daily rate) could not feed the report's per-meal-type math anyway. A school-entered rate had zero effect on anything. Migration `002_drop_meal_plan.py` removes the table from existing databases (data-preserving for every other table, idempotent). Ratified drop per the M33b necessity dossier §5.

## [1.1.0] — 2026-07-05 — M33 Item 4 (B11 — educlaw program-requirement CRUD)

### Added
- **`edu-add-program-requirement`** — attach a course to a program's degree
  requirements (`educlaw_program_requirement`). Args: `--program-id`,
  `--course-id`, `--requirement-type` (`required|elective|core|major|
  general_education`), optional `--credit-category`, `--min-grade`,
  `--company-id`. Validates both FKs (program + course) up front for clear
  errors and honors the table's `UNIQUE(program_id, course_id)` with a clean
  "already a requirement" message. When `--company-id` is supplied it is
  verified against the parent program's company (the requirement row is
  scoped through its program; the table has no `company_id` column).
- **`edu-list-program-requirements`** — list a program's course requirements
  (by `--program-id`), joined to course code/name/credit-hours.

### Fixed
- **`edu-get-program` `requirements` array is no longer permanently empty.**
  The reader already JOIN-read `educlaw_program_requirement`, but the table
  had zero writers, so the documented "program with requirements" contract
  always returned `[]`. The new CRUD writer fills it. (Retires the
  `educlaw_program_requirement` orphan-allowlist entry.)
