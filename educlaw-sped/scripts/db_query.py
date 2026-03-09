#!/usr/bin/env python3
"""EduClaw SPED — db_query.py (unified router)

Routes all 20 actions across 3 domain modules:
  iep (8), services (7), compliance (4), + status (1)

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
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed. Run: clawhub install erpclaw-setup",
        "suggestion": "clawhub install erpclaw-setup"
    }))
    sys.exit(1)

# Add scripts dir so domain modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iep import ACTIONS as IEP_ACTIONS
from services import ACTIONS as SERVICE_ACTIONS
from compliance import ACTIONS as COMPLIANCE_ACTIONS

# ─────────────────────────────────────────────────────────────────────────────
# Merge all domain actions into one router
# ─────────────────────────────────────────────────────────────────────────────
SKILL = "sped-educlaw-sped"
REQUIRED_TABLES = ["company", "sped_iep", "sped_service"]

ACTIONS = {}
ACTIONS.update(IEP_ACTIONS)
ACTIONS.update(SERVICE_ACTIONS)
ACTIONS.update(COMPLIANCE_ACTIONS)
ACTIONS["status"] = lambda conn, args: ok({
    "skill": SKILL,
    "version": "1.0.0",
    "actions_available": len([k for k in ACTIONS if k != "status"]),
    "domains": ["iep", "services", "compliance"],
    "database": DEFAULT_DB_PATH,
})


def main():
    parser = argparse.ArgumentParser(description="sped-educlaw-sped")
    parser.add_argument("--action", required=True, choices=sorted(ACTIONS.keys()))
    parser.add_argument("--db-path", default=None)

    # ── Shared ────────────────────────────────────────────────────────────
    parser.add_argument("--company-id")
    parser.add_argument("--user-id")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--search")
    parser.add_argument("--notes")
    parser.add_argument("--days-ahead", type=int, default=30)

    # ── IEP ───────────────────────────────────────────────────────────────
    parser.add_argument("--iep-id")
    parser.add_argument("--student-id")
    parser.add_argument("--iep-date")
    parser.add_argument("--review-date")
    parser.add_argument("--annual-review-date")
    parser.add_argument("--disability-category")
    parser.add_argument("--placement")
    parser.add_argument("--lre-percentage")
    parser.add_argument("--case-manager")
    parser.add_argument("--meeting-participants")
    parser.add_argument("--iep-status")

    # ── IEP Goal ──────────────────────────────────────────────────────────
    parser.add_argument("--goal-id")
    parser.add_argument("--goal-area")
    parser.add_argument("--goal-description")
    parser.add_argument("--baseline")
    parser.add_argument("--target")
    parser.add_argument("--current-progress")
    parser.add_argument("--measurement-method")
    parser.add_argument("--goal-status")
    parser.add_argument("--sort-order", type=int, default=0)

    # ── Service ───────────────────────────────────────────────────────────
    parser.add_argument("--service-id")
    parser.add_argument("--service-type")
    parser.add_argument("--provider")
    parser.add_argument("--frequency-minutes-per-week", type=int, default=0)
    parser.add_argument("--setting")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--service-status")

    # ── Service Log ───────────────────────────────────────────────────────
    parser.add_argument("--session-date")
    parser.add_argument("--duration-minutes", type=int, default=0)
    parser.add_argument("--session-notes")
    parser.add_argument("--is-makeup-session", type=int, default=0)
    parser.add_argument("--was-absent", type=int, default=0)
    parser.add_argument("--absence-reason")

    args, _unknown = parser.parse_known_args()
    check_input_lengths(args)

    db_path = getattr(args, "db_path", None) or DEFAULT_DB_PATH
    ensure_db_exists(db_path)
    conn = get_connection(db_path)

    _dep = check_required_tables(conn, REQUIRED_TABLES)
    if _dep:
        _dep["suggestion"] = (
            "clawhub install erpclaw-setup && "
            "clawhub install educlaw-sped && "
            "python3 init_db.py"
        )
        print(json.dumps(_dep, indent=2))
        conn.close()
        sys.exit(1)

    try:
        ACTIONS[args.action](conn, args)
    except Exception as e:
        conn.rollback()
        sys.stderr.write(f"[{SKILL}] {e}\n")
        err(str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
