# Compliance & Regulatory Requirements: Financial Aid

**Product:** EduClaw Financial Aid (educlaw-finaid)
**Research Date:** 2026-03-05
**Frameworks:** Title IV (34 CFR 668), FAFSA/ISIR Processing, SAP (Satisfactory Academic Progress)

---

## 1. Title IV Compliance (34 CFR Part 668)

### Overview

Title IV of the Higher Education Act (HEA) authorizes all federal student aid programs. Institutions must be certified by the U.S. Department of Education to participate. Title IV regulations are codified in the Code of Federal Regulations (CFR) Title 34, with Part 668 covering general administrative provisions.

**Regulatory Authority:** U.S. Department of Education, Federal Student Aid (FSA) office
**Primary Regulation:** 34 CFR Part 668 (Student Assistance General Provisions)
**Key Sub-parts:**
- Subpart A — Definitions
- Subpart B — Conditions for Participation
- Subpart C — Student Eligibility
- Subpart D — Institutional and Financial Assistance Information
- Subpart E — Verification of Student Aid Applications
- Subpart F — Misrepresentation
- Subpart G — Fine, Limitation, Suspension, and Termination Procedures

---

### 1.1 Institutional Eligibility Requirements

Institutions participating in Title IV must maintain:

| Requirement | Standard | Software Implication |
|------------|---------|---------------------|
| **State Authorization** | Licensed by state to operate | Store institution license data |
| **Accreditation** | Recognized accreditor | Store accreditation data |
| **Administrative Capability** | Demonstrate competent administration | Audit trail, staff credentials |
| **Financial Responsibility** | Composite score ≥ 1.5; or alternative standards | Financial reporting integration |
| **Cohort Default Rate (CDR)** | < 30% (3-year CDR) | Track loan defaults via NSLDS |
| **90/10 Rule** (for-profit only) | ≤ 90% revenue from Title IV | Revenue tracking by source |

---

### 1.2 Student Eligibility (34 CFR 668 Subpart C)

Students must meet all of the following to receive Title IV aid:

| Criterion | Details | Software Check |
|-----------|---------|---------------|
| **U.S. Citizenship / Eligible Non-citizen** | Verified via SSN match | ISIR C-flag `C01` resolution |
| **High School Completion** | Diploma, GED, or homeschool | Document verification |
| **Valid SSN** | Must match SSA records | ISIR match code |
| **Enrolled in Eligible Program** | Degree or certificate program | Link to `educlaw_program` |
| **Enrolled at Least Half-time** | Minimum credit hours | Check `educlaw_course_enrollment` |
| **Not in Default** | No defaulted federal loans | NSLDS check / ISIR flag |
| **No Overpayment** | No outstanding grant overpayment | NSLDS check / ISIR flag |
| **Satisfactory Academic Progress** | Meet institutional SAP standards | `finaid_sap_evaluation` |
| **Selective Service Registration** | Males 18–25 | ISIR match code |
| **Drug-Free** | No drug conviction disqualification | ISIR question |

---

### 1.3 Return of Title IV Funds (R2T4) — 34 CFR 668.22

**Trigger:** Student officially or unofficially withdraws from all courses in a payment period.

**Formula:**
```
% of Period Completed = Days Attended ÷ Total Days in Period
Earned Aid = % Completed × Total Title IV Aid Disbursed (or Could Have Been Disbursed)
Unearned Aid = Total Disbursed − Earned Aid

If Unearned Aid > 0: Institution must return funds to ED within 45 days
If Earned > Disbursed: Institution must offer Post-Withdrawal Disbursement within 45 days
```

**Key Rules:**
- Once 60% of the payment period is complete, student has earned 100% of aid
- "Days Attended" = last date of academically-related activity (not last class attended)
- Institution's share returned first, then student's share
- Return order: Unsubsidized Loans → Subsidized Loans → Direct PLUS → Pell Grant → FSEOG → TEACH Grant
- **45-day rule**: Institution must return funds within 45 days of determination of withdrawal date
- Unofficial withdrawals: Students who stop attending without notice — school must determine withdrawal date

**educlaw-finaid Requirements:**
- [ ] Store withdrawal date (pull from `educlaw_course_enrollment.drop_date`)
- [ ] Store last date of attendance
- [ ] Store payment period start/end dates
- [ ] Calculate % completed and earned aid amount
- [ ] Generate R2T4 worksheet showing all calculations
- [ ] Track return timeline (Day 0 = determination, Day 45 = deadline)
- [ ] Document post-withdrawal disbursement decision and timeline
- [ ] Support both official (drop) and unofficial (non-attendance) withdrawals

---

### 1.4 Verification (34 CFR 668 Subpart E)

**Purpose:** Verify accuracy of FAFSA data for selected applicants. FSA selects 30–40% of applicants.

**Selection:** FPS assigns a verification flag on the ISIR. C-flag C-25 indicates verification required.

**Verification Groups (2025-26):**
| Group | Items Verified |
|-------|---------------|
| V1 (Standard) | Tax return data, household size, family members in college |
| V4 (Custom) | Identity/Statement of Educational Purpose only |
| V5 (Aggregate) | All V1 items + child support paid, SNAP benefits, high school completion |

**Process:**
1. FAO receives ISIR with verification flag
2. FAO notifies student of required documents
3. Student submits documents (tax transcript, W-2s, household verification form, etc.)
4. FAO reviews documents against ISIR data
5. If discrepancy found: correct the ISIR; recalculate need
6. If no discrepancy: mark verification complete; package aid

**Timing:** Aid cannot be disbursed until verification is complete (or student becomes ineligible).

**educlaw-finaid Requirements:**
- [ ] Track verification flag from ISIR (yes/no)
- [ ] Verification group determination (V1/V4/V5)
- [ ] Per-student document checklist (required documents list)
- [ ] Document submission tracking (submitted/not submitted)
- [ ] Document review status (accepted/rejected/pending)
- [ ] Discrepancy flag and correction tracking
- [ ] Verification completion date
- [ ] Disbursement hold until verification complete

---

### 1.5 Cash Management — 34 CFR 668 Subpart K

**Key Rules:**

| Rule | Requirement | Software Implication |
|------|------------|---------------------|
| **Disbursement Timing** | No earlier than 10 days before term start | Disbursement date validation |
| **Credit Balance Processing** | Return credit balances within 14 days | Track credit balances |
| **Excess Cash** | Drawdown from G5 only when needed | G5 drawdown tracking |
| **Monthly Reconciliation** | Reconcile COD records monthly | COD reconciliation workflow |
| **90-day Rule** | Funds drawn more than 3 days before disbursement require return to ED | Drawdown date tracking |

---

### 1.6 Consumer Disclosures (34 CFR 668 Subpart D)

Institutions must publish and make available:
- Net Price Calculator
- Retention and graduation rates
- Cost of attendance information
- Financial aid policies (SAP, verification, professional judgment)
- Student loan default rates

**educlaw-finaid Requirements:**
- [ ] Publish SAP policy (link/document)
- [ ] Award letter format compliance (NASFAA standardized format encouraged)
- [ ] Per-student cost of attendance disclosure
- [ ] Student Rights and Responsibilities disclosure tracking

---

### 1.7 Audit and Program Review Requirements

**Annual Audit:** Independent auditor must certify Title IV compliance annually.

**Program Reviews:** FSA conducts periodic on-site program reviews. Institutions must produce:
- ISIR files and processing records
- Verification documentation
- Disbursement records with COD confirmation
- SAP evaluation records
- R2T4 calculations for all withdrawals
- Professional judgment documentation

**educlaw-finaid Requirements:**
- [ ] Complete audit trail on all aid actions (who, when, what)
- [ ] Immutable disbursement records
- [ ] R2T4 worksheet archive
- [ ] Professional judgment documentation with required fields (reason, documentation, authorized by)
- [ ] FERPA-compliant data access logging (inherited from educlaw)

---

## 2. FAFSA Processing Requirements

### 2.1 FAFSA Application Cycle

| Milestone | Timing | Notes |
|-----------|--------|-------|
| FAFSA Opens | October 1, prior year | Online form at studentaid.gov |
| Award Year | July 1 – June 30 | 12-month federal aid period |
| Processing Deadline | June 30 of award year | No late applications accepted |
| ISIR Delivery | Within 1–3 days of submission | Electronic via SAIG mailbox |

### 2.2 ISIR Key Data Elements

The ISIR contains the output of FAFSA processing. Critical fields for educlaw-finaid:

| Field Group | Key Fields |
|-------------|-----------|
| **Identification** | SSN, First/Last Name, Date of Birth, FAFSA Submission ID |
| **Dependency Status** | Dependency code (dependent/independent), Dependency override |
| **Aid Eligibility** | Student Aid Index (SAI), Primary EFC (formula A/B/C), SAI Indicator |
| **Pell Eligibility** | Pell Index, Scheduled Award, Pell Lifetime Eligibility Used (LEU) |
| **Match Flags** | SSA match (citizenship), NSLDS match (loans/grants), Selective Service |
| **C-Flags** | Comment codes requiring resolution before disbursement |
| **Verification** | Verification flag, Verification group code |
| **Aid History** | Prior FAFSA data, prior year aid received |
| **Income Data** | Adjusted Gross Income (AGI), taxed/untaxed income, assets |
| **Family Data** | Household size, family members in college |
| **Transaction Number** | ISIR transaction number (multiple transactions per student) |
| **School Codes** | Federal school codes listed on FAFSA |

### 2.3 C-Flag Resolution

C-Flags (Caution Flags) must be resolved before disbursing any Title IV aid.

| Common C-Flag | Description | Resolution Required |
|--------------|-------------|---------------------|
| C01 | SSN/citizenship match failed | Citizenship documentation |
| C06 | Selective Service match failed | Selective Service registration proof |
| C07 | NSLDS default match | Loan rehabilitation documentation |
| C09 | Unusual Enrollment History | Review enrollment at multiple schools |
| C25 | Selected for verification | Complete verification process |
| C28 | Identity/Statement of Purpose | Identity verification document |

**educlaw-finaid Requirements:**
- [ ] Store all C-flags from ISIR
- [ ] Track C-flag resolution status per flag
- [ ] Block disbursement until all C-flags cleared
- [ ] Document resolution with staff ID and date
- [ ] Store resolution documentation reference

### 2.4 ISIR Transactions

Students can update their FAFSA — each update generates a new ISIR transaction.

- Transaction 01 = original submission
- Transactions 02+ = corrections and updates
- Institutions should use the most recent **valid** ISIR transaction
- Some corrections reopen verification requirements

**educlaw-finaid Requirements:**
- [ ] Store all ISIR transactions per student per award year
- [ ] Track which transaction is currently "active"
- [ ] Flag when a new transaction changes aid eligibility
- [ ] Recalculate packaging when ISIR updates change SAI

---

## 3. Satisfactory Academic Progress (SAP)

### 3.1 Regulatory Basis

- **Authority:** 34 CFR 668.34
- **Purpose:** Ensure students are progressing toward a degree to remain eligible for Title IV aid
- **Applies to:** All Title IV aid recipients (grants, loans, work-study)

### 3.2 SAP Measurement Components

All three components must be evaluated simultaneously:

#### Component 1: Qualitative Measure (GPA)
| Standard | Typical Requirement |
|---------|---------------------|
| Undergraduate minimum GPA | 2.0 cumulative (varies by institution) |
| Graduate minimum GPA | 3.0 cumulative (varies by institution) |
| Measurement point | End of each payment period |
| All credits | Transferred credits included in GPA calculation |

#### Component 2: Quantitative Measure (Pace / Completion Rate)
| Standard | Requirement |
|---------|------------|
| Minimum completion rate | 67% of cumulative attempted credits |
| Formula | Credits Completed ÷ Credits Attempted |
| What counts as "attempted" | All enrolled credits, including W/I/F grades |
| What counts as "completed" | Credits with passing grades (A/B/C/D depending on policy) |
| Transfer credits | Both attempted and completed count |
| Repeated courses | Count as attempted again; only one passing grade counts |

**Example:**
```
Student attempted: 60 credits
Student completed: 39 credits
Completion rate: 39/60 = 65% → FAILS (below 67%)
```

#### Component 3: Maximum Timeframe (Pace)
| Standard | Requirement |
|---------|------------|
| Maximum timeframe | 150% of program's published length |
| Example | 120-credit bachelor's degree → 180 attempted credits maximum |
| Transfer credits | Counted toward maximum timeframe |
| Remedial courses | Excluded from 150% calculation |

**Maximum Timeframe Formula:**
```
Max Credits = Program Required Credits × 1.5
If (Attempted Credits + Remaining Required Credits) > Max Credits → FAILS
```

### 3.3 SAP Evaluation Schedule

| Timing | Requirement |
|--------|------------|
| Evaluation frequency | At least annually; recommended end of each term |
| First-time students | After first payment period |
| Transfer students | Must evaluate immediately; count all prior credits |
| Mid-term changes | Not required (end-of-term is standard) |

### 3.4 SAP Status Lifecycle

```
SAP STATUSES:
  SAT (Satisfactory) → Meets all three components → Aid continues

  FAW (Financial Aid Warning) → First-time failure only →
    Aid continues one more term on warning
    If fails again → FSP (Financial Aid Suspension)

  FSP (Financial Aid Suspension) → Aid SUSPENDED →
    Student must file appeal

  FAP (Financial Aid Probation) → Post-appeal, single term →
    Must meet SAP or show compliance with academic plan
    If meets → FSP lifted → SAT status
    If fails → FSP reinstated

  Maximum Timeframe Exceeded → FSP immediately (no warning period)
```

**educlaw-finaid Requirements:**
- [ ] Store SAP status per student per evaluation period
- [ ] Calculate all three SAP components automatically from educlaw data
- [ ] Enforce correct status lifecycle (Warning → Suspension → Appeal → Probation)
- [ ] Block disbursement for students in FSP status
- [ ] Record evaluation date, evaluator, and component details
- [ ] Support batch evaluation at end of each term
- [ ] Generate SAP notification to students

### 3.5 SAP Policy Requirements

Institutional SAP policies must be:
- Written and published
- Applied consistently to all students
- Applied to ALL Title IV programs (not just loans)
- Include appeal procedures
- Specify evaluation periods and standards

Institutions may set **stricter** standards than federal minimums (e.g., higher GPA requirement, higher completion rate) but not more lenient.

### 3.6 SAP Appeals

Students may appeal SAP suspension for documented extenuating circumstances:

**Allowable Appeal Grounds:**
- Death of a relative
- Injury or illness of student
- Other special circumstances (divorce, natural disaster, etc.)

**Required Appeal Documentation:**
- Written explanation of circumstances
- Academic plan (how student will meet SAP by next evaluation)
- Supporting documentation

**Outcomes:**
- Appeal granted → Student placed on FAP (probation) for one term
- Appeal denied → Aid remains suspended

**educlaw-finaid Requirements:**
- [ ] SAP appeal submission (reason, supporting docs, academic plan)
- [ ] Appeal reviewer workflow
- [ ] Appeal decision (granted/denied) with rationale
- [ ] Academic plan tracking (if appeal granted)
- [ ] FAP period length and conditions

---

## 4. Professional Judgment (PJ)

### 4.1 Authority

Financial Aid Administrators (FAAs) have authority under 34 CFR 668.53 to make **Professional Judgment** (PJ) adjustments to override standard federal calculations:

- Adjust SAI/EFC based on special circumstances
- Adjust Cost of Attendance components
- Adjust enrollment status for aid purposes
- Override dependency status in documented cases

### 4.2 PJ Documentation Requirements

Every PJ decision must be documented with:
- Reason for override
- What was changed (specific data element)
- Original value → New value
- Supporting documentation reference
- FAA name and credentials
- Date of decision

**educlaw-finaid Requirements:**
- [ ] Professional Judgment record per student per aid year
- [ ] Override type (SAI, COA, dependency status, enrollment)
- [ ] Original and adjusted values
- [ ] Reason code and narrative
- [ ] Authorizing FAA
- [ ] Document attachment reference
- [ ] Immutable (audit-protected) record

---

## 5. Loan-Specific Compliance

### 5.1 Direct Loan Requirements

Before disbursing any Direct Loan:

| Requirement | Standard | Tracking Needed |
|------------|---------|----------------|
| **Master Promissory Note (MPN)** | Signed before first disbursement | MPN status: pending/signed/date |
| **Entrance Counseling** | Completed for first-time borrowers | Completion: yes/no/date |
| **Annual Loan Limits** | Cannot exceed statutory maximums | Running total per award year |
| **Aggregate Loan Limits** | Lifetime borrowing limits | Cumulative total from NSLDS |
| **Half-time Enrollment** | Must be enrolled at least half-time | Enrollment status check |
| **Origination Reporting** | Reported to COD before first disbursement | COD origination record |

### 5.2 Annual Loan Limits (2025-26)

| Year | Subsidized | Unsubsidized | Combined Max |
|------|-----------|--------------|--------------|
| 1st Year Dependent Undergrad | $3,500 | $2,000 | $5,500 |
| 2nd Year Dependent Undergrad | $4,500 | $2,000 | $6,500 |
| 3rd Year+ Dependent Undergrad | $5,500 | $2,000 | $7,500 |
| Independent Undergrad (1st/2nd) | $3,500/$4,500 | $6,000 | $9,500/$10,500 |
| Independent Undergrad (3rd+) | $5,500 | $7,000 | $12,500 |
| Graduate Student | $0 | $20,500 | $20,500 |

### 5.3 Aggregate Loan Limits

| Student Type | Subsidized | Combined Sub+Unsub |
|-------------|-----------|-------------------|
| Dependent Undergraduate | $23,000 | $31,000 |
| Independent Undergraduate | $23,000 | $57,500 |
| Graduate/Professional | N/A | $138,500 (incl. undergrad) |

**educlaw-finaid Requirements:**
- [ ] Track loan type (subsidized/unsubsidized/PLUS)
- [ ] Annual total calculation per award year
- [ ] Aggregate total from NSLDS (stored on ISIR)
- [ ] Block packaging above annual/aggregate limits
- [ ] MPN status tracking (pending/signed/expired)
- [ ] Entrance counseling completion tracking
- [ ] Exit counseling requirement on graduation/withdrawal

---

## 6. Federal Work-Study Compliance

### 6.1 FWS Program Requirements

| Requirement | Standard |
|------------|---------|
| Federal Share | 75% federal / 25% institutional (standard) |
| On-campus Jobs | Any department; must not displace regular employees |
| Off-campus Jobs | Community service preference; public or private nonprofits |
| Pay Rate | At least federal minimum wage |
| Priority for Off-campus | Students with "exceptional need" |
| Community Service | 7% of FWS allocation must go to community service jobs |

### 6.2 FWS Award Management

- FWS awards are **not disbursed upfront** — students earn wages through work
- Students cannot be paid more than their FWS award amount
- Hours must be verified and approved before payroll
- FWS earnings are reported on W-2 and counted as income on future FAFSA

**educlaw-finaid Requirements:**
- [ ] FWS award allocation per student per term
- [ ] FWS job postings (department, pay rate, hours)
- [ ] Student job assignment tracking
- [ ] Timesheet entry (hours per pay period)
- [ ] Supervisor approval workflow
- [ ] Running earnings vs. award limit
- [ ] W-2/payroll data export
- [ ] Community service hours tracking (7% requirement)

---

## 7. FERPA Intersection with Financial Aid

Financial aid data is explicitly protected under FERPA (20 USC 1232g):

- `data_category = 'financial'` in educlaw_data_access_log
- Financial aid records = part of education records
- Third-party disclosure (scholarship sponsors, employers) requires student consent
- Parents of dependent students may access financial aid records without student consent

**educlaw-finaid Requirements:**
- [ ] All student financial aid record access logged to `educlaw_data_access_log`
- [ ] Consent tracking for third-party disclosure
- [ ] Audit trail on all aid award changes
- [ ] Inherited from parent's FERPA infrastructure

---

## 8. Compliance Calendar

| Action | Frequency | Deadline |
|--------|-----------|---------|
| Monthly COD Reconciliation | Monthly | Within 30 days of month-end |
| NSLDS Enrollment Reporting | Per-term or as changes occur | Within 60 days of term start |
| Annual SAP Evaluation | Per-term (recommended) | Before next term disbursements |
| R2T4 Calculation | Upon each withdrawal | 45 days from determination |
| Credit Balance Return | Per disbursement | 14 days from disbursement credit |
| Independent Audit | Annual | 6 months after fiscal year end |
| FISAP Submission | Annual | October 1 for next award year |
| Annual Disclosure Updates | Annual | By start of award year |

---

## 9. Recommended Compliance Features for educlaw-finaid

### Must-Have (v1)
- Complete ISIR storage with all eligibility flags
- C-flag resolution workflow with documentation
- Verification document tracking and completion gate
- Disbursement hold enforcement (verification, SAP, MPN, enrollment)
- Automated SAP calculation (all three components)
- SAP appeal workflow with academic plan
- R2T4 calculator with all required inputs
- Loan limit enforcement (annual and aggregate)
- MPN/entrance counseling completion tracking
- Professional judgment documentation
- Complete audit trail (who changed what, when, and why)
- FERPA-compliant data access logging (via educlaw parent)

### Recommended (v1 stretch)
- COD Common Record XML export (for manual submission to COD system)
- Monthly reconciliation report (disbursed vs. COD confirmed)
- Aggregate loan limit check against NSLDS data

### Defer (v2)
- Live COD API integration
- Live NSLDS enrollment reporting
- FISAP report generation
- State-specific compliance rules
- Gainful Employment disclosure reporting
- 90/10 rule calculation
