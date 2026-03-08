# Core Business Workflows: Financial Aid Management

**Product:** EduClaw Financial Aid (educlaw-finaid)
**Research Date:** 2026-03-05

---

## Overview of Workflow Domains

| Workflow | Trigger | Frequency | Complexity |
|----------|---------|-----------|------------|
| 1. ISIR Import & Review | New FAFSA submission | Per student, per aid year | Medium |
| 2. Verification | ISIR flagged for verification | ~30% of applicants | Medium |
| 3. Aid Packaging | Verified ISIR + enrollment | Per student, per term | High |
| 4. Award Acceptance | Packaging complete | Per student, per term | Low |
| 5. Disbursement | Enrollment confirmed | Per term, per student | High |
| 6. SAP Evaluation | End of each academic term | Batch, all students | High |
| 7. SAP Appeal | Student fails SAP | Per student | Medium |
| 8. R2T4 Calculation | Student withdrawal | Per withdrawal event | High |
| 9. Institutional Scholarship | Award cycle | Periodic | Medium |
| 10. Work-Study Management | Each pay period | Recurring | Medium |
| 11. Loan Tracking | Each loan origination | Per loan | Medium |
| 12. Professional Judgment | Special circumstances | Ad hoc | Low |

---

## Workflow 1: ISIR Import and Review

### Purpose
Receive and record FAFSA processing results for each student applicant. Identify eligibility flags and initiate the financial aid process.

### Trigger
- Student files FAFSA and lists institution's school code
- Institution receives ISIR from FSA (via SAIG mailbox in production; manual import in v1)

### Pre-conditions
- Student record exists in `educlaw_student` (or is a new applicant)
- Aid year is configured in `finaid_aid_year`

### Happy Path

```
STEP 1: ISIR Receipt
  ├── FAO receives ISIR file (batch import)
  ├── System matches ISIR to student by SSN (from educlaw_student.ssn_encrypted)
  ├── If student not found: create student record first (educlaw workflow)
  └── Create `finaid_isir` record for student + aid year

STEP 2: Data Extraction
  ├── Parse key ISIR fields: SAI, dependency status, Pell index, income
  ├── Extract C-flags (caution flags)
  ├── Extract verification flag and verification group
  └── Extract aid history (prior ISIR transactions, Pell LEU)

STEP 3: Eligibility Screening
  ├── Check: Is student enrolled in eligible program?
  ├── Check: Is enrollment at least half-time?
  ├── Check: Any NSLDS match failures (default, overpayment)?
  ├── Check: Any unresolved C-flags that block disbursement?
  └── Assign initial eligibility status: eligible / pending / ineligible

STEP 4: C-Flag Resolution (if any)
  ├── List all C-flags requiring resolution
  ├── Assign resolution tasks to FAO counselor
  └── → Branches to Verification Workflow if C25 flag present
      → Other C-flags: collect documentation, mark resolved

STEP 5: ISIR Review Complete
  ├── FAO marks ISIR as reviewed
  ├── If verification required: hold packaging → go to Workflow 2
  ├── If no flags: proceed to aid packaging → go to Workflow 3
  └── Notify student of ISIR receipt and next steps

STEP 6: ISIR Updates
  ├── Student may correct FAFSA → new ISIR transaction generated
  ├── System imports updated ISIR
  ├── Compare key fields (SAI, dependency) to detect changes
  ├── If SAI changed: recalculate need, adjust package
  └── Log all transactions; use latest valid transaction for packaging
```

### Decision Points
| Situation | Branch |
|-----------|--------|
| C-flag 25 (verification) | Go to Verification workflow before packaging |
| C-flag 07 (default) | Student ineligible until default resolved |
| Student not enrolled | Hold; package when enrollment confirmed |
| New ISIR transaction with different SAI | Recalculate and re-package |

### Data Flow
- **Input:** ISIR file (or manual entry)
- **Creates:** `finaid_isir` record, `finaid_isir_cflag` records
- **Reads:** `educlaw_student` (SSN match), `educlaw_program_enrollment`
- **Updates:** `finaid_isir.status`, `finaid_isir_cflag.resolution_status`

---

## Workflow 2: Verification

### Purpose
Collect and review documentation to verify accuracy of FAFSA data for selected applicants.

### Trigger
- ISIR contains verification flag (V1/V4/V5 group)

### Pre-conditions
- `finaid_isir` record exists with `verification_required = 1`

### Happy Path

```
STEP 1: Verification Package Setup
  ├── Determine verification group from ISIR (V1 / V4 / V5)
  ├── Generate required document checklist per group
  │     V1: Tax transcript, W-2s, household size form
  │     V4: Identity verification, Statement of Educational Purpose
  │     V5: All V1 + child support paid, SNAP, high school completion
  └── Create `finaid_verification_request` with document list

STEP 2: Student Notification
  ├── Send notification to student: verification required, documents needed
  ├── Include deadline (typically 30–60 days before expected disbursement)
  └── Send reminder notifications at 14 days, 7 days before deadline

STEP 3: Document Submission
  ├── Student submits documents (upload or in-person)
  ├── FAO receives each document
  ├── Log receipt date per document
  └── Mark each document as received

STEP 4: Document Review
  ├── FAO reviews each document against ISIR data
  ├── For tax data: compare ISIR AGI with IRS transcript
  ├── If document acceptable: mark approved
  ├── If document incomplete/incorrect: request re-submission
  └── Check for discrepancies between ISIR data and documents

STEP 5: Discrepancy Resolution (if applicable)
  ├── If ISIR data incorrect:
  │     ├── Correct FAFSA (student must submit correction)
  │     ├── Wait for corrected ISIR transaction
  │     └── Recalculate need analysis with corrected data
  ├── If discrepancy is intentional fraud: refer to Dean of Students
  └── Document all discrepancy findings and resolutions

STEP 6: Verification Complete
  ├── All documents approved, no outstanding discrepancies
  ├── Mark `finaid_verification_request.status = 'complete'`
  ├── Release disbursement hold
  └── Proceed to aid packaging → Workflow 3
```

### Decision Points
| Situation | Branch |
|-----------|--------|
| Student does not submit documents | Send escalating reminders; after deadline: suspend aid |
| Discrepancy found | Correct ISIR; recalculate need; re-notify student |
| Identity cannot be verified | Refer to Dean of Students; suspend aid |
| Verification deadline missed | Aid canceled for term; student must reapply next term |

### Data Flow
- **Input:** `finaid_isir` (verification flag)
- **Creates:** `finaid_verification_request`, `finaid_verification_document`
- **Updates:** `finaid_isir.verification_status`
- **Reads:** ISIR data for comparison

---

## Workflow 3: Aid Packaging

### Purpose
Create a complete financial aid package (award letter) for a student for a given aid year and term, combining all aid sources within Cost of Attendance and regulatory limits.

### Trigger
- ISIR received and reviewed (verification complete if applicable)
- Student enrolled in eligible program with at least half-time credit load

### Pre-conditions
- `finaid_isir` exists with status `reviewed`
- `finaid_cost_of_attendance` defined for student's program/term
- `educlaw_program_enrollment` is active

### Happy Path

```
STEP 1: Need Analysis
  ├── Retrieve COA from `finaid_cost_of_attendance` for program + term
  ├── Retrieve SAI from `finaid_isir`
  ├── Calculate Financial Need: Need = COA − SAI
  ├── Determine enrollment status (full-time/half-time/less-than-half)
  └── Apply enrollment intensity adjustment to COA if needed

STEP 2: Pell Grant Calculation
  ├── Retrieve Pell Index from ISIR
  ├── Look up Pell award from current Pell payment schedule
  ├── Adjust for enrollment status (full-time = 100%, ¾ = 75%, etc.)
  ├── Check Pell Lifetime Eligibility Used (LEU) — cap at 600% (12 semesters)
  └── If Pell-eligible: add Pell award to package

STEP 3: FSEOG Award (if applicable)
  ├── Check institution's FSEOG allocation balance
  ├── Prioritize students with lowest SAI (highest need)
  ├── Award up to $4,000/year (typically $100–$500 for most students)
  └── Add FSEOG to package if allocation available

STEP 4: Institutional Grant/Scholarship Award
  ├── Check student eligibility for each institutional scholarship program
  │     (GPA criteria, program, enrollment, need status)
  ├── Match student to eligible programs
  ├── Award institutional grants up to available allocation
  └── Add institutional awards to package

STEP 5: Federal Work-Study Award (if applicable)
  ├── Check FWS allocation balance
  ├── Prioritize students with financial need
  ├── Award FWS up to standard amount (institution sets)
  └── Add FWS award to package (not disbursed upfront — earned through work)

STEP 6: Direct Loan Packaging
  ├── Determine loan year (1st/2nd/3rd+) and student type (dep/indep)
  ├── Calculate remaining need after grants: Remaining Need = Need − Grants
  ├── Offer Subsidized Loan up to annual limit OR remaining need (lesser)
  ├── Offer Unsubsidized Loan up to annual limit minus subsidized awarded
  ├── Check aggregate loan limits (from NSLDS data on ISIR)
  └── Add loan offers to package

STEP 7: Overaward Check
  ├── Sum all awards: Grants + Loans + FWS + External Scholarships
  ├── Compare to COA: Total Aid ≤ COA (REQUIRED)
  ├── If overaward: reduce loans first, then work-study, then institutional grants
  └── If still over COA after reduction: flag for FAO review

STEP 8: Award Package Creation
  ├── Create `finaid_award_package` for student + aid year + term
  ├── Create one `finaid_award` record per aid type
  ├── Set package status = 'draft' for FAO review
  └── Log who packaged and when

STEP 9: FAO Review and Finalization
  ├── FAO reviews draft package
  ├── Adjust if needed (professional judgment)
  ├── Approve package → status = 'offered'
  └── Generate award letter → notify student

STEP 10: Award Letter Delivery
  ├── Send notification to student with award summary
  ├── List each award type, amount, and conditions
  ├── Provide deadline to accept/decline
  └── Include information on loan terms (for loan awards)
```

### Decision Points
| Situation | Branch |
|-----------|--------|
| Student not enrolled half-time | Cannot receive FSEOG; loan limits reduced; Pell prorated |
| Pell LEU at 600% | Cannot receive additional Pell; offer other aid |
| Aggregate loan limit reached | Cannot offer new loans; offer more grants if available |
| External scholarship received after packaging | Recalculate package; may reduce loan awards |
| SAI negative (extreme need) | May receive maximum Pell + full need-based package |
| SAI too high (wealthy family) | May qualify only for unsubsidized loans and institutional merit aid |

### Data Flow
- **Input:** `finaid_isir`, `finaid_cost_of_attendance`, `educlaw_program_enrollment`
- **Creates:** `finaid_award_package`, `finaid_award` (one per aid type)
- **Reads:** `finaid_scholarship_program`, institutional allocation balances
- **Updates:** Allocation balances for FSEOG, FWS, institutional funds

---

## Workflow 4: Award Acceptance

### Purpose
Student reviews and accepts or declines their financial aid package.

### Trigger
- `finaid_award_package.status = 'offered'` and student notified

### Happy Path

```
STEP 1: Student Reviews Award Letter
  ├── Student logs in and views award package
  ├── Sees breakdown: grants (free), loans (must repay), work-study (earned)
  └── Reads terms and conditions for each award type

STEP 2: Loan-Specific Requirements
  ├── If accepting Direct Subsidized/Unsubsidized:
  │     ├── First-time borrower: must complete Entrance Counseling
  │     ├── Must sign Master Promissory Note (MPN)
  │     └── Counseling + MPN tracked in `finaid_loan_requirement`
  └── If accepting PLUS Loan (for parent): separate MPN required

STEP 3: Award Acceptance
  ├── Student accepts full package OR partial (can decline individual awards)
  ├── Student may accept loans at lower amount than offered
  ├── Record acceptance decision per award
  ├── Update `finaid_award.acceptance_status` per award
  └── Update `finaid_award_package.status = 'accepted'`

STEP 4: Post-Acceptance Validation
  ├── Confirm MPN signed (for loans)
  ├── Confirm Entrance Counseling complete (first-time loan borrowers)
  ├── Confirm enrollment still active and half-time
  └── Release disbursement hold → proceed to Disbursement workflow
```

### Decision Points
| Situation | Branch |
|-----------|--------|
| Student declines all loans | Proceed with grants/work-study only |
| Student accepts less loan than offered | Adjust award to accepted amount |
| MPN not signed by deadline | Hold loan disbursement; send reminder |
| Student doesn't respond by deadline | Cancel unaccepted awards (usually 30-day window) |

---

## Workflow 5: Disbursement

### Purpose
Apply financial aid credits to the student's account and issue refunds for excess funds.

### Trigger
- Award package accepted
- Disbursement date reached (no earlier than 10 days before term start)
- All disbursement holds cleared

### Pre-conditions
- `finaid_award_package.status = 'accepted'`
- Enrollment confirmed (at least half-time)
- SAP status: Satisfactory or Warning
- Verification complete
- MPN signed (for loans)
- Entrance counseling complete (first-time loan borrowers)

### Happy Path

```
STEP 1: Pre-Disbursement Checks
  ├── Verify enrollment status (must be at least half-time)
  ├── Verify SAP status (must not be FSP)
  ├── Verify verification complete (if required)
  ├── Verify MPN signed and Entrance Counseling complete (for loans)
  ├── Verify no registration holds on student account
  └── If all checks pass: proceed to disbursement

STEP 2: Calculate Net Disbursement
  ├── For each award in accepted package:
  │     Grants (Pell, FSEOG, institutional): full term amount
  │     Loans: first half of term amount (per disbursement schedule)
  │     Work-study: NOT disbursed here (earned through work)
  └── Total disbursement = sum of all grant and loan amounts for term

STEP 3: COD Reporting (Pell and Direct Loans)
  ├── Generate COD origination record (before first disbursement)
  ├── Generate COD disbursement record (at disbursement)
  ├── Create COD XML Common Record (for manual submission in v1)
  └── Record COD confirmation when received

STEP 4: Post Credits to Student Account
  ├── Create GL credit entry for each aid type
  │     Debit: Financial Aid Receivable (or Fund)
  │     Credit: Student Account (erpclaw-selling customer account)
  ├── Apply credit against outstanding tuition/fee charges
  └── Record `finaid_disbursement` for each posted credit

STEP 5: Credit Balance (Refund)
  ├── Calculate: Credit Balance = Total Aid Credited − Total Charges
  ├── If Credit Balance > 0:
  │     Student has "credit balance" = excess aid over charges
  │     Must return to student within 14 days
  │     Create payment/refund via erpclaw-payments
  └── Record refund in `finaid_disbursement` with type='refund'

STEP 6: Second Disbursement (Mid-Term)
  ├── Second half of loans disbursed mid-term (typically week 6–8)
  ├── Re-verify enrollment before second disbursement
  └── Repeat steps 3–5 for second disbursement
```

### Disbursement Holds
| Hold Reason | Condition | Release Trigger |
|------------|-----------|----------------|
| Verification incomplete | ISIR has verification flag | Verification marked complete |
| MPN not signed | First-time loan borrower | MPN signed at studentaid.gov |
| Entrance counseling incomplete | First-time borrower | Counseling completed at studentaid.gov |
| SAP suspension | Student in FSP status | SAP appeal approved, or term meets SAP |
| Enrollment not confirmed | Below half-time | Enrollment confirmed by Registrar |
| Registration hold | educlaw_student.registration_hold = 1 | Hold released by Registrar |

### Data Flow
- **Input:** `finaid_award_package` (accepted awards)
- **Creates:** `finaid_disbursement` per disbursement event
- **Reads:** `educlaw_student` (enrollment, holds), `finaid_sap_evaluation`
- **Posts to:** erpclaw-selling (student account credits), erpclaw-gl (journal entries)

---

## Workflow 6: SAP Evaluation

### Purpose
Evaluate each financial aid recipient's academic progress at the end of each term to determine continued aid eligibility.

### Trigger
- End of each academic term (grades finalized in educlaw)
- `educlaw_academic_term.status = 'grades_finalized'`

### Pre-conditions
- All grades submitted for the term
- Student has active financial aid record

### Happy Path

```
STEP 1: Batch Evaluation Initiation
  ├── FAO triggers SAP evaluation batch for term
  ├── System identifies all students with active aid packages
  └── Process each student:

STEP 2: Collect Academic Data (per student)
  ├── From educlaw_student:
  │     cumulative_gpa → qualitative measure
  │     total_credits_earned → pace numerator
  ├── From educlaw_course_enrollment (all history, not just this term):
  │     Sum all enrolled credits (including W, F, I) → attempted
  │     Sum all passed credits (excluding W, F) → completed
  │     Flag: is_repeat → handle repeated course credits
  ├── From educlaw_program:
  │     total_credits_required → max timeframe denominator
  └── From NSLDS (on ISIR):
       Transfer credits attempted and completed

STEP 3: Qualitative Measure
  ├── cumulative_gpa >= institution_minimum_gpa (typically 2.0)
  ├── Record: gpa, threshold, pass/fail
  └── Component 1 result: PASS or FAIL

STEP 4: Quantitative Measure (Pace)
  ├── completion_rate = total_credits_completed / total_credits_attempted
  ├── completion_rate >= 0.67 (67%)
  ├── Record: attempted, completed, rate, threshold
  └── Component 2 result: PASS or FAIL

STEP 5: Maximum Timeframe
  ├── max_allowed = program_credits_required × 1.5
  ├── projected_completion = credits_attempted + credits_remaining
  ├── projected_completion <= max_allowed
  ├── Record: max allowed, current attempted, projected
  └── Component 3 result: PASS or FAIL

STEP 6: Determine SAP Status
  ├── If all 3 PASS: status = 'SAT' (satisfactory)
  │     → aid continues unchanged
  ├── If ANY FAIL:
  │     ├── If prior status = 'SAT': → status = 'FAW' (warning)
  │     │     First offense: aid continues with warning
  │     ├── If prior status = 'FAW': → status = 'FSP' (suspension)
  │     │     Aid suspended next term
  │     ├── If max timeframe exceeded: → status = 'FSP' (no warning)
  │     └── If prior status = 'FAP' and still failing: → status = 'FSP'

STEP 7: Record and Notify
  ├── Create `finaid_sap_evaluation` record
  ├── Store all component details and final status
  ├── If SAT or FAW: notify student (informational)
  ├── If FSP: notify student of suspension + appeal rights
  └── Place disbursement hold for FSP students (next term)
```

### Edge Cases
| Case | Handling |
|------|---------|
| Student with no prior financial aid | First evaluation after any term with aid |
| Transfer student | Include transfer credits (attempted and completed) in all calculations |
| Repeated course | Count each attempt as "attempted"; only one completion counts |
| Incomplete (I) grade | Counts as attempted, not completed; re-evaluate when grade posted |
| Audit courses | Excluded from SAP calculations |
| Remedial/developmental courses | Excluded from max timeframe; count for pace |
| Student not receiving aid this term | Evaluate only if previously received aid |

### Data Flow
- **Input:** `educlaw_course_enrollment`, `educlaw_student`, `finaid_isir` (transfer credits)
- **Creates:** `finaid_sap_evaluation` per student per term
- **Updates:** `finaid_award_package` (disbursement hold for FSP)
- **Triggers:** Student notification, next-term disbursement hold

---

## Workflow 7: SAP Appeal

### Purpose
Allow students who fail SAP to appeal for reinstatement of financial aid.

### Trigger
- Student receives SAP suspension notice (status = 'FSP')
- Student submits appeal

### Happy Path

```
STEP 1: Appeal Submission
  ├── Student provides written statement explaining circumstances
  │     (death in family, illness, divorce, natural disaster, etc.)
  ├── Student provides documentation supporting circumstances
  └── Student provides academic plan (path to meet SAP)

STEP 2: Appeal Review
  ├── FAO counselor reviews appeal package
  ├── Confirms circumstances are valid/documented
  ├── Evaluates academic plan (realistic? achievable?)
  └── Makes decision: grant or deny

STEP 3A: Appeal Denied
  ├── Record denial with reason
  ├── Notify student: aid remains suspended
  ├── Advise on options (private loans, payment plan, re-enrollment)
  └── Student may re-appeal or improve grades without aid

STEP 3B: Appeal Granted
  ├── Record approval with conditions
  ├── Place student on FAP (probation) status
  ├── Define conditions: "must earn X GPA next term" or "follow academic plan"
  ├── Release disbursement hold for next term
  └── Schedule re-evaluation at end of probation term

STEP 4: Probation Evaluation
  ├── End of probation term: evaluate SAP again
  ├── If meets SAP: → status = 'SAT'; full reinstatement
  ├── If complying with academic plan: → may continue FAP
  └── If fails SAP and not following plan: → status = 'FSP' reinstated
```

### Data Flow
- **Input:** `finaid_sap_evaluation` (FSP status)
- **Creates:** `finaid_sap_appeal`
- **Updates:** `finaid_sap_evaluation.appeal_status`, student's SAP status
- **Releases:** Disbursement hold if appeal granted

---

## Workflow 8: Return of Title IV Funds (R2T4)

### Purpose
Calculate and process the return of unearned federal financial aid when a student withdraws.

### Trigger
- Student officially withdraws (all courses dropped)
- Student unofficially withdraws (stops attending — determined by institution)
- `educlaw_student.status` changes to 'withdrawn' or all `educlaw_course_enrollment` records have status 'withdrawn'

### Pre-conditions
- Student received or was scheduled to receive Title IV aid

### Happy Path

```
STEP 1: Withdrawal Detection
  ├── Official: student submits withdrawal; last date of attendance = withdrawal date
  ├── Unofficial: FAO determines student stopped attending
  │     Last Date of Attendance (LDA) = last documented academically-related activity
  └── Record withdrawal date and LDA in `finaid_r2t4_calculation`

STEP 2: Determine Payment Period
  ├── Get term start date (from educlaw_academic_term)
  ├── Get term end date
  ├── Exclude scheduled breaks of 5+ consecutive days
  └── Calculate total days in payment period

STEP 3: Calculate % of Period Completed
  ├── Days attended = LDA − Term Start Date
  ├── % completed = Days Attended / Total Days in Period
  ├── If % completed > 60%: student earned 100% → no return required
  └── Record calculation details

STEP 4: Calculate Earned Aid
  ├── Total Title IV aid disbursed (or could have been disbursed)
  │     Pell + FSEOG + Direct Loans (not FWS — excluded)
  ├── If disbursed < eligible: use "could have been disbursed" for some aid
  ├── Earned Aid = % completed × Total Aid
  └── Unearned Aid = Disbursed − Earned Aid

STEP 5: Determine Institution vs. Student Responsibility
  ├── Institution's responsibility = lesser of:
  │     Total institutional charges × % unearned
  │     OR total unearned Title IV aid
  ├── Remaining unearned = Student's responsibility
  └── Record both amounts

STEP 6: Return Order (Institution's Portion)
  Return unearned funds in this order:
  ├── 1. Unsubsidized Direct Loan
  ├── 2. Subsidized Direct Loan
  ├── 3. Direct PLUS Loan (Graduate)
  ├── 4. Direct PLUS Loan (Parent)
  ├── 5. Pell Grant
  ├── 6. FSEOG
  └── 7. TEACH Grant

STEP 7: Post-Withdrawal Disbursement (if applicable)
  ├── If Earned Aid > Disbursed: student is owed a post-withdrawal disbursement
  ├── Loans: notify student within 30 days; student has 14 days to accept
  ├── Grants: disburse automatically within 45 days
  └── Record post-withdrawal disbursement

STEP 8: Process Returns
  ├── Return funds to ED via COD/G5 within 45 days of withdrawal determination
  ├── Create GL entries for returned funds
  ├── Update `finaid_disbursement` with return amounts
  └── Notify student of any remaining balance owed to institution

STEP 9: Documentation
  ├── Archive complete R2T4 worksheet (required for audit)
  ├── Record who calculated, who approved, return date
  └── Note in student record: withdrawal processed, R2T4 complete
```

### Key Calculations

```
Payment Period = Total Days in Term (excluding scheduled breaks ≥5 days)
Days Attended = LDA date − Term Start Date + 1
% Completed = Days Attended / Payment Period
If % Completed > 0.60: Earned = 100%
Else: Earned = % Completed (as decimal)

Earned Aid = Earned (%) × Total Aid Disbursed (or scheduleable)
Unearned Aid = Total Aid − Earned Aid
Institution Return = min(Total Charges × (1 − Earned %), Unearned Aid)
Student Return = Unearned Aid − Institution Return
```

### Data Flow
- **Input:** `educlaw_course_enrollment` (withdrawal dates), `finaid_award_package`
- **Creates:** `finaid_r2t4_calculation`
- **Updates:** `finaid_disbursement` (return records), GL entries
- **Posts to:** erpclaw-gl (return entries)

---

## Workflow 9: Institutional Scholarship Management

### Purpose
Define, award, and track institutional scholarship programs (merit and need-based).

### Sub-flows:

#### 9A: Scholarship Program Definition (Admin)
```
Admin creates scholarship program:
├── Name, funding source (endowment, general budget, departmental)
├── Award amount (fixed or calculated)
├── Renewal terms (GPA requirement, enrollment requirement)
├── Eligibility criteria (program, year, GPA, need threshold)
├── Application required? (yes/no)
├── Award limit (total students, total dollars)
└── Status: active/inactive
```

#### 9B: Scholarship Award (Auto-match or Application)
```
Auto-match:
├── System identifies eligible students based on criteria
├── Rank by criteria (need, GPA, etc.)
├── Award up to capacity
└── Notify students

Application-based:
├── Student submits scholarship application
├── Optional: essay, recommendations
├── Committee reviews
├── Award decision
└── Notify applicants (awarded/waitlisted/denied)
```

#### 9C: Scholarship Renewal
```
End of each term:
├── Check renewal criteria for each active scholarship
├── Verify student meets GPA/enrollment requirements
├── If meets: renew for next term
├── If fails: notify student; may have one-term grace period
└── Revoke if criteria not met
```

### Data Flow
- **Creates:** `finaid_scholarship_program`, `finaid_scholarship_application`, `finaid_scholarship_award`
- **Updates:** `finaid_award_package` (scholarship credits)

---

## Workflow 10: Federal Work-Study (FWS) Management

### Purpose
Manage FWS job postings, student assignments, timesheets, and earnings tracking.

### Happy Path

```
STEP 1: FWS Job Posting
  ├── Department posts FWS job
  ├── Pay rate, hours per week, job description
  ├── On-campus or off-campus (community service)
  └── Available positions count

STEP 2: Student Assignment
  ├── FAO awards FWS to eligible students (packaged in aid package)
  ├── Student applies for posted jobs
  ├── Supervisor selects student
  ├── Create `finaid_work_study_assignment`
  └── Define: start date, end date, max hours, pay rate, FWS award limit

STEP 3: Timesheet Entry
  ├── Student enters hours worked each pay period
  ├── Supervisor reviews and approves hours
  ├── System calculates earnings (hours × pay rate)
  ├── Check: running total ≤ FWS award limit
  └── If earnings would exceed award: stop and notify

STEP 4: Payroll Processing
  ├── Export approved timesheets to payroll
  ├── Student receives paycheck (NOT applied to student account)
  ├── Record earnings in `finaid_work_study_timesheet`
  └── Update running earned total vs. award limit

STEP 5: Award Exhaustion
  ├── When student reaches FWS award limit: stop taking additional hours
  ├── Notify student and supervisor
  └── Excess hours would be paid from departmental budget (not FWS)
```

---

## Workflow 11: Loan Tracking

### Purpose
Track all federal student loans from origination through repayment status.

### Happy Path

```
STEP 1: Loan Origination Setup
  ├── Student accepted loan in award package
  ├── Check aggregate loan limit (NSLDS data from ISIR)
  ├── Verify MPN signed
  ├── Verify entrance counseling complete (first-time borrowers)
  └── Create `finaid_loan` record

STEP 2: COD Origination
  ├── Generate COD origination record (Loan Origination ID, award year, period)
  ├── Submit to COD (manual XML in v1, or COD web portal)
  └── Record COD confirmation / origination acknowledgment

STEP 3: Disbursement
  ├── First disbursement: typically start of term
  ├── Second disbursement: mid-term (week 6–8)
  ├── Generate COD disbursement record
  └── Credit to student account (part of Workflow 5)

STEP 4: Exit Counseling (on withdrawal or graduation)
  ├── Flag student for exit counseling requirement
  ├── Notify student to complete exit counseling at studentaid.gov
  ├── Track completion date
  └── Inform student of repayment options and servicer

STEP 5: NSLDS Enrollment Reporting
  ├── Report enrollment status to NSLDS each term
  ├── Update: enrolled, withdrawn, graduated
  ├── Servicers use this to determine deferment/repayment status
  └── Required within 60 days of term start or status change
```

---

## Workflow 12: Professional Judgment

### Purpose
Document FAA decisions to override standard federal formulas for students with special circumstances.

### Trigger
- Student or FAO identifies circumstance that affects aid eligibility

### Types of PJ Actions

| PJ Type | Example | Action |
|---------|---------|--------|
| SAI/COA Adjustment | Parent lost job; death in family | Reduce SAI or increase COA |
| Dependency Override | Abused student can't contact parents | Change to independent status |
| Enrollment Status Override | Medical leave — maintain full-time status | Adjust for disbursement purposes |
| Non-standard Aid Year | Student's situation doesn't fit standard year | Custom packaging |

### Required Documentation
All PJ actions must be documented with:
- Reason for override
- Original value and adjusted value
- Supporting documentation reference
- FAA name, credentials, date
- Supervisor approval (for large adjustments)

### Data Flow
- **Creates:** `finaid_professional_judgment`
- **Updates:** `finaid_isir` (adjusted SAI), `finaid_cost_of_attendance` (adjusted COA), or `finaid_award_package`
- **Triggers:** Repackaging if SAI or COA changes
