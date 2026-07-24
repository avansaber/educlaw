---
name: educlaw
version: 1.2.0
description: AI-native education management for K-12/colleges/universities. 175 actions across 15 domains -- students, academics, enrollment, grading, attendance, fees, communications, staff, portal, cafeteria, transport, professional development, activities, library, housing. FERPA/COPPA compliant.
author: AvanSaber
homepage: https://github.com/avansaber/educlaw
source: https://github.com/avansaber/educlaw
tier: 4
category: education
requires: [erpclaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [educlaw, education, school, university, students, enrollment, grades, attendance, tuition, fees, ferpa, coppa, lms, sis, cafeteria, transport, library, housing, activities]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# educlaw

Education Administrator for EduClaw -- AI-native Student Information System on ERPClaw.
Manages student applications, enrollment, courses, sections, grading, attendance, instructors,
tuition/fees, parent portal, cafeteria/meal programs, transportation, professional development,
extracurricular activities, library, and student housing. FERPA access auto-logged.
COPPA auto-enforced for students under 13. All fees post to ERPClaw GL.

### Skill Activation Triggers

Activate when user mentions: student, enrollment, course, grade, GPA, transcript, attendance,
tuition, fee, instructor, teacher, classroom, section, program, academic year, semester, FERPA,
guardian, school, university, college, report card, cafeteria, meal plan, bus, transport,
library, housing, dormitory, activities, clubs, professional development.

### Setup
```
python3 {baseDir}/../erpclaw/scripts/erpclaw-setup/db_query.py --action initialize-database
python3 {baseDir}/scripts/db_query.py --action status
```

## Quick Start

```
--action edu-add-academic-year --company-id {id} --name "2025-2026" --start-date 2025-08-01 --end-date 2026-05-31
--action edu-add-student-applicant --company-id {id} --first-name "Jane" --last-name "Doe" --date-of-birth 2010-03-15 --grade-level 9
--action edu-approve-applicant --applicant-id {id} --applicant-status accepted --reviewed-by {user_id}
--action edu-convert-applicant-to-student --applicant-id {id} --company-id {id}
--action edu-create-section-enrollment --student-id {id} --section-id {id} --company-id {id}
--action edu-record-attendance --student-id {id} --attendance-date 2025-09-01 --attendance-status present --company-id {id}
--action edu-generate-transcript --student-id {id}
```

## All 176 Actions

### Students (21 actions)
| Action | Description |
|--------|-------------|
| `edu-add-student-applicant` | Create applicant in draft status |
| `edu-update-student-applicant` | Update applicant record |
| `edu-approve-applicant` | Accept, reject, or waitlist applicant |
| `edu-convert-applicant-to-student` | Convert accepted applicant to student |
| `edu-add-student` | Create student directly |
| `edu-update-student` | Update student record |
| `edu-get-student` | Get student (auto-logs FERPA access) |
| `edu-list-students` | List/filter students |
| `edu-update-student-status` | Change status (active/suspended/withdrawn) |
| `edu-complete-graduation` | Mark student as graduated |
| `edu-get-applicant` | Get applicant details |
| `edu-list-applicants` | List applicants |
| `edu-list-pending-applications` | List pending applications |
| `edu-add-guardian` | Add parent/guardian |
| `edu-update-guardian` | Update guardian |
| `edu-get-guardian` | Get guardian details |
| `edu-list-guardians` | List guardians |
| `edu-assign-guardian` | Link guardian to student |
| `edu-record-data-access` | Manual FERPA access log |
| `edu-add-consent-record` | Add FERPA consent |
| `edu-cancel-consent` | Revoke consent record |

### Academics (28 actions)
| Action | Description |
|--------|-------------|
| `edu-add-academic-year` | Create academic year |
| `edu-update-academic-year` | Update academic year |
| `edu-get-academic-year` | Get academic year |
| `edu-list-academic-years` | List academic years |
| `edu-add-academic-term` | Create semester/quarter/trimester |
| `edu-update-academic-term` | Update term |
| `edu-get-academic-term` | Get term details |
| `edu-list-academic-terms` | List terms |
| `edu-add-room` | Add classroom/lab |
| `edu-update-room` | Update room |
| `edu-list-rooms` | List rooms |
| `edu-add-program` | Create degree/program |
| `edu-update-program` | Update program |
| `edu-get-program` | Get program with requirements |
| `edu-list-programs` | List programs |
| `edu-add-program-requirement` | Add required/elective course to program |
| `edu-list-program-requirements` | List a program's course requirements |
| `edu-add-course` | Create course |
| `edu-update-course` | Update course |
| `edu-get-course` | Get course with prerequisites |
| `edu-list-courses` | List courses |
| `edu-add-section` | Create course section |
| `edu-update-section` | Update section |
| `edu-get-section` | Get section with roster |
| `edu-list-sections` | List sections |
| `edu-activate-section` | Open section for enrollment |
| `edu-cancel-section` | Cancel section; drop enrolled |
| `edu-generate-student-record` | Export all education records (FERPA) |

### Enrollment (10 actions)
| Action | Description |
|--------|-------------|
| `edu-create-program-enrollment` | Enroll in degree program |
| `edu-cancel-program-enrollment` | Withdraw from program |
| `edu-list-program-enrollments` | List program enrollments |
| `edu-create-section-enrollment` | Enroll in course section |
| `edu-cancel-enrollment` | Drop course (W grade) |
| `edu-terminate-enrollment` | Withdraw (no grade) |
| `edu-get-enrollment` | Get enrollment details |
| `edu-list-enrollments` | List enrollments |
| `edu-apply-waitlist` | Advance waitlist when seat opens |
| `edu-list-waitlist` | List waitlisted students |

### Grading (19 actions)
| Action | Description |
|--------|-------------|
| `edu-add-grading-scale` | Create grading scale |
| `edu-update-grading-scale` | Update grading scale |
| `edu-get-grading-scale` | Get scale with entries |
| `edu-list-grading-scales` | List grading scales |
| `edu-add-assessment-plan` | Create weighted assessment plan |
| `edu-update-assessment-plan` | Update plan |
| `edu-get-assessment-plan` | Get plan with categories |
| `edu-add-assessment` | Add assessment |
| `edu-update-assessment` | Update assessment |
| `edu-list-assessments` | List assessments |
| `edu-record-assessment-result` | Record grade for student |
| `edu-record-batch-results` | Bulk grade entry |
| `edu-generate-section-grade` | Calculate weighted grade |
| `edu-submit-grades` | Submit final grades (immutable) |
| `edu-update-grade` | Amend submitted grade |
| `edu-generate-gpa` | Recalculate cumulative GPA |
| `edu-generate-transcript` | Full academic transcript |
| `edu-generate-report-card` | Term report card |
| `edu-list-grades` | List enrollment grades |

### Attendance (8 actions)
| Action | Description |
|--------|-------------|
| `edu-record-attendance` | Mark single student attendance |
| `edu-record-batch-attendance` | Bulk attendance |
| `edu-update-attendance` | Correct attendance record |
| `edu-get-attendance` | Get attendance record |
| `edu-list-attendance` | List attendance records |
| `edu-get-attendance-summary` | Attendance % by student |
| `edu-get-section-attendance` | Section attendance for date |
| `edu-get-truancy-report` | Students below threshold |

### Staff (5 actions)
| Action | Description |
|--------|-------------|
| `edu-add-instructor` | Register employee as instructor |
| `edu-update-instructor` | Update instructor profile |
| `edu-get-instructor` | Get instructor with sections |
| `edu-list-instructors` | List instructors |
| `edu-get-teaching-load` | Teaching load vs max hours |

### Fees (15 actions)
| Action | Description |
|--------|-------------|
| `edu-add-fee-category` | Create fee category |
| `edu-update-fee-category` | Update fee category |
| `edu-list-fee-categories` | List fee categories |
| `edu-add-fee-structure` | Create fee structure |
| `edu-update-fee-structure` | Update fee structure |
| `edu-get-fee-structure` | Get fee structure |
| `edu-list-fee-structures` | List fee structures |
| `edu-add-scholarship` | Award scholarship/discount |
| `edu-update-scholarship` | Update scholarship |
| `edu-list-scholarships` | List scholarships |
| `edu-generate-fee-invoice` | Generate tuition invoice |
| `edu-list-fee-invoices` | List fee invoices |
| `edu-get-student-account` | Account summary with balance |
| `edu-get-outstanding-fees` | Students with overdue invoices |
| `edu-apply-late-fee` | Apply late fee charge |

### Communications (8 actions)
| Action | Description |
|--------|-------------|
| `edu-add-announcement` | Create announcement (draft) |
| `edu-update-announcement` | Update draft announcement |
| `edu-get-announcement` | Get announcement |
| `edu-list-announcements` | List announcements |
| `edu-submit-announcement` | Publish + notify audience |
| `edu-submit-notification` | Send targeted notification |
| `edu-list-notifications` | List notifications |
| `edu-submit-emergency-alert` | Broadcast emergency alert |

### Portal (16 actions)
| Action | Description |
|--------|-------------|
| `edu-portal-student-grades` | Student views grades |
| `edu-portal-student-attendance` | Student views attendance |
| `edu-portal-student-schedule` | Student views schedule |
| `edu-portal-student-fees` | Student views fees |
| `edu-portal-student-assignments` | Student views assignments |
| `edu-portal-student-discipline` | Student views discipline |
| `edu-portal-my-students` | Guardian views their students |
| `edu-portal-my-transport` | View transport assignment |
| `edu-portal-pay-fee` | Pay fee online |
| `edu-portal-submit-application` | Submit online application |
| `edu-portal-check-application-status` | Check application status |
| `edu-portal-submit-absence-excuse` | Submit absence excuse |
| `edu-portal-update-contact-info` | Update contact information |
| `edu-portal-upload-document` | Upload document |
| `edu-portal-announcements` | View announcements |
| `edu-portal-acknowledge-announcement` | Acknowledge announcement |

### Cafeteria (8 actions)
| Action | Description |
|--------|-------------|
| `edu-record-student-meal` | Record student meal |
| `edu-list-meal-records` | List meal records |
| `edu-update-student-meal-eligibility` | Update meal eligibility (FRPL) |
| `edu-record-daily-meal-count` | Record daily meal count |
| `edu-meal-participation-report` | Meal participation report |
| `edu-usda-claim-report` | USDA reimbursement claim |
| `edu-allergen-alert-list` | Student allergen alerts |
| `edu-generate-progress-report` | Generate progress report |

### Transport (7 actions)
| Action | Description |
|--------|-------------|
| `edu-add-bus-route` | Create bus route |
| `edu-update-bus-route` | Update bus route |
| `edu-list-bus-routes` | List bus routes |
| `edu-add-bus-stop` | Add stop to route |
| `edu-assign-student-transport` | Assign student to route |
| `edu-list-student-transport` | List student transport |
| `edu-bus-roster` | Bus roster report |

### Professional Development (5 actions)
| Action | Description |
|--------|-------------|
| `edu-add-pd-credit` | Record PD credit |
| `edu-list-pd-credits` | List PD credits |
| `edu-get-pd-summary` | PD summary by instructor |
| `edu-check-pd-compliance` | Check PD compliance |
| `edu-pd-transcript` | PD transcript |

### Activities (7 actions)
| Action | Description |
|--------|-------------|
| `edu-add-activity` | Create extracurricular activity |
| `edu-list-activities` | List activities |
| `edu-enroll-student-activity` | Enroll student in activity |
| `edu-remove-student-activity` | Remove from activity |
| `edu-list-activity-roster` | Activity roster |
| `edu-check-activity-eligibility` | Check eligibility |
| `edu-activity-participation-report` | Participation report |

### Library (7 actions)
| Action | Description |
|--------|-------------|
| `edu-add-library-item` | Add library item |
| `edu-list-library-items` | List library items |
| `edu-checkout-item` | Check out item |
| `edu-return-item` | Return item |
| `edu-renew-item` | Renew checkout |
| `edu-list-overdue` | List overdue items |
| `edu-student-reading-history` | Student reading history |

### Housing (7 actions)
| Action | Description |
|--------|-------------|
| `edu-add-housing-unit` | Add housing unit |
| `edu-list-housing-units` | List housing units |
| `edu-assign-housing` | Assign student housing |
| `edu-release-housing` | Release housing |
| `edu-list-housing-assignments` | List assignments |
| `edu-housing-availability` | Check availability |
| `edu-housing-occupancy-report` | Occupancy report |

### Additional (6 actions)
| Action | Description |
|--------|-------------|
| `edu-transport-report` | Transport summary report |
| `edu-library-inventory-report` | Library inventory report |
| `edu-housing-waitlist` | Housing waitlist |
| `edu-add-payment-method` | Add payment method |
| `edu-list-payment-methods` | List payment methods |
| `edu-payment-receipt` | Generate payment receipt |

## Technical Details (Tier 3)
**Tables:** All use `educlaw_` prefix. **Script:** `scripts/db_query.py` routes to 15 modules. **Data:** Money=TEXT(Decimal), IDs=TEXT(UUID4). FERPA auto-logged. COPPA auto-enforced.
