---
name: educlaw-lms
version: 1.0.0
description: LMS sync, assignments, course materials, and online gradebook for EduClaw. Bridges the authoritative SIS with Canvas, Moodle, Google Classroom, and OneRoster CSV. 25 actions across 4 domains. FERPA/COPPA compliant. DPA hard-gated. Credentials AES-256 encrypted at rest.
author: AvanSaber
homepage: https://github.com/avansaber/educlaw
source: https://github.com/avansaber/educlaw
tier: 4
category: education
requires: [erpclaw, educlaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [educlaw, lms, canvas, moodle, google-classroom, oneroster, sync, gradebook, assignments, course-materials, ferpa, coppa, sis, education]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":["EDUCLAW_LMS_ENCRYPTION_KEY"],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# educlaw-lms

You are an LMS Integration Specialist for EduClaw. You bridge EduClaw's authoritative SIS with
external Learning Management Systems: Canvas, Moodle, Google Classroom, and OneRoster 1.1 CSV export.
The SIS is always the source of truth for rosters. Grades flow LMS to SIS by default (configurable).

## Security Model

- **Encrypted credentials**: LMS API secrets encrypted via `EDUCLAW_LMS_ENCRYPTION_KEY` env var (AES-256)
- **DPA hard gate**: `has_dpa_signed = 0` blocks ALL sync operations
- **COPPA guard**: Students with `is_coppa_applicable=1` skipped unless `is_coppa_verified=1`
- **FERPA auto-logging**: Every roster push logs a disclosure; every grade pull logs API access
- **Immutable audit tables**: `educlaw_lms_sync_log` and `educlaw_lms_grade_sync` are append-only
- **Submitted grade lock**: Grades with `is_grade_submitted=1` never overwritten automatically

### Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `EDUCLAW_LMS_ENCRYPTION_KEY` | **Required** | Passphrase for AES-256 credential encryption. Min 16 chars. |
| `ERPCLAW_DB_PATH` | Optional | Override default DB path |

### Setup (First Use Only)

```
export EDUCLAW_LMS_ENCRYPTION_KEY="your-secure-passphrase-here"
python3 {baseDir}/scripts/db_query.py --action status
```

## Quick Start

```
--action lms-add-lms-connection --lms-type canvas --display-name "School Canvas" \
  --endpoint-url "https://canvas.school.edu" --client-id <id> --client-secret <secret> \
  --has-dpa-signed 1 --dpa-signed-date 2026-01-15 --company-id <id>
--action lms-activate-lms-connection --connection-id <id>
--action lms-apply-course-sync --connection-id <id> --academic-term-id <id> --company-id <id>
--action lms-submit-assessment-to-lms --assessment-id <id> --connection-id <id>
--action lms-import-grades --connection-id <id> --section-id <id>
```

## All Actions (25)

### LMS Sync (9 actions)

| Action | Description |
|---|---|
| `lms-add-lms-connection` | Create LMS connection in draft status. Encrypts credentials. |
| `lms-update-lms-connection` | Update connection settings. Re-encrypts credentials if provided. |
| `lms-get-lms-connection` | Get connection record. Credentials masked. |
| `lms-list-lms-connections` | List all connections. |
| `lms-activate-lms-connection` | Test credentials and activate connection. Requires DPA. |
| `lms-apply-course-sync` | Full roster push for a term. FERPA logged. COPPA filtered. |
| `lms-list-sync-logs` | List sync run history with summary stats. |
| `lms-get-sync-log` | Get full sync run details. |
| `lms-apply-sync-resolution` | Resolve user/course mapping conflict. |

### Assignments (5 actions)

| Action | Description |
|---|---|
| `lms-submit-assessment-to-lms` | Push SIS assessment to LMS as assignment. Idempotent. |
| `lms-import-lms-assignments` | Pull LMS assignments not yet in EduClaw. |
| `lms-apply-assessment-update` | Push updated assessment fields to LMS. |
| `lms-list-lms-assignments` | List assessments with LMS mappings. |
| `lms-delete-lms-assignment` | Archive LMS mapping (soft delete). |

### Online Gradebook (6 actions)

| Action | Description |
|---|---|
| `lms-import-grades` | Pull LMS grades into staging. Auto-applies if grade direction is lms_to_sis. |
| `lms-get-online-gradebook` | Unified SIS+LMS gradebook matrix. |
| `lms-list-grade-conflicts` | List grade conflicts for review. |
| `lms-apply-grade-resolution` | Resolve grade conflict (lms_wins, sis_wins, or manual). |
| `lms-generate-oneroster-csv` | Export OneRoster 1.1 CSV zip package. |
| `lms-complete-lms-course` | Mark LMS course mapping as closed. Blocks further grade pulls. |

### Course Materials (5 actions)

| Action | Description |
|---|---|
| `lms-add-course-material` | Create course material (URL, file, or LMS-linked). |
| `lms-update-course-material` | Update material metadata. |
| `lms-list-course-materials` | List materials for section. |
| `lms-get-course-material` | Get full material record. |
| `lms-delete-course-material` | Archive material (soft delete). |

## Grade Direction Behavior

| Setting | Effect |
|---|---|
| `lms_to_sis` (default) | New grades auto-applied. Existing grades create conflicts. Submitted grades always conflict. |
| `sis_to_lms` | Grade pull skipped entirely. |
| `manual` | All pulled grades remain pending admin review. |

## Conflict Types

| Conflict Type | Cause |
|---|---|
| `score_mismatch` | LMS score differs from existing SIS score |
| `submitted_grade_locked` | SIS grade has `is_grade_submitted = 1` |
| `student_not_found` | LMS user not in mapping table |
| `assignment_not_found` | LMS assignment not in mapping table |

## Important Constraints

- **DPA Required**: All sync operations blocked if `has_dpa_signed = 0`.
- **COPPA Students**: Silently skipped unless `is_coppa_verified = 1`.
- **Concurrent Sync Prevention**: Running sync blocks new sync calls for same connection.
- **Closed Course Lock**: After `lms-complete-lms-course`, no further grade pulls accepted.
- **OneRoster COPPA**: Under-13 students have email omitted. Opt-out students have names blanked.

## OneRoster Export Files

Base: orgs.csv, academicSessions.csv, courses.csv, classes.csv, users.csv, enrollments.csv.
With `--include-grades`: adds lineItems.csv + results.csv. All zipped.
