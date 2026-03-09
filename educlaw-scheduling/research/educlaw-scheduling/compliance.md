# EduClaw Advanced Scheduling — Compliance & Regulatory Requirements

## Overview

Scheduling is a compliance-adjacent domain. While scheduling itself is not as heavily regulated as student data privacy (FERPA/COPPA) or admissions (Title IX), several federal and state regulations **directly constrain how schools must structure their schedules** and what data must be captured.

---

## 1. Instructional Time Requirements

### 1.1 Federal Requirements
The federal government sets broad mandates but leaves implementation to states:
- **ESSA (Every Student Succeeds Act, 2015)** — Requires "well-rounded educational opportunities" but does not mandate specific hour counts; leaves this to states
- **Title I schools** — Must provide adequate instructional time; scheduling data used in Title I monitoring and audits

### 1.2 State-Level Instructional Time Requirements

Every state has specific minimum annual instructional hour/day requirements. Scheduling systems must be configurable to track compliance:

| State Tier | Typical Requirement | Notes |
|-----------|--------------------|----|
| **K-12 Days** | 170-180 school days/year | CA=180, TX=180, NY=180, FL=180 |
| **Elementary hours** | 900-1,000 hours/year | Varies by grade band |
| **Secondary hours** | 1,000-1,080 hours/year | High school most regulated |
| **Period length** | No federal mandate | States regulate total hours, not period structure |

**Compliance Implication for EduClaw Scheduling:**
- The scheduling module must calculate **total instructional minutes per course per term**
- When a schedule is built, validate: `Σ(meeting_duration_minutes × meetings_per_cycle × cycles_per_term) ≥ state_minimum`
- Holiday and non-instruction day calendars affect this calculation

### 1.3 Carnegie Unit (Credit Hour Standard)
For high schools and higher education, the **Carnegie Unit** defines a credit hour:
- **High school:** 1 credit = 120 hours of instruction (traditional model)
- **Higher ed:** 1 semester credit hour = 1 hour of classroom instruction per week per semester (~15 contact hours)

**Compliance Implication:**
- Section meetings must accumulate to the required contact hours for the course's credit value
- Block scheduling must be validated: a 4x4 block (90-min daily, one semester) must equal the same total contact hours as traditional (50-min, three times/week, full year)
- EduClaw must calculate: `total_contact_minutes = period_length × meetings_per_cycle × cycles_in_term`

---

## 2. Special Education Scheduling (IDEA)

### 2.1 Individuals with Disabilities Education Act (IDEA)
IDEA requires that students with disabilities receive a **Free Appropriate Public Education (FAPE)** in the **Least Restrictive Environment (LRE)**. This directly impacts scheduling:

**Scheduling Constraints from IEP:**
- **Inclusion scheduling:** Students with IEPs may have specific requirements to be placed in general education sections alongside non-disabled peers
- **Resource room scheduling:** Special education service periods must be scheduled without conflicting with core academic classes
- **Related services:** Speech therapy, occupational therapy, counseling sessions need scheduling time slots
- **Timing accommodations:** Extended time for assessments; scheduling must accommodate
- **Transition planning:** High school students with IEPs may need vocational education scheduled into their course load

**EduClaw Scheduling Compliance Requirement:**
- A course request from a student with an IEP should flag any scheduling constraints from the IEP
- The conflict detection engine should respect IEP-required placements (e.g., "must be in Period 2 for resource room")
- `educlaw_instructor_constraint` pattern should extend to student placement constraints
- **Not implementing:** Full IEP management (that's a separate specialized module); only the scheduling implications

### 2.2 Section 504 of the Rehabilitation Act
Students with 504 plans (disabilities not requiring special education) may need:
- Preferential seating (room assignment consideration)
- Specific period assignments (for medical needs, fatigue management)
- Access to accessible rooms (wheelchair accessibility, ADA compliance)

**EduClaw Scheduling Compliance Requirement:**
- Room features (`educlaw_room` facilities field) should be extensible to include accessibility features
- `educlaw_room_booking` should support accessibility requirement flags
- When assigning a student with a 504 plan to a section, room accessibility should be validated

---

## 3. Teacher/Faculty Compliance Requirements

### 3.1 Teacher Contract Hours (Collective Bargaining)
In public schools, teacher schedules are governed by union contracts that specify:
- **Maximum teaching periods per day** (commonly 5 of 7 or 4 of 6)
- **Minimum prep period** (usually 1 period per day)
- **Duty-free lunch** (teachers cannot be assigned supervision duty during their contractual lunch)
- **Maximum consecutive teaching periods** (often limited to 3-4 consecutive periods without a break)
- **Planning/collaboration time** (some contracts mandate weekly common planning time for teams)

**EduClaw Scheduling Compliance Requirement:**
- `educlaw_instructor_constraint` must model:
  - `max_periods_per_day` (hard limit from contract)
  - `requires_prep_period` (boolean — must have at least one free period)
  - `max_consecutive_periods` (consecutive teaching periods without break)
  - `unavailable_periods` (specific periods teacher cannot be assigned)
- Conflict detection must include: **instructor contract violation** as a conflict type

### 3.2 Teacher Certification/Qualification Requirements
Schools must assign only qualified (state-certified) teachers to courses they are certified to teach. While EduClaw's `educlaw_instructor.credentials` field stores credential data, the scheduling module should validate:
- Instructor credentials match the course's subject area when building the schedule
- **Highly Qualified Teacher (HQT)** requirements under ESSA for Title I schools

**EduClaw Scheduling Compliance Requirement:**
- Add `subject_certifications` to instructor constraint/profile
- Warn (not block) when a section is assigned to an instructor whose credentials don't match the course department

---

## 4. Accreditation Requirements

### 4.1 Regional Accreditation Bodies
Schools accredited by regional bodies (AdvancED/Cognia, WASC, NEASC, SACSCOC) must demonstrate:
- Adequate instructional time per course
- Qualified instructors for each course
- Proper course sequence (prerequisites honored in scheduling)
- Evidence that the master schedule supports the school's educational mission

**EduClaw Scheduling Data for Accreditation:**
- The master schedule serves as an accreditation document — it must be printable/exportable
- Instructional minutes per course must be calculable from the schedule
- Instructor-to-course qualification mapping must be auditable

### 4.2 Higher Education — HLC/SACSCOC Credit Hour Standards
For community colleges and universities, the Higher Learning Commission and SACSCOC require:
- **Credit hour compliance** — 1 credit hour = 1 contact hour + 2 hours of out-of-class work per week
- **Regular and substantive interaction** — for distance education courses (not scheduling-specific, but scheduling must flag online vs. face-to-face)
- **Course scheduling must match catalog description** — a lab-required course must actually have a lab section scheduled

**EduClaw Scheduling Compliance Requirement:**
- `educlaw_section_meeting` must capture meeting mode: `in_person / hybrid / online`
- Total contact hours per section must be calculable and match the course credit hours per accreditation standards
- Lab sections must be linked to their corresponding lecture section

---

## 5. FERPA — Scheduling Data Privacy

### 5.1 Student Schedule as Education Record
Under FERPA, a student's class schedule is an **education record** — it identifies which classes the student attends, which can be used to infer information about the student (IEP status, academic level, etc.).

**Implication for EduClaw Scheduling:**
- Course request data (what courses a student requested) is an education record
- Student schedule data must be protected with role-based access
- Parents have the right to inspect their child's schedule
- Third-party scheduling tools that receive student data must comply with FERPA's "school official" exception

**Data FERPA categories covered by scheduling:**
- Student schedules: `demographics` (indirectly) + `grades` (via academic placement)
- IEP placement in schedule: `health` category (sensitive)
- Course request data: `demographics` + `academics`

**EduClaw Scheduling Compliance Requirement:**
- All scheduling data (course requests, section meetings, master schedule) must be accessible only to authorized school officials
- Student schedule data must flow through the parent EduClaw's `educlaw_data_access_log` when accessed
- Schedule export functions must respect FERPA directory information opt-out

### 5.2 Data Minimization
FERPA and general privacy best practices require collecting only necessary data:
- Course request system should not require demographic information beyond what's needed for balancing
- Scheduling constraint data (IEP-related) must be stored with appropriate sensitivity markers

---

## 6. ADA (Americans with Disabilities Act) — Room Accessibility

### 6.1 Physical Accessibility Requirements
When assigning rooms to sections, schools must ensure:
- Students with mobility impairments are assigned to accessible rooms (ground floor, elevator access, wide doorways)
- Captioning/hearing loops available in rooms for hearing-impaired students
- Visual accommodations (adequate lighting, whiteboard visibility) for visually impaired students

**EduClaw Scheduling Compliance Requirement:**
- `educlaw_room` facilities field (existing JSON) should be extended with standardized accessibility flags:
  - `wheelchair_accessible`
  - `hearing_loop`
  - `accessible_furniture`
  - `elevator_access`
- Room assignment for sections with known accessibility needs should prioritize accessible rooms

---

## 7. Title IX — Non-Discrimination in Scheduling

### 7.1 Course Access
Title IX prohibits discriminatory course assignment based on gender:
- Students cannot be tracked into gender-stereotyped courses (e.g., boys to shop class, girls to home economics) purely based on gender
- PE scheduling cannot create segregated schedules except for contact sports

**EduClaw Scheduling Compliance Requirement:**
- No `gender_restriction` field in course or section (this was removed from the recommended data model for Title IX compliance)
- If an institution requires single-sex sections for specific activities (e.g., military school), this must be implemented with explicit documentation and justified under Title IX exceptions

---

## 8. State Reporting — Schedule Data

### 8.1 Accountability Reporting
Many states require schools to report scheduling data as part of accountability systems:
- **Course Offering Reports:** What courses are offered (available for state audit of course equity)
- **Teacher Assignment Reports:** Which teachers are assigned to which courses (HQT reporting)
- **Average Class Size:** Reported by grade level and subject area
- **Instructional Time Compliance:** Evidence of meeting state minimum hour requirements

**EduClaw Scheduling Data for State Reporting:**
- Master schedule export in structured format (JSON/CSV) enables state reporting tools to consume data
- Instructor-to-course-to-section assignments stored explicitly support HQT reporting
- Average enrollment per section calculable from scheduling data

### 8.2 Ed-Fi Standards (v2 Feature)
The **Ed-Fi Data Standard** is the dominant interoperability standard for K-12 data exchange with state education agencies:
- `CourseOffering` entity maps to EduClaw section concepts
- `StaffSectionAssociation` maps to instructor assignment
- `ClassPeriod` maps to bell period
- `BellSchedule` maps to schedule pattern

**EduClaw Scheduling v2 Consideration:** Expose scheduling data via Ed-Fi-compatible API for state reporting.

---

## 9. Compliance Summary Matrix

| Regulation | Applies To | Scheduling Implication | EduClaw Implementation |
|-----------|-----------|----------------------|----------------------|
| **ESSA/State Instructional Hours** | K-12 | Calculate total instructional minutes per course | Validate contact hours when building schedule |
| **Carnegie Unit** | K-12 and Higher Ed | Credit hours must match contact hours | Calculate and display contact hours per section |
| **IDEA / IEP** | K-12 (special ed) | IEP placement constraints must be respected | IEP flag on course request; constraint-aware scheduling |
| **Section 504** | K-12 and Higher Ed | Accessible room assignment | Room accessibility features in room_booking |
| **Teacher Contract Hours** | K-12 (public) | Max periods, prep time, consecutive limits | `educlaw_instructor_constraint` table |
| **Teacher Certification (HQT)** | K-12 (Title I) | Certified teacher to course match | Warn on credential mismatch |
| **Regional Accreditation** | K-12 and Higher Ed | Schedule serves as accreditation document | Export-ready master schedule |
| **HLC Credit Hour** | Higher Ed | Contact hours = credit × 15 weeks | Contact hours validation |
| **FERPA** | K-12 and Higher Ed | Student schedule is education record | RBAC + access log integration |
| **ADA** | K-12 and Higher Ed | Accessible rooms for students with disabilities | Room accessibility flags |
| **Title IX** | K-12 and Higher Ed | No gender-based course tracking | No gender restriction fields |
| **Ed-Fi** | K-12 (state reporting) | Schedule data exchange with state | v2 API export |

---

## 10. Compliance Recommendations for EduClaw Scheduling v1

### Must Have (v1)
1. **Contact hour calculation** — Compute total instructional minutes per section from meeting pattern
2. **Instructor contract constraints** — Max periods/day, prep period requirement, consecutive period limits
3. **FERPA-aware access** — Schedule data access logged; respects directory info opt-out
4. **Room accessibility flags** — Basic accessibility attributes on room booking
5. **Teacher qualification warning** — Warn (not block) on credential-course mismatch

### Should Have (v1)
6. **IEP scheduling flag** — Flag course requests from students with IEPs for manual review
7. **Conflict type "contract violation"** — Include instructor contract violations in conflict detection
8. **Schedule export** — Machine-readable export for accreditation and state reporting

### Defer (v2)
- Full Ed-Fi integration
- Automated ADA room assignment
- State-specific reporting templates
- IEP placement management (full IDEA compliance module)

---

*Sources: ESSA statute (20 U.S.C. 6301), IDEA statute (20 U.S.C. 1400), FERPA (34 CFR Part 99), ADA Title II, Carnegie Unit history (Carnegie Foundation), HLC Credit Hour Policy, NEA collective bargaining guidelines, Ed-Fi Data Standard documentation*
