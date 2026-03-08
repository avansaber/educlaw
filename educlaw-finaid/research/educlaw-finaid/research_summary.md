# Research Summary: EduClaw Financial Aid (educlaw-finaid)

**Product:** EduClaw Financial Aid
**Parent:** educlaw (AI-native SIS, v1.0.0)
**Research Date:** 2026-03-05
**Researcher:** ERPForge Domain Research Agent

---

## Executive Summary

EduClaw Financial Aid is a **sub-vertical of educlaw** that adds Title IV–compliant federal, state, and institutional financial aid management to the existing student information system. It is positioned as the **first open-source, AI-native financial aid module** for a full SIS — a significant market gap in a $593M annual software market.

The module must handle the most compliance-intensive domain in higher education: federal Title IV regulations spanning 1,000+ pages, annual FAFSA cycles, SAP evaluations, R2T4 withdrawal calculations, and direct loan management. Yet the core workflows are well-understood, standardized across the industry, and map cleanly to a relational data model.

**Key research finding:** The financial aid domain is not technically complex — it is *compliance complex*. The business logic is deterministic (formulas, status machines, date arithmetic). Building it correctly requires deep regulatory knowledge, not deep technical innovation.

---

## 1. Parent Product Assessment

### What educlaw Already Provides (High Reuse)

| Domain | Tables | finaid Reuse |
|--------|--------|-------------|
| Student identity | `educlaw_student` | Primary key for all finaid records; SSN (encrypted), GPA, academic standing, credits |
| Academic calendar | `educlaw_academic_year`, `educlaw_academic_term` | Term dates → payment periods; aid year alignment |
| Enrollment | `educlaw_program_enrollment`, `educlaw_course_enrollment` | SAP calculation inputs; R2T4 last date of attendance |
| Guardians | `educlaw_guardian`, `educlaw_student_guardian` | Dependent student FAFSA; Parent PLUS loan |
| FERPA infrastructure | `educlaw_data_access_log`, `educlaw_consent_record` | All finaid records are FERPA-protected — inherit audit trail |
| Notifications | `educlaw_announcement`, `educlaw_notification` | Award notifications, verification requests, SAP alerts |
| Programs | `educlaw_program` | Aid eligibility, loan limits, COA setup |
| Fee billing | erpclaw-selling invoices | Student account for aid credit posting |
| GL | erpclaw-gl | Fund accounting for disbursements |

### What educlaw Is Missing (Must Build)

| Gap | New Tables Needed | Priority |
|----|------------------|----------|
| FAFSA/ISIR processing | `finaid_isir`, `finaid_isir_cflag` | P0 |
| Verification workflow | `finaid_verification_request`, `finaid_verification_document` | P0 |
| Cost of Attendance | `finaid_cost_of_attendance`, `finaid_pell_schedule` | P0 |
| Aid packaging | `finaid_award_package`, `finaid_award` | P0 |
| Disbursement | `finaid_disbursement` | P0 |
| SAP evaluation engine | `finaid_sap_evaluation`, `finaid_sap_appeal` | P0 |
| R2T4 calculation | `finaid_r2t4_calculation` | P0 |
| Institutional scholarships | `finaid_scholarship_program`, `finaid_scholarship_application`, `finaid_scholarship_renewal` | P1 |
| Loan tracking | `finaid_loan` | P1 |
| Federal work-study | `finaid_work_study_job`, `finaid_work_study_assignment`, `finaid_work_study_timesheet` | P1 |
| Professional judgment | `finaid_professional_judgment` | P1 |
| Fund allocations | `finaid_fund_allocation` | P1 |
| Aid year config | `finaid_aid_year` | P0 |

**Total new tables: 22**
**educlaw parent tables: 32**
**Combined schema: 54 tables**

---

## 2. Competitive Positioning

### Market Gap Analysis

The financial aid software market is dominated by expensive enterprise systems (Ellucian Banner: $500K–$5M+; Workday: $500K–$3M+) that are inaccessible to small/mid-size institutions. The mid-market is served by PowerFAIDS (~$30K/year) and Jenzabar, both of which require a separate SIS.

**The key insight:** No fully open-source, Title IV–compliant financial aid system exists. educlaw-finaid would be the first.

### Competitive Advantages

| Advantage | Significance |
|-----------|-------------|
| **Native educlaw SIS integration** | No data silos; student enrollment, grades, and financial aid in one system |
| **Open source** | No licensing fees; institutions can self-host and customize |
| **AI-native** | Conversational aid counseling, automatic award explanation, compliance Q&A |
| **Local-first** | Data privacy; fully offline operation; no cloud dependency |
| **Affordable** | Relevant to 3,000+ small institutions priced out of Banner/Workday |
| **First-mover** | No open-source competitor in this exact space |

### Target Customers

| Segment | Size | Pain Points |
|---------|------|------------|
| Small private colleges | 500–5K students | Can't afford Banner; tired of PowerFAIDS's dated UX |
| Community colleges | 2K–20K students | Need non-traditional term support; tight budgets |
| Faith-based institutions | 1K–10K students | Value privacy; often self-hosted |
| Online/hybrid universities | Varies | Need non-standard term support |
| International institutions | Varies | Modeling US aid compliance for international campuses |

---

## 3. Compliance Summary

### Three Regulatory Frameworks

#### Framework 1: Title IV (34 CFR 668)
The overarching federal regulatory framework governing ALL federal student aid.

**Key obligations:**
- Institutional eligibility certification
- Student eligibility verification (citizenship, default status, enrollment)
- Annual independent compliance audit
- Consumer disclosures
- Verification procedures (30–40% of FAFSAs)
- Return of Title IV funds within 45 days of withdrawal
- Cash management (disbursement timing, credit balance return within 14 days)

**Software must enforce:**
- Disbursement holds (verification, SAP, MPN, enrollment)
- 45-day R2T4 return deadline tracking
- 14-day credit balance return tracking
- Aggregate loan limit enforcement
- Annual loan limit enforcement

#### Framework 2: FAFSA Processing
The annual student application cycle.

**Key elements:**
- ISIR storage (multiple transactions per student per year)
- C-flag identification and resolution
- SAI-based need analysis
- Verification group document requirements
- Award year alignment (July 1–June 30)
- Pell Lifetime Eligibility tracking (600% cap)

#### Framework 3: SAP (Satisfactory Academic Progress)
Ongoing academic eligibility for aid.

**Three measurement components:**
1. GPA ≥ 2.0 (qualitative)
2. Completion rate ≥ 67% (quantitative pace)
3. Maximum timeframe ≤ 150% of program length

**Status lifecycle:** SAT → FAW → FSP → Appeal → FAP → SAT

**Software must:**
- Run end-of-term batch evaluation automatically
- Enforce correct status machine (Warning before Suspension)
- Block disbursements for FSP students
- Support appeal workflow with academic plans

---

## 4. Recommended Build Scope

### v1 Build List (Recommended for Initial Release)

#### Domain: Financial Aid Administration
| Feature | Tables | Actions (est.) |
|---------|--------|---------------|
| Aid year setup | `finaid_aid_year`, `finaid_pell_schedule`, `finaid_fund_allocation` | 6 |
| COA management | `finaid_cost_of_attendance` | 5 |
| ISIR import and review | `finaid_isir`, `finaid_isir_cflag` | 8 |
| Verification workflow | `finaid_verification_request`, `finaid_verification_document` | 10 |
| Aid packaging | `finaid_award_package`, `finaid_award` | 12 |
| Disbursement | `finaid_disbursement` | 8 |
| SAP evaluation | `finaid_sap_evaluation`, `finaid_sap_appeal` | 10 |
| R2T4 calculator | `finaid_r2t4_calculation` | 6 |
| Professional judgment | `finaid_professional_judgment` | 5 |

**Subtotal: ~70 actions**

#### Domain: Scholarships
| Feature | Tables | Actions (est.) |
|---------|--------|---------------|
| Scholarship program definition | `finaid_scholarship_program` | 6 |
| Scholarship applications | `finaid_scholarship_application` | 8 |
| Scholarship renewals | `finaid_scholarship_renewal` | 4 |

**Subtotal: ~18 actions**

#### Domain: Work-Study
| Feature | Tables | Actions (est.) |
|---------|--------|---------------|
| Job postings | `finaid_work_study_job` | 5 |
| Student assignments | `finaid_work_study_assignment` | 5 |
| Timesheets | `finaid_work_study_timesheet` | 8 |

**Subtotal: ~18 actions**

#### Domain: Loan Tracking
| Feature | Tables | Actions (est.) |
|---------|--------|---------------|
| Loan origination records | `finaid_loan` | 8 |
| MPN and counseling tracking | (part of `finaid_loan`) | 4 |

**Subtotal: ~12 actions**

### Total v1 Estimate: ~118 actions, 22 tables

---

## 5. Key Differentiators to Target

### 1. Automated SAP Engine
No simple SIS has built-in SAP evaluation. This is typically done manually in spreadsheets or via expensive ERP modules. **educlaw-finaid's automated SAP batch engine — pulling directly from educlaw grades and enrollment — is a genuine differentiator.**

### 2. AI-Powered Financial Aid Counseling
The conversational interface (Claude/ERPClaw agent) can:
- Explain award packages in plain language to students
- Guide FAO staff through R2T4 calculations
- Answer compliance questions ("Can I disburse before 10 days before term?")
- Auto-generate verification document request letters
- Summarize SAP appeal decisions with regulatory citations

No competitor offers this. This is the "AI-native" story for educlaw-finaid.

### 3. Integrated SIS + Financial Aid
Banner, PowerFAIDS, and Jenzabar all maintain separate data stores. educlaw-finaid reads enrollment, grades, and GPA **directly from educlaw** with no export/import. This eliminates:
- ISIR-to-SIS data synchronization errors
- SAP calculation discrepancies
- Late R2T4 calculations due to missing withdrawal dates

### 4. R2T4 Compliance Automation
The 45-day R2T4 deadline is one of the most common audit findings. A system that:
- Automatically detects withdrawals from educlaw enrollment changes
- Calculates R2T4 within minutes
- Tracks the 45-day clock
- Alerts when deadline is approaching
...would prevent significant institutional liability.

### 5. First Open-Source Title IV Module
Being first in an uncontested category has compounding advantages: community contributions, regulatory update crowdsourcing, institutional trust-building.

---

## 6. Technical Risks and Mitigations

| Risk | Severity | Mitigation |
|------|---------|------------|
| **Federal regulation changes annually** | High | Store regulatory thresholds as configurable data (Pell table, loan limits, SAP thresholds) — not hardcoded |
| **R2T4 calculation errors** | High | Extensive unit tests with known calculation examples from ED; worksheet output for human review before submission |
| **Overaward bugs** | High | Award packaging must check COA ceiling at every step; unit test with all edge cases |
| **ISIR parsing errors** | Medium | ISIR format is well-documented (Federal Student Aid Handbook); manual import with validation is safer than live SAIG in v1 |
| **Aggregate loan limit errors** | High | Read NSLDS data from ISIR (stored on `finaid_isir`); enforce in packaging logic |
| **SAP status machine errors** | Medium | Explicit state transition validation; unit tests for all transition paths |
| **FERPA data exposure** | High | Inherit educlaw's existing FERPA infrastructure; all finaid record access must log to `educlaw_data_access_log` |
| **Decimal precision errors** | Medium | All monetary values TEXT (Python Decimal); never use float |
| **Disbursement timing violations** | Medium | Validate disbursement date ≥ term_start_date − 10 days at disbursement time |
| **Credit balance deadline violations** | Medium | Auto-flag credit balances; 14-day countdown alert |

---

## 7. Domain Vocabulary for educlaw-finaid SKILL.md

The AI agent should understand and use these terms:

```
Financial Aid → aid package, award, financial assistance
ISIR → FAFSA results, aid eligibility record, federal application data
SAI → Student Aid Index (formerly Expected Family Contribution/EFC)
COA → Cost of Attendance, student budget, school costs
R2T4 → Return of Title IV, withdrawal refund, earned aid calculation
SAP → Satisfactory Academic Progress, academic standards, progress review
Pell Grant → federal grant, Pell award, free money (no repayment)
Direct Loan → federal student loan, government loan, subsidized/unsubsidized
Work-Study → FWS, campus job, federal employment
Verification → FAFSA verification, document review, income verification
C-flag → caution flag, FAFSA flag, hold on aid
Disbursement → aid payment, credit to account, aid applied
Award Letter → financial aid offer, aid package notification
Professional Judgment → PJ, FAA discretion, special circumstances adjustment
```

---

## 8. Estimated Complexity by Domain

| Domain | Tables | Actions | Complexity | Notes |
|--------|--------|---------|-----------|-------|
| Aid year & COA setup | 3 | 11 | Low | Simple configuration |
| ISIR import & C-flags | 2 | 8 | Medium | Parsing logic; status machine |
| Verification | 2 | 10 | Medium | Document workflow |
| Aid packaging | 2 | 12 | High | Complex rules; overaward detection; Pell schedule |
| Disbursement | 1 | 8 | High | GL integration; COD reporting; timing rules |
| SAP evaluation | 2 | 10 | High | Complex calculation; batch processing; status machine |
| R2T4 calculation | 1 | 6 | High | Deadline tracking; complex formula; institutional/student split |
| Scholarships | 3 | 18 | Medium | CRUD + matching logic |
| Work-Study | 3 | 18 | Medium | Timesheet workflow |
| Loan tracking | 1 | 12 | Medium | COD reporting; limit enforcement |
| Professional judgment | 1 | 5 | Low | Audit documentation |

**Overall: HIGH complexity domain** — comparable to healthcare billing in regulatory burden, but with more deterministic formulas.

---

## 9. Build Recommendations

### Priority Order for Implementation

**Phase 1 (Core Compliance — Must Ship First):**
1. `finaid_aid_year` + `finaid_pell_schedule` + `finaid_fund_allocation` — setup
2. `finaid_cost_of_attendance` — student budgets
3. `finaid_isir` + `finaid_isir_cflag` — FAFSA data receipt
4. `finaid_verification_request` + `finaid_verification_document` — compliance gate
5. `finaid_award_package` + `finaid_award` — packaging
6. `finaid_disbursement` — fund delivery
7. `finaid_sap_evaluation` + `finaid_sap_appeal` — ongoing eligibility
8. `finaid_r2t4_calculation` — withdrawal compliance

**Phase 2 (Institutional Aid + Employment):**
9. `finaid_scholarship_program` + `finaid_scholarship_application` + `finaid_scholarship_renewal`
10. `finaid_work_study_job` + `finaid_work_study_assignment` + `finaid_work_study_timesheet`

**Phase 3 (Loans + Judgment):**
11. `finaid_loan`
12. `finaid_professional_judgment`

### Key Design Decisions

1. **ISIR as manual import (not live SAIG):** SAIG integration requires institutional SAIG mailbox credentials and is complex to implement safely. Manual CSV/text file import is sufficient for v1 and covers 100% of use cases. Students don't notice the difference.

2. **COD as XML export (not live API):** Generate COD-compliant XML files for institution to upload to COD web portal. Eliminates need for school-code-specific API credentials while maintaining full compliance.

3. **Read enrollment/grades from educlaw (never copy):** finaid should never shadow educlaw data. SAP calculations should query `educlaw_course_enrollment` directly. R2T4 should read from `educlaw_academic_term`. This is the key architectural advantage of being a sub-vertical.

4. **Immutable disbursement records:** Once posted, disbursements cannot be edited. Corrections are always new records (reversals). This matches how COD and the GL work.

5. **Configurable thresholds, not hardcoded:** Pell award amounts, loan limits, SAP minimums, and R2T4 percentages change annually. Store in database tables or configuration — never hardcode regulatory values.

---

## 10. Files Produced

| File | Status | Description |
|------|--------|-------------|
| `parent_analysis.md` | ✅ Complete | Detailed educlaw parent analysis — 8 sections |
| `overview.md` | ✅ Complete | Industry overview, market context, key entities |
| `competitors.md` | ✅ Complete | 7 competitors analyzed (0 open source, 7 commercial) |
| `compliance.md` | ✅ Complete | Title IV, FAFSA/ISIR, SAP — full regulatory requirements |
| `workflows.md` | ✅ Complete | 12 core workflows with step-by-step logic and decision points |
| `data_model.md` | ✅ Complete | 22 new tables with full column definitions and indexes |
| `research_summary.md` | ✅ Complete | This document |

**Total research output: ~15,000 words across 7 documents**
