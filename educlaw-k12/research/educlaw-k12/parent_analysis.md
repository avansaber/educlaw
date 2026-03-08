# Parent Analysis: EduClaw

> **Parent Product:** educlaw
> **Parent Path:** educlaw
> **Sub-vertical:** educlaw-k12 (K-12 Extensions)
> **Analysis Date:** 2026-03-05

---

## 1. Parent Product Overview

EduClaw is an AI-native Student Information System (SIS) built on ERPClaw. It provides the complete education lifecycle for both K-12 and higher-education institutions — from student applications through academics, grading, attendance, fee billing, and compliance.

**Version:** 1.0.0
**Tier:** 4
**Category:** Education
**Architecture:** Single OpenClaw skill package (single-package router pattern)
**Database:** SQLite (~/.openclaw/erpclaw/data.sqlite)
**Action Count:** 112 actions across 8 domain modules

---

## 2. Parent Schema: 32 Tables

### 2.1 Institutional Setup (3 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_academic_year` | Academic year calendar with start/end dates |
| `educlaw_academic_term` | Semesters/quarters with enrollment and grade deadlines |
| `educlaw_room` | Physical classrooms, labs, auditoriums |

### 2.2 Academic Catalog (4 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_program` | Degree/program catalog (supports `program_type = 'k12'`) |
| `educlaw_course` | Course catalog with `grade_level` field |
| `educlaw_program_requirement` | Required/elective courses per program |
| `educlaw_course_prerequisite` | Prerequisite enforcement |

### 2.3 Grading (2 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_grading_scale` | Letter grade scales (A/B/C) |
| `educlaw_grading_scale_entry` | Scale entries with min/max percentage and GPA points |

### 2.4 Staff (1 table)
| Table | Purpose |
|-------|---------|
| `educlaw_instructor` | Instructor extension of erpclaw-hr `employee` |

### 2.5 Students (4 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_student_applicant` | Application pipeline with status workflow |
| `educlaw_student` | Core student record (links to `customer` for billing) |
| `educlaw_guardian` | Parent/guardian contact information |
| `educlaw_student_guardian` | Student-guardian relationship (custody, pickup, comms) |

### 2.6 Enrollment (4 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_program_enrollment` | Student-to-program enrollment |
| `educlaw_section` | Course sections with schedule and instructor |
| `educlaw_course_enrollment` | Student-to-section enrollment with grade fields |
| `educlaw_waitlist_enrollment` | Waitlist with position and offer expiry |

### 2.7 Assessment & Grading (5 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_assessment_plan` | Weighted grading plan per section |
| `educlaw_assessment_category` | Category weights (homework 30%, tests 70%) |
| `educlaw_assessment` | Individual assignment/exam records |
| `educlaw_assessment_result` | Per-student grade for each assessment |
| `educlaw_grade_amendment` | Immutable grade change audit trail |

### 2.8 Attendance (1 table)
| Table | Purpose |
|-------|---------|
| `educlaw_student_attendance` | Daily + per-section attendance (nullable `section_id`) |

### 2.9 Fees & Billing (3 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_fee_category` | Fee type catalog (tuition, activity fees, etc.) |
| `educlaw_fee_structure` | Fee schedule per program/term |
| `educlaw_fee_structure_item` | Line items on a fee structure |
| `educlaw_scholarship` | Per-student discount records |

### 2.10 Communications (2 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_announcement` | School-wide or targeted announcements |
| `educlaw_notification` | Per-recipient system notifications |

### 2.11 FERPA Compliance (2 tables)
| Table | Purpose |
|-------|---------|
| `educlaw_data_access_log` | Automatic FERPA access logging |
| `educlaw_consent_record` | FERPA/COPPA consent management |

---

## 3. Parent Actions: 112 Actions Across 8 Domains

| Domain | Module | Action Count | Key Actions |
|--------|--------|-------------|-------------|
| students | scripts/students.py | ~21 | add-student, approve-applicant, assign-guardian, record-data-access |
| academics | scripts/academics.py | ~23 | add-academic-year, add-course, add-section, activate-section |
| enrollment | scripts/enrollment.py | ~10 | create-section-enrollment, cancel-enrollment, apply-waitlist |
| grading | scripts/grading.py | ~19 | add-assessment-plan, record-assessment-result, submit-grades, generate-transcript |
| attendance | scripts/attendance.py | ~8 | record-attendance, record-batch-attendance, get-truancy-report |
| staff | scripts/staff.py | ~5 | add-instructor, get-teaching-load |
| fees | scripts/fees.py | ~10+ | (fee structures, invoices, scholarships) |
| communications | scripts/communications.py | ~10+ | (announcements, notifications, progress reports) |

---

## 4. Key Design Patterns from Parent

### 4.1 Data Model Conventions
```
IDs:        TEXT PRIMARY KEY (UUID4)
Money/Qty:  TEXT NOT NULL DEFAULT '0' (Python Decimal)
Dates:      TEXT NOT NULL DEFAULT '' (ISO 8601 YYYY-MM-DD)
Timestamps: TEXT NOT NULL DEFAULT '' (ISO 8601)
Status:     TEXT NOT NULL DEFAULT 'X' CHECK(status IN (...))
Boolean:    INTEGER NOT NULL DEFAULT 0
JSON blobs: TEXT NOT NULL DEFAULT '[]' or '{}'
Nullable FKs: TEXT REFERENCES table(id) ON DELETE RESTRICT
```

### 4.2 Naming Conventions
- All tables prefixed with `educlaw_` (sub-vertical will use `educlaw_k12_`)
- All actions use kebab-case: `add-student`, `record-attendance`
- Status enum values use snake_case: `'under_review'`, `'grade_submitted'`
- Response keys avoid `"status"` field name collision — use domain-prefixed names

### 4.3 FERPA Integration
The parent already has `educlaw_data_access_log` with `data_category` covering:
```
'demographics','grades','attendance','financial','health','discipline','communications'
```
**K-12 extensions MUST call the parent's FERPA logging** when accessing health, discipline, or special education records. The `health` and `discipline` categories are already defined in the parent — sub-vertical just needs to log against them.

### 4.4 Student Record Already Has
- `grade_level` TEXT field (critical for K-12 promotion logic)
- `status` with `expelled` and `suspended` as valid values
- `academic_standing` with `probation` and `suspension`
- `is_coppa_applicable` and COPPA consent fields
- `emergency_contact` JSON field

### 4.5 Router Pattern
The sub-vertical must follow the same router pattern:
```python
ACTIONS = {}
ACTIONS.update(domain1.ACTIONS)
ACTIONS.update(domain2.ACTIONS)
```
The educlaw-k12 router should integrate with or extend the parent router.

---

## 5. What the Parent DOES NOT Provide

These are the gaps that educlaw-k12 must fill:

### 5.1 Discipline Management (MISSING)
- No incident recording tables
- No consequence/action tracking
- No parent notification for discipline events
- No referral-to-suspension workflow
- No PBIS/positive behavior tracking
- No state discipline reporting codes

### 5.2 Health Records (MISSING)
- No health profile (allergies, conditions, medications)
- No office visit / nurse visit log
- No medication administration tracking
- No immunization records or compliance tracking
- No emergency health information beyond generic `emergency_contact` JSON
- No sport/activity clearance

### 5.3 Special Education (MISSING)
- No referral-to-eligibility workflow
- No IEP document structure
- No goal tracking or progress monitoring
- No service delivery tracking (planned vs. actual minutes)
- No IEP team management
- No Section 504 accommodation plans
- No disability classification
- No transition planning records

### 5.4 Grade Promotion (MISSING)
- No end-of-year promotion review process
- No retention criteria evaluation
- No principal team decision records
- No parent notification for promotion/retention decisions
- No batch grade-level advancement action
- No intervention plan tracking for at-risk students

---

## 6. Reusable Parent Assets

The following parent assets are directly reusable by educlaw-k12:

| Asset | How K-12 Uses It |
|-------|-----------------|
| `educlaw_student.id` | FK target for all K-12 extension tables |
| `educlaw_student.grade_level` | Promotion/retention queries and health compliance |
| `educlaw_student.status` | Discipline may trigger `suspended` / `expelled` status updates |
| `educlaw_student.academic_standing` | Promotion review reads this |
| `educlaw_guardian` + `educlaw_student_guardian` | Discipline and health notifications use existing guardian contacts |
| `educlaw_data_access_log` | K-12 health/discipline/sped access must be FERPA-logged via parent |
| `educlaw_consent_record` | Parent consent for health treatment, IEP services |
| `educlaw_notification` | K-12 can create new notification_types for discipline and health |
| `educlaw_academic_year` + `educlaw_academic_term` | IEP annual review timing, promotion reviews |
| `educlaw_instructor` | IEP team member (teacher role) |
| `employee` (from erpclaw-hr) | IEP team members (counselor, school psychologist) |
| `company` (from erpclaw-setup) | All K-12 tables use company_id |

---

## 7. Extension Strategy

### 7.1 Table Naming
All new tables use prefix `educlaw_k12_` to avoid collision with parent tables.

### 7.2 FK Design
All FK references to parent tables use the fully qualified table name (e.g., `REFERENCES educlaw_student(id)`). No circular dependencies.

### 7.3 FERPA Logging
When any K-12 action reads health, discipline, or special education data, it must call `record-data-access` on the parent skill OR directly INSERT into `educlaw_data_access_log`. The K-12 scripts should import and invoke the parent's logging utility.

### 7.4 Notification Extension
New `notification_type` values needed for K-12:
- `discipline_incident` — parent notified of incident
- `health_alert` — allergy/medication alert for staff
- `immunization_overdue` — immunization compliance warning
- `iep_review_due` — IEP annual review approaching
- `promotion_decision` — grade promotion/retention decision

### 7.5 Action Namespace
All K-12 actions are namespaced to avoid collision:
- Discipline: `add-discipline-incident`, `add-discipline-action`, `notify-guardians-discipline`
- Health: `add-health-profile`, `add-office-visit`, `log-medication-admin`, `add-immunization`
- Special Ed: `create-sped-referral`, `add-iep`, `add-iep-goal`, `record-iep-progress`
- Promotion: `create-promotion-review`, `submit-promotion-decision`, `batch-promote-grade`

---

## 8. Recommended Sub-vertical Architecture

```
educlaw-k12/
├── SKILL.md
├── init_db.py              (~18-20 new tables)
├── scripts/
│   ├── db_query.py         (router — extends parent or standalone)
│   ├── discipline.py       (incident, action, notification)
│   ├── health_records.py   (health profile, visits, meds, immunizations)
│   ├── special_education.py (referral, IEP, 504, progress)
│   └── grade_promotion.py  (review, decision, batch promote)
└── tests/
```

**Estimated new tables:** 18–20
**Estimated new actions:** 55–70
**Complexity:** HIGH (special education is the most complex; IEP data model alone requires 8+ tables)
