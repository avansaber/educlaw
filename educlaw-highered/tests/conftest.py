"""Shared pytest fixtures for EduClaw Higher Education unit tests.

Each test function gets its own fresh SQLite database via the `db_path`
fixture (function scope), ensuring complete isolation.
"""
import os
import sqlite3
import sys

# Ensure the tests/ directory is on sys.path so helpers.py is importable
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Add educlaw root to path so educlaw_base_schema is importable
_EDUCLAW_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _EDUCLAW_ROOT not in sys.path:
    sys.path.insert(0, _EDUCLAW_ROOT)

import pytest
from helpers import bootstrap_foundation, run_init_db


@pytest.fixture
def db_path(tmp_path):
    """Per-test fresh SQLite database with full educlaw-highered schema."""
    path = str(tmp_path / "test.sqlite")

    # Step 1: Bootstrap foundation tables (company, naming_series, audit_log)
    bootstrap_foundation(path)

    # Step 2: Create educlaw base tables (6 merged tables now live here)
    from educlaw_base_schema import ensure_educlaw_base_tables
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_educlaw_base_tables(conn)
    conn.close()

    # Step 3: Run educlaw-highered init_db (creates 12 highered-only tables)
    run_init_db(path)

    # Store path in env var (useful for any subprocess-based tests)
    os.environ["ERPCLAW_DB_PATH"] = path
    yield path
    os.environ.pop("ERPCLAW_DB_PATH", None)
