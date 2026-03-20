"""Shared pytest fixtures for EduClaw K-12 unit tests."""
import importlib.util
import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Load helpers by explicit path to avoid cross-module collisions
_spec = importlib.util.spec_from_file_location(
    "k12_helpers", os.path.join(_TESTS_DIR, "helpers.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
init_all_tables = _helpers.init_all_tables


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.sqlite")
    init_all_tables(path)
    os.environ["ERPCLAW_DB_PATH"] = path
    yield path
    os.environ.pop("ERPCLAW_DB_PATH", None)
