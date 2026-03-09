---
name: educlaw-sped
version: 1.0.0
description: EduClaw Special Education (SPED) — IEP management, service tracking, and IDEA compliance reporting.
author: ERPForge
source: https://github.com/avansaber/educlaw
parent: educlaw-k12
scripts:
  - scripts/db_query.py
domains:
  - iep
  - services
  - compliance
total_actions: 20
tables: 4
---

# EduClaw SPED (Special Education)

Sub-vertical of EduClaw K-12. Manages the full IDEA Part B lifecycle: Individualized Education Programs (IEPs) with measurable goals, service allocations (speech therapy, OT, PT, counseling, etc.), session logging, and compliance monitoring. Tracks service hours delivered vs. prescribed and flags overdue annual reviews.

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline**: No external API calls, no telemetry, no cloud dependencies
- **No credentials required**: Uses erpclaw_lib shared library (installed by erpclaw-setup)
- **SQL injection safe**: All queries use parameterized statements
- **IDEA compliance**: IEP lifecycle enforced (draft -> active -> expired)

## Quick Start

```bash
# Create an IEP for a student
python3 scripts/db_query.py --action sped-add-iep \
  --student-id <id> --iep-date 2025-10-15 \
  --disability-category specific_learning_disability \
  --case-manager "Ms. Johnson"

# Add a goal to the IEP
python3 scripts/db_query.py --action sped-add-iep-goal \
  --iep-id <id> --goal-area reading \
  --goal-description "Read at grade level by EOY" \
  --baseline "60 wpm" --target "100 wpm"

# Add a service
python3 scripts/db_query.py --action sped-add-service \
  --student-id <id> --iep-id <id> \
  --service-type speech_therapy --provider "Dr. Speech" \
  --frequency-minutes-per-week 60

# Log a session
python3 scripts/db_query.py --action sped-add-service-log \
  --service-id <id> --session-date 2025-11-05 \
  --duration-minutes 30
```

---

## Tier 1: Most Used Actions

### IEP Management

| Action | Description |
|--------|-------------|
| `sped-add-iep` | Create a new IEP (starts in draft status) |
| `sped-list-ieps` | List IEPs, filter by student/status |
| `sped-get-iep` | Get IEP details including goals and services |
| `sped-update-iep` | Update a draft IEP (active IEPs are immutable) |
| `sped-activate-iep` | Activate a draft IEP; expires previous active IEP |

### IEP Goals

| Action | Description |
|--------|-------------|
| `sped-add-iep-goal` | Add a measurable goal to an IEP |
| `sped-list-iep-goals` | List goals for an IEP |
| `sped-update-iep-goal` | Update goal progress or mark as met/not_met |

---

## Tier 2: Service Tracking

| Action | Description |
|--------|-------------|
| `sped-add-service` | Add a service allocation (speech, OT, PT, etc.) |
| `sped-list-services` | List services, filter by student/type/status |
| `sped-get-service` | Get service details with session logs |
| `sped-update-service` | Update service provider, frequency, or status |
| `sped-add-service-log` | Log an individual therapy/service session |
| `sped-list-service-logs` | List session logs for a service |
| `sped-service-hours-report` | Report delivered vs. prescribed hours |

---

## Tier 3: Compliance & Reports

| Action | Description |
|--------|-------------|
| `sped-compliance-check` | Validate IEP deadlines and service delivery |
| `sped-overdue-iep-report` | List IEPs with overdue annual reviews |
| `sped-service-utilization-report` | Service utilization by type |
| `sped-caseload-report` | Active IEPs per case manager |
| `status` | Skill status and version info |

---

## Tables

| Table | Description |
|-------|-------------|
| `sped_iep` | Individualized Education Programs |
| `sped_iep_goal` | Measurable goals within an IEP |
| `sped_service` | Service allocations (speech, OT, PT, etc.) |
| `sped_service_log` | Individual session/delivery logs |

## IEP Status Lifecycle

```
draft -> active -> expired
                -> archived
```

- Only draft IEPs can be modified
- Activating an IEP automatically expires the previous active IEP for that student
- Active IEPs are immutable; create a new IEP to make changes

## Service Types

`speech_therapy`, `occupational_therapy`, `physical_therapy`, `counseling`, `behavioral`, `aide`, `transport`, `other`

## Dependencies

- `erpclaw-setup` (foundation tables)
