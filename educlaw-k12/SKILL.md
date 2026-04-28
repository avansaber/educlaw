---
name: educlaw-k12
version: 1.0.0
description: EduClaw K-12 Extensions -- discipline management, student health records, special education (IDEA/IEP/504), and grade promotion workflows. 76 actions across 4 domains.
author: AvanSaber
homepage: https://github.com/avansaber/educlaw
source: https://github.com/avansaber/educlaw
tier: 4
category: education
requires: [erpclaw, educlaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [educlaw, k12, discipline, health-records, special-education, iep, idea, 504, grade-promotion]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# EduClaw K-12 Extensions

Sub-vertical of EduClaw SIS. Adds K-12 specific workflows: behavioral incident tracking with IDEA MDR compliance, student health records with FERPA-compliant access logging, the complete IDEA Part B pipeline (referral, IEP, services, progress), Section 504 plans, and end-of-year grade promotion with batch advancement.

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline**: No external API calls, no telemetry, no cloud dependencies
- **FERPA compliant**: Health, discipline, and special education data access is logged
- **IDEA compliance**: IEP goals and services are immutable; changes require new IEP version
- **Immutable records**: Office visits, medication logs, immunizations, and promotion decisions cannot be modified

## Quick Start

```bash
python3 scripts/db_query.py --action k12-add-discipline-incident \
  --incident-date 2025-10-15 --location classroom --incident-type bullying --severity moderate
python3 scripts/db_query.py --action k12-add-health-profile --student-id <id>
python3 scripts/db_query.py --action k12-create-sped-referral --student-id <id> --referral-source teacher
python3 scripts/db_query.py --action k12-create-promotion-review --student-id <id> --academic-year-id <id>
```

## Discipline (15 actions)

| Action | Description |
|--------|-------------|
| `k12-add-discipline-incident` | Create a new behavioral incident header |
| `k12-update-discipline-incident` | Update incident details |
| `k12-get-discipline-incident` | Get incident with students and actions (FERPA logged) |
| `k12-list-discipline-incidents` | List incidents with filters |
| `k12-complete-discipline-incident` | Close incident; set reviewer and timestamp |
| `k12-add-discipline-student` | Add student involvement (offender/victim/witness/bystander) |
| `k12-add-discipline-action` | Add consequence; auto-updates cumulative suspension days |
| `k12-add-discipline-notification` | Create guardian notification for involved students |
| `k12-get-discipline-history` | Full discipline history across all years |
| `k12-get-cumulative-suspension-days` | MDR threshold check for student |
| `k12-add-manifestation-review` | Create MDR for IDEA-eligible student |
| `k12-update-manifestation-review` | Update MDR determination and outcome |
| `k12-add-pbis-recognition` | Record positive behavioral recognition |
| `k12-generate-discipline-report` | School-wide discipline analytics |
| `k12-generate-discipline-state-report` | State-format ISS/OSS/expulsion report |

## Health Records (20 actions)

| Action | Description |
|--------|-------------|
| `k12-add-health-profile` | Create student health profile (one per student) |
| `k12-update-health-profile` | Update health profile fields |
| `k12-get-health-profile` | Get health profile (FERPA logged) |
| `k12-submit-health-profile-verification` | Nurse sign-off verification |
| `k12-get-emergency-health-info` | Quick emergency access: allergies, EpiPen, contacts |
| `k12-add-office-visit` | Record nurse visit (immutable) |
| `k12-get-office-visit` | Get visit details |
| `k12-list-office-visits` | List visits with filters |
| `k12-add-student-medication` | Add school-administered medication |
| `k12-update-student-medication` | Update medication status/supply |
| `k12-list-student-medications` | List student medications |
| `k12-record-medication-admin` | Log medication administration; decrements supply |
| `k12-list-medication-logs` | List medication administration logs |
| `k12-add-immunization` | Add immunization dose record (immutable) |
| `k12-get-immunization-compliance` | Check compliance against grade-level requirements |
| `k12-get-immunization-record` | All doses + waivers for student |
| `k12-add-immunization-waiver` | Add vaccination exemption |
| `k12-update-immunization-waiver` | Update waiver status |
| `k12-list-health-alerts` | School-wide: severe allergies, expiring waivers, low supply |
| `k12-generate-immunization-report` | Compliance by grade level; state report |

## Special Education (29 actions)

| Action | Description |
|--------|-------------|
| `k12-create-sped-referral` | Start IDEA referral (begins 60-day evaluation clock) |
| `k12-update-sped-referral` | Update referral status and consent dates |
| `k12-get-sped-referral` | Get referral with evaluations |
| `k12-list-sped-referrals` | List referrals with filters |
| `k12-add-sped-evaluation` | Add evaluation (psychological, academic, etc.) |
| `k12-list-sped-evaluations` | List evaluations for referral |
| `k12-record-sped-eligibility` | Record eligibility determination |
| `k12-get-sped-eligibility` | Get eligibility details |
| `k12-add-iep` | Create IEP in draft status |
| `k12-update-iep` | Update draft IEP fields |
| `k12-get-iep` | Get IEP with goals, services, team |
| `k12-activate-iep` | Activate IEP with parent consent; prior IEP superseded |
| `k12-add-iep-amendment` | Create amendment to active IEP |
| `k12-get-active-iep` | Get student's active IEP |
| `k12-list-iep-deadlines` | List upcoming IEP deadlines |
| `k12-list-reevaluation-due` | List students due for reevaluation |
| `k12-add-iep-goal` | Add measurable annual goal (immutable) |
| `k12-list-iep-goals` | List goals for IEP |
| `k12-record-iep-progress` | Record progress on a goal |
| `k12-add-iep-service` | Add mandated service to IEP (immutable) |
| `k12-list-iep-services` | List services for IEP |
| `k12-record-iep-service-session` | Log service delivery session |
| `k12-list-iep-service-logs` | List service delivery logs |
| `k12-add-iep-team-member` | Add team member to IEP |
| `k12-generate-iep-progress-report` | Parent-facing progress report |
| `k12-get-service-compliance-report` | Planned vs actual service minutes |
| `k12-add-504-plan` | Create Section 504 plan |
| `k12-update-504-plan` | Update 504 plan status/accommodations |
| `k12-get-active-504-plan` | Get active 504 plan (FERPA logged) |

## Grade Promotion (12 actions)

| Action | Description |
|--------|-------------|
| `k12-create-promotion-review` | Create end-of-year review |
| `k12-update-promotion-review` | Update review recommendations |
| `k12-list-promotion-reviews` | List reviews with filters |
| `k12-submit-promotion-decision` | Record final immutable decision |
| `k12-get-promotion-decision` | Get promotion decision |
| `k12-add-promotion-notification` | Create guardian notification |
| `k12-list-at-risk-students` | Flag students below GPA/attendance thresholds |
| `k12-apply-grade-promotion` | Advance promoted students; graduate 12th graders |
| `k12-create-intervention-plan` | Create intervention plan for at-risk student |
| `k12-update-intervention-plan` | Update intervention plan |
| `k12-list-intervention-plans` | List intervention plans |
| `k12-generate-promotion-report` | Summary by grade: promote/retain/conditional |

## Key Workflows

1. **Discipline:** `k12-add-discipline-incident` -> `k12-add-discipline-student` -> `k12-add-discipline-action` -> `k12-add-discipline-notification` -> `k12-complete-discipline-incident` -> (if IDEA) `k12-add-manifestation-review`
2. **Health Enrollment:** `k12-add-health-profile` -> `k12-add-immunization` -> `k12-get-immunization-compliance` -> `k12-add-student-medication` -> `k12-submit-health-profile-verification`
3. **IDEA Pipeline:** `k12-create-sped-referral` -> `k12-add-sped-evaluation` -> `k12-record-sped-eligibility` -> `k12-add-iep` -> `k12-add-iep-goal` -> `k12-add-iep-service` -> `k12-add-iep-team-member` -> `k12-activate-iep`
4. **Promotion:** `k12-list-at-risk-students` -> `k12-create-promotion-review` -> `k12-create-intervention-plan` -> `k12-update-promotion-review` -> `k12-submit-promotion-decision` -> `k12-apply-grade-promotion`

## Business Invariants

- Closed incidents cannot be re-opened. MDR required for IDEA-eligible students with 10+ suspension days.
- One health profile per student. Visits, medication logs, and immunizations are immutable.
- At most one active IEP per student. IEP goals and services are immutable. Evaluation deadline = consent + 60 days.
- One promotion review per student per year. Decisions are immutable. Grade promotion is idempotent.

## Database

23 tables: discipline (4), health_records (6), special_education (10), grade_promotion (3). Run `python3 init_db.py` to create.
