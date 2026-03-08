# EduClaw LMS Integration — Competitor Analysis

## Overview

This document analyzes how existing products handle LMS integration and online gradebook features. We examine three categories: (1) open-source LMS platforms with SIS integration, (2) commercial SIS products with LMS connectors, and (3) dedicated integration middleware. The goal is to understand the integration patterns, data models, and feature sets that educlaw-lms should match and differentiate from.

---

## 1. LMS Platforms (The Integration Targets)

### 1.1 Canvas (Instructure)

**Market Position:** 39% higher education market share in North America (2024); dominant and growing.
**Website:** instructure.com | canvas.instructure.com
**License:** Open-source core (Instructure Canvas) + commercial SaaS
**API Maturity:** Highest of all major LMS platforms — comprehensive REST API.

#### API Architecture
| Aspect | Detail |
|--------|--------|
| Protocol | REST over HTTPS |
| Format | JSON |
| Auth | OAuth 2.0 (preferred); also supports API tokens |
| Base URL | `https://{domain}/api/v1/` |
| Rate Limiting | Dynamic throttling (leaky bucket); per-token limits; 403 when throttled |
| Standards | OneRoster 1.1/1.2, LTI 1.3, LTI Advantage (AGS, Deep Linking, NRPS) |

#### Key API Endpoints for SIS Integration

| Endpoint | Purpose | EduClaw Relevance |
|----------|---------|-------------------|
| `GET /courses` | List all courses | Map SIS sections to Canvas courses |
| `POST /courses` | Create course | Push new sections to Canvas |
| `GET /courses/:id/enrollments` | Get course roster | Validate sync |
| `POST /courses/:id/enrollments` | Enroll user | Push student/instructor enrollment |
| `DELETE /courses/:id/enrollments/:id` | Remove enrollment | Handle drops/withdrawals |
| `GET /courses/:id/assignments` | List assignments | Sync assignment catalog |
| `POST /courses/:id/assignments` | Create assignment | Push SIS assessment to Canvas |
| `GET /courses/:id/assignments/:id/submissions` | Get grades | Pull grades back to SIS |
| `GET /users` / `POST /users` | User management | Sync student/instructor user accounts |
| `POST /courses/:id/sections` | Create section | For courses with multiple sections |

#### Grade Passback Data Model
Canvas submissions include:
- `user_id` — Canvas user ID (must map to SIS student ID)
- `score` — Raw points earned
- `grade` — Letter grade (if grading scheme set)
- `submitted_at` — Submission timestamp
- `late` — Boolean (submitted after due date)
- `missing` — Boolean (not submitted)
- `attempt` — Submission attempt number
- `workflow_state` — submitted/graded/unsubmitted/pending_review

#### Strengths for Integration
- Most complete REST API of any LMS
- Rich grade data (submission timestamps, late flags, attempt tracking)
- OneRoster 1.1 certified
- LTI Advantage fully supported
- Sandbox environments available for testing

#### Weaknesses
- Rate limiting requires queue management for large batches
- Separate token per application recommended
- Complex OAuth flow for school-managed tokens
- API changes sometimes break undocumented behaviors

---

### 1.2 Moodle

**Market Position:** 16% higher education (NA); dominant in Europe (25%) and Latin America (73%); most deployed LMS globally by instance count.
**Website:** moodle.org
**License:** GPL v3 (fully open source)
**API Maturity:** Functional but less elegant than Canvas.

#### API Architecture
| Aspect | Detail |
|--------|--------|
| Protocol | REST, XML-RPC, SOAP, AMF (configurable per instance) |
| Format | JSON (REST) / XML (XML-RPC, SOAP) |
| Auth | Token-based (per user, admin-issued); no OAuth 2.0 natively |
| Base URL | `https://{domain}/webservice/rest/server.php` |
| Rate Limiting | Admin-configurable; no default throttling |
| Standards | OneRoster 1.1 (plugin), LTI 1.3 (Moodle 3.11+) |

#### Key API Functions for SIS Integration

| Function | Purpose |
|----------|---------|
| `core_course_create_courses` | Create courses |
| `core_course_update_courses` | Update courses |
| `core_course_get_courses` | Get course list |
| `enrol_manual_enrol_users` | Enroll users in courses |
| `core_enrol_get_enrolled_users` | Get enrolled users |
| `core_user_create_users` | Create user accounts |
| `core_user_update_users` | Update user accounts |
| `core_user_get_users` | Search/get users |
| `mod_assign_get_assignments` | Get assignments |
| `mod_assign_get_grades` | Get grades for assignment |
| `core_grades_get_grades` | Get grade report data |

#### Moodle-Specific Challenges

1. **Token authentication vs. OAuth** — Each Moodle user needs their own token. For SIS sync, a dedicated "sync user" account with admin token is the practical approach.
2. **Version variability** — Different schools run different Moodle versions (3.x, 4.x). API functions vary between versions.
3. **Plugin dependencies** — Advanced features (OneRoster, LTI Advantage) require specific plugins that not all schools have installed.
4. **Self-hosted variability** — As the most self-hosted LMS, each school's Moodle can be customized in ways that break standard API assumptions.

#### Data Model Differences from Canvas
- Moodle uses "course categories" as the hierarchy (Canvas has sub-accounts)
- Moodle "activities" (assignments, quizzes, forums) vs. Canvas "assignments"
- Moodle groups and groupings for cohort management
- Grade items in Moodle gradebook correspond to Canvas grade columns

#### Strengths for Integration
- Large installed base (especially in higher ed and community colleges)
- Open source — community plugins for almost any integration
- Flexible protocol support

#### Weaknesses
- Version fragmentation makes robust integration difficult
- No OAuth 2.0 native support (requires workaround or plugin)
- LTI 1.3 requires Moodle 3.11+ and plugin configuration
- OneRoster requires Moodle plugin (not built-in)

---

### 1.3 Google Classroom

**Market Position:** Leading in K-12 volume globally; free with Google Workspace for Education.
**Website:** classroom.google.com | developers.google.com/workspace/classroom
**License:** Proprietary SaaS (free tier available)
**API Maturity:** Good for basic use cases; significant limitations for advanced grading.

#### API Architecture
| Aspect | Detail |
|--------|--------|
| Protocol | REST over HTTPS |
| Format | JSON |
| Auth | OAuth 2.0 (mandatory) |
| Base URL | `https://classroom.googleapis.com/v1/` |
| Rate Limiting | Google quotas; 100 requests/100 seconds per user |
| Standards | **No LTI support. No OneRoster support.** Direct API only. |

#### Key API Resources for SIS Integration

| Resource | Endpoint | Purpose |
|----------|---------|---------|
| Courses | `/courses` | Create/list classes |
| Course students | `/courses/:id/students` | Add/remove students |
| Teachers | `/courses/:id/teachers` | Add/remove teachers |
| CourseWork | `/courses/:id/courseWork` | Create/list assignments |
| Student submissions | `/courses/:id/courseWork/:id/studentSubmissions` | Get/grade submissions |
| Invitations | `/invitations` | Invite users to courses |
| User Profiles | `/userProfiles/:id` | Get user info |
| Guardian Invitations | `/userProfiles/:id/guardianInvitations` | Parent access setup |

#### Critical Limitations

1. **No LTI support** — Google Classroom does not implement LTI. Requires direct API only.
2. **No OneRoster support** — No standards-based roster import. Custom API implementation required.
3. **Cannot read/write overall course grade** — The API cannot set or retrieve the total grade for a student in a course. Must calculate from individual assignments.
4. **Student must accept enrollment** — Unlike Canvas, students receive an invitation and must "accept" to join the class. Complicates automated bulk enrollment.
5. **Domain-restricted** — Google Classroom requires Google Workspace for Education domain. Personal Gmail accounts cannot be students/teachers in an institutional course.
6. **Guardian invitations (not enrollment)** — Parent access is managed through a separate "Guardian" invite flow, not standard user management.

#### 2025 API Additions
- **Student Groups API** (2025): Create and manage student groups programmatically
- **Grading Periods API** (2025): Create term-based grading periods

#### Strengths for Integration
- Free for K-12 schools (Google Workspace for Education)
- Deep integration with Google Drive, Docs, Slides, Sheets (assignment submission)
- Guardian (parent) email notification built-in
- Simple UI that teachers and students already know

#### Weaknesses
- No LTI / OneRoster — biggest integration limitation
- Cannot pull overall course grade (major gap for SIS grade passback)
- Invitation-based enrollment (not automatic)
- Only works within Google Workspace domain

---

### 1.4 D2L Brightspace

**Market Position:** 16% higher education (NA); growing in Canada and enterprise.
**Website:** d2l.com
**License:** Commercial SaaS
**Standards:** OneRoster 1.1/1.2 certified, LTI Advantage certified

#### API Architecture
| Aspect | Detail |
|--------|--------|
| Protocol | REST over HTTPS |
| Format | JSON |
| Auth | OAuth 2.0 or API key |
| Standards | OneRoster 1.1, LTI 1.3 + Advantage |

**Note:** D2L Brightspace is recommended for **v2** implementation. Good OneRoster and LTI support but smaller K-12 presence than Canvas/Google.

---

## 2. SIS Products with Native LMS Integration (Competitors)

### 2.1 PowerSchool — Unified Classroom

**What it does:** PowerSchool acquired Schoology in 2019 and built "Unified Classroom" — a tight SIS+LMS bundle.

#### Integration Architecture
- **Native integration:** PowerSchool SIS ↔ Schoology LMS share the same database tables for key entities
- **Rostering:** Automatic — no sync lag; student enrollment in SIS immediately appears in Schoology
- **Grade passback:** Instant — Schoology grades write directly to PowerSchool gradebook
- **Third-party LMS:** PowerSchool → Canvas via OneRoster 1.1; PowerSchool → Google Classroom via direct API

#### Feature Set
| Feature | PowerSchool Unified Classroom |
|---------|------------------------------|
| Roster sync | Real-time (Schoology native), batch (Canvas/Google) |
| Grade passback | Instant (Schoology), manual trigger (Canvas/Google) |
| Assignment sync | Full (Schoology), limited (Canvas) |
| Conflict resolution | SIS wins (for external LMS) |
| Sync audit log | Basic |
| Parent visibility | Parent app shows Schoology grades |
| Single sign-on | Yes, for PowerSchool ecosystem |

#### Lessons for educlaw-lms
- Real-time sync is the gold standard but requires tight coupling; batch sync (scheduled jobs) is practical for external LMS
- SIS should always win grade conflicts (SIS = source of truth)
- Parent visibility of LMS grades is a key UX feature (pull grades → EduClaw → notifications)

---

### 2.2 Infinite Campus — Campus Learning Suite

**What it does:** Infinite Campus (IC) has its own LMS module (Campus Learning) and OneRoster-based external sync.

#### Integration Architecture
- **Campus Learning:** Native embedded LMS within IC (basic, teacher-facing)
- **External LMS:** OneRoster 1.1/1.2 export to Canvas, Google Classroom, Schoology, Moodle
- **Grade passback:** OneRoster Results endpoint; or manual import

#### Key Feature: Rostering Engine
IC's rostering engine uses its OHIO (Only Handle Information Once) architecture:
- Each student exists once; their enrollments determine which LMS courses they appear in
- Enrollment changes (add/drop) propagate to LMS within the OneRoster sync cycle
- Supports multiple LMS connections simultaneously

#### OneRoster CSV Files Generated by IC
1. `orgs.csv` — School/district hierarchy
2. `users.csv` — Students, teachers, parents, admins
3. `courses.csv` — Course catalog entries
4. `classes.csv` — Course sections (with schedule, term)
5. `enrollments.csv` — Student-class and teacher-class links
6. `academicSessions.csv` — Terms and years
7. `lineItems.csv` — Assignment definitions
8. `results.csv` — Grade/score results

#### Lessons for educlaw-lms
- OneRoster CSV is the minimum viable integration path — all major LMS platforms can consume it
- Separate CSV files per entity type follows standard; don't try to merge
- Academic sessions (terms) must be synced before courses; courses before classes; classes before enrollments

---

### 2.3 OpenSIS — LMS Integration Module

**What it does:** OpenSIS (the most comprehensive open-source SIS) offers Moodle and Canvas sync via a dedicated module.

#### Integration Architecture (from OpenSIS documentation and code review)
- **Moodle sync:** Uses Moodle Web Services API; creates/updates users, courses, enrollments
- **Canvas sync:** Uses Canvas REST API; OAuth 2.0 token
- **Data model:** OpenSIS stores LMS external IDs in cross-reference tables

#### Cross-Reference Tables (from OpenSIS)
```
opensis_lms_connections
  - id, lms_type (moodle|canvas), endpoint_url, auth_token
  - school_id (multi-school support)

opensis_lms_course_map
  - opensis_course_id, lms_type, lms_course_id, sync_status, last_sync

opensis_lms_user_map
  - opensis_user_id, user_type (student|teacher), lms_type, lms_user_id

opensis_lms_grade_sync
  - opensis_assignment_id, lms_assignment_id, student_id, score, synced_at
```

#### OpenSIS Sync Features
- Manual trigger sync (no automatic/scheduled sync in open-source version)
- One-way grade pull (LMS → SIS)
- Sync error log with error messages per record
- Re-sync capability for failed records
- Assignment mapping (SIS assignment ↔ LMS assignment/activity)

#### Lessons for educlaw-lms
- Cross-reference tables (SIS ID ↔ LMS ID) are the architectural foundation — implement early
- Sync log with per-record error tracking is essential for debugging
- Support re-sync for failed records (partial sync recovery)
- Manual trigger is acceptable for v1; scheduled jobs are v2

---

### 2.4 Blackbaud — LMS Integration

**What it does:** Blackbaud has its own embedded LMS for private K-12 schools, plus Canvas/Google Classroom connectors.

#### Key Architectural Feature: Grade Sync Direction Policy
Blackbaud explicitly defines "grade sync direction":
- **LMS → SIS:** Instructor enters grade in LMS; it pulls to SIS (most common for LMS-first schools)
- **SIS → LMS:** SIS grade is authoritative; pushes to LMS display (less common)
- **Manual merge:** Administrator reviews conflicts and chooses winner

**This is the most important lesson from Blackbaud:** Grade direction must be an explicit configuration, not an assumption.

---

## 3. Integration Middleware (Alternatives to Direct API)

### 3.1 EdLink (ed.link)

**What it does:** EdLink is a middleware API that provides a unified interface to multiple LMS platforms. Instead of integrating with Canvas, Moodle, and Google separately, a product integrates once with EdLink.

#### EdLink API Coverage
- Canvas, Google Classroom, Moodle, Schoology, Blackboard, D2L Brightspace, Desire2Learn
- Standardized data model across all platforms
- Handles OAuth, token refresh, rate limiting

#### EdLink Relevance
- educlaw-lms could use EdLink instead of direct API integration to reduce complexity
- Trade-off: External dependency, subscription cost, less control
- **Recommendation:** Implement Canvas and Google Classroom directly (highest priority); use EdLink pattern as architecture reference

### 3.2 Classlink / Clever

**What they do:** Primarily roster/SSO providers for K-12. Clever and Classlink act as identity bridges between SIS and dozens of LMS/ed-tech tools.

- Used by PowerSchool, Infinite Campus, FACTS SIS for OneRoster distribution
- Not full grade passback solutions — primarily roster + SSO
- **Recommendation:** Not needed for educlaw-lms v1; relevant for future SSO integration

---

## 4. Competitive Feature Matrix

| Feature | Canvas Direct | Moodle Direct | Google Classroom Direct | OpenSIS LMS | PowerSchool UC | Infinite Campus | **educlaw-lms (Target)** |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Roster Push (SIS→LMS)** | ✅ | ✅ | ⚠️ (invite-based) | ✅ | ✅ | ✅ | **✅** |
| **Grade Pull (LMS→SIS)** | ✅ | ✅ | ⚠️ (no overall grade) | ✅ | ✅ | ✅ | **✅** |
| **Assignment Sync** | ✅ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | **✅** |
| **Course Material Mgmt** | LMS-only | LMS-only | LMS-only | ❌ | ✅ | ⚠️ | **✅** (SIS-side) |
| **OneRoster Export** | ✅ (import) | ✅ (plugin) | ❌ | ⚠️ | ✅ | ✅ | **✅** |
| **LTI 1.3 Support** | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | v2 |
| **Multi-LMS (one config)** | ❌ | ❌ | ❌ | ⚠️ | ❌ | ✅ | **✅** |
| **Sync Audit Log** | ❌ | ❌ | ❌ | ✅ | ⚠️ | ✅ | **✅** |
| **Conflict Resolution Policy** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | **✅** |
| **FERPA-logged Sync** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | **✅** |
| **Open Source** | ✅ (Canvas core) | ✅ | ❌ | ✅ | ❌ | ❌ | **✅** |
| **Offline-capable** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **⚠️ (local SIS + remote LMS)** |

---

## 5. Key Takeaways for educlaw-lms

### 5.1 Must-Have Features (from competitor analysis)
1. **Cross-reference tables** (SIS ID ↔ LMS ID per platform) — Every competitor has this
2. **Sync audit log** — Per-record status, error messages, timestamp
3. **Grade pull** — Pull LMS grades back to `educlaw_assessment_result`
4. **Roster push** — Push course_enrollment records as LMS enrollments
5. **Course/section mapping** — Map EduClaw sections to LMS courses
6. **User account mapping** — Student/instructor SIS ID ↔ LMS user ID
7. **Multi-LMS support** — One EduClaw instance, multiple LMS connections
8. **Grade direction policy** — Explicit config: LMS→SIS or SIS→LMS or manual

### 5.2 Key Differentiators to Build

1. **FERPA-logged sync** — No competitor logs LMS pushes as FERPA disclosures. We do.
2. **Conflict resolution UI** — Show conflicts explicitly; don't silently overwrite
3. **Open source + multi-LMS** — No open-source product handles Canvas + Moodle + Google in one
4. **Course materials in SIS** — Store syllabus/resource links in EduClaw, not scattered in LMS

### 5.3 Architecture Lessons

1. **OpenSIS pattern:** Cross-reference tables with `lms_type` enum — simple, works for all platforms
2. **PowerSchool:** SIS wins on conflicts for enrollment data; LMS wins for assignment-level grades
3. **Infinite Campus:** OneRoster CSV as reliable lowest-common-denominator integration
4. **Blackbaud:** Grade direction must be explicit setting per connection
5. **Canvas API:** Rate limit per token; use separate tokens per integration module
6. **Google Classroom:** Plan for invite-based enrollment; handle the "pending" state

---

*Sources: Canvas REST API Documentation (canvas.instructure.com/doc/api), Moodle Web Services API (docs.moodle.org), Google Classroom API (developers.google.com/workspace/classroom), OpenSIS Feature Documentation (opensis.com/lms-integration), EdLink Community Blog (ed.link/community), Infinite Campus OneRoster Documentation, PowerSchool Unified Classroom product page, Blackbaud LMS product page, IMS Global OneRoster Specification, 1EdTech LTI Advantage documentation*
