# EduClaw -- AI-Native Education Management

EduClaw is a modular education ERP built as [OpenClaw](https://clawhub.com) skills. It provides a complete Student Information System (SIS) with 6 packages: the core module covering students, academics, enrollment, grading, attendance, staff, fees, and communications, plus 5 expansion modules for financial aid, K-12 operations, scheduling, LMS integration, and state reporting. All financial data flows through ERPClaw's General Ledger. FERPA/COPPA compliance is built in. 483 actions across 111 tables.

## Skills

| Package | Description | Actions |
|---------|-------------|---------|
| `educlaw` | Core SIS -- students, academics, enrollment, grading, attendance, staff, fees, communications | 112 |
| `educlaw-finaid` | Financial aid -- scholarships, grants, loans, work-study, disbursements, Title IV | 116 |
| `educlaw-k12` | K-12 operations -- grade promotion, special education (IEP/504), discipline, health records | 76 |
| `educlaw-scheduling` | Scheduling -- master schedule, room assignment, conflict resolution, schedule patterns | 56 |
| `educlaw-lms` | LMS integration -- Canvas, Moodle, Google Classroom adapters, OneRoster CSV sync | 25 |
| `educlaw-statereport` | State reporting -- Ed-Fi, demographics, discipline reporting, data validation, submission tracking | 98 |
| **Total** | | **483** |

## Requirements

- [OpenClaw](https://clawhub.com) runtime
- ERPClaw foundation skills:
  - [erpclaw-setup](https://github.com/avansaber/erpclaw) -- database initialization, shared library
  - [erpclaw-gl](https://github.com/avansaber/erpclaw) -- General Ledger
  - [erpclaw-selling](https://github.com/avansaber/erpclaw) -- customer/invoice engine (students are customers)
  - [erpclaw-hr](https://github.com/avansaber/erpclaw) -- employee management (instructors are employees)
  - [erpclaw-payments](https://github.com/avansaber/erpclaw) -- payment processing

## Installation

Install each skill via ClawHub or clone this repo and symlink into your OpenClaw skills directory:

```bash
# Via ClawHub (recommended)
clawhub install educlaw
clawhub install educlaw-finaid
clawhub install educlaw-k12
clawhub install educlaw-scheduling
clawhub install educlaw-lms
clawhub install educlaw-statereport

# Initialize database tables
python3 ~/.openclaw/skills/educlaw/init_db.py
python3 ~/.openclaw/skills/educlaw-finaid/init_db.py
python3 ~/.openclaw/skills/educlaw-k12/init_db.py
python3 ~/.openclaw/skills/educlaw-scheduling/init_db.py
python3 ~/.openclaw/skills/educlaw-lms/init_db.py
python3 ~/.openclaw/skills/educlaw-statereport/init_db.py
```

## License

MIT License -- Copyright (c) 2026 AvanSaber
