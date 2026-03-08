# Data Model Insights: EduClaw Financial Aid

**Product:** EduClaw Financial Aid (educlaw-finaid)
**Research Date:** 2026-03-05

---

## 1. Design Principles

### Inherited from educlaw (Parent)
- IDs: `TEXT PRIMARY KEY` (UUID4)
- Money: `TEXT NOT NULL DEFAULT '0'` (Python Decimal for exact arithmetic)
- Dates: `TEXT NOT NULL DEFAULT ''` (ISO 8601 YYYY-MM-DD)
- Timestamps: `TEXT NOT NULL DEFAULT ''` (ISO 8601 datetime)
- Status fields: `TEXT NOT NULL DEFAULT 'X' CHECK(status IN (...))`
- Booleans: `INTEGER NOT NULL DEFAULT 0`
- Free text: `TEXT NOT NULL DEFAULT ''`
- JSON arrays/objects: `TEXT NOT NULL DEFAULT '[]'` or `'{}'`
- All FKs: `ON DELETE RESTRICT`
- All tables: `created_at`, `updated_at` (except append-only audit tables), `created_by`

### Financial Aid Specific
- **Immutability**: Disbursement records are append-only (never updated; reversals create new records)
- **Audit trail**: Every status change on award/package must have `changed_by` and `changed_at`
- **FERPA**: All reads of these tables must log to `educlaw_data_access_log` with `data_category='financial'`
- **Decimal precision**: All monetary amounts stored as TEXT with 2 decimal places minimum
- **Aid year vs academic year**: These are different time periods — maintain both FK references

---

## 2. Entity Relationship Overview

```
educlaw_student (parent)
  │
  ├──→ finaid_isir (one per student per aid year)
  │       │
  │       ├──→ finaid_isir_cflag (one per C-flag per ISIR)
  │       ├──→ finaid_verification_request (one per ISIR if flagged)
  │       │       └──→ finaid_verification_document (many per request)
  │       └──→ finaid_award_package (one per student per term)
  │               │
  │               ├──→ finaid_award (one per aid type per package)
  │               │       └──→ finaid_disbursement (one+ per award)
  │               └──→ finaid_professional_judgment (optional)
  │
  ├──→ finaid_sap_evaluation (one per student per term)
  │       └──→ finaid_sap_appeal (one+ per evaluation)
  │
  ├──→ finaid_r2t4_calculation (one per withdrawal event)
  │
  ├──→ finaid_loan (one per loan, per award year)
  │       └──→ finaid_loan_requirement (MPN, entrance counseling)
  │
  └──→ finaid_work_study_assignment (one per job per student)
          └──→ finaid_work_study_timesheet (one per pay period)

finaid_aid_year (global config)
  ├──→ finaid_cost_of_attendance (per program/enrollment status/aid year)
  ├──→ finaid_pell_schedule (Pell award schedule per aid year)
  └──→ finaid_fund_allocation (FSEOG/FWS institutional allocations)

finaid_scholarship_program (institutional scholarship definition)
  └──→ finaid_scholarship_application (student applies)
          └──→ finaid_scholarship_award (decision and term awards)

finaid_work_study_job (FWS job postings)
  └──→ finaid_work_study_assignment (student assigned to job)
```

---

## 3. Core Table Definitions

### 3.1 `finaid_aid_year`

The master configuration for each federal award year.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `aid_year_code` | TEXT | e.g., '2526' (2025-26) |
| `description` | TEXT | e.g., 'Aid Year 2025-2026' |
| `start_date` | TEXT | Always July 1 (e.g., 2025-07-01) |
| `end_date` | TEXT | Always June 30 (e.g., 2026-06-30) |
| `pell_max_award` | TEXT | e.g., '7395.00' |
| `is_active` | INTEGER | Currently open for packaging |
| `company_id` | TEXT FK | company |

**Key Indexes:** `(company_id, aid_year_code)` UNIQUE, `(company_id, is_active)`

---

### 3.2 `finaid_isir`

Stores ISIR (FAFSA processing output) per student per aid year. May have multiple transactions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK | educlaw_student |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `transaction_number` | INTEGER | ISIR transaction (01 = original) |
| `is_active_transaction` | INTEGER | 1 = current transaction used for packaging |
| `fafsa_submission_id` | TEXT | FAFSA tracking ID |
| `receipt_date` | TEXT | Date ISIR received |
| `sai` | TEXT | Student Aid Index (formerly EFC) |
| `sai_is_negative` | INTEGER | SAI can be −1500 to indicate extreme need |
| `dependency_status` | TEXT | CHECK(IN ('dependent','independent')) |
| `dependency_override` | INTEGER | FAA overrode dependency |
| `pell_index` | TEXT | Pell eligibility index |
| `pell_scheduled_award` | TEXT | Calculated Pell for full-time full-year |
| `pell_lifetime_eligibility_used` | TEXT | LEU % (max 600%) |
| `verification_flag` | INTEGER | 1 = selected for verification |
| `verification_group` | TEXT | CHECK(IN ('V1','V4','V5','')) |
| `has_unresolved_cflags` | INTEGER | Cached — must check finaid_isir_cflag |
| `nslds_default_flag` | INTEGER | Loan default match |
| `nslds_overpayment_flag` | INTEGER | Grant overpayment match |
| `selective_service_flag` | INTEGER | 1 = match issue |
| `citizenship_flag` | INTEGER | 1 = citizenship match issue |
| `agi` | TEXT | Adjusted Gross Income from FAFSA |
| `household_size` | INTEGER | Family size |
| `family_members_in_college` | INTEGER | For SAI formula |
| `aggregate_loan_borrowed` | TEXT | Total loans from NSLDS history |
| `aggregate_sub_loan_borrowed` | TEXT | Subsidized loans from NSLDS |
| `status` | TEXT | CHECK(IN ('received','under_review','reviewed','packaged','archived')) |
| `reviewed_by` | TEXT | Staff user ID |
| `reviewed_at` | TEXT | Date reviewed |
| `raw_isir_data` | TEXT | Full ISIR JSON (for audit) |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(student_id, aid_year_id, transaction_number)` UNIQUE
- `(student_id, aid_year_id, is_active_transaction)`
- `(company_id, status)`

---

### 3.3 `finaid_isir_cflag`

Individual C-flag records per ISIR (one row per flag).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `isir_id` | TEXT FK | finaid_isir |
| `student_id` | TEXT FK | educlaw_student (denormalized for queries) |
| `cflag_code` | TEXT | e.g., 'C25', 'C01', 'C07' |
| `cflag_description` | TEXT | Human-readable description |
| `blocks_disbursement` | INTEGER | 1 = cannot disburse until resolved |
| `resolution_status` | TEXT | CHECK(IN ('pending','resolved','waived')) |
| `resolution_date` | TEXT | When resolved |
| `resolved_by` | TEXT | Staff user ID |
| `resolution_notes` | TEXT | Documentation |

**Key Indexes:** `(isir_id, cflag_code)`, `(student_id, resolution_status)`

---

### 3.4 `finaid_verification_request`

Tracks the verification process for a flagged ISIR.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `isir_id` | TEXT FK | finaid_isir |
| `student_id` | TEXT FK | educlaw_student |
| `verification_group` | TEXT | V1 / V4 / V5 |
| `status` | TEXT | CHECK(IN ('initiated','documents_requested','in_review','discrepancy','complete','withdrawn')) |
| `requested_date` | TEXT | When student was notified |
| `deadline_date` | TEXT | Document submission deadline |
| `completed_date` | TEXT | When verification concluded |
| `discrepancy_found` | INTEGER | 1 = FAFSA data needed correction |
| `discrepancy_notes` | TEXT | What was different |
| `assigned_to` | TEXT | FAO staff user ID |
| `company_id` | TEXT FK | company |

**Key Indexes:** `(isir_id)` UNIQUE, `(student_id, status)`, `(company_id, status)`

---

### 3.5 `finaid_verification_document`

Individual documents required and collected per verification request.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `verification_request_id` | TEXT FK | finaid_verification_request |
| `student_id` | TEXT FK | educlaw_student |
| `document_type` | TEXT | CHECK(IN ('tax_transcript','w2','household_verification','identity','statement_of_purpose','snap_verification','child_support','hs_completion','other')) |
| `document_description` | TEXT | Human-readable description |
| `is_required` | INTEGER | 1 = required for this verification group |
| `submission_status` | TEXT | CHECK(IN ('not_submitted','submitted','accepted','rejected','waived')) |
| `submitted_date` | TEXT | |
| `reviewed_by` | TEXT | Staff user ID |
| `reviewed_date` | TEXT | |
| `rejection_reason` | TEXT | If rejected |
| `document_reference` | TEXT | File path or document ID |

**Key Indexes:** `(verification_request_id, document_type)`, `(student_id, submission_status)`

---

### 3.6 `finaid_cost_of_attendance`

Budget components for cost of attendance per program, enrollment status, and aid year.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `program_id` | TEXT FK | educlaw_program (nullable — can be institution-wide) |
| `enrollment_status` | TEXT | CHECK(IN ('full_time','three_quarter','half_time','less_than_half')) |
| `living_arrangement` | TEXT | CHECK(IN ('on_campus','off_campus','with_parent','')) |
| `tuition_fees` | TEXT | Annual tuition and mandatory fees |
| `books_supplies` | TEXT | Estimated books and supplies |
| `room_board` | TEXT | Housing and meal costs |
| `transportation` | TEXT | Local transportation estimate |
| `personal_expenses` | TEXT | Personal/miscellaneous |
| `loan_fees` | TEXT | Average loan origination fees |
| `total_coa` | TEXT | Calculated: sum of all components |
| `is_active` | INTEGER | |
| `company_id` | TEXT FK | company |

**Key Indexes:** `(aid_year_id, program_id, enrollment_status, living_arrangement)` UNIQUE, `(company_id, aid_year_id)`

---

### 3.7 `finaid_award_package`

The complete aid offer for one student for one term/year.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `naming_series` | TEXT UNIQUE | e.g., AWD-2526-00001 |
| `student_id` | TEXT FK | educlaw_student |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `academic_term_id` | TEXT FK | educlaw_academic_term |
| `program_enrollment_id` | TEXT FK | educlaw_program_enrollment |
| `isir_id` | TEXT FK | finaid_isir (the ISIR used for packaging) |
| `cost_of_attendance_id` | TEXT FK | finaid_cost_of_attendance |
| `enrollment_status` | TEXT | CHECK(IN ('full_time','three_quarter','half_time','less_than_half')) |
| `financial_need` | TEXT | COA − SAI |
| `total_grants` | TEXT | Sum of all grant awards |
| `total_loans` | TEXT | Sum of all loan awards (offered, not necessarily accepted) |
| `total_work_study` | TEXT | FWS award amount |
| `total_aid` | TEXT | Total of all aid types |
| `status` | TEXT | CHECK(IN ('draft','offered','accepted','partially_accepted','cancelled','disbursed')) |
| `offered_date` | TEXT | When award letter sent |
| `accepted_date` | TEXT | When student accepted |
| `acceptance_deadline` | TEXT | Deadline for student acceptance |
| `packaged_by` | TEXT | Staff user ID |
| `packaged_at` | TEXT | Timestamp |
| `approved_by` | TEXT | FAO approver |
| `approved_at` | TEXT | |
| `notes` | TEXT | Internal notes |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(student_id, aid_year_id, academic_term_id)` UNIQUE
- `(company_id, status)`
- `(aid_year_id, status)`

---

### 3.8 `finaid_award`

Individual award line item within a package.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `award_package_id` | TEXT FK | finaid_award_package |
| `student_id` | TEXT FK | educlaw_student (denormalized) |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `academic_term_id` | TEXT FK | educlaw_academic_term |
| `aid_type` | TEXT | CHECK(IN ('pell','fseog','subsidized_loan','unsubsidized_loan','plus_loan','parent_plus_loan','fws','institutional_grant','institutional_scholarship','state_grant','external_scholarship','tuition_waiver','teach_grant')) |
| `aid_source` | TEXT | CHECK(IN ('federal','state','institutional','external')) |
| `fund_source_id` | TEXT | FK to scholarship program or institutional fund (nullable) |
| `offered_amount` | TEXT | What was offered |
| `accepted_amount` | TEXT | What student accepted (may be less) |
| `disbursed_amount` | TEXT | Actual disbursed (running total) |
| `acceptance_status` | TEXT | CHECK(IN ('pending','accepted','declined','partial')) |
| `acceptance_date` | TEXT | |
| `disbursement_holds` | TEXT | JSON array of hold reasons |
| `is_locked` | INTEGER | 1 = cannot modify after first disbursement |
| `gl_account_id` | TEXT | FK to account (financial aid expense GL account) |
| `notes` | TEXT | |

**Key Indexes:**
- `(award_package_id, aid_type)` UNIQUE
- `(student_id, aid_year_id, aid_type)`
- `(company_id, aid_type, acceptance_status)` → needed for allocation tracking

---

### 3.9 `finaid_disbursement`

Actual funds applied to student account. Append-only (no updates; reversals create new records).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `award_id` | TEXT FK | finaid_award |
| `award_package_id` | TEXT FK | finaid_award_package |
| `student_id` | TEXT FK | educlaw_student |
| `disbursement_type` | TEXT | CHECK(IN ('disbursement','reversal','return','post_withdrawal')) |
| `disbursement_number` | INTEGER | 1, 2, 3... (for loans split per term) |
| `amount` | TEXT | Positive = credit; paired with reversal for returns |
| `disbursement_date` | TEXT | Date posted to student account |
| `gl_journal_id` | TEXT | FK to erpclaw-gl journal entry |
| `sales_invoice_id` | TEXT | FK to erpclaw-selling invoice (credit applied) |
| `cod_origination_id` | TEXT | COD origination ID (for Pell and Direct Loans) |
| `cod_disbursement_id` | TEXT | COD disbursement ID |
| `cod_status` | TEXT | CHECK(IN ('pending','reported','acknowledged','rejected','')) |
| `cod_response_date` | TEXT | When COD acknowledged |
| `is_credit_balance` | INTEGER | 1 = excess aid after charges (refund needed) |
| `credit_balance_amount` | TEXT | Amount to refund to student |
| `credit_balance_date` | TEXT | Date credit balance identified |
| `credit_balance_returned_date` | TEXT | Must be within 14 days |
| `disbursed_by` | TEXT | Staff user ID |
| `company_id` | TEXT FK | company |
| `created_at` | TEXT | Immutable — no updated_at |
| `created_by` | TEXT | |

**Key Indexes:**
- `(award_id, disbursement_number, disbursement_type)`
- `(student_id, disbursement_date)`
- `(company_id, cod_status)` — for reconciliation
- `(company_id, is_credit_balance)` — for credit balance tracking

---

### 3.10 `finaid_sap_evaluation`

SAP evaluation result per student per term.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK | educlaw_student |
| `academic_term_id` | TEXT FK | educlaw_academic_term |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `evaluation_date` | TEXT | When evaluation was run |
| `evaluation_type` | TEXT | CHECK(IN ('automatic','manual','appeal')) |
| `gpa_earned` | TEXT | Cumulative GPA at evaluation |
| `gpa_threshold` | TEXT | Institution's minimum (e.g., '2.00') |
| `gpa_meets_standard` | INTEGER | 1 = passes qualitative |
| `credits_attempted` | TEXT | Cumulative credits attempted |
| `credits_completed` | TEXT | Cumulative credits completed |
| `completion_rate` | TEXT | credits_completed / credits_attempted |
| `completion_threshold` | TEXT | Institution's minimum (typically '0.67') |
| `completion_meets_standard` | INTEGER | 1 = passes quantitative pace |
| `max_timeframe_credits` | TEXT | program_credits × 1.5 |
| `projected_credits_remaining` | TEXT | Credits still needed to graduate |
| `max_timeframe_met` | INTEGER | 1 = within max timeframe |
| `transfer_credits_attempted` | TEXT | From NSLDS |
| `transfer_credits_completed` | TEXT | From NSLDS |
| `sap_status` | TEXT | CHECK(IN ('SAT','FAW','FSP','FAP')) |
| `prior_sap_status` | TEXT | Status from prior evaluation |
| `holds_placed` | INTEGER | 1 = disbursement hold placed on next term |
| `evaluated_by` | TEXT | Staff user ID (or 'system') |
| `notes` | TEXT | |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(student_id, academic_term_id)` UNIQUE
- `(company_id, sap_status)` — for batch reporting
- `(academic_term_id, sap_status)` — for term-level SAP run

---

### 3.11 `finaid_sap_appeal`

Student appeal of SAP suspension.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `sap_evaluation_id` | TEXT FK | finaid_sap_evaluation |
| `student_id` | TEXT FK | educlaw_student |
| `submitted_date` | TEXT | |
| `appeal_reason` | TEXT | CHECK(IN ('death_family','illness','injury','other')) |
| `reason_narrative` | TEXT | Student's written explanation |
| `academic_plan` | TEXT | Student's plan to meet SAP |
| `supporting_documents` | TEXT | JSON array of document references |
| `status` | TEXT | CHECK(IN ('submitted','under_review','granted','denied')) |
| `reviewed_by` | TEXT | FAO staff |
| `reviewed_date` | TEXT | |
| `decision_rationale` | TEXT | FAO notes on decision |
| `probation_term_id` | TEXT FK | educlaw_academic_term (if granted: probation term) |
| `probation_conditions` | TEXT | What student must achieve on probation |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(student_id, status)`
- `(sap_evaluation_id)`
- `(company_id, status)`

---

### 3.12 `finaid_r2t4_calculation`

R2T4 withdrawal refund calculation. One record per withdrawal event.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK | educlaw_student |
| `academic_term_id` | TEXT FK | educlaw_academic_term |
| `withdrawal_type` | TEXT | CHECK(IN ('official','unofficial')) |
| `withdrawal_date` | TEXT | Official drop or institutional determination date |
| `last_date_of_attendance` | TEXT | Last documented academic activity |
| `determination_date` | TEXT | Date institution determined withdrawal (starts 45-day clock) |
| `payment_period_start` | TEXT | Term start date |
| `payment_period_end` | TEXT | Term end date |
| `payment_period_days` | INTEGER | Total days (excluding scheduled breaks ≥5 days) |
| `days_attended` | INTEGER | LDA − start date |
| `percent_completed` | TEXT | days_attended / payment_period_days |
| `earned_percent` | TEXT | If > 60%: 100%; else: percent_completed |
| `total_aid_disbursed` | TEXT | Pell + FSEOG + Loans disbursed |
| `total_aid_scheduleable` | TEXT | Aid that could have been disbursed |
| `earned_aid` | TEXT | earned_percent × total_aid |
| `unearned_aid` | TEXT | total_aid_disbursed − earned_aid |
| `institution_return_amount` | TEXT | Institution's responsibility |
| `student_return_amount` | TEXT | Student's responsibility |
| `post_withdrawal_disbursement` | TEXT | Amount owed to student if earned > disbursed |
| `pwd_offered_date` | TEXT | Date post-withdrawal disbursement offered |
| `pwd_accepted` | INTEGER | Student accepted PWD |
| `pwd_disbursed_date` | TEXT | |
| `institution_return_due_date` | TEXT | determination_date + 45 days |
| `institution_return_date` | TEXT | Actual date funds returned |
| `return_detail` | TEXT | JSON: amount returned per aid type in return order |
| `status` | TEXT | CHECK(IN ('calculated','approved','returned','complete')) |
| `calculated_by` | TEXT | Staff user ID |
| `approved_by` | TEXT | |
| `notes` | TEXT | |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(student_id, academic_term_id)` UNIQUE
- `(company_id, status)`
- `(company_id, institution_return_due_date)` — compliance deadline tracking

---

### 3.13 `finaid_loan`

Federal student loan record (one per loan origination).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK | educlaw_student |
| `award_id` | TEXT FK | finaid_award |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `loan_type` | TEXT | CHECK(IN ('subsidized','unsubsidized','graduate_plus','parent_plus','teach')) |
| `loan_period_start` | TEXT | Payment period start |
| `loan_period_end` | TEXT | Payment period end |
| `loan_amount` | TEXT | Total loan origination amount |
| `first_disbursement_amount` | TEXT | |
| `second_disbursement_amount` | TEXT | |
| `origination_fee` | TEXT | Loan origination fee (%) |
| `interest_rate` | TEXT | Current year rate |
| `cod_loan_id` | TEXT | COD-assigned loan ID (unique to COD system) |
| `cod_origination_status` | TEXT | CHECK(IN ('pending','accepted','rejected','')) |
| `cod_origination_date` | TEXT | |
| `mpn_required` | INTEGER | 1 = MPN must be signed |
| `mpn_signed` | INTEGER | 1 = MPN signed at StudentAid.gov |
| `mpn_signed_date` | TEXT | |
| `entrance_counseling_required` | INTEGER | 1 = first-time borrower |
| `entrance_counseling_complete` | INTEGER | |
| `entrance_counseling_date` | TEXT | |
| `exit_counseling_required` | INTEGER | 1 = on withdrawal/graduation |
| `exit_counseling_complete` | INTEGER | |
| `exit_counseling_date` | TEXT | |
| `borrower_id` | TEXT | For parent PLUS: guardian_id; else: student_id |
| `borrower_type` | TEXT | CHECK(IN ('student','parent')) |
| `status` | TEXT | CHECK(IN ('originated','active','repayment','deferred','defaulted','paid_off')) |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(student_id, aid_year_id, loan_type)`
- `(company_id, cod_origination_status)` — COD reconciliation
- `(company_id, mpn_signed, entrance_counseling_complete)` — holds dashboard

---

### 3.14 `finaid_scholarship_program`

Institutional scholarship program definition (replaces simple `educlaw_scholarship`).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | Scholarship name |
| `code` | TEXT | Short code |
| `description` | TEXT | |
| `scholarship_type` | TEXT | CHECK(IN ('merit','need_based','merit_need','athletic','departmental','endowed','external','tuition_waiver')) |
| `funding_source` | TEXT | CHECK(IN ('endowment','budget','departmental','donor','external')) |
| `award_method` | TEXT | CHECK(IN ('auto_match','application_required','fao_discretion')) |
| `award_amount_type` | TEXT | CHECK(IN ('fixed','percentage_coa','percentage_tuition','variable')) |
| `award_amount` | TEXT | Fixed amount (or percentage) |
| `min_award` | TEXT | For variable awards |
| `max_award` | TEXT | For variable awards |
| `annual_budget` | TEXT | Total institutional allocation |
| `budget_remaining` | TEXT | Running available balance |
| `max_recipients` | INTEGER | 0 = unlimited |
| `renewal_eligible` | INTEGER | 1 = can be renewed |
| `renewal_gpa_minimum` | TEXT | GPA to renew |
| `renewal_credits_minimum` | TEXT | Credits per term to renew |
| `eligibility_criteria` | TEXT | JSON: {gpa_min, program_types, year_levels, need_threshold, enrollment_min, etc.} |
| `application_deadline` | TEXT | For application-based scholarships |
| `award_period` | TEXT | CHECK(IN ('annual','per_term','one_time')) |
| `applies_to_aid_type` | TEXT | Where counted in package (institutional_grant / institutional_scholarship) |
| `gl_account_id` | TEXT FK | account (expense GL account) |
| `is_active` | INTEGER | |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(company_id, scholarship_type, is_active)`
- `(company_id, code)` UNIQUE

---

### 3.15 `finaid_scholarship_application`

Student application for application-based scholarships.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `scholarship_program_id` | TEXT FK | finaid_scholarship_program |
| `student_id` | TEXT FK | educlaw_student |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `submission_date` | TEXT | |
| `status` | TEXT | CHECK(IN ('draft','submitted','under_review','awarded','waitlisted','denied','withdrawn')) |
| `essay_response` | TEXT | If scholarship requires essay |
| `gpa_at_application` | TEXT | Snapshot of GPA at time of application |
| `reviewer_id` | TEXT | Staff user ID |
| `review_date` | TEXT | |
| `review_notes` | TEXT | |
| `award_amount` | TEXT | If awarded (may differ from standard amount) |
| `award_term_id` | TEXT FK | educlaw_academic_term (first term of award) |
| `denial_reason` | TEXT | |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(scholarship_program_id, student_id, aid_year_id)` UNIQUE
- `(company_id, status)`
- `(student_id, status)`

---

### 3.16 `finaid_scholarship_renewal`

Tracks term-by-term renewal evaluation for multi-term scholarships.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `scholarship_application_id` | TEXT FK | finaid_scholarship_application |
| `student_id` | TEXT FK | educlaw_student |
| `scholarship_program_id` | TEXT FK | finaid_scholarship_program |
| `academic_term_id` | TEXT FK | educlaw_academic_term |
| `renewal_status` | TEXT | CHECK(IN ('renewed','suspended','revoked','exhausted')) |
| `gpa_at_evaluation` | TEXT | GPA when evaluated |
| `credits_attempted` | INTEGER | |
| `meets_criteria` | INTEGER | 1 = all criteria met |
| `reason` | TEXT | If suspended or revoked |
| `evaluated_by` | TEXT | |
| `evaluation_date` | TEXT | |
| `company_id` | TEXT FK | company |

---

### 3.17 `finaid_work_study_job`

FWS job postings.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `job_title` | TEXT | |
| `department_id` | TEXT | FK to department (erpclaw-setup) |
| `supervisor_id` | TEXT | FK to employee (erpclaw-hr) |
| `job_type` | TEXT | CHECK(IN ('on_campus','off_campus_community','off_campus_other')) |
| `description` | TEXT | |
| `pay_rate` | TEXT | Hourly rate |
| `hours_per_week` | TEXT | Expected hours |
| `total_positions` | INTEGER | How many students can be placed |
| `filled_positions` | INTEGER | Running count |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `status` | TEXT | CHECK(IN ('open','filled','closed')) |
| `company_id` | TEXT FK | company |

---

### 3.18 `finaid_work_study_assignment`

Student assigned to FWS job.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK | educlaw_student |
| `award_id` | TEXT FK | finaid_award (the FWS award in their package) |
| `job_id` | TEXT FK | finaid_work_study_job |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `academic_term_id` | TEXT FK | educlaw_academic_term |
| `start_date` | TEXT | |
| `end_date` | TEXT | |
| `award_limit` | TEXT | Maximum earnings (= FWS award amount) |
| `earned_to_date` | TEXT | Running total |
| `status` | TEXT | CHECK(IN ('active','completed','terminated')) |
| `company_id` | TEXT FK | company |

---

### 3.19 `finaid_work_study_timesheet`

Hours worked per pay period.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `assignment_id` | TEXT FK | finaid_work_study_assignment |
| `student_id` | TEXT FK | educlaw_student |
| `pay_period_start` | TEXT | |
| `pay_period_end` | TEXT | |
| `hours_worked` | TEXT | Decimal hours |
| `earnings` | TEXT | hours × pay_rate |
| `cumulative_earnings` | TEXT | Running total for assignment |
| `submission_date` | TEXT | When student submitted |
| `supervisor_approval_status` | TEXT | CHECK(IN ('pending','approved','rejected')) |
| `supervisor_approved_by` | TEXT | employee_id |
| `supervisor_approved_date` | TEXT | |
| `payroll_exported` | INTEGER | 1 = sent to payroll |
| `payroll_export_date` | TEXT | |
| `company_id` | TEXT FK | company |

**Key Indexes:**
- `(assignment_id, pay_period_start)` UNIQUE
- `(student_id, pay_period_start)`
- `(company_id, supervisor_approval_status)` — approval queue

---

### 3.20 `finaid_professional_judgment`

Documentation of Professional Judgment decisions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `student_id` | TEXT FK | educlaw_student |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `award_package_id` | TEXT FK | finaid_award_package (nullable) |
| `pj_type` | TEXT | CHECK(IN ('sai_adjustment','coa_adjustment','dependency_override','enrollment_status_override','other')) |
| `pj_reason` | TEXT | CHECK(IN ('job_loss','death_family','illness_injury','divorce_separation','unusual_expenses','other')) |
| `reason_narrative` | TEXT | Required written explanation |
| `data_element_changed` | TEXT | What was changed (e.g., 'SAI', 'COA.housing') |
| `original_value` | TEXT | Value before PJ |
| `adjusted_value` | TEXT | Value after PJ |
| `effective_date` | TEXT | When change takes effect |
| `supporting_documentation` | TEXT | JSON array of document references |
| `authorized_by` | TEXT | FAA staff user ID |
| `authorization_date` | TEXT | |
| `supervisor_review_required` | INTEGER | 1 = large adjustment requiring second sign-off |
| `supervisor_reviewed_by` | TEXT | |
| `supervisor_review_date` | TEXT | |
| `company_id` | TEXT FK | company |
| `created_at` | TEXT | Immutable |
| `created_by` | TEXT | |

**Key Indexes:**
- `(student_id, aid_year_id, pj_type)`
- `(company_id, authorization_date)`

---

### 3.21 `finaid_fund_allocation`

Institutional allocation of campus-based federal funds (FSEOG, FWS) per aid year.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `fund_type` | TEXT | CHECK(IN ('fseog','fws','institutional_grant','departmental')) |
| `fund_name` | TEXT | |
| `total_allocation` | TEXT | Total available for year |
| `committed_amount` | TEXT | Awarded (in packages) |
| `disbursed_amount` | TEXT | Actually disbursed |
| `available_amount` | TEXT | Calculated: total − committed |
| `company_id` | TEXT FK | company |

**Key Indexes:** `(aid_year_id, fund_type)` UNIQUE, `(company_id, aid_year_id)`

---

### 3.22 `finaid_pell_schedule`

Pell Grant payment schedule per aid year (lookup table).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `aid_year_id` | TEXT FK | finaid_aid_year |
| `pell_index` | INTEGER | 0–6000 (SAI-based index) |
| `full_time_annual` | TEXT | Award for full-time, full-year |
| `three_quarter_time` | TEXT | 75% of full-time |
| `half_time` | TEXT | 50% of full-time |
| `less_than_half_time` | TEXT | 25% of full-time |

**Key Indexes:** `(aid_year_id, pell_index)` UNIQUE

---

## 4. Key Entity Relationships Summary

```
finaid_isir
  → student_id (educlaw_student)
  → aid_year_id (finaid_aid_year)
  → has many finaid_isir_cflag
  → has one finaid_verification_request
  → has many finaid_award_package

finaid_award_package
  → student_id
  → aid_year_id
  → academic_term_id (educlaw_academic_term)
  → program_enrollment_id (educlaw_program_enrollment)
  → isir_id (finaid_isir)
  → cost_of_attendance_id (finaid_cost_of_attendance)
  → has many finaid_award
  → has many finaid_professional_judgment

finaid_award
  → award_package_id
  → has many finaid_disbursement

finaid_sap_evaluation
  → student_id
  → academic_term_id
  → has many finaid_sap_appeal

finaid_r2t4_calculation
  → student_id
  → academic_term_id

finaid_loan
  → student_id
  → award_id (finaid_award)
  → has many finaid_loan_requirement (MPN, counseling)
```

---

## 5. Status Lifecycles

### Award Package Status
```
draft → offered → accepted → disbursed
              ↓         ↓
           cancelled  partially_accepted
```

### SAP Status
```
(no status) → SAT → FAW → FSP → FAP → SAT
                              ↑ (appeal granted)
                          (max timeframe) → FSP directly
```

### ISIR Status
```
received → under_review → reviewed → packaged → archived
```

### Verification Status
```
initiated → documents_requested → in_review → complete
                                          ↓
                                     discrepancy → (iterate)
```

### R2T4 Status
```
calculated → approved → returned → complete
```

### Loan Status
```
originated → active → repayment → paid_off
                    → deferred
                    → defaulted
```

---

## 6. Data Not Stored (Read from Parent)

The following data is **read from educlaw (parent)** and never duplicated in finaid:

| Data | Source Table |
|------|-------------|
| Student name, DOB, email, SSN | `educlaw_student` |
| Cumulative GPA | `educlaw_student.cumulative_gpa` |
| Credits earned | `educlaw_student.total_credits_earned` |
| Enrollment status | `educlaw_course_enrollment` |
| Drop dates / last day | `educlaw_course_enrollment.drop_date` |
| Term dates | `educlaw_academic_term` |
| Program credit requirements | `educlaw_program.total_credits_required` |
| Tuition charges | erpclaw-selling sales invoices |
| Guardian relationships | `educlaw_student_guardian` / `educlaw_guardian` |
| Academic standing | `educlaw_student.academic_standing` |

---

## 7. Recommended Index Strategy

### Critical Performance Indexes
| Query Pattern | Index |
|--------------|-------|
| Find active ISIR for student + aid year | `(student_id, aid_year_id, is_active_transaction)` |
| Find packages by term | `(academic_term_id, status)` |
| Find awards needing disbursement | `(company_id, acceptance_status, disbursement_holds)` |
| Find students in SAP FSP | `(company_id, sap_status, academic_term_id)` |
| Find R2T4s past due date | `(company_id, institution_return_due_date, status)` |
| Find unresolved C-flags | `(student_id, resolution_status)` |
| Find pending timesheet approvals | `(company_id, supervisor_approval_status)` |
| Monthly COD reconciliation | `(company_id, cod_status, disbursement_date)` |
