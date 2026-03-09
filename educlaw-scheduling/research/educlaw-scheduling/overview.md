# EduClaw Advanced Scheduling — Industry Overview

## 1. Domain Definition

**Master scheduling** is the process of building a school's complete instructional plan for a term: which courses will be offered, when they will meet, which instructor will teach each section, and in which room — while satisfying constraints around instructor availability, room capacity, student demand, and curriculum requirements.

Advanced scheduling extends beyond simple "create a section with a time slot" to encompass:
- **Schedule pattern management** — Traditional, block, rotating, trimester variants
- **Conflict resolution** — Proactive detection and resolution of double-bookings
- **Room optimization** — Smart assignment based on capacity, type, and equipment
- **Course request-driven building** — Schedule built from analyzed student demand
- **Master schedule lifecycle** — Draft → build → review → publish → lock workflow

### Why Scheduling Is Separate from Core EduClaw

EduClaw v1 provides basic section creation with a simple time slot model (`days_of_week`, `start_time`, `end_time`). This covers ~60% of school scheduling needs (small K-8 schools, simple semester-based higher ed programs). The remaining 40% — high schools with block schedules, middle schools with rotating schedules, colleges with complex room optimization — requires a dedicated scheduling engine. This sub-vertical delivers that engine.

---

## 2. Market Segments and Scheduling Complexity

### 2.1 K-12 Scheduling by Institution Type

| Institution Type | Schedule Complexity | Common Pattern | Key Scheduling Challenges |
|-----------------|--------------------|--------------|-----------------------------|
| **Elementary (K-5)** | Low | Self-contained classroom, fixed daily schedule | Specialist scheduling (art, music, PE) across multiple classrooms |
| **Middle School (6-8)** | Medium | Team-based, departmentalized, rotating | Team planning periods, exploratory courses, flexible blocks |
| **High School (9-12)** | High | Block, rotating drop, or traditional | Course requests, singleton sections, IEP accommodations, AP courses |
| **Private/Charter K-12** | Varies | Often hybrid or custom | Greater flexibility, smaller class sizes, unique program requirements |

### 2.2 Higher Education Scheduling

| Institution Type | Schedule Complexity | Key Challenges |
|-----------------|--------------------|--------------------|
| **Community College** | Medium | Evening/weekend sections, lab scheduling, adjunct faculty |
| **4-Year University** | High | Multi-building optimization, cross-listed sections, large lecture halls |
| **Professional School** | Very High | Clinical rotations, cohort scheduling, accreditation constraints |

### 2.3 EduClaw Scheduling Target

**Primary Market (v1 of scheduling sub-vertical):**
- **High schools** (grades 9-12): Most complex K-12 scheduling; highest ROI from automation
- **Middle schools** (grades 6-8): Rotating schedules; team-based planning
- **Community colleges**: Semester-based with evening/hybrid sections

**Secondary Market (v2 extensions):**
- Large university course optimization (1,000+ sections)
- Clinical/rotation scheduling for nursing/medical programs

---

## 3. Key Scheduling Concepts

### 3.1 Schedule Pattern Types

| Pattern | Description | Best For |
|---------|------------|---------|
| **Traditional (7-8 period)** | Students attend same 6-8 classes every day, each ~45-55 minutes | Most K-12, many community colleges |
| **4x4 Block** | Students take 4 classes per semester, meeting daily for ~90 minutes. Complete a full year's content in one semester | High schools wanting longer instructional periods |
| **A/B Block (Alternating)** | Students take 8 classes but alternate days (Day A classes on Mon/Wed, Day B on Tue/Thu). All 8 classes each week | High schools wanting block periods without losing year-long continuity |
| **Rotating Drop** | 7-8 periods rotate daily; students attend 5-6 per day, each period dropping once per cycle | High schools with 8-period days; reduces early/late period disadvantage |
| **Trimester** | Year divided into 3 terms (~12 weeks each); students take concentrated courses each term | Middle schools; some progressive high schools |
| **Modified Block / Hybrid** | Combines block days (Mon/Fri) with traditional days (Tue-Thu) | Flexibility for laboratory sciences or project-based learning |
| **Semester (higher ed)** | Standard 15-16 week semester with MWF, TR, or M-F patterns | Community colleges, universities |
| **Custom** | Institution-defined multi-day cycle (e.g., 6-day cycle in Jesuit schools) | Private schools, international schools |

### 3.2 Core Entities in Scheduling

| Entity | Description |
|--------|-------------|
| **Master Schedule** | The complete term-level document showing all sections, times, rooms, instructors |
| **Schedule Pattern** | Named template defining the cycle length, day types, and period structure |
| **Bell Period** | A named time slot within a day (e.g., "Period 1: 8:00-8:50", "Block A: 8:00-9:30") |
| **Day Type** | A named day within a scheduling cycle (e.g., "Day A", "Day B", "Monday", "Tuesday") |
| **Section Meeting** | A specific meeting of a section: section + day_type + period + room + instructor |
| **Course Request** | A student's pre-registration request for a specific course, used to drive scheduling |
| **Conflict** | A scheduling clash: room double-booking, instructor double-booking, student section overlap |
| **Singleton Section** | A section offered only once; if two singletons share students, they CANNOT be scheduled simultaneously |
| **Room Booking** | Formal reservation of a room for a specific period and day type |
| **Instructor Constraint** | Availability or preference rule for an instructor (unavailable Mondays before Period 3, max 4 consecutive periods, etc.) |

### 3.3 The Conflict Matrix

The conflict matrix is the most important analytical tool in scheduling:
- **Rows:** Course sections (or course requests)
- **Columns:** Periods/time slots
- **Cell values:** Shared students (conflicts between courses that share students cannot be scheduled simultaneously)

High-quality scheduling software minimizes conflicts (student unfulfilled requests) and maximizes **course fulfillment rate** — the % of students who get all requested courses. Industry benchmark: **95%+ fulfillment rate** is considered excellent.

### 3.4 Scheduling Quality Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Course Fulfillment Rate** | % of student course requests satisfied | ≥ 95% |
| **Section Balance** | Variance in enrollment across sections of same course | Low variance (CV < 15%) |
| **Room Utilization** | % of room capacity used on average | 70-85% (not too empty, not overcrowded) |
| **Instructor Load Balance** | Variance in teaching periods across instructors | Equitable distribution |
| **Singleton Conflict Rate** | % of singleton sections with irresolvable time conflicts | < 2% |

---

## 4. The Master Scheduling Process

The master scheduling process typically runs 3-6 months before the term begins:

```
Phase 1: Demand Analysis (8-12 weeks before term)
├── Collect student course requests
├── Analyze demand by course
├── Identify singleton sections (rare, must not conflict)
└── Estimate required sections per course

Phase 2: Schedule Building (6-8 weeks before term)
├── Define/select schedule pattern for the term
├── Assign courses to periods (accounting for constraints)
├── Assign instructors to sections
├── Assign rooms to sections
└── Resolve conflicts iteratively

Phase 3: Review and Refinement (4-6 weeks before term)
├── Run conflict analysis
├── Load students into sections (trial placement)
├── Check fulfillment rate
├── Manual adjustments
└── Finalize section sizes (open/cancel based on demand)

Phase 4: Publishing (2-4 weeks before term)
├── Publish master schedule to counselors/teachers
├── Open enrollment for students
└── Lock schedule (prevent further changes)

Phase 5: Active Term Adjustments (during term)
├── Add/drop processing
├── New section additions (if demand exceeds supply)
└── Room/instructor reassignments
```

---

## 5. Market Size and Growth

| Segment | Size | Notes |
|---------|------|-------|
| **Education Scheduling Software (Global, 2025)** | ~$1.2B (est.) | Sub-segment of $27.8B education software market |
| **K-12 Scheduling Specifically** | ~$400-600M | High schools drive majority of value |
| **CAGR (2025-2030)** | ~12-14% | Driven by AI adoption and cloud migration |

### Key Market Players
- **PowerSchool** with PowerScheduler module — dominant K-12 position
- **Infinite Campus** Scheduling — strong in public districts
- **aSc TimeTables** — popular in private/international schools globally
- **Rediker Super Schedule Builder** — mid-market K-12
- **Schedule25/CollegeNET** — university scheduling focus
- **Gibbon** — open source, international schools

---

## 6. Why Schools Need Advanced Scheduling Software

### Pain Points Without Advanced Scheduling
1. **Spreadsheet chaos** — Many schools still build master schedules in Excel. A typical high school schedule involves 100+ sections, 50+ instructors, 20+ rooms, and 500+ students — Excel doesn't scale.
2. **High conflict rates** — Manual scheduling produces 15-25% unfulfilled student requests vs. <5% with software
3. **Time cost** — Manual master scheduling takes 200-400 hours of administrator time; software reduces this to 20-50 hours
4. **Room waste** — Manual assignment averages 50-60% room utilization; optimized assignment reaches 75-85%
5. **Instructor inequity** — Manual scheduling creates uneven loads; software balances across staff

### Compelling Events for Software Adoption
- Growing student population (manual process breaks down above ~300 students)
- Adding block scheduling (too complex to manage manually)
- New building (room optimization needed)
- Staff reduction (must do more with less)
- State reporting requirements (scheduling data needed for accountability)

---

## 7. Integration with EduClaw Parent

EduClaw Scheduling sits as a focused sub-vertical on top of the parent EduClaw system:

```
ERPClaw Foundation (GL, Selling, Payments, HR)
         ↓
EduClaw Core (Students, Academics, Attendance, Grading, Fees)
         ↓
EduClaw Advanced Scheduling (Master Schedule, Patterns, Conflicts, Room Assignment)
```

The scheduling module **consumes** from the parent:
- Course catalog (`educlaw_course`)
- Room inventory (`educlaw_room`)
- Instructor profiles (`educlaw_instructor`)
- Academic terms (`educlaw_academic_term`)
- Program requirements (`educlaw_program_requirement`)
- Student enrollments (`educlaw_program_enrollment`)

The scheduling module **produces** for the parent:
- Enriched sections (`educlaw_section` + `educlaw_section_meeting`)
- Master schedule (feeding enrollment opening)
- Room bookings (preventing double-booking)
- Conflict reports (administrative alerts)

---

## 8. EduClaw Scheduling Value Proposition

For schools already running EduClaw:
1. **Native integration** — No data re-entry; scheduling module reads existing students, courses, rooms, instructors
2. **AI-native interface** — "Build me a draft schedule for Fall 2026 using the A/B block pattern" via conversational interface
3. **Conflict-free by default** — All section meetings validated against room and instructor bookings at insert time
4. **Iterative workflow** — Draft → build → review → publish lifecycle with save/restore capability
5. **Multi-pattern support** — Traditional, block, rotating, trimester in one system
6. **Course request analytics** — Demand analysis before sections are created; no more guessing section counts

---

*Sources: MarketsandMarkets Education ERP, Planifica School Scheduling FAQ, aSc TimeTables documentation, SchoolInsight Advanced Scheduling feature page, PowerScheduler User Guide, Infinite Campus Scheduling Reports, Follett Aspen documentation, Gibbon timetabling docs, UConn Classroom Scheduling Overview*
