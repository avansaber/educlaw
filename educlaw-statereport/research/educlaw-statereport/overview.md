# Industry Overview: K-12 State Reporting & Ed-Fi Integration

**Product:** EduClaw State Reporting (educlaw-statereport)
**Research Date:** 2026-03-05

---

## 1. What Is K-12 State Reporting?

K-12 state reporting is the systematic process by which Local Education Agencies (LEAs — school districts and charter schools) collect, validate, and submit student, staff, and institutional data to State Education Agencies (SEAs) and ultimately to the federal government. This data drives:

- **State funding allocation** — Average Daily Attendance (ADA/ADM) determines per-pupil funding
- **Federal funding** — Title I, IDEA Part B, Title III, and others are funded based on reported counts
- **Accountability** — ESSA school rating systems, graduation rates, chronic absenteeism metrics
- **Federal compliance** — IDEA 618 data collections, Civil Rights Data Collection (CRDC), EDFacts

Every state in the US operates its own data collection system, but increasingly these are built on the **Ed-Fi ODS/API standard**, enabling SIS vendors to implement a single integration pattern that works across multiple states.

---

## 2. Market Context

### Scale of the Problem

- **~13,000 school districts** in the US, each reporting annually to their SEA
- **~50.7 million K-12 students** tracked across SIS platforms
- **74 active EDFacts file specifications** submitted to the federal government annually
- **Each state** has unique collection windows, data elements, and validation rules on top of federal requirements
- **Annual reporting cycles** with high-stakes consequences for funding errors or compliance failures

### Why SIS Vendors Must Own State Reporting

State reporting cannot be delegated to a separate system without significant data loss. The SIS is the system of record for:
- Student enrollment and demographics
- Attendance (the basis for ADA funding)
- Course enrollment and grades
- Staff assignments

Any reporting system must either be deeply integrated with or part of the SIS. This is exactly why PowerSchool, Infinite Campus, and Skyward all have embedded state reporting modules.

### Market Shift: Ed-Fi Standardization

Prior to ~2018, every state had a proprietary extract format. SIS vendors maintained state-specific extract modules (extremely costly). Ed-Fi is changing this:
- **30+ states** now use Ed-Fi as their state reporting pipeline
- SEAs publish Ed-Fi API specifications; SIS vendors implement once
- Data flows continuously (not batch extracts), enabling real-time error correction
- **Ed-Fi ODS/API v7.3** (Dec 2024) is the current standard; v5.x and v6.x still widely deployed

---

## 3. Key Stakeholders & Entities

### Organizational Hierarchy

```
Federal (ED)
    ↑
State Education Agency (SEA) — e.g., California CDE, Texas TEA
    ↑
Local Education Agency (LEA) — school district or charter authority
    ↑
School — individual campus
    ↑
Classroom — teacher + students + course section
```

### Key Entity Types in State Reporting

| Entity Type | Description | Examples |
|------------|-------------|---------|
| **Student** | Individual learner with SSID (State Student ID) | Demographics, special programs, enrollment history |
| **Staff** | Teachers, paraprofessionals, administrators | FTE, certifications, assignments |
| **Education Organization** | LEA, School, State Agency | NCES IDs, Ed-Fi org codes |
| **Enrollment** | Student-to-school membership | Entry/exit dates, grade level, entry type |
| **Attendance** | Daily and period-level presence | ADA, ADM, chronic absenteeism |
| **Discipline** | Behavioral incidents and consequences | Suspension days, expulsion, firearm incidents |
| **Special Education** | IDEA Part B services | Disability category, educational environment, IEP |
| **English Learners** | EL program participation | Language background, proficiency, reclassification |
| **Assessment** | State and local test results | Proficiency levels, participation rates |
| **Staff Assignment** | Teacher-to-section relationships | Subject, FTE, certification status |
| **Program Participation** | Title I, SPED, EL, homeless, foster care | Program entry/exit dates |

---

## 4. Federal Reporting Programs

### EDFacts (74 Active File Specifications)

EDFacts is the primary federal K-12 data collection system. States submit files annually via the **EDPass** portal. Key categories:

| Category | File Examples | Key Data |
|----------|--------------|---------|
| **Special Education (IDEA)** | Child count, discipline, educational environments, exiting, assessment | Disability category, placement, services |
| **Academic Achievement** | Math, reading/ELA, science proficiency | Achievement levels, participation rates |
| **Accountability** | Graduation rates, chronic absenteeism | 4-year cohort rate, ≥10% absent count |
| **Demographics** | EL counts, economically disadvantaged, homeless, foster care | Program participation flags |
| **Staffing** | Teacher counts, paraprofessionals, related services | FTE, certification status |
| **Discipline** | Removals, suspensions, expulsions, firearms | Incident type, student subgroups |
| **Title Programs** | Title I schools, EL services | Funding eligibility, program enrollment |

### Civil Rights Data Collection (CRDC)
- Biennial survey (every 2 years) by OCR
- Comprehensive data on access and equity: advanced courses, discipline by race/disability/gender, harassment, school climate
- Every LEA must submit; high compliance burden

### IDEA 618 Data Collections (8 annual submissions)
1. Child count and educational environments
2. Personnel (special ed staff)
3. Exiting (graduation, drop-out, reaching age)
4. Discipline (suspensions/expulsions of IDEA students)
5. Assessment
6. Dispute resolution
7. State Performance Plan/APR
8. Maintenance of Effort

---

## 5. State-Level Reporting Systems

### Common State Systems

| State | System | Notes |
|-------|--------|-------|
| California | CALPADS | 4 annual snapshots (Fall, Spring, EOY 1-4) |
| Texas | TSDS / PEIMS | TEA's TSDS uses Ed-Fi; PEIMS is the state data model |
| Wisconsin | WISEdata | Full Ed-Fi implementation; multi-vendor SIS |
| Minnesota | MDE Ed-Fi | Ed-Fi-based pipeline |
| North Carolina | NC SIS (Infinite Campus) | Statewide Infinite Campus deployment |
| Florida | FLDOE / MSID | Florida-specific system; working toward Ed-Fi |
| New York | NYSSIS | Complex state-specific system |
| South Carolina | Ed-Fi/PowerSchool | Ed-Fi with PowerSchool as primary SIS |

### Collection Window Types

| Window Name | Timing | Key Data Collected |
|------------|--------|-------------------|
| **Fall Enrollment** | Oct/Nov | Student enrollment, demographics, program flags |
| **Winter** | Jan/Feb | Attendance, special education, EL updates |
| **Spring** | Mar/Apr | Enrollment updates, staff data |
| **EOY (End of Year)** | Jun/Jul | Attendance summaries, grades, completions, discipline |
| **Summer** | Jul/Aug | Corrections, final amendments |

---

## 6. The ADA/ADM Funding Calculation

**Average Daily Attendance (ADA)** is the single most financially consequential state reporting metric for most LEAs. It determines per-pupil funding allocation.

### How ADA Works
```
ADA = Total Student-Days Present / Total School Days in Period
ADM = Total Student-Days Enrolled / Total School Days in Period

For each student per day:
  Present = 1.0 FTE
  Half Day = 0.5 FTE
  Absent (excused) = varies by state (some count, some don't)
  Absent (unexcused) = 0.0 FTE
  Tardy (>x minutes) = partial credit in some states
```

### ADA Funding Example
A district with 1,000 students and 95% ADA vs. 93% ADA over 180 school days:
- At 95%: 950 ADA × $10,000/student = **$9.5M funding**
- At 93%: 930 ADA × $10,000/student = **$9.3M funding**
- **Difference: $200,000 per year** from 2% attendance improvement

This is why ADA reporting is mission-critical and why ADA recovery services (correcting under-reported attendance) is a significant market.

---

## 7. Data Quality & Validation

### Three-Level Validation Model (Ed-Fi standard)

| Level | Trigger | Examples |
|-------|---------|---------|
| **Level 1** | At API POST time | Required fields missing, invalid date formats, unknown descriptor values |
| **Level 2** | After data lands in ODS | Cross-entity rule violations (e.g., attendance date outside enrollment period) |
| **Level 3** | Business rule engine | State-specific: student must have valid EL assessment if EL-flagged, grade level must advance year-over-year |

### Common Validation Errors in Practice

- Student has attendance records outside enrollment dates
- SPED student missing disability category
- EL student has no English proficiency assessment
- Staff assignment references undefined course section
- Graduation cohort member missing exit reason
- Discipline incident missing race/ethnicity subgroup data
- Duplicate SSIDs across LEAs

### Data Quality Tools Available
- **Level Data** — Commercial validation-as-a-service platform
- **WISEdata Portal** (Wisconsin) — State-provided validation dashboard
- **Generate** (CIID) — Open-source federal reporting with built-in validations
- **Ed-Fi ODS/API** — Level 1 validations built-in

---

## 8. Ed-Fi Technical Architecture

### Component Overview

```
LEA (District)
├── SIS (EduClaw + educlaw-statereport)
│   ├── Ed-Fi API Client (POST resources to state ODS)
│   └── Data Mapping Engine (EduClaw → Ed-Fi UDM)
│
State Ed-Fi Infrastructure
├── LEA ODS (per-district data store)
├── State ODS (aggregated, multi-year)
├── Validation Engine (Level 2/3 rules)
├── Error Portal (LEA sees their errors)
└── SLDS / Data Warehouse (reporting, EDFacts generation)
│
Federal
└── EDPass / CRDC Submission Systems
```

### Ed-Fi ODS/API Key Resources (Entities)

| Domain | Core Resources |
|--------|---------------|
| **Education Organization** | LocalEducationAgency, School, StateEducationAgency |
| **Enrollment** | StudentSchoolAssociation (SSA), StudentEducationOrganizationResponsibilityAssociation |
| **Attendance** | StudentSchoolAttendanceEvent, StudentSectionAttendanceEvent |
| **Grades** | StudentSectionAssociation, Grade, CourseTranscript |
| **Staff** | Staff, StaffSchoolAssociation, StaffSectionAssociation |
| **Assessment** | AssessmentItem, StudentAssessment, ObjectiveAssessment |
| **Special Education** | StudentSpecialEducationProgramAssociation |
| **EL** | StudentLanguageInstructionProgramAssociation |
| **Discipline** | DisciplineIncident, StudentDisciplineIncidentAssociation |
| **Demographics** | StudentEducationOrganizationAssociation (race, programs) |
| **Calendar** | Calendar, CalendarDate, Session, GradingPeriod |

---

## 9. Vertical Product Opportunity

### Why This Vertical Matters

EduClaw already has the operational data. The gap is the **reporting layer** that transforms operational records into state-compliant submissions. This is where SIS vendors earn significant revenue:

- PowerSchool charges per-state compliance modules
- Infinite Campus's statewide contracts include reporting
- Districts pay premium for accurate state reporting (funding implications)

### Differentiation Opportunities for EduClaw State Reporting

1. **Open-source Ed-Fi client** — Most districts pay for this; EduClaw can include it
2. **State-agnostic validation** — Generic rule engine with pluggable state rulesets
3. **Real-time ADA dashboard** — Show funding impact of attendance in real time
4. **Submission audit trail** — Complete history of what was submitted when
5. **Error resolution workflow** — Task-based error assignment and resolution tracking
6. **Multi-state support** — One platform for districts operating across state lines (charter networks)

---

## 10. Key Terms & Acronyms

| Term | Definition |
|------|-----------|
| ADA | Average Daily Attendance — students present per day, basis for funding |
| ADM | Average Daily Membership — enrolled students per day |
| CRDC | Civil Rights Data Collection — biennial OCR survey |
| CEDS | Common Education Data Standards — federal vocabulary framework |
| EDFacts | Federal K-12 data collection system (74 file specs) |
| Ed-Fi | Education data interoperability standard; ODS/API platform |
| IDEA | Individuals with Disabilities Education Act — SPED law |
| IEP | Individualized Education Program — SPED service plan |
| LEA | Local Education Agency — school district |
| NCES | National Center for Education Statistics — assigns school/district IDs |
| ODS | Operational Data Store — Ed-Fi database instance |
| SEA | State Education Agency — state department of education |
| SIS | Student Information System — operational school data system |
| SSID | State Student Identifier — state-assigned unique student ID |
| SPED | Special Education |
| EL/ELL | English Learner / English Language Learner |
| FTE | Full-Time Equivalent — staffing measurement |
| ESSA | Every Student Succeeds Act — federal education law (2015) |
| FERPA | Family Educational Rights and Privacy Act — student data privacy |
