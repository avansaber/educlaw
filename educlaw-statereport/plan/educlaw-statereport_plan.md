# EduClaw State Reporting — Implementation Plan

## 1. Product Overview

| Attribute | Value |
| --- | --- |
| **Product Name** | educlaw-statereport |
| **Display Name** | EduClaw State Reporting |
| **Description** | State reporting, Ed-Fi integration, data validation, and submission tracking |
| **Parent Product** | educlaw |
| **Parent Path** | educlaw |
| **Skill Prefix** | educlaw-statereport |
| **Table Prefix** | `sr_` |

### What This Product Does

EduClaw State Reporting is a sub-vertical of EduClaw that transforms EduClaw's operational K-12 student data into compliant state and federal reporting submissions. It addresses one of the most financially critical and legally required functions in K-12 education: reporting student enrollment, attendance, special education, discipline, and staff data to State Education Agencies (SEAs) via the Ed-Fi ODS/API standard and ultimately to federal systems (EDFacts, CRDC, IDEA 618).

EduClaw already captures 70% of the needed operational data (students, enrollment, attendance, grades). This product adds the remaining 30%: state-specific supplemental data (race/ethnicity, SSID, SPED disability category, EL status, discipline incidents) plus the complete reporting infrastructure (collection windows, snapshot engine, Ed-Fi API client, validation rules engine, submission tracking with certification and amendment workflow).

### Target Domains and Scope

| Domain | Scope |
| --- | --- |
| `state_reporting` | Collection windows, snapshot engine, ADA/ADM calculation, chronic absenteeism, ADA funding dashboard, enrollment reports, org-to-NCES mapping |
| `ed_fi` | Ed-Fi ODS/API connection configuration, OAuth token management, descriptor mapping, dependency-ordered sync engine, sync log |
| `data_validation` | Validation rule library (100+ rules), pre-submission validation runs, error dashboard, error assignment, resolution tracking |
| `submission_tracking` | Submission history, certification workflow, amendment tracking, submission audit trail, export package |
| `demographics` | Student supplement (race/ethnicity, SSID, EL flags, SPED flags, economic status, homeless, military), EL program history, SPED placement + services |
| `discipline` | CRDC-aligned discipline incidents, student involvement records, disciplinary actions, IDEA manifestation determination |

### Foundation Dependencies

| Foundation Skill | Used For |
| --- | --- |
| erpclaw-setup | DB, company/LEA record, employee (staff) table, audit(), naming, response, RBAC |
| erpclaw-hr | employee table (staff FTE, certifications referenced by staff reporting) |
| erpclaw-gl | Not used directly — state reporting is non-financial; GL irrelevant to this product |
| erpclaw-selling | Not used directly in state reporting |
| erpclaw-payments | Not used directly in state reporting |

---

## 2. Domain Organization

| Domain | Module File | Scope |
| --- | --- | --- |
| state_reporting | state_reporting.py | Collection windows, snapshot engine, ADA calculation, chronic absenteeism, ADA dashboard, enrollment/CRDC reports, org mapping to NCES identifiers |
| ed_fi | ed_fi.py | Ed-Fi ODS connection configuration (per state per year), OAuth client config, descriptor URI mapping, dependency-ordered sync engine, Ed-Fi sync log |
| data_validation | data_validation.py | Validation rule library, validation run execution, validation results, submission error management, error assignment and resolution workflow |
| submission_tracking | submission_tracking.py | Submission records, status lifecycle, certification, amendment creation, submission history, export package for audit defense |
| demographics | demographics.py | Student supplement (race, SSID, EL, SPED, economic, homeless, foster, military flags), SPED placement per year, SPED related services, EL program enrollment history |
| discipline | discipline.py | Discipline incidents (CRDC-aligned types), student–incident junction records (roles, IDEA/504 flags), disciplinary actions (ISS/OSS/expulsion), MDR workflow, discipline summary reports |

---

## 3. Database Schema

### 3.1 Tables (New — `sr_` prefix)

All tables follow ERPClaw conventions:
- Primary key: `id TEXT PRIMARY KEY` (UUID4)
- Timestamps: `created_at TEXT`, `updated_at TEXT` (ISO 8601), `created_by TEXT`
- Money: TEXT (Decimal string)
- Status fields: TEXT with CHECK constraints
- Multi-tenant: `company_id TEXT NOT NULL REFERENCES company(id)` on all tables

---

#### `sr_org_mapping`
Maps EduClaw company (LEA) and schools to NCES federal identifiers and Ed-Fi organization identifiers. Required for all Ed-Fi submissions and federal reporting.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `company_id` | TEXT | NOT NULL, FK → company(id) ON DELETE RESTRICT | EduClaw LEA record |
| `nces_lea_id` | TEXT | NOT NULL DEFAULT '' | 7-digit NCES LEA ID (e.g., "0600005") |
| `nces_school_id` | TEXT | NOT NULL DEFAULT '' | 12-digit NCES School ID; empty for district-level records |
| `state_code` | TEXT | NOT NULL DEFAULT '' CHECK(length(state_code)=2 OR state_code='') | 2-letter US state code (CA, TX, WI) |
| `state_lea_id` | TEXT | NOT NULL DEFAULT '' | State-assigned district identifier (separate from NCES) |
| `state_school_id` | TEXT | NOT NULL DEFAULT '' | State-assigned school identifier |
| `edfi_lea_id` | TEXT | NOT NULL DEFAULT '' | Ed-Fi LocalEducationAgency natural key |
| `edfi_school_id` | TEXT | NOT NULL DEFAULT '' | Ed-Fi School natural key |
| `crdc_school_id` | TEXT | NOT NULL DEFAULT '' | CRDC school identifier (usually = NCES school ID) |
| `is_title_i_school` | INTEGER | NOT NULL DEFAULT 0 | 0/1 Title I eligibility flag |
| `title_i_status` | TEXT | NOT NULL DEFAULT '' CHECK(title_i_status IN ('targeted_assistance','schoolwide','not_title_i','')) | Title I program type |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |
| UNIQUE | (company_id, state_code, nces_school_id) | | One record per LEA per state per school |

**Indexes:**
- `idx_sr_org_mapping_company_state ON sr_org_mapping(company_id, state_code)`
- `idx_sr_org_mapping_nces_lea ON sr_org_mapping(nces_lea_id)`
- `idx_sr_org_mapping_nces_school ON sr_org_mapping(nces_school_id)`

---

#### `sr_edfi_config`
Ed-Fi ODS/API connection configuration per state per school year. Stores OAuth credentials (encrypted) for each state data pipeline.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `profile_name` | TEXT | NOT NULL DEFAULT '' | Human-readable name (e.g., "Texas TSDS 2025-26") |
| `state_code` | TEXT | NOT NULL DEFAULT '' | Target state (CA, TX, WI, etc.) |
| `school_year` | INTEGER | NOT NULL DEFAULT 0 | Reporting year (2026 = SY 2025-26) |
| `ods_base_url` | TEXT | NOT NULL DEFAULT '' | Ed-Fi ODS API base URL |
| `oauth_token_url` | TEXT | NOT NULL DEFAULT '' | OAuth 2.0 token endpoint URL |
| `oauth_client_id` | TEXT | NOT NULL DEFAULT '' | OAuth client ID |
| `oauth_client_secret_encrypted` | TEXT | NOT NULL DEFAULT '' | AES-256 encrypted OAuth secret |
| `api_version` | TEXT | NOT NULL DEFAULT '7' CHECK(api_version IN ('5','6','7')) | Ed-Fi ODS/API major version |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | 0/1 |
| `last_tested_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of last successful connection test |
| `last_token_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of last OAuth token fetch |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |
| UNIQUE | (company_id, state_code, school_year) | | One config per LEA per state per year |

**Indexes:**
- `idx_sr_edfi_config_company_state ON sr_edfi_config(company_id, state_code, is_active)`
- `idx_sr_edfi_config_year ON sr_edfi_config(company_id, school_year)`

---

#### `sr_edfi_descriptor_map`
Maps EduClaw internal codes to Ed-Fi descriptor URIs. Each state may have its own descriptor namespace extensions. Required before any Ed-Fi sync can produce valid submissions.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `config_id` | TEXT | NOT NULL FK → sr_edfi_config(id) ON DELETE RESTRICT | Which state/year config this mapping belongs to |
| `descriptor_type` | TEXT | NOT NULL DEFAULT '' CHECK(descriptor_type IN ('grade_level','race','sex','attendance_event','disability','language','exit_type','entry_type','discipline_behavior','discipline_action','sped_environment','program_type','credential_type','course_level','homeless_residence')) | Category of descriptor |
| `internal_code` | TEXT | NOT NULL DEFAULT '' | EduClaw internal value |
| `edfi_descriptor_uri` | TEXT | NOT NULL DEFAULT '' | Full Ed-Fi descriptor URI (e.g., "uri://ed-fi.org/RaceDescriptor#White") |
| `description` | TEXT | NOT NULL DEFAULT '' | Human-readable note about this mapping |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |
| UNIQUE | (config_id, descriptor_type, internal_code) | | No duplicate mappings per type per config |

**Indexes:**
- `idx_sr_descriptor_config_type ON sr_edfi_descriptor_map(config_id, descriptor_type, is_active)`
- `idx_sr_descriptor_internal ON sr_edfi_descriptor_map(config_id, internal_code)`

---

#### `sr_edfi_sync_log`
Immutable log of every Ed-Fi API call made. Records success and failure with HTTP status, payload hash, and response body. Used for retry management and error analysis.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `config_id` | TEXT | NOT NULL FK → sr_edfi_config(id) ON DELETE RESTRICT | Which state connection |
| `collection_window_id` | TEXT | FK → sr_collection_window(id) ON DELETE RESTRICT | NULL for continuous/nightly sync |
| `resource_type` | TEXT | NOT NULL DEFAULT '' | Ed-Fi resource name (students, studentSchoolAssociations, etc.) |
| `operation` | TEXT | NOT NULL DEFAULT '' CHECK(operation IN ('POST','PUT','DELETE','GET')) | HTTP method used |
| `internal_id` | TEXT | NOT NULL DEFAULT '' | EduClaw record ID being synced |
| `edfi_natural_key` | TEXT | NOT NULL DEFAULT '' | Ed-Fi natural key JSON sent |
| `http_status` | INTEGER | NOT NULL DEFAULT 0 | HTTP response status code |
| `request_payload_hash` | TEXT | NOT NULL DEFAULT '' | SHA-256 hash of request body (for deduplication) |
| `response_body` | TEXT | NOT NULL DEFAULT '' | Error or confirmation body from state ODS |
| `sync_status` | TEXT | NOT NULL DEFAULT 'pending' CHECK(sync_status IN ('success','error','retry','pending','skipped')) | |
| `retry_count` | INTEGER | NOT NULL DEFAULT 0 | Number of retry attempts |
| `synced_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of this attempt |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |

**Indexes:**
- `idx_sr_sync_log_resource_internal ON sr_edfi_sync_log(resource_type, internal_id)`
- `idx_sr_sync_log_status_time ON sr_edfi_sync_log(sync_status, synced_at)`
- `idx_sr_sync_log_config_window ON sr_edfi_sync_log(config_id, collection_window_id)`
- `idx_sr_sync_log_company_status ON sr_edfi_sync_log(company_id, sync_status)`

---

#### `sr_student_supplement`
**Critical table.** One-to-one extension of `educlaw_student` with all state reporting-specific demographic data elements not captured in the operational student table. Race/ethnicity, SSID, EL flag, SPED flag, economic status, homeless, foster care, military connected.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `student_id` | TEXT | NOT NULL UNIQUE FK → educlaw_student(id) ON DELETE RESTRICT | One supplement per student |
| `ssid` | TEXT | NOT NULL DEFAULT '' | State Student Identifier |
| `ssid_state_code` | TEXT | NOT NULL DEFAULT '' | Which state issued this SSID |
| `ssid_status` | TEXT | NOT NULL DEFAULT 'pending' CHECK(ssid_status IN ('pending','assigned','not_applicable')) | SSID assignment status |
| `is_hispanic_latino` | INTEGER | NOT NULL DEFAULT 0 | 0/1; federal OMB ethnicity question (asked separately from race) |
| `race_codes` | TEXT | NOT NULL DEFAULT '[]' | JSON array of federal race codes: WHITE, BLACK, ASIAN, AIAN, NHOPI |
| `race_federal_rollup` | TEXT | NOT NULL DEFAULT '' CHECK(race_federal_rollup IN ('WHITE','BLACK_OR_AFRICAN_AMERICAN','ASIAN','AMERICAN_INDIAN_OR_ALASKA_NATIVE','NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER','TWO_OR_MORE_RACES','HISPANIC_OR_LATINO','')) | Computed federal rollup per OMB rules |
| `is_el` | INTEGER | NOT NULL DEFAULT 0 | 0/1; current English Learner status |
| `el_entry_date` | TEXT | NOT NULL DEFAULT '' | Date EL status first determined |
| `home_language_code` | TEXT | NOT NULL DEFAULT '' | ISO 639-2 home language code |
| `native_language_code` | TEXT | NOT NULL DEFAULT '' | ISO 639-2 native language code |
| `english_proficiency_level` | TEXT | NOT NULL DEFAULT '' | 1–6 or state-specific scale value |
| `english_proficiency_instrument` | TEXT | NOT NULL DEFAULT '' CHECK(english_proficiency_instrument IN ('WIDA_ACCESS','ELPAC','TELPAS','LAS_LINKS','IPT','OTHER','')) | Assessment used to determine proficiency |
| `el_exit_date` | TEXT | NOT NULL DEFAULT '' | Date reclassified as RFEP (empty if still EL) |
| `is_rfep` | INTEGER | NOT NULL DEFAULT 0 | 0/1; Reclassified Fluent English Proficient |
| `rfep_date` | TEXT | NOT NULL DEFAULT '' | Date of RFEP reclassification |
| `is_sped` | INTEGER | NOT NULL DEFAULT 0 | 0/1; current IDEA Part B eligibility |
| `is_504` | INTEGER | NOT NULL DEFAULT 0 | 0/1; Section 504 (not IDEA) |
| `sped_entry_date` | TEXT | NOT NULL DEFAULT '' | Date IDEA eligibility was determined |
| `sped_exit_date` | TEXT | NOT NULL DEFAULT '' | Date exited SPED (empty if currently in SPED) |
| `is_economically_disadvantaged` | INTEGER | NOT NULL DEFAULT 0 | 0/1; free/reduced lunch or direct cert |
| `lunch_program_status` | TEXT | NOT NULL DEFAULT '' CHECK(lunch_program_status IN ('free','reduced','paid','direct_certification','')) | Free/Reduced lunch eligibility |
| `is_migrant` | INTEGER | NOT NULL DEFAULT 0 | 0/1; Migrant Education Program participation |
| `is_homeless` | INTEGER | NOT NULL DEFAULT 0 | 0/1; McKinney-Vento homeless status |
| `homeless_primary_nighttime_residence` | TEXT | NOT NULL DEFAULT '' CHECK(homeless_primary_nighttime_residence IN ('sheltered','unsheltered','doubled_up','hotel_motel','')) | Nighttime residence type for homeless students |
| `is_foster_care` | INTEGER | NOT NULL DEFAULT 0 | 0/1; foster care status |
| `is_military_connected` | INTEGER | NOT NULL DEFAULT 0 | 0/1 |
| `military_connection_type` | TEXT | NOT NULL DEFAULT '' CHECK(military_connection_type IN ('active_duty','veteran','national_guard','')) | |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_supplement_student ON sr_student_supplement(student_id)`
- `idx_sr_supplement_ssid ON sr_student_supplement(ssid, ssid_state_code)`
- `idx_sr_supplement_company_el ON sr_student_supplement(company_id, is_el)`
- `idx_sr_supplement_company_sped ON sr_student_supplement(company_id, is_sped)`
- `idx_sr_supplement_company_econ ON sr_student_supplement(company_id, is_economically_disadvantaged)`
- `idx_sr_supplement_ssid_status ON sr_student_supplement(company_id, ssid_status)`
- `idx_sr_supplement_race_rollup ON sr_student_supplement(company_id, race_federal_rollup)`

---

#### `sr_sped_placement`
IDEA Part B special education placement record per student per school year. Captures disability category, educational environment, and IEP dates for IDEA 618 child count and educational environments reporting.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `student_id` | TEXT | NOT NULL FK → educlaw_student(id) ON DELETE RESTRICT | |
| `school_year` | INTEGER | NOT NULL DEFAULT 0 | e.g., 2026 for SY 2025-26 |
| `disability_category` | TEXT | NOT NULL DEFAULT '' CHECK(disability_category IN ('AUT','DB','DD','ED','HI','ID','MD','OHI','OI','SLD','SLI','TBI','VI','')) | IDEA 14-category disability code |
| `secondary_disability` | TEXT | NOT NULL DEFAULT '' | Optional second IDEA disability code |
| `educational_environment` | TEXT | NOT NULL DEFAULT '' CHECK(educational_environment IN ('RC_80','RC_40_79','RC_LT40','SC','SS','RF','HH','')) | IDEA placement (% time in regular class) |
| `sped_program_entry_date` | TEXT | NOT NULL DEFAULT '' | Date entered IDEA SPED program |
| `sped_program_exit_date` | TEXT | NOT NULL DEFAULT '' | Date exited program (empty if current) |
| `sped_exit_reason` | TEXT | NOT NULL DEFAULT '' CHECK(sped_exit_reason IN ('graduated','dropped_out','reached_max_age','transferred','died','not_eligible','')) | Reason for exiting SPED |
| `iep_start_date` | TEXT | NOT NULL DEFAULT '' | Current IEP effective date |
| `iep_review_date` | TEXT | NOT NULL DEFAULT '' | Next IEP annual review due date |
| `is_transition_plan_required` | INTEGER | NOT NULL DEFAULT 0 | 0/1; age 14+ in most states |
| `lre_percentage` | TEXT | NOT NULL DEFAULT '' | % time in regular education setting (decimal string) |
| `is_early_childhood` | INTEGER | NOT NULL DEFAULT 0 | 0/1; ages 3-5 (different environment codes apply) |
| `early_childhood_environment` | TEXT | NOT NULL DEFAULT '' CHECK(early_childhood_environment IN ('early_childhood_program','home','part_time_ec_part_time_home','')) | EC placement type (used if is_early_childhood=1) |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |
| UNIQUE | (student_id, school_year) | | One SPED record per student per year |

**Indexes:**
- `idx_sr_sped_student_year ON sr_sped_placement(student_id, school_year)`
- `idx_sr_sped_company_year ON sr_sped_placement(company_id, school_year)`
- `idx_sr_sped_disability ON sr_sped_placement(company_id, disability_category, school_year)`
- `idx_sr_sped_environment ON sr_sped_placement(company_id, educational_environment, school_year)`

---

#### `sr_sped_service`
Related services provided under IDEA (speech therapy, OT, PT, etc.). Supports IDEA 618 personnel and services data. Linked to a SPED placement record.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `sped_placement_id` | TEXT | NOT NULL FK → sr_sped_placement(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL FK → educlaw_student(id) ON DELETE RESTRICT | Denormalized for direct lookup |
| `service_type` | TEXT | NOT NULL DEFAULT '' CHECK(service_type IN ('speech_language','occupational_therapy','physical_therapy','counseling','audiology','orientation_mobility','special_transportation','behavior_intervention','vision_services','other')) | Type of related service |
| `provider_type` | TEXT | NOT NULL DEFAULT '' CHECK(provider_type IN ('school_employed','contracted','')) | |
| `minutes_per_week` | INTEGER | NOT NULL DEFAULT 0 | Minutes of service per week (positive integer) |
| `start_date` | TEXT | NOT NULL DEFAULT '' | |
| `end_date` | TEXT | NOT NULL DEFAULT '' | Empty if service is ongoing |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_sped_service_placement ON sr_sped_service(sped_placement_id)`
- `idx_sr_sped_service_student ON sr_sped_service(student_id)`
- `idx_sr_sped_service_type ON sr_sped_service(company_id, service_type)`

---

#### `sr_el_program`
EL program enrollment history for English Learner students. Tracks program type, proficiency assessment dates, entry/exit, reclassification. Used for Title III reporting and EDFacts EL counts.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `student_id` | TEXT | NOT NULL FK → educlaw_student(id) ON DELETE RESTRICT | |
| `school_year` | INTEGER | NOT NULL DEFAULT 0 | |
| `program_type` | TEXT | NOT NULL DEFAULT '' CHECK(program_type IN ('pull_out','push_in','sheltered_english','dual_language','tbe_transitional','tbe_developmental','waiver','content_based')) | |
| `entry_date` | TEXT | NOT NULL DEFAULT '' | Date student entered this EL program |
| `exit_date` | TEXT | NOT NULL DEFAULT '' | Date student left (empty if currently enrolled) |
| `exit_reason` | TEXT | NOT NULL DEFAULT '' CHECK(exit_reason IN ('reclassified','parent_waiver','transferred','graduated','')) | |
| `english_proficiency_assessed_date` | TEXT | NOT NULL DEFAULT '' | Date of most recent proficiency test |
| `proficiency_level` | TEXT | NOT NULL DEFAULT '' | 1–6 or state-specific scale value |
| `proficiency_instrument` | TEXT | NOT NULL DEFAULT '' CHECK(proficiency_instrument IN ('WIDA_ACCESS','ELPAC','TELPAS','LAS_LINKS','IPT','OTHER','')) | Assessment instrument |
| `is_parent_waived` | INTEGER | NOT NULL DEFAULT 0 | 0/1; parent declined EL services |
| `waiver_date` | TEXT | NOT NULL DEFAULT '' | Date of parent waiver |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_el_program_student_year ON sr_el_program(student_id, school_year)`
- `idx_sr_el_program_company_year ON sr_el_program(company_id, school_year)`
- `idx_sr_el_program_exit ON sr_el_program(company_id, exit_date)`

---

#### `sr_discipline_incident`
A behavioral incident at a school. Aligned with CRDC incident type vocabulary. One incident can involve multiple students.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `naming_series` | TEXT | NOT NULL UNIQUE DEFAULT '' | e.g., INC-2026-00001 |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `school_year` | INTEGER | NOT NULL DEFAULT 0 | |
| `incident_date` | TEXT | NOT NULL DEFAULT '' | Date of incident (YYYY-MM-DD) |
| `incident_time` | TEXT | NOT NULL DEFAULT '' | Time of incident (HH:MM) |
| `incident_type` | TEXT | NOT NULL DEFAULT '' CHECK(incident_type IN ('bullying','harassment_race','harassment_sex','harassment_disability','harassment_other','drug_alcohol','physical_assault_student','physical_assault_staff','weapons_firearm','weapons_other','vandalism','robbery','sexual_offense','restraint','seclusion','insubordination','other')) | CRDC-aligned incident classification |
| `incident_description` | TEXT | NOT NULL DEFAULT '' | Narrative description |
| `campus_location` | TEXT | NOT NULL DEFAULT '' CHECK(campus_location IN ('classroom','hallway','cafeteria','restroom','playground','gymnasium','school_bus','off_campus','online','other','')) | Location where incident occurred |
| `reported_by` | TEXT | NOT NULL DEFAULT '' | Name or employee ID of staff reporting |
| `student_count_involved` | INTEGER | NOT NULL DEFAULT 0 | Total students involved (auto-updated) |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_discipline_incident_company_year ON sr_discipline_incident(company_id, school_year)`
- `idx_sr_discipline_incident_date ON sr_discipline_incident(incident_date)`
- `idx_sr_discipline_incident_type ON sr_discipline_incident(company_id, incident_type, school_year)`
- `idx_sr_discipline_incident_series ON sr_discipline_incident(naming_series)`

---

#### `sr_discipline_student`
Junction table: links students to discipline incidents with their role (offender, victim, witness). Auto-populated IDEA and 504 flags from `sr_student_supplement`.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `incident_id` | TEXT | NOT NULL FK → sr_discipline_incident(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL FK → educlaw_student(id) ON DELETE RESTRICT | |
| `role` | TEXT | NOT NULL DEFAULT '' CHECK(role IN ('offender','victim','witness')) | Student's role in the incident |
| `is_idea_student` | INTEGER | NOT NULL DEFAULT 0 | 0/1; auto-populated from sr_student_supplement.is_sped |
| `is_504_student` | INTEGER | NOT NULL DEFAULT 0 | 0/1; auto-populated from sr_student_supplement.is_504 |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |
| UNIQUE | (incident_id, student_id, role) | | |

**Indexes:**
- `idx_sr_discipline_student_incident ON sr_discipline_student(incident_id)`
- `idx_sr_discipline_student_student ON sr_discipline_student(student_id)`
- `idx_sr_discipline_student_idea ON sr_discipline_student(is_idea_student)`

---

#### `sr_discipline_action`
The disciplinary consequence applied to a specific student for a specific incident. CRDC-aligned action types with days-removed tracking. Includes IDEA Manifestation Determination Review.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `discipline_student_id` | TEXT | NOT NULL FK → sr_discipline_student(id) ON DELETE RESTRICT | |
| `incident_id` | TEXT | NOT NULL FK → sr_discipline_incident(id) ON DELETE RESTRICT | Denormalized for fast query |
| `student_id` | TEXT | NOT NULL FK → educlaw_student(id) ON DELETE RESTRICT | Denormalized for fast query |
| `action_type` | TEXT | NOT NULL DEFAULT '' CHECK(action_type IN ('iss','oss_1_10','oss_gt10','expulsion_with_services','expulsion_without_services','alternative_placement','law_enforcement_referral','school_related_arrest','no_action')) | CRDC-aligned action type |
| `start_date` | TEXT | NOT NULL DEFAULT '' | |
| `end_date` | TEXT | NOT NULL DEFAULT '' | |
| `days_removed` | INTEGER | NOT NULL DEFAULT 0 | Total instructional days removed from school |
| `alternative_services_provided` | INTEGER | NOT NULL DEFAULT 0 | 0/1; educational services during removal |
| `alternative_services_description` | TEXT | NOT NULL DEFAULT '' | |
| `mdr_required` | INTEGER | NOT NULL DEFAULT 0 | 0/1; IDEA MDR required (IDEA student + >10 day suspension) |
| `mdr_outcome` | TEXT | NOT NULL DEFAULT '' CHECK(mdr_outcome IN ('manifestation','not_manifestation','not_required','pending','')) | Manifestation Determination Review outcome |
| `mdr_date` | TEXT | NOT NULL DEFAULT '' | Date MDR was conducted |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_discipline_action_student ON sr_discipline_action(discipline_student_id)`
- `idx_sr_discipline_action_incident ON sr_discipline_action(incident_id)`
- `idx_sr_discipline_action_student_id ON sr_discipline_action(student_id)`
- `idx_sr_discipline_action_type ON sr_discipline_action(company_id, action_type)`
- `idx_sr_discipline_action_mdr ON sr_discipline_action(mdr_required, mdr_outcome)`

---

#### `sr_collection_window`
Defines a state reporting collection window (Fall Enrollment, EOY Attendance, etc.). Controls the snapshot and submission lifecycle. Each window has a status lifecycle and links to an Ed-Fi config.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `name` | TEXT | NOT NULL DEFAULT '' | Human-readable name (e.g., "Fall Enrollment 2025-26") |
| `state_code` | TEXT | NOT NULL DEFAULT '' | Two-letter state code |
| `window_type` | TEXT | NOT NULL DEFAULT '' CHECK(window_type IN ('fall_enrollment','fall_sped','winter_update','spring_enrollment','eoy_attendance','eoy_discipline','eoy_grades','staffing','crdc','summer_correction')) | Collection type |
| `school_year` | INTEGER | NOT NULL DEFAULT 0 | e.g., 2026 for SY 2025-26 |
| `academic_year_id` | TEXT | FK → educlaw_academic_year(id) ON DELETE RESTRICT | Links to EduClaw academic calendar |
| `open_date` | TEXT | NOT NULL DEFAULT '' | When data entry/sync begins |
| `close_date` | TEXT | NOT NULL DEFAULT '' | Data entry deadline |
| `snapshot_date` | TEXT | NOT NULL DEFAULT '' | Point-in-time freeze date |
| `status` | TEXT | NOT NULL DEFAULT 'upcoming' CHECK(status IN ('upcoming','open','data_entry','validation','snapshot','submitted','certified','closed')) | Window lifecycle status |
| `required_data_categories` | TEXT | NOT NULL DEFAULT '[]' | JSON array: ['enrollment','demographics','sped','el','attendance','discipline','staff'] |
| `description` | TEXT | NOT NULL DEFAULT '' | Notes for data coordinators |
| `is_federal_required` | INTEGER | NOT NULL DEFAULT 0 | 0/1; whether this window has federal submission requirement |
| `edfi_config_id` | TEXT | FK → sr_edfi_config(id) ON DELETE RESTRICT | Which Ed-Fi connection to use for this window |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |
| UNIQUE | (company_id, state_code, window_type, school_year) | | One window per LEA per type per year |

**Indexes:**
- `idx_sr_collection_window_company_status ON sr_collection_window(company_id, status)`
- `idx_sr_collection_window_year_state ON sr_collection_window(company_id, school_year, state_code)`
- `idx_sr_collection_window_type ON sr_collection_window(company_id, window_type, school_year)`
- `idx_sr_collection_window_dates ON sr_collection_window(open_date, close_date)`

---

#### `sr_snapshot`
Summary record for a completed snapshot. Created when a collection window reaches `snapshot` status. Contains summary counts and certification metadata.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `collection_window_id` | TEXT | NOT NULL UNIQUE FK → sr_collection_window(id) ON DELETE RESTRICT | One snapshot per window |
| `snapshot_taken_at` | TEXT | NOT NULL DEFAULT '' | ISO 8601 timestamp of data freeze |
| `snapshot_taken_by` | TEXT | NOT NULL DEFAULT '' | User ID who triggered snapshot |
| `total_students` | INTEGER | NOT NULL DEFAULT 0 | Students included in this snapshot |
| `total_enrollment` | INTEGER | NOT NULL DEFAULT 0 | Active program enrollments at snapshot time |
| `total_sped` | INTEGER | NOT NULL DEFAULT 0 | IDEA-eligible students at snapshot |
| `total_el` | INTEGER | NOT NULL DEFAULT 0 | EL students at snapshot |
| `total_economically_disadvantaged` | INTEGER | NOT NULL DEFAULT 0 | |
| `total_homeless` | INTEGER | NOT NULL DEFAULT 0 | |
| `ada_total` | TEXT | NOT NULL DEFAULT '' | District ADA as decimal string (EOY windows) |
| `adm_total` | TEXT | NOT NULL DEFAULT '' | District ADM as decimal string (EOY windows) |
| `chronic_absenteeism_count` | INTEGER | NOT NULL DEFAULT 0 | Students ≥10% absent days (EOY windows) |
| `error_count_at_snapshot` | INTEGER | NOT NULL DEFAULT 0 | Unresolved errors at time of snapshot |
| `status` | TEXT | NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','finalized','certified')) | |
| `certified_by` | TEXT | NOT NULL DEFAULT '' | User who certified |
| `certified_at` | TEXT | NOT NULL DEFAULT '' | |
| `certification_notes` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_snapshot_window ON sr_snapshot(collection_window_id)`
- `idx_sr_snapshot_company_status ON sr_snapshot(company_id, status)`

---

#### `sr_snapshot_record`
Immutable per-student snapshot records. Stores the complete JSON copy of each student's reporting data at the exact moment of snapshot freeze. This table is the audit-defensible record of what was submitted to the state.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `snapshot_id` | TEXT | NOT NULL FK → sr_snapshot(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | FK → educlaw_student(id) ON DELETE RESTRICT | NULL for non-student records (e.g., staff) |
| `record_type` | TEXT | NOT NULL DEFAULT '' CHECK(record_type IN ('student_enrollment','attendance_summary','sped_placement','el_program','discipline_summary','staff_assignment')) | Category of frozen record |
| `data_json` | TEXT | NOT NULL DEFAULT '{}' | Complete JSON snapshot of this record at freeze time |
| `school_year` | INTEGER | NOT NULL DEFAULT 0 | |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |

**Indexes:**
- `idx_sr_snapshot_record_snapshot_type ON sr_snapshot_record(snapshot_id, record_type)`
- `idx_sr_snapshot_record_student ON sr_snapshot_record(snapshot_id, student_id)`
- `idx_sr_snapshot_record_company ON sr_snapshot_record(company_id, school_year)`

---

#### `sr_submission`
Tracks each submission attempt to the state system. Supports initial, amendment, and correction submission types with full status lifecycle.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `naming_series` | TEXT | NOT NULL UNIQUE DEFAULT '' | e.g., SUB-2026-00001 |
| `collection_window_id` | TEXT | NOT NULL FK → sr_collection_window(id) ON DELETE RESTRICT | |
| `snapshot_id` | TEXT | FK → sr_snapshot(id) ON DELETE RESTRICT | Which snapshot was submitted |
| `submission_type` | TEXT | NOT NULL DEFAULT 'initial' CHECK(submission_type IN ('initial','amendment','correction')) | |
| `submission_method` | TEXT | NOT NULL DEFAULT '' CHECK(submission_method IN ('edfi_api','flat_file','manual_portal')) | How data was submitted |
| `submitted_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of submission |
| `submitted_by` | TEXT | NOT NULL DEFAULT '' | User who triggered submission |
| `records_submitted` | INTEGER | NOT NULL DEFAULT 0 | Total records sent |
| `records_accepted` | INTEGER | NOT NULL DEFAULT 0 | Records confirmed by state |
| `records_rejected` | INTEGER | NOT NULL DEFAULT 0 | Records rejected with errors |
| `status` | TEXT | NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in_progress','completed','failed','certified')) | |
| `state_confirmation_id` | TEXT | NOT NULL DEFAULT '' | State's acknowledgment/confirmation ID |
| `state_confirmed_at` | TEXT | NOT NULL DEFAULT '' | When state confirmed receipt |
| `amendment_reason` | TEXT | NOT NULL DEFAULT '' | Reason for amendment (if submission_type = amendment) |
| `linked_submission_id` | TEXT | FK → sr_submission(id) ON DELETE RESTRICT | Original submission being amended |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_submission_window ON sr_submission(collection_window_id)`
- `idx_sr_submission_company_status ON sr_submission(company_id, status)`
- `idx_sr_submission_series ON sr_submission(naming_series)`
- `idx_sr_submission_linked ON sr_submission(linked_submission_id)`

---

#### `sr_submission_error`
Tracks individual validation errors from Ed-Fi ODS responses, state portal, or internal pre-submission validation. Supports assignment to staff, resolution tracking, and state escalation.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `collection_window_id` | TEXT | NOT NULL FK → sr_collection_window(id) ON DELETE RESTRICT | |
| `submission_id` | TEXT | FK → sr_submission(id) ON DELETE RESTRICT | NULL for pre-submission validation errors |
| `error_source` | TEXT | NOT NULL DEFAULT '' CHECK(error_source IN ('edfi_api','state_portal','internal_validation')) | |
| `error_level` | TEXT | NOT NULL DEFAULT '' CHECK(error_level IN ('1','2','3')) | 1=format, 2=cross-entity, 3=business_rule |
| `severity` | TEXT | NOT NULL DEFAULT '' CHECK(severity IN ('critical','major','minor','warning')) | |
| `error_code` | TEXT | NOT NULL DEFAULT '' | State/Ed-Fi error code |
| `error_category` | TEXT | NOT NULL DEFAULT '' CHECK(error_category IN ('enrollment','demographics','sped','el','attendance','discipline','staff','calendar','other')) | |
| `error_message` | TEXT | NOT NULL DEFAULT '' | Human-readable error description |
| `student_id` | TEXT | FK → educlaw_student(id) ON DELETE RESTRICT | NULL for non-student errors |
| `staff_id` | TEXT | FK → employee(id) ON DELETE RESTRICT | NULL for non-staff errors |
| `record_type` | TEXT | NOT NULL DEFAULT '' | Which Ed-Fi resource type caused the error |
| `field_name` | TEXT | NOT NULL DEFAULT '' | Which field has the error |
| `field_value` | TEXT | NOT NULL DEFAULT '' | Current invalid value |
| `resolution_status` | TEXT | NOT NULL DEFAULT 'open' CHECK(resolution_status IN ('open','in_progress','resolved','deferred','state_waived')) | |
| `resolution_method` | TEXT | NOT NULL DEFAULT '' CHECK(resolution_method IN ('data_corrected','descriptor_mapped','state_exception','data_not_available','')) | How error was resolved |
| `resolved_by` | TEXT | NOT NULL DEFAULT '' | User who resolved the error |
| `resolved_at` | TEXT | NOT NULL DEFAULT '' | |
| `resolution_notes` | TEXT | NOT NULL DEFAULT '' | |
| `assigned_to` | TEXT | NOT NULL DEFAULT '' | Staff member responsible for resolving |
| `assigned_at` | TEXT | NOT NULL DEFAULT '' | |
| `state_ticket_id` | TEXT | NOT NULL DEFAULT '' | State help desk ticket number (if escalated) |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_sub_error_window_severity ON sr_submission_error(collection_window_id, severity, resolution_status)`
- `idx_sr_sub_error_student ON sr_submission_error(student_id, resolution_status)`
- `idx_sr_sub_error_submission ON sr_submission_error(submission_id)`
- `idx_sr_sub_error_company_open ON sr_submission_error(company_id, resolution_status)`
- `idx_sr_sub_error_assigned ON sr_submission_error(assigned_to, resolution_status)`
- `idx_sr_sub_error_category ON sr_submission_error(company_id, error_category, severity)`

---

#### `sr_validation_rule`
Library of data quality validation rules. Rules are stored as metadata with an executable SQL query that returns violating records. Supports federal rules (all states), state-specific rules, and district custom rules.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `rule_code` | TEXT | NOT NULL UNIQUE DEFAULT '' | Unique code e.g., ENROLL-001, DEMO-002, SPED-003 |
| `category` | TEXT | NOT NULL DEFAULT '' CHECK(category IN ('enrollment','demographics','sped','el','attendance','discipline','staff','calendar')) | |
| `severity` | TEXT | NOT NULL DEFAULT '' CHECK(severity IN ('critical','major','minor','warning')) | |
| `name` | TEXT | NOT NULL DEFAULT '' | Short human-readable name |
| `description` | TEXT | NOT NULL DEFAULT '' | What this rule checks and why |
| `applicable_windows` | TEXT | NOT NULL DEFAULT '[]' | JSON array of window_type values this rule applies to; empty = all |
| `applicable_states` | TEXT | NOT NULL DEFAULT '[]' | JSON array of state codes; empty = all states |
| `is_federal_rule` | INTEGER | NOT NULL DEFAULT 0 | 0/1; derived from federal reporting requirements |
| `sql_query` | TEXT | NOT NULL DEFAULT '' | SQL query that returns violating student/staff records |
| `error_message_template` | TEXT | NOT NULL DEFAULT '' | Template string with {field} placeholders for error message |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `idx_sr_validation_rule_category ON sr_validation_rule(category, severity, is_active)`
- `idx_sr_validation_rule_code ON sr_validation_rule(rule_code)`
- `idx_sr_validation_rule_federal ON sr_validation_rule(is_federal_rule, is_active)`

---

#### `sr_validation_result`
Results of a validation rule run against a collection window. One row per student per rule per run.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PK | UUID |
| `collection_window_id` | TEXT | NOT NULL FK → sr_collection_window(id) ON DELETE RESTRICT | |
| `run_at` | TEXT | NOT NULL DEFAULT '' | When this validation was executed |
| `run_by` | TEXT | NOT NULL DEFAULT '' | User or system that triggered the run |
| `rule_id` | TEXT | NOT NULL FK → sr_validation_rule(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | FK → educlaw_student(id) ON DELETE RESTRICT | NULL for non-student rules (e.g., staff rules) |
| `staff_id` | TEXT | FK → employee(id) ON DELETE RESTRICT | NULL for non-staff rules |
| `error_detail` | TEXT | NOT NULL DEFAULT '' | Specific invalid value that caused the rule to fail |
| `is_resolved` | INTEGER | NOT NULL DEFAULT 0 | 0/1; updated when underlying data is corrected |
| `resolved_at` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL FK → company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |

**Indexes:**
- `idx_sr_validation_result_window ON sr_validation_result(collection_window_id, is_resolved)`
- `idx_sr_validation_result_rule ON sr_validation_result(rule_id, collection_window_id)`
- `idx_sr_validation_result_student ON sr_validation_result(student_id, collection_window_id)`
- `idx_sr_validation_result_run ON sr_validation_result(collection_window_id, run_at)`

---

### 3.2 Tables (Inherited from Parent educlaw — Read/Reference Only)

The following parent tables are referenced via foreign keys or joined at query time. This product NEVER writes to these tables.

| Parent Table | How We Use It |
| --- | --- |
| `educlaw_student` | FK target for `sr_student_supplement`, `sr_sped_placement`, `sr_el_program`, `sr_discipline_student`, `sr_discipline_action`, `sr_submission_error`, `sr_validation_result`, `sr_snapshot_record` |
| `educlaw_student_attendance` | Read for ADA/ADM calculation and chronic absenteeism identification |
| `educlaw_program_enrollment` | Read for enrollment counts and membership in snapshot |
| `educlaw_course_enrollment` | Read for student–section associations pushed to Ed-Fi |
| `educlaw_academic_year` | FK target for `sr_collection_window`; read for school year boundaries |
| `educlaw_academic_term` | Read for term dates used in ADA calculation and sync |
| `educlaw_section` | Read for StaffSectionAssociation Ed-Fi sync |
| `educlaw_instructor` | Read for staff-section relationships |
| `educlaw_assessment_result` | Read for academic achievement data (EdFacts) — V2 scope |
| `educlaw_notification` | Write new notifications for errors and window status changes |
| `company` | FK target for all `sr_` tables; LEA identity |
| `employee` | FK target for `sr_submission_error.staff_id`, `sr_validation_result.staff_id`; staff data for Ed-Fi sync |
| `department` | Read for staff department in staffing report |

### 3.3 Lookup / Reference Data (Seeded at Init)

The following reference data is seeded into `sr_validation_rule` at install time. These are not separate tables — they are records in the validation rule library.

| Rule Category | Count | Examples |
| --- | --- | --- |
| DEMO-xxx | 10 rules | SSID present, race not null, DOB reasonable age 3-21 |
| ENROLL-xxx | 12 rules | Active enrollment exists for school year, no overlapping enrollments, entry type present |
| SPED-xxx | 8 rules | Disability category present if is_sped=1, educational environment present, IEP start ≤ enrollment |
| EL-xxx | 8 rules | Home language present if is_el=1, proficiency assessment present, EL entry date present |
| ATTEND-xxx | 8 rules | Attendance days ≤ school days, no attendance outside enrollment period, every student has ≥1 record |
| DISC-xxx | 6 rules | Incident has students attached, IDEA student suspension >10 days needs MDR |
| STAFF-xxx | 5 rules | Staff-section assignments cover all active sections, valid credential |
| **Total seed** | ~57 federal core rules | Expanded to 100+ with state-specific rules in V1.1 |

---

## 4. Action List

### 4.1 Actions by Domain

**Naming conventions:**
- `add-{entity}` — Create standalone entity
- `update-{entity}` — Modify existing entity
- `get-{entity}` — Get single entity by ID
- `list-{entities}` — List with filters
- `delete-{entity}` — Delete draft/unused record only
- `sync-{entity}-to-edfi` — Push to Ed-Fi ODS
- `run-{process}` — Execute a computation or batch process

---

#### Domain: demographics (demographics.py)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-student-supplement` | CRUD | Create state reporting supplement for a student (race, SSID, EL/SPED/economic flags) | sr_student_supplement INSERT |
| `update-student-supplement` | CRUD | Update any supplement fields; recomputes race_federal_rollup on race change | sr_student_supplement UPDATE |
| `get-student-supplement` | Query | Get supplement record by student_id; returns full supplement with EL/SPED flags | sr_student_supplement SELECT |
| `list-student-supplements` | Query | List supplements with filters: missing_ssid, missing_race, is_el, is_sped, company_id, school_year | sr_student_supplement + educlaw_student JOIN |
| `assign-ssid` | CRUD | Record state-assigned SSID for a student; sets ssid_status to 'assigned' | sr_student_supplement UPDATE |
| `set-student-race` | CRUD | Set race/ethnicity multi-select codes; auto-computes race_federal_rollup per OMB rules | sr_student_supplement UPDATE |
| `update-el-status` | CRUD | Update EL flags (is_el, el_entry_date, home_language_code, el_exit_date, rfep_date) | sr_student_supplement UPDATE |
| `update-sped-status` | CRUD | Update SPED flags (is_sped, is_504, sped_entry_date, sped_exit_date) | sr_student_supplement UPDATE |
| `update-economic-status` | CRUD | Update economic disadvantage flag and lunch_program_status | sr_student_supplement UPDATE |
| `add-sped-placement` | CRUD | Add SPED placement record for a student and school year | sr_sped_placement INSERT |
| `update-sped-placement` | CRUD | Update SPED placement (disability_category, educational_environment, IEP dates) | sr_sped_placement UPDATE |
| `get-sped-placement` | Query | Get SPED placement by student_id and school_year | sr_sped_placement SELECT |
| `list-sped-placements` | Query | List SPED placements by company, school_year, disability_category, educational_environment | sr_sped_placement SELECT |
| `add-sped-service` | CRUD | Add a related service record to a SPED placement | sr_sped_service INSERT |
| `update-sped-service` | CRUD | Update service type, minutes_per_week, or dates | sr_sped_service UPDATE |
| `list-sped-services` | Query | List related services for a placement or student | sr_sped_service SELECT |
| `delete-sped-service` | CRUD | Delete a service record (only if not yet part of a snapshot) | sr_sped_service DELETE |
| `add-el-program` | CRUD | Record EL program enrollment (type, entry_date, proficiency_level) | sr_el_program INSERT |
| `update-el-program` | CRUD | Update EL program (exit_date, exit_reason, new proficiency assessment) | sr_el_program UPDATE |
| `get-el-program` | Query | Get current or historical EL program record for a student | sr_el_program SELECT |
| `list-el-programs` | Query | List EL program enrollments by company, school_year, program_type, active/exited | sr_el_program SELECT |

---

#### Domain: discipline (discipline.py)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-discipline-incident` | CRUD | Create a discipline incident; assigns naming_series (INC-YYYY-NNNNN) | sr_discipline_incident INSERT |
| `update-discipline-incident` | CRUD | Update incident type, description, location, date, time | sr_discipline_incident UPDATE |
| `get-discipline-incident` | Query | Get incident by ID with students and actions | sr_discipline_incident + sr_discipline_student + sr_discipline_action SELECT |
| `list-discipline-incidents` | Query | List incidents with filters: school_year, incident_type, date_from, date_to, company_id | sr_discipline_incident SELECT |
| `delete-discipline-incident` | CRUD | Delete incident only if no students attached | sr_discipline_incident DELETE |
| `add-discipline-student` | CRUD | Add a student to an incident with role; auto-populates is_idea_student, is_504_student from sr_student_supplement | sr_discipline_student INSERT, sr_student_supplement READ |
| `update-discipline-student` | CRUD | Update student role or IDEA/504 flags | sr_discipline_student UPDATE |
| `remove-discipline-student` | CRUD | Remove a student from an incident (cascade removes their actions) | sr_discipline_student DELETE, sr_discipline_action DELETE |
| `list-discipline-students` | Query | List all students for an incident | sr_discipline_student + educlaw_student JOIN |
| `add-discipline-action` | CRUD | Add disciplinary action for a student in an incident; auto-sets mdr_required if IDEA student + days_removed > 10 | sr_discipline_action INSERT |
| `update-discipline-action` | CRUD | Update action type, dates, days_removed, alternative services, MDR outcome | sr_discipline_action UPDATE |
| `record-mdr-outcome` | CRUD | Record MDR (Manifestation Determination Review) outcome for an IDEA student suspension >10 days | sr_discipline_action UPDATE |
| `get-discipline-action` | Query | Get a specific disciplinary action by ID | sr_discipline_action SELECT |
| `list-discipline-actions` | Query | List actions with filters: student_id, school_year, action_type, mdr_required | sr_discipline_action SELECT |
| `get-discipline-summary` | Report | CRDC-formatted discipline summary: counts by action_type × race × sex × IDEA status | sr_discipline_action + sr_discipline_student + sr_student_supplement + educlaw_student JOIN |

---

#### Domain: ed_fi (ed_fi.py)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-edfi-config` | CRUD | Create Ed-Fi ODS connection profile for a state and school year; encrypts client_secret | sr_edfi_config INSERT |
| `update-edfi-config` | CRUD | Update ODS URL, OAuth credentials, API version; re-encrypts secret | sr_edfi_config UPDATE |
| `get-edfi-config` | Query | Get Ed-Fi config by ID (does not return decrypted secret) | sr_edfi_config SELECT |
| `list-edfi-configs` | Query | List all configs by company_id, state_code, is_active | sr_edfi_config SELECT |
| `test-edfi-connection` | Action | Test OAuth token fetch + GET /schools from ODS; records last_tested_at | sr_edfi_config UPDATE |
| `add-org-mapping` | CRUD | Map company/school to NCES LEA ID, NCES School ID, Ed-Fi org IDs | sr_org_mapping INSERT |
| `update-org-mapping` | CRUD | Update any NCES/Ed-Fi identifiers for an org | sr_org_mapping UPDATE |
| `get-org-mapping` | Query | Get org mapping for a company_id + state_code | sr_org_mapping SELECT |
| `list-org-mappings` | Query | List all org mappings for a company | sr_org_mapping SELECT |
| `add-descriptor-mapping` | CRUD | Add a single code → Ed-Fi descriptor URI mapping | sr_edfi_descriptor_map INSERT |
| `update-descriptor-mapping` | CRUD | Update descriptor URI for an existing mapping | sr_edfi_descriptor_map UPDATE |
| `bulk-import-descriptor-mappings` | CRUD | Import multiple descriptor mappings from a JSON array (upsert semantics) | sr_edfi_descriptor_map INSERT/UPDATE |
| `list-descriptor-mappings` | Query | List descriptor mappings for a config, optionally filtered by descriptor_type | sr_edfi_descriptor_map SELECT |
| `delete-descriptor-mapping` | CRUD | Delete a descriptor mapping (only if not referenced in sync logs) | sr_edfi_descriptor_map DELETE |
| `sync-student-to-edfi` | Sync | Push Student + StudentEducationOrganizationAssociation for one student to Ed-Fi ODS | sr_edfi_sync_log INSERT, educlaw_student + sr_student_supplement READ |
| `sync-enrollment-to-edfi` | Sync | Push StudentSchoolAssociation (enrollment entry/exit) for a student or collection window scope | sr_edfi_sync_log INSERT, educlaw_program_enrollment READ |
| `sync-attendance-to-edfi` | Sync | Push StudentSchoolAttendanceEvent records for a date range to Ed-Fi ODS | sr_edfi_sync_log INSERT, educlaw_student_attendance READ |
| `sync-sped-to-edfi` | Sync | Push StudentSpecialEducationProgramAssociation for SPED students | sr_edfi_sync_log INSERT, sr_sped_placement + sr_student_supplement READ |
| `sync-el-to-edfi` | Sync | Push StudentLanguageInstructionProgramAssociation for EL students | sr_edfi_sync_log INSERT, sr_el_program + sr_student_supplement READ |
| `sync-discipline-to-edfi` | Sync | Push DisciplineIncident + StudentDisciplineIncidentAssociation records | sr_edfi_sync_log INSERT, sr_discipline_incident + sr_discipline_student + sr_discipline_action READ |
| `sync-staff-to-edfi` | Sync | Push Staff + StaffSchoolAssociation + StaffSectionAssociation records | sr_edfi_sync_log INSERT, employee + educlaw_instructor + educlaw_section READ |
| `get-edfi-sync-log` | Query | Get sync log entries for a resource_type and internal_id | sr_edfi_sync_log SELECT |
| `list-edfi-sync-errors` | Query | List failed/pending sync entries for a company/window; used for retry dashboard | sr_edfi_sync_log SELECT |
| `retry-failed-syncs` | Action | Re-attempt all sync entries with sync_status='error' or 'retry' for a window | sr_edfi_sync_log UPDATE, all relevant parent tables READ |

---

#### Domain: state_reporting (state_reporting.py)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-collection-window` | CRUD | Define a new collection window (name, state, type, dates, edfi_config_id) | sr_collection_window INSERT |
| `update-collection-window` | CRUD | Update window dates, description, or config; only allowed if status is upcoming/open | sr_collection_window UPDATE |
| `get-collection-window` | Query | Get window by ID with current status, error counts, snapshot summary | sr_collection_window + sr_snapshot + sr_submission_error SELECT |
| `list-collection-windows` | Query | List windows filtered by status, school_year, state_code, window_type | sr_collection_window SELECT |
| `advance-window-status` | Action | Move window to next lifecycle status (upcoming→open→data_entry→validation→snapshot→submitted→certified→closed); validates that prerequisites are met for each transition | sr_collection_window UPDATE |
| `take-snapshot` | Action | Freeze data at snapshot timestamp: extracts all relevant data from educlaw + sr_ tables, writes sr_snapshot + sr_snapshot_record rows; marks window status='snapshot' | sr_snapshot INSERT, sr_snapshot_record INSERT, educlaw_student READ, educlaw_program_enrollment READ, sr_student_supplement READ, sr_sped_placement READ, sr_el_program READ, sr_discipline_incident READ |
| `get-snapshot` | Query | Get snapshot summary with counts and certification status | sr_snapshot SELECT |
| `list-snapshot-records` | Query | Get student-level snapshot records for a snapshot, filterable by record_type | sr_snapshot_record SELECT |
| `calculate-ada` | Compute | Calculate ADA/ADM for a given collection window or date range; returns per-school and district totals | educlaw_student_attendance READ, educlaw_program_enrollment READ, educlaw_academic_year READ |
| `get-ada-dashboard` | Report | Real-time ADA with trend, projected annual ADA, and funding impact (ADA × configurable per-pupil rate) | educlaw_student_attendance READ, educlaw_program_enrollment READ |
| `identify-chronic-absenteeism` | Compute | Flag students with ≥10% absent days for a school year; returns list by school/grade | educlaw_student_attendance READ, educlaw_program_enrollment READ |
| `get-data-readiness-report` | Report | Compute data readiness score per category (demographics, SPED, EL, attendance) showing % of students with complete data; returns readiness score 0-100 | sr_student_supplement READ, sr_sped_placement READ, sr_el_program READ, educlaw_student_attendance READ |
| `generate-enrollment-report` | Report | Enrollment counts disaggregated by race, grade level, EL, SPED, economic status; supports small-cell suppression | sr_student_supplement READ, educlaw_program_enrollment READ |
| `generate-crdc-report` | Report | CRDC-formatted data export: enrollment, discipline, staff by race/sex/disability subgroups; flags cells with N<10 | sr_student_supplement + sr_discipline_action + educlaw_student + employee READ |

---

#### Domain: data_validation (data_validation.py)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-validation-rule` | CRUD | Add a new rule to the library (with SQL query, category, severity, applicable_windows) | sr_validation_rule INSERT |
| `update-validation-rule` | CRUD | Update rule SQL, message template, or metadata | sr_validation_rule UPDATE |
| `get-validation-rule` | Query | Get rule by ID or rule_code | sr_validation_rule SELECT |
| `list-validation-rules` | Query | List rules filtered by category, severity, is_active, is_federal_rule, applicable_states | sr_validation_rule SELECT |
| `toggle-validation-rule` | Action | Activate or deactivate a validation rule | sr_validation_rule UPDATE |
| `seed-validation-rules` | Action | Load the built-in federal/common rule library (57+ rules); skips existing rule_codes | sr_validation_rule INSERT |
| `run-validation` | Action | Execute all active applicable rules for a collection window; clears prior results for this window; writes sr_validation_result and creates sr_submission_error entries for each violation | sr_validation_result INSERT, sr_submission_error INSERT, all relevant tables READ |
| `run-validation-for-student` | Action | Run all rules for a single student in the context of a collection window | sr_validation_result INSERT, sr_submission_error INSERT |
| `get-validation-results` | Query | Get validation results for a window run, with summary counts by severity | sr_validation_result + sr_validation_rule JOIN |
| `assign-submission-error` | CRUD | Assign a submission error to a staff member with a due date | sr_submission_error UPDATE |
| `update-error-resolution` | CRUD | Mark error resolved (or deferred/state_waived) with resolution method and notes | sr_submission_error UPDATE |
| `list-submission-errors` | Query | List errors for a window with filters: severity, resolution_status, error_category, student_id, assigned_to | sr_submission_error SELECT |
| `get-error-dashboard` | Report | Error count summary by severity × category × resolution_status for a collection window | sr_submission_error SELECT |
| `bulk-assign-errors` | Action | Assign multiple errors to a staff member in one operation | sr_submission_error UPDATE |
| `escalate-error` | Action | Escalate error to state help desk; records state_ticket_id | sr_submission_error UPDATE |

---

#### Domain: submission_tracking (submission_tracking.py)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-submission` | CRUD | Record a new submission attempt (initial or amendment); assigns naming_series (SUB-YYYY-NNNNN) | sr_submission INSERT |
| `update-submission-status` | Action | Update submission status (pending → in_progress → completed / failed); records records_accepted, records_rejected | sr_submission UPDATE |
| `get-submission` | Query | Get submission record by ID with linked snapshot and error counts | sr_submission + sr_snapshot + sr_submission_error JOIN |
| `list-submissions` | Query | List submissions for a company filtered by window, status, submission_type, school_year | sr_submission SELECT |
| `certify-submission` | Action | Certify a snapshot/submission as accurate and complete; sets snapshot.status='certified' and window.status='certified'; records certified_by + certified_at | sr_submission UPDATE, sr_snapshot UPDATE, sr_collection_window UPDATE |
| `create-amendment` | Action | Create a new amendment submission linked to original; opens window for corrections; sets submission_type='amendment' | sr_submission INSERT, sr_collection_window UPDATE |
| `get-submission-history` | Report | Full chronological submission history for a collection window including all amendments | sr_submission + sr_snapshot SELECT |
| `export-submission-package` | Report | Build export package for a submission: snapshot summary + all sr_snapshot_record rows as JSON; used for audit defense | sr_submission SELECT, sr_snapshot SELECT, sr_snapshot_record SELECT |
| `get-submission-audit-trail` | Report | Complete audit trail for a window: status transitions, snapshot actions, submissions, certifications, amendments with timestamps and users | sr_collection_window + sr_snapshot + sr_submission SELECT |

---

### 4.2 Cross-Domain Actions

| Action | Domains Involved | Description |
| --- | --- | --- |
| `take-snapshot` | state_reporting + demographics + discipline + all data | Reads from all sr_ and educlaw_ tables to build frozen snapshot |
| `run-validation` | data_validation + demographics + discipline + ed_fi | Executes SQL rules that join sr_ tables with educlaw_ tables |
| `sync-student-to-edfi` | ed_fi + demographics | Requires sr_student_supplement for race/EL/SPED to build Ed-Fi payload |
| `get-data-readiness-report` | state_reporting + demographics + discipline | Joins across supplement, SPED, EL, attendance to compute % completeness |
| `generate-crdc-report` | state_reporting + demographics + discipline | Requires all demographic and discipline data for disaggregated report |
| `advance-window-status` (→ snapshot) | state_reporting + data_validation | Must verify zero critical errors before advancing to snapshot status |
| `certify-submission` | submission_tracking + state_reporting | Updates both submission and collection_window records atomically |

### 4.3 Naming Conflict Check

**Parent educlaw actions inventoried:**
`create-applicant, update-applicant, accept-applicant, reject-applicant, admit-student, create-student, update-student, get-student, list-students, create-guardian, link-guardian, create-consent, revoke-consent, log-data-access, get-data-access-log, create-academic-year, update-academic-year, create-academic-term, update-academic-term, advance-term-status, create-program, create-course, add-prerequisite, create-section, update-section, open-section, create-room, create-program-enrollment, cancel-program-enrollment, create-section-enrollment, cancel-enrollment, terminate-enrollment, apply-waitlist, list-waitlist, create-grading-scale, add-grading-scale-entry, create-assessment-plan, add-assessment-category, create-assessment, record-assessment-result, calculate-grade, submit-grades, amend-grade, get-transcript, get-report-card, calculate-gpa, record-attendance, record-batch-attendance, update-attendance, get-attendance-summary, get-section-attendance, get-truancy-report, create-fee-structure, apply-fee-structure, create-scholarship, create-announcement, send-notification`

**Conflict analysis — all 89 educlaw-statereport actions reviewed:**
- No action name in this product duplicates any parent action name ✅
- `advance-window-status` (this product) vs. `advance-term-status` (parent) — DIFFERENT names ✅
- `calculate-ada` (this product) vs. `calculate-grade`, `calculate-gpa` (parent) — DIFFERENT names ✅
- `add-discipline-student` (this product) vs. `create-student` (parent) — DIFFERENT names ✅
- All `sync-*-to-edfi` patterns are unique to this product ✅
- All `sr_` table-specific actions are unique to this product ✅

**Result: ZERO naming conflicts with parent educlaw.**

---

## 5. Workflows

### Workflow A: Annual Fall Enrollment Collection (Core Workflow)

**Trigger:** School year begins; fall collection window opens (typically October)
**Primary Actor:** District Data Coordinator

```
Pre-Window Setup (August–September):
  1. add-org-mapping → Record NCES LEA ID and school IDs
  2. add-edfi-config → Configure state ODS URL + OAuth credentials
  3. test-edfi-connection → Verify connectivity
  4. bulk-import-descriptor-mappings → Map grade levels, race, EL, SPED codes
  5. add-collection-window (window_type=fall_enrollment)

Data Readiness (September–October):
  6. add-student-supplement (for each new student) → Race, SSID, EL/SPED flags
  7. assign-ssid → Record state-assigned SSIDs
  8. seed-validation-rules → Load federal rule library
  9. run-validation → Execute all rules; generate sr_validation_result
  10. get-error-dashboard → Review critical/major error counts
  11. bulk-assign-errors → Distribute errors to school secretaries

Data Correction (October):
  12. update-student-supplement, update-el-status, update-sped-status → Fix data
  13. run-validation (repeat) → Confirm error count decreasing

Collection Window Open:
  14. advance-window-status (upcoming → open)
  15. sync-student-to-edfi, sync-enrollment-to-edfi → Push to state ODS
  16. list-edfi-sync-errors → Review sync failures
  17. retry-failed-syncs → Re-attempt failed records

Pre-Snapshot Validation:
  18. run-validation (final run) → Confirm zero critical errors
  19. get-data-readiness-report → Confirm ≥95% completeness
  20. advance-window-status (open → data_entry → validation)

Snapshot:
  21. advance-window-status (validation → snapshot)
  22. take-snapshot → Freeze sr_snapshot + sr_snapshot_record
  23. get-snapshot → Review summary counts for reasonableness

Submission:
  24. add-submission (submission_type=initial) → Record submission
  25. update-submission-status (completed) → Mark records submitted
  26. certify-submission → Administrator certifies accuracy; window.status=certified
```

**GL/SLE Implications:** None — state reporting does not generate financial postings.

---

### Workflow B: EOY Attendance + ADA Calculation

**Trigger:** End of school year; EOY attendance window opens
**Primary Actor:** District Attendance Coordinator

```
1. add-collection-window (window_type=eoy_attendance)
2. calculate-ada → Compute ADA/ADM from educlaw_student_attendance
3. identify-chronic-absenteeism → Flag students ≥10% absent
4. get-ada-dashboard → Review ADA and projected funding impact
5. run-validation (ATTEND-xxx rules) → Validate attendance data
6. sync-attendance-to-edfi → Push StudentSchoolAttendanceEvent records
7. list-edfi-sync-errors → Review attendance sync errors
8. update-error-resolution → Resolve calendar/enrollment date errors
9. take-snapshot → Freeze ADA totals into sr_snapshot
10. certify-submission → Sign off on ADA report
```

**Funding Implication:** ADA × per-pupil rate = district funding allocation. A 1% ADA improvement on 1,000 students at $10,000/pupil = $100,000 additional funding. The `get-ada-dashboard` action must show this calculation explicitly.

---

### Workflow C: Discipline Incident → CRDC Reporting

**Trigger:** Behavioral incident occurs; CRDC annual collection window
**Primary Actor:** School Dean / Data Coordinator

```
Incident Recording (ongoing throughout year):
  1. add-discipline-incident (incident_date, type, location)
  2. add-discipline-student (student_id, role=offender) → auto-reads IDEA/504 flags
  3. add-discipline-action (action_type, start_date, end_date, days_removed)
  4. [If IDEA student + days_removed > 10]: record-mdr-outcome (manifestation/not_manifestation)

CRDC Collection Window:
  5. add-collection-window (window_type=crdc)
  6. run-validation (DISC-xxx rules) → Validate all incidents are complete
  7. sync-discipline-to-edfi → Push DisciplineIncident records
  8. generate-crdc-report → CRDC-formatted counts by subgroup
  9. take-snapshot → Freeze discipline data
  10. certify-submission
```

---

### Workflow D: SPED Child Count (IDEA 618)

**Trigger:** Fall SPED collection window (typically December 1 child count date)
**Primary Actor:** Special Education Director + Data Coordinator

```
1. add-collection-window (window_type=fall_sped)
2. add-sped-placement (for each SPED student; disability_category, educational_environment)
3. add-sped-service (related services per student)
4. run-validation (SPED-xxx rules) → Validate disability categories and environments
5. sync-sped-to-edfi → Push StudentSpecialEducationProgramAssociation
6. generate-enrollment-report → Verify IDEA child count by disability × environment
7. take-snapshot → Freeze SPED placements
8. certify-submission → Sign off for IDEA 618 submission
```

---

### Workflow E: Error Resolution (Continuous)

```
1. list-edfi-sync-errors OR list-submission-errors → Identify open errors
2. get-error-dashboard → Prioritize by critical → major → minor
3. bulk-assign-errors → Assign to responsible school staff
4. [Staff corrects source data in EduClaw operational tables]
5. run-validation-for-student → Re-validate corrected student
6. sync-student-to-edfi → Re-sync corrected records
7. update-error-resolution (resolution_status=resolved) → Close error
8. [If state help desk needed]: escalate-error → Record state_ticket_id
```

---

## 6. Dependencies

### 6.1 Foundation Skills

| Skill | What We Use | How |
| --- | --- | --- |
| erpclaw-setup | `company` table (LEA identity), `employee` table (staff), `department` table, shared lib (db, audit, response, validation, naming, crypto) | READ company, employee; WRITE via erpclaw_lib functions; encrypt Ed-Fi credentials using `erpclaw_lib.crypto.encrypt_field` |
| erpclaw-hr | `employee` table (staff FTE, name, department for staffing reports) | READ only; staff records created via erpclaw-hr |
| erpclaw-gl | Not used in V1 — state reporting is non-financial | No dependency |
| erpclaw-selling | Not used | No dependency |
| erpclaw-payments | Not used | No dependency |

### 6.2 Parent educlaw Dependencies

| Parent Table/Action | Relationship | Notes |
| --- | --- | --- |
| `educlaw_student` | FK reference on all sr_ student tables | The authoritative student record; state reporting extends via sr_student_supplement |
| `educlaw_student_attendance` | READ for ADA calculation | `calculate-ada` and `identify-chronic-absenteeism` join attendance against school calendar |
| `educlaw_program_enrollment` | READ for enrollment membership | Student's active enrollment provides entry/exit dates for Ed-Fi StudentSchoolAssociation |
| `educlaw_course_enrollment` | READ for section-level data | Teacher-student linkage for StaffSectionAssociation sync |
| `educlaw_academic_year` | FK on sr_collection_window; READ for year boundaries | Collection windows reference academic year for term date resolution |
| `educlaw_academic_term` | READ for term start/end dates | Used in ADA calculation period boundaries |
| `educlaw_section` | READ for staff-section assignments | `sync-staff-to-edfi` uses section-instructor relationships |
| `educlaw_instructor` | READ for teacher-of-record data | Links employee FK to section for staffing report |
| `educlaw_notification` | WRITE (via educlaw action subprocess) | Error alerts and window status changes notify data coordinators |

### 6.3 Shared Library Usage

| Library Function | Used In |
| --- | --- |
| `erpclaw_lib.db.get_connection` | All domain modules |
| `erpclaw_lib.response.ok / err` | All action handlers |
| `erpclaw_lib.audit.audit` | All state-changing actions |
| `erpclaw_lib.naming.get_next_name` | `add-discipline-incident` (INC series), `add-submission` (SUB series) |
| `erpclaw_lib.validation.check_input_lengths` | All action handlers |
| `erpclaw_lib.dependencies.check_required_tables` | db_query.py router |
| `erpclaw_lib.crypto.encrypt_field / decrypt_field` | `add-edfi-config` / `test-edfi-connection` for OAuth secret |
| `erpclaw_lib.decimal_utils.to_decimal` | ADA calculation (attendance ratios) |

---

## 7. Test Strategy

### 7.1 Unit Tests (per domain)

#### demographics.py
- `test_add_supplement_creates_one_to_one` — Adding supplement for student; second supplement for same student raises error
- `test_race_federal_rollup_hispanic_overrides` — Hispanic/Latino flag = rollup is HISPANIC regardless of race_codes
- `test_race_federal_rollup_two_or_more` — Non-Hispanic with 2 race codes = TWO_OR_MORE_RACES
- `test_assign_ssid_updates_status` — SSID assignment sets ssid_status='assigned'
- `test_el_entry_date_required_when_el_flag` — is_el=1 requires el_entry_date
- `test_sped_placement_unique_per_year` — Cannot add second SPED placement for same student/year
- `test_sped_service_links_to_placement` — Service must reference valid sped_placement_id
- `test_list_supplements_missing_ssid_filter` — Filter returns only students with ssid_status='pending'

#### discipline.py
- `test_naming_series_sequential` — INC-2026-00001, 00002, 00003 in sequence
- `test_add_student_auto_populates_idea_flag` — is_idea_student auto-read from sr_student_supplement
- `test_mdr_auto_required_on_idea_oss_gt10` — add-discipline-action with IDEA student + days_removed=11 sets mdr_required=1
- `test_delete_incident_blocked_if_students_attached` — Delete raises error if students present
- `test_crdc_discipline_summary_subgroup_breakdown` — Summary includes race × sex × action_type counts
- `test_days_removed_cannot_be_negative` — Validation rejects days_removed < 0

#### ed_fi.py
- `test_edfi_secret_is_encrypted_at_rest` — oauth_client_secret_encrypted is not plaintext
- `test_test_connection_records_tested_at` — Successful test updates last_tested_at
- `test_descriptor_map_unique_per_type_per_code` — Duplicate (config, type, code) raises error
- `test_bulk_import_descriptors_upserts` — Re-import same code updates URI without error
- `test_sync_log_created_for_each_call` — Every sync operation creates sr_edfi_sync_log record
- `test_retry_failed_syncs_resets_count` — retry-failed-syncs resets retry_count to 0

#### state_reporting.py
- `test_collection_window_unique_per_year_type` — Duplicate (company, state, type, year) raises error
- `test_advance_status_validates_prerequisites` — Cannot advance to snapshot if critical errors > 0
- `test_snapshot_creates_records_for_all_students` — take-snapshot creates one sr_snapshot_record per enrolled student
- `test_snapshot_is_immutable` — After snapshot, attempting to modify sr_snapshot_record raises error
- `test_ada_calculation_uses_enrollment_dates` — Student enrolled for only part of period gets prorated ADA
- `test_chronic_absenteeism_threshold` — Student with exactly 10% absent days IS flagged (≥10%)
- `test_ada_half_day_counts_point_five` — Half-day attendance contributes 0.5 to ADA credit

#### data_validation.py
- `test_run_validation_creates_result_per_student` — Validation run creates sr_validation_result for each violating student
- `test_run_validation_creates_submission_error` — Each result creates corresponding sr_submission_error
- `test_rerun_clears_prior_results` — Re-running validation for same window clears is_resolved=0 prior results
- `test_assign_error_records_assigned_at` — assign-submission-error sets assigned_at timestamp
- `test_resolve_error_records_resolution_fields` — update-error-resolution sets resolved_by, resolved_at, resolution_method
- `test_critical_severity_blocks_snapshot` — advance-window-status to snapshot fails if critical open errors exist

#### submission_tracking.py
- `test_naming_series_sequential` — SUB-2026-00001, 00002 in sequence
- `test_certify_updates_snapshot_and_window` — certify-submission atomically sets snapshot.status=certified AND window.status=certified
- `test_amendment_links_to_original` — create-amendment sets linked_submission_id to original ID
- `test_export_package_includes_all_snapshot_records` — export-submission-package returns all sr_snapshot_record rows for the snapshot
- `test_submission_history_includes_amendments` — get-submission-history returns both initial and amendment records

### 7.2 Integration Tests

| Test Scenario | Actions Exercised |
| --- | --- |
| Full fall enrollment cycle | add-org-mapping → add-edfi-config → add-student-supplement (10 students) → run-validation → resolve errors → take-snapshot → certify-submission |
| ADA calculation end-to-end | Pre-load educlaw_student_attendance + educlaw_program_enrollment → calculate-ada → verify against manual calculation |
| Discipline → CRDC report | add-discipline-incident → add-discipline-student → add-discipline-action → get-discipline-summary → verify CRDC subgroup counts |
| SPED child count cycle | add-sped-placement (5 students, 3 disability categories) → sync-sped-to-edfi → run-validation (SPED rules) → take-snapshot (fall_sped window) |
| Error lifecycle | run-validation (introduce student with missing race) → list-submission-errors → assign-submission-error → update-el-status (fix data) → run-validation-for-student (confirm cleared) → update-error-resolution |
| Amendment workflow | certify-submission → create-amendment → correct data → certify-submission (second) → get-submission-history (verify both records) |

### 7.3 Invariants

| Domain | Invariant |
| --- | --- |
| Demographics | One and only one `sr_student_supplement` per `educlaw_student` (UNIQUE constraint) |
| Demographics | `race_federal_rollup` must be computed, not entered manually; always consistent with is_hispanic_latino and race_codes |
| Demographics | One `sr_sped_placement` per student per school_year (UNIQUE constraint) |
| Discipline | `sr_discipline_action` must reference a `sr_discipline_student` row (the student must be linked to the incident) |
| Discipline | `mdr_required` must be 1 for any IDEA student with `days_removed > 10`; system enforces this at add-discipline-action time |
| Ed-Fi | `oauth_client_secret_encrypted` is NEVER stored in plaintext; always AES-encrypted via erpclaw_lib.crypto |
| Ed-Fi | Ed-Fi dependency order must be respected: Organizations → Students → Enrollments → Attendance → Discipline (never push child resources before parents) |
| State Reporting | `sr_snapshot_record` rows are INSERT-only; no UPDATE or DELETE after the snapshot is taken |
| State Reporting | Collection window UNIQUE(company_id, state_code, window_type, school_year) — no duplicate windows |
| State Reporting | Cannot advance to `snapshot` status if any `sr_submission_error` with severity='critical' and resolution_status='open' exists for this window |
| Data Validation | Validation rule `rule_code` is globally UNIQUE; cannot insert duplicate codes even across categories |
| Submission Tracking | `certify-submission` must be atomic — updates `sr_submission`, `sr_snapshot`, AND `sr_collection_window` in one transaction |
| Submission Tracking | `sr_snapshot.status` can only advance: draft → finalized → certified (never backward) |
| All tables | `company_id` is never NULL; all state reporting data is company-scoped |

---

## 8. Estimated Complexity

| Domain | New Tables | Actions | Estimated Lines | Priority |
| --- | --- | --- | --- | --- |
| demographics (state_reporting.py) | 4 (supplement, sped_placement, sped_service, el_program) | 21 | ~600 | 1 |
| discipline (discipline.py) | 3 (incident, discipline_student, discipline_action) | 15 | ~450 | 2 |
| ed_fi (ed_fi.py) | 3 (edfi_config, edfi_descriptor_map, edfi_sync_log) | 24 | ~750 | 1 |
| state_reporting (state_reporting.py) | 5 (org_mapping, collection_window, snapshot, snapshot_record) + ADA engine | 14 | ~600 | 1 |
| data_validation (data_validation.py) | 2 (validation_rule, validation_result) + sr_submission_error | 15 | ~500 | 1 |
| submission_tracking (submission_tracking.py) | 1 (submission) | 9 | ~300 | 2 |
| init_db.py | 18 total new tables, 50+ indexes | — | ~350 | 1 |
| db_query.py (router) | — | 98 total actions | ~200 | 1 |
| **Total** | **18 tables** | **98 actions** | **~3,750** | — |

### Build Priority Order

1. **Phase 1 — Foundation Data** (`init_db.py` + `demographics.py`): Create all 18 tables. Build student supplement CRUD, SPED placement, EL program. This unblocks all downstream reporting.

2. **Phase 2 — Ed-Fi Infrastructure** (`ed_fi.py`): Build config + descriptor mapping + sync engine. Test against Ed-Fi sandbox before attempting state ODS.

3. **Phase 3 — Collection Windows + Snapshots** (`state_reporting.py`): Window lifecycle, ADA calculation, snapshot engine. Core orchestration layer.

4. **Phase 4 — Validation + Error Management** (`data_validation.py`): Seed 57 federal rules, validation run engine, error dashboard. Requires Phase 1-3 data to be meaningful.

5. **Phase 5 — Discipline** (`discipline.py`): Standalone; can be built in parallel with Phase 2-3.

6. **Phase 6 — Submission Tracking** (`submission_tracking.py`): Final layer; depends on snapshots and errors.

---

## 9. Appendix — Standard ERPClaw Action Patterns

All actions follow the ERPClaw standard patterns from registry.yaml:

| Pattern | Template |
| --- | --- |
| add_action | `validate required fields → generate UUID4 → INSERT → audit() → return ok(entity)` |
| update_action | `validate entity exists → validate fields → UPDATE → audit() → return ok(updated_fields)` |
| list_action | `parse filters → SELECT with LIMIT/OFFSET pagination → return rows_to_list(rows)` |
| get_action | `validate entity exists → SELECT → return row_to_dict(row)` |
| delete_action | `validate status allows delete → DELETE → audit() → return ok()` |
| sync_action | `validate entity exists → build Ed-Fi payload → call state ODS → INSERT sr_edfi_sync_log → return ok(sync_status)` |
| compute_action | `validate inputs → run SQL aggregation on source tables → return ok(computed_result)` |
| report_action | `parse filters → JOIN across tables → apply small-cell suppression if N<10 → return ok(report_data)` |
