---
name: educlaw-finaid
version: 1.0.0
description: >
  Federal, state, and institutional financial aid management with Title IV compliance.
  ISIR processing, SAP evaluation, R2T4 calculations, award packaging, disbursements,
  COD origination, scholarships, work-study, and loan tracking. 116 actions.
author: AvanSaber
homepage: https://github.com/avansaber/educlaw
source: https://github.com/avansaber/educlaw
tier: 4
category: education
requires: [erpclaw, educlaw]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [educlaw, finaid, financial-aid, title-iv, isir, sap, r2t4, pell, scholarship, work-study, loan, fafsa]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# EduClaw Financial Aid

Federal, state, and institutional financial aid management. Full Title IV lifecycle
from ISIR import through disbursement, SAP evaluation, R2T4 return calculations,
professional judgment, COD origination, scholarships, work-study, and loan tracking.

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Fully offline**: No external API calls, no telemetry, no cloud dependencies
- **FERPA compliant**: Student financial data access is logged
- **Title IV compliance**: ISIR, SAP, R2T4, and COD records follow federal regulations

## Quick Start

```bash
python3 db_query.py --action finaid-add-aid-year --aid-year-code "2025-2026" \
  --start-date 2025-07-01 --end-date 2026-06-30 --pell-max-award 7395 --company-id <id>
python3 db_query.py --action finaid-import-isir --student-id <id> --aid-year-id <id> \
  --transaction-number 1 --receipt-date 2025-02-15 --sai -1500
python3 db_query.py --action finaid-create-award-package --student-id <id> \
  --aid-year-id <id> --isir-id <id> --cost-of-attendance-id <id>
```

## Tier 1 -- Aid Year & Fund Setup (11 actions)

| Action | Description |
|--------|-------------|
| `finaid-add-aid-year` | Create an aid year with Pell max award |
| `finaid-update-aid-year` | Update aid year dates and parameters |
| `finaid-activate-aid-year` | Activate aid year for packaging |
| `finaid-get-aid-year` | Get aid year details |
| `finaid-list-aid-years` | List all aid years |
| `finaid-import-pell-schedule` | Import Pell disbursement schedule |
| `finaid-list-pell-schedule` | List Pell schedule rows |
| `finaid-add-fund-allocation` | Create fund allocation (Pell, SEOG, etc.) |
| `finaid-update-fund-allocation` | Update allocation amounts |
| `finaid-get-fund-allocation` | Get fund details |
| `finaid-list-fund-allocations` | List fund allocations for aid year |

## Cost of Attendance (5 actions)

| Action | Description |
|--------|-------------|
| `finaid-add-cost-of-attendance` | Define COA by enrollment/living status |
| `finaid-update-cost-of-attendance` | Update COA components |
| `finaid-delete-cost-of-attendance` | Remove COA record |
| `finaid-get-cost-of-attendance` | Get COA details |
| `finaid-list-cost-of-attendance` | List COA records for aid year |

## ISIR Processing (8 actions)

| Action | Description |
|--------|-------------|
| `finaid-import-isir` | Import ISIR with SAI, dependency, C-flags |
| `finaid-complete-isir-review` | Mark ISIR as reviewed |
| `finaid-update-isir` | Update ISIR fields after correction |
| `finaid-get-isir` | Get ISIR details |
| `finaid-list-isirs` | List ISIRs for student/aid year |
| `finaid-add-isir-cflag` | Add C-flag comment code |
| `finaid-complete-isir-cflag` | Resolve a C-flag |
| `finaid-list-isir-cflags` | List C-flags for an ISIR |

## Verification (8 actions)

| Action | Description |
|--------|-------------|
| `finaid-create-verification-request` | Create verification with required docs |
| `finaid-add-verification-document` | Add document to verification request |
| `finaid-update-verification-document` | Update document submission status |
| `finaid-update-verification-request` | Update verification request |
| `finaid-complete-verification` | Mark verification complete |
| `finaid-get-verification-request` | Get verification details |
| `finaid-list-verification-requests` | List verification requests |
| `finaid-list-verification-documents` | List documents for request |

## Award Packaging (13 actions)

| Action | Description |
|--------|-------------|
| `finaid-create-award-package` | Create award package for student |
| `finaid-update-award-package` | Update package details |
| `finaid-submit-award-offer` | Offer package to student |
| `finaid-cancel-award-package` | Cancel an award package |
| `finaid-get-award-package` | Get package details with awards |
| `finaid-list-award-packages` | List packages for student/aid year |
| `finaid-add-award` | Add individual award to package |
| `finaid-update-award` | Update award amounts |
| `finaid-accept-award` | Student accepts an award |
| `finaid-deny-award` | Student declines an award |
| `finaid-delete-award` | Remove unapproved award |
| `finaid-get-award` | Get award details |
| `finaid-list-awards` | List awards in package |

## Disbursements (5 actions)

| Action | Description |
|--------|-------------|
| `finaid-record-award-disbursement` | Disburse funds for an award |
| `finaid-cancel-disbursement` | Reverse a disbursement |
| `finaid-record-credit-balance-return` | Mark credit balance returned to student |
| `finaid-get-disbursement` | Get disbursement details |
| `finaid-list-disbursements` | List disbursements for package/award |

## SAP -- Satisfactory Academic Progress (10 actions)

| Action | Description |
|--------|-------------|
| `finaid-generate-sap-evaluation` | Evaluate SAP for a student |
| `finaid-generate-sap-batch` | Batch SAP evaluation |
| `finaid-apply-sap-override` | Override SAP status |
| `finaid-get-sap-evaluation` | Get SAP evaluation details |
| `finaid-list-sap-evaluations` | List SAP evaluations |
| `finaid-submit-sap-appeal` | Submit SAP appeal with academic plan |
| `finaid-complete-sap-appeal` | Approve or deny SAP appeal |
| `finaid-update-sap-appeal` | Update appeal details |
| `finaid-get-sap-appeal` | Get appeal details |
| `finaid-list-sap-appeals` | List SAP appeals |

## R2T4 -- Return of Title IV (7 actions)

| Action | Description |
|--------|-------------|
| `finaid-create-r2t4` | Create R2T4 calculation for withdrawn student |
| `finaid-generate-r2t4-calculation` | Execute R2T4 calculation |
| `finaid-approve-r2t4` | Approve R2T4 result |
| `finaid-record-r2t4-return` | Record institutional return |
| `finaid-record-r2t4-return-disbursement` | Record return disbursement |
| `finaid-get-r2t4` | Get R2T4 calculation details |
| `finaid-list-r2t4s` | List R2T4 calculations |

## COD -- Common Origination & Disbursement (4 actions)

| Action | Description |
|--------|-------------|
| `finaid-generate-cod-origination` | Generate COD origination record |
| `finaid-update-cod-origination-status` | Update origination status |
| `finaid-generate-cod-export` | Generate COD export batch |
| `finaid-update-cod-status` | Update COD response status |

## Professional Judgment (4 actions)

| Action | Description |
|--------|-------------|
| `finaid-add-professional-judgment` | Create PJ request with documentation |
| `finaid-approve-professional-judgment` | Approve PJ with supervisor review |
| `finaid-get-professional-judgment` | Get PJ details |
| `finaid-list-professional-judgments` | List PJ requests |

## Scholarships (15 actions)

| Action | Description |
|--------|-------------|
| `finaid-add-scholarship-program` | Create scholarship program |
| `finaid-update-scholarship-program` | Update program criteria |
| `finaid-terminate-scholarship-program` | Deactivate program |
| `finaid-get-scholarship-program` | Get program details |
| `finaid-list-scholarship-programs` | List scholarship programs |
| `finaid-submit-scholarship-application` | Submit student application |
| `finaid-complete-scholarship-review` | Review application |
| `finaid-approve-scholarship-application` | Award scholarship to applicant |
| `finaid-deny-scholarship-application` | Deny application |
| `finaid-update-scholarship-application` | Update application |
| `finaid-get-scholarship-application` | Get application details |
| `finaid-list-scholarship-applications` | List applications |
| `finaid-generate-scholarship-renewal` | Evaluate renewal eligibility |
| `finaid-list-scholarship-renewals` | List renewal evaluations |
| `finaid-generate-scholarship-matches` | Auto-match students to programs |

## Work-Study (18 actions)

| Action | Description |
|--------|-------------|
| `finaid-add-work-study-job` | Create work-study position |
| `finaid-update-work-study-job` | Update job details |
| `finaid-terminate-work-study-job` | Close position |
| `finaid-get-work-study-job` | Get job details |
| `finaid-list-work-study-jobs` | List work-study positions |
| `finaid-assign-student-to-job` | Assign student to position |
| `finaid-update-work-study-assignment` | Update assignment |
| `finaid-terminate-work-study-assignment` | End assignment |
| `finaid-get-work-study-assignment` | Get assignment details |
| `finaid-list-work-study-assignments` | List assignments |
| `finaid-submit-work-study-timesheet` | Submit timesheet |
| `finaid-approve-work-study-timesheet` | Approve timesheet |
| `finaid-deny-work-study-timesheet` | Reject timesheet |
| `finaid-update-work-study-timesheet` | Update timesheet |
| `finaid-get-work-study-timesheet` | Get timesheet details |
| `finaid-list-work-study-timesheets` | List timesheets |
| `finaid-get-work-study-earnings-summary` | Get earnings summary |
| `finaid-generate-payroll-export` | Export payroll data |

## Loan Tracking (10 actions)

| Action | Description |
|--------|-------------|
| `finaid-add-loan` | Track a student loan |
| `finaid-update-loan` | Update loan details |
| `finaid-get-loan` | Get loan details |
| `finaid-list-loans` | List student loans |
| `finaid-get-loan-limits-status` | Check aggregate loan limits |
| `finaid-update-mpn-status` | Update MPN status |
| `finaid-update-entrance-counseling` | Update entrance counseling status |
| `finaid-update-exit-counseling` | Update exit counseling status |
| `finaid-generate-cod-origination` | Generate COD loan origination |
| `finaid-update-cod-origination-status` | Update COD origination response |

## Compliance

- **Title IV**: Full ISIR to packaging to disbursement to R2T4 lifecycle
- **FAFSA**: SAI-based Pell calculation, C-flag resolution, verification
- **SAP**: Quantitative + qualitative + pace evaluation with appeal workflow
- **R2T4**: 34 CFR 668.22 compliant percentage-based calculations
- **COD**: Origination and disbursement record generation
- **FERPA**: Student financial data access logging
