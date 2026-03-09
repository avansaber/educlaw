# EduClaw LMS Integration — Industry Overview

## 1. What is LMS Integration in the Context of Education ERP?

A **Learning Management System (LMS)** is a software platform used by educational institutions to deliver, manage, and track digital learning content — online courses, assignments, discussions, quizzes, and grades. Examples include Canvas, Moodle, Google Classroom, D2L Brightspace, and Schoology.

An **LMS integration** (or "SIS-LMS integration") is the bidirectional data bridge between a **Student Information System (SIS)** like EduClaw and the LMS. It solves a fundamental operational problem: schools maintain student records, course rosters, and official grades in their SIS, but instructors create and grade assignments in the LMS. Without integration, staff must manually copy data between systems — a time-consuming and error-prone process.

**educlaw-lms** extends the base EduClaw SIS to provide:
1. **Roster sync** — automatically push student/instructor enrollments from EduClaw to the LMS
2. **Course/section sync** — mirror EduClaw course sections as LMS courses
3. **Assignment management** — create and track LMS assignments within the SIS
4. **Online gradebook** — pull grades from the LMS back into EduClaw's authoritative gradebook
5. **Course materials** — organize course content attachments and external links within the SIS

---

## 2. Market Context

### 2.1 LMS Market Size and Growth

| Metric | Value | Source |
|--------|-------|--------|
| **Global LMS Market (2025)** | $28.6–$32.7 billion | Future Market Insights, Research.com |
| **Projected (2030)** | $70.8 billion | FMI |
| **Projected (2035)** | $172.4 billion | FMI |
| **CAGR (2025-2035)** | 18.1–20.2% | Multiple analysts |
| **K-12 Segment growth** | Faster than overall | Grand View Research |

The LMS market is growing substantially faster than the broader education software market. Driven by:
- Post-pandemic acceleration of hybrid/blended learning
- Increasing demand for digital assignment management
- Growing parent expectations for real-time grade visibility
- AI integration into content delivery and automated grading

### 2.2 LMS Market Share by Platform

#### Higher Education (North America, 2024)
| Platform | Market Share | Notes |
|----------|-------------|-------|
| **Canvas (Instructure)** | 39% | Dominant; greater than next 3 combined |
| **Blackboard Learn (Anthology)** | 19% | Declining |
| **Moodle** | 16% | Open-source leader |
| **D2L Brightspace** | 16% | Growing |

#### K-12 / Overall (Global)
| Platform | Market Share | Notes |
|----------|-------------|-------|
| **Google Classroom** | Leading | Especially K-12; free with Google Workspace |
| **Canvas** | 19% | Fastest-growing paid platform |
| **Moodle** | 14% | Open-source; 73% Latin America share |
| **Schoology (PowerSchool)** | 11% | Integrated with PowerSchool SIS |
| **Blackboard Learn** | 8% | Declining in K-12 |
| **D2L Brightspace** | 5% | Growing in Canada and enterprise |

**Regional variance:** Moodle dominates Europe (25%) and Latin America (73%). Canvas leads in US higher education. Google Classroom leads in US K-12 by volume.

---

## 3. The SIS-LMS Integration Problem

### 3.1 The Data Silos Problem

Schools operate two mission-critical systems that hold overlapping but non-identical data:

```
SIS (EduClaw)                       LMS (Canvas/Moodle/Google)
────────────────                    ──────────────────────────
✅ Official student records         ✅ Course content delivery
✅ Authoritative rosters            ✅ Assignment management
✅ Program enrollment               ✅ Online submission collection
✅ Attendance                       ✅ Rubric-based grading
✅ Financial aid / billing          ✅ Discussion forums
✅ FERPA audit trail                ✅ Real-time student engagement
✅ Transcript generation            ❌ Official academic record
❌ Online submission tracking       ❌ Financial management
❌ Course content hosting           ❌ State reporting
```

Without integration: Staff manually enter students into the LMS at term start (takes hours), manually re-enter grades from LMS into SIS at term end (error-prone), and students experience inconsistent information between systems.

### 3.2 Integration Data Flows

```
SIS → LMS (Push)                    LMS → SIS (Pull)
────────────────                    ────────────────
Student roster                      Assignment grades
Instructor assignments              Submission status
Course/section definitions          Completion data
Enrollment changes (add/drop)       (Optional) engagement metrics
Grading scale configuration
```

### 3.3 Frequency of Synchronization

| Data Type | Typical Frequency | Trigger |
|-----------|------------------|---------|
| Initial roster | Once per term | Term opens |
| Enrollment add/drop | Near real-time or daily | Enrollment change |
| Assignment creation | On instructor action | New assignment added |
| Grade passback | On grade entry | Instructor submits grade in LMS |
| Full resync | Weekly or on-demand | Drift correction |

---

## 4. Key Industry Standards

### 4.1 OneRoster (IMS Global / 1EdTech)

OneRoster is the **primary standard** for SIS-to-LMS roster and grade synchronization.

| Version | Status | Key Features |
|---------|--------|--------------|
| **1.0** | Deprecated (Jan 2019) | Basic CSV roster |
| **1.1** | Current recommended | REST/JSON + CSV; users, classes, enrollments, grades, resources |
| **1.2** | Latest | OAuth 2.0 Bearer Token only; enhanced usability |

**OneRoster 1.1 Services:**
- **Rostering:** Syncs orgs, users, courses, classes, enrollments
- **Gradebook:** Syncs line items (assignments) and results (scores)
- **Resources:** Links learning resources to classes

**Data Format:**
- **CSV**: 11 files (orgs.csv, users.csv, courses.csv, classes.csv, enrollments.csv, academicSessions.csv, lineItems.csv, results.csv, categories.csv, classResources.csv, courseResources.csv)
- **REST/JSON**: RESTful HTTP with OAuth 2.0; real-time API calls

**Adoption:** Required by most state education agencies and many districts. Canvas, Moodle, Blackboard, D2L Brightspace all have OneRoster 1.1 certification.

### 4.2 LTI (Learning Tools Interoperability) — 1EdTech Standard

LTI defines how **external tools** launch inside an LMS and exchange data. LTI 1.3 (current) uses OAuth2 + OpenID Connect + JSON Web Tokens.

**LTI Advantage Services (LTI 1.3 extension):**

| Service | Purpose | EduClaw Relevance |
|---------|---------|-------------------|
| **Assignment & Grade Services (AGS v2.0)** | Sync scores between tool and LMS gradebook | Grade passback for external tools |
| **Deep Linking** | Embed specific content into LMS course pages | Course material linking |
| **Names & Role Provisioning Services** | Share roster/enrollment info with tools | Roster push to integrated tools |

**Platform support:** Canvas, Moodle, Blackboard, D2L Brightspace all support LTI 1.3. **Google Classroom does NOT support LTI** — requires direct API integration.

### 4.3 SCORM and xAPI (Content Packaging Standards)

These govern how learning content packages communicate completion and scores back to the LMS:

| Standard | Version | Use Case | Grade Passback |
|----------|---------|----------|----------------|
| **SCORM 1.2** | 2001 | Most widely deployed; simple tracking | Completion + score (0-100 scale) |
| **SCORM 2004** | Current | Advanced sequencing, interaction tracking | Separate completion + success status |
| **xAPI (Tin Can API)** | 1.0+ | Analytics beyond the LMS; actor-verb-object statements | Via Learning Record Store (LRS) |

**EduClaw LMS relevance:** SCORM/xAPI are used by content publishers (e.g., Pearson textbooks). educlaw-lms does not need to generate SCORM content but should be aware that LMS grades may come from SCORM packages, not just instructor-entered grades.

---

## 5. Key Entities in LMS Integration

### 5.1 Cross-System Entity Mapping

| SIS (EduClaw) Entity | LMS Entity | Sync Direction |
|---------------------|-----------|----------------|
| `educlaw_academic_term` | Academic Session / Term | SIS → LMS |
| `educlaw_course` | Course (catalog entry) | SIS → LMS |
| `educlaw_section` | Class / Course Section | SIS → LMS |
| `educlaw_student` | Student User | SIS → LMS |
| `educlaw_instructor` | Teacher/Facilitator User | SIS → LMS |
| `educlaw_course_enrollment` | Enrollment / Roster | SIS → LMS |
| `educlaw_assessment` | Assignment / Line Item | SIS → LMS (or LMS-created) |
| `educlaw_assessment_result` | Result / Submission Score | LMS → SIS |
| (new) `educlaw_lms_connection` | LMS Platform Config | SIS only |
| (new) `educlaw_lms_course_mapping` | Course↔Class crossref | SIS only |
| (new) `educlaw_lms_user_mapping` | User crossref | SIS only |
| (new) `educlaw_lms_sync_log` | Sync audit trail | SIS only |
| (new) `educlaw_course_material` | Course document/resource | SIS + LMS |

### 5.2 LMS Assignment Types

| Assignment Type | LMS Examples | Grade Calculation Notes |
|----------------|-------------|-------------------------|
| Standard graded | Essay, quiz | Points → mapped to EduClaw assessment_result |
| Pass/Fail | Completion check | Maps to pass/fail grade type |
| Peer-reviewed | Group projects | May have multiple scores |
| Survey/ungraded | Attendance check | No grade passback |
| SCORM module | Interactive content | Completion status + score |
| Extra credit | Bonus points | May exceed max_points |

---

## 6. Why This is a Sub-Vertical (Not Part of Core EduClaw)

The parent EduClaw research explicitly deferred LMS integration because it requires:

1. **External network calls** — EduClaw is fully offline/local. LMS sync introduces first-ever network dependency.
2. **Per-LMS API expertise** — Canvas, Moodle, and Google Classroom each have distinct APIs, auth methods, and quirks.
3. **Conflict resolution logic** — When SIS grade ≠ LMS grade, resolution rules are complex.
4. **OAuth/LTI infrastructure** — Token management, refresh, LTI launch flows.
5. **Sync state management** — Retry logic, error handling, partial sync recovery.
6. **FERPA complexity** — Every external data push is a "disclosure" that must be tracked.

Schools that do not use an external LMS (e.g., pure offline environments) can run EduClaw without this sub-vertical entirely.

---

## 7. Target Users and Use Cases

### 7.1 Primary Users

| User | Use Case |
|------|----------|
| **Registrar / SIS Admin** | Configure LMS connections, trigger roster syncs, monitor sync errors |
| **Instructor** | Create assignments in SIS that push to LMS, or pull LMS grades back to gradebook |
| **IT Administrator** | Configure OAuth credentials, manage LMS API connections |
| **Student** | Transparent experience: submits in LMS, sees grades in SIS portal |
| **Parent/Guardian** | Sees LMS-sourced grades in EduClaw reports; no direct LMS access needed |

### 7.2 Core Use Cases (v1 Scope)

1. **Canvas Integration** — Highest priority (39% higher ed market share, strong API)
2. **Google Classroom Integration** — K-12 priority (dominant in K-12)
3. **Moodle Integration** — Open-source community priority
4. **OneRoster CSV Export** — Lowest-effort integration path for any compliant LMS
5. **Online Gradebook** — Track LMS-sourced grades alongside SIS-native grades

### 7.3 Use Cases for v2

- D2L Brightspace integration
- Schoology integration
- xAPI / LRS integration
- SCORM completion tracking
- LTI 1.3 tool launch from EduClaw
- Real-time assignment sync (webhook-based)

---

## 8. Market Trends (2025-2026)

| Trend | Description | EduClaw-LMS Relevance |
|-------|-------------|----------------------|
| **Blended learning normalization** | 60%+ of instruction has online component post-pandemic | LMS sync is now expected, not optional |
| **AI in grading** | LMS platforms adding auto-grading, feedback AI | Grade passback must handle AI-assigned scores |
| **Single sign-on (SSO)** | Schools want one login for SIS + LMS | SSO via Google/Microsoft OAuth (v2) |
| **Parent transparency** | 5-8% grade improvement with real-time parent access | Pulling LMS grades → EduClaw → parent portal |
| **OneRoster adoption surge** | States requiring OneRoster compliance | CSV export as minimum viable integration path |
| **Canvas dominance accelerating** | Canvas share grew vs. Blackboard's decline | Canvas API is highest-priority integration |
| **LTI 1.3 standardization** | Old LTI 1.1 being deprecated | New integrations must use LTI 1.3 |
| **Data privacy scrutiny** | FERPA + COPPA enforcement intensifying | Every LMS sync is a tracked disclosure |

---

## 9. EduClaw-LMS Competitive Position

### 9.1 How Competitors Handle LMS Integration

| SIS Product | LMS Integration Approach |
|-------------|-------------------------|
| **PowerSchool** | Native Schoology LMS (acquired); Canvas/Google via Unified Classroom |
| **Infinite Campus** | Campus Learning Suite; OneRoster for external LMS |
| **Blackbaud** | Built-in LMS; third-party via API |
| **Ellucian Banner** | Ethos integration platform; Canvas partnership |
| **OpenSIS** | Moodle + Canvas via custom plugin; OneRoster export |
| **ERPNext Education** | No native LMS integration |
| **EduClaw (base)** | No LMS integration (this sub-vertical) |

### 9.2 EduClaw-LMS Differentiators

1. **Standards-first** — OneRoster + LTI 1.3 from day one; not proprietary connectors
2. **Multi-LMS** — Canvas + Google Classroom + Moodle in one package (competitors tie you to one)
3. **SIS-authoritative** — Grades pulled from LMS but posted authoritatively to EduClaw (not the reverse)
4. **FERPA-first sync** — Every push/pull is logged as a data disclosure
5. **Open source** — Transparent, extensible, no per-seat sync fees
6. **Conflict resolution** — Explicit policy when SIS grade ≠ LMS grade (other systems often silently overwrite)

---

*Sources: Future Market Insights LMS Market Report 2035, ListEdTech K-12 LMS Market Share (2024), Research.com LMS Statistics 2026, IMS Global OneRoster Specification, 1EdTech LTI Advantage Overview, Canvas REST API Documentation, Moodle Web Services Documentation, Google Classroom API Documentation, EdLink "What Makes LMS Integration Challenging" (2025)*
