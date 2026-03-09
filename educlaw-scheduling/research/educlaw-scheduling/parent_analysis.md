# EduClaw Advanced Scheduling — Parent Analysis

**Parent Product:** EduClaw (`educlaw`)
**Sub-Vertical:** educlaw-scheduling
**Analysis Date:** 2026-03-05

---

## 1. Parent Product Overview

EduClaw is an AI-native education management system (SIS + ERP) for K-12 and small-to-mid higher education institutions. It provides:
- 32 database tables across 9 domains (Students, Academics, Grading, Attendance, Fees, Staff, Communications, FERPA Compliance, Institutional Setup)
- ~74 actions covering the full student lifecycle
- Full integration with ERPClaw foundation skills (GL, Selling, Payments, HR)

The parent explicitly **deferred** "Advanced Scheduling (block, rotating)" to v2 in its research summary. EduClaw Scheduling is the purpose-built v2 expansion that delivers this deferred capability.

---

## 2. Parent Tables Relevant to Scheduling

### 2.1 Directly Extended / Leveraged

| Table | Purpose | Scheduling Relevance |
|-------|---------|---------------------|
| `educlaw_academic_year` | Calendar year (e.g., "2026-2027") | Master schedule is anchored to academic year |
| `educlaw_academic_term` | Term (semester/quarter/trimester) | Schedule is built per term; status lifecycle drives scheduling window |
| `educlaw_room` | Physical space (room_number, building, capacity, room_type, facilities) | Room assignment and booking must reference this table |
| `educlaw_course` | Course catalog (course_code, name, credit_hours, course_type, max_enrollment) | Scheduling is section creation from course catalog |
| `educlaw_section` | Section instance (course + term + instructor + room + days_of_week + start_time + end_time) | **Core extension point** — current model is too simple for advanced scheduling |
| `educlaw_instructor` | Instructor profile (max_teaching_load_hours, office_hours) | Constraint source for scheduling engine |
| `educlaw_course_enrollment` | Student-section enrollment record | Must detect student-level schedule conflicts |
| `educlaw_waitlist` | Student waitlist for sections | Influenced by master schedule capacity decisions |
| `educlaw_course_prerequisite` | Course prerequisites | Scheduling must respect prerequisite sequencing across terms |
| `educlaw_program_enrollment` | Student's active program | Used to determine which courses students need |
| `educlaw_program_requirement` | Required courses per program | Source of scheduling demand (course requests) |

---

### 2.2 Parent `educlaw_section` — Current Limitations

The existing `educlaw_section` table stores schedule info as:
```yaml
days_of_week: TEXT NOT NULL DEFAULT '[]'   # JSON: ["Mon", "Wed", "Fri"]
start_time:   TEXT NOT NULL DEFAULT ''      # "09:00" (24-hour)
end_time:     TEXT NOT NULL DEFAULT ''      # "09:50"
```

**These fields are sufficient for traditional 5-day-a-week schedules but cannot represent:**
- Block schedules (A/B day alternating patterns)
- 4x4 block schedules (full semester in half the days)
- Rotating drop schedules (7-of-8 periods rotating daily)
- Trimester schedules with different period lengths per day type
- Multi-room sections (lecture hall + lab room)
- Split-block meetings (different rooms for different days)
- Period numbers (sections that meet in "Period 3" vs. specific clock times)

**EduClaw Scheduling extends the section model** with a proper period/day-type structure while keeping `educlaw_section` as the parent record for backward compatibility.

---

### 2.3 Foundation Tables (ERPClaw) Inherited

| Table | Owner | Scheduling Use |
|-------|-------|----------------|
| `company` | erpclaw-setup | Institution context on all scheduling tables |
| `employee` | erpclaw-hr | Instructor availability lookups |
| `department` | erpclaw-hr | Department-level scheduling constraints |
| `audit_log` | erpclaw-setup | Schedule changes, conflict resolutions |
| `naming_series` | erpclaw-gl | Naming series for master schedules, course requests |

---

## 3. What the Parent Already Provides

### 3.1 Basic Conflict Detection (Implicit)
The parent enforces conflict-free scheduling via database indexes only:
- `idx_section_instructor_term` — Same instructor can't be on two conflicting sections (but not enforced at overlap level)
- `idx_section_room_term` — Same room should not double-book

**Gap:** The parent does NOT have an explicit conflict detection engine — conflicts can be created and only discovered reactively. The sub-vertical must provide proactive detection.

### 3.2 Simple Section Creation
The parent's `add-section` action creates sections with:
- One instructor, one room, one time slot (days_of_week + start/end time)
- Status lifecycle: `draft → scheduled → open → closed → cancelled`
- Max enrollment tracked

**Gap:** No batch section creation, no schedule pattern application, no course request-driven scheduling.

### 3.3 Room Catalog
`educlaw_room` already captures: capacity, room_type, facilities (JSON array). This is sufficient for room assignment — the scheduling sub-vertical does NOT need to redefine rooms, but it needs to **extend** room data with:
- Availability windows (room may be unavailable certain periods)
- Preferred department/course type mappings

### 3.4 Instructor Profile
`educlaw_instructor` captures: `max_teaching_load_hours`, `office_hours` (JSON). The scheduling sub-vertical extends this with:
- Period-level unavailability (instructor can't teach Period 1 on Tuesdays)
- Preferred teaching times
- Prep period requirements

### 3.5 Academic Term Status Lifecycle
```
setup → enrollment_open → active → grades_open → grades_finalized → closed
```
Master schedule building happens during the `setup` phase. The scheduling module must integrate with this lifecycle.

---

## 4. What Needs to Be Extended / Built New

### 4.1 Schedule Pattern System (NEW)
The parent has no concept of named schedule patterns. EduClaw Scheduling must build:
- `educlaw_schedule_pattern` — Named pattern (Traditional 7-Period, 4x4 Block, A/B Block, Trimester, Rotating Drop, Custom)
- `educlaw_bell_period` — Named periods within a pattern (Period 1 = 8:00-8:50, etc.)
- `educlaw_day_type` — Named day types within a cycle (Day A, Day B, Monday, Tuesday, etc.)

### 4.2 Master Schedule Document (NEW)
No parent concept of a "master schedule" document. Needed:
- `educlaw_master_schedule` — The term-level master schedule with build status, pattern reference, and publishing lifecycle
- Status lifecycle: `draft → building → review → published → locked`

### 4.3 Section Meeting Slots (EXTENDS section)
Replace the simplistic `days_of_week + start_time + end_time` with proper period assignments:
- `educlaw_section_meeting` — Links a section to specific day_type + period combinations
- Supports multiple meeting slots per section (e.g., MWF lecture + T lab in different room)
- Maintains backward compat with parent `educlaw_section`

### 4.4 Course Request System (NEW)
Before the master schedule is built, students/counselors submit course requests:
- `educlaw_course_request` — Student requests for specific courses for an upcoming term
- Priority ranking, alternate course designation
- Request analysis (singleton detection, demand forecasting)

### 4.5 Instructor Scheduling Constraints (NEW)
- `educlaw_instructor_constraint` — Period unavailability, load limits, preferred periods, prep time requirements

### 4.6 Room Booking (NEW)
Formal room reservation tracking beyond basic section assignment:
- `educlaw_room_booking` — Explicit room-period-day_type reservations
- Enables conflict detection at booking level (not just query level)

### 4.7 Conflict Registry (NEW)
- `educlaw_schedule_conflict` — Detected conflicts with type, severity, status, and resolution notes
- Types: instructor_double_booking, room_double_booking, student_conflict, capacity_exceeded, instructor_overload, room_type_mismatch

---

## 5. Integration Points Between Parent and Sub-Vertical

### 5.1 Section Lifecycle Extension
```
educlaw_section (parent)
  ↓ EXTENDED BY
educlaw_master_schedule (scheduling) → groups sections for a term
educlaw_section_meeting (scheduling) → replaces days_of_week + start_time model
```

### 5.2 Enrollment Integration
```
educlaw_course_request (scheduling) → drives section creation demand
educlaw_section (parent) → sections created by master schedule builder
educlaw_course_enrollment (parent) → student placed into sections post-schedule
```

### 5.3 Room Integration
```
educlaw_room (parent) → reference for capacity, type, facilities
educlaw_room_booking (scheduling) → explicit reservation record
educlaw_section_meeting (scheduling) → room used per meeting slot
```

### 5.4 Instructor Integration
```
educlaw_instructor (parent) → max_teaching_load_hours
educlaw_instructor_constraint (scheduling) → period unavailability, preferences
educlaw_section_meeting (scheduling) → instructor per meeting slot
```

---

## 6. Naming Convention Alignment

Following parent's ERPClaw conventions:
- **Table prefix:** `educlaw_` (consistent with parent)
- **Scheduling-specific naming series:**
  - Master Schedule: `MS-{YEAR}-{SEQ}` (e.g., `MS-2026-001`)
  - Course Request: `CRQ-{YEAR}-{SEQ}` (e.g., `CRQ-2026-00001`)
- **Status fields:** Use domain-specific keys (not `status` which conflicts with ERPClaw `ok()` response wrapper)
  - `schedule_status`, `conflict_status`, `request_status`
- **Money/Decimal:** Not applicable to scheduling domain (no financial data)
- **Dates/Times:** ISO 8601 text fields, consistent with parent

---

## 7. What Must NOT Be Duplicated

| Parent Entity | Action | Why |
|---------------|--------|-----|
| `educlaw_room` | Do NOT create a new room table | Parent's room table is sufficient; extend via join |
| `educlaw_section` | Do NOT replace | Extend with `educlaw_section_meeting`; keep backward compat |
| `educlaw_academic_term` | Do NOT redefine term structure | Reference FK only |
| `educlaw_instructor` | Do NOT re-store instructor attributes | Add scheduling constraints as separate table |
| `educlaw_course_enrollment` | Do NOT manage enrollment here | Enrollment remains in parent; scheduling outputs feed enrollment |

---

## 8. Parent Analysis Summary

| Assessment | Finding |
|------------|---------|
| **Reuse (no change):** | academic_year, academic_term, room, course, instructor, section (as parent FK target) |
| **Extend (add columns or FK tables):** | room (add room_booking), instructor (add constraints), section (add meeting slots) |
| **Build new (net-new tables):** | master_schedule, schedule_pattern, bell_period, day_type, section_meeting, course_request, instructor_constraint, room_booking, schedule_conflict |
| **Parent lifecycle integration:** | Academic term `status = 'setup'` → schedule building; `status = 'enrollment_open'` → schedule published |
| **Forward compatibility:** | New tables designed so parent educlaw keeps working unchanged; scheduling is additive |

---

*Analysis based on: educlaw schema.yaml (32 tables), research/educlaw/workflows.md, research/educlaw/data_model.md, research/educlaw/research_summary.md*
