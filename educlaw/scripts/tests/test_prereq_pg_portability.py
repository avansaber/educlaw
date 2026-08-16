"""Live-Postgres pin for the EduClaw course-prerequisite INSERT OR IGNORE site (M48 / Wave G F5).

``academics.py::add_course`` seeds optional prerequisites with an ``INSERT OR IGNORE``.
That verb is SQLite-only; on a first-class PostgreSQL backend it is a hard syntax
error (SQLSTATE 42601), so the shipped educlaw prerequisite path could not run there.
F5 routes the statement through ``erpclaw_lib.query.insert_or_ignore``, which rewrites
it to ``INSERT ... ON CONFLICT DO NOTHING`` on Postgres.

This pin exercises BOTH halves on a live server through the same production connection
facade (``PgConnectionWrapper`` with ``?``→``%s`` translation) and the same helper the
site now calls:
  - the RAW statement still raises a Postgres syntax error (the shipped defect), and
  - the helper-routed statement runs, and a duplicate is silently ignored (the fix).

GATED: skipped unless ``ERPCLAW_PG_TEST_URL`` points at a reachable, EXPENDABLE
Postgres database (it drops/recreates the two tables, so never point it at real data).
CI has no Postgres, so this stays skipped there; run it on the OpenClaw PG box or a
throwaway local cluster:

    ERPCLAW_PG_TEST_URL='postgresql://postgres@/erpclaw_verify?host=/tmp/pg&port=5433' \
        pytest source/educlaw/educlaw/scripts/tests/test_prereq_pg_portability.py
"""
import os
import sys

import pytest

# Make erpclaw_lib importable (mirrors the core suite's helpers.py).
# tests/ -> scripts/ -> educlaw/ -> source/educlaw/ -> source/
SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

# M54: bind erpclaw_lib to the tree under test, never the deployed
# ~/.openclaw/erpclaw/lib symlink — the last install to run wins that symlink,
# so with several worktrees in flight it resolves to a tree nobody is testing
# (and DANGLES once that worktree is removed). The deployed install stays as
# the fallback for a published module repo, which ships no source/erpclaw/.
_IN_TREE_LIB = os.path.join(SRC_DIR, "erpclaw", "scripts", "erpclaw-setup", "lib")
ERPCLAW_LIB = (_IN_TREE_LIB if os.path.isdir(os.path.join(_IN_TREE_LIB, "erpclaw_lib"))
               else os.path.join(os.path.expanduser(
                   os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))
if ERPCLAW_LIB not in sys.path:
    import importlib.util
    if importlib.util.find_spec("erpclaw_lib") is None:
        sys.path.insert(0, ERPCLAW_LIB)

PG_URL = os.environ.get("ERPCLAW_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="ERPCLAW_PG_TEST_URL not set (live Postgres required for the PG-portability pin)",
)

# The exact statement from academics.py::add_course (the M48 site), kept verbatim so
# this pin tracks the shipped SQL. The leading ``INSERT OR IGNORE`` is what the dialect
# helper rewrites on Postgres.
_PREREQ_INSERT = (
    """INSERT OR IGNORE INTO educlaw_course_prerequisite
       (id, course_id, prerequisite_course_id, min_grade, is_corequisite, created_at, created_by)
       VALUES (?, ?, ?, ?, ?, ?, ?)"""
)

# Minimal PG-valid schema for the two tables the site touches. UNIQUE(course_id,
# prerequisite_course_id) is what the duplicate insert conflicts on.
_DDL = """
CREATE TABLE educlaw_course (
    id TEXT PRIMARY KEY
);
CREATE TABLE educlaw_course_prerequisite (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_course(id) ON DELETE RESTRICT,
    prerequisite_course_id TEXT NOT NULL DEFAULT '' REFERENCES educlaw_course(id) ON DELETE RESTRICT,
    min_grade TEXT NOT NULL DEFAULT '',
    is_corequisite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    UNIQUE(course_id, prerequisite_course_id),
    CHECK(course_id != prerequisite_course_id)
);
"""


def _params(prereq_id):
    """A prerequisite row referencing the two seeded courses (same UNIQUE pair each call)."""
    return (prereq_id, "c-src", "c-prereq", "", 0, "2026-07-31T00:00:00Z", "")


@pytest.fixture
def pg(monkeypatch):
    """Reset the two tables on the target Postgres and yield a production get_connection() wrapper."""
    import psycopg2
    monkeypatch.setenv("ERPCLAW_DB_DIALECT", "postgresql")
    monkeypatch.setenv("ERPCLAW_DB_URL", PG_URL)

    setup = psycopg2.connect(PG_URL)
    setup.autocommit = True
    with setup.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS educlaw_course_prerequisite, educlaw_course CASCADE;")
        cur.execute(_DDL)
        cur.execute("INSERT INTO educlaw_course (id) VALUES ('c-src'), ('c-prereq');")
    setup.close()

    from erpclaw_lib.db import get_connection
    conn = get_connection(PG_URL)
    yield conn
    conn.close()


def test_raw_statement_is_a_postgres_syntax_error(pg):
    """Shipped defect: the raw INSERT OR IGNORE verb is a hard PG syntax error (42601)."""
    import psycopg2
    with pytest.raises(psycopg2.ProgrammingError) as exc:
        pg.execute(_PREREQ_INSERT, _params("p1"))
    assert exc.value.pgcode == "42601", f"expected syntax_error, got pgcode {exc.value.pgcode}"
    pg.rollback()  # the failed statement aborted the transaction; clear it


def test_helper_routed_statement_runs_and_ignores_duplicate(pg):
    """The fix: helper-routed statement runs on PG, and a duplicate is silently ignored."""
    from erpclaw_lib.query import insert_or_ignore
    stmt = insert_or_ignore(_PREREQ_INSERT)
    assert "ON CONFLICT DO NOTHING" in stmt and "OR IGNORE" not in stmt

    pg.execute(stmt, _params("p1"))
    # Same UNIQUE(course_id, prerequisite_course_id) pair, different id → conflict, ignored.
    pg.execute(stmt, _params("p2"))
    pg.commit()

    cur = pg.execute("SELECT COUNT(*) FROM educlaw_course_prerequisite")
    assert cur.fetchone()[0] == 1
