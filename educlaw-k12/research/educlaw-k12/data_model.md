# Data Model Insights: EduClaw K-12 Extensions

> **Product:** educlaw-k12
> **Date:** 2026-03-05
> **Convention:** All new tables prefixed `educlaw_k12_`

---

## 1. Overview

EduClaw K-12 adds **19 new tables** across four domains. All tables:
- Use `id TEXT PRIMARY KEY` (UUID4)
- Reference `educlaw_student(id)` as the anchor entity
- Include `company_id` on all top-level tables
- Follow the parent's immutability conventions (no `updated_at` on log tables)
- Use TEXT for money/dates, INTEGER for booleans

### 1.1 Table Count by Domain

| Domain | Tables | Notes |
|--------|--------|-------|
| Discipline | 4 | Incident, student-involvement, action, MDR |
| Health Records | 6 | Profile, visit, medication, med-log, immunization, waiver |
| Special Education | 9 | Referral, evaluation, eligibility, IEP, goal, service, team, progress, 504 |
| Grade Promotion | 3 | Review, decision, intervention plan |
| **Total** | **22** | Replaces nothing in parent; all additive |

---

## 2. Domain 1: Discipline Tables (4 tables)

### 2.1 `educlaw_k12_discipline_incident`

The header record for a behavioral event. One incident may involve multiple students.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| naming_series | TEXT NOT NULL UNIQUE | e.g., DI-2025-000042 |
| incident_date | TEXT NOT NULL | ISO date |
| incident_time | TEXT NOT NULL | HH:MM (24h) |
| location | TEXT NOT NULL CHECK | `classroom / hallway / cafeteria / gym / bathroom / playground / bus / off_campus / online / other` |
| location_detail | TEXT NOT NULL | Free text (room number, bus route, etc.) |
| incident_type | TEXT NOT NULL CHECK | Taxonomized type (see below) |
| severity | TEXT NOT NULL CHECK | `minor / moderate / major / emergency` |
| description | TEXT NOT NULL | Narrative description |
| is_reported_to_law_enforcement | INTEGER NOT NULL DEFAULT 0 | Police notified? |
| is_mandatory_report | INTEGER NOT NULL DEFAULT 0 | Child abuse mandatory report filed? |
| mandatory_report_date | TEXT NOT NULL DEFAULT '' | Date CPS/police reported to |
| is_title_ix | INTEGER NOT NULL DEFAULT 0 | Sexual harassment/assault incident |
| incident_status | TEXT NOT NULL CHECK | `open / under_review / closed / appealed` |
| reviewed_by | TEXT NOT NULL DEFAULT '' | Admin who closed the incident |
| reviewed_at | TEXT NOT NULL DEFAULT '' | When closed |
| academic_year_id | TEXT NOT NULL → `educlaw_academic_year(id)` | |
| academic_term_id | TEXT → `educlaw_academic_term(id)` | Nullable |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(company_id, incident_date)`, `(academic_year_id, severity)`, `(incident_status)`, `(is_title_ix)`

**Incident Type Taxonomy (CHECK constraint values):**
```
tardy / dress_code / electronic_device / disruptive_behavior / disrespectful_language /
classroom_disruption / bullying / harassment / physical_altercation_minor /
theft / vandalism / cheating / truancy / insubordination / fighting /
assault / weapons / drugs_alcohol / sexual_harassment / threats /
extortion / arson / gang_activity / sexual_assault / serious_assault /
bomb_threat / active_threat / other_minor / other_major
```

---

### 2.2 `educlaw_k12_discipline_student`

Per-student involvement in a discipline incident. One incident can have multiple students with different roles and consequences.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| incident_id | TEXT NOT NULL → `educlaw_k12_discipline_incident(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| role | TEXT NOT NULL CHECK | `offender / victim / witness / bystander` |
| is_idea_eligible | INTEGER NOT NULL DEFAULT 0 | Denormalized from IEP for quick MDR check |
| cumulative_suspension_days_ytd | TEXT NOT NULL DEFAULT '0' | Updated on each suspension |
| mdr_required | INTEGER NOT NULL DEFAULT 0 | MDR triggered by this incident? |
| notes | TEXT NOT NULL DEFAULT '' | Per-student narrative |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | No updated_at — immutable |

**Indexes:** `(incident_id)`, `(student_id)`, `(student_id, is_idea_eligible)`

---

### 2.3 `educlaw_k12_discipline_action`

The consequence assigned to a specific student for a specific incident. A student may have multiple actions for one incident (e.g., suspension + counseling referral).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| discipline_student_id | TEXT NOT NULL → `educlaw_k12_discipline_student(id)` | |
| action_type | TEXT NOT NULL CHECK | `verbal_warning / parent_contact / detention / in_school_suspension / out_of_school_suspension / expulsion_referral / counseling_referral / law_enforcement_referral / restorative_practice / community_service / loss_of_privilege / other` |
| start_date | TEXT NOT NULL DEFAULT '' | Suspension start |
| end_date | TEXT NOT NULL DEFAULT '' | Suspension end |
| duration_days | TEXT NOT NULL DEFAULT '0' | Calculated from dates for suspension |
| administered_by | TEXT NOT NULL DEFAULT '' | Staff member ID or name |
| notes | TEXT NOT NULL DEFAULT '' | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(discipline_student_id)`, `(action_type, start_date)`

---

### 2.4 `educlaw_k12_manifestation_review`

IDEA Manifestation Determination Review record, required when an IDEA student's suspension exceeds 10 cumulative days.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| discipline_student_id | TEXT NOT NULL → `educlaw_k12_discipline_student(id)` | Triggering incident |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| iep_id | TEXT NOT NULL → `educlaw_k12_iep(id)` | Current active IEP |
| mdr_date | TEXT NOT NULL DEFAULT '' | Date of MDR meeting |
| question_1_result | TEXT NOT NULL CHECK | `yes / no / not_determined` — Was conduct caused by disability? |
| question_2_result | TEXT NOT NULL CHECK | `yes / no / not_determined` — Was conduct result of IEP failure? |
| determination | TEXT NOT NULL CHECK | `manifestation / not_manifestation` |
| outcome_action | TEXT NOT NULL CHECK | `return_to_placement / maintain_removal / interim_placement` |
| fba_required | INTEGER NOT NULL DEFAULT 0 | Functional Behavioral Assessment required? |
| bip_required | INTEGER NOT NULL DEFAULT 0 | Behavioral Intervention Plan required? |
| parent_notified_date | TEXT NOT NULL DEFAULT '' | Written notice to parents |
| notes | TEXT NOT NULL DEFAULT '' | |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id)`, `(iep_id)`, `(mdr_date)`

---

## 3. Domain 2: Health Records Tables (6 tables)

### 3.1 `educlaw_k12_health_profile`

One profile per student. Captures chronic health conditions, allergy information, and physician contacts. Updated each year at enrollment renewal.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL UNIQUE → `educlaw_student(id)` | One profile per student |
| allergies | TEXT NOT NULL DEFAULT '[]' | JSON array of allergy objects: {allergen, severity, reaction, treatment, epipen_location} |
| chronic_conditions | TEXT NOT NULL DEFAULT '[]' | JSON array: {condition, diagnosis_date, notes} |
| physician_name | TEXT NOT NULL DEFAULT '' | |
| physician_phone | TEXT NOT NULL DEFAULT '' | |
| physician_address | TEXT NOT NULL DEFAULT '' | |
| health_insurance_carrier | TEXT NOT NULL DEFAULT '' | |
| health_insurance_id | TEXT NOT NULL DEFAULT '' | |
| blood_type | TEXT NOT NULL CHECK | `A+ / A- / B+ / B- / AB+ / AB- / O+ / O- / unknown` |
| height_cm | TEXT NOT NULL DEFAULT '' | |
| weight_kg | TEXT NOT NULL DEFAULT '' | |
| vision_screening_date | TEXT NOT NULL DEFAULT '' | |
| hearing_screening_date | TEXT NOT NULL DEFAULT '' | |
| dental_screening_date | TEXT NOT NULL DEFAULT '' | |
| activity_restriction | TEXT NOT NULL DEFAULT '' | PE/sports restrictions |
| activity_restriction_notes | TEXT NOT NULL DEFAULT '' | |
| is_provisional_immunization | INTEGER NOT NULL DEFAULT 0 | Student on immunization catch-up |
| provisional_enrollment_end_date | TEXT NOT NULL DEFAULT '' | Deadline for immunization catch-up |
| is_mckinney_vento | INTEGER NOT NULL DEFAULT 0 | Homeless student flag — immunization deferral |
| emergency_instructions | TEXT NOT NULL DEFAULT '' | Special emergency procedures |
| profile_status | TEXT NOT NULL CHECK | `active / incomplete / archived` |
| last_verified_date | TEXT NOT NULL DEFAULT '' | Nurse verification date |
| last_verified_by | TEXT NOT NULL DEFAULT '' | |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id)`, `(company_id, profile_status)`, `(is_provisional_immunization, provisional_enrollment_end_date)`

---

### 3.2 `educlaw_k12_health_visit`

Each nurse office visit is a separate record. Immutable after creation (no `updated_at`).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| visit_date | TEXT NOT NULL | ISO date |
| visit_time | TEXT NOT NULL DEFAULT '' | HH:MM |
| chief_complaint | TEXT NOT NULL CHECK | `headache / stomachache / injury / fever / respiratory / mental_health / medication / vision / hearing / dental / skin / fatigue / other` |
| complaint_detail | TEXT NOT NULL DEFAULT '' | Free text |
| temperature | TEXT NOT NULL DEFAULT '' | Celsius or Fahrenheit string |
| pulse | TEXT NOT NULL DEFAULT '' | bpm |
| assessment | TEXT NOT NULL DEFAULT '' | Nurse assessment narrative |
| treatment_provided | TEXT NOT NULL DEFAULT '' | |
| disposition | TEXT NOT NULL CHECK | `returned_to_class / sent_home / 911_called / referred_to_physician / observation / no_action` |
| parent_contacted | INTEGER NOT NULL DEFAULT 0 | |
| parent_contact_time | TEXT NOT NULL DEFAULT '' | |
| parent_response | TEXT NOT NULL DEFAULT '' | |
| is_emergency | INTEGER NOT NULL DEFAULT 0 | |
| academic_term_id | TEXT → `educlaw_academic_term(id)` | Nullable |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, visit_date)`, `(company_id, visit_date)`, `(disposition)`

---

### 3.3 `educlaw_k12_student_medication`

Medications authorized to be administered at school. Catalog record (not an administration log).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| medication_name | TEXT NOT NULL DEFAULT '' | Brand or generic name |
| dosage | TEXT NOT NULL DEFAULT '' | e.g., "250mg" |
| route | TEXT NOT NULL CHECK | `oral / topical / inhalation / injection / nasal / eye_drops / ear_drops / other` |
| frequency | TEXT NOT NULL CHECK | `once_daily / twice_daily / three_times_daily / as_needed / as_scheduled` |
| administration_time | TEXT NOT NULL DEFAULT '[]' | JSON array of HH:MM strings |
| prescribing_physician | TEXT NOT NULL DEFAULT '' | |
| physician_authorization_date | TEXT NOT NULL DEFAULT '' | |
| start_date | TEXT NOT NULL DEFAULT '' | |
| end_date | TEXT NOT NULL DEFAULT '' | |
| supply_count | INTEGER NOT NULL DEFAULT 0 | Current supply at school |
| storage_instructions | TEXT NOT NULL DEFAULT '' | e.g., "Refrigerate" |
| administration_instructions | TEXT NOT NULL DEFAULT '' | Special notes |
| is_controlled_substance | INTEGER NOT NULL DEFAULT 0 | Narcotics, ADHD meds |
| medication_status | TEXT NOT NULL CHECK | `active / expired / discontinued` |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, medication_status)`, `(company_id, medication_status)`

---

### 3.4 `educlaw_k12_medication_log`

Immutable log of each medication administration event.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_medication_id | TEXT NOT NULL → `educlaw_k12_student_medication(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| log_date | TEXT NOT NULL | ISO date |
| log_time | TEXT NOT NULL | HH:MM |
| dose_given | TEXT NOT NULL DEFAULT '' | Actual dose given |
| administered_by | TEXT NOT NULL DEFAULT '' | Staff name/ID |
| student_response | TEXT NOT NULL DEFAULT '' | Any observed reaction |
| is_refused | INTEGER NOT NULL DEFAULT 0 | Student refused medication |
| refusal_reason | TEXT NOT NULL DEFAULT '' | |
| notes | TEXT NOT NULL DEFAULT '' | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_medication_id, log_date)`, `(student_id, log_date)`

---

### 3.5 `educlaw_k12_immunization`

Per-vaccine immunization record for a student. Multiple records per student (one per dose of each vaccine).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| vaccine_name | TEXT NOT NULL DEFAULT '' | Standard name (e.g., "MMR", "DTaP") |
| cvx_code | TEXT NOT NULL DEFAULT '' | CDC CVX vaccine code |
| dose_number | INTEGER NOT NULL DEFAULT 1 | e.g., 1, 2, 3 for series |
| administration_date | TEXT NOT NULL DEFAULT '' | Date given |
| lot_number | TEXT NOT NULL DEFAULT '' | Vaccine lot |
| manufacturer | TEXT NOT NULL DEFAULT '' | |
| provider_name | TEXT NOT NULL DEFAULT '' | Administering provider |
| source | TEXT NOT NULL CHECK | `manual / iis_sync / provider_import` |
| iis_record_id | TEXT NOT NULL DEFAULT '' | State IIS identifier (for sync) |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, cvx_code, dose_number)`, `(company_id, administration_date)`

---

### 3.6 `educlaw_k12_immunization_waiver`

Exemption record when a student cannot or will not receive a required vaccine.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| vaccine_name | TEXT NOT NULL DEFAULT '' | Which vaccine is exempted |
| cvx_code | TEXT NOT NULL DEFAULT '' | |
| waiver_type | TEXT NOT NULL CHECK | `medical / religious / philosophical` |
| waiver_basis | TEXT NOT NULL DEFAULT '' | Reason/explanation |
| issuing_physician | TEXT NOT NULL DEFAULT '' | For medical waivers |
| issue_date | TEXT NOT NULL DEFAULT '' | |
| expiry_date | TEXT NOT NULL DEFAULT '' | Medical waivers often have expiry |
| waiver_status | TEXT NOT NULL CHECK | `active / expired / revoked` |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, waiver_status)`, `(company_id, waiver_type, waiver_status)`, `(expiry_date, waiver_status)`

---

## 4. Domain 3: Special Education Tables (9 tables)

### 4.1 `educlaw_k12_sped_referral`

Initial referral to special education evaluation process.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| naming_series | TEXT NOT NULL UNIQUE | e.g., SPED-REF-000023 |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| referral_date | TEXT NOT NULL DEFAULT '' | Starts clock |
| referral_source | TEXT NOT NULL CHECK | `teacher / parent / counselor / physician / self / administrator / other` |
| referral_reason | TEXT NOT NULL DEFAULT '' | Areas of concern narrative |
| areas_of_concern | TEXT NOT NULL DEFAULT '[]' | JSON array: `[academic, behavioral, communication, motor, social_emotional]` |
| prior_interventions | TEXT NOT NULL DEFAULT '' | MTSS/RTI interventions already tried |
| referral_status | TEXT NOT NULL CHECK | `received / consent_pending / consent_received / consent_denied / evaluation_in_progress / evaluation_complete / closed` |
| consent_request_date | TEXT NOT NULL DEFAULT '' | When consent form sent to parents |
| consent_received_date | TEXT NOT NULL DEFAULT '' | 60-day clock starts here |
| consent_denied_date | TEXT NOT NULL DEFAULT '' | If parents refused evaluation |
| evaluation_deadline | TEXT NOT NULL DEFAULT '' | consent_received_date + 60 days |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id)`, `(company_id, referral_status)`, `(evaluation_deadline, referral_status)`

---

### 4.2 `educlaw_k12_sped_evaluation`

Documents each evaluation component conducted during the assessment process.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| referral_id | TEXT NOT NULL → `educlaw_k12_sped_referral(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| evaluation_type | TEXT NOT NULL CHECK | `psychological / academic_achievement / speech_language / occupational_therapy / physical_therapy / hearing_screening / vision_screening / social_behavioral / classroom_observation / adaptive_behavior / other` |
| evaluator_name | TEXT NOT NULL DEFAULT '' | |
| evaluator_role | TEXT NOT NULL DEFAULT '' | e.g., "School Psychologist" |
| evaluation_date | TEXT NOT NULL DEFAULT '' | |
| instrument_used | TEXT NOT NULL DEFAULT '' | Test name/tool used |
| findings_summary | TEXT NOT NULL DEFAULT '' | Narrative findings |
| scores | TEXT NOT NULL DEFAULT '{}' | JSON: standard scores, percentiles |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(referral_id)`, `(student_id, evaluation_type)`

---

### 4.3 `educlaw_k12_sped_eligibility`

Eligibility determination record — the output of the evaluation meeting.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| referral_id | TEXT NOT NULL UNIQUE → `educlaw_k12_sped_referral(id)` | One eligibility per referral |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| eligibility_meeting_date | TEXT NOT NULL DEFAULT '' | |
| iep_deadline | TEXT NOT NULL DEFAULT '' | eligibility_date + 30 days |
| is_eligible | INTEGER NOT NULL DEFAULT 0 | 1 = eligible for IDEA |
| disability_categories | TEXT NOT NULL DEFAULT '[]' | JSON array from 13 IDEA categories |
| primary_disability | TEXT NOT NULL CHECK | One of 13 IDEA category codes |
| adverse_educational_effect | TEXT NOT NULL DEFAULT '' | How disability impacts education |
| eligibility_status | TEXT NOT NULL CHECK | `eligible / ineligible / deferred` |
| ineligibility_reason | TEXT NOT NULL DEFAULT '' | If not eligible |
| team_members_present | TEXT NOT NULL DEFAULT '[]' | JSON array of names/roles |
| parent_consent_date | TEXT NOT NULL DEFAULT '' | Parent signature on eligibility |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, is_eligible)`, `(iep_deadline, is_eligible)`, `(company_id, eligibility_status)`

**Primary Disability CHECK values:**
```
specific_learning_disability / speech_language_impairment / other_health_impairment /
autism_spectrum_disorder / intellectual_disability / emotional_disturbance /
developmental_delay / multiple_disabilities / hearing_impairment / orthopedic_impairment /
visual_impairment / traumatic_brain_injury / deaf_blindness
```

---

### 4.4 `educlaw_k12_iep`

The IEP document header. One active IEP per student at a time; amendments create new versions.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| naming_series | TEXT NOT NULL UNIQUE | e.g., IEP-2025-000041 |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| eligibility_id | TEXT NOT NULL → `educlaw_k12_sped_eligibility(id)` | |
| iep_version | INTEGER NOT NULL DEFAULT 1 | Increments on annual review |
| is_amendment | INTEGER NOT NULL DEFAULT 0 | 1 if mid-year amendment |
| parent_iep_id | TEXT → `educlaw_k12_iep(id)` | FK to prior version (nullable) |
| iep_meeting_date | TEXT NOT NULL DEFAULT '' | |
| iep_start_date | TEXT NOT NULL DEFAULT '' | |
| iep_end_date | TEXT NOT NULL DEFAULT '' | 12 months from start |
| annual_review_due_date | TEXT NOT NULL DEFAULT '' | Same as end_date |
| triennial_reevaluation_due_date | TEXT NOT NULL DEFAULT '' | From first eligibility + 3 years |
| plaafp_academic | TEXT NOT NULL DEFAULT '' | Present levels — academic |
| plaafp_functional | TEXT NOT NULL DEFAULT '' | Present levels — functional |
| lre_percentage_general_ed | TEXT NOT NULL DEFAULT '' | % time in general ed |
| lre_justification | TEXT NOT NULL DEFAULT '' | If < 80% in general ed |
| state_assessment_participation | TEXT NOT NULL CHECK | `standard / with_accommodations / alternate_assessment / exempt` |
| transition_plan_required | INTEGER NOT NULL DEFAULT 0 | Auto-set if student >= 16 |
| transition_postsecondary_goal | TEXT NOT NULL DEFAULT '' | |
| transition_employment_goal | TEXT NOT NULL DEFAULT '' | |
| transition_independent_living_goal | TEXT NOT NULL DEFAULT '' | |
| progress_report_frequency | TEXT NOT NULL CHECK | `quarterly / semester / monthly / other` |
| iep_status | TEXT NOT NULL CHECK | `draft / active / amended / expired / superseded` |
| parent_consent_date | TEXT NOT NULL DEFAULT '' | |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, iep_status)`, `(annual_review_due_date, iep_status)`, `(triennial_reevaluation_due_date)`

---

### 4.5 `educlaw_k12_iep_goal`

Measurable annual goals within an IEP. Each goal tracks progress independently.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| iep_id | TEXT NOT NULL → `educlaw_k12_iep(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| goal_area | TEXT NOT NULL CHECK | `reading / writing / math / communication / social_emotional / behavioral / motor / vocational / adaptive / other` |
| goal_description | TEXT NOT NULL DEFAULT '' | Measurable goal statement |
| baseline_performance | TEXT NOT NULL DEFAULT '' | Current level at IEP creation |
| target_performance | TEXT NOT NULL DEFAULT '' | End-of-year target |
| measurement_method | TEXT NOT NULL CHECK | `test_score / work_sample / observation / rubric / checklist / probe / other` |
| monitoring_frequency | TEXT NOT NULL CHECK | `weekly / biweekly / monthly / quarterly / per_marking_period` |
| responsible_provider | TEXT NOT NULL DEFAULT '' | Staff responsible for this goal |
| sort_order | INTEGER NOT NULL DEFAULT 0 | |
| is_met | INTEGER NOT NULL DEFAULT 0 | Set at annual review |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(iep_id)`, `(student_id, is_met)`, `(responsible_provider)`

---

### 4.6 `educlaw_k12_iep_service`

Special education and related services mandated in the IEP (the service delivery contract).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| iep_id | TEXT NOT NULL → `educlaw_k12_iep(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| service_type | TEXT NOT NULL CHECK | `special_education_instruction / speech_therapy / occupational_therapy / physical_therapy / counseling / transportation / assistive_technology / health_services / orientation_mobility / other` |
| service_setting | TEXT NOT NULL CHECK | `general_ed_classroom / resource_room / self_contained / separate_school / home / hospital / other` |
| frequency_minutes_per_week | INTEGER NOT NULL DEFAULT 0 | IEP-mandated minutes |
| provider_name | TEXT NOT NULL DEFAULT '' | |
| provider_role | TEXT NOT NULL DEFAULT '' | |
| start_date | TEXT NOT NULL DEFAULT '' | |
| end_date | TEXT NOT NULL DEFAULT '' | |
| total_minutes_delivered | INTEGER NOT NULL DEFAULT 0 | Running sum from session logs |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(iep_id)`, `(student_id, service_type)`

---

### 4.7 `educlaw_k12_iep_service_log`

Immutable log of each service delivery session. Powers planned vs. actual compliance reporting.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| iep_service_id | TEXT NOT NULL → `educlaw_k12_iep_service(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| session_date | TEXT NOT NULL | ISO date |
| minutes_delivered | INTEGER NOT NULL DEFAULT 0 | |
| session_notes | TEXT NOT NULL DEFAULT '' | |
| provider_name | TEXT NOT NULL DEFAULT '' | |
| is_makeup_session | INTEGER NOT NULL DEFAULT 0 | Makeup for missed session? |
| was_session_missed | INTEGER NOT NULL DEFAULT 0 | 1 if service was not provided |
| missed_reason | TEXT NOT NULL DEFAULT '' | Absence, provider unavailable, etc. |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(iep_service_id, session_date)`, `(student_id, session_date)`

---

### 4.8 `educlaw_k12_iep_team_member`

IEP team composition (who participated in IEP meeting and has access to IEP).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| iep_id | TEXT NOT NULL → `educlaw_k12_iep(id)` | |
| member_type | TEXT NOT NULL CHECK | `parent / student / general_ed_teacher / special_ed_teacher / administrator / school_psychologist / speech_pathologist / ot / pt / counselor / other_agency / other` |
| member_name | TEXT NOT NULL DEFAULT '' | |
| member_role | TEXT NOT NULL DEFAULT '' | Job title |
| guardian_id | TEXT → `educlaw_guardian(id)` | Nullable — for parent members |
| instructor_id | TEXT → `educlaw_instructor(id)` | Nullable — for teacher members |
| attended_meeting | INTEGER NOT NULL DEFAULT 1 | |
| excused_absence | INTEGER NOT NULL DEFAULT 0 | IDEA allows excused absence w/ written agreement |
| signature_date | TEXT NOT NULL DEFAULT '' | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(iep_id)`, `(iep_id, member_type)`

---

### 4.9 `educlaw_k12_iep_progress`

Progress monitoring notes per goal, per reporting period.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| iep_goal_id | TEXT NOT NULL → `educlaw_k12_iep_goal(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | Denormalized |
| reporting_period | TEXT NOT NULL DEFAULT '' | "Q1 2025-2026", "Semester 1", etc. |
| progress_date | TEXT NOT NULL | When documented |
| progress_rating | TEXT NOT NULL CHECK | `met_goal / on_track / some_progress / insufficient_progress / not_started / regression` |
| current_performance | TEXT NOT NULL DEFAULT '' | Current level at reporting |
| evidence | TEXT NOT NULL DEFAULT '' | Test scores, observation notes |
| notes_for_parents | TEXT NOT NULL DEFAULT '' | Plain-language parent communication |
| documented_by | TEXT NOT NULL DEFAULT '' | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(iep_goal_id, reporting_period)`, `(student_id, progress_date)`

---

### 4.10 `educlaw_k12_504_plan`

Section 504 accommodation plan (simpler than IEP; different legal framework).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| naming_series | TEXT NOT NULL UNIQUE | e.g., 504-2025-000008 |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| meeting_date | TEXT NOT NULL DEFAULT '' | |
| disability_description | TEXT NOT NULL DEFAULT '' | How disability limits major life activity |
| eligibility_basis | TEXT NOT NULL DEFAULT '' | Evaluation data used |
| plan_start_date | TEXT NOT NULL DEFAULT '' | |
| plan_end_date | TEXT NOT NULL DEFAULT '' | Typically 1 year |
| review_date | TEXT NOT NULL DEFAULT '' | |
| accommodations | TEXT NOT NULL DEFAULT '[]' | JSON array of accommodation objects |
| team_members | TEXT NOT NULL DEFAULT '[]' | JSON array of name/role |
| parent_consent_date | TEXT NOT NULL DEFAULT '' | |
| plan_status | TEXT NOT NULL CHECK | `active / expired / revised / discontinued` |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, plan_status)`, `(review_date, plan_status)`

---

## 5. Domain 4: Grade Promotion Tables (3 tables)

### 5.1 `educlaw_k12_promotion_review`

The at-risk assessment / promotion eligibility record for each student at end of year.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| academic_year_id | TEXT NOT NULL → `educlaw_academic_year(id)` | |
| grade_level | TEXT NOT NULL DEFAULT '' | Current grade level (K, 1-12) |
| review_date | TEXT NOT NULL DEFAULT '' | When review was completed |
| gpa_ytd | TEXT NOT NULL DEFAULT '' | GPA at time of review |
| attendance_rate_ytd | TEXT NOT NULL DEFAULT '' | % present at review |
| failing_subjects | TEXT NOT NULL DEFAULT '[]' | JSON array of subject names |
| discipline_incident_count | INTEGER NOT NULL DEFAULT 0 | YTD incident count |
| teacher_recommendation | TEXT NOT NULL CHECK | `promote / retain / conditional / pending` |
| teacher_rationale | TEXT NOT NULL DEFAULT '' | |
| counselor_recommendation | TEXT NOT NULL CHECK | `promote / retain / conditional / pending` |
| counselor_notes | TEXT NOT NULL DEFAULT '' | |
| is_idea_eligible | INTEGER NOT NULL DEFAULT 0 | Affects retention decision process |
| prior_retention_count | INTEGER NOT NULL DEFAULT 0 | Prior years held back |
| interventions_tried | TEXT NOT NULL DEFAULT '[]' | JSON array of intervention descriptions |
| review_status | TEXT NOT NULL CHECK | `pending / in_review / decided / notified / appealed` |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, academic_year_id)`, `(company_id, grade_level, review_status)`, `(academic_year_id, teacher_recommendation)`

---

### 5.2 `educlaw_k12_promotion_decision`

The final, immutable decision record. Created once per student per year when decision is made.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| promotion_review_id | TEXT NOT NULL UNIQUE → `educlaw_k12_promotion_review(id)` | |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| academic_year_id | TEXT NOT NULL → `educlaw_academic_year(id)` | |
| decision | TEXT NOT NULL CHECK | `promote / retain / conditional_promote` |
| decision_date | TEXT NOT NULL DEFAULT '' | |
| decided_by | TEXT NOT NULL DEFAULT '' | Principal or team lead |
| rationale | TEXT NOT NULL DEFAULT '' | Documented justification |
| team_members | TEXT NOT NULL DEFAULT '[]' | JSON array of name/role |
| conditions | TEXT NOT NULL DEFAULT '' | If conditional_promote: conditions required |
| parent_notified_date | TEXT NOT NULL DEFAULT '' | Legal notification date |
| parent_notified_by | TEXT NOT NULL DEFAULT '' | |
| notification_method | TEXT NOT NULL CHECK | `in_person / letter / email / phone` |
| appeal_deadline | TEXT NOT NULL DEFAULT '' | Parent appeal deadline |
| is_appealed | INTEGER NOT NULL DEFAULT 0 | |
| appeal_outcome | TEXT NOT NULL CHECK | `promote / retain / not_applicable` |
| appeal_decision_date | TEXT NOT NULL DEFAULT '' | |
| next_grade_level | TEXT NOT NULL DEFAULT '' | Grade for next year (if promoted) |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | Immutable — no updated_at |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, academic_year_id)`, `(academic_year_id, decision)`, `(parent_notified_date)`

---

### 5.3 `educlaw_k12_intervention_plan`

Support plan for at-risk or retained students. Created during early warning (mid-year) or at retention decision.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| student_id | TEXT NOT NULL → `educlaw_student(id)` | |
| academic_year_id | TEXT NOT NULL → `educlaw_academic_year(id)` | |
| trigger | TEXT NOT NULL CHECK | `at_risk_mid_year / retention_decision / other` |
| intervention_types | TEXT NOT NULL DEFAULT '[]' | JSON array: `[tutoring, extended_day, counseling, family_conference, mentorship]` |
| academic_targets | TEXT NOT NULL DEFAULT '' | Specific targets (e.g., "Raise math grade to C by March") |
| attendance_target | TEXT NOT NULL DEFAULT '' | Target attendance rate |
| assigned_staff | TEXT NOT NULL DEFAULT '' | Responsible person |
| start_date | TEXT NOT NULL DEFAULT '' | |
| review_date | TEXT NOT NULL DEFAULT '' | Check-in date |
| parent_notification_date | TEXT NOT NULL DEFAULT '' | |
| plan_status | TEXT NOT NULL CHECK | `active / completed / abandoned` |
| outcome_notes | TEXT NOT NULL DEFAULT '' | Results at review date |
| company_id | TEXT NOT NULL → `company(id)` | |
| created_at | TEXT NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT NOT NULL DEFAULT '' | |

**Indexes:** `(student_id, academic_year_id)`, `(company_id, plan_status)`, `(review_date, plan_status)`

---

## 6. Entity Relationship Summary

```
educlaw_student (PARENT)
├── educlaw_k12_health_profile (1:1)
│   ├── educlaw_k12_health_visit (1:many, immutable)
│   ├── educlaw_k12_student_medication (1:many)
│   │   └── educlaw_k12_medication_log (1:many, immutable)
│   ├── educlaw_k12_immunization (1:many, immutable)
│   └── educlaw_k12_immunization_waiver (1:many)
│
├── educlaw_k12_sped_referral (1:many over time)
│   └── educlaw_k12_sped_evaluation (1:many, immutable)
│   └── educlaw_k12_sped_eligibility (1:1 per referral, immutable)
│       └── educlaw_k12_iep (1:many versions)
│           ├── educlaw_k12_iep_goal (1:many, immutable)
│           │   └── educlaw_k12_iep_progress (1:many per period, immutable)
│           ├── educlaw_k12_iep_service (1:many, immutable)
│           │   └── educlaw_k12_iep_service_log (1:many, immutable)
│           └── educlaw_k12_iep_team_member (1:many, immutable)
│
├── educlaw_k12_504_plan (1:many over time)
│
├── educlaw_k12_promotion_review (1 per academic_year)
│   ├── educlaw_k12_promotion_decision (1:1, immutable)
│   └── educlaw_k12_intervention_plan (1:many)
│
└── [via educlaw_k12_discipline_student]
    educlaw_k12_discipline_incident (many:many through discipline_student)
    ├── educlaw_k12_discipline_action (per involvement)
    └── educlaw_k12_manifestation_review (per MDR trigger)
```

---

## 7. Status Lifecycles

### Discipline Incident
```
open → under_review → closed
                    → appealed → closed
```

### Special Education Referral
```
received → consent_pending → consent_received → evaluation_in_progress → evaluation_complete → closed
                           → consent_denied → closed
```

### IEP
```
draft → active → amended (amendment created; original becomes superseded)
     → expired (after end_date, if not renewed)
     → superseded (when new version created at annual review)
```

### Promotion Review
```
pending → in_review → decided → notified
                             → appealed → decided (final)
```

---

## 8. Key Business Rules

1. **One active IEP per student:** A student can only have one `iep_status = 'active'` IEP. Creating a new annual review IEP must set the prior one to `superseded`.
2. **One health profile per student:** `educlaw_k12_health_profile.student_id` has UNIQUE constraint.
3. **MDR threshold:** When the sum of `duration_days` from `educlaw_k12_discipline_action` for action_type `out_of_school_suspension` or `in_school_suspension` reaches 10 days for an IDEA-eligible student in an academic year, flag MDR required.
4. **Immunization immutability:** Immunization records (`educlaw_k12_immunization`) are immutable — no `updated_at`. Corrections require a new record with a note linking to the corrected record.
5. **IEP goals are immutable:** Once an IEP is `active`, goals cannot be edited. Amendments create a new IEP version.
6. **Promotion decisions are immutable:** `educlaw_k12_promotion_decision` has no `updated_at`. Appeals create an `is_appealed` flag + `appeal_outcome` field (set at creation of decision record's appeal resolution).
7. **FERPA logging:** Every action that reads health, discipline, or special ed data must INSERT into `educlaw_data_access_log` with appropriate `data_category`.

---

## 9. Recommended Action Count

| Domain | Estimated Actions |
|--------|------------------|
| Discipline | 12–15 (add-incident, add-discipline-student, add-discipline-action, close-incident, add-mdr, add-pbis-recognition, get-discipline-history, list-discipline-incidents, get-discipline-report, get-cumulative-suspension-days, notify-guardians-discipline, generate-discipline-state-report) |
| Health Records | 18–22 (add-health-profile, update-health-profile, get-health-profile, add-office-visit, list-office-visits, add-medication, update-medication, log-medication-admin, list-medication-logs, add-immunization, add-immunization-waiver, get-immunization-record, check-immunization-compliance, generate-immunization-report) |
| Special Education | 25–30 (create-sped-referral, update-sped-referral, add-sped-evaluation, record-eligibility, add-iep, update-iep, add-iep-goal, add-iep-service, log-service-session, add-iep-team-member, record-iep-progress, generate-iep-report, get-service-compliance, add-504-plan, update-504-plan, get-active-iep) |
| Grade Promotion | 10–12 (create-promotion-review, update-promotion-review, generate-promotion-list, submit-promotion-decision, notify-promotion-decision, submit-appeal, batch-promote-grade, create-intervention-plan) |
| **Total** | **65–79 actions** |
