# EduClaw

Education management suite for [ERPClaw](https://github.com/avansaber/erpclaw). 7 modules covering student information, financial aid, K-12, scheduling, LMS integration, state reporting, and higher education. 549+ actions total. FERPA/COPPA compliant.

## Modules

### Core (`educlaw`)
Student information system for K-12 and higher ed. 112 actions across 8 domains -- students, academics, enrollment, grading, attendance, staff, fees, and communications. Integrates with ERPClaw HR, Selling, and Payments.

### Financial Aid (`educlaw-finaid`)
Federal, state, and institutional aid with Title IV compliance. ISIR processing, SAP evaluation, R2T4 calculations, award packaging, disbursements, COD origination, scholarships, work-study, and loan tracking. 116 actions.

### K-12 (`educlaw-k12`)
Discipline management, student health records, special education (IDEA/IEP/504), and grade promotion workflows. 76 actions.

### Scheduling (`educlaw-scheduling`)
Master scheduling, schedule patterns, conflict resolution, and room assignment for K-12 and higher-education institutions. 56 actions.

### LMS Integration (`educlaw-lms`)
LMS sync with Canvas, Moodle, Google Classroom, and OneRoster CSV. Assignments, course materials, and online gradebook. Credentials AES-256 encrypted at rest. 25 actions.

### State Reporting (`educlaw-statereport`)
State reporting, Ed-Fi integration, data validation, and submission tracking for K-12 LEAs. 98 actions.

### Higher Education (`educlaw-highered`)
Registrar, student records, financial aid, alumni relations, faculty management, and admissions. 60 actions.

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

MIT License -- Copyright (c) 2026 AvanSaber / Nikhil Jathar
