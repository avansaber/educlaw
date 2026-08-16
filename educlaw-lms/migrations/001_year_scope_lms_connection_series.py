"""Migration 001: give the LMS connection counter the year INV-10 requires (M104).

`add-lms-connection` used to allocate its series with the year deliberately
omitted, storing a counter row `naming_series.prefix = 'LMS-'` and issuing
identifiers shaped `LMS-00001`. Constitutional invariant INV-10 requires every
stored prefix to match `^[A-Z0-9]+-\\d{4}-$`, so the shipped writer and the
shipped check disagreed. Nik ruled 2026-08-13 that the check wins; `lms_sync.py`
now always embeds the year, and this converts the installs that already ran the
old writer. Without it, INV-10 stays red forever on any install that ever
created an LMS connection — fixing the writer alone fixes only new installs.

THERE ARE TWO ARTIFACTS AND ONLY ONE OF THEM IS WHAT INV-10 READS. Being exact
about this is the whole design:

  * the COUNTER row in `naming_series` (`entity_type='educlaw_lms_connection'`,
    `prefix='LMS-'`) — this is what INV-10 selects and rejects. It is what this
    migration changes;
  * the ISSUED identifiers in `educlaw_lms_connection.naming_series`
    (`LMS-00001`, `LMS-00002`, …) — INV-10 never looks at them. They are NOT
    rewritten. See below.

WHY THE ISSUED IDENTIFIERS ARE LEFT ALONE, measured rather than assumed. A
reference sweep of the whole tree found nothing machine-readable pointing at
them: all six foreign keys into `educlaw_lms_connection` target `id` (the
UUID), every query in the module filters on `id`, no other module reads the
table at all, the four LMS adapters (Canvas, Moodle, Google Classroom, OneRoster
CSV) never mention `naming_series` — the OneRoster export's `sourcedId` is
`company_id` and row `id` — and no frontend references it. The identifier
reaches a human in exactly two places, `lms-add-lms-connection`'s response and
`lms-list-lms-connections`, as display. So rewriting it would buy zero
constitutional compliance (INV-10 does not read it) in exchange for changing a
document number a person may have written down, and inventing a year claim for a
row whose only year evidence is `created_at`. The house rule for issued
documents is that they are not edited in place. They stay.

WHAT A LIVE INSTALL THEREFORE SEES, stated plainly because it is visible: after
this runs, `list-lms-connections` shows the old connections as `LMS-00001`,
`LMS-00002` and every new one as `LMS-<year>-000NN`. That discontinuity is real,
it is permanent, and this migration prints the count of pre-existing identifiers
so nobody has to discover it from a screen.

WHAT IT DOES, per company that has one:

  * the normal case — the counter row's `prefix` is rewritten `'LMS-'` ->
    `'LMS-<current year>-'`, keeping `current_value`. The sequence therefore
    continues rather than restarting, so no number is reused, and the row the
    fixed writer will hit on its next call is exactly this one;
  * the collision case — a `'LMS-<current year>-'` row already exists for that
    company (possible only if the fixed writer ran before this migration did).
    A plain rewrite would violate `UNIQUE(entity_type, prefix, company_id)`, so
    the surviving row takes `max()` of the two counters (never reusing a number
    already issued under either) and the stale row is removed. Its FULL contents
    go into the audit trail, because for a deleted row that trail is the only
    remaining copy.

The current year, not the year the old identifiers were issued in: the counter's
job is to number the NEXT identifier, and `_next_lms_series` keys on the current
year at call time, so any other choice would leave an orphan row the writer never
touches again.

WHOSE TABLE THIS IS. `naming_series` is provenance-owned by erpclaw-gl, but it is
a shared allocator partitioned by `entity_type`, written in production by
`erpclaw_lib.naming.get_next_name` on behalf of every module and directly by
educlaw-lms, educlaw-scheduling and this module's three domain files. Every
statement here is scoped to `entity_type = 'educlaw_lms_connection'` — the
partition educlaw-lms's own writer already owns. No other module's rows are read
for a write or touched.

Idempotent: a second run finds no `'LMS-'` row and says so, on top of the
runner's own ledger skip. Crash-safe: every write is one transaction on one
connection, so a crash rolls back to the pre-run state.

`--report-only` writes nothing at all and states exactly what the real run would
do, per counter row, with its before and after prefix.

AUDIT TRAIL (M102). One `audit_log` row per counter row changed, naming the row,
its old prefix and its new one, written on THIS connection inside the SAME
transaction as the change — so there is never a row for a change that rolled back
and never a committed change without its row. `--report-only` writes none, and a
second run changes nothing and so writes nothing. Read it back with

    get-audit-log --audit-action "migration:001_year_scope_lms_connection_series"

Authored through the seam (ADR-0034): `erpclaw_lib.db.get_connection` for the
connection, `erpclaw_lib.seam.table_exists` for the catalog question. Every
statement is a FIXED string — no table name, column name or value is ever
formatted into SQL.

SIM: planning/simlogs/m104_SIM_2026-08-13.md
Plan home: planning/pending_items.md row M104.

Usage:
    python3 001_year_scope_lms_connection_series.py [--db-path PATH] [--report-only]
"""
import argparse
import importlib.util
import os
import sys
from datetime import datetime, timezone

# Deployed-lib bootstrap, guarded: production has nothing pre-imported so this
# resolves the installed lib, while a caller that already bound a tree (tests,
# the module runner inside a worktree) keeps its binding (ADR-0034 step 2d).
if importlib.util.find_spec("erpclaw_lib") is None:  # pragma: no cover - env-dependent
    sys.path.insert(0, os.path.join(
        os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))

from erpclaw_lib import seam  # noqa: E402
from erpclaw_lib.audit import audit_migration, migration_action  # noqa: E402
from erpclaw_lib.db import get_connection  # noqa: E402
from erpclaw_lib.paths import db_default  # noqa: E402

DEFAULT_DB_PATH = db_default()

# M102: derived from the filename, never typed, so the audit trail's action
# string cannot drift from the stem migration_runner ledgers this file under.
MIGRATION_ID = os.path.splitext(os.path.basename(__file__))[0]

# This migration rewrites `prefix` in rows that existed before it ran, selected
# from the install's own data, so it writes an audit trail (M102 §3).
MIGRATION_DATA_CLASS = "rows"

MODULE_NAME = "educlaw-lms"
ENTITY_TYPE = "educlaw_lms_connection"
BASE_PREFIX = "LMS-"

# Fixed statements. Nothing is interpolated into any of them.
_SELECT_STALE = ("SELECT id, entity_type, prefix, current_value, company_id "
                 "FROM naming_series WHERE entity_type = ? AND prefix = ? "
                 "ORDER BY company_id")
_SELECT_TARGET = ("SELECT id, current_value FROM naming_series "
                  "WHERE entity_type = ? AND prefix = ? AND company_id = ?")
_UPDATE_PREFIX = "UPDATE naming_series SET prefix = ? WHERE id = ?"
_UPDATE_COUNTER = "UPDATE naming_series SET current_value = ? WHERE id = ?"
_DELETE_STALE = "DELETE FROM naming_series WHERE id = ?"
_COUNT_UNYEARED_IDENTIFIERS = (
    "SELECT COUNT(*) FROM educlaw_lms_connection WHERE naming_series LIKE 'LMS-%' "
    "AND naming_series NOT LIKE 'LMS-____-%'")


def year_prefix(year=None):
    """The prefix the fixed writer allocates under, e.g. 'LMS-2026-'.

    A module-level pure function so the tests can pin the shape without a run.
    """
    if year is None:
        year = datetime.now(timezone.utc).year
    return "%s%d-" % (BASE_PREFIX, year)


def _unyeared_identifier_count(conn, db_path):
    """How many issued identifiers still read `LMS-00001`. Reporting only.

    A missing table reads as zero: on an install where educlaw-lms's own tables
    are not present there is nothing to report, which is different from a
    migration failure.
    """
    if not seam.table_exists(ENTITY_TYPE, db_path):
        return 0
    row = conn.execute(_COUNT_UNYEARED_IDENTIFIERS).fetchone()
    return row[0] if row else 0


def _plan(conn, stale_rows, target_prefix):
    """[(stale_row, target_row_or_None)] — what each stale counter row becomes.

    Pure apart from the target lookup, so the two paths (rewrite / fold) are
    decided in one place and printed identically by the report and the real run.
    """
    out = []
    for row in stale_rows:
        target = conn.execute(
            _SELECT_TARGET, (ENTITY_TYPE, target_prefix, row["company_id"])).fetchone()
        out.append((row, target))
    return out


def _describe(row):
    return "company=%s prefix=%r current_value=%s" % (
        row["company_id"], row["prefix"], row["current_value"])


def run_migration(db_path=None, report_only=False):
    path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)
    conn = get_connection(path)
    try:
        if not seam.table_exists("naming_series", path):
            print("  naming_series absent (minimal install). Nothing to do.")
            return {"converted": [], "folded": [], "audit_rows": 0,
                    "report_only": report_only, "reason": "no naming_series table"}

        target_prefix = year_prefix()
        stale = conn.execute(_SELECT_STALE, (ENTITY_TYPE, BASE_PREFIX)).fetchall()
        legacy_identifiers = _unyeared_identifier_count(conn, path)

        if not stale:
            print("  no un-yeared '%s' counter row for %s on this install; "
                  "nothing to convert." % (BASE_PREFIX, ENTITY_TYPE))
            if legacy_identifiers:
                _print_identifier_notice(legacy_identifiers)
            return {"converted": [], "folded": [], "audit_rows": 0,
                    "report_only": report_only,
                    "legacy_identifiers": legacy_identifiers}

        plan = _plan(conn, stale, target_prefix)
        print("  un-yeared counter row(s) found: %d" % len(plan))
        for row, target in plan:
            if target is None:
                print("    %s -> prefix %r (sequence continues at %s)"
                      % (_describe(row), target_prefix, row["current_value"]))
            else:
                print("    %s -> folded into the existing %r row "
                      "(current_value %s vs %s, the larger wins)"
                      % (_describe(row), target_prefix,
                         row["current_value"], target["current_value"]))

        if report_only:
            print("  report-only: %d counter row(s) would change; "
                  "%d audit_log row(s) would be written; nothing was written."
                  % (len(plan), len(plan)))
            print("  report-only: educlaw_lms_connection.naming_series is NOT "
                  "touched, on this or the real run.")
            _print_identifier_notice(legacy_identifiers)
            return {"converted": [r["id"] for r, t in plan if t is None],
                    "folded": [r["id"] for r, t in plan if t is not None],
                    "audit_rows": 0, "report_only": True,
                    "legacy_identifiers": legacy_identifiers}

        # One transaction: every counter row and its audit row commit together
        # or not at all, so a crash can never leave a half-converted allocator.
        converted, folded, audit_rows = [], [], 0
        for row, target in plan:
            if target is None:
                conn.execute(_UPDATE_PREFIX, (target_prefix, row["id"]))
                # M102 — same connection, same transaction as the UPDATE above.
                audit_migration(
                    conn, MIGRATION_ID, "naming_series", row["id"],
                    module_name=MODULE_NAME,
                    old_values={"prefix": row["prefix"]},
                    new_values={"prefix": target_prefix},
                    description="migration %s year-scoped the %s counter for "
                                "company %s; reverse by setting prefix back to "
                                "%r on naming_series id %s"
                                % (MIGRATION_ID, ENTITY_TYPE, row["company_id"],
                                   row["prefix"], row["id"]))
                converted.append(row["id"])
                print("  converted %s -> %r" % (_describe(row), target_prefix))
            else:
                kept = max(row["current_value"], target["current_value"])
                if kept != target["current_value"]:
                    conn.execute(_UPDATE_COUNTER, (kept, target["id"]))
                conn.execute(_DELETE_STALE, (row["id"],))
                # The deleted row's FULL contents, deliberately: for a row that
                # no longer exists the trail is the only remaining copy, so the
                # changed-columns-only rule does not apply to it.
                audit_migration(
                    conn, MIGRATION_ID, "naming_series", row["id"],
                    module_name=MODULE_NAME,
                    old_values={"entity_type": row["entity_type"],
                                "prefix": row["prefix"],
                                "current_value": row["current_value"],
                                "company_id": row["company_id"]},
                    new_values={"folded_into": target["id"],
                                "prefix": target_prefix,
                                "current_value": kept},
                    description="migration %s folded the un-yeared %s counter "
                                "for company %s into the existing %r row "
                                "(kept current_value %s) and removed it"
                                % (MIGRATION_ID, ENTITY_TYPE, row["company_id"],
                                   target_prefix, kept))
                folded.append(row["id"])
                print("  folded %s into %r (current_value now %s)"
                      % (_describe(row), target_prefix, kept))
            audit_rows += 1
        conn.commit()

        print("  audit trail: %d audit_log row(s), committed with the change. "
              "Read them back with:  get-audit-log --audit-action \"%s\""
              % (audit_rows, migration_action(MIGRATION_ID)))
        _print_identifier_notice(legacy_identifiers)
        return {"converted": converted, "folded": folded,
                "audit_rows": audit_rows, "report_only": False,
                "legacy_identifiers": legacy_identifiers}
    finally:
        conn.close()


def _print_identifier_notice(count):
    """The discontinuity an operator will see, said out loud."""
    if not count:
        print("  no connection on this install carries an un-yeared identifier.")
        return
    print("  %d existing LMS connection(s) keep their issued identifier "
          "(LMS-00001 style). They are NOT rewritten: nothing in the tree looks "
          "a connection up by it (every lookup and all six foreign keys use the "
          "UUID id), and re-numbering an issued document would change a string a "
          "person may have written down. Expect list-lms-connections to show "
          "them alongside new %s000NN identifiers." % (count, year_prefix()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migration 001: year-scope the educlaw-lms connection "
                    "naming-series counter")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--report-only", action="store_true",
                        help="State what the real run would do; write nothing.")
    args = parser.parse_args()
    run_migration(args.db_path, report_only=args.report_only)
    print("educlaw-lms migration 001 "
          + ("report complete (no writes)." if args.report_only else "complete."))
