# EduClaw Advanced Scheduling — Implementation Plan

## 1. Product Overview

- **Product name:** `educlaw-scheduling`
- **Display name:** EduClaw Advanced Scheduling
- **Description:** Master scheduling, schedule patterns, conflict resolution, and room assignment for K-12 and higher-education institutions. Extends the parent EduClaw SIS with the advanced scheduling capabilities explicitly deferred in EduClaw v1.
- **Parent product:** `educlaw`
- **Foundation dependencies:** erpclaw-setup, erpclaw-gl, erpclaw-selling, erpclaw-payments, erpclaw-hr

### What This Sub-Vertical Adds

The parent EduClaw provides basic section scheduling (a section with a fixed weekly time slot encoded as `days_of_week + start_time + end_time`). This covers simple semester-based scheduling for ~60% of schools. This sub-vertical delivers the remaining 40%:

- **Named schedule patterns** — Traditional 7-period, 4x4 Block, A/B Alternating, Rotating Drop, Trimester, Semester, Custom
- **Formal master schedule lifecycle** — Draft → Building → Review → Published → Locked → Archived
- **Course request-driven demand analysis** — Collect student requests before sections are created; drive section count decisions from actual demand
- **Proactive conflict detection** — 11 conflict types covering instructor, room, student, and compliance dimensions
- **Smart room assignment** — Capacity, type, and feature-matching with utilization scoring
- **Instructor scheduling constraints** — Period unavailability, contract limits (max consecutive, prep period), preferences

### Target Institutions

- High schools (grades 9–12): block/rotating schedules, course requests, singleton detection
- Middle schools (grades 6–8): team-based scheduling, rotating periods
- Community colleges: semester/trimester patterns, evening sections

### Architectural Philosophy

1. **Extend, don't replace** — `educlaw_section` remains the canonical section record; this sub-vertical adds `educlaw_section_meeting` records on top
2. **Meetings as explicit records** — Every section meeting (section + day_type + period + room + instructor) is a stored row; no encoded JSON arrays
3. **Room booking as first-class entity** — `educlaw_room_booking` is the source of truth for conflict detection; enables future non-class bookings
4. **Constraint table pattern** — Instructor constraints in a separate table (term-specific, multiple per instructor, extensible types)
5. **Status field naming** — Domain-specific keys (`schedule_status`, `conflict_status`, `request_status`, `booking_status`) to avoid collision with ERPClaw's `ok()` response wrapper

---

## 2. Domain Organization

| Domain | Module File | Scope |
| --- | --- | --- |
| `schedule_patterns` | `schedule_patterns.py` | Define and manage reusable scheduling structures: patterns, day types, bell periods, calendar mapping, contact-hour calculation |
| `master_schedule` | `master_schedule.py` | Create and lifecycle-manage the term master schedule; course request collection and demand analysis; section placement in period slots; publish/lock workflow |
| `conflict_resolution` | `conflict_resolution.py` | Detect, categorize, track, and resolve 11 types of scheduling conflicts; pre-publish validation; fulfillment and singleton analysis |
| `room_assignment` | `room_assignment.py` | Manage room bookings; smart room suggestion; bulk auto-assign; instructor scheduling constraints; room utilization reporting |

> **Note on course requests:** Course requests (pre-scheduling demand capture) are implemented inside `master_schedule.py` since demand analysis directly drives master schedule building. They are a distinct sub-section of the domain with their own 9 actions but share the same module file.

---

## 3. Database Schema

### 3.1 Tables (New — 9 tables, all prefixed `educlaw_`)

---

#### Table 1: `educlaw_schedule_pattern`

**Purpose:** Named, reusable scheduling structure (Traditional 7-Period, A/B Block, 4x4 Block, Rotating Drop, Trimester, Semester, Custom). The foundation for all scheduling.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `name` | TEXT | NOT NULL DEFAULT '' | e.g., "Traditional 7-Period", "A/B Block", "4x4 Block" |
| `description` | TEXT | NOT NULL DEFAULT '' | Free-text description |
| `pattern_type` | TEXT | NOT NULL, CHECK | `traditional\|block_4x4\|block_ab\|trimester\|rotating_drop\|semester\|custom` |
| `cycle_days` | INTEGER | NOT NULL DEFAULT 1 | Unique day types per cycle (A/B block = 2, rotating 7-period = 7, traditional = 1) |
| `total_periods_per_cycle` | INTEGER | NOT NULL DEFAULT 0 | Total instructional class periods per full cycle |
| `notes` | TEXT | NOT NULL DEFAULT '' | Implementation notes / assumptions |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | 1 = available for master schedules, 0 = deprecated |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Constraints:**
```sql
CHECK(pattern_type IN ('traditional','block_4x4','block_ab','trimester','rotating_drop','semester','custom'))
CHECK(cycle_days >= 1)
CHECK(is_active IN (0, 1))
```

**Indexes:**
- `idx_schedule_pattern_company_type` ON `(company_id, pattern_type)`
- `idx_schedule_pattern_company_active` ON `(company_id, is_active)`

**Naming series:** None (master data, not transactional)

---

#### Table 2: `educlaw_day_type`

**Purpose:** A named day within a scheduling cycle. For A/B Block: "Day A" and "Day B". For Traditional: "Day 1". For Rotating Drop 7-period: "Day 1" through "Day 7".

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `schedule_pattern_id` | TEXT | NOT NULL, REFERENCES educlaw_schedule_pattern(id) ON DELETE RESTRICT | Parent pattern |
| `code` | TEXT | NOT NULL DEFAULT '' | Short code: "A", "B", "1", "2", "MON", "TUE" |
| `name` | TEXT | NOT NULL DEFAULT '' | Display name: "Day A", "Day B", "Monday", "Day 1" |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | Display order within cycle (1-based) |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Note:** No `updated_at` — treat as immutable; create a new pattern version if the cycle structure changes.

**Constraints:**
```sql
UNIQUE (schedule_pattern_id, code)
CHECK(sort_order >= 0)
```

**Indexes:**
- `idx_day_type_pattern_sort` ON `(schedule_pattern_id, sort_order)`
- `idx_day_type_pattern_code` ON `(schedule_pattern_id, code)` — UNIQUE enforced here

**Examples:**
- Traditional (1-day cycle): 1 row: code="1", name="Day 1"
- A/B Block (2-day cycle): 2 rows: code="A"/"B", names="Day A"/"Day B"
- Rotating Drop (7-day cycle): 7 rows: code="1"–"7", names="Day 1"–"Day 7"

---

#### Table 3: `educlaw_bell_period`

**Purpose:** A named time slot within a scheduling day. "Period 1: 8:00–8:50", "Block A: 8:00–9:30", "Lunch: 11:30–12:00". Both instructional and non-instructional periods are stored to calculate full day length.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `schedule_pattern_id` | TEXT | NOT NULL, REFERENCES educlaw_schedule_pattern(id) ON DELETE RESTRICT | Parent pattern |
| `period_number` | TEXT | NOT NULL DEFAULT '' | "1", "2", "A", "B", "Lunch", "Pass" |
| `period_name` | TEXT | NOT NULL DEFAULT '' | "Period 1", "Block A", "Lunch Period", "Passing" |
| `start_time` | TEXT | NOT NULL DEFAULT '' | HH:MM (24-hour format) |
| `end_time` | TEXT | NOT NULL DEFAULT '' | HH:MM (24-hour format) |
| `duration_minutes` | INTEGER | NOT NULL DEFAULT 0 | Pre-computed: (end_time - start_time) in minutes — stored, not derived |
| `period_type` | TEXT | NOT NULL DEFAULT 'class' | `class\|break\|lunch\|homeroom\|advisory\|flex\|passing` |
| `applies_to_day_types` | TEXT | NOT NULL DEFAULT '[]' | JSON array of day_type codes: `["A","B"]`. Empty = all day types |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | Display order within day |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Note:** No `updated_at` — treat as immutable; create a new pattern if period structure changes.

**Constraints:**
```sql
CHECK(period_type IN ('class','break','lunch','homeroom','advisory','flex','passing'))
CHECK(duration_minutes > 0)
UNIQUE (schedule_pattern_id, period_number)
```

**Indexes:**
- `idx_bell_period_pattern_sort` ON `(schedule_pattern_id, sort_order)`
- `idx_bell_period_pattern_number` ON `(schedule_pattern_id, period_number)` — UNIQUE
- `idx_bell_period_pattern_type` ON `(schedule_pattern_id, period_type)`

**Design note on `applies_to_day_types`:** For A/B Block with 4 class periods per day — "Block A" and "Block B" each appear on both day types: `applies_to_day_types = '[]'`. For a period that only exists on Day A (e.g., an advisory): `applies_to_day_types = '["A"]'`. Application layer parses JSON and filters.

---

#### Table 4: `educlaw_master_schedule`

**Purpose:** The master schedule document for an academic term — the container that groups all section placements for review, publication, and locking. One per academic term.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `naming_series` | TEXT | NOT NULL UNIQUE DEFAULT '' | `MS-{YEAR}-{SEQ}` e.g., `MS-2026-001` |
| `name` | TEXT | NOT NULL DEFAULT '' | e.g., "Fall 2026 Master Schedule" |
| `academic_term_id` | TEXT | NOT NULL UNIQUE, REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | One master schedule per term |
| `schedule_pattern_id` | TEXT | NOT NULL, REFERENCES educlaw_schedule_pattern(id) ON DELETE RESTRICT | The pattern applied to this term |
| `build_notes` | TEXT | NOT NULL DEFAULT '' | Planning notes, assumptions, decisions |
| `total_sections` | INTEGER | NOT NULL DEFAULT 0 | Count of sections linked to this master schedule |
| `sections_placed` | INTEGER | NOT NULL DEFAULT 0 | Sections with at least one section_meeting assigned |
| `sections_with_room` | INTEGER | NOT NULL DEFAULT 0 | Sections fully room-assigned (all meetings have room) |
| `open_conflicts` | INTEGER | NOT NULL DEFAULT 0 | Count of CRITICAL + HIGH conflicts with conflict_status='open'; recalculated by run-conflict-check |
| `fulfillment_rate` | TEXT | NOT NULL DEFAULT '' | Decimal % e.g., "94.5" — recalculated by get-fulfillment-report |
| `schedule_status` | TEXT | NOT NULL DEFAULT 'draft' | See lifecycle below |
| `published_at` | TEXT | NOT NULL DEFAULT '' | ISO 8601 timestamp |
| `published_by` | TEXT | NOT NULL DEFAULT '' | Username |
| `locked_at` | TEXT | NOT NULL DEFAULT '' | ISO 8601 timestamp |
| `locked_by` | TEXT | NOT NULL DEFAULT '' | Username |
| `cloned_from_id` | TEXT | REFERENCES educlaw_master_schedule(id) ON DELETE RESTRICT | Nullable — set when cloned from prior term |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Constraints:**
```sql
CHECK(schedule_status IN ('draft','building','review','published','locked','archived'))
UNIQUE (academic_term_id)
UNIQUE (naming_series)
```

**Lifecycle:**
```
draft → building → review → published → locked → archived
```
- `draft` → initial state; no sections placed
- `building` → sections being created and placed in periods
- `review` → conflict analysis run; administrator reviewing
- `published` → sections marked SCHEDULED; term moves to enrollment_open
- `locked` → no new sections or period changes (allows room/instructor substitutions with override)
- `archived` → end of term; read-only record

**Indexes:**
- `idx_master_schedule_term` ON `(academic_term_id)` UNIQUE
- `idx_master_schedule_company_status` ON `(company_id, schedule_status)`
- `idx_master_schedule_series` ON `(naming_series)` UNIQUE

**Naming series:** `MS-{YEAR}-{SEQ}` → `MS-2026-001`, `MS-2027-001`

---

#### Table 5: `educlaw_section_meeting`

**Purpose:** A specific meeting instance of a section — the atomic unit of the master schedule. Represents "Section MATH-101-001 meets on Day A, Period 3, in Room B-201, taught by Instructor Jones." This is the definitive source for per-period instructor and room assignments.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `section_id` | TEXT | NOT NULL, REFERENCES educlaw_section(id) ON DELETE RESTRICT | Parent section (from educlaw) |
| `master_schedule_id` | TEXT | NOT NULL, REFERENCES educlaw_master_schedule(id) ON DELETE RESTRICT | Master schedule container |
| `day_type_id` | TEXT | NOT NULL, REFERENCES educlaw_day_type(id) ON DELETE RESTRICT | Which day in the cycle |
| `bell_period_id` | TEXT | NOT NULL, REFERENCES educlaw_bell_period(id) ON DELETE RESTRICT | Which period of the day |
| `room_id` | TEXT | REFERENCES educlaw_room(id) ON DELETE RESTRICT | Nullable — room not yet assigned when NULL |
| `instructor_id` | TEXT | REFERENCES educlaw_instructor(id) ON DELETE RESTRICT | Nullable — may differ from section.instructor_id for co-teaching or substitution |
| `meeting_type` | TEXT | NOT NULL DEFAULT 'regular' | `regular\|lab\|exam\|field_trip\|make_up` |
| `meeting_mode` | TEXT | NOT NULL DEFAULT 'in_person' | `in_person\|hybrid\|online` — for accreditation (HLC contact hour rules) |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | Soft delete: 0 = cancelled meeting; does not appear in conflict checks |
| `notes` | TEXT | NOT NULL DEFAULT '' | Special notes for this meeting instance |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Constraints:**
```sql
CHECK(meeting_type IN ('regular','lab','exam','field_trip','make_up'))
CHECK(meeting_mode IN ('in_person','hybrid','online'))
CHECK(is_active IN (0, 1))
UNIQUE (section_id, day_type_id, bell_period_id)
```

**Indexes:**
- `idx_section_meeting_section_slot` ON `(section_id, day_type_id, bell_period_id)` UNIQUE
- `idx_section_meeting_master_slot` ON `(master_schedule_id, day_type_id, bell_period_id)`
- `idx_section_meeting_instructor_slot` ON `(instructor_id, day_type_id, bell_period_id)` — instructor schedule & conflict detection
- `idx_section_meeting_room_slot` ON `(room_id, day_type_id, bell_period_id)` — room schedule view
- `idx_section_meeting_master_section` ON `(master_schedule_id, section_id)` — all meetings for a section
- `idx_section_meeting_active` ON `(master_schedule_id, is_active)`

**Design notes:**
- A MWF traditional section creates 3 rows (one per day_type in a 1-day-type cycle that repeats Mon, Wed, Fri)
- A lab section that uses a different room on Thursdays: separate row with different `room_id`
- `instructor_id` here may differ from `educlaw_section.instructor_id` for co-teaching or per-meeting substitution
- Cancelled meetings: `is_active = 0`; excluded from conflict detection queries

---

#### Table 6: `educlaw_room_booking`

**Purpose:** Explicit room reservation record. The primary source of truth for room conflict detection. Covers class bookings (linked to section meetings) and non-class bookings (exams, events, maintenance) to form a complete room calendar.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `room_id` | TEXT | NOT NULL, REFERENCES educlaw_room(id) ON DELETE RESTRICT | The room being booked |
| `master_schedule_id` | TEXT | REFERENCES educlaw_master_schedule(id) ON DELETE RESTRICT | Nullable — may exist outside master schedule (events) |
| `section_meeting_id` | TEXT | REFERENCES educlaw_section_meeting(id) ON DELETE RESTRICT | Nullable — NULL for non-class bookings |
| `day_type_id` | TEXT | NOT NULL, REFERENCES educlaw_day_type(id) ON DELETE RESTRICT | Day type in cycle |
| `bell_period_id` | TEXT | NOT NULL, REFERENCES educlaw_bell_period(id) ON DELETE RESTRICT | Period of day |
| `booking_type` | TEXT | NOT NULL DEFAULT 'class' | `class\|exam\|event\|maintenance\|admin\|other` |
| `booking_title` | TEXT | NOT NULL DEFAULT '' | Display title for non-class bookings (e.g., "Board Meeting") |
| `booked_by` | TEXT | NOT NULL DEFAULT '' | Username who created the booking |
| `booking_status` | TEXT | NOT NULL DEFAULT 'confirmed' | `confirmed\|tentative\|cancelled` |
| `cancellation_reason` | TEXT | NOT NULL DEFAULT '' | Required when booking_status = cancelled |
| `accessibility_required` | INTEGER | NOT NULL DEFAULT 0 | 1 = section has student with accessibility needs (ADA/504) |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Constraints:**
```sql
CHECK(booking_type IN ('class','exam','event','maintenance','admin','other'))
CHECK(booking_status IN ('confirmed','tentative','cancelled'))
CHECK(accessibility_required IN (0, 1))
```

**Active booking uniqueness:** `UNIQUE (room_id, day_type_id, bell_period_id)` where `booking_status != 'cancelled'` — enforced at application layer (SQLite does not support partial indexes). Conflict detection query: `SELECT * FROM educlaw_room_booking WHERE room_id=? AND day_type_id=? AND bell_period_id=? AND booking_status='confirmed'`.

**Indexes:**
- `idx_room_booking_room_slot_status` ON `(room_id, day_type_id, bell_period_id, booking_status)` — primary conflict check
- `idx_room_booking_meeting` ON `(section_meeting_id)` — lookup booking by meeting
- `idx_room_booking_master_room` ON `(master_schedule_id, room_id)` — all bookings for a room in a schedule
- `idx_room_booking_company_type` ON `(company_id, booking_type)`
- `idx_room_booking_status` ON `(company_id, booking_status)`

---

#### Table 7: `educlaw_instructor_constraint`

**Purpose:** Scheduling constraints and preferences for instructors, per academic term. Used by conflict detection to flag constraint violations (instructor unavailable, max periods exceeded, no prep period, etc.).

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `instructor_id` | TEXT | NOT NULL, REFERENCES educlaw_instructor(id) ON DELETE RESTRICT | The instructor |
| `academic_term_id` | TEXT | NOT NULL, REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | Constraints are term-specific |
| `constraint_type` | TEXT | NOT NULL | See constraint types below |
| `day_type_id` | TEXT | REFERENCES educlaw_day_type(id) ON DELETE RESTRICT | Nullable — if constraint applies to specific day type |
| `bell_period_id` | TEXT | REFERENCES educlaw_bell_period(id) ON DELETE RESTRICT | Nullable — if constraint applies to specific period |
| `constraint_value` | INTEGER | NOT NULL DEFAULT 0 | Numeric value for quantitative constraints (e.g., 5 for max_periods_per_day) |
| `constraint_notes` | TEXT | NOT NULL DEFAULT '' | Justification (e.g., "union contract clause 14.2", "medical appointment Mondays") |
| `priority` | TEXT | NOT NULL DEFAULT 'preference' | `hard\|soft\|preference` |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | 0 = disabled for this term |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Constraint types and semantics:**

| constraint_type | day_type_id | bell_period_id | constraint_value | Meaning |
| --- | --- | --- | --- | --- |
| `unavailable` | required | required | — | Cannot teach this period on this day type (hard) |
| `preferred` | optional | required | — | Prefers to teach this period (soft) |
| `max_periods_per_day` | optional | — | e.g., 5 | Max class periods assignable per day type |
| `max_consecutive_periods` | — | — | e.g., 3 | Max back-to-back class periods without a free period |
| `requires_prep_period` | — | — | 1 | Must have at least one free (unassigned) period per day |
| `preferred_building` | — | — | — | Prefer sections in a specific building (building name in constraint_notes) |

**Constraints:**
```sql
CHECK(constraint_type IN ('unavailable','preferred','max_periods_per_day','max_consecutive_periods','requires_prep_period','preferred_building'))
CHECK(priority IN ('hard','soft','preference'))
CHECK(is_active IN (0, 1))
```

**Indexes:**
- `idx_instructor_constraint_inst_term` ON `(instructor_id, academic_term_id, is_active)` — active constraints per instructor/term
- `idx_instructor_constraint_inst_type` ON `(instructor_id, academic_term_id, constraint_type)`
- `idx_instructor_constraint_term_type` ON `(academic_term_id, constraint_type)` — all constraints of a type for a term

---

#### Table 8: `educlaw_course_request`

**Purpose:** A student's pre-registration request for a specific course in an upcoming term. Collected before the master schedule is built. Drives demand analysis, section count decisions, and conflict matrix analysis.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `naming_series` | TEXT | NOT NULL UNIQUE DEFAULT '' | `CRQ-{YEAR}-{SEQ}` e.g., `CRQ-2026-00001` |
| `student_id` | TEXT | NOT NULL, REFERENCES educlaw_student(id) ON DELETE RESTRICT | The student |
| `academic_term_id` | TEXT | NOT NULL, REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | The upcoming term |
| `course_id` | TEXT | NOT NULL, REFERENCES educlaw_course(id) ON DELETE RESTRICT | Course requested |
| `request_priority` | INTEGER | NOT NULL DEFAULT 1 | 1 = highest priority (schedule first); 2, 3 = secondary priorities |
| `is_alternate` | INTEGER | NOT NULL DEFAULT 0 | 1 = this is an alternate request (fallback if primary fails) |
| `alternate_for_course_id` | TEXT | REFERENCES educlaw_course(id) ON DELETE RESTRICT | Nullable — the primary course this alternates for |
| `request_status` | TEXT | NOT NULL DEFAULT 'submitted' | See lifecycle below |
| `fulfilled_section_id` | TEXT | REFERENCES educlaw_section(id) ON DELETE RESTRICT | Nullable — set when request is placed in a section |
| `prerequisite_override` | INTEGER | NOT NULL DEFAULT 0 | 1 = counselor waived prerequisite check |
| `prerequisite_override_by` | TEXT | NOT NULL DEFAULT '' | Counselor username who approved override |
| `prerequisite_override_note` | TEXT | NOT NULL DEFAULT '' | Reason for prerequisite override |
| `has_iep_flag` | INTEGER | NOT NULL DEFAULT 0 | 1 = student has an IEP; flag for manual scheduling review (IDEA compliance) |
| `submitted_by` | TEXT | NOT NULL DEFAULT '' | Username (student or counselor) |
| `approved_by` | TEXT | NOT NULL DEFAULT '' | Counselor username who approved |
| `approved_at` | TEXT | NOT NULL DEFAULT '' | ISO 8601 timestamp |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**Constraints:**
```sql
CHECK(request_status IN ('draft','submitted','approved','scheduled','alternate_used','unfulfilled','withdrawn'))
CHECK(is_alternate IN (0, 1))
CHECK(prerequisite_override IN (0, 1))
CHECK(has_iep_flag IN (0, 1))
UNIQUE (student_id, academic_term_id, course_id)
UNIQUE (naming_series)
```

**Lifecycle:**
```
draft → submitted → approved → scheduled        (placed in a section)
                             → alternate_used   (primary failed; alternate placed)
                             → unfulfilled      (neither primary nor alternate placed)
                             → withdrawn        (student withdrew)
```

**Indexes:**
- `idx_course_request_student_term_course` ON `(student_id, academic_term_id, course_id)` UNIQUE
- `idx_course_request_term_course_status` ON `(academic_term_id, course_id, request_status)` — demand analysis queries
- `idx_course_request_student_term` ON `(student_id, academic_term_id, request_status)` — student's requests
- `idx_course_request_term_status` ON `(academic_term_id, request_status)` — all pending for a term
- `idx_course_request_series` ON `(naming_series)` UNIQUE

**Naming series:** `CRQ-{YEAR}-{SEQ}` → `CRQ-2026-00001`

---

#### Table 9: `educlaw_schedule_conflict`

**Purpose:** Registry of detected scheduling conflicts — their type, severity, and resolution status. Conflicts are stored explicitly (not just reported) to enable the resolve workflow: detect → assign → resolve → verify.

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `master_schedule_id` | TEXT | NOT NULL, REFERENCES educlaw_master_schedule(id) ON DELETE RESTRICT | Master schedule this conflict belongs to |
| `conflict_type` | TEXT | NOT NULL | See 11 conflict types below |
| `severity` | TEXT | NOT NULL DEFAULT 'high' | `critical\|high\|medium\|low` |
| `section_meeting_id_a` | TEXT | REFERENCES educlaw_section_meeting(id) ON DELETE RESTRICT | Primary conflicting meeting (nullable for non-meeting conflicts) |
| `section_meeting_id_b` | TEXT | REFERENCES educlaw_section_meeting(id) ON DELETE RESTRICT | Secondary conflicting meeting (nullable — e.g., for overload conflicts) |
| `instructor_id` | TEXT | REFERENCES educlaw_instructor(id) ON DELETE RESTRICT | Nullable — for instructor-related conflicts |
| `room_id` | TEXT | REFERENCES educlaw_room(id) ON DELETE RESTRICT | Nullable — for room-related conflicts |
| `student_id` | TEXT | REFERENCES educlaw_student(id) ON DELETE RESTRICT | Nullable — for student-related conflicts |
| `description` | TEXT | NOT NULL DEFAULT '' | Human-readable conflict description (e.g., "Dr. Jones is double-booked in Period 3 on Day A") |
| `conflict_status` | TEXT | NOT NULL DEFAULT 'open' | See lifecycle below |
| `resolution_notes` | TEXT | NOT NULL DEFAULT '' | What action was taken to resolve |
| `resolved_by` | TEXT | NOT NULL DEFAULT '' | Username who resolved |
| `resolved_at` | TEXT | NOT NULL DEFAULT '' | ISO 8601 timestamp |
| `company_id` | TEXT | NOT NULL, REFERENCES company(id) ON DELETE RESTRICT | Institution |
| `created_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `updated_at` | TEXT | NOT NULL DEFAULT datetime('now') | ISO 8601 |
| `created_by` | TEXT | NOT NULL DEFAULT '' | Username |

**11 Conflict Types:**
```sql
CHECK(conflict_type IN (
  'instructor_double_booking',    -- CRITICAL: two meetings same instructor, same slot
  'room_double_booking',          -- CRITICAL: two meetings same room, same slot
  'student_conflict',             -- HIGH: two requested sections same slot for a student
  'instructor_overload',          -- HIGH: exceeds max_teaching_load_hours
  'instructor_contract_violation',-- HIGH: violates constraint (max consecutive, no prep, unavailable)
  'capacity_exceeded',            -- HIGH: enrollment > room capacity
  'room_type_mismatch',          -- MEDIUM: lab course in non-lab room
  'credential_mismatch',          -- MEDIUM: instructor not certified for course (warn, don't block)
  'singleton_overlap',            -- HIGH: two singleton courses at same slot with shared students
  'contact_hours_deficit',        -- MEDIUM: section contact minutes < required for credit hours
  'room_shortage'                 -- HIGH: no suitable room available for a section's slot
))
```

**Severity mapping (defaults):**
```
CRITICAL: instructor_double_booking, room_double_booking
HIGH: student_conflict, instructor_overload, instructor_contract_violation, capacity_exceeded, singleton_overlap, room_shortage
MEDIUM: room_type_mismatch, credential_mismatch, contact_hours_deficit
```

**Constraints:**
```sql
CHECK(severity IN ('critical','high','medium','low'))
CHECK(conflict_status IN ('open','resolving','resolved','accepted','superseded'))
```

**Conflict lifecycle:**
```
open → resolving → resolved    (conflict fixed by schedule change)
                 → accepted    (acknowledged; irresolvable; master schedule can still publish)
                 → superseded  (original conflict no longer exists due to other schedule changes)
```

**Pre-publish rule:** Master schedule CANNOT be published if any conflict has `severity = 'critical'` AND `conflict_status = 'open'`. Accepted critical conflicts ARE allowed.

**Indexes:**
- `idx_schedule_conflict_master_status_sev` ON `(master_schedule_id, conflict_status, severity)` — primary dashboard query
- `idx_schedule_conflict_master_type` ON `(master_schedule_id, conflict_type)`
- `idx_schedule_conflict_instructor` ON `(instructor_id, conflict_status)`
- `idx_schedule_conflict_room` ON `(room_id, conflict_status)`
- `idx_schedule_conflict_meeting_a` ON `(section_meeting_id_a)`
- `idx_schedule_conflict_company_status` ON `(company_id, conflict_status)`

---

### 3.2 Tables (Inherited from Parent — Read or Referenced)

| Parent Table | Owner | How Scheduling Uses It |
| --- | --- | --- |
| `educlaw_academic_term` | educlaw | `educlaw_master_schedule.academic_term_id` FK; term `status` lifecycle drives scheduling window |
| `educlaw_academic_year` | educlaw | Indirect via `educlaw_academic_term.academic_year_id` |
| `educlaw_section` | educlaw | `educlaw_section_meeting.section_id` FK; scheduling adds meetings on top of sections; publishes schedule by updating `section.status` → 'scheduled' |
| `educlaw_course` | educlaw | `educlaw_course_request.course_id` FK; demand analysis via course metadata (credit_hours, max_enrollment, course_type) |
| `educlaw_instructor` | educlaw | `educlaw_section_meeting.instructor_id` FK; `educlaw_instructor_constraint.instructor_id` FK; `max_teaching_load_hours` used for overload check |
| `educlaw_room` | educlaw | `educlaw_room_booking.room_id` FK; `educlaw_section_meeting.room_id` FK; `capacity`, `room_type`, `facilities` used for assignment logic |
| `educlaw_student` | educlaw | `educlaw_course_request.student_id` FK; student conflict detection |
| `educlaw_course_prerequisite` | educlaw | Read during `submit-course-request` to validate prerequisites |
| `educlaw_program_enrollment` | educlaw | Read to determine student's active program for course request suggestions |
| `company` | erpclaw-setup | `company_id` on ALL scheduling tables |
| `employee` | erpclaw-hr | Indirect via `educlaw_instructor.employee_id` |

**What the parent EduClaw tables NOT extended:**
- `educlaw_section.days_of_week`, `start_time`, `end_time` — remain intact for backward compat with simple sections that don't use the advanced scheduling module
- `educlaw_instructor` — not modified; constraints are additive via `educlaw_instructor_constraint`
- `educlaw_room` — not modified; accessibility attributes are stored on `educlaw_room_booking.accessibility_required` and described in `educlaw_room.facilities` JSON

### 3.3 Lookup / Reference Data (No Seed Tables Required)

The scheduling module uses `CHECK` constraints to enforce valid values rather than separate reference tables (ERPClaw convention). The following enumerated values are validated at the application and database layer:

| Entity | Field | Valid Values |
| --- | --- | --- |
| `educlaw_schedule_pattern` | `pattern_type` | traditional, block_4x4, block_ab, trimester, rotating_drop, semester, custom |
| `educlaw_bell_period` | `period_type` | class, break, lunch, homeroom, advisory, flex, passing |
| `educlaw_master_schedule` | `schedule_status` | draft, building, review, published, locked, archived |
| `educlaw_section_meeting` | `meeting_type` | regular, lab, exam, field_trip, make_up |
| `educlaw_section_meeting` | `meeting_mode` | in_person, hybrid, online |
| `educlaw_room_booking` | `booking_type` | class, exam, event, maintenance, admin, other |
| `educlaw_room_booking` | `booking_status` | confirmed, tentative, cancelled |
| `educlaw_instructor_constraint` | `constraint_type` | unavailable, preferred, max_periods_per_day, max_consecutive_periods, requires_prep_period, preferred_building |
| `educlaw_instructor_constraint` | `priority` | hard, soft, preference |
| `educlaw_course_request` | `request_status` | draft, submitted, approved, scheduled, alternate_used, unfulfilled, withdrawn |
| `educlaw_schedule_conflict` | `conflict_type` | 11 types (see table 9) |
| `educlaw_schedule_conflict` | `severity` | critical, high, medium, low |
| `educlaw_schedule_conflict` | `conflict_status` | open, resolving, resolved, accepted, superseded |

---

## 4. Action List

### 4.1 Actions by Domain

---

#### Domain: `schedule_patterns` (10 actions)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-schedule-pattern` | CRUD | Create a new named schedule pattern (traditional, block, A/B, rotating, etc.) | `educlaw_schedule_pattern` |
| `update-schedule-pattern` | CRUD | Update pattern name, description, notes (NOT cycle_days or pattern_type if already used) | `educlaw_schedule_pattern` |
| `get-schedule-pattern` | Query | Get pattern with all its day types and bell periods | `educlaw_schedule_pattern`, `educlaw_day_type`, `educlaw_bell_period` |
| `list-schedule-patterns` | Query | List all patterns for company, filterable by pattern_type and is_active | `educlaw_schedule_pattern` |
| `add-day-type` | CRUD | Add a day type to a pattern (e.g., "Day A" for A/B block) | `educlaw_day_type` |
| `add-bell-period` | CRUD | Add a named bell period to a pattern (period number, name, start_time, end_time, type, day_types) | `educlaw_bell_period` |
| `activate-schedule-pattern` | Lifecycle | Mark a pattern as active (is_active=1); optionally deactivate the old default | `educlaw_schedule_pattern` |
| `map-day-type-to-dates` | Utility | Generate and store a JSON calendar map of date→day_type for a term (stored in build_notes of master schedule or as a utility response) | `educlaw_master_schedule` (notes field), returns computed mapping |
| `get-pattern-calendar` | Query | Return the full date→day_type mapping for a term given a pattern and term date range | `educlaw_schedule_pattern`, `educlaw_day_type`, `educlaw_academic_term` |
| `calculate-contact-hours` | Utility | Calculate total instructional minutes for a section given its meetings, pattern, and term cycle counts | `educlaw_bell_period`, `educlaw_section_meeting`, `educlaw_day_type` |

---

#### Domain: `master_schedule` (24 actions — includes course requests sub-section)

**Master Schedule Core (15 actions):**

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `create-master-schedule` | CRUD | Create a master schedule document for an academic term, linked to a schedule pattern | `educlaw_master_schedule` |
| `update-master-schedule` | CRUD | Update master schedule name, build_notes, or pattern (only while in draft/building status) | `educlaw_master_schedule` |
| `get-master-schedule` | Query | Get master schedule with summary: section counts, conflict counts, fulfillment_rate, schedule_status | `educlaw_master_schedule`, `educlaw_section_meeting`, `educlaw_schedule_conflict` |
| `list-master-schedules` | Query | List master schedules for company, filterable by schedule_status | `educlaw_master_schedule` |
| `add-section-to-schedule` | CRUD | Create a new `educlaw_section` record (via parent) and attach it to the master schedule; sets section.status='draft' | `educlaw_section` (parent write), `educlaw_master_schedule` (update counter) |
| `place-section-meeting` | CRUD | Assign a section to a specific day_type + bell_period (creates `educlaw_section_meeting`); automatically runs instructor and room double-booking checks; creates conflicts if detected | `educlaw_section_meeting`, `educlaw_schedule_conflict` |
| `remove-section-meeting` | CRUD | Remove a section_meeting record (only when master_schedule is in draft or building status); cancels any linked room_booking; marks superseded conflicts | `educlaw_section_meeting`, `educlaw_room_booking`, `educlaw_schedule_conflict` |
| `list-section-meetings` | Query | List all section meetings for a master schedule or section, filterable by day_type, period, room, instructor | `educlaw_section_meeting` |
| `get-schedule-matrix` | Query | Return the full period grid: for each day_type + period combination, return all placed sections with instructor and room | `educlaw_section_meeting`, `educlaw_day_type`, `educlaw_bell_period` |
| `analyze-course-demand` | Analysis | Calculate sections needed per course from approved course requests: demand count, sections_needed = CEIL(demand / course.max_enrollment), singleton flag | `educlaw_course_request`, `educlaw_course`, `educlaw_academic_term` |
| `get-fulfillment-report` | Report | Calculate and return course fulfillment rate: % of approved course requests that can be satisfied given placed sections; updates `educlaw_master_schedule.fulfillment_rate` | `educlaw_course_request`, `educlaw_section_meeting`, `educlaw_master_schedule` |
| `get-load-balance-report` | Report | Return instructor load distribution (teaching periods per instructor) and section enrollment distribution (variance per course across sections) | `educlaw_section_meeting`, `educlaw_section` (parent), `educlaw_instructor` (parent) |
| `publish-master-schedule` | Lifecycle | Publish the master schedule: validates no open CRITICAL conflicts → updates all draft sections' status to 'scheduled' → updates academic_term.status to 'enrollment_open' → sets schedule_status='published' | `educlaw_master_schedule`, `educlaw_section` (parent write), `educlaw_academic_term` (parent write), `educlaw_schedule_conflict` |
| `lock-master-schedule` | Lifecycle | Lock the master schedule after enrollment begins: sets schedule_status='locked'; prevents section additions or period reassignments without override | `educlaw_master_schedule` |
| `clone-master-schedule` | Utility | Copy a prior term's master schedule sections and meetings as a draft for the new term (requires new academic_term_id); sections are cloned with status='draft'; meetings cloned without room assignments (rooms re-assigned) | `educlaw_master_schedule`, `educlaw_section` (parent write), `educlaw_section_meeting` |

**Course Requests Sub-Section (9 actions):**

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `open-course-requests` | Lifecycle | Open the course request window for an upcoming term: validates term is in 'setup' status; records open window on master schedule build_notes | `educlaw_master_schedule` |
| `submit-course-request` | CRUD | Student or counselor submits a course request: validates prerequisite from `educlaw_course_prerequisite`; warns (does not block) on prerequisite failure unless counselor override provided; checks for duplicate (student+term+course UNIQUE) | `educlaw_course_request`, `educlaw_course_prerequisite` (parent read) |
| `update-course-request` | CRUD | Update request priority, is_alternate, alternate_for_course_id, or has_iep_flag (only while request_status is draft or submitted) | `educlaw_course_request` |
| `get-course-request` | Query | Get a single course request with student, course, status, prerequisite override details | `educlaw_course_request` |
| `list-course-requests` | Query | List course requests, filterable by academic_term_id, student_id, course_id, request_status, is_alternate, has_iep_flag | `educlaw_course_request` |
| `approve-course-requests` | Lifecycle | Counselor batch-approves submitted requests for a term: sets request_status='approved'; records approved_by + approved_at | `educlaw_course_request` |
| `get-demand-report` | Report | Group approved requests by course: total_requests, primary_requests, alternate_requests, sections_needed = CEIL(primary_requests / course.max_enrollment) | `educlaw_course_request`, `educlaw_course` |
| `get-singleton-analysis` | Analysis | Identify singleton courses (likely 1 section) and their student overlap: for each pair of singletons, count shared students — these pairs must be placed in different periods | `educlaw_course_request`, `educlaw_course` |
| `close-course-requests` | Lifecycle | Close the request window: remaining draft requests are marked 'withdrawn'; returns summary (approved count, withdrawn count, demand report) | `educlaw_course_request` |

---

#### Domain: `conflict_resolution` (8 actions)

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `run-conflict-check` | Analysis | Run the full 6-category conflict scan on a master schedule: (1) instructor double-booking, (2) room double-booking, (3) instructor overload, (4) instructor contract violations, (5) capacity exceeded, (6) contact hours deficit; creates new conflict records for detected issues; marks superseded for resolved ones; updates `educlaw_master_schedule.open_conflicts` | `educlaw_section_meeting`, `educlaw_room_booking`, `educlaw_instructor_constraint`, `educlaw_instructor` (parent), `educlaw_room` (parent), `educlaw_schedule_conflict`, `educlaw_master_schedule` |
| `list-conflicts` | Query | List conflicts for a master schedule, filterable by conflict_type, severity, conflict_status | `educlaw_schedule_conflict` |
| `get-conflict` | Query | Get conflict detail: description, both conflicting meetings (with section, course, instructor, room details), suggested resolution options | `educlaw_schedule_conflict`, `educlaw_section_meeting`, `educlaw_section` (parent), `educlaw_instructor` (parent), `educlaw_room` (parent) |
| `resolve-conflict` | Lifecycle | Mark a conflict as resolved: sets conflict_status='resolved', records resolution_notes, resolved_by, resolved_at | `educlaw_schedule_conflict` |
| `accept-conflict` | Lifecycle | Accept an irresolvable conflict: sets conflict_status='accepted'; master schedule may still be published if no OPEN CRITICAL conflicts remain | `educlaw_schedule_conflict` |
| `get-conflict-summary` | Report | Return count of conflicts grouped by severity × status: summary table for the master schedule dashboard | `educlaw_schedule_conflict` |
| `get-singleton-conflict-map` | Analysis | Return the singleton conflict map: for each pair of singleton sections scheduled at the same period+day_type, show shared student count from course requests | `educlaw_section_meeting`, `educlaw_course_request`, `educlaw_course` |
| `get-student-conflict-report` | Report | For each student with approved course requests: check if any two requested courses are scheduled at the same period+day_type; return list of students with conflicts and their conflicting course pairs | `educlaw_course_request`, `educlaw_section_meeting`, `educlaw_section` (parent) |

---

#### Domain: `room_assignment` (14 actions)

**Room Booking (10 actions):**

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `assign-room` | CRUD | Assign a room to a section meeting: validates room available (no confirmed booking for same room+day_type+period), capacity ≥ max_enrollment, room_type matches; creates `educlaw_room_booking` record; updates `educlaw_section_meeting.room_id` | `educlaw_room_booking`, `educlaw_section_meeting`, `educlaw_room` (parent), `educlaw_section` (parent) |
| `suggest-room` | Analysis | Smart room suggestion for a section meeting: filter by availability → capacity → room_type → required features; score by building proximity, utilization rate, accessibility; return top 3 suggestions with scores and reasoning | `educlaw_room_booking`, `educlaw_room` (parent), `educlaw_section_meeting`, `educlaw_section` (parent) |
| `bulk-assign-rooms` | Utility | Auto-assign rooms to all unassigned section meetings in a master schedule: process in priority order (largest enrollment first, then special room requirements, then standard); for each meeting run suggest-room logic and assign top suggestion; return assignment report (assigned count, unassigned count, conflicts created) | `educlaw_room_booking`, `educlaw_section_meeting`, `educlaw_schedule_conflict`, `educlaw_master_schedule` |
| `unassign-room` | CRUD | Remove room assignment from a section meeting: sets `section_meeting.room_id = NULL`; cancels linked `educlaw_room_booking` | `educlaw_section_meeting`, `educlaw_room_booking` |
| `block-room` | CRUD | Mark a room as unavailable for a specific period+day_type (for maintenance, events, exams, etc.): creates `educlaw_room_booking` with `booking_type != 'class'` and `section_meeting_id = NULL` | `educlaw_room_booking` |
| `swap-rooms` | Utility | Swap room assignments between two section meetings in the same period+day_type: validates Section A fits in Room B and Section B fits in Room A; updates both section_meetings and room_bookings atomically | `educlaw_room_booking`, `educlaw_section_meeting`, `educlaw_room` (parent), `educlaw_section` (parent) |
| `get-room-availability` | Query | View all confirmed bookings for a room across all day_types and periods; return a period grid showing BOOKED / AVAILABLE / BLOCKED for each slot | `educlaw_room_booking`, `educlaw_day_type`, `educlaw_bell_period` |
| `get-room-utilization-report` | Report | Per room and per building: % of total class periods where room is confirmed-booked; flag underutilized (<40%) and over-utilized (>95%) rooms | `educlaw_room_booking`, `educlaw_room` (parent), `educlaw_bell_period` |
| `search-rooms-by-features` | Query | Find rooms with specific features available in a given period+day_type: filter by room_type, capacity range, facilities (JSON array match), and availability | `educlaw_room` (parent), `educlaw_room_booking`, `educlaw_day_type`, `educlaw_bell_period` |
| `emergency-reassign-room` | Utility | Bulk reassign all confirmed class bookings for a room to alternate rooms: for each booking, run suggest-room → assign top available suggestion; notify via return value (list of affected sections and their new rooms) | `educlaw_room_booking`, `educlaw_section_meeting`, `educlaw_room` (parent) |

**Instructor Constraints (4 actions):**

| Action | Type | Description | Tables Touched |
| --- | --- | --- | --- |
| `add-instructor-constraint` | CRUD | Add a scheduling constraint for an instructor for a specific term (unavailable, max_periods_per_day, etc.) | `educlaw_instructor_constraint` |
| `update-instructor-constraint` | CRUD | Update constraint value, notes, priority, or is_active | `educlaw_instructor_constraint` |
| `list-instructor-constraints` | Query | List all active constraints for an instructor and/or academic term, filterable by constraint_type and priority | `educlaw_instructor_constraint` |
| `delete-instructor-constraint` | CRUD | Soft-delete an instructor constraint: sets is_active=0 (does not hard-delete; constraint remains in history) | `educlaw_instructor_constraint` |

---

### 4.2 Cross-Domain Actions

| Action | Domains Involved | Description |
| --- | --- | --- |
| `place-section-meeting` | master_schedule + conflict_resolution | Creates `educlaw_section_meeting` AND immediately runs instructor + room double-booking checks, creating conflict records as side effects |
| `publish-master-schedule` | master_schedule + conflict_resolution | Validates no open CRITICAL conflicts (reads conflict_resolution domain) before setting sections to 'scheduled' and academic term to 'enrollment_open' |
| `bulk-assign-rooms` | room_assignment + conflict_resolution | Creates room bookings and immediately creates/clears `room_shortage` conflicts |
| `run-conflict-check` | conflict_resolution + room_assignment | Reads instructor constraints (room_assignment domain) to detect contract violations |
| `get-fulfillment-report` | master_schedule + course requests | Reads course requests (pre-scheduling domain) against placed section meetings (master_schedule domain) |

---

### 4.3 Naming Conflict Check

The following confirms zero naming conflicts between educlaw-scheduling actions and all parent/foundation actions:

**Parent EduClaw actions starting with same verbs (verified distinct):**
- Parent has `add-section` → mine is `add-section-to-schedule` ✓
- Parent has `update-section` → mine is `update-master-schedule` ✓
- Parent has `list-sections` → mine is `list-section-meetings` ✓
- Parent has `get-section` → mine is `get-schedule-matrix` ✓
- Parent has `submit-grades` → mine is `submit-course-request` ✓
- Parent has `add-instructor` → mine is `add-instructor-constraint` ✓
- Parent has `list-instructors` → mine is `list-instructor-constraints` ✓
- Parent has `list-courses` → mine is `list-course-requests` ✓
- Parent has `get-course` → mine is `get-course-request` ✓
- Parent has `update-course` → mine is `update-course-request` ✓
- Parent has `get-teaching-load` → mine is `get-load-balance-report` ✓
- Parent has `add-room` → mine is `block-room`, `assign-room`, `suggest-room` ✓

**Full action list (56 unique actions) — confirmed no duplicates with parent:**
`add-schedule-pattern`, `update-schedule-pattern`, `get-schedule-pattern`, `list-schedule-patterns`, `add-day-type`, `add-bell-period`, `activate-schedule-pattern`, `map-day-type-to-dates`, `get-pattern-calendar`, `calculate-contact-hours`, `create-master-schedule`, `update-master-schedule`, `get-master-schedule`, `list-master-schedules`, `add-section-to-schedule`, `place-section-meeting`, `remove-section-meeting`, `list-section-meetings`, `get-schedule-matrix`, `analyze-course-demand`, `get-fulfillment-report`, `get-load-balance-report`, `publish-master-schedule`, `lock-master-schedule`, `clone-master-schedule`, `open-course-requests`, `submit-course-request`, `update-course-request`, `get-course-request`, `list-course-requests`, `approve-course-requests`, `get-demand-report`, `get-singleton-analysis`, `close-course-requests`, `run-conflict-check`, `list-conflicts`, `get-conflict`, `resolve-conflict`, `accept-conflict`, `get-conflict-summary`, `get-singleton-conflict-map`, `get-student-conflict-report`, `assign-room`, `suggest-room`, `bulk-assign-rooms`, `unassign-room`, `block-room`, `swap-rooms`, `get-room-availability`, `get-room-utilization-report`, `search-rooms-by-features`, `emergency-reassign-room`, `add-instructor-constraint`, `update-instructor-constraint`, `list-instructor-constraints`, `delete-instructor-constraint`

---

## 5. Workflows

### Workflow 1: Define a Schedule Pattern (schedule_patterns domain)

```
Trigger: Administrator defines schedule structure for the institution or a new term

Steps:
1. add-schedule-pattern
   → Input: name, pattern_type, cycle_days, total_periods_per_cycle
   → Output: educlaw_schedule_pattern created (is_active=0 initially)

2. add-day-type (× cycle_days)
   → For A/B Block: 2 calls — code="A", name="Day A" / code="B", name="Day B"
   → For Traditional: 1 call — code="1", name="Day 1"
   → Validation: day count must match cycle_days

3. add-bell-period (× periods per day)
   → For each period: period_number, period_name, start_time, end_time,
     period_type, applies_to_day_types
   → duration_minutes calculated from end_time - start_time
   → Validation: no overlapping times within same day_type

4. activate-schedule-pattern
   → Sets is_active=1
   → Pattern is now available for master schedule creation

5. [Optional] get-pattern-calendar
   → Given academic_term_id, returns date→day_type mapping for the term
   → Administrator reviews and validates the calendar

GL/SLE implications: None — pattern management has no financial impact.
```

---

### Workflow 2: Course Request Demand Analysis (master_schedule domain)

```
Trigger: 8–12 weeks before term start; master schedule building phase begins

Steps:
1. open-course-requests
   → Validates: academic_term.status = 'setup'
   → Returns: request window now open; counselors can enter requests

2. submit-course-request (× N students × N courses)
   → Input: student_id, academic_term_id, course_id, request_priority, is_alternate
   → Validates: course prerequisites from educlaw_course_prerequisite
   → Warns (not blocks) on prerequisite failure; allows counselor override
   → Sets: request_status = 'submitted'
   → UNIQUE constraint prevents duplicate (student + term + course)

3. approve-course-requests
   → Counselor reviews and batch-approves requests for term
   → Sets: request_status = 'approved', approved_by, approved_at

4. get-demand-report
   → Groups approved requests by course
   → Returns: course_name, primary_requests, alternate_requests,
     sections_needed = CEIL(primary_requests / course.max_enrollment)

5. get-singleton-analysis
   → Identifies singleton courses (likely 1 section)
   → Returns: singleton pair matrix with shared_student_count
   → Pairs with shared students must be placed in different periods

6. close-course-requests
   → Remaining drafts marked 'withdrawn'
   → Returns: final demand summary; administrator approves section counts

GL/SLE implications: None — demand analysis has no financial impact.
```

---

### Workflow 3: Build the Master Schedule (master_schedule domain)

```
Trigger: 6–8 weeks before term start; demand report approved; sections to be created

Steps:
1. create-master-schedule
   → Input: academic_term_id, schedule_pattern_id, name, build_notes
   → Validates: academic_term.status = 'setup', pattern is_active = 1
   → Sets: schedule_status = 'draft'

2. add-section-to-schedule (× N sections based on demand report)
   → Creates educlaw_section (parent table) with status = 'draft'
   → Links to master_schedule
   → Priority order: singleton courses first → high demand → standard

3. place-section-meeting (× N meetings per section)
   → Input: section_id, day_type_id, bell_period_id, instructor_id (optional)
   → Creates educlaw_section_meeting record
   → Immediately runs:
     a. Instructor double-booking check → creates conflict if detected
     b. Room double-booking check (if room provided) → creates conflict
   → Returns: meeting created + any new conflicts detected

4. assign-room (for each meeting) OR bulk-assign-rooms
   → Manual: assign-room for each section meeting
   → Automated: bulk-assign-rooms processes all unassigned meetings
   → Creates educlaw_room_booking records
   → Flags room_shortage conflicts if no suitable room found

5. (Update master schedule status)
   → update-master-schedule: schedule_status = 'building'

GL/SLE implications: None — building the schedule has no financial impact.
Note: publish-master-schedule (step below) triggers section status changes
that may trigger fee invoice generation in the parent educlaw fees domain.
```

---

### Workflow 4: Conflict Resolution and Publishing (conflict_resolution + master_schedule domains)

```
Trigger: 4–6 weeks before term; master schedule ready for review

Steps:
1. run-conflict-check
   → Runs all 6 conflict categories:
     (1) instructor_double_booking — O(N²) self-join on section_meeting
     (2) room_double_booking — query room_booking with confirmed status
     (3) instructor_overload — count sections per instructor vs. max_teaching_load_hours
     (4) instructor_contract_violation — check each instructor's active constraints
     (5) capacity_exceeded — section.current_enrollment > room.capacity
     (6) contact_hours_deficit — calculate total minutes per section vs. required
   → Creates/updates educlaw_schedule_conflict records
   → Updates educlaw_master_schedule.open_conflicts counter
   → Sets schedule_status = 'review'

2. get-conflict-summary
   → Returns: count by severity × status
   → Administrator prioritizes: CRITICAL first, then HIGH

3. [Repeat until no CRITICAL open conflicts]
   a. get-conflict → view details + resolution options
   b. For instructor_double_booking:
      → Move one section to different period (remove-section-meeting + place-section-meeting)
      → OR assign different instructor to one section (update-section from parent)
   c. For room_double_booking:
      → Unassign one room (unassign-room) + assign different room (assign-room)
      → OR swap rooms between sections (swap-rooms)
   d. resolve-conflict OR accept-conflict
      → resolve-conflict: records resolution_notes; conflict_status = 'resolved'
      → accept-conflict: acknowledges irresolvable; conflict_status = 'accepted'

4. get-student-conflict-report (requires course requests)
   → Identifies students with conflicting requested courses
   → Administrator adjusts schedule or accepts student conflicts

5. get-fulfillment-report
   → Calculates and stores fulfillment_rate on master_schedule
   → Alert if fulfillment_rate < 90%

6. publish-master-schedule
   → Pre-flight: queries all conflicts with severity='critical' AND conflict_status='open'
   → Blocks if any open CRITICAL conflicts exist
   → Transaction:
     a. UPDATE educlaw_section SET status='scheduled' WHERE ... (all sections in master schedule)
     b. UPDATE educlaw_academic_term SET status='enrollment_open' WHERE id = academic_term_id
     c. UPDATE educlaw_master_schedule SET schedule_status='published', published_at, published_by
   → Returns: publish summary (sections scheduled, term opened)

7. lock-master-schedule (after enrollment window opens)
   → Sets schedule_status = 'locked'
   → Room and instructor substitutions still allowed (room_booking updates)
   → No new section additions or period reassignments

GL/SLE implications:
- publish-master-schedule updates educlaw_section.status → 'scheduled'
- This may trigger tuition invoice generation in parent EduClaw fees domain
  (parent's generate-fee-invoice depends on enrollment, not section scheduling)
- No direct GL entries from scheduling module itself
```

---

### Workflow 5: Mid-Term Room Reassignment (room_assignment domain)

```
Trigger: Room becomes unavailable mid-term (flood, HVAC failure, renovation)

Steps:
1. get-room-availability
   → Identify all confirmed class bookings for the affected room

2. emergency-reassign-room
   → Input: room_id (the unavailable room), master_schedule_id
   → For each confirmed class booking:
     a. Run suggest-room logic for the same period+day_type
     b. Assign top available suggestion → update room_booking + section_meeting.room_id
     c. If no room available → create room_shortage conflict
   → Returns: assignment report with original room, new room, and section for each

3. [Handle unresolved room_shortage conflicts]
   → run-conflict-check to register new room_shortage conflicts
   → resolve-conflict: combine sections, adjust capacity, or temporarily use
     non-standard spaces with documentation

GL/SLE implications: None — room reassignments are operational, not financial.
```

---

## 6. Dependencies

### 6.1 Foundation Skills

| Skill | What We Use | How |
| --- | --- | --- |
| `erpclaw-setup` | `company` table, `naming_series`, `audit` logging | `company_id` FK on all 9 tables; `get_next_name()` for MS-{YEAR} and CRQ-{YEAR} series; `audit()` called on publish and lock lifecycle events |
| `erpclaw-gl` | `get_connection()`, `ensure_db_exists()`, `ok()`, `err()`, `row_to_dict()` | Standard shared lib for DB access and response formatting; no GL entries posted by scheduling module itself |
| `erpclaw-hr` | `employee` table (indirect via educlaw_instructor) | Instructors are HR employees; `educlaw_instructor.employee_id` references `employee.id`; used for instructor display name lookups |
| `erpclaw-selling` | Not directly used | Parent EduClaw uses selling for tuition invoices; scheduling module does not post sales orders or invoices |
| `erpclaw-payments` | Not directly used | Payment processing is parent's domain; scheduling does not process payments |

**Shared library functions used by educlaw-scheduling:**

| Function | Module | Usage |
| --- | --- | --- |
| `get_connection()` | `erpclaw_lib/db.py` | Every action's first call |
| `ensure_db_exists()` | `erpclaw_lib/db.py` | Every action init |
| `ok(data)` | `erpclaw_lib/response.py` | All successful action responses |
| `err(message)` | `erpclaw_lib/response.py` | All error responses |
| `row_to_dict(row)` | `erpclaw_lib/response.py` | Convert SQLite rows to dicts |
| `rows_to_list(rows)` | `erpclaw_lib/response.py` | Convert SQLite row lists |
| `get_next_name()` | `erpclaw_lib/naming.py` | Generate MS-{YEAR}-{SEQ} and CRQ-{YEAR}-{SEQ} |
| `audit()` | `erpclaw_lib/audit.py` | Log publish-master-schedule, lock-master-schedule, resolve-conflict, accept-conflict |
| `check_required_tables()` | `erpclaw_lib/dependencies.py` | Pre-flight check for parent EduClaw tables |
| `resolve_company_id()` | `erpclaw_lib/query_helpers.py` | Resolve company_id from DB when not provided |

### 6.2 Parent EduClaw Dependencies

| Parent Table / Action | Relationship | Notes |
| --- | --- | --- |
| `educlaw_academic_term` | FK reference + status read/write | `master_schedule.academic_term_id` FK; `publish-master-schedule` writes term.status → 'enrollment_open' |
| `educlaw_section` | FK reference + write (add-section-to-schedule, publish-master-schedule) | `section_meeting.section_id` FK; scheduling creates sections (draft) and publishes them (scheduled) |
| `educlaw_course` | FK reference + read | `course_request.course_id` FK; read `credit_hours`, `max_enrollment`, `course_type` for demand and room matching |
| `educlaw_instructor` | FK reference + read | `section_meeting.instructor_id`, `instructor_constraint.instructor_id` FKs; read `max_teaching_load_hours` for overload check |
| `educlaw_room` | FK reference + read | `room_booking.room_id`, `section_meeting.room_id` FKs; read `capacity`, `room_type`, `facilities` for assignment |
| `educlaw_student` | FK reference + read | `course_request.student_id` FK; read for student conflict detection |
| `educlaw_course_prerequisite` | Read only | Read during `submit-course-request` to validate prerequisites |
| `educlaw_program_enrollment` | Read only | Read to suggest eligible courses for a student's course requests |
| `educlaw_course_enrollment` | Read only | Read for capacity_exceeded conflict check (current enrollment vs. room capacity) |
| Parent action `activate-section` | Coordination | Called by parent; scheduling's `publish-master-schedule` updates section.status directly via SQL (bypasses parent action to maintain transaction integrity) |

### 6.3 Required Table Check (init_db.py)

Before creating scheduling tables, `init_db.py` must verify these parent tables exist:
```python
REQUIRED_PARENT_TABLES = [
    'educlaw_academic_term',
    'educlaw_academic_year',
    'educlaw_section',
    'educlaw_course',
    'educlaw_instructor',
    'educlaw_room',
    'educlaw_student',
    'company',
]
```

---

## 7. Test Strategy

### 7.1 Unit Tests (per domain)

#### schedule_patterns domain
| Test | Scenario |
| --- | --- |
| `test_add_traditional_pattern` | Create a Traditional 7-period pattern; add 7 bell periods; add 1 day type; activate; verify total_periods_per_cycle |
| `test_add_ab_block_pattern` | Create A/B Block pattern with 2 day types and 4 class periods per day type; verify applies_to_day_types JSON handling |
| `test_bell_period_overlap_rejected` | Attempt to add a period with start_time within existing period → should fail validation |
| `test_duplicate_day_type_code_rejected` | Attempt to add a second day type with code="A" to a pattern that already has code="A" → UNIQUE constraint violation |
| `test_duplicate_period_number_rejected` | Attempt to add a second period with period_number="1" to a pattern → UNIQUE constraint violation |
| `test_calculate_contact_hours` | MWF section in 50-min periods, 15-week semester → expect 50×3×15 = 2,250 minutes = 37.5 hours |
| `test_get_pattern_calendar` | A/B Block pattern, 10-week term → verify alternating Day A/Day B assignment |
| `test_activate_pattern` | Activate pattern; verify is_active=1 |

#### master_schedule domain
| Test | Scenario |
| --- | --- |
| `test_create_master_schedule` | Create master schedule for term; verify naming_series = MS-{year}-001 |
| `test_unique_master_schedule_per_term` | Attempt to create second master schedule for same term → UNIQUE constraint failure |
| `test_place_section_meeting_creates_conflict_on_double_booking` | Place two section meetings with same instructor, same slot → both meetings created, conflict record created with severity=CRITICAL |
| `test_place_section_meeting_room_conflict` | Place two meetings in same room, same slot → room conflict created |
| `test_remove_section_meeting_cancels_booking` | Place meeting with room → remove meeting → verify room_booking.booking_status='cancelled' |
| `test_clone_master_schedule` | Clone prior term's master schedule; verify sections created with status='draft' and no room assignments |
| `test_analyze_course_demand` | 60 students request MATH-101, max_enrollment=30 → sections_needed = 2 |
| `test_singleton_analysis` | Course X (30 requests) and Course Y (25 requests) with 15 shared students → marked as singleton pair with shared_count=15 |
| `test_submit_course_request_prerequisite_check` | Student requests MATH-201 without MATH-101 completed → warning returned; not blocked if no override |
| `test_submit_course_request_duplicate_rejected` | Same student submits same course for same term twice → UNIQUE constraint failure |
| `test_publish_blocked_by_critical_conflict` | Open CRITICAL conflict exists → publish-master-schedule returns error |
| `test_publish_succeeds_with_accepted_critical` | CRITICAL conflict accepted → publish-master-schedule succeeds; sections set to 'scheduled' |
| `test_publish_updates_term_status` | publish-master-schedule → educlaw_academic_term.status = 'enrollment_open' |

#### conflict_resolution domain
| Test | Scenario |
| --- | --- |
| `test_run_conflict_check_instructor_double_booking` | Two meetings with same instructor, same slot → run-conflict-check creates/finds instructor_double_booking conflict |
| `test_run_conflict_check_instructor_overload` | Instructor assigned 7 sections, max_teaching_load_hours = 5 periods → instructor_overload conflict created |
| `test_run_conflict_check_contract_violation` | Instructor has unavailable constraint for Period 1 Day A; section assigned to that slot → instructor_contract_violation conflict |
| `test_run_conflict_check_contact_hours_deficit` | Section has 2 meetings × 50 min × 15 cycles = 1,500 min vs. required 2,250 min for 3 credit hours → contact_hours_deficit conflict |
| `test_resolve_conflict` | Open conflict → resolve-conflict with notes → conflict_status='resolved' |
| `test_accept_conflict` | Open critical conflict → accept-conflict → conflict_status='accepted'; publish allowed |
| `test_superseded_conflict_on_meeting_remove` | Two meetings cause instructor conflict; remove one meeting → run-conflict-check → conflict marked 'superseded' |
| `test_get_student_conflict_report` | Student requests MATH and ENGLISH, both placed in Period 3 Day A → appears in student conflict report |

#### room_assignment domain
| Test | Scenario |
| --- | --- |
| `test_assign_room_success` | Assign available room to meeting; verify section_meeting.room_id updated and room_booking.booking_status='confirmed' |
| `test_assign_room_already_booked` | Assign room that already has confirmed booking for same slot → error returned |
| `test_assign_room_capacity_check` | Room capacity 25, section max_enrollment 30 → capacity_exceeded conflict created |
| `test_suggest_room_returns_ranked_list` | Suggest room for meeting; verify returned rooms are available, sorted by score |
| `test_swap_rooms` | Section A in Room 101 Period 3, Section B in Room 201 Period 3; swap → verify both updated |
| `test_emergency_reassign_room` | Room 101 has 3 class bookings; emergency-reassign-room → all 3 reassigned to available rooms |
| `test_block_room` | Block Room 201 Period 1 Day A for maintenance; verify room_booking created with booking_type='maintenance' |
| `test_add_instructor_constraint_unavailable` | Add unavailable constraint for Period 1 Day A; verify run-conflict-check detects violation when section assigned there |
| `test_bulk_assign_rooms` | Master schedule with 10 unassigned meetings; bulk-assign-rooms → verify assignments made and room_shortage conflicts created for any unresolvable |

### 7.2 Integration Tests

| Test | Description |
| --- | --- |
| `test_full_scheduling_workflow` | End-to-end: create pattern → create master schedule → add sections → place meetings → assign rooms → run conflict check → publish → verify term status = enrollment_open and sections status = scheduled |
| `test_course_request_to_fulfillment` | Submit 100 course requests → approve → close requests → create master schedule → add sections → place meetings → get-fulfillment-report → verify fulfillment_rate > 0 and stored on master_schedule |
| `test_conflict_resolution_workflow` | Create double-booking conflict → list conflicts (CRITICAL) → resolve conflict (move meeting) → run-conflict-check → verify conflict superseded → publish succeeds |
| `test_clone_and_modify` | Clone prior term master schedule → update pattern → place new meetings → verify cloned sections have draft status and no room assignments |
| `test_room_assignment_with_smart_suggestion` | Create section requiring lab room; suggest-room → verify only lab rooms returned; assign suggested room; verify booking created |
| `test_singleton_placement` | Two singleton courses with 20 shared students; place both in Period 3 Day A → singleton_overlap conflict detected; move one → conflict resolved; get-singleton-conflict-map shows no remaining overlaps |

### 7.3 Invariants

These must hold at all times; test explicitly:

| Invariant | Description |
| --- | --- |
| **One master schedule per term** | `UNIQUE (academic_term_id)` on educlaw_master_schedule |
| **One meeting per section per slot** | `UNIQUE (section_id, day_type_id, bell_period_id)` on educlaw_section_meeting |
| **One active booking per room per slot** | Application enforces: no two confirmed bookings for (room_id, day_type_id, bell_period_id) |
| **No publish with open CRITICAL conflicts** | publish-master-schedule returns err() if `SELECT COUNT(*) FROM educlaw_schedule_conflict WHERE master_schedule_id=? AND severity='critical' AND conflict_status='open'` > 0 |
| **One request per student per course per term** | `UNIQUE (student_id, academic_term_id, course_id)` on educlaw_course_request |
| **Day type codes unique per pattern** | `UNIQUE (schedule_pattern_id, code)` on educlaw_day_type |
| **Period numbers unique per pattern** | `UNIQUE (schedule_pattern_id, period_number)` on educlaw_bell_period |
| **bell_period.duration_minutes > 0** | `CHECK(duration_minutes > 0)` enforced at DB level |
| **contact_hours = SUM(duration_minutes × occurrences)** | Application calculates and validates; conflict_type=contact_hours_deficit triggers when < required |
| **Status field naming** | All status fields use domain-specific names (`schedule_status`, `conflict_status`, `request_status`, `booking_status`) — never `status` — to avoid ERPClaw `ok()` response wrapper collision |

---

## 8. Estimated Complexity

| Domain | Tables | Actions | Estimated Lines | Priority | Build Order |
| --- | --- | --- | --- | --- | --- |
| `schedule_patterns` | 3 (`schedule_pattern`, `day_type`, `bell_period`) | 10 | ~400 | P0 | 1st — foundation; nothing works without patterns |
| `master_schedule` (core) | 1 (`master_schedule`) + uses `section_meeting` | 15 | ~700 | P0 | 2nd — create/list/get/place/publish lifecycle |
| `conflict_resolution` | 1 (`schedule_conflict`) | 8 | ~500 | P0 | 3rd — conflict detection runs after place-section-meeting |
| `room_assignment` (bookings) | 1 (`room_booking`) | 10 | ~450 | P1 | 4th — formalize room tracking; smart suggestions |
| `room_assignment` (constraints) | 1 (`instructor_constraint`) | 4 | ~150 | P1 | 5th — extends conflict detection with contract checks |
| `master_schedule` (course requests) | 1 (`course_request`) | 9 | ~350 | P1 | 6th — demand analysis + prerequisite validation |
| **schema (init_db.py)** | 9 | — | ~250 | P0 | 0th — all tables first |
| **SKILL.md** | — | 56 | ~200 | P0 | Last — after all actions implemented |
| **Tests** | — | — | ~800 | P0 | After each domain |
| **Total** | **9** | **56** | **~3,800** | | |

### Recommended Build Order

```
1. Schema — init_db.py with all 9 tables + indexes + constraints
2. schedule_patterns — add/get/list/add-day-type/add-bell-period/activate/calculate-contact-hours
3. master_schedule (core CRUD) — create/update/get/list/add-section-to-schedule
4. section_meeting placement — place-section-meeting/remove-section-meeting/list-section-meetings (with immediate conflict detection on double-booking)
5. conflict_resolution — run-conflict-check (all 6 categories)/list/get/resolve/accept/summary
6. room_assignment (bookings) — assign/suggest/unassign/block/swap/get-availability/utilization/search/emergency
7. master_schedule lifecycle — publish/lock/clone/get-fulfillment-report/get-schedule-matrix/get-load-balance-report
8. room_assignment (constraints) — add/update/list/delete instructor-constraint; extend run-conflict-check with contract violation check
9. course requests — open/submit/update/get/list/approve/get-demand/get-singleton/close
10. cross-domain — analyze-course-demand, get-fulfillment-report (full implementation with course request data)
11. Tests — write tests after each domain
12. SKILL.md — document all 56 actions
```

### v2 Feature Backlog (Out of Scope for v1)

| Feature | Description |
| --- | --- |
| Auto-generate schedule | Greedy + optimization algorithm: place singletons → high demand → standard; v2 differentiator |
| Student auto-loading | Auto-assign students to sections based on course requests (PowerScheduler Student Loader equivalent) |
| Ed-Fi API export | Expose master schedule in Ed-Fi standard for state reporting |
| Holiday calendar | Track non-instructional days; subtract from day-type cycle counts for accurate contact hours |
| Exam scheduling | Separate exam period scheduling at term end |
| IEP placement constraints | Student-level scheduling constraints from IEP data (IDEA compliance) |
| Schedule comparison | Save and compare multiple draft master schedules before choosing one |
| Multi-building travel time | Consider building travel time between consecutive periods in conflict detection |
| Substitute management | Real-time instructor substitution workflow during active term |

---

*Plan prepared: 2026-03-05*
*Parent product analyzed: EduClaw (32 tables, 112 actions, 8 domains)*
*Competitors studied: FET, Gibbon, ERPNext Education, PowerSchool PowerScheduler, Infinite Campus, aSc TimeTables, Rediker, Schedule25/CollegeNET, SchoolInsight/TeacherEase*
*Compliance addressed: ESSA/Carnegie Unit (contact hours), IDEA/IEP (scheduling flags), Section 504 (accessibility), Teacher Contract Hours (instructor constraints), FERPA (schedule data as education record), ADA (room accessibility flags), Title IX (no gender restrictions)*
