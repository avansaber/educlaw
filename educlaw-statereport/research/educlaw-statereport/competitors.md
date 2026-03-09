# Competitor Analysis: K-12 State Reporting

**Product:** EduClaw State Reporting (educlaw-statereport)
**Research Date:** 2026-03-05

---

## 1. Competitive Landscape Overview

K-12 state reporting is not a standalone market — it's a feature set embedded in SIS platforms. The competitive analysis covers:

1. **Embedded SIS Modules** — PowerSchool, Infinite Campus, Skyward (the dominant commercial players)
2. **Open-Source Tools** — Generate (CIID), Ed-Fi ODS/API itself
3. **Middleware/Specialists** — Level Data, Aeries (Ed-Fi integrator)
4. **State-Provided Tools** — WISEdata (Wisconsin), CALPADS (California)

---

## 2. PowerSchool SIS — State Compliance Modules

**Type:** Commercial SIS with embedded state reporting
**Market Share:** ~40% of K-12 districts in the US (largest SIS vendor)
**Pricing:** SaaS subscription; state compliance add-on modules per state

### State Reporting Architecture

PowerSchool implements state reporting as **per-state compliance plug-ins**. Each state gets:
- A state-specific reporting module (separate codebase per state)
- State-specific extract formats (Ed-Fi API or flat file)
- State-specific validation rules

### Key Features

| Feature | Details |
|---------|---------|
| **Ed-Fi Integration** | Native Ed-Fi publisher; ODS/API alignment varies by state; data published via Ed-Fi REST endpoints |
| **State Templates** | Each US state has its own module with state-specific data elements, validation, and export |
| **CRDC Reporting** | Built-in CRDC report generator; filters by race, disability, gender for each data category |
| **IDEA Compliance** | Special education IEP tracking; disability category codes; IDEA 618 data collection |
| **Data Publishing Pipeline** | Scheduled nightly sync or on-demand publish to state Ed-Fi ODS |
| **Error Management** | State-specific error codes displayed in compliance console; error prioritization |
| **Collection Windows** | Pre-configured windows per state; lock/unlock capability |
| **Audit Trail** | Submission history per collection window |

### Ed-Fi Implementation (South Carolina Example)
- Config: Enable Ed-Fi support per school, enter state ODS URL + OAuth credentials
- Data sync: Automatic background sync; manual trigger available
- Error handling: Errors displayed in "Ed-Fi Data Publishing" console with error codes and field-level explanations
- Mapping: PowerSchool internal fields mapped to Ed-Fi descriptors via configuration tables

### PowerSchool State Reporting Data Flow
```
PowerSchool DB → State Compliance Engine → Ed-Fi Publisher → State ODS
                        ↓
              Validation Error Console (per LEA)
                        ↓
              Compliance Dashboard (collection window status)
```

### Strengths
- Largest installed base; most states have PowerSchool-specific documentation
- Per-state modules are deeply customized to state requirements
- Strong CRDC and IDEA module
- Good error messaging (field-level error codes from state)

### Weaknesses
- Each state module is a separate product; inconsistent UX across states
- Very expensive; state compliance add-ons priced separately
- Difficult to customize or extend
- No open data model; black box reporting

### Relevant Data Elements Tracked (Beyond Basic SIS)
- **CRDC School ID** — school-level identifier for CRDC submission
- **Race/Ethnicity** — both federal (5 race + Hispanic) and state-specific codes
- **SPED disability categories** — IDEA disability type codes
- **EL status** — English proficiency level, language background
- **Economic disadvantage** — Free/reduced lunch eligibility (or direct certification)
- **Homeless status** — McKinney-Vento program flag
- **Discipline** — Incident type, action, days removed, IDEA/non-IDEA
- **Staff certifications** — Highly Qualified Teacher (HQT) flags, endorsements

---

## 3. Infinite Campus — State & Federal Reporting

**Type:** Commercial SIS with full state reporting suite
**Market Share:** ~20% of K-12 districts; holds statewide SIS contracts in multiple states
**Pricing:** SaaS subscription; state reporting included in base (for state contracts)

### Notable Statewide Implementations
- **North Carolina** — Statewide Infinite Campus deployment replacing PowerSchool; full state SIS
- **Montana** — EDUCATE system (state-branded Infinite Campus)
- **Delaware** — State SIS on Infinite Campus
- Multiple other states have district-level contracts

### State Reporting Architecture

Infinite Campus uses a **centralized state reporting framework** that is more unified than PowerSchool's per-state modules:
- Single state reporting console (Campus State Reporting)
- Ed-Fi integration built into core platform
- Real-time data quality monitoring
- Configurable reporting rules engine

### Key Features

| Feature | Details |
|---------|---------|
| **Campus State Reporting** | Central console for all state submissions; collection window tracking |
| **Ed-Fi Alignment** | Certified Ed-Fi provider; implements Ed-Fi ODS/API for state data pipeline |
| **Data Quality Dashboard** | Real-time data quality monitoring with student-level drill-down |
| **Threshold Alerts** | Alerts when data quality falls below configured thresholds |
| **Flexible Reporting Engine** | Report writer for ad hoc state reports; custom extracts |
| **Special Education** | Full IEP module; disability category; educational environment |
| **EL/Title III** | English learner program tracking; LPAC integration |
| **Discipline** | Full disciplinary incident workflow; CRDC-aligned data elements |
| **Cohort Graduation** | 4-year cohort graduation rate calculation |
| **Staff Reporting** | Staff FTE, certifications, evaluations |

### Infinite Campus State Reporting Modules (Included)
- Special Education Compliance Reporting
- English Learner Program Management
- State and Federal Reporting (Ed-Fi or state-specific)
- Civil Rights Data Collection (CRDC)
- Chronic Absenteeism reporting
- Behavior/Discipline Incident management

### Statewide SIS Module List (NC DPI)
Modules provided in North Carolina's statewide Infinite Campus include:
- Campus Student Information System
- Campus Scheduling
- Campus Health
- Campus Special Education
- Campus State Edition (state reporting)
- Campus Messenger (communications)
- Campus Mobile Portal (parent/student app)
- Campus Analytics

### Strengths
- More unified reporting framework than PowerSchool
- Deep special education integration
- Strong statewide contract experience (full-state deployments)
- Real-time data quality monitoring vs. batch validation

### Weaknesses
- Expensive for smaller districts
- Statewide contracts create vendor lock-in for individual districts
- Complex configuration for multi-school districts
- Less customizable for unique district needs

---

## 4. Skyward — Student Management Suite

**Type:** Commercial SIS with state reporting focus
**Market Share:** ~7% of K-12 districts; strong in Midwest/Texas
**Pricing:** SaaS subscription; state reporting included

### Ed-Fi Commitment
Skyward has made a public commitment to Ed-Fi integration as a core product direction. Key quote: "Districts aligned with the Ed-Fi standard benefit from streamlined state reporting submissions, reduced maintenance costs, and more local control."

### Key Features

| Feature | Details |
|---------|---------|
| **Ed-Fi Integration** | Native Ed-Fi publisher; participates in state data hubs (Michigan, others) |
| **State Reporting** | Supports all 50 states (varies by depth of integration) |
| **Family Access** | Parent portal integrated with state reporting data |
| **In-Progress Grade Reporting** | Unique feature: reports in-progress (not just final) grades to Ed-Fi ODS in real-time |
| **Data Hub Support** | Works with regional data hubs (WSIPC, Michigan Data Hub) for multi-district aggregation |
| **Staff Management** | Full HR/payroll integration with state staffing reports |
| **Special Education** | SPED module with IEP; state-specific IDEA reporting |

### Skyward's Unique Differentiator: In-Progress Grades
Skyward publishes in-progress grades to the Ed-Fi ODS, allowing states to monitor academic performance in real time rather than waiting for term-end grade submission. This is a significant Ed-Fi innovation not widely available from other SIS vendors.

### Strengths
- Strong Ed-Fi commitment and early adopter
- Regional data hub integration experience
- Good HR/payroll integration for staffing reports
- Strong in specific states (WI, MN, MI, TX)

### Weaknesses
- Smaller market share = less state-specific documentation
- Less feature-rich than PowerSchool for per-state edge cases
- Limited charter school focus

---

## 5. Generate (CIID) — Open-Source Federal Reporting

**Type:** Open-source state reporting application
**License:** Apache 2.0
**Developed By:** Center for the Integration of IDEA Data (CIID) / American Institutes for Research
**Installed In:** 12 states implemented, 10 preparing; 28 expressing interest

### What Generate Does

Generate is a **state-side** application (not district-side). It is installed in the SEA environment and:
1. Connects to the state's data warehouse or Ed-Fi ODS
2. Transforms data into **EDFacts file format** for federal submission
3. Validates data against CEDS/EDFacts business rules
4. Generates all 80 EDFacts files

### Architecture

```
District SIS
    ↓ (Ed-Fi API or ETL)
State ODS / Data Warehouse
    ↓
Generate (CIID Application)
    ↓ (validates and transforms)
EDPass Submission (US Dept of Ed)
```

### EDFacts Files Covered
Generate covers all 80 EDFacts files including:
- All 8 IDEA 618 data collections
- Academic achievement (Math, ELA, Science)
- Graduation rates
- Chronic absenteeism
- EL program data
- Title I school identification
- Discipline files
- Staff counts and FTE

### Technical Stack
- **Database:** SQL Server
- **Web Interface:** ASP.NET / C#
- **Background Processing:** .NET service workers
- **Data Format:** CEDS-aligned data model

### Generate's Data Flow from Ed-Fi
One documented integration path:
1. Ed-Fi ODS → Generate's CEDS staging database (via ETL connector)
2. Generate runs business rules on CEDS data
3. Generate produces EDFacts-format submission files
4. Files uploaded to EDPass

### Relevance to EduClaw State Reporting
- **Not a competitor for district-side** — Generate is a state agency tool
- **Complementary** — EduClaw State Reporting feeds data TO the state; Generate processes it on the state side
- **Open source reference** — Generate's CEDS data model is an excellent reference for what data elements state agencies need
- **Integration target** — Some states require LEAs to ensure their data passes Generate's validation rules

### Strengths (as reference architecture)
- Open source; can study data model
- CEDS-aligned; 1,710 data elements well documented
- Real-world validation rules for all 80 EDFacts files
- Authoritative on what federal reporting requires

---

## 6. Level Data — Validation Middleware

**Type:** Commercial data quality and validation middleware
**Model:** SaaS; integrates with any SIS via API

### What Level Data Does

Level Data sits between the SIS and the state reporting system, providing:
- **Real-time validation** as data enters the SIS
- **Pre-submission validation** against state and federal rules
- **Error dashboards** with student-level drill-down
- **Data quality scoring** over time
- **Multi-SIS support** — works with any SIS that has an API

### Key Features
- Rule library: 1,000+ pre-built validation rules (state and federal)
- Custom rule builder for district-specific rules
- Automated error assignment and tracking (assigns errors to the responsible data owner)
- Integration with Ed-Fi ODS for post-submission validation
- Historical trend analysis of data quality

### Relevance to EduClaw
- EduClaw State Reporting should build a validation engine that competes with Level Data's core offering
- Level Data is a separate SaaS product — EduClaw can embed this functionality natively
- The 1,000+ rule library is a reference for what validation rules need to be implemented

---

## 7. Aeries Software — SIS with Ed-Fi Focus

**Type:** Commercial SIS (primarily California)
**Focus:** California-specific compliance; Ed-Fi integration for Texas

### Relevant Features
- Deep CALPADS integration (California's state reporting system)
- Texas State Reporting via Ed-Fi (documented extensively)
- Ed-Fi API client built into SIS core
- Real-time data push to state Ed-Fi ODS

### Aeries Texas Ed-Fi Data Flow
1. Configure Ed-Fi connection (state ODS URL, OAuth credentials)
2. Enable Ed-Fi for each school
3. Sync data: students → demographics → enrollment → attendance → grades → discipline
4. Monitor sync status and errors in Ed-Fi console
5. Resolve errors, re-sync affected records
6. Confirm data in state portal

### Relevance
- Good reference implementation of Ed-Fi integration in a SIS
- Shows the specific Ed-Fi resources needed for full state reporting
- Texas documentation is publicly available and detailed

---

## 8. State-Provided Tools: CALPADS (California)

**Type:** State-operated SIS and reporting portal
**Scale:** ~6.2 million K-12 students in California

### CALPADS Data Collections

California operates **4 annual reporting windows** (plus supplemental windows):

| Window | Timing | Data Collected |
|--------|--------|---------------|
| **Fall 1** | Oct-Nov | Enrollment, demographics, program flags, staff |
| **Fall 2** | Dec-Jan | Special education child count, educational environment |
| **EOY 1** | Jun-Jul | Enrollment exits and changes |
| **EOY 2** | Aug-Sep | Course completion, graduation, retention |
| **EOY 3** | Aug-Sep | Cumulative enrollment, attendance, behavior incidents |
| **EOY 4** | Aug-Sep | Staff assignments and credentials |

### CALPADS Data Elements (Reference for EduClaw)

**Student-Level Required Fields:**
- SSID (State Student ID)
- Legal Name + Alias
- Date of Birth
- Gender (including non-binary options)
- Race/Ethnicity (multi-select + federal rollup)
- English Learner Status + language code
- Special Education eligibility + disability category
- Economic Disadvantage indicator
- Homeless/Foster Care status
- Migrant Education Program
- Grade Level
- District of Residence vs. School of Enrollment

**Attendance Required Fields:**
- Days in attendance (cumulative)
- Days absent (excused + unexcused)
- Chronic absenteeism flag (≥10% absent)

### CALPADS Lessons for EduClaw
1. **Race is multi-select** — students can have multiple racial identities; Hispanic/Latino is asked separately
2. **EL status has a lifecycle** — Initial identification → active EL → reclassified fluent English proficient (RFEP)
3. **SPED has educational environment codes** — not just a flag, but specific placement type
4. **Snapshots are truly frozen** — data cannot be changed after window closes without amendment process
5. **SSIDs are assigned by the state** — districts must request SSIDs for new students; matching is complex

---

## 9. Competitive Feature Matrix

| Feature | PowerSchool | Infinite Campus | Skyward | EduClaw SR (Target) |
|---------|------------|-----------------|---------|---------------------|
| Ed-Fi API Client | ✅ | ✅ | ✅ | ✅ Must have |
| State-specific modules | ✅ (per state) | ✅ (per state) | ✅ | ⚠️ Generic + config |
| Collection window tracking | ✅ | ✅ | ✅ | ✅ Must have |
| Data validation engine | ✅ | ✅ | ✅ | ✅ Must have |
| CRDC reporting | ✅ | ✅ | ✅ | ✅ Target |
| IDEA/SPED module | ✅ | ✅ Full IEP | ✅ | ✅ Lightweight |
| EL program tracking | ✅ | ✅ | ✅ | ✅ Must have |
| Discipline module | ✅ | ✅ | ✅ | ✅ Must have |
| ADA dashboard | ✅ | ✅ | ✅ | ✅ Differentiator |
| Error assignment workflow | ⚠️ | ✅ | ⚠️ | ✅ Differentiator |
| Real-time grade reporting | ❌ | ❌ | ✅ | ✅ Nice to have |
| Open source | ❌ | ❌ | ❌ | ✅ Differentiator |
| Submission audit trail | ✅ | ✅ | ✅ | ✅ Must have |
| Multi-state from one UI | ❌ | ⚠️ | ⚠️ | ✅ Differentiator |
| Charter network support | ⚠️ | ⚠️ | ❌ | ✅ Opportunity |

---

## 10. Build Recommendations Based on Competitor Analysis

### Must-Have (Parity Features)
1. **Ed-Fi API Client** — Configurable endpoint, OAuth, resource mapping
2. **Collection Window Engine** — Define windows, snapshot dates, lock/unlock
3. **Validation Rule Engine** — Multi-level (format, cross-entity, business rules)
4. **Data Submission Tracker** — Status per window, per resource type
5. **Error Management Console** — List errors, assign, track resolution
6. **Discipline Module** — Incidents, actions, IDEA flag, CRDC categories
7. **SPED Supplement** — Disability category, educational environment (not full IEP)
8. **EL Program Tracking** — Language background, proficiency level, program entry/exit
9. **Race/Ethnicity** — Multi-select with federal rollup logic

### Differentiating Features
1. **ADA Real-Time Calculator** — Show current ADA and projected funding impact
2. **Multi-State Configuration** — Single UI to configure for multiple states
3. **Error Resolution Workflow** — Assign errors to responsible staff; track resolution
4. **Submission History** — Full immutable audit of every submission attempt
5. **Open Source Ed-Fi Client** — Reusable library for state agencies and districts
6. **CEDS Alignment** — Map all data elements to CEDS IDs for maximum interoperability
