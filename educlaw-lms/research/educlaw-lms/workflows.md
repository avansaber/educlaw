# EduClaw LMS Integration — Core Business Workflows

## Overview

This document describes step-by-step workflows for all four domains of educlaw-lms:
1. **LMS Sync** — Connect to an LMS, sync courses/users/enrollments
2. **Assignments** — Create and manage assignments across SIS and LMS
3. **Course Materials** — Organize and link course content resources
4. **Online Gradebook** — Pull LMS grades to EduClaw's authoritative gradebook

All workflows follow EduClaw patterns: SIS is the source of truth for student records and official grades. The LMS is the delivery platform and receives a projection of SIS data. Grade passback flows from LMS → SIS but requires explicit approval.

---

## 1. LMS Sync Domain Workflows

### 1.1 Workflow: Configure LMS Connection

**Purpose:** Set up credentials and settings for a new LMS integration.
**Trigger:** Admin decides to connect EduClaw to a Canvas/Moodle/Google Classroom instance.

```
1. Create LMS Connection (Draft)
   ├── Input: lms_type (canvas | moodle | google_classroom | oneroster_csv)
   ├── Input: display_name (e.g., "Jefferson High Canvas")
   ├── Input: endpoint_url (base URL of LMS instance)
   ├── Input: auth credentials based on lms_type:
   │   ├── canvas: client_id, client_secret (OAuth 2.0)
   │   ├── moodle: site_token (admin-issued web service token)
   │   └── google_classroom: service_account_json or oauth_client credentials
   ├── Input: sync settings:
   │   ├── grade_direction: lms_to_sis | sis_to_lms | manual
   │   ├── auto_sync_enabled: 0 | 1
   │   ├── sync_frequency_hours: (if auto_sync_enabled)
   │   └── default_course_prefix: (optional, prepended to LMS course names)
   ├── Compliance fields (mandatory):
   │   ├── has_dpa_signed: 0 | 1 (block sync if 0)
   │   ├── is_coppa_verified: 0 | 1 (required for K-12)
   │   └── dpa_signed_date
   └── Status: DRAFT

2. Validate Connection
   ├── Attempt API call to verify credentials:
   │   ├── Canvas: GET /api/v1/courses (check 200 response)
   │   ├── Moodle: core_webservice_get_site_info
   │   └── Google: courses.list()
   ├── Record: lms_version, site_name from API response
   ├── If DPA not signed → return error: "Cannot activate connection without DPA"
   └── Status: ACTIVE (on success)

3. Configure Sync Scope (optional)
   ├── Limit sync to specific academic terms
   ├── Limit sync to specific programs or sections
   └── Exclude specific student groups (e.g., audit students)
```

**Decision Points:**
- `grade_direction` setting is critical — must be explicitly chosen, never defaulted
- `has_dpa_signed = 0` must BLOCK all sync operations (not just warn)
- `is_coppa_verified = 0` must BLOCK sync for any student with `is_coppa_applicable = 1`

---

### 1.2 Workflow: Sync Courses and Users (Roster Push)

**Purpose:** Push SIS sections, students, and instructors to LMS.
**Trigger:** Start of term, manual trigger by admin, or scheduled job.

```
1. Initiate Sync Run
   ├── Input: lms_connection_id, academic_term_id
   ├── Create sync run record: lms_sync_log (status: RUNNING)
   └── Log start time and triggered_by user

2. Sync Academic Session (Term)
   ├── Check: does LMS have a session matching this academic_term?
   │   ├── IF NO → create term in LMS (start_date, end_date, title)
   │   ├── IF YES → update if dates changed
   │   └── Map: educlaw_academic_term.id → lms_term_id in lms_course_mapping
   └── Log: sessions_created, sessions_updated

3. Sync Courses (Sections)
   ├── For each active section in the academic_term:
   │   ├── Check: does lms_course_mapping exist for this section?
   │   │   ├── IF NO:
   │   │   │   ├── Create course in LMS:
   │   │   │   │   ├── name = section.course.name + " " + section.section_number
   │   │   │   │   ├── course_code = section.course.course_code
   │   │   │   │   ├── term_id = (from step 2)
   │   │   │   │   └── start_date, end_date from academic_term
   │   │   │   └── Insert lms_course_mapping (section_id, lms_course_id, lms_type)
   │   │   └── IF YES:
   │   │       └── Update course name/dates if changed
   │   └── Log result per section (created | updated | error)
   └── Log: courses_created, courses_updated, courses_failed

4. Sync Users (Students + Instructors)
   ├── For each student enrolled in affected sections:
   │   ├── COPPA check: if is_coppa_applicable AND NOT is_coppa_verified → skip, log error
   │   ├── Directory opt-out check: flag if directory_info_opt_out = 1
   │   ├── Check: does lms_user_mapping exist for this student?
   │   │   ├── IF NO:
   │   │   │   ├── Look up by email in LMS (user may already exist)
   │   │   │   │   ├── IF FOUND → create mapping to existing user
   │   │   │   │   └── IF NOT FOUND → create new LMS user account
   │   │   │   │       ├── Fields: first_name, last_name, email
   │   │   │   │       ├── COPPA restriction: only send name + email for under-13
   │   │   │   │       └── Insert lms_user_mapping
   │   │   └── IF YES → update name/email if changed
   │   └── Log result per student (created | matched | updated | skipped_coppa | error)
   ├── For each instructor in affected sections:
   │   └── Same process; instructor role in LMS = "teacher"
   └── Log FERPA disclosure to educlaw_data_access_log per student pushed

5. Sync Enrollments (Roster)
   ├── For each course_enrollment (status = enrolled):
   │   ├── Check: student lms_user_mapping exists?
   │   │   └── IF NO → skip (user sync failed upstream)
   │   ├── Check: lms_course_mapping for the section exists?
   │   │   └── IF NO → skip (course sync failed upstream)
   │   ├── Check: enrollment already exists in LMS?
   │   │   ├── IF NO → create enrollment in LMS (student → course)
   │   │   └── IF YES → verify status matches (enrolled vs. dropped)
   │   └── Log result per enrollment
   ├── Handle drops: for enrollments with status = dropped/withdrawn:
   │   ├── Remove enrollment from LMS (or set status = inactive)
   │   └── Log removal
   └── Log: enrollments_created, enrollments_removed, enrollments_failed

6. Finalize Sync Run
   ├── Update lms_sync_log:
   │   ├── status: COMPLETED | COMPLETED_WITH_ERRORS | FAILED
   │   ├── sections_synced, students_synced, errors_count
   │   ├── completed_at
   │   └── error_summary (JSON of all errors)
   └── Trigger notification if errors_count > 0
```

**Status Lifecycle: Sync Run**
```
PENDING → RUNNING → COMPLETED
                  → COMPLETED_WITH_ERRORS (some records failed)
                  → FAILED (critical error; no records processed)
```

**Integration Points:**
| Step | Parent Action | LMS API |
|------|--------------|---------|
| 2 | `list-academic-terms` | Canvas: POST /terms; Moodle: core_course_create_categories |
| 3 | `list-sections` | Canvas: POST /courses; Moodle: core_course_create_courses |
| 4 | `list-students`, `list-instructors` | Canvas: POST /users; Moodle: core_user_create_users |
| 5 | `list-enrollments` | Canvas: POST /enrollments; Moodle: enrol_manual_enrol_users |

---

### 1.3 Workflow: Resolve Sync Conflicts

**Purpose:** Handle cases where sync produced data conflicts or errors.

```
1. List Conflicts
   ├── Query lms_sync_log for entries with status = 'conflict' or 'error'
   ├── Display: SIS data, LMS data, conflict type (user_mismatch | grade_conflict | enrollment_discrepancy)
   └── Admin reviews conflict list

2. Resolve Individual Conflict
   ├── For ENROLLMENT discrepancy:
   │   ├── Option A: Re-push SIS enrollment to LMS (SIS wins)
   │   ├── Option B: Mark as resolved (no action — manual LMS entry is intentional)
   │   └── Option C: Pull LMS enrollment into SIS (rare — creates course_enrollment record)
   ├── For USER mismatch (SIS email ≠ LMS email):
   │   ├── Option A: Update LMS user email to match SIS
   │   ├── Option B: Update mapping to point to different LMS user ID
   │   └── Option C: Create new LMS user (old user remains, may need manual cleanup)
   └── For GRADE conflict:
       ├── (See Workflow 3.3 — Grade Conflict Resolution)

3. Bulk Conflict Resolution
   ├── "SIS wins all" — push all SIS data, overwrite LMS discrepancies
   ├── "LMS wins all" — pull all LMS data into SIS
   └── "Dismiss all" — mark as reviewed/ignored (with reason)
```

---

## 2. Assignments Domain Workflows

### 2.1 Workflow: Create Assignment and Push to LMS

**Purpose:** Create an assignment in EduClaw (as an assessment) and simultaneously create it in the LMS.
**Context:** Parent EduClaw already has `add-assessment` action. This workflow extends it with LMS push.

```
1. Create Assessment in EduClaw (Parent Action)
   ├── Call parent: add-assessment
   │   ├── --plan-id, --category-id, --name, --max-points, --due-date
   │   └── Returns: assessment_id
   └── Assessment stored in educlaw_assessment

2. Push to LMS (educlaw-lms extension)
   ├── Input: assessment_id, lms_connection_id (or auto-detect from section's connection)
   ├── Lookup: lms_course_mapping for the section linked to this assessment's plan
   ├── Build LMS assignment payload:
   │   ├── name = assessment.name
   │   ├── points_possible = assessment.max_points
   │   ├── due_at = assessment.due_date
   │   ├── grading_type = "points" (or "pass_fail" if grade_type = pass_fail)
   │   └── published = assessment.is_published
   ├── API call to LMS: create assignment
   ├── Store mapping: lms_assignment_mapping (assessment_id, lms_assignment_id, lms_type)
   ├── Log FERPA disclosure (academics category, disclosure type)
   └── Return: lms_assignment_id, lms_assignment_url

3. Handle LMS Response
   ├── IF success → update assessment: lms_synced = 1, lms_url = assignment URL
   ├── IF error → log in lms_sync_log; assessment remains in SIS only
   └── Notify instructor of sync status

Decision Point: Auto-push vs. manual push
   ├── IF lms_connection.auto_push_assignments = 1 → trigger push automatically on add-assessment
   └── IF auto_push = 0 → instructor explicitly calls push-assessment-to-lms
```

---

### 2.2 Workflow: Sync Assignment Changes

**Purpose:** When an assessment is updated in EduClaw, propagate changes to LMS.

```
1. Detect Assessment Change
   ├── Trigger: update-assessment action called in parent
   ├── Check: is there an lms_assignment_mapping for this assessment?
   │   └── IF NO → no LMS action needed
   └── IF YES → proceed

2. Push Update to LMS
   ├── Identify changed fields: name, max_points, due_date, is_published
   ├── Build update payload (only changed fields)
   ├── API call: update assignment in LMS
   ├── Log: updated fields, LMS response
   └── Update lms_sync_log: last_synced_at, sync_status

3. Handle Critical Changes
   ├── max_points changed → warn: existing grades will recalculate in LMS gradebook
   ├── due_date changed → notify students via LMS (if LMS supports)
   └── is_published changed → respect: don't publish in LMS if EduClaw says unpublished
```

---

## 3. Online Gradebook Domain Workflows

### 3.1 Workflow: Pull Grades from LMS

**Purpose:** Import grades entered by instructors in the LMS into EduClaw's authoritative gradebook.
**Context:** This is the most critical workflow — it bridges instructor activity in LMS with official SIS records.

```
1. Initiate Grade Pull
   ├── Input: lms_connection_id, section_id (or academic_term_id for bulk)
   ├── Optionally: specific assessment_id (pull one assignment only)
   └── Create grade pull log entry

2. Fetch LMS Grades
   ├── For each assessment with lms_assignment_mapping:
   │   ├── API call: get all submissions for LMS assignment_id
   │   │   ├── Canvas: GET /courses/:id/assignments/:id/submissions
   │   │   ├── Moodle: mod_assign_get_grades
   │   │   └── Google: courses.courseWork.studentSubmissions.list
   │   └── For each submission:
   │       ├── Map: lms_user_id → student_id (via lms_user_mapping)
   │       ├── Extract: score, graded_at, is_late, comments
   │       └── Store in raw pull buffer

3. Compare LMS Grades to SIS Grades
   ├── For each (student_id, assessment_id) pair in pull buffer:
   │   ├── Look up existing educlaw_assessment_result
   │   ├── Case: No SIS result exists → grade is new (from LMS)
   │   ├── Case: SIS result matches LMS score → no action needed
   │   ├── Case: SIS result ≠ LMS score → CONFLICT (requires resolution)
   │   └── Case: LMS shows no submission → student hasn't submitted (no action)

4. Apply Grades (based on grade_direction setting)
   ├── IF grade_direction = 'lms_to_sis':
   │   ├── For NEW grades: create educlaw_assessment_result record
   │   │   ├── points_earned = LMS score
   │   │   ├── graded_by = "lms_sync" (system user)
   │   │   └── graded_at = LMS graded_at timestamp
   │   ├── For MATCHING grades: no action
   │   └── For CONFLICTS:
   │       ├── IF enrollment.is_grade_submitted = 0 → overwrite with LMS score (log it)
   │       └── IF enrollment.is_grade_submitted = 1 → mark as CONFLICT; requires manual resolution
   ├── IF grade_direction = 'sis_to_lms':
   │   └── Pull is informational only; SIS grades are never overwritten
   └── IF grade_direction = 'manual':
       └── All LMS grades staged for admin review before applying

5. Update FERPA Log
   ├── Log one data_access_log entry per student whose grade was accessed
   ├── access_type = 'pull', data_category = 'grades'
   └── access_reason = "LMS grade sync"

6. Finalize Grade Pull
   ├── Update lms_sync_log: grades_pulled, grades_applied, conflicts_flagged
   ├── Trigger: recalculate section grade for affected students (call parent generate-section-grade)
   └── Notify: if conflicts_flagged > 0, alert instructor/admin
```

**Status Lifecycle: Grade Sync Entry**
```
PENDING → PULLED (from LMS) → APPLIED (written to assessment_result)
                             → CONFLICT (SIS ≠ LMS, awaiting resolution)
                             → SKIPPED (grade_direction = sis_to_lms)
                             → ERROR (failed to map user or assessment)
```

---

### 3.2 Workflow: View Online Gradebook

**Purpose:** Display a unified gradebook showing both SIS-native grades and LMS-pulled grades.

```
1. Fetch Gradebook Data
   ├── Input: section_id
   ├── Load from parent: list-assessments (all assessments for section's plan)
   ├── Load from parent: list-grades (all assessment results)
   ├── Enhance with LMS data:
   │   ├── For each assessment: lookup lms_assignment_mapping
   │   │   └── Add: lms_url, lms_synced, last_synced_at
   │   └── For each assessment_result: lookup lms_grade_sync
   │       └── Add: lms_score (raw LMS score), sync_status, is_conflict

2. Present Unified View
   ├── Student rows × Assessment columns
   ├── Each cell shows:
   │   ├── SIS grade (authoritative): points_earned (from assessment_result)
   │   ├── LMS grade (pulled): lms_score (if different)
   │   └── Conflict indicator: ⚠️ if SIS ≠ LMS
   └── Row summary: current weighted grade, current letter grade

3. Quick Actions from Gradebook
   ├── Push grade SIS → LMS (override LMS with SIS value)
   ├── Accept LMS grade (overwrite SIS with LMS value)
   ├── View submission in LMS (open lms_url in browser)
   └── Trigger grade pull for this section
```

---

### 3.3 Workflow: Resolve Grade Conflict

**Purpose:** Resolve cases where the SIS grade and LMS grade disagree.

```
1. View Conflict
   ├── Display: student name, assessment name
   ├── Display: SIS grade = {points_earned}
   ├── Display: LMS grade = {lms_score}
   ├── Display: LMS graded_at, LMS grader (if available)
   └── Display: is_grade_submitted (if submitted, SIS grade is immutable)

2. Resolution Options

   Option A: Accept LMS Grade (LMS wins)
   ├── IF is_grade_submitted = 0:
   │   ├── Update educlaw_assessment_result.points_earned = lms_score
   │   └── Log: grade updated via LMS sync conflict resolution
   ├── IF is_grade_submitted = 1:
   │   ├── Must use parent's update-grade (amendment workflow)
   │   ├── Create grade_amendment record with reason "LMS sync conflict"
   │   └── Cannot directly overwrite immutable grade
   └── Mark conflict as RESOLVED

   Option B: Keep SIS Grade (SIS wins)
   ├── Optionally: push SIS grade back to LMS (to align)
   └── Mark conflict as DISMISSED

   Option C: Enter New Grade Manually
   ├── Admin/instructor enters a new value
   ├── Update SIS (or amendment if submitted)
   ├── Push new value to LMS
   └── Mark conflict as RESOLVED

3. Bulk Conflict Resolution
   ├── "Accept all LMS" — for unsubmitted grades only
   ├── "Dismiss all" — keep SIS as authoritative; log decisions
   └── Conflicts on submitted grades → require individual review
```

**Rule:** Submitted grades (`is_grade_submitted = 1`) can never be overwritten by automated sync. Always require amendment workflow.

---

## 4. Course Materials Domain Workflows

### 4.1 Workflow: Add Course Material

**Purpose:** Track course documents, links, and resources within EduClaw (SIS-side).
**Context:** Course materials are organized in EduClaw but may link to or be hosted in the LMS.

```
1. Create Course Material Record
   ├── Input: section_id, name, description, material_type
   │   (syllabus | reading | video_link | assignment_guide | rubric | other)
   ├── Input: access_type (url | file_attachment | lms_linked)
   ├── For url: external_url (e.g., YouTube link, external website)
   ├── For file_attachment: file_path (local file reference)
   ├── For lms_linked: fetch from LMS course files API
   │   └── Store: lms_file_id, lms_download_url
   ├── Input: is_visible_to_students (0 | 1)
   ├── Input: available_from, available_until (date range)
   └── Status: ACTIVE

2. Organize Materials
   ├── Sort by sort_order within section
   ├── Group by material_type (optional)
   └── Link to specific assessment_id if material is for a specific assignment

3. Optional: Push Material to LMS
   ├── IF material has a file: upload to LMS Files API
   │   ├── Canvas: POST /courses/:id/files
   │   └── Moodle: core_files_upload
   ├── Optionally: publish to LMS course page as module item
   └── Store: lms_file_id, lms_url in course_material record
```

---

### 4.2 Workflow: Generate OneRoster CSV Export

**Purpose:** Export EduClaw data in OneRoster CSV format for import into any OneRoster-compliant LMS.
**Use case:** Schools using LMS platforms without direct API support (or as a batch sync alternative).

```
1. Configure Export
   ├── Input: academic_term_id (which term to export)
   ├── Input: output_directory (where to write CSV files)
   └── Input: include_grades (0 | 1) — whether to include results.csv

2. Generate Required CSV Files (OneRoster 1.1 format)
   ├── orgs.csv — school organization record
   │   └── Fields: sourcedId, status, dateLastModified, name, type, identifier, parentSourcedId
   ├── academicSessions.csv — academic term data
   │   └── Fields: sourcedId, status, title, type, startDate, endDate, schoolYear
   ├── courses.csv — course catalog (educlaw_course records)
   │   └── Fields: sourcedId, status, title, courseCode, grades, orgSourcedId, subjects
   ├── classes.csv — course sections (educlaw_section records)
   │   └── Fields: sourcedId, status, title, course, terms, classCode, classType, location, school, periods
   ├── users.csv — students and teachers
   │   └── Fields: sourcedId, status, enabledUser, orgSourcedIds, role, username, userIds, givenName, familyName, email, grades
   ├── enrollments.csv — course enrollments + instructor assignments
   │   └── Fields: sourcedId, status, role, user, class, school, beginDate, endDate
   ├── lineItems.csv — assessments (if include_grades)
   │   └── Fields: sourcedId, status, dateLastModified, title, description, class, category, dueDate, resultValueMin, resultValueMax
   └── results.csv — assessment results (if include_grades)
       └── Fields: sourcedId, status, lineItem, student, scoreStatus, score, comment

3. Validate CSV Files
   ├── Check UTF-8 encoding
   ├── Verify required fields are populated
   ├── Verify cross-references are valid (all FKs resolve)
   └── Report any validation errors

4. Package and Output
   ├── Zip all CSV files into oneroster_{term_name}_{date}.zip
   ├── Log export to lms_sync_log (type = oneroster_csv_export)
   └── Return: output_path, file_count, student_count, errors
```

---

## 5. Workflow: End-of-Term Grade Finalization

**Purpose:** At term end, ensure all LMS grades are pulled and reconciled before final grade submission.

```
1. Pre-Submission Check
   ├── For each section with an LMS connection:
   │   ├── Check: any pending grade pulls?
   │   ├── Check: any unresolved grade conflicts?
   │   └── Check: any assessments in LMS not yet pulled?
   └── Report: sections with outstanding LMS sync items

2. Final Grade Pull
   ├── Trigger: pull-grades for all sections in the term
   ├── Apply all new grades from LMS
   └── Stage all conflicts for review

3. Conflict Resolution (Required Before Grade Submission)
   ├── List all unresolved conflicts
   ├── Instructor resolves each one
   └── Status: all conflicts RESOLVED | DISMISSED

4. Disconnect Section from LMS (Post-Submission)
   ├── After parent action: submit-grades (immutable)
   ├── Mark lms_course_mapping: sync_status = CLOSED
   └── No further grade pulls allowed for this section
   ├── (Grade sync for closed sections would violate immutability)
   └── Archive: lms_course_mapping retained for audit purposes
```

---

## 6. Workflow Interaction Map

```
                    ┌─────────────────────────────────────────────────┐
                    │           EduClaw (Parent SIS)                   │
                    │                                                   │
                    │  add-academic-term  →  lms_sync_workflow(1.2)    │
                    │  add-section        →  lms_sync_workflow(1.2)    │
                    │  create-section-enrollment → roster push         │
                    │  add-assessment     →  push-assessment-to-lms    │
                    │  submit-grades      →  close lms course mapping  │
                    └────────────────────────┬────────────────────────┘
                                             │
                              ┌──────────────▼──────────────┐
                              │         educlaw-lms          │
                              │                              │
                              │  lms_sync (Domain 1)        │
                              │  ├── add-lms-connection      │
                              │  ├── sync-courses            │
                              │  ├── sync-users              │
                              │  ├── sync-enrollments        │
                              │  └── resolve-sync-conflicts  │
                              │                              │
                              │  assignments (Domain 2)     │
                              │  ├── push-assessment-to-lms  │
                              │  ├── sync-assignment-update  │
                              │  └── list-lms-assignments    │
                              │                              │
                              │  online_gradebook (Domain 3)│
                              │  ├── pull-grades             │
                              │  ├── get-online-gradebook    │
                              │  └── resolve-grade-conflict  │
                              │                              │
                              │  course_materials (Domain 4) │
                              │  ├── add-course-material     │
                              │  ├── list-course-materials   │
                              │  └── export-oneroster-csv    │
                              └──────────────┬───────────────┘
                                             │
                         ┌───────────────────┴────────────────────┐
                         │                                        │
               ┌─────────▼──────────┐           ┌────────────────▼──────┐
               │  Canvas REST API   │           │ Google Classroom API   │
               │  Moodle WS API     │           │ Moodle WS API          │
               └────────────────────┘           └───────────────────────┘
```

---

## 7. Action Inventory (Estimated)

### LMS Sync Domain (~8 actions)
| Action | Key Parameters | Description |
|--------|----------------|-------------|
| `add-lms-connection` | --lms-type --endpoint-url --display-name --credentials | Configure new LMS connection |
| `update-lms-connection` | --connection-id [fields] | Update connection settings |
| `test-lms-connection` | --connection-id | Validate credentials against LMS API |
| `list-lms-connections` | --company-id --lms-type | List configured connections |
| `sync-courses` | --connection-id --academic-term-id | Push sections/users/enrollments to LMS |
| `list-sync-logs` | --connection-id --status --from-date | List sync history |
| `get-sync-log` | --sync-log-id | Get detailed sync result |
| `resolve-sync-conflict` | --conflict-id --resolution (sis_wins|lms_wins|manual) | Resolve individual conflict |

### Assignments Domain (~5 actions)
| Action | Key Parameters | Description |
|--------|----------------|-------------|
| `push-assessment-to-lms` | --assessment-id --connection-id | Push SIS assessment to LMS as assignment |
| `pull-lms-assignments` | --connection-id --section-id | Pull LMS assignments into SIS mapping |
| `sync-assessment-update` | --assessment-id | Push updated assessment to LMS |
| `list-lms-assignments` | --connection-id --section-id | List all LMS-mapped assignments |
| `unlink-lms-assignment` | --assessment-id --connection-id | Remove LMS mapping (stop syncing) |

### Online Gradebook Domain (~5 actions)
| Action | Key Parameters | Description |
|--------|----------------|-------------|
| `pull-grades` | --connection-id --section-id [--assessment-id] | Pull LMS grades into SIS |
| `get-online-gradebook` | --section-id --connection-id | Get unified SIS+LMS gradebook view |
| `resolve-grade-conflict` | --conflict-id --resolution --resolved-by | Resolve grade conflict |
| `list-grade-conflicts` | --section-id --connection-id --status | List unresolved conflicts |
| `export-oneroster-csv` | --academic-term-id --output-dir [--include-grades] | Generate OneRoster CSV export |

### Course Materials Domain (~5 actions)
| Action | Key Parameters | Description |
|--------|----------------|-------------|
| `add-course-material` | --section-id --name --material-type --access-type | Add material record |
| `update-course-material` | --material-id [fields] | Update material details |
| `list-course-materials` | --section-id --material-type --is-visible-to-students | List materials |
| `get-course-material` | --material-id | Get material with LMS link info |
| `delete-course-material` | --material-id | Archive material |

### **Total Estimated Actions: ~23**

---

*Sources: Canvas REST API Documentation, Moodle Web Services API Documentation, Google Classroom API, IMS Global OneRoster 1.1 CSV Specification, OpenSIS LMS Integration Code, Infinite Campus OneRoster Documentation, PowerSchool Unified Classroom Workflow Documentation, EdLink "What Makes LMS Integration Challenging" (2025)*
