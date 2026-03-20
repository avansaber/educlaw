"""Shared pytest fixtures for EduClaw K-12 unit tests.

Each test function gets its own fresh SQLite database via the `db_path`
fixture (function scope), ensuring complete isolation.
"""
import os
import sys

# Ensure the tests/ directory is on sys.path so helpers.py is importable
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import pytest
from helpers import bootstrap_foundation, run_init_db


@pytest.fixture
def db_path(tmp_path):
    """Per-test fresh SQLite database with full educlaw-k12 schema."""
    path = str(tmp_path / "test.sqlite")

    # Step 1: Bootstrap foundation tables (company, naming_series, audit_log, etc.)
    bootstrap_foundation(path)

    # Step 2: Run educlaw-k12 init_db (creates parent educlaw + K12-specific tables)
    run_init_db(path)

    # Store path in env var (useful for any subprocess-based tests)
    os.environ["ERPCLAW_DB_PATH"] = path
    yield path
    os.environ.pop("ERPCLAW_DB_PATH", None)
