# Parent Product Analysis: EduClaw

**Parent:** educlaw
**Parent Path:** educlaw
**Analysis Date:** 2026-03-05
**Analyzed By:** ERPForge Researcher Agent

---

## 1. Product Overview

EduClaw is a full K-12 through higher-education Student Information System (SIS) built on ERPClaw's shared foundation. It provides the operational core of institutional education management: student lifecycle, academic calendar, enrollment, grading, attendance, fees, and communications.

| Attribute | Value |
|-----------|-------|
| Tables | 32 |
| Columns | 419 |
| Indexes | 88 |
| Domains | 8 (students, academics, enrollment, grading, attendance, staff, fees, communications) |
| Foundation | erpclaw-setup, erpclaw-gl, erpclaw-selling, erpclaw-payments, erpclaw-hr |

---

## 2. Database Tables (Full Inventory)

### Academic Calendar
| Table | Purpose |
|-------|---------|
| `educlaw_academic_year` | Annual school year with start/end dates, company-scoped |
| `educlaw_academic_term` | Terms within year (semester, quarter, trimester, summer, custom); lifecycle: setup→enrollment_open→active→grades_open→grades_finalized→closed |

### Organization & Curriculum
| Table | Purpose |
|-------|---------|
| `educlaw_program` | Degree/program types (k12, associate, bachelor, master, doctoral, certificate, diploma) |
| `educlaw_program_requirement` | Courses required per program (required, elective, core, major, general_education) |
| `educlaw_course` | Courses with code, credit hours, type (lecture/lab/seminar/etc.), grade level |
| `educlaw_course_prerequisite` | Prerequisite relationships between courses, with min_grade enforcement |
| `educlaw_room` | Physical rooms (classroom, lab, auditorium, gym, library, office) |
| `educlaw_section` | Course sections per term with instructor, room, schedule, enrollment limits |

### People
| Table | Purpose |
|-------|---------|
| `educlaw_student_applicant` | Admission pipeline; status: applied→under_review→accepted→confirmed→enrolled |
| `educlaw_student` | Enrolled student with demographics (DOB, gender, address), academic standing, GPA, FERPA/COPPA flags |
| `educlaw_guardian` | Parent/guardian with relationship to customer (billing) |
| `educlaw_student_guardian` | Junction: custody, pickup permission, comms consent, emergency contact |
| `educlaw_instructor` | Faculty linked to HR employee record |

### Enrollment
| Table | Purpose |
|-------|---------|
| `educlaw_program_enrollment` | Student's enrollment in a program for an academic year |
| `educlaw_course_enrollment` | Student enrolled in a course section; grade lifecycle |
| `educlaw_waitlist` | Section waitlist with position, offer expiry |

### Grading & Assessment
| Table | Purpose |
|-------|---------|
| `educlaw_grading_scale` | Named grade scales per company |
| `educlaw_grading_scale_entry` | Letter grades with points, min/max %, passing flag |
| `educlaw_assessment_plan` | Per-section assessment plan |
| `educlaw_assessment_category` | Weighted categories (e.g., Homework 20%, Exams 50%) |
| `educlaw_assessment` | Individual assessments with max points, due date |
| `educlaw_assessment_result` | Student scores per assessment |
| `educlaw_grade_amendment` | Immutable grade change audit trail |

### Attendance
| Table | Purpose |
|-------|---------|
| `educlaw_student_attendance` | Daily/section attendance: present, absent, tardy, excused, half_day; sources: manual, biometric, app |

### Compliance & Consent
| Table | Purpose |
|-------|---------|
| `educlaw_consent_record` | FERPA/COPPA consent grants with type, expiry, revocation |
| `educlaw_data_access_log` | Immutable log of who accessed which student data category |

### Fees & Scholarships
| Table | Purpose |
|-------|---------|
| `educlaw_fee_category` | Revenue categories linked to GL accounts |
| `educlaw_fee_structure` | Fee schedule per program/term/grade level |
| `educlaw_fee_structure_item` | Line items within fee structure |
| `educlaw_scholarship` | Student discounts (fixed/percentage) |

### Communications
| Table | Purpose |
|-------|---------|
| `educlaw_announcement` | Broadcast messages with audience targeting |
| `educlaw_notification` | Per-recipient notifications (grade_posted, fee_due, absence, enrollment_confirmed, etc.) |

---

## 3. Foundation Tables Available (from ERPClaw)

| Table | Relevance to State Reporting |
|-------|------------------------------|
| `company` | LEA (district) identifier — maps to Ed-Fi EducationOrganization |
| `department` | Maps to academic departments |
| `employee` | Staff — maps to Ed-Fi Staff entities |
| `customer` | Guardian billing — can be extended for CRDC family income data |
| `account` | GL revenue accounts |

---

## 4. Key Actions Inventory

### Students Domain
- `create-applicant`, `update-applicant`, `accept-applicant`, `reject-applicant`, `admit-student`
- `create-student`, `update-student`, `get-student`, `list-students`
- `create-guardian`, `link-guardian`
- `create-consent`, `revoke-consent`
- `log-data-access`, `get-data-access-log`

### Academics Domain
- `create-academic-year`, `update-academic-year`
- `create-academic-term`, `update-academic-term`, `advance-term-status`
- `create-program`, `create-course`, `add-prerequisite`
- `create-section`, `update-section`, `open-section`
- `create-room`

### Enrollment Domain
- `create-program-enrollment`, `cancel-program-enrollment`
- `create-section-enrollment`, `cancel-enrollment`, `terminate-enrollment`
- `apply-waitlist`, `list-waitlist`

### Grading Domain
- `create-grading-scale`, `add-grading-scale-entry`
- `create-assessment-plan`, `add-assessment-category`, `create-assessment`
- `record-assessment-result`, `calculate-grade`, `submit-grades`
- `amend-grade`, `get-transcript`, `get-report-card`, `calculate-gpa`

### Attendance Domain
- `record-attendance`, `record-batch-attendance`, `update-attendance`
- `get-attendance-summary`, `get-section-attendance`, `get-truancy-report`

### Fees Domain
- `create-fee-structure`, `apply-fee-structure`, `create-scholarship`

### Communications Domain
- `create-announcement`, `send-notification`

---

## 5. What EduClaw Already Provides (Reusable for State Reporting)

### Directly Reusable Data

| Data Element | EduClaw Table | State Reporting Use |
|--------------|---------------|---------------------|
| Student demographics | `educlaw_student` | Enrollment counts, demographic disaggregation |
| DOB, gender, grade level | `educlaw_student` | IDEA child count, CRDC demographics |
| Enrollment date/status | `educlaw_program_enrollment`, `educlaw_course_enrollment` | ADA, membership counts |
| Attendance records | `educlaw_student_attendance` | ADA calculation, chronic absenteeism, CRDC |
| Grades/credits | `educlaw_course_enrollment` | Graduation rate, academic achievement |
| Assessment results | `educlaw_assessment_result` | Academic performance reporting |
| Staff (via employee) | `educlaw_instructor` | Staff FTE, teacher counts |
| Academic year/term | `educlaw_academic_year/term` | Reporting period boundaries |
| FERPA consent | `educlaw_consent_record` | Data sharing permissions |
| Program type | `educlaw_program` | Program participation |

### Reusable Computed Data
- **GPA calculation** — feeds academic achievement reporting
- **Truancy report** — feeds chronic absenteeism calculation
- **Attendance summary** — feeds ADA calculation
- **Grade submission workflow** — feeds transcript/achievement data

---

## 6. What EduClaw Does NOT Have (Gaps for State Reporting)

This is the core scope of `educlaw-statereport`. The following are completely absent from the parent:

### Critical Missing Data
| Gap | State Reporting Requirement |
|-----|----------------------------|
| **Discipline records** | IDEA discipline, CRDC suspension/expulsion, EDFacts discipline files |
| **Special Education (IEP/504)** | IDEA child count, disability category, educational environment |
| **English Language Learner (ELL/EL)** | EL program participation, Title III reporting |
| **Race/ethnicity** | All CRDC disaggregation, EDFacts demographic breakdowns |
| **Economically disadvantaged flag** | Title I, free/reduced lunch program |
| **Homeless/foster care status** | McKinney-Vento, CRDC, EDFacts |
| **Chronic absenteeism flags** | ESSA accountability, CRDC |
| **Graduation tracking** | Cohort graduation rate (EDFacts FS150) |
| **Staff certification/credentials** | EDFacts staffing files, highly qualified teacher |
| **State-specific ID (SSID)** | State Student ID for state reporting linkage |
| **LEA/School NCES IDs** | Federal org identifiers (NCES LEA/School IDs) |

### Missing Infrastructure
| Gap | Purpose |
|-----|---------|
| **Ed-Fi API client/connector** | Push data to state Ed-Fi ODS |
| **Reporting snapshot engine** | Point-in-time data capture for collection windows |
| **Data validation rules engine** | Pre-submission validation (federal/state rules) |
| **Submission tracker** | Track collection windows, submissions, errors |
| **Error management** | Log, prioritize, and resolve validation errors |
| **Collection window definitions** | Fall, Winter, Spring, EOY collection schedule |
| **Federal report generators** | EDFacts files, CRDC export formats |
| **State-specific mappings** | Map EduClaw entities to state data specifications |
| **Audit trail for submissions** | Immutable submission history |

---

## 7. Integration Points

### How educlaw-statereport Extends educlaw

```
educlaw_student           ──→  sr_student_demographics (race, ELL, SPED flags)
educlaw_student_attendance ──→  sr_ada_calculation (ADA/ADM computation)
educlaw_course_enrollment  ──→  sr_snapshot (enrollment membership counts)
educlaw_program_enrollment ──→  sr_snapshot (program participation)
educlaw_assessment_result  ──→  sr_assessment_report (academic achievement)
educlaw_instructor         ──→  sr_staff_report (FTE, certification)
company (LEA)              ──→  sr_organization_mapping (NCES IDs, Ed-Fi IDs)
```

### Key Foreign Key Patterns

The sub-vertical will:
1. **Extend student records** with `sr_student_supplement` (race, ELL, SPED, economic status, homeless, SSID)
2. **Add discipline domain** (`sr_discipline_incident`, `sr_discipline_action`)
3. **Add special education domain** (`sr_special_education_placement`, `sr_iep_record`)
4. **Add snapshot engine** (`sr_collection_window`, `sr_snapshot`, `sr_snapshot_record`)
5. **Add submission tracking** (`sr_submission`, `sr_submission_error`, `sr_submission_history`)
6. **Add Ed-Fi mapping tables** (`sr_edfi_mapping`, `sr_edfi_resource_log`)
7. **Add validation rules** (`sr_validation_rule`, `sr_validation_result`)

---

## 8. Naming Conventions (from educlaw)

- Tables: `educlaw_` prefix → use `sr_` prefix for state reporting
- UUIDs for all primary keys
- Soft deletes not used — status fields preferred
- `company_id` on all multi-tenant tables
- `naming_series` for human-readable IDs on key entities
- `created_at`, `updated_at`, `created_by` on all tables
- Audit via `erpclaw_lib.audit`
- Responses via `erpclaw_lib.response.ok/err`

---

## 9. Architecture Patterns to Follow

Based on review of educlaw's Python scripts:

1. **Domain modules** — Each domain is a separate Python file (`students.py`, `enrollment.py`, etc.)
2. **ACTIONS dict** — Maps action strings to handler functions
3. **Validation first** — All handlers validate inputs before DB operations
4. **Audit trail** — `audit()` called on all state-changing operations
5. **Notifications** — `educlaw_notification` used for async user alerts
6. **Status lifecycles** — Strict CHECK constraints on status transitions
7. **No soft deletes** — Records are status-updated, not deleted
8. **Batch operations** — Pattern established in `batch_mark_attendance`

---

## 10. Recommendations for Sub-Vertical Design

1. **Don't duplicate** — Never re-store student demographics already in `educlaw_student`. Use foreign keys and joins.
2. **Supplement, don't replace** — Add `sr_student_supplement` for state-specific fields (SSID, race detail, SPED flag).
3. **Snapshot immutability** — Snapshots must be frozen at collection window close. Never re-computed from live data.
4. **Ed-Fi as protocol, not model** — EduClaw's tables are the source of truth; Ed-Fi mappings are output adapters.
5. **Multi-state aware** — Use `state_code` on collection windows and mappings; different states have different requirements.
6. **Validation before submission** — Always run validation rules before generating submission files.
7. **Error traceability** — Every validation error must link back to a specific student record and source table.
