# EduClaw Advanced Scheduling — Data Model Insights

## Overview

EduClaw Advanced Scheduling adds **9 new tables** to the parent EduClaw system. All tables follow ERPClaw/EduClaw conventions:
- **IDs:** TEXT PRIMARY KEY (UUID4)
- **Money/Decimal:** N/A (no financial data in scheduling domain)
- **Dates:** TEXT NOT NULL DEFAULT '' (ISO 8601 YYYY-MM-DD)
- **Times:** TEXT NOT NULL DEFAULT '' (HH:MM, 24-hour format)
- **Status:** TEXT NOT NULL DEFAULT 'X' CHECK(status IN (...))
- **Boolean:** INTEGER NOT NULL DEFAULT 0
- **Table prefix:** `educlaw_` (same as parent)
- **Naming series:** for documents (master_schedule, course_request)

---

## Design Principles

### 1. Extend, Don't Replace
The parent `educlaw_section` table remains the canonical section record. The scheduling module extends it with:
- `educlaw_section_meeting` (explicit period/day_type placements)
- `educlaw_master_schedule` (groups sections for building/publishing)

`educlaw_section.days_of_week` + `start_time` + `end_time` fields remain valid for simple sections; `section_meeting` records are additive.

### 2. First-Class Meetings
Every meeting instance (section + day_type + period + room + instructor) is a stored record — not derived or computed. This follows the FET/aSc pattern and enables:
- Per-meeting conflict detection
- Multi-room sections (lecture + lab)
- Instructor substitution per meeting (not whole section)
- Different instructors for different day types (co-teaching)

### 3. Explicit Room Booking
Room assignments are stored twice: on `educlaw_section_meeting.room_id` AND as a separate `educlaw_room_booking` record. The booking record is the source of truth for conflict detection; the meeting record is for display convenience.

This pattern matches Schedule25 and enables future non-class bookings (exams, events) in the same room calendar.

### 4. Constraint Separation
Instructor constraints are stored in `educlaw_instructor_constraint`, not embedded in `educlaw_instructor`. Constraints are:
- Term-specific (can change each term)
- Multiple per instructor
- Multiple types (enumerated constraint_type CHECK)

### 5. Two-Phase: Request → Schedule
Course requests exist independently from sections. Request analysis drives section count decisions. After the master schedule is built, requests are linked to actual sections (request_status → SCHEDULED).

---

## Parent Tables Referenced (Not Owned)

| Parent Table | How Scheduling References It |
|-------------|------------------------------|
| `educlaw_academic_term` | `master_schedule.academic_term_id` (FK) |
| `educlaw_academic_year` | Indirect via academic_term |
| `educlaw_section` | `section_meeting.section_id` (FK) |
| `educlaw_course` | `course_request.course_id` (FK); section_meeting via section |
| `educlaw_instructor` | `section_meeting.instructor_id` (FK); `instructor_constraint.instructor_id` (FK) |
| `educlaw_room` | `room_booking.room_id` (FK); `section_meeting.room_id` (FK) |
| `educlaw_student` | `course_request.student_id` (FK) |
| `company` | `company_id` on ALL scheduling tables |

---

## New Tables: educlaw-scheduling

### Table 1: `educlaw_schedule_pattern`

**Purpose:** Named reusable schedule structure (Traditional, Block, A/B, etc.)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| name | TEXT | NOT NULL | e.g., "Traditional 7-Period", "A/B Block", "4x4 Block", "Rotating Drop" |
| description | TEXT | NOT NULL DEFAULT '' | |
| pattern_type | TEXT | NOT NULL | `traditional\|block_4x4\|block_ab\|trimester\|rotating_drop\|semester\|custom` |
| cycle_days | INTEGER | NOT NULL DEFAULT 1 | Number of unique day types per cycle (A/B block = 2) |
| total_periods_per_cycle | INTEGER | NOT NULL DEFAULT 0 | Total class periods per full cycle |
| notes | TEXT | NOT NULL DEFAULT '' | Implementation notes |
| is_active | INTEGER | NOT NULL DEFAULT 1 | |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(company_id, pattern_type)` — list by type
- `(company_id, is_active)` — list active patterns

**Status Check:** `CHECK(pattern_type IN ('traditional','block_4x4','block_ab','trimester','rotating_drop','semester','custom'))`

**Naming Series:** Not needed (master data, not transactional)

---

### Table 2: `educlaw_day_type`

**Purpose:** Named day within a scheduling cycle (e.g., "Day A", "Day B", "Monday", "Period 1 Day")

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| schedule_pattern_id | TEXT | FK → educlaw_schedule_pattern | NOT NULL |
| code | TEXT | NOT NULL DEFAULT '' | Short code: "A", "B", "1", "2", "MON" |
| name | TEXT | NOT NULL DEFAULT '' | Display name: "Day A", "Day B", "Monday" |
| sort_order | INTEGER | NOT NULL DEFAULT 0 | Display order in cycle |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(schedule_pattern_id, sort_order)` — ordered list per pattern
- `(schedule_pattern_id, code)` — lookup by code

**Constraints:** `UNIQUE (schedule_pattern_id, code)` — no duplicate codes per pattern

**Notes:**
- No `updated_at` — immutable once created (change pattern instead)
- For Traditional (1-day cycle): one day_type record ("Day 1")
- For A/B Block: two records ("Day A", "Day B")
- For Rotating Drop (7 periods): seven records ("Day 1" through "Day 7")

---

### Table 3: `educlaw_bell_period`

**Purpose:** A named time slot within a scheduling day (Period 1, Block A, Lunch, etc.)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| schedule_pattern_id | TEXT | FK → educlaw_schedule_pattern | NOT NULL |
| period_number | TEXT | NOT NULL DEFAULT '' | "1", "2", "A", "B", "Lunch" |
| period_name | TEXT | NOT NULL DEFAULT '' | "Period 1", "Block A", "Lunch Period" |
| start_time | TEXT | NOT NULL DEFAULT '' | HH:MM (24-hour) |
| end_time | TEXT | NOT NULL DEFAULT '' | HH:MM (24-hour) |
| duration_minutes | INTEGER | NOT NULL DEFAULT 0 | Computed: (end - start) in minutes |
| period_type | TEXT | NOT NULL DEFAULT 'class' | `class\|break\|lunch\|homeroom\|advisory\|flex\|passing` |
| applies_to_day_types | TEXT | NOT NULL DEFAULT '[]' | JSON: ["A", "B"] — which day_type codes this period appears on; empty = all |
| sort_order | INTEGER | NOT NULL DEFAULT 0 | Display order within day |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(schedule_pattern_id, sort_order)` — ordered periods per pattern
- `(schedule_pattern_id, period_number)` — lookup by number
- `(schedule_pattern_id, period_type)` — list class periods vs. non-class

**Constraints:**
- `CHECK(period_type IN ('class','break','lunch','homeroom','advisory','flex','passing'))`
- `CHECK(duration_minutes > 0)`
- `UNIQUE (schedule_pattern_id, period_number)` — unique period numbers per pattern

**Notes:**
- No `updated_at` — treat as immutable; create new pattern version if structure changes
- `applies_to_day_types = '[]'` means period applies to ALL day types
- `applies_to_day_types = '["A"]'` means only on Day A (e.g., Block A meeting)
- For A/B Block: 4 class periods per day type, each 90 minutes
- Passing periods stored here to accurately calculate total school day length

---

### Table 4: `educlaw_master_schedule`

**Purpose:** The master schedule document for an academic term — the container that groups all section placements.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| naming_series | TEXT | NOT NULL UNIQUE DEFAULT '' | e.g., "MS-2026-001" |
| name | TEXT | NOT NULL DEFAULT '' | e.g., "Fall 2026 Master Schedule" |
| academic_term_id | TEXT | FK → educlaw_academic_term | NOT NULL, UNIQUE — one master schedule per term |
| schedule_pattern_id | TEXT | FK → educlaw_schedule_pattern | NOT NULL |
| build_notes | TEXT | NOT NULL DEFAULT '' | Planning notes, assumptions |
| total_sections | INTEGER | NOT NULL DEFAULT 0 | Count of sections in this schedule |
| sections_placed | INTEGER | NOT NULL DEFAULT 0 | Sections with at least one meeting assigned |
| sections_with_room | INTEGER | NOT NULL DEFAULT 0 | Sections fully assigned to rooms |
| open_conflicts | INTEGER | NOT NULL DEFAULT 0 | Open CRITICAL or HIGH conflicts |
| fulfillment_rate | TEXT | NOT NULL DEFAULT '' | Decimal % e.g., "94.5" — recalculated on analysis |
| schedule_status | TEXT | NOT NULL DEFAULT 'draft' | See lifecycle below |
| published_at | TEXT | NOT NULL DEFAULT '' | ISO timestamp |
| published_by | TEXT | NOT NULL DEFAULT '' | |
| locked_at | TEXT | NOT NULL DEFAULT '' | ISO timestamp |
| locked_by | TEXT | NOT NULL DEFAULT '' | |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(academic_term_id)` UNIQUE — one master schedule per term
- `(company_id, schedule_status)` — list by status
- `(naming_series)` UNIQUE

**Status Check:** `CHECK(schedule_status IN ('draft','building','review','published','locked','archived'))`

**Naming Series:** `MS-{YEAR}-{SEQ}` → e.g., `MS-2026-001`

---

### Table 5: `educlaw_section_meeting`

**Purpose:** A specific meeting instance of a section — the atomic unit of the master schedule. Represents "Section MATH-101-001 meets on Day A, Period 3, in Room B-201, taught by Instructor Jones."

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| section_id | TEXT | FK → educlaw_section | NOT NULL |
| master_schedule_id | TEXT | FK → educlaw_master_schedule | NOT NULL |
| day_type_id | TEXT | FK → educlaw_day_type | NOT NULL |
| bell_period_id | TEXT | FK → educlaw_bell_period | NOT NULL |
| room_id | TEXT | FK → educlaw_room | Nullable — may not be assigned yet |
| instructor_id | TEXT | FK → educlaw_instructor | Nullable — may differ from section.instructor_id for specific days |
| meeting_type | TEXT | NOT NULL DEFAULT 'regular' | `regular\|lab\|exam\|field_trip\|make_up` |
| is_active | INTEGER | NOT NULL DEFAULT 1 | Soft delete for cancelled meetings |
| notes | TEXT | NOT NULL DEFAULT '' | Special notes for this meeting |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(section_id, day_type_id, bell_period_id)` UNIQUE — one meeting per section per slot
- `(master_schedule_id, day_type_id, bell_period_id)` — all meetings in a time slot
- `(instructor_id, day_type_id, bell_period_id)` — instructor's schedule
- `(room_id, day_type_id, bell_period_id)` — room's booking view
- `(master_schedule_id, section_id)` — all meetings for a section

**Constraints:**
- `CHECK(meeting_type IN ('regular','lab','exam','field_trip','make_up'))`
- `CHECK(is_active IN (0, 1))`

**Design Notes:**
- If a MWF traditional section has 3 meetings/week, there are 3 rows: one per day_type
- Lab sections that use a different room on Thursdays: separate row with different room_id
- `instructor_id` here may differ from `educlaw_section.instructor_id` for co-teaching/substitutes
- This is the definitive source for "what room is a section in" at period level

---

### Table 6: `educlaw_room_booking`

**Purpose:** Explicit room reservation record for conflict detection and room utilization tracking.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| room_id | TEXT | FK → educlaw_room | NOT NULL |
| master_schedule_id | TEXT | FK → educlaw_master_schedule | Nullable — booking may exist outside master schedule (events) |
| section_meeting_id | TEXT | FK → educlaw_section_meeting | Nullable — null for non-class bookings |
| day_type_id | TEXT | FK → educlaw_day_type | NOT NULL |
| bell_period_id | TEXT | FK → educlaw_bell_period | NOT NULL |
| booking_type | TEXT | NOT NULL DEFAULT 'class' | `class\|exam\|event\|maintenance\|admin\|other` |
| booking_title | TEXT | NOT NULL DEFAULT '' | Description for non-class bookings |
| booked_by | TEXT | NOT NULL DEFAULT '' | User who created the booking |
| booking_status | TEXT | NOT NULL DEFAULT 'confirmed' | `confirmed\|tentative\|cancelled` |
| cancellation_reason | TEXT | NOT NULL DEFAULT '' | |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(room_id, day_type_id, bell_period_id, booking_status)` — primary conflict check query
- `(section_meeting_id)` — lookup booking by meeting
- `(master_schedule_id, room_id)` — all bookings for a room in a schedule
- `(company_id, booking_type)` — list by type

**Constraints:**
- `CHECK(booking_type IN ('class','exam','event','maintenance','admin','other'))`
- `CHECK(booking_status IN ('confirmed','tentative','cancelled'))`
- `UNIQUE (room_id, day_type_id, bell_period_id)` where `booking_status != 'cancelled'` — enforced in application logic (SQLite partial indexes not supported)

**Notes:**
- The UNIQUE constraint for active bookings must be enforced at application layer
- Conflict detection query: `SELECT * FROM educlaw_room_booking WHERE room_id = ? AND day_type_id = ? AND bell_period_id = ? AND booking_status = 'confirmed'`
- Non-class bookings (exams, events, maintenance) also use this table → complete room calendar

---

### Table 7: `educlaw_instructor_constraint`

**Purpose:** Scheduling constraints and preferences for instructors, used during master schedule building.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| instructor_id | TEXT | FK → educlaw_instructor | NOT NULL |
| academic_term_id | TEXT | FK → educlaw_academic_term | NOT NULL — constraints are term-specific |
| constraint_type | TEXT | NOT NULL | See types below |
| day_type_id | TEXT | FK → educlaw_day_type | Nullable — if constraint applies to specific day type |
| bell_period_id | TEXT | FK → educlaw_bell_period | Nullable — if constraint applies to specific period |
| constraint_value | INTEGER | NOT NULL DEFAULT 0 | Numeric value for quantitative constraints |
| notes | TEXT | NOT NULL DEFAULT '' | Explanation/justification |
| priority | TEXT | NOT NULL DEFAULT 'preference' | `hard\|soft\|preference` |
| is_active | INTEGER | NOT NULL DEFAULT 1 | |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Constraint Types:**
| constraint_type | day_type_id | bell_period_id | constraint_value | Meaning |
|----------------|------------|----------------|-----------------|---------|
| `unavailable` | required | required | — | Cannot teach this period on this day type |
| `preferred` | optional | required | — | Prefers this period (soft) |
| `max_periods_per_day` | optional | — | e.g., 5 | Max class periods per day type |
| `max_consecutive_periods` | — | — | e.g., 3 | Max back-to-back class periods |
| `requires_prep_period` | — | — | 1 | Must have at least one free period per day |
| `preferred_building` | — | — | — | Prefer sections in a specific building (notes field) |

**Indexes:**
- `(instructor_id, academic_term_id, is_active)` — active constraints for an instructor/term
- `(instructor_id, academic_term_id, constraint_type)` — constraints by type
- `(academic_term_id, constraint_type)` — all constraints of a type for a term

**Constraint Check:** `CHECK(constraint_type IN ('unavailable','preferred','max_periods_per_day','max_consecutive_periods','requires_prep_period','preferred_building'))`
`CHECK(priority IN ('hard','soft','preference'))`

---

### Table 8: `educlaw_course_request`

**Purpose:** A student's request for a specific course in an upcoming term. Drives demand analysis and master schedule building.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| naming_series | TEXT | NOT NULL UNIQUE DEFAULT '' | "CRQ-2026-00001" |
| student_id | TEXT | FK → educlaw_student | NOT NULL |
| academic_term_id | TEXT | FK → educlaw_academic_term | NOT NULL |
| course_id | TEXT | FK → educlaw_course | NOT NULL |
| request_priority | INTEGER | NOT NULL DEFAULT 1 | 1 = highest priority; lower = scheduled first |
| is_alternate | INTEGER | NOT NULL DEFAULT 0 | 1 = alternate request |
| alternate_for_course_id | TEXT | FK → educlaw_course | Nullable — the primary course this alternates for |
| request_status | TEXT | NOT NULL DEFAULT 'submitted' | See lifecycle below |
| fulfilled_section_id | TEXT | FK → educlaw_section | Nullable — set when request is placed |
| prerequisite_override | INTEGER | NOT NULL DEFAULT 0 | 1 = counselor waived prerequisite check |
| prerequisite_override_by | TEXT | NOT NULL DEFAULT '' | Counselor who approved override |
| prerequisite_override_note | TEXT | NOT NULL DEFAULT '' | Reason for override |
| submitted_by | TEXT | NOT NULL DEFAULT '' | User who submitted (student or counselor) |
| approved_by | TEXT | NOT NULL DEFAULT '' | Counselor who approved |
| approved_at | TEXT | NOT NULL DEFAULT '' | |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(student_id, academic_term_id, course_id)` UNIQUE — one request per student per course per term
- `(academic_term_id, course_id, request_status)` — demand analysis queries
- `(student_id, academic_term_id, request_status)` — student's requests
- `(academic_term_id, request_status)` — all pending requests for a term
- `(naming_series)` UNIQUE

**Status Check:** `CHECK(request_status IN ('draft','submitted','approved','scheduled','alternate_used','unfulfilled','withdrawn'))`

**Naming Series:** `CRQ-{YEAR}-{SEQ}` → e.g., `CRQ-2026-00001`

**Notes:**
- `request_priority = 1` means "must have" — scheduled before priority 2, 3, etc.
- Alternate requests: `is_alternate = 1` + `alternate_for_course_id` — scheduled only if primary unavailable
- After master schedule built: update `request_status` and `fulfilled_section_id` via batch update

---

### Table 9: `educlaw_schedule_conflict`

**Purpose:** Registry of detected scheduling conflicts with their type, severity, and resolution status.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PK | UUID |
| master_schedule_id | TEXT | FK → educlaw_master_schedule | NOT NULL |
| conflict_type | TEXT | NOT NULL | See conflict types below |
| severity | TEXT | NOT NULL DEFAULT 'high' | `critical\|high\|medium\|low` |
| section_meeting_id_a | TEXT | FK → educlaw_section_meeting | Primary conflicting meeting |
| section_meeting_id_b | TEXT | FK → educlaw_section_meeting | Secondary conflicting meeting (if applicable) |
| instructor_id | TEXT | FK → educlaw_instructor | Nullable — for instructor-related conflicts |
| room_id | TEXT | FK → educlaw_room | Nullable — for room-related conflicts |
| student_id | TEXT | FK → educlaw_student | Nullable — for student-related conflicts |
| description | TEXT | NOT NULL DEFAULT '' | Human-readable conflict description |
| conflict_status | TEXT | NOT NULL DEFAULT 'open' | `open\|resolving\|resolved\|accepted\|superseded` |
| resolution_notes | TEXT | NOT NULL DEFAULT '' | What action was taken |
| resolved_by | TEXT | NOT NULL DEFAULT '' | User who resolved |
| resolved_at | TEXT | NOT NULL DEFAULT '' | ISO timestamp |
| company_id | TEXT | FK → company | NOT NULL |
| created_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| updated_at | TEXT | NOT NULL DEFAULT datetime('now') | |
| created_by | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(master_schedule_id, conflict_status, severity)` — primary dashboard query
- `(master_schedule_id, conflict_type)` — conflicts by type
- `(instructor_id, conflict_status)` — instructor's conflicts
- `(room_id, conflict_status)` — room's conflicts
- `(section_meeting_id_a)` — conflicts involving a specific meeting
- `(company_id, conflict_status)` — all open conflicts

**Conflict Type Check:**
```
CHECK(conflict_type IN (
  'instructor_double_booking',
  'room_double_booking',
  'student_conflict',
  'instructor_overload',
  'instructor_contract_violation',
  'capacity_exceeded',
  'room_type_mismatch',
  'credential_mismatch',
  'singleton_overlap',
  'contact_hours_deficit',
  'room_shortage'
))
```

**Severity Check:** `CHECK(severity IN ('critical','high','medium','low'))`
**Status Check:** `CHECK(conflict_status IN ('open','resolving','resolved','accepted','superseded'))`

---

## Entity-Relationship Diagram

```
educlaw_academic_term (parent)
        │
        ▼
educlaw_master_schedule ──── educlaw_schedule_pattern
        │                              │
        │                    ┌─────────┴──────────┐
        │                    ▼                    ▼
        │            educlaw_day_type     educlaw_bell_period
        │                    │                    │
        │                    └──────────┬──────────┘
        │                              │
        ▼                              ▼
educlaw_section (parent) ──── educlaw_section_meeting ──── educlaw_room (parent)
        │                              │                          │
        │                    ┌─────────┴──────────┐              │
        │                    ▼                    ▼               ▼
        │           educlaw_instructor     educlaw_room_booking
        │              (parent)
        │                    │
        │                    ▼
        │          educlaw_instructor_constraint
        │
        ▼
educlaw_section_meeting ──── educlaw_schedule_conflict ──── educlaw_master_schedule
        (conflict a)
        │
educlaw_section_meeting
        (conflict b)

educlaw_student (parent)
        │
        ▼
educlaw_course_request ──── educlaw_course (parent)
        │
        ▼ (after scheduling)
educlaw_section (parent) [fulfilled_section_id]
```

---

## Table Count Summary

| Domain | Tables | Notes |
|--------|--------|-------|
| Schedule Patterns | 3 | `schedule_pattern`, `day_type`, `bell_period` |
| Master Schedule | 1 | `master_schedule` |
| Section Meetings | 1 | `section_meeting` |
| Room Management | 1 | `room_booking` |
| Instructor Constraints | 1 | `instructor_constraint` |
| Course Requests | 1 | `course_request` |
| Conflict Registry | 1 | `schedule_conflict` |
| **Total New Tables** | **9** | |
| **Parent Tables Referenced** | **8** | academic_term, section, course, instructor, room, student, company, master_schedule |

---

## Status Lifecycle Summary

### Master Schedule (`schedule_status`)
```
draft → building → review → published → locked → archived
                                ↓
                    (mid-term: locked with override window)
```

### Course Request (`request_status`)
```
draft → submitted → approved → scheduled (placed in a section)
                              → alternate_used (primary failed, alternate placed)
                              → unfulfilled (neither primary nor alternate placed)
                              → withdrawn (student withdrew request)
```

### Schedule Conflict (`conflict_status`)
```
open → resolving → resolved (conflict fixed)
               → accepted (acknowledged, cannot fix)
               → superseded (conflict no longer exists due to other schedule changes)
```

### Schedule Pattern (`is_active` flag, not a status field)
```
active (is_active=1) → deprecated (is_active=0, replaced by new pattern)
```

---

## Naming Series Summary

| Entity | Prefix | Example |
|--------|--------|---------|
| Master Schedule | MS-{YEAR} | MS-2026-001 |
| Course Request | CRQ-{YEAR} | CRQ-2026-00001 |

---

## Key Queries

### 1. Instructor Double-Booking Detection
```sql
SELECT sm1.id AS meeting_a, sm2.id AS meeting_b,
       sm1.instructor_id, sm1.day_type_id, sm1.bell_period_id
FROM educlaw_section_meeting sm1
JOIN educlaw_section_meeting sm2
  ON sm1.instructor_id = sm2.instructor_id
  AND sm1.day_type_id = sm2.day_type_id
  AND sm1.bell_period_id = sm2.bell_period_id
  AND sm1.id != sm2.id
  AND sm1.is_active = 1 AND sm2.is_active = 1
WHERE sm1.master_schedule_id = ?
```

### 2. Room Double-Booking Detection
```sql
SELECT rb1.id AS booking_a, rb2.id AS booking_b,
       rb1.room_id, rb1.day_type_id, rb1.bell_period_id
FROM educlaw_room_booking rb1
JOIN educlaw_room_booking rb2
  ON rb1.room_id = rb2.room_id
  AND rb1.day_type_id = rb2.day_type_id
  AND rb1.bell_period_id = rb2.bell_period_id
  AND rb1.id != rb2.id
  AND rb1.booking_status = 'confirmed' AND rb2.booking_status = 'confirmed'
WHERE rb1.master_schedule_id = ?
```

### 3. Course Demand Analysis
```sql
SELECT cr.course_id, c.name, c.course_code,
       COUNT(*) as total_requests,
       COUNT(*) FILTER (WHERE cr.is_alternate = 0) as primary_requests,
       COUNT(*) FILTER (WHERE cr.is_alternate = 1) as alternate_requests,
       CEIL(COUNT(*) FILTER (WHERE cr.is_alternate = 0) * 1.0 / c.max_enrollment) as sections_needed
FROM educlaw_course_request cr
JOIN educlaw_course c ON c.id = cr.course_id
WHERE cr.academic_term_id = ?
  AND cr.request_status IN ('submitted', 'approved')
GROUP BY cr.course_id, c.name, c.course_code
ORDER BY primary_requests DESC
```

### 4. Student Conflict Detection
```sql
-- Find students with two approved requests that land in same period
SELECT cr1.student_id, cr1.course_id AS course_a, cr2.course_id AS course_b,
       sm1.day_type_id, sm1.bell_period_id
FROM educlaw_course_request cr1
JOIN educlaw_section_meeting sm1 ON sm1.section_id IN (
    SELECT id FROM educlaw_section WHERE course_id = cr1.course_id AND academic_term_id = ?
)
JOIN educlaw_course_request cr2 ON cr2.student_id = cr1.student_id AND cr2.id != cr1.id
JOIN educlaw_section_meeting sm2 ON sm2.section_id IN (
    SELECT id FROM educlaw_section WHERE course_id = cr2.course_id AND academic_term_id = ?
)
WHERE sm1.day_type_id = sm2.day_type_id AND sm1.bell_period_id = sm2.bell_period_id
  AND cr1.academic_term_id = ? AND cr2.academic_term_id = ?
  AND sm1.master_schedule_id = ? AND sm2.master_schedule_id = ?
```

### 5. Room Utilization Report
```sql
SELECT r.id, r.room_number, r.building, r.capacity,
       COUNT(rb.id) as total_bookings,
       COUNT(rb.id) FILTER (WHERE rb.booking_type = 'class') as class_bookings,
       (total_class_periods) as available_periods,  -- from pattern metadata
       ROUND(COUNT(rb.id) FILTER (WHERE rb.booking_type = 'class') * 100.0 / total_class_periods, 1) as utilization_pct
FROM educlaw_room r
LEFT JOIN educlaw_room_booking rb ON rb.room_id = r.id
  AND rb.master_schedule_id = ? AND rb.booking_status = 'confirmed'
WHERE r.company_id = ?
GROUP BY r.id, r.room_number, r.building, r.capacity
ORDER BY utilization_pct DESC
```

---

## Important Implementation Notes

### 1. `schedule_status` Not `status`
Use `schedule_status` (not `status`) on `educlaw_master_schedule` to avoid collision with ERPClaw's `ok()` response wrapper which overwrites `data["status"]`. Same pattern used in parent EduClaw.

### 2. `conflict_status` Not `status`
Same collision avoidance — `educlaw_schedule_conflict` uses `conflict_status`.

### 3. `request_status` Not `status`
Same collision avoidance — `educlaw_course_request` uses `request_status`.

### 4. `booking_status` Not `status`
Same collision avoidance — `educlaw_room_booking` uses `booking_status`.

### 5. Duration as Stored Integer
`educlaw_bell_period.duration_minutes` is stored as calculated integer — NOT derived at query time. This avoids time parsing in every query that calculates contact hours.

### 6. applies_to_day_types as JSON Array
`educlaw_bell_period.applies_to_day_types` is stored as JSON text (e.g., `'["A", "B"]'` or `'[]'` for all). This follows the parent pattern for JSON arrays. Application layer must parse and filter.

### 7. No Nested Sections
EduClaw Scheduling does not implement nested/cross-listed sections in v1. Cross-listed sections (same course offered under two course codes) are handled by creating two separate sections pointing to the same `section_meeting` records — not via a linking table.

---

*Sources: FET data model (lalescu.ro/liviu/fet), Gibbon database schema (GitHub GibbonEdu/core), PowerScheduler database concepts (Macomb ISD docs), Aspen/Follett schedule pattern documentation, Schedule25 room optimizer, ERPClaw conventions (naming series, TEXT IDs, status collision avoidance from parent EduClaw schema.yaml)*
