---
name: educlaw-scheduling
version: 1.0.0
description: >
  Master scheduling, schedule patterns, conflict resolution, and room assignment
  for K-12 and higher-education institutions. 57 actions across 5 domains.
author: AvanSaber
homepage: https://github.com/avansaber/educlaw
source: https://github.com/avansaber/educlaw
tier: 4
category: education
requires: [erpclaw, educlaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [educlaw, scheduling, master-schedule, conflict-resolution, room-assignment, bell-period, course-request]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# EduClaw Advanced Scheduling

Advanced scheduling for K-12 and higher-education. Named schedule patterns, master
schedule lifecycle, course request demand analysis, 11 conflict types, smart room
assignment, and instructor constraints.

## Quick Start

```bash
python3 db_query.py --action schedule-add-schedule-pattern \
  --name "Traditional 7-Period" --pattern-type traditional --cycle-days 1 --company-id <id>
python3 db_query.py --action schedule-add-day-type \
  --schedule-pattern-id <id> --code "MON-FRI" --name "Regular Day"
python3 db_query.py --action schedule-add-bell-period \
  --schedule-pattern-id <id> --period-number 1 --period-name "Period 1" \
  --start-time "08:00" --end-time "08:50" --duration-minutes 50
python3 db_query.py --action schedule-activate-schedule-pattern --pattern-id <id>
python3 db_query.py --action schedule-create-master-schedule \
  --academic-term-id <id> --schedule-pattern-id <id> --name "Fall 2026" --company-id <id>
```

## Schedule Patterns (10 actions)

| Action | Description |
|--------|-------------|
| `schedule-add-schedule-pattern` | Create a reusable schedule structure |
| `schedule-update-schedule-pattern` | Update pattern details |
| `schedule-get-schedule-pattern` | Get pattern with day types and bell periods |
| `schedule-list-schedule-patterns` | List patterns with filters |
| `schedule-activate-schedule-pattern` | Activate a pattern |
| `schedule-add-day-type` | Add a named day type (e.g., "Day A", "Day B") |
| `schedule-add-bell-period` | Add a named time slot to a pattern |
| `schedule-get-pattern-calendar` | Get calendar for a pattern |
| `schedule-get-day-type-calendar` | Get day-type-to-date mapping |
| `schedule-get-contact-hours` | Calculate contact hours for pattern/section |

## Master Schedule & Course Requests (24 actions)

| Action | Description |
|--------|-------------|
| `schedule-create-master-schedule` | Create master schedule for a term |
| `schedule-update-master-schedule` | Update schedule details/status |
| `schedule-get-master-schedule` | Get master schedule details |
| `schedule-list-master-schedules` | List master schedules |
| `schedule-add-section-to-schedule` | Add a section to master schedule |
| `schedule-add-section-meeting` | Place section into day-type + period slot |
| `schedule-delete-section-meeting` | Remove a section meeting |
| `schedule-list-section-meetings` | List section meetings |
| `schedule-get-schedule-matrix` | Get full schedule grid |
| `schedule-submit-master-schedule` | Publish master schedule (blocks if CRITICAL conflicts) |
| `schedule-update-schedule-lock` | Lock/unlock master schedule |
| `schedule-create-schedule-clone` | Clone schedule to another term |
| `schedule-activate-course-requests` | Open course request period |
| `schedule-complete-course-requests` | Close course request period |
| `schedule-submit-course-request` | Submit a student course request |
| `schedule-update-course-request` | Update request priority/flags |
| `schedule-get-course-request` | Get request details |
| `schedule-list-course-requests` | List course requests |
| `schedule-approve-course-requests` | Approve requests for a term |
| `schedule-get-demand-report` | Course demand summary |
| `schedule-get-course-demand-analysis` | Detailed demand analysis |
| `schedule-get-singleton-analysis` | Find singleton courses |
| `schedule-get-fulfillment-report` | Request fulfillment report |
| `schedule-get-load-balance-report` | Instructor load balance |

## Conflict Resolution (8 actions)

| Action | Description |
|--------|-------------|
| `schedule-generate-conflict-check` | Run all 11 conflict categories |
| `schedule-list-conflicts` | List conflicts with filters |
| `schedule-get-conflict` | Get conflict details |
| `schedule-complete-conflict` | Resolve a conflict |
| `schedule-accept-conflict` | Accept a non-critical conflict |
| `schedule-get-conflict-summary` | Conflict summary by type/severity |
| `schedule-get-singleton-conflict-map` | Singleton overlap map |
| `schedule-get-student-conflict-report` | Student conflict details |

## Room Assignment (14 actions)

| Action | Description |
|--------|-------------|
| `schedule-assign-room` | Assign room to a section meeting |
| `schedule-assign-rooms` | Bulk assign rooms for master schedule |
| `schedule-delete-room-assignment` | Remove a room assignment |
| `schedule-add-room-block` | Block a room for non-class use |
| `schedule-update-room-swap` | Swap rooms between two section meetings |
| `schedule-propose-room` | Suggest best available room |
| `schedule-list-rooms-by-features` | Search rooms by features and capacity |
| `schedule-assign-room-emergency` | Emergency reassign all meetings from one room to another |
| `schedule-get-room-availability` | Get room availability |
| `schedule-get-room-utilization-report` | Room utilization report |
| `schedule-add-instructor-constraint` | Add instructor scheduling constraint |
| `schedule-update-instructor-constraint` | Update constraint |
| `schedule-list-instructor-constraints` | List constraints |
| `schedule-delete-instructor-constraint` | Remove constraint |

## Auto-Schedule (1 action)

| Action | Description |
|--------|-------------|
| `edu-auto-build-schedule` | Auto-build schedule from demand and constraints |

## Lifecycle Rules

**Master Schedule:** `draft` -> `building` -> `review` -> `published` -> `locked` -> `archived`. Cannot publish with open CRITICAL conflicts.
**Course Request:** `draft` -> `submitted` -> `approved` -> `scheduled` / `alternate_used` / `unfulfilled`. Any -> `withdrawn`.
**Conflict:** `open` -> `resolving` -> `resolved` / `accepted` / `superseded`.

## Workflows

1. **Pattern:** `schedule-add-schedule-pattern` -> `schedule-add-day-type` -> `schedule-add-bell-period` -> `schedule-activate-schedule-pattern`
2. **Demand:** `schedule-activate-course-requests` -> `schedule-submit-course-request` -> `schedule-approve-course-requests` -> `schedule-get-demand-report` -> `schedule-complete-course-requests`
3. **Build:** `schedule-create-master-schedule` -> `schedule-add-section-to-schedule` -> `schedule-add-section-meeting` -> `schedule-assign-rooms` -> `schedule-generate-conflict-check` -> `schedule-submit-master-schedule`
