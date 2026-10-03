"""The scheduling scripts render updated_at through the dialect helper, and only inside f-strings.

Every converted statement formats erpclaw_lib.query.now(), imported as sql_now.
A statement that carries the text {sql_now()} without the f prefix would send
those characters to the database instead of a timestamp, and nothing else in
this suite would notice for the statements it does not execute. This test loads
both scripts, checks the binding, and walks their string literals.
"""
import ast
import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)


def _load(name, directory):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_load("helpers", _HERE)  # puts the scripts directory and the in-tree erpclaw_lib on sys.path

SCRIPTS = ("conflict_resolution", "master_schedule")


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_binds_the_dialect_helper(name, monkeypatch):
    monkeypatch.setenv("ERPCLAW_DB_DIALECT", "sqlite")
    mod = _load(name, _SCRIPTS)
    assert callable(getattr(mod, "sql_now", None)), f"{name}.py does not bind sql_now"
    assert str(mod.sql_now()) == "datetime('now')"


@pytest.mark.parametrize("name", SCRIPTS)
def test_no_plain_string_carries_the_helper_placeholder(name):
    with open(os.path.join(_SCRIPTS, f"{name}.py"), encoding="utf-8") as fh:
        source = fh.read()
    assert "datetime('now')" not in source
    tree = ast.parse(source)
    formatted_parts = {id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)
                       for v in node.values}
    literal = [node.lineno for node in ast.walk(tree)
               if isinstance(node, ast.Constant) and isinstance(node.value, str)
               and id(node) not in formatted_parts and "{sql_now" in node.value]
    assert literal == [], f"{name}.py has '{{sql_now' in a plain string at lines {literal}"
