# EduClaw LMS Integration — Compliance & Regulatory Requirements

## Overview

educlaw-lms introduces a fundamentally new compliance surface compared to base EduClaw: **external data transmission**. Base EduClaw is fully local/offline — no data ever leaves the machine. educlaw-lms pushes student data to external LMS systems (Canvas, Moodle, Google Classroom), which means every sync operation is a **FERPA-regulated disclosure** that must be tracked, controlled, and auditable.

This document covers compliance requirements inherited from the parent EduClaw plus those specific to LMS integration.

---

## 1. FERPA — LMS Integration Implications

### 1.1 LMS Integration as a FERPA Disclosure

Under FERPA (20 U.S.C. § 1232g; 34 CFR Part 99), sharing student records with an external system is a "disclosure." The LMS integration must qualify under one of these FERPA exceptions to be lawful:

| FERPA Exception | Applicability to LMS Sync | Requirements |
|----------------|--------------------------|-------------|
| **School Official** | ✅ Primary basis — LMS vendor is a "school official" if under school control | School must have "legitimate educational interest" defined in annual FERPA notice; LMS vendor must be under school's "direct control" with appropriate data use agreements |
| **Directory Information** | ⚠️ Limited — only for basic info (name, email) if student hasn't opted out | Cannot use for grades, enrollment details; opt-out students must be excluded from public fields |
| **Legitimate Educational Purpose** | ✅ Core basis for all academic data | Course enrollments, grades, assignments are educational records; sharing with LMS for delivery of instruction qualifies |

**Critical implication:** Students with `directory_info_opt_out = 1` in `educlaw_student` must still be synced to LMS (for instruction delivery), but their data must be excluded from any LMS features that would make it publicly visible (e.g., class lists visible to other students).

### 1.2 LMS Vendor as "School Official" — Requirements

For the LMS to qualify as a "school official" under FERPA:

1. **Data Processing Agreement (DPA)** — Written agreement between school and LMS vendor specifying:
   - Data use is strictly for educational purposes
   - Vendor cannot re-disclose data without school permission
   - Vendor must return/destroy data upon contract termination

2. **Legitimate Educational Interest** — School's annual FERPA notification must describe what third parties may receive records (can be generic: "educational software providers")

3. **School Control** — School must be able to direct and oversee the vendor's data use

**educlaw-lms implementation:** The LMS connection configuration should require acknowledgment that a DPA exists with the LMS vendor before allowing sync.

### 1.3 What Must Be Logged for FERPA Compliance

Every sync operation that transmits student PII must be logged in `educlaw_data_access_log`:

| Sync Operation | FERPA Log Category | Access Type |
|---------------|-------------------|-------------|
| Push student roster to LMS | `demographics` + `enrollment` | `disclosure` |
| Push instructor assignment to LMS | `academics` | `disclosure` |
| Pull student grade from LMS | `grades` | `view` (incoming) |
| Pull submission status from LMS | `academics` | `view` (incoming) |
| Full resync (all students) | `demographics` + `enrollment` + `grades` | `disclosure` |

**New access_type needed:** Parent EduClaw has `view`, `export`, `print`. educlaw-lms adds **`disclosure`** (data sent to third-party system) and **`pull`** (data received from third-party system).

### 1.4 FERPA — Directory Information Opt-Out Handling

Students with `educlaw_student.directory_info_opt_out = 1`:
- **Still sync** to LMS (must be in the course roster for educational delivery)
- **Restrict** in LMS: name/photo not displayed in class directory features
- **Log** sync with `is_restricted_disclosure = 1` flag
- **Never** include in OneRoster public exports meant for non-educational purposes

### 1.5 2025 FERPA Updates Affecting LMS Integration

- **AI prohibition:** Schools may NOT allow LMS vendors to use student data to train AI models without explicit consent. If Canvas, Moodle, or Google uses LMS data for AI, the school must configure this off OR obtain parent/student consent.
- **121+ state laws** now add requirements beyond FERPA. Common additions:
  - California SOPIPA: Prohibits LMS vendors from using student data for targeted advertising
  - New York Ed Law § 2-d: Annual security reports; breach notification within 24 hours
  - Illinois SOPPA: School board must approve LMS vendor data collection

---

## 2. COPPA — LMS Integration for Under-13 Students

### 2.1 Core COPPA Requirement for LMS Integration

COPPA (15 U.S.C. §§ 6501-6506) applies when students are under 13. When educlaw-lms syncs a student with `is_coppa_applicable = 1` to an external LMS, the school must verify:

1. **LMS vendor is COPPA-compliant** — Vendor has a published privacy policy; has COPPA compliance certification (e.g., iKeepSafe COPPA certification, TrustArc)
2. **School consent covers LMS use** — The school's COPPA consent form includes the specific LMS being used
3. **Data minimization** — Only sync fields required for educational delivery (name, email, class enrollment). Never sync: DOB, phone, address, SSN, photos unless explicitly required AND COPPA-consented

### 2.2 2025 COPPA Rule Update — LMS Impact

The FTC's 2025 COPPA amendments (effective June 23, 2025; compliance required April 22, 2026) significantly impact LMS integration:

| 2025 COPPA Requirement | Impact on LMS Integration |
|------------------------|--------------------------|
| **School consent scope** clarified: ONLY for school's authorized educational purpose | LMS may NOT use student data for analytics, improvement, or AI training without parent consent |
| **Expanded PII definition** includes device IDs, persistent identifiers, cookies | LMS-assigned user IDs for students under 13 are COPPA-protected PII |
| **Formal security program** required | School must verify LMS vendor has documented security program |
| **Data retention limits** | LMS must delete student data when enrollment ends; school must enforce via contract |
| **Parental opt-out of third-party disclosure** | Parents can request that student data NOT be sent to the LMS. School must handle this edge case. |

### 2.3 COPPA-Safe Sync Rules

| Field | Sync for Under-13 Students? | Reason |
|-------|---------------------------|--------|
| `full_name` | ✅ Required | Course roster identification |
| `email` | ✅ Required | LMS account creation |
| `section_id` → LMS class | ✅ Required | Enrollment delivery |
| `grade_level` | ⚠️ Minimize | Not always required; check if LMS needs it |
| `date_of_birth` | ❌ Never | Not needed by LMS |
| `address` | ❌ Never | Not needed by LMS |
| `guardian info` | ❌ Never to LMS | Guardian contacts stay in SIS |
| `photo` | ❌ Unless DPA covers | High-sensitivity COPPA PII |
| `SSN` | ❌ Absolutely never | Not needed; violates data minimization |

### 2.4 Implementation: COPPA Guard in Sync

Before syncing any student to LMS, educlaw-lms must check:

```python
# Pseudocode — COPPA guard in sync operation
if student.is_coppa_applicable == 1:
    if not lms_connection.is_coppa_verified:
        raise SyncError("Cannot sync under-13 student to unverified LMS. Verify COPPA compliance first.")
    # Apply data minimization: only sync required fields
    user_payload = build_minimal_payload(student)  # name, email, enrollment only
else:
    user_payload = build_full_payload(student)
```

---

## 3. FERPA + COPPA Combined: Parent Access to LMS Data

When grades flow from LMS → EduClaw:
- **Parents of under-18 students** have FERPA rights to inspect grades
- **Under-13 parents** have COPPA rights to review ALL data collected about their child (including LMS-sourced grades)
- **LMS-pulled grades** stored in `educlaw_assessment_result` are subject to the same FERPA amendment request process as manually-entered grades

---

## 4. Data Processing Agreements (DPA) Requirements

### 4.1 By Platform

| LMS Platform | DPA Availability | COPPA Certification | FERPA Compliance Claim |
|-------------|-----------------|---------------------|----------------------|
| **Canvas (Instructure)** | Yes — Instructure DPA available; district-specific agreements | iKeepSafe COPPA Safe Harbor | Yes — privacy.instructure.com |
| **Moodle** | Self-hosted: school is data controller; Moodle HQ DPA for MoodleCloud | Varies by hosting provider | Self-hosted: school controls |
| **Google Classroom** | Yes — Google Workspace for Education DPA; Additional Terms for K-12 | TRUSTe COPPA certification | Yes — edu.google.com/privacy |
| **D2L Brightspace** | Yes — D2L DPA available | iKeepSafe | Yes |

### 4.2 educlaw-lms Configuration Requirement

The `educlaw_lms_connection` configuration should include:
- `has_dpa_signed` — Boolean: has the school signed a DPA with this LMS?
- `is_coppa_verified` — Boolean: has admin confirmed the LMS is COPPA-compliant?
- `coppa_cert_url` — URL to LMS's COPPA certification (for audit purposes)
- `dpa_date` — When DPA was signed
- `allowed_data_fields` — JSON: which fields are permitted per the DPA

---

## 5. Section 508 / WCAG 2.1 — Online Gradebook Accessibility

### 5.1 Requirements

The online gradebook exposed by educlaw-lms must meet **WCAG 2.1 Level AA**:

| ADA Update | Effective Date | Scope |
|-----------|---------------|-------|
| ADA Title II Web Rule (April 24, 2024) | 2-3 years from publication = 2026-2027 | State/local governments incl. public schools |

**Timeline:** Public schools must meet WCAG 2.1 AA for all web content (including gradebooks) by 2026-2027.

### 5.2 WCAG 2.1 AA Requirements for Online Gradebook Features

| Criterion | Requirement | Gradebook Implementation |
|-----------|-------------|-------------------------|
| **1.1.1 Non-text Content** | Alt text for images | Sync status icons must have text alternatives |
| **1.3.1 Info and Relationships** | Programmatic structure | Grade tables must use proper `<table>`, `<thead>`, `<th scope>` |
| **1.4.1 Use of Color** | Not color-only | Sync status must show text ("Error"), not just red color |
| **1.4.3 Contrast** | 4.5:1 minimum for text | All grade data text must meet contrast ratio |
| **1.4.11 Non-text Contrast** | 3:1 for UI components | Input fields, buttons, icons must meet ratio |
| **2.1.1 Keyboard** | All functions keyboard-accessible | Grade review, conflict resolution, sync triggers |
| **2.4.3 Focus Order** | Logical tab order | Grade table cells, sync buttons in logical sequence |
| **3.3.1 Error Identification** | Errors described in text | Sync errors: "Failed to sync student Jane Doe: LMS returned 404" |
| **3.3.2 Labels or Instructions** | All inputs labeled | API key fields, sync schedule fields labeled |
| **4.1.2 Name, Role, Value** | ARIA for dynamic content | Sync status updates, loading indicators |

### 5.3 Gradebook-Specific Accessibility Considerations

- **Grade tables** with student rows and assignment columns must use `<table>` with `<th scope="col">` for assignment headers and `<th scope="row">` for student names
- **Sync status indicators** (✅ synced, ❌ error, ⚠️ conflict) must have text alternatives (not icon-only)
- **Grade conflict display** — when SIS grade ≠ LMS grade, the conflict UI must be keyboard-navigable
- **Loading states** during sync — must announce state changes to screen readers via `aria-live`

---

## 6. Student Data Privacy Laws — LMS Integration Scope

### 6.1 State Laws Affecting LMS Sync

| State | Law | Key LMS Sync Requirement |
|-------|-----|--------------------------|
| **California** | SOPIPA + AB 1584 | LMS vendor cannot use student data for advertising or create profiles beyond educational service; school must have written agreement |
| **New York** | Ed Law § 2-d + Part 121 | Annual data security plan; breach notification required; operators must provide data inventory |
| **Illinois** | SOPPA | School board must approve LMS vendor; vendor cannot retain data beyond education purpose |
| **Texas** | TEOG | Student data cannot be sold by LMS vendor; school must obtain parent consent for certain transfers |
| **Colorado** | SB 22-070 | Annual security audit; transparency report on data collection |

### 6.2 Common Requirements Across State Laws

All states with student privacy laws require for LMS vendors:
1. **Written data processing agreement** (DPA) required before any student data sync
2. **Prohibition on advertising use** — LMS cannot use student data for targeted ads
3. **Data deletion rights** — Must delete student data within specific timeframe after enrollment ends
4. **Breach notification** — Notify school within 24-72 hours of security incident
5. **Transparency** — Parents can request to know what data is shared with LMS

---

## 7. SCORM/xAPI Privacy Considerations

If the LMS delivers SCORM or xAPI content packages to students:
- SCORM completion data (score, time, status) flows from SCORM package → LMS → SIS
- xAPI statements can include very detailed learning activity data (question-level, video timestamps)
- **Privacy concern:** xAPI data may include behavioral tracking that wasn't disclosed to parents
- **educlaw-lms approach:** Import only top-level score and completion from SCORM/xAPI; do not import interaction-level data without explicit consent

---

## 8. Compliance Checklist for educlaw-lms v1

### Priority 1 — FERPA (Must Have at Launch)
- [ ] Log every roster push to LMS in `educlaw_data_access_log` with `access_type = 'disclosure'`
- [ ] Log every grade pull from LMS with `access_type = 'pull'`
- [ ] Respect `directory_info_opt_out` — exclude restricted fields from LMS sync
- [ ] DPA acknowledgment field in `educlaw_lms_connection` configuration
- [ ] Sync only data covered by "school official" / legitimate educational interest exception
- [ ] New `access_type` values: `disclosure`, `pull` added to parent's `educlaw_data_access_log`

### Priority 2 — COPPA (Must Have for K-12)
- [ ] COPPA guard: check `is_coppa_applicable` before syncing student
- [ ] `is_coppa_verified` flag on LMS connection (block sync if not verified)
- [ ] Data minimization: under-13 students sync name + email + enrollment ONLY
- [ ] Never sync: DOB, address, phone, SSN, guardian info, photos (without explicit DPA provision)
- [ ] COPPA certification URL stored in LMS connection config

### Priority 3 — Accessibility (Should Have)
- [ ] Sync status indicators include text (not icon-only)
- [ ] Grade tables use semantic HTML (`table`, `th scope`)
- [ ] Conflict resolution UI is keyboard-navigable
- [ ] ARIA live regions for sync status updates
- [ ] Error messages describe specific failure in text

### Priority 4 — State Privacy Laws (Infrastructure)
- [ ] DPA signed field in LMS connection
- [ ] Data deletion: when student withdrawn, flag for LMS account deactivation/deletion
- [ ] Breach logging: sync errors logged with enough detail for breach notification
- [ ] Data inventory: `educlaw_lms_sync_log` provides complete audit of what was shared

---

## 9. Compliance Architecture Summary

```
EduClaw (Local SIS)                     External LMS
────────────────────                    ────────────────
Before any sync:
  ✅ Check DPA signed                   LMS DPA (signed outside system)
  ✅ Check COPPA verified (for K-12)    LMS COPPA certification
  ✅ Check student opt-out status

During sync:
  ✅ Log every push → data_access_log
  ✅ Apply COPPA field restrictions
  ✅ Apply directory opt-out rules

After sync:
  ✅ Log sync result in lms_sync_log
  ✅ Flag conflicts for review
  ✅ Notify on errors
```

---

*Sources: studentprivacy.ed.gov (FERPA Third-Party Disclosure Guidance), ftc.gov (COPPA Rule 2025 Amendments), section508.gov (WCAG 2.1 AA Standards), ADA.gov (April 2024 Title II Web Rule), California SOPIPA, New York Education Law § 2-d, Illinois SOPPA, SchoolAI FERPA+COPPA Compliance Guide (2025), EdPrivacy "COPPA Updates 2025: What K-12 Schools Must Know", Instructure Privacy Center (privacy.instructure.com), Google Workspace for Education Privacy (edu.google.com/privacy), 1EdTech OneRoster Privacy Considerations*
