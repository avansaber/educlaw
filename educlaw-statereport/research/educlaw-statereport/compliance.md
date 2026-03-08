# Compliance & Regulatory Requirements: K-12 State Reporting

**Product:** EduClaw State Reporting (educlaw-statereport)
**Research Date:** 2026-03-05

---

## 1. Regulatory Framework Overview

K-12 state reporting compliance operates in a layered structure:

```
Federal Law (ESSA, IDEA, Title Programs)
    ↓
Federal Regulations (34 CFR Parts 200, 300, etc.)
    ↓
Federal Data Requirements (EDFacts, CRDC, IDEA 618)
    ↓
State Law (state education code)
    ↓
State Data Requirements (state SIS specs, Ed-Fi extensions)
    ↓
LEA Data Entry Requirements (SIS configuration, data quality)
```

EduClaw State Reporting must support all layers. The software doesn't enforce federal law directly — it ensures the data needed for compliance can be captured, validated, and submitted.

---

## 2. Ed-Fi Data Standard

### What It Is
The Ed-Fi Data Standard is an open data standard for K-12 student data exchange, developed and maintained by the Ed-Fi Alliance (a non-profit). It is **not a legal requirement** but has become the de facto technical standard for state reporting in the US.

### Current Versions
| Version | Status | School Years |
|---------|--------|-------------|
| Ed-Fi DS 6.x (ODS/API 7.x) | Current (2025) | 2026-2028 |
| Ed-Fi DS 5.x (ODS/API 6.x) | Supported | 2024-2028 |
| Ed-Fi DS 4.0 (ODS/API 5.x) | Extended support | 2024-2026 |
| Ed-Fi DS 3.x | Legacy | Being phased out |

### Ed-Fi Certification Levels

| Certification | Description | Required For |
|--------------|-------------|-------------|
| **Ed-Fi Certified** | Vendor has passed Ed-Fi Alliance conformance testing | Recommended for state contracts |
| **Ed-Fi Aligned** | Vendor follows Ed-Fi API design guidelines | Minimum for Ed-Fi integration |
| **State Extension** | Vendor supports state-specific Ed-Fi extensions | Required per state |

### Ed-Fi ODS/API REST Conventions
- **Authentication:** OAuth 2.0 Client Credentials Grant Flow
- **Encoding:** JSON (application/json)
- **API Style:** RESTful with CRUD operations; resource-centric
- **ID Strategy:** Natural keys (not UUIDs) for cross-system identity matching
- **Descriptor Pattern:** Controlled vocabularies using URI-based descriptor values
  - Example: `uri://ed-fi.org/GradeLevelDescriptor#Ninth grade`
- **Upsert Semantics:** PUT creates or updates based on natural key
- **Cascade Deletes:** Not supported; must delete child records first
- **Versioning:** API version in URL path (`/data/v3/`, `/data/v5/`)

### Ed-Fi Domain Compliance Requirements for State Reporting

| Domain | Key Resources | Required For |
|--------|---------------|-------------|
| **Education Organization** | LocalEducationAgency, School | All state reporting (foundation) |
| **Student Identity** | Student, StudentEducationOrganizationAssociation | All reporting; CRDC demographics |
| **Enrollment** | StudentSchoolAssociation, StudentProgramAssociation | ADA, enrollment counts |
| **Calendar** | Session, CalendarDate, GradingPeriod | ADA calculation, term boundaries |
| **Attendance** | StudentSchoolAttendanceEvent, StudentSectionAttendanceEvent | ADA, chronic absenteeism |
| **Staff** | Staff, StaffSchoolAssociation, StaffSectionAssociation | Teacher counts, FTE |
| **Grades** | StudentSectionAssociation, Grade, CourseTranscript | Graduation rate, achievement |
| **Assessment** | StudentAssessment, ObjectiveAssessment | Academic achievement EDFacts |
| **Special Education** | StudentSpecialEducationProgramAssociation | IDEA 618 data |
| **English Learner** | StudentLanguageInstructionProgramAssociation | EL counts, Title III |
| **Discipline** | DisciplineIncident, StudentDisciplineIncidentAssociation | IDEA discipline, CRDC |
| **Cohort** | StudentCohortAssociation | Graduation cohort tracking |

---

## 3. CEDS — Common Education Data Standards

### What It Is
CEDS (Common Education Data Standards) is a voluntary, national vocabulary framework maintained by the National Center for Education Statistics (NCES). It provides:
- Common definitions for 1,710+ K-12 data elements
- Crosswalk between state and federal data models
- Foundation for EDFacts and Generate

### CEDS vs. Ed-Fi
| Dimension | CEDS | Ed-Fi |
|-----------|------|-------|
| Purpose | Vocabulary/definitions | API/data exchange |
| Scope | All education levels (P-20) | Primarily K-12 |
| Format | Data element library | ODS/API platform |
| Adoption | Reference model | Active implementation |
| Mandatory | Voluntary | De facto standard |

### Key CEDS Element Groups Relevant to State Reporting

| Group | Element Count | Examples |
|-------|--------------|---------|
| **Demographic** | 85+ | Race/ethnicity, gender, DOB, SSID |
| **Enrollment** | 120+ | Entry type, exit type, grade level, program participation |
| **Attendance** | 40+ | Attendance status, ADA, ADM, membership |
| **Assessment** | 200+ | Proficiency level, accommodation types, assessment type |
| **Special Education** | 350+ | Disability category, IEP services, educational environment |
| **English Learner** | 80+ | Language, proficiency level, program type, reclassification |
| **Discipline** | 60+ | Incident type, action type, duration, IDEA flag |
| **Staff** | 150+ | Certification, FTE, assignment, evaluation |
| **Graduation** | 50+ | Diploma type, cohort year, exit reason |

### CEDS Race/Ethnicity Standard
CEDS aligns with OMB's federal race/ethnicity categories:
1. **Hispanic/Latino** (asked as separate question)
2. **American Indian or Alaska Native**
3. **Asian**
4. **Black or African American**
5. **Native Hawaiian or Other Pacific Islander**
6. **White**
7. **Two or More Races**

**Rule:** Hispanic/Latino is asked first. If yes, federal rollup = Hispanic regardless of race selection. Multi-racial non-Hispanic → "Two or More Races."

---

## 4. Federal Reporting Requirements

### 4.1 EDFacts — 74 Active File Specifications (SY 2024-25)

EDFacts is the US Department of Education's primary K-12 data collection. States submit annually via EDPass.

#### Category A: Special Education (IDEA Part B)
| File | Content | Frequency |
|------|---------|-----------|
| FS002 | Children with Disabilities (school age) — child count | Annual |
| FS089 | Children with Disabilities (early childhood) — child count | Annual |
| FS006 | Special Education Educational Environments (school age) | Annual |
| FS007 | Special Education Educational Environments (early childhood) | Annual |
| FS009 | Children with Disabilities — Exiting (ages 14-21) | Annual |
| FS048 | Special Education Assessment | Annual |
| FS052 | Special Education Discipline — suspensions/expulsions | Annual |
| FS053 | Special Education Dispute Resolution | Annual |
| FS143 | Special Education Personnel | Annual |

#### Category B: Academic Achievement
| File | Content |
|------|---------|
| FS113 | Math achievement (state assessment proficiency) |
| FS114 | Reading/ELA achievement |
| FS175 | Science achievement |
| FS185 | Math participation rate |
| FS188 | Reading/ELA participation rate |
| FS086 | Graduation rate (4-year cohort) |
| FS150 | Adjusted cohort graduation rate |

#### Category C: Demographics & Programs
| File | Content |
|------|---------|
| FS033 | EL (English Learner) enrollment |
| FS101 | Homeless enrollment |
| FS119 | Migrant enrollment |
| FS139 | Economically disadvantaged enrollment |
| FS129 | Foster care enrollment |

#### Category D: Discipline
| File | Content |
|------|---------|
| FS005 | Discipline — firearm incidents |
| FS043 | Discipline — offenses and actions (non-IDEA) |
| FS088 | Discipline — removals (IDEA students) |

#### Category E: Staffing
| File | Content |
|------|---------|
| FS099 | Teacher counts by subject |
| FS067 | Staff counts (all staff) |
| FS112 | Paraprofessional counts |

#### Category F: Accountability (ESSA)
| File | Content |
|------|---------|
| FS196 | Chronic absenteeism |
| FS199 | Per-pupil expenditure |
| FS204 | School level expenditure |

### 4.2 Civil Rights Data Collection (CRDC)

**Agency:** U.S. Department of Education, Office for Civil Rights (OCR)
**Frequency:** Biennial (every 2 years); most recent 2021-22 collection
**Scope:** Every public LEA in the US (~16,000 districts, ~98,000 schools)

#### CRDC Data Categories

| Category | Key Data Elements |
|----------|-----------------|
| **Enrollment** | Total enrollment by race/sex; IDEA; 504; EL; gifted |
| **Discipline** | ISS, OSS, expulsions by race/sex/disability; school-related arrests; referrals |
| **Courses & Programs** | AP enrollment, dual enrollment, gifted & talented by subgroup |
| **Staff** | Teacher counts, FTE, inexperienced teachers, emergency certification |
| **School Climate** | Restraint, seclusion, harassment, bullying |
| **Preschool** | Pre-K enrollment, discipline |
| **Athletics** | Participation by sex |
| **Testing** | SAT/ACT participation, advanced coursework |

#### CRDC Compliance Requirements for SIS
1. **CRDC School ID** — each school must have a valid CRDC school ID (= NCES school ID)
2. **Race/Ethnicity on all students** — cannot omit race; affects all disaggregation
3. **Disability flags** — IDEA vs. Section 504 (different from state SPED; district must track both)
4. **Discipline coding** — must distinguish: In-School Suspension (ISS), Out-of-School Suspension 1 day, OSS >1 day, expulsion, referral to law enforcement, school-related arrest
5. **Restraint and Seclusion** — required reporting; high sensitivity
6. **EL flag** — distinct from IDEA; can overlap

### 4.3 IDEA 618 Data Collections

IDEA Section 618 mandates annual data collection by OSEP (Office of Special Education Programs).

#### Eight IDEA 618 Authorized Collections

| Collection | Description | Key Data |
|-----------|-------------|---------|
| **Child Count** (Part B, Ages 3-21) | Number of SPED students by disability, educational environment, race, grade | 14 disability categories |
| **Educational Environments** | Placement type (% time in regular class) | Regular class ≥80%, <40%, <21%; separate school; residential |
| **Exiting** | How students left SPED (ages 14-21) | Graduated, dropped out, reached max age, moved (not known), died |
| **Personnel** | Full-time equivalent SPED staff | By personnel type; state vs. LEA employed |
| **Discipline** | Suspensions/removals of SPED students | By disability, race, sex; days removed |
| **Assessment** | SPED student assessment participation and performance | Alternate assessment, standard assessment |
| **Dispute Resolution** | Mediation, due process hearings | Outcomes |
| **Maintenance of Effort** | LEA financial compliance | Expenditure comparisons |

#### IDEA Disability Categories (14 Federal Categories)

| Code | Disability |
|------|-----------|
| AUT | Autism |
| DB | Deaf-Blindness |
| DD | Developmental Delay (ages 3-9) |
| ED | Emotional Disturbance |
| HI | Hearing Impairment |
| ID | Intellectual Disability |
| MD | Multiple Disabilities |
| OHI | Other Health Impairment |
| OI | Orthopedic Impairment |
| SLD | Specific Learning Disability |
| SLI | Speech or Language Impairment |
| TBI | Traumatic Brain Injury |
| VI | Visual Impairment |
| (varies) | Developmental Delay (state-specific) |

#### IDEA Educational Environments (Placement Types)

| Code | Description |
|------|-------------|
| RC_80 | Regular class ≥80% of time |
| RC_40_79 | Regular class 40-79% of time |
| RC_LT40 | Regular class <40% of time |
| SC | Separate class |
| SS | Separate school |
| RF | Residential facility |
| HH | Home or hospital |

---

## 5. State-Specific Requirements (SIS Requirements)

### Common State Data Elements (Beyond Federal)

Every state adds its own required data elements on top of federal requirements. Common additions:

| State Extension | Description | States (Examples) |
|----------------|-------------|------------------|
| **State Student ID (SSID)** | State-assigned unique student identifier | All 50 states |
| **School of Residence** | Where student lives vs. where enrolled | CA, TX, FL, NY |
| **Instructional Program Code** | State-specific program participation codes | CA (CALPADS Program Code) |
| **Language Background** | Home language + English proficiency instrument | CA, TX, NY, IL |
| **Teacher of Record** | State-specific teacher-student linkage for evaluation | Many ESSA-required states |
| **Course Codes** | State course code system (SCED codes or state-specific) | All states |
| **Credential Type** | State teaching credential type/endorsement | All states |
| **Title I School Status** | Which schools receive Title I funds | All states (from SEA) |
| **Section 504** | 504 plan students (not IDEA-eligible) | Required for CRDC, most states |

### NCES Identifiers — Required for All Federal Reporting

| ID Type | Description | Source |
|---------|-------------|--------|
| **NCES LEA ID** | 7-digit unique ID for each school district | NCES Common Core of Data |
| **NCES School ID** | 12-digit unique ID for each school | NCES Common Core of Data |
| **NCES State Code** | 2-digit federal FIPS state code | NCES |

These identifiers must be stored in EduClaw's organization tables and included in all Ed-Fi and EDFacts submissions.

### State-Specific Collection Window Requirements

| State | System | Windows | Notes |
|-------|--------|---------|-------|
| California | CALPADS | Fall 1, Fall 2, EOY 1-4 | 6 windows; very detailed |
| Texas | TSDS/PEIMS | Fall, Spring, Summer | Ed-Fi-based; PEIMS data model |
| Wisconsin | WISEdata | Fall, 3rd Friday, EOY | Full Ed-Fi; multi-SIS |
| Minnesota | MDE | Fall, Spring | Ed-Fi-based |
| Florida | FLDOE | 3 survey periods + EOY | Florida-specific format |
| New York | NYSSIS | Multiple | Complex; state-specific |
| North Carolina | NC Accountability | Per IC contract | Statewide IC deployment |

### SCED Course Codes

The School Codes for the Exchange of Data (SCED) is a voluntary national classification system for course codes maintained by NCES. Used for:
- EDFacts course completion reporting
- State course alignment with national standards
- Transcript exchange between institutions

SCED format: `SSSSNN` where `SSSS` = subject area code, `NN` = course level code

EduClaw must support mapping internal course codes to SCED codes for EDFacts reporting.

---

## 6. FERPA — Privacy Compliance for Reporting

**Law:** Family Educational Rights and Privacy Act (20 U.S.C. § 1232g)

### FERPA Implications for State Reporting

State reporting involves sharing student data with SEAs and the federal government. FERPA permits this under the **"School Official" exception** — state and federal agencies receiving data are school officials with legitimate educational interest.

However, EduClaw must:

1. **Log all data exports** — `educlaw_data_access_log` already tracks access; state reporting exports must be logged
2. **Respect directory information opt-outs** — `educlaw_student.directory_info_opt_out` must be checked when generating any public-facing reports
3. **De-identify small cell counts** — EDFacts and CRDC suppress cells with <10 students to prevent re-identification
4. **Document data sharing agreements** — State and federal recipients must have signed data sharing agreements (MOU/DUA)
5. **Consent not required for official reporting** — Routine state/federal reporting does not require FERPA consent

### Data Suppression Rule (Small Cell Size)

**Federal standard:** Suppress any cell with N < 10 students.

This means state reporting modules must:
- Flag cells below threshold in any disaggregated report
- Replace with `--` or `NE` (Not Enough) in export files
- Not calculate derived counts that could reveal suppressed cells

---

## 7. Ed-Fi Descriptor Requirements

Ed-Fi uses "descriptors" (controlled vocabularies) instead of raw codes. EduClaw must map internal codes to Ed-Fi descriptor URIs.

### Key Descriptor Namespaces

| Descriptor | Ed-Fi Namespace | Example Values |
|-----------|----------------|----------------|
| **Grade Level** | `uri://ed-fi.org/GradeLevelDescriptor#` | `Kindergarten`, `First grade`, `Ninth grade` |
| **Race** | `uri://ed-fi.org/RaceDescriptor#` | `White`, `Black or African American`, `Asian` |
| **Sex** | `uri://ed-fi.org/SexDescriptor#` | `Male`, `Female`, `Not Selected` |
| **Disability** | `uri://ed-fi.org/DisabilityDescriptor#` | `Autism`, `Intellectual Disability` |
| **Language** | `uri://ed-fi.org/LanguageDescriptor#` | `eng`, `spa`, `vie` (ISO 639) |
| **Attendance Event** | `uri://ed-fi.org/AttendanceEventCategoryDescriptor#` | `Unexcused Absence`, `Excused Absence`, `Tardy` |
| **Exit Withdraw Type** | `uri://ed-fi.org/ExitWithdrawTypeDescriptor#` | `Graduated`, `Dropped out`, `Transferred` |
| **Entry Type** | `uri://ed-fi.org/EntryTypeDescriptor#` | `Next year school`, `Transfer from public school` |
| **Discipline Incident** | `uri://ed-fi.org/BehaviorDescriptor#` | `Bullying`, `Drug Violation`, `Weapons Violation` |
| **Discipline Action** | `uri://ed-fi.org/DisciplineDescriptor#` | `Out of School Suspension`, `Expulsion` |
| **Educational Environment** | `uri://ed-fi.org/SpecialEducationSettingDescriptor#` | `Regular Early Childhood Program`, various |
| **Program Type** | `uri://ed-fi.org/ProgramTypeDescriptor#` | `Special Education`, `English Language Instruction` |

### State Extension Descriptors

States add their own descriptor namespaces. Example:
- `uri://mn.edu/GradeLevelDescriptor#PreK` — Minnesota-specific grade level
- `uri://tx-rsp.edu/ProgramCode#101` — Texas program participation code

EduClaw must support configurable descriptor namespaces per state.

---

## 8. Compliance Checklist for EduClaw State Reporting

### Data Collection Requirements
- [ ] Student race/ethnicity (multi-select, federal rollup)
- [ ] Student gender (including non-binary for state reporting)
- [ ] State Student ID (SSID) storage per student
- [ ] NCES LEA ID and School ID per organization
- [ ] EL status + English proficiency level + home language
- [ ] Special Education disability category + educational environment
- [ ] Section 504 status (separate from IDEA)
- [ ] Economic disadvantage indicator (free/reduced lunch or direct cert)
- [ ] Homeless status (McKinney-Vento)
- [ ] Foster care status
- [ ] Migrant education program participation
- [ ] Discipline incidents with required CRDC categories
- [ ] Teacher certification/credential storage
- [ ] SCED course codes on all courses

### Submission Requirements
- [ ] Ed-Fi OAuth 2.0 client authentication
- [ ] Ed-Fi resource mapping (EduClaw → Ed-Fi UDM)
- [ ] Ed-Fi descriptor mapping (internal codes → descriptor URIs)
- [ ] Collection window definition and enforcement
- [ ] Snapshot freeze capability
- [ ] Validation at all three levels (format, cross-entity, business rules)
- [ ] Error logging and tracking
- [ ] Submission history audit trail
- [ ] Small cell suppression in any exported reports

### Privacy Requirements
- [ ] FERPA data access logging for all state report exports
- [ ] Directory information opt-out respected in exports
- [ ] Small cell size suppression (<10 students)
- [ ] Data sharing agreement documentation (metadata, not enforcement)
- [ ] COPPA compliance for students under 13 (already in educlaw_student)

### Federal Reporting Requirements
- [ ] EDFacts: Enrollment counts disaggregated by race, EL, SPED, economic status
- [ ] EDFacts: Attendance-based ADA/ADM calculation
- [ ] EDFacts: IDEA child count by disability category and educational environment
- [ ] EDFacts: Discipline by subgroup (race, disability, sex)
- [ ] EDFacts: Academic achievement proficiency by subject and subgroup
- [ ] EDFacts: Graduation cohort rate (4-year)
- [ ] EDFacts: Chronic absenteeism (≥10% absent)
- [ ] CRDC: All enrollment, discipline, staff, course access data by race/sex/disability
