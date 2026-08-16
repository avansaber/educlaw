"""M104 — the LMS naming series carries a year, and INV-10 can see that it does.

THE DISAGREEMENT THIS PINS. `add-lms-connection` used to allocate its series
through `_next_lms_series(..., "LMS-", company_id, use_year=False)` and store a
counter row `naming_series.prefix = 'LMS-'`. Constitutional invariant INV-10
requires every stored prefix to match `^[A-Z0-9]+-\\d{4}-$`, so the shipped
writer and the shipped check disagreed: INV-10 was clean before the production
call and reported `1 invalid naming series format(s):
educlaw_lms_connection=LMS-` after it. Nik ruled 2026-08-13 that the check wins.

WHY THE MODULE'S OWN SUITE NEVER SAW IT, stated rather than implied. The
invariant engine short-circuits EVERY registered check when `gl_entry` is empty
(`invariant_engine.py`, `run_all`), and this module posts no GL at all, so a
whole-engine run over an educlaw-lms database reports INV-10 as skipped rather
than failed. That short-circuit is row M99 and is NOT fixed here — fixing it
changes what every empty-ledger declaration in the tree means. What is fixed
here is the narrower thing that can be fixed honestly from a module suite:
:func:`test_inv10_itself_is_clean_after_the_module_writes_its_series` calls the
INV-10 check DIRECTLY, so the constitution's own pattern (not a copy of it) is
executed against a database this module wrote.

Two tests, deliberately not one:

  * the first states the format in the module's own terms and runs everywhere,
    including the published `avansaber/educlaw` tree where `testing/` does not
    exist;
  * the second makes the constitutional claim and is guarded on the harness
    being present, which is the house idiom for a module test that reaches into
    `testing/` (`erpclaw-selling/tests/test_inv25_flows.py` and five siblings).

Plan home: `planning/pending_items.md` row M104.
SIM: `planning/simlogs/m104_SIM_2026-08-13.md`.
"""
import importlib.util
import os
import re
from datetime import datetime, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(directory, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load("helpers", _HERE)
call_action = _helpers.call_action
ns = _helpers.ns
get_conn = _helpers.get_conn
is_ok = _helpers.is_ok
seed_company = _helpers.seed_company

lms_sync = _load("lms_sync", _SCRIPTS_DIR)

# The seam, not the driver (ADR-0034): these reads go through the same door
# production uses, and the invariant check below runs against exactly the
# connection shape it would see on a live install.
from erpclaw_lib.db import get_connection  # noqa: E402


# ── the invariant engine, when this tree has one ─────────────────────────────

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
    _spec = importlib.util.spec_from_file_location("invariant_engine_m104", _INV_PATH)
    inv_engine = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(inv_engine)
else:                                             # pragma: no cover - published tree
    inv_engine = None


# The module's OWN statement of what it issues: a base, this year, a five-digit
# sequence. Deliberately not a copy of INV-10's regex — the constitutional claim
# is made below by running INV-10 itself.
_ISSUED = re.compile(r"^LMS-\d{4}-\d{5}$")


def _year():
    return datetime.now(timezone.utc).year


def _add_connection(conn, company_id, display_name="Canvas Prod"):
    result = call_action(lms_sync.add_lms_connection, conn, ns(
        display_name=display_name, lms_type="canvas",
        endpoint_url="https://canvas.example.edu", company_id=company_id,
        client_id="cid", client_secret="secret", user_id="tester"))
    assert is_ok(result), result
    return result


def _counter_rows(db_path):
    raw = get_connection(db_path)
    try:
        return [dict(r) for r in raw.execute(
            "SELECT entity_type, prefix, current_value FROM naming_series "
            "ORDER BY entity_type, prefix")]
    finally:
        raw.close()


@pytest.fixture
def setup(db_path):
    conn = get_conn(db_path)
    company_id = seed_company(conn)
    yield conn, company_id, db_path
    conn.close()


# ── the writer ───────────────────────────────────────────────────────────────

def test_add_lms_connection_issues_a_year_bearing_identifier(setup):
    """The identifier a user sees carries the year, like every other entity."""
    conn, company_id, _db_path = setup
    result = _add_connection(conn, company_id)
    issued = result["naming_series"]
    print(f"\nM104 issued identifier: {issued}")
    assert _ISSUED.match(issued), (
        f"{issued!r} is not PREFIX-YEAR-SEQUENCE; the un-yeared LMS-00001 format "
        f"is what INV-10 rejects (M104)")
    assert issued == f"LMS-{_year()}-00001"


def test_the_stored_counter_prefix_carries_the_year(setup):
    """INV-10 reads the COUNTER row, not the issued identifier.

    This is the distinction M104 turns on: `educlaw_lms_connection.naming_series`
    holds `LMS-2026-00001` and `naming_series.prefix` holds `LMS-2026-`, and only
    the second is what the constitutional check looks at. A fix that changed the
    issued string without changing the counter row would leave INV-10 red.
    """
    conn, company_id, db_path = setup
    _add_connection(conn, company_id)
    rows = _counter_rows(db_path)
    print(f"\nM104 counter rows: {rows}")
    connection_rows = [r for r in rows
                       if r["entity_type"] == "educlaw_lms_connection"]
    assert connection_rows, "no counter row was written at all"
    assert [r["prefix"] for r in connection_rows] == [f"LMS-{_year()}-"]


def test_the_sequence_still_increments_within_the_year(setup):
    """The year did not cost the counter its job."""
    conn, company_id, _db_path = setup
    first = _add_connection(conn, company_id, "Canvas Prod")["naming_series"]
    second = _add_connection(conn, company_id, "Moodle Prod")["naming_series"]
    print(f"\nM104 sequence: {first} then {second}")
    assert (first, second) == (f"LMS-{_year()}-00001", f"LMS-{_year()}-00002")


# ── the constitution ─────────────────────────────────────────────────────────

def test_inv10_itself_is_clean_after_the_module_writes_its_series(setup):
    """INV-10, executed against a database this module wrote.

    The engine's own check function, not a copy of its regex — so a change to
    what the constitution requires shows up here rather than passing against a
    stale duplicate. Called directly because a whole-engine run would report
    every check as skipped on a database with no `gl_entry` rows (M99).
    """
    if inv_engine is None:                        # pragma: no cover - published tree
        pytest.skip("invariant_engine harness not present (published skill tree)")
    conn, company_id, db_path = setup

    raw = get_connection(db_path)
    try:
        before = inv_engine._check_inv10_naming_series_format(raw)
    finally:
        raw.close()
    assert before is None, f"INV-10 was already red before this module wrote: {before}"

    _add_connection(conn, company_id)

    raw = get_connection(db_path)
    try:
        after = inv_engine._check_inv10_naming_series_format(raw)
    finally:
        raw.close()
    print(f"\nM104 INV-10 after add-lms-connection: {after or 'clean'}")
    assert after is None, (
        f"the shipped writer and the shipped check disagree again: {after}")


def test_every_series_this_module_writes_satisfies_inv10(setup):
    """Not just the connection: the sync-log series goes through INV-10 too.

    `apply-course-sync`, `submit-assessment-to-lms` and the gradebook actions all
    allocate a `SYN-` series through the same helper. They were already
    year-bearing, and this keeps them that way — an un-yeared regression in any
    of them is the same finding under a different prefix.
    """
    if inv_engine is None:                        # pragma: no cover - published tree
        pytest.skip("invariant_engine harness not present (published skill tree)")
    conn, company_id, db_path = setup
    _add_connection(conn, company_id)
    # Allocate a sync-log series directly: the actions that do it need a live
    # connection, an academic term and a section, and the series allocation is
    # the only part of them this test is about.
    lms_sync._next_lms_series(conn, "educlaw_lms_sync_log", "SYN-", company_id)
    conn.commit()

    rows = _counter_rows(db_path)
    print(f"\nM104 all counter rows: {rows}")
    assert len(rows) == 2, rows
    raw = get_connection(db_path)
    try:
        verdict = inv_engine._check_inv10_naming_series_format(raw)
    finally:
        raw.close()
    assert verdict is None, verdict


def test_the_helper_can_no_longer_be_asked_to_drop_the_year(setup):
    """The mechanism, not just the call site.

    `_next_lms_series` used to take `use_year=False`, which is how one call site
    came to emit a prefix the constitution rejects. The parameter is gone, so a
    future call cannot reintroduce the disagreement by passing a flag.
    """
    conn, company_id, _db_path = setup
    with pytest.raises(TypeError):
        lms_sync._next_lms_series(
            conn, "educlaw_lms_connection", "LMS-", company_id, use_year=False)
