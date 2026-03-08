# EduClaw Financial Aid — Implementation Plan

**Product:** educlaw-finaid
**Version:** 1.0.0
**Parent:** educlaw (v1.0.0)
**Plan Date:** 2026-03-05
**Planner:** ERPForge Planner Agent

---

## 1. Product Overview

### Description
EduClaw Financial Aid (`educlaw-finaid`) is a sub-vertical of educlaw that adds Title IV–compliant federal, state, and institutional financial aid management to the EduClaw Student Information System. It is the first open-source, AI-native financial aid module for a full SIS — targeting small-to-mid-size institutions (500–20K students) that need Title IV compliance without enterprise pricing.

### Target Domains

| Domain | Scope |
|--------|-------|
| `financial_aid` | Core compliance engine: ISIR/FAFSA processing, COA setup, aid packaging, disbursement, SAP evaluation, R2T4 calculations, professional judgment |
| `scholarships` | Institutional scholarship program definitions, student applications, awards, and renewal tracking |
| `work_study` | Federal Work-Study job postings, student assignments, timesheet management, payroll export |
| `loan_tracking` | Federal student loan origination records, MPN/counseling compliance, aggregate limit tracking, COD export |

### Foundation Dependencies

| Skill | Role |
|-------|------|
| `erpclaw-setup` | Company, user, and permission management; `company` table; `erp_user` table |
| `erpclaw-gl` | GL accounts, journal entries for disbursements and R2T4 returns |
| `erpclaw-selling` | Student-as-customer model, sales invoices for tuition charges, credit balance application |
| `erpclaw-payments` | Credit balance refunds to students |
| `erpclaw-hr` | Staff records (FAO counselors), FWS supervisor reference |

### Parent (educlaw) Dependency

educlaw-finaid is built on top of `educlaw` v1.0.0. It reads student, enrollment, grade, and calendar data directly from parent tables — never copies or shadows this data. All finaid records carry FK references to parent tables.

---

## 2. Domain Organization

| Domain | Module File | Scope |
|--------|-------------|-------|
| `financial_aid` | `financial_aid.py` | Aid year setup, COA, fund allocations, Pell schedule, ISIR import and review, C-flag resolution, verification workflow, award packaging, award acceptance, disbursement, COD export, SAP evaluation engine, SAP appeals, R2T4 calculations, professional judgment |
| `scholarships` | `scholarships.py` | Institutional scholarship program definitions, eligibility criteria, student applications, application review, award decisions, renewal tracking, auto-match engine |
| `work_study` | `work_study.py` | FWS job postings, student assignments, timesheet entry and approval, payroll export, earnings tracking vs. award limits |
| `loan_tracking` | `loan_tracking.py` | Federal loan origination records, loan type and period tracking, MPN status, entrance/exit counseling, annual/aggregate limit enforcement, COD origination data |

---

## 3. Database Schema

### Naming Conventions (Inherited from educlaw/ERPClaw)
- Table prefix: `finaid_`
- IDs: `TEXT PRIMARY KEY` (UUID4)
- Money: `TEXT NOT NULL DEFAULT '0'` (Python Decimal — never float)
- Dates: `TEXT NOT NULL DEFAULT ''` (ISO 8601 YYYY-MM-DD)
- Timestamps: `TEXT NOT NULL DEFAULT (datetime('now'))` (ISO 8601)
- Status: `TEXT NOT NULL DEFAULT 'X' CHECK(status IN (...))`
- Booleans: `INTEGER NOT NULL DEFAULT 0`
- Free text: `TEXT NOT NULL DEFAULT ''`
- JSON fields: `TEXT NOT NULL DEFAULT '[]'` or `TEXT NOT NULL DEFAULT '{}'`
- All FKs: `ON DELETE RESTRICT`
- All tables: `created_at`, `updated_at`, `created_by` (except append-only tables)
- Append-only tables (no `updated_at`): `finaid_disbursement`, `finaid_professional_judgment`

---

### 3.1 Tables (New — 22 Tables)

---

#### Table: `finaid_aid_year`

Master configuration for each federal award year (July 1–June 30).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `aid_year_code` | TEXT | NOT NULL DEFAULT '' | e.g., '2526' for 2025-26 |
| `description` | TEXT | NOT NULL DEFAULT '' | e.g., 'Aid Year 2025-2026' |
| `start_date` | TEXT | NOT NULL DEFAULT '' | Always July 1 (e.g., 2025-07-01) |
| `end_date` | TEXT | NOT NULL DEFAULT '' | Always June 30 (e.g., 2026-06-30) |
| `pell_max_award` | TEXT | NOT NULL DEFAULT '0' | Maximum scheduled Pell award (e.g., '7395.00') |
| `is_active` | INTEGER | NOT NULL DEFAULT 0 | 1 = currently open for packaging |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (company_id, aid_year_code)` — one record per year per institution
- `(company_id, is_active)` — find active aid year quickly

---

#### Table: `finaid_pell_schedule`

Pell Grant payment schedule for a given aid year and SAI index. Seed/lookup data; imported at aid year setup.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `pell_index` | INTEGER | NOT NULL DEFAULT 0 | 0–6206 (SAI-derived index) |
| `full_time_annual` | TEXT | NOT NULL DEFAULT '0' | Award for full-time, full-year enrollment |
| `three_quarter_time` | TEXT | NOT NULL DEFAULT '0' | 75% of full-time award |
| `half_time` | TEXT | NOT NULL DEFAULT '0' | 50% of full-time award |
| `less_than_half_time` | TEXT | NOT NULL DEFAULT '0' | 25% of full-time award |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (aid_year_id, pell_index)` — one schedule entry per index per year

---

#### Table: `finaid_fund_allocation`

Institutional allocation of campus-based federal funds (FSEOG, FWS) and institutional grant pools per aid year.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `fund_type` | TEXT | NOT NULL DEFAULT '' CHECK(fund_type IN ('fseog','fws','institutional_grant','departmental')) | |
| `fund_name` | TEXT | NOT NULL DEFAULT '' | Descriptive name for this allocation |
| `total_allocation` | TEXT | NOT NULL DEFAULT '0' | Total funds available for the year |
| `committed_amount` | TEXT | NOT NULL DEFAULT '0' | Amount packaged in award offers |
| `disbursed_amount` | TEXT | NOT NULL DEFAULT '0' | Amount actually disbursed |
| `available_amount` | TEXT | NOT NULL DEFAULT '0' | Calculated: total_allocation − committed_amount |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (aid_year_id, fund_type, fund_name)` — one allocation per fund type per year
- `(company_id, aid_year_id)` — all allocations for a year

---

#### Table: `finaid_cost_of_attendance`

Budget components for Cost of Attendance (COA) per program, enrollment status, living arrangement, and aid year.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `program_id` | TEXT | REFERENCES educlaw_program(id) ON DELETE RESTRICT | Nullable — can be institution-wide default |
| `enrollment_status` | TEXT | NOT NULL DEFAULT '' CHECK(enrollment_status IN ('full_time','three_quarter','half_time','less_than_half')) | |
| `living_arrangement` | TEXT | NOT NULL DEFAULT '' CHECK(living_arrangement IN ('on_campus','off_campus','with_parent','')) | |
| `tuition_fees` | TEXT | NOT NULL DEFAULT '0' | Annual tuition and mandatory fees |
| `books_supplies` | TEXT | NOT NULL DEFAULT '0' | Estimated books and supplies |
| `room_board` | TEXT | NOT NULL DEFAULT '0' | Housing and meal costs |
| `transportation` | TEXT | NOT NULL DEFAULT '0' | Local transportation estimate |
| `personal_expenses` | TEXT | NOT NULL DEFAULT '0' | Personal/miscellaneous allowance |
| `loan_fees` | TEXT | NOT NULL DEFAULT '0' | Average loan origination fees |
| `total_coa` | TEXT | NOT NULL DEFAULT '0' | Sum of all components (calculated on save) |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (aid_year_id, program_id, enrollment_status, living_arrangement)` — prevent duplicate COA rows
- `(company_id, aid_year_id)` — all COA records for a year

---

#### Table: `finaid_isir`

ISIR (Institutional Student Information Record — FAFSA output) per student per aid year. Multiple transactions per student are stored; only one is marked active.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `transaction_number` | INTEGER | NOT NULL DEFAULT 1 | 01 = original; 02+ = corrections |
| `is_active_transaction` | INTEGER | NOT NULL DEFAULT 0 | 1 = this transaction used for packaging |
| `fafsa_submission_id` | TEXT | NOT NULL DEFAULT '' | FAFSA tracking ID from FSA |
| `receipt_date` | TEXT | NOT NULL DEFAULT '' | Date ISIR received by institution |
| `sai` | TEXT | NOT NULL DEFAULT '0' | Student Aid Index (formerly EFC); can be negative |
| `sai_is_negative` | INTEGER | NOT NULL DEFAULT 0 | 1 = SAI is negative (extreme need) |
| `dependency_status` | TEXT | NOT NULL DEFAULT '' CHECK(dependency_status IN ('dependent','independent','')) | |
| `dependency_override` | INTEGER | NOT NULL DEFAULT 0 | 1 = FAA overrode dependency status via PJ |
| `pell_index` | TEXT | NOT NULL DEFAULT '' | Pell eligibility index from ISIR |
| `pell_scheduled_award` | TEXT | NOT NULL DEFAULT '0' | Calculated full-time full-year Pell award |
| `pell_lifetime_eligibility_used` | TEXT | NOT NULL DEFAULT '0' | LEU percentage (max 600.000) |
| `verification_flag` | INTEGER | NOT NULL DEFAULT 0 | 1 = selected for verification by FPS |
| `verification_group` | TEXT | NOT NULL DEFAULT '' CHECK(verification_group IN ('V1','V4','V5','')) | |
| `has_unresolved_cflags` | INTEGER | NOT NULL DEFAULT 0 | Cached flag; recalculate from finaid_isir_cflag |
| `nslds_default_flag` | INTEGER | NOT NULL DEFAULT 0 | 1 = NSLDS loan default match |
| `nslds_overpayment_flag` | INTEGER | NOT NULL DEFAULT 0 | 1 = NSLDS grant overpayment match |
| `selective_service_flag` | INTEGER | NOT NULL DEFAULT 0 | 1 = Selective Service match issue |
| `citizenship_flag` | INTEGER | NOT NULL DEFAULT 0 | 1 = citizenship/SSN match issue |
| `agi` | TEXT | NOT NULL DEFAULT '0' | Adjusted Gross Income from FAFSA |
| `household_size` | INTEGER | NOT NULL DEFAULT 0 | Family/household size |
| `family_members_in_college` | INTEGER | NOT NULL DEFAULT 0 | Number of family members in college |
| `aggregate_loan_borrowed` | TEXT | NOT NULL DEFAULT '0' | Total federal loans from NSLDS history |
| `aggregate_sub_loan_borrowed` | TEXT | NOT NULL DEFAULT '0' | Total subsidized loans from NSLDS |
| `status` | TEXT | NOT NULL DEFAULT 'received' CHECK(status IN ('received','under_review','reviewed','packaged','archived')) | |
| `reviewed_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID who reviewed |
| `reviewed_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of review completion |
| `raw_isir_data` | TEXT | NOT NULL DEFAULT '{}' | Full ISIR JSON for audit archive |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (student_id, aid_year_id, transaction_number)` — one transaction per number
- `(student_id, aid_year_id, is_active_transaction)` — find active ISIR for packaging
- `(company_id, status)` — FAO review queue

---

#### Table: `finaid_isir_cflag`

Individual C-flag (caution flag) records per ISIR. One row per distinct C-flag per ISIR.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `isir_id` | TEXT | NOT NULL REFERENCES finaid_isir(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | Denormalized for query performance |
| `cflag_code` | TEXT | NOT NULL DEFAULT '' | e.g., 'C25', 'C01', 'C07', 'C09', 'C28' |
| `cflag_description` | TEXT | NOT NULL DEFAULT '' | Human-readable description of the flag |
| `blocks_disbursement` | INTEGER | NOT NULL DEFAULT 1 | 1 = cannot disburse until this flag is resolved |
| `resolution_status` | TEXT | NOT NULL DEFAULT 'pending' CHECK(resolution_status IN ('pending','resolved','waived')) | |
| `resolution_date` | TEXT | NOT NULL DEFAULT '' | Date resolved or waived |
| `resolved_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID |
| `resolution_notes` | TEXT | NOT NULL DEFAULT '' | Documentation of resolution |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (isir_id, cflag_code)` — one record per flag per ISIR
- `(student_id, resolution_status)` — find students with pending flags
- `(company_id, resolution_status)` — FAO resolution queue

---

#### Table: `finaid_verification_request`

Tracks the FAFSA verification process for a flagged ISIR.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `isir_id` | TEXT | NOT NULL REFERENCES finaid_isir(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `verification_group` | TEXT | NOT NULL DEFAULT '' CHECK(verification_group IN ('V1','V4','V5')) | |
| `status` | TEXT | NOT NULL DEFAULT 'initiated' CHECK(status IN ('initiated','documents_requested','in_review','discrepancy','complete','withdrawn')) | |
| `requested_date` | TEXT | NOT NULL DEFAULT '' | Date student was notified |
| `deadline_date` | TEXT | NOT NULL DEFAULT '' | Document submission deadline |
| `completed_date` | TEXT | NOT NULL DEFAULT '' | Date verification concluded |
| `discrepancy_found` | INTEGER | NOT NULL DEFAULT 0 | 1 = FAFSA data needed correction |
| `discrepancy_notes` | TEXT | NOT NULL DEFAULT '' | What was discrepant and how resolved |
| `assigned_to` | TEXT | NOT NULL DEFAULT '' | FAO staff user ID responsible |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (isir_id)` — one verification request per ISIR
- `(student_id, status)` — student verification status
- `(company_id, status)` — FAO verification queue

---

#### Table: `finaid_verification_document`

Individual document items required and collected per verification request. One row per required document type.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `verification_request_id` | TEXT | NOT NULL REFERENCES finaid_verification_request(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `document_type` | TEXT | NOT NULL DEFAULT '' CHECK(document_type IN ('tax_transcript','w2','household_verification','identity','statement_of_purpose','snap_verification','child_support','hs_completion','other')) | |
| `document_description` | TEXT | NOT NULL DEFAULT '' | Human-readable description for student |
| `is_required` | INTEGER | NOT NULL DEFAULT 1 | 1 = required for this verification group |
| `submission_status` | TEXT | NOT NULL DEFAULT 'not_submitted' CHECK(submission_status IN ('not_submitted','submitted','accepted','rejected','waived')) | |
| `submitted_date` | TEXT | NOT NULL DEFAULT '' | |
| `reviewed_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID |
| `reviewed_date` | TEXT | NOT NULL DEFAULT '' | |
| `rejection_reason` | TEXT | NOT NULL DEFAULT '' | If rejected |
| `document_reference` | TEXT | NOT NULL DEFAULT '' | File path or document management ID |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (verification_request_id, document_type)` — one record per doc type per request
- `(student_id, submission_status)` — student document dashboard
- `(company_id, submission_status)` — FAO document review queue

---

#### Table: `finaid_award_package`

The complete financial aid offer for one student for one term within one aid year.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `naming_series` | TEXT | NOT NULL DEFAULT '' UNIQUE | e.g., AWD-2526-00001 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `academic_term_id` | TEXT | NOT NULL REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | |
| `program_enrollment_id` | TEXT | NOT NULL REFERENCES educlaw_program_enrollment(id) ON DELETE RESTRICT | Active program enrollment |
| `isir_id` | TEXT | NOT NULL REFERENCES finaid_isir(id) ON DELETE RESTRICT | ISIR transaction used for this package |
| `cost_of_attendance_id` | TEXT | NOT NULL REFERENCES finaid_cost_of_attendance(id) ON DELETE RESTRICT | COA budget used |
| `enrollment_status` | TEXT | NOT NULL DEFAULT '' CHECK(enrollment_status IN ('full_time','three_quarter','half_time','less_than_half')) | Enrollment intensity at packaging |
| `financial_need` | TEXT | NOT NULL DEFAULT '0' | COA − SAI (calculated) |
| `total_grants` | TEXT | NOT NULL DEFAULT '0' | Sum of all grant awards in package |
| `total_loans` | TEXT | NOT NULL DEFAULT '0' | Sum of all offered loan awards |
| `total_work_study` | TEXT | NOT NULL DEFAULT '0' | FWS award amount |
| `total_aid` | TEXT | NOT NULL DEFAULT '0' | Grand total of all aid types |
| `status` | TEXT | NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','offered','accepted','partially_accepted','cancelled','disbursed')) | |
| `offered_date` | TEXT | NOT NULL DEFAULT '' | Date award letter was sent |
| `accepted_date` | TEXT | NOT NULL DEFAULT '' | Date student accepted |
| `acceptance_deadline` | TEXT | NOT NULL DEFAULT '' | Deadline for student response |
| `packaged_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID |
| `packaged_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of packaging |
| `approved_by` | TEXT | NOT NULL DEFAULT '' | FAO approver user ID |
| `approved_at` | TEXT | NOT NULL DEFAULT '' | Timestamp of approval |
| `notes` | TEXT | NOT NULL DEFAULT '' | Internal FAO notes |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (student_id, aid_year_id, academic_term_id)` — one package per student per term per year
- `(company_id, status)` — FAO package management queue
- `(aid_year_id, status)` — year-level reporting

---

#### Table: `finaid_award`

Individual award line item within an award package. One row per aid type per package.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `award_package_id` | TEXT | NOT NULL REFERENCES finaid_award_package(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | Denormalized |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | Denormalized |
| `academic_term_id` | TEXT | NOT NULL REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | Denormalized |
| `aid_type` | TEXT | NOT NULL DEFAULT '' CHECK(aid_type IN ('pell','fseog','subsidized_loan','unsubsidized_loan','plus_loan','parent_plus_loan','fws','institutional_grant','institutional_scholarship','state_grant','external_scholarship','tuition_waiver','teach_grant')) | |
| `aid_source` | TEXT | NOT NULL DEFAULT '' CHECK(aid_source IN ('federal','state','institutional','external')) | |
| `fund_source_id` | TEXT | NOT NULL DEFAULT '' | FK to finaid_scholarship_program.id or finaid_fund_allocation.id (nullable logical FK) |
| `offered_amount` | TEXT | NOT NULL DEFAULT '0' | Amount offered to student |
| `accepted_amount` | TEXT | NOT NULL DEFAULT '0' | Amount student accepted (may be less than offered) |
| `disbursed_amount` | TEXT | NOT NULL DEFAULT '0' | Running total of disbursements posted |
| `acceptance_status` | TEXT | NOT NULL DEFAULT 'pending' CHECK(acceptance_status IN ('pending','accepted','declined','partial')) | |
| `acceptance_date` | TEXT | NOT NULL DEFAULT '' | |
| `disbursement_holds` | TEXT | NOT NULL DEFAULT '[]' | JSON array of hold reason codes blocking disbursement |
| `is_locked` | INTEGER | NOT NULL DEFAULT 0 | 1 = cannot modify after first disbursement |
| `gl_account_id` | TEXT | NOT NULL DEFAULT '' | FK to account (financial aid expense GL account) |
| `notes` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (award_package_id, aid_type)` — one award per type per package
- `(student_id, aid_year_id, aid_type)` — student aid history
- `(company_id, aid_type, acceptance_status)` — allocation tracking and reporting

---

#### Table: `finaid_disbursement`

Actual funds applied to student account. **Append-only — no `updated_at`**. Reversals create new records with `disbursement_type='reversal'`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `award_id` | TEXT | NOT NULL REFERENCES finaid_award(id) ON DELETE RESTRICT | |
| `award_package_id` | TEXT | NOT NULL REFERENCES finaid_award_package(id) ON DELETE RESTRICT | Denormalized |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | Denormalized |
| `disbursement_type` | TEXT | NOT NULL DEFAULT 'disbursement' CHECK(disbursement_type IN ('disbursement','reversal','return','post_withdrawal')) | |
| `disbursement_number` | INTEGER | NOT NULL DEFAULT 1 | 1 = first disbursement, 2 = second, etc. |
| `amount` | TEXT | NOT NULL DEFAULT '0' | Positive = credit to student; reversals use same sign, type indicates direction |
| `disbursement_date` | TEXT | NOT NULL DEFAULT '' | Date posted to student account |
| `gl_journal_id` | TEXT | NOT NULL DEFAULT '' | FK to GL journal entry |
| `sales_invoice_id` | TEXT | NOT NULL DEFAULT '' | FK to erpclaw-selling invoice where credit applied |
| `cod_origination_id` | TEXT | NOT NULL DEFAULT '' | COD Origination ID (Pell and Direct Loans) |
| `cod_disbursement_id` | TEXT | NOT NULL DEFAULT '' | COD Disbursement ID |
| `cod_status` | TEXT | NOT NULL DEFAULT '' CHECK(cod_status IN ('pending','reported','acknowledged','rejected','')) | |
| `cod_response_date` | TEXT | NOT NULL DEFAULT '' | When COD acknowledged |
| `is_credit_balance` | INTEGER | NOT NULL DEFAULT 0 | 1 = aid exceeds charges; refund needed within 14 days |
| `credit_balance_amount` | TEXT | NOT NULL DEFAULT '0' | Refund amount owed to student |
| `credit_balance_date` | TEXT | NOT NULL DEFAULT '' | Date credit balance identified |
| `credit_balance_returned_date` | TEXT | NOT NULL DEFAULT '' | Date refund issued (must be within 14 days) |
| `disbursed_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | Immutable — no updated_at |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(award_id, disbursement_number, disbursement_type)` — disbursement history per award
- `(student_id, disbursement_date)` — student disbursement timeline
- `(company_id, cod_status)` — COD reconciliation queue
- `(company_id, is_credit_balance, credit_balance_returned_date)` — 14-day credit balance compliance

---

#### Table: `finaid_sap_evaluation`

SAP (Satisfactory Academic Progress) evaluation result per student per academic term.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `academic_term_id` | TEXT | NOT NULL REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `evaluation_date` | TEXT | NOT NULL DEFAULT '' | Date evaluation was run |
| `evaluation_type` | TEXT | NOT NULL DEFAULT 'automatic' CHECK(evaluation_type IN ('automatic','manual','appeal')) | |
| `gpa_earned` | TEXT | NOT NULL DEFAULT '0' | Cumulative GPA at evaluation |
| `gpa_threshold` | TEXT | NOT NULL DEFAULT '2.00' | Institution minimum (e.g., '2.00') |
| `gpa_meets_standard` | INTEGER | NOT NULL DEFAULT 0 | 1 = passes qualitative measure |
| `credits_attempted` | TEXT | NOT NULL DEFAULT '0' | Cumulative credits attempted (includes W/F/I) |
| `credits_completed` | TEXT | NOT NULL DEFAULT '0' | Cumulative credits completed (passing grades) |
| `completion_rate` | TEXT | NOT NULL DEFAULT '0' | credits_completed / credits_attempted |
| `completion_threshold` | TEXT | NOT NULL DEFAULT '0.67' | Institution minimum (e.g., '0.67') |
| `completion_meets_standard` | INTEGER | NOT NULL DEFAULT 0 | 1 = passes quantitative pace measure |
| `max_timeframe_credits` | TEXT | NOT NULL DEFAULT '0' | Program required credits × 1.5 |
| `projected_credits_remaining` | TEXT | NOT NULL DEFAULT '0' | Credits still needed to graduate |
| `max_timeframe_met` | INTEGER | NOT NULL DEFAULT 0 | 1 = within maximum timeframe |
| `transfer_credits_attempted` | TEXT | NOT NULL DEFAULT '0' | Transfer attempted credits from NSLDS |
| `transfer_credits_completed` | TEXT | NOT NULL DEFAULT '0' | Transfer completed credits from NSLDS |
| `sap_status` | TEXT | NOT NULL DEFAULT 'SAT' CHECK(sap_status IN ('SAT','FAW','FSP','FAP')) | SAP outcome status |
| `prior_sap_status` | TEXT | NOT NULL DEFAULT '' | Status from previous evaluation |
| `holds_placed` | INTEGER | NOT NULL DEFAULT 0 | 1 = disbursement hold placed on next term aid |
| `evaluated_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID or 'system' |
| `notes` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (student_id, academic_term_id)` — one evaluation per student per term
- `(company_id, sap_status)` — find suspended students
- `(academic_term_id, sap_status)` — term-level SAP report

---

#### Table: `finaid_sap_appeal`

Student appeal of SAP suspension (FSP status). One appeal per evaluation event.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `sap_evaluation_id` | TEXT | NOT NULL REFERENCES finaid_sap_evaluation(id) ON DELETE RESTRICT | The FSP evaluation being appealed |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `submitted_date` | TEXT | NOT NULL DEFAULT '' | |
| `appeal_reason` | TEXT | NOT NULL DEFAULT '' CHECK(appeal_reason IN ('death_family','illness','injury','divorce_separation','natural_disaster','other')) | |
| `reason_narrative` | TEXT | NOT NULL DEFAULT '' | Student's written explanation |
| `academic_plan` | TEXT | NOT NULL DEFAULT '' | Student's plan to achieve SAP |
| `supporting_documents` | TEXT | NOT NULL DEFAULT '[]' | JSON array of document references |
| `status` | TEXT | NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted','under_review','granted','denied')) | |
| `reviewed_by` | TEXT | NOT NULL DEFAULT '' | FAO staff user ID |
| `reviewed_date` | TEXT | NOT NULL DEFAULT '' | |
| `decision_rationale` | TEXT | NOT NULL DEFAULT '' | FAO notes explaining decision |
| `probation_term_id` | TEXT | REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | If granted: the probation term |
| `probation_conditions` | TEXT | NOT NULL DEFAULT '' | What student must achieve during probation |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(student_id, status)` — student appeal history
- `(sap_evaluation_id)` — link from evaluation
- `(company_id, status)` — FAO appeal review queue

---

#### Table: `finaid_r2t4_calculation`

Return of Title IV Funds calculation. One record per student per withdrawal event per term.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `academic_term_id` | TEXT | NOT NULL REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | |
| `award_package_id` | TEXT | NOT NULL REFERENCES finaid_award_package(id) ON DELETE RESTRICT | Package being returned |
| `withdrawal_type` | TEXT | NOT NULL DEFAULT '' CHECK(withdrawal_type IN ('official','unofficial')) | |
| `withdrawal_date` | TEXT | NOT NULL DEFAULT '' | Official drop date or institution-determined date |
| `last_date_of_attendance` | TEXT | NOT NULL DEFAULT '' | Last documented academically-related activity |
| `determination_date` | TEXT | NOT NULL DEFAULT '' | Date institution determined withdrawal (starts 45-day clock) |
| `payment_period_start` | TEXT | NOT NULL DEFAULT '' | Term start date |
| `payment_period_end` | TEXT | NOT NULL DEFAULT '' | Term end date |
| `payment_period_days` | INTEGER | NOT NULL DEFAULT 0 | Total days in period (excluding scheduled breaks ≥5 days) |
| `days_attended` | INTEGER | NOT NULL DEFAULT 0 | last_date_of_attendance − payment_period_start |
| `percent_completed` | TEXT | NOT NULL DEFAULT '0' | days_attended / payment_period_days |
| `earned_percent` | TEXT | NOT NULL DEFAULT '0' | If > 0.60: 1.0; else: percent_completed |
| `total_aid_disbursed` | TEXT | NOT NULL DEFAULT '0' | Pell + FSEOG + Loans disbursed (excludes FWS) |
| `total_aid_scheduleable` | TEXT | NOT NULL DEFAULT '0' | Aid eligible to be disbursed (could have been) |
| `earned_aid` | TEXT | NOT NULL DEFAULT '0' | earned_percent × total_aid (disbursed or scheduleable, whichever higher) |
| `unearned_aid` | TEXT | NOT NULL DEFAULT '0' | total_aid_disbursed − earned_aid |
| `institution_return_amount` | TEXT | NOT NULL DEFAULT '0' | Institution's share of unearned aid to return |
| `student_return_amount` | TEXT | NOT NULL DEFAULT '0' | Student's share of unearned aid |
| `post_withdrawal_disbursement` | TEXT | NOT NULL DEFAULT '0' | Amount owed to student if earned > disbursed |
| `pwd_offered_date` | TEXT | NOT NULL DEFAULT '' | Date PWD offer made to student |
| `pwd_accepted` | INTEGER | NOT NULL DEFAULT 0 | 1 = student accepted post-withdrawal disbursement |
| `pwd_disbursed_date` | TEXT | NOT NULL DEFAULT '' | Date PWD disbursed |
| `institution_return_due_date` | TEXT | NOT NULL DEFAULT '' | determination_date + 45 calendar days |
| `institution_return_date` | TEXT | NOT NULL DEFAULT '' | Actual date institution returned funds to ED |
| `return_detail` | TEXT | NOT NULL DEFAULT '{}' | JSON: amounts returned per aid type in federal return order |
| `status` | TEXT | NOT NULL DEFAULT 'calculated' CHECK(status IN ('calculated','approved','returned','complete')) | |
| `calculated_by` | TEXT | NOT NULL DEFAULT '' | Staff user ID |
| `approved_by` | TEXT | NOT NULL DEFAULT '' | |
| `notes` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (student_id, academic_term_id)` — one R2T4 per withdrawal per term
- `(company_id, status)` — processing queue
- `(company_id, institution_return_due_date, status)` — 45-day compliance deadline tracking

---

#### Table: `finaid_professional_judgment`

Documentation of Professional Judgment (PJ) decisions by FAA. **Append-only — no `updated_at`.**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `award_package_id` | TEXT | REFERENCES finaid_award_package(id) ON DELETE RESTRICT | Nullable — PJ may precede packaging |
| `pj_type` | TEXT | NOT NULL DEFAULT '' CHECK(pj_type IN ('sai_adjustment','coa_adjustment','dependency_override','enrollment_status_override','other')) | |
| `pj_reason` | TEXT | NOT NULL DEFAULT '' CHECK(pj_reason IN ('job_loss','death_family','illness_injury','divorce_separation','unusual_expenses','natural_disaster','other')) | |
| `reason_narrative` | TEXT | NOT NULL DEFAULT '' | Required: FAA's written explanation |
| `data_element_changed` | TEXT | NOT NULL DEFAULT '' | What was changed (e.g., 'SAI', 'COA.housing', 'dependency_status') |
| `original_value` | TEXT | NOT NULL DEFAULT '' | Value before PJ override |
| `adjusted_value` | TEXT | NOT NULL DEFAULT '' | Value after PJ override |
| `effective_date` | TEXT | NOT NULL DEFAULT '' | When change takes effect |
| `supporting_documentation` | TEXT | NOT NULL DEFAULT '[]' | JSON array of document references |
| `authorized_by` | TEXT | NOT NULL DEFAULT '' | FAA staff user ID |
| `authorization_date` | TEXT | NOT NULL DEFAULT '' | |
| `supervisor_review_required` | INTEGER | NOT NULL DEFAULT 0 | 1 = large adjustment requiring second approval |
| `supervisor_reviewed_by` | TEXT | NOT NULL DEFAULT '' | |
| `supervisor_review_date` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | Immutable — no updated_at |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(student_id, aid_year_id, pj_type)` — PJ history per student per year
- `(company_id, authorization_date)` — audit trail by date

---

#### Table: `finaid_scholarship_program`

Institutional scholarship program definition. Replaces the parent's simplified `educlaw_scholarship` for institutional aid management.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `name` | TEXT | NOT NULL DEFAULT '' | Scholarship program name |
| `code` | TEXT | NOT NULL DEFAULT '' | Short code (e.g., 'MERIT-STEM-25') |
| `description` | TEXT | NOT NULL DEFAULT '' | Full description |
| `scholarship_type` | TEXT | NOT NULL DEFAULT '' CHECK(scholarship_type IN ('merit','need_based','merit_need','athletic','departmental','endowed','external','tuition_waiver')) | |
| `funding_source` | TEXT | NOT NULL DEFAULT '' CHECK(funding_source IN ('endowment','budget','departmental','donor','external')) | |
| `award_method` | TEXT | NOT NULL DEFAULT '' CHECK(award_method IN ('auto_match','application_required','fao_discretion')) | How students receive this award |
| `award_amount_type` | TEXT | NOT NULL DEFAULT '' CHECK(award_amount_type IN ('fixed','percentage_coa','percentage_tuition','variable')) | |
| `award_amount` | TEXT | NOT NULL DEFAULT '0' | Fixed amount or percentage (as decimal) |
| `min_award` | TEXT | NOT NULL DEFAULT '0' | For variable awards |
| `max_award` | TEXT | NOT NULL DEFAULT '0' | For variable awards |
| `annual_budget` | TEXT | NOT NULL DEFAULT '0' | Total institutional allocation per year |
| `budget_remaining` | TEXT | NOT NULL DEFAULT '0' | Available balance (running calculation) |
| `max_recipients` | INTEGER | NOT NULL DEFAULT 0 | 0 = unlimited |
| `renewal_eligible` | INTEGER | NOT NULL DEFAULT 0 | 1 = can be renewed each term |
| `renewal_gpa_minimum` | TEXT | NOT NULL DEFAULT '0' | Minimum GPA to renew |
| `renewal_credits_minimum` | TEXT | NOT NULL DEFAULT '0' | Minimum credits per term to renew |
| `eligibility_criteria` | TEXT | NOT NULL DEFAULT '{}' | JSON: {gpa_min, program_types[], year_levels[], need_threshold, enrollment_min} |
| `application_deadline` | TEXT | NOT NULL DEFAULT '' | For application-based scholarships |
| `award_period` | TEXT | NOT NULL DEFAULT '' CHECK(award_period IN ('annual','per_term','one_time')) | |
| `applies_to_aid_type` | TEXT | NOT NULL DEFAULT '' CHECK(applies_to_aid_type IN ('institutional_grant','institutional_scholarship','tuition_waiver')) | Which aid_type in finaid_award this maps to |
| `gl_account_id` | TEXT | NOT NULL DEFAULT '' | FK to account (expense GL account) |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (company_id, code)` — unique codes per institution
- `(company_id, scholarship_type, is_active)` — filter by type

---

#### Table: `finaid_scholarship_application`

Student application for an application-based scholarship program.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `scholarship_program_id` | TEXT | NOT NULL REFERENCES finaid_scholarship_program(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `submission_date` | TEXT | NOT NULL DEFAULT '' | |
| `status` | TEXT | NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','under_review','awarded','waitlisted','denied','withdrawn')) | |
| `essay_response` | TEXT | NOT NULL DEFAULT '' | If scholarship requires essay |
| `gpa_at_application` | TEXT | NOT NULL DEFAULT '0' | Snapshot of GPA when application submitted |
| `reviewer_id` | TEXT | NOT NULL DEFAULT '' | Staff user ID |
| `review_date` | TEXT | NOT NULL DEFAULT '' | |
| `review_notes` | TEXT | NOT NULL DEFAULT '' | |
| `award_amount` | TEXT | NOT NULL DEFAULT '0' | If awarded (may differ from program standard) |
| `award_term_id` | TEXT | REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | First term of award |
| `denial_reason` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (scholarship_program_id, student_id, aid_year_id)` — one application per student per program per year
- `(company_id, status)` — reviewer queue
- `(student_id, status)` — student application history

---

#### Table: `finaid_scholarship_renewal`

Term-by-term renewal evaluation for multi-term scholarships.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `scholarship_application_id` | TEXT | NOT NULL REFERENCES finaid_scholarship_application(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `scholarship_program_id` | TEXT | NOT NULL REFERENCES finaid_scholarship_program(id) ON DELETE RESTRICT | |
| `academic_term_id` | TEXT | NOT NULL REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | |
| `renewal_status` | TEXT | NOT NULL DEFAULT 'renewed' CHECK(renewal_status IN ('renewed','suspended','revoked','exhausted')) | |
| `gpa_at_evaluation` | TEXT | NOT NULL DEFAULT '0' | Cumulative GPA when evaluated |
| `credits_attempted` | INTEGER | NOT NULL DEFAULT 0 | Credits attempted this term |
| `meets_criteria` | INTEGER | NOT NULL DEFAULT 0 | 1 = all renewal criteria met |
| `reason` | TEXT | NOT NULL DEFAULT '' | If suspended or revoked |
| `evaluated_by` | TEXT | NOT NULL DEFAULT '' | |
| `evaluation_date` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (scholarship_application_id, academic_term_id)` — one renewal evaluation per term per award
- `(student_id, renewal_status)` — student scholarship status

---

#### Table: `finaid_work_study_job`

Federal Work-Study (FWS) job postings open to FWS-awarded students.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `job_title` | TEXT | NOT NULL DEFAULT '' | |
| `department_id` | TEXT | NOT NULL DEFAULT '' | FK to department (erpclaw-setup) |
| `supervisor_id` | TEXT | NOT NULL DEFAULT '' | FK to employee record (erpclaw-hr) |
| `job_type` | TEXT | NOT NULL DEFAULT '' CHECK(job_type IN ('on_campus','off_campus_community','off_campus_other')) | Community service jobs tracked for 7% FWS requirement |
| `description` | TEXT | NOT NULL DEFAULT '' | |
| `pay_rate` | TEXT | NOT NULL DEFAULT '0' | Hourly rate (must be ≥ federal minimum wage) |
| `hours_per_week` | TEXT | NOT NULL DEFAULT '0' | Expected weekly hours |
| `total_positions` | INTEGER | NOT NULL DEFAULT 1 | How many students can be placed |
| `filled_positions` | INTEGER | NOT NULL DEFAULT 0 | Running count of active assignments |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `status` | TEXT | NOT NULL DEFAULT 'open' CHECK(status IN ('open','filled','closed')) | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(company_id, aid_year_id, status)` — available jobs for a year
- `(company_id, job_type)` — community service tracking for 7% requirement

---

#### Table: `finaid_work_study_assignment`

Student assigned to a specific FWS job.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `award_id` | TEXT | NOT NULL REFERENCES finaid_award(id) ON DELETE RESTRICT | The FWS award line in the student's package |
| `job_id` | TEXT | NOT NULL REFERENCES finaid_work_study_job(id) ON DELETE RESTRICT | |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `academic_term_id` | TEXT | NOT NULL REFERENCES educlaw_academic_term(id) ON DELETE RESTRICT | |
| `start_date` | TEXT | NOT NULL DEFAULT '' | |
| `end_date` | TEXT | NOT NULL DEFAULT '' | |
| `award_limit` | TEXT | NOT NULL DEFAULT '0' | Maximum earnings = FWS award amount |
| `earned_to_date` | TEXT | NOT NULL DEFAULT '0' | Running total of approved + paid timesheets |
| `status` | TEXT | NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','terminated')) | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(student_id, aid_year_id, status)` — student work-study history
- `(job_id, status)` — job assignment tracking
- `(company_id, academic_term_id, status)` — term-level FWS roster

---

#### Table: `finaid_work_study_timesheet`

Hours worked per pay period for a work-study assignment.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `assignment_id` | TEXT | NOT NULL REFERENCES finaid_work_study_assignment(id) ON DELETE RESTRICT | |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | Denormalized |
| `pay_period_start` | TEXT | NOT NULL DEFAULT '' | |
| `pay_period_end` | TEXT | NOT NULL DEFAULT '' | |
| `hours_worked` | TEXT | NOT NULL DEFAULT '0' | Decimal hours (e.g., '7.50') |
| `earnings` | TEXT | NOT NULL DEFAULT '0' | hours_worked × pay_rate |
| `cumulative_earnings` | TEXT | NOT NULL DEFAULT '0' | Running total for this assignment |
| `submission_date` | TEXT | NOT NULL DEFAULT '' | When student submitted timesheet |
| `supervisor_approval_status` | TEXT | NOT NULL DEFAULT 'pending' CHECK(supervisor_approval_status IN ('pending','approved','rejected')) | |
| `supervisor_approved_by` | TEXT | NOT NULL DEFAULT '' | Employee ID of approving supervisor |
| `supervisor_approved_date` | TEXT | NOT NULL DEFAULT '' | |
| `rejection_reason` | TEXT | NOT NULL DEFAULT '' | If rejected by supervisor |
| `payroll_exported` | INTEGER | NOT NULL DEFAULT 0 | 1 = included in payroll export file |
| `payroll_export_date` | TEXT | NOT NULL DEFAULT '' | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `UNIQUE (assignment_id, pay_period_start)` — one timesheet per pay period per assignment
- `(student_id, pay_period_start)` — student timesheet history
- `(company_id, supervisor_approval_status)` — supervisor approval queue

---

#### Table: `finaid_loan`

Federal student loan origination record. One row per loan per student per aid year.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID4 |
| `student_id` | TEXT | NOT NULL REFERENCES educlaw_student(id) ON DELETE RESTRICT | |
| `award_id` | TEXT | NOT NULL REFERENCES finaid_award(id) ON DELETE RESTRICT | The loan award line in the package |
| `aid_year_id` | TEXT | NOT NULL REFERENCES finaid_aid_year(id) ON DELETE RESTRICT | |
| `loan_type` | TEXT | NOT NULL DEFAULT '' CHECK(loan_type IN ('subsidized','unsubsidized','graduate_plus','parent_plus','teach')) | |
| `loan_period_start` | TEXT | NOT NULL DEFAULT '' | Payment period start |
| `loan_period_end` | TEXT | NOT NULL DEFAULT '' | Payment period end |
| `loan_amount` | TEXT | NOT NULL DEFAULT '0' | Total origination amount |
| `first_disbursement_amount` | TEXT | NOT NULL DEFAULT '0' | First disbursement (start of term) |
| `second_disbursement_amount` | TEXT | NOT NULL DEFAULT '0' | Second disbursement (mid-term) |
| `origination_fee` | TEXT | NOT NULL DEFAULT '0' | Origination fee percentage |
| `interest_rate` | TEXT | NOT NULL DEFAULT '0' | Current year statutory interest rate |
| `cod_loan_id` | TEXT | NOT NULL DEFAULT '' | COD-assigned Loan ID (unique to COD system) |
| `cod_origination_status` | TEXT | NOT NULL DEFAULT '' CHECK(cod_origination_status IN ('pending','accepted','rejected','')) | |
| `cod_origination_date` | TEXT | NOT NULL DEFAULT '' | |
| `mpn_required` | INTEGER | NOT NULL DEFAULT 1 | 1 = MPN must be signed before disbursement |
| `mpn_signed` | INTEGER | NOT NULL DEFAULT 0 | 1 = MPN confirmed signed at StudentAid.gov |
| `mpn_signed_date` | TEXT | NOT NULL DEFAULT '' | |
| `entrance_counseling_required` | INTEGER | NOT NULL DEFAULT 0 | 1 = first-time borrower; counseling required |
| `entrance_counseling_complete` | INTEGER | NOT NULL DEFAULT 0 | |
| `entrance_counseling_date` | TEXT | NOT NULL DEFAULT '' | |
| `exit_counseling_required` | INTEGER | NOT NULL DEFAULT 0 | 1 = upon withdrawal or graduation |
| `exit_counseling_complete` | INTEGER | NOT NULL DEFAULT 0 | |
| `exit_counseling_date` | TEXT | NOT NULL DEFAULT '' | |
| `borrower_id` | TEXT | NOT NULL DEFAULT '' | For parent PLUS: guardian.id; else: student.id |
| `borrower_type` | TEXT | NOT NULL DEFAULT 'student' CHECK(borrower_type IN ('student','parent')) | |
| `status` | TEXT | NOT NULL DEFAULT 'originated' CHECK(status IN ('originated','active','repayment','deferred','defaulted','paid_off','cancelled')) | |
| `company_id` | TEXT | NOT NULL REFERENCES company(id) ON DELETE RESTRICT | |
| `created_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT | NOT NULL DEFAULT (datetime('now')) | |
| `created_by` | TEXT | NOT NULL DEFAULT '' | |

**Indexes:**
- `(student_id, aid_year_id, loan_type)` — student loan history per year
- `(company_id, cod_origination_status)` — COD origination reconciliation
- `(company_id, mpn_signed, entrance_counseling_complete)` — disbursement holds dashboard

---

### 3.2 Tables (Inherited from Parent — Read-Only)

These tables are owned by `educlaw` or foundation skills. `educlaw-finaid` reads from them but never writes to them directly.

| Table | Owner | How finaid Uses It |
|-------|-------|-------------------|
| `educlaw_student` | educlaw | Primary entity for all finaid records; SSN (encrypted), GPA, credits, status, customer_id |
| `educlaw_academic_year` | educlaw | Aid year alignment (academic year ↔ federal award year) |
| `educlaw_academic_term` | educlaw | Term dates → payment periods; COA assignments; disbursement scheduling |
| `educlaw_program` | educlaw | Loan limit determination; COA setup; aid eligibility; total_credits_required for SAP |
| `educlaw_program_enrollment` | educlaw | Active enrollment confirmation for disbursement; link to fee invoice |
| `educlaw_course_enrollment` | educlaw | Credits attempted/completed for SAP; drop_date for R2T4 LDA; is_repeat for SAP logic |
| `educlaw_guardian` | educlaw | Parent data for dependent students; Parent PLUS loan borrower reference |
| `educlaw_student_guardian` | educlaw | Guardian-student relationship (dependent/independent determination) |
| `educlaw_data_access_log` | educlaw | All finaid student record access must be logged here with data_category='financial' |
| `educlaw_consent_record` | educlaw | Title IV authorization; third-party disclosure consent |
| `educlaw_announcement` | educlaw | Broadcast aid notifications to student body |
| `educlaw_notification` | educlaw | Per-student alerts (award letter, verification request, SAP notice) |
| `company` | erpclaw-setup | Company context for all finaid records |
| `erp_user` | erpclaw-setup | Staff user references (FAO counselors, reviewers, approvers) |
| `account` | erpclaw-gl | GL accounts for disbursement journal entries |
| `customer` | erpclaw-selling | Student as customer for credit posting |
| `sales_invoice` | erpclaw-selling | Tuition charges that aid credits are applied against |

---

### 3.3 Lookup / Reference Tables

The following finaid tables function as seed/reference data loaded at setup:

| Table | Seeded With |
|-------|-------------|
| `finaid_pell_schedule` | Pell award schedule imported from Federal Student Aid each award year |
| `finaid_aid_year` | One record per award year (created annually) |
| `finaid_fund_allocation` | FSEOG, FWS, and institutional allocations (set at start of aid year) |

---

## 4. Action List

**Total: 115 actions across 4 domain modules**

---

### 4.1 Actions by Domain

#### Domain: `financial_aid` — 72 Actions

##### Aid Year Setup (7 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-aid-year` | CRUD | Create new federal award year configuration | `finaid_aid_year` |
| `update-aid-year` | CRUD | Update aid year description, Pell max, dates | `finaid_aid_year` |
| `get-aid-year` | Query | Get aid year by ID | `finaid_aid_year` |
| `list-aid-years` | Query | List aid years for company, optionally filter by active | `finaid_aid_year` |
| `set-active-aid-year` | Update | Mark one aid year as active; deactivates previous | `finaid_aid_year` |
| `import-pell-schedule` | CRUD | Bulk import Pell payment schedule rows for an aid year | `finaid_pell_schedule` |
| `list-pell-schedule` | Query | List Pell schedule entries for an aid year (with optional pell_index filter) | `finaid_pell_schedule` |

##### Fund Allocation (4 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-fund-allocation` | CRUD | Create campus-based fund allocation (FSEOG, FWS, institutional) | `finaid_fund_allocation` |
| `update-fund-allocation` | CRUD | Update allocation amounts (committed/disbursed/available recalculated) | `finaid_fund_allocation` |
| `get-fund-allocation` | Query | Get fund allocation by ID | `finaid_fund_allocation` |
| `list-fund-allocations` | Query | List allocations by aid year and fund type | `finaid_fund_allocation` |

##### Cost of Attendance (5 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-cost-of-attendance` | CRUD | Create COA budget for program/enrollment status/aid year | `finaid_cost_of_attendance` |
| `update-cost-of-attendance` | CRUD | Update individual COA components; recalculates total_coa | `finaid_cost_of_attendance` |
| `get-cost-of-attendance` | Query | Get COA record by ID | `finaid_cost_of_attendance` |
| `list-cost-of-attendance` | Query | List COAs by aid year, program, enrollment status | `finaid_cost_of_attendance` |
| `delete-cost-of-attendance` | Delete | Delete COA (only if not referenced by any award package) | `finaid_cost_of_attendance` |

##### ISIR Management (8 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `import-isir` | CRUD | Import/create ISIR record for a student; parses fields, creates C-flags | `finaid_isir`, `finaid_isir_cflag` |
| `update-isir` | CRUD | Update ISIR fields (manual correction); recalculates has_unresolved_cflags | `finaid_isir` |
| `get-isir` | Query | Get ISIR with all C-flags (auto-logs FERPA access) | `finaid_isir`, `finaid_isir_cflag`, `educlaw_data_access_log` |
| `list-isirs` | Query | List ISIRs by company/aid year/status/student | `finaid_isir` |
| `review-isir` | Update | Mark ISIR as reviewed by FAO; sets reviewed_by and reviewed_at | `finaid_isir` |
| `add-isir-cflag` | CRUD | Manually add a C-flag to an ISIR (for flags not in original file) | `finaid_isir_cflag`, `finaid_isir` |
| `resolve-isir-cflag` | Update | Resolve or waive a C-flag with documentation; updates has_unresolved_cflags cache | `finaid_isir_cflag`, `finaid_isir` |
| `list-isir-cflags` | Query | List all C-flags for an ISIR or all pending flags for a student | `finaid_isir_cflag` |

##### Verification Workflow (8 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `create-verification-request` | CRUD | Create verification request for flagged ISIR; auto-generates required document list by group | `finaid_verification_request`, `finaid_verification_document` |
| `update-verification-request` | CRUD | Update verification status, deadline, assigned counselor | `finaid_verification_request` |
| `get-verification-request` | Query | Get request with all document statuses (logs FERPA) | `finaid_verification_request`, `finaid_verification_document`, `educlaw_data_access_log` |
| `list-verification-requests` | Query | List by company/status/assigned counselor | `finaid_verification_request` |
| `add-verification-document` | CRUD | Add document requirement to request | `finaid_verification_document` |
| `update-verification-document` | CRUD | Update document submission status (submitted/accepted/rejected/waived) | `finaid_verification_document` |
| `complete-verification` | Update | Mark verification complete; releases disbursement hold; checks all required docs accepted | `finaid_verification_request`, `finaid_isir` |
| `list-verification-documents` | Query | List all documents for a verification request | `finaid_verification_document` |

##### Award Packaging (13 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `create-award-package` | CRUD | Create draft award package for student/term; calculates need = COA − SAI | `finaid_award_package` |
| `update-award-package` | CRUD | Update package metadata, notes, enrollment status | `finaid_award_package` |
| `get-award-package` | Query | Get package with all award lines (logs FERPA) | `finaid_award_package`, `finaid_award`, `educlaw_data_access_log` |
| `list-award-packages` | Query | List packages by company/status/aid year/term/student | `finaid_award_package` |
| `add-award` | CRUD | Add individual award line item to draft package; validates overaward ceiling | `finaid_award`, `finaid_award_package` |
| `update-award` | CRUD | Update award amount (draft only); recalculates package totals | `finaid_award`, `finaid_award_package` |
| `get-award` | Query | Get single award line item | `finaid_award` |
| `list-awards` | Query | List awards by package, student, aid type, or acceptance status | `finaid_award` |
| `delete-award` | Delete | Remove award line from draft package | `finaid_award`, `finaid_award_package` |
| `offer-award-package` | Submit | Validate package (no overaward, all holds clear), set status=offered, record offered_date | `finaid_award_package`, `finaid_award` |
| `accept-award` | Update | Student accepts individual award; sets acceptance_status=accepted; records accepted_amount | `finaid_award`, `finaid_award_package` |
| `decline-award` | Update | Student declines individual award; sets acceptance_status=declined | `finaid_award`, `finaid_award_package` |
| `cancel-award-package` | Cancel | Cancel offered package; reverses committed fund allocations | `finaid_award_package`, `finaid_award`, `finaid_fund_allocation` |

##### Disbursement (8 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `disburse-award` | Submit | Post aid disbursement to student account; pre-disbursement checks; GL journal; applies credit to sales invoice | `finaid_disbursement`, `finaid_award`, `finaid_award_package` + GL + erpclaw-selling |
| `reverse-disbursement` | Cancel | Create reversal record for incorrect disbursement; GL reversal | `finaid_disbursement` + GL |
| `record-r2t4-return-disbursement` | CRUD | Record return of Title IV funds to ED after R2T4; GL entry | `finaid_disbursement`, `finaid_r2t4_calculation` + GL |
| `get-disbursement` | Query | Get disbursement record | `finaid_disbursement` |
| `list-disbursements` | Query | List by student/term/status/COD status/credit balance flag | `finaid_disbursement` |
| `generate-cod-export` | Query | Generate COD Common Record XML for Pell and Direct Loan disbursements (manual submission) | `finaid_disbursement`, `finaid_loan`, `finaid_award` |
| `update-cod-status` | Update | Record COD acknowledgment/rejection for a disbursement | `finaid_disbursement` |
| `mark-credit-balance-returned` | Update | Record that credit balance refund was issued to student; validates 14-day rule | `finaid_disbursement` |

##### SAP Evaluation (10 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `run-sap-evaluation` | Submit | Calculate SAP (GPA, pace, max timeframe) for a single student/term; reads educlaw enrollment data | `finaid_sap_evaluation`, `educlaw_course_enrollment`, `educlaw_student`, `educlaw_program` |
| `run-sap-batch` | Submit | Batch SAP evaluation for all financial aid students in a term | `finaid_sap_evaluation` (many), `educlaw_course_enrollment` |
| `get-sap-evaluation` | Query | Get SAP evaluation with all component details | `finaid_sap_evaluation` |
| `list-sap-evaluations` | Query | List evaluations by company/student/term/sap_status | `finaid_sap_evaluation` |
| `override-sap-status` | Update | Manual FAO SAP status override with required documentation | `finaid_sap_evaluation` |
| `submit-sap-appeal` | CRUD | Student submits SAP suspension appeal; validates FSP status | `finaid_sap_appeal`, `finaid_sap_evaluation` |
| `update-sap-appeal` | CRUD | Update appeal with reviewer notes | `finaid_sap_appeal` |
| `get-sap-appeal` | Query | Get appeal details | `finaid_sap_appeal` |
| `list-sap-appeals` | Query | List appeals by company/student/status | `finaid_sap_appeal` |
| `decide-sap-appeal` | Update | FAO grants or denies appeal; if granted, sets FAP status and probation term; releases disbursement hold | `finaid_sap_appeal`, `finaid_sap_evaluation`, `finaid_award` |

##### R2T4 Calculation (6 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `create-r2t4` | CRUD | Create R2T4 record for a withdrawal event; pulls term dates from educlaw | `finaid_r2t4_calculation`, `educlaw_academic_term` |
| `calculate-r2t4` | Submit | Run R2T4 formula; compute percent completed, earned aid, institution/student return amounts, 45-day deadline | `finaid_r2t4_calculation`, `finaid_disbursement`, `finaid_award` |
| `approve-r2t4` | Update | FAO approves R2T4 calculation; locks worksheet | `finaid_r2t4_calculation` |
| `record-r2t4-return` | Update | Record institution's return of funds to ED; validate within 45-day window | `finaid_r2t4_calculation` |
| `get-r2t4` | Query | Get R2T4 calculation with full worksheet detail | `finaid_r2t4_calculation` |
| `list-r2t4s` | Query | List by company/status/student; optionally filter by approaching deadline | `finaid_r2t4_calculation` |

##### Professional Judgment (4 actions)

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-professional-judgment` | CRUD | Document PJ decision; immutable once created; optional supervisor approval flag | `finaid_professional_judgment` |
| `get-professional-judgment` | Query | Get PJ record (logs FERPA) | `finaid_professional_judgment`, `educlaw_data_access_log` |
| `list-professional-judgments` | Query | List PJ records by student/aid year/type | `finaid_professional_judgment` |
| `approve-professional-judgment` | Update | Second-level supervisor approval for large PJ adjustments | `finaid_professional_judgment` |

---

#### Domain: `scholarships` — 15 Actions

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-scholarship-program` | CRUD | Create institutional scholarship program definition with eligibility criteria | `finaid_scholarship_program` |
| `update-scholarship-program` | CRUD | Update scholarship program details, criteria, budget, award amounts | `finaid_scholarship_program` |
| `get-scholarship-program` | Query | Get program with eligibility criteria | `finaid_scholarship_program` |
| `list-scholarship-programs` | Query | List programs by type, active status, funding source | `finaid_scholarship_program` |
| `deactivate-scholarship-program` | Update | Deactivate scholarship program (no new awards) | `finaid_scholarship_program` |
| `auto-match-scholarships` | Submit | System identifies eligible students for auto_match programs; creates awards in packages | `finaid_scholarship_program`, `finaid_award`, `finaid_award_package`, `educlaw_student` |
| `submit-scholarship-application` | CRUD | Student submits application for application-based scholarship | `finaid_scholarship_application` |
| `update-scholarship-application` | CRUD | Update application (essay, additional materials) | `finaid_scholarship_application` |
| `get-scholarship-application` | Query | Get application details | `finaid_scholarship_application` |
| `list-scholarship-applications` | Query | List by program/status/aid year/reviewer | `finaid_scholarship_application` |
| `review-scholarship-application` | Update | FAO assigns reviewer; adds review notes | `finaid_scholarship_application` |
| `award-scholarship-application` | Update | Award scholarship; sets status=awarded; creates award in package | `finaid_scholarship_application`, `finaid_award`, `finaid_scholarship_program` |
| `deny-scholarship-application` | Update | Deny application with reason | `finaid_scholarship_application` |
| `evaluate-scholarship-renewal` | Submit | End-of-term renewal check: verify GPA/enrollment meet criteria; create renewal record | `finaid_scholarship_renewal`, `finaid_scholarship_application`, `educlaw_student` |
| `list-scholarship-renewals` | Query | List renewal evaluations by program/student/term/status | `finaid_scholarship_renewal` |

---

#### Domain: `work_study` — 18 Actions

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-work-study-job` | CRUD | Create FWS job posting | `finaid_work_study_job` |
| `update-work-study-job` | CRUD | Update job title, pay rate, positions, description | `finaid_work_study_job` |
| `get-work-study-job` | Query | Get job with assignment count | `finaid_work_study_job`, `finaid_work_study_assignment` |
| `list-work-study-jobs` | Query | List jobs by aid year/department/status/job type | `finaid_work_study_job` |
| `close-work-study-job` | Update | Close job to new assignments; sets status=closed | `finaid_work_study_job` |
| `assign-student-to-job` | CRUD | Create work-study assignment; validates FWS award exists; increments filled_positions | `finaid_work_study_assignment`, `finaid_work_study_job`, `finaid_award` |
| `update-work-study-assignment` | CRUD | Update assignment dates, award limit | `finaid_work_study_assignment` |
| `get-work-study-assignment` | Query | Get assignment with earnings summary | `finaid_work_study_assignment`, `finaid_work_study_timesheet` |
| `list-work-study-assignments` | Query | List by student/job/term/status | `finaid_work_study_assignment` |
| `terminate-work-study-assignment` | Update | End assignment early; decrements job filled_positions | `finaid_work_study_assignment`, `finaid_work_study_job` |
| `submit-work-study-timesheet` | CRUD | Student submits hours for a pay period; validates no duplicate period; checks award limit | `finaid_work_study_timesheet`, `finaid_work_study_assignment` |
| `update-work-study-timesheet` | CRUD | Update timesheet hours (only if still pending approval) | `finaid_work_study_timesheet` |
| `approve-work-study-timesheet` | Update | Supervisor approves timesheet; calculates earnings; updates cumulative | `finaid_work_study_timesheet`, `finaid_work_study_assignment` |
| `reject-work-study-timesheet` | Update | Supervisor rejects timesheet with reason | `finaid_work_study_timesheet` |
| `get-work-study-timesheet` | Query | Get timesheet record | `finaid_work_study_timesheet` |
| `list-work-study-timesheets` | Query | List by student/assignment/approval status/pay period | `finaid_work_study_timesheet` |
| `export-work-study-payroll` | Submit | Export approved, unpaid timesheets to payroll file (CSV); marks payroll_exported=1 | `finaid_work_study_timesheet` |
| `get-work-study-earnings-summary` | Query | Student earnings vs. award limit; community service hours summary | `finaid_work_study_assignment`, `finaid_work_study_timesheet` |

---

#### Domain: `loan_tracking` — 10 Actions

| Action | Type | Description | Tables Touched |
|--------|------|-------------|----------------|
| `add-loan` | CRUD | Create loan origination record linked to accepted award; validates MPN/counseling requirements; checks annual/aggregate limits | `finaid_loan`, `finaid_award`, `finaid_isir` |
| `update-loan` | CRUD | Update loan period, disbursement amounts, interest rate, COD identifiers | `finaid_loan` |
| `get-loan` | Query | Get loan record with MPN/counseling status | `finaid_loan` |
| `list-loans` | Query | List by student/aid year/loan type/status/COD status | `finaid_loan` |
| `update-mpn-status` | Update | Record MPN signed date; clears MPN disbursement hold on award | `finaid_loan`, `finaid_award` |
| `update-entrance-counseling` | Update | Record entrance counseling completion; clears EC disbursement hold on award | `finaid_loan`, `finaid_award` |
| `update-exit-counseling` | Update | Record exit counseling completion on withdrawal or graduation | `finaid_loan` |
| `generate-cod-origination` | Query | Generate COD origination data for manual XML submission to COD portal; output includes all required COD fields | `finaid_loan`, `finaid_award`, `finaid_award_package`, `educlaw_student` |
| `update-cod-origination-status` | Update | Record COD origination acknowledgment or rejection | `finaid_loan` |
| `get-loan-limits-status` | Query | Check annual and aggregate loan totals for a student/aid year; compares against regulatory limits | `finaid_loan`, `finaid_isir`, `finaid_award` |

---

### 4.2 Cross-Domain Actions

The following workflows span multiple domains:

| Workflow | Actions Involved | Description |
|----------|-----------------|-------------|
| **ISIR → Package → Disburse** | `import-isir` → `create-verification-request` (if flagged) → `create-award-package` → `offer-award-package` → `accept-award` → `disburse-award` | Full financial aid lifecycle |
| **Withdrawal → R2T4 → Return** | `create-r2t4` → `calculate-r2t4` → `approve-r2t4` → `record-r2t4-return-disbursement` → `record-r2t4-return` | Title IV withdrawal compliance |
| **End-of-Term SAP → Appeal** | `run-sap-batch` → `submit-sap-appeal` → `decide-sap-appeal` | Annual SAP compliance cycle |
| **Scholarship → Package** | `award-scholarship-application` or `auto-match-scholarships` → `add-award` in package | Institutional scholarship integration |
| **FWS Award → Assignment → Timesheet → Payroll** | `disburse-award` (FWS award only earns) → `assign-student-to-job` → `submit-work-study-timesheet` → `approve-work-study-timesheet` → `export-work-study-payroll` | Work-study employment lifecycle |
| **Loan → MPN + Counseling → Disbursement** | `add-loan` → `update-mpn-status` → `update-entrance-counseling` → `disburse-award` (holds clear) | Loan compliance gate |

---

### 4.3 Naming Conflict Check

**Actions compared against parent (educlaw) action namespace:**

educlaw parent actions include: `add-student`, `update-student`, `get-student`, `list-students`, `add-guardian`, `assign-guardian`, `add-scholarship`, `update-scholarship`, `list-scholarships`, `generate-fee-invoice`, `get-student-account`, `add-consent-record`, `record-data-access`, `send-notification`, `add-announcement`, etc.

**Potential conflicts resolved:**

| Our Action | Parent Action | Resolution |
|------------|--------------|------------|
| `add-scholarship-program` | `add-scholarship` | Different — parent's `add-scholarship` is a simple invoice discount. Our action creates a full scholarship program definition. No conflict. |
| `list-scholarship-programs` | `list-scholarships` | Different scopes — parent lists student discount records; ours lists program definitions. No conflict. |

**Verdict: Zero naming conflicts with parent educlaw or foundation skills.** All 115 actions use unique kebab-case names prefixed with finaid domain concepts not present in parent or foundation.

---

## 5. Workflows

### Workflow 1: ISIR Import and Review

**Trigger:** FAO receives ISIR file from FSA (manual import in v1)

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Import | `import-isir` | `finaid_isir` + `finaid_isir_cflag` created |
| 2. Review | `review-isir` | ISIR status → reviewed |
| 3. C-flag resolution | `resolve-isir-cflag` (per flag) | Clears holds; updates `has_unresolved_cflags` |
| 4. Verification (if flagged) | `create-verification-request` | → Workflow 2 |
| 5. Proceed to packaging | `create-award-package` | → Workflow 3 |

**GL/SLE implications:** None at this stage.

---

### Workflow 2: Verification

**Trigger:** `finaid_isir.verification_flag = 1`

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Create request | `create-verification-request` | Document checklist auto-generated by group (V1/V4/V5) |
| 2. Document receipt | `update-verification-document` (per doc) | Tracks submitted/accepted/rejected |
| 3. Complete | `complete-verification` | Status = complete; disbursement hold released |

**GL/SLE implications:** None.

---

### Workflow 3: Aid Packaging

**Trigger:** ISIR reviewed; enrollment confirmed; COA available

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Create package | `create-award-package` | Need = COA − SAI calculated |
| 2. Add Pell | `add-award` (aid_type=pell) | Pell amount from `finaid_pell_schedule` |
| 3. Add FSEOG | `add-award` (aid_type=fseog) | If allocation available |
| 4. Add institutional grants | `add-award` (aid_type=institutional_grant/scholarship) | From `finaid_scholarship_program` |
| 5. Add FWS | `add-award` (aid_type=fws) | If FWS allocation available |
| 6. Add loans | `add-award` (sub/unsub) | Within annual limits; overaward check |
| 7. Offer | `offer-award-package` | Status = offered; award letter sent |

**GL/SLE implications:** None at packaging stage. Allocations committed but not posted.

---

### Workflow 4: Award Acceptance and Disbursement

**Trigger:** Student receives award letter; `award_package.status = offered`

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Accept awards | `accept-award` (per line) | acceptance_status = accepted |
| 2. Loan compliance | `add-loan` → `update-mpn-status` → `update-entrance-counseling` | MPN/EC holds cleared |
| 3. Disburse | `disburse-award` (per award line) | GL journal posted; credit applied to sales invoice |
| 4. Credit balance | `mark-credit-balance-returned` | If aid > charges, refund issued within 14 days |
| 5. COD reporting | `generate-cod-export` | XML generated for manual COD submission |
| 6. COD acknowledgment | `update-cod-status` | Records COD confirmation |

**GL/SLE implications:**
- `disburse-award` posts a GL journal entry:
  - **Debit:** Financial Aid Receivable / Fund account
  - **Credit:** Student Account (erpclaw-selling customer account)
- `reverse-disbursement` reverses the above entries
- `record-r2t4-return-disbursement` posts return entries per federal return order

---

### Workflow 5: SAP Evaluation (End of Term)

**Trigger:** `educlaw_academic_term.status = 'grades_finalized'`

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Run batch | `run-sap-batch` | Creates `finaid_sap_evaluation` for all aid students |
| 2. Review results | `list-sap-evaluations` | FAO reviews FSP/FAW students |
| 3. Notify students | Parent `send-notification` | SAP status notifications sent |
| 4. Place holds | Automatic within `run-sap-evaluation` | FSP students have disbursement holds placed |

**SAP Status Machine:**
```
SAT → (fails) → FAW → (fails again) → FSP → (appeal granted) → FAP → (passes) → SAT
                                    ↑ (max timeframe exceeded: skip FAW)
```

**GL/SLE implications:** None. SAP holds block future disbursements but do not post entries.

---

### Workflow 6: SAP Appeal

**Trigger:** Student in FSP status submits appeal

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Submit | `submit-sap-appeal` | Appeal record created |
| 2. Review | `update-sap-appeal` | Reviewer notes added |
| 3. Decision | `decide-sap-appeal` | If granted: FAP status; hold released; probation term set |

**GL/SLE implications:** None.

---

### Workflow 7: R2T4 Calculation and Return

**Trigger:** Student withdraws from all courses in a payment period

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Create | `create-r2t4` | Withdrawal date, LDA, determination date recorded |
| 2. Calculate | `calculate-r2t4` | Full formula computed; 45-day deadline set |
| 3. Approve | `approve-r2t4` | FAO locks worksheet |
| 4. Return funds | `record-r2t4-return-disbursement` | GL entries for returned Title IV funds |
| 5. Record return | `record-r2t4-return` | Return date vs. due date compliance |

**GL/SLE implications:**
- Return of Pell: Debit Student Account Credit / Credit Financial Aid Receivable
- Return of loans: Debit Loan Liability / Credit Cash (payable to ED)
- All returns in federal return order: Unsub → Sub → PLUS → Pell → FSEOG → TEACH

---

### Workflow 8: Institutional Scholarship Cycle

**Trigger:** Annual scholarship award cycle

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Define program | `add-scholarship-program` | Program with criteria and budget |
| 2a. Auto-match | `auto-match-scholarships` | Eligible students identified; awards added to packages |
| 2b. Application | `submit-scholarship-application` → `review-scholarship-application` → `award-scholarship-application` | Award decision recorded |
| 3. Add to package | `award-scholarship-application` (calls `add-award`) | Scholarship appears in aid package |
| 4. Renewal | `evaluate-scholarship-renewal` (end of each term) | Renewal status recorded |

---

### Workflow 9: Work-Study Employment

**Trigger:** FWS award in accepted package

| Step | Actions | Outcome |
|------|---------|---------|
| 1. Post job | `add-work-study-job` | Job available to FWS students |
| 2. Assign | `assign-student-to-job` | Assignment with award limit |
| 3. Timesheet | `submit-work-study-timesheet` → `approve-work-study-timesheet` | Hours approved |
| 4. Payroll | `export-work-study-payroll` | Payroll file generated; students paid directly (not via student account) |

**GL/SLE implications:** FWS earnings are NOT posted to the student account. They are paid via regular payroll. The GL impact is through the HR/payroll system, not educlaw-finaid.

---

## 6. Dependencies

### 6.1 Foundation Skills

| Skill | What We Use | How |
|-------|-------------|-----|
| `erpclaw-setup` | `company` table; `erp_user` table; role/permission system | All finaid tables reference `company(id)`; user IDs reference `erp_user` |
| `erpclaw-gl` | `insert_gl_entries()`, `reverse_gl_entries()`, `validate_gl_entries()` from `gl_posting.py` | Called in `disburse-award` and `reverse-disbursement` for journal entries |
| `erpclaw-selling` | `sales_invoice` table; `customer` table | `disburse-award` credits the student's account via the sales invoice FK; `get-student-account` called to confirm charges |
| `erpclaw-payments` | Payment/refund processing | Credit balance refunds are issued via erpclaw-payments when aid exceeds charges |
| `erpclaw-hr` | `employee` table | FWS job supervisor references employee; FAO staff are erpclaw-hr employees |

### 6.2 Parent (educlaw) Dependencies

| Parent Table / Action | Relationship | How finaid Uses It |
|----------------------|-------------|-------------------|
| `educlaw_student` | FK reference (all finaid tables) | Primary entity; SSN_encrypted for ISIR matching; cumulative_gpa for SAP; customer_id for disbursement |
| `educlaw_academic_term` | FK reference | Payment period dates for R2T4; disbursement scheduling; SAP evaluation trigger |
| `educlaw_academic_year` | FK reference (via `finaid_aid_year`) | Aid year ↔ academic year alignment |
| `educlaw_program` | FK reference | total_credits_required for SAP max timeframe; program type for loan limits and COA |
| `educlaw_program_enrollment` | FK reference | Enrollment status confirmation for disbursement holds |
| `educlaw_course_enrollment` | Read (SAP, R2T4) | credits_attempted/completed for SAP pace; drop_date for R2T4 LDA; is_repeat for SAP logic; grade_type for audit exclusion |
| `educlaw_guardian` | Read | Parent PLUS loan borrower identification; dependent student FAFSA |
| `educlaw_student_guardian` | Read | Dependency status determination for FAFSA |
| `educlaw_data_access_log` | Write | Every student financial aid record read must log here with `data_category='financial'` |
| `educlaw_consent_record` | Write | Title IV authorization and third-party disclosure consent |
| `educlaw_notification` | Write (via parent action) | Award letters, verification requests, SAP suspension notices |
| `educlaw_announcement` | Write (via parent action) | Broadcast financial aid deadlines and events |
| `get-student` | Called | Retrieve student data (parent action auto-logs FERPA) |
| `list-enrollments` | Called | Determine credit load for SAP and COA enrollment status |
| `generate-transcript` | Called | SAP review reference |
| `send-notification` | Called | Award letters, verification requests, disbursement alerts |
| `record-data-access` | Called | Manual FERPA logging for financial data access |
| `add-consent-record` | Called | Document Title IV authorization |

### 6.3 Parent Actions Superseded

| Parent Action | educlaw-finaid Status | Reason |
|--------------|----------------------|--------|
| `add-scholarship` (educlaw fees domain) | **Superseded** for institutional aid | Parent action creates a simple invoice discount. educlaw-finaid's `add-scholarship-program` + `award-scholarship-application` pattern is the authoritative institutional aid model for higher-ed use cases. Parent action remains for simple K-12/discount use; not used by educlaw-finaid. |

---

## 7. Test Strategy

### 7.1 Unit Tests (per domain)

#### financial_aid.py

| Test Scenario | Priority |
|--------------|----------|
| ISIR import creates correct C-flags for given flags | P0 |
| `review-isir` blocks packaging when unresolved C-flags exist | P0 |
| Verification request auto-generates correct document list for V1/V4/V5 groups | P0 |
| `complete-verification` requires all required documents accepted | P0 |
| COA `total_coa` correctly sums all components | P0 |
| `create-award-package` correctly calculates need = COA − SAI | P0 |
| Pell award correctly prorated for three_quarter/half_time/less_than_half enrollment | P0 |
| `offer-award-package` blocks when total aid > COA (overaward detection) | P0 |
| `offer-award-package` blocks when unresolved C-flags on ISIR | P0 |
| `disburse-award` blocks when `verification_complete = 0` | P0 |
| `disburse-award` blocks when `sap_status = 'FSP'` | P0 |
| `disburse-award` blocks when `mpn_signed = 0` for loan awards | P0 |
| `disburse-award` blocks when disbursement_date < term_start_date − 10 days | P0 |
| Disbursement GL entries balance (debit = credit) | P0 |
| `reverse-disbursement` creates exactly offsetting GL entries | P0 |
| SAP GPA component: passes when cumulative_gpa >= threshold | P0 |
| SAP pace component: passes when completion_rate >= 0.67 | P0 |
| SAP max timeframe: fails when projected > max_timeframe_credits | P0 |
| SAP status machine: SAT → FAW (first failure), not directly FSP | P0 |
| SAP status machine: FAW → FSP (second consecutive failure) | P0 |
| SAP status machine: Max timeframe exceeded → FSP directly (no FAW) | P0 |
| SAP status machine: FAP → SAT (meets SAP after appeal) | P0 |
| `run-sap-batch` processes all students with active packages for a term | P0 |
| R2T4 percent_completed = days_attended / payment_period_days | P0 |
| R2T4 earned_percent = 1.0 when percent_completed > 0.60 | P0 |
| R2T4 institution_return follows federal return order | P0 |
| R2T4 institution_return_due_date = determination_date + 45 days | P0 |
| R2T4 correctly identifies post-withdrawal disbursement when earned > disbursed | P0 |
| Aggregate loan limit check blocks packaging above NSLDS history + current | P1 |
| Annual loan limit check blocks packaging above statutory maximum | P1 |
| Pell LEU at 600%: Pell award blocked | P1 |
| `cancel-award-package` releases committed fund allocation amounts | P1 |
| Credit balance 14-day flag set when aid > charges | P1 |
| `import-pell-schedule` rejects duplicate pell_index for same aid year | P1 |
| `finaid_fund_allocation.available_amount` updates correctly on award commit/cancel | P1 |

#### scholarships.py

| Test Scenario | Priority |
|--------------|----------|
| `auto-match-scholarships` correctly filters by gpa_min, program_type, year_level | P1 |
| `auto-match-scholarships` respects max_recipients limit | P1 |
| `award-scholarship-application` creates award line in package; respects COA ceiling | P1 |
| `evaluate-scholarship-renewal` suspends when GPA below renewal_gpa_minimum | P1 |
| scholarship_program budget_remaining decrements correctly on award | P1 |
| Scholarship codes are unique per company | P1 |

#### work_study.py

| Test Scenario | Priority |
|--------------|----------|
| `assign-student-to-job` fails when no FWS award in student's package | P1 |
| `assign-student-to-job` fails when job is full (total_positions reached) | P1 |
| `submit-work-study-timesheet` fails for duplicate (assignment, pay_period_start) | P1 |
| `approve-work-study-timesheet` calculates earnings = hours_worked × pay_rate | P1 |
| `approve-work-study-timesheet` blocks approval when cumulative would exceed award_limit | P1 |
| `export-work-study-payroll` only exports approved, not-yet-exported timesheets | P1 |
| Community service job type tracked for 7% FWS allocation compliance | P2 |

#### loan_tracking.py

| Test Scenario | Priority |
|--------------|----------|
| `add-loan` validates annual loan limit not exceeded | P1 |
| `add-loan` validates aggregate loan limit against NSLDS data from ISIR | P1 |
| `update-mpn-status` clears MPN disbursement hold on linked award | P1 |
| `update-entrance-counseling` clears EC disbursement hold on linked award | P1 |
| `generate-cod-origination` includes all required COD Common Record fields | P1 |
| `get-loan-limits-status` correctly calculates annual remaining capacity | P1 |
| Parent PLUS loan links borrower_id to guardian, not student | P2 |

---

### 7.2 Integration Tests

| Test | Domains | Description |
|------|---------|-------------|
| Full aid lifecycle: ISIR → verify → package → accept → disburse | financial_aid | Happy path end-to-end |
| Scholarship added to package: auto-match + disburse | scholarships + financial_aid | Scholarship appears in disbursement |
| FWS award packaged → assignment → timesheets → payroll export | work_study + financial_aid | FWS employment lifecycle |
| Loan packaged → MPN signed → EC complete → disburse | loan_tracking + financial_aid | Loan disbursement gate |
| End-of-term SAP batch → FSP → appeal granted → next term disbursement | financial_aid | SAP suspension and reinstatement |
| Student withdrawal → R2T4 → GL reversal entries | financial_aid | Withdrawal compliance |
| New ISIR transaction with different SAI → recalculate package | financial_aid | ISIR update recalculation |
| Credit balance: aid > charges → flag → return within 14 days | financial_aid | Credit balance compliance |

---

### 7.3 Domain Invariants

| Invariant | Description |
|-----------|-------------|
| **No overaward** | `finaid_award_package.total_aid` must never exceed `finaid_cost_of_attendance.total_coa` |
| **Immutable disbursements** | `finaid_disbursement` records are never updated; corrections are new records with `disbursement_type='reversal'` |
| **Immutable professional judgments** | `finaid_professional_judgment` records are never updated after creation |
| **SAP status machine** | First failure must produce FAW; second consecutive failure produces FSP; max timeframe directly produces FSP |
| **Disbursement holds enforced** | Aid cannot be disbursed while any of: verification incomplete, C-flags unresolved, SAP=FSP, MPN unsigned, EC incomplete, enrollment below half-time |
| **Pell LEU cap** | Student cannot receive Pell if `pell_lifetime_eligibility_used >= 600%` |
| **45-day R2T4** | `institution_return_due_date = determination_date + 45 calendar days`; alert when approaching |
| **14-day credit balance** | `credit_balance_returned_date` must be within 14 days of `credit_balance_date` |
| **Loan annual limits** | Annual loan totals must not exceed statutory maximums by year/dependency status |
| **FERPA logging** | Every call to `get-isir`, `get-award-package`, `get-professional-judgment`, `get-verification-request` must write to `educlaw_data_access_log` with `data_category='financial'` |
| **Money precision** | All monetary fields use Python `Decimal` — never `float`; stored as TEXT with 2+ decimal places |
| **Append-only fund allocation** | Once funds are committed (`finaid_fund_allocation.committed_amount` incremented), only `cancel-award-package` decrements it |
| **R2T4 uniqueness** | Only one R2T4 calculation per student per term |
| **ISIR active transaction** | Only one ISIR per student per aid year may have `is_active_transaction=1` |

---

## 8. Estimated Complexity

| Domain | Tables | Actions | Estimated Lines | Priority |
|--------|--------|---------|-----------------|----------|
| `financial_aid` | 13 | 72 | ~5,500 | 1 |
| `scholarships` | 3 | 15 | ~1,200 | 2 |
| `work_study` | 3 | 18 | ~1,400 | 2 |
| `loan_tracking` | 1 | 10 | ~900 | 3 |
| **Totals** | **22 (new)** | **115** | **~9,000** | — |

### Complexity Notes

| Domain | Complexity Driver |
|--------|-----------------|
| `financial_aid` | SAP three-component status machine; R2T4 formula with federal return order; overaward detection logic; disbursement hold enforcement (multiple conditions); FERPA logging on all reads; GL integration on every disbursement |
| `scholarships` | Eligibility criteria matching (auto-match engine); budget tracking; integration with award packaging |
| `work_study` | Supervisor approval workflow; award limit enforcement; payroll export; community service tracking |
| `loan_tracking` | Annual/aggregate limit validation from ISIR NSLDS data; COD origination data generation; hold management |

### Implementation Phase Priority

| Phase | Items | Rationale |
|-------|-------|-----------|
| **Phase 1 (Core Compliance)** | `finaid_aid_year`, `finaid_pell_schedule`, `finaid_fund_allocation`, `finaid_cost_of_attendance`, `finaid_isir`, `finaid_isir_cflag`, `finaid_verification_request`, `finaid_verification_document`, `finaid_award_package`, `finaid_award`, `finaid_disbursement`, `finaid_sap_evaluation`, `finaid_sap_appeal`, `finaid_r2t4_calculation`, `finaid_professional_judgment` | Title IV compliance requirements — must ship first to be a viable product |
| **Phase 2 (Institutional Aid + Employment)** | `finaid_scholarship_program`, `finaid_scholarship_application`, `finaid_scholarship_renewal`, `finaid_work_study_job`, `finaid_work_study_assignment`, `finaid_work_study_timesheet` | Institutional features — significant value but not blocking for Title IV |
| **Phase 3 (Loan Tracking)** | `finaid_loan` | Loan records are important but COD XML export and aggregate tracking can follow Phase 1 |

---

## Appendix: Action Name Verification

All 115 action names confirmed unique against:
- **educlaw parent** (112 actions): No overlap — all finaid actions use `aid-year`, `isir`, `cflag`, `verification`, `award-package`, `award`, `disbursement`, `sap`, `r2t4`, `professional-judgment`, `scholarship-program`, `scholarship-application`, `scholarship-renewal`, `work-study-job`, `work-study-assignment`, `work-study-timesheet`, `loan` prefixes not present in educlaw
- **erpclaw-setup** actions: `initialize-database`, `add-company`, `add-user`, etc. — no overlap
- **erpclaw-gl** actions: `add-account`, `submit-journal-entry`, etc. — no overlap
- **erpclaw-selling** actions: `add-customer`, `create-sales-order`, etc. — no overlap
- **erpclaw-payments** actions: `receive-payment`, `reconcile-payment`, etc. — no overlap
- **erpclaw-hr** actions: `add-employee`, `submit-payroll`, etc. — no overlap

**Confirmed: ZERO naming conflicts with parent or foundation skills.**
