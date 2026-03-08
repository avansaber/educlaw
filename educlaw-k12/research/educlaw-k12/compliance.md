# Compliance & Regulatory Requirements: EduClaw K-12 Extensions

> **Frameworks:** IDEA, FERPA (K-12 extensions), State Immunization Laws
> **Date:** 2026-03-05

---

## 1. IDEA — Individuals with Disabilities Education Act

### 1.1 Overview

IDEA (20 U.S.C. §1400 et seq.) is the federal law ensuring students with disabilities (ages 3–21) receive Free Appropriate Public Education (FAPE) in the Least Restrictive Environment (LRE). Enacted in 1975, last reauthorized in 2004. Administered by the US Department of Education, Office of Special Education Programs (OSEP).

**IDEA applies to:** All public schools and LEAs (Local Education Agencies) receiving federal education funding. Private schools receiving federal funds must provide equitable services.

**Part B** (ages 3–21) is the relevant section for K-12 schools. Part C (birth–2) is handled by state early intervention agencies and is out of scope for EduClaw K-12.

---

### 1.2 The 13 IDEA Disability Categories

Students must qualify under one or more of these categories to receive an IEP:

| # | Category | Common Examples |
|---|----------|----------------|
| 1 | Specific Learning Disability (SLD) | Dyslexia, dyscalculia, dysgraphia |
| 2 | Speech or Language Impairment | Stuttering, articulation disorder, language processing |
| 3 | Other Health Impairment (OHI) | ADHD, asthma, epilepsy, Tourette's |
| 4 | Autism Spectrum Disorder (ASD) | Autism, Asperger's (historic) |
| 5 | Intellectual Disability | Down syndrome, cognitive delays |
| 6 | Emotional Disturbance | Anxiety, bipolar, ODD, depression |
| 7 | Developmental Delay | Late milestone achievement (ages 3–9 only) |
| 8 | Multiple Disabilities | Combination requiring specialized approach |
| 9 | Hearing Impairment / Deafness | Partial or complete hearing loss |
| 10 | Orthopedic Impairment | Cerebral palsy, limb differences |
| 11 | Visual Impairment / Blindness | Partial sight to blindness (not correctable) |
| 12 | Traumatic Brain Injury (TBI) | Acquired brain injury post-birth |
| 13 | Deaf-Blindness | Combined severe hearing and vision loss |

**Software requirement:** The IEP eligibility record must capture one or more disability categories from this standardized list.

---

### 1.3 Key IDEA Timelines and Mandates

| Requirement | Timeline | Software Implication |
|-------------|---------|---------------------|
| Evaluation consent to evaluation completion | **60 calendar days** | Track consent date; auto-flag when 60-day deadline approaches |
| Eligibility determination to IEP creation | **30 calendar days** | Track eligibility date; alert when 30-day IEP deadline approaches |
| IEP annual review | **Every 12 months** | Track IEP creation date; alert when annual review is due |
| Triennial re-evaluation | **Every 3 years** | Track last evaluation date; alert at 3-year mark |
| Transition services begin | **No later than age 16** | Auto-flag students turning 16 who lack transition goals |
| Parental consent required | At evaluation, IEP initial, placement | Consent records must be timestamped and immutable |
| Prior written notice | Before any change in services | Track notices sent to parents |
| Manifestation Determination Review (MDR) | Before suspension >10 days cumulative | Flag IDEA students when discipline approaches 10-day threshold |

---

### 1.4 IEP Required Components (34 CFR §300.320)

Each IEP must include all of the following. EduClaw K-12 must capture these as structured data:

1. **Present Levels of Academic Achievement and Functional Performance (PLAAFP)** — Current level description; how disability affects participation in general curriculum
2. **Measurable Annual Goals** — Academic and functional goals; measurable criteria
3. **Special Education Services** — Type, frequency, duration, location
4. **Related Services** — Speech, OT, PT, counseling, transportation
5. **Supplementary Aids and Services** — Classroom accommodations
6. **Program Modifications** — Modifications for general education participation
7. **Participation with Nondisabled Peers** — Extent of non-inclusion justification (LRE statement)
8. **State and District Assessment Accommodations** — Testing modifications
9. **IEP Dates** — Start date, end date (12-month max), review date
10. **Transition Plan** (age 16+) — Postsecondary goals: education, employment, independent living
11. **Progress Reporting Schedule** — How often parents receive progress reports

---

### 1.5 IEP Team Required Members (34 CFR §300.321)

The following must be documented as IEP team members:

- Parent(s) or guardian(s) — always required
- At least one general education teacher (if student participates in general ed)
- At least one special education teacher
- School representative (administrator who can commit resources)
- Someone who can interpret evaluation results (school psychologist or similar)
- Other relevant parties (at parent or school discretion)
- Student (when appropriate, required for transition at age 16+)

---

### 1.6 Discipline and IDEA — Manifestation Determination

When a student with an IEP is subject to discipline (suspension, expulsion):

- **10-day rule:** School may suspend a student with a disability for up to 10 school days per year without triggering IDEA protections
- **Beyond 10 days:** A **Manifestation Determination Review (MDR)** must occur within 10 school days
- **MDR question 1:** Was the conduct caused by, or directly and substantially related to, the student's disability?
- **MDR question 2:** Was the conduct a direct result of the school's failure to implement the IEP?
- **If yes to either:** Conduct is a manifestation → return to placement; conduct functional behavior assessment
- **If no:** May apply same discipline as non-disabled student

**Software requirement:**
- Discipline module must flag IDEA-eligible students when cumulative suspensions approach 10 days
- MDR workflow must be captured as a separate record linked to the discipline incident
- MDR outcome (manifestation vs. not) must be recorded

---

### 1.7 IDEA State Reporting Requirements (IDEA Part B)

Schools must report to state education agencies annually:
- **Child Count** (December 1 count): Number of students with disabilities by age and disability category
- **Educational Environments** (LRE data): Time spent in general ed settings
- **Discipline Data**: Suspensions/expulsions of students with disabilities
- **Disproportionality**: Identification, placement, and discipline rates by race/ethnicity
- **Evaluation Timelines**: Compliance with 60-day evaluation timeline
- **Annual Goals/Progress**: Aggregate IEP goal progress data

**Software requirement:** Must support export of IDEA data in standard formats (OSEP data model); support CEDS (Common Education Data Standards) coding.

---

### 1.8 Section 504 (Rehabilitation Act)

Section 504 is a **civil rights law** (not IDEA) that prohibits discrimination against students with disabilities. Students who don't qualify for IDEA IEPs may qualify for 504 accommodation plans.

**Key differences from IEP:**
| | IEP | 504 Plan |
|-|-----|---------|
| Law | IDEA | Rehabilitation Act / ADA |
| Eligibility | 13 disability categories + adverse effect | Any disability that limits a major life activity |
| Document | Detailed legal document | Less formal accommodation plan |
| Funding | Federal special ed funding | No separate federal funding |
| Team | Formal multidisciplinary team | Typically simpler team |
| Procedural safeguards | Extensive (IDEA §615) | Less formal |

**EduClaw requirement:** 504 plans need a simplified workflow — eligibility determination, accommodation list, team sign-off — without the full IEP pipeline.

---

## 2. FERPA — K-12 Specific Extensions

### 2.1 FERPA Recap

The parent EduClaw product implements FERPA for grades, attendance, and financial records. K-12 extensions must extend FERPA compliance to health records, discipline records, and special education records.

**Key FERPA principle for K-12:** Parents (not students) hold FERPA rights for students under 18. Rights transfer to students at age 18 or upon enrollment in post-secondary institution.

---

### 2.2 Health Records Under FERPA

**Critical clarification (2023 DOE guidance):**
- Student health records **maintained by the school** are **education records** under FERPA, not HIPAA
- HIPAA does not apply to K-12 school health records (only to covered healthcare entities)
- Exception: Records made by a licensed professional used exclusively for treatment purposes may qualify as "treatment records" — but only if not disclosed outside treatment team
- Once treatment records are shared for any purpose other than treatment, they become education records subject to full FERPA protections

**Practical implication for EduClaw:**
- All health profile, office visit, medication log, and immunization records are **education records**
- Every access to health records must be FERPA-logged (`educlaw_data_access_log` with `data_category = 'health'`)
- Parents must be able to access and request corrections to health records
- Disclosure requires parental consent unless an FERPA exception applies

**Key FERPA exceptions relevant to health:**
- **Health/safety emergency:** Health information can be shared without consent in genuine emergencies (34 CFR §99.36)
- **School officials with legitimate educational interest:** School nurse and relevant staff can access without consent
- **State and local authorities:** Required for immunization reporting to state health departments

---

### 2.3 Discipline Records Under FERPA

- Student discipline records are **education records** subject to FERPA
- Cannot be shared with third parties without consent
- **Within school:** Can be shared with staff who have legitimate educational interest (no consent needed)
- **Transfer:** When a student transfers, discipline information can be shared with the receiving school without consent (34 CFR §99.34)
- **Law enforcement records:** Records created by school law enforcement units are NOT education records (but school-maintained discipline records about the same incident are)
- **IDEA discipline records:** Have additional IDEA confidentiality protections (34 CFR §300.610–300.626)

**Software requirement:**
- Discipline record access must be FERPA-logged
- Role-based access: teachers see records for their students; counselors see more; administrators see all
- Transfer disclosure must be documented

---

### 2.4 Special Education Records Under FERPA + IDEA

Special education records have **dual protection** under both FERPA and IDEA:

- IDEA 34 CFR §300.610–300.626 establishes additional confidentiality requirements
- Parents must be notified of their privacy rights annually
- Parents have the right to inspect and review all education records (including IEP) within 45 days of request
- IEP records must be maintained for at least 5 years after student exits special education (varies by state; some require 7–10 years)
- Upon student leaving special education or graduating, parents must be notified that records may be destroyed after retention period

**Software requirement:**
- IEP and evaluation records are the most sensitive education records — log all access
- Immutable audit trail of all IEP amendments (no in-place editing)
- Record retention dates must be tracked per student exit date

---

### 2.5 FERPA Data Access Logging Requirements for K-12

The parent EduClaw already has `educlaw_data_access_log` with categories:
`'demographics','grades','attendance','financial','health','discipline','communications'`

K-12 extensions must:
1. **Log every health record access** with `data_category = 'health'`
2. **Log every discipline record access** with `data_category = 'discipline'`
3. **Log every special education record access** with `data_category = 'special_education'` ← new category needed

**Proposed addition to parent schema:** Add `'special_education'` to the `data_category` CHECK constraint in `educlaw_data_access_log`. This is a parent schema change coordinated with the educlaw team.

---

## 3. State Immunization Laws

### 3.1 Overview

Every US state has laws requiring proof of immunization for K-12 school enrollment. Requirements vary significantly by state. There is no single federal school immunization standard — states legislate their own based on CDC/ACIP recommendations.

**Key federal reference:** CDC's Advisory Committee on Immunization Practices (ACIP) publishes the recommended childhood immunization schedule. States typically adopt some or all of this schedule.

---

### 3.2 Common Required Vaccines (Most States)

| Vaccine | Common Grade-Level Requirement |
|---------|-------------------------------|
| DTaP (Diphtheria, Tetanus, Pertussis) | Kindergarten entry; booster (Tdap) at 6th–7th grade |
| MMR (Measles, Mumps, Rubella) | Kindergarten entry (2 doses) |
| Varicella (Chickenpox) | Kindergarten entry (1–2 doses or proof of prior infection) |
| Hepatitis B | Kindergarten entry (3-dose series) |
| Polio (IPV) | Kindergarten entry (4 doses) |
| Meningococcal (MenACWY) | 6th–7th grade entry; booster 11th–12th grade |
| HPV | Recommended 11–12; not mandated in most states |
| Hepatitis A | Some states (CA, AZ, NY) for kindergarten |
| COVID-19 | Currently no state mandates (as of 2026) |

**Software requirement:** Vaccine catalog must include CVX codes (CDC standard codes for vaccines). Compliance rules are **grade-level specific**, not just school-level.

---

### 3.3 Exemption Types

| Exemption Type | Availability | Details |
|----------------|-------------|---------|
| Medical exemption | All states | Physician-certified contraindication; must be renewed periodically |
| Religious exemption | ~45 states | Parent declaration of sincere religious belief; some require notarization |
| Philosophical/personal belief | ~15 states | General personal belief objection; California eliminated in 2016 |

**Note:** California, New York, Maine, and West Virginia **do not** allow non-medical exemptions. Post-COVID, several states have tightened exemption laws.

**Software requirement:**
- Waivers must store type (medical/religious/philosophical), expiry date, and issuing authority
- Medical exemptions must include physician information
- Flag when waivers expire

---

### 3.4 Provisional Enrollment

Most states allow **provisional enrollment** — attending school while completing a catch-up vaccination schedule — for a limited period (typically 30 days after enrollment start).

- 28 states reported students attending under grace period or provisional enrollment (CDC MMWR 2022–23 data)
- Provisional enrollment must be tracked with deadlines
- Students not completing catch-up by deadline must be excluded from school

**Software requirement:**
- Health profile must have `provisional_enrollment_end_date`
- System must flag students whose provisional period is expiring

---

### 3.5 State Reporting Requirements

Schools must report immunization data to state health departments annually:
- **Annual Immunization Status Report (AISR):** Aggregate count of immunized vs. exempt students by grade
- Schools are responsible for ensuring compliance before reporting
- Some states require individual student-level reporting to state immunization information systems (IIS)
- Non-compliance with immunization laws can result in school losing state funding

**Software requirement:**
- Generate school-level immunization compliance summary by grade level
- Flag non-compliant students with specific missing vaccines
- Export in formats suitable for state reporting

---

### 3.6 Immunization Information Systems (IIS)

All 50 states have an Immunization Information System (IIS) — a centralized, population-based database of vaccination records. Magnus Health and other systems offer API integration with state IIS systems.

**Software requirement for EduClaw K-12:**
- Manually entered immunization records are sufficient for v1
- API integration with state IIS is a v2 feature
- Mark immunization records with `source` field: `manual`, `iis_sync`, `provider_import`

---

## 4. Other Relevant Regulatory Considerations

### 4.1 Child Abuse Mandatory Reporting

School personnel (including administrators who access discipline and health records) are **mandatory reporters** of suspected child abuse or neglect in all 50 states.

**Software implication:**
- Discipline and health incidents involving potential abuse may trigger mandatory reporting
- System should allow flagging an incident as "potential mandatory report"
- Documentation of report made (date, agency, reporter) should be attached to incident

### 4.2 IDEA Disproportionality (34 CFR §300.646)

States must identify school districts with **significant disproportionality** in:
- Identification of students with disabilities by race/ethnicity
- Placement in restrictive settings by race/ethnicity
- Discipline (suspension/expulsion) by race/ethnicity

**Software implication:**
- Discipline incidents must capture student demographic data (race/ethnicity — from parent `educlaw_student` demographic fields)
- Special education eligibility decisions must capture race/ethnicity
- System must be able to generate disproportionality analysis reports

### 4.3 McKinney-Vento Homeless Assistance Act

Students experiencing homelessness have special enrollment rights including immediate enrollment without immunization records.

**Software implication:**
- Immunization compliance can be flagged as `deferred_mckinney_vento` for homeless students
- Health profile should note McKinney-Vento status

### 4.4 Title IX (Discipline)

Sexual harassment and assault incidents have specific Title IX reporting and response requirements. Discipline records related to Title IX must be maintained separately and handled with additional privacy protections.

**Software implication:**
- Discipline incident type should include `sexual_harassment` and `sexual_assault` with additional access restrictions
- Title IX coordinator must be notified of applicable incidents (system trigger)

---

## 5. Compliance Checklist for EduClaw K-12

### Special Education (IDEA)
- [ ] 13 disability categories stored as structured enum
- [ ] Evaluation consent date captured; 60-day deadline auto-calculated and alerted
- [ ] Eligibility determination date captured; 30-day IEP deadline auto-calculated
- [ ] IEP annual review date tracked; alert 30 days before due
- [ ] Triennial re-evaluation tracked; alert 90 days before due
- [ ] IEP team members captured with roles
- [ ] IEP goals are measurable (baseline, target, measurement method, frequency)
- [ ] Service delivery minutes: planned vs. actual tracked
- [ ] Transition plan required at age 16 (auto-flag)
- [ ] Progress reports aligned with report card schedule
- [ ] MDR workflow triggered at 10-day suspension threshold
- [ ] IDEA access logged via FERPA access log

### Health Records (FERPA + State Immunization)
- [ ] Health record access logged (`data_category = 'health'`)
- [ ] Immunization records use CVX codes
- [ ] Exemption types: medical/religious/philosophical with expiry
- [ ] Provisional enrollment end date tracked
- [ ] Grade-level immunization compliance check
- [ ] State compliance report (aggregate by grade/vaccine)
- [ ] Mandatory reporting flag on health and discipline incidents
- [ ] McKinney-Vento immunization deferral flag

### Discipline (FERPA + IDEA + Title IX)
- [ ] Discipline access logged (`data_category = 'discipline'`)
- [ ] IDEA student MDR trigger at cumulative 10-day threshold
- [ ] Title IX incident type with restricted access
- [ ] Parent notification timestamped and logged
- [ ] State discipline reporting codes (CEDS standard)
- [ ] Disproportionality report by race/ethnicity

### Grade Promotion (State Law)
- [ ] Parent notification before May 1 for retention decisions (configurable date)
- [ ] Multi-stakeholder team documented for retention decisions
- [ ] Decision rationale recorded and immutable
- [ ] Intervention plan required for retained students
