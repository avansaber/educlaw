---
name: educlaw-k12
version: 1.0.0
description: EduClaw K-12 Extensions — discipline management, student health records, special education (IDEA/IEP/504), and grade promotion workflows.
author: ERPForge
source: https://github.com/avansaber/educlaw
parent: educlaw
scripts:
  - scripts/db_query.py
domains:
  - discipline
  - health_records
  - special_education
  - grade_promotion
total_actions: 76
tables: 23
---

# EduClaw K-12 Extensions

Sub-vertical of EduClaw SIS. Adds K-12 specific workflows: behavioral incident tracking with IDEA MDR compliance, student health records with FERPA-compliant access logging, the complete IDEA Part B pipeline (referral → IEP → services → progress), Section 504 plans, and end-of-year grade promotion with batch advancement.

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline**: No external API calls, no telemetry, no cloud dependencies
- **No credentials required**: Uses erpclaw_lib shared library (installed by erpclaw-setup)
- **SQL injection safe**: All queries use parameterized statements
- **FERPA compliant**: Health records, discipline records, and special education data access is logged
- **IDEA compliance**: IEP goals and services are immutable; changes require new IEP version
- **Immutable records**: Office visits, medication logs, immunizations, and promotion decisions cannot be modified after creation

## Quick Start

```bash
# Create a discipline incident
python3 scripts/db_query.py --action k12-add-discipline-incident \
  --incident-date 2025-10-15 --incident-time 10:30 \
  --location classroom --incident-type bullying \
  --severity moderate --academic-year-id <year-id>

# Add a student health profile
python3 scripts/db_query.py --action k12-add-health-profile \
  --student-id <id> --allergies '[{"allergen":"peanuts","severity":"severe","epipen_location":"nurse office"}]'

# Create a SpEd referral
python3 scripts/db_query.py --action k12-create-sped-referral \
  --student-id <id> --referral-source teacher \
  --referral-reason "Student struggling with reading fluency" \
  --referral-date 2025-09-10

# Start end-of-year promotion review
python3 scripts/db_query.py --action k12-create-promotion-review \
  --student-id <id> --academic-year-id <year-id>
```

---

## Tier 1: Most Used Actions

### Discipline

| Action | Description |
|--------|-------------|
| `k12-add-discipline-incident` | Create a new behavioral incident header |
| `k12-add-discipline-student` | Add student involvement (offender/victim/witness/bystander) |
| `k12-add-discipline-action` | Add consequence; auto-updates cumulative suspension days |
| `k12-get-discipline-incident` | Get incident with all students and actions (FERPA logged) |
| `close-discipline-incident` | Close incident; set reviewer and timestamp |
| `notify-guardians-discipline` | Create guardian notifications for involved students |

### Health Records

| Action | Description |
|--------|-------------|
| `k12-add-health-profile` | Create student health profile (one per student) |
| `k12-get-health-profile` | Get student health profile (FERPA logged) |
| `k12-get-emergency-health-info` | Quick emergency access: allergies, EpiPen, contacts |
| `k12-add-office-visit` | Record nurse visit (immutable) |
| `log-medication-admin` | Log medication administration; decrements supply |
| `k12-add-immunization` | Add immunization dose record (immutable) |
| `check-immunization-compliance` | Check compliance against grade-level requirements |

### Special Education

| Action | Description |
|--------|-------------|
| `k12-create-sped-referral` | Start IDEA referral (begins 60-day evaluation clock) |
| `k12-add-iep` | Create IEP in draft status |
| `k12-activate-iep` | Activate IEP with parent consent; prior IEP → superseded |
| `k12-add-iep-goal` | Add measurable annual goal (immutable) |
| `k12-add-iep-service` | Add mandated service to IEP (immutable) |
| `log-iep-service-session` | Log service delivery; increments total_minutes_delivered |
| `k12-get-active-iep` | Get student's active IEP with goals, services, team |
| `k12-get-active-504-plan` | Get active Section 504 plan (FERPA logged) |

### Grade Promotion

| Action | Description |
|--------|-------------|
| `k12-create-promotion-review` | Create end-of-year review; auto-populates discipline count |
| `k12-submit-promotion-decision` | Record final immutable decision (promote/retain/conditional) |
| `batch-promote-grade` | Advance all promoted students; graduates 12th graders |
| `identify-at-risk-students` | Flag students below GPA/attendance thresholds |

---

## Tier 2: Supporting Actions

### Discipline

| Action | Key Args |
|--------|----------|
| `k12-update-discipline-incident` | `--incident-id`, updatable fields |
| `k12-list-discipline-incidents` | `--academic-year-id`, `--severity`, `--incident-status`, `--student-id` |
| `k12-get-discipline-history` | `--student-id` — full history across all years |
| `k12-get-cumulative-suspension-days` | `--student-id`, `--academic-year-id` — MDR threshold check |
| `k12-add-manifestation-review` | `--discipline-student-id`, `--iep-id`, `--mdr-date` |
| `k12-update-manifestation-review` | `--mdr-id`, `--determination`, `--outcome-action` |
| `k12-add-pbis-recognition` | `--student-id`, `--incident-date`, `--description` |

### Health Records

| Action | Key Args |
|--------|----------|
| `k12-update-health-profile` | `--student-id`, updatable fields |
| `verify-health-profile` | `--student-id`, `--last-verified-by` |
| `k12-list-office-visits` | `--student-id`, `--date-from`, `--date-to`, `--disposition` |
| `k12-get-office-visit` | `--visit-id` |
| `k12-add-student-medication` | `--student-id`, `--medication-name`, `--route`, `--frequency` |
| `k12-update-student-medication` | `--medication-id`, `--medication-status`, `--supply-count` |
| `k12-list-student-medications` | `--student-id`, `--medication-status` |
| `k12-list-medication-logs` | `--student-id` or `--student-medication-id` |
| `k12-add-immunization-waiver` | `--student-id`, `--vaccine-name`, `--waiver-type` |
| `k12-update-immunization-waiver` | `--waiver-id`, `--waiver-status` |
| `k12-get-immunization-record` | `--student-id` — all doses + waivers |
| `k12-list-health-alerts` | School-wide: severe allergies, expiring waivers, low supply |

### Special Education

| Action | Key Args |
|--------|----------|
| `k12-update-sped-referral` | `--referral-id`, `--referral-status`, `--consent-received-date` |
| `k12-get-sped-referral` | `--referral-id` — includes evaluations |
| `k12-list-sped-referrals` | `--referral-status`, `--approaching-deadline` |
| `k12-add-sped-evaluation` | `--referral-id`, `--evaluation-type`, `--evaluation-date` |
| `k12-list-sped-evaluations` | `--referral-id` |
| `k12-record-sped-eligibility` | `--referral-id`, `--is-eligible`, `--primary-disability` |
| `k12-get-sped-eligibility` | `--student-id` or `--eligibility-id` |
| `k12-update-iep` | `--iep-id`, draft fields only |
| `amend-iep` | `--iep-id` (prior active IEP) — creates amendment |
| `k12-get-iep` | `--iep-id` — includes goals, services, team |
| `k12-list-iep-deadlines` | `--days-window` (default: 30) |
| `k12-list-reevaluation-due` | `--days-window` (default: 90) |
| `k12-list-iep-goals` | `--iep-id` |
| `k12-list-iep-services` | `--iep-id` |
| `k12-list-iep-service-logs` | `--iep-service-id` |
| `k12-add-iep-team-member` | `--iep-id`, `--member-type`, `--member-name` |
| `k12-record-iep-progress` | `--iep-goal-id`, `--progress-rating`, `--reporting-period` |
| `k12-add-504-plan` | `--student-id`, `--meeting-date`, `--accommodations` (JSON) |
| `k12-update-504-plan` | `--plan-504-id`, `--plan-status`, `--accommodations` |

### Grade Promotion

| Action | Key Args |
|--------|----------|
| `k12-update-promotion-review` | `--review-id`, `--teacher-recommendation`, `--counselor-recommendation` |
| `k12-list-promotion-reviews` | `--academic-year-id`, `--grade-level`, `--review-status` |
| `k12-get-promotion-decision` | `--decision-id` or `--student-id` + `--academic-year-id` |
| `notify-promotion-decision` | `--decision-id` — creates guardian notifications |
| `k12-create-intervention-plan` | `--student-id`, `--trigger`, `--intervention-types` |
| `k12-update-intervention-plan` | `--intervention-plan-id`, `--plan-status`, `--outcome-notes` |
| `k12-list-intervention-plans` | `--academic-year-id`, `--plan-status`, `--student-id` |

---

## Tier 3: Reports and Advanced Workflows

| Action | Description |
|--------|-------------|
| `k12-generate-discipline-report` | School-wide analytics: by type, severity, location, PBIS ratio |
| `k12-generate-discipline-state-report` | State-format: ISS/OSS/expulsion by grade/disability; MDR count |
| `k12-generate-immunization-report` | Compliance by grade level; state Annual Immunization Status Report |
| `k12-get-service-compliance-report` | Planned vs. actual IEP service minutes; gap detection |
| `k12-generate-iep-progress-report` | Parent-facing: all goals with progress ratings and notes |
| `k12-generate-promotion-report` | Summary by grade: promote/retain/conditional; intervention coverage |

---

## Key Workflows

### 1. Discipline Incident → MDR (IDEA Students)

```
add-discipline-incident (header)
→ add-discipline-student (role + is-idea-eligible)
→ add-discipline-action (suspension → auto-calculates cumulative days)
  └─ If IDEA-eligible + ≥10 days: mdr_alert in response
→ notify-guardians-discipline
→ close-discipline-incident
→ [If MDR needed] add-manifestation-review → update-manifestation-review
```

### 2. Health Records Enrollment

```
add-health-profile (allergies, conditions, physician)
→ add-immunization (one per dose per vaccine)
→ check-immunization-compliance (returns missing vaccines)
→ add-immunization-waiver (if exemption)
→ add-student-medication (for each school-administered medication)
→ verify-health-profile (nurse sign-off → status: active)
```

### 3. IDEA Full Pipeline

```
create-sped-referral
→ update-sped-referral (consent_request_date → consent_pending)
→ update-sped-referral (consent_received_date → auto-calc 60-day deadline)
→ add-sped-evaluation (psychological, academic, speech, OT, etc.)
→ record-sped-eligibility (is_eligible=1 → auto-calc IEP deadline +30 days)
→ add-iep (draft)
→ add-iep-goal (one per area)
→ add-iep-service (one per mandated service)
→ add-iep-team-member (parent, teachers, admin, specialists)
→ activate-iep (parent consent → prior IEP superseded)
→ [Ongoing] log-iep-service-session (each delivery session)
→ [Each period] record-iep-progress (per goal)
→ [Annual] list-iep-deadlines → add-iep (new version) → activate-iep
```

### 4. Grade Promotion End-of-Year

```
identify-at-risk-students (configurable GPA/attendance thresholds)
→ create-promotion-review (auto-populates discipline count from DB)
→ create-intervention-plan (for at-risk students)
→ update-promotion-review (teacher recommendation + rationale)
→ update-promotion-review (counselor recommendation + notes)
→ submit-promotion-decision (final immutable decision)
→ notify-promotion-decision (creates guardian notifications)
→ batch-promote-grade (idempotent; advances grade; graduates 12th)
→ generate-promotion-report (summary for administration)
```

---

## FERPA / Privacy Notes

- **Health records** (`k12-get-health-profile`, `k12-list-office-visits`, `k12-get-office-visit`, `k12-get-immunization-record`, `k12-get-emergency-health-info`) are logged to `educlaw_data_access_log` with `data_category='health'`.
- **Discipline reads** (`k12-get-discipline-incident`, `k12-get-discipline-history`) are logged with `data_category='discipline'`.
- **Special education reads** (`k12-get-sped-referral`, `k12-get-active-iep`, `k12-get-iep`, `k12-record-sped-eligibility`, `k12-get-active-504-plan`, `k12-generate-iep-progress-report`) are logged with `data_category='special_education'`.
- Emergency health access uses `is_emergency_access=1` in the FERPA log.

The `special_education` data category is used for FERPA access logging of IEP and 504 plan records.

---

## Business Invariants

| Domain | Invariant |
|--------|-----------|
| Discipline | Closed incidents cannot be re-opened |
| Discipline | `cumulative_suspension_days_ytd` = sum of ISS+OSS for student in academic year |
| Discipline | MDR required before expulsion for IDEA-eligible students (≥10 days) |
| Health | One health profile per student (`UNIQUE(student_id)`) |
| Health | Visits, medication logs, and immunizations are immutable |
| Health | Medical waivers require `--issuing-physician` |
| SpEd | At most one `iep_status='active'` IEP per student at a time |
| SpEd | IEP goals and services are immutable; changes require new IEP version |
| SpEd | `evaluation_deadline = consent_received_date + 60 days` |
| SpEd | `iep_deadline = eligibility_meeting_date + 30 days` |
| SpEd | `transition_plan_required=1` for students ≥16 at IEP start date |
| Promotion | One review per student per academic year |
| Promotion | `k12-submit-promotion-decision` creates immutable record |
| Promotion | `batch-promote-grade` is idempotent |

---

## Database

All tables use the shared SQLite database at `~/.openclaw/erpclaw/data.sqlite`.

Run `python3 init_db.py` to create the 23 K-12 tables (requires erpclaw-setup and educlaw parent tables to exist first).

### New Tables (23)

| Domain | Tables |
|--------|--------|
| discipline | `educlaw_k12_discipline_incident`, `educlaw_k12_discipline_student`, `educlaw_k12_discipline_action`, `educlaw_k12_manifestation_review` |
| health_records | `educlaw_k12_health_profile`, `educlaw_k12_health_visit`, `educlaw_k12_student_medication`, `educlaw_k12_medication_log`, `educlaw_k12_immunization`, `educlaw_k12_immunization_waiver` |
| special_education | `educlaw_k12_sped_referral`, `educlaw_k12_sped_evaluation`, `educlaw_k12_sped_eligibility`, `educlaw_k12_iep`, `educlaw_k12_iep_goal`, `educlaw_k12_iep_service`, `educlaw_k12_iep_service_log`, `educlaw_k12_iep_team_member`, `educlaw_k12_iep_progress`, `educlaw_k12_504_plan` |
| grade_promotion | `educlaw_k12_promotion_review`, `educlaw_k12_promotion_decision`, `educlaw_k12_intervention_plan` |
