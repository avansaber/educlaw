# EduClaw Advanced Scheduling — Research Summary

**Product:** educlaw-scheduling
**Display Name:** EduClaw Advanced Scheduling
**Research Date:** 2026-03-05
**Research Files:** parent_analysis.md, overview.md, competitors.md, compliance.md, workflows.md, data_model.md

---

## Executive Summary

EduClaw Advanced Scheduling is a sub-vertical of EduClaw that delivers the scheduling capabilities explicitly deferred in the parent product's v1 roadmap: **master scheduling, schedule patterns, conflict resolution, and room assignment**.

The parent EduClaw already covers basic section scheduling (a section with a fixed weekly time slot). This sub-vertical extends it to handle:
- **Named schedule patterns** (traditional 7-period, 4x4 block, A/B alternating, rotating drop, trimester, semester)
- **Formal master schedule lifecycle** (draft → build → review → publish → lock)
- **Course request-driven demand analysis** (before sections are created)
- **Proactive conflict detection** (11 conflict types across instructor, room, student, and compliance dimensions)
- **Smart room assignment** (capacity, type, and equipment matching with scoring)
- **Instructor scheduling constraints** (unavailability, contract limits, preferences)

The sub-vertical adds **9 new tables** and **~48 actions** on top of the parent EduClaw system.

---

## Recommended Scope

### Domain 1: master_schedule (P0 — Critical)

| Tables | Actions | Complexity |
|--------|---------|-----------|
| `educlaw_master_schedule` | 12 | Medium-High |

**Core functionality:**
- Create master schedule document linked to academic term and schedule pattern
- Section creation from demand analysis
- Section placement in period/day-type slots
- Publish/lock lifecycle with integration to parent `educlaw_section` status
- Contact hours validation against credit requirements
- Fulfillment rate analysis and load balancing reports
- Clone previous term's schedule as starting draft

**Why P0:** Without master schedule management, the scheduling module is just a collection of tools with no workflow. The master schedule is the product.

---

### Domain 2: schedule_patterns (P0 — Critical)

| Tables | Actions | Complexity |
|--------|---------|-----------|
| `educlaw_schedule_pattern`, `educlaw_day_type`, `educlaw_bell_period` | 10 | Low-Medium |

**Core functionality:**
- Define named patterns (traditional, block, A/B, trimester, rotating drop, semester, custom)
- Define day types per cycle (Day A, Day B, etc.)
- Define bell periods per day type (start/end times, period type, duration)
- Calendar mapping (which calendar dates are Day A vs. Day B)
- Contact hours calculator (total instructional minutes per section)
- Activate pattern for use in master schedules

**Why P0:** Schedule patterns are the foundation everything else is built on. A master schedule without a pattern is meaningless.

---

### Domain 3: conflict_resolution (P0 — Critical)

| Tables | Actions | Complexity |
|--------|---------|-----------|
| `educlaw_schedule_conflict` | 8 | Medium |

**Core functionality:**
- Automatic conflict detection on every section meeting placement
- 11 conflict types: instructor double-booking, room double-booking, student conflict, instructor overload, instructor contract violation, capacity exceeded, room type mismatch, credential mismatch, singleton overlap, contact hours deficit, room shortage
- Conflict severity: critical/high/medium/low
- Resolution workflow: open → resolving → resolved/accepted/superseded
- Pre-publish validation: block publish if CRITICAL conflicts unresolved
- Fulfillment analysis: % of student course requests satisfied

**Why P0:** Conflict detection is the #1 value proposition of any scheduling tool. Without it, EduClaw Scheduling is not better than a spreadsheet.

---

### Domain 4: room_assignment (P1 — Important)

| Tables | Actions | Complexity |
|--------|---------|-----------|
| `educlaw_room_booking`, `educlaw_instructor_constraint` | 10 | Medium |

**Core functionality:**
- Explicit room booking records (primary conflict detection source)
- Smart room suggestion (capacity + type + feature matching + scoring)
- Bulk auto-assign rooms to unassigned section meetings
- Instructor scheduling constraints (unavailability, max periods, prep period)
- Room utilization reports (per room, per building, per term)
- Emergency room reassignment (bulk move all sections from a room)

**Why P1 (not P0):** Room assignment can be done manually without the smart features; conflict detection (domain 3) catches manual errors. The smart assignment is a quality-of-life feature. Instructor constraints are critical for accurate conflict detection but can be added after the core.

---

### Course Requests (P1 — Important)

| Tables | Actions | Complexity |
|--------|---------|-----------|
| `educlaw_course_request` | 8 | Low-Medium |

**Core functionality:**
- Course request collection from students/counselors
- Prerequisite validation against parent `educlaw_course_prerequisite`
- Demand report (requests per course → sections needed)
- Singleton analysis (which singleton courses share students)
- Request status tracking (submitted → approved → scheduled/alternate_used/unfulfilled)
- Fulfillment rate tied to master schedule analysis

**Why P1:** Without course requests, the demand analysis phase is manual (counselors must estimate section counts). Many smaller schools are comfortable with manual demand estimation. Course requests add significant automation value but are not required for the scheduling engine to function.

---

## Build Scope Summary

| Domain | Tables | Actions | Priority | Complexity |
|--------|--------|---------|----------|------------|
| **Master Schedule** | 1 | 12 | P0 | Medium-High |
| **Schedule Patterns** | 3 | 10 | P0 | Low-Medium |
| **Conflict Resolution** | 1 | 8 | P0 | Medium |
| **Room Assignment + Constraints** | 2 | 10 | P1 | Medium |
| **Course Requests** | 1 | 8 | P1 | Low-Medium |
| **Section Meetings** | 1 | Included above | P0 | Low |
| **Totals** | **9** | **~48** | | |

---

## Key Architecture Decisions

### 1. Meetings as Explicit Records (NOT encoded in section fields)
Every section meeting (section + day_type + period + room + instructor) is a stored row in `educlaw_section_meeting`. This is the universal pattern in all serious scheduling tools (FET, aSc, PowerScheduler).

**Why:** Enables:
- Per-meeting conflict detection (not just whole-section checking)
- Multi-room sections (lecture in Room 101, lab in Room 305)
- Different instructors per day type (co-teaching, substitution)
- Visual period grids without complex client-side computation

**Anti-pattern to avoid:** Encoding schedule as `days_of_week: ["Mon","Wed","Fri"]` + single `start_time`/`end_time` (current parent model — fine for simple sections, inadequate for advanced scheduling)

### 2. Room Booking as First-Class Entity
Room assignments are stored as separate `educlaw_room_booking` records, not just as FK on section meetings. This enables:
- Complete room calendar including non-class bookings (exams, events, maintenance)
- Single-query conflict detection: `WHERE room_id = ? AND day_type_id = ? AND period_id = ?`
- Future integration with facilities/event management

**Conflict detection is fast:** `O(1)` lookup on `(room_id, day_type_id, bell_period_id)` unique index.

### 3. Constraint Table Pattern
Instructor constraints live in `educlaw_instructor_constraint`, not in `educlaw_instructor`. This is because:
- Constraints are term-specific (different each term)
- Instructors can have many constraints (multiple unavailable periods)
- New constraint types can be added without altering the instructor table

### 4. Status Field Naming Convention
Following parent EduClaw convention to avoid `ok()` response wrapper collision:
- `educlaw_master_schedule.schedule_status` (not `status`)
- `educlaw_schedule_conflict.conflict_status` (not `status`)
- `educlaw_course_request.request_status` (not `status`)
- `educlaw_room_booking.booking_status` (not `status`)

### 5. Backward Compatibility with Parent Sections
`educlaw_section` remains unchanged. The scheduling sub-vertical:
- Reads `educlaw_section` to get course/term/instructor assignments
- Writes `educlaw_section.status` to SCHEDULED when master schedule is published
- Creates new `educlaw_section_meeting` records linked to sections
- Does NOT modify `educlaw_section.days_of_week`, `start_time`, `end_time` fields (those remain for simple scheduling without the sub-vertical)

### 6. Deferred: Automated Schedule Generation
Building a schedule from scratch (fully automated, like FET's genetic algorithm) is **deferred to v2**. The v1 workflow is:
1. Counselor/administrator creates sections and places them in periods manually
2. System provides conflict detection, suggestions, and validations
3. Smart room assignment partially automates room selection
4. Course request demand analysis partially automates section count decisions

Full auto-generation requires implementing a constraint-based search algorithm — significant engineering complexity. Schools with experienced schedulers can build excellent schedules manually with good tooling (the v1 model). Auto-generation is the v2 differentiator.

### 7. No Student-Level Auto-Loading (Deferred)
Automatically loading students into sections based on their course requests (like PowerScheduler's "Student Loader") is deferred to v2. In v1, once sections are scheduled, students enroll through the parent EduClaw's `enroll-student` action.

---

## Key Differentiators vs. Competitors

| Capability | FET | Gibbon | PowerScheduler | aSc | **EduClaw Scheduling** |
|-----------|-----|--------|----------------|-----|------------------------|
| Native SIS Integration | ❌ | ✅ | ✅ | ❌ | ✅ (native to EduClaw) |
| Full ERP Integration | ❌ | ❌ | ❌ | ❌ | ✅ (via erpclaw-gl/payments) |
| AI/NLP Interface | ❌ | ❌ | ❌ | ❌ | ✅ (OpenClaw) |
| Open Source | ✅ | ✅ | ❌ | ❌ | ✅ |
| Cost | $0 | $0 | ~$5-20/student | ~$300-800/yr | **$0** |
| Block Scheduling | ✅ | ✅ | ✅ | ✅ | ✅ |
| Conflict Detection | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| Room Booking | ⚠️ | ❌ | ⚠️ | ✅ | ✅ |
| Course Requests | ❌ | ❌ | ✅ | ❌ | ✅ |
| Instructor Constraints | ✅ | ⚠️ | ✅ | ✅ | ✅ |

**EduClaw's unique position:** The only open-source education scheduling tool with native SIS integration, full ERP integration, and an AI-native interface — at zero cost.

---

## Technical Risks and Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Section meeting fan-out** | MEDIUM | A MWF section creates 3 meeting records. A 200-section schedule has 600+ meeting records. Indexes on `(day_type_id, bell_period_id, instructor_id)` and `(day_type_id, bell_period_id, room_id)` make conflict detection fast. |
| **Conflict detection on every insert** | MEDIUM | Run conflict check as a query after insert, not via triggers. Return conflict list as part of action response. Don't block insert — record conflict and let administrator resolve. |
| **schedule_status vs. section.status lifecycle** | HIGH | Master schedule `publish` action must carefully update `educlaw_section.status` from 'draft' → 'scheduled' for all sections in the master schedule. Must use a transaction. |
| **Day type → calendar date mapping complexity** | MEDIUM | For A/B blocks, the mapping is deterministic (alternating Mon/Tue starting Day A). Provide a wizard to auto-generate the mapping for common patterns; allow override for exceptions. |
| **Contact hours calculation with holidays** | MEDIUM | Contact hours = periods × days_per_type × duration. Holidays subtract from day_type counts. Must account for school calendar (holiday set stored in `educlaw_academic_term` or a new holiday table — v2 refinement). For v1, manually specify day type counts. |
| **Course request race condition** | LOW | Multiple counselors submitting requests simultaneously. The `UNIQUE (student_id, academic_term_id, course_id)` constraint prevents duplicates at DB level. |
| **Backward compat with sections without meetings** | LOW | Parent EduClaw sections that predate this sub-vertical have no `section_meeting` records. Display logic must gracefully handle sections with `days_of_week` JSON but no meeting records. |
| **Auto-generation algorithm (v2)** | HIGH | Genetic/local-search algorithms are complex. For v2, consider integrating FET as a library or re-implementing a greedy-then-optimize approach. |

---

## Estimated Complexity

| Component | Effort | Notes |
|-----------|--------|-------|
| Schema (9 new tables in init_db.py) | 1-2 hours | Follows established patterns |
| Schedule Pattern domain (~10 actions) | 2-3 hours | Mostly CRUD + calendar mapping wizard |
| Master Schedule domain (~12 actions) | 4-6 hours | Lifecycle management, demand analysis, publish workflow |
| Conflict Resolution domain (~8 actions) | 3-5 hours | Conflict queries, severity logic, resolution workflow |
| Room Assignment domain (~10 actions) | 3-4 hours | Smart suggestion algorithm, utilization reports |
| Course Request domain (~8 actions) | 2-3 hours | CRUD + demand report + singleton analysis |
| SKILL.md | 1-2 hours | ~48 actions to document |
| Tests | 8-12 hours | Complex workflows require thorough testing |
| **Total** | **~24-37 hours** | Build time excluding research/planning |

---

## Recommended Build Order

1. **Schema first** — All 9 tables in `init_db.py`; run `init_db.py` to create tables
2. **Schedule Patterns** — Foundation; nothing else works without patterns
3. **Master Schedule CRUD** — Create/get/list; no publish logic yet
4. **Section Meetings** — Place sections in periods; enables conflict detection
5. **Conflict Detection** — Instructor + room double-booking (critical conflicts first)
6. **Room Booking** — Formalize room assignments; complete conflict coverage
7. **Master Schedule Lifecycle** — Publish/lock with parent section status updates
8. **Instructor Constraints** — Add constraint types; extend conflict detection
9. **Course Requests** — Demand analysis; prerequisite validation
10. **Reporting actions** — Fulfillment rate, load balance, room utilization
11. **Tests** — Cover all critical paths

---

## v2 Feature Backlog

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Auto-generate schedule** | Greedy algorithm: place singletons → high demand → standard | Very High |
| **Student auto-loading** | Assign students to sections based on course requests | High |
| **Ed-Fi API export** | Expose master schedule in Ed-Fi standard format | Medium |
| **Holiday calendar** | Track non-instructional days; adjust contact hours | Medium |
| **Multi-building optimizer** | Consider building travel time between consecutive periods | High |
| **Exam scheduling** | Separate exam period scheduling at term end | Medium |
| **Substitute management** | Real-time instructor substitution during term | Medium |
| **IEP placement constraints** | Student-level scheduling constraints from IEP data | High |
| **4-year academic planning** | Multi-term course sequence planning for students | High |
| **Schedule comparison** | Save and compare multiple draft master schedules | Medium |

---

## Compliance Checklist for v1

- [x] **Instructional time validation** — Contact hours calculator with credit hour standard
- [x] **Instructor contract constraints** — Max periods, prep period, consecutive limits
- [x] **FERPA-aware access** — Course request data is education record; integrate with parent access log
- [x] **Room accessibility flags** — Extend room features for ADA accessibility
- [x] **Credential mismatch warning** — Non-blocking warning in conflict detection
- [ ] **Ed-Fi export** — Deferred to v2
- [ ] **IEP placement management** — Deferred to v2
- [ ] **Holiday calendar** — v2 refinement (v1 uses manual day type counts)

---

*Research completed: 2026-03-05*
*All research files written to: research/educlaw-scheduling/*
*Parent product analyzed: EduClaw (32 tables, 74 actions, 9 domains)*
*Competitors analyzed: FET, Gibbon, ERPNext Education, PowerSchool PowerScheduler, Infinite Campus, aSc TimeTables, Rediker, Schedule25, SchoolInsight/TeacherEase, Aspen/Follett*
