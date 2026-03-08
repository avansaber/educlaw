# Core Business Workflows: EduClaw State Reporting

**Product:** EduClaw State Reporting (educlaw-statereport)
**Research Date:** 2026-03-05

---

## Overview of Workflow Domains

EduClaw State Reporting has four primary workflow domains:

1. **State Reporting** — Annual cycle: configure → collect → validate → submit → confirm
2. **Ed-Fi Integration** — Continuous real-time data push to state ODS with error resolution
3. **Data Validation** — Pre-submission data quality checks and error management
4. **Submission Tracking** — Monitor collection windows, submission status, historical audit

Each domain contains specific sub-workflows detailed below.

---

## Domain 1: State Reporting Annual Cycle

### Workflow 1.1: Annual Reporting Setup

**Trigger:** Beginning of new school year or new collection window period
**Actor:** District Data Coordinator / SIS Administrator

```
Step 1: Configure State Connection
  - Enter state Ed-Fi ODS endpoint URL
  - Enter OAuth 2.0 client credentials (client ID + secret)
  - Select state (e.g., "California", "Texas", "Wisconsin")
  - Test connection → confirm authentication succeeds
  - Save Ed-Fi integration profile

Step 2: Define Collection Windows
  - Select state → import predefined window definitions
    OR
  - Manually define window:
    - Window name (e.g., "Fall 2025-26")
    - Window type (fall_enrollment, fall_sped, eoy_attendance, etc.)
    - Open date / close date
    - Snapshot date (data frozen at this point)
    - Required data categories for this window
  - Activate window

Step 3: Configure State-Specific Mappings
  - Enter NCES LEA ID for the district
  - Enter NCES School ID for each school
  - Map internal grade levels → Ed-Fi GradeLevelDescriptor
  - Map internal race codes → Ed-Fi RaceDescriptor
  - Map internal course codes → SCED codes (if required)
  - Map internal disability categories → IDEA disability codes
  - Map attendance status codes → Ed-Fi AttendanceEventCategoryDescriptor

Step 4: Verify Student Supplements
  - Check: all students have SSID assigned
    → If missing: flag students needing SSID request to state
  - Check: all students have race/ethnicity recorded
    → Flag students with missing demographics
  - Check: EL-flagged students have language + proficiency data
  - Check: SPED-flagged students have disability category + placement
  - Generate "Data Readiness Report" showing % complete per category

  Decision: Is data ≥ 95% complete?
    → Yes: Proceed to collection window
    → No: Assign data entry tasks to school staff; set deadline
```

---

### Workflow 1.2: Fall Enrollment Collection Window

**Trigger:** Collection window opens (typically October 1–31)
**Actor:** District Data Coordinator

```
Step 1: Open Collection Window
  - System status: "Collection Window Open"
  - LEA receives notification: "Fall collection window is now open"
  - System begins tracking: which students / data elements are ready

Step 2: Live Data Sync to State ODS (continuous)
  - Nightly (or on-demand): push all changes since last sync to Ed-Fi ODS
  - Resources pushed in dependency order:
    1. LocalEducationAgency (if changed)
    2. Schools (if changed)
    3. Students (new + changed demographics)
    4. StudentEducationOrganizationAssociation (race, EL, SPED flags)
    5. StudentSchoolAssociation (enrollment: entry date, grade level, entry type)
    6. StudentProgramAssociation (SPED, EL, Title programs)
    7. StaffSchoolAssociation (staff assignments)
    8. StaffSectionAssociation (teacher-section links)
    9. Session / CalendarDate (calendar data)
  - Each resource: record sync status (success / error) + HTTP response code
  - Errors logged to sr_submission_error table

Step 3: Monitor Validation Errors (ongoing)
  - State ODS returns Level 1 errors immediately on POST
  - State validation engine returns Level 2/3 errors asynchronously
  - Error portal (from state) shows errors; EduClaw pulls error feed
    OR
  - User manually checks state portal and enters errors into EduClaw
  - Error dashboard shows: error count by type, severity, student

Step 4: Resolve Errors
  - For each error:
    a. Identify source record (which student / staff / section)
    b. Determine cause (missing data, wrong code, date conflict)
    c. Correct source data (edit in EduClaw operational tables)
    d. Re-sync affected records to state ODS
    e. Confirm error resolved (state ODS accepts corrected record)
  - Mark error as resolved in sr_submission_error
  - Track time to resolution

  Decision: Are all critical errors resolved?
    → Yes: Proceed to snapshot
    → No: Continue error resolution; escalate if needed

Step 5: Take Snapshot (Collection Window Close Date)
  - System freezes data at snapshot timestamp:
    - Extract all relevant data from educlaw tables
    - Store point-in-time copy in sr_snapshot_record
    - Lock snapshot — cannot be modified after close
  - Generate snapshot summary report:
    - Total students enrolled
    - Enrollment by grade level
    - Enrollment by race/ethnicity (disaggregated)
    - EL student count
    - SPED student count
    - Economic disadvantage count
  - Coordinator reviews summary for reasonableness

  Decision: Does summary data look correct?
    → Yes: Finalize submission
    → No: Contact state for amendment process; document discrepancy

Step 6: Submit / Certify
  - District administrator certifies submission is accurate and complete
  - Certification recorded (user, timestamp, IP address) in sr_submission
  - State portal notified (if applicable)
  - Submission status → "Certified"
```

---

### Workflow 1.3: End-of-Year Attendance Collection (EOY)

**Trigger:** End-of-year collection window (typically June–August)
**Actor:** District Attendance Coordinator + Data Coordinator

```
Step 1: Calculate ADA/ADM for Reporting Period
  - For each student enrolled during the period:
    - Total school days in period = calendar.count(instructional_days)
    - Days present = count(attendance WHERE status = 'present')
    - Days excused = count(attendance WHERE status = 'excused')
    - Days half_day = count(attendance WHERE status = 'half_day') × 0.5
    - ADA contribution = (present + excused_if_counted + half_day) / total_days
      [Note: whether excused absences count toward ADA varies by state]
  - Aggregate: sum all student ADA contributions = total ADA
  - ADM = total student-days enrolled / total school days

Step 2: Identify Chronic Absenteeism
  - For each student:
    - Calculate % of days absent (excused + unexcused)
    - If ≥ 10% of enrolled days = chronically absent
  - Generate chronic absenteeism list by school, grade, subgroup
  - Cross-check: ESSA threshold must agree with EDFacts FS196

Step 3: Validate Attendance Data
  Validation rules:
  - No student has attendance recorded on non-instructional days
  - No student has attendance outside their enrollment period
  - Every enrolled student has ≥1 attendance record
  - Half-day attendance has section_id (period-level, not just daily)
  - ADA total is reasonable (compare to prior year; flag if >5% change)

Step 4: Push Attendance Data to Ed-Fi ODS
  - StudentSchoolAttendanceEvent — for each absent/tardy daily record
  - StudentSectionAttendanceEvent — for section-level records
  - CalendarDate — confirm all instructional days are marked

Step 5: Generate EOY Attendance Report
  - Report: ADA, ADM by school and grade level
  - Report: Chronic absenteeism rate by school, race, SPED, EL
  - Compare to prior year
  - Estimate funding impact (ADA × per-pupil rate)
  - Export for state portal submission

Step 6: Finalize and Certify
  - Lock attendance data for the school year
  - Administrator certifies accuracy
  - Record certification in sr_submission
```

---

## Domain 2: Ed-Fi Integration Workflows

### Workflow 2.1: Initial Ed-Fi Configuration

```
Step 1: Create Ed-Fi Profile
  - Profile name (e.g., "Texas TSDS 2025-26")
  - State code
  - Ed-Fi ODS base URL
  - OAuth token URL
  - OAuth client ID + secret (stored encrypted)
  - API version (5.x, 6.x, 7.x)
  - School year context

Step 2: Test Authentication
  - Request OAuth token → verify 200 OK
  - GET /ed-fi/localEducationAgencies → verify district is visible
  - GET /ed-fi/schools → verify schools are accessible

Step 3: Map Organization Identifiers
  - For each company (LEA): enter NCES LEA ID
  - For each school: enter NCES School ID
  - These become the Ed-Fi natural keys for all submissions

Step 4: Map Descriptors
  - For each EduClaw internal code, enter corresponding Ed-Fi descriptor URI
  - Grade levels, race, sex, attendance event types, disability types, etc.
  - Save descriptor mapping configuration

Step 5: Initial Sync (Bootstrap)
  - Push all existing data to state ODS:
    - Organizations → Students → Enrollments → Attendance → Grades
  - Review initial error count
  - Priority resolve: enrollment errors (block attendance from syncing)
```

---

### Workflow 2.2: Continuous Sync (Daily Operation)

**Trigger:** Nightly scheduled job (configurable; default: 2:00 AM)
**Also Available:** On-demand sync from admin console

```
Step 1: Determine Delta
  - Query educlaw tables for records changed since last_sync_at
  - Build priority queue:
    Priority 1: New enrollments / exits (immediately affects reporting)
    Priority 2: Demographic changes (race, EL status, SPED changes)
    Priority 3: Attendance updates
    Priority 4: Grade updates
    Priority 5: Staff changes

Step 2: Sync in Dependency Order
  For each resource type in order:
  2a. Resolve Ed-Fi natural keys for each record
  2b. Prepare JSON payload per Ed-Fi schema
  2c. PUT resource to Ed-Fi ODS endpoint
  2d. Handle response:
      → 200/201: Success — update sync_status, last_synced_at
      → 400: Validation error — log to sr_submission_error
      → 404: Resource not found — try POST instead
      → 409: Conflict — flag for manual review
      → 5xx: Retry with exponential backoff (3 attempts)
      → Timeout: Mark as pending retry

Step 3: Refresh Error Feed
  - Pull validation errors from state error API (if available)
  - OR: Check error count via state portal UI
  - Update sr_submission_error with latest error status

Step 4: Notify
  - If new critical errors introduced: notify Data Coordinator
  - Daily summary email: records synced, errors, resolution rate
```

---

### Workflow 2.3: Error Resolution

**Trigger:** Error appears in error dashboard
**Actor:** Data Coordinator / School Secretary

```
Step 1: Triage Error
  - Identify: which student, which data element
  - Classify:
    Level 1 (format/schema) → fix data entry
    Level 2 (cross-entity) → check related records
    Level 3 (business rule) → may require state guidance

Step 2: Investigate Root Cause
  - Click through to student record
  - Check specific field identified in error
  - Common root causes:
    - Missing race/ethnicity → school staff never entered it
    - Invalid SSID → typo in state ID field
    - Enrollment outside session dates → term dates misconfigured
    - Missing EL assessment → student flagged EL but no assessment recorded
    - SPED without disability category → IEP not fully entered
    - Attendance on non-school day → calendar error

Step 3: Correct Data
  - Edit source record in EduClaw
  - Error may be in: student supplement, enrollment, attendance, staff
  - Some errors require contacting school principal or teacher

Step 4: Re-Sync Affected Record
  - Manual re-sync: select student → "Re-sync to Ed-Fi"
  - System pushes updated record to state ODS
  - Check response: error cleared or new error

Step 5: Mark Resolved or Escalate
  - If resolved: mark error as resolved; record resolution_method
  - If not resolved: escalate to state help desk
    - Enter state support ticket number
    - Document state guidance received
    - Track escalation status
```

---

## Domain 3: Data Validation

### Workflow 3.1: Pre-Submission Validation Run

**Trigger:** Manual (data coordinator runs before window deadline) or Automatic (nightly)
**Actor:** Data Coordinator

```
Step 1: Select Scope
  - Run validation for: All students OR specific school OR specific collection window
  - Select rule set:
    - Federal standard rules (always run)
    - State-specific rules (select state)
    - District custom rules (optional)

Step 2: Execute Validation
  For each student in scope:

  Rule Category A: Student Identity & Demographics
  - [ ] SSID present and unique
  - [ ] Race/ethnicity not null or "Unknown"
  - [ ] Date of birth present and reasonable (age 3-21 for K-12)
  - [ ] Gender present
  - [ ] Legal name present (first + last)

  Rule Category B: Enrollment
  - [ ] Active program enrollment exists for current school year
  - [ ] Enrollment dates within academic year bounds
  - [ ] Grade level appropriate for age (±2 year tolerance)
  - [ ] Entry type present on all enrollment records
  - [ ] Exit type present on all closed enrollment records
  - [ ] No overlapping active enrollments in same school

  Rule Category C: Special Education (if SPED flagged)
  - [ ] Disability category present
  - [ ] Educational environment code present
  - [ ] IEP start date before enrollment date or same day
  - [ ] SPED program entry date present

  Rule Category D: English Learner (if EL flagged)
  - [ ] Home language code present (not "English" if EL)
  - [ ] English language proficiency assessment result present
  - [ ] EL program entry date present
  - [ ] If RFEP: reclassification date present

  Rule Category E: Attendance (EOY window only)
  - [ ] Total attendance days ≤ total instructional days
  - [ ] No attendance records outside enrollment period
  - [ ] Present + Absent + Excused = Total records ≤ Total school days

  Rule Category F: Discipline (CRDC/IDEA window only)
  - [ ] Each incident has: date, type, perpetrator, action
  - [ ] IDEA flag matches student SPED status
  - [ ] Suspension days summed per student ≤ 180

  Rule Category G: Staff (staffing window)
  - [ ] All teachers have valid credential on file
  - [ ] Staff-section assignments cover all active sections
  - [ ] FTE values sum to reasonable range per staff member

Step 3: Generate Validation Report
  - Summary: Total records checked, errors by category, severity
  - Detail: Student-level error list (student ID, name, error description, severity)
  - Priority sorting: Critical errors (block submission) → Major → Minor → Warnings
  - Export: CSV or print for distribution to school principals

Step 4: Assign Errors
  - For each error: assign responsible party (school, secretary, coordinator)
  - Set due date for resolution
  - Track in error management queue

Step 5: Re-Validate After Corrections
  - Run targeted validation for corrected records
  - Confirm error count decreasing
  - Generate "Validation Cleared" report for administrator sign-off
```

---

### Workflow 3.2: Discipline Incident Recording

**Trigger:** Behavioral incident occurs at school
**Actor:** School Administrator / Dean of Students

```
Step 1: Create Discipline Incident
  - Record: incident date, time, school
  - Incident type (select from CRDC-aligned list):
    - Bullying / Harassment
    - Drug Violation
    - Physical Assault (student on student)
    - Physical Assault (student on staff)
    - Weapons Violation (firearms)
    - Weapons Violation (other)
    - Vandalism
    - Insubordination
    - Other
  - Description (narrative)
  - Location on campus
  - Reported by

Step 2: Add Involved Students
  - Search and select student(s) involved
  - For each student:
    - Role: offender / victim / witness
    - IDEA flag (auto-populated from student SPED status)
    - Section 504 flag (auto-populated)

Step 3: Record Disciplinary Action
  - Action type (CRDC-aligned):
    - In-School Suspension (ISS)
    - Out-of-School Suspension 1–10 days (OSS short)
    - Out-of-School Suspension >10 days (OSS long)
    - Expulsion with services
    - Expulsion without services
    - Transfer to alternative school (placement change)
    - Referral to law enforcement
    - School-related arrest
    - No action
  - Start date / end date of suspension
  - Total days removed (calculated)
  - Alternative education provided? (Y/N)

Step 4: IDEA Manifestation Determination (if IDEA student + >10 day suspension)
  - Prompt: "This student is IDEA-eligible and has been suspended >10 days.
             A Manifestation Determination Review (MDR) is required."
  - Record MDR outcome: Manifestation / Not a manifestation
  - If manifestation: educational services must continue; log services provided

Step 5: Notify
  - Auto-notify guardian of suspension (via educlaw_notification)
  - Log notification for CRDC documentation

Step 6: Sync to Ed-Fi
  - POST DisciplineIncident to Ed-Fi ODS
  - POST StudentDisciplineIncidentAssociation for each involved student
  - Include: BehaviorDescriptor, DisciplineDescriptor, days removed
```

---

## Domain 4: Submission Tracking

### Workflow 4.1: Collection Window Lifecycle

```
Status Lifecycle:
  upcoming → open → data_entry → validation → snapshot → submitted → certified → closed

Step 1: upcoming
  - Window defined but not yet open
  - System shows countdown: "Fall window opens in 14 days"

Step 2: open
  - Window is open; continuous sync running
  - Data entry and corrections allowed
  - Errors being resolved

Step 3: data_entry (active work phase)
  - Bulk of error resolution
  - Data coordinators making corrections
  - Daily progress report to administrator

Step 4: validation
  - Final validation run before snapshot
  - All critical errors must be resolved
  - Decision gate: proceed to snapshot OR extend error resolution

Step 5: snapshot
  - Snapshot taken at configured timestamp
  - Data frozen (read-only for this window)
  - Summary report generated

Step 6: submitted
  - Data certified as submitted to state
  - If state has an acknowledgment API: poll for confirmation
  - Record submission timestamp and user

Step 7: certified
  - State has accepted the submission
  - No further action needed for this window
  - District receives confirmation from state portal

Step 8: closed
  - Window archived
  - Historical record preserved
  - Next window's "upcoming" state activates
```

---

### Workflow 4.2: Multi-Year Submission History

**Purpose:** Provide complete audit trail of all submissions for compliance and audit defense

```
View Submission History:
  - Filter by: school year, collection window, submission status
  - For each submission record:
    - Window name and dates
    - Snapshot date and data summary
    - Submission date and submitted_by user
    - Certification date and certified_by user
    - Total records submitted by resource type
    - Error count at submission (and how many resolved)
    - State confirmation received (Y/N + date)

Export Submission Package:
  - For a given window: export all records that were submitted
  - Useful for: audit defense, state queries, re-submission after correction

Re-Submission Workflow (after state requests correction):
  1. State contacts LEA with correction request
  2. LEA opens amendment in system (creates new submission record)
  3. Correct specific records
  4. Re-run validation
  5. Submit amended records to state ODS
  6. Record amendment reason + approval
  7. Link amendment to original submission
```

---

### Workflow 4.3: ADA Funding Dashboard

**Actor:** Superintendent / Business Manager
**Purpose:** Real-time visibility into ADA and its funding implications

```
Step 1: Calculate Current ADA
  - Current date: [today]
  - School days elapsed: [count of instructional days to date]
  - For each enrolled student:
    - Days present to date / days elapsed = student ADA contribution
  - District ADA = sum of all student contributions / enrolled count
  - Display: current ADA %, trending up/down, vs. prior year

Step 2: Project Annual ADA
  - Extrapolate current ADA to full year
  - Apply state ADA calculation rules (which absences count)
  - Project: full-year ADA if current trend continues

Step 3: Calculate Funding Impact
  - Input: state per-pupil ADA rate (configurable)
  - ADA × per-pupil rate = projected ADA funding
  - Compare to budget assumption
  - Show: variance from budget (favorable / unfavorable)
  - Show: funding impact of +1% ADA improvement

Step 4: Identify At-Risk Students
  - Students currently below 90% attendance (heading toward chronic absenteeism)
  - Chronically absent students (already ≥10% absent days)
  - Group by: school, grade, teacher
  - Export list for intervention outreach
```

---

## 5. Workflow Integration Map

```
educlaw_student ──────────────────────────────────────┐
educlaw_student_attendance ───────────────────────────┤
educlaw_course_enrollment ────────────────────────────┤
educlaw_program_enrollment ──────────────────────────→│  State Reporting Workflow
educlaw_assessment_result ───────────────────────────→│  (Snapshot Engine)
educlaw_instructor ──────────────────────────────────→│
educlaw_academic_year/term ──────────────────────────→│
                                                       ↓
                              sr_student_supplement (race, EL, SPED, SSID)
                              sr_discipline_incident
                              sr_special_education
                              sr_collection_window
                                                       ↓
                              sr_snapshot (frozen point-in-time)
                                                       ↓
                              Ed-Fi API Client → State ODS
                                                       ↓
                              sr_submission_error (from state ODS)
                                                       ↓
                              Error Resolution Workflow
                                                       ↓
                              sr_submission (certified, history)
```

---

## 6. Decision Points & Edge Cases

| Scenario | Decision | Action |
|----------|---------|--------|
| Student enrolled mid-year | Prorate ADA from enrollment date | Only count days from entry date |
| Student exits before window | Include with exit date and type | Exit type required; no attendance after exit |
| Student transfers from another district | Need prior SSID from previous district | SSID match must occur |
| SPED student suspended >10 days | Manifestation Determination required | System prompts MDR workflow |
| Race missing at snapshot time | Cannot submit without it | Block snapshot; require data entry |
| SSID not yet received from state | Log as "pending SSID"; sync when received | Cannot post to Ed-Fi without SSID |
| Ed-Fi ODS returns 409 (conflict) | Record already exists with different data | Manual review; update vs. delete/re-post |
| Collection window date missed | Late submission process | State-specific grace period; document reason |
| State returns no errors after submission | Window is clean | Proceed to certification |
| Staff assignment missing credential | Flag in staffing validation | Block EDFacts FS099 export |
