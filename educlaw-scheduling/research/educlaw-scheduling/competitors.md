# EduClaw Advanced Scheduling — Competitor Analysis

## Overview

Education scheduling competitors fall into three categories:
1. **Integrated SIS with scheduling modules** (PowerSchool, Infinite Campus, Aspen/Follett)
2. **Dedicated scheduling tools** (aSc TimeTables, Rediker, Schedule25, SchoolInsight/TeacherEase)
3. **Open-source timetabling** (FET, Gibbon, ERPNext Education)

EduClaw Scheduling must study all three to extract the best data models, UX patterns, and algorithmic approaches.

---

## 1. Open-Source Competitors

### 1.1 FET — Free Timetabling Software

**URL:** https://lalescu.ro/liviu/fet/
**License:** GNU Affero General Public License v3
**Language:** C++ (Qt framework)
**Users:** 100,000+ institutions globally (especially popular in Middle East, Eastern Europe, South America)

#### Architecture and Data Model

FET models the scheduling problem as a **constraint satisfaction problem (CSP)** with local search:
- **Algorithm:** Constraint-based + local search (simulated annealing variant)
- **Solve time:** 5-20 minutes for complex high school timetables
- **Input format:** XML file with complete institution data

**Key Entities:**
| FET Entity | EduClaw Equivalent |
|-----------|-------------------|
| Days | Day types in a scheduling cycle |
| Hours (periods per day) | Bell periods |
| Teachers | Instructors |
| Students Set / Group / Subgroup | Student cohort groupings |
| Subjects | Courses |
| Activity | Section meeting (course + teacher + students + room + period) |
| Room | Room |
| Building | Building |
| Time Constraint | Instructor/room constraints |
| Space Constraint | Room feature requirements |

**Scheduling Modes:**
- **Standard mode** — Regular timetabling
- **Mornings-Afternoons mode** — North African school systems (AM/PM division)
- **Block Planning mode** — North American block schedules (IB-style)
- **Terms mode** — Finnish school system (different courses per period per week)

**Key Features:**
- Automatic generation with full constraint satisfaction
- Semi-automatic (generate partially, then manual finalization)
- Manual override at any point
- Comprehensive time and space constraints:
  - Teacher unavailable times
  - Teacher max hours/day
  - Teacher min/max gaps between activities
  - Activity preferred time/room
  - Activities same time / different time
  - Students max hours continuously

**Data Model Insights (for EduClaw):**
- Activities (section meetings) are the atomic unit — each meeting is explicit
- Constraints are stored separately from activities (constraint table pattern)
- Multi-room activities supported (lecture + lab in different rooms)
- Student subgroups (not individual students in FET — population scheduling)
- Conflict detection is integral to the generation algorithm, not post-hoc

**Gaps (vs. EduClaw needs):**
- No student course request system (FET schedules populations, not individuals)
- No integration with SIS for actual enrollment data
- Desktop application only (no web/API)
- No room booking confirmation workflow
- No financial integration

**Lessons for EduClaw Scheduling:**
1. Store meetings as explicit records (section + day_type + period + room + instructor)
2. Constraints as a separate table — flexible, extensible
3. Conflict score is valuable — not just binary conflict/no-conflict
4. Support both automatic generation AND manual placement

---

### 1.2 Gibbon School Management Platform

**URL:** https://gibbonedu.org/
**License:** GNU General Public License v3
**Language:** PHP + MySQL
**Users:** ~1,500 schools in 140 countries

#### Architecture and Data Model

Gibbon uses a **column/row/timetable** abstraction:

```
Timetable Column
  ├── Defines a single day's period structure (times, period names)
  └── Reusable across multiple days within a timetable

Timetable Row
  ├── A named day (e.g., "Monday", "Day A")
  └── References one or more columns for that day's structure

Timetable
  ├── Year-specific schedule structure
  ├── Contains multiple rows (days)
  └── Classes assigned to period slots within rows

Timetable Day
  └── Maps timetable rows to actual calendar dates
```

**Key Features:**
- Multiple timetables per year (different structures for different year groups)
- Drag-and-drop schedule building
- Period assignment per class
- Conflict detection (teacher and room double-booking)
- Student schedule view
- Teacher schedule view
- Substitute teacher management

**Data Model Insights:**
- Separation of **schedule structure** (pattern) from **schedule content** (assignments)
- Column/Row abstraction cleanly handles A/B day, rotating schedules
- Calendar mapping (which day type maps to which date) is explicit — important for holidays/special events
- Multiple timetables per school year (separate schedule for primary/secondary divisions)

**Gaps:**
- No course request system / student-driven demand analysis
- No automated schedule building (entirely manual placement)
- No conflict matrix analysis tool
- No room optimization
- No integration with financial systems

**Lessons for EduClaw Scheduling:**
1. **Column/Row separation** → EduClaw's `schedule_pattern` (column) + `day_type` (row) pattern
2. **Calendar day mapping** → EduClaw must map day types to actual calendar dates for term
3. Multiple patterns per institution (high school vs. middle school can have different schedules)

---

### 1.3 ERPNext Education

**URL:** https://frappe.io/education
**License:** GNU General Public License v3
**Language:** Python (Frappe framework)

#### Scheduling Features

ERPNext Education scheduling is minimal:
- `Course Schedule` doctype: Course + instructor + room + time
- No schedule patterns or day types
- No conflict detection engine
- No course request system
- No block scheduling support

**Assessment:** ERPNext Education is ~2 years behind in scheduling capability compared to dedicated tools. EduClaw has already matched ERPNext in basic scheduling (via `educlaw_section`) and this sub-vertical decisively surpasses it.

---

## 2. Commercial Competitors

### 2.1 PowerSchool PowerScheduler

**Product:** PowerScheduler (part of PowerSchool SIS)
**Market Position:** #1 K-12 SIS with strongest K-12 scheduling market share
**Pricing:** ~$5-20/student/year (PowerSchool suite)

#### Scheduling Architecture

PowerScheduler is a dedicated scheduling engine within PowerSchool:

**Step 1: Course Catalog Preparation**
- Mark courses as "active for scheduling"
- Define: credit hours, singletons flag, gender restrictions, max/min enrollment
- Set alternate courses (if primary can't be scheduled)

**Step 2: Course Requests**
- Students/parents submit course requests via portal
- Counselors enter/approve requests
- Request priority (1=highest priority, ensures scheduled first)
- Alternate requests (scheduled if primary fails)
- Course Request Tally page: demand analysis before building

**Step 3: Teacher/Room Constraints**
- Mark teachers unavailable for certain periods
- Assign preferred rooms per course
- Set teacher max periods per day/week

**Step 4: Schedule Build**
- Define scheduling structure: number of periods, days in cycle, terms
- Run automated builder: analyzes requests + constraints, places sections
- Key algorithm: prioritizes singletons, then high-request courses, then fills by demand
- Multi-run capability: run builder multiple times, compare results

**Step 5: Student Loading**
- After master schedule built, load students into sections
- Student Loader: auto-assigns based on requests + constraints
- Walk-in Scheduler: manual single-student adjustment
- Handles alternates automatically

**Step 6: Verification**
- Conflict matrix: visual grid of student conflicts
- Section balance report: enrollment distribution
- Unfilled request report: students who didn't get requests

**Key Data Points:**
- PowerScheduler reports 95%+ average fulfillment rates for schools using it correctly
- Schedule building for a 1,500-student high school takes ~2-4 hours (automated) + review time
- Supports: traditional, block (4x4 and A/B), semester

**Data Model Insights (inferred from documentation):**
- Course Request entity: `student_id`, `course_id`, `priority`, `is_alternate`, `term_id`
- Schedule Structure: `periods_per_day`, `days_per_cycle`, `terms_per_year`
- Section entity (extended): links to schedule structure for period assignment
- Period assignment: `section_id`, `period_number`, `day_bitmap`, `room_id`, `teacher_id`

**Limitations:**
- Rigid schedule structure (must define structure before building)
- Complex UI — requires dedicated training
- No AI/NLP interface
- Expensive ($5-20/student/year)
- Heavy implementation burden

---

### 2.2 Infinite Campus Scheduling

**Product:** Infinite Campus SIS — Scheduling module
**Market Position:** #3 K-12 SIS; strong in public districts
**Pricing:** Custom enterprise pricing (~$4-15/student/year)

#### Key Features

**Master Scheduling:**
- Period grid builder — visual drag-and-drop
- Schedule set and period groups support multiple schedule structures
- Sequence of courses (prerequisite chains for scheduling priority)
- Team/house scheduling (K-8 cohort-based)

**Course Requests:**
- Portal submission by students/parents
- Counselor dashboard for review and approval
- Academic Planner integration (4-year plan driving current year requests)
- Request & Rosters tool for batch management

**Reports (unique to Infinite Campus):**
- Student schedule matrix
- Course placement report
- Open sections report
- Teacher/student schedule reports
- Course request reports with fulfillment analysis

**Data Model Insights:**
- `Schedule Set` — defines the schedule structure (period grid)
- `Period` — named time slot within a structure
- `Schedule Structure` — which periods map to which schedule sets
- `Section` (extended) — links to period + schedule set
- `Course Request` — student + course + term + priority

**Differentiators vs. PowerSchool:**
- Stronger team/house scheduling for middle schools
- Better reporting out of the box
- More granular period grid control

**Limitations:**
- Complex configuration (similar learning curve to PowerSchool)
- No open API for schedule export
- No AI/automation recommendations

---

### 2.3 aSc TimeTables

**Product:** aSc TimeTables
**Website:** https://www.asctimetables.com/
**Market:** Global, especially popular in Europe, International Schools
**Pricing:** ~$300-800/year for small school; enterprise pricing for districts
**Algorithm:** Genetic algorithm optimization

#### Scheduling Architecture

aSc is a **dedicated standalone timetabling tool** (not integrated SIS):

**Input Data:**
- Teachers (availability, max hours, preferences)
- Classes/groups (year groups, sections)
- Subjects (courses with credit hours)
- Classrooms (capacity, type)
- Lessons (activities: course + teacher + class + credits = number of periods needed per week)
- Constraints (teacher unavailable, class/subject fixed to period, room preferences)

**Schedule Generation:**
- Genetic algorithm: generates population of schedules, breeds/mutates, selects best
- Evaluates: hard constraints (no double-booking) + soft constraints (preferences)
- Generates alternative solutions to choose from
- Score for each solution: % hard constraints satisfied + soft constraint score

**Key Features:**
- Teacher substitution module (real-time during term)
- Exam scheduling module (separate from class scheduling)
- Student individual scheduling (for electives after base schedule is built)
- Export to PowerSchool, Infinite Campus, Blackboard
- Web publication of schedule

**Data Model Insights:**
- **Lesson** entity is equivalent to EduClaw's "section meeting requirement" — it defines what needs to be scheduled (course, teacher, class, N periods/week) before placement
- **Card/Activity** = placed lesson (lesson + specific period + room + day)
- **Constraint** table is first-class — dozens of constraint types, stored separately
- Two-phase approach: define requirements → place in schedule

**Lessons for EduClaw Scheduling:**
1. Pre-scheduling requirement (what needs to go in) vs. placed schedule (where it goes) is a useful separation
2. Constraint types should be enumerated and extensible
3. Genetic algorithm for auto-generation is effective but complex to implement — start with simpler heuristics

---

### 2.4 Rediker Super Deluxe Schedule Builder

**Product:** Part of Rediker SIS
**Market:** Small-mid private/independent K-12 schools
**Key Features:**
- Automated schedule building with manual override
- Drag-and-drop section placement
- Teacher and room conflict detection
- Student scheduling with alternate handling
- Singleton course priority
- Schedule comparison (save multiple draft schedules)
- PDF schedule cards (traditional school output)

**Data Model Insights:**
- Schedule builder operates in "planning mode" — separate from live student data
- "Sandbox" approach: changes are staged until published
- Multi-draft capability is important — administrators build 2-3 versions before choosing

**Lessons for EduClaw:**
1. Sandbox/draft scheduling is a must-have UX pattern — you don't build in production
2. Multiple saved draft schedules (with comparison) add significant value
3. Small school users need a simpler workflow than PowerScheduler

---

### 2.5 Schedule25 (CollegeNET)

**Product:** Academic scheduling for universities
**Website:** https://collegenet.com/scheduling/schedule25
**Market:** Higher education (universities, community colleges)
**Differentiator:** Room optimization for 1,000+ sections

#### University-Specific Features

**Meeting Pattern Standardization:**
- Enforces standard meeting patterns (MWF 50-min, TR 75-min, MTWR 50-min, etc.)
- Non-standard patterns flagged for special approval
- Pattern standardization maximizes room utilization (irregular patterns leave gaps)

**Room Assignment Optimization:**
- Two-phase: first assign all sections to rooms meeting hard constraints (capacity, type), then optimize for utilization
- Preferred building within department
- Equipment requirements matching
- Consecutive-period same-room preference for instructors
- Cross-listed section handling (same room for same time)

**Enrollment Projections:**
- Historical enrollment data drives section size estimates
- Overcap/undercap alerts before room assignment
- Dynamic re-optimization as enrollment changes

**Data Model Insights:**
- `Meeting Pattern` — formal enumerated list of approved patterns
- `Section Request` — department submits section to be scheduled (not students)
- `Room Assignment` — explicit reservation record separate from section
- `Space Utilization Report` — key administrative report

**Lessons for EduClaw Scheduling:**
1. **Meeting pattern standardization** is valuable even for K-12 (prevents schedule chaos from ad-hoc patterns)
2. **Room assignment as explicit record** (not just a field on section) enables better conflict detection
3. **Two-phase approach** — meet hard constraints first, then optimize soft constraints

---

### 2.6 SchoolInsight (TeacherEase) Advanced Scheduling

**URL:** https://www.teacherease.com/advancedscheduling.aspx
**Market:** Small-mid K-12 schools
**Pricing:** ~$1,000-5,000/year

**Key Features:**
- Automatic schedule generation with manual override
- Supports M-F, A/B alternating, block scheduling, custom cycles
- Course request collection (students and parents)
- Conflict matrix with singleton detection
- Lunch period auto-scheduling
- Teacher/room conflict detection
- Section balance optimization (gender, GPA, demographics)
- Save/restore draft schedules
- Fulfillment rate analytics

**Notable Feature: Section Balance**
Beyond conflict resolution, SchoolInsight allows balancing sections by student demographics (gender, academic level, ethnicity). This ensures equitable distribution across sections of the same course.

**Data Model Insights:**
- Schedule cycle: `N` days
- Period definition: period_number, start_time, end_time, period_type (class/break/lunch/advisory)
- Course attributes for scheduling: `is_singleton`, `requires_same_period_as`, `prohibited_from_period`, `gender_restriction`
- Teacher constraint: `unavailable_period_ids[]`, `max_consecutive_periods`, `requires_prep_period`

---

## 3. Feature Comparison Matrix

| Feature | FET | Gibbon | PowerScheduler | Infinite Campus | aSc | Rediker | SchoolInsight | **EduClaw Target** |
|---------|-----|--------|----------------|-----------------|-----|---------|---------------|--------------------|
| Traditional Schedule | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Block Schedule (4x4) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| A/B Block | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Rotating Drop | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| Trimester | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |
| Course Requests | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| Auto Schedule Build | ✅ | ❌ | ✅ | ⚠️ | ✅ | ✅ | ✅ | v2 |
| Conflict Matrix | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Room Optimization | ⚠️ | ❌ | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |
| Instructor Constraints | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Student Loading | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | v2 |
| Draft/Sandbox Mode | ❌ | ❌ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| SIS Integration | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ (native) |
| GL/Finance Integration | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (via parent) |
| AI/NLP Interface | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Open Source | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 4. Key Design Decisions from Competitor Analysis

### 4.1 Store Meetings as Explicit Records
Every major competitor (FET, aSc, PowerScheduler) stores section meetings as explicit records — not as encoded fields in the section record. An activity/card/period-assignment is a first-class entity.

**EduClaw Implementation:** `educlaw_section_meeting` table where each row = one meeting instance (section + day_type + period + room + instructor)

### 4.2 Separate Requirement from Placement (Two-Phase)
aSc separates "Lesson" (what needs scheduling) from "Card" (where it's placed). PowerScheduler similarly separates course requests from section assignments.

**EduClaw Implementation:**
- `educlaw_course_request` → what students need (demand)
- `educlaw_master_schedule` → the built schedule (supply)
- `educlaw_section_meeting` → specific placements

### 4.3 Conflict Registry as First-Class Entity
Conflicts detected during building should be stored explicitly, not just reported. This allows workflow: detect → assign → resolve → verify.

**EduClaw Implementation:** `educlaw_schedule_conflict` table with conflict_type, status (open/resolved/accepted), and resolution notes

### 4.4 Instructor Constraints as Separate Table
All competitors store instructor constraints separately — not embedded in the instructor record. This is because constraints are:
- Term-specific (unavailable Monday first period in Fall 2026 only)
- Multiple per instructor (can have many constraints)
- Different types (unavailable, preferred, max-consecutive, prep-period)

**EduClaw Implementation:** `educlaw_instructor_constraint` table

### 4.5 Room Booking as First-Class Entity
Schedule25 and aSc explicitly book rooms as a separate action from assigning a room to a section. This enables:
- Multi-system conflict detection (another event in a room during a class period)
- Future calendaring integration (rooms also used for events, exams, meetings)

**EduClaw Implementation:** `educlaw_room_booking` table

### 4.6 Named Schedule Patterns (Reusable)
Gibbon, aSc, and Aspen all define schedule patterns/structures independently from the actual schedule. A pattern can be reused across terms, buildings, or sub-schools.

**EduClaw Implementation:** `educlaw_schedule_pattern` + `educlaw_bell_period` + `educlaw_day_type` tables

---

## 5. Pricing Intelligence

| Product | Pricing Model | Target School Size | Annual Cost Estimate |
|---------|--------------|-------------------|---------------------|
| PowerSchool | Per student/year (~$5-20) | Districts; 500-50,000 students | $2,500-$100,000+ |
| Infinite Campus | Per student/year (~$4-15) | Districts; 500-50,000 students | $2,000-$75,000+ |
| aSc TimeTables | Per school/year (flat) | Any; 50-5,000 students | $300-$800 |
| Rediker | Suite pricing | Private schools; 100-2,000 students | $2,000-$8,000 |
| SchoolInsight | Per school/year | Small-mid; 100-2,000 students | $1,000-$5,000 |
| Schedule25 | Per institution (enterprise) | Universities; 1,000-40,000 students | $20,000-$100,000+ |
| FET | Free (open source) | Any | $0 |
| Gibbon | Free (open source) | Any | $0 |
| **EduClaw Scheduling** | Free (open source) | Any | **$0** |

**Market opportunity:** EduClaw Scheduling undercuts every commercial product at $0, while providing native SIS + ERP integration that no dedicated scheduling tool offers.

---

*Sources: FET Wikipedia entry, FET official documentation (lalescu.ro), Gibbon documentation (docs.gibbonedu.org), PowerScheduler User Guide (Macomb ISD), Infinite Campus Scheduling Reports documentation, aSc TimeTables website, SchoolInsight Advanced Scheduling feature page, CollegeNET Schedule25 product page, Aspen/Follett schedule pattern documentation*
