# Research Summary: EduClaw State Reporting

**Product:** educlaw-statereport
**Display Name:** EduClaw State Reporting
**Research Date:** 2026-03-05
**Research Status:** Complete

---

## Executive Summary

EduClaw State Reporting is a sub-vertical of EduClaw that transforms EduClaw's operational K-12 data into compliant state and federal reporting submissions. It addresses one of the most financially critical and legally required functions in K-12 education: reporting student enrollment, attendance, special education, discipline, and staff data to state education agencies (SEAs) and ultimately to the federal government.

**The core value proposition:** EduClaw already captures all the operational data (students, enrollment, attendance, grades). State reporting is the layer that validates, snapshots, and submits this data — plus collects state-specific supplemental data elements not needed for day-to-day operations (race/ethnicity detail, SSID, SPED disability category, EL status, discipline).

**The financial stakes are high:** ADA funding alone can mean $200,000+ per year difference for a mid-size district based on accurate attendance reporting. IDEA non-compliance can result in federal funding loss. CRDC errors can trigger OCR investigations.

---

## 1. Domain Scope

### What We Are Building

EduClaw State Reporting adds four capability domains to EduClaw:

| Domain | Description | Priority |
|--------|-------------|----------|
| **state_reporting** | Collection windows, snapshots, ADA calculation, report generation | Critical |
| **ed_fi** | Ed-Fi API client, descriptor mapping, sync engine, error management | Critical |
| **data_validation** | Pre-submission validation rules engine, error tracking, resolution workflow | Critical |
| **submission_tracking** | Submission history, certification, amendment tracking, audit trail | Critical |

Plus supplemental data collection domains that extend EduClaw's core:

| Extension Domain | New Data | Priority |
|-----------------|----------|----------|
| **Student demographics** | Race/ethnicity, SSID, economic disadvantage, homeless, foster care, military | Critical |
| **Special education** | IDEA disability category, educational environment, services | Critical |
| **English learner** | EL status, language, proficiency, program type, reclassification | Critical |
| **Discipline** | Incidents, actions, IDEA manifestation, CRDC categories | High |

---

## 2. Key Findings

### Finding 1: EduClaw Has ~70% of the Needed Operational Data

EduClaw's 32 existing tables provide:
- ✅ Student demographics (name, DOB, gender, address)
- ✅ Enrollment dates and program/course enrollment records
- ✅ Daily and section-level attendance
- ✅ Grades, GPA, credits earned
- ✅ Academic year and term dates (calendar)
- ✅ Staff/instructor records (via HR employee)
- ✅ FERPA consent and data access audit log
- ✅ Notification system for error alerts

The **critical gap** is the state-specific supplement data and the reporting infrastructure:
- ❌ Race/ethnicity (multi-select, federal rollup)
- ❌ State Student ID (SSID)
- ❌ EL status, language, proficiency
- ❌ SPED disability category + educational environment
- ❌ Section 504 status
- ❌ Economic disadvantage, homeless, foster care flags
- ❌ Discipline incidents and actions
- ❌ Collection window management
- ❌ Snapshot engine
- ❌ Ed-Fi API client
- ❌ Validation rule engine
- ❌ Submission tracking and certification

### Finding 2: Ed-Fi Is the Dominant Technical Standard (30+ States)

Ed-Fi ODS/API v7.3 (Dec 2024) is current. States either:
1. Use Ed-Fi as their primary data pipeline (Wisconsin, Minnesota, Texas TSDS, South Carolina, etc.)
2. Use state-specific extract formats but are migrating to Ed-Fi

Building an Ed-Fi API client in EduClaw State Reporting will cover the majority of states immediately. For non-Ed-Fi states, a flat-file export layer is needed as a secondary option.

### Finding 3: The Market Has Three Dominant Vendors With Clear Weaknesses

| Vendor | Market Share | Key Weakness |
|--------|-------------|--------------|
| PowerSchool | ~40% | Per-state black-box modules; expensive; inconsistent UX |
| Infinite Campus | ~20% | Enterprise-only; statewide contract lock-in; complex config |
| Skyward | ~7% | Smaller install base; limited charter focus |

**EduClaw's opportunity:** Open-source, multi-state-aware platform with embedded validation that competes on price and configurability.

### Finding 4: Compliance Requirements Are Layered and Non-Negotiable

The compliance stack is:
- **Federal:** ESSA, IDEA, Title Programs → EDFacts (74 files) + CRDC (biennial) + IDEA 618 (8 collections)
- **State:** Each state adds 30-100 additional required fields and custom collection windows
- **FERPA:** All reporting must respect privacy requirements (data access logging, small cell suppression)

The product cannot be built without handling IDEA disability categories, CRDC race/discipline disaggregation, and Ed-Fi descriptor mapping.

### Finding 5: Discipline and SPED Are the Highest-Risk Data Elements

Both IDEA discipline reporting and CRDC discipline disaggregation are high-visibility areas:
- OCR investigates districts with disparate discipline rates by race
- OSEP audits IDEA discipline removal data
- Missing or incorrect data can trigger compliance investigations

The discipline module must capture: incident type, action type, student role, IDEA flag, days removed, and CRDC subgroup data.

---

## 3. Recommended V1 Scope

### Must-Have for V1 (Core Compliance)

#### Domain: Student Demographics Extension
- [ ] `sr_student_supplement` table (race, SSID, EL flag, SPED flag, economic disadvantage, homeless)
- [ ] Race/ethnicity entry UI with federal rollup computation
- [ ] SSID assignment/lookup workflow
- [ ] EL status tracking with language and proficiency
- [ ] Economic disadvantage flag with lunch status

#### Domain: Special Education
- [ ] `sr_sped_placement` table (disability category, educational environment)
- [ ] IDEA disability category codes (14 federal categories)
- [ ] Educational environment codes (RC ≥80%, <40%, separate class, etc.)
- [ ] SPED service log (type, minutes/week, provider)
- [ ] IDEA child count report generator

#### Domain: Discipline
- [ ] `sr_discipline_incident` table with CRDC-aligned incident types
- [ ] `sr_discipline_student` (student roles, IDEA/504 flags)
- [ ] `sr_discipline_action` (ISS, OSS, expulsion, law enforcement referral)
- [ ] IDEA Manifestation Determination prompt (>10 day suspension)
- [ ] Days removed calculator
- [ ] CRDC discipline report by subgroup

#### Domain: Ed-Fi Integration
- [ ] `sr_edfi_config` table (connection profiles per state)
- [ ] `sr_edfi_descriptor_map` (code → URI mappings)
- [ ] OAuth 2.0 client (token management, refresh)
- [ ] Ed-Fi resource serializers for: Student, StudentSchoolAssociation, StudentEdOrgAssociation, StudentProgramAssociation, StudentSchoolAttendanceEvent, StaffSchoolAssociation
- [ ] Dependency-ordered sync engine
- [ ] `sr_edfi_sync_log` (every API call logged)
- [ ] Error pull from state ODS (where available)
- [ ] `sr_org_mapping` (NCES IDs per school)

#### Domain: Collection Windows
- [ ] `sr_collection_window` table
- [ ] Collection window lifecycle (upcoming → certified)
- [ ] Snapshot engine (freeze `sr_snapshot_record` at close date)
- [ ] `sr_submission` tracking with certification
- [ ] ADA calculation engine (from `educlaw_student_attendance`)
- [ ] Chronic absenteeism identification (≥10% absent)

#### Domain: Data Validation
- [ ] `sr_validation_rule` library (100+ federal/common rules)
- [ ] `sr_validation_result` per student per run
- [ ] `sr_submission_error` management
- [ ] Error assignment and resolution tracking
- [ ] Error dashboard (critical / major / minor counts)
- [ ] Pre-submission validation report (printable for principals)

### Defer to V2

| Feature | Reason to Defer |
|---------|----------------|
| Full IEP authoring | Complexity; most districts use separate SPED software |
| State-specific flat file exports | Ed-Fi covers 30+ states; start there |
| CRDC auto-submission | Complex biennial process; manual export + upload is fine for V1 |
| EL proficiency assessment entry | Complex; start with status flag + program tracking |
| Staff certification management | Needs deeper HR integration; defer |
| Real-time grade reporting to Ed-Fi | V2 differentiator; V1 covers final grades only |
| Parent/guardian notification of state errors | Nice-to-have; defer |
| Multi-state concurrent reporting (one district) | Charter network feature; defer |
| EDFacts flat file generator | Most states use Ed-Fi; start there |
| Section 504 full plan management | Flag tracking in V1; full 504 plan in V2 |

---

## 4. Technical Architecture Recommendations

### New Tables Required: 18

| # | Table | Priority |
|---|-------|---------|
| 1 | `sr_org_mapping` | Critical |
| 2 | `sr_edfi_config` | Critical |
| 3 | `sr_edfi_descriptor_map` | Critical |
| 4 | `sr_student_supplement` | Critical |
| 5 | `sr_sped_placement` | Critical |
| 6 | `sr_sped_service` | High |
| 7 | `sr_el_program` | Critical |
| 8 | `sr_discipline_incident` | Critical |
| 9 | `sr_discipline_student` | Critical |
| 10 | `sr_discipline_action` | Critical |
| 11 | `sr_collection_window` | Critical |
| 12 | `sr_snapshot` | Critical |
| 13 | `sr_snapshot_record` | Critical |
| 14 | `sr_submission` | Critical |
| 15 | `sr_submission_error` | Critical |
| 16 | `sr_validation_rule` | Critical |
| 17 | `sr_validation_result` | High |
| 18 | `sr_edfi_sync_log` | Critical |

### Domain Scripts Required: 6

| Script | Actions |
|--------|---------|
| `state_reporting.py` | Collection windows, snapshots, ADA calculation, ADA dashboard |
| `ed_fi.py` | Ed-Fi config, descriptor maps, sync engine, org mappings |
| `data_validation.py` | Validation rules, validation runs, error management |
| `submission_tracking.py` | Submissions, certification, amendment, history |
| `demographics.py` | Student supplements, race/ethnicity, SSID management |
| `discipline.py` | Incidents, student roles, actions, MDR workflow |

Note: SPED and EL can be part of `demographics.py` initially, or split to `sped.py` and `el_program.py`.

### Estimated Complexity

| Component | Complexity | Estimated Actions |
|-----------|-----------|------------------|
| Student demographics extension | Medium | 10–15 actions |
| SPED placement + services | Medium | 8–12 actions |
| EL program tracking | Low-Medium | 6–10 actions |
| Discipline module | Medium | 12–18 actions |
| Ed-Fi integration layer | High | 15–20 actions |
| Collection window + snapshots | High | 12–18 actions |
| Validation engine | Very High | 10–15 actions + 100+ rule definitions |
| Submission tracking | Medium | 8–12 actions |
| **Total Estimated** | | **~80–120 new actions** |

---

## 5. Key Differentiators to Build Toward

### Differentiator 1: Real-Time ADA Funding Dashboard
Show districts their current ADA, trend, and projected funding impact in real time. No competitor makes this financially explicit. This is the "hook" that demonstrates immediate ROI.

### Differentiator 2: Unified Multi-State Configuration
Build the Ed-Fi config and descriptor mapping framework so that a charter network operating in multiple states can configure each state separately from the same UI. This is underserved by current vendors.

### Differentiator 3: Error Assignment Workflow
Most vendors show errors in a list. EduClaw should allow errors to be assigned to specific staff members (school secretaries, teachers, coordinators) with due dates and resolution tracking. This is closer to a project management experience for compliance.

### Differentiator 4: Pre-Submission "Readiness Score"
Compute a data readiness score (0–100%) for each collection window based on how many validation rules pass. Show progress over time. This helps coordinators prioritize and gives administrators visibility.

### Differentiator 5: Immutable Submission Archive
Every submission stores a frozen copy of the data that was sent. Districts need this for audit defense ("what did we submit on October 15th?"). Most vendors don't surface this clearly.

---

## 6. Technical Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Ed-Fi API version drift (states on v5/v6/v7) | High | Medium | Version-configurable client; test against multiple versions |
| State-specific Ed-Fi extensions | High | Medium | Pluggable extension mechanism in descriptor map |
| SSID not available at enrollment | Medium | Medium | Allow "pending SSID" state; sync when received |
| Large snapshot performance (10k+ students) | Medium | High | Paginated snapshot; async background job |
| Validation rule maintenance (states change rules) | High | Medium | Rule library as configurable data; admin UI to update rules |
| Race/ethnicity data quality (missing from many students) | High | High | Validation rule blocks snapshot if race missing |
| Ed-Fi OAuth token expiry during large sync | Medium | Low | Token refresh middleware in Ed-Fi client |
| Manifestation Determination workflow complexity | Low | High | Simple prompt + record keeping; no legal automation |
| ADA calculation edge cases (partial day enrollment, transfers) | Medium | High | Prorate by enrollment date; comprehensive unit tests |
| Small cell suppression logic | Low | Medium | Apply N<10 rule at report export time |

---

## 7. File Inventory

| File | Status | Description |
|------|--------|-------------|
| `parent_analysis.md` | ✅ Complete | EduClaw (parent) tables, actions, gaps, integration points |
| `overview.md` | ✅ Complete | Market context, key entities, ADA funding, Ed-Fi architecture |
| `competitors.md` | ✅ Complete | PowerSchool, Infinite Campus, Skyward, Generate (CIID), Level Data |
| `compliance.md` | ✅ Complete | Ed-Fi standard, CEDS, EDFacts, CRDC, IDEA 618, FERPA, descriptors |
| `workflows.md` | ✅ Complete | Annual reporting cycle, Ed-Fi sync, validation, discipline, submission tracking |
| `data_model.md` | ✅ Complete | 18 new tables, entity relationships, ADA formula, Ed-Fi dependency order |
| `research_summary.md` | ✅ Complete | This document |

---

## 8. Recommended First Actions for Planner Agent

1. **Start with `sr_student_supplement`** — highest impact; race/ethnicity and SSID block all downstream reporting.

2. **Build Ed-Fi config + descriptor mapping infrastructure** — needed before any sync can happen; foundational.

3. **Build collection window + snapshot engine** — core orchestration; everything else depends on knowing what window is active.

4. **Build discipline module** — standalone; doesn't depend on Ed-Fi infrastructure; can be built in parallel.

5. **Build validation rule engine with 30 core rules** — start with the most common errors (missing race, missing SSID, enrollment date outside school year, SPED missing disability category).

6. **Wire Ed-Fi sync for enrollment + demographics first** — this unlocks the state ODS connection and starts surfacing real errors.

7. **Add ADA calculation and dashboard** — show value immediately from existing attendance data.

---

## Sources Referenced

- [Ed-Fi Alliance Documentation](https://docs.ed-fi.org/) — Data standard domains, ODS/API architecture, enrollment domain best practices
- [Ed-Fi ODS/API v7.3 Release (Dec 2024)](https://docs.ed-fi.org/blog/2024/12/18/)
- [EDFacts File Specifications SY 2024-25](https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2024-25)
- [Generate (CIID) GitHub](https://github.com/CEDS-Collaborative-Exchange/Generate) — Open-source federal reporting tool
- [Common Education Data Standards (CEDS)](https://ceds.ed.gov/) — Federal data element vocabulary
- [CALPADS User Manual](https://documentation.calpads.org/) — California state reporting reference
- [PowerSchool South Carolina Ed-Fi Documentation](https://ed.sc.gov/data/information-systems/interoperability-resources/ed-fi-in-south-carolina/) — Competitor implementation reference
- [Infinite Campus NC DPI Modules](https://www.dpi.nc.gov/educators/home-base/ncsis-powered-infinite-campus/included-modules) — Competitor feature reference
- [Skyward Ed-Fi Commitment](https://www.skyward.com/ed-fi) — Competitor reference
- [ListEdTech 2025 K-12 SIS Market Report](https://listedtech.com/blog/the-2025-k-12-sis-market/)
- EduClaw Parent Product Source Code (`educlaw/`)
