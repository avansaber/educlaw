# EduClaw LMS Integration — Data Model Insights

## Overview

This document defines the entity-relationship model for educlaw-lms based on competitor analysis, workflow requirements, and parent product analysis. All tables follow EduClaw/ERPClaw conventions:
- **IDs:** TEXT (UUID)
- **Monetary amounts:** TEXT (Python Decimal) — not applicable in LMS domain, but timestamps and scores follow standard
- **Naming series:** `LMS-NNNNN` for connections, `SYN-YYYY-NNNNN` for sync runs
- **Timestamps:** `created_at`, `updated_at` (sync logs omit `updated_at` — append-only)
- **Document lifecycle:** Draft → Active → Inactive for connections; Pending → Running → Completed for sync runs
- **Table prefix:** `educlaw_lms_` for all educlaw-lms-owned tables

## Design Principles

### 1. Cross-Reference Tables Are the Architectural Core
The entire LMS integration is built on four cross-reference tables that map EduClaw IDs to external LMS IDs:
- `educlaw_lms_course_mapping` — section_id ↔ LMS course/class ID
- `educlaw_lms_user_mapping` — student_id/instructor_id ↔ LMS user ID
- `educlaw_lms_assignment_mapping` — assessment_id ↔ LMS assignment/line item ID
- `educlaw_lms_grade_sync` — assessment_result_id ↔ LMS submission score

### 2. Multi-LMS Architecture
A single EduClaw instance can connect to **multiple LMS platforms simultaneously** (e.g., Canvas for high school, Google Classroom for middle school). All mapping tables carry a `lms_connection_id` foreign key to distinguish which LMS the mapping belongs to.

### 3. SIS Is Always Authoritative
The `educlaw_assessment_result` table (parent) is the official grade record. LMS grades are pulled into a staging table (`educlaw_lms_grade_sync`) and only written to `educlaw_assessment_result` when explicitly applied by the administrator or instructor — and only for non-submitted grades. Submitted grades always require the parent's amendment workflow.

### 4. Sync Logs Are Immutable Audit Records
Sync log entries and grade sync records have NO `updated_at` column. They are append-only. A new record is created for each sync attempt. This mirrors the GL immutability pattern from ERPClaw.

### 5. FERPA Integration
All sync operations that push student data to an LMS must create a corresponding `educlaw_data_access_log` entry (parent table) with `access_type = 'disclosure'`. Grade pulls create entries with `access_type = 'pull'`. This is enforced at the Python action level, not the database schema level.

---

## Parent Tables Used (Read-Only from educlaw-lms)

| Parent Table | educlaw-lms Usage |
|---|---|
| `educlaw_student` | Source for user sync; read `email`, `full_name`, `is_coppa_applicable`, `directory_info_opt_out` |
| `educlaw_instructor` | Source for teacher sync; read linked `employee_id` → email |
| `educlaw_course` | Source for course sync; read `course_code`, `name`, `description` |
| `educlaw_section` | Source for class/course sync; read `section_number`, `course_id`, `academic_term_id`, `instructor_id` |
| `educlaw_course_enrollment` | Source for roster sync; read enrolled students per section; check `is_grade_submitted` before writing grades |
| `educlaw_academic_term` | Source for academic session sync; read `name`, `start_date`, `end_date` |
| `educlaw_assessment` | Source for assignment push; read `name`, `max_points`, `due_date`, `is_published` |
| `educlaw_assessment_result` | Destination for grade pull; write `points_earned`, `graded_at`, `comments` |
| `educlaw_assessment_plan` | Link from assessment → section via plan |
| `educlaw_data_access_log` | Write disclosure/pull logs for every sync operation |
| `employee` | Read instructor email (via educlaw_instructor → employee_id) |
| `company` | Institution context for all LMS connections |

---

## educlaw-lms-Owned Tables (8 New Tables)

### Domain 1: LMS Connections

#### `educlaw_lms_connection`
Configuration record for a connected LMS platform.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| naming_series | TEXT | NOT NULL, UNIQUE | LMS-00001 |
| display_name | TEXT | NOT NULL | e.g., "Jefferson High — Canvas" |
| lms_type | TEXT | NOT NULL | `canvas` / `moodle` / `google_classroom` / `oneroster_csv` |
| endpoint_url | TEXT | | Base URL of LMS (null for oneroster_csv) |
| client_id | TEXT | | OAuth client_id (Canvas) |
| client_secret_encrypted | TEXT | | Encrypted OAuth secret (Canvas) |
| site_token_encrypted | TEXT | | Encrypted web service token (Moodle) |
| google_credentials_encrypted | TEXT | | Encrypted service account JSON (Google) |
| lms_site_name | TEXT | | LMS site name (populated on test-connection) |
| lms_version | TEXT | | LMS version string (populated on test-connection) |
| grade_direction | TEXT | NOT NULL DEFAULT 'lms_to_sis' | `lms_to_sis` / `sis_to_lms` / `manual` |
| auto_sync_enabled | INTEGER | NOT NULL DEFAULT 0 | 0 or 1 |
| sync_frequency_hours | INTEGER | | Hours between auto-syncs (if auto_sync_enabled) |
| last_sync_at | TEXT | | ISO timestamp of last successful sync |
| default_course_prefix | TEXT | | Optional prefix for LMS course names |
| auto_push_assignments | INTEGER | NOT NULL DEFAULT 0 | Auto-push new assessments to LMS |
| has_dpa_signed | INTEGER | NOT NULL DEFAULT 0 | **Required: DPA must be signed before sync** |
| dpa_signed_date | TEXT | | ISO date |
| is_coppa_verified | INTEGER | NOT NULL DEFAULT 0 | LMS confirmed COPPA-compliant |
| coppa_cert_url | TEXT | | URL to LMS COPPA certification |
| allowed_data_fields | TEXT | | JSON: which fields DPA permits to be synced |
| status | TEXT | NOT NULL DEFAULT 'draft' | `draft` / `active` / `inactive` / `error` |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL | ISO timestamp |
| updated_at | TEXT | NOT NULL | ISO timestamp |

**Indexes:** `(company_id, lms_type, status)`, `(naming_series)` UNIQUE
**Constraints:**
- `CHECK(lms_type IN ('canvas','moodle','google_classroom','oneroster_csv'))`
- `CHECK(grade_direction IN ('lms_to_sis','sis_to_lms','manual'))`
- `CHECK(status IN ('draft','active','inactive','error'))`

**Business Rules:**
- `has_dpa_signed = 0` → all sync actions must return error
- `is_coppa_verified = 0` → block sync for any student with `is_coppa_applicable = 1`
- Credentials stored encrypted; plaintext never in DB

---

### Domain 2: Cross-Reference Mappings

#### `educlaw_lms_course_mapping`
Maps EduClaw sections to LMS courses/classes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| lms_connection_id | TEXT | FK → educlaw_lms_connection | NOT NULL |
| section_id | TEXT | FK → educlaw_section | NOT NULL |
| lms_course_id | TEXT | NOT NULL | External LMS course/class ID |
| lms_course_url | TEXT | | Web URL to LMS course |
| lms_term_id | TEXT | | External LMS term/session ID |
| sync_status | TEXT | NOT NULL DEFAULT 'synced' | `synced` / `pending` / `error` / `closed` |
| last_synced_at | TEXT | | ISO timestamp |
| sync_error | TEXT | | Last error message if sync_status = error |
| created_at | TEXT | NOT NULL | |

**Indexes:** `(lms_connection_id, section_id)` UNIQUE, `(lms_course_id, lms_connection_id)` UNIQUE
**Note:** No `updated_at` — create a new record if a section needs remapping. Keep historical records with `sync_status = 'closed'`.

---

#### `educlaw_lms_user_mapping`
Maps EduClaw students and instructors to LMS user accounts.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| lms_connection_id | TEXT | FK → educlaw_lms_connection | NOT NULL |
| sis_user_type | TEXT | NOT NULL | `student` / `instructor` |
| sis_user_id | TEXT | NOT NULL | FK → educlaw_student.id OR educlaw_instructor.id |
| lms_user_id | TEXT | NOT NULL | External LMS user ID |
| lms_username | TEXT | | LMS login identifier |
| lms_login_email | TEXT | | Email used for LMS account |
| is_coppa_restricted | INTEGER | NOT NULL DEFAULT 0 | 1 if student has COPPA restrictions (under-13) |
| is_directory_restricted | INTEGER | NOT NULL DEFAULT 0 | 1 if directory_info_opt_out = 1 |
| sync_status | TEXT | NOT NULL DEFAULT 'synced' | `synced` / `pending` / `error` |
| last_synced_at | TEXT | | ISO timestamp |
| sync_error | TEXT | | Last error message |
| created_at | TEXT | NOT NULL | |

**Indexes:** `(lms_connection_id, sis_user_type, sis_user_id)` UNIQUE, `(lms_user_id, lms_connection_id)` UNIQUE
**Constraints:** `CHECK(sis_user_type IN ('student','instructor'))`

---

#### `educlaw_lms_assignment_mapping`
Maps EduClaw assessments to LMS assignments/line items.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| lms_connection_id | TEXT | FK → educlaw_lms_connection | NOT NULL |
| assessment_id | TEXT | FK → educlaw_assessment | NOT NULL |
| lms_assignment_id | TEXT | NOT NULL | External LMS assignment/activity ID |
| lms_assignment_url | TEXT | | Web URL to LMS assignment |
| lms_grade_scheme | TEXT | | LMS grading scheme (points / percentage / pass_fail) |
| push_direction | TEXT | NOT NULL DEFAULT 'sis_to_lms' | `sis_to_lms` (SIS created) / `lms_to_sis` (LMS created, imported) |
| is_published_in_lms | INTEGER | NOT NULL DEFAULT 0 | Whether assignment is visible to students in LMS |
| sync_status | TEXT | NOT NULL DEFAULT 'synced' | `synced` / `pending` / `error` |
| last_synced_at | TEXT | | ISO timestamp |
| sync_error | TEXT | | Last error message |
| created_at | TEXT | NOT NULL | |

**Indexes:** `(lms_connection_id, assessment_id)` UNIQUE, `(lms_assignment_id, lms_connection_id)` UNIQUE

---

### Domain 3: Sync Logging

#### `educlaw_lms_sync_log`
Audit trail for every sync operation (immutable — no `updated_at`).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| naming_series | TEXT | NOT NULL, UNIQUE | SYN-2026-00001 |
| lms_connection_id | TEXT | FK → educlaw_lms_connection | NOT NULL |
| sync_type | TEXT | NOT NULL | `roster_push` / `grade_pull` / `assignment_push` / `full_sync` / `oneroster_export` |
| academic_term_id | TEXT | FK → educlaw_academic_term | Which term was synced |
| section_id | TEXT | FK → educlaw_section | Which section (null for full_sync) |
| triggered_by | TEXT | | User who triggered; or 'scheduler' for auto |
| status | TEXT | NOT NULL DEFAULT 'pending' | `pending` / `running` / `completed` / `completed_with_errors` / `failed` |
| sections_synced | INTEGER | NOT NULL DEFAULT 0 | Count of sections processed |
| students_synced | INTEGER | NOT NULL DEFAULT 0 | Count of students processed |
| grades_pulled | INTEGER | NOT NULL DEFAULT 0 | Count of grades pulled from LMS |
| grades_applied | INTEGER | NOT NULL DEFAULT 0 | Count of grades written to SIS |
| conflicts_flagged | INTEGER | NOT NULL DEFAULT 0 | Count of grade conflicts |
| errors_count | INTEGER | NOT NULL DEFAULT 0 | Count of failed records |
| error_summary | TEXT | | JSON array of error objects: [{entity_type, entity_id, error_message}] |
| started_at | TEXT | | ISO timestamp |
| completed_at | TEXT | | ISO timestamp |
| duration_seconds | INTEGER | | Sync duration |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL | **NO updated_at — immutable** |

**Indexes:** `(lms_connection_id, status)`, `(academic_term_id, sync_type)`, `(company_id, created_at)`, `(naming_series)` UNIQUE
**Constraints:** `CHECK(status IN ('pending','running','completed','completed_with_errors','failed'))`, `CHECK(sync_type IN (...))`

---

### Domain 4: Grade Sync Staging

#### `educlaw_lms_grade_sync`
Staging table for grades pulled from LMS (before writing to authoritative `educlaw_assessment_result`).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| lms_connection_id | TEXT | FK → educlaw_lms_connection | NOT NULL |
| lms_assignment_id | TEXT | NOT NULL | External LMS assignment ID |
| lms_user_id | TEXT | NOT NULL | External LMS user ID |
| assessment_id | TEXT | FK → educlaw_assessment | Resolved from lms_assignment_mapping |
| student_id | TEXT | FK → educlaw_student | Resolved from lms_user_mapping |
| assessment_result_id | TEXT | FK → educlaw_assessment_result | NULL until applied |
| lms_score | TEXT | | Raw score from LMS (TEXT for precision) |
| lms_grade | TEXT | | Letter grade from LMS (if set) |
| lms_submitted_at | TEXT | | When student submitted in LMS |
| lms_graded_at | TEXT | | When instructor graded in LMS |
| is_late | INTEGER | NOT NULL DEFAULT 0 | LMS reported as late |
| is_missing | INTEGER | NOT NULL DEFAULT 0 | LMS reported as missing |
| lms_comments | TEXT | | Instructor feedback from LMS |
| sis_score | TEXT | | Current SIS score at time of pull (for conflict detection) |
| is_conflict | INTEGER | NOT NULL DEFAULT 0 | 1 if lms_score ≠ sis_score |
| conflict_type | TEXT | | `score_mismatch` / `submitted_grade_locked` / `student_not_found` / `assignment_not_found` |
| sync_status | TEXT | NOT NULL DEFAULT 'pulled' | `pulled` / `applied` / `conflict` / `skipped` / `error` |
| resolved_by | TEXT | | User who resolved conflict |
| resolved_at | TEXT | | ISO timestamp of resolution |
| resolution | TEXT | | `lms_wins` / `sis_wins` / `manual` |
| sync_log_id | TEXT | FK → educlaw_lms_sync_log | Which sync run produced this |
| created_at | TEXT | NOT NULL | **NO updated_at — immutable pull record** |

**Indexes:**
- `(lms_connection_id, assessment_id, student_id)` — find existing grade syncs
- `(sync_status, is_conflict)` — find unresolved conflicts
- `(assessment_id, student_id, sync_log_id)` — chronological grade history per student/assessment
- `(student_id, sync_status)` — student-level sync status
- `(sync_log_id)` — link back to sync run

**Constraints:**
- `CHECK(sync_status IN ('pulled','applied','conflict','skipped','error'))`
- `CHECK(conflict_type IN ('score_mismatch','submitted_grade_locked','student_not_found','assignment_not_found') OR conflict_type IS NULL)`

**Note:** No `updated_at` — this is a pull record. Resolution creates a new `educlaw_assessment_result` or grade amendment, not an update here.

---

### Domain 5: Course Materials

#### `educlaw_lms_course_material`
Course documents and resources tracked in the SIS.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| section_id | TEXT | FK → educlaw_section | NOT NULL |
| assessment_id | TEXT | FK → educlaw_assessment | NULL for general materials |
| name | TEXT | NOT NULL | e.g., "Week 3 Reading: Chapter 5" |
| description | TEXT | | |
| material_type | TEXT | NOT NULL | `syllabus` / `reading` / `video_link` / `assignment_guide` / `rubric` / `other` |
| access_type | TEXT | NOT NULL | `url` / `file_attachment` / `lms_linked` |
| external_url | TEXT | | For access_type = 'url' |
| file_path | TEXT | | For access_type = 'file_attachment' (local path) |
| lms_connection_id | TEXT | FK → educlaw_lms_connection | For access_type = 'lms_linked' |
| lms_file_id | TEXT | | LMS-side file identifier |
| lms_download_url | TEXT | | LMS-side download URL |
| is_visible_to_students | INTEGER | NOT NULL DEFAULT 1 | |
| available_from | TEXT | | ISO date — when to show to students |
| available_until | TEXT | | ISO date — when to hide |
| sort_order | INTEGER | NOT NULL DEFAULT 0 | Display order within section |
| status | TEXT | NOT NULL DEFAULT 'active' | `active` / `archived` |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |

**Indexes:** `(section_id, sort_order)`, `(section_id, material_type)`, `(assessment_id)`, `(company_id, status)`
**Constraints:** `CHECK(material_type IN (...))`, `CHECK(access_type IN ('url','file_attachment','lms_linked'))`, `CHECK(status IN ('active','archived'))`

---

## Table Count Summary

| Domain | Table | Purpose |
|--------|-------|---------|
| LMS Connections | `educlaw_lms_connection` | LMS platform config + compliance settings |
| Cross-Reference | `educlaw_lms_course_mapping` | Section ↔ LMS course |
| Cross-Reference | `educlaw_lms_user_mapping` | Student/instructor ↔ LMS user |
| Cross-Reference | `educlaw_lms_assignment_mapping` | Assessment ↔ LMS assignment |
| Sync Audit | `educlaw_lms_sync_log` | Per-sync-run audit trail (immutable) |
| Grade Staging | `educlaw_lms_grade_sync` | LMS grades staged before applying to SIS |
| Course Materials | `educlaw_lms_course_material` | Course documents and resource links |
| **Total** | **7 tables** | |

---

## Entity-Relationship Diagram (Text)

```
educlaw_lms_connection (1 per LMS platform configured)
    │
    ├──▶ educlaw_lms_course_mapping (N sections mapped to LMS courses)
    │       │
    │       └── section_id ──▶ educlaw_section (parent)
    │
    ├──▶ educlaw_lms_user_mapping (N students/instructors mapped to LMS users)
    │       │
    │       ├── sis_user_id ──▶ educlaw_student (parent, when sis_user_type='student')
    │       └── sis_user_id ──▶ educlaw_instructor (parent, when sis_user_type='instructor')
    │
    ├──▶ educlaw_lms_assignment_mapping (N assessments mapped to LMS assignments)
    │       │
    │       └── assessment_id ──▶ educlaw_assessment (parent)
    │
    ├──▶ educlaw_lms_sync_log (N sync runs — immutable audit trail)
    │       │
    │       └──▶ educlaw_lms_grade_sync (N grades pulled per sync run — immutable)
    │               │
    │               ├── assessment_id ──▶ educlaw_assessment (parent)
    │               ├── student_id ──▶ educlaw_student (parent)
    │               └── assessment_result_id ──▶ educlaw_assessment_result (parent, when applied)
    │
    └── (implicit via section) ──▶ educlaw_lms_course_material
            │
            ├── section_id ──▶ educlaw_section (parent)
            └── assessment_id ──▶ educlaw_assessment (parent, optional)

educlaw_data_access_log (parent) ◀── written by every sync action
    (tracks: student_id, data_category, access_type='disclosure'|'pull')
```

---

## Status Lifecycles

### LMS Connection
```
draft → active (connection tested + DPA signed)
      → inactive (manually disabled)
      → error (API failure on last operation)
```

### Sync Run (educlaw_lms_sync_log)
```
pending → running → completed (all records processed)
                  → completed_with_errors (some records failed)
                  → failed (critical error; no records processed)
```

### Grade Sync Entry (educlaw_lms_grade_sync)
```
pulled → applied (written to educlaw_assessment_result)
       → conflict (SIS ≠ LMS, awaiting resolution)
       → skipped (grade_direction = sis_to_lms)
       → error (could not map student or assignment)
```

### Course Mapping
```
pending → synced (successfully mapped to LMS)
        → error (failed to create/update in LMS)
        → closed (term ended; grade submission locked)
```

### Course Material
```
active → archived (removed from student view)
```

---

## Naming Series Summary

| Entity | Prefix | Year | Example |
|--------|--------|------|---------|
| LMS Connection | LMS- | No | LMS-00001 |
| Sync Run Log | SYN- | Yes | SYN-2026-00042 |

All other tables use system-generated UUIDs without a human-readable naming series (cross-reference tables and grade sync records are operational, not user-facing documents).

---

## Key Constraints and Business Rules

### Data Integrity Rules
1. **DPA Check:** `educlaw_lms_connection.has_dpa_signed = 0` → all sync actions return error code `E_DPA_REQUIRED`
2. **COPPA Check:** Student `is_coppa_applicable = 1` + connection `is_coppa_verified = 0` → skip student; log error `E_COPPA_UNVERIFIED`
3. **Grade Immutability:** `educlaw_course_enrollment.is_grade_submitted = 1` → `lms_grade_sync.sync_status` = `conflict` with `conflict_type = 'submitted_grade_locked'`; never auto-apply to SIS
4. **Duplicate Mapping:** `(lms_connection_id, section_id)` UNIQUE on `educlaw_lms_course_mapping` — one section maps to exactly one LMS course per connection
5. **User Mapping Uniqueness:** `(lms_connection_id, sis_user_type, sis_user_id)` UNIQUE — one LMS user per SIS user per connection

### Privacy Rules (enforced in Python, not DB)
1. **Directory opt-out:** Students with `directory_info_opt_out = 1` → set `lms_user_mapping.is_directory_restricted = 1`; LMS must be configured to hide their info from class lists
2. **COPPA field restriction:** For `is_coppa_applicable = 1` students → sync only `{first_name, last_name, email}` + enrollment; never DOB, address, guardian info, photo
3. **FERPA disclosure log:** Every roster push writes to `educlaw_data_access_log` with `access_type = 'disclosure'`, `data_category = 'demographics,enrollment'`
4. **FERPA pull log:** Every grade pull writes to `educlaw_data_access_log` with `access_type = 'pull'`, `data_category = 'grades'`

---

## Data Model Comparison vs. Competitors

| Concept | OpenSIS LMS Tables | educlaw-lms Tables | Advantage |
|---------|-------------------|-------------------|-----------|
| Connection config | `opensis_lms_connections` | `educlaw_lms_connection` | + DPA/COPPA compliance fields |
| Course mapping | `opensis_lms_course_map` | `educlaw_lms_course_mapping` | + sync_status, lms_term_id |
| User mapping | `opensis_lms_user_map` | `educlaw_lms_user_mapping` | + COPPA/directory restriction flags |
| Grade sync | `opensis_lms_grade_sync` | `educlaw_lms_grade_sync` | + conflict detection, immutability |
| Assignment mapping | None (OpenSIS) | `educlaw_lms_assignment_mapping` | Full bidirectional assignment sync |
| Sync audit | Limited | `educlaw_lms_sync_log` | Full immutable audit trail |
| Course materials | None (OpenSIS) | `educlaw_lms_course_material` | SIS-side material management |

---

## Implementation Notes for Schema (init_db.py)

1. **Encrypted credential storage** — `client_secret_encrypted`, `site_token_encrypted`, `google_credentials_encrypted` are TEXT fields. Encryption/decryption happens in Python using a school-specific key (stored in settings or environment variable). Schema stores ciphertext only.

2. **Score precision** — `lms_score`, `sis_score` in `educlaw_lms_grade_sync` are TEXT (Python Decimal), consistent with parent EduClaw's convention for all numeric values used in calculations.

3. **JSON fields** — `error_summary` (sync_log), `allowed_data_fields` (connection) are TEXT storing JSON. No JSON column type in SQLite — use `json.dumps/loads` in Python.

4. **LMS-type-specific API logic** — The `lms_type` field in `educlaw_lms_connection` determines which Python adapter module is used at runtime:
   - `canvas` → `scripts/adapters/canvas.py`
   - `moodle` → `scripts/adapters/moodle.py`
   - `google_classroom` → `scripts/adapters/google_classroom.py`
   - `oneroster_csv` → `scripts/adapters/oneroster_csv.py`

5. **No Frappe/ORM** — Pure SQLite + Python (parameterized queries), consistent with all EduClaw patterns.

---

*Sources: OpenSIS LMS Integration Schema (GitHub: OS4ED/openSIS-Classic), IMS Global OneRoster 1.1 Data Model, Canvas REST API Data Objects, Moodle Web Services Data Structures, Google Classroom API Resource Types, ERPNext Education DocType analysis, Infinite Campus OneRoster export format documentation, ERPClaw data model conventions (init_db.py patterns)*
