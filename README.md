# EduClaw

Education management suite for [ERPClaw](https://github.com/avansaber/erpclaw). <!-- SYNC:value:group.educlaw.module_count -->7<!-- /SYNC --> modules covering student information, financial aid, K-12, scheduling, LMS integration, state reporting, and higher education. <!-- SYNC:value:group.educlaw.total_actions -->610<!-- /SYNC --> actions total. FERPA/COPPA compliant.

## Modules

### Core (`educlaw`)
Student information system for K-12 and higher ed. <!-- SYNC:value:module.educlaw.actions -->176<!-- /SYNC --> actions across 8 domains -- students, academics, enrollment, grading, attendance, staff, fees, and communications. Integrates with ERPClaw HR, Selling, and Payments.

### Financial Aid (`educlaw-finaid`)
Federal, state, and institutional aid with Title IV compliance. ISIR processing, SAP evaluation, R2T4 calculations, award packaging, disbursements, COD origination, scholarships, work-study, and loan tracking. <!-- SYNC:value:module.educlaw-finaid.actions -->116<!-- /SYNC --> actions.

### K-12 (`educlaw-k12`)
Discipline management, student health records, special education (IDEA/IEP/504), and grade promotion workflows. <!-- SYNC:value:module.educlaw-k12.actions -->76<!-- /SYNC --> actions.

### Scheduling (`educlaw-scheduling`)
Master scheduling, schedule patterns, conflict resolution, and room assignment for K-12 and higher-education institutions. <!-- SYNC:value:module.educlaw-scheduling.actions -->57<!-- /SYNC --> actions.

### LMS Integration (`educlaw-lms`)
LMS sync with Canvas, Moodle, Google Classroom, and OneRoster CSV. Assignments, course materials, and online gradebook. Credentials AES-256 encrypted at rest. <!-- SYNC:value:module.educlaw-lms.actions -->25<!-- /SYNC --> actions.

### State Reporting (`educlaw-statereport`)
State reporting, Ed-Fi integration, data validation, and submission tracking for K-12 LEAs. <!-- SYNC:value:module.educlaw-statereport.actions -->98<!-- /SYNC --> actions.

### Higher Education (`educlaw-highered`)
Registrar, student records, financial aid, alumni relations, faculty management, and admissions. <!-- SYNC:value:module.educlaw-highered.actions -->62<!-- /SYNC --> actions.

## Installation

Requires [ERPClaw](https://github.com/avansaber/erpclaw) core. Install the core module first, then add extensions:

```
install-module educlaw
install-module educlaw-finaid
install-module educlaw-k12
install-module educlaw-scheduling
install-module educlaw-lms
install-module educlaw-statereport
install-module educlaw-highered
```

Or ask naturally:

```
"I'm running a school district"
"Set me up for a university"
"I need student information and financial aid"
```

## Links

- **Source**: [github.com/avansaber/educlaw](https://github.com/avansaber/educlaw)
- **ERPClaw Core**: [github.com/avansaber/erpclaw](https://github.com/avansaber/erpclaw)
- **Website**: [erpclaw.ai](https://www.erpclaw.ai)

## License

GNU General Public License v3 -- Copyright (c) 2026 AvanSaber / Nikhil Jathar
