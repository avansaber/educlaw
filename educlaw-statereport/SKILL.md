---
name: educlaw-statereport
version: 1.0.0
description: >
  EduClaw State Reporting -- State reporting, Ed-Fi integration, data validation,
  and submission tracking for K-12 LEAs. 98 actions across 6 domains.
author: AvanSaber
homepage: https://github.com/avansaber/educlaw
source: https://github.com/avansaber/educlaw
tier: 4
category: education
requires: [erpclaw, educlaw, educlaw-k12]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [educlaw, state-reporting, ed-fi, crdc, edfacts, idea-618, data-validation, submission-tracking]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# EduClaw State Reporting

State reporting, Ed-Fi API integration, data validation, and submission tracking
for K-12 Local Education Agencies (LEAs).

## Security Model

- **Local-only data**: All records stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline by default**: No network activity during data entry, validation, snapshot, or submission tracking
- **No credentials required for core operations**: Uses erpclaw_lib shared library (installed by erpclaw)
- **SQL injection safe**: All queries use parameterized statements
- **Ed-Fi sync is opt-in**: The `submit-*-to-edfi` and `statereport-get-edfi-connection-test` actions make outbound HTTPS calls to a configured ODS endpoint only when explicitly invoked. These are the sole source of external network activity.
- **Credential protection**: OAuth client secrets are encrypted before database insertion. Decrypted values are never returned in action output, logs, or error messages.

## Quick Reference

### Tier 1 — Daily Operations

| Action | Description |
|--------|-------------|
| `statereport-add-student-supplement` | Create state reporting supplement (race, SSID, EL/SPED flags) for a student |
| `statereport-assign-ssid` | Record state-assigned SSID; sets ssid_status='assigned' |
| `statereport-update-student-race` | Set race/ethnicity; auto-computes federal rollup per OMB rules |
| `statereport-update-el-status` | Update EL flags (is_el, el_entry_date, home_language_code) |
| `statereport-update-sped-status` | Update SPED flags (is_sped, is_504, sped_entry_date) |
| `statereport-add-discipline-incident` | Create discipline incident (INC-YYYY-NNNNN naming series) |
| `statereport-add-discipline-student` | Add student to incident; auto-populates IDEA/504 flags |
| `statereport-add-discipline-action` | Add disciplinary action; auto-sets mdr_required for IDEA students |
| `statereport-apply-validation` | Execute all active rules for a collection window |
| `statereport-list-submission-errors` | List open errors by window, severity, category |
| `statereport-update-error-resolution` | Mark error resolved/deferred with method and notes |

### Tier 2 — Collection Window Management

| Action | Description |
|--------|-------------|
| `statereport-add-collection-window` | Define a new state reporting collection window |
| `statereport-apply-window-status` | Move window through lifecycle (upcoming→open→…→certified) |
| `statereport-create-snapshot` | Freeze data: creates sr_snapshot + sr_snapshot_record rows |
| `statereport-add-submission` | Record a submission attempt (initial/amendment) |
| `statereport-approve-submission` | Certify accuracy; atomically updates submission+snapshot+window |
| `statereport-create-amendment` | Create amendment linked to original; re-opens window |
| `statereport-get-error-dashboard` | Error counts by severity × category × resolution_status |
| `statereport-assign-errors` | Assign multiple errors to staff in one operation |
| `statereport-generate-ada` | Calculate ADA/ADM for a period |
| `statereport-get-ada-dashboard` | ADA with funding impact calculation |
| `statereport-list-chronic-absenteeism` | Flag students with ≥10% absent days |

### Tier 3 — Ed-Fi Integration & Reports

| Action | Description |
|--------|-------------|
| `statereport-add-edfi-config` | Create Ed-Fi ODS connection profile; encrypts OAuth secret |
| `statereport-get-edfi-connection-test` | Test OAuth + ODS connectivity; records last_tested_at |
| `statereport-add-org-mapping` | Map LEA/school to NCES and Ed-Fi identifiers |
| `statereport-import-descriptor-mappings` | Upsert multiple code→URI descriptor mappings |
| `statereport-submit-student-to-edfi` | Push Student + SEOrgAssociation payload |
| `statereport-submit-enrollment-to-edfi` | Push StudentSchoolAssociation records |
| `statereport-submit-attendance-to-edfi` | Push StudentSchoolAttendanceEvent records |
| `statereport-submit-sped-to-edfi` | Push StudentSpecialEducationProgramAssociation |
| `statereport-submit-el-to-edfi` | Push StudentLanguageInstructionProgramAssociation |
| `statereport-submit-discipline-to-edfi` | Push DisciplineIncident records |
| `statereport-submit-staff-to-edfi` | Push Staff + StaffSchoolAssociation records |
| `statereport-submit-failed-syncs` | Re-queue all error/retry sync entries for a window |
| `statereport-import-validation-rules` | Load 57 built-in federal validation rules |
| `statereport-generate-enrollment-report` | Enrollment by race/grade/subgroup with suppression |
| `statereport-generate-crdc-report` | CRDC-formatted counts by race/sex/disability |
| `statereport-get-data-readiness-report` | Data completeness score per category (0-100) |
| `statereport-generate-submission-package` | Full snapshot+records JSON for audit defense |

---

## All Actions Index

Complete index of all 98 actions across 6 domains. All names use standard kebab-case
prefixes per ClawHub naming convention.

| Action | Domain | Description |
|--------|--------|-------------|
| `statereport-add-student-supplement` | demographics | Create state reporting supplement for a student |
| `statereport-update-student-supplement` | demographics | Update supplement fields; recomputes race_federal_rollup |
| `statereport-get-student-supplement` | demographics | Get supplement by student_id or supplement_id |
| `statereport-list-student-supplements` | demographics | List supplements with filters |
| `statereport-assign-ssid` | demographics | Record state-assigned SSID |
| `statereport-update-student-race` | demographics | Set race/ethnicity; auto-computes federal rollup |
| `statereport-update-el-status` | demographics | Update EL flags |
| `statereport-update-sped-status` | demographics | Update SPED flags |
| `statereport-update-economic-status` | demographics | Update economic disadvantage flag |
| `statereport-add-sped-placement` | demographics | Add SPED placement record |
| `statereport-update-sped-placement` | demographics | Update SPED placement fields |
| `statereport-get-sped-placement` | demographics | Get SPED placement by student_id + school_year |
| `statereport-list-sped-placements` | demographics | List SPED placements with filters |
| `statereport-add-sped-service` | demographics | Add related service to a SPED placement |
| `statereport-update-sped-service` | demographics | Update service fields |
| `statereport-list-sped-services` | demographics | List SPED services |
| `statereport-delete-sped-service` | demographics | Delete a service record |
| `statereport-add-el-program` | demographics | Record EL program enrollment |
| `statereport-update-el-program` | demographics | Update EL program fields |
| `statereport-get-el-program` | demographics | Get EL program record |
| `statereport-list-el-programs` | demographics | List EL programs with filters |
| `statereport-add-discipline-incident` | discipline | Create discipline incident |
| `statereport-update-discipline-incident` | discipline | Update incident fields |
| `statereport-get-discipline-incident` | discipline | Get incident with students and actions |
| `statereport-list-discipline-incidents` | discipline | List incidents with filters |
| `statereport-delete-discipline-incident` | discipline | Delete incident (only if no students attached) |
| `statereport-add-discipline-student` | discipline | Add student to incident |
| `statereport-update-discipline-student` | discipline | Update student role or IDEA/504 flags |
| `statereport-delete-discipline-student` | discipline | Remove student from incident |
| `statereport-list-discipline-students` | discipline | List all students for an incident |
| `statereport-add-discipline-action` | discipline | Add disciplinary action |
| `statereport-update-discipline-action` | discipline | Update action fields including MDR outcome |
| `statereport-record-mdr-outcome` | discipline | Record MDR outcome |
| `statereport-get-discipline-action` | discipline | Get a specific disciplinary action |
| `statereport-list-discipline-actions` | discipline | List actions with filters |
| `statereport-get-discipline-summary` | discipline | CRDC-formatted discipline summary |
| `statereport-add-edfi-config` | ed_fi | Create Ed-Fi ODS connection profile |
| `statereport-update-edfi-config` | ed_fi | Update ODS URL, OAuth credentials |
| `statereport-get-edfi-config` | ed_fi | Get Ed-Fi config (no decrypted secret) |
| `statereport-list-edfi-configs` | ed_fi | List configs with filters |
| `statereport-get-edfi-connection-test` | ed_fi | Test OAuth token fetch; records last_tested_at |
| `statereport-add-org-mapping` | ed_fi | Map LEA/school to NCES and Ed-Fi identifiers |
| `statereport-update-org-mapping` | ed_fi | Update NCES/Ed-Fi identifiers |
| `statereport-get-org-mapping` | ed_fi | Get org mapping |
| `statereport-list-org-mappings` | ed_fi | List org mappings for a company |
| `statereport-add-descriptor-mapping` | ed_fi | Add a code → Ed-Fi descriptor URI mapping |
| `statereport-update-descriptor-mapping` | ed_fi | Update descriptor URI |
| `statereport-import-descriptor-mappings` | ed_fi | Upsert multiple descriptor mappings from JSON array |
| `statereport-list-descriptor-mappings` | ed_fi | List descriptor mappings for a config |
| `statereport-delete-descriptor-mapping` | ed_fi | Delete a descriptor mapping |
| `statereport-submit-student-to-edfi` | ed_fi | Push Student + SEOrgAssociation payload |
| `statereport-submit-enrollment-to-edfi` | ed_fi | Push StudentSchoolAssociation records |
| `statereport-submit-attendance-to-edfi` | ed_fi | Push StudentSchoolAttendanceEvent records |
| `statereport-submit-sped-to-edfi` | ed_fi | Push StudentSpecialEducationProgramAssociation |
| `statereport-submit-el-to-edfi` | ed_fi | Push StudentLanguageInstructionProgramAssociation |
| `statereport-submit-discipline-to-edfi` | ed_fi | Push DisciplineIncident records |
| `statereport-submit-staff-to-edfi` | ed_fi | Push Staff + StaffSchoolAssociation records |
| `statereport-get-edfi-sync-log` | ed_fi | Get sync log entries |
| `statereport-list-edfi-sync-errors` | ed_fi | List failed/pending sync entries |
| `statereport-submit-failed-syncs` | ed_fi | Re-attempt all error/retry sync entries |
| `statereport-add-collection-window` | state_reporting | Define a new reporting collection window |
| `statereport-update-collection-window` | state_reporting | Update window dates/config |
| `statereport-get-collection-window` | state_reporting | Get window with error counts and snapshot summary |
| `statereport-list-collection-windows` | state_reporting | List windows with filters |
| `statereport-apply-window-status` | state_reporting | Move window through lifecycle |
| `statereport-create-snapshot` | state_reporting | Freeze data into snapshot |
| `statereport-get-snapshot` | state_reporting | Get snapshot summary |
| `statereport-list-snapshot-records` | state_reporting | Get student-level snapshot records |
| `statereport-generate-ada` | state_reporting | Calculate ADA/ADM |
| `statereport-get-ada-dashboard` | state_reporting | ADA with trend and funding impact |
| `statereport-list-chronic-absenteeism` | state_reporting | Flag students with ≥10% absent days |
| `statereport-get-data-readiness-report` | state_reporting | Data completeness score per category (0-100) |
| `statereport-generate-enrollment-report` | state_reporting | Enrollment by race/grade/subgroup |
| `statereport-generate-crdc-report` | state_reporting | CRDC-formatted counts by race/sex/disability |
| `statereport-add-validation-rule` | data_validation | Add a validation rule to the library |
| `statereport-update-validation-rule` | data_validation | Update rule SQL, message template, or metadata |
| `statereport-get-validation-rule` | data_validation | Get rule by ID or code |
| `statereport-list-validation-rules` | data_validation | List rules with filters |
| `statereport-update-validation-rule-status` | data_validation | Activate or deactivate a rule |
| `statereport-import-validation-rules` | data_validation | Load 57 built-in federal validation rules |
| `statereport-apply-validation` | data_validation | Execute all active rules for a collection window |
| `statereport-apply-student-validation` | data_validation | Run all rules for a single student |
| `statereport-get-validation-results` | data_validation | Get validation results with summary counts |
| `statereport-assign-submission-error` | data_validation | Assign error to a staff member |
| `statereport-update-error-resolution` | data_validation | Mark error resolved/deferred |
| `statereport-list-submission-errors` | data_validation | List errors for a window |
| `statereport-get-error-dashboard` | data_validation | Error counts by severity × category × resolution_status |
| `statereport-assign-errors` | data_validation | Assign multiple errors to a staff member |
| `statereport-submit-error-escalation` | data_validation | Escalate to state help desk with ticket ID |
| `statereport-add-submission` | submission_tracking | Record a new submission attempt |
| `statereport-update-submission-status` | submission_tracking | Update submission status |
| `statereport-get-submission` | submission_tracking | Get submission with snapshot and error counts |
| `statereport-list-submissions` | submission_tracking | List submissions for a company |
| `statereport-approve-submission` | submission_tracking | Certify accuracy; atomically updates submission + snapshot |
| `statereport-create-amendment` | submission_tracking | Create amendment linked to original |
| `statereport-get-submission-history` | submission_tracking | Full chronological submission history |
| `statereport-generate-submission-package` | submission_tracking | Full snapshot+records JSON for audit defense |
| `statereport-get-submission-audit-trail` | submission_tracking | Complete audit trail |

---

## Invariants

| Domain | Invariant |
|--------|-----------|
| Demographics | One `sr_student_supplement` per `educlaw_student` (UNIQUE) |
| Demographics | `race_federal_rollup` computed from is_hispanic_latino + race_codes |
| Demographics | One `sr_sped_placement` per student per school_year |
| Discipline | `mdr_required=1` auto-set for IDEA student + days_removed > 10 |
| Ed-Fi | `oauth_client_secret_encrypted` never stored in plaintext |
| State Reporting | Cannot advance to snapshot if critical open errors exist |
| State Reporting | `sr_snapshot_record` is INSERT-only (no UPDATE/DELETE) |
| Submission | `statereport-approve-submission` atomically updates submission + snapshot + window |
| Validation | `rule_code` is globally UNIQUE |
| All | `company_id` is never NULL |

