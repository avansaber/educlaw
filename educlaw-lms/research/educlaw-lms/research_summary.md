# EduClaw LMS Integration — Research Summary

**Product:** educlaw-lms
**Parent:** educlaw (112 actions, 32 tables, 8 domains)
**Research Date:** 2026-03-05
**Domains:** lms_sync, assignments, course_materials, online_gradebook

---

## Executive Summary

educlaw-lms is a sub-vertical that bridges EduClaw's authoritative Student Information System with external Learning Management Systems (Canvas, Moodle, Google Classroom). It solves the universal problem of **data silos between SIS and LMS** — a problem that affects virtually every school using a modern LMS for digital assignment delivery.

The LMS integration market represents a critical capability gap in the current educlaw offering. The parent's research explicitly flagged LMS integration as P2 priority sub-vertical with an estimated ~25-30 hour build and ~8 tables. This research deepens and refines that estimate: **7 new tables, ~23 actions, ~35-45 hours to build** — and reveals significant compliance and architectural complexity that the initial estimate underweighted.

**Key finding:** The introduction of external network calls (LMS API sync) is the most architecturally significant change from base EduClaw's offline-only design. Every design decision must account for: (1) network failure/retry, (2) FERPA disclosure logging, (3) credential encryption, (4) rate limiting, and (5) conflict resolution when SIS and LMS data diverge.

---

## Market Context

| Metric | Value |
|--------|-------|
| LMS Market Size (2025) | $28.6–$32.7 billion |
| LMS Market CAGR (2025-2035) | 18.1–20.2% |
| LMS Projected Market (2035) | $172.4 billion |
| Canvas Higher Ed Market Share (NA) | 39% |
| Google Classroom K-12 dominance | #1 by volume (free) |
| Moodle Global Deployments | Largest by instance count; #1 Europe, Latin America |
| Schools using external LMS | ~80%+ of US higher ed; majority of K-12 |

**Implication:** Nearly every EduClaw customer also uses an LMS. Without educlaw-lms, schools must manually transfer rosters and grades between systems — the #1 administrative pain point in K-12 and higher ed operations.

---

## Recommended Scope

### v1 — Core LMS Integration (This Build)

| Domain | Tables | Actions | Priority | Complexity |
|--------|--------|---------|----------|------------|
| **LMS Sync** | 4 (connection, course_mapping, user_mapping, sync_log) | ~8 | P0 (Critical) | High |
| **Assignments** | 1 (assignment_mapping) | ~5 | P1 (Important) | Medium |
| **Online Gradebook** | 1 (grade_sync) | ~5 | P0 (Critical) | High |
| **Course Materials** | 1 (course_material) | ~5 | P2 (Nice to have) | Low |
| **Total** | **7** | **~23** | | |

### LMS Platform Priority (v1)

| Priority | Platform | Why |
|----------|----------|-----|
| **P0** | Canvas (Instructure) | 39% higher ed; best API; most EduClaw higher-ed customers |
| **P0** | Google Classroom | Dominant K-12; free; most EduClaw K-12 customers |
| **P1** | Moodle | Open-source community alignment; large global install base |
| **P1** | OneRoster CSV Export | Lowest-effort path for any other compliant LMS |
| **v2** | D2L Brightspace | Growing but smaller K-12 presence |
| **v2** | Schoology | PowerSchool-native; less relevant for EduClaw customers |

### Deferred to v2

| Feature | Reason for Deferral |
|---------|---------------------|
| LTI 1.3 Tool Launch | Requires additional OAuth infrastructure; high complexity |
| SCORM/xAPI completion tracking | Specialized content standards; requires LRS |
| Automatic/scheduled sync | Requires background job runner; v1 uses manual trigger |
| D2L Brightspace integration | Smaller K-12 presence; defer |
| Schoology integration | PowerSchool-exclusive LMS; low relevance |
| SSO / Single Sign-On | Significant identity management complexity |
| Real-time webhook-based sync | Requires persistent listener; manual trigger covers v1 |
| AI-powered grade suggestions | v2 analytics add-on |
| Discussion/engagement data sync | LMS engagement data is LMS-native; not SIS territory |

---

## Key Differentiators

### 1. FERPA-First LMS Sync (Primary Differentiator)
No competitor (OpenSIS, Infinite Campus, or even PowerSchool) automatically logs each LMS sync as a FERPA disclosure event. educlaw-lms does — every roster push writes to `educlaw_data_access_log` with `access_type = 'disclosure'`. This makes audits trivial and demonstrates compliance commitment.

### 2. Multi-LMS, Single Config
A school can connect Canvas for high school AND Google Classroom for middle school in a single EduClaw instance. OpenSIS supports only one LMS type at a time. Infinite Campus uses a separate sync tool (IC Flow).

### 3. Explicit Grade Conflict Resolution
When LMS grade ≠ SIS grade, educlaw-lms surfaces the conflict explicitly for admin review rather than silently overwriting. Grade immutability (submitted grades) is enforced even during LMS sync — competitors routinely overwrite submitted grades.

### 4. Open Source + Standards-First
Canvas direct API, Google Classroom direct API, Moodle Web Services, and OneRoster CSV — all in one open-source package. No per-seat sync fees, no proprietary connectors.

### 5. DPA + COPPA Compliance Gate
educlaw-lms blocks ALL sync if `has_dpa_signed = 0`. It blocks COPPA-flagged student sync if `is_coppa_verified = 0`. These are hard gates, not warnings — reducing legal risk for the school.

---

## Competitive Positioning

```
                   Open Source         Commercial
                   ──────────          ──────────
Multi-LMS Support: educlaw-lms ★      Infinite Campus
                   OpenSIS (partial)  PowerSchool (Schoology-tied)

FERPA-Logged Sync: educlaw-lms ★      (no competitor does this)

Grade Conflict UI: educlaw-lms ★      Blackbaud (explicit policy)

COPPA Guard:       educlaw-lms ★      (no open-source competitor)

Cost:              Free (open source) $5-20/student/year for SIS
```

---

## Architecture Decisions

### 1. Adapter Pattern for Multi-LMS (Recommended)
```
scripts/lms_sync.py (router)
    ↓
scripts/adapters/
    canvas.py          ← Canvas REST API calls
    moodle.py          ← Moodle Web Services calls
    google_classroom.py ← Google Classroom API calls
    oneroster_csv.py   ← OneRoster CSV generation
```
Each adapter implements a standard interface: `sync_course(section)`, `sync_user(student)`, `sync_enrollment(enrollment)`, `push_assignment(assessment)`, `pull_grades(section)`.

### 2. Credentials Must Be Encrypted at Rest
LMS OAuth secrets and API tokens stored in SQLite MUST be encrypted. Use a school-specific encryption key stored in environment variable `EDUCLAW_LMS_ENCRYPTION_KEY`. Never log or display plaintext credentials.

### 3. DPA Gate (Hard Block, Not Warning)
```python
def check_dpa(connection):
    if not connection.has_dpa_signed:
        return error("E_DPA_REQUIRED: Cannot sync without signed Data Processing Agreement")
    if student.is_coppa_applicable and not connection.is_coppa_verified:
        return error("E_COPPA_UNVERIFIED: Cannot sync under-13 student to unverified LMS")
```

### 4. SIS Is Source of Truth for Enrollment; LMS Is Source of Truth for Grades
- Roster always flows SIS → LMS (enrollment changes are managed in EduClaw)
- Grades flow LMS → SIS by default (instructors grade in LMS; SIS is official record)
- Exception: manually entered SIS grades (or submitted grades) always win on conflict

### 5. Sync Runs Are Transactional
Each `sync-courses` or `pull-grades` run creates an `educlaw_lms_sync_log` entry at the start. All records in the run are associated with that log. If the run fails midway, partial results are preserved (not rolled back) — the log shows which records succeeded and which failed, enabling targeted re-sync.

### 6. Google Classroom — No LTI; Handle Invitation Flow
Google Classroom does not support LTI or OneRoster. educlaw-lms must use the Google Classroom API directly. Key complication: students must accept an "invitation" to join a class (unlike Canvas where enrollment is immediate). The sync code must handle `PENDING` invitation state.

### 7. Cannot Read Overall Course Grade from Google Classroom
Google Classroom API cannot return or set the overall course grade. educlaw-lms must calculate the weighted course grade from individual `studentSubmissions` scores pulled per assignment — same calculation logic as EduClaw's `generate-section-grade` but applied to LMS-pulled data.

---

## Technical Risks and Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Network failures during sync** | HIGH | All API calls wrapped in retry logic (3 attempts, exponential backoff). Sync run marked `completed_with_errors`, not `failed`, if some records succeed. |
| **LMS rate limiting** | HIGH | Canvas: per-token throttle. Implement queue with 100ms delay between calls. Batch where API supports it. Use separate API token for educlaw-lms. |
| **Credential expiry (OAuth tokens)** | HIGH | Canvas OAuth tokens expire. Implement refresh_token flow. Store refresh_token alongside access_token (both encrypted). Alert on expiry. |
| **Google Classroom invitation acceptance** | MEDIUM | Students must accept invite. Track `PENDING` state in `lms_user_mapping.sync_status`. Re-check invitation state on next sync. Alert admin if students don't accept within 48 hours. |
| **Grade overwrite on submitted grades** | HIGH | Check `is_grade_submitted = 1` before any grade write. If locked → set `conflict_type = 'submitted_grade_locked'`. Never auto-apply. Always route through amendment workflow. |
| **Moodle version fragmentation** | MEDIUM | Test against Moodle 3.11+ (LTI 1.3 support). Document minimum Moodle version (3.9+ for core Web Services). Gracefully degrade if endpoint missing. |
| **COPPA — under-13 LMS sync** | HIGH | `is_coppa_applicable = 1` → hard block unless `is_coppa_verified = 1`. Log all COPPA decisions in sync_log. |
| **Credential storage security** | HIGH | Never store plaintext in SQLite. Use `EDUCLAW_LMS_ENCRYPTION_KEY` env var. Log warning if env var not set. |
| **ok() status collision** | HIGH | Use `sync_status`, `connection_status`, `mapping_status` — never bare `status` in response dicts. |
| **getattr argparse bug** | HIGH | `getattr(args, "f", None) or "default"` pattern throughout. |
| **Concurrent sync runs** | LOW | SQLite handles concurrency adequately for v1 (single-school, infrequent sync). If race condition occurs, second run detects existing RUNNING status and aborts with message. |

---

## Estimated Complexity

| Component | Effort | Notes |
|-----------|--------|-------|
| Schema (init_db.py extension) | 1-2 hours | 7 new tables, extends parent schema |
| LMS Connection management | 2-3 hours | add/update/test connection; credential encryption |
| Canvas adapter | 4-5 hours | OAuth flow, course/user/enrollment/grade endpoints, rate limiting |
| Google Classroom adapter | 4-5 hours | OAuth, invitation flow, manual grade calculation, no LTI |
| Moodle adapter | 3-4 hours | Token auth, web service functions, version handling |
| OneRoster CSV export | 2-3 hours | 8 CSV files per OneRoster 1.1 spec |
| Grade pull + conflict detection | 4-5 hours | Pull → compare → stage → resolve workflow |
| Assignment sync | 2-3 hours | Push assessments to LMS, pull grade schema |
| Course materials | 1-2 hours | Simple CRUD + optional LMS file upload |
| FERPA logging (all actions) | 1-2 hours | Add disclosure/pull log to every sync action |
| SKILL.md | 1 hour | Action manifest, tiers, descriptions |
| Tests (pytest) | 8-10 hours | ~80-120 tests; mock LMS API responses |
| **Total** | **~35-45 hours** | Excludes research/planning already done |

---

## Data Model Summary

| Table | Rows (est. per term) | Purpose |
|-------|---------------------|---------|
| `educlaw_lms_connection` | 1-3 per school | LMS platform configs |
| `educlaw_lms_course_mapping` | = sections per term (30-200) | Section ↔ LMS course |
| `educlaw_lms_user_mapping` | = students + instructors (100-5000) | User crossref |
| `educlaw_lms_assignment_mapping` | = assessments (500-2000) | Assignment crossref |
| `educlaw_lms_sync_log` | 10-50 per term | Sync run audit |
| `educlaw_lms_grade_sync` | = assessments × students (5K-100K) | Grade pull staging |
| `educlaw_lms_course_material` | 5-20 per section | Course resources |

SQLite handles all expected volumes comfortably. For schools with 5,000 students × 200 sections × 20 assessments = 2 million grade sync records per year — still within SQLite's practical range.

---

## Workflows Summary

### Key Workflows Built

1. **Configure LMS Connection** — Multi-step setup with DPA/COPPA gates and connection testing
2. **Roster Push** — Push sections + students + instructors + enrollments to LMS (5-step sync run)
3. **Grade Pull** — Pull LMS submission scores → compare → stage → apply/flag conflicts
4. **Assignment Push** — Create SIS assessments as LMS assignments; keep in sync
5. **Grade Conflict Resolution** — Explicit UI for admin to choose between SIS grade and LMS grade
6. **OneRoster CSV Export** — Standards-based export for non-API LMS integrations
7. **Online Gradebook View** — Unified view of SIS + LMS grades with conflict indicators
8. **End-of-Term Finalization** — Pre-submission grade pull; close LMS sync post-submission

---

## Compliance Summary

| Requirement | Implementation |
|-------------|---------------|
| **FERPA** | Every sync logs to `educlaw_data_access_log`; DPA gate blocks all sync; directory opt-out respected |
| **COPPA** | Hard block on under-13 sync to unverified LMS; field minimization enforced in Python |
| **WCAG 2.1 AA** | Sync status with text labels; keyboard-navigable conflict UI; ARIA live regions |
| **State Laws** | DPA required (meets CA SOPIPA, NY Ed Law 2-d, IL SOPPA requirements); data deletion flag on student withdrawal |

---

## Build Sequence (Recommended)

1. **Schema (init_db.py)** — 7 new tables, extending parent EduClaw schema
2. **LMS connection management** — `add-lms-connection`, `test-lms-connection`, `list-lms-connections`
3. **OneRoster CSV export** — Quick win; no LMS API needed; usable by any compliant LMS
4. **Canvas adapter** — Highest priority; covers 39% of target market
5. **Roster sync** — `sync-courses` action using Canvas adapter
6. **Grade pull** — `pull-grades` + `get-online-gradebook` + `resolve-grade-conflict`
7. **Assignment sync** — `push-assessment-to-lms` + `list-lms-assignments`
8. **Google Classroom adapter** — K-12 priority
9. **Moodle adapter** — Open-source community priority
10. **Course materials** — Simplest domain; build last
11. **SKILL.md** — Document all 23 actions

---

## Key Architecture Alignment with Parent

| Parent Principle | educlaw-lms Implementation |
|-----------------|---------------------------|
| SIS is source of truth | Roster always SIS→LMS; grade conflicts require explicit resolution |
| Immutable grade submission | `is_grade_submitted = 1` blocks automated grade sync; requires amendment |
| FERPA audit logging | Every sync writes to parent's `educlaw_data_access_log` |
| TEXT for precision values | `lms_score`, `sis_score` are TEXT (Python Decimal) |
| UUIDs as IDs | All primary keys TEXT UUID |
| No ok() status collision | Use `sync_status`, `connection_status`, `mapping_status` |
| Parameterized SQL | All queries parameterized |
| Python adapter modules | `scripts/adapters/canvas.py`, `moodle.py`, `google_classroom.py`, `oneroster_csv.py` |

---

*Research completed: 2026-03-05*
*Research files: overview.md, competitors.md, compliance.md, workflows.md, data_model.md, parent_analysis.md, research_summary.md*
*Key sources: IMS Global OneRoster Spec, Canvas REST API Docs, Moodle Web Services Docs, Google Classroom API Docs, FMI LMS Market Report 2035, ListEdTech K-12 LMS Market Share 2024, OpenSIS LMS Integration, FTC COPPA 2025 Amendments, ADA Title II Web Rule (2024)*
