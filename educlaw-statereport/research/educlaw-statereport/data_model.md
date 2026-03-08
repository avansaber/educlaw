# Data Model Insights: EduClaw State Reporting

**Product:** EduClaw State Reporting (educlaw-statereport)
**Research Date:** 2026-03-05

---

## 1. Design Philosophy

### Core Principles

1. **EduClaw is the source of truth** — `educlaw-statereport` never duplicates operational data. It extends with supplemental fields and adds reporting infrastructure.

2. **Snapshot immutability** — Once a collection window closes, its snapshot data is frozen. Historical snapshots are never modified.

3. **Ed-Fi as output, not model** — The Ed-Fi API is a submission target. Internal data models are normalized for operational use; Ed-Fi serialization happens at export time.

4. **Multi-state architecture** — A single EduClaw instance may need to report to different states (charter networks operating across states). All reporting tables must be state-scoped.

5. **Separation of concerns**:
   - `sr_` prefix for all state reporting tables
   - Operational data stays in `educlaw_` tables
   - State reporting tables reference operational tables via foreign keys, never copy data

---

## 2. Entity-Relationship Overview

```
Foundation / EduClaw (existing):
┌─────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│ company (LEA)   │────<│ educlaw_student        │────<│ educlaw_program_ │
│ NCES LEA ID     │     │ ssid_encrypted        │     │   enrollment     │
└─────────────────┘     │ grade_level            │     └──────────────────┘
         │              └──────────────────────┘              │
         │                        │                           │
         ▼                        ▼                           ▼
┌─────────────────┐    ┌──────────────────────┐   ┌──────────────────┐
│ sr_org_mapping  │    │ sr_student_supplement│   │ sr_collection_   │
│ (NCES IDs,      │    │ (race, EL, SPED,     │   │   window        │
│  Ed-Fi IDs)     │    │  SSID, economic,     │   │ (annual windows)│
└─────────────────┘    │  homeless)           │   └──────────────────┘
                       └──────────────────────┘           │
                                │                          ▼
                                │                ┌──────────────────┐
                                │                │   sr_snapshot    │
                                │                │ (frozen copy at  │
                                │                │  window close)   │
                                │                └──────────────────┘
                                ▼                         │
                    ┌──────────────────────┐              ▼
                    │ sr_discipline_       │    ┌──────────────────┐
                    │   incident          │    │ sr_submission    │
                    │ sr_discipline_      │    │ (Ed-Fi sync log, │
                    │   student           │    │  certification)  │
                    │ sr_discipline_      │    └──────────────────┘
                    │   action            │              │
                    └──────────────────────┘             ▼
                                          ┌──────────────────────┐
                    ┌──────────────────┐  │ sr_submission_error  │
                    │ sr_sped_         │  │ (validation errors,  │
                    │   placement      │  │  resolution tracking)│
                    │ sr_sped_         │  └──────────────────────┘
                    │   service        │
                    └──────────────────┘
                    ┌──────────────────┐
                    │ sr_el_program    │
                    └──────────────────┘
                    ┌──────────────────┐
                    │ sr_edfi_         │
                    │   config         │
                    │ sr_edfi_         │
                    │   descriptor_map │
                    │ sr_edfi_         │
                    │   sync_log       │
                    └──────────────────┘
                    ┌──────────────────┐
                    │ sr_validation_   │
                    │   rule           │
                    │ sr_validation_   │
                    │   result         │
                    └──────────────────┘
```

---

## 3. Proposed Tables (New — educlaw-statereport)

### 3.1 Organization & Configuration

#### `sr_org_mapping`
Maps EduClaw company/school records to federal/state identifiers.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `company_id` | TEXT FK → company | LEA in EduClaw |
| `nces_lea_id` | TEXT | 7-digit NCES LEA ID |
| `nces_school_id` | TEXT | 12-digit NCES School ID (NULL for district-level) |
| `state_code` | TEXT | 2-letter state code (CA, TX, WI) |
| `state_lea_id` | TEXT | State-assigned district ID (separate from NCES) |
| `state_school_id` | TEXT | State-assigned school ID |
| `edfi_lea_id` | TEXT | Ed-Fi LocalEducationAgency identifier |
| `edfi_school_id` | TEXT | Ed-Fi School identifier |
| `crdc_school_id` | TEXT | CRDC school identifier (= NCES school ID typically) |
| `is_title_i_school` | INTEGER | 0/1 flag |
| `title_i_status` | TEXT | targeted_assistance, schoolwide, not_title_i |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |
| UNIQUE(company_id, state_code) | | One mapping per LEA per state |

#### `sr_edfi_config`
Ed-Fi ODS connection configuration per state per school year.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `profile_name` | TEXT | Human-readable name (e.g., "Texas TSDS 2025-26") |
| `state_code` | TEXT | Target state |
| `school_year` | INTEGER | e.g., 2026 (means 2025-26) |
| `ods_base_url` | TEXT | Ed-Fi ODS API base URL |
| `oauth_token_url` | TEXT | OAuth token endpoint |
| `oauth_client_id` | TEXT | OAuth client ID |
| `oauth_client_secret_encrypted` | TEXT | AES-encrypted secret |
| `api_version` | TEXT | 5, 6, 7 |
| `is_active` | INTEGER | 0/1 |
| `last_tested_at` | TEXT | Last successful auth test |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |
| UNIQUE(company_id, state_code, school_year) | | |

#### `sr_edfi_descriptor_map`
Maps EduClaw internal codes to Ed-Fi descriptor URIs.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `config_id` | TEXT FK → sr_edfi_config | Which state config |
| `descriptor_type` | TEXT | grade_level, race, sex, attendance_event, disability, language, exit_type, entry_type, discipline_behavior, discipline_action, sped_environment, program_type |
| `internal_code` | TEXT | EduClaw's internal value |
| `edfi_descriptor_uri` | TEXT | Full Ed-Fi descriptor URI |
| `is_active` | INTEGER | |
| `company_id` | TEXT FK → company | |
| `created_at`, `created_by` | TEXT | |
| UNIQUE(config_id, descriptor_type, internal_code) | | |

---

### 3.2 Student Supplement

#### `sr_student_supplement`
**Critical table.** Extends `educlaw_student` with all state reporting-specific data elements that EduClaw's operational student table doesn't capture.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK → educlaw_student | One-to-one |
| `ssid` | TEXT | State Student Identifier (may vary per state) |
| `ssid_state_code` | TEXT | Which state issued this SSID |
| **Race / Ethnicity** | | (multi-select; store as JSON array) |
| `is_hispanic_latino` | INTEGER | 0/1; asked separately per OMB standard |
| `race_codes` | TEXT | JSON array: ['WHITE', 'ASIAN', etc.] using federal codes |
| `race_federal_rollup` | TEXT | Computed: WHITE, BLACK, ASIAN, AIAN, NHOPI, TWO_OR_MORE, HISPANIC |
| **English Learner** | | |
| `is_el` | INTEGER | 0/1; current EL status |
| `el_entry_date` | TEXT | Date EL status first determined |
| `home_language_code` | TEXT | ISO 639-2 language code |
| `native_language_code` | TEXT | ISO 639-2 code |
| `el_program_type` | TEXT | pull_out, push_in, sheltered_english, dual_language, tbe_transitional, tbe_developmental |
| `english_proficiency_level` | TEXT | 1–6 or state-specific scale |
| `english_proficiency_instrument` | TEXT | WIDA ACCESS, ELPAC, TELPAS, etc. |
| `el_exit_date` | TEXT | Date reclassified as RFEP (NULL if still EL) |
| `el_exit_reason` | TEXT | RFEP (Reclassified Fluent English Proficient) |
| `is_rfep` | INTEGER | 0/1; reclassified fluent |
| `rfep_date` | TEXT | Date of reclassification |
| **Special Education (Screening flags only)** | | (detailed SPED in sr_sped_placement) |
| `is_sped` | INTEGER | 0/1; current IDEA eligibility |
| `is_504` | INTEGER | 0/1; Section 504 (not IDEA) |
| `sped_entry_date` | TEXT | Date IDEA eligibility determined |
| `sped_exit_date` | TEXT | Date exited SPED (NULL if current) |
| **Socioeconomic** | | |
| `is_economically_disadvantaged` | INTEGER | 0/1; free/reduced lunch or direct cert |
| `lunch_program_status` | TEXT | free, reduced, paid, direct_certification |
| `is_migrant` | INTEGER | 0/1; Migrant Education Program |
| **Housing** | | |
| `is_homeless` | INTEGER | 0/1; McKinney-Vento |
| `homeless_primary_nighttime_residence` | TEXT | sheltered, unsheltered, doubled_up, hotel_motel |
| `is_foster_care` | INTEGER | 0/1 |
| **Military Connected** | | |
| `is_military_connected` | INTEGER | 0/1 |
| `military_connection_type` | TEXT | active_duty, veteran, national_guard |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |
| UNIQUE(student_id) | | One supplement per student |

---

### 3.3 Special Education

#### `sr_sped_placement`
IDEA Part B placement and disability information. More detailed than the flag in student supplement.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK → educlaw_student | |
| `disability_category` | TEXT | IDEA code: AUT, DB, DD, ED, HI, ID, MD, OHI, OI, SLD, SLI, TBI, VI |
| `secondary_disability` | TEXT | Optional second disability |
| `educational_environment` | TEXT | RC_GE_80, RC_40_79, RC_LT40, SC, SS, RF, HH |
| `sped_program_entry_date` | TEXT | Date entered SPED program |
| `sped_program_exit_date` | TEXT | Date exited (NULL if current) |
| `sped_exit_reason` | TEXT | graduated, dropped_out, reached_max_age, transferred, died |
| `iep_start_date` | TEXT | Current IEP effective date |
| `iep_review_date` | TEXT | Next IEP review due date |
| `is_transition_plan_required` | INTEGER | 0/1 (age 14+ in most states) |
| `lre_percentage` | TEXT | % time in regular education setting (decimal) |
| `is_early_childhood` | INTEGER | 0/1 (ages 3-5; different environment codes) |
| `early_childhood_environment` | TEXT | early_childhood_program, home, part_time_ec_part_time_home |
| `school_year` | INTEGER | e.g., 2026 for 2025-26 |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |
| UNIQUE(student_id, school_year) | | One SPED record per student per year |

#### `sr_sped_service`
Related services provided under IDEA (not the IEP itself — a lightweight service log).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `sped_placement_id` | TEXT FK → sr_sped_placement | |
| `student_id` | TEXT FK → educlaw_student | |
| `service_type` | TEXT | speech_language, occupational_therapy, physical_therapy, counseling, audiology, orientation_mobility, special_transportation, behavior_intervention |
| `provider_type` | TEXT | school_employed, contracted |
| `minutes_per_week` | INTEGER | Minutes of service per week |
| `start_date` | TEXT | |
| `end_date` | TEXT | |
| `company_id` | TEXT FK → company | |
| `created_at`, `created_by` | TEXT | |

---

### 3.4 English Learner Program

#### `sr_el_program`
EL program enrollment history (separate from the flag in student supplement).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK → educlaw_student | |
| `program_type` | TEXT | pull_out, push_in, sheltered_english, dual_language, tbe_transitional, tbe_developmental, waiver |
| `entry_date` | TEXT | When student entered this EL program |
| `exit_date` | TEXT | When student left (NULL if current) |
| `exit_reason` | TEXT | reclassified, parent_waiver, transferred, graduated |
| `english_proficiency_assessed_date` | TEXT | Date of most recent proficiency test |
| `proficiency_level` | TEXT | 1–6 or state-specific scale |
| `proficiency_instrument` | TEXT | WIDA_ACCESS, ELPAC, TELPAS, etc. |
| `is_parent_waived` | INTEGER | 0/1; parent declined EL services |
| `waiver_date` | TEXT | |
| `school_year` | INTEGER | |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |

---

### 3.5 Discipline

#### `sr_discipline_incident`
A behavioral incident at the school level.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `naming_series` | TEXT UNIQUE | e.g., INC-2025-0001 |
| `incident_date` | TEXT | Date of incident |
| `incident_time` | TEXT | Time (HH:MM) |
| `company_id` | TEXT FK → company | |
| `school_year` | INTEGER | |
| `incident_type` | TEXT | bullying, harassment_race, harassment_sex, harassment_disability, drug_alcohol, physical_assault_student, physical_assault_staff, weapons_firearm, weapons_other, vandalism, robbery, sexual_offense, other |
| `incident_description` | TEXT | Narrative |
| `campus_location` | TEXT | classroom, hallway, cafeteria, restroom, playground, school_bus, off_campus |
| `reported_by` | TEXT | Staff member name or ID |
| `student_count_involved` | INTEGER | Total students involved |
| `created_at`, `updated_at`, `created_by` | TEXT | |

#### `sr_discipline_student`
Links students to incidents (many students can be in one incident; student can have multiple incidents).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `incident_id` | TEXT FK → sr_discipline_incident | |
| `student_id` | TEXT FK → educlaw_student | |
| `role` | TEXT | offender, victim, witness |
| `is_idea_student` | INTEGER | 0/1; auto-populated from sr_student_supplement |
| `is_504_student` | INTEGER | 0/1; auto-populated |
| `company_id` | TEXT FK → company | |
| `created_at`, `created_by` | TEXT | |

#### `sr_discipline_action`
The consequence applied to a student for a discipline incident.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `discipline_student_id` | TEXT FK → sr_discipline_student | |
| `incident_id` | TEXT FK → sr_discipline_incident | |
| `student_id` | TEXT FK → educlaw_student | |
| `action_type` | TEXT | iss (in-school suspension), oss_1_10 (1-10 day OSS), oss_gt10 (>10 day OSS), expulsion_with_services, expulsion_without_services, alternative_placement, law_enforcement_referral, school_related_arrest, no_action |
| `start_date` | TEXT | |
| `end_date` | TEXT | |
| `days_removed` | INTEGER | Total instructional days removed |
| `alternative_services_provided` | INTEGER | 0/1 |
| `alternative_services_description` | TEXT | |
| `mdr_required` | INTEGER | 0/1; Manifestation Determination Review required |
| `mdr_outcome` | TEXT | manifestation, not_manifestation, not_required |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |

---

### 3.6 Collection Windows & Snapshots

#### `sr_collection_window`
Defines a state reporting collection window.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | e.g., "Fall Enrollment 2025-26" |
| `state_code` | TEXT | Two-letter state (CA, TX, WI, etc.) |
| `window_type` | TEXT | fall_enrollment, fall_sped, winter_update, spring_enrollment, eoy_attendance, eoy_discipline, eoy_grades, staffing, crdc |
| `school_year` | INTEGER | e.g., 2026 |
| `academic_year_id` | TEXT FK → educlaw_academic_year | |
| `open_date` | TEXT | When data entry begins |
| `close_date` | TEXT | Data entry deadline |
| `snapshot_date` | TEXT | Point-in-time freeze date |
| `status` | TEXT | upcoming, open, data_entry, validation, snapshot, submitted, certified, closed |
| `required_data_categories` | TEXT | JSON array: ['enrollment', 'demographics', 'sped', 'el', 'attendance'] |
| `description` | TEXT | Notes for data coordinators |
| `is_federal_required` | INTEGER | 0/1 |
| `edfi_config_id` | TEXT FK → sr_edfi_config | Which Ed-Fi connection to use |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |
| UNIQUE(company_id, state_code, window_type, school_year) | | |

#### `sr_snapshot`
Summary record for a completed snapshot.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `collection_window_id` | TEXT FK → sr_collection_window | |
| `snapshot_taken_at` | TEXT | Actual timestamp of freeze |
| `snapshot_taken_by` | TEXT | User who triggered snapshot |
| `total_students` | INTEGER | Students in snapshot |
| `total_enrollment` | INTEGER | Active enrollments |
| `total_sped` | INTEGER | SPED students |
| `total_el` | INTEGER | EL students |
| `total_economically_disadvantaged` | INTEGER | |
| `total_homeless` | INTEGER | |
| `ada_total` | TEXT | Total ADA (decimal) — EOY windows |
| `adm_total` | TEXT | Total ADM (decimal) — EOY windows |
| `chronic_absenteeism_count` | INTEGER | EOY windows |
| `error_count_at_snapshot` | INTEGER | Unresolved errors when snapshot taken |
| `status` | TEXT | draft, finalized, certified |
| `certified_by` | TEXT | User who certified |
| `certified_at` | TEXT | |
| `certification_notes` | TEXT | |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |

#### `sr_snapshot_record`
Immutable per-student snapshot record. Stores the exact data that was submitted.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `snapshot_id` | TEXT FK → sr_snapshot | |
| `student_id` | TEXT FK → educlaw_student | Reference only; data is copied |
| `record_type` | TEXT | student_enrollment, attendance_summary, sped_placement, el_program, discipline_summary |
| `data_json` | TEXT | Complete JSON copy of the record at snapshot time |
| `school_year` | INTEGER | |
| `company_id` | TEXT FK → company | |
| `created_at` | TEXT | |
| INDEX(snapshot_id, record_type) | | Fast retrieval |

---

### 3.7 Submission Tracking

#### `sr_submission`
Tracks each submission attempt to the state.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `naming_series` | TEXT UNIQUE | e.g., SUB-2025-0001 |
| `collection_window_id` | TEXT FK → sr_collection_window | |
| `snapshot_id` | TEXT FK → sr_snapshot | |
| `submission_type` | TEXT | initial, amendment, correction |
| `submission_method` | TEXT | edfi_api, flat_file, manual_portal |
| `submitted_at` | TEXT | Timestamp of submission |
| `submitted_by` | TEXT | User who triggered submission |
| `records_submitted` | INTEGER | Total records sent |
| `records_accepted` | INTEGER | Records confirmed by state |
| `records_rejected` | INTEGER | Records rejected with errors |
| `status` | TEXT | pending, in_progress, completed, failed, certified |
| `state_confirmation_id` | TEXT | State's acknowledgment ID (if provided) |
| `state_confirmed_at` | TEXT | |
| `amendment_reason` | TEXT | Reason for amendment (if submission_type = amendment) |
| `linked_submission_id` | TEXT FK → sr_submission | Original submission being amended |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |

#### `sr_submission_error`
Tracks individual validation errors from state ODS or internal validation.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `collection_window_id` | TEXT FK → sr_collection_window | |
| `submission_id` | TEXT FK → sr_submission | NULL for pre-submission errors |
| `error_source` | TEXT | edfi_api, state_portal, internal_validation |
| `error_level` | TEXT | 1 (format), 2 (cross-entity), 3 (business_rule) |
| `severity` | TEXT | critical, major, minor, warning |
| `error_code` | TEXT | State/Ed-Fi error code |
| `error_category` | TEXT | enrollment, demographics, sped, el, attendance, discipline, staff |
| `error_message` | TEXT | Human-readable error description |
| `student_id` | TEXT FK → educlaw_student | NULL for non-student errors |
| `staff_id` | TEXT FK → employee | NULL for non-staff errors |
| `record_type` | TEXT | Which Ed-Fi resource type caused the error |
| `field_name` | TEXT | Which field has the error |
| `field_value` | TEXT | Current invalid value |
| `resolution_status` | TEXT | open, in_progress, resolved, deferred, state_waived |
| `resolution_method` | TEXT | data_corrected, descriptor_mapped, state_exception, data_not_available |
| `resolved_by` | TEXT | |
| `resolved_at` | TEXT | |
| `resolution_notes` | TEXT | |
| `assigned_to` | TEXT | Staff member responsible for resolution |
| `assigned_at` | TEXT | |
| `state_ticket_id` | TEXT | State help desk ticket number (if escalated) |
| `company_id` | TEXT FK → company | |
| `created_at`, `updated_at`, `created_by` | TEXT | |
| INDEX(collection_window_id, severity, resolution_status) | | Error dashboard query |
| INDEX(student_id, resolution_status) | | Student-level error lookup |

---

### 3.8 Validation Rules

#### `sr_validation_rule`
Library of data quality rules that can be executed pre-submission.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `rule_code` | TEXT UNIQUE | e.g., ENROLL-001, DEMO-002, SPED-003 |
| `category` | TEXT | enrollment, demographics, sped, el, attendance, discipline, staff |
| `severity` | TEXT | critical, major, minor, warning |
| `name` | TEXT | Human-readable name |
| `description` | TEXT | What the rule checks |
| `applicable_windows` | TEXT | JSON array of window_types this applies to |
| `applicable_states` | TEXT | JSON array of state codes; empty = all states |
| `is_federal_rule` | INTEGER | 0/1 |
| `sql_query` | TEXT | SQL query that returns violating records |
| `error_message_template` | TEXT | Template with {field} placeholders |
| `is_active` | INTEGER | 0/1 |
| `created_at`, `updated_at`, `created_by` | TEXT | |

#### `sr_validation_result`
Results of a validation run.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `collection_window_id` | TEXT FK → sr_collection_window | |
| `run_at` | TEXT | When validation was executed |
| `run_by` | TEXT | |
| `rule_id` | TEXT FK → sr_validation_rule | |
| `student_id` | TEXT FK → educlaw_student | NULL for non-student rules |
| `staff_id` | TEXT FK → employee | |
| `error_detail` | TEXT | Specific value that failed |
| `is_resolved` | INTEGER | 0/1 |
| `resolved_at` | TEXT | |
| `company_id` | TEXT FK → company | |
| `created_at` | TEXT | |
| INDEX(collection_window_id, is_resolved) | | |

---

### 3.9 Ed-Fi Sync Log

#### `sr_edfi_sync_log`
Records every Ed-Fi API call made (success and failure).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `config_id` | TEXT FK → sr_edfi_config | Which state connection |
| `collection_window_id` | TEXT FK → sr_collection_window | NULL for continuous sync |
| `resource_type` | TEXT | Ed-Fi resource: students, studentSchoolAssociations, etc. |
| `operation` | TEXT | POST, PUT, DELETE, GET |
| `internal_id` | TEXT | EduClaw internal record ID |
| `edfi_natural_key` | TEXT | Ed-Fi natural key sent |
| `http_status` | INTEGER | 200, 201, 400, 404, 409, 500 |
| `request_payload_hash` | TEXT | SHA256 of request body (for dedup) |
| `response_body` | TEXT | Error body from state ODS |
| `sync_status` | TEXT | success, error, retry, pending |
| `retry_count` | INTEGER | |
| `synced_at` | TEXT | Timestamp of attempt |
| `company_id` | TEXT FK → company | |
| `created_at` | TEXT | |
| INDEX(resource_type, internal_id) | | Find all syncs for a record |
| INDEX(sync_status, synced_at) | | Error dashboard |

---

## 4. Lifecycle / Status Enumerations

### Collection Window Status
```
upcoming → open → data_entry → validation → snapshot → submitted → certified → closed
```

### Submission Status
```
pending → in_progress → completed → certified
                     ↘ failed
```

### Submission Error Resolution Status
```
open → in_progress → resolved
                  ↘ deferred
                  ↘ state_waived
```

### EL Status Lifecycle
```
not_el → identified_el → active_el → rfep (reclassified)
                                   ↘ parent_waived
```

### SPED Placement Status
```
not_sped → referred → evaluated → eligible → placed → exiting → exited
                               ↘ not_eligible
```

### Discipline Action Severity (for CRDC)
```
iss → oss_1_10 → oss_gt10 → expulsion → law_enforcement_referral → school_related_arrest
```

---

## 5. Key Relationships

| Relationship | Cardinality | Notes |
|-------------|-------------|-------|
| student → sr_student_supplement | 1:1 | One supplement per student |
| student → sr_sped_placement | 1:many | One per year (student can have multiple years) |
| student → sr_el_program | 1:many | Can have multiple EL program entries |
| student → sr_discipline_student | 1:many | Can be in multiple incidents |
| incident → sr_discipline_student | 1:many | Multiple students per incident |
| discipline_student → sr_discipline_action | 1:many | Multiple actions possible |
| collection_window → sr_snapshot | 1:1 | One snapshot per window |
| snapshot → sr_snapshot_record | 1:many | One record per student/resource |
| collection_window → sr_submission | 1:many | Initial + amendments |
| submission → sr_submission_error | 1:many | Many errors per submission |
| collection_window → sr_validation_result | 1:many | Multiple validation runs |
| educlaw_student → sr_edfi_sync_log | 1:many | Multiple sync attempts |

---

## 6. ADA Calculation Logic

### Input Tables
- `educlaw_student_attendance` — daily attendance records
- `educlaw_student` + `educlaw_program_enrollment` — enrollment dates
- `educlaw_academic_year` + `educlaw_academic_term` — school year dates
- State ADA rules (configurable per state_code):
  - Does "excused" absence count toward ADA? (Yes in some states, No in others)
  - Does tardy count as full day? (Varies by minutes-late threshold)
  - Minimum minutes for full-day credit?

### ADA Formula (per student, per period)
```
Enrolled_Days = count(school_days WHERE date BETWEEN enrollment_date AND (exit_date OR period_end))
Days_Present = count(attendance WHERE status = 'present' AND date IN enrolled_period)
Days_HalfDay = count(attendance WHERE status = 'half_day' AND date IN enrolled_period)
Days_Excused = count(attendance WHERE status = 'excused' AND date IN enrolled_period)

ADA_Credit = Days_Present
           + (Days_HalfDay × 0.5)
           + (Days_Excused IF state_counts_excused ELSE 0)

Student_ADA = ADA_Credit / Enrolled_Days  [decimal, 0.0 to 1.0]
```

### District ADA
```
Total_ADA = SUM(Student_ADA_Credit) / Total_Enrolled_Days_All_Students
```

*This computed result feeds into EOY snapshot and state reporting.*

---

## 7. Ed-Fi Resource Dependency Order (for Sync)

The Ed-Fi ODS requires resources to be created in dependency order (child records cannot reference parents that don't exist).

```
Order 1:  EducationOrganization (LocalEducationAgency, School)
Order 2:  Student
Order 3:  Course, CourseOffering
Order 4:  Session, Calendar, CalendarDate
Order 5:  StaffEducationOrganizationAssociation
Order 6:  StudentSchoolAssociation (enrollment)
Order 7:  StudentEducationOrganizationAssociation (demographics)
Order 8:  StudentProgramAssociation (SPED, EL, Title programs)
Order 9:  Section, StaffSectionAssociation
Order 10: StudentSectionAssociation
Order 11: Attendance events (StudentSchoolAttendanceEvent, StudentSectionAttendanceEvent)
Order 12: DisciplineIncident → StudentDisciplineIncidentAssociation
Order 13: Grade, CourseTranscript
Order 14: StudentAssessment
```

EduClaw's sync engine must respect this order on initial bootstrap and when cascading changes.

---

## 8. Tables Summary

| Table | Purpose | Row Volume |
|-------|---------|------------|
| `sr_org_mapping` | NCES/Ed-Fi identifiers | ~10–50 rows (schools in district) |
| `sr_edfi_config` | State connection config | ~1–5 rows (states served) |
| `sr_edfi_descriptor_map` | Code → URI mappings | ~200–500 rows |
| `sr_student_supplement` | State reporting fields | 1 per student |
| `sr_sped_placement` | SPED placement per year | 1 per SPED student per year |
| `sr_sped_service` | IEP related services | ~3–5 per SPED student |
| `sr_el_program` | EL program enrollment | 1–3 per EL student |
| `sr_discipline_incident` | School incidents | 100–500/year for mid-size district |
| `sr_discipline_student` | Student × incident | 1–3 per incident |
| `sr_discipline_action` | Consequences per student per incident | 1–2 per discipline_student |
| `sr_collection_window` | Annual windows | 4–8 per year per state |
| `sr_snapshot` | Window snapshots | 1 per window |
| `sr_snapshot_record` | Frozen student data | 1 per student per window |
| `sr_submission` | Submission history | 1–3 per window (amendments) |
| `sr_submission_error` | Validation errors | 50–2000 per window |
| `sr_validation_rule` | Rule library | 100–500 rules |
| `sr_validation_result` | Rule check results | 1 per student per rule per run |
| `sr_edfi_sync_log` | API call log | High volume; purge after 90 days |
