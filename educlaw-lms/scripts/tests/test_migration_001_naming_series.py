"""Part A — migration 001: year-scope the LMS connection counter (M104).

Plan home: `planning/pending_items.md` row M104. SIM:
`planning/simlogs/m104_SIM_2026-08-13.md`.

The migration rewrites a value in a shared allocator table on someone else's
live install, so the pins are weighted toward what it must NOT do:

  * it must not touch a counter row belonging to any other entity type, or any
    `LMS-` row that already carries a year;
  * it must not rewrite `educlaw_lms_connection.naming_series` — the issued
    identifiers stay, and that decision is load-bearing enough to be pinned;
  * it must not write anything at all in `--report-only`;
  * it must produce the same end state when run twice, and after a crash;
  * its audit trail must describe exactly the rows that changed, compared
    against a real before/after diff rather than against the migration's own
    report.

Every pin runs the REAL migration module against a real database.
"""
import importlib.util
import io
import json
import os
import sys
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
_MODULE_DIR = os.path.dirname(_SCRIPTS_DIR)
_MIGRATION = os.path.join(_MODULE_DIR, "migrations",
                          "001_year_scope_lms_connection_series.py")

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", os.path.join(_HERE, "helpers.py"))
get_conn = _helpers.get_conn
seed_company = _helpers.seed_company
call_action = _helpers.call_action
ns = _helpers.ns
is_ok = _helpers.is_ok

lms_sync = _load("lms_sync", os.path.join(_SCRIPTS_DIR, "lms_sync.py"))
mig = _load("migration_lms_001", _MIGRATION)

# The seam, not the driver (ADR-0034) — the same door the migration itself opens.
from erpclaw_lib.db import get_connection  # noqa: E402

# M102: pinned BY VALUE, not derived from `mig.MIGRATION_ID`. A suite that
# derives its expectation from the module under test agrees with whatever that
# module ends up holding, which is how a reassigned MIGRATION_ID survived both
# halves of the M102 gate before the two checks were paired.
MIGRATION_STEM = "001_year_scope_lms_connection_series"
YEAR = datetime.now(timezone.utc).year
TARGET_PREFIX = f"LMS-{YEAR}-"


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def env(db_path):
    conn = get_conn(db_path)
    company_id = seed_company(conn)
    yield conn, company_id, db_path
    conn.close()


def _raw(db_path):
    return get_connection(db_path)


def _counter(conn, entity_type, prefix, company_id, value):
    """Plant a naming_series counter row exactly as some writer would have."""
    row_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO naming_series (id, entity_type, prefix, current_value, "
        "company_id) VALUES (?, ?, ?, ?, ?)",
        (row_id, entity_type, prefix, value, company_id))
    conn.commit()
    return row_id


def _legacy_connection(conn, company_id, series):
    """A connection issued under the OLD writer, identifier and all."""
    cid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO educlaw_lms_connection
           (id, naming_series, display_name, lms_type, endpoint_url, status,
            company_id, created_at, updated_at, created_by)
           VALUES (?, ?, ?, 'canvas', 'https://c.example.edu', 'draft', ?,
                   '2025-03-01T00:00:00Z', '2025-03-01T00:00:00Z', '')""",
        (cid, series, f"Legacy {series}", company_id))
    conn.commit()
    return cid


def _series_snapshot(conn):
    """Every naming_series row, keyed by id — the whole table, every column."""
    cur = conn.execute("SELECT id, entity_type, prefix, current_value, company_id "
                       "FROM naming_series")
    columns = [d[0] for d in cur.description]
    return {r[0]: dict(zip(columns, tuple(r))) for r in cur.fetchall()}


def _connection_snapshot(conn):
    cur = conn.execute("SELECT id, naming_series, display_name FROM "
                       "educlaw_lms_connection")
    columns = [d[0] for d in cur.description]
    return {r[0]: dict(zip(columns, tuple(r))) for r in cur.fetchall()}


def _run(db_path, report_only=False):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = mig.run_migration(db_path, report_only=report_only)
    return result, buf.getvalue()


def _trail(conn):
    """Every audit_log row this migration wrote, oldest first."""
    cur = conn.execute(
        "SELECT entity_type, entity_id, old_values, new_values, description, skill "
        "FROM audit_log WHERE action = ? ORDER BY timestamp, entity_id",
        ("migration:" + MIGRATION_STEM,))
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, tuple(r))) for r in cur.fetchall()]
    for row in rows:
        for key in ("old_values", "new_values"):
            row[key] = json.loads(row[key]) if row[key] else None
    return rows


# ── the stem the trail is filed under ────────────────────────────────────────

def test_the_migration_id_is_the_stem_the_runner_ledgers_it_under():
    """Pinned by value: `get-audit-log --audit-action` matches on this exactly."""
    assert mig.MIGRATION_ID == MIGRATION_STEM
    assert mig.MIGRATION_DATA_CLASS == "rows"


def test_the_target_prefix_is_the_one_the_writer_will_actually_allocate(env):
    """The migrated row must be the row `_next_lms_series` hits next, or the
    migration leaves an orphan counter nothing ever touches again."""
    conn, company_id, db_path = env
    assert mig.year_prefix() == TARGET_PREFIX
    lms_sync._next_lms_series(conn, "educlaw_lms_connection", "LMS-", company_id)
    conn.commit()
    prefixes = [r["prefix"] for r in _series_snapshot(conn).values()]
    assert prefixes == [TARGET_PREFIX]


# ── the normal path ──────────────────────────────────────────────────────────

def test_an_unyeared_counter_row_is_year_scoped_and_keeps_its_sequence(env):
    conn, company_id, db_path = env
    row_id = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 7)

    result, output = _run(db_path)

    row = _series_snapshot(conn)[row_id]
    print(f"\nM104 migration: {row}")
    assert row["prefix"] == TARGET_PREFIX
    assert row["current_value"] == 7, "the sequence restarted; numbers would repeat"
    assert result["converted"] == [row_id]
    assert result["folded"] == []


def test_the_next_identifier_after_the_migration_continues_the_sequence(env):
    """End to end: migrate, then create a connection through the real action."""
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 2)
    _legacy_connection(conn, company_id, "LMS-00001")
    _legacy_connection(conn, company_id, "LMS-00002")

    _run(db_path)

    result = call_action(lms_sync.add_lms_connection, conn, ns(
        display_name="After Migration", lms_type="canvas",
        endpoint_url="https://canvas.example.edu", company_id=company_id,
        client_id="c", client_secret="s", user_id="t"))
    assert is_ok(result), result
    print(f"\nM104 next identifier after migration: {result['naming_series']}")
    assert result["naming_series"] == f"{TARGET_PREFIX}00003"


def test_every_company_is_converted_not_just_the_first(env):
    conn, company_id, db_path = env
    other = seed_company(conn)
    a = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 3)
    b = _counter(conn, "educlaw_lms_connection", "LMS-", other, 11)

    result, _ = _run(db_path)

    snapshot = _series_snapshot(conn)
    assert snapshot[a]["prefix"] == TARGET_PREFIX
    assert snapshot[b]["prefix"] == TARGET_PREFIX
    assert (snapshot[a]["current_value"], snapshot[b]["current_value"]) == (3, 11)
    assert sorted(result["converted"]) == sorted([a, b])


# ── the rows it must not touch (D10: wrong rows matched) ─────────────────────

@pytest.mark.parametrize("entity_type,prefix", [
    ("educlaw_lms_sync_log", "SYN-"),           # this module, already year-free
    ("educlaw_lms_sync_log", "SYN-2026-"),      # this module, already year-bearing
    ("sales_invoice", "INV-"),                  # another module's un-yeared row
    ("educlaw_student", "STU-"),                # another module in the same vertical
    ("educlaw_lms_connection", "LMSX-"),        # same entity, a different prefix
    ("educlaw_lms_course_mapping", "LMS-"),     # the SAME prefix, a different entity
])
def test_a_row_this_migration_does_not_own_is_never_touched(env, entity_type, prefix):
    """The mutation that matters most: a WHERE that matched more than it should.

    `sales_invoice=INV-` is planted deliberately un-yeared. It is exactly the
    shape INV-10 rejects and exactly the shape this migration is NOT allowed to
    repair, because erpclaw-selling owns that partition. The last row carries
    the same `LMS-` prefix under a different entity type, so the `entity_type`
    half of the WHERE is load-bearing and not merely present.
    """
    conn, company_id, db_path = env
    foreign = _counter(conn, entity_type, prefix, company_id, 4)
    mine = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 1)

    result, _ = _run(db_path)

    snapshot = _series_snapshot(conn)
    print(f"\nM104 untouched {entity_type}={prefix}: {snapshot[foreign]}")
    assert snapshot[foreign]["prefix"] == prefix
    assert snapshot[foreign]["current_value"] == 4
    assert result["converted"] == [mine]


def test_an_already_converted_row_is_not_converted_again(env):
    """A `LMS-<year>-` row on its own is not a stale row."""
    conn, company_id, db_path = env
    row_id = _counter(conn, "educlaw_lms_connection", TARGET_PREFIX, company_id, 5)

    result, output = _run(db_path)

    assert result["converted"] == [] and result["folded"] == []
    assert _series_snapshot(conn)[row_id]["current_value"] == 5
    assert "nothing to convert" in output


# ── the issued identifiers stay ──────────────────────────────────────────────

def test_the_issued_identifiers_are_not_rewritten(env):
    """The decision, pinned. Nothing in the tree looks a connection up by its
    series, so re-numbering an issued document buys no constitutional
    compliance (INV-10 reads the counter row, not this column) and changes a
    string a person may have written down."""
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 2)
    _legacy_connection(conn, company_id, "LMS-00001")
    _legacy_connection(conn, company_id, "LMS-00002")
    before = _connection_snapshot(conn)

    _run(db_path)

    after = _connection_snapshot(conn)
    print(f"\nM104 identifiers after migration: "
          f"{sorted(r['naming_series'] for r in after.values())}")
    assert after == before


def test_the_run_says_out_loud_how_many_old_identifiers_remain(env):
    """The discontinuity is visible in `list-lms-connections`, so the operator
    is told about it rather than discovering it."""
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 2)
    _legacy_connection(conn, company_id, "LMS-00001")
    _legacy_connection(conn, company_id, "LMS-00002")

    result, output = _run(db_path)

    assert result["legacy_identifiers"] == 2
    assert "2 existing LMS connection(s) keep their issued identifier" in output


def test_a_year_bearing_identifier_is_not_counted_as_legacy(env):
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 1)
    _legacy_connection(conn, company_id, "LMS-00001")
    _legacy_connection(conn, company_id, f"{TARGET_PREFIX}00002")

    result, _ = _run(db_path)

    assert result["legacy_identifiers"] == 1


# ── the collision path ───────────────────────────────────────────────────────

def test_a_stale_row_beside_an_existing_target_is_folded_not_duplicated(env):
    """`UNIQUE(entity_type, prefix, company_id)` makes a plain rewrite illegal
    here; the surviving counter takes the larger of the two."""
    conn, company_id, db_path = env
    stale = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 9)
    target = _counter(conn, "educlaw_lms_connection", TARGET_PREFIX, company_id, 2)

    result, output = _run(db_path)

    snapshot = _series_snapshot(conn)
    print(f"\nM104 fold: {snapshot}")
    assert stale not in snapshot, "the stale row survived"
    assert snapshot[target]["current_value"] == 9, "a number could be reused"
    assert result["folded"] == [stale] and result["converted"] == []


def test_the_fold_keeps_the_larger_counter_when_the_target_is_ahead(env):
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 2)
    target = _counter(conn, "educlaw_lms_connection", TARGET_PREFIX, company_id, 40)

    _run(db_path)

    assert _series_snapshot(conn)[target]["current_value"] == 40


def test_a_fold_for_one_company_does_not_disturb_another(env):
    conn, company_id, db_path = env
    other = seed_company(conn)
    stale_a = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 9)
    target_a = _counter(conn, "educlaw_lms_connection", TARGET_PREFIX, company_id, 2)
    stale_b = _counter(conn, "educlaw_lms_connection", "LMS-", other, 3)

    result, _ = _run(db_path)

    snapshot = _series_snapshot(conn)
    assert snapshot[target_a]["current_value"] == 9
    assert snapshot[stale_b]["prefix"] == TARGET_PREFIX
    assert result["folded"] == [stale_a] and result["converted"] == [stale_b]


# ── report-only, re-runs, crashes (D10) ──────────────────────────────────────

def test_report_only_writes_nothing_at_all(env):
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 3)
    before = _series_snapshot(conn)

    result, output = _run(db_path, report_only=True)

    assert _series_snapshot(conn) == before, "report-only wrote to naming_series"
    assert _trail(conn) == [], "report-only wrote an audit row"
    assert result["audit_rows"] == 0 and result["report_only"] is True
    assert "nothing was written" in output


def test_report_only_then_the_real_run_does_what_it_said(env):
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 3)

    reported, _ = _run(db_path, report_only=True)
    real, _ = _run(db_path)

    assert reported["converted"] == real["converted"]
    assert reported["folded"] == real["folded"]


def test_a_second_run_changes_nothing_and_says_so(env):
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 6)

    _run(db_path)
    after_first = _series_snapshot(conn)
    trail_after_first = _trail(conn)

    result, output = _run(db_path)

    assert _series_snapshot(conn) == after_first
    assert _trail(conn) == trail_after_first, "the second run duplicated the trail"
    assert result["audit_rows"] == 0
    assert "nothing to convert" in output


def test_an_install_that_never_created_a_connection_is_a_clean_no_op(env):
    conn, company_id, db_path = env
    before = _series_snapshot(conn)

    result, output = _run(db_path)

    assert _series_snapshot(conn) == before == {}
    assert result["converted"] == [] and result["audit_rows"] == 0
    assert "nothing to convert" in output


def test_a_failed_run_leaves_neither_the_change_nor_the_trail(env):
    """Same transaction, proven by breaking it rather than argued.

    The second counter row's UPDATE is made to fail after the first row and its
    audit row have executed; both must roll back, or the install ends up with a
    trail describing a change it does not carry.
    """
    conn, company_id, db_path = env
    other = seed_company(conn)
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 3)
    _counter(conn, "educlaw_lms_connection", "LMS-", other, 4)
    before = _series_snapshot(conn)

    original = mig._UPDATE_PREFIX
    mig._UPDATE_PREFIX = "UPDATE naming_series SET no_such_column = ? WHERE id = ?"
    try:
        with pytest.raises(Exception):
            _run(db_path)
    finally:
        mig._UPDATE_PREFIX = original

    assert _trail(conn) == [], "a rolled-back run left audit rows behind"
    assert _series_snapshot(conn) == before, "the failed run changed a counter row"


# ── the audit trail (M102) ───────────────────────────────────────────────────

def test_the_trail_describes_exactly_the_rows_that_changed(env):
    """The row-level check the static L0 gate cannot make: the trail is compared
    against the ACTUAL before/after diff of `naming_series`, not against what the
    migration says it did. A trail built from a different variable than the
    UPDATE, or one that reports the new prefix as the old one, is a defect every
    other test in this file passes over.
    """
    conn, company_id, db_path = env
    other = seed_company(conn)
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 3)
    _counter(conn, "educlaw_lms_connection", "LMS-", other, 4)
    _counter(conn, "educlaw_lms_sync_log", "SYN-2026-", company_id, 1)
    before = _series_snapshot(conn)

    result, _ = _run(db_path)
    after = _series_snapshot(conn)

    changed = {rid: (before[rid], after[rid]) for rid in before
               if rid not in after or before[rid] != after[rid]}
    assert changed, "nothing changed, so this test would pass vacuously"

    rows = {r["entity_id"]: r for r in _trail(conn)}
    assert set(rows) == set(changed), (
        f"the trail names a different set of rows than the ones that changed: "
        f"trail={sorted(rows)} changed={sorted(changed)}")
    for rid, (old, new) in changed.items():
        row = rows[rid]
        assert row["entity_type"] == "naming_series"
        assert row["skill"] == "educlaw-lms"
        assert row["old_values"] == {"prefix": old["prefix"]}, (rid, row)
        assert row["new_values"] == {"prefix": new["prefix"]}, (rid, row)
    assert result["audit_rows"] == len(changed)


def test_a_folded_row_records_its_whole_contents_because_it_is_gone(env):
    """For a deleted row the trail is the only remaining copy, so the
    changed-columns-only rule does not apply to it."""
    conn, company_id, db_path = env
    stale = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 9)
    target = _counter(conn, "educlaw_lms_connection", TARGET_PREFIX, company_id, 2)

    _run(db_path)

    row = next(r for r in _trail(conn) if r["entity_id"] == stale)
    print(f"\nM104 fold trail: {row['old_values']} -> {row['new_values']}")
    assert row["old_values"] == {"entity_type": "educlaw_lms_connection",
                                 "prefix": "LMS-", "current_value": 9,
                                 "company_id": company_id}
    assert row["new_values"]["folded_into"] == target
    assert row["new_values"]["current_value"] == 9


def test_the_trail_carries_what_a_reversal_needs(env):
    """M102's whole point: the reversal must not depend on scrollback."""
    conn, company_id, db_path = env
    row_id = _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 3)

    _run(db_path)

    row = next(r for r in _trail(conn) if r["entity_id"] == row_id)
    assert row_id in row["description"]
    assert "'LMS-'" in row["description"]
    assert "reverse" in row["description"]


def test_the_run_tells_the_operator_where_the_trail_is(env):
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 1)

    _, output = _run(db_path)

    assert f'get-audit-log --audit-action "migration:{MIGRATION_STEM}"' in output


# ── the constitution, after the migration ────────────────────────────────────

def _find_repo_root(start):
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, "CLAUDE.md")) or \
                os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError(f"repo root not found from {start}")
        cur = parent


try:
    _INV_PATH = os.path.join(_find_repo_root(_HERE), "testing", "invariant_engine.py")
except RuntimeError:
    _INV_PATH = ""
if _INV_PATH and os.path.exists(_INV_PATH):
    _spec = importlib.util.spec_from_file_location("invariant_engine_m104_mig", _INV_PATH)
    inv_engine = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(inv_engine)
else:                                             # pragma: no cover - published tree
    inv_engine = None


def test_inv10_goes_from_red_to_clean_across_the_migration(env):
    """The whole point of the migration, driven: a database carrying the old
    counter row fails INV-10 before and passes after."""
    if inv_engine is None:                        # pragma: no cover - published tree
        pytest.skip("invariant_engine harness not present (published skill tree)")
    conn, company_id, db_path = env
    _counter(conn, "educlaw_lms_connection", "LMS-", company_id, 2)
    _legacy_connection(conn, company_id, "LMS-00001")

    raw = _raw(db_path)
    try:
        before = inv_engine._check_inv10_naming_series_format(raw)
    finally:
        raw.close()
    print(f"\nM104 INV-10 before migration: {before}")
    assert before == "1 invalid naming series format(s): educlaw_lms_connection=LMS-"

    _run(db_path)

    raw = _raw(db_path)
    try:
        after = inv_engine._check_inv10_naming_series_format(raw)
    finally:
        raw.close()
    print(f"M104 INV-10 after migration: {after or 'clean'}")
    assert after is None
