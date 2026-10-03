"""Every EduClaw script whose update actions stamp updated_at binds the dialect helper.

The update actions build their SET list from fragments and append the
updated_at fragment through erpclaw_lib.query.now(), imported as sql_now. Several
of those actions have only routability tests, so a missing import would surface
as a NameError only when someone first updates that record. This test loads each
script and checks the binding directly.
"""
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

SCRIPTS = ("academics", "attendance", "communications", "fees", "grading",
           "portal", "staff", "students", "transport")


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_binds_the_dialect_helper(name, monkeypatch):
    monkeypatch.setenv("ERPCLAW_DB_DIALECT", "sqlite")
    mod = _load(name, _SCRIPTS)
    assert callable(getattr(mod, "sql_now", None)), f"{name}.py does not bind sql_now"
    assert str(mod.sql_now()) == "datetime('now')"
    with open(os.path.join(_SCRIPTS, f"{name}.py"), encoding="utf-8") as fh:
        assert "datetime('now')" not in fh.read()
