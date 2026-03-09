# Competitor Analysis: EduClaw K-12 Extensions

> **Focus:** Discipline management, health records, special education, grade promotion
> **Date:** 2026-03-05

---

## 1. Commercial Competitors

### 1.1 PowerSchool SIS + Behavior Support

**Overview:** PowerSchool is the dominant K-12 SIS vendor, used by over 55 million students globally. Their platform includes a dedicated Behavior Support module and incident management system.

**Discipline Features:**
- **Incident Management Module**: Records and reports all discipline and truancy incidents, replacing traditional "log entries" with structured data capture
- **Incident Builder**: Three-section model — (1) Incident Description, (2) Incident Builder (involved parties), (3) Incident Elements (consequences)
- **Behavior Dashboard**: Tracks positive and corrective behaviors; PBIS-aligned framework that approaches incidents from an intervention lens rather than punitive
- **Multi-year tracking**: Behavior patterns visible across multiple academic years
- **Integration**: Full integration with PowerSchool SIS (enrollment, attendance, GPA)
- **State reporting**: Generates discipline reports for state compliance
- **Parent notifications**: Automated notifications to guardians for discipline events
- **Equity reports**: Identifies disproportionate discipline by race/ethnicity per IDEA requirements

**Health Features:**
- Integration with third-party health platforms (Magnus Health) — not native
- Some immunization tracking in base SIS

**Special Education Features:**
- Dedicated Special Programs module
- IEP creation and management
- Progress monitoring and goal tracking
- Integration with Frontline Education for deeper IEP workflow

**Grade Promotion Features:**
- At-risk student identification via GPA and attendance thresholds
- No dedicated promotion/retention workflow — handled through reporting + manual process

**Pricing:** $20–40/student/year for full platform
**Target Market:** Large public school districts (10,000+ students)
**Key Weakness:** 2023 data breach exposed 6,500+ school districts; trust issues persist. Complex UI requires dedicated IT support. Prohibitively expensive for small/private schools.

**Sources:** PowerSchool.com; PowerSchool discipline documentation (ps-compliance.powerschool-docs.com)

---

### 1.2 Infinite Campus

**Overview:** Second-largest K-12 SIS vendor. Strong in behavior management, IEP/504 tracking, and health records. Known for centralized, district-scale data management.

**Discipline Features:**
- Behavior tracking with incident logging
- Consequence assignment and tracking
- Truancy management
- PBIS behavior framework support
- Parent and student portal integration for real-time discipline alerts
- Disproportionality reporting for IDEA compliance

**Health Features:**
- Student health records module
- Immunization tracking
- Medication management
- Health screening documentation

**Special Education Features:**
- **IEP Creation & Amendment**: Full IEP document creation with team management
- **IEP Team Management**: Assign team members from student household, schedule, or staff list; add all teachers at once; print active team
- **504 Plan Management**: Similar team and document management as IEP
- **Document Archive**: Full document history and versioning
- **State Reporting**: Special ed state submission support
- **Progress Monitoring**: Goal progress per reporting period

**Grade Promotion Features:**
- Grade-level dashboards showing at-risk students by GPA/attendance
- No dedicated promotion/retention decision workflow

**Pricing:** $15–30/student/year for full platform
**Target Market:** Mid-to-large public school districts (2,000–50,000 students)
**Key Weakness:** High cost; requires significant IT infrastructure; not suitable for single-school private institutions.

**Sources:** Infinite Campus documentation; CCSD Infinite Campus IEP User Guide (ccsd.net)

---

### 1.3 Frontline Education — Special Education Management

**Overview:** Frontline is the market leader in dedicated K-12 special education software. Their Special Education Management product (formerly Excent/Enrich/eSped) is widely considered the gold standard for IEP compliance management.

**Discipline Features:** Not a primary focus (separate product line)

**Health Features:** Separate health management product

**Special Education Features (Most Comprehensive):**
- **Pre-referral workflow**: Documents RTI/MTSS interventions before formal referral
- **Evaluation management**: Timeline tracking, evaluation team assignments, consent tracking
- **IEP creation**: WYSIWYG editor with state-specific templates; real-time document sharing
- **Role-based access**: Different views for teachers, special ed coordinators, administrators
- **Progress monitoring**: Frequency scheduling, data graphing, trend analysis, auto-alerts when monitoring is due
- **Service delivery tracking**: Dynamic dashboards contrasting planned vs. actual service minutes; alerts for documentation lag; Medicaid billing support
- **State compliance validation**: Data validated at point of entry; state-specific report generation
- **Transition planning**: Postsecondary goals tracking (required at age 16)
- **Parent portal**: Secure parent access to IEP documents and progress
- **Multi-language support**: Family engagement in non-English languages

**Grade Promotion:** Not in scope

**Pricing:** ~$10–20/student/year (special ed students only); separate from SIS
**Target Market:** School districts of all sizes that need best-in-class IEP management
**Key Weakness:** Standalone product — requires integration with SIS (PowerSchool, Infinite Campus). Not suitable for schools that want an all-in-one system.

**Sources:** Frontline Education website (frontlineeducation.com); G2 reviews

---

### 1.4 Magnus Health — Student Health Management

**Overview:** Magnus Health is a leading cloud-based student health management platform focused on school nurse workflows. It integrates with major SIS platforms.

**Health Features:**
- **Centralized health records**: FERPA- and HIPAA-compliant centralized digital health files
- **Immunization tracking**: Auto-sync with state vaccine registries; upcoming deadline alerts; smart lists for non-compliant students; on-demand state compliance audit reports
- **Medication management**: Dosage/frequency tracking; administration charting; quantity auditing; parent communication for supply levels
- **Office visit documentation**: Customizable treatment note templates; pre-filled notes with automated alerts; injury/illness tracking
- **Emergency response (Magnus911)**: Immediate vital health information access during emergencies; emergency contact notification
- **Smart lists**: Group students by grade, sport, or health condition for bulk reporting
- **SIS integration**: Syncs with major SIS platforms; also syncs with state immunization registries (IIS)
- **Allergy management**: Allergy alerts surfaced to relevant staff

**Discipline Features:** None
**Special Education Features:** None
**Grade Promotion Features:** None

**Pricing:** ~$4–8/student/year
**Target Market:** K-12 schools of all sizes; school nurses as primary user
**Key Weakness:** Standalone health-only tool; requires separate purchase from SIS. No discipline or special ed integration.

**Sources:** Magnus Health website (magnushealth.com)

---

### 1.5 SchoolDoc

**Overview:** Dedicated school nurse EHR software designed by school nurses. Strong UX focus.

**Health Features:**
- Student health record management
- Immunization tracking with state-specific requirements
- Medication administration log
- Office visit documentation
- Allergy tracking
- Health forms management
- Behavioral health tracking
- Illness/injury tracking

**Other Features:** None
**Pricing:** ~$3–6/student/year
**Target Market:** Small-to-mid K-12 schools
**Key Weakness:** Very limited scope; no integration with SIS discipline or special ed.

**Sources:** SchoolDoc website (schooldoc.com)

---

### 1.6 Aimsweb Plus / FastBridge (Pearson / Renaissance)

**Overview:** Progress monitoring and assessment tools used for special education eligibility and IEP goal monitoring.

**Special Education Relevance:**
- Curriculum-based measurement (CBM) for reading and math
- Screening for special ed eligibility evaluation
- Progress monitoring data that feeds into IEP goal tracking
- MTSS data collection

**Key Relevance to EduClaw:** These tools generate the assessment data that feeds into IEP progress monitoring. EduClaw K-12 should be able to record/import progress monitoring scores as IEP goal progress notes.

---

### 1.7 SapphireK12

**Overview:** A school management platform with a dedicated school nurse health system module.

**Health Features:**
- Immunization management integrated into broader SIS
- Student health profile
- Office visit tracking
- Nurse-to-parent messaging

**Key Differentiation:** Attempts to integrate health with full SIS — similar to EduClaw's approach.

---

## 2. Open-Source Competitors

### 2.1 OpenSIS (Community Edition)

**Overview:** OpenSIS is an open-source SIS with commercial support options. One of the most widely deployed open-source school management systems globally.

**Discipline Features:** Basic discipline/incident logging in commercial version; limited in community edition
**Health Features:** Very limited; no dedicated module
**Special Education Features:** Not present in open-source version
**Grade Promotion Features:** Basic grade promotion in commercial version

**Key Gap vs. EduClaw:** OpenSIS community edition lacks all four K-12 extension domains. Commercial version requires paid upgrade.

---

### 2.2 Fedena

**Overview:** Rails-based open-source school management system.

**Discipline Features:** Basic behavioral incident logging module
**Health Features:** None significant
**Special Education Features:** None
**Grade Promotion Features:** Basic promotion module

**Key Gap vs. EduClaw:** No IEP/504 support; no immunization compliance; no FERPA/IDEA compliance built in.

---

### 2.3 GegoK12

**Overview:** Modern open-source school management system (MIT License) on GitHub.

**Discipline Features:** Unknown/limited
**Health Features:** Unknown/limited
**Special Education Features:** Not found
**Grade Promotion Features:** Unknown/limited

**Key Gap vs. EduClaw:** No evidence of IDEA-compliant special education module or health records.

---

### 2.4 SEIS — Special Education Information System (California)

**Overview:** State-run (California) web application for IEP management. Free for California LEAs.

**Special Education Features:**
- IEP creation and management
- State reporting
- Timeline tracking

**Key Gaps:** California-only; poor UX (aging system); no integration with ERP; no health, discipline, or promotion features.

---

### 2.5 IEP-IPP (SourceForge)

**Overview:** Basic open-source IEP document management tool.

**Special Education Features:** IEP goal entry; limited tracking
**Key Gaps:** No longer actively maintained; no FERPA compliance; no service delivery tracking; no state reporting.

---

## 3. Feature Gap Analysis

The following matrix shows which domains each competitor covers:

| Competitor | Discipline | Health Records | Special Ed (IEP) | Grade Promotion | SIS Integration | ERP/Accounting |
|-----------|:----------:|:--------------:|:----------------:|:---------------:|:--------------:|:---------------:|
| PowerSchool | ✅ Full | ⚠️ Partial | ⚠️ Partial | ❌ | ✅ Native | ❌ |
| Infinite Campus | ✅ Full | ✅ Full | ✅ Full | ❌ | ✅ Native | ❌ |
| Frontline Education | ❌ | ❌ | ✅ Best-in-class | ❌ | ⚠️ Integration | ❌ |
| Magnus Health | ❌ | ✅ Best-in-class | ❌ | ❌ | ⚠️ Integration | ❌ |
| SchoolDoc | ❌ | ✅ Good | ❌ | ❌ | ⚠️ Limited | ❌ |
| OpenSIS (Community) | ⚠️ Basic | ❌ | ❌ | ⚠️ Basic | ✅ Native | ❌ |
| Fedena | ⚠️ Basic | ❌ | ❌ | ⚠️ Basic | ✅ Native | ❌ |
| **EduClaw K-12 (target)** | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ✅ Native | ✅ **Unique** |

**EduClaw K-12 unique value proposition:** The only open-source system combining all four K-12 extension domains *plus* full ERP accounting integration through the parent EduClaw product.

---

## 4. Pricing Comparison

| Solution | Model | Cost |
|----------|-------|------|
| PowerSchool (full suite) | Commercial | $20–40/student/year |
| Infinite Campus | Commercial | $15–30/student/year |
| Frontline Special Ed | Commercial add-on | $10–20/sped student/year |
| Magnus Health | Commercial add-on | $4–8/student/year |
| SchoolDoc | Commercial | $3–6/student/year |
| OpenSIS Community | Open-source | Free (limited features) |
| **EduClaw K-12** | Open-source | **Free** (self-hosted) |

---

## 5. Architecture Insights from Competitors

### 5.1 Discipline Data Model (from PowerSchool documentation)
- Incidents have a **header record** (date, location, type) and **child records** (per student involvement)
- Each involved student has an independent **consequence/action** record
- State reporting uses **standardized incident type codes** (aligned with Common Education Data Standards / CEDS)
- Incidents can involve **multiple students** and **multiple staff members**
- **Manifestation determination** is a separate workflow for IDEA-eligible students

### 5.2 Health Records Data Model (from Magnus Health)
- **Health profile** is separate from office visit log (chronic conditions vs. acute visits)
- Immunization records link to a **vaccine catalog** with CVX codes (CDC vaccine codes)
- Waivers/exemptions tracked separately with expiry dates
- Medication records separate **prescription catalog** from **administration log**
- State immunization compliance uses **grade-level rules** (different vaccines required at K, 6th, 9th grade entry)

### 5.3 Special Education Data Model (from Frontline + Infinite Campus)
- **Referral → Evaluation → Eligibility → IEP** is a strict linear pipeline
- IEP is a **versioned document** (amendments create new versions, not overwrites)
- Goals are **measurable** with baseline, target, frequency of monitoring, and measurement method
- Services have **planned minutes** (from IEP) vs **delivered minutes** (from session logs)
- IEP team is a **many-to-many** between students and staff/parents with role assignments
- Progress notes are created **per reporting period** per goal (not continuous)
- **Manifestation Determination Review (MDR)** is required before suspending IDEA students 10+ days

### 5.4 Grade Promotion Data Model (from district policy documents)
- Promotion criteria are **configurable per grade level** (not one-size-fits-all)
- Review is triggered at a **date threshold** (typically April/May)
- Decision involves **multiple stakeholders** with documented rationale
- Intervention plans are **attached to retention decisions** with follow-up dates
- Parent notification has a **legal deadline** (varies by state; typically May 1 for public schools)
