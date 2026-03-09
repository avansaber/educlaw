# EduClaw LMS Integration — Parent Product Analysis

**Parent Product:** educlaw
**Parent Path:** educlaw
**Analysis Date:** 2026-03-05

---

## 1. Parent Product Overview

EduClaw is an AI-native Student Information System (SIS) built on ERPClaw. It delivers **112 actions across 8 domains** — students, academics, enrollment, grading, attendance, staff, fees, and communications. It is FERPA/COPPA compliant and integrates with ERPClaw's HR, Selling, and Payments foundations.

### Architecture Pattern
- **Single-package router pattern** — one `db_query.py` router dispatches to domain-specific Python modules
- **SQLite database** at `~/.openclaw/erpclaw/data.sqlite`
- **Offline-first, local-only** — zero external API calls in the base product
- **Fully parameterized SQL** — injection-safe throughout
- **ERPClaw foundation reuse** — customer, sales_invoice, payment_entry, employee, department, audit_log

### Key Vocabulary (Adaptive)
| ERPClaw Term | EduClaw Equivalent |
|---|---|
| Customer | Student |
| Order | Enrollment |
| Transaction | Fee Payment |
| Item | Course |
| Employee | Teacher |

---

## 2. Parent Tables (32 EduClaw-Owned Tables)

### 2.1 Institutional Setup (3 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_academic_year` | name, start_date, end_date, is_active | e.g., "2026-2027" |
| `educlaw_academic_term` | name, term_type, academic_year_id, start_date, end_date, status | status: setup/enrollment_open/active/grades_open/grades_finalized/closed |
| `educlaw_room` | room_number, building, capacity, room_type | classroom/lab/auditorium/gym |

### 2.2 Students (4 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_student_applicant` | naming_series (APP-YYYY-NNNNN), status, applying_for_program_id | Admission pipeline entry |
| `educlaw_student` | naming_series (STU-NNNNN), customer_id, current_program_id, grade_level, cumulative_gpa, is_coppa_applicable | Links to erpclaw-selling customer |
| `educlaw_guardian` | customer_id, relationship, is_primary_contact | Links to erpclaw-selling customer |
| `educlaw_student_guardian` | student_id, guardian_id, relationship, has_custody, receives_communications | Many-to-many junction |

### 2.3 Academics (4 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_program` | code, name, program_type, department_id, total_credits_required | k12/associate/bachelor/master/doctoral/certificate |
| `educlaw_program_requirement` | program_id, course_id, requirement_type, min_grade | required/elective/core/major/general_education |
| `educlaw_course` | course_code, name, credit_hours, department_id, course_type | lecture/lab/seminar/independent_study/internship |
| `educlaw_course_prerequisite` | course_id, prerequisite_course_id, min_grade, is_corequisite | |

### 2.4 Sections & Enrollment (4 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_section` | naming_series (SEC-YYYY-NNNNN), course_id, academic_term_id, instructor_id, room_id, days_of_week, start_time, end_time, max_enrollment, current_enrollment, status | draft/scheduled/open/closed/cancelled |
| `educlaw_program_enrollment` | naming_series (ENR-YYYY-NNNNN), student_id, program_id, academic_year_id, status | active/completed/withdrawn/suspended |
| `educlaw_course_enrollment` | student_id, section_id, status, final_letter_grade, final_grade_points, is_grade_submitted | enrolled/completed/dropped/withdrawn/incomplete/waitlisted |
| `educlaw_waitlist` | student_id, section_id, position, status | waiting/offered/accepted/expired/cancelled |

### 2.5 Grading & Assessment (7 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_grading_scale` | name, is_default | Institution-wide or program-specific |
| `educlaw_grading_scale_entry` | grading_scale_id, letter_grade, grade_points, min_percentage, max_percentage, counts_in_gpa | e.g., A=4.0, 93-100% |
| `educlaw_assessment_plan` | section_id, grading_scale_id | One plan per section |
| `educlaw_assessment_category` | assessment_plan_id, name, weight_percentage | e.g., "Homework 20%, Exams 40%" |
| `educlaw_assessment` | assessment_plan_id, category_id, name, max_points, due_date, is_published | Individual assignment/quiz/exam |
| `educlaw_assessment_result` | assessment_id, student_id, course_enrollment_id, points_earned, is_exempt, is_late, comments | Student score |
| `educlaw_grade_amendment` | course_enrollment_id, old_letter_grade, new_letter_grade, reason, amended_by | Immutable (no updated_at) |

### 2.6 Attendance (1 table)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_student_attendance` | student_id, attendance_date, section_id (nullable), status, source | present/absent/tardy/excused/half_day; source: manual/biometric/app |

### 2.7 Staff/Instructors (1 table)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_instructor` | naming_series (INS-NNNNN), employee_id, credentials, specializations, max_teaching_load_hours, office_hours | Links to erpclaw-hr employee |

### 2.8 Fees & Billing (4 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_fee_category` | name, revenue_account_id | Links to erpclaw-gl account |
| `educlaw_fee_structure` | name, program_id, academic_term_id, total_amount | Fee schedule per program/term |
| `educlaw_fee_structure_item` | fee_structure_id, fee_category_id, amount | Line items |
| `educlaw_scholarship` | student_id, discount_type, discount_amount, applies_to_category_id, status | fixed/percentage |

### 2.9 Communications (2 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_announcement` | title, body, priority, audience_type, audience_filter, status | draft/published/archived |
| `educlaw_notification` | recipient_type, recipient_id, notification_type, is_read, sent_via | grade_posted/fee_due/absence/announcement/etc. |

### 2.10 FERPA Compliance (2 tables)
| Table | Key Fields | Notes |
|-------|-----------|-------|
| `educlaw_data_access_log` | user_id, student_id, data_category, access_type, access_reason | Immutable; every get-student auto-logs |
| `educlaw_consent_record` | student_id, consent_type, granted_by, consent_date, is_revoked | ferpa_directory/ferpa_disclosure/coppa_collection |

---

## 3. Parent Actions (112 Actions Across 8 Domains)

### Students Domain (~19 actions)
`add-student-applicant`, `update-student-applicant`, `approve-applicant`, `convert-applicant-to-student`, `add-student`, `update-student`, `get-student`, `list-students`, `update-student-status`, `complete-graduation`, `get-applicant`, `list-applicants`, `add-guardian`, `update-guardian`, `get-guardian`, `list-guardians`, `assign-guardian`, `record-data-access`, `add-consent-record`, `cancel-consent`, `generate-student-record`

### Academics Domain (~20 actions)
`add-academic-year`, `update-academic-year`, `get-academic-year`, `list-academic-years`, `add-academic-term`, `update-academic-term`, `get-academic-term`, `list-academic-terms`, `add-room`, `update-room`, `list-rooms`, `add-program`, `update-program`, `get-program`, `list-programs`, `add-course`, `update-course`, `get-course`, `list-courses`, `add-section`, `update-section`, `get-section`, `list-sections`, `activate-section`, `cancel-section`

### Enrollment Domain (~10 actions)
`create-program-enrollment`, `cancel-program-enrollment`, `list-program-enrollments`, `create-section-enrollment`, `cancel-enrollment`, `terminate-enrollment`, `get-enrollment`, `list-enrollments`, `apply-waitlist`, `list-waitlist`

### Grading Domain (~16 actions)
`add-grading-scale`, `update-grading-scale`, `list-grading-scales`, `get-grading-scale`, `add-assessment-plan`, `update-assessment-plan`, `get-assessment-plan`, `add-assessment`, `update-assessment`, `list-assessments`, `record-assessment-result`, `record-batch-results`, `generate-section-grade`, `submit-grades`, `update-grade`, `generate-gpa`, `generate-transcript`, `generate-report-card`, `list-grades`

### Attendance Domain (~8 actions)
`record-attendance`, `record-batch-attendance`, `update-attendance`, `get-attendance`, `list-attendance`, `get-attendance-summary`, `get-section-attendance`, `get-truancy-report`

### Staff Domain (~5 actions)
`add-instructor`, `update-instructor`, `get-instructor`, `list-instructors`, `get-teaching-load`

### Fees Domain (~15 actions)
`add-fee-category`, `update-fee-category`, `list-fee-categories`, `add-fee-structure`, `update-fee-structure`, `get-fee-structure`, `list-fee-structures`, `add-scholarship`, `update-scholarship`, `list-scholarships`, `generate-fee-invoice`, `list-fee-invoices`, `get-student-account`, `get-outstanding-fees`, `apply-late-fee`

### Communications Domain (~9 actions)
`add-announcement`, `update-announcement`, `submit-announcement`, `list-announcements`, `get-announcement`, `send-notification`, `list-notifications`, `send-progress-report`, `send-emergency-alert`

---

## 4. ERPClaw Foundation Tables (Reused by Parent)

| Foundation Skill | Tables Used | How EduClaw Uses Them |
|---|---|---|
| **erpclaw-setup** | `company`, `naming_series`, `audit_log` | Institution context, series generation, access audit |
| **erpclaw-gl** | `account`, `cost_center`, `fiscal_year`, `gl_entry` | Tuition revenue accounts, GL postings |
| **erpclaw-selling** | `customer`, `sales_invoice`, `sales_invoice_item` | Student = customer; fee invoice = sales_invoice |
| **erpclaw-payments** | `payment_entry`, `payment_allocation`, `payment_ledger_entry` | Fee payments, outstanding tracking |
| **erpclaw-hr** | `employee`, `department`, `designation`, `attendance` | Instructor = employee; academic departments |

---

## 5. Key Data Entities Relevant to LMS Integration

### 5.1 Directly Reusable by educlaw-lms

| Parent Entity | LMS Relevance | How to Reuse |
|---|---|---|
| `educlaw_student` | LMS user account | student_id maps to LMS user; student email for LMS account creation |
| `educlaw_instructor` | LMS teacher/facilitator | instructor's employee→email for LMS instructor account |
| `educlaw_course` | LMS course definition | course_code maps to LMS course; name, description carry over |
| `educlaw_section` | LMS course section/cohort | section is the unit of LMS sync; each section = one LMS course instance |
| `educlaw_course_enrollment` | LMS roster | enrolled students in a section = LMS course roster |
| `educlaw_assessment` | LMS assignment | name, max_points, due_date map directly to LMS assignment |
| `educlaw_assessment_result` | LMS grade | points_earned maps back from LMS gradebook |
| `educlaw_academic_term` | LMS term/course grouping | term boundaries define LMS course activation windows |
| `educlaw_grading_scale` | LMS grade schema | letter grades and point thresholds for LMS configuration |
| `educlaw_announcement` | LMS announcement | can push to LMS discussion board |

### 5.2 Gaps — What Parent Does NOT Have (educlaw-lms Must Add)

| Missing Concept | Why Needed |
|---|---|
| LMS connection config | OAuth credentials, endpoint URLs, LMS type (Canvas/Moodle/Google) |
| LMS course mapping | SIS section_id ↔ LMS course_id cross-reference |
| LMS user mapping | SIS student_id/instructor_id ↔ LMS user_id cross-reference |
| LMS assignment mapping | SIS assessment_id ↔ LMS assignment_id cross-reference |
| Sync state/log | Track what was synced, when, status, errors |
| Course materials | File attachments, URLs, syllabi (parent has none) |
| Online submission tracking | Assignment submissions from LMS (not in SIS) |
| Grade sync direction/conflict | When SIS grade ≠ LMS grade, which wins? |

---

## 6. Data Flow: Parent → LMS Integration Points

```
Parent (educlaw)                    educlaw-lms                   External LMS
─────────────────                   ───────────────               ─────────────
educlaw_section ────────────────▶ lms_course_mapping ──────────▶ Canvas/Moodle Course
educlaw_course_enrollment ──────▶ lms_user_mapping ────────────▶ LMS Enrollment
educlaw_assessment ─────────────▶ lms_assignment_mapping ──────▶ LMS Assignment
                                                   ◀────────────  LMS Grade Submission
                                  lms_grade_sync ─────────────▶ educlaw_assessment_result
                                  lms_sync_log (audit trail)
```

---

## 7. Actions to NOT Duplicate (Parent Already Has These)

The following parent actions already cover the underlying data — educlaw-lms should **read** from these via shared DB, not re-implement them:

| Parent Action | What NOT to Duplicate in LMS |
|---|---|
| `add-student` / `list-students` | Student management — read student records for sync |
| `add-section` / `list-sections` | Section management — read sections to sync with LMS |
| `create-section-enrollment` | Enrollment management — read roster for LMS push |
| `add-assessment` / `list-assessments` | Assessment creation — read for LMS assignment creation |
| `record-assessment-result` | Grade recording — LMS writes back TO this via `pull-grades` |
| `generate-transcript` | Transcript generation — out of scope for LMS |
| `send-notification` | Notification sending — parent handles; LMS sync can trigger via parent |

---

## 8. Naming Conventions to Follow

| Pattern | Example |
|---|---|
| Table prefix | `educlaw_lms_*` (keep educlaw_ prefix for namespace consistency) |
| Action names | kebab-case: `add-lms-connection`, `sync-courses`, `pull-grades` |
| Naming series | `LMS-NNNNN` for connections, `SYN-YYYY-NNNNN` for sync logs |
| All IDs | TEXT (UUID) |
| All monetary values | TEXT (Python Decimal) |
| All timestamps | TEXT (ISO 8601) |
| No `updated_at` on | Sync log entries, grade sync records (append-only / immutable) |

---

## 9. Status Lifecycles to Inherit

EduClaw uses these status patterns — educlaw-lms must align:

| Pattern | Example from Parent |
|---|---|
| Draft → Submit → Cancel | Assessment plans, grade submission |
| Active / Inactive | Course, instructor, fee structure |
| Custom multi-step | Academic term: setup→enrollment_open→active→grades_open→grades_finalized→closed |
| **New for LMS:** pending → syncing → synced → error → conflict | Sync log entry lifecycle |

---

## 10. Compliance Inheritance

educlaw-lms MUST inherit all parent compliance constraints:

| Inherited Requirement | Implementation Impact |
|---|---|
| **FERPA audit logging** | Any student data pushed to LMS must be logged in `educlaw_data_access_log` |
| **COPPA** | Under-13 students (`is_coppa_applicable=1`) — verify LMS vendor is COPPA-compliant before syncing |
| **Directory info opt-out** | Students with `directory_info_opt_out=1` — restrict LMS data sharing |
| **Data minimization** | Only sync data the LMS actually needs (roster, not full student record) |
| **Immutable grade audit** | When pulling grades from LMS → `educlaw_assessment_result`, follow parent's immutability rules |
| **Consent tracking** | LMS integration = third-party disclosure; must check/log `educlaw_consent_record` |

---

## 11. Technical Risks Inherited from Parent

| Risk | Mitigation |
|---|---|
| `ok()` status collision | Use domain-specific keys: `sync_status`, `lms_status` (not raw `status`) |
| `getattr` argparse bug | Use `getattr(args, "f", None) or "default"` pattern consistently |
| GPA precision | Not directly in LMS scope, but grade passback to `assessment_result` must use TEXT/Decimal |
| FERPA log completeness | Every `pull-grades` call that touches student records must log to `educlaw_data_access_log` |
| SQLite concurrency | Sync operations may be long-running; use explicit transactions for batch sync |

---

## 12. Recommended Integration Architecture

Since educlaw operates **fully offline/local** by design, the LMS integration introduces the first **external network calls**. This requires special handling:

```
Local (OpenClaw)                    External (LMS API)
────────────────                    ──────────────────
educlaw-lms actions                 Canvas REST API
    ↓                               Moodle Web Services API
HTTP client (requests)  ──────────▶ Google Classroom API
    ↓                               (OneRoster endpoints)
Response parsing
    ↓
Map external IDs → local IDs
    ↓
Write to local SQLite
    ↓
Log sync in educlaw_lms_sync_log
```

**Key design decision:** educlaw-lms should **pull-first** — always treat the SIS (parent) as the source of truth for student data, courses, and enrollments. The LMS is the source of truth only for:
1. Assignment submission status
2. Grade scores entered by teachers in the LMS gradebook
3. Discussion/engagement data (v2)

---

*Parent analysis based on: SKILL.md (educlaw), research/educlaw/data_model.md, research/educlaw/workflows.md, research/educlaw/competitors.md, research/educlaw/suggested_subverticals.md, educlaw/plan/ directory structure*
