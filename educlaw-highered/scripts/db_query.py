#!/usr/bin/env python3
"""EduClaw Higher Education — db_query.py (unified router)

Routes all ~60 actions across 7 domain modules: registrar, records, finaid,
alumni, faculty, admissions, reports.

Usage: python3 db_query.py --action <action-name> [--flags ...]
Output: JSON to stdout, exit 0 on success, exit 1 on error.
"""
import argparse
import json
import os
import sys

# Add shared lib to path
try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection, ensure_db_exists, DEFAULT_DB_PATH
    from erpclaw_lib.validation import check_input_lengths
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.dependencies import check_required_tables
    from erpclaw_lib.args import SafeArgumentParser
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed. Install erpclaw-setup first.",
        "suggestion": "clawhub install erpclaw-setup"
    }))
    sys.exit(1)

# Add this script's directory so domain modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from registrar import ACTIONS as REGISTRAR_ACTIONS
from records import ACTIONS as RECORDS_ACTIONS
from finaid import ACTIONS as FINAID_ACTIONS
from alumni import ACTIONS as ALUMNI_ACTIONS
from faculty import ACTIONS as FACULTY_ACTIONS
from admissions import ACTIONS as ADMISSIONS_ACTIONS
from reports import ACTIONS as REPORTS_ACTIONS

# ---------------------------------------------------------------------------
# Merge all domain actions into one router
# ---------------------------------------------------------------------------
SKILL = "highered-educlaw-highered"
REQUIRED_TABLES = ["company", "highered_degree_program"]

ACTIONS = {}
ACTIONS.update(REGISTRAR_ACTIONS)
ACTIONS.update(RECORDS_ACTIONS)
ACTIONS.update(FINAID_ACTIONS)
ACTIONS.update(ALUMNI_ACTIONS)
ACTIONS.update(FACULTY_ACTIONS)
ACTIONS.update(ADMISSIONS_ACTIONS)
ACTIONS.update(REPORTS_ACTIONS)


def main():
    parser = SafeArgumentParser(description="highered-educlaw-highered")
    parser.add_argument("--action", required=True, choices=sorted(ACTIONS.keys()))
    parser.add_argument("--db-path", default=None)

    # -- Shared IDs --
    parser.add_argument("--company-id")
    parser.add_argument("--id")
    parser.add_argument("--student-id")
    parser.add_argument("--program-id")

    # -- Registrar: degree program --
    parser.add_argument("--name")
    parser.add_argument("--degree-type")
    parser.add_argument("--department")
    parser.add_argument("--credits-required", type=int)
    parser.add_argument("--program-status")

    # -- Registrar: course --
    parser.add_argument("--code")
    parser.add_argument("--credits", type=int)
    parser.add_argument("--prerequisites")
    parser.add_argument("--description")
    parser.add_argument("--is-active", type=int)

    # -- Registrar: section --
    parser.add_argument("--course-id")
    parser.add_argument("--term")
    parser.add_argument("--year", type=int)
    parser.add_argument("--instructor")
    parser.add_argument("--capacity", type=int)
    parser.add_argument("--schedule")
    parser.add_argument("--location")
    parser.add_argument("--section-status")

    # -- Registrar: enrollment --
    parser.add_argument("--section-id")
    parser.add_argument("--enrollment-date")
    parser.add_argument("--enrollment-status")
    parser.add_argument("--grade")
    parser.add_argument("--grade-points")

    # -- Records: holds --
    parser.add_argument("--hold-type")
    parser.add_argument("--reason")
    parser.add_argument("--placed-by")
    parser.add_argument("--hold-status")

    # -- Records: academic standing --
    parser.add_argument("--academic-standing")

    # -- Financial Aid: package --
    parser.add_argument("--aid-year")
    parser.add_argument("--total-cost")
    parser.add_argument("--efc")
    parser.add_argument("--total-need")
    parser.add_argument("--grants")
    parser.add_argument("--scholarships")
    parser.add_argument("--loans")
    parser.add_argument("--work-study")
    parser.add_argument("--package-status")

    # -- Financial Aid: disbursement --
    parser.add_argument("--aid-package-id")
    parser.add_argument("--amount")
    parser.add_argument("--disbursement-date")
    parser.add_argument("--aid-type")
    parser.add_argument("--fund-source")
    parser.add_argument("--disbursement-status")

    # -- Alumni --
    parser.add_argument("--email")
    parser.add_argument("--graduation-year", type=int)
    parser.add_argument("--degree-program")
    parser.add_argument("--employer")
    parser.add_argument("--job-title")
    parser.add_argument("--engagement-level")
    parser.add_argument("--is-donor", type=int)

    # -- Alumni event --
    parser.add_argument("--event-date")
    parser.add_argument("--event-type")
    parser.add_argument("--attendees", type=int)

    # -- Alumni giving --
    parser.add_argument("--alumnus-id")
    parser.add_argument("--giving-date")
    parser.add_argument("--campaign")
    parser.add_argument("--gift-type")

    # -- Faculty --
    parser.add_argument("--faculty-id")
    parser.add_argument("--rank")
    parser.add_argument("--tenure-status")
    parser.add_argument("--hire-date")

    # -- Faculty: course assignment --
    parser.add_argument("--role")

    # -- Faculty: research grant --
    parser.add_argument("--title")
    parser.add_argument("--funding-agency")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--grant-status")

    # -- Admissions --
    parser.add_argument("--application-id")
    parser.add_argument("--application-date")
    parser.add_argument("--application-status")
    parser.add_argument("--decision")
    parser.add_argument("--decision-date")
    parser.add_argument("--conditions")
    parser.add_argument("--scholarship-offered")
    parser.add_argument("--gpa-incoming")
    parser.add_argument("--test-scores")
    parser.add_argument("--documents")
    parser.add_argument("--phone")

    # -- Transfer/What-If Audit --
    parser.add_argument("--transfer-courses")       # JSON

    # -- Pagination --
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)

    args = parser.parse_args()

    # DB connection
    db_path = args.db_path or DEFAULT_DB_PATH
    ensure_db_exists(db_path)
    conn = get_connection(db_path)

    try:
        check_required_tables(conn, REQUIRED_TABLES)
    except SystemExit:
        return

    action_fn = ACTIONS[args.action]
    action_fn(conn, args)


if __name__ == "__main__":
    main()
