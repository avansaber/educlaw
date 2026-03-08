# Core Business Workflows: EduClaw K-12 Extensions

> **Domains:** Discipline, Health Records, Special Education, Grade Promotion
> **Date:** 2026-03-05

---

## Domain 1: Discipline Management

### Workflow 1.1: Discipline Incident Reporting (Happy Path)

**Trigger:** Teacher, administrator, or other staff observes or is notified of a student behavior incident.

**Steps:**

```
1. STAFF observes incident
   → Record incident header:
      - Date, time, location (room, hallway, cafeteria, bus, off-campus)
      - Incident type (see type taxonomy)
      - Severity level (minor / moderate / major / emergency)
      - Description (free text narrative)
      - School year and term

2. ADD involved parties
   → For each student involved:
      - Assign role: offender / victim / witness / bystander
      - Note if student is IDEA-eligible (triggers MDR monitoring)
   → For each staff involved:
      - Assign role: reporting staff / responding administrator / witness

3. RECORD consequences (per involved student)
   → Action type: verbal_warning / parent_contact / detention /
     in_school_suspension / out_of_school_suspension /
     expulsion_referral / counseling_referral /
     law_enforcement_referral / restorative_practice /
     community_service / loss_of_privilege / other
   → Start date and duration (for suspensions)
   → Administered by (staff member)

4. NOTIFY guardians
   → Auto-create guardian notification for each involved student
   → Notification method: phone / email / written notice
   → Record notification date/time and who made contact
   → FERPA-log: data_category = 'discipline'

5. CHECK IDEA compliance (automated)
   → If student has active IEP/504:
      a. Count cumulative suspension days this year
      b. If approaching 10 days: flag for MDR workflow (→ Workflow 1.2)
      c. If expulsion: MDR is mandatory before proceeding

6. CLOSE incident
   → Admin reviews and approves incident record
   → Record is immutable after closing (can be amended with reason)
```

**Decision Points:**
- **Is student IDEA-eligible?** → Triggers MDR monitoring counter
- **Suspension > 10 cumulative days?** → MDR required
- **Expulsion?** → MDR required; legal notice to parents required
- **Criminal act?** → Law enforcement referral + Title IX consideration for sexual offenses
- **Mandatory reporting?** → Flag for child protective services contact

**Data Flow:**
- Incident → Notification → `educlaw_notification` (notification_type = 'discipline_incident')
- Incident → FERPA log → `educlaw_data_access_log`
- Suspension → Student status update → `educlaw_student.status = 'suspended'`
- Expulsion → `educlaw_student.status = 'expelled'`

---

### Workflow 1.2: Manifestation Determination Review (MDR)

**Trigger:** IDEA-eligible student faces suspension exceeding 10 school days in a year.

**Steps:**

```
1. SYSTEM flags when IDEA student approaches 10-day threshold
   → Alert sent to special education coordinator and administrator

2. IEP TEAM convenes (within 10 days of decision to suspend > 10 days)
   → Record MDR meeting date
   → Team: parents, special ed teacher, admin, relevant staff

3. REVIEW two MDR questions:
   Question 1: Was conduct caused by or directly related to student's disability?
   Question 2: Was conduct result of school's failure to implement IEP?

4. RECORD determination:
   Option A: YES (manifestation) →
      - Return student to current placement (unless weapons/drugs/serious injury)
      - Conduct Functional Behavioral Assessment (FBA)
      - Develop or revise Behavioral Intervention Plan (BIP)
      - Record in IEP

   Option B: NO (not a manifestation) →
      - Apply same discipline as non-disabled student
      - Continue providing FAPE services during suspension
      - Document educational services plan during removal

5. NOTIFY parents in writing
   → Written notice of MDR outcome
   → Notice of IDEA procedural safeguards
   → Notice of right to appeal via due process
```

**Data Flow:**
- MDR record links to: discipline_incident + IEP record + student
- MDR outcome determines: whether FBA/BIP process begins
- Parent notification is a legal requirement — must be timestamped

---

### Workflow 1.3: PBIS Positive Behavior Tracking

**Trigger:** Teacher or staff wants to recognize positive student behavior.

**Steps:**
```
1. RECORD positive behavior recognition:
   → Student, date, behavior type, teacher, recognition type (praise, points, award)

2. VIEW student behavior dashboard:
   → Positive vs. corrective incident ratio
   → Behavior trend over time
   → Comparison to school/grade average

3. GENERATE PBIS reports:
   → School-wide positive behavior rate
   → Students with high discipline frequency (early warning)
   → Behavior by location, time, type
```

---

### Discipline Incident Type Taxonomy

```
Minor Infractions:
  - tardy / dress_code / unauthorized_electronic_device
  - disruptive_behavior / disrespectful_language / classroom_disruption

Moderate Infractions:
  - bullying / harassment / physical_altercation_minor
  - theft / vandalism / cheating / truancy / insubordination

Major Infractions:
  - fighting / assault / weapons / drugs_alcohol / sexual_harassment
  - threats / extortion / arson / gang_activity

Emergency/Criminal:
  - sexual_assault / serious_assault / weapons_possession
  - bomb_threat / active_threat
```

**CEDS Standard Codes:** All incident types should map to CEDS (Common Education Data Standards) discipline incident type codes for state reporting.

---

## Domain 2: Health Records

### Workflow 2.1: Enrollment Health Form Processing

**Trigger:** New student enrolls in school. School requires completion of health forms.

**Steps:**

```
1. COLLECT health forms from parent/guardian:
   → Medical history, allergies, conditions, physician information
   → Emergency contact (beyond what's in student record)
   → Medications to be administered at school
   → Immunization records or waiver

2. CREATE health profile:
   → Link to educlaw_student record
   → Enter allergies (type, severity, reaction, treatment, EpiPen location)
   → Enter chronic conditions (asthma, diabetes, epilepsy, etc.)
   → Enter physician contact information
   → Enter emergency health procedures

3. PROCESS immunizations:
   → For each required vaccine:
      a. Enter vaccine name (CVX code), dose number, date administered, lot number, provider
      b. If waiver: enter waiver type, basis, expiry date
      c. If missing: mark as non-compliant, set provisional period if applicable

4. CHECK compliance:
   → Auto-compare entered immunizations against state/grade-level requirements
   → Flag non-compliant or missing vaccines
   → Set provisional enrollment end date if applicable

5. PROCESS medications:
   → For each medication:
      a. Enter drug name, dosage, frequency, prescribing physician
      b. Upload physician authorization (required in most states)
      c. Note storage requirements
      d. Note administration instructions

6. VERIFY and LOCK health profile:
   → School nurse reviews and verifies all information
   → Flag any immediate health concerns for relevant teachers
   → Generate allergy alert list for classroom teachers
```

---

### Workflow 2.2: Office Visit / Nurse Visit

**Trigger:** Student comes to the health office with a complaint, injury, or illness.

**Steps:**

```
1. STUDENT arrives at health office
   → Record arrival time, student identity

2. ASSESS and DOCUMENT:
   → Chief complaint (headache, stomach, injury, etc.)
   → Vital signs if applicable (temperature, pulse)
   → Assessment findings
   → Treatment provided
   → Medications administered (→ triggers Workflow 2.3)

3. DETERMINE disposition:
   → returned_to_class / sent_home / 911_called / referred_to_physician / observation

4. IF sent home:
   → Contact parent/guardian
   → Record who was contacted, contact time
   → Record parent response

5. IF emergency:
   → Access emergency health information (Magnus911-equivalent)
   → Call 911
   → Contact emergency contacts in order
   → FERPA emergency exception applies (no consent needed to share health info)

6. RECORD visit:
   → Visit is immutable once saved
   → FERPA log: data_category = 'health'
```

---

### Workflow 2.3: Medication Administration

**Trigger:** Scheduled medication time or student-initiated request for PRN (as-needed) medication.

**Steps:**

```
1. IDENTIFY student and medication from active medication list
   → Verify student identity
   → Check medication is currently authorized
   → Check dosage schedule

2. ADMINISTER medication:
   → Record: date, time, medication, dose given, route, administered_by
   → Note any observations (student reaction, side effects)

3. LOG administration:
   → Every administration must be logged (liability requirement)
   → Immutable record — cannot be edited after saving

4. TRACK supply:
   → Decrement supply count
   → Alert when supply is low (auto-notify parent)

5. HANDLE refusals:
   → If student refuses: log refusal with reason
   → Notify parent if required by physician order
```

---

### Workflow 2.4: Immunization Compliance Audit

**Trigger:** Beginning of school year, new enrollment, or state reporting deadline.

**Steps:**

```
1. RUN compliance check:
   → For each enrolled student:
      a. Get student grade level
      b. Compare immunization records against grade-level requirements
      c. Flag non-compliant vaccines
      d. Check waiver validity and expiry

2. GENERATE non-compliance list:
   → Students missing vaccines
   → Students with expiring waivers
   → Students in provisional period with approaching deadline

3. NOTIFY parents:
   → Auto-generate notifications to parents of non-compliant students
   → Record notification date

4. EXCLUDE students (last resort):
   → If student fails to comply by deadline
   → Must follow state-specific process
   → Record exclusion action

5. GENERATE state report:
   → Aggregate by grade level
   → Counts: fully vaccinated / partially vaccinated (provisional) / waiver / non-compliant
   → Export for state Annual Immunization Status Report
```

---

## Domain 3: Special Education

### Workflow 3.1: Pre-Referral and Referral

**Trigger:** Teacher, parent, or other party has concerns about a student's learning or behavior.

**Steps:**

```
1. PRE-REFERRAL interventions (MTSS/RTI):
   → Document interventions already tried in general education
   → Collect data on intervention effectiveness
   → Meet with support team (teacher, counselor, admin)

   [Decision: Is the student sufficiently supported?]
   → YES: Continue monitoring
   → NO: Proceed to formal referral

2. FORMAL REFERRAL:
   → Referral submitted by: teacher / parent / other professional
   → Referral date recorded (starts clock)
   → Referral reason and areas of concern
   → Attach prior intervention documentation

3. OBTAIN PARENTAL CONSENT for evaluation:
   → Send Prior Written Notice and consent form to parents
   → Record consent request date
   → If consent received: record consent date → start 60-day evaluation clock
   → If consent denied: record denial; school cannot evaluate (FERPA)
   → If no response in 10 days: follow state-specific process

4. ASSIGN evaluation team:
   → School psychologist (assessment coordinator)
   → General education teacher
   → Relevant specialists (speech pathologist, OT, etc.)
```

---

### Workflow 3.2: Evaluation and Eligibility Determination

**Trigger:** Parental consent obtained for evaluation.

**Steps:**

```
1. CONDUCT evaluations (within 60 calendar days of consent):
   → Record each evaluation type:
      - Psychological assessment
      - Academic achievement testing
      - Speech/language evaluation
      - Occupational therapy evaluation
      - Physical therapy evaluation
      - Hearing/vision screening
      - Social/behavioral assessment
      - Classroom observation
   → Record evaluator, date, instrument used

   [SYSTEM: Auto-flag if 60-day deadline approaches]

2. COMPILE evaluation results:
   → Each evaluator enters findings and scores
   → Overall summary of strengths and needs

3. ELIGIBILITY MEETING:
   → Team convenes (parents + school team)
   → Review all evaluation data
   → Apply two-part IDEA test:
      Part 1: Does student meet criteria for one of 13 disability categories?
      Part 2: Does disability adversely affect educational performance?

   [Decision: Eligible?]
   → YES: Record eligibility determination, disability category(ies)
           → Proceed to IEP (Workflow 3.3) — must begin within 30 days
   → NO: Record ineligibility determination
          → Notify parents of rights; consider Section 504 (Workflow 3.5)

4. DOCUMENT eligibility:
   → Record: disability category, determination date, team members present
   → Parents sign eligibility document
   → 30-day IEP clock starts on eligibility date
   → FERPA log: data_category = 'special_education'
```

---

### Workflow 3.3: IEP Development

**Trigger:** Student determined eligible for IDEA services. IEP must be written within 30 days.

**Steps:**

```
1. SCHEDULE IEP meeting:
   → Notify parents in advance (typically 10 days notice)
   → Record IEP meeting date

   [SYSTEM: Auto-alert if 30-day deadline from eligibility approaches]

2. DEVELOP IEP collaboratively:
   → Present Levels (PLAAFP): Current performance in all affected areas
   → Annual Goals: For each area of need:
      - Goal description (measurable)
      - Baseline performance
      - Target performance
      - Measurement method (observation, test score, work samples)
      - Progress monitoring frequency
      - Person responsible

   → Special Education Services:
      - Service type (special ed instruction, resource room, self-contained)
      - Location (general ed classroom, resource room, separate school)
      - Frequency (minutes/week)
      - Duration (start date, end date)
      - Provider (staff member)

   → Related Services:
      - Speech therapy, OT, PT, counseling, transportation, etc.
      - Same frequency/duration/provider fields

   → Supplementary Aids and Accommodations:
      - Extended time, preferential seating, read-aloud, calculator, etc.

   → Participation in State Assessments:
      - With accommodations / alternate assessment / exempt

   → LRE Statement:
      - % of time in general education setting
      - Justification if less than 80% in general ed

   → Transition Plan (if student is 16+):
      - Postsecondary education goal
      - Employment goal
      - Independent living goal
      - Transition services to be provided

   → Progress Reporting:
      - How often parents receive progress reports (typically quarterly)

3. OBTAIN signatures:
   → Parents sign IEP (consent to placement)
   → Record all team members present and signatures obtained

4. IMPLEMENT IEP:
   → IEP goes into effect immediately upon parent signature
   → Teachers and service providers receive notification of student's IEP
   → Relevant staff can view accommodations and goals

5. TRACK service delivery:
   → Each provider logs sessions: date, minutes delivered, notes
   → System compares delivered vs. IEP-mandated minutes
   → Alert when service is falling significantly behind mandate
```

---

### Workflow 3.4: IEP Annual Review and Amendment

**Trigger:** 12-month anniversary of IEP, or need for mid-year amendment.

**Steps:**

```
ANNUAL REVIEW:
1. SYSTEM alerts 30 days before annual review due date
2. Schedule annual IEP review meeting (notify parents)
3. REVIEW all goals: progress documented per reporting period
4. REVISE goals, services, accommodations as needed
5. Create new IEP version (prior year IEP preserved as history)
6. Obtain parent signature on revised IEP
7. New 12-month cycle begins from review date

MID-YEAR AMENDMENT:
1. School or parent requests amendment to current IEP
2. Can be done without full meeting (with parent agreement in writing)
3. Create amendment record: what changed, why, date
4. Prior IEP content preserved (amendment is additive, not destructive)
5. Parent notification required

TRIENNIAL RE-EVALUATION (every 3 years):
1. SYSTEM alerts 90 days before 3-year re-evaluation due
2. Obtain parent consent for re-evaluation
   (Parent can waive re-evaluation with mutual written agreement)
3. Conduct updated evaluation (may be less comprehensive than initial)
4. Update eligibility determination and disability categories
5. Update IEP at annual review following re-evaluation
```

---

### Workflow 3.5: Section 504 Plan

**Trigger:** Student has a disability affecting major life activity but does not qualify for IDEA IEP.

**Steps:**

```
1. ELIGIBILITY REVIEW:
   → Team reviews evaluation data or existing documentation
   → Applies Section 504 test:
      - Does student have a physical or mental impairment?
      - Does it substantially limit a major life activity?
   → If yes: eligible for 504 Plan
   → Record eligibility determination and basis

2. DEVELOP 504 plan:
   → List accommodations (less formal than IEP):
      - Extended time / reduced workload / oral testing
      - Preferential seating / frequent breaks
      - Modified homework / note-taker / text-to-speech
      - Behavioral support / counseling access
   → Assign responsible staff for each accommodation
   → Set review date (typically annual)

3. OBTAIN parent signature
4. IMPLEMENT plan — distribute to relevant teachers
5. REVIEW annually (less formal than IEP — no re-evaluation required unless disability changes)
```

---

### Workflow 3.6: IEP Progress Monitoring

**Trigger:** Scheduled progress reporting period (quarterly) or mid-period check.

**Steps:**

```
1. EACH provider documents progress per goal:
   → Rating: met_goal / on_track / some_progress / insufficient_progress / not_started
   → Evidence: test score, observation notes, work samples
   → Updated performance level
   → Notes to parents

2. GENERATE progress report:
   → Parent-facing report for each goal with progress rating
   → Distributed on same schedule as regular report cards

3. IF goal not met at annual review:
   → Auto-flag goal as "not met" in annual review
   → IEP team must determine: continue goal / revise goal / change services

4. COMPLIANCE tracking:
   → System tracks whether progress was documented in each required period
   → Alert special ed coordinator if progress reports are overdue
```

---

## Domain 4: Grade Promotion

### Workflow 4.1: At-Risk Student Identification (Early Warning)

**Trigger:** Mid-year review point (typically November/December for semester-based schools).

**Steps:**

```
1. RUN at-risk report:
   → Query all enrolled students by grade level
   → Flag students meeting any at-risk criteria:
      - GPA below threshold (e.g., < 2.0 for grades 3-8)
      - Attendance below threshold (e.g., < 90% present)
      - Failing any required subject (Language Arts, Math, or state-specified)
      - More than X discipline incidents in year

2. REVIEW at-risk list:
   → Admin and counselor review flagged students
   → Determine if intervention is needed

3. CREATE intervention plan for each at-risk student:
   → Intervention type: tutoring / extended day / counseling / family conference / retention warning
   → Assigned staff member
   → Target improvement metrics
   → Review date

4. NOTIFY parents:
   → Letter/meeting informing parent of academic concern
   → Document notification date (required by most states)
```

---

### Workflow 4.2: End-of-Year Promotion Review

**Trigger:** End-of-year evaluation window opens (typically April 1 for May 1 notification deadline).

**Steps:**

```
1. SYSTEM generates promotion review list:
   → All students in promotion-decision grades (K–8, sometimes 9)
   → Pre-populated with: current GPA, attendance rate, failing subjects, discipline count

2. TEACHER completes promotion recommendation:
   → For each student: recommend_promote / recommend_retain / recommend_conditional
   → Free-text recommendation rationale
   → Supporting documentation (grades, attendance, test scores)

3. PRINCIPAL reviews recommendations:
   → Especially for any retention recommendations
   → Principals must consult Assistant Superintendent per many district policies
   → View student history: prior retentions, IDEA status, interventions tried

4. IF retention recommended:
   → CONVENE review team:
         - Principal
         - Classroom teacher(s)
         - Counselor
         - Parent/guardian
         - District representative (for some districts)
   → Team considers:
         - Academic skills and GPA
         - Learning ability and cognitive assessment data
         - Age and physical maturity
         - Social-emotional development
         - Prior retention history
         - Special education needs
         - Effectiveness of prior interventions

5. RECORD decision:
   → Outcome: promote / retain / conditional_promote
   → If conditional: conditions and timeline documented
   → Decision rationale recorded and immutable
   → Team members who participated documented

6. NOTIFY parents:
   → Required by most state laws before May 1
   → Written notice of retention decision
   → Include information on parent rights to appeal
   → Record notification date (legal requirement)

7. APPEAL PROCESS (if parents contest):
   → Parent files written appeal
   → Higher-level review (typically district superintendent)
   → Decision within specified window (varies by district)
   → Record appeal and final outcome

8. EXECUTE promotions (at year-end):
   → Batch action: advance all promoted students to next grade level
   → Update `educlaw_student.grade_level` for all promoted students
   → Retained students stay at current grade level
   → Generate summary report (how many per grade promoted/retained)
```

---

### Workflow 4.3: Batch Grade-Level Advancement

**Trigger:** End of school year; promotion decisions finalized.

**Steps:**

```
1. GENERATE promotion decision summary:
   → All promotion_review records with decided = true
   → Verify all students have a decision
   → Confirm no appeals outstanding

2. EXECUTE batch promotion:
   → For each student with decision = 'promote':
         - Increment grade_level (K → 1, 1 → 2, ..., 11 → 12)
         - Create history record of grade level advancement
   → For each student with decision = 'retain':
         - grade_level stays the same
         - Create retention record
   → For 12th grade promotions:
         - Trigger graduation eligibility check (credits earned, course requirements)
         - If meets graduation requirements: mark student as graduated
         - Update educlaw_student.status to 'graduated'
         - Update educlaw_student.graduation_date

3. ARCHIVE promotion review records:
   → All decisions become permanent records
   → Linked to academic year for historical review

4. GENERATE promotion report:
   → By grade level: # promoted / # retained / # conditionally promoted
   → District summary for administration
```

---

## Cross-Domain Integration Points

### Discipline ↔ Special Education
- Discipline incidents involving IDEA students trigger MDR monitoring
- MDR outcome may require IEP revision (FBA/BIP)
- IEP accommodations must be considered in discipline decisions

### Discipline ↔ Grade Promotion
- Discipline incident count is one input to promotion review
- Suspension days affect attendance calculations used in promotion criteria
- Chronic discipline issues may trigger early warning / intervention plans

### Health Records ↔ Grade Promotion
- Chronic illness-related absences are considered in promotion review
- Health records may explain attendance patterns (medical excusal)
- Special health needs may affect placement decisions

### Health Records ↔ Special Education
- Health conditions may form basis for IDEA eligibility (OHI category)
- IEP may include health accommodations (medication administration, rest breaks)
- Medical evaluations are part of IDEA evaluation process

### All Domains ↔ Parent EduClaw
- All workflows use `educlaw_student.id` as anchor
- FERPA logging goes to `educlaw_data_access_log`
- Guardian notifications use `educlaw_guardian` contacts
- Academic term context comes from `educlaw_academic_term`
