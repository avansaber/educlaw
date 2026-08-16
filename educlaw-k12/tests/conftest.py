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

# ── M97 canonical block: product SUBPROCESSES bind this checkout ─────────────
# helpers has already bound erpclaw_lib to the tree under test (M54);
# `_M97_CHILD_LIB` is that same directory, read off the imported package so it
# cannot drift from the real binding. The e2e scenarios invoke every k12 action
# as a real SUBPROCESS, and the shipped bootstrap resolves erpclaw_lib from
# $ERPCLAW_HOME/lib FIRST (ADR-0017) -- right on a user machine, wrong here,
# where that symlink points at whichever checkout last ran an install. The
# symlink into the temp home is seeded deliberately: under a BARE temp home the
# child dies with a structured "foundation not installed" error that most
# assertions accept, so the suite would go green having verified nothing.
# Full reasoning + the poison proof: testing/unit/L0/test_subprocess_home_pin.py
import erpclaw_lib

_M97_CHILD_LIB = os.path.dirname(os.path.dirname(
    os.path.abspath(erpclaw_lib.__file__)))


@pytest.fixture(scope="session", autouse=True)
def _isolated_erpclaw_home(tmp_path_factory):
    """Pin ERPCLAW_HOME at a throwaway install seeded with this tree's lib."""
    if not os.path.isdir(os.path.join(_M97_CHILD_LIB, "erpclaw_lib")):
        yield None          # published module repo: the deployed install is right
        return
    home = str(tmp_path_factory.mktemp("erpclaw_home"))
    os.symlink(_M97_CHILD_LIB, os.path.join(home, "lib"))
    _prev = os.environ.get("ERPCLAW_HOME")
    os.environ["ERPCLAW_HOME"] = home
    yield home
    if _prev is None:
        os.environ.pop("ERPCLAW_HOME", None)
    else:
        os.environ["ERPCLAW_HOME"] = _prev


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
