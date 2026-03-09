# EduClaw Advanced Scheduling — Core Business Workflows

## Overview

EduClaw Advanced Scheduling introduces 4 interconnected domain modules built on top of the parent EduClaw system:

1. **master_schedule** — Build and manage the term-level master schedule
2. **schedule_patterns** — Define reusable scheduling structures (bell periods, day types)
3. **conflict_resolution** — Detect, track, and resolve scheduling conflicts
4. **room_assignment** — Assign and optimize room bookings for sections

Workflows follow ERPClaw's document lifecycle: **Draft → Submit/Publish → Lock → (Cancel if needed)**

---

## Domain 1: Schedule Pattern Management

### Purpose
Define the scheduling structure an institution uses. A pattern specifies how many days are in a cycle, what those days are called, what periods exist in each day, and how long each period lasts. Patterns are reusable across terms.

### Workflow 1.1: Create a Schedule Pattern

```
1. Define Pattern Metadata
   ├── Input: name, description, pattern_type
   │   ├── pattern_type options: traditional, block_4x4, block_ab, trimester, rotating_drop, semester, custom
   ├── Input: cycle_days (how many unique day types in one cycle)
   │   ├── Traditional: cycle_days = 1 (same structure every day)
   │   ├── A/B Block: cycle_days = 2 (Day A, Day B)
   │   ├── Rotating Drop (7-period): cycle_days = 7 (one day per period rotation)
   ├── Input: total_periods_per_day
   └── Status: DRAFT

2. Define Day Types (for each day in the cycle)
   ├── Example for A/B Block:
   │   ├── Day A: Mon, Wed, Fri of week 1; Tue, Thu of week 2
   │   └── Day B: Tue, Thu of week 1; Mon, Wed, Fri of week 2
   ├── Input per day type: code (A, B, 1-7), name ("Day A", "Day B"), sort_order
   └── Validation: day count matches cycle_days

3. Define Bell Periods (for each period in a day)
   ├── Input per period:
   │   ├── period_number (1, 2, 3... or A, B, C...)
   │   ├── period_name ("Period 1", "Block A", "Homeroom")
   │   ├── start_time, end_time (24-hour ISO format)
   │   ├── period_type: class | break | lunch | homeroom | advisory | flex
   │   ├── applies_to_day_types: [] (which day types have this period — all or subset)
   │   └── duration_minutes (calculated: end_time - start_time)
   ├── Validation: no overlapping periods in the same day type
   ├── Validation: sum of class periods matches expected instructional time
   └── Periods can vary between day types (e.g., A days have 4 blocks, B days have 4 blocks)

4. Activate Pattern
   ├── Review: total instructional minutes per day type
   ├── Review: meeting pattern compliance (Carnegie unit check)
   └── Status: ACTIVE (available for use in master schedules)
```

### Workflow 1.2: Apply Pattern to Term

```
1. Activate pattern for an academic term
   ├── Master schedule creation selects this pattern
   └── Day types are mapped to actual calendar dates in the term

2. Calendar Mapping
   ├── For each week in the term:
   │   ├── Map each calendar date to a day type
   │   ├── Example A/B: Mon → Day A, Tue → Day B, Wed → Day A...
   │   ├── Handle exceptions: holidays, professional development days (no day type)
   └── Result: a calendar table of date → day_type mappings

3. Total Contact Days per Day Type
   ├── Calculate: how many times each day type occurs in the term
   ├── Used to validate total contact hours per section
   └── Alert if any day type has significantly fewer meetings (schedule inequity)
```

### Status Lifecycle: Schedule Pattern
```
DRAFT → ACTIVE → DEPRECATED (replaced by newer version)
```

---

## Domain 2: Master Schedule Building

### Purpose
Build the master schedule for an academic term: which course sections will be offered, when they will meet (period + day type), who will teach them, and in which room.

### Workflow 2.1: Initialize Master Schedule

```
1. Create Master Schedule Document
   ├── Input: name (e.g., "Fall 2026 Master Schedule")
   ├── Input: academic_term_id (must be in status 'setup')
   ├── Input: schedule_pattern_id (the pattern for this term)
   ├── Input: build_notes (planning assumptions)
   └── Status: DRAFT

2. Load Demand Data
   ├── Pull all active course requests for this term:
   │   SELECT student_id, course_id, priority, is_alternate
   │   FROM educlaw_course_request WHERE term_id = ?
   ├── Calculate demand per course:
   │   SELECT course_id, COUNT(*) as demand, COUNT(*)/max_section_size as sections_needed
   ├── Identify singletons: courses where likely only 1 section will be offered
   ├── Output: Demand Report showing sections needed per course
   └── Counselor reviews and approves proposed section counts

3. Load Constraint Data
   ├── Active instructors with max_teaching_load_hours
   ├── Instructor constraints (unavailable periods, preferences)
   ├── Room inventory: capacity, room_type, facilities
   ├── Course requirements: room_type preferences, lab requirements
   └── Output: Constraint Summary for review
```

### Workflow 2.2: Build Sections from Demand

```
1. Create Course Sections
   ├── For each course with confirmed demand:
   │   ├── Create N sections in educlaw_section (parent table)
   │   │   ├── section_number, course_id, academic_term_id
   │   │   ├── max_enrollment (from course demand / sections needed)
   │   │   └── Status: DRAFT
   │   └── Attach to master schedule
   ├── Singleton courses are flagged: must not overlap in period/day_type

2. Assign Instructors to Sections
   ├── For each section:
   │   ├── Select eligible instructors (department match, credential match)
   │   ├── Check teaching load: would this assignment exceed max_teaching_load_hours?
   │   ├── Check existing assignments: would this create a time conflict?
   │   ├── Check instructor constraints: is the instructor unavailable this period?
   │   ├── IF all checks pass → assign instructor
   │   └── IF any check fails → flag as unresolved (workflow passes to conflict resolution)
   └── Decision Point: Can auto-assign run? Or does counselor manually assign?

3. Place Sections in Period/Day-Type Slots
   ├── For each section, assign one or more section meetings:
   │   ├── Input per meeting: section_id, day_type_id, period_id
   │   ├── Meeting repeat: if course meets MWF, create 3 section_meeting records
   │   │   (one per day type occurrence in the cycle)
   │   ├── Validate: instructor not assigned to another section this period + day_type
   │   ├── Validate: room not booked for this period + day_type
   │   └── Status: PLACED
   ├── Priority order: singletons first → high demand → standard
   └── Conflict check runs automatically on each placement

4. Assign Rooms to Section Meetings
   ├── For each section meeting without a room:
   │   ├── Filter rooms: room_type matches course_type (lab for lab courses)
   │   ├── Filter rooms: capacity ≥ section max_enrollment
   │   ├── Filter rooms: not already booked for this period + day_type
   │   ├── Score remaining rooms by: utilization rate, building preference, proximity
   │   ├── Assign: highest-scoring available room
   │   └── Create room_booking record
   ├── Handle conflicts: if no suitable room available
   │   └── Flag as conflict: ROOM_SHORTAGE
   └── Status: ROOM_ASSIGNED

5. Contact Hours Validation
   ├── For each section, calculate total contact minutes:
   │   total_minutes = SUM(meeting_duration_minutes × occurrences_per_cycle × cycles_in_term)
   ├── Compare to required contact hours from course.credit_hours
   ├── Alert if: total_contact_minutes < required_contact_minutes
   └── Alert if: total_contact_minutes > required_contact_minutes + 10% (over-scheduled)
```

### Workflow 2.3: Review and Publish Master Schedule

```
1. Conflict Analysis (see Domain 3 for detail)
   ├── Run full conflict check on the draft master schedule
   ├── Output: conflict_report with all open conflicts
   └── Administrator reviews and resolves conflicts

2. Fulfillment Analysis (requires course requests)
   ├── For each student with course requests:
   │   ├── Check: does the student's schedule have a conflict?
   │   │   (two requested sections meeting at same period + day_type)
   │   └── Mark: fulfilled / unfulfilled per request
   ├── Calculate: overall course fulfillment rate (%)
   ├── Alert if: fulfillment rate < 90% (investigate)
   └── Report: students with unmet requests (manual intervention needed)

3. Load Balancing Review
   ├── Section size distribution per course:
   │   ├── Are all sections of same course similarly sized?
   │   └── Flag: sections with enrollment < 50% capacity (consider cancelling)
   ├── Instructor load distribution:
   │   ├── Teaching periods per instructor across term
   │   └── Flag: instructors significantly over or under average load
   └── Room utilization report:
       ├── Average % capacity used per room
       └── Flag: rooms consistently at <50% or >95% capacity

4. Publish Master Schedule
   ├── Administrator approves: all conflicts resolved, acceptable fulfillment rate
   ├── Mark all sections: status → SCHEDULED (from DRAFT)
   ├── Publish to academic term: status → ENROLLMENT_OPEN
   ├── Notify: instructors of their schedules
   ├── Notify: counselors to begin student enrollment
   └── Status: PUBLISHED

5. Lock Master Schedule
   ├── After enrollment period begins, lock the master schedule
   ├── Locked: no new sections, no period changes without override
   ├── Allow: room/instructor substitutions with approval
   └── Status: LOCKED
```

### Status Lifecycle: Master Schedule
```
DRAFT → BUILDING → REVIEW → PUBLISHED → LOCKED → ARCHIVED (end of term)
                                        ↓
                              (mid-term: ACTIVE adjustments allowed with override)
```

---

## Domain 3: Conflict Resolution

### Purpose
Proactively detect, categorize, track, and resolve scheduling conflicts during master schedule building and throughout the term.

### Conflict Types

| Conflict Type | Trigger | Severity | Description |
|--------------|---------|----------|-------------|
| `instructor_double_booking` | Two section meetings assigned same instructor, same period, same day_type | CRITICAL | Hard block — must resolve before publish |
| `room_double_booking` | Two section meetings assigned same room, same period, same day_type | CRITICAL | Hard block — must resolve before publish |
| `student_conflict` | Two sections in a student's request list meet at same period, same day_type | HIGH | Prevents student from getting both requested courses |
| `instructor_overload` | Instructor assigned more sections than max_teaching_load allows | HIGH | Contract violation risk |
| `instructor_contract_violation` | Instructor's schedule violates contract terms (max consecutive, no prep period, etc.) | HIGH | Legal/labor risk |
| `capacity_exceeded` | Section enrollment exceeds room capacity | HIGH | Safety and compliance issue |
| `room_type_mismatch` | Lab course assigned to non-lab room | MEDIUM | Functional issue |
| `credential_mismatch` | Instructor assigned to course outside their certification area | MEDIUM | Compliance risk (warn, not block) |
| `singleton_overlap` | Two singleton courses scheduled at same period (shared students) | HIGH | Students cannot take both |
| `contact_hours_deficit` | Section total contact minutes < required for credit hours | MEDIUM | Accreditation risk |
| `room_shortage` | No suitable room available for a section's period assignment | HIGH | Section cannot be placed |

### Workflow 3.1: Automatic Conflict Detection

```
Trigger: Any of the following events
├── Section meeting created or modified
├── Instructor assigned to section
├── Room booked for section meeting
└── Manual: "Run Conflict Check" action

Process:
1. Instructor Double-Booking Check
   ├── Query: any section_meeting with same instructor_id, period_id, day_type_id?
   └── If found → create conflict record (type: instructor_double_booking, severity: CRITICAL)

2. Room Double-Booking Check
   ├── Query: any room_booking with same room_id, period_id, day_type_id?
   └── If found → create conflict record (type: room_double_booking, severity: CRITICAL)

3. Student Conflict Check (batch process)
   ├── For each student with course requests in this term:
   │   ├── Get all sections the student is linked to (or likely to enroll in)
   │   ├── Check: do any two sections share a period + day_type?
   │   └── If found → create conflict record (type: student_conflict, severity: HIGH)
   └── Run ONLY after sections are placed in periods

4. Instructor Overload Check
   ├── Calculate: total section meetings per instructor per cycle day / week
   ├── Compare to: max_teaching_load_hours from educlaw_instructor
   └── If exceeded → create conflict record (type: instructor_overload, severity: HIGH)

5. Instructor Contract Violation Check
   ├── For each instructor with active constraints:
   │   ├── Check max_consecutive_periods: count consecutive teaching periods
   │   ├── Check requires_prep_period: does instructor have at least one free period?
   │   ├── Check unavailable_period_day_type combinations
   │   └── Flag each violation as a separate conflict record
   └── Severity: HIGH

6. Contact Hours Check
   ├── For each section, calculate total contact minutes
   ├── Compare to course credit hours × required minutes per credit
   └── If deficit > 5% → create conflict record (type: contact_hours_deficit, severity: MEDIUM)
```

### Workflow 3.2: Conflict Resolution Process

```
1. View Open Conflicts
   ├── Dashboard: count by type and severity
   ├── Filter: CRITICAL first → HIGH → MEDIUM
   └── List: each conflict with section_a, section_b, instructor/room, conflict_type, severity

2. Resolve Conflict
   ├── For instructor_double_booking:
   │   ├── Option A: Move section A to different period
   │   ├── Option B: Assign different instructor to section A or B
   │   └── Option C: Merge sections (if demand allows)
   │
   ├── For room_double_booking:
   │   ├── Option A: Assign different room to section A or B
   │   ├── Option B: Move section A to different period
   │   └── Option C: Find room with adequate capacity + right type
   │
   ├── For student_conflict (two requested sections same period):
   │   ├── Option A: Move one section to different period
   │   ├── Option B: Add another section of one course at different period
   │   └── Option C: Accept conflict (student must choose one) — mark as ACCEPTED
   │
   ├── For instructor_overload:
   │   ├── Option A: Remove one section from instructor → reassign
   │   └── Option B: Request exception (update max_teaching_load)
   │
   └── For contact_hours_deficit:
       ├── Option A: Add another meeting to section
       ├── Option B: Extend meeting duration
       └── Option C: Document exception (certain courses have waiver)

3. Document Resolution
   ├── Update conflict record: status → RESOLVED
   ├── Record: resolution_notes (what action was taken)
   ├── Record: resolved_by (user who resolved)
   ├── Record: resolved_at (timestamp)
   └── Automatically re-run conflict check to verify resolution didn't create new conflicts

4. Accept Conflict (if irresolvable)
   ├── Some conflicts cannot be resolved (scheduling constraints are genuinely incompatible)
   ├── Mark: conflict_status → ACCEPTED
   ├── Record: acceptance_reason
   └── Master schedule CAN be published with ACCEPTED conflicts (but not OPEN CRITICAL conflicts)

5. Pre-Publish Validation
   ├── Block publish if: any CRITICAL conflict is OPEN (unresolved + not accepted)
   ├── Warn if: any HIGH conflict is OPEN
   ├── Allow publish: if all CRITICAL conflicts are RESOLVED or ACCEPTED
   └── Generate: final conflict report for administrative records
```

### Status Lifecycle: Schedule Conflict
```
OPEN (detected) → RESOLVING (being worked on) → RESOLVED (fixed)
                                               → ACCEPTED (acknowledged, cannot fix)
                                               → SUPERSEDED (original conflict no longer exists due to other changes)
```

---

## Domain 4: Room Assignment

### Purpose
Formally manage room bookings for sections and special events, provide room utilization analytics, and enable smart room assignment optimization.

### Workflow 4.1: Assign Room to Section Meeting

```
1. Manual Room Assignment
   ├── Administrator selects: section_meeting + room
   ├── System checks:
   │   ├── Room available for this period + day_type? (query room_booking)
   │   ├── Room capacity ≥ section max_enrollment?
   │   ├── Room type matches course type? (lab course → lab room)
   │   └── Room features match course requirements? (projector, computers, etc.)
   ├── IF all pass → create room_booking record → assign room to section_meeting
   └── IF any fail → display conflict details → allow override with justification

2. Suggested Room Assignment (Smart)
   ├── Trigger: "Suggest Room" for a section meeting
   ├── Algorithm:
   │   a. Filter: available rooms (not booked for this period + day_type)
   │   b. Filter: capacity ≥ max_enrollment
   │   c. Filter: room_type matches (if lab course → lab rooms only)
   │   d. Filter: required features present (projector, computers, etc.)
   │   e. Score remaining rooms:
   │       ├── Proximity score: same building as instructor's other sections (+10)
   │       ├── Utilization score: prefers rooms at 70-85% capacity utilization
   │       ├── Dept preference: same building as course's department (+5)
   │       └── Accessibility: +15 if section has student with accessibility needs
   │   f. Sort by score DESC
   │   g. Return top 3 suggestions with reasoning
   └── Administrator selects from suggestions or overrides

3. Bulk Room Assignment
   ├── After all sections are placed in periods, run bulk room assignment
   ├── Process sections in priority order:
   │   ├── Priority 1: Largest enrollment sections first (harder to accommodate)
   │   ├── Priority 2: Special room requirements (labs, computer rooms)
   │   └── Priority 3: Standard sections (flexible room assignment)
   ├── For each section: run Suggested Room logic → auto-assign top suggestion
   ├── Flag sections with no suitable room as ROOM_SHORTAGE conflicts
   └── Result: assignment report (% sections assigned, unresolved count)
```

### Workflow 4.2: Room Availability Management

```
1. Block Rooms from Scheduling
   ├── Rooms may be unavailable for:
   │   ├── Renovation / maintenance
   │   ├── Special events (graduation, exams, community use)
   │   └── Administrative use (board meetings, staff training)
   ├── Create room_booking with booking_type = NON_CLASS
   ├── Room booking conflicts automatically prevent section assignment

2. View Room Availability
   ├── Visual: period grid for a room showing:
   │   ├── BOOKED: section or non-class booking
   │   ├── AVAILABLE: free for assignment
   │   └── BLOCKED: maintenance/event
   └── Filter by: date range, day type, building

3. Room Utilization Report
   ├── Per room: % of class periods where room is used
   ├── Per building: average utilization
   ├── Flag: underutilized rooms (< 40% across term) — candidate for repurposing
   ├── Flag: overcrowded rooms (> 95%) — capacity relief needed
   └── Export: CSV for facilities management

4. Room Feature Search
   ├── "Find all rooms with computers and projector available in Period 3 on Day A"
   ├── Used by instructors to book specialized rooms for specific activities
   └── Results: available rooms with matching features, capacity range
```

### Workflow 4.3: Mid-Term Room Changes

```
1. Instructor requests room change (mid-term)
   ├── Current section meeting → new room requested
   ├── System checks new room availability
   ├── IF available → update room_booking → update section_meeting
   └── IF not available → suggest alternatives

2. Emergency Room Reassignment
   ├── Trigger: room becomes unavailable (flood, HVAC failure, etc.)
   ├── Identify: all section_meetings in that room
   ├── For each meeting: suggest alternate rooms available for same period + day_type
   ├── Send notification to affected instructors
   └── Update bookings + section_meetings

3. Room Swap Between Two Sections
   ├── Section A (in Room 101, Period 3) and Section B (in Room 201, Period 3)
   ├── Swap their room assignments
   ├── Validate: Section A fits in Room 201, Section B fits in Room 101
   └── Update both room_booking records and section_meeting records
```

---

## Domain 5: Course Request Management (Pre-Scheduling)

### Purpose
Collect student course requests before the master schedule is built. Requests drive demand analysis, section count decisions, and conflict matrix analysis.

### Workflow 5.1: Collect Course Requests

```
1. Open Course Request Window
   ├── Administrator opens course request period:
   │   ├── Set: request_open_date, request_close_date
   │   ├── Set: academic_term_id (the upcoming term)
   │   └── Set: max_requests_per_student (e.g., 7 primary + 3 alternates)

2. Student/Counselor Submits Requests
   ├── For each student:
   │   ├── Select courses from course catalog (filtered by grade level + program)
   │   ├── Assign priority to each request (1 = highest)
   │   ├── Designate alternates: "If MATH-401 isn't available, give me MATH-300"
   │   ├── System validates: prerequisites met for each requested course
   │   │   └── If prerequisite not met → warn, allow override with counselor note
   │   └── Submit requests

3. Counselor Review
   ├── Review all students' requests
   ├── Approve / modify as needed
   ├── Batch override: assign a specific course to all students in a grade
   └── Close request window at deadline
```

### Workflow 5.2: Demand Analysis

```
1. Generate Course Demand Report
   ├── For each course: count of requests (primary + alternate weighted)
   ├── Sort: highest demand to lowest
   ├── Calculate: sections needed = CEILING(request_count / target_section_size)
   └── Output: Demand Summary for master schedule planning

2. Singleton Analysis
   ├── Identify courses likely offered as single sections (low demand or specialized)
   ├── Run conflict matrix: which pairs of singletons share students?
   ├── Singletons with shared students MUST be placed in different periods
   └── Output: Singleton Conflict Map (critical constraint for schedule building)

3. Request Feasibility Check
   ├── For each student: can all N requested courses physically fit in N periods?
   ├── Student's max: unique periods per cycle
   ├── If student requests more courses than available periods → warn
   └── Output: Students with over-requested schedules (counseling needed)

4. Section Size Recommendations
   ├── Based on demand and available rooms:
   │   ├── Under-demanded courses: consider not offering or combining
   │   ├── Over-demanded courses: plan 2-3 sections
   │   └── Singletons: flag for priority placement
   └── Counselor approves final section count plan
```

### Status Lifecycle: Course Request
```
DRAFT → SUBMITTED → APPROVED (by counselor) → SCHEDULED (placed in section)
                                             → ALTERNATE_USED (primary failed, alternate placed)
                                             → UNFULFILLED (neither primary nor alternate placed)
```

---

## 6. End-to-End Scheduling Workflow Map

```
PHASE 1: PATTERN SETUP (1-2 weeks, usually done once per year or once per school)
│
├── Create Schedule Pattern (traditional/block/rotating)
├── Define Day Types (A, B or Day 1-7 etc.)
├── Define Bell Periods (Period 1-8 with start/end times)
└── Activate Pattern

         ↓

PHASE 2: DEMAND ANALYSIS (8-12 weeks before term)
│
├── Open Course Request Window
├── Students/counselors submit course requests
├── Analyze: demand per course, singletons, conflicts
├── Approve: section counts per course
└── Close Request Window

         ↓

PHASE 3: MASTER SCHEDULE BUILD (6-8 weeks before term)
│
├── Create Master Schedule document (DRAFT)
├── Create sections from demand analysis
├── Place sections in periods (section_meeting records)
│   ├── Conflict detection runs on each placement
│   └── Singletons placed first (in different periods)
├── Assign instructors to sections
├── Assign rooms to section meetings
└── Status → BUILDING

         ↓

PHASE 4: REVIEW AND CONFLICT RESOLUTION (4-6 weeks before term)
│
├── Run full conflict analysis
├── Resolve CRITICAL conflicts (instructor/room double-booking)
├── Resolve/accept HIGH conflicts (student conflicts, overload)
├── Run fulfillment analysis (% requests satisfied)
├── Load balancing review
└── Status → REVIEW

         ↓

PHASE 5: PUBLISH (2-4 weeks before term)
│
├── All critical conflicts resolved
├── Mark sections: SCHEDULED
├── Publish master schedule
├── Academic term → ENROLLMENT_OPEN
├── Notify instructors
└── Status → PUBLISHED

         ↓

PHASE 6: ENROLLMENT (term enrollment window)
│
├── Students enroll in sections (parent EduClaw: enroll-student action)
├── Section fills up → waitlist kicks in
├── Late add/drop → room bookings updated
└── Enrollment closes → status → LOCKED

         ↓

PHASE 7: ACTIVE TERM MAINTENANCE
│
├── Instructor substitutions
├── Emergency room reassignments
├── Section cancellations (under-enrolled)
└── New section additions (over-demand)
```

---

## 7. Integration Points with Parent EduClaw

| Parent Table | Integration Point | Direction |
|-------------|------------------|-----------|
| `educlaw_section` | All section_meeting records reference section_id | scheduling → reads parent |
| `educlaw_academic_term` | master_schedule references academic_term_id | scheduling → reads parent |
| `educlaw_room` | room_booking references room_id | scheduling → reads parent |
| `educlaw_instructor` | section_meeting + instructor_constraint reference instructor_id | scheduling → reads parent |
| `educlaw_course` | section_meeting + course_request reference course_id | scheduling → reads parent |
| `educlaw_student` | course_request references student_id | scheduling → reads parent |
| `educlaw_program_requirement` | Used to generate student course request suggestions | scheduling → reads parent |
| `educlaw_course_enrollment` | Created AFTER sections are scheduled + enrollment opens | parent ← scheduling output |

---

## 8. Action Inventory (Estimated)

### Schedule Patterns Domain (~10 actions)
| Action | Description |
|--------|-------------|
| `add-schedule-pattern` | Create a new schedule pattern |
| `update-schedule-pattern` | Update pattern details |
| `get-schedule-pattern` | Get pattern with bell periods and day types |
| `list-schedule-patterns` | List all patterns for company |
| `add-bell-period` | Add a period to a pattern |
| `add-day-type` | Add a day type to a pattern |
| `map-day-type-to-dates` | Map day types to calendar dates for a term |
| `get-pattern-calendar` | View the full date→day_type mapping for a term |
| `calculate-contact-hours` | Calculate total contact hours for a section given pattern |
| `activate-schedule-pattern` | Mark a pattern as active |

### Master Schedule Domain (~12 actions)
| Action | Description |
|--------|-------------|
| `create-master-schedule` | Create master schedule for a term |
| `get-master-schedule` | Get master schedule with all sections |
| `analyze-course-demand` | Generate demand report from course requests |
| `add-section-to-schedule` | Add a section to the master schedule |
| `place-section-meeting` | Assign a section to a period + day_type |
| `remove-section-meeting` | Unplace a section meeting |
| `publish-master-schedule` | Publish (sets sections to SCHEDULED, term to ENROLLMENT_OPEN) |
| `lock-master-schedule` | Lock (prevents further changes) |
| `get-fulfillment-report` | % of course requests that can be satisfied |
| `get-schedule-matrix` | Visual period grid of all placed sections |
| `get-load-balance-report` | Instructor and section size distribution |
| `clone-master-schedule` | Copy last term's schedule as starting draft |

### Conflict Resolution Domain (~8 actions)
| Action | Description |
|--------|-------------|
| `run-conflict-check` | Run full conflict analysis on master schedule |
| `list-conflicts` | List all open conflicts (filterable by type/severity) |
| `get-conflict` | Get conflict detail with resolution options |
| `resolve-conflict` | Mark conflict as resolved with notes |
| `accept-conflict` | Accept an irresolvable conflict |
| `get-conflict-summary` | Count of open conflicts by type |
| `get-singleton-conflict-map` | Show which singleton courses share students |
| `get-student-conflict-report` | Students with conflicts in their requested courses |

### Room Assignment Domain (~10 actions)
| Action | Description |
|--------|-------------|
| `assign-room` | Assign a room to a section meeting |
| `suggest-room` | Get smart room suggestions for a section meeting |
| `bulk-assign-rooms` | Auto-assign rooms to all unassigned section meetings |
| `unassign-room` | Remove room from section meeting |
| `block-room` | Mark room as unavailable for a period range |
| `swap-rooms` | Swap room assignments between two section meetings |
| `get-room-availability` | View available periods for a room |
| `get-room-utilization-report` | Room utilization across term |
| `search-rooms-by-features` | Find rooms with specific features and availability |
| `emergency-reassign-room` | Bulk reassign all sections from a room (emergency) |

### Course Request Domain (~8 actions)
| Action | Description |
|--------|-------------|
| `open-course-requests` | Open request window for upcoming term |
| `submit-course-request` | Student/counselor submits course request |
| `update-course-request` | Modify request (change priority, add alternate) |
| `list-course-requests` | List all requests with filters (student, course, status) |
| `approve-course-requests` | Counselor batch-approves requests |
| `get-demand-report` | Sections needed per course based on requests |
| `get-singleton-analysis` | Singleton courses + their student overlap |
| `close-course-requests` | Close request window |

### **Total Estimated Actions: ~48**

---

*Sources: PowerScheduler User Guide, Infinite Campus scheduling documentation, FET documentation (lalescu.ro), SchoolInsight feature page, Gibbon timetabling documentation, aSc TimeTables feature list, Schedule25/CollegeNET documentation, Aspen/Follett scheduling docs*
