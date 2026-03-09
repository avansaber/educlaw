---
name: educlaw-highered
display_name: EduClaw Higher Education
version: 1.0.0
description: >
  Higher education administration: registrar (degree programs, courses, sections,
  enrollments), student records (transcripts, GPA, degree audit, holds), financial
  aid (packages, disbursements, SAP), alumni relations (giving, events), and
  faculty management (assignments, research grants).
author: ERPForge
source: https://github.com/avansaber/educlaw
parent: educlaw
scripts:
  - scripts/db_query.py
domains:
  - registrar
  - records
  - finaid
  - alumni
  - faculty
  - admissions
  - reports
total_actions: 60
tables:
  - highered_degree_program
  - highered_course
  - highered_section
  - highered_enrollment
  - highered_student_record
  - highered_hold
  - highered_aid_package
  - highered_disbursement
  - highered_alumnus
  - highered_alumni_event
  - highered_giving_record
  - highered_faculty
  - highered_course_assignment
  - highered_research_grant
  - highered_transcript
  - highered_academic_standing
  - highered_application
  - highered_admission_decision
---

# EduClaw Higher Education

Higher education administration covering registrar operations, student records,
financial aid, alumni relations, and faculty management.

## Security Model

- Zero network calls. All data stored locally in SQLite.
- No PII leaves the device. Student records, grades, and financial data stay local.
- All money fields stored as TEXT (Python Decimal). No floating-point errors.

## Tier 1 — Essential Operations

### Registrar
- `highered-add-degree-program` — Create a new degree program (associate through doctoral)
- `highered-list-degree-programs` — List programs with optional filters
- `highered-add-course` — Create a course with credits, prerequisites
- `highered-update-course` — Update course details
- `highered-list-courses` — List courses by department or status
- `highered-add-section` — Create a course section for a term
- `highered-list-sections` — List sections with filters
- `highered-add-enrollment` — Enroll a student in a section
- `highered-drop-enrollment` — Drop a student from a section
- `highered-list-enrollments` — List enrollments by student or section

### Student Records
- `highered-get-student-record` — View full student record
- `highered-list-student-records` — Search student records
- `highered-generate-transcript` — Generate academic transcript
- `highered-calculate-gpa` — Recalculate student GPA from enrollment grades

## Tier 2 — Intermediate Operations

### Registrar
- `highered-update-degree-program` — Update program details
- `highered-academic-calendar-report` — Sections by term summary

### Student Records
- `highered-degree-audit` — Check program completion progress
- `highered-update-academic-standing` — Update standing (good/probation/suspension/etc.)
- `highered-add-hold` — Place a hold on student record
- `highered-remove-hold` — Remove a hold
- `highered-list-holds` — List active holds
- `highered-academic-standing-report` — Standing distribution report

### Financial Aid
- `highered-add-aid-package` — Create financial aid package
- `highered-update-aid-package` — Update package amounts
- `highered-get-aid-package` — View package details
- `highered-list-aid-packages` — List packages by student or year
- `highered-add-disbursement` — Record a disbursement
- `highered-list-disbursements` — List disbursements

## Tier 3 — Advanced Operations

### Financial Aid
- `highered-calculate-sap` — Calculate Satisfactory Academic Progress
- `highered-aid-summary-report` — Aid distribution summary
- `highered-need-analysis` — Calculate financial need
- `highered-award-letter-report` — Generate award letter data

### Alumni
- `highered-add-alumnus` — Register an alumnus
- `highered-update-alumnus` — Update alumnus record
- `highered-list-alumni` — Search alumni
- `highered-add-alumni-event` — Create an alumni event
- `highered-list-alumni-events` — List events
- `highered-add-giving-record` — Record alumni donation
- `highered-alumni-giving-report` — Giving totals and trends
- `highered-alumni-engagement-report` — Engagement level summary

### Admissions
- `highered-add-application` — Submit a new application
- `highered-list-applications` — List applications with filters
- `highered-get-application` — View application with decisions
- `highered-add-admission-decision` — Record admission decision
- `highered-update-admission-decision` — Update a decision
- `highered-list-admission-decisions` — List decisions

### Faculty
- `highered-add-faculty` — Add a faculty member
- `highered-update-faculty` — Update faculty record
- `highered-list-faculty` — Search faculty
- `highered-add-course-assignment` — Assign faculty to section
- `highered-list-course-assignments` — List assignments
- `highered-add-research-grant` — Record a research grant
- `highered-list-research-grants` — List grants
- `highered-faculty-workload-report` — Teaching load summary

### Reports
- `highered-enrollment-report` — Enrollment statistics
- `highered-retention-report` — Retention/attrition analysis
- `highered-degree-completion-report` — Graduation statistics
- `highered-alumni-giving-summary` — Giving overview
- `highered-faculty-workload-summary` — Cross-department workload
- `status` — Skill health check
