# Domain Overview: Financial Aid Management (Higher Education)

**Product:** EduClaw Financial Aid (educlaw-finaid)
**Research Date:** 2026-03-05

---

## 1. Industry Overview

Financial aid management is one of the most regulated and operationally complex functions in higher education. U.S. colleges and universities collectively disburse over **$120 billion** in federal student aid annually, governed by the U.S. Department of Education's Federal Student Aid (FSA) office under Title IV of the Higher Education Act.

The Financial Aid Management Software market was valued at approximately **$593 million in 2025** (colleges and universities segment), projected to grow at 6.6% CAGR through 2034, driven by:
- Rising FAFSA application volumes
- Multi-source aid complexity (federal + state + institutional)
- Increasing regulatory scrutiny
- Demand for automation (compliance errors cost institutions millions in repayments)

### Who Needs Financial Aid Software?

| Institution Type | Scale | Primary Needs |
|-----------------|-------|---------------|
| Community Colleges | 2–50K students | Pell, FWS, FSEOG, state aid; non-standard terms |
| 4-Year Public Universities | 10–80K students | Full Title IV suite, COD integration, enterprise workflows |
| 4-Year Private Non-profit | 2–30K students | Institutional methodology, endowed scholarships, CSS Profile |
| Graduate/Professional Schools | 500–20K | PLUS loans, specialized scholarships, fellowship management |
| For-profit Institutions | Varies | Heavy compliance scrutiny (cohort default rates, gainful employment) |

---

## 2. Financial Aid Ecosystem

### Key Stakeholders
| Stakeholder | Role |
|-------------|------|
| **Student** | Applicant, borrower, award recipient |
| **Parent/Guardian** | Co-borrower (PLUS loans), dependent verification |
| **Financial Aid Office (FAO)** | Package awards, verify documents, disburse funds |
| **Registrar** | Enrollment certification, SAP data provider |
| **Bursar / Student Accounts** | Apply aid credits, issue refunds |
| **Department of Education (FSA)** | Regulator, fund source (federal programs) |
| **FAFSA Processing System (FPS)** | Processes FAFSA, produces ISIR |
| **COD System** | Originate and disburse Pell/Direct Loans |
| **NSLDS** | National Student Loan Data System — loan history |
| **State Aid Agency** | State grant programs |
| **External Scholarship Sponsors** | Third-party aid sources |

### Federal Aid Programs (Title IV)

| Program | Type | Source | Annual Limit (2025-26) |
|---------|------|---------|------------------------|
| **Federal Pell Grant** | Grant | Federal | Up to $7,395 |
| **FSEOG** | Grant (campus-based) | Federal | $100–$4,000/year |
| **Direct Subsidized Loan** | Loan | Federal | $3,500–$5,500/year (undergrad) |
| **Direct Unsubsidized Loan** | Loan | Federal | $2,000–$7,000/year (undergrad) + more for grad |
| **Direct PLUS Loan** | Loan | Federal | Up to COA minus other aid |
| **Federal Work-Study (FWS)** | Employment | Federal (campus-based) | Varies by institution allocation |
| **TEACH Grant** | Grant (service-conditional) | Federal | Up to $4,000/year |

### Non-Federal Aid Programs

| Program | Type | Notes |
|---------|------|-------|
| **State Grants** | Grant | Varies by state (e.g., Cal Grant, PELL equivalents) |
| **Institutional Merit Scholarships** | Grant | GPA/test score criteria |
| **Institutional Need-Based Grants** | Grant | Need analysis (institutional methodology) |
| **Endowed Scholarships** | Grant | Donor-funded, specific eligibility criteria |
| **Athletic Scholarships** | Grant | NCAA rules apply |
| **Private/External Scholarships** | Grant | Third-party awards; counted as OFA |
| **Tuition Waivers** | Discount | Employee benefit, departmental award |

---

## 3. Key Domain Entities

### Core Entities

| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| **ISIR** | Institutional Student Information Record — FAFSA output | SAI, C-flags, verification flag, dependency status, family income |
| **Aid Year** | 12-month award year (July 1–June 30) | Award year code, COA components, Pell table |
| **Cost of Attendance (COA)** | Estimated student budget for the year | Tuition, fees, housing, meals, books, transportation, personal |
| **Award Package** | Complete aid offer for a student per aid year/term | Total awarded, aid types, disbursement schedule |
| **Aid Award** | Individual award line item | Aid type, fund source, amount, status |
| **Disbursement** | Actual funds sent to student account | Date, amount, COD reporting, G/L entry |
| **Scholarship Program** | Institutional scholarship definition | Eligibility criteria, funding source, award amounts, renewal conditions |
| **Scholarship Application** | Student application for institutional scholarship | Status, reviewer, award decision |
| **Verification Request** | Document collection for FAFSA verification | Required documents, submission status, resolution |
| **SAP Evaluation** | Satisfactory Academic Progress review | GPA, completion rate, max timeframe status |
| **SAP Appeal** | Student appeal of SAP suspension | Reason, documentation, academic plan, outcome |
| **R2T4 Calculation** | Return of Title IV funds on withdrawal | Withdrawal date, % earned, amount to return |
| **Loan Record** | Individual loan origination | Loan type, amount, subsidized/unsubsidized, period |
| **Loan Requirement** | MPN and entrance counseling completion | Status, completion date |
| **Work-Study Job** | FWS job posting | Department, pay rate, hours available |
| **Work-Study Assignment** | Student placed in FWS job | Award limit, start/end dates |
| **Work-Study Timesheet** | Hours worked per pay period | Hours, earnings, supervisor approval |
| **Professional Judgment** | Override of federal formula | Reason, documentation, authorized by |

---

## 4. Market Context

### Pain Points Driving Software Adoption

1. **Regulatory Complexity**: Title IV regulations span 1,000+ pages and change annually. Staff spend 10–15 hours/week on compliance research alone. Automation reduces compliance errors by 41%.

2. **Manual Verification Burden**: FAFSA verification requires collecting and reviewing tax transcripts, W-2s, household documents. 30% of applications are selected for verification.

3. **Disbursement Timeliness**: Federal rules require disbursements within specific windows. Manual processes average 29 days longer than automated systems.

4. **R2T4 Liability**: Incorrect R2T4 calculations create institutional repayment liability. Must be completed within 45 days of withdrawal determination.

5. **SAP Complexity**: Manual SAP evaluations across thousands of students each term are error-prone and time-consuming.

6. **Overaward Risk**: Aid cannot exceed COA. Overawards create institutional repayment obligations.

7. **Student Experience**: Students need real-time visibility into aid status, missing documents, and disbursement dates.

### Market Differentiation Opportunities

| Gap in Existing Solutions | Opportunity for educlaw-finaid |
|--------------------------|-------------------------------|
| Complex enterprise systems (Banner, Workday) are overkill for small institutions | Lightweight, affordable, AI-native solution |
| No open-source Title IV compliant solution exists | First-mover open source advantage |
| Poor student-facing UX in legacy systems | AI-assisted counseling interface |
| COD/NSLDS integrations require expensive middleware | Direct federal system integration |
| Separate SIS and financial aid systems create data silos | Native integration with educlaw SIS |
| SAP calculations done manually in spreadsheets | Automated end-of-term SAP engine |

---

## 5. Academic Year and Aid Year Alignment

Financial aid operates on a **July 1–June 30 award year** that does not align with the academic calendar. Key alignment challenges:

- A Fall/Spring student's aid year spans two calendar years
- Summer aid is optional and often allocated to either the prior or upcoming award year
- Loan limits are annual (award year basis) but distributed across terms (payment periods)
- SAP is evaluated per academic term but measured cumulatively over the program

**educlaw-finaid must map:**
- `educlaw_academic_year` (Aug–May) → `finaid_aid_year` (July 1–June 30)
- `educlaw_academic_term` (Fall/Spring/Summer) → payment periods within the aid year

---

## 6. Technology Landscape

### Data Exchange Standards
| Standard | Used For |
|---------|---------|
| **ISIR file format** | FAFSA results delivered from FSA to institutions via SAIG |
| **COD Common Record (XML)** | Originating and disbursing Pell grants and Direct Loans |
| **NSLDS enrollment reporting** | Loan enrollment status updates |
| **FISAP** | Fiscal Operations Report (campus-based program allocation) |
| **EDExpress/FSA software** | Free desktop tool from ED for Title IV processing |

### Integration Architecture
```
Student applies FAFSA → FPS processes → ISIR transmitted via SAIG mailbox
Institution receives ISIR → FAO reviews → Packaging → Award notification
Student accepts award → Disbursement → COD origination → COD disbursement
Monthly: COD reconciliation + NSLDS enrollment update
End of term: SAP evaluation → Hold/release aid for next term
On withdrawal: R2T4 calculation → Return funds to COD within 45 days
```

---

## 7. Recommended Scope for educlaw-finaid v1

### Include in v1
- ISIR import and storage (manual import, not SAIG integration)
- Verification workflow (document checklist, status tracking)
- Cost of Attendance (COA) setup per program/term
- Aid packaging (Pell, Direct Loans, institutional grants)
- Award notification and acceptance workflow
- Disbursement posting to student account (via erpclaw-selling credit)
- Automated SAP evaluation engine (end-of-term)
- SAP appeal workflow
- R2T4 calculation tool (worksheet generator)
- Institutional scholarship program management
- Scholarship application and award workflow
- Federal Work-Study job posting and timesheet management
- Loan record tracking (manual origination data)
- MPN / entrance counseling completion tracking
- Professional Judgment documentation
- Financial aid audit trail (FERPA-compliant)

### Defer to v2
- Direct SAIG mailbox integration (live ISIR feeds)
- Live COD API integration (origination/disbursement XML)
- Live NSLDS reporting
- CSS Profile institutional methodology support
- FISAP report generation
- State grant program management (too variable)
- Athletic scholarship NCAA compliance
- Return of FSEOG calculations (separate from R2T4)
- Gainful employment disclosure reporting
