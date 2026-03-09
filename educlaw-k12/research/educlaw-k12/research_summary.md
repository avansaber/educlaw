# Research Summary: EduClaw K-12 Extensions

> **Product:** educlaw-k12
> **Display Name:** EduClaw K-12 Extensions
> **Parent:** educlaw
> **Research Date:** 2026-03-05

---

## Executive Summary

EduClaw K-12 Extensions fills the most compliance-sensitive gap in the parent EduClaw product: the four domains that make K-12 schools fundamentally different from higher education institutions. Discipline management, student health records, special education (IDEA/IEP), and grade promotion are legally mandated, operationally critical, and currently served by expensive standalone commercial systems that small and private schools cannot afford.

The opportunity is clear: **no open-source system combines all four domains in a single ERP-integrated package.** EduClaw K-12 is positioned to be the first.

This is a **high-complexity, high-compliance** build. Special education is particularly complex — the IEP pipeline requires 9 tables and strict IDEA timeline enforcement. The overall build adds 22 new tables and an estimated 65–79 actions.

---

## 1. What We Are Building

### Four Extension Domains

| Domain | Purpose | Compliance Driver | Complexity |
|--------|---------|------------------|------------|
| **Discipline** | Incident documentation, consequences, PBIS tracking, MDR workflow | FERPA, IDEA §615, state reporting | Medium |
| **Health Records** | Nurse visits, medications, immunization compliance | State Immunization Laws, FERPA, HIPAA-adjacent | Medium |
| **Special Education** | IEP/504 lifecycle: referral → evaluation → goals → service delivery → progress monitoring | IDEA Part B, FERPA, 34 CFR 300 | **HIGH** |
| **Grade Promotion** | End-of-year promotion/retention decisions with team review and parent notification | State education laws, IDEA (IDEA students need special consideration) | Low-Medium |

### Parent Reuse
The parent EduClaw product provides:
- `educlaw_student` — anchor entity for all K-12 records
- `educlaw_guardian` + `educlaw_student_guardian` — parent notification contacts
- `educlaw_data_access_log` — FERPA logging (health + discipline already defined)
- `educlaw_consent_record` — parental consent tracking
- `educlaw_academic_year` + `educlaw_academic_term` — IEP timeline anchors
- `educlaw_notification` — notification delivery pipeline
- `educlaw_instructor` — IEP team members (teacher role)

**Key parent gap:** The `data_access_log.data_category` CHECK constraint needs `'special_education'` added. Coordinate with parent team.

---

## 2. Recommended V1 Scope

### Include in V1 (Core Compliance)

**Discipline:**
- Incident recording (header + per-student involvement)
- Consequence/action tracking
- Guardian notification workflow
- IDEA 10-day suspension / MDR trigger alert
- MDR record keeping
- Basic discipline history report
- PBIS positive behavior recognition (simple)

**Health Records:**
- Student health profile (allergies, conditions, physician, emergency info)
- Office visit / nurse visit log
- Student medication catalog + administration log
- Immunization records + waiver management
- Immunization compliance check by grade level
- State immunization compliance report (aggregate by grade/vaccine)
- Provisional enrollment tracking

**Special Education:**
- Full referral → evaluation → eligibility → IEP pipeline
- IEP goals with measurable criteria
- Special education services (type, frequency, planned minutes)
- Service delivery session log (actual minutes)
- IEP progress notes per reporting period
- IEP team members documentation
- Annual review and triennial re-evaluation alerts
- Transition plan (age 16+ required fields)
- Section 504 plan (simplified)
- Service compliance report (planned vs. actual minutes)

**Grade Promotion:**
- Promotion review record per student per year
- Teacher and counselor recommendation workflow
- Promotion decision record (immutable)
- Parent notification tracking
- Batch grade-level advancement action
- At-risk identification report
- Intervention plan creation

### Defer to V2

- State-specific discipline incident codes (CEDS mapping) — manual codes sufficient for v1
- IIS (state immunization registry) API sync — manual entry first
- Title IX enhanced access controls — basic flag is sufficient for v1
- MDR FBA/BIP structured workflow — notes field covers v1
- Multi-language IEP progress reports
- Predictive at-risk AI scoring
- Medicaid billing for special education services
- Special education state reporting API integration
- Custom immunization schedule templates per state

---

## 3. Key Technical Decisions

### 3.1 IEP Versioning Strategy
**Decision:** IEPs are versioned by creating a new record (not in-place editing). Prior IEP versions move to `status = 'superseded'`. Amendment creates `is_amendment = 1` flag with `parent_iep_id` link.

**Rationale:** IEPs are legally binding documents — they must be preserved exactly as signed. This is the approach used by Frontline Education. In-place editing would destroy audit trail.

### 3.2 Discipline Incident Architecture
**Decision:** Header + child record pattern. One `educlaw_k12_discipline_incident` per event; one `educlaw_k12_discipline_student` per involved student; one or more `educlaw_k12_discipline_action` per student.

**Rationale:** Matches PowerSchool's proven architecture. Allows multi-student incidents (fights) with independent consequences per student. Supports IDEA MDR tracking at the per-student level.

### 3.3 Immunization Data Model
**Decision:** Individual records per dose (not per vaccine family). CVX codes stored. Source field distinguishes manual entry from future IIS sync.

**Rationale:** Multiple doses per vaccine, each with different lot numbers and dates. CVX codes enable future state IIS integration without data migration. Magnus Health and SchoolDoc both use this pattern.

### 3.4 Section 504 vs. IEP
**Decision:** 504 plans use a simpler flat structure (accommodations as JSON array) rather than the full goal/service/progress pipeline of IEPs.

**Rationale:** 504 plans are less formal than IEPs and have lighter requirements. Building a full pipeline for 504s would be over-engineering. JSON array accommodations are sufficient and more flexible.

### 3.5 Grade Promotion Batch Action
**Decision:** `batch-promote-grade` action reads all `promotion_decision.decision = 'promote'` records for a given academic year and increments `educlaw_student.grade_level`.

**Rationale:** Grade level advancement is the critical year-end action. It must be atomic (all-or-nothing), auditable (promotion decisions already recorded), and reversible only via amendment (which requires a new decision record).

### 3.6 FERPA Logging for Special Education
**Decision:** K-12 must log `data_category = 'special_education'` for IEP record access. This requires adding `'special_education'` to the CHECK constraint in the parent's `educlaw_data_access_log` table.

**Rationale:** IDEA has its own confidentiality provisions (34 CFR 300.610–300.626) that go beyond FERPA baseline. Separate category is necessary for compliance reporting — IDEA audits ask specifically about IEP record access logs.

**Action required:** File issue with educlaw parent team to add `special_education` to `data_access_log.data_category` CHECK constraint.

---

## 4. Competitive Differentiation

| Differentiator | vs. Commercial (PowerSchool, IC) | vs. Open Source (OpenSIS, Fedena) |
|---------------|--------------------------------|----------------------------------|
| Cost | **Free** (open source) vs. $15–40/student/year | Comparable (both free) |
| All-in-one integration | Same ERP as enrollment, grades, fees, attendance | **Unique** — no open source competitor integrates all 4 domains + ERP |
| IDEA compliance | Comparable features; PowerSchool/IC have state reporting APIs | **Far superior** — no open source has real IEP compliance pipeline |
| Health records | Commercial has SIS-native health; EduClaw K-12 matches | **Far superior** — no open source competitor has real health module |
| Immunization tracking | Comparable | **Far superior** |
| Accounting integration | None (SIS only) | **Unique** — EduClaw parent has full double-entry GL |
| AI-native interface | Traditional UI; AI features being added | **Unique** — conversational interface for all operations |

---

## 5. Compliance Risk Assessment

| Risk | Severity | Mitigation |
|------|---------|-----------|
| Missing IEP annual review alerts | HIGH — IDEA violation | Auto-calculate `annual_review_due_date = iep_start_date + 365 days`; alert at 30 days |
| Missing 60-day evaluation timeline | HIGH — IDEA violation | Auto-calculate `evaluation_deadline = consent_date + 60 days`; alert at 45 days |
| Immunization non-compliance not flagged | HIGH — state law | Run compliance check on enrollment and on-demand; provisional_enrollment_end_date |
| MDR trigger missed for IDEA students | HIGH — IDEA violation | Auto-sum suspension days per student per year; alert at 8 days |
| FERPA health records improperly shared | HIGH — FERPA violation | Role-based access to health profile; FERPA log on all reads |
| IEP records not preserved on amendment | MEDIUM | No in-place editing; version chain required |
| Parent notification deadline missed (promotion) | MEDIUM — state law | Alert at configurable threshold (default: 30 days before May 1) |
| Special ed record retention | MEDIUM | Track `exit_date`; compute destruction-eligible date |

---

## 6. Build Complexity Estimates

| Domain | Tables | Actions | Complexity | Notes |
|--------|--------|---------|-----------|-------|
| Discipline | 4 | 12–15 | Medium | MDR logic is most complex piece |
| Health Records | 6 | 18–22 | Medium | Immunization compliance logic requires grade-level rules |
| Special Education | 9 | 25–30 | **HIGH** | IEP versioning, timeline alerts, service compliance |
| Grade Promotion | 3 | 10–12 | Low-Medium | Batch promote action needs care |
| **Total** | **22** | **65–79** | **HIGH overall** | Largest sub-vertical planned |

**Recommended build order:**
1. **Health Records** first — simpler, compliance-critical, delivers immediate value
2. **Grade Promotion** second — smaller, builds on student data
3. **Discipline** third — medium complexity; MDR links to special ed
4. **Special Education** last — most complex; benefits from discipline MDR being ready

---

## 7. Data Architecture Highlights

### New Tables: 22

| Domain | Tables |
|--------|--------|
| Discipline | `educlaw_k12_discipline_incident`, `educlaw_k12_discipline_student`, `educlaw_k12_discipline_action`, `educlaw_k12_manifestation_review` |
| Health Records | `educlaw_k12_health_profile`, `educlaw_k12_health_visit`, `educlaw_k12_student_medication`, `educlaw_k12_medication_log`, `educlaw_k12_immunization`, `educlaw_k12_immunization_waiver` |
| Special Education | `educlaw_k12_sped_referral`, `educlaw_k12_sped_evaluation`, `educlaw_k12_sped_eligibility`, `educlaw_k12_iep`, `educlaw_k12_iep_goal`, `educlaw_k12_iep_service`, `educlaw_k12_iep_service_log`, `educlaw_k12_iep_team_member`, `educlaw_k12_iep_progress`, `educlaw_k12_504_plan` |
| Grade Promotion | `educlaw_k12_promotion_review`, `educlaw_k12_promotion_decision`, `educlaw_k12_intervention_plan` |

### Immutable Tables (no `updated_at`)
Following parent's convention for audit-critical records:
- `educlaw_k12_discipline_student` — involvement in incident is immutable
- `educlaw_k12_health_visit` — office visit logs
- `educlaw_k12_medication_log` — medication administration
- `educlaw_k12_immunization` — vaccine records
- `educlaw_k12_sped_evaluation` — evaluation findings
- `educlaw_k12_sped_eligibility` — eligibility determination
- `educlaw_k12_iep_goal` — IEP goals (new IEP version for changes)
- `educlaw_k12_iep_service` — mandated services
- `educlaw_k12_iep_service_log` — service delivery sessions
- `educlaw_k12_iep_team_member` — meeting participation
- `educlaw_k12_iep_progress` — progress notes
- `educlaw_k12_promotion_decision` — promotion/retention decision

---

## 8. Integration Dependencies

| Integration Point | Type | Notes |
|-----------------|------|-------|
| `educlaw_student.grade_level` | Read + Write | Promotion workflow reads current; batch-promote writes new value |
| `educlaw_student.status` | Write | Discipline may update to `suspended` or `expelled` |
| `educlaw_data_access_log` | Write | Every health/discipline/sped read must log FERPA access |
| `educlaw_guardian` + `educlaw_student_guardian` | Read | Discipline and health notification contacts |
| `educlaw_notification` | Write | New notification types for discipline, health, IEP alerts |
| `educlaw_academic_year` + `educlaw_academic_term` | Read | Timeline anchors for IEP deadlines and promotion reviews |
| `educlaw_instructor` | Read | IEP team member lookup |
| `employee` (erpclaw-hr) | Read | Non-teacher IEP team members |
| `company` (erpclaw-setup) | Read | company_id on all tables |

---

## 9. Recommended Action Naming Convention

```
# Discipline
add-discipline-incident        update-discipline-incident     close-discipline-incident
add-discipline-student         add-discipline-action          add-manifestation-review
get-discipline-history         list-discipline-incidents      notify-guardians-discipline
generate-discipline-report     get-cumulative-suspension-days add-pbis-recognition

# Health Records
add-health-profile             update-health-profile          get-health-profile
add-office-visit               list-office-visits             get-office-visit
add-student-medication         update-student-medication      list-student-medications
log-medication-admin           list-medication-logs
add-immunization               add-immunization-waiver        update-immunization-waiver
get-immunization-record        check-immunization-compliance  generate-immunization-report

# Special Education
create-sped-referral           update-sped-referral           get-sped-referral
add-sped-evaluation            record-sped-eligibility
add-iep                        update-iep                     get-active-iep            get-iep
add-iep-goal                   add-iep-service                log-iep-service-session
add-iep-team-member            record-iep-progress
generate-iep-progress-report   get-service-compliance-report
add-504-plan                   update-504-plan                get-active-504-plan
list-iep-deadlines             list-reevaluation-due

# Grade Promotion
create-promotion-review        update-promotion-review        list-promotion-reviews
submit-promotion-decision      notify-promotion-decision
batch-promote-grade            create-intervention-plan       update-intervention-plan
generate-promotion-report      identify-at-risk-students
```

---

## 10. Key Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| **Scope creep in special ed** — IEP is infinitely extensible | Strictly limit to 13 IDEA-required IEP components. No custom fields in v1. |
| **State law variation** in immunization requirements | Build rule engine as configurable JSON (grade → vaccine → required doses) rather than hardcoded. Default rules based on common multi-state requirements. |
| **Parent schema change** required (special_education log category) | Coordinate with educlaw maintainers; alternatively, check for existing category and map to closest fit in v1 |
| **Complex MDR logic** — cumulative suspension day counting | Count per student, per academic year, across all incidents. Store running total on `educlaw_k12_discipline_student.cumulative_suspension_days_ytd` |
| **IEP document complexity** — some fields are rich text, not structured | Use TEXT fields for narrative sections (PLAAFP, goals) in v1. Structured goal tracking uses dedicated `educlaw_k12_iep_goal` table. |
| **Grade promotion batch action** could run twice | Idempotency check: if `educlaw_student.grade_level` already matches next year's expected level, skip. |

---

## 11. Suggested File Structure

```
educlaw-k12/
├── educlaw-k12.yaml
├── SKILL.md
├── init_db.py                    (~22 tables)
├── scripts/
│   ├── db_query.py               (router)
│   ├── discipline.py             (incident, actions, MDR, PBIS)
│   ├── health_records.py         (profile, visits, medications, immunizations)
│   ├── special_education.py      (referral, evaluation, IEP, 504, progress)
│   └── grade_promotion.py        (review, decision, batch promote)
├── research/
│   └── educlaw-k12/              (these files)
├── plan/
│   └── educlaw_k12_plan.md       (generated by planner agent)
└── tests/
    └── (pytest test suite)
```
