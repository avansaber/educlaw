# Parent Product Analysis: EduClaw (educlaw)

**Parent:** educlaw v1.0.0
**Parent Path:** [REDACTED]
**Analysis Date:** 2026-03-05
**Purpose:** Determine what educlaw-finaid can reuse vs. must extend

---

## 1. Parent Overview

EduClaw is an AI-native Student Information System (SIS) built on ERPClaw. It provides:

- **112 actions** across 8 domains
- **32 domain tables** in SQLite
- FERPA/COPPA compliance baked in
- Students modeled as ERPClaw `customer` records
- Tuition invoices modeled as ERPClaw sales invoices
- All fees post to the ERPClaw General Ledger
- Fully offline / local-only architecture

### Foundation Skills (Inherited by educlaw-finaid)
| Skill | Relevance to Financial Aid |
|-------|---------------------------|
| `erpclaw-setup` | Company, user, and permission management |
| `erpclaw-gl` | GL accounts, journal entries, fund accounting |
| `erpclaw-selling` | Student-as-customer, invoices, payment terms |
| `erpclaw-payments` | Payment processing, receipts, reconciliation |
| `erpclaw-hr` | Staff management (financial aid counselors) |

---

## 2. Parent Table Inventory

### Tables Directly Reusable by educlaw-finaid (No Extension Needed)

| Table | How finaid uses it |
|-------|--------------------|
| `educlaw_student` | Student identity, SSN (encrypted), academic standing, GPA, COPPA flag |
| `educlaw_academic_year` | Award year alignment (aid is year-based) |
| `educlaw_academic_term` | Term-based COA and disbursement scheduling |
| `educlaw_program` | Program type determines aid eligibility and loan limits |
| `educlaw_program_enrollment` | Enrollment status affects disbursement holds |
| `educlaw_course_enrollment` | Credits enrolled/completed for SAP calculation |
| `educlaw_guardian` | Parent data for dependent student FAFSA |
| `educlaw_student_guardian` | Guardian-student relationship (dependency status) |
| `educlaw_data_access_log` | FERPA audit trail (finaid data is FERPA-protected) |
| `educlaw_consent_record` | Student consent for Title IV disclosure |
| `educlaw_announcement` | Aid award notifications to students |
| `educlaw_notification` | Individual award/disbursement alerts |

### Tables Partially Reusable (educlaw-finaid Extends)

| Table | Current Capability | What finaid Needs to Add |
|-------|--------------------|--------------------------|
| `educlaw_scholarship` | Basic discount (fixed/%) per student per term | Replace with richer `finaid_scholarship_program` + `finaid_scholarship_application` pattern; parent table is too simple for institutional aid management |
| `educlaw_fee_structure` | Tuition fee structures per program/term | finaid reads COA from fee structures; finaid adds its own `finaid_cost_of_attendance` for non-tuition components (housing, meals, books, travel) |
| `educlaw_fee_category` | Revenue categories | finaid creates specific categories: financial_aid_credit, scholarship_credit, loan_disbursement |
| `educlaw_student_attendance` | Raw attendance records | SAP quantitative measure uses course enrollment completions, not raw attendance directly |

### Tables NOT Used by educlaw-finaid

| Table | Reason |
|-------|--------|
| `educlaw_room` | Physical rooms not relevant to financial aid |
| `educlaw_instructor` | Instructors not involved in financial aid |
| `educlaw_section` | Section-level data not needed (finaid works at term level) |
| `educlaw_waitlist` | Course waitlist not related to financial aid |
| `educlaw_assessment_plan` / `educlaw_assessment` / `educlaw_assessment_result` | Grading internals not needed |
| `educlaw_grade_amendment` | Grade amendments affect SAP recalculation but are handled by educlaw |
| `educlaw_grading_scale` | finaid reads final grades, not grading methodology |
| `educlaw_student_applicant` | Admissions flow separate from financial aid |
| `educlaw_assessment_category` | Not needed |

---

## 3. Key Data Available from Parent

### Student Record (`educlaw_student`)
```
- id, naming_series (linking key)
- ssn_encrypted (critical for FAFSA matching)
- date_of_birth (age/dependency determination)
- email, phone, address (aid correspondence)
- current_program_id (program eligibility)
- cumulative_gpa (SAP qualitative measure)
- total_credits_earned (SAP quantitative)
- academic_standing (probation/suspension tracking)
- status (active/withdrawn — triggers R2T4)
- enrollment_date, graduation_date
- customer_id (links to erpclaw-selling for disbursement)
- is_coppa_applicable (age verification for dependent status)
- directory_info_opt_out
```

### Course Enrollment (`educlaw_course_enrollment`)
```
- student_id, section_id
- enrollment_date, enrollment_status (enrolled/dropped/withdrawn/incomplete)
- drop_date (critical for R2T4 last-date-of-attendance)
- final_letter_grade, final_grade_points, final_percentage
- is_grade_submitted
- is_repeat (repeated courses affect SAP)
- grade_type (audit grades excluded from SAP)
```

### Program Enrollment (`educlaw_program_enrollment`)
```
- student_id, program_id, academic_year_id
- enrollment_status (active/completed/withdrawn/suspended)
- fee_invoice_id (tuition billing link)
```

### Academic Term (`educlaw_academic_term`)
```
- term_type (semester/quarter/trimester — affects loan limits)
- start_date, end_date (payment period dates)
- status (enrollment_open/active/closed)
```

### Guardian (`educlaw_guardian`)
```
- relationship, occupation, employer
- customer_id (for parent PLUS loan billing)
```

---

## 4. Actions Available from Parent

### Actions educlaw-finaid Can Call Directly

| Action | Use in Financial Aid |
|--------|---------------------|
| `get-student` | Retrieve student for aid processing (auto-logs FERPA) |
| `list-students` | Batch SAP evaluation, cohort reports |
| `list-enrollments` | Determine credit load for COA and SAP |
| `get-attendance-summary` | Part of SAP qualitative evaluation |
| `generate-transcript` | Required for SAP review |
| `get-student-account` | Check existing fee invoices and balances |
| `generate-fee-invoice` | Issue tuition charge (finaid credits against this) |
| `add-scholarship` | Post simple institutional discount (parent action, may be deprecated by finaid) |
| `send-notification` | Notify student of aid award/verification request |
| `add-announcement` | Broadcast financial aid deadlines |
| `add-consent-record` | Document Title IV authorization |
| `record-data-access` | Manual FERPA log for financial data access |

---

## 5. Key Gaps — What educlaw-finaid Must Add

### Domain: Financial Aid Application (FAFSA/ISIR)
Parent has **zero** FAFSA/ISIR handling. Need:
- ISIR storage and C-flag tracking
- Verification workflow (documents, status)
- SAI/need analysis calculation
- Award year management

### Domain: Aid Packaging & Awards
Parent's `educlaw_scholarship` is a simple discount applied to an invoice. Financial aid packaging requires:
- Multi-source award packages (Pell + loans + work-study + institutional)
- Overaward detection (cannot exceed COA)
- Aggregate loan limit enforcement
- Award notification / acceptance workflow

### Domain: Disbursements
Parent posts fees and scholarships through erpclaw-selling. Financial aid disbursement requires:
- COD origination and disbursement records (for Pell, loans)
- Credit-to-student-account posting
- Refund processing (excess aid over charges)
- Disbursement holds (enrollment, SAP, MPN)
- 45-day disbursement window compliance

### Domain: SAP Evaluation
Parent tracks `academic_standing` and `cumulative_gpa` on the student record but has no:
- Per-term SAP status calculation
- Completion rate (pace) calculation
- Maximum timeframe tracking
- SAP Warning / Suspension / Appeal lifecycle
- Financial aid-specific SAP policies (separate from academic standing)

### Domain: Return of Title IV (R2T4)
No parent support for:
- Withdrawal processing workflow
- R2T4 calculation (% completed × aid awarded)
- Post-withdrawal disbursement determination
- Refund scheduling and tracking

### Domain: Loan Management
No parent support for:
- Loan origination records
- MPN tracking (signed / not signed)
- Entrance/exit counseling completion
- Annual and aggregate loan limit enforcement
- NSLDS enrollment reporting

### Domain: Institutional Scholarships (Enhanced)
Parent's `educlaw_scholarship` is too simple:
- No scholarship program definition (eligibility criteria)
- No application workflow
- No renewal tracking / GPA maintenance
- No endowment/funding source tracking
- No batch awarding capability

### Domain: Federal Work-Study
No parent support for:
- FWS job postings
- Student job applications and assignments
- Timesheet tracking
- Hours-to-earnings conversion
- FWS allocation limits per student

---

## 6. Architecture Constraints & Integration Points

### Naming Conventions (Must Follow Parent)
- IDs: `TEXT PRIMARY KEY` (UUID4)
- Money: `TEXT NOT NULL DEFAULT '0'` (Python Decimal)
- Dates: `TEXT NOT NULL DEFAULT ''` (ISO 8601)
- Status: `TEXT NOT NULL DEFAULT 'X' CHECK(status IN (...))`
- Boolean: `INTEGER NOT NULL DEFAULT 0`
- All tables get `created_at`, `updated_at`, `created_by`
- FK pattern: `TEXT REFERENCES table(id) ON DELETE RESTRICT`

### Vocabulary Mapping (Adaptive Vocabulary)
From erpforge.yaml:
- customer → student
- order → enrollment
- transaction → fee payment
- item → course
- employee → teacher

Financial aid adds its own vocabulary:
- award → financial aid package
- disbursement → aid payment
- COA → cost of attendance budget

### Data Flow with Parent

```
educlaw_student ──────────────────────→ finaid_isir
                                         finaid_award_package
educlaw_course_enrollment ────────────→ finaid_sap_evaluation
educlaw_program_enrollment ───────────→ finaid_award_package (term/year link)
educlaw_guardian ─────────────────────→ finaid_isir (dependent student parent data)
educlaw_academic_term ────────────────→ finaid_cost_of_attendance
                                         finaid_disbursement
erpclaw-selling (customer/invoice) ──→ finaid_disbursement (credit posting)
erpclaw-gl (journal entries) ─────────→ finaid_disbursement (fund accounting)
```

---

## 7. Recommended Integration Strategy

1. **Read parent data, don't duplicate**: finaid reads student, enrollment, and grade data from parent tables via the existing educlaw actions. It does not copy or shadow this data.

2. **Extend the fee/billing model**: Use erpclaw-selling invoice as the student account. Financial aid credits are posted as negative line items against tuition invoices. Disbursements trigger erpclaw-payments entries.

3. **Deprecate `educlaw_scholarship` for institutional aid**: The parent scholarship is too simplistic. educlaw-finaid introduces `finaid_scholarship_program` + `finaid_scholarship_application` as the authoritative institutional aid model. The parent `educlaw_scholarship` action (`add-scholarship`) should be wrapped/replaced for higher-ed use cases.

4. **FERPA compliance inheritance**: All finaid data access must log to `educlaw_data_access_log` with `data_category = 'financial'`. The parent's FERPA infrastructure handles this — finaid must call the `record-data-access` action for every student record retrieval.

5. **Notification reuse**: Use parent's `send-notification` for award notifications, verification requests, and disbursement alerts.

---

## 8. Parent Version and Stability

- educlaw is at **v1.0.0**
- 32 tables are stable and indexed appropriately
- The schema uses a consistent, production-ready pattern
- educlaw-finaid should target **schema stability** — add new tables rather than modifying parent tables
- Only soft coupling via FK references — no circular dependencies expected
