# EduClaw LMS Integration — Implementation Plan

## 1. Product Overview

- **Product name:** educlaw-lms
- **Display name:** EduClaw LMS Integration
- **Version:** 1.0.0
- **Description:** LMS sync, assignments, course materials, and online gradebook. Bridges EduClaw's
  authoritative Student Information System with external Learning Management Systems (Canvas,
  Moodle, and Google Classroom). Solves the universal SIS-LMS data-silo problem affecting every
  school using digital assignment delivery.
- **Parent product:** educlaw (112 actions, 32 tables, 8 domains)
- **Parent path:** `educlaw`
- **Sub-vertical type:** Extends parent EduClaw SIS with first-ever external network calls.

### Target Domains and Scope

| Domain | Scope |
| --- | --- |
| `lms_sync` | LMS connection management, roster push (courses/users/enrollments), sync audit logging, conflict resolution |
| `assignments` | Push SIS assessments to LMS as assignments; pull LMS-created assignments back; bidirectional mapping |
| `online_gradebook` | Pull LMS grades into staging; conflict detection; grade application; OneRoster CSV export |
| `course_materials` | SIS-side course document/resource tracking (syllabus, readings, video links, LMS-linked files) |

### Foundation Dependencies

| Foundation Skill | Usage |
| --- | --- |
| `erpclaw-setup` | DB connection (`get_connection`), `company` table, `naming_series`, `audit` function |
| `erpclaw-gl` | GL accounts for institution (read-only from educlaw-lms; no new GL postings) |
| `erpclaw-selling` | `customer` table (students are customers; read-only) |
| `erpclaw-payments` | Payment tracking (read-only; not affected by LMS sync) |
| `erpclaw-hr` | `employee` table (instructors are employees; read email for LMS account creation) |

### Key Architectural Decisions

1. **External network calls** — educlaw-lms is the first EduClaw sub-vertical that makes HTTP calls to external APIs (Canvas REST, Moodle Web Services, Google Classroom API). All calls wrapped in retry logic (3 attempts, exponential backoff).
2. **Adapter pattern** — LMS-specific logic isolated in `scripts/adapters/canvas.py`, `moodle.py`, `google_classroom.py`, `oneroster_csv.py`. All adapters share a common interface.
3. **SIS is source of truth** — Roster always flows SIS→LMS. Grades flow LMS→SIS by default, but require explicit apply step for non-new grades. Submitted grades (`is_grade_submitted=1`) NEVER overwrite automatically.
4. **DPA hard gate** — `has_dpa_signed = 0` blocks ALL sync operations (not a warning — a hard error `E_DPA_REQUIRED`).
5. **COPPA hard gate** — Under-13 students cannot sync to LMS without `is_coppa_verified = 1` on the connection.
6. **Credential encryption** — OAuth secrets, tokens stored encrypted using `encrypt_field()` from `erpclaw_lib/crypto.py`. Env var: `EDUCLAW_LMS_ENCRYPTION_KEY`. Plaintext never in DB or logs.
7. **Sync runs are transactional** — Each sync creates an immutable `educlaw_lms_sync_log` entry. Partial sync results preserved (not rolled back) for targeted re-sync.
8. **Immutable audit tables** — `educlaw_lms_sync_log` and `educlaw_lms_grade_sync` have NO `updated_at` column. Append-only.

---

## 2. Domain Organization

| Domain | Module File | Scope |
| --- | --- | --- |
| `lms_sync` | `scripts/lms_sync.py` | LMS connection CRUD, test-connection, sync-courses (roster push), sync log read, conflict resolution |
| `assignments` | `scripts/assignments.py` | Push/pull assessment↔LMS assignment mapping, list-lms-assignments, unlink-lms-assignment, sync-assessment-update |
| `online_gradebook` | `scripts/online_gradebook.py` | pull-grades, get-online-gradebook, list-grade-conflicts, resolve-grade-conflict, export-oneroster-csv, close-lms-course |
| `course_materials` | `scripts/course_materials.py` | Course material CRUD (add/update/list/get/delete) |
| **Adapters** | `scripts/adapters/` | LMS-specific API calls (not directly action-callable; invoked by domain modules) |
| **Router** | `scripts/db_query.py` | Main entry point; dispatches `--action` to domain module |

### Adapter Sub-Module Structure

| Adapter File | LMS Platform | Authentication |
| --- | --- | --- |
| `scripts/adapters/canvas.py` | Canvas (Instructure) | OAuth 2.0 (client_id + client_secret) |
| `scripts/adapters/moodle.py` | Moodle (3.9+) | Web Service Token (site_token_encrypted) |
| `scripts/adapters/google_classroom.py` | Google Classroom | OAuth 2.0 (google_credentials_encrypted) |
| `scripts/adapters/oneroster_csv.py` | Any OneRoster-compliant LMS | N/A (file export) |
| `scripts/adapters/base.py` | Abstract interface | Defines: `sync_course`, `sync_user`, `sync_enrollment`, `push_assignment`, `pull_grades` |

---

## 3. Database Schema

### 3.1 Tables (New — educlaw-lms-Owned)

All new tables use prefix `educlaw_lms_`. IDs are TEXT (UUID). Timestamps TEXT (ISO 8601). Scores TEXT (Python Decimal). No direct monetary amounts in this domain.

---

#### `educlaw_lms_connection`

**Purpose:** Configuration record for a connected LMS platform. One record per LMS platform connected to the institution.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `naming_series` | TEXT | NOT NULL, UNIQUE | e.g., `LMS-00001` |
| `display_name` | TEXT | NOT NULL | Human label, e.g., "Jefferson High — Canvas" |
| `lms_type` | TEXT | NOT NULL | `canvas` / `moodle` / `google_classroom` / `oneroster_csv` |
| `endpoint_url` | TEXT | | Base URL of LMS instance (NULL for `oneroster_csv`) |
| `client_id` | TEXT | | OAuth 2.0 client_id (Canvas, Google) |
| `client_secret_encrypted` | TEXT | | AES-256 encrypted OAuth client_secret (Canvas) |
| `site_token_encrypted` | TEXT | | AES-256 encrypted web service token (Moodle) |
| `google_credentials_encrypted` | TEXT | | AES-256 encrypted service account JSON (Google) |
| `lms_site_name` | TEXT | | LMS site name (populated by `test-lms-connection`) |
| `lms_version` | TEXT | | LMS version string (populated by `test-lms-connection`) |
| `grade_direction` | TEXT | NOT NULL DEFAULT `'lms_to_sis'` | `lms_to_sis` / `sis_to_lms` / `manual` |
| `auto_sync_enabled` | INTEGER | NOT NULL DEFAULT 0 | Boolean: 0 = manual only; 1 = scheduled (v2) |
| `sync_frequency_hours` | INTEGER | | Hours between auto-syncs (only if `auto_sync_enabled=1`) |
| `last_sync_at` | TEXT | | ISO timestamp of last successful sync run |
| `default_course_prefix` | TEXT | | Optional prefix prepended to LMS course names |
| `auto_push_assignments` | INTEGER | NOT NULL DEFAULT 0 | Boolean: auto-push new `educlaw_assessment` to LMS |
| `has_dpa_signed` | INTEGER | NOT NULL DEFAULT 0 | **REQUIRED: 0 blocks all sync (hard gate)** |
| `dpa_signed_date` | TEXT | | ISO date DPA was signed |
| `is_coppa_verified` | INTEGER | NOT NULL DEFAULT 0 | LMS confirmed COPPA-compliant; required for under-13 sync |
| `coppa_cert_url` | TEXT | | URL to LMS COPPA certification document |
| `allowed_data_fields` | TEXT | | JSON: list of field names DPA permits to be synced |
| `status` | TEXT | NOT NULL DEFAULT `'draft'` | `draft` / `active` / `inactive` / `error` |
| `company_id` | TEXT | NOT NULL, FK → `company` | Institution owning this connection |
| `created_at` | TEXT | NOT NULL | ISO timestamp |
| `updated_at` | TEXT | NOT NULL | ISO timestamp |

**CHECK Constraints:**
- `CHECK(lms_type IN ('canvas','moodle','google_classroom','oneroster_csv'))`
- `CHECK(grade_direction IN ('lms_to_sis','sis_to_lms','manual'))`
- `CHECK(status IN ('draft','active','inactive','error'))`

**Indexes:**
- `idx_lms_connection_company_type_status` ON `(company_id, lms_type, status)`
- `idx_lms_connection_naming_series` UNIQUE ON `(naming_series)`

**Business Rules:**
- `has_dpa_signed = 0` → all sync actions return `E_DPA_REQUIRED` error; no data leaves the SIS
- `is_coppa_verified = 0` → sync skips any student with `educlaw_student.is_coppa_applicable = 1`; logs `E_COPPA_UNVERIFIED` per skipped student
- Credential fields store only ciphertext; decryption at runtime via `decrypt_field()` with `EDUCLAW_LMS_ENCRYPTION_KEY` env var
- Status lifecycle: `draft` → `active` (after `test-lms-connection` succeeds + DPA signed) → `inactive` (manually disabled) → `error` (last API call failed)

---

#### `educlaw_lms_course_mapping`

**Purpose:** Cross-reference between EduClaw course sections and LMS courses/classes. One record per section-per-connection.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `lms_connection_id` | TEXT | NOT NULL, FK → `educlaw_lms_connection` | Which LMS connection |
| `section_id` | TEXT | NOT NULL, FK → `educlaw_section` | EduClaw course section |
| `lms_course_id` | TEXT | NOT NULL | External LMS course or class ID |
| `lms_course_url` | TEXT | | Web URL to the LMS course (for deep linking) |
| `lms_term_id` | TEXT | | External LMS term/session ID (created during term sync) |
| `sync_status` | TEXT | NOT NULL DEFAULT `'pending'` | `pending` / `synced` / `error` / `closed` |
| `last_synced_at` | TEXT | | ISO timestamp of last successful sync |
| `sync_error` | TEXT | | Last error message (if `sync_status = 'error'`) |
| `created_at` | TEXT | NOT NULL | ISO timestamp (no `updated_at` — create new record for remapping) |

**CHECK Constraints:**
- `CHECK(sync_status IN ('pending','synced','error','closed'))`

**Indexes:**
- `idx_lms_course_map_conn_section` UNIQUE ON `(lms_connection_id, section_id)` — one section per connection
- `idx_lms_course_map_course_conn` UNIQUE ON `(lms_course_id, lms_connection_id)` — one LMS course per connection

**Business Rules:**
- No `updated_at` — if a section requires remapping, close the existing record (`sync_status = 'closed'`) and create a new one
- `sync_status = 'closed'` after `close-lms-course` is called (post grade submission); no further grade pulls
- The UNIQUE constraint on `(lms_connection_id, section_id)` enforces one LMS course per section per connection

---

#### `educlaw_lms_user_mapping`

**Purpose:** Cross-reference between EduClaw students/instructors and LMS user accounts.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `lms_connection_id` | TEXT | NOT NULL, FK → `educlaw_lms_connection` | Which LMS connection |
| `sis_user_type` | TEXT | NOT NULL | `student` / `instructor` |
| `sis_user_id` | TEXT | NOT NULL | FK → `educlaw_student.id` OR `educlaw_instructor.id` depending on `sis_user_type` |
| `lms_user_id` | TEXT | NOT NULL | External LMS user ID |
| `lms_username` | TEXT | | LMS login identifier (e.g., email prefix) |
| `lms_login_email` | TEXT | | Email used for LMS account creation/login |
| `is_coppa_restricted` | INTEGER | NOT NULL DEFAULT 0 | 1 if student has COPPA restrictions (`is_coppa_applicable = 1`) |
| `is_directory_restricted` | INTEGER | NOT NULL DEFAULT 0 | 1 if `educlaw_student.directory_info_opt_out = 1` |
| `sync_status` | TEXT | NOT NULL DEFAULT `'synced'` | `synced` / `pending` / `error` / `invited` (Google Classroom pending acceptance) |
| `last_synced_at` | TEXT | | ISO timestamp |
| `sync_error` | TEXT | | Last error message |
| `created_at` | TEXT | NOT NULL | ISO timestamp |

**CHECK Constraints:**
- `CHECK(sis_user_type IN ('student','instructor'))`
- `CHECK(sync_status IN ('synced','pending','error','invited'))`

**Indexes:**
- `idx_lms_user_map_conn_type_user` UNIQUE ON `(lms_connection_id, sis_user_type, sis_user_id)`
- `idx_lms_user_map_lms_user_conn` UNIQUE ON `(lms_user_id, lms_connection_id)`
- `idx_lms_user_map_sync_status` ON `(lms_connection_id, sync_status)`

**Business Rules:**
- Google Classroom enrollments use invitation flow; `sync_status = 'invited'` until student accepts
- `is_coppa_restricted = 1` → LMS must be configured to hide student from public class directory features
- `is_directory_restricted = 1` → restrict LMS display of student name in any class-list features
- The UNIQUE constraint prevents a student from mapping to two different LMS users on the same connection

---

#### `educlaw_lms_assignment_mapping`

**Purpose:** Cross-reference between EduClaw assessments and LMS assignments/line items.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `lms_connection_id` | TEXT | NOT NULL, FK → `educlaw_lms_connection` | Which LMS connection |
| `assessment_id` | TEXT | NOT NULL, FK → `educlaw_assessment` | EduClaw assessment |
| `lms_assignment_id` | TEXT | NOT NULL | External LMS assignment, activity, or line item ID |
| `lms_assignment_url` | TEXT | | Web URL to the LMS assignment page |
| `lms_grade_scheme` | TEXT | | LMS grading scheme: `points` / `percentage` / `pass_fail` / `letter_grade` |
| `push_direction` | TEXT | NOT NULL DEFAULT `'sis_to_lms'` | `sis_to_lms` (SIS created, pushed out) / `lms_to_sis` (LMS created, imported) |
| `is_published_in_lms` | INTEGER | NOT NULL DEFAULT 0 | Whether the assignment is visible to students in LMS |
| `sync_status` | TEXT | NOT NULL DEFAULT `'synced'` | `synced` / `pending` / `error` |
| `last_synced_at` | TEXT | | ISO timestamp |
| `sync_error` | TEXT | | Last error message |
| `created_at` | TEXT | NOT NULL | ISO timestamp |

**CHECK Constraints:**
- `CHECK(push_direction IN ('sis_to_lms','lms_to_sis'))`
- `CHECK(sync_status IN ('synced','pending','error'))`
- `CHECK(lms_grade_scheme IN ('points','percentage','pass_fail','letter_grade') OR lms_grade_scheme IS NULL)`

**Indexes:**
- `idx_lms_assign_map_conn_assess` UNIQUE ON `(lms_connection_id, assessment_id)`
- `idx_lms_assign_map_lms_assign_conn` UNIQUE ON `(lms_assignment_id, lms_connection_id)`
- `idx_lms_assign_map_sync_status` ON `(lms_connection_id, sync_status)`

---

#### `educlaw_lms_sync_log`

**Purpose:** Immutable audit trail for every sync operation run. One record per sync run.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `naming_series` | TEXT | NOT NULL, UNIQUE | e.g., `SYN-2026-00001` |
| `lms_connection_id` | TEXT | NOT NULL, FK → `educlaw_lms_connection` | Which LMS connection |
| `sync_type` | TEXT | NOT NULL | `roster_push` / `grade_pull` / `assignment_push` / `full_sync` / `oneroster_export` |
| `academic_term_id` | TEXT | FK → `educlaw_academic_term` | Which term was synced (NULL if not term-scoped) |
| `section_id` | TEXT | FK → `educlaw_section` | Specific section synced (NULL for term-wide or full_sync) |
| `triggered_by` | TEXT | | User ID who triggered; `'scheduler'` for auto-sync |
| `status` | TEXT | NOT NULL DEFAULT `'pending'` | `pending` / `running` / `completed` / `completed_with_errors` / `failed` |
| `sections_synced` | INTEGER | NOT NULL DEFAULT 0 | Count of sections processed in this run |
| `students_synced` | INTEGER | NOT NULL DEFAULT 0 | Count of student records processed |
| `grades_pulled` | INTEGER | NOT NULL DEFAULT 0 | Count of grade records pulled from LMS |
| `grades_applied` | INTEGER | NOT NULL DEFAULT 0 | Count of grades written to `educlaw_assessment_result` |
| `conflicts_flagged` | INTEGER | NOT NULL DEFAULT 0 | Count of grade conflicts staged in `educlaw_lms_grade_sync` |
| `errors_count` | INTEGER | NOT NULL DEFAULT 0 | Count of individual records that failed |
| `error_summary` | TEXT | | JSON array of error objects: `[{entity_type, entity_id, error_message}]` |
| `started_at` | TEXT | | ISO timestamp when sync began |
| `completed_at` | TEXT | | ISO timestamp when sync finished |
| `duration_seconds` | INTEGER | | Wall-clock sync duration |
| `company_id` | TEXT | NOT NULL, FK → `company` | Institution context |
| `created_at` | TEXT | NOT NULL | ISO timestamp (**NO `updated_at` — immutable**) |

**CHECK Constraints:**
- `CHECK(status IN ('pending','running','completed','completed_with_errors','failed'))`
- `CHECK(sync_type IN ('roster_push','grade_pull','assignment_push','full_sync','oneroster_export'))`

**Indexes:**
- `idx_lms_sync_log_conn_status` ON `(lms_connection_id, status)`
- `idx_lms_sync_log_term_type` ON `(academic_term_id, sync_type)`
- `idx_lms_sync_log_company_created` ON `(company_id, created_at)`
- `idx_lms_sync_log_naming_series` UNIQUE ON `(naming_series)`

**Business Rules:**
- Never modify a sync log record — immutable once written
- If a sync run is detected already `running` for the same connection, second run aborts with message
- `completed_with_errors` = some records succeeded, some failed — enables targeted re-sync
- `failed` = critical error; zero records processed

---

#### `educlaw_lms_grade_sync`

**Purpose:** Staging table for grades pulled from LMS. Immutable pull records. Grades are NOT written to `educlaw_assessment_result` until explicitly applied.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `lms_connection_id` | TEXT | NOT NULL, FK → `educlaw_lms_connection` | Which LMS connection |
| `sync_log_id` | TEXT | NOT NULL, FK → `educlaw_lms_sync_log` | Which sync run produced this |
| `lms_assignment_id` | TEXT | NOT NULL | External LMS assignment ID |
| `lms_user_id` | TEXT | NOT NULL | External LMS user ID |
| `assessment_id` | TEXT | FK → `educlaw_assessment` | Resolved from `educlaw_lms_assignment_mapping`; NULL if unmapped |
| `student_id` | TEXT | FK → `educlaw_student` | Resolved from `educlaw_lms_user_mapping`; NULL if unmapped |
| `assessment_result_id` | TEXT | FK → `educlaw_assessment_result` | NULL until applied (after `resolve-grade-conflict` or auto-apply) |
| `lms_score` | TEXT | | Raw score from LMS as TEXT (Python Decimal for precision) |
| `lms_grade` | TEXT | | Letter grade from LMS (if LMS grading scheme uses letters) |
| `lms_submitted_at` | TEXT | | ISO timestamp when student submitted in LMS |
| `lms_graded_at` | TEXT | | ISO timestamp when instructor graded in LMS |
| `is_late` | INTEGER | NOT NULL DEFAULT 0 | 1 if LMS reported submission as late |
| `is_missing` | INTEGER | NOT NULL DEFAULT 0 | 1 if LMS reported assignment as missing (not submitted) |
| `lms_comments` | TEXT | | Instructor feedback text from LMS |
| `sis_score` | TEXT | | `educlaw_assessment_result.points_earned` at time of pull (for conflict detection) |
| `is_conflict` | INTEGER | NOT NULL DEFAULT 0 | 1 if `lms_score ≠ sis_score` (or SIS score is missing when LMS has one) |
| `conflict_type` | TEXT | | `score_mismatch` / `submitted_grade_locked` / `student_not_found` / `assignment_not_found` |
| `sync_status` | TEXT | NOT NULL DEFAULT `'pulled'` | `pulled` / `applied` / `conflict` / `skipped` / `error` |
| `resolved_by` | TEXT | | User ID who resolved the conflict |
| `resolved_at` | TEXT | | ISO timestamp of conflict resolution |
| `resolution` | TEXT | | `lms_wins` / `sis_wins` / `manual` |
| `created_at` | TEXT | NOT NULL | ISO timestamp (**NO `updated_at` — immutable pull record**) |

**CHECK Constraints:**
- `CHECK(sync_status IN ('pulled','applied','conflict','skipped','error'))`
- `CHECK(conflict_type IN ('score_mismatch','submitted_grade_locked','student_not_found','assignment_not_found') OR conflict_type IS NULL)`
- `CHECK(resolution IN ('lms_wins','sis_wins','manual') OR resolution IS NULL)`

**Indexes:**
- `idx_lms_grade_sync_conn_assess_student` ON `(lms_connection_id, assessment_id, student_id)`
- `idx_lms_grade_sync_status_conflict` ON `(sync_status, is_conflict)`
- `idx_lms_grade_sync_assess_student_log` ON `(assessment_id, student_id, sync_log_id)`
- `idx_lms_grade_sync_student_status` ON `(student_id, sync_status)`
- `idx_lms_grade_sync_log` ON `(sync_log_id)`

**Business Rules:**
- Immutable records — never update a pulled grade record
- `conflict_type = 'submitted_grade_locked'` → `educlaw_course_enrollment.is_grade_submitted = 1`; must use parent's `update-grade` amendment workflow to change
- `sync_status = 'applied'` → `assessment_result_id` must be populated
- When `grade_direction = 'lms_to_sis'` and no existing SIS score → `sync_status = 'pulled'` and auto-apply creates a new `educlaw_assessment_result` record
- When `grade_direction = 'manual'` → all pulled grades remain `'pulled'` pending admin review

---

#### `educlaw_lms_course_material`

**Purpose:** Course documents, resource links, and LMS-linked files tracked within the SIS.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID |
| `section_id` | TEXT | NOT NULL, FK → `educlaw_section` | Which course section this material belongs to |
| `assessment_id` | TEXT | FK → `educlaw_assessment` | NULL for general course materials; populated for assignment-specific guides |
| `name` | TEXT | NOT NULL | e.g., "Week 3 Reading: Chapter 5", "Course Syllabus" |
| `description` | TEXT | | Additional context or notes |
| `material_type` | TEXT | NOT NULL | `syllabus` / `reading` / `video_link` / `assignment_guide` / `rubric` / `other` |
| `access_type` | TEXT | NOT NULL | `url` / `file_attachment` / `lms_linked` |
| `external_url` | TEXT | | For `access_type = 'url'`: external website or video URL |
| `file_path` | TEXT | | For `access_type = 'file_attachment'`: local file path relative to data directory |
| `lms_connection_id` | TEXT | FK → `educlaw_lms_connection` | For `access_type = 'lms_linked'`: which LMS holds the file |
| `lms_file_id` | TEXT | | LMS-side file identifier (populated when pushed to LMS) |
| `lms_download_url` | TEXT | | LMS-side download or view URL |
| `is_visible_to_students` | INTEGER | NOT NULL DEFAULT 1 | Boolean: 1 = visible; 0 = instructor-only |
| `available_from` | TEXT | | ISO date: when to start showing to students (NULL = immediately) |
| `available_until` | TEXT | | ISO date: when to stop showing to students (NULL = no end date) |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | Display ordering within section (lower = first) |
| `status` | TEXT | NOT NULL DEFAULT `'active'` | `active` / `archived` |
| `company_id` | TEXT | NOT NULL, FK → `company` | Institution context |
| `created_at` | TEXT | NOT NULL | ISO timestamp |
| `updated_at` | TEXT | NOT NULL | ISO timestamp |

**CHECK Constraints:**
- `CHECK(material_type IN ('syllabus','reading','video_link','assignment_guide','rubric','other'))`
- `CHECK(access_type IN ('url','file_attachment','lms_linked'))`
- `CHECK(status IN ('active','archived'))`

**Indexes:**
- `idx_lms_material_section_order` ON `(section_id, sort_order)`
- `idx_lms_material_section_type` ON `(section_id, material_type)`
- `idx_lms_material_assessment` ON `(assessment_id)`
- `idx_lms_material_company_status` ON `(company_id, status)`
- `idx_lms_material_lms_conn` ON `(lms_connection_id)` WHERE `lms_connection_id IS NOT NULL`

---

### 3.2 Tables (Inherited from Parent — Read or Reference Only)

educlaw-lms does NOT modify parent table schemas. All reads are via shared SQLite connection using parameterized queries.

| Parent Table | How educlaw-lms Uses It |
| --- | --- |
| `educlaw_student` | **Read:** `id`, `full_name` (first+last), `email` via customer FK, `is_coppa_applicable`, `directory_info_opt_out`, `current_program_id`, `grade_level` for LMS user sync |
| `educlaw_instructor` | **Read:** `id`, `employee_id` for email lookup (via `employee.work_email`), for LMS teacher account |
| `educlaw_course` | **Read:** `course_code`, `name`, `description`, `credit_hours` for LMS course creation |
| `educlaw_section` | **Read:** `id`, `course_id`, `academic_term_id`, `instructor_id`, `section_number`, `status` for sync scope |
| `educlaw_course_enrollment` | **Read:** `student_id`, `section_id`, `status`, `is_grade_submitted` for roster push and grade lock check |
| `educlaw_academic_term` | **Read:** `name`, `start_date`, `end_date`, `status` for LMS academic session creation |
| `educlaw_assessment` | **Read:** `id`, `name`, `max_points`, `due_date`, `is_published`, `assessment_plan_id` for LMS assignment creation |
| `educlaw_assessment_result` | **Read** for conflict check: `points_earned`, `is_exempt`, `comments`. **Write** (new records only) when grade_direction = `lms_to_sis` and no existing grade: insert new result row. Never update existing rows directly — route through parent `update-grade` for amendments |
| `educlaw_assessment_plan` | **Read:** `section_id` to resolve section from assessment |
| `educlaw_grading_scale` | **Read:** grading scale for LMS grade scheme configuration |
| `educlaw_data_access_log` | **Write:** Every roster push logs `access_type = 'disclosure'`; every grade pull logs `access_type = 'pull'`. New `access_type` values: `disclosure`, `pull` (extending parent's `view`, `export`, `print`) |
| `educlaw_consent_record` | **Read:** Check `consent_type = 'ferpa_disclosure'` before LMS push |
| `company` | **Read:** Institution name, company_id for all scoping |
| `employee` | **Read:** `work_email` to get instructor email for LMS account creation |

---

### 3.3 Lookup/Reference Tables

No new lookup/reference tables. The `lms_type` values (`canvas`, `moodle`, `google_classroom`, `oneroster_csv`) are enforced via CHECK constraints on `educlaw_lms_connection.lms_type`. No separate seed data table needed.

---

## 4. Action List

### 4.1 Actions by Domain

#### LMS Sync Domain — `scripts/lms_sync.py` (9 actions)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-lms-connection` | Create | Create a new LMS connection in `draft` status. Validates lms_type, grade_direction. Encrypts credential fields before storage. Does NOT trigger API call. | `educlaw_lms_connection` (INSERT) |
| `update-lms-connection` | Update | Update connection settings (display_name, grade_direction, DPA fields, credentials). Re-encrypts credentials if provided. Cannot update a `closed` connection. | `educlaw_lms_connection` (UPDATE) |
| `get-lms-connection` | Read | Get full connection details. Decrypts and masks credentials (returns last 4 chars only). Shows last_sync_at and status. | `educlaw_lms_connection` (SELECT) |
| `list-lms-connections` | Query | List all connections for company. Filters: `--lms-type`, `--connection-status`. Returns id, display_name, lms_type, status, last_sync_at, has_dpa_signed, is_coppa_verified. | `educlaw_lms_connection` (SELECT) |
| `test-lms-connection` | Action | Make a test API call to validate credentials. On success: update `lms_version`, `lms_site_name`, set `status = 'active'`. On failure: set `status = 'error'`, return error message. Enforces DPA check before activating. | `educlaw_lms_connection` (UPDATE) |
| `sync-courses` | Action | Full roster push for an academic term. Steps: (1) sync academic session, (2) sync course sections as LMS courses, (3) sync students+instructors as LMS users, (4) sync enrollments. Creates `educlaw_lms_sync_log` at start. Writes FERPA disclosure log per student pushed. | `educlaw_lms_sync_log` (INSERT), `educlaw_lms_course_mapping` (INSERT/UPDATE), `educlaw_lms_user_mapping` (INSERT/UPDATE), `educlaw_data_access_log` (INSERT) |
| `list-sync-logs` | Query | List sync run history for a connection. Filters: `--connection-id`, `--sync-type`, `--sync-status`, `--from-date`, `--to-date`. Returns summary stats per run. | `educlaw_lms_sync_log` (SELECT) |
| `get-sync-log` | Read | Get full sync run details including `error_summary` JSON. Shows per-entity errors. | `educlaw_lms_sync_log` (SELECT) |
| `resolve-sync-conflict` | Action | Resolve a user mapping or enrollment conflict. Resolution options: `sis_wins` (re-push SIS data), `lms_wins` (accept LMS state), `dismiss` (mark as reviewed). Updates `educlaw_lms_user_mapping.sync_status`. | `educlaw_lms_user_mapping` (UPDATE), `educlaw_lms_course_mapping` (UPDATE) |

**Key Parameters:**

`add-lms-connection`: `--lms-type REQUIRED --display-name REQUIRED --endpoint-url --client-id --client-secret --site-token --google-credentials --grade-direction --has-dpa-signed --dpa-signed-date --is-coppa-verified --coppa-cert-url --company-id REQUIRED`

`test-lms-connection`: `--connection-id REQUIRED`

`sync-courses`: `--connection-id REQUIRED --academic-term-id REQUIRED --company-id REQUIRED [--section-id for partial sync]`

`resolve-sync-conflict`: `--connection-id REQUIRED --entity-type REQUIRED (user|course) --entity-id REQUIRED --resolution REQUIRED (sis_wins|lms_wins|dismiss)`

---

#### Assignments Domain — `scripts/assignments.py` (5 actions)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `push-assessment-to-lms` | Action | Push a SIS assessment to LMS as an assignment. Looks up `lms_course_mapping` for the section (via `assessment_plan_id → section_id`). Builds LMS payload (name, points_possible, due_at, grading_type, published). Creates `educlaw_lms_assignment_mapping`. Logs FERPA disclosure (academics category). | `educlaw_lms_assignment_mapping` (INSERT), `educlaw_lms_sync_log` (INSERT), `educlaw_data_access_log` (INSERT) |
| `pull-lms-assignments` | Action | Pull all assignments from an LMS course that are NOT yet mapped in EduClaw. For each unmapped LMS assignment: creates a stub `educlaw_assessment` (if `--create-assessments` flag) OR creates `educlaw_lms_assignment_mapping` with `push_direction = 'lms_to_sis'`. Used when instructor created assignment in LMS first. | `educlaw_lms_assignment_mapping` (INSERT), optionally `educlaw_assessment` (INSERT) |
| `sync-assessment-update` | Action | Push updated assessment fields to LMS. Detects if name, max_points, due_date, or is_published changed vs. last push. Calls LMS update assignment API. Warns if max_points changed (existing grades will recalculate in LMS). Updates `last_synced_at`. | `educlaw_lms_assignment_mapping` (UPDATE) |
| `list-lms-assignments` | Query | List assessments that have LMS mappings for a section. Shows SIS assessment details + LMS assignment URL, `is_published_in_lms`, `sync_status`, `last_synced_at`. Filters: `--connection-id`, `--section-id`, `--sync-status`. | `educlaw_lms_assignment_mapping` (SELECT), `educlaw_assessment` (SELECT), `educlaw_assessment_plan` (SELECT) |
| `unlink-lms-assignment` | Action | Remove the LMS assignment mapping. Sets `sync_status = 'error'` with note "unlinked by user". Does NOT delete the LMS assignment itself. Future grade pulls for this assessment will skip it. | `educlaw_lms_assignment_mapping` (DELETE — soft delete by status update) |

**Key Parameters:**

`push-assessment-to-lms`: `--assessment-id REQUIRED --connection-id REQUIRED [--section-id for override]`

`pull-lms-assignments`: `--connection-id REQUIRED --section-id REQUIRED [--create-assessments flag --plan-id --category-id]`

`sync-assessment-update`: `--assessment-id REQUIRED --connection-id REQUIRED`

`list-lms-assignments`: `--connection-id REQUIRED [--section-id --sync-status]`

`unlink-lms-assignment`: `--assessment-id REQUIRED --connection-id REQUIRED`

---

#### Online Gradebook Domain — `scripts/online_gradebook.py` (6 actions)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `pull-grades` | Action | Pull LMS submission scores into `educlaw_lms_grade_sync` staging. For each assignment mapping: calls LMS grades API, maps `lms_user_id → student_id`, compares to existing `educlaw_assessment_result`. Creates grade_sync records as `pulled`, `conflict`, or `skipped` (if grade_direction = sis_to_lms). Auto-applies new grades if `grade_direction = 'lms_to_sis'` and no existing SIS result. Logs FERPA `pull` per student. | `educlaw_lms_grade_sync` (INSERT), `educlaw_lms_sync_log` (INSERT), `educlaw_assessment_result` (INSERT for new grades only), `educlaw_data_access_log` (INSERT) |
| `get-online-gradebook` | Query | Return unified gradebook for a section showing both SIS and LMS grades. Student rows × Assessment columns. Each cell: SIS `points_earned`, LMS `lms_score`, `is_conflict` flag, `lms_assignment_url`. Includes row summary: weighted grade, letter grade. | `educlaw_assessment_result` (SELECT), `educlaw_lms_grade_sync` (SELECT), `educlaw_lms_assignment_mapping` (SELECT), `educlaw_assessment` (SELECT) |
| `list-grade-conflicts` | Query | List all unresolved grade conflicts for review. Filters: `--connection-id`, `--section-id`, `--conflict-type`, `--status` (pulled/conflict/applied). Returns student name, assessment name, SIS score, LMS score, `is_grade_submitted` flag. | `educlaw_lms_grade_sync` (SELECT), `educlaw_student` (SELECT), `educlaw_assessment` (SELECT) |
| `resolve-grade-conflict` | Action | Resolve a grade conflict. Options: `lms_wins` (apply LMS score to SIS), `sis_wins` (dismiss; optionally push SIS score back to LMS), `manual` (admin enters new score). For `lms_wins` on submitted grade: route through parent `update-grade` amendment workflow. Updates `grade_sync.resolved_by`, `resolved_at`, `resolution`, `sync_status = 'applied'` or `'skipped'`. | `educlaw_lms_grade_sync` (UPDATE — resolution fields only), `educlaw_assessment_result` (INSERT or UPDATE depending on submitted status) |
| `export-oneroster-csv` | Action | Generate OneRoster 1.1 CSV package for a term. Produces 8 CSV files: `orgs.csv`, `academicSessions.csv`, `courses.csv`, `classes.csv`, `users.csv`, `enrollments.csv`, `lineItems.csv` (if `--include-grades`), `results.csv` (if `--include-grades`). Validates cross-references. Zips all files. Logs export as `oneroster_export` in `educlaw_lms_sync_log`. | `educlaw_lms_sync_log` (INSERT), reads from parent tables (SELECT only) |
| `close-lms-course` | Action | Mark a course's LMS mapping as `closed` after grades are submitted. Triggered manually or called by parent's `submit-grades` hook. Sets `educlaw_lms_course_mapping.sync_status = 'closed'`. Prevents further grade pulls for this section. Logs closure in sync_log. | `educlaw_lms_course_mapping` (UPDATE), `educlaw_lms_sync_log` (INSERT) |

**Key Parameters:**

`pull-grades`: `--connection-id REQUIRED --section-id [--assessment-id for single assignment --academic-term-id for bulk]`

`get-online-gradebook`: `--section-id REQUIRED --connection-id REQUIRED`

`list-grade-conflicts`: `--connection-id REQUIRED [--section-id --conflict-type --conflict-status]`

`resolve-grade-conflict`: `--grade-sync-id REQUIRED --resolution REQUIRED (lms_wins|sis_wins|manual) --resolved-by REQUIRED [--new-score for manual --push-to-lms for sis_wins]`

`export-oneroster-csv`: `--academic-term-id REQUIRED --output-dir REQUIRED --company-id REQUIRED [--include-grades flag]`

`close-lms-course`: `--section-id REQUIRED --connection-id REQUIRED`

---

#### Course Materials Domain — `scripts/course_materials.py` (5 actions)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-course-material` | Create | Create a course material record for a section. Validates that `section_id` exists and is active. For `access_type = 'lms_linked'`: fetches file metadata from LMS and stores `lms_file_id`, `lms_download_url`. Validates date range if both `available_from` and `available_until` provided. | `educlaw_lms_course_material` (INSERT) |
| `update-course-material` | Update | Update material metadata: name, description, access_type, external_url, file_path, is_visible_to_students, available_from, available_until, sort_order. Cannot change section_id. | `educlaw_lms_course_material` (UPDATE) |
| `list-course-materials` | Query | List materials for a section. Filters: `--section-id REQUIRED`, `--material-type`, `--is-visible-to-students`, `--include-archived`. Ordered by `sort_order` ASC. | `educlaw_lms_course_material` (SELECT) |
| `get-course-material` | Read | Get full material record including LMS link details (`lms_file_id`, `lms_download_url`, `lms_connection_id`). | `educlaw_lms_course_material` (SELECT) |
| `delete-course-material` | Archive | Set `status = 'archived'`. Does not delete the row. Archived materials excluded from `list-course-materials` by default. | `educlaw_lms_course_material` (UPDATE) |

**Key Parameters:**

`add-course-material`: `--section-id REQUIRED --name REQUIRED --material-type REQUIRED --access-type REQUIRED [--external-url --file-path --lms-connection-id --is-visible-to-students --available-from --available-until --sort-order --assessment-id --company-id REQUIRED]`

`update-course-material`: `--material-id REQUIRED [updatable fields]`

`list-course-materials`: `--section-id REQUIRED [--material-type --is-visible-to-students --include-archived]`

`get-course-material`: `--material-id REQUIRED`

`delete-course-material`: `--material-id REQUIRED`

---

### 4.2 Cross-Domain Actions

| Action | Domains Involved | Description |
| --- | --- | --- |
| `sync-courses` | lms_sync + parent (read sections, students, enrollments, terms) | Reads from 5 parent tables; writes to 3 lms tables + FERPA log |
| `pull-grades` | online_gradebook + parent (read assessments, write assessment_result) | Reads parent assessment data; conditionally writes new parent assessment_result rows |
| `export-oneroster-csv` | online_gradebook + parent (read all entities) | Reads from ~8 parent tables to produce standard CSV output |
| `resolve-grade-conflict` | online_gradebook + parent (write assessment_result) | May call parent `update-grade` for submitted grades |
| `push-assessment-to-lms` | assignments + lms_sync (needs course_mapping) | Requires lms_course_mapping for the section to exist before pushing assignment |
| `close-lms-course` | online_gradebook + lms_sync (updates course_mapping) | Called after parent `submit-grades` closes the section's LMS sync |

---

### 4.3 Naming Conflict Check

**Verification against parent educlaw actions (112 actions):**

| educlaw-lms Action | Conflict with Parent? | Notes |
| --- | --- | --- |
| `add-lms-connection` | ✅ No conflict | `add-lms-connection` is unique to this sub-vertical |
| `update-lms-connection` | ✅ No conflict | |
| `get-lms-connection` | ✅ No conflict | |
| `list-lms-connections` | ✅ No conflict | |
| `test-lms-connection` | ✅ No conflict | |
| `sync-courses` | ✅ No conflict | Parent has `add-course`, `list-courses` — `sync-courses` is distinct |
| `list-sync-logs` | ✅ No conflict | |
| `get-sync-log` | ✅ No conflict | |
| `resolve-sync-conflict` | ✅ No conflict | |
| `push-assessment-to-lms` | ✅ No conflict | Parent has `add-assessment`, `update-assessment` — clearly distinct |
| `pull-lms-assignments` | ✅ No conflict | |
| `sync-assessment-update` | ✅ No conflict | |
| `list-lms-assignments` | ✅ No conflict | Parent has `list-assessments` — `list-lms-assignments` is distinct |
| `unlink-lms-assignment` | ✅ No conflict | |
| `pull-grades` | ✅ No conflict | Parent has `list-grades`, `record-assessment-result` — `pull-grades` is distinct |
| `get-online-gradebook` | ✅ No conflict | |
| `list-grade-conflicts` | ✅ No conflict | |
| `resolve-grade-conflict` | ✅ No conflict | |
| `export-oneroster-csv` | ✅ No conflict | |
| `close-lms-course` | ✅ No conflict | Parent has `cancel-section` (different: removes section) — `close-lms-course` closes the LMS mapping only |
| `add-course-material` | ✅ No conflict | |
| `update-course-material` | ✅ No conflict | |
| `list-course-materials` | ✅ No conflict | |
| `get-course-material` | ✅ No conflict | |
| `delete-course-material` | ✅ No conflict | Parent has no "delete" actions; this is archive/soft-delete |

**Result: ZERO naming conflicts with parent educlaw or ERPClaw foundation skills.**

**Verification against table names:**
All 7 new tables use prefix `educlaw_lms_*`. Parent uses `educlaw_*` (without `lms_`). Foundation uses `company`, `employee`, `account`, etc. — no overlap.

**Result: ZERO table naming conflicts.**

---

## 5. Workflows

### 5.1 Workflow: Configure and Activate LMS Connection

**Trigger:** Admin wants to connect EduClaw to an LMS.

| Step | Action | Description |
| --- | --- | --- |
| 1 | `add-lms-connection` | Create connection in `draft` with credentials and settings |
| 2 | Verify DPA | Admin confirms DPA is signed (`has_dpa_signed = 1`, `dpa_signed_date`) |
| 3 | `test-lms-connection` | API test call; populates `lms_version`/`lms_site_name`; sets `status = 'active'` |

**GL/SLE implications:** None. No financial transactions in this domain.

**Outcome:** `educlaw_lms_connection` in `active` status; ready for sync operations.

---

### 5.2 Workflow: Term Start — Roster Push

**Trigger:** New academic term begins; admin initiates sync to push all sections and students to LMS.

| Step | Action | Description |
| --- | --- | --- |
| 1 | `sync-courses` | Create `educlaw_lms_sync_log` (status: running) |
| 2 | *(internal)* | Check `has_dpa_signed`; abort if 0 (`E_DPA_REQUIRED`) |
| 3 | *(internal)* | Sync academic session: create/update term in LMS; store `lms_term_id` |
| 4 | *(internal)* | For each section: create LMS course; insert `educlaw_lms_course_mapping` |
| 5 | *(internal)* | For each student: COPPA check; directory opt-out check; create/match LMS user; insert `educlaw_lms_user_mapping`; write FERPA disclosure to `educlaw_data_access_log` |
| 6 | *(internal)* | For each instructor: create/match LMS teacher user; insert `educlaw_lms_user_mapping` |
| 7 | *(internal)* | For each `educlaw_course_enrollment` (status=enrolled): create LMS enrollment; handle Google Classroom `invited` state |
| 8 | *(internal)* | Update `educlaw_lms_sync_log` with counts, errors, `completed_at` |

**GL/SLE implications:** None.

**FERPA implications:** Every student pushed to LMS creates one `educlaw_data_access_log` entry with `access_type = 'disclosure'`, `data_category = 'demographics,enrollment'`.

**Outcome:** All sections mirrored in LMS; all enrolled students have LMS user accounts and enrollments.

---

### 5.3 Workflow: Assignment Push

**Trigger:** Instructor creates assessment in EduClaw (or manually triggers push).

| Step | Action | Description |
| --- | --- | --- |
| 1 | Parent: `add-assessment` | Creates `educlaw_assessment` record (not changed) |
| 2 | `push-assessment-to-lms` | Looks up `lms_course_mapping` for section; builds LMS payload; creates LMS assignment; inserts `educlaw_lms_assignment_mapping` |
| 3 | *(auto if `auto_push_assignments = 1`)* | Automatic trigger on parent `add-assessment` |

**GL/SLE implications:** None.

**FERPA implications:** Assignment push logs `access_type = 'disclosure'`, `data_category = 'academics'`.

**Outcome:** `educlaw_assessment` has a corresponding LMS assignment; `educlaw_lms_assignment_mapping` records the link.

---

### 5.4 Workflow: Grade Pull and Conflict Resolution

**Trigger:** Instructor has graded assignments in LMS; admin triggers grade pull to bring scores into EduClaw.

| Step | Action | Description |
| --- | --- | --- |
| 1 | `pull-grades` | Create `educlaw_lms_sync_log` (type: grade_pull). For each `lms_assignment_mapping`: call LMS grades API; map `lms_user_id → student_id`; compare to `educlaw_assessment_result` |
| 2 | *(internal)* | New grade (no SIS result): if `grade_direction = 'lms_to_sis'`, insert `educlaw_assessment_result`; set `grade_sync.sync_status = 'applied'` |
| 3 | *(internal)* | Grade matches SIS: set `grade_sync.sync_status = 'skipped'` (no action) |
| 4 | *(internal)* | Grade conflicts: if `is_grade_submitted = 1` → `conflict_type = 'submitted_grade_locked'`; else `conflict_type = 'score_mismatch'`; both → `sync_status = 'conflict'` |
| 5 | *(internal)* | Write FERPA `pull` log per student to `educlaw_data_access_log` |
| 6 | `list-grade-conflicts` | Admin reviews all conflicts (SIS score vs LMS score side-by-side) |
| 7 | `resolve-grade-conflict` | Per conflict: `lms_wins` (apply LMS score), `sis_wins` (dismiss), or `manual` (new value). For submitted grades: must use parent `update-grade` amendment workflow |
| 8 | *(post-pull)* | Parent `generate-section-grade` recalculates weighted grades for affected students |

**GL/SLE implications:** None directly. If instructors use graded components that post to GL (v2 scope), GL posting happens via parent actions.

**Outcome:** `educlaw_assessment_result` updated with LMS-pulled grades; all conflicts resolved; section grades recalculated.

---

### 5.5 Workflow: OneRoster CSV Export

**Trigger:** Admin needs to sync with an LMS that doesn't support Canvas/Moodle/Google direct API (or for batch import).

| Step | Action | Description |
| --- | --- | --- |
| 1 | `export-oneroster-csv` | Validate all parameters; check DPA signed |
| 2 | *(internal)* | Generate `orgs.csv` (school/company record) |
| 3 | *(internal)* | Generate `academicSessions.csv` (from `educlaw_academic_term`) |
| 4 | *(internal)* | Generate `courses.csv` (from `educlaw_course`) |
| 5 | *(internal)* | Generate `classes.csv` (from `educlaw_section`) |
| 6 | *(internal)* | Generate `users.csv` (from `educlaw_student` + `educlaw_instructor`, with COPPA field minimization and directory opt-out handling) |
| 7 | *(internal)* | Generate `enrollments.csv` (from `educlaw_course_enrollment`) |
| 8 | *(if --include-grades)* | Generate `lineItems.csv` (from `educlaw_assessment`) + `results.csv` (from `educlaw_assessment_result`) |
| 9 | *(internal)* | Validate cross-references; UTF-8 encode; zip all files |
| 10 | *(internal)* | Log export in `educlaw_lms_sync_log` (type: `oneroster_export`) |

**FERPA implications:** OneRoster export is a disclosure to the receiving LMS. Logs `access_type = 'disclosure'` for each student in the export.

**Outcome:** `oneroster_{term_name}_{date}.zip` in output directory with all required CSV files.

---

### 5.6 Workflow: End-of-Term Grade Finalization

**Trigger:** Term ends; admin prepares to run parent `submit-grades`.

| Step | Action | Description |
| --- | --- | --- |
| 1 | `pull-grades` | Final grade pull for all sections in the term |
| 2 | `list-grade-conflicts` | Review any remaining conflicts |
| 3 | `resolve-grade-conflict` | Resolve all outstanding conflicts (required before grade submission) |
| 4 | Parent: `submit-grades` | Submits grades in SIS (locks `is_grade_submitted = 1`) |
| 5 | `close-lms-course` | Mark `educlaw_lms_course_mapping.sync_status = 'closed'` for all sections |

**Outcome:** All LMS grades reconciled; course mapping closed; no further grade pulls possible for closed sections.

---

## 6. Dependencies

### 6.1 Foundation Skills

| Skill | What We Use | How |
| --- | --- | --- |
| `erpclaw-setup` | `get_connection()`, `ensure_db_exists()` | DB connection for all operations; `company` table for institution scoping |
| `erpclaw-setup` | `audit()` function from `erpclaw_lib/audit.py` | Write audit entries for all state changes |
| `erpclaw-setup` | `encrypt_field()` / `decrypt_field()` from `erpclaw_lib/crypto.py` | Encrypt/decrypt LMS API credentials at rest |
| `erpclaw-setup` | `naming_series` table | Generate `LMS-NNNNN` and `SYN-YYYY-NNNNN` naming series |
| `erpclaw-gl` | `account` table | Read-only: institution's chart of accounts (no new GL entries from LMS domain) |
| `erpclaw-selling` | `customer` table | Read `email` field for student email (student → customer → email) |
| `erpclaw-hr` | `employee` table | Read `work_email` for instructor email for LMS account creation |

### 6.2 Parent Dependencies (educlaw)

| Parent Table/Action | Relationship | How educlaw-lms Uses It |
| --- | --- | --- |
| `educlaw_section` | FK from `educlaw_lms_course_mapping.section_id` | Source entity for all LMS course sync; section = one LMS course |
| `educlaw_student` | FK from `educlaw_lms_user_mapping.sis_user_id` | Source for LMS user accounts; `is_coppa_applicable`, `directory_info_opt_out` |
| `educlaw_instructor` | FK from `educlaw_lms_user_mapping.sis_user_id` | Source for LMS teacher accounts via `employee.work_email` |
| `educlaw_course_enrollment` | Read for roster push | Enrolled students per section → LMS enrollment roster |
| `educlaw_assessment` | FK from `educlaw_lms_assignment_mapping.assessment_id` | Source for LMS assignment push |
| `educlaw_assessment_result` | FK from `educlaw_lms_grade_sync.assessment_result_id` | Destination for grade pull; new result rows inserted; `is_grade_submitted` checked |
| `educlaw_academic_term` | FK from `educlaw_lms_sync_log.academic_term_id` | Term boundaries define LMS academic sessions |
| `educlaw_data_access_log` | Write disclosure/pull records | FERPA compliance: every sync writes disclosure or pull log |
| `educlaw_course_enrollment.is_grade_submitted` | Business rule | If `1`: block auto-apply of LMS grade; route through amendment workflow |
| Parent `update-grade` action | Called for submitted grade conflict | Grade amendments on locked grades must use parent's amendment workflow |
| Parent `generate-section-grade` | Called after grade pull | Recalculate weighted grades after pulling LMS scores |

---

## 7. Test Strategy

### 7.1 Unit Tests (per domain)

#### lms_sync Domain Tests

| Test | Scenario |
| --- | --- |
| `test_add_lms_connection_canvas` | Create Canvas connection; verify encrypted credentials stored; status = draft |
| `test_add_lms_connection_missing_endpoint` | Canvas connection without endpoint_url → validation error |
| `test_add_lms_connection_invalid_lms_type` | Unknown lms_type → CHECK constraint error |
| `test_test_lms_connection_dpa_not_signed` | `has_dpa_signed = 0` → cannot activate; returns E_DPA_REQUIRED |
| `test_test_lms_connection_success` | Mock LMS API returns 200 → status updated to active, site_name populated |
| `test_test_lms_connection_bad_credentials` | Mock LMS API returns 401 → status = error, error message returned |
| `test_sync_courses_dpa_gate` | `has_dpa_signed = 0` → all sync blocked |
| `test_sync_courses_coppa_unverified` | Student with `is_coppa_applicable = 1`, `is_coppa_verified = 0` → student skipped, error logged |
| `test_sync_courses_new_section` | Section without mapping → creates LMS course and `lms_course_mapping` |
| `test_sync_courses_existing_section` | Section already mapped → updates LMS course name if changed |
| `test_sync_courses_new_student` | Student without user mapping → creates LMS user and `lms_user_mapping` |
| `test_sync_courses_student_email_match` | LMS user exists with matching email → creates mapping to existing user |
| `test_sync_courses_directory_restricted` | `directory_info_opt_out = 1` → `is_directory_restricted = 1` in mapping |
| `test_sync_courses_enrollment_push` | Enrolled student with user + course mapping → LMS enrollment created |
| `test_sync_courses_dropped_enrollment` | Enrollment status = dropped → LMS enrollment removed |
| `test_sync_courses_google_classroom_invited` | Google Classroom enrollment → `sync_status = 'invited'` |
| `test_sync_courses_creates_ferpa_log` | Roster push → `educlaw_data_access_log` entry with `access_type = 'disclosure'` |
| `test_sync_courses_partial_failure` | Some sections fail → `completed_with_errors`; successful sections preserved |
| `test_sync_courses_concurrent_run_blocked` | Second sync run while first running → aborted with message |
| `test_resolve_sync_conflict_sis_wins` | User mismatch → sis_wins → re-push SIS data |
| `test_list_sync_logs_filters` | Filter by status, date range → correct results |

#### assignments Domain Tests

| Test | Scenario |
| --- | --- |
| `test_push_assessment_no_course_mapping` | Assessment's section has no LMS mapping → error |
| `test_push_assessment_canvas_success` | Mock Canvas API → creates assignment; `lms_assignment_mapping` inserted |
| `test_push_assessment_pass_fail_grading` | Assessment grading type = pass_fail → LMS `grading_type = 'pass_fail'` |
| `test_push_assessment_unpublished` | `is_published = 0` → LMS assignment created as unpublished |
| `test_sync_assessment_update_name_change` | Name changed → LMS API update called; `last_synced_at` updated |
| `test_sync_assessment_update_max_points_change` | max_points changed → warning returned (grade recalc) |
| `test_sync_assessment_update_no_mapping` | Assessment not in LMS → no-op (success with note) |
| `test_pull_lms_assignments` | Mock LMS returns 3 assignments; 2 already mapped, 1 new → 1 mapping created |
| `test_unlink_lms_assignment` | Unlink removes mapping; future grade pull skips this assessment |
| `test_list_lms_assignments_by_section` | Filter by section → only assignments for that section's plan returned |

#### online_gradebook Domain Tests

| Test | Scenario |
| --- | --- |
| `test_pull_grades_new_grade_lms_to_sis` | No SIS result exists; `grade_direction = 'lms_to_sis'` → new `assessment_result` inserted |
| `test_pull_grades_matching_scores` | SIS score = LMS score → `sync_status = 'skipped'`; no SIS update |
| `test_pull_grades_score_mismatch` | SIS score ≠ LMS score, grade not submitted → `conflict_type = 'score_mismatch'` |
| `test_pull_grades_submitted_grade_locked` | `is_grade_submitted = 1` → `conflict_type = 'submitted_grade_locked'`; no auto-apply |
| `test_pull_grades_direction_sis_to_lms` | `grade_direction = 'sis_to_lms'` → all grades `sync_status = 'skipped'` |
| `test_pull_grades_direction_manual` | `grade_direction = 'manual'` → all grades remain `pulled`; no auto-apply |
| `test_pull_grades_user_not_mapped` | LMS user has no mapping → `conflict_type = 'student_not_found'` |
| `test_pull_grades_assignment_not_mapped` | LMS assignment has no mapping → `conflict_type = 'assignment_not_found'` |
| `test_pull_grades_ferpa_log` | Each student grade pull → `educlaw_data_access_log` with `access_type = 'pull'` |
| `test_get_online_gradebook_structure` | Returns student×assessment matrix with both SIS and LMS scores |
| `test_get_online_gradebook_conflict_flag` | Conflict cell shows `is_conflict = 1` and both scores |
| `test_resolve_conflict_lms_wins_unsubmitted` | `lms_wins` on unsubmitted grade → `assessment_result.points_earned` updated |
| `test_resolve_conflict_lms_wins_submitted` | `lms_wins` on submitted grade → must use amendment workflow; returns amendment_id |
| `test_resolve_conflict_sis_wins` | `sis_wins` → `sync_status = 'skipped'`; SIS unchanged |
| `test_resolve_conflict_manual` | Admin enters new score → `assessment_result` updated; grade_sync resolved |
| `test_list_grade_conflicts_filter_type` | Filter by `conflict_type` → correct subset returned |
| `test_export_oneroster_csv_all_files` | Export produces all 8 CSV files; orgs/courses/classes/users/enrollments valid |
| `test_export_oneroster_csv_coppa_minimization` | Under-13 students in users.csv: no DOB, no phone, no address |
| `test_export_oneroster_csv_directory_restricted` | Students with `directory_info_opt_out = 1` have restricted fields |
| `test_export_oneroster_csv_with_grades` | `--include-grades` flag → lineItems.csv and results.csv included |
| `test_close_lms_course` | After `submit-grades`, `close-lms-course` → `sync_status = 'closed'`; further pulls blocked |

#### course_materials Domain Tests

| Test | Scenario |
| --- | --- |
| `test_add_material_url` | URL material → validates external_url format; inserted |
| `test_add_material_lms_linked` | LMS-linked material → `lms_connection_id` required |
| `test_add_material_invalid_type` | Unknown material_type → CHECK constraint error |
| `test_add_material_invalid_date_range` | `available_until` before `available_from` → validation error |
| `test_list_materials_sort_order` | Materials returned in ascending `sort_order` |
| `test_list_materials_visibility_filter` | `--is-visible-to-students 0` → only instructor-only materials |
| `test_list_materials_archived_excluded` | Archived materials not in default list |
| `test_delete_material_archives` | `delete-course-material` → `status = 'archived'`; not deleted from DB |
| `test_update_material_cannot_change_section` | Cannot update `section_id` |

### 7.2 Integration Tests

| Test | Scenario |
| --- | --- |
| `test_full_term_sync_canvas` | Add connection → test → sync → verify mappings created; verify FERPA logs |
| `test_full_grade_flow` | sync-courses → push-assessment-to-lms → pull-grades → resolve-grade-conflict → verify assessment_result |
| `test_end_of_term_flow` | pull-grades (all) → list-grade-conflicts → resolve all → submit-grades (parent) → close-lms-course → verify closed |
| `test_multi_lms_connections` | Canvas + Google Classroom both configured; sections sync to both; grade pulls independent |
| `test_oneroster_export_import_cycle` | Export OneRoster CSV → validate format matches IMS Global 1.1 spec |
| `test_coppa_guard_end_to_end` | Under-13 student + unverified LMS → blocked in sync; log entry created; verified connection shows 0 COPPA students synced |
| `test_ferpa_disclosure_completeness` | After full roster push: every student in `course_enrollment` has matching `data_access_log` disclosure entry |

### 7.3 Invariants

| Invariant | Description |
| --- | --- |
| **DPA Gate** | `has_dpa_signed = 0` MUST always block sync. No workaround path. |
| **COPPA Guard** | `is_coppa_applicable = 1` AND `is_coppa_verified = 0` MUST skip student and log `E_COPPA_UNVERIFIED` |
| **Grade Immutability** | `is_grade_submitted = 1` MUST never be overwritten by automated sync. `conflict_type = 'submitted_grade_locked'` always set. |
| **Sync Log Immutability** | `educlaw_lms_sync_log` records are never updated after creation (no `updated_at`). |
| **Grade Sync Immutability** | `educlaw_lms_grade_sync` records are never updated after creation (no `updated_at`). Resolution creates new downstream records. |
| **Unique Course Mapping** | One section maps to exactly one LMS course per connection (`UNIQUE(lms_connection_id, section_id)`). |
| **Credential Encryption** | Plaintext credentials MUST never appear in the database, logs, or API responses. |
| **Closed Course Lock** | `sync_status = 'closed'` on `lms_course_mapping` MUST block further grade pulls for that section. |
| **FERPA Log Completeness** | Every student record pushed to LMS MUST create a corresponding `educlaw_data_access_log` entry with `access_type = 'disclosure'`. |
| **Google Classroom Invitation State** | Google Classroom enrollments MUST be created with `sync_status = 'invited'` until confirmed accepted. |

---

## 8. Estimated Complexity

| Domain | Tables | Actions | Estimated Lines | Priority |
| --- | --- | --- | --- | --- |
| `lms_sync` | 4 (`connection`, `course_mapping`, `user_mapping`, `sync_log`) | 9 | ~700-900 | P0 — Critical |
| `online_gradebook` | 1 (`grade_sync`) | 6 | ~600-800 | P0 — Critical |
| `assignments` | 1 (`assignment_mapping`) | 5 | ~400-500 | P1 — Important |
| `course_materials` | 1 (`course_material`) | 5 | ~200-300 | P2 — Nice to Have |
| `adapters/canvas.py` | (support) | — | ~400-500 | P0 — Canvas first |
| `adapters/google_classroom.py` | (support) | — | ~400-500 | P0 — K-12 priority |
| `adapters/moodle.py` | (support) | — | ~300-400 | P1 |
| `adapters/oneroster_csv.py` | (support) | — | ~300-400 | P1 — quick win |
| `adapters/base.py` | (support) | — | ~100 | P0 — defines interface |
| Schema (`init_db.py` ext.) | 7 new tables | — | ~300-400 | P0 |
| Tests | — | ~50+ tests | ~800-1000 | P0 |
| SKILL.md | — | 25 actions | ~200 | P1 |
| **Total** | **7** | **25** | **~4,500-5,700** | |

### Build Sequence (Recommended)

1. **Schema** — `init_db.py` extension for 7 new tables
2. **adapters/base.py** — Abstract adapter interface (defines `sync_course`, `sync_user`, `sync_enrollment`, `push_assignment`, `pull_grades`)
3. **lms_sync** — Connection management (`add`, `update`, `get`, `list`, `test`) — no LMS API needed for get/list
4. **adapters/oneroster_csv.py** + `export-oneroster-csv` — Quick win; no live LMS API
5. **adapters/canvas.py** — Highest market share; P0 priority
6. **lms_sync** `sync-courses` — Roster push using Canvas adapter
7. **online_gradebook** — `pull-grades`, `get-online-gradebook`, `list-grade-conflicts`, `resolve-grade-conflict`
8. **assignments** — `push-assessment-to-lms`, `sync-assessment-update`, `list-lms-assignments`
9. **adapters/google_classroom.py** — K-12 priority; invitation flow handling
10. **adapters/moodle.py** — Open-source community priority
11. **course_materials** — Simplest domain; build last
12. **SKILL.md** — Document all 25 actions

---

## 9. File Structure

```
educlaw-lms/
├── SKILL.md
├── scripts/
│   ├── db_query.py              # Router: dispatches --action to domain module
│   ├── lms_sync.py              # Domain: connection + roster sync (9 actions)
│   ├── assignments.py           # Domain: assignment mapping (5 actions)
│   ├── online_gradebook.py      # Domain: grade pull + gradebook + export (6 actions)
│   ├── course_materials.py      # Domain: course materials CRUD (5 actions)
│   └── adapters/
│       ├── base.py              # Abstract adapter interface
│       ├── canvas.py            # Canvas REST API (OAuth 2.0)
│       ├── moodle.py            # Moodle Web Services (token auth)
│       ├── google_classroom.py  # Google Classroom API (OAuth 2.0)
│       └── oneroster_csv.py     # OneRoster 1.1 CSV file generation
├── tests/
│   ├── test_lms_sync.py
│   ├── test_assignments.py
│   ├── test_online_gradebook.py
│   ├── test_course_materials.py
│   └── test_integration.py
├── plan/
│   └── educlaw-lms_plan.md      # This file
└── research/
    └── educlaw-lms/             # Stage 1 research output
```

---

## 10. Compliance Architecture Summary

### FERPA Implementation
- `educlaw_data_access_log` extended with two new `access_type` values: `disclosure` (outgoing push to LMS) and `pull` (incoming grade data from LMS)
- Every call to `sync-courses` logs one disclosure entry per student synced
- Every call to `pull-grades` logs one pull entry per student whose grade was accessed
- `export-oneroster-csv` logs disclosure for every student in the export
- DPA check (`has_dpa_signed`) enforced as hard gate in every sync action

### COPPA Implementation
- `educlaw_student.is_coppa_applicable` checked before every user sync
- Under-13 students blocked if `educlaw_lms_connection.is_coppa_verified = 0`
- COPPA-safe sync payload: only `{first_name, last_name, email, enrollment}` — never DOB, address, guardian info, photo, SSN
- `is_coppa_restricted = 1` stored in `educlaw_lms_user_mapping` as a permanent marker

### Credential Security
- All OAuth secrets, tokens, and service account JSON stored encrypted via `erpclaw_lib/crypto.py` `encrypt_field()`
- Decryption key from environment variable `EDUCLAW_LMS_ENCRYPTION_KEY` only
- API responses and logs never contain plaintext credentials
- `get-lms-connection` returns only last 4 characters of any credential field

### Google Classroom Special Handling
- No LTI or OneRoster support → direct API only
- Invitation-based enrollment: `sync_status = 'invited'` until acceptance confirmed
- Cannot read overall course grade from API → calculate from individual `studentSubmissions`
- Grading periods: use 2025 Grading Periods API for term mapping

### Rate Limiting Strategy
- Canvas: leaky bucket; 100ms delay between calls; separate API token for educlaw-lms
- Google: 100 req/100 sec per user; implement exponential backoff
- Moodle: admin-configurable; default no throttle; retry on 429/503
- All adapters: 3 retry attempts with exponential backoff (1s, 2s, 4s)

---

*Plan authored: 2026-03-05*
*Research basis: overview.md, competitors.md, compliance.md, workflows.md, data_model.md, parent_analysis.md, research_summary.md*
*Parent product: educlaw (112 actions, 32 tables) — ZERO naming conflicts verified*
*Foundation: erpclaw-setup, erpclaw-gl, erpclaw-selling, erpclaw-payments, erpclaw-hr*
